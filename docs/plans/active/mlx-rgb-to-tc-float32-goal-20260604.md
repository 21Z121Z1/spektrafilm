# MLX RGB To tc,b Float32 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the Hanatos2025 filming RGB -> XYZ -> xy -> tc,b hot path onto MLX float32 without enabling or promising float16.

**Architecture:** Keep the CPU `_rgb_to_tc_b()` implementation unchanged and add a narrowly gated MLX float32 helper beside it in `spectral_upsampling.py`. The helper reuses the existing transfer-only CCTF decode and RGB-to-XYZ matrix kernels, caches the small CAT16 RGB-to-XYZ matrix, and returns backend arrays that feed the existing cached 2D LUT backend path in `FilmingStage`.

**Tech Stack:** Python, NumPy, colour-science, MLX, SpektraFilm `ArrayBackend`, pytest, existing GPU validation.

---

## Current Bottleneck

`src/spektrafilm/runtime/stages/filming.py` currently enters the GPU Hanatos2025 path only after calling CPU `_rgb_to_tc_b()` on the full image. That CPU function calls `colour.RGB_to_XYZ()`, computes `b`, divides to `xy`, maps through `_tri2quad()`, then copies both large arrays to the backend before calling `apply_lut_cubic_2d_backend()`. On high-resolution images this defeats MLX residency for the first expensive step.

The existing GPU color kernel layer already provides:

- `precompute_rgb_to_xyz_matrix(color_space, illuminant_xy=..., cat=...)`.
- `cctf_decoding_transfer_backend()` for transfer decode only.
- `rgb_to_xyz()` for backend matrix multiplication.

Those are enough for a focused MLX implementation. I will not add generic `stack` or `sum` to `ArrayBackend` unless a test proves it is necessary.

## Files

- Modify: `src/spektrafilm/utils/spectral_upsampling.py`
  - Add `_rgb_to_tc_b_backend_available()`.
  - Add cached CAT16 matrix helper.
  - Add MLX-only `_tri2quad_backend()`.
  - Add MLX float32-only `_rgb_to_tc_b_backend()`.
- Modify: `src/spektrafilm/runtime/stages/filming.py`
  - Import the backend helper.
  - Use it only for Hanatos2025 + GPU + MLX + float32.
  - Preserve existing CPU fallback for fp16, CuPy, Halide, CPU, and `use_backend=False`.
- Modify: `src/spektrafilm/gpu/kernels/color.py`
  - Keep `rgb_to_tc_b_backend()` as a compatibility wrapper that delegates to the single gated spectral helper.
- Modify: `tests/test_spectral_upsampling.py`
  - Add backend parity tests for `_tri2quad_backend()` and `_rgb_to_tc_b_backend()`.
  - Add matrix cache and data-flow tests.
- Modify: `tests/test_filming_stage.py`
  - Add Hanatos2025 filming path tests proving MLX float32 uses the backend helper and fp16/non-MLX fall back to CPU `_rgb_to_tc_b()`.
- Modify: `tests/test_gpu_color_chain.py`
  - Keep the color-kernel compatibility wrapper covered without allowing a second implementation.
- Modify: `tests/test_gpu_pipeline.py`
  - Add or update an MLX float32 Hanatos2025 `gpu_validate` test that records pipeline diff metrics when MLX is available.
- Modify: `tests/test_spectral_lut_service.py`
  - Refresh a stale cached-LUT fixture exposed by the broader spectral test sweep.
- Update: this plan document with final validation data and residual risk.

## Implementation Tasks

### Task 1: Baseline Tests For Helper API

- [x] Add `_tri2quad_backend()` parity tests with a recording NumPy-backed MLX-like backend.
- [x] Inputs include normal xy, near-zero, boundary, and OOG coordinates.
- [x] Verified RED failure because `_tri2quad_backend` did not exist.
- [x] Add `_rgb_to_tc_b_backend()` parity tests for `sRGB`, `Display P3`, and `ITU-R BT.2020`, with `apply_cctf_decoding=True/False`.
- [x] Test inputs include black, near-black, mid gray, RGB primaries, saturated colors, HDR-like values above 1, and small OOG negative values.
- [x] Verified RED failure because `_rgb_to_tc_b_backend` did not exist.

### Task 2: Backend Helper Implementation

- [x] Implement `_rgb_to_tc_b_backend_available(backend)` returning true only when `backend.name == "mlx"`, `backend.supports_gpu is True`, and `backend.precision == "float32"`.
- [x] Implement `_tri2quad_backend(tc, backend)` using backend arrays and MLX-compatible slicing:
  - `tc = backend.asarray(tc, dtype=float32 when MLX dtype exists)`.
  - `tx = tc[..., 0]`; `ty = tc[..., 1]`.
  - `y = ty / backend.maximum(1.0 - tx, 1e-10)`.
  - `x = (1.0 - tx) * (1.0 - tx)`.
  - Clip `x` and `y` to `[0, 1]`.
  - Return a shape `[..., 2]` array without round-tripping to NumPy.
