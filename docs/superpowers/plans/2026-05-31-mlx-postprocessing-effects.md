# MLX Postprocessing Effects Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Spektrafilm postprocessing effects (halation, camera/enlarger diffusion, Gaussian blur, and grain) use the MLX backend without avoidable full-frame CPU materialization, while preserving CPU behavior and documenting the support envelope.

**Architecture:** Keep the existing `ArrayBackend` boundary. Deterministic spatial effects use backend-aware Gaussian, exponential, reflect-padding, and FFT-convolution kernels; stochastic grain uses MLX random primitives and returns MLX arrays, with statistical rather than pixel-identical parity. CPU remains the reference path, `compute_backend="mlx"` remains strict, and final pipeline output materialization remains the only unavoidable large MLX-to-NumPy transfer.

**Tech Stack:** Python 3.13, NumPy, SciPy, MLX 0.31.2, pytest, Spektrafilm runtime stages and model postprocessing modules.

---

## Current Findings

- The current worktree already contains an MLX backend, MLX availability probe, `float64` CPU fallback for `auto`, cached MLX custom Metal kernels for Gaussian FIR/IIR, MLX FFT convolution, backend-aware density/color/LUT kernels, and runtime stage plumbing.
- MLX is locally usable in this workspace: `.venv/bin/python` imports MLX 0.31.2, `mx.metal.is_available()` is `True`, and a tiny `mx.eval()` probe succeeds.
- Official MLX guidance supports this direction: MLX records lazy graphs until `eval()`; Apple Silicon arrays live in unified memory; MLX supports `fft2`/`ifft2`, random primitives, and custom Metal kernels; and `float64` arrays are CPU-only on GPU operations.
- Halation is feasible and already mostly wired: `FilmingStage.expose()` passes `backend` into `apply_halation_um()`, which dispatches scatter core to `gaussian_filter_backend()`, scatter tail to `exponential_filter_backend()`, and multi-bounce halation to `gaussian_filter_backend()`. The initial RED test found one real gap: `exponential_filter_backend()` requested MLX float64 for the scatter tail and therefore fell back to CPU.
- Diffusion is feasible and already mostly wired: camera and enlarger diffusion both pass `backend` into `apply_diffusion_filter_um()`, which uses MLX reflect padding and MLX FFT convolution when the backend supports GPU.
- Grain is partially feasible. The code already has `gpu/kernels/grain.py` and MLX implementations for Poisson, lognormal, and normal-approximation binomial grain, but `_layer_particle_model_gpu()` still evaluates and transfers the full `seeds` array to NumPy only to compute `max_n`. That is the concrete bug for this pass.
- Grain cannot be judged by pixel-exact CPU parity because the CPU and MLX random streams differ. Acceptance must be: output stays on MLX, is finite, deterministic for the same seed, and has plausible mean/variance bounds.

## Scope

- Add direct model-level MLX tests for halation and diffusion staying on backend arrays.
- Add a failing grain regression that monkeypatches `backend.to_numpy` and proves the current grain GPU path performs an avoidable full-frame transfer.
- Remove the grain GPU `to_numpy(seeds).max()` barrier and keep the normal-approximation binomial path entirely on MLX.
- Add deterministic/statistical smoke coverage for MLX grain.
- Update docs with the support matrix and remaining precision/statistical caveats.

## Out Of Scope

- Do not rewrite grain into a CPU bit-exact stateless RNG.
- Do not introduce `mx.compile` yet; current gaps are data residency and test coverage, not proven graph-fusion bottlenecks.
- Do not change default CPU behavior, SDR/HDR export routing, GUI defaults, profile data, or baseline images.
- Do not claim full large-image performance results without running synced benchmarks.

## Task 1: Lock Spatial Postprocessing Backend Residency

**Files:**
- Modify: `tests/test_gpu_filters.py`

- [x] **Step 1: Add MLX halation and diffusion tests**

Add tests that require real MLX and monkeypatch `backend.to_numpy` to fail. The tests call:

```python
apply_halation_um(backend.asarray(image), HalationParams(...), pixel_size_um=5.0, backend=backend)
apply_diffusion_filter_um(backend.asarray(image), DiffusionFilterParams(...), pixel_size_um=100.0, backend=backend)
```

They assert the result is an MLX array, can be evaluated with `backend.eval()`, and is finite after explicit `np.asarray(result)`.

- [x] **Step 2: Run spatial tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_gpu_filters.py::test_halation_mlx_stays_on_device_when_available tests/test_gpu_filters.py::test_diffusion_filter_mlx_stays_on_device_when_available -q
```

Expected: pass on the current implementation. These tests lock already implemented behavior before changing grain.

## Task 2: Prove Grain Has An Avoidable MLX-to-NumPy Transfer

**Files:**
- Modify: `tests/test_grain.py`

- [x] **Step 1: Add failing grain residency test**

Add a test that:

```python
backend = select_backend("mlx")
density = backend.asarray(np.full((8, 8, 3), 0.35, dtype=np.float32))
monkeypatch.setattr(backend, "to_numpy", fail_to_numpy)
result = apply_grain_to_density(
    density,
    pixel_size_um=5.0,
    grain_blur=0.0,
    fixed_seed=42,
    backend=backend,
)
assert backend._is_mlx_array(result)
```

- [x] **Step 2: Verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_grain.py::TestApplyGrain::test_apply_grain_to_density_mlx_does_not_materialize_when_available -q
```

Expected before implementation: fail with `AssertionError("unexpected MLX to NumPy transfer")`.

## Task 3: Keep Halation And Grain Sampling On MLX

**Files:**
- Modify: `src/spektrafilm/gpu/kernels/filters.py`
- Modify: `src/spektrafilm/model/grain.py`

