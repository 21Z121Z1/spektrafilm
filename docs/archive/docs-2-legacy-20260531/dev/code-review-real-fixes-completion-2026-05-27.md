# Code Review Real Fixes Completion Report

Date: 2026-05-27

## Summary

This pass read the requested review and research implementation documents, checked the reported findings against the current workspace, and fixed the still-real, in-scope issues that could be changed safely with focused tests.

The current branch already had many review items resolved before this pass: HDR rendition EXR routing, ACEScg ICC mapping, profile path-to-white toggle, SDR-base test expectations, HDRPhotoMapping validation, and the stale README package reference. Those were verified by source inspection and existing tests rather than reimplemented.

## Fixed In This Pass

- Added warning logs for GUI metadata read/write failures so headless or batch contexts retain diagnostic evidence.
- Cached `characterize_pipeline_profile()` results per `SimulationPipeline` instance and invalidated the cache on runtime updates that affect the curves.
- Changed scene-luminance grafting to use Rec.709/perceptual luminance instead of max-channel intensity for the paper-limited look.
- Hardened `load_image_oiio(Path(...))` open/read failures so Path inputs raise `OSError` cleanly instead of string-concat `TypeError`.
- Added HEIC/HDR photo output path preflight for control characters, missing parents, non-directory parents, and unwritable parents before invoking Swift/CoreImage.
- Contained grain RNG side effects: seeded `Generator` paths no longer mutate global `np.random`; fast-stats legacy RNG calls save/restore the previous global state.
- Replaced mutable grain default lists with tuple defaults.
- Fixed the latent `fixed_seed` branch in grain generation so it is usable instead of setting `seed=None` and then indexing it.
- Added correctly spelled `spektrafilm.utils.numba_boost_highlights`; kept the misspelled `numba_boost_hightlights` path as a compatibility wrapper; updated production imports to the correct spelling.

## Still Skipped Or Deferred

- GUI HEIC QApplication abort harness (`M3`): explicitly skipped by `CLAUDE.md`.
- Full-size HDR sidecar memory architecture (`H3`): explicitly skipped by `CLAUDE.md` as a larger refactor.
- Metal/macOS-only paths: explicitly skipped by `CLAUDE.md`.
- Broad style-only churn such as repository-wide line-length/import sorting, moving all `__main__` blocks, or wholesale type-annotation passes: real cleanup, but out of scope for this targeted correctness pass.
- Package resource write redesign for profiles/filter presets: real design concern, but it needs a user-writable storage contract decision rather than a narrow patch.
- `ruff` lint reproduction: not run because `ruff` is not installed in `.venv`.

## Verification

- Baseline before edits: `.venv/bin/python -m pytest --ignore=tests/gui -q` -> `508 passed, 6 skipped, 11 warnings`.
- Red tests added and observed failing before fixes:
  - Missing `numba_boost_highlights` import failed collection.
  - `apply_grain_to_density(..., fixed_seed=42)` failed with `TypeError: 'NoneType' object is not subscriptable`.
- Targeted post-fix suite: `.venv/bin/python -m pytest tests/test_hdr_photo.py tests/test_image_io_color_metadata.py tests/test_runtime_api.py tests/test_grain.py tests/test_numba_warmup.py tests/gui/test_controller_output.py -q` -> `231 passed, 3 warnings`.
- Halide targeted suite after current workspace sync: `.venv/bin/python -m pytest tests/test_halide_backend.py -q` -> `5 passed`.
- Full non-GUI suite: `.venv/bin/python -m pytest --ignore=tests/gui -q` -> `548 passed, 6 skipped, 13 warnings`.
- Compile check: `.venv/bin/python -m compileall src tests` -> exit 0.
- Whitespace check: `git diff --check` -> exit 0.

## Self-Audit

Question: Do I have factual confidence that every still-real, in-scope issue identified for this pass is either fixed, already resolved, explicitly skipped by local instruction, or documented as deferred?

Answer: Yes, based on the current source inspection and the verification commands above. The remaining unresolved items are not hidden implementation gaps in this pass; they are either explicitly excluded (`M3`, `H3`, Metal/macOS), broad style/refactor campaigns, or storage-contract decisions that should not be changed without a product-level target.
