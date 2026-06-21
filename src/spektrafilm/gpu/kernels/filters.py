from __future__ import annotations

from typing import Any

import numpy as np

from spektrafilm.utils.fast_gaussian_filter import (
    _gaussian_kernel_1d,
    _yvv_coeffs,
    fast_exponential_filter,
    fast_gaussian_filter,
    fast_gaussian_filter_small,
)


_GAUSSIAN_FIR_KERNEL = None
_GAUSSIAN_IIR_HORIZONTAL_KERNEL = None
_GAUSSIAN_IIR_VERTICAL_KERNEL = None
_REFLECT_PAD_HW_KERNEL = None
_GAUSSIAN_IIR_HORIZONTAL_KERNEL_F64 = None
_GAUSSIAN_IIR_VERTICAL_KERNEL_F64 = None


def _backend_supports_gpu(backend) -> bool:
    return backend is not None and bool(getattr(backend, "supports_gpu", False))


def _backend_supports_mlx_custom_kernels(backend) -> bool:
    return _backend_supports_gpu(backend) and hasattr(backend, "mx")


def _backend_supports_cupy(backend) -> bool:
    return _backend_supports_gpu(backend) and hasattr(backend, "cp")


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


def _get_gaussian_iir_horizontal_kernel(mx):
    """Return the cached MLX/Metal horizontal YVV Gaussian kernel."""
    global _GAUSSIAN_IIR_HORIZONTAL_KERNEL
    if _GAUSSIAN_IIR_HORIZONTAL_KERNEL is not None:
        return _GAUSSIAN_IIR_HORIZONTAL_KERNEL

    source = """
        uint elem = thread_position_in_grid.x;
        int H = image_shape[0];
        int W = image_shape[1];
        int C = image_shape[2];
        uint total = H * C;
        if (elem >= total) {
            return;
        }

        int c = elem % C;
        int y = elem / C;
        float b = B[c];
        float b1 = B1[c];
        float b2 = B2[c];
        float b3 = B3[c];

        uint first = ((uint)y * W) * C + (uint)c;
        float x0 = float(image[first]);
        float w1 = x0;
        float w2 = x0;
        float w3 = x0;
        for (int x = 0; x < W; ++x) {
            uint idx = ((uint)y * W + (uint)x) * C + (uint)c;
            float w = b * float(image[idx]) + b1 * w1 + b2 * w2 + b3 * w3;
            tmp[idx] = T(w);
            w3 = w2;
            w2 = w1;
            w1 = w;
        }

        uint last = ((uint)y * W + (uint)(W - 1)) * C + (uint)c;
        float y1 = float(tmp[last]);
        float y2 = y1;
        float y3 = y1;
        for (int x = W - 1; x >= 0; --x) {
            uint idx = ((uint)y * W + (uint)x) * C + (uint)c;
            float out_v = b * float(tmp[idx]) + b1 * y1 + b2 * y2 + b3 * y3;
            tmp[idx] = T(out_v);
            y3 = y2;
            y2 = y1;
            y1 = out_v;
        }
    """
    _GAUSSIAN_IIR_HORIZONTAL_KERNEL = mx.fast.metal_kernel(
        name="spektrafilm_gaussian_iir_horizontal",
        input_names=["image", "B", "B1", "B2", "B3"],
        output_names=["tmp"],
        source=source,
    )
    return _GAUSSIAN_IIR_HORIZONTAL_KERNEL


