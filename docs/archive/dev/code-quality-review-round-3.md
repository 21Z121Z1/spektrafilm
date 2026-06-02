> **STATUS: ARCHIVED** (historical). Findings addressed in subsequent rounds or adversarial review pass.

# Code Quality Review -- Round 3 -- Spektrafilm -- 2026-05-27

Comprehensive code quality review covering: type hints, error handling, dead code, code duplication, API consistency, test coverage, performance anti-patterns, and security concerns.

Review scope: all Python files in `src/spektrafilm/` and `src/spektrafilm_gui/` (~80 files).

## Findings Summary

| Category | Critical | High | Medium | Low |
|---|---|---|---|---|
| Type Hints & Docstrings | 0 | 12 | 27 | 12 |
| Error Handling | 3 | 9 | 11 | 6 |
| Dead Code & Unused Imports | 0 | 18 | 10 | 12 |
| Code Duplication | 0 | 6 | 6 | 5 |
| API Consistency | 0 | 4 | 9 | 10 |
| Test Coverage | 3 | 8 | 9 | 6 |
| Performance | 0 | 6 | 8 | 7 |
| Security | 0 | 3 | 4 | 3 |

---

## 1. Type Hints and Docstrings

### HIGH

**TH-H1. `model/parametric.py:3` -- `parametric_density_curves_model` entirely untyped**
All six parameters and the return type lack annotations. No docstring.
- Fix: Add `np.ndarray` annotations and a docstring with expected shapes.

**TH-H2. `model/glare.py:8,19` -- `add_glare` and `compute_random_glare_amount` lack full annotations**
`add_glare` has partial annotations but `illuminant_xyz` and `glare` are untyped. `compute_random_glare_amount` has zero annotations.
- Fix: Add types for all parameters.

**TH-H3. `model/color_filters.py:13-91` -- Nearly all public functions and both classes lack type annotations**
`create_combined_dichroic_filter`, `DichroicFilters`, `GenericFilter`, `sigmoid_erf`, `compute_band_pass_filter` -- none have return annotations.
- Fix: Add return types and parameter annotations to all public functions.

**TH-H4. `model/emulsion.py:18-29` -- `compute_density_spectral` and `develop_simple` entirely untyped**
Neither has type annotations or docstrings.
- Fix: Add `np.ndarray` annotations matching the style of `develop`.

**TH-H5. `model/illuminants.py:14-19` -- `black_body_spectrum` and `standard_illuminant` entirely untyped**
No parameter or return type annotations, no docstrings.
- Fix: Add `temperature: float -> colour.SpectralDistribution` and `type: str -> np.ndarray`.

**TH-H6. `model/couplers.py:9,69,135` -- Three public functions lack return annotations**
`compute_density_curves_before_dir_couplers`, `compute_exposure_correction_dir_couplers`, `apply_density_correction_dir_couplers`.
- Fix: Add `-> np.ndarray` return annotations.

**TH-H7. `model/grain.py:13,53,66,112,166` -- All public functions lack return annotations**
`layer_particle_model`, `add_micro_structure`, `apply_grain_to_density`, `apply_grain_to_density_layers`, `apply_grain`.
- Fix: Add `-> np.ndarray` returns.

**TH-H8. `model/diffusion.py:13,31,91,100,110,597` -- Multiple public functions lack return annotations**
`apply_unsharp_mask`, `apply_halation_um`, `apply_gaussian_blur`, `apply_gaussian_blur_um`, `apply_diffusion_filter_mm`, `apply_diffusion_filter_um`.
- Fix: Add `-> np.ndarray` returns.

**TH-H9. `utils/conversions.py:7,27,48` -- All public functions lack return annotations**
`density_to_light`, `compute_aces_conversion_matrix`, `rgb_to_raw_aces_idt`.
- Fix: Add `-> np.ndarray` and `-> tuple[np.ndarray, np.ndarray]`.

**TH-H10. `utils/preview.py:3` -- `resize_for_preview` entirely untyped**
No parameter annotations, no return annotation.
- Fix: Add `image: np.ndarray, max_size: int -> np.ndarray`.

