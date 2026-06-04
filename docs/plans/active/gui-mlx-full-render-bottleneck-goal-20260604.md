# GUI MLX Full Render Bottleneck Goal - 2026-06-04

> **For agentic workers:** REQUIRED SUB-SKILLS: Use `superpowers:systematic-debugging`, `superpowers:test-driven-development`, and `superpowers:verification-before-completion`. This plan is the pre-edit contract for the 2026-06-04 GUI MLX full-render bottleneck pass.

**Goal:** Remove confirmed safe GUI full-render bottlenecks for MLX float32 Scan/full render while preserving CPU/default SDR behavior, HDR HEIC metadata safety, and existing public runtime output semantics.

**Architecture:** Keep the runtime public API materialized as NumPy arrays and avoid a backend-resident rewrite. The safe changes are at GUI request preparation, metadata selection, worker post-processing, layer metadata/crossfade policy, and benchmark observability.

**Tech Stack:** Python 3.13, NumPy, Qt/napari GUI controller, Spektrafilm runtime pipeline, MLX float32 backend, pytest, `uv run --extra dev`, `.venv/bin/python` fallback.

---

## Current Full Render Call Chain

1. `GuiController.run_scan()` calls `_start_simulation(source_layer_name="input", mode_label="Scan")`.
2. `_start_simulation()` reads `_current_input_image`, collects GUI state, builds runtime params, and currently calls `np.double(image_data)` before creating `SimulationRequest`.
3. `SimulationWorker.run()` calls `GuiController._execute_simulation_request()`.
4. `controller_runtime.execute_simulation_request()` calls `_process_image_with_runtime()`.
5. `_process_image_with_runtime()` digests params, creates or updates `Simulator`, and currently always calls `process_with_metadata(image_data)`.
6. `SimulationPipeline.process_with_metadata()` runs `_preprocess_base()`, computes HDR scene luminance, runs film/print/scan stages, and `_materialize_output()` returns `np.asarray(..., dtype=np.float64)`.
7. `execute_simulation_request()` calls `prepare_output_display_image(scan, ...)`, then calls `np.asarray(scan)` again for `float_image`.
8. `_on_simulation_finished()` calls `_set_or_add_output_layer(display_image, float_image=...)`.
9. `ViewerLayerService.set_or_add_output_layer()` may copy visible layer data for crossfade, sets the display layer, and `set_output_layer_metadata()` currently stores `np.asarray(float_image, dtype=np.float32)`.

## Confirmed Bottlenecks

1. `src/spektrafilm_gui/controller.py`
   - `_start_simulation()` and `_run_simulation()` still force full-size `np.double(image_data)` before runtime dispatch.
   - This is directly harmful for MLX float32 and creates a full-size CPU float64 copy before the runtime.
2. `src/spektrafilm_gui/controller.py`
   - `_process_image_with_runtime()` always calls `process_with_metadata()`.
   - Ordinary SDR preview/Scan does not need HDR scene sidecars; HEIC/HEIF gain-map export does.
3. `src/spektrafilm_gui/controller_runtime.py`
   - Worker post-processing already has phase timings, but display preparation runs before the float image variable is normalized to a single array reference.
   - `np.asarray(scan)` is usually view-only for NumPy output, but the code does not record copy/materialization status or memory estimates.
4. `src/spektrafilm_gui/controller_layers.py`
   - `set_output_layer_metadata()` always dtype-converts to float32. If `float_image` is already float32, this can be copy-free; if runtime output is float64, it is still one intentional save/export copy.
   - Crossfade source copying is already pixel-thresholded by `_supports_output_layer_crossfade()`, but tests should lock the large-output no-crossfade behavior.
5. `src/spektrafilm/runtime/pipeline.py`
   - `_preprocess_base()` and `_materialize_output()` still force float64. This can erase some GUI-side MLX float32 benefit, but changing this runtime boundary risks CPU reference and old API semantics. This pass will document it and only add evidence unless tests prove a tiny safe change.
6. `src/spektrafilm/runtime/services/resize.py`
   - Crop/resize remain NumPy/skimage boundaries. They are part of preprocessing and are not a safe first edit for this GUI-specific pass.

## Safe Fixes For This Pass

### P0: GUI Input Preparation