- [x] **Step 1: Keep MLX exponential filtering in float32 by default**

In `exponential_filter_backend()`, keep the default precision as `"float32"` so MLX Gaussian-mixture exponential filters stay on device. Leave an explicit private `_precision="float64"` escape hatch for reference-only callers, but do not use it automatically in normal MLX postprocessing.

- [x] **Step 2: Remove the full-frame `to_numpy(seeds).max()` barrier**

In `_layer_particle_model_gpu()`, delete the eager `backend.eval(seeds)` / `backend.to_numpy(seeds).max()` branch and always compute the vectorized normal-approximation binomial sample:

```python
seeds_f = seeds.astype(mx.float32)
binom_mean = seeds_f * probability_of_development
binom_var = binom_mean * (1.0 - probability_of_development)
binom_std = mx.sqrt(mx.maximum(binom_var, mx.array(1e-8, dtype=mx.float32)))
...
grain = binom_result.astype(mx.float32) * mx.array(od_particle, dtype=mx.float32) * saturation
```

This remains correct for all-zero `seeds` because mean and variance are zero and the final clamp keeps samples in `[0, seeds]`.

- [x] **Step 3: Verify GREEN**

Run the halation/diffusion and grain residency tests. Expected: pass.

## Task 4: Add Grain Determinism And Plausibility Coverage

**Files:**
- Modify: `tests/test_grain.py`

- [x] **Step 1: Add seed determinism test**

Call `apply_grain_to_density()` twice with the same MLX backend, same fixed seed, `grain_blur=0.0`, and the same density input. Assert `np.testing.assert_allclose()` on the evaluated outputs.

- [x] **Step 2: Add statistical smoke test**

Use a 64x64 constant-density input and assert the MLX output is finite, has matching shape, and its per-channel means stay within a practical envelope around the input density, for example absolute mean error below `0.25`. This is not CPU parity; it catches broken sampling, NaNs, and gross scale errors.

- [x] **Step 3: Run grain tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_grain.py -q
```

Expected: pass.

## Task 5: Documentation

**Files:**
- Create: `docs/dev/2026-05-31-mlx-postprocessing-effects.md`
- Modify: `README.md`

- [x] **Step 1: Write postprocessing support note**

Document:

- Halation: supported on MLX through highlight boost, Gaussian, and exponential Gaussian-mixture passes.
- Diffusion: supported on MLX through reflect padding plus MLX FFT convolution; PSF construction remains CPU-side because it is small and parameter-only.
- Grain: supported as MLX statistical grain, deterministic by seed on MLX but not pixel-identical to CPU RNG.
- Precision: MLX GPU path is float32/float16 only; CPU remains the float64 reference.
- Timing: MLX lazy evaluation means benchmark commands must synchronize or include final materialization.
- Known boundaries: final output materialization, color-reference scalar/tiny arrays, LUT construction/test probes, and any non-MLX backend fallback.

- [x] **Step 2: Add README pointer**

Add a short pointer in the compute backend or performance section so users know the detailed support matrix lives in the new docs note.

## Task 6: Final Verification And Confidence Loop

**Files:**
- All touched files.

- [x] **Step 1: Run focused postprocessing suite**

```bash
.venv/bin/python -m pytest tests/test_gpu_filters.py tests/test_grain.py -q
```

- [x] **Step 2: Run GPU/runtime suite**

```bash
.venv/bin/python -m pytest tests/test_gpu_backend.py tests/test_gpu_lut.py tests/test_gpu_filters.py tests/test_gpu_density.py tests/test_gpu_color_chain.py tests/test_gpu_pipeline.py tests/test_gpu_primitives.py tests/test_grain.py -q
```

- [x] **Step 3: Run broader non-GUI suite**

```bash
.venv/bin/python -m pytest --ignore=tests/gui -q
```

- [x] **Step 4: Run compile and diff hygiene**

```bash
.venv/bin/python -m compileall -q src tests
git diff --check
```

- [x] **Step 5: 100% confidence self-audit**

Before marking complete, verify every claim against fresh evidence:

- Halation and diffusion model-level tests exercise real MLX and forbid backend `to_numpy`.
- Grain residency test fails before the grain fix and passes after it.
- Grain deterministic/statistical tests pass.
- Existing GPU suites still pass.
- Docs state float32/statistical/lazy-eval caveats and do not overclaim pixel-perfect grain parity.
- Any remaining failure is either fixed or explicitly reported with command output.

## Completion Note

Implementation completed on 2026-05-31. The confidence audit found one extra grain boundary beyond the original plan: `layer_particle_model(..., method="gamma_beta", backend=mlx)` could silently enter the MLX helper even though only `poisson_binomial` is accelerated. The final implementation validates method names, keeps `poisson_binomial` on MLX, and falls `gamma_beta` back to the CPU reference path when a backend is supplied. This is covered by `test_layer_particle_model_mlx_falls_back_for_gamma_beta` and `test_layer_particle_model_rejects_unknown_method`.

Final verification:

```bash
.venv/bin/python -m pytest tests/test_gpu_filters.py tests/test_grain.py -q
# 32 passed, 1 skipped

.venv/bin/python -m pytest tests/test_gpu_backend.py tests/test_gpu_lut.py tests/test_gpu_filters.py tests/test_gpu_density.py tests/test_gpu_color_chain.py tests/test_gpu_pipeline.py tests/test_gpu_primitives.py tests/test_grain.py -q
# 133 passed, 7 skipped

.venv/bin/python -m pytest --ignore=tests/gui -q
# 701 passed, 7 skipped, 1 warning

.venv/bin/python -m compileall -q src tests
# passed

git diff --check
# passed
```
