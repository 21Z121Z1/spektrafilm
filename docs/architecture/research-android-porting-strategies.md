# Android Porting Strategies — Deep Research

> **Date:** 2026-05-28
> **Scope:** Detailed technical evaluation of six porting dimensions for bringing
> spektrafilm's spectral film simulation to Android. Builds on the earlier
> `research-android-port.md` (strategy overview) and `halide-android-port-plan.md`
> (AOT generator status).
>
> Each section follows: **Options → Recommendation → Evidence → Risks**.

---

## 2026-05-28 Implementation Amendment

This document is now partially stale for the current repository dependency set.
The implementation pass verified official Chaquopy 17.0 support for Python
3.10-3.14 and AGP 7.3-9.2, but the checked Chaquopy Python 3.13 package index
does not satisfy Spektrafilm's declared dependencies: NumPy is available as
`1.26.2`, not `numpy~=2.4`, and SciPy does not provide a Python 3.13 wheel in
the checked index. The Android foundation therefore does not use Chaquopy.

Implemented foundation now lives under `android/`: AGP 9.2, Kotlin/Compose,
ViewModel/StateFlow, parameter serialization, processor contracts, and JNI
diagnostic bridge source. See `docs/dev/android-port-status-20260528.md`.
Treat later Chaquopy snippets and package-support tables in this document as
historical research unless they are reconfirmed against the current package
index.

## Table of Contents

