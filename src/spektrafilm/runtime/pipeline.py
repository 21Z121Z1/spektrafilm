from __future__ import annotations

import copy
import os
from time import perf_counter

import numpy as np

from spektrafilm.color_management import output_encoding_from_io
from spektrafilm.runtime.services import (
    EnlargerService,
    ResizingService,
    SpectralLUTService,
    ColorReferenceService,
)
from spektrafilm.runtime.stages import FilmingStage, PrintingStage, ScanningStage
from spektrafilm.gpu.backend import backend_summary, select_backend
from spektrafilm.utils.timings import format_timings

MLX_TILE_PIXELS_ENV = "SPEKTRAFILM_MLX_TILE_PIXELS"
DEFAULT_MLX_TILE_PIXELS = 2_000_000
_EXPONENTIAL_TAIL_SIGMA_RATIO = 2.7684


def _runtime_dtype(float_precision: str) -> np.dtype:
    if float_precision == "float64":
        return np.dtype(np.float64)
    if float_precision == "float32":
        return np.dtype(np.float32)
    raise ValueError("float_precision must be 'float32' or 'float64'")


def _mlx_tile_pixels() -> int:
    raw_limit = os.environ.get(MLX_TILE_PIXELS_ENV)
    if raw_limit is None:
        return DEFAULT_MLX_TILE_PIXELS
    try:
        return int(raw_limit)
    except ValueError:
        return DEFAULT_MLX_TILE_PIXELS


def _image_pixel_count(image) -> int:
    shape = tuple(getattr(image, "shape", ()))
    if len(shape) < 2:
        return 0
    return int(shape[0]) * int(shape[1])


