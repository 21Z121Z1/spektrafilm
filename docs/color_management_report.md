# SpektraFilm 色彩管理系统分析与最佳实践报告

## 一、项目概述

SpektraFilm 是一个**基于物理的、全光谱模拟的胶片摄影仿真项目**。它使用厂商提供的胶片乳剂光谱数据（特性曲线、光谱灵敏度、染料吸收谱），端到端地模拟从相机 RAW → 负片曝光 → 化学冲洗 → 放大机印相 → 相纸显影 → 虚拟扫描的完整摄影流程。

色彩管理系统（CMS）是其核心基础设施，负责确保输入图像被正确解读、光谱上采样物理准确、中间表示一致、以及输出到显示/文件时色彩空间与传递函数正确。

---

## 二、色彩管理系统架构

### 2.1 核心数据抽象：`ColorEncoding`

**文件**: `src/spektrafilm/color_management.py`

系统中心是一个不可变的数据类 `ColorEncoding`，它封装了任意像素数据的完整色彩契约：

| 字段 | 类型 | 含义 |
|------|------|------|
| `color_space` | `str` | 色彩空间名称（如 `"sRGB"`, `"ProPhoto RGB"`, `"ACES2065-1"`） |
| `transfer` | `"linear" \| "cctf"` | 传递函数状态：线性数据或经 CCTF 编码 |
| `role` | `"scene" \| "display" \| "interchange"` | 数据用途（场景参考 / 显示参考 / 交换空间） |
| `clip_negatives` | `bool` | 是否裁切负值 |
| `clip_highlights` | `bool` | 是否裁切高光（>1.0） |

构造函数中通过 `_known_rgb_colourspaces()` 对 `color_space` 做白名单校验，确保所有值来自 `colour-science` 库注册的 RGB 色彩空间。

从 `IOParams` 到 `ColorEncoding` 的转换由两个工厂函数完成：
- `input_encoding_from_io()` — 输入侧
- `output_encoding_from_io()` — 输出侧

### 2.2 色彩管理在全流水线中的角色

模拟流水线定义了三个主要阶段（均位于 `src/spektrafilm/runtime/stages/`）：

```
输入图像 → [FilmingStage] → CMY密度 → [PrintingStage] → CMY密度 → [ScanningStage] → 输出图像
```

**输入侧** (`FilmingStage.expose`):
- 接收用户指定的 `input_color_space` 和 `input_cctf_decoding`
- 调用 `colour.RGB_to_RGB()` 将 RGB 转换到 ACES2065-1
- 通过光谱上采样算法（Hanatos2025 或 Mallett2019）将 ACES RGB→胶片传感器的"raw"曝光值

**打印侧** (`PrintingStage.expose`):
- 将 CMY 密度转换为光谱透过率，与放大机光源（含二向色滤光片Y/M/C设置）相乘
- 通过相纸的光谱灵敏度积分得到曝光量

**扫描侧** (`ScanningStage.scan`):
- 将 CMY 密度 → 光谱 → XYZ（使用 CIE 1931 标准观察者）
- 通过预计算的 3×3 矩阵将 XYZ → 输出 RGB（含 CAT02 色适应）
- `_apply_cctf_encoding_and_clip()` — 最终输出编码与裁切

### 2.3 支持的光谱上采样方法

**配置文件**: `src/spektrafilm/utils/spectral_upsampling.py`

| 方法 | 原理 | 来源 |
|------|------|------|
| **Hanatos2025** | 预计算 128×128 2D LUT，将 xy 色度映射为全光谱辐照度；LUT 使用 triangular→square 坐标变换提升显色轨迹采样质量 | 社区贡献 |
| **Mallett2019** | 使用 sRGB 光谱基函数 + 最小二乘重建 | Mallett & Yuksel, EG SR 2019 |

Hanatos2025 是默认且优先的方法。它还支持：
- 灵敏度自适应（`hanatos2025_sensitiviy_adaptation`）
- 光学带通滤波器模拟（`bandpass_hanatos2025`）
- GPU 后端加速（通过 MLX 实现 2D LUT 三次插值）

### 2.4 输入处理：RAW 与元数据识别

