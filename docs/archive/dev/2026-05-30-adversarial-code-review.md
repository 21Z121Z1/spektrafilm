# Adversarial Code Review Report — Spektrafilm

**Date:** 2026-05-30
**Branch:** develop
**Method:** 6-lens adversarial attack (correctness, security, performance, edge-cases, architecture, testing) with independent skeptical verification.

---

## Executive Summary

| Severity | Count |
|----------|-------|
| Critical | 0 |
| High | 0 |
| Medium | 12 |
| Low | 11 |
| **Total**| **23**|

---

## Medium Findings

### M1. `MlxBackend.nan_to_num` does not replace inf values

**File:** `/Users/retriedstormtrooper/Documents/spektrafilm-main/src/spektrafilm/gpu/mlx_backend.py`
**Lines:** 120-121
**Lens:** correctness

`nan_to_num` uses `self.mx.where(self.mx.isnan(x), nan, x)`, which only replaces NaN. It leaves `+inf` and `-inf` values untouched. The NumPy backend's `np.nan_to_num` replaces NaN, +inf, and -inf. Downstream code in `autoexposure.py` (line 28) calls `np.nan_to_num(image_Y, nan=0.0, posinf=0.0, neginf=0.0)` expecting all non-finite values to be zeroed. On the MLX backend, inf values would propagate through `log2`, `sum`, and `dot` calls, producing incorrect autoexposure results. The same issue exists in `CupyBackend.nan_to_num` at line 107-108.

**Fix:** In `MlxBackend.nan_to_num`, also replace `+inf` and `-inf`: `return self.mx.where(self.mx.isnan(x), nan, self.mx.where(self.mx.isinf(x), 0.0, x))`. Similarly fix `CupyBackend`.

**Verification:** The MLX backend's `nan_to_num` at line 120-121 genuinely only replaces NaN and leaves `+inf`/`-inf` untouched, unlike all other backends (NumPy, CuPy, Halide) which delegate to `np.nan_to_num`/`cp.nan_to_num` and handle inf by default. The bug is real for the MLX path. However, the finding overstates in two ways: (a) the CuPy backend does NOT have the same issue -- `cp.nan_to_num(x, nan=nan)` replaces inf with large finite numbers by default, and (b) the autoexposure.py connection is a red herri

### M2. `HalideBackend.cctf_encode` uses `hl.fast_pow` which trades precision for speed

**File:** `/Users/retriedstormtrooper/Documents/spektrafilm-main/src/spektrafilm/gpu/halide_backend.py`
**Lines:** 591
**Lens:** correctness

The sRGB CCTF encode kernel uses `hl.fast_pow(v, 1.0 / gamma_p)` (line 591). Halide's `fast_pow` is an approximation with reduced precision compared to `hl.pow`. The project's GPU precision constraint (CLAUDE.md) requires "numerically identical (or within float32 epsilon) to CPU/NumPy output." The `fast_pow` approximation can introduce errors significantly larger than float32 epsilon (~1e-7), particularly for values near the piecewise threshold (0.0031308). The corresponding `cctf_decode` correctly uses `hl.pow` (line 651), so the encode/decode pair is asymmetric.

**Fix:** Change `hl.fast_pow` to `hl.pow` on line 591 for consistency and precision compliance.

