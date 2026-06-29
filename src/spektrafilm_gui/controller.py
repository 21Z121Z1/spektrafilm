from __future__ import annotations

from dataclasses import asdict, is_dataclass
import hashlib
from importlib import import_module
import json
from pathlib import Path
import time
from typing import TYPE_CHECKING

import numpy as np
from qtpy import QtCore, QtWidgets

from spektrafilm_gui import controller_persistence as persistence_actions
from spektrafilm_gui import controller_profile_sync as profile_sync
from spektrafilm_gui import controller_runtime as runtime
from spektrafilm_gui.controller_layers import (
    INPUT_LAYER_NAME,
    INPUT_PREVIEW_LAYER_NAME,
    ViewerLayerService,
)
from spektrafilm_gui.hdr_settings import hdr_projection_config_from_settings, normalize_hdr_mapping_mode
from spektrafilm_gui.persistence import (
    clear_saved_default_gui_state,
    load_dialog_dir,
    load_gui_state_from_path,
    save_default_gui_state,
    save_dialog_dir,
    save_gui_state_to_path,
)
from spektrafilm_gui.state import PROJECT_DEFAULT_GUI_STATE, digest_after_selection, gui_state_from_params
from spektrafilm_gui.napari_layout import dialog_parent, reset_viewer_camera, set_canvas_background, set_status
from spektrafilm_gui.params_mapper import build_params_from_state
from spektrafilm_gui.state_bridge import apply_gui_state, collect_gui_state
from spektrafilm_gui.widgets import WidgetBundle

OUTPUT_FLOAT_DATA_KEY = 'pipeline_float_output'
OUTPUT_COLOR_SPACE_KEY = 'pipeline_output_color_space'
OUTPUT_CCTF_ENCODING_KEY = 'pipeline_output_cctf_encoding'
OUTPUT_DISPLAY_TRANSFORM_KEY = 'pipeline_use_display_transform'
OUTPUT_HDR_SCENE_ENERGY_KEY = 'pipeline_hdr_scene_energy'
OUTPUT_ROUTE_MASTER_KEY = 'pipeline_route_master'
OUTPUT_ROUTE_MASTER_SIGNATURE_KEY = 'pipeline_route_master_signature'
OUTPUT_PHASE_TIMINGS_KEY = 'pipeline_phase_timings'
PROFILE_SYNC_SECTION_NAMES = profile_sync.PROFILE_SYNC_SECTION_NAMES
if TYPE_CHECKING:
    import napari
    from napari.layers import Image as NapariImageLayer


QThreadPool = getattr(QtCore, 'QThreadPool')
QTimer = getattr(QtCore, 'QTimer')
QFileDialog = QtWidgets.QFileDialog
QMessageBox = QtWidgets.QMessageBox
SimulationRequest = runtime.SimulationRequest
SimulationResult = runtime.SimulationResult
STARTUP_PREVIEW_ASPECT_RATIO = (3, 2)


class _DirMemoryDialog:
    """Wraps QFileDialog to open in the last-used directory via QSettings."""

    def __init__(self, key: str) -> None:
        self._key = key

    def get_save_file_name(self, parent, title, filename, file_filter):
        last_dir = load_dialog_dir(self._key)
        initial = str(Path(last_dir) / Path(filename).name) if last_dir else filename
        path, fmt = QFileDialog.getSaveFileName(parent, title, initial, file_filter)
        if path:
            save_dialog_dir(self._key, str(Path(path).parent))
        return path, fmt

    def get_open_file_name(self, parent, title, _initial, file_filter):
        path, fmt = QFileDialog.getOpenFileName(
            parent, title, load_dialog_dir(self._key), file_filter
        )
        if path:
            save_dialog_dir(self._key, str(Path(path).parent))
        return path, fmt


class _LazyModuleProxy:
    def __init__(self, loader):
        self._loader = loader
        self._module = None

    def _load(self):
        if self._module is None:
            self._module = self._loader()
        return self._module

    def __getattr__(self, name: str):
        return getattr(self._load(), name)


def _import_colour_module():
    return import_module('colour')


def _import_pil_image_module():
    return import_module('PIL.Image')


def _import_imagecms_module():
    return import_module('PIL.ImageCms')


def runtime_simulator(*args, **kwargs):
    return import_module('spektrafilm.runtime.api').Simulator(*args, **kwargs)


def digest_params(*args, **kwargs):
    return import_module('spektrafilm.runtime.api').digest_params(*args, **kwargs)


def load_image_oiio(*args, **kwargs):
    return import_module('spektrafilm.utils.io').load_image_oiio(*args, **kwargs)


def save_image_oiio(*args, **kwargs):
    return import_module("spektrafilm.utils.io").save_image_oiio(*args, **kwargs)


def sample_runtime_film_scan_curve_profile(*args, **kwargs):
    module = import_module("spektrafilm.utils.hdr_curve_profiles")
    sample_or_profile = module.sample_runtime_film_scan_curve_profile(*args, **kwargs)
    if isinstance(sample_or_profile, dict):
        return module.curve_profile_from_sample(sample_or_profile)
    return sample_or_profile


def read_image_metadata(*args, **kwargs):
    return import_module("spektrafilm.utils.io").read_image_metadata(*args, **kwargs)


def write_image_metadata(*args, **kwargs):
    return import_module("spektrafilm.utils.io").write_image_metadata(*args, **kwargs)


def load_and_process_raw_file(*args, **kwargs):
    return import_module('spektrafilm.utils.raw_file_processor').load_and_process_raw_file(*args, **kwargs)


def resize_for_preview(*args, **kwargs):
    return import_module('spektrafilm.utils.preview').resize_for_preview(*args, **kwargs)


def _uses_mlx_float32(params) -> bool:
    settings = getattr(params, "settings", None)
    return (
        str(getattr(settings, "compute_backend", "")).lower() == "mlx"
        and str(getattr(settings, "gpu_precision", "")).lower() == "float32"
    )


