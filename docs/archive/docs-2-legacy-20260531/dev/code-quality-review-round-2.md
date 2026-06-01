# Code Quality Review — Spektrafilm — Round 2

**Date:** 2026-05-27
**Reviewer:** Claude (automated)
**Scope:** All source in `src/spektrafilm/` and `src/spektrafilm_gui/`, plus `tests/`
**Method:** Static analysis, pattern search, manual code reading, cross-referencing with round 1
**Baseline:** Round 1 review (`code-quality-review-round-1.md`) and functional review (`code-review-2026-05-26.md`)

---

## Executive Summary

| Category | HIGH | MEDIUM | LOW |
|---|---|---|---|
| 1. Type Hints & Docstrings | 2 | 5 | 2 |
| 2. Error Handling | 2 | 3 | 1 |
| 3. Dead Code & Unused Imports | 1 | 3 | 3 |
| 4. Code Duplication | 1 | 3 | 1 |
| 5. API Consistency | 2 | 4 | 2 |
| 6. Test Coverage Gaps | 2 | 4 | 2 |
| 7. Performance Anti-patterns | 2 | 3 | 1 |
| 8. Security Concerns | 0 | 2 | 1 |
| **Total** | **12** | **27** | **13** |

---

## 1. Type Hints and Docstrings

### HIGH

#### 1H-1. `SimulationPipeline.__init__` accepts untyped `params` — runtime crash risk
- **File:** `src/spektrafilm/runtime/pipeline.py:191`
- `params` has no type annotation. Callers can pass anything; the constructor immediately accesses `.camera`, `.film`, etc. without guard. The `update_params: bool` parameter is also untyped.
- **Fix:** `def __init__(self, params: RuntimePhotoParams, update_params: bool = False, *, _reused_lut_service: SpectralLUTService | None = None) -> None:`

#### 1H-2. `Simulator.process` and `process_with_metadata` have no return type annotations
- **File:** `src/spektrafilm/runtime/process.py:27, 36`
- `process(self, image)` returns `np.ndarray` but isn't annotated. `process_with_metadata(self, image)` returns `SimulationPipelineResult` but isn't annotated. The `image` parameter is also untyped.
- **Fix:** Add `-> np.ndarray` and `-> SimulationPipelineResult` return types. Type `image` as `np.ndarray`.

### MEDIUM

#### 1M-1. `save_image_oiio` return type is inconsistent across code paths
- **File:** `src/spektrafilm/utils/io.py:529`
- Returns `()` (empty tuple) for PNG/TIFF/EXR paths (lines 680, 748), but delegates to `save_hdr_photo_heic` for HEIC which returns `tuple[str, ...]` with diagnostics. The return type annotation is `tuple[str, ...]` but the PNG/TIFF/EXR paths return `()`.
- **Fix:** Standardize return type. Either always return `tuple[str, ...]` (with `()` meaning "no diagnostics") or use `None` for non-HDR paths. The current `()` return is valid but confusing.

#### 1M-2. `digest_params` mutates its argument but return type suggests immutability
- **File:** `src/spektrafilm/runtime/params_builder.py:48`
- The function modifies `params` in-place (e.g., `params.enlarger.lens_blur = 0.0` at line 56) AND returns it. This is a classic mutation-vs-return confusion. Callers may not realize the original object is modified.
- **Fix:** Either (a) document that the function mutates in-place and returns the same object, or (b) deep-copy before mutating.

#### 1M-3. `_apply_film_specifics` modifies params in-place but is named like a pure function
- **File:** `src/spektrafilm/runtime/params_builder.py:108`
- Same pattern as 1M-2. The function name suggests it returns a new value, but it mutates `params` directly.
- **Fix:** Rename to `_mutate_film_specifics(params)` or return a modified copy.

#### 1M-4. `RuntimePhotoParams.__post_init__` validation is incomplete
- **File:** `src/spektrafilm/runtime/params_schema.py:250`
- Only validates that `film` and `print` are `Profile` instances. Does not validate any numeric ranges on sub-dataclasses (e.g., `camera.exposure_compensation_ev`, `enlarger.print_exposure`, `scanner.white_level`).
- **Fix:** Add range validation for physically meaningful parameters. At minimum: `print_exposure > 0`, `0 < white_level <= 1`, `0 <= black_level < white_level`.

