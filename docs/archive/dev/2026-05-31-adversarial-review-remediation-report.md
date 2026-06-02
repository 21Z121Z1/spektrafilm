# Adversarial Review Remediation Report

**Date:** 2026-05-31
**Scope:** `docs/dev/2026-05-30-adversarial-code-review.md`, current worktree state, and the later local v5 review notes.
**Plan:** `docs/superpowers/plans/2026-05-31-adversarial-review-remediation.md`

## External References Used

- Python `importlib.resources`: documents that package resources follow the same security model as `open()` and that resource path names are package-relative components. This supports validating profile stock names before joining them into resource paths.
- SciPy `Akima1DInterpolator`: documents that `extrapolate=None` resolves to no extrapolation, returning NaNs for out-of-bounds queries. This supports explicit NaN-to-zero sanitation for filter transmittance outside measured ranges.
- Git `gitcli`: recommends explicit `--` / `--end-of-options` separation for scripts handling random user input. This supports adding a separator before user-supplied revision strings.
- NumPy `nan_to_num`: defines the expected NaN and infinity replacement behavior used for backend parity and finite serialization.
- Pillow `Image`: documents lazy loading and file lifecycle behavior, supporting explicit image copies when loading from in-memory JPEG byte streams.

## Implemented Fixes

### Profile I/O and profile payload hardening

- `src/spektrafilm/profiles/io.py`
  - Added stock-name validation for `load_profile()` and `save_profile()` so package resources cannot be addressed with path traversal or option-like names.
  - Added a clear `ValueError` for `save_profile()` when `profile.info.stock` is unset.
  - Extended `_json_safe()` so scalar NaN and infinity values are serialized as JSON-safe `None`.
  - Made `profile_from_dict()` ignore unknown future keys for metadata, info, data, and density-curve models.
  - Added `ProfileData.__post_init__` shape and value validation. Density curves and log exposure must be finite; spectral tables allow NaN gaps but reject infinities and shape mismatches.
- Tests added in `tests/test_profiles.py`.

### Filter interpolation and numeric edge cases

- `src/spektrafilm/utils/io.py`
  - Sanitizes Akima interpolation output from `load_filter()` and `load_dichroic_filters()` with `np.nan_to_num(..., nan=0.0, posinf=0.0, neginf=0.0)`.
- `src/spektrafilm/model/emulsion.py`
  - Rejects all-NaN density-curve channels before `np.nanmin`/density conversion.
- `src/spektrafilm/utils/fast_gaussian_filter.py`
  - Returns an empty copy for empty image inputs before dispatching to kernels.
- Tests added in `tests/test_edge_cases.py` and `tests/test_emulsion.py`.

### Script argument safety

- `scripts/compare_simulation_revisions.py`
  - Inserts `--` before revision input in `git worktree add --detach` so revision strings beginning with dashes are treated as revisions, not options.
  - Verified locally with `git worktree add --detach /private/tmp/sf-separator-help-test -- --help`, which returned `fatal: invalid reference: --help` rather than printing command help.
- Test added in `tests/test_compare_simulation_revisions.py`.

### Gain-map JPEG loading and stricter tests

- `src/spektrafilm/utils/gain_map_io.py`
  - Copies Pillow images loaded from MPF byte streams before the byte stream can be closed.
  - Extracts the base JPEG image from MPF data before opening it, preventing the base image loader from seeing trailing MPF payload as part of the first image.
  - Adds a fallback MPF APP2 marker scan for MPF segments placed after the first scan payload.
- `tests/test_gain_map.py`
  - Uses a smooth deterministic gradient for JPEG roundtrip tolerance instead of high-frequency random noise.
  - Narrows nonexistent-file assertions to `FileNotFoundError` / `OSError`.

### Runtime LUT service correctness and waste reduction

- `src/spektrafilm/runtime/services/spectral_lut_compute.py`
  - Reuses the first `compute_with_lut()` result on CPU cache misses instead of applying the same LUT twice.
  - Validates `xmax > xmin` before cached GPU LUT normalization, preserving the same bounds contract as `compute_with_lut()`.
- Tests added in `tests/test_spectral_lut_service.py`.

### Test-strengthening retained or verified from the current worktree

