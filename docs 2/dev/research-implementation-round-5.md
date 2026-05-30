# Research Implementation Round 5 -- Oklch Gamut Mapping & ISO 21496-1 Validation

Date: 2026-05-27

## Context

This round implements improvements based on the findings in `research-gpu-color-management.md`, focusing on the remaining gaps after rounds 1-4. The research document's Section 2.6 recommended Oklch-based perceptual gamut mapping as an improvement over the current luma-preserving chroma compression for cross-gamut SDR output. Section 2.4 identified the need for ISO 21496-1 gain map validation tools.

## What Was Already Done (Rounds 1-4)

- H1: ACEScg ICC mapping
- C1: HDR Rendition EXR mode (save_hdr_rendition_exr helper)
- M2: HDRPhotoMapping validation (comprehensive __post_init__)
- Display P3 linear ICC profile
- ISO 21496-1 gain map metadata generator
- GPU tiling utility
- HDR EXR headroom metadata
- ICC profile resolution fix
- README stale reference removal
- HDR photo color space fallback warning
- Commented-out code cleanup

## Baseline

Before any changes: **423 passed, 13 skipped** (`.venv/bin/python -m pytest --ignore=tests/gui -q`).

---

## Improvement 1: Oklch-Based Perceptual Gamut Mapping

**Problem:** The existing gamut compression in `_apply_hdr_color_recovery()` uses luma-preserving chroma reduction. The research document (Section 2.6) recommends Oklch-based perceptual gamut mapping (CSS Color 4 approach) as an alternative that preserves both lightness and hue more accurately for cross-gamut SDR output (e.g., Display P3 highlights compressed to sRGB gamut).

**Research reference:** Section 2.6 (Gamut Mapping) and Section 5.2 Recommendation: "For cross-gamut SDR output (e.g., BT.2020 -> sRGB), consider adding Oklch-based perceptual mapping via colour-science or coloraide."

**Changes:**

- `src/spektrafilm/utils/hdr_photo.py`: Added Oklch gamut mapping infrastructure:
  - `_linear_to_srgb()` / `_srgb_to_linear()`: sRGB EOTF and inverse EOTF
  - `_linear_srgb_to_oklch()` / `_oklch_to_linear_srgb()`: Oklab/Oklch conversion using Bjorn Ottosson's matrices
  - `_working_to_srgb_matrix()` / `_srgb_to_working_matrix()`: Cached color space conversion matrices using `precompute_rgb_to_xyz_matrix` / `precompute_xyz_to_rgb_matrix` from `gpu/kernels/color.py`
  - `gamut_map_oklch(rgb_linear, working_color_space, peak_headroom)`: Main function that converts to Oklch, binary-searches maximum chroma within gamut bounds, preserves L and h
  - Added `gamut_mapping_mode` field to `HDRPhotoMapping` with validation
  - Integrated Oklch mode into `_apply_hdr_color_recovery()` gamut compression section

**Design decisions:**
- Binary search (16 iterations, ~1.5e-5 precision) over chroma axis in Oklch space
- Per-pixel gamut check: convert trial Oklch back to linear sRGB, verify all channels in [0, peak_headroom]
- Color space conversion via pre-computed matrices (cached with `lru_cache`)
- Negative input values clipped to 0 before processing
- `peak_headroom` parameter allows HDR-aware gamut mapping (>1.0 for HDR)

**Tests added to `tests/test_hdr_photo.py`:**
- `test_gamut_map_oklch_in_gamut_is_identity`: In-gamut pixels pass through unchanged
- `test_gamut_map_oklch_clips_negative_values`: Negative values clipped to 0
- `test_gamut_map_oklch_compresses_out_of_gamut`: Saturated Display P3 red compressed for sRGB
- `test_gamut_map_oklch_preserves_neutral`: Neutral greys pass through unchanged
- `test_gamut_map_oklch_handles_hdr_headroom`: HDR values handled with peak_headroom
- `test_gamut_map_oklch_preserves_hue`: Hue preserved through compression
- `test_mapping_validation_rejects_invalid_gamut_mapping_mode`: Validation for new field
- `test_oklch_gamut_compression_integration`: Integration with _apply_hdr_color_recovery
- `test_gamut_map_oklch_display_p3_to_srgb_gamut`: Cross-color-space (Display P3 green → sRGB)
- `test_luma_preserving_mode_is_default_and_unchanged`: Regression test for default behavior

