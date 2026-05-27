# GUI Research Hardening Implementation

Date: 2026-05-27

## Goal

Convert the actionable findings from:

- `docs 2/dev/research-gui-product-logic.md`
- `docs 2/dev/research-gui-aesthetics.md`
- `docs 2/dev/research-gui-color-hdr.md`

into tested GUI improvements without pretending that broader items such as
true HDR preview, worker cancellation, or undo can be safely solved by surface
styling alone.

The implementation plan was written first at
`docs/superpowers/plans/2026-05-27-gui-research-hardening.md`.

## External References Applied

- Qt `QAbstractSlider.tracking`
  (`https://doc.qt.io/qt-6/qabstractslider.html#tracking-prop`): disable
  tracking for expensive preview-bound sliders so the committed value changes
  on release, while drag feedback can still update local UI labels.
- Qt accessibility guidance (`https://doc.qt.io/qt-6/accessible.html`): assign
  accessible names and descriptions from the visible label and
  tooltip/spec description so assistive clients have useful control metadata.
- Qt style sheet reference (`https://doc.qt.io/qt-6/stylesheet-reference.html`):
  keyboard focus needs a visible state; removing outlines and borders globally
  makes the GUI harder to operate.
- Qt high-DPI guidance
  (`https://doc.qt.io/qtforpython-6.10/overviews/qtdoc-highdpi.html`): Qt
  widgets already use device-independent coordinates, so manual
  `devicePixelRatioF()` scaling is not a correct generic GUI fix.
- Apple HIG slider guidance
  (`https://developer.apple.com/design/human-interface-guidelines/sliders`):
  sliders are appropriate for bounded continuous values, especially when rapid
  visual tuning matters.

## Real Issues Fixed

### 1. Bounded Float Controls Were Spinboxes Only

The research requested more tactile control for preview-tuned parameters. The
actual code already had `SliderFloatEditor`, but `DataclassSection` never chose
it for bounded float fields. That made finite-range controls slower to scan and
tune.

Implemented:

- `DataclassSection` now uses `SliderFloatEditor` for float fields with finite
  `minimum`, finite `maximum`, positive `step`, and at most 256 slider steps.
- Unbounded float fields still use `FloatEditor`.
- Very wide technical guard ranges, such as `-100..100` exposure compensation
  at `0.25` step size, stay as spin boxes instead of becoming dense sliders.
- `SliderFloatEditor` disables slider tracking so expensive auto-preview work
  is not committed for every drag tick.
- Dragging still updates the local numeric label through `sliderMoved`.

Coverage:

- `tests/gui/test_widgets.py::test_bounded_float_fields_use_slider_editor_and_unbounded_fields_use_spinbox`
- `tests/gui/test_widgets.py::test_slider_float_editor_commits_on_value_changed_but_only_previews_dragged_label`

### 2. Focus Styling Was Removed

The current theme explicitly removed borders and outlines from common controls.
This made keyboard focus and active controls harder to see.

Implemented:

- Added neutral control borders.
- Added hover border color.
- Added focus border color using the existing accent token.
- Added QSlider groove, handle, and sub-page styling that fits the existing
  dark theme.
- Added a subtle status-bar top border.

Coverage:

- Covered by GUI import/layout tests and `compileall`; this is a style contract
  rather than business logic.

### 3. Widgets Lacked Programmatic Accessible Names

Control specs already had labels and tooltips, but editors did not receive
programmatic accessible names/descriptions.

Implemented:

- `DataclassSection._apply_specs()` sets `accessibleName` from the spec label or
  generated field label.
- `DataclassSection._apply_specs()` sets `accessibleDescription` from the
  tooltip.
- `TupleEditor` and `SliderFloatEditor` propagate accessible name/description
  to their child controls.

Coverage:

- Existing GUI widget construction tests exercise this path.

### 4. Control Tabs Mixed Workflow Stages And Technical Buckets

The old tabs were `MAIN`, `FILM`, `PRINT`, `ADVANCED`, and `CONFIG`. `MAIN`
mixed import/load/crop/output/HDR concerns, which made the first workflow
screen too broad.