- [x] Implement a cached CAT16 matrix helper keyed by `(color_space, reference_illuminant, "CAT16")`.
- [x] Implement `_rgb_to_tc_b_backend()`:
  - Raise or return a clear fallback signal when `_rgb_to_tc_b_backend_available()` is false.
  - Convert only the input and the small cached matrix to MLX float32.
  - Apply `cctf_decoding_transfer_backend()` only when requested.
  - Apply `rgb_to_xyz()` with the CAT16 RGB-to-XYZ matrix.
  - Compute `b = xyz[..., 0] + xyz[..., 1] + xyz[..., 2]`.
  - Compute `xy = xyz[..., 0:2] / backend.maximum(b[..., None], 1e-10)`.
  - Compute `tc = _tri2quad_backend(xy, backend)`.
  - Apply `backend.nan_to_num(b)`.
  - Return `(tc, b)` backend arrays.

### Task 3: Filming Path Integration

- [x] Update `FilmingStage._rgb_to_film_raw()` to call `_rgb_to_tc_b_backend()` only for MLX float32.
- [x] Keep the existing CPU `_rgb_to_tc_b()` + backend LUT route for fp16, CuPy, Halide, and other GPU backends.
- [x] Keep `mallett2019` unchanged.
- [x] Keep `_simple_rgb_to_density_spectral(... use_backend=False)` unchanged.
- [x] Verify LUT service prepared backend LUT reuse remains unchanged.

### Task 4: Fallback And Residency Tests

- [x] Add a filming-stage test where MLX float32 backend helper is called and CPU `_rgb_to_tc_b()` is monkeypatched to fail.
- [x] Add a filming-stage test where MLX fp16 keeps using CPU `_rgb_to_tc_b()` and does not call the backend helper.
- [x] Add a non-MLX GPU fallback test with the same CPU path.
- [x] Add a backend helper test where `backend.to_numpy()` raises, proving `_rgb_to_tc_b_backend()` does not materialize the full image.

### Task 5: Pipeline Validation

- [x] Run targeted unit tests:
  - `uv run --extra dev pytest tests/test_spectral_upsampling.py -q`
  - `uv run --extra dev pytest tests/test_filming_stage.py -q`
- [x] Run existing GPU validation tests:
  - `uv run --extra dev pytest tests/test_gpu_validate.py -q`
- [x] MLX is available; ran:
  - `uv run --extra dev pytest tests/test_gpu_pipeline.py -q`
  - a direct `SimulationPipeline` probe with `compute_backend="mlx"`, `gpu_precision="float32"`, `gpu_validate=True`.
- [x] Record `tc` max/mean abs diff, `b` max/mean abs diff, and pipeline max/mean abs diff here.
- [x] Run broader targeted sweep:
  - `uv run --extra dev pytest tests -k "gpu or mlx or spectral or hanatos or rgb_to_tc" -q`
- [x] Run `git diff --check`.

## Precision Risk Register

- CAT16 equivalence: Use `precompute_rgb_to_xyz_matrix(..., cat="CAT16")` and compare `_rgb_to_tc_b_backend()` directly to CPU `_rgb_to_tc_b()`.
- CCTF duplicate/missing decode: Use `cctf_decoding_transfer_backend()` only; do not use `cctf_decoding_backend()` because it applies a same-space matrix step.
- Near-zero `b`: Match CPU denominator `fmax(b, 1e-10)` and `nan_to_num(b)`.
- NaN/inf: Match CPU `nan_to_num(b)` for `b`; leave `tc` semantics driven by `_tri2quad()` and backend arithmetic.
- OOG inputs: Do not clip xy before `_tri2quad_backend()`; only `_tri2quad_backend()` clips output coordinates, matching CPU.
- fp16: Never call backend helper unless precision is exactly float32.
- CPU/CuPy/Halide: Keep current fallback path.
- SDR/HDR export: This change stops at filming raw calculation; printing, scanning, preview CCTF, and save/export paths are out of scope and must remain untouched.

## Final Validation Results

### Commands

- RED: `uv run --extra dev pytest tests/test_spectral_upsampling.py::test_tri2quad_backend_matches_cpu_edge_cases tests/test_spectral_upsampling.py::test_rgb_to_tc_b_backend_matches_cpu_reference tests/test_spectral_upsampling.py::test_rgb_to_tc_b_backend_caches_cat16_matrix -q`
  - Result before implementation: 8 failed on missing `_tri2quad_backend`, `_rgb_to_tc_b_backend`, and matrix helper import.
- RED: `uv run --extra dev pytest tests/test_filming_stage.py::test_rgb_to_film_raw_mlx_float32_uses_backend_tc_path -q`
  - Result before implementation: failed on missing filming-stage backend helper import.
