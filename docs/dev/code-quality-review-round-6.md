# Code Quality Review — Round 6

Date: 2026-05-27
Scope: Full `src/spektrafilm/` and `src/spektrafilm_gui/` codebase, plus test coverage analysis.

## Findings Summary

| Category | Count | Severity |
|---|---|---|
| Type Hints & Docstrings | 8 | Medium-Low |
| Error Handling | 5 | Medium-High |
| Dead Code & Unused Imports | 7 | Low-Medium |
| Code Duplication | 4 | Medium |
| API Consistency | 6 | Medium |
| Test Coverage Gaps | 8 | Medium-High |
| Performance Anti-Patterns | 5 | Medium |
| Security Concerns | 2 | Low |

Total: 45 findings.

---

## 1. Type Hints and Docstrings

### TH-1. Inconsistent `FloatArray` type alias — float64 vs float32 mismatch

- File: `src/spektrafilm/model/emulsion.py:12`
- `FloatArray` is aliased to `NDArray[np.float64]`, but the CLAUDE.md mandates float32 throughout for GPU parity. The model layer uses float64 internally (density curves, exposure), while the runtime pipeline and GPU backends use float32. The type alias creates a false contract.
- Fix: Either rename to `Float64Array` and add a `Float32Array` alias, or change the alias to `np.float32` if the model layer can be migrated. At minimum, document why the model layer uses float64.

### TH-2. Missing type hints on model-layer functions

- Files: `src/spektrafilm/model/couplers.py:9-10`, `src/spektrafilm/model/couplers.py:69-76`, `src/spektrafilm/model/couplers.py:135-145`, `src/spektrafilm/model/grain.py:12-20`, `src/spektrafilm/model/grain.py:52`, `src/spektrafilm/model/grain.py:65-75`, `src/spektrafilm/model/grain.py:111-124`, `src/spektrafilm/model/grain.py:165-175`, `src/spektrafilm/model/diffusion.py:14`, `src/spektrafilm/model/diffusion.py:31`, `src/spektrafilm/model/diffusion.py:91`, `src/spektrafilm/model/diffusion.py:97`, `src/spektrafilm/model/diffusion.py:549`
- Multiple functions in couplers.py, grain.py, and diffusion.py lack parameter and return type hints. The `backend=None` parameter appears without `ArrayBackend | None` annotation in 8+ locations.
- Fix: Add `ArrayBackend | None = None` annotation to all `backend` parameters. Add return types to all public functions.

### TH-3. Missing docstrings on GPU backend methods

- Files: `src/spektrafilm/gpu/numpy_backend.py:18-67`, `src/spektrafilm/gpu/mlx_backend.py:53-118`, `src/spektrafilm/gpu/cupy_backend.py:46-105`
- The `ArrayBackend` protocol has no docstrings on its methods. The concrete implementations (NumpyBackend, MlxBackend, CupyBackend) also lack docstrings on every method.
- Fix: Add one-line docstrings to the Protocol methods; concrete implementations can inherit.

### TH-4. Missing return type on `MlxBackend` methods

- File: `src/spektrafilm/gpu/mlx_backend.py:53-118`
- All methods in `MlxBackend` (except `to_numpy`, `eval`, `max`) lack return type annotations. Compare with `NumpyBackend` where all methods have `-> np.ndarray` or `-> float`.
- Fix: Add `-> Any` or specific return types to match the Protocol.

### TH-5. Inconsistent docstring style across modules

- Files: `src/spektrafilm/model/couplers.py` (Google style Args/Returns), `src/spektrafilm/utils/io.py` (NumPy style Parameters/Returns), `src/spektrafilm/utils/hdr_photo.py` (NumPy style), `src/spektrafilm/model/grain.py` (no docstrings)
- The codebase mixes Google-style and NumPy-style docstrings.
- Fix: Standardize on NumPy style (already dominant in utils/ and the protocol layer).

### TH-6. `_deserialize_dataclass` lacks type annotation for return

- File: `src/spektrafilm_gui/persistence.py:67`
- `_deserialize_dataclass(cls, data)` returns `GuiStateType` but the generic TypeVar is not bound. The function works for any dataclass, not just `GuiState`.
- Fix: Bind `GuiStateType` or add a `@overload` for `GuiState`.

### TH-7. `profile_to_dict` has no return type annotation

