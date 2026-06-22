from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from spektrafilm_gui import controller as controller_module
from spektrafilm_gui.controller import (
    GuiController,
    OUTPUT_CCTF_ENCODING_KEY,
    OUTPUT_COLOR_SPACE_KEY,
    OUTPUT_DISPLAY_TRANSFORM_KEY,
    OUTPUT_FLOAT_DATA_KEY,
    OUTPUT_PHASE_TIMINGS_KEY,
    OUTPUT_ROUTE_MASTER_KEY,
)

from .helpers import FakeLayer, StubToggle, make_test_controller_gui_state


pytestmark = pytest.mark.integration


def _make_output_layer(
    float_image: np.ndarray,
    *,
    output_color_space: str,
    output_cctf_encoding: bool,
    output_display_transform: bool = False,
) -> FakeLayer:
    return FakeLayer(
        np.uint8(float_image * 255),
        metadata={
            OUTPUT_FLOAT_DATA_KEY: float_image,
            OUTPUT_COLOR_SPACE_KEY: output_color_space,
            OUTPUT_CCTF_ENCODING_KEY: output_cctf_encoding,
            OUTPUT_DISPLAY_TRANSFORM_KEY: output_display_transform,
        },
    )


def _configure_save_output(monkeypatch, controller: GuiController, output_layer: FakeLayer, gui_state, captured: dict[str, object]) -> None:
    monkeypatch.setattr(controller, '_output_layer', lambda: output_layer)
    monkeypatch.setattr(controller_module, 'dialog_parent', lambda viewer: None)
    monkeypatch.setattr(controller_module, 'set_status', lambda viewer, message: captured.setdefault('status', message))
    monkeypatch.setattr(controller_module, 'load_dialog_dir', lambda key: '')
    monkeypatch.setattr(controller_module, 'save_dialog_dir', lambda key, directory: None)
    monkeypatch.setattr(
        controller_module.QFileDialog,
        'getSaveFileName',
        staticmethod(lambda *args, **kwargs: ('output.png', 'Images (*.png)')),
    )
    monkeypatch.setattr(controller_module, 'collect_gui_state', lambda *, widgets: gui_state)


def _capture_saved_output(monkeypatch, captured: dict[str, object]) -> None:
    def fake_save_image_oiio(filepath, image_data, **kwargs) -> None:
        captured.setdefault('saved', (filepath, image_data.copy()))
        captured.setdefault('saved_kwargs', kwargs)

    def fake_write_image_metadata(filepath, source_metadata=None, **kwargs) -> None:
        captured.setdefault('metadata', {
            'filepath': filepath,
            'source_metadata': source_metadata,
            **kwargs,
        })

    monkeypatch.setattr(
        controller_module,
        'save_image_oiio',
        fake_save_image_oiio,
    )
    monkeypatch.setattr(
        controller_module,
        'write_image_metadata',
        fake_write_image_metadata,
    )


def _run_save_output_case(
    monkeypatch,
    *,
    float_value: float,
    output_color_space: str,
    output_cctf_encoding: bool,
    saving_color_space: str,
    saving_cctf_encoding: bool,
    converted_delta: float | None,
) -> dict[str, object]:
    float_image = np.full((2, 2, 3), float_value, dtype=np.float32)
    output_layer = _make_output_layer(
        float_image,
        output_color_space=output_color_space,
        output_cctf_encoding=output_cctf_encoding,
    )
    controller = GuiController(viewer=object(), widgets=object())
    captured: dict[str, object] = {}
    gui_state = make_test_controller_gui_state()
    gui_state.simulation.workflow.saving_color_space = saving_color_space
    gui_state.simulation.workflow.saving_cctf_encoding = saving_cctf_encoding

    _configure_save_output(monkeypatch, controller, output_layer, gui_state, captured)

    if converted_delta is None:
        def fail_rgb_to_rgb(*args, **kwargs):
            raise AssertionError('RGB_to_RGB should not be called when color spaces and encoding flags match')

        monkeypatch.setattr(
            controller_module.colour,
            'RGB_to_RGB',
            fail_rgb_to_rgb,
        )
    else:
        def fake_rgb_to_rgb(image_data, input_color_space, output_color_space, apply_cctf_decoding, apply_cctf_encoding):
            captured['rgb_to_rgb'] = {
                'image_data': image_data.copy(),
                'input_color_space': input_color_space,
                'output_color_space': output_color_space,
                'apply_cctf_decoding': apply_cctf_decoding,
                'apply_cctf_encoding': apply_cctf_encoding,
            }
            return image_data + converted_delta

        monkeypatch.setattr(controller_module.colour, 'RGB_to_RGB', fake_rgb_to_rgb)

    _capture_saved_output(monkeypatch, captured)
    controller.save_output_layer()
    captured['float_image'] = float_image
    return captured


def _capture_status(monkeypatch) -> dict[str, object]:
    captured: dict[str, object] = {}

    def fake_set_status(_viewer, message) -> None:
        captured.setdefault('status', message)

    monkeypatch.setattr(controller_module, 'set_status', fake_set_status)
    return captured


def _assert_fallback_preview(preview: np.ndarray, status: str, *, expected_status: str) -> None:
    assert preview.dtype == np.uint8
    assert status == expected_status