**文件**: `src/spektrafilm_gui/controller.py`, `src/spektrafilm/utils/raw_file_processor.py`

- **RAW 导入**: 通过 `rawpy` 解码，白平衡（as shot/daylight/tungsten/custom）、色温/色调可调
- **文件加载**: 通过 OpenImageIO + Exiv2 读取 EXIF/IPTC/XMP
- **输入编码自动识别**: `read_image_color_encoding()` 按优先级尝试：
  1. ICC 配置文件逐字节匹配（对比内建 ICC 库）
  2. OIIO `oiio:ColorSpace` / `colorInteropID` 属性
  3. EXR `chromaticities` 浮点数组与已知色彩空间色度值匹配（阈值：原色 2e-4，白点 5e-4）
- 识别结果自动设置 GUI 的 `input_color_space` 和 `apply_cctf_decoding` 下拉

### 2.5 输出处理：保存与元数据嵌入

**文件**: `src/spektrafilm/utils/io.py`

`save_image_oiio()` 根据文件扩展名和 `ColorEncoding` 决定行为：

| 格式 | 要求 | 元数据 |
|------|------|--------|
| PNG | 必须 CCTF 编码 | ICC Profile (Elle Stone / Saucecontrol V2) |
| JPEG | 必须 CCTF 编码 | ICC Profile |
| EXR | 必须线性 | `chromaticities` (float[8]), `whiteLuminance` |
| TIFF | CCTF→整数位深 / 线性→32bit float | ICC Profile |

`write_image_metadata()` 负责：
- 复制源文件 EXIF/IPTC/XMP
- 设置 EXIF ColorSpace 标签（sRGB / Uncalibrated）
- 设置 XMP `photoshop:ICCProfile`
- **验证** ICC 在回写后未被破坏（读取后对比字节）

### 2.6 显示预览与显示变换

**文件**: `src/spektrafilm_gui/controller_runtime.py`

`napari` 本身不支持色彩管理，因此 spektrafilm 的 GUI 实现了自己的显示管线：

1. **输入预览**: 将输入图像通过 `colour.RGB_to_RGB` 转换到 sRGB 显示
2. **输出预览**:
   - 若输出为线性：先加 CCTF 编码再显示
   - 若开启 `use_display_transform`：使用 `PIL.ImageCms.profileToProfile` 将输出色彩空间 → 显示器 ICC 配置文件
   - 若显示器 ICC 不可用或无对应 ICC 配置文件，回退到 sRGB 预览并提示

默认预览空间硬编码为 `DISPLAY_PREVIEW_COLOR_SPACE = 'sRGB'`。

### 2.7 中灰参考与黑白校正

**文件**: `src/spektrafilm/runtime/services/color_reference.py`

`ColorReferenceService` 管理负片/相纸的黑白参考密度，用于：
- 中灰密度平衡打印曝光（`black_white_filming_exposure_correction` / `black_white_printing_exposure_correction`）
- 扫描阶段的 Y 值线性拉伸校正（`black_white_xyz_correction`）

关键实现：当 `input_cctf_decoding` 启用时，中灰参考值（0.184）会先进行 CCTF 编码再进入光谱流程。

### 2.8 GPU 加速的色彩操作

**文件**: `src/spektrafilm/gpu/kernels/color.py`

实现了后端无关（NumPy / MLX）的色彩变换内核：
- `rgb_to_xyz` / `xyz_to_rgb` — 矩阵乘法
- `cctf_decoding_backend` / `cctf_encoding_backend` — 针对 sRGB、Display P3、ProPhoto RGB、BT.2020、Adobe RGB、DCI-P3、ACES2065-1 的手写传递函数
- `precompute_rgb_to_xyz_matrix` / `precompute_xyz_to_rgb_matrix` — 含 CAT02 色适应的 3×3 矩阵

### 2.9 支持的色彩空间

**文件**: `src/spektrafilm_gui/options.py`

通过 `RGBColorSpaces` 枚举暴露给用户：

