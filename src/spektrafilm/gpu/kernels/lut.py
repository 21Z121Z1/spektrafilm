from __future__ import annotations

from typing import Any

import numpy as np


def _is_mlx_array(value: Any) -> bool:
    return type(value).__module__.startswith("mlx.")


def _as_mlx_array(mx, value: Any, dtype: Any):
    if _is_mlx_array(value):
        if value.dtype == dtype:
            return value
        return value.astype(dtype)
    return mx.array(value, dtype=dtype)


# ---------------------------------------------------------------------------
# 2D LUT Mitchell-Netravali cubic interpolation
# ---------------------------------------------------------------------------

_LUT_CUBIC_2D_KERNEL = None


def _get_lut_cubic_2d_kernel(mx):
    global _LUT_CUBIC_2D_KERNEL
    if _LUT_CUBIC_2D_KERNEL is not None:
        return _LUT_CUBIC_2D_KERNEL

    source = """
        uint elem = thread_position_in_grid.x;
        uint size = lut_shape[0];
        uint channels = lut_shape[2];
        uint total = image_shape[0] * image_shape[1] * channels;
        if (elem >= total) {
            return;
        }

        uint c = elem % channels;
        uint pixel = elem / channels;
        if (size == 1) {
            out[elem] = lut[c];
            return;
        }

        float upper = float(size - 1);
        float x = float(image[pixel * 2]) * upper;
        float y = float(image[pixel * 2 + 1]) * upper;

        if (x <= 0.0f) {
            x = 0.0f;
        } else if (x >= upper) {
            x = upper;
        }
        if (y <= 0.0f) {
            y = 0.0f;
        } else if (y >= upper) {
            y = upper;
        }

        int x_base;
        float x_frac;
        if (x >= upper) {
            x_base = int(size) - 2;
            x_frac = 1.0f;
        } else {
            x_base = int(floor(x));
            x_frac = x - float(x_base);
        }

        int y_base;
        float y_frac;
        if (y >= upper) {
            y_base = int(size) - 2;
            y_frac = 1.0f;
        } else {
            y_base = int(floor(y));
            y_frac = y - float(y_base);
        }

        float wx[4];
        float wy[4];

        float tx0 = fabs(x_frac + 1.0f);
        if (tx0 < 1.0f) {
            wx[0] = (1.0f / 6.0f) * ((7.0f) * tx0 * tx0 * tx0 + (-12.0f) * tx0 * tx0 + (16.0f / 3.0f));
        } else if (tx0 < 2.0f) {
            wx[0] = (1.0f / 6.0f) * ((-7.0f / 3.0f) * tx0 * tx0 * tx0 + 12.0f * tx0 * tx0 - 20.0f * tx0 + (32.0f / 3.0f));
        } else {
            wx[0] = 0.0f;
        }

        float tx1 = fabs(x_frac);
        if (tx1 < 1.0f) {
            wx[1] = (1.0f / 6.0f) * ((7.0f) * tx1 * tx1 * tx1 + (-12.0f) * tx1 * tx1 + (16.0f / 3.0f));
        } else if (tx1 < 2.0f) {
            wx[1] = (1.0f / 6.0f) * ((-7.0f / 3.0f) * tx1 * tx1 * tx1 + 12.0f * tx1 * tx1 - 20.0f * tx1 + (32.0f / 3.0f));
        } else {
            wx[1] = 0.0f;
        }

        float tx2 = fabs(x_frac - 1.0f);
        if (tx2 < 1.0f) {
            wx[2] = (1.0f / 6.0f) * ((7.0f) * tx2 * tx2 * tx2 + (-12.0f) * tx2 * tx2 + (16.0f / 3.0f));
        } else if (tx2 < 2.0f) {
            wx[2] = (1.0f / 6.0f) * ((-7.0f / 3.0f) * tx2 * tx2 * tx2 + 12.0f * tx2 * tx2 - 20.0f * tx2 + (32.0f / 3.0f));
        } else {
            wx[2] = 0.0f;
        }

        float tx3 = fabs(x_frac - 2.0f);
        if (tx3 < 1.0f) {
            wx[3] = (1.0f / 6.0f) * ((7.0f) * tx3 * tx3 * tx3 + (-12.0f) * tx3 * tx3 + (16.0f / 3.0f));
        } else if (tx3 < 2.0f) {
            wx[3] = (1.0f / 6.0f) * ((-7.0f / 3.0f) * tx3 * tx3 * tx3 + 12.0f * tx3 * tx3 - 20.0f * tx3 + (32.0f / 3.0f));
        } else {
            wx[3] = 0.0f;
        }

        float ty0 = fabs(y_frac + 1.0f);
        if (ty0 < 1.0f) {
            wy[0] = (1.0f / 6.0f) * ((7.0f) * ty0 * ty0 * ty0 + (-12.0f) * ty0 * ty0 + (16.0f / 3.0f));
        } else if (ty0 < 2.0f) {
            wy[0] = (1.0f / 6.0f) * ((-7.0f / 3.0f) * ty0 * ty0 * ty0 + 12.0f * ty0 * ty0 - 20.0f * ty0 + (32.0f / 3.0f));
        } else {
            wy[0] = 0.0f;
        }

        float ty1 = fabs(y_frac);
        if (ty1 < 1.0f) {
            wy[1] = (1.0f / 6.0f) * ((7.0f) * ty1 * ty1 * ty1 + (-12.0f) * ty1 * ty1 + (16.0f / 3.0f));
        } else if (ty1 < 2.0f) {
            wy[1] = (1.0f / 6.0f) * ((-7.0f / 3.0f) * ty1 * ty1 * ty1 + 12.0f * ty1 * ty1 - 20.0f * ty1 + (32.0f / 3.0f));
        } else {
            wy[1] = 0.0f;
        }

        float ty2 = fabs(y_frac - 1.0f);
        if (ty2 < 1.0f) {
            wy[2] = (1.0f / 6.0f) * ((7.0f) * ty2 * ty2 * ty2 + (-12.0f) * ty2 * ty2 + (16.0f / 3.0f));
        } else if (ty2 < 2.0f) {
            wy[2] = (1.0f / 6.0f) * ((-7.0f / 3.0f) * ty2 * ty2 * ty2 + 12.0f * ty2 * ty2 - 20.0f * ty2 + (32.0f / 3.0f));
        } else {
            wy[2] = 0.0f;
        }

        float ty3 = fabs(y_frac - 2.0f);
        if (ty3 < 1.0f) {
            wy[3] = (1.0f / 6.0f) * ((7.0f) * ty3 * ty3 * ty3 + (-12.0f) * ty3 * ty3 + (16.0f / 3.0f));
        } else if (ty3 < 2.0f) {
            wy[3] = (1.0f / 6.0f) * ((-7.0f / 3.0f) * ty3 * ty3 * ty3 + 12.0f * ty3 * ty3 - 20.0f * ty3 + (32.0f / 3.0f));
        } else {
            wy[3] = 0.0f;
        }

        float acc = 0.0f;
        float weight_sum = 0.0f;
        for (int i = 0; i < 4; ++i) {
            int xi = x_base - 1 + i;
            if (xi < 0) {
                xi = -xi;
            } else if (xi >= int(size)) {
                xi = 2 * (int(size) - 1) - xi;
            }
            for (int j = 0; j < 4; ++j) {
                int yj = y_base - 1 + j;
                if (yj < 0) {
                    yj = -yj;
                } else if (yj >= int(size)) {
                    yj = 2 * (int(size) - 1) - yj;
                }
                float weight = wx[i] * wy[j];
                weight_sum += weight;
                uint lut_index = (uint(xi) * size + uint(yj)) * channels + c;
                acc += weight * float(lut[lut_index]);
            }
        }
        if (weight_sum != 0.0f) {
            acc /= weight_sum;
        }
        out[elem] = acc;
    """
    _LUT_CUBIC_2D_KERNEL = mx.fast.metal_kernel(
        name="spektrafilm_lut_cubic_2d",
        input_names=["lut", "image"],
        output_names=["out"],
        source=source,
    )
    return _LUT_CUBIC_2D_KERNEL


