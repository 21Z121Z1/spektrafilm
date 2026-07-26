from __future__ import annotations

import copy
from dataclasses import replace

import numpy as np
import pytest

import spektrafilm.hdr.projection as projection_module
from spektrafilm.hdr import (
    HDRProjectionConfig,
    project_hdr_ideal_paper,
    project_hdr_light_table,
)
from spektrafilm.runtime.params_builder import digest_params, init_params
from spektrafilm.runtime.process import Simulator
from spektrafilm.runtime.route_master import RouteMaster
from spektrafilm.utils.hdr_curve_profiles import luminance_y


pytestmark = pytest.mark.integration


def _fast_params_before_digest(*, film_profile: str = "kodak_portra_400", print_profile: str = "kodak_portra_endura"):
    params = init_params(film_profile=film_profile, print_profile=print_profile)
    params.debug.deactivate_spatial_effects = True
    params.debug.deactivate_stochastic_effects = True
    params.settings.use_enlarger_lut = False
    params.settings.use_scanner_lut = False
    params.io.upscale_factor = 1.0
    params.io.crop = False
    params.camera.auto_exposure = False
    params.camera.exposure_compensation_ev = 0.0
    return params


def make_fast_test_params(*, film_profile: str = "kodak_portra_400", print_profile: str = "kodak_portra_endura"):
    params = _fast_params_before_digest(film_profile=film_profile, print_profile=print_profile)
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


def _paper_master_for_sdr_encoding(*, output_cctf_encoding: bool) -> RouteMaster:
    sdr_rgb = np.array([[[0.6, 0.5, 0.4]]], dtype=np.float32)
    route_rgb = np.array([[[0.3, 0.5, 0.7]]], dtype=np.float32)
    scene = np.array([[0.5]], dtype=np.float32)
    return RouteMaster(
        mode="paper",
        route_kind="print_scan",
        route_linear_rgb=route_rgb,
        route_linear_xyz=route_rgb,
        route_luminance_y=np.array([[0.5]], dtype=np.float32),
        sdr_legacy_rgb=sdr_rgb,
        scene_y_raw=scene,
        post_halation_y=scene,
        density_cmy=sdr_rgb,
        route_look_chroma=None,
        material_detail_y=None,
        diagnostics={
            "output_color_space": "Display P3",
            "output_cctf_encoding": output_cctf_encoding,
        },
    )


def _small_patch() -> np.ndarray:
    ramp = np.linspace(0.05, 1.25, 5, dtype=np.float64)
    return np.repeat(ramp.reshape(1, -1, 1), 5, axis=0).repeat(3, axis=2)


def _project_paper_hdr_rgb(params, image: np.ndarray) -> np.ndarray:
    master = Simulator(copy.deepcopy(params)).process_master(image, hdr_mode="paper")
    result = project_hdr_ideal_paper(master, HDRProjectionConfig(max_headroom=4.0, headroom_percentile=100.0))
    return result.hdr_rgb


def _assert_paper_hdr_changes(base_params, changed_params) -> None:
    image = _small_patch()
    base = _project_paper_hdr_rgb(base_params, image)
    changed = _project_paper_hdr_rgb(changed_params, image)
    assert not np.allclose(changed, base, atol=1e-4)


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


def test_paper_mode_responds_to_camera_exposure() -> None:
    base_params = make_fast_test_params()
    changed_params = copy.deepcopy(base_params)
    changed_params.camera.exposure_compensation_ev = 1.0

    _assert_paper_hdr_changes(base_params, changed_params)


def test_paper_mode_responds_to_film_stock() -> None:
    base_params = make_fast_test_params(film_profile="kodak_portra_400")
    changed_params = make_fast_test_params(film_profile="kodak_gold_200")

    _assert_paper_hdr_changes(base_params, changed_params)


def test_paper_mode_responds_to_enlarger_filter_color_adjustments() -> None:
    base_params = make_fast_test_params()
    changed_params = copy.deepcopy(base_params)
    changed_params.enlarger.y_filter_shift = 40.0
    changed_params.enlarger.m_filter_shift = 60.0

    _assert_paper_hdr_changes(base_params, changed_params)


