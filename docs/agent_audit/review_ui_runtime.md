# UI, Runtime & Threading Risk Review

> Generated 2026-05-28 — Review-only pass (no code modifications)

## Scope

Files reviewed:
- `src/spektrafilm_gui/controller.py` (1136 LOC — main GUI controller)
- `src/spektrafilm_gui/controller_runtime.py` (323 LOC — simulation worker, display transforms)
- `src/spektrafilm_gui/controller_layers.py` (712 LOC — napari layer management, animations)
- `src/spektrafilm_gui/state.py` (398 LOC — GUI state dataclasses)
- `src/spektrafilm_gui/app.py` (319 LOC — application bootstrap, signal wiring)
- `src/spektrafilm/runtime/api.py` (24 LOC — compatibility re-exports)
- `src/spektrafilm/runtime/process.py` (181 LOC — Simulator class, Metal serialization)
- `src/spektrafilm/runtime/pipeline.py` (693 LOC — core simulation pipeline)

Supporting files reviewed for cross-references:
- `src/spektrafilm_gui/state_bridge.py`, `src/spektrafilm_gui/params_mapper.py`
- `src/spektrafilm/gpu/metal_serialization.py`

---

## Findings

### UI-001: Window close while simulation running causes crash

**Severity:** P1
**File:Function:Line:** `controller.py:_on_simulation_finished:1069`, `controller.py:_on_simulation_failed:1095`

**Description:**
`GuiController` has no shutdown/cleanup method. When the user closes the napari main window while a `SimulationWorker` is still executing on the `QThreadPool`, the worker completes and its `finished`/`failed` signal fires. The slot runs on the GUI thread, but `self` (`GuiController`) may already be partially destroyed. Accessing `self._viewer`, `self._widgets`, or calling `set_status()` / `QMessageBox.critical()` on a destroyed viewer causes a RuntimeError or segfault.

The global `QThreadPool.globalInstance()` does not automatically cancel pending or running `QRunnable`s when the application shuts down.

**Reproduction:**
1. Load a large image.
2. Click "Scan" (full-resolution simulation).
3. Immediately close the main window before the simulation finishes.
4. Observe crash or RuntimeError in `_on_simulation_finished` / `_on_simulation_failed`.

**Minimal fix:**
Add a `shutdown()` method to `GuiController` that:
1. Sets a `_shutting_down = True` flag.
2. Disconnects `worker.signals.finished` and `worker.signals.failed` from the controller slots (if a worker is active).
3. Optionally calls `worker.signals.finished.disconnect()` / `worker.signals.failed.disconnect()`.
4. In `_on_simulation_finished` / `_on_simulation_failed`, early-return if `self._shutting_down`.

Connect this to the main window's `closeEvent` or napari's `viewer.close()` signal.

**Required validation:**
Manual test: close window mid-simulation, confirm no crash.

---

### UI-002: Blocking file I/O on GUI thread freezes application

**Severity:** P1
**File:Function:Line:**
- `controller.py:load_input_image:241` — `load_image_oiio(path)` is synchronous file I/O
- `controller.py:load_raw_image:267` — `load_and_process_raw_file(path, ...)` is synchronous CPU-heavy I/O
- `controller.py:save_output_layer:594` — `save_image_oiio(filepath, ...)` is synchronous file I/O + color conversion

**Description:**
All image load and save operations run synchronously on the Qt main (GUI) thread. For large images (e.g., 6000x4000 RAW files), these operations can take 2-10+ seconds, during which the entire GUI is unresponsive — no button clicks, no repaints, no cancel possible.

`load_raw_image` is particularly expensive because it includes RAW decoding (via rawpy/libraw), demosaicing, color space conversion, and optional lens correction — all on the main thread.

`save_output_layer` additionally performs synchronous colour-space conversion via `colour.RGB_to_RGB()` before writing, which can be slow for large float32 images.

**Reproduction:**
1. Load a 50+ MP RAW file.
2. The GUI freezes for several seconds during `load_raw_image`.
3. No progress bar, no cancel button, no visual feedback until complete.