def _assert_preview_conversion(
    preview: np.ndarray,
    status: str,
    *,
    expected_shape: tuple[int, int, int],
    expected_status: str,
    expected_center: np.ndarray,
    expected_corner: np.ndarray | None = None,
) -> None:
    assert preview.shape == expected_shape
    assert status == expected_status
    center_row = expected_shape[0] // 2
    center_col = expected_shape[1] // 2
    np.testing.assert_array_equal(preview[center_row, center_col], expected_center)
    if expected_corner is not None:
        np.testing.assert_array_equal(preview[0, 0], expected_corner)


def _make_display_transform_controller(*, with_toggle: bool) -> tuple[GuiController, StubToggle | None]:
    if not with_toggle:
        return GuiController(viewer=object(), widgets=object()), None

    toggle = StubToggle(True)
    controller = GuiController(
        viewer=object(),
        widgets=SimpleNamespace(display=SimpleNamespace(use_display_transform=toggle)),
    )
    return controller, toggle


def test_set_output_interpolation_mode_updates_visible_output_layer(monkeypatch) -> None:
    output_layer = FakeLayer(np.zeros((2, 2, 3), dtype=np.uint8), name='output')
    controller = GuiController(viewer=object(), widgets=object())
    monkeypatch.setattr(controller, '_output_layer', lambda: output_layer)

    controller.set_output_interpolation_mode('nearest')

    assert getattr(output_layer, 'interpolation2d') == 'nearest'


@pytest.mark.parametrize(
    (
        'float_value',
        'output_color_space',
        'output_cctf_encoding',
        'saving_color_space',
        'saving_cctf_encoding',
        'converted_delta',
        'expected_input_space',
        'expected_output_space',
        'expected_saved_delta',
    ),
    [
        (0.25, 'sRGB', True, 'Display P3', False, 0.1, 'sRGB', 'Display P3', 0.1),
        (0.5, 'Display P3', True, 'Display P3', True, None, None, None, 0.0),
        (0.5, 'Display P3', True, 'Display P3', False, -0.1, 'Display P3', 'Display P3', -0.1),
    ],
    ids=['convert-color-space', 'skip-matching-render-metadata', 'reencode-cctf-only'],
)
def test_save_output_layer_respects_recorded_render_metadata(
    monkeypatch,
    float_value: float,
    output_color_space: str,
    output_cctf_encoding: bool,
    saving_color_space: str,
    saving_cctf_encoding: bool,
    converted_delta: float | None,
    expected_input_space: str | None,
    expected_output_space: str | None,
    expected_saved_delta: float,
) -> None:
    captured = _run_save_output_case(
        monkeypatch,
        float_value=float_value,
        output_color_space=output_color_space,
        output_cctf_encoding=output_cctf_encoding,
        saving_color_space=saving_color_space,
        saving_cctf_encoding=saving_cctf_encoding,
        converted_delta=converted_delta,
    )

    if converted_delta is None:
        assert 'rgb_to_rgb' not in captured
    else:
        rgb_to_rgb_call = captured['rgb_to_rgb']
        np.testing.assert_allclose(rgb_to_rgb_call['image_data'], captured['float_image'])
        assert rgb_to_rgb_call['input_color_space'] == expected_input_space
        assert rgb_to_rgb_call['output_color_space'] == expected_output_space
        assert rgb_to_rgb_call['apply_cctf_decoding'] is True
        assert rgb_to_rgb_call['apply_cctf_encoding'] is False

    saved_path, saved_image = captured['saved']
    assert saved_path == 'output.png'
    np.testing.assert_allclose(saved_image, captured['float_image'] + expected_saved_delta)

    metadata_call = captured['metadata']
    assert metadata_call['filepath'] == 'output.png'
    assert metadata_call['saving_color_space'] == saving_color_space
    assert metadata_call['saving_cctf_encoding'] is saving_cctf_encoding

    saved_kwargs = captured['saved_kwargs']
    assert saved_kwargs['color_space'] == saving_color_space
    assert saved_kwargs['cctf_encoding'] is saving_cctf_encoding


def test_set_or_add_output_layer_records_hdr_scene_sidecar(monkeypatch) -> None:
    controller = GuiController(viewer=object(), widgets=object())
    output_layer = FakeLayer(np.zeros((1, 1, 3), dtype=np.uint8), name='output')
    hdr_scene_energy = SimpleNamespace(scene_luminance=np.array([[0.8]], dtype=np.float32))

    monkeypatch.setattr(controller, '_output_layer', lambda: output_layer)
    controller._layers = SimpleNamespace(set_or_add_output_layer=lambda *args, **kwargs: None)

    controller._set_or_add_output_layer(
        np.zeros((1, 1, 3), dtype=np.uint8),
        float_image=np.ones((1, 1, 3), dtype=np.float32),
        output_color_space='Display P3',
        output_cctf_encoding=False,
        use_display_transform=False,
        hdr_scene_energy=hdr_scene_energy,
    )

    assert output_layer.metadata[controller_module.OUTPUT_HDR_SCENE_ENERGY_KEY] is hdr_scene_energy


