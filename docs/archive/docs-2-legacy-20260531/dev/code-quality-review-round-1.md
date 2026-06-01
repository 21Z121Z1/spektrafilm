# Code Quality Review — Spektrafilm — Round 1

**Date:** 2026-05-27
**Reviewer:** Claude (automated)
**Scope:** All source in `src/spektrafilm/` and `src/spektrafilm_gui/`, plus `tests/`
**Method:** Static analysis, pattern search, manual code reading

---

## Executive Summary

| Category | HIGH | MEDIUM | LOW |
|---|---|---|---|
| 1. Type Hints & Docstrings | 4 | 6 | 3 |
| 2. Error Handling | 3 | 4 | 2 |
| 3. Dead Code & Unused Imports | 2 | 5 | 4 |
| 4. Code Duplication | 1 | 4 | 2 |
| 5. API Consistency | 2 | 5 | 3 |
| 6. Test Coverage Gaps | 3 | 4 | 2 |
| 7. Performance Anti-patterns | 2 | 3 | 2 |
| 8. Security Concerns | 1 | 2 | 1 |
| **Total** | **18** | **33** | **19** |

---

## 1. Type Hints and Docstrings

### HIGH

#### 1H-1. `save_image_oiio` has no return type annotation
- **File:** `src/spektrafilm/utils/io.py:524`
- The main public image-save function lacks a return type. It sometimes returns `None` (for PNG/TIFF/EXR), sometimes returns `tuple[str, ...]` (for HEIC via `save_hdr_photo_heic`). Callers cannot statically know which.
- **Fix:** Add `-> tuple[str, ...] | None` and document the conditional return.

#### 1H-2. `SimulationPipeline.__init__` untyped parameters
- **File:** `src/spektrafilm/runtime/pipeline.py:198`
- `params` is untyped (should be `RuntimePhotoParams`). `_reused_lut_service` is untyped.
- **Fix:** `def __init__(self, params: RuntimePhotoParams, update_params: bool = False, *, _reused_lut_service: SpectralLUTService | None = None) -> None:`

#### 1H-3. `GuiController` methods lack type annotations
- **File:** `src/spektrafilm_gui/controller.py:196–1131`
- Most methods have no return type annotation. `_process_image_with_runtime` returns `np.ndarray` but is not annotated. `_simulation_input_image` returns `np.ndarray | None` but is not annotated.
- **Fix:** Add return type annotations to all public and private methods.

#### 1H-4. `profile_from_dict` / `profile_to_dict` use `Any` instead of precise types
- **File:** `src/spektrafilm/profiles/io.py:192, 212`
- `profile_from_dict(data: Any)` — should accept `Mapping | Profile`. `profile_to_dict(data)` has no type annotation at all.
- **Fix:** Narrow the `Any` to `Mapping[str, Any] | Profile` and add return type `-> dict[str, Any]`.

### MEDIUM

#### 1M-1. Inconsistent docstring style
- `src/spektrafilm/utils/io.py` uses NumPy-style docstrings with Parameters/Returns sections.
- `src/spektrafilm/utils/hdr_photo.py` uses minimal single-line docstrings or none.
- `src/spektrafilm/utils/autoexposure.py` has zero docstrings on any function.
- `src/spektrafilm/profiles/io.py` has docstrings on some functions but not others.
- **Fix:** Pick one style (NumPy recommended for scientific code) and apply consistently to all public functions.

#### 1M-2. `load_image_oiio` missing type annotations on parameters
- **File:** `src/spektrafilm/utils/io.py:471`
- `filename` and `dtype` parameters have no type hints.
- **Fix:** `def load_image_oiio(filename: str | Path, *, dtype: type | np.dtype = np.float32) -> np.ndarray:`

#### 1M-3. `_runtime_image_dtype` returns `np.dtype` but accepts untyped `dtype`
- **File:** `src/spektrafilm/utils/io.py:518`
- **Fix:** `def _runtime_image_dtype(dtype: type | np.dtype) -> np.dtype:`

