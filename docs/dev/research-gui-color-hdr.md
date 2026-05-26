# GUI Color Management & HDR Preview Research

Research date: 2026-05-27

## Executive Summary

Spektrafilm's GUI currently uses napari/VisPy (OpenGL) for image display with PIL.ImageCms for ICC-based display transforms. All preview images are rendered as 8-bit sRGB, with no HDR preview capability and no Qt-level color management. This research evaluates Qt6's color management APIs, HDR surface rendering paths, and soft proofing implementation strategies for a professional photo editing workflow.

---

## 1. Current Display Pipeline Audit

### 1.1 Architecture Overview

The display pipeline flows through three layers:

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

### 1.2 Key Code Paths

**Input preview** (`controller.py:726-741`):
```python
preview_display_image = self._prepare_input_color_preview_image(
    preview_image,
    input_color_space=state.input_image.input_color_space,
    apply_cctf_decoding=state.input_image.apply_cctf_decoding,
)
```
Converts input from its native color space to sRGB for display via `colour.RGB_to_RGB()`.

**Output display** (`controller_runtime.py:249-286`):
```python
def prepare_output_display_image(
    image_data, *, output_encoding, use_display_transform,
    padding_pixels, imagecms_module, colour_module, pil_image_module,
) -> tuple[np.ndarray, str]:
```
Two paths:
1. **No display transform**: CCTF-encode to sRGB, convert to uint8
2. **With display transform**: ICC transform from output profile to display profile via `imagecms_module.profileToProfile()`

**Display transform** (`controller_runtime.py:164-212`):
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

### 1.3 Current Limitations

| Limitation | Impact | Severity |
|-----------|--------|----------|
| **uint8 output only** | Clips HDR values, banding in gradients | Critical for HDR |
| **sRGB preview assumption** | Wrong colors on P3/BT.2020 displays | High |
| **No QColorSpace usage** | Qt doesn't know image color space | Medium |
| **No soft proofing** | Can't simulate print/display output | Medium |
| **PIL.ImageCms only** | No GPU acceleration for color transforms | Low |
| **No HDR surface support** | Can't preview >1.0 values on HDR displays | Critical for HDR |
| **Napari layer has no color space tag** | VisPy assumes sRGB | High |

### 1.4 Display Profile Detection

Current method (`controller_runtime.py:117-124`):
```python
def display_profile_details(*, imagecms_module):
    display_profile = imagecms_module.get_display_profile()
    # Returns (profile_object, profile_name_string)
```

`PIL.ImageCms.get_display_profile()` behavior:
- **Windows**: Reads ICC profile from device context (DC)
- **macOS**: Reads from ColorSync
- **Linux**: Returns `None` (no standard API)

The GUI disables the display transform toggle when no profile is detected (`controller.py:424-431`).

---

## 2. Qt6 Color Management Capabilities

### 2.1 QColorSpace (Qt 5.14+, mature in Qt 6)

Qt6 provides built-in color space representation:

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

Qt6 can create color transforms between color spaces:

```python
from PySide6.QtGui import QColorSpace, QColorTransform

src = QColorSpace(QColorSpace.NamedColorSpace.DisplayP3)
dst = QColorSpace(QColorSpace.NamedColorSpace.SRgb)

# Create transform
transform = src.transformationToColorSpace(dst)

# Apply to QImage
converted_image = transformed_image  # Qt applies the transform
```

### 2.3 QImage Color Space Integration

```python
from PySide6.QtGui import QImage, QColorSpace

# Tag image with color space
image = QImage(data, width, height, QImage.Format.Format_RGBA8888)
image.setColorSpace(QColorSpace(QColorSpace.NamedColorSpace.DisplayP3))

# Qt will automatically convert when painting to a different color space widget
```

### 2.4 QColorTransferFunction (HDR)

Qt6 supports HDR transfer functions:

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

### 2.5 Qt6 Color Management Gaps

