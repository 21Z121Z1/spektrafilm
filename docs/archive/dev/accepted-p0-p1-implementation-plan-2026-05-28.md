> **STATUS: COMPLETED** (2026-05-28). P0 and P1 findings fixed during adversarial review pass.

# Accepted P0/P1 Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the accepted audit findings from `docs/agent_audit/accepted_p0_p1.md`, including the accepted-list omission for `HDR-C-002` in `triaged_findings.md`, with regression coverage for every fixed behavior.

**Architecture:** Keep fixes inside the existing module boundaries: HDR math remains in `utils/hdr_photo.py`, file/container handling in `utils/gain_map_io.py`, ICC and EXR I/O in `utils/io.py`, grain in `model/grain.py`, highlight boost in `utils/numba_boost_highlights.py`, and tests beside the current test families. Preserve the contracts in `module_contracts.md`: SDR paths stay unchanged, HDR behavior remains behind explicit HDR/gain-map/export routes, `process()` keeps its legacy array API, and image I/O embeds ICC only when a semantically matching profile exists.

**Tech Stack:** Python 3.13 via `.venv/bin/python` / `.venv/bin/pytest`, NumPy, OpenImageIO, Pillow, colour-science, pytest.

---

## Current State Readback

The audit documents disagree in a few places. `accepted_p0_p1.md` says 17 findings but lists 16; `triaged_findings.md` includes `HDR-C-002` (gain-map near-black log gain), so this plan treats it as accepted. `next_goals.md` also identifies three high-risk leftovers adjacent to the accepted set: Oklch binary search no-op, unbounded legacy `hdr_highlight_path_to_white`, and `compute_lut_spectra()` returning float16. These are narrow, contract-aligned fixes and will be handled in the same pass.

Several accepted items are already partially fixed in current source and need regression hardening rather than another code change:

- `PERF-002`: `boost_highlights()` no longer forces `float64`, but needs an explicit float32/out regression.
- `PERF-016`: `apply_grain_to_density()` already uses `density_cmy = density_cmy + density_min`, but needs an explicit no-mutation regression.
- `HDR-C-004`: `_apply_hdr_color_recovery()` now uses `_EPS32` for the `where=` threshold, but needs a direct discontinuity regression.
- `HDR-C-006`: `_graft_scene_luminance()` now clamps scale; existing test exists and will be retained.
- `FMT-001`: `_patch_heif_for_iso21496()` no longer inserts `tmap` bytes inline; add a no-file-growth regression.
- `FMT-003`: MPF gain-map length already includes EOI; add a byte-level regression.
- `DOC-001`, `TEST-031`, `TEST-033`, `TEST-035`: source/test edits are already present; add or retain verification coverage.

## File Map

**Modify source:**

- `src/spektrafilm/utils/hdr_photo.py`
  - Fix Oklch binary-search bounds.
  - Keep Oklab fed by linear-light sRGB.
  - Add near-black SDR floor for `encode_gain_map_log2()`.
  - Validate legacy `hdr_highlight_path_to_white` in `[0, 1]`.
- `src/spektrafilm/utils/gain_map_io.py`
  - Make missing `pillow-heif` raise `ImportError` instead of writing a `.jpg` at a different path.
  - Keep `_patch_heif_for_iso21496()` non-mutating when `_isobmff_patch` is unavailable.
- `src/spektrafilm/utils/io.py`
  - Use `resolve_icc_profile_bytes()` in the OIIO/TIFF ICC path.
  - Add a DCI-P3 linear ICC entry.
  - Warn on absolute float16 EXR overflow, including negative overflow.
- `src/spektrafilm/utils/spectral_upsampling.py`
  - Return float32 spectra from `compute_lut_spectra()`.
- `src/spektrafilm/data/icc/DCI-P3-linear.icc`
  - Add a linear-TRC DCI-P3 profile derived from the bundled DCI-P3 matrix profile by replacing RGB TRCs with linear `curv` tags.
- `README.md`
  - Keep the `init_params` public API example.

**Modify tests:**

- `tests/test_hdr_photo.py`
  - Strong Oklch compression regression.
  - Near-black gain-map floor regression.
  - `hdr_highlight_path_to_white > 1` validation regression.
  - `hdr_gain` threshold continuity regression if not already covered.
