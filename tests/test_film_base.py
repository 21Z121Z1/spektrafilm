from copy import deepcopy

import numpy as np

from spektrafilm.config import SPECTRAL_SHAPE
from spektrafilm.model.develop import (
    base_film_density_tuning,
    compute_density_spectral,
)
from spektrafilm.runtime.params_schema import FilmBaseParams
from spektrafilm.runtime.process import simulate


def _base_density():
    wavelengths = np.asarray(SPECTRAL_SHAPE.wavelengths, dtype=np.float64)
    return 0.12 + 0.08 * (wavelengths - wavelengths.min()) / np.ptp(wavelengths)


def _deterministic_cpu_params(default_params):
    params = deepcopy(default_params)
    params.settings.compute_backend = "cpu"
    params.debug.lut_mode = True
    params.camera.auto_exposure = False
    return params


def test_film_base_neutral_defaults_are_exact_identity():
    base = _base_density()
    tuned = base_film_density_tuning(base, FilmBaseParams())
    np.testing.assert_array_equal(tuned, base)


def test_disabled_film_base_is_identity_even_with_non_neutral_controls():
    base = _base_density()
    params = FilmBaseParams(
        active=False,
        scale=1.7,
        tilt=0.2,
        cyan=1.3,
        magenta=0.8,
        yellow=1.1,
    )
    tuned = base_film_density_tuning(base, params)
    np.testing.assert_array_equal(tuned, base)


def test_film_base_global_scale_is_applied_exactly_once_with_shape_tuning():
    base = _base_density()
    shaped = base_film_density_tuning(
        base,
        FilmBaseParams(
            active=True,
            scale=1.0,
            tilt=0.12,
            cyan=1.25,
            magenta=0.9,
            yellow=1.08,
        ),
    )
    scaled = base_film_density_tuning(
        base,
        FilmBaseParams(
            active=True,
            scale=1.6,
            tilt=0.12,
            cyan=1.25,
            magenta=0.9,
            yellow=1.08,
        ),
    )
    np.testing.assert_allclose(scaled, shaped * 1.6, rtol=0.0, atol=1e-14)


def test_compute_density_spectral_adds_tuned_film_base_once():
    base = _base_density()
    params = FilmBaseParams(
        active=True,
        scale=1.2,
        tilt=-0.08,
        cyan=0.95,
        magenta=1.1,
        yellow=1.2,
    )
    channel_density = np.zeros((base.size, 3), dtype=np.float64)
    density_cmy = np.zeros((2, 3, 3), dtype=np.float64)

    actual = compute_density_spectral(
        channel_density,
        density_cmy,
        base_density=base,
        base_density_params=params,
        is_film=True,
    )
    expected = base_film_density_tuning(base, params)

    assert actual.shape == (2, 3, base.size)
    expected_full = np.broadcast_to(expected, actual.shape)
    np.testing.assert_allclose(actual, expected_full, rtol=0.0, atol=1e-14)
    assert np.isfinite(actual).all()
    assert (actual >= 0.0).all()


def test_neutral_film_base_is_end_to_end_identical_to_disabled(default_params, small_rgb_image):
    disabled = _deterministic_cpu_params(default_params)
    disabled.film_render.base = FilmBaseParams(active=False)
    output_disabled = simulate(
        small_rgb_image,
        disabled,
        digest_params_first=False,
    )

    neutral = _deterministic_cpu_params(default_params)
    neutral.film_render.base = FilmBaseParams()
    output_neutral = simulate(
        small_rgb_image,
        neutral,
        digest_params_first=False,
    )

    np.testing.assert_array_equal(output_neutral, output_disabled)


def test_non_neutral_film_base_changes_end_to_end_cpu_output(default_params, small_rgb_image):
    baseline = _deterministic_cpu_params(default_params)
    baseline.film_render.base = FilmBaseParams()
    output_baseline = simulate(
        small_rgb_image,
        baseline,
        digest_params_first=False,
    )

    tuned = _deterministic_cpu_params(default_params)
    tuned.film_render.base = FilmBaseParams(
        active=True,
        scale=1.08,
        tilt=0.08,
        cyan=1.12,
        magenta=0.96,
        yellow=1.06,
    )
    output_tuned = simulate(
        small_rgb_image,
        tuned,
        digest_params_first=False,
    )

    assert output_tuned.shape == output_baseline.shape
    assert np.isfinite(output_tuned).all()
    assert not np.array_equal(output_tuned, output_baseline)
