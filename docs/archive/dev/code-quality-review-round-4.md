> **STATUS: ARCHIVED** (historical). Findings addressed in subsequent rounds or adversarial review pass.

# Code Quality Review -- Round 4 -- Spektrafilm -- 2026-05-27

Comprehensive code quality review covering: type hints, error handling, dead code, code duplication, API consistency, test coverage, performance anti-patterns, and security concerns.

Review scope: all Python files in `src/spektrafilm/` and `src/spektrafilm_gui/` (~80 files), plus test files.
Method: Full file reads, grep-based pattern search, cross-referencing with rounds 1-3 findings.

## What Was Fixed in Rounds 1-3

The following issues from prior reviews have been addressed:

- `math_ops.py` extraction (smoothstep centralized)
- `save_image_oiio` now has full type annotations and returns `tuple[str, ...]` consistently
- `HDRPhotoMapping.__post_init__` now validates all profile-HDR fields (M2 from functional review)
- `load_image_oiio` now has type annotations
- `pipeline.py` print statement replaced with `_log.warning` (2H-1 from round 2)
- `_runtime_image_dtype` extracted to `utils/dtypes.py` with proper typing
- `params_builder.py` logging improved

## Findings Summary

| Category | Critical | High | Medium | Low |
|---|---|---|---|---|
| 1. Type Hints & Docstrings | 0 | 5 | 12 | 8 |
| 2. Error Handling | 0 | 3 | 6 | 4 |
| 3. Dead Code & Unused Imports | 0 | 2 | 8 | 6 |
| 4. Code Duplication | 0 | 3 | 5 | 3 |
| 5. API Consistency | 0 | 4 | 7 | 5 |
| 6. Test Coverage Gaps | 1 | 5 | 8 | 4 |
| 7. Performance Anti-patterns | 0 | 3 | 5 | 3 |
| 8. Security Concerns | 0 | 1 | 3 | 2 |
| **Total** | **1** | **26** | **54** | **35** |

---

## 1. Type Hints and Docstrings

### HIGH

**TH-H1. `Pipeline.process` and `process_with_metadata` still lack return type annotations**
- **File:** `src/spektrafilm/runtime/pipeline.py:296,313`
- `def process(self, image):` and `def process_with_metadata(self, image) -> SimulationPipelineResult:` -- the first has no return annotation, and both accept untyped `image`.
- **Fix:** `def process(self, image: np.ndarray) -> np.ndarray:` and `def process_with_metadata(self, image: np.ndarray) -> SimulationPipelineResult:`

**TH-H2. `Pipeline.soft_update` has 7 untyped keyword parameters**
- **File:** `src/spektrafilm/runtime/pipeline.py:506-513`
- All parameters default to `None` with no type annotations: `exposure_compensation_ev`, `print_exposure`, `c_filter_neutral`, `m_filter_neutral`, `y_filter_neutral`, `film_density_curves`, `print_density_curves`.
- **Fix:** Add `float | None` for scalar params and `np.ndarray | None` for density curves.

**TH-H3. `Pipeline.update` accepts untyped `params`**
- **File:** `src/spektrafilm/runtime/pipeline.py:502`
- `def update(self, params):` -- should be `def update(self, params: RuntimePhotoParams) -> None:`.

**TH-H4. `Simulator.soft_update` has no type annotations at all**
- **File:** `src/spektrafilm/runtime/process.py:58`
- `def soft_update(self, **kwargs):` -- kwargs are untyped, return type missing.
- **Fix:** Match the signature of `Pipeline.soft_update` with explicit typed keyword args, or at minimum add `-> None`.

**TH-H5. `Simulator.get_timings`, `get_total_elapsed_time`, `format_timings`, `print_timings` all lack return types**
- **File:** `src/spektrafilm/runtime/process.py:81-95`
- Four public methods with no return annotations.
- **Fix:** Add `-> dict[str, float]`, `-> float | None`, `-> str`, `-> None`.

### MEDIUM

**TH-M1. `ArrayBackend` Protocol uses `Any` for every method**
- **File:** `src/spektrafilm/gpu/backend.py:7-31`
- All 14 methods use `Any` for parameters and returns. This defeats the purpose of a Protocol.
- **Fix:** At minimum: `to_numpy -> np.ndarray`, `max -> float`, `asarray(value: np.ndarray | ...) -> Any`.

**TH-M2. `NumpyBackend` methods lack return type annotations**
- **File:** `src/spektrafilm/gpu/numpy_backend.py:18-67`
- All 14 methods have no return types despite being straightforward numpy wrappers.
- **Fix:** Add `-> np.ndarray` to array methods, `-> float` to `max`, `-> None` to `eval`/`synchronize`.