- `tests/test_gain_map.py`
  - HEIF missing dependency raises `ImportError`.
  - MPF stored gain-map size includes EOI.
  - JPEG metadata assertion remains unconditional.
- `tests/test_tier3_fixes.py`
  - Update stale fallback tests to the new ImportError contract.
  - Expand DCI-P3 linear and EXR negative-overflow assertions.
- `tests/test_image_io_color_metadata.py`
  - Change DCI-P3 linear expectation from `None` to valid linear ICC bytes.
- `tests/test_numba_warmup.py`
  - Add float32 in-place highlight boost regression.
- `tests/test_grain.py`
  - Add no input mutation regression.
- `tests/test_pipeline_smoke.py`
  - Replace weak mid-gray range assertion with a stored output reference.
- `tests/test_public_api.py` or existing public API test file
  - Verify `from spektrafilm import init_params, simulate` works as documented.
- `tests/test_spectral_upsampling.py` or existing spectral test file
  - Add a monkeypatched fast regression proving `compute_lut_spectra()` returns `float32`, not `float16`.

**Update docs at completion:**

- `docs/agent_audit/final_validation_report.md`
  - Replace stale claims and record the actual current fixes and validation.

## Task 1: HDR Color And Gain-Map Math

**Files:**
- Modify: `src/spektrafilm/utils/hdr_photo.py`
- Test: `tests/test_hdr_photo.py`

- [ ] **Step 1: Write failing Oklch binary-search test**

Add a test that maps Display P3 green to sRGB gamut and computes Oklch chroma before/after in linear sRGB. Expected failure before the fix: output equals input and chroma delta is 0.

- [ ] **Step 2: Run RED**

Run: `.venv/bin/pytest tests/test_hdr_photo.py::test_gamut_map_oklch_actually_compresses_chroma -q`

Expected: FAIL because current `C_max = C` makes the search a no-op.

- [ ] **Step 3: Implement Oklch search bounds**

Use `C_low = 0`, `C_high = C`, update low on in-gamut trials and high on out-of-gamut trials, then use `C_low * 0.9999` for compressed pixels.

- [ ] **Step 4: Add and run gain-map near-black regression**

Add a test where SDR is black and HDR has a tiny shadow lift. Expected failure before the fix: map saturates to 1.0. Implement by flooring SDR luminance to `1e-3` before division, keeping output finite and below full-headroom saturation for tiny shadow lifts.

- [ ] **Step 5: Add path-to-white validation regression**

Add `HDRPhotoMapping(hdr_highlight_path_to_white=1.5)` expecting `ValueError`. Implement the upper bound in `__post_init__`.

- [ ] **Step 6: Add threshold and zero-look regressions**

Retain/strengthen tests for `_EPS32` threshold continuity and zero-look scene-luminance graft finite output.

## Task 2: Gain-Map Container And HEIF Contract

**Files:**
- Modify: `src/spektrafilm/utils/gain_map_io.py`
- Test: `tests/test_gain_map.py`, `tests/test_tier3_fixes.py`

- [ ] **Step 1: Write failing HEIF missing-dependency test**

Patch `sys.modules["pillow_heif"] = None`, call `save_gain_map_heif("out.heif", ...)`, and expect `ImportError` plus no sibling `.jpg` file.

- [ ] **Step 2: Run RED**

Run: `.venv/bin/pytest tests/test_gain_map.py::TestGainMapIOHeif::test_save_heif_requires_pillow_heif tests/test_tier3_fixes.py::TestHeifSaveRequiresPillowHeif -q`

Expected: FAIL because current code silently writes JPEG fallback.

- [ ] **Step 3: Implement ImportError contract**

Raise `ImportError("pillow-heif is required for HEIF gain map output.")` in `save_gain_map_heif()` and update the docstring.

- [ ] **Step 4: Add byte-level MPF tests**

Verify `_build_mpf_jpeg()` stores a gain-map image size that includes the appended EOI marker and that metadata assertions remain unconditional.

- [ ] **Step 5: Add no-inline-HEIF-patch test**

Verify `_patch_heif_for_iso21496()` returns `False` and leaves file bytes unchanged when `_isobmff_patch` is unavailable.

## Task 3: ICC, EXR, And Spectral Precision