**TH-H11. `utils/timings.py:9,25,42,88` -- All public functions lack return annotations**
`timeit`, `format_elapsed_time`, `format_timings`, `plot_timings`.
- Fix: Add return annotations.

**TH-H12. ~120+ functions/methods across the codebase missing return type annotations**
Concentrated in `model/`, `utils/`, `runtime/stages/`, `runtime/services/`, and `gpu/kernels/`.
- Fix: Systematic pass to add return types to all public and private methods.

### MEDIUM

**TH-M1. `gpu/backend.py:13-30` -- `ArrayBackend` Protocol uses `Any` pervasively**
Every method parameter and return is `Any`. `to_numpy` should return `-> np.ndarray`, `max` should return `-> float`.
- Fix: Add more specific types where possible.

**TH-M2-M27. 27 additional medium-severity findings**
See appendix: missing return annotations in `gpu/cupy_backend.py`, `gpu/mlx_backend.py`, `gpu/kernels/*.py`, `profiles/io.py`, `runtime/services/*.py`, `runtime/stages/*.py`, `runtime/pipeline.py`, `runtime/process.py`, `utils/io.py`, `utils/lut.py`, `utils/autoexposure.py`, `utils/crop_resize.py`, `utils/fast_interp.py`, `utils/fast_stats.py`, `utils/fast_gaussian_filter.py`, `utils/fft_gaussian_filter.py`, `utils/measure.py`, `utils/plotting.py`, `utils/spectral_upsampling.py`, `utils/calibration_targets.py`, `utils/raw_file_processor.py`.

### LOW

**TH-L1. Inconsistent `Optional[X]` vs `X | None` pattern**
The project consistently uses `X | None` (PEP 604) -- good. Minor: `profiles/io.py:47` uses `Any = None` where `float | None` would be better.

**TH-L2. Typo in method name: `_correction_fucntion` at `runtime/services/color_reference.py:135`**
Should be `_correction_function`. Called at lines 86, 106, 128.
- Fix: Rename to `_correction_function`.

---

## 2. Error Handling

### CRITICAL

**EH-C1. `_correction_fucntion` can crash with `NameError` on undefined `m`/`q`**
- File: `runtime/services/color_reference.py:135-153`
- When `_black_correction` and `_white_correction` are both `False`, the outer `if` block is skipped, but `midgray_black_white_corrected` at line 152 still references `m` and `q`. Callers have early-return guards, but any new caller without the guard triggers `NameError`.
- Fix: Add `else: return lambda y: y, 0.0` branch.

**EH-C2. Module-level data loading with no error handling on import**
- File: `model/color_filters.py:110-121`
- Five filter database objects are instantiated at module level. If any CSV file is missing, the entire module fails to import.
- Fix: Wrap in try/except with clear error messages.

**EH-C3. Module-level data loading with no error handling on import**
- File: `utils/spectral_upsampling.py:440`
- `HANATOS2025_SPECTRA_LUT = _load_hanatos2025_spectra_lut()` loads a `.npy` file at import time with no error handling.
- Fix: Wrap in try/except.

### HIGH

**EH-H1. `read_image_metadata` silently swallows all metadata errors**
- File: `utils/io.py:66-70`
- Catches `(OSError, RuntimeError, exiv2.extras.Exiv2Error)` and returns `None` with no logging.
- Fix: Log a warning with filename and exception.

**EH-H2. `load_image_payload` silently swallows color encoding errors**
- File: `utils/io.py:350-353`
- Catches `(OSError, RuntimeError, TypeError, ValueError)` and sets `color_encoding = None`. No logging.
- Fix: Log a warning.

**EH-H3. `load_hdr_curve_profiles` silently swallows all errors**
- File: `utils/hdr_curve_profiles.py:440-441`
- Catches `(OSError, ValueError, KeyError, TypeError, json.JSONDecodeError)` and returns empty dict. No logging.
- Fix: Log a warning.

**EH-H4. `standard_illuminant` uses dict lookup without validation**
- File: `model/illuminants.py:35`
- `colour.SDS_ILLUMINANTS[type]` raises raw `KeyError` with no context.
- Fix: Catch `KeyError` and raise `ValueError` with available options.

