# Gain Map HDR 图像生成 — ISO 标准分析与 Spektrafilm 集成方案

> 日期: 2026-05-27
> 分析基于: ISO 21496-1:2025, ISO/IEC 23008-12:2025/Amd.1:2025, ISO/IEC 23008-12:2025

---

## 1. ISO 标准核心摘要

### 1.1 ISO 21496-1 增益图算法

#### 1.1.1 核心概念

增益图（Gain Map）是一种在单个文件中同时存储 SDR 基础图像和 HDR 替代图像的高效方案。它通过存储基础图像与一个"局部商"数据结构（增益图），在两种动态范围表示之间进行转换，避免了存储两份完整图像的冗余。

核心术语定义（ISO 21496-1 第 3 章）：

- **基础图像（Baseline Image）**：文件中存储的主图像，通常是 SDR 表示
- **替代图像（Alternate Image）**：通过合并基础图像和增益图获得的图像，通常是 HDR 表示
- **增益图应用空间（Gain Map Application Space）**：应用增益图的线性 RGB 颜色空间，缩放使得 HDR 参考白的 R/G/B 值均为 1.0
- **HDR 余量（HDR Headroom）**：标称峰值亮度与 HDR 参考白亮度的比值，以 log2 表示。例如 HDR 参考白 203 nits，峰值 1624 nits，则 headroom = log2(1624/203) = 3 stops

#### 1.1.2 增益图计算公式 (A.1)

从两种图像表示计算增益图的核心公式（附录 A.2）：

```
G = sign(H_alternate - H_baseline) × log2((Alternate + k_alternate) / (Baseline + k_baseline))
```

其中：
- `G`：以 log2 表示的增益图颜色组件
- `H_alternate`、`H_baseline`：替代/基础图像的 HDR 余量
- `k_alternate`、`k_baseline`：逐组件偏移常数，用于避免数值问题（如除零）
- sign 函数确保增益图方向与 HDR 余量差值方向一致

**物理意义**：由于使用 log2 编码，增益图值具有直观的摄影学含义 —— 它近似表示两种表示之间以光圈档数（stops/EV）的差异。值为 0 意味着两表示相同；值为 +1 意味着替代表示比基础表示亮约 1 档。

#### 1.1.3 增益图应用公式 (2)

在线性 RGB 增益图应用空间中，将增益图应用于基础图像获得替代图像：

```
Alternate = (Baseline + k_baseline) × 2^(W × G) - k_alternate
```

其中 `W` 是权重因子，用于将增益图缩放到目标 HDR 余量值 `H_target`。

#### 1.1.4 权重因子公式 (3)

```
W = sign(H_alternate - H_baseline) × clamp((H_target - H_baseline) / (H_alternate - H_baseline), 0, 1)
```

权重因子实现了在 `[H_baseline, H_alternate]` 范围内的连续缩放，使得显示器可以根据自身 HDR 能力适配显示效果。

#### 1.1.5 增益图预处理流程

1. **计算原始增益图**（A.2）：`G = sign(...) × log2((Alternate + k_alt) / (Baseline + k_base))`
2. **可选重采样**（A.3.2）：降低增益图分辨率以减小文件体积
3. **归一化**（A.3.3）：`G_normalized = (G - min(G)) / (max(G) - min(G))`
4. **伽马编码**（A.3.4）：`G_normalized_gamma = G_normalized ^ γ`

#### 1.1.6 增益图反归一化公式 (1)

解码端反归一化：

```
G = [max(G) - min(G)] × (G_normalized_gamma)^(1/γ) + min(G)
```

#### 1.1.7 增益图要求（第 4 章）

- **尺寸**（4.2）：应与基础图像同尺寸，可降采样（如 1/2 宽高）
- **颜色组件**（4.3）：3 个 RGB 组件（最高精度）或 1 个无色组件
- **量化**（4.4）：每组件至少 8 位
- **方向**（4.5）：与基础图像一致

### 1.2 元数据结构

#### 1.2.1 逐组件元数据（5.2.5）

每个颜色组件携带以下元数据：
- `min(G)`：对数空间中增益图最小值
- `max(G)`：对数空间中增益图最大值
- `k_baseline`：基础偏移常数
- `k_alternate`：替代偏移常数
- `γ`：伽马值（预压缩用）

#### 1.2.2 HDR 余量元数据

