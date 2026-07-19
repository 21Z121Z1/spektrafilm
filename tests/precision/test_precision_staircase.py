from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from tests.precision.staircase import (
    assess_relation,
    build_report,
    color_metrics,
    grain_statistics,
    hdr_metrics,
    load_contract,
    numeric_metrics,
    quantized_code_metrics,
    representative_rgb,
)
from tests.precision.synthetic_pipeline import (
    run_contract_case_staircases,
    run_synthetic_staircase,
)


pytestmark = pytest.mark.unit


def test_frozen_baseline_matches_contract_and_records_all_relations() -> None:
    baseline_path = Path(__file__).with_name("baseline_current_20260719.json")
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    contract = load_contract()
    assert baseline["contract_id"] == contract["contract_id"]
    assert baseline["all_contract_failures"] == []
    assert set(baseline["stage_max_abs"]) == {
        "cpu64_to_cpu32", "cpu32_to_mlx32_unfused",
        "cpu64_to_mlx32_unfused", "mlx32_unfused_to_candidate",
    }
    assert all(set(stages) == set(contract["stages"]) for stages in baseline["stage_max_abs"].values())
    assert baseline["final_output"]["mlx32_unfused_to_candidate_final_arrays_bitwise_equal"] is True
    assert baseline["hanatos_balanced_fallback_candidate"]["film_raw_float32_bitwise_equal"] is True
    assert baseline["hanatos_balanced_fallback_candidate"]["film_log_exposure_bitwise_equal"] is True
    assert baseline["hanatos_balanced_fallback_candidate"]["final_output_bitwise_equal"] is True


def test_contract_is_locked_and_covers_required_stages_samples_and_metrics() -> None:
    contract = load_contract()
    assert contract["locked_before_candidate_optimization"] is True
    assert contract["reference_paths"] == ["cpu64", "cpu32", "mlx32_unfused", "mlx32_candidate"]
    assert set(contract["stages"]) == {
        "film_raw_exposure", "film_log_exposure", "film_cmy_density", "grain_density_shared_random",
        "paper_log_exposure", "paper_cmy_density", "scan_spectral_transmittance",
        "scan_xyz", "scene_output_linear_rgb", "sdr_pre_encode", "decoded_final_sdr",
        "hdr_linear_luminance", "hdr_headroom", "gain_map", "decoded_final_hdr",
    }
    samples = contract["sample_set"]
    assert {sample["film"] for sample in samples} == {"negative", "positive"}
    assert {sample["route"] for sample in samples} == {"chemical_print", "direct_scan"}
    assert {sample["output"] for sample in samples} == {"sdr", "hdr"}
    assert {sample["grain"] for sample in samples} == {False, True}
    assert {sample["spatial"] for sample in samples} == {False, True}
    assert any(sample["shape"][1] % 8 for sample in samples)
    assert contract["relations"]["mlx32_unfused_to_candidate"]["bitwise_stages"] == [
        "decoded_final_sdr", "gain_map", "decoded_final_hdr",
    ]
    assert contract["hanatos_balanced_fallback"]["bitwise_stages"] == [
        "film_raw_float32", "film_log_exposure", "final_output",
    ]


def test_representative_input_contains_every_declared_condition() -> None:
    image, labels = representative_rgb()
    contract = load_contract()
    assert image.dtype == np.float64
    assert image.shape == labels.shape + (3,)
    assert set(contract["input_conditions"]) <= set(np.unique(labels))


def test_numeric_metrics_report_tails_ulp_location_finite_and_clipping() -> None:
    reference = np.array([[[0.0, 0.5, 1.0], [np.nan, 0.25, 0.75]]], dtype=np.float32)
    candidate = reference.copy()
    candidate[0, 0, 1] = np.nextafter(candidate[0, 0, 1], np.float32(1.0))
    candidate[0, 0, 2] = np.float32(1.01)
    labels = np.array([["near_zero_shadow", "smooth_gradient"]])
    metrics = numeric_metrics(reference, candidate, condition_labels=labels, clip_bounds=(0.0, 1.0))
    assert metrics["mean_abs"] > 0.0
    assert metrics["rms"] > 0.0
    assert metrics["p95_abs"] <= metrics["p99_abs"] <= metrics["p99_9_abs"] <= metrics["max_abs"]
    assert metrics["ulp"]["max"] > 0
    assert metrics["max_error_location"]["pixel"] == [0, 0]
    assert metrics["max_error_location"]["channel"] == 2
    assert metrics["max_error_location"]["input_condition"] == "near_zero_shadow"
    assert metrics["finite"]["reference_nan"] == metrics["finite"]["candidate_nan"] == 1
    assert metrics["finite"]["classification_mismatch"] == 0
    assert metrics["clip_classification_changes"] == 1


def test_cpu64_to_cpu32_synthetic_staircase_meets_predeclared_contract() -> None:
    contract = load_contract()
    snapshots = run_synthetic_staircase(include_mlx=False)
    report = build_report(snapshots, contract=contract)
    comparison = report["comparisons"]["cpu64_to_cpu32"]
    assert comparison["failures"] == []
    assert set(comparison["stages"]) == set(contract["stages"])


