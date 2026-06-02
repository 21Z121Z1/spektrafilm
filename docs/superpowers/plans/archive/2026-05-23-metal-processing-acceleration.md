# Metal Processing Acceleration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the Apple Silicon Metal acceleration path so `compute_backend="mlx"` keeps non-random full-resolution processing on MLX/Metal across spectral upsampling, density interpolation, Gaussian/FFT spatial effects, LUT sampling, color transforms, CCTF encode/decode, and large-image tiling, with no silent CPU fallback in the hot path except explicitly documented stochastic effects and small scalar/reference calculations.

**Architecture:** Keep the runtime backend abstraction as the boundary: `SimulationPipeline` chooses `MlxBackend`, stage code calls backend-portable kernels, and MLX-specific custom Metal kernels live in `src/spektrafilm/gpu/kernels/`. CPU remains the default fallback, but explicit `mlx` must either run the supported path on Metal or fail loudly for unsupported precision/features. Large images are split into synchronized tiles at the pipeline level to reduce per-dispatch pressure without disabling GPU acceleration.

**Tech Stack:** Python 3.13, NumPy, MLX 0.31+, MLX `mx.fast.metal_kernel`, SciPy/Numba CPU references, pytest.

---

## Current Project Findings

- `src/spektrafilm/gpu/backend.py` already routes `auto -> mlx -> cupy -> cpu`, and `MlxBackend.requires_serial_runtime = True` correctly forces the shared Metal lock in `src/spektrafilm/runtime/process.py`.
- `src/spektrafilm/runtime/pipeline.py` already rejects explicit GPU backends with `float_precision="float64"`, converts runtime inputs to `float32` by default, and tiles large GPU images using `SPEKTRAFILM_GPU_TILE_PIXELS` / legacy `SPEKTRAFILM_MLX_TILE_PIXELS`.
- Stage code already uses backend kernels for Hanatos spectral upsampling, density interpolation, print/scan spectral transforms, Gaussian blur, diffusion filters, CCTF transforms, and RGB/XYZ matrix transforms.
- Stochastic grain and print glare still force CPU materialization. That is acceptable for this goal because their random fields are not currently tile-safe or backend-portable. The pipeline disables GPU tiling when these effects are active rather than producing seam-prone random output.
- A remaining gap exists in the MLX Gaussian dispatcher: mixed per-channel sigmas where some channels are below 3 px and others are above 3 px currently fall back through `backend.to_numpy(...)`. Halation, diffusion, and unsharp workflows can naturally produce mixed channel sigmas, so this is a real CPU fallback in a Metal hot path.

## Scope

- Finish MLX/Metal acceleration coverage for deterministic processing paths.
- Preserve CPU numerical references and existing public runtime/GUI controls.
- Preserve `compute_backend="auto"`, `compute_backend="cpu"`, and strict explicit GPU backend behavior.
- Keep CuPy additions opportunistic but do not expand this goal into a CUDA feature beyond preserving existing dispatch.
- Do not attempt GPU grain/glare random field generation in this pass; document it as a deliberate future step.

## Task 1: Lock The Mixed-Sigma MLX Gaussian Gap With A Failing Test

**Files:**
- Modify: `tests/test_gpu_filters.py`

- [ ] **Step 1: Add a regression test that would fail on current code**

Add a test that:
- Requires real MLX with `select_backend("mlx")`.
- Monkeypatches `backend.to_numpy` to raise.
- Calls `gaussian_filter_backend(image, np.array([0.75, 3.25, 1.5]), backend)`.
- Evaluates the returned MLX array without using `backend.to_numpy`.
- Compares against `fast_gaussian_filter(image, sigma)` within the mixed-kernel tolerance.

- [ ] **Step 2: Verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_gpu_filters.py::test_gaussian_filter_mixed_sigma_mlx_stays_on_device_when_available -q
```

Expected on current code: FAIL with the monkeypatched `to_numpy` assertion, proving the test catches the fallback.

## Task 2: Implement Mixed-Sigma MLX Gaussian Dispatch

**Files:**
- Modify: `src/spektrafilm/gpu/kernels/filters.py`

- [ ] **Step 1: Add an MLX-only mixed dispatcher**

Implement a small helper that promotes 2D/3D input, loops over channels, sends each channel to `gaussian_filter_small_backend` or `gaussian_filter_large_backend` based on its own sigma, and stacks the channel results with `backend.mx.stack(..., axis=-1)`.

- [ ] **Step 2: Route mixed sigmas through the helper**

In `gaussian_filter_backend`, replace the current MLX mixed-sigma CPU fallback with the helper. Keep all-small and all-large paths unchanged.

- [ ] **Step 3: Verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_gpu_filters.py::test_gaussian_filter_mixed_sigma_mlx_stays_on_device_when_available -q
```

Expected: PASS, with the returned result matching the CPU reference and no full-image `to_numpy` call during filtering.

## Task 3: Regression Suite For Metal Coverage

**Files:**
- Existing tests only unless failures expose a real gap.

- [ ] **Step 1: Run GPU kernel and runtime tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_gpu_backend.py tests/test_gpu_lut.py tests/test_gpu_density.py tests/test_gpu_filters.py tests/test_gpu_color_chain.py tests/test_gpu_pipeline.py tests/test_runtime_api.py -q
```

Expected: all available tests pass; unavailable CuPy tests may skip.

- [ ] **Step 2: Run full test suite**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected: all tests pass or any failure has a root-cause note and targeted fix.

- [ ] **Step 3: Compile-check runtime modules**

Run:

```bash
.venv/bin/python -m compileall -q src/spektrafilm src/spektrafilm_gui tests
```

Expected: exit 0.

## Task 4: Confidence Audit Loop

Before declaring completion, repeat this checklist until every item is supported by code and fresh command output:

- [ ] Explicit `compute_backend="mlx"` initializes MLX/Metal and rejects unsupported runtime precision.
- [ ] Main deterministic scan/print route preserves MLX arrays through Hanatos spectral upsampling, density interpolation, print exposure, scan conversion, CCTF, Gaussian blur, and LUT sampling.
- [ ] Mixed Gaussian sigmas do not silently materialize the full image on CPU.
- [ ] Large-image GPU tiling still keeps GPU backend processing active, records tile timings, synchronizes per tile, and keeps stochastic effects out of tile mode.
- [ ] Known CPU boundaries are intentional: final output materialization, LUT table construction/test samples, scalar/reference corrections, grain, and print glare.
- [ ] README and GUI controls describe the supported backend choices accurately.

If a checklist item cannot be proven, add or update the narrowest test first, verify it fails for the gap, then patch the code and rerun the relevant suite.