**EH-H5. `load_image_oiio` raises bare `Exception`**
- File: `utils/io.py:507`
- `raise Exception("Failed to read image data from " + filename)` -- should be `OSError`.
- Fix: Change to `OSError`.

**EH-H6. `_scene_luminance_y` catches 6 exception types as fallback**
- File: `runtime/pipeline.py:83-96`
- Catches `(AttributeError, KeyError, LookupError, RuntimeError, TypeError, ValueError)` and silently falls back to a fixed luminance vector. No logging.
- Fix: Narrow to expected errors. Log warning when falling back.

**EH-H7. `read_neutral_print_filters` has no error handling**
- File: `utils/io.py:800-804`
- Opens JSON with no try/except. Caller catches `FileNotFoundError` but not `JSONDecodeError`.
- Fix: Handle `JSONDecodeError`.

**EH-H8. `ProfileInfo` has no `__post_init__` validation**
- File: `profiles/io.py:33-88`
- String fields are validated separately by `_validate_profile_info`. Direct construction accepts invalid values.
- Fix: Add `__post_init__` validation.

**EH-H9. Typo in method name: `_correction_fucntion`**
- File: `runtime/services/color_reference.py:135`
- "fucntion" should be "function". Called at lines 86, 106, 128.
- Fix: Rename.

### MEDIUM

**EH-M1-M11.** Silent `None` returns from ICC profile loading, GPU tile pixel parsing, CCTF TypeError fallback, `NoneType` sentinel for `cmy_to_log_xyz`, profile validation `from None`, mutable default arguments in grain model, `write_image_metadata` ICC re-read race condition, `crop_image` missing validation, `image_data.shape` 3D assumption.

### LOW

**EH-L1-L6.** `Profile.__post_init__` style, ANSI escape codes in timings, `np.random.seed` global state in grain, `__main__` blocks without error handling, `plotting.py` legacy `self.type` references, `exiv2.Exiv2Error` namespace path inconsistency.

---

## 3. Dead Code and Unused Imports

### HIGH

**DC-H1. `model/color_filters.py:4` -- Unused import `scipy.interpolate`**
Only `scipy.special.erf` is used. `scipy.interpolate` is never referenced.
- Fix: Remove.

**DC-H2. `model/glare.py:2` -- Unused import `scipy.ndimage.gaussian_filter`**
Only referenced in commented-out code. Uses `fast_gaussian_filter` instead.
- Fix: Remove.

**DC-H3. `model/grain.py:3` -- Unused import `scipy.ndimage`**
Only referenced in commented-out code (lines 49, 60, 105, 161).
- Fix: Remove.

**DC-H4. `utils/fast_interp.py:3` -- Unused import `time` at module level**
Only used inside `if __name__ == '__main__':` block.
- Fix: Move into main block.

**DC-H5. `model/illuminants.py:8-12` -- Unused enum `Illuminants`**
Never referenced anywhere in the codebase.
- Fix: Remove or mark as internal.

**DC-H6. `model/stocks.py:3-29` -- Unused enum `FilmStocks`**
Never referenced anywhere in the codebase.
- Fix: Remove or mark as internal.

**DC-H7. `model/stocks.py:31-39` -- Unused enum `PrintPapers`**
Never referenced anywhere in the codebase.
- Fix: Remove or mark as internal.

**DC-H8. `utils/conversions.py:48-94` -- Unused function `rgb_to_raw_aces_idt`**
Never called from anywhere.
- Fix: Remove.

**DC-H9. `utils/timings.py:88-104` -- Unused function `plot_timings`**
Never called from anywhere.
- Fix: Remove.

**DC-H10. `model/density_curves.py:84,95` -- Unused functions `apply_gamma_shift_correction`, `remove_viewing_glare_comp`**
Never called from anywhere.
- Fix: Remove.

**DC-H11. `utils/measure.py:6,14,28` -- All three public functions unused**
`measure_gamma`, `measure_slopes_at_exposure`, `measure_density_min` -- never called.
- Fix: Remove entire file.

