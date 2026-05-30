# HDR & Color Review Findings

> Generated 2026-05-28 — HDR & Color Correctness Audit
> Updated 2026-05-28 — Comprehensive review pass (hdr_photo, hdr_curve_profiles, gain_map, scanning, filming, printing, emulsion, diffusion, spectral_upsampling, color_management)

---

## Finding: HDR-C-001
- **Severity**: P1
- **Evidence**: `hdr_photo.py:gamut_map_oklch:1144-1150`
- **Bug**: The Oklch gamut mapping binary search is a no-op. `C_max` is initialized to `C` (the out-of-gamut chroma), so `C_mid = (C_max + C) * 0.5 = C` every iteration. For out-of-gamut pixels, `C_max` never decreases. The final result `C_max * 0.9999` reduces chroma by only 0.01%, providing effectively zero gamut compression.
- **Expected**: Binary search should find the maximum safe chroma between 0 (safe) and C (potentially out-of-gamut), compressing out-of-gamut colors into the displayable range.
- **Repro**: Create a pixel with C=0.8 that is out-of-gamut. Current code reduces chroma to 0.79992 (0.01% reduction) instead of compressing to the gamut boundary.
- **Fix**: Initialize `C_max` to 0.0 for pixels needing work:
  ```python
  C_max = np.where(needs_work, 0.0, 0.0)  # Start at zero (known safe)
  ```
  Then `C` becomes the upper bound and `C_max` the lower bound, allowing proper convergence.
- **Required validation**: Unit test with a known out-of-gamut pixel (e.g., linear sRGB red at headroom=1.0). Assert gamut-mapped result has all channels in [0, headroom] and chroma reduction > 0.01.

---

## Finding: HDR-C-002
- **Severity**: P1
- **Evidence**: `hdr_photo.py:gamut_map_oklch:1135-1137, 1147-1148, 1153-1154`
- **Bug**: `gamut_map_oklch` applies sRGB EOTF (gamma encoding) to linear sRGB before passing to `_linear_srgb_to_oklch`, but the Oklab M1 matrix expects linear-light inputs. The comment at line 1135 says "Linear sRGB → gamma-encoded sRGB → Oklch" which is the wrong order. Bjorn Ottosson's Oklab specification requires linear sRGB → M1 → cbrt(LMS) → M2 → Lab. The current code feeds gamma-encoded values into M1, producing incorrect L (lightness), C (chroma), and h (hue) values. Verified with test color (1.0, 0.2, 0.1): lightness off by 0.113 (15%), chroma off by 0.079 (47%), hue off by ~5 degrees. The roundtrip cancels (error ~3.58e-7 for gray) so the binary search produces *correct linear values* but operates in a *wrong perceptual space*, finding non-optimal gamut boundaries.
- **Expected**: Oklch conversion should operate on linear sRGB values. The correct sequence is: linear sRGB → M1 → cbrt → M2 → Lab → Lch.
- **Repro**: Create a Display P3 image with highly saturated red highlights. Apply `gamut_map_oklch`. Compare Oklch values with a reference implementation (colour-science library). Hue will shift because gamma encoding distorts the a/b ratio.
- **Fix**: Remove the `_linear_to_srgb` / `_srgb_to_linear` steps entirely:
  ```python
  # Forward: linear sRGB → Oklch (no gamma)
  L, C, h = _linear_srgb_to_oklch(srgb)
  # Reverse: Oklch → linear sRGB (no inverse gamma)
  trial = _oklch_to_linear_srgb(L, C_mid, h)
  # Final output already in linear sRGB
  ```
- **Required validation**: Test roundtrip of known sRGB colors through corrected gamut mapping. Assert hue shift < 1 degree for gamut-compressed colors.

---

