from __future__ import annotations

from types import SimpleNamespace

import colour
import numpy as np

import spektrafilm.runtime.stages.filming as filming_module
from spektrafilm.utils.spectral_upsampling import SpectralInputPolicy


def test_rgb_to_film_raw_applies_hanatos_bandpass_to_sensitivity(monkeypatch) -> None:
    captured: dict[str, np.ndarray] = {}
    bandpass = np.array([[2.0, 3.0, 4.0], [5.0, 6.0, 7.0]], dtype=float)

    def fake_rgb_to_raw_hanatos2025_backend(
        rgb,
        sensitivity,
        *,
        color_space=None,
        apply_cctf_decoding=None,
        reference_illuminant=None,
        tc_lut=None,
        backend=None,
        precomputed=None,
        input_policy=None,
    ):
        del color_space, apply_cctf_decoding, reference_illuminant, tc_lut, backend, precomputed, input_policy
        captured['sensitivity'] = np.asarray(sensitivity, dtype=float)
        return np.ones(rgb.shape, dtype=float)

    monkeypatch.setattr(filming_module, 'rgb_to_raw_hanatos2025_backend', fake_rgb_to_raw_hanatos2025_backend)

    stage = object.__new__(filming_module.FilmingStage)
    setattr(stage, '_film', SimpleNamespace(
        info=SimpleNamespace(reference_illuminant='D55'),
        data=SimpleNamespace(
            log_sensitivity=np.zeros((2, 3), dtype=float),
            bandpass_hanatos2025=bandpass,
        ),
    ))
    setattr(stage, '_camera', SimpleNamespace(filter_uv=(0.0, 0.0, 0.0), filter_ir=(0.0, 0.0, 0.0)))
    setattr(stage, '_settings', SimpleNamespace(rgb_to_raw_method='hanatos2025', bandpass_hanatos2025=True))
    setattr(stage, '_lut_service', SimpleNamespace(get_filming_tc_lut=lambda sensitivity: None))
    setattr(stage, '_backend', None)

    rgb = np.ones((1, 1, 3), dtype=float)

    getattr(stage, '_rgb_to_film_raw')(rgb)

    np.testing.assert_allclose(captured['sensitivity'], bandpass)


def test_compute_density_midgray_encodes_reference_when_input_uses_cctf() -> None:
    stage = object.__new__(filming_module.FilmingStage)
    setattr(stage, '_io', SimpleNamespace(input_color_space='sRGB', input_cctf_decoding=True))
    setattr(stage, '_camera', SimpleNamespace(exposure_compensation_ev=1.0))
    setattr(stage, '_enlarger_service', SimpleNamespace(print_exposure_compensation=True))

    captured: list[np.ndarray] = []

    def fake_density(rgb):
        captured.append(np.asarray(rgb, dtype=float).copy())
        return np.asarray(rgb, dtype=float)

    setattr(stage, '_simple_rgb_to_density_spectral', fake_density)

    density, density_comp = getattr(stage, '_compute_density_spectral_midgray_to_balance_print')()

    expected = colour.RGB_COLOURSPACES['sRGB'].cctf_encoding(np.full((1, 1, 3), 0.184, dtype=float))
    expected_comp = colour.RGB_COLOURSPACES['sRGB'].cctf_encoding(np.full((1, 1, 3), 0.368, dtype=float))
    np.testing.assert_allclose(captured[0], expected, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(captured[1], expected_comp, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(density, expected)
    np.testing.assert_allclose(density_comp, expected_comp)


def test_rgb_to_film_raw_passes_spectral_input_policy(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_rgb_to_raw_hanatos2025_backend(
        rgb,
        sensitivity,
        *,
        color_space=None,
        apply_cctf_decoding=None,
        reference_illuminant=None,
        tc_lut=None,
        backend=None,
        precomputed=None,
        input_policy=None,
    ):
        del sensitivity, color_space, apply_cctf_decoding, reference_illuminant, tc_lut, backend, precomputed
        captured['input_policy'] = input_policy
        return np.ones(rgb.shape, dtype=float)

    monkeypatch.setattr(filming_module, 'rgb_to_raw_hanatos2025_backend', fake_rgb_to_raw_hanatos2025_backend)

    stage = object.__new__(filming_module.FilmingStage)
    setattr(stage, '_film', SimpleNamespace(
        info=SimpleNamespace(reference_illuminant='D55'),
        data=SimpleNamespace(
            log_sensitivity=np.zeros((2, 3), dtype=float),
            bandpass_hanatos2025=np.ones((2, 3), dtype=float),
        ),
    ))
    setattr(stage, '_camera', SimpleNamespace(filter_uv=(0.0, 0.0, 0.0), filter_ir=(0.0, 0.0, 0.0)))
    setattr(stage, '_settings', SimpleNamespace(
        rgb_to_raw_method='hanatos2025',
        bandpass_hanatos2025=False,
        spectral_negative_rgb='error',
        spectral_xy_out_of_bounds='warn',
        spectral_report_stats=False,
    ))
    setattr(stage, '_lut_service', SimpleNamespace(get_filming_tc_lut=lambda sensitivity: None))
    setattr(stage, '_backend', None)

    getattr(stage, '_rgb_to_film_raw')(np.ones((1, 1, 3), dtype=float))

    assert captured['input_policy'] == SpectralInputPolicy(
        negative_rgb='error',
        xy_out_of_bounds='warn',
        report_stats=False,
    )
