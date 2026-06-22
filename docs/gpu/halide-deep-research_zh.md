> 这是英文原文的中文翻译。权威版本请参考英文原文。

# Spektrafilm Android 移植的 Halide 深度研究

**日期：** 2026-05-27
**目的：** 将 Spektrafilm 的光谱胶片模拟移植到 C++/Halide（Android ARM 平台）的综合参考文档

---

## 目录

1. [Halide 实际项目](#1-halide-实际项目)
2. [调度优化](#2-调度优化)
3. [使用 CMake 进行 Android ARM 的 AOT 编译](#3-使用-cmake-进行-android-arm-的-aot-编译)
4. [Python 绑定](#4-python-绑定)
5. [高斯模糊 / 可分离卷积](#5-高斯模糊--可分离卷积)
6. [3D LUT 三线性插值](#6-3d-lut-三线性插值)
7. [IIR 滤波器：Young-van Vliet](#7-iir-滤波器young-van-vliet)
8. [FFT 集成](#8-fft-集成)
9. [随机数生成](#9-随机数生成)
10. [自动调度器比较](#10-自动调度器比较)
11. [常见陷阱](#11-常见陷阱)
12. [Android 上的 Vulkan Compute](#12-android-上的-vulkan-compute)
13. [Spektrafilm 专用 Halide 代码示例](#13-spektrafilm-专用-halide-代码示例)

---

## 1. Halide 实际项目

### 1.1 官方示例和教程

Halide 仓库（`github.com/halide/Halide`）附带约 20 个教程课程，涵盖所有主要概念。关键课程：

- **Lesson 05**：向量化、并行化、展开和分块
- **Lesson 08**：多级流水线调度（生产者-消费者融合）
- **Lesson 09**：更新定义和归约（直方图、方框模糊）
- **Lesson 13**：元组（多值 Func、argmax/argmin）
- **Lesson 15**：Generator（AOT 编译封装）
- **Lesson 18**：用于并行化关联归约的 `rfactor`
- **Lesson 21**：自动调度器集成

参考：`https://halide-lang.org/tutorials/`

### 1.2 使用 Halide 的知名开源项目

| 项目 | 描述 | 仓库 |
|------|------|------|
| **Arm.Halide.AndroidDemo** | Android 上使用 JNI、CMake、NDK 的 Halide AOT | `github.com/dawidborycki/Arm.Halide.AndroidDemo` |
| **Arm.Halide.Hello-World** | ARM 上的最小 Halide + OpenCV 示例 | `github.com/dawidborycki/Arm.Halide.Hello-World` |
| **Halide apps/** | 相机管线、双边直方图、局部拉普拉斯、NLMeans | `github.com/halide/Halide/tree/main/apps` |
| **halide-sparse** | Halide 中的稀疏矩阵运算 | 学术项目 |
| **OpenCV DNN Halide 后端** | Halide 作为 OpenCV 深度学习模块的后端 | `opencv/modules/dnn` |

### 1.3 Adobe 和 Google 的使用

Halide 由 MIT/Adobe 于 2012 年创建。Adobe 在 Photoshop 图像处理内核的生产环境中使用它。Google 为编译器做出了重大贡献（LLVM 后端、自动调度器）。该语言由 Google 的 Halide 团队维护。

### 1.4 来自实际项目的关键架构模式

来自 Arm Android Demo（`dawidborycki/Arm.Halide.AndroidDemo`）：

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

JNI 桥接将 `AHardwareBuffer` 或 `DirectByteBuffer` 指针作为 `halide_buffer_t` 结构体传递。

---

## 2. 调度优化

### 2.1 核心调度原语

Halide 的强大之处在于算法/调度的分离。调度控制算法*如何*执行，而不改变它*计算*什么。

#### 分块（Tiling）

将 x 和 y 都拆分为外层/内层对，实现缓存友好的遍历：

```cpp
Var x_outer, y_outer, x_inner, y_inner;
gradient.tile(x, y, x_outer, y_outer, x_inner, y_inner, 64, 64);
```

等价的 C 代码：
```c
for (y_outer = 0; y_outer < H/64; y_outer++)
  for (x_outer = 0; x_outer < W/64; x_outer++)
    for (y_inner = 0; y_inner < 64; y_inner++)
      for (x_inner = 0; x_inner < 64; x_inner++)
        // process pixel at (x_outer*64 + x_inner, y_outer*64 + y_inner)
```

#### 向量化

将内层循环替换为 SIMD 指令（ARM 上使用 NEON，x86 上使用 SSE）：

```cpp
gradient.vectorize(x, 4);  // split x by 4, vectorize inner
```

在 ARM 上，这会生成 NEON `float32x4_t` 操作。在 x86 上，生成 SSE `__m128`。

**ARM 特定说明**：使用 `natural_vector_size<float>()`，对于 ARM NEON（128 位寄存器 / 32 位浮点 = 4 通道）返回 4。

#### 并行化

将独立的工作分配到多个线程：

```cpp
gradient.parallel(y);  // each scanline runs on a different thread
```

最佳实践：将分块索引融合为单个并行维度，以避免嵌套并行：

```cpp
Var tile_index;
gradient.tile(x, y, x_outer, y_outer, x_inner, y_inner, 64, 64)
    .fuse(x_outer, y_outer, tile_index)
    .parallel(tile_index);
```

#### 展开（Unrolling）

消除小型固定迭代次数的循环开销：

```cpp
gradient.unroll(x, 4);  // unroll x by factor of 4
```

适用于小型卷积核（3x3、5x5）和颜色通道循环（c=0..2）。

### 2.2 生产者-消费者融合

多级流水线的关键优化。如果不进行融合，每个阶段都会将中间结果写入 DRAM，然后下一个阶段再读取回来——6 次 DRAM 操作而不是 2 次。

#### `compute_root()`

在消费者之前计算所有生产者。最大内存占用，最小冗余计算。

```cpp
producer.compute_root();
```

#### `compute_at(consumer, var)`

在消费者遍历 `var` 的循环内按需计算生产者。平衡内存与重新计算。

```cpp
producer.compute_at(consumer, y);   // per-scanline
producer.compute_at(consumer, x);   // per-pixel (like inlining but with storage)
```

#### `store_root().compute_at(consumer, var)`

在最外层分配存储，在内层计算。实现循环缓冲区优化——Halide 使用位掩码寻址将存储折叠为 `2 x width` 条扫描线。

```cpp
producer.store_root().compute_at(consumer, y);
```

这是 **Spektrafilm 管线的最佳模式**：一次分配，按需计算，重用之前的扫描线。

#### 分块融合（推荐用于大图像）

```cpp
Var xo, yo, xi, yi, tile_idx;
consumer.tile(x, y, xo, yo, xi, yi, 64, 64)
    .fuse(xo, yo, tile_idx)
    .parallel(tile_idx);
producer.compute_at(consumer, xo);  // compute per-tile
```

每个分块计算其所需的生产者区域，使数据保持在缓存中。

### 2.3 混合策略（95% 的实际调度场景）

来自 Halide Lesson 8——规范的生产调度：

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

**为什么这对 Spektrafilm 有效**：管线有约 10 个阶段。使用 `store_at` + `compute_at`，每 16 行的条带在所有阶段中流动时数据保持在 L1/L2 缓存中。循环缓冲区仅保留每条中间结果的 2 条扫描线。

### 2.4 用于归约的 rfactor

对于关联归约（求和、乘积、直方图），`rfactor` 拆分归约域以实现并行：

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

**与 Spektrafilm 的相关性**：`einsum('ijk,lk->ijl')` 操作是对波长维度（K=81）的归约。这些可以表示为 Halide 归约，并在需要时使用 `rfactor` 进行并行化（尽管 K=81 足够小，串行归约可能已经足够快）。

---

## 3. 使用 CMake 进行 Android ARM 的 AOT 编译

### 3.1 Halide Generator 模式

Halide Generator 是定义 AOT 编译管线的标准方式。Generator 是一个封装了输入、输出、参数和调度的类：

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

### 3.2 CMake 集成

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

### 3.3 Halide 目标字符串

目标字符串控制代码生成。对于 Android：

| ABI | Halide 目标 | 备注 |
|-----|-------------|------|
| `arm64-v8a` | `arm-64-android` | 主要目标，NEON 自动启用 |
| `armeabi-v7a` | `arm-32-android` | 旧版，NEON 可选 |
| `x86_64` | `x86-64-android` | 仅用于模拟器 |
| `x86` | `x86-32-android` | 少见 |

可以追加额外的目标特性：`arm-64-android-no_runtime`（避免捆绑 Halide 运行时）、`arm-64-android-hvx`（用于 Hexagon DSP，此处不相关）。

### 3.4 构建 Generator 可执行文件

```cmake
# Compile the generator as an executable
add_executable(spectral_pipeline_gen
    generators/spectral_pipeline_generator.cpp
    tools/GenGen.cpp
)
target_link_libraries(spectral_pipeline_gen PRIVATE Halide::Halide)
```

然后调用：

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

这会生成：
- `spectral_pipeline.a` — 要链接的静态库
- `spectral_pipeline.h` — 包含函数签名的 C 头文件

### 3.5 生成的函数签名

生成的头文件暴露一个 C 链接函数：

```c
int spectral_pipeline(
    const halide_buffer_t *rgb_input,
    const halide_buffer_t *ccm_3x3,
    float strength,
    halide_buffer_t *xyz_output
);
```

对于元组值输出，会附加多个 `halide_buffer_t*` 参数。

### 3.6 JNI 集成模式

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

## 4. Python 绑定

### 4.1 安装

```bash
pip install halide  # PyPI package, currently v21.0.0
```

Python 绑定（`halide` 模块）通过 pybind11 封装同一个 C++ 编译器。支持 JIT 和 AOT 编译。

### 4.2 基本用法

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

### 4.3 在 Python 中进行调度

```python
# Vectorize and parallelize
f.vectorize(x, 4).parallel(y)

# Tiling
xo, yo, xi, yi = hl.Var('xo'), hl.Var('yo'), hl.Var('xi'), hl.Var('yi')
f.tile(x, y, xo, yo, xi, yi, 64, 64)
f.fuse(xo, yo, tile_idx).parallel(tile_idx)
```

### 4.4 重要事项：Fortran 排序

Halide 的 Python 绑定假设 **Fortran（列优先）排序**。NumPy 默认为 C（行优先）。始终需要转换：

```python
img_fortran = np.asfortranarray(img)
buffer = hl.Buffer(img_fortran)
```

Fortran 中的维度顺序是 `(channels, width, height)`——最左边的维度变化最快。这与 NumPy 的 `(height, width, channels)` 相反。

### 4.5 Spektrafilm 现有的 Halide Python 后端

文件 `src/spektrafilm/gpu/halide_backend.py` 已经使用 Python Halide 绑定来实现 JIT 内核：

```python
import halide as hl

# 3D trilinear LUT sampling
# rgb_to_xyz 3x3 matrix multiply
```

这些 JIT 内核在主机上运行。对于 Android，相同的算法将表示为 C++ Generator 并进行 AOT 编译。

---

## 5. 高斯模糊 / 可分离卷积

### 5.1 可分离 FIR 高斯（小标准差）

标准差为 `σ` 的 2D 高斯可以分解为两个 1D 通道——先水平后垂直。这将每像素的工作量从 O(r²) 减少到 O(2r)。

**Halide 实现：**

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
          .parallel(tile_index)
          .vectorize(xi, 4);

    // Key: compute horizontal pass per-tile of vertical pass
    blur_x.compute_at(blur_y, xi).vectorize(x, 4);

    return blur_y;
}
```

**调度说明**：水平通道按需计算，为垂直通道的每个分块服务。由于每个 `blur_y` 分块需要 `(2*radius+1)` 行 `blur_x`，我们只计算这些行——将水平中间结果保持在 L1 缓存中。

### 5.2 Spektrafilm 的 FIR 内核

来自 `gpu/kernels/filters.py`，Metal 内核展示了确切的算法：

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

镜像反射边界为：`yy = yy % (2*H); if (yy >= H) yy = 2*H - 1 - yy;`

在 Halide 中，使用 `BoundaryConditions::mirror_interior(input)` 自动完成此操作。

### 5.3 每通道标准差

Spektrafilm 为每个通道应用不同的标准差（R、G、B 可以有不同的模糊半径）。在 Halide 中，使用 `select` 表达：

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

或者更高效地，将每个通道作为单独的 Func 处理，并为每个通道分别调度。

---

## 6. 3D LUT 三线性插值

### 6.1 算法

给定大小为 `NxNxN`、具有 3 个输出通道的 3D LUT，以及一个输入 RGB 像素：

1. 将输入缩放到 LUT 坐标：`p = rgb * (N-1)`
2. 找到周围 8 个格点
3. 计算小数部分 `fx, fy, fz`
4. 三线性插值：8 个角的加权平均

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

### 6.2 Halide 实现

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

### 6.3 Spektrafilm 的 LUT 实现

来自 `gpu/kernels/lut.py`，Metal 内核对 2D LUT 使用 Mitchell-Netravali 三次插值，对 3D LUT 使用三线性插值。3D 版本与上述算法完全匹配。2D 版本使用 4x4 双三次内核，权重为 Mitchell-Netravali `(a=1/3, b=1/3)`。

### 6.4 2D LUT（Mitchell-Netravali 三次插值）

对于 2D 三次 LUT，Halide 版本使用 `RDom` 迭代 4x4 邻域：

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

## 7. IIR 滤波器：Young-van Vliet

### 7.1 算法

Young-van Vliet（YvV）4-tap IIR 高斯近似使用具有 4 个复数极点的递归滤波器。无论标准差大小，它都能以每像素 O(1) 的代价实现高斯模糊，非常适合大半径。

滤波器形式为：
```
y[n] = b0*x[n] + b1*x[n-1] + b2*x[n-2] + b3*x[n-3]
             - a1*y[n-1] - a2*y[n-2] - a3*y[n-3]
```

系数通过求多项式的根从所需标准差推导而来。

### 7.2 Halide IIR 实现

IIR 沿扫描方向本质上是顺序的。Halide 通过 `update` 定义支持这一点：

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

### 7.3 Spektrafilm 的 YvV 实现

来自 `utils/fast_gaussian_filter.py`，`_yvv_coeffs` 函数从标准差计算 4-tap 系数。Numba 内核应用：

1. **前向通道**：沿每行从左到右
2. **后向通道**：从右到左，结合前向结果
3. **可分离**：对垂直方向重复（转置、应用、转置）

Metal/CuPy 版本将水平和垂直通道作为单独的内核调度执行。

### 7.4 Spektrafilm 的关键洞察

IIR 滤波器沿 x 方向有顺序依赖。Halide 无法并行化此阶段的 x 维度。但是：

- **y 维度是独立的**——每条扫描线可以并行处理
- **通道是独立的**——R、G、B 可以并行处理
- **每个维度需要两次通道**（前向 + 后向）

对于垂直通道，转置数据，应用水平 IIR，再转置回来。或者使用直接垂直实现，配合 `compute_at` 保持一列状态。

---

## 8. FFT 集成

### 8.1 Halide FFT 状态

Halide **没有**内置 FFT。Halide 研究小组发表了一篇关于使用 Halide 生成 FFT 的论文（`halide-fft`），但这不是标准库组件。

### 8.2 Spektrafilm 的选项

| 选项 | 优点 | 缺点 |
|------|------|------|
| **空间域卷积** | 纯 Halide，无依赖 | 大内核时很慢（r > 50） |
| **FFTW** | 最快的 CPU FFT | GPL 许可证，不适合 Android 应用 |
| **Ne10 (ARM)** | ARM 优化，许可证宽松 | 维护有限 |
| **VkFFT** | 基于 Vulkan，速度很快 | 需要 Vulkan |
| **cuFFT** | 仅限 CUDA | Android 上不可用 |
| **自定义 Radix-2 FFT** | 可以用 Halide 的 update 定义表达 | 实现复杂 |

### 8.3 Spektrafilm 的扩散滤波器策略

现有代码库已将扩散滤波器 PSF 分解为高斯子组件。每个高斯可以作为以下方式应用：

1. **FIR**（小标准差，< 约 10px 半径）——纯 Halide 可分离卷积
2. **IIR**（大标准差，> 约 10px 半径）——Young-van Vliet 递归滤波器

这种分解**完全消除了大多数用例对 FFT 的需求**。`model/diffusion.py` 中的 `diffusion_filter_um` 函数已经使用此策略。

**建议**：对小内核使用 Halide FIR，对大内核使用 Halide IIR（YvV）。仅在性能分析表明扩散滤波器是空间方法无法解决的瓶颈时才添加 FFT。

---

## 9. 随机数生成

### 9.1 问题

Halide 是一种**确定性数据流语言**。它没有内置的随机数生成器。每个 `Func` 必须对相同的输入坐标产生相同的输出。

Spektrafilm 将 RNG 用于：
- **颗粒模拟**：每像素 Poisson + Binomial 随机偏差
- **眩光模拟**：每像素 Lognormal 随机偏差

### 9.2 解决方法：预生成随机缓冲区

标准方法是在单独的 C++ 通道中生成随机数，并将其作为输入缓冲区输入 Halide：

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

### 9.3 基于哈希的确定性噪声

对于确定性噪声（相同种子 -> 所有设备上相同结果），使用整数哈希函数作为伪随机数生成器。这些是纯 Halide 表达式：

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

### 9.4 Spektrafilm 的 RNG 策略

来自 `utils/fast_stats.py`，Numba 实现使用：
- **Poisson**：小 λ 使用 Knuth 算法，大 λ 使用高斯近似
- **Binomial**：小 n 使用直接模拟，大 n 使用高斯近似
- **Lognormal**：从均匀分布进行 Box-Muller 变换

**Android 推荐方案**：

1. 使用 C++ `<random>` 以固定种子生成随机缓冲区
2. 作为 `halide_buffer_t` 输入传递给 Halide 颗粒/眩光管线
3. 使用 `std::mt19937` 实现跨设备的可重现性
4. 对于预览模式，使用较低分辨率的随机缓冲区（通过双线性插值放大）

这是一种**两通道架构**：RNG 通道（C++）-> Halide 计算通道。

---

## 10. 自动调度器比较

### 10.1 可用的自动调度器

| 自动调度器 | 年份 | 方法 | 状态 |
|-----------|------|------|------|
| **Mullapudi2016** | 2016 | 启发式/解析（区间分析 + ILP） | 稳定，包含在 Halide 中 |
| **Li2018** | 2018 | 深度强化学习 | 研究阶段，不在主线中 |
| **Anderson2021** | 2021 | 树搜索 + 随机程序训练 | 稳定，包含在 Halide 中 |

### 10.2 Mullapudi2016（默认）

**工作原理**：使用基于区间分析和整数线性规划的模型来决定：
- 哪些阶段内联 vs. compute_root
- 基于缓存模型的分块大小
- 简单的向量化和并行化

**参数**：
```bash
autoscheduler=Mullapudi2016
autoscheduler.parallelism=8        # CPU cores
autoscheduler.last_level_cache_size=8388608  # L3 cache in bytes
autoscheduler.balance=40           # ratio of cache-miss cost to arithmetic cost
```

**优势**：调度速度快（秒级），确定性，适合简单管线。

**劣势**：仅进行分块、向量化、并行化。不支持行缓冲、存储重排序或归约分解。

### 10.3 Anderson2021（推荐）

**工作原理**：
1. 生成许多随机 Halide 程序
2. 在其测量性能上训练成本模型
3. 使用树搜索为新程序找到好的调度

**用法**：
```bash
./my_generator -o . -g MyPipeline \
    -p libautoschedule_anderson2021.so \
    -S Anderson2021 \
    target=arm-64-android \
    autoscheduler=Anderson2021
```

**优势**：对复杂管线产生更好的调度，处理更多优化维度。

**劣势**：较慢（分钟级），非确定性（不同运行可能产生不同调度）。

### 10.4 Spektrafilm 的建议

1. **从 Mullapudi2016 开始**用于初始开发——快速迭代，可预测
2. **切换到 Anderson2021**用于生产——在 Spektrafilm 的多级管线上性能更好
3. **手动调优关键内核**，如果自动调度器无法利用领域知识（例如 81 波长归约维度）
4. **将自动调度器作为起点**，然后根据性能分析手动调整

自动调度器无法处理：
- 归约分解（`rfactor`）——必须手动完成
- 行缓冲 / 循环缓冲区技巧——可能需要手动 `store_at` + `compute_at`
- 每通道调度——所有通道获得相同的调度

---

## 11. 常见陷阱

### 11.1 边界条件

**问题**：访问图像边界之外的像素会导致未定义行为或崩溃。

**解决方案**：始终用边界条件包装输入：
```cpp
Func clamped = BoundaryConditions::repeat_edge(input);      // clamp to edge
Func mirrored = BoundaryConditions::mirror_interior(input);  // mirror reflection
Func constant = BoundaryConditions::constant_exterior(input, 0.0f);  // pad with constant
```

**Spektrafilm 备注**：对高斯模糊使用 `mirror_interior`（匹配现有 Numba 实现的反射填充），对 LUT 采样使用 `repeat_edge`。

### 11.2 类型不匹配和溢出

**问题**：`uint8_t` 算术静默溢出。`int * int` 可能在提升之前就溢出。

**解决方案**：在算术运算之前转换为更宽的类型：
```cpp
Expr val = cast<int16_t>(input(x, y, c));
Expr result = cast<uint8_t>(clamp(val * 5 - neighbors, 0, 255));
```

**Spektrafilm 备注**：所有操作使用 `float32`（如 CLAUDE.md 精度要求所规定）。没有整数溢出风险，但注意 81 波长归约的 float32 精度限制。

### 11.3 使用 `parallel()` 时的竞态条件

**问题**：并行化写入共享内存的循环（例如归约更新）会导致竞态条件。

**解决方案**：
- 纯定义可以安全地并行化
- 对并行化变量进行归约的更新定义是**不安全的**
- 使用 `rfactor` 将关联归约分解为并行安全的形式

### 11.4 忘记对非平凡阶段使用 `compute_root()`

**问题**：默认调度会内联所有内容。对于昂贵的中间阶段，这会导致大量冗余计算。

**解决方案**：从对所有非平凡阶段使用 `compute_root()` 开始，然后从此处优化：
```cpp
// Start here
producer.compute_root();

// Then optimize: try compute_at for better locality
producer.compute_at(consumer, yi);
```

### 11.5 调度顺序很重要

**问题**：调度生产者时，必须引用消费者调度引入的 Var。如果先调度生产者，这些 Var 还不存在。

**解决方案**：从管线末端向后调度：
```cpp
// Schedule consumer first (introduces xo, yo, xi, yi)
consumer.tile(x, y, xo, yo, xi, yi, 64, 64).parallel(yo);

// Then schedule producer (can now reference xo)
producer.compute_at(consumer, xo);
```

### 11.6 `split()` 不会改变执行顺序

**问题**：初学者期望 `split(x, xo, xi, 4)` 会改变循环顺序。它不会——你必须之后使用 `reorder()`。

**解决方案**：使用 `tile()`（组合了 split + reorder），或显式重排序：
```cpp
f.split(x, xo, xi, 4).split(y, yo, yi, 4).reorder(xi, yi, xo, yo);
```

### 11.7 边界推理可能过度计算

**问题**：Halide 的边界推理可能会请求比严格需要更多的生产者数据，特别是对于复杂的模板模式。

**解决方案**：使用 `bound()` 约束输出范围：
```cpp
output.bound(x, 0, W).bound(y, 0, H).bound(c, 0, 3);
```

### 11.8 调试：`print_loop_nest()` 和 `trace_stores()`

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

### 11.9 Python 缓冲区排序

**问题**：Halide Python 使用 Fortran 排序（最左边 = 最内层）。NumPy 使用 C 排序（最右边 = 最内层）。

**解决方案**：始终转换：
```python
img = np.asfortranarray(img)  # or use hl.Buffer.make_interleaved()
```

---

## 12. Android 上的 Vulkan Compute

### 12.1 当前状态（2026）

Halide 有 Vulkan 后端，但它是**实验性的**，不推荐用于生产 Android：

- Vulkan 后端存在于 Halide 源码树的 `src/CodeGen_Vulkan*` 下
- 官方文档将 Vulkan 支持描述为"开发中"
- 后端目标是 Vulkan compute shader（非图形管线）
- Android Vulkan 支持的测试不如桌面 Vulkan 充分

### 12.2 目标字符串

```cpp
// Vulkan on Android (experimental)
target = "arm-64-android-vulkan"

// Or with specific Vulkan version
target = "arm-64-android-vulkan-v1_0"
```

### 12.3 限制

- **没有成熟的自动调度器**用于 Vulkan 目标——需要手动调度
- **内存管理**——Vulkan 缓冲区分配/释放是显式的且复杂
- **描述符集管理**——Halide 的 Vulkan 后端处理此问题，但存在边界情况
- **Shader 编译**——编译时必须可用 `glslc` 或 `dxc`
- **设备兼容性**——并非所有 Android 设备都有良好的 Vulkan compute 支持
- **同步**——Vulkan 需要显式屏障；Halide 为简单情况处理此问题

### 12.4 Spektrafilm 的建议

**默认先使用 CPU AOT Halide。** 这是安全的、经过充分测试的路径：

1. 第 1-2 阶段：CPU AOT（`target=arm-64-android`）
2. 第 3 阶段：在真实设备上分析性能。如果 CPU 对特定内核太慢，仅对这些特定内核尝试 Vulkan
3. 为 Vulkan 支持较差的设备保留 CPU 回退

Vulkan 后端应被视为优化目标，而非主要策略。

---

## 13. Spektrafilm 专用 Halide 代码示例

这些示例展示了如何在 Halide C++ 中表达 Spektrafilm 的核心内核。所有示例全程使用 `float32`（符合 CLAUDE.md 精度要求）。

### 13.1 光谱 Einsum（81 波长矩阵乘法）

Spektrafilm 的 `compute_density_spectral` 执行：`density_spectral[i,j,l] = Σ_k density_cmy[i,j,k] * channel_density[l,k]`

这是对波长维度（K=81）的矩阵乘法。

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

**为什么有效**：K=3 的归约非常小（3 次乘加）。Halide 会内联 RDom 循环并在 x 方向上向量化。81 个波长是独立的，在 y 并行循环中处理。

### 13.2 light_to_raw（较大归约的 Einsum）

`light_to_raw[i,j,l] = Σ_k light[i,j,k] * sensitivity[k,l]`

结构相同，但 sensitivity 是 `3x81` 而非 `3x81`：

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

**性能说明**：每像素 81 次乘加约为 162 FLOPs。对于 1 百万像素，约为 162M FLOPs——对于现代 ARM CPU（可达 >10 GFLOPS）来说微不足道。瓶颈是内存带宽，而非计算。调度应关注局部性。

### 13.3 1D 线性插值（密度曲线）

Spektrafilm 的 `interpolate_exposure_to_density` 通过每通道密度曲线映射曝光值：

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

**备注**：对于非均匀 x_axis 间距，使用二分搜索（通过带顺序循环的 `RDom` 或预计算均匀查找表）。

### 13.4 2D/3D LUT 插值

完整的 3D 三线性和 2D Mitchell-Netravali 实现见第 6 节。Spektrafilm 的关键细节是 LUT 坐标来自管线（而非直接来自像素），因此 LUT 采样是单独的阶段。

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

### 13.5 高斯 FIR + IIR 模糊

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

### 13.6 CCTF sRGB 编码/解码

sRGB 传递函数是一个分段幂曲线：

**解码**（编码 -> 线性）：
```
linear = encoded / 12.92                    if encoded ≤ 0.04045
linear = ((encoded + 0.055) / 1.055)^2.4    otherwise
```

**编码**（线性 -> 编码）：
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

**备注**：`pow()` 开销较大。对于 ARM，Halide 生成 `powf()` 调用。如果这是瓶颈，考虑对 2.4 指数使用多项式近似（或使用快速的 `exp2(log2(x) * 2.4)` 技巧）。

### 13.7 3x3 颜色矩阵乘法

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

### 13.8 高光增强（分段指数）

Spektrafilm 的 `boost_highlights` 应用一条分段曲线，使用指数函数增强亮像素：

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

**备注**：`exp()` 在 ARM NEON 上可通过数学库向量化。Halide 生成 `expf()` 调用，由 LLVM 自动向量化。

### 13.9 完整管线组合

完整的 Spektrafilm 管线在 Halide 中将这些 generator 组合成单个融合管线：

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

这种融合调度将所有中间结果保持在每个 64x16 分块的 L1/L2 缓存中。对于 1 百万像素图像，每个分块使用约 4MB 中间存储（在任何现代设备上都可管理）。

---

## 总结：Spektrafilm 移植建议

| 关注点 | 建议 |
|--------|------|
| **主要目标** | `arm-64-android`（CPU AOT） |
| **调度** | Anderson2021 自动调度器 + 手动调优 |
| **高斯模糊** | FIR（小 σ）+ YvV IIR（大 σ），通过 `compute_at` 融合 |
| **LUT 插值** | Halide `select` + `clamp`，向量化 |
| **光谱 einsum** | Halide `RDom` 对 K=3 或 K=81 归约 |
| **CCTF** | Halide `select` + `pow` |
| **RNG（颗粒/眩光）** | C++ `<random>` 预处理通道 -> Halide 缓冲区输入 |
| **FFT** | 避免——分解为高斯子组件 |
| **Vulkan** | 仅实验性，推迟到第 3 阶段及以后 |
| **精度** | 全程 `float32`，`atol=1e-6` 容差 |
| **内存** | 基于分块的处理，64x16 分块，循环缓冲区 |

---

## 参考文献

- Halide 教程：`https://halide-lang.org/tutorials/`
- Halide GitHub：`https://github.com/halide/Halide`
- Arm Halide Android Demo：`https://github.com/dawidborycki/Arm.Halide.AndroidDemo`
- Arm Halide 学习路径：`https://learn.arm.com/learning-paths/mobile-graphics-and-gaming/android_halide/intro/`
- Mullapudi 等人 2016："Automatically Scheduling Halide Image Processing Pipelines"
- Adams 等人 2019："Halide: a language and compiler for optimizing parallelism, locality, and recomputation in image processing pipelines"（PLDI 2013，更新版）
- Anderson 和 Amarasinghe 2021："Learning to Optimize Halide with Tree Search and Random Programs"
- Spektrafilm 移植计划：`docs/dev/halide-android-port-plan.md`
