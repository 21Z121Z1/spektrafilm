import hashlib

import numpy as np
import pytest

from spektrafilm.gpu.backend import BackendUnavailableError, select_backend
from spektrafilm.gpu.kernels import grain as grain_kernels
from spektrafilm.model.density_curves import interp_density_cmy_layers
from spektrafilm.model.grain import apply_grain_to_density, apply_grain_to_density_layers, layer_particle_model
from spektrafilm.model.grain import apply_grain
from spektrafilm.runtime.params_schema import GrainParams


pytestmark = pytest.mark.unit


def _random_state_equal(left, right) -> bool:
    return (
        left[0] == right[0]
        and np.array_equal(left[1], right[1])
        and left[2:] == right[2:]
    )


def _mlx_backend_or_skip():
    try:
        return select_backend("mlx")
    except BackendUnavailableError as exc:
        pytest.skip(str(exc))


class TestApplyGrain:
    def test_mlx_poisson_all_normal_skips_unused_knuth_and_preserves_golden_bytes(self, monkeypatch):
        backend = _mlx_backend_or_skip()
        lam = backend.mx.full((7, 11), np.float32(12.5), dtype=backend.mx.float32)

        def fail_uniform(*_args, **_kwargs):
            raise AssertionError("all-normal Poisson path must not construct Knuth uniforms")

        monkeypatch.setattr(backend.mx.random, "uniform", fail_uniform)

        result = grain_kernels.fast_poisson_backend(
            lam,
            backend,
            seed=41,
            all_lam_above_threshold=True,
        )
        actual = backend.to_numpy(result)

        assert actual.dtype == np.int32
        assert hashlib.sha256(actual.tobytes()).hexdigest() == (
            "d17d64f16e8dea63c2289cd26a24158496b87c9b38318c05378c0f66ad00790c"
        )

    def test_mlx_poisson_mixed_and_threshold_values_keep_existing_golden_bytes(self):
        backend = _mlx_backend_or_skip()
        mixed = backend.asarray(np.array([[2.0, 12.5], [9.0, 20.0]], dtype=np.float32))
        edge = backend.asarray(np.array([[0.0, 1e-6, 10.0, 10.0001, 100.0]], dtype=np.float32))

        mixed_result = backend.to_numpy(grain_kernels.fast_poisson_backend(mixed, backend, seed=42))
        edge_result = backend.to_numpy(grain_kernels.fast_poisson_backend(edge, backend, seed=43))

        np.testing.assert_array_equal(mixed_result, np.array([[2, 18], [9, 18]], dtype=np.int32))
        np.testing.assert_array_equal(edge_result, np.array([[0, 0, 7, 4, 102]], dtype=np.int32))

    def test_mlx_poisson_unhinted_mixed_path_does_not_add_scalar_all_sync(self, monkeypatch):
        backend = _mlx_backend_or_skip()
        mixed = backend.asarray(np.array([[2.0, 12.5], [9.0, 20.0]], dtype=np.float32))

        def fail_all(*_args, **_kwargs):
            raise AssertionError("unhinted mixed path must retain the legacy graph without scalar sync")

        monkeypatch.setattr(backend.mx, "all", fail_all)

        result = grain_kernels.fast_poisson_backend(mixed, backend, seed=42)
        backend.eval(result)

    def test_layer_particle_model_passes_only_statically_proven_all_normal_hint(self, monkeypatch):
        backend = _mlx_backend_or_skip()
        captured: list[bool] = []
        captured_lambdas: list[np.ndarray] = []

        def fake_poisson(lam, _backend, *, seed=None, all_lam_above_threshold=False):
            del seed
            captured.append(bool(all_lam_above_threshold))
            captured_lambdas.append(backend.to_numpy(lam))
            return backend.mx.zeros(lam.shape, dtype=backend.mx.int32)

        monkeypatch.setattr(grain_kernels, "fast_poisson_backend", fake_poisson)
        density = backend.asarray(np.full((2, 2), 0.5, dtype=np.float32))

        layer_particle_model(
            density,
            n_particles_per_pixel=30.0,
            grain_uniformity=0.97,
            seed=1,
            backend=backend,
        )
        layer_particle_model(
            density,
            n_particles_per_pixel=5.0,
            grain_uniformity=0.97,
            seed=2,
            backend=backend,
        )
        layer_particle_model(
            density,
            n_particles_per_pixel=10.0000001,
            grain_uniformity=0.0,
            seed=3,
            backend=backend,
        )
        next_float32 = np.nextafter(np.float32(10.0), np.float32(np.inf))
        layer_particle_model(
            density,
            n_particles_per_pixel=next_float32,
            grain_uniformity=0.0,
            seed=4,
            backend=backend,
        )

        assert captured == [True, False, False, True]
        assert np.all(captured_lambdas[2] == np.float32(10.0))
        assert np.all(captured_lambdas[3] == next_float32)

    def test_mlx_poisson_float32_threshold_hint_matches_legacy_branch(self):
        backend = _mlx_backend_or_skip()
        rounded_to_threshold = backend.asarray(np.array([10.0000001], dtype=np.float32))
        next_float32 = np.nextafter(np.float32(10.0), np.float32(np.inf))
        above_threshold = backend.asarray(np.array([next_float32], dtype=np.float32))

        rounded_legacy = grain_kernels.fast_poisson_backend(rounded_to_threshold, backend, seed=41)
        rounded_current = grain_kernels.fast_poisson_backend(
            rounded_to_threshold,
            backend,
            seed=41,
            all_lam_above_threshold=False,
        )
        above_legacy = grain_kernels.fast_poisson_backend(above_threshold, backend, seed=42)
        above_current = grain_kernels.fast_poisson_backend(
            above_threshold,
            backend,
            seed=42,
            all_lam_above_threshold=True,
        )

        np.testing.assert_array_equal(backend.to_numpy(rounded_current), backend.to_numpy(rounded_legacy))
        np.testing.assert_array_equal(backend.to_numpy(above_current), backend.to_numpy(above_legacy))

    def test_layer_particle_model_seed_does_not_touch_global_rng_for_generator_path(self):
        density = np.full((2, 2), 0.5, dtype=np.float64)
        np.random.seed(12345)
        before = np.random.get_state()

        layer_particle_model(density, seed=7, use_fast_stats=False)

        after = np.random.get_state()
        assert _random_state_equal(after, before)

    def test_layer_particle_model_generator_path_uses_local_rng_for_seed(self, monkeypatch):
        density = np.full((2, 2), 0.5, dtype=np.float64)

        def fail_global_seed(_seed):
            raise AssertionError("layer_particle_model must not seed NumPy global RNG")

        monkeypatch.setattr(np.random, "seed", fail_global_seed)

        result = layer_particle_model(density, seed=7, use_fast_stats=False)

        assert result.shape == density.shape
        assert np.isfinite(result).all()

    def test_layer_particle_model_fast_stats_restores_global_rng_state(self):
        density = np.full((2, 2), 0.5, dtype=np.float64)
        np.random.seed(54321)
        before = np.random.get_state()

        layer_particle_model(density, seed=7, use_fast_stats=True)

        after = np.random.get_state()
        assert _random_state_equal(after, before)

    def test_layer_particle_model_rejects_unknown_method(self):
        density = np.full((2, 2), 0.5, dtype=np.float64)

        with pytest.raises(ValueError, match="Unsupported grain particle method"):
            layer_particle_model(density, method="unknown")

    def test_layer_particle_model_mlx_falls_back_for_gamma_beta(self):
        backend = _mlx_backend_or_skip()
        density = np.full((4, 4), 0.5, dtype=np.float32)

        expected = layer_particle_model(
            density,
            method="gamma_beta",
            seed=7,
            blur_particle=0.0,
        )
        actual = layer_particle_model(
            backend.asarray(density),
            method="gamma_beta",
            seed=7,
            blur_particle=0.0,
            backend=backend,
        )

        np.testing.assert_allclose(actual, expected, atol=0.0)

    def test_layer_particle_model_mlx_poisson_binomial_stays_backend_resident(self, monkeypatch):
        backend = _mlx_backend_or_skip()
        density = np.linspace(0.1, 1.6, 16 * 16, dtype=np.float32).reshape(16, 16)

        def fail_to_numpy(_value):
            raise AssertionError("unexpected MLX to NumPy transfer")

        monkeypatch.setattr(backend, "to_numpy", fail_to_numpy)

        actual = layer_particle_model(
            backend.asarray(density),
            density_max=2.4,
            n_particles_per_pixel=30,
            grain_uniformity=0.97,
            seed=123,
            blur_particle=0.0,
            backend=backend,
        )

        assert backend._is_mlx_array(actual)
        backend.eval(actual)

    def test_grain_function_defaults_are_not_mutable_lists(self):
        assert not any(isinstance(default, list) for default in apply_grain_to_density.__defaults__)
        assert not any(isinstance(default, list) for default in apply_grain_to_density_layers.__defaults__)

    def test_apply_grain_fixed_seed_is_usable(self):
        density_cmy = np.full((2, 2, 3), 0.4, dtype=np.float64)

        result = apply_grain_to_density(density_cmy.copy(), grain_blur=0.0, fixed_seed=42)

        assert result.shape == density_cmy.shape
        assert np.isfinite(result).all()

    def test_apply_grain_to_density_does_not_mutate_input(self):
        density_cmy = np.full((2, 2, 3), 0.4, dtype=np.float64)
        original = density_cmy.copy()

        apply_grain_to_density(density_cmy, grain_blur=0.0, fixed_seed=42)

        np.testing.assert_allclose(density_cmy, original)

    def test_layered_grain_falls_back_for_non_mlx_gpu_backend(self):
        class HalideLikeBackend:
            supports_gpu = True
            name = "halide"

        density_cmy_layers = np.full((2, 2, 3, 3), 0.2, dtype=np.float64)
        density_max_layers = np.full((3, 3), 1.0, dtype=np.float64)

        result = apply_grain_to_density_layers(
            density_cmy_layers,
            density_max_layers=density_max_layers,
            grain_blur=0.0,
            grain_blur_dye_clouds_um=0.0,
            grain_micro_structure=(0.0, 0.0),
            fixed_seed=42,
            backend=HalideLikeBackend(),
        )

        assert result.shape == density_cmy_layers.shape[:2] + (3,)
        assert np.isfinite(result).all()

    def test_apply_grain_to_density_mlx_does_not_materialize_when_available(self, monkeypatch):
        backend = _mlx_backend_or_skip()
        density_cmy = backend.asarray(np.full((8, 8, 3), 0.35, dtype=np.float32))

        def fail_to_numpy(_value):
            raise AssertionError("unexpected MLX to NumPy transfer")

        monkeypatch.setattr(backend, "to_numpy", fail_to_numpy)

        result = apply_grain_to_density(
            density_cmy,
            pixel_size_um=5.0,
            grain_blur=0.0,
            fixed_seed=42,
            backend=backend,
        )
        backend.eval(result)

        assert backend._is_mlx_array(result)

    def test_apply_grain_to_density_mlx_is_statistically_plausible_fixed_seed(self):
        backend = _mlx_backend_or_skip()
        density_cmy = np.linspace(0.05, 1.2, 16 * 16 * 3, dtype=np.float32).reshape(16, 16, 3)
        kwargs = dict(
            pixel_size_um=5.0,
            agx_particle_area_um2=0.25,
            agx_particle_scale=(0.9, 1.1, 1.3),
            density_min=(0.04, 0.05, 0.06),
            density_max_curves=(2.0, 2.2, 2.4),
            grain_uniformity=(0.98, 0.97, 0.96),
            grain_blur=0.0,
            n_sub_layers=2,
            fixed_seed=42,
        )

        actual = apply_grain_to_density(backend.asarray(density_cmy), backend=backend, **kwargs)
        actual_np = backend.to_numpy(actual)

        assert backend._is_mlx_array(actual)
        assert actual_np.shape == density_cmy.shape
        assert np.isfinite(actual_np).all()
        np.testing.assert_allclose(
            actual_np.mean(axis=(0, 1)),
            density_cmy.mean(axis=(0, 1)),
            atol=0.35,
        )

    def test_apply_grain_to_density_mlx_is_deterministic_for_fixed_seed(self):
        backend = _mlx_backend_or_skip()
        density_cmy = np.full((16, 16, 3), 0.35, dtype=np.float32)

        first = apply_grain_to_density(
            backend.asarray(density_cmy),
            pixel_size_um=5.0,
            grain_blur=0.0,
            fixed_seed=42,
            backend=backend,
        )
        second = apply_grain_to_density(
            backend.asarray(density_cmy),
            pixel_size_um=5.0,
            grain_blur=0.0,
            fixed_seed=42,
            backend=backend,
        )

        np.testing.assert_allclose(backend.to_numpy(first), backend.to_numpy(second), atol=0.0)

    def test_apply_grain_to_density_mlx_statistics_are_plausible(self):
        backend = _mlx_backend_or_skip()
        density_cmy = np.full((64, 64, 3), 0.35, dtype=np.float32)

        result = apply_grain_to_density(
            backend.asarray(density_cmy),
            pixel_size_um=5.0,
            grain_blur=0.0,
            fixed_seed=42,
            backend=backend,
        )
        result_np = backend.to_numpy(result)

        assert result_np.shape == density_cmy.shape
        assert np.isfinite(result_np).all()
        np.testing.assert_allclose(result_np.mean(axis=(0, 1)), density_cmy.mean(axis=(0, 1)), atol=0.25)

    def test_apply_grain_layered_mlx_uses_backend_layer_interpolation(self, monkeypatch):
        backend = _mlx_backend_or_skip()

        def fail_cpu_layer_interpolation(*_args, **_kwargs):
            raise AssertionError("unexpected CPU density layer interpolation")

        monkeypatch.setattr(
            "spektrafilm.model.grain.interp_density_cmy_layers",
            fail_cpu_layer_interpolation,
        )

        density_cmy = backend.asarray(np.full((8, 8, 3), [0.35, 0.55, 0.75], dtype=np.float32))
        density_curves = np.column_stack([
            np.linspace(0.0, 2.1, 10),
            np.linspace(0.0, 1.9, 10),
            np.linspace(0.0, 1.7, 10),
        ]).astype(np.float32)
        density_curves_layers = np.stack([
            density_curves * np.array([0.55, 0.50, 0.45], dtype=np.float32),
            density_curves * np.array([0.30, 0.33, 0.35], dtype=np.float32),
            density_curves * np.array([0.15, 0.17, 0.20], dtype=np.float32),
        ], axis=1)
        grain = GrainParams(
            active=True,
            sublayers_active=True,
            agx_particle_area_um2=0.18,
            agx_particle_scale=(0.8, 1.0, 1.2),
            agx_particle_scale_layers=(2.2, 1.0, 0.5),
            density_min=(0.04, 0.06, 0.08),
            uniformity=(0.99, 0.98, 0.97),
            blur=0.0,
            blur_dye_clouds_um=0.0,
            micro_structure=(0.0, 0.0),
        )

        result = apply_grain(
            density_cmy,
            4.0,
            grain,
            density_curves,
            density_curves_layers,
            "negative",
            backend=backend,
        )
        backend.eval(result)

        assert backend._is_mlx_array(result)

    def test_apply_grain_with_blur_differs_from_no_blur(self):
        density_cmy = np.full((8, 8, 3), 0.4, dtype=np.float64)

        no_blur = apply_grain_to_density(
            density_cmy.copy(), grain_blur=0.0, fixed_seed=42,
        )
        blurred = apply_grain_to_density(
            density_cmy.copy(), grain_blur=0.65, fixed_seed=42,
        )

        assert blurred.shape == density_cmy.shape
        assert np.isfinite(blurred).all()
        assert not np.allclose(no_blur, blurred)

    def test_apply_grain_returns_input_when_bypassed_or_inactive(self):
        density_cmy = np.full((3, 3, 3), 0.4)
        density_curves = np.tile(np.linspace(0.0, 2.0, 8)[:, None], (1, 3))
        density_curves_layers = np.tile(density_curves[:, None, :] / 3.0, (1, 3, 1))
        grain = GrainParams(active=False)

        inactive = apply_grain(
            density_cmy.copy(),
            4.0,
            grain,
            density_curves,
            density_curves_layers,
            "negative",
        )
        bypassed = apply_grain(
            density_cmy.copy(),
            4.0,
            GrainParams(active=True),
            density_curves,
            density_curves_layers,
            "negative",
            bypass_grain=True,
        )

        np.testing.assert_allclose(inactive, density_cmy, atol=1e-10)
        np.testing.assert_allclose(bypassed, density_cmy, atol=1e-10)

    def test_apply_grain_matches_single_layer_pipeline(self):
        density_cmy = np.full((4, 4, 3), [0.3, 0.6, 0.9], dtype=np.float64)
        density_curves = np.column_stack([
            np.linspace(0.0, 2.4, 12),
            np.linspace(0.0, 2.2, 12),
            np.linspace(0.0, 2.0, 12),
        ])
        density_curves_layers = np.tile(density_curves[:, None, :] / 3.0, (1, 3, 1))
        grain = GrainParams(
            active=True,
            sublayers_active=False,
            agx_particle_area_um2=0.25,
            agx_particle_scale=(0.9, 1.1, 1.4),
            density_min=(0.05, 0.07, 0.09),
            uniformity=(0.98, 0.97, 0.96),
            blur=0.0,
            n_sub_layers=2,
        )

        result = apply_grain(
            density_cmy.copy(),
            5.0,
            grain,
            density_curves,
            density_curves_layers,
            "negative",
        )

        expected = apply_grain_to_density(
            density_cmy.copy(),
            pixel_size_um=5.0,
            agx_particle_area_um2=grain.agx_particle_area_um2,
            agx_particle_scale=grain.agx_particle_scale,
            density_min=grain.density_min,
            density_max_curves=np.nanmax(density_curves, axis=0),
            grain_uniformity=grain.uniformity,
            grain_blur=grain.blur,
            n_sub_layers=grain.n_sub_layers,
        )

        np.testing.assert_allclose(result, expected, atol=1e-10)

    @pytest.mark.parametrize("n_sub_layers", [0, -1])
    def test_apply_grain_to_density_rejects_invalid_sub_layers(self, n_sub_layers):
        density_cmy = np.full((4, 4, 3), 0.4, dtype=np.float64)

        with pytest.raises(ValueError, match="n_sub_layers must be >= 1"):
            apply_grain_to_density(
                density_cmy.copy(),
                grain_blur=0.0,
                fixed_seed=42,
                n_sub_layers=n_sub_layers,
            )

    @pytest.mark.parametrize("profile_type", ["negative", "positive"])
    def test_apply_grain_matches_layered_pipeline(self, profile_type):
        density_cmy = np.full((4, 4, 3), [0.35, 0.55, 0.75], dtype=np.float64)
        density_curves = np.column_stack([
            np.linspace(0.0, 2.1, 10),
            np.linspace(0.0, 1.9, 10),
            np.linspace(0.0, 1.7, 10),
        ])
        density_curves_layers = np.stack([
            density_curves * np.array([0.55, 0.50, 0.45]),
            density_curves * np.array([0.30, 0.33, 0.35]),
            density_curves * np.array([0.15, 0.17, 0.20]),
        ], axis=1)
        grain = GrainParams(
            active=True,
            sublayers_active=True,
            agx_particle_area_um2=0.18,
            agx_particle_scale=(0.8, 1.0, 1.2),
            agx_particle_scale_layers=(2.2, 1.0, 0.5),
            density_min=(0.04, 0.06, 0.08),
            uniformity=(0.99, 0.98, 0.97),
            blur=0.0,
            blur_dye_clouds_um=0.0,
            micro_structure=(0.0, 0.0),
        )

        result = apply_grain(
            density_cmy.copy(),
            4.0,
            grain,
            density_curves,
            density_curves_layers,
            profile_type,
            use_fast_stats=False,
        )

        density_cmy_layers = interp_density_cmy_layers(
            density_cmy.copy(),
            density_curves,
            density_curves_layers,
            positive_film=profile_type == "positive",
        )
        expected = apply_grain_to_density_layers(
            density_cmy_layers,
            density_max_layers=np.nanmax(density_curves_layers, axis=0),
            pixel_size_um=4.0,
            agx_particle_area_um2=grain.agx_particle_area_um2,
            agx_particle_scale=grain.agx_particle_scale,
            agx_particle_scale_layers=grain.agx_particle_scale_layers,
            density_min=grain.density_min,
            grain_uniformity=grain.uniformity,
            grain_blur=grain.blur,
            grain_blur_dye_clouds_um=grain.blur_dye_clouds_um,
            grain_micro_structure=grain.micro_structure,
            use_fast_stats=False,
        )

        np.testing.assert_allclose(result, expected, atol=1e-10)
