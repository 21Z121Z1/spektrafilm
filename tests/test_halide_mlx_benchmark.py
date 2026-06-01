from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np


def _load_benchmark_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "benchmark_halide_mlx_parity.py"
    spec = importlib.util.spec_from_file_location("benchmark_halide_mlx_parity", script)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_parse_size_spec_accepts_named_and_explicit_sizes() -> None:
    bench = _load_benchmark_module()

    assert bench.parse_size_spec("full") is None
    assert bench.parse_size_spec("2048x1536") == (2048, 1536)
    assert bench.parse_size_spec("640X480") == (640, 480)


def test_describe_value_reports_numpy_shape_dtype_and_size() -> None:
    bench = _load_benchmark_module()
    array = np.zeros((2, 3, 4), dtype=np.float32)

    info = bench.describe_value(array)

    assert info["type"] == "numpy.ndarray"
    assert info["backend"] == "numpy"
    assert info["shape"] == [2, 3, 4]
    assert info["dtype"] == "float32"
    assert info["nbytes"] == 96


def test_precision_metrics_include_psnr_and_channel_stats() -> None:
    bench = _load_benchmark_module()
    reference = np.ones((2, 2, 3), dtype=np.float64)
    candidate = reference.copy()
    candidate[0, 0, 1] -= 0.25

    metrics = bench.compute_precision_metrics(reference, candidate)

    assert metrics["max_diff"] == 0.25
    assert metrics["mean_diff"] > 0.0
    assert metrics["psnr_db"] > 0.0
    assert metrics["channel_max_diff"] == [0.0, 0.25, 0.0]


def test_format_markdown_summarizes_conversion_counts() -> None:
    bench = _load_benchmark_module()
    payload = {
        "run_id": "unit",
        "input": {
            "path": "input.dng",
            "size_label": "512x384",
            "shape": [384, 512, 3],
        },
        "config": {"grain": "off", "use_lut": True},
        "runs": [
            {
                "label": "halide_float32",
                "status": "ok",
                "requested_backend": "halide",
                "selected_backend": "halide",
                "warmup_seconds": [0.25],
                "best_seconds": 1.0,
                "avg_seconds": 1.1,
                "output": {"shape": [384, 512, 3], "dtype": "float64"},
                "conversions": {
                    "halide.Buffer": {
                        "count": 4,
                        "bytes": 256,
                        "samples": [{"shape": [1, 1, 3]}],
                    }
                },
                "synced_conversions": {},
                "synced_total_seconds": 0.9,
            }
        ],
        "precision": [],
    }

    markdown = bench.format_markdown(payload)

    assert "`halide.Buffer`: 4 / 256 B" in markdown
    assert "samples" not in markdown


def test_format_markdown_reports_warmup_synced_and_conversion_counts() -> None:
    bench = _load_benchmark_module()
    payload = {
        "run_id": "test-run",
        "input": {
            "path": "/tmp/input.dng",
            "size_label": "32x24",
            "shape": [24, 32, 3],
        },
        "config": {"grain": "off", "use_lut": False},
        "runs": [
            {
                "label": "halide_float32",
                "requested_backend": "halide",
                "selected_backend": "halide",
                "status": "ok",
                "best_seconds": 0.5,
                "avg_seconds": 0.6,
                "warmup_seconds": [1.2],
                "synced_total_seconds": 0.4,
                "output": {"shape": [24, 32, 3], "dtype": "float32"},
                "conversions": {
                    "backend.asarray": {"count": 2, "bytes": 128, "samples": []},
                    "halide.Buffer": {"count": 3, "bytes": 256, "samples": []},
                },
                "synced_conversions": {"backend.to_numpy": {"count": 1, "bytes": 64, "samples": []}},
                "synced_stages": [],
            }
        ],
        "precision": [],
    }

    markdown = bench.format_markdown(payload)

    assert "## Run Diagnostics" in markdown
    assert "halide_float32" in markdown
    assert "1.200s" in markdown
    assert "0.400s" in markdown
    assert "`backend.asarray`: 2 / 128 B" in markdown
    assert "`halide.Buffer`: 3 / 256 B" in markdown
    assert "`backend.to_numpy`: 1 / 64 B" in markdown
    assert "samples" not in markdown