def test_save_output_layer_materializes_lazy_export_source_on_demand(monkeypatch) -> None:
    class LazyExportSource:
        def __init__(self) -> None:
            self.array_calls = 0

        def __array__(self, dtype=None):
            self.array_calls += 1
            array = np.full((2, 2, 3), 0.5, dtype=np.float64)
            if dtype is not None:
                return np.asarray(array, dtype=dtype)
            return array

    export_source = LazyExportSource()
    phase_timings: dict[str, float] = {}
    output_layer = FakeLayer(
        np.full((2, 2, 3), 127, dtype=np.uint8),
        metadata={
            OUTPUT_FLOAT_DATA_KEY: export_source,
            OUTPUT_COLOR_SPACE_KEY: 'sRGB',
            OUTPUT_CCTF_ENCODING_KEY: True,
            OUTPUT_DISPLAY_TRANSFORM_KEY: False,
            OUTPUT_PHASE_TIMINGS_KEY: phase_timings,
        },
    )
    controller = GuiController(viewer=object(), widgets=object())
    captured: dict[str, object] = {}
    gui_state = make_test_controller_gui_state()
    gui_state.simulation.workflow.saving_color_space = 'sRGB'
    gui_state.simulation.workflow.saving_cctf_encoding = True

    _configure_save_output(monkeypatch, controller, output_layer, gui_state, captured)
    _capture_saved_output(monkeypatch, captured)
    monkeypatch.setattr(
        controller_module.colour,
        'RGB_to_RGB',
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('matching export settings should not convert')),
    )

    controller.save_output_layer()

    assert export_source.array_calls == 1
    saved_path, saved_image = captured['saved']
    assert saved_path == 'output.png'
    assert saved_image.dtype == np.float32
    np.testing.assert_allclose(saved_image, np.full((2, 2, 3), 0.5, dtype=np.float32))
    assert phase_timings['gui.export_materialize'] >= 0.0


def test_save_output_layer_ignores_hdr_settings_for_standard_png(monkeypatch) -> None:
    float_image = np.full((1, 2, 3), 0.8, dtype=np.float32)
    output_layer = _make_output_layer(
        float_image,
        output_color_space='Display P3',
        output_cctf_encoding=False,
    )
    output_layer.metadata[controller_module.OUTPUT_HDR_SCENE_ENERGY_KEY] = SimpleNamespace(
        scene_luminance=np.array([[0.8, 4.0]], dtype=np.float32),
        scene_rgb=np.repeat(float_image, 1, axis=0),
    )
    controller = GuiController(viewer=object(), widgets=object())
    captured: dict[str, object] = {}
    gui_state = make_test_controller_gui_state()
    gui_state.hdr.hdr_heic_gain_map_enabled = True
    gui_state.hdr.hdr_mapping_mode = 'paper'
    gui_state.simulation.workflow.saving_color_space = 'Display P3'
    gui_state.simulation.workflow.saving_cctf_encoding = False

    _configure_save_output(monkeypatch, controller, output_layer, gui_state, captured)
    _capture_saved_output(monkeypatch, captured)

    controller.save_output_layer()

    assert 'hdr_mapping_kwargs' not in captured['saved_kwargs']
    assert 'scene_luminance' not in captured['saved_kwargs']
    assert 'scene_rgb' not in captured['saved_kwargs']


def test_save_output_layer_rejects_heic_when_hdr_gain_map_disabled(monkeypatch) -> None:
    float_image = np.full((1, 2, 3), 0.8, dtype=np.float32)
    output_layer = _make_output_layer(
        float_image,
        output_color_space='Display P3',
        output_cctf_encoding=False,
    )
    controller = GuiController(viewer=object(), widgets=object())
    controller._current_input_image = float_image
    controller._current_input_path = "input.jpg"
    captured: dict[str, object] = {}
    gui_state = make_test_controller_gui_state()
    gui_state.hdr.hdr_heic_gain_map_enabled = False
    gui_state.simulation.workflow.saving_color_space = 'Display P3'
    gui_state.simulation.workflow.saving_cctf_encoding = False

    _configure_save_output(monkeypatch, controller, output_layer, gui_state, captured)
    monkeypatch.setattr(
        controller_module.QFileDialog,
        'getSaveFileName',
        staticmethod(lambda *args, **kwargs: ('output.heic', 'Images (*.heic)')),
    )
    monkeypatch.setattr(
        controller_module.QMessageBox,
        'warning',
        staticmethod(lambda parent, title, message: captured.setdefault('warning', (title, message))),
    )
    _capture_saved_output(monkeypatch, captured)
    monkeypatch.setattr(
        controller_module,
        'read_image_metadata',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("HEIC metadata copy should not run")),
    )

    controller.save_output_layer()

    assert 'saved' not in captured
    title, message = captured['warning']
    assert title == 'Save output'
    assert 'Enable HDR HEIC gain map export' in message