**Minimal fix:**
Move `load_image_oiio`, `load_and_process_raw_file`, and `save_image_oiio` (+ color conversion) to a `QRunnable` / `QThread`, following the same pattern as `SimulationWorker`. Show a progress indicator (indeterminate spinner or status bar message) while running. Add a cancel mechanism via a flag checked by the worker.

For `save_output_layer`, the colour conversion (line 511-525) could be offloaded to a worker with a "Saving..." status message.

**Required validation:**
Manual test with a large RAW file; confirm GUI remains responsive during load/save.

---

### UI-003: `_on_simulation_failed` discards mode_label from user-facing error

**Severity:** P2
**File:Function:Line:** `controller.py:_on_simulation_failed:1095-1104`

**Description:**
When a simulation fails, the error dialog says only `"Simulation failed.\n\n{message}"`. The `mode_label` (which distinguishes "Preview" from "Scan") is captured on line 1097 but only used for the status bar message (line 1103), not in the `QMessageBox.critical` dialog (line 1102).

In contrast, `_on_simulation_finished` correctly uses `mode_label` in its status message (line 1092).

**Reproduction:**
1. Trigger a simulation that will fail (e.g., corrupt parameters).
2. The error dialog says "Simulation failed" — user cannot tell if it was Preview or Scan.

**Minimal fix:**
Change line 1102 from:
```python
QMessageBox.critical(dialog_parent(self._viewer), 'Run simulation', f'Simulation failed.\n\n{message}')
```
to:
```python
QMessageBox.critical(dialog_parent(self._viewer), f'Run {mode_label.lower()}', f'{mode_label} failed.\n\n{message}')
```

**Required validation:**
Trigger a failed preview and a failed scan; confirm dialog titles differ.

---

### UI-004: Warmup task silently swallows all exceptions including fatal ones

**Severity:** P2
**File:Function:Line:** `app.py:_WarmupTask.run:104-108`

**Description:**
The background warmup task catches `BaseException` (which includes `KeyboardInterrupt`, `SystemExit`, `MemoryError`) and silently returns. If the warmup encounters a fatal error (e.g., out of memory creating the simulator), the user gets no feedback — the app simply starts without warmup having completed, and the first user-triggered simulation pays the full cold-start cost.

```python
def run(self) -> None:
    try:
        self._warmup_fn()
    except BaseException:
        return  # All exceptions silently eaten
```

**Minimal fix:**
At minimum, log the exception:
```python
except Exception as exc:
    logging.getLogger(__name__).debug("Background warmup failed: %s", exc)
    return
```
Change `BaseException` to `Exception` so `KeyboardInterrupt`/`SystemExit` propagate normally.

**Required validation:**
Inject a deliberate failure in `_warmup_full_gui`; confirm it is logged.

---

### UI-005: Stale `_active_simulation_worker` reference holds memory after completion

**Severity:** P2
**File:Function:Line:** `controller.py:_start_simulation:1057-1067`

**Description:**
After `self._thread_pool.start(worker)` (line 1067), the controller holds a strong reference to the `SimulationWorker` via `self._active_simulation_worker` (line 1060). The worker itself holds a strong reference to the `SimulationRequest` (which contains the full input `image` numpy array) and, after completion, the `SimulationResult` (which contains both `display_image` and `float_image`).

The reference is only cleared when `_on_simulation_finished` or `_on_simulation_failed` runs (lines 1073, 1096). Between the worker's `run()` completing and the signal being delivered to the GUI thread (via queued connection), the worker and all its data remain alive.

Additionally, the `SimulationWorker` is a `QRunnable` without a parent. After completion, `QThreadPool` does not call `deleteLater()` on it — it relies on garbage collection. If the controller holds the reference, the worker (and its ~100MB+ of image data) persists until the next simulation or controller destruction.

**Minimal fix:**
In `_on_simulation_finished` / `_on_simulation_failed`, after clearing `self._active_simulation_worker`, also set `self._active_simulation_worker = None` (already done) and consider explicitly deleting the request's image reference. The current code already does `self._active_simulation_worker = None`, which is correct — the issue is the timing gap.

