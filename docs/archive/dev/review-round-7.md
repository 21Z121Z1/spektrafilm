# Autonomous Code Review — Round 7

Date: 2026-05-27

## Findings

### C1: Oklch gamut mapping uses wrong color space (Correctness bug)
- **File**: `src/spektrafilm/utils/hdr_photo.py:736`
- **Severity**: Critical
- **Description**: `gamut_map_oklch(hdr_rgb, peak_headroom=max_headroom)` is called without a `working_color_space` argument, defaulting to `"sRGB"`. But `hdr_rgb` is in the pipeline's output color space (typically Display P3). The function converts "working → sRGB" using an sRGB matrix, but if the data is already in Display P3, it incorrectly applies a Display P3 → sRGB conversion thinking the input is sRGB.
- **Mapping has the correct field**: `hdr_highlight_gamut` with values `"display-p3"`, `"rec2020"`, `"working"` is never forwarded.
- **Fix**: Map `hdr_highlight_gamut` to the actual color space name and pass it to `gamut_map_oklch`.

### H1: Missing validation in HDRPhotoMapping.__post_init__ (Type safety)
- **File**: `src/spektrafilm/utils/hdr_photo.py:134-233`
- **Severity**: High
- **Description**: Several `profile_hdr_*` fields lack validation:
  - `profile_hdr_knee_ev`: no finiteness or range check
  - `profile_hdr_enforce_monotonic`: no type check (bool)
  - `profile_hdr_max_chroma_gain`: no validation at all
  - `profile_hdr_path_to_white_start_ev` / `_end_ev`: no individual finiteness checks (only pairwise comparison)
- **Fix**: Add validation for these fields.

### M1: Unused function `_known_color_space_from_icc_profile` (Dead code)
- **File**: `src/spektrafilm/utils/io.py:419-421`
- **Severity**: Medium
- **Description**: Defined but never called anywhere in the codebase. It's a thin wrapper around `_known_encoding_from_icc_profile`.
- **Fix**: Remove the function.

### M2: Duplicate module with typo in filename (Dead code / confusion)
- **File**: `src/spektrafilm/utils/numba_boost_hightlights.py`
- **Severity**: Medium
- **Description**: The misspelled module `numba_boost_hightlights.py` exists as a backward-compat shim that just re-exports from `numba_boost_highlights.py`. It is imported in one test file (`tests/test_numba_warmup.py:4`). Since test files cannot be modified per CLAUDE.md rules, we note this but keep the shim for now.
- **Fix**: None (test file dependency prevents removal).

### M3: `GainMapMetadata` missing headroom ordering validation
- **File**: `src/spektrafilm/utils/gain_map_metadata.py:71-81`
- **Severity**: Medium
- **Description**: `__post_init__` validates version ranges and channel count but does not enforce `base_hdr_headroom < alternate_hdr_headroom`, which is required by ISO 21496-1.
- **Fix**: Add ordering validation.

### L1: `_to_pil_image` treats gain map identically to SDR base
- **File**: `src/spektrafilm/utils/gain_map_io.py:514-540`
- **Severity**: Low
- **Description**: When `is_gain_map=True` and input is float, the code does `arr * 255.0` — same as the SDR path. This is correct since gain maps are already [0,1] normalized. No action needed.

## Fixes Applied (Round 7)

1. **C1**: Pass correct `working_color_space` to `gamut_map_oklch` based on `mapping.hdr_highlight_gamut`
2. **H1**: Add missing validation for `profile_hdr_knee_ev`, `profile_hdr_enforce_monotonic`, `profile_hdr_max_chroma_gain`, `profile_hdr_path_to_white_start_ev`/`_end_ev`
3. **M1**: Remove unused `_known_color_space_from_icc_profile`
4. **M3**: Add `base_hdr_headroom < alternate_hdr_headroom` validation to `GainMapMetadata`
5. **L1**: No fix needed (behavior is correct)