| Feature | Qt6 Status | Workaround |
|---------|-----------|------------|
| **HDR window surface** | Qt 6.5+ Wayland HDR, Windows HDR | Platform-specific |
| **float16 framebuffer** | Not in QOpenGLWidget by default | Custom FBO required |
| **scRGB output** | Windows only (via DXGI) | Not cross-platform |
| **ICC profile from display** | macOS yes, Windows partial, Linux no | PIL.ImageCms fallback |
| **Soft proofing intent** | No built-in soft proofing | Manual ICC chain |
| **HDR10 metadata** | No Qt API for HDR metadata | Vulkan `VK_EXT_hdr_metadata` |
| **PQ/HLG rendering** | QColorSpace can represent, but no HDR surface | Need OpenGL FBO + tone map |

---

## 3. HDR Preview Implementation Path

### 3.1 Strategy Overview

HDR preview requires three components:

1. **HDR-capable framebuffer**: float16/float32 FBO instead of default 8-bit
2. **Tone mapping shader**: Map HDR values to display range
3. **HDR display surface**: OS-level HDR window (platform-specific)

### 3.2 OpenGL HDR Rendering via QOpenGLWidget

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

### 3.3 Tone Mapping Shader (GLSL)

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

### 3.4 Platform-Specific HDR Surfaces

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

### 3.5 Recommended HDR Preview Architecture

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

## 4. Soft Proofing Implementation

### 4.1 Soft Proofing Concepts

Soft proofing simulates how an image will appear on a target device (printer, different display). The transform chain is:

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

### 4.2 Rendering Intents

| Intent | Use Case | Behavior |
|--------|----------|----------|
| **Perceptual** | Photography | Compresses entire gamut to fit |
| **Relative Colorimetric** | Proof matching | Maps white point, clips out-of-gamut |
| **Absolute Colorimetric** | Color matching | Preserves absolute colors, no white map |
| **Saturation** | Business graphics | Preserves saturation over hue accuracy |

### 4.3 Implementation with PIL.ImageCms

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

### 4.4 Soft Proofing UI Integration

```python
class SoftProofingState:
    enabled: bool = False
    proof_profile_path: str | None = None  # Printer/display ICC profile
    rendering_intent: str = "perceptual"    # perceptual|relative|absolute|saturation
    simulate_paper_white: bool = True       # Simulate paper white point
    simulate_black_point: bool = True       # Simulate printer black point
    gamut_warning: bool = False             # Highlight out-of-gamut pixels
```

### 4.5 Gamut Warning Overlay

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

## 5. Display Transform Chain Recommendations

### 5.1 Recommended Architecture

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

### 5.2 Implementation Phases

**Phase 1: Qt Color Space Tagging (Low effort, high value)**
- Tag all QImages with correct QColorSpace
- Let Qt handle color conversion automatically
- Fixes oversaturation on wide-gamut displays

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

**Phase 2: Display Profile Integration (Medium effort)**
- Use Qt's `QScreen` to detect display color profile
- Fall back to PIL.ImageCms for Linux
- Display profile name in status bar

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

**Phase 3: HDR Preview (High effort, high value)**
- Custom OpenGL widget with float16 FBO
- Tone mapping shader
- Platform-specific HDR surface
- Headroom detection

**Phase 4: Soft Proofing (Medium effort)**
- Add proof profile selection UI
- Implement ICC transform chain
- Gamut warning overlay
- Paper white/black simulation

### 5.3 Napari Integration Challenges

Napari uses VisPy (OpenGL) internally. Key challenges:

1. **No color space API**: Napari layers don't have a color space property
2. **sRGB assumption**: VisPy assumes all textures are sRGB
3. **uint8 textures**: Default texture format is uint8
4. **No HDR surface**: Napari's canvas doesn't request HDR surfaces

**Workarounds**:
- Pre-convert to sRGB before passing to napari (current approach)
- Use napari's shader hooks for custom tone mapping (if available)
- Replace napari's canvas with custom QOpenGLWidget for HDR preview
- Use napari only for SDR preview, add separate HDR preview window

---

## 6. Specific Qt API Calls and Code Patterns

### 6.1 Complete HDR Preview Widget

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

### 6.2 QColorSpace for Napari Layer Metadata

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

### 6.3 Display Headroom Detection

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

### 6.4 ICC Profile Management

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

## 7. Implementation Roadmap

### Phase 1: Qt Color Space Awareness (1-2 days)

**Goal**: Fix oversaturation on wide-gamut displays.

