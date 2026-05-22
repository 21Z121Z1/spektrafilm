"""Bundle builder.

Drives the spektrafilm pipeline through its named taps with
``lut_mode`` active, samples a 3D cube grid in the input color space,
and packs the encoded output into a :class:`Lut`. M4 implements the
1-LUT topology; 2-LUT / 4-LUT follow in later milestones.

The boundary contract with the runtime (see
``src/spektrafilm_lut_creator/README.md``):

1. Generate a cube grid in the *encoded* input space (e.g., sRGB code
   values, Apple Log code values).
2. CCTF-decode → linear-light RGB in the input space's primaries.
3. Configure ``RuntimePhotoParams.io.input_primaries`` from the registry
   entry; both ``input_cctf_decoding`` and ``output_cctf_encoding`` stay
   False (the LUT creator owns the transport encoding).
4. Run the pipeline. The scan stage clips the bounded reflectance
   output to ``[0, 1]`` by physics (see n070 §1.5).
5. CCTF-encode → encoded LUT values in the output color space.

See studies/a40_lut_system/n030_lut_package_design.md §6 and n070 §6.
"""
from __future__ import annotations

import json
import math
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from spektrafilm_lut_creator.bundles import Bundle, BundleSpec
from spektrafilm_lut_creator.color_spaces import (
    decode_cctf,
    encode_cctf,
    input_exposure_gain,
    get as get_color_space,
)
from spektrafilm_lut_creator.formats import Lut, get_format
from spektrafilm_lut_creator.grid import cube_grid, grid_as_image
from spektrafilm_lut_creator.metadata import (
    SCHEMA_VERSION,
    BundleMeta,
    ColorSpaceMeta,
    InputExposureMeta,
    LutFileMeta,
    ProvenanceMeta,
    StocksMeta,
    WiresMeta,
)
from spektrafilm_lut_creator.shapers import (
    code_to_density,
    code_to_log_e,
    density_to_code,
    log_e_to_code,
)
from spektrafilm_lut_creator.wires import BoundaryWires, DensityWire, LogEWire


# Resolution of the d_max sampling grid for 2-LUT bundles. 9^3 = 729
# samples is enough to characterize each channel's max density well past
# the final LUT's grid spacing, and the pipeline call is sub-second.
_DENSITY_PROBE_RESOLUTION = 9

# Multiplicative headroom over the observed max density. Prevents the
# wire's nominal d_max from clipping any sample exactly at 1.0 in the
# output cube, which would lose interpolation precision at the
# shoulder.
_DENSITY_MARGIN = 1.05

# Below-zero headroom on the cmy_film wire. The cmy_film density taps
# the pipeline output above the base+fog floor — i.e. D >= 0 in the
# pipeline's deterministic mode. A user injecting grain in the
# intermediate code space will produce noise that fluctuates *around*
# the dye density, dipping briefly below zero (real fog grain works
# this way too). Reserving 0.2 of density below the natural floor lets
# that excursion survive the wire's [0, 1] code clamp without clipping.
_CMY_FILM_FOG_HEADROOM = 0.2

# Additive padding (in log10(E) units) around the observed [min, max] of
# a log_e tap. ~0.1 ≈ 1/3 stop on each side — enough that grid samples
# near the endpoints don't suffer trilinear clip artifacts.
_LOG_E_MARGIN = 0.1

# Decimal places to which wire constants are clamped before being applied
# and serialized. A human-interface choice: wires are read and edited by
# colorists inside node graphs, so short numbers are easier to copy and
# reason about. The LUT itself is baked against the clamped values, so
# precision of the cube is unchanged — only the wire's headroom moves by
# at most 10^-_WIRE_DECIMALS, and we always round *outward* so the wire
# strictly contains the observed data range.
_WIRE_DECIMALS = 4


def _round_wire_floor(value: float, decimals: int = _WIRE_DECIMALS) -> float:
    """Round down to ``decimals`` places (toward more-negative)."""
    factor = 10 ** decimals
    return math.floor(value * factor) / factor


def _round_wire_ceil(value: float, decimals: int = _WIRE_DECIMALS) -> float:
    """Round up to ``decimals`` places (toward more-positive)."""
    factor = 10 ** decimals
    return math.ceil(value * factor) / factor


_LUT_LICENSE_FILENAME = "SPEKTRAFILM_LICENSE.txt"
_BUNDLE_README_FILENAME = "README.md"


def _input_exposure_meta(spec: BundleSpec) -> InputExposureMeta | None:
    """Build the bundle.json record for the active input exposure gain.

    Returns ``None`` when ``spec.stops_above_gray`` is ``None`` (native
    behavior, no gain applied) — there's nothing creative baked into
    the LUT to disclose. Otherwise records the target stops-above-gray
    and the resulting linear gain so consumers can see exactly what
    multiplication the LUT internally absorbed.
    """
    if spec.stops_above_gray is None:
        return None
    gain = input_exposure_gain(spec.input_color_space, spec.stops_above_gray)
    return InputExposureMeta(
        stops_above_gray=float(spec.stops_above_gray),
        gain=float(gain),
    )

# Default base directory for `BundleBuilder.write(bundle)` when no out_dir
# is provided. Resolved against `Path.cwd()` at write time, so running a
# bake script from any directory drops its output into a sibling
# `build/lut_bundles/<name>/`. The `build/` parent is the conventional
# gitignored scratch space; `lut_bundles/` separates LUT artifacts from
# other build outputs the project might emit alongside (reports, plots,
# etc.) — see the bundle README guidance for context.
_DEFAULT_OUT_SUBPATH = Path("build") / "lut_bundles"


# Stock + version normalization moved to spektrafilm_lut_creator.naming so
# bundles.BundleSpec.__post_init__ can compute its default name without a
# circular import. Re-exported here under the old underscored names to keep
# this module's internal call sites unchanged.
from spektrafilm_lut_creator.naming import (  # noqa: E402
    normalize_stock as _normalize_stock,
    normalize_version as _normalize_version,
)


def _canonical_lut_filename(
    spec: BundleSpec, print_stock: str, version_tag: str, *, ext: str = ".cube"
) -> str:
    """Build the canonical camera-safe LUT filename for a combined 1-LUT.

    Pattern: ``lut_{version}_{film}_{print}.cube``
    Example: ``lut_v032_portra400_supraendura.cube``
    """
    film = _normalize_stock(spec.film_profile)
    print_tag = _normalize_stock(print_stock)
    return f"lut_{version_tag}_{film}_{print_tag}{ext}"


def _canonical_lut_title(spec: BundleSpec, print_stock: str, version_tag: str) -> str:
    """Compact LUT title for a combined 1-LUT: ``{version}_{film}_{print}``."""
    film = _normalize_stock(spec.film_profile)
    print_tag = _normalize_stock(print_stock)
    return f"{version_tag}_{film}_{print_tag}"


def _film_lut_filename(spec: BundleSpec, version_tag: str, *, ext: str = ".cube") -> str:
    """2-LUT film-half filename: ``lut_{version}_{film}_film.cube``.

    The film LUT is shared across prints within the bundle; the
    ``_film`` suffix marks it as the L1∘L2 half (input RGB → normalized
    cmy_film density).
    """
    film = _normalize_stock(spec.film_profile)
    return f"lut_{version_tag}_{film}_film{ext}"


def _film_lut_title(spec: BundleSpec, version_tag: str) -> str:
    """2-LUT film-half title: ``{version}_{film}_film``."""
    film = _normalize_stock(spec.film_profile)
    return f"{version_tag}_{film}_film"


def _print_lut_filename(
    spec: BundleSpec, print_stock: str, version_tag: str, *, ext: str = ".cube"
) -> str:
    """2-LUT print-half filename: ``lut_{version}_{film}_{print}_print.cube``.

    The film stock appears in the print-LUT filename because the print
    LUT's input wire is the *film stock's* normalized cmy_film density
    (the ``d_max`` constants are stock-dependent — see the bundle
    invariant in n010 §3 / n030 §3).
    """
    film = _normalize_stock(spec.film_profile)
    print_tag = _normalize_stock(print_stock)
    return f"lut_{version_tag}_{film}_{print_tag}_print{ext}"


def _print_lut_title(spec: BundleSpec, print_stock: str, version_tag: str) -> str:
    """2-LUT print-half title: ``{version}_{film}_{print}_print``."""
    film = _normalize_stock(spec.film_profile)
    print_tag = _normalize_stock(print_stock)
    return f"{version_tag}_{film}_{print_tag}_print"


# ---------------------------------------------------------------------------
# 4-LUT filename helpers.
#
# L1 / L2 are shared across prints (filming stages don't depend on the print
# profile); L3 / L4 are per-print. The film stock appears in every filename
# because the cmy_film and log_e wires are calibrated to that specific film.
# ---------------------------------------------------------------------------

def _l1_lut_filename(spec: BundleSpec, version_tag: str, *, ext: str = ".cube") -> str:
    """L1 filename: ``lut_{version}_{film}_l1.cube``."""
    film = _normalize_stock(spec.film_profile)
    return f"lut_{version_tag}_{film}_l1{ext}"


def _l1_lut_title(spec: BundleSpec, version_tag: str) -> str:
    film = _normalize_stock(spec.film_profile)
    return f"{version_tag}_{film}_l1"


