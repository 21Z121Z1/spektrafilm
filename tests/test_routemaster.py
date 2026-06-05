from __future__ import annotations

import copy

import numpy as np
import pytest

from spektrafilm.runtime.params_builder import digest_params, init_params
from spektrafilm.runtime.pipeline import SimulationPipeline
from spektrafilm.runtime.process import Simulator


pytestmark = pytest.mark.integration


def make_fast_test_params(*, film_profile: str = "kodak_portra_400", print_profile: str = "kodak_portra_endura"):
    params = init_params(film_profile=film_profile, print_profile=print_profile)
    params.debug.deactivate_spatial_effects = True
    params.debug.deactivate_stochastic_effects = True
    params.settings.use_enlarger_lut = False
    params.settings.use_scanner_lut = False
    params.io.upscale_factor = 1.0
    params.io.crop = False
    params.camera.auto_exposure = False
    params.camera.exposure_compensation_ev = 0.0
    return digest_params(params)


def _small_hdr_patch(size: int = 6) -> np.ndarray:
    ramp = np.linspace(0.03, 1.5, size, dtype=np.float64)
    image = np.ones((size, size, 3), dtype=np.float64)
    image *= ramp[None, :, None]
    image[:, size // 2 :, 0] *= 1.15
    image[:, : size // 2, 2] *= 0.85
    return image


def test_routemaster_fields_complete() -> None:
    params = make_fast_test_params()
    image = _small_hdr_patch()

    master = Simulator(params).process_master(image, hdr_mode="paper")

    assert master.mode == "paper"
    assert master.route_kind == "print_scan"
    assert master.route_linear_rgb.shape == image.shape
    assert master.route_linear_xyz.shape == image.shape
    assert master.route_luminance_y.shape == image.shape[:2]
    assert master.sdr_legacy_rgb.shape == image.shape
    assert master.scene_y_raw.shape == image.shape[:2]
    assert master.post_halation_y.shape == image.shape[:2]
    assert master.density_cmy.shape == image.shape
    assert isinstance(master.diagnostics, dict)
    for field in (
        master.route_linear_rgb,
        master.route_linear_xyz,
        master.route_luminance_y,
        master.sdr_legacy_rgb,
        master.scene_y_raw,
        master.post_halation_y,
        master.density_cmy,
    ):
        assert np.all(np.isfinite(field))


def test_scan_master_project_sdr_legacy_equivalence() -> None:
    params = make_fast_test_params()
    image = _small_hdr_patch()
    pipeline = SimulationPipeline(params)

    preprocessed = pipeline._preprocess(image)
    log_raw_film = pipeline._filming_stage.expose(preprocessed)
    cmy_film = pipeline._filming_stage.develop(log_raw_film)
    log_raw_print = pipeline._printing_stage.expose(cmy_film)
    cmy_print = pipeline._printing_stage.develop(log_raw_print)

    scan_master = pipeline._scanning_stage.scan_master(cmy_print)
    projected = pipeline._scanning_stage.project_sdr_legacy(scan_master)
    legacy = pipeline._scanning_stage.scan(cmy_print)

    np.testing.assert_allclose(projected, legacy, rtol=0.0, atol=1e-9)


def test_routemaster_sdr_equivalence_print_scan() -> None:
    params = make_fast_test_params()
    image = _small_hdr_patch()
    simulator = Simulator(copy.deepcopy(params))

    legacy = simulator.process(image)
    master = simulator.process_master(image, hdr_mode="paper")

    np.testing.assert_allclose(master.sdr_legacy_rgb, legacy, rtol=0.0, atol=1e-9)


def test_routemaster_sdr_equivalence_positive_film_scan() -> None:
    params = make_fast_test_params(film_profile="fujifilm_provia_100f")
    params.io.scan_film = True
    image = _small_hdr_patch()
    simulator = Simulator(copy.deepcopy(params))

    legacy = simulator.process(image)
    master = simulator.process_master(image, hdr_mode="light_table")

    assert master.route_kind == "film_scan"
    np.testing.assert_allclose(master.sdr_legacy_rgb, legacy, rtol=0.0, atol=1e-9)


def test_process_master_does_not_change_process_output() -> None:
    params = make_fast_test_params()
    image = _small_hdr_patch()
    simulator = Simulator(copy.deepcopy(params))

    before = simulator.process(image)
    _master = simulator.process_master(image, hdr_mode="paper")
    after = simulator.process(image)

    np.testing.assert_allclose(after, before, rtol=0.0, atol=1e-9)


def test_post_halation_y_shape_and_finiteness() -> None:
    params = make_fast_test_params()
    image = _small_hdr_patch()

    master = Simulator(params).process_master(image, hdr_mode="paper")

    assert master.post_halation_y.shape == master.route_luminance_y.shape
    assert np.all(np.isfinite(master.post_halation_y))
    assert float(np.max(master.post_halation_y)) > 0.0
    assert master.diagnostics["post_halation_y_source"] in {
        "filming_raw_after_halation",
        "backend_materialized",
    }


def test_density_cmy_sidecar_shape_and_finiteness() -> None:
    params = make_fast_test_params()
    image = _small_hdr_patch()

    master = Simulator(params).process_master(image, hdr_mode="paper")

    assert master.density_cmy.shape == master.sdr_legacy_rgb.shape
    assert np.all(np.isfinite(master.density_cmy))
