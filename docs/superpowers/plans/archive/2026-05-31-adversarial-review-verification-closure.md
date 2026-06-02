# Adversarial Review Verification Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining factual verification gap from `docs/dev/2026-05-31-codex-plugin-adversarial-review-report.md` by making the review fixes repeatably checkable even when the local Python 3.13 pytest runner stalls before collection.

**Architecture:** The three code fixes from the review are already present in the working tree, so this plan does not rewrite them. It adds a small stdlib-only verification utility that validates the exact source properties from the report, runs bounded Python-loader diagnostics, and invokes the Android AOT JNI syntax check when the NDK is present. A stdlib `unittest` file proves the verifier catches missing source guards without depending on pytest, NumPy, or SciPy.

**Tech Stack:** Python stdlib (`ast`, `argparse`, `subprocess`, `unittest`), existing Spektrafilm source/tests, Android NDK `clang++`, Markdown docs.

---

## Relevant Current-State Facts

- Current review report: `docs/dev/2026-05-31-codex-plugin-adversarial-review-report.md`.
- Already-modified source files from the report:
  - `src/spektrafilm/runtime/pipeline.py`
  - `src/spektrafilm/model/grain.py`
  - `android/app/src/main/cpp/spektrafilm_android_jni.cpp`
- Already-added pytest regression files:
  - `tests/test_pipeline_lut_lifecycle.py`
  - `tests/test_grain.py`
  - `tests/test_halide_android.py`
- Current unresolved blocker: `.venv/bin/python -m pytest ...` stalls before collection while Homebrew Python 3.13 loads dynamic extension modules. This makes pytest unavailable as a completion signal in this local runtime, but it does not prove the reviewed fixes are wrong.

## Task 1: Add A Bounded Verifier

**Files:**
- Create: `scripts/verify_codex_adversarial_review_fixes.py`

- [x] **Step 1: Write the verifier skeleton**

Create a stdlib-only command with these checks:

```python
def main(argv: list[str] | None = None) -> int:
    repo = Path(__file__).resolve().parents[1]
    failures: list[str] = []
    failures.extend(check_pipeline_backend_key(repo))
    failures.extend(check_grain_local_rng(repo))
    failures.extend(check_android_jni_guards(repo))
    failures.extend(run_python_loader_probe(repo, timeout_seconds=args.python_timeout))
    failures.extend(run_android_syntax_check(repo, timeout_seconds=args.android_timeout))
    return 1 if failures else 0
```

The script must default to bounded diagnostics only: every subprocess uses `timeout=` so a broken Python loader cannot hang the agent session.

- [x] **Step 2: Implement exact source checks**

The verifier must reject these regressions:

```text
pipeline.py lacks _backend_cache_key or does not compare previous LUT backend to current backend
grain.py seeds global NumPy outside the fast_stats/global-RNG branch or lacks random_state routing
spektrafilm_android_jni.cpp lacks short JSON guards, bounded token copy, profile offset bounds, or paramsJson null guards
```

- [x] **Step 3: Implement bounded environment checks**

The verifier should:

```text
Run .venv/bin/python -S -c "import _opcode; print('opcode import ok')" with a short timeout.
If it times out, emit PYTHON_LOADER_BLOCKED with the command and timeout.
Run Android NDK clang++ syntax check for spektrafilm_android_jni.cpp when the NDK clang exists.
If NDK clang is absent, emit ANDROID_CLANG_SKIPPED but do not fail the source verifier.
```

## Task 2: Add Stdlib Tests For The Verifier

**Files:**
- Create: `tests/test_codex_adversarial_review_verifier.py`

- [x] **Step 1: Write failing unittest cases before implementing verifier internals**

The test file must be runnable without pytest:

```bash
/usr/bin/python3 tests/test_codex_adversarial_review_verifier.py
```

It should create temporary source trees and verify:

```python
class VerifierSourceChecksTest(unittest.TestCase):
    def test_pipeline_check_rejects_missing_backend_comparison(self): ...
    def test_grain_check_rejects_global_seed_without_local_rng(self): ...
    def test_android_check_rejects_missing_short_json_guard(self): ...
```

Expected before implementation: imports or assertions fail because the verifier does not exist yet.

- [x] **Step 2: Run the unittest red check**

Run:

```bash
/usr/bin/python3 tests/test_codex_adversarial_review_verifier.py
```

Expected: fail because `scripts.verify_codex_adversarial_review_fixes` is missing or incomplete.

Actual: failed with `ModuleNotFoundError: No module named 'scripts.verify_codex_adversarial_review_fixes'`.

- [x] **Step 3: Implement verifier internals**

Implement the verifier so all source-check tests pass against temporary fixtures and the real repo.

- [x] **Step 4: Run the unittest green check**

Run:

```bash
/usr/bin/python3 tests/test_codex_adversarial_review_verifier.py
```

Expected: `OK`.

Actual: `Ran 3 tests in 0.004s` / `OK`.

## Task 3: Run The New Verifier Against The Real Workspace

**Files:**
- Execute: `scripts/verify_codex_adversarial_review_fixes.py`

- [x] **Step 1: Run source-only verification**

Run:

```bash
/usr/bin/python3 scripts/verify_codex_adversarial_review_fixes.py --skip-python-probe
```

Expected: source checks pass, Android syntax check passes or is explicitly skipped with a reason.

Actual: source checks passed and Android NDK AOT JNI syntax passed.

- [x] **Step 2: Run bounded loader diagnostics**

Run:

```bash
/usr/bin/python3 scripts/verify_codex_adversarial_review_fixes.py --python-timeout 5
```

Expected: either full pass if `.venv` Python loader recovers, or a bounded `PYTHON_LOADER_BLOCKED` diagnostic without hanging.

Actual: `_opcode` loader probe passed, source checks passed, and Android syntax passed.

## Task 4: Update The Review Report

**Files:**
- Modify: `docs/dev/2026-05-31-codex-plugin-adversarial-review-report.md`

- [x] **Step 1: Add the durable verifier command**

Document:

```bash
/usr/bin/python3 scripts/verify_codex_adversarial_review_fixes.py --python-timeout 5
/usr/bin/python3 tests/test_codex_adversarial_review_verifier.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q tests/test_codex_adversarial_review_verifier.py
```

- [x] **Step 2: Clarify the confidence statement**

State exactly what is now factually closed:

```text
The reviewed source invariants and Android AOT syntax are repeatably verified by a stdlib verifier.
The local pytest runner remains an environment blocker until Python 3.13 dynamic extension loading is fixed.
```

## Task 5: Final Verification Loop

**Commands:**

```bash
/usr/bin/python3 tests/test_codex_adversarial_review_verifier.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q tests/test_codex_adversarial_review_verifier.py
/usr/bin/python3 scripts/verify_codex_adversarial_review_fixes.py --python-timeout 5
/usr/bin/python3 -m py_compile scripts/verify_codex_adversarial_review_fixes.py tests/test_codex_adversarial_review_verifier.py
git diff --check
```

- [x] **Step 1: Run all final commands**

Expected: every command exits 0.

- [x] **Step 2: Re-open assumptions**

Ask:

```text
Do I have factual confidence that the review fixes are implemented and repeatably checked?
Do any accepted review findings remain without a source-level or syntax-level guard?
Is any remaining gap clearly classified as environment-only rather than code behavior?
```

If any answer is no, update the verifier or report and rerun Task 5.
