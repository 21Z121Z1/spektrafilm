# Code Quality Review — Round 5

**Date:** 2026-05-27
**Scope:** Full read-only review of `src/`, `tests/`, and project configuration
**Focus areas:** Type hints, error handling, dead code, duplication, API consistency, test coverage, performance, security

## Summary

| Severity | Count |
|----------|-------|
| Critical | 0     |
| High     | 6     |
| Medium   | 12    |
| Low      | 10    |

## Findings

---

### H1. Mutable default arguments in `CalibrationTarget` methods

**File:** `src/spektrafilm/utils/calibration_targets.py:53,60,67,74`
**Category:** Bug / API Consistency

Multiple methods use mutable list literals as default arguments:

```python
def negative_exposure_ramp(self, values=[-3, -2, -1, 0, 1, 2, 3]):
def print_exposure_ramp(self, values=[0.3, 0.5, 0.7, 1.0, 1.5, 2.0, 3.0]):
def grain_ramp(self, values=[0.05, 0.1, 0.2, 0.4, 0.8, 1.6]):
def dir_couplers_ramp(self, values=[0.0, 0.5, 1.0, 1.5, 2.0]):
```

If a caller mutates the returned list, subsequent calls without explicit `values` will see the mutated default.

**Fix:** Change to `values: list[float] | None = None` and assign inside the body, or use `tuple` defaults.

---

### H2. Mutable default argument in `CalibrationTarget.__init__`

**File:** `src/spektrafilm/utils/calibration_targets.py:10`
**Category:** Bug

```python
def __init__(self, image, base_params=init_params(), ...):
```

`init_params()` is called once at class definition time and shared across all instances. Each `CalibrationTarget` instance will share the same `base_params` object, causing cross-instance mutation.

**Fix:** Use `base_params=None` and call `init_params()` inside `__init__` when `None`.

---

### H3. Inconsistent `exiv2.Exiv2Error` exception paths

**File:** `src/spektrafilm/utils/io.py:73` vs `src/spektrafilm/utils/raw_file_processor.py:288`
**Category:** Error Handling / API Consistency

`io.py` catches `exiv2.extras.Exiv2Error` while `raw_file_processor.py` catches `exiv2.Exiv2Error`. These may be different exception classes depending on the exiv2 binding version.

```python
# io.py:73
except (OSError, RuntimeError, exiv2.extras.Exiv2Error) as exc:

# raw_file_processor.py:288
except (OSError, RuntimeError, exiv2.Exiv2Error):
```

**Fix:** Unify to one canonical path. If both exist, catch both in both locations.

---

### H4. `except Exception` silently swallows all errors in GUI controller runtime path

**File:** `src/spektrafilm_gui/controller.py:917`
**Category:** Error Handling

```python
except Exception:
    self._runtime_simulator = None
    raise
```

While this re-raises, the bare `except Exception` at `controller.py:531` and `controller.py:599` catches metadata errors without logging them — they are only surfaced in a UI status message. If the UI is not visible (headless test, batch mode), the error is silently swallowed.

**Fix:** Log metadata exceptions at `WARNING` level before appending to `metadata_errors`.

---

### H5. Module-level side effects in `color_filters.py` create globals that may be `None`

**File:** `src/spektrafilm/model/color_filters.py:113-135`
**Category:** Error Handling / API Consistency

The module creates 9 global filter instances at import time. If data files are missing, all are set to `None`. Downstream code (e.g., `color_enlarger()`) uses these globals without `None` checks, leading to `AttributeError` at call time instead of clear error at import time.

```python
try:
    dichroic_filters = DichroicFilters()
    ...
except (FileNotFoundError, OSError) as exc:
    _log.warning(...)
    dichroic_filters = None
```

**Fix:** Either fail loudly at import time, or add `None` guards in `color_enlarger()` and any other consumers.

---

### H6. Typo in filename: `numba_boost_hightlights.py`

**File:** `src/spektrafilm/utils/numba_boost_hightlights.py`
**Category:** API Consistency

The filename has a typo: "hightlights" instead of "highlights". This propagates to all imports:

- `src/spektrafilm/model/diffusion.py:12`
- `src/spektrafilm/utils/numba_warmup.py:5`
- `src/spektrafilm/gpu/kernels/color.py:277`

**Fix:** Rename to `numba_boost_highlights.py` and update all import paths.

---

### M1. Unused imports across the codebase (31 instances)

**Category:** Dead Code
**Severity:** Medium

Ruff F401 detected 31 unused imports. Key instances:

