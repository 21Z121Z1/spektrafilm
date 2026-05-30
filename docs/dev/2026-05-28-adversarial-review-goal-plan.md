# Spektrafilm Adversarial Review Goal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recreate the useful behavior of OpenAI's `/codex:adversarial-review` against this workspace, fix all defensible blocking findings, update durable docs, and verify the result.

**Architecture:** The upstream command is a read-only, skepticism-first review wrapper: it resolves a git target, collects repository context, injects it into an adversarial review prompt, requires grounded JSON findings, and keeps fixes out of the review command. For this goal, the review phase is adapted into an in-repo evidence loop, then this agent performs the requested implementation phase with tests-first fixes.

**Tech Stack:** Python 3.13, pytest, OpenImageIO, Qt/napari GUI tests, macOS Swift HEIC helper where available, local git state, and repository docs under `docs/dev`.

---

## Upstream `/codex:adversarial-review` Implementation Notes

- Slash command entry: `/tmp/codex-plugin-cc/plugins/codex/commands/adversarial-review.md`.
- Runtime entry: `/tmp/codex-plugin-cc/plugins/codex/scripts/codex-companion.mjs`, subcommand `adversarial-review`.
- Review prompt: `/tmp/codex-plugin-cc/plugins/codex/prompts/adversarial-review.md`.
- Schema: `/tmp/codex-plugin-cc/plugins/codex/schemas/review-output.schema.json`.
- Git context collector: `/tmp/codex-plugin-cc/plugins/codex/scripts/lib/git.mjs`.

The command does four important things:

1. It keeps the slash command review-only. The command itself must not patch files.
2. It selects the target using the same semantics as `/codex:review`: dirty working tree first, otherwise branch diff, with `--base` and `--scope` support.
3. It collects inline diff for small reviews and lightweight context for larger reviews, telling Codex to use read-only git commands to self-collect more evidence when needed.
4. It forces a skeptical prompt and JSON output: `approve` or `needs-attention`, material findings only, grounded file/line references, confidence, and concrete recommendations.

This workspace task intentionally extends the model: first perform that adversarial review, then implement the fixes the review can defend, because the user explicitly requested review plus remediation.

## Current Workspace Constraints

- Repository: `/Users/retriedstormtrooper/Documents/spektrafilm-main`.
- Current branch detected with old-Git-compatible command: `develop`.
- Existing status before this plan included only untracked files/directories, including `.matplotlib/`, `docs 2/`, `docs/agent_audit/`, several `docs/dev/*.md`, `docs/superpowers/`, `output.heic`, `scratch/`, and `scratch_precision_test.py`.
- Treat all pre-existing untracked files as user work. Do not delete, move, or normalize them unless required for the requested goal.
- Follow `CLAUDE.md`: use `.venv/bin/python` or `uv run --extra dev`, keep fixes within `src/`, `tests/`, `docs/`, `README.md`, and `pyproject.toml`, preserve SDR behavior, and add tests for validation changes.

## Review Focus

The adversarial stance for this workspace is:

- Find strongest reasons the current branch should not ship.
- Prioritize user-visible HDR/export/color issues, silent data corruption, wrong metadata, expensive memory behavior, GUI runtime mismatches, test harness failures, and compatibility regressions.
- Ignore pure style, naming, and cleanup unless they hide material risk.
- Revalidate old review findings against live code before relying on them.
- Treat older docs and memory as leads, not proof.

## Planned Execution

### Task 1: Freeze Review Inputs

**Files:**
- Read: `CLAUDE.md`
- Read: `pyproject.toml`
- Read: `README.md`
- Read: `docs/dev/code-review-2026-05-26.md`
- Read: `docs/dev/2026-05-26-full-workspace-code-review.md`
- Create/update: `docs/dev/2026-05-28-adversarial-review-report.md`

