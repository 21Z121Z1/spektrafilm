from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import inspect
import json
from pathlib import Path
from time import perf_counter
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
    "_rgb_to_film_raw",
    "spectral_lut_compute.py",
    "_positive_render_negative_scan_master",
    "_build_route_master",
    "_materialize_sidecar_array",
    "_scene_luminance",
    "_debug_mlx_kernel_nan_check",
    "final_encoder_boundary",
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
    elapsed_seconds: float | None = None
    category: str | None = None
    peak_memory_before_bytes: int | None = None
    peak_memory_after_bytes: int | None = None
    cache_memory_before_bytes: int | None = None
    cache_memory_after_bytes: int | None = None


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

    def record(
        self,
        direction: str,
        backend: str,
        value: Any,
        result: Any | None = None,
        *,
        elapsed_seconds: float | None = None,
        category: str | None = None,
        memory_before: dict[str, int | None] | None = None,
        memory_after: dict[str, int | None] | None = None,
    ) -> None:
        shape, dtype, nbytes = _array_info(result if result is not None else value)
        stack_label = _caller_label()
        category = category or _category_for(direction, shape, nbytes, stack_label)
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
                elapsed_seconds=elapsed_seconds,
                category=category,
                peak_memory_before_bytes=(memory_before or {}).get("peak_memory_bytes"),
                peak_memory_after_bytes=(memory_after or {}).get("peak_memory_bytes"),
                cache_memory_before_bytes=(memory_before or {}).get("cache_memory_bytes"),
                cache_memory_after_bytes=(memory_after or {}).get("cache_memory_bytes"),
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
        summary = {
            "events": len(self.events),
            "to_numpy": sum(1 for event in self.events if event.direction == "to_numpy"),
            "asarray": sum(1 for event in self.events if event.direction == "asarray"),
            "unallowed": len(self.unallowed_events()),
            "unallowed_to_numpy": len(self.unallowed_to_numpy_events()),
        }
        for direction in ("eval", "synchronize", "cleanup", "clear_cache"):
            summary[direction] = sum(1 for event in self.events if event.direction == direction)
        return summary

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary(),
            "events": [
                {
                    "direction": event.direction,
                    "backend": event.backend,
                    "shape": list(event.shape) if event.shape is not None else None,
                    "dtype": event.dtype,
                    "nbytes": event.nbytes,
                    "stack_label": event.stack_label,
                    "allowed": event.allowed,
                    "reason": event.reason,
                    "elapsed_seconds": event.elapsed_seconds,
                    "category": event.category,
                    "peak_memory_before_bytes": event.peak_memory_before_bytes,
                    "peak_memory_after_bytes": event.peak_memory_after_bytes,
                    "cache_memory_before_bytes": event.cache_memory_before_bytes,
                    "cache_memory_after_bytes": event.cache_memory_after_bytes,
                }
                for event in self.events
            ],
        }

    def write_json(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self.to_json_dict(), indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def write_markdown(self, path: str | Path) -> None:
        summary = self.summary()
        lines = [
            "# Backend Residency Profile",
            "",
            "## Summary",
            "",
        ]
        for key in sorted(summary):
            lines.append(f"- `{key}`: {summary[key]}")
        lines.extend(
            [
                "",
                "## Events",
                "",
                "| op | category | backend | shape | dtype | MiB | elapsed ms | allowed | reason |",
                "| --- | --- | --- | --- | --- | ---: | ---: | --- | --- |",
            ]
        )
        for event in self.events:
            mib = "" if event.nbytes is None else f"{event.nbytes / (1024.0 ** 2):.2f}"
            elapsed = "" if event.elapsed_seconds is None else f"{event.elapsed_seconds * 1000.0:.3f}"
            lines.append(
                "| "
                + " | ".join(
                    [
                        event.direction,
                        event.category or "",
                        event.backend,
                        str(event.shape),
                        event.dtype or "",
                        mib,
                        elapsed,
                        "yes" if event.allowed else "no",
                        event.reason,
                    ]
                )
                + " |"
            )
        Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


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


def residency_recording_active() -> bool:
    return _ACTIVE_RECORDER.get() is not None


def record_backend_operation(
    direction: str,
    backend: Any,
    value: Any = None,
    result: Any | None = None,
    *,
    elapsed_seconds: float | None = None,
    category: str | None = None,
    memory_before: dict[str, int | None] | None = None,
    memory_after: dict[str, int | None] | None = None,
) -> None:
    recorder = _ACTIVE_RECORDER.get()
    if recorder is None:
        return
    backend_name = getattr(backend, "name", backend)
    recorder.record(
        direction,
        str(backend_name),
        value,
        result,
        elapsed_seconds=elapsed_seconds,
        category=category,
        memory_before=memory_before,
        memory_after=memory_after,
    )


@contextmanager
def profile_backend_operation(
    direction: str,
    backend: Any,
    value: Any = None,
    *,
    category: str | None = None,
):
    if not residency_recording_active():
        yield None
        return
    scope = _BackendOperationScope(direction, backend, value, category)
    scope.start()
    try:
        yield scope
    finally:
        scope.finish()


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


class _BackendOperationScope:
    def __init__(self, direction: str, backend: Any, value: Any, category: str | None) -> None:
        self.direction = direction
        self.backend = backend
        self.value = value
        self.result = None
        self.category = category
        self._start = 0.0
        self._memory_before: dict[str, int | None] | None = None

    def start(self) -> None:
        self._memory_before = _mlx_memory_snapshot(self.backend)
        self._start = perf_counter()

    def finish(self) -> None:
        elapsed = perf_counter() - self._start
        memory_after = _mlx_memory_snapshot(self.backend)
        record_backend_operation(
            self.direction,
            self.backend,
            self.value,
            self.result,
            elapsed_seconds=elapsed,
            category=self.category,
            memory_before=self._memory_before,
            memory_after=memory_after,
        )


def _category_for(
    direction: str,
    shape: tuple[int, ...] | None,
    nbytes: int | None,
    stack_label: str,
) -> str:
    if direction in {"eval", "synchronize"}:
        return "sync"
    if direction in {"cleanup", "clear_cache"}:
        return "cleanup"
    if "final_encoder_boundary" in stack_label:
        return "final_encoder_boundary"
    if shape in (None, ()):
        return "scalar"
    if nbytes is not None and nbytes <= 64 * 1024:
        return "small_array"
    if direction == "to_numpy":
        return "materialize"
    return "full_frame"


def _mlx_memory_snapshot(backend: Any) -> dict[str, int | None]:
    mx = getattr(backend, "mx", None)
    return {
        "peak_memory_bytes": _mlx_memory_value(mx, "get_peak_memory"),
        "cache_memory_bytes": _mlx_memory_value(mx, "get_cache_memory"),
    }


def _mlx_memory_value(mx: Any, name: str) -> int | None:
    if mx is None:
        return None
    for owner in (mx, getattr(mx, "metal", None)):
        getter = getattr(owner, name, None)
        if callable(getter):
            try:
                return int(getter())
            except (OSError, RuntimeError, TypeError, ValueError):
                return None
    return None


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
        if name in {"residency.py", "contextlib.py"}:
            continue
        if filename.parent.name == "gpu" and name.endswith("_backend.py"):
            continue
        return f"{filename}:{frame.function}:{frame.lineno}"
    return "<unknown>"