- File: `src/spektrafilm/profiles/io.py:218`
- `def profile_to_dict(data):` — no type hints at all.
- Fix: `def profile_to_dict(data: Any) -> dict[str, Any] | list[Any] | Any:`

### TH-8. `_read_exif_metadata` uses non-standard docstring `Returns:` section

- File: `src/spektrafilm/utils/raw_file_processor.py:278`
- Uses `Returns:` with a colon (Sphinx style) instead of the `Returns\n-------` NumPy style used elsewhere.
- Fix: Align to NumPy style.

---

## 2. Error Handling

### EH-1. Broad `except Exception` in GUI controller

- Files: `src/spektrafilm_gui/controller.py:531`, `src/spektrafilm_gui/controller.py:599`, `src/spektrafilm_gui/controller.py:917`
- The controller catches `Exception` broadly during save and processing operations. This swallows unexpected errors (KeyError, TypeError, etc.) that should propagate or be logged with full context.
- Fix: Catch specific exceptions (`OSError`, `RuntimeError`, `ValueError`) and log the full traceback at ERROR level before re-raising or returning a user-visible error.

### EH-2. `_probe_device` catches all exceptions

- File: `src/spektrafilm/gpu/mlx_backend.py:44`
- `except Exception as exc:` — catches everything including `KeyboardInterrupt` (in Python <3.11) and `SystemExit`. Should be `except (RuntimeError, OSError) as exc:`.
- Fix: Narrow to `except (RuntimeError, OSError, ImportError)`.

### EH-3. CuPy device query catches all exceptions

- File: `src/spektrafilm/gpu/cupy_backend.py:30`
- `except Exception as exc:` on `cp.cuda.runtime.getDeviceCount()`.
- Fix: Catch `except (RuntimeError, cuda.runtime.CUDARuntimeError)` or at minimum `except (RuntimeError, OSError)`.

### EH-4. `save_neutral_print_filters` re-raises without context

- File: `src/spektrafilm/utils/io.py:867-868`
- `except OSError as exc:` then `raise` — good, but the `_log.error` message doesn't include the file path.
- Fix: Include the resource path in the log message.

### EH-5. Missing validation on `load_dichroic_filters` and `load_filter` CSV data

- Files: `src/spektrafilm/utils/io.py:894-908`, `src/spektrafilm/utils/io.py:910-926`
- `np.loadtxt` is called on user-path-derived CSV files without validating the file contents (NaN, wrong column count, empty file). The `_validate_path_component` only checks the name, not the file contents.
- Fix: Add a try/except around `np.loadtxt` and validate array shape after loading.

---

## 3. Dead Code and Unused Imports

### DC-1. Unused imports in `__init__.py` re-export files

- Files: `src/spektrafilm/__init__.py:3-6`, `src/spektrafilm/runtime/__init__.py:3-7`, `src/spektrafilm/gpu/__init__.py:3`, `src/spektrafilm/utils/__init__.py:3`, `src/spektrafilm/profiles/__init__.py:3`
- These files import names for re-export but the names are never used within the file. This is intentional for `__all__`-free re-exports, but `__all__` is not defined in most of these files, so static analyzers flag them.
- Fix: Add `__all__` to each `__init__.py` that re-exports, or use `# noqa: F401` comments.

### DC-2. Unused import `PIL.Image` and `PIL.ImageCms` in io.py

- File: `src/spektrafilm/utils/io.py:20-21`
- `PIL.Image` is used only in the `save_image_oiio` JPEG/PNG path (line 680). `PIL.ImageCms` is used only in `resolve_icc_profile_bytes` (line 256). Both are used, but the static analyzer flags them because they're imported at module level but used in conditional branches.
- Fix: Move imports to the functions that use them (lazy import pattern already used elsewhere).

### DC-3. Unused import `scipy.interpolate` in io.py

- File: `src/spektrafilm/utils/io.py:22`
- `scipy.interpolate` is imported at module level but only used in `load_dichroic_filters` and `load_filter`.
- Fix: Move to local import in those functions.

### DC-4. Unused import `scipy.ndimage` in diffusion.py

- File: `src/spektrafilm/model/diffusion.py:4`
- `scipy.ndimage` is imported but the code uses `fast_gaussian_filter` instead. The commented-out code on lines 59-60 and 104 references `scipy.ndimage.gaussian_filter`.
- Fix: Remove the unused import.

