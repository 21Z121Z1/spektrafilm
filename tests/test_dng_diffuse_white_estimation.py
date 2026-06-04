from __future__ import annotations

import numpy as np

from tools.research_dng_diffuse_white_estimation import (
    RawCaptureDiagnostics,
    classify_dng_natural_hdr_eligibility,
    compute_scene_luminance_y,
    estimate_diffuse_white_from_scene,
)


def _neutral_scene(values: np.ndarray) -> np.ndarray:
    y = np.asarray(values, dtype=np.float32)
    return np.repeat(y[..., None], 3, axis=-1)


def _raw_diagnostics(
    *,
    white_level: float = 4095.0,
    clipping_fraction: float = 0.0,
    raw_p50: float = 0.18,
    raw_p95: float = 0.75,
    raw_p99: float = 0.95,
    raw_p999: float = 1.10,
) -> RawCaptureDiagnostics:
    return RawCaptureDiagnostics(
        black_level=64.0,
        white_level=white_level,
        channel_white_levels=(white_level, white_level, white_level, white_level),
        clipping_fraction=clipping_fraction,
        channel_clipping_fraction=(clipping_fraction, clipping_fraction, clipping_fraction, clipping_fraction),
        raw_p50=raw_p50,
        raw_p95=raw_p95,
        raw_p99=raw_p99,
        raw_p999=raw_p999,
        warnings=(),
    )


def test_measured_white_card_supports_verified_natural_hdr() -> None:
    scene = _neutral_scene(np.full((16, 16), 0.35, dtype=np.float32))
    scene[2:8, 2:8, :] = 1.0
    scene[12:14, 12:14, :] = 3.0
    measured_mask = np.zeros((16, 16), dtype=bool)
    measured_mask[2:8, 2:8] = True

    estimate = estimate_diffuse_white_from_scene(
        scene_rgb=scene,
        measured_mask=measured_mask,
        raw_diagnostics=_raw_diagnostics(raw_p999=3.0),
    )

    assert estimate.method == "measured_gray_or_white_card"
    assert estimate.confidence == "high"
    assert estimate.is_measured is True
    assert estimate.can_claim_natural_hdr is True
    assert estimate.recommended_mode == "natural_scene_hdr"
    assert estimate.natural_hdr_class == "natural_scene_hdr_verified"
    assert 0.99 <= estimate.value <= 1.01
    assert estimate.highlight_headroom_estimate >= 2.9


def test_low_key_scene_downgrades_instead_of_fabricating_huge_headroom() -> None:
    scene_y = np.full((32, 32), 0.025, dtype=np.float32)
    scene_y[0:2, 0:2] = 5.0

    estimate = estimate_diffuse_white_from_scene(
        scene_rgb=_neutral_scene(scene_y),
        raw_diagnostics=_raw_diagnostics(raw_p50=0.02, raw_p95=0.03, raw_p99=4.5, raw_p999=5.0),
    )

    assert estimate.confidence == "low"
    assert estimate.can_claim_natural_hdr is False
    assert estimate.recommended_mode in {"scene_derived_heuristic_hdr", "authored_hdr"}
    assert estimate.highlight_headroom_estimate <= 8.0
    assert "low-key" in " ".join(estimate.warnings)


def test_large_neutral_high_key_scene_keeps_diffuse_candidate() -> None:
    scene_y = np.full((32, 32), 0.95, dtype=np.float32)
    scene_y[:, :8] = 0.75
    scene_y[0:2, 0:2] = 1.45

    estimate = estimate_diffuse_white_from_scene(
        scene_rgb=_neutral_scene(scene_y),
        raw_diagnostics=_raw_diagnostics(raw_p50=0.8, raw_p95=0.98, raw_p99=1.20, raw_p999=1.45),
    )

    assert estimate.confidence in {"medium", "high"}
    assert estimate.recommended_mode in {"natural_scene_hdr", "scene_derived_heuristic_hdr"}
    assert estimate.value >= 0.8
    assert "large diffuse" in " ".join(estimate.assumptions + estimate.warnings)


