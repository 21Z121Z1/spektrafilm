> This is an English translation of the Chinese original. For the authoritative version, see the Chinese original.

# Gain Map HDR Image Generation -- ISO Standard Analysis and Spektrafilm Integration Plan

> Date: 2026-05-27
> Analysis based on: ISO 21496-1:2025, ISO/IEC 23008-12:2025/Amd.1:2025, ISO/IEC 23008-12:2025

---

## 1. ISO Standard Core Summary

### 1.1 ISO 21496-1 Gain Map Algorithm

#### 1.1.1 Core Concepts

A Gain Map is an efficient scheme for storing both an SDR base image and an HDR alternate image in a single file. By storing the base image along with a "local quotient" data structure (the gain map), it performs conversion between two dynamic range representations, avoiding the redundancy of storing two complete images.

Core terminology definitions (ISO 21496-1 Chapter 3):

- **Baseline Image**: The primary image stored in the file, typically the SDR representation
- **Alternate Image**: The image obtained by merging the baseline image and the gain map, typically the HDR representation
- **Gain Map Application Space**: The linear RGB color space in which the gain map is applied, scaled so that the R/G/B values of the HDR reference white are all 1.0
- **HDR Headroom**: The ratio of nominal peak luminance to HDR reference white luminance, expressed in log2. For example, if HDR reference white is 203 nits and peak is 1624 nits, headroom = log2(1624/203) = 3 stops

#### 1.1.2 Gain Map Computation Formula (A.1)

The core formula for computing a gain map from two image representations (Annex A.2):

```
G = sign(H_alternate - H_baseline) × log2((Alternate + k_alternate) / (Baseline + k_baseline))
```

Where:
- `G`: The gain map color component expressed in log2
- `H_alternate`, `H_baseline`: The HDR headroom of the alternate/baseline image
- `k_alternate`, `k_baseline`: Per-component offset constants used to avoid numerical issues (such as division by zero)
- The sign function ensures the gain map direction is consistent with the HDR headroom difference direction

**Physical meaning**: Due to the use of log2 encoding, gain map values have an intuitive photographic meaning -- they approximately represent the difference in aperture stops (stops/EV) between the two representations. A value of 0 means the two representations are the same; a value of +1 means the alternate representation is approximately 1 stop brighter than the baseline.

#### 1.1.3 Gain Map Application Formula (2)

In the linear RGB gain map application space, applying the gain map to the baseline image to obtain the alternate image:

```
Alternate = (Baseline + k_baseline) × 2^(W × G) - k_alternate
```

Where `W` is a weight factor used to scale the gain map to the target HDR headroom value `H_target`.

#### 1.1.4 Weight Factor Formula (3)

```
W = sign(H_alternate - H_baseline) × clamp((H_target - H_baseline) / (H_alternate - H_baseline), 0, 1)
```

The weight factor enables continuous scaling within the `[H_baseline, H_alternate]` range, allowing displays to adapt the display effect based on their own HDR capabilities.

#### 1.1.5 Gain Map Preprocessing Pipeline

1. **Compute raw gain map** (A.2): `G = sign(...) × log2((Alternate + k_alt) / (Baseline + k_base))`
2. **Optional resampling** (A.3.2): Reduce gain map resolution to decrease file size
3. **Normalization** (A.3.3): `G_normalized = (G - min(G)) / (max(G) - min(G))`
4. **Gamma encoding** (A.3.4): `G_normalized_gamma = G_normalized ^ γ`

#### 1.1.6 Gain Map Denormalization Formula (1)

Decoder-side denormalization:

```
G = [max(G) - min(G)] × (G_normalized_gamma)^(1/γ) + min(G)
```

#### 1.1.7 Gain Map Requirements (Chapter 4)

- **Dimensions** (4.2): Shall be the same dimensions as the baseline image; down-sampling is permitted (e.g., 1/2 width and height)
- **Color components** (4.3): 3 RGB components (highest precision) or 1 achromatic component
- **Quantization** (4.4): At least 8 bits per component
- **Orientation** (4.5): Consistent with the baseline image

### 1.2 Metadata Structure

