from __future__ import annotations

import ctypes
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
import sys
import time
from typing import Any, Callable

import numpy as np
from qtpy import QtCore

from spektrafilm.color_management import aces_sdr_video_view_transform, is_aces_scene_linear_space
from spektrafilm.utils.io import resolve_icc_profile_bytes


DISPLAY_PREVIEW_COLOR_SPACE = 'sRGB'
QObject = getattr(QtCore, 'QObject')
QRunnable = getattr(QtCore, 'QRunnable')
Signal = getattr(QtCore, 'Signal')


@dataclass(slots=True)
class SimulationRequest:
    mode_label: str
    image: np.ndarray
    params: object
    output_color_space: str
    use_display_transform: bool
    output_cctf_encoding: bool = True
    phase_timings: dict[str, float] = field(default_factory=dict)
    memory_estimates: dict[str, int] = field(default_factory=dict)
    require_hdr_metadata: bool = False


@dataclass(slots=True)
class SimulationResult:
    mode_label: str
    display_image: np.ndarray
    float_image: np.ndarray
    output_color_space: str
    use_display_transform: bool
    status_message: str
    output_cctf_encoding: bool = True
    hdr_scene_energy: object | None = None
    phase_timings: dict[str, float] = field(default_factory=dict)
    runtime_stage_timings: dict[str, float] = field(default_factory=dict)
    memory_estimates: dict[str, int] = field(default_factory=dict)


class SimulationWorkerSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class SimulationWorker(QRunnable):
    def __init__(self, request: SimulationRequest, *, execute_request: Callable[[SimulationRequest], SimulationResult]):
        super().__init__()
        self._request = request
        self._execute_request = execute_request
        self.signals = SimulationWorkerSignals()

    def run(self) -> None:
        try:
            result = self._execute_request(self._request)
        except BaseException as exc:
            self.signals.failed.emit(f'{type(exc).__name__}: {exc}')
            return
        self.signals.finished.emit(result)


def normalized_image_data(image: np.ndarray, *, preserve_highlights: bool = False) -> np.ndarray:
    if np.issubdtype(image.dtype, np.floating):
        if preserve_highlights:
            return np.clip(image.astype(np.float32, copy=False), 0.0, None)
        return np.clip(image, 0.0, 1.0)
    if np.issubdtype(image.dtype, np.integer):
        max_value = np.iinfo(image.dtype).max
        if max_value == 0:
            return image.astype(np.float32)
        return image.astype(np.float32) / max_value
    return image.astype(np.float32)


def array_nbytes(value: object | None) -> int:
    if value is None:
        return 0
    nbytes = getattr(value, "nbytes", None)
    if nbytes is not None:
        return int(nbytes)
    shape = getattr(value, "shape", None)
    dtype = getattr(value, "dtype", None)
    if shape is None or dtype is None:
        return 0
    try:
        return int(np.prod(tuple(int(dim) for dim in shape)) * np.dtype(dtype).itemsize)
    except (TypeError, ValueError):
        return 0


def _record_phase_timing(phase_timings: dict[str, float] | None, key: str, elapsed: float) -> None:
    if phase_timings is None:
        return
    phase_timings[key] = phase_timings.get(key, 0.0) + float(elapsed)


def apply_white_padding(image_data: np.ndarray, padding_pixels: float) -> np.ndarray:
    padding = max(0, int(round(padding_pixels)))
    if padding == 0:
        return np.asarray(image_data)

    image = np.asarray(image_data)
    if image.ndim < 2:
        return image

    fill_value = np.iinfo(image.dtype).max if np.issubdtype(image.dtype, np.integer) else 1.0
    pad_width = [(padding, padding), (padding, padding)]
    pad_width.extend((0, 0) for _ in range(image.ndim - 2))
    return np.pad(image, pad_width, mode='constant', constant_values=fill_value)


def padding_pixels_for_image(image_data: np.ndarray, padding_fraction: float) -> int:
    image = np.asarray(image_data)
    if image.ndim < 2:
        return 0

    padding_fraction = max(0.0, float(padding_fraction))
    long_edge = max(int(image.shape[0]), int(image.shape[1]))
    return int(np.floor(long_edge * padding_fraction))


def _imagecms_error_type(imagecms_module: Any) -> type[BaseException]:
    pycms_error = getattr(imagecms_module, 'PyCMSError', RuntimeError)
    if isinstance(pycms_error, type) and issubclass(pycms_error, BaseException):
        return pycms_error
    return RuntimeError