def test_small_saturated_neon_highlights_are_not_treated_as_diffuse_white() -> None:
    scene = _neutral_scene(np.full((32, 32), 0.18, dtype=np.float32))
    scene[0:2, 0:2, :] = np.array([9.0, 0.05, 0.02], dtype=np.float32)
    scene[30:32, 30:32, :] = np.array([0.02, 0.05, 7.0], dtype=np.float32)

    estimate = estimate_diffuse_white_from_scene(
        scene_rgb=scene,
        raw_diagnostics=_raw_diagnostics(raw_p50=0.18, raw_p95=0.20, raw_p99=3.0, raw_p999=7.5),
    )

    assert estimate.confidence == "low"
    assert estimate.can_claim_natural_hdr is False
    assert estimate.recommended_mode == "scene_derived_heuristic_hdr"
    assert "emissive" in " ".join(estimate.warnings)


def test_clipped_raw_downgrades_or_refuses_natural_hdr() -> None:
    scene_y = np.linspace(0.1, 4.0, 64, dtype=np.float32).reshape(8, 8)
    estimate = estimate_diffuse_white_from_scene(
        scene_rgb=_neutral_scene(scene_y),
        raw_diagnostics=_raw_diagnostics(clipping_fraction=0.04, raw_p99=1.0, raw_p999=1.0),
    )

    assert estimate.confidence in {"low", "invalid"}
    assert estimate.can_claim_natural_hdr is False
    assert estimate.recommended_mode in {"scene_derived_heuristic_hdr", "sdr_only"}
    assert "clipped" in " ".join(estimate.warnings)


def test_creative_controls_force_authored_class_even_with_measured_white() -> None:
    scene = _neutral_scene(np.full((8, 8), 1.0, dtype=np.float32))
    scene[0, 0, :] = 3.0
    measured_mask = np.ones((8, 8), dtype=bool)
    measured_mask[0, 0] = False
    estimate = estimate_diffuse_white_from_scene(
        scene_rgb=scene,
        measured_mask=measured_mask,
        raw_diagnostics=_raw_diagnostics(raw_p999=3.0),
    )

    provenance = classify_dng_natural_hdr_eligibility(
        estimate,
        source_type="raw_dng",
        active_creative_controls=("profile_hdr_target_peak_ev", "modern_recovery_peak_budget", "path_to_white"),
    )

    assert provenance.natural_hdr_class == "authored_hdr_from_raw"
    assert provenance.can_claim_natural_hdr is False
    assert "profile_hdr_target_peak_ev" in provenance.disallowed_creative_controls
    assert "path_to_white" in provenance.disallowed_creative_controls


def test_whitelevel_is_recorded_as_sensor_saturation_not_diffuse_white() -> None:
    scene_y = np.linspace(0.05, 1.2, 100, dtype=np.float32).reshape(10, 10)
    raw = _raw_diagnostics(white_level=4095.0, raw_p50=0.20, raw_p95=0.60, raw_p99=0.95, raw_p999=1.2)

    estimate = estimate_diffuse_white_from_scene(
        scene_rgb=_neutral_scene(scene_y),
        raw_diagnostics=raw,
    )

    assert estimate.value != raw.white_level
    assert estimate.raw_metadata_summary["white_level"] == 4095.0
    assert "WhiteLevel" in " ".join(estimate.assumptions + estimate.warnings)


def test_scene_luminance_uses_recorded_linear_coefficients() -> None:
    scene = np.array([[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]], dtype=np.float32)

    state = compute_scene_luminance_y(scene, working_space="Rec.709")

    np.testing.assert_allclose(state.scene_y[0], [0.2126, 0.7152, 0.0722], rtol=1e-5, atol=1e-6)
    assert state.working_space == "Rec.709"
    assert state.luma_coefficients == (0.2126, 0.7152, 0.0722)
