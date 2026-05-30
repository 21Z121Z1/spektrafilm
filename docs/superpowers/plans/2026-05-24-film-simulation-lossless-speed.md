# Film Simulation Lossless Speed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Speed up SpektraFilm simulation without reducing image quality, changing algorithms, or loosening numerical precision expectations.

**Architecture:** Keep the current CPU reference and backend abstraction intact. Prefer optimizations that remove redundant synchronization, data conversion, allocation, and repeated constant preparation while preserving the same operations and output tolerances. GPU changes must keep arrays resident and lazy until the pipeline boundary that already materializes the final NumPy output.

**Tech Stack:** Python 3.13, NumPy, SciPy/Numba CPU references, MLX/Metal and optional CuPy backend paths, pytest.

---

## Current Project Findings

- Runtime entry points are `spektrafilm.runtime.process.Simulator` and `spektrafilm.runtime.pipeline.SimulationPipeline`.
- The main deterministic pipeline is `preprocess -> film expose/develop -> print expose/develop -> scan`.
- CPU remains the precision reference. GPU support is routed through `src/spektrafilm/gpu/backend.py` and backend-portable kernels under `src/spektrafilm/gpu/kernels/`.
  - *(Note 2026-05-25: The pipeline now separates unlifted SDR and lifted HDR renditions for CoreImage encoding. Profiling and speed benchmarks should account for this dual rendition step.)*
- Baseline targeted verification before implementation:
  - `.venv/bin/python -m pytest tests/test_gpu_backend.py tests/test_gpu_lut.py tests/test_gpu_density.py tests/test_gpu_filters.py tests/test_runtime_api.py -q`
  - Result: `43 passed, 5 skipped`.
- Baseline warm 512x512 deterministic benchmark with LUT enabled and `compute_backend="auto"` selected MLX on this machine:
  - CPU warm run: about `131 ms`.
  - MLX warm run: about `39 ms` with auto exposure enabled.
  - MLX warm run: about `23 ms` with auto exposure disabled and LUT enabled.
- Profiling shows the current GPU LUT path calls `gpu_backend.eval(output)` inside `compute_with_lut`. This forces synchronization inside `spectral_compute_enlarger` and `spectral_compute_scanner`, preventing MLX from scheduling the pipeline lazily and making the LUT stages dominate wall time.
- A runtime experiment that only suppressed backend `eval` calls kept the final output sum identical for the tested image and reduced repeated warm 512x512 LUT-enabled runs from about `37-41 ms` to about `20-21 ms`. The production fix must be narrower than that experiment: remove only the unnecessary LUT-internal sync, leaving final output synchronization intact.
- Existing GPU trilinear LUT sampling is already the current behavior when `use_enlarger_lut` / `use_scanner_lut` are enabled on GPU. This plan does not introduce any new approximation or lower interpolation quality.

## Non-Goals

- Do not change film, print, scan, halation, diffusion, grain, glare, color management, or LUT interpolation math.
- Do not make LUT resolution smaller, switch precision downward, skip corrections, or disable visual effects.
- Do not force GPU for stochastic grain/glare. Those paths remain intentional CPU boundaries unless a separate deterministic RNG design is added later.
- Do not rewrite the pipeline or GUI controls.

## Implementation Tasks

### Task 1: Add A Regression Test For Lazy GPU LUT Sampling

**Files:**
- Modify: `tests/test_gpu_lut.py`

- [ ] Add a unit test using a fake GPU backend where `eval()` raises an assertion.
- [ ] Monkeypatch `spektrafilm.gpu.kernels.lut.apply_lut_trilinear_3d_backend` so the test does not need real MLX/CuPy.
- [ ] Call `compute_with_lut(..., method="gpu_trilinear", gpu_backend=fake_backend)`.
- [ ] Assert the function returns the expected output and does not call `gpu_backend.eval`.
- [ ] Run the test before production changes and confirm it fails because current code calls `eval`.

### Task 2: Remove The Unnecessary LUT-Internal GPU Synchronization

