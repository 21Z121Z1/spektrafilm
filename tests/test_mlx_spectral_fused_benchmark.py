from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest


pytestmark = pytest.mark.unit


def _load_benchmark_module():
    script = Path(__file__).resolve().parent / "benchmarks" / "benchmark_mlx_spectral_fused.py"
    spec = importlib.util.spec_from_file_location("benchmark_mlx_spectral_fused", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_acceptance_cases_cover_required_sizes() -> None:
    bench = _load_benchmark_module()

    sizes = [(case.height, case.width) for case in bench.acceptance_cases()]

    assert sizes == [(256, 256), (768, 1024), (3024, 4032)]


def test_summarize_ms_reports_required_statistics() -> None:
    bench = _load_benchmark_module()

    summary = bench.summarize_ms([0.001, 0.004, 0.002, 0.003])

    assert summary["runs"] == 4
    assert summary["median_ms"] == pytest.approx(2.5)
    assert summary["p90_ms"] == pytest.approx(3.7)
    assert summary["min_ms"] == pytest.approx(1.0)
    assert summary["max_ms"] == pytest.approx(4.0)


def test_precision_metrics_reports_max_and_mean_diff() -> None:
    bench = _load_benchmark_module()

    metrics = bench.precision_metrics(
        np.array([0.0, 1.0, 2.0], dtype=np.float32),
        np.array([0.0, 1.25, 1.5], dtype=np.float32),
    )

    assert metrics["max_abs_diff"] == pytest.approx(0.5)
    assert metrics["mean_abs_diff"] == pytest.approx(0.25)
    assert metrics["p90_abs_diff"] == pytest.approx(0.45)


def test_evaluate_raw_pixel_thread_acceptance_requires_wall_share_and_ratio() -> None:
    bench = _load_benchmark_module()
    payload = {
        "kernel_runs": [
            {
                "status": "ok",
                "raw_fused_to_xyz_fused_median_ratio": 2.4,
                "raw_pixel_thread_v1_median_speedup_vs_current": 1.4,
                "raw_pixel_thread_v1_p90_speedup_vs_current": 1.2,
                "raw_pixel_thread_v1_peak_memory_ratio_vs_current": 1.0,
                "kernels": {
                    "cmy_to_log_raw": {
                        "results": [
                            {
                                "name": "cmy_to_log_raw_pixel_thread_v1",
                                "precision_vs_current_fused_metal": {"max_abs_diff": 5e-7},
                            }
                        ],
                    }
                },
            },
        ],
        "end_to_end_attribution": {
            "kernel_trace": {
                "cmy_to_log_raw": {"wall_percent": 12.5},
            },
        },
    }

    decision = bench.evaluate_raw_pixel_thread_acceptance(payload)

    assert decision["accept_raw_pixel_thread_v1"] is True
    assert decision["replace_production_recommended"] is True
    assert decision["raw_wall_percent"] == pytest.approx(12.5)
    assert decision["max_raw_fused_to_xyz_fused_median_ratio"] == pytest.approx(2.4)
    assert decision["median_speedup_raw_pixel_thread_v1"] == pytest.approx(1.4)


def test_evaluate_raw_pixel_thread_acceptance_rejects_low_wall_share() -> None:
    bench = _load_benchmark_module()
    payload = {
        "kernel_runs": [
            {
                "status": "ok",
                "raw_fused_to_xyz_fused_median_ratio": 3.0,
                "raw_pixel_thread_v1_median_speedup_vs_current": 1.5,
                "raw_pixel_thread_v1_p90_speedup_vs_current": 1.2,
                "raw_pixel_thread_v1_peak_memory_ratio_vs_current": 1.0,
                "kernels": {
                    "cmy_to_log_raw": {
                        "results": [
                            {
                                "name": "cmy_to_log_raw_pixel_thread_v1",
                                "precision_vs_current_fused_metal": {"max_abs_diff": 2e-7},
                            }
                        ],
                    }
                },
            },
        ],
        "end_to_end_attribution": {
            "kernel_trace": {
                "cmy_to_log_raw": {"wall_percent": 4.0},
            },
        },
    }

    decision = bench.evaluate_raw_pixel_thread_acceptance(payload)

    assert decision["accept_raw_pixel_thread_v1"] is False
    assert "wall share" in decision["reason"]


def test_evaluate_raw_pixel_thread_acceptance_uses_medium_and_full_sizes_for_v1_speedup() -> None:
    bench = _load_benchmark_module()

    def run_payload(height: int, width: int, speedup: float) -> dict:
        return {
            "status": "ok",
            "case": {"height": height, "width": width},
            "raw_fused_to_xyz_fused_median_ratio": 2.4,
            "raw_pixel_thread_v1_median_speedup_vs_current": speedup,
            "raw_pixel_thread_v1_p90_speedup_vs_current": 1.2,
            "raw_pixel_thread_v1_peak_memory_ratio_vs_current": 1.0,
            "kernels": {
                "cmy_to_log_raw": {
                    "results": [
                        {
                            "name": "cmy_to_log_raw_pixel_thread_v1",
                            "precision_vs_current_fused_metal": {"max_abs_diff": 5e-7},
                        }
                    ],
                }
            },
        }

    payload = {
        "kernel_runs": [
            run_payload(256, 256, 0.8),
            run_payload(768, 1024, 1.3),
            run_payload(3024, 4032, 1.4),
        ],
        "end_to_end_attribution": {
            "kernel_trace": {
                "cmy_to_log_raw": {"wall_percent": 12.5},
            },
        },
    }

    decision = bench.evaluate_raw_pixel_thread_acceptance(payload)

    assert decision["accept_raw_pixel_thread_v1"] is True
    assert decision["median_speedup_raw_pixel_thread_v1"] == pytest.approx(1.3)
    assert decision["pixel_thread_v1_decision_case_count"] == 2


def test_format_markdown_includes_kernel_report_and_recommendation() -> None:
    bench = _load_benchmark_module()
    result_template = {
        "summary": {"median_ms": 2.0, "p90_ms": 2.5, "min_ms": 1.8, "max_ms": 3.0},
        "peak_memory_bytes": 8 * 1024 * 1024,
        "speedup_vs_current": 1.0,
        "precision_vs_numpy": {"max_abs_diff": 1e-6, "mean_abs_diff": 2e-7},
        "precision_vs_unfused_backend_chain": {"max_abs_diff": 1e-7, "mean_abs_diff": 2e-8},
        "precision_vs_current_fused_metal": {"max_abs_diff": 0.0, "mean_abs_diff": 0.0},
    }
    pixel_thread_template = {
        **result_template,
        "speedup_vs_current": 1.35,
        "precision_vs_current_fused_metal": {"max_abs_diff": 4e-7, "mean_abs_diff": 1e-7},
    }
    payload = {
        "status": "ok",
        "suite": "mlx_spectral_fused_baseline",
        "seed": 1,
        "recommendation": {
            "accept_raw_pixel_thread_v1": False,
            "replace_production_recommended": False,
            "reason": "rejected: cmy_to_log_raw end-to-end wall share is below threshold",
            "raw_wall_percent": 3.5,
            "max_raw_fused_to_xyz_fused_median_ratio": 1.4,
            "median_speedup_raw_pixel_thread_v1": 1.35,
            "p90_speedup_raw_pixel_thread_v1": 1.1,
            "peak_memory_ratio_raw_pixel_thread_v1": 1.0,
            "max_diff_raw_pixel_thread_v1_vs_current": 4e-7,
        },
        "kernel_runs": [
            {
                "status": "ok",
                "label": "unit_case",
                "case": {
                    "height": 8,
                    "width": 9,
                    "dtype": "float32",
                    "film_profile": "kodak_portra_400",
                    "print_profile": "kodak_portra_endura",
                    "spectral_length": 81,
                    "compile_setup_excluded": True,
                    "static_table_conversion_excluded": True,
                    "numpy_reference_computed": True,
                },
                "warmup": 1,
                "runs": 2,
                "kernels": {
                    "cmy_to_log_raw": {
                        "median_speedup_fused_vs_unfused": 1.2,
                        "median_speedup_pixel_thread_v1_vs_current": 1.35,
                        "p90_speedup_pixel_thread_v1_vs_current": 1.1,
                        "peak_memory_ratio_pixel_thread_v1_vs_current": 1.0,
                        "results": [
                            {"name": "cmy_to_log_raw_unfused_backend_chain", **result_template},
                            {"name": "cmy_to_log_raw_fused_metal", **result_template},
                            {"name": "cmy_to_log_raw_pixel_thread_v1", **pixel_thread_template},
                        ],
                    },
                    "cmy_to_log_xyz": {
                        "median_speedup_fused_vs_unfused": 1.4,
                        "results": [
                            {"name": "cmy_to_log_xyz_unfused_backend_chain", **result_template},
                            {"name": "cmy_to_log_xyz_fused_metal", **result_template},
                        ],
                    },
                },
                "raw_fused_to_xyz_fused_median_ratio": 1.1,
                "raw_pixel_thread_v1_median_speedup_vs_current": 1.35,
                "raw_pixel_thread_v1_p90_speedup_vs_current": 1.1,
                "raw_pixel_thread_v1_peak_memory_ratio_vs_current": 1.0,
            }
        ],
        "end_to_end_attribution": {
            "status": "ok",
            "image_shape": [8, 9, 3],
            "runs": 2,
            "wall_summary": {"median_ms": 10.0},
            "kernel_trace": {
                "cmy_to_log_raw": {
                    "calls": 2,
                    "shapes": {"8x9x3": 2},
                    "total_seconds": 0.002,
                    "median_ms": 1.0,
                    "p90_ms": 1.1,
                    "wall_percent": 10.0,
                }
            },
            "stage_totals": {"PrintingStage.expose": 0.004},
            "stage_wall_percent": {"PrintingStage.expose": 20.0},
        },
    }

    markdown = bench.format_markdown(payload)

    assert "accept_raw_pixel_thread_v1" in markdown
    assert "replace_production_recommended" in markdown
    assert "cmy_to_log_raw_fused_metal" in markdown
    assert "cmy_to_log_raw_pixel_thread_v1" in markdown
    assert "cmy_to_log_xyz_fused_metal" in markdown
    assert "Max diff vs NumPy" in markdown
    assert "Max diff vs current" in markdown
    assert "Mean diff vs unfused" in markdown
    assert "End-To-End Attribution" in markdown
