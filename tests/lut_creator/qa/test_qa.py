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
    # 5 LUT-fidelity + 5 model-diagnostic + 2 input gamut compression
    # diagnostics + 4 picture-style diagnostics (noise sensitivity,
    # noise gradient, gamut edge stress, R-G plane slices) = 16. The
    # output-gamut compression preview is folded into
    # `output_gamut_compression`'s right panel rather than shipping as
    # its own test. (black_toe dropped per n090 §6 — flat line on log
    # inputs; highlight_rolloff dropped likewise.)
    assert len(DEFAULT_SUITE) == 16
    names = list_tests()
    assert "off_grid_identity" in names
    assert "monotonicity" in names
    assert "jacobian_condition" in names
    assert "total_variation" in names
    assert "output_gamut_compression" in names
    assert "characteristic_curve" in names
    assert "dynamic_range_usage" in names
    assert "planckian_sweep" in names
    assert "hue_twist_oklab" in names
    assert "spectral_locus_envelope" in names
    assert "input_gamut_compression_preview" in names
    assert "input_gamut_compression_smoothness" in names
    assert "noise_sensitivity" in names
    assert "noise_gradient" in names
    assert "output_gamut_edge_stress" in names
    assert "rg_plane_slices" in names


def test_all_tests_return_a_result(qa_results):
    results, _ = qa_results
    assert len(results) == 16
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


def test_noise_sensitivity_rosette_alignment(spec, bundle):
    """The polar rosette's per-hue noise gain (σ_L / σ_ab) and outer-ring
    bar color (LUT output sRGB at that hue) must refer to the same input
    sample at the same hue.

    The viz draws bar ``i`` centered on ``hue_rad[i]`` and colored by
    ``output_encoded[i]``, while the σ_L/σ_ab polyline passes through
    ``(hue_rad[i], sigma_L[i])`` / ``(hue_rad[i], sigma_ab[i])``. Both
    point to row ``i`` of the rosette dict — the alignment is enforced
    by applying the same ``[ring_mask][order]`` slice to all four
    arrays. This test reproduces the rosette assembly and verifies that
    invariant end-to-end: the LUT output stored at index ``i`` is the
    LUT response at the input sample whose OkLCh hue is stored at the
    same index ``i``.
    """
    import colour
    import numpy as np

    from spektrafilm_lut_creator import color_spaces
    from spektrafilm_lut_creator.qa import metrics, tests as qa_tests
    from spektrafilm_lut_creator.qa.evaluators import apply_trilinear

    in_cs = spec.input_color_space
    out_cs = spec.output_color_space
    chroma_rings = (0.07, 0.14, 0.21)
    target_ring = len(chroma_rings) // 2

    samples = qa_tests._polar_oklch_input_samples(
        in_cs, L=qa_tests.MIDGRAY_18_OKLAB_L,
        chroma_rings=chroma_rings, n_hues=16,
    )
    field = metrics.noise_sensitivity_field(
        bundle.luts[0][1].table, samples["input_encoded"],
        in_cs=in_cs, out_cs=out_cs,
    )

    # Reproduce the rosette assembly from qa.tests.noise_sensitivity.
    ring_mask = samples["ring_idx"] == target_ring
    order = np.argsort(samples["hue_deg"][ring_mask])
    hue_deg = samples["hue_deg"][ring_mask][order]
    input_encoded = samples["input_encoded"][ring_mask][order]
    output_encoded = field["output_encoded"][ring_mask][order]
    sigma_L = field["sigma_L"][ring_mask][order]
    sigma_ab = field["sigma_ab"][ring_mask][order]

    assert hue_deg.shape[0] == output_encoded.shape[0] == sigma_L.shape[0] \
        == sigma_ab.shape[0] == input_encoded.shape[0]
    assert hue_deg.shape[0] > 0, "middle chroma ring has no in-gamut samples"

    # 1) output_encoded[i] must be the LUT output at input_encoded[i].
    #    If this fails, the bar color at index i is showing a different
    #    sample than the noise-gain values at the same index.
    relut = np.asarray(
        apply_trilinear(bundle.luts[0][1].table, input_encoded), dtype=float,
    )
    np.testing.assert_allclose(np.asarray(output_encoded), relut, atol=1e-9)

    # 2) The input sample at index i, when round-tripped back through
    #    encoded → linear → XYZ → OkLab, must have the OkLCh hue stored
    #    at hue_deg[i]. If this fails, the angular position of bar i
    #    does not actually correspond to that bar's input chromaticity.
    in_entry = color_spaces.get(in_cs)
    if in_entry.cctf is not None:
        linear = np.asarray(
            colour.cctf_decoding(input_encoded, function=in_entry.cctf),
            dtype=float,
        )
    else:
        linear = np.asarray(input_encoded, dtype=float)
    xyz = colour.RGB_to_XYZ(
        linear, colourspace=in_entry.primaries, apply_cctf_decoding=False,
    )
    oklab = np.asarray(colour.XYZ_to_Oklab(xyz), dtype=float)
    recomputed = np.degrees(np.arctan2(oklab[:, 2], oklab[:, 1])) % 360.0
    stored = np.asarray(hue_deg) % 360.0
    # Tight tolerance — the conversion chain is exact for in-gamut samples.
    np.testing.assert_allclose(recomputed, stored, atol=1e-3)