#### 1M-5. `SettingsParams` has a typo in field name with a compatibility shim
- **File:** `src/spektrafilm/runtime/params_schema.py:218`
- `hanatos2025_sensitiviy_adaptation` (missing 't' in 'sensitivity') is the actual field. A property `hanatos2025_sensitivity_adaptation` (correct spelling) wraps it. This creates confusion about which name to use.
- **Fix:** Rename the field to the correct spelling and update all references. The property shim can be removed once all callers are updated.

---

## 2. Error Handling

### HIGH

#### 2H-1. `pipeline.py:560` catches `Exception` broadly and prints to stdout
- **File:** `src/spektrafilm/runtime/pipeline.py:560-561`
- `except Exception as e: print(f"Warning: Failed to characterize profile for HDR mapping: {e}")` — this swallows all exceptions including `MemoryError`, `KeyboardInterrupt` (via subclass), and real bugs. Profile characterization failure should be logged, not printed.
- **Fix:** Use `logging.warning()` instead of `print()`. Catch specific exceptions (`ValueError`, `RuntimeError`, `OSError`).

#### 2H-2. `raw_file_processor.py:288` catches bare `Exception` for EXIF reading
- **File:** `src/spektrafilm/utils/raw_file_processor.py:288`
- `except Exception:` in `_read_exif_metadata` silently returns default values. This hides real errors (e.g., corrupted file, permission denied).
- **Fix:** Catch `(OSError, RuntimeError, exiv2.extras.Exiv2Error)` specifically, matching the pattern in `io.py:69`.

### MEDIUM

#### 2M-1. `params_builder.py:40` uses `print()` for missing filter warning
- **File:** `src/spektrafilm/runtime/params_builder.py:40-44`
- Uses `print()` to warn about missing neutral print filters. This is a library function — it should use `warnings.warn()` or `logging.warning()`.
- **Fix:** Replace `print()` with `warnings.warn(message, UserWarning, stacklevel=2)`.

#### 2M-2. `diffusion.py:118` uses `print()` for filter size warning
- **File:** `src/spektrafilm/model/diffusion.py:118`
- `print(f"Warning: diffusion filter size {max_sigma:.1f} pixels is too large...")` — same issue as 2M-1.
- **Fix:** Use `warnings.warn()`.

#### 2M-3. `profiles/io.py:287` uses `print()` in `save_profile`
- **File:** `src/spektrafilm/profiles/io.py:287`
- `print('Saving profile to:', filename)` — library code should not print to stdout.
- **Fix:** Remove or replace with `logging.debug()`.

### LOW

#### 2L-1. `_swift_command` raises `HDRPhotoExportError` but callers catch `FileNotFoundError`
- **File:** `src/spektrafilm/utils/hdr_photo.py:975-982`
- `_swift_command()` raises `HDRPhotoExportError` when Swift is not found, but the caller at line 293 catches `FileNotFoundError`. This means the `HDRPhotoExportError` propagates uncaught if `shutil.which` returns None but the binary doesn't exist.
- **Fix:** Catch `HDRPhotoExportError` in the caller, or have `_swift_command` raise `FileNotFoundError` to match the caller's expectation.

---

## 3. Dead Code and Unused Imports

### HIGH

#### 3H-1. `timings.py` imports `matplotlib.pyplot` unconditionally at module level
- **File:** `src/spektrafilm/utils/timings.py:3`
- `import matplotlib.pyplot as plt` is imported at module level but only used in `plot_timings()` (line 89), which is a visualization helper. This forces matplotlib to be loaded on every import of the timings module, including in headless environments.
- **Fix:** Move the import inside `plot_timings()`.

### MEDIUM

#### 3M-1. `spectral_upsampling.py` has `if __name__=='__main__'` block with test code
- **File:** `src/spektrafilm/utils/spectral_upsampling.py:645-649`
- The `__main__` block loads LUTs and computes spectra — it's dead test/benchmark code.
- **Fix:** Move to a proper test or benchmark script.

#### 3M-2. `autoexposure.py` has `if __name__ == '__main__'` block with matplotlib
- **File:** `src/spektrafilm/utils/autoexposure.py:239-245`
- Creates a random image, measures exposure, and calls `plt.show()`. Dead benchmark code.
- **Fix:** Move to a test.

#### 3M-3. `grain.py` has extensive `if __name__=='__main__'` block
- **File:** `src/spektrafilm/model/grain.py:223-245`
- Dead benchmark code with matplotlib visualization.
- **Fix:** Move to a test or benchmark script.

### LOW

#### 3L-1. `fft_gaussian_filter.py` has large `if __name__=='__main__'` block
- **File:** `src/spektrafilm/utils/fft_gaussian_filter.py:103-172`
- Dead benchmark code.

