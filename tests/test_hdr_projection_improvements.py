"""Tests for the 2026-07-26 HDR review fixes.

Covers: Hunt-effect path-to-white scaling, fixed extension span (crop
stability), C1 soft shoulder blends, tightened monotonicity classification,
scene-authority-after-boost, and dynamic chemical profile resampling.
"""

from __future__ import annotations

import copy
from dataclasses import replace

import numpy as np
import pytest

from spektrafilm.hdr import HDRProjectionConfig, project_hdr_ideal_paper
from spektrafilm.hdr.ideal_paper import _smooth_max, _soft_clip_gain
from spektrafilm.hdr.profile_cache import (
    clear_dynamic_print_profile_cache,
    get_dynamic_print_curve_profile,
)
from spektrafilm.hdr.projection import (
    _effective_path_to_white_strength,
    _extension_gain,
)
from spektrafilm.runtime.params_builder import digest_params, init_params
from spektrafilm.runtime.process import Simulator
from spektrafilm.runtime.route_master import RouteMaster
from spektrafilm.utils.hdr_curve_profiles import (
    _classify_polarity,
    build_curve_profile_sample,
    curve_profile_from_sample,
)


def _fast_params(*, film_profile: str = "kodak_portra_400", print_profile: str = "kodak_portra_endura"):
    params = init_params(film_profile=film_profile, print_profile=print_profile)
    params.debug.deactivate_spatial_effects = True
    params.debug.deactivate_stochastic_effects = True
    params.settings.use_enlarger_lut = False
    params.settings.use_scanner_lut = False
    params.io.upscale_factor = 1.0
    params.io.crop = False
    params.camera.auto_exposure = False
    params.camera.exposure_compensation_ev = 0.0
    return digest_params(params)


def _paper_master(*, chroma: tuple[float, float, float] = (0.25, 0.55, 1.0)) -> RouteMaster:
    route_y = np.array([[0.25, 0.6, 0.75, 0.8]], dtype=np.float32)
    route_chroma = np.array(chroma, dtype=np.float32)
    route_rgb = route_y[..., None] * route_chroma
    scene_y = np.array([[0.25, 1.0, 2.0, 6.0]], dtype=np.float32)
    return RouteMaster(
        mode="paper",
        route_kind="print_scan",
        route_linear_rgb=route_rgb,
        route_linear_xyz=route_rgb,
        route_luminance_y=route_y,
        sdr_legacy_rgb=np.clip(route_rgb, 0.0, 1.0),
        scene_y_raw=scene_y,
        post_halation_y=scene_y,
        density_cmy=np.repeat(route_y[..., None], 3, axis=2),
        route_look_chroma=None,
        material_detail_y=None,
        diagnostics={
            "output_color_space": "Display P3",
            "output_cctf_encoding": False,
        },
    )


def _synthetic_profile(
    *,
    film: str = "synthetic_film",
    paper: str = "synthetic_paper",
    highlight_rise: float = 0.08,
):
    scene = np.array([0.05, 0.184, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0], dtype=np.float32)
    y = np.array(
        [
            0.05,
            0.15,
            0.35,
            0.60,
            0.60 + 0.4 * highlight_rise,
            0.60 + 0.7 * highlight_rise,
            0.60 + highlight_rise,
            0.60 + 1.1 * highlight_rise,
        ],
        dtype=np.float32,
    )
    rgb = np.repeat(y[:, None], 3, axis=1)
    sample = build_curve_profile_sample(
        film=film,
        paper=paper,
        route="print_scan",
        scene_y=scene,
        output_rgb=rgb,
    )
    return curve_profile_from_sample(sample)


# ---------------------------------------------------------------------------
# P0-(d): path-to-white scales with headroom (Hunt effect)
# ---------------------------------------------------------------------------


def test_effective_path_to_white_strength_reference_and_monotonic() -> None:
    assert _effective_path_to_white_strength(0.12, 4.0) == pytest.approx(0.12)
    values = [
        _effective_path_to_white_strength(0.12, headroom)
        for headroom in (2.0, 4.0, 8.0, 16.0)
    ]
    assert values == sorted(values)
    assert values[0] < 0.12 < values[2]
    assert _effective_path_to_white_strength(0.0, 16.0) == 0.0
    assert _effective_path_to_white_strength(0.9, 1024.0) <= 1.0
    assert _effective_path_to_white_strength(0.12, 1.01) >= 0.0