#### 1.2.1 Per-Component Metadata (5.2.5)

Each color component carries the following metadata:
- `min(G)`: Minimum value of the gain map in log space
- `max(G)`: Maximum value of the gain map in log space
- `k_baseline`: Baseline offset constant
- `k_alternate`: Alternate offset constant
- `γ`: Gamma value (for pre-compression)

#### 1.2.2 HDR Headroom Metadata

- `H_baseline`: HDR headroom of the baseline image (when gain map is not applied)
- `H_alternate`: HDR headroom of the alternate image (when gain map is fully applied); shall not be equal to `H_baseline`

#### 1.2.3 Color Metadata (5.3)

- Baseline image color space (ICC Profile or CICP metadata)
- Alternate image color space
- Gain map application space primaries indication (using baseline or alternate image primaries)

#### 1.2.4 GainMapMetadata Binary Payload (C.2)

Big-endian binary structure:

```
struct GainMapChannel {          // 40 bytes per channel
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
    GainMapVersion version;              // 4 bytes
    // when minimum_version == 0:
    unsigned int(1) is_multichannel;     // 1=3 channels, 0=1 channel
    unsigned int(1) use_base_colour_space; // 1=baseline image primaries, 0=alternate image primaries
    unsigned int(6) reserved;
    unsigned int(32) base_hdr_headroom_numerator;
    unsigned int(32) base_hdr_headroom_denominator;
    unsigned int(32) alternate_hdr_headroom_numerator;
    unsigned int(32) alternate_hdr_headroom_denominator;
    GainMapChannel channels[channel_count]; // channel_count = (is_multichannel)*2 + 1
}
```

All values are stored as rational numbers (numerator/denominator); the denominator shall not be 0.

### 1.3 HEIF tmap Derived Image Item

#### 1.3.1 Container Encapsulation Method (ISO/IEC 23008-12:2025/Amd.1 Section 6.6.2.4)

The encapsulation of a `'tmap'` type derived image item in a HEIF container:

- **Item type**: `item_type = 'tmap'`
- **Input references**: Two input items connected via a `SingleItemTypeReferenceBox` of type `'dimg'`
  - First: base image item
  - Second: gain map image item
- **ToneMapImage data structure**:

```
aligned(8) class ToneMapImage {
    unsigned int(8) version = 0;
    if (version == 0) {
        bit(8) gain_map_metadata[];  // ISO 21496-1 GainMapMetadata binary payload
    }
}
```

#### 1.3.2 Color Property Requirements

- **Base image item**: Must be associated with a `'colr'` item property (corresponding to ISO 21496-1 baseline image color metadata)
- **Gain map image item**: Must be associated with a `'colr'` item property of type `'nclx'`, with `colour_primaries` and `transfer_characteristics` set to 2
- **tmap derived image item**: Must be associated with a `'colr'` item property (corresponding to alternate image color metadata)
- The gain map input item should be marked as hidden (`(flags & 1) == 1`)

#### 1.3.3 Backward Compatibility

The tmap derived item and base item are grouped together via an `'altr'` entity group; parsers that do not support tmap will ignore the derived item and display the base image.

#### 1.3.4 File Brand

A file containing a tmap derived item shall include the `'tmap'` brand in the `compatible_brands` of the `FileTypeBox`.

### 1.4 JPEG Container Encapsulation (ISO 21496-1 Annex C.4)

JPEG uses CIPA DC-007 Multi-Picture Format (MPF) to store gain maps:

- **Base image**: An MPF-compliant base image (first image)
- **Gain map image**: Stored as an MPF additional image
- **Metadata**: Stored via APP2 segments, with URN `urn:iso:std:iso:ts:21496:-1` (28 bytes)
  - The APP2 segment of the base image contains the `GainMapVersion` structure
  - The APP2 segment of the gain map image contains the complete `GainMapMetadata` structure
- **Alternate image color space**: Described by the ICC Profile of the gain map image

### 1.5 Color Space Conversion Requirements (Annex B)

The gain map operates in the linear RGB gain map application space. When the baseline and alternate images are encoded in different color spaces:

