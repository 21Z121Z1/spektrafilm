from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class ArrayBackend(Protocol):
    name: str
    supports_gpu: bool
    fallback_reason: str | None

    def asarray(self, value: Any, dtype: Any | None = None) -> Any: ...
    def to_numpy(self, value: Any) -> Any: ...
    def eval(self, *values: Any) -> None: ...
    def synchronize(self) -> None: ...

    def exp(self, x: Any) -> Any: ...
    def log10(self, x: Any) -> Any: ...
    def maximum(self, x: Any, y: Any) -> Any: ...
    def clip(self, x: Any, lo: float, hi: float) -> Any: ...
    def matmul(self, a: Any, b: Any) -> Any: ...
    def einsum(self, pattern: str, *values: Any) -> Any: ...
    def power(self, base: float, x: Any) -> Any: ...
    def fmax(self, x: Any, y: float) -> Any: ...
    def nan_to_num(self, x: Any, nan: float = 0.0) -> Any: ...


class BackendUnavailableError(RuntimeError):
    """Raised when a requested compute backend cannot be initialized."""


@dataclass(slots=True)
class BackendInfo:
    requested: str
    selected: str
    supports_gpu: bool
    fallback_reason: str | None = None


def _normalize_backend_name(name: str | None) -> str:
    normalized = "auto" if name is None else str(name).strip().lower()
    if normalized not in {"auto", "cpu", "mlx"}:
        raise ValueError("compute_backend must be one of: 'auto', 'cpu', 'mlx'")
    return normalized


def select_backend(name: str | None = "auto", *, precision: str = "float32") -> ArrayBackend:
    """Select an array backend for runtime computation.

    ``auto`` prefers MLX when it is importable and Metal is available, otherwise
    it returns the NumPy backend with a fallback reason. ``mlx`` is strict and
    raises when MLX cannot be used.
    """
    requested = _normalize_backend_name(name)
    if requested == "cpu":
        from spektrafilm.gpu.numpy_backend import NumpyBackend

        return NumpyBackend()

    try:
        from spektrafilm.gpu.mlx_backend import MlxBackend

        return MlxBackend(precision=precision)
    except BackendUnavailableError:
        if requested == "mlx":
            raise
        from spektrafilm.gpu.numpy_backend import NumpyBackend

        return NumpyBackend(fallback_reason="MLX/Metal backend is unavailable")


def backend_summary(backend: ArrayBackend, *, runtime_gpu_enabled: bool = False) -> str:
    if backend.supports_gpu and not runtime_gpu_enabled:
        return f"cpu runtime path; {backend.name} validated for optional GPU kernels"
    summary = backend.name
    if backend.fallback_reason:
        summary = f"{summary} fallback: {backend.fallback_reason}"
    return summary
