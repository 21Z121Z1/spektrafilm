> 这是英文原文的中文翻译。权威版本请参考英文原文。

# GUI 色彩管理与 HDR 预览研究

研究日期：2026-05-27

## 摘要

Spektrafilm 的 GUI 目前使用 napari/VisPy (OpenGL) 进行图像显示，使用 PIL.ImageCms 进行基于 ICC 的显示变换。所有预览图像均以 8 位 sRGB 渲染，不具备 HDR 预览能力，也无 Qt 级别的色彩管理。本研究评估了 Qt6 的色彩管理 API、HDR 表面渲染路径，以及面向专业摄影后期工作流的软打样实现策略。

---

## 1. 当前显示管线审查

### 1.1 架构概述

显示管线流经三个层级：

```
Simulation Pipeline (float32 scene-linear)
    |
    v
controller_runtime.prepare_output_display_image()
    |
    v
PIL.ImageCms profileToProfile() [ICC transform]
    |
    v
uint8 numpy array [0-255]
    |
    v
napari viewer.add_image() [VisPy/OpenGL]
    |
    v
Monitor
```

### 1.2 关键代码路径

**输入预览** (`controller.py:726-741`):
```python
preview_display_image = self._prepare_input_color_preview_image(
    preview_image,
    input_color_space=state.input_image.input_color_space,
    apply_cctf_decoding=state.input_image.apply_cctf_decoding,
)
```
通过 `colour.RGB_to_RGB()` 将输入从其原始色彩空间转换为 sRGB 用于显示。

**输出显示** (`controller_runtime.py:249-286`):
```python
def prepare_output_display_image(
    image_data, *, output_encoding, use_display_transform,
    padding_pixels, imagecms_module, colour_module, pil_image_module,
) -> tuple[np.ndarray, str]:
```
两条路径：
1. **无显示变换**：CCTF 编码为 sRGB，转换为 uint8
2. **有显示变换**：通过 `imagecms_module.profileToProfile()` 进行从输出配置文件到显示配置文件的 ICC 变换

**显示变换** (`controller_runtime.py:164-212`):
```python
def apply_display_transform(
    image_data, *, output_encoding, colour_module, imagecms_module, pil_image_module,
) -> tuple[np.ndarray, str]:
    display_profile, profile_name = display_profile_details(imagecms_module=imagecms_module)
    # ...
    source_image = pil_image_module.fromarray(source_uint8, mode='RGB')
    transformed_image = imagecms_module.profileToProfile(
        source_image, source_profile, display_profile, outputMode='RGB'
    )
    return np.asarray(transformed_image, dtype=np.uint8), status
```

### 1.3 当前局限性

| 局限性 | 影响 | 严重程度 |
|--------|------|----------|
| **仅 uint8 输出** | HDR 值被裁剪，渐变出现色带 | HDR 场景为严重 |
| **sRGB 预览假设** | 在 P3/BT.2020 显示器上色彩不准确 | 高 |
| **未使用 QColorSpace** | Qt 不知道图像的色彩空间 | 中 |
| **无软打样** | 无法模拟印刷/显示输出 | 中 |
| **仅 PIL.ImageCms** | 色彩变换无 GPU 加速 | 低 |
| **无 HDR 表面支持** | 无法在 HDR 显示器上预览 >1.0 的值 | HDR 场景为严重 |
| **Napari 图层无色彩空间标签** | VisPy 假设为 sRGB | 高 |

### 1.4 显示配置文件检测

当前方法 (`controller_runtime.py`):
```python
def display_profile_details(*, imagecms_module):
    display_profile = _resolve_display_profile(imagecms_module=imagecms_module)
    # Returns (profile_object, profile_name_string)
```

`PIL.ImageCms.get_display_profile()` 行为：
- **Windows**：从设备上下文 (DC) 读取 ICC 配置文件
- **macOS**：即使 CoreGraphics 仍可提供主显示器 ICC 配置文件，也可能返回 `None`
- **Linux**：返回 `None`（无标准 API）

