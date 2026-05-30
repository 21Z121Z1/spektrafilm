# Accepted Findings — P0/P1 Implementation Guide

> 17 findings accepted for fix. Priority order below, with dependencies noted.

---

## Priority Order

### Tier 1 — Critical correctness (fix first)

#### 1. HDR-C-001: Oklch gamut mapping uses gamma-encoded input [P0]
- **File**: `src/spektrafilm/utils/hdr_photo.py:1135-1154`
- **Evidence**: Lines 1136-1137 apply `_linear_to_srgb(srgb)` before `_linear_srgb_to_oklch(srgb_g)`. The Oklab M1 matrix (line 1074) expects linear-light sRGB, not gamma-encoded. The comment at line 1135 says "Linear sRGB → gamma-encoded sRGB → Oklch" which is the wrong conversion order per Bjorn Ottosson's Oklab spec.
- **Impact**: All Oklch-based gamut mapping produces incorrect L, C, h values. Hue shifts on saturated colors, chroma compression targets wrong values.
- **Repro**: Create Display P3 image with saturated red highlights (RGB=[2.0, 0.05, 0.05]). Apply `gamut_map_oklch` with `peak_headroom=4.0`. Compare hue angle with correct Oklch conversion.
- **Fix**: Remove `_linear_to_srgb` at line 1136. Remove `_srgb_to_linear` at lines 1148 and 1154. Feed linear sRGB directly to `_linear_srgb_to_oklch` and receive linear sRGB from `_oklch_to_linear_srgb`.
- **Validation**: `pytest tests/ -k "oklch or gamut_map"` + manual test with saturated HDR colors.
- **Dependencies**: None. Standalone fix.

#### 2. PERF-002: boost_highlights dtype mismatch crashes CPU path [P1]
- **File**: `src/spektrafilm/utils/numba_boost_highlights.py:77,88`
- **Evidence**: Line 77: `x = np.asarray(x, dtype=np.float64)`. Line 88: `if out.dtype != x.dtype: raise ValueError`. When called from `filming.py:75` with `out=raw` (float32 pipeline default), this raises ValueError if `boost_ev > 0`. Currently masked because `boost_ev` defaults to 0.0.
- **Impact**: CPU pipeline crashes with ValueError when highlight boost is enabled (non-default setting).
- **Repro**: Set `halation.boost_ev=1.0` with CPU backend. Process any image.
- **Fix**: Either (a) remove the float64 conversion at line 77 and compile kernel for float32, or (b) convert `out` to match `x` dtype inside the function. Option (a) is preferred since it also fixes the memory issue.
- **Validation**: `pytest tests/ -k "boost"` + test with float32 input and boost_ev=1.0.
- **Dependencies**: None.

#### 3. PERF-016: apply_grain_to_density mutates input array [P2]
- **File**: `src/spektrafilm/model/grain.py:95`
- **Evidence**: Line 95: `density_cmy += density_min` — this is an in-place operation on the caller's array. The caller (`develop` in emulsion.py) passes `density_cmy` from `apply_density_correction_dir_couplers`. If the caller reuses the array after `apply_grain_to_density`, the data is corrupted.
- **Impact**: Silent data corruption if the caller reuses `density_cmy` after grain application.
- **Repro**: Call `develop()` twice with the same input array. Second call gets corrupted input.
- **Fix**: Change line 95 to `density_cmy = density_cmy + density_min` (creates a copy).
- **Validation**: `pytest tests/test_grain.py` + verify no in-place mutation.
- **Dependencies**: None.

#### 4. HDR-C-006: _graft_scene_luminance NaN on zero look_y [P2]
- **File**: `src/spektrafilm/utils/hdr_photo.py:935-936`
- **Evidence**: `scale = target_y / np.maximum(look_y, eps)`. When `look_y=0` exactly, `np.maximum(0, 1e-8) = 1e-8`. If specular rolloff makes `target_y > 0` (via `w_spec * specular_delta`), scale becomes very large. `hdr_rgb = look * scale[..., None]` — since `look` is 0, result is 0, not NaN. But if `look_y` is exactly 0 and there's floating-point noise, `inf * tiny = inf` or `inf * 0 = NaN`.
- **Impact**: Rare NaN/inf in deep shadow regions with specular content.
- **Repro**: Create image with exact-zero look pixels and scene luminance in those regions.
- **Fix**: Add clamp: `scale = np.minimum(scale, float(mapping.max_headroom) / max(eps, 1e-6))` or use `np.nan_to_num`.
- **Validation**: `pytest tests/test_hdr_photo.py` + test with zero-look pixels.
- **Dependencies**: None.