def _set_backend_materialize_policy_for_mlx_float32(params) -> None:
    settings = getattr(params, "settings", None)
    if settings is None or not _uses_mlx_float32(params):
        return
    if hasattr(settings, "materialize_policy"):
        settings.materialize_policy = "backend"


def _prepare_simulation_input_image(
    image_data: np.ndarray,
    params,
) -> tuple[np.ndarray, dict[str, float], dict[str, int]]:
    prepare_start = time.perf_counter()
    source_array = np.asarray(image_data)
    dtype_start = time.perf_counter()
    if _uses_mlx_float32(params):
        source_for_request = source_array[..., :3]
        image = np.asarray(source_for_request, dtype=np.float32)
    else:
        source_for_request = source_array
        image = np.double(image_data)
    dtype_elapsed = time.perf_counter() - dtype_start
    shares_input_memory = (
        isinstance(image, np.ndarray)
        and isinstance(source_for_request, np.ndarray)
        and np.shares_memory(image, source_for_request)
    )
    phase_timings = {
        'gui.input_prepare': time.perf_counter() - prepare_start,
        'gui.input_dtype_convert': dtype_elapsed,
        'gui.input_copy': 0.0 if shares_input_memory else dtype_elapsed,
    }
    memory_estimates = {
        'gui.input_source_nbytes': runtime.array_nbytes(source_for_request),
        'gui.input_request_nbytes': runtime.array_nbytes(image),
        'gui.input_copy_nbytes': 0 if shares_input_memory else runtime.array_nbytes(image),
    }
    return image, phase_timings, memory_estimates


def _requires_hdr_metadata_for_state(state) -> bool:
    hdr_state = getattr(state, "hdr", None)
    return bool(getattr(hdr_state, "hdr_heic_gain_map_enabled", False))


def _json_stable(value):
    if is_dataclass(value):
        return _json_stable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_stable(val) for key, val in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_json_stable(item) for item in value]
    if isinstance(value, np.ndarray):
        return {
            "shape": tuple(int(dim) for dim in value.shape),
            "dtype": str(value.dtype),
            "min": float(np.nanmin(value)) if value.size else None,
            "max": float(np.nanmax(value)) if value.size else None,
        }
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def _input_image_cache_fingerprint(image: object | None) -> dict[str, object] | None:
    if image is None:
        return None
    arr = np.asarray(image)
    content = np.ascontiguousarray(arr)
    pointer = None
    try:
        pointer = int(arr.__array_interface__["data"][0])
    except (AttributeError, KeyError, TypeError, ValueError):
        pointer = None
    return {
        "shape": tuple(int(dim) for dim in arr.shape),
        "dtype": str(arr.dtype),
        "strides": None if arr.strides is None else tuple(int(v) for v in arr.strides),
        "nbytes": int(arr.nbytes),
        "object_id": int(id(image)),
        "data_pointer": pointer,
        "sha256": hashlib.sha256(memoryview(content).cast("B")).hexdigest(),
    }