def _l2_lut_filename(spec: BundleSpec, version_tag: str, *, ext: str = ".cube") -> str:
    """L2 filename: ``lut_{version}_{film}_l2.cube``."""
    film = _normalize_stock(spec.film_profile)
    return f"lut_{version_tag}_{film}_l2{ext}"


def _l2_lut_title(spec: BundleSpec, version_tag: str) -> str:
    film = _normalize_stock(spec.film_profile)
    return f"{version_tag}_{film}_l2"


def _l3_lut_filename(spec: BundleSpec, print_stock: str, version_tag: str,
                     *, ext: str = ".cube") -> str:
    """L3 filename: ``lut_{version}_{film}_{print}_l3.cube``."""
    film = _normalize_stock(spec.film_profile)
    print_tag = _normalize_stock(print_stock)
    return f"lut_{version_tag}_{film}_{print_tag}_l3{ext}"


def _l3_lut_title(spec: BundleSpec, print_stock: str, version_tag: str) -> str:
    film = _normalize_stock(spec.film_profile)
    print_tag = _normalize_stock(print_stock)
    return f"{version_tag}_{film}_{print_tag}_l3"


def _l4_lut_filename(spec: BundleSpec, print_stock: str, version_tag: str,
                     *, ext: str = ".cube") -> str:
    """L4 filename: ``lut_{version}_{film}_{print}_l4.cube``."""
    film = _normalize_stock(spec.film_profile)
    print_tag = _normalize_stock(print_stock)
    return f"lut_{version_tag}_{film}_{print_tag}_l4{ext}"


def _l4_lut_title(spec: BundleSpec, print_stock: str, version_tag: str) -> str:
    film = _normalize_stock(spec.film_profile)
    print_tag = _normalize_stock(print_stock)
    return f"{version_tag}_{film}_{print_tag}_l4"


# ---------------------------------------------------------------------------
# Sub-chain combinations (n130).
#
# Each canonical N-LUT topology has an ordered list of pipeline taps; the
# canonical cubes are the adjacent (T_i, T_{i+1}) pairs. Combinations are
# every *other* (T_i, T_j) pair with j > i+1 — the contiguous sub-chains
# that the user opts into via ``BundleSpec.include_combinations``.
#
# A sub-chain is "shared" (print-independent) iff its collect tap is at
# or before ``cmy_film`` — i.e., the entire sub-chain lives in the
# filming half of the pipeline, which has no per-print variation.
# ---------------------------------------------------------------------------


_COMBINATIONS_SUBDIR = "combinations"


@dataclass(frozen=True)
class _SubchainEntry:
    """One combination sub-chain for a topology.

    ``stage_ids`` is the 1-indexed sequence of canonical stages the
    sub-chain spans (e.g., ``(1, 2)`` for L12, ``(2, 3, 4)`` for L234).
    The role string (``subchain_<ids>``) and the filename label
    (``l<ids>``) are derived from it.
    """
    stage_ids: tuple[int, ...]
    inject_tap: str
    collect_tap: str
    is_shared: bool

    @property
    def role(self) -> str:
        return "subchain_" + "".join(str(s) for s in self.stage_ids)

    @property
    def label(self) -> str:
        return "l" + "".join(str(s) for s in self.stage_ids)


_TOPOLOGY_COMBINATIONS: dict[str, tuple[_SubchainEntry, ...]] = {
    "1lut": (),
    "2lut": (
        _SubchainEntry((1, 2), "rgb_in", "rgb_out", is_shared=False),
    ),
    "3lut": (
        _SubchainEntry((1, 2),    "rgb_in",     "cmy_film", is_shared=True),
        _SubchainEntry((2, 3),    "log_e_film", "rgb_out",  is_shared=False),
        _SubchainEntry((1, 2, 3), "rgb_in",     "rgb_out",  is_shared=False),
    ),
    "4lut": (
        _SubchainEntry((1, 2),       "rgb_in",      "cmy_film",    is_shared=True),
        _SubchainEntry((2, 3),       "log_e_film",  "log_e_print", is_shared=False),
        _SubchainEntry((3, 4),       "cmy_film",    "rgb_out",     is_shared=False),
        _SubchainEntry((1, 2, 3),    "rgb_in",      "log_e_print", is_shared=False),
        _SubchainEntry((2, 3, 4),    "log_e_film",  "rgb_out",     is_shared=False),
        _SubchainEntry((1, 2, 3, 4), "rgb_in",      "rgb_out",     is_shared=False),
    ),
}


# Tap name → LutFileMeta.domain string. ``rgb_in`` and ``rgb_out`` get
# the ``input_rgb`` / ``output_rgb`` aliases used throughout the
# existing canonical metadata; the wire-named taps keep their tap name.
_TAP_TO_DOMAIN: dict[str, str] = {
    "rgb_in":      "input_rgb",
    "log_e_film":  "log_e_film",
    "cmy_film":    "cmy_film",
    "log_e_print": "log_e_print",
}

_TAP_TO_RANGE: dict[str, str] = {
    "log_e_film":  "log_e_film",
    "cmy_film":    "cmy_film",
    "log_e_print": "log_e_print",
    "rgb_out":     "output_rgb",
}


# Human-readable labels for the README's combinations table and file-list
# descriptors. Keyed by the LutFileMeta domain / range string (which is
# the post-_TAP_TO_* alias), so consumers reading bundle.json with the
# same vocabulary see consistent names in the README.
_TAP_DOMAIN_LABEL: dict[str, str] = {
    "input_rgb":   "input RGB",
    "log_e_film":  "log_e_film code",
    "cmy_film":    "cmy_film code",
    "log_e_print": "log_e_print code",
}

_TAP_RANGE_LABEL: dict[str, str] = {
    "log_e_film":  "log_e_film code",
    "cmy_film":    "cmy_film code",
    "log_e_print": "log_e_print code",
    "output_rgb":  "output RGB",
}


def _subchain_filename(
    spec: BundleSpec, version_tag: str, label: str,
    print_profile: str | None, *, ext: str = ".cube",
) -> str:
    """Build a combination cube's bundle-relative path.

    Shared cubes (print-independent) omit the print segment; per-print
    cubes include it. The path is rooted at the ``combinations/``
    subfolder so the canonical L1..LN stay visible at the bundle root.
    """
    film = _normalize_stock(spec.film_profile)
    if print_profile is None:
        name = f"lut_{version_tag}_{film}_{label}{ext}"
    else:
        print_tag = _normalize_stock(print_profile)
        name = f"lut_{version_tag}_{film}_{print_tag}_{label}{ext}"
    return f"{_COMBINATIONS_SUBDIR}/{name}"


def _subchain_title(
    spec: BundleSpec, version_tag: str, label: str, print_profile: str | None,
) -> str:
    """Compact title for a combination cube (same shape as canonical titles)."""
    film = _normalize_stock(spec.film_profile)
    if print_profile is None:
        return f"{version_tag}_{film}_{label}"
    print_tag = _normalize_stock(print_profile)
    return f"{version_tag}_{film}_{print_tag}_{label}"


def _lut_license_source_path() -> Path:
    """Return the repository-local LUT license file shipped with the source tree."""
    license_path = Path(__file__).resolve().parents[2] / _LUT_LICENSE_FILENAME
    if not license_path.is_file():
        raise FileNotFoundError(
            f"missing bundled LUT license file at {license_path}"
        )
    return license_path


def _bundle_output_paths(out_path: Path, container: str) -> tuple[Path, Path | None]:
    """Normalize bundle directory/archive destinations for the write path."""
    out_path = Path(out_path)
    if container != "zip":
        return out_path, None
    if out_path.suffix.lower() == ".zip":
        return out_path.with_suffix(""), out_path
    return out_path, out_path.with_suffix(".zip")


