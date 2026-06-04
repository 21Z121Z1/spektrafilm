from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

import spektrafilm.gpu.kernels.lut as lut_module
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


def test_rgb_to_film_raw_passes_linear_sensitivity_to_hanatos2025(monkeypatch) -> None:
    """`_rgb_to_film_raw` should pass `10**log_sensitivity` (linear sensitivity)
    to `rgb_to_raw_hanatos2025`. With no UV/IR filter active, no bandpass
    correction is applied. Hanatos2025 adaptation is handled separately via
    the LUT service's `tc_lut`, not by mutating sensitivity in this method.
    """
    captured: dict[str, np.ndarray] = {}
    log_sensitivity = np.array([[-1.0, -2.0, -3.0], [-0.5, -1.5, -2.5]], dtype=float)

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
        data=SimpleNamespace(log_sensitivity=log_sensitivity),
    ))
    setattr(stage, '_camera', SimpleNamespace(filter_uv=(0.0, 0.0, 0.0), filter_ir=(0.0, 0.0, 0.0)))
    setattr(stage, '_settings', SimpleNamespace(rgb_to_raw_method='hanatos2025'))
    setattr(stage, '_lut_service', SimpleNamespace(get_filming_tc_lut=lambda sensitivity: None))

    rgb = np.ones((1, 1, 3), dtype=float)

    getattr(stage, '_rgb_to_film_raw')(rgb)

    np.testing.assert_allclose(captured['sensitivity'], 10.0 ** log_sensitivity)


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


class _FakeGpuBackend:
    supports_gpu = True
    fallback_reason = None

    def __init__(self, *, name: str = "mlx", precision: str = "float32"):
        self.name = name
        self.precision = precision
        self.asarray_calls = 0

    def asarray(self, value, dtype=None):
        self.asarray_calls += 1
        return np.asarray(value, dtype=dtype)


def _make_hanatos_stage(*, backend) -> filming_module.FilmingStage:
    stage = object.__new__(filming_module.FilmingStage)
    setattr(stage, '_film', SimpleNamespace(
        info=SimpleNamespace(reference_illuminant='D55'),
        data=SimpleNamespace(log_sensitivity=np.zeros((2, 3), dtype=float)),
    ))
    setattr(stage, '_camera', SimpleNamespace(filter_uv=(0.0, 0.0, 0.0), filter_ir=(0.0, 0.0, 0.0)))
    setattr(stage, '_settings', SimpleNamespace(rgb_to_raw_method='hanatos2025', bandpass_hanatos2025=False))
    setattr(stage, '_backend', backend)
    setattr(stage, '_lut_service', SimpleNamespace(
        get_filming_tc_lut=lambda sensitivity: np.zeros((2, 2, 3), dtype=np.float32),
        get_filming_tc_lut_backend=lambda sensitivity: "prepared-lut",
    ))
    return stage


def test_rgb_to_film_raw_mlx_float32_uses_backend_tc_path(monkeypatch) -> None:
    backend = _FakeGpuBackend(name="mlx", precision="float32")
    stage = _make_hanatos_stage(backend=backend)
    rgb = np.ones((2, 2, 3), dtype=np.float32) * 0.184
    calls: dict[str, object] = {}

    def fail_cpu_rgb_to_tc_b(*_args, **_kwargs):
        raise AssertionError("MLX float32 path must not call CPU _rgb_to_tc_b")

    def fake_rgb_to_tc_b_backend(data, *, color_space, apply_cctf_decoding, reference_illuminant, backend):
        calls['backend_helper'] = {
            'data': data,
            'color_space': color_space,
            'apply_cctf_decoding': apply_cctf_decoding,
            'reference_illuminant': reference_illuminant,
            'backend': backend,
        }
        tc = np.zeros(data.shape[:-1] + (2,), dtype=np.float32)
        b = np.full(data.shape[:-1], 3.0, dtype=np.float32)
        return tc, b

    def fake_apply_lut_cubic_2d_backend(lut, image, backend_arg, *, prepared_lut=None):
        calls['lut'] = lut
        calls['lut_image'] = image
        calls['lut_backend'] = backend_arg
        calls['prepared_lut'] = prepared_lut
        return np.full(image.shape[:-1] + (3,), 2.0, dtype=np.float32)

    monkeypatch.setattr(filming_module, '_rgb_to_tc_b', fail_cpu_rgb_to_tc_b)
    monkeypatch.setattr(filming_module, 'rgb_to_tc_b_backend', fake_rgb_to_tc_b_backend)
    monkeypatch.setattr(lut_module, 'apply_lut_cubic_2d_backend', fake_apply_lut_cubic_2d_backend)

    raw = getattr(stage, '_rgb_to_film_raw')(
        rgb,
        color_space='Display P3',
        apply_cctf_decoding=True,
    )

    np.testing.assert_allclose(raw, np.full((2, 2, 3), 6.0, dtype=np.float32))
    assert calls['backend_helper']['data'] is rgb
    assert calls['backend_helper']['color_space'] == 'Display P3'
    assert calls['backend_helper']['apply_cctf_decoding'] is True
    assert calls['backend_helper']['reference_illuminant'] == 'D55'
    assert calls['backend_helper']['backend'] is backend
    assert calls['lut_backend'] is backend
    assert calls['prepared_lut'] == "prepared-lut"


