from __future__ import annotations

from typing import Any

import numpy as np

from spektrafilm.gpu.backend import BackendUnavailableError


class MlxBackend:
    name = "mlx"
    supports_gpu = True
    fallback_reason = None
    requires_serial_runtime = True

    def __init__(self, *, precision: str = "float32"):
        try:
            import mlx.core as mx
        except ModuleNotFoundError as exc:
            raise BackendUnavailableError(
                "compute_backend='mlx' requires the optional dependency: "
                "install spektrafilm[gpu-apple]."
            ) from exc

        metal = getattr(mx, "metal", None)
        is_available = getattr(metal, "is_available", None)
        if is_available is None or not bool(is_available()):
            raise BackendUnavailableError(
                "compute_backend='mlx' requires Apple Metal support through MLX."
            )

        if precision not in {"float32", "float16"}:
            raise ValueError("gpu_precision must be 'float32' or 'float16'")

        self.mx = mx
        self.precision = precision
        self.default_dtype = mx.float32 if precision == "float32" else mx.float16
        self._probe_device()

    def _probe_device(self) -> None:
        try:
            probe = self.mx.array([0.0], dtype=self.default_dtype)
            self.mx.eval(probe)
        except (RuntimeError, OSError, ValueError) as exc:
            raise BackendUnavailableError(
                "compute_backend='mlx' requires a usable Apple Metal device."
            ) from exc

    @staticmethod
    def _is_mlx_array(value: Any) -> bool:
        return type(value).__module__.startswith("mlx.")

    def asarray(self, value: Any, dtype: Any | None = None):
        if self._is_mlx_array(value):
            if dtype is None or value.dtype == dtype:
                return value
            return value.astype(dtype)
        return self.mx.array(value, dtype=dtype or self.default_dtype)

    def to_numpy(self, value: Any) -> np.ndarray:
        if not self._is_mlx_array(value):
            return np.asarray(value)
        self.eval(value)
        return np.asarray(value)

    def eval(self, *values: Any) -> None:
        mlx_values = [value for value in values if self._is_mlx_array(value)]
        if mlx_values:
            self.mx.eval(*mlx_values)

    def synchronize(self) -> None:
        self.mx.synchronize()

    def cleanup(self) -> None:
        self.synchronize()
        clear_cache = getattr(self.mx, "clear_cache", None)
        if not callable(clear_cache):
            metal = getattr(self.mx, "metal", None)
            clear_cache = getattr(metal, "clear_cache", None)
        if callable(clear_cache):
            clear_cache()

    def exp(self, x: Any):
        return self.mx.exp(x)

    def log10(self, x: Any):
        return self.mx.log10(x)

    def maximum(self, x: Any, y: Any):
        return self.mx.maximum(x, y)

    def max(self, x: Any) -> float:
        value = self.mx.max(x)
        self.eval(value)
        return float(np.asarray(value))

    def clip(self, x: Any, lo: float, hi: float):
        return self.mx.clip(x, lo, hi)

    def matmul(self, a: Any, b: Any):
        return self.mx.matmul(a, b)

    def einsum(self, pattern: str, *values: Any):
        return self.mx.einsum(pattern, *values)

    def power(self, base: float, x: Any):
        # MLX: base**x = exp(x * ln(base))
        import math
        return self.mx.exp(x * math.log(base))

    def pow(self, x: Any, exponent: float):
        power = getattr(self.mx, "power", None)
        if power is not None:
            return power(x, exponent)
        return x ** exponent

    def fmax(self, x: Any, y: float):
        return self.mx.maximum(x, y)

    def nan_to_num(self, x: Any, nan: float = 0.0):
        return self.mx.where(self.mx.isnan(x), nan, x)

    def where(self, condition: Any, x: Any, y: Any):
        return self.mx.where(condition, x, y)

    def abs(self, x: Any):
        return self.mx.abs(x)
