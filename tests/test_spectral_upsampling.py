import numpy as np
import pytest

from spektrafilm.utils import spectral_upsampling as spectral_upsampling_module
from spektrafilm.utils.spectral_upsampling import SpectralInputPolicy


pytestmark = pytest.mark.unit


def test_rgb_to_raw_hanatos2025_computes_tc_lut_when_missing(monkeypatch):
    sensitivity = np.array(
        [
            [1.0, 2.0, 3.0],
            [2.0, 3.0, 4.0],
            [3.0, 4.0, 5.0],
            [4.0, 5.0, 6.0],
        ],
        dtype=np.float64,
    )
    rgb = np.zeros((2, 3, 3), dtype=np.float64)

    def fake_rgb_to_tc_b(data, **_kwargs):
        tc = np.zeros(data.shape[:-1] + (2,), dtype=np.float64)
        if data.shape == (1, 1, 3):
            scale = np.ones((1, 1), dtype=np.float64)
        else:
            scale = np.full(data.shape[:-1], 2.0, dtype=np.float64)
        return tc, scale

    lut_calls = []

    def fake_compute_hanatos2025_tc_lut(arg_sensitivity):
        lut_calls.append(arg_sensitivity.copy())
        return np.zeros((2, 2, 3), dtype=np.float64)

    def fake_apply_lut_cubic_2d(_tc_lut, tc):
        lut_raw = np.empty(tc.shape[:-1] + (3,), dtype=np.float64)
        lut_raw[..., 0] = 2.0
        lut_raw[..., 1] = 4.0
        lut_raw[..., 2] = 6.0
        return lut_raw

    monkeypatch.setattr(spectral_upsampling_module, '_rgb_to_tc_b', fake_rgb_to_tc_b)
    monkeypatch.setattr(spectral_upsampling_module, 'compute_hanatos2025_tc_lut', fake_compute_hanatos2025_tc_lut)
    monkeypatch.setattr(spectral_upsampling_module, 'apply_lut_cubic_2d', fake_apply_lut_cubic_2d)

    raw = spectral_upsampling_module.rgb_to_raw_hanatos2025(
        rgb,
        sensitivity,
        color_space='sRGB',
        apply_cctf_decoding=False,
        reference_illuminant='D65',
    )

    assert len(lut_calls) == 1
    np.testing.assert_allclose(lut_calls[0], sensitivity)
    expected = np.empty_like(raw)
    expected[..., 0] = 4.0
    expected[..., 1] = 8.0
    expected[..., 2] = 12.0
    assert raw.shape == (2, 3, 3)
    np.testing.assert_allclose(raw, expected)


def test_rgb_to_raw_hanatos2025_lut_path_supports_image_rgb(monkeypatch):
    sensitivity = np.array(
        [
            [1.0, 2.0, 3.0],
            [2.0, 3.0, 4.0],
            [3.0, 4.0, 5.0],
            [4.0, 5.0, 6.0],
        ],
        dtype=np.float64,
    )
    rgb = np.zeros((2, 3, 3), dtype=np.float64)

    def fake_rgb_to_tc_b(data, **_kwargs):
        tc = np.zeros(data.shape[:-1] + (2,), dtype=np.float64)
        if data.shape == (1, 1, 3):
            scale = np.ones((1, 1), dtype=np.float64)
        else:
            scale = np.full(data.shape[:-1], 2.0, dtype=np.float64)
        return tc, scale

    def fake_apply_lut_cubic_2d(_tc_lut, tc):
        lut_raw = np.empty(tc.shape[:-1] + (3,), dtype=np.float64)
        lut_raw[..., 0] = 2.0
        lut_raw[..., 1] = 4.0
        lut_raw[..., 2] = 6.0
        return lut_raw

    monkeypatch.setattr(spectral_upsampling_module, '_rgb_to_tc_b', fake_rgb_to_tc_b)
    monkeypatch.setattr(spectral_upsampling_module, 'apply_lut_cubic_2d', fake_apply_lut_cubic_2d)

    raw = spectral_upsampling_module.rgb_to_raw_hanatos2025(
        rgb,
        sensitivity,
        color_space='sRGB',
        apply_cctf_decoding=False,
        reference_illuminant='D65',
        tc_lut=np.zeros((2, 2, 3), dtype=np.float64),
    )

    expected = np.empty_like(raw)
    expected[..., 0] = 4.0
    expected[..., 1] = 8.0
    expected[..., 2] = 12.0
    assert raw.shape == (2, 3, 3)
    np.testing.assert_allclose(raw, expected)


def test_spectral_input_policy_warns_and_clips_negative_rgb(monkeypatch):
    captured: dict[str, np.ndarray] = {}

    def fake_rgb_to_xyz(rgb, **_kwargs):
        captured["rgb"] = np.asarray(rgb, dtype=np.float64).copy()
        return np.ones_like(rgb, dtype=np.float64)

    monkeypatch.setattr(spectral_upsampling_module.colour, "RGB_to_XYZ", fake_rgb_to_xyz)

    with pytest.warns(RuntimeWarning, match="negative RGB values"):
        spectral_upsampling_module._rgb_to_tc_b(
            np.array([[[-0.1, 0.2, 0.3]]], dtype=np.float64),
            input_policy=SpectralInputPolicy(negative_rgb="warn"),
        )

    np.testing.assert_allclose(captured["rgb"], np.array([[[0.0, 0.2, 0.3]]], dtype=np.float64))


def test_spectral_input_policy_errors_on_negative_rgb():
    with pytest.raises(ValueError, match="negative RGB values"):
        spectral_upsampling_module._rgb_to_tc_b(
            np.array([[[-0.001, 0.2, 0.3]]], dtype=np.float64),
            input_policy=SpectralInputPolicy(negative_rgb="error"),
        )


def test_spectral_input_policy_errors_on_xy_out_of_bounds(monkeypatch):
    def fake_rgb_to_xyz(rgb, **_kwargs):
        return np.array([[[2.0, -0.25, 1.0]]], dtype=np.float64)

    monkeypatch.setattr(spectral_upsampling_module.colour, "RGB_to_XYZ", fake_rgb_to_xyz)

    with pytest.raises(ValueError, match="xy chromaticities outside"):
        spectral_upsampling_module._rgb_to_tc_b(
            np.array([[[0.2, 0.3, 0.4]]], dtype=np.float64),
            input_policy=SpectralInputPolicy(xy_out_of_bounds="error"),
        )


def test_mallett2019_policy_checks_negative_converted_linear_srgb(monkeypatch):
    def fake_rgb_to_rgb(*_args, **_kwargs):
        return np.array([[[-0.01, 0.2, 0.3]]], dtype=np.float64)

    monkeypatch.setattr(spectral_upsampling_module.colour, "RGB_to_RGB", fake_rgb_to_rgb)
    sensitivity = np.ones((len(spectral_upsampling_module.SPECTRAL_SHAPE.wavelengths), 3), dtype=np.float64)

    with pytest.raises(ValueError, match="Mallett2019 linear sRGB"):
        spectral_upsampling_module.rgb_to_raw_mallett2019(
            np.ones((1, 1, 3), dtype=np.float64),
            sensitivity,
            input_policy=SpectralInputPolicy(negative_rgb="error"),
        )
