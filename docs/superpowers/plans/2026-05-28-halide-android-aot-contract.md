# Halide Android AOT Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the current Halide/Android foundation from prose and partial generator files into a verified AOT pre-JNI contract by fixing CCTF transfer semantics and making the Halide generator CMake project configure reliably.

**Architecture:** Keep Android work at the native-kernel contract layer, not a full APK or Kotlin UI rewrite. The Python Halide JIT backend remains the executable parity reference, while `src/spektrafilm/generators/` becomes a CMake-configurable AOT generator project that future JNI work can link against.

**Tech Stack:** Python 3.13, pytest, NumPy, Halide 21 Python wheel and bundled CMake package, C++17 Halide Generators, CMake.

---

## Evidence And Scope

Fresh workspace analysis on 2026-05-28 found:

- `tests/test_halide_android.py tests/test_halide_backend.py -q` passes: 17 tests.
- `tests/test_halide_color.py tests/test_halide_lut.py -q` fails in `TestCctfDecode.test_srgb_roundtrip`.
- The failing roundtrip is not random noise. The current Python Halide CCTF helper encodes with `pow(c*x+d, gamma)` and decodes using the linear-domain threshold as if it were encoded-domain threshold. For sRGB-like curves, the shipped backend-portable implementation in `gpu/kernels/color.py` uses `1.055 * signed_power(x, 1/2.4) - 0.055`, and decode must branch at the encoded threshold `12.92 * 0.0031308 = 0.04045`.
- `cmake -S src/spektrafilm/generators -B /tmp/spektrafilm-halide-generators-check -DHalide_DIR=.venv/lib/python3.13/site-packages/halide/lib/cmake/Halide -DTARGET=host` fails during configure because `add_halide_library(... FROM spectral_generator)` references generator targets that were never created with `add_halide_generator(...)`.
- This plan intentionally stops before Android JNI or UI. Those require a real Android project boundary and device build matrix; the correct next local step is a verified AOT generator contract.

## Files

- Modify: `tests/test_halide_color.py`
  - Replace ambiguous CCTF reference helpers with sRGB-style encode/decode references that match the runtime color kernel contract.
  - Add branch-threshold tests proving decode uses encoded threshold.
- Modify: `src/spektrafilm/gpu/halide_backend.py`
  - Align `cctf_encode()` / `cctf_decode()` with the same transfer semantics used by `gpu/kernels/color.py`.
- Modify: `src/spektrafilm/generators/CMakeLists.txt`
  - Add `add_halide_generator()` targets for spectral, filter, color, and LUT generator source files.
  - Keep host configure/build possible, and keep `-DTARGET=arm-64-android` as the documented Android AOT target string.
- Modify: `src/spektrafilm/generators/color_generator.cpp`
  - Align AOT CCTF encode/decode formulas with Python Halide semantics.
  - Add missing Halide namespace imports if compiler feedback requires them.
- Modify as needed after compiler feedback: `src/spektrafilm/generators/spectral_generator.cpp`, `src/spektrafilm/generators/filter_generator.cpp`, `src/spektrafilm/generators/lut_generator.cpp`
  - Only make syntax/build-contract fixes required for CMake configure/build.
- Create: `tests/test_halide_generators.py`
  - Add a unit-level configure smoke for the generator CMake project using the installed Halide CMake package when available.
- Modify: `docs/dev/halide-android-port-plan.md`
  - Update current status and next-step section with the verified CMake/AOT contract.
- Modify: `docs/dev/halide-backend-implementation.md`
  - Replace stale “next work” language and record the CCTF semantic correction.

## Tasks

### Task 1: Lock The CCTF Contract With Failing Tests

- [ ] Update `tests/test_halide_color.py` so `numpy_cctf_encode()` computes:

```python
lo = a32 * linear + b32
hi = c32 * np.sign(linear) * np.power(np.abs(linear), np.float32(1.0) / g32) - d32
return np.where(linear <= t32, lo, hi).astype(np.float32)
```

- [ ] Update `numpy_cctf_decode()` so it branches on encoded threshold:

```python
encoded_threshold = a32 * t32 + b32
lo = (encoded - b32) / a32
hi_base = (encoded + d32) / c32
hi = np.sign(hi_base) * np.power(np.abs(hi_base), g32)
return np.where(encoded <= encoded_threshold, lo, hi).astype(np.float32)
```

- [ ] Add a focused test that encoded values just below and just above `0.04045` choose the correct decode branch.
- [ ] Run:

```bash
.venv/bin/python -m pytest tests/test_halide_color.py::TestCctfEncode tests/test_halide_color.py::TestCctfDecode -q
```

Expected before implementation: failures in CCTF encode/decode parity and/or roundtrip.

### Task 2: Fix Python Halide CCTF Semantics

- [ ] Change `HalideBackend._build_cctf_encode_pipeline()` to compute the high branch as:

```python
signed_power = hl.select(v < 0.0, -hl.fast_pow(-v, 1.0 / gamma_p), hl.fast_pow(v, 1.0 / gamma_p))
gamma_part = c_p * signed_power - d_p
```

- [ ] Change `HalideBackend._build_cctf_decode_pipeline()` to compute:

```python
encoded_threshold = a_p * threshold_p + b_p
base = (v + d_p) / c_p
signed_power = hl.select(base < 0.0, -hl.fast_pow(-base, gamma_p), hl.fast_pow(base, gamma_p))
output[x, y, c] = hl.select(v <= encoded_threshold, linear_part, signed_power)
```

- [ ] Keep the existing public method signature for compatibility with the current tests and future AOT parameter marshalling.
- [ ] Run:

```bash
.venv/bin/python -m pytest tests/test_halide_color.py -q
```

Expected after implementation: all Halide color tests pass.

### Task 3: Add Generator CMake Configure Test

- [ ] Create `tests/test_halide_generators.py` with a helper that imports `halide`, resolves `Path(halide.install_dir()) / "lib/cmake/Halide"`, and skips if the CMake package or `cmake` executable is absent.
- [ ] Add a test that runs:

```python
subprocess.run(
    [
        "cmake",
        "-S",
        str(repo_root / "src/spektrafilm/generators"),
        "-B",
        str(tmp_path / "build"),
        f"-DHalide_DIR={halide_cmake_dir}",
        "-DTARGET=host",
    ],
    check=False,
    text=True,
    capture_output=True,
)
```

- [ ] Assert exit code `0`, and include stdout/stderr in the assertion message.
- [ ] Run:

```bash
.venv/bin/python -m pytest tests/test_halide_generators.py -q
```

Expected before implementation: configure fails with “Unable to locate FROM as either spectral_generator...”.

### Task 4: Fix Generator CMake Targets

- [ ] Add these generator executable targets before the existing `add_halide_library()` calls:

```cmake
add_halide_generator(spectral_generator SOURCES spectral_generator.cpp)
add_halide_generator(filter_generator SOURCES filter_generator.cpp)
add_halide_generator(color_generator SOURCES color_generator.cpp)
add_halide_generator(lut_generator SOURCES lut_generator.cpp)
```

- [ ] Keep generated library target names unchanged so future JNI/CMake consumers can continue linking the documented names.
- [ ] Run:

```bash
.venv/bin/python -m pytest tests/test_halide_generators.py -q
```

Expected after implementation: configure succeeds, or reveals the next C++ compile-level issue to fix in Task 5.

### Task 5: Build The Host AOT Generator Project And Fix Compile Contract Issues

- [ ] Run a real build after configure:

```bash
cmake --build /tmp/spektrafilm-halide-generators-check
```

- [ ] If compiler errors show missing Halide symbols, fix namespace imports in the smallest affected generator file. The likely imports are `Halide::Input`, `Halide::Float`, `Halide::cast`, `Halide::clamp`, `Halide::floor`, `Halide::fast_exp`, `Halide::fast_pow`, and `Halide::select`.
- [ ] If compiler errors show invalid dynamic extents in C++ `int` variables, replace compile-time `int` declarations with `Expr` where the value comes from `image.dim(...).extent()`.
- [ ] Repeat the build until host AOT generator libraries compile.

### Task 6: Align AOT Color Generator With JIT CCTF Semantics

- [ ] Update `src/spektrafilm/generators/color_generator.cpp` so `CCTFEncodeGenerator` high branch is `alpha * signed_power(linear, 1/gamma) - offset`, with offset represented by the existing `alpha - 1.0f` convention.
- [ ] Update `CCTFDecodeGenerator` to branch at `linear_slope * threshold` and high branch `signed_power((encoded + offset) / alpha, gamma)`.
- [ ] Run the host AOT build again.
- [ ] Keep this as formula/build validation only; do not claim Android runtime execution until JNI/device tests exist.

### Task 7: Update Android/Halide Documentation

- [ ] Update `docs/dev/halide-android-port-plan.md` current status with:
  - CCTF encode/decode semantics now match the runtime color kernel.
  - Generator CMake configure/build has a host validation test.
  - Android CPU AOT remains the next native target; Vulkan remains experimental.
- [ ] Update `docs/dev/halide-backend-implementation.md` with:
  - New verification commands.
  - Removal or revision of stale “Add Generator/AOT outputs...” wording.
  - Clear warning that no JNI or Android app has shipped yet.

### Task 8: Verification And 100% Confidence Loop

- [ ] Run targeted tests:

```bash
.venv/bin/python -m pytest tests/test_halide_color.py tests/test_halide_lut.py tests/test_halide_android.py tests/test_halide_generators.py -q
```

- [ ] Run broader Halide/backend tests:

```bash
.venv/bin/python -m pytest tests/test_halide_backend.py tests/test_gpu_backend.py tests/test_gpu_lut.py tests/test_gpu_color_chain.py -q
```

- [ ] Run static sanity:

```bash
.venv/bin/python -m compileall src/spektrafilm/gpu src/spektrafilm/halide src/spektrafilm/generators tests -q
git diff --check
```

- [ ] Self-audit before completion:
  - Does the CCTF test prove the old branch-threshold bug would fail? It must.
  - Does the code match `gpu/kernels/color.py`, not a test-only formula? It must.
  - Does the generator CMake project configure under the installed Halide CMake package? It must.
  - Did any generator build failure remain ignored? It must not unless documented as a host-toolchain blocker with exact output.
  - Do docs avoid claiming JNI, APK, or device-side Android completion? They must.

If any answer is no, add a focused failing test or documentation correction, implement the fix, and repeat the relevant verification tier.