**TH-M3. `CupyBackend` methods lack return type annotations**
- **File:** `src/spektrafilm/gpu/cupy_backend.py:46-105`
- Same issue as TH-M2.

**TH-M4. All `runtime/stages/` classes lack method type annotations**
- **Files:** `src/spektrafilm/runtime/stages/filming.py:21-33`, `printing.py:19-45`, `scanning.py:22-45`
- Constructor parameters are all untyped. `expose`, `develop`, `scan` methods lack annotations.
- **Fix:** Add parameter and return types to all stage class methods.

**TH-M5. `runtime/services/` classes lack method type annotations**
- **Files:** `src/spektrafilm/runtime/services/spectral_lut_compute.py`, `resize.py`, `filter_enlarger_source.py`, `color_reference.py`
- Constructor parameters untyped, public methods untyped.

**TH-M6. `gpu/kernels/` modules have zero type annotations**
- **Files:** `src/spektrafilm/gpu/kernels/color.py`, `density.py`, `filters.py`, `lut.py`
- All functions use raw numpy arrays with no type hints.

**TH-M7. `model/` modules consistently lack return type annotations**
- **Files:** All files in `src/spektrafilm/model/` -- `parametric.py`, `couplers.py`, `stocks.py`, `density_curves.py`, `diffusion.py`, `grain.py`, `illuminants.py`, `glare.py`, `emulsion.py`, `color_filters.py`
- Covered in round 3 TH-H1-H8, still outstanding.

**TH-M8. `profiles/io.py` `profile_to_dict` still has no type annotations**
- **File:** `src/spektrafilm/profiles/io.py:218`
- `def profile_to_dict(data):` -- no parameter or return type. This was 1H-4 in round 1.

**TH-M9. `profiles/io.py` `profile_from_dict` still uses `Any`**
- **File:** `src/spektrafilm/profiles/io.py:198`
- `def profile_from_dict(data: Any) -> Profile:` -- should accept `Mapping | Profile`.

**TH-M10. `ProfileData.__post_init__` has no return annotation**
- **File:** `src/spektrafilm/profiles/io.py:108`
- Should be `def __post_init__(self) -> None:`.

**TH-M11. `load_dichroic_filters` and `load_filter` have no return type annotations**
- **File:** `src/spektrafilm/utils/io.py:894,910`
- Both return `np.ndarray` but aren't annotated.

**TH-M12. `autoexposure.py` has zero docstrings on any function**
- **File:** `src/spektrafilm/utils/autoexposure.py`
- 15 public/private functions, none have docstrings. This was noted in round 1 (1M-1) and is still outstanding.

### LOW

**TH-L1. `fast_interp_lut.py` docstrings use inconsistent style**
- Some functions have NumPy-style docstrings, others have single-line descriptions, some have none.

**TH-L2. `fast_gaussian_filter.py` public API has minimal docstrings**
- `fast_gaussian_filter`, `fast_gaussian_filter_small`, `fast_gaussian_filter_large`, `fast_exponential_filter` have one-line descriptions but no parameter/return docs.

**TH-L3. `crop_resize.py` `crop_image` docstring uses non-standard parameter format**
- Uses `Parameters:` with parenthetical type hints instead of NumPy-style.

**TH-L4. `numba_boost_hightlights.py` filename has typo**
- "hightlights" should be "highlights". The public function `boost_highlights` is correctly spelled.

**TH-L5. `config.py` has no module docstring**
- **File:** `src/spektrafilm/config.py:1`

**TH-L6. `spectral_upsampling.py` module-level docstring is missing**
- **File:** `src/spektrafilm/utils/spectral_upsampling.py`

**TH-L7. `fast_stats.py` functions have minimal docstrings**
- **File:** `src/spektrafilm/utils/fast_stats.py`

**TH-L8. `hdr_curve_profiles.py` complex functions lack detailed docstrings**
- `build_profile_preserving_hdr_curve`, `build_dynamic_curve_profile` etc. have minimal or no docstrings explaining the algorithm.

---

## 2. Error Handling

### HIGH

**EH-H1. `controller.py:917` catches bare `Exception` and re-raises after resetting simulator**
- **File:** `src/spektrafilm_gui/controller.py:917`
- `except Exception: self._runtime_simulator = None; raise` -- this catches `KeyboardInterrupt`, `SystemExit`, and `GeneratorExit` (subclasses of `BaseException` that bypass `Exception`, but still). The pattern is correct for its purpose (reset on any error), but the bare `except Exception` should be narrowed to `(RuntimeError, ValueError, OSError, MemoryError)` to avoid masking unexpected errors.

