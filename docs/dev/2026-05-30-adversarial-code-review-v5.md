# Adversarial Code Review v5 — 2026-05-30

## Summary

- **Candidates found:** 55 (non-low confidence from 74 raw)
- **Confirmed:** 23
- **Refuted:** 45 (via adversarial verification)
- **Dimensions:** correctness, security, performance, edge-cases, architecture, testing

---

## Confirmed Findings

### MEDIUM (5)

#### M1: `scanning.py` indentation defect — lines 165-166 outside `if` block
- **File:** `src/spektrafilm/runtime/stages/scanning.py:165-166`
- **Verifier:** Lines 165-166 are at the same indentation level as the `if` statement (8 spaces) while lines 161-164 defining `m`, `q`, and `correction_func` are inside the `if` block (12 spaces). Would raise `NameError` when neither `_black_correction` nor `_white_correction` is set, though all callers guard against this.

#### M2: PCHIP slopes recomputed on every `apply_lut_pchip_3d` call
- **File:** `src/spektrafilm/utils/fast_interp_lut.py`
- **Verifier:** Slopes are recomputed on every call despite the docstring stating they should be prepared once, but the absolute cost for a 32^3 Numba-JIT LUT is small enough that "high" overstates the impact.

#### M3: Double LUT application on cache miss in `_film_cmy_to_print_log_raw`
- **File:** `src/spektrafilm/runtime/services/spectral_lut_compute.py`
- **Verifier:** The double LUT application on cache miss is real but only the trilinear interpolation step is wasted (not the expensive PCHIP LUT creation), and it only affects the first invocation per LUT type.

#### M4: `SimulationPipeline.update()` re-enters `__init__` — fragile re-initialization
- **File:** `src/spektrafilm/runtime/pipeline.py:142-144`
- **Verifier:** CONFIRMED as architecture concern. Re-entering the constructor creates new stage objects and re-injects shared mutable state.

#### M5: Missing validation error-path tests for `RuntimePhotoParams`
- **File:** `tests/`
- **Verifier:** No test file contains `pytest.raises` or any assertion verifying that constructing `RuntimePhotoParams` with invalid `film_format_mm`, `upscale_factor`, or `lut_resolution` values raises `ValueError`.

### LOW (18)

#### L1: Descending x-axis in `np.interp` — no interpolation occurs
- **File:** `src/spektrafilm/utils/autoexposure.py`
- **Verifier:** For a descending x-axis, every element satisfies `x <= xp[0]`, so the outer `cp.where` always selects `fp[0]`. Path is unreachable since `log_exposure` is always ascending.

#### L2: Duplicate file with typo — `numba_boost_hightlights.py` vs `numba_boost_highlights.py`
- **File:** `src/spektrafilm/utils/numba_boost_hightlights.py`
- **Verifier:** Both files exist with real divergence (float64 forcing and dtype check in the typo version). Production code imports from the typo-named file; the correctly-named file is the orphan.

#### L3: Wasteful `np.repeat` allocations in grain loop
- **File:** `src/spektrafilm/model/grain.py:39,43`
- **Verifier:** The np.repeat allocations are real and wasteful but ephemeral (one at a time in the loop). Fixing requires modifying fast_interp's core interface.

#### L4: 4 `RegularGridInterpolator` instances created per `_fetch_coeffs` call
- **File:** `src/spektrafilm/runtime/services/spectral_lut_compute.py:76`
- **Verifier:** `_fetch_coeffs` is only invoked by `compute_lut_spectra` which is a one-time LUT generation step, making the performance impact negligible.

#### L5: Structurally defective `_correction_fucntion` — undefined variable references
- **File:** `src/spektrafilm/runtime/stages/scanning.py:165-166`
- **Verifier:** Lines 165-166 are outside the `if` block and reference undefined variables, but all three callers guard with early returns before calling the function, making it impossible to trigger.

#### L6: `lognorm_from_mean_std` references unimported `scipy`
- **File:** `src/spektrafilm/model/grain.py:247`
- **Verifier:** Would raise `NameError` if called, but it is dead code never invoked outside the module.

#### L7: `print()` instead of `logging.warning()` in `scanning.py`
- **File:** `src/spektrafilm/runtime/stages/scanning.py:133`
- **Verifier:** Line 133 uses `print(f"Warning: ...")` instead of `logging.warning()`, and no `logging` module is imported.

#### L8: GPU path duplicates normalization without guard
- **File:** `src/spektrafilm/runtime/services/spectral_lut_compute.py:141`
- **Verifier:** The GPU path duplicates the normalization without the guard from `lut.py:41`. Only triggers when a GPU backend is active and a subsequent call has `data_min==data_max` after a prior call populated the cache — extremely narrow edge case.

#### L9: `np.random` global state mutation — not thread-safe
- **File:** `src/spektrafilm/model/grain.py:22-57`
- **Verifier:** The function explicitly saves/restores `np.random` global state via `get_state/set_state`, which is inherently not thread-safe. Practical risk is minimal because the pipeline is not called from multiple threads.

