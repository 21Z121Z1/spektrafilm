# MLX Compile Element-Wise Chain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add guarded `mx.compile` acceleration for stable-shape MLX element-wise chains without changing CPU behavior, GPU precision policy, or pipeline semantics.

**Architecture:** Keep compilation inside the MLX backend and route only pure element-wise chains through a backend helper that caches compiled functions by operation name plus input shape/dtype. Do not use `shapeless=True`; this repo processes image tensors whose shape participates in downstream behavior, and the official MLX guidance says normal compilation recompiles on shape change while shapeless compilation is unsafe for shape-dependent graphs.

**Tech Stack:** Python 3.13, MLX `mx.compile`, NumPy, pytest, Spektrafilm GPU backend kernels, standalone benchmark script.

---

## Research Conclusions

- MLX `mx.compile()` is appropriate for pure tensor graphs because it can merge common work and fuse operations, reducing graph size, runtime, and memory pressure.
- A compiled MLX function traces and compiles on first call. Inputs with changed shapes recompile unless `shapeless=True`.
- This implementation must not use `shapeless=True`: Spektrafilm image processing frequently relies on explicit shape metadata, and the planned benchmark can keep shape/dtype fixed without weakening runtime safety.
- Debugging or materializing arrays inside compiled functions is invalid. Compiled functions in this pass must avoid `print`, `np.asarray`, `.item()`, `backend.max()`, `mx.eval()`, and `mx.synchronize()`.
- Timing must force evaluation with `mx.eval()` and `mx.synchronize()`; unsynchronized dispatch timing is not acceptable evidence.

## Current Workspace Findings

- Existing MLX residency work already removed confirmed CPU materialization points in filming LUT, printing spectral path, and LUT wrappers.
- `docs/dev/2026-05-31-mlx-backend-review.md` explicitly leaves `mx.compile` as future work because it needs stable input shape/dtype and a separate benchmark.
- Candidate pure element-wise chains:
  - `safe_log10(max(x, 0) + 1e-10)` in film, print, and scan spectral paths.
  - `density_to_light`: `10 ** (-density) * illuminant` followed by finite cleanup.
  - CCTF encode/decode transfer functions in `gpu/kernels/color.py`.
  - Highlight boost's per-pixel exponential curve after scalar `x_max` has been synchronized.
- Non-candidates:
  - MLX custom Metal kernels, LUT gather/interpolation, Gaussian IIR/FIR kernels, `einsum`, `matmul`, and any path that performs scalar reductions or backend-to-NumPy conversion.

## Task 1: MLX Compile Cache Helper

**Files:**
- Modify: `src/spektrafilm/gpu/mlx_backend.py`
- Test: `tests/test_gpu_backend.py`

- [ ] Add `MlxBackend.compiled_elementwise(name, function, *sample_args)` that returns `mx.compile(function)` when available.
- [ ] Key the cache by `name` and each MLX sample argument's `shape` and `dtype`, so same stable shape/dtype reuses the compiled callable and changed shape/dtype gets a separate callable.
- [ ] Avoid failing on older/fake MLX modules without `compile`; return the original function in that case.
- [ ] Add MLX-skipping tests that monkeypatch `backend.mx.compile` and prove same shape/dtype compiles once while changed shape compiles separately.

## Task 2: Compile Pure Element-Wise Chains

**Files:**
- Modify: `src/spektrafilm/gpu/kernels/color.py`
- Modify: `src/spektrafilm/gpu/kernels/density.py`
- Modify: `src/spektrafilm/runtime/stages/filming.py`
- Modify: `src/spektrafilm/runtime/stages/printing.py`

- [ ] Add a small local helper in kernel modules to call `backend.compiled_elementwise(...)` only when present.
- [ ] Route CCTF encode/decode transfer functions through compiled wrappers.
- [ ] Route highlight boost's per-pixel exponential curve through a compiled wrapper, passing scalar parameters as a fixed `(4,)` backend array so values can change without embedding them in a Python closure.
- [ ] Add `safe_log10_backend(values, backend)` in density kernels and use it in film, print, and scan final log clamps. Benchmark it before deciding whether it should use `mx.compile`; keep it uncompiled if measured speedup is negative.
- [ ] Route `density_to_light(...)` through a compiled wrapper when the backend supports it.
- [ ] Preserve exact CPU code paths and all existing GPU numerical tolerances.

## Task 3: Focused Regression Tests

**Files:**
- Modify: `tests/test_gpu_backend.py`
- Modify: `tests/test_gpu_color_chain.py`
- Modify: `tests/test_gpu_density.py`
- Modify: `tests/test_gpu_pipeline.py` only if stage residency needs extra coverage.

- [ ] Test compile-cache behavior with monkeypatched `mx.compile`.
- [ ] Test `safe_log10_backend` parity against NumPy.
- [ ] Test that MLX CCTF / density / pipeline tests still pass with compiled paths enabled.
- [ ] Keep tests skip-safe when MLX/Metal is unavailable.

## Task 4: Standalone Benchmark

**Files:**
- Create: `scripts/benchmark_mlx_compile_elementwise.py`
- Create artifacts under: `docs/dev/benchmark-artifacts/mlx_compile_elementwise_20260531/`

- [ ] Use deterministic NumPy RNG input and fixed default shape `(1024, 1024, 3)` with dtype `float32`.
- [ ] Warm up both uncompiled and compiled functions before timing.
- [ ] Time with `mx.eval(result)` and `mx.synchronize()` on every iteration.
- [ ] Benchmark at least:
  - safe log10 clamp
  - density-to-light finite cleanup
  - sRGB CCTF encode transfer
  - highlight boost element-wise curve
- [ ] Report best/median/mean milliseconds, speedup, shape, dtype, iteration count, and max absolute diff.
- [ ] Write JSON and Markdown artifacts.
- [ ] Remove any production compile use from chains that benchmark as slower.

## Task 5: Documentation Update

**Files:**
- Modify: `docs/dev/2026-05-31-mlx-backend-review.md`
- Create or modify: `docs/dev/2026-05-31-mlx-compile-elementwise.md`

- [ ] Document the actual implementation scope, official MLX constraints, benchmark command, and measured results.
- [ ] State that `mx.compile` is used only for pure element-wise chains and that shape/dtype-specific cache keys intentionally avoid shapeless compilation.
- [ ] List remaining non-compiled paths and why they are excluded.

## Task 6: Verification And Self-Audit

**Commands:**
- `.venv/bin/python -m pytest tests/test_gpu_backend.py tests/test_gpu_color_chain.py tests/test_gpu_density.py tests/test_gpu_pipeline.py -q`
- `.venv/bin/python scripts/benchmark_mlx_compile_elementwise.py --height 512 --width 512 --iterations 10`
- `.venv/bin/python -m compileall -q src/spektrafilm tests scripts`
- `git diff --check`

**Self-audit questions before completion:**
- Did any compiled function materialize arrays, synchronize, print, or branch on tensor values?
- Are compile cache keys tied to stable shape/dtype, with changed shape/dtype handled safely?
- Did speedup evidence include `mx.eval()` and `mx.synchronize()`?
- Did CPU behavior and explicit float64 policy stay unchanged?
- Did numerical parity remain within current MLX float32 tolerances?
- Did this pass avoid touching unrelated dirty-worktree changes?
