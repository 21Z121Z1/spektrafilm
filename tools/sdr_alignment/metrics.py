from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from skimage.metrics import structural_similarity


@dataclass(frozen=True)
class MetricThresholds:
    max_abs: float
    p99_abs: float
    rmse: float
    mean_abs: float | None = None
    srgb_p99_abs: float | None = None
    oklab_delta_p95: float | None = None
    ssim_min: float | None = None


CPU_STRICT_THRESHOLDS = MetricThresholds(
    max_abs=1e-8,
    p99_abs=1e-9,
    rmse=1e-10,
    mean_abs=1e-10,
    srgb_p99_abs=1e-8,
    oklab_delta_p95=1e-5,
    ssim_min=0.999999,
)
FLOAT32_THRESHOLDS = MetricThresholds(
    max_abs=1e-4,
    p99_abs=1e-5,
    rmse=1e-5,
    mean_abs=1e-5,
    srgb_p99_abs=1e-5,
    oklab_delta_p95=1e-4,
    ssim_min=0.99999,
)
FLOAT32_LUT_THRESHOLDS = MetricThresholds(
    max_abs=5e-4,
    p99_abs=2e-4,
    rmse=2e-4,
    mean_abs=2e-4,
    srgb_p99_abs=2e-4,
    oklab_delta_p95=5e-4,
    ssim_min=0.9999,
)
HALIDE_THRESHOLDS = MetricThresholds(
    max_abs=6e-2,
    p99_abs=6e-2,
    rmse=2e-2,
    mean_abs=2e-2,
    srgb_p99_abs=6e-2,
    oklab_delta_p95=6e-2,
    ssim_min=0.95,
)


def thresholds_for_backend(backend: str, *, mode: str, uses_lut: bool) -> MetricThresholds:
    if backend == "cpu" and mode == "upstream_compat":
        return CPU_STRICT_THRESHOLDS
    if backend == "halide":
        return HALIDE_THRESHOLDS
    if uses_lut:
        return FLOAT32_LUT_THRESHOLDS
    return FLOAT32_THRESHOLDS


def compare_arrays(reference: np.ndarray, candidate: np.ndarray, *, final_sdr: bool) -> dict[str, Any]:
    ref = np.asarray(reference, dtype=np.float64)
    cand = np.asarray(candidate, dtype=np.float64)
    metrics: dict[str, Any] = {
        "shape": list(cand.shape),
        "reference_shape": list(ref.shape),
        "shape_match": cand.shape == ref.shape,
        "finite": bool(np.all(np.isfinite(ref)) and np.all(np.isfinite(cand))),
    }
    if cand.shape != ref.shape:
        metrics.update(
            {
                "max_abs": None,
                "mean_abs": None,
                "rmse": None,
                "p99_abs": None,
            }
        )
        return metrics

    diff = np.abs(cand - ref)
    finite_diff = diff[np.isfinite(diff)]
    if finite_diff.size == 0:
        metrics.update(
            {
                "max_abs": float("inf"),
                "mean_abs": float("inf"),
                "rmse": float("inf"),
                "p99_abs": float("inf"),
            }
        )
    else:
        metrics.update(
            {
                "max_abs": float(np.max(finite_diff)),
                "mean_abs": float(np.mean(finite_diff)),
                "rmse": float(np.sqrt(np.mean(finite_diff * finite_diff))),
                "p99_abs": float(np.percentile(finite_diff, 99.0)),
            }
        )

    if final_sdr:
        metrics.update(compare_final_sdr(reference=ref, candidate=cand))
    return metrics


