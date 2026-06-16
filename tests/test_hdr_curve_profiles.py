from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from spektrafilm.utils import hdr_curve_profiles


def _assert_finite_tree(value) -> None:
    if isinstance(value, dict):
        for child in value.values():
            _assert_finite_tree(child)
        return
    if isinstance(value, list):
        for child in value:
            _assert_finite_tree(child)
        return
    if isinstance(value, float):
        assert math.isfinite(value)


def test_synthetic_increasing_curve_is_safe_and_exports_finite_defaults() -> None:
    scene_y = np.array([0.125, 0.184, 0.5, 1.0, 2.0, 4.0, 8.0], dtype=np.float32)
    y = np.array([0.05, 0.10, 0.45, 0.83, 0.90, 0.94, 0.955], dtype=np.float32)
    rgb = np.repeat(y[:, None], 3, axis=1)

    sample = hdr_curve_profiles.build_curve_profile_sample(
        film="synthetic_increasing",
        paper="test_paper",
        scene_y=scene_y,
        output_rgb=rgb,
    )

    assert sample["version"] == 2
    assert sample["metrics"]["polarity"] == "increasing"
    assert sample["metrics"]["midtone_slope"] > 0.0
    assert sample["metrics"]["highlight_slope"] > 0.0
    assert sample["metrics"]["safe_for_profile_aware_hdr"] is True
    assert 1.0 in sample["input_domain"]["scene_y"]
    _assert_finite_tree(sample)


def test_synthetic_decreasing_curve_is_not_safe_for_increasing_hdr_mapping() -> None:
    scene_y = np.array([0.125, 0.184, 0.5, 1.0, 2.0, 4.0, 8.0], dtype=np.float32)
    y = np.array([0.95, 0.90, 0.70, 0.55, 0.35, 0.20, 0.10], dtype=np.float32)
    rgb = np.repeat(y[:, None], 3, axis=1)

    sample = hdr_curve_profiles.build_curve_profile_sample(
        film="synthetic_decreasing",
        paper="test_paper",
        scene_y=scene_y,
        output_rgb=rgb,
    )

    assert sample["metrics"]["polarity"] == "decreasing"
    assert sample["metrics"]["safe_for_profile_aware_hdr"] is False


def test_curve_profile_database_schema_and_loader_roundtrip(tmp_path: Path) -> None:
    scene_y = np.array([0.125, 0.184, 0.5, 1.0, 2.0, 4.0, 8.0], dtype=np.float32)
    y = np.array([0.05, 0.10, 0.45, 0.83, 0.90, 0.94, 0.955], dtype=np.float32)
    sample = hdr_curve_profiles.build_curve_profile_sample(
        film="kodak_portra_400",
        paper="kodak_portra_endura",
        scene_y=scene_y,
        output_rgb=np.repeat(y[:, None], 3, axis=1),
    )

    summary_path = hdr_curve_profiles.write_curve_profile_database([sample], tmp_path)
    summary = json.loads(summary_path.read_text())

    assert summary["version"] == 2
    assert len(summary["profiles"]) == 1
    entry = summary["profiles"][0]
    for key in (
        "film",
        "paper",
        "sample",
        "polarity",
        "safe_for_profile_aware_hdr",
        "look_diffuse_white_y",
        "defaults",
    ):
        assert key in entry

    sample_path = tmp_path / entry["sample"]
    assert sample_path.exists()
    sample_json = json.loads(sample_path.read_text())
    assert 1.0 in sample_json["input_domain"]["scene_y"]
    _assert_finite_tree(summary)
    _assert_finite_tree(sample_json)

    profiles = hdr_curve_profiles.load_hdr_curve_profiles(tmp_path)
    profile = profiles[("kodak_portra_400", "kodak_portra_endura")]
    assert profile.route == "print_scan"
    assert profile.safe_for_profile_aware_hdr is True
    assert profile.output_rgb is not None
    assert profile.output_rgb.shape == (len(scene_y), 3)
    assert profile.defaults.safe_max_headroom >= 1.01
    np.testing.assert_allclose(
        hdr_curve_profiles.evaluate_profile_sdr_curve(profile, np.array([1.0], dtype=np.float32)),
        [profile.look_diffuse_white_y],
        atol=1e-6,
    )
    np.testing.assert_allclose(
        hdr_curve_profiles.evaluate_profile_rgb_curve(profile, np.array([1.0], dtype=np.float32)),
        [[profile.look_diffuse_white_y] * 3],
        atol=1e-6,
    )


