from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import colour
import numpy as np
import pytest
from opt_einsum import contract

from spektrafilm.color_management import ColorEncoding
from spektrafilm.gpu.backend import BackendUnavailableError, select_backend
from spektrafilm.gpu.kernels.color import (
    cctf_decoding_backend,
    cctf_encoding_backend,
    precompute_rgb_to_xyz_matrix,
    precompute_xyz_to_rgb_matrix,
    rgb_to_xyz,
    xyz_to_rgb,
)
from spektrafilm.gpu.numpy_backend import NumpyBackend
from spektrafilm.runtime.stages import scanning as scanning_module


pytestmark = pytest.mark.unit


def _available_backends() -> list[str]:
    """Return ['cpu'] plus any GPU backends that can be imported."""
    backends = ["cpu"]
    for name in ("mlx", "cupy", "halide"):
        try:
            select_backend(name)
            backends.append(name)
        except (BackendUnavailableError, Exception):
            pass
    return backends


def _get_backend(name: str):
    if name == "cpu":
        return NumpyBackend()
    return select_backend(name)


@dataclass
class RecordingNumpyGpuBackend:
    to_numpy_calls: int = 0

    name: str = "recording-gpu"
    supports_gpu: bool = True
    fallback_reason: str | None = None

    def asarray(self, value: Any, dtype: Any | None = None) -> np.ndarray:
        return np.asarray(value, dtype=dtype)

    def to_numpy(self, value: Any) -> np.ndarray:
        self.to_numpy_calls += 1
        raise AssertionError("GPU CCTF path must not materialize the full image on CPU")

    def eval(self, *values: Any) -> None:
        return None

    def synchronize(self) -> None:
        return None

    def exp(self, x: Any) -> np.ndarray:
        return np.exp(x)

    def log10(self, x: Any) -> np.ndarray:
        return np.log10(x)

    def maximum(self, x: Any, y: Any) -> np.ndarray:
        return np.maximum(x, y)

    def max(self, x: Any) -> float:
        return float(np.max(x))

    def clip(self, x: Any, lo: float, hi: float) -> np.ndarray:
        return np.clip(x, lo, hi)

    def matmul(self, a: Any, b: Any) -> np.ndarray:
        return np.matmul(a, b)

    def einsum(self, pattern: str, *values: Any) -> np.ndarray:
        return contract(pattern, *values)

    def power(self, base: float, x: Any) -> np.ndarray:
        return np.power(base, x)

    def pow(self, x: Any, exponent: float) -> np.ndarray:
        return np.power(x, exponent)

    def fmax(self, x: Any, y: float) -> np.ndarray:
        return np.fmax(x, y)

    def nan_to_num(self, x: Any, nan: float = 0.0) -> np.ndarray:
        return np.nan_to_num(x, nan=nan)

    def where(self, condition: Any, x: Any, y: Any) -> np.ndarray:
        return np.where(condition, x, y)

    def abs(self, x: Any) -> np.ndarray:
        return np.abs(x)


@pytest.mark.parametrize(
    "color_space",
    ["sRGB", "Display P3", "ProPhoto RGB", "ITU-R BT.2020", "Adobe RGB (1998)", "DCI-P3", "ACES2065-1", "ACEScg"],
)
def test_backend_cctf_encoding_matches_colour_reference(color_space: str) -> None:
    backend = RecordingNumpyGpuBackend()
    values = np.array(
        [
            [[-0.01, 0.0, 0.001], [0.0031308, 0.018, 0.18]],
            [[0.5, 1.0, 1.5], [0.02, 0.25, 0.75]],
        ],
        dtype=np.float64,
    )

    with np.errstate(invalid="ignore"):
        actual = cctf_encoding_backend(values, color_space, backend)
        expected = colour.RGB_to_RGB(
            values,
            color_space,
            color_space,
            apply_cctf_decoding=False,
            apply_cctf_encoding=True,
        )

    np.testing.assert_allclose(actual, expected, rtol=2e-7, atol=2e-7, equal_nan=True)
    assert backend.to_numpy_calls == 0