**Required validation:**
Run a simulation, then check `gc.get_referrers(worker)` before the signal is delivered; confirm the worker is collected after the handler runs.

---

### UI-006: `_clear_output_layer_large_metadata` does not clear HDR scene energy metadata

**Severity:** P3
**File:Function:Line:** `controller_layers.py:_clear_output_layer_large_metadata:489-492`

**Description:**
When the output layer is hidden, `_clear_output_layer_large_metadata` is called (line 474). It only removes `output_float_data_key` but retains `hdr_scene_energy_metadata_key` (which contains `HDRSceneEnergyMetadata` — a dataclass holding multiple float32 arrays: `scene_luminance`, `profile_scene_y`, `profile_look_y`, `scene_rgb`).

For a 4K image, `scene_luminance` alone is ~24MB (3840x2160x4 bytes). With `scene_rgb`, that doubles. These arrays are kept in napari layer metadata even when the output layer is hidden and no longer needed.

**Minimal fix:**
Also clear the HDR metadata:
```python
def _clear_output_layer_large_metadata(self, layer: NapariImageLayer) -> None:
    for key in (self.output_float_data_key, self.hdr_scene_energy_metadata_key, self.hdr_scene_luminance_key):
        layer.metadata.pop(key, None)
```

**Required validation:**
Run a simulation with HDR EXR output enabled, hide the output layer, check `layer.metadata` keys.

---

### UI-007: Animation closure captures mutable state, creating a reference cycle

**Severity:** P3
**File:Function:Line:** `controller_layers.py:_start_output_layer_animation:564-578`

**Description:**
The `_tick()` closure (line 564) captures `self` (the `ViewerLayerService`), `layer`, `generation`, `output_image`, `state`, `frame_times`, and `current_index` (via `nonlocal`). The closure is connected to `timer.timeout` (line 579). The timer is stored in `self._output_animations` (line 580). This creates a cycle: `self` -> `_output_animations` -> handle -> timer -> signal -> `_tick` closure -> `self`.

The same pattern exists in `_start_output_layer_crossfade` (line 627).

Python's cyclic GC will eventually collect this, but until collection runs, the entire chain (including `output_image`/`final_image` numpy arrays) stays alive. The `_stop_output_layer_animation` method breaks the cycle by stopping the timer and calling `deleteLater()` (lines 672-677), which disconnects the signal — but only if `_stop` is actually called.

**Minimal fix:**
In `_stop_output_layer_animation`, also explicitly disconnect the timeout signal before calling `deleteLater()`:
```python
timeout_signal = getattr(timer, 'timeout', None)
if timeout_signal is not None:
    try:
        timeout_signal.disconnect()
    except (RuntimeError, TypeError):
        pass
```
This is already implicitly done by `deleteLater()` in most Qt implementations, but explicit disconnect is more robust.

**Required validation:**
Start an animation, let it complete, verify the closure and numpy arrays are collected (e.g., via `weakref`).

---

### UI-008: Stale simulation result can be displayed when input generation changes during signal delivery

**Severity:** P2
**File:Function:Line:** `controller.py:_on_simulation_finished:1069-1093`

**Description:**
The input-generation guard (lines 1077-1081) correctly discards stale results:
```python
if active_input_generation is not None and active_input_generation != self._input_generation:
    # discard stale result
```

However, `_on_simulation_finished` first reads `self._active_simulation_reports_status` (line 1070) and `self._active_simulation_label` (line 1071) before clearing them (lines 1073-1076). If `_start_simulation` is called between the signal emission from the worker thread and its delivery on the GUI thread, these fields could have been overwritten by the new simulation's values.

In practice, `_start_simulation` checks `self._active_simulation_worker is not None` (line 1024) and returns early if a worker is running. Since the worker reference is only cleared in the signal handler, a new simulation cannot start until the handler runs. So this race is prevented by the existing guard — but only because the guard is on the GUI thread.

