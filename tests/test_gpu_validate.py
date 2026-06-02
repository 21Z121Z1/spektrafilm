from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from spektrafilm.runtime import pipeline as pipeline_module
from spektrafilm.runtime.pipeline import SimulationPipeline


pytestmark = pytest.mark.unit


class _FakeGpuBackend:
    name = "mlx"
    supports_gpu = True

    def to_numpy(self, value):
        return value


class _FakeCpuPipeline:
    captured_params = None
    captured_image = None
    reference = None

    def __init__(self, params):
        type(self).captured_params = params

    def process(self, image):
        type(self).captured_image = image
        return type(self).reference


def _stub_validation_pipeline():
    pipeline = object.__new__(SimulationPipeline)
    pipeline.timings = {}
    pipeline._last_elapsed_time = None
    pipeline._array_backend = _FakeGpuBackend()
    pipeline.debug = SimpleNamespace()
    pipeline.settings = SimpleNamespace(
        compute_backend="mlx",
        gpu_precision="float32",
        gpu_validate=True,
        gpu_validation_tolerance=None,
        use_enlarger_lut=False,
        use_scanner_lut=False,
    )
    pipeline._params = SimpleNamespace(settings=pipeline.settings)
    return pipeline





def test_gpu_validate_runs_cpu_reference_and_records_metrics(monkeypatch) -> None:
    pipeline = _stub_validation_pipeline()
    source = np.full((2, 2, 3), 0.18, dtype=np.float32)
    gpu_output = np.full((2, 2, 3), 0.25, dtype=np.float32)
    _FakeCpuPipeline.reference = gpu_output + 5e-6

    monkeypatch.setattr(pipeline_module, "SimulationPipeline", _FakeCpuPipeline)

    pipeline._run_gpu_validate(source, gpu_output)

    report = pipeline.validation_report
    assert report["status"] == "ok"
    assert report["backend"] == "mlx"
    assert report["reference_backend"] == "cpu"
    assert report["shape"] == (2, 2, 3)
    assert report["tolerance"] == pytest.approx(1e-5)
    assert report["max_abs_diff"] == pytest.approx(5e-6, rel=0, abs=1e-8)
    assert report["mean_abs_diff"] == pytest.approx(5e-6, rel=0, abs=1e-8)
    assert _FakeCpuPipeline.captured_image is source
    assert _FakeCpuPipeline.captured_params is not pipeline._params
    assert _FakeCpuPipeline.captured_params.settings.compute_backend == "cpu"
    assert _FakeCpuPipeline.captured_params.settings.gpu_validate is False
    assert "SimulationPipeline.gpu_validate" in pipeline.timings


def test_gpu_validate_raises_when_cpu_reference_diverges(monkeypatch) -> None:
    pipeline = _stub_validation_pipeline()
    source = np.full((2, 2, 3), 0.18, dtype=np.float32)
    gpu_output = np.full((2, 2, 3), 0.25, dtype=np.float32)
    _FakeCpuPipeline.reference = gpu_output + 1e-3

    monkeypatch.setattr(pipeline_module, "SimulationPipeline", _FakeCpuPipeline)

    with pytest.raises(RuntimeError, match="GPU validation failed"):
        pipeline._run_gpu_validate(source, gpu_output)

    assert pipeline.validation_report["status"] == "failed"
    assert pipeline.validation_report["max_abs_diff"] == pytest.approx(1e-3, rel=0, abs=1e-7)