def test_backend_cctf_encoding_uses_compiled_elementwise_hook_when_available() -> None:
    backend = RecordingNumpyGpuBackend()
    compile_names: list[str] = []

    def compiled_elementwise(name, function, *sample_args):
        compile_names.append(name)
        return function

    backend.compiled_elementwise = compiled_elementwise  # type: ignore[attr-defined]
    values = np.array(
        [
            [[0.0, 0.001, 0.0031308], [0.018, 0.18, 0.5]],
            [[0.75, 1.0, 1.5], [0.02, 0.25, 0.75]],
        ],
        dtype=np.float64,
    )

    actual = cctf_encoding_backend(values, "sRGB", backend)
    expected = colour.RGB_to_RGB(
        values,
        "sRGB",
        "sRGB",
        apply_cctf_decoding=False,
        apply_cctf_encoding=True,
    )

    assert "cctf_encoding_srgb_like" in compile_names
    np.testing.assert_allclose(actual, expected, rtol=2e-7, atol=2e-7)


@pytest.mark.parametrize(
    "color_space",
    ["sRGB", "Display P3", "ProPhoto RGB", "ITU-R BT.2020", "Adobe RGB (1998)", "DCI-P3", "ACES2065-1", "ACEScg"],
)
def test_backend_cctf_decoding_matches_colour_reference(color_space: str) -> None:
    backend = RecordingNumpyGpuBackend()
    values = np.array(
        [
            [[-0.01, 0.0, 0.001], [0.04045, 0.081, 0.18]],
            [[0.5, 1.0, 1.5], [0.02, 0.25, 0.75]],
        ],
        dtype=np.float64,
    )

    with np.errstate(invalid="ignore"):
        actual = cctf_decoding_backend(values, color_space, backend)
        expected = colour.RGB_to_RGB(
            values,
            color_space,
            color_space,
            apply_cctf_decoding=True,
            apply_cctf_encoding=False,
        )

    np.testing.assert_allclose(actual, expected, rtol=2e-7, atol=2e-7, equal_nan=True)
    assert backend.to_numpy_calls == 0


def test_scanning_stage_cctf_encoding_does_not_call_colour_rgb_to_rgb(monkeypatch) -> None:
    def fail_rgb_to_rgb(*_args, **_kwargs):
        raise AssertionError("GPU CCTF path should use spektrafilm.gpu.kernels.color")

    monkeypatch.setattr(scanning_module.colour, "RGB_to_RGB", fail_rgb_to_rgb)

    backend = RecordingNumpyGpuBackend()
    stage = object.__new__(scanning_module.ScanningStage)
    setattr(stage, "_backend", backend)
    rgb = np.array(
        [
            [[-0.01, 0.0, 0.18], [0.5, 1.2, 2.0]],
            [[0.003, 0.004, 0.005], [0.25, 0.5, 0.75]],
        ],
        dtype=np.float64,
    )
    encoding = ColorEncoding(
        color_space="sRGB",
        transfer="cctf",
        clip_negatives=True,
        clip_highlights=True,
    )

    actual = stage._apply_cctf_encoding_and_clip(rgb, encoding)
    matrix = colour.matrix_RGB_to_RGB("sRGB", "sRGB", chromatic_adaptation_transform="CAT02")
    expected = np.clip(colour.RGB_COLOURSPACES["sRGB"].cctf_encoding(rgb @ matrix.T), 0.0, 1.0)

    np.testing.assert_allclose(actual, expected, rtol=2e-7, atol=2e-7)
    assert backend.to_numpy_calls == 0


def test_rgb_to_xyz_backend_matrix_matches_colour_science_reference() -> None:
    backend = NumpyBackend()
    rgb = np.array(
        [
            [[0.1, 0.2, 0.3], [0.7, 0.5, 0.2]],
            [[1.0, 0.9, 0.8], [0.0, 0.4, 0.6]],
        ],
        dtype=np.float64,
    )
    matrix = precompute_rgb_to_xyz_matrix("sRGB")

    actual = rgb_to_xyz(rgb, matrix, backend)
    expected = colour.RGB_to_XYZ(
        rgb,
        colourspace="sRGB",
        apply_cctf_decoding=False,
    )

    np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-12)


