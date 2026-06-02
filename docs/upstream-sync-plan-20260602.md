# Upstream Sync Plan And Report - 2026-06-02

## Plan Section

### New /goal

Safely finalize `develop` against `upstream/main` by proving the latest upstream history is already incorporated, preserving all local Spektrafilm work and the current documentation cleanup, committing any remaining local work without rewriting history, validating with the repository's `.venv`/pytest workflow, and pushing only to `origin/develop` when the working tree and push target are verified.

### Current Branch And Remote State

- Current branch: `develop`
- `HEAD`: `949cf43ad0e8af8cf14dfc51eba02489441cacc1`
- `origin/develop`: `949cf43ad0e8af8cf14dfc51eba02489441cacc1`
- `upstream/main`: `906351eca5f677e4c7d991b929e2dcbdac53827a`
- `origin` fetch URL: `https://github.com/21Z121Z1/spektrafilm.git`
- `origin` push URL: `https://github.com/21Z121Z1/spektrafilm.git`
- `upstream` fetch URL: `https://github.com/andreavolpato/spektrafilm.git`
- `upstream` push URL exists in local config but must never be used.
- After `git fetch origin` and `git fetch upstream`, `git rev-list --left-right --count HEAD...upstream/main` returns `380 0`.
- `upstream/main` is already an ancestor of `HEAD`.
- `origin/develop` is already equal to `HEAD`; the remaining local work is uncommitted.

### Existing Working Tree Changes To Preserve

The working tree is dirty before this plan is written. The changes are not upstream conflict residue; they are current local work:

- A documentation archive sweep moving historical Markdown files into `docs/archive/`, `docs/archive/dev/`, and `docs/superpowers/plans/archive/`.
- Router updates in `docs/README.md`, `docs/dev/README.md`, `docs/archive/README.md`, and `docs/superpowers/plans/README.md`.
- English companion docs such as `docs/color-management-hdr-review-2026-05-31.en.md`, `docs/dev/gain-map-HDR-analysis-report.en.md`, `docs/dev/project-status-report-20260527.en.md`, `docs/halide-mlx-parity-results-20260531.en.md`, `docs/hdr_exr_output_plan.en.md`, and `docs/hdr_profile_aware_raw_validation.en.md`.
- `uv.lock` regeneration matching the current `pyproject.toml` dependency graph and project version `0.3.3`.

These changes must be committed, not discarded, because the user explicitly requires preserving all completed local work.

### Upstream Recent 31-Commit Analysis

The 31 newest commits on `upstream/main` are already included in `develop`. Their combined range, `upstream/main~31..upstream/main`, changes 704 files with about 240k insertions and 88k deletions. The main themes are:

- Project layout migration from legacy `agx_emulsion/` and `setup.py` into `src/spektrafilm`, `src/spektrafilm_gui`, and `src/spektrafilm_lut_creator`.
- New packaged profile JSON data, ICC assets, license packaging, citation/support files, README banner and support copy.
- LUT creator expansion: topologies, color spaces, OCIO config emission, QA reports, formats, metadata, CLI, and tests.
- Runtime and GUI refactors: topology, gamut compression, parameter manifest, GUI state/persistence/widgets, and GUI tests.
- Tests and baselines for runtime, LUT creator, GUI, raw processing, profile loading, gamut compression, and regression fixtures.
- Recent GUI refactor commit `906351e` merged `gui-refactor` and introduced `param_manifest.py`, refactored widget sections, state, persistence, and GUI tests.

### Local Ahead Work To Protect

`develop` has 380 commits not in `upstream/main`. These commits contain the fork-specific work that must not be overwritten:

- HDR, HEIC, Apple Adaptive HDR, ISO 21496-1 gain-map, JPEG/HEIF gain-map helpers, and macOS HEIC encoder support.
- Profile-aware HDR, film-scan-aware HDR, HDR curve-profile data, path-to-white controls, and export-only HDR rendition paths.
- RAW, EXR, HEIC, ICC, EXIF, and color-metadata export handling.
- Color-management workflow additions, ACES/scene-linear contracts, gamut compression hardening, and SDR parity checks.
- GPU, MLX, CuPy, and Halide backends, generators, kernels, Android Halide AOT/JNI foundation, and backend parity tests.
- Film simulation pipeline work around grain, diffusion, couplers, scanning, printing, runtime params, and GUI/macOS bridge integration.
- Regression tests and documentation that describe the above behavior.

