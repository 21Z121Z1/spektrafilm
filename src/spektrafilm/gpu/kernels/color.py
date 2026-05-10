"""Backend-portable per-pixel colour operations.

All public kernel functions accept and return backend arrays (NumPy *or*
MLX).  Pre-computed matrices / constants are ordinary NumPy arrays that
the caller converts once via ``backend.asarray()`` and caches.

CPU-only helpers (matrix extraction) are at the top; per-pixel kernels
follow.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import colour


# ---------------------------------------------------------------------------
# Matrix extraction helpers (CPU-only, run once at init / param-digest time)
# ---------------------------------------------------------------------------

def precompute_rgb_to_xyz_matrix(
    color_space: str,
    *,
    illuminant_xy: np.ndarray | None = None,
    cat: str = "CAT02",
) -> np.ndarray:
    """Return a 3×3 float64 matrix: ``XYZ = linear_RGB @ M.T``.

    When *illuminant_xy* differs from the colour-space whitepoint a
    chromatic-adaptation matrix (Von Kries / *cat*) is folded in, matching
    the behaviour of ``colour.RGB_to_XYZ(illuminant=…, chromatic_adaptation_transform=…)``.
    """
    cs = colour.RGB_COLOURSPACES[color_space]
    M = np.array(cs.matrix_RGB_to_XYZ, dtype=np.float64)

    if illuminant_xy is not None:
        src_wp = np.asarray(cs.whitepoint, dtype=np.float64)
        dst_wp = np.asarray(illuminant_xy, dtype=np.float64)
        if not np.allclose(src_wp, dst_wp, atol=1e-8):
            cat_matrix = colour.adaptation.matrix_chromatic_adaptation_VonKries(
                colour.xy_to_XYZ(src_wp),
                colour.xy_to_XYZ(dst_wp),
                transform=cat,
            )
            M = cat_matrix @ M

    return M


def precompute_xyz_to_rgb_matrix(
    color_space: str,
    *,
    illuminant_xy: np.ndarray | None = None,
    cat: str = "CAT02",
) -> np.ndarray:
    """Return a 3×3 float64 matrix: ``linear_RGB = XYZ @ M.T``."""
    cs = colour.RGB_COLOURSPACES[color_space]
    M = np.array(cs.matrix_XYZ_to_RGB, dtype=np.float64)

    if illuminant_xy is not None:
        src_wp = np.asarray(illuminant_xy, dtype=np.float64)
        dst_wp = np.asarray(cs.whitepoint, dtype=np.float64)
        if not np.allclose(src_wp, dst_wp, atol=1e-8):
            cat_matrix = colour.adaptation.matrix_chromatic_adaptation_VonKries(
                colour.xy_to_XYZ(src_wp),
                colour.xy_to_XYZ(dst_wp),
                transform=cat,
            )
            M = M @ cat_matrix

    return M


def precompute_cctf_decode_matrix(
    color_space: str,
    *,
    illuminant_xy: np.ndarray | None = None,
    cat: str = "CAT02",
) -> np.ndarray:
    """Return the combined ``encoded_RGB → XYZ`` matrix.

    This is ``CAT @ M_rgb_to_xyz``, exactly the same matrix that
    ``colour.RGB_to_XYZ`` uses *after* CCTF decoding.  The caller
    is responsible for applying CCTF decode separately.
    """
    return precompute_rgb_to_xyz_matrix(
        color_space, illuminant_xy=illuminant_xy, cat=cat,
    )


# ---------------------------------------------------------------------------
# Per-pixel colour transforms (backend-portable)
# ---------------------------------------------------------------------------

def rgb_to_xyz(rgb: Any, matrix_3x3: Any, backend) -> Any:
    """``XYZ[…,j] = Σ_i RGB[…,i] * M[j,i]`` — i.e. ``XYZ = RGB @ M.T``."""
    # M is stored as (3, 3). We want …i,ji->…j which is matmul(rgb, M.T).
    M_T = matrix_3x3.T if hasattr(matrix_3x3, 'T') else backend.asarray(np.asarray(matrix_3x3).T)
    return backend.matmul(rgb, M_T)


def xyz_to_rgb(xyz: Any, matrix_3x3: Any, backend) -> Any:
    """``RGB[…,j] = Σ_i XYZ[…,i] * M[j,i]`` — i.e. ``RGB = XYZ @ M.T``."""
    M_T = matrix_3x3.T if hasattr(matrix_3x3, 'T') else backend.asarray(np.asarray(matrix_3x3).T)
    return backend.matmul(xyz, M_T)


# ---------------------------------------------------------------------------
# Highlight boost (replaces Numba ``_boost_curve_kernel``)
# ---------------------------------------------------------------------------

def boost_highlights_backend(
    x: Any,
    boost_ev: float,
    boost_range: float,
    protect_ev: float,
    backend,
    *,
    midgray: float = 0.184,
) -> Any:
    """Backend-portable highlight boost.

    Reproduces the exact same curve as the Numba kernel in
    ``numba_boost_hightlights.py`` using element-wise backend ops.

    For ``x <= raw_x0``: identity.
    For ``x > raw_x0``: ``y = x + boost_scale * (exp(a * dx) - a * dx - 1)``
    where ``dx = (x - raw_x0) / max_raw``.

    The ``fmax(…, 0)`` trick means dx ≡ 0 when x ≤ raw_x0, so b ≡ 0 ⟹
    y = x — exactly matching the piece-wise Numba kernel.
    """
    if boost_ev <= 0:
        return x

    # Scalar reduction — negligible cost, works on any backend.
    x_np = backend.to_numpy(x)
    x_max = float(np.max(x_np))
    if x_max == 0.0:
        return x

    raw_x0 = float(np.clip(midgray * (2.0 ** protect_ev), 0.0, x_max))
    if raw_x0 >= x_max:
        return x

    import math
    a = 28.0 ** (1.0 - boost_range)
    x0_norm = raw_x0 / x_max
    denom = math.exp(a * (1.0 - x0_norm)) - a * (1.0 - x0_norm) - 1.0
    if denom <= 0.0:
        return x

    k = (2.0 ** boost_ev - 1.0) / denom
    boost_scale = k * x_max
    inv_max_raw = 1.0 / x_max

    # dx = max(x - raw_x0, 0) / max_raw
    dx = backend.fmax(x - raw_x0, 0.0) * inv_max_raw
    # b = boost_scale * (exp(a * dx) - a * dx - 1)
    adx = dx * a
    b = boost_scale * (backend.exp(adx) - adx - 1.0)
    return x + b