**DC-H12. `model/parametric.py:3` -- Unused function `parametric_density_curves_model`**
Never called from anywhere.
- Fix: Remove entire file.

**DC-H13. `utils/fft_gaussian_filter.py:4` -- Entire module unused**
`fft_gaussian_filter` is never called. Depends on `pyfftw` which is not in dependencies.
- Fix: Remove entire file.

**DC-H14. `gpu/kernels/lut.py:457,503` -- Unused functions `apply_lut_bilinear_2d_mlx`, `apply_lut_bilinear_2d_numpy`**
Never called from anywhere.
- Fix: Remove.

**DC-H15. `gpu/kernels/color.py:76` -- Unused function `precompute_cctf_decode_matrix`**
Never called from anywhere.
- Fix: Remove.

**DC-H16. `gpu/kernels/color.py:209` -- Unused function `cctf_decoding_backend`**
Never called from anywhere.
- Fix: Remove.

**DC-H17. `model/diffusion.py:514` -- Unused function `diffusion_filter_radial_profile`**
Never called from anywhere.
- Fix: Remove or keep as diagnostic helper.

**DC-H18. `utils/fast_stats.py:236` -- Unused function `lognorm_from_mean_std`**
Never called from anywhere. Also references `scipy.stats` which is not imported.
- Fix: Remove.

### MEDIUM

**DC-M1. Module-level filter instances loaded at import time in `model/color_filters.py:112-118`**
Several instances (`thorlabs_dichroic_filters`, `edmund_optics_dichroic_filters`, etc.) are created at import time but never used outside the file. Causes unnecessary I/O.
- Fix: Lazy instantiation or remove unused ones.

**DC-M2. `runtime/pipeline.py:3,161` -- Duplicate `import copy`**
Module-level and function-level import of `copy`.
- Fix: Remove function-level import.

**DC-M3. `model/density_curves.py:2` -- Redundant `import scipy`**
Only `scipy.ndimage.gaussian_filter` is used. Should be `import scipy.ndimage`.
- Fix: Change import.

**DC-M4-M10.** `np_interp_for_image` (benchmark only), `compute_lut_spectra` (benchmark only), `rgb_to_smooth_spectrum` (unused), `apply_lut_cubic_scipy` (benchmark only), `MALLETT2019_BASIS` loaded at import time.

### LOW

**DC-L1-L10.** Commented-out code blocks in `density_curves.py`, `diffusion.py`, `glare.py`, `grain.py`, `couplers.py`. Typo `dicrhoic` in `color_filters.py:114`. Empty `if __name__` in `emulsion.py:98`. Redundant `Profile` property forwarding. Unused `load_processed_profile`/`save_processed_profile` aliases. Unused variables in `spectral_upsampling.py:563`.

---

## 4. Code Duplication

### HIGH

**CD-H1. `spectral_lut_compute.py` -- `spectral_compute_enlarger` vs `spectral_compute_scanner`**
~60 lines each, line-for-line identical except cache attribute names.
- Fix: Extract `_spectral_compute_cached()` taking attribute names as parameters.
- Est. savings: ~55 lines.

**CD-H2. `gpu/kernels/lut.py` -- Trilinear 3D LUT interpolation repeated 3 times**
Identical algorithm in `apply_lut_trilinear_3d_mlx` (293-346), `_numpy` (349-390), `_cupy` (393-439).
- Fix: Parameterized function accepting a namespace of operations.
- Est. savings: ~75 lines.

**CD-H3. `gpu/kernels/density.py` and `gpu/kernels/filters.py` -- `_backend_supports_*` helpers duplicated**
Three identical helper functions defined in both modules.
- Fix: Move to `spektrafilm.gpu.backend`.
- Est. savings: ~12 lines.

**CD-H4. `model/emulsion.py` and `gpu/kernels/density.py` -- `compute_density_spectral` duplicated**
CPU version uses `opt_einsum.contract`, GPU version uses `backend.einsum`. Same math.
- Fix: Have CPU version delegate to backend version with `NumpyBackend`.
- Est. savings: ~8 lines.