def apply_lut_cubic_2d_mlx(lut: Any, image: Any, *, mx=None, prepared_lut: Any = None):
    """Apply a normalized 2D LUT with Mitchell-Netravali cubic interpolation.

    When *prepared_lut* is provided it is used directly as the LUT array,
    avoiding a redundant numpy-to-MLX conversion on every call.
    """
    if mx is None:
        import mlx.core as mx

    lut = _as_mlx_array(mx, prepared_lut if prepared_lut is not None else lut, mx.float32)
    image = _as_mlx_array(mx, image, mx.float32)
    size = int(lut.shape[0])
    if lut.ndim != 3:
        raise ValueError("2D LUT must have shape LxLxC")
    if size == 0 or lut.shape[1] != size:
        raise ValueError("2D LUT must have equal non-empty dimensions")
    if image.ndim != 3 or image.shape[-1] != 2:
        raise ValueError("2D LUT coordinates must have shape HxWx2")

    channels = int(lut.shape[2])
    kernel = _get_lut_cubic_2d_kernel(mx)
    outputs = kernel(
        inputs=[lut, image],
        grid=(int(np.prod(image.shape[:-1]) * channels), 1, 1),
        threadgroup=(256, 1, 1),
        output_shapes=[image.shape[:-1] + (channels,)],
        output_dtypes=[mx.float32],
    )
    return outputs[0]


