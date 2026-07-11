from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "benchmarks" / "benchmark_mlx_performance_reaudit.py"
SPEC = importlib.util.spec_from_file_location("benchmark_mlx_performance_reaudit", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
reaudit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reaudit)


def test_required_scenarios_cover_requested_matrix() -> None:
    assert reaudit.REQUIRED_SCENARIOS == (
        "scan-only",
        "film-paper",
        "film-paper-spatial-grain",
        "hdr-light-table",
        "hdr-paper",
        "preprocess-resize",
        "save-boundary",
        "hdr-export-boundary",
    )
    assert {"poisson-all-normal", "legacy-poisson", "tile-cache-release"}.issubset(reaudit.CANDIDATES)


def test_hdr_export_boundary_uses_a_headroom_capable_route() -> None:
    assert reaudit.hdr_mode_for_scenario("hdr-light-table") == "light_table"
    assert reaudit.hdr_mode_for_scenario("hdr-paper") == "paper"
    assert reaudit.hdr_mode_for_scenario("hdr-export-boundary") == "light_table"


def test_direct_input_metadata_is_exact_50mp_and_not_upscaled() -> None:
    spec = reaudit.direct_input_spec(height=6120, width=8160, seed=20260710)

    assert spec["height"] == 6120
    assert spec["width"] == 8160
    assert spec["pixels"] == 49_939_200
    assert spec["generation"] == "direct_deterministic_linear_rgb"
    assert spec["upscaled"] is False
    assert spec["real_50mp_raw"] is False


def test_deterministic_rgb_is_reproducible_float32() -> None:
    first = reaudit.make_deterministic_rgb(13, 17, seed=20260710, chunk_rows=4)
    second = reaudit.make_deterministic_rgb(13, 17, seed=20260710, chunk_rows=7)
    changed = reaudit.make_deterministic_rgb(13, 17, seed=20260711, chunk_rows=4)

    assert first.shape == (13, 17, 3)
    assert first.dtype == np.float32
    np.testing.assert_array_equal(first, second)
    assert not np.array_equal(first, changed)
    assert np.isfinite(first).all()


def test_sample_summary_separates_cold_and_hot_and_reports_median_min_max() -> None:
    summary = reaudit.summarize_samples(
        [
            {"phase": "cold", "wall_seconds": 9.0},
            {"phase": "hot", "wall_seconds": 4.0},
            {"phase": "hot", "wall_seconds": 2.0},
            {"phase": "hot", "wall_seconds": 3.0},
        ]
    )

    assert summary["cold"]["runs"] == 1
    assert summary["cold"]["median_seconds"] == 9.0
    assert summary["hot"] == {
        "runs": 3,
        "median_seconds": 3.0,
        "min_seconds": 2.0,
        "max_seconds": 4.0,
    }


def test_memory_snapshot_keeps_overlapping_counters_separate() -> None:
    snapshot = reaudit.memory_snapshot(
        mlx_active_bytes=100,
        mlx_peak_bytes=200,
        mlx_cache_bytes=300,
        rss_bytes=400,
        physical_footprint_bytes=500,
        physical_footprint_peak_bytes=600,
    )

    assert snapshot == {
        "mlx_active_bytes": 100,
        "mlx_peak_bytes": 200,
        "mlx_cache_bytes": 300,
        "rss_bytes": 400,
        "physical_footprint_bytes": 500,
        "physical_footprint_peak_bytes": 600,
        "counters_overlap": True,
        "combined_total_bytes": None,
    }


def test_parse_footprint_output_reads_current_and_peak() -> None:
    output = """
    demo [42]: 64-bit    Footprint: 1.25 GB (16384 bytes per page)
    Auxiliary data:
        phys_footprint: 1.20 GB
        phys_footprint_peak: 1.50 GB
    """

    parsed = reaudit.parse_footprint_output(output)

    assert parsed["physical_footprint_bytes"] == int(1.20 * 1024**3)
    assert parsed["physical_footprint_peak_bytes"] == int(1.50 * 1024**3)


def test_concurrent_footprint_peak_does_not_sum_nonconcurrent_process_peaks() -> None:
    sampled_peak, reported_upper_bound = reaudit.update_footprint_peaks(
        sampled_peak_bytes=700,
        reported_peak_upper_bound_bytes=900,
        current_tree_bytes=800,
        summed_process_peak_bytes=1_400,
    )

    assert sampled_peak == 800
    assert reported_upper_bound == 1_400