def test_mlx_unfused_and_candidate_staircase_meet_predeclared_contract() -> None:
    contract = load_contract()
    snapshots = run_synthetic_staircase(include_mlx=True)
    if "mlx32_unfused" not in snapshots:
        pytest.skip("MLX backend unavailable")
    report = build_report(snapshots, contract=contract)
    for relation in (
        "cpu32_to_mlx32_unfused",
        "cpu64_to_mlx32_unfused",
        "mlx32_unfused_to_candidate",
        "cpu64_to_candidate",
    ):
        assert report["comparisons"][relation]["failures"] == []


def test_declared_profile_route_and_output_cases_are_executed() -> None:
    from spektrafilm.profiles.io import load_profile

    contract = load_contract()
    definitions = {case["id"]: case for case in contract["sample_set"]}
    case_snapshots = run_contract_case_staircases(contract, include_mlx=True)
    assert set(case_snapshots) == set(definitions)

    for case_id, snapshots in case_snapshots.items():
        case = definitions[case_id]
        profile = load_profile(case["profile"])
        assert profile.is_negative is (case["film"] == "negative")
        assert profile.is_positive is (case["film"] == "positive")
        expected_shape = tuple(case["shape"])
        cpu64_stages = snapshots["cpu64"]
        assert cpu64_stages["film_log_exposure"].values.shape[:2] == expected_shape
        assert ("paper_log_exposure" in cpu64_stages) is (case["route"] == "chemical_print")
        assert ("grain_density_shared_random" in cpu64_stages) is bool(case["grain"])
        assert ("gain_map" in cpu64_stages) is (case["output"] == "hdr")

        if "mlx32_unfused" not in snapshots:
            continue
        report = build_report(snapshots, contract=contract)
        for comparison in report["comparisons"].values():
            assert comparison["failures"] == []


def test_terminal_color_quantization_and_hdr_metrics_are_reportable() -> None:
    snapshots = run_synthetic_staircase(include_mlx=False)
    reference = snapshots["cpu64"]
    candidate = snapshots["cpu32"]
    contract = load_contract()["final_output"]
    color = color_metrics(reference["decoded_final_sdr"].values, candidate["decoded_final_sdr"].values)
    codes = quantized_code_metrics(
        reference["decoded_final_sdr"].values,
        candidate["decoded_final_sdr"].values,
        bit_depth=contract["sdr_bit_depth"],
    )
    gain_codes = quantized_code_metrics(
        reference["gain_map"].values,
        candidate["gain_map"].values,
        bit_depth=contract["gain_map_bit_depth"],
    )
    hdr = hdr_metrics(
        reference["decoded_final_hdr"].values,
        candidate["decoded_final_hdr"].values,
        diffuse_white_nits=contract["hdr_diffuse_white_nits"],
        reference_headroom=float(reference["hdr_headroom"].values[0]),
        candidate_headroom=float(candidate["hdr_headroom"].values[0]),
    )
    assert set(color["partitions"]) == {"shadow", "midtone", "highlight", "high_saturation"}
    assert color["delta_e00"]["p99"] <= contract["delta_e00_p99_budget"]
    assert color["delta_e00"]["max"] <= contract["delta_e00_max_budget"]
    assert codes["max_code_difference"] <= contract["sdr_code_value_budget"]
    assert gain_codes["max_code_difference"] <= contract["gain_map_code_value_budget"]
    assert hdr["nits"]["p99"] <= contract["hdr_nits_p99_budget"]
    assert hdr["nits"]["max"] <= contract["hdr_nits_max_budget"]


def test_shared_random_grain_math_is_in_staircase_and_native_stats_are_complete() -> None:
    snapshots = run_synthetic_staircase(include_mlx=False)
    grain64 = snapshots["cpu64"]["grain_density_shared_random"].values
    grain32 = snapshots["cpu32"]["grain_density_shared_random"].values
    metrics = numeric_metrics(grain64, grain32, clip_bounds=(0.0, 3.2))
    failures = assess_relation(
        {"grain_density_shared_random": metrics},
        relation="cpu64_to_cpu32",
        contract=load_contract(),
    )
    assert failures == []

    exposure = np.linspace(0.0, 1.0, grain32.shape[0] * grain32.shape[1], dtype=np.float32).reshape(grain32.shape[:2])
    stats = grain_statistics(grain32, exposure=exposure)
    assert len(stats["mean"]) == 3
    assert len(stats["variance"]) == 3
    assert set(stats["quantiles"]) == {"0.01", "0.05", "0.5", "0.95", "0.99"}
    assert len(stats["autocorrelation_x"]) == 3
    assert np.asarray(stats["channel_correlation"]).shape == (3, 3)
    assert len(stats["exposure_bins"]) == 4
    assert len(stats["normalized_power_spectrum"]) == 8
    assert np.sum(stats["normalized_power_spectrum"]) == pytest.approx(1.0)
