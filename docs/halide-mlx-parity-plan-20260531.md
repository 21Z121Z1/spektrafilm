# Halide / MLX Parity Plan - 2026-05-31

## Goal

Bring the experimental Halide backend as close as practical to the current MLX runtime path without changing Spektrafilm simulation semantics. Acceptance is based on real wall-clock timing, synchronized stage timing, final materialization cost, output precision against CPU float64 and MLX float32, and tests.

## Current Architecture Audit

### Runtime backend flow

- `RuntimePhotoParams.settings.compute_backend` and `gpu_precision` are selected in `SimulationPipeline.__init__`.
- `select_backend()` returns CPU, MLX, CuPy, or explicit Halide. `auto` still prefers MLX, then CuPy, then CPU; Halide is strict opt-in.
- The selected backend is passed into `SpectralLUTService`, `FilmingStage`, `PrintingStage`, and `ScanningStage`.
- `SimulationPipeline.process()` always materializes the final output as `np.asarray(..., dtype=np.float64)` at `_pipeline()` exit. This is part of end-to-end wall-clock and must be reported separately.

### MLX implementation

- `MlxBackend` is a real eager/lazy array backend over `mlx.core`, with Metal availability probing and explicit `eval()` / `synchronize()` hooks.
- MLX performance comes from stage-local residency: stage code calls backend ops for highlight boost, log/power, density interpolation, spectral LUT application, spectral chain ops, filters, and CCTF.
- `gpu/kernels/density.py`, `filters.py`, `lut.py`, and `color.py` contain MLX-specific custom Metal kernels or MLX-native ops for density interpolation, Gaussian/IIR filters, LUTs, highlight boost, CCTF, and matrix transforms.
- `PrintingStage` pre-converts static spectral tables to backend arrays, and `SpectralLUTService` keeps backend LUT copies. This avoids repeated numpy to MLX transfers.

### Halide implementation

- `HalideBackend` currently uses Python Halide JIT with `hl.get_host_target()`. It is float32-only and caches Func pipelines per instance.
- Its generic `ArrayBackend` methods mostly delegate to NumPy / opt_einsum. This means selecting `compute_backend="halide"` does not automatically make the normal runtime path use Halide kernels.
- Implemented Halide JIT kernels exist for RGB matrix, 3D LUT, spectral micro-kernels, FIR blur, CCTF encode/decode, 1D interpolation, and 2D LUT, but most normal kernel dispatch still bypasses them.
- `gpu/kernels/lut.py` dispatches 3D LUT to Halide via `backend.apply_lut_trilinear_3d()`. Density, filter, and CCTF runtime paths mostly fall back through generic protocol methods or CPU conversions.
- Existing docs report the same problem: Halide is correct for many micro-kernels, fast for 3D LUT, but slower end-to-end because the pipeline is not coarse-grained or fused.

### Stage-level differences

- `FilmingStage.expose()` benefits from backend highlight boost, LUT, filters, and backend log10. Halide gets only partial benefit because many backend helper functions do not dispatch to Halide-specific methods.
- `FilmingStage.develop()` calls backend density interpolation. MLX uses a Metal interpolation kernel; Halide currently falls back to CPU interpolation through backend conversion.
- `PrintingStage.expose()` is the major target. MLX keeps static spectral tables resident and uses backend ops. Halide currently materializes or computes through NumPy for most of the chain, so it loses the benefit of Halide fusion.
- `ScanningStage.scan()` is the second major target. The CMY to log XYZ chain can be fused into one Halide pipeline; today it is expressed as separate backend protocol operations.
- Grain remains a compatibility path. Main precision/performance validation uses grain OFF and halation ON; grain ON is a smoke test only.

## Why Halide Is Currently Slower Than CPU

