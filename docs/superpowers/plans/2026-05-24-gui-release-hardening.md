# GUI Release Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the spektrafilm GUI safer to ship by hardening preview/scan correctness, output saving, metadata transfer, background-worker failures, and user-facing action readiness.

**Architecture:** Keep the existing napari + Qt GUI structure and avoid a broad UI rewrite. Add small controller-level state tracking for input/output readiness, stale simulation protection, and save error isolation. Keep preview rendering, output layer management, and file export behavior covered by targeted pytest tests.

**Tech Stack:** Python 3.13, NumPy, PySide/Qt via qtpy, napari layer services, OpenImageIO/exiv2 metadata helpers, pytest through `uv run --extra dev pytest`.

---

## Product Review

The current GUI is close to a research workstation: it can load RAW or processed images, build a preview stack, run preview or full scan, update output layers, and save rendered files with color metadata. For a releasable application, the main user workflow should read as:

1. Import or reprocess an input image.
2. See a fast preview with reliable layer state.
3. Adjust profiles and controls.
4. Run a full scan for final output.
5. Save/export the result without losing the output because optional metadata transfer failed.

The GUI should avoid publishing a result from the wrong input. If a user loads or rotates a file while a preview/scan is running, the old worker result must not overwrite the new input stack or become the output that later gets saved. This is the highest-risk release bug in the preview system.

The action bar should communicate readiness. Preview and scan are unavailable before an input exists. Save is unavailable before a visible output layer exists. During a running simulation, preview/scan/save are temporarily disabled. This is a low-cost UX improvement that prevents common invalid operations instead of relying only on warning dialogs.

*(Note 2026-05-25: A dedicated "HDR Export Settings" panel was added for Dual-Layer HDR Mapping. These new parameters—`hdr_diffuse_lift_strength`, `graft_strength`, etc.—must also be tracked properly by the readiness and state synchronization systems.)*

The file transfer/export path should treat metadata copy as best effort. Pixel output is the product-critical artifact; reading or writing source metadata should not prevent saving the rendered image. Metadata failures should be surfaced in the status bar after the pixel file is written.

## Code Review Findings

1. `src/spektrafilm_gui/controller.py` has no input generation guard around asynchronous `SimulationWorker` completion. `_on_simulation_finished()` always writes the result layer, even if `_current_input_image` was replaced while the worker was running.
2. `src/spektrafilm_gui/controller.py` handles metadata write errors after saving, but `read_image_metadata(self._current_input_path)` happens before `save_image_oiio()` and is not guarded. A metadata read failure can block file saving.
3. `src/spektrafilm_gui/controller_runtime.py` and `src/spektrafilm_gui/app.py` catch only ordinary exception subclasses at Qt worker boundaries. Previous crash analysis for this repository identified `BaseException` escaping `QRunnable.run()` as a process-abort risk.
4. `src/spektrafilm_gui/controller.py` enables and disables all simulation action buttons only while a worker runs. It does not reflect whether preview/scan/save are currently actionable.

## File Structure

- Modify `tests/gui/test_controller_flow.py`
  - Add stale async result coverage and action-button readiness coverage.
- Modify `tests/gui/test_controller_output.py`
  - Add metadata read failure export coverage.
- Modify `tests/gui/test_controller_runtime_module.py`
  - Add `BaseException` worker-boundary coverage for simulation workers.
- Modify `tests/gui/test_app.py`
  - Add `BaseException` worker-boundary coverage for background warmup.
- Modify `src/spektrafilm_gui/controller.py`
  - Add input-generation tracking, stale result discard, metadata read isolation, and action-state synchronization.
- Modify `src/spektrafilm_gui/controller_runtime.py`
  - Catch `BaseException` at `SimulationWorker.run()`.
- Modify `src/spektrafilm_gui/app.py`
  - Catch `BaseException` at `_WarmupTask.run()`.

## Task 1: Add Failing Preview And Action-State Tests

- [ ] Add a controller-flow test that starts an async preview, mutates `_current_input_image` through `_update_preview_cache()`, then calls `_on_simulation_finished()` with the old result. Expected behavior: no output layer is written, status says the result was discarded, controls are synced back to the current input state, and pending auto-preview replay can proceed.
- [ ] Add a controller-flow test for action button readiness. Expected behavior: preview/scan disabled with no input, preview/scan enabled after input cache exists, save disabled until a visible output layer exists, and all three disabled while a simulation is active.
- [ ] Run:

```bash
uv run --extra dev pytest -q tests/gui/test_controller_flow.py::test_stale_simulation_result_is_discarded_after_input_changes tests/gui/test_controller_flow.py::test_action_buttons_reflect_input_output_and_worker_state
```

Expected RED: tests fail because the controller has no generation guard and no readiness sync method yet.

## Task 2: Add Failing Save And Worker-Boundary Tests

- [ ] Add a controller-output test where `read_image_metadata()` raises `RuntimeError("bad metadata")`. Expected behavior: `save_image_oiio()` still receives the output pixels, `write_image_metadata()` is not called with missing source metadata, and status reports that the image was saved but metadata copy failed.
- [ ] Add a simulation-worker test where `execute_request` raises `KeyboardInterrupt("stop")`. Expected behavior: the worker emits `failed` with `KeyboardInterrupt: stop` and never lets the exception escape.
- [ ] Add a warmup-task test where `warmup_fn` raises `KeyboardInterrupt("stop")`. Expected behavior: `_WarmupTask.run()` returns without raising.
- [ ] Run:

```bash
uv run --extra dev pytest -q tests/gui/test_controller_output.py::test_save_output_layer_still_saves_when_source_metadata_read_fails tests/gui/test_controller_runtime_module.py::test_simulation_worker_catches_base_exception_at_qt_boundary tests/gui/test_app.py::test_warmup_task_swallows_base_exception_boundary_failures
```

Expected RED: tests fail because metadata read is not isolated and the Qt worker boundaries do not catch `BaseException`.

## Task 3: Implement Preview Correctness And UX State

- [ ] Add `_input_generation: int` and `_active_simulation_input_generation: int | None` to `GuiController`.
- [ ] Increment `_input_generation` inside `_update_preview_cache()` after it accepts a new full-resolution input.
- [ ] Capture the current generation in `_start_simulation()` after creating the request and before starting the worker.
- [ ] In `_on_simulation_finished()`, compare the active generation to the current generation. If they differ, clear active worker state, re-enable/sync action buttons, set a concise discarded-result status when status reporting is enabled, replay pending auto-preview, and return without writing output.
- [ ] Add `_sync_action_button_state()` and call it from controller init, `_update_preview_cache()`, `_start_simulation()`, `_on_simulation_finished()`, `_on_simulation_failed()`, and stale-discard handling.
- [ ] Keep `_set_simulation_controls_enabled()` as the low-level helper used by `_sync_action_button_state()` so existing tests and simple widget stubs keep working.

## Task 4: Implement Save And Worker-Boundary Hardening

- [ ] Wrap source metadata reading in `save_output_layer()` with the same best-effort semantics as metadata writing.
- [ ] Save pixels even when source metadata cannot be read.
- [ ] If metadata read fails, skip metadata writing and report `Saved output image to <path>, but failed to copy metadata: <error>`.
- [ ] Catch `BaseException` in `SimulationWorker.run()` and `_WarmupTask.run()`.
- [ ] Format worker failure messages as the existing path does: `<ExceptionType>: <message>`.

## Verification

- [ ] Run all modified targeted tests:

```bash
uv run --extra dev pytest -q tests/gui/test_controller_flow.py tests/gui/test_controller_output.py tests/gui/test_controller_runtime_module.py tests/gui/test_app.py
```

- [ ] Run the full GUI test suite:

```bash
uv run --extra dev pytest -q tests/gui
```

- [ ] Run the full repository suite:

```bash
uv run --extra dev pytest -q
```

- [ ] Self-review the implementation against the code review findings. If any finding lacks a test or implementation path, add the missing test first, then patch.

## Confidence Loop

Before calling the goal complete, answer these checks from fresh evidence:

- Can an old preview/scan worker write an output layer after the input changed? The answer must be no, proven by a test.
- Can metadata read or write failure prevent saving the rendered pixels? The answer must be no, proven by tests.
- Can `BaseException` escape a Qt `QRunnable.run()` boundary used by preview/scan or warmup? The answer must be no, proven by tests.
- Do GUI action buttons reflect whether input/output work is currently possible? The answer must be yes, proven by tests.
- Do existing GUI tests and the full repository suite still pass under `uv run --extra dev pytest`? The answer must come from fresh command output.
