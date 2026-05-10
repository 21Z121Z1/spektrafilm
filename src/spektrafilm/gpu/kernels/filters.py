from __future__ import annotations

from typing import Any

import numpy as np

from spektrafilm.utils.fast_gaussian_filter import (
    _gaussian_kernel_1d,
    fast_exponential_filter,
    fast_gaussian_filter,
    fast_gaussian_filter_small,
)


_GAUSSIAN_FIR_KERNEL = None
_REFLECT_PAD_HW_KERNEL = None


def _backend_supports_gpu(backend) -> bool:
    return backend is not None and bool(getattr(backend, "supports_gpu", False))


def _get_gaussian_fir_kernel(mx):
    """Return the cached MLX/Metal separable FIR Gaussian kernel."""
    global _GAUSSIAN_FIR_KERNEL
    if _GAUSSIAN_FIR_KERNEL is not None:
        return _GAUSSIAN_FIR_KERNEL

    source = """
        uint elem = thread_position_in_grid.x;
        uint total = image_shape[0] * image_shape[1] * image_shape[2];
        if (elem >= total) {
            return;
        }

        int C = image_shape[2];
        int W = image_shape[1];
        int H = image_shape[0];
        int c = elem % C;
        int x = (elem / C) % W;
        int y = elem / (C * W);
        int max_radius = kernels_shape[1] / 2;
        int radius = radii[c];

        if (sigma[c] <= 0.0f || radius <= 0) {
            out[elem] = image[elem];
            return;
        }

        float total_value = 0.0f;
        for (int dy = -radius; dy <= radius; ++dy) {
            int yy = y + dy;
            if (H <= 1) {
                yy = 0;
            } else {
                int period_y = 2 * H;
                yy = yy % period_y;
                if (yy < 0) {
                    yy += period_y;
                }
                if (yy >= H) {
                    yy = period_y - 1 - yy;
                }
            }
            float wy = kernels[c * kernels_shape[1] + dy + max_radius];

            for (int dx = -radius; dx <= radius; ++dx) {
                int xx = x + dx;
                if (W <= 1) {
                    xx = 0;
                } else {
                    int period_x = 2 * W;
                    xx = xx % period_x;
                    if (xx < 0) {
                        xx += period_x;
                    }
                    if (xx >= W) {
                        xx = period_x - 1 - xx;
                    }
                }
                float wx = kernels[c * kernels_shape[1] + dx + max_radius];
                uint src = ((uint)yy * W + (uint)xx) * C + (uint)c;
                total_value += float(image[src]) * wy * wx;
            }
        }
        out[elem] = T(total_value);
    """
    _GAUSSIAN_FIR_KERNEL = mx.fast.metal_kernel(
        name="spektrafilm_gaussian_fir_reflect",
        input_names=["image", "kernels", "radii", "sigma"],
        output_names=["out"],
        source=source,
    )
    return _GAUSSIAN_FIR_KERNEL


def _get_reflect_pad_hw_kernel(mx):
    """Return the cached MLX/Metal H/W reflect-padding kernel."""
    global _REFLECT_PAD_HW_KERNEL
    if _REFLECT_PAD_HW_KERNEL is not None:
        return _REFLECT_PAD_HW_KERNEL

    source = """
        uint elem = thread_position_in_grid.x;
        int H = image_shape[0];
        int W = image_shape[1];
        int C = image_shape[2];
        int out_H = H + 2 * PAD;
        int out_W = W + 2 * PAD;
        uint total = out_H * out_W * C;
        if (elem >= total) {
            return;
        }

        int c = elem % C;
        int x = (elem / C) % out_W;
        int y = elem / (C * out_W);
        int yy = y - PAD;
        if (H <= 1) {
            yy = 0;
        } else {
            int period_y = 2 * H - 2;
            yy = yy % period_y;
            if (yy < 0) {
                yy += period_y;
            }
            if (yy >= H) {
                yy = period_y - yy;
            }
        }
        int xx = x - PAD;
        if (W <= 1) {
            xx = 0;
        } else {
            int period_x = 2 * W - 2;
            xx = xx % period_x;
            if (xx < 0) {
                xx += period_x;
            }
            if (xx >= W) {
                xx = period_x - xx;
            }
        }
        out[elem] = image[((uint)yy * W + (uint)xx) * C + (uint)c];
    """
    _REFLECT_PAD_HW_KERNEL = mx.fast.metal_kernel(
        name="spektrafilm_reflect_pad_hw",
        input_names=["image"],
        output_names=["out"],
        source=source,
    )
    return _REFLECT_PAD_HW_KERNEL


