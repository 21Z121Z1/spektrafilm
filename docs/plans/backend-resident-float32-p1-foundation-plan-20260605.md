# Backend Resident Float32 P1 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish P1 only: prove and harden the MLX/Metal backend-resident float32 foundation while preserving the legacy CPU/public API default of NumPy float64 output.

**Architecture:** Keep the existing runtime topology and public API stable. Add only the missing backend scalar-reduction primitive needed to keep highlight boost from forcing MLX scalar materialization, then add targeted tests, a benchmark/diagnostic, and a P1 report that gates any P2 work.

**Tech Stack:** Python 3.13, NumPy, MLX/Metal optional backend, CuPy/Halide optional backends, pytest, uv, Spektrafilm runtime pipeline.

---

## New /goal

Complete a verified P1 foundation for `compute_backend="mlx"`, `gpu_precision="float32"`, and `materialize_policy="backend"`:

- Default CPU/public API behavior remains NumPy `float64`.
- `materialize_policy` accepts exactly `numpy_float64`, `numpy_float32`, and `backend`.
- MLX backend policy returns a backend-resident `mlx.core.array` with `float32` dtype.
- GPU float32 preprocess no longer unconditionally enters the legacy `np.double(np.array(...))` branch.
- `boost_highlights_backend()` no longer calls the Python-scalar `backend.max()` synchronization path on GPU backends.
- Tests and benchmark prove output types/dtypes, materialization timing, highlight sync behavior, finiteness, and CPU compatibility.
- P1 report documents the remaining P2/P3/P4 boundaries and explicitly states whether P2 is allowed.

This plan intentionally does not claim the full P2/P3/P4 end-to-end resident path.

## Official and local sources checked

- OpenAI Codex manual refreshed locally at `/var/folders/9m/l8brh8z93lb589gnms27vrrm0000gn/T/openai-docs-cache/codex-manual.md`.
  - Best-practices section says complex tasks should be scoped with goal/context/constraints/done-when, planned first, tested, and reviewed.
  - `/goal` guidance says goals should include measurable success criteria.
  - `AGENTS.md` guidance maps to repository instructions; this repo currently has `CLAUDE.md`, not `AGENTS.md`.
- MLX official docs checked:
  - `https://ml-explore.github.io/mlx/build/html/usage/lazy_evaluation.html`
  - `https://ml-explore.github.io/mlx/build/html/usage/numpy.html`
  - `https://ml-explore.github.io/mlx/build/html/python/_autosummary/mlx.core.eval.html`
  - Key implication: NumPy conversion, scalar `.item()`, printing arrays, and scalar-array control flow trigger evaluation.
- NumPy official docs checked:
  - `https://numpy.org/doc/stable/reference/generated/numpy.ndarray.astype.html`
  - `https://numpy.org/doc/2.1/reference/generated/numpy.asarray.html`
  - Key implication: explicit dtype conversion and `astype`/`asarray` may allocate and should be treated as materialization boundaries.
- Repository guidance checked:
  - `CLAUDE.md`: use `.venv/bin/python` or `uv`, preserve behavior, keep fixes targeted, GPU must match CPU within float32 tolerance, run non-GUI tests when practical.
- Repository reports checked:
  - `docs/reports/backend-resident-float32-pipeline-audit-20260605.md`
  - `docs/reports/metal-p0-p4-benchmark-20260604-144839.md`
  - `docs/reports/metal-p0-p4-benchmark-20260604-144839.json`
  - `docs/reports/metal-p0-p4-benchmark-20260605-134223.md`
  - `docs/reports/metal-p0-p4-benchmark-20260605-134223.json`
  - `docs/reports/gui-mlx-full-render-benchmark-20260604.md`
  - `docs/reports/gui-mlx-full-render-benchmark-20260604-mlx.md`
  - `docs/reports/gui-mlx-full-render-benchmark-20260604-mlx.json`
  - `docs/reports/gui-mlx-full-render-benchmark-20260604-cpu.md`
  - `docs/reports/gui-mlx-full-render-benchmark-20260604-cpu.json`

Internet search was available. No external claim in this plan relies on model memory alone.

## Current source evidence

- `src/spektrafilm/runtime/params_schema.py`
  - `SettingsParams.materialize_policy` already exists with default `"numpy_float64"`.
  - `RuntimePhotoParams.__post_init__` already rejects unsupported policies.
