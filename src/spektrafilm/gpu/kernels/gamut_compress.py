"""Backend-portable output gamut compression.

Accelerates the per-pixel compression loop from
``spektrafilm.utils.gamut_compression`` on GPU backends (MLX / CuPy).
The expensive ``C_max(L, h)`` boundary table is still computed on CPU
(it runs once per output-color-space change); only the per-pixel
RGB → OkLab → compress → OkLab → RGB chain is ported.

CPU fallback delegates to the existing NumPy implementation so callers
can use ``compress_rgb_backend`` unconditionally.
"""
from __future__ import annotations

from typing import Any

import numpy as np


# ---------------------------------------------------------------------------
# OkLab matrices (exact values from colour-science / Björn Ottosson)
# ---------------------------------------------------------------------------

# XYZ → LMS (M1)
_OKLAB_M1 = np.array([
    [0.8189330101, 0.3618667424, -0.1288597137],
    [0.0329845436, 0.9293118715,  0.0361456387],
    [0.0482003018, 0.2643662691,  0.6338517070],
], dtype=np.float64)

# LMS^(1/3) → Lab (M2)
_OKLAB_M2 = np.array([
    [0.2104542553,  0.7936177850, -0.0040720468],
    [1.9779984951, -2.4285922050,  0.4505937099],
    [0.0259040371,  0.7827717662, -0.8086757660],
], dtype=np.float64)

# LMS → XYZ (M1 inverse)
_OKLAB_M1_INV = np.array([
    [ 1.2270138511035211,  -0.5577999806518222,  0.2812561489664678],
    [-0.0405801784232806,   1.1122568696168302, -0.0716766786656012],
    [-0.0763812845057069,  -0.4214819784180127,  1.5861632204407947],
], dtype=np.float64)

# Lab → LMS^(1/3) (M2 inverse)
_OKLAB_M2_INV = np.array([
    [1.0,  0.3963377774,  0.2158037573],
    [1.0, -0.1055613458, -0.0638541728],
    [1.0, -0.0894841775, -1.2914855480],
], dtype=np.float64)


# ---------------------------------------------------------------------------
# Backend detection helpers
# ---------------------------------------------------------------------------

def _backend_supports_gpu(backend) -> bool:
    return backend is not None and bool(getattr(backend, "supports_gpu", False))


# ---------------------------------------------------------------------------
# OkLab forward / inverse  (backend-portable)
# ---------------------------------------------------------------------------

def _xyz_to_oklab_backend(xyz, backend):
    """XYZ → OkLab via MLX/CuPy matrix ops.

    ``Lab = M2 @ cbrt(M1 @ XYZ)``  (per-pixel, batched via matmul).
    """
    mx = backend.mx
    M1 = backend.asarray(_OKLAB_M1)
    M2 = backend.asarray(_OKLAB_M2)

    # xyz shape: (..., 3).  matmul with (3, 3).T → (..., 3)
    lms = mx.matmul(xyz, mx.transpose(M1))
    # Signed cube root: preserve sign for negative XYZ edge cases
    lms_abs = mx.abs(lms)
    lms_cbrt = mx.where(
        lms >= 0,
        mx.power(lms_abs + 1e-30, 1.0 / 3.0),
        -mx.power(lms_abs + 1e-30, 1.0 / 3.0),
    )
    lab = mx.matmul(lms_cbrt, mx.transpose(M2))
    return lab


def _oklab_to_xyz_backend(lab, backend):
    """OkLab → XYZ via MLX/CuPy matrix ops.

    ``XYZ = M1_inv @ (M2_inv @ Lab)^3``
    """
    mx = backend.mx
    M1_inv = backend.asarray(_OKLAB_M1_INV)
    M2_inv = backend.asarray(_OKLAB_M2_INV)

    lms_cbrt = mx.matmul(lab, mx.transpose(M2_inv))
    lms = lms_cbrt * lms_cbrt * lms_cbrt   # cube
    xyz = mx.matmul(lms, mx.transpose(M1_inv))
    return xyz


# ---------------------------------------------------------------------------
# RGB ↔ XYZ  (using pre-computed matrices, no colour dependency)
# ---------------------------------------------------------------------------

def _rgb_to_xyz_backend(rgb, matrix_rgb_to_xyz, backend):
    """Linear RGB → XYZ:  ``XYZ = RGB @ M.T``."""
    return backend.mx.matmul(rgb, backend.mx.transpose(matrix_rgb_to_xyz))