#### 5. FMT-001: ISOBMFF brand-patching corrupts file structure [P1]
- **File**: `src/spektrafilm/utils/gain_map_io.py:276-298`
- **Evidence**: Line 293: `data[ftyp_size:ftyp_size] = b"tmap"` inserts 4 bytes into the ftyp box. Line 295 updates the ftyp box size header. But every ISOBMFF box after ftyp (meta, mdat, moov) has its absolute file offset shifted by +4 bytes. Internal offset tables (stco/co64) now point 4 bytes too early.
- **Impact**: Corrupted HEIF file structure. May work with lenient parsers but fails with strict ones.
- **Repro**: Write a gain map HEIF, then parse with a strict ISOBMFF validator.
- **Fix**: Remove the inline fallback (lines 276-298). Log a warning and return False. The proper `_isobmff_patch` module handles this correctly.
- **Validation**: `pytest tests/test_gain_map.py` + verify HEIF output with strict validator.
- **Dependencies**: None.

#### 6. FMT-003: MPF gain map size off by 2 bytes [P1]
- **File**: `src/spektrafilm/utils/gain_map_io.py:217,222`
- **Evidence**: Line 217: `gm_length = len(gm_data)` where `gm_data` has SOI and EOI stripped. Line 222: `out += gm_data + _EOI` — the actual written data is 2 bytes larger. A conforming MPF reader would truncate the gain map JPEG, missing the final EOI marker.
- **Impact**: Gain map JPEG may be truncated by conforming MPF readers.
- **Repro**: Save gain map JPEG, parse with external MPF reader, verify gain map integrity.
- **Fix**: Change line 217 from `len(gm_data)` to `len(gm_data) + 2`.
- **Validation**: `pytest tests/test_gain_map.py` + round-trip verification.
- **Dependencies**: None.

### Tier 2 — High-priority fixes

#### 7. DOC-001: README uses non-existent API function [P1]
- **File**: `README.md:66-72`
- **Evidence**: Line 66: `from spektrafilm import create_params, simulate`. Actual API (`__init__.py:4`) exports `init_params`, not `create_params`. This raises ImportError for anyone following the README.
- **Impact**: Broken onboarding — new users cannot run the example code.
- **Repro**: Copy README code sample into a fresh Python script. Run it. ImportError.
- **Fix**: Change `create_params` to `init_params` in the README code sample.
- **Validation**: Copy-paste README code and verify it runs.
- **Dependencies**: None.

#### 8. TEST-031: test_color_management.py imports GUI module [P1]
- **File**: `tests/test_color_management.py:14`
- **Evidence**: Line 14: `from spektrafilm_gui.options import RGBColorSpaces` — module-level import. On headless Linux where `spektrafilm_gui` is not installed, this causes `ModuleNotFoundError` and all 10 color management tests silently disappear from the suite.
- **Impact**: All color management encoding, ACES workflow, and validation tests are disabled on CI.
- **Repro**: Run `pytest tests/test_color_management.py` on headless Linux without GUI. All tests skipped/errored.
- **Fix**: Move `from spektrafilm_gui.options import RGBColorSpaces` inside the test function that uses it, guarded by `pytest.importorskip("spektrafilm_gui")`.
- **Validation**: `pytest tests/test_color_management.py -v` — should show 9 tests pass, 1 skips.
- **Dependencies**: None.

#### 9. TEST-032: Pipeline smoke tests lack value assertions [P1]
- **File**: `tests/test_pipeline_smoke.py`
- **Evidence**: `_assert_valid_output` only checks shape, finiteness, and [0,1] bounds. No test asserts that a specific input produces a specific output value. The pipeline could return uniform random noise in [0,1] and every smoke test would pass.
- **Impact**: Regressions in film simulation accuracy go undetected.
- **Fix**: Add at least one test with a known mid-gray input that asserts output values against a stored reference (even `atol=0.05`).
- **Validation**: Verify the new test catches an intentional regression (e.g., wrong density curve).
- **Dependencies**: None.

#### 10. TEST-033: LUT path comparison tolerance too loose [P2]
- **File**: `tests/test_pipeline_smoke.py:200`
- **Evidence**: `np.testing.assert_allclose(result_lut, result_direct, atol=0.02)` — 2% absolute tolerance on [0,1] data for a 17-point LUT on uniform gray input. A LUT interpolation bug producing 1.5% error would pass.
- **Impact**: LUT indexing errors or interpolation bugs go undetected.
- **Fix**: Tighten to `atol=0.005` for uniform gray, or add a test with a color ramp.
- **Validation**: Verify tighter tolerance still passes with current code.
- **Dependencies**: None.