def _get_gaussian_iir_vertical_kernel(mx):
    """Return the cached MLX/Metal vertical YVV Gaussian kernel."""
    global _GAUSSIAN_IIR_VERTICAL_KERNEL
    if _GAUSSIAN_IIR_VERTICAL_KERNEL is not None:
        return _GAUSSIAN_IIR_VERTICAL_KERNEL

    source = """
        uint elem = thread_position_in_grid.x;
        int H = tmp_shape[0];
        int W = tmp_shape[1];
        int C = tmp_shape[2];
        uint total = W * C;
        if (elem >= total) {
            return;
        }

        int c = elem % C;
        int x = elem / C;
        float b = B[c];
        float b1 = B1[c];
        float b2 = B2[c];
        float b3 = B3[c];

        uint first = ((uint)0 * W + (uint)x) * C + (uint)c;
        float x0 = float(tmp[first]);
        float w1 = x0;
        float w2 = x0;
        float w3 = x0;
        for (int y = 0; y < H; ++y) {
            uint idx = ((uint)y * W + (uint)x) * C + (uint)c;
            float w = b * float(tmp[idx]) + b1 * w1 + b2 * w2 + b3 * w3;
            out[idx] = T(w);
            w3 = w2;
            w2 = w1;
            w1 = w;
        }

        uint last = ((uint)(H - 1) * W + (uint)x) * C + (uint)c;
        float y1 = float(out[last]);
        float y2 = y1;
        float y3 = y1;
        for (int y = H - 1; y >= 0; --y) {
            uint idx = ((uint)y * W + (uint)x) * C + (uint)c;
            float out_v = b * float(out[idx]) + b1 * y1 + b2 * y2 + b3 * y3;
            out[idx] = T(out_v);
            y3 = y2;
            y2 = y1;
            y1 = out_v;
        }
    """
    _GAUSSIAN_IIR_VERTICAL_KERNEL = mx.fast.metal_kernel(
        name="spektrafilm_gaussian_iir_vertical",
        input_names=["tmp", "B", "B1", "B2", "B3"],
        output_names=["out"],
        source=source,
    )
    return _GAUSSIAN_IIR_VERTICAL_KERNEL


def _get_gaussian_iir_horizontal_kernel_f64(mx):
    """Return the cached double-precision horizontal YVV Gaussian kernel."""
    global _GAUSSIAN_IIR_HORIZONTAL_KERNEL_F64
    if _GAUSSIAN_IIR_HORIZONTAL_KERNEL_F64 is not None:
        return _GAUSSIAN_IIR_HORIZONTAL_KERNEL_F64

    source = """
        uint elem = thread_position_in_grid.x;
        int H = image_shape[0];
        int W = image_shape[1];
        int C = image_shape[2];
        uint total = H * C;
        if (elem >= total) {
            return;
        }

        int c = elem % C;
        int y = elem / C;
        double b = (double)B[c];
        double b1 = (double)B1[c];
        double b2 = (double)B2[c];
        double b3 = (double)B3[c];

        uint first = ((uint)y * W) * C + (uint)c;
        double x0 = (double)image[first];
        double w1 = x0;
        double w2 = x0;
        double w3 = x0;
        for (int x = 0; x < W; ++x) {
            uint idx = ((uint)y * W + (uint)x) * C + (uint)c;
            double w = b * (double)image[idx] + b1 * w1 + b2 * w2 + b3 * w3;
            tmp[idx] = T(w);
            w3 = w2;
            w2 = w1;
            w1 = w;
        }

        uint last = ((uint)y * W + (uint)(W - 1)) * C + (uint)c;
        double y1 = (double)tmp[last];
        double y2 = y1;
        double y3 = y1;
        for (int x = W - 1; x >= 0; --x) {
            uint idx = ((uint)y * W + (uint)x) * C + (uint)c;
            double out_v = b * (double)tmp[idx] + b1 * y1 + b2 * y2 + b3 * y3;
            tmp[idx] = T(out_v);
            y3 = y2;
            y2 = y1;
            y1 = out_v;
        }
    """
    _GAUSSIAN_IIR_HORIZONTAL_KERNEL_F64 = mx.fast.metal_kernel(
        name="spektrafilm_gaussian_iir_horizontal_f64",
        input_names=["image", "B", "B1", "B2", "B3"],
        output_names=["tmp"],
        source=source,
    )
    return _GAUSSIAN_IIR_HORIZONTAL_KERNEL_F64