def _xyz_to_rgb_backend(xyz, matrix_xyz_to_rgb, backend):
    """XYZ → Linear RGB:  ``RGB = XYZ @ M.T``."""
    return backend.mx.matmul(xyz, backend.mx.transpose(matrix_xyz_to_rgb))


# ---------------------------------------------------------------------------
# Bilinear C_max(L, h) lookup  (backend-portable)
# ---------------------------------------------------------------------------

def _c_max_lookup_backend(L, h, L_grid, h_grid, C_max_table, backend):
    """Bilinear interpolation of C_max(L, h) on the backend.

    Mirrors ``gamut_compression._c_max_lookup`` but with MLX tensors.
    The C_max_table, L_grid, h_grid are pre-computed numpy arrays from
    the CPU-side boundary builder and are transferred to backend once.
    """
    mx = backend.mx

    # Convert grid metadata to backend arrays (these are tiny, cached upstream)
    L_grid_b = backend.asarray(L_grid)
    h_grid_b = backend.asarray(h_grid)
    C_max_b = backend.asarray(C_max_table)

    n_L = L_grid.shape[0]
    n_h = h_grid.shape[0]

    # Clamp L to grid range
    L_clamped = mx.clip(L, float(L_grid[0]), float(L_grid[-1]))

    # Compute fractional indices for L dimension
    L_range = float(L_grid[-1] - L_grid[0])
    L_idx = (L_clamped - float(L_grid[0])) / L_range * (n_L - 1)
    L_lo = mx.clip(mx.floor(L_idx).astype(mx.int32), 0, n_L - 2)
    L_hi = L_lo + 1
    L_frac = L_idx - L_lo.astype(mx.float32)

    # Compute fractional indices for h dimension (periodic)
    h_step = float(h_grid[1] - h_grid[0])
    h_idx = (h - float(h_grid[0])) / h_step
    h_lo = mx.floor(h_idx).astype(mx.int32) % n_h
    h_hi = (h_lo + 1) % n_h
    h_frac = h_idx - mx.floor(h_idx)

    # Flatten indices for gather
    orig_shape = L.shape
    L_lo_f = mx.reshape(L_lo, (-1,))
    L_hi_f = mx.reshape(L_hi, (-1,))
    h_lo_f = mx.reshape(h_lo, (-1,))
    h_hi_f = mx.reshape(h_hi, (-1,))

    # Gather the four corner values
    # C_max_table shape is (n_L, n_h)
    v00 = C_max_b[L_lo_f, h_lo_f]
    v01 = C_max_b[L_lo_f, h_hi_f]
    v10 = C_max_b[L_hi_f, h_lo_f]
    v11 = C_max_b[L_hi_f, h_hi_f]

    v00 = mx.reshape(v00, orig_shape)
    v01 = mx.reshape(v01, orig_shape)
    v10 = mx.reshape(v10, orig_shape)
    v11 = mx.reshape(v11, orig_shape)

    # Bilinear interpolation
    result = (
        v00 * (1 - L_frac) * (1 - h_frac)
        + v01 * (1 - L_frac) * h_frac
        + v10 * L_frac * (1 - h_frac)
        + v11 * L_frac * h_frac
    )
    return result


# ---------------------------------------------------------------------------
# Reinhard knee  (backend-portable)
# ---------------------------------------------------------------------------

def _reinhard_knee_backend(d, *, threshold, limit, power, backend):
    """Reinhard knee on the backend, matching ``gamut_compression.reinhard_knee``."""
    mx = backend.mx
    scale = limit - threshold
    x = (d - threshold) / scale
    # Clamp x to non-negative for the power; identity below threshold
    x_safe = mx.maximum(x, 0.0)
    y = x_safe / mx.power(1.0 + mx.power(x_safe, power), 1.0 / power)
    compressed = threshold + scale * y
    # Identity below threshold
    return mx.where(d > threshold, compressed, d)


def _compress_lightness_backend(L, *, params, L_white, backend):
    """One-sided soft compression on perceptual lightness, backend version."""
    threshold, limit, power = params
    L_norm = L / L_white
    L_norm = _reinhard_knee_backend(
        L_norm, threshold=threshold, limit=limit, power=power, backend=backend,
    )
    return L_norm * L_white


# ---------------------------------------------------------------------------
# Oklrab Lr remap  (backend-portable)
# ---------------------------------------------------------------------------

