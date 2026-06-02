# MLX Runtime Hot Path Plan - 2026-06-02

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:systematic-debugging`, `superpowers:test-driven-development`, and `superpowers:verification-before-completion`. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Diagnose and fix the gap between selecting `compute_backend="mlx"` and actually accelerating Spektrafilm's runtime/model hot path.

**Architecture:** Treat backend selection, runtime array residency, and user-facing status as separate contracts. Keep CPU/SDR output semantics intact, preserve MLX arrays across full-image stages where the existing backend abstraction can do so safely, and report remaining CPU-only boundaries honestly.

**Tech Stack:** Python 3.13, NumPy, MLX, Spektrafilm runtime stages, `ArrayBackend`, pytest, `uv`, benchmark JSON/Markdown artifacts.

---

## Current Evidence

### Git State

Observed on the live checkout before any task edits:

- Current branch/HEAD: `develop` at `949cf43 fix: handle Optional/float|None union types in GUI editor resolution`.
- The user-provided `f0ca402 feat: add GPU compute backend section to ADVANCED tab` is present, but it is not current HEAD; it is the parent of `949cf43`.
- The worktree already has many unrelated documentation migration changes (`D docs/...`, `?? docs/archive/...`, `M docs/README.md`, `M docs/dev/README.md`, `M uv.lock`). This task must not revert or normalize those changes.

### Required Backend Probe

Command:

```bash
uv run python - <<'PY'
from spektrafilm.gpu.backend import select_backend, backend_summary
for name in ["cpu", "auto", "mlx"]:
    b = select_backend(name, precision="float32")
    print(name, b.name, b.supports_gpu, getattr(b, "requires_serial_runtime", None), backend_summary(b))
PY
```

Observed output:

```text
cpu cpu False False cpu
auto mlx True True cpu runtime path; mlx validated for optional GPU kernels
mlx mlx True True cpu runtime path; mlx validated for optional GPU kernels
```

### Why `backend_summary()` Says CPU Runtime Path

`src/spektrafilm/gpu/backend.py` currently defines:

```python
def backend_summary(backend: ArrayBackend, *, runtime_gpu_enabled: bool = False) -> str:
    if backend.supports_gpu and not runtime_gpu_enabled:
        return f"cpu runtime path; {backend.name} validated for optional GPU kernels"
    ...
