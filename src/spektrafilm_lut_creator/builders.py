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
from dataclasses import asdict
from pathlib import Path

import numpy as np

from spektrafilm_lut_creator.bundles import Bundle, BundleSpec
from spektrafilm_lut_creator.color_spaces import (
    decode_cctf,
    encode_cctf,
    get as get_color_space,
)
from spektrafilm_lut_creator.formats import Lut, get_format
from spektrafilm_lut_creator.grid import cube_grid, grid_as_image
from spektrafilm_lut_creator.metadata import (
    SCHEMA_VERSION,
    BundleMeta,
    ColorSpaceMeta,
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
from spektrafilm_lut_creator.wires import DensityWire, LogEWire


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


_LUT_LICENSE_FILENAME = "LICENSE_SPEKTRAFILM_LUT"
_BUNDLE_README_FILENAME = "README.md"

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
    paper = _normalize_stock(print_stock)
    return f"lut_{version_tag}_{film}_{paper}{ext}"


def _canonical_lut_title(spec: BundleSpec, print_stock: str, version_tag: str) -> str:
    """Compact LUT title for a combined 1-LUT: ``{version}_{film}_{print}``."""
    film = _normalize_stock(spec.film_profile)
    paper = _normalize_stock(print_stock)
    return f"{version_tag}_{film}_{paper}"


def _film_lut_filename(spec: BundleSpec, version_tag: str, *, ext: str = ".cube") -> str:
    """2-LUT film-half filename: ``lut_{version}_{film}_film.cube``.

    The film LUT is shared across papers within the bundle; the
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
    """2-LUT print-half filename: ``lut_{version}_{film}_{paper}_print.cube``.

    The film stock appears in the print-LUT filename because the print
    LUT's input wire is the *film stock's* normalized cmy_film density
    (the ``d_max`` constants are stock-dependent — see the bundle
    invariant in n010 §3 / n030 §3).
    """
    film = _normalize_stock(spec.film_profile)
    paper = _normalize_stock(print_stock)
    return f"lut_{version_tag}_{film}_{paper}_print{ext}"


def _print_lut_title(spec: BundleSpec, print_stock: str, version_tag: str) -> str:
    """2-LUT print-half title: ``{version}_{film}_{paper}_print``."""
    film = _normalize_stock(spec.film_profile)
    paper = _normalize_stock(print_stock)
    return f"{version_tag}_{film}_{paper}_print"


# ---------------------------------------------------------------------------
# 4-LUT filename helpers.
#
# L1 / L2 are shared across papers (filming stages don't depend on the print
# paper); L3 / L4 are per-paper. The film stock appears in every filename
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
    """L3 filename: ``lut_{version}_{film}_{paper}_l3.cube``."""
    film = _normalize_stock(spec.film_profile)
    paper = _normalize_stock(print_stock)
    return f"lut_{version_tag}_{film}_{paper}_l3{ext}"


def _l3_lut_title(spec: BundleSpec, print_stock: str, version_tag: str) -> str:
    film = _normalize_stock(spec.film_profile)
    paper = _normalize_stock(print_stock)
    return f"{version_tag}_{film}_{paper}_l3"


def _l4_lut_filename(spec: BundleSpec, print_stock: str, version_tag: str,
                     *, ext: str = ".cube") -> str:
    """L4 filename: ``lut_{version}_{film}_{paper}_l4.cube``."""
    film = _normalize_stock(spec.film_profile)
    paper = _normalize_stock(print_stock)
    return f"lut_{version_tag}_{film}_{paper}_l4{ext}"


def _l4_lut_title(spec: BundleSpec, print_stock: str, version_tag: str) -> str:
    film = _normalize_stock(spec.film_profile)
    paper = _normalize_stock(print_stock)
    return f"{version_tag}_{film}_{paper}_l4"


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


def _bundle_readme_text(meta: BundleMeta) -> str:
    """Render a quick-start README for the bundle root."""
    prov = meta.provenance
    input_cs = meta.color_spaces.get("input")
    output_cs = meta.color_spaces.get("output")
    lines = [
        "# spektrafilm LUT bundle",
        "",
        "This folder contains exported LUT files plus the machine-readable metadata and license for this bundle.",
        "",
        "## Quick info",
        f"- Name: {meta.name}",
        f"- Topology: {meta.topology}",
        f"- Resolution: {meta.resolution}^3",
        f"- Delivery target: {meta.target or 'generic Adobe .cube'}",
        f"- Created: {prov.created}",
        f"- spektrafilm version: {prov.spektrafilm_version}",
    ]
    if meta.stocks is not None:
        lines.append(f"- Film stock: {meta.stocks.film}")
        if meta.stocks.prints:
            lines.append(f"- Print stocks: {', '.join(meta.stocks.prints)}")
    if input_cs is not None:
        lines.append(
            f"- Input color space: {input_cs.name} (cctf {'on' if input_cs.cctf else 'off'})"
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
            descr = f"print half for {lut.paper} (L3∘L4: cmy_film → output RGB)"
        elif lut.role == "combined":
            descr = f"full chain for {lut.paper}"
        elif lut.role == "filming_expose":
            descr = "shared L1 — filming.expose (input RGB → normalized log_e_film code)"
        elif lut.role == "filming_develop":
            descr = "shared L2 — filming.develop (log_e_film code → normalized cmy_film code)"
        elif lut.role == "printing_expose":
            descr = f"L3 for {lut.paper} — printing.expose (cmy_film code → normalized log_e_print code)"
        elif lut.role == "printing_develop_scan":
            descr = f"L4 for {lut.paper} — printing.develop + scanning.scan (log_e_print code → output RGB)"
        elif lut.role == "printing_combined":
            descr = f"L3 for {lut.paper} — printing.expose + develop + scan (cmy_film code → output RGB)"
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
            "- L1 and L2 are shared across all papers in the bundle.",
            "- L3 is paper-specific; pick the cube matching the print stock you want.",
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
            "- L1 and L2 are shared across all papers in the bundle.",
            "- L3 and L4 are paper-specific; pick the pair matching the print stock you want.",
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
            "- **After L3 — `log_e_print`** (light hitting the print paper, log-shaped): decode via `wires/log_e_print` to get log10(E) at the paper. Enlarger-stage effects belong here — **enlarger diffusion filters** (soft-focus, baseboard scatter), simulated **dodge / burn masks**, and any other manipulation of the printing light.",
        ])
    lines.extend([
        "",
        "## Notes",
        f"- {prov.notes}",
        "- See bundle.json for the complete structured metadata.",
    ])
    return "\n".join(lines) + "\n"


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

        n_papers = len(spec.print_profiles)
        paper_word = "paper" if n_papers == 1 else "papers"
        print(
            f"[bake] {spec.name} "
            f"({spec.topology}, {spec.resolution}^3, {n_papers} {paper_word})"
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

        Each (film, paper) pair produces an independent cube; nothing is
        shared across papers. This is the simplest deployable form —
        users apply one cube and get the full simulation.
        """
        spec = self.spec
        n = spec.resolution
        grid = cube_grid(n)
        image_encoded = grid_as_image(grid, n)
        image_linear_in = decode_cctf(image_encoded, spec.input_color_space).astype(np.float32)

        provenance = ProvenanceMeta()
        version_tag = _normalize_version(provenance.spektrafilm_version)

        bundle_luts: list[tuple[str, Lut]] = []
        lut_metas: list[LutFileMeta] = []
        for print_stock in spec.print_profiles:
            pipeline = self._make_pipeline(spec, in_entry, out_entry, print_stock)
            image_linear_out = pipeline.process(image_linear_in)
            image_encoded_out = encode_cctf(
                np.asarray(image_linear_out, dtype=float),
                spec.output_color_space,
            )
            encoded_clipped = np.clip(image_encoded_out, 0.0, 1.0)
            table = encoded_clipped.reshape(n, n, n, 3)

            rel_path = _canonical_lut_filename(spec, print_stock, version_tag)
            title = _canonical_lut_title(spec, print_stock, version_tag)

            bundle_luts.append((rel_path, Lut(table=table, title=title)))
            lut_metas.append(LutFileMeta(
                role="combined",
                path=rel_path,
                domain="input_rgb",
                range="output_rgb",
                paper=print_stock,
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
        )
        return Bundle(luts=bundle_luts, meta=meta)

    # ---- 2-LUT (M5) ------------------------------------------------------

    def _build_2lut_film_print(self, in_entry, out_entry) -> Bundle:
        """Bake one film LUT (L1∘L2) + per-paper print LUTs (L3∘L4).

        The film LUT depends only on the film stock and input space;
        it is baked once and shared across every print paper in the
        bundle. Each paper gets its own print LUT that takes
        normalized cmy_film density (the ``d_max``-scaled output of
        the film LUT) and produces encoded output RGB.

        ``d_max`` is measured by sampling the film half at a 9^3 grid
        through the actual pipeline (with one representative paper
        attached, since the cmy_film tap is print-independent) and
        taking the per-channel maximum × :data:`_DENSITY_MARGIN`. This
        is robust to film-stock differences and to whatever the
        spektrafilm chemistry model is doing under the hood.
        """
        spec = self.spec
        n = spec.resolution
        provenance = ProvenanceMeta()
        version_tag = _normalize_version(provenance.spektrafilm_version)

        # Build one pipeline against the first paper to (a) measure
        # d_max and (b) bake the shared film LUT. The cmy_film tap is
        # only a function of film + input, so the choice of paper here
        # is immaterial.
        first_paper = spec.print_profiles[0]
        pipeline = self._make_pipeline(spec, in_entry, out_entry, first_paper)
        density_wire = self._compute_density_wire(pipeline, spec)
        film_lut = self._bake_film_lut(pipeline, spec, density_wire, version_tag)

        bundle_luts: list[tuple[str, Lut]] = [film_lut]
        lut_metas: list[LutFileMeta] = [LutFileMeta(
            role="film",
            path=film_lut[0],
            domain="input_rgb",
            range="cmy_film",
            paper=None,
        )]

        # Bake one print LUT per paper.
        for paper in spec.print_profiles:
            pipeline = self._make_pipeline(spec, in_entry, out_entry, paper)
            print_lut = self._bake_print_lut(pipeline, spec, density_wire, paper, version_tag)
            bundle_luts.append(print_lut)
            lut_metas.append(LutFileMeta(
                role="print",
                path=print_lut[0],
                domain="cmy_film",
                range="output_rgb",
                paper=paper,
            ))

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
        )
        return Bundle(luts=bundle_luts, meta=meta)

    # ---- 3-LUT ------------------------------------------------------

    def _build_3lut_film_develop_print_combined(self, in_entry, out_entry) -> Bundle:
        """Bake the three-stage LUT chain: L1 + L2 + collapsed back-half.

        Stage mapping:

        - **L1** ``rgb_in → log_e_film`` — ``filming.expose`` (shared)
        - **L2** ``log_e_film → cmy_film`` — ``filming.develop`` (shared)
        - **L3** ``cmy_film → rgb_out`` — collapses ``printing.expose +
          printing.develop + scanning.scan`` into one cube (per paper)

        The trade vs 4-LUT: the ``log_e_print`` tap is *not* exposed,
        so enlarger-stage effects (diffusion filters, dodge / burn,
        baseboard scatter) cannot be injected. In exchange the bundle
        ships one fewer cube per paper, and the back-half stays
        monolithic — fewer interpolation stages, lower compound error.
        Use 3-LUT when only grain (cmy_film tap) and pre-film spatial
        effects (log_e_film tap) matter; use 4-LUT when enlarger
        manipulation is in scope.

        Total cubes for an N-paper bundle: ``2 + N``.

        Wires recorded in ``bundle.json``:

        - ``log_e_film``: linear-in-log10 shaper for L1's output / L2's input.
        - ``cmy_film``: per-channel density normalization for L2's output / L3's input.
        - ``log_e_print`` and ``cmy_print`` stay None (collapsed inside L3).
        """
        spec = self.spec
        provenance = ProvenanceMeta()
        version_tag = _normalize_version(provenance.spektrafilm_version)

        # Shared pipeline: filming.* stages are paper-independent, so the
        # choice of paper for the shared pass is just a convenient anchor.
        first_paper = spec.print_profiles[0]
        pipeline_shared = self._make_pipeline(spec, in_entry, out_entry, first_paper)

        # Probe wires from the same 9³ pass (cheap; pipeline runs sub-second).
        log_e_film_wire = self._compute_log_e_wire(pipeline_shared, spec, tap="log_e_film")
        density_wire = self._compute_density_wire(pipeline_shared, spec)

        # Bake L1 + L2 once.
        l1 = self._bake_l1(pipeline_shared, spec, log_e_film_wire, version_tag)
        l2 = self._bake_l2(pipeline_shared, spec, log_e_film_wire,
                           density_wire, version_tag)
        bundle_luts: list[tuple[str, Lut]] = [l1, l2]
        lut_metas: list[LutFileMeta] = [
            LutFileMeta(role="filming_expose",
                        path=l1[0], domain="input_rgb", range="log_e_film", paper=None),
            LutFileMeta(role="filming_develop",
                        path=l2[0], domain="log_e_film", range="cmy_film", paper=None),
        ]

        # Bake the combined back-half once per paper. Math is identical to
        # the 2-LUT print LUT (cmy_film code → rgb_out); only the filename
        # role differs to stay consistent with the numbered-cube convention
        # we use for topologies with ≥3 cubes.
        for paper in spec.print_profiles:
            pipeline_paper = self._make_pipeline(spec, in_entry, out_entry, paper)
            l3 = self._bake_l3_combined(pipeline_paper, spec, density_wire,
                                        paper, version_tag)
            bundle_luts.append(l3)
            lut_metas.append(LutFileMeta(
                role="printing_combined",
                path=l3[0],
                domain="cmy_film",
                range="output_rgb",
                paper=paper,
            ))

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
        )
        return Bundle(luts=bundle_luts, meta=meta)

    def _bake_l3_combined(self, pipeline, spec, density_wire: DensityWire,
                          print_stock: str, version_tag: str) -> tuple[str, Lut]:
        """3-LUT L3: cmy_film code → encoded output RGB.

        Same math as :meth:`_bake_print_lut` (2-LUT) — uniform [0,1]³ code
        grid → decode to density via :class:`DensityWire` → inject at the
        ``cmy_film`` tap → run pipeline to ``rgb_out`` → encode output CCTF.
        Filename uses the numbered-cube convention: ``lut_<v>_<film>_<paper>_l3.cube``.
        """
        n = spec.resolution
        code_grid = cube_grid(n)
        density_grid = code_to_density(code_grid, density_wire)
        density_image = grid_as_image(density_grid, n).astype(np.float32)
        rgb_linear_out = np.asarray(
            pipeline.process(density_image, inject="cmy_film", collect="rgb_out"),
            dtype=float,
        )
        rgb_encoded_out = encode_cctf(rgb_linear_out, spec.output_color_space)
        rgb_clipped = np.clip(rgb_encoded_out, 0.0, 1.0)
        table = rgb_clipped.reshape(n, n, n, 3)
        rel_path = _l3_lut_filename(spec, print_stock, version_tag)
        title = _l3_lut_title(spec, print_stock, version_tag)
        return rel_path, Lut(table=table, title=title)

    # ---- 4-LUT (M6) ------------------------------------------------------

    def _build_4lut_film_develop_print_develop(self, in_entry, out_entry) -> Bundle:
        """Bake the four-stage LUT chain.

        Stage mapping (n010 §2):

        - **L1** ``rgb_in → log_e_film`` — ``filming.expose``
        - **L2** ``log_e_film → cmy_film`` — ``filming.develop``
        - **L3** ``cmy_film → log_e_print`` — ``printing.expose``
        - **L4** ``log_e_print → rgb_out`` — ``printing.develop`` +
          ``scanning.scan``

        L1 and L2 don't depend on the print paper (the filming stages
        only see the film stock + input color space), so they're baked
        **once and shared** across every paper in the bundle. L3 and
        L4 are paper-specific.

        Total cubes for an N-paper bundle: ``2 + 2N``.

        Wires recorded in ``bundle.json``:

        - ``log_e_film``: linear-in-log10 shaper for L1's output / L2's
          input. Measured on a 9³ probe pass through the shared
          pipeline.
        - ``cmy_film``: per-channel density normalization for L2's
          output / L3's input. Same as 2-LUT.
        - ``log_e_print``: linear-in-log10 shaper for L3's output / L4's
          input. Measured on the same 9³ probe pass.

        Note: the ``log_e_print`` wire is measured against the *first*
        paper's pipeline and reused across all papers. For typical
        spektrafilm chemistry, paper-to-paper variation in the
        log_e_print range is small relative to the wire's margin
        (``_LOG_E_MARGIN`` = 0.1 log E); if a future stock falls
        outside, raise the margin or switch to per-paper wires.
        """
        spec = self.spec
        provenance = ProvenanceMeta()
        version_tag = _normalize_version(provenance.spektrafilm_version)

        # Shared pipeline: paper-independent stages (filming.*) produce
        # identical output regardless of which paper we attach here, so
        # we use the first paper as a convenient anchor.
        first_paper = spec.print_profiles[0]
        pipeline_shared = self._make_pipeline(spec, in_entry, out_entry, first_paper)

        # Probe wires from a single 9³ pass.
        log_e_film_wire = self._compute_log_e_wire(pipeline_shared, spec, tap="log_e_film")
        density_wire = self._compute_density_wire(pipeline_shared, spec)
        log_e_print_wire = self._compute_log_e_wire(pipeline_shared, spec, tap="log_e_print")

        # Bake L1 + L2 once.
        l1 = self._bake_l1(pipeline_shared, spec, log_e_film_wire, version_tag)
        l2 = self._bake_l2(pipeline_shared, spec, log_e_film_wire,
                           density_wire, version_tag)
        bundle_luts: list[tuple[str, Lut]] = [l1, l2]
        lut_metas: list[LutFileMeta] = [
            LutFileMeta(role="filming_expose",
                        path=l1[0], domain="input_rgb", range="log_e_film", paper=None),
            LutFileMeta(role="filming_develop",
                        path=l2[0], domain="log_e_film", range="cmy_film", paper=None),
        ]

        # Bake L3 + L4 per paper.
        for paper in spec.print_profiles:
            pipeline_paper = self._make_pipeline(spec, in_entry, out_entry, paper)
            l3 = self._bake_l3(pipeline_paper, spec, density_wire,
                               log_e_print_wire, paper, version_tag)
            l4 = self._bake_l4(pipeline_paper, spec, log_e_print_wire,
                               paper, version_tag)
            bundle_luts.extend([l3, l4])
            lut_metas.extend([
                LutFileMeta(role="printing_expose",
                            path=l3[0], domain="cmy_film", range="log_e_print",
                            paper=paper),
                LutFileMeta(role="printing_develop_scan",
                            path=l4[0], domain="log_e_print", range="output_rgb",
                            paper=paper),
            ])

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
        probe_image_lin = decode_cctf(probe_image_enc, spec.input_color_space).astype(np.float32)
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

    def _bake_film_lut(self, pipeline, spec, density_wire: DensityWire,
                       version_tag: str) -> tuple[str, Lut]:
        """Bake the L1∘L2 LUT: encoded input RGB → normalized cmy_film code."""
        n = spec.resolution
        grid = cube_grid(n)
        image_enc = grid_as_image(grid, n)
        image_lin = decode_cctf(image_enc, spec.input_color_space).astype(np.float32)
        cmy_film = np.asarray(
            pipeline.process(image_lin, collect="cmy_film"),
            dtype=float,
        )
        code = density_to_code(cmy_film, density_wire)
        # density_to_code already clamps to [0, 1].
        table = code.reshape(n, n, n, 3)
        rel_path = _film_lut_filename(spec, version_tag)
        title = _film_lut_title(spec, version_tag)
        return rel_path, Lut(table=table, title=title)

    def _bake_print_lut(self, pipeline, spec, density_wire: DensityWire,
                        print_stock: str, version_tag: str) -> tuple[str, Lut]:
        """Bake the L3∘L4 LUT: normalized cmy_film code → encoded output RGB.

        Input grid is sampled uniformly in normalized density code
        ``[0, 1]^3``; we decode to physical density via the
        :class:`DensityWire`, run the pipeline from the ``cmy_film``
        tap to ``rgb_out``, then encode the output CCTF.
        """
        n = spec.resolution
        code_grid = cube_grid(n)
        density_grid = code_to_density(code_grid, density_wire)
        density_image = grid_as_image(density_grid, n).astype(np.float32)
        rgb_linear_out = np.asarray(
            pipeline.process(density_image, inject="cmy_film", collect="rgb_out"),
            dtype=float,
        )
        rgb_encoded_out = encode_cctf(rgb_linear_out, spec.output_color_space)
        rgb_clipped = np.clip(rgb_encoded_out, 0.0, 1.0)
        table = rgb_clipped.reshape(n, n, n, 3)
        rel_path = _print_lut_filename(spec, print_stock, version_tag)
        title = _print_lut_title(spec, print_stock, version_tag)
        return rel_path, Lut(table=table, title=title)

    # ---- 4-LUT helpers (M6) ---------------------------------------------

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
            probe_image_enc, spec.input_color_space
        ).astype(np.float32)
        log_e = np.asarray(
            pipeline.process(probe_image_lin, collect=tap),
            dtype=float,
        ).reshape(-1, 3)
        lo = float(log_e.min()) - _LOG_E_MARGIN
        hi = float(log_e.max()) + _LOG_E_MARGIN
        # Round outward so the clamped wire strictly contains the observed
        # log_e range: floor the min (toward -∞), ceil the max (toward +∞).
        return LogEWire(min=_round_wire_floor(lo), max=_round_wire_ceil(hi))

    def _bake_l1(self, pipeline, spec, log_e_film_wire: LogEWire,
                 version_tag: str) -> tuple[str, Lut]:
        """L1: encoded input RGB → normalized log_e_film code."""
        n = spec.resolution
        grid = cube_grid(n)
        image_enc = grid_as_image(grid, n)
        image_lin = decode_cctf(image_enc, spec.input_color_space).astype(np.float32)
        log_e_film = np.asarray(
            pipeline.process(image_lin, collect="log_e_film"),
            dtype=float,
        )
        code = log_e_to_code(log_e_film, log_e_film_wire)
        table = np.clip(code, 0.0, 1.0).reshape(n, n, n, 3)
        rel_path = _l1_lut_filename(spec, version_tag)
        title = _l1_lut_title(spec, version_tag)
        return rel_path, Lut(table=table, title=title)

    def _bake_l2(self, pipeline, spec, log_e_film_wire: LogEWire,
                 density_wire: DensityWire, version_tag: str) -> tuple[str, Lut]:
        """L2: normalized log_e_film code → normalized cmy_film code."""
        n = spec.resolution
        code_grid = cube_grid(n)
        log_e_grid = code_to_log_e(code_grid, log_e_film_wire)
        log_e_image = grid_as_image(log_e_grid, n).astype(np.float32)
        cmy_film = np.asarray(
            pipeline.process(log_e_image, inject="log_e_film", collect="cmy_film"),
            dtype=float,
        )
        code = density_to_code(cmy_film, density_wire)
        table = code.reshape(n, n, n, 3)
        rel_path = _l2_lut_filename(spec, version_tag)
        title = _l2_lut_title(spec, version_tag)
        return rel_path, Lut(table=table, title=title)

    def _bake_l3(self, pipeline, spec, density_wire: DensityWire,
                 log_e_print_wire: LogEWire, print_stock: str,
                 version_tag: str) -> tuple[str, Lut]:
        """L3: normalized cmy_film code → normalized log_e_print code."""
        n = spec.resolution
        code_grid = cube_grid(n)
        density_grid = code_to_density(code_grid, density_wire)
        density_image = grid_as_image(density_grid, n).astype(np.float32)
        log_e_print = np.asarray(
            pipeline.process(density_image, inject="cmy_film", collect="log_e_print"),
            dtype=float,
        )
        code = log_e_to_code(log_e_print, log_e_print_wire)
        table = np.clip(code, 0.0, 1.0).reshape(n, n, n, 3)
        rel_path = _l3_lut_filename(spec, print_stock, version_tag)
        title = _l3_lut_title(spec, print_stock, version_tag)
        return rel_path, Lut(table=table, title=title)

    def _bake_l4(self, pipeline, spec, log_e_print_wire: LogEWire,
                 print_stock: str, version_tag: str) -> tuple[str, Lut]:
        """L4: normalized log_e_print code → encoded output RGB.

        Covers both ``printing.develop`` (log_e_print → cmy_print)
        and ``scanning.scan`` (cmy_print → rgb_out). cmy_print is
        not exposed as a wire — exposing it would push us to 6-LUT
        and isn't worth the extra cube per paper for v1.
        """
        n = spec.resolution
        code_grid = cube_grid(n)
        log_e_grid = code_to_log_e(code_grid, log_e_print_wire)
        log_e_image = grid_as_image(log_e_grid, n).astype(np.float32)
        rgb_linear_out = np.asarray(
            pipeline.process(log_e_image, inject="log_e_print", collect="rgb_out"),
            dtype=float,
        )
        rgb_encoded_out = encode_cctf(rgb_linear_out, spec.output_color_space)
        table = np.clip(rgb_encoded_out, 0.0, 1.0).reshape(n, n, n, 3)
        rel_path = _l4_lut_filename(spec, print_stock, version_tag)
        title = _l4_lut_title(spec, print_stock, version_tag)
        return rel_path, Lut(table=table, title=title)

    def _run_qa(self, bundle: Bundle, bundle_root: Path) -> None:
        """Run the QA suite for the spec's selected paper(s).

        Reports land at ``<bundle_root>/qa/<per-paper-bundle-name>/``;
        when ``spec.qa_paper_index`` is None, every paper in the bundle
        gets its own report folder. After each paper's run the
        ``cache/`` subdirectory is removed — the reference samples are
        cheap to recompute when needed and don't belong in a shipped
        bundle.
        """
        # Lazy import: qa.suite imports bundles/builders symbols transitively,
        # so eager-importing here would risk a cycle on cold module load.
        from spektrafilm_lut_creator.qa import run as run_qa
        from spektrafilm_lut_creator.naming import per_paper_bundle_name

        spec = self.spec
        if spec.qa_paper_index is None:
            paper_indices: tuple[int, ...] = tuple(range(len(spec.print_profiles)))
        else:
            paper_indices = (spec.qa_paper_index,)

        qa_root = bundle_root / "qa"
        qa_root.mkdir(parents=True, exist_ok=True)

        for idx in paper_indices:
            paper = spec.print_profiles[idx]
            report_name = per_paper_bundle_name(
                film_profile=spec.film_profile,
                print_profile=paper,
                topology=spec.topology,
                input_color_space=spec.input_color_space,
                output_color_space=spec.output_color_space,
            )
            report_dir = qa_root / report_name
            run_qa(spec, bundle, report_dir, paper_index=idx)
            # The QA reference cache is regenerable scratch work — strip
            # it before the bundle is potentially zipped or shipped.
            cache_dir = report_dir / "cache"
            if cache_dir.exists():
                shutil.rmtree(cache_dir)

    def write(self, bundle: Bundle, out_dir: Path | None = None) -> Path:
        """Write a built bundle to ``out_dir`` and return the output path.

        Writes one cube per ``(film, print)`` combination using the
        canonical filename (``lut_<version>_<film>_<print>.cube``) plus
        a ``bundle.json`` side-car, a quick-start ``README.md``, and a
        copy of ``LICENSE_SPEKTRAFILM_LUT`` in the bundle root.

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
        written and drops reports under ``<bundle>/qa/<per-paper-name>/``
        — one folder per QA'd paper (``spec.qa_paper_index`` selects one
        paper, ``None`` runs them all). The QA cache directories are
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
        print(f"[bake] wrote {n_cubes} {cube_word} + bundle.json, README.md, LICENSE")
        if self.spec.qa:
            self._run_qa(bundle, out_dir)
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