**EH-H2. `controller.py:531` catches broad `Exception` for metadata reading**
- **File:** `src/spektrafilm_gui/controller.py:531`
- `except Exception as exc:` when reading image metadata. Should be `(OSError, RuntimeError, exiv2.extras.Exiv2Error)` to match the pattern in `read_image_metadata`.

**EH-H3. `pipeline.py:567` catches 5 exception types for profile characterization**
- **File:** `src/spektrafilm/runtime/pipeline.py:567`
- `except (ValueError, RuntimeError, OSError, AttributeError, TypeError) as e:` -- `AttributeError` and `TypeError` suggest the code is defensively catching programming errors. If the API contract is correct, these shouldn't be needed. Consider whether `AttributeError`/`TypeError` indicate real bugs being swallowed.

### MEDIUM

**EH-M1. `hdr_photo.py:260-261` -- `save_hdr_photo_heic` raises `HDRPhotoExportError` but callers catch `Exception`**
- **File:** `src/spektrafilm_gui/controller.py:531`
- The controller catches generic `Exception` when it should catch `HDRPhotoExportError` specifically.

**EH-M2. `diffusion.py:110-140` -- `apply_diffusion_filter_mm` uses `warnings.warn` but doesn't validate inputs**
- **File:** `src/spektrafilm/model/diffusion.py:110`
- `diffusion_fraction`, `sigma_mm`, `iterations`, `growth`, `decay` are destructured from a tuple with no validation. Negative `sigma_mm` or `iterations <= 0` silently returns data unchanged.

**EH-M3. `spectral_upsampling.py:446-449` -- LUT loading failure is a warning, not an error**
- **File:** `src/spektrafilm/utils/spectral_upsampling.py:446`
- `HANATOS2025_SPECTRA_LUT` is set to `None` on failure, but downstream functions raise `RuntimeError` when it's `None`. The warning at import time is easy to miss; the runtime error is confusing without context.
- **Fix:** Include the original exception message in the RuntimeError at call sites.

**EH-M4. `io.py:864-868` -- `save_neutral_print_filters` writes to package resources**
- **File:** `src/spektrafilm/utils/io.py:864`
- Writing to `importlib.resources` may fail silently or raise unclear errors depending on how the package is installed (editable vs. wheel). No error handling for write failures.

**EH-M5. `measure.py:75` -- `least_squares` result is not checked for convergence**
- **File:** `src/spektrafilm/utils/measure.py:75`
- `fit = least_squares(residues, k0, bounds=(lb, ub))` -- `fit.success` is never checked. A failed fit silently produces garbage `density_min` values.

**EH-M6. `crop_resize.py:4-28` -- `crop_image` can produce empty arrays silently**
- **File:** `src/spektrafilm/utils/crop_resize.py:4`
- If `size` is very small relative to image, `sz` can become 0, producing an empty array with no warning.

### LOW

**EH-L1. `timings.py:42` -- `format_timings` divides by zero when `percentage_total` is 0**
- **File:** `src/spektrafilm/utils/timings.py:57`
- Guarded by `if percentage_total > 0` but the `else` branch returns `"  0.0%"` which may be misleading when timings are actually nonzero but total is unknown.

**EH-L2. `fast_interp_lut.py:140` -- floating-point comparison `weight_sum != 0.0`**
- **File:** `src/spektrafilm/utils/fast_interp_lut.py:140`
- Exact float comparison. Should use `abs(weight_sum) > eps` for robustness.

**EH-L3. `autoexposure.py:239-245` -- `__main__` block uses `plt.show()` which hangs on headless**
- **File:** `src/spektrafilm/utils/autoexposure.py:239`
- Same pattern in `fast_interp.py:119`, `fast_gaussian_filter.py:355`, `lut.py:649`, `numba_boost_hightlights.py:128`.

**EH-L4. `profiles/io.py:281` -- validation catches broad exceptions**
- **File:** `src/spektrafilm/profiles/io.py:281`
- `except (AttributeError, IndexError, KeyError, TypeError):` -- masks programming errors in validation logic itself.

---

## 3. Dead Code and Unused Imports

### HIGH

**DC-H1. Commented-out code blocks in production files**
- **File:** `src/spektrafilm/utils/lut.py:52-58` -- `_create_lut_2d` fully commented out
- **File:** `src/spektrafilm/utils/crop_resize.py:30-41` -- `resize_image` fully commented out with `#TBD`
- **File:** `src/spektrafilm/model/density_curves.py:72` -- `interpolate_layers` commented out
- **File:** `src/spektrafilm/utils/measure.py:35-42` -- old `curve_toe` implementation commented out
- **Fix:** Remove all commented-out code. Use git history to recover if needed.