Implemented:

- New workflow grouping:
  - `IMPORT`: file selection, raw loading, crop, input image, camera.
  - `FILM`: simulation, exposure, halation, couplers, grain.
  - `PRINT`: enlarger, diffusion, glare, preflashing, scanner.
  - `OUTPUT`: HDR export and output.
  - `ADVANCED`: spectral upsampling, tuning, special options,
    camera diffusion.
  - `CONFIG`: GUI/display/Napari layer controls.
- The simulation action bar remains pinned below tabs.

Coverage:

- `tests/gui/test_layout.py::test_build_controls_panel_groups_controls_by_workflow_stage`

### 5. Queued Auto-Preview Had No User-Visible Status

When a preview was requested while a worker was already active, the controller
set `_pending_auto_preview` but did not tell the user that work was queued.

Implemented:

- `_run_scheduled_auto_preview()` now reports:
  `Preview queued; it will run after the current simulation finishes`.

Coverage:

- `tests/gui/test_controller_flow.py::test_request_auto_preview_reports_queued_preview_when_worker_is_active`

### 6. HDR Path-To-White Disable Needed A Regression Test

The production controller already mapped the GUI toggle to both the legacy and
profile-aware path-to-white strength values. No production change was needed,
but the behavior was important enough to lock down.

Implemented:

- Added a regression test proving that disabling the GUI toggle passes
  `path_to_white_strength=0.0` and
  `profile_path_to_white_strength=0.0` into `save_hdr_photo_heic()`.

Coverage:

- `tests/gui/test_controller_output.py::test_save_output_layer_disables_profile_path_to_white_when_gui_toggle_is_off`

## Explicit Non-Goals

These items were considered but deliberately not implemented in this pass:

- Worker cancellation: Qt `QRunnable` cannot be safely killed externally. A real
  cancel feature needs cooperative cancellation in the simulation loop.
- Undo: safe undo needs signal suppression and a state-history contract. A
  button-only change would be unreliable.
- True HDR preview: the current Napari/Qt display path is not a verified HDR
  presentation surface. Export metadata correctness remains separate from
  on-screen HDR presentation.
- Manual high-DPI scaling: Qt already handles device-independent coordinates.
  Adding manual scaling would risk double-scaling.
- QColorSpace-only HDR fix: image color-space tagging is useful for assets, but
  it does not make the current viewer a true HDR display pipeline.

## Files Changed

- `src/spektrafilm_gui/widget_sections.py`
- `src/spektrafilm_gui/widget_editors.py`
- `src/spektrafilm_gui/theme_palette.py`
- `src/spektrafilm_gui/theme_styles.py`
- `src/spektrafilm_gui/napari_layout.py`
- `src/spektrafilm_gui/controller.py`
- `tests/gui/test_widgets.py`
- `tests/gui/test_layout.py`
- `tests/gui/test_controller_flow.py`
- `tests/gui/test_controller_output.py`
- `tests/gui/test_controller_runtime_module.py`
- `docs/superpowers/plans/2026-05-27-gui-research-hardening.md`
- `docs/dev/gui-research-hardening-implementation.md`

## Verification

Commands run:

```bash
.venv/bin/python -m pytest -q tests/gui
.venv/bin/python -m pytest --ignore=tests/gui -q
.venv/bin/python -m compileall -q src/spektrafilm src/spektrafilm_gui tests
git diff --check
```

Results:

- `tests/gui`: 186 passed.
- Non-GUI suite: 549 passed, 6 skipped, 13 warnings.
- `compileall`: passed.
- `git diff --check`: passed.

The non-GUI warnings are existing numeric/deprecation warnings and are not
introduced by the GUI changes.

## Confidence Check

Self-audit result before completion:

- Every implemented GUI behavior has focused coverage or is covered by existing
  construction/import tests.
- Existing SDR/HDR export behavior was not broadened or re-routed.
- No fake cancellation, fake undo, or fake HDR preview was added.
- The GUI tab grouping now follows user workflow instead of exposing all
  controls as technical buckets.
- Full GUI and non-GUI test suites pass in the current workspace state.
