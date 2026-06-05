from __future__ import annotations

import copy

from spektrafilm.hdr.profile_cache import build_route_profile_cache_key
from spektrafilm.runtime.params_builder import digest_params, init_params


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


def test_dynamic_profile_cache_key_changes_for_tone_params() -> None:
    base = make_fast_test_params()
    changed = copy.deepcopy(base)
    changed.camera.exposure_compensation_ev = 0.5
    assert build_route_profile_cache_key(base, hdr_mode="paper") != build_route_profile_cache_key(changed, hdr_mode="paper")

    changed = copy.deepcopy(base)
    changed.film_render.density_curve_gamma = 1.2
    assert build_route_profile_cache_key(base, hdr_mode="paper") != build_route_profile_cache_key(changed, hdr_mode="paper")

    changed = copy.deepcopy(base)
    changed.enlarger.print_exposure = 1.4
    assert build_route_profile_cache_key(base, hdr_mode="paper") != build_route_profile_cache_key(changed, hdr_mode="paper")

    changed = make_fast_test_params(print_profile="fujifilm_crystal_archive_typeii")
    assert build_route_profile_cache_key(base, hdr_mode="paper") != build_route_profile_cache_key(changed, hdr_mode="paper")


def test_dynamic_profile_cache_key_ignores_spatial_random_params() -> None:
    base = make_fast_test_params()
    changed = copy.deepcopy(base)
    changed.film_render.grain.active = not changed.film_render.grain.active
    changed.film_render.grain.agx_particle_area_um2 = 9.0
    changed.camera.lens_blur_um = 22.0
    changed.camera.diffusion_filter.active = True
    changed.camera.diffusion_filter.strength = 1.0
    changed.scanner.lens_blur = 4.0
    changed.scanner.unsharp_mask = (3.0, 2.0)
    changed.print_render.glare.percent = 0.9

    assert build_route_profile_cache_key(base, hdr_mode="paper") == build_route_profile_cache_key(changed, hdr_mode="paper")


def test_dynamic_profile_cache_key_ignores_paper_tone_params_for_light_table() -> None:
    base = make_fast_test_params(print_profile="kodak_portra_endura")
    changed = make_fast_test_params(print_profile="fujifilm_crystal_archive_typeii")
    changed.enlarger.print_exposure = 3.0
    changed.enlarger.y_filter_neutral = 5.0
    changed.enlarger.m_filter_neutral = 120.0
    changed.enlarger.preflash_exposure = 0.5

    assert build_route_profile_cache_key(base, hdr_mode="light_table") == build_route_profile_cache_key(
        changed,
        hdr_mode="light_table",
    )
