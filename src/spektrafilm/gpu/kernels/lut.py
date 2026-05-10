from __future__ import annotations

from typing import Any

import numpy as np


# ---------------------------------------------------------------------------
# 3D LUT trilinear interpolation
# ---------------------------------------------------------------------------

def apply_lut_trilinear_3d_mlx(lut: Any, image: Any, *, mx=None):
    """Apply a normalized 3D LUT with trilinear interpolation using MLX ops.

    This is a fast pilot kernel, not the CPU PCHIP-quality path. Callers must
    label outputs that use it as fast/trilinear rather than exact PCHIP parity.
    """
    if mx is None:
        import mlx.core as mx

    lut = mx.array(lut, dtype=mx.float32)
    image = mx.array(image, dtype=mx.float32)
    size = int(lut.shape[0])
    if lut.ndim != 4 or lut.shape[-1] != 3:
        raise ValueError("3D LUT must have shape LxLxLx3")
    if size == 0 or lut.shape[1] != size or lut.shape[2] != size:
        raise ValueError("3D LUT must have equal non-empty dimensions")
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


def apply_lut_trilinear_3d_numpy(lut: np.ndarray, image: np.ndarray) -> np.ndarray:
    """NumPy reference for the MLX trilinear pilot kernel."""
    lut = np.asarray(lut, dtype=np.float64)
    image = np.asarray(image, dtype=np.float64)
    size = lut.shape[0]
    if lut.ndim != 4 or lut.shape[-1] != 3:
        raise ValueError("3D LUT must have shape LxLxLx3")
    if size == 0 or lut.shape[1] != size or lut.shape[2] != size:
        raise ValueError("3D LUT must have equal non-empty dimensions")
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

    lut = mx.array(lut, dtype=mx.float32)
    image = mx.array(image, dtype=mx.float32)
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