#### 1M-4. `develop()` in emulsion.py has mixed typing
- **File:** `src/spektrafilm/model/emulsion.py:44`
- Uses `FloatArray` TypeAlias for some params but `backend=None` is untyped. `profile_type: ProfileType` is good but `gamma_factor: float` has no docstring context.
- **Fix:** Type the `backend` parameter as `ArrayBackend | None`.

#### 1M-5. `HDRPhotoMapping` dataclass has 80+ fields with no field-level docstrings
- **File:** `src/spektrafilm/utils/hdr_photo.py:47–122`
- Complex physics parameters like `paper_rolloff_k`, `graft_strength` etc. have no docstrings explaining their physical meaning or valid ranges.
- **Fix:** Add docstrings or inline comments for non-obvious physical parameters.

#### 1M-6. `RuntimePhotoParams` and sub-dataclasses lack class-level docstrings
- **File:** `src/spektrafilm/runtime/params_schema.py:10–239`
- None of the 12 dataclass definitions (`DiffusionFilterParams`, `CameraParams`, `EnlargerParams`, etc.) have class docstrings.
- **Fix:** Add one-line class docstrings explaining the purpose of each params group.

### LOW

#### 1L-1. `__init__.py` files lack module docstrings
- `src/spektrafilm/__init__.py`, `src/spektrafilm_gui/__init__.py`, most sub-package `__init__.py` files.

#### 1L-2. `_smoothstep` is a well-known function but has no docstring
- **File:** `src/spektrafilm/utils/hdr_photo.py:802`

#### 1L-3. `_content_headroom` has a good docstring but `_rgba_float_payload` does not
- **File:** `src/spektrafilm/utils/hdr_photo.py:963`

---

## 2. Error Handling

### HIGH

#### 2H-1. Silent exception swallowing in `read_image_metadata`
- **File:** `src/spektrafilm/utils/io.py:67`
- `except Exception: return None` silently swallows all errors including permission denied, corrupt files, and programming errors. Callers have no way to distinguish "no metadata" from "file corrupted".
- **Fix:** Catch specific exceptions (`OSError`, `RuntimeError`) and log a warning for unexpected errors.

#### 2H-2. `controller.py` catches bare `Exception` and resets simulator
- **File:** `src/spektrafilm_gui/controller.py:924`
- `except Exception: self._runtime_simulator = None; raise` — this destroys the simulator on ANY exception including `KeyboardInterrupt` (which inherits from `BaseException`, not `Exception`, so actually OK). However, it also catches `MemoryError` which should probably be handled differently.
- **Fix:** Catch `(RuntimeError, ValueError, OSError)` instead of bare `Exception`.

#### 2H-3. Pipeline profile characterization silently catches all exceptions
- **File:** `src/spektrafilm/runtime/pipeline.py:576`
- `except Exception as e: print(f"Warning: ...")` — uses `print()` instead of `logging.warning()`, and catches everything including potential `SystemError` or `MemoryError`.
- **Fix:** Use `logging.warning()` and catch `(RuntimeError, ValueError, TypeError)`.

### MEDIUM

#### 2M-1. `_read_exif_metadata` catches bare `Exception`
- **File:** `src/spektrafilm/utils/raw_file_processor.py:287`
- Returns a default `ExifData` on any exception. Should catch `(OSError, RuntimeError, ValueError)`.

#### 2M-2. `write_image_metadata` can raise `RuntimeError` on ICC mismatch but callers don't handle it
- **File:** `src/spektrafilm/utils/io.py:153`
- The metadata write validates ICC round-trip and raises `RuntimeError` if the profile changed. The controller catches generic `Exception` at `controller.py:606` which masks this specific failure.

#### 2M-3. `save_image_oiio` raises generic `IOError` and `Exception`
- **File:** `src/spektrafilm/utils/io.py:477, 499`
- Line 477: `raise IOError(...)` — should use `FileNotFoundError` or `OSError`.
- Line 499: `raise Exception("Failed to read image data")` — should use `RuntimeError`.