#### 11. TEST-035: JPEG gain map metadata test conditionally asserts [P2]
- **File**: `tests/test_gain_map.py:566-568`
- **Evidence**: `if loaded["metadata"] is not None: assert ...` — if `load_gain_map` fails to extract metadata, the test silently passes without checking anything.
- **Impact**: Regression in JPEG MPF metadata embedding goes undetected.
- **Fix**: Assert `loaded["metadata"] is not None` unconditionally, then check values.
- **Validation**: Verify test fails when metadata extraction is broken.
- **Dependencies**: None.

### Tier 3 — Important fixes

#### 12. HDR-C-004: hdr_gain threshold discontinuity [P2]
- **File**: `src/spektrafilm/utils/hdr_photo.py:598-603`
- **Evidence**: `where=s_profile > 1e-6` but division uses `np.maximum(s_profile, _EPS32)` (1e-8). For pixels at `s_profile=9e-7`, the default gain is 1.0 (from `out=np.ones_like`), but adjacent pixels at `s_profile=1.1e-6` get the computed gain (e.g., 1.5). This creates a visible discontinuity.
- **Impact**: Visible banding at the s_profile=1e-6 boundary in HDR color recovery.
- **Fix**: Lower the `where` threshold to `_EPS32` (1e-8) to match the division floor.
- **Validation**: `pytest tests/test_hdr_photo.py` + visual test with gradient input.
- **Dependencies**: None.

#### 13. FMT-004: HEIF save silently falls back to JPEG [P2]
- **File**: `src/spektrafilm/utils/gain_map_io.py:119`
- **Evidence**: When `pillow-heif` is unavailable, line 119-121: `jpeg_path = Path(output_path).with_suffix(".jpg"); save_gain_map_jpeg(jpeg_path, ...)`. Caller requested `.heif` but gets `.jpg` at a different path. No exception raised.
- **Impact**: Caller has no way to know output format changed without checking filesystem.
- **Fix**: Raise `ImportError("pillow-heif is required for HEIF gain map output.")` instead of silent fallback.
- **Validation**: Test with pillow-heif unavailable; verify ImportError is raised.
- **Dependencies**: None.

#### 14. FMT-005: PIL save path missing ICC fallback [P2]
- **File**: `src/spektrafilm/utils/io.py:690`
- **Evidence**: Line 690: `icc_bytes = _load_icc_profile(color_space, cctf_encoding)` — this only checks `_ICC_FILENAMES`. If the entry is missing, ICC is silently omitted. The OIIO path (line 754) has the same issue. `resolve_icc_profile_bytes` adds a fallback to `_load_icc_profile_from_extra`.
- **Impact**: Some color spaces get no ICC profile embedded in 8-bit PNG/JPEG output.
- **Fix**: Replace `_load_icc_profile(...)` with `resolve_icc_profile_bytes(...)` at line 690 (and line 754 for OIIO path).
- **Validation**: Save DCI-P3 linear JPEG, verify ICC profile is embedded.
- **Dependencies**: FMT-006 (adding the missing ICC entry would also fix this for DCI-P3 linear).

#### 15. FMT-006: Missing DCI-P3 linear ICC entry [P2]
- **File**: `src/spektrafilm/utils/io.py:171-191`
- **Evidence**: `_ICC_FILENAMES` has `("DCI-P3", True)` but not `("DCI-P3", False)`. Linear DCI-P3 output gets no ICC from the primary lookup.
- **Impact**: DCI-P3 linear files have no embedded ICC profile.
- **Fix**: Add `("DCI-P3", False): "saucecontrol/DCI-P3-v4.icc"` (or appropriate linear variant) to `_ICC_FILENAMES`.
- **Validation**: Save DCI-P3 linear EXR/TIFF, verify ICC is present.
- **Dependencies**: None.

#### 16. FMT-008: EXR float16 overflow [P2]
- **File**: `src/spektrafilm/utils/io.py:711-716`
- **Evidence**: Line 714: `img_half = image_data.astype(np.float16)`. float16 max is ~65504. HDR scene-linear data can exceed this, producing `inf` in the output EXR.
- **Impact**: Corrupted EXR output for bright HDR scenes at bit_depth=16.
- **Fix**: Add warning when data exceeds float16 range: `if np.any(np.abs(image_data) > 65504): _log.warning(...)`.
- **Validation**: Create image with values > 65504, save as 16-bit EXR, verify warning is emitted.
- **Dependencies**: None.

---

## Dependency Graph

```
FMT-006 ──→ FMT-005 (adding ICC entry makes fallback less critical)
```

All other findings are independent and can be fixed in any order within their tier.