| 空间 | 色域 | 白点 | Gamma/传递函数 |
|------|------|------|----------------|
| sRGB | BT.709 | D65 | ~2.2 (分段) |
| Display P3 | DCI-P3 | D65 | ~2.2 (sRGB 传递函数) |
| DCI-P3 | DCI-P3 | D60 | 2.6 |
| Adobe RGB (1998) | Adobe RGB | D65 | 2.2 |
| ITU-R BT.2020 | BT.2020 | D65 | ~2.4 (分段) |
| ProPhoto RGB | ProPhoto | D50 | 1.8 |
| ACES2065-1 | AP0 | D60 | 线性 |

同时内建对应的 ICC V2 配置文件（Elle Stone 系列 + Saucecontrol P3 变体）。

---

## 三、架构亮点总结

1. **统一的色彩契约** — `ColorEncoding` 贯穿整个流水线，消除分散的硬编码
2. **物理光谱渲染** — 不使用 LUT-based "胶片 Look"，而是从乳剂光谱数据正向模拟
3. **双重上采样策略** — Hanatos2025（默认，高精度 2D LUT）+ Mallett2019（基函数）
4. **格式感知的保存安全网** — 防止线性数据写入 PNG、CCTF 数据写入 EXR
5. **输入元数据自动识别** — ICC/色度/OIIO 三层探测
6. **显示变换管线** — 通过 LittleCMS/PIL 对接显示器 ICC
7. **GPU 后端抽象** — 色彩内核支持 NumPy 和 MLX 两套后端

---

## 四、与业界最佳实践的对比分析

### 4.1 ACES 管线对齐程度

SpektraFilm 的管线结构与 ACES（Academy Color Encoding System）有**概念上的相似性**但不完全对齐：

| ACES 概念 | SpektraFilm 对应 | 差异 |
|-----------|------------------|------|
| IDT (Input Device Transform) | `rgb_to_raw_hanatos2025` 含 ACES→中间空间→灵敏度矩阵 | ACES IDT 通常使用 3×3 矩阵，SpektraFilm 做全光谱重建 |
| ACES2065-1 | 作为中间交换空间使用 | 正确 |
| RRT + ODT | 扫描阶段的 `cmy→XYZ→RGB` + `cctf_encoding` | 无需 RRT（模拟自行产生场景参考输出） |
| 参考中灰 | 0.184 / 0.18 | ACES 为 0.18，SpektraFilm 使用 0.184（CIE L* 定义） |

**推荐改进**：考虑引入 ACES 的 `Output Device Transform (ODT)` 概念，替代当前的硬编码 CAT02 矩阵 + CCTF 编码。对于 HDR 显示器输出尤其有益。

### 4.2 ICC 配置文件管理

当前系统内建了 V2 ICC 配置文件（Elle Stone + Saucecontrol），但：

| 最佳实践 | SpektraFilm 状态 | 建议 |
|---------|-----------------|------|
| ICC V4 优先 | V2/V4 混合，关键路径用 V2 | 对 PNG/JPEG 输出升级到 V4（macOS/iOS 对 V2 支持好但行业趋势是 V4） |
| 嵌入式 ICC 校验 | 有（写后回读检验） | 良好 |
| EXR 色度元数据 | 有（chromaticities float[8]） | 良好，建议增加 `openexr:whiteLuminance` 标准化 |
| sRGB 作为默认 | 是 | 可接受，但应考虑"跟随 OS 显示 ICC" |

### 4.3 色适应策略

| 环节 | 方法 | 评价 |
|------|------|------|
| RGB→XYZ | CAT02 (Bradford 变体) | 与 ICC 标准一致，推荐 |
| 扫描端 XYZ→RGB | CAT02 + Von Kries | 通过预计算矩阵在 init 时完成，性能良好 |
| 中灰参考 | 无色适应（透明过流水线） | 取决于输入白点，若输入/输出白点不同可能需 CAT |

**改进建议**：在 `ColorReferenceService` 中增加 CAT 路径，使中灰参考始终与输出色彩空间白点对齐。

### 4.4 传递函数处理

