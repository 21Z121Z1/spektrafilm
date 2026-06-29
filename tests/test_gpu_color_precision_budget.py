from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from opt_einsum import contract

import spektrafilm.gpu.kernels.gamut_compress as gamut_backend_module
import spektrafilm.runtime.stages.filming as filming_module
from spektrafilm.gpu.kernels.color import (
    _cctf_encoding_srgb_like,
    cctf_decoding_transfer_backend,
    cctf_encoding_backend,
    precompute_rgb_to_xyz_matrix,
    precompute_xyz_to_rgb_matrix,
    rgb_to_xyz,
    xyz_to_rgb,
)
from spektrafilm.gpu.kernels.gamut_compress import compress_rgb_backend
from spektrafilm.gpu.precision_policy import (
    OP_GAMUT_JZAZBZ,
    OP_LUT_2D_MITCHELL,
    OP_SPECTRAL_REDUCTION,
    precision_decision,
    precision_metrics,
)
from spektrafilm.utils.gamut_compression import OutputGamutCompressSpec, compress_rgb


pytestmark = pytest.mark.unit


class _ArrayGpuBackend:
    name = "mlx"
    precision = "float32"
    supports_gpu = True
    fallback_reason = None
    requires_serial_runtime = False

    def __init__(self) -> None:
        self.asarray_calls = 0
        self.to_numpy_calls = 0

    def asarray(self, value: Any, dtype: Any | None = None) -> np.ndarray:
        self.asarray_calls += 1
        return np.asarray(value, dtype=dtype)

    def to_numpy(self, value: Any) -> np.ndarray:
        self.to_numpy_calls += 1
        return np.asarray(value)

    def eval(self, *values: Any) -> None:
        return None

    def synchronize(self) -> None:
        return None

    def matmul(self, a: Any, b: Any) -> np.ndarray:
        return np.matmul(a, b)

    def einsum(self, pattern: str, *values: Any) -> np.ndarray:
        return contract(pattern, *values)

    def abs(self, x: Any) -> np.ndarray:
        return np.abs(x)

    def pow(self, x: Any, exponent: float) -> np.ndarray:
        return np.power(x, exponent)

    def where(self, condition: Any, x: Any, y: Any) -> np.ndarray:
        return np.where(condition, x, y)

    def maximum(self, x: Any, y: Any) -> np.ndarray:
        return np.maximum(x, y)

    def fmax(self, x: Any, y: float) -> np.ndarray:
        return np.fmax(x, y)

    def nan_to_num(self, x: Any, nan: float = 0.0) -> np.ndarray:
        return np.nan_to_num(x, nan=nan)


def test_cctf_srgb_threshold_boundaries_use_float32_branch_points() -> None:
    backend = _ArrayGpuBackend()
    threshold = np.float32(0.0031308)
    values = np.array(
        [
            np.nextafter(threshold, np.float32(0.0)),
            threshold,
            np.nextafter(threshold, np.float32(1.0)),
            -threshold,
        ],
        dtype=np.float32,
    ).reshape(2, 2, 1)
    rgb = np.repeat(values, 3, axis=-1)

    encoded = _cctf_encoding_srgb_like(rgb, backend)
    manual = np.where(
        rgb <= float(threshold),
        rgb * np.float32(12.92),
        np.sign(rgb) * (np.float32(1.055) * np.abs(rgb) ** np.float32(1.0 / 2.4)) - np.float32(0.055),
    )

    np.testing.assert_allclose(encoded, manual, rtol=0.0, atol=2e-7)

    decode_threshold = np.float32(0.04045)
    encoded_values = np.array(
        [
            np.nextafter(decode_threshold, np.float32(0.0)),
            decode_threshold,
            np.nextafter(decode_threshold, np.float32(1.0)),
        ],
        dtype=np.float32,
    ).reshape(1, 3, 1)
    encoded_rgb = np.repeat(encoded_values, 3, axis=-1)
    decoded = cctf_decoding_transfer_backend(encoded_rgb, "sRGB", backend)
    manual_decoded = np.where(
        encoded_rgb <= float(decode_threshold),
        encoded_rgb / np.float32(12.92),
        np.sign((encoded_rgb + np.float32(0.055)) / np.float32(1.055))
        * np.abs((encoded_rgb + np.float32(0.055)) / np.float32(1.055)) ** np.float32(2.4),
    )
    np.testing.assert_allclose(decoded, manual_decoded, rtol=0.0, atol=2e-7)


@pytest.mark.parametrize("color_space", ["ACEScg", "ACES2065-1"])
def test_aces_scene_linear_cctf_noop_is_preserved(color_space: str) -> None:
    backend = _ArrayGpuBackend()
    rgb = np.array([[[0.0, 0.18, 1.0], [-0.1, 2.0, 0.5]]], dtype=np.float32)

    encoded = cctf_encoding_backend(rgb, color_space, backend)
    decoded = cctf_decoding_transfer_backend(rgb, color_space, backend)

    np.testing.assert_allclose(encoded, rgb, rtol=0.0, atol=2e-7)
    assert decoded is rgb


