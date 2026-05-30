# Code Review Real Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix every still-real, in-scope code review issue that is not already resolved by the current tree and is not explicitly excluded by `CLAUDE.md`.

**Architecture:** Keep changes narrow and test-first. Preserve the HDR export contracts already added in earlier rounds, add missing observability/caching/boundary checks, and avoid broad style-only churn or large memory architecture refactors.

**Tech Stack:** Python 3.13, NumPy, OpenImageIO, pytest, Qt controller tests where already available, Spektrafilm runtime/HDR utilities.

---

## Source Review Scope

Read and cross-checked:

- `docs 2/dev/code-review-2026-05-26.md`
- `docs 2/dev/code-quality-review-round-1.md`
- `docs 2/dev/code-quality-review-round-2.md`
- `docs 2/dev/code-quality-review-round-3.md`
- `docs 2/dev/code-quality-review-round-4.md`
- `docs 2/dev/code-quality-review-round-5.md`
- `docs 2/dev/code-quality-review-round-6.md`
- `docs 2/dev/research-implementation-round-1.md`
- `docs 2/dev/research-implementation-round-2.md`
- `docs 2/dev/research-implementation-round-3.md`
- `docs 2/dev/research-implementation-round-4.md`
- `docs 2/dev/research-implementation-round-5.md`
- `CLAUDE.md`

External best-practice checks used:

- Python default argument values: mutable defaults are evaluated once; use a `None` sentinel when the default must not be shared. Source: `https://docs.python.org/3/tutorial/controlflow.html#default-argument-values`.
- Python logging for libraries: library code should use loggers and let the application configure handlers. Source: `https://docs.python.org/3/howto/logging.html#configuring-logging-for-a-library`.
- Python subprocess: prefer `subprocess.run()` with an argument sequence and `shell=False`; use fully qualified executables where possible. Source: `https://docs.python.org/3/library/subprocess.html`.
- NumPy random: new code should transition to `Generator/default_rng`; global `np.random` convenience functions share a single legacy global state. Source: `https://numpy.org/doc/stable/reference/random/index.html`.

## Current Baseline

- Command: `.venv/bin/python -m pytest --ignore=tests/gui -q`
- Result before edits: `508 passed, 6 skipped, 11 warnings`

## Findings Classification

### Already Resolved In Current Tree

- `C1` HDR Rendition EXR routing: `save_image_oiio()` accepts `exr_mode`, sidecars, and HDR mapping kwargs; `save_hdr_rendition_exr()` exists; controller passes `exr_mode`.
- `H1` ACEScg ICC mapping: `_ICC_FILENAMES` and `_ICC_PROFILES` include ACEScg.
- `H2` GUI path-to-white toggle: controller maps disabled path-to-white to `profile_hdr_path_to_white_strength=0.0`.
- `M1` SDR-base test expectation: HDR photo tests now assert `preserve_sdr_base=True` behavior and preserve old tone-map coverage under `preserve_sdr_base=False`.
- `M2` HDRPhotoMapping validation: current `__post_init__` validates the modern profile-HDR fields called out in the review.
- `L1` README stale `spektrafilm_profile_creator` reference: current `README.md` no longer contains it.
- Several code-quality findings already fixed: calibration target mutable defaults, `SimulationPipeline.update()` no longer calls `__init__` directly, broad profile characterization print was replaced by logging, soft-update/GPU tiling tests exist, and module-level matplotlib imports were moved out of hot import paths.

### Explicitly Out Of Scope This Round

- `M3` GUI HEIC QApplication abort harness issue: explicitly skipped by `CLAUDE.md`.
- `H3` full-size HDR sidecar memory architecture: explicitly skipped by `CLAUDE.md` as a larger refactor.
- Metal/macOS-only behavior: explicitly skipped by `CLAUDE.md`.
- Broad line-length/import-sort/style passes and full `__main__` extraction: real cleanup, but high churn and not correctness-critical for this goal.
- Package-resource write redesign for `save_profile()` / `save_neutral_print_filters()`: real design concern, but changing the storage contract requires product/user-directory decisions beyond this targeted pass.

### Still Real And In Scope

1. GUI metadata copy/read failures are appended to status text but are not logged, so headless/batch contexts lose diagnostic evidence.
2. `characterize_pipeline_profile()` still builds a temporary pipeline on every metadata run; current tests verify validity but not caching.
3. `_graft_scene_luminance()` still uses max-channel intensity for `look_y` while the rest of HDR mapping uses perceptual luminance.
4. `load_image_oiio()` accepts `Path` but concatenates the filename into error strings as if it were `str`.
5. `save_hdr_photo_heic()` uses safe `subprocess.run([...], shell=False)` but lacks preflight path validation for null/control characters and unwritable parent directories.
6. `grain.layer_particle_model()` seeds NumPy's global legacy RNG even when the `Generator` path is used; the fast-stats path also needs save/restore around its legacy RNG dependency.
7. Grain APIs still expose mutable list defaults for scale/min/max/uniformity parameters.
8. The highlight boost module typo still propagates through production imports as `numba_boost_hightlights.py`.

## File Structure

