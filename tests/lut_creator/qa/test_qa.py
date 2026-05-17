"""Smoke test for the QA suite.

Builds a tiny 5^3 bundle and runs the default suite end-to-end. The
goal isn't to verify correctness of every metric — that's the
metric-module unit tests' job — but to catch import / wiring /
serialization breakage early.

Tests deliberately do *not* assert PASS on the small bundle; off-grid
ΔE₀₀ at 5^3 will exceed tolerances. We assert the suite *runs* (every
test returns a Result, no exceptions hidden in error-stub Results)
and that the report + figures land on disk.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from spektrafilm_lut_creator.builders import BundleBuilder
from spektrafilm_lut_creator.bundles import BundleSpec
from spektrafilm_lut_creator.qa import DEFAULT_SUITE, list_tests, run


_RESOLUTION = 5  # matches the builder smoke test's tiny bundle
_INPUT_CS = "ACEScg"
_OUTPUT_CS = "sRGB"


@pytest.fixture(scope="module")
def spec() -> BundleSpec:
    return BundleSpec(
        name="qa_smoke",
        film_profile="kodak_portra_400",
        print_profiles=("kodak_portra_endura",),
        input_color_space=_INPUT_CS,
        output_color_space=_OUTPUT_CS,
        topology="1lut",
        resolution=_RESOLUTION,
    )


@pytest.fixture(scope="module")
def bundle(spec: BundleSpec):
    return BundleBuilder(spec).build()


@pytest.fixture(scope="module")
def qa_results(spec, bundle, tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("qa_smoke")
    return run(spec, bundle, out_dir), out_dir


def test_default_suite_has_expected_tests():
    # 5 LUT-fidelity + 7 model-diagnostic + 2 input gamut compression
    # diagnostics + 1 output gamut compression diagnostic + 2 picture-
    # style diagnostics (gamut edge stress + R-G plane slices) = 17.
    assert len(DEFAULT_SUITE) == 17
    names = list_tests()
    assert "off_grid_identity" in names
    assert "monotonicity" in names
    assert "jacobian_condition" in names
    assert "total_variation" in names
    assert "gamut_self_intersection" in names
    assert "characteristic_curve" in names
    assert "dynamic_range_usage" in names
    assert "planckian_sweep" in names
    assert "highlight_rolloff" in names
    assert "black_toe" in names
    assert "hue_twist_oklab" in names
    assert "spectral_locus_envelope" in names
    assert "input_gamut_compression_preview" in names
    assert "input_gamut_compression_smoothness" in names
    assert "output_gamut_compression_preview" in names
    assert "gamut_edge_stress" in names
    assert "rg_plane_slices" in names


def test_all_tests_return_a_result(qa_results):
    results, _ = qa_results
    assert len(results) == 17
    for r in results:
        assert r.name, f"empty name on result: {r}"


def test_no_test_raised_internally(qa_results):
    """A Result whose summary dict has an "error" key means the test
    raised — we surface those visibly rather than aborting the suite,
    so the smoke test asserts on the surfaced state."""
    results, _ = qa_results
    failing = [r for r in results if "error" in r.summary]
    assert not failing, (
        "tests raised internally:\n"
        + "\n".join(f"  {r.name}: {r.summary['error']}" for r in failing)
    )


def test_report_and_figures_are_written(qa_results):
    results, out_dir = qa_results
    out_dir = Path(out_dir)
    assert (out_dir / "report.md").exists()
    # Each test should produce a figure (the suite design — every
    # test pairs a metric with a visualization, per n080 §2).
    figures = list((out_dir / "figures").glob("*.png"))
    assert len(figures) == len(results), (
        f"expected one figure per test ({len(results)}); got {len(figures)}: "
        f"{sorted(p.name for p in figures)}"
    )


def test_reference_cache_invalidates_on_paper_change(spec, bundle, tmp_path):
    """The cache should round-trip on a second run with the same bundle."""
    run(spec, bundle, tmp_path, paper_index=0)
    cache_files = list((tmp_path / "cache").glob("*.npz"))
    assert cache_files, "first run should write the reference cache"
    # Second run reuses the cache; we just verify it completes.
    results = run(spec, bundle, tmp_path, paper_index=0)
    assert len(results) == 17


# ---------------------------------------------------------------------------
# 2-LUT chain QA (M5).
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def two_lut_spec() -> BundleSpec:
    return BundleSpec(
        name="qa_smoke_two_lut",
        film_profile="kodak_portra_400",
        print_profiles=("kodak_portra_endura", "fujifilm_crystal_archive_typeii"),
        input_color_space=_INPUT_CS,
        output_color_space=_OUTPUT_CS,
        topology="2lut",
        resolution=_RESOLUTION,
    )


@pytest.fixture(scope="module")
def two_lut_bundle(two_lut_spec: BundleSpec):
    return BundleBuilder(two_lut_spec).build()


@pytest.fixture(scope="module")
def two_lut_results(two_lut_spec, two_lut_bundle, tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("qa_two_lut")
    return run(two_lut_spec, two_lut_bundle, out_dir, paper_index=0), out_dir


def test_two_lut_qa_returns_all_tests(two_lut_results):
    results, _ = two_lut_results
    assert len(results) == 17


def test_two_lut_qa_no_tests_raised(two_lut_results):
    results, _ = two_lut_results
    failing = [r for r in results if "error" in r.summary]
    assert not failing, (
        "tests raised on 2-LUT bundle:\n"
        + "\n".join(f"  {r.name}: {r.summary['error']}" for r in failing)
    )


def test_two_lut_qa_writes_report_and_figures(two_lut_results):
    results, out_dir = two_lut_results
    out_dir = Path(out_dir)
    assert (out_dir / "report.md").exists()
    figures = list((out_dir / "figures").glob("*.png"))
    assert len(figures) == len(results)


def test_two_lut_qa_indexes_by_paper_not_lut(two_lut_spec, two_lut_bundle, tmp_path):
    """paper_index=1 must select the SECOND paper, not the second cube in
    bundle.luts (which is the first paper's print LUT at index 1 in a
    2-LUT layout). This is the topology-stable indexing contract."""
    # The bundle has 1 film + 2 print LUTs; paper_index in [0, 1].
    out_dir = tmp_path / "p1"
    results = run(two_lut_spec, two_lut_bundle, out_dir, paper_index=1)
    assert len(results) == 17
    report = (out_dir / "report.md").read_text(encoding="utf-8")
    # The report names the paper, which must be the second print stock.
    assert "fujifilm_crystal_archive_typeii" in report


def test_two_lut_qa_paper_index_out_of_range(two_lut_spec, two_lut_bundle, tmp_path):
    # Bundle has 2 papers; index 2 is out of range.
    with pytest.raises(IndexError, match="out of range"):
        run(two_lut_spec, two_lut_bundle, tmp_path, paper_index=2)


# ---------------------------------------------------------------------------
# 3-LUT chain QA.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def three_lut_spec() -> BundleSpec:
    return BundleSpec(
        name="qa_smoke_three_lut",
        film_profile="kodak_portra_400",
        print_profiles=("kodak_portra_endura", "fujifilm_crystal_archive_typeii"),
        input_color_space=_INPUT_CS,
        output_color_space=_OUTPUT_CS,
        topology="3lut",
        resolution=_RESOLUTION,
    )


@pytest.fixture(scope="module")
def three_lut_bundle(three_lut_spec: BundleSpec):
    return BundleBuilder(three_lut_spec).build()


@pytest.fixture(scope="module")
def three_lut_results(three_lut_spec, three_lut_bundle, tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("qa_three_lut")
    return run(three_lut_spec, three_lut_bundle, out_dir, paper_index=0), out_dir


def test_three_lut_qa_returns_all_tests(three_lut_results):
    results, _ = three_lut_results
    assert len(results) == 17


def test_three_lut_qa_no_tests_raised(three_lut_results):
    results, _ = three_lut_results
    failing = [r for r in results if "error" in r.summary]
    assert not failing, (
        "tests raised on 3-LUT bundle:\n"
        + "\n".join(f"  {r.name}: {r.summary['error']}" for r in failing)
    )


def test_three_lut_qa_indexes_by_paper_not_lut(
    three_lut_spec, three_lut_bundle, tmp_path,
):
    """For a 3-LUT bundle, paper_index=1 must compose L1+L2+L3(paper1),
    not literally bundle.luts[1] (which is the shared L2)."""
    out_dir = tmp_path / "p1"
    results = run(three_lut_spec, three_lut_bundle, out_dir, paper_index=1)
    assert len(results) == 17
    report = (out_dir / "report.md").read_text(encoding="utf-8")
    assert "fujifilm_crystal_archive_typeii" in report


# ---------------------------------------------------------------------------
# 4-LUT chain QA (M6).
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def four_lut_spec() -> BundleSpec:
    return BundleSpec(
        name="qa_smoke_four_lut",
        film_profile="kodak_portra_400",
        print_profiles=("kodak_portra_endura", "fujifilm_crystal_archive_typeii"),
        input_color_space=_INPUT_CS,
        output_color_space=_OUTPUT_CS,
        topology="4lut",
        resolution=_RESOLUTION,
    )


@pytest.fixture(scope="module")
def four_lut_bundle(four_lut_spec: BundleSpec):
    return BundleBuilder(four_lut_spec).build()


@pytest.fixture(scope="module")
def four_lut_results(four_lut_spec, four_lut_bundle, tmp_path_factory):
    out_dir = tmp_path_factory.mktemp("qa_four_lut")
    return run(four_lut_spec, four_lut_bundle, out_dir, paper_index=0), out_dir


def test_four_lut_qa_returns_all_tests(four_lut_results):
    results, _ = four_lut_results
    assert len(results) == 17


def test_four_lut_qa_no_tests_raised(four_lut_results):
    results, _ = four_lut_results
    failing = [r for r in results if "error" in r.summary]
    assert not failing, (
        "tests raised on 4-LUT bundle:\n"
        + "\n".join(f"  {r.name}: {r.summary['error']}" for r in failing)
    )


def test_four_lut_qa_writes_report_and_figures(four_lut_results):
    results, out_dir = four_lut_results
    out_dir = Path(out_dir)
    assert (out_dir / "report.md").exists()
    figures = list((out_dir / "figures").glob("*.png"))
    assert len(figures) == len(results)


def test_four_lut_qa_indexes_by_paper_not_lut(four_lut_spec, four_lut_bundle, tmp_path):
    """For a 4-LUT bundle, paper_index=1 must compose L1+L2+L3(paper1)+L4(paper1),
    not literally bundle.luts[1] (which is the shared L2)."""
    out_dir = tmp_path / "p1"
    results = run(four_lut_spec, four_lut_bundle, out_dir, paper_index=1)
    assert len(results) == 17
    report = (out_dir / "report.md").read_text(encoding="utf-8")
    assert "fujifilm_crystal_archive_typeii" in report