def _bundle_readme_text(
    meta: BundleMeta,
    *,
    qa_results: dict[str, list] | None = None,
) -> str:
    """Render a quick-start README for the bundle root.

    ``qa_results`` is the optional ``{print: [Result, ...]}`` mapping
    produced by :meth:`BundleBuilder._run_qa`. When present, a
    "## Quality" pass/fail badge block is rendered near the top of
    the README (n090 §6.1).
    """
    prov = meta.provenance
    input_cs = meta.color_spaces.get("input")
    output_cs = meta.color_spaces.get("output")
    film_label = meta.stocks.film if meta.stocks is not None else "the film"
    if meta.stocks is not None and meta.stocks.prints:
        print_label = (
            meta.stocks.prints[0]
            if len(meta.stocks.prints) == 1
            else f"{len(meta.stocks.prints)} prints"
        )
    else:
        print_label = "a print"
    lines = [
        "# spektrafilm LUT bundle",
        "",
        "This folder contains exported LUT files plus the machine-readable metadata and license for this bundle.",
        "",
        "## What this is",
        "",
        (
            f"A physically based simulation of {film_label} on "
            f"{print_label}, calibrated against published spectral dye "
            "response and characteristic curves. The cube is the "
            "*neutral developed and printed* render — the technical "
            "transform a perfectly exposed negative would walk through "
            "to land on the print."
        ),
        "",
        "## What this is not",
        "",
        (
            "This is **not** a stylistic look-up grade. There is no "
            "creative color decision baked in beyond the film's own "
            "physics — no extra contrast, no shifted hue, no taste "
            "layer. Aesthetic grading happens *before* (input side) or "
            "*after* (output side) this LUT, not inside it."
        ),
        "",
    ]
    if qa_results:
        lines.extend(_quality_readme_section(qa_results))
    lines.extend([
        "## Quick info",
        f"- Name: {meta.name}",
        f"- Topology: {meta.topology}",
        f"- Resolution: {meta.resolution}^3",
        f"- Delivery target: {meta.target or 'generic Adobe .cube'}",
        f"- Created: {prov.created}",
        f"- spektrafilm version: {prov.spektrafilm_version}",
    ])
    if meta.stocks is not None:
        lines.append(f"- Film stock: {meta.stocks.film}")
        if meta.stocks.prints:
            lines.append(f"- Print stocks: {', '.join(meta.stocks.prints)}")
    if input_cs is not None:
        lines.append(
            f"- Input color space: {input_cs.name} (cctf {'on' if input_cs.cctf else 'off'})"
        )
    if meta.input_exposure is not None:
        exp = meta.input_exposure
        lines.append(
            f"- Input exposure: source white at +{exp.stops_above_gray:g} "
            f"stops above 0.18 (linear gain {exp.gain:.4g})"
        )
    if output_cs is not None:
        lines.append(
            f"- Output color space: {output_cs.name} (cctf {'on' if output_cs.cctf else 'off'})"
        )
    lines.extend([
        "",
        "## Files",
        f"- {_BUNDLE_README_FILENAME}: this summary",
        "- bundle.json: full metadata payload",
        f"- {_LUT_LICENSE_FILENAME}: LUT license text",
    ])
    for lut in meta.luts:
        if lut.role == "film":
            descr = "shared film half (L1∘L2: input RGB → normalized cmy_film density)"
        elif lut.role == "print":
            descr = f"print half for {lut.print_profile} (L3∘L4: cmy_film → output RGB)"
        elif lut.role == "combined":
            descr = f"full chain for {lut.print_profile}"
        elif lut.role == "filming_expose":
            descr = "shared L1 — filming.expose (input RGB → normalized log_e_film code)"
        elif lut.role == "filming_develop":
            descr = "shared L2 — filming.develop (log_e_film code → normalized cmy_film code)"
        elif lut.role == "printing_expose":
            descr = f"L3 for {lut.print_profile} — printing.expose (cmy_film code → normalized log_e_print code)"
        elif lut.role == "printing_develop_scan":
            descr = f"L4 for {lut.print_profile} — printing.develop + scanning.scan (log_e_print code → output RGB)"
        elif lut.role == "printing_combined":
            descr = f"L3 for {lut.print_profile} — printing.expose + develop + scan (cmy_film code → output RGB)"
        elif lut.role.startswith("subchain_"):
            ids = lut.role[len("subchain_"):]
            scope = f"for {lut.print_profile}" if lut.print_profile else "shared"
            descr = (
                f"L{ids} sub-chain ({scope}) — pre-collapsed canonical stages {ids} "
                f"({_TAP_DOMAIN_LABEL.get(lut.domain, lut.domain)} → "
                f"{_TAP_RANGE_LABEL.get(lut.range, lut.range)})"
            )
        else:
            descr = lut.role
        lines.append(f"- {lut.path}: {descr}")
    if meta.topology == "2lut":
        lines.extend([
            "",
            "## Apply order",
            "Apply the film LUT first, then the matching print LUT. The two LUTs share the bundle's `cmy_film` wire — film LUT output is normalized density code in `[0, 1]` per channel, and the print LUT expects exactly that. Do not chain a film LUT from one bundle with a print LUT from another; the `d_max` constants differ.",
            "",
            "## Working in the intermediate space",
            "",
            "The `cmy_film` tap between the film and print LUTs exposes normalized film-density code. Decode via `bundle.json/wires/cmy_film` (which carries per-channel `d_min` and `d_max`) to get physical D per channel:",
            "",
            "    D = code * (d_max - d_min) + d_min",
            "",
            "Modify, re-encode to the same `[0, 1]` code range, then feed the print LUT.",
            "",
            "**Base+fog headroom.** The pipeline's `cmy_film` density is reported *above base+fog*, so the deterministic baked value is `>= 0` per channel. `d_min` is set slightly negative (e.g. -0.2) to reserve headroom below the natural floor for downstream grain models — film grain fluctuates around the dye density, including in the fog itself, so noise samples can legitimately dip below zero. Without this headroom those dips would be silently clamped at the wire's [0, 1] boundary.",
            "",
            "Useful effects to inject here:",
            "",
            "- **Grain**: density-modulated noise reproduces real film grain. Magnitude should scale with density (more grain in shadow regions for negative-positive workflows). The `cmy_film` tap is the canonical place — film grain modulates the actual silver / dye granularity, which is what density represents.",
        ])
    elif meta.topology == "3lut":
        lines.extend([
            "",
            "## Apply order",
            "Apply the three LUTs in order: L1 → L2 → L3.",
            "",
            "- L1 and L2 are shared across all prints in the bundle.",
            "- L3 is print-specific; pick the cube matching the print stock you want.",
            "",
            "Wire contracts (each cube carries [0, 1] code values; the wire describes what those codes represent physically):",
            "",
            "- After L1: normalized `log_e_film` code, with shaper (min, max) in `bundle.json/wires/log_e_film`.",
            "- After L2: normalized `cmy_film` density code, with `d_min` / `d_max` in `bundle.json/wires/cmy_film` (decode: `D = code * (d_max - d_min) + d_min`).",
            "- After L3: encoded RGB in the bundle's output color space. The `log_e_print` and `cmy_print` taps are collapsed inside L3 — they are *not* exposed as a working space.",
            "",
            "Do not cross-chain LUTs between bundles — the wire constants are stock-specific and won't line up.",
            "",
            "## Working in the intermediate spaces",
            "",
            "Two intermediate taps are exposed (after L1 and after L2). To intercept, decode via the matching wire, apply the effect in physical units, then re-encode before feeding the next LUT.",
            "",
            "- **After L1 — `log_e_film`** (light hitting the film, log-shaped): decode via `wires/log_e_film` to get log10(E), then exponentiate to recover linear-light exposure. This is the right place for spatial effects that operate on the actual light landing on the film — **halation**, **light scattering** through the emulsion, and **lens diffusion** filters (Pro-Mist, Black Pro-Mist, etc.).",
            "- **After L2 — `cmy_film` density** (developed film density, reported *above base+fog*): decode via `wires/cmy_film` (`D = code * (d_max - d_min) + d_min`) to get physical D per channel. **Grain** belongs here — film grain originates in the silver / dye granularity that density represents, so density-modulated noise at this tap is the canonical film-grain injection point. `d_min` is reserved slightly negative (e.g. -0.2) so noise samples can dip below zero — real fog grain fluctuates around base+fog, including downward — without being clipped at the [0, 1] code boundary.",
            "",
            "Enlarger-stage effects (diffusion filters at the printing light, dodge / burn masks) are **not** available in this topology because the `log_e_print` tap is collapsed inside L3. Use the 4-LUT bundle for that.",
        ])
    elif meta.topology == "4lut":
        lines.extend([
            "",
            "## Apply order",
            "Apply the four LUTs in order: L1 → L2 → L3 → L4.",
            "",
            "- L1 and L2 are shared across all prints in the bundle.",
            "- L3 and L4 are print-specific; pick the pair matching the print stock you want.",
            "",
            "Wire contracts (each cube carries [0, 1] code values; the wire describes what those codes represent physically):",
            "",
            "- After L1: normalized `log_e_film` code, with shaper (min, max) in `bundle.json/wires/log_e_film`.",
            "- After L2: normalized `cmy_film` density code, with `d_min` / `d_max` in `bundle.json/wires/cmy_film` (decode: `D = code * (d_max - d_min) + d_min`).",
            "- After L3: normalized `log_e_print` code, with shaper (min, max) in `bundle.json/wires/log_e_print`.",
            "- After L4: encoded RGB in the bundle's output color space.",
            "",
            "Do not cross-chain LUTs between bundles — the wire constants are stock-specific and won't line up.",
            "",
            "## Working in the intermediate spaces",
            "",
            "Each of the three intermediate taps exposes a normalized `[0, 1]` code. To intercept, decode via the matching wire, apply the effect in physical units, then re-encode before feeding the next LUT.",
            "",
            "- **After L1 — `log_e_film`** (light hitting the film, log-shaped): decode via `wires/log_e_film` to get log10(E), then exponentiate to recover linear-light exposure. This is the right place for spatial effects that operate on the actual light landing on the film — **halation**, **light scattering** through the emulsion, and **lens diffusion** filters (Pro-Mist, Black Pro-Mist, etc.).",
            "- **After L2 — `cmy_film` density** (developed film density, reported *above base+fog*): decode via `wires/cmy_film` (`D = code * (d_max - d_min) + d_min`) to get physical D per channel. **Grain** belongs here — film grain originates in the silver / dye granularity that density represents, so density-modulated noise at this tap is the canonical film-grain injection point. `d_min` is reserved slightly negative (e.g. -0.2) so noise samples can dip below zero — real fog grain fluctuates around base+fog, including downward — without being clipped at the [0, 1] code boundary.",
            "- **After L3 — `log_e_print`** (light hitting the print, log-shaped): decode via `wires/log_e_print` to get log10(E) at the print. Enlarger-stage effects belong here — **enlarger diffusion filters** (soft-focus, baseboard scatter), simulated **dodge / burn masks**, and any other manipulation of the printing light.",
        ])
    # Combinations section (n130). Driven entirely off the bundle's
    # luts metadata: if any subchain_* entries are present, render the
    # section; otherwise skip silently. Keeps the README self-describing.
    subchain_luts = tuple(l for l in meta.luts if l.role.startswith("subchain_"))
    if subchain_luts:
        lines.extend(_combinations_readme_section(subchain_luts))
    if meta.input_exposure is not None:
        exp = meta.input_exposure
        film_mid_gray = 0.18 * exp.gain
        lines.extend([
            "",
            "## Input exposure",
            "",
            (
                f"This bundle was baked with `stops_above_gray = "
                f"{exp.stops_above_gray:g}` — the source's encoded 1.0 "
                f"is placed at +{exp.stops_above_gray:g} stops above "
                f"0.18 linear in the film's frame via a simple linear "
                f"gain of {exp.gain:.4g}. No log shaping: every input "
                f"linear value gets the same multiplier, so middle "
                f"gray drifts with the gain. For a source whose "
                f"native mid-gray is 0.18 linear, the film sees "
                f"mid-gray at {film_mid_gray:.4g} linear — "
                f"{'above' if film_mid_gray > 0.18 else 'below'} the "
                f"photographic 0.18 reference. This is the simple-"
                f"multiplication trade-off (recovering both fixed "
                f"mid-gray and configurable headroom would require "
                f"log shaping, which this design deliberately "
                f"avoids)."
            ),
            "",
            (
                "**Disclosure.** With `stops_above_gray` set, the LUT "
                "is no longer a strict colorimetric "
                f"`{input_cs.name if input_cs else 'input'} → "
                f"{output_cs.name if output_cs else 'output'}` "
                "transform — it bakes in the exposure gain so the "
                "source walks more (or less) of the film's latitude. "
                "See spektrafilm-research n150 for the rationale."
            ),
        ])
    lines.extend([
        "",
        "## Notes",
        f"- {prov.notes}",
        "- See bundle.json for the complete structured metadata.",
    ])
    return "\n".join(lines) + "\n"


