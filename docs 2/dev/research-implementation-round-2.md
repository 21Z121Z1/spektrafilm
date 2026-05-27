# Research Implementation Round 2

Date: 2026-05-27

Source: `docs/dev/research-gpu-color-management.md` + `docs/dev/code-review-2026-05-26.md`

## Selection Criteria

All three improvements were chosen because they are:
1. **Low risk** -- no architectural changes, no behavioral changes to existing working paths
2. **High impact** -- fix correctness gaps, close validation holes, improve metadata completeness
3. **Self-contained** -- each change is isolated and independently testable

## Baseline

Before any changes: **377 passed, 13 skipped** (`.venv/bin/python -m pytest --ignore=tests/gui -q`).

---

## Improvement 1: HDR EXR Rendition Headroom Metadata

**Problem:** When `exr_mode="hdr_rendition"`, the EXR file gets `whiteLuminance` and `chromaticities` but not the computed headroom value. Downstream HDR tools (OCIO, DaVinci Resolve, custom pipelines) need headroom to correctly scale the HDR data.

**Changes:**
- `src/spektrafilm/utils/io.py`: Added `hdr_headroom` variable, captured from `renditions.headroom` when in `hdr_rendition` mode, written to EXR spec as `hdrHeadroom` attribute
- `tests/test_image_io_color_metadata.py`: Updated `test_hdr_rendition_exr_uses_authored_hdr_mapping` to verify `hdrHeadroom` is present and in valid range `[MIN_HDR_HEADROOM, max_headroom]`

**Note:** Used `hdrHeadroom` (camelCase) instead of `hdr:headroom` because OpenEXR doesn't support colons in attribute names. OIIO silently drops attributes with colons during EXR write.

**Test impact:** +1 assertion in existing test (no new test functions).

---

## Improvement 2: HDRPhotoMapping Validation for Remaining Numeric Fields

**Problem:** Five numeric fields in `HDRPhotoMapping` accepted invalid values that would silently produce wrong HDR output:
- `paper_rolloff_contrast`: used as `np.power(progress, contrast)` exponent -- 0 flattens, negative inverts
- `profile_hdr_slope_full`: slope parameter in HDR curve -- 0 flattens, negative inverts
- `profile_hdr_slope_zero`: slope parameter -- negative inverts
- `profile_hdr_soft_clip_softness`: soft clipping parameter -- 0 gives hard clip, negative causes artifacts
- `profile_hdr_min_gain`: gain floor -- below 1.0 allows darkening below the intended minimum

**Changes:**
- `src/spektrafilm/utils/hdr_photo.py`: Added 5 validation checks to `HDRPhotoMapping.__post_init__`:
  - `paper_rolloff_contrast` must be finite positive (> 0)
  - `profile_hdr_slope_full` must be finite positive (> 0)
  - `profile_hdr_slope_zero` must be finite non-negative (>= 0)
  - `profile_hdr_soft_clip_softness` must be finite positive (> 0)
  - `profile_hdr_min_gain` must be finite >= 1
- `tests/test_hdr_photo.py`: Added 11 new parametrized test cases to `test_mapping_validation_rejects_invalid_values`:
  - `paper_rolloff_contrast` = 0.0 and -1.0
  - `profile_hdr_slope_full` = 0.0 and -0.5
  - `profile_hdr_slope_zero` = -0.1
  - `profile_hdr_soft_clip_softness` = 0.0 and -1.0
  - `profile_hdr_min_gain` = 0.5 and -1.0

**Test impact:** +9 new test cases.

---

## Improvement 3: Display P3 Linear ICC Profile

**Problem:** `("Display P3", False)` was missing from `_ICC_FILENAMES`. When `resolve_icc_profile_bytes("Display P3", cctf_encoding=False)` was called (e.g., for linear TIFF export), it returned `None`, meaning no ICC profile was embedded. All other color spaces with linear profiles (sRGB, Adobe RGB, ProPhoto, BT.2020, ACEScg, ACES2065-1) had linear ICC entries.

**Changes:**
- `src/spektrafilm/data/icc/DisplayP3-linear.icc`: New ICC v2 matrix-shaper profile with Display P3 primaries (P3-D65 gamut) and linear TRC (`curv` tag with count=0, meaning gamma=1.0). Generated programmatically from `colour.RGB_COLOURSPACES['Display P3']` primaries and whitepoint.
- `src/spektrafilm/utils/io.py`: Added `("Display P3", False): "DisplayP3-linear.icc"` to `_ICC_FILENAMES` dict.
- `tests/test_image_io_color_metadata.py`:
  - Updated `test_resolve_icc_profile_bytes_returns_none_for_linear_without_bundled_profile`: Changed assertion from `is None` to `is not None` for Display P3 linear. DCI-P3 linear still correctly returns `None`.
  - Added `test_display_p3_linear_icc_profile_has_linear_trc`: Verifies the profile is a valid ICC v2 display profile with a `curv` TRC tag having count=0 (linear/gamma-1.0).

**Test impact:** +1 new test function, 1 assertion changed in existing test.

---

## Final State

After all three improvements: **387 passed, 13 skipped** (+10 from baseline).

### What wasn't done (and why)

| Research recommendation | Reason skipped |
|------------------------|----------------|
| Taichi GPU backend | Too large for self-contained improvement; requires new dependency, new backend class, Vulkan testing |
| Cross-platform HDR gain map encoding | Too large; requires libheif bindings or custom JPEG MPF encoder |
| OCIO integration | Too large; adds heavy optional dependency, requires ACES Output Transform design |
| DCI-P3 linear ICC profile | Lower priority than Display P3; can be added with same pattern when needed |
| GPU tiling for 100MP+ images | Architectural change; needs VRAM detection, tile overlap strategy |

### Remaining items from code review

- **H2** (GUI path-to-white toggle): GUI-only fix, skipped per CLAUDE.md rules (Linux server, no display)
- **H3** (memory optimization): Skipped per CLAUDE.md rules (larger refactor)
- **M1** (HDR SDR-base test expectations): Test expectation issue, not addressed in this round
- **M3** (GUI HEIC test abort): Skipped per CLAUDE.md rules (GUI-only)
- **M4** (save_image_oiio API boundary): Documentation/ownership issue, not addressed in this round