#### 2M-4. `_pipeline_debug` can return `None` implicitly
- **File:** `src/spektrafilm/runtime/pipeline.py:615–619`
- If `debug_mode` is not `"output"` or `"inject"`, the function falls through and returns `None` implicitly. The caller at line 304 assigns this to `image`, causing a downstream crash.
- **Fix:** Add `raise ValueError(f"Unknown debug_mode: {self.debug.debug_mode!r}")` as the else branch.

### LOW

#### 2L-1. `save_profile` uses `print()` for status
- **File:** `src/spektrafilm/profiles/io.py:287`
- `print('Saving profile to:', filename)` — should use `logging.info()`.

#### 2L-2. `diffusion.py` uses `print()` for warning
- **File:** `src/spektrafilm/model/diffusion.py:118`
- `print(f"Warning: diffusion filter size...")` — should use `logging.warning()`.

---

## 3. Dead Code and Unused Imports

### HIGH

#### 3H-1. `_run_simulation` is a dead synchronous code path
- **File:** `src/spektrafilm_gui/controller.py:1102–1131`
- `_run_simulation` duplicates the logic of `_start_simulation` but runs synchronously. It is never called from anywhere in the codebase (the async path via `_start_simulation` is used exclusively).
- **Fix:** Remove `_run_simulation` or document its purpose for testing.

#### 3H-2. `_should_tile_mlx_image` is an alias for `_should_tile_gpu_image`
- **File:** `src/spektrafilm/runtime/pipeline.py:379`
- `_should_tile_mlx_image` just calls `_should_tile_gpu_image`. Similarly `_process_with_mlx_tiles` at line 431 just calls `_process_with_gpu_tiles`. These are legacy aliases from the MLX-only era.
- **Fix:** Remove both methods and any remaining callers.

### MEDIUM

#### 3M-1. `if __name__ == '__main__': pass` block in emulsion.py
- **File:** `src/spektrafilm/model/emulsion.py:98–99`
- Empty main block. Either add a meaningful entry point or remove.

#### 3M-2. Commented-out code blocks in spectral_upsampling.py
- **File:** `src/spektrafilm/utils/spectral_upsampling.py:184–190, 251–257`
- Large commented-out code blocks that should be removed or converted to proper documentation.

#### 3M-3. `load_processed_profile` / `save_processed_profile` are trivial aliases
- **File:** `src/spektrafilm/profiles/io.py:302–303`
- These are `load_profile` and `save_profile` renamed. If they exist for backwards compatibility, they should be documented as such. If unused, remove.

#### 3M-4. `compute_lut_spectra` is only used in `__main__` blocks
- **File:** `src/spektrafilm/utils/spectral_upsampling.py:214`
- Only called from the `__main__` guard. May be dead code if the LUT is always loaded from disk.

#### 3M-5. `_pipeline_scan_film` / `_pipeline_print` duplicate del patterns
- **File:** `src/spektrafilm/runtime/pipeline.py:584–604`
- The explicit `del` calls (`del rgb_image`, `del log_raw_film`, etc.) are premature optimization — Python's reference counting handles this. They add noise without measurable benefit since the arrays are GPU-backed.

### LOW

#### 3L-1. `import copy` at top of `pipeline.py` shadows `from dataclasses import dataclass`
- **File:** `src/spektrafilm/runtime/pipeline.py:4`
- `copy` is imported at module level but also imported inside `characterize_pipeline_profile` at line 164.

#### 3L-2. `import warnings` unused in `spectral_upsampling.py` at module scope
- **File:** `src/spektrafilm/utils/spectral_upsampling.py:3`
- `warnings` is used inside functions, so the import is fine. But `scipy` is imported twice: `import scipy` and `import scipy.interpolate` and `import scipy.special` (lines 10–12).

