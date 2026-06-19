from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest


pytestmark = pytest.mark.unit


def _load_benchmark_module():
    script = Path(__file__).resolve().parent / "benchmarks" / "benchmark_mlx_lut_trilinear_3d.py"
    spec = importlib.util.spec_from_file_location("benchmark_mlx_lut_trilinear_3d", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_summarize_ms_reports_median_and_p90() -> None:
    bench = _load_benchmark_module()

    summary = bench.summarize_ms([0.001, 0.004, 0.002, 0.003])

    assert summary["runs"] == 4
    assert summary["median_ms"] == pytest.approx(2.5)
    assert summary["p90_ms"] == pytest.approx(3.7)


def test_make_case_builds_float32_lut_and_out_of_range_probe_pixels() -> None:
    bench = _load_benchmark_module()

    lut, image = bench.make_case(height=5, width=7, lut_size=3, seed=123)

    assert lut.shape == (3, 3, 3, 3)
    assert image.shape == (5, 7, 3)
    assert lut.dtype == np.float32
    assert image.dtype == np.float32
    assert np.min(image) < 0.0
    assert np.max(image) > 1.0


def test_format_markdown_includes_required_timing_and_memory_fields() -> None:
    bench = _load_benchmark_module()
    payload = {
        "status": "ok",
        "case": {"height": 8, "width": 9, "lut_size": 5, "dtype": "float32", "seed": 1},
        "warmup": 2,
        "runs": 3,
        "compile_setup_excluded": True,
        "threadgroup": [256, 1, 1],
        "median_speedup_metal_vs_mlx_ops": 1.25,
        "results": [
            {
                "name": "mlx_ops_baseline",
                "summary": {"median_ms": 2.0, "p90_ms": 2.5, "min_ms": 1.8, "max_ms": 3.0},
                "peak_memory_bytes": 8 * 1024 * 1024,
                "precision_vs_numpy": {"max_abs_diff": 1e-7},
            },
            {
                "name": "metal_kernel",
                "summary": {"median_ms": 1.6, "p90_ms": 1.9, "min_ms": 1.5, "max_ms": 2.1},
                "peak_memory_bytes": 4 * 1024 * 1024,
                "precision_vs_numpy": {"max_abs_diff": 2e-7},
                "precision_vs_mlx_ops_baseline": {"max_abs_diff": 1e-7},
            },
        ],
    }

    markdown = bench.format_markdown(payload)

    assert "Compile/setup excluded: True" in markdown
    assert "Threadgroup: [256, 1, 1]" in markdown
    assert "Median" in markdown
    assert "P90" in markdown
    assert "Peak memory" in markdown
    assert "metal_kernel" in markdown
    assert "Max diff vs MLX ops baseline" in markdown


def test_format_suite_markdown_reports_threadgroup_decisions() -> None:
    bench = _load_benchmark_module()
    payload = {
        "status": "ok",
        "suite": "threadgroup-sweep",
        "seed": 1,
        "runs": [
            {
                "status": "ok",
                "suite": "threadgroup_sweep",
                "label": "unit_case",
                "case": {"height": 4, "width": 5, "lut_size": 3, "dtype": "float32", "seed": 1},
                "warmup": 1,
                "runs": 2,
                "compile_setup_excluded": True,
                "baseline": {
                    "summary": {"median_ms": 2.0, "p90_ms": 2.5},
                    "peak_memory_bytes": 8 * 1024 * 1024,
                },
                "candidates": [
                    {
                        "threadgroup": [128, 1, 1],
                        "summary": {"median_ms": 1.4, "p90_ms": 1.5, "min_ms": 1.3, "max_ms": 1.6},
                        "peak_memory_bytes": 4 * 1024 * 1024,
                        "precision_vs_numpy": {"max_abs_diff": 1e-7},
                        "precision_vs_mlx_ops_baseline": {"max_abs_diff": 2e-7},
                    },
                    {
                        "threadgroup": [256, 1, 1],
                        "summary": {"median_ms": 1.6, "p90_ms": 1.7, "min_ms": 1.5, "max_ms": 1.8},
                        "peak_memory_bytes": 4 * 1024 * 1024,
                        "precision_vs_numpy": {"max_abs_diff": 1e-7},
                        "precision_vs_mlx_ops_baseline": {"max_abs_diff": 2e-7},
                    },
                ],
                "decisions": [
                    {
                        "threadgroup_size": 128,
                        "accepted": True,
                        "baseline": False,
                        "median_change": 0.125,
                        "p90_change": -0.1,
                        "memory_change": 0.0,
                        "reason": "accepted",
                    },
                    {
                        "threadgroup_size": 256,
                        "accepted": True,
                        "baseline": True,
                        "median_change": 0.0,
                        "p90_change": 0.0,
                        "memory_change": 0.0,
                        "reason": "current accepted implementation",
                    },
                ],
                "accepted_threadgroup_size": 128,
            }
        ],
    }

    markdown = bench.format_markdown(payload)

    assert "Threadgroup" in markdown
    assert "Accepted threadgroup size: 128" in markdown
    assert "unit_case" in markdown
    assert "accepted" in markdown
