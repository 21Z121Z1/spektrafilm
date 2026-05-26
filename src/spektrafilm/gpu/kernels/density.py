"""Backend-portable density / spectral operations.

Mirrors the CPU functions in ``spektrafilm.model.emulsion`` and
``spektrafilm.utils.conversions`` but works through an ``ArrayBackend``
so the same code runs on NumPy, MLX, and CuPy where the operation is portable.
"""
from __future__ import annotations

from typing import Any

import numpy as np


_INTERP_DENSITY_CURVES_KERNEL = None
_INTERP_DENSITY_LAYERS_KERNEL = None


def _backend_supports_gpu(backend) -> bool:
    return (
        backend is not None
        and bool(getattr(backend, "supports_gpu", False))
    )


def _backend_supports_mlx_custom_kernels(backend) -> bool:
    return (
        _backend_supports_gpu(backend)
        and hasattr(backend, "mx")
    )


def _backend_supports_cupy(backend) -> bool:
    return _backend_supports_gpu(backend) and hasattr(backend, "cp")


def _get_interp_density_curves_kernel(mx):
    """Return the cached MLX/Metal density-curve interpolation kernel."""
    global _INTERP_DENSITY_CURVES_KERNEL
    if _INTERP_DENSITY_CURVES_KERNEL is not None:
        return _INTERP_DENSITY_CURVES_KERNEL

    source = """
        uint elem = thread_position_in_grid.x;
        uint total = values_shape[0] * values_shape[1] * values_shape[2];
        if (elem >= total) {
            return;
        }

        int c = elem % 3;
        int K = x_axis_shape[0];
        float x = float(values[elem]);

        float x_first = x_axis[c];
        float x_last = x_axis[(K - 1) * 3 + c];
        if (x <= x_first) {
            out[elem] = T(y_vals[c]);
            return;
        }
        if (x >= x_last) {
            out[elem] = T(y_vals[(K - 1) * 3 + c]);
            return;
        }

        int lo = 0;
        int hi = K;
        while (lo < hi) {
            int mid = (lo + hi) / 2;
            float xm = x_axis[mid * 3 + c];
            if (x < xm) {
                hi = mid;
            } else {
                lo = mid + 1;
            }
        }

        int low = max(lo - 1, 0);
        float x0 = x_axis[low * 3 + c];
        float x1 = x_axis[(low + 1) * 3 + c];
        float y0 = y_vals[low * 3 + c];
        float y1 = y_vals[(low + 1) * 3 + c];
        float inv_dx = x1 != x0 ? 1.0f / (x1 - x0) : 0.0f;
        float t = (x - x0) * inv_dx;
        out[elem] = T(y0 + t * (y1 - y0));
    """
    _INTERP_DENSITY_CURVES_KERNEL = mx.fast.metal_kernel(
        name="spektrafilm_interp_density_curves",
        input_names=["values", "x_axis", "y_vals"],
        output_names=["out"],
        source=source,
    )
    return _INTERP_DENSITY_CURVES_KERNEL


def _get_interp_density_layers_kernel(mx):
    """Return the cached MLX/Metal layer-density interpolation kernel."""
    global _INTERP_DENSITY_LAYERS_KERNEL
    if _INTERP_DENSITY_LAYERS_KERNEL is not None:
        return _INTERP_DENSITY_LAYERS_KERNEL

    source = """
        uint elem = thread_position_in_grid.x;
        uint height = values_shape[0];
        uint width = values_shape[1];
        uint channels = values_shape[2];
        uint layers = y_vals_shape[1];
        uint total = height * width * layers * channels;
        if (elem >= total) {
            return;
        }

        uint c = elem % channels;
        uint layer = (elem / channels) % layers;
        uint pixel = elem / (layers * channels);
        int K = x_axis_shape[0];
        float x = float(values[pixel * channels + c]);

        float x_first = x_axis[c];
        float x_last = x_axis[(K - 1) * channels + c];
        if (x <= x_first) {
            out[elem] = T(y_vals[layer * channels + c]);
            return;
        }
        if (x >= x_last) {
            out[elem] = T(y_vals[((K - 1) * layers + layer) * channels + c]);
            return;
        }

        int lo = 0;
        int hi = K;
        while (lo < hi) {
            int mid = (lo + hi) / 2;
            float xm = x_axis[mid * channels + c];
            if (x < xm) {
                hi = mid;
            } else {
                lo = mid + 1;
            }
        }

        int low = max(lo - 1, 0);
        float x0 = x_axis[low * channels + c];
        float x1 = x_axis[(low + 1) * channels + c];
        float y0 = y_vals[(low * layers + layer) * channels + c];
        float y1 = y_vals[((low + 1) * layers + layer) * channels + c];
        float inv_dx = x1 != x0 ? 1.0f / (x1 - x0) : 0.0f;
        float t = (x - x0) * inv_dx;
        out[elem] = T(y0 + t * (y1 - y0));
    """
    _INTERP_DENSITY_LAYERS_KERNEL = mx.fast.metal_kernel(
        name="spektrafilm_interp_density_layers",
        input_names=["values", "x_axis", "y_vals"],
        output_names=["out"],
        source=source,
    )
    return _INTERP_DENSITY_LAYERS_KERNEL