def _normalize_sigma_for_channels(sigma: Any, channels: int) -> np.ndarray:
    sigma_array = np.asarray(sigma, dtype=np.float64)
    if sigma_array.ndim == 0 or sigma_array.size == 1:
        return np.full(channels, float(sigma_array.reshape(-1)[0]), dtype=np.float64)
    sigma_array = sigma_array.ravel()
    if sigma_array.shape[0] != channels:
        raise ValueError(f"sigma length {sigma_array.shape[0]} does not match channel count {channels}")
    return sigma_array


def _promote_image_to_3d(image: Any):
    shape = tuple(image.shape)
    if len(shape) == 2:
        return image[..., None], True
    if len(shape) == 3:
        return image, False
    raise ValueError(f"Unsupported image dimension: {len(shape)}")


def gaussian_filter_small_backend(
    image: Any,
    sigma: Any,
    backend=None,
    *,
    truncate: float = 3.0,
) -> Any:
    """Small-sigma Gaussian FIR with SciPy reflect boundary semantics.

    For GPU backends this uses a cached MLX custom Metal kernel. For CPU
    fallback it delegates to the existing Numba FIR implementation.
    """
    if not _backend_supports_gpu(backend):
        return fast_gaussian_filter_small(image, sigma, truncate=truncate)

    image_3d, squeeze = _promote_image_to_3d(backend.asarray(image))
    channels = int(image_3d.shape[-1])
    sigmas = _normalize_sigma_for_channels(sigma, channels)
    max_sigma = float(np.max(sigmas))
    if max_sigma <= 0.0:
        return image_3d[..., 0] if squeeze else image_3d

    kernels = []
    radii = []
    max_radius = 0
    for sigma_ch in sigmas:
        kernel_ch, radius_ch = _gaussian_kernel_1d(float(sigma_ch), float(truncate))
        kernels.append(np.asarray(kernel_ch, dtype=np.float32))
        radii.append(int(radius_ch))
        max_radius = max(max_radius, int(radius_ch))
    kernel_rows = np.zeros((channels, 2 * max_radius + 1), dtype=np.float32)
    for channel, (kernel_ch, radius_ch) in enumerate(zip(kernels, radii)):
        start = max_radius - int(radius_ch)
        kernel_rows[channel, start:start + kernel_ch.size] = kernel_ch
    mx = backend.mx
    kernel = mx.array(kernel_rows, dtype=mx.float32)
    radii_mx = mx.array(np.asarray(radii, dtype=np.int32), dtype=mx.int32)
    sigma_mx = mx.array(sigmas.astype(np.float32), dtype=mx.float32)
    fir = _get_gaussian_fir_kernel(mx)
    outputs = fir(
        inputs=[image_3d, kernel, radii_mx, sigma_mx],
        template=[("T", image_3d.dtype)],
        grid=(int(np.prod(image_3d.shape)), 1, 1),
        threadgroup=(128, 1, 1),
        output_shapes=[image_3d.shape],
        output_dtypes=[image_3d.dtype],
    )
    out = outputs[0]
    return out[..., 0] if squeeze else out


def reflect_pad_hw_backend(image: Any, pad: int, backend=None) -> Any:
    """Pad the first two dimensions using NumPy ``mode='reflect'`` semantics."""
    pad = int(pad)
    if pad <= 0:
        return image
    if not _backend_supports_gpu(backend):
        return np.pad(np.asarray(image), ((pad, pad), (pad, pad), (0, 0)), mode="reflect")

    image_mx = backend.asarray(image)
    if len(tuple(image_mx.shape)) != 3:
        raise ValueError("reflect_pad_hw_backend expects an HxWxC array")
    out_shape = (
        int(image_mx.shape[0]) + 2 * pad,
        int(image_mx.shape[1]) + 2 * pad,
        int(image_mx.shape[2]),
    )
    kernel = _get_reflect_pad_hw_kernel(backend.mx)
    outputs = kernel(
        inputs=[image_mx],
        template=[("T", image_mx.dtype), ("PAD", pad)],
        grid=(int(np.prod(out_shape)), 1, 1),
        threadgroup=(256, 1, 1),
        output_shapes=[out_shape],
        output_dtypes=[image_mx.dtype],
    )
    return outputs[0]