def test_save_output_layer_passes_paper_hdr_mode_when_heic_gain_map_enabled(monkeypatch) -> None:
    float_image = np.full((1, 2, 3), 1.4, dtype=np.float32)
    output_layer = _make_output_layer(
        float_image,
        output_color_space='Display P3',
        output_cctf_encoding=False,
    )
    controller = GuiController(viewer=object(), widgets=object())
    controller._current_input_image = float_image
    captured: dict[str, object] = {}
    gui_state = make_test_controller_gui_state()
    gui_state.hdr.hdr_heic_gain_map_enabled = True
    gui_state.hdr.hdr_mapping_mode = 'paper'
    gui_state.hdr.hdr_peak_headroom = 5.0
    gui_state.hdr.gain_map_mode = 'luma'
    gui_state.hdr.heic_quality = 0.91
    gui_state.simulation.workflow.saving_color_space = 'Display P3'
    gui_state.simulation.workflow.saving_cctf_encoding = False

    _configure_save_output(monkeypatch, controller, output_layer, gui_state, captured)
    monkeypatch.setattr(
        controller_module.QFileDialog,
        'getSaveFileName',
        staticmethod(lambda *args, **kwargs: ('output.heic', 'Images (*.heic)')),
    )
    _capture_saved_output(monkeypatch, captured)

    from spektrafilm.hdr import routemaster_export
    def fake_export_hdr_heic_from_simulator(
        simulator, image, filename, *, hdr_mode, config, color_space, quality, gain_map_mode, master=None
    ):
        captured['heic_export'] = {
            'hdr_mode': hdr_mode,
            'config': config,
            'color_space': color_space,
            'quality': quality,
            'gain_map_mode': gain_map_mode,
            'master': master,
        }
        return (str(filename),)

    monkeypatch.setattr(
        routemaster_export,
        'export_hdr_heic_from_simulator',
        fake_export_hdr_heic_from_simulator,
    )

    controller.save_output_layer()

    heic_export = captured['heic_export']
    assert heic_export['hdr_mode'] == 'paper'
    assert heic_export['color_space'] == 'Display P3'
    assert heic_export['quality'] == 0.91
    assert heic_export['gain_map_mode'] == 'luma'
    assert 'metadata' not in captured
    assert 'HEIC/HEIF source metadata copy is not supported' in captured['status']

    config = heic_export['config']
    assert config.max_headroom == 5.0
    assert config.gain_map_mode == 'luma'


def test_save_output_layer_passes_paper_hdr_config(monkeypatch) -> None:
    float_image = np.full((1, 2, 3), 1.4, dtype=np.float32)
    output_layer = _make_output_layer(
        float_image,
        output_color_space='Display P3',
        output_cctf_encoding=False,
    )
    controller = GuiController(viewer=object(), widgets=object())
    controller._current_input_image = float_image
    captured: dict[str, object] = {}
    gui_state = make_test_controller_gui_state()
    gui_state.hdr.hdr_heic_gain_map_enabled = True
    gui_state.hdr.hdr_mapping_mode = 'paper'
    gui_state.hdr.hdr_diffuse_white_target = 0.9
    gui_state.hdr.hdr_output_diffuse_white = 1.25
    gui_state.hdr.hdr_peak_headroom = 6.0
    gui_state.hdr.gain_map_mode = 'rgb'
    gui_state.hdr.heic_quality = 0.95
    gui_state.simulation.workflow.saving_color_space = 'Display P3'
    gui_state.simulation.workflow.saving_cctf_encoding = False

    _configure_save_output(monkeypatch, controller, output_layer, gui_state, captured)
    monkeypatch.setattr(
        controller_module.QFileDialog,
        'getSaveFileName',
        staticmethod(lambda *args, **kwargs: ('output.heic', 'Images (*.heic)')),
    )
    _capture_saved_output(monkeypatch, captured)

    from spektrafilm.hdr import routemaster_export
    def fake_export_hdr_heic_from_simulator(
        simulator, image, filename, *, hdr_mode, config, color_space, quality, gain_map_mode, master=None
    ):
        captured['heic_export'] = {
            'hdr_mode': hdr_mode,
            'config': config,
            'color_space': color_space,
            'quality': quality,
            'gain_map_mode': gain_map_mode,
            'master': master,
        }
        return (str(filename),)

    monkeypatch.setattr(
        routemaster_export,
        'export_hdr_heic_from_simulator',
        fake_export_hdr_heic_from_simulator,
    )

    controller.save_output_layer()

    heic_export = captured['heic_export']
    assert heic_export['hdr_mode'] == 'paper'
    assert heic_export['color_space'] == 'Display P3'

    config = heic_export['config']
    assert config.max_headroom == 6.0
    assert config.paper_white == 0.9
    assert config.diffuse_white_scene_anchor == 0.9
    assert config.output_diffuse_white == 1.25
    assert config.gain_map_mode == 'rgb'


