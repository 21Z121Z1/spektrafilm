# Halide Android Port Plan

**Date:** 2026-05-28
**Status:** Android app/JNI foundation exists. No full renderer, APK artifact,
or device-side Halide execution has been shipped.

---

## 2026-05-28 Implementation Amendment

The previous "JNI not started" and "Kotlin UI not started" sections are stale.
This repository now has an `android/` app foundation with Compose UI,
ViewModel/StateFlow state, processor contracts, and JNI/C++ diagnostic bridge
source. The JNI bridge is intentionally minimal and placeholder-free: it checks
direct-buffer address/capacity handling and exposes self-test/version methods,
but it does not link Halide kernels or implement Spektrafilm rendering.

Android NDK cross-compilation remains unproven locally because the SDK has no
complete NDK with `build/cmake/android.toolchain.cmake`. `assembleDebug` fails
with an explicit NDK preflight until `ndk;28.2.13676358` is installed. See
`docs/dev/android-port-status-20260528.md`.

## 1. Current Status

### 1.1 Python JIT backend — COMPLETE

- 67/67 Halide-focused tests pass on the local host (`halide>=21,<22`, Python 3.13)
- 12 verified JIT kernels in `src/spektrafilm/gpu/halide_backend.py`
- All kernels validated against NumPy reference implementations with `atol=1e-5..1e-6`
- See `docs/dev/halide-backend-implementation.md` for the full kernel catalog

### 1.2 C++ AOT generators — SOURCE EXISTS, BUILD VERIFIED

Four generator source files exist in `src/spektrafilm/generators/`:

| Source file | Generators | Kernels |
|------------|-----------|---------|
| `spectral_generator.cpp` | 3 | density_to_light, light_to_raw, compute_density_spectral |
| `filter_generator.cpp` | 2 | gaussian_blur_fir, gaussian_blur_iir |
| `color_generator.cpp` | 3 | cctf_encode, cctf_decode, highlight_boost |
| `lut_generator.cpp` | 2 | interp_1d, lut_2d_cubic |

**Total: 10 generators producing 10 AOT-compiled kernels.**

CMake configuration (`CMakeLists.txt`) defines all 10 `add_halide_library()` targets
and an aggregate `spektrafilm_halide_all` interface library. The build defaults to
`host` target; override with `-DTARGET=arm-64-android` for Android cross-compilation.
The local verification builds the complete host AOT target set and includes a
source-level guard that `density_to_light` indexes density by wavelength rather
than accidentally reusing wavelength 0.

This does **not** prove Android NDK cross-compilation or Android device runtime.
Those remain separate future gates.

### 1.3 Android JNI — NOT STARTED (Foundation laid - see amendment at top)

No JNI wrapper, no Android NDK project, no `.so` packaging exists.

### 1.4 Kotlin UI — NOT STARTED (Foundation laid - see amendment at top)

No Kotlin/Compose code exists.

---

## 2. AOT Contract Layer

The C++ generators mirror the Python JIT formulas at source level. They use
Halide's C++ Generator API (`Halide::Generator<>` base class) and are compiled
via `add_halide_library()` in CMake. Current verification proves host configure,
generator compilation, and host AOT artifact generation; it does not yet execute
the generated C ABI against NumPy parity fixtures.

### 2.1 Generator API pattern

Each generator follows the same structure:

```cpp
class MyKernelGenerator : public Generator<MyKernelGenerator> {
public:
    Input<Buffer<float, 3>> input{"input"};
    Input<float> param{"param"};
    Output<Buffer<float, 3>> output{"output"};

    void generate() {
        Var x("x"), y("y"), c("c");
        // ... kernel logic ...
        output(x, y, c) = /* expression */;
    }

    void schedule() {
        if (auto_schedule) return;
        // ... manual schedule ...
    }
};

HALIDE_REGISTER_GENERATOR(MyKernelGenerator, my_kernel)
```

The `add_halide_library()` CMake function:
1. Compiles the generator executable (host, at build time)
2. Runs the generator to produce `.a` (static library) + `.h` (header) for the target
3. Registers the target for linking via `target_link_libraries()`

### 2.2 Source-level formula map

The generated source is intended to match these Python JIT formulas. Runtime
parity through the generated C ABI is a future test gate.

**density_to_light:** `output(c, y, w) = fast_exp(-density(c, y, w) * ln(10)) * illuminant(w, c)`