## Finding: HDR-C-003
- **Severity**: P1
- **Evidence**: `hdr_photo.py:HDRPhotoMapping.__post_init__:187-188; _apply_hdr_color_recovery:728-735`
- **Bug**: `hdr_highlight_path_to_white` has no upper bound in validation. When `profile_hdr_path_to_white_strength=0.0` and `hdr_highlight_path_to_white=5.0` (legacy fallback), `pw_strength` becomes 5.0. For pixels with `pw_mask=1.0`, the blending factor `1.0 - pw_mask * pw_strength = -4.0`, producing negative pixel values: `hdr_rgb * (-4.0) + hdr_luma * 5.0`. For pixel (2.0, 0.5, 0.5) with luma 0.82, R channel becomes -3.9.
- **Expected**: `hdr_highlight_path_to_white` should be bounded to [0, 1] since it represents a blend strength.
- **Repro**: Set `hdr_highlight_path_to_white=5.0`, `profile_hdr_path_to_white_strength=0.0`. Process HDR image with highlights. Output will contain negative pixel values.
- **Fix**: Add upper bound validation:
  ```python
  if not math.isfinite(self.hdr_highlight_path_to_white) or not (0.0 <= self.hdr_highlight_path_to_white <= 1.0):
      raise ValueError("hdr_highlight_path_to_white must be in [0, 1].")
  ```
  Or clamp `pw_strength` at usage: `pw_strength = np.minimum(pw_strength, np.float32(1.0))`
- **Required validation**: Test with `hdr_highlight_path_to_white=5.0`. Assert all output pixels >= 0.

---

## Finding: HDR-C-004
- **Severity**: P1
- **Evidence**: `hdr_photo.py:encode_gain_map_log2:1270-1281`
- **Bug**: `encode_gain_map_log2` computes `log2(hdr_luma / sdr_luma)` with `sdr_luma` floored to `_EPS32` (1e-8). For near-black SDR pixels, `sdr_luma ≈ 1e-8` while `hdr_luma` may be 0.01, producing `log2(0.01 / 1e-8) ≈ 20` stops of gain. After normalization by `max_log_gain` (typically 3), the value saturates to 1.0. Near-black pixels with any HDR content get encoded as "full headroom gain", which the decoder then amplifies by the full headroom factor, producing visible noise or color shifts in shadows.
- **Expected**: Near-black SDR pixels should have near-zero gain, not full headroom gain.
- **Repro**: SDR base with black gradient (0.001 to 0.01), HDR region slightly brighter (0.01 to 0.1). Pixels at sdr=0.001 get gain_map ≈ 1.0 instead of a small value.
- **Fix**: Increase the floor for sdr_luma:
  ```python
  sdr = np.maximum(np.asarray(sdr_rgb, dtype=np.float32), 0.001)
  ```

---

## Finding: HDR-C-005
- **Severity**: P1
- **Evidence**: `gain_map_io.py:_build_mpf_jpeg:216-218; _build_mpf_payload:254`
- **Bug**: The MPF data offset for the gain map image is stored as `base_offset = len(out)`, which is the file position of the MPF APP2 segment itself. The reader computes `gm_start = app2_pos + base_offset`. Since `app2_pos == base_offset`, this yields `gm_start = 2 * base_offset`, pointing far past the actual gain map data. The gain map image can never be correctly extracted from saved JPEGs. The test `test_save_and_load_jpeg_roundtrip` never validates `loaded["gain_map"]` — only checks `loaded["base_image"]` size.
- **Expected**: The MPF data offset should be the byte distance from the MPF APP2 segment start to the gain map data (the size of the MPF APP2 segment, ~40 bytes).
- **Repro**: Save a gain map JPEG, then load it back. The loaded gain map will be garbage data or an extraction error.
- **Fix**: Compute the MPF APP2 segment size deterministically and store that as the offset:
  ```python
  mpf_segment = _build_app2_segment(b"MPF\x00" + _build_mpf_payload(0, len(base_jpeg), len(gm_data)))
  gm_offset_from_mpf = len(mpf_segment)
  mpf_payload = _build_mpf_payload(gm_offset_from_mpf, len(base_jpeg), len(gm_data))
  out += _build_app2_segment(b"MPF\x00" + mpf_payload)
  ```
- **Required validation**: Test full round-trip: save gain map JPEG, load it, assert loaded gain map matches original within float32 tolerance.

---