def test_loader_tolerates_missing_or_invalid_json(tmp_path: Path) -> None:
    assert hdr_curve_profiles.load_hdr_curve_profiles(tmp_path) == {}

    (tmp_path / "curve_profiles_v2.json").write_text("{not valid json", encoding="utf-8")
    hdr_curve_profiles.load_hdr_curve_profiles.cache_clear()

    assert hdr_curve_profiles.load_hdr_curve_profiles(tmp_path) == {}


def test_repo_smoke_samples_known_runtime_profile() -> None:
    sample = hdr_curve_profiles.sample_runtime_curve_profile(
        film="kodak_portra_400",
        paper="kodak_portra_endura",
        ev_min=-2.0,
        ev_max=2.0,
        ev_step=2.0,
    )

    assert sample["film"] == "kodak_portra_400"
    assert sample["paper"] == "kodak_portra_endura"
    assert sample["route"] == "print_scan"
    assert 1.0 in sample["input_domain"]["scene_y"]
    assert 0.184 in sample["input_domain"]["scene_y"]
    assert len(sample["output"]["rgb"]) == len(sample["input_domain"]["scene_y"])
    assert sample["metrics"]["polarity"] in {"increasing", "decreasing", "nonmonotonic"}
    _assert_finite_tree(sample)


def test_film_scan_curve_profile_records_route_without_paper() -> None:
    scene_y = np.array([0.125, 0.184, 0.5, 1.0, 2.0, 4.0], dtype=np.float32)
    y = np.array([0.04, 0.08, 0.35, 0.74, 1.02, 1.34], dtype=np.float32)

    sample = hdr_curve_profiles.build_curve_profile_sample(
        film="kodak_portra_400",
        paper=None,
        route="film_scan",
        scene_y=scene_y,
        output_rgb=np.repeat(y[:, None], 3, axis=1),
    )

    assert sample["route"] == "film_scan"
    assert sample["paper"] is None
    assert sample["metrics"]["safe_for_profile_aware_hdr"] is True


def test_film_scan_runtime_sampling_forces_scan_route_and_disables_output_clip(monkeypatch) -> None:
    from spektrafilm.runtime.params_builder import init_params

    captured: dict[str, object] = {}

    class FakeSimulator:
        def __init__(self, params) -> None:
            captured["params"] = params

        def process(self, ramp_rgb: np.ndarray) -> np.ndarray:
            scene = ramp_rgb[0, :, 0].astype(np.float32)
            response = scene * np.float32(0.35) + np.float32(0.05)
            return np.repeat(response.reshape(1, -1, 1), 3, axis=2).astype(np.float32)

    monkeypatch.setattr("spektrafilm.runtime.process.Simulator", FakeSimulator)
    params = init_params(film_profile="fujifilm_provia_100f", print_profile="kodak_portra_endura")
    params.io.scan_film = False
    params.io.output_cctf_encoding = True
    params.io.output_clip_min = True
    params.io.output_clip_max = True
    params.camera.auto_exposure = True

    sample = hdr_curve_profiles.sample_runtime_film_scan_curve_profile(
        params=params,
        film="fujifilm_provia_100f",
        ev_min=0.0,
        ev_max=3.0,
        ev_step=1.0,
    )

    sampled_params = captured["params"]
    assert sampled_params.io.scan_film is True
    assert sampled_params.io.output_cctf_encoding is False
    assert sampled_params.io.output_clip_min is False
    assert sampled_params.io.output_clip_max is False
    assert sampled_params.debug.deactivate_spatial_effects is True
    assert sampled_params.debug.deactivate_stochastic_effects is True
    assert sampled_params.camera.auto_exposure is False
    assert sample["route"] == "film_scan"
    assert sample["paper"] is None
    assert max(sample["output"]["luminance_y"]) > 1.0


