from __future__ import annotations

import numpy as np
import pytest
from scipy.signal import fftconvolve

from spektrafilm.gpu.backend import BackendUnavailableError, select_backend
from spektrafilm.gpu.kernels.filters import (
    fft_convolve_same_backend,
    gaussian_filter_backend,
    gaussian_filter_large_backend,
    gaussian_filter_small_backend,
    reflect_pad_hw_backend,
)
from spektrafilm.gpu.numpy_backend import NumpyBackend
from spektrafilm.utils.fast_gaussian_filter import (
    fast_gaussian_filter,
    fast_gaussian_filter_small,
)


pytestmark = pytest.mark.unit


def _sample_image() -> np.ndarray:
    y = np.linspace(0.0, 1.0, 6, dtype=np.float64)[:, None]
    x = np.linspace(0.0, 1.0, 7, dtype=np.float64)[None, :]
    return np.stack(
        (
            x.repeat(6, axis=0),
            y.repeat(7, axis=1),
            0.25 + 0.5 * x.repeat(6, axis=0) * y.repeat(7, axis=1),
        ),
        axis=-1,
    )


def _mlx_backend_or_skip():
    try:
        return select_backend("mlx")
    except BackendUnavailableError as exc:
        pytest.skip(str(exc))


def _cupy_backend_or_skip():
    try:
        return select_backend("cupy")
    except BackendUnavailableError as exc:
        pytest.skip(str(exc))


def test_gaussian_filter_backend_cpu_fallback_matches_fast_gaussian_filter() -> None:
    backend = NumpyBackend()
    image = _sample_image()

    for sigma in (0.75, 3.5, np.array([0.5, 1.25, 2.0])):
        actual = gaussian_filter_backend(image, sigma, backend)
        expected = fast_gaussian_filter(image, sigma)
        np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-12)


def test_reflect_pad_hw_backend_cpu_fallback_matches_numpy_reflect() -> None:
    backend = NumpyBackend()
    image = _sample_image()

    actual = reflect_pad_hw_backend(image, 2, backend)
    expected = np.pad(image, ((2, 2), (2, 2), (0, 0)), mode="reflect")

    np.testing.assert_array_equal(actual, expected)


def test_fft_convolve_same_backend_cpu_fallback_matches_scipy_per_channel() -> None:
    backend = NumpyBackend()
    image = _sample_image()
    kernel = np.zeros((3, 3, 3), dtype=np.float64)
    kernel[:, :, 0] = np.array([[0.0, 0.1, 0.0], [0.1, 0.6, 0.1], [0.0, 0.1, 0.0]])
    kernel[:, :, 1] = np.array([[0.05, 0.1, 0.05], [0.1, 0.4, 0.1], [0.05, 0.1, 0.05]])
    kernel[:, :, 2] = np.array([[0.0, 0.2, 0.0], [0.2, 0.2, 0.2], [0.0, 0.2, 0.0]])

    actual = fft_convolve_same_backend(image, kernel, backend)
    expected = np.empty_like(image)
    for channel in range(3):
        expected[:, :, channel] = fftconvolve(image[:, :, channel], kernel[:, :, channel], mode="same")

    np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-12)


def test_gaussian_filter_small_mlx_matches_cpu_reference_when_available() -> None:
    backend = _mlx_backend_or_skip()
    image = _sample_image().astype(np.float32)
    sigma = np.array([0.5, 1.0, 1.5], dtype=np.float32)

    actual = gaussian_filter_small_backend(image, sigma, backend)
    expected = fast_gaussian_filter_small(image, sigma)

    np.testing.assert_allclose(backend.to_numpy(actual), expected, rtol=3e-5, atol=3e-5)


def test_gaussian_filter_large_mlx_matches_cpu_reference_when_available() -> None:
    backend = _mlx_backend_or_skip()
    image = _sample_image().astype(np.float32)
    sigma = np.array([3.0, 3.5, 4.0], dtype=np.float32)

    actual = gaussian_filter_large_backend(image, sigma, backend)
    expected = fast_gaussian_filter(image, sigma)

    np.testing.assert_allclose(backend.to_numpy(actual), expected, rtol=5e-4, atol=5e-4)


def test_gaussian_filter_mixed_sigma_mlx_stays_on_device_when_available(monkeypatch) -> None:
    backend = _mlx_backend_or_skip()
    image = _sample_image().astype(np.float32)
    sigma = np.array([0.75, 3.25, 1.5], dtype=np.float32)

    def fail_to_numpy(_value):
        raise AssertionError("mixed-sigma MLX Gaussian path must not materialize the full image on CPU")

    monkeypatch.setattr(backend, "to_numpy", fail_to_numpy)

    actual = gaussian_filter_backend(backend.asarray(image), sigma, backend)
    backend.eval(actual)
    expected = fast_gaussian_filter(image, sigma)

    np.testing.assert_allclose(np.asarray(actual), expected, rtol=6e-4, atol=6e-4)


def test_fft_convolve_same_cupy_matches_scipy_reference_when_available() -> None:
    backend = _cupy_backend_or_skip()
    image = _sample_image().astype(np.float32)
    kernel = np.zeros((3, 3, 3), dtype=np.float32)
    kernel[:, :, 0] = np.array([[0.0, 0.1, 0.0], [0.1, 0.6, 0.1], [0.0, 0.1, 0.0]])
    kernel[:, :, 1] = np.array([[0.05, 0.1, 0.05], [0.1, 0.4, 0.1], [0.05, 0.1, 0.05]])
    kernel[:, :, 2] = np.array([[0.0, 0.2, 0.0], [0.2, 0.2, 0.2], [0.0, 0.2, 0.0]])

    actual = fft_convolve_same_backend(backend.asarray(image), kernel, backend)
    expected = np.empty_like(image)
    for channel in range(3):
        expected[:, :, channel] = fftconvolve(image[:, :, channel], kernel[:, :, channel], mode="same")

    np.testing.assert_allclose(backend.to_numpy(actual), expected, rtol=2e-6, atol=2e-6)