### DC-5. Unused import `boost_highlights` in diffusion.py

- File: `src/spektrafilm/model/diffusion.py:12`
- `boost_highlights` is imported but never called in the file.
- Fix: Remove the unused import.

### DC-6. `__main__` blocks with matplotlib/benchmark code in 14 source files

- Files: `src/spektrafilm/model/color_filters.py:164`, `src/spektrafilm/model/illuminants.py:57`, `src/spektrafilm/model/couplers.py:183`, `src/spektrafilm/model/grain.py:222`, `src/spektrafilm/utils/fast_gaussian_filter.py:355`, `src/spektrafilm/utils/calibration_targets.py:150`, `src/spektrafilm/utils/spectral_upsampling.py:649`, `src/spektrafilm/utils/fast_interp_lut.py:649`, `src/spektrafilm/utils/fast_stats.py:236`, `src/spektrafilm/utils/autoexposure.py:239`, `src/spektrafilm/utils/lut.py:151`, `src/spektrafilm/utils/numba_boost_hightlights.py:128`, `src/spektrafilm/utils/fft_gaussian_filter.py:103`, `src/spektrafilm/utils/fast_interp.py:119`
- These blocks contain benchmark/visualization code with `matplotlib.pyplot.show()` and `time.time()`. They're not tests and not part of the public API.
- Fix: Move benchmark code to `benchmarks/` directory or `scripts/`. Keep `__main__` blocks minimal (warmup only).

### DC-7. `grain.py:222-244` — matplotlib visualization in `__main__`

- File: `src/spektrafilm/model/grain.py:222-244`
- Contains a full matplotlib visualization block that imports `matplotlib.pyplot` and calls `plt.show()`. This is development/debug code, not a test.
- Fix: Move to a dedicated benchmark or test file.

---

## 4. Code Duplication

### CD-1. Duplicated `is_*` property delegation in `Profile` and `ProfileInfo`

- Files: `src/spektrafilm/profiles/io.py:53-91` (ProfileInfo) and `src/spektrafilm/profiles/io.py:157-195` (Profile)
- `Profile` duplicates every `is_*` property from `ProfileInfo` (is_positive, is_negative, is_paper, is_film, is_color, is_bw, is_filming, is_printing, is_still, is_cine). That's 10 properties that just delegate to `self.info.*`.
- Fix: Use `__getattr__` delegation or remove the duplicates from `Profile` since callers can access `profile.info.is_positive`.

### CD-2. Duplicated ICC profile loading patterns

- Files: `src/spektrafilm/utils/io.py:194-203` (`_load_icc_profile`) and `src/spektrafilm/utils/io.py:382-391` (`_load_icc_profile_from_extra`)
- Both functions follow the same pattern: look up a path, join with `pkg_resources.files(...)`, call `read_bytes()`, catch `FileNotFoundError/OSError`.
- Fix: Extract a shared `_load_resource_bytes(relative_path: str) -> bytes | None` helper.

### CD-3. Duplicated array normalization in hdr_photo.py

- Files: `src/spektrafilm/utils/hdr_photo.py:367` (`_paper_logistic_progress`) and `src/spektrafilm/utils/hdr_photo.py:403` (`_paper_logarithmic_progress`)
- Both functions start with identical boilerplate: `np.maximum(np.asarray(scene_y, dtype=np.float32), 0.0)`, check `above = y > s`, return `out` if not `np.any(above)`.
- Fix: Extract a shared `_prepare_scene_y(scene_y, start)` helper.

### CD-4. Duplicated GPU backend method signatures

- Files: `src/spektrafilm/gpu/numpy_backend.py`, `src/spektrafilm/gpu/mlx_backend.py`, `src/spektrafilm/gpu/cupy_backend.py`
- All three backends implement identical method signatures (16 methods each) with no shared base class. Adding a new method requires editing 3 files.
- Fix: Consider a `BaseBackend` with default implementations for `eval`/`synchronize`/`abs`, or use the Protocol more effectively with `@runtime_checkable`.

---

## 5. API Consistency

### AC-1. Inconsistent `backend` parameter typing