## Finding: HDR-C-006
- **Severity**: P1
- **Evidence**: `gain_map_io.py:_patch_heif_for_iso21496:293-295`
- **Bug**: The HEIF ftyp brand insertion inserts 4 bytes (`b"tmap"`) at the end of the ftyp box using `data[ftyp_size:ftyp_size] = b"tmap"`. This shifts all subsequent ISOBMFF boxes (moov, mdat, etc.) by 4 bytes. The ftyp box size is updated correctly, but absolute file offsets stored inside the moov box (stco/co64 chunk offset tables, iloc item locations) still reference the old positions. Every chunk offset is now 4 bytes short of the actual data location. Since `_isobmff_patch` module does not exist, this inline fallback always runs, and corruption is silent (try/except at line 136-140).
- **Expected**: Either properly update all internal offsets after byte insertion, or do not modify the binary structure at all.
- **Repro**: Save an HEIF file with gain map. Try to decode it. Decoders reading chunk offsets will read 4 bytes before the actual image data.
- **Fix**: Remove the inline binary patching fallback. If `_isobmff_patch` is unavailable, log a warning but leave the file intact:
  ```python
  try:
      from spektrafilm.utils import _isobmff_patch as patcher
      return patcher.patch_heic_for_iso21496(path, iso_meta=iso_meta)
  except ImportError:
      _log.warning("_isobmff_patch not available; HEIF will lack ISO 21496-1 tmap brand.")
      return False
  ```

---

## Finding: HDR-C-007
- **Severity**: P2
- **Evidence**: `hdr_photo.py:_apply_hdr_color_recovery:748-754`
- **Bug**: Luma-preserving gamut compression can produce values exceeding headroom. When `hdr_luma > max_headroom`: `scale = (headroom - luma) / (max - luma)` where numerator is negative, denominator non-negative. After `clip(scale, 0.0, 1.0)`, scale=0. Result: `hdr_rgb = luma`, which is still > headroom. The caller clips to `safe_max_headroom` at line 620, but the intermediate result is technically out of range.
- **Expected**: The function should be self-contained and guarantee output in [0, max_headroom].
- **Fix**: Add headroom clipping in the return:
  ```python
  return np.clip(hdr_rgb, 0.0, np.float32(max_headroom)).astype(np.float32, copy=False)
  ```

---

## Finding: HDR-C-008
- **Severity**: P2
- **Evidence**: `hdr_photo.py:_apply_hdr_color_recovery:598-603`
- **Bug**: The `hdr_gain` division uses `out=np.ones_like(...)` and `where=s_profile > 1e-6`. For pixels where `s_profile` is near-zero but `h_profile` is also near-zero, the default gain of 1.0 is applied. If `s_profile` is very small (1e-7) but `h_profile` is larger (due to `min_gain` floor at hdr_curve_profiles.py:968-969), the default gain of 1.0 bypasses the min_gain floor, creating a discontinuity at the s_profile=1e-6 boundary.
- **Expected**: The `where` threshold should align with the min_gain logic.
- **Fix**: Use `_EPS32` (1e-8) as the threshold instead of 1e-6, or compute gain with a safer fallback that accounts for min_gain.

---

## Finding: HDR-C-009
- **Severity**: P2
- **Evidence**: `hdr_photo.py:gamut_map_oklch:1133`
- **Bug**: When converting from a working color space to linear sRGB, the code clips to 0.0 after the matrix multiply. For BT.2020 → sRGB with highly saturated colors, small negative values (representing out-of-sRGB-gamut colors) are clipped before Oklch conversion, shifting the hue before gamut mapping begins. Clipping should happen after gamut mapping, not before.
- **Expected**: Small negative values from color space conversion should be preserved for the gamut mapper to handle.
- **Fix**: Remove pre-clipping:
  ```python
  srgb = np.einsum('...i,ji->...j', rgb, M)  # no clipping here
  ```

---

## Finding: HDR-C-010
- **Severity**: P2
- **Evidence**: `hdr_photo.py:_graft_scene_luminance:935-936`
- **Bug**: Scale computation `scale = target_y / np.maximum(look_y, eps)` can produce very large values (1e8+) when `look_y` is near zero but `target_y` is non-zero. When `look_y` is exactly 0.0, the scale becomes `inf * 0 = NaN` due to IEEE 754 semantics.
- **Expected**: Scale should be clamped or the division should use a larger epsilon.
- **Fix**: Add a clamp: `scale = np.clip(target_y / np.maximum(look_y, eps), 0.0, float(mapping.max_headroom) / max(float(eps), 1e-6))`

---