- `H_baseline`：基础图像的 HDR 余量（不应用增益图时）
- `H_alternate`：替代图像的 HDR 余量（完全应用增益图时），不应等于 `H_baseline`

#### 1.2.3 色度元数据（5.3）

- 基础图像颜色空间（ICC Profile 或 CICP 元数据）
- 替代图像颜色空间
- 增益图应用空间基色指示（使用基础或替代图像的基色）

#### 1.2.4 GainMapMetadata 二进制载荷（C.2）

大端序二进制结构：

```
struct GainMapChannel {          // 每通道 40 字节
    int(32) gain_map_min_numerator;
    unsigned int(32) gain_map_min_denominator;
    int(32) gain_map_max_numerator;
    unsigned int(32) gain_map_max_denominator;
    unsigned int(32) gamma_numerator;
    unsigned int(32) gamma_denominator;
    int(32) base_offset_numerator;
    unsigned int(32) base_offset_denominator;
    int(32) alternate_offset_numerator;
    unsigned int(32) alternate_offset_denominator;
}

aligned(8) class GainMapMetadata {
    GainMapVersion version;              // 4 字节
    // 当 minimum_version == 0 时：
    unsigned int(1) is_multichannel;     // 1=3通道, 0=1通道
    unsigned int(1) use_base_colour_space; // 1=基础图像基色, 0=替代图像基色
    unsigned int(6) reserved;
    unsigned int(32) base_hdr_headroom_numerator;
    unsigned int(32) base_hdr_headroom_denominator;
    unsigned int(32) alternate_hdr_headroom_numerator;
    unsigned int(32) alternate_hdr_headroom_denominator;
    GainMapChannel channels[channel_count]; // channel_count = (is_multichannel)*2 + 1
}
```

所有值以有理数（分子/分母）形式存储，分母不应为 0。

### 1.3 HEIF tmap 派生图像项

#### 1.3.1 容器封装方式（ISO/IEC 23008-12:2025/Amd.1 第 6.6.2.4 节）

`'tmap'` 类型的派生图像项在 HEIF 容器中的封装方式：

- **项类型**：`item_type = 'tmap'`
- **输入引用**：通过 `'dimg'` 类型的 `SingleItemTypeReferenceBox` 连接两个输入项
  - 第一个：基础输入图像项（base image item）
  - 第二个：增益图输入图像项（gain map image item）
- **ToneMapImage 数据结构**：

```
aligned(8) class ToneMapImage {
    unsigned int(8) version = 0;
    if (version == 0) {
        bit(8) gain_map_metadata[];  // ISO 21496-1 GainMapMetadata 二进制载荷
    }
}
```

#### 1.3.2 颜色属性要求

- **基础输入图像项**：必须关联 `'colr'` 项属性（对应 ISO 21496-1 基线图像色度元数据）
- **增益图输入图像项**：必须关联 `'nclx'` 类型的 `'colr'` 项属性，`colour_primaries` 和 `transfer_characteristics` 设为 2
- **tmap 派生图像项**：必须关联 `'colr'` 项属性（对应替代图像色度元数据）
- 增益图输入项应标记为隐藏（`(flags & 1) == 1`）

#### 1.3.3 向后兼容

通过 `'altr'` 实体组将 tmap 派生项和基础项组合，不支持 tmap 的解析器会忽略派生项而显示基础图像。

#### 1.3.4 文件品牌

包含 tmap 派生项的文件应在 `FileTypeBox` 的 `compatible_brands` 中包含 `'tmap'` 品牌。

### 1.4 JPEG 容器封装（ISO 21496-1 附录 C.4）

JPEG 使用 CIPA DC-007 多图片格式（MPF）存储增益图：

- **基础图像**：符合 MPF 的基础图像（第一张图像）
- **增益图图像**：作为 MPF 附加图像存储
- **元数据**：通过 APP2 段存储，URN 为 `urn:iso:std:iso:ts:21496:-1`（28 字节）
  - 基础图像的 APP2 段包含 `GainMapVersion` 结构
  - 增益图图像的 APP2 段包含完整的 `GainMapMetadata` 结构
- **替代图像颜色空间**：由增益图图像的 ICC Profile 描述

### 1.5 色度空间转换要求（附录 B）

增益图在线性 RGB 增益图应用空间中操作。当基础和替代图像编码在不同颜色空间时：

1. 转换至增益图应用空间：将基础图像像素转换为线性 RGB
2. 应用增益图
3. 转换至替代颜色空间
4. 如替代色域小于基础色域，需应用色域映射

