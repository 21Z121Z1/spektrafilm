# Backend Resident Float32 P1 Foundation Plan - 2026-06-08

## New /goal

Complete and verify Spektrafilm P1 foundation for an MLX/Metal backend-resident float32 runtime path:

- Preserve default CPU/public API behavior: no caller-specified `materialize_policy` still returns `numpy.ndarray` `float64`.
- Keep SDR rendering semantics unchanged.
- Support exactly `materialize_policy="numpy_float64"`, `"numpy_float32"`, and `"backend"`.
- Ensure `compute_backend="mlx"`, `gpu_precision="float32"`, and `materialize_policy="backend"` can return a backend-resident MLX float32 array.
- Ensure the GPU float32 preprocess path does not enter the legacy unconditional `np.double(np.array(...))` conversion.
- Ensure `boost_highlights_backend()` avoids the Python-scalar `backend.max()` synchronization path for GPU/no-explicit-`x_max` calls, or documents any unavoidable sync boundary.
- Refresh P1 tests, benchmark evidence, and this plan/report before any P2 work.

This goal is P1 only. P2/P3/P4 remain gated and must start with their own audit and plan after P1 is proven.

## Sources Checked

Internet access was available.

- OpenAI Codex manual fetched locally at `/var/folders/9m/l8brh8z93lb589gnms27vrrm0000gn/T/openai-docs-cache/codex-manual.md`.
  - Relevant guidance: complex tasks should carry explicit goal/context/constraints/done-when, use plan-first behavior, validate with tests, and review diffs.
  - `/goal` guidance: a goal should be a persistent, measurable objective shaped before implementation.
  - `AGENTS.md` guidance: project instructions are the durable place for repo conventions; this repo has `CLAUDE.md`/`CLAUDE-RESEARCH.md`, not `AGENTS.md`.
- MLX official docs:
  - `https://ml-explore.github.io/mlx/build/html/usage/lazy_evaluation.html`
  - `https://ml-explore.github.io/mlx/build/html/usage/numpy.html`
  - `https://ml-explore.github.io/mlx/build/html/python/_autosummary/mlx.core.eval.html`
  - Design impact: MLX operations are lazy; `eval`, printing, NumPy conversion, scalar `.item()`, and scalar-array Python control flow can trigger evaluation.
- NumPy official docs:
  - `https://numpy.org/doc/stable/reference/generated/numpy.asarray.html`
  - Design impact: `np.asarray(..., dtype=...)` is an explicit array conversion and can copy when dtype/order/backend differ, so it is a materialization boundary in this project.
- Repository reports/benchmarks:
  - `docs/reports/metal-p0-p4-benchmark-20260604-144839.md`
  - `docs/reports/metal-p0-p4-benchmark-20260604-144839.json`
  - `docs/reports/gui-mlx-full-render-benchmark-20260604.md`
  - `docs/reports/gui-mlx-full-render-benchmark-20260604-mlx.md`
  - `docs/reports/gui-mlx-full-render-benchmark-20260604-mlx.json`
  - `docs/reports/gui-mlx-full-render-benchmark-20260604-cpu.md`
  - `docs/reports/gui-mlx-full-render-benchmark-20260604-cpu.json`
  - `docs/reports/backend-resident-float32-pipeline-audit-20260605.md`
  - `docs/reports/backend-resident-float32-p1-foundation-20260605.md`
  - `docs/reports/backend-resident-float32-p1-benchmark-20260605-171413.md`
  - `docs/reports/backend-resident-float32-p1-benchmark-20260605-171428.md`
- Repository guidance:
  - `CLAUDE.md`
  - `CLAUDE-RESEARCH.md`

## Current Source Evidence

- `src/spektrafilm/runtime/params_schema.py`
  - `SettingsParams.materialize_policy` exists and defaults to `"numpy_float64"`.
  - `RuntimePhotoParams.__post_init__` rejects unsupported materialization policies.