**Verification:** The code at line 591 indeed uses `hl.fast_pow(v, 1.0 / gamma_p)` while the decode at line 651 uses `hl.pow(...)`. The asymmetry is real and `fast_pow` is a documented approximation. However, there are significant mitigating factors that reduce the severity: (1) The production pipeline does NOT call `backend.cctf_encode()` or `backend.cctf_decode()` -- production code routes through `cctf_encoding_backend()` in `color.py` which uses `_signed_power` -> `backend.pow()` -> `np.power()` (full-precisi

### M3. No pickle, yaml.load, eval/exec, or unsafe deserialization found

**File:** `N/A`
**Lines:** N/A
**Lens:** security

The codebase does not use pickle, yaml.load (no PyYAML import at all), Python eval/exec for code execution, or any other unsafe deserialization mechanism. The `GainMapMetadata.deserialize()` uses safe `struct.unpack_from()` on binary data. JSON loading (`json.load()`) is used safely with type-checked dict access patterns. No `marshal`, `shelve`, or `dill` usage was found.

**Fix:**

**Verification:** Thorough search confirms no pickle, yaml.load, Python eval/exec, marshal, shelve, dill, or any other unsafe deserialization mechanism exists in the codebase. The `struct.unpack_from()` usage is safe fixed-format binary parsing. The `json.load()` usage follows standard safe patterns. The `eval` hits are MLX/backend API calls, not Python's eval() builtin.
ADJUSTED_SEVERITY: KEEP

### M4. `save_profile` crashes when `stock` is None (default)

**File:** `/Users/retriedstormtrooper/Documents/spektrafilm-main/src/spektrafilm/profiles/io.py`
**Lines:** 334-336
**Lens:** edge-cases

`ProfileInfo.stock` defaults to `None`. Calling `save_profile` on a freshly-constructed Profile does `profile.info.stock = profile.info.stock + suffix`, which is `None + ''` -- a TypeError.

**Consequence:** crash

**Fix:** Guard with `if profile.info.stock is None: raise ValueError("profile.info.stock must be set before saving")` at the top of `save_profile`.

**Verification:** Line 92 defines `stock: str = None` so `ProfileInfo()` has `stock=None`. Line 336 does `profile.info.stock + suffix` with no None guard -- `None + ''` raises `TypeError`. The function is a public API (`__all__`, aliased as `save_processed_profile`). While in normal workflow profiles are loaded via `load_profile` which always populates `stock`, any caller constructing a `Profile`/`ProfileInfo` from scratch and calling `save_profile` without explicitly setting `stock` first will get an opaque `Typ

### M5. `_json_safe` does not handle Infinity values

**File:** `/Users/retriedstormtrooper/Documents/spektrafilm-main/src/spektrafilm/profiles/io.py`
**Lines:** 276-287, 342
**Lens:** edge-cases

`_json_safe` converts NaN floats to None but does not convert Inf or -Inf. When `save_profile` calls `json.dump(..., allow_nan=False)`, any Infinity value in the profile data raises `ValueError: Out of range float values are not JSON compliant`.

**Consequence:** crash

**Fix:** Extend the float check at line 285 to also handle `np.isinf(data)`, converting Inf to `None` (or a large finite sentinel).

**Verification:** The code at lines 276-287 clearly shows that `_json_safe` handles NaN (line 285-286: `if isinstance(data, float) and np.isnan(data): return None`) but has no equivalent check for `math.isinf(data)` or `np.isinf(data)`. Line 342 explicitly passes `allow_nan=False` to `json.dump`, which will raise `ValueError` on any Infinity or -Infinity value. The gap is real: the NaN guard exists but the Inf guard is missing. In practice, spectral computation profiles could contain Inf values from division-by-z

### M6. `crop_image` produces wrong results when crop size exceeds image dimensions

**File:** `/Users/retriedstormtrooper/Documents/spektrafilm-main/src/spektrafilm/utils/crop_resize.py`
**Lines:** 4-28
**Lens:** edge-cases

When `size` fraction produces `sz` larger than `shape`, the correction `x0[0] = shape[0]-sz[0]` yields a negative value (after the earlier `x0[x0<0] = 0` clip). The numpy slice `image[negative_start:negative_start+sz]` returns an empty or incorrectly-sized array because numpy interprets out-of-bounds slicing differently from the intended crop.

**Consequence:** wrong result

**Fix:** Clamp `sz` to `min(sz, shape)` before computing `x0`, or add `if sz[0] > shape[0]: sz[0] = shape[0]` (and similarly for axis 1).

**Verification:** The code at lines 25-26 sets `x0[i] = shape[i] - sz[i]` which is negative when `sz[i] > shape[i]`. NumPy interprets the negative slice start as counting from the array end, producing a crop of wrong size and wrong position with no error raised. This triggers for any non-square image when `size` fraction exceeds the short/long aspect ratio (e.g., `size >= 0.57` for 16:9 images, `size=1.0` always triggers). The default `size=(0.1, 0.1)` avoids the bug, limiting practical impact.
ADJUSTED_SEVERITY:

### M7. `RuntimePhotoParams.__post_init__` validates only type, not parameter ranges

**File:** `/Users/retriedstormtrooper/Documents/spektrafilm-main/src/spektrafilm/runtime/params_schema.py`
**Lines:** 216-220
**Lens:** edge-cases

Only `film` and `print` type checks exist. No validation for: `film_format_mm > 0` (line 49), `upscale_factor > 0` (line 172), `print_exposure > 0` (line 58), `lut_resolution >= 2` (line 196), `n_sub_layers >= 1` (line 95), `white_level > black_level` in ScannerParams (lines 78-79). A zero or negative `film_format_mm` makes `pixel_size_um` zero or negative, causing division-by-zero in all spatial filters. A zero `n_sub_layers` causes division-by-zero in `grain.py` line 97.

**Consequence:** crash or silent corruption

**Fix:** Add `@property` validators or a `__post_init__` on the relevant dataclasses. At minimum: `film_format_mm` must be > 0, `upscale_factor` must be > 0, `n_sub_layers` must be >= 1, `lut_resolution` must be >= 2.

**Verification:** The code at lines 218-222 is exactly as described -- only two isinstance checks, zero range validation. The specific risks are real: `n_sub_layers=0` causes silent NaN corruption at grain.py line 109 (the finding incorrectly cites line 97 which IS guarded, but line 109 is unconditional); `film_format_mm=0` produces `pixel_size_um=0` leading to inf values in all spatial filters; `upscale_factor=0` similarly produces division by zero in resize.py line 24. All defaults are safe, so this requires de

### M8. `apply_grain_to_density_layers` mutates the input array in-place

**File:** `/Users/retriedstormtrooper/Documents/spektrafilm-main/src/spektrafilm/model/grain.py`
**Lines:** 120-151
**Lens:** edge-cases

Line 151 `density_cmy_layers += density_min_layers` modifies the caller's array. The non-layer variant `apply_grain_to_density` (line 99) correctly calls `.copy()`, but the layers variant does not. The caller `apply_grain` (line 201-207) passes `density_cmy_layers` from `interp_density_cmy_layers`, and after this mutation the array is permanently altered -- if the caller retains a reference, subsequent operations see corrupted data.

**Consequence:** silent corruption

**Fix:** Add `density_cmy_layers = density_cmy_layers.copy()` at the top of `apply_grain_to_density_layers`.

**Verification:** The in-place mutation is real. At line 143 (the finding says line 151, but the actual line is 143), `density_cmy_layers += density_min_layers` mutates the numpy array passed as the first argument. The non-layer variant `apply_grain_to_density` at line 99 correctly does `density_cmy = density_cmy.copy()` before its `+=` at line 100. The layer variant skips this copy. The sole production caller `apply_grain` (line 200) creates `density_cmy_layers` locally via `interp_density_cmy_layers`, passes it

### M9. `scanning.py` always clips output ignoring `output_clip_min`/`output_clip_max` flags

**File:** `/Users/retriedstormtrooper/Documents/spektrafilm-main/src/spektrafilm/runtime/stages/scanning.py`
**Lines:** 117-126
**Lens:** edge-cases

`_apply_cctf_encoding_and_clip` unconditionally calls `np.clip(rgb, a_min=0, a_max=1)`. The `IOParams` dataclass defines `output_clip_min: bool = True` and `output_clip_max: bool = True` (params_schema.py lines 167-168) but these flags are never consulted. Users who set `output_clip_min=False` or `output_clip_max=False` expecting unclamped output still get clipped results.

**Consequence:** wrong result

**Fix:** Replace the unconditional clip with `if self._io.output_clip_min: rgb = np.maximum(rgb, 0)` and `if self._io.output_clip_max: rgb = np.minimum(rgb, 1)`.

**Verification:** The code at lines 117-126 of `scanning.py` unconditionally calls `np.clip(rgb, a_min=0, a_max=1)` at line 126. The `IOParams` dataclass at `params_schema.py:167-168` defines `output_clip_min: bool = True` and `output_clip_max: bool = True`, and these flags are properly read in `color_management.py:174-175` via `getattr(io, "output_clip_min", True)` to set `clip_negatives`/`clip_highlights` on the `ColorEncoding` object. However, `scanning.py` has access to `self._io` (the `IOParams` instance) bu

### M10. ColorReferenceService uses cross-stage mutable communication via set-once attributes

**File:** `/Users/retriedstormtrooper/Documents/spektrafilm-main/src/spektrafilm/runtime/services/color_reference.py`
**Lines:** 34-37
**Lens:** architecture

`ColorReferenceService.__init__` sets `self.cmy_to_log_xyz = None` and `self.log_raw_print_black = None`. These are later set by `ScanningStage.__init__` (line 42 of scanning.py: `self._color_reference_service.cmy_to_log_xyz = self.cmy_to_log_xyz`) and `PrintingStage.expose` (lines 45-46 of printing.py: `self._color_reference_service.log_raw_print_black = ...`). The service depends on external code injecting these values before they are used, with no validation or error if they remain None.

**Impact:** If the pipeline stages are reordered or a stage is skipped, `cmy_to_log_xyz` stays None and `_update_cmy_black_white_references` will call `None(cmy_black)` raising `TypeError` with no useful context. This is a classic temporal coupling.

**Fix:** Either pass `cmy_to_log_xyz` as a constructor argument, or have `ColorReferenceService` accept a reference to the scanning stage. At minimum, raise a descriptive error if these are None when accessed.

**Verification:** The code at lines 34-37 does set `self.cmy_to_log_xyz = None`, `self.log_raw_print_black = None`, and `self.log_raw_print_white = None`. ScanningStage.__init__ injects `cmy_to_log_xyz` at scanning.py:44, and PrintingStage.expose injects the other two at printing.py:47-48. These are public mutable attributes with no validation, type checking, or sentinel guards -- if the service methods that consume them (`_update_cmy_black_white_references`, lines 50-51/56/62/67-68) were ever called before injec

### M11. GPU pipeline test checks only shape and finiteness, not correctness

**File:** `/Users/retriedstormtrooper/Documents/spektrafilm-main/tests/test_gpu_pipeline.py`
**Lines:** 22-36, 39-57
**Lens:** testing

test_pipeline_processes_small_image_with_mlx_backend and test_pipeline_processes_small_image_with_mlx_lut_backend only assert shape, finiteness, and range [0,1]. They never compare the GPU pipeline output to a CPU reference. The test would pass even if the GPU path produced completely wrong colors (e.g., swapped channels, inverted values, or all zeros).
MISSED_BUG: A regression in the MLX backend (wrong kernel, incorrect dtype casting, broken LUT sampling) would silently pass because the test only checks structural properties. Any finite output in [0,1] passes.

**Missed bug:** A regression in the MLX backend (wrong kernel, incorrect dtype casting, broken LUT sampling) would silently pass because the test only checks structural properties. Any finite output in [0,1] passes.

**Fix:** Add np.testing.assert_allclose(result, cpu_reference_result, atol=1e-5) where cpu_reference_result is computed via the CPU backend with identical params.

**Verification:** The two tests (lines 22-36 and 39-57) genuinely lack CPU reference comparisons. They only assert shape, finiteness, and range [0,1]. A pipeline orchestration bug (e.g., wrong stage ordering, incorrect inter-stage data flow) would not be caught. However, the severity is overstated: individual GPU kernels (LUT, density, filters) ARE tested for numerical correctness against CPU references in test_gpu_lut.py, test_gpu_density.py, and test_gpu_filters.py. The gap is limited to pipeline-level integrat

### M12. Missing test for grain with blur > 0

**File:** `/Users/retriedstormtrooper/Documents/spektrafilm-main/tests/test_grain.py`
**Lines:** 46-52
**Lens:** testing

test_apply_grain_fixed_seed_is_usable calls apply_grain_to_density with grain_blur=0.0 only. No test exercises the blur code path (grain_blur > 0). The test_apply_grain_matches_layered_pipeline also uses blur=0.0. The blur path involves gaussian filtering of the grain noise, which is a separate code path that is never tested.
MISSED_BUG: A bug in the grain blur implementation (wrong sigma, wrong axis, wrong padding mode) would escape undetected because every test disables blur.

**Missed bug:** A bug in the grain blur implementation (wrong sigma, wrong axis, wrong padding mode) would escape undetected because every test disables blur.

**Fix:** Add a test with grain_blur=0.65 and blur_dye_clouds_um=1.0 that asserts the result differs from the no-blur case, is finite, and has expected shape.

**Verification:** Every test in test_grain.py sets blur to 0.0. I verified all four tests that exercise grain: test_apply_grain_fixed_seed_is_usable (line 49, grain_blur=0.0), test_apply_grain_to_density_does_not_mutate_input (line 58, grain_blur=0.0), test_apply_grain_matches_single_layer_pipeline (line 105, blur=0.0), and test_apply_grain_matches_layered_pipeline (line 152, blur=0.0, blur_dye_clouds_um=0.0). The grain source code has three separate blur code paths: `apply_grain_to_density` lines 112-114 applies

---

## Low Findings

### L1. _remove_sRGB_cctf creates 3-element array just to get a scalar

**File:** `/Users/retriedstormtrooper/Documents/spektrafilm-main/src/spektrafilm/runtime/services/color_reference.py`
**Lines:** 168-174
**Lens:** performance

`_remove_sRGB_cctf()` multiplies the scalar input by `np.ones((1,1,3))` to create a 3-element array, passes it through `colour.RGB_to_RGB()` (a full color space conversion pipeline), and then takes `.mean()` to get a scalar. This is called during `__init__` for `_black_level` and `_white_level`.

**Impact:** Creates a 1x1x3 array, runs a full colour library RGB_to_RGB conversion (matrix multiply, CCTF decode), and averages. Two calls during init. Negligible runtime cost but unnecessarily complex.

**Fix:** Use `colour.cctf.decode()` directly on the scalar value, or implement the sRGB gamma decode inline: `x <= 0.04045 ? x/12.92 : ((x+0.055)/1.055)^2.4`.

**Verification:** The code at lines 168-174 does exactly what the finding describes. `_remove_sRGB_cctf` multiplies a scalar by `np.ones((1,1,3))` to create a (1,1,3) array, passes it through the full `colour.RGB_to_RGB()` pipeline (sRGB-to-sRGB identity matrix with CCTF decoding), and takes `.mean()` to recover a scalar. It is called at lines 26-27 during `__init__` for both `_black_level` and `_white_level`. The operation could be replaced with `colour.cctf_decoding(y_input, 'sRGB')` directly on the scalar. How

### L2. `profile_from_dict` crashes on profiles with extra unknown keys

**File:** `/Users/retriedstormtrooper/Documents/spektrafilm-main/src/spektrafilm/profiles/io.py`
**Lines:** 257-261
**Lens:** edge-cases

`ProfileInfo(**info_payload)` raises `TypeError: __init__() got an unexpected keyword argument` if the JSON contains keys not defined in the `ProfileInfo` dataclass (e.g. a future profile version adds a new field). Same issue applies to `ProfileMetadata` and `ProfileData` construction.

**Consequence:** crash

**Fix:** Filter `info_payload` to only include keys present in `ProfileInfo.__dataclass_fields__` before unpacking, or add `**kwargs` to the dataclass constructors.

**Verification:** The code at lines 257-261 passes dicts directly to `ProfileMetadata(**dict(metadata_payload))`, `ProfileInfo(**info_payload)`, and `ProfileData(**dict(data_payload))`. All three are plain `@dataclass` classes (lines 77, 91, 117) with no custom `__init__` and no `**kwargs` — standard dataclass `__init__` rejects unknown keyword arguments with `TypeError`. The only filtering is removal of `LEGACY_PROFILE_INFO_KEYS` (line 254) from `info_payload` only, which strips *old* keys but does nothing for *

### L3. print() used for warnings in production code instead of logging

**File:** `/Users/retriedstormtrooper/Documents/spektrafilm-main/src/spektrafilm/runtime/params_builder.py`
**Lines:** 40-44
**Lens:** architecture

`apply_database_neutral_print_filters()` uses `print()` to emit a warning about missing neutral print filters. `params_builder.py` line 40-44 prints directly to stdout.

**Impact:** Warnings cannot be suppressed, filtered, or redirected. In a GUI or server context, stdout may be unavailable or unexpected. The codebase already uses `logging` in `utils/io.py` and `utils/hdr_curve_profiles.py` for the same kind of message.

**Fix:** Replace `print(f"Warning: ...")` with `logging.warning(...)` using `logging.getLogger(__name__)`.

**Verification:** The code at lines 40-44 does use `print()` to emit a warning string directly to stdout. The function is called from `digest_params()` (line 53) which is the main parameter preparation pipeline entrypoint. The project already uses the `logging` module in several sibling modules (`hdr_photo.py`, `io.py`, `gain_map_io.py`, `hdr_curve_profiles.py`), so this is inconsistent. However, the warning is gated behind `warn_missing=True` (default) and only fires on a missing database entry — a conditional p

### L4. Module-level side effects in model/color_filters.py -- filter objects instantiated at import time

**File:** `/Users/retriedstormtrooper/Documents/spektrafilm-main/src/spektrafilm/model/color_filters.py`
**Lines:** 111-121
**Lens:** architecture

Lines 111-121 instantiate 9 module-level objects (`dichroic_filters`, `thorlabs_dichroic_filters`, `edmund_optics_dichroic_filters`, `durst_digital_light_dicrhoic_filters`, `custom_dichroic_filters`, `schott_kg1_heat_filter`, `schott_kg3_heat_filter`, `schott_kg5_heat_filter`, `generic_lens_transmission`) at import time. Each `DichroicFilters()` and `GenericFilter()` constructor reads CSV files from disk via `importlib.resources`. The `color_enlarger` function (line 126) defaults `filters=custom_dichroic_filters`, binding to the module-level instance.

**Impact:** Importing `model.color_filters` triggers 9 disk reads and CSV parses even if none are needed. This slows down import time and makes tests slower. The default argument `filters=custom_dichroic_filters` is a mutable default bound at definition time, which is correct but non-obvious and couples the function to the module's import-time state.

**Fix:** Use lazy initialization (e.g., a `_get_custom_filters()` function with `@functools.lru_cache`) or move instantiation to a factory function.

**Verification:** The code is exactly as described. Lines 111-120 instantiate 9 module-level objects. 8 of the 9 constructors perform disk I/O at import time: `load_dichroic_filters` reads 3 CSV files per brand (c/m/y channels) via `importlib.resources`, and `load_filter` reads 1 CSV file each. The `custom_dichroic_filters` (brand='custom') is the only exception -- it calls `create_custom_filters()` which is pure math with no I/O. That's approximately 3*3 + 4 = 13 CSV file reads triggered on `import color_filters

### L5. SpectralLUTService has duplicate code paths for enlarger and scanner LUT computation

**File:** `/Users/retriedstormtrooper/Documents/spektrafilm-main/src/spektrafilm/runtime/services/spectral_lut_compute.py`
**Lines:** 99-173
**Lens:** architecture

`spectral_compute_enlarger` (lines 99-135) and `spectral_compute_scanner` (lines 137-173) are nearly identical methods with different cache attribute names (`enlarger_lut_memory`/`_enlarger_test_results_memory` vs `scanner_lut_memory`/`_scanner_test_results_memory`). The test-result cache pattern is copy-pasted.

**Impact:** Any bug fix or optimization must be applied twice. The test-result cache mechanism (computing a fixed input, comparing outputs to detect changes) is duplicated with different attribute names.

**Fix:** Extract a shared `_spectral_compute` method that takes the cache attributes as parameters, or use a dict keyed by cache name.

**Verification:** The two methods are verbatim identical in logic. Comparing `spectral_compute_enlarger` (lines 100-135) and `spectral_compute_scanner` (lines 138-173): the signatures, early-return for `not use_lut`, test-result computation, cache-hit check, `compute_with_lut` calls, cache-store, and `None` guard are all structurally identical. The only differences are the attribute names used for caching: `enlarger_lut_memory`/`_enlarger_test_results_memory` vs `scanner_lut_memory`/`_scanner_test_results_memory`

### L6. _debug_inject_pipeline returns None when inject_film_density_cmy is False

**File:** `/Users/retriedstormtrooper/Documents/spektrafilm-main/src/spektrafilm/runtime/pipeline.py`
**Lines:** 213-219
**Lens:** architecture

`_debug_inject_pipeline` only runs when `self.debug.inject_film_density_cmy` is True. If it's False (while `debug_mode == "inject"`), the method falls through and returns `None`.

**Impact:** Same as above -- silent None return.

**Fix:** Raise an error if `inject_film_density_cmy` is False when `debug_mode == "inject"`.

**Verification:** The code at lines 221-227 is factually correct as described. `_debug_inject_pipeline` has no fallback return path when `inject_film_density_cmy` is False, so it implicitly returns `None`, which propagates through `_pipeline_debug` (line 200) and `process()` (lines 107-108). Contrast with `_debug_output_pipeline` (lines 202-219) which always returns a valid result via its fallthrough at line 218-219. The `DebugParams` dataclass (params_schema.py:176-185) has no validation enforcing that `inject_f

### L7. test_measure_density_min convergence test does not verify the warning was issued

**File:** `/Users/retriedstormtrooper/Documents/spektrafilm-main/tests/test_edge_cases.py`
**Lines:** 213-227
**Lens:** testing

test_measure_density_min_warns_on_poor_fit enters a warnings.catch_warnings(record=True) block but never asserts that any warning was actually captured. The docstring says "Verify that measure_density_min issues a warning when fitting fails" but the test only checks result.shape == (3,). The warning may or may not be issued -- the test doesn't care.
MISSED_BUG: If the warning mechanism is broken (e.g., wrong warning category, wrong logger, or warning silenced by default filters), the test passes silently.

**Missed bug:** If the warning mechanism is broken (e.g., wrong warning category, wrong logger, or warning silenced by default filters), the test passes silently.

**Fix:** Assert len(recorded_warnings) > 0 or that any expected warning message is in str(recorded_warnings[0].message).

**Verification:** The code at lines 213-227 shows `warnings.catch_warnings(record=True)` without `as w:` binding (line 222), so captured warnings are discarded. The test only asserts `result.shape == (3,)` on line 226 and never checks if any warning was emitted. Furthermore, the actual `measure_density_min` function (measure.py:28-96) issues zero warnings — it uses `scipy.optimize.least_squares` which doesn't warn on poor convergence, and there is no `warnings.warn()` call anywhere in the function body. The test'

### L8. test_format_elapsed_time asserts only suffix, not exact values

**File:** `/Users/retriedstormtrooper/Documents/spektrafilm-main/tests/test_edge_cases.py`
**Lines:** 234-271
**Lens:** testing

test_microseconds, test_milliseconds, test_seconds only assert that the output string contains "us", "ms", or "s" respectively. They do not assert the numeric value. A formatter that returns "0.00 ms" for 5e-6 seconds would pass the test_microseconds test because it contains "ms" -- but the actual value is 5 microseconds, not 0 milliseconds. Only test_zero_seconds and test_large_value_high_precision check exact strings.
MISSED_BUG: A unit-conversion bug (e.g., displaying 0.005 as "5.00 us" instead of "5.00 ms") would pass because the test only checks for the presence of a unit suffix.

**Missed bug:** A unit-conversion bug (e.g., displaying 0.005 as "5.00 us" instead of "5.00 ms") would pass because the test only checks for the presence of a unit suffix.

**Fix:** Assert the full formatted string, e.g., assert "5.00" in result and "us" in result for 5e-6.

**Verification:** The tests for `test_microseconds`, `test_milliseconds`, `test_seconds`, `test_boundary_at_one_second`, and `test_boundary_at_one_millisecond` (lines 239-270) only assert the presence of a unit suffix, not the numeric value. A multiplier error within the correct branch (e.g., `seconds * 1e5` instead of `seconds * 1e6` for microseconds) would produce the wrong number but still pass because "us" appears in the result. The suffix check correctly validates unit selection/branching but cannot catch nu

### L9. test_color_reference TestRemoveCCTF has weak range assertions

**File:** `/Users/retriedstormtrooper/Documents/spektrafilm-main/tests/test_color_reference.py`
**Lines:** 73-85
**Lens:** testing

test_srgb_round_trip_is_close_to_identity asserts 0.1 < result < 0.6 for input 0.5. The sRGB CCTF decode of 0.5 is approximately 0.214 (linear). The assertion range [0.1, 0.6] is wide enough to accept completely wrong values. Similarly, test_white_level_decodes_to_near_one asserts 0.8 < result < 1.1 for input 1.0 (which should decode to exactly 1.0).
MISSED_BUG: A CCTF decode function that applies gamma 2.2 instead of sRGB (2.4 with threshold) would produce ~0.218 instead of ~0.214, passing the test. A function that returns the input unchanged (identity) would also pass since 0.5 is in [0.1, 0.6].

**Missed bug:** A CCTF decode function that applies gamma 2.2 instead of sRGB (2.4 with threshold) would produce ~0.218 instead of ~0.214, passing the test. A function that returns the input unchanged (identity) would also pass since 0.5 is in [0.1, 0.6].

**Fix:** Assert tighter bounds, e.g., 0.20 < result < 0.22 for sRGB decode of 0.5, and np.testing.assert_allclose(result, 1.0, atol=0.01) for decode of 1.0.

**Verification:** The code at lines 73-85 exists exactly as described. The sRGB EOTF decode of 0.5 is approximately 0.214 (computed as ((0.5+0.055)/1.055)^2.4), yet the assertion `0.1 < result < 0.6` would accept an identity function (returning 0.5), a gamma-2.2 decode (giving ~0.218), or any value in that broad range. The decode of 1.0 should be exactly 1.0, yet `0.8 < result < 1.1` would also accept an identity function. The function itself delegates to `colour.RGB_to_RGB` which is likely correct, but the test

### L10. test_gain_map test_load_nonexistent_raises uses bare Exception

**File:** `/Users/retriedstormtrooper/Documents/spektrafilm-main/tests/test_gain_map.py`
**Lines:** 603-608
**Lens:** testing

test_load_nonexistent_raises asserts pytest.raises(Exception) without matching a specific exception type or message. This means any exception (including TypeError from a bug in argument passing, or AttributeError from a missing method) would satisfy the test.
MISSED_BUG: If load_gain_map raises a TypeError due to a bug in the function signature (e.g., wrong parameter name), the test would incorrectly pass.

**Missed bug:** If load_gain_map raises a TypeError due to a bug in the function signature (e.g., wrong parameter name), the test would incorrectly pass.

**Fix:** Use pytest.raises((FileNotFoundError, OSError), match="nonexistent") to verify the specific error type and message.

**Verification:** The code at lines 603-608 does use `pytest.raises(Exception)` (bare `Exception`) for `load_gain_map("/nonexistent/file.jpg")`. The actual call path goes to `_load_gain_map_jpeg` which calls `path.read_bytes()` (line 300), raising `FileNotFoundError`. Using bare `Exception` means any exception type (TypeError, AttributeError, RuntimeError, etc.) would satisfy the test, masking real bugs. The sibling test at lines 610-614 correctly uses `pytest.raises(ValueError, match="Unsupported format")`, show

### L11. No test for GrainParams n_sub_layers=0 or negative values

**File:** `/Users/retriedstormtrooper/Documents/spektrafilm-main/tests/test_grain.py`
**Lines:** entire file
**Lens:** testing

All grain tests use n_sub_layers >= 1. There is no test that verifies behavior when n_sub_layers=0 (which should either skip grain or raise an error). The GrainParams dataclass has no validation on n_sub_layers.
MISSED_BUG: If n_sub_layers=0 causes a division by zero or an empty array operation in the grain model, it would crash at runtime with an unhelpful error.

**Missed bug:** If n_sub_layers=0 causes a division by zero or an empty array operation in the grain model, it would crash at runtime with an unhelpful error.

**Fix:** Add a test with n_sub_layers=0 that asserts either expected behavior (no-op) or a clear error message.

**Verification:** The code at `/Users/retriedstormtrooper/Documents/spektrafilm-main/src/spektrafilm/model/grain.py` line 109 has `density_cmy_out /= n_sub_layers` with no guard. When `n_sub_layers=0`: (1) the loop `np.arange(0)` on line 103 produces zero iterations, so `density_cmy_out` stays all zeros, then (2) line 109 divides by zero, causing a `ZeroDivisionError`. For negative values like `-1`, `np.arange(-1)` also produces no iterations, and the division on line 109 silently flips the sign of a zero array (

---

## Remediation Priority

| # | Finding | Severity | Lens |
|---|---------|----------|------|
| 1 | `MlxBackend.nan_to_num` does not replace inf values | medium | correctness |
| 2 | `HalideBackend.cctf_encode` uses `hl.fast_pow` which trades precision for speed | medium | correctness |
| 3 | No pickle, yaml.load, eval/exec, or unsafe deserialization found | medium | security |
| 4 | `save_profile` crashes when `stock` is None (default) | medium | edge-cases |
| 5 | `_json_safe` does not handle Infinity values | medium | edge-cases |
| 6 | `crop_image` produces wrong results when crop size exceeds image dimensions | medium | edge-cases |
| 7 | `RuntimePhotoParams.__post_init__` validates only type, not parameter ranges | medium | edge-cases |
| 8 | `apply_grain_to_density_layers` mutates the input array in-place | medium | edge-cases |
| 9 | `scanning.py` always clips output ignoring `output_clip_min`/`output_clip_max` flags | medium | edge-cases |
| 10 | ColorReferenceService uses cross-stage mutable communication via set-once attributes | medium | architecture |
| 11 | GPU pipeline test checks only shape and finiteness, not correctness | medium | testing |
| 12 | Missing test for grain with blur > 0 | medium | testing |
| 13 | _remove_sRGB_cctf creates 3-element array just to get a scalar | low | performance |
| 14 | `profile_from_dict` crashes on profiles with extra unknown keys | low | edge-cases |
| 15 | print() used for warnings in production code instead of logging | low | architecture |
| 16 | Module-level side effects in model/color_filters.py -- filter objects instantiated at import time | low | architecture |
| 17 | SpectralLUTService has duplicate code paths for enlarger and scanner LUT computation | low | architecture |
| 18 | _debug_inject_pipeline returns None when inject_film_density_cmy is False | low | architecture |
| 19 | test_measure_density_min convergence test does not verify the warning was issued | low | testing |
| 20 | test_format_elapsed_time asserts only suffix, not exact values | low | testing |
| 21 | test_color_reference TestRemoveCCTF has weak range assertions | low | testing |
| 22 | test_gain_map test_load_nonexistent_raises uses bare Exception | low | testing |
| 23 | No test for GrainParams n_sub_layers=0 or negative values | low | testing |

---

*Generated by adversarial-review-v4 — 23 confirmed from 96 candidates (73 refuted).*