| File | Line | Unused Import |
|------|------|---------------|
| `model/color_filters.py` | 4 | `colour` |
| `model/diffusion.py` | 12 | `boost_highlights` |
| `runtime/services/color_reference.py` | 4 | `Callable` |
| `utils/hdr_photo.py` | 26 | `profile_slope_loglog` |
| `gui/controller_runtime.py` | 12 | `SimulationPipelineResult` |
| `gui/widgets.py` | 3-42 | 20 re-exported names never used in module |
| `tests/test_edge_cases.py` | 199 | `_DIFFUSION_STRENGTH_TOTAL_FRACTION` |
| `tests/test_hdr_curve_profiles.py` | 147 | `enforce_monotonic_profile_curve` |
| `tests/test_hdr_photo.py` | 14,753,1096,1213 | 4 unused imports |

**Fix:** Remove unused imports. For `gui/widgets.py`, verify if these are public re-exports; if so, use `__all__` to document intent.

---

### M2. Unused local variables (5 instances)

**File:** Multiple
**Category:** Dead Code

| File | Line | Variable |
|------|------|----------|
| `gpu/kernels/color.py` | 173 | `beta` |
| `utils/hdr_photo.py` | 562 | `look_y` |
| `tests/test_edge_cases.py` | 223 | `w` |
| `tests/test_hdr_photo.py` | 753 | `sdr_look_y` |
| `tests/test_hdr_photo.py` | 1096 | `s_profile` |

**Fix:** Remove or prefix with `_` if intentionally unused.

---

### M3. `__main__` blocks in production source files

**File:** Multiple (9 files)
**Category:** Dead Code

9 source files under `src/` contain `if __name__ == '__main__':` blocks with matplotlib plotting and benchmarking code:

- `utils/fast_interp_lut.py:649` (170+ lines of matplotlib)
- `utils/fast_gaussian_filter.py:355`
- `utils/autoexposure.py:239`
- `utils/calibration_targets.py:138`
- `utils/numba_boost_hightlights.py:128`
- `model/color_filters.py:148` (138 lines of matplotlib)
- `gui/app.py:317`
- `gui/virtual_photo_paper_back.py:272`
- `gui/polaroid_animation.py:173`

These add import-time overhead (matplotlib) and are not executed in normal use.

**Fix:** Move to `scripts/` or `tools/` directories, or guard with `if __name__ == '__main__':` (already done, but the code still exists in the source tree). At minimum, remove `import matplotlib.pyplot as plt` from module-level in `color_filters.py:5` and `calibration_targets.py:2`.

---

### M4. Module-level matplotlib import in production code

**File:** `src/spektrafilm/model/color_filters.py:5`, `src/spektrafilm/utils/calibration_targets.py:2`
**Category:** Performance

`import matplotlib.pyplot as plt` at module level forces matplotlib initialization on every import of these modules, even when plotting is never used. This adds ~200ms to import time.

**Fix:** Move to `if __name__ == '__main__':` guard or lazy import.

---

### M5. GPU backend `Any` type annotations are too permissive

**File:** `src/spektrafilm/gpu/backend.py:13-31`, `cupy_backend.py`, `mlx_backend.py`, `numpy_backend.py`
**Category:** Type Hints

The `ArrayBackend` protocol and all implementations use `Any` for array parameters and return types. This defeats type checking for all GPU/CPU code paths.

```python
def asarray(self, value: Any, dtype: Any | None = None) -> Any: ...
def exp(self, x: Any) -> Any: ...
```

**Fix:** Use `TypeVar` or `numpy.typing.NDArray` for at least the return types. For protocol methods, `-> Any` is acceptable as a contract, but concrete implementations should annotate their actual return types.

---

### M6. Inconsistent `backend=None` parameter style across model modules

**File:** `model/emulsion.py:33,57`, `model/diffusion.py:14`, `gpu/kernels/*.py`
**Category:** API Consistency

Many functions accept `backend=None` without type annotation:

```python
def develop_simple(..., backend=None) -> FloatArray:
def apply_unsharp_mask(image, ..., *, backend=None):
```

While some use `backend: ArrayBackend | None = None`.

**Fix:** Add `backend: ArrayBackend | None = None` type annotation consistently.

---

### M7. Pipeline `del` statements for memory management

**File:** `src/spektrafilm/runtime/pipeline.py:577-594`
**Category:** Performance / Style

The pipeline methods use explicit `del` to free intermediate arrays:

```python
log_raw_film = self._runtime_array(self._filming_stage.expose(rgb_image))
del rgb_image
cmy_film = self._runtime_array(self._filming_stage.develop(log_raw_film))
del log_raw_film
```

While this is intentional for large image memory management, it makes the code harder to read and the `del` only removes the local reference — the GC timing is unchanged. For GPU arrays, `del` does not guarantee immediate device memory release.

**Fix:** Consider wrapping stages in functions that naturally scope variables, or document the intent with a comment. Keep the `del` pattern for now but add a brief comment explaining the memory pressure motivation.