#### 3L-2. `fast_gaussian_filter.py` has large `if __name__=='__main__'` block
- **File:** `src/spektrafilm/utils/fast_gaussian_filter.py:355-413`
- Dead benchmark code.

#### 3L-3. Commented-out code in `spectral_upsampling.py`
- **File:** `src/spektrafilm/utils/spectral_upsampling.py:251-256`
- Commented-out chromatic adaptation code in `_rgb_to_tc_b`. Should be removed or documented with a reason.

---

## 4. Code Duplication

### HIGH

#### 4H-1. `_smoothstep` is defined in two files with slightly different implementations
- **Files:**
  - `src/spektrafilm/utils/hdr_photo.py:806-808`
  - `src/spektrafilm/utils/hdr_curve_profiles.py:83-87`
- The `hdr_photo.py` version handles `edge1 <= edge0` gracefully (returns step function), while the `hdr_curve_profiles.py` version has the same guard. Both are identical in behavior but duplicated.
- **Fix:** Extract to a shared utility (e.g., `spektrafilm.utils.math_ops`) and import from both.

### MEDIUM

#### 4M-1. `_content_headroom` and `estimate_raw_hdr_import_diagnostics` duplicate percentile headroom logic
- **Files:**
  - `src/spektrafilm/utils/hdr_photo.py:952-964`
  - `src/spektrafilm/utils/raw_file_processor.py:202-263`
- Both compute percentile-based headroom estimates from image intensity. The HDR photo version uses per-pixel max-channel; the RAW version uses per-pixel max-channel too.
- **Fix:** Extract a shared `_percentile_headroom(intensity, percentile, max_headroom)` helper.

#### 4M-2. `_luminance_y` duplicated across `hdr_photo.py`, `hdr_curve_profiles.py`, `pipeline.py`, and `autoexposure.py`
- **Files:**
  - `src/spektrafilm/utils/hdr_photo.py` — `luminance_y()` at line 49
  - `src/spektrafilm/utils/hdr_curve_profiles.py` — `luminance_y()` at line 49 (same module)
  - `src/spektrafilm/runtime/pipeline.py` — `_scene_luminance_y()` at line 72
  - `src/spektrafilm/utils/autoexposure.py` — `_luminance_y()` at line 22
- All compute Y luminance from RGB using the same BT.709 coefficients, but with different error handling and precision.
- **Fix:** Consolidate into a single `spektrafilm.utils.color.luminance_y()` with configurable error handling.

#### 4M-3. `np.float32(1e-8)` epsilon pattern repeated dozens of times
- **Files:** `src/spektrafilm/utils/hdr_photo.py` (lines 339, 375, 421, 618, etc.), `src/spektrafilm/utils/hdr_curve_profiles.py`
- The same `eps = np.float32(1e-8)` pattern appears ~20 times across these files.
- **Fix:** Define `_EPS32 = np.float32(1e-8)` as a module-level constant and use it everywhere.

### LOW

#### 4L-1. `_prepare_hdr_rgb` validation duplicated in `_prepare_scene_luminance`
- **Files:** `src/spektrafilm/utils/hdr_photo.py:308-320` and `src/spektrafilm/utils/hdr_photo.py:792-803`
- Both validate shape, finiteness, and dtype of input arrays with similar patterns.

---

## 5. API Consistency

### HIGH

#### 5H-1. `save_image_oiio` sometimes returns `()`, sometimes `tuple[str, ...]`
- **File:** `src/spektrafilm/utils/io.py:529`
- PNG/TIFF/EXR paths return `()` (empty tuple). HEIC path returns diagnostics from `save_hdr_photo_heic`. The return type annotation says `tuple[str, ...]` but `()` is technically valid. Callers that check `if diagnostics:` will get `False` for empty tuple, which may mask bugs.
- **Fix:** Return `()` consistently or return `None` for non-HDR paths.

#### 5H-2. `SimulationPipeline.update` re-initializes via `__init__` — fragile pattern
- **File:** `src/spektrafilm/runtime/pipeline.py:495-497`
- `def update(self, params): self.__init__(params, update_params=True)` — calling `__init__` on an existing instance is fragile. If `__init__` is refactored to add class-level state, this will break.
- **Fix:** Use a factory pattern or extract initialization to `_initialize(params, update_params)`.

### MEDIUM