def test_rgb_xyz_matrix_precompute_dtype_shape_finite_and_roundtrip() -> None:
    backend = _ArrayGpuBackend()
    m_rgb_xyz = precompute_rgb_to_xyz_matrix("Display P3")
    m_xyz_rgb = precompute_xyz_to_rgb_matrix("Display P3")

    assert m_rgb_xyz.dtype == np.float64
    assert m_xyz_rgb.dtype == np.float64
    assert m_rgb_xyz.shape == (3, 3)
    assert m_xyz_rgb.shape == (3, 3)
    assert np.isfinite(m_rgb_xyz).all()
    assert np.isfinite(m_xyz_rgb).all()

    rgb = np.array([[[0.0, 0.18, 1.0], [1.3, -0.05, 0.25]]], dtype=np.float32)
    xyz = rgb_to_xyz(rgb, backend.asarray(m_rgb_xyz.astype(np.float32)), backend)
    roundtrip = xyz_to_rgb(xyz, backend.asarray(m_xyz_rgb.astype(np.float32)), backend)

    np.testing.assert_allclose(roundtrip, rgb, rtol=0.0, atol=3e-6)


def _make_hanatos_stage(policy: str, backend: _ArrayGpuBackend) -> filming_module.FilmingStage:
    stage = object.__new__(filming_module.FilmingStage)
    setattr(stage, "_film", SimpleNamespace(
        info=SimpleNamespace(reference_illuminant="D55"),
        data=SimpleNamespace(log_sensitivity=np.zeros((2, 3), dtype=float)),
    ))
    setattr(stage, "_camera", SimpleNamespace(filter_uv=(0.0, 0.0, 0.0), filter_ir=(0.0, 0.0, 0.0)))
    setattr(stage, "_settings", SimpleNamespace(
        rgb_to_raw_method="hanatos2025",
        bandpass_hanatos2025=False,
        color_precision_policy=policy,
    ))
    setattr(stage, "_backend", backend)
    setattr(stage, "_lut_service", SimpleNamespace(
        get_filming_tc_lut=lambda sensitivity: np.zeros((2, 2, 3), dtype=np.float32),
        get_filming_tc_lut_backend=lambda sensitivity: np.zeros((2, 2, 3), dtype=np.float32),
    ))
    return stage


def test_balanced_2d_mitchell_lut_falls_back_to_cpu_reference(monkeypatch) -> None:
    backend = _ArrayGpuBackend()
    stage = _make_hanatos_stage("balanced", backend)
    rgb = np.ones((2, 2, 3), dtype=np.float32) * 0.184
    calls: dict[str, Any] = {}

    def fake_cpu_reference(data, sensitivity, **kwargs):
        calls["data"] = data
        calls["sensitivity"] = sensitivity
        calls["kwargs"] = kwargs
        return np.full(data.shape, 0.25, dtype=np.float64)

    def fail_backend_lut(*_args, **_kwargs):
        raise AssertionError("balanced policy must not call the non-compliant GPU 2D LUT")

    monkeypatch.setattr(filming_module, "rgb_to_raw_hanatos2025", fake_cpu_reference)
    monkeypatch.setattr("spektrafilm.gpu.kernels.lut.apply_lut_cubic_2d_backend", fail_backend_lut)

    raw = stage._rgb_to_film_raw(rgb, color_space="sRGB", apply_cctf_decoding=False)

    np.testing.assert_allclose(raw, np.full_like(rgb, 0.25, dtype=np.float64))
    assert backend.to_numpy_calls == 1
    assert calls["data"].shape == rgb.shape
    assert precision_decision(OP_LUT_2D_MITCHELL, policy="balanced").fallback_to_cpu is True


def test_strict_jzazbz_gamut_compression_falls_back_to_cpu(monkeypatch) -> None:
    backend = _ArrayGpuBackend()
    rgb = np.array([[[1.2, -0.05, -0.05], [0.1, 1.1, 0.2]]], dtype=np.float32)
    spec = OutputGamutCompressSpec(algorithm="jzazbz")

    def fail_resident_kernel(*_args, **_kwargs):
        raise AssertionError("strict policy must not call resident JzAzBz GPU kernel")

    monkeypatch.setattr(gamut_backend_module, "compress_rgb_jzazbz_chroma_backend", fail_resident_kernel)

    actual = compress_rgb_backend(
        backend.asarray(rgb),
        spec,
        output_color_space="sRGB",
        backend=backend,
        precision_policy="strict",
    )
    expected = compress_rgb(rgb.astype(float), spec, output_color_space="sRGB")

    np.testing.assert_allclose(actual, expected, rtol=0.0, atol=1e-12)
    assert backend.to_numpy_calls == 1
    assert precision_decision(OP_GAMUT_JZAZBZ, policy="strict").fallback_to_cpu is True


def test_balanced_jzazbz_policy_does_not_claim_l1_compliance() -> None:
    decision = precision_decision(OP_GAMUT_JZAZBZ, policy="balanced", backend_name="mlx")

    assert decision.status == "exception"
    assert decision.allow_gpu is True
    assert decision.l1_compliant_claim is False


def test_spectral_reduction_adversarial_float32_budget_is_visible() -> None:
    rng = np.random.default_rng(20260629)
    light = rng.lognormal(mean=-2.0, sigma=3.0, size=(5, 4, 81)).astype(np.float64)
    sensitivity = rng.lognormal(mean=-1.0, sigma=2.0, size=(81, 3)).astype(np.float64)

    ref = contract("ijk,kl->ijl", light, sensitivity)
    candidate = contract(
        "ijk,kl->ijl",
        light.astype(np.float32),
        sensitivity.astype(np.float32),
    ).astype(np.float64)
    metrics = precision_metrics(ref, candidate, data_range=max(float(np.max(ref)), 1.0))

    assert metrics["max_abs"] > 0.0
    assert metrics["max_rel"] < 5e-5
    decision = precision_decision(OP_SPECTRAL_REDUCTION, policy="balanced", backend_name="mlx")
    assert decision.status == "conditional"
    assert decision.l1_compliant_claim is False
