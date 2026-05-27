# Autonomous Code Review — Round 8

Date: 2026-05-27

## Findings

### H1: `_compute_raw_preflash` returns wrong shape when preflash disabled (Bug)
- **File**: `src/spektrafilm/runtime/stages/printing.py:146`
- **Severity**: High
- **Description**: When `preflash_exposure <= 0`, returns `np.zeros((3,))` which is 1D. But the caller at line 134 does `raw = raw + raw_preflash` where `raw` is 3D `(H, W, 3)`. NumPy broadcasting makes this work, but the intent is clearly wrong — it should return a shape compatible with the batch data. If the caller changes to use `+=` or in-place ops, this would silently broadcast incorrectly.
- **Fix**: Return `np.zeros((1, 1, 3))` for consistency.

### M1: ANSI color codes in timing output leak into non-terminal contexts
- **File**: `src/spektrafilm/utils/timings.py:5-6,78-80`
- **Severity**: Medium
- **Description**: `format_timings` unconditionally embeds ANSI escape codes (`\033[31m`) for highlighting the top-3 slowest stages. When output is captured to a log file, CI artifact, or GUI text widget, these codes render as garbage characters.
- **Fix**: Make ANSI highlighting opt-in via a parameter, defaulting to off.

### M2: `ResizingService.small_preview` doesn't preserve input dtype
- **File**: `src/spektrafilm/runtime/services/resize.py:33-43`
- **Severity**: Medium
- **Description**: `skimage.transform.rescale` with `order=0` returns float64 regardless of input dtype. For float32 pipeline data, this doubles memory usage for the preview and may cause dtype mismatches downstream.
- **Fix**: Add `.astype(image.dtype)` after rescale.

### M3: `density_to_light` silently converts NaN to 0
- **File**: `src/spektrafilm/utils/conversions.py:23`
- **Severity**: Medium
- **Description**: `transmitted[np.isnan(transmitted)] = 0` silently masks NaN values. NaN in density typically indicates corrupted input data. Silently zeroing makes debugging harder.
- **Fix**: Remove the NaN masking — let NaNs propagate so callers can detect corruption.

### M4: `crop_image` can produce empty crops when size > image
- **File**: `src/spektrafilm/utils/crop_resize.py:24`
- **Severity**: Medium
- **Description**: When crop size exceeds image dimensions, `x0[0] = shape[0]-sz[0]` can go negative. The function doesn't clamp the crop size to the image dimensions, potentially returning an empty array.
- **Fix**: Clamp `sz` to `shape` before computing `x0`.

### L1: `_remove_cctf` creates redundant array for single value
- **File**: `src/spektrafilm/runtime/services/color_reference.py:159-166`
- **Severity**: Low
- **Description**: Creates a `(1, 1, 3)` array just to call `RGB_to_RGB` on a single luminance value, then takes the mean. This is a full colour-science pipeline call for what could be a simpler CCTF decode.
- **Fix**: Acceptable trade-off for correctness. No change.

## Fixes Applied (Round 8)

1. **H1**: Fix `_compute_raw_preflash` return shape
2. **M1**: Make ANSI highlighting opt-in in `format_timings`
3. **M2**: Preserve dtype in `ResizingService.small_preview`
4. **M4**: Clamp crop size in `crop_image`
5. **M3**: Remove silent NaN masking in `density_to_light`
