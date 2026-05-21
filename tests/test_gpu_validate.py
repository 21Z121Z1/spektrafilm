from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from spektrafilm.runtime.pipeline import SimulationPipeline


pytestmark = pytest.mark.unit


class _FakeGpuBackend:
    supports_gpu = True

    def to_numpy(self, value):
        return value


def test_gpu_validate_skips_in_debug_mode_for_stub_pipeline() -> None:
    pipeline = object.__new__(SimulationPipeline)
    pipeline.timings = {}
    pipeline._last_elapsed_time = None
    pipeline._runtime_dtype = np.dtype(np.float32)
    pipeline._array_backend = _FakeGpuBackend()
    pipeline.debug = SimpleNamespace(debug_mode="inject")
    pipeline.settings = SimpleNamespace(gpu_validate=True)

    # Avoid touching the real runtime pipeline implementation.
    pipeline._should_tile_mlx_image = lambda image: False
    pipeline._pipeline_debug = lambda image: image

    image = np.random.rand(4, 4, 3).astype(np.float32)
    out = pipeline.process(image)

    assert out.shape == image.shape
    assert pipeline.validation_report == {
        "status": "skipped",
        "reason": "debug_mode",
    }
    assert "SimulationPipeline.gpu_validate" in pipeline.timings