#### 5M-1. `Simulator` methods have inconsistent `image` parameter typing
- **File:** `src/spektrafilm/runtime/process.py:27, 36, 45, 56`
- `process(self, image)` — untyped. `update_params(self, params)` — untyped. `soft_update(self, **kwargs)` — no validation of kwargs.
- **Fix:** Add type annotations. `soft_update` should validate kwargs against known parameter names.

#### 5M-2. `load_image_oiio` uses `IOError` instead of `OSError`
- **File:** `src/spektrafilm/utils/io.py:485`
- `raise IOError("Could not open image file: " + filename)` — `IOError` is an alias for `OSError` in Python 3, but using the old name is inconsistent with the rest of the codebase which uses `OSError`.
- **Fix:** Replace `IOError` with `OSError`.

#### 5M-3. `read_image_color_encoding` raises `IOError` while `read_image_metadata` returns `None`
- **Files:**
  - `src/spektrafilm/utils/io.py:310-313` (raises)
  - `src/spektrafilm/utils/io.py:51-76` (returns None)
- Two functions that read from files have different error semantics. One raises, one returns None.
- **Fix:** Standardize: both should raise on file-not-found, or both should return None.

#### 5M-4. `_known_color_space_from_chromaticities` iterates `_ICC_PROFILES.keys()` instead of `_ICC_FILENAMES.keys()`
- **File:** `src/spektrafilm/utils/io.py:459`
- This means it only checks color spaces in `_ICC_PROFILES`, missing some that are only in `_ICC_FILENAMES` (like `(color_space, True)` vs `(color_space, False)` variants). Since `_ICC_PROFILES` is a superset of unique color space names, this works but is semantically misleading.
- **Fix:** Iterate over unique color space names from both dicts, or use a dedicated set.

### LOW

#### 5L-1. `photo_params` legacy function sets attributes that trigger deprecation warnings
- **File:** `src/spektrafilm/runtime/process.py:153-154`
- `params.io.full_image = True` and `params.io.preview_resize_factor = 1.0` — the first triggers a deprecation warning (line 189), the second would fail since `preview_resize_factor` doesn't exist on `IOParams`.
- **Fix:** Remove these lines or handle the missing attribute.

#### 5L-2. `AgXPhoto` class is a thin wrapper that adds no value
- **File:** `src/spektrafilm/runtime/process.py:139-142`
- `class AgXPhoto(Simulator): def __init__(self, params): super().__init__(digest_params(params))` — this just calls `digest_params` before passing to `Simulator`. The `simulate()` function already does this.
- **Fix:** Document the deprecation timeline or remove if no external consumers remain.

---

## 6. Test Coverage Gaps

### HIGH

#### 6H-1. No tests for `SimulationPipeline.soft_update`
- **File:** `src/spektrafilm/runtime/pipeline.py:499-528`
- `soft_update` modifies pipeline state (camera exposure, enlarger filters, density curves) and recomputes density spectral midgray. No test verifies this works correctly or that the recomputed values are valid.
- **Fix:** Add tests that verify (a) parameter changes propagate, (b) density spectral midgray is recomputed, (c) invalid parameters raise errors.

#### 6H-2. No tests for GPU tiling logic in `SimulationPipeline`
- **File:** `src/spektrafilm/runtime/pipeline.py:386-416`
- `_process_with_gpu_tiles`, `_process_preprocessed_with_gpu_tiles`, `_tile_core_rows`, `_tile_overlap_pixels` — all untested. The tiling logic is complex (overlap computation, strip cropping) and critical for GPU correctness.
- **Fix:** Add tests with small images that verify (a) tiling produces identical results to non-tiled, (b) overlap is computed correctly, (c) edge cases (image smaller than one tile) work.

### MEDIUM

#### 6M-1. No tests for `characterize_pipeline_profile`
- **File:** `src/spektrafilm/runtime/pipeline.py:156-185`
- This function creates a temporary pipeline, runs a ramp through it, and extracts scene/look curves. It's used for HDR profile-aware mapping. No test verifies the output shape, value ranges, or error handling.
- **Fix:** Add a test with a known pipeline configuration that verifies the returned `(scene_y, look_y)` arrays are valid.

#### 6M-2. No tests for `_hdr_scene_energy_metadata`
- **File:** `src/spektrafilm/runtime/pipeline.py:95-153`
- This function computes HDR scene energy metadata (diffuse white, headroom, method, confidence). No test verifies the percentile-based diffuse white estimation or the low-key fallback.
- **Fix:** Add tests for (a) normal image, (b) low-key image, (c) empty image, (d) single-pixel image.

