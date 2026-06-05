from __future__ import annotations

import numpy as np
import pytest

from spektrafilm.gpu.backend import BackendUnavailableError, select_backend
from spektrafilm.runtime.pipeline import SimulationPipeline
from tests.conftest import make_fast_test_params


pytestmark = pytest.mark.integration


def _mlx_backend_or_skip():
    try:
        return select_backend("mlx", precision="float32")
    except BackendUnavailableError as exc:
        pytest.skip(str(exc))


def _image() -> np.ndarray:
    x = np.linspace(0.02, 0.95, 8, dtype=np.float32)[None, :]
    y = np.linspace(0.04, 0.90, 6, dtype=np.float32)[:, None]
    xx = np.broadcast_to(x, (6, 8))
    yy = np.broadcast_to(y, (6, 8))
    return np.stack((xx, yy, 0.5 * (xx + yy)), axis=-1).astype(np.float32)


def _params():
    params = make_fast_test_params()
    params.settings.compute_backend = "mlx"
    params.settings.gpu_precision = "float32"
    params.settings.materialize_policy = "backend"
    params.settings.gpu_validate = False
    params.io.crop = False
    params.io.upscale_factor = 1.0
    params.camera.auto_exposure = False
    return params


def test_mlx_backend_policy_returns_backend_float32_array() -> None:
    _mlx_backend_or_skip()
    pipeline = SimulationPipeline(_params())

    result = pipeline.process(_image())

    assert pipeline._array_backend._is_mlx_array(result)
    assert result.dtype == pipeline._array_backend.mx.float32
    assert pipeline.timings["SimulationPipeline.materialize"] < 1e-3


def test_mlx_backend_policy_does_not_materialize_through_numpy_float64(monkeypatch) -> None:
    _mlx_backend_or_skip()
    pipeline = SimulationPipeline(_params())
    backend_value = pipeline._backend.asarray(_image(), dtype=pipeline._backend.default_dtype)

    def fail_asarray(*_args, **_kwargs):
        raise AssertionError("backend materialize policy must not call np.asarray")

    import spektrafilm.runtime.pipeline as pipeline_module

    monkeypatch.setattr(pipeline_module.np, "asarray", fail_asarray)

    assert pipeline._materialize_output(backend_value) is backend_value


def test_mlx_backend_policy_explicit_numpy_conversion_matches_cpu_reference() -> None:
    _mlx_backend_or_skip()
    params = _params()
    image = _image()

    cpu_params = make_fast_test_params()
    cpu_params.settings.compute_backend = "cpu"
    cpu_reference = SimulationPipeline(cpu_params).process(image)

    pipeline = SimulationPipeline(params)
    backend_result = pipeline.process(image)
    numpy_result = pipeline._backend.to_numpy(backend_result)

    assert numpy_result.dtype == np.float32
    assert np.all(np.isfinite(numpy_result))
    np.testing.assert_allclose(numpy_result, cpu_reference, rtol=0.0, atol=1e-5)


def test_mlx_float32_preprocess_keeps_backend_dtype_without_resize() -> None:
    _mlx_backend_or_skip()
    params = _params()
    pipeline = SimulationPipeline(params)
    rgba = np.ones((5, 7, 4), dtype=np.float64) * 0.184

    preprocessed, auto_ev = pipeline._preprocess_base(rgba)

    assert auto_ev is None
    assert pipeline._backend._is_mlx_array(preprocessed)
    assert preprocessed.dtype == pipeline._backend.mx.float32
    assert tuple(preprocessed.shape) == (5, 7, 3)
