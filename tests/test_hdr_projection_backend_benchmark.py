from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest


pytestmark = pytest.mark.unit


def _load_benchmark_module():
    script = Path(__file__).resolve().parent / "benchmarks" / "benchmark_hdr_projection_backend.py"
    spec = importlib.util.spec_from_file_location("benchmark_hdr_projection_backend", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_benchmark_modes_distinguish_backend_and_chemical_fallback_paths() -> None:
    bench = _load_benchmark_module()

    modes = bench.benchmark_modes()

    assert [mode.label for mode in modes] == [
        "light_table_backend_resident",
        "paper_generic_backend_resident",
        "paper_chemical_numpy_fallback",
    ]
    assert [mode.chemical_profile for mode in modes] == [False, False, True]


def test_make_synthetic_arrays_and_master_shape() -> None:
    bench = _load_benchmark_module()
    arrays = bench.make_synthetic_arrays(height=3, width=5, seed=1)
    mode = bench.benchmark_modes()[0]

    master = bench.make_master(arrays, mode)

    assert master.route_linear_rgb.shape == (3, 5, 3)
    assert master.scene_y_raw.shape == (3, 5)
    assert master.diagnostics["output_cctf_encoding"] is False
    assert np.max(master.scene_y_raw) > 1.0


def test_format_markdown_includes_sort_timing_memory_and_mode_boundaries() -> None:
    bench = _load_benchmark_module()
    payload = {
        "status": "ok",
        "input": {"height": 3000, "width": 4000, "pixels": 12_000_000, "seed": 1},
        "runs": 1,
        "warmups": 1,
        "results": [
            {
                "mode": "light_table_backend_resident",
                "cpu_projection": {
                    "summary": {"median_ms": 100.0, "p90_ms": 100.0},
                    "result_backend": "numpy",
                    "projection_metadata_statistics": None,
                    "projection_profiles": [],
                    "peak_memory_bytes": None,
                    "cache_memory_bytes": None,
                },
                "backend_master_projection": {
                    "summary": {"median_ms": 50.0, "p90_ms": 50.0},
                    "result_backend": "mlx",
                    "projection_metadata_statistics": "omitted_backend_fast_path",
                    "projection_profiles": [
                        {
                            "percentile_sort_ms_total": 3.0,
                            "percentile_calls": [
                                {
                                    "label": "extension_gain",
                                    "percentile": 99.9,
                                    "size": 12_000_000,
                                    "sort_to_scalar_ms": 1.25,
                                }
                            ],
                        }
                    ],
                    "peak_memory_bytes": 8 * 1024 * 1024,
                    "cache_memory_bytes": 4 * 1024 * 1024,
                },
            }
        ],
    }

    markdown = bench.format_markdown(payload)

    assert "light_table_backend_resident" in markdown
    assert "Backend RouteMaster projection" in markdown
    assert "MLX peak memory" in markdown
    assert "MLX cache memory" in markdown
    assert "Percentile sort total" in markdown
    assert "extension_gain" in markdown
    assert "omitted_backend_fast_path" in markdown
