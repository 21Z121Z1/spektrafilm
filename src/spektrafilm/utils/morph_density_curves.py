from dataclasses import dataclass

import numpy as np
from scipy.stats import norm as _norm_dist

from spektrafilm.profiles.io import DensityCurvesModel


__all__ = ["PrintCurvesMorphParams", "apply_print_curves_morph"]


SIGMA_FLOOR = 0.05


@dataclass(frozen=True)
class PrintCurvesMorphParams:
    """User-facing controls for the s022 print density-curve morph."""

    active: bool = True
    gamma_factor: float = 1.0
    fast_uniformity: float = 1.0
    mid_uniformity: float = 1.0
    slow_uniformity: float = 1.0
    fast_warmth: float = 0.0
    fast_tint: float = 0.0
    mid_warmth: float = 0.0
    mid_tint: float = 0.0
    slow_warmth: float = 0.0
    slow_tint: float = 0.0


def _signed_z(z, profile_type):
    return -z if profile_type == "positive" else z


def _layer_cdf(z, profile_type):
    return _norm_dist.cdf(_signed_z(z, profile_type))


def _evaluate_channel_density(log_exposure, centers_c, amplitudes_c, sigmas_c, profile_type):
    x = np.asarray(log_exposure, dtype=float)
    centers_c = np.asarray(centers_c, dtype=float)
    amplitudes_c = np.asarray(amplitudes_c, dtype=float)
    sigmas_c = np.asarray(sigmas_c, dtype=float)

    total = np.zeros(x.size, dtype=float)
    for i in range(centers_c.size):
        z = (x - centers_c[i]) / sigmas_c[i]
        total += amplitudes_c[i] * _layer_cdf(z, profile_type)
    return total


def _evaluate_fitted_density(log_exposure, density_curves_model, profile_type):
    log_exposure = np.asarray(log_exposure, dtype=float)
    model = density_curves_model
    n_channels = model.centers.shape[0]
    fitted = np.empty((log_exposure.size, n_channels), dtype=float)

    for channel_idx in range(n_channels):
        fitted[:, channel_idx] = _evaluate_channel_density(
            log_exposure,
            model.centers[channel_idx],
            model.amplitudes[channel_idx],
            model.sigmas[channel_idx],
            profile_type,
        )

    return fitted


def _speed_layer_indices(centers_c):
    """Return (i_fast, i_mid, i_slow) by ascending center."""
    order = np.argsort(np.asarray(centers_c, dtype=float))
    n = len(order)
    return int(order[0]), int(order[n // 2]), int(order[-1])


def _morph_channel_params(model, params, channel_idx):
    centers_c = np.asarray(model.centers[channel_idx], dtype=float).copy()
    amplitudes_c = np.asarray(model.amplitudes[channel_idx], dtype=float).copy()
    sigmas_c = np.asarray(model.sigmas[channel_idx], dtype=float).copy()

    i_fast, i_mid, i_slow = _speed_layer_indices(centers_c)

    fast_rgb_offset = np.array(
        [params.fast_warmth, params.fast_tint, -params.fast_warmth],
        dtype=float,
    )
    mid_rgb_offset = np.array(
        [params.mid_warmth, params.mid_tint, -params.mid_warmth],
        dtype=float,
    )
    slow_rgb_offset = np.array(
        [params.slow_warmth, params.slow_tint, -params.slow_warmth],
        dtype=float,
    )

    gamma_factor = float(params.gamma_factor)
    g_fast = gamma_factor * (float(params.fast_uniformity) + float(fast_rgb_offset[channel_idx]))
    g_mid = gamma_factor * (float(params.mid_uniformity) + float(mid_rgb_offset[channel_idx]))
    g_slow = gamma_factor * (float(params.slow_uniformity) + float(slow_rgb_offset[channel_idx]))

    if g_fast <= 0.0 or g_mid <= 0.0 or g_slow <= 0.0:
        raise ValueError(
            "Effective gamma must remain strictly positive per channel "
            f"(channel {channel_idx}: fast={g_fast:.3f}, mid={g_mid:.3f}, slow={g_slow:.3f})."
        )

    sigmas_c[i_fast] = max(sigmas_c[i_fast] / g_fast, SIGMA_FLOOR)
    centers_c[i_fast] = centers_c[i_fast] / g_fast
    sigmas_c[i_mid] = max(sigmas_c[i_mid] / g_mid, SIGMA_FLOOR)
    centers_c[i_mid] = centers_c[i_mid] / g_mid
    sigmas_c[i_slow] = max(sigmas_c[i_slow] / g_slow, SIGMA_FLOOR)
    centers_c[i_slow] = centers_c[i_slow] / g_slow

    return centers_c, amplitudes_c, sigmas_c


def apply_print_curves_morph(
    log_exposure,
    density_curves_model: DensityCurvesModel,
    morph_params,
    *,
    profile_type="positive",
):
    """Apply the s022 coupled gamma morph from explicit print-curve inputs."""
    if not morph_params.active:
        return _evaluate_fitted_density(log_exposure, density_curves_model, profile_type)

    model = density_curves_model
    if model.n_layers == 0:
        raise NotImplementedError("s022 morph requires a fitted density_curves_model.")

    for gamma_name, value in [
        ("gamma_factor", morph_params.gamma_factor),
        ("fast_uniformity", morph_params.fast_uniformity),
        ("mid_uniformity", morph_params.mid_uniformity),
        ("slow_uniformity", morph_params.slow_uniformity),
    ]:
        if value <= 0.0:
            raise ValueError(f"{gamma_name} must be strictly positive (got {value}).")

    log_exposure = np.asarray(log_exposure, dtype=float)
    n_channels = model.centers.shape[0]
    morphed = np.empty((log_exposure.size, n_channels), dtype=float)

    for channel_idx in range(n_channels):
        centers_c, amplitudes_c, sigmas_c = _morph_channel_params(model, morph_params, channel_idx)
        morphed[:, channel_idx] = _evaluate_channel_density(
            log_exposure,
            centers_c,
            amplitudes_c,
            sigmas_c,
            profile_type,
        )

    return morphed