def test_parse_swap_and_memory_pressure_outputs() -> None:
    swap = reaudit.parse_swap_usage(
        "vm.swapusage: total = 2048.00M  used = 1031.50M  free = 1016.50M  (encrypted)"
    )
    pressure = reaudit.parse_memory_pressure(
        "The system has 17179869184 bytes.\nSystem-wide memory free percentage: 63%"
    )

    assert swap["used_bytes"] == int(1031.50 * 1024**2)
    assert swap["free_bytes"] == int(1016.50 * 1024**2)
    assert pressure["free_percent"] == 63.0
    assert pressure["level"] == "normal"


def test_swap_activity_requires_repeated_growth_before_calling_it_thrashing() -> None:
    mib = 1024**2
    one_jump = reaudit.classify_swap_activity(
        start_used_bytes=1_000 * mib,
        samples=[1_000 * mib, 1_800 * mib, 1_800 * mib, 1_800 * mib],
    )
    repeated = reaudit.classify_swap_activity(
        start_used_bytes=1_000 * mib,
        samples=[1_000 * mib, 1_400 * mib, 2_000 * mib, 2_000 * mib],
    )

    assert one_jump["swap_growth_bytes"] == 800 * mib
    assert one_jump["swap_thrashing"] is False
    assert one_jump["short_swap"] is True
    assert repeated["swap_thrashing"] is True
    assert repeated["short_swap"] is False


def test_classify_subprocess_exit_preserves_failures() -> None:
    assert reaudit.classify_subprocess_exit(returncode=0, timed_out=False, stderr="") == "ok"
    assert reaudit.classify_subprocess_exit(returncode=-9, timed_out=False, stderr="") == "system-kill"
    assert reaudit.classify_subprocess_exit(returncode=1, timed_out=False, stderr="out of memory") == "oom"
    assert reaudit.classify_subprocess_exit(returncode=1, timed_out=False, stderr="traceback") == "error"
    assert reaudit.classify_subprocess_exit(returncode=None, timed_out=True, stderr="") == "timeout"


def test_safety_abort_reason_stops_after_memory_or_swap_risk() -> None:
    assert reaudit.safety_abort_reason({"status": "ok", "swap_thrashing": False}) is None
    assert reaudit.safety_abort_reason({"status": "memory-guard"}) == "memory-guard"
    assert reaudit.safety_abort_reason({"status": "ok", "critical_pressure": True}) == "critical-pressure"
    assert reaudit.safety_abort_reason({"status": "ok", "swap_thrashing": True}) == "swap-thrashing"


def test_default_guard_stays_below_the_pass_acceptance_ceiling() -> None:
    assert reaudit.parse_args([]).max_footprint_gib == 10.5


def test_safety_abort_marks_every_unrun_matrix_cell() -> None:
    results = {"baseline": {"scan-only": {"status": "memory-guard"}}}

    reaudit.mark_unrun_scenarios(
        results,
        candidates=("baseline", "stable-compile-cache"),
        scenarios=("scan-only", "hdr-paper"),
        blocked_by="baseline/scan-only",
        reason="memory-guard",
    )

    assert results["baseline"]["scan-only"]["status"] == "memory-guard"
    assert results["baseline"]["hdr-paper"]["status"] == "not-run-safety-abort"
    assert results["stable-compile-cache"]["scan-only"]["blocked_by"] == "baseline/scan-only"
    assert results["stable-compile-cache"]["hdr-paper"]["parity_ok"] is False


def test_supplemental_summary_keeps_decision_metrics_and_drops_pressure_samples() -> None:
    payload = {
        "head_sha": "abc",
        "input": {"pixels": 12},
        "verdict": {"level": "PASS"},
        "scenarios": {
            "baseline": {
                "scan-only": {
                    "status": "ok",
                    "parity_ok": True,
                    "physical_footprint_peak_bytes": 123,
                    "rss_tree_peak_bytes": 456,
                    "timing_summary": {"hot": {"median_seconds": 1.5}},
                    "prototype_state": {},
                    "external_measurement": {
                        "swap_growth_bytes": 0,
                        "minimum_memory_free_percent": 70.0,
                        "pressure_samples": [{"free_percent": 70.0}],
                    },
                }
            }
        },
        "parity": {},
    }

    summary = reaudit.summarize_supplemental_payload(payload)

    scenario = summary["scenarios"]["baseline"]["scan-only"]
    assert scenario["physical_footprint_peak_bytes"] == 123
    assert scenario["timing_summary"]["hot"]["median_seconds"] == 1.5
    assert "pressure_samples" not in scenario


