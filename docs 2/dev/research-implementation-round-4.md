# Research Implementation Round 4 -- GPU Acceleration & Color Management

Date: 2026-05-27

## Context

This round implements improvements based on the findings in `research-gpu-color-management.md` and the code quality review in `code-quality-review-round-4.md`. The research document evaluated cross-platform GPU frameworks, color management systems, and Python integration patterns for Spektrafilm.

## What Was Already Done

The research document's primary recommendations were already implemented in prior rounds:

- **ACEScg ICC mapping** (H1): `_ICC_FILENAMES` has `("ACEScg", True)` and `("ACEScg", False)` entries pointing to `ellelstone/ACEScg-elle-V2-g10.icc`. Verified by `test_acescg_exr_roundtrips_scene_linear_metadata_and_hdr_values` and `test_acescg_tiff_icc_roundtrips_as_linear_encoding`.

- **Display P3 linear ICC profile**: `("Display P3", False)` entry points to `DisplayP3-linear.icc`. Verified by `test_display_p3_linear_icc_profile_has_linear_trc` which confirms gamma=1.0 TRC.

- **HDR Rendition EXR mode** (C1): `save_hdr_rendition_exr()` helper exists in `utils/io.py` with `exr_mode="hdr_rendition"` support in `save_image_oiio`. Verified by `test_save_hdr_rendition_exr_produces_valid_output`.

- **HDRPhotoMapping validation** (M2): `__post_init__` validates all profile-HDR fields (126 lines of validation). Verified by extensive parametrized tests.

- **ISO 21496-1 gain map metadata tests** (TC-H3, TC-H4): Tests for `build_iso_21496_1_gain_map_metadata`, `encode_gain_map_log2`, and `build_gain_map_xmp_packet` exist in `test_hdr_photo.py`.

## Improvements Implemented

### 1. HDR Photo Color Space Fallback Warning (API-M2 / TC-H2)

**Problem**: `hdr_photo_color_space()` silently fell back to `"Display P3"` when given an unsupported color space. Callers passing e.g. `"Adobe RGB"` would get `"Display P3"` with no indication of the substitution.

**Research basis**: Section 2.4 of the research document discusses HDR color space support. The function's silent fallback could surprise callers who expect their specified color space to be used.

**Fix**: Added `logging.warning()` when `color_space` is not `None` and not in `SUPPORTED_HDR_PHOTO_COLOR_SPACES`. The warning includes the unsupported space name and the fallback target.

**Files changed**:
- `src/spektrafilm/utils/hdr_photo.py`: Added `import logging`, `_log = logging.getLogger(__name__)`, and warning in `hdr_photo_color_space()`

**Tests added**:
- `test_hdr_photo_color_space_returns_supported_spaces_unchanged`: Verifies all supported spaces pass through
- `test_hdr_photo_color_space_falls_back_to_display_p3_for_unsupported`: Verifies warning is emitted for unsupported spaces
- `test_hdr_photo_color_space_falls_back_to_display_p3_for_none`: Verifies None falls back silently

### 2. Removed Commented-Out Code in density_curves.py (DC-H1)

**Problem**: `density_curves.py` contained two blocks of commented-out code:
- Lines 23-27: Old `np.interp` implementation replaced by `fast_interp`
- Line 70: Commented-out `return density_cmy_layers` statement

**Research basis**: The code review (round 4) identified commented-out code as a "Must fix" item. Clean code is easier to maintain and reduces confusion.

**Fix**: Removed both commented-out blocks and the unused `density_cmy = np.zeros(...)` initialization (immediately overwritten by `fast_interp`).

**Files changed**:
- `src/spektrafilm/model/density_curves.py`: Removed 6 lines of commented-out code and 1 unused variable initialization

### 3. Test Suite Verification

All 423 non-GUI tests pass (3 new tests added, 13 skipped, 11 warnings). No regressions.

## What Was Not Implemented (and Why)

The research document's remaining recommendations require major architectural changes:

- **Taichi backend** (Priority 2, Section 5.1): Adding a new GPU backend is a significant architectural change. Not self-contained.
- **GPU tiling for 100MP+ images** (Priority 3, Section 5.1): Requires changes to the pipeline architecture. Not low-risk.
- **Cross-platform HDR gain map encoding** (Priority 4, Section 5.2): Replacing macOS-only HEIC encoder requires new dependencies and significant code. Not self-contained.
- **OCIO integration** (Priority 5, Section 5.2): Adding OpenColorIO as a dependency changes the color management architecture. Not self-contained.

## Test Results

```
423 passed, 13 skipped, 11 warnings
```
