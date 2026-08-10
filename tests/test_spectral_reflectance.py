import numpy as np
import pytest

from spektrafilm.utils.fast_interp_lut import apply_lut_cubic_2d
from spektrafilm.utils.spectral_lut_registry import (
    available_spectral_luts,
    spectral_lut_descriptor,
)
from spektrafilm.utils.spectral_reflectance import (
    compute_reflectance_tc_lut,
    compute_spectral_tc_lut,
    get_spectral_lut_spectra,
)
from spektrafilm.utils.spectral_upsampling import (
    HANATOS2025_NO_ADAPTATION,
    _illuminant_to_xy,
    _tri2quad,
    compute_hanatos2025_tc_lut,
)


_REFLECTANCE_METHODS = (
    "arctic2026beta04",
    "jakob2019",
    "otsu2018",
    "gauss-lasers",
)


def _synthetic_sensitivity():
    wavelengths = np.linspace(0.0, 1.0, 81)
    return np.stack(
        (
            0.4 + wavelengths,
            0.7 + 0.2 * np.cos(wavelengths * np.pi),
            1.2 - 0.5 * wavelengths,
        ),
        axis=-1,
    )


@pytest.mark.parametrize("method", _REFLECTANCE_METHODS)
def test_reflectance_descriptor_and_asset_contract(method):
    assert method in available_spectral_luts("reflectance")
    descriptor = spectral_lut_descriptor(method)
    assert descriptor["kind"] == "reflectance"
    assert descriptor["array"]["lut_size"] == 192
    assert descriptor["array"]["bands"] == 81
    assert descriptor["array"]["spectral_shape"] == [380, 780, 5]
    assert descriptor["reflectance"]["scene_illuminant"] == "D65"

    spectra = get_spectral_lut_spectra(method)
    assert spectra.shape == (192, 192, 81)
    assert spectra.dtype == np.float64
    assert np.isfinite(spectra).all()


@pytest.mark.parametrize("method", _REFLECTANCE_METHODS)
def test_reflectance_relight_preserves_method_neutral(method):
    raw_lut = compute_reflectance_tc_lut(
        method,
        _synthetic_sensitivity(),
        "D55",
    )
    descriptor = spectral_lut_descriptor(method)
    scene_tc = _tri2quad(
        _illuminant_to_xy(descriptor["reflectance"]["scene_illuminant"])
    )
    neutral = apply_lut_cubic_2d(
        raw_lut,
        np.asarray(scene_tc).reshape(1, 1, 2),
    )[0, 0]
    np.testing.assert_allclose(neutral, np.ones(3), rtol=2e-6, atol=2e-6)


def test_generic_hanatos_dispatch_is_exactly_existing_path():
    sensitivity = _synthetic_sensitivity()
    expected = compute_hanatos2025_tc_lut(
        sensitivity,
        HANATOS2025_NO_ADAPTATION,
    )
    actual = compute_spectral_tc_lut(
        "hanatos2025",
        sensitivity,
        reference_illuminant="D55",
    )
    np.testing.assert_array_equal(actual, expected)
