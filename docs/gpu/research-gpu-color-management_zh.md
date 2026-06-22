# GPU 加速与色彩管理研究

> 这是英文原文的中文翻译。权威版本请参考英文原文。

> **更新**（2026-05-28）：ACEScg ICC 映射和 HDR EXR 渲染输出的缺失问题已修复。macOS HDR HEIC 导出仍仅限 macOS 平台。

研究日期：2026-05-27

## ⚠️ 关键约束：零精度损失

所有 GPU 实现必须产生与 CPU/NumPy 输出在数值上完全一致的结果（在 float32 精度范围内，atol=1e-6）。不允许近似、不允许有损优化、不使用 float16，除非用户明确选择。每个 GPU 内核都需要一个断言 `np.allclose(gpu, cpu, atol=1e-6)` 的测试。如果某个后端无法匹配精度，则对该操作回退到 CPU。


## 概要

Spektrafilm 当前使用简洁的 `ArrayBackend` 协议（NumPy/MLX/CuPy）配合后端可移植的色彩内核、OpenImageIO 处理 I/O、以及 `colour-science` 处理色彩空间数学运算。该项目的光谱胶片模拟流水线在 GPU 加速方面结构良好，但存在若干差距：缺少 Display P3 的 ACES ICC 配置文件映射、HDR HEIC 导出仅限 macOS、以及没有 HDR EXR 渲染输出模式。本研究评估了跨平台 GPU 框架、色彩管理系统和 Python 集成模式，以指导下一阶段的开发。

---

## 1. 跨平台 GPU 计算框架

### 1.1 当前 Spektrafilm 架构

该项目已拥有简洁的后端抽象：

```python
# src/spektrafilm/gpu/backend.py
class ArrayBackend(Protocol):
    name: str
    supports_gpu: bool
    def asarray(self, value, dtype=None): ...
    def to_numpy(self, value): ...
    def matmul(self, a, b): ...
    def einsum(self, pattern, *values): ...
    # ... ~15 methods total
```

后端选择级联：`auto` -> MLX/Metal -> CuPy/CUDA -> NumPy 回退。

### 1.2 框架对比表

| 框架 | 平台 | Python 成熟度 | NumPy 兼容性 | Array API 标准 | 最佳用途 |
|-----------|-----------|-----------------|--------------|---------------|----------|
| **CuPy** | Linux/Windows (CUDA, ROCm) | 高 (v13+) | 直接替换 | 是 | NVIDIA/AMD GPU 科学计算 |
| **MLX** | macOS (Apple Silicon), Linux (CUDA) | 中 (v0.20+) | 部分 | 否 | Apple 统一内存，机器学习工作负载 |
| **JAX** | Linux/Windows/macOS (CPU/GPU/TPU) | 高 (v0.10+) | 良好 | 是 | 可微计算，TPU |
| **Taichi** | Linux/Windows/macOS (CPU/CUDA/Vulkan/Metal) | 高 (v1.7+) | 良好集成 | 否 | 自定义内核，仿真 |
| **PyTorch** | 所有平台 | 非常高 | 部分 | 是 | 深度学习，大型生态系统 |
| **wgpu-py** | 所有平台 (通过 Dawn/wgpu-native) | 中 (v0.31+) | 通过缓冲区 | 否 | WebGPU 计算着色器 |

### 1.3 Array API 标准

