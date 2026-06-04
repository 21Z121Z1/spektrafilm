import numpy as np
import pytest
from opt_einsum import contract

from spektrafilm.gpu.backend import BackendUnavailableError, select_backend
from spektrafilm.profiles.io import Hanatos2025SensitivityAdaptation
from spektrafilm.utils import spectral_upsampling as spectral_upsampling_module


pytestmark = pytest.mark.unit


class RecordingMlxFloat32Backend:
    name = "mlx"
    supports_gpu = True
    fallback_reason = None
    requires_serial_runtime = True
    precision = "float32"

    def __init__(self, *, fail_to_numpy: bool = False):
        self.fail_to_numpy = fail_to_numpy
        self.to_numpy_calls = 0

    def asarray(self, value, dtype=None):
        return np.asarray(value, dtype=dtype or np.float32)

    def to_numpy(self, value):
        self.to_numpy_calls += 1
        if self.fail_to_numpy:
            raise AssertionError("backend helper must not materialize the full image")
        return np.asarray(value)

    def eval(self, *values):
        return None

    def synchronize(self):
        return None

    def cleanup(self):
        return None

    def exp(self, x):
        return np.exp(x)

    def log10(self, x):
        return np.log10(x)

    def maximum(self, x, y):
        return np.maximum(x, y)

    def max(self, x):
        return float(np.max(x))

    def clip(self, x, lo, hi):
        return np.clip(x, lo, hi)

    def matmul(self, a, b):
        return np.matmul(a, b)

    def einsum(self, pattern, *values):
        return contract(pattern, *values)

    def power(self, base, x):
        return np.power(base, x)

    def pow(self, x, exponent):
        return np.power(x, exponent)

    def fmax(self, x, y):
        return np.fmax(x, y)

    def nan_to_num(self, x, nan=0.0):
        return np.nan_to_num(x, nan=nan)

    def where(self, condition, x, y):
        return np.where(condition, x, y)

    def abs(self, x):
        return np.abs(x)


def _rgb_tc_b_test_values() -> np.ndarray:
    return np.array(
        [
            [[0.0, 0.0, 0.0], [1e-8, 1e-8, 1e-8], [0.184, 0.184, 0.184], [1.0, 1.0, 1.0]],
            [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [1.0, 0.25, 0.0]],
            [[1.5, 0.2, 0.1], [1.2, 1.1, 0.9], [-0.01, 0.2, 0.3], [0.9, 0.05, 1.4]],
        ],
        dtype=np.float32,
    )


def test_tri2quad_backend_matches_cpu_edge_cases():
    backend = RecordingMlxFloat32Backend()
    tc = np.array(
        [
            [[0.0, 0.0], [0.2, 0.3], [0.999999, 0.5], [1.0, 1.0]],
            [[-0.2, 0.4], [0.5, -0.1], [1.2, 0.8], [0.75, 1.5]],
        ],
        dtype=np.float32,
    )

    actual = spectral_upsampling_module._tri2quad_backend(backend.asarray(tc), backend)
    expected = spectral_upsampling_module._tri2quad(tc)

    np.testing.assert_allclose(np.asarray(actual), expected, rtol=0.0, atol=1e-6)


@pytest.mark.parametrize("color_space", ["sRGB", "Display P3", "ITU-R BT.2020"])
@pytest.mark.parametrize("apply_cctf_decoding", [False, True])
def test_rgb_to_tc_b_backend_matches_cpu_reference(color_space: str, apply_cctf_decoding: bool):
    backend = RecordingMlxFloat32Backend(fail_to_numpy=True)
    rgb = _rgb_tc_b_test_values()

    tc_backend, b_backend = spectral_upsampling_module._rgb_to_tc_b_backend(
        backend.asarray(rgb),
        color_space=color_space,
        apply_cctf_decoding=apply_cctf_decoding,
        reference_illuminant="D55",
        backend=backend,
    )
    expected_tc, expected_b = spectral_upsampling_module._rgb_to_tc_b(
        rgb,
        color_space=color_space,
        apply_cctf_decoding=apply_cctf_decoding,
        reference_illuminant="D55",
    )

    actual_tc = np.asarray(tc_backend)
    actual_b = np.asarray(b_backend)
    tc_abs = np.abs(actual_tc - expected_tc)
    b_abs = np.abs(actual_b - expected_b)

    np.testing.assert_allclose(
        actual_tc,
        expected_tc,
        rtol=5e-5,
        atol=2e-6,
        err_msg=f"tc max_abs={float(np.max(tc_abs)):.3e} mean_abs={float(np.mean(tc_abs)):.3e}",
    )
    np.testing.assert_allclose(
        actual_b,
        expected_b,
        rtol=5e-5,
        atol=2e-6,
        err_msg=f"b max_abs={float(np.max(b_abs)):.3e} mean_abs={float(np.mean(b_abs)):.3e}",
    )
    assert backend.to_numpy_calls == 0


def test_rgb_to_tc_b_backend_caches_cat16_matrix(monkeypatch):
    backend = RecordingMlxFloat32Backend()
    calls: list[tuple[str, tuple[float, float], str]] = []

    def fake_precompute_rgb_to_xyz_matrix(color_space, *, illuminant_xy=None, cat="CAT02"):
        calls.append((color_space, tuple(np.asarray(illuminant_xy, dtype=float)), cat))
        return np.eye(3, dtype=np.float64)

    monkeypatch.setattr(
        spectral_upsampling_module,
        "precompute_rgb_to_xyz_matrix",
        fake_precompute_rgb_to_xyz_matrix,
    )
    spectral_upsampling_module._cached_rgb_to_xyz_matrix.cache_clear()

    rgb = np.full((2, 2, 3), 0.184, dtype=np.float32)
    for _ in range(2):
        spectral_upsampling_module._rgb_to_tc_b_backend(
            backend.asarray(rgb),
            color_space="sRGB",
            apply_cctf_decoding=False,
            reference_illuminant="D55",
            backend=backend,
        )

    assert calls == [("sRGB", tuple(spectral_upsampling_module._illuminant_to_xy("D55")), "CAT16")]
    spectral_upsampling_module._cached_rgb_to_xyz_matrix.cache_clear()


