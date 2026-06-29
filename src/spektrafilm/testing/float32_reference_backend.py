"""Test-only float32 same-order reference backend.

This module deliberately lives outside ``spektrafilm.gpu.backend`` selection.
It is an instrumentation aid for precision-staircase tests, not a production
runtime backend.  The goal is to model the operation order and float32 round
points used by the MLX fast paths closely enough to separate inherent float32
error from backend-specific error.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np


_F32_EPS_LOG = np.float32(1e-10)
_F32_DENSITY_FLOOR = np.float32(-35.0)
_F32_ZERO = np.float32(0.0)
_F32_ONE = np.float32(1.0)


def _as_f32(value: Any) -> np.ndarray:
    return np.asarray(value, dtype=np.float32)


def _round_f32(value: Any) -> np.ndarray:
    return np.asarray(value, dtype=np.float32)


def _scalar_f32(value: Any) -> np.float32:
    return np.float32(value)


def _float_result(value: Any) -> Any:
    arr = np.asarray(value)
    if arr.dtype.kind in {"f", "c"}:
        return arr.astype(np.float32, copy=False)
    return arr


def _is_float_dtype(dtype: Any | None) -> bool:
    if dtype is None:
        return True
    try:
        return np.dtype(dtype).kind in {"f", "c"}
    except TypeError:
        return True


@dataclass(slots=True)
class Float32ReferenceBackend:
    """NumPy-backed, test-only backend with explicit float32 round points."""

    fallback_reason: str | None = None
    fallback_einsum_patterns: list[str] = field(default_factory=list)

    name: str = "numpy_same_order_f32"
    supports_gpu: bool = False
    requires_serial_runtime: bool = False
    precision: str = "float32"
    default_dtype: Any = np.float32

    def asarray(self, value: Any, dtype: Any | None = None) -> np.ndarray:
        if dtype is None:
            arr = np.asarray(value)
            if arr.dtype.kind in {"b", "i", "u"}:
                return arr
            return np.asarray(value, dtype=np.float32)
        return np.asarray(value, dtype=np.float32 if _is_float_dtype(dtype) else dtype)

    def to_numpy(self, value: Any) -> np.ndarray:
        return np.asarray(value)

    def eval(self, *values: Any) -> None:
        return None

    def synchronize(self) -> None:
        return None

    def cleanup(self) -> None:
        return None

    def zeros(self, shape: tuple[int, ...], dtype: Any | None = None) -> np.ndarray:
        return np.zeros(shape, dtype=np.float32 if _is_float_dtype(dtype) else dtype)

    def exp(self, x: Any) -> np.ndarray:
        return _round_f32(np.exp(_as_f32(x)))

    def log10(self, x: Any) -> np.ndarray:
        return _round_f32(np.log10(_as_f32(x)))

    def log2(self, x: Any) -> np.ndarray:
        return _round_f32(np.log2(_as_f32(x)))

    def maximum(self, x: Any, y: Any) -> np.ndarray:
        return _round_f32(np.maximum(_as_f32(x), _as_f32(y)))

    def max_array(self, x: Any) -> np.ndarray:
        return np.asarray(np.max(_as_f32(x)), dtype=np.float32)

    def max(self, x: Any) -> float:
        return float(np.max(_as_f32(x)))

    def clip(self, x: Any, lo: float, hi: float) -> np.ndarray:
        return _round_f32(np.clip(_as_f32(x), _scalar_f32(lo), _scalar_f32(hi)))

    def matmul(self, a: Any, b: Any) -> np.ndarray:
        lhs = _as_f32(a)
        rhs = _as_f32(b)
        if lhs.ndim < 1 or rhs.ndim != 2 or lhs.shape[-1] != rhs.shape[0]:
            return _round_f32(np.matmul(lhs, rhs))

        flat = lhs.reshape((-1, lhs.shape[-1]))
        out = np.zeros((flat.shape[0], rhs.shape[1]), dtype=np.float32)
        for n in range(rhs.shape[1]):
            acc = np.zeros((flat.shape[0],), dtype=np.float32)
            for k in range(rhs.shape[0]):
                term = _round_f32(flat[:, k] * rhs[k, n])
                acc = _round_f32(acc + term)
            out[:, n] = acc
        return out.reshape(lhs.shape[:-1] + (rhs.shape[1],))

    def einsum(self, pattern: str, *values: Any) -> np.ndarray:
        normalized = pattern.replace(" ", "")
        if normalized == "ijk,lk->ijl" and len(values) == 2:
            return _einsum_ijk_lk_to_ijl(values[0], values[1])
        if normalized == "ijk,kl->ijl" and len(values) == 2:
            return _einsum_ijk_kl_to_ijl(values[0], values[1])
        if normalized == "ijk,k->ij" and len(values) == 2:
            return _einsum_ijk_k_to_ij(values[0], values[1])

        self.fallback_einsum_patterns.append(normalized)
        return _round_f32(np.einsum(pattern, *[_as_f32(value) for value in values]))

    def power(self, base: float, x: Any) -> np.ndarray:
        # Mirrors MlxBackend.power(): exp(x * ln(base)), with float32 round
        # points around the multiply and final exponential.
        exponent = _round_f32(_as_f32(x) * _scalar_f32(math.log(float(base))))
        return _round_f32(np.exp(exponent))

    def pow(self, x: Any, exponent: float) -> np.ndarray:
        return _round_f32(np.power(_as_f32(x), _scalar_f32(exponent)))

    def fmax(self, x: Any, y: float) -> np.ndarray:
        return _round_f32(np.fmax(_as_f32(x), _scalar_f32(y)))

    def nan_to_num(self, x: Any, nan: float = 0.0) -> np.ndarray:
        return _round_f32(np.nan_to_num(_as_f32(x), nan=_scalar_f32(nan)))

    def where(self, condition: Any, x: Any, y: Any) -> np.ndarray:
        return _float_result(np.where(condition, _as_f32(x), _as_f32(y)))

    def abs(self, x: Any) -> np.ndarray:
        return _round_f32(np.abs(_as_f32(x)))


def _einsum_ijk_lk_to_ijl(a: Any, b: Any) -> np.ndarray:
    lhs = _as_f32(a)
    rhs = _as_f32(b)
    if lhs.ndim != 3 or rhs.ndim != 2 or lhs.shape[2] != rhs.shape[1]:
        return _round_f32(np.einsum("ijk,lk->ijl", lhs, rhs))

    out = np.zeros((lhs.shape[0], lhs.shape[1], rhs.shape[0]), dtype=np.float32)
    for l in range(rhs.shape[0]):
        acc = np.zeros(lhs.shape[:2], dtype=np.float32)
        for k in range(lhs.shape[2]):
            acc = _round_f32(acc + _round_f32(lhs[..., k] * rhs[l, k]))
        out[..., l] = acc
    return out


def _einsum_ijk_kl_to_ijl(a: Any, b: Any) -> np.ndarray:
    lhs = _as_f32(a)
    rhs = _as_f32(b)
    if lhs.ndim != 3 or rhs.ndim != 2 or lhs.shape[2] != rhs.shape[0]:
        return _round_f32(np.einsum("ijk,kl->ijl", lhs, rhs))

    out = np.zeros((lhs.shape[0], lhs.shape[1], rhs.shape[1]), dtype=np.float32)
    for l in range(rhs.shape[1]):
        acc = np.zeros(lhs.shape[:2], dtype=np.float32)
        for k in range(lhs.shape[2]):
            acc = _round_f32(acc + _round_f32(lhs[..., k] * rhs[k, l]))
        out[..., l] = acc
    return out


def _einsum_ijk_k_to_ij(a: Any, b: Any) -> np.ndarray:
    lhs = _as_f32(a)
    rhs = _as_f32(b)
    if lhs.ndim != 3 or rhs.ndim != 1 or lhs.shape[2] != rhs.shape[0]:
        return _round_f32(np.einsum("ijk,k->ij", lhs, rhs))

    acc = np.zeros(lhs.shape[:2], dtype=np.float32)
    for k in range(lhs.shape[2]):
        acc = _round_f32(acc + _round_f32(lhs[..., k] * rhs[k]))
    return acc


def cmy_to_log_raw_same_order(
    density_cmy: Any,
    channel_density: Any,
    base_density: Any,
    print_illuminant: Any,
    sensitivity: Any,
    exposure_factor: Any,
    preflash: Any,
    *,
    tile_rows: int | None = None,
) -> np.ndarray:
    """Approximate the MLX pixel-thread fused ``cmy_to_log_raw`` order."""

    density = _as_f32(density_cmy)
    if density.ndim != 3 or density.shape[-1] != 3:
        raise ValueError("density_cmy must have shape (H, W, 3)")

    rows = int(density.shape[0])
    if tile_rows is None or tile_rows <= 0 or tile_rows >= rows:
        return _cmy_to_log_raw_same_order_tile(
            density,
            channel_density,
            base_density,
            print_illuminant,
            sensitivity,
            exposure_factor,
            preflash,
        )

    out = np.empty_like(density, dtype=np.float32)
    for y0 in range(0, rows, int(tile_rows)):
        y1 = min(rows, y0 + int(tile_rows))
        out[y0:y1] = _cmy_to_log_raw_same_order_tile(
            density[y0:y1],
            channel_density,
            base_density,
            print_illuminant,
            sensitivity,
            exposure_factor,
            preflash,
        )
    return out


def _cmy_to_log_raw_same_order_tile(
    density_cmy: np.ndarray,
    channel_density: Any,
    base_density: Any,
    print_illuminant: Any,
    sensitivity: Any,
    exposure_factor: Any,
    preflash: Any,
) -> np.ndarray:
    density = _as_f32(density_cmy)
    channel = _as_f32(channel_density)
    base = np.zeros((channel.shape[0],), dtype=np.float32) if base_density is None else _as_f32(base_density)
    illuminant = _as_f32(print_illuminant)
    sens = _as_f32(sensitivity)
    exposure = _as_f32(exposure_factor).reshape(-1)
    pre = _as_f32(preflash).reshape(-1)
    if channel.ndim != 2 or channel.shape[1] != 3:
        raise ValueError("channel_density must have shape (K, 3)")
    if sens.shape != (channel.shape[0], 3):
        raise ValueError("sensitivity must have shape (K, 3)")

    c0 = density[..., 0]
    c1 = density[..., 1]
    c2 = density[..., 2]
    raw0 = np.zeros(density.shape[:2], dtype=np.float32)
    raw1 = np.zeros(density.shape[:2], dtype=np.float32)
    raw2 = np.zeros(density.shape[:2], dtype=np.float32)

    with np.errstate(invalid="ignore", over="ignore"):
        for k in range(channel.shape[0]):
            d = _round_f32(c0 * channel[k, 0])
            d = _round_f32(d + _round_f32(c1 * channel[k, 1]))
            d = _round_f32(d + _round_f32(c2 * channel[k, 2]))
            d = _round_f32(d + base[k])
            valid = d == d
            d = np.where(d < _F32_DENSITY_FLOOR, _F32_DENSITY_FLOOR, d).astype(np.float32, copy=False)
            light = _round_f32(np.power(np.float32(10.0), _round_f32(-d)))
            light = _round_f32(light * illuminant[k])
            raw0 = np.where(valid, _round_f32(raw0 + _round_f32(light * sens[k, 0])), raw0).astype(np.float32)
            raw1 = np.where(valid, _round_f32(raw1 + _round_f32(light * sens[k, 1])), raw1).astype(np.float32)
            raw2 = np.where(valid, _round_f32(raw2 + _round_f32(light * sens[k, 2])), raw2).astype(np.float32)

    raw = np.stack((raw0, raw1, raw2), axis=-1).astype(np.float32, copy=False)
    raw = _round_f32(raw * exposure[0] + pre.reshape((1, 1, 3)))
    raw = np.where(raw == raw, raw, _F32_ZERO).astype(np.float32, copy=False)
    raw = np.where(raw < _F32_ZERO, _F32_ZERO, raw).astype(np.float32, copy=False)
    return _round_f32(np.log10(_round_f32(raw + _F32_EPS_LOG)))


def cmy_to_log_xyz_same_order(
    density_cmy: Any,
    channel_density: Any,
    base_density: Any,
    scan_illuminant: Any,
    cmfs: Any,
    normalization: float,
    *,
    tile_rows: int | None = None,
) -> np.ndarray:
    """Approximate the MLX/Metal fused ``cmy_to_log_xyz`` order."""

    density = _as_f32(density_cmy)
    if density.ndim != 3 or density.shape[-1] != 3:
        raise ValueError("density_cmy must have shape (H, W, 3)")

    rows = int(density.shape[0])
    if tile_rows is None or tile_rows <= 0 or tile_rows >= rows:
        return _cmy_to_log_xyz_same_order_tile(
            density,
            channel_density,
            base_density,
            scan_illuminant,
            cmfs,
            normalization,
        )

    out = np.empty_like(density, dtype=np.float32)
    for y0 in range(0, rows, int(tile_rows)):
        y1 = min(rows, y0 + int(tile_rows))
        out[y0:y1] = _cmy_to_log_xyz_same_order_tile(
            density[y0:y1],
            channel_density,
            base_density,
            scan_illuminant,
            cmfs,
            normalization,
        )
    return out


def _cmy_to_log_xyz_same_order_tile(
    density_cmy: np.ndarray,
    channel_density: Any,
    base_density: Any,
    scan_illuminant: Any,
    cmfs: Any,
    normalization: float,
) -> np.ndarray:
    density = _as_f32(density_cmy)
    channel = _as_f32(channel_density)
    base = np.zeros((channel.shape[0],), dtype=np.float32) if base_density is None else _as_f32(base_density)
    illuminant = _as_f32(scan_illuminant)
    cmf = _as_f32(cmfs)
    norm = _scalar_f32(normalization)
    if channel.ndim != 2 or channel.shape[1] != 3:
        raise ValueError("channel_density must have shape (K, 3)")
    if cmf.shape != (channel.shape[0], 3):
        raise ValueError("cmfs must have shape (K, 3)")

    c0 = density[..., 0]
    c1 = density[..., 1]
    c2 = density[..., 2]
    xyz0 = np.zeros(density.shape[:2], dtype=np.float32)
    xyz1 = np.zeros(density.shape[:2], dtype=np.float32)
    xyz2 = np.zeros(density.shape[:2], dtype=np.float32)

    with np.errstate(invalid="ignore", over="ignore"):
        for k in range(channel.shape[0]):
            d = _round_f32(c0 * channel[k, 0])
            d = _round_f32(d + _round_f32(c1 * channel[k, 1]))
            d = _round_f32(d + _round_f32(c2 * channel[k, 2]))
            d = _round_f32(d + base[k])
            valid = d == d
            d = np.where(d < _F32_DENSITY_FLOOR, _F32_DENSITY_FLOOR, d).astype(np.float32, copy=False)
            light = _round_f32(np.power(np.float32(10.0), _round_f32(-d)))
            light = _round_f32(light * illuminant[k])
            xyz0 = np.where(valid, _round_f32(xyz0 + _round_f32(light * cmf[k, 0])), xyz0).astype(np.float32)
            xyz1 = np.where(valid, _round_f32(xyz1 + _round_f32(light * cmf[k, 1])), xyz1).astype(np.float32)
            xyz2 = np.where(valid, _round_f32(xyz2 + _round_f32(light * cmf[k, 2])), xyz2).astype(np.float32)

    xyz = np.stack((xyz0, xyz1, xyz2), axis=-1).astype(np.float32, copy=False)
    xyz = _round_f32(xyz / norm)
    xyz = np.where(xyz < _F32_ZERO, _F32_ZERO, xyz).astype(np.float32, copy=False)
    return _round_f32(np.log10(_round_f32(xyz + _F32_EPS_LOG)))


def apply_lut_trilinear_3d_same_order(lut: Any, image: Any) -> np.ndarray:
    """Float32-order NumPy reference for the MLX fused 3D trilinear LUT."""

    table = _as_f32(lut)
    coords = _as_f32(image)
    if table.ndim != 4 or table.shape[-1] != 3:
        raise ValueError("3D LUT must have shape LxLxLx3")
    if coords.ndim != 3 or coords.shape[-1] != 3:
        raise ValueError("3D LUT coordinates must have shape HxWx3")
    size = int(table.shape[0])
    if size == 0 or table.shape[1] != size or table.shape[2] != size:
        raise ValueError("3D LUT must have equal non-empty dimensions")
    if size == 1:
        return np.broadcast_to(table[0, 0, 0], coords.shape[:-1] + (3,)).astype(np.float32).copy()

    upper = _scalar_f32(size - 1)
    clipped = np.clip(coords, _F32_ZERO, _F32_ONE).astype(np.float32, copy=False)
    coord = _round_f32(clipped * upper)
    idx0 = np.floor(coord).astype(np.int64)
    idx1 = np.minimum(idx0 + 1, size - 1)
    frac = _round_f32(coord - idx0.astype(np.float32))

    r0, g0, b0 = idx0[..., 0], idx0[..., 1], idx0[..., 2]
    r1, g1, b1 = idx1[..., 0], idx1[..., 1], idx1[..., 2]
    fr = frac[..., 0:1]
    fg = frac[..., 1:2]
    fb = frac[..., 2:3]

    c000 = table[r0, g0, b0]
    c100 = table[r1, g0, b0]
    c010 = table[r0, g1, b0]
    c110 = table[r1, g1, b0]
    c001 = table[r0, g0, b1]
    c101 = table[r1, g0, b1]
    c011 = table[r0, g1, b1]
    c111 = table[r1, g1, b1]

    c00 = _round_f32(c000 + _round_f32(fr * _round_f32(c100 - c000)))
    c10 = _round_f32(c010 + _round_f32(fr * _round_f32(c110 - c010)))
    c01 = _round_f32(c001 + _round_f32(fr * _round_f32(c101 - c001)))
    c11 = _round_f32(c011 + _round_f32(fr * _round_f32(c111 - c011)))
    c0 = _round_f32(c00 + _round_f32(fg * _round_f32(c10 - c00)))
    c1 = _round_f32(c01 + _round_f32(fg * _round_f32(c11 - c01)))
    return _round_f32(c0 + _round_f32(fb * _round_f32(c1 - c0)))


def gain_map_ev_same_order(
    sdr_rgb: Any,
    hdr_rgb: Any,
    *,
    sdr_luma_floor: float = 1e-3,
    hdr_luma_floor: float = 1e-6,
) -> np.ndarray:
    """Return raw gain-map EV, ``log2(hdr_luma / max(sdr_luma, floor))``."""

    sdr = _as_f32(sdr_rgb)
    hdr = _as_f32(hdr_rgb)
    sdr_y = _round_f32(
        _round_f32(sdr[..., 0] * np.float32(0.2126))
        + _round_f32(sdr[..., 1] * np.float32(0.7152))
        + _round_f32(sdr[..., 2] * np.float32(0.0722))
    )
    hdr_y = _round_f32(
        _round_f32(hdr[..., 0] * np.float32(0.2126))
        + _round_f32(hdr[..., 1] * np.float32(0.7152))
        + _round_f32(hdr[..., 2] * np.float32(0.0722))
    )
    sdr_y = np.maximum(sdr_y, _scalar_f32(sdr_luma_floor)).astype(np.float32, copy=False)
    hdr_y = np.maximum(hdr_y, _scalar_f32(hdr_luma_floor)).astype(np.float32, copy=False)
    return _round_f32(np.log2(_round_f32(hdr_y / sdr_y)))