- Files: `src/spektrafilm/model/couplers.py:42` (`def compute_dir_couplers_matrix(couplers_params)`), `src/spektrafilm/model/couplers.py:69` (`backend=None`), `src/spektrafilm/model/grain.py:165` (`backend=None`), `src/spektrafilm/model/diffusion.py:14` (`backend=None`)
- The `backend` parameter is typed as `None` (no annotation) in model functions, while `ArrayBackend` Protocol exists. Some functions use `backend=None`, others use `backend: ArrayBackend | None = None`.
- Fix: Add `ArrayBackend | None = None` consistently.

### AC-2. Inconsistent return type from `save_image_oiio`

- File: `src/spektrafilm/utils/io.py:531-755`
- Returns `tuple[str, ...]` (empty tuple `()` for non-HDR, diagnostics for HDR). The caller must know which branch was taken to interpret the return value. For HEIC, it delegates to `save_hdr_photo_heic` which returns diagnostics.
- Fix: Document the return contract clearly. Consider returning a typed result object instead of a bare tuple.

### AC-3. Mixed `np.random` legacy API and modern Generator API

- Files: `src/spektrafilm/model/grain.py:22` (`np.random.seed`), `src/spektrafilm/utils/fast_stats.py:49,56,65,115,118,161` (legacy `np.random.rand/randn`)
- The grain model uses `np.random.seed()` which sets global state and is not thread-safe. The fast_stats numba functions use legacy `np.random.rand()` which is deprecated in favor of `np.random.default_rng()`.
- Note: Numba njit functions require the legacy API for `np.random.rand()` — this is a Numba constraint, not a code smell. But `grain.py:22` `np.random.seed(seed)` is a real issue.
- Fix: For `grain.py`, pass a `numpy.random.Generator` instance or use a local seed. For numba functions, document the constraint.

### AC-4. `getattr(mapping, ...)` on a frozen dataclass with known fields

- Files: `src/spektrafilm/utils/hdr_photo.py:506,700,718,719,720,722,732,799`
- `HDRPhotoMapping` is a frozen dataclass with all fields defined, yet the code uses `getattr(mapping, "profile_hdr_path_to_white_strength", 0.30)` with defaults. This is defensive coding against older mapping instances that might lack newer fields, but since `HDRPhotoMapping` is frozen and all fields have defaults, `getattr` is unnecessary.
- Fix: Access fields directly: `mapping.profile_hdr_path_to_white_strength`. If backward compatibility with unpickled old instances is needed, document why `getattr` is used.

### AC-5. Inconsistent validation approach across dataclasses

- Files: `src/spektrafilm/utils/hdr_photo.py:133-232` (extensive `__post_init__`), `src/spektrafilm/color_management.py:99-117` (moderate `__post_init__`), `src/spektrafilm/profiles/io.py:108-125` (only array coercion), `src/spektrafilm/utils/raw_file_processor.py:22-48` (no validation)
- `HDRPhotoMapping` has 100+ lines of validation. `ColorEncoding` has moderate validation. `ExifData` and `RawImportDiagnostics` have none. `ProfileData` only coerces arrays.
- Fix: Add basic validation to `ExifData` (e.g., `focal_length >= 0`) and `RawImportDiagnostics` (e.g., `0 <= clip_fraction <= 1`).

### AC-6. `ProfileData.__post_init__` silently reshapes empty arrays

- File: `src/spektrafilm/profiles/io.py:112-126`
- If `hanatos2025_adaptation_bandpass_params` is empty, it's replaced with `_empty_matrix()` (shape `(0, 3)`). But the original might have been `(0,)` — this silent reshape could mask data issues.
- Fix: Validate shape before reshaping, or document the expected input format.

---

## 6. Test Coverage Gaps

### TC-1. No tests for model layer modules

- Files without tests: `src/spektrafilm/model/glare.py`, `src/spektrafilm/model/color_filters.py`, `src/spektrafilm/model/illuminants.py`, `src/spektrafilm/model/diffusion.py`, `src/spektrafilm/model/stocks.py`, `src/spektrafilm/model/density_curves.py`
- 6 out of 8 model modules have zero test coverage. The model layer is the core physics simulation — untested model code means regressions in film simulation accuracy are undetectable.
- Fix: Add at least smoke tests (known input → expected output within tolerance) for each model module.

### TC-2. No tests for profile I/O round-tripping

- File: `src/spektrafilm/profiles/io.py` — no corresponding test file.
- `profile_from_dict`, `profile_to_dict`, `save_profile`, `load_profile`, `_validate_profile` are untested.
- Fix: Add round-trip tests: save a profile, load it, assert equality.