def gaussian_filter_backend(
    image: Any,
    sigma: Any,
    backend=None,
    *,
    truncate: float = 3.0,
) -> Any:
    """Backend-aware Gaussian blur.

    The GPU path uses the exact small-sigma FIR kernel for sigma < 3 px and
    intentionally falls back to the existing CPU IIR path for larger sigmas
    until a high-confidence FFT/MPS large-sigma replacement is available.
    """
    if not _backend_supports_gpu(backend):
        return fast_gaussian_filter(image, sigma, truncate=truncate)

    channels = int(image.shape[-1]) if len(tuple(image.shape)) == 3 else 1
    sigmas = _normalize_sigma_for_channels(sigma, channels)
    if np.max(sigmas) >= 3.0:
        return backend.asarray(fast_gaussian_filter(backend.to_numpy(image), sigma, truncate=truncate))
    return gaussian_filter_small_backend(image, sigmas, backend, truncate=truncate)


def exponential_filter_backend(
    image: Any,
    decay_constant: Any,
    backend=None,
    *,
    n_gaussians: int = 3,
    truncate: float = 3.0,
) -> Any:
    """Backend-aware exponential filter using the existing Gaussian mixture."""
    if not _backend_supports_gpu(backend):
        return fast_exponential_filter(
            image,
            decay_constant,
            n_gaussians=n_gaussians,
            truncate=truncate,
        )

    from spektrafilm.utils.fast_gaussian_filter import _EXPONENTIAL_GAUSSIAN_FITS

    if n_gaussians not in _EXPONENTIAL_GAUSSIAN_FITS:
        raise ValueError(
            f"No hardcoded fit for n_gaussians={n_gaussians}; "
            f"available: {sorted(_EXPONENTIAL_GAUSSIAN_FITS)}"
        )
    decay = np.asarray(decay_constant, dtype=np.float64)
    result = None
    for amplitude, sigma_ratio in _EXPONENTIAL_GAUSSIAN_FITS[n_gaussians]:
        component = gaussian_filter_backend(
            image,
            sigma_ratio * decay,
            backend,
            truncate=truncate,
        )
        result = amplitude * component if result is None else result + amplitude * component
    return result


def fft_convolve_same_backend(image: Any, kernel: Any, backend=None) -> Any:
    """Channel-wise 2D FFT convolution with ``mode='same'`` output.

    ``image`` and ``kernel`` are HxWxC arrays. This mirrors scipy's centered
    ``fftconvolve(..., mode='same')`` cropping for the shapes used by the
    diffusion-filter path.
    """
    if not _backend_supports_gpu(backend):
        from scipy.signal import fftconvolve

        image_np = np.asarray(image)
        kernel_np = np.asarray(kernel)
        output = np.empty_like(image_np)
        for channel in range(image_np.shape[2]):
            output[:, :, channel] = fftconvolve(
                image_np[:, :, channel],
                kernel_np[:, :, channel],
                mode="same",
            )
        return output

    mx = backend.mx
    image_mx = backend.asarray(image)
    kernel_mx = mx.array(np.asarray(kernel, dtype=np.float32), dtype=mx.float32)
    image_h, image_w, channels = (int(v) for v in image_mx.shape)
    kernel_h, kernel_w = int(kernel_mx.shape[0]), int(kernel_mx.shape[1])
    fft_h = image_h + kernel_h - 1
    fft_w = image_w + kernel_w - 1
    image_fft = mx.fft.fft2(image_mx, s=(fft_h, fft_w), axes=(0, 1))
    kernel_fft = mx.fft.fft2(kernel_mx, s=(fft_h, fft_w), axes=(0, 1))
    convolved = mx.real(mx.fft.ifft2(image_fft * kernel_fft, axes=(0, 1)))
    start_y = (kernel_h - 1) // 2
    start_x = (kernel_w - 1) // 2
    return convolved[start_y:start_y + image_h, start_x:start_x + image_w, :channels]
