from __future__ import annotations

import numpy as np
import pytest

from spektrafilm.hdr import HDRDisplayProfile, HDRProjectionConfig, project_hdr_ideal_paper
from spektrafilm.runtime.route_master import RouteMaster
from spektrafilm.utils.hdr_curve_profiles import luminance_y


def _master(
    *,
    route_rgb: np.ndarray,
    sdr_rgb: np.ndarray | None = None,
    scene_y: np.ndarray | None = None,
    route_look_chroma: np.ndarray | None = None,
    material_detail_y: np.ndarray | None = None,
) -> RouteMaster:
    route_rgb = np.asarray(route_rgb, dtype=np.float32)
    shape = route_rgb.shape[:2]
    if sdr_rgb is None:
        sdr_rgb = np.clip(route_rgb, 0.0, 1.0)
    if scene_y is None:
        scene_y = luminance_y(route_rgb)
    return RouteMaster(
        mode="paper",
        route_kind="print_scan",
        route_linear_rgb=route_rgb,
        route_linear_xyz=route_rgb,
        route_luminance_y=luminance_y(route_rgb),
        sdr_legacy_rgb=np.asarray(sdr_rgb, dtype=np.float32),
        scene_y_raw=np.asarray(scene_y, dtype=np.float32),
        post_halation_y=np.asarray(scene_y, dtype=np.float32),
        density_cmy=np.zeros(shape + (3,), dtype=np.float32),
        route_look_chroma=route_look_chroma,
        material_detail_y=material_detail_y,
        diagnostics={"output_cctf_encoding": False, "output_color_space": "Display P3"},
    )


def test_display_profile_overrides_legacy_headroom_fields_and_reports_linear_pair() -> None:
    profile = HDRDisplayProfile(
        profile_id="test-p3-1000",
        color_primaries="P3-D65",
        output_color_volume="P3-D65 1000 nit",
        transfer_function="gain-map-linear-pair",
        reference_white_nits=250.0,
        peak_nits=1000.0,
        black_nits=0.01,
        output_diffuse_white=1.1,
        content_headroom_percentile=98.0,
    )
    config = HDRProjectionConfig(max_headroom=8.0, headroom_percentile=99.9, display_profile=profile)

    assert config.max_headroom == pytest.approx(4.0)
    assert config.headroom_percentile == pytest.approx(98.0)
    assert config.display_reference_white_nits == pytest.approx(250.0)
    assert config.output_diffuse_white == pytest.approx(1.1)

    route = np.full((1, 2, 3), 0.5, dtype=np.float32)
    master = _master(route_rgb=route, scene_y=np.array([[1.0, 4.0]], dtype=np.float32))
    result = project_hdr_ideal_paper(master, config)

    diagnostics = result.diagnostics["display_profile"]
    assert diagnostics["id"] == "test-p3-1000"
    assert diagnostics["transfer_function"] == "gain-map-linear-pair"
    assert diagnostics["gain_map_pair_encoding"] == "linear_sdr_base_plus_linear_hdr_alternate"
    assert result.standards_metadata.reference_white_nits == pytest.approx(250.0)
    assert result.standards_metadata.target_display_min_luminance_nits == pytest.approx(0.01)


def test_legacy_projection_config_builds_backwards_compatible_display_profile() -> None:
    config = HDRProjectionConfig(max_headroom=5.0, headroom_percentile=100.0, display_reference_white_nits=203.0)

    assert config.display_profile is not None
    assert config.display_profile.transfer_function == "gain-map-linear-pair"
    assert config.display_profile.reference_white_nits == pytest.approx(203.0)
    assert config.display_profile.peak_nits == pytest.approx(1015.0)
    assert config.display_profile.content_headroom_percentile == pytest.approx(100.0)


def test_hdr_ramp_is_finite_nonnegative_and_monotonic() -> None:
    ramp = np.linspace(0.1, 1.0, 8, dtype=np.float32).reshape(1, -1, 1)
    route = np.repeat(ramp, 3, axis=2)
    scene = np.linspace(0.1, 8.0, 8, dtype=np.float32).reshape(1, -1)
    master = _master(route_rgb=route, scene_y=scene)

    result = project_hdr_ideal_paper(master, HDRProjectionConfig(max_headroom=6.0, headroom_percentile=100.0))

    y = result.hdr_luminance_y.reshape(-1)
    assert np.all(np.isfinite(result.hdr_rgb))
    assert np.all(result.hdr_rgb >= 0.0)
    assert np.all(np.diff(y) >= -1e-6)


