from __future__ import annotations

import copy
import os
from time import perf_counter
from dataclasses import dataclass

import colour
import numpy as np

from spektrafilm.color_management import output_encoding_from_io
from spektrafilm.utils.dtypes import runtime_float_dtype as _runtime_float_dtype
from spektrafilm.runtime.services import (
    EnlargerService,
    ResizingService,
    SpectralLUTService,
    ColorReferenceService,
)
from spektrafilm.runtime.stages import FilmingStage, PrintingStage, ScanningStage
from spektrafilm.gpu.backend import backend_summary, select_backend
from spektrafilm.utils.timings import format_timings

GPU_TILE_PIXELS_ENV = "SPEKTRAFILM_GPU_TILE_PIXELS"
MLX_TILE_PIXELS_ENV = "SPEKTRAFILM_MLX_TILE_PIXELS"
DEFAULT_GPU_TILE_PIXELS = 2_000_000
DEFAULT_MLX_TILE_PIXELS = DEFAULT_GPU_TILE_PIXELS
_EXPONENTIAL_TAIL_SIGMA_RATIO = 2.7684


@dataclass(frozen=True, slots=True)
class HDRSceneEnergyMetadata:
    scene_luminance: np.ndarray
    diffuse_white_estimate: float
    headroom_estimate: float
    auto_exposure_ev: float
    method: str
    confidence: str
    profile_scene_y: np.ndarray | None = None
    profile_look_y: np.ndarray | None = None
    scene_rgb: np.ndarray | None = None


@dataclass(frozen=True, slots=True)
class SimulationPipelineResult:
    image: np.ndarray
    hdr_scene_energy: HDRSceneEnergyMetadata | None = None


def _runtime_dtype(float_precision: str) -> np.dtype:
    return _runtime_float_dtype(float_precision)


def _gpu_tile_pixels() -> int:
    raw_limit = os.environ.get(GPU_TILE_PIXELS_ENV)
    if raw_limit is None:
        raw_limit = os.environ.get(MLX_TILE_PIXELS_ENV)
    if raw_limit is None:
        return DEFAULT_GPU_TILE_PIXELS
    try:
        return int(raw_limit)
    except ValueError:
        return DEFAULT_GPU_TILE_PIXELS


def _image_pixel_count(image) -> int:
    shape = tuple(getattr(image, "shape", ()))
    if len(shape) < 2:
        return 0
    return int(shape[0]) * int(shape[1])


def _scene_luminance_y(
    image: np.ndarray,
    *,
    input_color_space: str,
    apply_cctf_decoding: bool,
) -> np.ndarray:
    rgb = np.asarray(image[..., :3], dtype=np.float32)
    try:
        xyz = colour.RGB_to_XYZ(
            rgb,
            input_color_space,
            apply_cctf_decoding=apply_cctf_decoding,
        )
        luminance = np.asarray(xyz[..., 1], dtype=np.float32)
    except (AttributeError, KeyError, LookupError, RuntimeError, TypeError, ValueError):
        luminance = np.tensordot(
            rgb,
            np.array([0.2126, 0.7152, 0.0722], dtype=np.float32),
            axes=([-1], [0]),
        ).astype(np.float32, copy=False)
    return np.maximum(np.nan_to_num(luminance, nan=0.0, posinf=0.0, neginf=0.0), 0.0)


