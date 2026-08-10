import numpy as np

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


def test_arctic_descriptor_and_asset_contract():
    assert "arctic2026beta04" in available_spectral_luts("reflectance")
    descriptor = spectral_lut_descriptor("arctic2026beta04")
    assert descriptor["kind"] == "reflectance"
    assert descriptor["array"]["spectral_shape"] == [380, 780, 5]
    assert descriptor["reflectance"]["scene_illuminant"] == "D65"

    spectra = get_spectral_lut_spectra("arctic2026beta04")
    assert spectra.shape == (192, 192, 81)
    assert spectra.dtype == np.float64
    assert np.isfinite(spectra).all()


def test_arctic_relight_preserves_method_neutral():
    raw_lut = compute_reflectance_tc_lut(
        "arctic2026beta04",
        _synthetic_sensitivity(),
        "D55",
    )
    d65_tc = _tri2quad(_illuminant_to_xy("D65"))
    neutral = apply_lut_cubic_2d(
        raw_lut,
        np.asarray(d65_tc).reshape(1, 1, 2),
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
