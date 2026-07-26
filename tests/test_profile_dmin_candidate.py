import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from spektrafilm.profiles.io import profile_from_dict


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "reports"
    / "profile-measurement-basis-evaluation.py"
)
SPEC = importlib.util.spec_from_file_location("profile_measurement_basis_evaluation", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
EVALUATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EVALUATION)


def test_resample_gs0_dmin_changes_only_shared_finite_cmy_support():
    profile_wavelengths = np.arange(380.0, 421.0, 5.0)
    current_base = np.full_like(profile_wavelengths, 0.1)
    channel_density = np.full((len(profile_wavelengths), 3), np.nan)
    shared_support = (profile_wavelengths >= 385.0) & (profile_wavelengths <= 415.0)
    channel_density[shared_support] = 1.0
    measured_wavelengths = np.arange(380.0, 421.0, 10.0)
    measured_dmin = np.array([1.0, 0.55, 0.2, 0.08, 0.04])

    candidate, actual_support, interpolation = (
        EVALUATION._resample_gs0_dmin_to_profile_grid(
            profile_wavelengths,
            current_base,
            channel_density,
            measured_wavelengths,
            measured_dmin,
        )
    )

    np.testing.assert_array_equal(actual_support, shared_support)
    np.testing.assert_allclose(candidate[~shared_support], current_base[~shared_support])
    for wavelength in (390.0, 400.0, 410.0):
        profile_index = np.flatnonzero(profile_wavelengths == wavelength)[0]
        measured_index = np.flatnonzero(measured_wavelengths == wavelength)[0]
        assert candidate[profile_index] == pytest.approx(measured_dmin[measured_index])
    assert np.all(np.isfinite(candidate))
    assert np.all(candidate >= 0.0)
    assert interpolation["shared_support_point_count"] == 7
    assert interpolation["shared_support_range_nm"] == [385.0, 415.0]
    assert interpolation["outside_shared_support"] == (
        "retained from bundled base_density"
    )


def test_resample_gs0_dmin_rejects_incomplete_wavelength_coverage():
    profile_wavelengths = np.arange(380.0, 421.0, 5.0)
    current_base = np.full_like(profile_wavelengths, 0.1)
    channel_density = np.ones((len(profile_wavelengths), 3))

    with pytest.raises(ValueError, match="does not cover"):
        EVALUATION._resample_gs0_dmin_to_profile_grid(
            profile_wavelengths,
            current_base,
            channel_density,
            np.arange(390.0, 411.0, 10.0),
            np.array([0.5, 0.2, 0.1]),
        )


def test_candidate_payload_is_non_default_and_loadable(tmp_path):
    measured_wavelengths = np.arange(380.0, 781.0, 10.0)
    measured_dmin = 0.04 + 0.9 * np.exp(-((measured_wavelengths - 380.0) / 22.0))

    payload, summary = EVALUATION._build_gs0_dmin_candidate_payload(
        "fujifilm_provia_100f",
        "F240222",
        measured_wavelengths,
        measured_dmin,
        "0" * 64,
    )
    candidate = profile_from_dict(payload)

    assert candidate.info.stock == "fujifilm_provia_100f"
    assert summary["candidate_id"] == (
        "fujifilm_provia_100f_gs0_dmin_candidate"
    )
    assert candidate.metadata.provenance.measurement_status == "partial-instrument-data"
    base_provenance = candidate.metadata.provenance.fields["base_density"]
    assert base_provenance.origin == "published-measurement"
    assert base_provenance.status == "reconstructed"
    assert "COLORAID_F240222_GS0_DMIN" in base_provenance.sources
    assert "do not redistribute" in candidate.metadata.license
    assert summary["default_profile_modified"] is False
    assert summary["field_changed"] == "base_density"
    assert summary["changed_point_count"] == 67
    assert summary["unchanged_point_count"] == 14

    output = EVALUATION._write_candidate_payload(
        payload,
        tmp_path,
        candidate_id=summary["candidate_id"],
    )
    output_path = Path(output["path"])
    assert output_path.parent == tmp_path
    assert output_path.name == "fujifilm_provia_100f_gs0_dmin_candidate.json"
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert written["info"]["stock"] == candidate.info.stock
    assert len(output["sha256"]) == 64


