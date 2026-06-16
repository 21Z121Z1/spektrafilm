# Backend Resident Float32 P2 Runtime Boundaries Report - 2026-06-08

## Executive Summary

P2 runtime middle-boundary work is complete and the P2 gate is closed.

What changed:

- Added dormant-by-default residency diagnostics for backend `asarray()` and
  `to_numpy()` conversion choke points.
- Added P2 tests proving MLX middle-stage taps stay backend-resident float32.
- Added a P2 benchmark/diagnostic that reports stage output types, conversion
  events, runtime, explicit sync, and explicit validation conversion.
- Fixed a correctness issue in GPU spectral LUT handling: backend spectral LUT
  requests now use exact backend direct spectral calculation instead of the
  existing approximate trilinear backend LUT apply path.

P3 is allowed to start, with a fresh GUI preview/export audit and plan.

## Modified Files

P2 implementation:

- `src/spektrafilm/gpu/residency.py`
- `src/spektrafilm/gpu/mlx_backend.py`
- `src/spektrafilm/gpu/numpy_backend.py`
- `src/spektrafilm/gpu/cupy_backend.py`
- `src/spektrafilm/gpu/halide_backend.py`
- `src/spektrafilm/runtime/services/spectral_lut_compute.py`
- `src/spektrafilm/runtime/stages/printing.py`

P2 tests and benchmark:

- `tests/test_backend_resident_runtime_boundaries.py`
- `tests/test_spectral_lut_service.py`
- `tools/benchmark_backend_resident_runtime_boundaries.py`

P2 docs:

- `docs/plans/backend-resident-float32-p2-runtime-boundaries-plan-20260608.md`
- `docs/reports/backend-resident-float32-p2-runtime-boundaries-20260608.md`

## Residency Diagnostics

`spektrafilm.gpu.residency` now provides:

- `record_backend_residency(...)` context manager;
- `ResidencyEvent` records with direction, backend, shape, dtype, bytes, stack
  label, allowed flag, and reason;
- default classification that treats backend uploads as allowed, tiny readbacks
  as allowed, and full-size `to_numpy` as unallowed unless the stack is an
  explicit boundary such as auto-exposure preview, resize fallback,
  `gpu_validate`, final materialization, debug nan checking, LUT build-time
  sampling, or RouteMaster/P4 sidecar materialization.

The recorder is inactive by default and does not change public API behavior.

## Runtime Boundary Results

Live MLX stage trace for a 384x512 synthetic float32 image:

| Tap | Type | Dtype | Shape |
|---|---|---|---|
| `log_e_film` | `mlx.core.array` | `mlx.core.float32` | `[384, 512, 3]` |
| `cmy_film` | `mlx.core.array` | `mlx.core.float32` | `[384, 512, 3]` |
| `log_e_print` | `mlx.core.array` | `mlx.core.float32` | `[384, 512, 3]` |
| `cmy_print` | `mlx.core.array` | `mlx.core.float32` | `[384, 512, 3]` |
| `rgb_out` | `mlx.core.array` | `mlx.core.float32` | `[384, 512, 3]` |

Normal MLX backend-policy runtime reports zero unallowed full-size `to_numpy`
events before explicit validation/export conversion.

## Spectral LUT Correctness

Audit finding:

- CPU 3D spectral LUT application uses the project PCHIP LUT path.
- The backend 3D LUT helper is documented as a fast trilinear pilot.
- On the scanner-LUT diagnostic run, the old resident backend LUT path differed
  too much from CPU LUT output to claim correctness.

P2 fix:

- GPU spectral LUT requests in `SpectralLUTService._spectral_compute()` use the
  exact backend direct spectral path.
- GPU enlarger LUT requests in `PrintingStage._spectral_compute_enlarger_gpu()`
  also use exact backend direct spectral calculation.
- Timing labels record these correctness-first fallbacks:
  `SpectralLUTService.gpu_lut_direct_fallback` and
  `PrintingStage.gpu_lut_direct_fallback`.

Result:

- No full-size backend-to-NumPy LUT apply boundary.
- MLX output with scanner/enlarger LUT flags matches CPU direct spectral output
  within `1e-5` in the new regression test.
- Exact backend PCHIP LUT application is not implemented; this is a future
  optimization, not a P2 correctness requirement.

## Commands Run

