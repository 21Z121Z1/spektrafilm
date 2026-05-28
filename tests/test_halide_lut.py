"""Tests for Halide 2-D cubic LUT interpolation kernel."""

from __future__ import annotations

import numpy as np
import pytest

halide = pytest.importorskip("halide")

from spektrafilm.gpu.halide_backend import HalideBackend


@pytest.fixture(scope="module")
def backend():
    return HalideBackend()


# ---------------------------------------------------------------------------
# Reference NumPy Mitchell-Netravali bicubic
# ---------------------------------------------------------------------------


def _mitchell(t: np.ndarray) -> np.ndarray:
    """Mitchell-Netravali kernel (B=1/3, C=1/3)."""
    B = 1.0 / 3.0
    C = 1.0 / 3.0
    at = np.abs(t)
    t2 = at * at
    t3 = t2 * at
    inner = ((12 - 9 * B - 6 * C) * t3 + (-18 + 12 * B + 6 * C) * t2 + (6 - 2 * B)) / 6.0
    outer = ((-B - 6 * C) * t3 + (6 * B + 30 * C) * t2 + (-12 * B - 48 * C) * at + (8 * B + 24 * C)) / 6.0
    return np.where(at < 1.0, inner, outer).astype(np.float32)


def numpy_lut_2d_cubic(lut: np.ndarray, image: np.ndarray) -> np.ndarray:
    """NumPy reference bicubic 2-D LUT interpolation."""
    size = lut.shape[0]
    n_channels = lut.shape[2]
    upper = float(size - 1)
    h, w = image.shape[:2]

    fx = np.clip(image[..., 0] * upper, 0.0, upper)
    fy = np.clip(image[..., 1] * upper, 0.0, upper)

    ix = np.floor(fx).astype(np.int32)
    iy = np.floor(fy).astype(np.int32)
    dx = fx - ix.astype(np.float32)
    dy = fy - iy.astype(np.float32)

    result = np.zeros((h, w, n_channels), dtype=np.float32)

    for m in range(-1, 3):
        for n in range(-1, 3):
            cx = np.clip(ix + m, 0, size - 1)
            cy = np.clip(iy + n, 0, size - 1)
            wx = _mitchell(dx - float(m))
            wy = _mitchell(dy - float(n))
            result += lut[cy, cx] * wx[..., None] * wy[..., None]

    return result


class TestLut2DCubic:
    def test_identity_lut(self, backend: HalideBackend) -> None:
        """A 2-channel identity LUT should return the input coordinates."""
        size = 16
        lut = np.zeros((size, size, 2), dtype=np.float32)
        for i in range(size):
            for j in range(size):
                lut[i, j, 0] = j / (size - 1)
                lut[i, j, 1] = i / (size - 1)

        rng = np.random.RandomState(0)
        image = rng.uniform(0.0, 1.0, (32, 32, 2)).astype(np.float32)

        result = backend.lut_2d_cubic(lut, image)
        np.testing.assert_allclose(result, image, atol=0.02)

    def test_random_lut(self, backend: HalideBackend) -> None:
        rng = np.random.RandomState(42)
        size = 8
        lut = rng.uniform(0.0, 1.0, (size, size, 3)).astype(np.float32)
        image = rng.uniform(0.0, 1.0, (32, 32, 2)).astype(np.float32)

        expected = numpy_lut_2d_cubic(lut, image)
        result = backend.lut_2d_cubic(lut, image)
        np.testing.assert_allclose(result, expected, atol=1e-5)

    def test_boundary_clamp(self, backend: HalideBackend) -> None:
        """Coords at 0.0 and 1.0 should clamp correctly."""
        size = 4
        rng = np.random.RandomState(7)
        lut = rng.uniform(0.0, 1.0, (size, size, 2)).astype(np.float32)

        image = np.zeros((4, 4, 2), dtype=np.float32)
        image[0, 0] = [0.0, 0.0]
        image[0, 1] = [1.0, 1.0]
        image[0, 2] = [0.0, 1.0]
        image[0, 3] = [1.0, 0.0]

        result = backend.lut_2d_cubic(lut, image)
        expected = numpy_lut_2d_cubic(lut, image)
        np.testing.assert_allclose(result, expected, atol=1e-5)

    def test_single_channel(self, backend: HalideBackend) -> None:
        rng = np.random.RandomState(99)
        size = 6
        lut = rng.uniform(0.0, 1.0, (size, size, 1)).astype(np.float32)
        image = rng.uniform(0.0, 1.0, (16, 16, 2)).astype(np.float32)

        expected = numpy_lut_2d_cubic(lut, image)
        result = backend.lut_2d_cubic(lut, image)
        np.testing.assert_allclose(result, expected, atol=1e-5)
