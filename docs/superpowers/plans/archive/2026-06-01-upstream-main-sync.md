# Upstream Main Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge `upstream/main` into local `develop` without rebasing, force-pushing, resetting, or discarding local Spektrafilm work.

**Architecture:** Treat this as a backup-first Git integration task. The current workspace already contains substantial uncommitted source, test, documentation, benchmark, Android, GPU, MLX, Halide, HDR, and GUI work, so the first implementation step is to preserve that work in ordinary local history before the upstream merge. Then create the required backup branch at the clean pre-merge tip and merge `upstream/main` with per-file conflict review.

**Tech Stack:** Git 2.15.0, `uv`, Python 3.13 local virtualenv, pytest, Spektrafilm runtime/GUI/GPU/HDR test suite.

---

## Initial Audit Snapshot

- Repository: `/Users/retriedstormtrooper/Documents/spektrafilm-main`
- Current branch: `develop`
- Current HEAD before any preservation commit: `e9022e68cfe62066d7654a69c0acc6967a3fdfa9`
- `origin`: `https://github.com/21Z121Z1/spektrafilm.git`
- `upstream`: `https://github.com/andreavolpato/spektrafilm.git`
- `upstream/main` after fetch: `500bc429b7e93450ef228305c319dc03d8e185d1`
- Pre-merge divergence: `git rev-list --left-right --count HEAD...upstream/main` returned `360 31`
- `develop` vs `origin/develop`: `0 0`
- Working tree: not clean. It contains modified tracked files, staged documentation archive renames, and untracked source, tests, scripts, docs, `macos/`, and `.codex/`.
- Required backup branch name: `backup/before-upstream-sync-20260601-1747`

## Non-Negotiable Safety Rules

- Do not run `git reset --hard`.
- Do not run `git rebase upstream/main`.
- Do not run `git push --force`.
- Do not use broad `git checkout --theirs` or broad `git checkout --ours`.
- Do not delete local files to make the merge easy.
- Preserve SDR preview/output behavior. HDR additions must stay export-only or on explicit HDR rendition paths.
- Preserve local HDR, HEIC, Apple Adaptive HDR, profile-aware HDR, MLX/GPU acceleration, color management, film simulation, export, test, and documentation work.

### Task 1: Protect The Dirty Workspace

**Files:**
- Modify: `.gitignore`
- Create: external snapshot under `/Users/retriedstormtrooper/Documents/spektrafilm-main-git-backups/before-upstream-sync-20260601-1747/`
- Commit: existing local dirty work plus this plan, excluding generated caches and local app build products already ignored by `.gitignore`

- [ ] **Step 1: Save status and diffs outside the repository**

Run:

```bash
mkdir -p /Users/retriedstormtrooper/Documents/spektrafilm-main-git-backups/before-upstream-sync-20260601-1747
git status --short --branch > /Users/retriedstormtrooper/Documents/spektrafilm-main-git-backups/before-upstream-sync-20260601-1747/status-before-preserve.txt
git diff > /Users/retriedstormtrooper/Documents/spektrafilm-main-git-backups/before-upstream-sync-20260601-1747/unstaged-before-preserve.patch
git diff --cached > /Users/retriedstormtrooper/Documents/spektrafilm-main-git-backups/before-upstream-sync-20260601-1747/staged-before-preserve.patch
```

Expected: files are written outside the repository. No repository files are modified by these commands.

- [ ] **Step 2: Ignore local Codex cache**

Add `.codex/` to `.gitignore`, keeping `.DS_Store`, build products, and Android local state ignored.

- [ ] **Step 3: Stage only repository work**

Run:

```bash
git add -A
git reset -- .codex
git status --short --branch
```

Expected: `.codex/` is not staged. Ignored macOS build outputs remain untracked/ignored, not committed.

- [ ] **Step 4: Commit preserved local work**

Run:

```bash
git commit -m "chore: preserve local work before upstream sync"
```

Expected: a normal local commit records current tracked and relevant untracked repository work. The working tree is clean apart from ignored local build/cache outputs.

### Task 2: Create Required Backup Branch

**Files:**
- Git ref: `refs/heads/backup/before-upstream-sync-20260601-1747`

- [ ] **Step 1: Create backup branch at the clean pre-merge tip**