| 空间 | CCTF | 状态 |
|------|------|------|
| sRGB / Display P3 | 分段 sRGB (~2.2) | 手写实现，与 colour-science 一致 |
| ProPhoto RGB | 1.8 + 线性段 | 手写实现 |
| BT.2020 | 分段 ~2.4 | 手写实现 |
| Adobe RGB | 2.2 纯幂律 | 手写实现（负值 → NaN，与 colour-science 一致） |
| ACES2065-1 | 线性（恒等映射） | 正确 |

注意：Adobe RGB 的 CCTF 在 GPU 后端使用 `backend.pow()` 而不处理负数，**需验证**与 colour-science 的 `gamma_function(negative_number_handling="Indeterminate")` 行为是否完全一致。

### 4.5 HDR 输出

当前 HDR EXR 输出已支持：
- 线性数据，不做 CCTF 编码
- 不裁切高光
- 写入 `chromaticities` + `whiteLuminance`

**尚未实现但可考虑**：
- SMPTE ST.2084 (PQ) 编码输出
- HLG 输出
- HDR PNG (sRGB 色域内但高于 1.0 的场景)
- Dolby Vision metadata 嵌入

### 4.6 中灰 / 中性打印平衡

这是 spektrafilm 的独特优势 — 它物理模拟了放大机滤光片平衡过程：
- 使用 `EnlargerService` 计算中性密度参考
- 打印阶段通过 `_exposure_factor` 自动归一化曝光
- 支持曝光补偿（`print_exposure_compensation`）

**与行业对标的差异**：专业打印实验室使用光谱密度计测量并迭代，spektrafilm 使用来自胶片数据表的理论密度曲线做开环计算。

---

## 五、推荐改进路线（按优先级）

### P0 — 关键修复

1. **Adobe RGB GPU CCTF 负数行为**：确认 `_cctf_encoding_adobe_rgb_1998` 中 `backend.pow(negative)` 是否按 colour-science 语义返回 NaN，若不是则需修复为 `_signed_power`

2. **`ColorReferenceService` 白点对齐**：中灰参考的线性值通过 `RGB_to_RGB` 转换时确保目的白点与输出色彩空间一致

### P1 — 架构增强

3. **ACES ODT 集成**：将输出端从"CAT02 + CCTF"重构为可选的 ACES Output Transform，特别是 HDR 场景（使用 `output_transform="ACES 1.3"` 或 `"SDR-Cinema"`）

4. **ICC V4 升级**：将 `_ICC_FILENAMES` 中 V2 条目替换为对应 V4 配置（保留 V2 作为 fallback）

5. **`ColorEncoding` 增加 `hdr_reference_white`**：在 `ColorEncoding` 中加入 `hdr_reference_white: float = 203.0`（单位 cd/m²），使 HDR EXR 输出包含标准的 scene-referred 元数据

### P2 — 生态集成

6. **EXR 元数据标准化**：写入 SMPTE 标准的 `openexr:whiteLuminance`、`openexr:screenPower`、以及色彩空间全名

7. **CLF/CTL 格式支持**：考虑将色彩变换导出为 ACES CLF 或 CTL 格式，以便在其他 DCC 工具中复用变换

8. **色彩管理测试套件**：增加以下自动化测试：
   - 输入编码识别（构造已知 ICC 文件验证识别准确率）
   - 色彩空间往返（RGB→XYZ→RGB 误差 < 1e-6）
   - CCTF 往返（0% 到 100% 的 1000 个采样点误差 < 1e-4）
   - 不同输出格式的 ICC 嵌入验证

---

## 六、参考资源

- [Giorgianni & Madden, Digital Color Management, 2nd ed., Wiley 2008] — 项目核心理论框架
- [Hunt, The Reproduction of Color, 6th ed., Wiley 2004] — 彩色耦合剂与染料形成
- [Mallett & Yuksel, Spectral Primary Decomposition, EG SR 2019] — RGB→光谱上采样
- [ACES 1.3 Specification, AMPAS] — 色彩交换标准参考
- [ICC.2:2022 (ICC V4)] — 配置文件的国际标准
- Elle Stone ICC Profiles — https://ninedegreesbelow.com/photography/srgb-profiles.html
- colour-science Python Library — https://www.colour-science.org/

---

*报告生成基于 spektrafilm commit 版本 v0.3.1 源码分析，2026-05-14*