def _hdr_scene_energy_metadata(
    post_auto_rgb: np.ndarray,
    *,
    input_color_space: str,
    apply_cctf_decoding: bool,
    auto_exposure_ev: float,
    auto_percentile: float = 99.0,
    headroom_percentile: float = 99.9,
    min_auto_diffuse_white: float = 0.10,
    low_key_median_threshold: float = 0.03,
    max_headroom: float = 8.0,
) -> HDRSceneEnergyMetadata:
    post_auto_y = _scene_luminance_y(
        post_auto_rgb,
        input_color_space=input_color_space,
        apply_cctf_decoding=apply_cctf_decoding,
    )

    exposure_scale = np.float32(2.0 ** float(auto_exposure_ev))
    metering_y = post_auto_y / np.float32(max(float(exposure_scale), 1e-8))

    flat = metering_y.reshape(-1)
    if flat.size == 0:
        diffuse_white = float(min_auto_diffuse_white)
        method = "auto_floor_empty"
        confidence = "low"
    else:
        p50 = float(np.percentile(flat, 50.0))
        p99 = float(np.percentile(flat, auto_percentile))
        if p99 < float(min_auto_diffuse_white) and p50 < float(low_key_median_threshold):
            diffuse_white = float(min_auto_diffuse_white)
            method = "auto_floor_low_key"
            confidence = "low"
        else:
            diffuse_white = float(np.clip(p99, float(min_auto_diffuse_white), 1.0))
            method = "auto_percentile"
            confidence = "medium"

    scene_luminance = (post_auto_y / np.float32(max(diffuse_white, 1e-8))).astype(np.float32, copy=False)
    scene_luminance = np.maximum(np.nan_to_num(scene_luminance, nan=0.0, posinf=0.0, neginf=0.0), 0.0)

    scene_rgb = (post_auto_rgb / np.float32(max(diffuse_white, 1e-8))).astype(np.float32, copy=False)
    scene_rgb = np.maximum(np.nan_to_num(scene_rgb, nan=0.0, posinf=0.0, neginf=0.0), 0.0)

    headroom = min(
        max(float(np.percentile(scene_luminance.reshape(-1), headroom_percentile)), 1.0),
        float(max_headroom),
    )
    return HDRSceneEnergyMetadata(
        scene_luminance=np.ascontiguousarray(scene_luminance, dtype=np.float32),
        diffuse_white_estimate=diffuse_white,
        headroom_estimate=float(headroom),
        auto_exposure_ev=float(auto_exposure_ev),
        method=method,
        confidence=confidence,
        profile_scene_y=None,
        profile_look_y=None,
        scene_rgb=np.ascontiguousarray(scene_rgb, dtype=np.float32),
    )


def characterize_pipeline_profile(pipeline: 'SimulationPipeline') -> tuple[np.ndarray, np.ndarray]:
    import copy
    from spektrafilm.runtime.params_builder import digest_params
    p = copy.deepcopy(pipeline._params)
    p.debug.deactivate_spatial_effects = True
    p.debug.deactivate_stochastic_effects = True
    p = digest_params(p, apply_stocks_specifics=False)

    temp_pipeline = pipeline.__class__.__new__(pipeline.__class__)
    temp_pipeline._lut_service = pipeline._lut_service
    temp_pipeline.__init__(p, update_params=True)
    temp_pipeline._resize_service.pixel_size_um = 10.0  # Dummy value to prevent NoneType crashes

    w = 512
    scene_y = np.logspace(-8, 6, w, base=2, dtype=np.float32)
    ramp_rgb = np.repeat(scene_y.reshape(1, w, 1), 3, axis=2)
    ramp_rgb_backend = temp_pipeline._runtime_array(ramp_rgb)

    if temp_pipeline.io.scan_film:
        look_rgb = temp_pipeline._pipeline_scan_film(ramp_rgb_backend)
    else:
        look_rgb = temp_pipeline._pipeline_print(ramp_rgb_backend)

    look_rgb = np.asarray(temp_pipeline._array_backend.to_numpy(look_rgb), dtype=np.float32)
    look_y = np.tensordot(
        look_rgb[0, :, :3],
        np.array([0.2126, 0.7152, 0.0722], dtype=np.float32),
        axes=([-1], [0]),
    ).astype(np.float32, copy=False)
    return scene_y, look_y