def _as_channel_gamma(gamma_factor: Any) -> np.ndarray:
    gamma = np.asarray(gamma_factor, dtype=np.float64)
    if gamma.ndim == 0 or gamma.size == 1:
        return np.full(3, float(gamma.reshape(-1)[0]), dtype=np.float64)
    if gamma.shape == (3,):
        return gamma
    raise ValueError("gamma_factor must be a scalar or a length-3 sequence")


def _interp_1d_cupy(x: Any, xp: Any, fp: Any, cp) -> Any:
    k = int(xp.shape[0])
    if bool(cp.asnumpy(xp[0] > xp[-1])):
        return cp.where(x <= xp[0], fp[0], cp.where(x >= xp[-1], fp[-1], fp[0]))
    idx = cp.searchsorted(xp, x, side="right")
    idx = cp.clip(idx, 1, k - 1)
    low = idx - 1
    x0 = xp[low]
    x1 = xp[idx]
    y0 = fp[low]
    y1 = fp[idx]
    inv_dx = cp.where(x1 != x0, 1.0 / (x1 - x0), 0.0)
    t = (x - x0) * inv_dx
    out = y0 + t * (y1 - y0)
    return cp.where(x <= xp[0], fp[0], cp.where(x >= xp[-1], fp[-1], out))


def _interpolate_exposure_to_density_cupy(
    log_exposure_rgb: Any,
    log_exposure: Any,
    density_curves: Any,
    gamma_factor: Any,
    backend,
) -> Any:
    cp = backend.cp
    values = backend.asarray(log_exposure_rgb)
    gamma = _as_channel_gamma(gamma_factor)
    x_axis = np.asarray(log_exposure, dtype=np.float32)[:, None] / gamma[None, :].astype(np.float32)
    y_vals = np.asarray(density_curves, dtype=np.float32)
    if x_axis.shape != y_vals.shape or x_axis.ndim != 2 or x_axis.shape[1] != 3:
        raise ValueError("log_exposure and density_curves must produce Kx3 interpolation tables")

    x_axis_cp = cp.asarray(x_axis, dtype=cp.float32)
    y_vals_cp = cp.asarray(y_vals, dtype=cp.float32)
    out = cp.empty(values.shape, dtype=values.dtype)
    for channel in range(3):
        out[..., channel] = _interp_1d_cupy(
            values[..., channel],
            x_axis_cp[:, channel],
            y_vals_cp[:, channel],
            cp,
        )
    return out


def _interpolate_density_cmy_layers_cupy(
    density_cmy: Any,
    density_curves: Any,
    density_curves_layers: Any,
    *,
    positive_film: bool,
    backend,
) -> Any:
    cp = backend.cp
    values = backend.asarray(density_cmy)
    density_curves_np = np.asarray(density_curves, dtype=np.float32)
    density_curves_layers_np = np.asarray(density_curves_layers, dtype=np.float32)
    if density_curves_np.ndim != 2 or density_curves_np.shape[1] != 3:
        raise ValueError("density_curves must have shape Kx3")
    if density_curves_layers_np.ndim != 3 or density_curves_layers_np.shape[1:] != (3, 3):
        raise ValueError("density_curves_layers must have shape Kx3x3")
    if density_curves_layers_np.shape[0] != density_curves_np.shape[0]:
        raise ValueError("density_curves and density_curves_layers must have the same length")
    if values.shape[-1] != 3:
        raise ValueError("density_cmy must have 3 channels in the last dimension")

    x_axis = density_curves_np
    y_vals = density_curves_layers_np
    if positive_film:
        values = -values
        x_axis = -x_axis

    x_axis_cp = cp.asarray(x_axis, dtype=cp.float32)
    y_vals_cp = cp.asarray(y_vals, dtype=cp.float32)
    output_shape = tuple(values.shape[:-1]) + tuple(density_curves_layers_np.shape[1:])
    out = cp.empty(output_shape, dtype=values.dtype)
    for channel in range(3):
        for layer in range(3):
            out[..., layer, channel] = _interp_1d_cupy(
                values[..., channel],
                x_axis_cp[:, channel],
                y_vals_cp[:, layer, channel],
                cp,
            )
    return out