def test_paper_projection_reports_and_applies_hunt_scaling() -> None:
    master = _paper_master()
    high = project_hdr_ideal_paper(
        master, HDRProjectionConfig(max_headroom=8.0, headroom_percentile=100.0)
    )
    reference = project_hdr_ideal_paper(
        master, HDRProjectionConfig(max_headroom=4.0, headroom_percentile=100.0)
    )
    assert high.diagnostics["path_to_white_strength_effective"] > high.diagnostics[
        "path_to_white_strength_input"
    ]
    assert reference.diagnostics["path_to_white_strength_effective"] == pytest.approx(
        reference.diagnostics["path_to_white_strength_input"]
    )
    # The blue-dominant highlight keeps its dominant channel while
    # desaturating toward neutral (hue-preserving path to white).
    brightest = high.hdr_rgb[0, 3]
    assert int(np.argmax(brightest)) == 2
    chroma = np.array([0.25, 0.55, 1.0], dtype=np.float32)
    source_spread = float((chroma.max() - chroma.min()) / chroma.max())
    hdr_spread = float((brightest.max() - brightest.min()) / max(brightest.max(), 1e-8))
    assert hdr_spread < source_spread


# ---------------------------------------------------------------------------
# P1-(c): extension gain independent of content statistics (crop stability)
# ---------------------------------------------------------------------------


def test_extension_gain_is_content_independent() -> None:
    ratio = np.array([[0.5, 1.2, 1.8, 3.5]], dtype=np.float32)
    cropped = ratio[:, :3]
    full_gain = _extension_gain(ratio, max_headroom=4.0, strength=0.55)
    cropped_gain = _extension_gain(cropped, max_headroom=4.0, strength=0.55)
    np.testing.assert_allclose(cropped_gain, full_gain[:, :3], rtol=0.0, atol=1e-7)


def test_paper_projection_reports_span_policy() -> None:
    result = project_hdr_ideal_paper(
        _paper_master(), HDRProjectionConfig(max_headroom=4.0, headroom_percentile=100.0)
    )
    assert result.diagnostics["extension_span_policy"] == "fixed_max_headroom"


# ---------------------------------------------------------------------------
# P1-(b): C1 soft shoulder helpers
# ---------------------------------------------------------------------------


def test_smooth_max_bounds_and_seam_exactness() -> None:
    a = np.linspace(0.0, 4.0, 401, dtype=np.float32)
    b = np.full_like(a, 2.0)
    blended = _smooth_max(a, b, 0.06)
    assert np.all(blended >= np.minimum(a, b) - 1e-6)
    assert np.all(blended <= np.maximum(a, b) + 1e-6)
    equal = _smooth_max(b, b, 0.06)
    np.testing.assert_allclose(equal, b, rtol=0.0, atol=1e-6)
    # C1: the finite-difference slope has no O(1) jump at the crossing
    # (a hard max would jump by ~1.0 between adjacent samples).
    slopes = np.diff(blended) / np.diff(a)
    assert float(np.max(np.abs(np.diff(slopes)))) < 0.3


def test_soft_clip_gain_reaches_cap_without_slope_jump() -> None:
    gain = np.linspace(1.0, 6.0, 1001, dtype=np.float32)
    clipped = _soft_clip_gain(gain, 4.0)
    assert np.all(np.diff(clipped) >= -1e-6)
    assert clipped[-1] == pytest.approx(4.0)
    np.testing.assert_allclose(clipped[gain <= 3.6], gain[gain <= 3.6], rtol=0.0, atol=1e-6)
    assert np.all(clipped <= 4.0 + 1e-6)
    slopes = np.diff(clipped) / np.diff(gain)
    assert float(np.max(np.abs(np.diff(slopes)))) < 0.05


# ---------------------------------------------------------------------------
# P1-(d): monotonicity classification is magnitude-aware
# ---------------------------------------------------------------------------


def test_classifier_rejects_single_large_reversal() -> None:
    y = np.linspace(0.1, 1.0, 40, dtype=np.float32)
    y[20] = y[19] - 0.2
    polarity, _ = _classify_polarity(y)
    assert polarity == "nonmonotonic"


def test_classifier_tolerates_numeric_noise() -> None:
    y = np.linspace(0.1, 1.0, 40, dtype=np.float32)
    y[20] = y[19] - 2e-5
    polarity, _ = _classify_polarity(y)
    assert polarity == "increasing"


# ---------------------------------------------------------------------------
# P1-(f): scene authority reflects highlight-boost reconstruction
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_scene_authority_includes_highlight_boost() -> None:
    image = np.repeat(
        np.linspace(0.05, 6.0, 6, dtype=np.float64).reshape(1, -1, 1), 3, axis=2
    ).repeat(2, axis=0)

    plain = _fast_params()
    plain.film_render.halation.boost_ev = 0.0
    boosted = _fast_params()
    boosted.film_render.halation.boost_ev = 2.0
    boosted.film_render.halation.boost_range = 0.5
    boosted.film_render.halation.protect_ev = 0.0

    master_plain = Simulator(plain).process_master(image, hdr_mode="paper")
    master_boosted = Simulator(boosted).process_master(image, hdr_mode="paper")

    assert float(np.max(master_boosted.scene_y_raw)) > float(np.max(master_plain.scene_y_raw)) + 1e-6


