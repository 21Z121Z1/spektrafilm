from __future__ import annotations

import copy

import numpy as np
import pytest

from spektrafilm.runtime.params_builder import digest_params, init_params
from spektrafilm.runtime.pipeline import SimulationPipeline
from spektrafilm.runtime.process import Simulator
from spektrafilm.runtime.route_master import (
    iter_route_master_sidecars,
    route_master_sidecar_fields,
    route_master_sidecar_nbytes,
)
from spektrafilm.utils.gamut_compression import OutputGamutCompressSpec


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


def make_equivalence_params(
    *,
    case: str,
    film_profile: str = "kodak_portra_400",
    print_profile: str = "kodak_portra_endura",
):
    params = init_params(film_profile=film_profile, print_profile=print_profile)
    params.debug.deactivate_spatial_effects = True
    params.debug.deactivate_stochastic_effects = True
    params.settings.use_enlarger_lut = False
    params.settings.use_scanner_lut = False
    params.io.upscale_factor = 1.0
    params.io.crop = False
    params.camera.auto_exposure = False
    params.camera.exposure_compensation_ev = 0.0
    params.io.output_gamut_compress = OutputGamutCompressSpec(algorithm="off")

    if case == "grain":
        params.debug.deactivate_stochastic_effects = False
        params.film_render.grain.active = True
        params.film_render.grain.sublayers_active = False
        params.film_render.grain.blur = 0.0
        params.print_render.glare.active = False
    elif case == "halation":
        params.debug.deactivate_spatial_effects = False
        params.film_render.halation.active = True
        params.film_render.halation.boost_ev = 0.5
        params.film_render.halation.halation_strength = (0.08, 0.03, 0.0)
    elif case == "diffusion":
        params.debug.deactivate_spatial_effects = False
        params.camera.diffusion_filter.active = True
        params.camera.diffusion_filter.strength = 0.5
        params.camera.diffusion_filter.spatial_scale = 0.8
    elif case == "scanner_blur_unsharp":
        params.debug.deactivate_spatial_effects = False
        params.scanner.lens_blur = 0.45
        params.scanner.unsharp_mask = (0.5, 0.6)
    elif case == "output_gamut_compression":
        params.io.output_gamut_compress = OutputGamutCompressSpec(algorithm="oklch")
    elif case == "linear_unclipped_output":
        params.io.output_cctf_encoding = False
        params.io.output_clip_min = False
        params.io.output_clip_max = False
    elif case == "cctf_clipped_output":
        params.io.output_cctf_encoding = True
        params.io.output_clip_min = True
        params.io.output_clip_max = True
    elif case != "baseline":
        raise ValueError(f"unknown equivalence case {case!r}")

    digested = digest_params(params)
    if case == "grain":
        digested.debug.deactivate_stochastic_effects = False
        digested.film_render.grain.active = True
        digested.film_render.grain.sublayers_active = False
        digested.film_render.grain.blur = 0.0
        digested.print_render.glare.active = False
    elif case == "halation":
        digested.debug.deactivate_spatial_effects = False
        digested.film_render.halation.active = True
        digested.film_render.halation.boost_ev = 0.5
        digested.film_render.halation.halation_strength = (0.08, 0.03, 0.0)
    elif case == "diffusion":
        digested.debug.deactivate_spatial_effects = False
        digested.camera.diffusion_filter.active = True
        digested.camera.diffusion_filter.strength = 0.5
        digested.camera.diffusion_filter.spatial_scale = 0.8
    elif case == "scanner_blur_unsharp":
        digested.debug.deactivate_spatial_effects = False
        digested.scanner.lens_blur = 0.45
        digested.scanner.unsharp_mask = (0.5, 0.6)
    elif case == "output_gamut_compression":
        digested.io.output_gamut_compress = OutputGamutCompressSpec(algorithm="oklch")
    elif case == "linear_unclipped_output":
        digested.io.output_cctf_encoding = False
        digested.io.output_clip_min = False
        digested.io.output_clip_max = False
    elif case == "cctf_clipped_output":
        digested.io.output_cctf_encoding = True
        digested.io.output_clip_min = True
        digested.io.output_clip_max = True
    return digested


