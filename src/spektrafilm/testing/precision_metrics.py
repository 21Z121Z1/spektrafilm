"""Precision metrics for backend staircase reports."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import numpy as np


DEFAULT_RELATIVE_ERROR_BINS: tuple[float, ...] = (
    0.0,
    1e-8,
    1e-7,
    1e-6,
    1e-5,
    1e-4,
    1e-3,
    1e-2,
    math.inf,
)


def finite_counts(value: Any) -> dict[str, int]:
    arr = np.asarray(value)
    return {
        "total": int(arr.size),
        "finite": int(np.isfinite(arr).sum()),
        "nan": int(np.isnan(arr).sum()) if np.issubdtype(arr.dtype, np.floating) else 0,
        "posinf": int(np.isposinf(arr).sum()) if np.issubdtype(arr.dtype, np.floating) else 0,
        "neginf": int(np.isneginf(arr).sum()) if np.issubdtype(arr.dtype, np.floating) else 0,
    }


def difference_metrics(
    reference: Any,
    candidate: Any,
    *,
    data_range: float = 1.0,
    relative_floor: float = 1e-12,
    relative_bins: Sequence[float] = DEFAULT_RELATIVE_ERROR_BINS,
) -> dict[str, Any]:
    ref = np.asarray(reference, dtype=np.float64)
    cand = np.asarray(candidate, dtype=np.float64)
    if ref.shape != cand.shape:
        raise ValueError(f"shape mismatch: reference {ref.shape}, candidate {cand.shape}")

    finite = np.isfinite(ref) & np.isfinite(cand)
    diff = cand - ref
    abs_diff = np.abs(diff)
    finite_abs = abs_diff[finite]
    if finite_abs.size:
        rmse = float(np.sqrt(np.mean(np.square(diff[finite], dtype=np.float64), dtype=np.float64)))
        max_abs = float(np.max(finite_abs))
        mean_abs = float(np.mean(finite_abs, dtype=np.float64))
        p99_abs = float(np.percentile(finite_abs, 99.0))
        p999_abs = float(np.percentile(finite_abs, 99.9))
    else:
        rmse = math.nan
        max_abs = math.nan
        mean_abs = math.nan
        p99_abs = math.nan
        p999_abs = math.nan

    psnr = math.inf if rmse == 0.0 else 20.0 * math.log10(float(data_range) / rmse) if rmse > 0.0 else math.nan
    return {
        "shape": list(ref.shape),
        "finite_pair_count": int(finite.sum()),
        "reference_finite": finite_counts(ref),
        "candidate_finite": finite_counts(cand),
        "max_abs_diff": max_abs,
        "mean_abs_diff": mean_abs,
        "rmse": rmse,
        "psnr": float(psnr),
        "p99_abs_diff": p99_abs,
        "p999_abs_diff": p999_abs,
        "relative_error_histogram": relative_error_histogram(
            ref,
            cand,
            floor=relative_floor,
            bins=relative_bins,
            finite_mask=finite,
        ),
    }


def relative_error_histogram(
    reference: Any,
    candidate: Any,
    *,
    floor: float = 1e-12,
    bins: Sequence[float] = DEFAULT_RELATIVE_ERROR_BINS,
    finite_mask: Any | None = None,
) -> dict[str, Any]:
    ref = np.asarray(reference, dtype=np.float64)
    cand = np.asarray(candidate, dtype=np.float64)
    if ref.shape != cand.shape:
        raise ValueError(f"shape mismatch: reference {ref.shape}, candidate {cand.shape}")
    finite = np.isfinite(ref) & np.isfinite(cand) if finite_mask is None else np.asarray(finite_mask, dtype=bool)
    denom = np.maximum(np.abs(ref), float(floor))
    rel = np.abs(cand - ref) / denom
    values = rel[finite]
    edges = np.asarray(tuple(bins), dtype=np.float64)
    counts, edges = np.histogram(values, bins=edges)
    return {
        "bin_edges": [_json_float(edge) for edge in edges],
        "counts": [int(count) for count in counts],
        "sample_count": int(values.size),
    }


def ulp_distance_float32(reference: Any, candidate: Any) -> np.ndarray:
    """Return ULP distances between finite float32 representations."""

    ref = np.asarray(reference, dtype=np.float32)
    cand = np.asarray(candidate, dtype=np.float32)
    if ref.shape != cand.shape:
        raise ValueError(f"shape mismatch: reference {ref.shape}, candidate {cand.shape}")

    ref_ordered = _float32_ordered_int(ref)
    cand_ordered = _float32_ordered_int(cand)
    dist = np.abs(cand_ordered.astype(np.int64) - ref_ordered.astype(np.int64))
    finite = np.isfinite(ref) & np.isfinite(cand)
    return dist[finite]


def ulp_metrics(reference: Any, candidate: Any) -> dict[str, Any]:
    dist = ulp_distance_float32(reference, candidate)
    if dist.size == 0:
        return {
            "sample_count": 0,
            "max_ulp": None,
            "mean_ulp": None,
            "p99_ulp": None,
            "p999_ulp": None,
            "histogram": _empty_ulp_histogram(),
        }
    return {
        "sample_count": int(dist.size),
        "max_ulp": int(np.max(dist)),
        "mean_ulp": float(np.mean(dist, dtype=np.float64)),
        "p99_ulp": float(np.percentile(dist, 99.0)),
        "p999_ulp": float(np.percentile(dist, 99.9)),
        "histogram": ulp_histogram(dist),
    }


def ulp_histogram(distances: Any) -> dict[str, int]:
    dist = np.asarray(distances, dtype=np.int64)
    return {
        "0": int(np.sum(dist == 0)),
        "1": int(np.sum(dist == 1)),
        "2": int(np.sum(dist == 2)),
        "3_4": int(np.sum((dist >= 3) & (dist <= 4))),
        "5_8": int(np.sum((dist >= 5) & (dist <= 8))),
        "9_16": int(np.sum((dist >= 9) & (dist <= 16))),
        "17_32": int(np.sum((dist >= 17) & (dist <= 32))),
        "33_128": int(np.sum((dist >= 33) & (dist <= 128))),
        "gt_128": int(np.sum(dist > 128)),
    }


def _empty_ulp_histogram() -> dict[str, int]:
    return {key: 0 for key in ("0", "1", "2", "3_4", "5_8", "9_16", "17_32", "33_128", "gt_128")}


def _float32_ordered_int(value: np.ndarray) -> np.ndarray:
    arr = np.asarray(value, dtype=np.float32)
    bits = arr.view(np.uint32)
    ordered = np.where((bits & np.uint32(0x80000000)) != 0, ~bits, bits | np.uint32(0x80000000))
    ordered = ordered.astype(np.uint32, copy=False)
    ordered = np.where(arr == np.float32(0.0), np.uint32(0x80000000), ordered)
    return ordered


def luminance_y(rgb: Any) -> np.ndarray:
    arr = np.asarray(rgb, dtype=np.float64)
    if arr.shape[-1] != 3:
        raise ValueError("rgb input must have last dimension 3")
    return arr[..., 0] * 0.2126 + arr[..., 1] * 0.7152 + arr[..., 2] * 0.0722


def luminance_error_metrics(reference_rgb: Any, candidate_rgb: Any) -> dict[str, Any]:
    return difference_metrics(luminance_y(reference_rgb), luminance_y(candidate_rgb), data_range=1.0)


def gain_map_ev(rgb_sdr: Any, rgb_hdr: Any, *, sdr_luma_floor: float = 1e-3, hdr_luma_floor: float = 1e-6) -> np.ndarray:
    sdr_y = np.maximum(luminance_y(rgb_sdr), float(sdr_luma_floor))
    hdr_y = np.maximum(luminance_y(rgb_hdr), float(hdr_luma_floor))
    return np.log2(hdr_y / sdr_y)


def gain_map_ev_metrics(
    reference_sdr_rgb: Any,
    reference_hdr_rgb: Any,
    candidate_sdr_rgb: Any,
    candidate_hdr_rgb: Any,
    *,
    sdr_luma_floor: float = 1e-3,
    hdr_luma_floor: float = 1e-6,
) -> dict[str, Any]:
    ref_ev = gain_map_ev(reference_sdr_rgb, reference_hdr_rgb, sdr_luma_floor=sdr_luma_floor, hdr_luma_floor=hdr_luma_floor)
    cand_ev = gain_map_ev(candidate_sdr_rgb, candidate_hdr_rgb, sdr_luma_floor=sdr_luma_floor, hdr_luma_floor=hdr_luma_floor)
    metrics = difference_metrics(ref_ev, cand_ev, data_range=1.0)
    metrics["units"] = "EV"
    return metrics


def headroom_metrics(reference_sdr_rgb: Any, reference_hdr_rgb: Any, candidate_sdr_rgb: Any, candidate_hdr_rgb: Any) -> dict[str, Any]:
    ref = _headroom(reference_sdr_rgb, reference_hdr_rgb)
    cand = _headroom(candidate_sdr_rgb, candidate_hdr_rgb)
    return {
        "reference_headroom": ref,
        "candidate_headroom": cand,
        "abs_diff": abs(cand - ref),
        "signed_diff": cand - ref,
    }


def monotonicity_violation_count(values: Any, *, axis: int = -1, atol: float = 0.0) -> int:
    arr = np.asarray(values, dtype=np.float64)
    diffs = np.diff(arr, axis=axis)
    return int(np.sum(diffs < -float(atol)))


def tile_seam_statistics(reference: Any, candidate: Any, *, tile_rows: int) -> dict[str, Any]:
    if tile_rows <= 0:
        raise ValueError("tile_rows must be positive")
    ref = np.asarray(reference, dtype=np.float64)
    cand = np.asarray(candidate, dtype=np.float64)
    if ref.shape != cand.shape:
        raise ValueError(f"shape mismatch: reference {ref.shape}, candidate {cand.shape}")
    if ref.ndim < 2:
        raise ValueError("tile seam statistics require at least two spatial dimensions")

    height = ref.shape[0]
    seam_rows: list[int] = []
    for seam in range(tile_rows, height, tile_rows):
        seam_rows.extend(row for row in (seam - 1, seam) if 0 <= row < height)
    seam_rows = sorted(set(seam_rows))
    diff = cand - ref
    abs_diff = np.abs(diff)
    if not seam_rows:
        return {
            "tile_rows": int(tile_rows),
            "seam_count": 0,
            "seam_rows": [],
            "seam_max_abs_diff": 0.0,
            "seam_mean_abs_diff": 0.0,
            "seam_p99_abs_diff": 0.0,
            "non_seam_mean_abs_diff": float(np.mean(abs_diff, dtype=np.float64)) if abs_diff.size else 0.0,
            "signed_mean_diff": 0.0,
            "positive_fraction": 0.0,
            "per_seam": [],
        }

    seam_abs = abs_diff[seam_rows]
    seam_diff = diff[seam_rows]
    non_mask = np.ones(height, dtype=bool)
    non_mask[seam_rows] = False
    non_seam_abs = abs_diff[non_mask]
    per_seam = []
    for row in seam_rows:
        row_abs = abs_diff[row]
        row_diff = diff[row]
        per_seam.append(
            {
                "row": int(row),
                "max_abs_diff": float(np.max(row_abs)) if row_abs.size else 0.0,
                "mean_abs_diff": float(np.mean(row_abs, dtype=np.float64)) if row_abs.size else 0.0,
                "signed_mean_diff": float(np.mean(row_diff, dtype=np.float64)) if row_diff.size else 0.0,
            }
        )

    return {
        "tile_rows": int(tile_rows),
        "seam_count": int(len(seam_rows) // 2 if len(seam_rows) > 1 else len(seam_rows)),
        "seam_rows": [int(row) for row in seam_rows],
        "seam_max_abs_diff": float(np.max(seam_abs)) if seam_abs.size else 0.0,
        "seam_mean_abs_diff": float(np.mean(seam_abs, dtype=np.float64)) if seam_abs.size else 0.0,
        "seam_p99_abs_diff": float(np.percentile(seam_abs, 99.0)) if seam_abs.size else 0.0,
        "non_seam_mean_abs_diff": float(np.mean(non_seam_abs, dtype=np.float64)) if non_seam_abs.size else 0.0,
        "signed_mean_diff": float(np.mean(seam_diff, dtype=np.float64)) if seam_diff.size else 0.0,
        "positive_fraction": float(np.mean(seam_diff > 0.0)) if seam_diff.size else 0.0,
        "per_seam": per_seam,
    }


def precision_report(reference: Any, candidate: Any, *, data_range: float = 1.0) -> dict[str, Any]:
    report = difference_metrics(reference, candidate, data_range=data_range)
    report["ulp"] = ulp_metrics(reference, candidate)
    if np.asarray(reference).ndim >= 1 and np.asarray(reference).shape[-1] == 3:
        report["luminance_y"] = luminance_error_metrics(reference, candidate)
    return report


def _headroom(sdr_rgb: Any, hdr_rgb: Any, *, floor: float = 1e-3) -> float:
    sdr_y = np.maximum(luminance_y(sdr_rgb), float(floor))
    hdr_y = np.maximum(luminance_y(hdr_rgb), 0.0)
    return float(np.max(hdr_y / sdr_y))


def _json_float(value: float) -> float | str:
    value = float(value)
    if math.isinf(value):
        return "inf" if value > 0 else "-inf"
    if math.isnan(value):
        return "nan"
    return value
