from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class ArrayBackend(Protocol):
    name: str
    supports_gpu: bool
    fallback_reason: str | None
    requires_serial_runtime: bool

    def asarray(self, value: Any, dtype: Any | None = None) -> Any: ...
    def to_numpy(self, value: Any) -> Any: ...
    def eval(self, *values: Any) -> None: ...
    def synchronize(self) -> None: ...

    def exp(self, x: Any) -> Any: ...
    def log10(self, x: Any) -> Any: ...
    def maximum(self, x: Any, y: Any) -> Any: ...
    def max(self, x: Any) -> float: ...
    def clip(self, x: Any, lo: float, hi: float) -> Any: ...
    def matmul(self, a: Any, b: Any) -> Any: ...
    def einsum(self, pattern: str, *values: Any) -> Any: ...
    def power(self, base: float, x: Any) -> Any: ...
    def pow(self, x: Any, exponent: float) -> Any: ...
    def fmax(self, x: Any, y: float) -> Any: ...
    def nan_to_num(self, x: Any, nan: float = 0.0) -> Any: ...
    def where(self, condition: Any, x: Any, y: Any) -> Any: ...
    def abs(self, x: Any) -> Any: ...


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
    if normalized not in {"auto", "cpu", "mlx", "cupy", "cuda"}:
        raise ValueError("compute_backend must be one of: 'auto', 'cpu', 'mlx', 'cupy', 'cuda'")
    return normalized


def _select_mlx_backend(*, precision: str) -> ArrayBackend:
    from spektrafilm.gpu.mlx_backend import MlxBackend

    return MlxBackend(precision=precision)


def _select_cupy_backend(*, precision: str) -> ArrayBackend:
    from spektrafilm.gpu.cupy_backend import CupyBackend

    return CupyBackend(precision=precision)


def select_backend(name: str | None = "auto", *, precision: str = "float32") -> ArrayBackend:
    """Select an array backend for runtime computation.

    ``auto`` prefers MLX when it is importable and Metal is available, then
    CuPy when a CUDA/ROCm device is visible, otherwise it returns the NumPy
    backend with a fallback reason. Explicit GPU backend names are strict and
    raise when the requested backend cannot be used.
    """
    requested = _normalize_backend_name(name)
    if requested == "cpu":
        from spektrafilm.gpu.numpy_backend import NumpyBackend

        return NumpyBackend()

    if requested in {"cupy", "cuda"}:
        return _select_cupy_backend(precision=precision)

    mlx_error: BackendUnavailableError | None = None
    try:
        return _select_mlx_backend(precision=precision)
    except BackendUnavailableError as exc:
        if requested == "mlx":
            raise
        mlx_error = exc

    try:
        return _select_cupy_backend(precision=precision)
    except BackendUnavailableError as cupy_exc:
        from spektrafilm.gpu.numpy_backend import NumpyBackend

        return NumpyBackend(
            fallback_reason=(
                "GPU backends are unavailable "
                f"(MLX/Metal: {mlx_error}; CuPy/CUDA/ROCm: {cupy_exc})"
            )
        )


def backend_summary(backend: ArrayBackend, *, runtime_gpu_enabled: bool = False) -> str:
    if backend.supports_gpu and not runtime_gpu_enabled:
        return f"cpu runtime path; {backend.name} validated for optional GPU kernels"
    summary = backend.name
    if backend.fallback_reason:
        summary = f"{summary} fallback: {backend.fallback_reason}"
    return summary