1. The runtime does not call most Halide JIT kernels. Methods in `HalideBackend` are present but not reached by `gpu/kernels/density.py`, `filters.py`, and color dispatch in the same way MLX methods are reached.
2. Halide is used as many small JIT kernels rather than as coarse fused pipelines. Python boundary cost, `Buffer` construction, transposes, and per-kernel dispatch erase gains.
3. Generic `HalideBackend.einsum()`, `power()`, `log10()`, and `matmul()` are NumPy operations, not Halide operations.
4. The spectral path creates or implies huge `H x W x 81` intermediates (`density_spectral`, `light`). MLX can tolerate this better through device-resident lazy execution; Halide should fuse these reductions so intermediates are not separately materialized.
5. Timed runs may include Halide JIT compilation. Benchmark must separate warm-up/JIT from timed runs.
6. `supports_gpu=True` on Halide currently means "experimental accelerator backend", not necessarily a Metal/GPU target. The host target should remain experimental unless measurements prove a real end-to-end win.

## Hypotheses To Verify

- H1: Dispatching `cmy_to_log_xyz_backend()` to a fused Halide CMY-to-logXYZ pipeline reduces `ScanningStage.scan` time versus generic NumPy/opt_einsum.
- H2: Dispatching `PrintingStage._film_cmy_to_print_log_raw()` to a fused Halide CMY-to-logRaw pipeline reduces `PrintingStage.expose` time by eliminating separate `density_spectral` and `light` materialization.
- H3: A warm Halide run that excludes JIT is materially faster than the current Halide wall-clock, even if the first run remains slow.
- H4: Halide precision remains within the existing float32 envelope: PSNR >= 52 dB against CPU float64 for full pipeline, and mean_diff no worse than 1.5x the MLX mean_diff in the same configuration.
- H5: If Halide is still slower than CPU after fused spectral paths, the remaining bottleneck is in density interpolation, halation IIR/exponential filters, Python Buffer construction, or host-only Halide target limits.

## Planned File Changes

### Benchmark and diagnostics

- Create `scripts/benchmark_halide_mlx_parity.py`
  - Loads either the known local DNG or a deterministic generated fallback.
  - Runs CPU float64, CPU float32 where supported, MLX float32 if available, and Halide float32 if available.
  - Supports `--size full` and `--size 2048x1536`.
  - Separates warm-up/JIT from timed runs.
  - Reports wall-clock, synced-stage times, final materialization time, output shape/dtype/backend, and conversion counters.
  - Writes JSON and Markdown artifacts under `docs/dev/benchmark-artifacts/`.

- Add tests for the benchmark helpers in `tests/test_halide_mlx_benchmark.py`.
  - Keep unit tests synthetic and fast; do not run full 12MP inside pytest.

### Halide dispatch and fused kernels

- Modify `src/spektrafilm/gpu/halide_backend.py`
  - Add fused `cmy_to_log_xyz()` for HWC runtime arrays.
  - Add fused `cmy_to_log_raw()` for printing exposure spectral chain.
  - Cache fused pipelines by wavelength count and output channel count.
  - Preserve existing micro-kernel APIs and cleanup behavior.

- Modify `src/spektrafilm/gpu/kernels/density.py`
  - Dispatch `cmy_to_log_xyz_backend()` to `backend.cmy_to_log_xyz()` when present.
  - Keep existing MLX/CuPy/CPU semantics unchanged.

- Modify `src/spektrafilm/runtime/stages/printing.py`
  - Use `backend.cmy_to_log_raw()` for Halide when available.
  - Keep the current MLX path and CPU path intact.
  - Do not disable halation, spectral simulation, LUT, or scan semantics.

- Optionally modify `src/spektrafilm/gpu/kernels/filters.py` only after benchmark data proves filters dominate. Initial scope is spectral fusion because it is the largest known Halide end-to-end bottleneck.

### Tests

- Extend `tests/test_halide_spectral.py`
  - Verify fused `cmy_to_log_xyz()` and `cmy_to_log_raw()` against NumPy references.
  - Verify pipeline cache reuse and cleanup.

- Extend `tests/test_gpu_density.py`
  - Verify generic `cmy_to_log_xyz_backend()` dispatches to a backend-specialized method when present.

- Extend `tests/test_gpu_pipeline.py` or add a focused integration test
  - Run small image Halide pipeline against CPU reference with LUT/spatial effects configured in a way that exercises the fused path.

