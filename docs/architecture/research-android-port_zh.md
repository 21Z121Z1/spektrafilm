> 这是英文原文的中文翻译。权威版本请参考英文原文。

# Spektrafilm Android 移植 — 研究与策略

> 研究日期：2026-05-27
> 范围：将胶片光谱模拟引擎移植到 Android，同时保持零精度损失的 GPU 要求和色彩科学保真度。

---

## 2026-05-28 实施修订

下面的依赖表对当前仓库来说已过时。实施阶段已检查了 Chaquopy 17.0 和 Python 3.13 软件包索引：该索引未提供 Spektrafilm 声明的 `numpy~=2.4`，也未提供适用于所需 `scipy~=1.17` 的 Python 3.13 SciPy wheel。在通过实际 wheel 或项目自有原生构建验证之前，请将 Chaquopy 中 NumPy/SciPy/原生科学软件包的 "easy" 标签视为无效。

已实施的 Android 基础是原生 Kotlin/Compose 加上 `android/` 下的 JNI 诊断源代码。参见 `docs/dev/android-port-status-20260528.md`。本文档中后续的 Chaquopy 架构、依赖、Gradle 和桥接部分作为历史研究笔记保留；对于当前实施来说它们已被取代，除非新的软件包证据或项目自有的 Android wheel 使 Python 依赖图变得可行。

## 目录

