# GUI Research Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the verified GUI research findings into concrete, low-risk improvements: workflow-stage tabs, bounded-value sliders, visible focus/accessibility metadata, queued auto-preview feedback, and HDR path-to-white regression coverage.

**Architecture:** Keep the existing napari + Qt Widgets structure. Improve the current widget factory, style sheet, tab composition, and controller status behavior without adding a separate HDR renderer, undo stack, or batch subsystem in this pass. Preserve existing state dataclasses and runtime contracts.

**Tech Stack:** Python 3.13, qtpy/PySide6, napari, NumPy, pytest, `.venv/bin/python`.

---

## Evidence And Scope

The research files under `docs/archive/docs-2-legacy-20260531/dev/` contain three classes of recommendations:

1. Verified defects or product-quality gaps that are small enough to fix safely now.
2. Feature gaps that are real but require larger product design: cancelable simulation, undo/redo, before/after, histogram, crop overlay, batch export, soft proofing, and true HDR preview.
3. Recommendations that are not correct for the current architecture. In particular, Qt high-DPI documentation says normal QWidget geometry is already device-independent; manually multiplying custom widget rectangles by `devicePixelRatioF()` would double-scale the checkbox indicator. Also, Qt `QColorSpace`/`QImage` tagging does not directly fix napari's NumPy/VisPy display path.

External reference points used for this plan:

- Qt `QSlider` is explicitly for bounded values and emits `valueChanged`; its tracking behavior determines whether dragging emits continuously.
- Qt accessibility docs recommend using Qt widgets where possible and providing accessible interface metadata for custom UI elements.
- Qt style sheets support focus-state styling; removing all focus borders makes keyboard navigation hard to see.
- Qt high-DPI docs say higher-level Qt Widgets use device-independent coordinates automatically; raw buffers and lower-level drawing need extra care.
- Qt `QColorSpace` and `QImage::setColorSpace()` are useful for QImage-based pipelines, but Spektrafilm display layers currently enter napari as arrays after explicit sRGB/display conversion.

Confirmed current-state findings:

- `SliderFloatEditor` exists in `src/spektrafilm_gui/widget_editors.py` but `DataclassSection._build_editor()` never uses it for bounded floats.
- `SliderFloatEditor` currently uses default slider tracking, which would emit `valueChanged` repeatedly during drag and make auto-preview churn worse.
- `theme_styles.py` removes focus borders for push buttons, tool buttons, combo boxes, line edits, spin boxes, check boxes, and tabs.
- `DataclassSection` applies tooltips and numeric constraints but does not set accessible names or descriptions on generated editors.
- `build_controls_panel()` still uses `MAIN / FILM / PRINT / ADVANCED / CONFIG`, leaving import/output settings and creative film controls mixed in the long main tab.
- `request_auto_preview()` queues work while a simulation is active, but the status bar does not tell the user that the preview is queued.
- `GuiController.save_output_layer()` currently maps `path_to_white_enabled=False` to both legacy and profile-aware path-to-white strength, but there is no GUI regression test preserving that behavior.

Explicit non-goals for this pass:

- Do not implement a fake cancel button. `QRunnable` cannot be stopped safely from the outside, and the simulation pipeline does not yet expose cooperative progress/cancel checks.
- Do not add true HDR preview. It needs a separate HDR-capable rendering surface and platform-specific display headroom handling; the current napari array path remains SDR preview by design.
- Do not add undo/redo in this patch. It needs a state-history boundary and signal suppression policy so profile-sync and scan-for-print side effects do not produce corrupted history.

## File Structure

- Modify `tests/gui/test_widgets.py`
  - Add tests proving bounded floats use `SliderFloatEditor`, unbounded floats stay as `FloatEditor`, slider tracking is disabled, slider drag updates its label without emitting committed value changes, and generated editors receive accessible names/descriptions.
- Modify `tests/gui/test_layout.py`
  - Add a Qt-offscreen test proving controls tabs are workflow-stage ordered: `IMPORT`, `FILM`, `PRINT`, `OUTPUT`, `ADVANCED`, `CONFIG`.
- Modify `tests/gui/test_controller_flow.py`
  - Add a test proving queued auto-preview while a worker is active writes a status message.
- Modify `tests/gui/test_controller_output.py`
  - Add a test proving the GUI `path_to_white_enabled=False` state disables both `hdr_highlight_path_to_white` and `profile_hdr_path_to_white_strength`.
