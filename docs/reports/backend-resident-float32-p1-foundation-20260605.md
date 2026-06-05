# Backend Resident Float32 P1 Foundation Report - 2026-06-05

## Executive Summary

P1 foundation is complete in the current working tree.

The implemented P1 delta adds a backend-resident scalar reduction API (`max_array`) and rewires `boost_highlights_backend()` so GPU/no-explicit-`x_max` calls no longer use the Python-scalar `backend.max()` path. Existing P1 foundations already present in the live tree were verified: default materialization remains NumPy `float64`, `numpy_float32` explicitly returns NumPy `float32`, CPU `backend` policy safely returns NumPy, MLX `backend` policy returns `mlx.core.array` `float32`, and MLX float32 preprocess avoids the legacy unconditional `np.double(np.array(...))` path.

P2 is allowed from the P1 evidence below, but P2/P3/P4 are not claimed complete by this report.

## Modified Files

P1 implementation:

- `src/spektrafilm/gpu/backend.py`
- `src/spektrafilm/gpu/numpy_backend.py`
- `src/spektrafilm/gpu/mlx_backend.py`
- `src/spektrafilm/gpu/cupy_backend.py`
- `src/spektrafilm/gpu/halide_backend.py`
- `src/spektrafilm/gpu/kernels/color.py`

P1 tests:

- `tests/test_runtime_materialize_policy.py`
- `tests/test_backend_resident_float32.py`
- `tests/test_gpu_highlight_boost_sync.py`
- `tests/test_gpu_backend.py`

P1 benchmark and docs:

- `tools/benchmark_backend_resident_float32.py`
- `docs/plans/backend-resident-float32-p1-foundation-plan-20260605.md`
- `docs/reports/backend-resident-float32-p1-benchmark-20260605-171413.md`
- `docs/reports/backend-resident-float32-p1-benchmark-20260605-171413.json`
- `docs/reports/backend-resident-float32-p1-benchmark-20260605-171428.md`
- `docs/reports/backend-resident-float32-p1-benchmark-20260605-171428.json`
- `docs/reports/backend-resident-float32-p1-foundation-20260605.md`

The working tree also contains unrelated modified/untracked HDR/routemaster/GUI files that were not part of this P1 implementation. They were not reverted.

## Materialize Policy Semantics Verified

- `numpy_float64`: legacy-compatible final output, NumPy `float64`.
- `numpy_float32`: explicit final output, NumPy `float32`.
- `backend`: GPU backends return backend arrays; CPU backend returns NumPy safely.
- Invalid policy: raises a clear `ValueError`.

The default remains `numpy_float64`, so default CPU/public API behavior is not changed by the P1 policy.

## MLX Float32 Preprocess Boundary

Verified behavior:

- `compute_backend="mlx"` and `gpu_precision="float32"` use the backend preprocess branch.
- With `crop=False`, `upscale_factor=1.0`, and auto exposure disabled, preprocess returns an MLX array with `mx.float32`.
- CPU/default preprocess remains the legacy NumPy `float64` path.

Documented remaining boundaries:

- Auto exposure can still materialize a small backend preview for CPU metering.
- Crop/upscale can still use CPU/skimage fallback and then rewrap as backend float32.
- ResizingService is not rewritten in P1.

## Highlight Boost Sync Result

Before P1, `boost_highlights_backend()` called `backend.max(x)` when `x_max is None`. For MLX, `MlxBackend.max()` performs `mx.max`, `eval`, `np.asarray`, and `float(...)`, which forces lazy graph evaluation into a Python scalar.

P1 adds:

- `ArrayBackend.max_array(x) -> Any`
- `MlxBackend.max_array()` returning `mx.max(x)` without `eval()`
- `CupyBackend.max_array()` returning `cp.max(x)` without stream synchronization
- CPU/Halide `max_array()` NumPy-compatible fallback
- GPU branch in `boost_highlights_backend()` that uses backend scalar arrays and `backend.where()` instead of Python scalar control flow

Tests prove:

- fake GPU backend raises if scalar `max()` is called, and the new highlight path passes;
- GPU `max_array()` path matches the CPU scalar reference for normal highlight ramps, all-zero input, and below-protection input;
- explicit `x_max` still preserves the tiled/global scalar path;
- MLX `max_array()` does not call `backend.eval()` when MLX is available.

## Benchmark Results

CPU benchmark:

`uv run python tools/benchmark_backend_resident_float32.py --backend cpu --runs 2 --warmups 1`

Output:

- `cpu_default`: NumPy `float64`, median wall `0.584686s`, materialize `0.000003s`, max abs diff vs CPU `0`.

MLX benchmark:

`uv run python tools/benchmark_backend_resident_float32.py --backend mlx --precision float32 --runs 2 --warmups 1`

Output:

| Case | Output | Median Wall | Materialize | Explicit Sync | Max Abs Diff vs CPU |
|---|---|---:|---:|---:|---:|
| `cpu_default` | `numpy.ndarray float64` | `0.556335s` | `0.000004s` | `0.000003s` | `0` |
| `mlx_numpy_float64` | `numpy.ndarray float64` | `0.020521s` | `0.013958s` | `0.000075s` | `2.23611e-06` |
| `mlx_numpy_float32` | `numpy.ndarray float32` | `0.017497s` | `0.013009s` | `0.000066s` | `2.23611e-06` |
| `mlx_backend` | `mlx.core.array mlx.core.float32` | `0.019660s` | `0.000001s` | `0.015122s` | `2.23611e-06` |

