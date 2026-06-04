import numpy as np
import pytest

from spektrafilm.profiles.io import Hanatos2025SensitivityAdaptation
from spektrafilm.runtime.services import spectral_lut_compute as spectral_lut_compute_module


pytestmark = pytest.mark.unit


def test_filming_tc_lut_recomputes_when_spectral_gaussian_blur_changes(monkeypatch) -> None:
    calls: list[float] = []

    def fake_compute_hanatos2025_tc_lut(sensitivity, adaptation, gamut_compress=None):
        del sensitivity, gamut_compress
        calls.append(float(adaptation.spectral_gaussian_blur))
        return np.full((2, 2, 3), adaptation.spectral_gaussian_blur + 1.0, dtype=float)

    monkeypatch.setattr(
        spectral_lut_compute_module,
        'compute_hanatos2025_tc_lut',
        fake_compute_hanatos2025_tc_lut,
    )

    service = spectral_lut_compute_module.SpectralLUTService(lut_resolution=17)
    sensitivity = np.ones((4, 3), dtype=float)
    adaptation = Hanatos2025SensitivityAdaptation(
        window_params=np.empty((0,), dtype=float),
        surface_params=np.empty((0, 3), dtype=float),
        spectral_gaussian_blur=0.0,
        reference_illuminant='D55',
        apply_window=True,
        apply_surface=True,
    )

    service.set_hanatos2025_adaptation(adaptation)
    first = service.get_filming_tc_lut(sensitivity)

    adaptation.spectral_gaussian_blur = 4.0
    service.set_hanatos2025_adaptation(adaptation)
    second = service.get_filming_tc_lut(sensitivity)

    assert calls == [0.0, 4.0]
    assert np.array_equal(first, second) is False


def test_spectral_compute_cpu_cache_miss_reuses_first_lut_result(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_compute_with_lut(data, function, *, xmin, xmax, steps, lut=None):
        calls.append({'lut_was_cached': lut is not None})
        fake_lut = np.ones((steps, steps, steps, 3), dtype=float)
        return function(data) + 1.0, fake_lut

    monkeypatch.setattr(
        spectral_lut_compute_module,
        'compute_with_lut',
        fake_compute_with_lut,
    )

    service = spectral_lut_compute_module.SpectralLUTService(lut_resolution=5)
    data = np.full((1, 1, 3), 0.25, dtype=float)

    result = service.spectral_compute_enlarger(
        data,
        spectral_calculation=lambda value: np.asarray(value, dtype=float) * 2.0,
        data_min=np.zeros(3),
        data_max=np.ones(3),
        use_lut=True,
    )

    assert calls == [{'lut_was_cached': False}]
    np.testing.assert_allclose(result, data * 2.0 + 1.0)


def test_spectral_compute_gpu_cache_hit_rejects_degenerate_bounds() -> None:
    class FakeGpuBackend:
        supports_gpu = True

        def asarray(self, value):
            return np.asarray(value)

    service = spectral_lut_compute_module.SpectralLUTService(
        lut_resolution=5,
        backend=FakeGpuBackend(),
    )
    service.enlarger_lut_memory = np.zeros((5, 5, 5, 3), dtype=float)

    def spectral_calculation(value):
        return np.zeros_like(np.asarray(value, dtype=float))

    service._enlarger_test_results_memory = spectral_calculation(service._cmy_test_values)

    with pytest.raises(ValueError, match='xmax must be greater than xmin'):
        service.spectral_compute_enlarger(
            np.zeros((1, 1, 3), dtype=float),
            spectral_calculation=spectral_calculation,
            data_min=np.zeros(3),
            data_max=np.zeros(3),
            use_lut=True,
        )


def test_spectral_compute_gpu_direct_path_keeps_backend_array_resident() -> None:
    class FakeGpuArray:
        shape = (1, 1, 3)

        def __array__(self, dtype=None):
            del dtype
            raise AssertionError("unexpected GPU array to NumPy transfer")

    class FakeGpuBackend:
        supports_gpu = True

        def asarray(self, value):
            assert isinstance(value, FakeGpuArray)
            return value

    value = FakeGpuArray()
    service = spectral_lut_compute_module.SpectralLUTService(
        lut_resolution=5,
        backend=FakeGpuBackend(),
    )

    def spectral_calculation(data):
        assert data is value
        return data

    result = service.spectral_compute_scanner(
        value,
        spectral_calculation=spectral_calculation,
        data_min=np.zeros(3),
        data_max=np.ones(3),
        use_lut=False,
    )

    assert result is value


def test_spectral_compute_gpu_lut_path_returns_backend_result_without_numpy_transfer(monkeypatch) -> None:
    class FakeGpuArray:
        def __array__(self, dtype=None):
            del dtype
            raise AssertionError("unexpected LUT result to NumPy transfer")

    class FakeGpuBackend:
        supports_gpu = True

        def asarray(self, value):
            return np.asarray(value, dtype=np.float32)

    expected = FakeGpuArray()
    calls: list[dict[str, object]] = []

    def spectral_calculation(value):
        return np.zeros_like(np.asarray(value, dtype=float))

    def fake_apply_lut(lut, image, backend, *, prepared_lut=None):
        calls.append(
            {
                "lut_shape": np.asarray(lut).shape,
                "image_shape": np.asarray(image).shape,
                "backend": backend,
                "prepared_lut_was_cached": prepared_lut is not None,
            }
        )
        return expected

    monkeypatch.setattr(
        spectral_lut_compute_module,
        "apply_lut_trilinear_3d_backend",
        fake_apply_lut,
    )

    service = spectral_lut_compute_module.SpectralLUTService(
        lut_resolution=5,
        backend=FakeGpuBackend(),
    )
    data_min = np.zeros(3)
    data_max = np.ones(3)
    service.scanner_lut_memory = np.zeros((5, 5, 5, 3), dtype=float)
    service._scanner_test_results_memory = (
        hash(np.asarray(data_min).tobytes()),
        hash(np.asarray(data_max).tobytes()),
        id(spectral_calculation),
    )

    result = service.spectral_compute_scanner(
        np.full((2, 2, 3), 0.25, dtype=np.float32),
        spectral_calculation=spectral_calculation,
        data_min=data_min,
        data_max=data_max,
        use_lut=True,
    )

    assert result is expected
    assert calls == [
        {
            "lut_shape": (5, 5, 5, 3),
            "image_shape": (2, 2, 3),
            "backend": service._backend,
            "prepared_lut_was_cached": True,
        }
    ]
