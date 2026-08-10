from copy import deepcopy

import numpy as np

from spektrafilm.runtime.services.spectral_lut_compute import SpectralLUTService
from spektrafilm.utils.spectral_reflectance import compute_reflectance_tc_lut
from spektrafilm.utils.spectral_upsampling import (
    HANATOS2025_NO_ADAPTATION,
    compute_hanatos2025_tc_lut,
)
from spektrafilm_gui.options import RGBtoRAWMethod


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


def _hanatos_adaptation():
    adaptation = deepcopy(HANATOS2025_NO_ADAPTATION)
    adaptation.reference_illuminant = "D55"
    return adaptation


def test_gui_exposes_arctic_without_changing_default_enum_order_contract():
    assert RGBtoRAWMethod.hanatos2025.value == "hanatos2025"
    assert RGBtoRAWMethod.arctic2026beta04.value == "arctic2026beta04"
    assert RGBtoRAWMethod.mallett2019.value == "mallett2019"


def test_filming_lut_service_preserves_legacy_hanatos_call_exactly():
    sensitivity = _synthetic_sensitivity()
    adaptation = _hanatos_adaptation()
    service = SpectralLUTService(lut_resolution=17)
    service.set_hanatos2025_adaptation(adaptation)

    expected = compute_hanatos2025_tc_lut(
        sensitivity,
        adaptation,
        gamut_compress=service.input_gamut_compress,
    )
    actual = service.get_filming_tc_lut(sensitivity)
    np.testing.assert_array_equal(actual, expected)


def test_filming_lut_service_builds_and_caches_arctic_by_reference_illuminant():
    sensitivity = _synthetic_sensitivity()
    service = SpectralLUTService(lut_resolution=17)
    service.set_hanatos2025_adaptation(_hanatos_adaptation())

    d55 = service.get_filming_tc_lut(
        sensitivity,
        method="arctic2026beta04",
        reference_illuminant="D55",
    )
    expected_d55 = compute_reflectance_tc_lut(
        "arctic2026beta04",
        sensitivity,
        "D55",
        gamut_compress=service.input_gamut_compress,
    )
    np.testing.assert_array_equal(d55, expected_d55)

    cached_d55 = service.get_filming_tc_lut(
        sensitivity,
        method="arctic2026beta04",
        reference_illuminant="D55",
    )
    assert cached_d55 is d55

    d65 = service.get_filming_tc_lut(
        sensitivity,
        method="arctic2026beta04",
        reference_illuminant="D65",
    )
    assert d65 is not d55
    assert not np.array_equal(d65, d55)


def test_switching_spectral_methods_does_not_reuse_wrong_cached_lut():
    sensitivity = _synthetic_sensitivity()
    service = SpectralLUTService(lut_resolution=17)
    service.set_hanatos2025_adaptation(_hanatos_adaptation())

    hanatos_before = service.get_filming_tc_lut(sensitivity)
    arctic = service.get_filming_tc_lut(
        sensitivity,
        method="arctic2026beta04",
        reference_illuminant="D55",
    )
    hanatos_after = service.get_filming_tc_lut(sensitivity)

    assert arctic is not hanatos_before
    np.testing.assert_array_equal(hanatos_after, hanatos_before)
