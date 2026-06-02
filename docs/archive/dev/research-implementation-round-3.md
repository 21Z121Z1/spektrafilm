# Research Implementation Round 3

Date: 2026-05-27

Source: `docs/dev/research-gpu-color-management.md` + `docs/dev/code-review-2026-05-26.md`

## Selection Criteria

All three improvements were chosen because they are:
1. **Low risk** -- additive new functions, no behavioral changes to existing working paths
2. **High impact** -- enable cross-platform HDR workflows, large image processing, API clarity
3. **Self-contained** -- each change is isolated and independently testable

## Baseline

Before any changes: **387 passed, 13 skipped** (`.venv/bin/python -m pytest --ignore=tests/gui -q`).

---

## Improvement 1: ISO 21496-1 Gain Map Metadata Generator

**Problem:** Spektrafilm's HDR photo export is macOS-only (Swift/CoreImage HEIC). There's no cross-platform way to generate gain map metadata for JPEG/HEIC HDR encoding per ISO 21496-1 (the standard used by Apple iOS 17+ and Adobe Lightroom).

**Research reference:** Sections 2.4 (HDR Standards & Gain Maps) and 5.2 Priority 4 (Cross-platform HDR gain map encoding).

**Changes:**
- `src/spektrafilm/utils/hdr_photo.py`: Added three new components:
  - `ISO21496GainMapMetadata` dataclass: Stores the 7 required gain map parameters (`gainMapMin`, `gainMapMax`, `gamma`, `offsetSDR`, `offsetHDR`, `hdrCapacityMin`, `hdrCapacityMax`)
  - `build_iso_21496_1_gain_map_metadata(renditions)`: Computes gain map metadata from HDR renditions, using headroom to derive `gainMapMax = log2(headroom)`
  - `encode_gain_map_log2(sdr_rgb, hdr_rgb)`: Encodes the per-pixel gain map as `log2(hdr_luma / sdr_luma)`, normalised to [0, 1]
  - `build_gain_map_xmp_packet(metadata)`: Generates a standards-compliant XMP packet with all ISO 21496-1 fields, suitable for embedding in JPEG APP1 or HEIC metadata

**Tests added to `tests/test_hdr_photo.py`:**
- `test_build_iso_21496_1_gain_map_metadata_from_renditions`: Verifies metadata matches headroom
- `test_gain_map_metadata_custom_luminance`: Verifies custom luminance parameters
- `test_encode_gain_map_log2_neutral`: SDR-only content produces zero gain
- `test_encode_gain_map_log2_highlights`: HDR highlights produce positive gain
- `test_build_gain_map_xmp_packet_contains_required_fields`: XMP contains all required fields

**Test impact:** +5 new test functions.

---

## Improvement 2: GPU Tiling Utility for Large Images

**Problem:** Processing 100MP+ images on GPU can exceed VRAM. The research document (section 1.4) describes the standard pattern of tiled processing with overlap regions, but no implementation existed.

**Research reference:** Sections 1.4 (GPU Tiling for Large Images) and 5.1 Priority 3 (Add GPU tiling for 100MP+ images).

**Changes:**
- `src/spektrafilm/gpu/backend.py`: Added `tiled_processing()` function:
  - Splits image into overlapping tiles of configurable size
  - Processes each tile through a caller-provided function on the backend
  - Discards overlap regions to prevent seam artifacts
  - Validates full coverage (no uncovered pixels)
  - Works with any `ArrayBackend` (NumPy, MLX, CuPy) -- zero backend-specific code
  - Overlap parameter: element-wise ops need 0, Gaussian blur needs `3*sigma`

**Tests added to `tests/test_gpu_backend.py`:**
- `test_tiled_processing_identity_element_wise`: Element-wise tiling matches no-tiling result
- `test_tiled_processing_with_overlap`: Tiled 3x3 mean filter matches full-image filter
- `test_tiled_processing_covers_full_image`: Every pixel is processed
- `test_tiled_processing_rejects_invalid_tile_size`: Validates tile_size > 2*overlap

**Test impact:** +4 new test functions.

---

## Improvement 3: `save_hdr_rendition_exr()` Convenience Wrapper

**Problem:** The `save_image_oiio()` function handles HDR rendition EXR via `exr_mode="hdr_rendition"`, but the API requires callers to construct a `ColorEncoding`, pass `exr_mode`, and know the sidecar parameters. The code review M4 finding identified unclear API boundaries.

**Research reference:** Section 5.3 (Specific Code Changes) recommends a dedicated `save_hdr_rendition_exr` helper.

**Changes:**
- `src/spektrafilm/utils/io.py`: Added `save_hdr_rendition_exr()` function:
  - Thin wrapper around `save_image_oiio()` with `exr_mode="hdr_rendition"`
  - Automatically constructs the correct `ColorEncoding` (linear, scene, unclipped)
  - Validates the file extension is `.exr`
  - Accepts all HDR sidecar parameters (`scene_luminance`, `scene_rgb`, `hdr_mapping_kwargs`)
  - Defaults `white_luminance` to 203 nits (HDR reference white)
  - Returns diagnostics from the HDR mapping

**Tests added to `tests/test_image_io_color_metadata.py`:**
- `test_save_hdr_rendition_exr_produces_valid_output`: Verifies EXR has HDR metadata and distinct pixels
- `test_save_hdr_rendition_exr_rejects_non_exr_extension`: Validates extension check

**Test impact:** +2 new test functions.

---

## Final State

After all three improvements: **398 passed, 13 skipped** (+11 from baseline).

### What wasn't done (and why)

| Research recommendation | Reason skipped |
|------------------------|----------------|
| Taichi GPU backend | Too large for self-contained improvement; requires new dependency, new backend class, Vulkan testing |
| OCIO integration | Too large; adds heavy optional dependency, requires ACES Output Transform design |
| ACES Output Transform (RRT+ODT) | Requires OCIO or custom implementation; not self-contained |
| ACEScct/ACEScc log working spaces | Requires UI grading workflow; not self-contained |
| BT.2100 PQ/HLG encoding | Requires display-side metadata; not self-contained |

### Remaining items from code review

- **H2** (GUI path-to-white toggle): GUI-only fix, skipped per CLAUDE.md rules (Linux server, no display)
- **H3** (memory optimization): Skipped per CLAUDE.md rules (larger refactor)
- **M1** (HDR SDR-base test expectations): Test expectation issue, not addressed in this round
- **M3** (GUI HEIC test abort): Skipped per CLAUDE.md rules (GUI-only)
- **M4** (save_image_oiio API boundary): Partially addressed by Improvement 3; full ownership clarification is a documentation task

### Key architectural notes

- The ISO 21496-1 metadata generator produces standards-compliant XMP that can be embedded in JPEG (via MPF) or HEIC files by downstream encoders. The actual gain map image encoding (lossy compression, container packaging) is format-specific and left to the caller.
- The GPU tiling utility is backend-agnostic and works with any `ArrayBackend`. For VRAM-aware tile sizing, callers can query CuPy's `cp.cuda.Device.memory_info()` and pass an appropriate `tile_size`.
- The `save_hdr_rendition_exr` wrapper makes the HDR EXR export path explicit and self-documenting, addressing the M4 API boundary concern without changing existing behavior.
