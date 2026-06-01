# Markdown Documentation Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate and organize every Markdown document in the current `spektrafilm-main` workspace without deleting historical evidence or trampling concurrent implementation work.

**Architecture:** Keep `README.md` as the project front door, make `docs/README.md` the canonical documentation router, add focused directory-level indexes, and move the tracked `docs 2/` duplicate tree into a clearly labeled archive under `docs/archive/`. Existing source, tests, GPU work, and benchmark scripts remain untouched.

**Tech Stack:** Markdown, git file moves, shell-based inventory/link checks, `uv` or `.venv/bin/python` only for repository validation when needed.

---

## Current Inventory

- Workspace: `/Users/retriedstormtrooper/Documents/spektrafilm-main`
- Branch: `develop`
- Worktree isolation: normal checkout, not a linked worktree.
- Dirty worktree boundary: many pre-existing source/test/GPU changes exist. This plan only edits Markdown and doc paths.
- Markdown count excluding `.git`, `.venv`, `.pytest_cache`, and `__pycache__`: 300 files before this plan.
- Main document clusters:
  - Root docs: `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `CLAUDE.md`, `CLAUDE-RESEARCH.md`
  - Canonical docs tree: `docs/`
  - Duplicate legacy tree: `docs 2/`
  - Generated curve reports: `docs/curve_analysis/`
  - Development/review reports: `docs/dev/`
  - Audit reports: `docs/agent_audit/`
  - Agentic implementation plans: `docs/superpowers/plans/`
  - Runtime data notes: `src/spektrafilm/data/hdr_curve_profiles/README.md`, `src/spektrafilm/data/icc/README.md`

## Task 1: Preserve Boundaries And Add This Plan

**Files:**
- Create: `docs/superpowers/plans/2026-05-31-markdown-documentation-consolidation.md`

- [x] **Step 1: Record the current dirty worktree boundary**

Run:

```bash
git status --short
```

Expected: source/test/GPU changes may already be present. Do not revert them.

- [x] **Step 2: Save this plan before implementation**

Use `apply_patch` to create this plan file.

- [x] **Step 3: Confirm this plan is visible**

Run:

```bash
test -f docs/superpowers/plans/2026-05-31-markdown-documentation-consolidation.md
```

Expected: command exits 0.

## Task 2: Move The Legacy `docs 2` Tree Into A Real Archive

**Files:**
- Move: former `docs 2/dev/*.md` files to `docs/archive/docs-2-legacy-20260531/dev/*.md`
- Modify: `.gitignore` so `docs/archive/` documentation is not hidden by the root archive ignore rule
- Create: `docs/archive/README.md`
- Create: `docs/archive/docs-2-legacy-20260531/README.md`
- Modify references in Markdown files that mention the former `docs 2/dev/...` path

- [x] **Step 1: Verify `docs 2` is tracked and not externally referenced by code**

Run:

```bash
git ls-files 'docs 2/*'
rg -n "docs 2|docs%202|docs\\+2" . -g '*.md' -g '*.py' -g '*.sh'
```

Expected: references are Markdown-only and can be rewritten to archive paths.

- [x] **Step 2: Move the tracked tree**

Run:

```bash
mkdir -p docs/archive/docs-2-legacy-20260531
git mv "docs 2" docs/archive/docs-2-legacy-20260531
```

Expected: no top-level `docs 2/` directory remains; git records renames instead of deletes.

- [x] **Step 3: Rewrite legacy path references**

Replace references from:

```text
docs 2/dev/
```

to:

```text
docs/archive/docs-2-legacy-20260531/dev/
```

Expected: `rg -n "docs 2|docs%202|docs\\+2" . -g '*.md'` returns no references except this plan's historical description if preserved intentionally.

- [x] **Step 4: Add archive README files**

Create `docs/archive/README.md` explaining that archive documents are preserved evidence, not the active source of truth.

Create `docs/archive/docs-2-legacy-20260531/README.md` explaining why the former `docs 2/` tree was moved and how to compare it with canonical `docs/dev/`.

- [x] **Step 5: Keep documentation archives visible to git**

Change `.gitignore` from `archive/` to `/archive/` so a root-level generated archive remains ignored while `docs/archive/` can be tracked as documentation.

## Task 3: Create Directory-Level Indexes

**Files:**
- Create: `docs/dev/README.md`
- Create: `docs/agent_audit/README.md`
- Create: `docs/curve_analysis/README.md`

- [x] **Step 1: Add `docs/dev/README.md`**

Group development docs by:

- Current coordination and active reports
- GPU / MLX / Halide work
- Android / Halide port work
- GUI, memory, test, and code-quality work
- Historical review rounds

Expected: every direct Markdown file under `docs/dev/` is represented or covered by a named grouped rule.

- [x] **Step 2: Add `docs/agent_audit/README.md`**

List the audit entry points in priority order:

- `final_validation_report.md`
- `triaged_findings.md`
- `accepted_p0_p1.md`
- review dimension files
- architecture/test inventory support files
- upstream baseline contract file

Expected: all Markdown files under `docs/agent_audit/` are covered.

- [x] **Step 3: Add `docs/curve_analysis/README.md`**

Explain that this directory is a generated corpus, not hand-authored narrative docs. Point users to:

- `film_print_hdr_analysis.md`
- `curve_analysis.json`
- `analyze_curves.py`
- `generate_all_md.py`
- per-combination reports named `<film>_on_<paper>.md`

Expected: the index explains the count mismatch between summary docs and generated per-combination reports.

## Task 4: Refresh The Canonical Documentation Router

**Files:**
- Modify: `docs/README.md`
- Modify: `README.md`
- Modify: `CLAUDE.md` only if needed to point agents at the refreshed documentation router

- [x] **Step 1: Rewrite `docs/README.md` around current document topology**

Keep it concise enough to scan. Include:

- "Read first" section
- Current status and active work
- HDR / color / GPU entry points
- Development reports
- Audit reports
- Curve-analysis corpus
- Archive policy
- Runtime data notes
- A short "what not to treat as current truth" warning for old plans and archive docs

Expected: new untracked 2026-05-30/2026-05-31 docs are included and the old `docs 2` path is not used as an active entry point.

- [x] **Step 2: Add a small root README pointer**

Add a short "Documentation map" section to `README.md` linking to `docs/README.md`.

Expected: product README remains focused on the project and only gains one concise navigation section.

- [x] **Step 3: Update agent instruction pointer if stale**

If `CLAUDE.md` still points to a single older code-review file as the only documentation entry, add `docs/README.md` as the first documentation entry point while preserving the existing task-specific constraints.

Expected: future agents start from the router before deep-diving old review docs.

## Task 5: Verify Links, Coverage, And Formatting

**Files:**
- Modify indexes if validation finds omissions or stale references.

- [x] **Step 1: Recount Markdown inventory**

Run:

```bash
find . -path ./.git -prune -o -path ./.venv -prune -o -path ./.pytest_cache -prune -o -path ./__pycache__ -prune -o -iname '*.md' -print | wc -l
```

Expected: count may change by new index files and archive README files. No ordinary documentation is deleted.

- [x] **Step 2: Verify no live `docs 2` references remain**

Run:

```bash
rg -n "docs 2|docs%202|docs\\+2" . -g '*.md'
```

Expected: only intentional historical mentions in this plan are allowed.

- [x] **Step 3: Check Markdown links to local `.md` files**

Run a local link scan over Markdown files and fix broken relative links introduced by this task.

Expected: no broken links caused by the new archive path or new indexes.

- [x] **Step 4: Check diff whitespace**

Run:

```bash
git diff --check
```

Expected: no whitespace errors in the documentation diff.

## Task 6: Final Confidence Loop

**Files:**
- Modify: `docs/README.md`, `docs/dev/README.md`, or archive notes if self-audit exposes a gap.

- [x] **Step 1: Re-read changed documentation**

Check each changed Markdown file for stale claims, duplicated entry points, and links that imply old review reports are current truth.

- [x] **Step 2: Ask the factual confidence question**

Question: "Do I have factual 100% confidence that the documentation surface is organized, current entry points are clear, legacy docs are preserved, and no concurrent code work was altered?"

Expected: if the answer is not yes, identify the specific gap, patch it, and re-run relevant checks.

- [x] **Step 3: Final status check**

Run:

```bash
git status --short
```

Expected: documentation changes are visible; pre-existing source/test changes remain untouched.

## Final Verification Notes

- Markdown inventory after consolidation: 314+ files, excluding `.git`, `.venv`, `.pytest_cache`, and `__pycache__`; the count can grow while concurrent benchmark jobs write generated Markdown under `docs/dev/benchmark-artifacts/`.
- Local relative Markdown link scan: `broken=0` in the final observed Markdown set; the checked count can grow while benchmark artifact generation is active.
- Top-level `docs 2/` directory removal check: passed.
- `docs/dev/README.md` coverage check: all direct child Markdown files except the README itself are linked; generated benchmark artifacts are covered by directory.
- `docs/superpowers/plans/README.md` coverage check: all direct child plan files except the README itself are linked.
- Documentation-scope whitespace check passed with `git diff --check -- .gitignore docs README.md CLAUDE.md 'docs 2'`.
- Full-worktree `git diff --check` passed in the final verification run.