- `src/spektrafilm/runtime/pipeline.py`
  - `SimulationPipelineResult.image` is typed as `Any`.
  - `_materialize_output_value()` already branches on `numpy_float64`, `numpy_float32`, and `backend`.
  - `backend` policy returns the backend array only when `self._backend.supports_gpu`; CPU returns `np.asarray(value)`.
  - `_preprocess_base()` already has `_should_use_backend_preprocess()`.
  - `_preprocess_base_backend()` keeps MLX/CuPy/Halide float32 arrays resident when crop is disabled and `upscale_factor == 1.0`.
  - `_backend_auto_exposure_preview()` intentionally syncs a small preview for CPU AE metering.
  - `_backend_crop_and_rescale()` intentionally falls back to CPU/skimage for resize, then rewraps float32 backend arrays.
- `src/spektrafilm/gpu/kernels/color.py`
  - `boost_highlights_backend()` still uses `backend.max(x)` when `x_max is None`, then Python float branches on `x_max`, `raw_x0`, and `denom`.
  - For MLX, `MlxBackend.max()` calls `mx.max`, `self.eval(value)`, and `float(np.asarray(value))`, which is a forced evaluation point.
- `src/spektrafilm_gui/controller_runtime.py`
  - GUI worker still performs `scan_array = np.asarray(scan)` and stores a full `float_image`. This is P3 scope, not P1, but must be documented as an unresolved boundary.
- `tests/test_gpu_pipeline.py`
  - Existing tests already cover default float64 output, `numpy_float32`, CPU backend policy fallback, MLX backend policy output, and preprocess backend rewrap.
  - P1 still needs dedicated materialize-policy/process-with-metadata coverage and highlight-sync diagnostics.
- `tools/benchmark_metal_pipeline_p0_p4.py`
  - Existing benchmark covers CPU baseline, MLX `numpy_float64`, and MLX `backend`, but not `numpy_float32` and not the highlight max sync diagnostic.

## Current dtype/materialization boundaries

- Keep as compatibility boundaries in P1:
  - CPU/default `_preprocess_base`: `np.double(np.array(image)[:, :, 0:3])`.
  - CPU/default final materialization: `np.asarray(value, dtype=np.float64)`.
  - CPU backend with `materialize_policy="backend"` returns NumPy through `np.asarray(value)`.
  - `gpu_validate=True` explicitly materializes GPU output to NumPy for CPU comparison.
  - Auto exposure preview materializes a small backend slice only.
  - Crop/resize CPU fallback materializes only when `io.upscale_factor != 1.0` or crop path needs CPU behavior; the result is rewrapped in backend default dtype.
- Must fix in P1:
  - `boost_highlights_backend()` must not call Python-scalar `backend.max()` on GPU backend hot path.
- Defer with documentation:
  - GUI `scan_array = np.asarray(scan)` full-image materialization.
  - HDR `_scene_luminance()` CPU/NumPy metadata path.
  - Spectral LUT hot-path validation/test point CPU roundtrips.
  - Grain/stochastic and large filter CPU fallbacks.

## Implementation scope

### Modify

- `src/spektrafilm/gpu/backend.py`
  - Extend `ArrayBackend` with `max_array(self, x: Any) -> Any`.
- `src/spektrafilm/gpu/numpy_backend.py`
  - Add `max_array()` returning `np.max(x)`.
  - Keep `max()` returning Python `float` for legacy callers.
- `src/spektrafilm/gpu/mlx_backend.py`
  - Add `max_array()` returning `self.mx.max(x)` without `eval()` or `np.asarray()`.
  - Keep `max()` unchanged for legacy scalar callers.
- `src/spektrafilm/gpu/cupy_backend.py`
  - Add `max_array()` returning `self.cp.max(x)` without `synchronize()`.
  - Keep `max()` unchanged for legacy scalar callers.
- `src/spektrafilm/gpu/halide_backend.py`
  - Add `max_array()` returning `np.max(x)` because Halide generic arrays are NumPy-backed here.
- `src/spektrafilm/gpu/kernels/color.py`
  - Use backend-resident scalar arrays when `x_max is None` and backend supports GPU.
  - Preserve exact old behavior for CPU and for explicit numeric `x_max`.
  - Avoid Python control flow on backend scalar arrays. Use element-wise safe denominators and `backend.where`.
- `tests/test_runtime_materialize_policy.py`
  - Add focused P1 policy tests, including process-with-metadata.
- `tests/test_backend_resident_float32.py`
  - Add focused P1 MLX skip-aware tests for backend output dtype, preprocess dtype, finiteness, and CPU parity after explicit conversion.