def _get_gaussian_iir_vertical_kernel_f64(mx):
    """Return the cached double-precision vertical YVV Gaussian kernel."""
    global _GAUSSIAN_IIR_VERTICAL_KERNEL_F64
    if _GAUSSIAN_IIR_VERTICAL_KERNEL_F64 is not None:
        return _GAUSSIAN_IIR_VERTICAL_KERNEL_F64

    source = """
        uint elem = thread_position_in_grid.x;
        int H = tmp_shape[0];
        int W = tmp_shape[1];
        int C = tmp_shape[2];
        uint total = W * C;
        if (elem >= total) {
            return;
        }

        int c = elem % C;
        int x = elem / C;
        double b = (double)B[c];
        double b1 = (double)B1[c];
        double b2 = (double)B2[c];
        double b3 = (double)B3[c];

        uint first = ((uint)0 * W + (uint)x) * C + (uint)c;
        double x0 = (double)tmp[first];
        double w1 = x0;
        double w2 = x0;
        double w3 = x0;
        for (int y = 0; y < H; ++y) {
            uint idx = ((uint)y * W + (uint)x) * C + (uint)c;
            double w = b * (double)tmp[idx] + b1 * w1 + b2 * w2 + b3 * w3;
            out[idx] = T(w);
            w3 = w2;
            w2 = w1;
            w1 = w;
        }

        uint last = ((uint)(H - 1) * W + (uint)x) * C + (uint)c;
        double y1 = (double)out[last];
        double y2 = y1;
        double y3 = y1;
        for (int y = H - 1; y >= 0; --y) {
            uint idx = ((uint)y * W + (uint)x) * C + (uint)c;
            double out_v = b * (double)out[idx] + b1 * y1 + b2 * y2 + b3 * y3;
            out[idx] = T(out_v);
            y3 = y2;
            y2 = y1;
            y1 = out_v;
        }
    """
    _GAUSSIAN_IIR_VERTICAL_KERNEL_F64 = mx.fast.metal_kernel(
        name="spektrafilm_gaussian_iir_vertical_f64",
        input_names=["tmp", "B", "B1", "B2", "B3"],
        output_names=["out"],
        source=source,
    )
    return _GAUSSIAN_IIR_VERTICAL_KERNEL_F64


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


def _gaussian_filter_cupy(
    image: Any,
    sigma: Any,
    backend,
    *,
    truncate: float = 3.0,
) -> Any:
    import cupyx.scipy.ndimage as cupy_ndimage

    cp = backend.cp
    image_3d, squeeze = _promote_image_to_3d(backend.asarray(image))
    channels = int(image_3d.shape[-1])
    sigmas = _normalize_sigma_for_channels(sigma, channels)
    out = cp.empty_like(image_3d)
    for channel, sigma_ch in enumerate(sigmas):
        if float(sigma_ch) <= 0.0:
            out[..., channel] = image_3d[..., channel]
        else:
            out[..., channel] = cupy_ndimage.gaussian_filter(
                image_3d[..., channel],
                float(sigma_ch),
                mode="reflect",
                truncate=float(truncate),
            )
    return out[..., 0] if squeeze else out


def gaussian_filter_small_backend(
    image: Any,
    sigma: Any,
    backend=None,
    *,
    truncate: float = 3.0,
) -> Any:
    """Small-sigma Gaussian FIR with SciPy reflect boundary semantics.

    MLX uses a cached custom Metal kernel. CuPy uses cupyx.scipy.ndimage on
    device arrays. CPU fallback delegates to the existing Numba FIR
    implementation.
    """
    if not _backend_supports_gpu(backend):
        return fast_gaussian_filter_small(image, sigma, truncate=truncate)
    if _backend_supports_cupy(backend):
        return _gaussian_filter_cupy(image, sigma, backend, truncate=truncate)
    if not _backend_supports_mlx_custom_kernels(backend):
        return backend.asarray(fast_gaussian_filter_small(backend.to_numpy(image), sigma, truncate=truncate))

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