def test_save_output_layer_reuses_route_master_from_scan(monkeypatch) -> None:
    float_image = np.full((1, 2, 3), 1.4, dtype=np.float32)
    route_master = SimpleNamespace(mode='paper')
    output_layer = _make_output_layer(
        float_image,
        output_color_space='Display P3',
        output_cctf_encoding=False,
    )
    output_layer.metadata[OUTPUT_ROUTE_MASTER_KEY] = route_master
    controller = GuiController(viewer=object(), widgets=object())
    controller._current_input_image = float_image
    captured: dict[str, object] = {}
    gui_state = make_test_controller_gui_state()
    gui_state.hdr.hdr_heic_gain_map_enabled = True
    gui_state.hdr.hdr_mapping_mode = 'paper'
    gui_state.simulation.workflow.saving_color_space = 'Display P3'
    gui_state.simulation.workflow.saving_cctf_encoding = False

    _configure_save_output(monkeypatch, controller, output_layer, gui_state, captured)
    monkeypatch.setattr(
        controller_module.QFileDialog,
        'getSaveFileName',
        staticmethod(lambda *args, **kwargs: ('output.heic', 'Images (*.heic)')),
    )
    _capture_saved_output(monkeypatch, captured)

    from spektrafilm.hdr import routemaster_export

    def fake_export_hdr_heic_from_simulator(
        simulator, image, filename, *, hdr_mode, config, color_space, quality, gain_map_mode, master=None
    ):
        captured['heic_export'] = {
            'hdr_mode': hdr_mode,
            'master': master,
        }
        return (str(filename),)

    monkeypatch.setattr(
        routemaster_export,
        'export_hdr_heic_from_simulator',
        fake_export_hdr_heic_from_simulator,
    )

    controller.save_output_layer()

    assert captured['heic_export']['hdr_mode'] == 'paper'
    assert captured['heic_export']['master'] is route_master


def test_save_output_layer_ignores_cached_route_master_when_mode_differs(monkeypatch) -> None:
    float_image = np.full((1, 2, 3), 1.4, dtype=np.float32)
    route_master = SimpleNamespace(mode='light_table')
    output_layer = _make_output_layer(
        float_image,
        output_color_space='Display P3',
        output_cctf_encoding=False,
    )
    output_layer.metadata[OUTPUT_ROUTE_MASTER_KEY] = route_master
    controller = GuiController(viewer=object(), widgets=object())
    controller._current_input_image = float_image
    captured: dict[str, object] = {}
    gui_state = make_test_controller_gui_state()
    gui_state.hdr.hdr_heic_gain_map_enabled = True
    gui_state.hdr.hdr_mapping_mode = 'paper'
    gui_state.simulation.workflow.saving_color_space = 'Display P3'
    gui_state.simulation.workflow.saving_cctf_encoding = False

    _configure_save_output(monkeypatch, controller, output_layer, gui_state, captured)
    monkeypatch.setattr(
        controller_module.QFileDialog,
        'getSaveFileName',
        staticmethod(lambda *args, **kwargs: ('output.heic', 'Images (*.heic)')),
    )
    _capture_saved_output(monkeypatch, captured)

    from spektrafilm.hdr import routemaster_export

    def fake_export_hdr_heic_from_simulator(
        simulator, image, filename, *, hdr_mode, config, color_space, quality, gain_map_mode, master=None
    ):
        captured['heic_export'] = {
            'hdr_mode': hdr_mode,
            'master': master,
        }
        return (str(filename),)

    monkeypatch.setattr(
        routemaster_export,
        'export_hdr_heic_from_simulator',
        fake_export_hdr_heic_from_simulator,
    )

    controller.save_output_layer()

    assert captured['heic_export']['hdr_mode'] == 'paper'
    assert captured['heic_export']['master'] is None


@pytest.mark.parametrize(
    ("field", "value", "expected_message"),
    [
        ("preserve_sdr_base", False, "preserve_sdr_base=False is not supported"),
        ("hdr_scene_source", "embedded_scene_rgb", "unknown HDR scene source"),
        ("hdr_headroom_mode", "modern_recovery_peak_budget", "content_percentile headroom mode"),
    ],
)
def test_save_output_layer_rejects_unsupported_routemaster_hdr_settings(
    monkeypatch,
    field: str,
    value: object,
    expected_message: str,
) -> None:
    float_image = np.full((1, 2, 3), 1.4, dtype=np.float32)
    output_layer = _make_output_layer(
        float_image,
        output_color_space='Display P3',
        output_cctf_encoding=False,
    )
    controller = GuiController(viewer=object(), widgets=object())
    controller._current_input_image = float_image
    captured: dict[str, object] = {}
    gui_state = make_test_controller_gui_state()
    gui_state.hdr.hdr_heic_gain_map_enabled = True
    gui_state.hdr.hdr_mapping_mode = 'paper'
    setattr(gui_state.hdr, field, value)
    gui_state.simulation.workflow.saving_color_space = 'Display P3'
    gui_state.simulation.workflow.saving_cctf_encoding = False

    _configure_save_output(monkeypatch, controller, output_layer, gui_state, captured)
    monkeypatch.setattr(
        controller_module.QFileDialog,
        'getSaveFileName',
        staticmethod(lambda *args, **kwargs: ('output.heic', 'Images (*.heic)')),
    )
    monkeypatch.setattr(
        controller_module.QMessageBox,
        'critical',
        staticmethod(lambda parent, title, message: captured.setdefault('critical', (title, message))),
    )

    from spektrafilm.hdr import routemaster_export

    monkeypatch.setattr(
        routemaster_export,
        'export_hdr_heic_from_simulator',
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("HDR export should not run")),
    )

    controller.save_output_layer()

    assert 'saved' not in captured
    title, message = captured['critical']
    assert title == 'Save output'
    assert expected_message in message


