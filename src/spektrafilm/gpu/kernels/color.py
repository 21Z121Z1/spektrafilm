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


def _run_compiled_elementwise(backend, name: str, function, *args):
    compiled_elementwise = getattr(backend, "compiled_elementwise", None)
    if callable(compiled_elementwise):
        return compiled_elementwise(name, function, *args)(*args)
    return function(*args)


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
    specialized = getattr(backend, "rgb_to_xyz", None)
    if callable(specialized):
        return specialized(rgb, matrix_3x3)
    # M is stored as (3, 3). We want …i,ji->…j which is matmul(rgb, M.T).
    M_T = matrix_3x3.T if hasattr(matrix_3x3, 'T') else np.asarray(matrix_3x3).T
    return backend.matmul(backend.asarray(rgb), backend.asarray(M_T))


def xyz_to_rgb(xyz: Any, matrix_3x3: Any, backend) -> Any:
    """``RGB[…,j] = Σ_i XYZ[…,i] * M[j,i]`` — i.e. ``RGB = XYZ @ M.T``."""
    specialized = getattr(backend, "xyz_to_rgb", None)
    if callable(specialized):
        return specialized(xyz, matrix_3x3)
    M_T = matrix_3x3.T if hasattr(matrix_3x3, 'T') else np.asarray(matrix_3x3).T
    return backend.matmul(backend.asarray(xyz), backend.asarray(M_T))


def _backend_float32_dtype(backend):
    if getattr(backend, "precision", "float32") != "float32":
        raise NotImplementedError(
            "backend colour kernels currently support backend float32 only; "
            "set gpu_precision='float32' or use the CPU reference path."
        )
    dtype = getattr(backend, "default_dtype", None)
    if dtype is not None:
        return dtype
    mx = getattr(backend, "mx", None)
    if mx is not None:
        return mx.float32
    cp = getattr(backend, "cp", None)
    if cp is not None:
        return cp.float32
    return np.float32


def _stack_last_dim_backend(x, y, backend):
    mx = getattr(backend, "mx", None)
    if mx is not None:
        return mx.stack((x, y), axis=-1)
    cp = getattr(backend, "cp", None)
    if cp is not None:
        return cp.stack((x, y), axis=-1)
    return np.stack((x, y), axis=-1)


def _fmax_scalar_backend(x, floor: float, backend):
    fmax = getattr(backend, "fmax", None)
    if callable(fmax):
        return fmax(x, floor)
    return backend.maximum(x, floor)


def _tri2quad_backend(xy: Any, backend) -> Any:
    xy = backend.asarray(xy, dtype=_backend_float32_dtype(backend))
    tx = xy[..., 0]
    ty = xy[..., 1]
    y = ty / _fmax_scalar_backend(1.0 - tx, 1e-10, backend)
    x = (1.0 - tx) * (1.0 - tx)
    x = backend.clip(x, 0.0, 1.0)
    y = backend.clip(y, 0.0, 1.0)
    return _stack_last_dim_backend(x, y, backend)


def _illuminant_to_xy(illuminant_label: str) -> np.ndarray:
    from spektrafilm.config import STANDARD_OBSERVER_CMFS
    from spektrafilm.model.illuminants import standard_illuminant

    illuminant = standard_illuminant(illuminant_label)
    xyz = np.zeros((3,), dtype=np.float64)
    for i in range(3):
        xyz[i] = np.sum(illuminant * STANDARD_OBSERVER_CMFS[:, i])
    return xyz[0:2] / np.sum(xyz)


@lru_cache(maxsize=32)
def _cached_rgb_to_xyz_matrix(
    color_space: str,
    reference_illuminant: str,
    cat: str = "CAT16",
) -> np.ndarray:
    illuminant_xy = _illuminant_to_xy(reference_illuminant)
    return np.asarray(
        precompute_rgb_to_xyz_matrix(
            color_space,
            illuminant_xy=illuminant_xy,
            cat=cat,
        ),
        dtype=np.float32,
    )


@lru_cache(maxsize=32)
def _cached_rgb_to_srgb_matrix(color_space: str) -> np.ndarray:
    return np.asarray(
        colour.matrix_RGB_to_RGB(
            color_space,
            "sRGB",
            chromatic_adaptation_transform="CAT02",
        ),
        dtype=np.float32,
    )


@lru_cache(maxsize=16)
def _cached_mallett2019_basis_with_illuminant(reference_illuminant: str) -> np.ndarray:
    from spektrafilm.model.illuminants import standard_illuminant
    from spektrafilm.utils.spectral_upsampling import MALLETT2019_BASIS

    illuminant = np.asarray(standard_illuminant(reference_illuminant)[:], dtype=np.float32)
    basis = np.asarray(MALLETT2019_BASIS[:], dtype=np.float32)
    return basis * illuminant[:, None]