在 macOS 上，Spektrafilm 现在会通过 Python 标准库 `ctypes` 调用 CoreGraphics/CoreFoundation fallback，使用 `CGMainDisplayID()` 和 `CGColorSpaceCopyICCData()` 取得 ICC bytes 并构造 Pillow `ImageCmsProfile`。只有 Pillow 和 macOS fallback 都无法提供配置文件时，GUI 才会禁用显示变换开关。该 fallback 基于主显示器，不感知当前窗口所在显示器。

---

## 2. Qt6 色彩管理能力

### 2.1 QColorSpace (Qt 5.14+，Qt 6 中已成熟)

Qt6 提供内置的色彩空间表示：

```python
from PySide6.QtGui import QColorSpace

# Preset color spaces
srgb = QColorSpace(QColorSpace.NamedColorSpace.SRgb)
display_p3 = QColorSpace(QColorSpace.NamedColorSpace.DisplayP3)
adobe_rgb = QColorSpace(QColorSpace.NamedColorSpace.AdobeRgb)
pro_photo = QColorSpace(QColorSpace.NamedColorSpace.ProPhotoRgb)

# Custom color space from primaries + transfer function
bt2020_pq = QColorSpace(
    QColorSpace.Primaries.BT2020,
    QColorSpace.TransferFunction.PQ
)

# From ICC profile
icc_bytes = open('profile.icc', 'rb').read()
custom_space = QColorSpace.fromIccProfile(icc_bytes)
```

### 2.2 QColorTransform

Qt6 可以在色彩空间之间创建变换：

```python
from PySide6.QtGui import QColorSpace, QColorTransform

src = QColorSpace(QColorSpace.NamedColorSpace.DisplayP3)
dst = QColorSpace(QColorSpace.NamedColorSpace.SRgb)

# Create transform
transform = src.transformationToColorSpace(dst)

# Apply to QImage
converted_image = transformed_image  # Qt applies the transform
```

### 2.3 QImage 色彩空间集成

```python
from PySide6.QtGui import QImage, QColorSpace

# Tag image with color space
image = QImage(data, width, height, QImage.Format.Format_RGBA8888)
image.setColorSpace(QColorSpace(QColorSpace.NamedColorSpace.DisplayP3))

# Qt will automatically convert when painting to a different color space widget
```

### 2.4 QColorTransferFunction (HDR)

Qt6 支持 HDR 传递函数：

```python
from PySide6.QtGui import QColorSpace

# PQ (Perceptual Quantizer) - HDR10
pq_space = QColorSpace(
    QColorSpace.Primaries.BT2020,
    QColorSpace.TransferFunction.PQ
)

# HLG (Hybrid Log-Gamma) - Broadcast HDR
hlg_space = QColorSpace(
    QColorSpace.Primaries.BT2020,
    QColorSpace.TransferFunction.HLG
)

# Linear
linear_space = QColorSpace(
    QColorSpace.Primaries.BT2020,
    QColorSpace.TransferFunction.Linear
)
```

### 2.5 Qt6 色彩管理的不足

| 功能 | Qt6 状态 | 替代方案 |
|------|----------|----------|
| **HDR 窗口表面** | Qt 6.5+ Wayland HDR、Windows HDR | 平台相关 |
| **float16 帧缓冲** | QOpenGLWidget 默认不支持 | 需要自定义 FBO |
| **scRGB 输出** | 仅 Windows（通过 DXGI） | 非跨平台 |
| **从显示器获取 ICC 配置文件** | macOS 支持、Windows 部分支持、Linux 不支持 | 回退到 PIL.ImageCms |
| **软打样意图** | 无内置软打样 | 手动 ICC 链 |
| **HDR10 元数据** | Qt 无 HDR 元数据 API | Vulkan `VK_EXT_hdr_metadata` |
| **PQ/HLG 渲染** | QColorSpace 可表示，但无 HDR 表面 | 需要 OpenGL FBO + 色调映射 |

---

## 3. HDR 预览实现路径

### 3.1 策略概述