- [ ] Record current `git status --short`, branch, HEAD commit, and relevant remotes in the report.
- [ ] Summarize upstream `/codex:adversarial-review` mechanics in the report.
- [ ] Inventory source, tests, docs, and tool entry points with `rg --files`.
- [ ] Re-check old findings C1/H1/H2/M1/M2/M3/M4/L1 against current source before marking them fixed or still live.

### Task 2: Run Evidence-First Baseline

**Files:**
- Test: `tests/test_hdr_photo.py`
- Test: `tests/test_image_io_color_metadata.py`
- Test: `tests/gui/test_controller_output.py`
- Test: `tests/gui/test_controller_runtime_module.py`
- Test: `tests/test_runtime_api.py`
- Test: `tests/test_gpu_*`

- [ ] Run targeted tests around HDR photo mapping, image I/O metadata, GUI save routing, controller runtime color transforms, and runtime metadata.
- [ ] Run static searches for risky patterns: unbounded metadata sidecars, GUI dialog calls in headless tests, bare exceptions around worker boundaries, HDR path controls not forwarded, ICC mappings, and color-space fallbacks.
- [ ] Record failures and command evidence in `docs/dev/2026-05-28-adversarial-review-report.md`.

### Task 3: Write Failing Tests for Any Live Finding

**Files:**
- Modify tests only after the live finding is proven.
- Likely targets, depending on evidence:
  - `tests/test_hdr_photo.py`
  - `tests/test_image_io_color_metadata.py`
  - `tests/gui/test_controller_output.py`
  - `tests/gui/test_controller_runtime_module.py`
  - `tests/test_runtime_api.py`

- [ ] For each material finding, write the smallest test that fails for the risk.
- [ ] Run the specific test and confirm it fails for the expected reason.
- [ ] Do not edit production code before observing the failing test.

### Task 4: Implement Minimal Fixes

**Files:**
- Modify production files only for findings with failing tests.
- Likely targets, depending on evidence:
  - `src/spektrafilm/utils/hdr_photo.py`
  - `src/spektrafilm/utils/io.py`
  - `src/spektrafilm/color_management.py`
  - `src/spektrafilm/runtime/pipeline.py`
  - `src/spektrafilm_gui/controller.py`
  - `src/spektrafilm_gui/controller_runtime.py`
  - `src/spektrafilm_gui/controller_layers.py`

- [ ] Patch only the responsible boundary.
- [ ] Preserve existing SDR paths unless the failing test proves SDR behavior is wrong.
- [ ] Keep HDR-only behavior behind explicit HDR routes.
- [ ] Re-run the targeted failing test after each fix.

### Task 5: Documentation Update

**Files:**
- Create/update: `docs/dev/2026-05-28-adversarial-review-report.md`
- Update if behavior changes: `README.md`
- Update if API/testing contract changes: nearby docs under `docs/dev/`

- [ ] Record final findings, fixed/not-fixed decisions, and why.
- [ ] Document any remaining non-blocking risk honestly.
- [ ] If user-facing behavior changes, update README or the relevant dev doc.

### Task 6: Verification and Confidence Loop

**Commands:**
- `uv run --extra dev pytest -q <targeted tests>`
- `uv run --extra dev pytest -q`
- `uv run --extra dev python -m compileall -q src/spektrafilm src/spektrafilm_gui tests scripts`
- `git diff --check`

- [ ] Run targeted tests for touched behavior.
- [ ] Run the full non-GUI or full suite according to environment constraints.
- [ ] Run compileall.
- [ ] Run whitespace diff check.
- [ ] Re-read the diff and ask: "Do I have factual confidence that every implemented change is tested and every material review finding is either fixed or documented?"
- [ ] If confidence is not factual, add the missing test, fix, or doc entry and repeat the loop.

## Initial Self-Review of This Plan

- No placeholder tasks are left; each phase has concrete files and commands.
- The plan deliberately separates review from implementation to preserve the upstream command's adversarial discipline while still honoring the user's explicit request to fix issues.
- The plan avoids deleting or reverting user work in the dirty workspace.
- The likely fix list is not frozen from old docs; old findings must be revalidated against current code.