def gaussian_filter_large_backend(
    image: Any,
    sigma: Any,
    backend=None,
    *,
    _precision: str = "float32",
) -> Any:
    """Large-sigma YVV Gaussian matching ``fast_gaussian_filter`` dispatch.

    When *_precision* is ``"float64"``, attempts double-precision IIR on
    the GPU (Metal ``double``).  If the GPU backend does not support
    float64 (current Apple Silicon via MLX), falls back to the CPU
    float64 YVV implementation for exact parity with the reference path.

    **Known float32 bias:** The Young-van Vliet IIR filter in float32
    accumulates a systematic bias of ~5e-6 vs the float64 reference.
    This is inherent to the reduced-precision accumulation and is
    visually imperceptible.  Use ``_precision="float64"`` where exact
    parity is required (unit tests, halide-vs-CPU assertions).
    """
    if not _backend_supports_gpu(backend):
        return fast_gaussian_filter(image, sigma)
    if _backend_supports_cupy(backend):
        return _gaussian_filter_cupy(image, sigma, backend)
    if not _backend_supports_mlx_custom_kernels(backend):
        return backend.asarray(fast_gaussian_filter(backend.to_numpy(image), sigma))

    image_3d, squeeze = _promote_image_to_3d(backend.asarray(image))
    channels = int(image_3d.shape[-1])
    sigmas = _normalize_sigma_for_channels(sigma, channels)
    if np.any(sigmas < 3.0):
        raise ValueError("gaussian_filter_large_backend expects all sigmas >= 3")

    mx = backend.mx
    use_f64 = _precision == "float64"
    coeff_np_dtype = np.float64 if use_f64 else np.float32
    coeff_mx_dtype = mx.float64 if use_f64 else mx.float32

    if use_f64:
        try:
            image_3d = image_3d.astype(mx.float64)
        except (ValueError, RuntimeError):
            # GPU backend does not support float64 — fall back to CPU float64
            # IIR for exact parity with the reference path.
            return backend.asarray(
                fast_gaussian_filter(backend.to_numpy(image), sigma)
            )

    coeffs = np.asarray(
        [_yvv_coeffs(float(sigma_ch)) for sigma_ch in sigmas],
        dtype=coeff_np_dtype,
    )
    B = mx.array(coeffs[:, 0], dtype=coeff_mx_dtype)
    B1 = mx.array(coeffs[:, 1], dtype=coeff_mx_dtype)
    B2 = mx.array(coeffs[:, 2], dtype=coeff_mx_dtype)
    B3 = mx.array(coeffs[:, 3], dtype=coeff_mx_dtype)

    if use_f64:
        horizontal = _get_gaussian_iir_horizontal_kernel_f64(mx)
        vertical = _get_gaussian_iir_vertical_kernel_f64(mx)
    else:
        horizontal = _get_gaussian_iir_horizontal_kernel(mx)
        vertical = _get_gaussian_iir_vertical_kernel(mx)

    tmp = horizontal(
        inputs=[image_3d, B, B1, B2, B3],
        template=[("T", image_3d.dtype)],
        grid=(int(image_3d.shape[0]) * channels, 1, 1),
        threadgroup=(64, 1, 1),
        output_shapes=[image_3d.shape],
        output_dtypes=[image_3d.dtype],
    )[0]
    out = vertical(
        inputs=[tmp, B, B1, B2, B3],
        template=[("T", image_3d.dtype)],
        grid=(int(image_3d.shape[1]) * channels, 1, 1),
        threadgroup=(64, 1, 1),
        output_shapes=[image_3d.shape],
        output_dtypes=[image_3d.dtype],
    )[0]
    return out[..., 0] if squeeze else out


def reflect_pad_hw_backend(image: Any, pad: int, backend=None) -> Any:
    """Pad the first two dimensions using NumPy ``mode='reflect'`` semantics."""
    pad = int(pad)
    if pad <= 0:
        return image
    if not _backend_supports_gpu(backend):
        return np.pad(np.asarray(image), ((pad, pad), (pad, pad), (0, 0)), mode="reflect")
    if _backend_supports_cupy(backend):
        return backend.cp.pad(backend.asarray(image), ((pad, pad), (pad, pad), (0, 0)), mode="reflect")
    if not _backend_supports_mlx_custom_kernels(backend):
        return backend.asarray(
            np.pad(backend.to_numpy(image), ((pad, pad), (pad, pad), (0, 0)), mode="reflect")
        )

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


def _gaussian_filter_mlx_mixed_backend(
    image: Any,
    sigmas: np.ndarray,
    backend,
    *,
    truncate: float = 3.0,
    _precision: str = "float32",
) -> Any:
    image_3d, squeeze = _promote_image_to_3d(backend.asarray(image))
    channels = int(image_3d.shape[-1])
    if sigmas.shape[0] != channels:
        raise ValueError(f"sigma length {sigmas.shape[0]} does not match channel count {channels}")

    filtered_channels = []
    for channel, sigma_ch in enumerate(sigmas):
        sigma_value = float(sigma_ch)
        channel_image = image_3d[..., channel]
        if sigma_value <= 0.0:
            filtered = channel_image
        elif sigma_value >= 3.0:
            filtered = gaussian_filter_large_backend(
                channel_image, sigma_value, backend, _precision=_precision,
            )
        else:
            filtered = gaussian_filter_small_backend(
                channel_image,
                sigma_value,
                backend,
                truncate=truncate,
            )
        filtered_channels.append(filtered)

    out = backend.mx.stack(filtered_channels, axis=-1)
    return out[..., 0] if squeeze else out