**DC-H2. `diffusion.py:143` -- `from scipy.signal import fftconvolve` at module level after function definitions**
- **File:** `src/spektrafilm/model/diffusion.py:143`
- This import is placed after 140 lines of code, violating PEP 8 import ordering. It's used only in `apply_diffusion_filter_um`. Should be at the top of the file.

### MEDIUM

**DC-M1. `spectral_upsampling.py:186-198` -- commented-out code in `_fetch_coeffs`**
- **File:** `src/spektrafilm/utils/spectral_upsampling.py:186-198`
- Large block of commented-out color space conversion code.

**DC-M2. `diffusion.py:25-27` -- commented-out scipy import in `apply_unsharp_mask`**
- **File:** `src/spektrafilm/model/diffusion.py:25`
- `# image_blur = scipy.ndimage.gaussian_filter(image, sigma=(sigma, sigma, 0))`

**DC-M3. `diffusion.py:93-96` -- commented-out scipy import in `apply_gaussian_blur`**
- **File:** `src/spektrafilm/model/diffusion.py:93-96`

**DC-M4. `diffusion.py:102-105` -- commented-out scipy import in `apply_gaussian_blur_um`**
- **File:** `src/spektrafilm/model/diffusion.py:102-105`

**DC-M5. `emulsion.py:93-96` -- stale future-work comments**
- **File:** `src/spektrafilm/model/emulsion.py:93-96`
- "Some future work notes:" comments that should be in issue tracker, not code.

**DC-M6. `emulsion.py:98-99` -- empty `if __name__ == '__main__': pass` block**
- **File:** `src/spektrafilm/model/emulsion.py:98-99`

**DC-M7. `io.py:507` -- stale comment "Fallback: use 'uint16' by default. You might choose 'float' if desired."**
- **File:** `src/spektrafilm/utils/io.py:507`

**DC-M8. `runtime/api.py` is a pure re-export shim**
- **File:** `src/spektrafilm/runtime/api.py`
- Re-exports everything from `process.py`, `params_builder.py`, `pipeline.py`, `params_schema.py`. The `__init__.py` already re-exports from `api.py`. This double indirection adds no value.

### LOW

**DC-L1. `profiles/io.py:316-317` -- aliases `load_processed_profile` and `save_processed_profile`**
- These are documented as "split-architecture aliases" but add indirection with no clear consumer.

**DC-L2. `spectral_upsampling.py:399` -- `MALLETT2019_BASIS` is a module-level copy that may not be needed at import time**
- **File:** `src/spektrafilm/utils/spectral_upsampling.py:399`

**DC-L3. `lut.py:159-185` -- `if __name__ == '__main__':` block is 170+ lines of benchmarks**
- **File:** `src/spektrafilm/utils/lut.py:649-838`
- Same pattern in `fast_interp.py:119-183`, `fast_gaussian_filter.py:355-414`, `numba_boost_hightlights.py:128-165`, `autoexposure.py:239-245`.
- **Fix:** Move benchmark code to a dedicated benchmark script or test.

**DC-L4. `fast_gaussian_filter.py:296-309` -- `_EXPONENTIAL_GAUSSIAN_FITS` placeholder comment**
- "Placeholder fits, to be refined" -- should be tracked as an issue.

**DC-L5. `config.py:6` -- `LOG_EXPOSURE` constant appears unused**
- **File:** `src/spektrafilm/config.py:6`
- `LOG_EXPOSURE = np.linspace(-3,4,256)` -- no grep hits in src/ for `LOG_EXPOSURE` usage.

**DC-L6. `process.py:7` -- `from spektrafilm.gpu.metal_serialization import serialized_metal_runtime`**
- Imported at module level but only used conditionally. Could be a lazy import.

---

## 4. Code Duplication

### HIGH

**CD-H1. `_prepare_hdr_rgb` validation duplicated across `hdr_photo.py` and `io.py`**
- **File:** `src/spektrafilm/utils/hdr_photo.py:320-332` and `src/spektrafilm/utils/io.py:624-632`
- Both validate image shape, dtype, finiteness, and channel count. The `save_image_oiio` HEIC branch performs its own validation before calling `save_hdr_photo_heic` which validates again via `_prepare_hdr_rgb`.

**CD-H2. `luminance_y` duplicated: `hdr_photo.py` imports from `hdr_curve_profiles.py` but `pipeline.py` computes it inline**
- **File:** `src/spektrafilm/runtime/pipeline.py:187-191`
- `look_y = np.tensordot(look_rgb[0, :, :3], np.array([0.2126, 0.7152, 0.0722], ...))` -- this is the same BT.709 luma formula as `luminance_y()` in `hdr_curve_profiles.py`.
- **Fix:** Use `luminance_y()` from `hdr_curve_profiles.py` in `pipeline.py`.

