"""Shared numeric helpers."""

from __future__ import annotations

import numpy as np


def smoothstep(edge0: float, edge1: float, value: np.ndarray) -> np.ndarray:
    """Hermite smoothstep interpolation with safe edge0 == edge1 handling."""
    if edge1 <= edge0:
        return np.where(value >= np.float32(edge1), np.float32(1.0), np.float32(0.0))
    t = np.clip((value - np.float32(edge0)) / np.float32(edge1 - edge0), 0.0, 1.0)
    return (t * t * (np.float32(3.0) - np.float32(2.0) * t)).astype(np.float32, copy=False)