**light_to_raw:** `output(c, y, s) = sum_k light(c, y, k) * sensitivity(k, s)` (RDom over 81)

**compute_density_spectral:** `output(c, y, w) = sum_k density_cmy(c, y, k) * channel_density(w, k)` (RDom over 3)

**cctf_encode:** `select(v <= threshold, linear_slope * v, alpha * fast_pow(v, 1/gamma) - (alpha - 1))`

**cctf_decode:** `select(v <= linear_slope * threshold, v / linear_slope, fast_pow((v + (alpha - 1)) / alpha, gamma))`

**highlight_boost:** `select(v < threshold, v * scale, pivot + (v - pivot) * fast_exp(-(v - pivot) * scale))`

**gaussian_blur_fir:** Two-pass separable convolution with `mirror_interior` boundary, `RDom` over kernel width.

**gaussian_blur_iir:** Young-van Vliet 4-tap recursive filter (causal + anti-causal, horizontal + vertical).
This is a full Halide IIR implementation using `RDom` update definitions — unlike the Python JIT
backend which falls back to NumPy because Python JIT cannot express recursive Funcs.

**interp_1d:** Linear interpolation with evenly-spaced shortcut and `clamp` boundary.

**lut_2d_cubic:** Mitchell-Netravali (B=1/3, C=1/3) 4x4 bicubic with `clamp` boundary.

### 2.3 CMake target configuration

```cmake
# Default to host; override with -DTARGET=arm-64-android
if(NOT DEFINED TARGET)
    set(TARGET host)
endif()

# Each add_halide_library() call produces .a + .h for ${TARGET}
add_halide_library(density_to_light FROM spectral_generator ...)
# ... (10 total)

# Aggregate convenience target
add_library(spektrafilm_halide_all INTERFACE)
target_link_libraries(spektrafilm_halide_all INTERFACE
    density_to_light light_to_raw compute_density_spectral
    gaussian_blur_fir gaussian_blur_iir
    cctf_encode cctf_decode highlight_boost
    interp_1d lut_2d_cubic)
```

### 2.4 Build command (host verification)

```bash
cmake -S src/spektrafilm/generators \
      -B /tmp/spektrafilm-halide-generators-check \
      -DHalide_DIR=/path/to/halide/lib/cmake/Halide \
      -DTARGET=host
cmake --build /tmp/spektrafilm-halide-generators-check
```

For Android cross-compilation:
```bash
cmake .. -DTARGET=arm-64-android \
         -DCMAKE_TOOLCHAIN_FILE=$ANDROID_NDK/build/cmake/android.toolchain.cmake \
         -DANDROID_ABI=arm64-v8a \
         -DHalide_DIR=/path/to/halide-android/lib/cmake/Halide
```

---

## 3. What the generators do NOT cover

The following operations are **not** represented as AOT generators:

| Operation | Reason |
|-----------|--------|
| `rgb_to_xyz` (3x3 matmul) | Covered by generic `einsum`/`matmul` — could add a generator if needed |
| `apply_lut_trilinear_3d` | Present in Python JIT, not yet ported to C++ generator |
| `generate_grain_buffer` | RNG — cannot be expressed in Halide. Requires C++ pre-pass |
| FFT convolution | Requires external FFT library or spatial decomposition |
| All non-kernel operations | Element-wise math, reductions — handled by NumPy (Python) or C++ loops |

---

## 4. Next Steps (future work, not this session)

### 4.1 Android NDK project setup

- Create `android/` directory with `build.gradle`, `CMakeLists.txt`
- Configure NDK toolchain for `arm64-v8a`
- Build Halide for Android host (or use pre-built Halide Android distribution)
- Cross-compile the 10 generators for `arm-64-android`
- Link generated `.a` files into a shared library (`libspektrafilm.so`)

### 4.2 JNI wrapper layer

- `SpektrafilmEngine` C++ class wrapping the pipeline
- JNI methods for: `processImage(ByteBuffer, Params)`, `setProfile(String)`, `getVersion()`
- Direct ByteBuffer passing for zero-copy image I/O
- Parameter marshalling via flat C structs (matching `params_schema.py` dataclasses)

### 4.3 Kotlin integration

- Jetpack Compose UI for parameter adjustment
- CameraX integration for live preview
- MediaStore for import/export
- Profile selection from bundled assets

### 4.4 Device testing matrix