def display_profile_name(display_profile: object, *, imagecms_module: Any) -> str:
    pycms_error = _imagecms_error_type(imagecms_module)
    try:
        profile_name = imagecms_module.getProfileName(display_profile)
    except (AttributeError, OSError, ValueError, TypeError, pycms_error):
        profile_name = None

    if isinstance(profile_name, str):
        cleaned_name = profile_name.replace('\x00', ' ').strip()
        if cleaned_name:
            return ' '.join(cleaned_name.split())

    profile_filename = getattr(display_profile, 'filename', None)
    if isinstance(profile_filename, str) and profile_filename.strip():
        return Path(profile_filename).stem

    return type(display_profile).__name__


def _running_under_pytest() -> bool:
    return "pytest" in sys.modules


def _mac_display_profile_fallback_enabled() -> bool:
    return sys.platform == "darwin" and not _running_under_pytest()


def _configure_coregraphics_display_profile_functions(core_foundation: Any, core_graphics: Any) -> None:
    core_graphics.CGMainDisplayID.restype = ctypes.c_uint32

    core_graphics.CGDisplayCopyColorSpace.argtypes = [ctypes.c_uint32]
    core_graphics.CGDisplayCopyColorSpace.restype = ctypes.c_void_p

    core_graphics.CGColorSpaceCopyICCData.argtypes = [ctypes.c_void_p]
    core_graphics.CGColorSpaceCopyICCData.restype = ctypes.c_void_p

    core_foundation.CFDataGetLength.argtypes = [ctypes.c_void_p]
    core_foundation.CFDataGetLength.restype = ctypes.c_long

    core_foundation.CFDataGetBytePtr.argtypes = [ctypes.c_void_p]
    core_foundation.CFDataGetBytePtr.restype = ctypes.c_void_p

    core_foundation.CFRelease.argtypes = [ctypes.c_void_p]
    core_foundation.CFRelease.restype = None


def _release_core_foundation_object(core_foundation: Any | None, ref: object | None) -> None:
    if core_foundation is None or not ref:
        return
    try:
        core_foundation.CFRelease(ref)
    except Exception:
        return


def _get_mac_display_profile_bytes() -> bytes | None:
    if sys.platform != "darwin":
        return None

    core_foundation = None
    color_space = None
    icc_data = None
    try:
        core_foundation = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        core_graphics = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
        _configure_coregraphics_display_profile_functions(core_foundation, core_graphics)

        display_id = core_graphics.CGMainDisplayID()
        if not display_id:
            return None

        color_space = core_graphics.CGDisplayCopyColorSpace(display_id)
        if not color_space:
            return None

        icc_data = core_graphics.CGColorSpaceCopyICCData(color_space)
        if not icc_data:
            return None

        length = core_foundation.CFDataGetLength(icc_data)
        if length <= 0:
            return None

        ptr = core_foundation.CFDataGetBytePtr(icc_data)
        if not ptr:
            return None

        return ctypes.string_at(ptr, int(length))
    except Exception:
        return None
    finally:
        _release_core_foundation_object(core_foundation, icc_data)
        _release_core_foundation_object(core_foundation, color_space)


def _display_profile_from_fallback(*, imagecms_module: Any) -> object | None:
    if not _mac_display_profile_fallback_enabled():
        return None
    icc_bytes = _get_mac_display_profile_bytes()
    if not icc_bytes:
        return None
    pycms_error = _imagecms_error_type(imagecms_module)
    try:
        return imagecms_module.ImageCmsProfile(BytesIO(icc_bytes))
    except (AttributeError, OSError, ValueError, TypeError, pycms_error):
        return None


def _resolve_display_profile(*, imagecms_module: Any) -> object | None:
    pycms_error = _imagecms_error_type(imagecms_module)
    try:
        display_profile = imagecms_module.get_display_profile()
    except (AttributeError, OSError, ValueError, TypeError, pycms_error):
        display_profile = None
    if display_profile is not None:
        return display_profile
    return _display_profile_from_fallback(imagecms_module=imagecms_module)


def display_profile_details(*, imagecms_module: Any) -> tuple[object | None, str | None]:
    display_profile = _resolve_display_profile(imagecms_module=imagecms_module)
    if display_profile is None:
        return None, None
    return display_profile, display_profile_name(display_profile, imagecms_module=imagecms_module)


def display_profile_available(*, imagecms_module: Any) -> bool:
    return _resolve_display_profile(imagecms_module=imagecms_module) is not None


def display_transform_status_message(enabled: bool, *, imagecms_module: Any) -> str:
    if not enabled:
        return 'Display transform: disabled'
    display_profile, profile_name = display_profile_details(imagecms_module=imagecms_module)
    if display_profile is None:
        return 'Display transform: no display profile, using raw preview'
    return f'Display transform: display profile found ({profile_name})'