```

The default `runtime_gpu_enabled=False` forces the "cpu runtime path; mlx validated for optional GPU kernels" wording for any GPU backend unless the caller explicitly passes `runtime_gpu_enabled=True`.

That default is not a runtime measurement. It is a conservative display hint. However, because the summary is used without a runtime-residency audit, it currently conflates three different states:

- MLX selected and usable.
- Some optional GPU kernels available.
- Full runtime path resident on MLX.

Only the first two are proven by the selection probe.

### `requires_serial_runtime` Semantics And Actual Impact

Current backend declarations:

- `MlxBackend.requires_serial_runtime = True`
- `HalideBackend.requires_serial_runtime = True`
- `NumpyBackend.requires_serial_runtime = False`
- `CupyBackend.requires_serial_runtime = False`

Actual current usage:

- `SimulationPipeline._backend_cache_key()` includes `requires_serial_runtime` so LUT services rebuild when that flag changes.
- `src/spektrafilm/gpu/metal_serialization.py` defines `serialized_metal_runtime()`.
- Current `src/spektrafilm/runtime/process.py` does not import or call `serialized_metal_runtime()`.
- Search found no current runtime branch that serializes `Simulator.process()` or `SimulationPipeline.process()` based on `requires_serial_runtime`.

Conclusion: today `requires_serial_runtime=True` is metadata plus cache-key material. It does not itself serialize MLX runtime calls. This is a correctness/status bug relative to older docs that describe a Metal runtime lock in `process.py`.

## Why MLX Can Be Selected But Still Feel Equal-Speed

The current runtime is partially MLX-backed, not fully MLX-resident:

- `SimulationPipeline.__init__()` selects `self._backend = select_backend(...)` and passes it into `SpectralLUTService`, `FilmingStage`, `PrintingStage`, and `ScanningStage`.
- Several stage/model calls use backend kernels and can return `mlx.core.array`.
- But `SimulationPipeline._preprocess_base()` starts with `np.double(np.array(image)[:, :, 0:3])`, forcing NumPy float64 input.
- `SimulationPipeline._pipeline()` and `_pipeline_with_metadata()` end with `np.asarray(rgb_scan, dtype=np.float64)`, forcing final materialization to CPU float64.
- `PrintingStage.develop()` still calls `develop_print_morph()` with no backend parameter, so print density interpolation is CPU NumPy.
- `SpectralLUTService` LUT build/test paths intentionally call NumPy callbacks and `backend.to_numpy()` in places.
- Some color/gamut/profile/reference operations are still CPU helper paths.
- MLX lazy evaluation means unsynchronized stage timings can under-report work until a later `mx.eval()`, `backend.to_numpy()`, or final `np.asarray()`.

Therefore, CPU and MLX can be close in wall-clock when:

- Full-resolution CPU-only boundaries dominate.
- The benchmark includes `gpu_validate=True`, which re-runs a CPU reference after the MLX run.
- The benchmark uses preview/downsampled images where MLX dispatch/materialization overhead can erase kernel gains.
- Existing summary/status text is interpreted as "full runtime acceleration" even though it only states "optional GPU kernels."

## Current CPU Runtime Paths

These are true CPU or CPU-materializing boundaries in the current code:

- `SimulationPipeline._preprocess_base()`: `np.array` plus `np.double` on the full input, then CPU auto-exposure and crop/rescale.
- `SimulationPipeline._pipeline()` / `_pipeline_with_metadata()`: final `np.asarray(..., dtype=np.float64)`.
- `SimulationPipeline._run_gpu_validate()`: with `gpu_validate=True`, creates a CPU float64 pipeline and processes the source image again.
- `FilmingStage._simple_rgb_to_density_spectral()`: intentionally CPU-only for tiny reference data and NaN-bearing channel density.
- `PrintingStage.develop()`: `develop_print_morph()` remains CPU-only.
- `SpectralLUTService._spectral_compute()` when building or validating LUTs: CPU callback/test-value path, plus `_to_numpy()` for GPU callback results.
- `ScanningStage._density_to_rgb()`: `compress_rgb()` currently receives RGB data and is not proven backend-resident; current code wraps the result back into backend afterward if GPU is active.
- CPU-only profile/reference helper calculations in `ColorReferenceService`, exposure-factor calculations, and small static table preparation.
- Final GUI/macOS bridge display/save paths intentionally materialize NumPy arrays.

## Existing Optional GPU Kernels

The grep and source audit confirm these GPU/backend-aware paths already exist:

- Backend selection and protocol: `src/spektrafilm/gpu/backend.py`, `mlx_backend.py`, `cupy_backend.py`, `halide_backend.py`, `numpy_backend.py`.
- LUT kernels: `gpu/kernels/lut.py` for 2D filming LUT and 3D trilinear LUT, including MLX paths.
- Density kernels: `gpu/kernels/density.py` for exposure-to-density interpolation, density-layer interpolation, `compute_density_spectral`, `density_to_light`, `light_to_raw`, `safe_log10_backend`, and `cmy_to_log_xyz_backend`.
- Color kernels: `gpu/kernels/color.py` for CCTF encode/decode, highlight boost, matrix transforms, and same-space transfer functions.
- Filter kernels: `gpu/kernels/filters.py` for Gaussian, exponential, reflect padding, FFT convolution, diffusion/halation-adjacent filters.
- Grain kernels: `gpu/kernels/grain.py` and `model/grain.py` for MLX/CuPy stochastic grain paths.
- Runtime stage integration: `runtime/stages/filming.py`, `printing.py`, `scanning.py` pass backend into selected model/kernel calls.
- LUT service backend caches: `runtime/services/spectral_lut_compute.py` caches backend LUT copies and backend filming TC LUT.

## Runtime/Model Backend Use Classification

### Truly Uses MLX In The Current Runtime

- `FilmingStage._rgb_to_film_raw()` when `rgb_to_raw_method == "hanatos2025"`: uses backend 2D LUT.
- `FilmingStage.expose()`: highlight boost, diffusion, lens blur, halation, and final `safe_log10_backend()` can be backend operations.
- `develop_simple()` and DIR coupler correction: density interpolation and selected coupler math can use backend kernels.
- `PrintingStage.expose()`: direct spectral chain and LUT path can use backend arrays, static spectral tables are pre-converted.
- `ScanningStage._return_callable_cmy_to_log_xyz()`: can use `cmy_to_log_xyz_backend()`.
- `ScanningStage._apply_blur_and_unsharp()` and `_apply_cctf_encoding_and_clip()`: can use backend filters/CCTF/clip.
- Grain/halation/diffusion helpers have MLX-specific residency tests in prior work.

### Selects Backend But Still Has NumPy Boundaries

- `SimulationPipeline._preprocess_base()` always starts as NumPy float64.
- `SimulationPipeline._pipeline()` always returns NumPy float64.
- `PrintingStage.develop()` ignores backend.
- `SpectralLUTService` LUT build/test paths use CPU callback/reference paths.
- `ScanningStage._density_to_rgb()` calls `compress_rgb()` before re-wrapping the result.
- `ColorReferenceService` frequently materializes via `backend.to_numpy()` at scalar/reference boundaries.
- Current benchmark/status code can print `backend_summary()` without saying which runtime stages are resident.

### Must Stay CPU-Only Or CPU-Boundary For Now

- Tiny black/white/midgray reference computations that intentionally avoid GPU because profile arrays may contain NaN.
- Final output/display/save boundary.
- CPU float64 validation reference.
- GUI preview/output conversion and metadata/write paths.
- LUT construction itself when using CPU callbacks to bake reference LUTs.

### Good Migration Candidates

- Preprocess dtype policy: avoid unconditional `np.double` for GPU float32 and optionally convert to `backend.asarray(..., dtype=backend.default_dtype)` after crop/rescale.
- `PrintingStage.develop()`: add backend-aware print-curve interpolation if the morphed curves are precomputed on CPU but image-sized interpolation runs through `interpolate_exposure_to_density_backend()`.
- `ScanningStage` gamut compression boundary: either make compression backend-aware for simple/default specs or record it as a CPU-only fallback in type tracing.
- Runtime final materialization: keep only one final `to_numpy`/`np.asarray`, not repeated small materializations before it.
- `Simulator.process()` serialization: use `requires_serial_runtime` to guard MLX/Halide calls with `serialized_metal_runtime()`.

## Benchmark Plan

Do not use GUI preview as performance evidence. Add a dedicated benchmark script, tentatively:

- `scripts/benchmark_mlx_runtime_hotpath.py`
- Artifacts under `docs/dev/benchmark-artifacts/mlx_runtime_hotpath_20260602/`

Required benchmark matrix:

- CPU full-res.
- MLX full-res float32, `gpu_validate=False`.
- MLX full-res float32, `gpu_validate=True`.
- Preview 640.

Required output fields per run:

- Requested backend and selected backend name.
- `supports_gpu`.
- `requires_serial_runtime`.
- `backend_summary`, with explicit `runtime_gpu_enabled` state.
- Image shape and megapixels.
- `gpu_precision`.
- `gpu_validate`.
- Pipeline stage timings from `SimulationPipeline.get_timings()`.
- Total wall-clock from `SimulationPipeline.get_total_elapsed_time()` and outer measured wall-clock.
- Final output type/shape/dtype.
- Conversion counters and stage input/output type trace.

Required type trace stages:

- `preprocess`.
- `filming.expose`.
- `filming.develop`.
- `printing.expose`.
- `printing.develop`.
- `scanning`.
- LUT/spectral compute sub-stages where possible.

Trace classification must distinguish:

- `numpy.ndarray`.
- `mlx.core.array` / module starts with `mlx.`.
- Other backend arrays.
- Python/scalar/None.

Benchmark correctness constraints:

- Fixed film/print profiles.
- Stochastic grain disabled by default, unless separately marked.
- Auto exposure disabled by default for timing repeatability.
- Include warmup separately from timed runs.
- Synchronize/evaluate GPU work before recording synced stage timing or final materialization.
- Record if MLX is unavailable instead of fabricating results.

## Fix Strategy

### Phase 1: Honest Status And Runtime Metadata

- Add a runtime capability/status helper that can describe `selected_backend`, `supports_gpu`, `requires_serial_runtime`, and whether this pipeline has backend-aware stages enabled.
- Do not claim "full MLX acceleration" unless type trace shows full-image stages stay on MLX until final output.
- Update GUI/status/log text to say the current truth, for example: `MLX selected; runtime uses mixed CPU/MLX path with optional GPU kernels`.
- Use `backend_summary(..., runtime_gpu_enabled=...)` only with a real runtime flag, not the default.

### Phase 2: Serialization Semantics

- Reconnect `requires_serial_runtime` to actual runtime execution in `Simulator.process()`, `process_with_metadata()`, `update_params()`, and `soft_update()` where the contained pipeline backend requires it.
- Add a focused test with a fake backend/pipeline to prove the serialization context is entered only for `requires_serial_runtime=True`.

### Phase 3: Hot-Path MLX Residency

- Preserve SDR output semantics: final public `process()` output remains NumPy float64 unless a separate explicit API is introduced.
- Keep image-sized MLX float32 arrays resident after preprocess when `compute_backend="mlx"` and `gpu_precision="float32"`.
- Convert to NumPy only at:
  - final output/display/save boundary,
  - CPU validation reference,
  - confirmed CPU-only helper boundary.
- Add backend-aware `PrintingStage.develop()` by precomputing morphed print curves on CPU and using `interpolate_exposure_to_density_backend()` for the image-sized interpolation when backend is GPU.
- Avoid per-small-op `mx.eval()` / `synchronize()` in production code. Evaluation belongs in benchmark/test finalization.
- Preserve existing CPU path byte-for-byte where practical and within current test tolerances.

### Phase 4: Benchmark And Report

- Run baseline benchmark before hot-path code changes if feasible.
- Run the new benchmark after changes.
- If MLX still has no true full-res speedup, record that honestly and identify remaining bottlenecks.
- Update this document from plan to result report with measured data and remaining blockers.

## TDD Plan

- [x] Add unit tests for benchmark helper functions: size parsing, array description, stage trace schema, markdown/json payload shape.
- [x] Add a failing runtime API test showing `Simulator.process()` enters `serialized_metal_runtime()` for backends with `requires_serial_runtime=True`.
- [x] Add a failing backend/status test showing GPU summaries differentiate selected backend from runtime acceleration state.
- [x] Add or extend MLX residency tests for the highest-value stage boundary:
  - `PrintingStage.develop()` returns an MLX array when backend is MLX.
  - Full manual stage trace has fewer `mlx -> numpy -> mlx` round trips after the fix.
- [x] Keep tests skippable when MLX is unavailable.

## Verification Plan

Required commands:

```bash
uv run pytest tests/gui/test_layout.py tests/test_grain.py tests/test_pipeline_lut_lifecycle.py -q
```

Additional targeted commands expected for this task:

```bash
uv run pytest tests/test_gpu_backend.py tests/test_gpu_pipeline.py tests/test_runtime_api.py tests/test_gpu_validate.py -q
uv run pytest tests/test_mlx_runtime_hotpath_benchmark.py -q
```

New benchmark command, after implementation:

```bash
uv run python scripts/benchmark_mlx_runtime_hotpath.py --size full --include-preview-640 --runs 1 --warmups 1
```

If the local full-res source is unavailable or too slow, also run a deterministic smaller smoke:

```bash
uv run python scripts/benchmark_mlx_runtime_hotpath.py --size 640x640 --runs 1 --warmups 0
```

Final hygiene:

```bash
uv run python -m compileall -q src tests scripts
git diff --check
```

## Acceptance Standards

- MLX selection is still strict and correct:
  - `select_backend("mlx", precision="float32")` selects MLX when available.
  - `auto` may select MLX when available.
  - float64 GPU requests remain CPU-only or strict errors per current backend policy.
- Status and docs no longer imply full runtime acceleration when only optional GPU kernels are proven.
- Benchmark reports the required CPU full-res, MLX full-res `gpu_validate=False`, MLX full-res `gpu_validate=True`, and preview 640 cases.
- Benchmark outputs include backend identity, `supports_gpu`, `requires_serial_runtime`, `backend_summary`, shape, precision, validation flag, stage timings, total time, and type trace.
- Type trace can identify where arrays are NumPy vs MLX and where conversions happen.
- At least one confirmed hot-path CPU boundary is removed or proven non-removable with evidence.
- `requires_serial_runtime` has actual runtime effect or the document explicitly records why it cannot be safely wired in this pass.
- SDR output semantics remain unchanged within existing CPU/GPU tolerances.
- Required pytest slices pass or failures are documented with exact error output.
- Final report states whether real full-res acceleration appeared; no fabricated speedup conclusions.

## Initial Root-Cause Hypothesis

The user-observed equal speed is not caused by a failed `select_backend("mlx")`; MLX selection works. The likely root cause is a mixed runtime where enough image-sized work is still CPU-bound or materialized at CPU boundaries to erase the benefit of existing optional MLX kernels, especially when `gpu_validate=True` doubles work with a CPU reference run. The fix is to make status honest, measure with a stable benchmark/type trace, wire missing serialization semantics, and migrate the largest confirmed image-sized CPU interpolation/materialization boundary that can be changed without altering SDR semantics.

---

## Result Report

### Current Checkout Note

The initial audit was performed with live HEAD at `949cf43` and user-referenced `f0ca402` as its parent. During the session the checkout advanced to:

```text
d721fda (HEAD -> develop, origin/develop) docs: update upstream sync post-commit report
40e387b chore: finalize upstream sync state
949cf43 (backup/before-upstream-sync-20260602-2303) fix: handle Optional/float|None union types in GUI editor resolution
f0ca402 feat: add GPU compute backend section to ADVANCED tab
```

The MLX runtime changes are present in the current checkout. Existing unrelated untracked documentation files were left alone.

### Backend Selection

MLX selection is correct. The required probe still reports:

```text
cpu cpu False False cpu
auto mlx True True cpu runtime path; mlx validated for optional GPU kernels
mlx mlx True True cpu runtime path; mlx validated for optional GPU kernels
```

This remains expected for `backend_summary()` because its default `runtime_gpu_enabled=False` still produces the conservative summary. The runtime now exposes a separate pipeline-level status:

```text
MLX selected; mixed CPU/MLX runtime path with optional GPU kernels
```

That wording is intentional. It does not claim complete MLX acceleration.

### Implemented Fixes

- Added `runtime_backend_summary()` in `src/spektrafilm/gpu/backend.py` and exposed it through `SimulationPipeline.backend_runtime_summary()`.
- Updated GUI/controller status plumbing so a completed run can append the runtime backend truth to the user-visible status.
- Wired `requires_serial_runtime=True` into `Simulator.process()`, `process_with_metadata()`, `update_params()`, and `soft_update()` through `serialized_metal_runtime()`.
- Migrated `PrintingStage.develop()` to run image-sized print density interpolation through `interpolate_exposure_to_density_backend()` for GPU backends, while keeping the morphed print curves on the CPU side.
- Added `scripts/benchmark_mlx_runtime_hotpath.py` with CPU full-res, MLX full-res false/true validation, preview 640, stage timings, backend identity, conversion counters, and hot-path type traces.
- Added tests for runtime serialization, runtime summary propagation, controller status propagation, printing develop MLX residency, and benchmark output schema.
- Fixed a stale LUT lifecycle test fake so it accepts the production `gamut_compress` keyword argument.

### Benchmark Evidence

Primary completed artifact:

- `docs/dev/benchmark-artifacts/mlx_runtime_hotpath_20260602/benchmark-20260602-233135.json`
- `docs/dev/benchmark-artifacts/mlx_runtime_hotpath_20260602/benchmark-20260602-233135.md`

Input:

```text
img/test/portrait_leaves_32bit_linear_prophoto_rgb.tif
shape=[1000, 667, 3]
```

Results:

| Case | Backend | Shape | Precision | gpu_validate | Total | Wall | Summary |
|---|---|---:|---|---:|---:|---:|---|
| CPU full-res | cpu | 1000x667x3 | float64 | false | 2.3709s | 2.3737s | cpu |
| MLX full-res | mlx | 1000x667x3 | float32 | false | 0.6141s | 0.6146s | MLX selected; mixed CPU/MLX runtime path with optional GPU kernels |
| MLX full-res validate | mlx | 1000x667x3 | float32 | true | 2.1299s | 2.1304s | MLX selected; mixed CPU/MLX runtime path with optional GPU kernels |
| MLX preview 640 | mlx | 640x426x3 | float32 | false | 0.3415s | 0.3549s | MLX selected; mixed CPU/MLX runtime path with optional GPU kernels |

On this bounded full-res TIFF, MLX `float32` without validation is about `3.86x` faster than CPU. With `gpu_validate=True`, the CPU reference pass dominates and the result is close to CPU speed, which matches the user observation when validation or CPU-bound paths are included.

RAW full-res note:

- Attempted real OPPO RAW input: `/Users/retriedstormtrooper/Documents/OPPO 互联/combine dng/IMG20260530191638.dng`.
- The first full matrix with type trace was terminated after the CPU case exceeded 10 minutes.
- A second timed-only RAW full-res run was terminated after the CPU case exceeded 5 minutes.
- No RAW speedup conclusion is claimed from those interrupted runs. The report records only that this RAW CPU path is too slow for the interactive benchmark settings used here.

### Hot-Path Type Trace

For CPU full-res all traced full-image stages stayed as NumPy:

```text
preprocess: numpy.ndarray -> numpy.ndarray
filming.expose: numpy.ndarray -> numpy.ndarray
filming.develop: numpy.ndarray -> numpy.ndarray
printing.expose: numpy.ndarray -> numpy.ndarray
printing.develop: numpy.ndarray -> numpy.ndarray
scanning: numpy.ndarray -> numpy.ndarray
final.to_numpy_float64: numpy.ndarray -> numpy.ndarray
```

For MLX full-res `gpu_validate=False`, the current hot path is:

```text
preprocess: numpy.ndarray -> numpy.ndarray
filming.expose: numpy.ndarray -> mlx.core.array
filming.develop: mlx.core.array -> mlx.core.array
printing.expose: mlx.core.array -> mlx.core.array
printing.develop: mlx.core.array -> mlx.core.array
scanning: mlx.core.array -> mlx.core.array
final.to_numpy_float64: mlx.core.array -> numpy.ndarray
```

This proves MLX is no longer just a selected label for the measured TIFF path. It also proves the runtime is still mixed, because preprocess begins on NumPy and the public output boundary returns NumPy float64.

Conversion counters still show many `backend.asarray` calls:

```text
mlx_full_res_validate_false:
backend.asarray.input count=70 bytes=1113451572
backend.asarray.output count=70 bytes=1097001020
backend.to_numpy.input count=2 bytes=24
backend.to_numpy.output count=2 bytes=24
```

The tiny `to_numpy` counters reflect non-image scalar/reference conversions, while repeated `asarray` calls show remaining opportunities to cache constants and avoid repeated small conversions.

### Remaining CPU/Mixed Boundaries

- `SimulationPipeline._preprocess_base()` still receives and normalizes input as NumPy before the first backend-resident stage.
- The public `SimulationPipeline.process()` output still materializes NumPy float64 by design.
- `gpu_validate=True` runs a CPU reference pipeline and therefore should never be used as a speed benchmark.
- LUT construction/test callbacks and some reference/profile helpers still use CPU paths.
- RAW loading and RAW preprocessing remain outside the measured MLX stage residency and can dominate real camera-file runs.
- Repeated backend conversion of constants and small arrays remains visible in the conversion counters.

### Confidence Check

I am not claiming "full runtime acceleration" with 100% confidence, because the evidence says the runtime is still mixed. I am confident in the narrower facts below:

- MLX backend selection works.
- `backend_summary()` default wording explains the user's confusing summary.
- `requires_serial_runtime` now has a runtime effect.
- The measured TIFF full-res path keeps image-sized arrays on MLX from filming onward until final output.
- The measured TIFF full-res MLX path shows real acceleration when `gpu_validate=False`.
- `gpu_validate=True` explains near-CPU timing because it includes a CPU reference rerun.

The next highest-value work is to remove or explicitly classify the remaining NumPy preprocess boundary, reduce repeated `backend.asarray` conversions, and separately benchmark RAW loading/preprocessing so RAW-file latency is not misattributed to MLX compute.

### Verification Completed

Required:

```text
uv run pytest tests/gui/test_layout.py tests/test_grain.py tests/test_pipeline_lut_lifecycle.py -q
46 passed in 6.26s
```

Targeted:

```text
uv run pytest tests/test_mlx_runtime_hotpath_benchmark.py tests/test_runtime_api.py::TestRuntimeApi::test_process_uses_serialized_runtime_for_serial_backend tests/test_runtime_api.py::TestRuntimeApi::test_backend_runtime_summary_delegates_to_pipeline tests/gui/test_controller_runtime_module.py::test_execute_simulation_request_appends_runtime_backend_status tests/gui/test_controller_flow.py::test_process_image_with_runtime_captures_backend_runtime_summary tests/test_gpu_pipeline.py::test_printing_develop_keeps_mlx_array_when_available -q
9 passed in 1.05s
```

Backend/runtime slice:

```text
uv run pytest tests/test_gpu_backend.py tests/test_gpu_pipeline.py tests/test_runtime_api.py tests/test_gpu_validate.py tests/test_mlx_runtime_hotpath_benchmark.py -q
41 passed, 2 skipped in 2.41s
```

Benchmark smoke:

```text
uv run python scripts/benchmark_mlx_runtime_hotpath.py --input /tmp/nonexistent-spektrafilm-benchmark.dng --generated-size 96x64 --size 64x48 --warmups 0 --runs 1 --out-dir docs/dev/benchmark-artifacts/mlx_runtime_hotpath_20260602_smoke
```

Benchmark full-res TIFF:

```text
uv run python scripts/benchmark_mlx_runtime_hotpath.py --input img/test/portrait_leaves_32bit_linear_prophoto_rgb.tif --size full --warmups 0 --runs 1 --out-dir docs/dev/benchmark-artifacts/mlx_runtime_hotpath_20260602
```

Final hygiene:

```text
uv run python -m compileall -q src tests scripts
git diff --check
```

Both final hygiene commands passed.