def apply_lut_cubic_2d_numpy(lut: np.ndarray, image: np.ndarray) -> np.ndarray:
    """NumPy/Numba reference for the MLX Mitchell 2D LUT kernel."""
    from spektrafilm.utils.fast_interp_lut import apply_lut_cubic_2d

    return apply_lut_cubic_2d(
        np.ascontiguousarray(lut, dtype=np.float64),
        np.ascontiguousarray(image, dtype=np.float64),
    )


def _mitchell_weight_cupy(t: Any, cp):
    t = cp.abs(t)
    inner = (1.0 / 6.0) * (7.0 * t * t * t - 12.0 * t * t + (16.0 / 3.0))
    outer = (1.0 / 6.0) * ((-7.0 / 3.0) * t * t * t + 12.0 * t * t - 20.0 * t + (32.0 / 3.0))
    return cp.where(t < 1.0, inner, cp.where(t < 2.0, outer, 0.0))


def _reflect_lut_index_cupy(index: Any, size: int, cp):
    return cp.where(index < 0, -index, cp.where(index >= size, 2 * (size - 1) - index, index))


def apply_lut_cubic_2d_cupy(lut: Any, image: Any, *, cp=None):
    """Apply a normalized 2D LUT with Mitchell-Netravali cubic interpolation using CuPy."""
    if cp is None:
        import cupy as cp

    lut = cp.asarray(lut, dtype=cp.float32)
    image = cp.asarray(image, dtype=cp.float32)
    size = int(lut.shape[0])
    if lut.ndim != 3:
        raise ValueError("2D LUT must have shape LxLxC")
    if size == 0 or int(lut.shape[1]) != size:
        raise ValueError("2D LUT must have equal non-empty dimensions")
    if image.ndim != 3 or int(image.shape[-1]) != 2:
        raise ValueError("2D LUT coordinates must have shape HxWx2")

    channels = int(lut.shape[2])
    if size == 1:
        return cp.broadcast_to(lut[0, 0], image.shape[:-1] + (channels,))

    upper = float(size - 1)
    coord = cp.clip(image, 0.0, 1.0) * upper
    x = coord[..., 0]
    y = coord[..., 1]

    x_floor = cp.floor(x)
    y_floor = cp.floor(y)
    x_base = cp.where(x >= upper, size - 2, x_floor).astype(cp.int32)
    y_base = cp.where(y >= upper, size - 2, y_floor).astype(cp.int32)
    x_frac = cp.where(x >= upper, 1.0, x - x_floor)
    y_frac = cp.where(y >= upper, 1.0, y - y_floor)

    wx = [_mitchell_weight_cupy(x_frac + 1.0 - i, cp) for i in range(4)]
    wy = [_mitchell_weight_cupy(y_frac + 1.0 - j, cp) for j in range(4)]

    output_shape = image.shape[:-1] + (channels,)
    acc = cp.zeros(output_shape, dtype=cp.float32)
    weight_sum = cp.zeros(image.shape[:-1] + (1,), dtype=cp.float32)
    for i in range(4):
        xi = _reflect_lut_index_cupy(x_base - 1 + i, size, cp).astype(cp.int32)
        for j in range(4):
            yj = _reflect_lut_index_cupy(y_base - 1 + j, size, cp).astype(cp.int32)
            weight = (wx[i] * wy[j])[..., None]
            acc = acc + weight * lut[xi, yj]
            weight_sum = weight_sum + weight

    return cp.where(weight_sum != 0.0, acc / weight_sum, acc)


