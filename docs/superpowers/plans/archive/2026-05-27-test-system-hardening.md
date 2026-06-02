# Test System Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the current non-GUI pytest system into a truthful, maintainable state by correcting stale assumptions in `docs/archive/docs-2-legacy-20260531/dev/test-improvement-plan.md`, fixing real behavior uncovered by the new tests, and documenting the final verification evidence.

**Architecture:** Keep the work test-first and local to `src/`, `tests/`, and `docs/`. Do not duplicate tests that already exist; strengthen weak assertions where they currently allow broken behavior, and fix only root causes proven by failing tests.

**Tech Stack:** Python 3.13, pytest, NumPy, SciPy reference filters, optional Halide/Numba tests, current Spektrafilm runtime test fixtures.

---

## Current Findings

The source plan is stale in several places:

- `tests/test_fft_gaussian_filter.py`, `tests/test_crop_resize.py`, and `tests/test_color_reference.py` already exist.
- `tests/test_parametric.py` has more than two tests, but it still does not cover the zero toe/shoulder limit called out by the plan.
- `tests/test_hdr_photo.py` already contains a broad parameterized `HDRPhotoMapping.__post_init__` validation test.
- `tests/test_photo_params.py` already exercises the missing neutral-filter database path, but it lets the expected `UserWarning` leak into the suite instead of asserting it.
- `.venv/bin/python -m pytest --ignore=tests/gui -q` currently passes with `548 passed, 6 skipped, 13 warnings`, so the actual work is not to create the old P1-P5 files from scratch.

Actual remaining test-system problems:

1. FFT Gaussian filtering validates sigma length only on the sequential 3D path. The default `parallel=True` path can fail with `IndexError` instead of the tested `ValueError`, and NumPy scalar sigma values are not treated like Python scalar sigma values.
2. Parametric density curves produce `NaN` and divide-by-zero warnings when `toe_size` or `shoulder_size` is exactly zero, even though the source plan explicitly calls for that edge case.
3. Crop tests are still too weak in boundary cases: they mostly assert non-empty shapes and do not prove exact clamping or exact pixel preservation at the corners.
4. Color reference tests cover identity and smoke-level correction, but do not yet prove black-only, white-only, and combined correction math against exact linear transforms.
5. The neutral print filter missing-database warning path is behaviorally covered but not asserted with `pytest.warns`, leaving an avoidable warning in the suite.
6. Untracked Halide/Numba files currently present in the workspace (`src/spektrafilm/halide/*`, `src/spektrafilm/gpu/halide_backend.py`, `tests/test_halide_*.py`, and the correctly spelled `numba_boost_highlights` path) must be treated as active local state and validated without being reverted.

External practice checks used:

- Pytest discovery starts from configured `testpaths` and collects `test_*.py` / `*_test.py`, so stale test modules must either import cleanly or be intentionally skipped: <https://docs.pytest.org/en/7.1.x/explanation/goodpractices.html>.
- Pytest warning assertions should use `pytest.warns()` / `recwarn` when a warning is expected behavior, rather than leaking warnings into the session summary: <https://docs.pytest.org/en/7.1.x/how-to/capture-warnings.html>.
- Pytest parametrization is the right local pattern for validation matrices and boundary cases already used in this repo: <https://docs.pytest.org/en/stable/how-to/parametrize.html>.
- SciPy documents `gaussian_filter` sigma as scalar-or-sequence and `reflect` as the default edge mode, which matches the existing reference-style FFT tests: <https://docs.scipy.org/doc/scipy/reference/generated/scipy.ndimage.gaussian_filter.html>.
- Halide CMake docs confirm `add_halide_library(... TARGETS ... AUTOSCHEDULER ...)` and target triples of the form `<arch>-<bits>-<os>`, matching the Android helper tests now present in the workspace: <https://halide-lang.org/docs/md_doc_2_halide_c_make_package.html>.

## File Structure

- Modify `src/spektrafilm/utils/fft_gaussian_filter.py`: normalize scalar/sequence sigma once before parallel dispatch and reject mismatched per-channel sigma arrays consistently.
- Modify `tests/test_fft_gaussian_filter.py`: add failing tests for default-parallel sigma mismatch and NumPy scalar sigma.
- Modify `src/spektrafilm/model/parametric.py`: implement the mathematical zero-size softplus limit for toe and shoulder terms.
- Modify `tests/test_parametric.py`: add failing tests for zero toe/shoulder and mixed zero/nonzero parameter arrays.
- Modify `tests/test_crop_resize.py`: make boundary assertions exact enough to catch clamping regressions.
- Modify `tests/test_color_reference.py`: add exact black-only, white-only, and combined correction tests using controlled `_y_black`/`_y_white` references.
- Modify `tests/test_photo_params.py`: assert the missing neutral-filter warning with `pytest.warns`.
- Add `docs/dev/test-system-hardening-2026-05-27.md`: completion record with what was fixed, what was already fixed, what remains intentionally out of scope, and verification output.

## Tasks

### Task 1: FFT Sigma Validation

- [ ] Add tests proving the default `parallel=True` path raises `ValueError` for a per-channel sigma length mismatch.
- [ ] Add a test proving a zero-dimensional NumPy scalar sigma behaves like a Python scalar on a 3D image.
- [ ] Run `tests/test_fft_gaussian_filter.py` and confirm the new tests fail for the right reason.
- [ ] Normalize `sigma` in `fft_gaussian_filter()` before branching into sequential/parallel work.
- [ ] Rerun `tests/test_fft_gaussian_filter.py`.

### Task 2: Parametric Zero Toe/Shoulder Limit

- [ ] Add tests for zero toe and zero shoulder producing finite clipped-linear limits.
- [ ] Run `tests/test_parametric.py` and confirm the new test fails with the current divide-by-zero/NaN behavior.
- [ ] Implement a stable `_toe_or_shoulder_term()` helper that returns `max(x, 0)` when the size parameter is zero.
- [ ] Rerun `tests/test_parametric.py`.

### Task 3: Strengthen Boundary And Branch Tests

- [ ] Replace weak crop shape-only assertions with exact shape and pixel equality checks for origin, far corner, oversized, and asymmetric crops.
- [ ] Add exact color-reference correction tests for black-only, white-only, and combined correction branches.
- [ ] Wrap the missing neutral-filter database test in `pytest.warns(UserWarning, match=...)`.
- [ ] Run `tests/test_crop_resize.py tests/test_color_reference.py tests/test_photo_params.py::TestDigestParamsFilmDefaults::test_missing_neutral_filter_database_entry_keeps_current_filters`.

### Task 4: Workspace-State Validation

- [ ] Run `tests/test_halide_android.py tests/test_halide_backend.py tests/test_numba_warmup.py` to confirm the current untracked Halide/Numba local state imports and behaves correctly.
- [ ] Run the full non-GUI baseline `.venv/bin/python -m pytest --ignore=tests/gui -q`.
- [ ] Run `.venv/bin/python -m compileall src/spektrafilm src/spektrafilm_gui tests -q`.
- [ ] Run `git diff --check`.

### Task 5: Documentation And Self-Audit

- [ ] Write `docs/dev/test-system-hardening-2026-05-27.md` with actual findings, changed files, and verification evidence.
- [ ] Re-read `docs/archive/docs-2-legacy-20260531/dev/test-improvement-plan.md` and this plan; confirm every real issue is either fixed, already fixed, or explicitly out of scope.
- [ ] Ask: "Do I have factual 100% confidence?" If not, loop back to add the missing test/fix/documentation before finalizing.
