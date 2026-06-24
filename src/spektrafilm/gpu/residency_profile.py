from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass
import inspect
import json
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable

import numpy as np

_ACTIVE: ContextVar["ResidencyProfileRecorder | None"] = ContextVar(
    "spektrafilm_residency_profile_recorder",
    default=None,
)


@dataclass(frozen=True, slots=True)
class ResidencyProfileEvent:
    operation: str
    backend: str
    label: str
    category: str
    shape: tuple[int, ...] | None
    dtype: str | None
    nbytes: int | None
    elapsed_ms: float | None
    stack_label: str
    cache_memory_before_bytes: int | None = None
    cache_memory_after_bytes: int | None = None
    peak_memory_bytes: int | None = None
    allowed: bool = True
    reason: str = "ok"

    def to_json_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["shape"] = list(self.shape) if self.shape is not None else None
        payload["nbytes_mib"] = _mib(self.nbytes)
        payload["cache_memory_before_mib"] = _mib(self.cache_memory_before_bytes)
        payload["cache_memory_after_mib"] = _mib(self.cache_memory_after_bytes)
        payload["peak_memory_mib"] = _mib(self.peak_memory_bytes)
        return payload


class ResidencyProfileRecorder:
    def __init__(self, *, small_array_bytes: int = 64 * 1024) -> None:
        self.small_array_bytes = int(small_array_bytes)
        self.events: list[ResidencyProfileEvent] = []
        self.warnings: list[str] = []

    def record(
        self,
        operation: str,
        backend: str,
        value: Any | None = None,
        result: Any | None = None,
        *,
        label: str | None = None,
        elapsed_seconds: float | None = None,
        cache_memory_before_bytes: int | None = None,
        cache_memory_after_bytes: int | None = None,
        peak_memory_bytes: int | None = None,
    ) -> None:
        shape, dtype, nbytes = _array_info(result if result is not None else value)
        stack_label = _caller_label()
        category = _category(operation, nbytes, label, stack_label, self.small_array_bytes)
        allowed, reason = _classify(operation, category, label)
        self.events.append(
            ResidencyProfileEvent(
                operation=str(operation),
                backend=str(backend),
                label=str(label or f"{operation}:{stack_label}"),
                category=category,
                shape=shape,
                dtype=dtype,
                nbytes=nbytes,
                elapsed_ms=None if elapsed_seconds is None else float(elapsed_seconds) * 1000.0,
                stack_label=stack_label,
                cache_memory_before_bytes=cache_memory_before_bytes,
                cache_memory_after_bytes=cache_memory_after_bytes,
                peak_memory_bytes=peak_memory_bytes,
                allowed=allowed,
                reason=reason,
            )
        )

    def summary(self) -> dict[str, int]:
        counts = Counter(event.operation for event in self.events)
        return {
            "profile_events": len(self.events),
            "backend.asarray": int(counts.get("asarray", 0)),
            "backend.to_numpy": int(counts.get("to_numpy", 0)),
            "backend.eval": int(counts.get("eval", 0)),
            "backend.synchronize": int(counts.get("synchronize", 0)),
            "backend.cleanup": int(counts.get("cleanup", 0)),
            "backend.clear_cache": int(counts.get("clear_cache", 0)),
            "np.ascontiguousarray": int(counts.get("ascontiguousarray", 0)),
            "unallowed": sum(1 for event in self.events if not event.allowed),
        }

    def to_json_dict(self) -> dict[str, Any]:
        peak_values = [event.peak_memory_bytes for event in self.events if event.peak_memory_bytes is not None]
        cache_values = [event.cache_memory_after_bytes for event in self.events if event.cache_memory_after_bytes is not None]
        return {
            "summary": self.summary(),
            "mlx_peak_memory_bytes": max(peak_values) if peak_values else None,
            "mlx_peak_memory_mib": _mib(max(peak_values) if peak_values else None),
            "mlx_cache_memory_last_bytes": cache_values[-1] if cache_values else None,
            "mlx_cache_memory_last_mib": _mib(cache_values[-1] if cache_values else None),
            "warnings": list(self.warnings),
            "events": [event.to_json_dict() for event in self.events],
        }

    def write_json(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_json_dict(), indent=2, sort_keys=True), encoding="utf-8")
        return path

    def write_markdown(self, path: str | Path, *, title: str = "MLX Memory Residency Profile") -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_markdown(title=title), encoding="utf-8")
        return path

    def to_markdown(self, *, title: str = "MLX Memory Residency Profile") -> str:
        data = self.to_json_dict()
        summary = data["summary"]
        lines = [f"# {title}", "", "## Summary", ""]
        for key, value in summary.items():
            lines.append(f"- `{key}`: `{value}`")
        lines.append(f"- `mlx_peak_memory_mib`: `{data.get('mlx_peak_memory_mib')}`")
        lines.append(f"- `mlx_cache_memory_last_mib`: `{data.get('mlx_cache_memory_last_mib')}`")
        if self.warnings:
            lines.extend(["", "## Warnings", ""])
            lines.extend(f"- {warning}" for warning in self.warnings)
        lines.extend(["", "## Events", "", "| Operation | Label | Category | Shape | MiB | Elapsed ms | Allowed | Reason |", "| --- | --- | --- | --- | ---: | ---: | --- | --- |"])
        for event in self.events:
            lines.append(
                f"| {event.operation} | {event.label} | {event.category} | {event.shape} | "
                f"{'' if event.nbytes is None else f'{_mib(event.nbytes):.3f}'} | "
                f"{'' if event.elapsed_ms is None else f'{event.elapsed_ms:.3f}'} | "
                f"{event.allowed} | {event.reason} |"
            )
        lines.append("")
        return "\n".join(lines)