def rgb_to_tc_b_backend(
    rgb: Any,
    *,
    color_space: str = "ITU-R BT.2020",
    apply_cctf_decoding: bool = False,
    reference_illuminant: str = "D55",
    backend,
) -> tuple[Any, Any]:
    """Backend-resident Hanatos RGB -> triangular coordinates and brightness.

    This mirrors ``utils.spectral_upsampling._rgb_to_tc_b`` with CAT16
    adaptation, but keeps the per-pixel path on the supplied float32 backend.
    Unsupported backend transfer functions raise from
    ``cctf_decoding_transfer_backend`` instead of silently materializing the
    full image through the CPU reference helper.
    """
    if backend is None:
        raise ValueError("rgb_to_tc_b_backend requires an array backend")

    dtype = _backend_float32_dtype(backend)
    rgb_backend = backend.asarray(rgb, dtype=dtype)
    if apply_cctf_decoding:
        rgb_backend = cctf_decoding_transfer_backend(rgb_backend, color_space, backend)

    matrix = backend.asarray(
        _cached_rgb_to_xyz_matrix(color_space, reference_illuminant, "CAT16"),
        dtype=dtype,
    )
    xyz = rgb_to_xyz(rgb_backend, matrix, backend)
    b = xyz[..., 0] + xyz[..., 1] + xyz[..., 2]
    xy = xyz[..., 0:2] / _fmax_scalar_backend(b[..., None], 1e-10, backend)
    tc = _tri2quad_backend(xy, backend)
    return tc, backend.nan_to_num(b)


def rgb_to_raw_mallett2019_backend(
    rgb: Any,
    sensitivity: Any,
    *,
    color_space: str = "sRGB",
    apply_cctf_decoding: bool = True,
    reference_illuminant: str = "D65",
    backend,
) -> Any:
    """Backend-resident Mallett 2019 RGB -> raw sensor response.

    Mirrors ``utils.spectral_upsampling.rgb_to_raw_mallett2019`` while keeping
    the image-sized RGB, linear-sRGB, and raw-response tensors on the supplied
    float32 backend.  Only the small basis, sensitivity, and normalization
    constants are prepared on CPU and uploaded.
    """
    if backend is None:
        raise ValueError("rgb_to_raw_mallett2019_backend requires an array backend")

    dtype = _backend_float32_dtype(backend)
    rgb_backend = backend.asarray(rgb, dtype=dtype)
    if apply_cctf_decoding:
        rgb_backend = cctf_decoding_transfer_backend(rgb_backend, color_space, backend)

    matrix = backend.asarray(_cached_rgb_to_srgb_matrix(color_space), dtype=dtype)
    lrgb = rgb_to_xyz(rgb_backend, matrix, backend)

    sensitivity_np = np.nan_to_num(np.asarray(sensitivity, dtype=np.float32))
    basis = backend.asarray(
        _cached_mallett2019_basis_with_illuminant(reference_illuminant),
        dtype=dtype,
    )
    sensitivity_backend = backend.asarray(sensitivity_np, dtype=dtype)
    raw = backend.einsum("ijk,lk,lm->ijm", lrgb, basis, sensitivity_backend)
    raw = backend.nan_to_num(raw)

    from spektrafilm.model.illuminants import standard_illuminant

    illuminant = np.asarray(standard_illuminant(reference_illuminant)[:], dtype=np.float32)
    raw_midgray = np.einsum("k,km->m", illuminant * 0.184, sensitivity_np)
    return raw / float(raw_midgray[1])


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
    def _chain(values):
        nonlinear = 1.055 * _signed_power(values, 1.0 / 2.4, backend) - 0.055
        return backend.where(values <= 0.0031308, values * 12.92, nonlinear)

    return _run_compiled_elementwise(backend, "cctf_encoding_srgb_like", _chain, rgb)


def _cctf_encoding_romm_rgb(rgb: Any, backend) -> Any:
    def _chain(values):
        threshold = 16.0 ** (1.8 / (1.0 - 1.8))
        nonlinear = _signed_power(values, 1.0 / 1.8, backend)
        return backend.where(values < threshold, values * 16.0, nonlinear)

    return _run_compiled_elementwise(backend, "cctf_encoding_romm_rgb", _chain, rgb)


def _cctf_encoding_bt2020(rgb: Any, backend) -> Any:
    def _chain(values):
        alpha = 1.099
        beta = 0.018
        nonlinear = alpha * _signed_power(values, 0.45, backend) - (alpha - 1.0)
        return backend.where(values < beta, values * 4.5, nonlinear)

    return _run_compiled_elementwise(backend, "cctf_encoding_bt2020", _chain, rgb)


def _cctf_encoding_adobe_rgb_1998(rgb: Any, backend) -> Any:
    # colour-science uses gamma_function(..., negative_number_handling="Indeterminate")
    # for Adobe RGB (1998), so negative fractional powers intentionally
    # produce NaN, matching the CPU reference.
    def _chain(values):
        return backend.pow(values, 0.4547069271758437)

    return _run_compiled_elementwise(backend, "cctf_encoding_adobe_rgb_1998", _chain, rgb)


