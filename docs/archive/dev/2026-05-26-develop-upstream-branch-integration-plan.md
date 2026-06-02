> **STATUS: COMPLETED**. upstream/main merge into develop completed 2026-05-29 (commit 7cb4f87).

# Develop Upstream Branch Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:verification-before-completion before claiming completion. This integration is history and behavior preservation work, not a blind upstream replacement.

**Goal:** Produce a validated `develop` branch that contains intended local work from the scoped local branches and current `andreavolpato/spektrafilm:main`, then push it to `origin/develop`.

**Architecture:** Use local `develop` as the target branch so its explicit tracking/test/lockfile intent is preserved. Merge `main-sync` to bring the broad HDR/GPU/runtime/upstream integration because it already contains the backup snapshot and current upstream `main`; then merge color-management branch tips carefully so narrow PR fixes are not lost. Resolve conflicts by preserving local GPU, HDR, color-management, profile-aware export, runtime safety, and tracked test/docs/lockfile intent unless upstream is clearly equivalent or better.

**Tech Stack:** Git 2.15.0, Python 3.13 Spektrafilm package, `uv`, pytest, OpenImageIO, PySide/Qt, MLX/CuPy optional GPU backends.

---

## Audit Snapshot

Audit timestamp: `2026-05-26T22:55:33+0800`.

Current checkout:

- Current branch: `main-sync`.
- Current `HEAD`: `30f7436a56a1fc9a684f9fc85bb21b5617c4821f` (`Revert "refactor: GPU kernel improvements - async-safe highlight boost, density/LUT/diffusion/grain refinements"`).
- Worktree state: no tracked modifications; untracked local artifacts only:
  - `.matplotlib/` (`164K`, font cache)
  - `scratch/` (`9.4M`, DNG/HDR analysis scratch files)
  - `scratch_precision_test.py` (`4.0K`)
  - `output.heic` (`4.0K`)
- These untracked artifacts are preserved in place but must not be staged or committed.
- Git isolation check: this is a normal checkout (`.git` equals common dir), not a linked worktree. The user requested the real `develop` branch, so work continues in place after creating a safety ref.

Post-plan correction discovered during implementation:

- Checkout from `main-sync` to `develop` exposed three tracked HDR/UI edits that were present after the initial audit: `src/spektrafilm/utils/hdr_curve_profiles.py`, `src/spektrafilm/utils/hdr_photo.py`, and `src/spektrafilm_gui/widget_sections.py`.
- Those edits were inspected, classified as relevant HDR/profile-aware UI work, and preserved with stash entry `temp preserve HDR profile-aware edits before develop integration` for reapplication during integration.
- Switching to `develop` also exposed previously ignored local docs/tests as untracked because `develop` stops ignoring `docs/` and `tests/`. They remain preserved in the working tree but out of the index unless explicitly selected.
- The `main-sync` merge staged root-level debug outputs and scratch/evaluation files. They were excluded from the final merge because they are generated/debug artifacts, while reusable tools under `tools/` and packaged HDR curve data under `src/spektrafilm/data/hdr_curve_profiles/` are retained.

Remotes:

- `origin`: `https://github.com/21Z121Z1/spektrafilm.git`
- `upstream`: `https://github.com/andreavolpato/spektrafilm.git`

Fetched refs after `git fetch --all --prune`:

- `upstream/main`: `48645a2b4bf58c20b6a3b75c8022d0f462db754a` (`docs: update high-res banner`)
- `upstream/dev`: `48645a2b4bf58c20b6a3b75c8022d0f462db754a`
- `origin/develop`: `95001bf1aa820e1ac246adc3f074efccfd9a32e3` (`Merge upstream main baseline`)
- `origin/color-management-pr`: `c0de6b17ea1c2feedae74c313f4fc6c9b62fa52f` (`Potential fix for pull request finding`)

Local branches discovered:

| Branch | SHA | Tracking | Relative evidence | Handling |
| --- | --- | --- | --- | --- |
| `backup/main-sync-before-upstream-48645a2-20260525T183007` | `b8bd9a6f51c15bc5434ef8b25b148d2dd2cf5cee` | none | `main-sync...backup` = `9 0`, so `main-sync` already contains this backup. Against `develop`, backup has 19 unique commits and lacks the 2 local tracking commits. | Treat as safety/backup snapshot, not a separate feature branch to re-merge after `main-sync`; document containment. |
| `color-management-pr` | `a44068e8b4734ac743b538222bf2e9f63cca24c7` | `origin/color-management-pr` | Local branch is `ahead 1, behind 1`; `color-management-pr...origin/color-management-pr` = `1 1`. Unique local tip adds LUT-service reuse, `film_format_mm` float handling, persistence cleanup, and docs. | Include meaningful unique local work after broad local integration, resolving conflicts in favor of current local GPU/HDR/runtime behavior. |
| `develop` | `887fe9e9f3b70caae58ce758c6ef2c6f8a0438cf` | `origin/develop` | `develop...origin/develop` = `2 0`. The 2 local commits track previously ignored GPU tests and `uv.lock`, then stop ignoring `tests/`, `docs/`, and `uv.lock`. | Target branch. Preserve its tracked-test/docs/lockfile intent. |
| `main-sync` | `30f7436a56a1fc9a684f9fc85bb21b5617c4821f` | `upstream/main` | `main-sync...upstream/main` = `14 0`; `develop...main-sync` = `2 28`. Contains backup, upstream `48645a2`, HDR export fixes, profile-aware HDR recovery, GPU/backend work, and a revert of one GPU kernel-refactor commit. | Merge into `develop` first. This is the broad local integration branch. |