If the guard were ever relaxed (e.g., to allow cancel-and-restart), this race would manifest.

**Minimal fix:**
Capture the stale fields into local variables at the very start of the handler (already done for `active_input_generation`). The current code is correct for the current concurrency model. Document the invariant: "Only one simulation may be active at a time; the `_active_simulation_worker is not None` check in `_start_simulation` is the serialization point."

**Required validation:**
Code review confirmation — no test needed unless the concurrency model changes.

---

### UI-009: `save_output_layer` uses live GUI state for color conversion, not simulation-time state

**Severity:** P2
**File:Function:Line:** `controller.py:save_output_layer:428-525`

**Description:**
`save_output_layer` reads the current GUI widget state (via `collect_gui_state`) at save time, not at simulation time. The `source_color_space` and `source_cctf_encoding` are read from the output layer's metadata (correct), but the `saving_color_space` and `saving_cctf_encoding` are read from the live GUI widgets (lines 485-490).

If the user changes `output_color_space` or `saving_cctf_encoding` between running the simulation and saving, the color conversion will use the new values, potentially producing a file that doesn't match what was displayed.

Additionally, `hdr_exr_output` (line 448) and `hdr_export` settings (lines 558-574) are read from live GUI state at save time, not stored in the simulation metadata. If the user adjusts HDR export knobs between simulation and save, the exported file uses the new settings with the old pixel data.

**Minimal fix:**
Store the `saving_color_space`, `saving_cctf_encoding`, and relevant HDR export settings in the output layer's metadata alongside the float data. On save, prefer the stored values over the live GUI state (fall back to GUI state only if metadata is missing, for backward compatibility with old sessions).

**Required validation:**
Run a simulation, change `output_color_space`, save — confirm the file uses the simulation-time color space, not the new one.

---

### RUNTIME-001: `_runtime_simulator` cleared in worker thread without synchronization

**Severity:** P3
**File:Function:Line:** `controller.py:_process_image_with_runtime:948-949`

**Description:**
When the simulation raises an exception, `self._runtime_simulator = None` is executed in the worker thread (line 949). The `_runtime_simulator` field is also read from the GUI thread in `_process_image_with_runtime` (lines 927-928, 935-936) — but since `_process_image_with_runtime` is only called from `SimulationWorker.run()` (worker thread), and only one worker runs at a time (guarded by `_active_simulation_worker`), there is no concurrent read/write.

The `serialized_metal_runtime` lock in `process.py` serializes Metal GPU operations but does not protect `controller.py` fields.

**Current risk:** None — the single-worker guard prevents concurrent access. But if the concurrency model ever changes (e.g., cancel-and-restart, or multiple concurrent workers), this becomes a data race.

**Minimal fix:**
Add a comment documenting the invariant: "Only one simulation worker runs at a time; `_active_simulation_worker` check in `_start_simulation` is the serialization point for all `_runtime_simulator` access."

**Required validation:**
Code review confirmation.

---

### RUNTIME-002: `SimulationPipeline` mutable state not protected by any lock for non-Metal backends

**Severity:** P3
**File:Function:Line:** `pipeline.py:process:307`, `process.py:process:29`

**Description:**
`SimulationPipeline.process()` mutates `self.timings` (line 309: `self.timings.clear()`) and `self._last_elapsed_time` (line 322). These mutations happen in the worker thread.

The `serialized_metal_runtime` lock in `Simulator.process()` only protects Metal GPU backends. For CPU backends (numpy), no lock is held.

Since only one worker runs at a time (controller-level guard), this is safe. But `SimulationPipeline` itself has no thread-safety guarantees — if used from multiple threads (e.g., in a web service), it would be unsafe.

**Minimal fix:**
No code change needed for the GUI use case. Add a docstring note to `SimulationPipeline.process()`: "Not thread-safe. Callers must serialize access."

**Required validation:**
Code review confirmation.

---

### RUNTIME-003: `soft_update` modifies shared pipeline state without lock for non-Metal backends