def test_rgb_to_film_raw_mlx_float16_fails_without_cpu_tc_fallback(monkeypatch) -> None:
    backend = _FakeGpuBackend(name="mlx", precision="float16")
    stage = _make_hanatos_stage(backend=backend)
    rgb = np.ones((2, 2, 3), dtype=np.float32) * 0.184

    def fake_backend_helper(*_args, **_kwargs):
        raise NotImplementedError("rgb_to_tc_b_backend currently supports backend float32 only")

    def fail_cpu_rgb_to_tc_b(*_args, **_kwargs):
        raise AssertionError("GPU filming must not fall back to CPU _rgb_to_tc_b")

    monkeypatch.setattr(filming_module, 'rgb_to_tc_b_backend', fake_backend_helper)
    monkeypatch.setattr(filming_module, '_rgb_to_tc_b', fail_cpu_rgb_to_tc_b)

    with pytest.raises(NotImplementedError, match="float32"):
        getattr(stage, '_rgb_to_film_raw')(rgb)


def test_rgb_to_film_raw_non_mlx_gpu_uses_backend_tc_path(monkeypatch) -> None:
    backend = _FakeGpuBackend(name="cupy", precision="float32")
    stage = _make_hanatos_stage(backend=backend)
    rgb = np.ones((2, 2, 3), dtype=np.float32) * 0.184
    calls: dict[str, object] = {}

    def fail_cpu_rgb_to_tc_b(*_args, **_kwargs):
        raise AssertionError("GPU filming must not fall back to CPU _rgb_to_tc_b")

    def fake_backend_helper(data, *, color_space, apply_cctf_decoding, reference_illuminant, backend):
        calls['backend'] = (data, color_space, apply_cctf_decoding, reference_illuminant, backend)
        return np.zeros(data.shape[:-1] + (2,), dtype=np.float32), np.full(data.shape[:-1], 7.0, dtype=np.float32)

    def fake_apply_lut_cubic_2d_backend(_lut, image, _backend_arg, *, prepared_lut=None):
        calls['prepared_lut'] = prepared_lut
        return np.full(image.shape[:-1] + (3,), 11.0, dtype=np.float32)

    monkeypatch.setattr(filming_module, 'rgb_to_tc_b_backend', fake_backend_helper)
    monkeypatch.setattr(filming_module, '_rgb_to_tc_b', fail_cpu_rgb_to_tc_b)
    monkeypatch.setattr(lut_module, 'apply_lut_cubic_2d_backend', fake_apply_lut_cubic_2d_backend)

    raw = getattr(stage, '_rgb_to_film_raw')(rgb)

    np.testing.assert_allclose(raw, np.full((2, 2, 3), 77.0, dtype=np.float32))
    assert calls['backend'][0] is rgb
    assert calls['backend'][4] is backend
    assert calls['prepared_lut'] == "prepared-lut"