## Finding: HDR-C-011
- **Severity**: P2
- **Evidence**: `gain_map_metadata.py:GainMapMetadata.deserialize:133,156`
- **Bug**: Minimum payload length check uses 15 bytes but the header alone requires 21 bytes (version 4 + flags 1 + base_hdr_headroom 8 + alternate_hdr_headroom 8). A 15-byte payload passes the initial check but crashes during `_unpack_rational(data, 13)` with `struct.error`. Additionally, `expected_len = 15 + channel_count * 40` at line 156 uses wrong base; should be 21.
- **Expected**: Correct minimum is 21 bytes for header + 40 bytes per channel.
- **Fix**: Change line 133 to `if len(data) < 21:` and line 156 to `expected_len = 21 + channel_count * 40`.

---

## Finding: HDR-C-012
- **Severity**: P2
- **Evidence**: `gain_map_metadata.py:GainMapMetadata.to_xmp:201`
- **Bug**: XMP serialization only includes channel 0, discarding per-channel metadata for multichannel gain maps. `ch = self.channels[0]` is used for all XMP attributes. The Adobe hdrgm namespace supports per-channel attributes (GainMapMinR, GainMapMinG, GainMapMinB). Binary payload correctly handles all 3 channels, so only XMP-based consumers are affected.
- **Expected**: When `is_multichannel=True`, emit per-channel XMP attributes.
- **Fix**: Branch on `is_multichannel` and emit per-channel attributes with R/G/B suffixes.

---

## Finding: HDR-C-013
- **Severity**: P2
- **Evidence**: `hdr_photo.py:_prepare_profile_aware_renditions:629; hdr_photo.py:_prepare_generic_renditions:512-516`
- **Bug**: `_prepare_profile_aware_renditions` ignores the `preserve_sdr_base` flag. SDR always uses the authored look (`sdr_rgb = np.clip(look, 0.0, 1.0)`), while the generic path explicitly checks `mapping.preserve_sdr_base` and offers tone-mapped SDR when False. Users may set `preserve_sdr_base=False` expecting different behavior in profile-aware mode.
- **Expected**: Either respect the flag or add a diagnostic warning when it's set to False in profile-aware mode.
- **Fix**: Add `if not mapping.preserve_sdr_base: warnings.warn("preserve_sdr_base=False is ignored in profile_aware mode")`.

---

## Finding: HDR-C-014
- **Severity**: P2
- **Evidence**: `hdr_curve_profiles.py:_classify_polarity:94`
- **Bug**: `y[-1]` and `y[0]` accessed without checking for empty arrays. Calling `build_curve_profile_sample` or `build_dynamic_curve_profile` with empty `scene_y` produces `IndexError: index -1 is out of bounds for axis 0 with size 0`.
- **Expected**: Should raise `ValueError("scene_y must contain at least one sample")`.
- **Fix**: Add size guard in `_classify_polarity`: `if y.size == 0: return "nonmonotonic", 0`

---

## Finding: HDR-C-015
- **Severity**: P2
- **Evidence**: `hdr_curve_profiles.py:build_dynamic_curve_profile:240-241`
- **Bug**: `build_dynamic_curve_profile` does not validate that `scene_y` values are positive, unlike `build_curve_profile_sample` which raises `ValueError` for non-positive values. Non-positive values silently pass through and are clamped to `_EPS` (~1e-8) in `_interp_log_domain`, producing misleading results.
- **Expected**: Both functions should reject non-positive scene_y.
- **Fix**: Add after line 243: `if np.any(scene <= 0.0): raise ValueError("scene_y samples must be positive.")`

---

## Finding: HDR-C-016
- **Severity**: P2
- **Evidence**: `hdr_curve_profiles.py:profile_modern_recovery_budgeted_gain_ev:764,768; profile_relative_hdr_gain_ev:830-835`
- **Bug**: Smoothstep parameters are not validated for ordering. When `recovery_knee_ev >= recovery_full_ev` or `slope_zero >= slope_full`, the smoothstep degrades to a step function, producing discontinuous transitions instead of smooth ramps, which can create visible banding artifacts.
- **Expected**: Validate `edge0 < edge1` for all smoothstep calls.
- **Fix**: Add validation: `if recovery_knee_ev >= recovery_full_ev: raise ValueError(...)` and `if slope_zero >= slope_full: raise ValueError(...)`