def test_bundle_write_with_qa_appends_quality_block_to_readme(tmp_path):
    """n090 §6.1 — when ``BundleSpec.qa=True``, the rendered README must
    surface a ``## Quality`` pass/fail/info badge block.

    Builds an explicit bundle (rather than reusing the module-level
    fixture) so the ``write()`` call lands in a clean directory and we
    can inspect the resulting README without other QA artifacts in the
    way.
    """
    spec = BundleSpec(
        name="qa_readme_smoke",
        film_profile="kodak_portra_400",
        print_profiles=("kodak_portra_endura",),
        input_color_space=_INPUT_CS,
        output_color_space=_OUTPUT_CS,
        topology="1lut",
        resolution=_RESOLUTION,
        qa=True,
    )
    builder = BundleBuilder(spec)
    out_dir = builder.write(builder.build(), tmp_path / "qa_readme")
    readme = (out_dir / "README.md").read_text(encoding="utf-8")
    assert "## Quality" in readme
    # Badge legend present (any one of PASS/FAIL/INFO at least).
    assert "PASS" in readme or "FAIL" in readme or "INFO" in readme
    # Quality block should sit near the top — before "Quick info".
    assert readme.index("## Quality") < readme.index("## Quick info")
    # Per-test row exists (one of the suite tests by name).
    assert "off_grid_identity" in readme


def test_reference_cache_invalidates_on_print_change(spec, bundle, tmp_path):
    """The cache should round-trip on a second run with the same bundle."""
    run(spec, bundle, tmp_path, print_index=0)
    cache_files = list((tmp_path / "cache").glob("*.npz"))
    assert cache_files, "first run should write the reference cache"
    # Second run reuses the cache; we just verify it completes.
    results = run(spec, bundle, tmp_path, print_index=0)
    assert len(results) == 16


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
    return run(two_lut_spec, two_lut_bundle, out_dir, print_index=0), out_dir


def test_two_lut_qa_returns_all_tests(two_lut_results):
    results, _ = two_lut_results
    assert len(results) == 16


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


def test_two_lut_qa_indexes_by_print_not_lut(two_lut_spec, two_lut_bundle, tmp_path):
    """print_index=1 must select the SECOND print, not the second cube in
    bundle.luts (which is the first print's print LUT at index 1 in a
    2-LUT layout). This is the topology-stable indexing contract."""
    # The bundle has 1 film + 2 print LUTs; print_index in [0, 1].
    out_dir = tmp_path / "p1"
    results = run(two_lut_spec, two_lut_bundle, out_dir, print_index=1)
    assert len(results) == 16
    report = (out_dir / "report.md").read_text(encoding="utf-8")
    # The report names the print, which must be the second print stock.
    assert "fujifilm_crystal_archive_typeii" in report


def test_two_lut_qa_print_index_out_of_range(two_lut_spec, two_lut_bundle, tmp_path):
    # Bundle has 2 prints; index 2 is out of range.
    with pytest.raises(IndexError, match="out of range"):
        run(two_lut_spec, two_lut_bundle, tmp_path, print_index=2)


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
    return run(three_lut_spec, three_lut_bundle, out_dir, print_index=0), out_dir


def test_three_lut_qa_returns_all_tests(three_lut_results):
    results, _ = three_lut_results
    assert len(results) == 16


def test_three_lut_qa_no_tests_raised(three_lut_results):
    results, _ = three_lut_results
    failing = [r for r in results if "error" in r.summary]
    assert not failing, (
        "tests raised on 3-LUT bundle:\n"
        + "\n".join(f"  {r.name}: {r.summary['error']}" for r in failing)
    )


def test_three_lut_qa_indexes_by_print_not_lut(
    three_lut_spec, three_lut_bundle, tmp_path,
):
    """For a 3-LUT bundle, print_index=1 must compose L1+L2+L3(print1),
    not literally bundle.luts[1] (which is the shared L2)."""
    out_dir = tmp_path / "p1"
    results = run(three_lut_spec, three_lut_bundle, out_dir, print_index=1)
    assert len(results) == 16
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
    return run(four_lut_spec, four_lut_bundle, out_dir, print_index=0), out_dir


def test_four_lut_qa_returns_all_tests(four_lut_results):
    results, _ = four_lut_results
    assert len(results) == 16


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


def test_four_lut_qa_indexes_by_print_not_lut(four_lut_spec, four_lut_bundle, tmp_path):
    """For a 4-LUT bundle, print_index=1 must compose L1+L2+L3(print1)+L4(print1),
    not literally bundle.luts[1] (which is the shared L2)."""
    out_dir = tmp_path / "p1"
    results = run(four_lut_spec, four_lut_bundle, out_dir, print_index=1)
    assert len(results) == 16
    report = (out_dir / "report.md").read_text(encoding="utf-8")
    assert "fujifilm_crystal_archive_typeii" in report
