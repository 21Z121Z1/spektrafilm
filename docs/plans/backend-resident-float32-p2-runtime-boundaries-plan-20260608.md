# Backend Resident Float32 P2 Runtime Boundaries Plan - 2026-06-08

## Gate Status

P1 is closed. The P1 report records:

- SDR/golden subset: `7 passed`.
- P1 focused tests: `15 passed`.
- Full non-GUI suite: `1402 passed, 7 skipped, 1 warning`.
- MLX backend policy returns `mlx.core.array mlx.core.float32` with
  `SimulationPipeline.materialize` near zero.

P2 is therefore allowed to start.

## Refined P2 /goal

Prove and harden runtime middle-stage residency for the MLX/Metal float32 path:

- `LOG_E_FILM`, `CMY_FILM`, `LOG_E_PRINT`, `CMY_PRINT`, and `RGB_OUT` remain
  backend arrays under `compute_backend="mlx"`, `gpu_precision="float32"`,
  `materialize_policy="backend"`.
- Full-size `to_numpy` host readbacks before final materialization are recorded
  and rejected unless explicitly classified as allowed.
- Allowed CPU boundaries remain allowed: LUT build-time sampling, tiny
  black/white/midgray reference arrays, auto-exposure preview, resize fallback,
  `gpu_validate`, debug nan checks, explicit final materialization, and P4
  HDR/RouteMaster sidecars.
- CPU/default public API and SDR output semantics remain unchanged.

This is P2 only. GUI preview/export separation remains P3; HDR sidecars and
grain/stochastic validation remain P4/P5.

## Audit Evidence

Files audited:

- `src/spektrafilm/runtime/pipeline.py`
- `src/spektrafilm/runtime/stages/filming.py`
- `src/spektrafilm/runtime/stages/printing.py`
- `src/spektrafilm/runtime/stages/scanning.py`
- `src/spektrafilm/runtime/services/spectral_lut_compute.py`
- `src/spektrafilm/runtime/services/color_reference.py`
- `src/spektrafilm/gpu/backend.py`
- `src/spektrafilm/gpu/mlx_backend.py`
- `src/spektrafilm/gpu/numpy_backend.py`
- `src/spektrafilm/gpu/kernels/lut.py`
- `src/spektrafilm/gpu/kernels/density.py`
- `src/spektrafilm/gpu/kernels/color.py`
- `src/spektrafilm/gpu/kernels/gamut_compress.py`
- `src/spektrafilm/model/develop.py`
- `src/spektrafilm/model/diffusion.py`
- `src/spektrafilm/model/grain.py`

Current source facts:

- `SimulationPipeline._pipeline()` materializes only at final
  `_materialize_output()` for the normal process path.
- Topology `collect` bypasses final materialization and can expose stage
  intermediates directly.
- `PrintingStage.expose()` has a GPU direct path using
  `_spectral_compute_enlarger_gpu()` and backend density/light/raw helpers.
- `ScanningStage._density_to_master()` routes the scanner spectral path through
  `SpectralLUTService.spectral_compute_scanner()` and then backend XYZ/RGB,
  gamut compression, blur, and CCTF helpers.
- `SpectralLUTService._spectral_compute()` uses backend arrays for direct GPU
  calculation and backend LUT application. GPU LUT build-time uses NumPy
  callback sampling and is an allowed CPU boundary.
- `ColorReferenceService._to_numpy_scalar()` intentionally reads tiny scalar
  reference values.
- `gpu_validate` intentionally materializes for CPU reference comparison.
- `process_master()` and RouteMaster construction still materialize sidecars;
  this is P4 scope, not P2 normal runtime scope.

Live trace on this machine:

```text
log_e_film  mlx.core.array mlx.core.float32 (32, 32, 3)
cmy_film    mlx.core.array mlx.core.float32 (32, 32, 3)
log_e_print mlx.core.array mlx.core.float32 (32, 32, 3)
cmy_print   mlx.core.array mlx.core.float32 (32, 32, 3)
rgb_out     mlx.core.array mlx.core.float32 (32, 32, 3)
```