---

## Finding: HDR-C-017
- **Severity**: P2
- **Evidence**: `hdr_curve_profiles.py:_interp_log_domain:74-85`
- **Bug**: `np.interp` is called with `xp` that may contain duplicate values (from duplicate `scene_y` entries). NumPy docs state `xp` "must be increasing". NumPy's implementation happens to work with non-strictly-increasing `xp` but this is implementation-specific behavior.
- **Expected**: Deduplicate after sorting to ensure strictly increasing xp.
- **Fix**: After sorting, deduplicate: `mask = np.concatenate([[True], np.diff(sx) > 0]); sx, vy = sx[mask], vy[mask]`

---

## Finding: HDR-C-018
- **Severity**: P2
- **Evidence**: `gain_map_io.py:_build_mpf_payload:252`
- **Bug**: MPF Entry flags for gain map use `0x02000000` (non-standard MP Type). Per CIPA DC-007, value 0x02 is not a standard MP Type. Most gain map implementations (Adobe, Google Ultra HDR) use `0x00000000`. Strict MPF parsers may reject or misinterpret the gain map.
- **Expected**: Use `0x00000000` for the gain map MP Entry flags.
- **Fix**: `payload += struct.pack(">I", 0)`

---

## Finding: HDR-C-019
- **Severity**: P2
- **Evidence**: `hdr_curve_profiles.py:load_hdr_curve_profiles:424-441`
- **Bug**: `lru_cache` caches the same dict object. If any caller mutates the returned dict, the cache is permanently corrupted for all subsequent callers.
- **Expected**: Return a frozen copy.
- **Fix**: Return `dict(profiles)` (shallow copy) at the end.

---

## Finding: COL-001
- **Severity**: P2
- **Evidence**: `color_management.py:apply_color_management_workflow_to_io:77-84`
- **Bug**: The ACES preset sets `saving_color_space` and `saving_cctf_encoding` (lines 64-65), but `apply_color_management_workflow_to_io` only applies 6 of the 8 attributes to the `io` object — `saving_color_space` and `saving_cctf_encoding` are silently omitted. Callers who inspect `io` after applying the workflow will see the original saving params, not the ACES-prescribed `ACES2065-1`.
- **Expected**: All preset attributes applied to `io`, or clear documentation that saving params must be handled separately.
- **Fix**: Add `"saving_color_space"` and `"saving_cctf_encoding"` to the attribute loop.

---

## Finding: COL-002
- **Severity**: P2
- **Evidence**: `color_management.py:ACES_SCENE_LINEAR_COLOR_SPACES:15-20`
- **Bug**: `ACES_SCENE_LINEAR_COLOR_SPACES` only includes `"ACES2065-1"` and `"ACEScg"`. Common OIIO aliases `"lin_ap1"` and `"lin_ap1_scene"` (which are ACEScg) are not recognized, so users passing these aliases get the generic CCTF-based path instead of the ACES scene-linear path.
- **Expected**: The alias table from `utils/io.py` should be consulted, or the frozenset should include common aliases.
- **Fix**: Expand the frozenset or have `is_aces_scene_linear_space` normalize through the alias table.

---

## Finding: COL-003
- **Severity**: P2
- **Evidence**: `filming.py:_simple_rgb_to_density_spectral:237`
- **Bug**: Missing `fmax` guard before `log10`. `np.log10(raw + 1e-10)` is used instead of `np.log10(np.fmax(raw, 0.0) + 1e-10)`. If spectral upsampling returns a negative raw value, `log10` of a negative number returns NaN. This NaN propagates into `density_spectral_midgray`, corrupting the print exposure normalization factor for all subsequent frames. The `expose()` method at lines 98-100 correctly uses `fmax`.
- **Expected**: Consistent with `expose()` method: `np.log10(np.fmax(raw, 0.0) + 1e-10)`
- **Fix**: `log_raw = np.log10(np.fmax(raw, 0.0) + 1e-10)`

---