class SimulationPipeline:
    """Thin runtime orchestrator that composes stage objects."""

    def __init__(self, params, update_params=False):
        self._params = copy.deepcopy(params)

        self.camera = self._params.camera
        self.film = self._params.film
        self.film_render = self._params.film_render
        self.enlarger = self._params.enlarger
        self.print = self._params.print
        self.print_render = self._params.print_render
        self.scanner = self._params.scanner
        self.io = self._params.io
        self.debug = self._params.debug
        self.settings = self._params.settings
        self._runtime_dtype = _runtime_dtype(self.settings.float_precision)
        compute_backend = self.settings.compute_backend
        if self._runtime_dtype == np.dtype(np.float64):
            if compute_backend == "mlx":
                raise ValueError("float64 runtime precision requires compute_backend='cpu' or 'auto'.")
            compute_backend = "cpu"
        self._array_backend = select_backend(
            compute_backend,
            precision=self.settings.gpu_precision,
        )

        self.timings = {}
        self._last_elapsed_time = None

        self._resize_service = ResizingService(self.io, self.camera.film_format_mm)
        if not update_params:
            self._lut_service = SpectralLUTService(
                self.settings.lut_resolution,
                gpu_backend=self._array_backend,
            )
        self._enlarger_service = EnlargerService(self.enlarger)
        self._output_encoding = output_encoding_from_io(self.io)
        self._color_reference_service = ColorReferenceService(self.film, self.film_render,
                                                              self.print, self.print_render,
                                                              self.scanner.black_correction, self.scanner.white_correction,
                                                              self.scanner.black_level, self.scanner.white_level,
                                                              self.io, output_encoding=self._output_encoding)

        
        self._filming_stage = FilmingStage(
            self.film,
            self.film_render,
            self.camera,
            self.io,
            self.settings,
            self._lut_service,
            self._resize_service, # to get pixel size um for blurs
            self._enlarger_service, # to compute and save density spectral midgray to balance print
            self._color_reference_service,
            backend=self._array_backend,
        )
        self._printing_stage = PrintingStage(
            self.film,
            self.film_render,
            self.print,
            self.print_render,
            self.enlarger,
            self.settings,
            self._lut_service,
            self._enlarger_service,
            self._resize_service, # to get pixel size um for diffusion filter
            self._color_reference_service,
            backend=self._array_backend,
        )
        self._scanning_stage = ScanningStage(
            self.film,
            self.film_render,
            self.print,
            self.print_render,
            self.scanner,
            self.io,
            self.settings,
            self._lut_service,
            self._color_reference_service,
            backend=self._array_backend,
        )
        
        # timing communication
        self._filming_stage.timings = self.timings
        self._printing_stage.timings = self.timings
        self._scanning_stage.timings = self.timings
        self._lut_service.timings = self.timings

    def process(self, image):
        """Process an image through the simulation pipeline."""
        self.timings.clear()
        start = perf_counter()
        try:
            if self._should_tile_mlx_image(image):
                image = self._process_with_mlx_tiles(image)
            elif self.debug.debug_mode == 'off':
                image = self._pipeline(image)
            else:
                image = self._pipeline_debug(image)
            return np.asarray(self._array_backend.to_numpy(image), dtype=self._runtime_dtype)
        finally:
            self._last_elapsed_time = perf_counter() - start

    def get_timings(self):
        return self.timings

    def get_total_elapsed_time(self):
        return self._last_elapsed_time

    def format_timings(self):
        return format_timings(
            self.get_timings(),
            total_elapsed_time=self.get_total_elapsed_time(),
            header=f"Simulation timings (backend: {backend_summary(self._array_backend)})",
        )

    def print_timings(self):
        print(self.format_timings())

    def _should_tile_mlx_image(self, image) -> bool:
        if not getattr(self._array_backend, "supports_gpu", False):
            return False
        if self.debug.debug_mode != 'off':
            return False
        if self._has_stochastic_effects():
            return False
        tile_pixels = _mlx_tile_pixels()
        if tile_pixels <= 0:
            return False
        return _image_pixel_count(image) > tile_pixels

    def _has_stochastic_effects(self) -> bool:
        film_render = getattr(self, "film_render", None)
        print_render = getattr(self, "print_render", None)

        grain = getattr(film_render, "grain", None)
        if bool(getattr(grain, "active", False)):
            return True

        glare = getattr(print_render, "glare", None)
        if bool(getattr(glare, "active", False)):
            return True

        return False

    def _process_with_mlx_tiles(self, image):
        preprocessed = self._preprocess_input_image(image)
        height, width = preprocessed.shape[:2]
        if height == 0 or width == 0:
            return preprocessed

        overlap = min(self._tile_overlap_pixels(), max(height - 1, 0))
        core_rows = self._tile_core_rows(width=width, overlap=overlap)
        output = np.empty((height, width, 3), dtype=self._runtime_dtype)
        tile_count = 0

        for start_y in range(0, height, core_rows):
            end_y = min(start_y + core_rows, height)
            input_start = max(start_y - overlap, 0)
            input_end = min(end_y + overlap, height)
            tile = self._runtime_array(preprocessed[input_start:input_end, :, :])
            tile_output = self._process_runtime_array(tile)
            tile_output = np.asarray(self._array_backend.to_numpy(tile_output), dtype=self._runtime_dtype)
            crop_start = start_y - input_start
            crop_end = crop_start + (end_y - start_y)
            output[start_y:end_y, :, :] = tile_output[crop_start:crop_end, :, :]
            self._synchronize_backend()
            tile_count += 1

        self.timings["mlx_tiled_tiles"] = float(tile_count)
        self.timings["mlx_tiled_overlap_pixels"] = float(overlap)
        self.timings["mlx_tiled_tile_pixels"] = float(_mlx_tile_pixels())
        return output

    def _tile_core_rows(self, *, width: int, overlap: int) -> int:
        tile_pixels = _mlx_tile_pixels()
        if tile_pixels <= 0:
            return 1
        rows_with_overlap_budget = max(tile_pixels // max(width, 1), 1)
        return max(int(rows_with_overlap_budget) - 2 * int(overlap), 1)

    def _tile_overlap_pixels(self) -> int:
        pixel_size_um = max(float(getattr(self._resize_service, "pixel_size_um", 1.0)), 1e-6)
        margins = [
            3.0 * float(getattr(self.camera, "lens_blur_um", 0.0)) / pixel_size_um,
            3.0 * float(getattr(self.enlarger, "lens_blur", 0.0)),
            3.0 * float(getattr(self.scanner, "lens_blur", 0.0)),
        ]
        scanner_unsharp = getattr(self.scanner, "unsharp_mask", (0.0, 0.0))
        if len(scanner_unsharp) >= 2 and float(scanner_unsharp[1]) > 0:
            margins.append(3.0 * float(scanner_unsharp[0]))

        halation = self.film_render.halation
        if getattr(halation, "active", False):
            scatter_scale = float(getattr(halation, "scatter_spatial_scale", 1.0))
            halation_scale = float(getattr(halation, "halation_spatial_scale", 1.0))
            margins.append(
                3.0 * float(np.max(np.asarray(halation.scatter_core_um, dtype=np.float64)))
                * scatter_scale
                / pixel_size_um
            )
            margins.append(
                3.0 * _EXPONENTIAL_TAIL_SIGMA_RATIO
                * float(np.max(np.asarray(halation.scatter_tail_um, dtype=np.float64)))
                * scatter_scale
                / pixel_size_um
            )
            bounce_count = max(int(getattr(halation, "halation_n_bounces", 1)), 1)
            margins.append(
                3.0 * float(np.max(np.asarray(halation.halation_first_sigma_um, dtype=np.float64)))
                * halation_scale
                * np.sqrt(float(bounce_count))
                / pixel_size_um
            )

        couplers = self.film_render.dir_couplers
        if getattr(couplers, "active", False):
            margins.append(3.0 * float(getattr(couplers, "diffusion_size_um", 0.0)) / pixel_size_um)
            margins.append(
                3.0 * _EXPONENTIAL_TAIL_SIGMA_RATIO
                * float(getattr(couplers, "diffusion_tail_um", 0.0))
                / pixel_size_um
            )

        for diffusion_filter in (self.camera.diffusion_filter, self.enlarger.diffusion_filter):
            if not getattr(diffusion_filter, "active", False):
                continue
            if float(getattr(diffusion_filter, "strength", 0.0)) <= 0.0:
                continue
            margins.append(self._diffusion_filter_overlap_pixels(diffusion_filter, pixel_size_um))

        return max(int(np.ceil(max(margins, default=0.0))), 0)

    @staticmethod
    def _diffusion_filter_overlap_pixels(diffusion_filter, pixel_size_um: float) -> float:
        try:
            from spektrafilm.model.diffusion import _bloom_max_lambda_um, _overrides_from_params

            bloom_um = _bloom_max_lambda_um(
                diffusion_filter.filter_family,
                _overrides_from_params(diffusion_filter),
            )
        except (AttributeError, KeyError, TypeError, ValueError):
            bloom_um = 0.0
        return 8.0 * bloom_um * float(getattr(diffusion_filter, "spatial_scale", 1.0)) / pixel_size_um

    def _synchronize_backend(self) -> None:
        synchronize = getattr(self._array_backend, "synchronize", None)
        if callable(synchronize):
            synchronize()
    
    def update(self, params):
        """Update params and re-initialize stages that depend on them."""
        self.__init__(params, update_params=True)
        
    def soft_update(self,
                    exposure_compensation_ev=None,
                    print_exposure=None,
                    c_filter_neutral=None,
                    m_filter_neutral=None,
                    y_filter_neutral=None,
                    film_density_curves=None,
                    print_density_curves=None,):
        invalidates_print_balance_reference = False
        if exposure_compensation_ev is not None:
            self.camera.exposure_compensation_ev = exposure_compensation_ev
            invalidates_print_balance_reference = True
        if print_exposure is not None:
            self.enlarger.print_exposure = print_exposure
        if c_filter_neutral is not None:
            self.enlarger.c_filter_neutral = c_filter_neutral
        if m_filter_neutral is not None:
            self.enlarger.m_filter_neutral = m_filter_neutral
        if y_filter_neutral is not None:
            self.enlarger.y_filter_neutral = y_filter_neutral
        if film_density_curves is not None:
            self.film.data.density_curves = film_density_curves
            invalidates_print_balance_reference = True
        if print_density_curves is not None:
            self.print.data.density_curves = print_density_curves
        if invalidates_print_balance_reference:
            (
                self._enlarger_service.density_spectral_midgray,
                self._enlarger_service.density_spectral_midgray_comp,
            ) = self._filming_stage._compute_density_spectral_midgray_to_balance_print()
        
    # private methods
    
    def _pipeline(self, image):
        return self._process_runtime_array(self._preprocess(image))
    
    def _process_runtime_array(self, image):
        if self.io.scan_film: # replace with route switch
            return self._pipeline_scan_film(image)
        return self._pipeline_print(image)

    def _preprocess_input_image(self, image):
        image = np.ascontiguousarray(np.asarray(image, dtype=self._runtime_dtype)[:, :, 0:3])
        image = self._filming_stage.auto_exposure(image) # autoexposure service?
        return self._resize_service.crop_and_rescale(image)

    def _preprocess(self, image):
        return self._runtime_array(self._preprocess_input_image(image))
    
    def _pipeline_scan_film(self, rgb_image):
        log_raw_film = self._runtime_array(self._filming_stage.expose(rgb_image))
        del rgb_image
        cmy_film = self._runtime_array(self._filming_stage.develop(log_raw_film))
        del log_raw_film
        rgb_scan = self._runtime_array(self._scanning_stage.scan(cmy_film, output_encoding=self._output_encoding))
        del cmy_film
        return rgb_scan
    
    def _pipeline_print(self, rgb_image):
        log_raw_film = self._runtime_array(self._filming_stage.expose(rgb_image))
        del rgb_image
        cmy_film = self._runtime_array(self._filming_stage.develop(log_raw_film))
        del log_raw_film
        log_raw_print = self._runtime_array(self._printing_stage.expose(cmy_film))
        del cmy_film
        cmy_print = self._runtime_array(self._printing_stage.develop(log_raw_print))
        del log_raw_print
        rgb_scan = self._runtime_array(self._scanning_stage.scan(cmy_print, output_encoding=self._output_encoding))
        del cmy_print
        return rgb_scan

    def _runtime_array(self, image):
        if self._array_backend.supports_gpu:
            return self._array_backend.asarray(image)
        return np.asarray(image, dtype=self._runtime_dtype)
    
################################################################################
    
    # debug_methods

    def _pipeline_debug(self, rgb_image):
        if self.debug.debug_mode == "output":
            return self._debug_output_pipeline(rgb_image)
        elif self.debug.debug_mode == "inject":
            return self._debug_inject_pipeline(rgb_image)
    
    def _debug_output_pipeline(self, rgb_image):
        """Run the pipeline with additional outputs for debugging."""
        rgb_image = self._preprocess(rgb_image)
        log_raw_film = self._filming_stage.expose(rgb_image)
        if self.debug.output_film_log_raw:
            return log_raw_film
        
        cmy_film = self._filming_stage.develop(log_raw_film)
        if self.debug.output_film_density_cmy:
            return cmy_film
        
        log_raw_print = self._printing_stage.expose(cmy_film)
        cmy_print = self._printing_stage.develop(log_raw_print)
        if self.debug.output_print_density_cmy:
            return cmy_print
        
        rgb_scan = self._scanning_stage.scan(cmy_print, output_encoding=self._output_encoding)
        return rgb_scan
    
    def _debug_inject_pipeline(self, cmy_film):
        """Run the pipeline with additional inputs for debugging."""
        if self.debug.inject_film_density_cmy:
            log_raw_print = self._printing_stage.expose(cmy_film)
            cmy_print = self._printing_stage.develop(log_raw_print)
            rgb_scan = self._scanning_stage.scan(cmy_print, output_encoding=self._output_encoding)
            return rgb_scan
