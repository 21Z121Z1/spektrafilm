"""Fused filming filter chain via frequency-domain transfer functions.

The fused path is an opt-in implementation for the filming spatial chain:

    diffusion filter -> lens blur -> halation scatter -> halation bounces

It intentionally uses a NumPy fused implementation as the reference for the
MLX fused implementation.  It is not a strict replacement for the older serial
CPU chain, whose large Gaussian filters use the project's existing IIR-style
helpers.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import scipy.fft

from spektrafilm.utils.fast_gaussian_filter import _EXPONENTIAL_GAUSSIAN_FITS


_GAUSSIAN_SUPPORT_SIGMAS = 8.0
_MIN_ACTIVE_PAD = 5


@dataclass(frozen=True)
class _FusedFilterPlan:
    image_shape: tuple[int, int, int]
    pad_y: int
    pad_x: int
    fft_shape: tuple[int, int]
    diffusion_radius: int
    precision: str


def supports_fused_filming_filters(backend: Any) -> bool:
    """Return True when *backend* can run the MLX fused filming path."""
    if backend is None or not bool(getattr(backend, "supports_gpu", False)):
        return False
    mx = getattr(backend, "mx", None)
    if mx is None:
        return False
    fft = getattr(mx, "fft", None)
    return callable(getattr(fft, "fft2", None)) and callable(getattr(fft, "ifft2", None))


def _clear_mlx_cache(backend) -> None:
    clear = getattr(backend, "clear_cache", None)
    if callable(clear):
        clear()
        return
    mx = getattr(backend, "mx", None)
    clear = getattr(mx, "clear_cache", None)
    if callable(clear):
        clear()
        return
    metal = getattr(mx, "metal", None)
    clear = getattr(metal, "clear_cache", None)
    if callable(clear):
        clear()


def _frequency_squared_grid(fft_h: int, fft_w: int, *, dtype=np.float64, real: bool = False) -> np.ndarray:
    fy = scipy.fft.fftfreq(fft_h).astype(dtype, copy=False)
    fx_fn = scipy.fft.rfftfreq if real else scipy.fft.fftfreq
    fx = fx_fn(fft_w).astype(dtype, copy=False)
    return fy[:, None] ** 2 + fx[None, :] ** 2


def _frequency_squared_grid_mlx(fft_h: int, fft_w: int, backend, *, real: bool = False):
    mx = backend.mx
    fy = mx.fft.fftfreq(fft_h).astype(mx.float32)
    fx_fn = mx.fft.rfftfreq if real else mx.fft.fftfreq
    fx = fx_fn(fft_w).astype(mx.float32)
    return fy[:, None] * fy[:, None] + fx[None, :] * fx[None, :]


def _normalized_exponential_fit(n_gaussians: int) -> np.ndarray:
    if n_gaussians not in _EXPONENTIAL_GAUSSIAN_FITS:
        raise ValueError(
            f"No hardcoded fit for n_gaussians={n_gaussians}; "
            f"available: {sorted(_EXPONENTIAL_GAUSSIAN_FITS)}"
        )
    fit = np.asarray(_EXPONENTIAL_GAUSSIAN_FITS[n_gaussians], dtype=np.float64)
    fit = fit.copy()
    fit[:, 0] /= fit[:, 0].sum()
    return fit


def _gauss_tf(f2: np.ndarray, sigma_px: np.ndarray) -> np.ndarray:
    sigma = np.asarray(sigma_px, dtype=f2.dtype)
    coeff = np.asarray(-2.0 * np.pi ** 2, dtype=f2.dtype) * sigma * sigma
    return np.exp(f2[..., None] * coeff[None, None, :])


def _gauss_tf_mlx(f2, sigma_px: np.ndarray, backend):
    mx = backend.mx
    sigma = backend.asarray(np.asarray(sigma_px, dtype=np.float32))
    coeff = np.float32(-2.0 * np.pi ** 2) * sigma * sigma
    return mx.exp(f2[..., None] * coeff[None, None, :])


def _gauss_tf_mlx_scalar(f2, sigma_px: float, backend):
    sigma = np.float32(max(float(sigma_px), 1e-6))
    return backend.mx.exp(f2 * np.float32(-2.0 * np.pi ** 2 * sigma * sigma))


def _channel_values(values: Any, channels: int, *, dtype=np.float64) -> np.ndarray:
    arr = np.asarray(values, dtype=dtype)
    if arr.ndim == 0:
        return np.full((channels,), float(arr), dtype=dtype)
    arr = arr.reshape(-1)
    if arr.size == channels:
        return arr
    if arr.size == 1:
        return np.full((channels,), float(arr[0]), dtype=dtype)
    raise ValueError(f"Expected scalar or {channels} channel values, got shape {arr.shape}")


def _support_from_sigmas(sigmas_px: np.ndarray) -> int:
    sigmas = np.asarray(sigmas_px, dtype=np.float64)
    if sigmas.size == 0 or not np.any(sigmas > 0.0):
        return 0
    return int(np.ceil(max(_GAUSSIAN_SUPPORT_SIGMAS * float(np.max(sigmas)), _MIN_ACTIVE_PAD)))


def _diffusion_radius(image_shape: tuple[int, int, int], diffusion_filter, pixel_size_um: float) -> int:
    from spektrafilm.model.diffusion import (
        _DIFFUSION_FILTER_SHAPES,
        _bloom_max_lambda_um,
        _overrides_from_params,
    )

    if (
        not diffusion_filter.active
        or diffusion_filter.strength <= 0
        or diffusion_filter.spatial_scale <= 0
    ):
        return 0

    family = diffusion_filter.filter_family
    if family not in _DIFFUSION_FILTER_SHAPES:
        raise ValueError(f"Unknown diffusion filter family: {family!r}")

    overrides = _overrides_from_params(diffusion_filter)
    bloom_max_lambda_px = (
        _bloom_max_lambda_um(family, overrides) * diffusion_filter.spatial_scale / pixel_size_um
    )
    radius = int(np.ceil(max(_GAUSSIAN_SUPPORT_SIGMAS * bloom_max_lambda_px, _MIN_ACTIVE_PAD)))
    max_radius = max(min(image_shape[0], image_shape[1]) // 2 - 1, 1)
    return min(radius, max_radius)


def _spatial_support_radius(
    image_shape: tuple[int, int, int],
    *,
    diffusion_filter,
    lens_blur_um: float,
    halation,
    pixel_size_um: float,
) -> tuple[int, int]:
    channels = image_shape[2]
    radius = _diffusion_radius(image_shape, diffusion_filter, pixel_size_um)

    if lens_blur_um > 0:
        radius = max(radius, _support_from_sigmas(np.array([lens_blur_um / pixel_size_um])))

    if halation.active:
        if float(halation.scatter_amount) > 0.0:
            scatter_scale = float(halation.scatter_spatial_scale)
            scatter_sigmas = _channel_values(halation.scatter_core_um, channels) * scatter_scale / pixel_size_um
            tail_lambda = _channel_values(halation.scatter_tail_um, channels) * scatter_scale / pixel_size_um
            tail_weight = _channel_values(halation.scatter_tail_weight, channels)
            fit = _normalized_exponential_fit(3)
            if np.any(tail_weight > 0.0):
                tail_sigmas = np.array(
                    [sigma_ratio * tail_lambda for _amplitude, sigma_ratio in fit],
                    dtype=np.float64,
                )
                radius = max(radius, _support_from_sigmas(tail_sigmas))
            if np.any(scatter_sigmas > 0.0):
                radius = max(radius, _support_from_sigmas(scatter_sigmas))

        a_tot = _channel_values(halation.halation_strength, channels) * float(halation.halation_amount)
        sigma_h = (
            _channel_values(halation.halation_first_sigma_um, channels)
            * float(halation.halation_spatial_scale)
            / pixel_size_um
        )
        n_bounces = int(halation.halation_n_bounces)
        if n_bounces >= 1 and np.any(a_tot > 0.0) and np.any(sigma_h > 0.0):
            radius = max(radius, _support_from_sigmas(sigma_h * np.sqrt(float(n_bounces))))

    max_reflect_pad = max(min(image_shape[0], image_shape[1]) - 1, 0)
    radius = min(radius, max_reflect_pad)
    return radius, _diffusion_radius(image_shape, diffusion_filter, pixel_size_um)


def _fast_symmetric_pad(size: int, min_pad: int) -> int:
    """Return a symmetric pad whose padded size is scipy-FFT friendly."""
    pad = max(int(min_pad), 0)
    target = scipy.fft.next_fast_len(size + 2 * pad)
    while target < size + 2 * pad or (target - size) % 2 != 0:
        target = scipy.fft.next_fast_len(target + 1)
    return (target - size) // 2


def _make_plan(
    raw: Any,
    *,
    diffusion_filter,
    lens_blur_um: float,
    halation,
    pixel_size_um: float,
    backend=None,
) -> _FusedFilterPlan | None:
    shape = tuple(int(s) for s in raw.shape)
    if len(shape) != 3:
        raise ValueError(f"Expected HxWxC image, got shape {shape}")

    support_radius, diffusion_radius = _spatial_support_radius(
        shape,
        diffusion_filter=diffusion_filter,
        lens_blur_um=lens_blur_um,
        halation=halation,
        pixel_size_um=pixel_size_um,
    )

    if support_radius <= 0:
        return None

    pad_y = _fast_symmetric_pad(shape[0], support_radius)
    pad_x = _fast_symmetric_pad(shape[1], support_radius)
    fft_shape = (shape[0] + 2 * pad_y, shape[1] + 2 * pad_x)
    precision = "float32" if _should_use_float32(raw, backend) else "float64"
    return _FusedFilterPlan(
        image_shape=shape,
        pad_y=pad_y,
        pad_x=pad_x,
        fft_shape=fft_shape,
        diffusion_radius=diffusion_radius,
        precision=precision,
    )


def _should_use_float32(raw: Any, backend=None) -> bool:
    if backend is not None and supports_fused_filming_filters(backend):
        return True
    dtype = getattr(raw, "dtype", None)
    return dtype == np.dtype("float32")


def _expand_transfer_numpy(component: np.ndarray, channels: int) -> np.ndarray:
    if component.ndim == 2:
        component = component[..., None]
    if component.ndim != 3:
        raise ValueError(f"Expected 2D or 3D transfer function, got shape {component.shape}")
    if component.shape[2] == channels:
        return component
    if component.shape[2] == 1:
        return np.broadcast_to(component, (*component.shape[:2], channels))
    raise ValueError(f"Transfer channel count {component.shape[2]} does not match image channels {channels}")


def _build_diffusion_tf_numpy(
    plan: _FusedFilterPlan,
    diffusion_filter,
    pixel_size_um: float,
) -> np.ndarray | None:
    from spektrafilm.model.diffusion import (
        _DIFFUSION_FILTER_SHAPES,
        _overrides_from_params,
        _strength_to_scatter,
        diffusion_filter_psf,
    )

    if (
        not diffusion_filter.active
        or diffusion_filter.strength <= 0
        or diffusion_filter.spatial_scale <= 0
    ):
        return None
    family = diffusion_filter.filter_family
    if family not in _DIFFUSION_FILTER_SHAPES:
        raise ValueError(f"Unknown diffusion filter family: {family!r}")
    p_s = _strength_to_scatter(diffusion_filter.strength, family)
    if p_s <= 0.0:
        return None

    radius = plan.diffusion_radius
    if radius <= 0:
        return None

    overrides = _overrides_from_params(diffusion_filter)
    psf = diffusion_filter_psf(
        (2 * radius + 1, 2 * radius + 1),
        family=family,
        spatial_scale=diffusion_filter.spatial_scale,
        pixel_size_um=pixel_size_um,
        halo_warmth=float(getattr(diffusion_filter, "halo_warmth", 0.0)),
        overrides=overrides,
    )
    if plan.precision == "float32":
        psf = psf.astype(np.float32, copy=False)
    fft_h, fft_w = plan.fft_shape
    kernel_grid = np.zeros((fft_h, fft_w, psf.shape[2]), dtype=psf.dtype)
    kernel_grid[: psf.shape[0], : psf.shape[1], :] = psf
    kernel_grid = np.roll(kernel_grid, shift=(-radius, -radius), axis=(0, 1))
    kernel_fft = scipy.fft.rfft2(kernel_grid, axes=(0, 1))
    return (1.0 - p_s) + p_s * kernel_fft


def _build_lens_tf_numpy(
    f2: np.ndarray,
    *,
    lens_blur_um: float,
    pixel_size_um: float,
) -> np.ndarray | None:
    if lens_blur_um <= 0:
        return None
    sigma_px = lens_blur_um / pixel_size_um
    if sigma_px <= 0:
        return None
    return np.exp(f2 * np.asarray(-2.0 * np.pi ** 2 * sigma_px ** 2, dtype=f2.dtype))


def _build_scatter_tf_numpy(
    f2: np.ndarray,
    halation,
    pixel_size_um: float,
    channels: int,
) -> np.ndarray | None:
    if not halation.active:
        return None
    s_amount = float(halation.scatter_amount)
    if s_amount <= 0.0:
        return None

    scatter_scale = float(halation.scatter_spatial_scale)
    w_s = _channel_values(halation.scatter_tail_weight, channels, dtype=f2.dtype)
    sigma_c_px = _channel_values(halation.scatter_core_um, channels, dtype=f2.dtype) * scatter_scale / pixel_size_um
    lambda_t_px = _channel_values(halation.scatter_tail_um, channels, dtype=f2.dtype) * scatter_scale / pixel_size_um
    if not (np.any(sigma_c_px > 0.0) or np.any(lambda_t_px > 0.0)):
        return None

    h_scattered = (1.0 - w_s)[None, None, :] * _gauss_tf(f2, np.maximum(sigma_c_px, 1e-6))
    for amplitude, sigma_ratio in _normalized_exponential_fit(3).astype(f2.dtype, copy=False):
        h_scattered += (w_s * amplitude)[None, None, :] * _gauss_tf(
            f2,
            np.maximum(sigma_ratio * lambda_t_px, 1e-6),
        )
    return (1.0 - s_amount) + s_amount * h_scattered


def _build_halation_tf_numpy(
    f2: np.ndarray,
    halation,
    pixel_size_um: float,
    channels: int,
) -> np.ndarray | None:
    if not halation.active:
        return None

    h_amount = float(halation.halation_amount)
    a_tot = _channel_values(halation.halation_strength, channels, dtype=f2.dtype) * h_amount
    sigma_h_px = (
        _channel_values(halation.halation_first_sigma_um, channels, dtype=f2.dtype)
        * float(halation.halation_spatial_scale)
        / pixel_size_um
    )
    n_bounces = int(halation.halation_n_bounces)
    rho = float(halation.halation_bounce_decay)
    if n_bounces < 1 or not np.any(a_tot > 0.0) or not np.any(sigma_h_px > 0.0):
        return None

    decay = np.asarray([rho ** (k - 1) for k in range(1, n_bounces + 1)], dtype=f2.dtype)
    decay /= decay.sum()
    h_blur = np.zeros((*f2.shape, channels), dtype=f2.dtype)
    for k, wk in zip(range(1, n_bounces + 1), decay):
        sigma_k = np.maximum(sigma_h_px * np.sqrt(k), 1e-6)
        h_blur += wk * _gauss_tf(f2, sigma_k)

    h_total = 1.0 + a_tot[None, None, :] * h_blur
    if halation.halation_renormalize:
        h_total = h_total / (1.0 + a_tot)[None, None, :]
    return h_total


def _build_combined_transfer_numpy(
    plan: _FusedFilterPlan,
    *,
    diffusion_filter,
    lens_blur_um: float,
    halation,
    pixel_size_um: float,
) -> np.ndarray | None:
    channels = plan.image_shape[2]
    dtype = np.float32 if plan.precision == "float32" else np.float64
    f2 = _frequency_squared_grid(*plan.fft_shape, dtype=dtype, real=True)
    h_total = np.ones((*f2.shape, channels), dtype=dtype)
    has_component = False
    for component in (
        _build_diffusion_tf_numpy(plan, diffusion_filter, pixel_size_um),
        _build_lens_tf_numpy(f2, lens_blur_um=lens_blur_um, pixel_size_um=pixel_size_um),
        _build_scatter_tf_numpy(f2, halation, pixel_size_um, channels),
        _build_halation_tf_numpy(f2, halation, pixel_size_um, channels),
    ):
        if component is None:
            continue
        has_component = True
        h_total = h_total * _expand_transfer_numpy(component, channels)
        del component
    if not has_component:
        return None
    if plan.precision == "float32":
        return np.asarray(h_total, dtype=np.complex64 if np.iscomplexobj(h_total) else np.float32)
    return h_total


def _expand_transfer_mlx(component, channels: int, backend):
    if len(component.shape) == 2:
        component = component[..., None]
    if int(component.shape[2]) == channels:
        return component
    if int(component.shape[2]) == 1:
        return backend.mx.broadcast_to(component, (*component.shape[:2], channels))
    raise ValueError(f"Transfer channel count {component.shape[2]} does not match image channels {channels}")


def _build_diffusion_tf_mlx(
    plan: _FusedFilterPlan,
    diffusion_filter,
    pixel_size_um: float,
    backend,
):
    from spektrafilm.model.diffusion import (
        _DIFFUSION_FILTER_SHAPES,
        _overrides_from_params,
        _strength_to_scatter,
        diffusion_filter_psf,
    )

    if (
        not diffusion_filter.active
        or diffusion_filter.strength <= 0
        or diffusion_filter.spatial_scale <= 0
    ):
        return None
    family = diffusion_filter.filter_family
    if family not in _DIFFUSION_FILTER_SHAPES:
        raise ValueError(f"Unknown diffusion filter family: {family!r}")
    p_s = _strength_to_scatter(diffusion_filter.strength, family)
    if p_s <= 0.0 or plan.diffusion_radius <= 0:
        return None

    mx = backend.mx
    radius = plan.diffusion_radius
    psf = diffusion_filter_psf(
        (2 * radius + 1, 2 * radius + 1),
        family=family,
        spatial_scale=diffusion_filter.spatial_scale,
        pixel_size_um=pixel_size_um,
        halo_warmth=float(getattr(diffusion_filter, "halo_warmth", 0.0)),
        overrides=_overrides_from_params(diffusion_filter),
    ).astype(np.float32, copy=False)
    psf_gpu = backend.asarray(psf)
    fft_h, fft_w = plan.fft_shape
    pad_h = fft_h - int(psf.shape[0])
    pad_w = fft_w - int(psf.shape[1])
    kernel_grid = mx.pad(psf_gpu, [(0, pad_h), (0, pad_w), (0, 0)])
    kernel_grid = mx.roll(kernel_grid, shift=(-radius, -radius), axis=(0, 1))
    kernel_fft = mx.fft.rfft2(kernel_grid, axes=(0, 1))
    return np.float32(1.0 - p_s) + np.float32(p_s) * kernel_fft


def _build_lens_tf_mlx(f2, *, lens_blur_um: float, pixel_size_um: float, backend):
    if lens_blur_um <= 0:
        return None
    sigma_px = np.float32(lens_blur_um / pixel_size_um)
    if sigma_px <= 0:
        return None
    return backend.mx.exp(f2 * np.float32(-2.0 * np.pi ** 2 * sigma_px * sigma_px))


def _build_scatter_tf_mlx(f2, halation, pixel_size_um: float, channels: int, backend):
    if not halation.active:
        return None
    s_amount = np.float32(halation.scatter_amount)
    if s_amount <= 0:
        return None

    scatter_scale = float(halation.scatter_spatial_scale)
    w_s_np = _channel_values(halation.scatter_tail_weight, channels, dtype=np.float32)
    sigma_c_np = _channel_values(halation.scatter_core_um, channels, dtype=np.float32) * scatter_scale / pixel_size_um
    lambda_t_np = _channel_values(halation.scatter_tail_um, channels, dtype=np.float32) * scatter_scale / pixel_size_um
    if not (np.any(sigma_c_np > 0.0) or np.any(lambda_t_np > 0.0)):
        return None

    w_s = backend.asarray(w_s_np)
    h_scattered = (
        (np.float32(1.0) - w_s)[None, None, :]
        * _gauss_tf_mlx(f2, np.maximum(sigma_c_np, 1e-6), backend)
    )
    for amplitude, sigma_ratio in _normalized_exponential_fit(3).astype(np.float32, copy=False):
        h_scattered = h_scattered + (w_s * np.float32(amplitude))[None, None, :] * _gauss_tf_mlx(
            f2,
            np.maximum(np.float32(sigma_ratio) * lambda_t_np, 1e-6),
            backend,
        )
    return (np.float32(1.0) - s_amount) + s_amount * h_scattered


def _build_halation_tf_mlx(f2, halation, pixel_size_um: float, channels: int, backend):
    if not halation.active:
        return None

    mx = backend.mx
    a_tot_np = (
        _channel_values(halation.halation_strength, channels, dtype=np.float32)
        * np.float32(halation.halation_amount)
    )
    sigma_h_np = (
        _channel_values(halation.halation_first_sigma_um, channels, dtype=np.float32)
        * np.float32(halation.halation_spatial_scale)
        / np.float32(pixel_size_um)
    )
    n_bounces = int(halation.halation_n_bounces)
    rho = float(halation.halation_bounce_decay)
    if n_bounces < 1 or not np.any(a_tot_np > 0.0) or not np.any(sigma_h_np > 0.0):
        return None

    decay = np.asarray([rho ** (k - 1) for k in range(1, n_bounces + 1)], dtype=np.float32)
    decay /= decay.sum()
    h_blur = mx.zeros((*f2.shape, channels), dtype=mx.float32)
    for k, wk in zip(range(1, n_bounces + 1), decay):
        sigma_k = np.maximum(sigma_h_np * np.sqrt(k), 1e-6)
        h_blur = h_blur + np.float32(wk) * _gauss_tf_mlx(f2, sigma_k, backend)

    a_tot = backend.asarray(a_tot_np)
    h_total = np.float32(1.0) + a_tot[None, None, :] * h_blur
    if halation.halation_renormalize:
        h_total = h_total / (np.float32(1.0) + a_tot)[None, None, :]
    return h_total


def _build_combined_transfer_mlx(
    plan: _FusedFilterPlan,
    *,
    diffusion_filter,
    lens_blur_um: float,
    halation,
    pixel_size_um: float,
    backend,
):
    mx = backend.mx
    channels = plan.image_shape[2]
    f2 = _frequency_squared_grid_mlx(*plan.fft_shape, backend, real=True)
    h_total = mx.ones((*f2.shape, channels), dtype=mx.float32)
    builders = (
        lambda: _build_diffusion_tf_mlx(plan, diffusion_filter, pixel_size_um, backend),
        lambda: _build_lens_tf_mlx(f2, lens_blur_um=lens_blur_um, pixel_size_um=pixel_size_um, backend=backend),
        lambda: _build_scatter_tf_mlx(f2, halation, pixel_size_um, channels, backend),
        lambda: _build_halation_tf_mlx(f2, halation, pixel_size_um, channels, backend),
    )
    has_component = False
    for build_component in builders:
        component = build_component()
        if component is None:
            continue
        has_component = True
        h_total = h_total * _expand_transfer_mlx(component, channels, backend)
        mx.eval(h_total)
        del component
        _clear_mlx_cache(backend)
    if not has_component:
        return None
    return h_total


def _build_diffusion_tf_channel_mlx(
    plan: _FusedFilterPlan,
    channel: int,
    diffusion_filter,
    pixel_size_um: float,
    backend,
):
    from spektrafilm.model.diffusion import (
        _DIFFUSION_FILTER_SHAPES,
        _overrides_from_params,
        _strength_to_scatter,
        diffusion_filter_psf,
    )

    if (
        not diffusion_filter.active
        or diffusion_filter.strength <= 0
        or diffusion_filter.spatial_scale <= 0
    ):
        return None
    family = diffusion_filter.filter_family
    if family not in _DIFFUSION_FILTER_SHAPES:
        raise ValueError(f"Unknown diffusion filter family: {family!r}")
    p_s = _strength_to_scatter(diffusion_filter.strength, family)
    if p_s <= 0.0 or plan.diffusion_radius <= 0:
        return None

    mx = backend.mx
    radius = plan.diffusion_radius
    psf = diffusion_filter_psf(
        (2 * radius + 1, 2 * radius + 1),
        family=family,
        spatial_scale=diffusion_filter.spatial_scale,
        pixel_size_um=pixel_size_um,
        halo_warmth=float(getattr(diffusion_filter, "halo_warmth", 0.0)),
        overrides=_overrides_from_params(diffusion_filter),
    )[:, :, channel].astype(np.float32, copy=False)
    psf_gpu = backend.asarray(psf)
    fft_h, fft_w = plan.fft_shape
    kernel_grid = mx.pad(psf_gpu, [(0, fft_h - int(psf.shape[0])), (0, fft_w - int(psf.shape[1]))])
    kernel_grid = mx.roll(kernel_grid, shift=(-radius, -radius), axis=(0, 1))
    kernel_fft = mx.fft.rfft2(kernel_grid, axes=(0, 1))
    return np.float32(1.0 - p_s) + np.float32(p_s) * kernel_fft


def _build_scatter_tf_channel_mlx(f2, halation, pixel_size_um: float, channel: int, backend):
    if not halation.active:
        return None
    s_amount = np.float32(halation.scatter_amount)
    if s_amount <= 0:
        return None

    scatter_scale = np.float32(halation.scatter_spatial_scale)
    w_s = np.float32(_channel_values(halation.scatter_tail_weight, 3, dtype=np.float32)[channel])
    sigma_c = (
        np.float32(_channel_values(halation.scatter_core_um, 3, dtype=np.float32)[channel])
        * scatter_scale
        / np.float32(pixel_size_um)
    )
    lambda_t = (
        np.float32(_channel_values(halation.scatter_tail_um, 3, dtype=np.float32)[channel])
        * scatter_scale
        / np.float32(pixel_size_um)
    )
    if not (sigma_c > 0.0 or lambda_t > 0.0):
        return None

    h_scattered = (np.float32(1.0) - w_s) * _gauss_tf_mlx_scalar(f2, float(sigma_c), backend)
    for amplitude, sigma_ratio in _normalized_exponential_fit(3).astype(np.float32, copy=False):
        h_scattered = h_scattered + w_s * np.float32(amplitude) * _gauss_tf_mlx_scalar(
            f2,
            float(np.float32(sigma_ratio) * lambda_t),
            backend,
        )
    return (np.float32(1.0) - s_amount) + s_amount * h_scattered


def _build_halation_tf_channel_mlx(f2, halation, pixel_size_um: float, channel: int, backend):
    if not halation.active:
        return None

    mx = backend.mx
    a_tot = (
        np.float32(_channel_values(halation.halation_strength, 3, dtype=np.float32)[channel])
        * np.float32(halation.halation_amount)
    )
    sigma_h = (
        np.float32(_channel_values(halation.halation_first_sigma_um, 3, dtype=np.float32)[channel])
        * np.float32(halation.halation_spatial_scale)
        / np.float32(pixel_size_um)
    )
    n_bounces = int(halation.halation_n_bounces)
    rho = float(halation.halation_bounce_decay)
    if n_bounces < 1 or a_tot <= 0.0 or sigma_h <= 0.0:
        return None

    decay = np.asarray([rho ** (k - 1) for k in range(1, n_bounces + 1)], dtype=np.float32)
    decay /= decay.sum()
    h_blur = mx.zeros(f2.shape, dtype=mx.float32)
    for k, wk in zip(range(1, n_bounces + 1), decay):
        h_blur = h_blur + np.float32(wk) * _gauss_tf_mlx_scalar(
            f2,
            float(sigma_h * np.sqrt(k)),
            backend,
        )

    h_total = np.float32(1.0) + a_tot * h_blur
    if halation.halation_renormalize:
        h_total = h_total / (np.float32(1.0) + a_tot)
    return h_total


def _build_transfer_channel_mlx(
    plan: _FusedFilterPlan,
    channel: int,
    *,
    diffusion_filter,
    lens_blur_um: float,
    halation,
    pixel_size_um: float,
    backend,
):
    mx = backend.mx
    f2 = _frequency_squared_grid_mlx(*plan.fft_shape, backend, real=True)
    h_total = mx.ones(f2.shape, dtype=mx.float32)
    has_component = False
    components = (
        _build_diffusion_tf_channel_mlx(plan, channel, diffusion_filter, pixel_size_um, backend),
        _build_lens_tf_mlx(f2, lens_blur_um=lens_blur_um, pixel_size_um=pixel_size_um, backend=backend),
        _build_scatter_tf_channel_mlx(f2, halation, pixel_size_um, channel, backend),
        _build_halation_tf_channel_mlx(f2, halation, pixel_size_um, channel, backend),
    )
    for component in components:
        if component is None:
            continue
        has_component = True
        h_total = h_total * component
        mx.eval(h_total)
        del component
        _clear_mlx_cache(backend)
    if not has_component:
        return None
    return h_total


def _reflect_indices_numpy(length: int, pad_before: int, pad_after: int) -> np.ndarray:
    if length <= 1:
        return np.zeros((length + pad_before + pad_after,), dtype=np.int64)
    idx = np.arange(-pad_before, length + pad_after, dtype=np.int64)
    period = 2 * length - 2
    reflected = np.mod(idx, period)
    return np.where(reflected < length, reflected, period - reflected)


def _reflect_pad_numpy(raw: np.ndarray, pad_y: int, pad_x: int) -> np.ndarray:
    if pad_y <= 0 and pad_x <= 0:
        return raw
    y_idx = _reflect_indices_numpy(raw.shape[0], pad_y, pad_y)
    x_idx = _reflect_indices_numpy(raw.shape[1], pad_x, pad_x)
    return raw[y_idx][:, x_idx, :]


def _reflect_indices_mlx(length: int, pad_before: int, pad_after: int, backend):
    mx = backend.mx
    if length <= 1:
        return mx.zeros((length + pad_before + pad_after,), dtype=mx.int32)
    idx = mx.arange(-pad_before, length + pad_after, dtype=mx.int32)
    period = 2 * length - 2
    reflected = idx % period
    return mx.where(reflected < length, reflected, period - reflected)


def _reflect_pad_mlx(raw: Any, pad_y: int, pad_x: int, backend):
    image = backend.asarray(raw)
    if pad_y <= 0 and pad_x <= 0:
        return image
    y_idx = _reflect_indices_mlx(int(image.shape[0]), pad_y, pad_y, backend)
    x_idx = _reflect_indices_mlx(int(image.shape[1]), pad_x, pad_x, backend)
    padded = backend.mx.take(image, y_idx, axis=0)
    return backend.mx.take(padded, x_idx, axis=1)


def _apply_fused_numpy(raw: np.ndarray, transfer: np.ndarray, plan: _FusedFilterPlan) -> np.ndarray:
    raw_np = np.asarray(raw)
    source_dtype = raw_np.dtype
    work_dtype = np.float32 if plan.precision == "float32" else np.float64
    padded = _reflect_pad_numpy(raw_np.astype(work_dtype, copy=False), plan.pad_y, plan.pad_x)
    image_fft = scipy.fft.rfft2(padded, axes=(0, 1))
    filtered = scipy.fft.irfft2(image_fft * transfer, s=plan.fft_shape, axes=(0, 1))
    h, w, _channels = plan.image_shape
    cropped = filtered[plan.pad_y:plan.pad_y + h, plan.pad_x:plan.pad_x + w, :]
    if source_dtype == np.dtype("float32"):
        return np.asarray(cropped, dtype=np.float32)
    return cropped


def _apply_fused_mlx(
    raw: Any,
    plan: _FusedFilterPlan,
    *,
    diffusion_filter,
    lens_blur_um: float,
    halation,
    pixel_size_um: float,
    backend,
):
    mx = backend.mx
    h, w, channels = plan.image_shape
    image = backend.asarray(raw)
    output_channels = []
    for channel in range(channels):
        transfer = _build_transfer_channel_mlx(
            plan,
            channel,
            diffusion_filter=diffusion_filter,
            lens_blur_um=lens_blur_um,
            halation=halation,
            pixel_size_um=pixel_size_um,
            backend=backend,
        )
        if transfer is None:
            output_channels.append(image[:, :, channel])
            continue
        mx.eval(transfer)
        _clear_mlx_cache(backend)
        padded = _reflect_pad_mlx(image[:, :, channel], plan.pad_y, plan.pad_x, backend)
        image_fft = mx.fft.rfft2(padded, axes=(0, 1))
        mx.eval(image_fft)
        del padded
        _clear_mlx_cache(backend)
        filtered = mx.fft.irfft2(image_fft * transfer, s=plan.fft_shape, axes=(0, 1))
        cropped = filtered[plan.pad_y:plan.pad_y + h, plan.pad_x:plan.pad_x + w]
        mx.eval(cropped)
        output_channels.append(cropped)
        del transfer, image_fft, filtered, cropped
        _clear_mlx_cache(backend)
    return mx.stack(output_channels, axis=2)


def apply_fused_filming_filters(
    raw,
    *,
    diffusion_filter,
    lens_blur_um: float,
    halation,
    pixel_size_um: float,
    backend=None,
):
    """Apply diffusion, lens blur, and halation as one fused FFT operation.

    ``backend=None`` runs the NumPy fused reference.  A supported MLX backend
    runs the same fused model on device.  Unsupported GPU backends are rejected
    instead of silently falling back to CPU.
    """
    if backend is not None and not supports_fused_filming_filters(backend):
        raise ValueError("apply_fused_filming_filters currently supports only NumPy or MLX backends")

    plan = _make_plan(
        raw,
        diffusion_filter=diffusion_filter,
        lens_blur_um=lens_blur_um,
        halation=halation,
        pixel_size_um=pixel_size_um,
        backend=backend,
    )
    if plan is None:
        return raw

    if backend is None:
        transfer = _build_combined_transfer_numpy(
            plan,
            diffusion_filter=diffusion_filter,
            lens_blur_um=lens_blur_um,
            halation=halation,
            pixel_size_um=pixel_size_um,
        )
        if transfer is None:
            return raw
        return _apply_fused_numpy(raw, transfer, plan)

    return _apply_fused_mlx(
        raw,
        plan,
        diffusion_filter=diffusion_filter,
        lens_blur_um=lens_blur_um,
        halation=halation,
        pixel_size_um=pixel_size_um,
        backend=backend,
    )
