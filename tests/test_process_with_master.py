from __future__ import annotations

import copy

import numpy as np
import pytest

from spektrafilm.runtime.params_builder import digest_params, init_params
from spektrafilm.runtime.process import Simulator, simulate_with_master
from spektrafilm.utils.gamut_compression import OutputGamutCompressSpec


pytestmark = pytest.mark.integration


def _params(*, scan_film: bool):
    film_profile = "fujifilm_provia_100f" if scan_film else "kodak_portra_400"
    params = init_params(film_profile=film_profile, print_profile="kodak_portra_endura")
    params.debug.deactivate_spatial_effects = True
    params.debug.deactivate_stochastic_effects = True
    params.settings.use_enlarger_lut = False
    params.settings.use_scanner_lut = False
    params.io.output_gamut_compress = OutputGamutCompressSpec(algorithm="off")
    params.io.upscale_factor = 1.0
    params.io.crop = False
    params.io.scan_film = scan_film
    params.camera.auto_exposure = False
    params.camera.exposure_compensation_ev = 0.0
    return digest_params(params)


def _image(size: int = 6) -> np.ndarray:
    ramp = np.linspace(0.03, 1.5, size, dtype=np.float64)
    image = np.ones((size, size, 3), dtype=np.float64)
    image *= ramp[None, :, None]
    image[:, size // 2 :, 0] *= 1.15
    image[:, : size // 2, 2] *= 0.85
    return image


def _assert_master_allclose(actual, expected) -> None:
    assert actual.mode == expected.mode
    assert actual.route_kind == expected.route_kind
    for field in (
        "route_linear_rgb",
        "route_linear_xyz",
        "route_luminance_y",
        "sdr_legacy_rgb",
        "scene_y_raw",
        "post_halation_y",
        "density_cmy",
        "route_look_chroma",
        "material_detail_y",
    ):
        actual_value = getattr(actual, field)
        expected_value = getattr(expected, field)
        if actual_value is None or expected_value is None:
            assert actual_value is expected_value
        else:
            np.testing.assert_allclose(actual_value, expected_value, rtol=0.0, atol=1e-9)
    assert actual.diagnostics == expected.diagnostics


@pytest.mark.parametrize(
    ("hdr_mode", "scan_film"),
    [
        ("paper", False),
        ("light_table", True),
    ],
)
def test_process_with_master_returns_valid_result(hdr_mode: str, scan_film: bool) -> None:
    result = Simulator(_params(scan_film=scan_film)).process_with_master(_image(), hdr_mode=hdr_mode)  # type: ignore[arg-type]

    assert result.image.shape == (6, 6, 3)
    assert result.hdr_scene_energy is not None
    assert result.hdr_scene_energy.scene_luminance.shape == (6, 6)
    assert result.route_master is not None
    assert result.route_master.mode == hdr_mode


@pytest.mark.parametrize(
    ("hdr_mode", "scan_film"),
    [
        ("paper", False),
        ("light_table", True),
    ],
)
def test_process_with_master_image_matches_process_with_metadata(hdr_mode: str, scan_film: bool) -> None:
    params = _params(scan_film=scan_film)
    image = _image()

    with_master = Simulator(copy.deepcopy(params)).process_with_master(image, hdr_mode=hdr_mode)  # type: ignore[arg-type]
    with_metadata = Simulator(copy.deepcopy(params)).process_with_metadata(image)

    np.testing.assert_allclose(with_master.image, with_metadata.image, rtol=1e-5, atol=1e-6)
    np.testing.assert_allclose(
        with_master.hdr_scene_energy.scene_luminance,
        with_metadata.hdr_scene_energy.scene_luminance,
        rtol=1e-5,
        atol=1e-6,
    )


@pytest.mark.parametrize(
    ("hdr_mode", "scan_film"),
    [
        ("paper", False),
        ("light_table", True),
    ],
)
def test_process_with_master_route_master_matches_process_master(hdr_mode: str, scan_film: bool) -> None:
    params = _params(scan_film=scan_film)
    image = _image()

    with_master = Simulator(copy.deepcopy(params)).process_with_master(image, hdr_mode=hdr_mode)  # type: ignore[arg-type]
    master = Simulator(copy.deepcopy(params)).process_master(image, hdr_mode=hdr_mode)  # type: ignore[arg-type]

    _assert_master_allclose(with_master.route_master, master)


def test_simulate_with_master_convenience_function() -> None:
    result = simulate_with_master(_image(), _params(scan_film=False), hdr_mode="paper", digest_params_first=False)

    assert result.route_master is not None
    assert result.route_master.mode == "paper"