def test_16gb_verdict_thresholds_and_fail_conditions() -> None:
    gib = 1024**3
    pass_case = reaudit.classify_16gb_verdict(
        [{"status": "ok", "physical_footprint_peak_bytes": 11 * gib, "critical_pressure": False,
          "swap_thrashing": False, "exceptional_fallback": False, "parity_ok": True}]
    )
    conditional = reaudit.classify_16gb_verdict(
        [{"status": "ok", "physical_footprint_peak_bytes": int(12.5 * gib), "critical_pressure": False,
          "swap_thrashing": False, "exceptional_fallback": False, "parity_ok": True}]
    )
    short_swap = reaudit.classify_16gb_verdict(
        [{"status": "ok", "physical_footprint_peak_bytes": 8 * gib, "critical_pressure": False,
          "swap_thrashing": False, "short_swap": True, "exceptional_fallback": False, "parity_ok": True}]
    )
    failed = reaudit.classify_16gb_verdict(
        [{"status": "ok", "physical_footprint_peak_bytes": int(13.1 * gib), "critical_pressure": False,
          "swap_thrashing": False, "exceptional_fallback": False, "parity_ok": True}]
    )
    killed = reaudit.classify_16gb_verdict(
        [{"status": "system-kill", "physical_footprint_peak_bytes": None, "critical_pressure": True,
          "swap_thrashing": True, "exceptional_fallback": False, "parity_ok": False}]
    )

    assert pass_case["level"] == "PASS"
    assert conditional["level"] == "CONDITIONAL"
    assert short_swap == {
        "level": "CONDITIONAL",
        "max_physical_footprint_bytes": 8 * gib,
        "reasons": ["short swap growth"],
    }
    assert failed["level"] == "FAIL"
    assert killed["level"] == "FAIL"


def _closure_factory(threshold: float):
    def chain(value):
        return value + threshold

    return chain


def test_stable_compile_key_reuses_code_location_but_tracks_closure_values() -> None:
    first = _closure_factory(0.1)
    same = _closure_factory(0.1)
    changed = _closure_factory(0.2)
    image = np.zeros((8, 9, 3), dtype=np.float32)

    key_first = reaudit.stable_compile_key("chain", first, image)
    key_same = reaudit.stable_compile_key("chain", same, image)
    key_changed = reaudit.stable_compile_key("chain", changed, image)

    assert key_first == key_same
    assert key_first != key_changed


def test_poisson_all_normal_prototype_preserves_rng_bytes() -> None:
    pytest.importorskip("mlx.core")
    from spektrafilm.gpu.mlx_backend import MlxBackend
    from spektrafilm.gpu.kernels import grain as grain_kernels

    try:
        backend = MlxBackend(precision="float32")
    except Exception as exc:
        pytest.skip(f"MLX Metal backend unavailable: {exc}")

    high = backend.mx.full((7, 11), np.float32(12.5), dtype=backend.mx.float32)
    mixed = backend.mx.array([[2.0, 12.5], [9.0, 20.0]], dtype=backend.mx.float32)
    baseline_high = backend.to_numpy(grain_kernels.fast_poisson_backend(high, backend, seed=41))
    baseline_mixed = backend.to_numpy(grain_kernels.fast_poisson_backend(mixed, backend, seed=42))

    restore, state = reaudit.install_poisson_all_normal_prototype()
    try:
        candidate_high = backend.to_numpy(grain_kernels.fast_poisson_backend(high, backend, seed=41))
        candidate_mixed = backend.to_numpy(grain_kernels.fast_poisson_backend(mixed, backend, seed=42))
    finally:
        restore()

    np.testing.assert_array_equal(candidate_high, baseline_high)
    np.testing.assert_array_equal(candidate_mixed, baseline_mixed)
    assert state == {"calls": 2, "all_normal_fast_path": 1, "delegated": 1}