Run:

```bash
git branch backup/before-upstream-sync-20260601-1747
git show-ref --verify refs/heads/backup/before-upstream-sync-20260601-1747
```

Expected: the backup branch points at the preserved local pre-merge tip.

- [ ] **Step 2: Reconfirm clean state and divergence**

Run:

```bash
git status --short --branch
git rev-list --left-right --count HEAD...upstream/main
```

Expected: clean tracked state, ignored local artifacts only, and nonzero behind count before merge.

### Task 3: Merge Upstream Main

**Files:**
- Modify: any files changed by the real merge from `upstream/main`

- [ ] **Step 1: Start a non-rebase merge**

Run:

```bash
git merge --no-ff upstream/main
```

Expected: either a clean merge commit or explicit conflicted files for manual resolution. Do not substitute rebase, squash, reset, or broad file overwrite.

- [ ] **Step 2: If conflicts occur, inspect each file**

Run:

```bash
git status --short
git diff --name-only --diff-filter=U
```

For every conflicted file:

1. Inspect base, ours, and theirs with `git show :1:path`, `git show :2:path`, and `git show :3:path`.
2. Preserve local HDR, GPU, color, GUI, runtime, export, and test invariants.
3. Manually integrate upstream fixes where compatible.
4. Document the file-level principle in the final sync report.

### Task 4: Verify The Merged Tree

**Files:**
- Create or modify: `docs/dev/2026-06-01-upstream-main-sync-report.md`

- [ ] **Step 1: Required Git checks**

Run:

```bash
git status --short --branch
git diff --check
```

Expected: no unresolved conflicts and no whitespace errors.

- [ ] **Step 2: Fast Python syntax gate**

Run:

```bash
.venv/bin/python -m compileall -q src/spektrafilm src/spektrafilm_gui tests
```

Expected: exit code 0, or a clear environment/tooling failure that is not a code regression.

- [ ] **Step 3: Targeted merge-sensitive pytest slices**

Run:

```bash
uv run --extra dev pytest -q tests/test_runtime_api.py tests/test_pipeline_smoke.py tests/test_color_management.py tests/test_gain_map.py tests/test_gpu_backend.py tests/test_gpu_color_chain.py tests/test_gpu_pipeline.py tests/test_halide_spectral.py tests/test_spectral_lut_service.py tests/test_grain.py
```

Expected: pass, or documented environment-only failure. These cover runtime API, SDR pipeline smoke, color management, gain maps, GPU/MLX/Halide-adjacent behavior, LUT lifecycle, and grain.

- [ ] **Step 4: Wider non-GUI gate**

Run:

```bash
.venv/bin/python -m pytest --ignore=tests/gui -q
```

Expected: pass, or documented environment-only failure. This follows local `CLAUDE.md` and avoids GUI tests when no display/QApplication is guaranteed.

- [ ] **Step 5: Final repository audit**

Run:

```bash
git rev-list --left-right --count HEAD...upstream/main
git ls-tree -r --name-only HEAD | rg '(^|/)__pycache__/|(^|/)\\.DS_Store$|\\.pyc$'
git status --short --branch
```

Expected: behind count is `0`, no generated cache files in committed tree, and clean tracked state.

### Task 5: Final Documentation And Completion Check

**Files:**
- Modify: `docs/dev/2026-06-01-upstream-main-sync-report.md`

- [ ] **Step 1: Record final report**

The report must include:

1. Current branch name.
2. Backup branch name.
3. Merge-before and merge-after ahead/behind counts.
4. Conflict file list.
5. Per-conflict handling principle.
6. Commands run and results.
7. Push recommendation and non-force push command.

- [ ] **Step 2: Commit report if the merge did not already commit it**

Run:

```bash
git add docs/dev/2026-06-01-upstream-main-sync-report.md
git commit -m "docs: record upstream main sync validation"
```

Expected: final documentation is in branch history and `git status --short --branch` is clean.

- [ ] **Step 3: Self-audit before completion**

Ask: "Do I have factual 100% confidence that every explicit requirement is proven by current evidence?"

If no, list the gap, gather stronger evidence, and repeat verification. If yes, leave the goal complete and recommend only a normal non-force push:

```bash
git push origin develop
```