**CD-H3. RGB-to-XYZ luminance computation duplicated in `pipeline.py` and `autoexposure.py`**
- **File:** `src/spektrafilm/runtime/pipeline.py:76-100` and `src/spektrafilm/utils/autoexposure.py:22-34`
- Both compute scene luminance via `colour.RGB_to_XYZ` with nearly identical fallback logic. `_scene_luminance_y` in pipeline.py falls back to Rec.709 luma; `_luminance_y` in autoexposure.py doesn't.
- **Fix:** Extract a shared `scene_luminance_y(image, color_space, apply_cctf_decoding)` utility.

### MEDIUM

**CD-M1. `profile_to_dict` and `_json_safe` do similar recursive serialization**
- **File:** `src/spektrafilm/profiles/io.py:218-228` and `src/spektrafilm/profiles/io.py:230-241`
- Both recursively walk dataclass/dict/list/tuple trees. `_json_safe` adds NaN->None handling.

**CD-M2. `_ICC_FILENAMES` and `_ICC_PROFILES` serve overlapping purposes**
- **File:** `src/spektrafilm/utils/io.py:171-191` and `src/spektrafilm/utils/io.py:230-239`
- Two separate dicts mapping color space names to ICC file paths. `_ICC_FILENAMES` is keyed by `(name, cctf_encoding)`, `_ICC_PROFILES` by `name` only. The lookup logic in `resolve_icc_profile_bytes` and `_known_encoding_from_icc_profile` tries both.
- **Fix:** Merge into a single data structure or document the distinction clearly.

**CD-M3. Diffusion filter shape configs defined as dicts rather than dataclasses**
- **File:** `src/spektrafilm/model/diffusion.py:197-254`
- `_DIFFUSION_FILTER_SHAPES` uses nested dicts with string keys. This duplicates the pattern of the `DiffusionFilterParams` dataclass in `params_schema.py`. Using dataclasses would catch typos at construction time.

**CD-M4. `Pipeline._preprocess_input_image` and `_preprocess_input_image_with_metadata` share 80% of code**
- **File:** `src/spektrafilm/runtime/pipeline.py:547-570`
- The only difference is that the metadata variant also calls `_hdr_scene_energy_metadata` and `characterize_pipeline_profile`.
- **Fix:** Make `_preprocess_input_image` call `_preprocess_input_image_with_metadata` and discard the metadata.

**CD-M5. GPU backend `__init__` validation patterns duplicated across `CupyBackend` and `MlxBackend`**
- **File:** `src/spektrafilm/gpu/cupy_backend.py:16-41` and `src/spektrafilm/gpu/mlx_backend.py:19-47`
- Both check precision, import the library, probe the device, and raise `BackendUnavailableError`. Pattern could be extracted to a base class or factory.

---

## 5. API Consistency

### HIGH

**API-H1. `save_image_oiio` docstring documents parameters that don't exist in the signature**
- **File:** `src/spektrafilm/utils/io.py:549-599`
- The docstring's "Parameters" section documents `scene_luminance`, `scene_rgb`, `hdr_mapping_kwargs`, and `exr_mode` -- these were added to the signature in round 3 fixes. However, the docstring still says "the implementation treats HEIC as a controller-level special case" (from M4 in functional review). The docstring should be updated to reflect the current API.

**API-H2. `Pipeline.__init__` calls `__init__` recursively via `update`**
- **File:** `src/spektrafilm/runtime/pipeline.py:502-504`
- `def update(self, params): self.__init__(params, update_params=True)` -- this is an anti-pattern. Re-calling `__init__` on an existing instance is fragile (e.g., if subclasses override `__init__`, if `__init__` has side effects). Should use a separate `_reinit` method or rebuild the pipeline.

**API-H3. `Pipeline.soft_update` directly mutates sub-objects**
- **File:** `src/spektrafilm/runtime/pipeline.py:506-535`
- Accesses `self.camera.exposure_compensation_ev`, `self.enlarger.print_exposure`, etc. directly. If the sub-objects are frozen dataclasses, this will raise. If they're mutable, changes aren't tracked.
- **Fix:** Use `dataclasses.replace` on the params and call `update`.

**API-H4. `Pipeline._pipeline_print` and `_pipeline_scan_film` delete intermediate arrays with `del`**
- **File:** `src/spektrafilm/runtime/pipeline.py:575-595`
- `del rgb_image`, `del log_raw_film`, etc. -- this is manual memory management that fights Python's GC. The `del` statements don't guarantee immediate deallocation and make the code harder to read. The intent (memory pressure for large images) is valid but the execution is fragile.