Interpretation:

- `mlx_backend` satisfies the P1 resident-output contract.
- `SimulationPipeline.materialize` no longer hides a full NumPy conversion under `materialize_policy="backend"`.
- Explicit sync remains visible and benchmark-side, which is expected under MLX lazy execution.
- This is a P1 residency/materialization benchmark, not a 12MP RAW performance proof.

## Correctness Validation

Commands run:

```bash
uv run pytest tests/test_runtime_materialize_policy.py -q
uv run pytest tests/test_backend_resident_float32.py -q
uv run pytest tests/test_gpu_highlight_boost_sync.py -q
uv run pytest tests/test_runtime_materialize_policy.py tests/test_backend_resident_float32.py tests/test_gpu_highlight_boost_sync.py -q
uv run pytest tests/test_gpu_pipeline.py tests/test_gpu_backend.py tests/test_gpu_highlight_boost.py -q
uv run pytest tests/test_gui_mlx_full_render_benchmark.py tests/test_mlx_runtime_hotpath_benchmark.py -q
uv run pytest --ignore=tests/gui -q
uv run pytest --ignore=tests/gui --ignore=tests/test_hdr_profile_cache.py --ignore=tests/test_hdr_routemaster_export.py --ignore=tests/test_hdr_routemaster_projection.py -q
uv run pytest --ignore=tests/gui --ignore=tests/test_hdr_profile_cache.py --ignore=tests/test_hdr_routemaster_export.py --ignore=tests/test_hdr_routemaster_projection.py --ignore=tests/test_routemaster.py --ignore=tests/test_regression_baselines.py -k 'not test_midgray_input_produces_expected_output_values and not test_midgray_output_golden_reference' -q
```

Results:

- `tests/test_runtime_materialize_policy.py`: `6 passed`
- `tests/test_backend_resident_float32.py`: `4 passed`
- `tests/test_gpu_highlight_boost_sync.py`: first red run failed on scalar `backend.max()` as expected; after implementation `5 passed`
- combined P1 new tests: `15 passed`
- `tests/test_gpu_pipeline.py tests/test_gpu_backend.py tests/test_gpu_highlight_boost.py`: `37 passed, 2 skipped`
- benchmark-script tests: `8 passed`
- expanded non-GUI suite excluding classified blockers: `1366 passed, 7 skipped, 2 deselected, 1 warning`

Full non-GUI collection/status:

- `uv run pytest --ignore=tests/gui -q` failed during collection because untracked files `tests/test_hdr_profile_cache.py`, `tests/test_hdr_routemaster_export.py`, and `tests/test_hdr_routemaster_projection.py` import missing `spektrafilm.hdr`.
- After excluding those untracked files, the suite reported 12 failures. Six were from untracked `tests/test_routemaster.py` expecting `Simulator.process_master`; six tracked golden/baseline failures were reproduced in a clean detached HEAD worktree at commit `3f40cd6`, proving they are baseline failures and not introduced by P1.

Clean HEAD baseline command:

```bash
uv run --with pytest pytest tests/test_pipeline_smoke.py::test_midgray_input_produces_expected_output_values tests/test_regression_baselines.py tests/test_upstream_parity.py::TestGoldenReference::test_midgray_output_golden_reference -q
```

Clean HEAD result:

- same six tracked smoke/regression/upstream-parity failures reproduced.

## Known Limits Not Solved In P1

- GUI preview/export still has a full-image `np.asarray(scan)` boundary in `src/spektrafilm_gui/controller_runtime.py`; this is P3.
- HDR scene luminance and route sidecars can still materialize CPU arrays; this is P4.
- Spectral LUT validation/test points and print/scanner middle-boundaries still need P2 audit and remediation.
- Crop/upscale still has a CPU/skimage fallback; this is explicitly documented as P1-compatible.
- Grain/stochastic effects are not rewritten in P1.
- Existing tracked golden/baseline failures remain unresolved baseline debt.
- Several untracked HDR/routemaster tests/files are present in the working tree and can affect unqualified full-suite runs.

## P1 Self-Audit

- Default CPU/public API behavior unchanged: yes. The default policy remains `numpy_float64`; CPU policy tests pass; P1 code changes do not touch CPU pipeline semantics.
- MLX backend policy avoids `_materialize_output()` NumPy float64 conversion: yes. Test monkeypatches pipeline `np.asarray` to fail under backend policy, and benchmark reports `SimulationPipeline.materialize = 0.000001s`.
- GPU float32 preprocess avoids unconditional `np.double`: yes. Existing/preexisting preprocess fast path is verified by MLX dtype tests.
- Highlight boost sync eliminated/reduced: yes for the P1 hot path. GPU/no-explicit-`x_max` now uses `max_array()` and backend scalar arrays; tests prevent regression to `backend.max()`.
- Correctness validation preserved: yes for P1 scope. MLX output converted explicitly to NumPy matches CPU within `2.23611e-06`, below the P1 threshold.
- Benchmark not lazy-misleading: yes. The benchmark separately reports pipeline materialize, explicit backend sync, and explicit NumPy conversion.
- Docs updated: yes. Plan, benchmark reports, and this P1 report are present.

## Gate Decision

P1 reaches evidence-backed confidence for the requested foundation.

P2 is allowed to begin. P2 must still start with its own audit and plan, and must not reuse the P1 benchmark as proof of middle-stage backend residency.
