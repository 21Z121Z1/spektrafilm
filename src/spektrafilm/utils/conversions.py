import numpy as np
import colour

from spektrafilm.config import SPECTRAL_SHAPE

def density_to_light(density: np.ndarray, light: np.ndarray) -> np.ndarray:
    """
    Convert density to light transmittance.

    This function calculates the light transmittance based on the given density
    and light intensity. It uses the formula transmittance = 10^(-density) to 
    compute the transmittance and then multiplies it by the light intensity.

    Parameters:
    density (float or np.ndarray): The density value(s) which affect the light transmittance.
    light (float or np.ndarray): The initial light intensity value(s).

    Returns:
    np.ndarray: The light intensity after passing through the medium with the given density.
    """
    transmitted = 10**(-density)
    transmitted *= light
    transmitted[np.isnan(transmitted)] = 0
    return transmitted

def compute_aces_conversion_matrix(sensitivity: np.ndarray, illuminant: np.ndarray) -> np.ndarray:            
    """
    Computes the ACES (Academy Color Encoding System) conversion matrix.

    Parameters
    ----------
    sensitivity : array-like
        The spectral sensitivity data.
    illuminant : array-like
        The illuminant spectral distribution.

    Returns
    -------
    numpy.ndarray
        The ACES to raw conversion matrix.
    """
    msds = colour.MultiSpectralDistributions(sensitivity, domain=SPECTRAL_SHAPE.wavelengths)
    M, _ = colour.matrix_idt(msds, illuminant)
    aces_to_raw_conversion_matrix = np.linalg.inv(M)
    return aces_to_raw_conversion_matrix