**Test impact:** +10 new test functions.

---

## Improvement 2: ISO 21496-1 Gain Map Validation and Statistics

**Problem:** The gain map metadata generator (Round 3) and XMP packet builder produce ISO 21496-1 compliant output, but there's no way to validate that an encoded gain map is consistent with the metadata, or to inspect gain map statistics for debugging.

**Research reference:** Section 2.4 (HDR Standards & Gain Maps) describes the ISO 21496-1 metadata fields and their relationship to the gain map pixel data.

**Changes:**

- `src/spektrafilm/utils/hdr_photo.py`: Added two new functions:
  - `validate_gain_map(gain_map, metadata)`: Returns list of warnings if gain map values exceed metadata bounds, contain non-finite values, or have wrong shape
  - `gain_map_statistics(gain_map)`: Returns dict with min, max, mean, median, p95, p99, fraction_zero, fraction_one

**Tests added to `tests/test_hdr_photo.py`:**
- `test_validate_gain_map_accepts_consistent_map`: No warnings for valid gain map
- `test_validate_gain_map_flags_out_of_range`: Warning when gain map exceeds metadata max
- `test_validate_gain_map_flags_non_finite`: Warning for NaN/Inf values
- `test_validate_gain_map_rejects_non_2d`: Warning for wrong shape
- `test_gain_map_statistics_reports_correct_values`: Statistics match hand-computed values

**Test impact:** +5 new test functions.

---

## Improvement 3: Cross-Color-Space Coverage and Validation Completeness

**Problem:** The parametrized validation test list didn't include the new `gamut_mapping_mode` field, and there was no test for Oklch gamut mapping across color spaces (the primary use case).

**Changes:**
- `tests/test_hdr_photo.py`:
  - Added `{"gamut_mapping_mode": "invalid"}` to the parametrized validation test
  - Added `test_gamut_map_oklch_display_p3_to_srgb_gamut` for cross-color-space coverage
  - Added `test_luma_preserving_mode_is_default_and_unchanged` regression test

**Test impact:** +1 parametrized test case, +2 new test functions.

---

## Final State

After all three improvements: **439 passed, 13 skipped** (+16 from baseline).

### What wasn't done (and why)

| Research recommendation | Reason skipped |
|------------------------|----------------|
| Taichi GPU backend (Section 5.1 Priority 2) | Major architectural change; new dependency, new backend class |
| Cross-platform HDR gain map encoding (Section 5.2 Priority 4) | Requires libheif or custom JPEG MPF encoder; not self-contained |
| OCIO integration (Section 5.2 Priority 5) | Adds heavy optional dependency; requires ACES Output Transform design |
| GPU tiling VRAM auto-sizing | Already implemented in Round 3; VRAM detection is backend-specific |

### Remaining items from code review

- **H2** (GUI path-to-white toggle): GUI-only fix, skipped per CLAUDE.md rules
- **H3** (memory optimization): Skipped per CLAUDE.md rules (larger refactor)
- **M3** (GUI HEIC test abort): Skipped per CLAUDE.md rules (GUI-only)
- **M4** (save_image_oiio API boundary): Partially addressed in Round 3; full documentation task

### Key architectural notes

- The Oklch gamut mapping uses Bjorn Ottosson's Oklab matrices (2020-01-13) for the linear sRGB ↔ Oklab conversion. The `working_color_space` parameter enables cross-gamut mapping by converting through the sRGB ↔ XYZ ↔ working-space matrix chain.
- Color space conversion matrices are cached with `lru_cache(maxsize=8)` to avoid recomputation.
- The `gamut_mapping_mode` field on `HDRPhotoMapping` defaults to `"luma_preserving"` for full backward compatibility. The `"oklch_perceptual"` mode is opt-in.
- The `gamut_map_oklch` function is a standalone utility that can be used independently of the HDR photo pipeline.
