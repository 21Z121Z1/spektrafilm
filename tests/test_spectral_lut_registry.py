from spektrafilm.utils.spectral_lut_registry import (
    available_spectral_luts,
    spectral_lut_descriptor,
    spectral_lut_resource,
)


def test_existing_hanatos_lut_is_registered():
    assert "hanatos2025" in available_spectral_luts()
    assert available_spectral_luts(kind="irradiance") == ("hanatos2025",)


def test_hanatos_descriptor_matches_existing_asset_contract():
    descriptor = spectral_lut_descriptor("hanatos2025")
    assert descriptor["kind"] == "irradiance"
    assert descriptor["file"] == "irradiance_xy_tc.npy"
    assert descriptor["array"]["spectral_shape"] == [380, 780, 5]
    assert spectral_lut_resource("hanatos2025").is_file()


def test_unknown_identifier_fails_explicitly():
    try:
        spectral_lut_descriptor("not-a-real-method")
    except KeyError as exc:
        assert "hanatos2025" in str(exc)
    else:
        raise AssertionError("unknown spectral LUT identifier must raise KeyError")