def apply_lut_cubic_2d_backend(lut: Any, image: Any, backend, *, prepared_lut: Any = None):
    """Dispatch 2D cubic LUT sampling to the selected GPU backend.

    When *prepared_lut* is provided and the backend supports GPU, the
    pre-converted backend array is used directly, avoiding a redundant
    numpy-to-backend transfer of the LUT on every call.
    """
    if backend is not None and getattr(backend, "supports_gpu", False):
        if hasattr(backend, "mx"):
            return apply_lut_cubic_2d_mlx(lut, image, mx=backend.mx, prepared_lut=prepared_lut)
        if hasattr(backend, "cp"):
            return apply_lut_cubic_2d_cupy(lut, image, cp=backend.cp)
        return backend.asarray(apply_lut_cubic_2d_numpy(lut, backend.to_numpy(image)))
    return apply_lut_cubic_2d_numpy(lut, image)


# ---------------------------------------------------------------------------
# 3D LUT trilinear interpolation
# ---------------------------------------------------------------------------

_LUT_TRILINEAR_3D_KERNEL = None


def _get_lut_trilinear_3d_kernel(mx):
    global _LUT_TRILINEAR_3D_KERNEL
    if _LUT_TRILINEAR_3D_KERNEL is not None:
        return _LUT_TRILINEAR_3D_KERNEL

    source = """
        uint elem = thread_position_in_grid.x;
        uint H = image_shape[0];
        uint W = image_shape[1];
        uint total = H * W * 3;
        if (elem >= total) {
            return;
        }

        uint c = elem % 3;
        uint pixel = elem / 3;
        uint size = lut_shape[0];
        float upper = float(size - 1);

        float r = float(image[pixel * 3 + 0]);
        float g = float(image[pixel * 3 + 1]);
        float b = float(image[pixel * 3 + 2]);

        if (r <= 0.0f) {
            r = 0.0f;
        } else if (r >= 1.0f) {
            r = 1.0f;
        }
        if (g <= 0.0f) {
            g = 0.0f;
        } else if (g >= 1.0f) {
            g = 1.0f;
        }
        if (b <= 0.0f) {
            b = 0.0f;
        } else if (b >= 1.0f) {
            b = 1.0f;
        }

        float rc = r * upper;
        float gc = g * upper;
        float bc = b * upper;

        uint r0 = uint(floor(rc));
        uint g0 = uint(floor(gc));
        uint b0 = uint(floor(bc));
        uint max_index = size - 1;
        uint r1 = min(r0 + 1, max_index);
        uint g1 = min(g0 + 1, max_index);
        uint b1 = min(b0 + 1, max_index);

        float fr = rc - float(r0);
        float fg = gc - float(g0);
        float fb = bc - float(b0);

        uint stride_r = size * size * 3;
        uint stride_g = size * 3;
        uint stride_b = 3;
        uint base000 = r0 * stride_r + g0 * stride_g + b0 * stride_b + c;
        uint base100 = r1 * stride_r + g0 * stride_g + b0 * stride_b + c;
        uint base010 = r0 * stride_r + g1 * stride_g + b0 * stride_b + c;
        uint base110 = r1 * stride_r + g1 * stride_g + b0 * stride_b + c;
        uint base001 = r0 * stride_r + g0 * stride_g + b1 * stride_b + c;
        uint base101 = r1 * stride_r + g0 * stride_g + b1 * stride_b + c;
        uint base011 = r0 * stride_r + g1 * stride_g + b1 * stride_b + c;
        uint base111 = r1 * stride_r + g1 * stride_g + b1 * stride_b + c;

        float c000 = float(lut[base000]);
        float c100 = float(lut[base100]);
        float c010 = float(lut[base010]);
        float c110 = float(lut[base110]);
        float c001 = float(lut[base001]);
        float c101 = float(lut[base101]);
        float c011 = float(lut[base011]);
        float c111 = float(lut[base111]);

        float c00 = c000 + fr * (c100 - c000);
        float c10 = c010 + fr * (c110 - c010);
        float c01 = c001 + fr * (c101 - c001);
        float c11 = c011 + fr * (c111 - c011);
        float c0 = c00 + fg * (c10 - c00);
        float c1 = c01 + fg * (c11 - c01);
        out[elem] = c0 + fb * (c1 - c0);
    """
    _LUT_TRILINEAR_3D_KERNEL = mx.fast.metal_kernel(
        name="spektrafilm_lut_trilinear_3d",
        input_names=["lut", "image"],
        output_names=["out"],
        source=source,
    )
    return _LUT_TRILINEAR_3D_KERNEL