1. [代码库可移植性评估](#1-codebase-portability-assessment)
2. [移植策略对比](#2-porting-strategies-comparison)
3. [Android 上的 GPU 计算](#3-gpu-compute-on-android)
4. [Android 上的色彩管理](#4-color-management-on-android)
5. [移动端 RAW/DNG 处理](#5-rawdng-processing-on-mobile)
6. [架构建议](#6-architecture-recommendations)
7. [性能考量](#7-performance-considerations)
8. [构建系统配置](#8-build-system-setup)
9. [推荐方案](#9-recommended-approach)

---

## 1. 代码库可移植性评估

### 当前架构

Spektrafilm 的处理流程结构如下：

```
Input RGB → Spectral Upsampling → Film Exposure → Development →
  [Optional: Printing → Development] → Scanning → Output RGB
```

关键模块及其 Android 可移植性：

| 模块 | 路径 | Android 可移植性 | 备注 |
|--------|------|---------------------|-------|
| **流水线编排器** | `runtime/pipeline.py` | 纯 Python | 完全可移植 |
| **光谱上采样** | `utils/spectral_upsampling.py` | NumPy/SciPy | Android 上需要 NumPy |
| **乳剂模型** | `model/emulsion.py` | NumPy + colour-science | colour-science 是纯 Python |
| **GPU 后端** | `gpu/backend.py` | 抽象协议 | 需要新的 Android 后端 |
| **NumPy 后端** | `gpu/numpy_backend.py` | NumPy + opt-einsum | 通过 Chaquopy 可移植 |
| **MLX 后端** | `gpu/mlx_backend.py` | 仅限 Apple | 不可移植 — 跳过 |
| **CuPy 后端** | `gpu/cupy_backend.py` | 仅限 CUDA | 不可移植 — 用 Vulkan 替代 |
| **色彩核心** | `gpu/kernels/color.py` | 后端可移植 | 后端存在即可移植 |
| **LUT 核心** | `gpu/kernels/lut.py` | 后端可移植 | 后端存在即可移植 |
| **密度核心** | `gpu/kernels/density.py` | 后端可移植 | 后端存在即可移植 |
| **滤波核心** | `gpu/kernels/filters.py` | 后端可移植 | 基于 FFT — 需要 pyfftw 替代方案 |
| **RAW 处理** | `utils/raw_file_processor.py` | rawpy + exiv2 + lensfunpy | 原生 C/C++ 库 — 需要 NDK 构建 |
| **IO** | `utils/io.py` | OpenImageIO | 重量级原生依赖 — 需要替代方案 |
| **GUI** | `spektrafilm_gui/` | PySide6/Qt | 不可移植 — 重写 UI |
| **HDR 处理** | `utils/hdr_photo.py` | NumPy + colour-science | 可移植 |
| **快速插值** | `utils/fast_interp.py` | Numba JIT | Android 上需要 Numba 或 C 重写 |
| **FFT 滤波** | `utils/fft_gaussian_filter.py` | pyfftw | 需要 pocketfft 或 Vulkan FFT |
| **自动曝光** | `utils/autoexposure.py` | NumPy | 可移植 |

### 关键依赖

| 依赖 | 类型 | Android 路径 | 难度 |
|-----------|------|-------------|------------|
| `numpy~=2.4` | C 扩展 | Chaquopy 预构建 | 简单 |
| `scipy~=1.17` | C/Fortran | Chaquopy 预构建 | 简单 |
| `colour-science~=0.4.6` | 纯 Python | Chaquopy pip | 简单 |
| `scikit-image~=0.26` | C 扩展 | Chaquopy 预构建 | 中等 |
| `opt-einsum~=3.4.0` | 纯 Python | Chaquopy pip | 简单 |
| `Pillow~=12.1` | C 扩展 | Chaquopy 预构建 | 简单 |
| `PyYAML~=6.0` | C 扩展 | Chaquopy 预构建 | 简单 |
| `lmfit~=1.3.2` | 纯 Python | Chaquopy pip | 简单 |
| `numba~=0.64` | LLVM JIT | **非常困难** | 困难 — ARM 上需要 LLVM |
| `OpenImageIO~=3.1.11` | 重量级 C++ | NDK 自定义构建 | 困难 |
| `pyfftw~=0.15.0` | C (FFTW3) | NDK 构建或替代 | 中等 |
| `rawpy~=0.26.1` | C++ (LibRaw) | NDK 构建 | 中等 |
| `exiv2~=0.18.1` | C++ | NDK 构建 | 中等 |
| `lensfunpy~=1.18.0` | C++ (lensfun) | NDK 构建 | 中等 |
| `napari~=0.6.6` | Qt 查看器 | **不可移植** | 跳过 — 移动端无需查看器 |
| `qtpy~=2.4` | Qt 抽象层 | **不可移植** | 用原生 Android UI 替代 |
| `pyside6~=6.9` | Qt 绑定 | **不可移植** | 用原生 Android UI 替代 |
| `matplotlib~=3.10` | 绘图 | **不可移植** | 跳过 — 移动端不需要 |
| `pyconify~=0.2.1` | 图标渲染 | 纯 Python | 简单 |

### 结论

约 60% 的代码库（光谱模型、色彩科学、流水线逻辑）是纯 Python + NumPy，可直接移植。其余约 40% 要么是需要 NDK 构建的原生 C/C++ 库，要么是需要完全重写的 GUI 代码。

---

## 2. 移植策略对比

### 策略 A：Python 封装（Chaquopy + 原生 UI）

**概念**：通过 Chaquopy 嵌入 Python 运行时，在 Python 中运行光谱处理流水线，用 Kotlin/Compose 原生构建 Android UI。

```
┌─────────────────────────────────────┐
│  Android App (Kotlin/Compose)       │
│  ┌───────────────────────────────┐  │
│  │  原生 UI 层                   │  │
│  │  - Jetpack Compose 视图       │  │
│  │  - CameraX 集成               │  │
│  │  - Material Design 3          │  │
│  └───────────┬───────────────────┘  │
│              │ Chaquopy 桥接         │
│  ┌───────────▼───────────────────┐  │
│  │  Python 运行时 (Chaquopy)     │  │
│  │  - spektrafilm 流水线         │  │
│  │  - numpy, scipy, colour       │  │
│  │  - rawpy, Pillow              │  │
│  └───────────┬───────────────────┘  │
│              │ JNI                   │
│  ┌───────────▼───────────────────┐  │
│  │  原生 C/C++ (NDK)             │  │
│  │  - Vulkan 计算后端             │  │
│  │  - OpenCV 用于变换             │  │
│  │  - FFTW3 或 pocketfft         │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
```

**优点**：
- 无需修改即可复用约 60% 的现有 Python 代码
- colour-science、scipy、numpy 均可通过 Chaquopy 使用
- 原生 Android UI 提供最佳用户体验
- 增量迁移路径：先用 Python，后续将热点路径优化为 C++
- Python 基于 dataclass 的参数系统无需修改即可工作

**缺点**：
- Chaquopy 使 APK 增大约 30-50 MB（Python 运行时 + 标准库）
- Python 执行速度比原生慢 5-50 倍（紧凑循环）
- Numba JIT 在 ARM Android 上极难运行
- 冷启动时间惩罚（Python 解释器初始化）
- 跨 Python/Kotlin 边界调试更困难
- 需要维护两个语言生态系统

**性能估算**：处理 24MP 图像的流水线：
- Python/NumPy 路径：约 8-15 秒（批量可接受，非实时）
- 使用 NDK C++ 热点路径：约 2-4 秒
- 使用 Vulkan 计算：约 0.5-1.5 秒

### 策略 B：原生 C++/Rust 核心 + Kotlin UI

**概念**：将计算核心移植到 C++ 或 Rust，用 Kotlin 构建 UI，通过 JNI/FFI 通信。

```
┌─────────────────────────────────────┐
│  Android App (Kotlin/Compose)       │
│  ┌───────────────────────────────┐  │
│  │  原生 UI 层                   │  │
│  └───────────┬───────────────────┘  │
│              │ JNI / C FFI           │
│  ┌───────────▼───────────────────┐  │
│  │  核心库 (C++ 或 Rust)         │  │
│  │  - 光谱处理流水线             │  │
│  │  - 色彩科学（移植）           │  │
│  │  - GPU 调度 (Vulkan)          │  │
│  │  - 类 NumPy 数组操作          │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
```

**优点**：
- 最佳性能（比 Python 快 10-100 倍）
- 更低的内存占用（无 Python 解释器）
- 确定性内存管理（Rust）或手动控制（C++）
- 无需 Python → C → GPU 桥接即可直接集成 Vulkan
- 更小的 APK 体积（约 5-15 MB）

**缺点**：
- **大量重写工作** — 必须移植 colour-science（15k+ 行）、scipy 函数、光谱上采样、乳剂模型
- colour-science 是一个没有 C 等价物的复杂库
- 无法使用 Python 科学计算生态系统
- C++ 内存安全问题；Rust 学习曲线
- 无热重载用于参数调整
- 预计 6-12 个月的移植工作量

**性能估算**：处理 24MP 图像的流水线：
- C++ + NEON：约 0.5-1.5 秒
- Rust + SIMD：约 0.4-1.2 秒
- 使用 Vulkan 计算卸载：约 0.2-0.5 秒

### 策略 C：Halide 用于图像处理核心

**概念**：使用 Halide（图像处理嵌入式 DSL）从单一流水线描述生成优化的 CPU/GPU 代码。

```
┌─────────────────────────────────────┐
│  Android App (Kotlin/Compose)       │
│  ┌───────────┬───────────────────┐  │
│  │  Halide 流水线 (AOT)          │  │
│  │  - 胶片模拟核心               │  │
│  │  - ARM 自动调度               │  │
│  │  - GPU 卸载 (OpenCL/Vk)       │  │
│  └───────────┬───────────────────┘  │
│              │ 编译后的 .so           │
│  ┌───────────▼───────────────────┐  │
│  │  Kotlin 粘合层 + Vulkan 计算   │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
```

**优点**：
- 一次编写，自动调度 CPU（ARM NEON）和 GPU（OpenCL/Vulkan）
- 非常适合图像处理流水线（专为此设计）
- AOT 编译为 .so 文件 — 无需 JIT
- 已在 Android 上验证（Google 内部使用 Halide）

**缺点**：
- Halide 是一门需要学习的独立语言
- 不适用于所有光谱操作（FFT、矩阵分解）
- 参数化模型仍需 Python 或 C++
- 社区比 Python/C++ 小
- 必须单独移植 colour-science 库
- 仅限于图像处理风格的核心（非通用计算）

**性能估算**：处理 24MP 图像的流水线：
- Halide CPU（ARM NEON，自动调度）：约 0.3-0.8 秒
- Halide GPU（OpenCL）：约 0.1-0.3 秒

### 策略 D：混合方案 — Chaquopy + NDK + Vulkan（推荐）

**概念**：组合策略。使用 Chaquopy 运行 Python 流水线编排和 colour-science 库。将热点路径（光谱 LUT 应用、矩阵变换、高斯模糊、FFT）卸载到 NDK C++ 配合 Vulkan 计算着色器。

```
┌─────────────────────────────────────────────┐
│  Android App (Kotlin/Compose)               │
│  ┌───────────────────────────────────────┐  │
│  │  UI 层 (Jetpack Compose)              │  │
│  │  - 参数滑块                           │  │
│  │  - 预览渲染                           │  │
│  │  - 图库 / 导出                        │  │
│  └───────────┬───────────────────────────┘  │
│              │ Chaquopy JNI 桥接             │
│  ┌───────────▼───────────────────────────┐  │
│  │  Python 编排层                        │  │
│  │  - params_schema (dataclasses)        │  │
│  │  - params_builder (digest)            │  │
│  │  - pipeline.py (编排器)               │  │
│  │  - colour-science (XYZ, RGB 等)       │  │
│  │  - model/ (乳剂、成色剂等)            │  │
│  └───────────┬───────────────────────────┘  │
│              │ ArrayBackend 协议             │
│  ┌───────────▼───────────────────────────┐  │
│  │  Android 后端 (NDK C++)               │  │
│  │  - AndroidBackend(ArrayBackend)       │  │
│  │  - Vulkan 计算着色器                  │  │
│  │  - NEON 优化核心                      │  │
│  │  - VkFFT 用于光谱 FFT                 │  │
│  └───────────┬───────────────────────────┘  │
│              │ Vulkan API                    │
│  ┌───────────▼───────────────────────────┐  │
│  │  GPU 硬件 (Adreno/Mali/PowerVR)       │  │
│  └───────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

**优点**：
- 复用现有 Python 流水线和 colour-science 代码
- 热点路径通过现有 ArrayBackend 协议获得原生/GPU 性能
- 增量式：先用 Python+NumPy 后端，后续添加 Vulkan 后端
- colour-science 库无需修改即可工作
- 同样的零精度损失保证（Vulkan 计算使用 float32）
- Kotlin UI 提供原生 Android 体验

**缺点**：
- 复杂的构建系统（Gradle + Chaquopy + NDK + CMake + Vulkan）
- APK 体积约 60-80 MB（Python 运行时 + 原生库）
- 仍有 Python 冷启动惩罚
- 需要维护三个代码库（Kotlin UI、Python 核心、C++ GPU）

---

## 3. Android 上的 GPU 计算

### 3.1 Vulkan 计算着色器

**状态**：Vulkan 1.1+ 在 95% 以上的活跃 Android 设备上受支持（2024+）。所有主要 SoC（Snapdragon 8 Gen 3、Exynos 2400、Dimensity 9300、Tensor G3、Kirin 9000s）均支持计算着色器。

**关键能力**：
- `VK_QUEUE_COMPUTE_BIT` — 专用计算队列
- `shaderStorageImageExtendedFormats` — 宽格式存储图像
- 共享内存：每个工作组 16-32 KB（移动端）
- 典型工作组大小：128-256 个调用

**Spektrafilm 的 Vulkan 计算流水线**：

```glsl
// 示例：3x3 矩阵乘法（RGB-to-XYZ 转换）
// 逐像素应用于整幅图像
#version 450
layout(local_size_x = 16, local_size_y = 16) in;

layout(set = 0, binding = 0, rgba32f) uniform readonly image2D inputImg;
layout(set = 0, binding = 1, rgba32f) uniform writeonly image2D outputImg;
layout(set = 0, binding = 2) uniform Params {
    mat3 colorMatrix;  // 例如 RGB_to_XYZ 矩阵
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

**LUT 应用着色器**（Spektrafilm 核心操作）：

```glsl
// 3D LUT 三线性插值应用
#version 450
layout(local_size_x = 16, local_size_y = 16) in;

layout(set = 0, binding = 0, rgba32f) uniform readonly image2D inputImg;
layout(set = 0, binding = 1, rgba32f) uniform writeonly image2D outputImg;
layout(set = 0, binding = 2) uniform sampler3D lutSampler;

layout(set = 0, binding = 3) uniform LUTParams {
    float lutScale;    // (resolution - 1) 用于归一化
    float lutOffset;
    float padding[2];
} lutParams;

void main() {
    ivec2 pos = ivec2(gl_GlobalInvocationID.xy);
    ivec2 size = imageSize(inputImg);
    if (pos.x >= size.x || pos.y >= size.y) return;

    vec4 pixel = imageLoad(inputImg, pos);
    // 归一化到 LUT 坐标 [0, 1]
    vec3 lutCoord = clamp(pixel.rgb, 0.0, 1.0);
    vec3 result = texture(lutSampler, lutCoord).rgb;
    imageStore(outputImg, pos, vec4(result, pixel.a));
}
```

**基于 FFT 的高斯模糊**（用于光晕、扩散、镜头模糊）：

Vulkan 没有原生 FFT，但有优秀的库：
- **VkFFT** — Vulkan FFT 库，在移动 GPU 上非常快
- **cuFFT 等价物**：VkFFT 提供类似 cuFFT 的 API
- 对于可分离高斯模糊，对于小核，使用计算着色器的两遍（水平 + 垂直）方法通常比 FFT 更快

### 3.2 OpenGL ES 3.1 计算着色器

比 Vulkan 兼容性更广（覆盖约 99% 的设备），但：
- 每个核心调度开销更高
- 内存控制不那么显式
- 仍可作为后备方案

```glsl
// GLES 3.1 计算着色器
#version 310 es
layout(local_size_x = 16, local_size_y = 16) in;
layout(rgba32f, binding = 0) uniform readonly highp image2D inputImg;
layout(rgba32f, binding = 1) uniform writeonly highp image2D outputImg;

void main() {
    ivec2 pos = ivec2(gl_GlobalInvocationID.xy);
    ivec2 size = imageSize(inputImg);
    if (pos.x >= size.x || pos.y >= size.y) return;
    vec4 pixel = imageLoad(inputImg, pos);
    // ... 处理 ...
    imageStore(outputImg, pos, pixel);
}
```

### 3.3 AGSL（Android 图形着色语言）

在 Android 13（API 33）中引入，AGSL 基于 SkSL（Skia 的着色语言）。它专为 UI 着色效果和片段着色设计，**非**通用计算。对 Spektrafilm 流水线的用途有限。

- 适用于：实时预览滤镜、UI 中的色彩分级效果
- 不适用于：多遍光谱模拟、LUT 计算、FFT
- 集成方式：通过 Jetpack Compose 中的 `RuntimeShader` 或 `android.graphics.Paint`

### 3.4 RenderScript 状态

RenderScript 在 **Android 12（API 31）中已被弃用**并正在被移除。Google 官方的迁移路径是：
1. **计算工作负载** → Vulkan 计算着色器
2. **图像滤镜（UI）** → AGSL `RuntimeShader`
3. **简单内建功能（模糊等）** → AGSL 或 OpenGL ES

### 3.5 Spektrafilm 推荐的 GPU 策略

**主要方案**：所有数组操作使用 Vulkan 计算着色器：
- 矩阵乘法（3x3 色彩变换）
- LUT 三线性插值
- 逐像素数学运算（exp、log10、pow、clip、where）
- 高斯模糊（可分离或通过 VkFFT 的 FFT）
- 光谱求和（通过归约实现 einsum 等价）

**后备方案**：通过 NumPy 在 CPU 上运行（现有的 `NumpyBackend`）

**为何不用 OpenGL ES**：Vulkan 对内存和同步的显式控制对于 Spektrafilm 的零精度损失要求至关重要。GLES 有更多隐式驱动行为，可能引入细微差异。

### 3.6 Vulkan 后端实现草图

```python
# 新文件：src/spektrafilm/gpu/vulkan_backend.py
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

## 4. Android 上的色彩管理

### 4.1 Android ColorSpace API（API 24+）

Android 提供了全面的 `android.graphics.ColorSpace` 类，包含与 Spektrafilm 相关的预定义命名色彩空间：

| 命名色彩空间 | 原色 | 传递函数 | Spektrafilm 用途 |
|---|---|---|---|
| `SRGB` | sRGB (D65) | sRGB OETF | 默认导出目标 |
| `LINEAR_SRGB` | sRGB (D65) | 线性 | 场景线性交换 |
| `EXTENDED_SRGB` | sRGB (D65) | sRGB（扩展范围） | HDR 预览中间值 |
| `DISPLAY_P3` | DCI-P3 (D65) | sRGB OETF | **主要预览目标** |
| `DCI_P3` | DCI-P3 (DCI 白点) | Gamma 2.6 | 电影参考 |
| `BT2020` | BT.2020 (D65) | BT.2020 OETF | 广色域导出 |
| `BT2020_PQ` | BT.2020 (D65) | PQ (ST 2084) | **HDR10 导出目标** |
| `BT2020_HLG` | BT.2020 (D65) | HLG | 广播 HDR 导出 |

**色彩空间转换**使用 CIE XYZ 作为配置文件连接空间：
```kotlin
// 将 Spektrafilm ACEScg 输出转换为 Display P3 用于预览
val connector = ColorSpace.connect(
    ColorSpace.get(ColorSpace.Named.LINEAR_SRGB),  // ACEScg 是场景线性的
    ColorSpace.get(ColorSpace.Named.DISPLAY_P3)
)
val displayP3Pixel = connector.transform(acesR, acesG, acesB)
```

### 4.2 显示色彩模式与 HDR

**Activity 级别启用**（manifest 或运行时）：
```xml
<activity
    android:name=".EditActivity"
    android:hasWideColorGamut="true"
    android:colorMode="wideColorGamut" />
```

**运行时显示查询**：
```kotlin
val display = windowManager.defaultDisplay
val isWideGamut = display.isWideColorGamut()      // API 26+
val isHdr = display.isHdr()                         // API 26+
val hdrCaps = display.hdrCapabilities               // HDR10, HLG, HDR10+, Dolby Vision
```

**窗口 HDR 余量**（API 34+）：
```kotlin
// 请求指定余量比的 HDR 渲染
window.setDesiredHdrHeadroom(2.0f)  // 2 倍 SDR 白 = 约 406 尼特峰值
```

**显示色彩模式常量**（`ActivityInfo`）：
- `COLOR_MODE_WIDE_COLOR_GAMUT` (1) — Display P3 色域
- `COLOR_MODE_HDR` (2) — HDR 渲染
- `COLOR_MODE_HDR10` (3) — HDR10 特定（10 位 PQ）

### 4.3 原生 HDR 流水线（AOSP SurfaceComposer）

原生合成器通过以下方式支持 HDR：
- **Dataspace**：`ADATASPACE_DISPLAY_P3`、`ADATASPACE_BT2020_PQ`、`ADATASPACE_BT2020_HLG`
- **HDR 元数据**：静态（MaxCLL、MaxFALL、母版显示）通过 `setHdrMetadata()`
- **HDR 余量**：`setDesiredHdrHeadroom(ratio)` 控制 HDR/SDR 亮度比
- **色彩空间无关模式**：`setColorSpaceAgnostic(true)` 用于自定义流水线控制

### 4.4 广色域的 EGL 扩展

通过 Vulkan 或 OpenGL ES 渲染时：
- `EGL_GL_COLORSPACE_SRGB_KHR` — sRGB 帧缓冲
- `EGL_GL_COLORSPACE_DISPLAY_P3_EXT` — Display P3 帧缓冲
- `EGL_GL_COLORSPACE_BT2020_PQ_EXT` — BT.2020 PQ (HDR10)
- `EGL_GL_COLORSPACE_BT2020_HLG_EXT` — BT.2020 HLG

### 4.5 通过 Chaquopy 在 Android 上使用 colour-science

`colour-science` Python 库可通过 Chaquopy 在 Android 上运行：

```python
# 通过 Chaquopy 在 Android 上运行
import colour
import numpy as np

# 所有 colour-science 函数均可使用：
xyz = colour.RGB_to_XYZ(rgb, "ACEScg", apply_cctf_decoding=False)
display_p3 = colour.RGB_to_RGB(xyz, "ACEScg", "Display P3")
```

**ICC 配置文件处理**：Spektrafilm 使用 ICC 配置文件进行输出编码。在 Android 上，ICC 配置文件可以嵌入输出文件中，但 Android 的显示合成器负责最终转换。流水线应以目标色彩空间（sRGB 或 Display P3）输出，让 Android 处理显示管理。

### 4.6 Spektrafilm 的广色域考量

流水线当前支持 ACEScg 作为工作空间。在 Android 上：

1. **预览渲染**：以 Display P3 输出（比 sRGB 更广，自 API 24 以来在旗舰 Android 设备上普遍支持）
2. **HDR 预览**：使用 `BT2020_PQ` dataspace 配合 `window.setDesiredHdrHeadroom()` 进行 HDR 再现预览
3. **导出**：支持 sRGB（通用）、Display P3、BT.2020 PQ (HDR10) 和 ACES2065-1 (EXR)
4. **ICC 配置文件**：使用现有的 `_ICC_PROFILES` / `_ICC_FILENAMES` 系统在导出图像中嵌入 ICC 配置文件
5. **HDR 显示**：使用 Android 的 HDR10 流水线（`COLOR_MODE_HDR10`）进行 HDR 再现模式，设置与 Spektrafilm HDR 场景能量元数据匹配的 PQ 传递函数
6. **传递函数**：BT.2020 PQ 使用 ST 2084（绝对亮度，最高 10,000 尼特）；BT.2020 HLG 使用混合对数伽马（SDR 白点 203 尼特）

---

## 5. 移动端 RAW/DNG 处理

### 5.1 Camera2/CameraX RAW 拍摄

Android 通过以下方式支持 RAW 拍摄：

**Camera2 API**（底层，更多控制）：
```kotlin
// 请求 RAW 拍摄
val captureRequest = camera.createCaptureRequest(
    CameraDevice.TEMPLATE_STILL_CAPTURE
).apply {
    set(CaptureRequest.STATISTICS_LENS_SHADING_MAP_MODE,
        CaptureRequest.STATISTICS_LENS_SHADING_MAP_MODE_ON)
    // 请求 RAW_SENSOR 输出
    addTarget(rawImageReader.surface)
}

// RAW_SENSOR 格式：Bayer 模式传感器数据
// RAW10：10 位打包 Bayer（更常见）
// RAW12：12 位 Bayer（更高质量）
```

**CameraX**（高层，更简单）：
```kotlin
// CameraX 支持 RAW 拍摄 (CameraX 1.4+)
val imageCapture = ImageCapture.Builder()
    .setCaptureMode(ImageCapture.CAPTURE_MODE_MAXIMIZE_QUALITY)
    .build()

// CameraX RAW 扩展（需要 CameraX 1.4+）
val rawCapture = RawImageCapture.Builder().build()
```

### 5.2 DNG 文件处理

**在 Android 上写入 DNG**：
```kotlin
// 使用 Adobe DNG SDK 或自定义 DNG 写入器
// DNG 基于 TIFF，带有特定标签
fun writeDng(
    rawSensorData: ByteArray,
    width: Int,
    height: Int,
    bayerPattern: Int,  // RGGB, BGGR 等
    blackLevel: IntArray,
    whiteLevel: Int,
    colorMatrix: FloatArray,  // 3x3，来自 CameraCharacteristics
    outputPath: String
) {
    // 写入带有 DNG 特定标签的 TIFF IFD：
    // - Tag 0xC612: DNGVersion
    // - Tag 0xC614: UniqueCameraModel
    // - Tag 0xC68D: BlackLevel
    // - Tag 0xC68E: WhiteLevel
    // - Tag 0xC621: ColorMatrix1
}
```

### 5.3 LibRaw 在 Android 上的使用

LibRaw（Python 的 `rawpy` 使用）可通过 NDK 为 Android 构建：

```cmake
# LibRaw 在 Android 上的 CMakeLists.txt
cmake_minimum_required(VERSION 3.18)
project(rawkit)

set(CMAKE_CXX_STANDARD 17)

# 从源码构建 LibRaw
add_subdirectory(libraw)

# JNI 桥接
add_library(rawkit SHARED rawkit_jni.cpp)
target_link_libraries(rawkit raw_static)
target_link_libraries(rawkit jnigraphics)  # 用于 Android Bitmap
```

**替代方案**：使用 Android 内建的 `android.media.ImageReader` 配合 `ImageFormat.RAW_SENSOR` 进行拍摄，然后用自定义 C++ 代码直接处理 Bayer 数据，而不使用 LibRaw。

### 5.4 Spektrafilm RAW 处理需求

当前 `raw_file_processor.py` 使用：
- `rawpy` — LibRaw 封装，用于 RAW 解码
- `exiv2` — EXIF/元数据读取
- `lensfunpy` — 镜头畸变校正
- `colour-science` — 色彩空间转换

对于 Android，推荐方案：
1. **拍摄**：使用 CameraX/Camera2 进行 RAW_SENSOR 拍摄
2. **解码**：通过 NDK 构建 LibRaw，或使用 Android 的 DNG Creator API（`android.media.ImageWriter` + DNG 元数据）
3. **元数据**：使用 Android 的 `ExifInterface`（自 API 24 起支持 DNG 标签）
4. **镜头校正**：通过 NDK 构建 lensfun，或使用 Android 的 `CameraCharacteristics` 获取逐镜头畸变数据
5. **色彩**：通过 Chaquopy 使用现有的 colour-science 库

---

## 6. 架构建议

### 6.1 推荐分层架构

```
┌──────────────────────────────────────────────────────────────┐
│                    Android 应用层                              │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  Jetpack Compose UI                                     │ │
│  │  ├── FilmStockSelector（预设网格）                       │ │
│  │  ├── ParameterControls（滑块、颜色选择器）               │ │
│  │  ├── ImagePreview（实时渲染预览）                        │ │
│  │  ├── ExportDialog（格式、质量、ICC 配置文件）             │ │
│  │  └── GalleryView（已处理图像）                           │ │
│  └───────────────────────┬─────────────────────────────────┘ │
│                          │ ViewModel / StateFlow              │
│  ┌───────────────────────▼─────────────────────────────────┐ │
│  │  处理服务 (Kotlin)                                       │ │
│  │  ├── ChaquopyBridge — Python 生命周期管理               │ │
│  │  ├── ImageRepository — 加载/缓存/编码图像               │ │
│  │  ├── ProgressTracker — 流水线进度回调                   │ │
│  │  └── ExportManager — 使用 WorkManager 的后台导出        │ │
│  └───────────────────────┬─────────────────────────────────┘ │
│                          │ Chaquopy JNI                       │
│  ┌───────────────────────▼─────────────────────────────────┐ │
│  │  Python 流水线 (Chaquopy)                               │ │
│  │  ├── params_schema — dataclass 定义                     │ │
│  │  ├── params_builder — digest_params, init_params        │ │
│  │  ├── pipeline — SimulationPipeline 编排器               │ │
│  │  ├── stages/ — Filming, Printing, Scanning              │ │
│  │  ├── model/ — Emulsion, Couplers, Diffusion, Grain      │ │
│  │  ├── colour-science — XYZ, RGB, 适应矩阵               │ │
│  │  └── utils/ — 光谱上采样、LUT、自动曝光                │ │
│  └───────────────────────┬─────────────────────────────────┘ │
│                          │ ArrayBackend 协议                  │
│  ┌───────────────────────▼─────────────────────────────────┐ │
│  │  计算后端                                                │ │
│  │  ├── NumpyBackend — 后备方案，NumPy + opt-einsum        │ │
│  │  ├── VulkanBackend — NDK C++, VkBuffer, 计算着色器      │ │
│  │  └── (未来) GLESBackend — OpenGL ES 3.1 后备            │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

### 6.2 处理模式

| 模式 | 分辨率 | 后端 | 用途 |
|------|-----------|---------|----------|
| **预览** | 约 1 MP | Vulkan | 实时滑块反馈 |
| **标准** | 最高 12 MP | Vulkan 或 CPU | 普通照片处理 |
| **全质量** | 24-48 MP | Vulkan（分块） | 全质量导出 |
| **批量** | 多张图像 | CPU（后台） | 处理图库 |

### 6.3 非破坏性编辑

参照 Snapseed/Lightroom 模型：

```kotlin
// 编辑配方 — 以 JSON 存储，按需应用
data class EditRecipe(
    val version: Int = 1,
    val filmStock: String = "kodak_portra_400",
    val params: RuntimePhotoParams,  // 来自 params_schema.py
    val crop: CropRegion? = null,
    val timestamp: Long = System.currentTimeMillis()
)

// 存储：仅存储配方，不存储已处理的像素
// 按需重新渲染：配方 → 流水线 → 输出像素
```

### 6.4 预览流水线

用于实时预览（滑块反馈 30+ FPS）：

1. **降采样**输入至约 1 MP（GPU 上快速双线性）
2. **运行流水线**处理降采样图像（Python + Vulkan 后端）
3. **放大**结果至显示大小（GPU 双线性）
4. **缓存**以参数哈希为键的结果

使用 Vulkan 后端，1 MP 预览耗时约 30-80ms，可实现实时滑块交互。

---

## 7. 性能考量

### 7.1 内存预算

| 组件 | 典型预算 | Spektrafilm 估算 |
|-----------|---------------|---------------------|
| 操作系统 + 系统服务 | 2-3 GB | 2-3 GB |
| 应用 UI 层 | 100-200 MB | 150 MB |
| Python 运行时 | 50-100 MB | 80 MB |
| 流水线缓冲区 (24MP) | 200-400 MB | 300 MB |
| Vulkan GPU 内存 | 200-500 MB | 400 MB |
| 光谱 LUT 表 | 50-200 MB | 100 MB |
| **总计** | | **约 1 GB** |

典型 Android 设备有 6-16 GB RAM，单个应用可用 2-4 GB。Spektrafilm 的 1 GB 估算可行但偏紧。

**缓解策略**：
- **分块处理**：以 200 万像素分块处理（现有的 `_should_tile_gpu_image`）
- **LUT 量化**：预览时将 LUT 分辨率从 256 降至 128
- **内存映射 LUT**：使用 `mmap()` 存储 LUT 表以允许操作系统分页
- **显式清理**：在流水线阶段之间调用 `del image` + `gc.collect()`（流水线在 `_pipeline_scan_film` 中已这样做）

### 7.2 电量与散热

| 操作 | 功耗 | 时长 (24MP) | 散热影响 |
|-----------|-----------|-----------------|----------------|
| Vulkan 计算流水线 | 高 (GPU) | 0.5-1.5s | 短暂峰值 |
| Python 编排 | 中 (CPU) | 1-3s | 中等 |
| FFT (pyfftw) | 高 (CPU+NEON) | 0.5-1s | 中等 |
| 完整流水线 (GPU) | 高 | 2-4s | 短暂峰值 |
| 完整流水线 (CPU) | 中 | 8-15s | 持续中等 |

**散热节流缓解**：
- 分块处理时在块之间调用 `synchronize()`（已实现）
- 添加让出点：块之间 `Thread.sleep(1)` 以让 SoC 冷却
- 显示进度指示器，让用户了解处理时间
- 使用 `PowerManager.isThermalStatusSupported()` 检测散热压力
- 检测到散热节流时降低处理质量

### 7.3 Python 解释器开销

| 阶段 | 时间 | 备注 |
|-------|------|------|
| 解释器冷启动 | 0.5-1.5s | 每次应用启动一次 |
| 模块导入（首次） | 1-3s | colour-science、scipy、numpy |
| 模块导入（缓存后） | 0.1-0.3s | 后续导入 |
| 流水线初始化 | 0.5-1s | LUT 预计算、后端初始化 |
| 每张图像处理 | 2-4s | 实际计算 |

**优化**：在图像处理会话之间保持 Python 进程存活。初始化一次，处理多张图像。

### 7.4 APK 体积预算

| 组件 | 体积 |
|-----------|------|
| Python 运行时 + 标准库 | 20-30 MB |
| numpy + scipy + colour-science | 30-50 MB |
| 原生 C++ 库（Vulkan 引擎） | 2-5 MB |
| LibRaw + lensfun + exiv2 | 3-5 MB |
| Kotlin/Compose UI + 资源 | 5-10 MB |
| Spektrafilm Python 代码 + 数据 | 2-5 MB |
| **总计** | **62-105 MB** |

这在照片处理应用的可接受范围内（Lightroom Mobile 约 150 MB，Snapseed 约 30 MB）。

---

## 8. 构建系统配置

### 8.1 Gradle 配置

```kotlin
// build.gradle.kts（应用级）
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
        minSdk = 26  // Android 8.0 — 广色域 + Vulkan
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"

        ndk {
            abiFilters += listOf("arm64-v8a", "armeabi-v7a")
        }

        // Chaquopy Python 配置
        python {
            version = "3.11"  // Chaquopy 支持 3.8-3.11
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

### 8.2 NDK 组件的 CMake 配置

```cmake
# src/main/cpp/CMakeLists.txt
cmake_minimum_required(VERSION 3.22)
project(spektrafilm_native)

set(CMAKE_CXX_STANDARD 20)

# 查找 Vulkan
find_package(Vulkan REQUIRED)

# VkFFT（Vulkan 的仅头文件 FFT 库）
add_subdirectory(third_party/vkfft)

# LibRaw（RAW 文件处理）
add_subdirectory(third_party/LibRaw)

# lensfun（镜头校正）
add_subdirectory(third_party/lensfun)

# 我们的 Vulkan 计算引擎
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

# RAW 处理桥接
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

# 将 GLSL 计算着色器编译为 SPIR-V
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

### 8.3 项目结构

```
spektrafilm-android/
├── app/
│   ├── build.gradle.kts
│   └── src/main/
│       ├── java/com/spektrafilm/android/
│       │   ├── SpektrafilmApp.kt          # Application 类
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
│       │   │   ├── PythonBridge.kt        # Chaquopy 桥接
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
│       ├── python/                       # Spektrafilm Python 代码
│       │   └── spektrafilm/
│       │       ├── __init__.py
│       │       ├── pipeline.py
│       │       ├── model/
│       │       ├── gpu/
│       │       │   ├── backend.py
│       │       │   ├── numpy_backend.py
│       │       │   └── vulkan_backend.py  # 新的 Android 后端
│       │       └── ...
│       └── AndroidManifest.xml
├── build.gradle.kts                       # 根构建文件
├── settings.gradle.kts
└── gradle.properties
```

### 8.4 Chaquopy 集成细节

```kotlin
// PythonBridge.kt — Chaquopy 集成
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
# spektrafilm_android_bridge.py — Python 桥接模块
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

## 9. 推荐方案

### 第一阶段：概念验证（2-3 周）

**目标**：在 Android 上使用 CPU 后端运行 Spektrafilm 流水线。

1. 使用 Chaquopy 搭建 Android 项目
2. 移植 Python 依赖（numpy、scipy、colour-science、Pillow）
3. 创建 `spektrafilm_android_bridge.py` 作为入口点
4. 初始使用 `NumpyBackend`（CPU）
5. 用小图像（约 1 MP）测试以验证正确性
6. 验证：输出与桌面 Python 输出匹配（float32 位相同）

**交付物**：能处理照片并保存结果的 APK。

### 第二阶段：原生 UI（2-3 周）

1. 使用 Material Design 3 构建 Jetpack Compose UI
2. 胶片选择器，带预设缩略图
3. 参数滑块（曝光、滤镜、颗粒等）
4. 降采样渲染的图像预览
5. 已处理图像的图库视图
6. 带格式选择的导出（JPEG、PNG、HEIF）

### 第三阶段：Vulkan 后端（4-6 周）

1. 在 NDK C++ 中搭建 Vulkan 计算基础设施
2. 将 `ArrayBackend` 操作实现为计算着色器：
   - `matmul` — 矩阵乘法
   - `exp`、`log10`、`pow`、`clip` — 逐元素操作
   - `einsum` — 专用归约核心
   - `where`、`maximum`、`fmax` — 条件操作
3. 实现 LUT 三线性插值着色器
4. 实现可分离高斯模糊着色器
5. 实现 VkFFT 集成用于基于 FFT 的滤波器
6. 创建带 JNI 桥接的 `VulkanBackend` Python 类
7. 测试：`np.allclose(vulkan_result, numpy_result, atol=1e-6)`

### 第四阶段：RAW 拍摄（2-3 周）

1. 集成 CameraX 用于照片拍摄
2. 通过 NDK 构建 LibRaw 用于 RAW 解码
3. 集成 lensfun 用于镜头校正
4. 添加 RAW → 流水线数据路径
5. 支持从外部应用导入 DNG

### 第五阶段：优化（2-3 周）

1. 分析并优化热点路径
2. 实现大图像的分块处理
3. 添加预览缓存（参数哈希 → 渲染位图）
4. 优化 Python 冷启动（预导入、模块缓存）
5. 内存分析与优化
6. 散热节流检测与自适应质量

### 第六阶段：完善（2-3 周）

1. HDR 显示支持（Display P3 输出、HDR10 元数据）
2. 导出中的 ICC 配置文件嵌入
3. 批量处理模式
4. 分享意图集成
5. 深色模式 / 动态色彩主题
6. App Bundle 优化（移除未使用的 ABI）

### 总预计时间线：14-21 周（3.5-5 个月）

---

## 附录 A：关键参考

### Android 开发
- [Android NDK Vulkan 指南](https://developer.android.com/ndk/guides/graphics/getting-started)
- [Android GPU 计算](https://developer.android.com/develop/background-work/gpu-compute)
- [Chaquopy 文档](https://chaquo.com/chaquopy/doc/current/)
- [CameraX 文档](https://developer.android.com/training/camerax)
- [Android 广色域](https://developer.android.com/training/wide-color-gamut)

### Vulkan 计算
- [Khronos Vulkan 指南 — 计算](https://docs.vulkan.org/guide/latest/compute.html)
- [VkFFT 库](https://github.com/DTolm/VkFFT)
- [Sascha Willems Vulkan 示例](https://github.com/SaschaWillems/Vulkan)
- [Android GPU Inspector](https://gpuinspector.dev/)

### 移动端图像处理
- [Snapseed 架构 (Google)](https://engineering.fb.com/)
- [Lightroom Mobile 架构 (Adobe)](https://developer.adobe.com/xmp/)
- [GPUImage (iOS/Android)](https://github.com/BradLarson/GPUImage)
- [Halide 语言](https://halide-lang.org/)

### Python 在 Android 上
- [Kivy 框架](https://kivy.org/doc/stable/guide/android.html)
- [BeeWare 项目](https://beeware.org)
- [Chaquopy GitHub](https://github.com/chaquopy/chaquopy)

---

## 附录 B：风险矩阵

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------------|--------|------------|
| Chaquopy 无法运行 colour-science | 低 | 严重 | 第一阶段早期测试；后备为 C++ 移植 |
| 目标设备不支持 Vulkan | 低 | 高 | 通过 NumpyBackend 的 CPU 后备 |
| Python 冷启动过慢 | 中 | 中 | 保持解释器存活；预热导入 |
| 内存压力导致 OOM | 中 | 高 | 分块处理；积极的缓冲区复用 |
| Numba 代码路径在 ARM 上不工作 | 高 | 中 | 用 C++ NDK 实现替代 |
| FFT 性能不足 | 低 | 中 | 使用 VkFFR；后备为可分离模糊 |
| APK 体积超过 Play Store 限制 | 低 | 低 | App Bundle；ABI 拆分 |
| 处理期间散热节流 | 中 | 中 | 自适应质量；块间让出 |
| colour-science API 变更破坏桥接 | 低 | 低 | 锁定版本；集成测试 |
| 特定 SoC 上的 Vulkan 驱动问题 | 中 | 中 | 逐设备测试；CPU 后备 |

---

## 附录 C：依赖迁移图

```
桌面 Python              →  Android (Chaquopy)      →  Android (NDK C++)
─────────────────────────────────────────────────────────────────────────
numpy                   →  numpy (Chaquopy 预构建)
scipy                   →  scipy (Chaquopy 预构建)
colour-science          →  colour-science (pip)
Pillow                  →  Pillow (Chaquopy 预构建)
opt-einsum              →  opt-einsum (pip)
PyYAML                  →  PyYAML (Chaquopy 预构建)
lmfit                   →  lmfit (pip)
numba                   →  ❌ (用 C++ 替代)         →  NEON intrinsics
OpenImageIO             →  ❌ (替代)                 →  自定义 OIIO-lite 或 PIL
pyfftw                  →  ❌ (替代)                 →  VkFFT 或 pocketfft
rawpy                   →  ❌ (通过 NDK 构建)        →  LibRaw
exiv2                   →  ❌ (通过 NDK 构建)        →  exiv2
lensfunpy               →  ❌ (通过 NDK 构建)        →  lensfun
napari                  →  ❌ (不需要)
qtpy / PySide6          →  ❌ (用 Kotlin 替代)
matplotlib              →  ❌ (不需要)
pyconify                →  pyconify (pip)
scikit-image            →  scikit-image (Chaquopy)   →  OpenCV 或自定义
```