1. [Python → Android: Runtime Strategies](#1-python--android-runtime-strategies)
2. [Halide AOT on Android](#2-halide-aot-on-android)
3. [NumPy/SciPy Equivalents on Android](#3-numpyscipy-equivalents-on-android)
4. [GPU Compute on Android](#4-gpu-compute-on-android)
5. [Image I/O on Android](#5-image-io-on-android)
6. [Qt/PySide6 on Android & UI Alternatives](#6-qtpyside6-on-android--ui-alternatives)

---

## 1. Python → Android: Runtime Strategies

### Context

Spektrafilm is Python 3.13+ with ~60% pure Python/NumPy code (pipeline logic,
colour-science, model dataclasses) and ~40% native C/C++ (OpenImageIO, exiv2,
rawpy, Numba, pyfftw). The `ArrayBackend` protocol (`gpu/backend.py`) cleanly
separates compute from orchestration, making it feasible to swap backends.

### Options

#### Option A: Chaquopy (Python-in-Android)

Embed CPython 3.13 via the Chaquopy Gradle plugin. Python code runs inside the
Android process with full JNI bridge to Kotlin.

| Aspect | Detail |
|--------|--------|
| Python versions | 3.10, 3.11, 3.12, 3.13, 3.14 (Chaquopy 17.0) |
| minSdk | 24 (Android 7.0) |
| ABIs | `arm64-v8a` (primary), `x86_64` (emulator). 32-bit only for Python ≤3.11 |
| Package support | Pure-Python packages: all. Native packages: prebuilt wheel catalog (numpy, scipy, Pillow, opencv, etc.) |
| APK overhead | +30–50 MB (Python runtime + stdlib + pip packages) |
| Cold start | 0.5–1.5s interpreter init, 1–3s first module imports |
| Performance | ~5–50x slower than C++ for tight loops; native-backed libs (NumPy, OpenCV) run at near-native speed |
| Multiprocessing | Not supported (System V IPC unavailable); use `multiprocessing.dummy` |
| File I/O | `os.environ["HOME"]` → app internal storage; data files extracted at install |

**Build integration:**
```kotlin
// build.gradle.kts
plugins {
    id("com.chaquo.python") version "17.0.0"
}
chaquopy {
    defaultConfig {
        version = "3.13"
        pip {
            install("numpy")
            install("scipy")
            install("colour-science")
            install("Pillow")
            install("opt-einsum")
            install("PyYAML")
            install("lmfit")
        }
    }
}
```

#### Option B: BeeWare / Briefcase

Package Python apps as native Android APKs using Briefcase. Uses Chaquopy
under the hood for the Android target.

| Aspect | Detail |
|--------|--------|
| Build tool | `briefcase create android` then `briefcase build android` |
| Python versions | Matches Chaquopy's supported versions |
| UI framework | Toga (BeeWare's native widget toolkit) — limited Android widgets |
| Package support | Same as Chaquopy (pip packages) |
| Maturity | Production-ready for simple apps; complex native UI limited |

#### Option C: Kivy / Buildozer

Cross-platform Python UI framework with OpenGL ES rendering. Buildozer
packages for Android.

| Aspect | Detail |
|--------|--------|
| UI paradigm | OpenGL ES canvas, custom widget tree (not Material Design) |
| Performance | Decent for UI; image processing still needs NumPy/native |
| APK overhead | +40–60 MB (Python + Kivy + SDL2) |
| Native look | No — custom rendered UI, not platform-native |
| Package support | Limited native package catalog |

#### Option D: Full Kotlin Rewrite

Rewrite the entire pipeline in Kotlin/C++. No Python runtime.

| Aspect | Detail |
|--------|--------|
| Performance | Best possible (10–100x faster than Python) |
| APK size | 5–15 MB |
| Effort | 6–12 months — must port colour-science (15k+ lines), all spectral models |
| colour-science | No C/C++ equivalent exists; must reimplement or precompute all matrices |
| Risk | Massive scope; lose Python scientific ecosystem |

### Recommendation

**Option A: Chaquopy** as the primary strategy. Reasons:

1. **ArrayBackend protocol** means the hot path (NumPy operations) already runs
   at native speed via prebuilt numpy wheels. The Python orchestration overhead
   is negligible compared to image processing time.
2. **colour-science** library works unchanged — this is the single hardest
   dependency to replace in a native rewrite.
3. **Incremental migration**: start with `NumpyBackend` (CPU), add
   `HalideBackend` or `VulkanBackend` later via the same protocol.
4. **Chaquopy 17.0 supports Python 3.13**, matching spektrafilm's requirement.

### Evidence

- Chaquopy 17.0 documentation confirms Python 3.13 support, prebuilt numpy
  and scipy wheels, and Gradle plugin integration.
- The `ArrayBackend` protocol (`gpu/backend.py:7-31`) cleanly separates compute
  from orchestration — the pipeline never calls numpy directly, only through
  `backend.exp()`, `backend.einsum()`, etc.
- colour-science is pure Python with numpy dependencies — installs via pip on
  Chaquopy without native compilation.

### Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Python cold start (1–3s) | Medium | Keep Python process alive; pre-import modules in `Application.onCreate()` |
| APK size (+30–50 MB) | Low | Acceptable for photo app; use App Bundle to split ABIs |
| Numba unavailable | High | Replace with Halide AOT generators (already done for 10 kernels) or C++ |
| pyfftw unavailable | Medium | Replace with pocketfft (pure C, NDK-buildable) or VkFFT |
| multiprocessing broken | Low | Pipeline is single-threaded; use threading for batch |
| Debug across Python/Kotlin | Medium | Use structured logging; Chaquopy redirects stdout/stderr to Logcat |

---

## 2. Halide AOT on Android

### Context

Spektrafilm already has 10 Halide AOT generators in C++ (`src/spektrafilm/generators/`)
producing optimized kernels. The generators use `Halide::Generator<>` base class
and compile via `add_halide_library()` in CMake. Currently targeting `host`;
Android cross-compilation requires targeting `arm-64-android`.

### Options

#### Option A: Halide AOT → Static Library → NDK Link

Compile Halide generators on the build host for `arm-64-android` target, producing
`.a` + `.h` files, link into a shared `libspektrafilm.so` via NDK CMake.

**Build flow:**
```
[Build Host]                          [Android Device]
generators/*.cpp ──► Halide compiler ──► .a + .h ──► NDK link ──► libspektrafilm.so
  (x86-64)          (runs generators     (arm-64)     (CMake)      (loaded at runtime)
                      for target)
```

**CMake integration:**
```cmake
# Cross-compile Halide generators for Android
find_package(Halide REQUIRED)

add_halide_library(density_to_light
    FROM spectral_generator
    GENERATOR density_to_light
    TARGETS arm-64-android
    FEATURES neon
    AUTOSCHEDULER Halide::Adams2019
)

# ... repeat for all 10 generators ...

# Aggregate target
add_library(spektrafilm_halide_all INTERFACE)
target_link_libraries(spektrafilm_halide_all INTERFACE
    density_to_light light_to_raw compute_density_spectral
    gaussian_blur_fir gaussian_blur_iir
    cctf_encode cctf_decode highlight_boost
    interp_1d lut_2d_cubic
)

# JNI wrapper
add_library(spektrafilm SHARED jni_bridge.cpp)
target_link_libraries(spektrafilm PRIVATE spektrafilm_halide_all)
```

**Halide target strings for Android:**

| ABI | Halide Target | Features |
|-----|---------------|----------|
| `arm64-v8a` | `arm-64-android` | `neon`, `vfpv4` |
| `armeabi-v7a` | `arm-32-android` | `neon` |
| `x86_64` | `x86-64-android` | `sse4.1`, `avx` (emulator) |
| `x86` | `x86-32-android` | `sse4.1` (legacy emulator) |

#### Option B: Halide Auto-Scheduler for ARM

Use Halide's auto-scheduler (`Adams2019` or `Mullapudi2016`) to automatically
generate schedules optimized for ARM Cortex-A cores.

```cmake
add_halide_library(gaussian_blur_fir
    FROM filter_generator
    GENERATOR gaussian_blur_fir
    TARGETS arm-64-android
    AUTOSCHEDULER Halide::Adams2019
)
```

The auto-scheduler analyzes the pipeline DAG and generates:
- NEON vectorization (128-bit SIMD, 4x float32)
- Cache-tiled loop nests
- Parallel loop scheduling across cores
- Fusion of element-wise operations

#### Option C: Halide AOT + Vulkan Backend (Hybrid)

Use Halide AOT for CPU kernels (NEON) and Vulkan compute shaders for GPU
dispatch. The `ArrayBackend` protocol selects at runtime.

```
┌─────────────────────────────────┐
│  ArrayBackend                   │
│  ├── HalideBackend (CPU/NEON)   │  ← 10 AOT generators
│  ├── VulkanBackend (GPU)        │  ← compute shaders
│  └── NumpyBackend (fallback)    │  ← Chaquopy numpy
└─────────────────────────────────┘
```

### Recommendation

**Option A (Halide AOT → NDK link)** as the primary compute path, with
**Option C (Vulkan backend)** as a future GPU acceleration layer.

Rationale:
1. The 10 AOT generators already exist and implement the core hot-path kernels
2. ARM NEON auto-vectorization from Halide gives 3–4x speedup over scalar C++
3. No JIT needed on device — all compilation happens at build time
4. The `atol=1e-6` precision guarantee is maintained (float32 throughout)

### Evidence

- **Google's usage**: Halide is used internally at Google for Android camera
  pipelines (Google Camera HDR+, Night Sight, Portrait Mode). The Halide team
  actively maintains the `arm-64-android` target.
- **Existing generators**: The 10 generators cover the critical hot paths:
  - Spectral: `density_to_light`, `light_to_raw`, `compute_density_spectral`
  - Filters: `gaussian_blur_fir` (separable FIR), `gaussian_blur_iir` (YvV 4-tap)
  - Color: `cctf_encode`, `cctf_decode`, `highlight_boost`
  - LUT: `interp_1d`, `lut_2d_cubic` (Mitchell-Netravali)
- **Halide CMake**: `add_halide_library()` is the official CMake function for
  AOT compilation. It handles generator compilation, cross-compilation, and
  `.a`/`.h` output.
- **ARM NEON**: Halide's `vectorize(x, 4)` on `float32` maps directly to NEON
  128-bit SIMD instructions (`vmlaq_f32`, etc.). The auto-scheduler handles
  this automatically.

### Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Halide Android cross-compilation untested | High | Build Halide from source for Android host; test with a trivial generator first |
| Auto-scheduler quality on ARM | Medium | Manual schedule overrides for critical kernels (already done in generators) |
| Generator coverage gaps | Medium | 3 operations not covered: `rgb_to_xyz` (3x3 matmul), `apply_lut_trilinear_3d`, grain RNG — add generators or use C++ |
| IIR recursion in Halide | Low | Already implemented as RDom update definitions in `filter_generator.cpp` |
| Binary size per generator | Low | Each generator produces ~50–200 KB `.a`; 10 generators ≈ 1–2 MB total |
| Halide version compatibility | Low | Project pins `halide>=21,<22`; generators use v21 `Output<Buffer<>>` API |

### Build Verification Steps

```bash
# 1. Build Halide for the Android host (one-time)
git clone https://github.com/halide/Halide.git
cd Halide && git checkout v21.0.0
cmake -B build -DCMAKE_BUILD_TYPE=Release \
      -DHalide_TARGET=host \
      -DCMAKE_INSTALL_PREFIX=$HOME/halide-host
cmake --build build && cmake --install build

# 2. Cross-compile generators for Android
cd src/spektrafilm/generators
cmake -B build-android \
      -DCMAKE_TOOLCHAIN_FILE=$ANDROID_NDK/build/cmake/android.toolchain.cmake \
      -DANDROID_ABI=arm64-v8a \
      -DANDROID_PLATFORM=android-26 \
      -DHalide_DIR=$HOME/halide-host/lib/cmake/Halide \
      -DTARGET=arm-64-android
cmake --build build-android

# 3. Verify outputs
ls build-android/*.a build-android/*.h
# Expected: density_to_light.a, density_to_light.h, ... (10 pairs)
```

---

## 3. NumPy/SciPy Equivalents on Android

### Context

Spektrafilm's `NumpyBackend` uses: `np.exp`, `np.log10`, `np.maximum`, `np.clip`,
`np.matmul`, `np.power`, `np.where`, `np.abs`, `np.nan_to_num`, and
`opt_einsum.contract` for einsum operations. The `ArrayBackend` protocol
abstracts these, so replacements only need to implement the protocol.

### Options

#### Option A: Chaquopy Prebuilt NumPy/SciPy

Chaquopy ships prebuilt wheels for numpy and scipy on `arm64-v8a`. This is
the simplest path — the existing `NumpyBackend` works unchanged.

| Package | Chaquopy Status | Version |
|---------|----------------|---------|
| numpy | Prebuilt wheel | ~2.4 |
| scipy | Prebuilt wheel | ~1.17 |
| scikit-image | Prebuilt wheel | ~0.26 |
| Pillow | Prebuilt wheel | ~12.1 |
| opt-einsum | Pure Python | ~3.4.0 |

**Performance**: NumPy on Android ARM64 uses BLAS (OpenBLAS or reference BLAS)
for matrix operations. Typical performance:
- `np.matmul` (1000x1000): ~5–15ms (BLAS-optimized)
- `np.exp` (24MP float32): ~50–100ms (NEON-vectorized)
- `opt_einsum.contract` (spectral einsum): ~10–30ms

#### Option B: Eigen for C++ Matrix Operations

Eigen is a header-only C++ template library for linear algebra. Can be used
in the NDK C++ layer for matrix operations.

```cpp
#include <Eigen/Dense>

// 3x3 colour matrix transform (per-pixel)
Eigen::Matrix3f rgb_to_xyz;
rgb_to_xyz << 0.4124f, 0.3576f, 0.1805f,
              0.2126f, 0.7152f, 0.0722f,
              0.0193f, 0.1192f, 0.9505f;

// Process pixel buffer
for (int i = 0; i < num_pixels; i++) {
    Eigen::Vector3f pixel(pixels[i*3], pixels[i*3+1], pixels[i*3+2]);
    Eigen::Vector3f result = rgb_to_xyz * pixel;
    output[i*3] = result(0);
    output[i*3+1] = result(1);
    output[i*3+2] = result(2);
}
```

**Pros**: No dependency on Python; NEON auto-vectorization via GCC/Clang;
header-only (no build step).

**Cons**: Only covers linear algebra; doesn't replace element-wise NumPy ops.

#### Option C: Vulkan Compute for Array Operations

Use Vulkan compute shaders for all array operations (exp, log, matmul, etc.).
This is the highest-performance option but requires the most infrastructure.

See [Section 4: GPU Compute on Android](#4-gpu-compute-on-android) for details.

#### Option D: xtensor (NumPy-like C++ Array Library)

xtensor provides a NumPy-like API in C++ with lazy evaluation and SIMD support.

```cpp
#include <xtensor/xarray.hpp>
#include <xtensor/xmath.hpp>

xt::xarray<float> density = ...;
xt::xarray<float> transmittance = xt::pow(10.0f, -density);
xt::xarray<float> light = transmittance * illuminant;
```

**Pros**: Familiar API for NumPy users; lazy evaluation; SIMD support.

**Cons**: Not prebuilt for Android NDK; requires manual build; smaller community.

### Recommendation

**Option A (Chaquopy NumPy)** for the initial port, supplemented by
**Option B (Eigen)** in the NDK C++ layer for operations that Halide generators
don't cover (e.g., small matrix operations, coefficient computation).

The `ArrayBackend` protocol means this is a non-decision at the architecture
level — `NumpyBackend` works immediately via Chaquopy, and `HalideBackend`
replaces hot paths later.

### Evidence

- Chaquopy's package catalog lists numpy, scipy, and scikit-image as prebuilt
  wheels for `arm64-v8a`.
- The `NumpyBackend` (`gpu/numpy_backend.py`) is 60 lines of straightforward
  numpy calls — zero modifications needed for Chaquopy.
- opt-einsum is pure Python — installs without compilation.

### Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| BLAS performance on ARM | Medium | numpy uses OpenBLAS on Chaquopy; matmul is ~2x slower than desktop. Use Halide for hot-path matmul |
| scipy.interpolate availability | Low | Chaquopy prebuilds scipy; FITPACK interpolation works |
| scikit-image availability | Low | Prebuilt on Chaquopy; used only for `resize` in `crop_resize.py` |
| Memory pressure from Python arrays | Medium | Use tiled processing (already implemented in `backend.py:tiled_processing`) |

---

## 4. GPU Compute on Android

### Context

Spektrafilm's GPU backends implement the `ArrayBackend` protocol. Currently:
- `MlxBackend` — Apple Silicon (Metal), not portable
- `CupyBackend` — CUDA/ROCm, not portable to mobile
- `HalideBackend` — CPU/vector, portable via AOT

A new Android GPU backend is needed for performance-critical processing.

### Options

#### Option A: Vulkan Compute Shaders

Vulkan 1.1+ is supported on 95%+ of active Android devices (2024+). All major
SoCs support compute shaders.

| SoC | GPU | Vulkan | Compute Shaders |
|-----|-----|--------|-----------------|
| Snapdragon 8 Gen 3 | Adreno 750 | 1.3 | Yes |
| Exynos 2400 | Xclipse 940 | 1.3 | Yes |
| Dimensity 9300 | Immortalis-G720 | 1.3 | Yes |
| Tensor G3 | Mali-G715 | 1.3 | Yes |

**Capabilities:**
- `VK_QUEUE_COMPUTE_BIT` — dedicated compute queue
- Shared memory: 16–32 KB per workgroup
- Typical workgroup size: 128–256 invocations
- `shaderStorageImageExtendedFormats` — wide-format storage images
- Float32 precision (IEEE 754 compliant on all modern mobile GPUs)

**Example: element-wise exp shader:**
```glsl
#version 450
layout(local_size_x = 256) in;

layout(set = 0, binding = 0) buffer InputBuffer { float input_data[]; };
layout(set = 0, binding = 1) buffer OutputBuffer { float output_data[]; };

void main() {
    uint idx = gl_GlobalInvocationID.x;
    output_data[idx] = exp(input_data[idx]);
}
```

**Integration framework: Kompute** (Linux Foundation project)
- C++ SDK with Android NDK support
- Python bindings (pip installable)
- Mobile-enabled with dynamic Vulkan loading
- Apache 2.0 license
- GitHub: `KomputeProject/kompute`

```cmake
# Kompute in Android CMake
add_subdirectory(third_party/kompute)
target_link_libraries(spektrafilm PRIVATE kompute)
```

#### Option B: OpenGL ES 3.1 Compute Shaders

Broader compatibility (~99% of devices) but higher dispatch overhead.

```glsl
#version 310 es
layout(local_size_x = 256) in;
layout(std430, binding = 0) buffer InputBuffer { float input_data[]; };
layout(std430, binding = 1) buffer OutputBuffer { float output_data[]; };

void main() {
    uint idx = gl_GlobalInvocationID.x;
    output_data[idx] = exp(input_data[idx]);
}
```

**Pros**: Near-universal device support; simpler API than Vulkan.

**Cons**: Higher per-dispatch overhead; less explicit memory control; no
dedicated compute queue family.

#### Option C: NNAPI (Android Neural Networks API)

Designed for ML inference, not general-purpose compute. Limited utility for
Spektrafilm's pixel-processing pipeline.

**Not recommended** — NNAPI is optimized for tensor operations in ML models,
not image processing pipelines with arbitrary data dependencies.

#### Option D: OpenCL via POCL

OpenCL is not natively supported on most Android devices (Qualcomm dropped
OpenCL support on some Adreno drivers). POCL (Portable Computing Language)
can provide a CPU OpenCL implementation but doesn't give GPU access.

**Not recommended** — vendor support is inconsistent and declining.

### Recommendation

**Option A: Vulkan Compute** via the Kompute framework. Reasons:

1. **Cross-vendor**: Works on Adreno (Qualcomm), Mali (ARM), Xclipse (Samsung),
   PowerVR (Imagination) — all modern Android GPUs.
2. **Float32 precision**: IEEE 754 compliant, matching spektrafilm's
   zero-precision-loss requirement.
3. **Kompute** reduces Vulkan boilerplate from 500–2000 lines to ~50 lines
   per kernel dispatch.
4. **Android NDK integration**: Kompute has first-class Android support with
   `KOMPUTE_OPT_ANDROID_BUILD=ON` CMake flag and NDK Vulkan wrapper headers.
5. **Async dispatch**: Kompute supports multi-queue parallel dispatch,
   useful for pipeline stages.

### Evidence

- Kompute documentation confirms Android NDK support with a working
  `CMakeLists.txt` example for Android builds.
- Vulkan compute is used by Google's ML frameworks (TensorFlow Lite GPU
  delegate) and camera pipelines on Android.
- The `ArrayBackend` protocol maps cleanly to Vulkan compute dispatches:
  each method (`exp`, `matmul`, `einsum`, `clip`, etc.) becomes a compute
  shader dispatch.

### Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Vulkan not available on old devices | Low | minSdk 26 (Android 8.0) guarantees Vulkan 1.0; use NumpyBackend fallback |
| GPU memory limits | Medium | Tiled processing (already implemented); typical mobile GPU has 2–6 GB shared memory |
| Shader compilation latency | Medium | Pre-compile SPIR-V at build time; cache pipeline objects |
| Precision differences across GPUs | High | Validate `atol=1e-6` on each target GPU; fall back to CPU if validation fails |
| Kompute maintenance risk | Low | Linux Foundation backed; active community; Apache 2.0 |
| Debug difficulty | Medium | Use Vulkan validation layers in debug builds; Android GPU Inspector |

### GPU Vendor Quirks

| Vendor | GPU Family | Known Issues |
|--------|------------|--------------|
| Qualcomm | Adreno 6xx/7xx | Robust Vulkan; `VK_KHR_portability_subset` may be needed |
| ARM | Mali-G7xx | Lower shared memory (16 KB); good float32 precision |
| Samsung | Xclipse | AMD RDNA-based; good Vulkan 1.3 support |
| MediaTek | Mali-Immortalis | Good compute performance; test precision carefully |
| Google | Mali (Tensor) | Same as ARM Mali; standard Android reference |

---

## 5. Image I/O on Android

### Context

Spektrafilm's I/O (`utils/io.py`) uses:
- **OpenImageIO (OIIO)**: EXR read/write, multi-channel support
- **Pillow**: PNG, JPEG, TIFF
- **pillow-heif**: HEIC/HEIF read/write (implied by HDR photo support)
- **rawpy**: RAW file decoding (LibRaw wrapper)
- **exiv2**: EXIF/IPTC/XMP metadata
- **pyfftw**: FFT for Gaussian blur (not I/O, but related)

### Options

#### Option A: Platform APIs + NDK Libraries

| Format | Read | Write | Library |
|--------|------|-------|---------|
| **HEIC/HEIF** | Android 10+ `ImageDecoder` / NDK `AImageDecoder` (API 31+) | Android 10+ `HeifWriter` / libheif NDK | Platform + libheif |
| **EXR** | tinyexr (header-only C++) | tinyexr | tinyexr |
| **TIFF** | libtiff (NDK) | libtiff (NDK) | libtiff |
| **PNG** | Android `BitmapFactory` / stb_image | stb_image_write | Platform or stb |
| **JPEG** | Android `BitmapFactory` | Android `Bitmap.compress()` | Platform |
| **DNG/RAW** | LibRaw (NDK build) | N/A (read-only) | LibRaw |

**tinyexr** (EXR support):
- Header-only: `#define TINYEXR_IMPLEMENTATION` in one `.cpp` file
- Reads/writes OpenEXR multi-channel float32 images
- No external dependencies
- GitHub: `syoyo/tinyexr` (actively maintained)
- Perfect for spektrafilm's EXR HDR rendition output

**libheif** (HEIC support):
- C/C++ library for HEIF/HEIC read/write
- Requires libde265 (HEVC decoder) or dav1d (AV1 decoder)
- ARM NEON optimizations in v1.17+
- Alternative: Android's built-in `AImageDecoder` NDK API (Android 12+)

**libtiff** (TIFF support):
- Standard C library
- Available via NDK or build from source
- Supports 32-bit float TIFF (needed for spectral data)

#### Option B: Chaquopy Pillow + Custom Native Extensions

Use Pillow (prebuilt on Chaquopy) for PNG/JPEG/TIFF, add native extensions
for HEIC and EXR via JNI.

```
Kotlin UI
    │
    ▼
Chaquopy Python
    ├── Pillow (PNG, JPEG, TIFF)     ← prebuilt wheel
    ├── tinyexr_jni (EXR)            ← NDK C++ → JNI → Python
    └── libheif_jni (HEIC)           ← NDK C++ → JNI → Python
```

#### Option C: Android Bitmap + Hardware Buffers

Use Android's `Bitmap` API for basic formats, `AHardwareBuffer` for zero-copy
GPU path.

```kotlin
// Load image
val bitmap = BitmapFactory.decodeFile(inputPath)

// Convert to float32 array for pipeline
val pixels = FloatArray(width * height * 3)
val buffer = ByteBuffer.allocateDirect(pixels.size * 4)
bitmap.copyPixelsToBuffer(buffer)
// ... pass to Python via Chaquopy ...
```

**Pros**: Zero-copy GPU path via `AHardwareBuffer`; hardware-accelerated
decode/encode.

**Cons**: Limited to Android-supported formats; no EXR support; RGBA only
(no multi-channel).

### Recommendation

**Hybrid approach:**
1. **HEIC**: Use Android's built-in `AImageDecoder` NDK API (Android 12+)
   for reading; libheif for writing with HDR gain map metadata.
2. **EXR**: Use tinyexr (header-only, zero dependencies, float32 support).
3. **TIFF**: Use libtiff via NDK (supports float32 multi-channel).
4. **PNG/JPEG**: Use Android `BitmapFactory` for reading, stb_image_write
   for writing (lighter than Pillow).
5. **RAW/DNG**: Use LibRaw via NDK build.
6. **Metadata**: Use Android's `ExifInterface` (supports DNG tags since API 24)
   or build exiv2 via NDK.

### Evidence

- tinyexr is a single header file with no dependencies — trivially integrable
  into any NDK project.
- Android's `AImageDecoder` NDK API (API 31+) provides hardware-accelerated
  HEIC decoding without external dependencies.
- libheif is actively maintained (v1.17+) with ARM NEON optimizations.
- The existing `utils/io.py` uses OIIO for EXR read/write — tinyexr is a
  direct replacement for the EXR subset.

### Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| HEIC HDR gain map writing | High | Android's `HeifWriter` doesn't support gain maps; use libheif with custom metadata injection |
| EXR multi-channel support | Medium | tinyexr supports multi-channel EXR; verify channel layout matches OIIO output |
| OIIO feature parity | Medium | OIIO handles many formats; Android needs per-format library selection |
| RAW format coverage | Medium | LibRaw covers most camera RAW formats; test with target camera files |
| ICC profile embedding | Low | Pillow/PIL supports ICC embedding; Android's `ExifInterface` handles DNG profiles |
| Memory for large images | Medium | Use streaming decode where possible; tiled processing for GPU path |

### Format Priority for Spektrafilm

| Format | Priority | Reason |
|--------|----------|--------|
| HEIC | Critical | HDR photo export with gain maps (core feature) |
| EXR | Critical | HDR rendition mode, ACES interchange |
| TIFF | High | Lossless intermediate, spectral data storage |
| PNG | High | SDR export, preview sharing |
| JPEG | Medium | Quick sharing, low-quality preview |
| RAW/DNG | Medium | Camera import (Phase 4 feature) |

---

## 6. Qt/PySide6 on Android & UI Alternatives

### Context

Spektrafilm's GUI (`spektrafilm_gui/`) is built with PySide6 (Qt 6.9) and
uses napari for image viewing. The GUI has 24 Python modules covering:
parameter editing, profile synchronization, runtime control, persistence,
theming, and widget primitives.

### Options

#### Option A: Qt for Android (C++ Qt, not PySide6)

Qt 6.8+ supports Android as a target platform. However, **PySide6 for Android
is not officially supported** — Qt's Android deployment uses C++/QML, not Python.

| Aspect | Detail |
|--------|--------|
| Qt for Android | Supported (C++ / QML) |
| PySide6 for Android | **Not supported** — no official deployment tooling |
| pyside6-android-deploy | Experimental; limited documentation; large APK size |
| QML UI | Declarative UI language; Material Design support |
| Build complexity | High (Qt + NDK + Android Gradle) |

#### Option B: Jetpack Compose (Kotlin)

Google's modern declarative UI toolkit for Android. Native look and feel,
Material Design 3, excellent tooling.

| Aspect | Detail |
|--------|--------|
| UI paradigm | Declarative (Kotlin DSL) |
| Material Design | Full MD3 support (dynamic color, theming) |
| Performance | Excellent (Compose runtime optimized for mobile) |
| State management | StateFlow / ViewModel — maps well to spektrafilm's param system |
| Image preview | Canvas rendering, Coil for image loading |
| Development speed | Fast (live preview in Android Studio) |

**Compose equivalent of spektrafilm's parameter UI:**
```kotlin
@Composable
fun ParameterSlider(
    label: String,
    value: Float,
    onValueChange: (Float) -> Unit,
    valueRange: ClosedFloatingPointRange<Float> = 0f..1f
) {
    Column {
        Text(text = "$label: ${"%.2f".format(value)}")
        Slider(
            value = value,
            onValueChange = onValueChange,
            valueRange = valueRange,
            colors = SliderDefaults.colors(
                thumbColor = MaterialTheme.colorScheme.primary,
                trackColor = MaterialTheme.colorScheme.primaryContainer
            )
        )
    }
}
```

#### Option C: Flutter (Dart)

Cross-platform UI framework. Would allow sharing UI code between Android and iOS.

| Aspect | Detail |
|--------|--------|
| Cross-platform | Android + iOS from single codebase |
| Performance | Good (Skia/Impeller rendering) |
| Platform integration | FFI for C/C++; platform channels for Kotlin/Swift |
| Dart ecosystem | Smaller than Kotlin; no scientific libraries |

#### Option D: WebView (Hybrid)

Render UI in a WebView using HTML/CSS/JS. Communicate with Python via
Chaquopy bridge.

| Aspect | Detail |
|--------|--------|
| UI quality | Good (web technologies are mature) |
| Performance | Slower than native; janky scrolling |
| Development speed | Fast (web tooling) |
| Native feel | Poor — doesn't match Android conventions |

### Recommendation

**Option B: Jetpack Compose** for the Android UI. Reasons:

1. **Native Android experience**: Material Design 3, dynamic theming,
   proper gesture handling, system integration (share intent, notifications).
2. **State management**: Compose's `StateFlow` + `ViewModel` maps directly
   to spektrafilm's `RuntimePhotoParams` dataclass pattern.
3. **Python bridge**: Chaquopy's JNI bridge connects Compose UI to Python
   pipeline. Parameters are serialized as JSON, passed to Python, results
   returned as file paths or byte arrays.
4. **Performance**: Compose renders at 60/120 FPS; image preview uses
   `Bitmap` + `Canvas` for real-time rendering.
5. **Tooling**: Android Studio provides live preview, layout inspector,
   profiler — much better than Qt Creator for mobile development.

### Evidence

- Jetpack Compose is Google's recommended UI toolkit for new Android apps
  (since 2021). Material Design 3 is the current design system.
- The spektrafilm GUI's parameter system (`params_schema.py` with dataclasses)
  maps cleanly to Compose's state model — each field becomes a `mutableStateOf`.
- Chaquopy's `Python.getModule().callAttr()` API provides clean Kotlin ↔
  Python interop for the pipeline bridge.
- The existing GUI's 24 modules cover ~500 lines of widget code — modest
  enough to rewrite in Compose in 2–3 weeks.

### Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Full GUI rewrite required | Medium | GUI is ~500 lines of widget code; Compose equivalent is ~300 lines |
| napari not available | Low | Replace with Compose Canvas + custom image viewer; napari is overkill for mobile |
| Qt knowledge doesn't transfer | Low | Compose is well-documented; Kotlin is similar to Python in expressiveness |
| Dark mode / theming | Low | Material 3 has built-in dynamic color theming |
| Image preview performance | Medium | Use `Bitmap` + hardware-accelerated Canvas; downsample for preview |
| Complex color picker UI | Medium | Use Compose Color Picker library or custom Canvas implementation |

### UI Architecture Mapping

| Spektrafilm GUI Module | Compose Equivalent | Effort |
|------------------------|--------------------|--------|
| `widgets.py` (parameter sliders) | Compose `Slider`, `TextField` | 1 week |
| `theme.py` + `theme_palette.py` | Material 3 `ColorScheme` | 2 days |
| `controller.py` (state management) | `ViewModel` + `StateFlow` | 1 week |
| `persistence.py` (save/load) | `DataStore` or JSON files | 3 days |
| `options.py` (film stock presets) | Compose `LazyVerticalGrid` | 3 days |
| `napari_layout.py` (image viewer) | Custom Compose `Canvas` | 1 week |
| `polaroid_animation.py` | Compose `AnimatedVisibility` | 2 days |
| `controller_runtime.py` (pipeline bridge) | Chaquopy `PythonBridge` class | 1 week |

---

## Summary: Recommended Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Android App (Kotlin + Jetpack Compose)                      │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  UI Layer (Compose / Material 3)                        │ │
│  │  ├── EditScreen (parameter sliders, film stock selector)│ │
│  │  ├── PreviewCanvas (real-time image rendering)          │ │
│  │  ├── ExportDialog (format, quality, ICC profile)        │ │
│  │  └── GalleryScreen (processed images)                   │ │
│  └───────────────────────┬─────────────────────────────────┘ │
│                          │ Chaquopy JNI                       │
│  ┌───────────────────────▼─────────────────────────────────┐ │
│  │  Python Pipeline (Chaquopy 17.0, Python 3.13)           │ │
│  │  ├── params_schema / params_builder (unchanged)         │ │
│  │  ├── pipeline.py → stages/ (unchanged)                  │ │
│  │  ├── model/ (emulsion, couplers, etc. — unchanged)      │ │
│  │  ├── colour-science (XYZ, RGB — unchanged)              │ │
│  │  └── gpu/backend.py → ArrayBackend protocol             │ │
│  └───────────────────────┬─────────────────────────────────┘ │
│                          │                                    │
│  ┌───────────────────────▼─────────────────────────────────┐ │
│  │  Compute Backends (ArrayBackend)                        │ │
│  │  ├── HalideBackend (10 AOT generators, ARM NEON)        │ │
│  │  │   └── .a/.h from CMake cross-compilation             │ │
│  │  ├── VulkanBackend (Kompute, compute shaders) — future  │ │
│  │  └── NumpyBackend (Chaquopy numpy — fallback)           │ │
│  └───────────────────────┬─────────────────────────────────┘ │
│                          │                                    │
│  ┌───────────────────────▼─────────────────────────────────┐ │
│  │  Image I/O (NDK C++)                                    │ │
│  │  ├── tinyexr (EXR read/write)                           │ │
│  │  ├── libheif (HEIC read/write with HDR gain maps)       │ │
│  │  ├── libtiff (TIFF read/write)                          │ │
│  │  ├── LibRaw (RAW/DNG decode)                            │ │
│  │  └── Android Bitmap (PNG/JPEG)                          │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

### Timeline Estimate

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| 1. Chaquopy PoC | 2–3 weeks | APK running pipeline on CPU (NumpyBackend) |
| 2. Compose UI | 2–3 weeks | Native Android UI with parameter editing |
| 3. Halide AOT integration | 2–3 weeks | NEON-optimized compute via 10 AOT generators |
| 4. Image I/O | 1–2 weeks | HEIC/EXR/TIFF/PNG read/write |
| 5. Vulkan backend | 4–6 weeks | GPU compute via Kompute (optional, for perf) |
| 6. RAW capture | 2–3 weeks | CameraX + LibRaw integration |
| 7. Polish & HDR | 2–3 weeks | HDR display, ICC profiles, batch processing |
| **Total** | **15–23 weeks** | Production-ready Android app |

---

## Appendix: Cross-Reference to Existing Documents

| Document | Path | Relevant Sections |
|----------|------|-------------------|
| Android port strategy overview | `docs/dev/research-android-port.md` | Architecture, phased plan, colour management |
| Halide Android port plan | `docs/dev/halide-android-port-plan.md` | AOT generator status, CMake config, JNI plan |
| Halide deep research | `docs/dev/halide-deep-research.md` | Generator API, scheduling, ARM NEON |
| Halide backend implementation | `docs/dev/halide-backend-implementation.md` | JIT kernel catalog, validation results |
| GPU colour management research | `docs/dev/research-gpu-color-management.md` | Colour pipeline, ICC profiles, HDR |
