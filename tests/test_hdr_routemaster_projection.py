from __future__ import annotations

import copy

import numpy as np
import pytest

from spektrafilm.hdr import (
    HDRProjectionConfig,
    project_hdr_ideal_paper,
    project_hdr_light_table,
)
from spektrafilm.runtime.params_builder import digest_params, init_params
from spektrafilm.runtime.process import Simulator
from spektrafilm.runtime.route_master import RouteMaster


pytestmark = pytest.mark.integration


def make_fast_test_params(*, film_profile: str = "kodak_portra_400", print_profile: str = "kodak_portra_endura"):
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


def _synthetic_master(
    *,
    mode: str = "light_table",
    route_kind: str = "film_scan",
    route_scale: float = 1.0,
    scene_scale: float = 1.0,
    diagnostics: dict | None = None,
) -> RouteMaster:
    route_y = np.array([[0.25, 0.75, 1.0, 1.2]], dtype=np.float32) * np.float32(route_scale)
    route_chroma = np.array([1.0, 0.55, 0.25], dtype=np.float32)
    route_rgb = route_y[..., None] * route_chroma
    scene_y = np.array([[0.25, 1.0, 2.0, 6.0]], dtype=np.float32) * np.float32(scene_scale)
    return RouteMaster(
        mode=mode,  # type: ignore[arg-type]
        route_kind=route_kind,  # type: ignore[arg-type]
        route_linear_rgb=route_rgb,
        route_linear_xyz=route_rgb,
        route_luminance_y=route_y,
        sdr_legacy_rgb=np.clip(route_rgb, 0.0, 1.0),
        scene_y_raw=scene_y,
        post_halation_y=scene_y * np.float32(1.1),
        density_cmy=np.repeat(route_y[..., None], 3, axis=2),
        route_look_chroma=None,
        material_detail_y=None,
        diagnostics={} if diagnostics is None else diagnostics,
    )


def _small_patch() -> np.ndarray:
    ramp = np.linspace(0.05, 1.25, 5, dtype=np.float64)
    return np.repeat(ramp.reshape(1, -1, 1), 5, axis=0).repeat(3, axis=2)


def test_light_table_does_not_respond_to_paper_params() -> None:
    image = _small_patch()
    base_params = make_fast_test_params(film_profile="fujifilm_provia_100f", print_profile="kodak_portra_endura")
    changed_params = make_fast_test_params(film_profile="fujifilm_provia_100f", print_profile="kodak_ultra_endura")
    changed_params.enlarger.print_exposure = 3.0
    changed_params.enlarger.y_filter_neutral = 5.0
    changed_params.enlarger.m_filter_neutral = 120.0
    changed_params.enlarger.preflash_exposure = 0.4
    changed_params.print_render.glare.percent = 0.8

    base_master = Simulator(base_params).process_master(image, hdr_mode="light_table")
    changed_master = Simulator(changed_params).process_master(image, hdr_mode="light_table")
    config = HDRProjectionConfig(max_headroom=4.0, headroom_percentile=100.0)

    base = project_hdr_light_table(base_master, config)
    changed = project_hdr_light_table(changed_master, config)

    np.testing.assert_allclose(changed.hdr_rgb, base.hdr_rgb, rtol=0.0, atol=1e-9)
    np.testing.assert_allclose(changed.sdr_rgb, base.sdr_rgb, rtol=0.0, atol=1e-9)


def test_paper_mode_responds_to_print_exposure() -> None:
    image = _small_patch()
    base_params = make_fast_test_params()
    changed_params = copy.deepcopy(base_params)
    for params in (base_params, changed_params):
        params.enlarger.normalize_print_exposure = False
        params.enlarger.print_exposure_compensation = False
    changed_params.enlarger.print_exposure = 2.0

    base_master = Simulator(base_params).process_master(image, hdr_mode="paper")
    changed_master = Simulator(changed_params).process_master(image, hdr_mode="paper")
    config = HDRProjectionConfig(max_headroom=4.0, headroom_percentile=100.0)

    base = project_hdr_ideal_paper(base_master, config)
    changed = project_hdr_ideal_paper(changed_master, config)

    assert not np.allclose(changed.hdr_rgb, base.hdr_rgb, atol=1e-4)


def test_paper_mode_responds_to_paper_profile() -> None:
    image = _small_patch()
    base_params = make_fast_test_params(print_profile="kodak_portra_endura")
    changed_params = make_fast_test_params(print_profile="fujifilm_crystal_archive_typeii")

    base_master = Simulator(base_params).process_master(image, hdr_mode="paper")
    changed_master = Simulator(changed_params).process_master(image, hdr_mode="paper")
    config = HDRProjectionConfig(max_headroom=4.0, headroom_percentile=100.0)

    base = project_hdr_ideal_paper(base_master, config)
    changed = project_hdr_ideal_paper(changed_master, config)

    assert not np.allclose(changed.hdr_rgb, base.hdr_rgb, atol=1e-4)


def test_negative_film_light_table_requires_positive_rendering() -> None:
    raw_master = _synthetic_master(
        route_kind="film_scan",
        diagnostics={"profile_kind": "raw_negative_scan"},
    )

    with pytest.raises(ValueError, match="positive"):
        project_hdr_light_table(raw_master, HDRProjectionConfig())

    params = make_fast_test_params(film_profile="kodak_gold_200")
    master = Simulator(params).process_master(_small_patch(), hdr_mode="light_table")
    assert master.diagnostics["profile_kind"] == "positive_negative_scan"
    result = project_hdr_light_table(master, HDRProjectionConfig(max_headroom=4.0))
    assert np.all(np.isfinite(result.hdr_rgb))