def test_paper_mode_responds_to_film_density_gamma() -> None:
    base_params = make_fast_test_params()
    changed_raw_params = _fast_params_before_digest()
    changed_raw_params.film_render.density_curve_gamma = 1.35
    changed_params = digest_params(changed_raw_params)

    _assert_paper_hdr_changes(base_params, changed_params)


def test_paper_mode_responds_to_print_density_curve_morph() -> None:
    base_params = make_fast_test_params()
    changed_raw_params = _fast_params_before_digest()
    changed_raw_params.print_render.density_curves_morph = replace(
        changed_raw_params.print_render.density_curves_morph,
        active=True,
        gamma_factor=1.3,
    )
    changed_params = digest_params(changed_raw_params)

    _assert_paper_hdr_changes(base_params, changed_params)


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


def test_negative_positive_scan_route_xyz_not_rgb_alias() -> None:
    params = make_fast_test_params(film_profile="kodak_gold_200")
    params.settings.hdr_route_sidecar_policy = "full"
    master = Simulator(params).process_master(_small_patch(), hdr_mode="light_table")

    assert master.diagnostics["profile_kind"] == "positive_negative_scan"
    assert master.diagnostics["route_linear_xyz_source"] == "positive_render_rgb_to_xyz"
    assert master.route_linear_xyz.shape == master.route_linear_rgb.shape
    assert np.all(np.isfinite(master.route_linear_xyz))
    assert not np.allclose(master.route_linear_xyz, master.route_linear_rgb, rtol=0.0, atol=1e-6)


def test_projection_respects_linear_sdr_without_cctf_decode() -> None:
    master = _paper_master_for_sdr_encoding(output_cctf_encoding=False)
    result = project_hdr_ideal_paper(master)

    np.testing.assert_allclose(result.sdr_rgb, master.sdr_legacy_rgb, rtol=0.0, atol=1e-7)
    np.testing.assert_allclose(result.hdr_rgb, master.sdr_legacy_rgb, rtol=0.0, atol=1e-7)
    np.testing.assert_allclose(result.gain_map, 0.0, atol=1e-5)


def test_projection_decodes_cctf_sdr_once() -> None:
    master = _paper_master_for_sdr_encoding(output_cctf_encoding=True)
    result = project_hdr_ideal_paper(master)

    expected_linear = np.array([[[
        ((0.6 + 0.055) / 1.055) ** 2.4,
        ((0.5 + 0.055) / 1.055) ** 2.4,
        ((0.4 + 0.055) / 1.055) ** 2.4,
    ]]], dtype=np.float32)
    np.testing.assert_allclose(result.sdr_rgb, expected_linear, rtol=1e-3)
    np.testing.assert_allclose(result.hdr_rgb, expected_linear, rtol=1e-3)


def test_paper_white_anchor_changes_hdr_join() -> None:
    scene = np.array([[0.9]], dtype=np.float32)
    route = np.array([[0.45]], dtype=np.float32)
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
        diagnostics={"output_cctf_encoding": False},
    )

    below = project_hdr_ideal_paper(master, HDRProjectionConfig(max_headroom=4.0, paper_white=1.0))
    above = project_hdr_ideal_paper(master, HDRProjectionConfig(max_headroom=4.0, paper_white=0.8))

    np.testing.assert_allclose(below.hdr_rgb, below.sdr_rgb, rtol=0.0, atol=1e-7)
    # The extension span is fixed at max_headroom (content-independent), so a
    # pixel 0.125 ratio above the anchor receives a small but strictly
    # positive extension; the join moving is the property under test.
    assert float(np.max(above.hdr_rgb - above.sdr_rgb)) > 5e-5


def test_diffuse_white_scene_anchor_replaces_paper_white_alias() -> None:
    config = HDRProjectionConfig(max_headroom=4.0, diffuse_white_scene_anchor=0.8)

    assert config.diffuse_white_scene_anchor == 0.8
    assert config.paper_white == 0.8


def test_conflicting_diffuse_white_aliases_raise() -> None:
    with pytest.raises(ValueError, match="diffuse_white_scene_anchor and paper_white"):
        HDRProjectionConfig(diffuse_white_scene_anchor=0.8, paper_white=1.0)