HDR 预览需要三个组件：

1. **支持 HDR 的帧缓冲**：float16/float32 FBO 替代默认的 8 位
2. **色调映射着色器**：将 HDR 值映射到显示范围
3. **HDR 显示表面**：操作系统级别的 HDR 窗口（平台相关）

### 3.2 通过 QOpenGLWidget 实现 OpenGL HDR 渲染

```python
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtOpenGL import QOpenGLFramebufferObject, QOpenGLFramebufferObjectFormat
import OpenGL.GL as gl

class HDRPreviewWidget(QOpenGLWidget):
    def __init__(self):
        super().__init__()
        self._hdr_fbo = None
        self._hdr_texture = None

    def initializeGL(self):
        # Create float16 FBO for HDR rendering
        fmt = QOpenGLFramebufferObjectFormat()
        fmt.setInternalTextureFormat(gl.GL_RGBA16F)
        fmt.setSamples(4)  # MSAA
        self._hdr_fbo = QOpenGLFramebufferObject(self.size(), fmt)

        # Enable sRGB framebuffer for automatic linear->sRGB conversion
        gl.glEnable(gl.GL_FRAMEBUFFER_SRGB)

    def paintGL(self):
        # Bind HDR FBO
        self._hdr_fbo.bind()

        # Render HDR content (float16 values > 1.0)
        self._render_hdr_content()

        # Blit to default framebuffer with tone mapping
        self._hdr_fbo.release()
        self._tone_map_and_blit()

    def _tone_map_and_blit(self):
        """Apply tone mapping shader when blitting HDR FBO to screen."""
        # Use a full-screen quad with tone mapping shader
        # Shader maps [0, headroom] -> [0, 1] for SDR display
        pass
```

### 3.3 色调映射着色器 (GLSL)

```glsl
#version 330 core

uniform sampler2D hdr_texture;
uniform float headroom;        // e.g., 4.0 for 4x SDR white
uniform float reference_white; // 1.0 = SDR white point
uniform int tone_map_mode;     // 0=linear clip, 1=ACES, 2=Reinhard, 3=filmic

in vec2 tex_coord;
out vec4 frag_color;

// ACES filmic tone mapping (approximation)
vec3 aces_tone_map(vec3 x) {
    float a = 2.51;
    float b = 0.03;
    float c = 2.43;
    float d = 0.59;
    float e = 0.14;
    return clamp((x * (a * x + b)) / (x * (c * x + d) + e), 0.0, 1.0);
}

// Reinhard tone mapping
vec3 reinhard_tone_map(vec3 x) {
    return x / (1.0 + x);
}

void main() {
    vec3 hdr = texture(hdr_texture, tex_coord).rgb;

    // Normalize to reference white
    vec3 normalized = hdr / reference_white;

    vec3 mapped;
    if (tone_map_mode == 0) {
        mapped = clamp(normalized, 0.0, 1.0);
    } else if (tone_map_mode == 1) {
        mapped = aces_tone_map(normalized / headroom);
    } else if (tone_map_mode == 2) {
        mapped = reinhard_tone_map(normalized);
    } else {
        // Filmic (Hable)
        vec3 x = max(normalized - 0.004, 0.0);
        mapped = (x * (6.2 * x + 0.5)) / (x * (6.2 * x + 1.7) + 0.06);
    }

    // Apply sRGB gamma for display
    mapped = pow(mapped, vec3(1.0 / 2.2));

    frag_color = vec4(mapped, 1.0);
}
```

### 3.4 平台相关的 HDR 表面

**Windows (DXGI)**:
```python
# Qt 6.5+ with DXGI swap chain
# Requires Windows 10 1803+ with HDR enabled in display settings
# Qt automatically uses DXGI when available

# Manual approach via ctypes:
import ctypes
from ctypes import wintypes

# Enable HDR swap chain for the window
# This requires creating a DXGI swap chain with
# DXGI_SWAP_CHAIN_DESC1.Format = DXGI_FORMAT_R16G16B16A16_FLOAT
# and DXGI_COLOR_SPACE_TYPE = DXGI_COLOR_SPACE_RGB_FULL_G2084_NONE_P2020
```

