from __future__ import annotations

import numpy as np
import pytest

from tests.conftest import make_fast_test_params

from spektrafilm.gpu.backend import BackendUnavailableError, select_backend
from spektrafilm.runtime.pipeline import SimulationPipeline


pytestmark = pytest.mark.integration


def _require_mlx_backend() -> None:
    try:
        select_backend("mlx")
    except BackendUnavailableError as exc:
        pytest.skip(str(exc))


def test_pipeline_processes_small_image_with_mlx_backend() -> None:
    _require_mlx_backend()
    params = make_fast_test_params()
    params.settings.compute_backend = "mlx"
    params.settings.gpu_precision = "float32"

    image = np.ones((4, 4, 3), dtype=np.float64) * 0.184
    pipeline = SimulationPipeline(params)
    result = pipeline.process(image)

    assert pipeline._array_backend.name == "mlx"
    assert result.shape == (4, 4, 3)
    assert np.all(np.isfinite(result))
    assert np.all(result >= 0.0)
    assert np.all(result <= 1.0)


def test_pipeline_processes_small_image_with_mlx_lut_backend() -> None:
    _require_mlx_backend()
    params = make_fast_test_params()
    params.settings.compute_backend = "mlx"
    params.settings.gpu_precision = "float32"
    params.settings.use_enlarger_lut = True
    params.settings.use_scanner_lut = True
    params.settings.lut_resolution = 5

    image = np.ones((4, 4, 3), dtype=np.float64) * 0.184
    pipeline = SimulationPipeline(params)
    result = pipeline.process(image)

    assert pipeline._array_backend.name == "mlx"
    assert result.shape == (4, 4, 3)
    assert np.all(np.isfinite(result))
    assert np.all(result >= 0.0)
    assert np.all(result <= 1.0)
