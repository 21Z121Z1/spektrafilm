import numpy as np
import colour
from enum import Enum
from spektrafilm.config import SPECTRAL_SHAPE
from spektrafilm.model.color_filters import schott_kg3_heat_filter, generic_lens_transmission


class Illuminants(Enum):
    lamp = 'TH-KG3' # tungsten halogen with heat filter
    # bulb = 'T'
    # cine = 'K75P'
    # led_rgb = 'LED-RGB1'

def black_body_spectrum(temperature: float) -> colour.SpectralDistribution:
    values = colour.colorimetry.blackbody_spectral_radiance(SPECTRAL_SHAPE.wavelengths*1e-9, temperature) # to emulate an halogen lamp
    spectral_intensity = colour.SpectralDistribution(values, domain=SPECTRAL_SHAPE)
    return spectral_intensity

def standard_illuminant(type: str = 'D65', return_class: bool = False) -> colour.SpectralDistribution | np.ndarray:
    if type[0:2]=='BB':
        temperature = np.double(type[2:])
        spectral_intensity = black_body_spectrum(temperature)
    elif type=='T':
        spectral_intensity = colour.SDS_LIGHT_SOURCES['Incandescent'].copy().align(SPECTRAL_SHAPE)
    elif type=='K75P':
        spectral_intensity = colour.SDS_LIGHT_SOURCES['Kinoton 75P'].copy().align(SPECTRAL_SHAPE)
    elif type=='TH-KG3':
        if schott_kg3_heat_filter is None:
            raise RuntimeError("TH-KG3 illuminant requires filter data files that are not installed.")
        spectral_intensity = black_body_spectrum(3400)
        spectral_intensity.values = schott_kg3_heat_filter.apply(spectral_intensity.values)
    elif type=='TH-KG3-L': # enlarger source with heat filter and lens transmittance
        if schott_kg3_heat_filter is None or generic_lens_transmission is None:
            raise RuntimeError("TH-KG3-L illuminant requires filter data files that are not installed.")
        spectral_intensity = black_body_spectrum(3400)
        spectral_intensity.values = schott_kg3_heat_filter.apply(spectral_intensity.values)
        spectral_intensity.values = generic_lens_transmission.apply(spectral_intensity.values)
    else:
        try:
            spectral_intensity = colour.SDS_ILLUMINANTS[type].copy().align(SPECTRAL_SHAPE)
        except KeyError:
            available = sorted(colour.SDS_ILLUMINANTS.keys())
            raise ValueError(
                f"Unknown illuminant type {type!r}. Available standard illuminants: {available}"
            ) from None
    spectral_intensity.name = type
    # normalization
    normalization = np.sum(spectral_intensity.values) / np.size(SPECTRAL_SHAPE.wavelengths)
    spectral_intensity.values = spectral_intensity.values / normalization
    
    if return_class:
        return spectral_intensity
    else:
        return spectral_intensity[:]


if __name__=="__main__":
    import matplotlib.pyplot as plt
    ill = standard_illuminant('TH-KG3', return_class=True)
    ill_bb = standard_illuminant('BB3400', return_class=True)
    print(ill[:])
    plt.plot(ill.wavelengths, ill.values)
    plt.plot(ill_bb.wavelengths, ill_bb.values)
    plt.show()


