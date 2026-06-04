# MLX GUI Full Render Hot Path Plan - 2026-06-03

> **For agentic workers:** REQUIRED SUB-SKILLS: Use `superpowers:systematic-debugging`, `superpowers:test-driven-development`, and `superpowers:verification-before-completion`. This plan is the pre-edit contract for the 2026-06-03 MLX GUI full-render performance pass.

**Goal:** Improve warm-run MLX GUI full-render performance and observability for 12MP DNG input by removing confirmed unnecessary MLX synchronization/cache clearing and exposing GUI/runtime phase timings.

**Architecture:** Keep the public runtime contract unchanged: CPU remains the reference backend, MLX remains float32 GPU acceleration, and final public outputs still materialize as NumPy arrays for GUI display/export. The optimization targets only cache/synchronization policy and timing instrumentation around existing behavior.

**Tech Stack:** Python 3.13, NumPy, MLX 0.31.2, rawpy, Qt/napari GUI controller, Spektrafilm runtime pipeline, pytest, `.venv/bin/python`.

---

## Current Baseline

### Environment

- Workspace: `/Users/retriedstormtrooper/Documents/spektrafilm-main`
- Test input: `/Users/retriedstormtrooper/Downloads/IMG_4897/IMG_4897.DNG`
- DNG file size: 18 MB
- MLX probe: `.venv/bin/python`, Python 3.13.1, MLX 0.31.2, `mx.metal.is_available() == True`
- Current worktree already has unrelated untracked local files such as `debug_mlx.py`, `debug_pipeline.py`, `docs.zip`, and scratch scripts. This pass must not clean or include them.

### RAW Load Baseline

Direct rawpy probe:

```text
rawpy import: 0.0895s
rawpy.imread: 0.0370s
raw.postprocess: 0.5794s
astype/normalize: 0.0535s
shape: (3024, 4032, 3)
```

Spektrafilm RAW helper probe:

```text
cold import spektrafilm.utils.raw_file_processor: 50.7740s
warm import spektrafilm.utils.raw_file_processor: 1.2502s
load_and_process_raw_file: 1.0143s
shape: (3024, 4032, 3)
dtype: float64 after ProPhoto conversion
```

Conclusion: the DNG decode itself is not the 16-17s bottleneck. Cold import cost is large and currently hidden, while warm RAW load/convert is about 1s on this machine.

### Pipeline Baseline

Existing 2026-06-02 TIFF benchmark evidence still matches the current source shape:

- `docs/dev/2026-06-02-mlx-runtime-hotpath-plan.md`
- `docs/dev/benchmark-artifacts/mlx_runtime_hotpath_20260602/benchmark-20260602-233135.md`

That benchmark proved the measured TIFF path can stay MLX-resident from filming onward, but the runtime is still mixed because preprocess starts as NumPy and final output returns NumPy float64. It also showed repeated backend conversions:

```text
backend.asarray.input count=70 bytes=1113451572
backend.asarray.output count=70 bytes=1097001020
backend.to_numpy.input count=2 bytes=24
backend.to_numpy.output count=2 bytes=24
```

The current DNG default-grain CPU probe was terminated after more than 90s of CPU work because it did not match the user's reported CPU 21-24s baseline. Treat this as parameter mismatch evidence, not as a valid CPU baseline.

## Source Audit Findings

### Confirmed Hot Path Issues

1. `src/spektrafilm/gpu/kernels/filters.py`
   - `fft_convolve_same_backend()` calls `mx.eval(convolved)` and `mx.metal.clear_cache()` inside the MLX diffusion path.
   - This forces an intermediate sync and clears MLX/Metal caches before the final materialization boundary.

2. `src/spektrafilm/runtime/pipeline.py`
   - `_process_result()` and `_process_topology()` call `self._backend.cleanup()` after every non-preview MLX run.
   - `update()` calls `backend.cleanup()` before every GUI `update_params()` rebuild.
   - GUI full render reuses a `Simulator`, but `_process_image_with_runtime()` calls `update_params()` before every run. This means warm full renders can still lose backend cache benefits.

3. `src/spektrafilm/runtime/pipeline.py`
   - `update()` rebuilds a new backend for the same backend/precision request and may reuse a `SpectralLUTService` that still references the previous backend object.
   - Reusing the backend when the selection key is unchanged is lower risk and better for MLX compile/cache locality.

4. `src/spektrafilm_gui/controller_runtime.py`
   - `execute_simulation_request()` records only a total elapsed string in the status message.
   - It does not expose `process`, final `np.asarray`, display preparation, or runtime stage timings in `SimulationResult`.