增益图应用空间的基色由 `use_base_colour_space` 元数据指示。

---

## 2. 与 Spektrafilm 的关联分析

### 2.1 直接相关模块

#### 2.1.1 `src/spektrafilm/utils/hdr_photo.py` — 核心 HDR 管线

这是与 gain map 生成最直接相关的模块。现有功能包括：

- **`HDRPhotoMapping`**（第 55-233 行）：完整的 HDR 映射参数数据类，包含：
  - `gain_map_mode: Literal["luma", "rgb"]` — 已支持单通道/三通道增益图选择
  - `preserve_sdr_base: bool = True` — SDR 基础保持模式
  - 纸张 rolloff 参数（logistic/logarithmic 两种模式）
  - 漫反射提升参数
  - Profile-preserving HDR 曲线参数
  - 色彩恢复与色域映射参数

- **`ISO21496GainMapMetadata`**（第 1157-1172 行）：已有的 ISO 21496-1 元数据结构，但字段使用简化命名（`gain_map_min`/`gain_map_max` 而非分子/分母有理数形式）

- **`build_iso_21496_1_gain_map_metadata()`**（第 1175-1214 行）：从 HDR renditions 构建元数据

- **`encode_gain_map_log2()`**（第 1217-1255 行）：计算 `log2(hdr_luma / sdr_luma)` 并归一化到 [0, 1]

- **`build_gain_map_xmp_packet()`**（第 1258-1307 行）：生成 XMP 元数据包（使用 Adobe `hdrgm` 命名空间）

- **`validate_gain_map()`**（第 1310-1341 行）：增益图验证

- **`save_hdr_photo_heic()`**（第 262-332 行）：HEIC 导出 — **当前仅支持 macOS CoreImage**

- **`prepare_hdr_photo_renditions()`**（第 471-482 行）：生成 SDR/HDR renditions 的核心入口

- **`HDRPhotoRenditions`**（第 236-241 行）：包含 `hdr_rgb`、`sdr_rgb`、`headroom` 的输出数据类

#### 2.1.2 `src/spektrafilm/utils/io.py` — 图像 I/O

- **`save_image_oiio()`**（第 531-755 行）：通用图像保存函数，已支持 EXR hdr_rendition 模式
- **`save_hdr_rendition_exr()`**（第 758-820 行）：HDR rendition EXR 保存便捷函数
- **ICC Profile 管理**（第 171-258 行）：完整的 ICC Profile 映射和加载系统
- HEIC/HEIF 扩展名检测通过 `is_hdr_photo_extension()` 委托给 `hdr_photo.py`

#### 2.1.3 `src/spektrafilm/utils/hdr_curve_profiles.py` — HDR 曲线配置

- **`FilmPrintHDRCurveProfile`**：胶片/相纸 HDR 曲线配置文件
- **`build_profile_preserving_hdr_curve()`**（第 892-1050 行）：profile-preserving HDR 曲线构建
- **`profile_modern_recovery_budgeted_gain_ev()`**：带 EV 预算的现代恢复增益计算
- **`budget_recovery_gain_ev()`**（第 600-722 行）：EV 预算约束系统

#### 2.1.4 `src/spektrafilm/color_management.py` — 色彩管理

- **`ColorEncoding`**：颜色编码数据类（色彩空间、传递函数、角色）
- 支持 sRGB、Display P3、DCI-P3、Adobe RGB、BT.2020、ProPhoto RGB、ACES2065-1、ACEScg
- ACES 工作流预设

#### 2.1.5 `src/spektrafilm/gpu/kernels/color.py` — GPU 色彩内核

- `precompute_rgb_to_xyz_matrix()` / `precompute_xyz_to_rgb_matrix()`：色彩空间转换矩阵预计算
- `cctf_decoding_transfer_backend()` / `cctf_encoding_backend()`：后端无关的 CCTF 编解码
- 支持 sRGB、Display P3、ProPhoto RGB、BT.2020、Adobe RGB、DCI-P3

### 2.2 现有 HDR 管线与 ISO 标准的差异