- Modify `src/spektrafilm_gui/widget_editors.py`
  - Make `SliderFloatEditor` non-tracking, expose committed `valueChanged(float)`, update the display label while dragging, and propagate accessible metadata to child widgets.
- Modify `src/spektrafilm_gui/widget_sections.py`
  - Import `SliderFloatEditor`, choose it for bounded float fields with finite min/max/step and a reasonable slider-step count, keep unbounded or overly wide technical ranges as spin boxes, and apply accessible names/descriptions.
- Modify `src/spektrafilm_gui/theme_palette.py`
  - Add focus/border/slider color aliases backed by the existing neutral palette and accent.
- Modify `src/spektrafilm_gui/theme_styles.py`
  - Add subtle control borders, visible focus borders, slider groove/handle styling, and a status-bar top border.
- Modify `src/spektrafilm_gui/napari_layout.py`
  - Recompose tabs around workflow stages without moving the persistent action bar.
- Modify `src/spektrafilm_gui/controller.py`
  - Report queued preview status when auto-preview is deferred by an active worker.
- Add `docs/dev/gui-research-hardening-implementation.md`
  - Record implemented changes, rejected/staged recommendations, external-source conclusions, and verification commands.

## Task 1: Write Failing Widget Tests

- [x] Add `test_bounded_float_fields_use_slider_editor_and_unbounded_fields_use_spinbox()` to `tests/gui/test_widgets.py`:

```python
def test_bounded_float_fields_use_slider_editor_and_unbounded_fields_use_spinbox(monkeypatch) -> None:
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from qtpy import QtWidgets

    _app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    @dataclass
    class TestState:
        bounded: float = 0.5
        unbounded: float = 2.0

    monkeypatch.setitem(
        widget_specs_module.GUI_WIDGET_SPECS,
        'slider_test',
        {
            'bounded': widget_specs_module.WidgetSpec(label='Bounded', tooltip='Bounded value', min_value=0.0, max_value=1.0, step=0.1, decimals=2),
            'unbounded': widget_specs_module.WidgetSpec(label='Unbounded', tooltip='Unbounded value', min_value=0.0, step=0.1, decimals=2),
        },
    )

    section = widgets_module.DataclassSection(state_cls=TestState, section_name='slider_test', title='Slider Test')

    assert isinstance(section.bounded, widget_editors_module.SliderFloatEditor)
    assert isinstance(section.unbounded, widget_editors_module.FloatEditor)
    assert section.bounded.accessibleName() == 'Bounded'
    assert section.bounded.accessibleDescription() == 'Bounded value'
```

- [x] Add `test_slider_float_editor_commits_on_value_changed_but_only_previews_dragged_label()`:

```python
def test_slider_float_editor_commits_on_value_changed_but_only_previews_dragged_label() -> None:
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from qtpy import QtWidgets

    _app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    editor = widget_editors_module.SliderFloatEditor(minimum=0.0, maximum=1.0, step=0.25, decimals=2)
    emitted: list[float] = []
    editor.valueChanged.connect(emitted.append)

    assert editor._slider.hasTracking() is False

    editor._slider.sliderMoved.emit(3)
    assert editor._label.text() == '0.75'
    assert emitted == []

    editor._slider.setValue(3)
    assert emitted == [0.75]
```

- [x] Run:

```bash
.venv/bin/python -m pytest -q tests/gui/test_widgets.py::test_bounded_float_fields_use_slider_editor_and_unbounded_fields_use_spinbox tests/gui/test_widgets.py::test_slider_float_editor_commits_on_value_changed_but_only_previews_dragged_label
```

Expected RED: first test fails because bounded floats still use `FloatEditor`; second test fails because slider tracking is still enabled and `sliderMoved` does not update the label independently.

## Task 2: Implement Widget Factory, Slider, Accessibility, And QSS

- [x] In `SliderFloatEditor.__init__()`, call `self._slider.setTracking(False)` after creating the `QSlider`.
- [x] Add helper methods to `SliderFloatEditor`:

```python
def _value_for_tick(self, tick: int) -> float:
    return self._minimum + int(tick) * self._step

def _label_text_for_value(self, value: float) -> str:
    return f'{value:.{self._decimals}f}{self._suffix}'

def _update_label(self, value: float | None = None) -> None:
    self._label.setText(self._label_text_for_value(self.value if value is None else value))

def _on_slider_moved(self, tick: int) -> None:
    self._update_label(self._value_for_tick(tick))
```

- [x] Connect `self._slider.sliderMoved.connect(self._on_slider_moved)` and keep `valueChanged` connected to `_on_slider_changed`.
- [x] Override `setAccessibleName()` and `setAccessibleDescription()` in `SliderFloatEditor` and `TupleEditor` to propagate metadata to child controls.
- [x] In `DataclassSection._build_editor()`, return `SliderFloatEditor` for float fields only when `spec.min_value`, `spec.max_value`, and `spec.step` are all present, the step is positive, and the resulting slider is not an overly dense technical range.
- [x] In `DataclassSection._apply_specs()`, set each editor's accessible name to `spec.label or _format_label(field_name)` and accessible description to `spec.tooltip` when present.
- [x] Add neutral border/focus/slider color constants to `theme_palette.py`, then update `theme_styles.py`:

```css
QPushButton, QToolButton, QComboBox, QLineEdit, QAbstractSpinBox {
    border: 1px solid <neutral-border>;
}
QPushButton:focus, QToolButton:focus, QComboBox:focus, QLineEdit:focus, QAbstractSpinBox:focus, QCheckBox:focus, QTabBar::tab:focus {
    border: 1px solid <accent>;
    outline: none;
}
QSlider::groove:horizontal { ... }
QSlider::handle:horizontal { ... }
QStatusBar { border-top: 1px solid <neutral-border>; }
```

- [x] Run the two widget tests from Task 1. Expected GREEN.

## Task 3: Write Failing Layout, Queue, And HDR Contract Tests

- [x] Add `test_build_controls_panel_groups_controls_by_workflow_stage()` to `tests/gui/test_layout.py`:

```python
def test_build_controls_panel_groups_controls_by_workflow_stage() -> None:
    import os
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from qtpy import QtWidgets

    _app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    action_bar = QtWidgets.QWidget()
    widgets = SimpleNamespace(
        filepicker=QtWidgets.QWidget(),
        load_raw=QtWidgets.QWidget(),
        preview_crop=QtWidgets.QWidget(),
        input_image=QtWidgets.QWidget(),
        camera=QtWidgets.QWidget(),
        simulation=SimpleNamespace(action_bar=lambda: action_bar),
        exposure_control=QtWidgets.QWidget(),
        halation=QtWidgets.QWidget(),
        couplers=QtWidgets.QWidget(),
        grain=QtWidgets.QWidget(),
        enlarger=QtWidgets.QWidget(),
        diffusion=QtWidgets.QWidget(),
        glare=QtWidgets.QWidget(),
        preflashing=QtWidgets.QWidget(),
        scanner=QtWidgets.QWidget(),
        hdr_export=QtWidgets.QWidget(),
        output=QtWidgets.QWidget(),
        spectral_upsampling=QtWidgets.QWidget(),
        tune=QtWidgets.QWidget(),
        special=QtWidgets.QWidget(),
        camera_diffusion=QtWidgets.QWidget(),
        gui_config=QtWidgets.QWidget(),
        display=QtWidgets.QWidget(),
    )
    viewer = make_test_viewer_namespace(_qt_viewer=SimpleNamespace(dockLayerList=None))

    container = napari_layout_module.build_controls_panel(viewer, widgets)
    tab_widget = container.findChild(QtWidgets.QTabWidget, 'controlsTabWidget')

    assert [tab_widget.tabText(index) for index in range(tab_widget.count())] == [
        'IMPORT',
        'FILM',
        'PRINT',
        'OUTPUT',
        'ADVANCED',
        'CONFIG',
    ]
```

- [x] Add `test_request_auto_preview_reports_queued_preview_when_worker_is_active()` to `tests/gui/test_controller_flow.py`:

```python
def test_request_auto_preview_reports_queued_preview_when_worker_is_active(monkeypatch) -> None:
    simulation_section = SimpleNamespace(auto_preview_value=lambda: True)
    controller = GuiController(viewer=object(), widgets=SimpleNamespace(simulation=simulation_section))
    controller._current_preview_image = np.full((2, 2, 3), 0.25, dtype=np.float32)
    controller._active_simulation_worker = object()
    statuses: list[tuple[str, int]] = []

    monkeypatch.setattr(controller_module.QTimer, 'singleShot', staticmethod(lambda _delay_ms, callback: callback()))
    monkeypatch.setattr(controller_module, 'set_status', lambda _viewer, message, timeout_ms=5000: statuses.append((message, timeout_ms)))
    monkeypatch.setattr(controller, '_run_preview', lambda *, report_status: (_ for _ in ()).throw(AssertionError('active worker should defer preview')))

    controller.request_auto_preview()

    assert controller._pending_auto_preview is True
    assert statuses == [('Preview queued; it will run after the current simulation finishes', 5000)]
```

- [x] Add `test_save_output_layer_disables_profile_path_to_white_when_gui_toggle_is_off()` to `tests/gui/test_controller_output.py` using the existing save helper style. Expected values:

```python
assert hdr_kwargs['hdr_highlight_path_to_white'] == 0.0
assert hdr_kwargs['profile_hdr_path_to_white_strength'] == 0.0
```

- [x] Run:

```bash
.venv/bin/python -m pytest -q tests/gui/test_layout.py::test_build_controls_panel_groups_controls_by_workflow_stage tests/gui/test_controller_flow.py::test_request_auto_preview_reports_queued_preview_when_worker_is_active tests/gui/test_controller_output.py::test_save_output_layer_disables_profile_path_to_white_when_gui_toggle_is_off
```

Expected RED: layout and queue tests fail before implementation. The HDR contract test may already pass, which is acceptable because it locks down a current-state fix from a prior change.

## Task 4: Implement Layout And Queue Feedback

- [x] In `napari_layout.build_controls_panel()`, replace the current tab list with:

```python
IMPORT: filepicker, load_raw, preview_crop, input_image, camera
FILM: simulation, exposure_control, halation, couplers, grain
PRINT: enlarger, diffusion, glare, preflashing, scanner
OUTPUT: hdr_export, output
ADVANCED: spectral_upsampling, tune, special, camera_diffusion
CONFIG: gui_config, display, napari layers
```

- [x] Leave `widgets.simulation.action_bar()` below the tab widget so PREVIEW/SCAN/SAVE remain pinned.
- [x] In `GuiController._run_scheduled_auto_preview()`, when `_active_simulation_worker is not None`, set `_pending_auto_preview = True` and call:

```python
set_status(self._viewer, 'Preview queued; it will run after the current simulation finishes')
```

- [x] Run the three tests from Task 3. Expected GREEN.

## Task 5: Update Documentation

- [x] Create `docs/dev/gui-research-hardening-implementation.md` with:
  - Date and source documents reviewed.
  - Confirmed implemented changes.
  - Findings intentionally not implemented now and why.
  - External-source conclusions for Qt slider tracking, accessibility, high-DPI, and color/HDR.
  - Verification commands and outcomes.
- [x] Include the 100% confidence checklist:
  - Are all implemented behavior changes covered by tests?
  - Did any research recommendation rely on a false assumption?
  - Did tab reordering preserve the pinned action bar?
  - Does the slider avoid auto-preview churn while still updating its label during drag?
  - Is the HDR path-to-white toggle contract covered?

## Verification

- [x] Run targeted GUI tests:

```bash
.venv/bin/python -m pytest -q tests/gui/test_widgets.py tests/gui/test_layout.py tests/gui/test_controller_flow.py tests/gui/test_controller_output.py
```

- [x] Run all GUI tests:

```bash
.venv/bin/python -m pytest -q tests/gui
```

- [x] Run non-GUI full suite per `CLAUDE.md`:

```bash
.venv/bin/python -m pytest --ignore=tests/gui -q
```

- [x] Run compile and whitespace checks:

```bash
.venv/bin/python -m compileall -q src/spektrafilm src/spektrafilm_gui tests
git diff --check
```

## Confidence Loop

Before marking the goal complete, repeat this audit:

- Every user-referenced research document was read and each claim was either implemented, tested as already fixed, or explicitly rejected/deferred with current-code evidence.
- Every production change has a fresh test or objective check.
- No broad HDR renderer, cancel button, undo stack, or high-DPI double-scaling was added without the architecture needed to make it true.
- Fresh targeted tests, GUI tests, non-GUI tests, compileall, and diff-check provide the completion evidence.
