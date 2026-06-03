> 这是英文原文的中文翻译。权威版本请参考英文原文。

# Android 移植策略 -- 深度研究

> **日期：** 2026-05-28
> **范围：** 将 spektrafilm 的光谱胶片模拟移植到 Android 的六个维度的详细技术评估。基于之前的
> `research-android-port.md`（策略概览）和 `halide-android-port-plan.md`
>（AOT 生成器状态）。
>
> 每个章节按以下结构组织：**选项 → 建议 → 依据 → 风险**。

---

## 2026-05-28 实施修正

本文档对当前仓库依赖集已部分过时。
实施过程验证了官方 Chaquopy 17.0 对 Python 3.10-3.14 和 AGP 7.3-9.2 的支持，
但已检查的 Chaquopy Python 3.13 包索引无法满足 Spektrafilm 声明的依赖：
NumPy 可用版本为 `1.26.2`，而非 `numpy~=2.4`，
且 SciPy 在已检查的索引中未提供 Python 3.13 wheel。
因此 Android 基础架构未使用 Chaquopy。

已实现的基础架构位于 `android/` 目录下：AGP 9.2、Kotlin/Compose、
ViewModel/StateFlow、参数序列化、处理器合约和 JNI 诊断桥接源码。
参见 `docs/dev/android-port-status-20260528.md`。
除非根据当前包索引重新确认，否则将本文档中后续的 Chaquopy 代码片段和包支持表视为历史研究。

## 目录

