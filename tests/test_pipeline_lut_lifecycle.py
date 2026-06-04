"""Tests for pipeline LUT service lifecycle and SpectralLUTService memory management."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from spektrafilm.runtime.services import spectral_lut_compute as spectral_lut_compute_module


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# SpectralLUTService: lut_resolution property
# ---------------------------------------------------------------------------

def test_lut_resolution_property_matches_constructor_value():
    service = spectral_lut_compute_module.SpectralLUTService(lut_resolution=33)
    assert service.lut_resolution == 33


# ---------------------------------------------------------------------------
# SpectralLUTService: clear() releases all cached data
# ---------------------------------------------------------------------------

def test_clear_releases_all_cached_fields(monkeypatch):
    def fake_compute_tc_lut(sensitivity, adaptation=None, *, gamut_compress=False):
        return np.ones((2, 2, 3), dtype=float)

    monkeypatch.setattr(
        spectral_lut_compute_module,
        'compute_hanatos2025_tc_lut',
        fake_compute_tc_lut,
    )

    service = spectral_lut_compute_module.SpectralLUTService(lut_resolution=17)

    # Populate filming tc lut cache
    service.get_filming_tc_lut(np.ones((4, 3)))

    # Populate enlarger/scanner LUT caches manually
    service.enlarger_lut_memory = np.zeros((17, 17, 17, 3))
    service._enlarger_test_results_memory = np.zeros((2, 2, 3))
    service.scanner_lut_memory = np.zeros((17, 17, 17, 3))
    service._scanner_test_results_memory = np.zeros((2, 2, 3))

    # Verify caches are populated
    assert service.filming_tc_lut_memory is not None
    assert service.enlarger_lut_memory is not None
    assert service.scanner_lut_memory is not None

    # Clear and verify
    service.clear()

    assert service.filming_tc_lut_memory is None
    assert service.enlarger_lut_memory is None
    assert service.scanner_lut_memory is None
    assert service._film_sensitivity is None
    assert service._film_tc_lut_key is None
    assert service._enlarger_test_results_memory is None
    assert service._scanner_test_results_memory is None


# ---------------------------------------------------------------------------
# SpectralLUTService: memory_info() returns byte sizes
# ---------------------------------------------------------------------------

def test_memory_info_reports_zero_when_caches_empty():
    service = spectral_lut_compute_module.SpectralLUTService(lut_resolution=17)
    info = service.memory_info()
    assert all(v == 0 for v in info.values())


def test_memory_info_reports_nonzero_after_caching():
    service = spectral_lut_compute_module.SpectralLUTService(lut_resolution=17)
    service.enlarger_lut_memory = np.zeros((17, 17, 17, 3), dtype=np.float64)
    info = service.memory_info()
    assert info['enlarger_lut'] > 0
    assert info['scanner_lut'] == 0


# ---------------------------------------------------------------------------
# Pipeline: update() rebuilds LUT service when lut_resolution changes
# ---------------------------------------------------------------------------

def test_pipeline_update_rebuilds_lut_service_on_resolution_change():
    from spektrafilm.runtime.params_builder import init_params, digest_params
    from spektrafilm.runtime.pipeline import SimulationPipeline

    params = digest_params(init_params())
    params.settings.lut_resolution = 5
    pipeline = SimulationPipeline(params)
    assert pipeline._lut_service.lut_resolution == 5

    # Update with different resolution
    params_new = digest_params(init_params())
    params_new.settings.lut_resolution = 9
    pipeline.update(params_new)
    assert pipeline._lut_service.lut_resolution == 9


def test_pipeline_update_reuses_lut_service_when_resolution_unchanged():
    from spektrafilm.runtime.params_builder import init_params, digest_params
    from spektrafilm.runtime.pipeline import SimulationPipeline

    params = digest_params(init_params())
    params.settings.lut_resolution = 17
    pipeline = SimulationPipeline(params)
    original_service = pipeline._lut_service

    # Update with same resolution
    params_new = digest_params(init_params())
    params_new.settings.lut_resolution = 17
    pipeline.update(params_new)

    assert pipeline._lut_service is original_service


def test_pipeline_update_reuses_mlx_backend_without_cleanup_when_selection_unchanged(monkeypatch):
    from spektrafilm.runtime.params_builder import init_params, digest_params
    from spektrafilm.runtime import pipeline as pipeline_module

    class FakeMlxBackend:
        name = "mlx"
        supports_gpu = False
        fallback_reason = None
        requires_serial_runtime = False

        def __init__(self, precision: str) -> None:
            self.precision = precision
            self.cleanup_calls = 0

        def cleanup(self) -> None:
            self.cleanup_calls += 1

    created: list[FakeMlxBackend] = []

    def fake_select_backend(name, *, precision):
        assert name == "mlx"
        backend = FakeMlxBackend(precision)
        created.append(backend)
        return backend

    monkeypatch.setattr(pipeline_module, "select_backend", fake_select_backend)

    params = digest_params(init_params())
    params.settings.compute_backend = "mlx"
    params.settings.gpu_precision = "float32"
    pipeline = pipeline_module.SimulationPipeline(params)
    original_backend = pipeline._backend
    original_service = pipeline._lut_service

    params_new = digest_params(init_params())
    params_new.settings.compute_backend = "mlx"
    params_new.settings.gpu_precision = "float32"
    pipeline.update(params_new)

    assert created == [original_backend]
    assert pipeline._backend is original_backend
    assert pipeline._lut_service is original_service
    assert pipeline._lut_service._backend is original_backend
    assert original_backend.cleanup_calls == 0


def test_pipeline_mlx_cleanup_triggers_when_cache_threshold_is_exceeded():
    from spektrafilm.runtime.pipeline import SimulationPipeline

    pipeline = object.__new__(SimulationPipeline)
    pipeline._backend = SimpleNamespace(
        name="mlx",
        cleanup=lambda: None,
        mx=SimpleNamespace(get_cache_memory=lambda: 9 * 1024 * 1024),
    )
    pipeline.settings = SimpleNamespace(
        gpu_aggressive_cleanup=False,
        preview_mode=False,
        gpu_cleanup_cache_threshold_mb=8.0,
    )

    assert pipeline._should_cleanup_after_process() is True


def test_pipeline_mlx_cleanup_skips_when_cache_is_below_threshold():
    from spektrafilm.runtime.pipeline import SimulationPipeline

    pipeline = object.__new__(SimulationPipeline)
    pipeline._backend = SimpleNamespace(
        name="mlx",
        cleanup=lambda: None,
        mx=SimpleNamespace(get_cache_memory=lambda: 7 * 1024 * 1024),
    )
    pipeline.settings = SimpleNamespace(
        gpu_aggressive_cleanup=False,
        preview_mode=False,
        gpu_cleanup_cache_threshold_mb=8.0,
    )

    assert pipeline._should_cleanup_after_process() is False


def test_pipeline_update_rebuilds_lut_service_when_backend_changes(monkeypatch):
    from spektrafilm.runtime.params_builder import init_params, digest_params
    from spektrafilm.runtime import pipeline as pipeline_module

    class FakeBackend:
        supports_gpu = False
        fallback_reason = None
        requires_serial_runtime = False

        def __init__(self, name):
            self.name = name

    def fake_select_backend(name, *, precision):
        return FakeBackend(f"{name}:{precision}")

    monkeypatch.setattr(pipeline_module, "select_backend", fake_select_backend)

    params = digest_params(init_params())
    params.settings.compute_backend = "cpu"
    params.settings.gpu_precision = "float32"
    params.settings.lut_resolution = 17
    pipeline = pipeline_module.SimulationPipeline(params)
    original_service = pipeline._lut_service
    assert original_service._backend is pipeline._backend

    params_new = digest_params(init_params())
    params_new.settings.compute_backend = "auto"
    params_new.settings.gpu_precision = "float32"
    params_new.settings.lut_resolution = 17
    pipeline.update(params_new)

    assert pipeline._lut_service is not original_service
    assert pipeline._lut_service._backend is pipeline._backend


def test_pipeline_update_does_not_reuse_lut_service_when_resolution_differs():
    from spektrafilm.runtime.params_builder import init_params, digest_params
    from spektrafilm.runtime.pipeline import SimulationPipeline

    params = digest_params(init_params())
    params.settings.lut_resolution = 17
    pipeline = SimulationPipeline(params)
    original_service = pipeline._lut_service

    # Update with different resolution
    params_new = digest_params(init_params())
    params_new.settings.lut_resolution = 33
    pipeline.update(params_new)

    assert pipeline._lut_service is not original_service
    assert pipeline._lut_service.lut_resolution == 33