#### 6M-3. No tests for `budget_recovery_gain_ev` edge cases
- **File:** `src/spektrafilm/utils/hdr_curve_profiles.py:601-723`
- The binary search budget logic (lines 686-696) has 64 iterations. No test verifies (a) budget not needed (raw_peak <= target), (b) budget applied with hard_cap, (c) budget with active_mask.
- **Fix:** Add parametrized tests covering the three branches.

#### 6M-4. No tests for `_apply_lens_correction` in `raw_file_processor.py`
- **File:** `src/spektrafilm/utils/raw_file_processor.py:425-502`
- Lens correction depends on `lensfunpy` database lookups. No test verifies (a) camera/lens not found returns original image, (b) correct lens is selected from candidates, (c) coordinate distortion is applied.
- **Fix:** Add tests with monkeypatched `lensfunpy` to verify the selection logic.

### LOW

#### 6L-1. `test_hdr_photo.py` has many tests but no parametrized edge-case coverage for `_smoothstep`
- **File:** `src/spektrafilm/utils/hdr_photo.py:806-808`
- The `_smoothstep` function is used extensively but only tested indirectly through integration tests.

#### 6L-2. No test for `write_curve_profile_database` round-trip
- **File:** `src/spektrafilm/utils/hdr_curve_profiles.py:314-333`
- Writes JSON files but no test verifies the output can be read back by `load_hdr_curve_profiles`.

---

## 7. Performance Anti-patterns

### HIGH

#### 7H-1. `_prepare_profile_aware_renditions` calls `luminance_y(look)` on the full image
- **File:** `src/spektrafilm/utils/hdr_photo.py:542`
- `look_y = luminance_y(look)` computes a full-size float32 luminance array. This is used only for `look_white` estimation (line 862) and path-to-white (line 700). For the diffuse lift path, `look_y` is recomputed from `np.max(look, axis=2)` (line 846). This is a redundant full-image allocation.
- **Fix:** Compute `look_y` lazily only when needed, or reuse the max-channel computation.

#### 7H-2. `characterize_pipeline_profile` creates a full temporary pipeline on every call
- **File:** `src/spektrafilm/runtime/pipeline.py:156-185`
- Each call to `process_with_metadata` triggers `characterize_pipeline_profile`, which deep-copies the entire params, creates a new pipeline, and runs a 512-sample ramp through it. For large images, this adds significant overhead.
- **Fix:** Cache the characterization result per pipeline configuration. The result only depends on the film/print profiles and settings, not the input image.

### MEDIUM

#### 7M-1. `_apply_per_channel` creates contiguous copies of each channel slice
- **File:** `src/spektrafilm/utils/fast_gaussian_filter.py:258`
- `ch_in = np.ascontiguousarray(image[:, :, ch])` — for a 3-channel image, this creates 3 temporary contiguous copies. For large images (50MP+), this is ~200MB of temporary allocations.
- **Fix:** Use `np.ascontiguousarray` on the full image once, then slice with `image[:, :, ch]` which is already contiguous if the image is C-contiguous.

#### 7M-2. `_paper_logistic_progress` and `_paper_logarithmic_progress` allocate `out` array then partially fill it
- **File:** `src/spektrafilm/utils/hdr_photo.py:342, 379`
- Both allocate `out = np.zeros_like(y)` then only fill `out[above]`. For images where most pixels are below `start`, this wastes an allocation.
- **Fix:** This is acceptable for typical HDR images where most pixels exceed start. No change needed unless profiling shows it's a bottleneck.

#### 7M-3. `lru_cache` on `_load_icc_profile` and `_load_icc_profile_from_extra` with no eviction control
- **File:** `src/spektrafilm/utils/io.py:189, 376`
- `@lru_cache(maxsize=64)` and `@lru_cache(maxsize=32)` — ICC profiles can be several KB each. With 64 entries, this could cache ~500KB of profile bytes. Not a problem in practice, but the caches are never cleared.
- **Fix:** Consider using `functools.cache` (unbounded) since the profile set is fixed, or document the cache size rationale.

### LOW

#### 7L-1. `HANATOS2025_SPECTRA_LUT` loaded at module import time
- **File:** `src/spektrafilm/utils/spectral_upsampling.py:440`
- `_load_hanatos2025_spectra_lut()` is called at module import time, loading a NumPy array from disk. This adds import latency even if the LUT is never used.
- **Fix:** Use lazy loading via `functools.lru_cache` or a module-level `__getattr__`.