1. Convert to gain map application space: Convert baseline image pixels to linear RGB
2. Apply gain map
3. Convert to alternate color space
4. If the alternate gamut is smaller than the baseline gamut, gamut mapping is required

The primaries of the gain map application space are indicated by the `use_base_colour_space` metadata.

---

## 2. Relevance Analysis for Spektrafilm

### 2.1 Directly Related Modules

#### 2.1.1 `src/spektrafilm/utils/hdr_photo.py` -- Core HDR Pipeline

This is the module most directly related to gain map generation. Existing functionality includes:

- **`HDRPhotoMapping`** (lines 55-233): A complete HDR mapping parameter data class, containing:
  - `gain_map_mode: Literal["luma", "rgb"]` -- already supports single-channel/three-channel gain map selection
  - `preserve_sdr_base: bool = True` -- SDR base preservation mode
  - Paper rolloff parameters (logistic/logarithmic modes)
  - Diffuse lift parameters
  - Profile-preserving HDR curve parameters
  - Color recovery and gamut mapping parameters

- **`ISO21496GainMapMetadata`** (lines 1157-1172): Existing ISO 21496-1 metadata structure, but with simplified field names (`gain_map_min`/`gain_map_max` instead of numerator/denominator rational form)

- **`build_iso_21496_1_gain_map_metadata()`** (lines 1175-1214): Builds metadata from HDR renditions

- **`encode_gain_map_log2()`** (lines 1217-1255): Computes `log2(hdr_luma / sdr_luma)` and normalizes to [0, 1]

- **`build_gain_map_xmp_packet()`** (lines 1258-1307): Generates XMP metadata packet (using Adobe `hdrgm` namespace)

- **`validate_gain_map()`** (lines 1310-1341): Gain map validation

- **`save_hdr_photo_heic()`** (lines 262-332): HEIC export -- **currently only supports macOS CoreImage**

- **`prepare_hdr_photo_renditions()`** (lines 471-482): Core entry point for generating SDR/HDR renditions

- **`HDRPhotoRenditions`** (lines 236-241): Output data class containing `hdr_rgb`, `sdr_rgb`, `headroom`

#### 2.1.2 `src/spektrafilm/utils/io.py` -- Image I/O

- **`save_image_oiio()`** (lines 531-755): General-purpose image saving function, already supports EXR hdr_rendition mode
- **`save_hdr_rendition_exr()`** (lines 758-820): HDR rendition EXR save convenience function
- **ICC Profile management** (lines 171-258): Complete ICC Profile mapping and loading system
- HEIC/HEIF extension detection delegates to `hdr_photo.py` via `is_hdr_photo_extension()`

#### 2.1.3 `src/spektrafilm/utils/hdr_curve_profiles.py` -- HDR Curve Profiles

- **`FilmPrintHDRCurveProfile`**: Film/photographic paper HDR curve profile
- **`build_profile_preserving_hdr_curve()`** (lines 892-1050): Profile-preserving HDR curve construction
- **`profile_modern_recovery_budgeted_gain_ev()`**: Modern recovery gain calculation with EV budget
- **`budget_recovery_gain_ev()`** (lines 600-722): EV budget constraint system

#### 2.1.4 `src/spektrafilm/color_management.py` -- Color Management

- **`ColorEncoding`**: Color encoding data class (color space, transfer function, role)
- Supports sRGB, Display P3, DCI-P3, Adobe RGB, BT.2020, ProPhoto RGB, ACES2065-1, ACEScg
- ACES workflow presets

#### 2.1.5 `src/spektrafilm/gpu/kernels/color.py` -- GPU Color Kernels

- `precompute_rgb_to_xyz_matrix()` / `precompute_xyz_to_rgb_matrix()`: Color space conversion matrix precomputation
- `cctf_decoding_transfer_backend()` / `cctf_encoding_backend()`: Backend-agnostic CCTF encode/decode
- Supports sRGB, Display P3, ProPhoto RGB, BT.2020, Adobe RGB, DCI-P3

### 2.2 Gaps Between Existing HDR Pipeline and ISO Standard

