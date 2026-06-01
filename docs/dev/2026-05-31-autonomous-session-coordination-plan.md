# Autonomous Session Coordination Plan

**Date:** 2026-05-31
**Coordinator thread:** `019e792e-d732-71c1-b9bc-bc18b0c063ed`
**Workspace:** `/Users/retriedstormtrooper/Documents/spektrafilm-main`

## Goal

Coordinate the active `spektrafilm-main` work, avoid trampling concurrent GPU/MLX/Halide review work, and land only high-confidence fixes that can be proven with targeted tests and repository verification.

## Current Workspace Facts

- The checkout is `develop` and is not an isolated git worktree: `.git` and the git common directory are the same path.
- The working tree is already dirty with broad edits across GPU kernels, MLX/Halide backends, runtime stages, model code, GUI params, tests, benchmark scripts, and docs.
- Recent active Codex threads are working in the same repository on MLX/Halide review and adversarial review, so this coordinator thread must avoid large overlapping rewrites.
- A separate background worktree audit thread was requested from the current working tree with a read-only prompt.
- The strongest local convention for this repo remains: preserve SDR behavior unless an explicit opt-in path is being changed, and validate through `uv run --extra dev ...` or `.venv/bin/python` rather than plain `python3`.

## External Reference Checks

- [MLX lazy evaluation documentation](https://ml-explore.github.io/mlx/build/html/usage/lazy_evaluation.html) confirms operations are lazy and computation occurs when `eval()` is performed; this supports requiring synchronized timing in MLX benchmarks and not trusting unsynchronized timings.
- [MLX unified memory documentation](https://ml-explore.github.io/mlx/build/html/usage/unified_memory.html) confirms arrays live in unified memory and operations choose the execution device at operation time; this supports minimizing avoidable CPU/MLX conversion churn but does not remove the need to force evaluation for validation.
- [Halide namespace documentation](https://halide-lang.org/docs/namespace_halide.html) describes `fast_pow` as an approximate Float32 operation; replacing it with `pow` in precision-sensitive color transfer functions is consistent with the repo's parity-oriented tests.

## Confirmed High-Value Gap For This Coordinator Pass

`src/spektrafilm/model/grain.py` still allows the direct public helper `apply_grain_to_density(..., n_sub_layers=0)` to produce NaN through division by zero. A new test currently documents this broken behavior as expected. That is the wrong contract: invalid grain layer counts should fail early with a clear `ValueError`, matching the new `GrainParams.__post_init__` validation.

## Implementation Scope

1. Replace the regression test that expects NaN for `n_sub_layers=0` with tests that require clear `ValueError` failures for zero and negative values.
2. Add a minimal guard at the top of `apply_grain_to_density()` so direct callers receive the same clear contract as `GrainParams`.
3. Run targeted tests for grain and photo-param validation.
4. Run lightweight repository checks that do not mask active concurrent work: `git diff --check` and `compileall`.
5. If targeted verification exposes broader breakage, classify it as caused by this coordinator fix, pre-existing dirty work, missing local toolchain, or concurrent work.

## Execution Results

Coordinator-owned changes:

- `apply_grain_to_density()` now rejects `n_sub_layers < 1` with `ValueError` before it can divide by zero or produce NaN.
- `tests/test_grain.py` now asserts the public helper rejects zero and negative sub-layer counts.
- `scripts/benchmark_halide_mlx_parity.py` was added to satisfy the existing Halide/MLX benchmark helper tests that were present in the working tree.

Validated current workspace behavior from concurrent GPU/profile/filter work:

- Filter loading now converts Akima out-of-range NaN/inf values to `0.0`.
- Profile loading/saving now rejects unsafe stock names before resource lookup, and `ProfileData` performs shape and value validation during construction.
- MLX LUT paths avoid redundant `mx.array()` conversion when the caller supplies prepared MLX arrays.
- Halide fused CMY-to-log XYZ/raw paths match NumPy references for dynamic spectral lengths and clear NaN light values like the generic backend path.

Verification completed on the final observed workspace state:

- `.venv/bin/python -m pytest tests/test_grain.py::TestApplyGrain::test_apply_grain_to_density_rejects_invalid_sub_layers -q` -> `2 passed`.
- `.venv/bin/python -m pytest tests/test_grain.py -q` -> `12 passed`.
- `.venv/bin/python -m pytest tests/test_photo_params.py::TestRuntimePhotoParamsValidation -q` -> `6 passed`.
- `.venv/bin/python -m pytest tests/test_edge_cases.py tests/test_profiles.py -q` -> `66 passed`.
- `.venv/bin/python -m pytest tests/test_gpu_lut.py::test_compute_with_lut_gpu_trilinear_reuses_prepared_backend_arrays tests/test_gpu_lut.py::test_trilinear_3d_lut_mlx_prepared_arrays_avoid_mx_array_copy tests/test_gpu_lut.py::test_cubic_2d_lut_mlx_prepared_arrays_avoid_mx_array_copy -q` -> `3 passed`.
- `.venv/bin/python -m pytest tests/test_halide_spectral.py::test_fused_cmy_to_log_xyz_matches_numpy_for_hwc_runtime_shape tests/test_halide_spectral.py::test_fused_cmy_to_log_raw_matches_numpy_for_printing_chain 'tests/test_gpu_density.py::test_cmy_to_log_xyz_backend_matches_cpu_reference[halide]' -q` -> `3 passed`.
- `.venv/bin/python -m pytest tests/test_halide_spectral.py::test_fused_cmy_to_log_xyz_zeroes_nan_light_like_generic_backend tests/test_halide_spectral.py::test_fused_cmy_to_log_raw_zeroes_nan_light_like_generic_backend -q` -> `2 passed`.
- `.venv/bin/python -m compileall -q src tests scripts` -> passed.
- `git diff --check` -> passed.
- `.venv/bin/python -m pytest --ignore=tests/gui -q` -> `686 passed, 7 skipped, 1 warning`.

The remaining warning is the pre-existing `tests/test_autoexposure.py::test_legacy_autoexposure_methods_remain_finite_on_small_images[matrix]` divide-by-zero runtime warning in `src/spektrafilm/utils/autoexposure.py:121`; the test passes and it is not part of this coordinator fix.

## Non-Goals

- Do not rewrite the broader MLX/Halide optimization currently being handled by active threads.
- Do not revert or normalize existing dirty files unless they directly block this fix.
- Do not claim full repository release readiness while other active threads are still changing the same working tree.
- Do not commit unless the user explicitly asks for a commit.

## 100 Percent Confidence Loop

Before marking the goal complete, this loop was performed:

1. Re-read the changed test and implementation.
2. Ask whether invalid `n_sub_layers` can still reach a divide-by-zero path through direct CPU or MLX calls.
3. Run the targeted tests fresh and read the output.
4. Run `git diff --check` and `compileall` fresh.
5. Update this document or another current doc if the final state differs from this plan.
6. If any answer is not factually supported, patch or document the gap and repeat the relevant verification.

Final answer for this pass: invalid `n_sub_layers` is now blocked at the public helper boundary, the known targeted failures are green in the current workspace, and the non-GUI test suite is passing. The repository remains a dirty shared worktree with many unrelated active edits, so confidence applies to the current tested state, not to unreviewed concurrent diffs as a future release unit.
