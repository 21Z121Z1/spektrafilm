# Research Implementation Round 1

Date: 2026-05-27
Based on: `docs/dev/research-gpu-color-management.md` and `docs/dev/code-review-2026-05-26.md`

## Context

After reading the GPU acceleration & color management research document and cross-referencing with the code review findings, we identified the TOP 3 most impactful improvements that are low-risk, high-impact, and self-contained. Many findings from the code review (H1 ACEScg ICC, C1 HDR Rendition EXR, M2 HDRPhotoMapping validation) were already resolved in prior work. We focused on the remaining gaps.

## Changes Made

### 1. HDRPhotoMapping Validation: `paper_rolloff_x0` and `hdr_render_ev`

**File:** `src/spektrafilm/utils/hdr_photo.py`

Added missing `__post_init__` validation for two fields:

- **`paper_rolloff_x0`**: Must be a finite positive value. Previously accepted negative or zero values, which would cause invalid Logistic rolloff math (division by zero or negative progress).
- **`hdr_render_ev`**: Must be finite. Previously accepted NaN or Inf, which would propagate through `2.0 ** hdr_render_ev` producing silent NaN/Inf in scene luminance.

**Tests added:** `tests/test_hdr_photo.py` - 4 new parametrized test cases:
- `paper_rolloff_x0=0.0` rejected
- `paper_rolloff_x0=-0.5` rejected
- `hdr_render_ev=NaN` rejected
- `hdr_render_ev=Inf` rejected

**Risk:** Very low. Only adds validation; no existing valid construction is affected.

### 2. ICC Profile Resolution for Linear Data

**File:** `src/spektrafilm/utils/io.py`

Fixed `resolve_icc_profile_bytes()` to correctly handle linear data requests. Previously, when `cctf_encoding=False` was passed for color spaces without a bundled linear profile (Display P3, DCI-P3), the function fell through to `_load_icc_profile_from_extra()` which returns the sRGB-TRC encoded profile. Embedding an encoded ICC profile in a file with linear pixel data is semantically incorrect and would cause downstream tools to misinterpret the data.

**Fix:** Skip the `_ICC_PROFILES` fallback when `cctf_encoding=False`. The `_ICC_FILENAMES` lookup (which IS parameterized by `cctf_encoding`) correctly handles all color spaces with bundled linear profiles (sRGB, Adobe RGB, ProPhoto RGB, BT.2020, ACES2065-1, ACEScg).

**Behavior change:**
- `resolve_icc_profile_bytes("Display P3", False)` → now returns `None` (was returning sRGB-TRC profile)
- `resolve_icc_profile_bytes("DCI-P3", False)` → now returns `None` (was returning encoded profile)
- All other combinations unchanged

**Test added:** `tests/test_image_io_color_metadata.py` - `test_resolve_icc_profile_bytes_returns_none_for_linear_without_bundled_profile()`

**Risk:** Low. The only production call site (`controller_runtime.py:216`) uses the default `cctf_encoding=True`. The `save_image_oiio` function uses `_load_icc_profile` directly (already correct).

### 3. README Stale Reference

**File:** `README.md`

Removed the reference to `spektrafilm_profile_creator` in the dependency direction section (line 78). This package does not exist in the source tree.

**Risk:** None. Documentation-only change.

## Test Results

```
372 passed, 13 skipped, 12 warnings
```

Baseline was 367 passed. The +5 increase comes from:
- 4 new HDRPhotoMapping validation parametrized tests
- 1 new ICC profile resolution test

## What Was NOT Changed (and Why)

| Research Finding | Status | Reason |
|---|---|---|
| H1: ACEScg ICC mapping | Already done | `_ICC_FILENAMES` already has both ACEScg entries |
| C1: HDR Rendition EXR mode | Already done | `exr_mode` parameter exists in `save_image_oiio()` |
| M2: HDRPhotoMapping validation | Mostly done | Only `paper_rolloff_x0` and `hdr_render_ev` were missing |
| Display P3 linear ICC generation | Not done | No bundled linear P3 profile exists; generating one from scratch is fragile (PIL rejects hand-crafted ICC binaries). The resolution fix prevents incorrect profiles from being returned instead |
| Taichi backend | Not done | New dependency, not self-contained |
| GPU tiling utility | Not done | New feature, no existing code path uses it |
| Cross-platform HDR gain map | Not done | Major feature, requires libheif or custom JPEG MPF encoding |
| OCIO integration | Not done | Major feature, adds new dependency |