## Benchmark Contract

The benchmark artifact must include:

- Input identity: path or generated seed, shape, dtype, megapixels.
- Configuration: film profile, print profile, grain setting, halation setting, LUT settings, color spaces, auto exposure state.
- Backend identity: requested backend, selected backend, precision, Halide target, MLX availability.
- Warm-up/JIT timing separated from timed run.
- End-to-end wall-clock for each backend.
- Per-stage synchronized timing:
  - preprocess
  - film.expose
  - film.develop
  - print.expose
  - print.develop
  - scan
- Final materialization and output conversion time.
- Per-stage input/output metadata:
  - shape
  - dtype
  - Python type / backend type
  - bytes
- Conversion observations:
  - calls to `backend.asarray`
  - calls to `backend.to_numpy`
  - explicit final `np.asarray`
- Precision metrics:
  - max_diff
  - mean_diff
  - median_diff
  - RMSE
  - PSNR
  - per-channel max and mean

Unsynced dispatch-only timing is allowed only as secondary context and must not be used as the performance verdict.

## Acceptance Standards

### Hard minimum

- Halide output must remain valid and finite.
- CPU default behavior and MLX behavior must not regress.
- Halide must not become the default backend.
- Halide must not gain speed by disabling halation, spectral simulation, LUTs, scan, output CCTF, or by changing profile/size semantics.
- Timed Halide run must exclude JIT/warm-up from the timed run.

### Precision

- Primary reference: CPU float64.
- Secondary reference: MLX float32.
- Main config: `kodak_portra_400 / kodak_portra_endura`, grain OFF, halation ON.
- Halide vs CPU full-pipeline floor:
  - PSNR >= 52 dB.
  - mean_diff <= 1.5x MLX mean_diff under the same config.
  - max_diff should be in MLX's order of magnitude; if > 6e-2, document and isolate the source.

### Performance

- Hard target: 12MP Halide wall-clock faster than CPU float64.
- Preferred target: 12MP Halide wall-clock >= 2x CPU speedup.
- Stretch target: within 2x of current MLX wall-clock, or a benchmark-backed explanation for why host Halide cannot reach it.
- 2048x1536 must be measured separately to expose size-scaling and JIT amortization.

## Risks And Rollback

- Fused Halide spectral kernels may improve speed but increase compile time. Benchmark will report warm-up separately.
- Fused kernels may duplicate spectral formulas. Tests must pin parity against the existing NumPy/MLX chain.
- Halide Python JIT may still be host-only in this runtime, limiting speed relative to MLX Metal. If so, leave Halide experimental and document the AOT/Metal/Generator route as follow-up.
- `Buffer` dimension ordering is error-prone. Tests must cover non-square images and channel ordering.
- Any behavior change outside explicit Halide dispatch is a regression. CPU and MLX paths are the rollback boundary.

## Implementation Sequence

1. Add failing tests for fused Halide spectral methods and dispatch.
2. Implement the benchmark helper/script with synthetic fast tests.
3. Implement `HalideBackend.cmy_to_log_xyz()` and dispatch from `gpu/kernels/density.py`.
4. Implement `HalideBackend.cmy_to_log_raw()` and dispatch from `PrintingStage`.
5. Run Halide-focused tests and GPU parity tests.
6. Run benchmark on 2048x1536 and 12MP if the local DNG is available.
7. Save benchmark/precision results to `docs/dev/benchmark-artifacts/`.
8. Re-run self-audit questions and decide whether Halide remains experimental.

## Self-Audit Questions To Answer In The Result Document

- Did Halide really execute the Halide fused path, or did it silently fall back to CPU?
- Did timed runs exclude JIT and warm-up?
- Were stage timings synchronized and separated from final conversion?
- Did any speedup come from changing rendering semantics?
- Is Halide output numerically comparable to CPU and MLX?
- Did CPU or MLX behavior regress?
- Were both 12MP and 2048x1536 inputs tested or honestly skipped?
- Did grain OFF + halation ON and grain ON smoke both run?