@contextmanager
def record_residency_profile(*, small_array_bytes: int = 64 * 1024):
    recorder = ResidencyProfileRecorder(small_array_bytes=small_array_bytes)
    token = _ACTIVE.set(recorder)
    try:
        yield recorder
    finally:
        _ACTIVE.reset(token)


def active_residency_profile() -> ResidencyProfileRecorder | None:
    return _ACTIVE.get()


class ProfilingBackendProxy:
    """Explicit opt-in backend wrapper for residency profiling.

    Unknown attributes are forwarded to the wrapped backend, so this proxy does
    not change backend semantics. It is intended for benchmarks/tests and should
    not be installed by default runtime paths.
    """

    def __init__(self, backend: Any, *, label_prefix: str = "") -> None:
        self._backend = backend
        self._label_prefix = str(label_prefix).strip(".")
        self.name = getattr(backend, "name", type(backend).__name__)
        self.supports_gpu = bool(getattr(backend, "supports_gpu", False))
        self.fallback_reason = getattr(backend, "fallback_reason", None)
        self.requires_serial_runtime = bool(getattr(backend, "requires_serial_runtime", False))
        self.precision = getattr(backend, "precision", None)
        self.default_dtype = getattr(backend, "default_dtype", None)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._backend, name)

    def asarray(self, value: Any, dtype: Any | None = None, *, label: str | None = None):
        cache_before = self._memory_bytes("get_cache_memory")
        start = perf_counter()
        result = self._backend.asarray(value, dtype=dtype)
        self._record("asarray", value, result, label, perf_counter() - start, cache_before)
        return result

    def to_numpy(self, value: Any, *, label: str | None = None):
        cache_before = self._memory_bytes("get_cache_memory")
        start = perf_counter()
        result = self._backend.to_numpy(value)
        self._record("to_numpy", value, result, label, perf_counter() - start, cache_before)
        return result

    def eval(self, *values: Any, label: str | None = None) -> None:
        cache_before = self._memory_bytes("get_cache_memory")
        start = perf_counter()
        self._backend.eval(*values)
        self._record("eval", values[0] if values else None, None, label, perf_counter() - start, cache_before)

    def synchronize(self, *, label: str | None = None) -> None:
        cache_before = self._memory_bytes("get_cache_memory")
        start = perf_counter()
        self._backend.synchronize()
        self._record("synchronize", None, None, label, perf_counter() - start, cache_before)

    def clear_cache(self, *, label: str | None = None) -> None:
        cache_before = self._memory_bytes("get_cache_memory")
        start = perf_counter()
        clear = getattr(self._backend, "clear_cache", None)
        if callable(clear):
            clear()
        else:
            mx = getattr(self._backend, "mx", None)
            clear = getattr(mx, "clear_cache", None) or getattr(getattr(mx, "metal", None), "clear_cache", None)
            if callable(clear):
                clear()
        self._record("clear_cache", None, None, label, perf_counter() - start, cache_before)

    def cleanup(self, *, label: str | None = None) -> None:
        cache_before = self._memory_bytes("get_cache_memory")
        start = perf_counter()
        self._backend.cleanup()
        self._record("cleanup", None, None, label, perf_counter() - start, cache_before)

    def _record(self, operation: str, value: Any, result: Any, label: str | None, elapsed: float, cache_before: int | None) -> None:
        recorder = _ACTIVE.get()
        if recorder is None:
            return
        recorder.record(
            operation,
            self.name,
            value,
            result,
            label=self._label(operation, label),
            elapsed_seconds=elapsed,
            cache_memory_before_bytes=cache_before,
            cache_memory_after_bytes=self._memory_bytes("get_cache_memory"),
            peak_memory_bytes=self._memory_bytes("get_peak_memory"),
        )

    def _label(self, operation: str, label: str | None) -> str:
        base = str(label or operation)
        return f"{self._label_prefix}.{base}" if self._label_prefix else base

    def _memory_bytes(self, getter_name: str) -> int | None:
        mx = getattr(self._backend, "mx", None)
        for owner in (mx, getattr(mx, "metal", None)):
            getter = getattr(owner, getter_name, None)
            if callable(getter):
                try:
                    return int(getter())
                except (OSError, RuntimeError, TypeError, ValueError):
                    return None
        return None