def test_rgb_to_tc_b_backend_real_mlx_matches_cpu_without_materializing(monkeypatch):
    try:
        backend = select_backend("mlx", precision="float32")
    except BackendUnavailableError as exc:
        pytest.skip(str(exc))

    spectral_upsampling_module._cached_rgb_to_xyz_matrix.cache_clear()
    rgb = _rgb_tc_b_test_values()
    original_to_numpy = backend.to_numpy

    def fail_to_numpy(_value):
        raise AssertionError("MLX rgb->tc,b helper must not materialize the full image")

    monkeypatch.setattr(backend, "to_numpy", fail_to_numpy)
    tc_backend, b_backend = spectral_upsampling_module._rgb_to_tc_b_backend(
        backend.asarray(rgb),
        color_space="sRGB",
        apply_cctf_decoding=True,
        reference_illuminant="D55",
        backend=backend,
    )

    assert backend._is_mlx_array(tc_backend)
    assert backend._is_mlx_array(b_backend)

    actual_tc = original_to_numpy(tc_backend)
    actual_b = original_to_numpy(b_backend)
    expected_tc, expected_b = spectral_upsampling_module._rgb_to_tc_b(
        rgb,
        color_space="sRGB",
        apply_cctf_decoding=True,
        reference_illuminant="D55",
    )

    np.testing.assert_allclose(actual_tc, expected_tc, rtol=5e-5, atol=2e-6)
    np.testing.assert_allclose(actual_b, expected_b, rtol=5e-5, atol=2e-6)


def test_compute_lut_spectra_preserves_float32_precision(monkeypatch):
    coeffs = np.ones((2, 2, 3), dtype=np.float32)
    spectra = np.linspace(0.0, 1.0, 2 * 2 * 4, dtype=np.float32).reshape(2, 2, 4)

    monkeypatch.setattr(spectral_upsampling_module, "_load_coeffs_lut", lambda _filename: coeffs)
    monkeypatch.setattr(spectral_upsampling_module, "_fetch_coeffs", lambda _tc, _lut: coeffs)
    monkeypatch.setattr(
        spectral_upsampling_module,
        "_compute_spectra_from_coeffs",
        lambda _coeffs, smooth_steps=1: spectra,
    )

    lut_spectra = spectral_upsampling_module.compute_lut_spectra(lut_size=2)

    assert lut_spectra.dtype == np.float32
    np.testing.assert_allclose(lut_spectra, spectra)


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

    def fake_compute_hanatos2025_tc_lut(arg_sensitivity, _adaptation):
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


def test_spectral_bandpass_windows_return_wavelength_channel_arrays():
    erf4 = spectral_upsampling_module.eval_erf4_spectral_bandpass(
        np.array([415.0, 12.0, 667.0, 76.0], dtype=np.float64)
    )
    logiflex8 = spectral_upsampling_module.eval_logiflex8_spectral_bandpass(
        np.array([415.0, 12.0, 667.0, 76.0, 430.0, 650.0, 1.0, 1.0], dtype=np.float64)
    )

    assert erf4.shape == (81, 3)
    assert logiflex8.shape == (81, 3)
    np.testing.assert_allclose(erf4[:, 0], erf4[:, 1])
    np.testing.assert_allclose(erf4[:, 1], erf4[:, 2])


def test_compute_hanatos2025_tc_lut_normalizes_window_to_preserve_midgray(monkeypatch):
    lut = np.array(
        [
            [[1.0, 10.0], [2.0, 20.0]],
            [[3.0, 30.0], [4.0, 40.0]],
        ],
        dtype=np.float64,
    )
    sensitivity = np.array(
        [
            [1.0, 2.0, 3.0],
            [4.0, 5.0, 6.0],
        ],
        dtype=np.float64,
    )
    window = np.array(
        [
            [0.5, 0.25, 0.75],
            [0.8, 0.6, 0.4],
        ],
        dtype=np.float64,
    )
    illuminant = np.array([2.0, 4.0], dtype=np.float64)

    adaptation = Hanatos2025SensitivityAdaptation(
        window_params=np.array([415.0, 12.0, 667.0, 76.0], dtype=np.float64),
        reference_illuminant='D55',
        apply_window=True,
        apply_surface=False,
    )

    monkeypatch.setattr(spectral_upsampling_module, 'HANATOS2025_SPECTRA_LUT', lut)
    monkeypatch.setattr(spectral_upsampling_module, 'eval_spectral_bandpass_window', lambda _params: window)
    monkeypatch.setattr(spectral_upsampling_module, 'standard_illuminant', lambda _label: illuminant)

    raw_lut = spectral_upsampling_module.compute_hanatos2025_tc_lut(sensitivity, adaptation)

    normalization = np.sum(sensitivity * illuminant[:, None] * window, axis=0) / np.sum(sensitivity * illuminant[:, None], axis=0)
    expected = np.einsum('ijl,lm->ijm', lut, sensitivity * (window / normalization))
    np.testing.assert_allclose(raw_lut, expected)