def prepare_input_color_preview_image(
    image_data: np.ndarray,
    *,
    input_color_space: str,
    apply_cctf_decoding: bool,
    colour_module: Any,
) -> np.ndarray:
    normalized_image = normalized_image_data(np.asarray(image_data)[..., :3])
    try:
        srgb_preview = colour_module.RGB_to_RGB(
            normalized_image,
            input_color_space,
            DISPLAY_PREVIEW_COLOR_SPACE,
            apply_cctf_decoding=apply_cctf_decoding,
            apply_cctf_encoding=True,
        )
    except (AttributeError, LookupError, RuntimeError, TypeError, ValueError):
        return np.asarray(np.clip(normalized_image, 0.0, 1.0), dtype=np.float32)
    return np.asarray(np.clip(srgb_preview, 0.0, 1.0), dtype=np.float32)


def apply_display_transform(
    image_data: np.ndarray,
    *,
    output_color_space: str,
    output_cctf_encoding: bool,
    colour_module: Any,
    imagecms_module: Any,
    pil_image_module: Any,
) -> tuple[np.ndarray, str]:
    if is_aces_scene_linear_space(output_color_space):
        preview = aces_sdr_video_view_transform(
            image_data,
            color_space=output_color_space,
            colour_module=colour_module,
        )
        return (
            np.uint8(np.clip(preview, 0.0, 1.0) * 255),
            'Display transform: ACES SDR video output transform',
        )

    if not output_cctf_encoding:
        srgb_preview = colour_module.RGB_to_RGB(
            image_data,
            output_color_space,
            DISPLAY_PREVIEW_COLOR_SPACE,
            apply_cctf_decoding=False,
            apply_cctf_encoding=True,
        )
        return (
            np.uint8(np.clip(srgb_preview, 0.0, 1.0) * 255),
            'Display transform: linear scene preview, using sRGB display encoding',
        )

    display_profile, profile_name = display_profile_details(imagecms_module=imagecms_module)
    if display_profile is None:
        return np.uint8(np.clip(image_data, 0.0, 1.0) * 255), 'Display transform: no display profile, using raw preview'

    source_profile = imagecms_profile_for_color_space(
        output_color_space,
        output_cctf_encoding=output_cctf_encoding,
        imagecms_module=imagecms_module,
    )
    source_image_data = np.uint8(np.clip(image_data, 0.0, 1.0) * 255)
    if source_profile is None:
        srgb_preview = colour_module.RGB_to_RGB(
            image_data,
            output_color_space,
            DISPLAY_PREVIEW_COLOR_SPACE,
            apply_cctf_decoding=True,
            apply_cctf_encoding=True,
        )
        source_image_data = np.uint8(np.clip(srgb_preview, 0.0, 1.0) * 255)
        source_profile = imagecms_module.createProfile(DISPLAY_PREVIEW_COLOR_SPACE)

    source_image = pil_image_module.fromarray(source_image_data, mode='RGB')
    transformed_image = imagecms_module.profileToProfile(source_image, source_profile, display_profile, outputMode='RGB')
    return np.asarray(transformed_image, dtype=np.uint8), f'Display transform: active ({profile_name})'


def imagecms_profile_for_color_space(
    color_space: str,
    *,
    output_cctf_encoding: bool,
    imagecms_module: Any,
) -> object | None:
    icc_bytes = resolve_icc_profile_bytes(color_space, output_cctf_encoding)
    if icc_bytes is not None and hasattr(imagecms_module, 'ImageCmsProfile'):
        return imagecms_module.ImageCmsProfile(BytesIO(icc_bytes))
    if output_cctf_encoding:
        pycms_error = getattr(imagecms_module, 'PyCMSError', RuntimeError)
        try:
            return imagecms_module.createProfile(color_space)
        except (AttributeError, OSError, ValueError, TypeError, pycms_error):
            if color_space == DISPLAY_PREVIEW_COLOR_SPACE:
                return imagecms_module.createProfile(DISPLAY_PREVIEW_COLOR_SPACE)
    return None


def prepare_output_display_image(
    image_data: np.ndarray,
    *,
    output_color_space: str,
    output_cctf_encoding: bool = True,
    use_display_transform: bool,
    padding_pixels: float = 0.0,
    imagecms_module: Any,
    colour_module: Any,
    pil_image_module: Any,
    phase_timings: dict[str, float] | None = None,
) -> tuple[np.ndarray, str]:
    del padding_pixels
    source_image = np.asarray(image_data)[..., :3]
    uint8_start = time.perf_counter()
    preview_image = np.uint8(np.clip(normalized_image_data(source_image), 0.0, 1.0) * 255)
    _record_phase_timing(phase_timings, "gui.display_uint8", time.perf_counter() - uint8_start)
    if not use_display_transform:
        return preview_image, display_transform_status_message(False, imagecms_module=imagecms_module)
    preserve_scene_highlights = is_aces_scene_linear_space(output_color_space) or not output_cctf_encoding
    transform_image = normalized_image_data(source_image, preserve_highlights=preserve_scene_highlights)
    pycms_error = getattr(imagecms_module, 'PyCMSError', RuntimeError)
    transform_start = time.perf_counter()
    try:
        transformed_image, status = apply_display_transform(
            transform_image,
            output_color_space=output_color_space,
            output_cctf_encoding=output_cctf_encoding,
            colour_module=colour_module,
            imagecms_module=imagecms_module,
            pil_image_module=pil_image_module,
        )
        return transformed_image, status
    except (AttributeError, LookupError, OSError, RuntimeError, ValueError, TypeError, pycms_error):
        return preview_image, 'Display transform: transform failed, using raw preview'
    finally:
        _record_phase_timing(phase_timings, "gui.display_transform", time.perf_counter() - transform_start)


