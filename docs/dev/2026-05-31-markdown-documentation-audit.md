# Markdown Documentation Audit - 2026-05-31

## Scope

This audit covers Markdown documentation in `/Users/retriedstormtrooper/Documents/spektrafilm-main`, excluding `.git`, `.venv`, `.pytest_cache`, and `__pycache__`.

The goal was to make the documentation surface navigable without deleting historical evidence or touching concurrent source/test/GPU implementation work.

## Inventory Findings

- Markdown inventory observed during final verification: 314+ files. The exact count can increase while concurrent benchmark jobs write generated Markdown under `docs/dev/benchmark-artifacts/`.
- Main clusters:
  - Root project docs: `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `CLAUDE.md`, `CLAUDE-RESEARCH.md`.
  - Canonical documentation tree: `docs/`.
  - Active development reports: `docs/dev/`.
  - Audit snapshot: `docs/agent_audit/`.
  - Generated curve-analysis corpus: `docs/curve_analysis/`.
  - Agentic implementation plans: `docs/superpowers/plans/`.
  - Runtime data notes: `src/spektrafilm/data/hdr_curve_profiles/README.md` and `src/spektrafilm/data/icc/README.md`.
  - Historical duplicate tree: former top-level `docs 2/`, now archived under `docs/archive/docs-2-legacy-20260531/`.

## Classification Conclusions

1. `docs/README.md` should be the canonical documentation router. The root `README.md` should remain product-facing and only point to the router.
2. `docs/dev/` is a mixed working area. It needs a local index because it contains active coordination docs, current GPU/MLX/Halide reports, Android research, GUI/memory/test work, and older review rounds.
3. `docs/agent_audit/` is a coherent audit snapshot and should have its own index instead of being flattened into the top-level router.
4. `docs/curve_analysis/` is generated corpus documentation. The summary report is the entry point; the 160 per-combination files should not be hand-maintained independently.
5. `docs/superpowers/plans/` contains implementation plans, not proof of completion. It needs an index that warns readers to verify current state.
6. The former `docs 2/` tree was a real tracked duplicate with 26 Markdown files. It should be preserved as archive evidence, not kept as a second documentation root.
7. `.gitignore` used `archive/`, which hid `docs/archive/README.md`. The rule was narrowed to `/archive/` so documentation archives can be tracked.

## Changes Made

- Created a plan-first implementation artifact: `docs/superpowers/plans/2026-05-31-markdown-documentation-consolidation.md`.
- Rewrote `docs/README.md` as the canonical documentation map.
- Added directory indexes:
  - `docs/dev/README.md`
  - `docs/agent_audit/README.md`
  - `docs/curve_analysis/README.md`
  - `docs/superpowers/plans/README.md`
- Added archive documentation:
  - `docs/archive/README.md`
  - `docs/archive/docs-2-legacy-20260531/README.md`
- Moved former `docs 2/dev/*.md` files to `docs/archive/docs-2-legacy-20260531/dev/`.
- Rewrote Markdown references from the old `docs 2/dev/...` path to the archive path where they referred to actual files.
- Added a root `README.md` pointer to `docs/README.md`.
- Updated `CLAUDE.md` so agents start from the documentation map before using older review files.
- Updated `.gitignore` from `archive/` to `/archive/` so `docs/archive/` is visible to git.

## Verification Evidence

- Markdown local relative link scan: `broken=0` in the final observed Markdown set; the checked count can grow while benchmark artifact generation is active.
- Documentation-scope whitespace check passed:

```bash
git diff --check -- .gitignore docs README.md CLAUDE.md 'docs 2'
```

- Full-worktree whitespace check also passed:

```bash
git diff --check
```

- Top-level `docs 2/` removal check passed:

```bash
test ! -e "docs 2"
```

- `docs/dev/README.md` covers all direct Markdown files under `docs/dev/`, and covers generated benchmark artifacts by directory because those files are actively generated.
- `docs/superpowers/plans/README.md` covers all direct plan files under `docs/superpowers/plans/`, except its own README.

## Remaining Boundary

The workspace still contains broad source, test, script, lockfile, and generated artifact changes from concurrent implementation work. This audit only owns the documentation organization changes described above.