[Array API 标准](https://data-apis.github.io/array-api/latest/) 定义了可移植的数组接口。要点如下：

- **采用情况**：NumPy 2.0+、CuPy 13+、JAX 0.4+、scikit-learn 1.3+、SciPy 1.11+
- **互操作性**：`array-api-compat` 包允许代码在任何兼容后端上运行
- **关键操作**：`asarray`、`matmul`、`einsum`、`astype`、设备/类型提升规则
- **局限性**：不涵盖 FFT、稀疏数组或高级线性代数

对于 Spektrafilm，现有的 `ArrayBackend` 协议本质上已经是 Array API 的子集。正式采用该标准意味着：
- 使用 `array-api-compat` 进行自动后端调度
- 获得与 scikit-learn/scipy GPU 路径的互操作性
- 失去一些不在标准中的自定义方法（如 `fmax`、`nan_to_num`）

**建议**：保持当前的 `ArrayBackend` 协议。它精确覆盖了所需的操作，比采用完整标准更简单。如果 scipy/scikit-learn 互操作性变得重要，可在边界处用 `array-api-compat` 包装后端。

### 1.4 大型图像（100MP+）的 GPU 分块处理

对于超出 GPU 显存的超大图像，标准模式是：

```python
def tiled_processing(image, tile_size, process_fn, backend):
    """Process image in overlapping tiles to fit in VRAM."""
    h, w = image.shape[:2]
    overlap = 32  # pixels of overlap for filter kernels
    result = np.empty_like(image)

    for y in range(0, h, tile_size - overlap):
        for x in range(0, w, tile_size - overlap):
            y1, y2 = max(0, y), min(h, y + tile_size)
            x1, x2 = max(0, x), min(w, x + tile_size)

            tile = backend.asarray(image[y1:y2, x1:x2])
            processed = process_fn(tile)
            result[y1+overlap//2:y2-overlap//2, x1+overlap//2:x2-overlap//2] = \
                backend.to_numpy(processed)[overlap//2:-overlap//2 or None,
                                            overlap//2:-overlap//2 or None]

    return result
```

**关键考虑**：
- CuPy：使用 `cp.cuda.Device.memory_info()` 查询可用显存并自动调整分块大小
- MLX：统一内存意味着无需显式显存管理，但惰性求值可能导致内存峰值
- 重叠大小取决于滤波器核半径（高斯模糊需要 `3*sigma` 的重叠）
- 对于纯逐元素操作（如色彩变换），不需要重叠

### 1.5 GPU 回退链模式

当前 Spektrafilm 模式（已实现）：

```python
# Current: MLX -> CuPy -> NumPy
def select_backend(name="auto", *, precision="float32"):
    if name == "cpu": return NumpyBackend()
    if name in ("cupy", "cuda"): return CupyBackend(precision=precision)
    try: return MlxBackend(precision=precision)
    except BackendUnavailableError:
        try: return CupyBackend(precision=precision)
        except BackendUnavailableError:
            return NumpyBackend(fallback_reason="...")
```

**增强机会**：
- 添加 Taichi 作为中间选项（Vulkan 后端在无需 CUDA 的 Linux 上可用）
- 添加 JAX 作为 TPU/Google Cloud 场景的选项
- 添加 `wgpu-py` 用于无 CUDA 依赖的 WebGPU/Vulkan 计算

### 1.6 通过 Taichi 或 wgpu-py 进行 Vulkan 计算

**Taichi** (v1.7.4)：
- 将类 Python 代码 JIT 编译为 Vulkan/CUDA/Metal
- 在场维度上自动并行化
- 适合自定义光谱内核
- `ti.init(arch=ti.vulkan)` 在安装了 Mesa 或 NVIDIA 驱动的 Linux 上工作

```python
import taichi as ti
ti.init(arch=ti.vulkan)

@ti.kernel
def apply_color_matrix(pixels: ti.types.ndarray(), matrix: ti.types.ndarray(),
                       result: ti.types.ndarray()):
    for i, j in ti.ndrange(pixels.shape[0], pixels.shape[1]):
        for k in ti.static(3):
            result[i, j, k] = 0.0
            for l in ti.static(3):
                result[i, j, k] += pixels[i, j, l] * matrix[l, k]
```

**wgpu-py** (v0.31.0)：
- 通过 wgpu-native (Rust) 实现的纯 Python WebGPU 绑定
- WGSL 计算着色器以获得最大性能
- 在 Linux (Vulkan)、macOS (Metal)、Windows (D3D12) 上工作
- 比 Taichi 更底层但更具可移植性

```python
import wgpu
from wgpu.gui.auto import WgpuCanvas

# Create compute shader in WGSL
shader_code = """
@group(0) @binding(0) var<storage, read> input: array<f32>;
@group(0) @binding(1) var<storage, read_write> output: array<f32>;

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) id: vec3<u32>) {
    let i = id.x;
    if (i < arrayLength(&input)) {
        // Apply sRGB transfer function
        let x = input[i];
        output[i] = select(
            1.055 * pow(x, 1.0/2.4) - 0.055,
            x * 12.92,
            x <= 0.0031308
        );
    }
}
"""
```

### 1.7 性能特征：MLX vs CuPy vs Taichi

| 操作 | CuPy (CUDA) | MLX (Metal) | Taichi (Vulkan) | NumPy (CPU) |
|-----------|-------------|-------------|-----------------|-------------|
| 3x3 矩阵 @ 50MP | ~0.5ms | ~0.8ms | ~1.2ms | ~50ms |
| 高斯模糊 (sigma=5) | ~2ms | ~3ms | ~4ms | ~200ms |
| 4096 条 LUT 插值 | ~1ms | ~1.5ms | ~2ms | ~30ms |
| 光谱上采样 | ~5ms | ~8ms | ~10ms | ~500ms |

*基于 50MP (8640x5760) float32 图像的估算。实际时间取决于硬件。*

**关键洞察**：对于 Spektrafilm 的流水线（矩阵变换 + LUT 插值 + 逐元素操作），在同等硬件上 CuPy 比 MLX 快约 2-3 倍，但 MLX 的统一内存消除了 Apple Silicon 的传输开销。

---

## 2. 色彩管理系统

### 2.1 当前 Spektrafilm 色彩架构

该项目使用分层方法：
1. **colour-science** (v0.4.7)：RGB 色彩空间定义、矩阵提取、CCTF 传递函数
2. **OpenImageIO** (v3.1.13)：格式无关的 I/O 并保留元数据
3. **PIL/Pillow**：带 ICC 嵌入的 PNG/JPEG 写入
4. **exiv2** (pyexiv2)：EXIF/IPTC/XMP 元数据管理
5. **自定义内核**（`gpu/kernels/color.py`）：后端可移植的 CCTF 编码/解码

支持的色彩空间：sRGB、Display P3、DCI-P3、Adobe RGB、ProPhoto RGB、BT.2020、ACES2065-1、ACEScg。

### 2.2 ICC 配置文件处理

当前状态（`utils/io.py`）：
- **ICC 嵌入**：适用于 PNG (iCCP 块)、JPEG (APP2)、TIFF (ICCProfile 标签)
- **ICC 读取**：通过与捆绑配置文件的字节比较进行匹配，然后通过描述匹配
- **ICC 来源**：Elle Stone V2 配置文件（工作空间）、Saucecontrol V2/V4（Display P3、DCI-P3）
- **ACES 配置文件**：ACES2065-1 和 ACEScg 都有线性 ICC 配置文件（V2，g10 TRC）

**差距**：没有 Display P3 线性 ICC 配置文件。当前的 `_ICC_FILENAMES` 将 `("Display P3", False)` 映射为空，回退到使用不同来源的 `_ICC_PROFILES`。

**建议**：添加指向线性 Display P3 配置文件的 `("Display P3", False)` 条目，或使用 `PIL.ImageCms.createProfile("DISPLAYP3")` 生成一个。

### 2.3 ACES 工作流

当前 ACES 支持：
- ACES2065-1 (AP0，线性，场景参考交换空间)
- ACEScg (AP1，线性，场景参考工作空间)
- 两者均视为线性（无 CCTF），不对负值/高光进行裁剪

**ACES 2.0 (ACESnext) 进展**：
- ACES 2.0 引入了改进色域映射的新输出变换
- 仍使用 ACES2065-1 作为交换空间
- 新的 ACEScg 仍是推荐的工作空间
- OCIO 2.4+ 内置 ACES 2.0 配置支持

**完整 ACES 集成的缺失项**：
1. 无 OCIO 集成（当前直接使用 colour-science）
2. 无 ACES 输出变换（ODT/RRT）用于显示参考输出
3. 无 ACES 输入变换（IDT）用于相机原生文件
4. 无 ACEScct/ACEScc 对数工作空间用于调色

### 2.4 HDR 标准与增益图

当前 HDR 支持（`utils/hdr_photo.py`）：
- 仅限 macOS 的 HEIC 导出（通过 Swift/CoreImage）
- 增益图方法：SDR 基础 + 逐像素增益图
- `HDRPhotoMapping` 数据类，约 40 个参数
- 基于胶片/相纸特性的配置文件感知 HDR 曲线拟合
- 两种增益图模式：`luma`（单通道）和 `rgb`（逐通道）

**ISO 21496-1（增益图 HDR）**：
- 标准化了 Apple/Adobe 增益图方法
- 单个文件包含 SDR 基础图像 + 增益图元数据
- 向后兼容：SDR 设备看到基础图像
- 增益图存储每像素的 `log2(hdr_luminance / sdr_luminance)`
- 元数据包括：`gainMapMin`、`gainMapMax`、`gamma`、`offsetSDR`、`offsetHDR`、`hdrCapacityMin`、`hdrCapacityMax`

**Apple 的实现** (iOS 17+)：
- 带嵌入式增益图的 HEIC
- CoreImage 中的 `kCGImageAuxiliaryDataTypeHDRGainMap`
- SDR 基础使用 Display P3 色彩空间，HDR 渲染使用线性色彩空间

**Adobe 的实现** (Lightroom/Camera Raw)：
- 带 MPF（多图片格式）辅助图像的 JPEG
- XMP 中符合 ISO 21496-1 的元数据

**Spektrafilm 的需求**：
1. 跨平台增益图编码（不仅仅是 macOS CoreImage）
2. JPEG/HEIC 的 ISO 21496-1 元数据生成
3. EXR HDR 渲染输出导出（当前仅支持场景线性归档）
4. 用于 HDR 显示输出的 BT.2100 PQ/HLG 编码

### 2.5 色调映射算子

`hdr_photo.py` 中的当前实现：
- **逻辑回退（Logistic rolloff）**：基于相纸曲线的自定义肩部压缩
- **对数回退（Logarithmic rolloff）**：非配置文件感知模式的回退方案
- **SDR 基础映射**：带 `sdr_paper_white` 缩放的对数肩部
- **路径到白色（Path-to-white）**：基于 Smoothstep 的高 EV 值时朝向亮度的去饱和

**行业标准色调映射算子**：

| 算子 | 类型 | 用途 | 参考文献 |
|----------|------|----------|-----------|
| **ACES (RRT+ODT)** | 胶片风格 | 场景参考到显示 | AMPAS 标准 |
| **Reinhard** | 全局/局部 | HDR 摄影 | Reinhard et al. 2002 |
| **Filmic (Hable)** | 胶片风格 | 游戏渲染 | John Hable, Uncharted 2 |
| **BT.2446** | HDR->SDR | 广播 HDR 转换 | ITU-R BT.2446 |
| **BT.2390** | EETF | HDR 显示映射 | ITU-R BT.2390 |
| **显示参考** | 逐显示 | 内容自适应 | Dolby Vision IQ |

**Spektrafilm 的方法设计得很好**：基于相纸曲线的回退建立在实际摄影相纸响应曲线的基础上（来自富士胶片/柯达数据的 Logistic 拟合）。对于胶片模拟用例，这比通用的 Reinhard/ACES 更具真实感。

### 2.6 色域映射

当前实现：`_apply_hdr_color_recovery()` 中的亮度保持色度压缩。

```python
# Current: compress overshooting channels while preserving luminance
max_rgb = np.max(hdr_rgb, axis=-1)
overshoot = max_rgb > max_headroom
if np.any(overshoot):
    hdr_luma = luminance_y(hdr_rgb)
    scale = (max_headroom - hdr_luma[overshoot]) / np.maximum(
        max_rgb[overshoot] - hdr_luma[overshoot], eps
    )
    hdr_rgb[overshoot] = hdr_luma[overshoot, None] + (
        hdr_rgb[overshoot] - hdr_luma[overshoot, None]
    ) * scale[..., None]
```

**色域映射策略**：

| 策略 | 描述 | 适用场景 |
|----------|-------------|-------------|
| **绝对比色** | 裁剪到目标色域边界 | 打样匹配 |
| **相对比色** | 缩放白点，裁剪其余 | 标准打印模拟 |
| **感知** | 压缩整个色域以适应 | 跨色域显示 |
| **饱和度** | 保持饱和度而非色相 | 商业图形 |
| **CSS Color 4 色域映射** | 基于 Oklch 的感知映射 | Web/现代工作流 |

**CSS Color 4 方法**（由 ColorAide 库使用）：
```python
# Perceptual gamut mapping in Oklch space
# 1. Convert to Oklch (perceptual lightness, chroma, hue)
# 2. Reduce chroma until in-gamut, preserving L and h
# 3. If still out of gamut, reduce L slightly
```

**对 Spektrafilm 的建议**：当前的亮度保持方法适用于 HDR 高光处理。对于跨色域 SDR 输出（如 BT.2020 -> sRGB），可考虑通过 colour-science 或 coloraide 添加基于 Oklch 的感知映射。

### 2.7 OpenColorIO (OCIO) 集成

**OCIO** (v2.x) 是 VFX/动画行业色彩管理的行业标准：
- 被 Nuke、Blender、DaVinci Resolve、Maya、Houdini 使用
- 通过 GLSL/Metal/CUDA 提供 GPU 加速的色彩变换
- ACES 配置由 ASWF 维护
- Python 绑定：`PyOpenColorIO`

**Python API 模式**：
```python
import PyOpenColorIO as OCIO

config = OCIO.Config.CreateFromFile('config.ocio')
# Or use built-in ACES config:
config = OCIO.Config.CreateFromBuiltinConfig('ocio://studio-config-latest')

# Create a processor for a specific transform
processor = config.getProcessor('ACEScg', 'sRGB - Display')
cpu = processor.getDefaultCPUProcessor()

# Apply to pixel data
import numpy as np
pixels = np.random.rand(100, 100, 3).astype(np.float32)
result = cpu.applyRGB(pixels.flatten()).reshape(pixels.shape)
```

**OCIO GPU 加速**：
```python
# GPU-accelerated transform (requires OpenGL/Metal/CUDA context)
gpu = processor.getDefaultGPUProcessor()
# Creates GLSL/Metal shader code for the transform chain
shader_desc = gpu.extractGpuShaderInfo()
```

**何时使用 OCIO vs colour-science**：
- **OCIO**：当需要 ACES 输出变换、基于 LUT 的工作流或跨应用一致性时
- **colour-science**：当需要光谱计算、自定义传递函数或细粒度控制时

**建议**：添加可选的 OCIO 集成以支持 ACES 输出变换。保留 colour-science 用于光谱运算。OCIO 将替换 `gpu/kernels/color.py` 中用于 ACES 工作流的手动 CCTF 编码/解码。

---

## 3. Python GPU 图像处理模式

### 3.1 colour-science (v0.4.7)

主要的色彩数学库。Spektrafilm 使用的关键功能：

```python
import colour

# RGB colour space definitions
cs = colour.RGB_COLOURSPACES['ACEScg']
M = cs.matrix_RGB_to_XYZ  # 3x3 matrix
wp = cs.whitepoint  # (x, y) chromaticity

# Chromatic adaptation
cat = colour.adaptation.matrix_chromatic_adaptation_VonKries(
    colour.xy_to_XYZ(src_wp),
    colour.xy_to_XYZ(dst_wp),
    transform="CAT02",
)

# Transfer functions
linear = colour.cctf_decoding(srgb_encoded)  # sRGB -> linear
encoded = colour.cctf_encoding(linear)  # linear -> sRGB

# Colour conversion pipeline
xyz = colour.RGB_to_XYZ(rgb, 'ACEScg', 'D65', illuminant='D65',
                         chromatic_adaptation_transform='CAT02')
srgb = colour.XYZ_to_RGB(xyz, 'sRGB', 'D65')
```

**GPU 集成模式**（Spektrafilm 的做法）：
1. 使用 colour-science 在 CPU 上预计算矩阵
2. 将矩阵作为常量传输到 GPU
3. 使用后端的 matmul/einsum 应用逐像素变换
4. 将传递函数实现为后端的逐元素操作

这是正确的模式——colour-science 仅支持 CPU，但其矩阵/常量提取很快且只执行一次。

### 3.2 OpenImageIO (OIIO) Python 绑定 (v3.1.13)

Spektrafilm 中的当前用法：

```python
import OpenImageIO as oiio

# Reading
in_img = oiio.ImageInput.open(filename)
spec = in_img.spec()
pixels = in_img.read_image(oiio.TypeDesc("float"))
icc_bytes = spec.getattribute("ICCProfile")
color_space = spec.get_string_attribute("oiio:ColorSpace")

# Writing
spec = oiio.ImageSpec(width, height, 3, oiio.TypeDesc("float"))
spec.attribute("oiio:ColorSpace", "ACEScg")
spec.attribute("chromaticities", oiio.TypeDesc("float[8]"), chromaticities)
spec.attribute("ICCProfile", oiio.TypeDesc("uint8[N]"), icc_array)
out = oiio.ImageOutput.create(filename)
out.open(filename, spec)
out.write_image(data)
```

**OIIO 尚未使用的功能**：
- `ImageBuf`：带 ImageBufAlgo 函数的内存图像操作
- `ImageCache`：用于巨大图像的透明多分辨率缓存
- `TextureSystem`：过滤纹理查找（适用于光谱 LUT）
- 色彩转换：`oiio.ImageBufAlgo.colorconvert()` 配合 OCIO 集成
- `oiiotool`：用于批处理的 CLI（可用于验证）

**OIIO + OCIO 集成**：
```python
# OIIO can use OCIO for color transforms
import OpenImageIO as oiio
buf = oiio.ImageBuf("input.exr")
oiio.ImageBufAlgo.colorconvert(buf, buf, "ACEScg", "sRGB - Display")
buf.write("output.png")
```

### 3.3 数组后端互操作性

当前 Spektrafilm 的后端无关代码模式：

```python
# Pattern: pre-compute on CPU, transfer to GPU, compute, transfer back
matrix_np = colour.RGB_COLOURSPACES['ACEScg'].matrix_RGB_to_XYZ
matrix_gpu = backend.asarray(matrix_np)  # One-time transfer
result_gpu = backend.matmul(pixels_gpu, matrix_gpu.T)  # GPU compute
result_np = backend.to_numpy(result_gpu)  # Transfer back when needed
```

**零拷贝模式**：
- CuPy：`cp.asarray(numpy_array)` 拷贝到 GPU；`cp.asnumpy(gpu_array)` 拷贝回来
- MLX：统一内存意味着 `mx.array(numpy_array)` 在 Apple Silicon 上可能共享内存
- NumPy：已在 CPU 上，`asarray` 通常是视图

**流式/异步模式**（用于流水线重叠）：
```python
# CuPy: async transfer with streams
stream = cp.cuda.Stream()
with stream:
    gpu_data = cp.asarray(cpu_data)
    result = process(gpu_data)
# Stream sync happens automatically on to_numpy()
```

### 3.4 HDR 图像 I/O 模式

**EXR (OpenEXR)**：
```python
# Scene-linear archive (current Spektrafilm default)
spec.attribute("oiio:ColorSpace", "ACEScg")
spec.attribute("chromaticities", oiio.TypeDesc("float[8]"), chromaticities)
spec.attribute("whiteLuminance", 203.0)  # cd/m² reference white

# HDR rendition (what the code-review recommended adding)
# Use hdr_rendition mode to prepare gain-mapped data before writing
```

**带增益图的 HEIC/HEIF**（当前仅限 macOS）：
```python
# Pattern: prepare SDR + HDR renditions, encode via platform tool
renditions = prepare_hdr_photo_renditions(image_data, mapping=mapping)
# sdr_rgb: [0, 1] range, CCTF-encoded
# hdr_rgb: [0, headroom] range, linear
# headroom: typically 2-8x SDR white
```

**带增益图的 JPEG (ISO 21496-1)**：
```python
# Cross-platform approach using libheif or custom MPF encoding
# 1. Write SDR base as primary JPEG
# 2. Write gain map as auxiliary image (MPF or EXIF auxiliary)
# 3. Write ISO 21496-1 metadata in XMP
```

### 3.5 GPU 上的光谱处理

Spektrafilm 的核心光谱模拟包括：
1. **光谱上采样**：RGB -> 反射率光谱（31+ 个采样点）
2. **光源乘法**：光谱 × 光源功率
3. **灵敏度积分**：光谱 × 锥体灵敏度曲线
4. **密度曲线**：通过 LUT 插值的胶片/相纸响应

这些操作非常适合 GPU：
```python
# Spectral LUT interpolation (backend-portable)
def interp_spectral_lut(wavelengths, reflectance, lut_wavelengths, lut_values, backend):
    """Interpolate spectral LUT at each pixel's reflectance."""
    # Shape: (H, W, 31) for reflectance, (N, 3) for LUT
    # Use backend-specific interpolation
    if hasattr(backend, 'interp'):  # CuPy
        return backend.interp(wavelengths, lut_wavelengths, lut_values)
    else:  # MLX/NumPy - use searchsorted
        indices = backend.searchsorted(lut_wavelengths, wavelengths)
        # Linear interpolation
        ...
```

---

## 4. 库版本汇总

| 库 | 当前版本 | 最新稳定版 | Spektrafilm 使用情况 |
|---------|----------------|---------------|------------------|
| CuPy | 13.x / ROCm 7.0 | 13.4+ | GPU 后端 |
| MLX | 0.20+ (Linux 上支持 CUDA) | 0.22+ | GPU 后端（macOS 主力） |
| colour-science | 0.4.7 | 0.4.7 | 色彩数学，RGB 色彩空间 |
| OpenImageIO | 3.1.13 | 3.1.13 | 图像 I/O |
| OpenColorIO | 2.4.x | 2.4.1 | 尚未使用 |
| Taichi | 1.7.4 | 1.7.4 | 尚未使用 |
| wgpu-py | 0.31.0 | 0.31.0 | 尚未使用 |
| JAX | 0.10.1 | 0.10.1 | 尚未使用 |
| NumPy | 2.x | 2.2+ | CPU 后端 |
| OpenCV | 4.13.0 | 4.13.0 | 未使用 |
| ColorAide | 最新 | 最新 | 未使用（colour-science 的替代方案） |
| Pillow | 最新 | 最新 | PNG/JPEG 写入 |

---

## 5. 建议

### 5.1 GPU 加速

**优先级 1：保持当前 ArrayBackend 架构**
现有协议简洁、经过充分测试，且覆盖所有所需操作。不要用 Array API 标准替换它——自定义协议更聚焦。

**优先级 2：添加 Taichi 作为可选后端**
Taichi 的 Vulkan 后端在无需 CUDA 的 Linux 上提供 GPU 加速。这填补了"MLX（仅限 macOS）"和"CuPy（仅限 NVIDIA）"之间的空白。

```python
# Proposed addition to backend.py
def _select_taichi_backend(*, precision: str) -> ArrayBackend:
    from spektrafilm.gpu.taichi_backend import TaichiBackend
    return TaichiBackend(precision=precision)

# In select_backend():
# auto cascade: MLX -> CuPy -> Taichi/Vulkan -> NumPy
```

**优先级 3：为 100MP+ 图像添加 GPU 分块处理**
光谱模拟流水线处理全帧图像。当 GPU 内存不足时添加自动分块。

### 5.2 色彩管理

**优先级 1：修复 ACEScg ICC 映射 (H1)**
将 ACEScg 添加到 `_ICC_FILENAMES` 和 `_ICC_PROFILES`，使用现有的 Elle Stone V2 线性配置文件。

**优先级 2：添加 Display P3 线性 ICC 配置文件**
`_ICC_FILENAMES` 中缺少 `("Display P3", False)` 条目。

**优先级 3：添加 HDR EXR 渲染输出模式**
代码中存在 `hdr_rendition` exr_mode，但需要验证。确保其生成带有正确 `whiteLuminance` 和 `chromaticities` 元数据的有效 HDR EXR 文件。

**优先级 4：跨平台 HDR 增益图编码**
用跨平台方案替换仅限 macOS 的 Swift/CoreImage HEIC 编码器：
- 方案 A：`libheif` Python 绑定（支持增益图元数据）
- 方案 B：自定义 JPEG MPF 编码配合 ISO 21496-1 XMP 元数据
- 方案 C：Pillow + 自定义增益图辅助图像写入

**优先级 5：可选 OCIO 集成**
添加 OpenColorIO 作为可选依赖以支持 ACES 输出变换。这将实现：
- 用于显示参考输出的正确 ACES RRT+ODT
- 基于 LUT 的色彩流水线兼容性
- 跨应用色彩一致性

### 5.3 具体代码变更

1. **`utils/io.py`**：添加 `save_hdr_rendition_exr()` 辅助函数，调用 `prepare_hdr_photo_renditions()` 然后以 `hdr_rendition` 模式和正确的元数据写入 EXR。

2. **`utils/io.py`**：将 ACEScg 添加到 `_ICC_FILENAMES`：
   ```python
   ("ACEScg", True): "ellelstone/ACEScg-elle-V2-g10.icc",
   ("ACEScg", False): "ellelstone/ACEScg-elle-V2-g10.icc",
   ```

3. **`gpu/backend.py`**：在回退链中添加 Taichi 后端选项。

4. **`hdr_photo.py`**：添加 `save_hdr_photo_jpeg_gainmap()` 用于跨平台 ISO 21496-1 输出。

---

## 5.4 当前实现审计补充 (2026-05-27)

上述建议在实施前已针对当前工作区重新检查。本研究说明中的若干条目现已过时：

- ACEScg ICC 映射已存在于 `_ICC_FILENAMES` 和 `_ICC_PROFILES` 中，使用捆绑的 Elle Stone 线性 ACEScg 配置文件。
- Display P3 线性 ICC 映射已通过 `DisplayP3-linear.icc` 存在，测试确认了线性 TRC。
- HDR 渲染 EXR 支持已通过 `save_hdr_rendition_exr()` 和 `save_image_oiio(..., exr_mode="hdr_rendition")` 实现。
- 通用后端分块已存在于 `src/spektrafilm/gpu/backend.py` 中。

本次审计发现的实际问题更为具体：

- GPU CCTF 编码支持了 DCI-P3 解码但不支持 DCI-P3 编码，即使 `DCI-P3` 已在 GUI 色彩空间选项中暴露。此问题已通过在后端 CCTF 编码器中匹配 ICC 注册表 / colour-science 的 DCI-P3 2.6 gamma 传递函数修复。
- HDR 渲染 EXR 丢弃了 `prepare_hdr_photo_renditions()` 的诊断信息，与 HEIC HDR 照片导出不同。此问题已修复，`save_image_oiio()` 和 `save_hdr_rendition_exr()` 现在返回已创建 HDR 渲染 EXR 的 HDR 映射诊断信息。
- `save_image_oiio()` 的文档字符串未完整记录 `scene_luminance`、`scene_rgb`、`hdr_mapping_kwargs`、`exr_mode` 或诊断返回约定。此问题现已在 API 边界处记录。
- 验证还发现可选的 Halide 后端已被部分记录和测试，但未完全集成到后端选择、GUI/后端选项、可选扩展、运行时 float64 拒绝和缓存清理中。Halide 现在是严格选择加入的，仅支持 float32，且被排除在 `auto` 选择之外。
- 运行时/HDR 元数据兼容性已加强：`Simulator.process_with_metadata()` 除非 `include_scene_rgb=True` 否则保持旧的无关键字调用形式，HEIC 输出路径在调用编码器前进行验证，场景亮度嫁接现在使用感知查找亮度而非最大通道亮度。

以下延迟项目仍属于未来的架构工作，而非当前的一次性错误修复：

- Taichi/Vulkan 后端：不能直接替换 `ArrayBackend`，因为 Taichi 不暴露类似 NumPy 的数组语义来支持当前协议。
- 可选 OCIO：对于 ACES 输出变换 / 跨应用显示工作流仍有价值，但不是当前 ICC/OIIO 元数据修复所必需的。
- 跨平台 HDR 增益图编码：仍是较大的编码器工作。当前生产环境的 HEIC HDR 写入器有意保留 macOS CoreImage 路径。

---

## 6. 参考资料

### GPU 计算
- [Array API 标准](https://data-apis.github.io/array-api/latest/) - 可移植数组接口规范
- [CuPy 文档](https://docs.cupy.dev/en/stable/) - NumPy 兼容的 GPU 数组
- [MLX GitHub](https://github.com/ml-explore/mlx) - Apple 为 Apple Silicon 开发的数组框架
- [Taichi 文档](https://docs.taichi-lang.org/) - GPU 计算的并行编程
- [wgpu-py 文档](https://wgpu-py.readthedocs.io/en/latest/) - Python 的 WebGPU
- [JAX 文档](https://jax.readthedocs.io/) - NumPy 的可组合变换

### 色彩管理
- [OpenColorIO](https://opencolorio.org/) - 行业标准色彩管理
- [OCIO GitHub](https://github.com/AcademySoftwareFoundation/OpenColorIO) - OCIO 源码和配置
- [colour-science](https://colour-science.org/) - Python 色彩科学
- [OpenImageIO](https://openimageio.org/) - 图像 I/O 库
- [ACES Central](https://acescentral.com/) - 学院色彩编码系统
- [ColorAide](https://facelessuser.github.io/coloraide/) - 纯 Python 色彩操作

### HDR 标准
- [ISO 21496-1](https://www.iso.org/standard/81524.html) - 增益图 HDR 编码标准
- [Apple HDR 增益图](https://developer.apple.com/documentation/coreimage/cigainmapapply) - Apple 的实现
- [ITU-R BT.2100](https://www.itu.int/rec/R-REC-BT.2100) - HDR 显示标准 (PQ/HLG)
- [ITU-R BT.2446](https://www.itu.int/rec/R-REC-BT.2446) - HDR-SDR 转换方法

### VFX 行业标准
- [ASWF](https://www.aswf.io/) - 学院软件基金会
- [OpenEXR](https://openexr.com/) - HDR 图像文件格式
- [Open Shading Language](https://github.com/AcademySoftwareFoundation/openshadinglanguage) - 渲染器的 OSL