P2 tests:

```bash
.venv/bin/python -m pytest tests/test_backend_resident_runtime_boundaries.py -q
```

Result: `6 passed in 2.71s`.

Affected LUT tests:

```bash
.venv/bin/python -m pytest tests/test_spectral_lut_service.py -q
```

Result: `5 passed in 0.48s`.

P1 focused tests:

```bash
.venv/bin/python -m pytest tests/test_runtime_materialize_policy.py tests/test_backend_resident_float32.py tests/test_gpu_highlight_boost_sync.py -q
```

Result: `15 passed in 1.46s`.

SDR/golden subset:

```bash
.venv/bin/python -m pytest tests/test_pipeline_smoke.py::test_midgray_input_produces_expected_output_values tests/test_regression_baselines.py tests/test_upstream_parity.py::TestGoldenReference::test_midgray_output_golden_reference -q
```

Result: `7 passed in 1.22s`.

P2 CPU benchmark:

```bash
.venv/bin/python tools/benchmark_backend_resident_runtime_boundaries.py --backend cpu --runs 2 --warmups 1 --no-write
```

Result: CPU default output `numpy.ndarray float64`, median runtime `0.513685s`,
unallowed `to_numpy` `0`.

P2 MLX direct benchmark:

```bash
.venv/bin/python tools/benchmark_backend_resident_runtime_boundaries.py --backend mlx --precision float32 --runs 2 --warmups 1 --no-write
```

Result: MLX output `mlx.core.array mlx.core.float32`, median runtime
`0.036015s`, explicit sync `0.000075s`, explicit NumPy `0.017437s`,
unallowed `to_numpy` `0`, max abs diff vs CPU direct `6.4131e-06`.

P2 MLX scanner-LUT diagnostic:

```bash
.venv/bin/python tools/benchmark_backend_resident_runtime_boundaries.py --backend mlx --precision float32 --runs 2 --warmups 1 --scanner-lut --no-write
```

Result: MLX output `mlx.core.array mlx.core.float32`, median runtime
`0.031361s`, explicit sync `0.000094s`, explicit NumPy `0.016754s`,
unallowed `to_numpy` `0`, max abs diff vs CPU direct `6.4131e-06`.

The same run reports max abs diff vs CPU LUT `0.0105294`; this is expected
because the GPU path intentionally uses exact direct spectral calculation
instead of the CPU approximate LUT path until an exact backend PCHIP LUT exists.

Full non-GUI suite:

```bash
.venv/bin/python -m pytest --ignore=tests/gui -q
```

Result: `1408 passed, 7 skipped, 1 warning in 89.96s`.

## Correctness Validation Summary

- CPU/default public API still returns NumPy `float64`.
- P1 materialization policy behavior remains green.
- SDR/golden compatibility remains green.
- MLX direct runtime output matches CPU direct within `6.4131e-06`.
- MLX scanner/enlarger LUT flags route to exact backend direct spectral
  calculation and match CPU direct within `1e-5` in tests.
- No unallowed full-size `to_numpy` occurs in normal MLX backend-policy runtime
  before explicit validation/export conversion.

## Known Limits

- Exact backend PCHIP 3D spectral LUT application is not implemented. GPU
  spectral LUT flags use direct backend spectral calculation for correctness.
- P2 does not split GUI preview/export; GUI still materializes a full
  `float_image` and remains P3 scope.
- P2 does not make HDR RouteMaster sidecars backend-resident; P4 scope.
- Grain/stochastic and 12MP RAW matrix validation remain P4/P5 scope.
- Synthetic 384x512 diagnostics are not a 12MP RAW performance proof.

## Self-Audit

- P1 remains green: yes.
- Middle-stage MLX collect taps stay backend arrays: yes.
- No unallowed full-size middle-stage `to_numpy`: yes, diagnostics and benchmark
  show zero.
- Lazy execution is not hidden: benchmark reports explicit sync separately.
- Correctness was not sacrificed for LUT speed: yes, approximate backend LUT is
  bypassed in favor of exact backend direct calculation.
- CPU/default API and SDR tests remain green: yes.
- Documentation updated: yes.

## Gate Decision

P2 is complete and allowed to advance to P3.

P3 must start with its own audit and plan, focused on separating GUI preview
materialization from explicit export/full-float materialization.