1. [Python → Android：运行时策略](#1-python--android-runtime-strategies)
2. [Halide AOT 在 Android 上的应用](#2-halide-aot-on-android)
3. [Android 上的 NumPy/SciPy 替代方案](#3-numpyscipy-equivalents-on-android)
4. [Android 上的 GPU 计算](#4-gpu-compute-on-android)
5. [Android 上的图像 I/O](#5-image-io-on-android)
6. [Qt/PySide6 在 Android 上的应用及 UI 替代方案](#6-qtpyside6-on-android--ui-alternatives)

---

## 1. Python → Android：运行时策略

### 背景

Spektrafilm 基于 Python 3.13+，其中约 60% 为纯 Python/NumPy 代码（管线逻辑、
色彩科学、模型数据类），约 40% 为原生 C/C++（OpenImageIO、exiv2、
rawpy、Numba、pyfftw）。`ArrayBackend` 协议（`gpu/backend.py`）清晰地
将计算与编排分离，使得替换后端成为可能。

### 选项

#### 选项 A：Chaquopy（Android 内嵌 Python）

通过 Chaquopy Gradle 插件嵌入 CPython 3.13。Python 代码在
Android 进程内运行，通过 JNI 桥接与 Kotlin 通信。

| 方面 | 详情 |
|------|------|
| Python 版本 | 3.10、3.11、3.12、3.13、3.14（Chaquopy 17.0） |
| minSdk | 24（Android 7.0） |
| ABI | `arm64-v8a`（主要）、`x86_64`（模拟器）。Python ≤3.11 仅支持 32 位 |
| 包支持 | 纯 Python 包：全部。原生包：预构建 wheel 目录（numpy、scipy、Pillow、opencv 等） |
| APK 开销 | +30-50 MB（Python 运行时 + 标准库 + pip 包） |
| 冷启动 | 0.5-1.5 秒解释器初始化，1-3 秒首次模块导入 |
| 性能 | 紧密循环比 C++ 慢约 5-50 倍；原生支持的库（NumPy、OpenCV）以接近原生速度运行 |
| 多进程 | 不支持（System V IPC 不可用）；使用 `multiprocessing.dummy` |
| 文件 I/O | `os.environ["HOME"]` → 应用内部存储；数据文件在安装时提取 |

**构建集成：**
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

#### 选项 B：BeeWare / Briefcase

使用 Briefcase 将 Python 应用打包为原生 Android APK。在 Android 目标下
使用 Chaquopy 作为底层。

| 方面 | 详情 |
|------|------|
| 构建工具 | `briefcase create android` 然后 `briefcase build android` |
| Python 版本 | 与 Chaquopy 支持的版本一致 |
| UI 框架 | Toga（BeeWare 的原生小部件工具集）—— Android 小部件有限 |
| 包支持 | 与 Chaquopy 相同（pip 包） |
| 成熟度 | 简单应用已可生产使用；复杂原生 UI 有限 |

#### 选项 C：Kivy / Buildozer

跨平台 Python UI 框架，使用 OpenGL ES 渲染。Buildozer
用于 Android 打包。

| 方面 | 详情 |
|------|------|
| UI 范式 | OpenGL ES 画布，自定义小部件树（非 Material Design） |
| 性能 | UI 性能尚可；图像处理仍需 NumPy/原生库 |
| APK 开销 | +40-60 MB（Python + Kivy + SDL2） |
| 原生外观 | 否——自定义渲染 UI，非平台原生 |
| 包支持 | 原生包目录有限 |

#### 选项 D：完全 Kotlin 重写

使用 Kotlin/C++ 重写整个管线。无需 Python 运行时。

| 方面 | 详情 |
|------|------|
| 性能 | 最佳（比 Python 快 10-100 倍） |
| APK 大小 | 5-15 MB |
| 工作量 | 6-12 个月——必须移植 colour-science（15k+ 行）、所有光谱模型 |
| colour-science | 无 C/C++ 等效库存在；必须重新实现或预计算所有矩阵 |
| 风险 | 范围巨大；失去 Python 科学计算生态系统 |

### 建议

**选项 A：Chaquopy** 作为主要策略。理由：

1. **ArrayBackend 协议**意味着热路径（NumPy 操作）通过预构建的 numpy wheel 已经以原生速度运行。
   Python 编排开销与图像处理时间相比可以忽略不计。
2. **colour-science** 库无需修改即可工作——这是原生重写中最难替换的单一依赖。
3. **增量迁移**：从 `NumpyBackend`（CPU）开始，之后通过相同协议添加
   `HalideBackend` 或 `VulkanBackend`。
4. **Chaquopy 17.0 支持 Python 3.13**，与 spektrafilm 的要求匹配。

### 依据

- Chaquopy 17.0 文档确认支持 Python 3.13、预构建的 numpy
  和 scipy wheel，以及 Gradle 插件集成。
- `ArrayBackend` 协议（`gpu/backend.py:7-31`）清晰地将计算与编排分离——管线从不直接调用 numpy，仅通过
  `backend.exp()`、`backend.einsum()` 等方法。
- colour-science 是纯 Python 库，依赖 numpy——在 Chaquopy 上通过 pip 安装，无需原生编译。

### 风险

| 风险 | 严重程度 | 缓解措施 |
|------|----------|----------|
| Python 冷启动（1-3 秒） | 中 | 保持 Python 进程存活；在 `Application.onCreate()` 中预导入模块 |
| APK 大小（+30-50 MB） | 低 | 对照片应用可接受；使用 App Bundle 按 ABI 拆分 |
| Numba 不可用 | 高 | 用 Halide AOT 生成器替代（已完成 10 个内核）或 C++ |
| pyfftw 不可用 | 中 | 用 pocketfft（纯 C，可 NDK 构建）或 VkFFT 替代 |
| multiprocessing 不可用 | 低 | 管线为单线程；使用 threading 进行批处理 |
| Python/Kotlin 跨语言调试 | 中 | 使用结构化日志；Chaquopy 将 stdout/stderr 重定向到 Logcat |

---

## 2. Halide AOT 在 Android 上的应用

### 背景

Spektrafilm 已有 10 个 Halide AOT 生成器（位于 `src/spektrafilm/generators/`），
用于生成优化的内核。生成器使用 `Halide::Generator<>` 基类，
通过 CMake 的 `add_halide_library()` 进行编译。当前目标为 `host`；
Android 交叉编译需要目标为 `arm-64-android`。

### 选项

#### 选项 A：Halide AOT → 静态库 → NDK 链接

在构建主机上将 Halide 生成器编译为 `arm-64-android` 目标，生成
`.a` + `.h` 文件，通过 NDK CMake 链接到共享库 `libspektrafilm.so`。

**构建流程：**
```
[构建主机]                              [Android 设备]
generators/*.cpp ──► Halide 编译器 ──► .a + .h ──► NDK 链接 ──► libspektrafilm.so
  (x86-64)          （为目标运行         (arm-64)     (CMake)      （运行时加载）
                     生成器）
```

**CMake 集成：**
```cmake
# 为 Android 交叉编译 Halide 生成器
find_package(Halide REQUIRED)

add_halide_library(density_to_light
    FROM spectral_generator
    GENERATOR density_to_light
    TARGETS arm-64-android
    FEATURES neon
    AUTOSCHEDULER Halide::Adams2019
)

# ... 对所有 10 个生成器重复 ...

# 聚合目标
add_library(spektrafilm_halide_all INTERFACE)
target_link_libraries(spektrafilm_halide_all INTERFACE
    density_to_light light_to_raw compute_density_spectral
    gaussian_blur_fir gaussian_blur_iir
    cctf_encode cctf_decode highlight_boost
    interp_1d lut_2d_cubic
)

# JNI 包装器
add_library(spektrafilm SHARED jni_bridge.cpp)
target_link_libraries(spektrafilm PRIVATE spektrafilm_halide_all)
```

**Android 的 Halide 目标字符串：**

| ABI | Halide 目标 | 特性 |
|-----|-------------|------|
| `arm64-v8a` | `arm-64-android` | `neon`、`vfpv4` |
| `armeabi-v7a` | `arm-32-android` | `neon` |
| `x86_64` | `x86-64-android` | `sse4.1`、`avx`（模拟器） |
| `x86` | `x86-32-android` | `sse4.1`（旧版模拟器） |

#### 选项 B：Halide 自动调度器（ARM 优化）

使用 Halide 的自动调度器（`Adams2019` 或 `Mullapudi2016`）自动生成
针对 ARM Cortex-A 核心优化的调度方案。

```cmake
add_halide_library(gaussian_blur_fir
    FROM filter_generator
    GENERATOR gaussian_blur_fir
    TARGETS arm-64-android
    AUTOSCHEDULER Halide::Adams2019
)
```

自动调度器分析管线 DAG 并生成：
- NEON 向量化（128 位 SIMD，4 路 float32）
- 缓存分块循环嵌套
- 跨核心的并行循环调度
- 逐元素操作的融合

#### 选项 C：Halide AOT + Vulkan 后端（混合方案）

对 CPU 内核（NEON）使用 Halide AOT，对 GPU 调度使用 Vulkan 计算着色器。
`ArrayBackend` 协议在运行时进行选择。

```
┌─────────────────────────────────┐
│  ArrayBackend                   │
│  ├── HalideBackend (CPU/NEON)   │  ← 10 个 AOT 生成器
│  ├── VulkanBackend (GPU)        │  ← 计算着色器
│  └── NumpyBackend (回退方案)     │  ← Chaquopy numpy
└─────────────────────────────────┘
```

### 建议

**选项 A（Halide AOT → NDK 链接）** 作为主要计算路径，
**选项 C（Vulkan 后端）** 作为未来的 GPU 加速层。

理由：
1. 10 个 AOT 生成器已经存在并实现了核心热路径内核
2. Halide 的 ARM NEON 自动向量化比标量 C++ 快 3-4 倍
3. 设备上无需 JIT——所有编译在构建时完成
4. `atol=1e-6` 精度保证得以维持（全程 float32）

### 依据

- **Google 的使用**：Halide 在 Google 内部用于 Android 相机管线
 （Google Camera HDR+、Night Sight、Portrait Mode）。Halide 团队
  积极维护 `arm-64-android` 目标。
- **现有生成器**：10 个生成器覆盖了关键热路径：
  - 光谱：`density_to_light`、`light_to_raw`、`compute_density_spectral`
  - 滤波：`gaussian_blur_fir`（可分离 FIR）、`gaussian_blur_iir`（YvV 4-tap）
  - 色彩：`cctf_encode`、`cctf_decode`、`highlight_boost`
  - LUT：`interp_1d`、`lut_2d_cubic`（Mitchell-Netravali）
- **Halide CMake**：`add_halide_library()` 是 AOT 编译的官方 CMake 函数。
  它处理生成器编译、交叉编译和 `.a`/`.h` 输出。
- **ARM NEON**：Halide 的 `vectorize(x, 4)` 在 `float32` 上直接映射到 NEON
  128 位 SIMD 指令（`vmlaq_f32` 等）。自动调度器会自动处理。

### 风险

| 风险 | 严重程度 | 缓解措施 |
|------|----------|----------|
| Halide Android 交叉编译未经测试 | 高 | 为 Android 主机从源码构建 Halide；先用简单生成器测试 |
| ARM 上自动调度器的质量 | 中 | 对关键内核使用手动调度覆盖（生成器中已有） |
| 生成器覆盖缺口 | 中 | 3 个操作未覆盖：`rgb_to_xyz`（3x3 矩阵乘法）、`apply_lut_trilinear_3d`、grain RNG——添加生成器或使用 C++ |
| Halide 中的 IIR 递归 | 低 | 已在 `filter_generator.cpp` 中作为 RDom 更新定义实现 |
| 每个生成器的二进制大小 | 低 | 每个生成器产生约 50-200 KB `.a`；10 个生成器总计约 1-2 MB |
| Halide 版本兼容性 | 低 | 项目锁定 `halide>=21,<22`；生成器使用 v21 `Output<Buffer<>>` API |

### 构建验证步骤

```bash
# 1. 为主机构建 Halide（一次性）
git clone https://github.com/halide/Halide.git
cd Halide && git checkout v21.0.0
cmake -B build -DCMAKE_BUILD_TYPE=Release \
      -DHalide_TARGET=host \
      -DCMAKE_INSTALL_PREFIX=$HOME/halide-host
cmake --build build && cmake --install build

# 2. 为 Android 交叉编译生成器
cd src/spektrafilm/generators
cmake -B build-android \
      -DCMAKE_TOOLCHAIN_FILE=$ANDROID_NDK/build/cmake/android.toolchain.cmake \
      -DANDROID_ABI=arm64-v8a \
      -DANDROID_PLATFORM=android-26 \
      -DHalide_DIR=$HOME/halide-host/lib/cmake/Halide \
      -DTARGET=arm-64-android
cmake --build build-android

# 3. 验证输出
ls build-android/*.a build-android/*.h
# 预期：density_to_light.a、density_to_light.h、...（10 对文件）
```

---

## 3. Android 上的 NumPy/SciPy 替代方案

### 背景

Spektrafilm 的 `NumpyBackend` 使用：`np.exp`、`np.log10`、`np.maximum`、`np.clip`、
`np.matmul`、`np.power`、`np.where`、`np.abs`、`np.nan_to_num`，以及
`opt_einsum.contract` 用于 einsum 操作。`ArrayBackend` 协议
对这些进行了抽象，因此替代方案只需实现该协议即可。

### 选项

#### 选项 A：Chaquopy 预构建的 NumPy/SciPy

Chaquopy 为 `arm64-v8a` 提供预构建的 numpy 和 scipy wheel。这是
最简单的路径——现有的 `NumpyBackend` 无需修改即可工作。

| 包 | Chaquopy 状态 | 版本 |
|----|---------------|------|
| numpy | 预构建 wheel | ~2.4 |
| scipy | 预构建 wheel | ~1.17 |
| scikit-image | 预构建 wheel | ~0.26 |
| Pillow | 预构建 wheel | ~12.1 |
| opt-einsum | 纯 Python | ~3.4.0 |

**性能**：Android ARM64 上的 NumPy 使用 BLAS（OpenBLAS 或参考 BLAS）
进行矩阵运算。典型性能：
- `np.matmul`（1000x1000）：约 5-15 毫秒（BLAS 优化）
- `np.exp`（24MP float32）：约 50-100 毫秒（NEON 向量化）
- `opt_einsum.contract`（光谱 einsum）：约 10-30 毫秒

#### 选项 B：Eigen 用于 C++ 矩阵运算

Eigen 是一个仅头文件的 C++ 模板线性代数库。可在 NDK C++ 层中
用于矩阵运算。

```cpp
#include <Eigen/Dense>

// 3x3 色彩矩阵变换（逐像素）
Eigen::Matrix3f rgb_to_xyz;
rgb_to_xyz << 0.4124f, 0.3576f, 0.1805f,
              0.2126f, 0.7152f, 0.0722f,
              0.0193f, 0.1192f, 0.9505f;

// 处理像素缓冲区
for (int i = 0; i < num_pixels; i++) {
    Eigen::Vector3f pixel(pixels[i*3], pixels[i*3+1], pixels[i*3+2]);
    Eigen::Vector3f result = rgb_to_xyz * pixel;
    output[i*3] = result(0);
    output[i*3+1] = result(1);
    output[i*3+2] = result(2);
}
```

**优点**：不依赖 Python；通过 GCC/Clang 实现 NEON 自动向量化；
仅头文件（无需构建步骤）。

**缺点**：仅覆盖线性代数；无法替代逐元素的 NumPy 操作。

#### 选项 C：Vulkan 计算用于数组操作

使用 Vulkan 计算着色器进行所有数组操作（exp、log、matmul 等）。
这是性能最高的选项，但需要最多的基础设施。

详见[第 4 节：Android 上的 GPU 计算](#4-gpu-compute-on-android)。

#### 选项 D：xtensor（类 NumPy 的 C++ 数组库）

xtensor 在 C++ 中提供类似 NumPy 的 API，支持惰性求值和 SIMD。

```cpp
#include <xtensor/xarray.hpp>
#include <xtensor/xmath.hpp>

xt::xarray<float> density = ...;
xt::xarray<float> transmittance = xt::pow(10.0f, -density);
xt::xarray<float> light = transmittance * illuminant;
```

**优点**：对 NumPy 用户来说 API 熟悉；惰性求值；SIMD 支持。

**缺点**：未为 Android NDK 预构建；需要手动构建；社区较小。

### 建议

**选项 A（Chaquopy NumPy）** 用于初始移植，辅以
**选项 B（Eigen）** 在 NDK C++ 层中用于 Halide 生成器
未覆盖的操作（如小型矩阵运算、系数计算）。

`ArrayBackend` 协议意味着这在架构层面不是一个需要做的决定——`NumpyBackend` 通过 Chaquopy 立即可用，
`HalideBackend` 之后替换热路径。

### 依据

- Chaquopy 的包目录列出了 numpy、scipy 和 scikit-image 作为 `arm64-v8a` 的预构建 wheel。
- `NumpyBackend`（`gpu/numpy_backend.py`）是 60 行简单的 numpy 调用——Chaquopy 零修改即可使用。
- opt-einsum 是纯 Python——无需编译即可安装。

### 风险

| 风险 | 严重程度 | 缓解措施 |
|------|----------|----------|
| ARM 上的 BLAS 性能 | 中 | numpy 在 Chaquopy 上使用 OpenBLAS；matmul 比桌面慢约 2 倍。对热路径 matmul 使用 Halide |
| scipy.interpolate 可用性 | 低 | Chaquopy 预构建了 scipy；FITPACK 插值可用 |
| scikit-image 可用性 | 低 | Chaquopy 上已预构建；仅在 `crop_resize.py` 中用于 `resize` |
| Python 数组的内存压力 | 中 | 使用分块处理（已在 `backend.py:tiled_processing` 中实现） |

---

## 4. Android 上的 GPU 计算

### 背景

Spektrafilm 的 GPU 后端实现了 `ArrayBackend` 协议。目前：
- `MlxBackend` — Apple Silicon（Metal），不可移植
- `CupyBackend` — CUDA/ROCm，不可移植到移动端
- `HalideBackend` — CPU/向量化，可通过 AOT 移植

需要新的 Android GPU 后端用于性能关键的处理。

### 选项

#### 选项 A：Vulkan 计算着色器

Vulkan 1.1+ 在 95% 以上的活跃 Android 设备上受支持（2024+）。所有主要
SoC 都支持计算着色器。

| SoC | GPU | Vulkan | 计算着色器 |
|-----|-----|--------|-----------|
| Snapdragon 8 Gen 3 | Adreno 750 | 1.3 | 是 |
| Exynos 2400 | Xclipse 940 | 1.3 | 是 |
| Dimensity 9300 | Immortalis-G720 | 1.3 | 是 |
| Tensor G3 | Mali-G715 | 1.3 | 是 |

**能力：**
- `VK_QUEUE_COMPUTE_BIT` — 专用计算队列
- 共享内存：每个工作组 16-32 KB
- 典型工作组大小：128-256 调用
- `shaderStorageImageExtendedFormats` — 宽格式存储图像
- Float32 精度（所有现代移动 GPU 上符合 IEEE 754）

**示例：逐元素 exp 着色器：**
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

**集成框架：Kompute**（Linux 基金会项目）
- C++ SDK，支持 Android NDK
- Python 绑定（可通过 pip 安装）
- 支持移动端，动态加载 Vulkan
- Apache 2.0 许可证
- GitHub：`KomputeProject/kompute`

```cmake
# Android CMake 中的 Kompute
add_subdirectory(third_party/kompute)
target_link_libraries(spektrafilm PRIVATE kompute)
```

#### 选项 B：OpenGL ES 3.1 计算着色器

兼容性更广（约 99% 的设备），但调度开销更高。

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

**优点**：几乎支持所有设备；API 比 Vulkan 简单。

**缺点**：每次调度开销更高；内存控制不够显式；无
专用计算队列族。

#### 选项 C：NNAPI（Android 神经网络 API）

专为 ML 推理设计，非通用计算。对 Spektrafilm 的像素处理管线
用途有限。

**不推荐** — NNAPI 针对 ML 模型中的张量运算优化，
不适用于具有任意数据依赖的图像处理管线。

#### 选项 D：通过 POCL 使用 OpenCL

OpenCL 在大多数 Android 设备上不受原生支持（Qualcomm 在部分 Adreno 驱动上
放弃了 OpenCL 支持）。POCL（Portable Computing Language）
可以提供 CPU OpenCL 实现，但无法提供 GPU 访问。

**不推荐** — 厂商支持不一致且在下降。

### 建议

**选项 A：Vulkan 计算**，通过 Kompute 框架。理由：

1. **跨厂商**：适用于 Adreno（Qualcomm）、Mali（ARM）、Xclipse（Samsung）、
   PowerVR（Imagination）——所有现代 Android GPU。
2. **Float32 精度**：符合 IEEE 754，满足 spektrafilm 的零精度损失要求。
3. **Kompute** 将 Vulkan 样板代码从 500-2000 行减少到每次内核调度约 50 行。
4. **Android NDK 集成**：Kompute 通过 `KOMPUTE_OPT_ANDROID_BUILD=ON` CMake 标志
   和 NDK Vulkan 包装器头文件提供一流的 Android 支持。
5. **异步调度**：Kompute 支持多队列并行调度，
   适用于管线阶段。

### 依据

- Kompute 文档确认支持 Android NDK，提供了适用于 Android 构建的
  `CMakeLists.txt` 示例。
- Vulkan 计算被 Google 的 ML 框架（TensorFlow Lite GPU
  delegate）和 Android 上的相机管线所使用。
- `ArrayBackend` 协议可清晰映射到 Vulkan 计算调度：
  每个方法（`exp`、`matmul`、`einsum`、`clip` 等）变成一次计算着色器调度。

### 风险

| 风险 | 严重程度 | 缓解措施 |
|------|----------|----------|
| 旧设备上 Vulkan 不可用 | 低 | minSdk 26（Android 8.0）保证 Vulkan 1.0；使用 NumpyBackend 回退 |
| GPU 内存限制 | 中 | 分块处理（已实现）；典型移动 GPU 有 2-6 GB 共享内存 |
| 着色器编译延迟 | 中 | 在构建时预编译 SPIR-V；缓存管线对象 |
| 不同 GPU 间的精度差异 | 高 | 在每个目标 GPU 上验证 `atol=1e-6`；验证失败则回退到 CPU |
| Kompute 维护风险 | 低 | Linux 基金会支持；活跃社区；Apache 2.0 |
| 调试难度 | 中 | 在调试构建中使用 Vulkan 验证层；Android GPU Inspector |

### GPU 厂商特性

| 厂商 | GPU 系列 | 已知问题 |
|------|----------|----------|
| Qualcomm | Adreno 6xx/7xx | Vulkan 稳健；可能需要 `VK_KHR_portability_subset` |
| ARM | Mali-G7xx | 共享内存较低（16 KB）；float32 精度良好 |
| Samsung | Xclipse | 基于 AMD RDNA；Vulkan 1.3 支持良好 |
| MediaTek | Mali-Immortalis | 计算性能良好；需仔细测试精度 |
| Google | Mali（Tensor） | 与 ARM Mali 相同；标准 Android 参考 |

---

## 5. Android 上的图像 I/O

### 背景

Spektrafilm 的 I/O（`utils/io.py`）使用：
- **OpenImageIO（OIIO）**：EXR 读写，多通道支持
- **Pillow**：PNG、JPEG、TIFF
- **pillow-heif**：HEIC/HEIF 读写（由 HDR 照片支持隐含）
- **rawpy**：RAW 文件解码（LibRaw 包装器）
- **exiv2**：EXIF/IPTC/XMP 元数据
- **pyfftw**：用于高斯模糊的 FFT（非 I/O，但相关）

### 选项

#### 选项 A：平台 API + NDK 库

| 格式 | 读取 | 写入 | 库 |
|------|------|------|-----|
| **HEIC/HEIF** | Android 10+ `ImageDecoder` / NDK `AImageDecoder`（API 31+） | Android 10+ `HeifWriter` / libheif NDK | 平台 + libheif |
| **EXR** | tinyexr（仅头文件 C++） | tinyexr | tinyexr |
| **TIFF** | libtiff（NDK） | libtiff（NDK） | libtiff |
| **PNG** | Android `BitmapFactory` / stb_image | stb_image_write | 平台或 stb |
| **JPEG** | Android `BitmapFactory` | Android `Bitmap.compress()` | 平台 |
| **DNG/RAW** | LibRaw（NDK 构建） | 不适用（只读） | LibRaw |

**tinyexr**（EXR 支持）：
- 仅头文件：在一个 `.cpp` 文件中 `#define TINYEXR_IMPLEMENTATION`
- 读写 OpenEXR 多通道 float32 图像
- 无外部依赖
- GitHub：`syoyo/tinyexr`（积极维护）
- 非常适合 spektrafilm 的 EXR HDR 渲染输出

**libheif**（HEIC 支持）：
- 用于 HEIF/HEIC 读写的 C/C++ 库
- 需要 libde265（HEVC 解码器）或 dav1d（AV1 解码器）
- v1.17+ 中有 ARM NEON 优化
- 替代方案：Android 内置的 `AImageDecoder` NDK API（Android 12+）

**libtiff**（TIFF 支持）：
- 标准 C 库
- 可通过 NDK 获取或从源码构建
- 支持 32 位浮点 TIFF（光谱数据所需）

#### 选项 B：Chaquopy Pillow + 自定义原生扩展

使用 Pillow（Chaquopy 上已预构建）处理 PNG/JPEG/TIFF，通过 JNI 添加
用于 HEIC 和 EXR 的原生扩展。

```
Kotlin UI
    │
    ▼
Chaquopy Python
    ├── Pillow（PNG、JPEG、TIFF）     ← 预构建 wheel
    ├── tinyexr_jni（EXR）            ← NDK C++ → JNI → Python
    └── libheif_jni（HEIC）           ← NDK C++ → JNI → Python
```

#### 选项 C：Android Bitmap + 硬件缓冲区

使用 Android 的 `Bitmap` API 处理基本格式，使用 `AHardwareBuffer` 实现零拷贝
GPU 路径。

```kotlin
// 加载图像
val bitmap = BitmapFactory.decodeFile(inputPath)

// 转换为 float32 数组供管线使用
val pixels = FloatArray(width * height * 3)
val buffer = ByteBuffer.allocateDirect(pixels.size * 4)
bitmap.copyPixelsToBuffer(buffer)
// ... 通过 Chaquopy 传给 Python ...
```

**优点**：通过 `AHardwareBuffer` 实现零拷贝 GPU 路径；硬件加速
解码/编码。

**缺点**：仅限于 Android 支持的格式；不支持 EXR；仅 RGBA
（不支持多通道）。

### 建议

**混合方案：**
1. **HEIC**：使用 Android 内置的 `AImageDecoder` NDK API（Android 12+）
   进行读取；使用 libheif 写入并附带 HDR gain map 元数据。
2. **EXR**：使用 tinyexr（仅头文件，零依赖，float32 支持）。
3. **TIFF**：通过 NDK 使用 libtiff（支持 float32 多通道）。
4. **PNG/JPEG**：使用 Android `BitmapFactory` 读取，使用 stb_image_write
   写入（比 Pillow 更轻量）。
5. **RAW/DNG**：通过 NDK 构建使用 LibRaw。
6. **元数据**：使用 Android 的 `ExifInterface`（API 24 起支持 DNG 标签）
   或通过 NDK 构建 exiv2。

### 依据

- tinyexr 是单头文件，无依赖——可轻松集成到任何 NDK 项目中。
- Android 的 `AImageDecoder` NDK API（API 31+）提供硬件加速的
  HEIC 解码，无需外部依赖。
- libheif 积极维护（v1.17+），具有 ARM NEON 优化。
- 现有的 `utils/io.py` 使用 OIIO 进行 EXR 读写——tinyexr 是
  EXR 子集的直接替代。

### 风险

| 风险 | 严重程度 | 缓解措施 |
|------|----------|----------|
| HEIC HDR gain map 写入 | 高 | Android 的 `HeifWriter` 不支持 gain map；使用 libheif 并自定义元数据注入 |
| EXR 多通道支持 | 中 | tinyexr 支持多通道 EXR；验证通道布局与 OIIO 输出匹配 |
| OIIO 功能对等 | 中 | OIIO 处理多种格式；Android 需要按格式选择库 |
| RAW 格式覆盖 | 中 | LibRaw 覆盖大多数相机 RAW 格式；使用目标相机文件测试 |
| ICC 配置文件嵌入 | 低 | Pillow/PIL 支持 ICC 嵌入；Android 的 `ExifInterface` 处理 DNG 配置文件 |
| 大图像的内存 | 中 | 尽可能使用流式解码；GPU 路径使用分块处理 |

### Spektrafilm 的格式优先级

| 格式 | 优先级 | 原因 |
|------|--------|------|
| HEIC | 关键 | 带 gain map 的 HDR 照片导出（核心功能） |
| EXR | 关键 | HDR 渲染模式、ACES 交换 |
| TIFF | 高 | 无损中间格式、光谱数据存储 |
| PNG | 高 | SDR 导出、预览分享 |
| JPEG | 中 | 快速分享、低质量预览 |
| RAW/DNG | 中 | 相机导入（第 4 阶段功能） |

---

## 6. Qt/PySide6 在 Android 上的应用及 UI 替代方案

### 背景

Spektrafilm 的 GUI（`spektrafilm_gui/`）基于 PySide6（Qt 6.9）构建，
使用 napari 进行图像查看。GUI 有 24 个 Python 模块，涵盖：
参数编辑、配置文件同步、运行时控制、持久化、
主题和小部件原语。

### 选项

#### 选项 A：Qt for Android（C++ Qt，非 PySide6）

Qt 6.8+ 支持 Android 作为目标平台。然而，**PySide6 for Android
不受官方支持** —— Qt 的 Android 部署使用 C++/QML，不使用 Python。

| 方面 | 详情 |
|------|------|
| Qt for Android | 支持（C++ / QML） |
| PySide6 for Android | **不受支持** —— 无官方部署工具 |
| pyside6-android-deploy | 实验性；文档有限；APK 体积大 |
| QML UI | 声明式 UI 语言；Material Design 支持 |
| 构建复杂度 | 高（Qt + NDK + Android Gradle） |

#### 选项 B：Jetpack Compose（Kotlin）

Google 为 Android 提供的现代声明式 UI 工具集。原生外观和体验，
Material Design 3，优秀的工具支持。

| 方面 | 详情 |
|------|------|
| UI 范式 | 声明式（Kotlin DSL） |
| Material Design | 完整的 MD3 支持（动态颜色、主题） |
| 性能 | 优秀（Compose 运行时针对移动端优化） |
| 状态管理 | StateFlow / ViewModel —— 与 spektrafilm 的参数系统映射良好 |
| 图像预览 | Canvas 渲染，Coil 用于图像加载 |
| 开发速度 | 快（Android Studio 中实时预览） |

**spektrafilm 参数 UI 的 Compose 等效实现：**
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

#### 选项 C：Flutter（Dart）

跨平台 UI 框架。可在 Android 和 iOS 之间共享 UI 代码。

| 方面 | 详情 |
|------|------|
| 跨平台 | 单一代码库支持 Android + iOS |
| 性能 | 良好（Skia/Impeller 渲染） |
| 平台集成 | C/C++ 使用 FFI；Kotlin/Swift 使用平台通道 |
| Dart 生态系统 | 比 Kotlin 小；无科学计算库 |

#### 选项 D：WebView（混合方案）

使用 HTML/CSS/JS 在 WebView 中渲染 UI。通过 Chaquopy 桥接
与 Python 通信。

| 方面 | 详情 |
|------|------|
| UI 质量 | 良好（Web 技术成熟） |
| 性能 | 比原生慢；滚动不流畅 |
| 开发速度 | 快（Web 工具链） |
| 原生体验 | 差——不匹配 Android 习惯 |

### 建议

**选项 B：Jetpack Compose** 用于 Android UI。理由：

1. **原生 Android 体验**：Material Design 3、动态主题、
   正确的手势处理、系统集成（分享意图、通知）。
2. **状态管理**：Compose 的 `StateFlow` + `ViewModel` 直接映射
   到 spektrafilm 的 `RuntimePhotoParams` 数据类模式。
3. **Python 桥接**：Chaquopy 的 JNI 桥接将 Compose UI 连接到 Python
   管线。参数序列化为 JSON，传递给 Python，结果以文件路径或字节数组返回。
4. **性能**：Compose 以 60/120 FPS 渲染；图像预览使用
   `Bitmap` + `Canvas` 进行实时渲染。
5. **工具支持**：Android Studio 提供实时预览、布局检查器、
   性能分析器——比 Qt Creator 更适合移动开发。

### 依据

- Jetpack Compose 是 Google 推荐的新 Android 应用 UI 工具集
  （自 2021 年起）。Material Design 3 是当前的设计系统。
- spektrafilm GUI 的参数系统（`params_schema.py` 中的数据类）
  可清晰映射到 Compose 的状态模型——每个字段变成一个 `mutableStateOf`。
- Chaquopy 的 `Python.getModule().callAttr()` API 为管线桥接
  提供了清晰的 Kotlin <-> Python 互操作。
- 现有 GUI 的 24 个模块涵盖约 500 行小部件代码——
  在 Compose 中重写大约需要 2-3 周。

### 风险

| 风险 | 严重程度 | 缓解措施 |
|------|----------|----------|
| 需要完全重写 GUI | 中 | GUI 约 500 行小部件代码；Compose 等效约 300 行 |
| napari 不可用 | 低 | 用 Compose Canvas + 自定义图像查看器替代；napari 对移动端来说过于重量级 |
| Qt 知识无法迁移 | 低 | Compose 文档完善；Kotlin 在表达力上与 Python 相似 |
| 暗色模式 / 主题 | 低 | Material 3 内置动态颜色主题 |
| 图像预览性能 | 中 | 使用 `Bitmap` + 硬件加速 Canvas；预览时降采样 |
| 复杂的颜色选择器 UI | 中 | 使用 Compose Color Picker 库或自定义 Canvas 实现 |

### UI 架构映射

| Spektrafilm GUI 模块 | Compose 等效实现 | 工作量 |
|----------------------|-----------------|--------|
| `widgets.py`（参数滑块） | Compose `Slider`、`TextField` | 1 周 |
| `theme.py` + `theme_palette.py` | Material 3 `ColorScheme` | 2 天 |
| `controller.py`（状态管理） | `ViewModel` + `StateFlow` | 1 周 |
| `persistence.py`（保存/加载） | `DataStore` 或 JSON 文件 | 3 天 |
| `options.py`（胶片预设） | Compose `LazyVerticalGrid` | 3 天 |
| `napari_layout.py`（图像查看器） | 自定义 Compose `Canvas` | 1 周 |
| `polaroid_animation.py` | Compose `AnimatedVisibility` | 2 天 |
| `controller_runtime.py`（管线桥接） | Chaquopy `PythonBridge` 类 | 1 周 |

---

## 总结：推荐架构

```
┌──────────────────────────────────────────────────────────────┐
│  Android 应用（Kotlin + Jetpack Compose）                      │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  UI 层（Compose / Material 3）                           │ │
│  │  ├── EditScreen（参数滑块、胶片选择器）                    │ │
│  │  ├── PreviewCanvas（实时图像渲染）                        │ │
│  │  ├── ExportDialog（格式、质量、ICC 配置文件）              │ │
│  │  └── GalleryScreen（已处理图像）                          │ │
│  └───────────────────────┬─────────────────────────────────┘ │
│                          │ Chaquopy JNI                       │
│  ┌───────────────────────▼─────────────────────────────────┐ │
│  │  Python 管线（Chaquopy 17.0，Python 3.13）               │ │
│  │  ├── params_schema / params_builder（不变）              │ │
│  │  ├── pipeline.py → stages/（不变）                       │ │
│  │  ├── model/（乳剂、耦合剂等——不变）                      │ │
│  │  ├── colour-science（XYZ、RGB——不变）                    │ │
│  │  └── gpu/backend.py → ArrayBackend 协议                  │ │
│  └───────────────────────┬─────────────────────────────────┘ │
│                          │                                    │
│  ┌───────────────────────▼─────────────────────────────────┐ │
│  │  计算后端（ArrayBackend）                                │ │
│  │  ├── HalideBackend（10 个 AOT 生成器，ARM NEON）         │ │
│  │  │   └── CMake 交叉编译的 .a/.h                         │ │
│  │  ├── VulkanBackend（Kompute，计算着色器）——未来          │ │
│  │  └── NumpyBackend（Chaquopy numpy——回退方案）            │ │
│  └───────────────────────┬─────────────────────────────────┘ │
│                          │                                    │
│  ┌───────────────────────▼─────────────────────────────────┐ │
│  │  图像 I/O（NDK C++）                                     │ │
│  │  ├── tinyexr（EXR 读写）                                 │ │
│  │  ├── libheif（HEIC 读写，带 HDR gain map）               │ │
│  │  ├── libtiff（TIFF 读写）                                │ │
│  │  ├── LibRaw（RAW/DNG 解码）                              │ │
│  │  └── Android Bitmap（PNG/JPEG）                          │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

### 时间线估算

| 阶段 | 时长 | 交付物 |
|------|------|--------|
| 1. Chaquopy 概念验证 | 2-3 周 | 在 CPU（NumpyBackend）上运行管线的 APK |
| 2. Compose UI | 2-3 周 | 带参数编辑的原生 Android UI |
| 3. Halide AOT 集成 | 2-3 周 | 通过 10 个 AOT 生成器实现 NEON 优化计算 |
| 4. 图像 I/O | 1-2 周 | HEIC/EXR/TIFF/PNG 读写 |
| 5. Vulkan 后端 | 4-6 周 | 通过 Kompute 实现 GPU 计算（可选，用于性能优化） |
| 6. RAW 拍摄 | 2-3 周 | CameraX + LibRaw 集成 |
| 7. 完善与 HDR | 2-3 周 | HDR 显示、ICC 配置文件、批处理 |
| **总计** | **15-23 周** | 可投入生产的 Android 应用 |

---

## 附录：与现有文档的交叉引用

| 文档 | 路径 | 相关章节 |
|------|------|----------|
| Android 移植策略概览 | `docs/dev/research-android-port.md` | 架构、分阶段计划、色彩管理 |
| Halide Android 移植计划 | `docs/dev/halide-android-port-plan.md` | AOT 生成器状态、CMake 配置、JNI 计划 |
| Halide 深度研究 | `docs/dev/halide-deep-research.md` | 生成器 API、调度、ARM NEON |
| Halide 后端实现 | `docs/dev/halide-backend-implementation.md` | JIT 内核目录、验证结果 |
| GPU 色彩管理研究 | `docs/dev/research-gpu-color-management.md` | 色彩管线、ICC 配置文件、HDR |