| 方面 | Spektrafilm 现状 | ISO 21496-1 要求 | 差距 |
|------|------------------|------------------|------|
| **增益图计算** | `encode_gain_map_log2()` 使用亮度比 `log2(hdr_luma/sdr_luma)` | 公式 A.1：`sign(...) × log2((Alt+k_alt)/(Base+k_base))`，逐通道、含偏移 | 现有实现为单通道亮度模式，缺少逐通道 RGB 模式和偏移常数支持 |
| **元数据格式** | XMP `hdrgm` 命名空间（Adobe 格式） | `GainMapMetadata` 二进制载荷（大端序有理数结构） | 完全不同的编码格式，需实现二进制序列化 |
| **元数据字段** | `ISO21496GainMapMetadata` 简化浮点字段 | 分子/分母有理数对 + `is_multichannel` + `use_base_colour_space` | 缺少有理数编码和基色空间指示 |
| **容器封装** | macOS CoreImage Swift 脚本（平台依赖） | JPEG MPF APP2 / HEIF tmap 派生项 | 需要跨平台的 MPF 和 HEIF 封装实现 |
| **HEIC 导出** | 仅 macOS，通过 Swift/CoreImage | 标准 HEIF tmap 派生项 | 需要基于 libheif 或类似库的跨平台方案 |
| **颜色空间处理** | 在单一工作空间中操作 | 附录 B：基础/替代可使用不同色彩空间，需基色转换 | 需要增益图应用空间的基色转换逻辑 |
| **权重因子** | 无（固定 headroom） | 公式 (3)：基于 H_target 的连续缩放 | 需要实现 W 权重因子计算 |

### 2.3 需要新增的模块/功能清单

1. **`GainMapMetadataBinaryEncoder`**：将增益图参数编码为 ISO 21496-1 C.2 规定的大端序二进制载荷
2. **`GainMapMetadataBinaryDecoder`**：解析二进制载荷还原参数
3. **`compute_gain_map_iso21496()`**：实现公式 A.1 的逐通道增益图计算（含偏移常数和 sign 函数）
4. **`normalize_gain_map()`**：实现公式 A.2 和 A.3 的归一化 + 伽马编码
5. **`apply_gain_map()`**：实现公式 (2) 和 (3) 的增益图应用（含权重因子）
6. **`JPEGMPFGainMapWriter`**：JPEG MPF APP2 增益图封装器
7. **`HEIFTmapWriter`**：HEIF tmap 派生项封装器（基于 pyheif/libheif）
8. **增益图应用空间基色转换**：基础/替代色彩空间不同时的基色转换管线
9. **`save_gain_map_jpeg()`**：JPEG 增益图导出入口函数
10. **`save_gain_map_heif()`**：HEIF 增益图导出入口函数

---

## 3. Gain Map 生成的技术方案设计

### 3.1 增益图计算（基于 ISO 21496-1 附录 A）

#### 3.1.1 从 SDR+HDR 表示计算增益图

```python
def compute_gain_map_iso21496(
    baseline: np.ndarray,      # 线性 SDR 基础图像 (H, W, 3)
    alternate: np.ndarray,     # 线性 HDR 替代图像 (H, W, 3)
    *,
    k_baseline: float = 1/1023,    # 基础偏移常数
    k_alternate: float = 1/1023,   # 替代偏移常数
    h_baseline: float = 0.0,       # 基础 HDR 余量（SDR = 0）
    h_alternate: float = 3.0,      # 替代 HDR 余量
) -> np.ndarray:
    """公式 A.1：计算逐通道 log2 增益图"""
    sign = np.sign(h_alternate - h_baseline)  # +1 或 -1
    ratio = (alternate + k_alternate) / (baseline + k_baseline)
    gain = sign * np.log2(np.maximum(ratio, 1e-8))
    return gain.astype(np.float32)
```

#### 3.1.2 归一化与伽马编码

```python
def normalize_gain_map(
    gain: np.ndarray,          # 原始 log2 增益图 (H, W, 3) 或 (H, W)
    gamma: float = 1.0,        # 伽马值
) -> tuple[np.ndarray, float, float]:
    """公式 A.2 + A.3：归一化和伽马编码"""
    g_min = float(np.min(gain))
    g_max = float(np.max(gain))
    if g_max - g_min < 1e-8:
        normalized = np.zeros_like(gain)
    else:
        normalized = (gain - g_min) / (g_max - g_min)
    normalized_gamma = np.power(np.clip(normalized, 0, 1), gamma)
    return normalized_gamma.astype(np.float32), g_min, g_max
```

#### 3.1.3 增益图应用（解码端）