**Severity:** P3
**File:Function:Line:** `pipeline.py:soft_update:539-582`, `process.py:soft_update:74-85`

**Description:**
`Simulator.soft_update()` modifies `self.camera.exposure_compensation_ev`, `self.enlarger.print_exposure`, `self.film.data.density_curves`, etc. For Metal backends, the `serialized_metal_runtime` lock is held. For CPU backends, no lock is held.

The `soft_update` method is not currently called from `GuiController` (only `update_params` is used), so this is not an active risk in the GUI. But the API is public and could be called from a different thread.

**Minimal fix:**
Same as RUNTIME-002: add a thread-safety note to the docstring.

**Required validation:**
Code review confirmation.

---

### UI-010: `output_layer()` returns `None` for hidden output layer, blocking save of cached data

**Severity:** P3
**File:Function:Line:** `controller_layers.py:output_layer:458-462`

**Description:**
`output_layer()` returns `None` if the layer exists but is not visible:
```python
def output_layer(self) -> NapariImageLayer | None:
    layer = self.image_layer(OUTPUT_LAYER_NAME)
    if layer is None or not layer.visible:
        return None
    return layer
```

When a new input image is loaded, the output layer is hidden (line 442 of `set_or_add_input_preview_layer`). After this, `_visible_output_layer_available()` returns `False`, disabling the save button. The float data and metadata are still in the layer (unless cleared by `remove_layer`), but the user cannot save without re-running the simulation.

This is arguably by design (the old output is stale relative to the new input), but it means:
- User runs simulation on image A -> output shown.
- User loads image B -> output hidden, save button disabled.
- User cannot save the output from image A without re-loading image A and re-running.

**Minimal fix:**
If this is intentional, document it. If not, `output_layer()` could return the layer regardless of visibility, and `_visible_output_layer_available()` could check for layer existence only.

**Required validation:**
UX decision — no code change needed if intentional.

---

### UI-011: `_set_editor_value_silently` does not handle `setattr` failure gracefully

**Severity:** P3
**File:Function:Line:** `controller.py:_set_editor_value_silently:772-784`

**Description:**
If `setattr(editor, 'value', value)` raises (e.g., due to a type mismatch or read-only property), the `finally` block correctly restores `blockSignals`. However, the exception propagates up to `_apply_loaded_input_encoding` (line 757), which has no try/except — so the exception would propagate to `load_input_image` or `load_raw_image`.

In `load_input_image` (line 241), there's no try/except around `_apply_loaded_input_encoding` (line 249). If the encoding application fails, the entire load operation fails and the exception reaches the caller unhandled.

**Minimal fix:**
Wrap the `setattr` call in a try/except:
```python
try:
    setattr(editor, 'value', value)
except (AttributeError, TypeError, ValueError):
    pass
```
This is consistent with the defensive `getattr`/`callable` pattern used throughout the codebase.

**Required validation:**
Pass an invalid value type to `_set_editor_value_silently`; confirm no crash.

---

### UI-012: `_connect_auto_preview_signal` may silently skip widgets with no standard signal

**Severity:** P3
**File:Function:Line:** `app.py:_connect_auto_preview_signal:196-207`

**Description:**
The function tries to connect to `toggled`, `currentTextChanged`, or `valueChanged` signals in that order. If a widget has none of these signals, the function silently returns without connecting. Any custom widget that uses a non-standard signal name (e.g., `textChanged`, `editingFinished`) would not trigger auto-preview.

This is not a bug per se — it's the design intent to match standard Qt widget signals. But it means adding a new widget type with a non-standard signal requires updating this function.

**Minimal fix:**
Add a debug log when no signal is found:
```python
for signal_name in ('toggled', 'currentTextChanged', 'valueChanged'):
    ...
# If we get here, no signal was found
logging.getLogger(__name__).debug("No auto-preview signal found for %s", type(widget).__name__)
```

**Required validation:**
Add a widget with a non-standard signal; confirm the debug log appears.

---

## Summary Table

