from __future__ import annotations

import copy
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import colour
import numpy as np
from skimage.transform import rescale

from spektrafilm.color_management import is_aces_scene_linear_space
from spektrafilm.runtime.services import (
    EnlargerService,
    ResizingService,
    SpectralLUTService,
    ColorReferenceService,
)
from spektrafilm.gpu.backend import runtime_backend_summary, select_backend
from spektrafilm.runtime.route_master import HDRMode, RouteMaster, ScanMasterResult
from spektrafilm.runtime.stages import FilmingStage, PrintingStage, ScanningStage
from spektrafilm.runtime.topology import Node, Tap, run_topology
from spektrafilm.utils.autoexposure import _luminance_y, measure_autoexposure_ev
from spektrafilm.utils.hdr_curve_profiles import luminance_y, render_negative_scan_positive_rgb
from spektrafilm.utils.timings import format_timings


@dataclass(slots=True)
class HDRSceneEnergyMetadata:
    scene_luminance: np.ndarray
    auto_exposure_ev: float | None
    input_color_space: str
    input_cctf_decoding: bool


@dataclass(slots=True)
class SimulationPipelineResult:
    image: Any
    hdr_scene_energy: HDRSceneEnergyMetadata | None = None
    route_master: RouteMaster | None = None


def _backend_cache_key(backend):
    if backend is None:
        return None
    return (
        type(backend),
        getattr(backend, "name", None),
        getattr(backend, "precision", None),
        bool(getattr(backend, "supports_gpu", False)),
        bool(getattr(backend, "requires_serial_runtime", False)),
    )


def _backend_selection_key_from_settings(settings):
    if settings is None:
        return None
    return (
        getattr(settings, "compute_backend", None),
        getattr(settings, "gpu_precision", None),
    )


