# Codex Plugin Adversarial Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Recreate the useful behavior of OpenAI `codex-plugin-cc` `/codex:adversarial-review` for the current `spektrafilm-main` worktree, perform a fresh skepticism-first review, fix every currently defensible blocking issue, and leave durable documentation plus verification evidence.

**Architecture:** The upstream command is read-only and has three separable pieces: target selection from git state, repository-context collection, and a skeptical JSON-constrained review prompt. This plan adapts that into a local two-phase workflow: first produce a grounded adversarial review of the current dirty worktree and repository risk surfaces, then implement only fixes that are proven by current code and tests.

**Tech Stack:** Python 3.13, pytest, NumPy/SciPy/colour-science/OpenImageIO, optional MLX/CuPy/Halide GPU backends, Android Gradle/JNI diagnostics, git worktree state, Markdown docs.

---

## Upstream Mechanics To Replicate

- Slash command: `plugins/codex/commands/adversarial-review.md` in `openai/codex-plugin-cc`.
- Runtime: `plugins/codex/scripts/codex-companion.mjs`, subcommand `adversarial-review`.
- Prompt: `plugins/codex/prompts/adversarial-review.md`.
- Output schema: `plugins/codex/schemas/review-output.schema.json`.
- Git context: `plugins/codex/scripts/lib/git.mjs`.

The upstream command:

1. Keeps the slash command review-only and prevents patching inside the command.
2. Preserves user focus text instead of rewriting the review instruction.
3. Resolves the review target with the same semantics as `/codex:review`: dirty working tree first, otherwise branch diff, with `--base` and `--scope auto|working-tree|branch`.
4. Inlines diffs only for tiny reviews; for larger reviews it supplies status, stats, changed file names, and tells Codex to self-collect with read-only git/file commands.
5. Forces an adversarial stance: try to break confidence, report material risks only, ground every finding in file/line evidence, and return `approve` or `needs-attention` JSON.

This local run differs in one deliberate way: the user requested remediation after review, so the review phase remains skeptical/read-only, then the implementation phase fixes issues that survive validation.

## Current Workspace Constraints

- Repository root: `/Users/retriedstormtrooper/Documents/spektrafilm-main`.
- Branch: `develop`.
- Current worktree is heavily dirty across source, tests, docs, archived docs, GPU runtime work, Android docs, benchmark artifacts, and prior adversarial review reports.
- Treat every pre-existing modified, renamed, and untracked file as user work. Do not delete or revert it.
- Follow `CLAUDE.md`: use `.venv/bin/python` or `uv run --extra dev`; keep code changes inside `src/`, `tests/`, `docs/`, `README.md`, and `pyproject.toml`; preserve working code paths and add tests for validation changes.
- For HDR/imaging changes, preserve SDR behavior unless the defect is explicitly in SDR routing.
- For Android, current memory says the implementation is Kotlin/Compose plus JNI diagnostic plumbing, not a full renderer; missing NDK should be reported as an environment/toolchain blocker rather than patched around.

## Review Lenses

Run the adversarial pass through these lenses, keeping only material findings:

1. Git/worktree integration risk: current changes versus prior completed adversarial remediation docs.
2. Public input and resource boundary risk: profile names, image metadata, file paths, binary parsing, subprocess and revision arguments.
3. Numeric correctness risk: NaN/Inf handling, shape mismatches, dtype drift, GPU parity, clipping, interpolation/extrapolation.
4. Runtime architecture risk: mutable cross-stage state, update/reinitialization behavior, cache invalidation, stale prepared state.
5. GUI and I/O risk: save routing, HDR/SDR metadata ownership, file handle lifecycle, headless-safe test behavior.
6. Android/JNI risk: direct buffer validation, native preflight, diagnostic-only status, doc truthfulness.
7. Documentation and test risk: stale docs pointing to superseded implementation paths, missing tests for fixed defects, over-broad claims of completion.

## Task 1: Freeze Evidence And Inputs

**Files:**
- Read: `CLAUDE.md`
- Read: `pyproject.toml`
- Read: `README.md`
- Read: `docs/dev/2026-05-30-adversarial-code-review.md`
- Read: `docs/dev/2026-05-30-adversarial-code-review-v5.md`
- Read: `docs/dev/2026-05-31-adversarial-review-remediation-report.md`
- Create: `docs/dev/2026-05-31-codex-plugin-adversarial-review-report.md`

- [x] **Step 1: Capture git state**

Run:

```bash
git status --short --untracked-files=all
git symbolic-ref --short HEAD || git rev-parse --short HEAD
git diff --shortstat
git diff --cached --shortstat
```

Expected: a dirty `develop` worktree is recorded without reverting user changes.

- [x] **Step 2: Capture upstream implementation facts**

Record the command, runtime, prompt, schema, and git target selection facts from the cloned `/tmp/codex-plugin-cc` checkout and the GitHub source links.

- [x] **Step 3: Capture prior local review state**

Summarize which previous findings were fixed, rejected, or still deferred based on the three prior review/remediation documents.

## Task 2: Re-run A Fresh Adversarial Review