- Modify `src/spektrafilm_gui/controller.py`: add module logger and warning logs for metadata read/write failures.
- Modify `src/spektrafilm/runtime/pipeline.py`: cache profile characterization curves on the pipeline instance and invalidate on reinitialization/soft update.
- Modify `src/spektrafilm/utils/hdr_photo.py`: use perceptual `luminance_y()` in `_graft_scene_luminance()` and validate HEIC output paths before subprocess execution.
- Modify `src/spektrafilm/utils/io.py`: make `Path` error formatting safe.
- Modify `src/spektrafilm/model/grain.py`: remove mutable defaults and contain global RNG side effects around fast-stats calls.
- Add `src/spektrafilm/utils/numba_boost_highlights.py`: correctly spelled highlight boost implementation.
- Modify `src/spektrafilm/utils/numba_boost_hightlights.py`: compatibility wrapper for the old misspelled import path.
- Modify imports in `src/spektrafilm/runtime/stages/filming.py`, `src/spektrafilm/utils/numba_warmup.py`, and comments/tests as needed to use the correctly spelled module.
- Add/update tests in `tests/test_image_io_color_metadata.py`, `tests/test_hdr_photo.py`, `tests/test_runtime_api.py`, `tests/test_grain.py` or a nearby model test file, `tests/test_numba_warmup.py`, and `tests/gui/test_controller_output.py` if import-safe.
- Add final documentation in `docs 2/dev/code-review-real-fixes-completion-2026-05-27.md`.

## Tasks

### Task 1: Logging Evidence For GUI Metadata Failures

- [ ] Add a failing controller-level test that monkeypatches metadata read/write to raise and asserts `spektrafilm_gui.controller` logs a warning containing the path and failure.
- [ ] Add `import logging` and `_log = logging.getLogger(__name__)` to `src/spektrafilm_gui/controller.py`.
- [ ] In both metadata exception handlers, call `_log.warning(..., exc_info=True)` before appending to `metadata_errors`.
- [ ] Run the targeted controller output test if it is safe locally; otherwise run the import-free non-GUI slice and document any GUI skip.

### Task 2: Cache Profile Characterization Per Runtime Instance

- [ ] Add a failing test proving two consecutive `characterize_pipeline_profile(pipeline)` calls reuse cached curves for the same pipeline instance.
- [ ] Store a private cache such as `_profile_characterization_curves: tuple[np.ndarray, np.ndarray] | None` during `_reinitialize()`.
- [ ] Make `characterize_pipeline_profile()` return cached arrays when present and write the computed arrays into the cache after the first computation.
- [ ] Invalidate the cache in `soft_update()` when any field that affects filming/printing/profile curves changes.
- [ ] Run targeted runtime tests.

### Task 3: Use Perceptual Luminance In Scene Graft

- [ ] Add a failing HDR unit test with saturated/non-neutral `look_rgb` where max-channel and Rec.709 luminance produce different graft behavior.
- [ ] Change `_graft_scene_luminance()` to compute `look_y = luminance_y(look)` instead of `np.max(look, axis=2)`.
- [ ] Run targeted HDR photo tests.

### Task 4: Harden I/O Boundary Validation

- [ ] Add a failing `load_image_oiio(Path(...))` test that monkeypatches `oiio.ImageInput.open` to return `None` and expects `OSError`, not `TypeError`.
- [ ] Replace filename string concatenation in `load_image_oiio()` error paths with f-strings or `str(filename)`.
- [ ] Add failing tests for `save_hdr_photo_heic()` rejecting paths with null/control characters and unwritable or missing parents before invoking Swift.
- [ ] Implement a small path preflight helper in `hdr_photo.py`; keep `subprocess.run()` as an argument list with `shell=False`.
- [ ] Run targeted I/O/HDR tests.

### Task 5: Contain Grain RNG Side Effects And Mutable Defaults

- [ ] Add failing tests showing `layer_particle_model(seed=..., use_fast_stats=False)` does not mutate `np.random` global state, and `use_fast_stats=True` restores the previous state after its legacy RNG calls.
- [ ] Replace mutable list defaults in grain functions with tuple defaults.
- [ ] Only touch the global legacy RNG inside the fast-stats branch, and save/restore its previous state with `np.random.get_state()` / `np.random.set_state()`.
- [ ] Run targeted grain/model tests.

### Task 6: Add Correctly Spelled Highlight Boost Module

- [ ] Add failing import tests for `spektrafilm.utils.numba_boost_highlights` and compatibility tests for the old misspelled path.
- [ ] Add `src/spektrafilm/utils/numba_boost_highlights.py` with the implementation currently in the misspelled module.
- [ ] Convert `src/spektrafilm/utils/numba_boost_hightlights.py` to a compatibility wrapper whose `warmup_boost_highlights()` still respects monkeypatching of the wrapper's `boost_highlights`.
- [ ] Update production imports to use `numba_boost_highlights`.
- [ ] Run Numba warmup/highlight tests.

### Task 7: Verification And Documentation

- [ ] Run targeted test slices after each task.
- [ ] Run `.venv/bin/python -m pytest --ignore=tests/gui -q`.
- [ ] Run `.venv/bin/python -m compileall src tests`.
- [ ] Run `git diff --check`.
- [ ] Write `docs 2/dev/code-review-real-fixes-completion-2026-05-27.md` with actual fixed/resolved/skipped findings and verification results.
- [ ] Final self-audit: ask whether any still-real in-scope review item lacks a test or code/doc decision. If yes, loop back; if no, mark the goal complete.