**Wayland (Linux)**:
```python
# Qt 6.5+ Wayland HDR protocol support
# Requires compositor support (KWin 5.27+, GNOME 45+)
# Uses wp_color_management_v1 protocol

# Surface format for HDR:
from PySide6.QtGui import QSurfaceFormat

fmt = QSurfaceFormat()
fmt.setRenderableType(QSurfaceFormat.OpenGL)
fmt.setVersion(3, 3)
fmt.setProfile(QSurfaceFormat.CoreProfile)
# Request float16 color buffer
fmt.setRedBufferSize(16)
fmt.setGreenBufferSize(16)
fmt.setBlueBufferSize(16)
fmt.setAlphaBufferSize(16)
```

**macOS**:
```python
# macOS uses EDR (Extended Dynamic Range)
# NSWindow.canDrawConcurrently = YES
# CGColorSpace with PQ/HLG transfer function
# Metal layer with float16 pixel format

# Qt on macOS: use QMetalWindow or custom Metal layer
```

### 3.5 推荐的 HDR 预览架构

```
Simulation Pipeline (float32 scene-linear, any color space)
    |
    v
HDR Preview Manager
    |
    +-- SDR Preview Path (current)
    |   |-- CCTF encode -> uint8 -> napari layer
    |   |-- Fallback for non-HDR displays
    |   |
    |
    +-- HDR Preview Path (new)
        |-- float16 FBO (OpenGL)
        |-- Tone mapping shader (ACES/Reinhard/filmic)
        |-- HDR surface (platform-specific)
        |-- Headroom detection from display
```

---

## 4. 软打样实现

### 4.1 软打样概念

软打样模拟图像在目标设备（打印机、不同显示器）上的显示效果。变换链如下：

```
Source Color Space (e.g., ACEScg)
    |
    v (PCS: Lab/XYZ)
    |
    v (Rendering Intent)
    |
Simulation Profile (e.g., printer ICC)
    |
    v (PCS: Lab/XYZ)
    |
    v
Display Profile (monitor ICC)
    |
    v
Monitor
```

### 4.2 渲染意图

| 意图 | 使用场景 | 行为 |
|------|----------|------|
| **感知 (Perceptual)** | 摄影 | 压缩整个色域以适应 |
| **相对比色 (Relative Colorimetric)** | 校样匹配 | 映射白点，裁剪超出色域的部分 |
| **绝对比色 (Absolute Colorimetric)** | 颜色匹配 | 保留绝对颜色，不映射白点 |
| **饱和度 (Saturation)** | 商业图形 | 优先保留饱和度而非色相精度 |

### 4.3 使用 PIL.ImageCms 实现

```python
from PIL import ImageCms

def soft_proof_image(
    image_data: np.ndarray,
    source_profile: ImageCms.ImageCmsProfile,
    proof_profile: ImageCms.ImageCmsProfile,
    display_profile: ImageCms.ImageCmsProfile,
    intent: int = ImageCms.Intent.PERCEPTUAL,
    proof_intent: int = ImageCms.Intent.ABSOLUTE_COLORIMETRIC,
) -> np.ndarray:
    """Apply soft proofing transform chain."""

    # Source -> Proof (simulates output device)
    proof_transform = ImageCms.buildTransform(
        source_profile, proof_profile,
        "RGB", "RGB",
        renderingIntent=intent,
    )

    # Proof -> Display (shows on monitor)
    display_transform = ImageCms.buildTransform(
        proof_profile, display_profile,
        "RGB", "RGB",
        renderingIntent=proof_intent,
    )

    # Chain transforms
    source_img = Image.fromarray(image_data, 'RGB')
    proof_img = ImageCms.applyTransform(source_img, proof_transform)
    display_img = ImageCms.applyTransform(proof_img, display_transform)

    return np.asarray(display_img)
```

### 4.4 软打样 UI 集成