- Pixel 6/7/8 (ARM Cortex-A series + Mali GPU)
- Samsung Galaxy S series (Exynos + Mali)
- OnePlus (Snapdragon + Adreno)
- Validate float32 precision parity with host Python output (`atol=1e-5`)

---

## 5. Explicit Warning

**No JNI, APK, or device-side Android code has been shipped.**

What exists:
- Python JIT/backend foundation: fully verified by 67/67 Halide-focused tests on the local host
- C++ AOT generator sources: 10 generators across 4 files, CMake build system configured
- CMake can produce host `.a`/`.h` files (Android cross-compilation not yet validated)

What does NOT exist:
- Android NDK project
- JNI bindings
- Kotlin/Jetpack Compose UI
- Device-side testing
- Vulkan compute dispatch
- APK or app bundle

---

## Appendix: Full Portability Analysis

For a comprehensive module-by-module portability assessment, dependency replacement
map, and risk analysis, see the earlier analysis document below (from 2026-05-27).

---

### A. Dependency Graph

```
Input RGB Image
       |
       v
[Preprocessing] ─── auto_exposure, crop_and_rescale
       |
       v
[FilmingStage.expose]
  ├─ rgb_to_film_raw ─── spectral_upsampling (LUT)
  ├─ boost_highlights ─── piecewise exp
  ├─ diffusion_filter_um ─── FFT or Gaussian mixture
  ├─ gaussian_blur_um ─── FIR/IIR Gaussian
  ├─ halation_um ─── Gaussian + exponential blur
  └─ log10
       |
       v
[FilmingStage.develop]
  ├─ interpolate_exposure_to_density ─── 1D interp
  ├─ dir_couplers ─── einsum + blur
  └─ grain ─── stochastic (RNG + blur)
       |
       v
[PrintingStage.expose]
  ├─ compute_density_spectral ─── einsum
  ├─ density_to_light ─── 10^(-density) * illuminant
  ├─ light_to_raw ─── einsum
  └─ diffusion_filter_um + log10
       |
       v
[PrintingStage.develop]
  └─ interpolate_exposure_to_density
       |
       v
[ScanningStage.scan]
  ├─ cmy_to_log_xyz ─── density_spectral → light → XYZ
  ├─ black_white_correction
  ├─ glare ─── stochastic
  ├─ xyz_to_rgb ─── 3x3 matrix
  ├─ gaussian_blur + unsharp_mask
  └─ cctf_encoding ─── sRGB/ProPhoto/BT.2020
       |
       v
Output RGB Image
```

### B. Operation Portability Summary

| Operation Class | Portability | Halide Fit |
|----------------|-------------|------------|
| Element-wise math (exp, log, pow, select) | Excellent | Native Halide |
| Matrix multiply (3x3, einsum) | Excellent | Halide reduction |
| 1D interpolation | Excellent | Halide with clamp |
| 2D/3D LUT sampling | Excellent | Halide with lookup |
| Gaussian blur (FIR) | Excellent | Halide convolve |
| Gaussian blur (IIR) | Good | Halide scan (C++ generator only) |
| FFT convolution | Medium | External FFT or spatial decomposition |
| Stochastic (RNG) | Poor | Pre-pass C++ RNG |
| Colour-science init | N/A | Precomputed static data |
| File I/O | N/A | Native Android APIs |

### C. Risk: Grain Stochasticity

Halide is deterministic — it cannot express RNG. The grain model needs a two-pass
approach: generate random deviates in C++ (`<random>` or xoroshiro128+), store in
a Halide Buffer, then feed into the grain compute pipeline. The existing
`fast_stats.py` Numba implementations provide reference algorithms.

### D. Risk: Numerical Precision

ARM NEON float32 is IEEE 754 compliant. The project's `atol=1e-6` tolerance
should be achievable. Validate on target devices.

### E. External Library Replacement

| Dependency | Android Replacement |
|-----------|-------------------|
| colour-science | Precomputed matrices + static spectral data arrays |
| scipy (interpolate, FFT) | Native interpolation + FFT library (FFTW/Ne10) |
| Numba | Halide generators (already done) |
| opt-einsum | Halide reductions or C++ loops |
| matplotlib, napari | Skip (GUI only) |
| qtpy/PySide6 | Kotlin/Jetpack Compose |
| Pillow | Android Bitmap API or stb_image |
| OpenImageIO | OpenEXR native |
| rawpy | LibRaw (already native C++) |