def _validate_lut_trilinear_3d_inputs(lut: Any, image: Any) -> int:
    size = int(lut.shape[0])
    if lut.ndim != 4 or lut.shape[-1] != 3:
        raise ValueError("3D LUT must have shape LxLxLx3")
    if size == 0 or lut.shape[1] != size or lut.shape[2] != size:
        raise ValueError("3D LUT must have equal non-empty dimensions")
    if image.ndim != 3 or image.shape[-1] != 3:
        raise ValueError("3D LUT coordinates must have shape HxWx3")
    return size


def apply_lut_trilinear_3d_mlx_ops(lut: Any, image: Any, *, mx=None):
    """Apply a normalized 3D LUT with trilinear interpolation using MLX ops.

    This is a fast pilot kernel, not the CPU PCHIP-quality path. Callers must
    label outputs that use it as fast/trilinear rather than exact PCHIP parity.
    """
    if mx is None:
        import mlx.core as mx

    lut = _as_mlx_array(mx, lut, mx.float32)
    image = _as_mlx_array(mx, image, mx.float32)
    size = _validate_lut_trilinear_3d_inputs(lut, image)
    if size == 1:
        return mx.broadcast_to(lut[0, 0, 0], image.shape[:-1] + (3,))

    # Clip to [0, 1] — this is the normalised density coordinate space,
    # NOT the output RGB space.  HDR scene-linear values are produced
    # downstream by XYZ_to_RGB and preserved per ColorEncoding policy.
    coord = mx.clip(image, 0.0, 1.0) * float(size - 1)
    idx0 = mx.floor(coord).astype(mx.int32)
    idx1 = mx.minimum(idx0 + 1, size - 1)
    frac = coord - idx0.astype(mx.float32)

    r0 = idx0[..., 0]
    g0 = idx0[..., 1]
    b0 = idx0[..., 2]
    r1 = idx1[..., 0]
    g1 = idx1[..., 1]
    b1 = idx1[..., 2]

    fr = frac[..., 0:1]
    fg = frac[..., 1:2]
    fb = frac[..., 2:3]

    c000 = lut[r0, g0, b0]
    c100 = lut[r1, g0, b0]
    c010 = lut[r0, g1, b0]
    c110 = lut[r1, g1, b0]
    c001 = lut[r0, g0, b1]
    c101 = lut[r1, g0, b1]
    c011 = lut[r0, g1, b1]
    c111 = lut[r1, g1, b1]

    c00 = c000 + fr * (c100 - c000)
    c10 = c010 + fr * (c110 - c010)
    c01 = c001 + fr * (c101 - c001)
    c11 = c011 + fr * (c111 - c011)
    c0 = c00 + fg * (c10 - c00)
    c1 = c01 + fg * (c11 - c01)
    return c0 + fb * (c1 - c0)


def apply_lut_trilinear_3d_mlx(lut: Any, image: Any, *, mx=None):
    """Apply a normalized 3D LUT with the fused MLX/Metal trilinear kernel.

    ``apply_lut_trilinear_3d_mlx_ops`` remains available as the legacy MLX
    array-ops baseline for benchmark comparisons.
    """
    if mx is None:
        import mlx.core as mx

    lut = _as_mlx_array(mx, lut, mx.float32)
    image = _as_mlx_array(mx, image, mx.float32)
    _validate_lut_trilinear_3d_inputs(lut, image)

    kernel = _get_lut_trilinear_3d_kernel(mx)
    outputs = kernel(
        inputs=[lut, image],
        grid=(int(np.prod(image.shape[:-1]) * 3), 1, 1),
        threadgroup=(256, 1, 1),
        output_shapes=[image.shape],
        output_dtypes=[mx.float32],
    )
    return outputs[0]