def _format_phase_timing_summary(phase_timings: dict[str, float]) -> str:
    ordered = (
        ("process", "runtime.process"),
        ("display", "gui.display_prepare"),
        ("materialize", "gui.float_materialize"),
    )
    parts = [
        f"{label}={phase_timings[key]:.2f}s"
        for label, key in ordered
        if key in phase_timings
    ]
    return ", ".join(parts)


def execute_simulation_request(
    request: SimulationRequest,
    *,
    run_simulation_fn: Callable[..., np.ndarray],
    prepare_output_display_image_fn: Callable[..., tuple[np.ndarray, str]],
    runtime_status_fn: Callable[[], str | None] | None = None,
    runtime_timings_fn: Callable[[], dict[str, float] | None] | None = None,
) -> SimulationResult:
    phase_timings = dict(getattr(request, "phase_timings", {}) or {})
    memory_estimates = dict(getattr(request, "memory_estimates", {}) or {})
    start_time = time.perf_counter()

    process_start = time.perf_counter()
    if request.require_hdr_metadata:
        simulation_output = run_simulation_fn(
            request.image,
            request.params,
            require_hdr_metadata=True,
        )
    else:
        simulation_output = run_simulation_fn(request.image, request.params)
    phase_timings["runtime.process"] = time.perf_counter() - process_start

    scan = getattr(simulation_output, 'image', simulation_output)
    hdr_scene_energy = getattr(simulation_output, 'hdr_scene_energy', None)

    materialize_start = time.perf_counter()
    scan_array = np.asarray(scan)
    phase_timings["gui.float_materialize"] = time.perf_counter() - materialize_start
    if isinstance(scan, np.ndarray) and np.shares_memory(scan_array, scan):
        memory_estimates["gui.float_materialize_copy_nbytes"] = 0
    else:
        memory_estimates["gui.float_materialize_copy_nbytes"] = array_nbytes(scan_array)
    memory_estimates["gui.float_image_nbytes"] = array_nbytes(scan_array)

    display_start = time.perf_counter()
    scan_display, display_status = prepare_output_display_image_fn(
        scan_array,
        output_color_space=request.output_color_space,
        output_cctf_encoding=request.output_cctf_encoding,
        use_display_transform=request.use_display_transform,
        phase_timings=phase_timings,
    )
    phase_timings["gui.display_prepare"] = time.perf_counter() - display_start
    memory_estimates["gui.display_image_nbytes"] = array_nbytes(scan_display)
    scene_luminance = getattr(hdr_scene_energy, "scene_luminance", None)
    scene_rgb = getattr(hdr_scene_energy, "scene_rgb", None)
    memory_estimates["gui.hdr_scene_luminance_nbytes"] = array_nbytes(scene_luminance)
    memory_estimates["gui.hdr_scene_rgb_nbytes"] = array_nbytes(scene_rgb)

    elapsed_time = time.perf_counter() - start_time
    phase_timings["gui.worker_total"] = elapsed_time
    runtime_status = runtime_status_fn() if runtime_status_fn is not None else None
    runtime_stage_timings = dict(runtime_timings_fn() or {}) if runtime_timings_fn is not None else {}
    
    parts = [display_status]
    if runtime_status:
        parts.append(runtime_status)
    parts.append(f"{elapsed_time:.2f}s")
    timing_summary = _format_phase_timing_summary(phase_timings)
    if timing_summary:
        parts.append(timing_summary)
    status_message = " | ".join(parts)
    return SimulationResult(
        mode_label=request.mode_label,
        display_image=scan_display,
        float_image=scan_array,
        output_color_space=request.output_color_space,
        output_cctf_encoding=request.output_cctf_encoding,
        use_display_transform=request.use_display_transform,
        status_message=status_message,
        hdr_scene_energy=hdr_scene_energy,
        phase_timings=phase_timings,
        runtime_stage_timings=runtime_stage_timings,
        memory_estimates=memory_estimates,
    )