def attach_residency_profiler(pipeline: Any, *, label_prefix: str = "pipeline") -> ProfilingBackendProxy | None:
    backend = getattr(pipeline, "_backend", None)
    if backend is None or isinstance(backend, ProfilingBackendProxy):
        return backend
    proxy = ProfilingBackendProxy(backend, label_prefix=label_prefix)
    pipeline._backend = proxy
    pipeline._array_backend = proxy
    for attr in ("_filming_stage", "_printing_stage", "_scanning_stage", "_lut_service", "_color_reference_service"):
        obj = getattr(pipeline, attr, None)
        if obj is not None and hasattr(obj, "_backend"):
            obj._backend = proxy
    return proxy


def record_external_materialization(operation: str, backend: str, value: Any, result: Any | None = None, *, label: str) -> None:
    recorder = _ACTIVE.get()
    if recorder is not None:
        recorder.record(operation, backend, value, result, label=label)


def scan_direct_numpy_materialization(paths: Iterable[str | Path], *, allowed_path_fragments: Iterable[str] = ()) -> list[dict[str, Any]]:
    needles = ("np.asarray(", "numpy.asarray(", "np.ascontiguousarray(", "numpy.ascontiguousarray(")
    allowed = tuple(str(fragment) for fragment in allowed_path_fragments)
    hits: list[dict[str, Any]] = []
    for root in paths:
        root_path = Path(root)
        candidates = [root_path] if root_path.is_file() else root_path.rglob("*.py")
        for path in candidates:
            path_text = str(path)
            if any(fragment in path_text for fragment in allowed):
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            for lineno, line in enumerate(lines, start=1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if any(needle in line for needle in needles):
                    hits.append({"path": path_text, "line": lineno, "text": stripped})
    return hits


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
        if "64" in text:
            return 8
        if "32" in text:
            return 4
        if "16" in text:
            return 2
        if "8" in text or "bool" in text:
            return 1
    return None


def _caller_label() -> str:
    for frame in inspect.stack(context=0)[2:]:
        filename = Path(frame.filename)
        if filename.name == "residency_profile.py":
            continue
        return f"{filename}:{frame.function}:{frame.lineno}"
    return "<unknown>"


def _category(operation: str, nbytes: int | None, label: str | None, stack_label: str, small_array_bytes: int) -> str:
    text = f"{label or ''} {stack_label}".lower()
    if "final_encoder_boundary" in text:
        return "final_encoder_boundary"
    if operation in {"eval", "synchronize", "cleanup", "clear_cache"}:
        return "sync_or_cache"
    if nbytes is None:
        return "unknown"
    if nbytes <= small_array_bytes:
        return "scalar_or_small"
    if nbytes >= 4 * 1024 * 1024:
        return "full_frame_materialize"
    return "intermediate_materialize"


def _classify(operation: str, category: str, label: str | None) -> tuple[bool, str]:
    if operation in {"asarray", "eval", "synchronize", "cleanup", "clear_cache"}:
        return True, "backend_boundary"
    if category in {"scalar_or_small", "final_encoder_boundary"}:
        return True, category
    if label and any(fragment in label for fragment in ("auto_exposure_preview", "route_master", "sidecar", "gpu_validate")):
        return True, "allowed_labeled_materialization"
    return operation != "to_numpy", "unallowed_full_frame_to_numpy" if operation == "to_numpy" else "ok"


def _mib(value: int | None) -> float | None:
    return None if value is None else float(value) / (1024.0 * 1024.0)