def test_negative_film_raw_scan_diagnostic_is_decreasing_and_not_hdr_safe() -> None:
    sample = hdr_curve_profiles.sample_runtime_film_scan_curve_profile(
        film="kodak_gold_200",
        scan_profile_kind="raw_negative_scan",
        ev_min=-2.0,
        ev_max=3.0,
        ev_step=1.0,
    )

    scene_y = np.asarray(sample["input_domain"]["scene_y"], dtype=np.float32)
    y = np.asarray(sample["output"]["luminance_y"], dtype=np.float32)
    order = np.argsort(scene_y)

    assert sample["route"] == "film_scan"
    assert sample["paper"] is None
    assert sample["profile_kind"] == "raw_negative_scan"
    assert sample["metrics"]["polarity"] == "decreasing"
    assert sample["metrics"]["safe_for_profile_aware_hdr"] is False
    assert float(y[order][-1]) < float(y[order][0])


def test_negative_film_scan_defaults_to_positive_hdr_safe_profile() -> None:
    sample = hdr_curve_profiles.sample_runtime_film_scan_curve_profile(
        film="kodak_gold_200",
        ev_min=-2.0,
        ev_max=3.0,
        ev_step=1.0,
    )

    scene_y = np.asarray(sample["input_domain"]["scene_y"], dtype=np.float32)
    y = np.asarray(sample["output"]["luminance_y"], dtype=np.float32)
    order = np.argsort(scene_y)
    sorted_y = y[order]
    highlight_y = sorted_y[scene_y[order] >= 2.0]

    assert sample["route"] == "film_scan"
    assert sample["paper"] is None
    assert sample["profile_kind"] == "positive_negative_scan"
    assert sample["negative_scan_render"]["model"] == "density_normalized_positive"
    assert sample["metrics"]["polarity"] == "increasing"
    assert sample["metrics"]["safe_for_profile_aware_hdr"] is True
    assert np.all(np.diff(sorted_y) >= -1e-5)
    assert float(sorted_y[-1]) > float(sorted_y[0])
    assert float(np.ptp(highlight_y)) > 1e-3
    assert max(sample["output"]["luminance_y"]) > 1.0


def test_positive_reversal_film_scan_is_not_negative_inverted() -> None:
    sample = hdr_curve_profiles.sample_runtime_film_scan_curve_profile(
        film="fujifilm_provia_100f",
        ev_min=-2.0,
        ev_max=3.0,
        ev_step=1.0,
    )

    assert sample["route"] == "film_scan"
    assert sample["profile_kind"] == "positive_film_scan"
    assert "negative_scan_render" not in sample
    assert sample["metrics"]["polarity"] == "increasing"
    assert sample["metrics"]["safe_for_profile_aware_hdr"] is True
    scene_y = np.asarray(sample["input_domain"]["scene_y"], dtype=np.float32)
    y = np.asarray(sample["output"]["luminance_y"], dtype=np.float32)
    order = np.argsort(scene_y)
    assert np.all(np.diff(y[order]) >= -1e-5)

    with pytest.raises(ValueError, match="raw_negative_scan"):
        hdr_curve_profiles.sample_runtime_film_scan_curve_profile(
            film="fujifilm_provia_100f",
            scan_profile_kind="raw_negative_scan",
            ev_min=-2.0,
            ev_max=2.0,
            ev_step=1.0,
        )