```python
def apply_gain_map(
    baseline: np.ndarray,      # 线性基础图像 (H, W, 3)
    gain_map: np.ndarray,      # 归一化增益图 (H, W, 3) 或 (H, W)
    *,
    g_min: float, g_max: float,
    gamma: float = 1.0,
    k_baseline: float = 1/1023,
    k_alternate: float = 1/1023,
    h_baseline: float = 0.0,
    h_alternate: float = 3.0,
    h_target: float | None = None,
) -> np.ndarray:
    """公式 (1) + (2) + (3)：应用增益图"""
    # 反归一化 — 公式 (1)
    g = (g_max - g_min) * np.power(gain_map, 1.0 / gamma) + g_min

    # 权重因子 — 公式 (3)
    if h_target is None:
        h_target = h_alternate
    sign = np.sign(h_alternate - h_baseline)
    w = sign * np.clip(
        (h_target - h_baseline) / max(h_alternate - h_baseline, 1e-8), 0, 1
    )

    # 应用增益图 — 公式 (2)
    alternate = (baseline + k_baseline) * np.power(2.0, w * g) - k_alternate
    return np.clip(alternate, 0, None).astype(np.float32)
```

### 3.2 元数据编码方案

#### 3.2.1 GainMapMetadata 二进制序列化

```python
import struct

def encode_gain_map_metadata(
    *,
    is_multichannel: bool,
    use_base_colour_space: bool,
    base_hdr_headroom: float,
    alternate_hdr_headroom: float,
    channels: list[dict],  # [{min, max, gamma, base_offset, alternate_offset}, ...]
) -> bytes:
    """编码 ISO 21496-1 C.2 GainMapMetadata 二进制载荷"""
    buf = bytearray()

    # GainMapVersion
    buf += struct.pack(">HH", 0, 0)  # minimum_version=0, writer_version=0

    # Flags byte
    flags = (int(is_multichannel) << 7) | (int(use_base_colour_space) << 6)
    buf += struct.pack(">B", flags)

    # HDR headroom (有理数)
    buf += _encode_rational(base_hdr_headroom)
    buf += _encode_rational(alternate_hdr_headroom)

    # Per-channel metadata
    channel_count = 3 if is_multichannel else 1
    for ch in channels[:channel_count]:
        buf += _encode_rational(ch["min"])
        buf += _encode_rational(ch["max"])
        buf += _encode_unsigned_rational(ch["gamma"])
        buf += _encode_rational(ch["base_offset"])
        buf += _encode_rational(ch["alternate_offset"])

    return bytes(buf)

def _encode_rational(value: float) -> bytes:
    """将浮点数编码为 int32/uint32 有理数对"""
    if value == 0:
        return struct.pack(">iI", 0, 1)
    # 使用 1/10000 精度
    numerator = int(round(value * 10000))
    return struct.pack(">iI", numerator, 10000)

def _encode_unsigned_rational(value: float) -> bytes:
    numerator = max(1, int(round(value * 10000)))
    return struct.pack(">II", numerator, 10000)
```

#### 3.2.2 现有 XMP 方案与 ISO 二进制方案的兼容

当前 `build_gain_map_xmp_packet()` 使用 Adobe `hdrgm` XMP 命名空间，这是 Google/Apple 增益图实现使用的格式。ISO 21496-1 标准使用二进制载荷。两种方案应并存：

- **XMP 方案**：用于 JPEG 中的 Google Ultra HDR 兼容格式
- **二进制方案**：用于 HEIF tmap 派生项和严格 ISO 合规场景

### 3.3 JPEG/HEIF 容器封装方案

#### 3.3.1 JPEG MPF 封装

JPEG 增益图封装基于 CIPA DC-007 多图片格式：

1. 主图像（SDR base）：标准 JPEG
2. 附加图像（gain map）：JPEG 压缩的 8 位增益图
3. APP2 段：URN `urn:iso:std:iso:ts:21496:-1` + GainMapMetadata 二进制载荷

实现方案：
- 使用 `struct` 模块手动构造 MPF APP2 段
- 增益图量化为 8 位 JPEG（与标准 C.4.1 对齐）
- 基础图像的 APP2 段仅包含 `GainMapVersion`（4 字节）
- 增益图图像的 APP2 段包含完整 `GainMapMetadata`

#### 3.3.2 HEIF tmap 封装

HEIF 封装需要构造以下 Box 结构：

