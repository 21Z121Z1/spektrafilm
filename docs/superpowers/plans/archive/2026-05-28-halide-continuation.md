# Halide Continuation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Continue the Halide backend from `origin/develop@8615e6e` by fixing the live Python JIT CCTF defect, making the AOT generator CMake skeleton configure/build, and updating the implementation docs so they describe the actual verified state.

**Architecture:** Keep Halide as an explicit opt-in backend and keep NumPy/colour-science as the numerical reference. Python `HalideBackend` should only expose kernels whose parity is proven by focused tests; C++ generators should be buildable AOT foundations, not uncompiled prose. Android remains a future integration target, with host generator build used here as the local confidence gate.

**Tech Stack:** Python 3.13, pytest, NumPy, colour-science, optional `halide>=21,<22`, CMake 3.28+ through Halide v21 helper macros, AppleClang host build for generator syntax validation.

---

## Evidence And Current State

- Synced `develop` from local `defbb91` to GitHub `origin/develop@8615e6e`.
- Safety backup before fast-forward:
  - Git ref: `backup/develop-before-origin-8615e6e-20260528T131615`
  - Untracked snapshot: `/Users/retriedstormtrooper/Documents/spektrafilm-main-git-backups/develop-before-origin-8615e6e-20260528T131615`
- Local Halide is installed in `.venv`: Python 3.13.1, host target `arm-64-osx-arm_dot_prod-arm_fp16`, install dir `.venv/lib/python3.13/site-packages/halide`.
- Existing Halide test command:

```bash
.venv/bin/python -m pytest tests/test_halide_backend.py tests/test_halide_android.py tests/test_halide_color.py tests/test_halide_filters.py tests/test_halide_lut.py tests/test_halide_spectral.py -q
```

Current result after syncing `8615e6e`: `62 passed, 1 failed`. The failure is `tests/test_halide_color.py::TestCctfDecode::test_srgb_roundtrip`.

- Existing CMake configure probe:

```bash
cmake -S src/spektrafilm/generators -B /tmp/spektrafilm-halide-generators-build -DHalide_DIR="$PWD/.venv/lib/python3.13/site-packages/halide/lib/cmake/Halide"
```

Current result: fails with `Unable to locate FROM as either spectral_generator ...`, because `src/spektrafilm/generators/CMakeLists.txt` calls `add_halide_library(... FROM spectral_generator ...)` without first declaring `add_halide_generator(spectral_generator ...)`.

## Root Cause Analysis

1. The Python CCTF JIT helper uses a non-invertible encode formula:

```text
encode: x <= threshold ? a*x + b : pow(c*x + d, gamma)
decode: y <= threshold ? (y-b)/a : (pow(y, 1/gamma)-d)/c
```

With sRGB-like parameters this creates an overlapping discontinuity. Values just above linear threshold encode below the decode threshold, so decode takes the wrong branch. The C++ generator and `src/spektrafilm/gpu/kernels/color.py` already show the correct sRGB-style contract:

```text
encode: x <= linear_threshold ? linear_slope*x : alpha*pow(x, 1/gamma) - (alpha-1)
decode: y <= encoded_threshold ? y/linear_slope : pow((y + alpha - 1)/alpha, gamma)
encoded_threshold = linear_slope * linear_threshold
```

For the Python API's existing parameter names this maps to:

```text
a = linear_slope
b = linear offset, normally 0
c_coeff = alpha
d_coeff = alpha - 1
encode high branch = c_coeff * pow(linear, 1/gamma) - d_coeff
decode high branch = pow((encoded + d_coeff) / c_coeff, gamma)
decode threshold = a * threshold + b
```

2. The C++ AOT directory is tracked but unverified. It currently misses `add_halide_generator()` targets and likely needs C++ API cleanup before host generator build can prove the sources compile.

3. Documentation still describes only the early 3x3 matrix and 3D LUT pilot, while tracked code now contains spectral, filter, CCTF, interpolation, 2D LUT, and generator foundations. Docs must be updated after implementation so they do not overclaim full Android/JNI completion.

## Task 1: Strengthen CCTF Tests First

**Files:**
- Modify: `tests/test_halide_color.py`

- [ ] Replace the NumPy encode/decode reference with the sRGB-style formulas used by `src/spektrafilm/gpu/kernels/color.py` and `src/spektrafilm/generators/color_generator.cpp`.
- [ ] Add a focused regression vector around the old failing interval: linear values just above `0.0031308` must round-trip through Halide encode/decode within `1e-5`.
- [ ] Run:

```bash
.venv/bin/python -m pytest tests/test_halide_color.py::TestCctfDecode::test_srgb_roundtrip tests/test_halide_color.py::TestCctfDecode::test_srgb_transition_roundtrip -q
```

Expected before production fix: fail because `HalideBackend.cctf_encode()` and `HalideBackend.cctf_decode()` still use the old non-invertible branch formulas.

## Task 2: Fix Python Halide CCTF Formulas

**Files:**
- Modify: `src/spektrafilm/gpu/halide_backend.py`

- [ ] Change `_build_cctf_encode_pipeline()` to compute the high branch as `c_coeff * fast_pow(v, 1 / gamma) - d_coeff`, keeping the low branch `a * v + b`.
- [ ] Change `_build_cctf_decode_pipeline()` to use `encoded_threshold = a * threshold + b`, low branch `(v - b) / a`, and high branch `fast_pow((v + d_coeff) / c_coeff, gamma)`.
- [ ] Keep all parameters as `hl.Float(32)` and preserve the existing `[C,H,W]` buffer layout.
- [ ] Run:

```bash
.venv/bin/python -m pytest tests/test_halide_color.py -q
```

Expected after fix: all CCTF/interp/grain tests in that file pass.

## Task 3: Add AOT Generator Build Coverage

**Files:**
- Create: `tests/test_halide_generators.py`

- [ ] Add an integration test that imports `halide`, locates `halide.install_dir()/lib/cmake/Halide`, and skips if CMake or a C++ compiler is unavailable.
- [ ] In a pytest `tmp_path`, run CMake configure against `src/spektrafilm/generators`.
- [ ] Build the generator executable targets `spectral_generator`, `filter_generator`, `color_generator`, and `lut_generator`.
- [ ] Run:

```bash
.venv/bin/python -m pytest tests/test_halide_generators.py -q
```

Expected before CMake/source fix: fail at configure with the missing `FROM spectral_generator` generator target.

## Task 4: Fix CMake Generator Declarations

**Files:**
- Modify: `src/spektrafilm/generators/CMakeLists.txt`

- [ ] Raise `cmake_minimum_required()` to `3.28`, matching Halide v21 helper macros.
- [ ] Add:

```cmake
add_halide_generator(spectral_generator SOURCES spectral_generator.cpp)
add_halide_generator(filter_generator SOURCES filter_generator.cpp)
add_halide_generator(color_generator SOURCES color_generator.cpp)
add_halide_generator(lut_generator SOURCES lut_generator.cpp)
```

- [ ] Change each `add_halide_library(... GENERATOR ...)` argument to the registered generator names from `HALIDE_REGISTER_GENERATOR`, for example `GENERATOR density_to_light` rather than `GENERATOR DensityToLightGenerator`.
- [ ] Keep the `TARGET` override and aggregate `spektrafilm_halide_all` target.

## Task 5: Fix C++ Generator Build Errors And Obvious Contract Bugs

**Files:**
- Modify: `src/spektrafilm/generators/spectral_generator.cpp`
- Modify: `src/spektrafilm/generators/filter_generator.cpp`
- Modify: `src/spektrafilm/generators/color_generator.cpp`
- Modify: `src/spektrafilm/generators/lut_generator.cpp`

- [ ] Use a consistent Halide C++ namespace/import style so all generator files compile against Halide v21.
- [ ] Fix `DensityToLightGenerator` to use the wavelength coordinate, not `density(c, y, 0)`.
- [ ] Replace invalid `int W = image.dim(...).extent()` style with `Expr` where extents are symbolic.
- [ ] Remove or repair schedule code that tries to schedule fresh `Func("h_fwd")` objects instead of the actual Funcs.
- [ ] Keep generator comments conservative: host build verifies syntax and generator contracts only; Android AOT/JNI is not complete.
- [ ] Run:

```bash
.venv/bin/python -m pytest tests/test_halide_generators.py -q
```

Expected after fix: configure and generator executable build pass locally.

## Task 6: Documentation Update

**Files:**
- Modify: `docs/dev/halide-backend-implementation.md`
- Modify: `docs/dev/halide-android-port-plan.md`
- Modify: `README.md`

- [ ] Update the shipped kernel list to include the current Python JIT surface that is verified by tests: RGB matrix, 3D trilinear LUT, spectral helpers, FIR Gaussian, CCTF encode/decode, 1D interpolation, 2D cubic LUT, highlight boost, and NumPy-backed IIR/grain fallbacks.
- [ ] Add a note that C++ AOT generator sources now configure and compile as host generator executables, but Android NDK/JNI packaging remains future work.
- [ ] State the CCTF formula contract explicitly so future changes do not reintroduce the non-invertible branch bug.

## Task 7: Verification And Confidence Loop

- [ ] Run focused tests:

```bash
.venv/bin/python -m pytest tests/test_halide_backend.py tests/test_halide_android.py tests/test_halide_color.py tests/test_halide_filters.py tests/test_halide_lut.py tests/test_halide_spectral.py tests/test_halide_generators.py -q
```

- [ ] Run integration-adjacent GPU tests:

```bash
.venv/bin/python -m pytest tests/test_gpu_backend.py tests/test_gpu_color_chain.py tests/test_gpu_density.py tests/test_gpu_filters.py tests/test_gpu_highlight_boost.py tests/test_gpu_lut.py tests/test_runtime_api.py::TestRuntimeApi::test_float64_runtime_precision_rejects_explicit_gpu_backend -q
```

- [ ] Run non-GUI suite:

```bash
.venv/bin/python -m pytest --ignore=tests/gui -q
```

- [ ] Run syntax and whitespace gates:

```bash
.venv/bin/python -m compileall src/spektrafilm src/spektrafilm_gui tests -q
git diff --check
```

- [ ] Self-audit before declaring done:
  - Does explicit `compute_backend="halide"` ever silently fall back when Halide is missing? It must not.
  - Does `auto` silently pick Halide? It must not.
  - Does any float64 runtime path use Halide float32 kernels? It must not.
  - Does CCTF encode/decode round-trip through the transition region? It must.
  - Does CMake prove the generator executable sources compile? It must.
  - Do docs distinguish Python host JIT, C++ AOT source foundation, and unfinished Android/JNI packaging? They must.