---

### M8. `global` statements in GPU kernel caches

**File:** `src/spektrafilm/gpu/kernels/filters.py:36,110,169,228`, `density.py:38,96`, `lut.py:16`
**Category:** Code Quality

GPU kernels use module-level `global` variables as caches:

```python
_GAUSSIAN_FIR_KERNEL = None

def _get_gaussian_fir_kernel(mx):
    global _GAUSSIAN_FIR_KERNEL
    if _GAUSSIAN_FIR_KERNEL is not None:
        return _GAUSSIAN_FIR_KERNEL
```

This is not thread-safe and prevents garbage collection of compiled kernels.

**Fix:** Use `functools.lru_cache` or a class-level cache attribute. If thread safety is not needed (single-threaded GUI), document this assumption.

---

### M9. `save_neutral_print_filters` writes to package resources

**File:** `src/spektrafilm/utils/io.py:863-867`
**Category:** Security / Error Handling

```python
def save_neutral_print_filters(neutral_print_filters):
    package = pkg_resources.files('spektrafilm.data.filters')
    resource = package / NEUTRAL_PRINT_FILTERS_FILENAME
    with resource.open("w") as file:
        json.dump(neutral_print_filters, file, indent=4)
```

Writing to package resource paths may fail silently in installed (non-editable) packages or read-only environments. The function has no error handling.

**Fix:** Add try/except for `OSError` and log or raise with a clear message. Consider writing to user config directory instead.

---

### M10. `read_neutral_print_filters` raises generic `OSError` wrapping JSON decode errors

**File:** `src/spektrafilm/utils/io.py:870-877`
**Category:** Error Handling

```python
except (FileNotFoundError, json.JSONDecodeError) as exc:
    raise OSError(f"Failed to read neutral print filters: {exc}") from exc
```

`FileNotFoundError` is a subclass of `OSError`, so catching it and re-raising as `OSError` loses the specific exception type.

**Fix:** Let `FileNotFoundError` propagate naturally, or use a custom exception.

---

### M11. `config.py` uses module-level `colour` computation at import time

**File:** `src/spektrafilm/config.py:9-15`
**Category:** Performance

```python
STANDARD_OBSERVER_CMFS = colour.MSDS_CMFS["CIE 1931 2 Degree Standard Observer"].copy().align(SPECTRAL_SHAPE)
STANDARD_OBSERVER_LMS = colour.colorimetry.MSDS_CMFS_LMS["Stockman & Sharpe 2 Degree Cone Fundamentals"].copy().align(SPECTRAL_SHAPE)
```

These execute on every import of `config.py`, which is imported transitively by most modules. The `colour` library's data loading is not instant.

**Fix:** Use `functools.lru_cache` on a getter function, or accept the cost if profiling shows it's negligible.

---

### M12. `SimulationPipeline._reinitialize` is ~90 lines with no validation

**File:** `src/spektrafilm/runtime/pipeline.py:198-293`
**Category:** Code Quality

The `_reinitialize` method constructs 6 service objects and 3 stage objects with no validation of the params input. If params are malformed, errors surface deep in stage constructors with unclear context.

**Fix:** Add a brief params validation at the top of `_reinitialize` (e.g., check required fields are non-None).

---

### L1. Missing return type annotations on several utility functions

**File:** `utils/conversions.py:6,26`, `utils/autoexposure.py:16-22`, `model/color_filters.py:15,90,93,140`
**Category:** Type Hints

Functions like `density_to_light`, `compute_aces_conversion_matrix`, `sigmoid_erf`, `compute_band_pass_filter`, `color_enlarger` lack return type annotations.

**Fix:** Add `-> np.ndarray` return annotations.

---

### L2. Docstring style inconsistency

**File:** Multiple files
**Category:** Code Quality

Most of the codebase uses NumPy-style docstrings (Parameters/Returns sections with `---` underlines). However, some files use Google-style or no docstrings:

- `utils/conversions.py:6` uses `Parameters:` without underlines
- `model/emulsion.py` functions have no docstrings
- `gpu/kernels/*.py` functions have no docstrings
- `utils/fast_interp_lut.py` functions have minimal docstrings

**Fix:** Standardize on NumPy-style for all public functions. Internal helpers can have one-line docstrings.

---

### L3. `NumpyBackend` dataclass has no `frozen=True`

**File:** `src/spektrafilm/gpu/numpy_backend.py:11`
**Category:** API Consistency

`NumpyBackend` uses `@dataclass(slots=True)` while `CupyBackend` and `MlxBackend` are plain classes with class-level attributes. None are frozen, allowing mutation of shared backend state.

**Fix:** Not critical, but document that backends are mutable by design.

---