- `tests/test_gpu_highlight_boost_sync.py`
  - Add tests proving `boost_highlights_backend()` does not call `backend.max()` for GPU-like backend objects and still matches the CPU reference.
- `tools/benchmark_backend_resident_float32.py`
  - Add P1 benchmark/diagnostic covering CPU default, MLX `numpy_float64`, MLX `numpy_float32`, and MLX `backend`.
- `docs/reports/backend-resident-float32-p1-foundation-20260605.md`
  - Add final P1 evidence report after tests/benchmarks run.

### Do not modify in P1

- No GUI preview/export architecture split.
- No ResizingService GPU rewrite.
- No HDR metadata GPU-native rewrite.
- No grain/stochastic rewrite.
- No full Spektrafilm float32 conversion.
- No float16 implementation.
- No SDR rendering semantic changes.
- No public API default output change.

## Design details

### Backend max array API

Add a protocol method:

```python
def max_array(self, x: Any) -> Any: ...
```

Semantics:

- Returns a backend scalar array when the backend has lazy/device arrays.
- Does not call `eval()`, `synchronize()`, `to_numpy()`, or `np.asarray()` for MLX/CuPy.
- Returns a NumPy scalar for CPU/Halide generic fallback.
- Existing `max()` remains a Python `float` API for callers that explicitly need host scalar control flow.

### Highlight boost backend path

For GPU-backed calls with `x_max is None`:

- Compute `x_max_arr = backend.max_array(x)`.
- Compute `raw_x0 = backend.clip(midgray * 2**protect_ev, 0.0, x_max_arr)` using backend-compatible clipping. If the existing `backend.clip()` only accepts numeric hi for some backends, use `backend.maximum`/`backend.minimum` helper or add `minimum()` only if required by tests.
- Avoid `if x_max == 0.0`, `if raw_x0 >= x_max`, and `if denom <= 0.0` Python branches for backend scalar arrays.
- Compute the curve with safe denominators:
  - `safe_x_max = backend.where(x_max_arr > 0, x_max_arr, 1.0)`
  - `denom_safe = backend.where(denom > 0, denom, 1.0)`
  - `active = (x_max_arr > 0) & (raw_x0 < x_max_arr) & (denom > 0)`
  - `boosted = values + b`
  - `return backend.where(active, boosted, values)`
- For CPU or explicit numeric `x_max`, keep the old scalar implementation to preserve exact behavior and tiled-test parity.

If MLX lacks one of the scalar-array comparisons/operators in the current environment, fallback must be local, explicit, tested, and documented. Do not silently reintroduce `backend.max()` in the default MLX hot path.

## Risks

- Scalar-array control flow risk: MLX docs warn scalar-array control flow evaluates. P1 design avoids Python `if` on backend scalars.
- Numerical parity risk: removing scalar branches changes protection behavior near all-zero inputs or degenerate denom. Tests must cover zeros, low values, and normal highlights.
- Backend protocol risk: every backend implementation must add `max_array()` or structural typing will drift.
- Lazy benchmark risk: backend output timing can look fast because the graph is unevaluated. Benchmark must record explicit sync/eval after `process()` separately from `SimulationPipeline.materialize`.
- GUI confusion risk: P1 backend policy is not a GUI preview solution. Report must explicitly defer `controller_runtime.py` full-image `np.asarray(scan)` to P3.

## Rollback strategy

- Revert the `max_array()` additions and `boost_highlights_backend()` change as one small set if parity fails.
- Existing `materialize_policy` and preprocess fast path already exist in the current tree; do not remove them unless tests prove regression.
- Because P1 keeps old `backend.max()` and old scalar code for CPU/explicit `x_max`, rollback risk is isolated to GPU no-`x_max` highlight boost calls.

## Verification plan

Run red/green and final verification with:

```bash
uv run pytest tests/test_runtime_materialize_policy.py -q
uv run pytest tests/test_backend_resident_float32.py -q
uv run pytest tests/test_gpu_highlight_boost_sync.py -q
uv run pytest tests/test_gpu_pipeline.py tests/test_gpu_backend.py tests/test_gpu_highlight_boost.py -q
uv run python tools/benchmark_backend_resident_float32.py --backend cpu --runs 2 --warmups 1
uv run python tools/benchmark_backend_resident_float32.py --backend mlx --precision float32 --runs 2 --warmups 1
uv run pytest --ignore=tests/gui -q
```

