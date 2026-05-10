from typing import Literal, TypeAlias

import numpy as np
from numpy.typing import NDArray
from opt_einsum import contract
from spektrafilm.model.couplers import apply_density_correction_dir_couplers
from spektrafilm.model.grain import apply_grain
from spektrafilm.gpu.kernels.density import interpolate_exposure_to_density_backend
from spektrafilm.runtime.params_schema import DirCouplersParams, GrainParams


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
    backend=None,
):
    density_cmy = interpolate_exposure_to_density_backend(
        log_raw,
        log_exposure,
        density_curves,
        gamma_factor,
        backend=backend,
    )
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
    backend=None,
) -> FloatArray:
    density_curves = np.asarray(density_curves)
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
    if backend is not None and backend.supports_gpu and (not grain.active or bypass_grain):
        return density_cmy
    if backend is not None and backend.supports_gpu:
        density_cmy = backend.to_numpy(density_cmy)
    return apply_grain(
        density_cmy,
        pixel_size_um,
        grain,
        normalized_density_curves,
        density_curves_layers,
        profile_type,
        bypass_grain=bypass_grain,
        use_fast_stats=use_fast_stats,
    )

# Some future work notes:
# Add print dye shift in nanometers for dye absorption peaks.
# Investigate how density curves change with development conditions.
# Add a gray card border to check white balance.

if __name__ == '__main__':
    pass