| Aspect | Spektrafilm Current State | ISO 21496-1 Requirement | Gap |
|--------|--------------------------|------------------------|-----|
| **Gain map computation** | `encode_gain_map_log2()` uses luminance ratio `log2(hdr_luma/sdr_luma)` | Formula A.1: `sign(...) × log2((Alt+k_alt)/(Base+k_base))`, per-channel with offsets | Existing implementation is single-channel luminance mode, lacks per-channel RGB mode and offset constant support |
| **Metadata format** | XMP `hdrgm` namespace (Adobe format) | `GainMapMetadata` binary payload (big-endian rational number structure) | Completely different encoding format; binary serialization needs to be implemented |
| **Metadata fields** | `ISO21496GainMapMetadata` simplified float fields | Numerator/denominator rational pairs + `is_multichannel` + `use_base_colour_space` | Missing rational number encoding and primaries space indication |
| **Container encapsulation** | macOS CoreImage Swift script (platform-dependent) | JPEG MPF APP2 / HEIF tmap derived item | Cross-platform MPF and HEIF encapsulation implementation needed |
| **HEIC export** | macOS only, via Swift/CoreImage | Standard HEIF tmap derived item | Cross-platform solution based on libheif or similar library needed |
| **Color space handling** | Operates in a single working space | Annex B: baseline/alternate may use different color spaces, primaries conversion required | Gain map application space primaries conversion logic needed |
| **Weight factor** | None (fixed headroom) | Formula (3): Continuous scaling based on H_target | W weight factor computation needs to be implemented |

### 2.3 New Modules/Functions Required

1. **`GainMapMetadataBinaryEncoder`**: Encode gain map parameters into ISO 21496-1 C.2 big-endian binary payload
2. **`GainMapMetadataBinaryDecoder`**: Parse binary payload to recover parameters
3. **`compute_gain_map_iso21496()`**: Implement per-channel gain map computation per formula A.1 (with offset constants and sign function)
4. **`normalize_gain_map()`**: Implement normalization + gamma encoding per formulas A.2 and A.3
5. **`apply_gain_map()`**: Implement gain map application per formulas (2) and (3) (with weight factor)
6. **`JPEGMPFGainMapWriter`**: JPEG MPF APP2 gain map encapsulator
7. **`HEIFTmapWriter`**: HEIF tmap derived item encapsulator (based on pyheif/libheif)
8. **Gain map application space primaries conversion**: Primaries conversion pipeline when baseline/alternate color spaces differ
9. **`save_gain_map_jpeg()`**: JPEG gain map export entry function
10. **`save_gain_map_heif()`**: HEIF gain map export entry function

---

## 3. Technical Design for Gain Map Generation

### 3.1 Gain Map Computation (Based on ISO 21496-1 Annex A)

#### 3.1.1 Computing Gain Map from SDR+HDR Representations

```python
def compute_gain_map_iso21496(
    baseline: np.ndarray,      # Linear SDR baseline image (H, W, 3)
    alternate: np.ndarray,     # Linear HDR alternate image (H, W, 3)
    *,
    k_baseline: float = 1/1023,    # Baseline offset constant
    k_alternate: float = 1/1023,   # Alternate offset constant
    h_baseline: float = 0.0,       # Baseline HDR headroom (SDR = 0)
    h_alternate: float = 3.0,      # Alternate HDR headroom
) -> np.ndarray:
    """Formula A.1: Compute per-channel log2 gain map"""
    sign = np.sign(h_alternate - h_baseline)  # +1 or -1
    ratio = (alternate + k_alternate) / (baseline + k_baseline)
    gain = sign * np.log2(np.maximum(ratio, 1e-8))
    return gain.astype(np.float32)
```

#### 3.1.2 Normalization and Gamma Encoding

```python
def normalize_gain_map(
    gain: np.ndarray,          # Raw log2 gain map (H, W, 3) or (H, W)
    gamma: float = 1.0,        # Gamma value
) -> tuple[np.ndarray, float, float]:
    """Formula A.2 + A.3: Normalization and gamma encoding"""
    g_min = float(np.min(gain))
    g_max = float(np.max(gain))
    if g_max - g_min < 1e-8:
        normalized = np.zeros_like(gain)
    else:
        normalized = (gain - g_min) / (g_max - g_min)
    normalized_gamma = np.power(np.clip(normalized, 0, 1), gamma)
    return normalized_gamma.astype(np.float32), g_min, g_max
```