#### L10: `init_params()` evaluated at import time — import-time I/O
- **File:** `src/spektrafilm/runtime/params_builder.py:10`
- **Verifier:** `init_params()` is evaluated once at function definition time during module import, triggering two `load_profile()` calls that read and parse JSON files from disk. The real issue is import-time I/O rather than mutable shared state.

#### L11: Missing tests for `smoothstep`, glare, and grain blur functions
- **File:** `tests/`
- **Verifier:** The functions are thin wrappers delegating to already-tested utilities, exercised through the pipeline smoke test. Minor gap rather than medium-severity risk.

#### L12: `runtime_float_dtype` dead code; `validate_float_dtype` untested
- **File:** `src/spektrafilm/utils/dtypes.py`
- **Verifier:** `runtime_float_dtype` has zero callers (dead code). `validate_float_dtype` is a trivial one-line guard called only from `load_image_oiio` with the safe default `dtype=np.float32`.

#### L13: `resize_for_preview` — zero non-mocked test coverage
- **File:** `src/spektrafilm/utils/preview.py`
- **Verifier:** All test references are monkeypatched replacements — no test calls the actual function.

#### L14: `build_hdr_debug_sidecar` — zero test coverage
- **File:** `src/spektrafilm/utils/hdr_photo.py`
- **Verifier:** Zero callers in production code, but it is a simple diagnostic JSON builder whose failure cannot affect image output.

#### L15: `standard_illuminant` — no dedicated tests
- **File:** `src/spektrafilm/model/illuminants.py`
- **Verifier:** Every test call site monkeypatches it away. No test directly invokes any branch.

#### L16: HEIF gain map load/patch/metadata paths untested
- **File:** `src/spektrafilm/utils/gain_map_io.py`
- **Verifier:** No test file references `_load_gain_map_heif`, `_patch_heif_for_iso21496`, or `_gainmap_metadata_to_iso_dict`. Existing HEIF tests only exercise the `ImportError` guard.

#### L17: `gamma_beta` branch — dead code
- **File:** `src/spektrafilm/model/grain.py`
- **Verifier:** No caller passes `method='gamma_beta'` (all use default `poisson_binomial`). `GrainParams` has no `method` field. Zero tests exercise the path.

#### L18: Test tolerance too wide for `_remove_sRGB_cctf`
- **File:** `tests/test_color_reference.py`
- **Verifier:** The range check `0.20 < result < 0.22` (allowing ~6.5% deviation) is wider than necessary. `pytest.approx(0.2140, abs=1e-4)` would be a more precise regression guard.

---

## Refuted Findings (45)

All 45 refuted findings were rejected by independent skeptical verification. Common refutation reasons:
- **Unreachable code paths** — all callers guard against the edge case
- **Dead code** — function is never called in production
- **Intentional design** — behavior is by design, not a bug
- **Negligible impact** — operation runs once or on tiny arrays
- **Standard patterns** — the "issue" is actually a common/acceptable pattern

---

## Gap Analysis

### Modules NOT Reviewed

The review examined ~12 source files out of 74 non-`__init__` Python files. Significant unreviewed modules:

| Module | Lines | Concern |
|--------|-------|---------|
| `model/diffusion.py` | 666 | Largest model file, no tests, no review |
| `utils/fast_interp_lut.py` | 827 | Numba-JIT LUT interpolation, no tests |
| `utils/hdr_photo.py` | 1391 | Largest utility file, calls `subprocess.run()` |
| `utils/gain_map_io.py` | 516 | Binary parsing code, no IO tests |
| `utils/fast_gaussian_filter.py` | 413 | Performance-critical numba utility, no tests |
| `utils/fast_stats.py` | 353 | Performance-critical numba utility, no tests |
| `runtime/stages/filming.py` | — | Only `scanning.py` was reviewed |
| `runtime/stages/printing.py` | — | Only `scanning.py` was reviewed |
| `runtime/api.py` | — | Not reviewed |
| `spektrafilm_gui/` | 24 files | Zero mentions in review |

### Patterns Missed by 6 Lenses

1. **`fastmath=True` in numba kernels** — `numba_boost_highlights.py` and `numba_boost_hightlights.py` use `@njit(fastmath=True)`, enabling unsafe floating-point optimizations (reassociation, FMA contraction) that may violate the "ZERO precision/quality loss" constraint.

2. **Resource management** — `utils/io.py` opens OIIO `ImageInput` handles with manual `.close()` calls (4 instances) rather than context managers. Handle leak on exception.

3. **Module-level mutable GPU kernel caches** — `gpu/kernels/density.py` and `gpu/kernels/filters.py` use module-level globals for kernel caching without thread safety.

4. **Entire GUI package unreviewed** — 24 files in `spektrafilm_gui/` with zero coverage.

---

## Verdict

The codebase is in **good shape** after the v4 fixes. The 5 medium findings are:
- 2 are structural/architecture concerns (M4 pipeline re-init, M2 slope recompute)
- 2 are performance micro-issues (M3 double LUT, M2 slope recompute)
- 1 is a missing test (M5 validation error paths)

No critical or high-severity issues were confirmed. The low findings are mostly dead code, missing tests for internal functions, and negligible edge cases.