def _cctf_encoding_dci_p3(rgb: Any, backend) -> Any:
    def _chain(values):
        return backend.pow(values, 1.0 / 2.6)

    return _run_compiled_elementwise(backend, "cctf_encoding_dci_p3", _chain, rgb)


def _cctf_decoding_srgb_like(rgb: Any, backend) -> Any:
    def _chain(values):
        linear = values / 12.92
        nonlinear = _signed_power((values + 0.055) / 1.055, 2.4, backend)
        return backend.where(values <= 0.04045, linear, nonlinear)

    return _run_compiled_elementwise(backend, "cctf_decoding_srgb_like", _chain, rgb)


def _cctf_decoding_romm_rgb(rgb: Any, backend) -> Any:
    def _chain(values):
        linear_threshold = 16.0 ** (1.8 / (1.0 - 1.8))
        encoded_threshold = linear_threshold * 16.0
        nonlinear = _signed_power(values, 1.8, backend)
        return backend.where(values < encoded_threshold, values / 16.0, nonlinear)

    return _run_compiled_elementwise(backend, "cctf_decoding_romm_rgb", _chain, rgb)


def _cctf_decoding_bt2020(rgb: Any, backend) -> Any:
    def _chain(values):
        alpha = 1.099
        nonlinear = _signed_power((values + (alpha - 1.0)) / alpha, 1.0 / 0.45, backend)
        return backend.where(values <= 0.081, values / 4.5, nonlinear)

    return _run_compiled_elementwise(backend, "cctf_decoding_bt2020", _chain, rgb)


def _cctf_decoding_adobe_rgb_1998(rgb: Any, backend) -> Any:
    def _chain(values):
        return backend.pow(values, 1.0 / 0.4547069271758437)

    return _run_compiled_elementwise(backend, "cctf_decoding_adobe_rgb_1998", _chain, rgb)


def _cctf_decoding_dci_p3(rgb: Any, backend) -> Any:
    def _chain(values):
        return backend.pow(values, 2.6)

    return _run_compiled_elementwise(backend, "cctf_decoding_dci_p3", _chain, rgb)


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
    if color_space == "DCI-P3":
        return _cctf_encoding_dci_p3(rgb, backend)
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
    ``numba_boost_highlights.py`` using element-wise backend ops.

    For ``x <= raw_x0``: identity.
    For ``x > raw_x0``: ``y = x + boost_scale * (exp(a * dx) - a * dx - 1)``
    where ``dx = (x - raw_x0) / max_raw``.

    The ``fmax(…, 0)`` trick means dx ≡ 0 when x ≤ raw_x0, so b ≡ 0 ⟹
    y = x — exactly matching the piece-wise Numba kernel.
    """
    if boost_ev <= 0:
        return x

    # Ensure x is in the backend's native array type (e.g. MLX rejects raw
    # numpy arrays in reductions).
    x = backend.asarray(x)

    use_backend_max_array = (
        x_max is None
        and getattr(backend, "supports_gpu", False)
        and callable(getattr(backend, "max_array", None))
    )
    if use_backend_max_array:
        x_max_arr = backend.max_array(x)
        raw_x0 = backend.clip(
            backend.asarray(midgray * (2.0 ** protect_ev)),
            0.0,
            x_max_arr,
        )
        a = 28.0 ** (1.0 - boost_range)
        a_arr = backend.asarray(a)
        safe_x_max = backend.where(x_max_arr > 0.0, x_max_arr, 1.0)
        x0_norm = raw_x0 / safe_x_max
        span = 1.0 - x0_norm
        denom = backend.exp(a_arr * span) - a_arr * span - 1.0
        active = (x_max_arr > 0.0) & (raw_x0 < x_max_arr) & (denom > 0.0)
        denom_safe = backend.where(denom > 0.0, denom, 1.0)
        boost_scale = backend.asarray(2.0 ** boost_ev - 1.0) * x_max_arr / denom_safe
        inv_max_raw = 1.0 / safe_x_max

        def _chain(values, raw_x0_v, a_v, boost_scale_v, inv_max_raw_v, active_v):
            dx = backend.fmax(values - raw_x0_v, 0.0) * inv_max_raw_v
            adx = dx * a_v
            b = boost_scale_v * (backend.exp(adx) - adx - 1.0)
            return backend.where(active_v, values + b, values)

        return _run_compiled_elementwise(
            backend,
            "boost_highlights",
            _chain,
            x,
            raw_x0,
            a_arr,
            boost_scale,
            inv_max_raw,
            active,
        )

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
    params = backend.asarray([raw_x0, a, boost_scale, inv_max_raw])

    def _chain(values, factors):
        raw_x0_v = factors[0]
        a_v = factors[1]
        boost_scale_v = factors[2]
        inv_max_raw_v = factors[3]
        dx = backend.fmax(values - raw_x0_v, 0.0) * inv_max_raw_v
        adx = dx * a_v
        b = boost_scale_v * (backend.exp(adx) - adx - 1.0)
        return values + b

    return _run_compiled_elementwise(backend, "boost_highlights", _chain, x, params)
