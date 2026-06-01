# SDR Parity Reality Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the stale SDR parity guarantee with verifiable current-state checks, fix the upstream parity script so it catches real shared data drift, and update the documentation so it no longer claims guarantees that the current checkout does not satisfy.

**Architecture:** Keep runtime behavior unchanged. The work is limited to tests, the parity shell check, and docs. The shell check remains the command-line enforcement layer; pytest covers the script behavior with isolated temporary Git repositories; `tests/test_upstream_parity.py` remains the local numerical regression suite.

**Tech Stack:** Bash, Git, pytest, NumPy, project `.venv/bin/python`.

---

## Current Evidence

The current checkout does not satisfy the original `docs/sdr-parity-guarantee.md` text.

- `bash scripts/check-upstream-parity.sh` fails against current `upstream/main`.
- `upstream/main` has advanced 27 commits beyond this branch merge-base.
- Several files listed as byte-identical core files differ in the current working tree: `pipeline.py`, `params_builder.py`, `params_schema.py`, `filming.py`, `printing.py`, `scanning.py`, `spectral_lut_compute.py`, `couplers.py`, and `profiles/io.py`.
- The script currently reports `(no shared data files found in upstream/main)` even though upstream tracks shared data under `src/spektrafilm/data/`.
- The current local numerical suite still passes: `.venv/bin/python -m pytest tests/test_upstream_parity.py -v` reports `13 passed`.
- The document's counts are stale: current local counts are 162 files under `src/spektrafilm/data/hdr_curve_profiles` and 173 ICC/ICM files under `src/spektrafilm/data/icc`.

## External Best-Practice Inputs

- NumPy recommends `numpy.testing.assert_allclose` for array tolerance checks because it checks shapes and compares values with explicit `atol + rtol * abs(desired)` semantics.
- Pytest recommends registering custom markers so marker usage appears in `pytest --markers` and avoids warning-prone surprise behavior.
- Git's own `git diff` documentation distinguishes working-tree, index, commit, and merge-base comparisons; the parity script must state exactly which Git object is being compared.

## Actual Problems To Fix

1. The guarantee document overclaims current upstream parity.
2. The parity report is stale and still says the fork is strictly ahead of upstream at SHA `a227823...`, which is no longer true after fetching current `upstream/main`.
3. The shell script does not hash-check the real upstream data root `src/spektrafilm/data/`, so shared profile/filter/LUT drift can pass silently.
4. The shell script warns instead of failing when a declared core file is missing from upstream, which makes a broken file contract look non-fatal.
5. The docs conflate two different guarantees: local SDR numerical stability and byte/path parity against a moving upstream branch.

## Task 1: Add Failing Tests For The Script Defects

**Files:**
- Create: `tests/test_upstream_parity_script.py`

- [ ] Create a pytest fixture that builds a temporary upstream Git repo with one tracked shared data file at `src/spektrafilm/data/profiles/example.json`.
- [ ] Clone that repo into a working repo, copy `scripts/check-upstream-parity.sh`, modify the shared data file locally, and run the script with `UPSTREAM_REMOTE=origin UPSTREAM_BRANCH=main`.
- [ ] Assert the script exits non-zero and names `src/spektrafilm/data/profiles/example.json` as a failing hash comparison.
- [ ] Create a second temporary repo scenario where the upstream lacks a declared core file path and assert the script exits non-zero rather than warning-only.
- [ ] Run: `.venv/bin/python -m pytest tests/test_upstream_parity_script.py -v`
- [ ] Expected before implementation: at least the shared-data test fails because the current script does not scan `src/spektrafilm/data/`.

## Task 2: Fix `scripts/check-upstream-parity.sh`

**Files:**
- Modify: `scripts/check-upstream-parity.sh`

- [ ] Add `DATA_ROOT_PATTERNS` that include `src/spektrafilm/data/` and keep old roots only as compatibility.
- [ ] Fail missing core paths instead of warning-only when a path is explicitly part of the contract.
- [ ] Keep binary-safe upstream hash computation by piping `git cat-file blob "$UPSTREAM_REF:$path"` into `shasum -a 256`.
- [ ] Print a clear summary with the compared upstream ref, merge-base, and data file count.
- [ ] Preserve `UPSTREAM_REMOTE` and `UPSTREAM_BRANCH` overrides.
- [ ] Run: `.venv/bin/python -m pytest tests/test_upstream_parity_script.py -v`
- [ ] Expected after implementation: new script tests pass.

## Task 3: Correct The SDR Parity Documentation

**Files:**
- Modify: `docs/sdr-parity-guarantee.md`
- Modify: `docs/upstream-parity-report.md`

- [ ] Rewrite the guarantee as a current-state contract, not a false assertion that all core files are currently identical.
- [ ] Separate "byte/path parity against upstream" from "local numerical SDR regression stability".
- [ ] Record the current failed `scripts/check-upstream-parity.sh` evidence and the passing local `tests/test_upstream_parity.py` evidence.
- [ ] Correct the real data root to `src/spektrafilm/data/`.
- [ ] Correct current local counts for HDR curve profile files and ICC/ICM files.
- [ ] Explain that current upstream parity is broken until upstream divergence and core file diffs are intentionally reconciled or accepted by a new documented baseline.

## Task 4: Verification Loop

**Files:**
- Read-only unless failures require targeted test/docs fixes.

- [ ] Run: `.venv/bin/python -m pytest tests/test_upstream_parity_script.py tests/test_upstream_parity.py -v`
- [ ] Run: `bash scripts/check-upstream-parity.sh`
- [ ] Run: `.venv/bin/python -m pytest --ignore=tests/gui -q`
- [ ] Run: `.venv/bin/python -m compileall src tests scripts`
- [ ] Run: `git diff --check`
- [ ] Self-review: ask whether the implementation can falsely claim 100% parity. If yes, revise docs or checks until the remaining failed state is explicit and cannot be mistaken for success.

## Non-Goals

- Do not revert or rewrite existing runtime, model, GPU, or GUI changes.
- Do not merge current `upstream/main` into this dirty working tree.
- Do not make `scripts/check-upstream-parity.sh` pass by weakening the upstream parity standard.
- Do not claim full SDR upstream parity while current upstream divergence and core-file diffs remain unresolved.