def apply_lut_trilinear_3d_numpy(lut: np.ndarray, image: np.ndarray) -> np.ndarray:
    """NumPy reference for the MLX trilinear pilot kernel."""
    lut = np.asarray(lut, dtype=np.float64)
    image = np.asarray(image, dtype=np.float64)
    size = _validate_lut_trilinear_3d_inputs(lut, image)
    if size == 1:
        return np.broadcast_to(lut[0, 0, 0], image.shape[:-1] + (3,)).copy()

    # Clip to [0, 1] — this is the normalised density coordinate space,
    # NOT the output RGB space.  HDR scene-linear values are produced
    # downstream by XYZ_to_RGB and preserved per ColorEncoding policy.
    coord = np.clip(image, 0.0, 1.0) * float(size - 1)
    idx0 = np.floor(coord).astype(np.int64)
    idx1 = np.minimum(idx0 + 1, size - 1)
    frac = coord - idx0

    r0, g0, b0 = idx0[..., 0], idx0[..., 1], idx0[..., 2]
    r1, g1, b1 = idx1[..., 0], idx1[..., 1], idx1[..., 2]
    fr = frac[..., 0:1]
    fg = frac[..., 1:2]
    fb = frac[..., 2:3]

    c000 = lut[r0, g0, b0]
    c100 = lut[r1, g0, b0]
    c010 = lut[r0, g1, b0]
    c110 = lut[r1, g1, b0]
    c001 = lut[r0, g0, b1]
    c101 = lut[r1, g0, b1]
    c011 = lut[r0, g1, b1]
    c111 = lut[r1, g1, b1]

    c00 = c000 + fr * (c100 - c000)
    c10 = c010 + fr * (c110 - c010)
    c01 = c001 + fr * (c101 - c001)
    c11 = c011 + fr * (c111 - c011)
    c0 = c00 + fg * (c10 - c00)
    c1 = c01 + fg * (c11 - c01)
    return c0 + fb * (c1 - c0)


def apply_lut_trilinear_3d_cupy(lut: Any, image: Any, *, cp=None):
    """Apply a normalized 3D LUT with trilinear interpolation using CuPy ops."""
    if cp is None:
        import cupy as cp

    lut = cp.asarray(lut, dtype=cp.float32)
    image = cp.asarray(image, dtype=cp.float32)
    size = int(lut.shape[0])
    if lut.ndim != 4 or int(lut.shape[-1]) != 3:
        raise ValueError("3D LUT must have shape LxLxLx3")
    if size == 0 or int(lut.shape[1]) != size or int(lut.shape[2]) != size:
        raise ValueError("3D LUT must have equal non-empty dimensions")
    if size == 1:
        return cp.broadcast_to(lut[0, 0, 0], image.shape[:-1] + (3,))

    coord = cp.clip(image, 0.0, 1.0) * float(size - 1)
    idx0 = cp.floor(coord).astype(cp.int32)
    idx1 = cp.minimum(idx0 + 1, size - 1)
    frac = coord - idx0.astype(cp.float32)

    r0 = idx0[..., 0]
    g0 = idx0[..., 1]
    b0 = idx0[..., 2]
    r1 = idx1[..., 0]
    g1 = idx1[..., 1]
    b1 = idx1[..., 2]

    fr = frac[..., 0:1]
    fg = frac[..., 1:2]
    fb = frac[..., 2:3]

    c000 = lut[r0, g0, b0]
    c100 = lut[r1, g0, b0]
    c010 = lut[r0, g1, b0]
    c110 = lut[r1, g1, b0]
    c001 = lut[r0, g0, b1]
    c101 = lut[r1, g0, b1]
    c011 = lut[r0, g1, b1]
    c111 = lut[r1, g1, b1]

    c00 = c000 + fr * (c100 - c000)
    c10 = c010 + fr * (c110 - c010)
    c01 = c001 + fr * (c101 - c001)
    c11 = c011 + fr * (c111 - c011)
    c0 = c00 + fg * (c10 - c00)
    c1 = c01 + fg * (c11 - c01)
    return c0 + fb * (c1 - c0)


