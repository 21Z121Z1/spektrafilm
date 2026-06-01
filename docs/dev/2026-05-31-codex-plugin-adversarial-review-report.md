# 2026-05-31 Codex Plugin-Style Adversarial Review Report

## Upstream `/codex:adversarial-review` Mechanics

Source reviewed: `openai/codex-plugin-cc` main at `807e03a`.

- Command entrypoint: `plugins/codex/commands/adversarial-review.md`.
- Runtime construction: `plugins/codex/scripts/codex-companion.mjs`.
- Diff/context collector: `plugins/codex/scripts/lib/git.mjs`.
- Review prompt: `plugins/codex/prompts/adversarial-review.md`.
- Structured output schema: `plugins/codex/schemas/review-output.schema.json`.

The command is a read-only review runner over the current working tree or branch diff. It preserves raw user focus text, rejects narrow staged/unstaged-only scope flags, chooses wait/background mode from diff size, gathers changed files and stats, then runs a skeptical reviewer prompt with a JSON schema. The prompt asks for material, ship-blocking findings only, with file/line grounding, confidence, and recommendations.

This repository pass adapted that behavior manually: review current dirty workspace context, prioritize material regressions over style, turn accepted findings into regression tests, then patch only the affected files.

## Workspace Context

- Working directory: `/Users/retriedstormtrooper/Documents/spektrafilm-main`.
- Branch: `develop`.
- Starting state was already dirty and included many staged renames plus broad unstaged edits. This report only describes the fixes from this run and does not treat pre-existing worktree changes as mine.
- Existing adversarial-review docs from 2026-05-28 through 2026-05-31 were treated as snapshots, not as proof that current source was safe.

## Findings And Fixes

### 1. Backend changes reused stale LUT service

Severity: medium.

`SimulationPipeline.update()` rebuilt `SpectralLUTService` only when `lut_resolution` changed. If the GUI/runtime changed `compute_backend` or `gpu_precision` while keeping the same LUT resolution, existing LUT caches and `_lut_service._backend` stayed bound to the old backend.

Fix:

- Added `_backend_cache_key()` in `src/spektrafilm/runtime/pipeline.py`.
- Reuse the LUT service only when both LUT resolution and backend identity match.
- Added `test_pipeline_update_rebuilds_lut_service_when_backend_changes()`.

### 2. Seeded CPU grain path touched global NumPy RNG

Severity: medium.

`layer_particle_model(..., seed=..., use_fast_stats=False)` saved/restored global NumPy RNG state but still called `np.random.seed(seed)`. That is unsafe for concurrent GUI/runtime workers because another thread can sample while the global state is temporarily replaced.

Fix:

- For SciPy CPU paths, use a local `np.random.RandomState(seed)` and pass it as `random_state`.
- Retain global save/restore only for the fast numba stats path, where existing samplers are global-RNG based.
- Added `test_layer_particle_model_generator_path_uses_local_rng_for_seed()`.

### 3. Android AOT JNI accepted malformed boundary inputs

Severity: medium.

The AOT-only JNI path had three native-boundary hazards:

- JSON helper loops used `len - klen` with unsigned `size_t`, so short JSON payloads could underflow.
- Float extraction temporarily wrote a NUL byte at `p`, including the `p == end` case.
- `load_profile_bytes()` trusted the profile data offset before subtracting it from total length.
- `nativeProcessImage()` did not reject null `paramsJson` before JNI array access.

Fix:

- Guard null keys/payloads and `len < klen`.
- Iterate as `i + klen <= len`.
- Copy JSON float tokens into a bounded local buffer before `atof`.
- Reject profile offsets below the 16-byte header or beyond total payload length.
- Guard null JNI byte-array pins for profile, LUT, and JSON arrays.
- Added source-level Android JNI regression checks in `tests/test_halide_android.py`.

## Rejected Or Deferred Candidates

- Existing HDR profile/export routing was not changed in this pass. Current docs and source already emphasize explicit HDR routing and preserving SDR behavior.
- Android diagnostic fallback behavior in Kotlin was not changed; it matches the current native-preflight/diagnostic contract.
- Full formal multi-agent deep security scan was not run because this session has no explicit sub-agent request and the local review already found bounded, actionable fixes.

## Verification Evidence

Passed:

```bash
python3 -m py_compile src/spektrafilm/runtime/pipeline.py src/spektrafilm/model/grain.py tests/test_pipeline_lut_lifecycle.py tests/test_grain.py tests/test_halide_android.py
```