- Add a small helper in `controller.py` to prepare simulation input arrays.
- For `settings.compute_backend == "mlx"` and `settings.gpu_precision == "float32"`, pass `np.asarray(image_data[..., :3], dtype=np.float32)`.
- For all other backends/default legacy paths, preserve `np.double(image_data)`.
- Record:
  - `gui.input_prepare`
  - `gui.input_dtype_convert`
  - `gui.input_copy`
- Apply the same helper to `_run_simulation()`.

### P1: HDR Metadata Selection

- Add a conservative GUI helper that decides when runtime metadata is needed.
- Request metadata when `gui_state.hdr.hdr_heic_gain_map_enabled` is true, because the user may save HEIC/HEIF after a Scan.
- Ordinary non-HDR runs call `Simulator.process()`.
- Preserve the current HEIC/HEIF save-time error if metadata is missing for profile-aware or film-scan-aware HDR export.

### P2: Worker Post-Processing Materialization

- Normalize `scan_array = np.asarray(scan)` once in `execute_simulation_request()`.
- Pass `scan_array` to display preparation and `float_image`.
- Record whether the array shares memory with NumPy scan output when practical.
- Add memory estimates for input, float output, display output, and metadata copy candidates.

### P3: Display Preparation Timing

- Keep visual behavior unchanged.
- Add split timings inside `prepare_output_display_image()` through an optional `phase_timings` dictionary:
  - `gui.display_uint8`
  - `gui.display_transform`
- Keep existing `gui.display_prepare` around the whole call.
- Do not implement display-sized previews in this pass because napari layer and save/export semantics currently expect full-size output layer data.

### P4: Layer Metadata And Animation Copies

- Make `set_output_layer_metadata()` preserve an existing float32 NumPy array without dtype conversion copy where possible.
- Return or record layer metadata copy bytes so the benchmark can report it.
- Add a regression test proving large visible output updates do not start crossfade and do not copy the old full-size layer data.
- Keep small-output animation/crossfade behavior unchanged.

### P5: Runtime Boundaries

- Do not rewrite `_preprocess_base()` or `_materialize_output()` in this pass unless a failing test exposes a local no-risk edit.
- Document runtime float64 materialization as the main remaining MLX boundary.

### P6: Benchmark Evidence

- Add `tools/benchmark_gui_mlx_full_render.py`.
- The script will simulate the GUI worker path headlessly with synthetic images and the real controller/runtime helpers.
- It will run warmup 1 and measured 3 by default.
- It will output JSON plus Markdown under `docs/reports/gui-mlx-full-render-benchmark-20260604.*`.
- It will report:
  - backend and precision
  - input dtype/shape/nbytes
  - phase timings
  - runtime stage timings
  - display/float/metadata memory estimates
  - median/min/max
  - speed comparison when both CPU and MLX runs complete

## Tests

Add or update tests before production edits:

- `tests/gui/test_controller_flow.py`
  - MLX float32 `_start_simulation()` request image is float32, not float64.
  - CPU/default `_start_simulation()` request image stays float64.
  - `_run_simulation()` uses the same input preparation policy.
  - ordinary SDR `_process_image_with_runtime()` calls `process()`, not `process_with_metadata()`.
  - HDR HEIC-enabled `_process_image_with_runtime()` calls `process_with_metadata()` and returns sidecar.
- `tests/gui/test_controller_runtime_module.py`
  - `execute_simulation_request()` reuses a single materialized NumPy scan array for display and float output.
  - display split timings and memory estimates are present.
- `tests/gui/test_controller_layers.py` and `tests/gui/test_controller_layers_animation.py`
  - float32 metadata is stored without an avoidable dtype conversion copy.
  - large output update skips crossfade/animation.
- `tests/test_mlx_runtime_hotpath_benchmark.py`
  - benchmark helpers parse backend/precision and compute median/min/max.

## Benchmark Method

Commands planned:

```bash
uv run python tools/benchmark_gui_mlx_full_render.py --backend cpu --size 512x384 --warmups 1 --runs 3
uv run python tools/benchmark_gui_mlx_full_render.py --backend mlx --precision float32 --size 512x384 --warmups 1 --runs 3
uv run python tools/benchmark_gui_mlx_full_render.py --backend mlx --precision float32 --size 1600x1200 --warmups 1 --runs 3
```

If `uv` cannot run because of local environment issues, use `.venv/bin/python` for the same commands and record that substitution.

## Validation Matrix

Required before completion:

```bash
uv run --extra dev pytest tests/gui/test_controller_flow.py tests/gui/test_controller_runtime_module.py tests/gui/test_controller_layers.py tests/gui/test_controller_layers_animation.py tests/test_mlx_runtime_hotpath_benchmark.py -q
uv run --extra dev pytest tests -k "gui or controller or runtime or mlx or gpu or pipeline"
uv run python tools/benchmark_gui_mlx_full_render.py --backend cpu
uv run python tools/benchmark_gui_mlx_full_render.py --backend mlx --precision float32
git diff --check
grep -R "np.double(image_data)\|np.asarray(scan)\|process_with_metadata" src/spektrafilm_gui src/spektrafilm/runtime -n
```

If the broad pytest slice stalls or fails for environment reasons, run targeted slices first, record the blocker, and keep the final report honest.

## Rollback Points

- Revert input preparation helper if CPU/default paths no longer preserve float64 behavior.
- Revert metadata selection if HDR HEIC tests fail or scene sidecar persistence breaks.
- Revert display timing injection if it changes preview image values.
- Revert layer metadata optimization if save/export no longer sees `pipeline_float_output`.
- Leave runtime float64 preprocessing/materialization untouched unless fully validated.

## Risks And Guardrails

- MLX float32 input may still become float64 inside `_preprocess_base()`; this is expected and must be reported as remaining runtime debt.
- HDR HEIC export after an ordinary SDR run may still lack sidecars. The policy will request metadata when HDR HEIC export is enabled in GUI state, and save-time error remains for missing metadata.
- Display transform is color-sensitive; only timing and array reuse are allowed here.
- Large-output animation changes must only disable extra copies for images already above `OUTPUT_LAYER_ANIMATION_MAX_PIXELS`.

## Self-Audit Loop

Before completion, ask:

- Does GUI full render still copy full-size input to float64 before the worker for MLX float32?
- Does ordinary non-HDR Scan still calculate HDR scene luminance?
- Does worker post-processing materialize scan more than once?
- Does layer metadata still make an avoidable float32 copy?
- Can large output still start crossfade and copy existing full-size layer data?
- Are GUI phase timings split enough to separate input, runtime, display, materialize, layer, and metadata costs?
- Did any change alter CPU/default SDR output semantics?
- Is HDR HEIC sidecar generation still available when enabled?

## Completion Record

Completed on 2026-06-04.

### Actual Changes

- `src/spektrafilm_gui/controller.py`
  - Added `_prepare_simulation_input_image()`.
  - MLX float32 GUI requests now pass a 3-channel float32 array without the old pre-worker `np.double(image_data)` copy.
  - CPU/default paths still use the legacy `np.double(image_data)` conversion.
  - `_process_image_with_runtime()` now calls `process()` by default and `process_with_metadata()` only when requested.
  - `_start_simulation()` requests HDR metadata when GUI HDR HEIC gain-map export is enabled.
  - `_run_simulation()` uses the same input-preparation and metadata-selection policy.
- `src/spektrafilm_gui/controller_runtime.py`
  - `SimulationRequest` and `SimulationResult` now carry memory estimates and the HDR metadata request bit.
  - Worker post-processing materializes `scan` once into `scan_array`, uses that same object for display prep and `float_image`, and records copy/memory estimates.
  - Display prep records `gui.display_uint8` and `gui.display_transform` when a timing dictionary is provided.
- `tools/benchmark_gui_mlx_full_render.py`
  - New headless GUI-like benchmark for CPU and MLX float32 full-render worker paths.
- Tests added/updated:
  - GUI input dtype and metadata routing.
  - Worker single materialization and memory estimates.
  - Display timing splits.
  - Layer metadata/crossfade copy guardrails.
  - Benchmark helper contract.
- Documentation/report:
  - Added `docs/reports/gui-mlx-full-render-benchmark-20260604.md` plus per-backend artifacts.

### Validation Commands And Results

Passed:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run --extra dev pytest tests/gui/test_controller_flow.py tests/gui/test_controller_runtime_module.py tests/gui/test_controller_layers.py tests/gui/test_controller_layers_animation.py tests/test_gui_mlx_full_render_benchmark.py -q
# 63 passed

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run --extra dev pytest tests/test_runtime_api.py tests/test_gpu_backend.py tests/test_gpu_pipeline.py tests/test_gpu_validate.py tests/test_mlx_runtime_hotpath_benchmark.py tests/test_gui_mlx_full_render_benchmark.py -q
# 54 passed, 2 skipped

uv run python -m compileall -q src/spektrafilm_gui tools/benchmark_gui_mlx_full_render.py