def test_film_scan_sampling_ignores_print_controls_but_uses_film_and_scanner(monkeypatch) -> None:
    from spektrafilm.runtime.params_builder import init_params

    class FakeSimulator:
        def __init__(self, params) -> None:
            self._params = params

        def process(self, ramp_rgb: np.ndarray) -> np.ndarray:
            scene = ramp_rgb[0, :, 0].astype(np.float32)
            film_gamma = np.float32(self._params.film_render.density_curve_gamma)
            scanner_curve = np.float32(self._params.scanner.white_level)
            raw = np.float32(0.82) / (np.float32(1.0) + film_gamma * scene)
            raw = raw - np.float32(0.015) * scanner_curve * np.square(scene / np.max(scene))
            raw = np.maximum(raw, np.float32(1e-4))
            return np.repeat(raw.reshape(1, -1, 1), 3, axis=2).astype(np.float32)

    monkeypatch.setattr("spektrafilm.runtime.process.Simulator", FakeSimulator)

    base = init_params(film_profile="kodak_gold_200", print_profile="kodak_portra_endura")
    changed_print = init_params(film_profile="kodak_gold_200", print_profile="kodak_portra_endura")
    changed_print.enlarger.print_exposure = 3.0
    changed_print.enlarger.y_filter_shift = 20.0
    changed_print.enlarger.m_filter_shift = -15.0
    changed_print.enlarger.preflash_exposure = 0.5
    changed_print.print_render.glare.percent = 0.8

    changed_film = init_params(film_profile="kodak_gold_200", print_profile="kodak_portra_endura")
    changed_film.film_render.density_curve_gamma = 1.4

    changed_scanner = init_params(film_profile="kodak_gold_200", print_profile="kodak_portra_endura")
    changed_scanner.scanner.white_level = 0.55

    kwargs = {"ev_min": 0.0, "ev_max": 3.0, "ev_step": 1.0}
    base_sample = hdr_curve_profiles.sample_runtime_film_scan_curve_profile(params=base, film="kodak_gold_200", **kwargs)
    print_sample = hdr_curve_profiles.sample_runtime_film_scan_curve_profile(params=changed_print, film="kodak_gold_200", **kwargs)
    film_sample = hdr_curve_profiles.sample_runtime_film_scan_curve_profile(params=changed_film, film="kodak_gold_200", **kwargs)
    scanner_sample = hdr_curve_profiles.sample_runtime_film_scan_curve_profile(params=changed_scanner, film="kodak_gold_200", **kwargs)

    base_y = np.asarray(base_sample["output"]["luminance_y"], dtype=np.float32)
    print_y = np.asarray(print_sample["output"]["luminance_y"], dtype=np.float32)
    film_y = np.asarray(film_sample["output"]["luminance_y"], dtype=np.float32)
    scanner_y = np.asarray(scanner_sample["output"]["luminance_y"], dtype=np.float32)

    np.testing.assert_allclose(base_y, print_y, atol=1e-6)
    assert not np.allclose(base_y, film_y, atol=1e-4)
    assert not np.allclose(base_y, scanner_y, atol=1e-4)