**Files:**
- Modify: `src/spektrafilm/utils/lut.py`

- [ ] In `compute_with_lut`, remove the `gpu_backend.eval(output)` call from the `method == "gpu_trilinear"` branch.
- [ ] Keep final pipeline materialization unchanged; `SimulationPipeline.process` still returns a NumPy array and the serial MLX runtime still synchronizes after processing.
- [ ] Run the new regression test and the existing GPU LUT tests.

### Task 3: Cache GPU LUT Prepared State Without Changing Output

**Files:**
- Modify: `src/spektrafilm/utils/lut.py`
- Modify: `tests/test_gpu_lut.py`
- No change required: `src/spektrafilm/runtime/services/spectral_lut_compute.py` already stores and reuses non-`None` prepared values returned by `compute_with_lut`.

- [ ] Extend `compute_with_lut(..., return_prepared=True, method="gpu_trilinear")` so it can return a prepared tuple that stores backend-ready LUT and normalized bounds.
- [ ] Reuse the prepared tuple on later calls instead of rebuilding backend arrays for the same cached LUT.
- [ ] Keep the CPU `pchip` prepared data path unchanged.
- [ ] Preserve fallback behavior when no GPU backend is provided.
- [ ] Add or update tests to verify the prepared object is reused and output stays identical.

### Task 4: Re-Measure And Audit Exactness

**Files:**
- Existing benchmark/test commands only unless failures expose a root cause.

- [ ] Run:

```bash
.venv/bin/python -m pytest tests/test_gpu_lut.py tests/test_gpu_backend.py tests/test_gpu_density.py tests/test_gpu_filters.py tests/test_runtime_api.py -q
```

- [ ] Run:

```bash
.venv/bin/python -m pytest -q
```

- [ ] Run:

```bash
.venv/bin/python -m compileall -q src/spektrafilm src/spektrafilm_gui tests
```

- [ ] Re-run the 512x512 deterministic benchmark used in analysis and compare repeated output stability for the same seeded image.
- [ ] Check the implementation against this confidence checklist:
  - [ ] No lower precision setting was introduced.
  - [ ] No film/print/scan math changed.
  - [ ] LUT interpolation method did not change.
  - [ ] GPU work is still synchronized at final materialization/runtime boundary.
  - [ ] Existing CPU fallback behavior is preserved.
  - [ ] New tests prove the removed sync would have been caught.

## Verification Results

- New RED test confirmed the old `compute_with_lut(..., method="gpu_trilinear")` path called `gpu_backend.eval(output)`.
- New GREEN tests:
  - `.venv/bin/python -m pytest tests/test_gpu_lut.py::test_compute_with_lut_gpu_trilinear_does_not_force_backend_eval -q`
  - `.venv/bin/python -m pytest tests/test_gpu_lut.py::test_compute_with_lut_gpu_trilinear_reuses_prepared_backend_arrays -q`
- Existing GPU LUT suite: `.venv/bin/python -m pytest tests/test_gpu_lut.py -q` -> `8 passed, 2 skipped`.
- Target suite: `.venv/bin/python -m pytest tests/test_gpu_lut.py tests/test_gpu_backend.py tests/test_gpu_density.py tests/test_gpu_filters.py tests/test_runtime_api.py -q` -> `47 passed, 5 skipped`.
- Full suite after resolving the current worktree HEIC sidecar compatibility failure: `.venv/bin/python -m pytest -q` -> `398 passed, 5 skipped, 6 warnings`.
- Compile check: `.venv/bin/python -m compileall -q src/spektrafilm src/spektrafilm_gui tests` -> exit `0`.
- 512x512 deterministic MLX/LUT benchmark with auto exposure disabled: backend `mlx`, warm best `0.024638s`, repeated output max absolute diff `0.0`.

If any checklist item cannot be proven with code and fresh command output, stop, identify the root cause, add the narrowest failing test, fix that specific issue, and repeat the verification loop.