def test_output_diffuse_white_scales_hdr_extension_and_gain_map() -> None:
    master = _synthetic_master(mode="paper", route_kind="print_scan")
    base_config = HDRProjectionConfig(
        max_headroom=4.0,
        diffuse_white_scene_anchor=0.75,
        output_diffuse_white=1.0,
    )
    lifted_config = HDRProjectionConfig(
        max_headroom=4.0,
        diffuse_white_scene_anchor=0.75,
        output_diffuse_white=1.25,
    )

    base = project_hdr_ideal_paper(master, base_config)
    lifted = project_hdr_ideal_paper(master, lifted_config)

    below_or_at_white = master.scene_y_raw <= lifted_config.diffuse_white_scene_anchor
    np.testing.assert_allclose(
        lifted.hdr_rgb[below_or_at_white],
        lifted.sdr_rgb[below_or_at_white],
        rtol=0.0,
        atol=1e-7,
    )
    above_white = master.scene_y_raw > lifted_config.diffuse_white_scene_anchor
    assert float(np.max(lifted.hdr_rgb[above_white] - base.hdr_rgb[above_white])) > 1e-3
    assert float(np.max(lifted.gain_map - base.gain_map)) > 1e-3
    assert lifted.diagnostics["diffuse_white_scene_anchor"] == pytest.approx(0.75)
    assert lifted.diagnostics["output_diffuse_white"] == pytest.approx(1.25)
    assert lifted.diagnostics["output_diffuse_white_effect"] == "hdr_delta_from_sdr"
    assert lifted.diagnostics["preserve_sdr_base"] is True


def test_paper_projection_uses_safe_chemical_print_profile() -> None:
    master = _synthetic_master(
        mode="paper",
        route_kind="print_scan",
        diagnostics={
            "film": "kodak_portra_400",
            "paper": "kodak_portra_endura",
            "output_cctf_encoding": False,
        },
    )

    result = project_hdr_ideal_paper(master, HDRProjectionConfig(max_headroom=5.0, headroom_percentile=100.0))

    assert result.diagnostics["paper_rolloff_strategy"] == "chemical_print"
    assert result.diagnostics["chemical_profile_source"] == "kodak_portra_400__kodak_portra_endura"
    assert result.diagnostics["chemical_profile_safe"] is True
    below_or_at_white = master.scene_y_raw <= 1.0
    np.testing.assert_allclose(
        result.hdr_rgb[below_or_at_white],
        result.sdr_rgb[below_or_at_white],
        rtol=0.0,
        atol=1e-7,
    )
    sdr_y = luminance_y(result.sdr_rgb)
    assert float(np.max(result.hdr_luminance_y[master.scene_y_raw > 1.0] - sdr_y[master.scene_y_raw > 1.0])) > 1e-3


def test_paper_projection_display_budget_creates_hdr_when_paper_sdr_is_low() -> None:
    master = _synthetic_master(
        mode="paper",
        route_kind="print_scan",
        route_scale=0.6,
        diagnostics={
            "film": "kodak_gold_200",
            "paper": "kodak_supra_endura",
            "output_cctf_encoding": False,
        },
    )
    config = HDRProjectionConfig(max_headroom=8.0, headroom_percentile=99.9)

    result = project_hdr_ideal_paper(master, config)

    assert float(np.nanpercentile(master.scene_y_raw, 99.9)) > 3.0
    assert float(np.max(luminance_y(result.sdr_rgb))) <= 0.6
    np.testing.assert_allclose(result.sdr_rgb, master.sdr_legacy_rgb, rtol=0.0, atol=1e-7)

    below_or_at_white = master.scene_y_raw <= config.diffuse_white_scene_anchor
    np.testing.assert_allclose(
        result.hdr_rgb[below_or_at_white],
        result.sdr_rgb[below_or_at_white],
        rtol=0.0,
        atol=1e-7,
    )
    assert result.diagnostics["paper_rolloff_strategy"] == "chemical_print"
    assert result.diagnostics["paper_headroom_strategy"] == "chemical_display_budget"
    assert result.diagnostics["paper_display_extension_strength_used"] > 0.0
    assert result.headroom > 1.0
    assert float(np.max(result.hdr_rgb)) > 1.0