def test_sdr_base_and_diffuse_white_join_are_preserved() -> None:
    route = np.full((1, 4, 3), 0.45, dtype=np.float32)
    scene = np.array([[0.5, 1.0, 1.02, 4.0]], dtype=np.float32)
    master = _master(route_rgb=route, scene_y=scene)
    config = HDRProjectionConfig(max_headroom=5.0, headroom_percentile=100.0, diffuse_white_scene_anchor=1.0)

    result = project_hdr_ideal_paper(master, config)

    np.testing.assert_allclose(result.hdr_rgb[0, :2], result.sdr_rgb[0, :2], rtol=0.0, atol=1e-7)
    assert float(np.max(result.hdr_rgb[0, 2] - result.sdr_rgb[0, 2])) < 0.01
    assert float(np.max(result.hdr_rgb[0, 3] - result.sdr_rgb[0, 3])) > 0.1
    assert result.diagnostics["measured_content_headroom"] >= 1.0


def test_highlight_headroom_is_not_darker_than_sdr_base() -> None:
    route = np.full((1, 3, 3), 0.35, dtype=np.float32)
    scene = np.array([[1.0, 2.5, 7.0]], dtype=np.float32)
    master = _master(route_rgb=route, scene_y=scene)

    result = project_hdr_ideal_paper(master, HDRProjectionConfig(max_headroom=5.0, headroom_percentile=100.0))

    hdr_y = result.hdr_luminance_y
    sdr_y = luminance_y(result.sdr_rgb)
    assert np.all(hdr_y + 1e-6 >= sdr_y)
    assert float(hdr_y[0, -1] - sdr_y[0, -1]) > 0.1


def test_saturated_highlights_preserve_dominant_hue_without_silent_clip() -> None:
    colors = np.array(
        [
            [1.0, 0.05, 0.05],
            [0.05, 1.0, 0.05],
            [0.05, 0.05, 1.0],
            [0.05, 1.0, 1.0],
            [1.0, 1.0, 0.05],
        ],
        dtype=np.float32,
    ).reshape(1, 5, 3)
    chroma = colors / np.maximum(luminance_y(colors)[..., None], np.float32(1e-8)) * np.float32(2.0)
    sdr = colors * np.float32(0.35)
    scene = np.full((1, 5), 8.0, dtype=np.float32)
    master = _master(route_rgb=sdr, sdr_rgb=sdr, scene_y=scene, route_look_chroma=chroma)

    result = project_hdr_ideal_paper(
        master,
        HDRProjectionConfig(
            max_headroom=2.0,
            headroom_percentile=100.0,
            output_diffuse_white=3.0,
            paper_path_to_white_strength=0.0,
        ),
    )

    dominant = np.argmax(colors.reshape(5, 3), axis=1)
    projected = result.hdr_rgb.reshape(5, 3)
    assert np.all(np.argmax(projected, axis=1) == dominant)
    assert result.diagnostics["highlight_gamut_strategy"] == "luminance_preserving_chroma_compression"
    assert result.diagnostics["highlight_gamut_compressed_pixels"] > 0


def test_material_detail_only_modulates_highlight_extension() -> None:
    route = np.full((1, 5, 3), 0.4, dtype=np.float32)
    scene = np.array([[0.5, 1.0, 1.05, 2.0, 5.0]], dtype=np.float32)
    detail = np.array([[1.25, 0.75, 1.25, 1.25, 0.75]], dtype=np.float32)
    master = _master(route_rgb=route, scene_y=scene, material_detail_y=detail)
    no_detail = _master(route_rgb=route, scene_y=scene, material_detail_y=np.ones_like(detail))
    config = HDRProjectionConfig(max_headroom=5.0, headroom_percentile=100.0)

    result = project_hdr_ideal_paper(master, config)
    baseline = project_hdr_ideal_paper(no_detail, config)

    np.testing.assert_allclose(result.hdr_rgb[0, :2], baseline.hdr_rgb[0, :2], rtol=0.0, atol=1e-7)
    assert abs(float(result.hdr_luminance_y[0, 2] - baseline.hdr_luminance_y[0, 2])) < 0.01
    assert float(result.hdr_luminance_y[0, 3] - baseline.hdr_luminance_y[0, 3]) > 0.005
    assert float(result.hdr_luminance_y[0, 4] - baseline.hdr_luminance_y[0, 4]) < -0.01
    assert result.diagnostics["highlight_detail_strategy"] == "highlight_extension_only"
