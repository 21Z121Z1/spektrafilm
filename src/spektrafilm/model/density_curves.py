import numpy as np
from spektrafilm.utils.fast_interp import fast_interp

################################################################################
# Denstity curves
################################################################################

def interpolate_exposure_to_density(log_exposure_rgb, density_curves, log_exposure, gamma_factor):
    """
    Interpolates the exposure values to density values using the provided density curves.
    Parameters:
    log_exposure_rgb (numpy.ndarray): A 3D array of shape (height, width, 3) representing the log10 RGB exposure values.
    density_curves (numpy.ndarray): A 2D array of shape (num_points, 3) representing the density curves for each channel.
    log_exposure (numpy.ndarray): A 1D array of logarithmic exposure values.
    gamma_factor (float): The gamma correction factor to be applied to the density characteristic curves.
    Returns:
    numpy.ndarray: A 3D array of shape (height, width, 3) representing the interpolated density values in CMY channels.
    """
    if np.size(gamma_factor)==1:
        gamma_factor = [gamma_factor, gamma_factor, gamma_factor]
    gamma_factor = np.array(gamma_factor)
    density_cmy = fast_interp(np.ascontiguousarray(log_exposure_rgb),
                              log_exposure[:,None]/gamma_factor[None,:],
                              density_curves)
    return density_cmy


def _interp_density_cmy_layers_cpu(density_cmy, density_curves, density_curves_layers, positive_film=False):
    density_cmy_layers = np.zeros((density_cmy.shape[0], density_cmy.shape[1], 3, 3)) # x,y,layer,rgb
    if positive_film:
        for ch in np.arange(3):
            density_cmy_layers[:,:,:,ch] = fast_interp(-np.repeat(density_cmy[:,:,ch,np.newaxis], 3, -1),
                                                       -density_curves[:,ch], density_curves_layers[:,:,ch])
    else:
        for ch in np.arange(3):
            density_cmy_layers[:,:,:,ch] = fast_interp(np.repeat(density_cmy[:,:,ch,np.newaxis], 3, -1),
                                                       density_curves[:,ch], density_curves_layers[:,:,ch])
    return density_cmy_layers


def interp_density_cmy_layers(
    density_cmy,
    density_curves,
    density_curves_layers,
    positive_film=False,
    backend=None,
):
    if backend is not None and getattr(backend, "supports_gpu", False):
        from spektrafilm.gpu.kernels.density import interpolate_density_cmy_layers_backend

        return interpolate_density_cmy_layers_backend(
            density_cmy,
            density_curves,
            density_curves_layers,
            positive_film=positive_film,
            backend=backend,
        )
    return _interp_density_cmy_layers_cpu(
        density_cmy,
        density_curves,
        density_curves_layers,
        positive_film=positive_film,
    )