def test_linear_candidate_changes_only_interpolation_and_keeps_real_stock():
    measured_wavelengths = np.arange(380.0, 781.0, 10.0)
    measured_dmin = 0.04 + 0.9 * np.exp(-((measured_wavelengths - 380.0) / 22.0))

    pchip_payload, _ = EVALUATION._build_gs0_dmin_candidate_payload(
        "fujifilm_provia_100f",
        "F240222",
        measured_wavelengths,
        measured_dmin,
        "0" * 64,
    )
    linear_payload, linear_summary = EVALUATION._build_gs0_dmin_candidate_payload(
        "fujifilm_provia_100f",
        "F240222",
        measured_wavelengths,
        measured_dmin,
        "0" * 64,
        interpolation="linear",
    )

    assert linear_payload["info"]["stock"] == "fujifilm_provia_100f"
    assert linear_summary["candidate_id"].endswith("_gs0_dmin_linear_candidate")
    assert linear_summary["interpolation"]["method"] == "linear"
    assert linear_payload["data"]["base_density"] != pchip_payload["data"]["base_density"]
    assert (
        "linear-10-nm-to-5-nm"
        in linear_payload["metadata"]["provenance"]["fields"]["base_density"][
            "transformations"
        ]
    )


def test_runtime_candidate_validation_preserves_stock_parameters_and_is_finite():
    measured_wavelengths = np.arange(380.0, 781.0, 10.0)
    measured_dmin = 0.04 + 0.9 * np.exp(-((measured_wavelengths - 380.0) / 22.0))
    bundled_path = (
        EVALUATION.PROFILE_DIR / "fujifilm_provia_100f.json"
    )
    bundled = json.loads(bundled_path.read_text(encoding="utf-8"))
    pchip, _ = EVALUATION._build_gs0_dmin_candidate_payload(
        "fujifilm_provia_100f",
        "F240222",
        measured_wavelengths,
        measured_dmin,
        "0" * 64,
    )
    linear, _ = EVALUATION._build_gs0_dmin_candidate_payload(
        "fujifilm_provia_100f",
        "F240222",
        measured_wavelengths,
        measured_dmin,
        "0" * 64,
        interpolation="linear",
    )

    result = EVALUATION._evaluate_runtime_candidates(
        "fujifilm_provia_100f",
        bundled,
        pchip,
        linear,
    )

    assert result["patch_count"] == 96
    assert result["neutral_patch_count"] == 32
    assert result["stock_specific_coupler_parameters_preserved"] is True
    assert result["pchip_repeat_max_absolute_difference"] == pytest.approx(0.0)
    assert all(
        profile_result["all_arrays_finite"]
        for profile_result in result["profiles"].values()
    )
    assert all(
        profile_result["neutral_ramp_monotonic_non_decreasing"]
        for profile_result in result["profiles"].values()
    )
    assert (
        result["differences"]["pchip_to_linear_interpolation"]
        ["route_linear_rgb_max_absolute_difference"]
        > 0.0
    )


def test_metric_improvement_percent_uses_lower_is_better():
    baseline = {
        "density_rmse_D": 2.0,
        "transmittance_rmse_percentage_points": 4.0,
        "delta_e_2000_median": 6.0,
        "delta_e_2000_mean": 8.0,
        "delta_e_2000_p95": 10.0,
    }
    candidate = {name: value / 2.0 for name, value in baseline.items()}

    improvement = EVALUATION._metric_improvement_percent(baseline, candidate)

    assert set(improvement) == set(baseline)
    assert all(value == pytest.approx(50.0) for value in improvement.values())