| ID | Severity | Category | Summary |
|----|----------|----------|---------|
| UI-001 | P1 | Crash | Window close mid-simulation crashes on signal delivery to destroyed controller |
| UI-002 | P1 | GUI freeze | All file I/O (load RAW, load image, save image) blocks main thread |
| UI-003 | P2 | UX | Error dialog discards mode_label, says "Simulation failed" without context |
| UI-004 | P2 | Robustness | Warmup task catches BaseException silently, including MemoryError |
| UI-005 | P2 | Memory | Stale worker reference holds ~100MB+ image data until next simulation |
| UI-006 | P3 | Memory | HDR scene energy metadata (~48MB) not cleared when output layer hidden |
| UI-007 | P3 | Memory | Animation closure creates reference cycle with viewer service |
| UI-008 | P2 | Correctness | Stale simulation fields could be read if concurrency model changes |
| UI-009 | P2 | Correctness | Save uses live GUI state for color space, not simulation-time state |
| UI-010 | P3 | UX | Hidden output layer prevents saving cached simulation results |
| UI-011 | P3 | Robustness | `setattr` failure in silent editor update propagates unhandled |
| UI-012 | P3 | Debugging | Widgets with non-standard signals silently skipped for auto-preview |
| RUNTIME-001 | P3 | Thread safety | `_runtime_simulator` cleared in worker without lock (safe due to single-worker guard) |
| RUNTIME-002 | P3 | Thread safety | `SimulationPipeline` mutable state unprotected for non-Metal backends |
| RUNTIME-003 | P3 | Thread safety | `soft_update` modifies pipeline state without lock for non-Metal backends |

---

## Architecture Notes

### Threading Model

The GUI uses Qt's `QThreadPool.globalInstance()` for simulation workers. The threading model is:

1. **GUI thread (main):** All widget reads/writes, signal/slot delivery, `collect_gui_state`, `build_params_from_state`.
2. **Worker threads:** `SimulationWorker.run()` → `GuiController._execute_simulation_request` → `Simulator.process()` → `SimulationPipeline.process()`.
3. **Warmup thread pool:** Separate `QThreadPool` (max 1 thread) for startup warmup. No interaction with simulation workers.

Cross-thread communication is via `Signal(object)` / `Signal(str)` with `Qt::AutoConnection` (default). Since the receiver (`GuiController`) lives on the GUI thread, signals emitted from worker threads are queued and delivered on the GUI thread.

### Serialization Points

- **Single-worker guard:** `self._active_simulation_worker is not None` check in `_start_simulation` (line 1024) ensures only one simulation runs at a time. This is the primary serialization mechanism for all controller state.
- **Metal runtime lock:** `serialized_metal_runtime()` in `process.py` uses a `threading.RLock` to serialize MLX/Metal GPU operations. This is only relevant for Metal backends.
- **No lock for CPU backends:** For numpy/CuPy backends, no lock is held during simulation. This is safe because of the single-worker guard.

### Signal Connection Map

| Source | Signal | Slot | Thread |
|--------|--------|------|--------|
| `worker.signals.finished` | `Signal(object)` | `_on_simulation_finished` | Worker → GUI (queued) |
| `worker.signals.failed` | `Signal(str)` | `_on_simulation_failed` | Worker → GUI (queued) |
| `filepicker.load_requested` | `Signal(str)` | `load_input_image` | GUI → GUI |
| `load_raw.load_requested` | `Signal(str)` | `load_raw_image` | GUI → GUI |
| `simulation.preview_requested` | `Signal()` | `run_preview` | GUI → GUI |
| `simulation.scan_requested` | `Signal()` | `run_scan` | GUI → GUI |
| `simulation.save_requested` | `Signal()` | `save_output_layer` | GUI → GUI |
| Various widget signals | `toggled`/`valueChanged`/`currentTextChanged` | `request_auto_preview` | GUI → GUI |

All signal connections are made in `app.py:connect_controller_signals` (line 230) and `app.py:connect_auto_preview_signals` (line 210). No signals are disconnected during normal operation.
