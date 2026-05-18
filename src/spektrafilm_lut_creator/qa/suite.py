"""Suite runner + markdown report emission.

``run(spec, bundle, out_dir)`` is the one-call entry point used by
``explore_lut.py`` and any other caller. It assembles the
:class:`QAContext`, executes the default test list, writes
``report.md`` and the figures, and returns the list of
:class:`Result` objects.

The report is markdown-only — renders in VS Code, GitHub, any reader.
HTML / PDF can be produced downstream from the same content.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

import numpy as np

from spektrafilm_lut_creator.bundles import Bundle, BundleSpec
from spektrafilm_lut_creator.formats import Lut
from spektrafilm_lut_creator.grid import cube_grid
from spektrafilm_lut_creator.qa import evaluators, reference
from spektrafilm_lut_creator.qa.result import Result
from spektrafilm_lut_creator.qa.tests import DEFAULT_TESTS


# Public re-export so callers can compose their own suites.
DEFAULT_SUITE: tuple[Callable[["QAContext"], Result], ...] = DEFAULT_TESTS


@dataclass
class QAContext:
    """Per-LUT context handed to every test function.

    Held read-only by tests; suite-level objects don't mutate it.

    Attributes
    ----------
    spec
        The :class:`BundleSpec` used to build the bundle. Tests use it
        to re-invoke the pipeline for ad-hoc patterns.
    bundle
        The built :class:`Bundle`. Carries metadata + the LUT list.
    paper_index
        Which LUT in ``bundle.luts`` this context is for.
    paper_name
        Convenience: the print stock name (e.g.,
        ``"kodak_portra_endura"``).
    lut
        The :class:`Lut` being QA'd.
    grid_input
        Shape ``(N³, 3)`` of on-grid input samples in the encoded
        input space. Constant for a given resolution.
    grid_output
        Shape ``(N³, 3)`` of on-grid output samples — the cube table
        flattened in Adobe canonical order.
    reference
        :class:`ReferenceSamples` holding the off-grid pipeline ground
        truth used by ``off_grid_identity``. Computed once per
        ``run()`` call and cached on disk.
    out_dir
        Root output directory for this QA pass.
    figures_dir
        ``out_dir / "figures"`` — where tests save PNGs.
    """
    spec: BundleSpec
    bundle: Bundle
    paper_index: int
    paper_name: str
    lut: Lut
    grid_input: np.ndarray
    grid_output: np.ndarray
    reference: "reference.ReferenceSamples"
    out_dir: Path
    figures_dir: Path


def list_tests() -> list[str]:
    """Names of the tests in the default suite, in execution order."""
    return [fn.__name__ for fn in DEFAULT_SUITE]


def _paper_name(bundle: Bundle, paper_index: int) -> str:
    """Resolve the human-readable paper name for the QA paper index.

    The ``paper_index`` always means "which print paper", indexed into
    ``bundle.meta.stocks.prints`` — the *bundle.luts* indexing is
    topology-dependent (1-LUT: 1:1; 2-LUT: film at 0 then prints).
    """
    if bundle.meta.stocks is not None:
        prints = bundle.meta.stocks.prints
        if paper_index < 0 or paper_index >= len(prints):
            raise IndexError(
                f"paper_index {paper_index} out of range for bundle with "
                f"{len(prints)} papers"
            )
        return prints[paper_index]
    # Fallback: no stocks recorded; assume 1-LUT and use the LUT path.
    return bundle.luts[paper_index][0]


def _effective_lut(bundle: Bundle, paper_index: int) -> tuple[str, Lut]:
    """Return ``(label, Lut)`` for the LUT to QA at ``paper_index``.

    For 1-LUT bundles this is exactly ``bundle.luts[paper_index]``.
    For 2-LUT and 4-LUT bundles, this composes the relevant LUTs at
    the bundle's cube resolution and returns a virtual combined
    :class:`Lut`. The composition uses trilinear interpolation in
    each stage — matching the most common host interpolation mode
    (Premiere/FFmpeg/OBS). The composed table is therefore *what
    users will deploy*, sampled at the bundle's grid.
    """
    topology = bundle.meta.topology
    if topology == "1lut":
        return bundle.luts[paper_index]
    if topology == "2lut":
        # Layout: bundle.luts[0] is the shared film LUT, then one
        # print LUT per paper in order.
        film_rel, film_lut = bundle.luts[0]
        print_rel, print_lut = bundle.luts[1 + paper_index]
        composed = _compose_film_print(film_lut, print_lut, bundle.meta.resolution)
        # Label by the print LUT's filename — that's the artifact the
        # user thinks of as "this paper's LUT chain".
        return print_rel, composed
    if topology == "3lut":
        # Layout: bundle.luts[0]=L1, [1]=L2 (shared); then [2+paper_index]=L3
        # for each paper in order. L3 is the combined back-half cube.
        l1 = bundle.luts[0][1]
        l2 = bundle.luts[1][1]
        l3_rel, l3 = bundle.luts[2 + paper_index]
        composed = _compose_3lut(l1, l2, l3, bundle.meta.resolution)
        return l3_rel, composed
    if topology == "4lut":
        # Layout: bundle.luts[0]=L1, [1]=L2 (shared); then [2+2*paper_index]=L3,
        # [3+2*paper_index]=L4 for each paper in order.
        l1 = bundle.luts[0][1]
        l2 = bundle.luts[1][1]
        l3_idx = 2 + 2 * paper_index
        l4_idx = 3 + 2 * paper_index
        l3 = bundle.luts[l3_idx][1]
        l4_rel, l4 = bundle.luts[l4_idx]
        composed = _compose_4lut(l1, l2, l3, l4, bundle.meta.resolution)
        return l4_rel, composed
    raise NotImplementedError(
        f"QA does not yet handle topology={topology!r}"
    )


def _compose_film_print(film_lut: Lut, print_lut: Lut, resolution: int) -> Lut:
    """Sample film_lut ∘ print_lut at a ``resolution^3`` cube grid.

    The composition is evaluated with trilinear interpolation (the
    host-default mode). The resulting :class:`Lut` table is what a
    user gets by applying the two cubes in order — encoded input RGB
    → cmy_film code → encoded output RGB — and is suitable for the
    standard QA harness without further awareness of the 2-LUT
    structure.
    """
    grid = cube_grid(resolution)
    cmy_codes = evaluators.apply_trilinear(film_lut.table, grid)
    rgb_encoded = evaluators.apply_trilinear(print_lut.table, cmy_codes)
    table = rgb_encoded.reshape(resolution, resolution, resolution, 3)
    title = f"{film_lut.title} + {print_lut.title}" if film_lut.title and print_lut.title else "2-lut chain"
    return Lut(table=table, title=title)


def _compose_3lut(l1: Lut, l2: Lut, l3: Lut, resolution: int) -> Lut:
    """Sample L1∘L2∘L3 at a ``resolution^3`` cube grid.

    Three trilinear hops total: encoded input RGB → log_e_film code →
    cmy_film code → encoded output RGB. One interpolation hop fewer than
    4-LUT, so off-grid error is between 2-LUT and 4-LUT.
    """
    grid = cube_grid(resolution)
    log_e_film_code = evaluators.apply_trilinear(l1.table, grid)
    cmy_film_code = evaluators.apply_trilinear(l2.table, log_e_film_code)
    rgb_encoded = evaluators.apply_trilinear(l3.table, cmy_film_code)
    table = rgb_encoded.reshape(resolution, resolution, resolution, 3)
    title = f"{l1.title} + {l2.title} + {l3.title}" if all(
        lut.title for lut in (l1, l2, l3)
    ) else "3-lut chain"
    return Lut(table=table, title=title)


def _compose_4lut(l1: Lut, l2: Lut, l3: Lut, l4: Lut, resolution: int) -> Lut:
    """Sample L1∘L2∘L3∘L4 at a ``resolution^3`` cube grid.

    Each stage is evaluated with trilinear interpolation (4 hops of
    interpolation total). The output is what a user gets by applying
    the four cubes in order: encoded input RGB → log_e_film code →
    cmy_film code → log_e_print code → encoded output RGB.

    Note that 4-stage trilinear chains accumulate more interpolation
    error than 1- or 2-LUT bundles at the same per-cube resolution,
    so the QA's ``off_grid_identity`` test typically reports higher
    ΔE for 4-LUT — that's the cost of the modular structure, not a
    bug in the bake.
    """
    grid = cube_grid(resolution)
    log_e_film_code = evaluators.apply_trilinear(l1.table, grid)
    cmy_film_code = evaluators.apply_trilinear(l2.table, log_e_film_code)
    log_e_print_code = evaluators.apply_trilinear(l3.table, cmy_film_code)
    rgb_encoded = evaluators.apply_trilinear(l4.table, log_e_print_code)
    table = rgb_encoded.reshape(resolution, resolution, resolution, 3)
    parts = [lut.title for lut in (l1, l2, l3, l4) if lut.title]
    title = " + ".join(parts) if parts else "4-lut chain"
    return Lut(table=table, title=title)


def run(
    spec: BundleSpec,
    bundle: Bundle,
    out_dir: Path | str,
    *,
    suite: Sequence[Callable[[QAContext], Result]] | None = None,
    paper_index: int = 0,
) -> list[Result]:
    """Run the QA suite against one paper's LUT chain in the bundle.

    Parameters
    ----------
    spec, bundle
        Both required: ``spec`` is the source-of-truth for pipeline
        invocation, ``bundle`` carries the cube and metadata.
    out_dir
        Directory to write ``report.md``, ``figures/*.png``, and
        ``cache/*.npz`` into. Created if missing.
    suite
        Optional alternative test list. Each item is a function
        taking a :class:`QAContext` and returning a :class:`Result`.
    paper_index
        Which print paper to QA. For ``1lut`` bundles this
        indexes directly into ``bundle.luts``; for ``2lut``
        the paper_index selects which paper's chain (shared film +
        that paper's print) to QA.

    Returns
    -------
    list[Result]
        The full result set for the run, in suite order.
    """
    suite = tuple(suite) if suite is not None else DEFAULT_SUITE
    spec_obj = spec
    bundle_obj = bundle
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    figures_dir = out_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = out_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    if not bundle_obj.luts:
        raise ValueError("bundle has no LUTs to QA")

    # Materialize the effective LUT for QA. For 2-LUT bundles, this is
    # the chain (film → print) sampled at the bundle's cube resolution
    # — what users will actually deploy. For 1-LUT bundles, it's just
    # the paper's combined LUT.
    rel_path, lut = _effective_lut(bundle_obj, paper_index)
    paper_name = _paper_name(bundle_obj, paper_index)

    n = lut.resolution
    grid_input = cube_grid(n)
    grid_output = lut.table.reshape(n ** 3, 3)

    print(f"[qa] computing reference samples for paper {paper_index} ({paper_name})...")
    ref = reference.compute_or_load(spec_obj, bundle_obj, paper_index, cache_dir)
    print(f"[qa]   cache key={ref.cache_key}  samples={ref.rng_samples_encoded.shape[0]}")

    ctx = QAContext(
        spec=spec_obj,
        bundle=bundle_obj,
        paper_index=paper_index,
        paper_name=paper_name,
        lut=lut,
        grid_input=grid_input,
        grid_output=grid_output,
        reference=ref,
        out_dir=out_dir,
        figures_dir=figures_dir,
    )

    results: list[Result] = []
    for fn in suite:
        print(f"[qa] running {fn.__name__}...")
        try:
            result = fn(ctx)
        except Exception as exc:  # noqa: BLE001 — one failing test should not abort the suite
            result = Result(
                name=fn.__name__,
                summary={"error": str(exc)},
                interpretation=f"Test raised {type(exc).__name__}: {exc}",
                passed=False,
            )
            print(f"[qa]   FAILED: {exc}")
        results.append(result)

    report_path = out_dir / "report.md"
    write_report(results, ctx, report_path)
    # Render the same content as a self-contained HTML page next to
    # report.md. Cheap (~100ms) and the colorist can double-click it.
    from spektrafilm_lut_creator.qa.html_export import report_md_to_html
    html_path = report_md_to_html(report_path)

    n_pass = sum(1 for r in results if r.passed is True)
    n_fail = sum(1 for r in results if r.passed is False)
    n_info = sum(1 for r in results if r.passed is None)
    print(f"[qa] summary: {n_pass} pass, {n_fail} fail, {n_info} info")
    if n_fail:
        for r in results:
            if r.passed is False:
                print(f"[qa]   FAIL  {r.name}  {r.short_summary()}")
    print(f"[qa] wrote {report_path}, {html_path.name}")
    return results


# ---------------------------------------------------------------------------
# Markdown report emission.
# ---------------------------------------------------------------------------

_STATUS_BADGES = {"PASS": "✅", "FAIL": "❌", "INFO": "ℹ️"}


def write_report(results: list[Result], ctx: QAContext, path: Path) -> None:
    """Write ``report.md`` summarizing the QA run.

    The layout is the same every time:

    1. Run header (bundle, paper, color spaces, resolution).
    2. Summary table — one row per test, status + headline number(s).
    3. Failing tests called out at the top (in body order otherwise).
    4. Per-test sections: heading, status, summary table, figure,
       interpretation paragraph, references list.

    Markdown renders cleanly in VS Code, GitHub, and any reader. PDF
    export is a downstream concern.
    """
    bundle = ctx.bundle
    spec = ctx.spec
    lines: list[str] = []

    lines.append(f"# QA report — `{bundle.meta.name}`")
    lines.append("")
    lines.append(f"- **Paper**: `{ctx.paper_name}`")
    lines.append(f"- **Film**: `{spec.film_profile}`")
    lines.append(f"- **Input color space**: `{spec.input_color_space}`")
    lines.append(f"- **Output color space**: `{spec.output_color_space}`")
    lines.append(f"- **Topology**: `{bundle.meta.topology}`  ·  **Resolution**: `{spec.resolution}^3`")
    lines.append(f"- **Gamut clip**: `{spec.gamut_clip}`")
    lines.append(f"- **spektrafilm version**: `{bundle.meta.provenance.spektrafilm_version}`")
    lines.append(f"- **Generated**: `{bundle.meta.provenance.created}`")
    lines.append("")

    # Failing tests called out at the top.
    failing = [r for r in results if r.passed is False]
    if failing:
        lines.append("## ⚠ Failing tests")
        lines.append("")
        for r in failing:
            lines.append(f"- **{r.name}** — {r.short_summary()}")
        lines.append("")

    # Summary table.
    lines.append("## Summary")
    lines.append("")
    lines.append("| Test | Status | Headline numbers |")
    lines.append("|---|---|---|")
    for r in results:
        badge = _STATUS_BADGES[r.status()]
        summary = r.short_summary()
        # Escape pipes inside the summary cell.
        summary = summary.replace("|", "\\|")
        lines.append(f"| [{r.name}](#{_anchor(r.name)}) | {badge} {r.status()} | {summary} |")
    lines.append("")

    # Per-test sections.
    for r in results:
        lines.append(f"## {r.name}")
        lines.append("")
        badge = _STATUS_BADGES[r.status()]
        lines.append(f"**Status**: {badge} {r.status()}")
        if r.units:
            lines.append(f"  ·  **Units**: {r.units}")
        lines.append("")

        # Summary key/value table.
        if r.summary:
            lines.append("| Metric | Value |")
            lines.append("|---|---|")
            for key, val in r.summary.items():
                rendered = _render_value(val)
                lines.append(f"| `{key}` | {rendered} |")
            lines.append("")

        if r.figure_path is not None:
            rel = _relative(r.figure_path, path.parent)
            lines.append(f"![{r.name}]({rel})")
            lines.append("")

        if r.interpretation:
            lines.append(r.interpretation)
            lines.append("")

        if r.references:
            lines.append("**References:**")
            for ref in r.references:
                lines.append(f"- {ref}")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(
        f"Generated by `spektrafilm_lut_creator.qa` "
        f"(spektrafilm {bundle.meta.provenance.spektrafilm_version}). "
        f"See `studies/a40_lut_system/n080_lut_quality_and_visualization.md` "
        f"for design context."
    )
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def _render_value(val) -> str:
    """Render a summary value for the markdown table."""
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, np.integer)):
        return str(int(val))
    if isinstance(val, float):
        return f"{val:.4g}"
    return f"`{val}`"


def _anchor(name: str) -> str:
    """GitHub-flavored markdown anchor for a heading."""
    return name.replace("_", "-").lower()


def _relative(target: Path, base: Path) -> str:
    """Path of ``target`` relative to ``base`` as a forward-slash string."""
    target = Path(target).resolve()
    base = Path(base).resolve()
    try:
        return target.relative_to(base).as_posix()
    except ValueError:
        # Targets outside base — fall back to absolute path string.
        return target.as_posix()
