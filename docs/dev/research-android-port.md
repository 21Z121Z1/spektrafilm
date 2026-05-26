# Spektrafilm Android Port — Research & Strategy

> Research date: 2026-05-27
> Scope: Porting the spectral film simulation engine to Android while preserving
> zero-precision-loss GPU requirements and colour-science fidelity.

---

## Table of Contents

1. [Codebase Portability Assessment](#1-codebase-portability-assessment)
2. [Porting Strategies Comparison](#2-porting-strategies-comparison)
3. [GPU Compute on Android](#3-gpu-compute-on-android)
4. [Color Management on Android](#4-color-management-on-android)
5. [RAW/DNG Processing on Mobile](#5-rawdng-processing-on-mobile)
6. [Architecture Recommendations](#6-architecture-recommendations)
7. [Performance Considerations](#7-performance-considerations)
8. [Build System Setup](#8-build-system-setup)
9. [Recommended Approach](#9-recommended-approach)

---

## 1. Codebase Portability Assessment

### Current Architecture

Spektrafilm's pipeline is structured as:

```
Input RGB → Spectral Upsampling → Film Exposure → Development →
  [Optional: Printing → Development] → Scanning → Output RGB
```

Key modules and their Android portability:

| Module | Path | Android Portability | Notes |
|--------|------|---------------------|-------|
| **Pipeline orchestrator** | `runtime/pipeline.py` | Pure Python | Fully portable |
| **Spectral upsampling** | `utils/spectral_upsampling.py` | NumPy/SciPy | Needs NumPy on Android |
| **Emulsion model** | `model/emulsion.py` | NumPy + colour-science | colour-science is pure Python |
| **GPU backend** | `gpu/backend.py` | Abstract protocol | New Android backend needed |
| **NumPy backend** | `gpu/numpy_backend.py` | NumPy + opt-einsum | Portable via Chaquopy |
| **MLX backend** | `gpu/mlx_backend.py` | Apple-only | Not portable — skip |
| **CuPy backend** | `gpu/cupy_backend.py` | CUDA-only | Not portable — replace with Vulkan |
| **Colour kernels** | `gpu/kernels/color.py` | Backend-portable | Portable if backend exists |
| **LUT kernels** | `gpu/kernels/lut.py` | Backend-portable | Portable if backend exists |
| **Density kernels** | `gpu/kernels/density.py` | Backend-portable | Portable if backend exists |
| **Filter kernels** | `gpu/kernels/filters.py` | Backend-portable | FFT-based — needs pyfftw alternative |
| **RAW processing** | `utils/raw_file_processor.py` | rawpy + exiv2 + lensfunpy | Native C/C++ libs — need NDK builds |
| **IO** | `utils/io.py` | OpenImageIO | Heavy native dep — needs alternative |
| **GUI** | `spektrafilm_gui/` | PySide6/Qt | Not portable — rewrite UI |
| **HDR processing** | `utils/hdr_photo.py` | NumPy + colour-science | Portable |
| **Fast interp** | `utils/fast_interp.py` | Numba JIT | Needs Numba on Android or C rewrite |
| **FFT filter** | `utils/fft_gaussian_filter.py` | pyfftw | Needs pocketfft or Vulkan FFT |
| **Auto exposure** | `utils/autoexposure.py` | NumPy | Portable |

### Critical Dependencies

| Dependency | Type | Android Path | Difficulty |
|-----------|------|-------------|------------|
| `numpy~=2.4` | C extension | Chaquopy prebuilt | Easy |
| `scipy~=1.17` | C/Fortran | Chaquopy prebuilt | Easy |
| `colour-science~=0.4.6` | Pure Python | Chaquopy pip | Easy |
| `scikit-image~=0.26` | C extension | Chaquopy prebuilt | Medium |
| `opt-einsum~=3.4.0` | Pure Python | Chaquopy pip | Easy |
| `Pillow~=12.1` | C extension | Chaquopy prebuilt | Easy |
| `PyYAML~=6.0` | C extension | Chaquopy prebuilt | Easy |
| `lmfit~=1.3.2` | Pure Python | Chaquopy pip | Easy |
| `numba~=0.64` | LLVM JIT | **Very difficult** | Hard — needs LLVM on ARM |
| `OpenImageIO~=3.1.11` | Heavy C++ | NDK custom build | Hard |
| `pyfftw~=0.15.0` | C (FFTW3) | NDK build or replace | Medium |
| `rawpy~=0.26.1` | C++ (LibRaw) | NDK build | Medium |
| `exiv2~=0.18.1` | C++ | NDK build | Medium |
| `lensfunpy~=1.18.0` | C++ (lensfun) | NDK build | Medium |
| `napari~=0.6.6` | Qt viewer | **Not portable** | Skip — no viewer on mobile |
| `qtpy~=2.4` | Qt abstraction | **Not portable** | Replace with native Android UI |
| `pyside6~=6.9` | Qt bindings | **Not portable** | Replace with native Android UI |
| `matplotlib~=3.10` | Plotting | **Not portable** | Skip — not needed on mobile |
| `pyconify~=0.2.1` | Icon rendering | Pure Python | Easy |

### Verdict

~60% of the codebase (spectral models, colour science, pipeline logic) is pure
Python + NumPy and ports directly. The remaining ~40% is either native C/C++
libraries that need NDK builds or GUI code that needs complete rewriting.

---

## 2. Porting Strategies Comparison

### Strategy A: Python Wrapper (Chaquopy + Native UI)

**Concept**: Embed the Python runtime via Chaquopy, run the spectral pipeline
in Python, build the Android UI natively in Kotlin/Compose.

```
┌─────────────────────────────────────┐
│  Android App (Kotlin/Compose)       │
│  ┌───────────────────────────────┐  │
│  │  Native UI Layer              │  │
│  │  - Jetpack Compose views      │  │
│  │  - CameraX integration        │  │
│  │  - Material Design 3          │  │
│  └───────────┬───────────────────┘  │
│              │ Chaquopy bridge       │
│  ┌───────────▼───────────────────┐  │
│  │  Python Runtime (Chaquopy)    │  │
│  │  - spektrafilm pipeline       │  │
│  │  - numpy, scipy, colour       │  │
│  │  - rawpy, Pillow              │  │
│  └───────────┬───────────────────┘  │
│              │ JNI                   │
│  ┌───────────▼───────────────────┐  │
│  │  Native C/C++ (NDK)           │  │
│  │  - Vulkan compute backend     │  │
│  │  - OpenCV for transforms      │  │
│  │  - FFTW3 or pocketfft         │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
```

**Pros**:
- Reuses ~60% of existing Python code without modification
- colour-science, scipy, numpy all available via Chaquopy
- Native Android UI gives best user experience
- Incremental migration path: start Python, optimize hot paths to C++ later
- Python's dataclass-based param system works unchanged

**Cons**:
- Chaquopy adds ~30-50 MB to APK size (Python runtime + stdlib)
- Python execution is 5-50x slower than native for tight loops
- Numba JIT is extremely difficult to get working on ARM Android
- Cold start time penalty (Python interpreter initialization)
- Debugging across Python/Kotlin boundary is harder
- Two language ecosystems to maintain

**Performance estimate**: Pipeline processing 24MP image:
- Python/NumPy path: ~8-15 seconds (acceptable for batch, not real-time)
- With NDK C++ hot paths: ~2-4 seconds
- With Vulkan compute: ~0.5-1.5 seconds

### Strategy B: Native C++/Rust Core with Kotlin UI

**Concept**: Port the computational core to C++ or Rust, use Kotlin for UI,
communicate via JNI/FFI.

```
┌─────────────────────────────────────┐
│  Android App (Kotlin/Compose)       │
│  ┌───────────────────────────────┐  │
│  │  Native UI Layer              │  │
│  └───────────┬───────────────────┘  │
│              │ JNI / C FFI           │
│  ┌───────────▼───────────────────┐  │
│  │  Core Library (C++ or Rust)   │  │
│  │  - Spectral pipeline          │  │
│  │  - Colour science (port)      │  │
│  │  - GPU dispatch (Vulkan)      │  │
│  │  - NumPy-like array ops       │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
```

**Pros**:
- Best possible performance (10-100x faster than Python)
- Lower memory footprint (no Python interpreter)
- Deterministic memory management (Rust) or manual control (C++)
- Direct Vulkan integration without Python → C → GPU bridging
- Smaller APK size (~5-15 MB)

**Cons**:
- **Massive rewrite effort** — must port colour-science (15k+ lines),
  scipy functions, spectral upsampling, emulsion model
- colour-science is a complex library with no C equivalent
- Lose access to Python scientific ecosystem
- C++ memory safety bugs; Rust learning curve
- No hot-reload for parameter tuning
- Estimated 6-12 months of porting work

**Performance estimate**: Pipeline processing 24MP image:
- C++ with NEON: ~0.5-1.5 seconds
- Rust with SIMD: ~0.4-1.2 seconds
- With Vulkan compute offload: ~0.2-0.5 seconds

### Strategy C: Halide for Image Processing Kernels

**Concept**: Use Halide (embedded DSL for image processing) to generate
optimized CPU/GPU code from a single pipeline description.

```
┌─────────────────────────────────────┐
│  Android App (Kotlin/Compose)       │
│  ┌───────────┬───────────────────┐  │
│  │  Halide Pipeline (AOT)        │  │
│  │  - Film simulation kernels    │  │
│  │  - Auto-scheduled for ARM     │  │
│  │  - GPU offload (OpenCL/Vk)    │  │
│  └───────────┬───────────────────┘  │
│              │ Compiled .so          │
│  ┌───────────▼───────────────────┐  │
│  │  Kotlin glue + Vulkan compute │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
```

**Pros**:
- Write once, auto-schedule for CPU (ARM NEON) and GPU (OpenCL/Vulkan)
- Excellent for image processing pipelines (designed for this)
- AOT compilation to .so files — no JIT needed
- Proven on Android (Google uses Halide internally)

**Cons**:
- Halide is a separate language to learn
- Not suitable for all spectral operations (FFT, matrix decomposition)
- Would still need Python or C++ for the parametric model
- Smaller community than Python/C++
- Must port the colour-science library separately
- Limited to image-processing-style kernels (not general computation)

**Performance estimate**: Pipeline processing 24MP image:
- Halide CPU (ARM NEON, auto-scheduled): ~0.3-0.8 seconds
- Halide GPU (OpenCL): ~0.1-0.3 seconds

### Strategy D: Hybrid — Chaquopy + NDK + Vulkan (Recommended)

**Concept**: Combine strategies. Use Chaquopy for the Python pipeline
orchestration and colour-science library. Offload hot paths (spectral LUT
application, matrix transforms, Gaussian blur, FFT) to NDK C++ with Vulkan
compute shaders.

```
┌─────────────────────────────────────────────┐
│  Android App (Kotlin/Compose)               │
│  ┌───────────────────────────────────────┐  │
│  │  UI Layer (Jetpack Compose)           │  │
│  │  - Parameter sliders                  │  │
│  │  - Preview rendering                  │  │
│  │  - Gallery / export                   │  │
│  └───────────┬───────────────────────────┘  │
│              │ Chaquopy JNI bridge           │
│  ┌───────────▼───────────────────────────┐  │
│  │  Python Orchestration Layer           │  │
│  │  - params_schema (dataclasses)        │  │
│  │  - params_builder (digest)            │  │
│  │  - pipeline.py (orchestrator)         │  │
│  │  - colour-science (XYZ, RGB, etc.)    │  │
│  │  - model/ (emulsion, couplers, etc.)  │  │
│  └───────────┬───────────────────────────┘  │
│              │ ArrayBackend protocol          │
│  ┌───────────▼───────────────────────────┐  │
│  │  Android Backend (NDK C++)            │  │
│  │  - AndroidBackend(ArrayBackend)       │  │
│  │  - Vulkan compute shaders             │  │
│  │  - NEON-optimized kernels             │  │
│  │  - VkFFT for spectral FFT             │  │
│  └───────────┬───────────────────────────┘  │
│              │ Vulkan API                    │
│  ┌───────────▼───────────────────────────┐  │
│  │  GPU Hardware (Adreno/Mali/PowerVR)   │  │
│  └───────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

**Pros**:
- Reuses existing Python pipeline and colour-science code
- Hot paths get native/GPU performance via the existing ArrayBackend protocol
- Incremental: start with Python+NumPy backend, add Vulkan backend later
- colour-science library works unchanged
- Same zero-precision-loss guarantee (Vulkan compute with float32)
- Kotlin UI gives native Android experience

**Cons**:
- Complex build system (Gradle + Chaquopy + NDK + CMake + Vulkan)
- APK size ~60-80 MB (Python runtime + native libs)
- Still have Python cold-start penalty
- Three codebases to maintain (Kotlin UI, Python core, C++ GPU)

---

## 3. GPU Compute on Android

### 3.1 Vulkan Compute Shaders

**Status**: Vulkan 1.1+ is supported on 95%+ of active Android devices (2024+).
All major SoCs (Snapdragon 8 Gen 3, Exynos 2400, Dimensity 9300, Tensor G3,
Kirin 9000s) support compute shaders.

**Key capabilities**:
- `VK_QUEUE_COMPUTE_BIT` — dedicated compute queue
- `shaderStorageImageExtendedFormats` — wide-format storage images
- Shared memory: 16-32 KB per workgroup (mobile)
- Typical workgroup size: 128-256 invocations

**Vulkan compute pipeline for Spektrafilm**:

```glsl
// Example: 3x3 matrix multiply (RGB-to-XYZ conversion)
// Applied per-pixel across the full image
#version 450
layout(local_size_x = 16, local_size_y = 16) in;

layout(set = 0, binding = 0, rgba32f) uniform readonly image2D inputImg;
layout(set = 0, binding = 1, rgba32f) uniform writeonly image2D outputImg;
layout(set = 0, binding = 2) uniform Params {
    mat3 colorMatrix;  // e.g., RGB_to_XYZ matrix
    float padding;
} params;

void main() {
    ivec2 pos = ivec2(gl_GlobalInvocationID.xy);
    ivec2 size = imageSize(inputImg);
    if (pos.x >= size.x || pos.y >= size.y) return;

    vec4 pixel = imageLoad(inputImg, pos);
    vec3 rgb = pixel.rgb;
    vec3 result = params.colorMatrix * rgb;
    imageStore(outputImg, pos, vec4(result, pixel.a));
}
```

**LUT application shader** (core Spektrafilm operation):

```glsl
// 3D LUT application via trilinear interpolation
#version 450
layout(local_size_x = 16, local_size_y = 16) in;

layout(set = 0, binding = 0, rgba32f) uniform readonly image2D inputImg;
layout(set = 0, binding = 1, rgba32f) uniform writeonly image2D outputImg;
layout(set = 0, binding = 2) uniform sampler3D lutSampler;

layout(set = 0, binding = 3) uniform LUTParams {
    float lutScale;    // (resolution - 1) for normalization
    float lutOffset;
    float padding[2];
} lutParams;

void main() {
    ivec2 pos = ivec2(gl_GlobalInvocationID.xy);
    ivec2 size = imageSize(inputImg);
    if (pos.x >= size.x || pos.y >= size.y) return;

    vec4 pixel = imageLoad(inputImg, pos);
    // Normalize to LUT coordinates [0, 1]
    vec3 lutCoord = clamp(pixel.rgb, 0.0, 1.0);
    vec3 result = texture(lutSampler, lutCoord).rgb;
    imageStore(outputImg, pos, vec4(result, pixel.a));
}
```

**FFT-based Gaussian blur** (used for halation, diffusion, lens blur):

Vulkan does not have native FFT, but there are excellent libraries:
- **VkFFT** — Vulkan FFT library, very fast on mobile GPUs
- **cuFFT equivalent**: VkFFT provides similar API to cuFFT
- For separable Gaussian blur, a two-pass (horizontal + vertical) approach
  with compute shaders is often faster than FFT for small kernels

### 3.2 OpenGL ES 3.1 Compute Shaders

Broader compatibility than Vulkan (covers ~99% of devices), but:
- Higher dispatch overhead per kernel
- Less explicit memory control
- Still viable as a fallback

```glsl
// GLES 3.1 compute shader
#version 310 es
layout(local_size_x = 16, local_size_y = 16) in;
layout(rgba32f, binding = 0) uniform readonly highp image2D inputImg;
layout(rgba32f, binding = 1) uniform writeonly highp image2D outputImg;

void main() {
    ivec2 pos = ivec2(gl_GlobalInvocationID.xy);
    ivec2 size = imageSize(inputImg);
    if (pos.x >= size.x || pos.y >= size.y) return;
    vec4 pixel = imageLoad(inputImg, pos);
    // ... processing ...
    imageStore(outputImg, pos, pixel);
}
```

### 3.3 AGSL (Android Graphics Shading Language)

Introduced in Android 13 (API 33), AGSL is based on SkSL (Skia's shader
language). It is designed for UI shader effects and fragment shading, **not**
general-purpose compute. Limited utility for Spektrafilm's pipeline.

- Good for: real-time preview filters, colour grading effects in the UI
- Not good for: multi-pass spectral simulation, LUT computation, FFT
- Integration: via `RuntimeShader` in Jetpack Compose or `android.graphics.Paint`

### 3.4 RenderScript Status

RenderScript was **deprecated in Android 12 (API 31)** and is being removed.
Google's official migration path is:
1. **Compute workloads** → Vulkan compute shaders
2. **Image filters (UI)** → AGSL `RuntimeShader`
3. **Simple intrinsics (blur, etc.)** → AGSL or OpenGL ES

### 3.5 Recommended GPU Strategy for Spektrafilm

**Primary**: Vulkan compute shaders for all array operations:
- Matrix multiplication (3x3 colour transforms)
- LUT trilinear interpolation
- Per-pixel math (exp, log10, pow, clip, where)
- Gaussian blur (separable or FFT via VkFFT)
- Spectral summation (einsum equivalent via reduction)

**Fallback**: CPU via NumPy (the existing `NumpyBackend`)

**Why not OpenGL ES**: Vulkan's explicit control over memory and synchronization
is critical for Spektrafilm's zero-precision-loss requirement. GLES has more
implicit driver behavior that can introduce subtle differences.

### 3.6 Vulkan Backend Implementation Sketch

```python
# New file: src/spektrafilm/gpu/vulkan_backend.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass(slots=True)
class VulkanBackend:
    """Vulkan compute backend for Android.

    Wraps an NDK C++ Vulkan compute engine via JNI. The C++ side manages
    VkDevice, VkQueue, VkCommandBuffer, and compute pipelines. Operations
    are dispatched as Vulkan compute dispatches.

    Requires: libvulkan.so (Android 7.0+), VK_KHR_get_physical_device_properties2
    """

    name: str = "vulkan"
    supports_gpu: bool = True
    fallback_reason: str | None = None
    requires_serial_runtime: bool = False

    def __init__(self, *, precision: str = "float32"):
        self._precision = precision
        # JNI bridge to C++ Vulkan engine
        # self._engine = _init_vulkan_engine()

    def asarray(self, value: Any, dtype: Any | None = None) -> Any:
        """Upload array to GPU VkBuffer."""
        # ... JNI call to upload ...
        ...

    def to_numpy(self, value: Any) -> Any:
        """Download array from GPU to NumPy."""
        # ... JNI call to download ...
        ...

    def matmul(self, a: Any, b: Any) -> Any:
        """Dispatch Vulkan compute shader for matrix multiply."""
        # Dispatch vk_matmul.comp shader
        ...

    def exp(self, x: Any) -> Any:
        """Dispatch Vulkan compute shader for element-wise exp."""
        # Dispatch vk_elementwise.comp with EXP opcode
        ...

    # ... other ArrayBackend methods ...
```

---

## 4. Color Management on Android

### 4.1 Android ColorSpace API (API 24+)

Android provides a comprehensive `android.graphics.ColorSpace` class with
pre-defined named colour spaces relevant to Spektrafilm:

| Named Color Space | Primaries | Transfer Function | Spektrafilm Use |
|---|---|---|---|
| `SRGB` | sRGB (D65) | sRGB OETF | Default export target |
| `LINEAR_SRGB` | sRGB (D65) | Linear | Scene-linear interchange |
| `EXTENDED_SRGB` | sRGB (D65) | sRGB (extended range) | HDR preview intermediate |
| `DISPLAY_P3` | DCI-P3 (D65) | sRGB OETF | **Primary preview target** |
| `DCI_P3` | DCI-P3 (DCI white) | Gamma 2.6 | Cinema reference |
| `BT2020` | BT.2020 (D65) | BT.2020 OETF | Wide-gamut export |
| `BT2020_PQ` | BT.2020 (D65) | PQ (ST 2084) | **HDR10 export target** |
| `BT2020_HLG` | BT.2020 (D65) | HLG | Broadcast HDR export |

**Colour space conversion** uses CIE XYZ as the profile connection space:
```kotlin
// Convert Spektrafilm ACEScg output to Display P3 for preview
val connector = ColorSpace.connect(
    ColorSpace.get(ColorSpace.Named.LINEAR_SRGB),  // ACEScg is scene-linear
    ColorSpace.get(ColorSpace.Named.DISPLAY_P3)
)
val displayP3Pixel = connector.transform(acesR, acesG, acesB)
```

### 4.2 Display Colour Modes & HDR

**Activity-level opt-in** (manifest or runtime):
```xml
<activity
    android:name=".EditActivity"
    android:hasWideColorGamut="true"
    android:colorMode="wideColorGamut" />
```

**Runtime display query**:
```kotlin
val display = windowManager.defaultDisplay
val isWideGamut = display.isWideColorGamut()      // API 26+
val isHdr = display.isHdr()                         // API 26+
val hdrCaps = display.hdrCapabilities               // HDR10, HLG, HDR10+, Dolby Vision
```

**Window HDR headroom** (API 34+):
```kotlin
// Request HDR rendering with specified headroom ratio
window.setDesiredHdrHeadroom(2.0f)  // 2x SDR white = ~406 nits peak
```

**Display colour mode constants** (`ActivityInfo`):
- `COLOR_MODE_WIDE_COLOR_GAMUT` (1) — Display P3 gamut
- `COLOR_MODE_HDR` (2) — HDR rendering
- `COLOR_MODE_HDR10` (3) — HDR10 specifically (10-bit PQ)

### 4.3 Native HDR Pipeline (AOSP SurfaceComposer)

The native compositor supports HDR via:
- **Dataspace**: `ADATASPACE_DISPLAY_P3`, `ADATASPACE_BT2020_PQ`, `ADATASPACE_BT2020_HLG`
- **HDR metadata**: Static (MaxCLL, MaxFALL, mastering display) via `setHdrMetadata()`
- **HDR headroom**: `setDesiredHdrHeadroom(ratio)` controls HDR/SDR brightness ratio
- **Colour-space agnostic mode**: `setColorSpaceAgnostic(true)` for custom pipeline control

### 4.4 EGL Extensions for Wide Gamut

When rendering via Vulkan or OpenGL ES:
- `EGL_GL_COLORSPACE_SRGB_KHR` — sRGB framebuffer
- `EGL_GL_COLORSPACE_DISPLAY_P3_EXT` — Display P3 framebuffer
- `EGL_GL_COLORSPACE_BT2020_PQ_EXT` — BT.2020 PQ (HDR10)
- `EGL_GL_COLORSPACE_BT2020_HLG_EXT` — BT.2020 HLG

### 4.5 Colour Science on Android via Chaquopy

The `colour-science` Python library works on Android via Chaquopy:

```python
# This runs on Android via Chaquopy
import colour
import numpy as np

# All colour-science functions work:
xyz = colour.RGB_to_XYZ(rgb, "ACEScg", apply_cctf_decoding=False)
display_p3 = colour.RGB_to_RGB(xyz, "ACEScg", "Display P3")
```

**ICC Profile handling**: Spektrafilm uses ICC profiles for output encoding.
On Android, ICC profiles can be embedded in output files but Android's display
compositor handles the final conversion. The pipeline should output in the
target colour space (sRGB or Display P3) and let Android handle display
management.

### 4.6 Wide Gamut Considerations for Spektrafilm

The pipeline currently supports ACEScg as a working space. On Android:

1. **Preview rendering**: Output in Display P3 (wider than sRGB, commonly
   supported on flagship Android devices since API 24)
2. **HDR preview**: Use `BT2020_PQ` dataspace with `window.setDesiredHdrHeadroom()`
   for HDR rendition preview
3. **Export**: Support sRGB (universal), Display P3, BT.2020 PQ (HDR10),
   and ACES2065-1 (EXR)
4. **ICC profiles**: Embed ICC profiles in exported images using the existing
   `_ICC_PROFILES` / `_ICC_FILENAMES` system
5. **HDR display**: Use Android's HDR10 pipeline (`COLOR_MODE_HDR10`) for
   HDR rendition mode, setting PQ transfer function matching Spektrafilm's
   HDR scene energy metadata
6. **Transfer functions**: BT.2020 PQ uses ST 2084 (absolute luminance, up to
   10,000 nits); BT.2020 HLG uses hybrid log-gamma (SDR whitepoint 203 nits)

---

## 5. RAW/DNG Processing on Mobile

### 5.1 Camera2/CameraX RAW Capture

Android supports RAW capture via:

**Camera2 API** (lower-level, more control):
```kotlin
// Request RAW capture
val captureRequest = camera.createCaptureRequest(
    CameraDevice.TEMPLATE_STILL_CAPTURE
).apply {
    set(CaptureRequest.STATISTICS_LENS_SHADING_MAP_MODE,
        CaptureRequest.STATISTICS_LENS_SHADING_MAP_MODE_ON)
    // Request RAW_SENSOR output
    addTarget(rawImageReader.surface)
}

// RAW_SENSOR format: Bayer-pattern sensor data
// RAW10: 10-bit packed Bayer (more common)
// RAW12: 12-bit Bayer (higher quality)
```

**CameraX** (higher-level, easier):
```kotlin
// CameraX with RAW capture (CameraX 1.4+)
val imageCapture = ImageCapture.Builder()
    .setCaptureMode(ImageCapture.CAPTURE_MODE_MAXIMIZE_QUALITY)
    .build()

// CameraX RAW extension (requires CameraX 1.4+)
val rawCapture = RawImageCapture.Builder().build()
```

### 5.2 DNG File Handling

**Writing DNG on Android**:
```kotlin
// Use Adobe DNG SDK or custom DNG writer
// DNG is TIFF-based with specific tags
fun writeDng(
    rawSensorData: ByteArray,
    width: Int,
    height: Int,
    bayerPattern: Int,  // RGGB, BGGR, etc.
    blackLevel: IntArray,
    whiteLevel: Int,
    colorMatrix: FloatArray,  // 3x3 from CameraCharacteristics
    outputPath: String
) {
    // Write TIFF IFD with DNG-specific tags:
    // - Tag 0xC612: DNGVersion
    // - Tag 0xC614: UniqueCameraModel
    // - Tag 0xC68D: BlackLevel
    // - Tag 0xC68E: WhiteLevel
    // - Tag 0xC621: ColorMatrix1
}
```

### 5.3 LibRaw on Android

LibRaw (used by Python's `rawpy`) can be built for Android via NDK:

```cmake
# CMakeLists.txt for LibRaw on Android
cmake_minimum_required(VERSION 3.18)
project(rawkit)

set(CMAKE_CXX_STANDARD 17)

# Build LibRaw from source
add_subdirectory(libraw)

# JNI bridge
add_library(rawkit SHARED rawkit_jni.cpp)
target_link_libraries(rawkit raw_static)
target_link_libraries(rawkit jnigraphics)  # For Android Bitmap
```

**Alternative**: Use Android's built-in `android.media.ImageReader` with
`ImageFormat.RAW_SENSOR` for capture, and process the Bayer data directly
with custom C++ code instead of LibRaw.

### 5.4 Spektrafilm RAW Processing Requirements

The current `raw_file_processor.py` uses:
- `rawpy` — LibRaw wrapper for RAW decoding
- `exiv2` — EXIF/metadata reading
- `lensfunpy` — lens distortion correction
- `colour-science` — colour space conversions

For Android, the recommended approach:
1. **Capture**: Use CameraX/Camera2 for RAW_SENSOR capture
2. **Decode**: Build LibRaw via NDK, or use Android's DNG Creator API
   (`android.media.ImageWriter` + DNG metadata)
3. **Metadata**: Use Android's `ExifInterface` (supports DNG tags since API 24)
4. **Lens correction**: Build lensfun via NDK, or use Android's
   `CameraCharacteristics` for per-lens distortion data
5. **Colour**: Use the existing colour-science library via Chaquopy

---

## 6. Architecture Recommendations

### 6.1 Recommended Layered Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    Android Application Layer                   │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  Jetpack Compose UI                                     │ │
│  │  ├── FilmStockSelector (presets grid)                   │ │
│  │  ├── ParameterControls (sliders, color pickers)         │ │
│  │  ├── ImagePreview (real-time rendered preview)          │ │
│  │  ├── ExportDialog (format, quality, ICC profile)        │ │
│  │  └── GalleryView (processed images)                     │ │
│  └───────────────────────┬─────────────────────────────────┘ │
│                          │ ViewModel / StateFlow              │
│  ┌───────────────────────▼─────────────────────────────────┐ │
│  │  Processing Service (Kotlin)                            │ │
│  │  ├── ChaquopyBridge — Python lifecycle management       │ │
│  │  ├── ImageRepository — load/cache/encode images         │ │
│  │  ├── ProgressTracker — pipeline progress callbacks      │ │
│  │  └── ExportManager — background export with WorkManager │ │
│  └───────────────────────┬─────────────────────────────────┘ │
│                          │ Chaquopy JNI                       │
│  ┌───────────────────────▼─────────────────────────────────┐ │
│  │  Python Pipeline (Chaquopy)                             │ │
│  │  ├── params_schema — dataclass definitions              │ │
│  │  ├── params_builder — digest_params, init_params        │ │
│  │  ├── pipeline — SimulationPipeline orchestrator         │ │
│  │  ├── stages/ — Filming, Printing, Scanning              │ │
│  │  ├── model/ — Emulsion, Couplers, Diffusion, Grain      │ │
│  │  ├── colour-science — XYZ, RGB, adaptation matrices     │ │
│  │  └── utils/ — spectral upsampling, LUT, auto-exposure   │ │
│  └───────────────────────┬─────────────────────────────────┘ │
│                          │ ArrayBackend protocol              │
│  ┌───────────────────────▼─────────────────────────────────┐ │
│  │  Compute Backends                                       │ │
│  │  ├── NumpyBackend — fallback, NumPy + opt-einsum        │ │
│  │  ├── VulkanBackend — NDK C++, VkBuffer, compute shaders │ │
│  │  └── (future) GLESBackend — OpenGL ES 3.1 fallback      │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

### 6.2 Processing Modes

| Mode | Resolution | Backend | Use Case |
|------|-----------|---------|----------|
| **Preview** | ~1 MP | Vulkan | Real-time slider feedback |
| **Standard** | Up to 12 MP | Vulkan or CPU | Normal photo processing |
| **Full quality** | 24-48 MP | Vulkan (tiled) | Export with full quality |
| **Batch** | Multiple images | CPU (background) | Process gallery |

### 6.3 Non-Destructive Editing

Following the Snapseed/Lightroom model:

```kotlin
// Edit recipe — stored as JSON, applied on-demand
data class EditRecipe(
    val version: Int = 1,
    val filmStock: String = "kodak_portra_400",
    val params: RuntimePhotoParams,  // From params_schema.py
    val crop: CropRegion? = null,
    val timestamp: Long = System.currentTimeMillis()
)

// Storage: just the recipe, never the processed pixels
// Re-render on demand: recipe → pipeline → output pixels
```

### 6.4 Preview Pipeline

For real-time preview (slider feedback at 30+ FPS):

1. **Downsample** input to ~1 MP (fast bilinear on GPU)
2. **Run pipeline** on downsampled image (Python + Vulkan backend)
3. **Upscale** result to display size (GPU bilinear)
4. **Cache** result keyed by parameter hash

With Vulkan backend, a 1 MP preview takes ~30-80ms, enabling real-time
slider interaction.

---

## 7. Performance Considerations

### 7.1 Memory Budget

| Component | Typical Budget | Spektrafilm Estimate |
|-----------|---------------|---------------------|
| OS + system services | 2-3 GB | 2-3 GB |
| App UI layer | 100-200 MB | 150 MB |
| Python runtime | 50-100 MB | 80 MB |
| Pipeline buffers (24MP) | 200-400 MB | 300 MB |
| Vulkan GPU memory | 200-500 MB | 400 MB |
| Spectral LUT tables | 50-200 MB | 100 MB |
| **Total** | | **~1 GB** |

Typical Android devices have 6-16 GB RAM, with 2-4 GB available to a single
app. Spektrafilm's 1 GB estimate is feasible but tight.

**Mitigation strategies**:
- **Tiled processing**: Process in 2M-pixel tiles (existing `_should_tile_gpu_image`)
- **LUT quantization**: Reduce LUT resolution from 256 to 128 for preview
- **Memory-mapped LUTs**: Use `mmap()` for LUT tables to allow OS paging
- **Explicit cleanup**: Call `del image` + `gc.collect()` between pipeline stages
  (the pipeline already does this in `_pipeline_scan_film`)

### 7.2 Battery & Thermal

| Operation | Power Draw | Duration (24MP) | Thermal Impact |
|-----------|-----------|-----------------|----------------|
| Vulkan compute pipeline | High (GPU) | 0.5-1.5s | Brief spike |
| Python orchestration | Medium (CPU) | 1-3s | Moderate |
| FFT (pyfftw) | High (CPU+NEON) | 0.5-1s | Moderate |
| Full pipeline (GPU) | High | 2-4s | Brief spike |
| Full pipeline (CPU) | Medium | 8-15s | Sustained moderate |

**Thermal throttling mitigation**:
- Process in tiles with `synchronize()` calls between tiles (already done)
- Add yield points: `Thread.sleep(1)` between tiles to let SoC cool
- Show progress indicator so user understands processing time
- Use `PowerManager.isThermalStatusSupported()` to detect thermal pressure
- Reduce processing quality when thermal throttling detected

### 7.3 Python Interpreter Overhead

| Phase | Time | Notes |
|-------|------|-------|
| Interpreter cold start | 0.5-1.5s | One-time per app launch |
| Module imports (first time) | 1-3s | colour-science, scipy, numpy |
| Module imports (cached) | 0.1-0.3s | Subsequent imports |
| Pipeline init | 0.5-1s | LUT precomputation, backend init |
| Per-image processing | 2-4s | Actual computation |

**Optimization**: Keep the Python process alive across image processing
sessions. Initialize once, process many images.

### 7.4 APK Size Budget

| Component | Size |
|-----------|------|
| Python runtime + stdlib | 20-30 MB |
| numpy + scipy + colour-science | 30-50 MB |
| Native C++ libs (Vulkan engine) | 2-5 MB |
| LibRaw + lensfun + exiv2 | 3-5 MB |
| Kotlin/Compose UI + resources | 5-10 MB |
| Spektrafilm Python code + data | 2-5 MB |
| **Total** | **62-105 MB** |

This is within acceptable range for a photo processing app (Lightroom Mobile
is ~150 MB, Snapseed ~30 MB).

---

## 8. Build System Setup

### 8.1 Gradle Configuration

```kotlin
// build.gradle.kts (app-level)
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python") version "16.0.0"  // Chaquopy
}

android {
    namespace = "com.spektrafilm.android"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.spektrafilm.android"
        minSdk = 26  // Android 8.0 — wide gamut + Vulkan
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"

        ndk {
            abiFilters += listOf("arm64-v8a", "armeabi-v7a")
        }

        // Chaquopy Python configuration
        python {
            version = "3.11"  // Chaquopy supports 3.8-3.11
            pip {
                install("numpy")
                install("scipy")
                install("colour-science")
                install("Pillow")
                install("opt-einsum")
                install("PyYAML")
                install("lmfit")
                install("pyconify")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }

    externalNativeBuild {
        cmake {
            path = file("src/main/cpp/CMakeLists.txt")
            version = "3.22.1"
        }
    }
}
```

### 8.2 CMake for NDK Components

```cmake
# src/main/cpp/CMakeLists.txt
cmake_minimum_required(VERSION 3.22)
project(spektrafilm_native)

set(CMAKE_CXX_STANDARD 20)

# Find Vulkan
find_package(Vulkan REQUIRED)

# VkFFT (header-only FFT library for Vulkan)
add_subdirectory(third_party/vkfft)

# LibRaw (RAW file processing)
add_subdirectory(third_party/LibRaw)

# lensfun (lens correction)
add_subdirectory(third_party/lensfun)

# Our Vulkan compute engine
add_library(spekfilm_vulkan SHARED
    vulkan_engine.cpp
    vulkan_compute.cpp
    vulkan_buffers.cpp
    shaders/compiled/matmul.comp.spv
    shaders/compiled/lut_interp.comp.spv
    shaders/compiled/gaussian_blur.comp.spv
    shaders/compiled/elementwise.comp.spv
)

target_link_libraries(spekfilm_vulkan
    Vulkan::Vulkan
    VkFFT
    android
    log
)

# RAW processing bridge
add_library(spekfilm_raw SHARED
    raw_processor_jni.cpp
)

target_link_libraries(spekfilm_raw
    raw_static
    lensfun
    jnigraphics
    android
    log
)

# Compile GLSL compute shaders to SPIR-V
find_program(GLSLC glslc)

set(SHADER_DIR ${CMAKE_CURRENT_SOURCE_DIR}/shaders)
set(SPIRV_DIR ${CMAKE_CURRENT_SOURCE_DIR}/shaders/compiled)

file(GLOB SHADERS ${SHADER_DIR}/*.comp)
foreach(SHADER ${SHADERS})
    get_filename_component(SHADER_NAME ${SHADER} NAME)
    set(SPIRV ${SPIRV_DIR}/${SHADER_NAME}.spv)
    add_custom_command(
        OUTPUT ${SPIRV}
        COMMAND ${GLSLC} ${SHADER} -o ${SPIRV}
        DEPENDS ${SHADER}
    )
    list(APPEND SPIRV_FILES ${SPIRV})
endforeach()
```

### 8.3 Project Structure

```
spektrafilm-android/
├── app/
│   ├── build.gradle.kts
│   └── src/main/
│       ├── java/com/spektrafilm/android/
│       │   ├── SpektrafilmApp.kt          # Application class
│       │   ├── MainActivity.kt
│       │   ├── ui/
│       │   │   ├── theme/Theme.kt
│       │   │   ├── screens/
│       │   │   │   ├── HomeScreen.kt
│       │   │   │   ├── EditScreen.kt
│       │   │   │   ├── ExportScreen.kt
│       │   │   │   └── GalleryScreen.kt
│       │   │   └── components/
│       │   │       ├── FilmStockCard.kt
│       │   │       ├── ParameterSlider.kt
│       │   │       └── ImagePreview.kt
│       │   ├── viewmodel/
│       │   │   └── EditViewModel.kt
│       │   ├── service/
│       │   │   ├── PythonBridge.kt        # Chaquopy bridge
│       │   │   ├── ImageRepository.kt
│       │   │   └── ExportWorker.kt
│       │   └── data/
│       │       ├── EditRecipe.kt
│       │       └── FilmStockPreset.kt
│       ├── cpp/
│       │   ├── CMakeLists.txt
│       │   ├── vulkan_engine.cpp
│       │   ├── vulkan_compute.cpp
│       │   ├── raw_processor_jni.cpp
│       │   └── shaders/
│       │       ├── matmul.comp
│       │       ├── lut_interp.comp
│       │       ├── gaussian_blur.comp
│       │       └── elementwise.comp
│       ├── python/                       # Spektrafilm Python code
│       │   └── spektrafilm/
│       │       ├── __init__.py
│       │       ├── pipeline.py
│       │       ├── model/
│       │       ├── gpu/
│       │       │   ├── backend.py
│       │       │   ├── numpy_backend.py
│       │       │   └── vulkan_backend.py  # New Android backend
│       │       └── ...
│       └── AndroidManifest.xml
├── build.gradle.kts                       # Root build file
├── settings.gradle.kts
└── gradle.properties
```

### 8.4 Chaquopy Integration Details

```kotlin
// PythonBridge.kt — Chaquopy integration
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform

class PythonBridge(private val context: Context) {
    private val python: Python by lazy {
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(context))
        }
        Python.getInstance()
    }

    private val module by lazy {
        python.getModule("spektrafilm_android_bridge")
    }

    fun processImage(
        inputPath: String,
        params: EditRecipe,
        onProgress: (Float) -> Unit
    ): String {
        return module.callAttr(
            "process_image",
            inputPath,
            params.toPythonDict(),
            object : PyObject.Callback {
                override fun call(vararg args: PyObject): PyObject {
                    onProgress(args[0].toFloat())
                    return PyObject.fromJava(null)
                }
            }
        ).toString()
    }
}
```

```python
# spektrafilm_android_bridge.py — Python bridge module
"""Android bridge for Spektrafilm pipeline."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from spektrafilm.runtime.api import simulate, RuntimePhotoParams
from spektrafilm.runtime.params_builder import init_params, digest_params


def process_image(
    input_path: str,
    params_json: str,
    progress_callback=None,
) -> str:
    """Process an image and return the output path.

    Called from Kotlin via Chaquopy.
    """
    # Load image
    img = np.array(Image.open(input_path), dtype=np.float32) / 255.0

    # Parse params
    params_dict = json.loads(params_json)
    params = _dict_to_params(params_dict)
    params = digest_params(params)

    # Process
    if progress_callback:
        progress_callback(0.1)

    result = simulate(img, params)

    if progress_callback:
        progress_callback(0.9)

    # Save output
    output_path = str(Path(input_path).parent / "output.png")
    output_img = np.clip(result * 255, 0, 255).astype(np.uint8)
    Image.fromarray(output_img).save(output_path)

    if progress_callback:
        progress_callback(1.0)

    return output_path
```

---

## 9. Recommended Approach

### Phase 1: Proof of Concept (2-3 weeks)

**Goal**: Run the Spektrafilm pipeline on Android with the CPU backend.

1. Set up Android project with Chaquopy
2. Port Python dependencies (numpy, scipy, colour-science, Pillow)
3. Create `spektrafilm_android_bridge.py` as the entry point
4. Use `NumpyBackend` (CPU) initially
5. Test with a small image (~1 MP) to verify correctness
6. Verify: output matches desktop Python output (bit-identical for float32)

**Deliverable**: APK that processes a photo and saves the result.

### Phase 2: Native UI (2-3 weeks)

1. Build Jetpack Compose UI with Material Design 3
2. Film stock selector with preset thumbnails
3. Parameter sliders (exposure, filters, grain, etc.)
4. Image preview with downsampled rendering
5. Gallery view for processed images
6. Export with format selection (JPEG, PNG, HEIF)

### Phase 3: Vulkan Backend (4-6 weeks)

1. Set up Vulkan compute infrastructure in NDK C++
2. Implement `ArrayBackend` operations as compute shaders:
   - `matmul` — matrix multiply
   - `exp`, `log10`, `pow`, `clip` — elementwise ops
   - `einsum` — specialized reduction kernels
   - `where`, `maximum`, `fmax` — conditional ops
3. Implement LUT trilinear interpolation shader
4. Implement separable Gaussian blur shader
5. Implement VkFFT integration for FFT-based filters
6. Create `VulkanBackend` Python class with JNI bridge
7. Test: `np.allclose(vulkan_result, numpy_result, atol=1e-6)`

### Phase 4: RAW Capture (2-3 weeks)

1. Integrate CameraX for photo capture
2. Build LibRaw via NDK for RAW decoding
3. Integrate lensfun for lens correction
4. Add RAW → pipeline data path
5. Support DNG import from external apps

### Phase 5: Optimization (2-3 weeks)

1. Profile and optimize hot paths
2. Implement tiled processing for large images
3. Add preview caching (parameter hash → rendered bitmap)
4. Optimize Python cold start (pre-import, module caching)
5. Memory profiling and optimization
6. Thermal throttling detection and adaptive quality

### Phase 6: Polish (2-3 weeks)

1. HDR display support (Display P3 output, HDR10 metadata)
2. ICC profile embedding in exports
3. Batch processing mode
4. Share intent integration
5. Dark mode / dynamic colour theming
6. App bundle optimization (remove unused ABIs)

### Total Estimated Timeline: 14-21 weeks (3.5-5 months)

---

## Appendix A: Key References

### Android Development
- [Android NDK Vulkan Guide](https://developer.android.com/ndk/guides/graphics/getting-started)
- [Android GPU Compute](https://developer.android.com/develop/background-work/gpu-compute)
- [Chaquopy Documentation](https://chaquo.com/chaquopy/doc/current/)
- [CameraX Documentation](https://developer.android.com/training/camerax)
- [Android Wide Color Gamut](https://developer.android.com/training/wide-color-gamut)

### Vulkan Compute
- [Khronos Vulkan Guide — Compute](https://docs.vulkan.org/guide/latest/compute.html)
- [VkFFT Library](https://github.com/DTolm/VkFFT)
- [Sascha Willems Vulkan Examples](https://github.com/SaschaWillems/Vulkan)
- [Android GPU Inspector](https://gpuinspector.dev/)

### Image Processing on Mobile
- [Snapseed Architecture (Google)](https://engineering.fb.com/)
- [Lightroom Mobile Architecture (Adobe)](https://developer.adobe.com/xmp/)
- [GPUImage (iOS/Android)](https://github.com/BradLarson/GPUImage)
- [Halide Language](https://halide-lang.org/)

### Python on Android
- [Kivy Framework](https://kivy.org/doc/stable/guide/android.html)
- [BeeWare Project](https://beeware.org)
- [Chaquopy GitHub](https://github.com/chaquopy/chaquopy)

---

## Appendix B: Risk Matrix

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Chaquopy can't run colour-science | Low | Critical | Test early in Phase 1; fallback to C++ port |
| Vulkan not available on target device | Low | High | CPU fallback via NumpyBackend |
| Python cold start too slow | Medium | Medium | Keep interpreter alive; pre-warm imports |
| Memory pressure causes OOM | Medium | High | Tiled processing; aggressive buffer reuse |
| Numba code paths don't work on ARM | High | Medium | Replace with C++ NDK implementations |
| FFT performance inadequate | Low | Medium | Use VkFFT; fall back to separable blur |
| APK size exceeds Play Store limit | Low | Low | App Bundle; ABI splitting |
| Thermal throttling during processing | Medium | Medium | Adaptive quality; yield between tiles |
| colour-science API changes break bridge | Low | Low | Pin version; integration tests |
| Vulkan driver bugs on specific SoCs | Medium | Medium | Per-device testing; CPU fallback |

---

## Appendix C: Dependency Migration Map

```
Desktop Python          →  Android (Chaquopy)      →  Android (NDK C++)
─────────────────────────────────────────────────────────────────────────
numpy                   →  numpy (Chaquopy prebuilt)
scipy                   →  scipy (Chaquopy prebuilt)
colour-science          →  colour-science (pip)
Pillow                  →  Pillow (Chaquopy prebuilt)
opt-einsum              →  opt-einsum (pip)
PyYAML                  →  PyYAML (Chaquopy prebuilt)
lmfit                   →  lmfit (pip)
numba                   →  ❌ (replace with C++)    →  NEON intrinsics
OpenImageIO             →  ❌ (replace)             →  Custom OIIO-lite or PIL
pyfftw                  →  ❌ (replace)             →  VkFFT or pocketfft
rawpy                   →  ❌ (build via NDK)       →  LibRaw
exiv2                   →  ❌ (build via NDK)       →  exiv2
lensfunpy               →  ❌ (build via NDK)       →  lensfun
napari                  →  ❌ (not needed)
qtpy / PySide6          →  ❌ (replace with Kotlin)
matplotlib              →  ❌ (not needed)
pyconify                →  pyconify (pip)
scikit-image            →  scikit-image (Chaquopy)  →  OpenCV or custom
```