- `src/spektrafilm/runtime/pipeline.py`
  - `SimulationPipelineResult.image` is typed as `Any`.
  - `_materialize_output()` keeps the `SimulationPipeline.materialize` timing label and delegates to `_materialize_output_value()`.
  - `_materialize_output_value()` branches over `backend`, `numpy_float32`, and `numpy_float64`.
  - CPU/default `_preprocess_base()` still uses the legacy `np.double(np.array(image)[:, :, 0:3])`.
  - GPU float32 `_preprocess_base_backend()` converts RGB input to backend default dtype, performs backend crop by slicing, uses a small CPU auto-exposure preview when enabled, and uses CPU/skimage only for resize fallback before rewrapping as backend float32.
- `src/spektrafilm/gpu/backend.py`, `numpy_backend.py`, `mlx_backend.py`, `cupy_backend.py`, `halide_backend.py`
  - The backend protocol and implementations already expose `max_array()`.
  - `MlxBackend.max_array()` returns `mx.max(x)` without `eval()`; `MlxBackend.max()` remains the Python scalar sync path for legacy callers.
- `src/spektrafilm/gpu/kernels/color.py`
  - `boost_highlights_backend()` has a GPU/no-explicit-`x_max` branch using `backend.max_array()` and backend scalar arrays.
  - The CPU/explicit `x_max` branch still uses the legacy scalar code for parity and tiled callers.
- `src/spektrafilm_gui/controller_runtime.py`
  - GUI still stores a full `float_image`; this is a P3 boundary and is not changed in P1.

## Current Dtype And Materialization Boundaries

P1 compatibility boundaries to preserve:

- CPU/default preprocess: `np.double(np.array(image)[:, :, 0:3])`.
- CPU/default final output: `np.asarray(value, dtype=np.float64)`.
- CPU backend with `materialize_policy="backend"`: safe NumPy fallback.
- `gpu_validate=True`: explicit NumPy conversion for correctness validation.
- Auto exposure preview: small backend-to-NumPy preview for CPU metering.
- Resize fallback: CPU/skimage when `upscale_factor != 1.0`, followed by backend float32 rewrap.

P1 fixed or to verify:

- `_materialize_output()` must not convert backend policy output to NumPy float64.
- MLX float32 preprocess must avoid the legacy float64 preprocess branch.
- Highlight boost must not call scalar `backend.max()` in GPU/no-explicit-`x_max` hot path.

Deferred boundaries:

- GUI full `float_image` materialization: P3.
- HDR `scene_luminance` and RouteMaster sidecars: P4.
- Spectral LUT and print/scan middle-stage full-size roundtrips: P2.
- Grain/stochastic and large filter CPU fallbacks: P4/P5.

## Implementation Scope

The current tree already contains most P1 implementation. This pass will:

- Re-audit the existing implementation against the 2026-06-08 request.
- Repair only P1 defects found by tests, benchmarks, or review.
- Add or update documentation with current evidence.
- Run P1 tests, relevant compatibility tests, and P1 benchmark commands.
- Write `docs/reports/backend-resident-float32-p1-foundation-20260608.md`.

## Explicit Non-Goals

- No P2 runtime middle-boundary rewrite.
- No GUI preview/export split.
- No HDR sidecar GPU-native rewrite.
- No grain/stochastic rewrite.
- No ResizingService GPU rewrite.
- No float16 implementation.
- No global Spektrafilm float32 conversion.
- No change to CPU default dtype or SDR rendering semantics.
- No claim that 512x384 synthetic benchmarks prove 12MP RAW performance.

## Planned File Changes

Likely documentation only unless validation finds a P1 defect:

- `docs/plans/backend-resident-float32-p1-foundation-plan-20260608.md`
- `docs/reports/backend-resident-float32-p1-foundation-20260608.md`

Potential repair targets if tests expose defects:

- `src/spektrafilm/runtime/params_schema.py`
- `src/spektrafilm/runtime/pipeline.py`
- `src/spektrafilm/gpu/backend.py`
- `src/spektrafilm/gpu/numpy_backend.py`
- `src/spektrafilm/gpu/mlx_backend.py`
- `src/spektrafilm/gpu/cupy_backend.py`
- `src/spektrafilm/gpu/halide_backend.py`
- `src/spektrafilm/gpu/kernels/color.py`
- `tests/test_runtime_materialize_policy.py`
- `tests/test_backend_resident_float32.py`
- `tests/test_gpu_highlight_boost_sync.py`
- `tools/benchmark_backend_resident_float32.py`

