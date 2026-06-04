# Metal Resident P0-P4 Goal Plan - 2026-06-04

> **For agentic workers:** REQUIRED SUB-SKILLS: Use `superpowers:test-driven-development`, `superpowers:systematic-debugging` for failures, and `superpowers:verification-before-completion` before claiming completion.

**Goal:** Remove the confirmed full-image CPU/MLX round trips in the float32 Metal/MLX runtime path while keeping the default CPU and public NumPy float64 API behavior unchanged.

**Architecture:** Keep CPU as the reference implementation and MLX as a backend-resident acceleration path where the current backend abstraction can express the operation safely. Add explicit boundaries for resize, metadata, validation, export, and legacy tiling instead of silently materializing full frames in the normal preview/process path.

**Tech Stack:** Python 3.13, NumPy, MLX, colour-science, Spektrafilm `ArrayBackend`, pytest, `uv`, Markdown/JSON benchmark artifacts.

---

## Current Hot Path Evidence

Live source scan before code edits found the requested boundaries:

- `src/spektrafilm/runtime/pipeline.py`:
  - `_preprocess_base()` starts with `np.double(np.array(image)[:, :, 0:3])`, forcing a full input image to CPU float64 before auto exposure or crop/resize.
  - `_materialize_output()` always returns `np.asarray(value, dtype=np.float64)`, so no process call can return backend-resident output.
  - `_scene_luminance()` and `_run_gpu_validate()` are valid CPU materialization boundaries for metadata and validation, but they must stay local to those features.
- `src/spektrafilm/runtime/stages/filming.py`:
  - GPU `hanatos2025` filming calls CPU `_rgb_to_tc_b()` before applying the backend 2D LUT.
- `src/spektrafilm/gpu/kernels/density.py`:
  - The MLX custom `cmy_to_log_xyz_backend()` path calls `np.array(...)` on flattened MLX inputs and output only for NaN debug printing.
- `src/spektrafilm/gpu/backend.py`:
  - `tiled_processing()` converts GPU input to NumPy, processes each tile, converts each processed tile to NumPy, assembles on CPU, and returns `backend.asarray(result)`.
- `src/spektrafilm/runtime/services/resize.py`:
  - `crop_and_rescale()` uses NumPy/skimage. Backend crop can be added in the pipeline; backend resize is a deliberate fallback for this pass.

Recent local docs show MLX 0.31.2 has been usable here and that residency regressions should be tested by monkeypatching `backend.to_numpy`.

## P0-P4 Breakdown

### P0: Gate MLX NaN Debug Readbacks

- Remove default `np.array(...)` debug checks from the MLX custom density kernel path.
- Preserve optional debug diagnostics behind an explicit environment variable, for example `SPEKTRAFILM_MLX_KERNEL_DEBUG_NAN=1`.
- Default runtime must not materialize MLX arrays for this debug path.

### P1: Backend-Resident RGB To TC/B

- Add `rgb_to_tc_b_backend()` in `src/spektrafilm/gpu/kernels/color.py`.
- Use `precompute_rgb_to_xyz_matrix(..., cat="CAT16")`, `cctf_decoding_transfer_backend()`, and `rgb_to_xyz()` to match CPU `_rgb_to_tc_b()`.
- Implement backend `_tri2quad` and backend `nan_to_num(b)`.
- Change the MLX/GPU branch of `FilmingStage._rgb_to_film_raw()` to call the new backend function and never call CPU `_rgb_to_tc_b()` for full images.
- Keep CPU `_rgb_to_tc_b()` unchanged as the reference.

### P2: Backend-Aware Preprocess

- Keep CPU/default preprocess exactly compatible: NumPy float64, CPU auto exposure, CPU crop/resize.
- For GPU float32:
  - Convert only RGB channels with `backend.asarray(..., dtype=backend.default_dtype)` where available.
  - Apply crop through backend slicing when `io.crop=True`.
  - If `io.upscale_factor != 1.0`, explicitly fall back to CPU resize and re-wrap to backend, timing/reporting the fallback.
  - For auto exposure, use the existing CPU small-preview measurement only on a small materialized preview, not the full frame, unless no downscale is needed. The full image scale should be applied on backend.
- `process_with_metadata()` may still materialize for `_scene_luminance()` because HDR metadata is CPU-facing.

### P3: Output Materialization Policy

- Add `settings.materialize_policy` with values:
  - `numpy_float64`: default legacy behavior.
  - `numpy_float32`: CPU materialization to NumPy float32.
  - `backend`: return backend-resident output when a GPU backend is selected.