**CD-H5. `utils/conversions.py` and `gpu/kernels/density.py` -- `density_to_light` duplicated**
Same operation with different NaN handling.
- Fix: Consolidate.
- Est. savings: ~18 lines.

**CD-H6. `profiles/io.py` -- `ProfileInfo` properties duplicated on `Profile`**
10 properties (`is_positive`, `is_negative`, etc.) re-declared verbatim on `Profile`, each just calling `self.info.*`.
- Fix: Use `__getattr__` delegation.
- Est. savings: ~40 lines.

### MEDIUM

**CD-M1. `filter_enlarger_source.py` -- Three EnlargerService methods with identical structure**
`enlarger_filtered_illuminant`, `enlarger_neutral_illuminant`, `preflash_filtered_illuminant` differ only in shift parameters.
- Fix: Single `_filtered_illuminant(self, light_source, *, m_shift=0.0, y_shift=0.0)`.
- Est. savings: ~12 lines.

**CD-M2. `runtime/stages/scanning.py` -- Scan illuminant computation repeated 3 times**
`_precompute_xyz_to_rgb_matrix`, `_density_to_rgb`, `_return_callable_cmy_to_log_xyz` all resolve `scan_illuminant` identically.
- Fix: Cache at init time.
- Est. savings: ~15 lines.

**CD-M3. `gpu/kernels/lut.py` -- Mitchell-Netravali weight computed 8 times in Metal shader**
~56 lines of identical shader code for `wx[0]..wx[3]` and `wy[0]..wy[3]`.
- Fix: Define Metal helper function `mitchell_weight(float t)`.
- Est. savings: ~40 lines.

**CD-M4-M6.** CCTF encoding GPU/CPU branches, RGB-to-XYZ / XYZ-to-RGB matrix computation, CCTF encoding/decoding dispatch.

### LOW

**CD-L1-L5.** `safe_log10` pattern (5 instances), `10**log_sensitivity` pattern (2 instances), normalization computation (3 instances), GPU array conversion guard (20 instances), `antilog10` pattern (3 instances).

---

## 5. API Consistency

### HIGH

**AC-H1. Missing `__all__` exports in multiple `__init__.py` files**
`model/__init__.py`, `runtime/services/__init__.py`, `gpu/kernels/__init__.py`, `spektrafilm_gui/__init__.py` -- all empty.
- Fix: Add explicit `__all__`.

**AC-H2. Parameter order inconsistency between CPU and GPU versions**
`interpolate_exposure_to_density()` takes `(log_exposure_rgb, density_curves, log_exposure, gamma_factor)`. The GPU version `interpolate_exposure_to_density_backend()` swaps `density_curves` and `log_exposure`.
- Fix: Align parameter order.

**AC-H3. Inconsistent return types for `SimulationPipeline` methods**
`get_timings()`, `get_total_elapsed_time()`, `format_timings()`, `print_timings()` all lack return type annotations.
- Fix: Add annotations.

**AC-H4. Inconsistent constructor patterns across backends**
`NumpyBackend` is a `@dataclass(slots=True)`, `CupyBackend` and `MlxBackend` are plain classes with `__init__`.
- Fix: Convert `NumpyBackend` to plain class.

### MEDIUM

**AC-M1. `type` used as parameter name (shadows builtin)**
`model/illuminants.py:19` and `model/color_filters.py:68`.
- Fix: Rename to `illuminant_type` / `filter_type`.

**AC-M2. Inconsistent `__init__` parameter ordering across stage classes**
`FilmingStage`, `PrintingStage`, `ScanningStage` have different parameter orders for services.
- Fix: Use keyword-only arguments.

**AC-M3. Inconsistent default `color_space` across spectral upsampling functions**
Some default to `'sRGB'`, some to `'ITU-R BT.2020'`, some have no default.
- Fix: Make `color_space` required everywhere.

**AC-M4. Inconsistent `apply_cctf_decoding` default**
Some default to `True`, some to `False`.
- Fix: Default to `False` everywhere (runtime pipeline passes explicitly).