def test_high_tint_chemical_profile_reduces_path_to_white_strength() -> None:
    master = _synthetic_master(
        mode="paper",
        route_kind="print_scan",
        diagnostics={
            "film": "fujifilm_c200",
            "paper": "kodak_2393",
            "output_cctf_encoding": False,
        },
    )
    config = HDRProjectionConfig(
        max_headroom=5.0,
        headroom_percentile=100.0,
        paper_path_to_white_strength=0.2,
    )

    result = project_hdr_ideal_paper(master, config)

    assert result.diagnostics["paper_rolloff_strategy"] == "chemical_print"
    assert result.diagnostics["chemical_highlight_tint_spread"] > 0.12
    assert result.diagnostics["paper_path_to_white_strength_used"] == pytest.approx(0.1)


def test_safe_chemical_profile_without_scene_headroom_falls_back() -> None:
    master = _synthetic_master(
        mode="paper",
        route_kind="print_scan",
        scene_scale=0.1,
        diagnostics={
            "film": "kodak_portra_400",
            "paper": "kodak_portra_endura",
            "output_cctf_encoding": False,
        },
    )

    result = project_hdr_ideal_paper(master, HDRProjectionConfig(max_headroom=5.0))

    assert result.diagnostics["paper_rolloff_strategy"] == "generic_scene_extension"
    assert result.diagnostics["chemical_profile_safe"] is True
    assert result.diagnostics["chemical_fallback_reason"] == "no_scene_headroom"
    np.testing.assert_allclose(result.hdr_rgb, result.sdr_rgb, rtol=0.0, atol=1e-7)


def test_paper_projection_falls_back_without_chemical_profile_identity() -> None:
    master = _synthetic_master(mode="paper", route_kind="print_scan")

    result = project_hdr_ideal_paper(master, HDRProjectionConfig(max_headroom=5.0, headroom_percentile=100.0))

    assert result.diagnostics["paper_rolloff_strategy"] == "generic_scene_extension"
    assert result.diagnostics["chemical_profile_safe"] is False
    assert result.diagnostics["chemical_fallback_reason"] == "missing_film_or_paper_identifier"


def test_paper_projection_rejects_unsafe_chemical_print_profile() -> None:
    master = _synthetic_master(
        mode="paper",
        route_kind="print_scan",
        diagnostics={
            "film": "fujifilm_velvia_100",
            "paper": "fujifilm_crystal_archive_typeii",
            "output_cctf_encoding": False,
        },
    )

    result = project_hdr_ideal_paper(master, HDRProjectionConfig(max_headroom=5.0, headroom_percentile=100.0))

    assert result.diagnostics["paper_rolloff_strategy"] == "generic_scene_extension"
    assert result.diagnostics["chemical_profile_safe"] is False
    assert result.diagnostics["chemical_fallback_reason"] in {
        "profile_marked_unsafe",
        "profile_not_increasing",
        "negative_highlight_slope",
    }


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
    from spektrafilm.hdr.projection import _sdr_rgb

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

    result = project_hdr_ideal_paper(master, HDRProjectionConfig(max_headroom=3.0, paper_white=1.0))
    y = result.hdr_luminance_y.reshape(-1)
    join_index = int(np.argmin(np.abs(scene.reshape(-1) - 1.0)))

    sdr_rgb = _sdr_rgb(master)
    expected_join_val = float(luminance_y(sdr_rgb).reshape(-1)[join_index])
    assert abs(float(y[join_index]) - expected_join_val) < 0.03
    assert float(np.max(np.abs(np.diff(y)))) < 0.08


def test_chunked_projection_materialization_is_exact(monkeypatch) -> None:
    rng = np.random.default_rng(711)
    shape = (129, 131)
    route_rgb = rng.random(shape + (3,), dtype=np.float32) * np.float32(1.2)
    sdr_rgb = rng.random(shape + (3,), dtype=np.float32)
    master = RouteMaster(
        mode="paper",
        route_kind="print_scan",
        route_linear_rgb=route_rgb,
        route_linear_xyz=route_rgb,
        route_luminance_y=route_rgb[..., 1],
        sdr_legacy_rgb=sdr_rgb,
        scene_y_raw=sdr_rgb[..., 0],
        diagnostics={"output_cctf_encoding": True, "output_color_space": "sRGB"},
    )

    monkeypatch.setattr(projection_module, "_CHUNKED_PROJECTION_MIN_PIXELS", 10**12)
    expected_sdr = projection_module._sdr_rgb(master)
    expected_chroma = projection_module._route_chroma(master, shape)
    monkeypatch.setattr(projection_module, "_CHUNKED_PROJECTION_MIN_PIXELS", 0)

    np.testing.assert_array_equal(projection_module._sdr_rgb(master), expected_sdr)
    np.testing.assert_array_equal(projection_module._route_chroma(master, shape), expected_chroma)


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