5. `src/spektrafilm_gui/controller.py`
   - `_start_simulation()` performs an input `np.double(image_data)` copy before dispatch but does not time it.
   - `_on_simulation_finished()` updates the napari output layer and metadata but does not time display/layer update.
   - `load_raw_image()` and `save_output_layer()` have no phase timing.

### Important Non-Issues Or Deferred Items

- `tiled_processing()` in `src/spektrafilm/gpu/backend.py` does force `backend.to_numpy(image)` and per-tile `backend.to_numpy(process_fn(tile))`. Current full runtime does not appear to call this helper, so changing it is not a first-pass performance win. Add a guard/test or document it as unsafe for MLX hot paths instead of rewriting it broadly.
- Grain is still a likely bottleneck when default quality uses layered stochastic grain. The MLX path still loops channel x sublayer in Python and launches many random/filter kernels. A fused Metal grain kernel is plausible future work, but this pass will not change grain statistics without stronger parity evidence.
- HDR HEIC/gain-map export is a separate save path. This pass must not remove, merge, or weaken the HDR settings path.

## Bottleneck Hypotheses

1. Warm GUI MLX runs lose cache benefits because the runtime cleans or rebuilds MLX backend state on every full render.
2. Diffusion-filter MLX FFT convolution pays avoidable sync and cache-clear overhead before the final materialization boundary.
3. User-visible timing conflates runtime compute, materialization, display transform, and layer update, so current GUI status cannot identify the real 16-17s split.
4. `gpu_validate=True` is not a performance mode because it runs a CPU reference pass. GUI performance measurements must keep it off unless explicitly validating output.
5. Grain can dominate under default-quality settings, but fixing it safely requires a separate statistical validation track.

## Implementation Plan

### Task 1: Add Regression Tests For MLX Lazy/Cleanup Policy

**Files:**

- Modify: `tests/test_gpu_backend.py`
- Modify: `tests/test_runtime_api.py`
- Modify: `tests/test_gpu_pipeline.py` if a real MLX backend reuse test is practical

Steps:

- Add a test that skips when MLX is unavailable, monkeypatches `mx.eval` and `mx.metal.clear_cache`, calls `fft_convolve_same_backend()` on a small MLX array, and asserts neither function is called inside the kernel helper.
- Add a fake pipeline/backend test showing repeated `Simulator.update_params()` with the same backend selection does not call `cleanup()` by default.
- Add a test showing an explicit aggressive cleanup setting still calls cleanup when requested.
- Add a test showing same backend/precision update reuses the existing backend object.

Expected red failures before implementation:

- `fft_convolve_same_backend()` currently calls both `mx.eval` and `mx.metal.clear_cache`.
- `SimulationPipeline.update()` currently calls `cleanup()` unconditionally for MLX.

### Task 2: Implement MLX Cache/Synchronization Fix

**Files:**

- Modify: `src/spektrafilm/gpu/kernels/filters.py`
- Modify: `src/spektrafilm/runtime/params_schema.py`
- Modify: `src/spektrafilm/runtime/pipeline.py`

Implementation:

- Remove intermediate `mx.eval(convolved)` and `mx.metal.clear_cache()` from `fft_convolve_same_backend()`.
- Add a runtime setting such as `gpu_aggressive_cleanup: bool = False`.
- Only call backend cleanup after process/update when that setting is enabled or when replacing a backend with a different backend-selection key.
- Track and reuse the existing backend object when `compute_backend` and `gpu_precision` are unchanged across `SimulationPipeline.update()`.
- Keep `MlxBackend.cleanup()` unchanged for explicit/manual cleanup and memory-pressure recovery.

Acceptance:

- Final public `process()` still returns NumPy float64.
- CPU path is unchanged.
- MLX lazy evaluation remains synchronized only by final materialization, benchmark sync, validation, explicit cleanup, or explicit backend API calls.

### Task 3: Add GUI And Runtime Phase Timing

**Files:**

- Modify: `src/spektrafilm_gui/controller_runtime.py`
- Modify: `src/spektrafilm_gui/controller.py`
- Modify: `src/spektrafilm_gui/controller_layers.py` if output-layer update timing needs to be persisted in metadata
- Modify: `tests/gui/test_controller_runtime_module.py`
- Modify: `tests/gui/test_controller_flow.py`

Implementation:

- Add `phase_timings: dict[str, float]` and `runtime_stage_timings: dict[str, float]` to `SimulationResult`.
- In `execute_simulation_request()`, time:
  - `runtime.process_with_metadata`
  - final materialization or `np.asarray(scan)`
  - `prepare_output_display_image`
  - total worker elapsed