_OKLRAB_K1 = 0.206
_OKLRAB_K2 = 0.03
_OKLRAB_K3 = (1.0 + _OKLRAB_K1) / (1.0 + _OKLRAB_K2)


def _oklab_L_to_oklrab_Lr_backend(L, backend):
    """Forward Lr from OkLab L (Ottosson 2023), backend version."""
    mx = backend.mx
    k1, k2, k3 = _OKLRAB_K1, _OKLRAB_K2, _OKLRAB_K3
    t = k3 * L - k1
    return 0.5 * (t + mx.sqrt(t * t + 4.0 * k2 * k3 * L))


# ---------------------------------------------------------------------------
# compress_rgb_aces_rgc_backend
# ---------------------------------------------------------------------------

def compress_rgb_aces_rgc_backend(rgb, *, threshold, limit, power, backend):
    """ACES RGC v1.3 on the backend. Pure element-wise arithmetic."""
    mx = backend.mx
    rgb = backend.asarray(rgb)

    ach = mx.max(rgb, axis=-1, keepdims=True)
    safe_ach = mx.where(ach > 1e-12, ach, 1.0)

    d = (ach - rgb) / safe_ach
    d_compressed = _reinhard_knee_backend(
        d, threshold=threshold, limit=limit, power=power, backend=backend,
    )
    rgb_compressed = ach * (1.0 - d_compressed)
    return mx.where(ach > 1e-12, rgb_compressed, rgb)


# ---------------------------------------------------------------------------
# compress_rgb_oklch_chroma_backend
# ---------------------------------------------------------------------------

def compress_rgb_oklch_chroma_backend(
    rgb,
    output_color_space: str,
    *,
    threshold: float,
    limit: float,
    power: float,
    lightness_compression: tuple[float, float, float] | None = None,
    backend,
):
    """OkLch chroma reduction on the backend.

    Mirrors ``gamut_compression.compress_rgb_oklch_chroma`` but keeps all
    per-pixel computation on MLX.  The C_max table is built on CPU (cached)
    and transferred to the backend once.
    """
    mx = backend.mx
    rgb = backend.asarray(rgb)

    # Pre-computed matrices (CPU, cached by caller or here)
    from spektrafilm.gpu.kernels.color import (
        precompute_rgb_to_xyz_matrix,
        precompute_xyz_to_rgb_matrix,
    )
    M_rgb_to_xyz = backend.asarray(precompute_rgb_to_xyz_matrix(output_color_space))
    M_xyz_to_rgb = backend.asarray(precompute_xyz_to_rgb_matrix(output_color_space))

    # RGB → XYZ → OkLab
    xyz = _rgb_to_xyz_backend(rgb, M_rgb_to_xyz, backend)
    lab = _xyz_to_oklab_backend(xyz, backend)
    L = lab[..., 0]
    a = lab[..., 1]
    b = lab[..., 2]

    # Optional lightness compression (OkLab white = L=1.0)
    if lightness_compression is not None:
        L = _compress_lightness_backend(
            L, params=lightness_compression, L_white=1.0, backend=backend,
        )

    # Polar coordinates
    C = mx.sqrt(a * a + b * b)
    h = mx.arctan2(b, a)

    # C_max lookup (table from CPU cache)
    from spektrafilm.utils.gamut_compression import _get_output_c_max_table
    c_max_data = _get_output_c_max_table("oklch", output_color_space)
    C_max = _c_max_lookup_backend(L, h, *c_max_data, backend)
    safe_C_max = mx.maximum(C_max, 1e-9)

    # Reinhard knee on normalized chroma
    d_norm = C / safe_C_max
    d_compressed = _reinhard_knee_backend(
        d_norm, threshold=threshold, limit=limit, power=power, backend=backend,
    )
    C_new = d_compressed * safe_C_max

    # Polar → OkLab → XYZ → RGB
    a_new = C_new * mx.cos(h)
    b_new = C_new * mx.sin(h)
    lab_new = mx.stack([L, a_new, b_new], axis=-1)
    xyz_new = _oklab_to_xyz_backend(lab_new, backend)
    rgb_new = _xyz_to_rgb_backend(xyz_new, M_xyz_to_rgb, backend)
    return rgb_new


# ---------------------------------------------------------------------------
# compress_rgb_oklrab_chroma_backend
# ---------------------------------------------------------------------------