uv run python tools/benchmark_gui_mlx_full_render.py --backend cpu

uv run python tools/benchmark_gui_mlx_full_render.py --backend mlx --precision float32

git diff --check
```

The requested broad slice was also run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run --extra dev pytest tests -k "gui or controller or runtime or mlx or gpu or pipeline" -q
```

Result: 400 passed, 7 skipped, 6 failed, 1127 deselected. The stable failures were in existing pipeline/regression baseline tests and one order-sensitive spectral-LUT test during the broad run. Re-running the failing subset reproduced the pipeline/regression baseline mismatches but not the spectral-LUT failure:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run --extra dev pytest tests/test_pipeline_smoke.py::test_midgray_input_produces_expected_output_values tests/test_regression_baselines.py::TestRegressionBaselines::test_pipeline_snapshot tests/test_spectral_lut_service.py::test_spectral_compute_gpu_lut_path_returns_backend_result_without_numpy_transfer -q
# 5 failed, 2 passed
```

These failures are outside the touched GUI files and reflect current runtime/baseline state, not this GUI hot-path change.

### Grep Audit

Source-only command:

```bash
grep -R --exclude-dir=__pycache__ "np.double(image_data)\|np.asarray(scan)\|process_with_metadata" src/spektrafilm_gui src/spektrafilm/runtime -n
```

Results and interpretation:

- `src/spektrafilm_gui/controller.py:164`: `np.double(image_data)` remains only in `_prepare_simulation_input_image()` for CPU/default legacy paths. MLX float32 bypasses it.
- `src/spektrafilm_gui/controller.py:803`: `process_with_metadata()` is now guarded by `require_hdr_metadata`.
- `src/spektrafilm_gui/controller_runtime.py:354`: `np.asarray(scan)` is now the single worker materialization point before display and float output reuse.
- `src/spektrafilm/runtime/pipeline.py` and `src/spektrafilm/runtime/process.py`: public runtime metadata API and internal metadata preprocessing remain legitimate boundaries.

### Benchmark Artifacts

- `docs/reports/gui-mlx-full-render-benchmark-20260604.md`
- `docs/reports/gui-mlx-full-render-benchmark-20260604-cpu.json`
- `docs/reports/gui-mlx-full-render-benchmark-20260604-cpu.md`
- `docs/reports/gui-mlx-full-render-benchmark-20260604-mlx.json`
- `docs/reports/gui-mlx-full-render-benchmark-20260604-mlx.md`

Benchmark result on synthetic `512x384` input, warmup 1, runs 3:

| Backend | Precision | Median wall | Min | Max | Speed vs CPU |
|---|---|---:|---:|---:|---:|
| CPU | float64 | 0.657018s | 0.548733s | 0.981479s | 1.00x |
| MLX | float32 | 0.076036s | 0.059970s | 0.085732s | 8.64x |

Copy evidence:

| Backend | Input request bytes | Input copy bytes | Float image bytes | Display image bytes |
|---|---:|---:|---:|---:|
| CPU | 4,718,592 | 4,718,592 | 4,718,592 | 589,824 |
| MLX | 2,359,296 | 0 | 4,718,592 | 589,824 |

### Remaining Bottlenecks

- `SimulationPipeline._preprocess_base()` still converts to float64 internally. This pass deliberately did not change that runtime/API boundary.
- `SimulationPipeline._materialize_output()` still returns float64 NumPy output, so GUI save/export float output remains float64-sized.
- Display prep still creates a full-size uint8 display image for napari semantics.
- Full 12MP default-quality RAW speed is still dominated by runtime scanner/grain work identified in the 2026-06-03 report; this pass removes GUI-side copies and metadata work but does not fuse scanner/grain kernels.
- Existing pipeline/regression baseline tests are failing outside this change surface and should be handled in a separate runtime correctness/baseline task.

### Final Confidence Assessment

I have high factual confidence in the scoped GUI changes:

- MLX float32 GUI requests no longer perform the pre-worker full-size float64 input copy.
- Ordinary non-HDR GUI runs no longer call `process_with_metadata()`.
- HDR HEIC-enabled GUI runs still request metadata and save-time missing-sidecar errors remain intact.
- Worker post-processing has a single explicit `np.asarray(scan)` point and reports memory estimates.
- Large output animation/crossfade copy behavior is locked by tests.

I am not claiming repo-wide SDR baseline health because the broader runtime/regression baseline suite currently fails in untouched files.
