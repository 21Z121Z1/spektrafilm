"""Tests for pipeline LUT service lifecycle and SpectralLUTService memory management."""
from __future__ import annotations

import numpy as np
import pytest

from spektrafilm.profiles.io import Hanatos2025SensitivityAdaptation
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
    def fake_compute_tc_lut(sensitivity, adaptation):
        return np.ones((2, 2, 3), dtype=float)

    monkeypatch.setattr(
        spectral_lut_compute_module,
        'compute_hanatos2025_tc_lut',
        fake_compute_tc_lut,
    )

    service = spectral_lut_compute_module.SpectralLUTService(lut_resolution=17)

    # Populate filming tc lut cache
    adaptation = Hanatos2025SensitivityAdaptation(
        window_params=np.empty((0,), dtype=float),
        surface_params=np.empty((0, 3), dtype=float),
        spectral_gaussian_blur=0.0,
        reference_illuminant='D55',
        apply_window=True,
        apply_surface=True,
    )
    service.set_hanatos2025_adaptation(adaptation)
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
    assert service._cached_filming_adaptation is None
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