**AC-M5. Inconsistent `backend` parameter style: positional vs keyword-only**
Some `_backend` functions use `backend` as last positional arg, others as keyword-only.
- Fix: Always keyword-only (`*, backend`).

**AC-M6. Inconsistent `backend` guard pattern**
Some use `getattr(backend, "supports_gpu", False)`, others use `backend.supports_gpu` directly.
- Fix: Use helper consistently.

**AC-M7. Inconsistent `positive` parameter vs `profile_type` string**
Same concept expressed as `positive` (bool), `positive_film` (bool), and `profile_type` (string).
- Fix: Use `profile_type: ProfileType` everywhere.

**AC-M8. Mixed mutation patterns in `params_builder.py`**
`digest_params` mutates in-place and returns; `_apply_halation_preset` mutates in-place and returns `None`.
- Fix: Pick one pattern.

**AC-M9. Typo `_correction_fucntion`**
Already noted in EH-H9.

### LOW

**AC-L1-L10.** Mutable default arguments in `color_filters.py`, inconsistent docstring style, `__all__` definitions inconsistency, `dataclass` decorator inconsistency, `save_profile`/`load_profile` missing annotations, `standard_illuminant` boolean trap, commented-out code in `utils/io.py`, inconsistent `@staticmethod` vs module-level functions, `CouplersState` missing fields.

---

## 6. Test Coverage Gaps

### CRITICAL

**TC-C1. `model/diffusion.py` -- No test file exists (659 lines)**
One of the most complex modules. Contains `_strength_to_scatter`, `_expand_group`, `_halo_channel_weights`, `diffusion_filter_psf`, `apply_diffusion_filter_um`, `apply_halation_um`.
- Fix: Add tests for PSF normalization, energy conservation, inactive bypass, warmth redistribution.

**TC-C2. `model/illuminants.py` -- No test file exists**
`standard_illuminant` is the default enlarger light source. A bug corrupts every pipeline output.
- Fix: Add tests for each illuminant type, positive values, normalization.

**TC-C3. `model/color_filters.py` -- No module-level test file**
`DichroicFilters.apply`, `GenericFilter.apply`, `compute_band_pass_filter` are untested.
- Fix: Add tests for bounded transmittance, identity at value 1, UV/IR attenuation.

### HIGH

**TC-H1. `utils/fast_gaussian_filter.py` -- No direct test file**
Core blur primitive used throughout. `fast_gaussian_filter`, `fast_exponential_filter` untested.
- Fix: Test against SciPy reference.

**TC-H2. `utils/fast_interp.py` -- No direct test file**
Numba-accelerated 1D interpolation. Critical for density curves.
- Fix: Test against `np.interp`, endpoint clamping, monotonicity.

**TC-H3. `utils/fast_interp_lut.py` -- No direct test file**
Mitchell-Netravali cubic interpolation. Complex 4x4 stencil with reflection boundary.
- Fix: Test identity LUT, reflect boundary.

**TC-H4. `utils/fast_stats.py` -- No direct test file**
`fast_binomial`, `fast_poisson`, `fast_lognormal_from_mean_std` -- Numba RNGs used by grain.
- Fix: Test statistical moments match SciPy.

**TC-H5. `utils/numba_boost_hightlights.py` -- No direct test file**
Numba kernel tested only via GPU backend, not against CPU reference.
- Fix: Test parity with GPU backend.

**TC-H6. `runtime/stages/filming.py` -- Limited direct tests (3 tests, monkeypatched)**
Core simulation stage. Only exercised indirectly through smoke tests.
- Fix: Add targeted unit tests for `expose` and `develop`.

**TC-H7. `runtime/stages/printing.py` -- No direct test file**
Zero direct tests.
- Fix: Add tests for print exposure, diffusion, preflash.

**TC-H8. `runtime/services/spectral_lut_compute.py` -- LUT tolerance too broad**
`test_lut_path_stays_close_to_direct_path` uses `atol=0.02` (2% of range).
- Fix: Tighten tolerance or document acceptable error.

### MEDIUM

