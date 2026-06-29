from __future__ import annotations

import pytest

from spektrafilm.runtime.pipeline import SimulationPipeline
from tests.conftest import make_fast_test_params


class FakeMlxMemoryBackend:
    name = "mlx"
    supports_gpu = True
    fallback_reason = None
    requires_serial_runtime = True
    default_dtype = "float32"

    def __init__(self, *, peak_memory_bytes: int) -> None:
        self.peak_memory_bytes = peak_memory_bytes
        self.reset_calls = 0
        self.cleanup_calls = 0

    def reset_peak_memory(self) -> bool:
        self.reset_calls += 1
        return True

    def memory_snapshot(self) -> dict[str, int | None]:
        return {
            "active_memory_bytes": self.peak_memory_bytes // 2,
            "cache_memory_bytes": 0,
            "peak_memory_bytes": self.peak_memory_bytes,
        }

    def cleanup(self) -> None:
        self.cleanup_calls += 1


def _pipeline_with_fake_backend(*, peak_memory_bytes: int, budget_mb: float, policy: str = "warn"):
    params = make_fast_test_params()
    params.settings.compute_backend = "cpu"
    params.settings.mlx_peak_memory_budget_mb = budget_mb
    params.settings.mlx_peak_memory_policy = policy
    pipeline = SimulationPipeline(params)
    backend = FakeMlxMemoryBackend(peak_memory_bytes=peak_memory_bytes)
    pipeline._backend = backend
    return pipeline, backend


def test_mlx_memory_governance_resets_peak_and_records_warn_budget_overrun() -> None:
    pipeline, backend = _pipeline_with_fake_backend(
        peak_memory_bytes=2 * 1024 * 1024,
        budget_mb=1.0,
    )

    pipeline._prepare_mlx_memory_governance()
    pipeline._apply_mlx_peak_budget_policy()

    assert backend.reset_calls == 1
    assert pipeline.timings["SimulationPipeline.mlx_peak_memory_reset"] == 1.0
    assert pipeline.timings["SimulationPipeline.mlx_peak_memory_bytes"] == float(2 * 1024 * 1024)
    assert pipeline.timings["SimulationPipeline.mlx_peak_memory_budget_bytes"] == float(1024 * 1024)
    assert pipeline.timings["SimulationPipeline.mlx_peak_memory_over_budget"] == float(1024 * 1024)
    assert backend.cleanup_calls == 0


def test_mlx_memory_governance_cleanup_policy_clears_backend_on_budget_overrun() -> None:
    pipeline, backend = _pipeline_with_fake_backend(
        peak_memory_bytes=2 * 1024 * 1024,
        budget_mb=1.0,
        policy="cleanup",
    )

    pipeline._apply_mlx_peak_budget_policy()

    assert backend.cleanup_calls == 1


def test_mlx_memory_governance_raise_policy_fails_on_budget_overrun() -> None:
    pipeline, _backend = _pipeline_with_fake_backend(
        peak_memory_bytes=2 * 1024 * 1024,
        budget_mb=1.0,
        policy="raise",
    )

    with pytest.raises(MemoryError, match="MLX peak memory budget exceeded"):
        pipeline._apply_mlx_peak_budget_policy()