#### 3L-3. `FastStats` module `__main__` blocks contain benchmark code
- **Files:** `src/spektrafilm/utils/fast_stats.py`, `src/spektrafilm/utils/fast_gaussian_filter.py`, `src/spektrafilm/utils/fast_interp_lut.py`, `src/spektrafilm/utils/fft_gaussian_filter.py`
- These contain benchmarking code with many `print()` calls. Should be moved to a benchmark script or test.

#### 3L-4. `plotting.py` appears to be a utility/scratch module
- **File:** `src/spektrafilm/utils/plotting.py`
- Contains `print()` debug statements (line 151). Not imported by any production code.

---

## 4. Code Duplication

### HIGH

#### 4H-1. `_runtime_dtype` duplicated across three files
- **Files:**
  - `src/spektrafilm/utils/io.py:518` — `_runtime_image_dtype`
  - `src/spektrafilm/utils/raw_file_processor.py:608` — `_runtime_raw_dtype`
  - `src/spektrafilm/runtime/pipeline.py:48` — `_runtime_dtype`
  - `src/spektrafilm_gui/controller.py:188` — `runtime_float_dtype`
- All four do the same thing: validate and return `np.float32` or `np.float64`.
- **Fix:** Extract to a shared utility in `src/spektrafilm/utils/conversions.py` or a new `src/spektrafilm/utils/dtypes.py`.

### MEDIUM

#### 4M-1. `_scene_luminance_y` duplicated in pipeline.py
- **File:** `src/spektrafilm/runtime/pipeline.py:79–99`
- Computes XYZ luminance from RGB. This duplicates logic in `autoexposure.py:_luminance_y` and `hdr_photo.py:luminance_y`.
- **Fix:** Consolidate into a single utility function.

#### 4M-2. `color_management_workflow_preset` called redundantly in controller
- **File:** `src/spektrafilm_gui/controller.py:264, 447, 478, 930`
- The same workflow preset is computed multiple times within a single `save_output_layer` call (lines 447 and 478).
- **Fix:** Compute once at the top of the method and pass through.

#### 4M-3. Profile property delegation duplicated
- **File:** `src/spektrafilm/profiles/io.py:47–85 vs 151–189`
- `ProfileInfo` and `Profile` both define identical property accessors (`is_positive`, `is_negative`, `is_paper`, `is_film`, `is_color`, `is_bw`, `is_filming`, `is_printing`, `is_still`, `is_cine`). `Profile` just delegates to `self.info`.
- **Fix:** Use `__getattr__` delegation on `Profile` or remove the duplication.

#### 4M-4. GPU tile timing keys duplicated with MLX prefix
- **File:** `src/spektrafilm/runtime/pipeline.py:423–428`
- Both `gpu_tiled_*` and `mlx_tiled_*` keys are written with identical values.
- **Fix:** Remove the `mlx_tiled_*` keys.

### LOW

#### 4L-1. `load_dichroic_filters` and `load_filter` share identical CSV parsing
- **File:** `src/spektrafilm/utils/io.py:798–826`
- Both load CSV, deduplicate, and interpolate. Could share a `_load_filter_csv` helper.

#### 4L-2. `_smoothstep` could be a shared utility
- **File:** `src/spektrafilm/utils/hdr_photo.py:802`
- Used extensively in HDR code. Could live in `utils/conversions.py` for reuse.

---

## 5. API Consistency

### HIGH

#### 5H-1. `save_image_oiio` has inconsistent return semantics
- **File:** `src/spektrafilm/utils/io.py:524`
- Returns `None` for most formats, returns `tuple[str, ...]` for HEIC (via `save_hdr_photo_heic`). The caller at `controller.py:593` does `hdr_diagnostics = save_image_oiio(...) or ()`, which works but hides the inconsistency.
- **Fix:** Always return `tuple[str, ...]` (empty tuple for non-HEIC) or split into separate functions.

#### 5H-2. `IOParams.full_image` property is a compatibility shim
- **File:** `src/spektrafilm/runtime/params_schema.py:176–182`
- The getter always returns `True` and the setter is a no-op. This is a silent API lie — callers setting `full_image = False` get no effect and no error.
- **Fix:** Deprecate with a warning or remove entirely.

