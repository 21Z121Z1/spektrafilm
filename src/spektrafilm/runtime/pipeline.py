from __future__ import annotations

import copy
from dataclasses import dataclass
from time import perf_counter

import numpy as np

from spektrafilm.color_management import is_aces_scene_linear_space
from spektrafilm.runtime.services import (
    EnlargerService,
    ResizingService,
    SpectralLUTService,
    ColorReferenceService,
)
from spektrafilm.gpu.backend import select_backend
from spektrafilm.runtime.stages import FilmingStage, PrintingStage, ScanningStage
from spektrafilm.runtime.topology import Node, Tap, run_topology
from spektrafilm.utils.autoexposure import _luminance_y
from spektrafilm.utils.timings import format_timings


@dataclass(slots=True)
class HDRSceneEnergyMetadata:
    scene_luminance: np.ndarray
    auto_exposure_ev: float | None
    input_color_space: str
    input_cctf_decoding: bool


@dataclass(slots=True)
class SimulationPipelineResult:
    image: np.ndarray
    hdr_scene_energy: HDRSceneEnergyMetadata | None = None


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
            self._last_elapsed_time = perf_counter() - start

    def _process_topology(self, image, *, inject: str | None = None, collect: str | None = None):
        inject = inject or self.taps.inject or Tap.RGB_IN
        collect = collect or self.taps.collect or Tap.RGB_OUT

        self.timings.clear()
        start = perf_counter()
        try:
            return run_topology(
                self._topology, inject, collect, image,
                on_fire=self._record_node_timing,
            )
        finally:
            self._last_elapsed_time = perf_counter() - start

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
        image = self._preprocess(image)
        if self.io.scan_film: # replace with route switch
            rgb_scan = self._pipeline_scan_film(image)
        else:
            rgb_scan = self._pipeline_print(image)
        return np.asarray(rgb_scan, dtype=np.float64)

    def _pipeline_with_metadata(self, image) -> SimulationPipelineResult:
        image, hdr_scene_energy = self._preprocess_with_metadata(image)
        if self.io.scan_film: # replace with route switch
            rgb_scan = self._pipeline_scan_film(image)
        else:
            rgb_scan = self._pipeline_print(image)
        return SimulationPipelineResult(
            image=np.asarray(rgb_scan, dtype=np.float64),
            hdr_scene_energy=hdr_scene_energy,
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
        image = np.double(np.array(image)[:, :, 0:3])
        image, auto_exposure_ev = self._filming_stage.auto_exposure_with_ev(image) # autoexposure service?
        image = self._resize_service.crop_and_rescale(image)
        return image, auto_exposure_ev

    def _scene_luminance(self, image: np.ndarray) -> np.ndarray:
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
        log_raw_film = self._filming_stage.expose(rgb_image)
        cmy_film = self._filming_stage.develop(log_raw_film)
        rgb_scan = self._scanning_stage.scan(cmy_film)
        return rgb_scan
    
    def _pipeline_print(self, rgb_image):
        log_raw_film = self._filming_stage.expose(rgb_image)
        cmy_film = self._filming_stage.develop(log_raw_film)
        log_raw_print = self._printing_stage.expose(cmy_film)
        cmy_print = self._printing_stage.develop(log_raw_print)
        rgb_scan = self._scanning_stage.scan(cmy_print)
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