#### 3.1.3 Gain Map Application (Decoder Side)

```python
def apply_gain_map(
    baseline: np.ndarray,      # Linear baseline image (H, W, 3)
    gain_map: np.ndarray,      # Normalized gain map (H, W, 3) or (H, W)
    *,
    g_min: float, g_max: float,
    gamma: float = 1.0,
    k_baseline: float = 1/1023,
    k_alternate: float = 1/1023,
    h_baseline: float = 0.0,
    h_alternate: float = 3.0,
    h_target: float | None = None,
) -> np.ndarray:
    """Formula (1) + (2) + (3): Apply gain map"""
    # Denormalization -- formula (1)
    g = (g_max - g_min) * np.power(gain_map, 1.0 / gamma) + g_min

    # Weight factor -- formula (3)
    if h_target is None:
        h_target = h_alternate
    sign = np.sign(h_alternate - h_baseline)
    w = sign * np.clip(
        (h_target - h_baseline) / max(h_alternate - h_baseline, 1e-8), 0, 1
    )

    # Apply gain map -- formula (2)
    alternate = (baseline + k_baseline) * np.power(2.0, w * g) - k_alternate
    return np.clip(alternate, 0, None).astype(np.float32)
```

### 3.2 Metadata Encoding Scheme

#### 3.2.1 GainMapMetadata Binary Serialization

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
    """Encode ISO 21496-1 C.2 GainMapMetadata binary payload"""
    buf = bytearray()

    # GainMapVersion
    buf += struct.pack(">HH", 0, 0)  # minimum_version=0, writer_version=0

    # Flags byte
    flags = (int(is_multichannel) << 7) | (int(use_base_colour_space) << 6)
    buf += struct.pack(">B", flags)

    # HDR headroom (rational numbers)
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
    """Encode a float as an int32/uint32 rational number pair"""
    if value == 0:
        return struct.pack(">iI", 0, 1)
    # Use 1/10000 precision
    numerator = int(round(value * 10000))
    return struct.pack(">iI", numerator, 10000)

def _encode_unsigned_rational(value: float) -> bytes:
    numerator = max(1, int(round(value * 10000)))
    return struct.pack(">II", numerator, 10000)
```

#### 3.2.2 Compatibility Between Existing XMP and ISO Binary Schemes

The current `build_gain_map_xmp_packet()` uses the Adobe `hdrgm` XMP namespace, which is the format used by Google/Apple gain map implementations. ISO 21496-1 uses binary payloads. Both schemes should coexist:

- **XMP scheme**: For Google Ultra HDR compatible format in JPEG
- **Binary scheme**: For HEIF tmap derived items and strict ISO compliance scenarios

### 3.3 JPEG/HEIF Container Encapsulation Scheme

#### 3.3.1 JPEG MPF Encapsulation

JPEG gain map encapsulation is based on CIPA DC-007 Multi-Picture Format:

1. Main image (SDR base): Standard JPEG
2. Additional image (gain map): JPEG-compressed 8-bit gain map
3. APP2 segment: URN `urn:iso:std:iso:ts:21496:-1` + GainMapMetadata binary payload

Implementation plan:
- Use the `struct` module to manually construct the MPF APP2 segment
- Quantize gain map to 8-bit JPEG (aligned with standard C.4.1)
- The APP2 segment of the base image contains only `GainMapVersion` (4 bytes)
- The APP2 segment of the gain map image contains the complete `GainMapMetadata`

#### 3.3.2 HEIF tmap Encapsulation

HEIF encapsulation requires constructing the following Box structure:

```
FileTypeBox: major_brand='heic', compatible_brands=['tmap', 'mif1', 'heic']
MetaBox:
  ItemInfoBox:
    - Base image item (e.g. hvc1)
    - Gain map image item (Hidden, hvc1/avc1)
    - tmap derived image item
  ItemReferenceBox:
    - tmap → dimg → [base image, gain map image]
  ItemPropertyBox:
    - colr (nclx) for base image
    - colr (nclx) for gain map (primaries=2, transfer=2)
    - colr for tmap (alternate image color space)
  ItemLocationBox