### MEDIUM

**API-M1. `compute_with_lut` returns inconsistent tuple lengths**
- **File:** `src/spektrafilm/utils/lut.py:60-126`
- Returns `(output, lut)` by default, but `(output, lut, prepared_lut)` when `return_prepared=True`. Callers must unpack differently based on a flag.
- **Fix:** Always return a 3-tuple with `prepared_lut=None` when not requested, or use a dataclass.

**API-M2. `hdr_photo_color_space` silently falls back to `Display P3`**
- **File:** `src/spektrafilm/utils/hdr_photo.py:239-244`
- If the input color space isn't in `SUPPORTED_HDR_PHOTO_COLOR_SPACES`, it silently returns `"Display P3"`. This could surprise callers who pass e.g. `"Adobe RGB"` expecting an error.
- **Fix:** Raise `ValueError` for unsupported color spaces, or at least log a warning.

**API-M3. `Profile.update` uses keyword args `info=None, data=None` but `update_info`/`update_data` use `**changes`**
- **File:** `src/spektrafilm/profiles/io.py:142-155`
- `update_info(**changes)` passes kwargs to `dataclasses.replace`, while `update(info={...})` passes a dict. The two patterns are inconsistent.

**API-M4. `SimulationPipelineResult` has `hdr_scene_energy` field but the name doesn't match `HDRSceneEnergyMetadata`**
- **File:** `src/spektrafilm/runtime/pipeline.py:47-51`
- The field is `hdr_scene_energy` but the type is `HDRSceneEnergyMetadata`. The "scene_energy" vs "scene_energy" naming is consistent, but the field could be more descriptive: `hdr_metadata` or `scene_energy_metadata`.

**API-M5. `save_image_oiio` returns `()` (empty tuple) for non-HDR paths**
- **File:** `src/spektrafilm/utils/io.py:689,759`
- Returns `()` which is a valid `tuple[str, ...]` but semantically confusing. Callers must check `if hdr_diagnostics:` rather than `if hdr_diagnostics is not None:`.

**API-M6. `characterize_pipeline_profile` is a module-level function that takes a `SimulationPipeline`**
- **File:** `src/spektrafilm/runtime/pipeline.py:164`
- It accesses `pipeline._params` (private) and creates a temporary pipeline. This is tightly coupled to the pipeline internals.
- **Fix:** Make it a method on `SimulationPipeline`.

**API-M7. `diffusion.py` exposes both `apply_diffusion_filter_mm` (legacy) and `apply_diffusion_filter_um` (current)**
- **File:** `src/spektrafilm/model/diffusion.py:110,557`
- The `_mm` variant takes a tuple `diffusion_filter_params` while the `_um` variant takes a `DiffusionFilterParams` dataclass. The `_mm` variant is used in one place (`filming.py`).

---

## 6. Test Coverage Gaps

### CRITICAL

**TC-C1. No tests for `Pipeline.soft_update` behavior**
- **File:** `src/spektrafilm/runtime/pipeline.py:506-535`
- `soft_update` mutates internal state and recomputes `density_spectral_midgray`. No test verifies:
  - Parameters are actually updated
  - Dependent state is recomputed
  - Subsequent `process()` calls use the updated values
  - Invalid parameter names are rejected (currently silently ignored)

### HIGH

**TC-H1. No tests for GPU tiling logic**
- **File:** `src/spektrafilm/runtime/pipeline.py:393-430`
- `_process_with_gpu_tiles`, `_tile_core_rows`, `_tile_overlap_pixels` have no dedicated tests. The tiling logic is complex (overlap computation, strip cropping) and error-prone.

**TC-H2. No tests for `hdr_photo_color_space` fallback behavior**
- **File:** `src/spektrafilm/utils/hdr_photo.py:239-244`
- Silent fallback to Display P3 is untested.

**TC-H3. No tests for `build_iso_21496_1_gain_map_metadata` or `encode_gain_map_log2`**
- **File:** `src/spektrafilm/utils/hdr_photo.py:1020-1100`
- ISO 21496-1 gain map metadata construction and encoding are untested.

**TC-H4. No tests for `build_gain_map_xmp_packet` XMP generation**
- **File:** `src/spektrafilm/utils/hdr_photo.py:1103-1152`
- XMP string construction with f-strings could have formatting bugs.

**TC-H5. No tests for diffusion filter warmth redistribution**
- **File:** `src/spektrafilm/model/diffusion.py:347-392`
- `_halo_channel_weights` energy conservation property (sum(weights) preserved for any warmth) is untested.

### MEDIUM