- Validate policy in `RuntimePhotoParams.__post_init__()`.
- Keep public default `process()` compatible.
- In `process_with_metadata()`, materialize locally for metadata when needed and honor the image policy separately.
- Add GUI manifest enum/control if the GUI settings surface supports this field; default remains compatibility-safe.

### P4: GPU Tiling Contract Fix

- Keep existing `tiled_processing()` behavior for CPU.
- For GPU backends, fail early with a clear message instead of doing tile-level CPU round trips.
- Add a dedicated `backend_tiled_processing()` only if the backend can assemble tiles without readback. For this pass, no current runtime hot path calls tiling, so the safer scope is to mark old tiling as CPU fallback and prevent accidental GPU use.
- Tests must confirm no GPU `to_numpy` calls happen through the tiling helper.

## Expected File Changes

- Modify `src/spektrafilm/gpu/kernels/density.py`
- Modify `src/spektrafilm/gpu/kernels/color.py`
- Modify `src/spektrafilm/runtime/stages/filming.py`
- Modify `src/spektrafilm/runtime/pipeline.py`
- Modify `src/spektrafilm/runtime/params_schema.py`
- Modify `src/spektrafilm/gpu/backend.py`
- Modify `src/spektrafilm_gui/options.py`
- Modify `src/spektrafilm_gui/param_manifest.py`
- Add or modify focused tests in `tests/test_gpu_color_chain.py`, `tests/test_gpu_pipeline.py`, `tests/test_gpu_backend.py`, and optionally `tests/test_pipeline_smoke.py`
- Add `tools/benchmark_metal_pipeline_p0_p4.py`
- Add benchmark report under `docs/reports/` or `artifacts/benchmarks/`

## Behaviors That Must Not Change

- CPU/default `process()` returns NumPy float64 and existing SDR output values remain within current tolerances.
- CPU `_rgb_to_tc_b()` remains the reference for parity tests.
- `gpu_validate=True` still runs the CPU reference path and may materialize by design.
- `process_with_metadata()` still returns CPU-friendly HDR scene luminance.
- GUI/display/export paths may materialize outputs for display/save compatibility.
- No float16 changes are in scope.
- No P5 kernel fusion, GUI Metal texture bridge, or grain-statistics rewrite is in scope.

## Test Matrix

Red tests before production edits:

- `rgb_to_tc_b_backend()` matches CPU `_rgb_to_tc_b()` for small random images across `sRGB`, `Display P3`, and `ITU-R BT.2020`, with `apply_cctf_decoding=True/False`.
- GPU filming branch does not call CPU `_rgb_to_tc_b()` when backend is active.
- GPU preprocess without resize returns a backend array and does not full-frame `to_numpy()`.
- Resize fallback is explicit and returns a backend array after CPU resize.
- Default process returns NumPy float64.
- `materialize_policy="numpy_float32"` returns NumPy float32.
- `materialize_policy="backend"` returns backend arrays under MLX and degrades sensibly for CPU.
- GPU `tiled_processing()` raises before `to_numpy`.
- P0 grep/runtime test confirms default density MLX custom path has no NaN debug readbacks.

Targeted verification commands:

```bash
uv run --extra dev pytest tests/test_gpu_color_chain.py tests/test_gpu_backend.py -q
uv run --extra dev pytest tests/test_gpu_pipeline.py tests/test_pipeline_smoke.py -q
uv run --extra dev pytest tests -k "gpu or mlx or backend or pipeline or spectral or lut or density or preprocessing" -q
```

