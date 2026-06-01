from __future__ import annotations

from typing import Callable
import numpy as np

from spektrafilm.profiles.io import Hanatos2025SensitivityAdaptation
from spektrafilm.utils.lut import _as_channel_bounds, _create_lut_3d, compute_with_lut
from spektrafilm.utils.spectral_upsampling import compute_hanatos2025_tc_lut
from spektrafilm.utils.timings import timeit
from spektrafilm.gpu.kernels.lut import apply_lut_trilinear_3d_backend


class SpectralLUTService:
    def __init__(self, lut_resolution: int, backend=None):
        self._lut_resolution = lut_resolution
        self._backend = backend

        self.timings = {}
        self.hanatos2025_adaptation = None # to be set by filming stage with info from film profile and settings

        # external memory
        self.filming_tc_lut_memory : np.ndarray | None = None # tc_lut memory
        self.enlarger_lut_memory : np.ndarray | None = None # enlarger lut memory
        self.scanner_lut_memory : np.ndarray | None = None # scanner lut memory

        # local memory
        self._film_sensitivity = None # to track if tc_lut needs to be recomputed when film sensitivity changes
        self._film_tc_lut_key = None # cache key for tc_lut
        self._cached_filming_adaptation = None # full adaptation state for which the cached tc_lut was computed
        self._enlarger_test_results_memory = None # to test if enlarger LUTs are identical for same input
        self._scanner_test_results_memory = None # to test if scanner LUTs are identical for same input

        # backend LUT caches — avoid numpy→backend transfer on every call
        self._enlarger_lut_backend = None
        self._scanner_lut_backend = None
        self._tc_lut_backend = None  # backend-cached filming tc_lut

        self._cmy_test_values = np.array([[[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],
                                          [[0.7, 0.8, 0.9], [1.0, 1.1, 1.2]]]) # to test if LUTs are identical

    @property
    def lut_resolution(self) -> int:
        return self._lut_resolution

    def clear(self) -> None:
        """Release all cached LUT and sensitivity data."""
        self.filming_tc_lut_memory = None
        self.enlarger_lut_memory = None
        self.scanner_lut_memory = None
        self._film_sensitivity = None
        self._film_tc_lut_key = None
        self._cached_filming_adaptation = None
        self._enlarger_test_results_memory = None
        self._scanner_test_results_memory = None
        self._enlarger_lut_backend = None
        self._scanner_lut_backend = None
        self._tc_lut_backend = None

    def memory_info(self) -> dict[str, int]:
        """Return byte sizes of cached arrays."""
        def _nbytes(arr: np.ndarray | None) -> int:
            return 0 if arr is None else int(arr.nbytes)
        return {
            'filming_tc_lut': _nbytes(self.filming_tc_lut_memory),
            'enlarger_lut': _nbytes(self.enlarger_lut_memory),
            'scanner_lut': _nbytes(self.scanner_lut_memory),
        }

    def set_hanatos2025_adaptation(self, adaptation: Hanatos2025SensitivityAdaptation) -> None:
        adaptation_copy = self._copy_hanatos2025_adaptation(adaptation)
        self.hanatos2025_adaptation = adaptation_copy
        if not self._same_hanatos2025_adaptation(self._cached_filming_adaptation, adaptation_copy):
            self.filming_tc_lut_memory = None
            self._film_sensitivity = None
            self._cached_filming_adaptation = None
            self._tc_lut_backend = None

    @staticmethod
    def _copy_hanatos2025_adaptation(
        adaptation: Hanatos2025SensitivityAdaptation | None,
    ) -> Hanatos2025SensitivityAdaptation | None:
        if adaptation is None:
            return None
        return Hanatos2025SensitivityAdaptation(
            window_params=np.array(adaptation.window_params, copy=True),
            surface_params=np.array(adaptation.surface_params, copy=True),
            spectral_gaussian_blur=float(adaptation.spectral_gaussian_blur),
            reference_illuminant=adaptation.reference_illuminant,
            apply_window=bool(adaptation.apply_window),
            apply_surface=bool(adaptation.apply_surface),
            active=adaptation.active,
        )

    @staticmethod
    def _same_hanatos2025_adaptation(
        left: Hanatos2025SensitivityAdaptation | None,
        right: Hanatos2025SensitivityAdaptation | None,
    ) -> bool:
        if left is None or right is None:
            return left is right
        return (
            bool(left.apply_window) == bool(right.apply_window)
            and bool(left.apply_surface) == bool(right.apply_surface)
            and float(left.spectral_gaussian_blur) == float(right.spectral_gaussian_blur)
            and left.reference_illuminant == right.reference_illuminant
            and np.array_equal(left.window_params, right.window_params)
            and np.array_equal(left.surface_params, right.surface_params)
        )

    def _spectral_compute(
        self,
        cmy_data,
        spectral_calculation: Callable,
        data_min,
        data_max,
        *,
        use_lut: bool,
        lut_attr: str,
        test_attr: str,
        backend_lut_attr: str,
    ):
        _gpu = self._backend is not None and getattr(self._backend, 'supports_gpu', False)
        if not use_lut:
            if _gpu:
                cmy_data = self._backend.asarray(cmy_data)
                return spectral_calculation(cmy_data)
            # Direct CPU spectral calculation needs float64 for precision.
            cmy_data = np.asarray(cmy_data, dtype=np.float64)
            return spectral_calculation(cmy_data)

        xmin = _as_channel_bounds(data_min)
        xmax = _as_channel_bounds(data_max)
        if np.any(xmax <= xmin):
            raise ValueError('xmax must be greater than xmin')

        def _to_numpy(value):
            if _gpu and hasattr(self._backend, 'to_numpy'):
                return self._backend.to_numpy(value)
            return np.asarray(value)

        def _spectral_calculation_numpy(data):
            return np.asarray(_to_numpy(spectral_calculation(data)), dtype=np.float64)

        test_results = _spectral_calculation_numpy(np.array(self._cmy_test_values))

        cached_lut = getattr(self, lut_attr)
        cached_test = getattr(self, test_attr)
        data_out = None

        if (
            cached_lut is not None
            and cached_test is not None
            and np.array_equal(test_results, cached_test)
        ):
            lut = cached_lut
        else:
            if _gpu:
                lut = _create_lut_3d(
                    _spectral_calculation_numpy,
                    xmin=xmin,
                    xmax=xmax,
                    steps=self._lut_resolution,
                )
            else:
                cmy_data = np.asarray(cmy_data)
                data_out, lut = compute_with_lut(cmy_data,
                                                 spectral_calculation,
                                                 xmin=xmin,
                                                 xmax=xmax,
                                                 steps=self._lut_resolution)
            setattr(self, lut_attr, lut)
            setattr(self, test_attr, np.array(test_results, copy=True))
            # Invalidate the backend LUT cache when numpy LUT changes
            if _gpu:
                setattr(self, backend_lut_attr, None)

        if _gpu:
            cmy_data_backend = self._backend.asarray(cmy_data)
            xmin_backend = self._backend.asarray(xmin)
            xmax_backend = self._backend.asarray(xmax)
            data_normalized = (cmy_data_backend - xmin_backend) / (xmax_backend - xmin_backend)
            # Reuse cached backend LUT to avoid numpy→backend transfer
            backend_lut = getattr(self, backend_lut_attr)
            if backend_lut is None:
                backend_lut = self._backend.asarray(lut)
                setattr(self, backend_lut_attr, backend_lut)
            data_out = apply_lut_trilinear_3d_backend(
                lut,
                data_normalized,
                self._backend,
                prepared_lut=backend_lut,
            )
        else:
            if data_out is None:
                data_out, _ = compute_with_lut(cmy_data,
                                               spectral_calculation,
                                               xmin=xmin,
                                               xmax=xmax,
                                               steps=self._lut_resolution,
                                               lut=lut)

        if data_out is None:
            raise RuntimeError('LUT computation did not produce an output')
        return data_out

    @timeit("spectral_compute_enlarger")
    def spectral_compute_enlarger(self,
        cmy_data,
        spectral_calculation: Callable,
        data_min,
        data_max,
        *,
        use_lut: bool = False,
    ):
        return self._spectral_compute(
            cmy_data, spectral_calculation, data_min, data_max,
            use_lut=use_lut,
            lut_attr='enlarger_lut_memory',
            test_attr='_enlarger_test_results_memory',
            backend_lut_attr='_enlarger_lut_backend',
        )

    @timeit("spectral_compute_scanner")
    def spectral_compute_scanner(self,
        cmy_data,
        spectral_calculation: Callable,
        data_min,
        data_max,
        *,
        use_lut: bool = False,
    ):
        return self._spectral_compute(
            cmy_data, spectral_calculation, data_min, data_max,
            use_lut=use_lut,
            lut_attr='scanner_lut_memory',
            test_attr='_scanner_test_results_memory',
            backend_lut_attr='_scanner_lut_backend',
        )

    @timeit("get_filming_tc_lut")
    def get_filming_tc_lut(self, sensitivity):
        sensitivity = np.asarray(sensitivity)
        if (
            self.filming_tc_lut_memory is not None
            and self._film_sensitivity is not None
            and self._same_hanatos2025_adaptation(self._cached_filming_adaptation, self.hanatos2025_adaptation)
            and np.array_equal(self._film_sensitivity, sensitivity)
        ):
            return self.filming_tc_lut_memory

        self._film_sensitivity = np.array(sensitivity, copy=True)
        self._cached_filming_adaptation = self._copy_hanatos2025_adaptation(self.hanatos2025_adaptation)
        self.filming_tc_lut_memory = compute_hanatos2025_tc_lut(sensitivity, self.hanatos2025_adaptation)
        # Invalidate backend cache when numpy tc_lut changes
        self._tc_lut_backend = None
        return self.filming_tc_lut_memory

    @timeit("get_filming_tc_lut_backend")
    def get_filming_tc_lut_backend(self, sensitivity):
        """Return the tc_lut as a backend array, using the cached version when available.

        Ensures the numpy tc_lut is up-to-date first, then converts to backend
        only when the backend cache is empty.
        """
        tc_lut = self.get_filming_tc_lut(sensitivity)
        _gpu = self._backend is not None and getattr(self._backend, 'supports_gpu', False)
        if _gpu:
            if self._tc_lut_backend is None:
                self._tc_lut_backend = self._backend.asarray(tc_lut)
            return self._tc_lut_backend
        return tc_lut
