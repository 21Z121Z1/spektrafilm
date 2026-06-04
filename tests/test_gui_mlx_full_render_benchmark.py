from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_benchmark_module():
    script = Path(__file__).resolve().parents[1] / "tools" / "benchmark_gui_mlx_full_render.py"
    spec = importlib.util.spec_from_file_location("benchmark_gui_mlx_full_render", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_parse_size_accepts_full_and_dimensions() -> None:
    bench = _load_benchmark_module()

    assert bench.parse_size("full") is None
    assert bench.parse_size("640x480") == (640, 480)


def test_summarize_seconds_reports_median_min_max() -> None:
    bench = _load_benchmark_module()

    assert bench.summarize_seconds([0.4, 0.1, 0.2]) == {
        "median": 0.2,
        "min": 0.1,
        "max": 0.4,
    }


def test_memory_nbytes_handles_missing_arrays() -> None:
    bench = _load_benchmark_module()

    assert bench.array_nbytes(None) == 0