def test_hdr_light_table_curve_monotonic() -> None:
    master = _synthetic_master(route_kind="film_scan")
    result = project_hdr_light_table(master, HDRProjectionConfig(max_headroom=5.0, headroom_percentile=100.0))
    y = result.hdr_luminance_y.reshape(-1)

    assert np.all(np.diff(y) >= -1e-6)
    assert result.headroom > 1.0


def test_hdr_ideal_paper_curve_monotonic() -> None:
    master = _synthetic_master(mode="paper", route_kind="print_scan")
    result = project_hdr_ideal_paper(master, HDRProjectionConfig(max_headroom=5.0, headroom_percentile=100.0))
    y = result.hdr_luminance_y.reshape(-1)

    assert np.all(np.diff(y) >= -1e-6)
    assert result.headroom > 1.0


def test_hdr_ideal_paper_curve_continuity() -> None:
    scene = np.linspace(0.9, 1.1, 33, dtype=np.float32).reshape(1, -1)
    route = np.minimum(scene * 0.84, 0.92)
    master = RouteMaster(
        mode="paper",
        route_kind="print_scan",
        route_linear_rgb=np.repeat(route[..., None], 3, axis=2),
        route_linear_xyz=np.repeat(route[..., None], 3, axis=2),
        route_luminance_y=route,
        sdr_legacy_rgb=np.repeat(route[..., None], 3, axis=2),
        scene_y_raw=scene,
        post_halation_y=scene,
        density_cmy=np.repeat(route[..., None], 3, axis=2),
        route_look_chroma=None,
        material_detail_y=None,
        diagnostics={},
    )

    result = project_hdr_ideal_paper(master, HDRProjectionConfig(max_headroom=3.0, paper_white=0.84))
    y = result.hdr_luminance_y.reshape(-1)
    join_index = int(np.argmin(np.abs(scene.reshape(-1) - 1.0)))

    assert abs(float(y[join_index]) - float(route.reshape(-1)[join_index])) < 0.03
    assert float(np.max(np.abs(np.diff(y)))) < 0.08


def test_route_look_chroma_preserved_by_default() -> None:
    master = _synthetic_master(route_kind="film_scan")
    result = project_hdr_light_table(master, HDRProjectionConfig(max_headroom=5.0, headroom_percentile=100.0))

    route_ratio = master.route_linear_rgb[0, -1, 2] / master.route_linear_rgb[0, -1, 0]
    hdr_ratio = result.hdr_rgb[0, -1, 2] / result.hdr_rgb[0, -1, 0]
    np.testing.assert_allclose(hdr_ratio, route_ratio, atol=0.03)


def test_scene_rgb_is_auxiliary_not_default() -> None:
    master = _synthetic_master(
        route_kind="film_scan",
        diagnostics={"scene_rgb_aux": np.array([[[0.1, 0.1, 10.0]]], dtype=np.float32)},
    )
    result = project_hdr_light_table(master, HDRProjectionConfig(max_headroom=5.0, headroom_percentile=100.0))

    route_ratio = master.route_linear_rgb[0, -1, 2] / master.route_linear_rgb[0, -1, 0]
    hdr_ratio = result.hdr_rgb[0, -1, 2] / result.hdr_rgb[0, -1, 0]
    np.testing.assert_allclose(hdr_ratio, route_ratio, atol=0.03)


def test_gain_map_high_frequency_cleanliness() -> None:
    checker = (np.indices((16, 16)).sum(axis=0) % 2).astype(np.float32)
    route_y = 0.5 + checker * 0.08
    scene_y = np.full((16, 16), 2.5, dtype=np.float32)
    master = RouteMaster(
        mode="paper",
        route_kind="print_scan",
        route_linear_rgb=np.repeat(route_y[..., None], 3, axis=2),
        route_linear_xyz=np.repeat(route_y[..., None], 3, axis=2),
        route_luminance_y=route_y,
        sdr_legacy_rgb=np.repeat(route_y[..., None], 3, axis=2),
        scene_y_raw=scene_y,
        post_halation_y=scene_y,
        density_cmy=np.repeat(route_y[..., None], 3, axis=2),
        route_look_chroma=None,
        material_detail_y=None,
        diagnostics={},
    )

    result = project_hdr_ideal_paper(master, HDRProjectionConfig(max_headroom=4.0))
    gain = result.gain_map
    high_frequency = np.mean(np.abs(gain[:-1, :-1] - gain[1:, 1:]))

    assert high_frequency < 0.03


def test_grain_shared_between_sdr_and_hdr_projection() -> None:
    checker = (np.indices((10, 10)).sum(axis=0) % 2).astype(np.float32)
    route_y = 0.45 + checker * 0.06
    master = RouteMaster(
        mode="light_table",
        route_kind="film_scan",
        route_linear_rgb=np.repeat(route_y[..., None], 3, axis=2),
        route_linear_xyz=np.repeat(route_y[..., None], 3, axis=2),
        route_luminance_y=route_y,
        sdr_legacy_rgb=np.repeat(route_y[..., None], 3, axis=2),
        scene_y_raw=np.full((10, 10), 3.0, dtype=np.float32),
        post_halation_y=np.full((10, 10), 3.0, dtype=np.float32),
        density_cmy=np.repeat(route_y[..., None], 3, axis=2),
        route_look_chroma=None,
        material_detail_y=None,
        diagnostics={},
    )

    result = project_hdr_light_table(master, HDRProjectionConfig(max_headroom=4.0))
    sdr_texture = result.sdr_rgb[..., 0] - np.mean(result.sdr_rgb[..., 0])
    hdr_texture = result.hdr_rgb[..., 0] - np.mean(result.hdr_rgb[..., 0])
    corr = float(np.corrcoef(sdr_texture.reshape(-1), hdr_texture.reshape(-1))[0, 1])

    assert corr > 0.98
