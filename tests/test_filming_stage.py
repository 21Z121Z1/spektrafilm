from __future__ import annotations

from types import SimpleNamespace

import numpy as np

import spektrafilm.runtime.stages.filming as filming_module


def test_rgb_to_film_raw_applies_hanatos_bandpass_to_sensitivity(monkeypatch) -> None:
    captured: dict[str, np.ndarray] = {}
    bandpass = np.array([[2.0, 3.0, 4.0], [5.0, 6.0, 7.0]], dtype=float)

    def fake_rgb_to_raw_hanatos2025(
        rgb,
        sensitivity,
        *,
        color_space=None,
        apply_cctf_decoding=None,
        reference_illuminant=None,
        tc_lut=None,
    ):
        del color_space, apply_cctf_decoding, reference_illuminant, tc_lut
        captured['sensitivity'] = np.asarray(sensitivity, dtype=float)
        return np.ones(rgb.shape, dtype=float)

    monkeypatch.setattr(filming_module, 'rgb_to_raw_hanatos2025', fake_rgb_to_raw_hanatos2025)

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

    rgb = np.ones((1, 1, 3), dtype=float)

    getattr(stage, '_rgb_to_film_raw')(rgb)

    np.testing.assert_allclose(captured['sensitivity'], bandpass)


def test_simple_midgray_density_uses_active_input_encoding(monkeypatch) -> None:
    captured: dict[str, object] = {}

    stage = object.__new__(filming_module.FilmingStage)
    setattr(stage, '_io', SimpleNamespace(input_color_space='Display P3', input_cctf_decoding=True))
    setattr(stage, '_film_render', SimpleNamespace(density_curve_gamma=1.0))
    setattr(stage, '_film', SimpleNamespace(
        data=SimpleNamespace(
            log_exposure=np.array([0.0], dtype=float),
            density_curves=np.zeros((1, 3), dtype=float),
            channel_density=np.zeros((1, 3), dtype=float),
            base_density=np.zeros(1, dtype=float),
        ),
    ))

    def fake_rgb_to_film_raw(rgb, *, color_space, apply_cctf_decoding, use_backend):
        captured['rgb'] = np.asarray(rgb)
        captured['color_space'] = color_space
        captured['apply_cctf_decoding'] = apply_cctf_decoding
        captured['use_backend'] = use_backend
        return np.ones_like(rgb, dtype=float)

    monkeypatch.setattr(stage, '_rgb_to_film_raw', fake_rgb_to_film_raw)
    monkeypatch.setattr(filming_module, 'develop_simple', lambda log_raw, *args, **kwargs: log_raw)
    monkeypatch.setattr(filming_module, 'compute_density_spectral', lambda channel_density, density_cmy, *, base_density: density_cmy)

    getattr(stage, '_simple_rgb_to_density_spectral')(np.full((1, 1, 3), 0.184, dtype=float))

    assert captured['color_space'] == 'Display P3'
    assert captured['apply_cctf_decoding'] is True
    assert captured['use_backend'] is False