## Implementation Scope

P2 will add:

- A lightweight backend residency diagnostic recorder.
- Instrumentation in backend `asarray()` and `to_numpy()` methods that records
  conversions only when diagnostics are active.
- Tests proving MLX stage collects stay backend-resident.
- Tests proving normal MLX backend-policy runtime has no unallowed full-size
  `to_numpy` before final materialization.
- A benchmark/diagnostic script reporting stage output types, conversion events,
  timings, explicit sync, and explicit validation conversion.
- A P2 report with commands, results, limitations, and the P2 gate decision.

Potential fixes if diagnostics expose a real issue:

- Keep scanner/enlarger LUT apply-time on backend.
- Move any accidental full-size `to_numpy` behind an explicit allowed
  materialization or replace it with backend operations.

## Explicit Non-Goals

- No GUI preview/export split.
- No HDR RouteMaster or sidecar rewrite.
- No ResizingService GPU rewrite.
- No grain/stochastic rewrite.
- No float16 implementation.
- No global float32 conversion.
- No change to CPU default dtype or public API.
- No change to SDR rendering semantics.

## Planned File Changes

- `src/spektrafilm/gpu/backend.py`
- `src/spektrafilm/gpu/numpy_backend.py`
- `src/spektrafilm/gpu/mlx_backend.py`
- `src/spektrafilm/gpu/cupy_backend.py`
- `src/spektrafilm/gpu/halide_backend.py`
- New `src/spektrafilm/gpu/residency.py`
- New `tests/test_backend_resident_runtime_boundaries.py`
- New `tools/benchmark_backend_resident_runtime_boundaries.py`
- New `docs/reports/backend-resident-float32-p2-runtime-boundaries-20260608.md`

## Risk Analysis

- Diagnostics must be inactive by default and must not change runtime behavior.
- Lazy MLX execution can hide pending work; benchmark must report explicit sync
  separately from graph construction and explicit NumPy conversion.
- Tiny reference readbacks must not be misclassified as regressions.
- LUT build-time CPU sampling is allowed; LUT apply-time full-image readbacks
  are not.
- `gpu_validate=True` is correctness validation and intentionally materializes.
- Existing dirty HDR/GUI worktree changes are unrelated and must not be reverted.

## Validation Plan

Required P2 commands:

```bash
.venv/bin/python -m pytest tests/test_backend_resident_runtime_boundaries.py -q
.venv/bin/python -m pytest tests/test_runtime_materialize_policy.py tests/test_backend_resident_float32.py tests/test_gpu_highlight_boost_sync.py -q
.venv/bin/python -m pytest tests/test_pipeline_smoke.py::test_midgray_input_produces_expected_output_values tests/test_regression_baselines.py tests/test_upstream_parity.py::TestGoldenReference::test_midgray_output_golden_reference -q
.venv/bin/python tools/benchmark_backend_resident_runtime_boundaries.py --backend cpu --runs 2 --warmups 1 --no-write
.venv/bin/python tools/benchmark_backend_resident_runtime_boundaries.py --backend mlx --precision float32 --runs 2 --warmups 1 --no-write
.venv/bin/python -m pytest --ignore=tests/gui -q
```

If MLX/Metal is unavailable, MLX-specific tests must skip and the benchmark must
report the skip reason.

## Gate Decision Criteria

P2 can advance to P3 only if:

- P1 tests remain green.
- New P2 tests pass or skip only for documented MLX unavailability.
- MLX stage collects for `LOG_E_FILM`, `CMY_FILM`, `LOG_E_PRINT`,
  `CMY_PRINT`, and `RGB_OUT` are backend arrays.
- Diagnostics report no unallowed full-size `to_numpy` in normal MLX backend
  policy runtime before explicit validation/export conversion.
- CPU/default behavior remains unchanged.
- Benchmark distinguishes runtime, materialization, sync, and explicit NumPy
  conversion.
- P2 report documents what was fixed, what was only measured, known limits, and
  whether P3 is allowed.