- Let the controller pass optional functions for `Simulator.get_timings()` and `Simulator.get_total_elapsed_time()`.
- In `_start_simulation()`, time input conversion (`np.double(image_data)`) and include it in the request or result.
- In `_on_simulation_finished()`, time output layer update and store the full timing dictionary in output layer metadata.
- Keep status text concise: total time plus a compact phase summary, while detailed timings live in metadata and docs/bench output.

Acceptance:

- GUI full render can expose at least input conversion, runtime process, final materialize, display preparation, and layer update.
- Runtime stage timings still include existing stage labels such as `FilmingStage.auto_exposure`, `PrintingStage.expose`, `PrintingStage.develop`, `ScanningStage.scan`, and `SimulationPipeline.gpu_validate` when present.

### Task 4: Improve Benchmark Script For DNG GUI-Like Runs

**Files:**

- Modify: `scripts/benchmark_mlx_runtime_hotpath.py`
- Modify: `tests/test_mlx_runtime_hotpath_benchmark.py`

Implementation:

- Parse CLI arguments before loading heavyweight modules or image data, so bad arguments fail immediately.
- Print or record load/decode timing, input conversion timing, runtime process timing, display preparation timing, final materialization timing, and optional encode/export timing.
- Add a matrix option that can run only CPU, only MLX, or skip `gpu_validate=True` for performance runs.
- Record machine/backend/precision, cold/warm run counts, and DNG load timing in JSON/Markdown.

Acceptance:

- The script can benchmark the provided DNG without a silent no-output phase.
- A smoke-sized generated run remains fast and covered by tests.

### Task 5: Validate CPU/MLX, SDR, Timing, And HDR

Commands:

```bash
.venv/bin/python -m pytest tests/test_gpu_backend.py tests/test_runtime_api.py tests/test_gpu_pipeline.py tests/test_mlx_runtime_hotpath_benchmark.py -q
.venv/bin/python -m pytest tests/gui/test_controller_runtime_module.py tests/gui/test_controller_flow.py tests/gui/test_controller_output.py -q
.venv/bin/python -m pytest tests/test_gain_map.py tests/test_hdr_photo.py tests/test_hdr_profile_validation_tool.py -q
.venv/bin/python -m compileall -q src tests scripts
git diff --check
```

Performance commands:

```bash
.venv/bin/python scripts/benchmark_mlx_runtime_hotpath.py --input /Users/retriedstormtrooper/Downloads/IMG_4897/IMG_4897.DNG --size full --warmups 1 --runs 2 --no-preview-640 --skip-gpu-validate --out-dir docs/dev/benchmark-artifacts/mlx_gui_full_render_20260603
.venv/bin/python scripts/benchmark_mlx_runtime_hotpath.py --input /Users/retriedstormtrooper/Downloads/IMG_4897/IMG_4897.DNG --size 1024x768 --warmups 1 --runs 1 --out-dir docs/dev/benchmark-artifacts/mlx_gui_full_render_20260603_smoke
```

If full CPU remains inconsistent with the user's 21-24s report, record the exact parameter set used and avoid claiming direct apples-to-apples parity with the user's run.

## Behaviors That Must Not Break

- SDR preview/output semantics and existing CPU reference path.
- HDR HEIC/HEIF gain-map export settings and save path.
- `gpu_validate=True` CPU-reference validation semantics.
- Final public runtime output materialization as NumPy.
- Existing profile/LUT invalidation when film, print, LUT resolution, backend, or precision changes.
- MLX unavailability skip behavior in tests.
- Explicit backend cleanup for manual memory-pressure recovery.

## Rollback Risks

- Deferring cleanup may increase MLX memory residency across warm runs. Mitigation: preserve explicit cleanup and aggressive cleanup setting.
- Reusing backend objects across updates may accidentally reuse stale LUT/backend caches. Mitigation: compare backend selection key and retain existing LUT invalidation checks.
- Removing diffusion FFT `mx.eval` may defer memory allocation to final materialization. Mitigation: benchmark full DNG and keep explicit benchmark sync outside production hot path.
- Timing instrumentation may add status noise or test brittleness. Mitigation: store detailed timing in metadata and keep status summary compact.

## Completion Criteria

- A repo-local plan exists before code edits.
- Tests prove the MLX diffusion FFT helper no longer syncs or clears cache internally.
- Tests prove per-render MLX cleanup is not the default warm-run behavior and explicit cleanup remains available.
- GUI `SimulationResult` and output metadata expose phase timings.
- Benchmark output records DNG load/decode, input conversion, runtime, final materialization, display, and warm-run timings.
- At least one DNG or smoke benchmark shows post-change warm-run timing with stage breakdown.
- Targeted CPU/MLX/GUI/HDR tests pass or any failures are reported with exact command output.
- Final report states whether factual 100% confidence was reached and lists remaining uncertainties.
