"""Halide JIT tests for filter kernels: gaussian_blur_fir, gaussian_blur_iir, highlight_boost."""
from __future__ import annotations

import numpy as np
import pytest
from scipy.ndimage import convolve1d

from spektrafilm.gpu.halide_backend import HalideBackend
from spektrafilm.utils.fast_gaussian_filter import _gaussian_kernel_1d, fast_gaussian_filter_large

pytestmark = pytest.mark.unit

halide = pytest.importorskip("halide")


@pytest.fixture()
def backend():
    return HalideBackend(halide_module=halide)


def _fir_blur_reference(image_chw, kernel_1d):
    """Per-channel 1D separable convolution with scipy reflect boundary."""
    out = np.empty_like(image_chw)
    for c in range(image_chw.shape[0]):
        tmp = convolve1d(image_chw[c], kernel_1d, axis=0, mode="reflect")
        out[c] = convolve1d(tmp, kernel_1d, axis=1, mode="reflect")
    return out.astype(np.float32)


def _iir_blur_reference(image_chw, sigma):
    """Per-channel YVV IIR Gaussian via fast_gaussian_filter_large."""
    out = np.empty_like(image_chw)
    for ch in range(image_chw.shape[0]):
        out[ch] = fast_gaussian_filter_large(image_chw[ch], sigma)
    return out


def _highlight_boost_reference(image_chw, *, threshold, boost, offset=0.0):
    return np.where(image_chw < threshold, image_chw, (image_chw + offset) * boost).astype(np.float32)


# ---------- gaussian_blur_fir ----------


def test_fir_blur_matches_scipy_reference(backend) -> None:
    rng = np.random.default_rng(60)
    image = rng.random((3, 12, 16), dtype=np.float32)
    kernel, _radius = _gaussian_kernel_1d(1.5, 3.0)
    kernel = kernel.astype(np.float32)

    expected = _fir_blur_reference(image, kernel)
    actual = backend.gaussian_blur_fir(image, kernel)

    assert actual.shape == image.shape
    assert actual.dtype == np.float32
    np.testing.assert_allclose(actual, expected, atol=1e-5)


def test_fir_blur_identity_kernel(backend) -> None:
    rng = np.random.default_rng(61)
    image = rng.random((2, 8, 10), dtype=np.float32)
    kernel = np.array([0.0, 1.0, 0.0], dtype=np.float32)

    actual = backend.gaussian_blur_fir(image, kernel)
    np.testing.assert_allclose(actual, image, atol=1e-6)


def test_fir_blur_cache_rebuilds_on_kernel_change(backend) -> None:
    rng = np.random.default_rng(62)
    image = rng.random((2, 6, 8), dtype=np.float32)
    k3 = np.array([0.25, 0.5, 0.25], dtype=np.float32)
    k5 = np.array([0.0625, 0.25, 0.375, 0.25, 0.0625], dtype=np.float32)

    backend.gaussian_blur_fir(image, k3)
    len1 = backend._fir_blur_kernel_len
    backend.gaussian_blur_fir(image, k5)
    len2 = backend._fir_blur_kernel_len

    assert len1 == 3
    assert len2 == 5


def test_fir_blur_invalid_image_ndim(backend) -> None:
    with pytest.raises(ValueError, match="image must be 3D"):
        backend.gaussian_blur_fir(np.zeros((8, 8), dtype=np.float32), np.array([0.5, 0.5], dtype=np.float32))


def test_fir_blur_invalid_kernel_length(backend) -> None:
    with pytest.raises(ValueError, match="kernel_1d must be 1D"):
        backend.gaussian_blur_fir(np.zeros((2, 8, 8), dtype=np.float32), np.array([0.5, 0.5, 0.5, 0.5], dtype=np.float32))


# ---------- gaussian_blur_iir ----------


def test_iir_blur_matches_reference(backend) -> None:
    rng = np.random.default_rng(70)
    image = rng.random((2, 10, 14), dtype=np.float32)
    sigma = 5.0

    expected = _iir_blur_reference(image, sigma)
    actual = backend.gaussian_blur_iir(image, sigma)

    assert actual.shape == image.shape
    assert actual.dtype == np.float32
    np.testing.assert_allclose(actual, expected, atol=1e-6)


def test_iir_blur_various_sigmas(backend) -> None:
    rng = np.random.default_rng(71)
    image = rng.random((3, 12, 16), dtype=np.float32)
    for sigma in [0.5, 3.0, 8.0, 20.0]:
        expected = _iir_blur_reference(image, sigma)
        actual = backend.gaussian_blur_iir(image, sigma)
        np.testing.assert_allclose(actual, expected, atol=1e-6)


def test_iir_blur_invalid_sigma(backend) -> None:
    with pytest.raises(ValueError, match="sigma must be >= 0.5"):
        backend.gaussian_blur_iir(np.zeros((2, 8, 8), dtype=np.float32), 0.3)


def test_iir_blur_invalid_image_ndim(backend) -> None:
    with pytest.raises(ValueError, match="image must be 3D"):
        backend.gaussian_blur_iir(np.zeros((8, 8), dtype=np.float32), 5.0)


# ---------- highlight_boost ----------


def test_highlight_boost_matches_numpy(backend) -> None:
    rng = np.random.default_rng(80)
    image = rng.random((3, 10, 14), dtype=np.float32)

    expected = _highlight_boost_reference(image, threshold=0.5, boost=1.5, offset=0.1)
    actual = backend.highlight_boost(image, threshold=0.5, boost=1.5, offset=0.1)

    assert actual.shape == image.shape
    assert actual.dtype == np.float32
    np.testing.assert_allclose(actual, expected, atol=1e-6)


def test_highlight_boost_zero_threshold(backend) -> None:
    rng = np.random.default_rng(81)
    image = rng.random((2, 8, 10), dtype=np.float32)

    expected = _highlight_boost_reference(image, threshold=0.0, boost=2.0, offset=0.0)
    actual = backend.highlight_boost(image, threshold=0.0, boost=2.0, offset=0.0)
    np.testing.assert_allclose(actual, expected, atol=1e-6)


def test_highlight_boost_negative_offset(backend) -> None:
    rng = np.random.default_rng(82)
    image = rng.random((3, 8, 10), dtype=np.float32) + 0.3

    expected = _highlight_boost_reference(image, threshold=0.5, boost=0.8, offset=-0.2)
    actual = backend.highlight_boost(image, threshold=0.5, boost=0.8, offset=-0.2)
    np.testing.assert_allclose(actual, expected, atol=1e-6)


def test_highlight_boost_invalid_image_ndim(backend) -> None:
    with pytest.raises(ValueError, match="image must be 3D"):
        backend.highlight_boost(np.zeros((8, 8), dtype=np.float32), threshold=0.5, boost=1.5)


def test_highlight_boost_cache_reuses_pipeline(backend) -> None:
    rng = np.random.default_rng(83)
    image = rng.random((2, 6, 8), dtype=np.float32)
    backend.highlight_boost(image, threshold=0.5, boost=1.5)
    p1 = backend._highlight_boost_pipeline
    backend.highlight_boost(image, threshold=0.3, boost=2.0)
    p2 = backend._highlight_boost_pipeline
    assert p1 is p2