def gaussian_filter_backend(
    image: Any,
    sigma: Any,
    backend=None,
    *,
    truncate: float = 3.0,
    _precision: str = "float32",
) -> Any:
    """Backend-aware Gaussian blur.

    The GPU path uses the small-sigma FIR kernel for sigma < 3 px and the
    same Young-van Vliet IIR approximation as the CPU path when every channel
    is in the large-sigma regime. Mixed small/large per-channel sigma arrays
    are split per channel on MLX so they stay on-device without changing
    channel semantics.
    """
    if not _backend_supports_gpu(backend):
        return fast_gaussian_filter(image, sigma, truncate=truncate)
    if _backend_supports_cupy(backend):
        return _gaussian_filter_cupy(image, sigma, backend, truncate=truncate)
    if not _backend_supports_mlx_custom_kernels(backend):
        return backend.asarray(fast_gaussian_filter(backend.to_numpy(image), sigma, truncate=truncate))

    channels = int(image.shape[-1]) if len(tuple(image.shape)) == 3 else 1
    sigmas = _normalize_sigma_for_channels(sigma, channels)
    if np.min(sigmas) >= 3.0:
        return gaussian_filter_large_backend(image, sigmas, backend, _precision=_precision)
    if np.max(sigmas) >= 3.0:
        return _gaussian_filter_mlx_mixed_backend(
            image,
            sigmas,
            backend,
            truncate=truncate,
            _precision=_precision,
        )
    return gaussian_filter_small_backend(image, sigmas, backend, truncate=truncate)


def exponential_filter_backend(
    image: Any,
    decay_constant: Any,
    backend=None,
    *,
    n_gaussians: int = 3,
    truncate: float = 3.0,
    _precision: str = "float32",
) -> Any:
    """Backend-aware exponential filter using the existing Gaussian mixture.

    MLX stays on the GPU by default and uses float32 Gaussian components.
    Callers which explicitly need CPU-reference float64 behavior may pass
    ``_precision="float64"``, accepting a possible CPU fallback on MLX.
    """
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
            _precision=_precision,
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
    if _backend_supports_cupy(backend):
        import cupyx.scipy.signal as cupy_signal

        cp = backend.cp
        image_cp = backend.asarray(image)
        kernel_cp = cp.asarray(kernel, dtype=image_cp.dtype)
        output = cp.empty_like(image_cp)
        for channel in range(int(image_cp.shape[2])):
            output[:, :, channel] = cupy_signal.fftconvolve(
                image_cp[:, :, channel],
                kernel_cp[:, :, channel],
                mode="same",
            )
        return output
    if not _backend_supports_mlx_custom_kernels(backend):
        from scipy.signal import fftconvolve

        image_np = backend.to_numpy(image)
        kernel_np = np.asarray(kernel)
        output = np.empty_like(image_np)
        for channel in range(image_np.shape[2]):
            output[:, :, channel] = fftconvolve(
                image_np[:, :, channel],
                kernel_np[:, :, channel],
                mode="same",
            )
        return backend.asarray(output)

    import scipy.fft

    mx = backend.mx
    image_mx = backend.asarray(image)
    kernel_mx = backend.asarray(kernel, dtype=mx.float32)
    image_h, image_w, channels = (int(v) for v in image_mx.shape)
    kernel_h, kernel_w = int(kernel_mx.shape[0]), int(kernel_mx.shape[1])
    fft_h = scipy.fft.next_fast_len(image_h + kernel_h - 1)
    fft_w = scipy.fft.next_fast_len(image_w + kernel_w - 1)
    image_fft = mx.fft.fft2(image_mx, s=(fft_h, fft_w), axes=(0, 1))
    kernel_fft = mx.fft.fft2(kernel_mx, s=(fft_h, fft_w), axes=(0, 1))
    convolved = mx.real(mx.fft.ifft2(image_fft * kernel_fft, axes=(0, 1)))
    start_y = (kernel_h - 1) // 2
    start_x = (kernel_w - 1) // 2
    return convolved[start_y:start_y + image_h, start_x:start_x + image_w, :channels]