Hard constraint: SDR preview, SDR output, and the film/print/scan runtime look must not change as a side effect of this synchronization. HDR must remain export-only or isolated in explicit HDR rendition paths.

### Strategy Comparison

| Strategy | Result | Risk |
| --- | --- | --- |
| Merge `upstream/main` into `develop` | Normally preferred when behind. Preserves local commits and creates an auditable merge commit. | Not needed right now because behind is `0`; running another merge would be a no-op or empty history churn. |
| Rebase `develop` onto `upstream/main` | Linearizes history. | Forbidden by user, high risk with 380 local commits, and unnecessary because upstream is already incorporated. |
| Reset to `upstream/main` | Matches upstream exactly. | Forbidden and destructive; would discard local fork work. |
| Cherry-pick missing upstream commits | Useful when only selected upstream changes are wanted. | Not needed because there are no missing upstream commits. |
| Commit current dirty local work and push to `origin/develop` | Preserves the remaining working-tree cleanup and makes origin match local state. | Safe if validation passes and push target is checked. |

Final choice: do not run another merge. Create the required backup branch, preserve the dirty working-tree changes as normal commits, validate, and push only to origin.

### Backup Plan Before Large Git Operations

Before staging or committing the large documentation/archive sweep, create:

```bash
git branch backup/before-upstream-sync-20260602-2303
```

The backup branch protects the current committed tip before this finalization pass. The dirty tree will then be preserved by ordinary commits on `develop`.

### Conflict Handling Strategy

No new merge is planned, so this run should produce no new conflict files. If fresh remote analysis later shows nonzero behind count before push, stop and switch back to a real merge flow:

- Create a new backup branch before the merge.
- Run `git merge --no-ff upstream/main`.
- Audit each conflict file by comparing upstream intent and local fork intent.
- Never use repository-wide `ours` or `theirs`.
- Preserve local HDR/HEIC/export-only/GPU/color/runtime behavior unless file-level evidence proves an upstream change is a safe additive fix.
- Re-run focused tests before committing the merge.

Historical note: the current history already contains merge commit `0d3aeda` (`Merge upstream/main into develop`), which handled the upstream GUI refactor. Its known conflict surface included GUI files, runtime params, grain/backend paths, and tests. This run must not overwrite that resolved state.

### Test Plan

Required checks:

```bash
git status --short --branch
git diff --check
```

Repository entrypoint from `CLAUDE.md` and `CONTRIBUTING.md`:

```bash
.venv/bin/python -m pytest --ignore=tests/gui -q
```

Focused verification before or alongside the full non-GUI suite:

```bash
.venv/bin/python -m pytest --ignore=tests/gui -q \
  tests/test_upstream_parity.py \
  tests/test_hdr_photo.py \
  tests/test_gain_map.py \
  tests/test_image_io_color_metadata.py \
  tests/test_color_management.py \
  tests/test_gpu_backend.py \
  tests/test_gpu_color_chain.py \
  tests/test_gpu_lut.py \
  tests/test_pipeline_smoke.py \
  tests/test_runtime_api.py
```

If the full suite fails, classify each failure as environment, known pre-existing issue, upstream issue, or regression from this finalization work. Do not report a failing command as passing.

### Push Strategy

Push only after all of the following are true:

- `origin` still points to `https://github.com/21Z121Z1/spektrafilm.git`.
- Current branch is `develop`.
- `upstream/main` remains an ancestor of `HEAD`.
- `git rev-list --left-right --count HEAD...upstream/main` still reports `ahead > 0` and `behind = 0`.
- Validation results are recorded in this document.
- No unresolved conflict markers or whitespace errors remain.

Allowed push:

```bash
git push origin develop
```

Forbidden push forms:

```bash
git push upstream ...
git push --force upstream ...
git push --mirror ...
```

No force push to origin is planned.

### Rollback Plan

- To recover the pre-finalization committed tip locally: `git switch develop` then inspect `backup/before-upstream-sync-20260602-2303`.
- If a newly created local commit is wrong before push, prefer a normal revert commit over history rewrite.
- If a pushed commit must be backed out, use `git revert` and push a new revert commit to `origin/develop`.
- Do not reset or force push unless the user explicitly approves after seeing the evidence.

