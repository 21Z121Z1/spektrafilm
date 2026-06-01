# Test Improvement Plan — 2026-05-27

## Current Status
- **295 tests pass**, 13 skipped, 6 warnings
- No GUI tests run (Linux headless server)
- Good coverage of core pipeline (emulsion, couplers, grain, GPU backends)
- Excellent HDR photo test coverage (~80 tests)

## Coverage Gaps

### Source Files With No Corresponding Tests

| Source File | Risk | Notes |
|---|---|---|
| `utils/fft_gaussian_filter.py` | **HIGH** | Complex FFT math, no tests. Uses pyFFTW. Should validate against scipy reference. |
| `runtime/services/color_reference.py` | **HIGH** | Black/white correction logic with complex branching. No unit tests. |
| `runtime/stages/printing.py` | **MEDIUM** | Complex printing stage, tested only indirectly via pipeline integration. |
| `utils/crop_resize.py` | **MEDIUM** | Boundary clamping logic, easy to get wrong at edges. |
| `utils/calibration_targets.py` | **LOW** | Visualization tool, heavy matplotlib dependency. |
| `utils/plotting.py` | **LOW** | Visualization utility. |
| `gpu/metal_serialization.py` | **SKIP** | macOS/Metal only, not available on Linux. |

### Untested Error Paths in Existing Code

**`HDRPhotoMapping.__post_init__`** — Many validation checks exist but not all have dedicated tests:
- `diffuse_white <= 0`
- `sdr_paper_white` out of (0,1) range
- `shoulder_strength <= 0`
- `hdr_diffuse_lift_start >= hdr_diffuse_lift_end`
- `hdr_diffuse_lift_strength` out of [0,1]
- `look_diffuse_white_reference <= 0`
- `hdr_highlight_color_mode` invalid
- `hdr_highlight_gamut` invalid
- `profile_curve_mode` invalid
- `profile_hdr_peak_ev <= 0`
- `profile_hdr_strength` out of [0,1]
- `profile_hdr_mode` invalid

**`params_builder.py`** — `apply_database_neutral_print_filters` has a missing-filters warning path, never tested.

**`parametric.py`** — Only 2 tests. Missing: positive film polarity, edge cases (extreme gamma, zero toe/shoulder).

### Test Quality Issues

1. **`test_parametric.py`**: Only 2 tests for a model with many parameters. No parametrize, no edge cases.
2. **`test_emulsion.py`**: Good coverage but no negative test for invalid inputs.
3. **`test_hdr_photo.py`**: Extensive but focused on happy-path HDR behavior. Some `__post_init__` validation paths untested.

## Priority Test Additions (Ranked by Bug-Catching Impact)

### P1: FFT Gaussian Filter Accuracy (NEW file: `tests/test_fft_gaussian_filter.py`)
**Why**: Untested complex numerical code. FFT-based filtering is easy to get wrong (kernel scaling, padding, truncation). A regression here would silently corrupt image output.

**Tests**:
1. 2D filter accuracy vs `scipy.ndimage.gaussian_filter` (scalar sigma)
2. 3D filter accuracy vs scipy (per-channel sigma)
3. Error on unsupported dimensionality (1D, 4D)
4. Error on sigma array length mismatch
5. `pad=False` produces valid output
6. Scalar sigma on 3D image uses same sigma for all channels

### P2: Crop/Resize Boundary Logic (NEW file: `tests/test_crop_resize.py`)
**Why**: Boundary clamping at image edges is a classic off-by-one source. Easy to test, high confidence gain.

**Tests**:
1. Center crop produces correct size
2. Edge crop clamps to image bounds (center near 0 or 1)
3. Crop size larger than image handles gracefully
4. Non-square image with aspect ratio crop
5. Output shape matches expected dimensions

### P3: Parametric Density Curve Edge Cases (extend `tests/test_parametric.py`)
**Why**: Only 2 tests for a model with 6+ parameters. Missing positive-film polarity and boundary conditions.

**Tests**:
1. Positive film polarity (decreasing curves)
2. Extreme gamma values (very low, very high)
3. Zero toe/shoulder sizes
4. Density max is respected as upper bound
5. Symmetric gamma produces symmetric curves

### P4: HDRPhotoMapping Validation Coverage (extend `tests/test_hdr_photo.py`)
**Why**: The `__post_init__` has ~25 validation checks. About half are tested. Untested checks are silent bugs waiting to happen — invalid parameters could pass through unchecked.

**Tests** (parametrized for compactness):
1. `diffuse_white <= 0` raises ValueError
2. `sdr_paper_white = 0.0` and `sdr_paper_white = 1.0` raise ValueError
3. `shoulder_strength <= 0` raises ValueError
4. `hdr_diffuse_lift_start >= hdr_diffuse_lift_end` raises ValueError
5. `hdr_diffuse_lift_strength` out of [0,1] raises ValueError
6. `hdr_highlight_color_mode` invalid raises ValueError
7. `profile_curve_mode` invalid raises ValueError
8. `profile_hdr_peak_ev <= 0` raises ValueError
9. `profile_hdr_strength` out of [0,1] raises ValueError
10. `profile_hdr_mode` invalid raises ValueError

### P5: ColorReferenceService Unit Tests (NEW file: `tests/test_color_reference.py`)
**Why**: Complex correction logic with 4+ branching paths. Currently only tested indirectly through integration. A unit test isolates the correction math.

**Tests**:
1. No correction returns identity when both corrections disabled
2. Negative film scan returns identity (no correction applied)
3. Black-only correction shifts output appropriately
4. White-only correction shifts output appropriately
5. Combined black+white correction is a linear transform
6. `_remove_cctf` round-trips correctly

## Implementation Order
1. P1 (FFT gaussian filter) — highest risk, zero coverage
2. P2 (crop/resize) — easy win, boundary bugs are common
3. P3 (parametric edge cases) — extend existing file
4. P4 (HDRPhotoMapping validation) — extend existing file
5. P5 (ColorReferenceService) — new file, complex logic

## Success Criteria
- All new tests pass
- No regressions (295 existing tests still pass)
- Coverage of previously untested code paths