ItemDataBox:
  ToneMapImage payload (version + GainMapMetadata)
MediaDataBox:
  Encoded image data
```

It is recommended to use `pyheif` or directly call the `libheif` C API for HEIF container operations.

### 3.4 Color Space Conversion Pipeline

#### 3.4.1 Gain Map Application Space

The gain map operates in a linear RGB space, scaled so that HDR reference white = 1.0. Pipeline flow:

```
[Input: baseline image encoding space] → CCTF decode → linear RGB → primaries conversion (if needed) → gain map application space
    → apply gain map → primaries conversion (if needed) → alternate image encoding space → CCTF encode → [Output]
```

#### 3.4.2 Spektrafilm Existing Color Space Support

CCTF encode/decode already supported in `gpu/kernels/color.py`:
- sRGB / Display P3 (sRGB-like EOTF)
- ProPhoto RGB (ROMM RGB EOTF)
- ITU-R BT.2020 (BT.1886 EOTF)
- Adobe RGB (1998) (gamma 2.2)
- DCI-P3 (gamma 2.6)
- ACES2065-1 / ACEScg (linear passthrough)

These already cover the major color space conversions required by ISO 21496-1 Annex B. What needs to be added is the primaries selection logic for the gain map application space (`use_base_colour_space` flag).

---

## 4. GPU Acceleration Feasibility

### 4.1 Steps Suitable for GPU Acceleration

| Step | Operation | GPU Feasibility | Notes |
|------|-----------|----------------|-------|
| Gain map computation (A.1) | `log2((Alt+k_alt)/(Base+k_base))` | High | Per-pixel independent operation, perfectly parallel |
| Normalization (A.2) | `(G - min) / (max - min)` | High | `min`/`max` require reduction, then broadcast |
| Gamma encoding (A.3) | `G_normalized ^ γ` | High | Per-pixel `pow` operation |
| Resampling | Bilinear/bicubic interpolation | Medium | Requires texture sampling or shared memory |
| Gain map application (2) | `(Base+k) × 2^(W×G) - k_alt` | High | Per-pixel `pow2` + multiplication |
| Weight factor (3) | `sign × clamp(...)` | High | Scalar computation, result broadcast |
| Color space conversion | Matrix multiplication + CCTF | High | Already implemented in `color.py` |
| Gamut mapping | Oklch bisection search | Medium | 16 iterations, each requiring full-image operation |

### 4.2 Integration Points with the ArrayBackend Architecture

The existing `ArrayBackend` protocol (`gpu/backend.py`) operations already cover gain map computation requirements:

- `exp(x)` / `pow(x, exp)` -- for `2^(W×G)` and gamma encoding
- `maximum(x, y)` / `clip(x, lo, hi)` -- for clamping and non-negative guarantees
- `log10(x)` -- can be extended to `log2` (`log2(x) = log10(x) / log10(2)`)
- `where(condition, x, y)` -- for conditional branching
- `abs(x)` -- for the sign function

**New Backend method required**:

```python
def log2(self, x: Any) -> Any: ...
```

CuPy implementation: `self.cp.log2(x)`
MLX implementation: `mx.log2(x)`
NumPy implementation: `np.log2(x)`

### 4.3 Precision Requirements

Per the CLAUDE.md GPU precision constraints (`atol=1e-6`):

- Gain map computation uses float32 -- `log2` and `pow2` have sufficient precision in float32
- Normalization `min`/`max` reduction must ensure consistency with CPU (using the same reduction strategy)
- Gamma encoding `pow(x, γ)` has good precision in float32
- Color space matrix multiplication already has a float32 implementation and has been verified

**Recommendation**: Gain map computation throughout uses float32, with precision conversion only at the final 8-bit quantization stage.

---

## 5. Implementation Roadmap

### Phase 1: Core Gain Map Computation Engine (Estimated 3-5 days)

**Goal**: Implement the gain map computation and application algorithms from ISO 21496-1 Annex A

1. Add `compute_gain_map_iso21496()` function (formula A.1)
2. Add `normalize_gain_map()` function (formula A.2 + A.3)
3. Add `apply_gain_map()` function (formula (1) + (2) + (3))
4. Extend `HDRPhotoRenditions` to carry per-channel gain map data
5. Refactor `encode_gain_map_log2()` to support per-channel RGB mode
6. Add corresponding unit tests (CPU-side, verifying formula correctness)

**Key file**: `src/spektrafilm/utils/hdr_photo.py`

### Phase 2: Metadata Encoding and Container Encapsulation (Estimated 5-7 days)

**Goal**: Implement GainMapMetadata binary encoding and JPEG/HEIF container writing

1. Implement `GainMapMetadata` binary serialization/deserialization (C.2 structure)
2. Implement JPEG MPF APP2 encapsulation (C.4 specification)
3. Integrate `pyheif`/`libheif` for HEIF tmap derived item encapsulation
4. Add `save_gain_map_jpeg()` entry function
5. Add `save_gain_map_heif()` entry function (cross-platform replacement for macOS CoreImage)
6. Add round-trip tests for XMP and binary metadata

**Key file**: New file `src/spektrafilm/utils/gain_map_io.py`, modification to `hdr_photo.py`

### Phase 3: GPU Acceleration Optimization (Estimated 2-3 days)

**Goal**: Integrate gain map computation into the ArrayBackend architecture

1. Add `log2()` method to the `ArrayBackend` protocol
2. Implement `log2()` in `NumpyBackend`, `CupyBackend`, and `MlxBackend`
3. Implement GPU-side gain map computation kernel (`gpu/kernels/gain_map.py`)
4. Use `tiled_processing()` for large images
5. Add GPU vs CPU precision comparison tests (`atol=1e-6`)

**Key files**: `gpu/backend.py`, `gpu/kernels/`, `gpu/cupy_backend.py`, `gpu/mlx_backend.py`

### Phase 4: Testing and Verification (Estimated 2-3 days)

**Goal**: Comprehensive testing and standards compliance verification

1. Unit tests: Round-trip consistency of gain map computation/application
2. Metadata encoding tests: Binary payload serialization/deserialization
3. Container encapsulation tests: Generated JPEG/HEIF files can be read by standard parsers
4. Color space tests: Different baseline/alternate color space combinations
5. GPU precision tests: CPU vs GPU output comparison
6. End-to-end tests: Complete pipeline from scene-linear input to gain map HEIC output

### Effort Estimate

| Phase | Effort | Dependencies |
|-------|--------|--------------|
| Phase 1: Core algorithm | 3-5 days | None |
| Phase 2: Metadata and encapsulation | 5-7 days | Phase 1 |
| Phase 3: GPU acceleration | 2-3 days | Phase 1 |
| Phase 4: Testing and verification | 2-3 days | Phase 1-3 |
| **Total** | **12-18 days** | |

---

## 6. Risks and Dependencies

### 6.1 OpenImageIO Support for HEIF Gain Map

**Risk**: OpenImageIO (Spektrafilm's primary I/O library) has limited support for HEIF gain maps.

- OIIO supports basic HEIF read/write (via `libheif`) but does not directly expose a tmap derived item API
- OIIO's `ImageSpec` property system does not include native support for `GainMapMetadata`
- HEIF container structure operations require the `libheif` Python bindings (`pyheif`) or direct C API

**Mitigation strategy**:
- Use `pyheif` as the primary dependency for HEIF container operations
- Keep OIIO for base image read/write; implement gain map encapsulation on top of OIIO
- Consider using `pillow-heif` as a fallback (already supports basic gain map writing)

### 6.2 Applicability of the colour-science Library

**Current state**: Spektrafilm has deeply integrated the `colour-science` library (used for RGB color space definitions, CCTF encode/decode, matrix calculations, etc.).

**Applicability analysis**:
- Color space matrices: `colour.RGB_COLOURSPACES` already covers all required color spaces
- CCTF encode/decode: `colour.RGB_to_RGB()` provides standard transfer functions
- Colorimetric calculations: Functions like `colour.xy_to_XYZ()` can be used for primaries conversion
- **Not applicable**: `colour-science` does not contain gain-map-specific functionality; it must be implemented independently

**Risk**: Low. Existing integration has been verified as stable; gain map computation is primarily mathematical operations and does not depend on additional color science functionality.

### 6.3 Standards Compliance Verification Strategy

1. **Formula verification**:
   - Use reference values from ISO 21496-1 Annex A for unit testing
   - Verify gain map round-trip consistency: `compute -> normalize -> denormalize -> apply ≈ original`

2. **Binary payload verification**:
   - Manually construct known binary sequences and verify parsing results
   - Cross-validate with Google's `libultrahdr` reference implementation

3. **Container compliance verification**:
   - Verify JPEG MPF structure with `exiftool`
   - Verify HEIF tmap structure with `heif-info` (libheif tool)
   - Verify HEIC gain map rendering with Apple devices (if available)

4. **Interoperability testing**:
   - Google Photos / Android rendering of JPEG gain maps
   - Apple Photos rendering of HEIC gain maps
   - Adobe Lightroom reading of both formats

### 6.4 Other Risks

| Risk | Impact | Mitigation Strategy |
|------|--------|---------------------|
| `pyheif` installation depends on `libheif` C library | Increased deployment complexity | Provide conda/pip installation documentation; consider `pillow-heif` as fallback |
| JPEG MPF not recognized in older software | Older viewers only display the SDR base image | This is the standard-designed backward-compatible behavior; acceptable |
| macOS CoreImage HEIC output does not conform to ISO 21496-1 binary format | Existing HEIC output needs migration | Implement standard format in Phase 2; retain CoreImage as macOS fallback |
| Per-channel RGB gain map size is 3x that of luminance mode | JPEG file size increases | Support downsampling (1/2 or 1/4 resolution); use configurable quality |
| Large image (50MP+) gain map computation memory usage | GPU memory exhaustion | Use existing `tiled_processing()` for tiled processing |

---

## Appendix: Key Code Path Reference

| Function | File | Lines |
|----------|------|-------|
| HDRPhotoMapping data class | `src/spektrafilm/utils/hdr_photo.py` | 55-233 |
| HDRPhotoRenditions output | `src/spektrafilm/utils/hdr_photo.py` | 236-241 |
| prepare_hdr_photo_renditions() | `src/spektrafilm/utils/hdr_photo.py` | 471-482 |
| save_hdr_photo_heic() | `src/spektrafilm/utils/hdr_photo.py` | 262-332 |
| ISO21496GainMapMetadata | `src/spektrafilm/utils/hdr_photo.py` | 1157-1172 |
| build_iso_21496_1_gain_map_metadata() | `src/spektrafilm/utils/hdr_photo.py` | 1175-1214 |
| encode_gain_map_log2() | `src/spektrafilm/utils/hdr_photo.py` | 1217-1255 |
| build_gain_map_xmp_packet() | `src/spektrafilm/utils/hdr_photo.py` | 1258-1307 |
| save_image_oiio() | `src/spektrafilm/utils/io.py` | 531-755 |
| save_hdr_rendition_exr() | `src/spektrafilm/utils/io.py` | 758-820 |
| ICC Profile mapping | `src/spektrafilm/utils/io.py` | 171-258 |
| ArrayBackend protocol | `src/spektrafilm/gpu/backend.py` | 7-30 |
| tiled_processing() | `src/spektrafilm/gpu/backend.py` | 116-194 |
| Color space conversion kernel | `src/spektrafilm/gpu/kernels/color.py` | 1-316 |
| CCTF encode/decode | `src/spektrafilm/gpu/kernels/color.py` | 185-256 |
| ColorEncoding data class | `src/spektrafilm/color_management.py` | 92-130 |
| FilmPrintHDRCurveProfile | `src/spektrafilm/utils/hdr_curve_profiles.py` | 38-51 |
| build_profile_preserving_hdr_curve() | `src/spektrafilm/utils/hdr_curve_profiles.py` | 892-1050 |
| Oklch gamut mapping | `src/spektrafilm/utils/hdr_photo.py` | 1020-1134 |