def _negative_scene(*, cast: tuple[float, float, float] = (1.0, 1.0, 1.0), highlight: bool = True) -> np.ndarray:
    height, width = 12, 12
    ramp = np.linspace(0.05, 0.9, height, dtype=np.float64).reshape(-1, 1, 1)
    image = np.repeat(np.repeat(ramp, width, axis=1), 3, axis=2)
    image[2:5, 2:5] = [0.45, 0.10, 0.08]
    image[2:5, 6:9] = [0.08, 0.12, 0.55]
    if highlight:
        image[8:11, 8:11] = 5.0
    return np.ascontiguousarray(image * np.asarray(cast, dtype=np.float64))


def test_light_table_negative_positive_render_is_composition_independent() -> None:
    params = make_fast_test_params()
    full = _negative_scene()
    m_full = Simulator(copy.deepcopy(params)).process_master(full, hdr_mode="light_table")
    assert m_full.diagnostics["negative_scan_render_origin"] in (
        "dynamic_resample",
        "dynamic_resample_cached",
    )

    crop = np.ascontiguousarray(full[4:10, :8])
    m_crop = Simulator(copy.deepcopy(params)).process_master(crop, hdr_mode="light_table")

    # The calibration comes from the film profile, not from image content,
    # so reframing the same scene must not change the rendered pixels.
    np.testing.assert_allclose(
        np.asarray(m_full.sdr_legacy_rgb, dtype=np.float32)[4:10, :8],
        np.asarray(m_crop.sdr_legacy_rgb, dtype=np.float32),
        rtol=0.0,
        atol=1e-5,
    )


def test_light_table_negative_positive_render_preserves_scene_cast() -> None:
    params = make_fast_test_params()
    neutral_scene = _negative_scene(cast=(1.0, 1.0, 1.0), highlight=False)
    warm_scene = _negative_scene(cast=(1.3, 1.0, 0.6), highlight=False)
    neutral = Simulator(copy.deepcopy(params)).process_master(neutral_scene, hdr_mode="light_table")
    warm = Simulator(copy.deepcopy(params)).process_master(warm_scene, hdr_mode="light_table")

    probe = np.s_[6:8, 2:10]

    def red_blue_ratio(master: RouteMaster) -> float:
        rgb = np.asarray(master.sdr_legacy_rgb, dtype=np.float32)[probe].reshape(-1, 3).mean(axis=0)
        return float(rgb[0]) / max(float(rgb[2]), 1e-6)

    # A global illuminant cast must survive the positive render instead of
    # being auto-white-balanced away by content statistics.
    assert red_blue_ratio(warm) / red_blue_ratio(neutral) > 1.25


def test_light_table_preserves_sdr_base_below_anchor() -> None:
    for film in ("kodak_portra_400", "fujifilm_provia_100f"):
        params = make_fast_test_params(film_profile=film)
        master = Simulator(params).process_master(_negative_scene(), hdr_mode="light_table")
        result = project_hdr_light_table(master, HDRProjectionConfig(max_headroom=8.0, headroom_percentile=100.0))

        authority = np.asarray(master.post_halation_y, dtype=np.float32)
        below = authority <= np.float32(1.0)
        assert below.any(), film
        np.testing.assert_allclose(
            np.asarray(result.hdr_rgb, dtype=np.float32)[below],
            np.asarray(result.sdr_rgb, dtype=np.float32)[below],
            rtol=0.0,
            atol=1e-6,
            err_msg=film,
        )


def test_light_table_path_to_white_is_active() -> None:
    master = _synthetic_master()
    result = project_hdr_light_table(master, HDRProjectionConfig(max_headroom=4.0, headroom_percentile=100.0))

    assert float(result.diagnostics["path_to_white_strength_input"]) > 0.0
    assert float(result.diagnostics["path_to_white_strength_effective"]) > 0.0