If full non-GUI pytest is too slow or blocked by pre-existing environment issues, record the subset commands, failure text, and reason in the P1 report. If MLX/Metal is unavailable, MLX tests must skip and the benchmark must report `skipped`, not fail.

## Task checklist

### Task 1: Write P1 policy and residency tests

**Files:**
- Create: `tests/test_runtime_materialize_policy.py`
- Create: `tests/test_backend_resident_float32.py`

- [ ] Add tests for default CPU `numpy_float64`, explicit `numpy_float32`, CPU `backend` fallback, invalid policy error, and `process_with_metadata()` preserving policy semantics.
- [ ] Add MLX skip-aware tests for backend policy output type/dtype, explicit NumPy conversion parity with CPU, finite output, preprocess backend dtype, and materialize timing not hiding NumPy float64 conversion.
- [ ] Run both new test files and confirm failures only reflect missing/insufficient coverage or implementation gaps.

### Task 2: Write highlight sync tests

**Files:**
- Create: `tests/test_gpu_highlight_boost_sync.py`
- Modify only if needed: `tests/test_gpu_backend.py`

- [ ] Add a fake GPU backend where `max()` raises and `max_array()` returns a backend-like scalar/array.
- [ ] Assert `boost_highlights_backend(..., x_max=None)` does not call `max()` on the fake GPU backend.
- [ ] Assert numeric output matches the old CPU scalar implementation for normal highlight ramps and all-zero input.
- [ ] Add backend primitive tests for `max_array()` on NumPy and skip-aware MLX if practical.
- [ ] Run the new test and confirm it fails before production code changes.

### Task 3: Implement backend `max_array`

**Files:**
- Modify: `src/spektrafilm/gpu/backend.py`
- Modify: `src/spektrafilm/gpu/numpy_backend.py`
- Modify: `src/spektrafilm/gpu/mlx_backend.py`
- Modify: `src/spektrafilm/gpu/cupy_backend.py`
- Modify: `src/spektrafilm/gpu/halide_backend.py`

- [ ] Add `max_array()` to `ArrayBackend`.
- [ ] Implement no-sync MLX/CuPy versions.
- [ ] Implement CPU/Halide NumPy versions.
- [ ] Keep existing `max()` behavior unchanged.
- [ ] Run `uv run pytest tests/test_gpu_backend.py -q`.

### Task 4: Remove highlight boost hot-path scalar sync

**Files:**
- Modify: `src/spektrafilm/gpu/kernels/color.py`

- [ ] Route GPU/no-explicit-`x_max` calls through backend-resident `max_array()`.
- [ ] Preserve old scalar branch for CPU and explicit `x_max`.
- [ ] Avoid Python `if` on backend scalar arrays.
- [ ] Run highlight tests and existing GPU highlight tests.

### Task 5: Add P1 benchmark

**Files:**
- Create: `tools/benchmark_backend_resident_float32.py`
- Optionally reuse code from: `tools/benchmark_metal_pipeline_p0_p4.py`

- [ ] Cover CPU `numpy_float64`.
- [ ] Cover MLX `numpy_float64`, `numpy_float32`, and `backend`.
- [ ] Record output type, dtype, shape, materialize timing, explicit sync timing, and max finite check.
- [ ] Write JSON and Markdown reports under `docs/reports/`.
- [ ] Gracefully skip unavailable MLX/Metal.

### Task 6: Final P1 verification and report

**Files:**
- Create: `docs/reports/backend-resident-float32-p1-foundation-20260605.md`

- [ ] Run targeted P1 tests.
- [ ] Run benchmark CPU and MLX.
- [ ] Run broader non-GUI pytest if practical.
- [ ] Review `git diff` for accidental GUI/P2/P3/P4 scope creep.
- [ ] Write report with modified files, commands, results, benchmark summary, correctness validation, known limits, and P2 gate decision.
- [ ] Only if every P1 hard gate passes, explicitly allow P2. Otherwise, state P2 is blocked and why.

## P1 gate decision before implementation

P1 is not complete at plan time.

Current partial pass:

- `materialize_policy` field and basic pipeline branch exist.
- GPU float32 preprocess branch exists.
- Existing benchmark reports show `SimulationPipeline.materialize` is near zero for MLX backend policy.

Current blockers:

- `boost_highlights_backend()` still calls `backend.max()` and forces MLX evaluation.
- Dedicated P1 test files requested by the task do not exist.
- Dedicated P1 benchmark `tools/benchmark_backend_resident_float32.py` does not exist.
- P1 final report does not exist.

P2 is not allowed until this plan's P1 verification and report are complete.