**TC-M1. No tests for `measure_gamma` or `measure_slopes_at_exposure`**
- **File:** `src/spektrafilm/utils/measure.py:6-26`
- Calibration measurement functions are untested.

**TC-M2. No tests for `measure_density_min` curve fitting**
- **File:** `src/spektrafilm/utils/measure.py:28-96`
- Complex curve fitting with `least_squares` is untested.

**TC-M3. No tests for `crop_image` boundary conditions**
- **File:** `src/spektrafilm/utils/crop_resize.py:4-28`
- Edge cases: crop extends beyond image bounds, very small crops, zero-size crops.

**TC-M4. No tests for `_strength_to_scatter` interpolation**
- **File:** `src/spektrafilm/model/diffusion.py:283-300`
- Strength-to-scatter mapping uses log2 interpolation on a breakpoint table. Boundary values and extrapolation are untested.

**TC-M5. No tests for `locked_logistic_rising` mathematical properties**
- **File:** `src/spektrafilm/utils/spectral_upsampling.py:315-335`
- The function has specific mathematical properties (passes through (mu, 0.5), max slope = 1/(sigma*sqrt(2*pi))) that should be verified.

**TC-M6. No tests for `_radial_mobius_warp_xy`**
- **File:** `src/spektrafilm/utils/spectral_upsampling.py:281-294`

**TC-M7. No tests for `poly2d_deg3`**
- **File:** `src/spektrafilm/utils/spectral_upsampling.py:297-313`

**TC-M8. No tests for `tiled_processing` in `gpu/backend.py`**
- **File:** `src/spektrafilm/gpu/backend.py:116-194`
- Complex tiling logic with overlap, stride, and coverage verification.

### LOW

**TC-L1. No tests for `warmup_*` functions**
- `warmup_luts`, `warmup_fast_interp`, `warmup_fast_gaussian_filter`, `warmup_boost_highlights`, `warmup_fast_stats` -- these are utility functions that trigger JIT compilation. Low risk but untested.

**TC-L2. No tests for `format_timings` edge cases**
- Empty timings dict, single timing, very large/small values.

**TC-L3. No tests for `SpectralInputPolicy` validation**
- **File:** `src/spektrafilm/utils/spectral_upsampling.py:28-39`

**TC-L4. No tests for `Profile.clone`, `update_info`, `update_data`, `update`**
- **File:** `src/spektrafilm/profiles/io.py:139-155`

---

## 7. Performance Anti-patterns

### HIGH

**PF-H1. `Pipeline.__init__` deep-copies entire params on every call**
- **File:** `src/spektrafilm/runtime/pipeline.py:199`
- `self._params = copy.deepcopy(params)` -- `RuntimePhotoParams` contains numpy arrays in `Profile.data`. Deep-copying these arrays on every pipeline construction (including `update` which re-calls `__init__`) is expensive.
- **Fix:** Only deepcopy the mutable parts, or use copy-on-write for numpy arrays.

**PF-H2. `characterize_pipeline_profile` creates a temporary pipeline on every call**
- **File:** `src/spektrafilm/runtime/pipeline.py:164-192`
- Creates a full `SimulationPipeline` copy, runs a 512-pixel ramp through it, and discards it. This is called in `_preprocess_input_image_with_metadata` which runs on every preview/scan.
- **Fix:** Cache the characterization result for a given (film, paper, settings) combination.

**PF-H3. `_paper_logistic_progress` allocates a full output array even when `above` mask is sparse**
- **File:** `src/spektrafilm/utils/hdr_photo.py:340-374`
- `out = np.zeros_like(y)` allocates for the full image, then only fills `out[above]`. For images with few bright pixels, this wastes memory.

### MEDIUM

**PF-M1. `apply_lut_cubic_3d` forces `np.float64` on LUT**
- **File:** `src/spektrafilm/utils/fast_interp_lut.py:198`
- `lut = np.ascontiguousarray(lut, dtype=np.float64)` -- forces float64 even when the pipeline runs in float32. This doubles memory usage for the LUT and all intermediate arrays.

**PF-M2. `fast_gaussian_filter` copies image per channel**
- **File:** `src/spektrafilm/utils/fast_gaussian_filter.py:258`
- `ch_in = np.ascontiguousarray(image[:, :, ch])` -- creates a contiguous copy of each channel slice. If the image is already contiguous (C-order), the slice `[:, :, ch]` is not contiguous, forcing a copy.

**PF-M3. `Pipeline._pipeline_print` creates 6 intermediate arrays**
- **File:** `src/spektrafilm/runtime/pipeline.py:584-595`
- Each stage produces a new array: `log_raw_film`, `cmy_film`, `log_raw_print`, `cmy_print`, `rgb_scan`. For a 50MP image at float32, each is ~600MB. The `del` statements hint at memory pressure but don't actually free memory immediately.