### MEDIUM

#### 5M-1. Inconsistent function naming: `load_*` vs `read_*`
- `load_image_oiio`, `load_image_payload`, `load_profile`, `load_filter`, `load_dichroic_filters` — all use `load_`
- `read_image_metadata`, `read_image_color_encoding`, `read_neutral_print_filters` — all use `read_`
- No clear distinction between when to use `load` vs `read`.
- **Fix:** Document the convention: `load` = returns processed data, `read` = returns raw/file data.

#### 5M-2. `hdr_mapping_kwargs` passed as `dict | None` instead of typed dataclass
- **File:** `src/spektrafilm_gui/controller.py:549, 583–589`
- HDR mapping parameters are assembled as a raw dict and passed through `save_image_oiio` to `HDRPhotoMapping(**hdr_mapping_kwargs)`. This bypasses IDE autocomplete and static type checking.
- **Fix:** Construct `HDRPhotoMapping` directly in the controller and pass the typed object.

#### 5M-3. `SettingsParams.hanatos2025_sensitiviy_adaptation` has a typo
- **File:** `src/spektrafilm/runtime/params_schema.py:208`
- "sensitiviy" should be "sensitivity". A property alias exists at line 219 but the typo persists in the underlying field.
- **Fix:** Rename the field and provide a deprecated property for backward compatibility.

#### 5M-4. `_output_path_with_default_extension` uses regex but could use `Path.suffix`
- **File:** `src/spektrafilm_gui/controller.py:92–101`
- Uses `re.findall` to parse file filter strings. This is fragile if the filter format changes.

#### 5M-5. `_process_image_with_runtime` returns different types
- **File:** `src/spektrafilm_gui/controller.py:905–926`
- Returns `np.ndarray` from `process()` or `SimulationPipelineResult` from `process_with_metadata()`. The caller doesn't distinguish — it just works because `SimulationPipelineResult` has `.image` but also has other fields that are silently discarded when the controller treats the result as an ndarray.
- **Fix:** Always use `process_with_metadata()` and handle the `SimulationPipelineResult` consistently.

### LOW

#### 5L-1. `_ICC_FILENAMES` and `_ICC_PROFILES` serve similar but different purposes
- **File:** `src/spektrafilm/utils/io.py:164–231`
- Two dictionaries mapping color space names to ICC file paths, with overlapping entries. `_ICC_FILENAMES` is keyed by `(name, cctf_encoded)`, `_ICC_PROFILES` is keyed by name only.

#### 5L-2. `profile_type: ProfileType` uses a Literal type alias
- **File:** `src/spektrafilm/model/emulsion.py:12`
- `ProfileType = Literal['negative', 'positive']` duplicates the `PROFILE_TYPES` frozenset in `profiles/io.py`.

#### 5L-3. `DiffusionFilterParams` has complex inline documentation
- **File:** `src/spektrafilm/runtime/params_schema.py:10–41`
- Field comments are excellent but would be better as docstrings for IDE hover support.

---

## 6. Test Coverage Gaps

### HIGH

#### 6H-1. No tests for `save_image_oiio` EXR HDR rendition mode
- **File:** `src/spektrafilm/utils/io.py:634–648`
- The `exr_mode="hdr_rendition"` code path calls `prepare_hdr_photo_renditions` but there are no unit tests verifying the EXR output pixels differ from the archive path.

#### 6H-2. No tests for `load_and_process_raw_file` error paths
- **File:** `src/spektrafilm/utils/raw_file_processor.py:504–605`
- The function has multiple branches (white balance modes, lens correction, color space conversion) but `tests/test_raw_file_processor.py` only tests a subset. The `return_diagnostics=True` path and tint adjustment are untested.

#### 6H-3. No tests for `_apply_hdr_color_recovery` color modes
- **File:** `src/spektrafilm/utils/hdr_photo.py:602–709`
- Three highlight color modes (`off`, `source_chroma`, `bounded_look_chroma`) with complex blending logic. Only the `off` mode is implicitly tested via integration tests.