def _small_hdr_patch(size: int = 6) -> np.ndarray:
    ramp = np.linspace(0.03, 1.5, size, dtype=np.float64)
    image = np.ones((size, size, 3), dtype=np.float64)
    image *= ramp[None, :, None]
    image[:, size // 2 :, 0] *= 1.15
    image[:, : size // 2, 2] *= 0.85
    return image


def _present_shaped_fields(master) -> set[str]:
    return {
        field
        for field in (
            "route_linear_rgb",
            "route_linear_xyz",
            "route_luminance_y",
            "sdr_legacy_rgb",
            "scene_y_raw",
            "post_halation_y",
            "density_cmy",
            "route_look_chroma",
            "material_detail_y",
        )
        if getattr(getattr(master, field), "shape", None) is not None
    }


def test_routemaster_minimal_fields_by_default() -> None:
    params = make_fast_test_params()
    image = _small_hdr_patch()

    master = Simulator(params).process_master(image, hdr_mode="paper")

    assert master.mode == "paper"
    assert master.route_kind == "print_scan"
    assert master.route_linear_rgb.shape == image.shape
    assert master.route_luminance_y.shape == image.shape[:2]
    assert master.sdr_legacy_rgb.shape == image.shape
    assert master.scene_y_raw.shape == image.shape[:2]
    assert master.post_halation_y.shape == image.shape[:2]
    assert master.route_linear_xyz is None
    assert master.density_cmy is None
    assert master.route_look_chroma is None
    assert master.material_detail_y is None
    assert isinstance(master.diagnostics, dict)
    for field in (
        master.route_linear_rgb,
        master.route_luminance_y,
        master.sdr_legacy_rgb,
        master.scene_y_raw,
        master.post_halation_y,
    ):
        assert np.all(np.isfinite(field))


def test_routemaster_sidecar_helpers_are_policy_scoped() -> None:
    params = make_fast_test_params()
    image = _small_hdr_patch()

    minimal = Simulator(copy.deepcopy(params)).process_master(image, hdr_mode="paper")
    full_params = copy.deepcopy(params)
    full_params.settings.hdr_route_sidecar_policy = "full"
    full = Simulator(full_params).process_master(image, hdr_mode="paper")

    assert route_master_sidecar_fields("minimal") == (
        "route_linear_rgb",
        "route_luminance_y",
        "sdr_legacy_rgb",
        "scene_y_raw",
        "post_halation_y",
    )
    assert set(name for name, _value in iter_route_master_sidecars(minimal, policy="minimal")) == set(
        route_master_sidecar_fields("minimal")
    )
    assert set(name for name, _value in iter_route_master_sidecars(full, policy="full")) == set(
        route_master_sidecar_fields("full")
    )
    assert route_master_sidecar_nbytes(minimal, policy="minimal") > 0
    assert route_master_sidecar_nbytes(full, policy="full") > route_master_sidecar_nbytes(minimal, policy="minimal")

    with pytest.raises(ValueError, match="hdr_route_sidecar_policy"):
        route_master_sidecar_fields("debug_everything")


def test_routemaster_full_sidecar_policy_restores_diagnostics() -> None:
    minimal_params = make_fast_test_params()
    full_params = copy.deepcopy(minimal_params)
    full_params.settings.hdr_route_sidecar_policy = "full"
    image = _small_hdr_patch()

    minimal = Simulator(copy.deepcopy(minimal_params)).process_master(image, hdr_mode="paper")
    full = Simulator(copy.deepcopy(full_params)).process_master(image, hdr_mode="paper")

    assert full.route_linear_rgb.shape == image.shape
    assert full.route_linear_xyz.shape == image.shape
    assert full.route_luminance_y.shape == image.shape[:2]
    assert full.sdr_legacy_rgb.shape == image.shape
    assert full.scene_y_raw.shape == image.shape[:2]
    assert full.post_halation_y.shape == image.shape[:2]
    assert full.density_cmy.shape == image.shape
    assert full.route_look_chroma.shape == image.shape
    assert full.material_detail_y.shape == image.shape[:2]
    assert _present_shaped_fields(minimal) < _present_shaped_fields(full)
    for field in (
        full.route_linear_rgb,
        full.route_linear_xyz,
        full.route_luminance_y,
        full.sdr_legacy_rgb,
        full.scene_y_raw,
        full.post_halation_y,
        full.density_cmy,
        full.route_look_chroma,
        full.material_detail_y,
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


@pytest.mark.parametrize(
    ("case", "film_profile", "hdr_mode", "scan_film"),
    [
        ("baseline", "kodak_portra_400", "paper", False),
        ("grain", "kodak_portra_400", "paper", False),
        ("halation", "kodak_portra_400", "paper", False),
        ("diffusion", "kodak_portra_400", "paper", False),
        ("scanner_blur_unsharp", "kodak_portra_400", "paper", False),
        ("output_gamut_compression", "kodak_portra_400", "paper", False),
        ("linear_unclipped_output", "kodak_portra_400", "paper", False),
        ("cctf_clipped_output", "kodak_portra_400", "paper", False),
        ("baseline", "fujifilm_provia_100f", "light_table", True),
        ("baseline", "kodak_gold_200", "paper", False),
    ],
)
def test_routemaster_sdr_strict_equivalence_matrix(
    case: str,
    film_profile: str,
    hdr_mode: str,
    scan_film: bool,
) -> None:
    params = make_equivalence_params(case=case, film_profile=film_profile)
    params.io.scan_film = scan_film
    image = _small_hdr_patch(size=7)
    legacy = Simulator(copy.deepcopy(params)).process(image)
    master = Simulator(copy.deepcopy(params)).process_master(image, hdr_mode=hdr_mode)  # type: ignore[arg-type]

    np.testing.assert_allclose(master.sdr_legacy_rgb, legacy, rtol=0.0, atol=1e-9)
    assert master.diagnostics["output_cctf_encoding"] is bool(params.io.output_cctf_encoding)
    assert master.diagnostics["output_clip_min"] is bool(params.io.output_clip_min)
    assert master.diagnostics["output_clip_max"] is bool(params.io.output_clip_max)


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
    params.settings.hdr_route_sidecar_policy = "full"
    image = _small_hdr_patch()

    master = Simulator(params).process_master(image, hdr_mode="paper")

    assert master.density_cmy.shape == master.sdr_legacy_rgb.shape
    assert np.all(np.isfinite(master.density_cmy))