**TC-M1-TC-M9.** Missing edge case tests in `color_management.py`, `profiles/io.py`, `hdr_photo.py`, `runtime/params_builder.py`, `utils/conversions.py`, `model/glare.py`, `utils/crop_resize.py`, GPU `NumpyBackend`, `utils/dtypes.py`.

### LOW

**TC-L1-TC-L6.** `utils/measure.py`, `utils/preview.py`, `utils/timings.py`, `utils/calibration_targets.py`, `utils/numba_warmup.py`, `gpu/metal_serialization.py`.

---

## 7. Performance Anti-Patterns

### HIGH

**PF-H1. `model/illuminants.py:19` -- `standard_illuminant()` recomputed on every pipeline call**
Called 3+ times per image. Each call constructs `colour.SpectralDistribution`, aligns, normalizes.
- Fix: Add `@lru_cache` or cache at stage init.
- Est. savings: 15-45ms per image.

**PF-H2. `utils/spectral_upsampling.py:182-196` -- `_fetch_coeffs` creates 4 `RegularGridInterpolator` objects per call**
Expensive interpolator construction without caching.
- Fix: Cache interpolator objects.
- Est. savings: 100-200ms per LUT generation.

**PF-H3. `utils/autoexposure.py:29-33` -- `colour.RGB_to_XYZ` matrix recomputed for every auto-exposure call**
`colour.RGB_to_XYZ` internally builds a 3x3 matrix from scratch every call.
- Fix: Precompute the matrix once, apply via `np.tensordot`.
- Est. savings: 5-10ms per call.

**PF-H4. `model/diffusion.py:597-658` -- Diffusion filter PSF recomputed per image**
`_resolve_family_cfg`, `_strength_to_scatter`, `diffusion_filter_psf` all recomputed every frame. Inputs are pipeline constants.
- Fix: Cache PSF keyed on parameters.
- Est. savings: 20-50ms per image.

**PF-H5. `utils/spectral_upsampling.py:209-211` -- `_compute_spectra_from_coeffs` uses `np.apply_along_axis`**
16,384 Python-level `np.interp` calls for a 128x128 LUT.
- Fix: Vectorize with reshaped array.
- Est. savings: 200-500ms per LUT generation.

**PF-H6. `runtime/pipeline.py:545,550` -- `np.ascontiguousarray` on already-processed arrays**
Creates unnecessary copies of 288MB float32 images.
- Fix: Only call when downstream requires contiguous memory.
- Est. savings: 50-100ms per image.

### MEDIUM

**PF-M1-PF-M8.** `_remove_cctf` scalar-to-array conversion, `density_to_light` unconditional NaN scan, couplers matrix recomputed per image, `np.repeat` in density interpolation, LUT preparation on every call, per-channel FFT convolution, `_apply_per_channel` per-channel contiguous copies.

### LOW

**PF-L1-PF-L7.** Glare temporary arrays, `parametric_density_curves_model` Python loop, grain nested loops, `_load_coeffs_lut` pixel-by-pixel struct unpack, `_rgba_float_payload` redundant contiguous call, `_illuminant_to_xy` Python loop, `_remove_cctf` scalar RGB_to_RGB.

---

## 8. Security Concerns

### HIGH

**SC-H1. `profiles/io.py:294-301` -- Path traversal in `load_profile`**
`stock` parameter concatenated directly into file path without sanitization.
- Fix: Validate `stock` matches `r'^[A-Za-z0-9_-]+$'`.

**SC-H2. `profiles/io.py:284-292` -- Path traversal in `save_profile`**
`profile.info.stock + suffix` used to construct file path without validation.
- Fix: Same validation as H1.

**SC-H3. `utils/io.py:810-838` -- Unsanitized `brand`, `name`, `filter_type` in filter loading**
Used to construct paths passed to `pkg_resources.files()`.
- Fix: Validate against `r'^[A-Za-z0-9_-]+$'`.

### MEDIUM

**SC-M1. `utils/io.py:479-523,529-753` -- No input validation on filenames**
`load_image_oiio` and `save_image_oiio` accept arbitrary paths.
- Fix: Document caller responsibility; validate regular file for defense-in-depth.

