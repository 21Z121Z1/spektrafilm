from __future__ import annotations

import copy

import numpy as np
import pytest

from spektrafilm.gpu.backend import BackendUnavailableError, select_backend
from spektrafilm.gpu.residency import record_backend_residency
from spektrafilm.runtime.pipeline import SimulationPipeline
from spektrafilm.runtime.topology import Tap
from tests.conftest import make_fast_test_params


pytestmark = pytest.mark.integration


def _mlx_backend_or_skip():
    try:
        return select_backend("mlx", precision="float32")
    except BackendUnavailableError as exc:
        pytest.skip(str(exc))


def _image(size: int = 32) -> np.ndarray:
    x = np.linspace(0.02, 0.95, size, dtype=np.float32)[None, :]
    y = np.linspace(0.04, 0.90, size, dtype=np.float32)[:, None]
    xx = np.broadcast_to(x, (size, size))
    yy = np.broadcast_to(y, (size, size))
    return np.stack((xx, yy, 0.5 * (xx + yy)), axis=-1).astype(np.float32)


def _params(*, use_scanner_lut: bool = False):
    params = make_fast_test_params()
    params.settings.compute_backend = "mlx"
    params.settings.gpu_precision = "float32"
    params.settings.materialize_policy = "backend"
    params.settings.gpu_validate = False
    params.settings.preview_mode = True
    params.settings.use_enlarger_lut = False
    params.settings.use_scanner_lut = use_scanner_lut
    params.settings.lut_resolution = 5
    params.io.crop = False
    params.io.upscale_factor = 1.0
    params.camera.auto_exposure = False
    return params


def _format_events(events) -> str:
    return "\n".join(
        f"{event.direction} {event.shape} {event.dtype} {event.nbytes} "
        f"{event.reason} {event.stack_label}"
        for event in events
    )


def test_cpu_default_runtime_still_materializes_float64() -> None:
    params = make_fast_test_params()
    params.settings.compute_backend = "cpu"

    result = SimulationPipeline(params).process(_image(8))

    assert isinstance(result, np.ndarray)
    assert result.dtype == np.float64


def test_mlx_middle_stage_collects_remain_backend_float32() -> None:
    _mlx_backend_or_skip()
    pipeline = SimulationPipeline(_params())

    for tap in (
        Tap.LOG_E_FILM,
        Tap.CMY_FILM,
        Tap.LOG_E_PRINT,
        Tap.CMY_PRINT,
        Tap.RGB_OUT,
    ):
        result = pipeline.process(_image(), collect=tap)
        assert pipeline._backend._is_mlx_array(result), tap
        assert result.dtype == pipeline._backend.mx.float32
        assert tuple(result.shape) == (32, 32, 3)


def test_mlx_runtime_has_no_unallowed_full_size_to_numpy_before_materialize() -> None:
    _mlx_backend_or_skip()
    pipeline = SimulationPipeline(_params())

    with record_backend_residency(small_array_bytes=1024) as recorder:
        result = pipeline.process(_image())

    assert pipeline._backend._is_mlx_array(result)
    unallowed = recorder.unallowed_to_numpy_events()
    assert not unallowed, _format_events(unallowed)


def test_mlx_scanner_lut_apply_path_has_no_unallowed_full_size_to_numpy() -> None:
    _mlx_backend_or_skip()
    pipeline = SimulationPipeline(_params(use_scanner_lut=True))

    with record_backend_residency(small_array_bytes=1024) as recorder:
        result = pipeline.process(_image())

    assert pipeline._backend._is_mlx_array(result)
    unallowed = recorder.unallowed_to_numpy_events()
    assert not unallowed, _format_events(unallowed)


def test_mlx_spectral_lut_requests_use_exact_backend_direct_fallback() -> None:
    _mlx_backend_or_skip()
    image = _image()

    cpu_params = make_fast_test_params()
    cpu_params.settings.compute_backend = "cpu"
    cpu_direct = SimulationPipeline(cpu_params).process(image)

    params = _params(use_scanner_lut=True)
    params.settings.use_enlarger_lut = True
    pipeline = SimulationPipeline(params)
    backend_result = pipeline.process(image)
    result = pipeline._backend.to_numpy(backend_result)

    np.testing.assert_allclose(result, cpu_direct, rtol=0.0, atol=1e-5)
    assert "PrintingStage.gpu_lut_direct_fallback" in pipeline.timings
    assert "SpectralLUTService.gpu_lut_direct_fallback" in pipeline.timings


def test_mlx_soft_update_enlarger_filters_matches_rebuilt_pipeline() -> None:
    _mlx_backend_or_skip()
    image = _image()
    params = _params()
    params.settings.use_enlarger_lut = False

    pipeline = SimulationPipeline(params)
    base = pipeline._backend.to_numpy(pipeline.process(image))

    pipeline.soft_update(c_filter_neutral=80.0)
    soft_updated = pipeline._backend.to_numpy(pipeline.process(image))

    rebuilt_params = copy.deepcopy(params)
    rebuilt_params.enlarger.c_filter_neutral = 80.0
    rebuilt_pipeline = SimulationPipeline(rebuilt_params)
    rebuilt = rebuilt_pipeline._backend.to_numpy(rebuilt_pipeline.process(image))

    assert not np.allclose(base, rebuilt, rtol=0.0, atol=1e-5)
    np.testing.assert_allclose(soft_updated, rebuilt, rtol=0.0, atol=1e-5)


def test_residency_diagnostic_flags_manual_full_size_mlx_to_numpy() -> None:
    backend = _mlx_backend_or_skip()
    value = backend.asarray(_image(), dtype=backend.default_dtype)

    with record_backend_residency(small_array_bytes=1024) as recorder:
        backend.to_numpy(value)

    unallowed = recorder.unallowed_to_numpy_events()
    assert len(unallowed) == 1
    assert unallowed[0].shape == (32, 32, 3)
    assert unallowed[0].reason == "unallowed_full_size_to_numpy"
