# Test System Hardening Completion — 2026-05-27

## Scope

This pass started from `docs/archive/docs-2-legacy-20260531/dev/test-improvement-plan.md` and verified it against the current workspace instead of treating the document as current truth.

The original plan's P1/P2/P5 "new test file" items were already present in the tree:

- `tests/test_fft_gaussian_filter.py`
- `tests/test_crop_resize.py`
- `tests/test_color_reference.py`

`tests/test_parametric.py` and `tests/test_hdr_photo.py` had also already been expanded. The remaining useful work was therefore to fix real failures and weak tests, not to duplicate old planned files.

## External References Used

- Pytest collection and test layout: <https://docs.pytest.org/en/7.1.x/explanation/goodpractices.html>
- Pytest warning assertions: <https://docs.pytest.org/en/7.1.x/how-to/capture-warnings.html>
- Pytest parametrization: <https://docs.pytest.org/en/stable/how-to/parametrize.html>
- SciPy Gaussian filter scalar-or-sequence sigma reference: <https://docs.scipy.org/doc/scipy/reference/generated/scipy.ndimage.gaussian_filter.html>
- Halide CMake AOT `add_halide_library` target/autoscheduler contract: <https://halide-lang.org/docs/md_doc_2_halide_c_make_package.html>

## Fixed Real Issues

1. `fft_gaussian_filter()` now normalizes scalar and sequence sigma values before the 3D parallel/sequential split.
   - Before: default `parallel=True` could raise `IndexError` for a sigma length mismatch.
   - Before: a zero-dimensional NumPy scalar sigma was treated as a mismatched array.
   - Tests added in `tests/test_fft_gaussian_filter.py`.

2. `parametric_density_curves_model()` now handles zero toe/shoulder sizes with the finite clipped-linear mathematical limit.
   - Before: exact zero values produced divide-by-zero warnings and `NaN`.
   - Tests added in `tests/test_parametric.py`.

3. Crop boundary tests now assert exact crop shapes and pixel slices.
   - The earlier tests mostly checked "non-empty", which could miss off-by-one or wrong-corner clamps.
   - Tests strengthened in `tests/test_crop_resize.py`.

4. Color reference correction tests now assert exact black-only, white-only, and combined linear correction math.
   - The earlier coverage only proved identity and a smoke-level "changes output" case.
   - Tests added in `tests/test_color_reference.py`.

5. The neutral print-filter missing-database warning path is now asserted with `pytest.warns()`.
   - This removed an avoidable warning from the suite.
   - Updated `tests/test_photo_params.py`.

6. Remaining expected warnings were made explicit or removed.
   - Negative CCTF reference tests now use local `np.errstate(invalid="ignore")` around expected NaN comparisons.
   - `sample_runtime_curve_profile()` no longer writes the deprecated no-op `IOParams.full_image` field.
   - The ART compatibility test still exercises `full_image`, but now asserts the deprecation warning with `pytest.deprecated_call()`.

## Workspace-State Notes

The workspace also contains active local Halide/Numba changes that were not created by this pass but are part of the current test surface:

- `src/spektrafilm/gpu/halide_backend.py`
- `src/spektrafilm/halide/*`
- `src/spektrafilm/utils/numba_boost_highlights.py`
- `tests/test_halide_android.py`
- `tests/test_halide_backend.py`
- updates around the correctly spelled highlight boost import path

These were validated as current local state rather than reverted.

## Verification

Commands run from `/Users/retriedstormtrooper/Documents/spektrafilm-main`:

```bash
.venv/bin/python -m pytest tests/test_fft_gaussian_filter.py tests/test_parametric.py tests/test_crop_resize.py tests/test_color_reference.py tests/test_photo_params.py::TestDigestParamsFilmDefaults::test_missing_neutral_filter_database_entry_keeps_current_filters -q
```

Result: `44 passed`

```bash
.venv/bin/python -m pytest tests/test_halide_android.py tests/test_halide_backend.py tests/test_numba_warmup.py -q
```

Result: `23 passed`

```bash
.venv/bin/python -m pytest tests/test_gpu_color_chain.py::test_backend_cctf_encoding_matches_colour_reference tests/test_gpu_color_chain.py::test_backend_cctf_decoding_matches_colour_reference tests/test_hdr_curve_profiles.py::test_repo_smoke_samples_known_runtime_profile tests/test_runtime_api.py::TestRuntimeApi::test_art_extlut_compatibility_path_runs -q -W error
```

Result: `18 passed`

```bash
.venv/bin/python -m pytest --ignore=tests/gui -q -W error
```

Result: `556 passed, 6 skipped`

```bash
.venv/bin/python -m compileall src/spektrafilm src/spektrafilm_gui tests -q
```

Result: exit code `0`

```bash
git diff --check
```

Result: exit code `0`

## Self-Audit

Question: Do I have factual 100% confidence that the test system improvements requested by `docs/archive/docs-2-legacy-20260531/dev/test-improvement-plan.md` are handled?

Answer: Yes for the non-GUI test system in this workspace. The old plan's high-priority missing files already existed, the remaining real defects now have red-green proof, the non-GUI suite passes with warnings elevated to errors, and the local Halide/Numba test surface imports cleanly.

Explicit boundary: GUI tests remain outside the final gate because `CLAUDE.md` defines `.venv/bin/python -m pytest --ignore=tests/gui -q` as the required environment command and explicitly skips GUI-only harness issues in this checkout.