**PF-M4. `diffusion_filter_psf` builds PSF with Python loops**
- **File:** `src/spektrafilm/model/diffusion.py:514-554`
- The `_exp_sum` helper uses a Python `for` loop over Gaussian components. For large PSFs (radius 100+), this is slow. Could be vectorized.

**PF-M5. `_halo_channel_weights` builds output array in Python loop**
- **File:** `src/spektrafilm/model/diffusion.py:383-392`
- `for c in range(3):` with numpy operations inside. Could be vectorized to operate on all 3 channels at once.

### LOW

**PF-L1. `fast_interp_lut.py:250-305` -- `_prepare_lut_pchip_3d_impl` uses nested Python loops**
- Triple-nested loops over LUT dimensions. For a 32x32x32 LUT, this is 32K iterations. Numba `@njit` is used but the function has no `parallel=True`.

**PF-L2. `autoexposure.py:140-153` -- `_matrix_luminance` builds zone lists in Python**
- Uses Python lists and `append` in a double loop. Could be vectorized with numpy reshaping.

**PF-L3. `spectral_upsampling.py:195-199` -- `_fetch_coeffs` uses `np.apply_along_axis`**
- `np.apply_along_axis` is a Python-level loop over slices. For large images, this is slow.

---

## 8. Security Concerns

### HIGH

**SC-H1. `hdr_photo.py:298-304` -- `subprocess.run` with user-influenced arguments**
- **File:** `src/spektrafilm/utils/hdr_photo.py:298`
- The `command` list includes `str(output_path)` which comes from the user's save dialog. While `subprocess.run` with a list is safe against shell injection, the path is not validated for suspicious characters.
- **Risk:** Low on Linux (no shell interpretation), but the Swift encoder script path is from `importlib.resources` which is safe.

### MEDIUM

**SC-M1. `io.py:864-868` -- `save_neutral_print_filters` writes to package resources**
- **File:** `src/spektrafilm/utils/io.py:864`
- Writing to `importlib.resources` paths may modify installed package files. In a production deployment this could corrupt the installation.

**SC-M2. `profiles/io.py:293-302` -- `save_profile` writes to package resources**
- **File:** `src/spektrafilm/profiles/io.py:293`
- Same concern as SC-M1. The `_validate_stock_name` regex prevents path traversal, but writing to package data is still risky.

**SC-M3. `load_dichroic_filters` and `load_filter` use user-provided names in file paths**
- **File:** `src/spektrafilm/utils/io.py:894-926`
- `brand`, `name`, `filter_type` are validated by `_validate_path_component` (alphanumeric + hyphens/underscores only), which prevents path traversal. This is good.

### LOW

**SC-L1. `io.py:884` -- `_SAFE_PATH_COMPONENT_RE` allows hyphens and underscores**
- **File:** `src/spektrafilm/utils/io.py:884`
- Pattern `^[A-Za-z0-9_-]+$` is safe for path components. No concern.

**SC-L2. `json.dump` with `allow_nan=False` in `save_profile`**
- **File:** `src/spektrafilm/profiles/io.py:302`
- This is correct -- prevents NaN values from producing invalid JSON.

---

## Prioritized Action List

### Must fix (correctness/robustness):

1. **TC-C1**: Add tests for `Pipeline.soft_update` -- critical untested mutation path
2. **API-H2**: Refactor `Pipeline.update` to not re-call `__init__`
3. **CD-H2**: Use `luminance_y()` consistently instead of inline BT.709 luma
4. **EH-M5**: Check `least_squares` convergence in `measure.py`
5. **DC-H1**: Remove all commented-out code blocks

### Should fix soon (quality/maintainability):

1. **TH-H1-H5**: Add return type annotations to `Pipeline` and `Simulator` public methods
2. **CD-H3**: Extract shared `scene_luminance_y` utility
3. **PF-H2**: Cache `characterize_pipeline_profile` results
4. **EH-H3**: Narrow exception catches in `pipeline.py:567`
5. **TC-H1-H5**: Add tests for GPU tiling, HDR metadata, diffusion warmth

### Nice to have (polish):

1. **TH-M1-M12**: Systematic type annotation pass across all modules
2. **DC-M1-M8**: Clean up commented-out code and stale comments
3. **PF-M1-M5**: Optimize float64 forcing and per-channel copies
4. **API-M1-M7**: Standardize return types and naming conventions

---

## Test Suite Status

All 398 non-GUI tests pass (13 skipped, 11 warnings). No regressions detected.