Other refs:

- `refs/stash` contains a previous temporary stash from `develop`; it is not a local branch and will not be merged.
- `refs/codex/snapshots/ed2c0a8d6450c7092654a8ac49f946996cd11817` is an archive-cleanup snapshot ref, not an integration branch.
- Remote-only upstream branches (`upstream/lut-export`, `upstream/couplers-tuning-iterations`) are not in scope and will not be merged blindly.

## Branch Intent And Risk Inventory

Local feature intent that must be preserved:

- `develop`: repo hygiene intent to track `tests/`, `docs/`, and `uv.lock`; keep generated caches and local scratch untracked.
- `main-sync`: current broad local state, including upstream `48645a2`, HDR export SDR-base fix, profile-based modern HDR recovery with fixed EV budget, current HDR curve/profile data, RAW scene-energy sidecar plumbing, CoreImage HEIC/HDR encoder, EXR/HDR output routing, GUI HDR controls, ACES/color workflow, GPU backend infrastructure, MLX/CuPy paths, runtime smoke updates, and the intentional revert of a risky GPU kernel refactor.
- `backup/main-sync-before-upstream-48645a2-20260525T183007`: safety snapshot before the upstream baseline merge; meaningful feature content is already present through `main-sync`.
- `color-management-pr`: metadata-aware image I/O and `ColorEncoding` contract, OIIO float64 default restoration, output-layer color metadata propagation, LUT-service reuse and persistence cleanup, plus origin-only controller fix `c0de6b1`.

High-risk areas:

- `.gitignore`, `docs/`, `tests/`, and `uv.lock`: `develop` explicitly stopped ignoring these, while `main-sync` still ignores/deletes some of them. Preserve `develop` intent and keep generated caches out.
- `src/spektrafilm/utils/io.py`, `color_management.py`, GUI controller save paths, and controller runtime metadata: color branch and HDR branch both touch export/metadata contracts.
- `src/spektrafilm/utils/hdr_photo.py`, `hdr_curve_profiles.py`, `raw_file_processor.py`, and runtime sidecar plumbing: must not make SDR paths darker or infer HDR headroom from `look_rgb` alone.
- `src/spektrafilm/gpu/*`, runtime pipeline, LUT services, and precision defaults: must not disable MLX/CuPy/Metal or silently change float precision to make tests pass.
- `src/spektrafilm_gui/state.py`, `options.py`, `widget_specs.py`, `widget_sections.py`: schema and GUI state migration conflicts are likely.
- `src/spektrafilm/utils/autoexposure.py` and profile JSON data: upstream exposure-metering/film-format changes and local scene-linear autoexposure must coexist.
- Root-level debug outputs and scratch scripts tracked on `main-sync`: preserve behavior but avoid committing generated junk in the final integration if not required by runtime/tests/docs.

## Integration Strategy

1. Preserve the current starting point with a local safety branch before modifying `develop`:
   - `backup/develop-integration-start-20260526T225533`
   - Target commit: current `main-sync` `30f7436a56a1fc9a684f9fc85bb21b5617c4821f`
2. Check out local `develop` (`887fe9e9f3b70caae58ce758c6ef2c6f8a0438cf`).
3. Merge `main-sync` into `develop` with `--no-ff --no-commit` for inspectable conflict resolution.
   - Safe order rationale: `main-sync` already contains the backup branch and upstream `48645a2`, so this single merge brings the broad local HDR/GPU/runtime state and upstream progress while keeping `develop` as the target.
   - Resolution rule: preserve `develop` `.gitignore`/tracked-test/docs/`uv.lock` intent; preserve `main-sync` runtime/HDR/GPU behavior.
4. Resolve conflicts and inspect staged diff before committing.
5. Merge `color-management-pr` with `--no-ff --no-commit`.
   - Safe order rationale: apply the narrow color-management branch after the broad local branch so older PR-slice code cannot replace newer HDR/GPU/runtime surfaces.
   - If a change is already superseded by `main-sync`, keep the newer local implementation and document it as contained/superseded.
6. Merge or cherry-pick `origin/color-management-pr` tip `c0de6b1` if it is not already included by the local branch merge.
   - It is one controller-line fix and is likely intended remote feedback on the same PR branch.
7. Confirm `upstream/main` is incorporated.
   - `main-sync` already contains `upstream/main` at `48645a2`; after the `main-sync` merge, `develop...upstream/main` should show no upstream-only commits, or `git merge-base --is-ancestor upstream/main HEAD` should succeed.
   - If upstream advances during the work, fetch again and merge the new `upstream/main` using normal content merge unless it would regress local functionality; then resolve by inspection.