def _quality_readme_section(qa_results: dict[str, list]) -> list[str]:
    """Render the README's "## Quality" pass/fail badge block (n090 §6.1).

    Produces one row per QA test, surfacing the test's pass/fail/info
    status and its headline ``short_summary()``. For multi-print
    bundles every print gets its own subsection so the colorist can
    audit each chain independently.
    """
    badges = {"PASS": "✓ PASS", "FAIL": "✗ FAIL", "INFO": "· INFO"}
    lines = ["## Quality", ""]
    multi_print = len(qa_results) > 1
    for print_profile, results in qa_results.items():
        if multi_print:
            lines.extend([f"### {print_profile}", ""])
        n_pass = sum(1 for r in results if r.passed is True)
        n_fail = sum(1 for r in results if r.passed is False)
        n_info = sum(1 for r in results if r.passed is None)
        lines.extend([
            f"{n_pass} pass · {n_fail} fail · {n_info} info "
            f"— full report at `qa/<print-folder>/report.md`.",
            "",
            "| Test | Status | Headline |",
            "|------|--------|----------|",
        ])
        for r in results:
            lines.append(
                f"| `{r.name}` | {badges[r.status()]} | {r.short_summary()} |"
            )
        lines.append("")
    return lines


def _combinations_readme_section(
    subchain_luts: tuple[LutFileMeta, ...],
) -> list[str]:
    """Render the README's "Pre-collapsed sub-chains" section.

    Lists every ``subchain_*`` cube in the bundle with its domain →
    range mapping and print-specificity. Generated from the bundle's
    own metadata so the README never lists a cube that wasn't baked.
    """
    lines = [
        "",
        "## Pre-collapsed sub-chains",
        "",
        "In addition to the canonical LUTs above, this bundle ships every "
        "contiguous sub-chain of the canonical chain in `combinations/`. Each "
        "combination cube collapses two or more canonical stages into a "
        "single transform, for grading apps that only have one LUT slot "
        "(Resolve LUT slot, Lumix Lab, OBS, FFmpeg, Premiere).",
        "",
        "| Cube | Maps | Print-specific |",
        "|------|------|----------------|",
    ]
    for lut in subchain_luts:
        ids = lut.role[len("subchain_"):]
        label = f"l{ids}"
        domain_label = _TAP_DOMAIN_LABEL.get(lut.domain, lut.domain)
        range_label = _TAP_RANGE_LABEL.get(lut.range, lut.range)
        print_specific = "yes" if lut.print_profile else "no"
        lines.append(f"| {label} | {domain_label} → {range_label} | {print_specific} |")
    lines.extend([
        "",
        "The canonical L1..LN cubes in the bundle root remain the recommended "
        "chain — they expose every intermediate tap for grain, halation, "
        "diffusion, and enlarger-stage manipulation. Use the combinations "
        "when you want a single-cube application of a particular sub-chain. "
        "Wire contracts and decode formulas for each tap are the same as in "
        "the apply-order section above, and recorded in `bundle.json/wires`.",
    ])
    return lines