**Files:**
- Inspect: `src/spektrafilm/**/*.py`
- Inspect: `src/spektrafilm_gui/**/*.py`
- Inspect: `scripts/*.py`
- Inspect: `android/**/*`
- Inspect: `tests/**/*.py`
- Write: `docs/dev/2026-05-31-codex-plugin-adversarial-review-report.md`

- [x] **Step 1: Build changed-file and risk worklists**

Run:

```bash
git diff --name-only
git diff --cached --name-only
rg --files src scripts android tests docs | sort
```

Expected: changed files and high-risk runtime files are separated from docs/benchmark artifacts.

- [x] **Step 2: Search for adversarial patterns**

Run targeted searches for:

```bash
rg -n "eval\\(|exec\\(|pickle|yaml\\.load|subprocess|os\\.system|shell=True|open\\(|ImageInput\\.open|json\\.load|np\\.random\\.seed|get_state|set_state|nan_to_num|isfinite|clip\\(|GetDirectBufferAddress|ByteBuffer|TODO|FIXME|print\\(" src scripts android tests
```

Expected: every promoted finding has a concrete path from source to sink or broken control.

- [x] **Step 3: Inspect prior deferred candidates against live code**

Check v5 medium/low candidates and the latest remediation report against current source. Promote only items that still identify active user-visible failure, crash, silent corruption, security, or high-confidence test gap.

## Task 3: Add Tests For Surviving Findings

**Files:**
- Modify only relevant test files under `tests/`.

- [x] **Step 1: Write a failing regression test for each accepted issue**

For each accepted finding, write the smallest test that proves the current behavior is wrong.

- [x] **Step 2: Run each new test before production changes**

Run:

```bash
uv run --extra dev pytest -q <targeted test file>::<test_name>
```

Expected: the test fails for the reviewed defect, not from unrelated environment breakage.

Actual: the tests were added before production changes, but local pytest did not reach collection because Homebrew Python 3.13 stalled while loading dynamic modules before test code executed. This blocker is recorded in `docs/dev/2026-05-31-codex-plugin-adversarial-review-report.md`.

## Task 4: Implement Minimal Fixes

**Files:**
- Modify only the production files responsible for accepted findings.

- [x] **Step 1: Patch the narrowest boundary**

Prefer validation, guard, cache invalidation, or routing fixes over broad refactors.

- [x] **Step 2: Preserve existing behavior**

Keep SDR defaults, public API compatibility, and optional-backend skip behavior unchanged unless the failing regression test proves they are the defect.

- [x] **Step 3: Re-run the targeted regression test**

Run:

```bash
uv run --extra dev pytest -q <targeted test file>::<test_name>
```

Expected: the new test passes and nearby tests still pass.

Actual: pytest remained blocked before collection by the same Python 3.13 dynamic-module loader issue. Replacement verification used Python syntax compilation, static source assertions, `git diff --check`, and an Android NDK AOT C++ syntax check.

## Task 5: Document The Final Review And Remediation

**Files:**
- Create/update: `docs/dev/2026-05-31-codex-plugin-adversarial-review-report.md`
- Update if behavior changes: nearest relevant `docs/dev/*.md` or README entry.

- [x] **Step 1: Record findings**

Use a compact schema: severity, status, file/lines, evidence, recommendation, remediation, and verification.

- [x] **Step 2: Record rejected/deferred items**

For every tempting but rejected candidate, state exact counterevidence or why it belongs to a future broad refactor rather than this patch.

- [x] **Step 3: Update current docs**

Before completion, update either the new report or the relevant domain doc with final current-state facts and verification evidence.

## Task 6: Verification And Confidence Loop

**Commands:**

```bash
uv run --extra dev pytest -q <targeted tests touched by this pass>
uv run --extra dev pytest -q
uv run --extra dev python -m compileall -q src tests scripts
git diff --check
```

- [x] **Step 1: Run targeted tests**

Expected: every new/fixed behavior test passes.

Actual: targeted pytest invocation was attempted but blocked before collection by Homebrew Python 3.13 dynamic-module loading.

- [x] **Step 2: Run broad tests**

Expected: full suite passes or any failure is documented with exact environment/root-cause evidence.

Actual: the environment/root-cause evidence is documented in the final report; full pytest was not a valid signal in this local runtime until the Python loader issue is fixed.

- [x] **Step 3: Run static checks**

Expected: compileall and `git diff --check` pass.

Actual: scoped Python syntax compilation, static source assertions, Android AOT C++ syntax, and `git diff --check` passed. Full `compileall` through `.venv` is blocked by the same Python 3.13 dynamic loader issue.

- [x] **Step 4: Re-open assumptions**

Ask: do I have factual confidence that every accepted issue is fixed, every rejected/deferred item has counterevidence, docs are current, and verification is fresh? If not, add the missing test, fix, or documentation and repeat the loop.

Actual: accepted C++ issue has syntax-level and source-level closure. Python fixes have code-inspection and syntax confidence but not runtime pytest proof because pytest cannot start in the current Python 3.13 environment.