```python
class SoftProofingState:
    enabled: bool = False
    proof_profile_path: str | None = None  # Printer/display ICC profile
    rendering_intent: str = "perceptual"    # perceptual|relative|absolute|saturation
    simulate_paper_white: bool = True       # Simulate paper white point
    simulate_black_point: bool = True       # Simulate printer black point
    gamut_warning: bool = False             # Highlight out-of-gamut pixels
```

### 4.5 色域警告叠加

```python
def gamut_warning_overlay(
    source_image: np.ndarray,
    proof_image: np.ndarray,
    threshold: float = 0.01,
) -> np.ndarray:
    """Highlight pixels that are out of gamut in the proof."""
    diff = np.abs(source_image.astype(float) - proof_image.astype(float))
    out_of_gamut = np.any(diff > threshold, axis=-1)

    overlay = proof_image.copy()
    overlay[out_of_gamut] = [255, 0, 255]  # Magenta warning
    return overlay
```

---

## 5. 显示变换链建议

### 5.1 推荐架构

```
┌─────────────────────────────────────────────────────────┐
│                   Spektrafilm GUI                        │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────┐    ┌──────────────┐    ┌────────────┐ │
│  │ Simulation  │───>│ Display      │───>│ Qt/VisPy   │ │
│  │ Pipeline    │    │ Transform    │    │ Renderer   │ │
│  │ (float32)   │    │ Manager      │    │            │ │
│  └─────────────┘    └──────────────┘    └────────────┘ │
│                            │                    │       │
│                     ┌──────┴──────┐             │       │
│                     │             │             │       │
│                ┌────┴────┐  ┌────┴────┐        │       │
│                │ SDR Path│  │ HDR Path│        │       │
│                │ (uint8) │  │ (f16)   │        │       │
│                └─────────┘  └─────────┘        │       │
│                     │             │             │       │
│                     └──────┬──────┘             │       │
│                            │                    │       │
│                     ┌──────┴──────┐             │       │
│                     │ QColorSpace │             │       │
│                     │ Tag on      │─────────────┘       │
│                     │ QImage      │                     │
│                     └─────────────┘                     │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 5.2 实现阶段

**阶段 1：Qt 色彩空间标注（低工作量，高价值）**
- 为所有 QImage 标注正确的 QColorSpace
- 让 Qt 自动处理色彩转换
- 修复广色域显示器上的过饱和问题

```python
from PySide6.QtGui import QImage, QColorSpace

def numpy_to_qimage(data: np.ndarray, color_space_name: str) -> QImage:
    """Convert numpy array to QImage with color space tag."""
    h, w, c = data.shape
    bytes_per_line = c * w

    # Map color space names to Qt enums
    cs_map = {
        'sRGB': QColorSpace.NamedColorSpace.SRgb,
        'Display P3': QColorSpace.NamedColorSpace.DisplayP3,
        'Adobe RGB (1998)': QColorSpace.NamedColorSpace.AdobeRgb,
        'ProPhoto RGB': QColorSpace.NamedColorSpace.ProPhotoRgb,
    }

    qt_cs = cs_map.get(color_space_name, QColorSpace.NamedColorSpace.SRgb)

    if data.dtype == np.uint8:
        fmt = QImage.Format.Format_RGB888
    elif data.dtype == np.float32:
        # Qt doesn't have native float32 format for display
        # Convert to uint8 first
        data = (np.clip(data, 0, 1) * 255).astype(np.uint8)
        fmt = QImage.Format.Format_RGB888

    image = QImage(data.data, w, h, bytes_per_line, fmt)
    image.setColorSpace(QColorSpace(qt_cs))
    return image
```

**阶段 2：显示配置文件集成（中等工作量）**
- 使用 Qt 的 `QScreen` 检测显示器色彩配置文件
- Linux 上回退到 PIL.ImageCms
- 在状态栏显示配置文件名称

```python
from PySide6.QtGui import QScreen