### L4. `_cctf_decoding_bt2020` uses hardcoded `alpha` and `beta` but `beta` is unused

**File:** `src/spektrafilm/gpu/kernels/color.py:172-173`
**Category:** Dead Code

```python
def _cctf_decoding_bt2020(rgb: Any, backend) -> Any:
    alpha = 1.099
    beta = 0.018  # <-- unused
```

**Fix:** Remove `beta` or use it (BT.2020 PQ/HLG transfer functions do use beta for the linear segment).

---

### L5. `load_image_oiio` missing return type annotation

**File:** `src/spektrafilm/utils/io.py:485`
**Category:** Type Hints

```python
def load_image_oiio(filename, *, dtype=np.float32):
```

Missing return type and `filename` parameter type.

**Fix:** `def load_image_oiio(filename: str | Path, *, dtype: np.dtype = np.float32) -> np.ndarray:`

---

### L6. `_runtime_image_dtype` is a trivial wrapper

**File:** `src/spektrafilm/utils/io.py:531-532`
**Category:** Code Quality

```python
def _runtime_image_dtype(dtype) -> np.dtype:
    return validate_float_dtype(dtype)
```

This one-line wrapper adds no value.

**Fix:** Inline at the single call site.

---

### L7. `_ICC_FILENAMES` has duplicate entries for ACES spaces

**File:** `src/spektrafilm/utils/io.py:182-186`
**Category:** Code Quality

Both `(True, False)` entries for ACES2065-1 and ACEScg map to the same linear ICC file. This is intentional (ACES is always linear) but confusing.

**Fix:** Add a comment explaining that both entries exist because the lookup key includes `cctf_encoding`, and ACES is always linear regardless.

---

### L8. Test file `test_edge_cases.py` has an unused `w` variable

**File:** `tests/test_edge_cases.py:223`
**Category:** Dead Code

The variable `w` is assigned but never used in the test, suggesting incomplete test logic.

**Fix:** Either use `w` in an assertion or remove it.

---

### L9. `_slug` function in `hdr_curve_profiles.py` allows consecutive underscores

**File:** `src/spektrafilm/utils/hdr_curve_profiles.py:287-288`
**Category:** Code Quality

```python
def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")
```

This can produce slugs like `"foo__bar"` from inputs like `"foo & bar"`.

**Fix:** Add `.strip("_")` then collapse with `re.sub(r"_+", "_", result)`.

---

### L10. `Simulator.process` return type annotation is wrong

**File:** `src/spektrafilm/runtime/process.py:29`
**Category:** Type Hints

```python
def process(self, image: np.ndarray) -> np.ndarray:
```

This is correct. But `process_with_metadata` at line 38 returns `SimulationPipelineResult`, which is properly annotated. No issue here — marking as verified.

---

## Automated Linter Summary

Running `ruff check src/ tests/ --exclude 'tests/gui/' --select E,F,W,I` produced:

| Code | Count | Description |
|------|-------|-------------|
| E501 | 1399 | Line too long (>88 chars) |
| I001 | 116 | Import not sorted |
| W293 | 116 | Whitespace before ':' |
| F401 | 31 | Unused import |
| W292 | 27 | No newline at end of file |
| E402 | 23 | Module-level import not at top |
| W191 | 18 | Indentation contains tabs |
| W291 | 16 | Trailing whitespace |
| F841 | 5 | Unused local variable |
| E701 | 5 | Multiple statements on one line |

**Total:** 1756 issues (mostly style, not correctness)

The E501 (line length) and I001 (import sorting) issues are the most numerous and lowest-risk. A single `ruff format` pass would fix most of them.

---

## Recommendations (Priority Order)

1. **Fix mutable default arguments** in `CalibrationTarget` (H1, H2) — these are real bugs that can cause subtle cross-instance state sharing.

2. **Unify exiv2 error handling** (H3) — inconsistent exception paths can cause different behavior on different platforms.

3. **Add `None` guards for module-level filter globals** (H5) — prevents `AttributeError` at runtime when data files are missing.

4. **Rename `numba_boost_hightlights.py`** (H6) — the typo propagates through the entire import chain.

5. **Run `ruff format` and `ruff check --fix`** for the 116 import sorting and 116 whitespace issues.

6. **Remove unused imports** (M1) — 31 instances, low risk cleanup.

7. **Move matplotlib imports to `__main__` guards** (M4) — reduces import time for production code.

8. **Add return type annotations** to the ~15 public functions missing them (L1, L5).

---

## Previous Rounds Reference

- Round 1-4 findings are documented in `code-quality-review-round-1.md` through `code-quality-review-round-4.md`
- The critical code review from 2026-05-26 is in `code-review-2026-05-26.md`
- This round focuses on cross-cutting code quality patterns not covered by the previous feature/behavior-focused reviews
