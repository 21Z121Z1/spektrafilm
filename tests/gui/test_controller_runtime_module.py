from __future__ import annotations

from io import BytesIO
import sys
from types import SimpleNamespace

import numpy as np
import pytest

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
    assert 'gui.float_materialize' not in result.phase_timings
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


def test_execute_simulation_request_keeps_scan_as_export_source_until_display() -> None:
    class ArrayLikeScan:
        def __init__(self) -> None:
            self.array_calls = 0
            self.shape = (2, 2, 3)
            self.dtype = np.dtype(np.float32)
            self.nbytes = int(np.prod(self.shape) * self.dtype.itemsize)

        def __array__(self, dtype=None):
            self.array_calls += 1
            array = np.full((2, 2, 3), 0.5, dtype=np.float32)
            if dtype is not None:
                return np.asarray(array, dtype=dtype)
            return array

    scan = ArrayLikeScan()
    captured: dict[str, object] = {}
    request = runtime_module.SimulationRequest(
        mode_label='Scan',
        image=np.full((2, 2, 3), 0.25, dtype=np.float32),
        params=object(),
        output_color_space='sRGB',
        use_display_transform=False,
    )

    def fake_prepare_display(image, **_kwargs):
        captured['display_image_input'] = image
        np.asarray(image)
        return np.full((2, 2, 3), 127, dtype=np.uint8), 'Display transform: disabled'

    result = runtime_module.execute_simulation_request(
        request,
        run_simulation_fn=lambda image, params: SimpleNamespace(image=scan),
        prepare_output_display_image_fn=fake_prepare_display,
    )

    assert scan.array_calls == 1
    assert result.float_image is scan
    assert captured['display_image_input'] is scan
    assert 'gui.float_materialize' not in result.phase_timings
    assert 'gui.float_materialize_copy_nbytes' not in result.memory_estimates
    assert result.memory_estimates['gui.export_source_nbytes'] == scan.nbytes
    assert result.memory_estimates['gui.float_image_nbytes'] == scan.nbytes
    assert result.memory_estimates['gui.display_image_nbytes'] == result.display_image.nbytes


def test_materialize_export_image_records_timing_and_dtype() -> None:
    timings: dict[str, float] = {}
    source = np.full((2, 2, 4), 0.5, dtype=np.float64)

    export_image = runtime_module.materialize_export_image(source, phase_timings=timings)

    assert export_image.dtype == np.float32
    assert export_image.shape == (2, 2, 3)
    np.testing.assert_allclose(export_image, np.full((2, 2, 3), 0.5, dtype=np.float32))
    assert timings['gui.export_materialize'] >= 0.0


def test_prepare_output_display_image_records_split_timings() -> None:
    timings: dict[str, float] = {}

    preview, status = runtime_module.prepare_output_display_image(
        np.full((2, 2, 3), 0.5, dtype=np.float32),
        output_color_space='sRGB',
        output_cctf_encoding=True,
        use_display_transform=False,
        colour_module=SimpleNamespace(),
        imagecms_module=SimpleNamespace(
            PyCMSError=RuntimeError,
            get_display_profile=lambda: None,
        ),
        pil_image_module=SimpleNamespace(),
        phase_timings=timings,
    )

    assert preview.dtype == np.uint8
    assert status == 'Display transform: disabled'
    assert timings['gui.display_uint8'] >= 0.0
    assert 'gui.display_transform' not in timings


def test_prepare_output_display_image_materializes_full_resolution_scan_for_large_sources() -> None:
    captured: dict[str, object] = {}

    class LargeArrayLike:
        shape = (100, 100, 3)
        dtype = np.dtype(np.float32)
        nbytes = int(np.prod(shape) * dtype.itemsize)

        def __getitem__(self, key):
            captured['key'] = key
            raise AssertionError('display preparation must not downsample scan output')

        def __array__(self, dtype=None):
            captured['array_dtype'] = dtype
            array = np.full(self.shape, 0.5, dtype=np.float32)
            if dtype is not None:
                return np.asarray(array, dtype=dtype)
            return array

    preview, status = runtime_module.prepare_output_display_image(
        LargeArrayLike(),
        output_color_space='sRGB',
        output_cctf_encoding=True,
        use_display_transform=False,
        colour_module=SimpleNamespace(),
        imagecms_module=SimpleNamespace(
            PyCMSError=RuntimeError,
            get_display_profile=lambda: None,
        ),
        pil_image_module=SimpleNamespace(),
    )

    assert preview.shape == (100, 100, 3)
    assert preview.dtype == np.uint8
    assert 'key' not in captured
    assert captured['array_dtype'] is None
    assert 'display proxy' not in status


def test_prepare_output_display_image_defers_raw_uint8_when_transform_succeeds(monkeypatch) -> None:
    timings: dict[str, float] = {}

    monkeypatch.setattr(
        runtime_module,
        'apply_display_transform',
        lambda image, **_kwargs: (np.full(image.shape, 127, dtype=np.uint8), 'Display transform: active (Test; SDR 8-bit preview)'),
    )

    preview, status = runtime_module.prepare_output_display_image(
        np.full((2, 2, 3), 0.5, dtype=np.float32),
        output_color_space='sRGB',
        output_cctf_encoding=True,
        use_display_transform=True,
        colour_module=SimpleNamespace(),
        imagecms_module=SimpleNamespace(PyCMSError=RuntimeError),
        pil_image_module=SimpleNamespace(),
        phase_timings=timings,
    )

    assert preview.dtype == np.uint8
    assert status == 'Display transform: active (Test; SDR 8-bit preview)'
    assert 'gui.display_uint8' not in timings
    assert timings['gui.display_transform'] >= 0.0


def test_full_render_memory_guard_reports_large_mlx_render() -> None:
    class LargeImage:
        shape = (6144, 8192, 3)
        dtype = np.dtype(np.float32)
        nbytes = int(np.prod(shape) * dtype.itemsize)

    params = SimpleNamespace(
        settings=SimpleNamespace(compute_backend='mlx', gpu_precision='float32'),
        io=SimpleNamespace(input_color_space='ProPhoto RGB'),
        film_render=SimpleNamespace(grain=SimpleNamespace(active=True, sublayers_active=True)),
    )

    message = runtime_module.full_render_memory_guard_message(
        LargeImage(),
        params,
        available_bytes=32 * 1024**3,
    )

    assert message is not None
    assert 'Full-resolution render is likely to exceed the memory budget' in message
    assert 'spatial_filter_transients' in message


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


def test_get_mac_display_profile_bytes_returns_none_when_framework_load_fails(monkeypatch) -> None:
    monkeypatch.setattr(runtime_module.sys, 'platform', 'darwin')

    def raise_os_error(_path):
        raise OSError('framework unavailable')

    monkeypatch.setattr(runtime_module.ctypes, 'CDLL', raise_os_error)

    assert runtime_module._get_mac_display_profile_bytes() is None


@pytest.mark.skipif(sys.platform != 'darwin', reason='macOS display profile smoke test')
def test_get_mac_display_profile_bytes_macos_smoke() -> None:
    from PIL import ImageCms

    icc_bytes = runtime_module._get_mac_display_profile_bytes()
    if icc_bytes is None:
        pytest.skip('No main display ICC profile available through CoreGraphics')

    assert len(icc_bytes) > 0
    ImageCms.ImageCmsProfile(BytesIO(icc_bytes))


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


def test_simulation_worker_reraises_base_exception() -> None:
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

    with pytest.raises(WorkerAbort, match='metal abort'):
        worker.run()

    assert worker.signals.finished.emitted == []
    assert worker.signals.failed.emitted == []


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