def detect_display_color_space(screen: QScreen) -> QColorSpace:
    """Detect the color space of the current display."""
    # macOS: Qt can read ICC profile from ColorSync
    # Windows: Qt reads from device context
    # Linux: Returns sRGB (no standard API)

    # Qt 6.5+ method
    color_space = screen.colorSpace()
    if color_space.isValid():
        return color_space

    # Fallback to sRGB
    return QColorSpace(QColorSpace.NamedColorSpace.SRgb)
```

**阶段 3：HDR 预览（高工作量，高价值）**
- 自定义带 float16 FBO 的 OpenGL 控件
- 色调映射着色器
- 平台相关的 HDR 表面
- 余量检测

**阶段 4：软打样（中等工作量）**
- 添加校样配置文件选择 UI
- 实现 ICC 变换链
- 色域警告叠加
- 纸白/黑点模拟

### 5.3 Napari 集成挑战

Napari 内部使用 VisPy (OpenGL)。主要挑战：

1. **无色彩空间 API**：Napari 图层没有色彩空间属性
2. **sRGB 假设**：VisPy 假设所有纹理都是 sRGB
3. **uint8 纹理**：默认纹理格式为 uint8
4. **无 HDR 表面**：Napari 的画布不请求 HDR 表面

**替代方案**：
- 在传递给 napari 之前预转换为 sRGB（当前方案）
- 使用 napari 的着色器钩子进行自定义色调映射（如可用）
- 用自定义 QOpenGLWidget 替换 napari 的画布以实现 HDR 预览
- 仅将 napari 用于 SDR 预览，添加单独的 HDR 预览窗口

---

## 6. 具体 Qt API 调用和代码模式

### 6.1 完整的 HDR 预览控件

```python
from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtGui import QSurfaceFormat, QColorSpace
from PySide6.QtCore import Qt
import numpy as np