def interpolate_exposure_to_density_backend(
    log_exposure_rgb: Any,
    log_exposure: Any,
    density_curves: Any,
    gamma_factor: Any,
    backend=None,
) -> Any:
    """Backend-aware equivalent of ``fast_interp`` for density curves.

    MLX uses a custom Metal kernel and CuPy uses device-side searchsorted
    interpolation, both with the same endpoint clamp and right-biased
    exact-match behaviour as ``spektrafilm.utils.fast_interp``. The CPU path
    intentionally delegates to the existing Numba reference.
    """
    if not _backend_supports_gpu(backend):
        from spektrafilm.model.density_curves import interpolate_exposure_to_density

        return interpolate_exposure_to_density(
            log_exposure_rgb,
            np.asarray(density_curves),
            np.asarray(log_exposure),
            gamma_factor,
        )
    if _backend_supports_cupy(backend):
        return _interpolate_exposure_to_density_cupy(
            log_exposure_rgb,
            log_exposure,
            density_curves,
            gamma_factor,
            backend,
        )
    if not _backend_supports_mlx_custom_kernels(backend):
        from spektrafilm.model.density_curves import interpolate_exposure_to_density

        return backend.asarray(
            interpolate_exposure_to_density(
                backend.to_numpy(log_exposure_rgb),
                np.asarray(density_curves),
                np.asarray(log_exposure),
                gamma_factor,
            )
        )

    if log_exposure_rgb.shape[-1] != 3:
        raise ValueError("log_exposure_rgb must have 3 channels in the last dimension")

    mx = backend.mx
    gamma = _as_channel_gamma(gamma_factor)
    x_axis = np.asarray(log_exposure, dtype=np.float32)[:, None] / gamma[None, :].astype(np.float32)
    y_vals = np.asarray(density_curves, dtype=np.float32)
    if x_axis.shape != y_vals.shape or x_axis.ndim != 2 or x_axis.shape[1] != 3:
        raise ValueError("log_exposure and density_curves must produce Kx3 interpolation tables")

    values = backend.asarray(log_exposure_rgb)
    x_axis_mx = mx.array(x_axis, dtype=mx.float32)
    y_vals_mx = mx.array(y_vals, dtype=mx.float32)
    kernel = _get_interp_density_curves_kernel(mx)
    outputs = kernel(
        inputs=[values, x_axis_mx, y_vals_mx],
        template=[("T", values.dtype)],
        grid=(int(np.prod(values.shape)), 1, 1),
        threadgroup=(256, 1, 1),
        output_shapes=[values.shape],
        output_dtypes=[values.dtype],
    )
    return outputs[0]