```bash
python3 - <<'PY'
from pathlib import Path
root = Path('.')
checks = {
    'pipeline backend key': ('src/spektrafilm/runtime/pipeline.py', ['def _backend_cache_key', 'previous_lut_backend', '_backend_cache_key(previous_lut_backend) != _backend_cache_key(self._backend)']),
    'grain local rng': ('src/spektrafilm/model/grain.py', ["uses_global_rng = seed is not None and method == 'poisson_binomial' and use_fast_stats", 'np.random.RandomState(seed)', 'random_state']),
    'android json guard': ('android/app/src/main/cpp/spektrafilm_android_jni.cpp', ['if (json == nullptr || key == nullptr) return def;', 'if (klen == 0 || len < klen) return def;', 'for (size_t i = 0; i + klen <= len; i++)', 'char token[64];']),
    'android profile guard': ('android/app/src/main/cpp/spektrafilm_android_jni.cpp', ['offset < 16', 'static_cast<size_t>(offset) > total_len']),
    'android params guard': ('android/app/src/main/cpp/spektrafilm_android_jni.cpp', ['if (paramsJson == nullptr) return kInvalidCount;', 'if (json_bytes == nullptr) return kNullBuffer;']),
}
for name, (path, needles) in checks.items():
    text = (root / path).read_text()
    missing = [needle for needle in needles if needle not in text]
    if missing:
        raise SystemExit(f'{name} missing {missing}')
    print(f'{name}: ok')
PY
```

```bash
$HOME/Library/Android/sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/darwin-x86_64/bin/clang++ --target=aarch64-linux-android35 -std=c++17 -fsyntax-only -DSPEKTRAFILM_HAS_HALIDE_AOT -Iandroid/app/src/main/cpp -I/Library/Java/JavaVirtualMachines/jdk-21.jdk/Contents/Home/include -I/Library/Java/JavaVirtualMachines/jdk-21.jdk/Contents/Home/include/darwin android/app/src/main/cpp/spektrafilm_android_jni.cpp
```

```bash
git diff --check
```

```bash
/usr/bin/python3 tests/test_codex_adversarial_review_verifier.py
```

Result: `Ran 3 tests in 0.004s` / `OK`.

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q tests/test_codex_adversarial_review_verifier.py
```

Result: `3 passed in 0.02s`.

```bash
/usr/bin/python3 scripts/verify_codex_adversarial_review_fixes.py --python-timeout 5
```

Result:

```text
PIPELINE_SOURCE_OK
GRAIN_SOURCE_OK
ANDROID_JNI_SOURCE_OK
PYTHON_LOADER_OK: opcode import ok
ANDROID_CLANG_OK: AOT JNI syntax check passed
VERIFY_OK
```

```bash
/usr/bin/python3 -m py_compile scripts/verify_codex_adversarial_review_fixes.py tests/test_codex_adversarial_review_verifier.py
```

Result: exit `0`.

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q tests/test_halide_android.py::test_android_jni_json_helpers_guard_short_payloads tests/test_halide_android.py::test_android_jni_profile_loader_rejects_out_of_bounds_offset tests/test_halide_android.py::test_android_jni_process_image_rejects_null_params_json
```

Result: `3 passed in 0.03s`.

Blocked:

- Combined targeted pytest for the grain and pipeline regression tests still did not complete in this local runtime. With `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, `tests/test_grain.py::TestApplyGrain::test_layer_particle_model_generator_path_uses_local_rng_for_seed` and `tests/test_pipeline_lut_lifecycle.py::test_pipeline_update_rebuilds_lut_service_when_backend_changes` remained in pytest collection/import for more than two minutes and were killed. `sample` showed Python executing nested import/pytest collection frames rather than a test assertion failure.
- The earlier `_opcode` dynamic-extension probe now passes through the stdlib verifier, so the remaining blocker is narrower: runtime/pytest import for NumPy/SciPy-heavy Spektrafilm modules, not the stdlib verifier or Android JNI checks.

## Confidence Loop

Self-question: do I have 100% factual confidence?

- For the Android C++ boundary hardening: yes for syntax, pytest source-level checks, and direct source-level hazard closure; the AOT guarded file compiles with the NDK clang syntax check.
- For the pipeline and grain Python fixes: the reviewed source invariants are now repeatably verified by `scripts/verify_codex_adversarial_review_fixes.py`, and the verifier has stdlib plus pytest coverage. This closes the review-report implementation gap at source level.
- Remaining environment action: if the NumPy/SciPy-heavy pytest import path becomes responsive, run the targeted pytest commands below first, then the normal full suite.

Targeted commands to rerun after fixing the Python 3.13 loader:

```bash
uv run --extra dev pytest -q tests/test_pipeline_lut_lifecycle.py::test_pipeline_update_rebuilds_lut_service_when_backend_changes tests/test_grain.py::TestApplyGrain::test_layer_particle_model_generator_path_uses_local_rng_for_seed tests/test_halide_android.py::test_android_jni_json_helpers_guard_short_payloads tests/test_halide_android.py::test_android_jni_profile_loader_rejects_out_of_bounds_offset tests/test_halide_android.py::test_android_jni_process_image_rejects_null_params_json
uv run --extra dev pytest -q
```