**Files:**
- Modify: `src/spektrafilm/utils/io.py`
- Modify: `src/spektrafilm/utils/spectral_upsampling.py`
- Add: `src/spektrafilm/data/icc/DCI-P3-linear.icc`
- Test: `tests/test_image_io_color_metadata.py`, `tests/test_tier3_fixes.py`, `tests/test_spectral_upsampling.py`

- [ ] **Step 1: Write failing DCI-P3 linear ICC test**

Expect `resolve_icc_profile_bytes("DCI-P3", cctf_encoding=False)` to return bytes with linear TRC tags. Current result is `None`.

- [ ] **Step 2: Add linear ICC profile and mapping**

Create `DCI-P3-linear.icc` by taking the bundled DCI-P3 matrix profile and replacing `rTRC`, `gTRC`, and `bTRC` payloads with linear `curv` tags. Add `("DCI-P3", False): "DCI-P3-linear.icc"` to `_ICC_FILENAMES`.

- [ ] **Step 3: Write failing OIIO ICC fallback test**

Monkeypatch `resolve_icc_profile_bytes()` and fake `oiio.ImageOutput` to prove the TIFF path uses resolver bytes, not `_load_icc_profile()` directly.

- [ ] **Step 4: Implement OIIO resolver call**

Replace `_load_icc_profile(color_space, cctf_encoding)` with `resolve_icc_profile_bytes(color_space, cctf_encoding)` in the non-EXR OIIO path.

- [ ] **Step 5: Add EXR negative overflow regression**

Current warning only checks `image_data > float16.max`; add test for `image_data < -float16.max` and implement `np.abs(image_data) > float16.max`.

- [ ] **Step 6: Add spectral LUT dtype regression**

Monkeypatch spectral helpers so `compute_lut_spectra()` is fast and deterministic; expect `np.float32`, then replace `dtype=np.half` with `dtype=np.float32`.

## Task 4: Already-Fixed Accepted Items Need Durable Regressions

**Files:**
- Test: `tests/test_numba_warmup.py`, `tests/test_grain.py`, `tests/test_pipeline_smoke.py`, `tests/test_public_api.py`

- [ ] **Step 1: Add highlight boost float32 in-place test**

Call `boost_highlights()` with float32 input and float32 `out`, `boost_ev=1.0`; assert returned object is `out`, dtype remains float32, output is finite, and no `ValueError` occurs.

- [ ] **Step 2: Add grain no-mutation test**

Call `apply_grain_to_density()` on an array and assert the original input still equals a saved copy.

- [ ] **Step 3: Strengthen mid-gray smoke reference**

Compute a stable center-pixel reference for current fast test params and assert the pipeline output matches it with a narrow tolerance. This closes the random-noise false-positive gap better than the existing range-only assertion.

- [ ] **Step 4: Add README public API import test**

Verify `from spektrafilm import init_params, simulate` and `init_params(...)` work, matching README.

## Task 5: Verification And Documentation

**Files:**
- Modify: `docs/agent_audit/final_validation_report.md`
- Optional modify: this plan document with completion notes if needed.

- [ ] **Step 1: Run focused tests**

Run:

```bash
.venv/bin/pytest \
  tests/test_hdr_photo.py \
  tests/test_gain_map.py \
  tests/test_tier3_fixes.py \
  tests/test_image_io_color_metadata.py \
  tests/test_numba_warmup.py \
  tests/test_grain.py \
  tests/test_pipeline_smoke.py \
  tests/test_spectral_upsampling.py \
  tests/test_public_api.py -q
```

- [ ] **Step 2: Run full validation gate**

Run:

```bash
.venv/bin/pytest -q
.venv/bin/python -m compileall src tests
git diff --check
```

If full pytest still has known Halide failures, rerun a non-Halide full slice and record the exact failures as baseline in the validation report.

- [ ] **Step 3: Update final validation report**

Record fixed findings, tests added, commands run, known residual failures, and the accepted-list mismatch (`accepted_p0_p1.md` 16 listed vs. 17 accepted in `triaged_findings.md`).

- [ ] **Step 4: 100% confidence loop**

Before marking the goal complete, re-read the diff for each changed module, re-run the target tests after any doc edits, and explicitly check for:

- Any production change without a regression test.
- Any test that only checks source strings where a functional assertion is feasible.
- Any SDR/default pipeline behavior accidentally changed by HDR-only fixes.
- Any container write path that silently changes the requested output format.
- Any ICC mapping that embeds a nonlinear profile for linear pixel data.