class SimulationPipeline:
    """Thin runtime orchestrator that composes stage objects."""

    def __init__(self, params, update_params=False, *, _reused_lut_service=None):
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
            if str(compute_backend).strip().lower() in {"mlx", "cupy", "cuda"}:
                raise ValueError("float64 runtime precision requires compute_backend='cpu' or 'auto'.")
            compute_backend = "cpu"
        self._array_backend = select_backend(
            compute_backend,
            precision=self.settings.gpu_precision,
        )

        self.timings = {}
        self._last_elapsed_time = None
        self.validation_report = None

        self._resize_service = ResizingService(self.io, self.camera.film_format_mm)
        reused_lut_service = _reused_lut_service
        if reused_lut_service is None and update_params:
            reused_lut_service = getattr(self, "_lut_service", None)
        reused_backend = getattr(reused_lut_service, "_gpu_backend", None)
        can_reuse_lut_service = (
            reused_lut_service is not None
            and reused_lut_service.lut_resolution == self.settings.lut_resolution
            and type(reused_backend) is type(self._array_backend)
        )
        if can_reuse_lut_service:
            self._lut_service = reused_lut_service
        else:
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
            if self._should_tile_gpu_image(image):
                image = self._process_with_gpu_tiles(image)
            elif self.debug.debug_mode == 'off':
                image = self._pipeline(image)
            else:
                image = self._pipeline_debug(image)
            if self._gpu_validation_enabled() and self.debug.debug_mode != 'off':
                self._record_gpu_validation_skip("debug_mode")
            return np.asarray(self._array_backend.to_numpy(image), dtype=self._runtime_dtype)
        finally:
            self._last_elapsed_time = perf_counter() - start

    def process_with_metadata(self, image) -> SimulationPipelineResult:
        """Process an image and return the rendered output plus HDR sidecar metadata."""

        self.timings.clear()
        start = perf_counter()
        try:
            hdr_scene_energy = None
            if self._should_tile_gpu_image(image):
                preprocessed, hdr_scene_energy = self._preprocess_input_image_with_metadata(image)
                image = self._process_preprocessed_with_gpu_tiles(preprocessed)
            elif self.debug.debug_mode == 'off':
                preprocessed, hdr_scene_energy = self._preprocess_input_image_with_metadata(image)
                image = self._process_runtime_array(self._runtime_array(preprocessed))
            else:
                image = self._pipeline_debug(image)
            if self._gpu_validation_enabled() and self.debug.debug_mode != 'off':
                self._record_gpu_validation_skip("debug_mode")
            return SimulationPipelineResult(
                image=np.asarray(self._array_backend.to_numpy(image), dtype=self._runtime_dtype),
                hdr_scene_energy=hdr_scene_energy,
            )
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
            header=f"Simulation timings (backend: {backend_summary(self._array_backend, runtime_gpu_enabled=True)})",
        )

    def print_timings(self):
        print(self.format_timings())

    def _gpu_validation_enabled(self) -> bool:
        settings = getattr(self, "settings", None)
        return bool(getattr(settings, "gpu_validate", False)) and bool(
            getattr(self._array_backend, "supports_gpu", False)
        )

    def _record_gpu_validation_skip(self, reason: str) -> None:
        start = perf_counter()
        self.validation_report = {
            "status": "skipped",
            "reason": reason,
        }
        self.timings["SimulationPipeline.gpu_validate"] = perf_counter() - start

    def _should_tile_gpu_image(self, image) -> bool:
        if not getattr(self._array_backend, "supports_gpu", False):
            return False
        if self.debug.debug_mode != 'off':
            return False
        if self._has_stochastic_effects():
            return False
        tile_pixels = _gpu_tile_pixels()
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

    def _process_with_gpu_tiles(self, image):
        preprocessed = self._preprocess_input_image(image)
        return self._process_preprocessed_with_gpu_tiles(preprocessed)

    def _process_preprocessed_with_gpu_tiles(self, preprocessed):
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

        self.timings["gpu_tiled_tiles"] = float(tile_count)
        self.timings["gpu_tiled_overlap_pixels"] = float(overlap)
        self.timings["gpu_tiled_tile_pixels"] = float(_gpu_tile_pixels())
        return output

    def _tile_core_rows(self, *, width: int, overlap: int) -> int:
        tile_pixels = _gpu_tile_pixels()
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
        image, _auto_exposure_ev = self._filming_stage.auto_exposure_with_ev(image)
        return self._resize_service.crop_and_rescale(image)

    def _preprocess_input_image_with_metadata(self, image) -> tuple[np.ndarray, HDRSceneEnergyMetadata]:
        image = np.ascontiguousarray(np.asarray(image, dtype=self._runtime_dtype)[:, :, 0:3])
        auto_exposed, auto_exposure_ev = self._filming_stage.auto_exposure_with_ev(image)
        preprocessed = self._resize_service.crop_and_rescale(auto_exposed)
        metadata = _hdr_scene_energy_metadata(
            preprocessed,
            input_color_space=self.io.input_color_space,
            apply_cctf_decoding=self.io.input_cctf_decoding,
            auto_exposure_ev=float(auto_exposure_ev),
        )

        try:
            profile_scene_y, profile_look_y = characterize_pipeline_profile(self)
            from dataclasses import replace
            metadata = replace(metadata, profile_scene_y=profile_scene_y, profile_look_y=profile_look_y)
        except Exception as e:
            print(f"Warning: Failed to characterize profile for HDR mapping: {e}")

        return preprocessed, metadata

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
        raise ValueError(f"Unknown debug_mode: {self.debug.debug_mode!r}")

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
