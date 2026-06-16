from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import inspect
from pathlib import Path
from typing import Any, Iterable

import numpy as np


_ACTIVE_RECORDER: ContextVar["ResidencyRecorder | None"] = ContextVar(
    "spektrafilm_residency_recorder",
    default=None,
)


DEFAULT_ALLOWED_STACK_FRAGMENTS: tuple[str, ...] = (
    "_backend_auto_exposure_preview",
    "_backend_crop_and_rescale",
    "_run_gpu_validate",
    "_materialize_output_value",
    "_to_numpy_scalar",
    "_spectral_calculation_numpy",
    "spectral_lut_compute.py",
    "_positive_render_negative_scan_master",
    "_build_route_master",
    "_materialize_sidecar_array",
    "_scene_luminance",
    "_debug_mlx_kernel_nan_check",
)


@dataclass(frozen=True)
class ResidencyEvent:
    direction: str
    backend: str
    shape: tuple[int, ...] | None
    dtype: str | None
    nbytes: int | None
    stack_label: str
    allowed: bool
    reason: str


class ResidencyRecorder:
    """Collect backend conversion events for runtime residency diagnostics."""

    def __init__(
        self,
        *,
        small_array_bytes: int = 64 * 1024,
        allowed_stack_fragments: Iterable[str] = DEFAULT_ALLOWED_STACK_FRAGMENTS,
    ) -> None:
        self.small_array_bytes = int(small_array_bytes)
        self.allowed_stack_fragments = tuple(str(fragment) for fragment in allowed_stack_fragments)
        self.events: list[ResidencyEvent] = []

    def record(self, direction: str, backend: str, value: Any, result: Any | None = None) -> None:
        shape, dtype, nbytes = _array_info(result if result is not None else value)
        stack_label = _caller_label()
        allowed, reason = self._classify(direction, nbytes, stack_label)
        self.events.append(
            ResidencyEvent(
                direction=direction,
                backend=str(backend),
                shape=shape,
                dtype=dtype,
                nbytes=nbytes,
                stack_label=stack_label,
                allowed=allowed,
                reason=reason,
            )
        )

    def _classify(self, direction: str, nbytes: int | None, stack_label: str) -> tuple[bool, str]:
        if direction == "asarray":
            return True, "backend_upload"
        if direction != "to_numpy":
            return True, "not_host_readback"
        if nbytes is not None and nbytes <= self.small_array_bytes:
            return True, "small_array"
        for fragment in self.allowed_stack_fragments:
            if fragment and fragment in stack_label:
                return True, f"allowed_stack:{fragment}"
        return False, "unallowed_full_size_to_numpy"

    def unallowed_events(self) -> list[ResidencyEvent]:
        return [event for event in self.events if not event.allowed]

    def unallowed_to_numpy_events(self) -> list[ResidencyEvent]:
        return [
            event for event in self.events
            if event.direction == "to_numpy" and not event.allowed
        ]

    def summary(self) -> dict[str, int]:
        return {
            "events": len(self.events),
            "to_numpy": sum(1 for event in self.events if event.direction == "to_numpy"),
            "asarray": sum(1 for event in self.events if event.direction == "asarray"),
            "unallowed": len(self.unallowed_events()),
            "unallowed_to_numpy": len(self.unallowed_to_numpy_events()),
        }


@contextmanager
def record_backend_residency(
    *,
    small_array_bytes: int = 64 * 1024,
    allowed_stack_fragments: Iterable[str] = DEFAULT_ALLOWED_STACK_FRAGMENTS,
):
    recorder = ResidencyRecorder(
        small_array_bytes=small_array_bytes,
        allowed_stack_fragments=allowed_stack_fragments,
    )
    token = _ACTIVE_RECORDER.set(recorder)
    try:
        yield recorder
    finally:
        _ACTIVE_RECORDER.reset(token)


def record_conversion(direction: str, backend: str, value: Any, result: Any | None = None) -> None:
    recorder = _ACTIVE_RECORDER.get()
    if recorder is None:
        return
    recorder.record(direction, backend, value, result)


def _array_info(value: Any) -> tuple[tuple[int, ...] | None, str | None, int | None]:
    shape_obj = getattr(value, "shape", None)
    dtype_obj = getattr(value, "dtype", None)
    shape = tuple(int(dim) for dim in shape_obj) if shape_obj is not None else None
    dtype = str(dtype_obj) if dtype_obj is not None else None

    nbytes_obj = getattr(value, "nbytes", None)
    if nbytes_obj is not None:
        try:
            return shape, dtype, int(nbytes_obj)
        except (TypeError, ValueError):
            pass

    if shape is None:
        return shape, dtype, None

    itemsize = _dtype_itemsize(dtype_obj)
    if itemsize is None:
        return shape, dtype, None
    return shape, dtype, int(np.prod(shape, dtype=np.int64)) * itemsize


def _dtype_itemsize(dtype: Any) -> int | None:
    if dtype is None:
        return None
    try:
        return int(np.dtype(dtype).itemsize)
    except TypeError:
        text = str(dtype)
        if "float64" in text or "int64" in text:
            return 8
        if "float32" in text or "int32" in text:
            return 4
        if "float16" in text or "int16" in text:
            return 2
        if "bool" in text or "int8" in text:
            return 1
    return None


def _caller_label() -> str:
    for frame in inspect.stack(context=0)[2:]:
        filename = Path(frame.filename)
        name = filename.name
        if name == "residency.py":
            continue
        if filename.parent.name == "gpu" and name.endswith("_backend.py"):
            continue
        return f"{filename}:{frame.function}:{frame.lineno}"
    return "<unknown>"
