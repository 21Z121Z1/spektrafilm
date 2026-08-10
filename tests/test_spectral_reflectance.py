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
    rgb_to_raw_reflectance,
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
    assert descriptor["reflectance"]["midgray"] == pytest.approx(0.184)

    spectra = get_spectral_lut_spectra(method)
    assert spectra.shape == (192, 192, 81)
    assert spectra.dtype == np.float64
    assert np.isfinite(spectra).all()


@pytest.mark.parametrize("method", _REFLECTANCE_METHODS)
def test_reflectance_lut_neutral_keeps_chroma_and_midgray_anchor(method):
    sensitivity = _synthetic_sensitivity()
    descriptor = spectral_lut_descriptor(method)
    reflectance = descriptor["reflectance"]
    scene_xy = _illuminant_to_xy(reflectance["scene_illuminant"])
    scene_tc = _tri2quad(scene_xy)

    raw_lut = compute_reflectance_tc_lut(method, sensitivity, "D55")
    neutral_lut_value = apply_lut_cubic_2d(
        raw_lut,
        np.asarray(scene_tc).reshape(1, 1, 2),
    )[0, 0]
    expected_anchor = float(scene_xy[1]) / float(reflectance["midgray"])
    np.testing.assert_allclose(
        neutral_lut_value,
        np.full(3, expected_anchor),
        rtol=2e-6,
        atol=2e-6,
    )

    midgray = np.full((1, 1, 3), float(reflectance["midgray"]), dtype=np.float64)
    raw = rgb_to_raw_reflectance(
        method,
        midgray,
        sensitivity,
        color_space="sRGB",
        apply_cctf_decoding=False,
        reference_illuminant="D55",
        tc_lut=raw_lut,
    )
    np.testing.assert_allclose(raw[0, 0], np.ones(3), rtol=3e-6, atol=3e-6)


def test_reflectance_midgray_anchor_is_channel_generic_for_bw():
    method = "arctic2026beta04"
    sensitivity = _synthetic_sensitivity()[:, :1]
    descriptor = spectral_lut_descriptor(method)
    midgray_value = float(descriptor["reflectance"]["midgray"])
    raw_lut = compute_reflectance_tc_lut(method, sensitivity, "D55")

    raw = rgb_to_raw_reflectance(
        method,
        np.full((1, 1, 3), midgray_value, dtype=np.float64),
        sensitivity,
        color_space="sRGB",
        apply_cctf_decoding=False,
        reference_illuminant="D55",
        tc_lut=raw_lut,
    )
    assert raw.shape == (1, 1, 1)
    np.testing.assert_allclose(raw[0, 0], np.ones(1), rtol=3e-6, atol=3e-6)


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
