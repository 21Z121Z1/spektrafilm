from __future__ import annotations

import math

import numpy as np

from spektrafilm.testing.precision_metrics import (
    difference_metrics,
    finite_counts,
    gain_map_ev,
    gain_map_ev_metrics,
    monotonicity_violation_count,
    tile_seam_statistics,
    ulp_distance_float32,
    ulp_metrics,
)


def test_difference_metrics_reports_core_values() -> None:
    reference = np.array([0.0, 0.5, 1.0], dtype=np.float64)
    candidate = np.array([0.0, 0.5, 0.75], dtype=np.float64)

    metrics = difference_metrics(reference, candidate)

    assert metrics["finite_pair_count"] == 3
    assert metrics["max_abs_diff"] == 0.25
    assert metrics["mean_abs_diff"] == np.mean([0.0, 0.0, 0.25])
    assert metrics["rmse"] == math.sqrt((0.25 * 0.25) / 3.0)
    assert metrics["psnr"] > 10.0


def test_difference_metrics_zero_error_has_infinite_psnr() -> None:
    arr = np.array([0.0, 0.5, 1.0], dtype=np.float32)

    metrics = difference_metrics(arr, arr)

    assert metrics["rmse"] == 0.0
    assert math.isinf(metrics["psnr"])


def test_finite_counts_detects_nan_and_inf() -> None:
    counts = finite_counts(np.array([0.0, np.nan, np.inf, -np.inf], dtype=np.float32))

    assert counts == {"total": 4, "finite": 1, "nan": 1, "posinf": 1, "neginf": 1}


def test_ulp_distance_uses_float32_spacing() -> None:
    one = np.array([1.0], dtype=np.float32)
    next_one = np.nextafter(one, np.array([np.inf], dtype=np.float32), dtype=np.float32)

    distance = ulp_distance_float32(one, next_one)
    metrics = ulp_metrics(one, next_one)

    assert distance.tolist() == [1]
    assert metrics["max_ulp"] == 1
    assert metrics["histogram"]["1"] == 1


def test_gain_map_ev_is_log2_luminance_ratio() -> None:
    sdr = np.full((2, 2, 3), 0.5, dtype=np.float32)
    hdr = sdr * np.float32(2.0)

    ev = gain_map_ev(sdr, hdr)
    metrics = gain_map_ev_metrics(sdr, hdr, sdr, hdr)

    np.testing.assert_allclose(ev, np.ones((2, 2)), atol=1e-7)
    assert metrics["units"] == "EV"
    assert metrics["max_abs_diff"] == 0.0


def test_monotonicity_violation_count() -> None:
    values = np.array([0.0, 0.25, 0.24, 0.5, 0.49], dtype=np.float32)

    assert monotonicity_violation_count(values, atol=0.0) == 2
    assert monotonicity_violation_count(values, atol=0.02) == 0


def test_tile_seam_statistics_focuses_on_tile_boundaries() -> None:
    reference = np.zeros((6, 2, 1), dtype=np.float32)
    candidate = reference.copy()
    candidate[2, :, :] = 0.25
    candidate[3, :, :] = -0.125

    stats = tile_seam_statistics(reference, candidate, tile_rows=3)

    assert stats["seam_rows"] == [2, 3]
    assert stats["seam_max_abs_diff"] == 0.25
    assert stats["non_seam_mean_abs_diff"] == 0.0
    assert stats["positive_fraction"] == 0.5
