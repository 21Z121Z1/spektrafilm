from __future__ import annotations

import numpy as np
import pytest

from benchmarks import benchmark_mlx_tile_assembly as bench
from spektrafilm.gpu.backend import BackendUnavailableError, select_backend


pytestmark = pytest.mark.integration


def _mlx_backend_or_skip():
    try:
        return select_backend("mlx", precision="float32")
    except BackendUnavailableError as exc:
        pytest.skip(str(exc))


def test_resolve_benchmark_tile_rows_includes_current_default() -> None:
    assert bench.resolve_benchmark_tile_rows(
        3072,
        [256, 512, 1024, 2048],
        spatial=False,
    ) == [256, 384, 512, 1024, 2048]
    assert bench.resolve_benchmark_tile_rows(
        4000,
        [256, 512, 1024, 2048],
        spatial=True,
    ) == [256, 512, 1024, 2048]


def test_metal_scatter_is_marked_infeasible_without_safe_inplace_output() -> None:
    feasible, reason = bench.metal_scatter_feasibility()

    assert feasible is False
    assert "in-place" in reason
    assert "full-frame output per tile" in reason


def test_recommendation_keeps_at_add_when_concat_memory_gate_fails() -> None:
    summaries = [
        bench.StrategySummary("12mp", "at_add", "ok", 1.0, 100.0, 0.0, 1),
        bench.StrategySummary("12mp", "concat", "ok", 0.8, 130.0, 0.0, 1),
        bench.StrategySummary("24mp", "at_add", "ok", 2.0, 200.0, 0.0, 1),
        bench.StrategySummary("24mp", "concat", "ok", 1.7, 250.0, 0.0, 1),
    ]

    recommendation = bench.recommendation_from_summaries(summaries)

    assert recommendation["should_change_write_tile_default"] is False
    assert recommendation["default_strategy_recommendation"] == "keep_at_add"


def test_concat_assembly_matches_at_add_for_small_mlx_arrays() -> None:
    backend = _mlx_backend_or_skip()
    rng = np.random.default_rng(20260624)
    image = backend.asarray(rng.uniform(0.0, 1.0, size=(64, 48, 3)).astype(np.float32))

    spectral_fn = bench.spectral_process_fn(backend.mx)
    spectral_ref = bench.assemble_spectral_at_add(image, spectral_fn, backend, 16)
    spectral_concat = bench.assemble_spectral_concat(image, spectral_fn, backend, 16)
    assert bench.max_abs_diff(spectral_concat, spectral_ref, backend) <= 1e-6

    spatial_fn = bench.spatial_process_fn(backend.mx)
    spatial_ref = bench.assemble_spatial_at_add(
        image,
        spatial_fn,
        backend,
        overlap=4,
        tile_rows=16,
    )
    spatial_concat = bench.assemble_spatial_concat(
        image,
        spatial_fn,
        backend,
        overlap=4,
        tile_rows=16,
    )
    assert bench.max_abs_diff(spatial_concat, spatial_ref, backend) <= 1e-6