- GREEN: `uv run --extra dev pytest tests/test_spectral_upsampling.py tests/test_filming_stage.py tests/test_gpu_validate.py tests/test_gpu_pipeline.py tests/test_gpu_color_chain.py tests/test_spectral_lut_service.py -q`
  - Result: 81 passed, 2 skipped.
- GREEN: `uv run --extra dev pytest tests -k "gpu or mlx or spectral or hanatos or rgb_to_tc" --ignore=tests/test_fft_gaussian_filter.py -q`
  - Result: 209 passed, 7 skipped, 1311 deselected.
- HYGIENE: `git diff --check`
  - Result: passed.
- CAVEAT: `uv run --extra dev pytest tests -k "gpu or mlx or spectral or hanatos or rgb_to_tc" -q`
  - Result: collection failed before selected tests ran because `pyfftw` in `tests/test_fft_gaussian_filter.py` is blocked by macOS code-signing policy.

### Precision Metrics

Measured on real MLX float32 against CPU `_rgb_to_tc_b()` for the required color spaces and transfer modes:

| Case | tc max abs | tc mean abs | b max abs | b mean abs |
| --- | ---: | ---: | ---: | ---: |
| sRGB, decode=False | 7.820147e-08 | 2.471833e-08 | 1.719511e-07 | 4.050046e-08 |
| sRGB, decode=True | 1.258637e-07 | 2.419872e-08 | 3.671115e-07 | 9.976617e-08 |
| Display P3, decode=False | 1.127768e-07 | 3.404102e-08 | 9.868860e-08 | 3.543905e-08 |
| Display P3, decode=True | 1.127768e-07 | 2.858173e-08 | 4.842109e-07 | 1.273694e-07 |
| ITU-R BT.2020, decode=False | 1.096828e-07 | 3.068528e-08 | 1.209714e-07 | 4.575215e-08 |
| ITU-R BT.2020, decode=True | 2.834299e-07 | 3.609279e-08 | 4.708070e-07 | 8.678342e-08 |

Real MLX `SimulationPipeline` with `compute_backend="mlx"`, `gpu_precision="float32"`, `gpu_validate=True`:

- status: `ok`
- backend/reference: `mlx` / `cpu`
- tolerance: `1e-05`
- pipeline max_abs_diff: `1.4962645784582368e-06`
- pipeline mean_abs_diff: `3.1786747157587617e-07`
- finite: `true`

### Data-Flow Proof

- `tests/test_rgb_to_film_raw_mlx_float32_uses_backend_tc_path` monkeypatches CPU `_rgb_to_tc_b()` to raise; MLX float32 filming raw still succeeds through `_rgb_to_tc_b_backend()`.
- `tests/test_rgb_to_tc_b_backend_real_mlx_matches_cpu_without_materializing` monkeypatches `backend.to_numpy()` to raise during the helper call, asserts returned `tc` and `b` are MLX arrays, then materializes only after the helper returns for comparison.
- `tests/test_rgb_to_film_raw_mlx_float16_uses_existing_cpu_tc_path` proves fp16 does not enter the new path.
- `tests/test_rgb_to_film_raw_non_mlx_gpu_uses_existing_cpu_tc_path` proves non-MLX GPU backends do not enter the new path.

## 100% Confidence Self-Review

I am at practical 100% confidence for the scoped goal.

- CAT16 equivalence: covered by direct tc/b comparisons against CPU `_rgb_to_tc_b()` and by the real MLX metrics above.
- CCTF duplicate/missing decode: helper uses `cctf_decoding_transfer_backend()` only; tests cover `apply_cctf_decoding=True/False`.
- Near-zero `b`: black and near-black inputs are in the tc/b parity matrix; denominator uses fmax-style floor.
- NaN/inf: `b` uses backend `nan_to_num()` after matching CPU denominator behavior. No new clipping is introduced for xy.
- OOG input: parity tests include HDR-like values above 1 and small negative values; `_tri2quad_backend()` clips only final tc coordinates.
- fp16: filming test proves MLX fp16 stays on the old CPU `_rgb_to_tc_b()` path before backend LUT sampling.
- Backend residency: MLX helper test fails on any full-image `to_numpy()` inside the helper.
- CPU/CuPy/Halide paths: filming tests prove non-MLX GPU path uses existing CPU tc/b calculation and cached backend LUT sampling.
- CPU path: `use_backend=False` remains routed through `rgb_to_raw_hanatos2025()`; `_simple_rgb_to_density_spectral()` was not changed.
- mallett2019 path: untouched by implementation and covered by no edits to its branch.
- SDR/HDR/export semantics: no printing, scanning, preview CCTF, ACES, gain-map, or export files were changed.
- Duplicate-helper loophole: `spektrafilm.gpu.kernels.color.rgb_to_tc_b_backend()` is now a compatibility wrapper delegating to the single gated spectral helper, so there is not a second uncached implementation.