def test_print_scan_runtime_sampling_keeps_print_route(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeSimulator:
        def __init__(self, params) -> None:
            captured["params"] = params

        def process(self, ramp_rgb: np.ndarray) -> np.ndarray:
            scene = ramp_rgb[0, :, 0].astype(np.float32)
            response = np.minimum(scene * np.float32(0.2) + np.float32(0.1), np.float32(0.95))
            return np.repeat(response.reshape(1, -1, 1), 3, axis=2).astype(np.float32)

    monkeypatch.setattr("spektrafilm.runtime.process.Simulator", FakeSimulator)

    sample = hdr_curve_profiles.sample_runtime_curve_profile(
        film="kodak_portra_400",
        paper="kodak_portra_endura",
        ev_min=0.0,
        ev_max=2.0,
        ev_step=1.0,
    )

    assert captured["params"].io.scan_film is False
    assert sample["route"] == "print_scan"
    assert sample["paper"] == "kodak_portra_endura"


# ---------------------------------------------------------------------------
# Profile-preserving HDR curve tests
# ---------------------------------------------------------------------------

from types import SimpleNamespace

from spektrafilm.utils.hdr_curve_profiles import (
    HDRCurveDefaults,
    FilmPrintHDRCurveProfile,
    profile_slope_loglog,
    profile_relative_hdr_gain_ev,
    soft_clip_relative_to_white,
    build_profile_preserving_hdr_curve,
    ProfilePreservingHDRCurveResult,
)


def _make_shoulder_profile(
    scene_y: np.ndarray,
    sdr_y: np.ndarray,
    *,
    safe_max_headroom: float = 6.0,
) -> FilmPrintHDRCurveProfile:
    """Helper to build a synthetic profile from arrays."""
    return FilmPrintHDRCurveProfile(
        film="synthetic",
        paper="test",
        polarity="increasing",
        safe_for_profile_aware_hdr=True,
        look_diffuse_white_y=float(np.interp(1.0, scene_y, sdr_y)),
        shoulder_limit_y=float(np.max(sdr_y)),
        midtone_slope=0.7,
        highlight_slope=0.02,
        shoulder_severity=0.85,
        highlight_tint_spread=0.0,
        defaults=HDRCurveDefaults(
            look_diffuse_white_reference=float(np.interp(1.0, scene_y, sdr_y)),
            hdr_diffuse_lift_strength=1.0,
            hdr_diffuse_lift_start=0.35,
            hdr_diffuse_lift_end=1.0,
            paper_rolloff_k=5.5,
            paper_rolloff_exposure_scale=2.5,
            graft_strength=1.0,
            safe_max_headroom=safe_max_headroom,
        ),
        scene_y=scene_y,
        sdr_luminance_y=sdr_y,
    )


_SHOULDER_SCENE = np.array([0.0625, 0.125, 0.184, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0], dtype=np.float32)
_SHOULDER_SDR = np.array([0.018, 0.045, 0.090, 0.46, 0.83, 0.89, 0.925, 0.948, 0.958], dtype=np.float32)


def test_profile_slope_loglog_on_linear_ramp() -> None:
    """Linear identity s=scene_y should give slope ≈ 1.0."""
    scene_y = np.array([0.1, 0.5, 1.0, 2.0, 4.0], dtype=np.float32)
    s = scene_y.copy()  # identity
    slope = profile_slope_loglog(scene_y, s)
    np.testing.assert_allclose(slope, 1.0, atol=0.05)


def test_profile_slope_loglog_on_shoulder_curve() -> None:
    """Shoulder region (scene_y >= 2) should have slope << midtone slope."""
    slope = profile_slope_loglog(_SHOULDER_SCENE, _SHOULDER_SDR)
    midtone_idx = np.argmin(np.abs(_SHOULDER_SCENE - 0.5))
    shoulder_idx = np.argmin(np.abs(_SHOULDER_SCENE - 8.0))
    assert slope[shoulder_idx] < slope[midtone_idx] * 0.5, (
        f"Shoulder slope {slope[shoulder_idx]} should be much less than midtone slope {slope[midtone_idx]}"
    )


def test_gain_ev_zero_below_diffuse_white() -> None:
    """gain_ev must be near zero for scene_y <= diffuse_white."""
    scene_y = np.array([0.1, 0.3, 0.5, 0.8, 1.0], dtype=np.float32)
    s = np.array([0.02, 0.15, 0.40, 0.72, 0.83], dtype=np.float32)
    gain_ev = profile_relative_hdr_gain_ev(scene_y, s, diffuse_white=1.0)
    # All scene_y <= diffuse_white, so x = log2(scene_y/dw) <= 0 => scene_excess = 0 => gain = 0.
    np.testing.assert_allclose(gain_ev, 0.0, atol=0.01)


def test_gain_ev_increases_when_slope_is_low() -> None:
    """Lower profile slope should yield higher gain_ev."""
    scene_y = np.array([0.5, 1.0, 2.0, 4.0, 8.0, 16.0], dtype=np.float32)
    # Profile A: strong shoulder (slope drops quickly).
    s_a = np.array([0.40, 0.83, 0.89, 0.925, 0.948, 0.958], dtype=np.float32)
    # Profile B: weak shoulder (slope stays higher).
    s_b = np.array([0.40, 0.83, 0.95, 1.10, 1.30, 1.50], dtype=np.float32)

    gain_a = profile_relative_hdr_gain_ev(scene_y, s_a, diffuse_white=1.0)
    gain_b = profile_relative_hdr_gain_ev(scene_y, s_b, diffuse_white=1.0)

    # At 8 stops above DW, profile A (strong shoulder) should have more gain.
    idx_8 = np.argmin(np.abs(scene_y - 8.0))
    assert gain_a[idx_8] > gain_b[idx_8], (
        f"Strong shoulder gain {gain_a[idx_8]} should exceed weak shoulder gain {gain_b[idx_8]}"
    )


def test_soft_clip_below_knee_is_identity() -> None:
    """Values below the knee must pass through unchanged."""
    y = np.array([0.1, 0.3, 0.5, 0.8], dtype=np.float32)
    result = soft_clip_relative_to_white(y, white=0.83, peak=2.35, softness=0.45)
    # Knee = 0.83 + (2.35 - 0.83) * (1 - 0.45) = 0.83 + 0.836 = 1.666. All y < knee.
    np.testing.assert_allclose(result, y, atol=1e-6)


def test_soft_clip_approaches_peak_asymptotically() -> None:
    """Large inputs should be capped at exactly peak. Output must be monotonic."""
    y = np.array([0.5, 1.0, 2.0, 5.0, 10.0, 100.0], dtype=np.float32)
    result = soft_clip_relative_to_white(y, white=0.83, peak=2.35, softness=0.45)
    assert float(result[-1]) == pytest.approx(2.35, abs=1e-5)
    assert np.all(np.diff(result) >= -1e-6), "Output must be monotonic"


def test_build_profile_preserving_hdr_curve_monotonic() -> None:
    """h_profile must be monotonically non-decreasing w.r.t. sorted scene_y."""
    profile = _make_shoulder_profile(_SHOULDER_SCENE, _SHOULDER_SDR)
    h = build_profile_preserving_hdr_curve(profile, _SHOULDER_SCENE, diffuse_white=1.0)
    order = np.argsort(_SHOULDER_SCENE)
    np.testing.assert_array_less(-1e-6, np.diff(h[order]))


def test_build_profile_preserving_hdr_curve_ge_sdr() -> None:
    """h_profile >= s_profile when min_gain = 1.0."""
    profile = _make_shoulder_profile(_SHOULDER_SCENE, _SHOULDER_SDR)
    mapping = SimpleNamespace(profile_hdr_min_gain=1.0)
    result = build_profile_preserving_hdr_curve(
        profile, _SHOULDER_SCENE, diffuse_white=1.0,
        mapping=mapping, return_diagnostics=True,
    )
    assert isinstance(result, ProfilePreservingHDRCurveResult)
    np.testing.assert_array_less(result.s_profile - 1e-6, result.h_profile)


def test_peak_scales_with_look_white() -> None:
    """visual_peak / look_white must be constant for the same peak_ev."""
    profile = _make_shoulder_profile(_SHOULDER_SCENE, _SHOULDER_SDR)

    # Case A: diffuse_white = 1.0.
    res_a = build_profile_preserving_hdr_curve(
        profile, _SHOULDER_SCENE, diffuse_white=1.0, return_diagnostics=True,
    )
    # Case B: diffuse_white = 0.5 — different look_white.
    res_b = build_profile_preserving_hdr_curve(
        profile, _SHOULDER_SCENE, diffuse_white=0.5, return_diagnostics=True,
    )

    ratio_a = res_a.visual_peak / res_a.look_white
    ratio_b = res_b.visual_peak / res_b.look_white
    np.testing.assert_allclose(ratio_a, ratio_b, rtol=1e-5)


def test_different_s_profile_produces_different_h_profile() -> None:
    """Two different profiles with the same scene_y must produce different H_profile
    through look_white and slope, not through fixed absolute headroom."""
    scene_y = _SHOULDER_SCENE

    # Profile A: strong shoulder (typical film).
    profile_a = _make_shoulder_profile(scene_y, _SHOULDER_SDR)

    # Profile B: darker print / different shoulder.
    sdr_b = np.array([0.012, 0.030, 0.060, 0.35, 0.68, 0.73, 0.76, 0.78, 0.79], dtype=np.float32)
    profile_b = _make_shoulder_profile(scene_y, sdr_b)

    res_a = build_profile_preserving_hdr_curve(
        profile_a, scene_y, diffuse_white=1.0, return_diagnostics=True,
    )
    res_b = build_profile_preserving_hdr_curve(
        profile_b, scene_y, diffuse_white=1.0, return_diagnostics=True,
    )

    # S_profile differs.
    assert not np.allclose(res_a.s_profile, res_b.s_profile, atol=0.01)
    # look_white differs.
    assert res_a.look_white != pytest.approx(res_b.look_white, abs=0.01)
    # H_profile differs.
    assert not np.allclose(res_a.h_profile, res_b.h_profile, atol=0.01)
    # Slope remains profile-derived even when strict gain saturates to the same
    # shoulder capacity pattern for these two synthetic profiles.
    assert not np.allclose(res_a.slope, res_b.slope, atol=0.01)
    # But the relative peak ratio is preserved.
    ratio_a = res_a.visual_peak / res_a.look_white
    ratio_b = res_b.visual_peak / res_b.look_white
    np.testing.assert_allclose(ratio_a, ratio_b, rtol=1e-4)


from spektrafilm.utils.hdr_curve_profiles import (
    budget_recovery_gain_ev,
    profile_modern_recovery_budgeted_gain_ev,
    ProfileHDRCurveResult,
)

def test_budget_does_not_expand_when_raw_peak_below_target() -> None:
    p_ev = np.array([0.0, 0.5, 1.0], dtype=np.float32)
    raw_gain_ev = np.array([0.0, 0.2, 0.5], dtype=np.float32)
    gain_ev, info = budget_recovery_gain_ev(p_ev, raw_gain_ev, target_peak_ev=2.03, return_info=True)
    np.testing.assert_allclose(gain_ev, raw_gain_ev, atol=1e-6)
    assert info["budget_scale"] == 1.0
    assert info["budget_was_applied"] is False
    assert info["raw_peak_ev_before_budget"] < 2.03

def test_budget_scales_recovery_when_raw_peak_exceeds_target() -> None:
    p_ev = np.array([0.0, 0.5, 1.0], dtype=np.float32)
    raw_gain_ev = np.array([0.0, 0.5, 2.0], dtype=np.float32)
    gain_ev, info = budget_recovery_gain_ev(p_ev, raw_gain_ev, target_peak_ev=2.03, return_info=True)
    assert info["raw_peak_ev_before_budget"] > 2.03
    assert info["budget_scale"] < 1.0
    assert info["budget_was_applied"] is True
    # The max of final should be close to 2.03
    np.testing.assert_allclose(info["actual_peak_ev_after_budget"], 2.03, atol=1e-2)

def test_budget_preserves_profile_baseline() -> None:
    # When p_ev itself exceeds target, we should not scale down p_ev
    p_ev = np.array([0.0, 1.5, 2.5], dtype=np.float32)
    raw_gain_ev = np.array([0.0, 0.5, 1.0], dtype=np.float32)
    gain_ev, info = budget_recovery_gain_ev(p_ev, raw_gain_ev, target_peak_ev=2.03, return_info=True)
    # The baseline is preserved. The effective target becomes 2.5.
    assert info["effective_target_peak_ev"] >= 2.5
    # gain_ev should be non-negative
    assert np.all(gain_ev >= 0.0)

def test_budget_scales_gain_not_profile_ev() -> None:
    p_ev = np.array([0.0, 0.5, 1.0], dtype=np.float32)
    raw_gain_ev = np.array([0.0, 0.5, 2.0], dtype=np.float32)
    gain_ev, info = budget_recovery_gain_ev(p_ev, raw_gain_ev, target_peak_ev=2.03, return_info=True)
    scale = info["budget_scale"]
    # The gain_ev should exactly be raw_gain_ev * scale
    np.testing.assert_allclose(gain_ev, raw_gain_ev * scale, atol=1e-5)

def test_modern_recovery_uses_compressed_ev() -> None:
    scene_y = np.array([0.5, 1.0, 2.0, 4.0, 8.0, 16.0], dtype=np.float32)
    profile = _make_shoulder_profile(scene_y, _SHOULDER_SDR[3:])

    mapping = SimpleNamespace(
        profile_hdr_mode="modern_recovery_peak_budget",
        profile_hdr_recovery_ratio=0.5,
        profile_hdr_recovery_knee_ev=0.1,
        profile_hdr_recovery_full_ev=1.1,
        profile_hdr_slope_full=0.9,
        profile_hdr_slope_zero=0.18,
        profile_hdr_target_peak_ev=2.03,
        profile_hdr_normalize_percentile=99.9,
        profile_hdr_budget_hard_cap=True,
        profile_hdr_min_gain=1.0,
        profile_hdr_enforce_monotonic=True,
    )

    result = build_profile_preserving_hdr_curve(
        profile, scene_y, diffuse_white=1.0, mapping=mapping, return_diagnostics=True
    )
    assert isinstance(result, ProfileHDRCurveResult)
    # Compressed EV should increase with scene_y
    diffs = np.diff(result.compressed_ev)
    assert np.all(diffs >= -1e-5)

def test_modern_recovery_zero_below_knee() -> None:
    scene_y = np.array([0.5, 1.0, 1.05], dtype=np.float32)
    s = scene_y.copy() # dummy profile
    result = profile_modern_recovery_budgeted_gain_ev(
        scene_y, s, diffuse_white=1.0, look_white=1.0,
        recovery_knee_ev=0.10, return_diagnostics=True
    )
    np.testing.assert_allclose(result["raw_gain_ev"], 0.0, atol=1e-5)

def test_modern_recovery_respects_target_peak_ev() -> None:
    scene_y = np.array([0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0], dtype=np.float32)
    s_profile = np.array([0.5, 0.8, 0.9, 0.95, 0.98, 0.99, 0.995, 0.999], dtype=np.float32)
    result = profile_modern_recovery_budgeted_gain_ev(
        scene_y, s_profile, diffuse_white=1.0, look_white=0.8,
        target_peak_ev=2.03, return_diagnostics=True
    )
    assert result["actual_peak_ev_after_budget"] <= 2.03 + 1e-4

def test_profile_modern_recovery_budget_increases_headroom_over_strict() -> None:
    scene_y = np.array([0.5, 1.0, 2.0, 4.0, 8.0, 16.0], dtype=np.float32)
    s_profile = np.array([0.5, 0.8, 0.9, 0.95, 0.98, 0.99], dtype=np.float32)
    profile = _make_shoulder_profile(scene_y, s_profile)

    strict_mapping = SimpleNamespace(profile_hdr_mode="strict_preserving", profile_hdr_peak_ev=1.5, profile_hdr_strength=0.65, profile_hdr_soft_clip_softness=0.45, profile_hdr_min_gain=1.0, profile_hdr_enforce_monotonic=True)
    strict_res = build_profile_preserving_hdr_curve(profile, scene_y, diffuse_white=1.0, mapping=strict_mapping, return_diagnostics=True)

    modern_mapping = SimpleNamespace(
        profile_hdr_mode="modern_recovery_peak_budget",
        profile_hdr_recovery_ratio=0.5,
        profile_hdr_recovery_knee_ev=0.1,
        profile_hdr_recovery_full_ev=1.1,
        profile_hdr_slope_full=0.9,
        profile_hdr_slope_zero=0.18,
        profile_hdr_target_peak_ev=2.03,
        profile_hdr_normalize_percentile=99.9,
        profile_hdr_budget_hard_cap=True,
        profile_hdr_enforce_monotonic=True,
        profile_hdr_min_gain=1.0,
    )
    modern_res = build_profile_preserving_hdr_curve(profile, scene_y, diffuse_white=1.0, mapping=modern_mapping, return_diagnostics=True)

    assert np.max(modern_res.final_h_ev) > np.max(np.log2(np.maximum(strict_res.h_profile, 1e-8) / strict_res.look_white))

def test_kodak_gold_200_auto_resolves_positive_negative_scan() -> None:
    sample = hdr_curve_profiles.sample_runtime_film_scan_curve_profile(
        film="kodak_gold_200",
        scan_profile_kind="auto",
        ev_min=-2.0, ev_max=2.0, ev_step=2.0,
    )
    assert sample["profile_kind"] == "positive_negative_scan"
    assert sample["metrics"]["safe_for_profile_aware_hdr"] is True
    assert "negative_scan_render" in sample

def test_fujifilm_provia_100f_auto_resolves_positive_film_scan() -> None:
    sample = hdr_curve_profiles.sample_runtime_film_scan_curve_profile(
        film="fujifilm_provia_100f",
        scan_profile_kind="auto",
        ev_min=-2.0, ev_max=2.0, ev_step=2.0,
    )
    assert sample["profile_kind"] == "positive_film_scan"
    # positive_film_scan generally has no negative_scan_render
    assert "negative_scan_render" not in sample

def test_kodak_2383_auto_raises() -> None:
    with pytest.raises(ValueError, match="requires a filming film profile"):
        hdr_curve_profiles.sample_runtime_film_scan_curve_profile(
            film="kodak_2383", scan_profile_kind="auto", ev_min=-2.0, ev_max=2.0, ev_step=2.0
        )

def test_kodak_2393_auto_raises() -> None:
    with pytest.raises(ValueError, match="requires a filming film profile"):
        hdr_curve_profiles.sample_runtime_film_scan_curve_profile(
            film="kodak_2393", scan_profile_kind="auto", ev_min=-2.0, ev_max=2.0, ev_step=2.0
        )

def test_kodak_2383_explicit_kinds_all_raise() -> None:
    for kind in ("raw_negative_scan", "positive_negative_scan"):
        with pytest.raises(ValueError, match="requires a negative filming film profile"):
            hdr_curve_profiles.sample_runtime_film_scan_curve_profile(
                film="kodak_2383", scan_profile_kind=kind, ev_min=-2.0, ev_max=2.0, ev_step=2.0
            )
    with pytest.raises(ValueError, match="requires a positive/reversal filming film profile"):
        hdr_curve_profiles.sample_runtime_film_scan_curve_profile(
            film="kodak_2383", scan_profile_kind="positive_film_scan", ev_min=-2.0, ev_max=2.0, ev_step=2.0
        )
