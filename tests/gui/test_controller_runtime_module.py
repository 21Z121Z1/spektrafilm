from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from spektrafilm.color_management import ColorEncoding
from spektrafilm_gui import controller_runtime as runtime_module


class FakeSignal:
    def __init__(self) -> None:
        self.emitted: list[object] = []

    def emit(self, value) -> None:
        self.emitted.append(value)


def test_execute_simulation_request_uses_runtime_runner_without_padding() -> None:
    request = runtime_module.SimulationRequest(
        mode_label='Preview',
        image=np.full((2, 2, 3), 0.25, dtype=np.float32),
        params=object(),
        output_encoding=ColorEncoding(color_space='ACES2065-1', transfer='linear'),
        use_display_transform=True,
    )
    captured: dict[str, object] = {}

    result = runtime_module.execute_simulation_request(
        request,
        run_simulation_fn=lambda image, params: np.full((4, 4, 3), 0.5, dtype=np.float32),
        prepare_output_display_image_fn=lambda image, **kwargs: _capture_preview_result(captured, image, **kwargs),
    )

    np.testing.assert_allclose(captured['display_args']['image'], np.full((4, 4, 3), 0.5, dtype=np.float32))
    assert result.mode_label == 'Preview'
    np.testing.assert_allclose(result.float_image, np.full((4, 4, 3), 0.5, dtype=np.float32))
    assert result.status_message == 'Display transform: active'


def test_execute_simulation_request_propagates_hdr_scene_energy_metadata() -> None:
    request = runtime_module.SimulationRequest(
        mode_label='Scan',
        image=np.full((2, 2, 3), 0.25, dtype=np.float32),
        params=object(),
        output_encoding=ColorEncoding(color_space='Display P3', transfer='linear'),
        use_display_transform=False,
    )
    metadata = runtime_module.HDRSceneEnergyMetadata(
        scene_luminance=np.array([[0.5, 2.0]], dtype=np.float32),
        diffuse_white_estimate=0.5,
        headroom_estimate=4.0,
        auto_exposure_ev=-1.0,
        method='auto_percentile',
        confidence='medium',
    )
    rendered = np.full((1, 2, 3), 0.75, dtype=np.float32)

    result = runtime_module.execute_simulation_request(
        request,
        run_simulation_fn=lambda image, params: runtime_module.SimulationPipelineResult(
            image=rendered,
            hdr_scene_energy=metadata,
        ),
        prepare_output_display_image_fn=lambda image, **kwargs: (np.uint8(image * 255), 'Display transform: disabled'),
    )

    np.testing.assert_allclose(result.float_image, rendered)
    assert result.hdr_scene_energy is metadata


def test_simulation_worker_emits_failure_message() -> None:
    request = runtime_module.SimulationRequest(
        mode_label='Preview',
        image=np.zeros((1, 1, 3), dtype=np.float32),
        params=object(),
        output_encoding=ColorEncoding(color_space='sRGB', transfer='cctf'),
        use_display_transform=False,
    )
    worker = runtime_module.SimulationWorker(
        request,
        execute_request=lambda request: (_ for _ in ()).throw(ValueError('bad simulation')),
    )
    worker.signals = SimpleNamespace(finished=FakeSignal(), failed=FakeSignal())

    worker.run()

    assert worker.signals.finished.emitted == []
    assert worker.signals.failed.emitted == ['ValueError: bad simulation']


def test_simulation_worker_catches_base_exception_at_qt_boundary() -> None:
    request = runtime_module.SimulationRequest(
        mode_label='Preview',
        image=np.zeros((1, 1, 3), dtype=np.float32),
        params=object(),
        output_encoding=ColorEncoding(color_space='sRGB', transfer='cctf'),
        use_display_transform=False,
    )
    worker = runtime_module.SimulationWorker(
        request,
        execute_request=lambda request: (_ for _ in ()).throw(KeyboardInterrupt('stop')),
    )
    worker.signals = SimpleNamespace(finished=FakeSignal(), failed=FakeSignal())

    worker.run()

    assert worker.signals.finished.emitted == []
    assert worker.signals.failed.emitted == ['KeyboardInterrupt: stop']


def test_prepare_input_color_preview_image_converts_to_srgb_float_preview() -> None:
    captured: dict[str, object] = {}

    def fake_rgb_to_rgb(image, input_color_space, output_color_space, apply_cctf_decoding, apply_cctf_encoding):
        captured['call'] = {
            'image': image.copy(),
            'input_color_space': input_color_space,
            'output_color_space': output_color_space,
            'apply_cctf_decoding': apply_cctf_decoding,
            'apply_cctf_encoding': apply_cctf_encoding,
        }
        return np.full((1, 1, 3), 0.5, dtype=np.float32)

    preview = runtime_module.prepare_input_color_preview_image(
        np.full((1, 1, 3), 0.25, dtype=np.float32),
        input_color_space='Display P3',
        apply_cctf_decoding=True,
        colour_module=SimpleNamespace(RGB_to_RGB=fake_rgb_to_rgb),
    )

    assert preview.dtype == np.float32
    np.testing.assert_allclose(preview, np.full((1, 1, 3), 0.5, dtype=np.float32))
    assert captured['call']['input_color_space'] == 'Display P3'
    assert captured['call']['output_color_space'] == runtime_module.DISPLAY_PREVIEW_COLOR_SPACE
    assert captured['call']['apply_cctf_decoding'] is True
    assert captured['call']['apply_cctf_encoding'] is True