class HDRPreviewWidget(QOpenGLWidget):
    """OpenGL widget for HDR image preview with tone mapping."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hdr_data: np.ndarray | None = None
        self._headroom: float = 4.0
        self._tone_map_mode: int = 1  # 0=linear, 1=ACES, 2=Reinhard
        self._reference_white: float = 1.0

        # Request float16 framebuffer
        fmt = QSurfaceFormat()
        fmt.setRenderableType(QSurfaceFormat.OpenGL)
        fmt.setVersion(3, 3)
        fmt.setProfile(QSurfaceFormat.CoreProfile)
        fmt.setRedBufferSize(16)
        fmt.setGreenBufferSize(16)
        fmt.setBlueBufferSize(16)
        self.setFormat(fmt)

    def set_hdr_image(
        self,
        data: np.ndarray,
        headroom: float = 4.0,
        color_space: str = 'ACEScg',
    ):
        """Set HDR image data (float32, linear, values > 1.0 allowed)."""
        self._hdr_data = data.astype(np.float32)
        self._headroom = headroom
        self.update()

    def set_tone_map_mode(self, mode: int):
        """Set tone mapping mode: 0=linear, 1=ACES, 2=Reinhard, 3=filmic."""
        self._tone_map_mode = mode
        self.update()

    def initializeGL(self):
        import OpenGL.GL as gl
        gl.glEnable(gl.GL_DEPTH_TEST)
        gl.glClearColor(0.0, 0.0, 0.0, 1.0)

        # Create shader program for tone mapping
        self._shader_program = self._create_tone_map_shader()

    def paintGL(self):
        import OpenGL.GL as gl
        gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)

        if self._hdr_data is None:
            return

        # Upload HDR texture (float16)
        # Render full-screen quad with tone mapping shader
        self._render_tone_mapped_quad()
```

### 6.2 用于 Napari 图层元数据的 QColorSpace

```python
def tag_napari_layer_color_space(layer, color_space_name: str):
    """Store color space information in napari layer metadata."""
    # Napari doesn't have native color space support,
    # so we store it in metadata for our display transform to use
    layer.metadata['color_space'] = color_space_name
    layer.metadata['is_linear'] = color_space_name in ('ACES2065-1', 'ACEScg')
    layer.metadata['qt_color_space'] = _qt_color_space_for_name(color_space_name)

def _qt_color_space_for_name(name: str) -> QColorSpace:
    """Map color space name to QColorSpace."""
    mapping = {
        'sRGB': QColorSpace.NamedColorSpace.SRgb,
        'Display P3': QColorSpace.NamedColorSpace.DisplayP3,
        'Adobe RGB (1998)': QColorSpace.NamedColorSpace.AdobeRgb,
        'ProPhoto RGB': QColorSpace.NamedColorSpace.ProPhotoRgb,
    }
    named = mapping.get(name)
    if named is not None:
        return QColorSpace(named)

    # For spaces not in Qt's presets, create from primaries
    # BT.2020, ACEScg, etc. need custom construction
    return QColorSpace(QColorSpace.Primaries.Custom, QColorSpace.TransferFunction.Linear)
```

### 6.3 显示余量检测

```python
def detect_display_headroom() -> float:
    """Detect the HDR headroom of the current display.

    Returns the ratio of peak luminance to reference white.
    e.g., 4.0 means the display can show 4x brighter than SDR white.
    Returns 1.0 for SDR displays.
    """
    import sys

    if sys.platform == 'darwin':
        # macOS: Use CGDisplayCopyDisplayMode
        # EDR headroom = mode.maximumExtendedDynamicRangeColorComponentValue
        try:
            import objc
            from Quartz import CGDisplayCopyDisplayMode, CGMainDisplayID
            mode = CGDisplayCopyDisplayMode(CGMainDisplayID())
            headroom = mode.maximumExtendedDynamicRangeColorComponentValue()
            return max(float(headroom), 1.0)
        except ImportError:
            return 1.0

    elif sys.platform == 'win32':
        # Windows: Use DXGI output description
        # DXGI_OUTPUT_DESC1.MaxLuminance / ReferenceWhiteLuminance
        try:
            import ctypes
            from ctypes import wintypes
            # ... DXGI enumeration code ...
            return 1.0  # Placeholder
        except Exception:
            return 1.0

    else:
        # Linux: Check Wayland HDR protocol support
        # wp_color_management_v1 interface
        return 1.0  # Default to SDR
```

### 6.4 ICC 配置文件管理

```python
from PySide6.QtGui import QColorSpace
from pathlib import Path

def load_icc_profile_as_qcolorspace(profile_path: Path) -> QColorSpace:
    """Load an ICC profile file as a QColorSpace."""
    icc_bytes = profile_path.read_bytes()
    cs = QColorSpace.fromIccProfile(icc_bytes)
    if not cs.isValid():
        raise ValueError(f"Invalid ICC profile: {profile_path}")
    return cs

def get_display_qcolorspace() -> QColorSpace:
    """Get the QColorSpace of the primary display."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        return QColorSpace(QColorSpace.NamedColorSpace.SRgb)

    screen = app.primaryScreen()
    if screen is None:
        return QColorSpace(QColorSpace.NamedColorSpace.SRgb)

    # Qt 6.5+ can read display color space
    cs = screen.colorSpace()
    if cs.isValid():
        return cs

    return QColorSpace(QColorSpace.NamedColorSpace.SRgb)