### Stop Conditions

Stop and report before pushing if any of these occur:

- `origin` is not `21Z121Z1/spektrafilm`.
- The intended push target is not `origin develop`.
- `upstream/main` is no longer an ancestor of `HEAD` after a fresh fetch.
- A merge becomes necessary and conflicts affect SDR/HDR/GPU/runtime code in a way that cannot be resolved with file-level evidence.
- Validation shows a plausible regression in SDR output, HDR/export behavior, color management, GPU/MLX/Halide, or the film/print/scan runtime.
- Authentication or push permissions fail.

### Completion Standard

This goal is complete only when:

- Backup branch exists.
- Current branch contains all local changes as commits.
- `upstream/main` is incorporated without rebase/reset/force push.
- Working tree is clean except ignored files.
- Required validation has been run and recorded.
- Sync report section below is updated.
- Push to `origin/develop` succeeds.
- No push to `upstream` has been made.

## Execution Report

### Actions Performed

- Confirmed current branch with `git rev-parse --abbrev-ref HEAD`: `develop`.
- Confirmed remotes with `git remote -v`:
  - `origin`: `https://github.com/21Z121Z1/spektrafilm.git`
  - `upstream`: `https://github.com/andreavolpato/spektrafilm.git`
- Ran `git fetch origin` and `git fetch upstream`.
- Confirmed `HEAD`, `origin/develop`, and `upstream/main`:
  - `HEAD`: `949cf43ad0e8af8cf14dfc51eba02489441cacc1`
  - `origin/develop`: `949cf43ad0e8af8cf14dfc51eba02489441cacc1`
  - `upstream/main`: `906351eca5f677e4c7d991b929e2dcbdac53827a`
- Confirmed `git rev-list --left-right --count HEAD...upstream/main`: `380 0`.
- Confirmed `upstream/main` is already an ancestor of `HEAD`.
- Created backup branch: `backup/before-upstream-sync-20260602-2303`.
- Did not run a new merge, rebase, reset, force push, repository-wide checkout, or upstream push.

### Final Sync Strategy

No new merge was necessary in this pass. The requested upstream history was already incorporated by the existing `develop` history, including prior merge commit `0d3aeda` (`Merge upstream/main into develop`). This pass therefore finalized the fork state by:

- preserving the existing 380 local commits ahead of upstream;
- preserving the current local documentation cleanup and HDR/GPU/GUI runtime work;
- fixing only a stale GUI test fixture that omitted the new `compute` widget section;
- documenting the actual live state instead of repeating the older 31-commit-behind plan;
- preparing the branch for a normal `git push origin develop`.

### Conflict Files

There were no new conflict files in this run because no new merge was required. Historical conflict information from the earlier upstream GUI-refactor merge remains documented above for auditability, but it was not re-opened or overwritten in this pass.

### Protected Local Functionality

The following local fork work remained present and was included in validation:

- HDR/HEIC/Apple Adaptive HDR/gain-map export code and tests.
- Profile-aware and film-scan-aware HDR curve/profile logic.
- Export-only HDR rendition paths; no SDR preview/output path was changed by this finalization pass.
- RAW/EXR/HEIC export and image color metadata handling.
- MLX/GPU runtime backend summary, serialized Metal runtime handling, and MLX hot-path benchmark/type tracing.
- GUI HDR export settings, persistence, state bridge, layout, controller save path, and widget manifest wiring.

### Validation Results

Status and whitespace checks:

```bash
git status --short --branch
git diff --check
git diff --cached --check
```

Results:

- `git status --short --branch` showed the expected local dirty tree before final commits.
- `git diff --check` passed.
- `git diff --cached --check` initially found trailing blank lines in `docs/dev/2026-06-02-mlx-runtime-hotpath-plan.md` and `docs/docs_inventory.txt`; those were removed and the command then passed.

Focused tests that pass:

```bash
.venv/bin/python -m pytest \
  tests/gui/test_state_bridge.py::test_apply_gui_state_updates_all_sections_and_scan_film \
  tests/gui/test_state_bridge.py::test_collect_gui_state_reads_all_sections_and_bottom_bar_scan_flag \
  tests/gui/test_controller_flow.py::test_process_image_with_runtime_captures_backend_runtime_summary \
  tests/gui/test_controller_runtime_module.py::test_execute_simulation_request_appends_runtime_backend_status \
  -q
```

Result: `4 passed`.

```bash
.venv/bin/python -m pytest \
  tests/test_hdr_curve_profiles.py \
  tests/test_hdr_photo.py \
  tests/test_gpu_pipeline.py \
  tests/test_runtime_api.py \
  -q
```

Result: `189 passed, 2 skipped`.

```bash
.venv/bin/python -m pytest \
  tests/gui/test_controller_flow.py \
  tests/gui/test_controller_output.py \
  tests/gui/test_controller_runtime_module.py \
  tests/gui/test_layout.py \
  tests/gui/test_persistence.py \
  tests/gui/test_state_bridge.py \
  tests/gui/test_widgets.py \
  -q
```

Result: `102 passed`.

```bash
.venv/bin/python -m pytest \
  tests/test_image_io_color_metadata.py \
  tests/test_hdr_curve_profiles.py \
  tests/test_hdr_photo.py \
  tests/test_gpu_pipeline.py \
  tests/test_runtime_api.py \
  tests/test_mlx_runtime_hotpath_benchmark.py \
  -q
```

Result: `219 passed, 2 skipped`.

Repository documented non-GUI entrypoint:

```bash
.venv/bin/python -m pytest --ignore=tests/gui -q
```

Result: `1298 passed, 7 skipped, 6 failed, 1 warning`.

The six failures are SDR regression-baseline/golden-reference mismatches:

- `tests/test_pipeline_smoke.py::test_midgray_input_produces_expected_output_values`
- `tests/test_regression_baselines.py::TestRegressionBaselines::test_pipeline_snapshot[print_rgb_portra_endura_gray_ramp16]`
- `tests/test_regression_baselines.py::TestRegressionBaselines::test_pipeline_snapshot[negative_density_portra_endura_gray_ramp16]`
- `tests/test_regression_baselines.py::TestRegressionBaselines::test_pipeline_snapshot[print_rgb_fuji_crystal_gray_ramp16]`
- `tests/test_regression_baselines.py::TestRegressionBaselines::test_pipeline_snapshot[print_rgb_portra_endura_green_patch8]`
- `tests/test_upstream_parity.py::TestGoldenReference::test_midgray_output_golden_reference`

To classify these failures, a temporary clean worktree was created at `/tmp/spektrafilm-head-VUcgYc` from `HEAD`. The same six SDR baseline/golden tests were run there with `PYTHONPATH=/tmp/spektrafilm-head-VUcgYc/src`, and they failed with the same numeric outputs. This proves the six SDR baseline failures are already present in the current committed `HEAD`/`origin/develop`, not introduced by this finalization pass. They were not hidden or treated as passed.

### Self-Audit Findings

- Merge omission risk: checked by `git rev-list --left-right --count HEAD...upstream/main` returning `380 0` and by verifying `upstream/main` is an ancestor of `HEAD`.
- Push-target risk: mitigated by remote verification; only `origin develop` is allowed.
- Local work loss risk: mitigated by `backup/before-upstream-sync-20260602-2303` and normal commits rather than reset/rebase.
- Conflict misunderstanding risk: no new conflict files existed in this run.
- SDR behavior risk: full non-GUI tests expose six SDR baseline mismatches, but the clean `HEAD` worktree reproduces them, so they are known current-branch baseline debt rather than a new regression from this sync pass.
- HDR/export risk: focused HDR/photo/export/color metadata tests passed.
- MLX/GPU risk: focused GPU/runtime/MLX hot-path tests passed.
- Documentation risk: the stale Chinese sync report was replaced with a current summary to remove obsolete force-push rollback guidance.

### Known Limits And Follow-Up

- The six SDR baseline/golden failures should be handled in a separate SDR baseline reconciliation task. Do not silently update baselines unless the current SDR behavior is explicitly accepted as the new reference.
- The temporary clean worktree `/tmp/spektrafilm-head-VUcgYc` can be removed after final reporting.
- Push is safe only as a normal `git push origin develop`; no upstream push and no force push are permitted.