def test_apply_display_transform_warns_for_linear_scene_space_without_icc() -> None:
    captured: dict[str, object] = {}

    class FakePILImage:
        def __init__(self, array: np.ndarray):
            self.array = array

    def fake_rgb_to_rgb(image, input_color_space, output_color_space, apply_cctf_decoding, apply_cctf_encoding):
        captured['rgb_to_rgb'] = {
            'image': np.asarray(image).copy(),
            'input_color_space': input_color_space,
            'output_color_space': output_color_space,
            'apply_cctf_decoding': apply_cctf_decoding,
            'apply_cctf_encoding': apply_cctf_encoding,
        }
        return np.full((1, 1, 3), 0.5, dtype=np.float32)

    def fake_profile_to_profile(source, source_profile, display_profile, outputMode='RGB'):
        captured['profile_to_profile'] = {
            'source_profile': source_profile,
            'display_profile': display_profile,
            'output_mode': outputMode,
            'image': source.array.copy(),
        }
        return np.full((1, 1, 3), 64, dtype=np.uint8)

    imagecms_module = SimpleNamespace(
        PyCMSError=RuntimeError,
        get_display_profile=lambda: 'display-profile',
        getProfileName=lambda profile: 'Reference Monitor\x00',
        createProfile=lambda name: f'profile:{name}',
        profileToProfile=fake_profile_to_profile,
    )
    pil_image_module = SimpleNamespace(fromarray=lambda array, mode='RGB': FakePILImage(array.copy()))

    preview, status = runtime_module.apply_display_transform(
        np.array([[[0.2, 0.4, 0.6]]], dtype=np.float32),
        output_encoding=ColorEncoding(color_space='ACES2065-1', transfer='linear'),
        colour_module=SimpleNamespace(RGB_to_RGB=fake_rgb_to_rgb),
        imagecms_module=imagecms_module,
        pil_image_module=pil_image_module,
    )

    np.testing.assert_array_equal(preview, np.full((1, 1, 3), 64, dtype=np.uint8))
    assert 'ACES2065-1 has no ICC profile' in status
    assert 'without a scene-linear view transform' in status
    assert captured['rgb_to_rgb']['input_color_space'] == 'ACES2065-1'
    assert captured['rgb_to_rgb']['output_color_space'] == runtime_module.DISPLAY_PREVIEW_COLOR_SPACE
    assert captured['rgb_to_rgb']['apply_cctf_decoding'] is False
    assert captured['rgb_to_rgb']['apply_cctf_encoding'] is True
    assert captured['profile_to_profile']['source_profile'] == 'profile:sRGB'


def test_apply_display_transform_uses_acescg_icc_profile_when_available() -> None:
    captured: dict[str, object] = {}

    class FakePILImage:
        def __init__(self, array: np.ndarray):
            self.array = array

    def fake_rgb_to_rgb(image, input_color_space, output_color_space, apply_cctf_decoding, apply_cctf_encoding):
        captured['rgb_to_rgb'] = {
            'image': np.asarray(image).copy(),
            'input_color_space': input_color_space,
            'output_color_space': output_color_space,
            'apply_cctf_decoding': apply_cctf_decoding,
            'apply_cctf_encoding': apply_cctf_encoding,
        }
        return np.full((1, 1, 3), 0.5, dtype=np.float32)

    def fake_profile_to_profile(source, source_profile, display_profile, outputMode='RGB'):
        captured['profile_to_profile'] = {
            'source_profile': source_profile,
            'display_profile': display_profile,
            'output_mode': outputMode,
            'image': source.array.copy(),
        }
        return np.full((1, 1, 3), 64, dtype=np.uint8)

    imagecms_module = SimpleNamespace(
        PyCMSError=RuntimeError,
        get_display_profile=lambda: 'display-profile',
        getProfileName=lambda profile: 'Reference Monitor',
        ImageCmsProfile=lambda stream: 'profile:acescg',
        profileToProfile=fake_profile_to_profile,
    )
    pil_image_module = SimpleNamespace(fromarray=lambda array, mode='RGB': FakePILImage(array.copy()))

    preview, status = runtime_module.apply_display_transform(
        np.array([[[0.2, 0.4, 0.6]]], dtype=np.float32),
        output_encoding=ColorEncoding(color_space='ACEScg', transfer='linear'),
        colour_module=SimpleNamespace(RGB_to_RGB=fake_rgb_to_rgb),
        imagecms_module=imagecms_module,
        pil_image_module=pil_image_module,
    )

    np.testing.assert_array_equal(preview, np.full((1, 1, 3), 64, dtype=np.uint8))
    assert status == 'Display transform: active (Reference Monitor)'
    assert captured['rgb_to_rgb']['input_color_space'] == 'ACEScg'
    assert captured['rgb_to_rgb']['output_color_space'] == 'ACEScg'
    assert captured['rgb_to_rgb']['apply_cctf_decoding'] is False
    assert captured['rgb_to_rgb']['apply_cctf_encoding'] is True
    assert captured['profile_to_profile']['source_profile'] == 'profile:acescg'


def _capture_preview_result(captured: dict[str, object], image: np.ndarray, **kwargs):
    captured['display_args'] = {'image': image.copy(), **kwargs}
    return np.full((6, 6, 3), 99, dtype=np.uint8), 'Display transform: active'
