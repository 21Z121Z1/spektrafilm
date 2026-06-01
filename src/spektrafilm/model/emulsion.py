from typing import Literal, TypeAlias

import numpy as np
from numpy.typing import NDArray
from opt_einsum import contract
from spektrafilm.model.couplers import apply_density_correction_dir_couplers
from spektrafilm.model.density_curves import interpolate_exposure_to_density
from spektrafilm.model.grain import apply_grain
from spektrafilm.runtime.params_schema import DirCouplersParams, GrainParams
from spektrafilm.gpu.kernels.density import interpolate_exposure_to_density_backend


FloatArray: TypeAlias = NDArray[np.float64]
ProfileType: TypeAlias = Literal['negative', 'positive']

################################################################################
# Emulsion helpers

def compute_density_spectral(
    channel_density,
    density_cmy,
    base_density=None,
):
    density_spectral = contract('ijk, lk->ijl', density_cmy, np.asarray(channel_density))
    if base_density is not None:
        density_spectral += np.asarray(base_density)
    return density_spectral

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
    )

    return density_cmy

# Some future work notes:
# Add print dye shift in nanometers for dye absorption peaks.
# Investigate how density curves change with development conditions.
# Add a gray card border to check white balance.

if __name__ == '__main__':
    pass
