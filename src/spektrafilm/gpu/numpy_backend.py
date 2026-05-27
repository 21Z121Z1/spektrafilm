from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from opt_einsum import contract


@dataclass(slots=True)
class NumpyBackend:
    fallback_reason: str | None = None

    name: str = "cpu"
    supports_gpu: bool = False
    requires_serial_runtime: bool = False

    def asarray(self, value: Any, dtype: Any | None = None) -> np.ndarray:
        return np.asarray(value, dtype=dtype)

    def to_numpy(self, value: Any) -> np.ndarray:
        return np.asarray(value)

    def eval(self, *values: Any) -> None:
        return None

    def synchronize(self) -> None:
        return None

    def cleanup(self) -> None:
        return None

    def exp(self, x: Any) -> np.ndarray:
        return np.exp(x)

    def log10(self, x: Any) -> np.ndarray:
        return np.log10(x)

    def maximum(self, x: Any, y: Any) -> np.ndarray:
        return np.maximum(x, y)

    def max(self, x: Any) -> float:
        return float(np.max(x))

    def clip(self, x: Any, lo: float, hi: float) -> np.ndarray:
        return np.clip(x, lo, hi)

    def matmul(self, a: Any, b: Any) -> np.ndarray:
        return np.matmul(a, b)

    def einsum(self, pattern: str, *values: Any) -> np.ndarray:
        return contract(pattern, *values)

    def power(self, base: float, x: Any) -> np.ndarray:
        return np.power(base, x)

    def pow(self, x: Any, exponent: float) -> np.ndarray:
        return np.power(x, exponent)

    def fmax(self, x: Any, y: float) -> np.ndarray:
        return np.fmax(x, y)

    def nan_to_num(self, x: Any, nan: float = 0.0) -> np.ndarray:
        return np.nan_to_num(x, nan=nan)

    def where(self, condition: Any, x: Any, y: Any) -> np.ndarray:
        return np.where(condition, x, y)

    def abs(self, x: Any) -> np.ndarray:
        return np.abs(x)