```
FileTypeBox: major_brand='heic', compatible_brands=['tmap', 'mif1', 'heic']
MetaBox:
  ItemInfoBox:
    - 基础图像项 (e.g. hvc1)
    - 增益图图像项 (Hidden, hvc1/avc1)
    - tmap 派生图像项
  ItemReferenceBox:
    - tmap → dimg → [基础图像, 增益图图像]
  ItemPropertyBox:
    - colr (nclx) for 基础图像
    - colr (nclx) for 增益图 (primaries=2, transfer=2)
    - colr for tmap (替代图像色彩空间)
  ItemLocationBox
ItemDataBox:
  ToneMapImage payload (version + GainMapMetadata)
MediaDataBox:
  编码的图像数据
```

推荐使用 `pyheif` 或直接调用 `libheif` C API 进行 HEIF 容器操作。

### 3.4 颜色空间转换管线

#### 3.4.1 增益图应用空间

增益图在线性 RGB 空间中操作，缩放使得 HDR 参考白 = 1.0。管线流程：

```
[输入: 基础图像编码空间] → CCTF 解码 → 线性 RGB → 基色转换(如需) → 增益图应用空间
    → 应用增益图 → 基色转换(如需) → 替代图像编码空间 → CCTF 编码 → [输出]
```

#### 3.4.2 Spektrafilm 现有色彩空间支持

`gpu/kernels/color.py` 已支持的 CCTF 编解码：
- sRGB / Display P3（sRGB-like EOTF）
- ProPhoto RGB（ROMM RGB EOTF）
- ITU-R BT.2020（BT.1886 EOTF）
- Adobe RGB (1998)（gamma 2.2）
- DCI-P3（gamma 2.6）
- ACES2065-1 / ACEScg（线性直通）

这些已覆盖 ISO 21496-1 附录 B 所需的主要色彩空间转换。需要新增的是增益图应用空间的基色选择逻辑（`use_base_colour_space` flag）。

---

## 4. GPU 加速可行性

### 4.1 可 GPU 加速的步骤

| 步骤 | 操作 | GPU 可行性 | 备注 |
|------|------|-----------|------|
| 增益图计算 (A.1) | `log2((Alt+k_alt)/(Base+k_base))` | 高 | 逐像素独立操作，完美并行 |
| 归一化 (A.2) | `(G - min) / (max - min)` | 高 | `min`/`max` 需 reduction，然后广播 |
| 伽马编码 (A.3) | `G_normalized ^ γ` | 高 | 逐像素 `pow` 操作 |
| 重采样 | 双线性/双三次插值 | 中 | 需要纹理采样或共享内存 |
| 增益图应用 (2) | `(Base+k) × 2^(W×G) - k_alt` | 高 | 逐像素 `pow2` + 乘法 |
| 权重因子 (3) | `sign × clamp(...)` | 高 | 标量计算，结果广播 |
| 色彩空间转换 | 矩阵乘法 + CCTF | 高 | 已在 `color.py` 中实现 |
| 色域映射 | Oklch 二分搜索 | 中 | 16 次迭代，每次需全图操作 |

### 4.2 与 ArrayBackend 架构的集成点

现有 `ArrayBackend` 协议（`gpu/backend.py`）提供的操作已覆盖增益图计算所需：

- `exp(x)` / `pow(x, exp)` — 用于 `2^(W×G)` 和伽马编码
- `maximum(x, y)` / `clip(x, lo, hi)` — 用于 clamp 和非负保证
- `log10(x)` — 可扩展为 `log2`（`log2(x) = log10(x) / log10(2)`）
- `where(condition, x, y)` — 用于条件分支
- `abs(x)` — 用于 sign 函数

**需新增的 Backend 方法**：

```python
def log2(self, x: Any) -> Any: ...
```

CuPy 实现：`self.cp.log2(x)`
MLX 实现：`mx.log2(x)`
NumPy 实现：`np.log2(x)`

### 4.3 精度要求

按照 CLAUDE.md 的 GPU 精度约束（`atol=1e-6`）：

- 增益图计算使用 float32 — `log2` 和 `pow2` 在 float32 下精度足够
- 归一化操作 `min`/`max` reduction 需确保与 CPU 一致（使用相同 reduction 策略）
- 伽马编码 `pow(x, γ)` 在 float32 下精度良好
- 色彩空间矩阵乘法已有 float32 实现并经过验证

**建议**：增益图计算全程 float32，仅在最终量化为 8 位时转换精度。

---

## 5. 实施路线图

