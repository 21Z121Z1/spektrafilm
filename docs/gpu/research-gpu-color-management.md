# GPU Acceleration & Color Management Research

> **UPDATE** (2026-05-28): ACEScg ICC mapping and HDR EXR rendition gaps have been fixed. macOS HDR HEIC export remains macOS-only.

Research date: 2026-05-27

## ⚠️ CRITICAL CONSTRAINT: ZERO Precision Loss

All GPU implementations MUST produce numerically identical results to CPU/NumPy output (within float32 epsilon, atol=1e-6). No approximations, no lossy optimizations, no float16 unless explicitly opted in. Every GPU kernel needs a test asserting `np.allclose(gpu, cpu, atol=1e-6)`. If a backend can't match precision, fall back to CPU for that operation.


## Executive Summary

Spektrafilm currently uses a clean `ArrayBackend` protocol (NumPy/MLX/CuPy) with backend-portable colour kernels, OpenImageIO for I/O, and `colour-science` for colour-space math. The project's spectral film simulation pipeline is well-structured for GPU acceleration, but several gaps exist: no ACES ICC profile mapping for Display P3, macOS-only HDR HEIC export, and no HDR EXR rendition mode. This research evaluates cross-platform GPU frameworks, colour management systems, and Python integration patterns to guide the next phase of development.

---

## 1. Cross-Platform GPU Compute Frameworks

### 1.1 Current Spektrafilm Architecture

The project already has a clean backend abstraction:

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

Backend selection cascade: `auto` -> MLX/Metal -> CuPy/CUDA -> NumPy fallback.

### 1.2 Framework Comparison Table

| Framework | Platforms | Python Maturity | NumPy Compat | Array API Std | Best For |
|-----------|-----------|-----------------|--------------|---------------|----------|
| **CuPy** | Linux/Windows (CUDA, ROCm) | High (v13+) | Drop-in | Yes | NVIDIA/AMD GPU scientific computing |
| **MLX** | macOS (Apple Silicon), Linux (CUDA) | Medium (v0.20+) | Partial | No | Apple unified memory, ML workloads |
| **JAX** | Linux/Windows/macOS (CPU/GPU/TPU) | High (v0.10+) | Good | Yes | Differentiable computing, TPU |
| **Taichi** | Linux/Windows/macOS (CPU/CUDA/Vulkan/Metal) | High (v1.7+) | Good integration | No | Custom kernels, simulation |
| **PyTorch** | All platforms | Very High | Partial | Yes | Deep learning, large ecosystem |
| **wgpu-py** | All platforms (via Dawn/wgpu-native) | Medium (v0.31+) | Via buffers | No | WebGPU compute shaders |

### 1.3 Array API Standard

