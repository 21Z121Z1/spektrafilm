from __future__ import annotations

from types import SimpleNamespace

import numpy as np

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
        output_color_space='ACES2065-1',
        output_cctf_encoding=False,
        use_display_transform=True,
        phase_timings={'gui.input_conversion': 0.125},
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
    assert result.output_cctf_encoding is False
    assert captured['display_args']['output_cctf_encoding'] is False
    assert result.status_message.startswith('Display transform: active')
    assert 'process=' in result.status_message
    assert result.phase_timings['gui.input_conversion'] == 0.125
    assert result.phase_timings['runtime.process'] >= 0.0
    assert result.phase_timings['gui.display_prepare'] >= 0.0
    assert result.phase_timings['gui.float_materialize'] >= 0.0
    assert result.phase_timings['gui.worker_total'] >= result.phase_timings['runtime.process']


def test_execute_simulation_request_appends_runtime_backend_status() -> None:
    request = runtime_module.SimulationRequest(
        mode_label='Preview',
        image=np.full((2, 2, 3), 0.25, dtype=np.float32),
        params=object(),
        output_color_space='sRGB',
        use_display_transform=False,
    )

    result = runtime_module.execute_simulation_request(
        request,
        run_simulation_fn=lambda image, params: np.full((4, 4, 3), 0.5, dtype=np.float32),
        prepare_output_display_image_fn=lambda image, **kwargs: (
            np.full((4, 4, 3), 127, dtype=np.uint8),
            'Display transform: disabled',
        ),
        runtime_status_fn=lambda: 'MLX float32',
        runtime_timings_fn=lambda: {'preprocess': 0.01, 'filming.develop': 0.02},
    )

    assert result.status_message.startswith('Display transform: disabled | MLX float32')
    assert 'process=' in result.status_message
    assert result.runtime_stage_timings == {'preprocess': 0.01, 'filming.develop': 0.02}


def test_prepare_output_display_image_uses_aces_output_transform_for_linear_scene(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_aces_output_transform(image, *, color_space, colour_module):
        captured['aces_call'] = {
            'image': image.copy(),
            'color_space': color_space,
            'colour_module': colour_module,
        }
        return np.full_like(image, 0.5)

    def fail_rgb_to_rgb(*_args, **_kwargs):
        raise AssertionError('ACES preview must use the dedicated ACES output transform')

    monkeypatch.setattr(runtime_module, 'aces_sdr_video_view_transform', fake_aces_output_transform)
    colour_module = SimpleNamespace(RGB_to_RGB=fail_rgb_to_rgb)
    preview, status = runtime_module.prepare_output_display_image(
        np.array([[[-0.25, 1.25, 2.0]]], dtype=np.float32),
        output_color_space='ACEScg',
        output_cctf_encoding=False,
        use_display_transform=True,
        colour_module=colour_module,
        imagecms_module=SimpleNamespace(
            PyCMSError=RuntimeError,
            get_display_profile=lambda: object(),
            getProfileName=lambda profile: 'Display',
        ),
        pil_image_module=SimpleNamespace(),
    )

    assert preview.dtype == np.uint8
    assert status == 'Display transform: ACES SDR video output transform'
    assert captured['aces_call']['color_space'] == 'ACEScg'
    assert captured['aces_call']['colour_module'] is colour_module
    np.testing.assert_allclose(captured['aces_call']['image'], [[[0.0, 1.25, 2.0]]])


def test_simulation_worker_emits_failure_message() -> None:
    request = runtime_module.SimulationRequest(
        mode_label='Preview',
        image=np.zeros((1, 1, 3), dtype=np.float32),
        params=object(),
        output_color_space='sRGB',
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


def test_simulation_worker_emits_failure_message_for_base_exception() -> None:
    request = runtime_module.SimulationRequest(
        mode_label='Preview',
        image=np.zeros((1, 1, 3), dtype=np.float32),
        params=object(),
        output_color_space='sRGB',
        use_display_transform=False,
    )

    class WorkerAbort(BaseException):
        pass

    worker = runtime_module.SimulationWorker(
        request,
        execute_request=lambda request: (_ for _ in ()).throw(WorkerAbort('metal abort')),
    )
    worker.signals = SimpleNamespace(finished=FakeSignal(), failed=FakeSignal())

    worker.run()

    assert worker.signals.finished.emitted == []
    assert worker.signals.failed.emitted == ['WorkerAbort: metal abort']


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


def _capture_preview_result(captured: dict[str, object], image: np.ndarray, **kwargs):
    captured['display_args'] = {'image': image.copy(), **kwargs}
    return np.full((6, 6, 3), 99, dtype=np.uint8), 'Display transform: active'
