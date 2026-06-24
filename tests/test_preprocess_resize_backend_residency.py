from __future__ import annotations

import numpy as np
import pytest

from tests.conftest import make_fast_test_params

from spektrafilm.gpu.backend import BackendUnavailableError, select_backend
from spektrafilm.runtime.pipeline import SimulationPipeline


pytestmark = pytest.mark.integration


def _mlx_available_or_skip() -> None:
    try:
        select_backend("mlx", precision="float32")
    except BackendUnavailableError as exc:
        pytest.skip(str(exc))


def _mlx_backend_params(*, upscale_factor: float):
    params = make_fast_test_params()
    params.settings.compute_backend = "mlx"
    params.settings.gpu_precision = "float32"
    params.settings.materialize_policy = "backend"
    params.io.upscale_factor = upscale_factor
    params.io.crop = False
    params.camera.auto_exposure = False
    return params


def test_mlx_backend_preprocess_upscale_records_cpu_fallback_and_residency_break() -> None:
    _mlx_available_or_skip()
    params = _mlx_backend_params(upscale_factor=1.25)
    pipeline = SimulationPipeline(params)
    image = np.ones((8, 10, 3), dtype=np.float32) * 0.184

    preprocessed, auto_ev = pipeline._preprocess_base(image)

    assert auto_ev is None
    assert pipeline._backend._is_mlx_array(preprocessed)
    assert tuple(preprocessed.shape[:2]) == (10, 12)
    assert pipeline.timings["SimulationPipeline.preprocess.resize_cpu_fallback"] >= 0.0
    assert (
        pipeline.timings["SimulationPipeline.preprocess.resize_breaks_backend_residency"]
        == pipeline.timings["SimulationPipeline.preprocess.resize_cpu_fallback"]
    )


def test_mlx_backend_preprocess_default_scale_does_not_record_resize_fallback() -> None:
    _mlx_available_or_skip()
    params = _mlx_backend_params(upscale_factor=1.0)
    pipeline = SimulationPipeline(params)
    image = np.ones((8, 10, 3), dtype=np.float32) * 0.184

    preprocessed, auto_ev = pipeline._preprocess_base(image)

    assert auto_ev is None
    assert pipeline._backend._is_mlx_array(preprocessed)
    assert tuple(preprocessed.shape[:2]) == (8, 10)
    assert "SimulationPipeline.preprocess.resize_cpu_fallback" not in pipeline.timings
    assert "SimulationPipeline.preprocess.resize_breaks_backend_residency" not in pipeline.timings
