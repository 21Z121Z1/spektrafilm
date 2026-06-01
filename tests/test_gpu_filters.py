from __future__ import annotations

import numpy as np
import pytest
from scipy.signal import fftconvolve

from spektrafilm.gpu.backend import BackendUnavailableError, select_backend
from spektrafilm.gpu.kernels.filters import (
    exponential_filter_backend,
    fft_convolve_same_backend,
    gaussian_filter_backend,
    gaussian_filter_large_backend,
    gaussian_filter_small_backend,
    reflect_pad_hw_backend,
)
from spektrafilm.gpu.numpy_backend import NumpyBackend
from spektrafilm.model.diffusion import apply_diffusion_filter_um, apply_halation_um
from spektrafilm.runtime.params_schema import DiffusionFilterParams, HalationParams
from spektrafilm.utils.fast_gaussian_filter import (
    fast_exponential_filter,
    fast_gaussian_filter,
    fast_gaussian_filter_small,
)


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


def test_halation_mlx_stays_on_device_when_available(monkeypatch) -> None:
    backend = _mlx_backend_or_skip()
    image = _sample_image().astype(np.float32) + 0.1
    halation = HalationParams(
        active=True,
        scatter_amount=0.65,
        scatter_spatial_scale=1.0,
        halation_amount=0.45,
        halation_spatial_scale=1.0,
        scatter_core_um=(2.5, 0.0, 1.2),
        scatter_tail_um=(7.5, 5.0, 0.0),
        scatter_tail_weight=(0.35, 0.20, 0.0),
        halation_strength=(0.05, 0.02, 0.0),
        halation_first_sigma_um=(8.0, 5.0, 0.0),
        halation_n_bounces=2,
        halation_bounce_decay=0.5,
    )

    def fail_to_numpy(_value):
        raise AssertionError("halation MLX path must not materialize the full image on CPU")

    monkeypatch.setattr(backend, "to_numpy", fail_to_numpy)

    actual = apply_halation_um(backend.asarray(image), halation, pixel_size_um=4.0, backend=backend)
    backend.eval(actual)
    actual_np = np.asarray(actual)

    assert backend._is_mlx_array(actual)
    assert actual_np.shape == image.shape
    assert np.isfinite(actual_np).all()


def test_diffusion_filter_mlx_stays_on_device_when_available(monkeypatch) -> None:
    backend = _mlx_backend_or_skip()
    image = _sample_image().astype(np.float32) + 0.1
    diffusion_filter = DiffusionFilterParams(
        active=True,
        filter_family="glimmerglass",
        strength=0.25,
        spatial_scale=0.8,
        halo_warmth=0.1,
    )

    def fail_to_numpy(_value):
        raise AssertionError("diffusion filter MLX path must not materialize the full image on CPU")

    monkeypatch.setattr(backend, "to_numpy", fail_to_numpy)

    actual = apply_diffusion_filter_um(
        backend.asarray(image),
        diffusion_filter,
        pixel_size_um=120.0,
        backend=backend,
    )
    backend.eval(actual)
    actual_np = np.asarray(actual)

    assert backend._is_mlx_array(actual)
    assert actual_np.shape == image.shape
    assert np.isfinite(actual_np).all()


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


# ---------------------------------------------------------------------------
# Parity: exponential filter backend vs CPU reference
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("backend_name", _available_backends())
def test_exponential_filter_backend_matches_cpu_reference(backend_name: str) -> None:
    """GPU exponential filter must match the CPU Gaussian-mixture reference.

    Tolerance is 5e-4 to account for IIR accumulation differences on MLX
    float32 and potential backend-specific rounding.
    """
    backend = _get_backend(backend_name)
    rng = np.random.default_rng(42)
    image = rng.random((64, 64, 3))
    dtype = np.float64 if backend_name == "cpu" else np.float32
    image_backend = backend.asarray(image.astype(dtype))

    result = exponential_filter_backend(image_backend, 9.0, backend)
    result_np = backend.to_numpy(result)
    expected = fast_exponential_filter(image.astype(dtype), 9.0)

    max_abs_diff = float(np.max(np.abs(result_np - expected)))
    assert np.allclose(result_np, expected, atol=5e-4), (
        f"backend={backend_name!r} exponential filter mismatch: max_abs_diff={max_abs_diff:.2e}"
    )


# ---------------------------------------------------------------------------
# Parity: Gaussian IIR systematic bias bounds
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("backend_name", _available_backends())
def test_gaussian_filter_iir_systematic_bias_bounded(backend_name: str) -> None:
    """Large-sigma Gaussian IIR must stay within bounded systematic bias.

    MLX float32 IIR accumulates ~5e-6 bias vs float64 reference; other
    backends should be tighter.
    """
    backend = _get_backend(backend_name)
    rng = np.random.default_rng(42)
    image = rng.random((64, 64, 3))
    dtype = np.float64 if backend_name == "cpu" else np.float32
    image_backend = backend.asarray(image.astype(dtype))

    result = gaussian_filter_backend(image_backend, 5.0, backend)
    result_np = backend.to_numpy(result)
    expected = fast_gaussian_filter(image.astype(dtype), 5.0)

    max_abs_diff = float(np.max(np.abs(result_np - expected)))
    tolerance = 5e-6 if backend_name == "mlx" else 1e-6
    assert max_abs_diff < tolerance, (
        f"backend={backend_name!r} Gaussian IIR bias {max_abs_diff:.2e} "
        f"exceeds tolerance {tolerance:.2e}"
    )
