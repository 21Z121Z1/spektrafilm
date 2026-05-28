"""Tests for Halide CCTF encode/decode kernels."""

from __future__ import annotations

import numpy as np
import pytest

halide = pytest.importorskip("halide")

from spektrafilm.gpu.halide_backend import HalideBackend


@pytest.fixture(scope="module")
def backend():
    return HalideBackend()


# ---------------------------------------------------------------------------
# Reference NumPy implementations
# ---------------------------------------------------------------------------


def numpy_cctf_encode(
    linear: np.ndarray,
    *,
    gamma: float,
    threshold: float,
    a: float,
    b: float,
    c_coeff: float,
    d_coeff: float,
) -> np.ndarray:
    a32, b32 = np.float32(a), np.float32(b)
    c32, d32 = np.float32(c_coeff), np.float32(d_coeff)
    g32, t32 = np.float32(gamma), np.float32(threshold)
    lo = a32 * linear + b32
    hi = (c32 * np.power(linear, 1.0 / g32) - d32).astype(np.float32)
    return np.where(linear <= t32, lo, hi).astype(np.float32)


def numpy_cctf_decode(
    encoded: np.ndarray,
    *,
    gamma: float,
    threshold: float,
    a: float,
    b: float,
    c_coeff: float,
    d_coeff: float,
) -> np.ndarray:
    a32, b32 = np.float32(a), np.float32(b)
    c32, d32 = np.float32(c_coeff), np.float32(d_coeff)
    g32, t32 = np.float32(gamma), np.float32(threshold)
    lo = (encoded - b32) / a32
    hi = np.power((encoded + d32) / c32, g32).astype(np.float32)
    encoded_threshold = a32 * t32 + b32
    return np.where(encoded <= encoded_threshold, lo, hi).astype(np.float32)


# ---------------------------------------------------------------------------
# sRGB parameters
# ---------------------------------------------------------------------------

SRGB_PARAMS = dict(gamma=2.4, threshold=0.0031308, a=12.92, b=0.0, c_coeff=1.055, d_coeff=0.055)


class TestCctfEncode:
    def test_srgb_random(self, backend: HalideBackend) -> None:
        rng = np.random.RandomState(42)
        linear = rng.uniform(0.0, 1.0, (3, 64, 48)).astype(np.float32)
        expected = numpy_cctf_encode(linear, **SRGB_PARAMS)
        result = backend.cctf_encode(linear, **SRGB_PARAMS)
        np.testing.assert_allclose(result, expected, atol=2e-6)

    def test_below_threshold(self, backend: HalideBackend) -> None:
        linear = np.array([[[0.001, 0.002, 0.0]]], dtype=np.float32)
        expected = numpy_cctf_encode(linear, **SRGB_PARAMS)
        result = backend.cctf_encode(linear, **SRGB_PARAMS)
        np.testing.assert_allclose(result, expected, atol=2e-6)

    def test_above_threshold(self, backend: HalideBackend) -> None:
        linear = np.array([[[0.5, 0.8, 1.0]]], dtype=np.float32)
        expected = numpy_cctf_encode(linear, **SRGB_PARAMS)
        result = backend.cctf_encode(linear, **SRGB_PARAMS)
        np.testing.assert_allclose(result, expected, atol=2e-6)

    def test_exact_threshold(self, backend: HalideBackend) -> None:
        linear = np.full((3, 16, 16), 0.0031308, dtype=np.float32)
        expected = numpy_cctf_encode(linear, **SRGB_PARAMS)
        result = backend.cctf_encode(linear, **SRGB_PARAMS)
        np.testing.assert_allclose(result, expected, atol=2e-6)

    def test_custom_params(self, backend: HalideBackend) -> None:
        params = dict(gamma=2.2, threshold=0.01, a=10.0, b=0.0, c_coeff=1.1, d_coeff=0.05)
        linear = np.random.RandomState(7).uniform(0.0, 1.0, (3, 32, 32)).astype(np.float32)
        expected = numpy_cctf_encode(linear, **params)
        result = backend.cctf_encode(linear, **params)
        np.testing.assert_allclose(result, expected, atol=2e-6)