def apply_lut_trilinear_3d_backend(lut: Any, image: Any, backend, *, prepared_lut: Any = None):
    """Dispatch 3D trilinear LUT sampling to the selected GPU backend.

    When *prepared_lut* is provided and the backend supports GPU, the
    pre-converted backend array is used directly, avoiding a redundant
    numpy-to-backend transfer of the LUT on every call.
    """
    if backend is not None and getattr(backend, "supports_gpu", False):
        halide_lut = getattr(backend, "apply_lut_trilinear_3d", None)
        if callable(halide_lut):
            return halide_lut(lut, image)
        if hasattr(backend, "mx"):
            mx = backend.mx
            image_mx = _as_mlx_array(mx, image, mx.float32)
            lut_mx = _as_mlx_array(mx, prepared_lut if prepared_lut is not None else lut, mx.float32)
            return apply_lut_trilinear_3d_mlx(lut_mx, image_mx, mx=mx)
        if hasattr(backend, "cp"):
            return apply_lut_trilinear_3d_cupy(
                prepared_lut if prepared_lut is not None else lut,
                image,
                cp=backend.cp,
            )
        return backend.asarray(apply_lut_trilinear_3d_numpy(lut, backend.to_numpy(image)))
    return apply_lut_trilinear_3d_numpy(lut, image)


# ---------------------------------------------------------------------------
# 2D LUT bilinear interpolation
# ---------------------------------------------------------------------------

def apply_lut_bilinear_2d_mlx(lut: Any, image: Any, *, mx=None):
    """Apply a 2D LUT with bilinear interpolation using MLX ops.

    ``lut`` has shape ``LxLxC`` where C is the number of output channels.
    ``image`` has shape ``HxWx2`` with normalised [0,1] coordinates.

    This is a fast pilot kernel corresponding to the CPU cubic
    ``apply_lut_cubic_2d``. Callers must be aware of the quality difference.
    """
    if mx is None:
        import mlx.core as mx

    lut = _as_mlx_array(mx, lut, mx.float32)
    image = _as_mlx_array(mx, image, mx.float32)
    size = int(lut.shape[0])
    channels = int(lut.shape[2])
    if lut.ndim != 3:
        raise ValueError("2D LUT must have shape LxLxC")
    if size == 0 or lut.shape[1] != size:
        raise ValueError("2D LUT must have equal non-empty dimensions")
    if size == 1:
        return mx.broadcast_to(lut[0, 0], image.shape[:-1] + (channels,))

    coord = mx.clip(image, 0.0, 1.0) * float(size - 1)
    idx0 = mx.floor(coord).astype(mx.int32)
    idx1 = mx.minimum(idx0 + 1, size - 1)
    frac = coord - idx0.astype(mx.float32)

    x0 = idx0[..., 0]
    y0 = idx0[..., 1]
    x1 = idx1[..., 0]
    y1 = idx1[..., 1]

    fx = frac[..., 0:1]
    fy = frac[..., 1:2]

    c00 = lut[x0, y0]
    c10 = lut[x1, y0]
    c01 = lut[x0, y1]
    c11 = lut[x1, y1]

    c0 = c00 + fx * (c10 - c00)
    c1 = c01 + fx * (c11 - c01)
    return c0 + fy * (c1 - c0)


def apply_lut_bilinear_2d_numpy(lut: np.ndarray, image: np.ndarray) -> np.ndarray:
    """NumPy reference for the MLX bilinear 2D LUT kernel."""
    lut = np.asarray(lut, dtype=np.float64)
    image = np.asarray(image, dtype=np.float64)
    size = lut.shape[0]
    channels = lut.shape[2]
    if lut.ndim != 3:
        raise ValueError("2D LUT must have shape LxLxC")
    if size == 0 or lut.shape[1] != size:
        raise ValueError("2D LUT must have equal non-empty dimensions")
    if size == 1:
        return np.broadcast_to(lut[0, 0], image.shape[:-1] + (channels,)).copy()

    coord = np.clip(image, 0.0, 1.0) * float(size - 1)
    idx0 = np.floor(coord).astype(np.int64)
    idx1 = np.minimum(idx0 + 1, size - 1)
    frac = coord - idx0

    x0, y0 = idx0[..., 0], idx0[..., 1]
    x1, y1 = idx1[..., 0], idx1[..., 1]
    fx = frac[..., 0:1]
    fy = frac[..., 1:2]

    c00 = lut[x0, y0]
    c10 = lut[x1, y0]
    c01 = lut[x0, y1]
    c11 = lut[x1, y1]

    c0 = c00 + fx * (c10 - c00)
    c1 = c01 + fx * (c11 - c01)
    return c0 + fy * (c1 - c0)