- `tests/test_color_reference.py` now asserts exact sRGB CCTF reference values.
- `tests/test_edge_cases.py` now checks exact elapsed-time strings and current `measure_density_min` warning behavior.
- `tests/test_grain.py`, `src/spektrafilm/model/grain.py`, and `src/spektrafilm/runtime/params_schema.py` cover and reject invalid grain sublayer counts.
- GPU/runtime fixes already present in the current worktree were verified rather than replaced:
  - MLX `nan_to_num()` handles infinities consistently with NumPy default behavior.
  - Halide CCTF encode uses `hl.pow`.
  - scanning honors `output_clip_min` / `output_clip_max`.
  - color-reference temporal coupling has clear runtime errors.
  - GPU pipeline tests compare against CPU references.

## Disposition of Review Findings

### Fixed by this pass

- Original M4: `save_profile()` crash on missing stock.
- Original M5: `_json_safe()` infinity handling.
- Original L2: unknown profile keys.
- Additional current issue: profile resource path traversal in `load_profile()` / `save_profile()`.
- Additional current issue: Akima out-of-range NaNs in filter loaders.
- Additional current issue: all-NaN density-curve channel in emulsion development.
- Additional current issue: empty image handling in fast Gaussian filter.
- Additional current issue: untrusted revision argument separation in `compare_simulation_revisions.py`.
- Original L9/L10 and v5 L18: weak CCTF and broad gain-map missing-file tests.
- v5 M3/L8: duplicate LUT application and cached GPU degenerate-bound guard in `SpectralLUTService`.
- Additional current issue: MPF base-image loading could leave a lazy Pillow object tied to closed bytes and could misread trailing MPF payload.

### Already fixed in the current worktree and verified

- Original M1: MLX infinity handling in `nan_to_num()`.
- Original M2: Halide CCTF encode precision path.
- Original M7/L11: runtime and grain parameter validation.
- Original M8: layered grain input mutation.
- Original M9: scanning clip flags.
- Original M10: color-reference missing dependency errors.
- Original M11: GPU pipeline correctness tests.
- Original M12: grain blur coverage.
- Original L1/L3/L6/L7/L8: CCTF implementation simplification, logging, debug inject error, edge-case test assertions.

### Not treated as code defects

- Original M3 is a negative security finding: unsafe deserialization was not found.
- Original L4/L5 and v5 broad architecture/performance notes are maintainability follow-ups, not currently failing behavior. The safe one-pass changes above avoid reshaping stage ownership, module import policy, or the public LUT API while the current dirty worktree already has broad GPU/runtime changes in flight.
- v5 dead-code and zero-coverage notes were not all converted into code changes because they do not identify active user-facing behavior failures. They remain candidates for a separate coverage-hardening pass.

## Verification Evidence

- Targeted remediation suite:
  - `uv run pytest tests/test_profiles.py tests/test_edge_cases.py tests/test_emulsion.py tests/test_compare_simulation_revisions.py tests/test_color_reference.py tests/test_gain_map.py tests/test_spectral_lut_service.py tests/test_pipeline_lut_lifecycle.py tests/test_gpu_backend.py tests/test_gpu_pipeline.py tests/test_photo_params.py tests/test_grain.py -q`
  - Result: `193 passed, 2 skipped in 1.57s`
- Full test suite:
  - `uv run pytest -q`
  - Result: `833 passed, 7 skipped, 1 warning in 48.93s`
  - Remaining warning: existing `tests/test_autoexposure.py::test_legacy_autoexposure_methods_remain_finite_on_small_images[matrix]` divide-by-zero warning in `autoexposure.py:121`.
- Compile check:
  - `uv run python -m compileall src tests`
  - Result: pass.
- Whitespace/patch check:
  - `git diff --check`
  - Result: pass.

## Completion Audit

I re-read the original review, the v5 notes, and the implementation plan after the final verification pass. The real, localized behavior defects that could be fixed safely in this pass now have regression tests and green verification. The remaining review items are either already fixed in the current worktree, negative findings, broad maintainability work without a current failing behavior, or dead-code/coverage suggestions that should be handled in a dedicated follow-up rather than mixed into this remediation patch.