## Finding: COL-004
- **Severity**: P2
- **Evidence**: `color_reference.py:black_white_xyz_correction:128-131`
- **Bug**: Black/white XYZ correction can amplify noise by factors of 10^7 in dark areas. Scale factor `y_corrected / (y + 1e-10)` is unbounded. For `y=1e-9` and `y_corrected=0.01`, scale = 1e7, turning near-black sensor noise into bright chromatic artifacts.
- **Expected**: Scale factor should be bounded.
- **Fix**: `scale = np.clip(y_corrected / (y + 1e-10), 0.0, 100.0)`

---

## Finding: COL-005
- **Severity**: P2
- **Evidence**: `scanning.py:scan:66-71; color_reference.py:_correction_function:144-150`
- **Bug**: Black/white correction uses init-time clipping settings while `scan()` accepts per-call `output_encoding`. If `scan()` is called with `clip_highlights=False` (HDR mode) but the `ColorReferenceService` was initialized with `clip_highlights=True`, the correction function clips Y to [0, 1] before XYZ-to-RGB, removing highlight information the caller asked to preserve.
- **Expected**: Correction function's clipping should match the final output encoding.
- **Fix**: Pass the current `output_encoding` through to the correction service, or make the correction function encoding-agnostic.

---

## Finding: MOD-001
- **Severity**: P1
- **Evidence**: `spectral_upsampling.py:compute_lut_spectra:215`
- **Bug**: LUT spectra stored in float16 (`np.half`), violating the project's CLAUDE.md constraint: "float32 throughout (no float16 unless explicitly opted in by user)." Spectral irradiance data loses precision — small differences between adjacent wavelengths or subtle spectral features are truncated. The pre-computed `.npy` file uses `np.double` (fine), but the on-the-fly generation path uses float16.
- **Expected**: `np.float32` per the project's GPU precision constraint.
- **Fix**: `lut_spectra = np.array(lut_spectra, dtype=np.float32)`

---

## Finding: MOD-002
- **Severity**: P2
- **Evidence**: `hdr_photo.py:_oklch_to_linear_srgb:1088-1090; _linear_srgb_to_oklch:1075`
- **Bug**: Asymmetric Oklab transform: forward path clips negative LMS to 0 (`np.cbrt(np.maximum(lms, 0.0))`), but reverse path allows negative LMS cubes (`lms ** 3`). When the binary search explores chroma values producing negative LMS in reverse, the forward path's clipping causes the search to converge to a slightly different result than expected.
- **Expected**: Symmetric transform or documented asymmetry.
- **Fix**: Consider `np.sign(lms) * np.cbrt(np.abs(lms))` for a fully symmetric transform, though this deviates from Ottosson's specification. Low priority — the binary search tolerance of -1e-6 handles this.

---

## Finding: MOD-003
- **Severity**: P2
- **Evidence**: `gain_map.py:compute_gain_map:54-64`
- **Bug**: No validation that pixel inputs are non-negative. If `baseline` or `alternate` contain negative values, `num = alternate + k_alternate` could be negative. The `np.maximum(..., 1e-8)` clamp silently replaces negative ratios with 1e-8, producing incorrect gain values without warning.
- **Expected**: Warning or validation for negative inputs.
- **Fix**: Add: `if np.any(b < 0) or np.any(a < 0): _log.warning("Negative pixel values in compute_gain_map inputs")`

---

## Finding: MOD-004
- **Severity**: P3
- **Evidence**: `hdr_photo.py:_paper_logistic_progress:388`
- **Bug**: Mixed float64/float32 precision. `raw0` computed in float64 via `math.exp`, then cast to float32. The normalization `(raw - raw0) / (1 - raw0)` could have subtle precision differences at the float64/float32 boundary.
- **Fix**: Compute `raw0` in float32: `raw0 = np.float32(1.0 / (1.0 + np.exp(-k_f * (np.float32(0.0) - x0_f))))`

---

## Finding: MOD-005
- **Severity**: P3
- **Evidence**: `gain_map_metadata.py:_float_to_rational:23`
- **Bug**: Rational encoding with denominator 10000 gives ~2.3% quantization error for k=1/1023 (0.000977517 encodes as 10/10000=0.001). The test tolerance `abs=1e-3` accommodates this error rather than verifying true precision.
- **Fix**: Use higher precision encoding (1/100000) or store k as a float directly.

---