def test_save_output_layer_passes_light_table_hdr_mode(monkeypatch) -> None:
    float_image = np.full((1, 2, 3), 1.4, dtype=np.float32)
    output_layer = _make_output_layer(
        float_image,
        output_color_space='Display P3',
        output_cctf_encoding=False,
    )
    controller = GuiController(viewer=object(), widgets=object())
    controller._current_input_image = float_image
    captured: dict[str, object] = {}
    gui_state = make_test_controller_gui_state()
    gui_state.hdr.hdr_heic_gain_map_enabled = True
    gui_state.hdr.hdr_mapping_mode = 'light_table'
    gui_state.simulation.workflow.saving_color_space = 'Display P3'
    gui_state.simulation.workflow.saving_cctf_encoding = False

    _configure_save_output(monkeypatch, controller, output_layer, gui_state, captured)
    monkeypatch.setattr(
        controller_module.QFileDialog,
        'getSaveFileName',
        staticmethod(lambda *args, **kwargs: ('output.heic', 'Images (*.heic)')),
    )
    _capture_saved_output(monkeypatch, captured)

    from spektrafilm.hdr import routemaster_export
    def fake_export_hdr_heic_from_simulator(
        simulator, image, filename, *, hdr_mode, config, color_space, quality, gain_map_mode, master=None
    ):
        captured['heic_export'] = {
            'hdr_mode': hdr_mode,
            'config': config,
            'color_space': color_space,
            'quality': quality,
            'gain_map_mode': gain_map_mode,
            'master': master,
        }
        return (str(filename),)

    monkeypatch.setattr(
        routemaster_export,
        'export_hdr_heic_from_simulator',
        fake_export_hdr_heic_from_simulator,
    )

    controller.save_output_layer()

    heic_export = captured['heic_export']
    assert heic_export['hdr_mode'] == 'light_table'
    assert heic_export['color_space'] == 'Display P3'


def test_save_output_layer_rejects_heic_without_input_image(monkeypatch) -> None:
    float_image = np.full((1, 2, 3), 1.4, dtype=np.float32)
    output_layer = _make_output_layer(
        float_image,
        output_color_space='Display P3',
        output_cctf_encoding=False,
    )
    controller = GuiController(viewer=object(), widgets=object())
    captured: dict[str, object] = {}
    gui_state = make_test_controller_gui_state()
    gui_state.hdr.hdr_heic_gain_map_enabled = True
    gui_state.hdr.hdr_mapping_mode = 'paper'
    gui_state.simulation.workflow.saving_color_space = 'Display P3'
    gui_state.simulation.workflow.saving_cctf_encoding = False

    _configure_save_output(monkeypatch, controller, output_layer, gui_state, captured)
    monkeypatch.setattr(
        controller_module.QFileDialog,
        'getSaveFileName',
        staticmethod(lambda *args, **kwargs: ('output.heic', 'Images (*.heic)')),
    )
    monkeypatch.setattr(
        controller_module.QMessageBox,
        'warning',
        staticmethod(lambda parent, title, message: captured.setdefault('warning', (title, message))),
    )
    _capture_saved_output(monkeypatch, captured)

    controller.save_output_layer()

    assert 'saved' not in captured
    title, message = captured['warning']
    assert title == 'Save output'
    assert 'No input image available for HDR HEIC export' in message


@pytest.mark.parametrize(
    ('image_data', 'padding_pixels', 'expected_shape', 'expected_center', 'expected_corner'),
    [
        (
            np.array([[[0.0, 0.5, 1.0]]], dtype=np.float32),
            0.0,
            (1, 1, 3),
            np.array([0, 127, 255], dtype=np.uint8),
            None,
        ),
        (
            np.array([[[0.25, 0.5, 0.75]]], dtype=np.float32),
            1.0,
            (1, 1, 3),
            np.array([63, 127, 191], dtype=np.uint8),
            None,
        ),
    ],
    ids=['simple-preview', 'padding-ignored'],
)
def test_prepare_output_display_image_without_transform(
    image_data: np.ndarray,
    padding_pixels: float,
    expected_shape: tuple[int, int, int],
    expected_center: np.ndarray,
    expected_corner: np.ndarray | None,
) -> None:
    controller = GuiController(viewer=object(), widgets=object())

    preview, status = controller._prepare_output_display_image(
        image_data,
        output_color_space='sRGB',
        use_display_transform=False,
        padding_pixels=padding_pixels,
    )

    _assert_preview_conversion(
        preview,
        status,
        expected_shape=expected_shape,
        expected_status='Display transform: disabled',
        expected_center=expected_center,
        expected_corner=expected_corner,
    )