def compare_final_sdr(*, reference: np.ndarray, candidate: np.ndarray) -> dict[str, float]:
    ref_srgb = _srgb_encode(np.clip(reference, 0.0, 1.0))
    cand_srgb = _srgb_encode(np.clip(candidate, 0.0, 1.0))
    srgb_diff = np.abs(cand_srgb - ref_srgb)

    ref_lab = _oklab(_srgb_decode(np.clip(reference, 0.0, 1.0)))
    cand_lab = _oklab(_srgb_decode(np.clip(candidate, 0.0, 1.0)))
    delta = np.linalg.norm(cand_lab - ref_lab, axis=-1)

    return {
        "srgb_max_abs": float(np.max(srgb_diff)),
        "srgb_p99_abs": float(np.percentile(srgb_diff, 99.0)),
        "oklab_delta_mean": float(np.mean(delta)),
        "oklab_delta_p95": float(np.percentile(delta, 95.0)),
        "oklab_delta_max": float(np.max(delta)),
        "ssim": _safe_ssim(ref_srgb, cand_srgb),
    }


def failed_metrics(metrics: dict[str, Any], thresholds: MetricThresholds, *, final_sdr: bool) -> dict[str, float]:
    failures: dict[str, float] = {}
    if not metrics.get("shape_match", False):
        failures["shape_match"] = 0.0
    if not metrics.get("finite", False):
        failures["finite"] = 0.0
    for key, limit in (
        ("max_abs", thresholds.max_abs),
        ("p99_abs", thresholds.p99_abs),
        ("rmse", thresholds.rmse),
        ("mean_abs", thresholds.mean_abs),
    ):
        if limit is not None and _metric_value(metrics, key) > limit:
            failures[key] = limit
    if final_sdr:
        for key, limit in (
            ("srgb_p99_abs", thresholds.srgb_p99_abs),
            ("oklab_delta_p95", thresholds.oklab_delta_p95),
        ):
            if limit is not None and _metric_value(metrics, key) > limit:
                failures[key] = limit
        if thresholds.ssim_min is not None and _metric_value(metrics, "ssim") < thresholds.ssim_min:
            failures["ssim"] = thresholds.ssim_min
    return failures


def _metric_value(metrics: dict[str, Any], key: str) -> float:
    value = metrics.get(key)
    if value is None:
        return float("inf")
    return float(value)


def _srgb_encode(linear: np.ndarray) -> np.ndarray:
    linear = np.asarray(linear, dtype=np.float64)
    return np.where(
        linear <= 0.0031308,
        12.92 * linear,
        1.055 * np.power(np.maximum(linear, 0.0), 1.0 / 2.4) - 0.055,
    )


def _srgb_decode(encoded: np.ndarray) -> np.ndarray:
    encoded = np.asarray(encoded, dtype=np.float64)
    return np.where(
        encoded <= 0.04045,
        encoded / 12.92,
        np.power((np.maximum(encoded, 0.0) + 0.055) / 1.055, 2.4),
    )


def _oklab(linear_rgb: np.ndarray) -> np.ndarray:
    rgb = np.asarray(linear_rgb, dtype=np.float64)
    lms = np.einsum(
        "...c,dc->...d",
        rgb,
        np.array(
            [
                [0.4122214708, 0.5363325363, 0.0514459929],
                [0.2119034982, 0.6806995451, 0.1073969566],
                [0.0883024619, 0.2817188376, 0.6299787005],
            ],
            dtype=np.float64,
        ),
    )
    lms_cbrt = np.cbrt(np.maximum(lms, 0.0))
    return np.einsum(
        "...c,dc->...d",
        lms_cbrt,
        np.array(
            [
                [0.2104542553, 0.7936177850, -0.0040720468],
                [1.9779984951, -2.4285922050, 0.4505937099],
                [0.0259040371, 0.7827717662, -0.8086757660],
            ],
            dtype=np.float64,
        ),
    )


def _safe_ssim(reference: np.ndarray, candidate: np.ndarray) -> float:
    if reference.shape != candidate.shape:
        return 0.0
    min_side = min(reference.shape[0], reference.shape[1])
    if min_side < 3:
        return 1.0 if np.array_equal(reference, candidate) else 0.0
    win_size = min(7, min_side)
    if win_size % 2 == 0:
        win_size -= 1
    return float(
        structural_similarity(
            reference,
            candidate,
            data_range=1.0,
            channel_axis=-1,
            win_size=win_size,
        )
    )