def _route_master_cache_signature(
    *,
    input_image: object | None,
    gui_state,
    hdr_mode: str,
    saving_color_space: str,
    saving_cctf_encoding: bool,
) -> str:
    payload = {
        "schema": "spektrafilm.gui.route_master_cache.v1",
        "input": _input_image_cache_fingerprint(input_image),
        "state": _json_stable(gui_state),
        "hdr_mode": str(hdr_mode),
        "saving_color_space": str(saving_color_space),
        "saving_cctf_encoding": bool(saving_cctf_encoding),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _format_hdr_export_diagnostics(diagnostics: dict[str, object]) -> str:
    if not diagnostics:
        return ""
    headroom = diagnostics.get("hdr_headroom")
    try:
        headroom_text = f"{float(headroom):.3g}"
    except (TypeError, ValueError):
        headroom_text = str(headroom)
    positive_negative = diagnostics.get("positive_negative_scan")
    parts = [
        f"mode={diagnostics.get('hdr_mode', 'unknown')}",
        f"route={diagnostics.get('route_kind', 'unknown')}",
        f"profile={diagnostics.get('profile_kind', 'unknown')}",
        f"sdr={diagnostics.get('sdr_base_domain', 'unknown')}",
        f"headroom={headroom_text}",
        f"cached={'yes' if diagnostics.get('cached_route_master') else 'no'}",
    ]
    if positive_negative is not None:
        parts.insert(3, f"positive_negative_scan={'yes' if positive_negative else 'no'}")
    return " HDR export: " + ", ".join(parts)


colour = _LazyModuleProxy(_import_colour_module)
PILImage = _LazyModuleProxy(_import_pil_image_module)
ImageCms = _LazyModuleProxy(_import_imagecms_module)


class GuiController:
    def __init__(self, *, viewer: napari.Viewer, widgets: WidgetBundle):
        self._viewer = viewer
        self._widgets = widgets
        self._layers = ViewerLayerService(
            viewer=viewer,
            output_float_data_key=OUTPUT_FLOAT_DATA_KEY,
            output_color_space_key=OUTPUT_COLOR_SPACE_KEY,
            output_cctf_encoding_key=OUTPUT_CCTF_ENCODING_KEY,
            output_display_transform_key=OUTPUT_DISPLAY_TRANSFORM_KEY,
        )
        self._thread_pool = QThreadPool.globalInstance()
        self._active_simulation_worker: runtime.SimulationWorker | None = None
        self._active_simulation_label: str | None = None
        self._active_export_worker: runtime.HEICExportWorker | None = None
        self._active_export_filepath: str | None = None
        self._runtime_simulator = None
        self._last_runtime_backend_summary: str | None = None
        self._next_runtime_digest_applies_stock_specifics = True
        self._current_input_image: np.ndarray | None = None
        self._current_input_path: str | None = None
        self._current_preview_image: np.ndarray | None = None
        self._auto_preview_scheduled = False
        self._pending_auto_preview = False
        self._active_simulation_reports_status = True

    def show_startup_placeholder(self) -> None:
        if self._white_border_layer() is not None:
            return

        state = collect_gui_state(widgets=self._widgets)
        preview_height = max(int(state.gui_only.display.settings.preview_max_size), 1)
        preview_width = max(
            int(round(preview_height * STARTUP_PREVIEW_ASPECT_RATIO[1] / STARTUP_PREVIEW_ASPECT_RATIO[0])),
            1,
        )
        placeholder_preview = np.zeros((preview_height, preview_width, 3), dtype=np.uint8)
        self._layers.set_or_add_input_preview_layer(
            placeholder_preview,
            watermark_source_size=(preview_height, preview_width),
            white_padding=state.gui_only.display.white_padding,
            hide_output=True,
            set_active=True,
        )
        self._home_input_stack()

    def load_input_image(self, path: str) -> None:
        image = load_image_oiio(path)[..., :3]
        self._current_input_path = path
        self._set_or_add_input_stack(image)
        self._request_auto_preview_if_enabled()

    def load_raw_image(self, path: str) -> None:
        gui_state = collect_gui_state(widgets=self._widgets)
        set_status(self._viewer, "Loading raw...", timeout_ms=0)
        lens_info: dict[str, str] = {}
        try:
            image = load_and_process_raw_file(
                path,
                white_balance=gui_state.gui_only.load_raw.white_balance,
                temperature=gui_state.gui_only.load_raw.temperature,
                tint=gui_state.gui_only.load_raw.tint,
                lens_correction=gui_state.gui_only.load_raw.lens_correction,
                output_colorspace=gui_state.input_image.io.input_color_space,
                output_cctf_encoding=gui_state.input_image.io.input_cctf_decoding,
                lens_info_out=lens_info,
            )
        except (OSError, ValueError) as exc:
            QMessageBox.critical(dialog_parent(self._viewer), 'Load raw', f'Failed to load RAW image.\n\n{exc}')
            set_status(self._viewer, 'Load raw failed')
            return

        self._current_input_path = path
        self._set_or_add_input_stack(image)

        lens_summary = lens_info.get('summary')
        if lens_summary:
            set_status(
                self._viewer,
                f"Loaded raw and applied lens correction: {lens_summary}",
            )
        elif gui_state.gui_only.load_raw.lens_correction:
            set_status(self._viewer, "Loaded raw, lens correction not applied")
        else:
            set_status(self._viewer, "Loaded raw")
        self._request_auto_preview_if_enabled()

    def refresh_preview_cache(self, *_args) -> None:
        input_image = self._current_input_image
        if input_image is None:
            return
        self._update_preview_cache(
            input_image,
            home_input_stack=False,
            hide_output=False,
        )

    def rotate_input_image_clockwise(self) -> None:
        self._rotate_input_image(quarter_turns=-1)

    def rotate_input_image_counterclockwise(self) -> None:
        self._rotate_input_image(quarter_turns=1)

    def _rotate_input_image(self, *, quarter_turns: int) -> None:
        input_image = self._current_input_image
        if input_image is None:
            return

        rotated_image = np.rot90(np.asarray(input_image), k=int(quarter_turns))
        self._update_preview_cache(
            rotated_image,
            home_input_stack=True,
            hide_output=True,
        )
        self._request_auto_preview_if_enabled()

    def apply_profile_defaults(self, _selected_value: str) -> None:
        state = collect_gui_state(widgets=self._widgets)
        if not state.selection.film_stock or not state.selection.print_paper:
            return

        params = build_params_from_state(state)
        synced_state = gui_state_from_params(
            digest_after_selection(params),
            film_stock=state.selection.film_stock,
            print_paper=state.selection.print_paper,
        )
        self._apply_profile_sync_state(synced_state)
        self._next_runtime_digest_applies_stock_specifics = True

    def apply_film_profile_defaults(self, film_stock: str) -> None:
        self.apply_profile_defaults(film_stock)

    def _apply_profile_sync_state(self, synced_state) -> None:
        profile_sync.apply_profile_sync_state(
            widgets=self._widgets,
            synced_state=synced_state,
            profile_sync_section_names=PROFILE_SYNC_SECTION_NAMES,
        )

    def run_preview(self) -> None:
        self._run_preview(report_status=True)

    def _run_preview(self, *, report_status: bool) -> None:
        self._start_simulation(
            source_layer_name=INPUT_PREVIEW_LAYER_NAME,
            mode_label='Preview',
            report_status=report_status,
        )

    def run_scan(self) -> None:
        self._start_simulation(source_layer_name=INPUT_LAYER_NAME, mode_label='Scan')

    def request_auto_preview(self, *_args) -> None:
        if self._auto_preview_scheduled:
            return
        self._auto_preview_scheduled = True
        QTimer.singleShot(0, self._run_scheduled_auto_preview)

    def _request_auto_preview_if_enabled(self) -> None:
        if not self._auto_preview_enabled() or self._current_preview_image is None:
            return
        self.request_auto_preview()

    def report_display_transform_status(self, enabled: bool) -> None:
        if enabled and not self.sync_display_transform_availability(report_status=True):
            return
        set_status(self._viewer, runtime.display_transform_status_message(enabled, imagecms_module=ImageCms))

    def set_gray_18_canvas_enabled(self, enabled: bool) -> None:
        set_canvas_background(self._viewer, gray_18_canvas=enabled)

    def set_output_interpolation_mode(self, mode: str) -> None:
        output_layer = self._output_layer()
        if output_layer is None:
            return
        self._layers.set_output_layer_interpolation(output_layer, mode)

    def sync_display_transform_availability(self, *, report_status: bool) -> bool:
        if runtime.display_profile_available(imagecms_module=ImageCms):
            return True

        self._set_display_transform_checked(False)
        if report_status:
            set_status(self._viewer, 'Display transform unavailable: no display profile detected, disabled')
        return False

    def save_output_layer(self) -> None:
        output_layer = self._output_layer()
        if output_layer is None:
            QMessageBox.warning(dialog_parent(self._viewer), 'Save output', 'Run a simulation before saving the output layer.')
            return

        if self._current_input_path is not None:
            default_name = Path(self._current_input_path).stem + '.jpg'
        else:
            default_name = 'output.jpg'

        filepath, _ = _DirMemoryDialog('save_output').get_save_file_name(
            dialog_parent(self._viewer),
            'Save output image',
            default_name,
            'Images (*.jpg *.jpeg *.png *.tif *.tiff *.exr *.heic *.heif)',
        )
        if not filepath:
            return

        gui_state = collect_gui_state(widgets=self._widgets)
        saving_color_space = gui_state.simulation.workflow.saving_color_space
        saving_cctf_encoding = gui_state.simulation.workflow.saving_cctf_encoding

        suffix = Path(filepath).suffix.lower()
        if suffix in {'.heic', '.heif'}:
            hdr_settings = gui_state.hdr
            if not hdr_settings.hdr_heic_gain_map_enabled:
                QMessageBox.warning(
                    dialog_parent(self._viewer),
                    'Save output',
                    'Enable HDR HEIC gain map export in the HDR Export panel before saving HEIC/HEIF.'
                )
                return

            try:
                from spektrafilm.hdr.routemaster_export import export_hdr_heic_from_simulator

                hdr_mode = normalize_hdr_mapping_mode(hdr_settings.hdr_mapping_mode)
                if hdr_mode == "light_table" and not self._confirm_light_table_hdr_export():
                    set_status(self._viewer, "HDR Light Table export cancelled")
                    return

                current_route_master_signature = None
                if self._current_input_image is not None:
                    current_route_master_signature = _route_master_cache_signature(
                        input_image=self._current_input_image,
                        gui_state=gui_state,
                        hdr_mode=hdr_mode,
                        saving_color_space=saving_color_space,
                        saving_cctf_encoding=saving_cctf_encoding,
                    )

                cached_route_master = output_layer.metadata.get(OUTPUT_ROUTE_MASTER_KEY)
                cached_route_master_signature = output_layer.metadata.get(OUTPUT_ROUTE_MASTER_SIGNATURE_KEY)
                if current_route_master_signature is None:
                    current_route_master_signature = (
                        str(cached_route_master_signature)
                        if cached_route_master_signature is not None
                        else None
                    )
                if (
                    getattr(cached_route_master, "mode", None) != hdr_mode
                    or cached_route_master_signature is None
                    or str(cached_route_master_signature) != str(current_route_master_signature)
                ):
                    cached_route_master = None

                if cached_route_master is None and self._current_input_image is None:
                    QMessageBox.warning(
                        dialog_parent(self._viewer),
                        'Save output',
                        'No input image available for HDR HEIC export. Please load an image first.'
                    )
                    return

                config = hdr_projection_config_from_settings(hdr_settings)

                if cached_route_master is not None:
                    export_request = runtime.HEICExportRequest(
                        simulator=None,
                        image=None,
                        filepath=filepath,
                        hdr_mode=hdr_mode,
                        config=config,
                        color_space=saving_color_space,
                        quality=float(hdr_settings.heic_quality),
                        gain_map_mode=hdr_settings.gain_map_mode,
                        master=cached_route_master,
                    )
                else:
                    params = build_params_from_state(gui_state)
                    apply_stocks_specifics = (
                        self._runtime_simulator is None
                        or self._next_runtime_digest_applies_stock_specifics
                    )
                    digested_params = digest_params(
                        params,
                        apply_stocks_specifics=apply_stocks_specifics,
                    )
                    if self._runtime_simulator is None:
                        self._runtime_simulator = runtime_simulator(digested_params)
                    else:
                        self._runtime_simulator.update_params(digested_params)
                    self._next_runtime_digest_applies_stock_specifics = False

                    export_request = runtime.HEICExportRequest(
                        simulator=self._runtime_simulator,
                        image=self._current_input_image,
                        filepath=filepath,
                        hdr_mode=hdr_mode,
                        config=config,
                        color_space=saving_color_space,
                        quality=float(hdr_settings.heic_quality),
                        gain_map_mode=hdr_settings.gain_map_mode,
                        master=None,
                    )

                worker = runtime.HEICExportWorker(
                    export_request,
                    execute_export=self._execute_heic_export_request,
                )
                worker.signals.finished.connect(self._on_heic_export_finished)
                worker.signals.failed.connect(self._on_heic_export_failed)
                self._active_export_worker = worker
                self._active_export_filepath = filepath
                self._set_simulation_controls_enabled(False)
                set_status(
                    self._viewer,
                    f"Saving HDR HEIC to {Path(filepath).name}...",
                    timeout_ms=0,
                )
                self._thread_pool.start(worker)
            except Exception as exc:
                self._set_simulation_controls_enabled(True)
                QMessageBox.critical(
                    dialog_parent(self._viewer),
                    'Save output',
                    f'Failed to save HDR HEIC output image.\n\n{exc}'
                )
            return

        float_image_data = self._output_layer_float_data()
        if float_image_data is None:
            image_data = runtime.normalized_image_data(np.asarray(output_layer.data)[..., :3])
        else:
            phase_timings = output_layer.metadata.get(OUTPUT_PHASE_TIMINGS_KEY)
            image_data = runtime.materialize_export_image(
                float_image_data,
                phase_timings=phase_timings if isinstance(phase_timings, dict) else None,
            )

        source_color_space, source_cctf_encoding = self._output_layer_render_settings(
            default_color_space=gui_state.simulation.io.output_color_space,
            default_cctf_encoding=True,
        )
        if source_color_space != saving_color_space:
            image_data = colour.RGB_to_RGB(
                image_data,
                source_color_space,
                saving_color_space,
                apply_cctf_decoding=source_cctf_encoding,
                apply_cctf_encoding=saving_cctf_encoding,
            )
        elif source_cctf_encoding != saving_cctf_encoding:
            image_data = colour.RGB_to_RGB(
                image_data,
                source_color_space,
                saving_color_space,
                apply_cctf_decoding=source_cctf_encoding,
                apply_cctf_encoding=saving_cctf_encoding,
            )

        source_metadata = None

        if self._current_input_path is not None:
            source_metadata = read_image_metadata(self._current_input_path)

        try:
            save_kwargs = self._save_output_kwargs(
                filepath,
                gui_state=gui_state,
                output_layer=output_layer,
                saving_color_space=saving_color_space,
                saving_cctf_encoding=saving_cctf_encoding,
            )
            save_image_oiio(filepath, image_data, **save_kwargs)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(dialog_parent(self._viewer), 'Save output', f'Failed to save output image.\n\n{exc}')
            return

        metadata_write_error = None
        try:
            write_image_metadata(
                filepath,
                source_metadata,
                saving_color_space=saving_color_space,
                saving_cctf_encoding=saving_cctf_encoding,
            )
        except Exception as exc:
            metadata_write_error = exc

        if metadata_write_error is not None:
            set_status(
                self._viewer,
                f"Saved output image to {filepath}, but failed to copy metadata: {metadata_write_error}",
            )
        else:
            set_status(self._viewer, f"Saved output image to {filepath}")

    def _save_output_kwargs(
        self,
        filepath: str,
        *,
        gui_state,
        output_layer: NapariImageLayer,
        saving_color_space: str,
        saving_cctf_encoding: bool,
    ) -> dict[str, object]:
        return {
            'color_space': saving_color_space,
            'cctf_encoding': saving_cctf_encoding,
        }

    def _confirm_light_table_hdr_export(self) -> bool:
        yes = getattr(QMessageBox, "Yes", 0x00004000)
        no = getattr(QMessageBox, "No", 0x00010000)
        result = QMessageBox.question(
            dialog_parent(self._viewer),
            "HDR Light Table export",
            "HDR Light Table is an idealized HDR viewing/export mode, not the ordinary Scan image.\n\n"
            "Preview/Scan, the HEIC SDR base, and the HDR image shown by Quick Look are different projections. "
            "The exported SDR base is stored as linear RGB and HDR viewers may show a gain-map composite.\n\n"
            "Continue exporting HDR Light Table HEIC/HEIF?",
            yes | no,
            no,
        )
        return result == yes

    def save_current_as_default(self) -> None:
        persistence_actions.save_current_as_default(
            viewer=self._viewer,
            widgets=self._widgets,
            collect_gui_state_fn=collect_gui_state,
            save_default_gui_state_fn=save_default_gui_state,
            set_status_fn=set_status,
            dialog_parent_fn=dialog_parent,
            message_box=QMessageBox,
        )

    def save_current_state_to_file(self) -> None:
        persistence_actions.save_current_state_to_file(
            viewer=self._viewer,
            widgets=self._widgets,
            file_dialog=_DirMemoryDialog('gui_state'),
            collect_gui_state_fn=collect_gui_state,
            save_gui_state_to_path_fn=save_gui_state_to_path,
            set_status_fn=set_status,
            dialog_parent_fn=dialog_parent,
            message_box=QMessageBox,
        )

    def load_state_from_file(self) -> None:
        persistence_actions.load_state_from_file(
            viewer=self._viewer,
            widgets=self._widgets,
            file_dialog=_DirMemoryDialog('gui_state'),
            load_gui_state_from_path_fn=load_gui_state_from_path,
            apply_gui_state_fn=apply_gui_state,
            sync_canvas_background_fn=self._sync_canvas_background,
            set_status_fn=set_status,
            dialog_parent_fn=dialog_parent,
            message_box=QMessageBox,
        )

    def restore_factory_default(self) -> None:
        persistence_actions.restore_factory_default(
            viewer=self._viewer,
            widgets=self._widgets,
            project_default_gui_state=PROJECT_DEFAULT_GUI_STATE,
            clear_saved_default_gui_state_fn=clear_saved_default_gui_state,
            apply_gui_state_fn=apply_gui_state,
            sync_canvas_background_fn=self._sync_canvas_background,
            set_status_fn=set_status,
            dialog_parent_fn=dialog_parent,
            message_box=QMessageBox,
        )

    def _preview_input_layer(self) -> NapariImageLayer | None:
        return self._layers.preview_input_layer()

    def _white_border_layer(self) -> NapariImageLayer | None:
        return self._layers.white_border_layer()

    def _set_or_add_output_layer(
        self,
        image: np.ndarray,
        *,
        float_image: object | None,
        output_color_space: str,
        output_cctf_encoding: bool,
        use_display_transform: bool,
        hdr_scene_energy: object | None = None,
        route_master: object | None = None,
        route_master_cache_signature: str | None = None,
    ) -> NapariImageLayer | None:
        self._layers.set_or_add_output_layer(
            image,
            float_image=float_image,
            output_color_space=output_color_space,
            output_cctf_encoding=output_cctf_encoding,
            use_display_transform=use_display_transform,
            output_interpolation_mode=self._output_interpolation_mode(),
        )
        output_layer = self._output_layer()
        if output_layer is not None:
            output_layer.metadata[OUTPUT_HDR_SCENE_ENERGY_KEY] = hdr_scene_energy
            if route_master is None:
                output_layer.metadata.pop(OUTPUT_ROUTE_MASTER_KEY, None)
                output_layer.metadata.pop(OUTPUT_ROUTE_MASTER_SIGNATURE_KEY, None)
            else:
                output_layer.metadata[OUTPUT_ROUTE_MASTER_KEY] = route_master
                if route_master_cache_signature is None:
                    output_layer.metadata.pop(OUTPUT_ROUTE_MASTER_SIGNATURE_KEY, None)
                else:
                    output_layer.metadata[OUTPUT_ROUTE_MASTER_SIGNATURE_KEY] = route_master_cache_signature
        return output_layer

    def _set_or_add_input_stack(
        self,
        image: np.ndarray,
    ) -> None:
        self._update_preview_cache(
            image,
            home_input_stack=True,
            hide_output=True,
        )

    def _update_preview_cache(
        self,
        image: np.ndarray,
        *,
        home_input_stack: bool,
        hide_output: bool,
    ) -> None:
        state = collect_gui_state(widgets=self._widgets)
        preview_image = self._resize_for_preview(image, max_size=state.gui_only.display.settings.preview_max_size)
        preview_display_image = self._prepare_input_color_preview_image(
            preview_image,
            input_color_space=state.input_image.io.input_color_space,
            apply_cctf_decoding=state.input_image.io.input_cctf_decoding,
        )
        self._current_input_image = image
        self._current_preview_image = preview_image
        self._layers.set_or_add_input_preview_layer(
            preview_display_image,
            watermark_source_size=tuple(int(dimension) for dimension in image.shape[:2]),
            white_padding=state.gui_only.display.white_padding,
            hide_output=hide_output,
            set_active=home_input_stack or self._output_layer() is None,
        )
        if home_input_stack:
            self._home_input_stack()

    def _sync_white_border(self, *, white_padding: float) -> None:
        self._layers.sync_white_border(white_padding=white_padding)

    def _home_input_stack(self) -> None:
        if self._white_border_layer() is None:
            return
        reset_viewer_camera(self._viewer)
        self._set_active_layer(self._white_border_layer())

    def _simulation_input_image(self, *, source_layer_name: str) -> np.ndarray | None:
        if source_layer_name == INPUT_PREVIEW_LAYER_NAME:
            return self._current_preview_image
        if source_layer_name == INPUT_LAYER_NAME:
            return self._current_input_image
        return None

    def _auto_preview_enabled(self) -> bool:
        simulation_section = getattr(self._widgets, 'simulation', None)
        auto_preview_value = getattr(simulation_section, 'auto_preview_value', None)
        return bool(auto_preview_value()) if callable(auto_preview_value) else False

    def _run_scheduled_auto_preview(self) -> None:
        self._auto_preview_scheduled = False
        if not self._auto_preview_enabled() or self._current_preview_image is None:
            self._pending_auto_preview = False
            return
        if self._active_simulation_worker is not None:
            self._pending_auto_preview = True
            return
        self._run_preview(report_status=False)

    def _replay_pending_auto_preview(self) -> None:
        if not self._pending_auto_preview:
            return
        self._pending_auto_preview = False
        self.request_auto_preview()

    def _output_layer(self) -> NapariImageLayer | None:
        return self._layers.output_layer()

    def _set_active_layer(self, layer: NapariImageLayer | None) -> None:
        self._layers.set_active_layer(layer)

    def _output_layer_float_data(self) -> object | None:
        output_layer = self._output_layer()
        if output_layer is None:
            return None
        float_data = output_layer.metadata.get(OUTPUT_FLOAT_DATA_KEY)
        if float_data is None:
            return None
        return float_data

    def _output_layer_render_settings(
        self,
        *,
        default_color_space: str,
        default_cctf_encoding: bool,
    ) -> tuple[str, bool]:
        output_layer = self._output_layer()
        if output_layer is None:
            return default_color_space, default_cctf_encoding
        color_space = output_layer.metadata.get(OUTPUT_COLOR_SPACE_KEY, default_color_space)
        cctf_encoding = output_layer.metadata.get(OUTPUT_CCTF_ENCODING_KEY, default_cctf_encoding)
        return str(color_space), bool(cctf_encoding)

    def _output_interpolation_mode(self) -> str:
        display_section = getattr(self._widgets, 'display', None)
        editor = getattr(display_section, 'output_interpolation', None)
        value = getattr(editor, 'value', None)
        if isinstance(value, str) and value:
            return value
        current_text = getattr(editor, 'currentText', None)
        if callable(current_text):
            text = current_text()
            if isinstance(text, str) and text:
                return text
        return 'spline36'

    @staticmethod
    def _resize_for_preview(image_data: np.ndarray, *, max_size: int) -> np.ndarray:
        return resize_for_preview(image_data, max_size)

    @staticmethod
    def _prepare_input_color_preview_image(
        image_data: np.ndarray,
        *,
        input_color_space: str,
        apply_cctf_decoding: bool,
    ) -> np.ndarray:
        return runtime.prepare_input_color_preview_image(
            image_data,
            input_color_space=input_color_space,
            apply_cctf_decoding=apply_cctf_decoding,
            colour_module=colour,
        )

    @staticmethod
    def _prepare_output_display_image(
        image_data: np.ndarray,
        *,
        output_color_space: str,
        output_cctf_encoding: bool = True,
        use_display_transform: bool,
        padding_pixels: float = 0.0,
        phase_timings: dict[str, float] | None = None,
    ) -> tuple[np.ndarray, str]:
        return runtime.prepare_output_display_image(
            image_data,
            output_color_space=output_color_space,
            output_cctf_encoding=output_cctf_encoding,
            use_display_transform=use_display_transform,
            padding_pixels=padding_pixels,
            imagecms_module=ImageCms,
            colour_module=colour,
            pil_image_module=PILImage,
            phase_timings=phase_timings,
        )

    def _process_image_with_runtime(
        self,
        image_data: np.ndarray,
        params,
        *,
        require_hdr_metadata: bool = False,
        require_route_master: bool = False,
        hdr_mode: str = "paper",
    ) -> object:
        apply_stocks_specifics = (
            self._runtime_simulator is None
            or self._next_runtime_digest_applies_stock_specifics
        )
        digested_params = digest_params(
            params,
            apply_stocks_specifics=apply_stocks_specifics,
        )
        try:
            if self._runtime_simulator is None:
                self._runtime_simulator = runtime_simulator(digested_params)
            else:
                self._runtime_simulator.update_params(digested_params)
            self._next_runtime_digest_applies_stock_specifics = False
            if require_route_master:
                result = self._runtime_simulator.process_with_master(
                    image_data,
                    hdr_mode=hdr_mode,
                )
            elif require_hdr_metadata:
                result = self._runtime_simulator.process_with_metadata(image_data)
            else:
                result = self._runtime_simulator.process(image_data)
            summary_fn = getattr(self._runtime_simulator, "backend_runtime_summary", None)
            self._last_runtime_backend_summary = summary_fn() if callable(summary_fn) else None
            return result
        except Exception:
            self._runtime_simulator = None
            self._last_runtime_backend_summary = None
            raise

    def _set_display_transform_checked(self, enabled: bool) -> None:
        display_section = getattr(self._widgets, 'display', None)
        toggle = getattr(display_section, 'use_display_transform', None)
        if toggle is None:
            return

        block_signals = getattr(toggle, 'blockSignals', None)
        set_checked = getattr(toggle, 'setChecked', None)
        if not callable(set_checked):
            return

        previous_block_state = None
        if callable(block_signals):
            previous_block_state = block_signals(True)
        try:
            set_checked(enabled)
        finally:
            if callable(block_signals):
                block_signals(bool(previous_block_state))

    def _sync_canvas_background(self) -> None:
        display_section = getattr(self._widgets, 'display', None)
        toggle = getattr(display_section, 'gray_18_canvas', None)
        is_checked = getattr(toggle, 'isChecked', None)
        self.set_gray_18_canvas_enabled(bool(is_checked()) if callable(is_checked) else False)

    def _execute_simulation_request(self, request: SimulationRequest) -> SimulationResult:
        return runtime.execute_simulation_request(
            request,
            run_simulation_fn=self._process_image_with_runtime,
            prepare_output_display_image_fn=self._prepare_output_display_image,
            runtime_status_fn=lambda: self._last_runtime_backend_summary,
            runtime_timings_fn=lambda: dict(self._runtime_simulator.get_timings())
            if self._runtime_simulator is not None and hasattr(self._runtime_simulator, "get_timings")
            else {},
        )

    @staticmethod
    def _configure_simulation_params(params, *, source_layer_name: str):
        settings = getattr(params, 'settings', None)
        if settings is not None and hasattr(settings, 'preview_mode'):
            settings.preview_mode = source_layer_name == INPUT_PREVIEW_LAYER_NAME
        _set_backend_materialize_policy_for_mlx_float32(params)
        return params

    def _start_simulation(self, *, source_layer_name: str, mode_label: str, report_status: bool = True) -> None:
        if self._active_simulation_worker is not None:
            set_status(self._viewer, 'Simulation already running')
            return

        image_data = self._simulation_input_image(source_layer_name=source_layer_name)
        if image_data is None:
            QMessageBox.warning(dialog_parent(self._viewer), 'Run simulation', 'Load an input image before running the simulation.')
            return

        state = collect_gui_state(widgets=self._widgets)
        self._sync_white_border(white_padding=state.gui_only.display.white_padding)
        params = self._configure_simulation_params(
            build_params_from_state(state),
            source_layer_name=source_layer_name,
        )
        require_hdr_metadata = _requires_hdr_metadata_for_state(state)
        require_route_master = require_hdr_metadata and source_layer_name == INPUT_LAYER_NAME
        hdr_mode = "paper"
        hdr_state = getattr(state, "hdr", None)
        if hdr_state is not None:
            hdr_mode = normalize_hdr_mapping_mode(getattr(hdr_state, "hdr_mapping_mode", "paper"))
        route_master_cache_signature = None
        if require_route_master:
            route_master_cache_signature = _route_master_cache_signature(
                input_image=image_data,
                gui_state=state,
                hdr_mode=hdr_mode,
                saving_color_space=state.simulation.workflow.saving_color_space,
                saving_cctf_encoding=state.simulation.workflow.saving_cctf_encoding,
            )
        memory_warning_shown = False
        if source_layer_name == INPUT_LAYER_NAME:
            memory_message = runtime.full_render_memory_guard_message(
                image_data,
                params,
                require_hdr_metadata=require_hdr_metadata,
                require_route_master=require_route_master,
            )
            if memory_message is not None:
                warning_message = (
                    f'{memory_message}\n\n'
                    'Continuing anyway. If the render fails or the system becomes memory pressured, '
                    'use Preview, crop/downscale, disable grain/spatial effects, or increase '
                    'SPEKTRAFILM_RENDER_MEMORY_BUDGET_MB.'
                )
                QMessageBox.warning(
                    dialog_parent(self._viewer),
                    'Run simulation',
                    warning_message,
                )
                set_status(
                    self._viewer,
                    'Full-resolution render exceeds estimated memory budget; continuing anyway',
                    timeout_ms=0,
                )
                memory_warning_shown = True

        image, phase_timings, memory_estimates = _prepare_simulation_input_image(image_data, params)
        phase_timings['gui.input_conversion'] = phase_timings['gui.input_prepare']
        request = SimulationRequest(
            mode_label=mode_label,
            image=image,
            params=params,
            output_color_space=state.simulation.io.output_color_space,
            output_cctf_encoding=state.simulation.io.output_cctf_encoding,
            use_display_transform=state.gui_only.display.use_display_transform,
            phase_timings=phase_timings,
            memory_estimates=memory_estimates,
            require_hdr_metadata=require_hdr_metadata,
            require_route_master=require_route_master,
            hdr_mode=hdr_mode,
            route_master_cache_signature=route_master_cache_signature,
        )

        worker = runtime.SimulationWorker(request, execute_request=self._execute_simulation_request)
        worker.signals.finished.connect(self._on_simulation_finished)
        worker.signals.failed.connect(self._on_simulation_failed)
        self._active_simulation_worker = worker
        self._active_simulation_label = mode_label
        self._active_simulation_reports_status = report_status
        self._set_simulation_controls_enabled(False)
        if report_status and not memory_warning_shown:
            set_status(self._viewer, f'Computing {mode_label.lower()}...', timeout_ms=0)
        self._thread_pool.start(worker)

    def _on_simulation_finished(self, result: SimulationResult) -> None:
        report_status = self._active_simulation_reports_status
        self._active_simulation_worker = None
        self._active_simulation_label = None
        self._active_simulation_reports_status = True
        self._set_simulation_controls_enabled(True)
        layer_start = time.perf_counter()
        output_layer = self._set_or_add_output_layer(
            result.display_image,
            float_image=result.float_image,
            output_color_space=result.output_color_space,
            output_cctf_encoding=result.output_cctf_encoding,
            use_display_transform=result.use_display_transform,
            hdr_scene_energy=result.hdr_scene_energy,
            route_master=result.route_master,
            route_master_cache_signature=result.route_master_cache_signature,
        )
        result.phase_timings['gui.layer_update'] = time.perf_counter() - layer_start
        if output_layer is not None and hasattr(output_layer, "metadata"):
            output_layer.metadata[OUTPUT_PHASE_TIMINGS_KEY] = dict(result.phase_timings)
        if report_status:
            set_status(self._viewer, f'{result.mode_label} completed. {result.status_message}', timeout_ms=0)
        self._replay_pending_auto_preview()

    def _on_simulation_failed(self, message: str) -> None:
        self._active_simulation_worker = None
        mode_label = self._active_simulation_label or 'Simulation'
        self._active_simulation_label = None
        self._active_simulation_reports_status = True
        self._set_simulation_controls_enabled(True)
        QMessageBox.critical(dialog_parent(self._viewer), 'Run simulation', f'Simulation failed.\n\n{message}')
        set_status(self._viewer, f'{mode_label} failed')
        self._replay_pending_auto_preview()

    @staticmethod
    def _execute_heic_export_request(request: runtime.HEICExportRequest) -> dict[str, object]:
        from spektrafilm.hdr.routemaster_export import export_hdr_heic_from_simulator

        export_diagnostics: dict[str, object] = {}
        if request.master is not None:
            diagnostics = export_hdr_heic_from_simulator(
                None,
                None,
                request.filepath,
                hdr_mode=request.hdr_mode,
                config=request.config,
                color_space=request.color_space,
                quality=request.quality,
                gain_map_mode=request.gain_map_mode,
                master=request.master,
                export_diagnostics_out=export_diagnostics,
            )
        else:
            diagnostics = export_hdr_heic_from_simulator(
                request.simulator,
                request.image,
                request.filepath,
                hdr_mode=request.hdr_mode,
                config=request.config,
                color_space=request.color_space,
                quality=request.quality,
                gain_map_mode=request.gain_map_mode,
                master=None,
                export_diagnostics_out=export_diagnostics,
            )
        return {"diagnostics": diagnostics, "export_diagnostics": export_diagnostics}

    def _on_heic_export_finished(self, result: dict[str, object]) -> None:
        self._active_export_worker = None
        filepath = self._active_export_filepath
        self._active_export_filepath = None
        self._set_simulation_controls_enabled(True)
        export_diagnostics = result.get("export_diagnostics", {}) if isinstance(result, dict) else {}
        set_status(
            self._viewer,
            f"Saved output image to {filepath}; HEIC/HEIF source metadata copy is not supported."
            f"{_format_hdr_export_diagnostics(export_diagnostics)}",
        )

    def _on_heic_export_failed(self, message: str) -> None:
        self._active_export_worker = None
        filepath = self._active_export_filepath
        self._active_export_filepath = None
        self._set_simulation_controls_enabled(True)
        QMessageBox.critical(
            dialog_parent(self._viewer),
            'Save output',
            f'Failed to save HDR HEIC output image{f" to {filepath}" if filepath else ""}.\n\n{message}'
        )
        set_status(self._viewer, 'HDR HEIC save failed')

    def _set_simulation_controls_enabled(self, enabled: bool) -> None:
        simulation_section = getattr(self._widgets, 'simulation', None)
        if simulation_section is None:
            return
        for button_name in ('preview_button', 'scan_button', 'save_button'):
            button = getattr(simulation_section, button_name, None)
            set_enabled = getattr(button, 'setEnabled', None)
            if callable(set_enabled):
                set_enabled(enabled)

    def _run_simulation(self, *, source_layer_name: str) -> None:
        image_data = self._simulation_input_image(source_layer_name=source_layer_name)
        if image_data is None:
            QMessageBox.warning(dialog_parent(self._viewer), 'Run simulation', 'Load an input image before running the simulation.')
            return

        state = collect_gui_state(widgets=self._widgets)
        self._sync_white_border(white_padding=state.gui_only.display.white_padding)
        params = self._configure_simulation_params(
            build_params_from_state(state),
            source_layer_name=source_layer_name,
        )

        image, _phase_timings, _memory_estimates = _prepare_simulation_input_image(image_data, params)
        if _requires_hdr_metadata_for_state(state):
            hdr_mode = normalize_hdr_mapping_mode(getattr(state.hdr, "hdr_mapping_mode", "paper"))
            simulation_output = self._process_image_with_runtime(
                image,
                params,
                require_hdr_metadata=True,
                require_route_master=source_layer_name == INPUT_LAYER_NAME,
                hdr_mode=hdr_mode,
            )
        else:
            simulation_output = self._process_image_with_runtime(image, params)
        scan = getattr(simulation_output, 'image', simulation_output)
        hdr_scene_energy = getattr(simulation_output, 'hdr_scene_energy', None)
        route_master = getattr(simulation_output, 'route_master', None)
        # MLX arrays cannot be evaluated across threads. Since the route master
        # may be cached and later reused by an export worker, materialize it
        # before storing it in layer metadata.
        route_master = runtime.materialize_route_master(route_master)
        scan_display, display_status = self._prepare_output_display_image(
            scan,
            output_color_space=state.simulation.io.output_color_space,
            output_cctf_encoding=state.simulation.io.output_cctf_encoding,
            use_display_transform=state.gui_only.display.use_display_transform,
        )
        self._set_or_add_output_layer(
            scan_display,
            float_image=scan,
            output_color_space=state.simulation.io.output_color_space,
            output_cctf_encoding=state.simulation.io.output_cctf_encoding,
            use_display_transform=state.gui_only.display.use_display_transform,
            hdr_scene_energy=hdr_scene_energy,
            route_master=route_master,
            route_master_cache_signature=None,
        )
        set_status(self._viewer, display_status)