class SimulationPipeline:
    """Thin runtime orchestrator that composes stage objects around a
    tap-based topology dispatcher.

    The pipeline declares its stages as a list of :class:`Node` objects via
    :meth:`_build_topology`. Calling :meth:`process` walks the topology in
    declared order, firing each node whose input taps are present in state,
    and returns the value at the requested ``collect`` tap.
    """

    def __init__(self, params, update_params=False):
        previous_lut_service = getattr(self, "_lut_service", None) if update_params else None
        previous_lut_backend = getattr(previous_lut_service, "_backend", None)
        previous_backend = getattr(self, "_backend", None) if update_params else None
        previous_backend_selection_key = getattr(self, "_backend_selection_key", None) if update_params else None

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
        self.taps = self._params.taps
        self._backend_selection_key = _backend_selection_key_from_settings(self.settings)
        if (
            previous_backend is not None
            and previous_backend_selection_key == self._backend_selection_key
        ):
            self._backend = previous_backend
        else:
            self._backend = select_backend(
                self.settings.compute_backend,
                precision=self.settings.gpu_precision,
            )
        self._array_backend = self._backend

        self.timings = {}
        self._last_elapsed_time = None

        self._resize_service = ResizingService(self.io, self.camera.film_format_mm)
        if (
            previous_lut_service is None
            or getattr(previous_lut_service, 'lut_resolution', None) != self.settings.lut_resolution
            or _backend_cache_key(previous_lut_backend) != _backend_cache_key(self._backend)
        ):
            self._lut_service = SpectralLUTService(self.settings.lut_resolution, backend=self._backend)
        else:
            self._lut_service = previous_lut_service
        self._enlarger_service = EnlargerService(self.enlarger)
        self._color_reference_service = ColorReferenceService(self.film, self.film_render,
                                                              self.print, self.print_render,
                                                              self.scanner.black_correction, self.scanner.white_correction,
                                                              self.scanner.black_level, self.scanner.white_level,
                                                              self.io,
                                                              backend=self._backend)

        self._filming_stage = FilmingStage(
            self.film,
            self.film_render,
            self.camera,
            self.io,
            self.settings,
            self._lut_service,
            self._resize_service,
            self._enlarger_service,
            self._color_reference_service,
            self._backend,
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
            self._resize_service,
            self._color_reference_service,
            self._backend,
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
            self._backend,
        )

        # timing communication
        self._filming_stage.timings = self.timings
        self._printing_stage.timings = self.timings
        self._scanning_stage.timings = self.timings
        self._lut_service.timings = self.timings

        self._topology: list[Node] = self._build_topology()

    def process(self, image, *, inject: str | None = None, collect: str | None = None):
        """Process an image through the simulation pipeline."""
        if inject is not None or collect is not None or self.taps.inject is not None or self.taps.collect is not None:
            return self._process_topology(image, inject=inject, collect=collect)
        return self._process_result(image, include_metadata=False).image

    def process_with_metadata(self, image) -> SimulationPipelineResult:
        """Process an image and return the final image plus optional HDR scene metadata."""
        return self._process_result(image, include_metadata=True)

    def process_master(self, image, *, hdr_mode: HDRMode) -> RouteMaster:
        """Process one full-resolution route into a RouteMaster."""
        result = self.process_with_master(image, hdr_mode=hdr_mode)
        if result.route_master is None:
            raise RuntimeError("RouteMaster processing completed without a RouteMaster.")
        return result.route_master

    def process_with_master(self, image, *, hdr_mode: HDRMode) -> SimulationPipelineResult:
        """Process one route and return output image, HDR scene metadata, and RouteMaster."""
        if hdr_mode not in ("light_table", "paper"):
            raise ValueError("hdr_mode must be 'light_table' or 'paper'.")
        desired_scan_film = hdr_mode == "light_table"
        if bool(self.io.scan_film) != desired_scan_film:
            route_params = copy.deepcopy(self._params)
            route_params.io.scan_film = desired_scan_film
            route_pipeline = SimulationPipeline(route_params)
            result = route_pipeline.process_with_master(image, hdr_mode=hdr_mode)
            self.timings.clear()
            self.timings.update(route_pipeline.timings)
            self._last_elapsed_time = route_pipeline.get_total_elapsed_time()
            return result
        return self._process_with_master_result(image, hdr_mode=hdr_mode)

    def _process_result(self, image, *, include_metadata: bool) -> SimulationPipelineResult:
        self.timings.clear()
        start = perf_counter()
        
        try:
            if include_metadata:
                result = self._pipeline_with_metadata(image)
            else:
                result = SimulationPipelineResult(image=self._pipeline(image))
            self._run_gpu_validate(image, result.image)
            return result
        finally:
            if self._should_cleanup_after_process():
                cleanup_start = perf_counter()
                self._backend.cleanup()
                self.timings["SimulationPipeline.mlx_cleanup"] = perf_counter() - cleanup_start
            self._last_elapsed_time = perf_counter() - start

    def _process_with_master_result(self, image, *, hdr_mode: HDRMode) -> SimulationPipelineResult:
        self.timings.clear()
        start = perf_counter()

        try:
            result = self._pipeline_with_master(image, hdr_mode=hdr_mode)
            self._run_gpu_validate(image, result.image)
            return result
        finally:
            if self._should_cleanup_after_process():
                cleanup_start = perf_counter()
                self._backend.cleanup()
                self.timings["SimulationPipeline.mlx_cleanup"] = perf_counter() - cleanup_start
            self._last_elapsed_time = perf_counter() - start

    def _process_topology(self, image, *, inject: str | None = None, collect: str | None = None):
        inject = inject or self.taps.inject or Tap.RGB_IN
        collect = collect or self.taps.collect or Tap.RGB_OUT

        self.timings.clear()
        start = perf_counter()
        
        try:
            self._prepare_topology_injection_side_effects(image, inject)
            return run_topology(
                self._topology, inject, collect, image,
                on_fire=self._record_node_timing,
            )
        finally:
            if self._should_cleanup_after_process():
                cleanup_start = perf_counter()
                self._backend.cleanup()
                self.timings["SimulationPipeline.mlx_cleanup"] = perf_counter() - cleanup_start
            self._last_elapsed_time = perf_counter() - start

    def _prepare_topology_injection_side_effects(self, image, inject: str) -> None:
        if inject == Tap.RGB_IN or self._resize_service.pixel_size_um is not None:
            return
        if inject not in {
            Tap.RGB_PRE,
            Tap.LOG_E_FILM,
            Tap.CMY_FILM,
            Tap.LOG_E_PRINT,
            Tap.CMY_PRINT,
            Tap.RGB_OUT,
        }:
            return

        shape = getattr(image, "shape", None)
        if shape is None or len(shape) < 2:
            raise ValueError(
                "topology injection after preprocess requires an image with "
                "height and width to infer pixel_size_um"
            )
        height, width = int(shape[0]), int(shape[1])
        if height <= 0 or width <= 0:
            raise ValueError(
                "topology injection after preprocess requires non-empty image geometry"
            )
        self._resize_service.pixel_size_um = self.camera.film_format_mm * 1000 / max(height, width)

    def _gpu_validation_tolerance(self) -> float:
        explicit = getattr(self.settings, "gpu_validation_tolerance", None)
        if explicit is not None:
            return float(explicit)

        backend_name = getattr(self._array_backend, "name", "")
        if backend_name == "halide":
            return 6e-2
        if (
            getattr(self.settings, "use_enlarger_lut", False)
            or getattr(self.settings, "use_scanner_lut", False)
        ):
            return 2e-4
        return 1e-5

    def _run_gpu_validate(self, source_image, output_image=None):
        """Run GPU validation if enabled."""
        if not getattr(self.settings, 'gpu_validate', False):
            return
        validate_start = perf_counter()
        try:
            backend_name = getattr(self._array_backend, "name", "unknown")
            if not getattr(self._array_backend, "supports_gpu", False):
                self.validation_report = {
                    "status": "skipped",
                    "reason": "non_gpu_backend",
                    "backend": backend_name,
                }
                return

            candidate = np.asarray(source_image if output_image is None else output_image, dtype=np.float64)
            cpu_params = copy.deepcopy(self._params)
            cpu_params.settings.compute_backend = "cpu"
            cpu_params.settings.gpu_precision = "float64"
            cpu_params.settings.gpu_validate = False
            cpu_pipeline = SimulationPipeline(cpu_params)
            reference = np.asarray(cpu_pipeline.process(source_image), dtype=np.float64)

            tolerance = self._gpu_validation_tolerance()
            report = {
                "status": "ok",
                "backend": backend_name,
                "reference_backend": "cpu",
                "precision": getattr(self.settings, "gpu_precision", None),
                "tolerance": tolerance,
                "shape": tuple(candidate.shape),
                "reference_shape": tuple(reference.shape),
            }

            if candidate.shape != reference.shape:
                report.update(
                    {
                        "status": "failed",
                        "reason": "shape_mismatch",
                        "max_abs_diff": None,
                        "mean_abs_diff": None,
                        "finite": bool(np.all(np.isfinite(candidate)) and np.all(np.isfinite(reference))),
                    }
                )
                self.validation_report = report
                raise RuntimeError(
                    "GPU validation failed: output shape "
                    f"{candidate.shape} != CPU reference shape {reference.shape}"
                )

            finite = bool(np.all(np.isfinite(candidate)) and np.all(np.isfinite(reference)))
            diff = np.abs(candidate - reference)
            finite_diff = diff[np.isfinite(diff)]
            max_abs_diff = float(np.max(finite_diff)) if finite_diff.size else float("inf")
            mean_abs_diff = float(np.mean(finite_diff)) if finite_diff.size else float("inf")
            report.update(
                {
                    "max_abs_diff": max_abs_diff,
                    "mean_abs_diff": mean_abs_diff,
                    "finite": finite,
                }
            )

            if not finite or max_abs_diff > tolerance:
                report["status"] = "failed"
                if not finite:
                    report["reason"] = "non_finite_output"
                else:
                    report["reason"] = "tolerance_exceeded"
                self.validation_report = report
                raise RuntimeError(
                    "GPU validation failed: "
                    f"backend={backend_name}, max_abs_diff={max_abs_diff:.6g}, "
                    f"tolerance={tolerance:.6g}"
                )

            self.validation_report = report
        except Exception as exc:
            if not hasattr(self, "validation_report"):
                self.validation_report = {
                    "status": "failed",
                    "reason": "exception",
                    "error": str(exc),
                }
            raise
        finally:
            self.timings["SimulationPipeline.gpu_validate"] = perf_counter() - validate_start

    def get_timings(self):
        return self.timings

    def get_total_elapsed_time(self):
        return self._last_elapsed_time

    def format_timings(self):
        return format_timings(
            self.get_timings(),
            total_elapsed_time=self.get_total_elapsed_time(),
        )

    def print_timings(self):
        print(self.format_timings())

    def backend_runtime_summary(self) -> str:
        return runtime_backend_summary(self._backend)

    def update(self, params):
        """Update params and re-initialize stages that depend on them."""
        backend = getattr(self, "_backend", None)
        old_selection_key = getattr(self, "_backend_selection_key", None)
        new_selection_key = _backend_selection_key_from_settings(getattr(params, "settings", None))
        if (
            backend is not None
            and old_selection_key != new_selection_key
            and getattr(backend, "name", "") == "mlx"
            and hasattr(backend, "cleanup")
        ):
            backend.cleanup()
        self.__init__(params, update_params=True)

    def _should_cleanup_after_process(self) -> bool:
        if (
            getattr(self._backend, "name", "") != "mlx"
            or not hasattr(self._backend, "cleanup")
            or getattr(self.settings, "preview_mode", False)
        ):
            return False
        if bool(getattr(self.settings, "gpu_aggressive_cleanup", False)):
            return True

        threshold_mb = getattr(self.settings, "gpu_cleanup_cache_threshold_mb", 8192.0)
        if threshold_mb is None or float(threshold_mb) <= 0.0:
            return False
        cache_bytes = self._mlx_cache_memory_bytes()
        if cache_bytes is None:
            return False
        return cache_bytes >= int(float(threshold_mb) * 1024 * 1024)

    def _mlx_cache_memory_bytes(self) -> int | None:
        mx = getattr(self._backend, "mx", None)
        for owner in (mx, getattr(mx, "metal", None)):
            getter = getattr(owner, "get_cache_memory", None)
            if callable(getter):
                try:
                    return int(getter())
                except (OSError, RuntimeError, TypeError, ValueError):
                    return None
        return None

    def soft_update(self,
                    exposure_compensation_ev=None,
                    print_exposure=None,
                    c_filter_neutral=None,
                    m_filter_neutral=None,
                    y_filter_neutral=None,
                    film_density_curves=None,
                    print_density_curves=None,):
        invalidates_print_balance_reference = False
        refreshes_backend_print_tables = False
        if exposure_compensation_ev is not None:
            self.camera.exposure_compensation_ev = exposure_compensation_ev
            invalidates_print_balance_reference = True
        if print_exposure is not None:
            self.enlarger.print_exposure = print_exposure
        if c_filter_neutral is not None:
            self.enlarger.c_filter_neutral = c_filter_neutral
            refreshes_backend_print_tables = True
        if m_filter_neutral is not None:
            self.enlarger.m_filter_neutral = m_filter_neutral
            refreshes_backend_print_tables = True
        if y_filter_neutral is not None:
            self.enlarger.y_filter_neutral = y_filter_neutral
            refreshes_backend_print_tables = True
        if film_density_curves is not None:
            self.film.data.density_curves = film_density_curves
            invalidates_print_balance_reference = True
        if print_density_curves is not None:
            self.print.data.density_curves = print_density_curves
        if refreshes_backend_print_tables:
            self._printing_stage.refresh_backend_spectral_tables()
        if invalidates_print_balance_reference:
            (
                self._enlarger_service.density_spectral_midgray,
                self._enlarger_service.density_spectral_midgray_comp,
            ) = self._filming_stage._compute_density_spectral_midgray_to_balance_print()

    # private methods

    def _pipeline(self, image):
        image = self._record_stage_timing("preprocess", self._preprocess, image)
        if self.io.scan_film: # replace with route switch
            rgb_scan = self._pipeline_scan_film(image)
        else:
            rgb_scan = self._pipeline_print(image)
        return self._materialize_output(rgb_scan)

    def _pipeline_with_metadata(self, image) -> SimulationPipelineResult:
        image, hdr_scene_energy = self._record_stage_timing(
            "preprocess",
            self._preprocess_with_metadata,
            image,
        )
        if self.io.scan_film: # replace with route switch
            rgb_scan = self._pipeline_scan_film(image)
        else:
            rgb_scan = self._pipeline_print(image)
        return SimulationPipelineResult(
            image=self._materialize_output(rgb_scan),
            hdr_scene_energy=hdr_scene_energy,
        )

    def _pipeline_master(self, image, *, hdr_mode: HDRMode) -> RouteMaster:
        result = self._pipeline_with_master(image, hdr_mode=hdr_mode)
        if result.route_master is None:
            raise RuntimeError("RouteMaster pipeline completed without a RouteMaster.")
        return result.route_master

    def _pipeline_with_master(self, image, *, hdr_mode: HDRMode) -> SimulationPipelineResult:
        image, hdr_scene_energy = self._record_stage_timing(
            "preprocess",
            self._preprocess_with_metadata,
            image,
        )
        exposure = self._record_stage_timing(
            "filming.expose",
            self._filming_stage.expose_with_metadata,
            image,
        )
        cmy_film = self._record_stage_timing(
            "filming.develop",
            self._filming_stage.develop,
            exposure.log_raw,
        )
        diagnostics = dict(exposure.diagnostics)

        if hdr_mode == "light_table":
            scan_master = self._record_stage_timing(
                "scanning.scan_film_master",
                self._scanning_stage.scan_master,
                cmy_film,
            )
            sdr_legacy_rgb = self._record_stage_timing(
                "scanning.project_sdr_legacy",
                self._scanning_stage.project_sdr_legacy,
                scan_master,
            )
            diagnostics.update(scan_master.diagnostics)
            diagnostics["profile_kind"] = "positive_film_scan"
            if getattr(self.film, "is_negative", False):
                scan_master, sdr_legacy_rgb, render_diagnostics = self._positive_render_negative_scan_master(
                    scan_master,
                    exposure.scene_y_raw,
                )
                diagnostics.update(render_diagnostics)
            route_master = self._build_route_master(
                hdr_mode=hdr_mode,
                route_kind="film_scan",
                scan_master=scan_master,
                sdr_legacy_rgb=sdr_legacy_rgb,
                scene_y_raw=exposure.scene_y_raw,
                post_halation_y=exposure.post_halation_y,
                diagnostics=diagnostics,
            )
            return SimulationPipelineResult(
                image=self._materialize_output(sdr_legacy_rgb),
                hdr_scene_energy=hdr_scene_energy,
                route_master=route_master,
            )

        log_raw_print = self._record_stage_timing(
            "printing.expose",
            self._printing_stage.expose,
            cmy_film,
        )
        cmy_print = self._record_stage_timing(
            "printing.develop",
            self._printing_stage.develop,
            log_raw_print,
        )
        scan_master = self._record_stage_timing(
            "scanning.scan_print_master",
            self._scanning_stage.scan_master,
            cmy_print,
        )
        sdr_legacy_rgb = self._record_stage_timing(
            "scanning.project_sdr_legacy",
            self._scanning_stage.project_sdr_legacy,
            scan_master,
        )
        diagnostics.update(scan_master.diagnostics)
        diagnostics["profile_kind"] = "print_scan"
        route_master = self._build_route_master(
            hdr_mode=hdr_mode,
            route_kind="print_scan",
            scan_master=scan_master,
            sdr_legacy_rgb=sdr_legacy_rgb,
            scene_y_raw=exposure.scene_y_raw,
            post_halation_y=exposure.post_halation_y,
            diagnostics=diagnostics,
        )
        return SimulationPipelineResult(
            image=self._materialize_output(sdr_legacy_rgb),
            hdr_scene_energy=hdr_scene_energy,
            route_master=route_master,
        )
    
    def _preprocess(self, image):
        image, _auto_exposure_ev = self._preprocess_base(image)
        return image

    def _preprocess_with_metadata(self, image):
        image, auto_exposure_ev = self._preprocess_base(image)
        hdr_scene_energy = HDRSceneEnergyMetadata(
            scene_luminance=self._scene_luminance(image),
            auto_exposure_ev=auto_exposure_ev,
            input_color_space=self.io.input_color_space,
            input_cctf_decoding=bool(self.io.input_cctf_decoding),
        )
        return image, hdr_scene_energy

    def _preprocess_base(self, image):
        if self._should_use_backend_preprocess():
            return self._preprocess_base_backend(image)

        image = np.double(np.array(image)[:, :, 0:3])
        image, auto_exposure_ev = self._filming_stage.auto_exposure_with_ev(image) # autoexposure service?
        image = self._resize_service.crop_and_rescale(image)
        return image, auto_exposure_ev

    def _should_use_backend_preprocess(self) -> bool:
        return (
            getattr(self._backend, "supports_gpu", False)
            and str(getattr(self.settings, "gpu_precision", "float32")) == "float32"
        )

    def _backend_rgb_input(self, image):
        try:
            rgb = image[..., :3]
        except (TypeError, IndexError):
            rgb = np.asarray(image)[..., :3]
        dtype = getattr(self._backend, "default_dtype", np.float32)
        return self._backend.asarray(rgb, dtype=dtype)

    @staticmethod
    def _crop_slices(
        shape: tuple[int, int],
        *,
        center: tuple[float, float],
        size: tuple[float, float],
    ) -> tuple[slice, slice]:
        center_yx = np.flip(center)
        shape_arr = np.asarray(shape, dtype=np.float64)
        center_px = np.round(shape_arr * np.asarray(center_yx, dtype=np.float64))
        crop_size = np.round(np.double(np.max(shape_arr)) * np.flip(np.asarray(size, dtype=np.float64)))
        crop_size = np.minimum(crop_size, shape_arr).astype(np.int64)
        origin = np.round(center_px - crop_size / 2.0).astype(np.int64)
        origin[origin < 0] = 0
        if origin[0] + crop_size[0] > shape[0]:
            origin[0] = shape[0] - crop_size[0]
        if origin[1] + crop_size[1] > shape[1]:
            origin[1] = shape[1] - crop_size[1]
        return (
            slice(int(origin[0]), int(origin[0] + crop_size[0])),
            slice(int(origin[1]), int(origin[1] + crop_size[1])),
        )

    def _preprocess_base_backend(self, image):
        image = self._backend_rgb_input(image)
        image, auto_exposure_ev = self._backend_auto_exposure_with_ev(image)
        image = self._backend_crop_and_rescale(image)
        return image, auto_exposure_ev

    def _backend_auto_exposure_with_ev(self, image):
        if not self.camera.auto_exposure:
            return image, None

        preview_start = perf_counter()
        preview = self._backend_auto_exposure_preview(image)
        self.timings["SimulationPipeline.preprocess.auto_exposure_preview"] = (
            self.timings.get("SimulationPipeline.preprocess.auto_exposure_preview", 0.0)
            + (perf_counter() - preview_start)
        )
        autoexposure_ev = measure_autoexposure_ev(
            preview,
            self.io.input_color_space,
            self.io.input_cctf_decoding,
            method=self.camera.auto_exposure_method,
        )
        return image * (2 ** autoexposure_ev), float(autoexposure_ev)

    def _backend_auto_exposure_preview(self, image, *, max_size: int = 256) -> np.ndarray:
        h, w = (int(dim) for dim in image.shape[:2])
        max_dim = max(h, w)
        if max_dim <= max_size:
            return self._backend.to_numpy(image)
        step = int(np.ceil(max_dim / max_size))
        preview_backend = image[::step, ::step, :]
        return self._backend.to_numpy(preview_backend)

    def _backend_crop_and_rescale(self, image):
        h, w = (int(dim) for dim in image.shape[:2])
        self._resize_service.pixel_size_um = self.camera.film_format_mm * 1000 / max(h, w)

        if self.io.crop:
            y_slice, x_slice = self._crop_slices(
                (h, w),
                center=self.io.crop_center,
                size=self.io.crop_size,
            )
            image = image[y_slice, x_slice, :]

        if self.io.upscale_factor != 1.0:
            fallback_start = perf_counter()
            self._resize_service.pixel_size_um /= self.io.upscale_factor
            breaks_backend_residency = (
                getattr(self._backend, "name", None) == "mlx"
                and getattr(self.settings, "materialize_policy", None) == "backend"
            )
            image_np = self._backend.to_numpy(image)
            image_np = rescale(
                image_np,
                self.io.upscale_factor,
                channel_axis=2,
                order=3,
            )
            dtype = getattr(self._backend, "default_dtype", np.float32)
            image = self._backend.asarray(image_np, dtype=dtype)
            fallback_elapsed = perf_counter() - fallback_start
            self.timings["SimulationPipeline.preprocess.resize_cpu_fallback"] = (
                self.timings.get("SimulationPipeline.preprocess.resize_cpu_fallback", 0.0)
                + fallback_elapsed
            )
            if breaks_backend_residency:
                self.timings["SimulationPipeline.preprocess.resize_breaks_backend_residency"] = (
                    self.timings.get(
                        "SimulationPipeline.preprocess.resize_breaks_backend_residency",
                        0.0,
                    )
                    + fallback_elapsed
                )
        return image

    def _scene_luminance(self, image: np.ndarray) -> np.ndarray:
        if getattr(self._backend, "supports_gpu", False):
            image = self._materialize_sidecar_array(
                image,
                dtype=np.float32,
                label="SimulationPipeline.hdr_scene_luminance_materialize",
            )
        apply_cctf_decoding = bool(self.io.input_cctf_decoding)
        if is_aces_scene_linear_space(self.io.input_color_space):
            apply_cctf_decoding = False
        try:
            luminance = _luminance_y(
                image,
                self.io.input_color_space,
                apply_cctf_decoding,
            )
        except (AttributeError, LookupError, RuntimeError, TypeError, ValueError):
            luminance = np.tensordot(
                np.asarray(image)[..., :3],
                np.array([0.2126, 0.7152, 0.0722], dtype=float),
                axes=([-1], [0]),
            )
        luminance = np.nan_to_num(luminance, nan=0.0, posinf=0.0, neginf=0.0)
        return np.asarray(np.maximum(luminance, 0.0), dtype=np.float32)
    
    def _pipeline_scan_film(self, rgb_image):
        log_raw_film = self._record_stage_timing(
            "filming.expose",
            self._filming_stage.expose,
            rgb_image,
        )
        cmy_film = self._record_stage_timing(
            "filming.develop",
            self._filming_stage.develop,
            log_raw_film,
        )
        rgb_scan = self._record_stage_timing(
            "scanning.scan_film",
            self._scanning_stage.scan,
            cmy_film,
        )
        return rgb_scan

    def _positive_render_negative_scan_master(
        self,
        scan_master: ScanMasterResult,
        scene_y_raw,
    ) -> tuple[ScanMasterResult, np.ndarray, dict[str, object]]:
        raw_rgb = self._materialize_sidecar_array(
            scan_master.route_linear_rgb,
            dtype=np.float32,
            label="SimulationPipeline.route_master_materialize",
        )
        scene_y = self._materialize_sidecar_array(
            scene_y_raw,
            dtype=np.float32,
            label="SimulationPipeline.route_master_materialize",
        )
        positive_rgb, render_metadata = render_negative_scan_positive_rgb(
            raw_rgb,
            scene_y=scene_y.reshape(-1),
            return_metadata=True,
        )
        positive_xyz = np.asarray(
            colour.RGB_to_XYZ(
                positive_rgb,
                colourspace=self.io.output_color_space,
                apply_cctf_decoding=False,
            ),
            dtype=np.float32,
        )
        positive_y = luminance_y(positive_rgb)
        rendered_master = ScanMasterResult(
            route_linear_rgb=positive_rgb,
            route_linear_xyz=positive_xyz,
            route_luminance_y=positive_y,
            density_cmy=scan_master.density_cmy,
            diagnostics={
                **scan_master.diagnostics,
                "negative_scan_positive_rendering": True,
                "route_linear_xyz_source": "positive_render_rgb_to_xyz",
            },
        )
        diagnostics = {
            "profile_kind": "positive_negative_scan",
            "negative_scan_render": render_metadata,
            "negative_scan_positive_rendering": True,
            "route_linear_xyz_source": "positive_render_rgb_to_xyz",
        }
        return rendered_master, np.clip(positive_rgb, 0.0, 1.0).astype(np.float32, copy=False), diagnostics

    def _build_route_master(
        self,
        *,
        hdr_mode: HDRMode,
        route_kind: str,
        scan_master: ScanMasterResult,
        sdr_legacy_rgb,
        scene_y_raw,
        post_halation_y,
        diagnostics: dict[str, Any],
    ) -> RouteMaster:
        sidecar_policy = getattr(self.settings, "hdr_route_sidecar_policy", "minimal")
        if sidecar_policy not in {"minimal", "full"}:
            raise ValueError("hdr_route_sidecar_policy must be either 'minimal' or 'full'")
        full_sidecar = sidecar_policy == "full"

        route_rgb = self._route_sidecar_array(
            scan_master.route_linear_rgb,
            force_numpy=full_sidecar,
            label="SimulationPipeline.route_master_materialize",
        )
        route_y = self._route_sidecar_array(
            scan_master.route_luminance_y,
            force_numpy=full_sidecar,
            label="SimulationPipeline.route_master_materialize",
        )
        sdr_rgb = self._route_sidecar_array(
            sdr_legacy_rgb,
            force_numpy=full_sidecar,
            label="SimulationPipeline.route_master_materialize",
        )
        scene_y = self._route_sidecar_array(
            scene_y_raw,
            dtype=np.float32,
            force_numpy=full_sidecar,
            label="SimulationPipeline.route_master_materialize",
        )
        post_y = self._route_sidecar_array(
            post_halation_y,
            dtype=np.float32,
            force_numpy=full_sidecar,
            label="SimulationPipeline.route_master_materialize",
        )
        if full_sidecar:
            route_xyz = self._route_sidecar_array(
                scan_master.route_linear_xyz,
                force_numpy=True,
                label="SimulationPipeline.route_master_materialize",
            )
            density_cmy = self._route_sidecar_array(
                scan_master.density_cmy,
                force_numpy=True,
                label="SimulationPipeline.route_master_materialize",
            )
            route_look_chroma = self._route_look_chroma(route_rgb)
            material_detail_y = self._material_detail_y(route_y)
        else:
            route_xyz = None
            density_cmy = None
            route_look_chroma = None
            material_detail_y = None
        diagnostics = dict(diagnostics)
        diagnostics.setdefault("route_render_count", 1)
        diagnostics.setdefault("route_kind", route_kind)
        diagnostics.setdefault("hdr_route_sidecar_policy", sidecar_policy)
        diagnostics.setdefault("film", getattr(getattr(self.film, "info", None), "stock", None))
        diagnostics.setdefault("paper", getattr(getattr(self.print, "info", None), "stock", None))
        diagnostics.setdefault("output_color_space", self.io.output_color_space)
        diagnostics.setdefault("output_cctf_encoding", bool(self.io.output_cctf_encoding))
        diagnostics.setdefault("output_clip_min", bool(self.io.output_clip_min))
        diagnostics.setdefault("output_clip_max", bool(self.io.output_clip_max))
        return RouteMaster(
            mode=hdr_mode,
            route_kind=route_kind,  # type: ignore[arg-type]
            route_linear_rgb=route_rgb,
            route_linear_xyz=route_xyz,
            route_luminance_y=route_y,
            sdr_legacy_rgb=sdr_rgb,
            scene_y_raw=scene_y,
            post_halation_y=post_y,
            density_cmy=density_cmy,
            route_look_chroma=route_look_chroma,
            material_detail_y=material_detail_y,
            diagnostics=diagnostics,
        )

    @staticmethod
    def _route_look_chroma(route_rgb: np.ndarray) -> np.ndarray:
        route_rgb = np.asarray(route_rgb, dtype=np.float32)
        route_y = luminance_y(route_rgb)
        return np.divide(
            route_rgb,
            np.maximum(route_y[..., None], np.float32(1e-8)),
            out=np.zeros_like(route_rgb, dtype=np.float32),
            where=route_y[..., None] > np.float32(1e-8),
        )

    @staticmethod
    def _material_detail_y(route_y: np.ndarray) -> np.ndarray:
        y = np.asarray(route_y, dtype=np.float32)
        finite = y[np.isfinite(y) & (y > 0.0)]
        if finite.size == 0:
            return np.ones_like(y, dtype=np.float32)
        anchor = float(np.median(finite))
        detail = y / np.float32(max(anchor, 1e-8))
        return np.clip(detail, 0.5, 2.0).astype(np.float32)
    
    def _pipeline_print(self, rgb_image):
        log_raw_film = self._record_stage_timing(
            "filming.expose",
            self._filming_stage.expose,
            rgb_image,
        )
        cmy_film = self._record_stage_timing(
            "filming.develop",
            self._filming_stage.develop,
            log_raw_film,
        )
        log_raw_print = self._record_stage_timing(
            "printing.expose",
            self._printing_stage.expose,
            cmy_film,
        )
        cmy_print = self._record_stage_timing(
            "printing.develop",
            self._printing_stage.develop,
            log_raw_print,
        )
        rgb_scan = self._record_stage_timing(
            "scanning.scan_print",
            self._scanning_stage.scan,
            cmy_print,
        )
        return rgb_scan
    

    def _build_topology(self) -> list[Node]:
        f, p, s = self._filming_stage, self._printing_stage, self._scanning_stage
        common = [
            Node((Tap.RGB_IN,),     (Tap.RGB_PRE,),    self._preprocess, "preprocess"),
            Node((Tap.RGB_PRE,),    (Tap.LOG_E_FILM,), f.expose,         "filming.expose"),
            Node((Tap.LOG_E_FILM,), (Tap.CMY_FILM,),   f.develop,        "filming.develop"),
        ]
        if self.io.scan_film:
            return common + [
                Node((Tap.CMY_FILM,), (Tap.RGB_OUT,), s.scan, "scanning.scan_film"),
            ]
        return common + [
            Node((Tap.CMY_FILM,),    (Tap.LOG_E_PRINT,), p.expose,  "printing.expose"),
            Node((Tap.LOG_E_PRINT,), (Tap.CMY_PRINT,),   p.develop, "printing.develop"),
            Node((Tap.CMY_PRINT,),   (Tap.RGB_OUT,),     s.scan,    "scanning.scan_print"),
        ]

    def _record_node_timing(self, node: Node, elapsed: float) -> None:
        self.timings[node.label] = self.timings.get(node.label, 0.0) + elapsed

    def _record_stage_timing(self, label: str, func, *args):
        start = perf_counter()
        try:
            return func(*args)
        finally:
            self.timings[label] = self.timings.get(label, 0.0) + (perf_counter() - start)

    def _materialize_output(self, image):
        return self._record_stage_timing(
            "SimulationPipeline.materialize",
            self._materialize_output_value,
            image,
        )

    def _materialize_output_value(self, value):
        policy = getattr(self.settings, "materialize_policy", "numpy_float64")
        if policy == "backend":
            if getattr(self._backend, "supports_gpu", False):
                return value
            return np.asarray(value)
        if policy == "numpy_float32":
            return np.asarray(value, dtype=np.float32)
        if policy == "numpy_float64":
            return np.asarray(value, dtype=np.float64)
        raise ValueError(
            "materialize_policy must be one of: 'numpy_float64', 'numpy_float32', 'backend'"
        )

    def _materialize_sidecar_array(
        self,
        value,
        *,
        dtype=None,
        label: str = "SimulationPipeline.sidecar_materialize",
    ) -> np.ndarray:
        return self._record_stage_timing(
            label,
            self._materialize_sidecar_array_value,
            value,
            dtype,
        )

    def _materialize_sidecar_array_value(self, value, dtype=None) -> np.ndarray:
        policy = getattr(self.settings, "materialize_policy", "numpy_float64")
        if (
            policy == "backend"
            and getattr(self._backend, "supports_gpu", False)
            and hasattr(self._backend, "to_numpy")
        ):
            array = self._backend.to_numpy(value)
        else:
            array = self._materialize_output_value(value)
        if dtype is not None:
            return np.asarray(array, dtype=dtype)
        return np.asarray(array)

    def _route_sidecar_array(
        self,
        value,
        *,
        dtype=None,
        force_numpy: bool = False,
        label: str = "SimulationPipeline.route_master_materialize",
    ):
        return self._record_stage_timing(
            label,
            self._route_sidecar_array_value,
            value,
            dtype,
            force_numpy,
        )

    def _route_sidecar_array_value(self, value, dtype=None, force_numpy: bool = False):
        if value is None:
            return None
        policy = getattr(self.settings, "materialize_policy", "numpy_float64")
        if (
            not force_numpy
            and policy == "backend"
            and getattr(self._backend, "supports_gpu", False)
        ):
            return value
        if (
            force_numpy
            and policy == "backend"
            and getattr(self._backend, "supports_gpu", False)
            and hasattr(self._backend, "to_numpy")
        ):
            array = self._backend.to_numpy(value)
        else:
            array = self._materialize_output_value(value)
        if dtype is not None:
            return np.asarray(array, dtype=dtype)
        return np.asarray(array)