# ---------------------------------------------------------------------------
# P0-(a): dynamic chemical profile resampling
# ---------------------------------------------------------------------------


def test_ideal_paper_uses_chemical_profile_override() -> None:
    master = _paper_master()
    profile = _synthetic_profile()
    config = HDRProjectionConfig(max_headroom=4.0, headroom_percentile=100.0)

    dynamic = project_hdr_ideal_paper(master, config, chemical_profile=profile)
    assert dynamic.diagnostics["paper_rolloff_strategy"] == "chemical_print"
    assert dynamic.diagnostics["chemical_profile_origin"] == "dynamic_resample"
    assert dynamic.diagnostics["chemical_shoulder_severity"] == pytest.approx(
        profile.shoulder_severity
    )

    static = project_hdr_ideal_paper(master, config)
    assert static.diagnostics["chemical_profile_origin"] == "static_bundled"
    assert static.diagnostics["paper_rolloff_strategy"] == "generic_scene_extension"


def test_shoulder_metrics_change_hdr_rendering() -> None:
    master = _paper_master()
    config = HDRProjectionConfig(max_headroom=4.0, headroom_percentile=100.0)
    soft = _synthetic_profile(highlight_rise=0.3)
    hard = _synthetic_profile(highlight_rise=0.005)

    soft_result = project_hdr_ideal_paper(master, config, chemical_profile=soft)
    hard_result = project_hdr_ideal_paper(master, config, chemical_profile=hard)

    assert soft_result.diagnostics["chemical_shoulder_severity"] < hard_result.diagnostics[
        "chemical_shoulder_severity"
    ]
    assert not np.allclose(soft_result.hdr_rgb, hard_result.hdr_rgb, atol=1e-5)


def test_dynamic_print_profile_cache_and_failure(monkeypatch) -> None:
    clear_dynamic_print_profile_cache()
    try:
        params = _fast_params()
        calls = {"count": 0}

        def fake_sample(*, params, **kwargs):
            calls["count"] += 1
            profile = _synthetic_profile()
            scene = profile.scene_y
            rgb = np.asarray(profile.output_rgb, dtype=np.float32)
            return build_curve_profile_sample(
                film="kodak_portra_400",
                paper="kodak_portra_endura",
                route="print_scan",
                scene_y=scene,
                output_rgb=rgb,
            )

        monkeypatch.setattr(
            "spektrafilm.utils.hdr_curve_profiles.sample_runtime_print_curve_profile",
            fake_sample,
        )

        first, first_origin = get_dynamic_print_curve_profile(params)
        assert first is not None
        assert first_origin == "dynamic_resample"
        assert calls["count"] == 1

        second, second_origin = get_dynamic_print_curve_profile(params)
        assert second is not None
        assert second_origin == "dynamic_resample_cached"
        assert calls["count"] == 1

        changed = copy.deepcopy(params)
        changed.print_render.density_curves_morph = replace(
            changed.print_render.density_curves_morph, gamma_factor=1.4
        )
        third, third_origin = get_dynamic_print_curve_profile(changed)
        assert third is not None
        assert third_origin == "dynamic_resample"
        assert calls["count"] == 2

        def failing_sample(*, params, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(
            "spektrafilm.utils.hdr_curve_profiles.sample_runtime_print_curve_profile",
            failing_sample,
        )
        clear_dynamic_print_profile_cache()
        failed, failed_origin = get_dynamic_print_curve_profile(params)
        assert failed is None
        assert failed_origin.startswith("dynamic_sampling_failed:")
    finally:
        clear_dynamic_print_profile_cache()


@pytest.mark.integration
def test_dynamic_resample_follows_print_curve_morph() -> None:
    clear_dynamic_print_profile_cache()
    try:
        base = _fast_params()
        morphed = _fast_params()
        morphed.print_render.density_curves_morph = replace(
            morphed.print_render.density_curves_morph, active=True, gamma_factor=0.6
        )

        base_profile, base_origin = get_dynamic_print_curve_profile(base)
        morphed_profile, morphed_origin = get_dynamic_print_curve_profile(morphed)

        assert base_origin == "dynamic_resample"
        assert morphed_origin == "dynamic_resample"
        assert base_profile is not None and morphed_profile is not None
        assert morphed_profile.shoulder_severity != pytest.approx(
            base_profile.shoulder_severity, abs=1e-4
        )
    finally:
        clear_dynamic_print_profile_cache()
