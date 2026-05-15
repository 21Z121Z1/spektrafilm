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
)


# Brand prefixes stripped from profile stock names when building canonical
# camera-safe filename tags. Order matters when prefixes share a stem (none
# here yet). Extend as new vendors arrive.
_BRAND_PREFIXES: tuple[str, ...] = (
    "kodak", "fujifilm", "fuji", "ilford", "agfa",
    "cinestill", "polaroid", "ferrania", "lomography",
)

_LUT_LICENSE_FILENAME = "LICENSE_SPEKTRAFILM_LUT"
_BUNDLE_README_FILENAME = "README.md"


def _normalize_stock(stock: str) -> str:
    """``kodak_portra_400`` → ``portra400``; ``fujifilm_c200`` → ``c200``;
    ``fujifilm_crystal_archive_typeii`` → ``crystalarchive``.

    Strips the brand prefix (if recognized) and fuses the first two
    remaining underscore-separated segments without delimiter.
    """
    parts = stock.lower().split("_")
    if parts and parts[0] in _BRAND_PREFIXES:
        parts = parts[1:]
    return "".join(parts[:2])


def _normalize_version(version: str) -> str:
    """``0.3.2`` → ``v032``; ``0.4.1.dev0+abc`` → ``v041``.

    Strips PEP 440 dev / local-version suffixes, drops dots, prepends ``v``.
    """
    base = version.split("+", 1)[0].split(".dev", 1)[0]
    digit_groups = [g for g in base.split(".") if g.isdigit()]
    return "v" + "".join(digit_groups)


def _canonical_lut_filename(
    spec: BundleSpec, print_stock: str, version_tag: str, *, ext: str = ".cube"
) -> str:
    """Build the canonical camera-safe LUT filename.

    Pattern: ``lut_{version}_{film}_{print}.cube``
    Example: ``lut_v032_portra400_supraendura.cube``
    """
    film = _normalize_stock(spec.film_profile)
    paper = _normalize_stock(print_stock)
    return f"lut_{version_tag}_{film}_{paper}{ext}"


def _canonical_lut_title(spec: BundleSpec, print_stock: str, version_tag: str) -> str:
    """Compact LUT title: ``{version}_{film}_{print}``.

    Drops color spaces from the filename form so the title stays short
    in grading-suite LUT pickers (which sometimes truncate or wrap long
    names).
    """
    film = _normalize_stock(spec.film_profile)
    paper = _normalize_stock(print_stock)
    return f"{version_tag}_{film}_{paper}"


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
        label = lut.paper or lut.role
        lines.append(f"- {lut.path}: {lut.role} LUT for {label}")
    lines.extend([
        "",
        "## Notes",
        f"- {prov.notes}",
        "- See bundle.json for the complete structured metadata.",
    ])
    return "\n".join(lines) + "\n"


class BundleBuilder:
    """Build a LUT bundle by driving the spektrafilm pipeline.

    M4 implements ``topology="1-lut-combined"``. Other topologies raise
    :class:`NotImplementedError`.
    """

    def __init__(self, spec: BundleSpec):
        if spec.topology != "1-lut-combined":
            raise NotImplementedError(
                f"BundleBuilder currently supports topology='1-lut-combined' only; "
                f"got {spec.topology!r}"
            )
        self.spec = spec

    def build(self) -> Bundle:
        spec = self.spec
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

        # Deferred runtime import — keeps `import spektrafilm_lut_creator`
        # cheap for callers that only need registry / metadata access.
        from spektrafilm.runtime.params_builder import digest_params, init_params
        from spektrafilm.runtime.pipeline import SimulationPipeline

        film_stock = spec.film_profile
        print_stocks = spec.print_profiles
        n = spec.resolution
        grid = cube_grid(n)
        image_encoded = grid_as_image(grid, n)
        image_linear_in = decode_cctf(image_encoded, spec.input_color_space).astype(np.float32)

        # Build provenance once; its version informs every cube's
        # canonical filename and TITLE.
        provenance = ProvenanceMeta()
        version_tag = _normalize_version(provenance.spektrafilm_version)

        bundle_luts: list[tuple[str, Lut]] = []
        lut_metas: list[LutFileMeta] = []
        for print_stock in print_stocks:
            params = init_params(film_profile=film_stock, print_profile=print_stock)
            params.debug.lut_mode = True
            params.io.input_primaries = in_entry.primaries
            params.io.output_primaries = out_entry.primaries
            params.io.input_cctf_decoding = False
            params.io.output_cctf_encoding = False
            params.io.gamut_clip = spec.gamut_clip
            params = digest_params(params)

            pipeline = SimulationPipeline(params)
            image_linear_out = pipeline.process(image_linear_in)
            image_encoded_out = encode_cctf(
                np.asarray(image_linear_out, dtype=float),
                spec.output_color_space,
            )
            encoded_clipped = np.clip(image_encoded_out, 0.0, 1.0)
            # cube_grid lays samples in C-order with B slowest and R
            # fastest; Lut.table follows the same indexing.
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
            topology="1-lut-combined",
            resolution=n,
            target=spec.target,
            provenance=provenance,
            stocks=StocksMeta(film=film_stock, prints=tuple(print_stocks)),
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

    def write(self, bundle: Bundle, out_dir: Path) -> Path:
        """Write a built bundle to ``out_dir`` and return the output path.

        Writes one cube per ``(film, print)`` combination using the
        canonical filename (``lut_<version>_<film>_<print>.cube``) plus
        a ``bundle.json`` side-car, a quick-start ``README.md``, and a
        copy of ``LICENSE_SPEKTRAFILM_LUT`` in the bundle root. The cube
        *format* depends on the spec's :class:`DeliveryTarget`:
        the spec's :class:`DeliveryTarget`:

        - ``target=None``: generic Adobe ``.cube`` with a provenance
          comment block at the top (multi-line attribution + license).
        - ``target`` set: target's format plugin (e.g., Lumix-strict
          ``.cube`` with ``#LUMIXPHOTOSTYLE`` and no extra comments).
          The generic sibling is **not** emitted — when a user picks a
          target they want exactly that file.

        When ``spec.container == "zip"``, the populated bundle directory is
        also archived to ``<out_dir>.zip`` (or to ``out_dir`` itself if the
        caller already passed a ``.zip`` path), and that archive path is
        returned.
        """
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
        if archive_path is not None:
            archive_base = archive_path.with_suffix("")
            shutil.make_archive(
                str(archive_base),
                "zip",
                root_dir=out_dir.parent,
                base_dir=out_dir.name,
            )
            return archive_path
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