def compress_rgb_oklrab_chroma_backend(
    rgb,
    output_color_space: str,
    *,
    threshold: float,
    limit: float,
    power: float,
    lightness_compression: tuple[float, float, float] | None = None,
    backend,
):
    """Oklrab chroma reduction on the backend.

    Same as oklch but C_max is indexed by rebased lightness Lr.
    """
    mx = backend.mx
    rgb = backend.asarray(rgb)

    from spektrafilm.gpu.kernels.color import (
        precompute_rgb_to_xyz_matrix,
        precompute_xyz_to_rgb_matrix,
    )
    M_rgb_to_xyz = backend.asarray(precompute_rgb_to_xyz_matrix(output_color_space))
    M_xyz_to_rgb = backend.asarray(precompute_xyz_to_rgb_matrix(output_color_space))

    xyz = _rgb_to_xyz_backend(rgb, M_rgb_to_xyz, backend)
    lab = _xyz_to_oklab_backend(xyz, backend)
    L = lab[..., 0]
    a = lab[..., 1]
    b = lab[..., 2]

    if lightness_compression is not None:
        L = _compress_lightness_backend(
            L, params=lightness_compression, L_white=1.0, backend=backend,
        )

    Lr = _oklab_L_to_oklrab_Lr_backend(L, backend)
    C = mx.sqrt(a * a + b * b)
    h = mx.arctan2(b, a)

    from spektrafilm.utils.gamut_compression import _get_output_c_max_table
    c_max_data = _get_output_c_max_table("oklrab", output_color_space)
    C_max = _c_max_lookup_backend(Lr, h, *c_max_data, backend)
    safe_C_max = mx.maximum(C_max, 1e-9)

    d_norm = C / safe_C_max
    d_compressed = _reinhard_knee_backend(
        d_norm, threshold=threshold, limit=limit, power=power, backend=backend,
    )
    C_new = d_compressed * safe_C_max

    a_new = C_new * mx.cos(h)
    b_new = C_new * mx.sin(h)
    lab_new = mx.stack([L, a_new, b_new], axis=-1)
    xyz_new = _oklab_to_xyz_backend(lab_new, backend)
    rgb_new = _xyz_to_rgb_backend(xyz_new, M_xyz_to_rgb, backend)
    return rgb_new


# ---------------------------------------------------------------------------
# Top-level dispatcher
# ---------------------------------------------------------------------------

def compress_rgb_backend(
    rgb: Any,
    spec,
    *,
    output_color_space: str | None = None,
    backend=None,
) -> Any:
    """Backend-aware output gamut compression.

    When *backend* supports GPU, runs the compression entirely on the
    backend (MLX / CuPy).  Otherwise falls back to the CPU implementation
    in ``spektrafilm.utils.gamut_compression.compress_rgb``.

    Parameters
    ----------
    rgb : array
        Linear RGB in the output color space, shape ``(..., 3)``.
    spec : OutputGamutCompressSpec
        Compression configuration.
    output_color_space : str or None
        Required for perceptual algorithms (oklch, oklrab, etc.).
    backend : ArrayBackend or None
        GPU backend.  ``None`` falls back to CPU.
    """
    if not _backend_supports_gpu(backend):
        from spektrafilm.utils.gamut_compression import compress_rgb
        return compress_rgb(rgb, spec, output_color_space=output_color_space)

    if spec.algorithm == "off":
        return backend.asarray(rgb)

    threshold, limit, power = spec.knee

    if spec.algorithm == "aces_rgc":
        return compress_rgb_aces_rgc_backend(
            rgb, threshold=threshold, limit=limit, power=power, backend=backend,
        )

    if spec.algorithm == "oklch":
        if output_color_space is None:
            raise ValueError("output_color_space is required for oklch")
        return compress_rgb_oklch_chroma_backend(
            rgb, output_color_space,
            threshold=threshold, limit=limit, power=power,
            lightness_compression=spec.lightness_compression,
            backend=backend,
        )

    if spec.algorithm == "oklrab":
        if output_color_space is None:
            raise ValueError("output_color_space is required for oklrab")
        return compress_rgb_oklrab_chroma_backend(
            rgb, output_color_space,
            threshold=threshold, limit=limit, power=power,
            lightness_compression=spec.lightness_compression,
            backend=backend,
        )

    # Unsupported algorithms on GPU → fall back to CPU
    from spektrafilm.utils.gamut_compression import compress_rgb
    rgb_np = backend.to_numpy(rgb) if hasattr(backend, "to_numpy") else np.asarray(rgb)
    result = compress_rgb(rgb_np, spec, output_color_space=output_color_space)
    return backend.asarray(result)
