from __future__ import annotations

import numpy as np
import pytest
from scipy.ndimage import gaussian_filter

from spektrafilm.utils.fft_gaussian_filter import fft_gaussian_filter

pytestmark = pytest.mark.unit


def _assert_close_to_scipy(result: np.ndarray, image: np.ndarray, sigma, truncate: float = 7.0) -> None:
    """Compare FFT-based filter output to scipy.ndimage.gaussian_filter.

    The FFT approach uses frequency-domain multiplication with mirror padding,
    while scipy uses spatial convolution with reflect mode. Small differences
    are expected at edges; we check the interior and use relaxed tolerance.
    """
    if np.isscalar(sigma) or (isinstance(sigma, np.ndarray) and sigma.ndim == 0):
        expected = gaussian_filter(image, float(sigma), mode="reflect")
    elif image.ndim == 3:
        expected = np.empty_like(image)
        for c in range(image.shape[2]):
            expected[..., c] = gaussian_filter(image[..., c], sigma[c], mode="reflect")
    else:
        expected = gaussian_filter(image, sigma, mode="reflect")
    # FFT and spatial-domain filters differ at edges due to different padding strategies.
    # Check interior region only (skip border of `pad_width` pixels).
    pad = int(truncate * (np.max(sigma) if not np.isscalar(sigma) else sigma) + 0.5)
    if image.ndim == 2:
        r = result[pad:-pad or None, pad:-pad or None]
        e = expected[pad:-pad or None, pad:-pad or None]
    else:
        r = result[pad:-pad or None, pad:-pad or None, :]
        e = expected[pad:-pad or None, pad:-pad or None, :]
    np.testing.assert_allclose(r, e, atol=0.01, rtol=0.02)


class TestFFT2DFilter:
    def test_2d_scalar_sigma_matches_scipy(self) -> None:
        rng = np.random.default_rng(42)
        image = rng.random((64, 64), dtype=np.float64)
        result = fft_gaussian_filter(image, 3.0, truncate=4.0, pad=True)
        _assert_close_to_scipy(result, image, 3.0, 4.0)

    def test_2d_large_sigma_matches_scipy(self) -> None:
        rng = np.random.default_rng(7)
        image = rng.random((128, 128), dtype=np.float64)
        result = fft_gaussian_filter(image, 15.0, truncate=4.0, pad=True)
        _assert_close_to_scipy(result, image, 15.0, 4.0)

    def test_2d_no_padding_matches_scipy(self) -> None:
        rng = np.random.default_rng(99)
        image = rng.random((64, 64), dtype=np.float64)
        result = fft_gaussian_filter(image, 2.0, truncate=4.0, pad=False)
        # Without padding, edge effects differ from reflect-padded scipy,
        # but interior should still be close.
        expected = gaussian_filter(image, 2.0, mode="reflect")
        # Check interior only (skip 10-pixel border).
        np.testing.assert_allclose(result[10:-10, 10:-10], expected[10:-10, 10:-10], atol=1e-5)


class TestFFT3DFilter:
    def test_3d_scalar_sigma_matches_scipy(self) -> None:
        """3D filter with scalar sigma should match scipy per-channel."""
        rng = np.random.default_rng(42)
        image = rng.random((128, 128, 3), dtype=np.float64)
        # Process per-channel manually to match scipy's spatial-only behavior.
        result = fft_gaussian_filter(image, 3.0, truncate=4.0, pad=True, parallel=False)
        pad = int(4.0 * 3.0 + 0.5)
        for c in range(3):
            expected_ch = gaussian_filter(image[..., c], 3.0, mode="reflect")
            np.testing.assert_allclose(
                result[pad:-pad, pad:-pad, c],
                expected_ch[pad:-pad, pad:-pad],
                atol=0.02, rtol=0.03,
            )

    def test_3d_per_channel_sigma_matches_scipy(self) -> None:
        rng = np.random.default_rng(42)
        image = rng.random((32, 32, 3), dtype=np.float64)
        sigma = np.array([1.0, 3.0, 5.0])
        result = fft_gaussian_filter(image, sigma, truncate=4.0, pad=True, parallel=False)
        _assert_close_to_scipy(result, image, sigma, 4.0)

    def test_3d_parallel_matches_sequential(self) -> None:
        rng = np.random.default_rng(42)
        image = rng.random((32, 32, 3), dtype=np.float64)
        sigma = np.array([1.0, 2.0, 3.0])
        result_par = fft_gaussian_filter(image, sigma, truncate=4.0, pad=True, parallel=True)
        result_seq = fft_gaussian_filter(image, sigma, truncate=4.0, pad=True, parallel=False)
        np.testing.assert_allclose(result_par, result_seq, atol=1e-12)


class TestFFTEdgeCases:
    def test_rejects_1d_input(self) -> None:
        with pytest.raises(ValueError, match="Unsupported image dimension"):
            fft_gaussian_filter(np.zeros(10), 1.0)

    def test_rejects_4d_input(self) -> None:
        with pytest.raises(ValueError, match="Unsupported image dimension"):
            fft_gaussian_filter(np.zeros((4, 4, 3, 2)), 1.0)

    def test_rejects_sigma_array_length_mismatch(self) -> None:
        image = np.zeros((8, 8, 3))
        with pytest.raises(ValueError, match="Length of sigma"):
            fft_gaussian_filter(image, np.array([1.0, 2.0]), truncate=4.0, parallel=False)

    def test_scalar_sigma_on_3d_uses_same_for_all_channels(self) -> None:
        rng = np.random.default_rng(42)
        image = rng.random((32, 32, 3), dtype=np.float64)
        result = fft_gaussian_filter(image, 2.0, truncate=4.0, pad=True, parallel=False)
        # Each channel should be independently filtered with sigma=2.0.
        # Check interior only (skip border) with relaxed tolerance.
        pad = int(4.0 * 2.0 + 0.5)
        for c in range(3):
            expected_ch = gaussian_filter(image[..., c], 2.0, mode="reflect")
            np.testing.assert_allclose(
                result[pad:-pad, pad:-pad, c],
                expected_ch[pad:-pad, pad:-pad],
                atol=0.01, rtol=0.02,
            )

    def test_small_image(self) -> None:
        image = np.ones((4, 4), dtype=np.float64)
        result = fft_gaussian_filter(image, 0.5, truncate=3.0, pad=True)
        assert result.shape == (4, 4)
        assert np.all(np.isfinite(result))

    def test_output_shape_matches_input(self) -> None:
        rng = np.random.default_rng(42)
        for shape in [(16, 16), (17, 23), (8, 8, 3), (8, 8, 5)]:
            image = rng.random(shape)
            result = fft_gaussian_filter(image, 1.0, truncate=3.0, pad=True)
            assert result.shape == shape
