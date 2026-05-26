"""Backend-portable per-pixel colour operations.

All public kernel functions accept and return backend arrays (NumPy, MLX, or
CuPy).  Pre-computed matrices / constants are ordinary NumPy arrays that
the caller converts once via ``backend.asarray()`` and caches.

CPU-only helpers (matrix extraction) are at the top; per-pixel kernels
follow.
"""
from __future__ import annotations

from functools import lru_cache
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
# CCTF encoding
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def _precompute_same_space_rgb_to_rgb_matrix(color_space: str) -> np.ndarray:
    """Matrix used by ``colour.RGB_to_RGB(cs, cs)`` before CCTF encoding."""
    return np.asarray(
        colour.matrix_RGB_to_RGB(
            color_space,
            color_space,
            chromatic_adaptation_transform="CAT02",
        ),
        dtype=np.float64,
    )


def _signed_power(x: Any, exponent: float, backend) -> Any:
    """Colour-science ``spow`` equivalent for backend arrays."""
    magnitude = backend.pow(backend.abs(x), exponent)
    return backend.where(x < 0, -magnitude, magnitude)


def _cctf_encoding_srgb_like(rgb: Any, backend) -> Any:
    nonlinear = 1.055 * _signed_power(rgb, 1.0 / 2.4, backend) - 0.055
    return backend.where(rgb <= 0.0031308, rgb * 12.92, nonlinear)


def _cctf_encoding_romm_rgb(rgb: Any, backend) -> Any:
    threshold = 16.0 ** (1.8 / (1.0 - 1.8))
    nonlinear = _signed_power(rgb, 1.0 / 1.8, backend)
    return backend.where(rgb < threshold, rgb * 16.0, nonlinear)


def _cctf_encoding_bt2020(rgb: Any, backend) -> Any:
    alpha = 1.099
    beta = 0.018
    nonlinear = alpha * _signed_power(rgb, 0.45, backend) - (alpha - 1.0)
    return backend.where(rgb < beta, rgb * 4.5, nonlinear)


def _cctf_encoding_adobe_rgb_1998(rgb: Any, backend) -> Any:
    # colour-science uses gamma_function(..., negative_number_handling="Indeterminate")
    # for Adobe RGB (1998), so negative fractional powers intentionally
    # produce NaN, matching the CPU reference.
    return backend.pow(rgb, 0.4547069271758437)


def _cctf_decoding_srgb_like(rgb: Any, backend) -> Any:
    linear = rgb / 12.92
    nonlinear = _signed_power((rgb + 0.055) / 1.055, 2.4, backend)
    return backend.where(rgb <= 0.04045, linear, nonlinear)


def _cctf_decoding_romm_rgb(rgb: Any, backend) -> Any:
    linear_threshold = 16.0 ** (1.8 / (1.0 - 1.8))
    encoded_threshold = linear_threshold * 16.0
    nonlinear = _signed_power(rgb, 1.8, backend)
    return backend.where(rgb < encoded_threshold, rgb / 16.0, nonlinear)


def _cctf_decoding_bt2020(rgb: Any, backend) -> Any:
    alpha = 1.099
    nonlinear = _signed_power((rgb + (alpha - 1.0)) / alpha, 1.0 / 0.45, backend)
    return backend.where(rgb <= 0.081, rgb / 4.5, nonlinear)


def _cctf_decoding_adobe_rgb_1998(rgb: Any, backend) -> Any:
    return backend.pow(rgb, 1.0 / 0.4547069271758437)


def _cctf_decoding_dci_p3(rgb: Any, backend) -> Any:
    return backend.pow(rgb, 2.6)


def cctf_decoding_transfer_backend(rgb: Any, color_space: str, backend) -> Any:
    """Apply only the colour-space transfer decoding without matrix adaptation."""
    if backend is None or not getattr(backend, "supports_gpu", False):
        return colour.RGB_COLOURSPACES[color_space].cctf_decoding(rgb)

    if color_space in {"sRGB", "Display P3"}:
        return _cctf_decoding_srgb_like(rgb, backend)
    if color_space == "ProPhoto RGB":
        return _cctf_decoding_romm_rgb(rgb, backend)
    if color_space == "ITU-R BT.2020":
        return _cctf_decoding_bt2020(rgb, backend)
    if color_space == "Adobe RGB (1998)":
        return _cctf_decoding_adobe_rgb_1998(rgb, backend)
    if color_space == "DCI-P3":
        return _cctf_decoding_dci_p3(rgb, backend)
    if color_space in {"ACES2065-1", "ACEScg"}:
        return rgb

    raise NotImplementedError(
        f"Backend CCTF decoding is not implemented for color space {color_space!r}"
    )


def cctf_decoding_backend(rgb: Any, color_space: str, backend) -> Any:
    """Apply same-colour-space CCTF decoding without leaving the backend."""
    if backend is None or not getattr(backend, "supports_gpu", False):
        return colour.RGB_to_RGB(
            rgb,
            color_space,
            color_space,
            apply_cctf_decoding=True,
            apply_cctf_encoding=False,
        )

    decoded = cctf_decoding_transfer_backend(rgb, color_space, backend)
    matrix = backend.asarray(_precompute_same_space_rgb_to_rgb_matrix(color_space))
    return rgb_to_xyz(decoded, matrix, backend)


def cctf_encoding_backend(rgb: Any, color_space: str, backend) -> Any:
    """Apply the output colour-space CCTF without leaving the array backend.

    The supported spaces cover the runtime/GUI choices currently exposed by
    SpektraFilm.  Their formulas mirror the corresponding colour-science
    transfer functions used by ``colour.RGB_to_RGB(..., apply_cctf_encoding=True)``.
    """
    if backend is None or not getattr(backend, "supports_gpu", False):
        return colour.RGB_to_RGB(
            rgb,
            color_space,
            color_space,
            apply_cctf_decoding=False,
            apply_cctf_encoding=True,
        )

    matrix = backend.asarray(_precompute_same_space_rgb_to_rgb_matrix(color_space))
    rgb = rgb_to_xyz(rgb, matrix, backend)

    if color_space in {"sRGB", "Display P3"}:
        return _cctf_encoding_srgb_like(rgb, backend)
    if color_space == "ProPhoto RGB":
        return _cctf_encoding_romm_rgb(rgb, backend)
    if color_space == "ITU-R BT.2020":
        return _cctf_encoding_bt2020(rgb, backend)
    if color_space == "Adobe RGB (1998)":
        return _cctf_encoding_adobe_rgb_1998(rgb, backend)
    if color_space in {"ACES2065-1", "ACEScg"}:
        return rgb

    raise NotImplementedError(
        f"Backend CCTF encoding is not implemented for color space {color_space!r}"
    )


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
    x_max: float | None = None,
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

    # Scalar synchronization only; the image itself remains resident. Tiled
    # callers can pass a precomputed full-frame maximum to preserve parity.
    if x_max is None:
        x_max = backend.max(x)
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