### Phase 1: 核心增益图计算引擎（预计 3-5 天）

**目标**：实现 ISO 21496-1 附录 A 的增益图计算和应用算法

1. 新增 `compute_gain_map_iso21496()` 函数（公式 A.1）
2. 新增 `normalize_gain_map()` 函数（公式 A.2 + A.3）
3. 新增 `apply_gain_map()` 函数（公式 (1) + (2) + (3)）
4. 扩展 `HDRPhotoRenditions` 以携带逐通道增益图数据
5. 重构 `encode_gain_map_log2()` 以支持逐通道 RGB 模式
6. 添加对应的单元测试（CPU 端，验证公式正确性）

**关键文件**：`src/spektrafilm/utils/hdr_photo.py`

### Phase 2: 元数据编码与容器封装（预计 5-7 天）

**目标**：实现 GainMapMetadata 二进制编码和 JPEG/HEIF 容器写入

1. 实现 `GainMapMetadata` 二进制序列化/反序列化（C.2 结构）
2. 实现 JPEG MPF APP2 封装（C.4 规范）
3. 集成 `pyheif`/`libheif` 实现 HEIF tmap 派生项封装
4. 新增 `save_gain_map_jpeg()` 入口函数
5. 新增 `save_gain_map_heif()` 入口函数（跨平台替代 macOS CoreImage）
6. 添加 XMP 和二进制元数据的往返测试

**关键文件**：新文件 `src/spektrafilm/utils/gain_map_io.py`，修改 `hdr_photo.py`

### Phase 3: GPU 加速优化（预计 2-3 天）

**目标**：将增益图计算集成到 ArrayBackend 架构

1. 在 `ArrayBackend` 协议中新增 `log2()` 方法
2. 在 `NumpyBackend`、`CupyBackend`、`MlxBackend` 中实现 `log2()`
3. 实现 GPU 端增益图计算内核（`gpu/kernels/gain_map.py`）
4. 利用 `tiled_processing()` 处理大图
5. 添加 GPU vs CPU 精度对比测试（`atol=1e-6`）

**关键文件**：`gpu/backend.py`、`gpu/kernels/`、`gpu/cupy_backend.py`、`gpu/mlx_backend.py`

### Phase 4: 测试与验证（预计 2-3 天）

**目标**：全面测试和标准合规性验证

1. 单元测试：增益图计算/应用的往返一致性
2. 元数据编码测试：二进制载荷的序列化/反序列化
3. 容器封装测试：生成的 JPEG/HEIF 文件可被标准解析器读取
4. 色彩空间测试：不同基础/替代色彩空间组合
5. GPU 精度测试：CPU vs GPU 输出对比
6. 端到端测试：从场景线性输入到 gain map HEIC 输出的完整流程

### 工作量估算

| 阶段 | 工作量 | 依赖 |
|------|--------|------|
| Phase 1: 核心算法 | 3-5 天 | 无 |
| Phase 2: 元数据与封装 | 5-7 天 | Phase 1 |
| Phase 3: GPU 加速 | 2-3 天 | Phase 1 |
| Phase 4: 测试验证 | 2-3 天 | Phase 1-3 |
| **总计** | **12-18 天** | |

---

## 6. 风险与依赖

### 6.1 OpenImageIO 对 HEIF Gain Map 的支持现状

**风险**：OpenImageIO（Spektrafilm 的主要 I/O 库）对 HEIF gain map 的支持有限。

- OIIO 支持 HEIF 基本读写（通过 `libheif`），但不直接暴露 tmap 派生项 API
- OIIO 的 `ImageSpec` 属性系统不包含 `GainMapMetadata` 的原生支持
- 需要通过 `libheif` Python 绑定（`pyheif`）或直接 C API 操作 HEIF 容器结构

**缓解策略**：
- 使用 `pyheif` 作为 HEIF 容器操作的主要依赖
- 保持 OIIO 用于基础图像的读写，增益图封装在 OIIO 之上实现
- 考虑使用 `pillow-heif` 作为备选方案（已支持基本的 gain map 写入）

### 6.2 色彩科学库（colour-science）的适用性

**现状**：Spektrafilm 已深度集成 `colour-science` 库（用于 RGB 色彩空间定义、CCTF 编解码、矩阵计算等）。