```

---

## 7. 实现路线图

### 阶段 1：Qt 色彩空间感知（1-2 天）

**目标**：修复广色域显示器上的过饱和问题。

1. 为 napari 中显示的所有图像添加 `QColorSpace` 标注
2. 将 Spektrafilm 色彩空间名称映射到 `QColorSpace` 预设
3. 在 napari 图层上存储色彩空间元数据
4. 在 Display P3 和 Adobe RGB 显示器上测试

**需修改的文件**：
- `src/spektrafilm_gui/controller_runtime.py` - 添加 QColorSpace 映射
- `src/spektrafilm_gui/controller_layers.py` - 为图层标注色彩空间
- `src/spektrafilm_gui/app.py` - 初始化 Qt 色彩管理

### 阶段 2：软打样（3-5 天）

**目标**：在预览中模拟输出设备。

1. 在 `state.py` 中添加 `SoftProofingState`
2. 在 GUI 控件中添加软打样部分
3. 在 `controller_runtime.py` 中实现 ICC 变换链
4. 添加色域警告叠加
5. 使用打印机 ICC 配置文件测试

**需修改的文件**：
- `src/spektrafilm_gui/state.py` - 添加 SoftProofingState
- `src/spektrafilm_gui/widget_sections.py` - 添加 SoftProofingSection
- `src/spektrafilm_gui/controller_runtime.py` - 软打样变换
- `src/spektrafilm_gui/options.py` - 渲染意图枚举

### 阶段 3：HDR 预览（5-10 天）

**目标**：在支持 HDR 的显示器上预览 HDR 输出。

1. 创建 `HDRPreviewWidget`（自定义 QOpenGLWidget）
2. 实现色调映射着色器（ACES、Reinhard、filmic）
3. 添加平台相关的 HDR 表面检测
4. 与现有 HDR 导出管线集成
5. 在 GUI 中添加 HDR/SDR 预览切换

**需创建/修改的文件**：
- `src/spektrafilm_gui/hdr_preview.py` - 新的 HDR 预览控件
- `src/spektrafilm_gui/controller.py` - HDR 预览集成
- `src/spektrafilm_gui/state.py` - HDR 预览状态
- `src/spektrafilm_gui/napari_layout.py` - 添加 HDR 预览面板

### 阶段 4：高级色彩管理（5-10 天）

**目标**：专业色彩管理功能。

1. 集成 OpenColorIO 以支持 ACES 工作流
2. 自定义 ICC 配置文件加载
3. 显示器校准验证
4. 色彩管理的导出预览
5. 多显示器色彩管理

---

## 8. 参考文献

### Qt 文档
- [QColorSpace](https://doc.qt.io/qt-6/qcolorspace.html) - 色彩空间表示
- [QColorTransform](https://doc.qt.io/qt-6/qcolortransform.html) - 色彩空间转换
- [QScreen::colorSpace()](https://doc.qt.io/qt-6/qscreen.html#colorSpace) - 显示器色彩空间
- [QOpenGLWidget](https://doc.qt.io/qt-6/qopenglwidget.html) - OpenGL 渲染控件
- [QSurfaceFormat](https://doc.qt.io/qt-6/qsurfaceformat.html) - 表面格式配置

### HDR 标准
- [ITU-R BT.2100](https://www.itu.int/rec/R-REC-BT.2100) - HDR 显示标准（PQ/HLG）
- [ITU-R BT.2446](https://www.itu.int/rec/R-REC-BT.2446) - HDR-SDR 转换
- [ISO 21496-1](https://www.iso.org/standard/81524.html) - 增益图 HDR 编码
- [SMPTE ST 2084](https://www.smpte.org/st2084) - PQ EOTF

### 色彩管理
- [ICC 规范](https://www.color.org/specification.xalter) - ICC 配置文件格式
- [OpenColorIO](https://opencolorio.org/) - VFX 色彩管理
- [colour-science](https://colour-science.org/) - Python 色彩科学

### OpenGL HDR
- [OpenGL sRGB](https://www.khronos.org/opengl/wiki/SRGB) - sRGB 帧缓冲
- [GL_RGBA16F](https://registry.khronos.org/OpenGL-Refpages/gl4/) - Float16 纹理
- [Vulkan HDR](https://registry.khronos.org/vulkan/specs/1.3-extensions/man/html/VK_EXT_hdr_metadata.html) - HDR 元数据扩展

### 平台 HDR
- [Windows HDR](https://learn.microsoft.com/en-us/windows/win32/direct3darticles/high-dynamic-range) - DXGI HDR
- [Wayland HDR](https://gitlab.freedesktop.org/wayland/wayland-protocols/-/merge_requests/14) - 色彩管理协议
- [macOS EDR](https://developer.apple.com/documentation/metal/hdr_content/implementing_hdr_rendering_in_a_metal_app) - 扩展动态范围
