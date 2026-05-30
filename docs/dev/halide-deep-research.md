# Halide Deep Research for Spektrafilm Android Port

**Date:** 2026-05-27
**Purpose:** Comprehensive reference for porting Spektrafilm's spectral film simulation to C++/Halide on Android ARM

---

## Table of Contents

1. [Halide Real-World Projects](#1-halide-real-world-projects)
2. [Schedule Optimization](#2-schedule-optimization)
3. [AOT Compilation with CMake for Android ARM](#3-aot-compilation-with-cmake-for-android-arm)
4. [Python Bindings](#4-python-bindings)
5. [Gaussian Blur / Separable Convolution](#5-gaussian-blur--separable-convolution)
6. [3D LUT Trilinear Interpolation](#6-3d-lut-trilinear-interpolation)
7. [IIR Filter: Young-van Vliet](#7-iir-filter-young-van-vliet)
8. [FFT Integration](#8-fft-integration)
9. [Random Number Generation](#9-random-number-generation)
10. [Autoscheduler Comparison](#10-autoscheduler-comparison)
11. [Common Pitfalls](#11-common-pitfalls)
12. [Vulkan Compute on Android](#12-vulkan-compute-on-android)
13. [Spektrafilm-Specific Halide Code Examples](#13-spektrafilm-specific-halide-code-examples)

---

## 1. Halide Real-World Projects

### 1.1 Official Examples and Tutorials

The Halide repository (`github.com/halide/Halide`) ships ~20 tutorial lessons covering every major concept. Key lessons:

- **Lesson 05**: Vectorize, parallelize, unroll, and tile
- **Lesson 08**: Scheduling multi-stage pipelines (producer-consumer fusion)
- **Lesson 09**: Update definitions and reductions (histogram, box blur)
- **Lesson 13**: Tuples (multi-valued Funcs, argmax/argmin)
- **Lesson 15**: Generators (AOT compilation encapsulation)
- **Lesson 18**: `rfactor` for parallelizing associative reductions
- **Lesson 21**: Auto-scheduler integration

Reference: `https://halide-lang.org/tutorials/`

### 1.2 Notable Open-Source Projects Using Halide

| Project | Description | Repository |
|---------|-------------|------------|
| **Arm.Halide.AndroidDemo** | Halide AOT on Android with JNI, CMake, NDK | `github.com/dawidborycki/Arm.Halide.AndroidDemo` |
| **Arm.Halide.Hello-World** | Minimal Halide + OpenCV example for ARM | `github.com/dawidborycki/Arm.Halide.Hello-World` |
| **Halide apps/** | Camera pipe, bilateral histogram, local Laplacian, NLMeans | `github.com/halide/Halide/tree/main/apps` |
| **halide-sparse** | Sparse matrix operations in Halide | Academic project |
| **OpenCV DNN Halide backend** | Halide as a backend for OpenCV's deep learning module | `opencv/modules/dnn` |

### 1.3 Adobe and Google Usage

Halide was created at MIT/Adobe (2012). Adobe uses it in production for Photoshop image processing kernels. Google has contributed significantly to the compiler (LLVM backend, autoschedulers). The language is maintained by the Halide team at Google.

### 1.4 Key Architectural Patterns from Real Projects

From the Arm Android Demo (`dawidborycki/Arm.Halide.AndroidDemo`):

```
# CMakeLists.txt pattern for Android
cmake_minimum_required(VERSION 3.20)
project(HalideAndroidDemo)

find_package(Halide REQUIRED)

# AOT-compile the generator for ARM64
add_halide_library(halide_pipeline FROM halide_generator
    GENERATOR pipeline_generator
    PARAMS target=arm-64-android
    FUNCTION_NAME pipeline
)

# JNI shared library
add_library(native-lib SHARED native-lib.cpp)
target_link_libraries(native-lib PRIVATE halide_pipeline)
```

The JNI bridge passes `AHardwareBuffer` or `DirectByteBuffer` pointers as `halide_buffer_t` structs.

---

## 2. Schedule Optimization

### 2.1 Core Scheduling Primitives

Halide's power comes from the algorithm/schedule separation. The schedule controls *how* the algorithm executes without changing *what* it computes.

#### Tiling

Splits both x and y into outer/inner pairs, enabling cache-friendly traversal:

```cpp
Var x_outer, y_outer, x_inner, y_inner;
gradient.tile(x, y, x_outer, y_outer, x_inner, y_inner, 64, 64);
```

Equivalent C:
```c
for (y_outer = 0; y_outer < H/64; y_outer++)
  for (x_outer = 0; x_outer < W/64; x_outer++)
    for (y_inner = 0; y_inner < 64; y_inner++)
      for (x_inner = 0; x_inner < 64; x_inner++)
        // process pixel at (x_outer*64 + x_inner, y_outer*64 + y_inner)
```

#### Vectorization

Replaces inner loop with SIMD instructions (NEON on ARM, SSE on x86):

```cpp
gradient.vectorize(x, 4);  // split x by 4, vectorize inner
```

On ARM this generates NEON `float32x4_t` operations. On x86, SSE `__m128`.

**ARM-specific**: Use `natural_vector_size<float>()` which returns 4 for ARM NEON (128-bit registers / 32-bit float = 4 lanes).

#### Parallelism

Distributes independent work across threads:

```cpp
gradient.parallel(y);  // each scanline runs on a different thread
```

Best practice: fuse tile indices into a single parallel dimension to avoid nested parallelism:

```cpp
Var tile_index;
gradient.tile(x, y, x_outer, y_outer, x_inner, y_inner, 64, 64)
    .fuse(x_outer, y_outer, tile_index)
    .parallel(tile_index);
```

#### Unrolling

Eliminates loop overhead for small, fixed iteration counts:

```cpp
gradient.unroll(x, 4);  // unroll x by factor of 4
```

Useful for small kernels (3x3, 5x5) and color channel loops (c=0..2).

### 2.2 Producer-Consumer Fusion

The key optimization for multi-stage pipelines. Without fusion, each stage writes intermediate results to DRAM and the next stage reads them back — 6 DRAM operations instead of 2.

#### `compute_root()`

Compute all of producer before any of consumer. Maximum memory, minimum redundant computation.

```cpp
producer.compute_root();
```

#### `compute_at(consumer, var)`

Compute producer on-demand inside consumer's loop over `var`. Balances memory vs. recomputation.

```cpp
producer.compute_at(consumer, y);   // per-scanline
producer.compute_at(consumer, x);   // per-pixel (like inlining but with storage)
```

#### `store_root().compute_at(consumer, var)`

Allocate storage at outermost level, compute at inner level. Enables circular buffer optimization — Halide folds storage into `2 × width` scanlines using bitmask addressing.

```cpp
producer.store_root().compute_at(consumer, y);
```

This is the **best pattern for Spektrafilm's pipeline**: allocate once, compute on-demand, reuse previous scanlines.

#### Tiled Fusion (Recommended for Large Images)

```cpp
Var xo, yo, xi, yi, tile_idx;
consumer.tile(x, y, xo, yo, xi, yi, 64, 64)
    .fuse(xo, yo, tile_idx)
    .parallel(tile_idx);
producer.compute_at(consumer, xo);  // compute per-tile
```

Each tile computes the producer region it needs, keeping data cache-resident.

### 2.3 The Mixed Strategy (95% of Practical Scheduling)

From Halide Lesson 8 — the canonical production schedule:

```cpp
// Split consumer into strips of 16 scanlines
Var yo, yi;
consumer.split(y, yo, yi, 16);
consumer.parallel(yo);           // parallelize strips
consumer.vectorize(x, 4);        // vectorize within strips

// Producer: store per-strip, compute per-scanline
producer.store_at(consumer, yo);  // storage for 17 scanlines (circular buffer of 2)
producer.compute_at(consumer, yi); // compute per scanline, skipping already-done rows
producer.vectorize(x, 4);
```

**Why this works for Spektrafilm**: The pipeline has ~10 stages. With `store_at` + `compute_at`, each strip of 16 rows flows through all stages while data is hot in L1/L2 cache. The circular buffer keeps only 2 scanlines of each intermediate alive.

### 2.4 rfactor for Reductions

For associative reductions (sum, product, histogram), `rfactor` splits the reduction domain to enable parallelism:

```cpp
// Serial reduction
Func histogram;
histogram(x) = 0;
RDom r(0, W, 0, H);
histogram(input(r.x, r.y) / 32) += 1;

// Parallel reduction via rfactor
Func intermediate = histogram.update().rfactor({{r.y, y}});
intermediate.compute_root().update().parallel(y);
```

**Spektrafilm relevance**: The `einsum('ijk,lk->ijl')` operations are reductions over the wavelength dimension (K=81). These can be expressed as Halide reductions and parallelized with `rfactor` if needed (though K=81 is small enough that serial reduction is likely fast enough).

---

## 3. AOT Compilation with CMake for Android ARM

### 3.1 Halide Generator Pattern

Halide Generators are the standard way to define AOT-compiled pipelines. A Generator is a class that encapsulates inputs, outputs, parameters, and the schedule:

```cpp
#include "Halide.h"

class SpectralPipeline : public Halide::Generator<SpectralPipeline> {
public:
    // Inputs
    Input<Buffer<float, 3>> rgb_input{"rgb_input"};  // H x W x 3
    Input<Buffer<float, 2>> ccm_3x3{"ccm_3x3"};      // 3 x 3 color matrix
    Input<float> strength{"strength"};

    // Output
    Output<Buffer<float, 3>> xyz_output{"xyz_output"}; // H x W x 3

    void generate() {
        Var x("x"), y("y"), c("c");

        // Boundary condition
        Func clamped = BoundaryConditions::repeat_edge(rgb_input);

        // 3x3 matrix multiply: XYZ[c] = sum_i(RGB[i] * M[c,i])
        RDom i(0, 3);
        result(x, y, c) = sum(clamped(x, y, i) * ccm_3x3(c, i));

        xyz_output(x, y, c) = result(x, y, c);

        // Schedule
        if (using_autoscheduler()) {
            rgb_input.set_estimates({{0, 1024}, {0, 1024}, {0, 3}});
            ccm_3x3.set_estimates({{0, 3}, {0, 3}});
            strength.set_estimate(1.0f);
            xyz_output.set_estimates({{0, 1024}, {0, 1024}, {0, 3}});
        } else {
            xyz_output.vectorize(x, natural_vector_size<float>())
                      .parallel(y);
        }
    }

private:
    Func result;
};

HALIDE_REGISTER_GENERATOR(SpectralPipeline, spectral_pipeline)
```

### 3.2 CMake Integration

```cmake
cmake_minimum_required(VERSION 3.20)
project(spektrafilm_halide)

find_package(Halide REQUIRED)

# AOT compile for host (development)
add_halide_library(spectral_pipeline_host FROM spectral_pipeline_gen
    GENERATOR SpectralPipeline
    PARAMS target=host
)

# AOT compile for Android ARM64 (cross-compilation)
add_halide_library(spectral_pipeline_arm64 FROM spectral_pipeline_gen
    GENERATOR SpectralPipeline
    PARAMS target=arm-64-android
)

# AOT compile for Android ARM32
add_halide_library(spectral_pipeline_arm32 FROM spectral_pipeline_gen
    GENERATOR SpectralPipeline
    PARAMS target=arm-32-android
)

# Link into JNI library
add_library(spektrafilm_jni SHARED jni_bridge.cpp)
target_link_libraries(spektrafilm_jni PRIVATE spectral_pipeline_arm64)
```

### 3.3 Halide Target Strings

The target string controls code generation. For Android:

| ABI | Halide Target | Notes |
|-----|---------------|-------|
| `arm64-v8a` | `arm-64-android` | Primary target, NEON auto-enabled |
| `armeabi-v7a` | `arm-32-android` | Legacy, NEON optional |
| `x86_64` | `x86-64-android` | Emulator only |
| `x86` | `x86-32-android` | Rare |

Additional target features can be appended: `arm-64-android-no_runtime` (to avoid bundling Halide runtime), `arm-64-android-hvx` (for Hexagon DSP, not relevant here).

### 3.4 Building the Generator Executable

```cmake
# Compile the generator as an executable
add_executable(spectral_pipeline_gen
    generators/spectral_pipeline_generator.cpp
    tools/GenGen.cpp
)
target_link_libraries(spectral_pipeline_gen PRIVATE Halide::Halide)
```

Then invoke it:

```bash
# Generate for host
./spectral_pipeline_gen -o . -g SpectralPipeline \
    -e static_library,h,schedule \
    target=host

# Generate for ARM64 Android
./spectral_pipeline_gen -o . -g SpectralPipeline \
    -e static_library,h \
    target=arm-64-android
```

This produces:
- `spectral_pipeline.a` — static library to link
- `spectral_pipeline.h` — C header with function signature

### 3.5 Generated Function Signature

The generated header exposes a C-linkage function:

```c
int spectral_pipeline(
    const halide_buffer_t *rgb_input,
    const halide_buffer_t *ccm_3x3,
    float strength,
    halide_buffer_t *xyz_output
);
```

For Tuple-valued outputs, multiple `halide_buffer_t*` params are appended.

### 3.6 JNI Integration Pattern

```cpp
#include <jni.h>
#include "spectral_pipeline.h"
#include <android/hardware_buffer.h>

extern "C" JNIEXPORT void JNICALL
Java_com_spektrafilm_engine_NativeProcess_applyPipeline(
    JNIEnv *env, jobject /* this */,
    jobject inputBuffer, jobject outputBuffer, jfloat strength) {

    float *in = (float *)env->GetDirectBufferAddress(inputBuffer);
    float *out = (float *)env->GetDirectBufferAddress(outputBuffer);

    halide_buffer_t h_in = {};
    h_in.dim[0] = {0, width, 1};
    h_in.dim[1] = {0, height, width};
    h_in.dim[2] = {0, 3, width * height};
    h_in.host = (uint8_t *)in;
    h_in.type = halide_type_of<float>();

    halide_buffer_t h_out = {};
    // ... similar setup ...

    spectral_pipeline(&h_in, &ccm_buf, strength, &h_out);
}
```

---

## 4. Python Bindings

### 4.1 Installation

```bash
pip install halide  # PyPI package, currently v21.0.0
```

The Python bindings (`halide` module) wrap the same C++ compiler via pybind11. They support both JIT and AOT compilation.

### 4.2 Basic Usage

```python
import halide as hl
import numpy as np

# Define pipeline
input_img = hl.ImageParam(hl.Float(32), 3)  # 3D float32
f = hl.Func('f')
x, y, c = hl.Var('x'), hl.Var('y'), hl.Var('c')

# Brightness adjustment
f[x, y, c] = hl.min(2.0 * input_img[x, y, c], 1.0)

# Set input
img = np.random.rand(1024, 1024, 3).astype(np.float32)
# NOTE: Halide uses Fortran (column-major) ordering
input_img.set(hl.Buffer(np.asfortranarray(img)))

# Execute
output = f.realize(img.shape[1], img.shape[0], img.shape[2])
result = np.array(output)
```

### 4.3 Scheduling in Python

```python
# Vectorize and parallelize
f.vectorize(x, 4).parallel(y)

# Tiling
xo, yo, xi, yi = hl.Var('xo'), hl.Var('yo'), hl.Var('xi'), hl.Var('yi')
f.tile(x, y, xo, yo, xi, yi, 64, 64)
f.fuse(xo, yo, tile_idx).parallel(tile_idx)
```

### 4.4 Important: Fortran Ordering

Halide's Python bindings assume **Fortran (column-major) ordering**. NumPy defaults to C (row-major). Always convert:

```python
img_fortran = np.asfortranarray(img)
buffer = hl.Buffer(img_fortran)
```

The dimension order in Fortran is `(channels, width, height)` — leftmost dimension varies fastest. This is the opposite of NumPy's `(height, width, channels)`.

### 4.5 Spektrafilm's Existing Halide Python Backend

The file `src/spektrafilm/gpu/halide_backend.py` already uses the Python Halide bindings for JIT kernels:

```python
import halide as hl

# 3D trilinear LUT sampling
# rgb_to_xyz 3x3 matrix multiply
```

These JIT kernels run on the host. For Android, the same algorithms would be expressed as C++ Generators and AOT-compiled.

---

## 5. Gaussian Blur / Separable Convolution

### 5.1 Separable FIR Gaussian (Small Sigma)

A 2D Gaussian with standard deviation `σ` decomposes into two 1D passes — horizontal then vertical. This reduces work from O(r²) to O(2r) per pixel.

**Halide Implementation:**

```cpp
Func separable_gaussian_fir(Buffer<float> input, float sigma, int radius) {
    Var x("x"), y("y"), c("c");
    Func clamped = BoundaryConditions::mirror_interior(input);

    // Precompute 1D kernel weights
    // w[i] = exp(-i²/(2σ²)) / Σw, for i ∈ [-radius, radius]

    // Horizontal pass
    Func blur_x("blur_x");
    RDom rx(-radius, 2 * radius + 1);
    blur_x(x, y, c) = sum(clamped(x + rx, y, c) * kernel(rx + radius));

    // Vertical pass
    Func blur_y("blur_y");
    RDom ry(-radius, 2 * radius + 1);
    blur_y(x, y, c) = sum(blur_x(x, y + ry, c) * kernel(ry + radius));

    // Schedule: tile + fuse + parallel + vectorize
    Var xo, yo, xi, yi, tile_idx;
    blur_y.tile(x, y, xo, yo, xi, yi, 64, 16)
          .fuse(xo, yo, tile_idx)
          .parallel(tile_idx)
          .vectorize(xi, 4);

    // Key: compute horizontal pass per-tile of vertical pass
    blur_x.compute_at(blur_y, xi).vectorize(x, 4);

    return blur_y;
}
```

**Schedule explanation**: The horizontal pass is computed on-demand for each tile of the vertical pass. Since we need `(2*radius+1)` rows of `blur_x` per tile of `blur_y`, we compute only those rows — keeping the horizontal intermediate in L1 cache.

### 5.2 Spektrafilm's FIR Kernel

From `gpu/kernels/filters.py`, the Metal kernel shows the exact algorithm:

```
// For each pixel (x, y, c):
//   for dy in [-radius, radius]:
//     yy = mirror_reflect(y + dy, H)
//     wy = gaussian_kernel[dy + radius]
//     for dx in [-radius, radius]:
//       xx = mirror_reflect(x + dx, W)
//       wx = gaussian_kernel[dx + radius]
//       total += image[yy, xx, c] * wx * wy
//   out[y, x, c] = total
```

The mirror-reflection boundary is: `yy = yy % (2*H); if (yy >= H) yy = 2*H - 1 - yy;`

In Halide, use `BoundaryConditions::mirror_interior(input)` which does this automatically.

### 5.3 Per-Channel Sigma

Spektrafilm applies different sigma per channel (R, G, B can have different blur radii). In Halide, express this with `select`:

```cpp
Expr radius_c = clamp(select(c == 0, sigma_to_radius(sigma_r),
                                    c == 1, sigma_to_radius(sigma_g),
                                             sigma_to_radius(sigma_b)),
                      0, max_radius);

// Mask out contributions beyond the per-channel radius
Expr weight = select(abs(rx) <= radius_c && abs(ry) <= radius_c,
                     kernel_x(rx + max_radius, c) * kernel_y(ry + max_radius, c),
                     0.0f);
```

Or more efficiently, process each channel as a separate Func and schedule differently per channel.

---

## 6. 3D LUT Trilinear Interpolation

### 6.1 Algorithm

Given a 3D LUT of size `N×N×N` with 3 output channels, and an input RGB pixel:

1. Scale input to LUT coordinates: `p = rgb * (N-1)`
2. Find the 8 surrounding lattice points
3. Compute fractional parts `fx, fy, fz`
4. Trilinear interpolation: weighted average of 8 corners

```
result = (1-fx)*(1-fy)*(1-fz) * LUT[x0,y0,z0]
       + fx*(1-fy)*(1-fz)     * LUT[x1,y0,z0]
       + (1-fx)*fy*(1-fz)     * LUT[x0,y1,z0]
       + fx*fy*(1-fz)         * LUT[x1,y1,z0]
       + (1-fx)*(1-fy)*fz     * LUT[x0,y0,z1]
       + fx*(1-fy)*fz         * LUT[x1,y0,z1]
       + (1-fx)*fy*fz         * LUT[x0,y1,z1]
       + fx*fy*fz             * LUT[x1,y1,z1]
```

### 6.2 Halide Implementation

```cpp
Func apply_lut_3d(Buffer<float> lut,    // N x N x N x 3
                  Buffer<float> coords, // H x W x 3 (normalized 0..1)
                  int N) {
    Var x("x"), y("y"), c("c");

    // Scale to LUT domain
    Expr sx = clamp(coords(x, y, 0) * (N - 1), 0.0f, (float)(N - 1));
    Expr sy = clamp(coords(x, y, 1) * (N - 1), 0.0f, (float)(N - 1));
    Expr sz = clamp(coords(x, y, 2) * (N - 1), 0.0f, (float)(N - 1));

    // Integer and fractional parts
    Expr x0 = cast<int>(floor(sx)), y0 = cast<int>(floor(sy)), z0 = cast<int>(floor(sz));
    Expr x1 = min(x0 + 1, N - 1),   y1 = min(y0 + 1, N - 1),   z1 = min(z0 + 1, N - 1);
    Expr fx = sx - cast<float>(x0);
    Expr fy = sy - cast<float>(y0);
    Expr fz = sz - cast<float>(z0);

    // 8-corner interpolation
    Expr c000 = lut(x0, y0, z0, c), c100 = lut(x1, y0, z0, c);
    Expr c010 = lut(x0, y1, z0, c), c110 = lut(x1, y1, z0, c);
    Expr c001 = lut(x0, y0, z1, c), c101 = lut(x1, y0, z1, c);
    Expr c011 = lut(x0, y1, z1, c), c111 = lut(x1, y1, z1, c);

    // Trilinear blend
    Func result("lut_3d");
    result(x, y, c) =
        c000 * (1-fx)*(1-fy)*(1-fz) + c100 * fx*(1-fy)*(1-fz) +
        c010 * (1-fx)*fy*(1-fz)     + c110 * fx*fy*(1-fz) +
        c001 * (1-fx)*(1-fy)*fz     + c101 * fx*(1-fy)*fz +
        c011 * (1-fx)*fy*fz         + c111 * fx*fy*fz;

    // Schedule: process planar (c innermost for LUT locality)
    result.vectorize(x, 4).parallel(y);

    return result;
}
```

### 6.3 Spektrafilm's LUT Implementation

From `gpu/kernels/lut.py`, the Metal kernel uses Mitchell-Netravali cubic for 2D LUTs and trilinear for 3D LUTs. The 3D version matches the algorithm above exactly. The 2D version uses a 4x4 bicubic kernel with Mitchell-Netravali weights `(a=1/3, b=1/3)`.

### 6.4 2D LUT (Mitchell-Netravali Cubic)

For the 2D cubic LUT, the Halide version uses `RDom` to iterate over the 4x4 neighborhood:

```cpp
Func apply_lut_2d_cubic(Buffer<float> lut,     // N x N x C_out
                        Buffer<float> coords,   // H x W x 2
                        int N) {
    Var x("x"), y("y"), c("c");

    Expr sx = clamp(coords(x, y, 0) * (N - 1), 0.0f, (float)(N - 1));
    Expr sy = clamp(coords(x, y, 1) * (N - 1), 0.0f, (float)(N - 1));

    Expr x_base = cast<int>(floor(sx));
    Expr y_base = cast<int>(floor(sy));
    Expr x_frac = sx - cast<float>(x_base);
    Expr y_frac = sy - cast<float>(y_base);

    // Mitchell-Netravali weight function
    auto mitchell = [](Expr t) {
        Expr at = abs(t);
        return select(at < 1.0f,
            (1.0f/6.0f) * ((12.0f - 9.0f*at) * at*at),
            select(at < 2.0f,
                (1.0f/6.0f) * ((-at + 3.0f)*at - 3.0f)*at + (8.0f/6.0f),
                0.0f));
    };

    // Accumulate over 4x4 neighborhood
    Func result("lut_2d_cubic");
    RDom r(-1, 4, -1, 4);  // dx, dy from -1 to 2
    Expr wx = mitchell(x_frac - cast<float>(r.x));
    Expr wy = mitchell(y_frac - cast<float>(r.y));
    Expr lx = clamp(x_base + r.x, 0, N - 1);
    Expr ly = clamp(y_base + r.y, 0, N - 1);

    result(x, y, c) = sum(lut(lx, ly, c) * wx * wy);

    result.vectorize(x, 4).parallel(y);
    return result;
}
```

---

## 7. IIR Filter: Young-van Vliet

### 7.1 Algorithm

The Young-van Vliet (YvV) 4-tap IIR Gaussian approximation uses a recursive filter with 4 complex poles. It achieves Gaussian blur with O(1) cost per pixel regardless of sigma, making it ideal for large radii.

The filter has the form:
```
y[n] = b0*x[n] + b1*x[n-1] + b2*x[n-2] + b3*x[n-3]
             - a1*y[n-1] - a2*y[n-2] - a3*y[n-3]
```

The coefficients are derived from the desired sigma by finding the roots of a polynomial.

### 7.2 Halide IIR Implementation

IIR filters are inherently sequential along the scan direction. Halide supports this via `update` definitions:

```cpp
Func young_van_vliet_1d(Buffer<float> input, float b0, float b1, float b2, float b3,
                        float a1, float a2, float a3, int W) {
    Var x("x"), y("y"), c("c");

    // Forward pass (left-to-right)
    Func forward("forward");
    forward(x, y, c) = 0.0f;  // pure definition

    // Update: sequential dependency along x
    // We need access to x-1, x-2, x-3, so we use clamp
    Expr px = forward(clamp(x - 1, 0, W - 1), y, c);
    Expr px2 = forward(clamp(x - 2, 0, W - 1), y, c);
    Expr px3 = forward(clamp(x - 3, 0, W - 1), y, c);

    forward(x, y, c) = b0 * input(x, y, c)
                     + b1 * select(x > 0, input(x - 1, y, c), input(x, y, c))
                     + b2 * select(x > 1, input(x - 2, y, c), input(x, y, c))
                     + b3 * select(x > 2, input(x - 3, y, c), input(x, y, c))
                     - a1 * px - a2 * px2 - a3 * px3;

    // Backward pass (right-to-left)
    Func backward("backward");
    backward(x, y, c) = 0.0f;

    Expr nx = backward(clamp(x + 1, 0, W - 1), y, c);
    Expr nx2 = backward(clamp(x + 2, 0, W - 1), y, c);
    Expr nx3 = backward(clamp(x + 3, 0, W - 1), y, c);

    backward(x, y, c) = b0 * forward(x, y, c)
                      + b1 * forward(clamp(x + 1, 0, W - 1), y, c)
                      + b2 * forward(clamp(x + 2, 0, W - 1), y, c)
                      + b3 * forward(clamp(x + 3, 0, W - 1), y, c)
                      - a1 * nx - a2 * nx2 - a3 * nx3;

    // Schedule: parallelize across y (independent scanlines)
    forward.parallel(y).vectorize(x, 4);
    backward.parallel(y).vectorize(x, 4);

    return backward;
}
```

### 7.3 Spektrafilm's YvV Implementation

From `utils/fast_gaussian_filter.py`, the `_yvv_coeffs` function computes the 4-tap coefficients from sigma. The Numba kernel applies:

1. **Forward pass**: left-to-right along each row
2. **Backward pass**: right-to-left, combining forward results
3. **Separable**: repeat for vertical direction (transpose, apply, transpose)

The Metal/CuPy versions do the horizontal and vertical passes as separate kernel dispatches.

### 7.4 Key Insight for Spektrafilm

The IIR filter has a sequential dependency along x. Halide cannot parallelize the x dimension for this stage. However:

- **y dimension is independent** — each scanline can be processed in parallel
- **Channels are independent** — R, G, B can be processed in parallel
- **Two passes** (forward + backward) are needed per dimension

For the vertical pass, transpose the data, apply horizontal IIR, transpose back. Or use a direct vertical implementation with `compute_at` to keep a column of state.

---

## 8. FFT Integration

### 8.1 Halide FFT Status

Halide does **not** have a built-in FFT. The Halide research group published a paper on generating FFTs with Halide (`halide-fft`), but this is not a standard library component.

### 8.2 Options for Spektrafilm

| Option | Pros | Cons |
|--------|------|------|
| **Spatial-domain convolution** | Pure Halide, no dependencies | Slow for large kernels (r > 50) |
| **FFTW** | Fastest CPU FFT | GPL license, not suitable for Android apps |
| **Ne10 (ARM)** | ARM-optimized, permissive license | Limited maintenance |
| **VkFFT** | Vulkan-based, very fast | Requires Vulkan |
| **cuFFT** | CUDA-only | Not available on Android |
| **Custom Radix-2 FFT** | Can be expressed in Halide with update defs | Complex to implement |

### 8.3 Spektrafilm's Diffusion Filter Strategy

The existing codebase already decomposes the diffusion filter PSF into Gaussian sub-components. Each Gaussian can be applied as:

1. **FIR** (small sigma, < ~10px radius) — pure Halide separable convolution
2. **IIR** (large sigma, > ~10px radius) — Young-van Vliet recursive filter

This decomposition **eliminates the need for FFT entirely** for most use cases. The `diffusion_filter_um` function in `model/diffusion.py` already uses this strategy.

**Recommendation**: Use Halide FIR for small kernels and Halide IIR (YvV) for large kernels. Only add FFT if profiling shows the diffusion filter is a bottleneck that spatial methods can't address.

---

## 9. Random Number Generation

### 9.1 The Problem

Halide is a **deterministic dataflow language**. It has no built-in random number generator. Every `Func` must produce the same output for the same input coordinates.

Spektrafilm uses RNG for:
- **Grain simulation**: Poisson + Binomial random deviates per pixel
- **Glare simulation**: Lognormal random deviates per pixel

### 9.2 Workaround: Pre-Generated Random Buffer

The standard approach is to generate random numbers in a separate C++ pass and feed them into Halide as an input buffer:

```cpp
// Step 1: Generate random deviates in C++
#include <random>
std::mt19937 rng(seed);
std::poisson_distribution<int> poisson(lambda);

Buffer<int> random_buf(W, H);
for (int y = 0; y < H; y++)
    for (int x = 0; x < W; x++)
        random_buf(x, y) = poisson(rng);

// Step 2: Use in Halide pipeline
Func grain;
grain(x, y, c) = input(x, y, c) + cast<float>(random_buf(x, y)) * scale;
```

### 9.3 Hash-Based Deterministic Noise

For deterministic noise (same seed → same result on all devices), use integer hash functions as pseudo-random number generators. These are pure Halide expressions:

```cpp
Expr wang_hash(Expr seed) {
    Expr x = cast<uint32_t>(seed);
    x = (x ^ 61) ^ (x >> 16);
    x = x + (x << 3);
    x = x ^ (x >> 4);
    x = x * 0x27d4eb2d;
    x = x ^ (x >> 15);
    return cast<float>(x) / cast<float>(0xFFFFFFFF);
}

Func perlin_noise;
Expr hash_input = cast<int>(x) * 73856093 ^ cast<int>(y) * 19349663;
perlin_noise(x, y) = wang_hash(hash_input);
```

### 9.4 Spektrafilm's RNG Strategy

From `utils/fast_stats.py`, the Numba implementations use:
- **Poisson**: Knuth's algorithm for small λ, Gaussian approximation for large λ
- **Binomial**: Direct simulation for small n, Gaussian approximation for large n
- **Lognormal**: Box-Muller transform from uniform

**Recommended approach for Android**:

1. Generate random buffers using C++ `<random>` with a fixed seed
2. Pass as `halide_buffer_t` input to the Halide grain/glare pipeline
3. Use `std::mt19937` for reproducibility across devices
4. For preview mode, use lower-resolution random buffers (upscale with bilinear interpolation)

This is a **two-pass architecture**: RNG pass (C++) → Halide compute pass.

---

## 10. Autoscheduler Comparison

### 10.1 Available Autoschedulers

| Autoscheduler | Year | Approach | Status |
|---------------|------|----------|--------|
| **Mullapudi2016** | 2016 | Heuristic/analytic (interval analysis + ILP) | Stable, included in Halide |
| **Li2018** | 2018 | Deep reinforcement learning | Research, not in mainline |
| **Anderson2021** | 2021 | Tree search + random program training | Stable, included in Halide |

### 10.2 Mullapudi2016 (Default)

**How it works**: Uses a model based on interval analysis and integer linear programming to decide:
- Which stages to inline vs. compute_root
- Tile sizes based on cache model
- Simple vectorization and parallelization

**Parameters**:
```bash
autoscheduler=Mullapudi2016
autoscheduler.parallelism=8        # CPU cores
autoscheduler.last_level_cache_size=8388608  # L3 cache in bytes
autoscheduler.balance=40           # ratio of cache-miss cost to arithmetic cost
```

**Strengths**: Fast scheduling (seconds), deterministic, good for simple pipelines.

**Weaknesses**: Only does tiling, vectorization, parallelization. No line buffering, storage reordering, or reduction factoring.

### 10.3 Anderson2021 (Recommended)

**How it works**: 
1. Generates many random Halide programs
2. Trains a cost model on their measured performance
3. Uses tree search to find good schedules for new programs

**Usage**:
```bash
./my_generator -o . -g MyPipeline \
    -p libautoschedule_anderson2021.so \
    -S Anderson2021 \
    target=arm-64-android \
    autoscheduler=Anderson2021
```

**Strengths**: Better schedules for complex pipelines, handles more optimization dimensions.

**Weaknesses**: Slower (minutes), non-deterministic (may produce different schedules on different runs).

### 10.4 Recommendation for Spektrafilm

1. **Start with Mullapudi2016** for initial development — fast iteration, predictable
2. **Switch to Anderson2021** for production — better performance on Spektrafilm's multi-stage pipeline
3. **Hand-tune critical kernels** if the autoscheduler doesn't exploit domain knowledge (e.g., the 81-wavelength reduction dimension)
4. **Use the autoscheduler as a starting point**, then manually adjust based on profiling

The autoscheduler cannot handle:
- Reduction factoring (`rfactor`) — must be done manually
- Line buffering / circular buffer tricks — may need manual `store_at` + `compute_at`
- Per-channel scheduling — all channels get the same schedule

---

## 11. Common Pitfalls

### 11.1 Boundary Conditions

**Problem**: Accessing pixels outside the image bounds causes undefined behavior or crashes.

**Solution**: Always wrap inputs in boundary conditions:
```cpp
Func clamped = BoundaryConditions::repeat_edge(input);      // clamp to edge
Func mirrored = BoundaryConditions::mirror_interior(input);  // mirror reflection
Func constant = BoundaryConditions::constant_exterior(input, 0.0f);  // pad with constant
```

**Spektrafilm note**: Use `mirror_interior` for Gaussian blur (matches the existing Numba implementation's reflect-padding) and `repeat_edge` for LUT sampling.

### 11.2 Type Mismatches and Overflow

**Problem**: `uint8_t` arithmetic overflows silently. `int * int` can overflow before promotion.

**Solution**: Cast to wider types before arithmetic:
```cpp
Expr val = cast<int16_t>(input(x, y, c));
Expr result = cast<uint8_t>(clamp(val * 5 - neighbors, 0, 255));
```

**Spektrafilm note**: All operations use `float32` (as mandated by CLAUDE.md precision requirements). No integer overflow risk, but be aware of float32 precision limits for the 81-wavelength reductions.

### 11.3 Race Conditions with `parallel()`

**Problem**: Parallelizing a loop that writes to shared memory (e.g., reduction updates) causes race conditions.

**Solution**: 
- Pure definitions are safe to parallelize
- Update definitions with reductions over parallelized variables are NOT safe
- Use `rfactor` to factor associative reductions into parallel-safe form

### 11.4 Forgetting `compute_root()` for Non-Trivial Stages

**Problem**: The default schedule inlines everything. For expensive intermediate stages, this causes massive redundant computation.

**Solution**: Start with `compute_root()` for all non-trivial stages, then optimize from there:
```cpp
// Start here
producer.compute_root();

// Then optimize: try compute_at for better locality
producer.compute_at(consumer, yi);
```

### 11.5 Scheduling Order Matters

**Problem**: When scheduling producers, you must refer to Vars introduced by the consumer's schedule. If you schedule the producer first, those Vars don't exist yet.

**Solution**: Schedule from the end of the pipeline backwards:
```cpp
// Schedule consumer first (introduces xo, yo, xi, yi)
consumer.tile(x, y, xo, yo, xi, yi, 64, 64).parallel(yo);

// Then schedule producer (can now reference xo)
producer.compute_at(consumer, xo);
```

### 11.6 `split()` Doesn't Change Execution Order

**Problem**: Beginners expect `split(x, xo, xi, 4)` to change the loop order. It doesn't — you must `reorder()` afterward.

**Solution**: Use `tile()` which combines split + reorder, or explicitly reorder:
```cpp
f.split(x, xo, xi, 4).split(y, yo, yi, 4).reorder(xi, yi, xo, yo);
```

### 11.7 Bounds Inference Can Over-Compute

**Problem**: Halide's bounds inference may request more of the producer than strictly needed, especially with complex stencil patterns.

**Solution**: Use `bound()` to constrain output extents:
```cpp
output.bound(x, 0, W).bound(y, 0, H).bound(c, 0, 3);
```

### 11.8 Debugging: `print_loop_nest()` and `trace_stores()`

```cpp
// See the generated loop structure
consumer.print_loop_nest();

// Trace actual stores (generates a LOT of output for large images)
consumer.trace_stores();
producer.trace_stores();
consumer.realize({64, 64});  // small image for debugging

// Check generated code
consumer.compile_to_lowered_stmt("output.html", {}, "consumer");
```

### 11.9 Python Buffer Ordering

**Problem**: Halide Python uses Fortran ordering (leftmost = innermost). NumPy uses C ordering (rightmost = innermost).

**Solution**: Always convert:
```python
img = np.asfortranarray(img)  # or use hl.Buffer.make_interleaved()
```

---

## 12. Vulkan Compute on Android

### 12.1 Current Status (2026)

Halide has a Vulkan backend, but it is **experimental** and not recommended for production Android use:

- The Vulkan backend exists in Halide's source tree under `src/CodeGen_Vulkan*`
- Official documentation describes Vulkan support as "work in progress"
- The backend targets Vulkan compute shaders (not graphics pipelines)
- Android Vulkan support is less tested than desktop Vulkan

### 12.2 Target String

```cpp
// Vulkan on Android (experimental)
target = "arm-64-android-vulkan"

// Or with specific Vulkan version
target = "arm-64-android-vulkan-v1_0"
```

### 12.3 Limitations

- **No mature autoscheduler** for Vulkan targets — manual scheduling required
- **Memory management** — Vulkan buffer allocation/deallocation is explicit and complex
- **Descriptor set management** — Halide's Vulkan backend handles this, but edge cases exist
- **Shader compilation** — `glslc` or `dxc` must be available at compile time
- **Device compatibility** — not all Android devices have good Vulkan compute support
- **Synchronization** — Vulkan requires explicit barriers; Halide handles this for simple cases

### 12.4 Recommendation for Spektrafilm

**Default to CPU AOT Halide first.** This is the safe, well-tested path:

1. Phase 1-2: CPU AOT (`target=arm-64-android`)
2. Phase 3: Profile on real devices. If CPU is too slow for specific kernels, experiment with Vulkan for those specific kernels only
3. Keep a CPU fallback for devices with poor Vulkan support

The Vulkan backend should be considered an optimization target, not a primary strategy.

---

## 13. Spektrafilm-Specific Halide Code Examples

These examples show how to express Spektrafilm's core kernels in Halide C++. All use `float32` throughout (matching the CLAUDE.md precision requirement).

### 13.1 Spectral Einsum (81-Wavelength Matrix Multiply)

Spektrafilm's `compute_density_spectral` performs: `density_spectral[i,j,l] = Σ_k density_cmy[i,j,k] * channel_density[l,k]`

This is a matrix multiplication over the wavelength dimension (K=81).

```cpp
// Generator: SpectralEinsum
class SpectralEinsum : public Halide::Generator<SpectralEinsum> {
public:
    Input<Buffer<float, 3>> density_cmy{"density_cmy"};      // H x W x 3 (CMY)
    Input<Buffer<float, 2>> channel_density{"channel_density"}; // 81 x 3
    Output<Buffer<float, 3>> density_spectral{"density_spectral"}; // H x W x 81

    void generate() {
        Var x("x"), y("y"), wl("wl");

        // density_spectral(x, y, wl) = sum over k of density_cmy(x, y, k) * channel_density(wl, k)
        RDom k(0, 3);
        density_spectral(x, y, wl) = sum(
            density_cmy(x, y, k) * channel_density(wl, k)
        );

        // Schedule
        if (using_autoscheduler()) {
            density_cmy.set_estimates({{0, 1024}, {0, 1024}, {0, 3}});
            channel_density.set_estimates({{0, 81}, {0, 3}});
            density_spectral.set_estimates({{0, 1024}, {0, 1024}, {0, 81}});
        } else {
            // K=3 reduction is tiny, inline it
            density_spectral.vectorize(x, 4).parallel(y);
        }
    }
};
```

**Why this works**: The reduction over K=3 is trivially small (3 multiply-adds). Halide will inline the RDom loop and vectorize across x. The 81 wavelengths are independent and process in the y-parallel loop.

### 13.2 light_to_raw (Einsum with Larger Reduction)

`light_to_raw[i,j,l] = Σ_k light[i,j,k] * sensitivity[k,l]`

Same structure but sensitivity is `3×81` instead of `3×81`:

```cpp
class LightToRaw : public Halide::Generator<LightToRaw> {
public:
    Input<Buffer<float, 3>> light{"light"};          // H x W x 81
    Input<Buffer<float, 2>> sensitivity{"sensitivity"}; // 3 x 81
    Output<Buffer<float, 3>> raw_output{"raw_output"};  // H x W x 3

    void generate() {
        Var x("x"), y("y"), c("c");

        // raw(x, y, c) = sum over wl of light(x, y, wl) * sensitivity(c, wl)
        RDom wl(0, 81);
        raw_output(x, y, c) = sum(light(x, y, wl) * sensitivity(c, wl));

        if (using_autoscheduler()) {
            light.set_estimates({{0, 1024}, {0, 1024}, {0, 81}});
            sensitivity.set_estimates({{0, 3}, {0, 81}});
            raw_output.set_estimates({{0, 1024}, {0, 1024}, {0, 3}});
        } else {
            // K=81 reduction: vectorize the reduction with rfactor if needed
            // For now, inline (81 iterations is small)
            raw_output.vectorize(x, 4).parallel(y);
        }
    }
};
```

**Performance note**: 81 multiply-adds per pixel is ~162 FLOPs. At 1 megapixel, that's ~162M FLOPs — trivial for modern ARM CPUs (which can do >10 GFLOPS). The bottleneck is memory bandwidth, not compute. The schedule should focus on locality.

### 13.3 1D Linear Interpolation (Density Curves)

Spektrafilm's `interpolate_exposure_to_density` maps exposure values through per-channel density curves:

```cpp
class InterpDensityCurve : public Halide::Generator<InterpDensityCurve> {
public:
    Input<Buffer<float, 3>> values{"values"};   // H x W x 3 (exposure values)
    Input<Buffer<float, 2>> x_axis{"x_axis"};   // K x 3 (per-channel x coords)
    Input<Buffer<float, 2>> y_vals{"y_vals"};   // K x 3 (per-channel y values)
    Input<int> K{"K"};                           // number of knot points
    Output<Buffer<float, 3>> output{"output"};   // H x W x 3

    void generate() {
        Var x("x"), y("y"), c("c");

        // Binary search for the interval [lo, lo+1] containing values(x,y,c)
        // Then linear blend: output = y_lo + (val - x_lo) / (x_hi - x_lo) * (y_hi - y_lo)

        // For simplicity, use Halide's clamp + lerp pattern:
        // Scale value to [0, K-1] index space (assuming uniform x_axis)
        Expr val = values(x, y, c);
        Expr x_first = x_axis(0, c);
        Expr x_last = x_axis(K - 1, c);
        Expr scaled = clamp((val - x_first) / (x_last - x_first), 0.0f, 1.0f);
        Expr idx_f = scaled * cast<float>(K - 1);
        Expr idx_lo = clamp(cast<int>(floor(idx_f)), 0, K - 2);
        Expr idx_hi = idx_lo + 1;
        Expr frac = idx_f - cast<float>(idx_lo);

        // Linear interpolation
        Expr y_lo = y_vals(idx_lo, c);
        Expr y_hi = y_vals(idx_hi, c);
        output(x, y, c) = y_lo + frac * (y_hi - y_lo);

        if (using_autoscheduler()) {
            values.set_estimates({{0, 1024}, {0, 1024}, {0, 3}});
            x_axis.set_estimates({{0, 256}, {0, 3}});
            y_vals.set_estimates({{0, 256}, {0, 3}});
            output.set_estimates({{0, 1024}, {0, 1024}, {0, 3}});
        } else {
            output.vectorize(x, 4).parallel(y);
        }
    }
};
```

**Note**: For non-uniform x_axis spacing, use binary search (via `RDom` with a sequential loop or precompute a uniform lookup table).

### 13.4 2D/3D LUT Interpolation

See Section 6 for the full 3D trilinear and 2D Mitchell-Netravali implementations. The key Spektrafilm-specific detail is that the LUT coordinates come from the pipeline (not from the pixel directly), so the LUT sampling is a separate stage.

```cpp
class ApplyLUT3D : public Halide::Generator<ApplyLUT3D> {
public:
    Input<Buffer<float, 4>> lut{"lut"};       // N x N x N x 3
    Input<Buffer<float, 3>> coords{"coords"}; // H x W x 3 (normalized 0..1)
    Input<int> N{"N"};
    Output<Buffer<float, 3>> output{"output"}; // H x W x 3

    void generate() {
        Var x("x"), y("y"), c("c");

        // (full trilinear interpolation as in Section 6.2)
        // ... [implementation as above] ...

        output(x, y, c) = /* trilinear result */;

        if (using_autoscheduler()) {
            lut.set_estimates({{0, 33}, {0, 33}, {0, 33}, {0, 3}});
            coords.set_estimates({{0, 1024}, {0, 1024}, {0, 3}});
            output.set_estimates({{0, 1024}, {0, 1024}, {0, 3}});
        } else {
            output.vectorize(x, 4).parallel(y);
        }
    }
};
```

### 13.5 Gaussian FIR + IIR Blur

```cpp
class GaussianBlur : public Halide::Generator<GaussianBlur> {
public:
    Input<Buffer<float, 3>> input{"input"};  // H x W x 3
    Input<Buffer<float, 1>> kernel_1d{"kernel_1d"};  // (2*radius+1) weights
    Input<int> radius{"radius"};
    Output<Buffer<float, 3>> output{"output"}; // H x W x 3

    void generate() {
        Var x("x"), y("y"), c("c");

        Func clamped = BoundaryConditions::mirror_interior(input);

        // Horizontal pass
        Func blur_x("blur_x");
        RDom rx(-radius, 2 * radius + 1);
        blur_x(x, y, c) = sum(clamped(x + rx, y, c) * kernel_1d(rx + radius));

        // Vertical pass
        Func blur_y("blur_y");
        RDom ry(-radius, 2 * radius + 1);
        blur_y(x, y, c) = sum(blur_x(x, y + ry, c) * kernel_1d(ry + radius));

        output(x, y, c) = blur_y(x, y, c);

        if (using_autoscheduler()) {
            input.set_estimates({{0, 1024}, {0, 1024}, {0, 3}});
            kernel_1d.set_estimates({{0, 31}});
            radius.set_estimate(15);
            output.set_estimates({{0, 1024}, {0, 1024}, {0, 3}});
        } else {
            // Tiled schedule with fused producer
            Var xo, yo, xi, yi, tile_idx;
            output.tile(x, y, xo, yo, xi, yi, 64, 16)
                   .fuse(xo, yo, tile_idx)
                   .parallel(tile_idx)
                   .vectorize(xi, 4);
            blur_x.compute_at(output, xi).vectorize(x, 4);
        }
    }
};
```

### 13.6 CCTF sRGB Encoding/Decoding

The sRGB transfer function is a piecewise power curve:

**Decode** (encoded → linear):
```
linear = encoded / 12.92                    if encoded ≤ 0.04045
linear = ((encoded + 0.055) / 1.055)^2.4    otherwise
```

**Encode** (linear → encoded):
```
encoded = linear * 12.92                     if linear ≤ 0.0031308
encoded = 1.055 * linear^(1/2.4) - 0.055    otherwise
```

```cpp
class CCTFDecode : public Halide::Generator<CCTFDecode> {
public:
    Input<Buffer<float, 3>> encoded{"encoded"}; // H x W x 3
    Output<Buffer<float, 3>> linear{"linear"};  // H x W x 3

    void generate() {
        Var x("x"), y("y"), c("c");

        Expr e = encoded(x, y, c);
        linear(x, y, c) = select(
            e <= 0.04045f,
            e / 12.92f,
            pow((e + 0.055f) / 1.055f, 2.4f)
        );

        if (using_autoscheduler()) {
            encoded.set_estimates({{0, 1024}, {0, 1024}, {0, 3}});
            linear.set_estimates({{0, 1024}, {0, 1024}, {0, 3}});
        } else {
            linear.vectorize(x, 4).parallel(y);
        }
    }
};

class CCTFEncode : public Halide::Generator<CCTFEncode> {
public:
    Input<Buffer<float, 3>> linear{"linear"};   // H x W x 3
    Output<Buffer<float, 3>> encoded{"encoded"}; // H x W x 3

    void generate() {
        Var x("x"), y("y"), c("c");

        Expr l = linear(x, y, c);
        encoded(x, y, c) = select(
            l <= 0.0031308f,
            l * 12.92f,
            1.055f * pow(l, 1.0f / 2.4f) - 0.055f
        );

        if (using_autoscheduler()) {
            linear.set_estimates({{0, 1024}, {0, 1024}, {0, 3}});
            encoded.set_estimates({{0, 1024}, {0, 1024}, {0, 3}});
        } else {
            encoded.vectorize(x, 4).parallel(y);
        }
    }
};
```

**Note**: `pow()` is expensive. For ARM, Halide generates calls to `powf()`. If this is a bottleneck, consider a polynomial approximation for the 2.4 exponent (or use the fast `exp2(log2(x) * 2.4)` trick).

### 13.7 3x3 Color Matrix Multiply

```cpp
class ColorMatrix3x3 : public Halide::Generator<ColorMatrix3x3> {
public:
    Input<Buffer<float, 3>> rgb_input{"rgb_input"}; // H x W x 3
    Input<Buffer<float, 2>> matrix_3x3{"matrix_3x3"}; // 3 x 3
    Output<Buffer<float, 3>> rgb_output{"rgb_output"}; // H x W x 3

    void generate() {
        Var x("x"), y("y"), c("c");

        // rgb_output(x,y,c) = sum_i(rgb_input(x,y,i) * matrix_3x3(c,i))
        RDom i(0, 3);
        rgb_output(x, y, c) = sum(rgb_input(x, y, i) * matrix_3x3(c, i));

        if (using_autoscheduler()) {
            rgb_input.set_estimates({{0, 1024}, {0, 1024}, {0, 3}});
            matrix_3x3.set_estimates({{0, 3}, {0, 3}});
            rgb_output.set_estimates({{0, 1024}, {0, 1024}, {0, 3}});
        } else {
            // Tiny reduction (3 elements), inline it
            rgb_output.vectorize(x, 4).parallel(y);
            // Unroll the channel dimension for better register usage
            rgb_output.bound(c, 0, 3).unroll(c);
        }
    }
};
```

### 13.8 Highlight Boost (Piecewise Exponential)

Spektrafilm's `boost_highlights` applies a piecewise curve that boosts bright pixels using an exponential function:

```cpp
class HighlightBoost : public Halide::Generator<HighlightBoost> {
public:
    Input<Buffer<float, 3>> rgb_input{"rgb_input"}; // H x W x 3
    Input<float> threshold{"threshold"};
    Input<float> strength{"strength"};
    Output<Buffer<float, 3>> rgb_output{"rgb_output"}; // H x W x 3

    void generate() {
        Var x("x"), y("y"), c("c");

        // Piecewise: below threshold = identity, above = exponential boost
        Expr val = rgb_input(x, y, c);
        Expr excess = val - threshold;
        Expr boosted = threshold + excess * exp(strength * excess);
        rgb_output(x, y, c) = select(val > threshold, boosted, val);

        if (using_autoscheduler()) {
            rgb_input.set_estimates({{0, 1024}, {0, 1024}, {0, 3}});
            threshold.set_estimate(0.8f);
            strength.set_estimate(1.0f);
            rgb_output.set_estimates({{0, 1024}, {0, 1024}, {0, 3}});
        } else {
            rgb_output.vectorize(x, 4).parallel(y);
        }
    }
};
```

**Note**: `exp()` is vectorizable on ARM NEON via the math library. Halide generates `expf()` calls which are auto-vectorized by LLVM.

### 13.9 Complete Pipeline Composition

A full Spektrafilm pipeline in Halide would compose these generators into a single fused pipeline:

```cpp
class SpektrafilmPipeline : public Halide::Generator<SpektrafilmPipeline> {
public:
    // ... all inputs (RGB image, profile data, parameters) ...
    // ... all outputs (final RGB image) ...

    void generate() {
        Var x("x"), y("y"), c("c");

        // Stage 1: RGB → XYZ (3x3 matmul)
        Func xyz;
        RDom i(0, 3);
        xyz(x, y, c) = sum(clamped(x, y, i) * rgb_to_xyz_mat(c, i));

        // Stage 2: Spectral upsampling (LUT + einsum)
        Func spectral;
        RDom k(0, 3);
        spectral(x, y, wl) = sum(xyz(x, y, k) * basis(k, wl));

        // Stage 3: Film exposure (element-wise + density curve interp)
        Func exposed;
        exposed(x, y, wl) = spectral(x, y, wl) * exposure_time;

        // Stage 4: Density development (1D interp + einsum)
        Func density;
        density(x, y, wl) = interp_curve(exposed(x, y, wl));
        // ... more stages ...

        // Stage N: CCTF encoding
        Func output;
        Expr l = final_linear(x, y, c);
        output(x, y, c) = select(l <= 0.0031308f,
            l * 12.92f,
            1.055f * pow(l, 1.0f / 2.4f) - 0.055f);

        // Schedule: fused tile-based processing
        // All intermediate Funcs compute_at the output's tile level
        Var xo, yo, xi, yi, tile_idx;
        output.tile(x, y, xo, yo, xi, yi, 64, 16)
               .fuse(xo, yo, tile_idx)
               .parallel(tile_idx)
               .vectorize(xi, 4);

        // Each intermediate stage computes per-tile
        xyz.compute_at(output, xi).vectorize(x, 4);
        spectral.compute_at(output, xi);
        exposed.compute_at(output, xi);
        density.compute_at(output, xi);
        // ... etc for each stage ...
    }
};
```

This fused schedule keeps all intermediate results in L1/L2 cache within each 64×16 tile. For a 1-megapixel image, this uses ~4MB of intermediate storage per tile (manageable on any modern device).

---

## Summary: Spektrafilm Port Recommendations

| Concern | Recommendation |
|---------|---------------|
| **Primary target** | `arm-64-android` (CPU AOT) |
| **Scheduling** | Anderson2021 autoscheduler + manual tuning |
| **Gaussian blur** | FIR (small σ) + YvV IIR (large σ), fused with `compute_at` |
| **LUT interpolation** | Halide `select` + `clamp`, vectorized |
| **Spectral einsum** | Halide `RDom` reduction over K=3 or K=81 |
| **CCTF** | Halide `select` + `pow` |
| **RNG (grain/glare)** | C++ `<random>` pre-pass → Halide buffer input |
| **FFT** | Avoid — decompose into Gaussian sub-components |
| **Vulkan** | Experimental only, defer to Phase 3+ |
| **Precision** | `float32` throughout, `atol=1e-6` tolerance |
| **Memory** | Tile-based processing, 64×16 tiles, circular buffers |

---

## References

- Halide Tutorials: `https://halide-lang.org/tutorials/`
- Halide GitHub: `https://github.com/halide/Halide`
- Arm Halide Android Demo: `https://github.com/dawidborycki/Arm.Halide.AndroidDemo`
- Arm Halide Learning Path: `https://learn.arm.com/learning-paths/mobile-graphics-and-gaming/android_halide/intro/`
- Mullapudi et al. 2016: "Automatically Scheduling Halide Image Processing Pipelines"
- Adams et al. 2019: "Halide: a language and compiler for optimizing parallelism, locality, and recomputation in image processing pipelines" (PLDI 2013, updated)
- Anderson & Amarasinghe 2021: "Learning to Optimize Halide with Tree Search and Random Programs"
- Spektrafilm port plan: `docs/dev/halide-android-port-plan.md`