# ---------------------------------------------------------------------------
# Parity: xyz_to_rgb backend vs CPU manual matmul reference
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("backend_name", _available_backends())
def test_xyz_to_rgb_backend_matches_cpu_reference(backend_name: str) -> None:
    backend = _get_backend(backend_name)
    rng = np.random.default_rng(42)
    xyz = rng.random((16, 16, 3))
    matrix = precompute_xyz_to_rgb_matrix("sRGB")
    dtype = np.float64 if backend_name == "cpu" else np.float32
    xyz_backend = backend.asarray(xyz.astype(dtype))
    matrix_backend = backend.asarray(matrix.astype(dtype))

    result = xyz_to_rgb(xyz_backend, matrix_backend, backend)
    result_np = backend.to_numpy(result)
    expected = np.matmul(xyz.astype(dtype), matrix.astype(dtype).T)

    max_abs_diff = float(np.max(np.abs(result_np - expected)))
    assert np.allclose(result_np, expected, atol=1e-6), (
        f"backend={backend_name!r} xyz_to_rgb mismatch: max_abs_diff={max_abs_diff:.2e}"
    )


# ---------------------------------------------------------------------------
# Parity: CCTF encode/decode roundtrip
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("color_space", ["sRGB", "ProPhoto RGB", "ITU-R BT.2020"])
@pytest.mark.parametrize("backend_name", _available_backends())
def test_cctf_encoding_backend_roundtrip(color_space: str, backend_name: str) -> None:
    """decode(encode(x)) must match the colour-science roundtrip reference.

    The full cctf_encoding_backend/cctf_decoding_backend include a same-space
    matrix step (CAT02) that is not exactly identity, so the roundtrip is
    compared against colour.RGB_to_RGB(encode=True) then colour.RGB_to_RGB(decode=True).
    """
    backend = _get_backend(backend_name)
    rng = np.random.default_rng(42)
    data = rng.random((64, 64, 3))
    dtype = np.float64 if backend_name == "cpu" else np.float32
    data_backend = backend.asarray(data.astype(dtype))

    encoded = cctf_encoding_backend(data_backend, color_space, backend)
    decoded = cctf_decoding_backend(encoded, color_space, backend)
    result_np = backend.to_numpy(decoded)

    # colour-science reference roundtrip
    expected = colour.RGB_to_RGB(
        colour.RGB_to_RGB(
            data.astype(dtype),
            color_space,
            color_space,
            apply_cctf_decoding=False,
            apply_cctf_encoding=True,
        ),
        color_space,
        color_space,
        apply_cctf_decoding=True,
        apply_cctf_encoding=False,
    )

    max_abs_diff = float(np.max(np.abs(result_np - expected)))
    assert np.allclose(result_np, expected, atol=1e-6), (
        f"backend={backend_name!r} color_space={color_space!r} CCTF roundtrip mismatch: "
        f"max_abs_diff={max_abs_diff:.2e}"
    )


# ---------------------------------------------------------------------------
# Regression: large image CCTF produces finite values (P1-1)
# ---------------------------------------------------------------------------


def test_cctf_encoding_large_image_produces_finite() -> None:
    """Regression test for P1-1: large images must produce finite output in [0, 1].

    Marked xfail until P1-1 is confirmed fixed.
    """
    try:
        backend = select_backend("halide")
    except BackendUnavailableError:
        pytest.skip("halide backend not available")

    rng = np.random.default_rng(42)
    data = rng.random((64, 64, 3)).astype(np.float32)
    data_backend = backend.asarray(data)

    result = cctf_encoding_backend(data_backend, "sRGB", backend)
    result_np = backend.to_numpy(result)

    assert np.all(np.isfinite(result_np)), "CCTF encoding produced non-finite values"
    assert np.all(result_np >= 0.0), "CCTF encoding produced negative values"
    assert np.all(result_np <= 1.0), "CCTF encoding produced values > 1.0"