def test_prepare_output_display_image_uses_imagecms_transform(monkeypatch) -> None:
    controller = GuiController(viewer=object(), widgets=object())
    image_data = np.array([[[0.2, 0.4, 0.6]]], dtype=np.float32)
    captured: dict[str, object] = {}

    class FakePILImage:
        def __init__(self, array: np.ndarray):
            self.array = array

    monkeypatch.setattr(controller_module.ImageCms, 'get_display_profile', lambda: object())
    monkeypatch.setattr(controller_module.ImageCms, 'getProfileName', lambda profile: 'Studio Display ICC\x00')
    monkeypatch.setattr(controller_module.colour, 'RGB_to_RGB', lambda *args, **kwargs: np.full((1, 1, 3), 0.5, dtype=np.float32))
    monkeypatch.setattr(controller_module.ImageCms, 'createProfile', lambda name: f'profile:{name}')
    monkeypatch.setattr(
        controller_module.PILImage,
        'fromarray',
        lambda array, mode='RGB': captured.setdefault('source_image', FakePILImage(array.copy())),
    )

    def fake_profile_to_profile(source_image, source_profile, display_profile, outputMode='RGB'):
        captured['profile_to_profile'] = {
            'source_profile': source_profile,
            'display_profile': display_profile,
            'output_mode': outputMode,
            'image_data': source_image.array.copy(),
        }
        return np.full((1, 1, 3), 64, dtype=np.uint8)

    monkeypatch.setattr(controller_module.ImageCms, 'profileToProfile', fake_profile_to_profile)

    preview, status = controller._prepare_output_display_image(
        image_data,
        output_color_space='Display P3',
        use_display_transform=True,
    )

    np.testing.assert_array_equal(preview, np.full((1, 1, 3), 64, dtype=np.uint8))
    assert status == 'Display transform: active (Studio Display ICC; SDR 8-bit preview)'
    assert captured['profile_to_profile']['source_profile'] is not None
    assert captured['profile_to_profile']['output_mode'] == 'RGB'
    np.testing.assert_array_equal(
        captured['profile_to_profile']['image_data'],
        np.array([[[51, 102, 153]]], dtype=np.uint8),
    )


def test_prepare_output_display_image_reports_missing_display_profile(monkeypatch) -> None:
    controller = GuiController(viewer=object(), widgets=object())
    image_data = np.array([[[0.2, 0.4, 0.6]]], dtype=np.float32)

    monkeypatch.setattr(controller_module.ImageCms, 'get_display_profile', lambda: None)

    preview, status = controller._prepare_output_display_image(
        image_data,
        output_color_space='Display P3',
        use_display_transform=True,
    )

    _assert_fallback_preview(preview, status, expected_status='Display transform: no display profile, using raw preview')


def test_display_profile_helpers_use_explicit_macos_fallback(monkeypatch) -> None:
    icc_bytes = controller_module.ImageCms.ImageCmsProfile(
        controller_module.ImageCms.createProfile('sRGB')
    ).tobytes()

    monkeypatch.setattr(controller_module.ImageCms, 'get_display_profile', lambda: None)
    monkeypatch.setattr(controller_module.runtime, '_mac_display_profile_fallback_enabled', lambda: True)
    monkeypatch.setattr(controller_module.runtime, '_get_mac_display_profile_bytes', lambda: icc_bytes)

    assert controller_module.runtime.display_profile_available(imagecms_module=controller_module.ImageCms) is True
    profile, profile_name = controller_module.runtime.display_profile_details(imagecms_module=controller_module.ImageCms)

    assert profile is not None
    assert profile_name is not None
    assert profile_name.strip()


def test_prepare_output_display_image_uses_explicit_macos_fallback_profile(monkeypatch) -> None:
    controller = GuiController(viewer=object(), widgets=object())
    image_data = np.array([[[0.2, 0.4, 0.6]]], dtype=np.float32)
    captured: dict[str, object] = {}
    icc_bytes = controller_module.ImageCms.ImageCmsProfile(
        controller_module.ImageCms.createProfile('sRGB')
    ).tobytes()

    class FakePILImage:
        def __init__(self, array: np.ndarray):
            self.array = array

    monkeypatch.setattr(controller_module.ImageCms, 'get_display_profile', lambda: None)
    monkeypatch.setattr(controller_module.runtime, '_mac_display_profile_fallback_enabled', lambda: True)
    monkeypatch.setattr(controller_module.runtime, '_get_mac_display_profile_bytes', lambda: icc_bytes)
    monkeypatch.setattr(controller_module.colour, 'RGB_to_RGB', lambda *args, **kwargs: np.full((1, 1, 3), 0.5, dtype=np.float32))
    monkeypatch.setattr(controller_module.ImageCms, 'createProfile', lambda name: f'profile:{name}')
    monkeypatch.setattr(
        controller_module.PILImage,
        'fromarray',
        lambda array, mode='RGB': captured.setdefault('source_image', FakePILImage(array.copy())),
    )

    def fake_profile_to_profile(source_image, source_profile, display_profile, outputMode='RGB'):
        captured['profile_to_profile'] = {
            'source_profile': source_profile,
            'display_profile': display_profile,
            'output_mode': outputMode,
            'image_data': source_image.array.copy(),
        }
        return np.full((1, 1, 3), 64, dtype=np.uint8)

    monkeypatch.setattr(controller_module.ImageCms, 'profileToProfile', fake_profile_to_profile)

    preview, status = controller._prepare_output_display_image(
        image_data,
        output_color_space='Display P3',
        use_display_transform=True,
    )

    np.testing.assert_array_equal(preview, np.full((1, 1, 3), 64, dtype=np.uint8))
    assert status.startswith('Display transform: active (')
    assert captured['profile_to_profile']['display_profile'] is not None
    assert captured['profile_to_profile']['output_mode'] == 'RGB'