def interpolate_density_cmy_layers_backend(
    density_cmy: Any,
    density_curves: Any,
    density_curves_layers: Any,
    *,
    positive_film: bool = False,
    backend=None,
) -> Any:
    """Backend-aware equivalent of ``interp_density_cmy_layers``."""
    if not _backend_supports_gpu(backend):
        from spektrafilm.model.density_curves import _interp_density_cmy_layers_cpu

        return _interp_density_cmy_layers_cpu(
            density_cmy,
            np.asarray(density_curves),
            np.asarray(density_curves_layers),
            positive_film=positive_film,
        )
    if _backend_supports_cupy(backend):
        return _interpolate_density_cmy_layers_cupy(
            density_cmy,
            density_curves,
            density_curves_layers,
            positive_film=positive_film,
            backend=backend,
        )
    if not _backend_supports_mlx_custom_kernels(backend):
        from spektrafilm.model.density_curves import _interp_density_cmy_layers_cpu

        return backend.asarray(
            _interp_density_cmy_layers_cpu(
                backend.to_numpy(density_cmy),
                np.asarray(density_curves),
                np.asarray(density_curves_layers),
                positive_film=positive_film,
            )
        )

    density_curves_np = np.asarray(density_curves, dtype=np.float32)
    density_curves_layers_np = np.asarray(density_curves_layers, dtype=np.float32)
    if density_curves_np.ndim != 2 or density_curves_np.shape[1] != 3:
        raise ValueError("density_curves must have shape Kx3")
    if density_curves_layers_np.ndim != 3 or density_curves_layers_np.shape[1:] != (3, 3):
        raise ValueError("density_curves_layers must have shape Kx3x3")
    if density_curves_layers_np.shape[0] != density_curves_np.shape[0]:
        raise ValueError("density_curves and density_curves_layers must have the same length")
    if density_cmy.shape[-1] != 3:
        raise ValueError("density_cmy must have 3 channels in the last dimension")

    mx = backend.mx
    values = backend.asarray(density_cmy)
    x_axis = density_curves_np
    if positive_film:
        values = -values
        x_axis = -x_axis

    x_axis_mx = mx.array(x_axis, dtype=mx.float32)
    y_vals_mx = mx.array(density_curves_layers_np, dtype=mx.float32)
    output_shape = density_cmy.shape[:-1] + density_curves_layers_np.shape[1:]
    kernel = _get_interp_density_layers_kernel(mx)
    outputs = kernel(
        inputs=[values, x_axis_mx, y_vals_mx],
        template=[("T", values.dtype)],
        grid=(int(np.prod(output_shape)), 1, 1),
        threadgroup=(256, 1, 1),
        output_shapes=[output_shape],
        output_dtypes=[values.dtype],
    )
    return outputs[0]


def compute_density_spectral(
    channel_density: Any,
    density_cmy: Any,
    base_density: Any | None,
    backend,
) -> Any:
    """``density_spectral = density_cmy @ channel_density.T [+ base_density]``

    Parameters
    ----------
    channel_density : array  shape ``(K, 3)``
        Per-wavelength dye densities for the three channels.
    density_cmy : array  shape ``(H, W, 3)``
        Per-pixel CMY density values.
    base_density : array  shape ``(K,)`` or ``None``
        Additive base (fog) density.
    backend : ArrayBackend

    Returns
    -------
    density_spectral : array  shape ``(H, W, K)``
    """
    # einsum 'ijk, lk -> ijl'  ⟺  matmul(density_cmy, channel_density.T)
    density_spectral = backend.einsum("ijk,lk->ijl", density_cmy, channel_density)
    if base_density is not None:
        density_spectral = density_spectral + base_density
    return density_spectral


def density_to_light(
    density_spectral: Any,
    illuminant: Any,
    backend,
) -> Any:
    """``light = 10^(-density) * illuminant``

    Parameters
    ----------
    density_spectral : array  shape ``(H, W, K)``
    illuminant : array  shape ``(K,)``
    backend : ArrayBackend

    Returns
    -------
    light : array  shape ``(H, W, K)``
    """
    transmitted = backend.power(10.0, -density_spectral)
    transmitted = transmitted * illuminant
    transmitted = backend.nan_to_num(transmitted, nan=0.0)
    return transmitted


def light_to_raw(
    light: Any,
    sensitivity: Any,
    backend,
) -> Any:
    """``raw = light @ sensitivity``  — contract over wavelength.

    Parameters
    ----------
    light : array  shape ``(H, W, K)``
    sensitivity : array  shape ``(K, C)``  (C = 3 for CMY/XYZ)
    backend : ArrayBackend

    Returns
    -------
    raw : array  shape ``(H, W, C)``
    """
    return backend.einsum("ijk,kl->ijl", light, sensitivity)


def cmy_to_log_xyz_backend(
    density_cmy: Any,
    channel_density: Any,
    base_density: Any,
    scan_illuminant: Any,
    cmfs: Any,
    normalization: float,
    backend,
) -> Any:
    """Full CMY → log₁₀(XYZ) chain on the backend.

    This is the backend-portable equivalent of the closure built by
    ``ScanningStage._return_callable_cmy_to_log_xyz``.
    """
    channel_density = backend.asarray(channel_density)
    scan_illuminant = backend.asarray(scan_illuminant)
    cmfs = backend.asarray(cmfs)
    if base_density is not None:
        base_density = backend.asarray(base_density)

    density_spectral = compute_density_spectral(
        channel_density, density_cmy, base_density, backend,
    )
    light = density_to_light(density_spectral, scan_illuminant, backend)
    xyz = light_to_raw(light, cmfs, backend) / normalization
    # log10(max(xyz, 0) + 1e-10)
    xyz_safe = backend.fmax(xyz, 0.0) + 1e-10
    return backend.log10(xyz_safe)