### TC-3. No tests for GPU backend protocol compliance

- Files: `src/spektrafilm/gpu/numpy_backend.py`, `src/spektrafilm/gpu/mlx_backend.py`, `src/spektrafilm/gpu/cupy_backend.py` — no dedicated test files.
- The GPU backends are tested indirectly through `test_gpu_*.py` tests, but there's no test that verifies the Protocol contract (all methods present, correct signatures).
- Fix: Add a `test_backend_protocol.py` that checks each backend against `ArrayBackend`.

### TC-4. No tests for `fast_gaussian_filter` edge cases

- File: `src/spektrafilm/utils/fast_gaussian_filter.py` — no test file.
- The filter has complex edge handling (reflect mode), IIR/FIR dispatch, and multi-channel support. None of this is directly tested.
- Fix: Add tests for: sigma=0 (identity), sigma < 0.5 (IIR fallback), 2D and 3D inputs, edge reflection correctness.

### TC-5. No tests for `timings.py` formatting

- File: `src/spektrafilm/utils/timings.py` — no test file.
- `format_elapsed_time` and `format_timings` have branching logic (seconds/ms/us, percentage calculation).
- Fix: Add unit tests for boundary values (0, 0.001, 1, 100).

### TC-6. No tests for `_validate_path_component` security

- File: `src/spektrafilm/utils/io.py:887-891`
- The regex-based path validation is a security boundary but has no tests.
- Fix: Add tests for: valid names, names with `../`, names with special characters.

### TC-7. No tests for persistence round-tripping