## Finding: MOD-006
- **Severity**: P3
- **Evidence**: `gain_map_metadata.py:_float_to_unsigned_rational:31`
- **Bug**: `max(1, int(round(value * 10000)))` silently clamps values below 0.00005 to 0.0001. Affects gamma values if set extremely small.
- **Fix**: Remove `max(1, ...)` or document the 0.0001 minimum resolution.

---

## Finding: MOD-007
- **Severity**: P3
- **Evidence**: `gain_map_io.py:_to_pil_image:523-528`
- **Bug**: `is_gain_map` parameter has no effect — both branches perform identical `clip(arr * 255.0, 0, 255).astype(np.uint8)`. Callers pass `is_gain_map=True` expecting different behavior.
- **Fix**: Remove the parameter and dead branch, or implement distinct behavior for gain maps.

---

## Finding: MOD-008
- **Severity**: P3
- **Evidence**: `hdr_curve_profiles.py:budget_recovery_gain_ev:654-656`
- **Bug**: Dead code fallback for `active_mask`. After `np.nan_to_num` + `np.maximum(..., 0.0)`, both `p` and `raw` are guaranteed finite, so `np.isfinite` check is always True and the fallback `active = np.ones(...)` never triggers.
- **Fix**: Remove dead code or add comment explaining it's defensive.

---

## Finding: MOD-009
- **Severity**: P3
- **Evidence**: `hdr_curve_profiles.py:_slope_between:101-104`
- **Bug**: Function name `_slope_between` suggests log-log slope but computes linear-domain slope (output vs. linear scene luminance). For a constant-gamma power law (gamma=0.4), produces `shoulder_severity = 0.69` despite having no actual shoulder.
- **Fix**: Rename to `_linear_slope_between` or add docstring clarifying the domain.

---

## Finding: MOD-010
- **Severity**: P3
- **Evidence**: `spectral_upsampling.py:_illuminant_to_xy:229`
- **Bug**: `xy = xyz[0:2] / np.sum(xyz)` has no guard against zero-sum XYZ from a malformed illuminant spectrum. Produces `inf`/`NaN` with no error.
- **Fix**: `xy = xyz[0:2] / max(np.sum(xyz), 1e-10)`

---

## Finding: MOD-011
- **Severity**: P3
- **Evidence**: `spectral_upsampling.py:locked_logistic_rising:315-326`
- **Bug**: `np.where` evaluates both branches unconditionally. When `nu_log2 > 50.0`, `np.expm1(nu_log2)` overflows to `inf`, producing a RuntimeWarning in some numpy configurations. The masked result is correct but the warning is undesirable.
- **Fix**: Use explicit `if/else` branches instead of `np.where` for scalar `nu`.

---

## Summary by Severity

| Severity | Count | IDs |
|----------|-------|-----|
| P1 | 6 | HDR-C-001, HDR-C-002, HDR-C-003, HDR-C-004, HDR-C-005, HDR-C-006, MOD-001 |
| P2 | 16 | HDR-C-007..019, COL-001..005, MOD-002, MOD-003 |
| P3 | 11 | MOD-004..011, plus findings from existing doc |

## Highest-Priority Fixes

1. **HDR-C-001 + HDR-C-002** (gamut_map_oklch): Broken binary search + wrong Oklch input. Together these mean `oklch_perceptual` gamut mapping produces effectively zero chroma compression in a non-standard perceptual space. Fix both together.
2. **HDR-C-005 + HDR-C-006** (gain map I/O): MPF offset bug breaks JPEG gain map round-trip; HEIF byte insertion corrupts file structure. Both break file I/O round-trips.
3. **HDR-C-003** (path_to_white): Unbounded parameter causes negative pixel values in highlight regions.
4. **MOD-001** (float16 LUT): Violates project's float32 precision constraint for spectral data.
5. **HDR-C-004** (gain map shadows): Near-black pixels get full headroom gain, amplifying shadow noise.

## Non-Goals (Not Trying to Fix)

- Performance-only issues (GPU→CPU round-trips, data re-uploading)
- macOS-specific paths (HEIC Swift encoder, Metal)
- GUI-only issues (QApplication-dependent tests)
- Theoretical ULP-level precision issues that don't manifest in practice
- Documentation/naming issues (P3) — noted but not blocking