---

## 8. Security Concerns

### MEDIUM

#### 8M-1. `subprocess.run` in `save_hdr_photo_heic` passes user-controlled filenames to shell
- **File:** `src/spektrafilm/utils/hdr_photo.py:286-292`
- The `command` list includes `str(output_path)` which comes from user input. While `subprocess.run` with a list (not shell=True) is safe against shell injection, the filename is passed as a positional argument to the Swift encoder script. If the filename contains special characters, the Swift script may misinterpret them.
- **Fix:** Validate that the output path contains only safe characters, or use `shlex.quote` when constructing the command for logging.

#### 8M-2. `load_profile` reads arbitrary JSON from package data without size limits
- **File:** `src/spektrafilm/profiles/io.py:291-298`
- `json.load(file)` reads the entire file into memory. If a malicious profile file is very large, this could cause OOM.
- **Fix:** This is low risk since profile files are bundled in the package, but consider adding a size check for user-provided profiles.

### LOW

#### 8L-1. `np.random.seed` in `grain.py` affects global random state
- **File:** `src/spektrafilm/model/grain.py:23`
- `np.random.seed(seed)` sets the global NumPy random state. This is not thread-safe and can affect other code using `np.random`.
- **Fix:** Use `np.random.Generator` with a local `rng = np.random.default_rng(seed)` and pass `rng` to distribution functions.

---

## Cross-Reference with Prior Reviews

### Findings confirmed from Round 1 (`code-quality-review-round-1.md`)
- 1H-1 (save_image_oiio return type) — confirmed, still present
- 1H-2 (SimulationPipeline.__init__ untyped) — confirmed, still present
- 2M-1 (print in library code) — confirmed, still present in `params_builder.py:40`, `profiles/io.py:287`

### Findings confirmed from Functional Review (`code-review-2026-05-26.md`)
- M2 (HDRPhotoMapping validation) — **RESOLVED**. The `__post_init__` now validates all profile-HDR fields (lines 124-211). The round-1 review's M2 finding is addressed.
- H1 (ACEScg ICC mapping) — **RESOLVED**. `_ICC_FILENAMES` now includes ACEScg entries (lines 180-181).
- H2 (GUI path-to-white toggle) — not verifiable in this review (GUI code not fully read).

### New findings not in Round 1
- 3H-1 (matplotlib import in timings.py) — new
- 4H-1 (duplicate _smoothstep) — new
- 5H-2 (update via __init__) — new
- 6H-1 (no tests for soft_update) — new
- 6H-2 (no tests for GPU tiling) — new
- 7H-2 (characterize_pipeline_profile overhead) — new

---

## Prioritized Action List

### Must fix (HIGH priority)
1. **2H-1**: Replace broad `except Exception` in `pipeline.py:560` with specific exceptions and `logging.warning()`.
2. **2H-2**: Replace bare `except Exception` in `raw_file_processor.py:288` with specific exceptions.
3. **3H-1**: Move `matplotlib.pyplot` import in `timings.py` inside `plot_timings()`.
4. **4H-1**: Extract shared `_smoothstep` to `spektrafilm.utils.math_ops`.
5. **5H-2**: Refactor `SimulationPipeline.update` to not call `__init__`.
6. **6H-1**: Add tests for `SimulationPipeline.soft_update`.
7. **6H-2**: Add tests for GPU tiling logic.
8. **7H-2**: Cache `characterize_pipeline_profile` result.

### Should fix (MEDIUM priority)
1. **1M-2/1M-3**: Document or fix mutation-in-return pattern in `digest_params` and `_apply_film_specifics`.
2. **1M-5**: Fix typo in `hanatos2025_sensitiviy_adaptation` field name.
3. **2M-1/2M-2/2M-3**: Replace `print()` with `warnings.warn()` or `logging.warning()` in library code.
4. **4M-2**: Consolidate `_luminance_y` implementations.
5. **5M-2/5M-3**: Standardize error handling in I/O functions.
6. **6M-1/6M-2**: Add tests for `characterize_pipeline_profile` and `_hdr_scene_energy_metadata`.
7. **7M-1**: Remove redundant `np.ascontiguousarray` per-channel copy.

### Nice to have (LOW priority)
1. Remove `if __name__=='__main__'` blocks from library modules.
2. Remove commented-out code in `spectral_upsampling.py`.
3. Fix `np.random.seed` in `grain.py` to use local RNG.
4. Add lazy loading for `HANATOS2025_SPECTRA_LUT`.
