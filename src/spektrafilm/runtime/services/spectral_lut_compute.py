from __future__ import annotations

from typing import Callable
import numpy as np

from spektrafilm.utils.lut import compute_with_lut
from spektrafilm.utils.spectral_upsampling import compute_hanatos2025_tc_lut
from spektrafilm.utils.timings import timeit

# Sentinel object used when the GPU trilinear path does not produce PCHIP
# prepared data.  This lets cache-hit logic distinguish "not yet computed"
# (None) from "computed but not needed" (the sentinel).
_GPU_TRILINEAR_PREPARED = object()


class SpectralLUTService:
    def __init__(self, lut_resolution: int, *, gpu_backend=None):
        self._lut_resolution = lut_resolution
        self._gpu_backend = gpu_backend
        self.timings = {}
        self.filming_tc_lut_memory : np.ndarray | None = None # tc_lut memory
        self.enlarger_lut_memory : np.ndarray | None = None # enlarger lut memory
        self.enlarger_lut_prepared_memory = None # prepared PCHIP data for enlarger lut
        self._enlarger_lut_bounds_memory = None # normalized input bounds used for enlarger lut
        self.scanner_lut_memory : np.ndarray | None = None # scanner lut memory
        self.scanner_lut_prepared_memory = None # prepared PCHIP data for scanner lut
        self._scanner_lut_bounds_memory = None # normalized input bounds used for scanner lut
        self._film_sensitivity = None # to track if tc_lut needs to be recomputed when film sensitivity changes
        self._enlarger_test_results_memory = None # to test if enlarger LUTs are identical for same input
        self._scanner_test_results_memory = None # to test if scanner LUTs are identical for same input
        
        self._cmy_test_values = np.array([[[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],
                                          [[0.7, 0.8, 0.9], [1.0, 1.1, 1.2]]]) # to test if LUTs are identical

    def _lut_method(self) -> str:
        """Select the LUT interpolation method based on the GPU backend."""
        if (
            self._gpu_backend is not None
            and self._gpu_backend.supports_gpu
        ):
            return 'gpu_trilinear'
        return 'pchip'

    def _lut_source_callable(self, spectral_calculation: Callable) -> Callable:
        """Wrap spectral callables so CPU-built LUTs always receive NumPy output."""
        if self._gpu_backend is None or not self._gpu_backend.supports_gpu:
            return spectral_calculation

        def wrapped(values):
            return self._gpu_backend.to_numpy(spectral_calculation(values))

        return wrapped

    def _lut_input(self, cmy_data):
        if self._gpu_backend is None or not self._gpu_backend.supports_gpu:
            return cmy_data
        return cmy_data

    @timeit("spectral_compute_enlarger")
    def spectral_compute_enlarger(self,
        cmy_data,
        spectral_calculation: Callable,
        data_min,
        data_max,
        *,
        use_lut: bool = False,
    ):
        if not use_lut:
            return spectral_calculation(cmy_data)

        lut_spectral_calculation = self._lut_source_callable(spectral_calculation)
        lut_input = self._lut_input(cmy_data)
        test_results = lut_spectral_calculation(np.array(self._cmy_test_values))
        bounds = _lut_bounds(data_min, data_max)
        method = self._lut_method()

        if (
            self.enlarger_lut_memory is not None
            and self.enlarger_lut_prepared_memory is not None
            and _bounds_equal(bounds, self._enlarger_lut_bounds_memory)
            and self._enlarger_test_results_memory is not None
            and np.array_equal(test_results, self._enlarger_test_results_memory)
        ):
            prepared = self.enlarger_lut_prepared_memory if self.enlarger_lut_prepared_memory is not _GPU_TRILINEAR_PREPARED else None
            data_out, _, returned_prepared = compute_with_lut(
                lut_input,
                lut_spectral_calculation,
                xmin=data_min,
                xmax=data_max,
                steps=self._lut_resolution,
                lut=self.enlarger_lut_memory,
                prepared_lut=prepared,
                return_prepared=True,
                method=method,
                gpu_backend=self._gpu_backend,
            )
            self.enlarger_lut_prepared_memory = returned_prepared if returned_prepared is not None else _GPU_TRILINEAR_PREPARED
        else:
            data_out, lut, returned_prepared = compute_with_lut(
                lut_input,
                lut_spectral_calculation,
                xmin=data_min,
                xmax=data_max,
                steps=self._lut_resolution,
                return_prepared=True,
                method=method,
                gpu_backend=self._gpu_backend,
            )
            self.enlarger_lut_memory = lut
            self.enlarger_lut_prepared_memory = returned_prepared if returned_prepared is not None else _GPU_TRILINEAR_PREPARED
            self._enlarger_lut_bounds_memory = bounds
            self._enlarger_test_results_memory = np.array(test_results, copy=True)

        if data_out is None:
            raise RuntimeError('LUT computation did not produce an output')
        return data_out

    @timeit("spectral_compute_scanner")
    def spectral_compute_scanner(self,
        cmy_data,
        spectral_calculation: Callable,
        data_min,
        data_max,
        *,
        use_lut: bool = False,
    ):
        if not use_lut:
            return spectral_calculation(cmy_data)

        lut_spectral_calculation = self._lut_source_callable(spectral_calculation)
        lut_input = self._lut_input(cmy_data)
        test_results = lut_spectral_calculation(np.array(self._cmy_test_values))
        bounds = _lut_bounds(data_min, data_max)
        method = self._lut_method()

        if (
            self.scanner_lut_memory is not None
            and self.scanner_lut_prepared_memory is not None
            and _bounds_equal(bounds, self._scanner_lut_bounds_memory)
            and self._scanner_test_results_memory is not None
            and np.array_equal(test_results, self._scanner_test_results_memory)
        ):
            prepared = self.scanner_lut_prepared_memory if self.scanner_lut_prepared_memory is not _GPU_TRILINEAR_PREPARED else None
            data_out, _, returned_prepared = compute_with_lut(
                lut_input,
                lut_spectral_calculation,
                xmin=data_min,
                xmax=data_max,
                steps=self._lut_resolution,
                lut=self.scanner_lut_memory,
                prepared_lut=prepared,
                return_prepared=True,
                method=method,
                gpu_backend=self._gpu_backend,
            )
            self.scanner_lut_prepared_memory = returned_prepared if returned_prepared is not None else _GPU_TRILINEAR_PREPARED
        else:
            data_out, lut, returned_prepared = compute_with_lut(
                lut_input,
                lut_spectral_calculation,
                xmin=data_min,
                xmax=data_max,
                steps=self._lut_resolution,
                return_prepared=True,
                method=method,
                gpu_backend=self._gpu_backend,
            )
            self.scanner_lut_memory = lut
            self.scanner_lut_prepared_memory = returned_prepared if returned_prepared is not None else _GPU_TRILINEAR_PREPARED
            self._scanner_lut_bounds_memory = bounds
            self._scanner_test_results_memory = np.array(test_results, copy=True)

        if data_out is None:
            raise RuntimeError('LUT computation did not produce an output')
        return data_out

    @timeit("get_filming_tc_lut")
    def get_filming_tc_lut(self, sensitivity):
        sensitivity = np.asarray(sensitivity)
        if (
            self.filming_tc_lut_memory is not None
            and self._film_sensitivity is not None
            and np.array_equal(self._film_sensitivity, sensitivity)
        ):
            return self.filming_tc_lut_memory

        self._film_sensitivity = np.array(sensitivity, copy=True)
        self.filming_tc_lut_memory = compute_hanatos2025_tc_lut(sensitivity)
        return self.filming_tc_lut_memory


def _lut_bounds(data_min, data_max):
    return (
        np.asarray(data_min, dtype=np.float64).copy(),
        np.asarray(data_max, dtype=np.float64).copy(),
    )


def _bounds_equal(left, right) -> bool:
    if left is None or right is None:
        return False
    return np.array_equal(left[0], right[0]) and np.array_equal(left[1], right[1])