### MEDIUM

#### 6M-1. `SimulationPipeline.process_with_metadata` has no dedicated tests
- **File:** `src/spektrafilm/runtime/pipeline.py:313–335`
- The HDR metadata collection path (scene luminance, scene RGB, profile characterization) is only tested indirectly through the GUI controller tests.

#### 6M-2. GPU backend selection has minimal edge-case coverage
- **File:** `src/spektrafilm/gpu/backend.py:64–99`
- The `auto` fallback chain (MLX → CuPy → NumPy) is tested but environment variable overrides (`SPEKTRAFILM_GPU_TILE_PIXELS`) are not.

#### 6M-3. `color_management.py` ACES workflow presets untested
- **File:** `src/spektrafilm/color_management.py:49–70`
- Only `manual` and `aces_reference` workflows exist. The error path for unsupported workflow strings is untested.

#### 6M-4. `_write_png_rgb16` custom PNG writer has no edge-case tests
- **File:** `src/spektrafilm/utils/io.py:753–772`
- The custom PNG writer handles ICC profiles and 16-bit encoding but has no tests for empty images, single-pixel images, or ICC profile embedding.

### LOW

#### 6L-1. `profile_to_dict` / `_json_safe` have no round-trip tests
- **File:** `src/spektrafilm/profiles/io.py:212–235`
- Serialization/deserialization is tested via `load_profile`/`save_profile` but the recursive dict conversion and NaN handling are not directly tested.

#### 6L-2. `_extension_from_selected_filter` regex edge cases
- **File:** `src/spektrafilm_gui/controller.py:104–110`
- The regex `r"\*\.([A-Za-z0-9]+)"` could fail on unusual filter strings.

---

## 7. Performance Anti-patterns

### HIGH

#### 7H-1. `_known_encoding_from_icc_profile` loads all ICC profiles on every call
- **File:** `src/spektrafilm/utils/io.py:376–401`
- For every image load, this function iterates `_ICC_FILENAMES` (14 entries) and `_ICC_PROFILES` (8 entries), loading each ICC file from disk via `importlib.resources` and comparing bytes. This is O(n) disk reads per image.
- **Fix:** Cache loaded ICC profile bytes at module level using `@lru_cache` or a module-level dict.

#### 7H-2. `characterize_pipeline_profile` creates a full temporary pipeline
- **File:** `src/spektrafilm/runtime/pipeline.py:163–192`
- Every `process_with_metadata` call creates a deep copy of params, instantiates a new `SimulationPipeline`, and renders a 512-pixel ramp. This is expensive (hundreds of ms) and happens on every preview.
- **Fix:** Cache the characterization result per (film, paper) pair.

### MEDIUM

#### 7M-1. `np.asarray` called redundantly on already-numpy arrays
- **Files:** Multiple locations in `hdr_photo.py`, `pipeline.py`
- e.g., `hdr_photo.py:305`: `image = np.asarray(image_data)` when `image_data` is already validated as ndarray. `hdr_photo.py:418`: `y = np.maximum(np.asarray(scene_y, dtype=np.float32), 0.0)` — `np.maximum` already handles conversion.

#### 7M-2. `_prepare_hdr_rgb` validates and copies the entire image
- **File:** `src/spektrafilm/utils/hdr_photo.py:304–316`
- `np.asarray(image[..., :3], dtype=np.float32)` creates a full copy of potentially 50MP+ images. If the input is already float32 with 3 channels, this is a wasteful copy.

#### 7M-3. `_graft_scene_luminance` computes `look_y = np.max(look, axis=2)` instead of using `luminance_y`
- **File:** `src/spektrafilm/utils/hdr_photo.py:842`
- Uses max-channel intensity instead of perceptual luminance (0.2126R + 0.7152G + 0.0722B). This is inconsistent with `_prepare_profile_aware_renditions` which uses `luminance_y()`.