- File: `src/spektrafilm_gui/persistence.py` — no test file (GUI tests skipped on Linux).
- `gui_state_to_dict`/`gui_state_from_dict` and `_deserialize_dataclass` are untested.
- Fix: Add non-GUI tests for the serialization/deserialization logic (it doesn't require Qt).

### TC-8. 517 test functions across 54 test files, but 66 source files

- Coverage ratio: ~7.8 test functions per source file, but distribution is uneven. Core model modules have 0 tests while utils and GUI have good coverage.
- Fix: Prioritize model-layer tests in the next test sprint.

---

## 7. Performance Anti-Patterns

### PA-1. Unnecessary `np.asarray` calls on already-array data

- Files: `src/spektrafilm/model/emulsion.py:23,25,58`, `src/spektrafilm/model/diffusion.py:56-74`
- `np.asarray(channel_density)` is called on parameters that are already `FloatArray` (NDArray). Each call creates a new array object if the input is not already contiguous.
- Fix: Use `np.ascontiguousarray` only when the downstream code requires contiguous memory, or skip the call when the type contract guarantees array input.

### PA-2. `FloatArray` type alias uses float64, causing implicit float64 promotion

- File: `src/spektrafilm/model/emulsion.py:12`
- `FloatArray = NDArray[np.float64]` — the model layer operates in float64. When the pipeline feeds float32 data into model functions, `np.asarray(x, dtype=float)` silently promotes to float64, doubling memory usage.
- Fix: Either make the model layer float32-aware (matching GPU constraint) or document the float64→float32 conversion boundary.

### PA-3. Redundant `.astype(np.float32, copy=False)` after `np.clip`

- Files: `src/spektrafilm/utils/hdr_photo.py:503,504,614,621,623,745,933,953,976`
- Pattern: `np.clip(x, 0.0, h).astype(np.float32, copy=False)` — if `x` is already float32, `np.clip` returns float32, and the `.astype` is a no-op. But it's called 9+ times.
- Fix: Remove `.astype(np.float32, copy=False)` when the input is guaranteed float32. Use it only at conversion boundaries.

### PA-4. `gamut_map_oklch` creates many temporary arrays per iteration

- File: `src/spektrafilm/utils/hdr_photo.py:1118-1125`
- The binary search loop (16 iterations) creates `_oklch_to_linear_srgb(L, C_mid, h)` → `_srgb_to_linear(trial_g)` → `np.all(...)` each iteration. For a 4K image, each iteration allocates ~3 arrays of shape (H, W, 3).
- Fix: Pre-allocate `trial` and `trial_g` buffers and reuse them across iterations.

### PA-5. `_apply_per_channel` copies each channel slice

- File: `src/spektrafilm/utils/fast_gaussian_filter.py:258`
- `ch_in = np.ascontiguousarray(image[:, :, ch])` — for a 3-channel 4K image, this creates 3 contiguous copies of ~96MB each.
- Fix: Use `np.ascontiguousarray` on the full 3D array once, then index with stride tricks or accept non-contiguous channel slices (numba can handle C-contiguous 2D slices from a 3D array).

---

## 8. Security Concerns

### SC-1. `_validate_path_component` regex is correct but incomplete

- File: `src/spektrafilm/utils/io.py:884-891`
- The regex `^[A-Za-z0-9_-]+$` prevents path traversal in path components used to construct `importlib.resources` paths. This is good. However, the validation is only applied to `load_dichroic_filters` and `load_filter`, not to `load_profile` (which uses `_validate_stock_name` with the same regex — good).
- Status: Adequate. No action needed.

### SC-2. `subprocess.run` in `save_hdr_photo_heic` — safe but worth noting

- File: `src/spektrafilm/utils/hdr_photo.py:313-319`
- `subprocess.run(command, check=False, capture_output=True, text=True, timeout=300)` — the command is constructed from `shutil.which("xcrun")` and `_encoder_script_path()` (a package resource). No user-provided strings are interpolated into the command. `shell=False` (default). Timeout is set.
- Status: Safe. No action needed.

### SC-3. No path traversal protection on `load_gui_state_from_path`

- File: `src/spektrafilm_gui/persistence.py:54-57`
- `load_gui_state_from_path(path)` opens an arbitrary file path without validation. In the GUI context, the path comes from `QFileDialog` (user-selected), which is acceptable. But the function is also importable for non-GUI use.
- Risk: Low. The function is a thin wrapper around `json.load` — no code execution.
- Fix: Consider adding a path validation parameter for programmatic callers.

### SC-4. `np.random.seed` in grain model — global state mutation

- File: `src/spektrafilm/model/grain.py:22`
- `np.random.seed(seed)` mutates the global random state, which is not thread-safe and can affect other code in the same process.
- Risk: Low (no security impact, but correctness risk in concurrent contexts).
- Fix: Use `np.random.default_rng(seed)` and pass the Generator to sampling functions.

---

## Prioritized Action List

### High Priority (correctness/quality)

1. **PA-2/TH-1**: Document or fix the float64/float32 boundary in the model layer. This is the most impactful architectural issue.
2. **TC-1**: Add smoke tests for the 6 untested model modules. Core physics simulation without tests is the biggest quality risk.
3. **EH-1**: Narrow the `except Exception` in the GUI controller to prevent swallowing unexpected errors.
4. **AC-4**: Replace `getattr(mapping, ...)` with direct field access on the frozen dataclass.
5. **DC-6**: Move `__main__` benchmark/visualization code to a `benchmarks/` directory.

### Medium Priority (consistency/maintainability)

6. **AC-1**: Add `ArrayBackend | None = None` type annotation to all `backend` parameters.
7. **TH-2**: Add type hints to all model-layer public functions.
8. **CD-1**: Remove duplicated `is_*` properties from `Profile` or use `__getattr__` delegation.
9. **DC-2/DC-3**: Move `PIL.*` and `scipy.interpolate` imports to local scope in io.py.
10. **TC-4**: Add edge-case tests for `fast_gaussian_filter`.

### Low Priority (cleanup)

11. **DC-1**: Add `__all__` to `__init__.py` files that re-export.
12. **TH-5**: Standardize on NumPy-style docstrings across all modules.
13. **DC-4/DC-5**: Remove unused imports in `diffusion.py`.
14. **PA-4**: Pre-allocate buffers in `gamut_map_oklch` binary search loop.
15. **SC-4**: Replace `np.random.seed` with `np.random.default_rng` in grain.py.

---

## Metrics

| Metric | Value |
|---|---|
| Source files | 66 |
| Test files | 54 |
| Test functions | 517 |
| Source files without tests | 20+ |
| `__main__` blocks in src/ | 14 |
| Bare `except Exception` | 5 |
| Unused imports (non-`__init__`) | ~15 |
| Files using `from __future__ import annotations` | 29/66 (44%) |
| Largest file | `hdr_photo.py` (1360 lines) |
| Lines of `__post_init__` validation | ~100 (hdr_photo.py) |
