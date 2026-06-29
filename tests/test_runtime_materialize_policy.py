from __future__ import annotations

import numpy as np
import pytest

from spektrafilm.runtime.params_schema import RuntimePhotoParams
from spektrafilm.runtime.pipeline import SimulationPipeline, SimulationPipelineResult
from tests.conftest import make_fast_test_params


pytestmark = pytest.mark.integration


def _small_image(dtype=np.float32) -> np.ndarray:
    return np.full((4, 5, 3), 0.184, dtype=dtype)


def test_default_cpu_public_api_materializes_numpy_float64() -> None:
    params = make_fast_test_params()
    params.settings.compute_backend = "cpu"

    result = SimulationPipeline(params).process(_small_image())

    assert isinstance(result, np.ndarray)
    assert result.dtype == np.float64


def test_numpy_float32_policy_materializes_numpy_float32() -> None:
    params = make_fast_test_params()
    params.settings.compute_backend = "cpu"
    params.settings.materialize_policy = "numpy_float32"

    result = SimulationPipeline(params).process(_small_image())

    assert isinstance(result, np.ndarray)
    assert result.dtype == np.float32


def test_backend_policy_on_cpu_returns_numpy_without_changing_default_dtype() -> None:
    params = make_fast_test_params()
    params.settings.compute_backend = "cpu"
    params.settings.materialize_policy = "backend"

    result = SimulationPipeline(params).process(_small_image())

    assert isinstance(result, np.ndarray)
    assert result.dtype == np.float64


def test_process_with_metadata_uses_materialize_policy_and_keeps_metadata_usable() -> None:
    params = make_fast_test_params()
    params.settings.compute_backend = "cpu"
    params.settings.materialize_policy = "numpy_float32"

    result = SimulationPipeline(params).process_with_metadata(_small_image())

    assert isinstance(result, SimulationPipelineResult)
    assert isinstance(result.image, np.ndarray)
    assert result.image.dtype == np.float32
    assert result.hdr_scene_energy is not None
    assert isinstance(result.hdr_scene_energy.scene_luminance, np.ndarray)
    assert result.hdr_scene_energy.scene_luminance.dtype == np.float32
    assert np.all(np.isfinite(result.hdr_scene_energy.scene_luminance))


def test_invalid_materialize_policy_raises_clear_error() -> None:
    params = make_fast_test_params()
    params.settings.materialize_policy = "device_magic"

    with pytest.raises(ValueError, match="materialize_policy must be one of"):
        SimulationPipeline(params).process(_small_image())


def test_runtime_params_constructor_rejects_invalid_materialize_policy() -> None:
    params = make_fast_test_params()

    with pytest.raises(ValueError, match="materialize_policy must be one of"):
        RuntimePhotoParams(
            film=params.film,
            print=params.print,
            settings=type(params.settings)(materialize_policy="device_magic"),
        )


def test_runtime_params_constructor_rejects_invalid_hdr_route_sidecar_policy() -> None:
    params = make_fast_test_params()

    with pytest.raises(ValueError, match="hdr_route_sidecar_policy must be either"):
        RuntimePhotoParams(
            film=params.film,
            print=params.print,
            settings=type(params.settings)(hdr_route_sidecar_policy="debug_everything"),
        )


def test_runtime_params_constructor_rejects_invalid_resize_backend_policy() -> None:
    params = make_fast_test_params()

    with pytest.raises(ValueError, match="preprocess_resize_backend_policy"):
        RuntimePhotoParams(
            film=params.film,
            print=params.print,
            settings=type(params.settings)(preprocess_resize_backend_policy="hidden_numpy"),
        )


def test_runtime_params_constructor_rejects_invalid_mlx_memory_governance_policy() -> None:
    params = make_fast_test_params()

    with pytest.raises(ValueError, match="mlx_peak_memory_policy"):
        RuntimePhotoParams(
            film=params.film,
            print=params.print,
            settings=type(params.settings)(mlx_peak_memory_policy="kill_process"),
        )