class BundleBuilder:
    """Build a LUT bundle by driving the spektrafilm pipeline.

    Supports ``topology="1lut"`` (combined), ``"2lut"`` (film+print
    chain) and ``"4lut"`` (full L1/L2/L3/L4 chain).
    """

    def __init__(self, spec: BundleSpec):
        self.spec = spec

    def build(self) -> Bundle:
        spec = self.spec
        # Validate color spaces up-front for either topology.
        in_entry = get_color_space(spec.input_color_space)
        out_entry = get_color_space(spec.output_color_space)
        if "input" not in in_entry.role:
            raise ValueError(
                f"{spec.input_color_space!r} is not registered as an input color space"
            )
        if "output" not in out_entry.role:
            raise ValueError(
                f"{spec.output_color_space!r} is not registered as an output color space"
            )

        n_prints = len(spec.print_profiles)
        print_word = "print" if n_prints == 1 else "prints"
        print(
            f"[bake] {spec.name} "
            f"({spec.topology}, {spec.resolution}^3, {n_prints} {print_word})"
        )
        if spec.include_combinations and spec.topology == "1lut":
            print(
                "[bake] include_combinations=True is a no-op for 1lut topology "
                "(the single canonical cube already collapses all stages)"
            )

        if spec.topology == "1lut":
            return self._build_1lut_combined(in_entry, out_entry)
        if spec.topology == "2lut":
            return self._build_2lut_film_print(in_entry, out_entry)
        if spec.topology == "3lut":
            return self._build_3lut_film_develop_print_combined(in_entry, out_entry)
        if spec.topology == "4lut":
            return self._build_4lut_film_develop_print_develop(in_entry, out_entry)
        raise NotImplementedError(
            f"BundleBuilder does not yet support topology={spec.topology!r}; "
            f"supported: '1lut', '2lut', '3lut', '4lut'"
        )

    # ---- 1-LUT (M4) ------------------------------------------------------

    def _build_1lut_combined(self, in_entry, out_entry) -> Bundle:
        """Bake one combined L1∘L2∘L3∘L4 LUT per print stock.

        Each (film, print) pair produces an independent cube; nothing is
        shared across prints. This is the simplest deployable form —
        users apply one cube and get the full simulation.
        """
        spec = self.spec
        n = spec.resolution
        provenance = ProvenanceMeta()
        version_tag = _normalize_version(provenance.spektrafilm_version)
        wires = BoundaryWires()  # 1-LUT measures no intermediate wires

        bundle_luts: list[tuple[str, Lut]] = []
        lut_metas: list[LutFileMeta] = []
        for print_stock in spec.print_profiles:
            pipeline = self._make_pipeline(spec, in_entry, out_entry, print_stock)
            rel_path = _canonical_lut_filename(spec, print_stock, version_tag)
            title = _canonical_lut_title(spec, print_stock, version_tag)
            bundle_luts.append(self._bake_sublut(
                pipeline, spec, "rgb_in", "rgb_out", wires, rel_path, title,
            ))
            lut_metas.append(LutFileMeta(
                role="combined",
                path=rel_path,
                domain="input_rgb",
                range="output_rgb",
                print_profile=print_stock,
            ))

        meta = BundleMeta(
            schema_version=SCHEMA_VERSION,
            name=spec.name,
            topology="1lut",
            resolution=n,
            target=spec.target,
            provenance=provenance,
            stocks=StocksMeta(film=spec.film_profile, prints=tuple(spec.print_profiles)),
            color_spaces={
                "input": ColorSpaceMeta(
                    name=spec.input_color_space,
                    cctf=(in_entry.cctf is not None),
                ),
                "output": ColorSpaceMeta(
                    name=spec.output_color_space,
                    cctf=(out_entry.cctf is not None),
                ),
            },
            luts=tuple(lut_metas),
            input_exposure=_input_exposure_meta(spec),
        )
        return Bundle(luts=bundle_luts, meta=meta)

    # ---- 2-LUT (M5) ------------------------------------------------------

    def _build_2lut_film_print(self, in_entry, out_entry) -> Bundle:
        """Bake one film LUT (L1∘L2) + per-print print LUTs (L3∘L4).

        The film LUT depends only on the film stock and input space;
        it is baked once and shared across every print in the
        bundle. Each print gets its own print LUT that takes
        normalized cmy_film density (the ``d_max``-scaled output of
        the film LUT) and produces encoded output RGB.

        ``d_max`` is measured by sampling the film half at a 9^3 grid
        through the actual pipeline (with one representative print
        attached, since the cmy_film tap is print-independent) and
        taking the per-channel maximum × :data:`_DENSITY_MARGIN`. This
        is robust to film-stock differences and to whatever the
        spektrafilm chemistry model is doing under the hood.
        """
        spec = self.spec
        n = spec.resolution
        provenance = ProvenanceMeta()
        version_tag = _normalize_version(provenance.spektrafilm_version)

        # Build one pipeline against the first print to (a) measure
        # d_max and (b) bake the shared film LUT. The cmy_film tap is
        # only a function of film + input, so the choice of print here
        # is immaterial.
        first_print = spec.print_profiles[0]
        pipeline = self._make_pipeline(spec, in_entry, out_entry, first_print)
        density_wire = self._compute_density_wire(pipeline, spec)
        wires = BoundaryWires(cmy_film=density_wire)
        film_lut = self._bake_film_lut(pipeline, spec, wires, version_tag)

        bundle_luts: list[tuple[str, Lut]] = [film_lut]
        lut_metas: list[LutFileMeta] = [LutFileMeta(
            role="film",
            path=film_lut[0],
            domain="input_rgb",
            range="cmy_film",
            print_profile=None,
        )]

        # Bake one print LUT per print. Per-print combinations (l12 for 2-LUT,
        # which spans rgb_in → rgb_out and therefore depends on the print
        # stock) live alongside the per-print print LUT.
        for print_profile in spec.print_profiles:
            pipeline = self._make_pipeline(spec, in_entry, out_entry, print_profile)
            print_lut = self._bake_print_lut(pipeline, spec, wires, print_profile, version_tag)
            bundle_luts.append(print_lut)
            lut_metas.append(LutFileMeta(
                role="print",
                path=print_lut[0],
                domain="cmy_film",
                range="output_rgb",
                print_profile=print_profile,
            ))
            for (path_lut, combo_meta) in self._bake_combinations(
                pipeline, spec, wires, version_tag, print_profile=print_profile,
            ):
                bundle_luts.append(path_lut)
                lut_metas.append(combo_meta)

        meta = BundleMeta(
            schema_version=SCHEMA_VERSION,
            name=spec.name,
            topology="2lut",
            resolution=n,
            target=spec.target,
            provenance=provenance,
            stocks=StocksMeta(film=spec.film_profile, prints=tuple(spec.print_profiles)),
            color_spaces={
                "input": ColorSpaceMeta(
                    name=spec.input_color_space,
                    cctf=(in_entry.cctf is not None),
                ),
                "output": ColorSpaceMeta(
                    name=spec.output_color_space,
                    cctf=(out_entry.cctf is not None),
                ),
            },
            wires=WiresMeta(cmy_film=density_wire),
            luts=tuple(lut_metas),
            input_exposure=_input_exposure_meta(spec),
        )
        return Bundle(luts=bundle_luts, meta=meta)

    # ---- 3-LUT ------------------------------------------------------

    def _build_3lut_film_develop_print_combined(self, in_entry, out_entry) -> Bundle:
        """Bake the three-stage LUT chain: L1 + L2 + collapsed back-half.

        Stage mapping:

        - **L1** ``rgb_in → log_e_film`` — ``filming.expose`` (shared)
        - **L2** ``log_e_film → cmy_film`` — ``filming.develop`` (shared)
        - **L3** ``cmy_film → rgb_out`` — collapses ``printing.expose +
          printing.develop + scanning.scan`` into one cube (per print)

        The trade vs 4-LUT: the ``log_e_print`` tap is *not* exposed,
        so enlarger-stage effects (diffusion filters, dodge / burn,
        baseboard scatter) cannot be injected. In exchange the bundle
        ships one fewer cube per print, and the back-half stays
        monolithic — fewer interpolation stages, lower compound error.
        Use 3-LUT when only grain (cmy_film tap) and pre-film spatial
        effects (log_e_film tap) matter; use 4-LUT when enlarger
        manipulation is in scope.

        Total cubes for an N-print bundle: ``2 + N``.

        Wires recorded in ``bundle.json``:

        - ``log_e_film``: linear-in-log10 shaper for L1's output / L2's input.
        - ``cmy_film``: per-channel density normalization for L2's output / L3's input.
        - ``log_e_print`` and ``cmy_print`` stay None (collapsed inside L3).
        """
        spec = self.spec
        provenance = ProvenanceMeta()
        version_tag = _normalize_version(provenance.spektrafilm_version)

        # Shared pipeline: filming.* stages are print-independent, so the
        # choice of print for the shared pass is just a convenient anchor.
        first_print = spec.print_profiles[0]
        pipeline_shared = self._make_pipeline(spec, in_entry, out_entry, first_print)

        # Probe wires from the same 9³ pass (cheap; pipeline runs sub-second).
        log_e_film_wire = self._compute_log_e_wire(pipeline_shared, spec, tap="log_e_film")
        density_wire = self._compute_density_wire(pipeline_shared, spec)
        wires = BoundaryWires(log_e_film=log_e_film_wire, cmy_film=density_wire)

        # Bake L1 + L2 once.
        l1 = self._bake_l1(pipeline_shared, spec, wires, version_tag)
        l2 = self._bake_l2(pipeline_shared, spec, wires, version_tag)
        bundle_luts: list[tuple[str, Lut]] = [l1, l2]
        lut_metas: list[LutFileMeta] = [
            LutFileMeta(role="filming_expose",
                        path=l1[0], domain="input_rgb", range="log_e_film", print_profile=None),
            LutFileMeta(role="filming_develop",
                        path=l2[0], domain="log_e_film", range="cmy_film", print_profile=None),
        ]

        # Shared combinations (print-independent sub-chains — only l12 for
        # 3-LUT) ride the same shared pipeline pass as L1/L2.
        for (path_lut, combo_meta) in self._bake_combinations(
            pipeline_shared, spec, wires, version_tag, print_profile=None,
        ):
            bundle_luts.append(path_lut)
            lut_metas.append(combo_meta)

        # Bake the combined back-half once per print. Math is identical to
        # the 2-LUT print LUT (cmy_film code → rgb_out); only the filename
        # role differs to stay consistent with the numbered-cube convention
        # we use for topologies with ≥3 cubes.
        for print_profile in spec.print_profiles:
            pipeline_print = self._make_pipeline(spec, in_entry, out_entry, print_profile)
            l3 = self._bake_l3_combined(pipeline_print, spec, wires,
                                        print_profile, version_tag)
            bundle_luts.append(l3)
            lut_metas.append(LutFileMeta(
                role="printing_combined",
                path=l3[0],
                domain="cmy_film",
                range="output_rgb",
                print_profile=print_profile,
            ))
            for (path_lut, combo_meta) in self._bake_combinations(
                pipeline_print, spec, wires, version_tag, print_profile=print_profile,
            ):
                bundle_luts.append(path_lut)
                lut_metas.append(combo_meta)

        meta = BundleMeta(
            schema_version=SCHEMA_VERSION,
            name=spec.name,
            topology="3lut",
            resolution=spec.resolution,
            target=spec.target,
            provenance=provenance,
            stocks=StocksMeta(film=spec.film_profile, prints=tuple(spec.print_profiles)),
            color_spaces={
                "input": ColorSpaceMeta(
                    name=spec.input_color_space,
                    cctf=(in_entry.cctf is not None),
                ),
                "output": ColorSpaceMeta(
                    name=spec.output_color_space,
                    cctf=(out_entry.cctf is not None),
                ),
            },
            wires=WiresMeta(
                log_e_film=log_e_film_wire,
                cmy_film=density_wire,
                log_e_print=None,  # collapsed inside L3
                cmy_print=None,    # collapsed inside L3
            ),
            luts=tuple(lut_metas),
            input_exposure=_input_exposure_meta(spec),
        )
        return Bundle(luts=bundle_luts, meta=meta)

    def _bake_l3_combined(self, pipeline, spec, wires: BoundaryWires,
                          print_stock: str, version_tag: str) -> tuple[str, Lut]:
        """3-LUT L3: cmy_film code → encoded output RGB.

        Same math as :meth:`_bake_print_lut` (2-LUT); filename uses the
        numbered-cube convention ``lut_<v>_<film>_<print>_l3.cube`` to
        stay consistent with the 4-LUT naming.
        """
        return self._bake_sublut(
            pipeline, spec, "cmy_film", "rgb_out", wires,
            _l3_lut_filename(spec, print_stock, version_tag),
            _l3_lut_title(spec, print_stock, version_tag),
        )

    # ---- 4-LUT (M6) ------------------------------------------------------

    def _build_4lut_film_develop_print_develop(self, in_entry, out_entry) -> Bundle:
        """Bake the four-stage LUT chain.

        Stage mapping (n010 §2):

        - **L1** ``rgb_in → log_e_film`` — ``filming.expose``
        - **L2** ``log_e_film → cmy_film`` — ``filming.develop``
        - **L3** ``cmy_film → log_e_print`` — ``printing.expose``
        - **L4** ``log_e_print → rgb_out`` — ``printing.develop`` +
          ``scanning.scan``

        L1 and L2 don't depend on the print (the filming stages
        only see the film stock + input color space), so they're baked
        **once and shared** across every print in the bundle. L3 and
        L4 are print-specific.

        Total cubes for an N-print bundle: ``2 + 2N``.

        Wires recorded in ``bundle.json``:

        - ``log_e_film``: linear-in-log10 shaper for L1's output / L2's
          input. Measured on a 9³ probe pass through the shared
          pipeline.
        - ``cmy_film``: per-channel density normalization for L2's
          output / L3's input. Same as 2-LUT.
        - ``log_e_print``: linear-in-log10 shaper for L3's output / L4's
          input. Measured on the same 9³ probe pass.

        Note: the ``log_e_print`` wire is measured against the *first*
        print's pipeline and reused across all prints. For typical
        spektrafilm chemistry, print-to-print variation in the
        log_e_print range is small relative to the wire's margin
        (``_LOG_E_MARGIN`` = 0.1 log E); if a future stock falls
        outside, raise the margin or switch to per-print wires.
        """
        spec = self.spec
        provenance = ProvenanceMeta()
        version_tag = _normalize_version(provenance.spektrafilm_version)

        # Shared pipeline: print-independent stages (filming.*) produce
        # identical output regardless of which print we attach here, so
        # we use the first print as a convenient anchor.
        first_print = spec.print_profiles[0]
        pipeline_shared = self._make_pipeline(spec, in_entry, out_entry, first_print)

        # Probe wires from a single 9³ pass.
        log_e_film_wire = self._compute_log_e_wire(pipeline_shared, spec, tap="log_e_film")
        density_wire = self._compute_density_wire(pipeline_shared, spec)
        log_e_print_wire = self._compute_log_e_wire(pipeline_shared, spec, tap="log_e_print")
        wires = BoundaryWires(
            log_e_film=log_e_film_wire,
            cmy_film=density_wire,
            log_e_print=log_e_print_wire,
        )

        # Bake L1 + L2 once.
        l1 = self._bake_l1(pipeline_shared, spec, wires, version_tag)
        l2 = self._bake_l2(pipeline_shared, spec, wires, version_tag)
        bundle_luts: list[tuple[str, Lut]] = [l1, l2]
        lut_metas: list[LutFileMeta] = [
            LutFileMeta(role="filming_expose",
                        path=l1[0], domain="input_rgb", range="log_e_film", print_profile=None),
            LutFileMeta(role="filming_develop",
                        path=l2[0], domain="log_e_film", range="cmy_film", print_profile=None),
        ]

        # Shared combinations (print-independent sub-chains — l12 for
        # 4-LUT) ride the same shared pipeline pass as L1/L2.
        for (path_lut, combo_meta) in self._bake_combinations(
            pipeline_shared, spec, wires, version_tag, print_profile=None,
        ):
            bundle_luts.append(path_lut)
            lut_metas.append(combo_meta)

        # Bake L3 + L4 per print, then the per-print combinations against
        # the same per-print pipeline (l23, l34, l123, l234, l1234).
        for print_profile in spec.print_profiles:
            pipeline_print = self._make_pipeline(spec, in_entry, out_entry, print_profile)
            l3 = self._bake_l3(pipeline_print, spec, wires, print_profile, version_tag)
            l4 = self._bake_l4(pipeline_print, spec, wires, print_profile, version_tag)
            bundle_luts.extend([l3, l4])
            lut_metas.extend([
                LutFileMeta(role="printing_expose",
                            path=l3[0], domain="cmy_film", range="log_e_print",
                            print_profile=print_profile),
                LutFileMeta(role="printing_develop_scan",
                            path=l4[0], domain="log_e_print", range="output_rgb",
                            print_profile=print_profile),
            ])
            for (path_lut, combo_meta) in self._bake_combinations(
                pipeline_print, spec, wires, version_tag, print_profile=print_profile,
            ):
                bundle_luts.append(path_lut)
                lut_metas.append(combo_meta)

        meta = BundleMeta(
            schema_version=SCHEMA_VERSION,
            name=spec.name,
            topology="4lut",
            resolution=spec.resolution,
            target=spec.target,
            provenance=provenance,
            stocks=StocksMeta(film=spec.film_profile, prints=tuple(spec.print_profiles)),
            color_spaces={
                "input": ColorSpaceMeta(
                    name=spec.input_color_space,
                    cctf=(in_entry.cctf is not None),
                ),
                "output": ColorSpaceMeta(
                    name=spec.output_color_space,
                    cctf=(out_entry.cctf is not None),
                ),
            },
            wires=WiresMeta(
                log_e_film=log_e_film_wire,
                cmy_film=density_wire,
                log_e_print=log_e_print_wire,
                cmy_print=None,  # L4 collapses cmy_print; not a wire in 4-LUT
            ),
            luts=tuple(lut_metas),
            input_exposure=_input_exposure_meta(spec),
        )
        return Bundle(luts=bundle_luts, meta=meta)

    # ---- shared helpers --------------------------------------------------

    def _make_pipeline(self, spec, in_entry, out_entry, print_stock):
        """Construct a ``SimulationPipeline`` configured for LUT baking.

        ``lut_mode`` switches the pipeline into deterministic
        per-pixel mode (all spatial / stochastic effects off);
        ``input_cctf_decoding`` and ``output_cctf_encoding`` stay
        False because the LUT creator owns the transport encoding.
        """
        # Deferred runtime imports per the README boundary contract.
        from spektrafilm.runtime.params_builder import digest_params, init_params
        from spektrafilm.runtime.pipeline import SimulationPipeline

        params = init_params(film_profile=spec.film_profile, print_profile=print_stock)
        params.debug.lut_mode = True
        params.io.input_primaries = in_entry.primaries
        params.io.output_primaries = out_entry.primaries
        params.io.input_cctf_decoding = False
        params.io.output_cctf_encoding = False
        params.io.gamut_clip = spec.gamut_clip
        params.io.input_gamut_compress = spec.input_gamut_compress
        params.io.output_gamut_compress = spec.output_gamut_compress
        params = digest_params(params)
        return SimulationPipeline(params)

    def _compute_density_wire(self, pipeline, spec) -> DensityWire:
        """Measure per-channel max cmy_film density via a small input pass.

        Samples a ``_DENSITY_PROBE_RESOLUTION**3`` cube of encoded
        input, decodes the CCTF, runs the pipeline with
        ``collect="cmy_film"``, takes the per-channel max and
        multiplies by :data:`_DENSITY_MARGIN`. The result is the
        ``DensityWire.d_max`` for the bundle.
        """
        n_probe = _DENSITY_PROBE_RESOLUTION
        probe_grid = cube_grid(n_probe)
        probe_image_enc = grid_as_image(probe_grid, n_probe)
        probe_image_lin = decode_cctf(probe_image_enc, spec.input_color_space)
        # n150: apply the input exposure gain so the wire measurement
        # reflects the LUT's actual exposure (otherwise d_max would be
        # measured at the input's native range and the wire would be
        # too narrow for the post-gain probe values).
        gain = input_exposure_gain(spec.input_color_space, spec.stops_above_gray)
        probe_image_lin = (probe_image_lin * gain).astype(np.float32)
        # Collect the cmy_film tap directly.
        cmy_film = np.asarray(
            pipeline.process(probe_image_lin, collect="cmy_film"),
            dtype=float,
        ).reshape(-1, 3)
        # cmy_film density is non-negative; max over samples per channel.
        d_max_observed = np.max(cmy_film, axis=0)
        # Round outward (ceil) so the wire's d_max strictly contains the
        # observed range after the 4-decimal clamp.
        d_max = tuple(
            _round_wire_ceil(float(d)) for d in (d_max_observed * _DENSITY_MARGIN)
        )
        # d_min reserves below-fog headroom for downstream grain injection;
        # see _CMY_FILM_FOG_HEADROOM. Already on the 1e-4 grid.
        d_min = (-_CMY_FILM_FOG_HEADROOM,) * 3
        return DensityWire(d_max=d_max, d_min=d_min)

    def _compute_log_e_wire(self, pipeline, spec, tap: str) -> LogEWire:
        """Measure log10(E) span at a named tap via a probe cube pass.

        ``tap`` is either ``"log_e_film"`` or ``"log_e_print"``. We
        run a small input cube through the pipeline, collect the
        tap's output, and take the scalar min/max across all three
        channels + padding (``_LOG_E_MARGIN``).

        The LogE wire is intentionally scalar (one (min, max) for all
        three channels) rather than per-channel — this matches the
        :class:`LogEWire` contract and keeps the shaper math simple.
        The cost is that anisotropic spans waste a little of the
        cube's [0, 1] range on the under-used channel.
        """
        if tap not in ("log_e_film", "log_e_print"):
            raise ValueError(
                f"_compute_log_e_wire expects 'log_e_film' or 'log_e_print', got {tap!r}"
            )
        n_probe = _DENSITY_PROBE_RESOLUTION
        probe_grid = cube_grid(n_probe)
        probe_image_enc = grid_as_image(probe_grid, n_probe)
        probe_image_lin = decode_cctf(
            probe_image_enc, spec.input_color_space,
        )
        # n150: same input-exposure plumb as _compute_density_wire —
        # the log_e span here must reflect the post-gain probe values
        # or the wire collapses to the input's native range.
        gain = input_exposure_gain(spec.input_color_space, spec.stops_above_gray)
        probe_image_lin = (probe_image_lin * gain).astype(np.float32)
        log_e = np.asarray(
            pipeline.process(probe_image_lin, collect=tap),
            dtype=float,
        ).reshape(-1, 3)
        lo = float(log_e.min()) - _LOG_E_MARGIN
        hi = float(log_e.max()) + _LOG_E_MARGIN
        # Round outward so the clamped wire strictly contains the observed
        # log_e range: floor the min (toward -∞), ceil the max (toward +∞).
        return LogEWire(min=_round_wire_floor(lo), max=_round_wire_ceil(hi))

    # ---- generic sub-chain bake (n130) ----------------------------------
    #
    # Every canonical bake (L1..L4 for 4-LUT, film/print for 2-LUT, the
    # single combined cube for 1-LUT) is one entry through this machinery.
    # Sub-chain combinations (n130 — l12, l23, ...) will reuse it without
    # adding new code paths.

    def _make_inject_image(self, n: int, inject_tap: str,
                           wires: BoundaryWires, spec: BundleSpec) -> np.ndarray:
        """Build the pipeline-input image for a sub-chain starting at
        ``inject_tap``.

        The returned ``(n, n, n, 3)`` float32 array carries *physical*
        values at the inject tap — decoded from a uniform [0, 1] code
        cube via the boundary wire for that tap. The pipeline runs
        directly on this array via
        ``pipeline.process(image, inject=inject_tap, collect=...)``.
        """
        code_grid = cube_grid(n)
        if inject_tap == "rgb_in":
            image_enc = grid_as_image(code_grid, n)
            image_lin = decode_cctf(image_enc, spec.input_color_space)
            # n150: simple linear gain that places source white at
            # 0.18 * 2**spec.stops_above_gray in the film's frame
            # (gain = 1.0 when stops_above_gray is None — native).
            gain = input_exposure_gain(
                spec.input_color_space, spec.stops_above_gray,
            )
            image_lin = image_lin * gain
            return image_lin.astype(np.float32)
        if inject_tap == "log_e_film":
            log_e_grid = code_to_log_e(code_grid, wires.log_e_film)
            return grid_as_image(log_e_grid, n).astype(np.float32)
        if inject_tap == "cmy_film":
            density_grid = code_to_density(code_grid, wires.cmy_film)
            return grid_as_image(density_grid, n).astype(np.float32)
        if inject_tap == "log_e_print":
            log_e_grid = code_to_log_e(code_grid, wires.log_e_print)
            return grid_as_image(log_e_grid, n).astype(np.float32)
        raise ValueError(f"cannot build inject image at tap {inject_tap!r}")

    def _encode_at_tap(self, value, collect_tap: str,
                       wires: BoundaryWires, spec: BundleSpec) -> np.ndarray:
        """Encode a pipeline-output value at ``collect_tap`` into [0, 1]
        code space, using the boundary wire at that tap."""
        arr = np.asarray(value, dtype=float)
        if collect_tap == "log_e_film":
            return log_e_to_code(arr, wires.log_e_film)
        if collect_tap == "cmy_film":
            return density_to_code(arr, wires.cmy_film)
        if collect_tap == "log_e_print":
            return log_e_to_code(arr, wires.log_e_print)
        if collect_tap == "rgb_out":
            return encode_cctf(arr, spec.output_color_space)
        raise ValueError(f"cannot encode at tap {collect_tap!r}")

    def _bake_sublut(self, pipeline, spec: BundleSpec,
                     inject_tap: str, collect_tap: str,
                     wires: BoundaryWires,
                     rel_path: str, title: str) -> tuple[str, Lut]:
        """Bake one sub-chain LUT from ``inject_tap`` to ``collect_tap``.

        Pattern: build a code-space grid at the inject tap, decode it via
        ``wires`` into physical values, run the pipeline through the
        sub-chain, encode the output at the collect tap into [0, 1] code
        via the corresponding wire, pack into a :class:`Lut`.

        The final ``np.clip`` is idempotent on outputs that the encoder
        already clamps (``density_to_code``) and supplies the [0, 1]
        clamp for the rest. One code path covers every sub-chain.
        """
        n = spec.resolution
        image = self._make_inject_image(n, inject_tap, wires, spec)
        raw_out = pipeline.process(image, inject=inject_tap, collect=collect_tap)
        code = self._encode_at_tap(raw_out, collect_tap, wires, spec)
        table = np.clip(code, 0.0, 1.0).reshape(n, n, n, 3)
        return rel_path, Lut(table=table, title=title)

    # ---- canonical-bake wrappers ----------------------------------------
    #
    # Each wrapper names a canonical cube (L1..L4, film, print) and routes
    # to ``_bake_sublut`` with the matching (inject, collect) pair and
    # the right naming helpers. Keeping them as named methods preserves
    # readable call sites in the topology-specific builders.

    def _bake_film_lut(self, pipeline, spec, wires: BoundaryWires,
                       version_tag: str) -> tuple[str, Lut]:
        """2-LUT L1∘L2: encoded input RGB → normalized cmy_film code."""
        return self._bake_sublut(
            pipeline, spec, "rgb_in", "cmy_film", wires,
            _film_lut_filename(spec, version_tag),
            _film_lut_title(spec, version_tag),
        )

    def _bake_print_lut(self, pipeline, spec, wires: BoundaryWires,
                        print_stock: str, version_tag: str) -> tuple[str, Lut]:
        """2-LUT L3∘L4: normalized cmy_film code → encoded output RGB."""
        return self._bake_sublut(
            pipeline, spec, "cmy_film", "rgb_out", wires,
            _print_lut_filename(spec, print_stock, version_tag),
            _print_lut_title(spec, print_stock, version_tag),
        )

    def _bake_l1(self, pipeline, spec, wires: BoundaryWires,
                 version_tag: str) -> tuple[str, Lut]:
        """L1: encoded input RGB → normalized log_e_film code."""
        return self._bake_sublut(
            pipeline, spec, "rgb_in", "log_e_film", wires,
            _l1_lut_filename(spec, version_tag),
            _l1_lut_title(spec, version_tag),
        )

    def _bake_l2(self, pipeline, spec, wires: BoundaryWires,
                 version_tag: str) -> tuple[str, Lut]:
        """L2: normalized log_e_film code → normalized cmy_film code."""
        return self._bake_sublut(
            pipeline, spec, "log_e_film", "cmy_film", wires,
            _l2_lut_filename(spec, version_tag),
            _l2_lut_title(spec, version_tag),
        )

    def _bake_l3(self, pipeline, spec, wires: BoundaryWires,
                 print_stock: str, version_tag: str) -> tuple[str, Lut]:
        """L3: normalized cmy_film code → normalized log_e_print code."""
        return self._bake_sublut(
            pipeline, spec, "cmy_film", "log_e_print", wires,
            _l3_lut_filename(spec, print_stock, version_tag),
            _l3_lut_title(spec, print_stock, version_tag),
        )

    def _bake_l4(self, pipeline, spec, wires: BoundaryWires,
                 print_stock: str, version_tag: str) -> tuple[str, Lut]:
        """L4: normalized log_e_print code → encoded output RGB.

        Covers both ``printing.develop`` (log_e_print → cmy_print) and
        ``scanning.scan`` (cmy_print → rgb_out). cmy_print is not
        exposed as a wire — that would push us to 6-LUT and isn't worth
        the extra cube per print for v1.
        """
        return self._bake_sublut(
            pipeline, spec, "log_e_print", "rgb_out", wires,
            _l4_lut_filename(spec, print_stock, version_tag),
            _l4_lut_title(spec, print_stock, version_tag),
        )

    # ---- combinations (n130) --------------------------------------------

    def _bake_combinations(
        self, pipeline, spec: BundleSpec, wires: BoundaryWires,
        version_tag: str, *, print_profile: str | None,
    ) -> list[tuple[tuple[str, Lut], LutFileMeta]]:
        """Bake the topology's combination sub-chains for one pipeline pass.

        ``print_profile=None`` selects the *shared* (print-independent) sub-chains
        and expects ``pipeline`` to be the shared-pipeline pass.
        ``print_profile="..."`` selects the *per-print* sub-chains and expects a
        per-print pipeline. The split keeps the call sites symmetric with
        the canonical-bake loop in each ``_build_Nlut_*`` method.

        Returns one ``((rel_path, Lut), LutFileMeta)`` tuple per baked
        cube. Empty when :attr:`BundleSpec.include_combinations` is
        False, when the topology has no combinations (1-LUT), or when
        no entry in the table matches the requested print/shared role.
        """
        if not spec.include_combinations:
            return []
        entries = _TOPOLOGY_COMBINATIONS.get(spec.topology, ())
        matching = [e for e in entries if e.is_shared == (print_profile is None)]
        if not matching:
            return []
        baked: list[tuple[tuple[str, Lut], LutFileMeta]] = []
        for entry in matching:
            rel_path = _subchain_filename(spec, version_tag, entry.label, print_profile)
            title = _subchain_title(spec, version_tag, entry.label, print_profile)
            path, lut = self._bake_sublut(
                pipeline, spec, entry.inject_tap, entry.collect_tap,
                wires, rel_path, title,
            )
            meta = LutFileMeta(
                role=entry.role,
                path=path,
                domain=_TAP_TO_DOMAIN[entry.inject_tap],
                range=_TAP_TO_RANGE[entry.collect_tap],
                print_profile=print_profile,
            )
            baked.append(((path, lut), meta))
        return baked

    def _maybe_emit_ocio(self, bundle: Bundle, bundle_root: Path) -> bool:
        """Write ``config.ocio`` to the bundle root if the spec opts in
        and the (topology, color-space) combination is supported.

        Returns True iff a config was written. Unsupported combinations
        log a concise notice and return False rather than raising — the
        user explicitly opted in to OCIO via ``spec.ocio_config=True``
        and probably wants to know why no file appeared.

        See studies/a40_lut_system/n120_ocio_config_emission.md.
        """
        if not self.spec.ocio_config:
            return False
        # Lazy import: keeps ocio_emit isolated from the cold-load path
        # of the builders module (mirrors the pattern used for qa.run
        # and delivery_targets).
        from spektrafilm_lut_creator import ocio_emit
        reason = ocio_emit.unsupported_reason(self.spec)
        if reason:
            print(f"[bake] skipping config.ocio: {reason}")
            return False
        yaml_text = ocio_emit.emit_ocio_config(bundle, self.spec)
        (bundle_root / "config.ocio").write_text(yaml_text, encoding="utf-8")
        return True

    def _run_qa(
        self, bundle: Bundle, bundle_root: Path,
    ) -> dict[str, list]:
        """Run the QA suite for the spec's selected print(s).

        Reports land at ``<bundle_root>/qa/<per-print-bundle-name>/``;
        when ``spec.qa_print_index`` is None, every print in the bundle
        gets its own report folder. After each print's run the
        ``cache/`` subdirectory is removed — the reference samples are
        cheap to recompute when needed and don't belong in a shipped
        bundle.

        Returns a ``{print: [Result, ...]}`` mapping so callers can
        surface the QA outcomes elsewhere (e.g. the bundle README's
        "## Quality" pass/fail block, n090 §6.1).
        """
        # Lazy import: qa.suite imports bundles/builders symbols transitively,
        # so eager-importing here would risk a cycle on cold module load.
        from spektrafilm_lut_creator.qa import run as run_qa
        from spektrafilm_lut_creator.naming import per_print_qa_folder_name

        spec = self.spec
        if spec.qa_print_index is None:
            print_indices: tuple[int, ...] = tuple(range(len(spec.print_profiles)))
        else:
            print_indices = (spec.qa_print_index,)

        qa_root = bundle_root / "qa"
        qa_root.mkdir(parents=True, exist_ok=True)

        results_by_print: dict[str, list] = {}
        for idx in print_indices:
            print_profile = spec.print_profiles[idx]
            report_name = per_print_qa_folder_name(
                film_profile=spec.film_profile,
                print_profile=print_profile,
            )
            report_dir = qa_root / report_name
            results_by_print[print_profile] = run_qa(spec, bundle, report_dir, print_index=idx)
            # The QA reference cache is regenerable scratch work — strip
            # it before the bundle is potentially zipped or shipped.
            cache_dir = report_dir / "cache"
            if cache_dir.exists():
                shutil.rmtree(cache_dir)
        return results_by_print

    def write(self, bundle: Bundle, out_dir: Path | None = None) -> Path:
        """Write a built bundle to ``out_dir`` and return the output path.

        Writes one cube per ``(film, print)`` combination using the
        canonical filename (``lut_<version>_<film>_<print>.cube``) plus
        a ``bundle.json`` side-car, a quick-start ``README.md``, and a
        copy of ``SPEKTRAFILM_LICENSE.txt`` in the bundle root.

        When ``out_dir`` is ``None``, the bundle lands at
        ``cwd/build/lut_bundles/<spec.name>/`` — drop-in usable for a
        bake script that doesn't want to think about paths.

        The cube *format* depends on the spec's :class:`DeliveryTarget`:

        - ``target=None``: generic Adobe ``.cube`` with a provenance
          comment block at the top (multi-line attribution + license).
        - ``target`` set: target's format plugin (e.g., Lumix-strict
          ``.cube`` with ``#LUMIXPHOTOSTYLE`` and no extra comments).
          The generic sibling is **not** emitted — when a user picks a
          target they want exactly that file.

        If ``spec.qa`` is True, the QA suite runs after the LUTs are
        written and drops reports under ``<bundle>/qa/<per-print-name>/``
        — one folder per QA'd print (``spec.qa_print_index`` selects one
        print, ``None`` runs them all). The QA cache directories are
        deleted afterward so the bundle stays ship-ready.

        When ``spec.container == "zip"``, the populated bundle directory is
        also archived to ``<out_dir>.zip`` (or to ``out_dir`` itself if the
        caller already passed a ``.zip`` path), and that archive path is
        returned. The archive captures whatever the QA step produced —
        run QA *before* the archive step.
        """
        if out_dir is None:
            out_dir = Path.cwd() / _DEFAULT_OUT_SUBPATH / self.spec.name
        out_dir, archive_path = _bundle_output_paths(out_dir, self.spec.container)
        out_dir.mkdir(parents=True, exist_ok=True)

        if self.spec.target is not None:
            # Deferred import: delivery_targets references the format
            # registry; importing it at module-load order can race with
            # plugin registration.
            from spektrafilm_lut_creator.delivery_targets import get as get_target
            target = get_target(self.spec.target)
            fmt = get_format(target.format)
            for rel_path, lut in bundle.luts:
                full_path = out_dir / rel_path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                fmt.write(lut, full_path, **target.writer_kwargs)
        else:
            cube = get_format("cube")
            for rel_path, lut in bundle.luts:
                full_path = out_dir / rel_path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                header = _cube_header_lines(bundle.meta, rel_path)
                cube.write(lut, full_path, header_lines=header)

        (out_dir / "bundle.json").write_text(
            json.dumps(asdict(bundle.meta), indent=2, default=_json_default),
            encoding="utf-8",
        )
        (out_dir / _BUNDLE_README_FILENAME).write_text(
            _bundle_readme_text(bundle.meta),
            encoding="utf-8",
        )
        shutil.copy2(_lut_license_source_path(), out_dir / _LUT_LICENSE_FILENAME)
        n_cubes = len(bundle.luts)
        cube_word = "cube" if n_cubes == 1 else "cubes"
        emitted_ocio = self._maybe_emit_ocio(bundle, out_dir)
        extras = ", config.ocio" if emitted_ocio else ""
        print(f"[bake] wrote {n_cubes} {cube_word} + bundle.json, README.md, LICENSE{extras}")
        if self.spec.qa:
            qa_results = self._run_qa(bundle, out_dir)
            # Rewrite the README with a Quality pass/fail block now that
            # we have QA outcomes (n090 §6.1). The original README was
            # written above so the bundle is well-formed even when QA is
            # skipped; this overwrite is a refinement, not a fallback.
            (out_dir / _BUNDLE_README_FILENAME).write_text(
                _bundle_readme_text(bundle.meta, qa_results=qa_results),
                encoding="utf-8",
            )
        if archive_path is not None:
            archive_base = archive_path.with_suffix("")
            shutil.make_archive(
                str(archive_base),
                "zip",
                root_dir=out_dir.parent,
                base_dir=out_dir.name,
            )
            print(f"[done] {archive_path}")
            return archive_path
        print(f"[done] {out_dir}")
        return out_dir


