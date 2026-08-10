from typing import Literal, TypeAlias

import numpy as np
from numpy.typing import NDArray
from opt_einsum import contract
from scipy.ndimage import gaussian_filter1d

from spektrafilm.config import SPECTRAL_SHAPE
from spektrafilm.model.couplers import apply_density_correction_dir_couplers
from spektrafilm.model.density_curves import interpolate_exposure_to_density
from spektrafilm.model.grain import apply_grain
from spektrafilm.profiles.io import DensityCurvesModel
from spektrafilm.runtime.params_schema import DirCouplersParams, FilmBaseParams, GrainParams
from spektrafilm.gpu.kernels.density import interpolate_exposure_to_density_backend
from spektrafilm.utils.morph_curves import apply_print_curves_morph, PrintCurvesMorphParams

FloatArray: TypeAlias = NDArray[np.float64]
ProfileType: TypeAlias = Literal['negative', 'positive']

################################################################################
# Emulsion helpers

def base_film_density_tuning(
    base_density,
    base_density_params: FilmBaseParams | None,
):
    """Return the film base after optional spectral-shape tuning.

    This follows the current upstream experimental Status-M interpolation and
    tilt model, with one intentional correction: the global ``scale`` is
    applied exactly once. Upstream currently multiplies scale inside its film
    shaping helper and again in the shared wrapper for non-neutral CMY/tilt,
    which makes the effective control ``scale**2`` whenever shaping is active.

    Neutral CMY (all 1.0), zero tilt and scale 1.0 are an exact identity.
    The input array is never modified in place.
    """
    if base_density is None:
        return None

    base = np.asarray(base_density)
    if base_density_params is None or not base_density_params.active:
        return base

    cmy_neutral = (
        base_density_params.cyan,
        base_density_params.magenta,
        base_density_params.yellow,
    ) == (1.0, 1.0, 1.0)
    tilt_neutral = base_density_params.tilt == 0.0

    if cmy_neutral and tilt_neutral:
        shaped = base
    else:
        wavelengths = SPECTRAL_SHAPE.wavelengths
        status_m_max_peaks = [460.0, 555.0, 650.0]
        sigma_nm = 35.0
        sigma_points = sigma_nm / np.mean(np.diff(wavelengths))

        # Status-M order along wavelength is Y, M, C. Values of 1.0 are
        # neutral multipliers; smoothing produces a continuous spectral scale.
        density_scale_channels = [
            base_density_params.yellow,
            base_density_params.magenta,
            base_density_params.cyan,
        ]
        spectral_density_scale = np.interp(
            wavelengths,
            status_m_max_peaks,
            density_scale_channels,
        )
        density_scale = gaussian_filter1d(spectral_density_scale, sigma_points)

        # ``tilt`` is defined as the density multiplier delta at 650 nm
        # relative to the 555 nm pivot: +0.1 -> multiplier 1.1 at 650 nm.
        tilt_slope = base_density_params.tilt / (650.0 - 555.0)
        density_tilt = tilt_slope * (wavelengths - 555.0) + 1.0
        density_tilt = np.clip(density_tilt, 0.0, np.inf)
        density_tilt = gaussian_filter1d(density_tilt, sigma_points)

        shaped = base * density_scale * density_tilt

    return shaped * base_density_params.scale


def _tuned_base_density(base_density, base_density_params=None, is_film=False):
    """Apply film-base tuning while preserving legacy behavior elsewhere."""
    if base_density is None:
        return None
    if is_film:
        return base_film_density_tuning(base_density, base_density_params)
    return np.asarray(base_density)


def compute_density_spectral(
    channel_density,
    density_cmy,
    base_density=None,
    base_density_params=None,
    is_film=False,
):
    density_spectral = contract('ijk, lk->ijl', density_cmy, np.asarray(channel_density))
    if base_density is not None:
        density_spectral += _tuned_base_density(
            base_density,
            base_density_params,
            is_film=is_film,
        )
    return density_spectral


# Keep black/white reference correction anchored to the stock density curves.
# Creative print-curve morphing belongs in develop_print_morph().
def develop_simple(
    log_raw,
    log_exposure,
    density_curves,
    gamma_factor=1.0,
    *,
    backend=None,
):
    if backend is not None and getattr(backend, "supports_gpu", False):
        density_cmy = interpolate_exposure_to_density_backend(
            log_raw, log_exposure, density_curves, gamma_factor, backend,
        )
    else:
        density_cmy = interpolate_exposure_to_density(log_raw, density_curves, log_exposure, gamma_factor)
    return density_cmy

def develop(
    log_raw: FloatArray,
    pixel_size_um: float,
    log_exposure: FloatArray,
    density_curves: FloatArray,
    density_curves_layers: FloatArray,
    dir_couplers: DirCouplersParams,
    grain: GrainParams,
    profile_type: ProfileType,
    gamma_factor: float = 1.0,
    bypass_grain: bool = False,
    use_fast_stats: bool = False,
    *,
    backend=None,
    settings=None,
) -> FloatArray:
    density_curves = np.asarray(density_curves)
    if density_curves.ndim != 2 or density_curves.shape[1] != 3:
        raise ValueError(f"density_curves must have shape (n, 3), got {density_curves.shape}")
    missing_channels = np.where(np.all(np.isnan(density_curves), axis=0))[0]
    if missing_channels.size:
        channels = ", ".join(str(int(ch)) for ch in missing_channels)
        raise ValueError(f"density_curves has all-NaN data in channel {channels}")
    normalized_density_curves = density_curves - np.nanmin(density_curves, axis=0)

    density_cmy = develop_simple(
        log_raw,
        log_exposure,
        normalized_density_curves,
        gamma_factor=gamma_factor,
        backend=backend,
    )

    density_cmy = apply_density_correction_dir_couplers(
        density_cmy,
        log_raw,
        pixel_size_um,
        log_exposure,
        normalized_density_curves,
        dir_couplers,
        profile_type,
        gamma_factor=gamma_factor,
        backend=backend,
    )
    density_cmy = apply_grain(
        density_cmy,
        pixel_size_um,
        grain,
        normalized_density_curves,
        density_curves_layers,
        profile_type,
        bypass_grain=bypass_grain,
        use_fast_stats=use_fast_stats,
        backend=backend,
        settings=settings,
    )

    return density_cmy


def develop_print_morph(
    log_raw: FloatArray,
    log_exposure: FloatArray,
    density_curves_model: DensityCurvesModel,
    density_curves_morph: PrintCurvesMorphParams,
    profile_type: ProfileType = 'negative',
):
    density_curves_morphed = apply_print_curves_morph(
        log_exposure,
        density_curves_model,
        density_curves_morph,
        profile_type=profile_type,
    )
    density_cmy = interpolate_exposure_to_density(
        log_raw,
        density_curves_morphed,
        log_exposure,
        gamma_factor=1.0,
    )
    return density_cmy


# Some future work notes:
# Add print dye shift in nanometers for dye absorption peaks.
# Investigate how density curves change with development conditions.
# Add a gray card border to check white balance.

if __name__ == '__main__':
    pass
