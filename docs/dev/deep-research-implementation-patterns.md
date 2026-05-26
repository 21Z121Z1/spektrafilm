# Deep Research: Implementation Patterns for Spektrafilm

**Date:** 2026-05-27
**Purpose:** Exhaustive research to drive the Spektrafilm implementation roadmap

---

## Table of Contents

1. [colour-science GPU Acceleration & Array API](#1-colour-science-gpu-acceleration--array-api)
2. [OpenColorIO Python ACES Workflow](#2-opencolorio-python-aces-workflow)
3. [ICC Profile v4 Creation & Embedding](#3-icc-profile-v4-creation--embedding)
4. [HDR Gain Map Encoding (ISO 21496)](#4-hdr-gain-map-encoding-iso-21496)
5. [Vulkan Compute Shaders via Python](#5-vulkan-compute-shaders-via-python)
6. [WebGPU / wgpu-py Image Processing](#6-webgpu--wgpu-py-image-processing)
7. [GPU Tiling for Large Image Processing](#7-gpu-tiling-for-large-image-processing)
8. [ACES Tone Mapping (Scene-Referred)](#8-aces-tone-mapping-scene-referred)
9. [OpenImageIO HDR/EXR Metadata & Color Management](#9-openimageio-hdrexr-metadata--color-management)
10. [Array API Standard & Cross-Backend Interoperability](#10-array-api-standard--cross-backend-interoperability)
11. [Integration Recommendations for Spektrafilm](#11-integration-recommendations-for-spektrafilm)

---

## 1. colour-science GPU Acceleration & Array API

### What We Found

**colour-science v0.4.7** is the latest release (Python 3.11-3.14). It is a NumFOCUS-affiliated, BSD-3-Clause library providing comprehensive colour science algorithms. Key finding: colour-science has **optional dependencies** on `opencolorio>=2` and `openimageio>=3`, meaning it already integrates with both OCIO and OIIO.

**Current GPU status:** colour-science does NOT yet have a native CuPy/Array API backend in the main branch. The `colour.hints` module uses `numpy.typing.NDArray` and `numpy.typing.ArrayLike` exclusively. There is no `cupy` or array-api-compat integration in the core. The library is NumPy-only at the computation level.

**Array API adoption:** The `colour.algebra` module uses a `ModuleAPI` wrapper pattern for backwards compatibility but does not dispatch to alternative array backends. The library's computation graph (via `networkx`) operates on NumPy arrays.

### Code Examples

```python
# colour-science current usage (NumPy only)
import colour
import numpy as np

# RGB colourspace conversion
rgb = np.array([0.5, 0.3, 0.1])
aces = colour.RGB_to_RGB(rgb, 'sRGB', 'ACEScg')

# Spectral operations
cmfs = colour.MFS_CMFS['CIE 1931 2 Degree Standard Observer']
illuminant = colour.SDS_ILLUMINANTS['D65']
```

### How It Applies to Spektrafilm

Spektrafilm already depends on `colour-science~=0.4.6`. Since colour-science has no native GPU dispatch, Spektrafilm's existing `ArrayBackend` protocol (in `gpu/backend.py`) is the correct abstraction layer. The pattern should be:

1. Use colour-science for **reference implementations** and **colour space definitions** (lookup tables, transforms matrices)
2. Extract the numerical computation into Spektrafilm's own backend-dispatched functions
3. Use colour-science's `RGB_COLOURSPACES` dict for colour space metadata, but perform actual matrix math through `ArrayBackend.matmul()` etc.

### Libraries & Versions

| Library | Version | Purpose |
|---|---|---|
| `colour-science` | `~=0.4.6` (current) | Colour space definitions, reference transforms, CMFs |
| `opencolorio` | `>=2,<3` | OCIO integration (optional dep of colour-science) |
| `openimageio` | `>=3,<4` | Image I/O (optional dep of colour-science) |

### Integration Complexity: **LOW**
Already integrated. No changes needed for the library itself; the work is in how Spektrafilm dispatches computation.

---

## 2. OpenColorIO Python ACES Workflow

### What We Found

**OpenColorIO (OCIO) v2.x** is the industry-standard color management framework from the Academy Software Foundation. It has native Python bindings (`PyOpenColorIO`) and ships with built-in ACES configurations.

**Key API pattern:**
```python
import PyOpenColorIO as ocio

# Load built-in ACES config (v2.1.0 with ACES v1.3)
config = ocio.Config.CreateFromBuiltinConfig(
    'studio-config-v2.1.0_aces-v1.3_ocio-v2.3'
)

# Create a processor for color space conversion
processor = config.getProcessor('ACES - ACEScg', 'Output - sRGB')
cpu = processor.getDefaultCPUProcessor()

# Apply to pixel data
rgb = [0.5, 0.3, 0.1]
result = cpu.applyRGB(rgb)

# For bulk processing (more efficient)
processor = config.getProcessor('ACES - ACEScg', 'Output - sRGB')
cpu = processor.getDefaultCPUProcessor()
# Can process entire image arrays
```

**OCIO v2 features relevant to Spektrafilm:**
- Built-in ACES configs (no external config files needed)
- `ColorConfig` class with `getColorSpaceNames()`, `getColorSpaceFamilyByName()`, etc.
- GPU processor path (for OpenGL/Vulkan compute)
- Named transforms for custom scene-referred workflows
- Display/view transforms with looks support

**OIIO integration:** OpenImageIO has `checked_find_package(OpenColorIO REQUIRED)` and exposes `ColorConfig` in its Python stubs, including `getColorSpaceFromFilepath()`, display/view management, and `supportsOpenColorIO` flag.

### Code Examples

```python
import PyOpenColorIO as ocio

# Full ACES workflow
config = ocio.Config.CreateFromBuiltinConfig(
    'studio-config-v2.1.0_aces-v1.3_ocio-v2.3'
)

# List available color spaces
for name in config.getColorSpaceNames():
    print(name)

# Scene-referred to display transform
proc = config.getProcessor(
    ocio.ColorSpaceTransform(src='ACES - ACEScg', dst='Output - sRGB')
)
cpu = proc.getDefaultCPUProcessor()

# Process an entire image (float32 array)
import numpy as np
image = np.random.rand(1024, 1024, 3).astype(np.float32)
# OCIO can apply in-place or return new array
```

### How It Applies to Spektrafilm

Spektrafilm already uses `colour-science` for ACES colour space definitions (`ACES2065-1`, `ACEScg`). OCIO would provide:

1. **Standardized ACES Output Transforms** (RRT+ODT) that are certified correct
2. **Display-referred output** with proper tone mapping for various displays
3. **Config-driven** colour pipeline (swap configs without code changes)
4. **ACEScg interchange** — Spektrafilm's `ACES_WORKING_COLOR_SPACE = "ACEScg"` maps directly to OCIO's `ACES - ACEScg`

**Recommended integration path:** Add OCIO as an optional dependency. Use it for the output/display transform path (scene-referred ACEScg → display sRGB/P3/HDR), while keeping colour-science for the spectral/emulsion simulation internals.

### Libraries & Versions

| Library | Version | Purpose |
|---|---|---|
| `opencolorio` | `>=2.3,<3` | ACES transforms, display management |
| Install | `pip install opencolorio` | Python 3.11-3.13 supported |

### Integration Complexity: **MEDIUM**
OCIO itself is straightforward, but integrating it with Spektrafilm's existing `color_management.py` workflow and the GUI display pipeline requires careful mapping of colour space names.

---

## 3. ICC Profile v4 Creation & Embedding

### What We Found

**ICC v4 profiles** use the `scnr` (scene-referred) or `mntr` (monitor-referred) class tags and support floating-point PCS encoding. The key tools for Python ICC profile work:

1. **Little CMS (lcms2)** — The standard C library with Python bindings
   - `python-lcms2` or via Pillow's `ImageCms` module
   - Can create v4 profiles programmatically with `cmsCreateXYZProfile()`, `cmsCreate_sRGBProfile()`
   
2. **OpenImageIO** — Embeds ICC profiles via `ImageSpec.attribute("ICCProfile", bytes)`
   - Read: `spec.getattribute("ICCProfile")` returns raw bytes
   - Write: `spec.attribute("ICCProfile", icc_bytes)` before `out.open()`

3. **Pillow `ImageCms`** — Higher-level Python API for ICC profile creation
   - `ImageCms.createProfile('sRGB')` for simple profiles
   - Custom profiles via `ImageCms.buildTransform()`

**Key pattern for OIIO:**
```python
import OpenImageIO as oiio

# Write with ICC profile
spec = oiio.ImageSpec(width, height, channels, oiio.FLOAT)
with open("sRGB_v4.icc", "rb") as f:
    icc_bytes = f.read()
spec.attribute("ICCProfile", icc_bytes)
spec.attribute("oiio:ColorSpace", "sRGB")

out = oiio.ImageOutput.create("output.tif")
out.open("output.tif", spec)
out.write_image(pixels)
out.close()

# Read ICC profile
img = oiio.ImageInput.open("input.exr")
spec = img.spec()
icc = spec.getattribute("ICCProfile")  # bytes or None
color_space = spec.getattribute("oiio:ColorSpace")
```

### How It Applies to Spektrafilm

Spektrafilm already uses `OpenImageIO~=3.1.11` for image I/O. The ICC profile work maps to:

1. **ACEScg ICC profiles** — Need to create/embed a v4 ICC profile for ACEScg (the `scnr` class) when saving scene-referred outputs
2. **sRGB v4 profiles** — For display-referred output (currently using v2 implicitly)
3. **Display P3 profiles** — For HDR output targeting Apple displays

**Specific pattern for Spektrafilm:**
- Store ICC profile files as binary data in `spektrafilm/data/icc/`
- At save time, load the appropriate profile bytes and set via `spec.attribute("ICCProfile", ...)`
- For ACEScg, create a v4 `scnr` profile with D60 whitepoint and AP1 primaries

### Libraries & Versions

| Library | Version | Purpose |
|---|---|---|
| `OpenImageIO` | `~=3.1.11` (current) | ICC embedding in image files |
| `Pillow` | `~=12.1` (current) | `ImageCms` for profile creation |
| `lcms2` (system) | Latest | Underlying C library |

### Integration Complexity: **MEDIUM**
Creating custom ICC v4 profiles (especially ACEScg scene-referred) requires careful specification compliance. Embedding existing profiles via OIIO is trivial.

---

## 4. HDR Gain Map Encoding (ISO 21496)

### What We Found

**ISO 21496-1:2024** is the international standard for adaptive HDR gain map metadata. It defines how gain maps are embedded in image files for HDR rendering while maintaining SDR backward compatibility.

**Key implementations:**

1. **Google libultrahdr v1.4.0** — Open-source C/C++ library
   - Dual-licensed MIT/Apache-2.0
   - Supports: JPEG, HEIF, AVIF containers
   - Input formats: P010, RGBA1010102, RGBAF16, YUV420, RGBA8888
   - Color gamuts: BT.709, Display P3, BT.2100
   - Color transfers: Linear, HLG, PQ, sRGB
   - Encoding APIs: 5 variants depending on available inputs (HDR-only, HDR+SDR, HDR+SDR-compressed, etc.)
   - Decoding: Configurable display boost, multiple output formats

2. **Apple's approach** — Gain maps in HEIF/JPEG, supported since iPhone 12
3. **Adobe Ultra HDR** — Contributed to the standard, used in Lightroom/ACR

**libultrahdr encoding pattern:**
```c
// API-1: HDR raw + SDR raw → gain map JPEG
uhdr_encoder_t* encoder = uhdr_create_encoder();
uhdr_enc_set_raw_image(encoder, hdr_img, UHDR_HDR_IMG);
uhdr_enc_set_raw_image(encoder, sdr_img, UHDR_SDR_IMG);
uhdr_enc_set_quality(encoder, 90, UHDR_BASE_IMG);
uhdr_enc_set_quality(encoder, 85, UHDR_GAIN_MAP_IMG);
uhdr_encode(encoder);
uhdr_compressed_image_t* output = uhdr_get_encoded_stream(encoder);
```

**Gain map concept:** The gain map encodes the ratio between HDR and SDR renditions:
```
gain = log2(HDR_luminance / SDR_luminance)
```
Legacy viewers see the SDR base; HDR-capable viewers apply the gain map.

### How It Applies to Spektrafilm

Spektrafilm's HDR pipeline (`hdr_photo.py`, `controller.py`) already handles HDR preservation. Gain map encoding would:

1. **HDR JPEG output** — Generate gain map JPEGs that are backward-compatible SDR+HDR
2. **Profile integration** — Map Spektrafilm's `HDRPhotoMapping` to gain map metadata (min/max boost, gamma)
3. **SDR base + gain map** — Spektrafilm's `preserve_sdr_base=True` default aligns perfectly with the gain map model

**Integration approach:**
- Use `libultrahdr` via Python ctypes/CFFI bindings (no native Python package exists)
- Or: generate gain map mathematically in Python, write via OIIO with custom metadata
- The gain map metadata fields map to Spektrafilm's existing HDR profile fields

### Libraries & Versions

| Library | Version | Purpose |
|---|---|---|
| `libultrahdr` | `1.4.0` | Reference gain map encoder/decoder |
| Install | Build from source (CMake) | No pip package |
| Alternative | OIIO + custom metadata | Embed gain map as auxiliary image |

### Integration Complexity: **HIGH**
Requires C library integration (ctypes/CFFI) or reimplementing the gain map math in pure Python. The metadata format is well-specified but the encoding pipeline is non-trivial.

---

## 5. Vulkan Compute Shaders via Python

### What We Found

Vulkan compute shaders can be accessed from Python through several paths:

1. **wgpu-py** (recommended) — WebGPU API with Vulkan backend
   - See [Section 6](#6-webgpu--wgpu-py-image-processing) for details
   - Cross-platform: Windows, Linux (x86/aarch64), macOS
   
2. **Taichi** — High-level Python framework with Vulkan backend
   - `ti.init(arch=ti.vulkan)`
   - Automatic tiling, parallelization
   
3. **PyVulkan** — Low-level Vulkan API bindings
   - Full Vulkan control but very verbose
   - Requires SPIR-V shader compilation

4. **Numba CUDA** — Not Vulkan, but relevant for GPU compute patterns

**Typical Vulkan compute pipeline:**
```
Python → GLSL/SPIR-V shader → Vulkan Pipeline → GPU dispatch → Read back
```

### How It Applies to Spektrafilm

Spektrafilm already has a GPU backend abstraction (`ArrayBackend` protocol). Vulkan compute would be another backend option, but:

- **wgpu-py is the better entry point** (see Section 6)
- Vulkan compute shaders are most useful for **per-pixel operations** (tone mapping, colour transforms)
- Less useful for Spektrafilm's spectral simulation (which is matrix-heavy, better suited to CuPy/MLX)

### Libraries & Versions

| Library | Version | Purpose |
|---|---|---|
| `wgpu` | Latest | WebGPU/Vulkan from Python |
| `taichi` | Latest | High-level GPU compute |
| `vulkan` (PyPI) | Latest | Low-level bindings |

### Integration Complexity: **HIGH**
Custom shader writing required. Best approached through wgpu-py (Section 6) rather than raw Vulkan.

---

## 6. WebGPU / wgpu-py Image Processing

### What We Found

**wgpu-py** is a Python implementation of WebGPU, wrapping `wgpu-native` (Rust). It provides a modern, cross-platform GPU API that's the successor to OpenGL.

**Key features:**
- Complete WebGPU spec coverage
- WGSL shader language (WebGPU Shading Language)
- Compute shaders for image processing
- Sync and async APIs
- Works on Linux (x86/aarch64), macOS (Intel/M1), Windows
- Built on `wgpu-native` (Vulkan/Metal/DX12 backends)

**Installation:** `pip install wgpu`

**Compute shader example pattern:**
```python
import wgpu
from wgpu.gui.auto import WgpuCanvas

# Get adapter and device
adapter = wgpu.gpu.request_adapter(power_preference="high-performance")
device = adapter.request_device()

# Create compute shader
shader_code = """
@group(0) @binding(0) var<storage, read> input_data: array<f32>;
@group(0) @binding(1) var<storage, read_write> output_data: array<f32>;

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) id: vec3<u32>) {
    let i = id.x;
    output_data[i] = input_data[i] * 2.0;  // Example operation
}
"""

# Create pipeline
shader = device.create_shader_module(code=shader_code)
pipeline = device.create_compute_pipeline(
    layout="auto",
    compute={"module": shader, "entry_point": "main"}
)

# Create buffers
input_buffer = device.create_buffer_with_data(data=your_data, usage=wgpu.BufferUsage.STORAGE)
output_buffer = device.create_buffer(size=data_size, usage=wgpu.BufferUsage.STORAGE | wgpu.BufferUsage.COPY_SRC)

# Dispatch
bind_group = device.create_bind_group(layout=pipeline.get_bind_group_layout(0),
    entries=[
        {"binding": 0, "resource": {"buffer": input_buffer}},
        {"binding": 1, "resource": {"buffer": output_buffer}},
    ])

command_encoder = device.create_command_encoder()
compute_pass = command_encoder.begin_compute_pass()
compute_pass.set_pipeline(pipeline)
compute_pass.set_bind_group(0, bind_group)
compute_pass.dispatch_workgroups(num_elements // 64, 1, 1)
compute_pass.end()
device.queue.submit([command_encoder.finish()])

# Read back
result = device.queue.read_buffer(output_buffer)
```

### How It Applies to Spektrafilm

wgpu-py could serve as a **cross-platform GPU backend** alternative to CuPy (CUDA-only) and MLX (macOS-only):

1. **Uniform GPU backend** — One code path works on Linux+AMD, Linux+NVIDIA, macOS, Windows
2. **Image processing shaders** — Tone mapping, colour space conversion, HDR gain map application
3. **Complementary to CuPy/MLX** — Use for per-pixel operations; keep CuPy/MLX for matrix math

**Integration with ArrayBackend:**
```python
class WgpuBackend:
    name = "wgpu"
    supports_gpu = True
    
    def asarray(self, value, dtype=None):
        # Upload to GPU buffer
        ...
    
    def to_numpy(self, value):
        # Read back from GPU buffer
        ...
```

### Libraries & Versions

| Library | Version | Purpose |
|---|---|---|
| `wgpu` | Latest (0.x) | WebGPU Python bindings |
| `rendercanvas` | Latest | Optional: render to screen |
| Install | `pip install wgpu` | Also: `pip install wgpu rendercanvas glfw` |

### Integration Complexity: **MEDIUM-HIGH**
Requires writing WGSL shaders for each operation. The Python API is clean but the shader language is new. Best for a dedicated `WgpuBackend` class.

---

## 7. GPU Tiling for Large Image Processing

### What We Found

For images that exceed GPU memory, tiling strategies are essential:

### Strategy 1: CuPy + Overlapping Tiles
```python
import cupy as cp
import numpy as np

def process_tiled(image, tile_size=1024, overlap=64, process_fn=None):
    """Process a large image in overlapping GPU tiles."""
    h, w = image.shape[:2]
    result = np.zeros_like(image)
    weight = np.zeros((h, w, 1), dtype=np.float32)
    
    step = tile_size - overlap
    for y in range(0, h, step):
        for x in range(0, w, step):
            # Extract tile with bounds checking
            y_end = min(y + tile_size, h)
            x_end = min(x + tile_size, w)
            tile = image[y:y_end, x:x_end]
            
            # Upload, process, download
            gpu_tile = cp.asarray(tile)
            processed = process_fn(gpu_tile)
            cpu_result = cp.asnumpy(processed)
            
            # Blend overlapping regions with ramp weights
            ramp = _make_ramp(y_end - y, x_end - x, overlap)
            result[y:y_end, x:x_end] += cpu_result * ramp
            weight[y:y_end, x:x_end] += ramp
    
    return result / np.maximum(weight, 1e-8)

def _make_ramp(h, w, overlap):
    """Create a blending ramp for seamless tile stitching."""
    ramp = np.ones((h, w, 1), dtype=np.float32)
    if overlap > 0:
        # Fade in/out at edges
        fade = np.linspace(0, 1, overlap, dtype=np.float32)
        ramp[:overlap] *= fade[:, None, None]
        ramp[-overlap:] *= fade[::-1, None, None]
        ramp[:, :overlap] *= fade[None, :, None]
        ramp[:, -overlap:] *= fade[None, ::-1, None]
    return ramp
```

### Strategy 2: CuPy Memory Pool
```python
import cupy as cp

# Use memory pool to reduce allocation overhead
pool = cp.cuda.MemoryPool()
cp.cuda.set_allocator(pool.malloc)

# After processing, free unused memory
pool.free_all_blocks()
```

### Strategy 3: pyvips (Streaming)
```python
import pyvips

# Streaming access - never loads full image into RAM
image = pyvips.Image.new_from_file("huge.exr", access="sequential")
# Operations are streamed through with minimal memory
result = image.linear(2.0, 0.0)  # Example: multiply by 2
result.write_to_file("output.exr")
```

### Strategy 4: Generator-Based Tile Iteration
```python
def tile_generator(image, tile_size=512):
    """Memory-efficient tile iterator."""
    h, w = image.shape[:2]
    for y in range(0, h, tile_size):
        for x in range(0, w, tile_size):
            yield (y, x, image[y:y+tile_size, x:x+tile_size])
```

### Best Practices Summary

| Strategy | Benefit | When to Use |
|---|---|---|
| Overlapping tiles | Avoids seam artifacts | Any tile-based processing |
| `cp.cuda.MemoryPool` | Reuse GPU allocations | Repeated tile processing |
| Generators/lazy loading | Don't load all tiles at once | Very large images |
| Streaming I/O (pyvips) | Minimal RAM usage | Images larger than RAM |
| `numba.cuda` | Custom GPU tile kernels | Complex per-tile logic |

### How It Applies to Spektrafilm

Spektrafilm processes potentially large images (high-res scans, HDR). Tiling is needed when:

1. **GPU memory is limited** — Split 100MP+ images into manageable tiles
2. **Spectral processing** — Each tile can be processed independently for most operations
3. **The emulsion simulation** — Grain/diffusion models may need overlap for continuity

**Recommended approach:** Integrate tiling into `ArrayBackend` as a generic `process_tiled()` method that all backends can override. CuPy backend uses GPU tiles; NumPy backend uses CPU tiles with the same interface.

### Libraries & Versions

| Library | Version | Purpose |
|---|---|---|
| `cupy` | `>=13` (current optional dep) | GPU tile processing |
| `pyvips` | Optional | Streaming I/O for huge images |
| `numba` | `~=0.64` (current dep) | Custom CUDA kernels |

### Integration Complexity: **MEDIUM**
The tiling logic is straightforward; the hard part is handling edge cases (non-divisible image sizes, overlap blending, operations that need global context).

---

## 8. ACES Tone Mapping (Scene-Referred)

### What We Found

**ACES (Academy Color Encoding System)** provides standardized scene-referred to display-referred transforms.

### ACES Filmic Curve (Simplified)
```python
import numpy as np

def aces_filmic(x):
    """ACES filmic tone mapping curve (Narkowicz 2015)."""
    a = 2.51
    b = 0.03
    c = 2.43
    d = 0.59
    e = 0.14
    return np.clip((x * (a * x + b)) / (x * (c * x + d) + e), 0, 1)
```

### Full ACES Transform via colour-science
```python
import colour

# ACEScg (scene-referred) → sRGB (display-referred)
aces_rgb = np.array([0.5, 0.3, 0.1])

# Method 1: colour-science RGB_to_RGB
srgb = colour.RGB_to_RGB(aces_rgb, 'ACEScg', 'sRGB', apply_cctf_encoding=True)

# Method 2: Using ACES Output Transform
# colour-science has ACES RRT+ODT built in
srgb_output = colour.ACES_RID_to_sRGB(aces_rgb)  # if available in version

# Method 3: Custom matrix + tone curve
# AP1 to sRGB matrix
ap1_to_srgb = colour.matrix_RGB_to_RGB('ACEScg', 'sRGB')
linear_srgb = aces_rgb @ ap1_to_srgb.T
# Apply sRGB OETF
srgb_encoded = colour.cctf_encoding(linear_srgb, function='sRGB')
```

### Scene-Referred Workflow Pattern
```python
# Working in ACEScg (scene-referred, linear)
# 1. Load input → convert to ACEScg
input_srgb = load_image()  # sRGB encoded
linear_srgb = colour.cctf_decoding(input_srgb, function='sRGB')
acescg = colour.RGB_to_RGB(linear_srgb, 'sRGB', 'ACEScg')

# 2. Do all processing in ACEScg (linear, scene-referred)
processed = film_simulation(acescg)

# 3. Output transform: ACEScg → display
# For SDR output:
output_srgb = colour.RGB_to_RGB(processed, 'ACEScg', 'sRGB', apply_cctf_encoding=True)

# For HDR output (PQ):
output_pq = colour.RGB_to_RGB(processed, 'ACEScg', 'Display P3', apply_cctf_encoding=True)
# Then apply PQ EOTF...
```

### How It Applies to Spektrafilm

Spektrafilm already works in ACEScg (`ACES_WORKING_COLOR_SPACE = "ACEScg"`). The tone mapping path is:

1. **Internal processing** — All in ACEScg (linear, scene-referred) ✓ already done
2. **SDR output** — Need proper ACES Output Transform (RRT+ODT) for display
3. **HDR output** — Need ACES HDR Output Transform (different curve)
4. **Tone mapping for preview** — GUI needs real-time tone mapping for display

**Key insight:** The simplified ACES filmic curve is good enough for preview. For final output, use the full ACES transforms via colour-science or OCIO.

### Libraries & Versions

| Library | Version | Purpose |
|---|---|---|
| `colour-science` | `~=0.4.6` (current) | ACES transforms, colour spaces |
| `opencolorio` | `>=2.3` (optional) | Certified ACES output transforms |

### Integration Complexity: **LOW-MEDIUM**
Spektrafilm's ACEScg workflow is already in place. The work is in implementing proper output transforms (SDR and HDR) and preview tone mapping.

---

## 9. OpenImageIO HDR/EXR Metadata & Color Management

### What We Found

**OpenImageIO (OIIO) v3.x** provides comprehensive HDR/EXR support with Python bindings.

### Key Python API (from stubs):

```python
import OpenImageIO as oiio

# ImageSpec - metadata container
spec = oiio.ImageSpec(width, height, channels, oiio.FLOAT)
spec.alpha_channel = 3
spec.channelnames = ("R", "G", "B", "A")
spec.deep = False

# Color management attributes
spec.attribute("oiio:ColorSpace", "ACEScg")
spec.attribute("oiio:BitsPerSample", 32)

# EXR-specific metadata
spec.attribute("chromaticities", oiio.TypeDesc(oiio.TypeFloat, 4), chromaticities_array)
spec.attribute("whiteLuminance", 1.0)

# ICC profile embedding
spec.attribute("ICCProfile", icc_bytes)

# Reading
img = oiio.ImageInput.open("input.exr")
spec = img.spec()
pixels = img.read_image(oiio.FLOAT)
img.close()

# ColorConfig integration
config = oiio.ColorConfig()
color_spaces = config.getColorSpaceNames()
cs = config.getColorSpaceFromFilepath("image_sRGB.exr")
```

### OIIO + OCIO Integration
```python
import OpenImageIO as oiio

# OIIO has built-in OCIO support
print(oiio.supportsOpenColorIO)  # True if compiled with OCIO

config = oiio.ColorConfig.default_colorconfig()
# This loads the OCIO config automatically

# Get color space from filename patterns
cs = config.getColorSpaceFromFilepath("/path/to/acescg_render.exr")
```

### How It Applies to Spektrafilm

Spektrafilm already uses `OpenImageIO~=3.1.11`. Key improvements:

1. **EXR metadata** — Set `oiio:ColorSpace` to `"ACEScg"` when saving scene-referred EXR
2. **ICC embedding** — Add ICC profiles to all output formats (TIFF, PNG, JPEG)
3. **Chromaticities** — Write proper chromaticity tags for EXR files
4. **ColorConfig** — Use OIIO's color config for automatic color space detection
5. **HDR metadata** — Write HDR-specific metadata (max luminance, white point) for HDR outputs

**Specific code pattern for Spektrafilm's `save_image_oiio`:**
```python
def save_image_oiio_with_metadata(path, pixels, color_space="ACEScg", icc_profile=None):
    spec = oiio.ImageSpec(
        pixels.shape[1], pixels.shape[0], pixels.shape[2], oiio.FLOAT
    )
    spec.attribute("oiio:ColorSpace", color_space)
    
    if icc_profile is not None:
        with open(icc_profile, "rb") as f:
            spec.attribute("ICCProfile", f.read())
    
    if path.endswith(".exr"):
        # Set EXR chromaticities for ACEScg (AP1 primaries)
        chromaticities = get_ap1_chromaticities()
        spec.attribute("chromaticities", chromaticities)
    
    out = oiio.ImageOutput.create(path)
    out.open(path, spec)
    out.write_image(pixels.astype(np.float32))
    out.close()
```

### Libraries & Versions

| Library | Version | Purpose |
|---|---|---|
| `OpenImageIO` | `~=3.1.11` (current) | HDR I/O, metadata, color management |
| OCIO (via OIIO) | Compiled in | ColorConfig, automatic color space detection |

### Integration Complexity: **LOW**
OIIO is already integrated. The work is in adding proper metadata to save operations.

---

## 10. Array API Standard & Cross-Backend Interoperability

### What We Found

**The Array API Standard** (data-apis consortium) defines a common API for array libraries, enabling backend-agnostic code.

**Current status (2025):**
- **NumPy 2.x** — Supports Array API via `numpy.array_api` and improved dispatching
- **CuPy** — Strong adopter, Array API compliant
- **MLX** — Growing compatibility
- **PyTorch, JAX, Dask** — All supported via `array-api-compat`

**array-api-compat library:**
```python
# Small wrapper for cross-backend compatibility
# Supports: NumPy, CuPy, PyTorch, Dask, JAX, ndonnx, sparse
import array_api_compat as xp

# Works with any backend
x = xp.asarray([1, 2, 3])
y = xp.sum(x)
```

**Key design pattern:**
```python
# Backend-agnostic function
def process(x, xp=None):
    if xp is None:
        import numpy as xp
    return xp.exp(x) / xp.sum(xp.exp(x))  # softmax
```

### How It Applies to Spektrafilm

Spektrafilm's `ArrayBackend` protocol is **already aligned** with the Array API standard's philosophy. The key difference:

| Spektrafilm's ArrayBackend | Array API Standard |
|---|---|
| Protocol-based (duck typing) | Standard-based (conformance tests) |
| Custom method names (`matmul`, `einsum`) | Standard names (`matmul`, `einsum`) |
| Manual backend selection | `xp` module parameter pattern |
| NumPy, CuPy, MLX | NumPy, CuPy, PyTorch, JAX, Dask |

**Migration path (if desired):**
1. Replace `ArrayBackend` protocol with `array-api-compat` import pattern
2. Use `xp = array_api_compat.get_namespace(array)` to get the right backend
3. Write functions that accept `xp` parameter instead of `backend`

**However:** Spektrafilm's current approach is actually **more practical** because:
- It has explicit control over GPU memory (`.eval()`, `.synchronize()`)
- It handles backend-specific quirks (MLX's lazy evaluation, CuPy's memory pool)
- It doesn't need PyTorch/JAX (would add huge dependencies)

**Recommendation:** Keep Spektrafilm's `ArrayBackend` protocol. It's the right abstraction level. If needed, add a thin adapter to `array-api-compat` for interoperability with external libraries.

### Libraries & Versions

| Library | Version | Purpose |
|---|---|---|
| `array-api-compat` | Latest | Cross-backend compatibility layer |
| `numpy` | `>=2.0` (current) | Array API baseline |
| `cupy` | `>=13` (optional) | CUDA GPU arrays |
| `mlx` | `>=0.31` (optional) | Apple Silicon arrays |

### Integration Complexity: **LOW** (no change needed)
Spektrafilm's current abstraction is sound. Only adopt `array-api-compat` if integrating with libraries that require it (e.g., scikit-learn with GPU arrays).

---

## 11. Integration Recommendations for Spektrafilm

### Priority Matrix

| Priority | Item | Library | Complexity | Impact |
|---|---|---|---|---|
| **P0** | OIIO metadata on save | OpenImageIO (existing) | LOW | High — fixes C1, M4 |
| **P0** | ACEScg ICC profile embedding | OIIO + Pillow | MEDIUM | High — fixes H1 |
| **P1** | OCIO for ACES output transforms | opencolorio | MEDIUM | High — proper tone mapping |
| **P1** | Gain map HDR encoding | libultrahdr | HIGH | High — HDR JPEG output |
| **P2** | GPU tiling for large images | CuPy (existing) | MEDIUM | Medium — memory efficiency |
| **P2** | wgpu-py backend | wgpu | MEDIUM-HIGH | Medium — cross-platform GPU |
| **P3** | ACES HDR output transform | colour-science/OCIO | LOW | Medium — HDR display output |
| **P3** | array-api-compat bridge | array-api-compat | LOW | Low — future interop |

### Recommended Implementation Order

1. **Phase 1: Metadata & Color Management** (P0 items)
   - Add `oiio:ColorSpace` to all save operations
   - Create ACEScg ICC v4 profile and embed in outputs
   - Add chromaticities to EXR saves
   
2. **Phase 2: OCIO Integration** (P1 items)
   - Add `opencolorio` as optional dependency
   - Implement ACES Output Transforms via OCIO processors
   - Replace manual tone mapping with OCIO transforms

3. **Phase 3: HDR Output** (P1 items)
   - Integrate libultrahdr for gain map JPEG
   - Map Spektrafilm's HDR profile fields to gain map metadata
   - Support HDR output in JPEG, HEIF, AVIF

4. **Phase 4: GPU Optimization** (P2 items)
   - Add tiling to `ArrayBackend` for large images
   - Evaluate wgpu-py as cross-platform GPU alternative

### Key Technical Decisions Needed

1. **OCIO vs colour-science for ACES transforms?**
   - OCIO: Certified, config-driven, industry-standard
   - colour-science: Already integrated, pure Python, no new dependency
   - **Recommendation:** OCIO for output transforms, colour-science for internal use

2. **libultrahdr integration method?**
   - ctypes/CFFI bindings to C library
   - Pure Python reimplementation of gain map math
   - **Recommendation:** Start with pure Python (simpler), optimize to C if needed

3. **wgpu-py vs CuPy for GPU backend?**
   - CuPy: Already integrated, CUDA-only, mature
   - wgpu-py: Cross-platform (Vulkan/Metal/DX12), newer, compute shaders
   - **Recommendation:** Keep CuPy as primary, add wgpu-py as alternative for non-CUDA systems

---

## Appendix A: Library Version Compatibility Matrix

| Library | Spektrafilm Current | Latest | Python | Notes |
|---|---|---|---|---|
| colour-science | ~=0.4.6 | 0.4.7 | 3.11-3.14 | NumPy 2.x required |
| OpenImageIO | ~=3.1.11 | 3.x | 3.11+ | Compiled with OCIO |
| opencolorio | (not dep) | 2.3+ | 3.11-3.13 | pip installable |
| numpy | ~=2.4 | 2.x | 3.13+ | Array API baseline |
| cupy | >=13 (optional) | 13.x | 3.11+ | CUDA 12.x |
| mlx | >=0.31 (optional) | 0.31+ | 3.13+ | macOS only |
| wgpu | (not dep) | 0.x | 3.10+ | Cross-platform GPU |
| libultrahdr | (not dep) | 1.4.0 | N/A (C) | Build from source |
| numba | ~=0.64 | 0.64+ | 3.13+ | CUDA JIT |
| Pillow | ~=12.1 | 12.x | 3.13+ | ImageCms for ICC |

## Appendix B: Key URLs & Resources

- colour-science: https://github.com/colour-science/colour
- OCIO: https://github.com/AcademySoftwareFoundation/OpenColorIO
- OIIO: https://github.com/AcademySoftwareFoundation/openimageio
- libultrahdr: https://github.com/Google/libultrahdr
- wgpu-py: https://github.com/pygfx/wgpu-py
- Array API Standard: https://github.com/data-apis/array-api
- array-api-compat: https://github.com/data-apis/array-api-compat
- ISO 21496-1:2024 (gain map standard): https://www.iso.org/standard/81524.html
- ACES Central: https://acescentral.com/
- OCIO Built-in Configs: https://opencolorio.readthedocs.io/en/latest/guides/using_ocio/using_ocio.html
