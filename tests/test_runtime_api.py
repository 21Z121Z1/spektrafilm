from contextlib import contextmanager
from types import SimpleNamespace
import copy

import numpy as np
import pytest

from spektrafilm import AgXPhoto, Simulator, photo_params, simulate
from spektrafilm.model.stocks import FilmStocks, PrintPapers
from spektrafilm.runtime import pipeline as pipeline_module
from spektrafilm.runtime import process as process_module


pytestmark = pytest.mark.integration


class TestRuntimeApi:
    def test_simulate_matches_simulator_process(self, small_rgb_image, default_params):
        new_result = simulate(small_rgb_image, default_params)
        direct_result = Simulator(default_params).process(small_rgb_image)

        np.testing.assert_allclose(new_result, direct_result, atol=1e-12)

    def test_simulator_process_with_metadata_preserves_process_array_api(self, monkeypatch):
        rendered = np.full((1, 2, 3), 0.25, dtype=np.float32)
        scene_luminance = np.array([[0.5, 3.0]], dtype=np.float32)
        metadata = pipeline_module.HDRSceneEnergyMetadata(
            scene_luminance=scene_luminance,
            diffuse_white_estimate=0.5,
            headroom_estimate=6.0,
            auto_exposure_ev=1.0,
            method='auto_percentile',
            confidence='medium',
        )

        class FakePipeline:
            def __init__(self, _params):
                self._array_backend = SimpleNamespace(requires_serial_runtime=False)

            def process(self, image):
                assert image == 'frame'
                return rendered

            def process_with_metadata(self, image):
                assert image == 'frame'
                return pipeline_module.SimulationPipelineResult(
                    image=rendered,
                    hdr_scene_energy=metadata,
                )

        monkeypatch.setattr(process_module, 'SimulationPipeline', FakePipeline)
        params = SimpleNamespace(
            settings=SimpleNamespace(compute_backend='cpu', float_precision='float32'),
        )

        simulator = process_module.Simulator(params)

        np.testing.assert_allclose(simulator.process('frame'), rendered)
        result = simulator.process_with_metadata('frame')
        np.testing.assert_allclose(result.image, rendered)
        assert result.hdr_scene_energy is metadata

    def test_pipeline_process_with_metadata_uses_auto_exposed_scene_luminance(self, monkeypatch):
        pipeline = object.__new__(pipeline_module.SimulationPipeline)
        pipeline.timings = {}
        pipeline._last_elapsed_time = None
        pipeline._runtime_dtype = np.dtype(np.float32)
        pipeline._array_backend = SimpleNamespace(
            supports_gpu=False,
            to_numpy=lambda value: value,
        )
        pipeline.debug = SimpleNamespace(debug_mode='off')
        pipeline.io = SimpleNamespace(input_color_space='sRGB', input_cctf_decoding=False)

        auto_exposed = np.full((1, 100, 3), 0.5, dtype=np.float32)
        auto_exposed[0, -1, :] = 4.0
        pipeline._filming_stage = SimpleNamespace(
            auto_exposure_with_ev=lambda image: (auto_exposed, 2.0),
        )
        pipeline._resize_service = SimpleNamespace(crop_and_rescale=lambda image: image)
        monkeypatch.setattr(pipeline, '_process_runtime_array', lambda image: image * 0.25)
        monkeypatch.setattr(pipeline, '_runtime_array', lambda image: image)

        result = pipeline_module.SimulationPipeline.process_with_metadata(
            pipeline,
            np.full((1, 100, 3), 0.125, dtype=np.float32),
        )

        np.testing.assert_allclose(result.image, auto_exposed * 0.25)
        assert result.hdr_scene_energy.auto_exposure_ev == pytest.approx(2.0)
        assert result.hdr_scene_energy.headroom_estimate > 1.0
        assert result.hdr_scene_energy.scene_luminance.shape == (1, 100)
        assert float(result.hdr_scene_energy.scene_luminance[0, -1]) > 1.0

    def test_hdr_scene_energy_sidecar_tracks_auto_exposure_ev_direction(self):
        post_auto = np.full((2, 2, 3), 0.25, dtype=np.float32)

        baseline = pipeline_module._hdr_scene_energy_metadata(
            post_auto,
            input_color_space='sRGB',
            apply_cctf_decoding=False,
            auto_exposure_ev=0.0,
        )
        lifted = pipeline_module._hdr_scene_energy_metadata(
            post_auto,
            input_color_space='sRGB',
            apply_cctf_decoding=False,
            auto_exposure_ev=1.0,
        )

        assert float(np.median(lifted.scene_luminance)) > float(np.median(baseline.scene_luminance))

    def test_runtime_float_precision_controls_cpu_output_dtype(self, small_rgb_image, default_params):
        params = copy.deepcopy(default_params)
        params.settings.compute_backend = 'cpu'
        params.settings.float_precision = 'float64'

        result = Simulator(params).process(small_rgb_image)

        assert result.dtype == np.float64

    @pytest.mark.parametrize("backend_name", ["mlx", "cupy", "cuda", "halide"])
    def test_float64_runtime_precision_rejects_explicit_gpu_backend(self, default_params, backend_name):
        params = copy.deepcopy(default_params)
        params.settings.compute_backend = backend_name
        params.settings.float_precision = 'float64'

        with pytest.raises(ValueError, match='float64 runtime precision'):
            Simulator(params)

    def test_update_params_delegates_to_pipeline_without_public_state(self, monkeypatch):
        class FakePipeline:
            def __init__(self, params):
                self.label = params.label
                self.timings = {'label': params.label}

            def process(self, image):
                return f'processed-{self.label}-{image}'

            def update(self, params):
                self.label = params.label
                self.timings = {'label': params.label}

        monkeypatch.setattr(process_module, 'SimulationPipeline', FakePipeline)
        initial_params = SimpleNamespace(label='initial')
        updated_params = SimpleNamespace(label='updated')

        simulator = process_module.Simulator(initial_params)
        assert not hasattr(simulator, 'camera')
        assert not hasattr(simulator, 'timings')
        assert not hasattr(simulator, 'update')

        simulator.update_params(updated_params)

        assert simulator.process('frame') == 'processed-updated-frame'

    def test_gpu_process_is_serialized_until_backend_synchronizes(self, monkeypatch):
        events: list[str] = []

        @contextmanager
        def fake_serialized_metal_runtime():
            events.append('lock-enter')
            try:
                yield
            finally:
                events.append('lock-exit')

        class FakeBackend:
            supports_gpu = True
            requires_serial_runtime = True

            def synchronize(self):
                events.append('sync')

        class FakePipeline:
            def __init__(self, _params):
                self._array_backend = FakeBackend()

            def process(self, image):
                events.append('process')
                return f'processed-{image}'

        monkeypatch.setattr(process_module, 'serialized_metal_runtime', fake_serialized_metal_runtime)
        monkeypatch.setattr(process_module, 'SimulationPipeline', FakePipeline)
        params = SimpleNamespace(
            settings=SimpleNamespace(compute_backend='cpu', float_precision='float32'),
        )

        simulator = process_module.Simulator(params)
        result = simulator.process('frame')

        assert result == 'processed-frame'
        assert events == ['lock-enter', 'process', 'sync', 'lock-exit']

    def test_non_serial_gpu_process_does_not_use_metal_lock(self, monkeypatch):
        events: list[str] = []

        @contextmanager
        def fake_serialized_metal_runtime():
            raise AssertionError('non-Metal GPU backends should not use the Metal runtime lock')

        class FakeBackend:
            supports_gpu = True
            requires_serial_runtime = False

            def synchronize(self):
                events.append('sync')

        class FakePipeline:
            def __init__(self, _params):
                self._array_backend = FakeBackend()

            def process(self, image):
                events.append('process')
                return f'processed-{image}'

        monkeypatch.setattr(process_module, 'serialized_metal_runtime', fake_serialized_metal_runtime)
        monkeypatch.setattr(process_module, 'SimulationPipeline', FakePipeline)
        params = SimpleNamespace(
            settings=SimpleNamespace(compute_backend='cupy', float_precision='float32'),
        )

        simulator = process_module.Simulator(params)
        result = simulator.process('frame')

        assert result == 'processed-frame'
        assert events == ['process']

    def test_mlx_pipeline_tiles_large_images_on_gpu(self, monkeypatch):
        pipeline = object.__new__(pipeline_module.SimulationPipeline)
        pipeline.timings = {}
        pipeline._last_elapsed_time = None
        captured: dict[str, object] = {}

        def fake_synchronize():
            captured['syncs'] = int(captured.get('syncs', 0)) + 1

        pipeline._array_backend = SimpleNamespace(
            supports_gpu=True,
            to_numpy=lambda value: value,
            synchronize=fake_synchronize,
        )
        pipeline._runtime_dtype = np.dtype(np.float32)
        pipeline.debug = SimpleNamespace(debug_mode='off')
        image = np.arange(45, dtype=np.float32).reshape(5, 3, 3)

        def fake_process_tile(tile):
            captured.setdefault('tile_shapes', []).append(tile.shape)
            return tile + 1.0

        monkeypatch.setenv(pipeline_module.MLX_TILE_PIXELS_ENV, '6')
        monkeypatch.setattr(pipeline, '_tile_overlap_pixels', lambda: 0)
        monkeypatch.setattr(pipeline, '_preprocess_input_image', lambda frame: frame)
        monkeypatch.setattr(pipeline, '_runtime_array', lambda frame: frame)
        monkeypatch.setattr(
            pipeline,
            '_process_runtime_array',
            fake_process_tile,
        )
        monkeypatch.setattr(
            pipeline,
            '_pipeline',
            lambda _frame: (_ for _ in ()).throw(AssertionError('GPU path should not run')),
        )

        result = pipeline_module.SimulationPipeline.process(pipeline, image)

        assert captured['tile_shapes'] == [(2, 3, 3), (2, 3, 3), (1, 3, 3)]
        assert captured['syncs'] == 3
        np.testing.assert_allclose(result, image + 1.0)
        assert result.dtype == np.float32

    @pytest.mark.parametrize(
        ('grain_active', 'glare_active'),
        [
            (True, False),
            (False, True),
        ],
        ids=['grain', 'glare'],
    )
    def test_mlx_tiling_is_disabled_for_stochastic_effects(self, monkeypatch, grain_active, glare_active):
        pipeline = object.__new__(pipeline_module.SimulationPipeline)
        pipeline.timings = {}
        pipeline._last_elapsed_time = None
        pipeline._array_backend = SimpleNamespace(
            supports_gpu=True,
            to_numpy=lambda value: value,
            synchronize=lambda: None,
        )
        pipeline._runtime_dtype = np.dtype(np.float32)
        pipeline.debug = SimpleNamespace(debug_mode='off')
        pipeline.film_render = SimpleNamespace(grain=SimpleNamespace(active=grain_active))
        pipeline.print_render = SimpleNamespace(glare=SimpleNamespace(active=glare_active))
        image = np.arange(45, dtype=np.float32).reshape(5, 3, 3)

        monkeypatch.setenv(pipeline_module.MLX_TILE_PIXELS_ENV, '6')
        monkeypatch.setattr(
            pipeline,
            '_process_with_gpu_tiles',
            lambda _frame: (_ for _ in ()).throw(AssertionError('tiled GPU path should be disabled')),
        )
        monkeypatch.setattr(pipeline, '_pipeline', lambda frame: frame + 1.0)

        result = pipeline_module.SimulationPipeline.process(pipeline, image)

        np.testing.assert_allclose(result, image + 1.0)
        assert result.dtype == np.float32

    def test_soft_update_delegates_to_pipeline(self, monkeypatch):
        captured_kwargs = {}

        class FakePipeline:
            def __init__(self, params):
                self.label = params.label
                self.timings = {'label': params.label}

            def process(self, image):
                return image

            def soft_update(self, **kwargs):
                captured_kwargs.update(kwargs)

        monkeypatch.setattr(process_module, 'SimulationPipeline', FakePipeline)
        simulator = process_module.Simulator(SimpleNamespace(label='initial'))

        simulator.soft_update(print_exposure=1.5, exposure_compensation_ev=-0.25)

        assert captured_kwargs == {
            'print_exposure': 1.5,
            'exposure_compensation_ev': -0.25,
        }

    def test_soft_update_keeps_print_exposure_compensation_consistent_with_rebuild(self, default_params):
        params = copy.deepcopy(default_params)
        params.camera.auto_exposure = False
        params.enlarger.normalize_print_exposure = True
        params.enlarger.print_exposure_compensation = True

        image = np.array([[[0.184, 0.184, 0.184]]], dtype=np.float64)
        simulator = process_module.Simulator(copy.deepcopy(params))

        for exposure_compensation_ev in (-2.0, -1.0, 0.0, 1.0, 2.0):
            simulator.soft_update(exposure_compensation_ev=exposure_compensation_ev)
            soft_updated = simulator.process(image)

            rebuilt_params = copy.deepcopy(params)
            rebuilt_params.camera.exposure_compensation_ev = exposure_compensation_ev
            rebuilt = process_module.Simulator(rebuilt_params).process(image)

            np.testing.assert_allclose(soft_updated, rebuilt, atol=1e-12)

    def test_simulate_prints_pipeline_timings(self, monkeypatch, capsys):
        class FakePipeline:
            def __init__(self, params):
                del params
                self.timings = {'previous': 1.0}
                self._last_elapsed_time = None

            def process(self, image):
                self.timings.clear()
                start = pipeline_module.perf_counter()
                try:
                    self.timings['FilmingStage.expose'] = 0.012345
                    self.timings['ScanningStage.scan'] = 0.0004567
                    return image
                finally:
                    self._last_elapsed_time = pipeline_module.perf_counter() - start

            def get_timings(self):
                return self.timings

            def get_total_elapsed_time(self):
                return self._last_elapsed_time

            def format_timings(self):
                return pipeline_module.format_timings(
                    self.get_timings(),
                    total_elapsed_time=self.get_total_elapsed_time(),
                )

            def print_timings(self):
                print(self.format_timings())

        monkeypatch.setattr(process_module, 'SimulationPipeline', FakePipeline)
        ticks = iter((10.0, 10.1234))
        monkeypatch.setattr(pipeline_module, 'perf_counter', lambda: next(ticks))

        params = SimpleNamespace(label='timed')

        result = process_module.simulate('frame', params, digest_params_first=False, print_timings=True)

        assert result == 'frame'
        assert capsys.readouterr().out.strip() == (
            "Simulation timings\n"
            "  Total                 123 ms  100.0%\n"
            "  -------------------  -------  ------\n"
            "  FilmingStage.expose  \033[31m12.3 ms\033[0m  \033[31m 10.0%\033[0m\n"
            "  ScanningStage.scan   \033[31m 457 us\033[0m  \033[31m  0.4%\033[0m"
        )

    def test_art_extlut_compatibility_path_runs(self):
        # make sure ART is compatible
        """reference this https://github.com/artraweditor/ART/blob/master/tools/extlut/spektrafilm_mklut.py"""
        def make_art_params():
            params = photo_params(
                FilmStocks.kodak_portra_400.value,
                PrintPapers.kodak_portra_endura.value,
            )
            params.camera.auto_exposure = False
            params.camera.auto_exposure_method = 'median'
            params.camera.exposure_compensation_ev = 0.0
            params.debug.deactivate_spatial_effects = True
            params.debug.deactivate_stochastic_effects = True
            params.enlarger.lens_blur = 0.0
            params.enlarger.m_filter_shift = 0.0
            params.enlarger.print_exposure = 1.0
            params.enlarger.print_exposure_compensation = True
            params.enlarger.y_filter_shift = 0.0
            params.io.compute_negative = False
            params.io.crop = False
            with pytest.deprecated_call(match="full_image is deprecated"):
                params.io.full_image = True
            params.io.input_cctf_decoding = False
            params.io.input_color_space = 'sRGB'
            params.io.output_cctf_encoding = False
            params.io.output_color_space = 'ACES2065-1'
            params.io.preview_resize_factor = 1.0
            params.io.upscale_factor = 1.0
            params.scanner.lens_blur = 0.0
            params.scanner.unsharp_mask = (0.0, 0.0)
            params.settings.use_enlarger_lut = False
            params.settings.use_scanner_lut = False
            params.settings.rgb_to_raw_method = 'mallett2019'
            params.film_render.grain.active = False
            params.film_render.halation.active = False
            params.film_render.density_curve_gamma = 1.0
            params.film_render.dir_couplers.active = True
            params.film_render.dir_couplers.amount = 1.0
            params.print_render.glare.active = False
            params.print_render.density_curve_gamma = 1.0
            return params

        image = np.array([[[0.184, 0.184, 0.184]]], dtype=np.float64)

        params = make_art_params()
        assert params.io.compute_negative is False
        with pytest.deprecated_call(match="full_image is deprecated"):
            assert params.io.full_image is True
        assert params.io.preview_resize_factor == 1.0

        output = AgXPhoto(params).process(image)
        assert output.shape == image.shape
        assert np.isfinite(output).all()

        shifted_params = make_art_params()
        shifted_params.enlarger.y_filter_shift = 0.5
        shifted_params.enlarger.m_filter_shift = -0.5
        shifted_output = AgXPhoto(shifted_params).process(image)
        assert shifted_output.shape == image.shape
        assert np.isfinite(shifted_output).all()

    def test_characterize_pipeline_profile_returns_valid_curves(self, default_params):
        simulator = process_module.Simulator(default_params)
        scene_y, look_y = pipeline_module.characterize_pipeline_profile(simulator._pipeline)

        assert scene_y.shape == (512,)
        assert look_y.shape == (512,)
        assert np.all(np.isfinite(scene_y))
        assert np.all(np.isfinite(look_y))
        assert np.all(scene_y > 0), "scene_y should be positive (logspace ramp)"
        assert np.all(look_y >= 0), "look_y should be non-negative"

    def test_characterize_pipeline_profile_uses_cached_curves(self, default_params, monkeypatch):
        simulator = process_module.Simulator(default_params)
        first_scene_y, first_look_y = pipeline_module.characterize_pipeline_profile(simulator._pipeline)

        def fail_if_recomputed(*args, **kwargs):
            raise AssertionError("profile characterization should be cached")

        monkeypatch.setattr(pipeline_module.SimulationPipeline, "_pipeline_print", fail_if_recomputed)

        second_scene_y, second_look_y = pipeline_module.characterize_pipeline_profile(simulator._pipeline)

        assert second_scene_y is first_scene_y
        assert second_look_y is first_look_y

    @pytest.mark.parametrize(
        'image_factory,expected_confidence',
        [
            (lambda: np.full((2, 4, 3), 0.25, dtype=np.float32), 'medium'),
            (lambda: np.full((2, 4, 3), 0.001, dtype=np.float32), 'low'),
            (lambda: np.zeros((1, 1, 3), dtype=np.float32), 'low'),
        ],
        ids=['normal', 'low_key', 'black'],
    )
    def test_hdr_scene_energy_metadata_confidence_levels(self, image_factory, expected_confidence):
        image = image_factory()
        metadata = pipeline_module._hdr_scene_energy_metadata(
            image,
            input_color_space='sRGB',
            apply_cctf_decoding=False,
            auto_exposure_ev=0.0,
        )
        assert metadata.confidence == expected_confidence
        assert metadata.scene_luminance.shape == image.shape[:2]
        assert np.all(np.isfinite(metadata.scene_luminance))
        assert metadata.diffuse_white_estimate > 0
        assert metadata.headroom_estimate >= 1.0

    def test_hdr_scene_energy_metadata_single_pixel(self):
        image = np.array([[[0.5, 0.5, 0.5]]], dtype=np.float32)
        metadata = pipeline_module._hdr_scene_energy_metadata(
            image,
            input_color_space='sRGB',
            apply_cctf_decoding=False,
            auto_exposure_ev=0.0,
        )
        assert metadata.scene_luminance.shape == (1, 1)
        assert np.all(np.isfinite(metadata.scene_luminance))
        assert metadata.diffuse_white_estimate > 0

    def test_hdr_scene_energy_metadata_omits_scene_rgb_by_default(self):
        image = np.full((2, 3, 3), 0.25, dtype=np.float32)

        metadata = pipeline_module._hdr_scene_energy_metadata(
            image,
            input_color_space='sRGB',
            apply_cctf_decoding=False,
            auto_exposure_ev=0.0,
        )

        assert metadata.scene_luminance.shape == image.shape[:2]
        assert metadata.scene_rgb is None

    def test_hdr_scene_energy_metadata_can_include_scene_rgb(self):
        image = np.full((2, 3, 3), 0.25, dtype=np.float32)

        metadata = pipeline_module._hdr_scene_energy_metadata(
            image,
            input_color_space='sRGB',
            apply_cctf_decoding=False,
            auto_exposure_ev=0.0,
            include_scene_rgb=True,
        )

        assert metadata.scene_rgb is not None
        assert metadata.scene_rgb.shape == image.shape
        assert metadata.scene_rgb.dtype == np.float32

    def test_simulator_process_with_metadata_forwards_scene_rgb_flag(self, monkeypatch):
        rendered = np.full((1, 1, 3), 0.25, dtype=np.float32)
        metadata = pipeline_module.HDRSceneEnergyMetadata(
            scene_luminance=np.array([[0.5]], dtype=np.float32),
            diffuse_white_estimate=0.5,
            headroom_estimate=1.0,
            auto_exposure_ev=0.0,
            method='auto_percentile',
            confidence='medium',
            scene_rgb=np.full((1, 1, 3), 0.5, dtype=np.float32),
        )
        captured: dict[str, object] = {}

        class FakePipeline:
            def __init__(self, _params):
                self._array_backend = SimpleNamespace(requires_serial_runtime=False)

            def process_with_metadata(self, image, *, include_scene_rgb=False):
                captured['call'] = (image, include_scene_rgb)
                return pipeline_module.SimulationPipelineResult(
                    image=rendered,
                    hdr_scene_energy=metadata,
                )

        monkeypatch.setattr(process_module, 'SimulationPipeline', FakePipeline)
        params = SimpleNamespace(
            settings=SimpleNamespace(compute_backend='cpu', float_precision='float32'),
        )

        result = process_module.Simulator(params).process_with_metadata('frame', include_scene_rgb=True)

        assert captured['call'] == ('frame', True)
        assert result.hdr_scene_energy is metadata

    def test_pipeline_process_cleans_up_gpu_backend_after_materialization(self, monkeypatch):
        pipeline = object.__new__(pipeline_module.SimulationPipeline)
        pipeline.timings = {}
        pipeline._last_elapsed_time = None
        pipeline.debug = SimpleNamespace(debug_mode='off')
        pipeline._runtime_dtype = np.dtype(np.float32)
        captured: dict[str, object] = {'cleanup_calls': 0}

        class FakeBackend:
            supports_gpu = True

            def to_numpy(self, value):
                captured['to_numpy'] = value
                return np.asarray(value, dtype=np.float32)

            def cleanup(self):
                captured['cleanup_calls'] += 1

        pipeline._array_backend = FakeBackend()
        monkeypatch.setattr(pipeline, '_should_tile_gpu_image', lambda _image: False)
        monkeypatch.setattr(pipeline, '_pipeline', lambda image: image + 1.0)
        monkeypatch.setattr(pipeline, '_gpu_validation_enabled', lambda: False)

        result = pipeline_module.SimulationPipeline.process(
            pipeline,
            np.full((1, 1, 3), 0.25, dtype=np.float32),
        )

        np.testing.assert_allclose(result, 1.25)
        assert captured['cleanup_calls'] == 1