def _cube_header_lines(meta: BundleMeta, rel_path: str) -> list[str]:
    """Render the bundle's provenance into ``# ``-prefixable comment lines
    suitable for the top of a ``.cube`` file.

    The lines are deliberately short and human-readable: a user opening
    the file in a text editor should immediately see what it is, how it
    was made, the license, and how to cite. Long fields wrap to multiple
    comment lines.
    """
    prov = meta.provenance
    sep = "=" * 76
    lines: list[str] = [sep, "spektrafilm LUT"]
    lines.append(f"Bundle:  {meta.name}  ({meta.topology}, {meta.resolution}^3)")
    if meta.stocks is not None:
        lines.append(f"Film:    {meta.stocks.film}")
        if meta.stocks.prints:
            lines.append(f"Print:   {', '.join(meta.stocks.prints)}")
    in_cs = meta.color_spaces.get("input")
    out_cs = meta.color_spaces.get("output")
    if in_cs is not None:
        lines.append(f"Input:   {in_cs.name}  (cctf {'on' if in_cs.cctf else 'off'})")
    if out_cs is not None:
        lines.append(f"Output:  {out_cs.name}  (cctf {'on' if out_cs.cctf else 'off'})")
    lines.append(f"Created: {prov.created}")
    lines.append(f"spektrafilm: {prov.spektrafilm_version}")
    lines.append(f"Project: {prov.project_url}")
    lines.append("")
    lines.append(prov.copyright)
    lines.append("")
    lines.extend(_wrap_field("License",  prov.license))
    lines.append("")
    lines.extend(_wrap_field("Citation", prov.citation))
    lines.append("")
    lines.extend(_wrap_field("Notes",    prov.notes))
    lines.append("")
    this_lut = next((l for l in meta.luts if l.path == rel_path), None)
    if this_lut is not None and this_lut.role != "combined":
        lines.append(
            f"Role:    {this_lut.role}  (domain={this_lut.domain} → range={this_lut.range})"
        )
    lines.append(f"File: {rel_path}  (see sibling bundle.json for full metadata)")
    lines.append(sep)
    return lines


def _wrap_field(label: str, text: str, width: int = 76) -> list[str]:
    """Soft-wrap a labeled paragraph onto an indented multi-line comment block."""
    import textwrap
    wrapped = textwrap.wrap(text, width=width - len(label) - 2)
    if not wrapped:
        return [f"{label}: "]
    first, *rest = wrapped
    indent = " " * (len(label) + 2)
    return [f"{label}: {first}"] + [f"{indent}{line}" for line in rest]


def _json_default(value):
    """Fallback JSON encoder for tuple-of-tuple wire constants etc."""
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"object of type {type(value).__name__} is not JSON-serializable")