### LOW

#### 7L-1. `lru_cache` on `_known_rgb_colourspaces` with `maxsize=1`
- **File:** `src/spektrafilm/color_management.py:23`
- The colour-science library's `RGB_COLOURSPACES` is a global dict that doesn't change. `maxsize=1` is fine but could be `maxsize=None` since it never needs eviction.

#### 7L-2. `_load_coeffs_lut` uses Python loops for binary parsing
- **File:** `src/spektrafilm/utils/spectral_upsampling.py:141–159`
- Nested Python `for` loops reading struct data. Could use `np.fromfile` for faster loading.

---

## 8. Security Concerns

### HIGH

#### 8H-1. `subprocess.run` with user-influenced file paths in HEIC export
- **File:** `src/spektrafilm/utils/hdr_photo.py:282–288`
- `subprocess.run(command, ...)` passes file paths as arguments to a Swift script. While `check=False` and `shell=False` (default) are used, the file paths come from user GUI input. A malicious filename with special characters could cause issues if the Swift script doesn't handle them properly.
- **Risk:** Low-medium. The paths go through `Path()` normalization and are passed as list args (not shell-interpolated), but the Swift encoder script should validate its inputs.
- **Fix:** Validate that output paths don't contain null bytes or control characters.

### MEDIUM

#### 8M-1. `save_profile` writes to package data directory
- **File:** `src/spektrafilm/profiles/io.py:281–289`
- `pkg_resources.files('spektrafilm.data.profiles')` opens a resource for writing. Depending on installation method (wheel, editable install), this may write to a shared location, fail silently, or require elevated permissions.
- **Fix:** Write to a user-configurable data directory, not the package resource path.

#### 8M-2. `save_neutral_print_filters` writes to package data directory
- **File:** `src/spektrafilm/utils/io.py:781–785`
- Same issue as 8M-1.

### LOW

#### 8L-1. `np.random.seed` in grain model affects global state
- **File:** `src/spektrafilm/model/grain.py:23`
- `np.random.seed(seed)` sets the global NumPy random state, which can affect other concurrent operations. Should use `np.random.Generator` for local state.

---

## Prioritized Action Plan

### Must Fix (blocks correctness or reliability)

| ID | Finding | Effort |
|---|---|---|
| 2M-4 | `_pipeline_debug` can return `None` | 5 min |
| 5H-1 | `save_image_oiio` inconsistent return type | 30 min |
| 5H-2 | `IOParams.full_image` silent no-op | 10 min |
| 3H-1 | Dead `_run_simulation` method | 5 min |
| 3H-2 | Dead `_should_tile_mlx_image` aliases | 5 min |
| 4H-1 | `_runtime_dtype` quadruplicated | 30 min |
| 7H-1 | ICC profile loading on every image read | 15 min |

### Should Fix (improves quality and maintainability)

| ID | Finding | Effort |
|---|---|---|
| 1H-1 | `save_image_oiio` return annotation | 5 min |
| 1H-2 | `SimulationPipeline.__init__` types | 10 min |
| 2H-1 | Silent exception in `read_image_metadata` | 10 min |
| 2H-3 | `print()` instead of `logging.warning()` | 15 min |
| 4M-1 | Duplicated luminance computation | 20 min |
| 5M-3 | `sensitiviy` typo in SettingsParams | 10 min |
| 6H-3 | Missing HDR color recovery tests | 60 min |
| 7H-2 | Pipeline characterization on every preview | 30 min |
| 8M-1 | `save_profile` writes to package dir | 20 min |

### Nice to Have (polish)

| ID | Finding | Effort |
|---|---|---|
| 1M-1 | Standardize docstring style | 2 hrs |
| 3M-2 | Remove commented-out code blocks | 10 min |
| 4M-3 | Profile property delegation | 15 min |
| 5M-2 | Typed `hdr_mapping_kwargs` | 30 min |
| 8L-1 | Use `np.random.Generator` | 15 min |