def test_display_profile_fallback_missing_bytes_preserves_missing_profile(monkeypatch) -> None:
    controller = GuiController(viewer=object(), widgets=object())
    image_data = np.array([[[0.2, 0.4, 0.6]]], dtype=np.float32)

    monkeypatch.setattr(controller_module.ImageCms, 'get_display_profile', lambda: None)
    monkeypatch.setattr(controller_module.runtime, '_mac_display_profile_fallback_enabled', lambda: True)
    monkeypatch.setattr(controller_module.runtime, '_get_mac_display_profile_bytes', lambda: None)

    assert controller_module.runtime.display_profile_available(imagecms_module=controller_module.ImageCms) is False

    preview, status = controller._prepare_output_display_image(
        image_data,
        output_color_space='Display P3',
        use_display_transform=True,
    )

    _assert_fallback_preview(preview, status, expected_status='Display transform: no display profile, using raw preview')


def test_display_profile_fallback_bad_icc_bytes_preserves_missing_profile(monkeypatch) -> None:
    monkeypatch.setattr(controller_module.ImageCms, 'get_display_profile', lambda: None)
    monkeypatch.setattr(controller_module.runtime, '_mac_display_profile_fallback_enabled', lambda: True)
    monkeypatch.setattr(controller_module.runtime, '_get_mac_display_profile_bytes', lambda: b'not an icc profile')

    assert controller_module.runtime.display_profile_available(imagecms_module=controller_module.ImageCms) is False
    assert controller_module.runtime.display_profile_details(imagecms_module=controller_module.ImageCms) == (None, None)


def test_prepare_output_display_image_reports_transform_failure(monkeypatch) -> None:
    controller = GuiController(viewer=object(), widgets=object())
    image_data = np.array([[[0.2, 0.4, 0.6]]], dtype=np.float32)

    monkeypatch.setattr(controller_module.ImageCms, 'get_display_profile', lambda: object())
    monkeypatch.setattr(controller_module.colour, 'RGB_to_RGB', lambda *args, **kwargs: np.full((1, 1, 3), 0.5, dtype=np.float32))
    monkeypatch.setattr(controller_module.ImageCms, 'createProfile', lambda name: f'profile:{name}')
    monkeypatch.setattr(controller_module.PILImage, 'fromarray', lambda array, mode='RGB': object())

    def raise_transform_error(*args, **kwargs):
        raise controller_module.ImageCms.PyCMSError('bad transform')

    monkeypatch.setattr(controller_module.ImageCms, 'profileToProfile', raise_transform_error)

    preview, status = controller._prepare_output_display_image(
        image_data,
        output_color_space='Display P3',
        use_display_transform=True,
    )

    _assert_fallback_preview(preview, status, expected_status='Display transform: transform failed, using raw preview')


@pytest.mark.parametrize(
    ('enabled', 'display_profile', 'profile_name', 'expected_status'),
    [
        (False, None, None, 'Display transform: disabled'),
        (True, object(), 'Adobe RGB Monitor\x00', 'Display transform: display profile found (Adobe RGB Monitor)'),
    ],
    ids=['disabled', 'profile-found'],
)
def test_report_display_transform_status_messages(
    monkeypatch,
    enabled: bool,
    display_profile: object | None,
    profile_name: str | None,
    expected_status: str,
) -> None:
    controller, _ = _make_display_transform_controller(with_toggle=False)
    captured = _capture_status(monkeypatch)

    monkeypatch.setattr(controller_module.ImageCms, 'get_display_profile', lambda: display_profile)
    if profile_name is not None:
        monkeypatch.setattr(controller_module.ImageCms, 'getProfileName', lambda profile: profile_name)

    controller.report_display_transform_status(enabled)

    assert captured['status'] == expected_status


def test_set_gray_18_canvas_enabled_updates_napari_background(monkeypatch) -> None:
    controller = GuiController(viewer=object(), widgets=object())
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        controller_module,
        'set_canvas_background',
        lambda viewer, *, gray_18_canvas: captured.setdefault('canvas', (viewer, gray_18_canvas)),
    )

    controller.set_gray_18_canvas_enabled(True)

    assert captured['canvas'] == (controller._viewer, True)


def test_report_display_transform_status_missing_profile(monkeypatch) -> None:
    controller, toggle = _make_display_transform_controller(with_toggle=True)
    captured = _capture_status(monkeypatch)

    monkeypatch.setattr(controller_module.ImageCms, 'get_display_profile', lambda: None)

    controller.report_display_transform_status(True)

    assert captured['status'] == 'Display transform unavailable: no display profile detected, disabled'
    assert toggle.checked is False


def test_sync_display_transform_availability_unchecks_when_profile_missing(monkeypatch) -> None:
    controller, toggle = _make_display_transform_controller(with_toggle=True)

    monkeypatch.setattr(controller_module.ImageCms, 'get_display_profile', lambda: None)

    available = controller.sync_display_transform_availability(report_status=False)

    assert available is False
    assert toggle.checked is False