def test_tile_cache_release_prototype_exposes_bounded_cache_hook() -> None:
    pytest.importorskip("mlx.core")
    from spektrafilm.gpu.mlx_backend import MlxBackend

    original = getattr(MlxBackend, "clear_cache", None)
    restore, state = reaudit.install_tile_cache_release_prototype()
    try:
        backend = MlxBackend(precision="float32")
        backend.clear_cache()
        assert state["calls"] == 1
    finally:
        restore()

    assert getattr(MlxBackend, "clear_cache", None) is original


def test_legacy_poisson_reference_matches_production_for_high_mixed_and_special_values() -> None:
    pytest.importorskip("mlx.core")
    from spektrafilm.gpu.mlx_backend import MlxBackend
    from spektrafilm.gpu.kernels import grain as grain_kernels

    try:
        backend = MlxBackend(precision="float32")
    except Exception as exc:
        pytest.skip(f"MLX Metal backend unavailable: {exc}")

    cases = (
        (backend.mx.full((7, 11), np.float32(12.5), dtype=backend.mx.float32), 41),
        (backend.asarray(np.array([[2.0, 12.5], [9.0, 20.0]], dtype=np.float32)), 42),
        (backend.asarray(np.array([[-1.0, np.nan, np.inf, 10.0]], dtype=np.float32)), 43),
        (backend.mx.zeros((0,), dtype=backend.mx.float32), 44),
    )
    expected = [backend.to_numpy(grain_kernels.fast_poisson_backend(values, backend, seed=seed)) for values, seed in cases]

    restore, state = reaudit.install_legacy_poisson_prototype()
    try:
        actual = [backend.to_numpy(grain_kernels.fast_poisson_backend(values, backend, seed=seed)) for values, seed in cases]
    finally:
        restore()

    for candidate, baseline in zip(actual, expected):
        np.testing.assert_array_equal(candidate, baseline)
    assert state == {"calls": 4, "mlx_legacy_calls": 4, "knuth_rounds_constructed": 240}


def test_percentile_index_plan_matches_numpy_linear_definition() -> None:
    assert reaudit.percentile_index_plan(size=1, percentile=99.9) == (0, 0, 0.0)
    lower, upper, weight = reaudit.percentile_index_plan(size=1000, percentile=99.9)
    assert (lower, upper) == (998, 999)
    assert np.isclose(weight, 0.001)


def test_raw_overlap_estimate_is_explicit_and_not_double_counted() -> None:
    estimate = reaudit.estimate_raw_decode_overlap(
        height=6120,
        width=8160,
        mosaic_bytes_per_pixel=2,
        decoder_rgb_bytes_per_channel=2,
        spektrafilm_input_bytes_per_channel=4,
    )

    pixels = 49_939_200
    assert estimate["raw_mosaic_bytes"] == pixels * 2
    assert estimate["decoder_rgb_bytes"] == pixels * 3 * 2
    assert estimate["spektrafilm_input_bytes"] == pixels * 3 * 4
    assert estimate["conservative_simultaneous_bytes"] == pixels * (2 + 6 + 12)
    assert estimate["includes_mlx_allocator"] is False


def test_result_envelope_contains_required_machine_readable_sections() -> None:
    envelope = reaudit.result_envelope(head_sha="abc", environment={"platform": "macOS"})

    assert set(envelope) == {
        "schema_version",
        "head_sha",
        "environment",
        "input",
        "scenarios",
        "memory",
        "parity",
        "findings",
        "verdict",
        "limitations",
        "commands",
        "agent_configuration",
    }
    assert envelope["schema_version"] == 1


def test_candidate_parity_uses_export_file_hash_when_no_array_is_returned() -> None:
    scenarios = {
        "baseline": {
            "hdr-export-boundary": {
                "samples": [
                    {"phase": "hot", "output_signatures": [], "output_files": [{"path": "x.heic", "sha256": "same"}]}
                ]
            }
        },
        "candidate": {
            "hdr-export-boundary": {
                "samples": [
                    {"phase": "hot", "output_signatures": [], "output_files": [{"path": "x.heic", "sha256": "same"}]}
                ]
            }
        },
    }

    parity = reaudit._candidate_parity(scenarios)

    assert parity["candidate"]["hdr-export-boundary"]["exact_output_hash_match"] is True
