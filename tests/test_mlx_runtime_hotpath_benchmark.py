from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np


def _load_benchmark_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "benchmark_mlx_runtime_hotpath.py"
    spec = importlib.util.spec_from_file_location("benchmark_mlx_runtime_hotpath", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_parse_size_spec_accepts_full_and_dimensions() -> None:
    bench = _load_benchmark_module()

    assert bench.parse_size_spec("full") is None
    assert bench.parse_size_spec("640x480") == (640, 480)


def test_benchmark_specs_include_required_cpu_mlx_and_preview_cases() -> None:
    bench = _load_benchmark_module()

    labels = [spec.label for spec in bench.benchmark_specs(include_preview_640=True)]

    assert labels == [
        "cpu_full_res",
        "mlx_full_res_validate_false",
        "mlx_full_res_validate_true",
        "preview_640",
    ]


def test_describe_array_classifies_numpy_arrays() -> None:
    bench = _load_benchmark_module()
    image = np.zeros((2, 3, 3), dtype=np.float32)

    assert bench.describe_array(image) == {
        "type": "numpy.ndarray",
        "backend": "numpy",
        "shape": [2, 3, 3],
        "dtype": "float32",
        "bytes": 72,
    }


def test_format_markdown_includes_backend_identity_and_type_trace() -> None:
    bench = _load_benchmark_module()
    payload = {
        "run_id": "test",
        "input": {
            "path": "generated",
            "full_shape": [8, 8, 3],
            "dtype": "float64",
        },
        "runs": [
            {
                "label": "mlx_full_res_validate_false",
                "status": "ok",
                "requested_backend": "mlx",
                "selected_backend": "mlx",
                "supports_gpu": True,
                "requires_serial_runtime": True,
                "backend_summary": "MLX selected; mixed CPU/MLX runtime path with optional GPU kernels",
                "image_shape": [8, 8, 3],
                "gpu_precision": "float32",
                "gpu_validate": False,
                "timings": {"FilmingStage.expose": 0.1},
                "total_seconds": 0.2,
                "outer_wall_seconds": 0.21,
                "type_trace": [
                    {
                        "stage": "preprocess",
                        "input": {"type": "numpy.ndarray", "backend": "numpy", "shape": [8, 8, 3], "dtype": "float64", "bytes": 1536},
                        "output": {"type": "mlx.core.array", "backend": "mlx", "shape": [8, 8, 3], "dtype": "float32", "bytes": 768},
                    }
                ],
            }
        ],
    }

    markdown = bench.format_markdown(payload)

    assert "supports_gpu" in markdown
    assert "requires_serial_runtime" in markdown
    assert "backend_summary" in markdown
    assert "preprocess" in markdown
    assert "mlx.core.array" in markdown
