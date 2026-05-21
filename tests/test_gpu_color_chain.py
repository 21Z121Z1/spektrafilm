from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import colour
import numpy as np
import pytest
from opt_einsum import contract

from spektrafilm.color_management import ColorEncoding
from spektrafilm.gpu.kernels.color import (
    cctf_decoding_backend,
    cctf_encoding_backend,
    precompute_rgb_to_xyz_matrix,
    rgb_to_xyz,
)
from spektrafilm.gpu.numpy_backend import NumpyBackend
from spektrafilm.runtime.stages import scanning as scanning_module


pytestmark = pytest.mark.unit


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
    ["sRGB", "Display P3", "ProPhoto RGB", "ITU-R BT.2020", "Adobe RGB (1998)", "ACES2065-1"],
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


@pytest.mark.parametrize(
    "color_space",
    ["sRGB", "Display P3", "ProPhoto RGB", "ITU-R BT.2020", "Adobe RGB (1998)", "DCI-P3", "ACES2065-1"],
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
