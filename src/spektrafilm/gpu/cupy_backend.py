from __future__ import annotations

from typing import Any

import numpy as np

from spektrafilm.gpu.backend import BackendUnavailableError


class CupyBackend:
    name = "cupy"
    supports_gpu = True
    fallback_reason = None
    requires_serial_runtime = False

    def __init__(self, *, precision: str = "float32"):
        try:
            import cupy as cp
        except ImportError as exc:
            raise BackendUnavailableError(
                "compute_backend='cupy' requires CuPy. Install a CUDA/ROCm "
                "CuPy package matching your driver stack."
            ) from exc

        if precision not in {"float32", "float16"}:
            raise ValueError("gpu_precision must be 'float32' or 'float16'")

        try:
            device_count = int(cp.cuda.runtime.getDeviceCount())
        except Exception as exc:
            raise BackendUnavailableError(
                "compute_backend='cupy' could not query a CUDA/ROCm device."
            ) from exc
        if device_count <= 0:
            raise BackendUnavailableError(
                "compute_backend='cupy' requires at least one visible CUDA/ROCm device."
            )

        self.cp = cp
        self.precision = precision
        self.default_dtype = cp.float32 if precision == "float32" else cp.float16

    def _is_cupy_array(self, value: Any) -> bool:
        return isinstance(value, self.cp.ndarray)

    def asarray(self, value: Any, dtype: Any | None = None):
        if self._is_cupy_array(value):
            if dtype is None or value.dtype == dtype:
                return value
            return value.astype(dtype)
        return self.cp.asarray(value, dtype=dtype or self.default_dtype)

    def to_numpy(self, value: Any) -> np.ndarray:
        if self._is_cupy_array(value):
            self.synchronize()
            return self.cp.asnumpy(value)
        return np.asarray(value)

    def eval(self, *values: Any) -> None:
        if any(self._is_cupy_array(value) for value in values):
            self.synchronize()

    def synchronize(self) -> None:
        self.cp.cuda.get_current_stream().synchronize()

    def exp(self, x: Any):
        return self.cp.exp(x)

    def log10(self, x: Any):
        return self.cp.log10(x)

    def maximum(self, x: Any, y: Any):
        return self.cp.maximum(x, y)

    def max(self, x: Any) -> float:
        value = self.cp.max(x)
        self.synchronize()
        return float(self.cp.asnumpy(value))

    def clip(self, x: Any, lo: float, hi: float):
        return self.cp.clip(x, lo, hi)

    def matmul(self, a: Any, b: Any):
        return self.cp.matmul(a, b)

    def einsum(self, pattern: str, *values: Any):
        return self.cp.einsum(pattern, *values)

    def power(self, base: float, x: Any):
        return self.cp.power(base, x)

    def pow(self, x: Any, exponent: float):
        return self.cp.power(x, exponent)

    def fmax(self, x: Any, y: float):
        return self.cp.fmax(x, y)

    def nan_to_num(self, x: Any, nan: float = 0.0):
        return self.cp.nan_to_num(x, nan=nan)

    def where(self, condition: Any, x: Any, y: Any):
        return self.cp.where(condition, x, y)

    def abs(self, x: Any):
        return self.cp.abs(x)