**适用性分析**：
- 色彩空间矩阵：`colour.RGB_COLOURSPACES` 已覆盖所有需要的色彩空间
- CCTF 编解码：`colour.RGB_to_RGB()` 提供标准传递函数
- 色度学计算：`colour.xy_to_XYZ()` 等函数可用于基色转换
- **不适用**：`colour-science` 不包含增益图专用功能，需自行实现

**风险**：低。现有集成已验证稳定，增益图计算主要是数学运算，不依赖额外色彩科学功能。

### 6.3 标准合规性验证策略

1. **公式验证**：
   - 使用 ISO 21496-1 附录 A 中的参考值进行单元测试
   - 验证增益图往返一致性：`compute → normalize → denormalize → apply ≈ original`

2. **二进制载荷验证**：
   - 手工构造已知二进制序列并验证解析结果
   - 与 Google 的 `libultrahdr` 参考实现进行交叉验证

3. **容器合规性验证**：
   - 使用 `exiftool` 验证 JPEG MPF 结构
   - 使用 `heif-info`（libheif 工具）验证 HEIF tmap 结构
   - 使用 Apple 设备（如可用）验证 HEIC gain map 渲染

4. **互操作性测试**：
   - Google Photos / Android 对 JPEG gain map 的渲染
   - Apple Photos 对 HEIC gain map 的渲染
   - Adobe Lightroom 对两种格式的读取

### 6.4 其他风险

| 风险 | 影响 | 缓解策略 |
|------|------|----------|
| `pyheif` 安装依赖 `libheif` C 库 | 部署复杂度增加 | 提供 conda/pip 安装文档，考虑 `pillow-heif` 替代 |
| JPEG MPF 在旧软件中不被识别 | 旧查看器只显示 SDR 基础图像 | 这是标准设计的向后兼容行为，可接受 |
| macOS CoreImage 的 HEIC 输出不符合 ISO 21496-1 二进制格式 | 现有 HEIC 输出需迁移 | Phase 2 中实现标准格式，保留 CoreImage 作为 macOS 备选 |
| 逐通道 RGB 增益图体积是亮度模式的 3 倍 | JPEG 文件体积增大 | 支持降采样（1/2 或 1/4 分辨率），使用可配置质量 |
| 大图（50MP+）增益图计算内存占用 | GPU 内存不足 | 利用现有 `tiled_processing()` 分块处理 |

---

## 附录：关键代码路径参考

| 功能 | 文件 | 行号 |
|------|------|------|
| HDRPhotoMapping 数据类 | `src/spektrafilm/utils/hdr_photo.py` | 55-233 |
| HDRPhotoRenditions 输出 | `src/spektrafilm/utils/hdr_photo.py` | 236-241 |
| prepare_hdr_photo_renditions() | `src/spektrafilm/utils/hdr_photo.py` | 471-482 |
| save_hdr_photo_heic() | `src/spektrafilm/utils/hdr_photo.py` | 262-332 |
| ISO21496GainMapMetadata | `src/spektrafilm/utils/hdr_photo.py` | 1157-1172 |
| build_iso_21496_1_gain_map_metadata() | `src/spektrafilm/utils/hdr_photo.py` | 1175-1214 |
| encode_gain_map_log2() | `src/spektrafilm/utils/hdr_photo.py` | 1217-1255 |
| build_gain_map_xmp_packet() | `src/spektrafilm/utils/hdr_photo.py` | 1258-1307 |
| save_image_oiio() | `src/spektrafilm/utils/io.py` | 531-755 |
| save_hdr_rendition_exr() | `src/spektrafilm/utils/io.py` | 758-820 |
| ICC Profile 映射 | `src/spektrafilm/utils/io.py` | 171-258 |
| ArrayBackend 协议 | `src/spektrafilm/gpu/backend.py` | 7-30 |
| tiled_processing() | `src/spektrafilm/gpu/backend.py` | 116-194 |
| 色彩空间转换内核 | `src/spektrafilm/gpu/kernels/color.py` | 1-316 |
| CCTF 编解码 | `src/spektrafilm/gpu/kernels/color.py` | 185-256 |
| ColorEncoding 数据类 | `src/spektrafilm/color_management.py` | 92-130 |
| FilmPrintHDRCurveProfile | `src/spektrafilm/utils/hdr_curve_profiles.py` | 38-51 |
| build_profile_preserving_hdr_curve() | `src/spektrafilm/utils/hdr_curve_profiles.py` | 892-1050 |
| Oklch 色域映射 | `src/spektrafilm/utils/hdr_photo.py` | 1020-1134 |