Fallback when the local pytest/import path stalls:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run --extra dev pytest tests/test_gpu_color_chain.py tests/test_gpu_backend.py tests/test_gpu_pipeline.py -q
```

## Benchmark Plan

Add `tools/benchmark_metal_pipeline_p0_p4.py`.

Required output:

- Environment: requested/selected backend, `gpu_precision`, MLX/Metal availability, image shape, materialize policy, LUT/auto-exposure/resize/scan-film settings.
- Matrix:
  - CPU baseline.
  - MLX old-compatible materialized path (`numpy_float64`).
  - MLX backend-resident path (`backend`).
- Stage timings:
  - `preprocess`
  - `filming.expose`
  - `filming.develop`
  - `printing.expose`
  - `printing.develop`
  - `scanning.scan` or `scanning.scan_print`
  - `SimulationPipeline.materialize`
  - total elapsed and outer wall time
- Warmup: 1.
- Measured runs: 3.
- Summary: median/min/max and speedup ratios.
- Artifact: Markdown plus JSON under `docs/reports/` or `artifacts/benchmarks/`.
- If MLX/Metal is unavailable, record a skipped MLX result and still run CPU.

Benchmark commands:

```bash
uv run python tools/benchmark_metal_pipeline_p0_p4.py --backend cpu
uv run python tools/benchmark_metal_pipeline_p0_p4.py --backend mlx --precision float32
```

## Risk And Rollback Points

- P1 color conversion risk: CAT16 or CCTF mismatch. Roll back `rgb_to_tc_b_backend()` integration and keep CPU `_rgb_to_tc_b()` if parity fails.
- P2 preprocess risk: backend slicing crop may differ from `crop_image()` rounding. Verify crop tests against CPU. Resize remains CPU fallback by design.
- P3 policy risk: callers may assume NumPy arrays. Default stays `numpy_float64`; only explicit `backend` changes return type.
- P4 tiling risk: external GPU callers may rely on old silent behavior. Raising is intentional because the previous docstring promised GPU tiling that did not exist.
- Benchmark risk: first LUT build can dominate. Separate warmup from measured runs and mention cold/warm boundary.

## Completion Log

Status: complete.

### Implemented Scope

- P0: gated MLX custom density-kernel NaN debug readbacks behind `SPEKTRAFILM_MLX_KERNEL_DEBUG_NAN`; default runtime no longer calls `np.array(...)` for these flattened MLX buffers.
- P1: added direct `gpu.kernels.color.rgb_to_tc_b_backend()` with backend float32 RGB input, optional backend CCTF decode, CAT16 RGB to XYZ matrix, backend `b`, backend xy, backend `_tri2quad`, and backend `nan_to_num`. `FilmingStage._rgb_to_film_raw()` GPU path now calls this helper and no longer calls CPU `_rgb_to_tc_b()` for full images.
- P2: added backend-aware preprocess for GPU float32. No-resize path stays backend-resident after RGB slicing, crop uses backend slicing, auto exposure materializes only a preview, and resize is an explicit timed CPU fallback that re-wraps to backend.
- P3: added `settings.materialize_policy` with `numpy_float64` default compatibility, `numpy_float32`, and `backend`; GUI compute panel exposes the policy.
- P4: changed `tiled_processing()` into an explicit CPU fallback and reject GPU backends before any tile-level `to_numpy`.

### Modified Files

- `src/spektrafilm/gpu/kernels/density.py`
- `src/spektrafilm/gpu/kernels/color.py`
- `src/spektrafilm/runtime/stages/filming.py`
- `src/spektrafilm/runtime/pipeline.py`
- `src/spektrafilm/runtime/params_schema.py`
- `src/spektrafilm/gpu/backend.py`
- `src/spektrafilm_gui/options.py`
- `src/spektrafilm_gui/param_manifest.py`
- `tests/test_gpu_density.py`
- `tests/test_gpu_color_chain.py`
- `tests/test_gpu_pipeline.py`
- `tests/test_gpu_backend.py`
- `tests/test_filming_stage.py`
- `tools/benchmark_metal_pipeline_p0_p4.py`
- `docs/reports/metal-p0-p4-benchmark-20260604-144839.md`
- `docs/reports/metal-p0-p4-benchmark-20260604-144839.json`

### Validation Commands

```bash
uv run --extra dev pytest tests/test_gpu_color_chain.py tests/test_filming_stage.py -q
```

Result: `45 passed in 1.63s`.

```bash
uv run --extra dev pytest tests/test_gpu_color_chain.py tests/test_gpu_density.py tests/test_gpu_backend.py tests/test_gpu_pipeline.py tests/test_filming_stage.py tests/test_spectral_upsampling.py -q
```

Result: `114 passed, 4 skipped in 2.87s`.

```bash
uv run --extra dev pytest tests -k "(gpu or mlx or backend or pipeline or spectral or lut or density or preprocessing) and not midgray_input and not pipeline_snapshot" -q
```

Result: `770 passed, 7 skipped, 764 deselected in 17.77s`.

```bash
uv run --extra dev pytest tests/test_pipeline_smoke.py::test_midgray_input_produces_expected_output_values tests/test_regression_baselines.py -q
```

Result: `5 failed, 1 passed`. The failing cases are the known SDR baseline/golden mismatches documented in `docs/upstream-sync-plan-20260602.md`; this task did not update SDR baselines.

```bash
uv run --extra dev python -m compileall -q src/spektrafilm/gpu src/spektrafilm/runtime tools/benchmark_metal_pipeline_p0_p4.py
git diff --check
```

Result: both passed.

### Benchmark Result

Fresh report: `docs/reports/metal-p0-p4-benchmark-20260604-144839.md`.

Command:

```bash
uv run python tools/benchmark_metal_pipeline_p0_p4.py --backend mlx --precision float32 --shape 256x256 --warmups 1 --runs 3
```

Result:

| Case | Median | Min | Max | Speedup vs CPU | Output |
|---|---:|---:|---:|---:|---|
| CPU baseline | 0.198884s | 0.176386s | 0.311270s | | NumPy float64 |
| MLX `numpy_float64` | 0.019117s | 0.017948s | 0.021608s | 10.404x | NumPy float64 |
| MLX `backend` | 0.014527s | 0.012768s | 0.017159s | 13.690x | `mlx.core.array` float32 |

Important interpretation: `mlx_backend_resident` reports near-zero `SimulationPipeline.materialize` time (`0.000001s` in the final measured run), but the benchmark still performs an explicit `gpu_sync` after `process()` (`0.009421s` in the final measured run) so the timing is not hiding deferred MLX work. The resident policy is most valuable when the next consumer remains on the backend; a CPU consumer/export path will still pay materialization later.

### Grep Audit

Command:

```bash
grep -R --exclude-dir='__pycache__' "np.array(.*flat\|np.asarray(.*outputs\|to_numpy" src/spektrafilm/gpu src/spektrafilm/runtime -n
```

Remaining matches are classified as follows:

- `gpu/kernels/density.py:57`: explicit env-gated debug helper only; default off.
- `gpu/kernels/density.py:371,434`: fallback for backend paths without the specialized MLX/CuPy density implementation.
- `gpu/kernels/lut.py:306,485`: fallback for unsupported GPU LUT kernels; MLX/CuPy supported paths avoid these.
- `gpu/kernels/filters.py:*`: fallback paths for unsupported filters or exact CPU-style filtering; not the P0-P4 default resident path.
- `gpu/kernels/gamut_compress.py:442`: unsupported compression algorithm fallback.
- `gpu/*_backend.py` and `gpu/backend.py`: backend API definitions.
- `runtime/stages/printing.py:228,256`: explicit helper boundary when a caller asks `return_backend=False`.
- `runtime/pipeline.py:523,526`: auto-exposure preview materialization only, not unconditional full-frame preprocess.
- `runtime/pipeline.py:543`: explicit resize CPU fallback when `upscale_factor != 1.0`.
- `runtime/services/color_reference.py:*`: scalar black/white/midgray reference boundaries.
- `runtime/services/spectral_lut_compute.py:*`: LUT construction callback boundary, not steady-state per-pixel pipeline processing.

### Self-Audit

Question: "Do I have factual 100% confidence in this implementation?"

Answer: I have high confidence for P0-P4 as scoped, backed by targeted tests, broad GPU/runtime selector tests, grep audit, compileall, `git diff --check`, and a fresh benchmark. The remaining gaps are explained boundaries rather than silent hot-path round trips.

Highest-risk loopholes checked:

- P1 delegation loophole: fixed after an audit found the first helper still delegated through `spectral_upsampling`; tests now monkeypatch that helper to fail and still pass.
- P1 import-cycle loophole: fixed by lazy illuminant lookup after focused tests caught the circular import.
- P1 CPU fallback loophole: filming GPU tests now patch CPU `_rgb_to_tc_b()` to fail and verify GPU branches use the backend helper or raise for fp16.
- P2 full-frame preprocess loophole: tests verify MLX no-resize preprocess returns backend arrays and resize fallback is explicit.
- P3 compatibility loophole: default remains NumPy float64; explicit policies are tested.
- P4 tiling loophole: GPU tiling rejects before `to_numpy`.

Residual boundaries still not full end-to-end Metal:

- Resize remains a CPU fallback and is timed as `SimulationPipeline.preprocess.resize_cpu_fallback`.
- Auto exposure still materializes a small preview.
- HDR metadata, export, GUI texture upload/display, and GPU validation may materialize by design.
- Some unsupported LUT/filter/gamut-compress algorithms still have explicit CPU fallback paths.
- Float16 is intentionally not implemented for this pass.

Next best P5/P6 work:

- Add backend resize or a clearly separated Metal resize stage to remove the largest remaining preprocess fallback.
- Move GUI preview/output texture upload to consume backend-resident arrays directly.
- Fuse or reduce synchronization between printing/scanning kernels after measuring steady-state MLX graph costs.