The [Array API Standard](https://data-apis.github.io/array-api/latest/) defines a portable array interface. Key points:

- **Adoption**: NumPy 2.0+, CuPy 13+, JAX 0.4+, scikit-learn 1.3+, SciPy 1.11+
- **Interop**: `array-api-compat` package lets code run on any compliant backend
- **Key operations**: `asarray`, `matmul`, `einsum`, `astype`, device/dtype promotion rules
- **Limitation**: Does not cover FFT, sparse arrays, or advanced linalg

For Spektrafilm, the existing `ArrayBackend` protocol is already essentially an Array API subset. Adopting the standard formally would mean:
- Using `array-api-compat` for automatic backend dispatch
- Gaining interoperability with scikit-learn/scipy GPU paths
- Losing some custom methods (e.g., `fmax`, `nan_to_num`) that aren't in the standard

**Recommendation**: Keep the current `ArrayBackend` protocol. It covers exactly the operations needed and is simpler than adopting the full standard. If scipy/scikit-learn interop becomes important, wrap the backend with `array-api-compat` at the boundary.

### 1.4 GPU Tiling for Large Images (100MP+)

For very large images that exceed GPU VRAM, the standard pattern is:

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

**Key considerations**:
- CuPy: Use `cp.cuda.Device.memory_info()` to query free VRAM and auto-size tiles
- MLX: Unified memory means no explicit VRAM management, but lazy evaluation can cause memory spikes
- Overlap size depends on filter kernel radius (Gaussian blur needs `3*sigma` overlap)
- For purely element-wise operations (like colour transforms), no overlap is needed

### 1.5 GPU Fallback Chain Pattern

Current Spektrafilm pattern (already implemented):

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

**Enhancement opportunities**:
- Add Taichi as an intermediate option (Vulkan backend works on Linux without CUDA)
- Add JAX as an option for TPU/Google Cloud scenarios
- Add `wgpu-py` for WebGPU/Vulkan compute without CUDA dependency

### 1.6 Vulkan Compute via Taichi or wgpu-py

**Taichi** (v1.7.4):
- JIT-compiles Python-like code to Vulkan/CUDA/Metal
- Automatic parallelization over field dimensions
- Good for custom spectral kernels
- `ti.init(arch=ti.vulkan)` works on Linux with Mesa or NVIDIA drivers

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

**wgpu-py** (v0.31.0):
- Pure Python WebGPU bindings via wgpu-native (Rust)
- WGSL compute shaders for maximum performance
- Works on Linux (Vulkan), macOS (Metal), Windows (D3D12)
- Lower-level than Taichi but more portable

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

### 1.7 Performance Characteristics: MLX vs CuPy vs Taichi

| Operation | CuPy (CUDA) | MLX (Metal) | Taichi (Vulkan) | NumPy (CPU) |
|-----------|-------------|-------------|-----------------|-------------|
| Matrix 3x3 @ 50MP | ~0.5ms | ~0.8ms | ~1.2ms | ~50ms |
| Gaussian blur (sigma=5) | ~2ms | ~3ms | ~4ms | ~200ms |
| 4096-entry LUT interp | ~1ms | ~1.5ms | ~2ms | ~30ms |
| Spectral upsampling | ~5ms | ~8ms | ~10ms | ~500ms |

*Estimates for 50MP (8640x5760) float32 images. Actual times depend on hardware.*

**Key insight**: For Spektrafilm's pipeline (matrix transforms + LUT interpolation + element-wise ops), CuPy is ~2-3x faster than MLX on equivalent hardware, but MLX's unified memory eliminates transfer overhead for Apple Silicon.

---

## 2. Color Management Systems

### 2.1 Current Spektrafilm Color Architecture

The project uses a layered approach:
1. **colour-science** (v0.4.7): RGB colourspace definitions, matrix extraction, CCTF transfer functions
2. **OpenImageIO** (v3.1.13): Format-agnostic I/O with metadata preservation
3. **PIL/Pillow**: PNG/JPEG writing with ICC embedding
4. **exiv2** (pyexiv2): EXIF/IPTC/XMP metadata management
5. **Custom kernels** (`gpu/kernels/color.py`): Backend-portable CCTF encode/decode

Supported color spaces: sRGB, Display P3, DCI-P3, Adobe RGB, ProPhoto RGB, BT.2020, ACES2065-1, ACEScg.

### 2.2 ICC Profile Handling

Current state (`utils/io.py`):
- **ICC embedding**: Works for PNG (iCCP chunk), JPEG (APP2), TIFF (ICCProfile tag)
- **ICC reading**: Matches by byte comparison against bundled profiles, then by description
- **ICC sources**: Elle Stone V2 profiles (working spaces), Saucecontrol V2/V4 (Display P3, DCI-P3)
- **ACES profiles**: Both ACES2065-1 and ACEScg have linear ICC profiles (V2, g10 TRC)

**Gap**: No Display P3 linear ICC profile. The current `_ICC_FILENAMES` maps `("Display P3", False)` to nothing, falling through to `_ICC_PROFILES` which uses a different source.

**Recommendation**: Add `("Display P3", False)` entry pointing to a linear Display P3 profile, or generate one with `PIL.ImageCms.createProfile("DISPLAYP3")`.

### 2.3 ACES Workflow

Current ACES support:
- ACES2065-1 (AP0, linear, scene-referred interchange)
- ACEScg (AP1, linear, scene-referred working space)
- Both treated as linear (no CCTF), no clipping of negatives/highlights

**ACES 2.0 (ACESnext) developments**:
- ACES 2.0 introduces a new Output Transform with improved gamut mapping
- Still uses ACES2065-1 as the interchange space
- New ACEScg remains the recommended working space
- OCIO 2.4+ has built-in ACES 2.0 config support

**What's missing for full ACES integration**:
1. No OCIO integration (currently uses colour-science directly)
2. No ACES Output Transform (ODT/RRT) for display-referred output
3. No ACES Input Transform (IDT) for camera-native files
4. No ACEScct/ACEScc log working spaces for grading

### 2.4 HDR Standards & Gain Maps

Current HDR support (`utils/hdr_photo.py`):
- macOS-only HEIC export via Swift/CoreImage
- Gain map approach: SDR base + per-pixel gain map
- `HDRPhotoMapping` dataclass with ~40 parameters
- Profile-aware HDR curve fitting from film/paper characteristics
- Two gain map modes: `luma` (single channel) and `rgb` (per-channel)

**ISO 21496-1 (Gain Map HDR)**:
- Standardizes the Apple/Adobe gain map approach
- Single file contains SDR base image + gain map metadata
- Backward compatible: SDR devices see the base image
- Gain map stores `log2(hdr_luminance / sdr_luminance)` per pixel
- Metadata includes: `gainMapMin`, `gainMapMax`, `gamma`, `offsetSDR`, `offsetHDR`, `hdrCapacityMin`, `hdrCapacityMax`

**Apple's implementation** (iOS 17+):
- HEIC with embedded gain map
- `kCGImageAuxiliaryDataTypeHDRGainMap` in CoreImage
- Display P3 color space for SDR base, linear for HDR rendition

**Adobe's implementation** (Lightroom/Camera Raw):
- JPEG with MPF (Multi-Picture Format) auxiliary image
- ISO 21496-1 compliant metadata in XMP

**What Spektrafilm needs**:
1. Cross-platform gain map encoding (not just macOS CoreImage)
2. ISO 21496-1 metadata generation for JPEG/HEIC
3. EXR HDR rendition export (currently only scene-linear archive)
4. BT.2100 PQ/HLG encoding for HDR display output

### 2.5 Tone Mapping Operators

Current implementation in `hdr_photo.py`:
- **Logistic rolloff**: Custom paper-curve-based shoulder compression
- **Logarithmic rolloff**: Fallback for non-profile-aware mode
- **SDR base mapping**: Logarithmic shoulder with `sdr_paper_white` scaling
- **Path-to-white**: Smoothstep-based desaturation toward luminance at high EVs

**Industry-standard tone mapping operators**:

| Operator | Type | Use Case | Reference |
|----------|------|----------|-----------|
| **ACES (RRT+ODT)** | Filmic | Scene-referred to display | AMPAS standard |
| **Reinhard** | Global/Local | HDR photography | Reinhard et al. 2002 |
| **Filmic (Hable)** | Filmic | Game rendering | John Hable, Uncharted 2 |
| **BT.2446** | HDR->SDR | Broadcast HDR conversion | ITU-R BT.2446 |
| **BT.2390** | EETF | HDR display mapping | ITU-R BT.2390 |
| **Display-referred** | Per-display | Content-adaptive | Dolby Vision IQ |

**Spektrafilm's approach is well-designed**: The paper-curve-based rolloff is physically grounded in actual photographic paper response curves (Logistic fits from Fujifilm/Kodak data). This is more authentic than generic Reinhard/ACES for the film simulation use case.

### 2.6 Gamut Mapping

Current implementation: Luma-preserving chroma compression in `_apply_hdr_color_recovery()`.

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

**Gamut mapping strategies**:

| Strategy | Description | When to Use |
|----------|-------------|-------------|
| **Absolute colorimetric** | Clip to destination gamut boundary | Proof matching |
| **Relative colorimetric** | Scale white point, clip rest | Standard print simulation |
| **Perceptual** | Compress entire gamut to fit | Cross-gamut display |
| **Saturation** | Preserve saturation over hue | Business graphics |
| **CSS Color 4 gamut mapping** | Oklch-based perceptual mapping | Web/modern workflows |

**CSS Color 4 approach** (used by ColorAide library):
```python
# Perceptual gamut mapping in Oklch space
# 1. Convert to Oklch (perceptual lightness, chroma, hue)
# 2. Reduce chroma until in-gamut, preserving L and h
# 3. If still out of gamut, reduce L slightly
```

**Recommendation for Spektrafilm**: The current luma-preserving approach is good for HDR highlight handling. For cross-gamut SDR output (e.g., BT.2020 -> sRGB), consider adding Oklch-based perceptual mapping via colour-science or coloraide.

### 2.7 OpenColorIO (OCIO) Integration

**OCIO** (v2.x) is the industry standard for color management in VFX/animation:
- Used by Nuke, Blender, DaVinci Resolve, Maya, Houdini
- Provides GPU-accelerated color transforms via GLSL/Metal/CUDA
- ACES configs maintained by ASWF
- Python bindings: `PyOpenColorIO`

**Python API pattern**:
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

**OCIO GPU acceleration**:
```python
# GPU-accelerated transform (requires OpenGL/Metal/CUDA context)
gpu = processor.getDefaultGPUProcessor()
# Creates GLSL/Metal shader code for the transform chain
shader_desc = gpu.extractGpuShaderInfo()
```

**When to use OCIO vs colour-science**:
- **OCIO**: When you need ACES Output Transforms, LUT-based workflows, or cross-application consistency
- **colour-science**: When you need spectral calculations, custom transfer functions, or fine-grained control

**Recommendation**: Add optional OCIO integration for ACES Output Transform support. Keep colour-science for spectral operations. OCIO would replace the manual CCTF encode/decode in `gpu/kernels/color.py` for ACES workflows.

---

## 3. Python GPU Image Processing Patterns

### 3.1 colour-science (v0.4.7)

The primary color math library. Key capabilities used by Spektrafilm:

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

**GPU integration pattern** (what Spektrafilm does):
1. Pre-compute matrices on CPU using colour-science
2. Transfer matrices to GPU as constants
3. Apply per-pixel transforms using backend matmul/einsum
4. Implement transfer functions as backend element-wise ops

This is the correct pattern - colour-science is CPU-only but its matrix/constant extraction is fast and happens once.

### 3.2 OpenImageIO (OIIO) Python Bindings (v3.1.13)

Current usage in Spektrafilm:

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

**OIIO capabilities not yet used**:
- `ImageBuf`: In-memory image manipulation with ImageBufAlgo functions
- `ImageCache`: Transparent multi-resolution caching for huge images
- `TextureSystem`: Filtered texture lookups (useful for spectral LUTs)
- Color conversion: `oiio.ImageBufAlgo.colorconvert()` with OCIO integration
- `oiiotool`: CLI for batch processing (could be used for validation)

**OIIO + OCIO integration**:
```python
# OIIO can use OCIO for color transforms
import OpenImageIO as oiio
buf = oiio.ImageBuf("input.exr")
oiio.ImageBufAlgo.colorconvert(buf, buf, "ACEScg", "sRGB - Display")
buf.write("output.png")
```

### 3.3 Array Backend Interoperability

Current Spektrafilm pattern for backend-agnostic code:

```python
# Pattern: pre-compute on CPU, transfer to GPU, compute, transfer back
matrix_np = colour.RGB_COLOURSPACES['ACEScg'].matrix_RGB_to_XYZ
matrix_gpu = backend.asarray(matrix_np)  # One-time transfer
result_gpu = backend.matmul(pixels_gpu, matrix_gpu.T)  # GPU compute
result_np = backend.to_numpy(result_gpu)  # Transfer back when needed
```

**Zero-copy patterns**:
- CuPy: `cp.asarray(numpy_array)` copies to GPU; `cp.asnumpy(gpu_array)` copies back
- MLX: Unified memory means `mx.array(numpy_array)` may share memory on Apple Silicon
- NumPy: Already CPU, `asarray` is often a view

**Streaming/async patterns** (for pipeline overlap):
```python
# CuPy: async transfer with streams
stream = cp.cuda.Stream()
with stream:
    gpu_data = cp.asarray(cpu_data)
    result = process(gpu_data)
# Stream sync happens automatically on to_numpy()
```

### 3.4 HDR Image I/O Patterns

**EXR (OpenEXR)**:
```python
# Scene-linear archive (current Spektrafilm default)
spec.attribute("oiio:ColorSpace", "ACEScg")
spec.attribute("chromaticities", oiio.TypeDesc("float[8]"), chromaticities)
spec.attribute("whiteLuminance", 203.0)  # cd/m² reference white

# HDR rendition (what the code-review recommended adding)
# Use hdr_rendition mode to prepare gain-mapped data before writing
```

**HEIC/HEIF with gain map** (current macOS-only):
```python
# Pattern: prepare SDR + HDR renditions, encode via platform tool
renditions = prepare_hdr_photo_renditions(image_data, mapping=mapping)
# sdr_rgb: [0, 1] range, CCTF-encoded
# hdr_rgb: [0, headroom] range, linear
# headroom: typically 2-8x SDR white
```

**JPEG with gain map (ISO 21496-1)**:
```python
# Cross-platform approach using libheif or custom MPF encoding
# 1. Write SDR base as primary JPEG
# 2. Write gain map as auxiliary image (MPF or EXIF auxiliary)
# 3. Write ISO 21496-1 metadata in XMP
```

### 3.5 Spectral Processing on GPU

Spektrafilm's core spectral simulation involves:
1. **Spectral upsampling**: RGB -> reflectance spectrum (31+ samples)
2. **Illuminant multiplication**: Spectrum × illuminant power
3. **Sensitivity integration**: Spectrum × cone sensitivity curves
4. **Density curves**: Film/paper response via LUT interpolation

These operations are well-suited to GPU:
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

## 4. Library Version Summary

| Library | Current Version | Latest Stable | Spektrafilm Uses |
|---------|----------------|---------------|------------------|
| CuPy | 13.x / ROCm 7.0 | 13.4+ | GPU backend |
| MLX | 0.20+ (CUDA on Linux) | 0.22+ | GPU backend (macOS primary) |
| colour-science | 0.4.7 | 0.4.7 | Color math, RGB colourspaces |
| OpenImageIO | 3.1.13 | 3.1.13 | Image I/O |
| OpenColorIO | 2.4.x | 2.4.1 | Not yet used |
| Taichi | 1.7.4 | 1.7.4 | Not yet used |
| wgpu-py | 0.31.0 | 0.31.0 | Not yet used |
| JAX | 0.10.1 | 0.10.1 | Not yet used |
| NumPy | 2.x | 2.2+ | CPU backend |
| OpenCV | 4.13.0 | 4.13.0 | Not used |
| ColorAide | Latest | Latest | Not used (alternative to colour-science) |
| Pillow | Latest | Latest | PNG/JPEG writing |

---

## 5. Recommendations

### 5.1 GPU Acceleration

**Priority 1: Keep current ArrayBackend architecture**
The existing protocol is clean, well-tested, and covers all needed operations. Don't replace it with Array API standard - the custom protocol is more focused.

**Priority 2: Add Taichi as optional backend**
Taichi's Vulkan backend provides GPU acceleration on Linux without CUDA. This fills the gap between "MLX (macOS only)" and "CuPy (NVIDIA only)".

```python
# Proposed addition to backend.py
def _select_taichi_backend(*, precision: str) -> ArrayBackend:
    from spektrafilm.gpu.taichi_backend import TaichiBackend
    return TaichiBackend(precision=precision)

# In select_backend():
# auto cascade: MLX -> CuPy -> Taichi/Vulkan -> NumPy
```

**Priority 3: Add GPU tiling for 100MP+ images**
The spectral simulation pipeline processes full-frame images. Add automatic tiling when GPU memory is insufficient.

### 5.2 Color Management

**Priority 1: Fix ACEScg ICC mapping (H1)**
Add ACEScg to `_ICC_FILENAMES` and `_ICC_PROFILES` with the existing Elle Stone V2 linear profile.

**Priority 2: Add Display P3 linear ICC profile**
The `("Display P3", False)` entry is missing from `_ICC_FILENAMES`.

**Priority 3: Add HDR EXR rendition mode**
The `hdr_rendition` exr_mode exists in code but needs validation. Ensure it produces valid HDR EXR files with proper `whiteLuminance` and `chromaticities` metadata.

**Priority 4: Cross-platform HDR gain map encoding**
Replace the macOS-only Swift/CoreImage HEIC encoder with a cross-platform solution:
- Option A: `libheif` Python bindings (supports gain map metadata)
- Option B: Custom JPEG MPF encoding with ISO 21496-1 XMP metadata
- Option C: Pillow + custom gain map auxiliary image writing

**Priority 5: Optional OCIO integration**
Add OpenColorIO as an optional dependency for ACES Output Transform support. This would enable:
- Proper ACES RRT+ODT for display-referred output
- LUT-based color pipeline compatibility
- Cross-application color consistency

### 5.3 Specific Code Changes

1. **`utils/io.py`**: Add `save_hdr_rendition_exr()` helper that calls `prepare_hdr_photo_renditions()` then writes EXR with `hdr_rendition` mode and proper metadata.

2. **`utils/io.py`**: Add ACEScg to `_ICC_FILENAMES`:
   ```python
   ("ACEScg", True): "ellelstone/ACEScg-elle-V2-g10.icc",
   ("ACEScg", False): "ellelstone/ACEScg-elle-V2-g10.icc",
   ```

3. **`gpu/backend.py`**: Add Taichi backend option in the fallback chain.

4. **`hdr_photo.py`**: Add `save_hdr_photo_jpeg_gainmap()` for cross-platform ISO 21496-1 output.

---

## 5.4 Current Implementation Audit Addendum (2026-05-27)

The recommendations above were re-checked against the current workspace before implementation. Several items in this research note are now stale:

- ACEScg ICC mapping is already present in `_ICC_FILENAMES` and `_ICC_PROFILES`, using the bundled Elle Stone linear ACEScg profile.
- Display P3 linear ICC mapping is already present via `DisplayP3-linear.icc`, with tests confirming a linear TRC.
- HDR rendition EXR support already exists through `save_hdr_rendition_exr()` and `save_image_oiio(..., exr_mode="hdr_rendition")`.
- Generic backend tiling exists in `src/spektrafilm/gpu/backend.py`.

The real issues found in this audit were narrower:

- GPU CCTF encoding supported DCI-P3 decoding but not DCI-P3 encoding, even though `DCI-P3` is exposed in GUI color-space options. This is fixed by matching the ICC registry / colour-science DCI-P3 2.6 gamma transfer function in the backend CCTF encoder.
- HDR rendition EXR was discarding `prepare_hdr_photo_renditions()` diagnostics, unlike HEIC HDR photo export. This is fixed so `save_image_oiio()` and `save_hdr_rendition_exr()` return HDR mapping diagnostics for authored HDR rendition EXR.
- The `save_image_oiio()` docstring did not fully document `scene_luminance`, `scene_rgb`, `hdr_mapping_kwargs`, `exr_mode`, or the diagnostics return contract. This is now documented at the API boundary.
- Verification also exposed that the optional Halide backend was partially documented and tested but not fully integrated into backend selection, GUI/backend options, optional extras, runtime float64 rejection, and cache cleanup. Halide is now strict opt-in, float32-only, and excluded from `auto` selection.
- Runtime/HDR metadata compatibility was tightened: `Simulator.process_with_metadata()` preserves the old no-keyword call shape unless `include_scene_rgb=True`, HEIC output paths are validated before invoking the encoder, and scene-luminance grafting now uses perceptual look luminance instead of max channel luminance.

Deferred items remain future architecture work, not current one-shot bug fixes:

- Taichi/Vulkan backend: not a drop-in `ArrayBackend` replacement because Taichi does not expose NumPy-like array semantics for the current protocol.
- Optional OCIO: still valuable for ACES Output Transform / cross-application display workflows, but not required for the current ICC/OIIO metadata fixes.
- Cross-platform HDR gain-map encoding: still larger encoder work. The current production HEIC HDR writer intentionally remains the macOS CoreImage path.

---

## 6. References

### GPU Compute
- [Array API Standard](https://data-apis.github.io/array-api/latest/) - Portable array interface specification
- [CuPy Documentation](https://docs.cupy.dev/en/stable/) - NumPy-compatible GPU arrays
- [MLX GitHub](https://github.com/ml-explore/mlx) - Apple's array framework for Apple Silicon
- [Taichi Documentation](https://docs.taichi-lang.org/) - Parallel programming for GPU compute
- [wgpu-py Documentation](https://wgpu-py.readthedocs.io/en/latest/) - WebGPU for Python
- [JAX Documentation](https://jax.readthedocs.io/) - Composable transformations of NumPy

### Color Management
- [OpenColorIO](https://opencolorio.org/) - Industry-standard color management
- [OCIO GitHub](https://github.com/AcademySoftwareFoundation/OpenColorIO) - OCIO source and configs
- [colour-science](https://colour-science.org/) - Color science for Python
- [OpenImageIO](https://openimageio.org/) - Image I/O library
- [ACES Central](https://acescentral.com/) - Academy Color Encoding System
- [ColorAide](https://facelessuser.github.io/coloraide/) - Pure Python color manipulation

### HDR Standards
- [ISO 21496-1](https://www.iso.org/standard/81524.html) - Gain map HDR encoding standard
- [Apple HDR Gain Map](https://developer.apple.com/documentation/coreimage/cigainmapapply) - Apple's implementation
- [ITU-R BT.2100](https://www.itu.int/rec/R-REC-BT.2100) - HDR display standard (PQ/HLG)
- [ITU-R BT.2446](https://www.itu.int/rec/R-REC-BT.2446) - HDR-SDR conversion methods

### VFX Industry Standards
- [ASWF](https://www.aswf.io/) - Academy Software Foundation
- [OpenEXR](https://openexr.com/) - HDR image file format
- [Open Shading Language](https://github.com/AcademySoftwareFoundation/openshadinglanguage) - OSL for renderers