class TestCctfDecode:
    def test_srgb_roundtrip(self, backend: HalideBackend) -> None:
        rng = np.random.RandomState(99)
        linear = rng.uniform(0.0, 1.0, (3, 64, 48)).astype(np.float32)
        encoded = backend.cctf_encode(linear, **SRGB_PARAMS)
        decoded = backend.cctf_decode(encoded, **SRGB_PARAMS)
        np.testing.assert_allclose(decoded, linear, atol=1e-5)

    def test_srgb_random(self, backend: HalideBackend) -> None:
        rng = np.random.RandomState(42)
        encoded = rng.uniform(0.0, 1.0, (3, 64, 48)).astype(np.float32)
        expected = numpy_cctf_decode(encoded, **SRGB_PARAMS)
        result = backend.cctf_decode(encoded, **SRGB_PARAMS)
        np.testing.assert_allclose(result, expected, atol=1e-6)

    def test_below_threshold(self, backend: HalideBackend) -> None:
        encoded = np.array([[[0.01, 0.02, 0.0]]], dtype=np.float32)
        expected = numpy_cctf_decode(encoded, **SRGB_PARAMS)
        result = backend.cctf_decode(encoded, **SRGB_PARAMS)
        np.testing.assert_allclose(result, expected, atol=1e-6)

    def test_above_threshold(self, backend: HalideBackend) -> None:
        encoded = np.array([[[0.5, 0.8, 1.0]]], dtype=np.float32)
        expected = numpy_cctf_decode(encoded, **SRGB_PARAMS)
        result = backend.cctf_decode(encoded, **SRGB_PARAMS)
        np.testing.assert_allclose(result, expected, atol=1e-6)

    def test_custom_params(self, backend: HalideBackend) -> None:
        params = dict(gamma=2.2, threshold=0.01, a=10.0, b=0.0, c_coeff=1.1, d_coeff=0.05)
        encoded = np.random.RandomState(7).uniform(0.0, 1.0, (3, 32, 32)).astype(np.float32)
        expected = numpy_cctf_decode(encoded, **params)
        result = backend.cctf_decode(encoded, **params)
        np.testing.assert_allclose(result, expected, atol=1e-6)

    def test_transition_region_roundtrip(self, backend: HalideBackend) -> None:
        """Values around the 0.0031308 threshold must roundtrip without discontinuity."""
        linear = np.array(
            [0.001, 0.002, 0.003, 0.0031, 0.0031308, 0.0032, 0.004, 0.005, 0.01, 0.05, 0.1],
            dtype=np.float32,
        ).reshape(1, 1, -1)

        encoded = backend.cctf_encode(linear, **SRGB_PARAMS)
        decoded = backend.cctf_decode(encoded, **SRGB_PARAMS)

        # Roundtrip must be close
        np.testing.assert_allclose(decoded, linear, atol=1e-5)

        # Encoded values must be monotonically increasing (no jump at threshold)
        flat = encoded.ravel()
        assert np.all(np.diff(flat) > 0), (
            f"Encoded values not monotonic around threshold: {flat}"
        )


class TestInterp1D:
    def test_linear_ramp(self, backend: HalideBackend) -> None:
        values = np.array([0.0, 1.0, 2.0, 3.0], dtype=np.float32)
        positions = np.array([0.0, 1.0, 2.0, 3.0], dtype=np.float32)
        query = np.array([[0.5, 1.5, 2.5]], dtype=np.float32)
        result = backend.interp_1d(values, positions, query)
        expected = np.array([[0.5, 1.5, 2.5]], dtype=np.float32)
        np.testing.assert_allclose(result, expected, atol=1e-6)

    def test_clamp_below(self, backend: HalideBackend) -> None:
        values = np.array([10.0, 20.0, 30.0], dtype=np.float32)
        positions = np.array([0.0, 1.0, 2.0], dtype=np.float32)
        query = np.array([[-1.0]], dtype=np.float32)
        result = backend.interp_1d(values, positions, query)
        np.testing.assert_allclose(result, np.array([[10.0]]), atol=1e-6)

    def test_clamp_above(self, backend: HalideBackend) -> None:
        values = np.array([10.0, 20.0, 30.0], dtype=np.float32)
        positions = np.array([0.0, 1.0, 2.0], dtype=np.float32)
        query = np.array([[5.0]], dtype=np.float32)
        result = backend.interp_1d(values, positions, query)
        np.testing.assert_allclose(result, np.array([[30.0]]), atol=1e-6)

    def test_against_numpy(self, backend: HalideBackend) -> None:
        values = np.array([0.0, 0.5, 1.0, 0.8, 0.3], dtype=np.float32)
        positions = np.array([0.0, 0.25, 0.5, 0.75, 1.0], dtype=np.float32)
        rng = np.random.RandomState(123)
        query = rng.uniform(0.0, 1.0, (32, 32)).astype(np.float32)
        expected = np.interp(query.ravel(), positions, values).reshape(query.shape).astype(np.float32)
        result = backend.interp_1d(values, positions, query)
        np.testing.assert_allclose(result, expected, atol=1e-6)


class TestGrainBuffer:
    def test_shape(self) -> None:
        buf = HalideBackend.generate_grain_buffer((3, 64, 64), seed=0)
        assert buf.shape == (3, 64, 64)
        assert buf.dtype == np.float32

    def test_reproducible(self) -> None:
        a = HalideBackend.generate_grain_buffer((4, 4), seed=42)
        b = HalideBackend.generate_grain_buffer((4, 4), seed=42)
        np.testing.assert_array_equal(a, b)

    def test_different_seed(self) -> None:
        a = HalideBackend.generate_grain_buffer((4, 4), seed=1)
        b = HalideBackend.generate_grain_buffer((4, 4), seed=2)
        assert not np.array_equal(a, b)