**SC-M2. `utils/hdr_photo.py:284-304` -- Subprocess with user-influenced output path**
`output_path` passed to `subprocess.run()` as argument. List-based (no shell injection), but path not validated.
- Fix: Validate parent directory exists and is writable.

**SC-M3. Unbounded JSON file reads**
`json.load` on profile files, curve profile files, GUI state files with no size limits.
- Fix: Check file size before reading user-facing files.

**SC-M4. `spektrafilm_gui/persistence.py:47-51` -- No file permission restrictions**
GUI state files created with default permissions.
- Fix: Set `0o600` permissions.

### LOW

**SC-L1. `pyproject.toml:33` -- PyYAML dependency appears unused in source**
Unnecessary dependency expands attack surface.
- Fix: Verify if needed; move to dev dependencies if only used in tests.

**SC-L2. `utils/io.py:818,833` -- `np.loadtxt` on CSV without shape validation**
- Fix: Add shape validation after loading.

**SC-L3. `pyproject.toml` -- Compatible release constraints without hash pinning**
- Fix: Consider lockfile with hash verification for production.

### Clean Areas

No unsafe deserialization (pickle), no eval/exec on user input, no hardcoded credentials, no insecure temp files (proper `tempfile.TemporaryDirectory`), no unsafe YAML loading, no shell injection (subprocess uses list args), no network requests without timeout, no integer overflow risks, no unsafe `os.path.join`.

---

## Prioritized Action List

### Must Fix (Critical)

1. **EH-C1**: Fix latent `NameError` in `_correction_fucntion` -- add `else` branch
2. **EH-C2**: Wrap module-level filter loading in try/except
3. **EH-C3**: Wrap `HANATOS2025_SPECTRA_LUT` loading in try/except
4. **TC-C1**: Add tests for `model/diffusion.py` (most complex untested module)

### Should Fix Soon (High)

1. **SC-H1/H2/H3**: Add path validation to profile/filter loading
2. **EH-H1/H2/H3**: Add logging to silent error handlers
3. **EH-H5**: Change bare `Exception` to `OSError` in `load_image_oiio`
4. **DC-H1-H18**: Remove dead code (unused functions, imports, enums, entire files)
5. **PF-H1**: Cache `standard_illuminant()` results
6. **PF-H4**: Cache diffusion filter PSF
7. **CD-H1**: Deduplicate `spectral_compute_enlarger`/`scanner`
8. **CD-H2**: Deduplicate trilinear LUT backends
9. **TC-H1-H4**: Add tests for `fast_gaussian_filter`, `fast_interp`, `fast_interp_lut`, `fast_stats`

### Should Fix (Medium)

1. **TH-M1-M27**: Add return type annotations systematically
2. **AC-M1-M9**: Fix API inconsistencies (parameter naming, ordering, defaults)
3. **CD-M1-M6**: Extract common patterns (EnlargerService, scanning illuminant, Mitchell shader)
4. **PF-H3/H5/H6**: Cache auto-exposure matrix, vectorize LUT spectra, remove unnecessary contiguous copies
5. **TC-M1-M9**: Add edge case tests for validated modules
6. **EH-M1-M11**: Improve error handling in ICC loading, GPU config, profile validation

### Optional Cleanup (Low)

1. **DC-L1-L10**: Remove commented-out code, fix typos, clean empty main blocks
2. **AC-L1-L10**: Fix mutable defaults, consistent docstring style, `__all__` definitions
3. **TH-L1-L12**: Fix `_correction_fucntion` typo, consistent `X | None` usage
4. **PF-L1-L7**: Minor optimizations (glare arrays, parametric loop, grain batch RNG)
5. **SC-L1-L3**: PyYAML audit, CSV shape validation, lockfile for production

---

## Appendix: Files Reviewed

All 63 Python files in `src/spektrafilm/` and `src/spektrafilm_gui/` were read in full. Test files in `tests/` (excluding `tests/gui/`) were analyzed for coverage gaps. `pyproject.toml` was reviewed for dependency security.