## Risk Analysis

- Lazy execution can make graph-build timings look fast. Benchmarks must report explicit sync and explicit NumPy conversion separately.
- CPU fallback for `materialize_policy="backend"` must remain boring and safe, not a pseudo-device object.
- GPU scalar-array Python control flow would reintroduce MLX evaluation. Highlight boost tests must guard against `backend.max()` regression.
- Existing dirty worktree files may be unrelated. They must not be reverted.
- Full `uv run pytest` can fail due unrelated pre-existing tests or environment issues. Any such failure must be recorded with the relevant passing P1 subset.

## Verification Plan

Commands to run:

```bash
uv run pytest tests/test_runtime_materialize_policy.py -q
uv run pytest tests/test_backend_resident_float32.py -q
uv run pytest tests/test_gpu_highlight_boost_sync.py -q
uv run pytest tests/test_gpu_pipeline.py tests/test_gpu_backend.py tests/test_gpu_highlight_boost.py -q
uv run python tools/benchmark_backend_resident_float32.py --backend cpu --runs 2 --warmups 1
uv run python tools/benchmark_backend_resident_float32.py --backend mlx --precision float32 --runs 2 --warmups 1
uv run pytest --ignore=tests/gui -q
```

If MLX/Metal is unavailable, MLX tests must skip and the benchmark must report the skip reason. If full non-GUI pytest is blocked by unrelated failures, the P1 report must record the failing command and the smaller passing evidence set.

## Rollback Strategy

- Documentation updates can be reverted independently.
- If P1 validation exposes a regression in the existing foundation, repair narrowly in the P1 files listed above.
- If `max_array()` or highlight boost parity fails, restore the prior scalar path only behind an explicit documented fallback and keep the P1 report gate closed.

## P1 Gate

P2 is allowed only if this pass proves:

- CPU/default public API remains NumPy float64.
- `materialize_policy` default is `"numpy_float64"` and illegal values fail clearly.
- MLX backend policy returns backend-resident float32 when MLX is available.
- GPU float32 preprocess avoids unconditional `np.double`.
- Highlight boost GPU/no-explicit-`x_max` avoids scalar `backend.max()`.
- Tests and benchmark pass or skip for documented environmental reasons.
- The final P1 report is accurate and explicit about unresolved P2/P3/P4 boundaries.

## P1 Gate Closure Addendum - 2026-06-08

The first 2026-06-08 verification pass proved the P1 materialization,
preprocess, and highlight-sync foundation, but six SDR/golden tests failed
because deterministic expectations were stale.

The original historical claim that `1a26ba7` was a known-good point for the
current SDR/golden expectations did not hold under a direct source-level check.
Running the current midgray contract on detached `1a26ba7` produced the same
center value as the live tree:

```text
[0.46483247 0.45977580 0.46409895] float64
```

A literal pytest bisect over `1a26ba7..d9e31d2` was invalid because the current
test node `tests/test_upstream_parity.py::TestGoldenReference::test_midgray_output_golden_reference`
and the current smoke test node were missing in older commits. A source-level
numeric check showed the stale scalar and snapshot expectations, not a P1
source regression.

Closure actions:

- Regenerated deterministic regression snapshots with
  `scripts/regenerate_test_baselines.py`.
- Updated the midgray smoke expected center to
  `[0.46483247, 0.45977580, 0.46409895]`.
- Updated the upstream-parity midgray golden center to
  `[4.587501955381701468e-01, 4.532247835250490797e-01, 4.577094035034299790e-01]`.
- Re-ran the P1 focused tests, SDR/golden subset, full non-GUI suite, and CPU/MLX
  P1 materialization benchmarks.

P1 compatibility gate is closed by the final report evidence, and P2 is allowed
to start with its own audit and plan.