8. Remove generated/junk tracked by the integration only when it is not required by code, tests, or docs:
   - Never stage `.DS_Store`, `__pycache__/`, `.pyc`, `.pytest_cache/`, `.matplotlib/`, `scratch/`, `scratch_precision_test.py`, or `output.heic`.
   - Re-evaluate root `debug/` outputs and root scratch/eval scripts before final commit; keep reusable tools under `tools/` and durable docs under `docs/`.
9. Commit the integrated `develop` branch with a merge/integration message.
10. Validate, fix integration-caused failures, re-run validation, then push only `develop` to `origin`.

Avoided strategies:

- No force-push unless validation proves the remote branch must be rewritten. The expected result is a normal push from an updated local `develop`.
- No blind `ours` merge for upstream content because the goal is to include upstream progress and local branch work, not merely record ancestry. Use local-wins resolutions only for concrete conflicts/regressions.
- No merge of unrelated remote-only upstream feature branches.

## Upstream Synchronization Strategy

- Current `upstream/main` is `48645a2b4bf58c20b6a3b75c8022d0f462db754a`.
- `main-sync` already contains `upstream/main` (`main-sync...upstream/main` = `14 0`), including `dac7c51` and `37a1ac1`.
- The final branch must prove upstream containment with:
  - `git merge-base --is-ancestor upstream/main HEAD`
  - `git rev-list --left-right --count HEAD...upstream/main`
- Upstream changes are accepted for compatible docs/infrastructure/bug fixes, but local behavior wins for HDR, color management, GPU/MLX/Metal, profile-aware export, precision, large-image/runtime safety, and GUI preview/export parity.

## Validation Commands

Use project tooling from `pyproject.toml`, `pytest.ini`, README, and prior successful runs.

Required final checks:

```bash
git diff --check
uv run --extra dev pytest -q
git status --short --branch
git log --oneline --decorate --graph --max-count=40
git ls-tree -r --name-only HEAD | rg '(^|/)__pycache__/|(^|/)\\.DS_Store$|\\.pyc$|^\\.pytest_cache/|^\\.matplotlib/|^scratch/|^output\\.heic$'
```

Targeted integration checks:

```bash
uv run --extra dev pytest -q tests/test_color_management.py tests/test_image_io_color_metadata.py tests/test_hdr_photo.py tests/test_raw_file_processor.py tests/test_runtime_api.py tests/test_pipeline_smoke.py
uv run --extra dev pytest -q tests/test_gpu_backend.py tests/test_gpu_color_chain.py tests/test_gpu_density.py tests/test_gpu_filters.py tests/test_gpu_lut.py
uv run --extra dev pytest -q tests/gui/test_controller_output.py tests/gui/test_controller_runtime_module.py tests/gui/test_controller_flow.py tests/gui/test_params_mapper.py tests/gui/test_persistence.py tests/gui/test_app.py
uv run python -m compileall -q src/spektrafilm src/spektrafilm_gui tests
```

If the full suite fails due to missing optional system dependencies or pre-existing upstream baseline failures, capture exact output, then run the maximum meaningful targeted subset and separate environment/upstream failures from integration regressions.

## Rollback Strategy

- Safety branch from starting state: `backup/develop-integration-start-20260526T225533`.
- Existing scoped backup branch remains untouched: `backup/main-sync-before-upstream-48645a2-20260525T183007`.
- If a merge goes wrong before commit, abort with `git merge --abort`.
- If an integration commit is bad before push, create a diagnostic branch at the bad state, reset local `develop` back to the previous safety ref or `origin/develop`, and repeat with a narrower merge/cherry-pick.
- If push succeeds but a defect is later found, push a normal follow-up fix commit to `origin/develop`; avoid force-push unless there is no safe alternative and it is documented.

## Definition Of Done

- Local `develop` is the checked-out final branch.
- `upstream/main` at `48645a2b4bf58c20b6a3b75c8022d0f462db754a` is an ancestor of final `develop`.
- Each in-scope branch is either merged, already contained, or explicitly classified:
  - `backup/...`: contained through `main-sync`, backup only.
  - `main-sync`: merged.
  - `develop`: target and preserved.
  - `color-management-pr`: meaningful unique local and origin tracking work included or documented as superseded by newer integrated code.
- Local feature surfaces are reviewed and tested: HDR photo export, SDR preservation, scene-energy sidecars, EXR/HEIC export, color metadata, GPU/MLX/CuPy paths, precision defaults, profile defaults, print/scan route behavior, GUI runtime safety, and preview/export parity.
- Required and targeted validation commands pass, or non-passing checks are proven environmental/pre-existing and documented with exact evidence.
- Final tree does not track caches, `.DS_Store`, `__pycache__`, `.pyc`, untracked scratch outputs, or unrelated local artifacts.
- `origin/develop` is pushed successfully and points at the final integrated commit.