1. Add `QColorSpace` tagging to all images displayed in napari
2. Map Spektrafilm color space names to `QColorSpace` presets
3. Store color space metadata on napari layers
4. Test on Display P3 and Adobe RGB monitors

**Files to modify**:
- `src/spektrafilm_gui/controller_runtime.py` - Add QColorSpace mapping
- `src/spektrafilm_gui/controller_layers.py` - Tag layers with color space
- `src/spektrafilm_gui/app.py` - Initialize Qt color management

### Phase 2: Soft Proofing (3-5 days)

**Goal**: Simulate output devices in the preview.

1. Add `SoftProofingState` to `state.py`
2. Add soft proofing section to GUI widgets
3. Implement ICC transform chain in `controller_runtime.py`
4. Add gamut warning overlay
5. Test with printer ICC profiles

**Files to modify**:
- `src/spektrafilm_gui/state.py` - Add SoftProofingState
- `src/spektrafilm_gui/widget_sections.py` - Add SoftProofingSection
- `src/spektrafilm_gui/controller_runtime.py` - Soft proofing transforms
- `src/spektrafilm_gui/options.py` - Rendering intent enum

### Phase 3: HDR Preview (5-10 days)

**Goal**: Preview HDR output on HDR-capable displays.

1. Create `HDRPreviewWidget` (custom QOpenGLWidget)
2. Implement tone mapping shaders (ACES, Reinhard, filmic)
3. Add platform-specific HDR surface detection
4. Integrate with existing HDR export pipeline
5. Add HDR/SDR preview toggle to GUI

**Files to create/modify**:
- `src/spektrafilm_gui/hdr_preview.py` - New HDR preview widget
- `src/spektrafilm_gui/controller.py` - HDR preview integration
- `src/spektrafilm_gui/state.py` - HDR preview state
- `src/spektrafilm_gui/napari_layout.py` - Add HDR preview panel

### Phase 4: Advanced Color Management (5-10 days)

**Goal**: Professional color management features.

1. OpenColorIO integration for ACES workflows
2. Custom ICC profile loading
3. Display calibration verification
4. Color-managed export preview
5. Multi-monitor color management

---

## 8. References

### Qt Documentation
- [QColorSpace](https://doc.qt.io/qt-6/qcolorspace.html) - Color space representation
- [QColorTransform](https://doc.qt.io/qt-6/qcolortransform.html) - Color space conversions
- [QScreen::colorSpace()](https://doc.qt.io/qt-6/qscreen.html#colorSpace) - Display color space
- [QOpenGLWidget](https://doc.qt.io/qt-6/qopenglwidget.html) - OpenGL rendering widget
- [QSurfaceFormat](https://doc.qt.io/qt-6/qsurfaceformat.html) - Surface format configuration

### HDR Standards
- [ITU-R BT.2100](https://www.itu.int/rec/R-REC-BT.2100) - HDR display standard (PQ/HLG)
- [ITU-R BT.2446](https://www.itu.int/rec/R-REC-BT.2446) - HDR-SDR conversion
- [ISO 21496-1](https://www.iso.org/standard/81524.html) - Gain map HDR encoding
- [SMPTE ST 2084](https://www.smpte.org/st2084) - PQ EOTF

### Color Management
- [ICC Specification](https://www.color.org/specification.xalter) - ICC profile format
- [OpenColorIO](https://opencolorio.org/) - VFX color management
- [colour-science](https://colour-science.org/) - Python color science

### OpenGL HDR
- [OpenGL sRGB](https://www.khronos.org/opengl/wiki/SRGB) - sRGB framebuffer
- [GL_RGBA16F](https://registry.khronos.org/OpenGL-Refpages/gl4/) - Float16 textures
- [Vulkan HDR](https://registry.khronos.org/vulkan/specs/1.3-extensions/man/html/VK_EXT_hdr_metadata.html) - HDR metadata extension

### Platform HDR
- [Windows HDR](https://learn.microsoft.com/en-us/windows/win32/direct3darticles/high-dynamic-range) - DXGI HDR
- [Wayland HDR](https://gitlab.freedesktop.org/wayland/wayland-protocols/-/merge_requests/14) - Color management protocol
- [macOS EDR](https://developer.apple.com/documentation/metal/hdr_content/implementing_hdr_rendering_in_a_metal_app) - Extended Dynamic Range
