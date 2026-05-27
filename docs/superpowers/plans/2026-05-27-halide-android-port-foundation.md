# Halide Android Port Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a verified Halide/Android port foundation to Spektrafilm without pretending the full multi-month Android rewrite is complete.

**Architecture:** Keep the existing Python `ArrayBackend` runtime intact and add Halide as an optional, strict backend. The first shipped kernel is a float32 `rgb_to_xyz`/3x3 matrix path implemented through Halide JIT on host, plus Android AOT target metadata that documents and validates the CMake target strings needed by the future native port.

**Tech Stack:** Python 3.13, NumPy, optional `halide>=21,<22`, pytest, existing Spektrafilm GPU backend protocol, Halide AOT target triples for Android.

---

## Evidence And Scope

The source documents describe a full C++/Halide/Android rewrite that is explicitly phased over several months. Fresh official-source checks confirm these points:

- Halide supports C++17, Python bindings, CPU targets including ARM, Android/iOS operating targets, and GPU backends including CUDA, Metal, OpenCL, DirectX 12, and Vulkan.
- Halide CMake AOT integration is centered on `add_halide_generator` and `add_halide_library`, with Android target triples using `arch-bits-os` such as `arm-64-android`.
- Halide cross-compilation is first-class through `Target::Android`/`Target::ARM` and `compile_to_file`.
- Autoscheduler use requires realistic input/output estimates; CMake can pass autoscheduler targets such as `Halide::Adams2019`.
- Android Vulkan support is still documented as work in progress, so the Android foundation must default to CPU AOT first and treat Vulkan as a later experimental target.

Therefore the correct one-turn implementation is a validated foundation:

- Optional `halide` backend selection.
- Strict dependency failure when users request Halide without installing it.
- First Halide-backed float32 kernel: HWC image multiplied by a 3x3 matrix, matching the existing NumPy/colour-science reference within `1e-6`.
- Android ABI to Halide target metadata and CMake snippet rendering, so future native work has a tested contract instead of prose-only target strings.
- Documentation update clarifying what is now implemented and what remains a future native rewrite.

## Files

- Create: `src/spektrafilm/gpu/halide_backend.py`
  - Optional Halide import, strict dependency errors, host JIT 3x3 matrix kernel, NumPy fallback for unsupported array operations.
- Create: `src/spektrafilm/halide/__init__.py`
  - Public exports for availability and Android target helpers.
- Create: `src/spektrafilm/halide/availability.py`
  - `probe_halide()` and `HalideAvailability` for deterministic capability checks.
- Create: `src/spektrafilm/halide/android.py`
  - Android ABI target mapping and safe CMake `add_halide_library` snippet renderer.
- Modify: `src/spektrafilm/gpu/backend.py`
  - Accept `compute_backend='halide'`, select strict optional backend, include Halide in float64 rejection semantics.
- Modify: `src/spektrafilm/gpu/kernels/color.py`
  - Allow backends with a specialized `rgb_to_xyz`/matrix method to handle the color matrix kernel.
- Modify: `src/spektrafilm/runtime/pipeline.py`
  - Reject `compute_backend='halide'` for float64 runtime precision.
- Modify: `src/spektrafilm_gui/options.py`
  - Expose `halide` in compute backend options.
- Modify: `src/spektrafilm_gui/widget_specs.py`
  - Explain that Halide is optional and currently a verified host/AOT foundation.
- Modify: `pyproject.toml`
  - Add optional dependency group `halide = ["halide>=21,<22"]`.
- Create: `tests/test_halide_backend.py`
  - Strict unavailable dependency test and optional live Halide parity test.
- Create: `tests/test_halide_android.py`
  - Android ABI mapping and CMake snippet validation tests.
- Modify: `tests/test_gpu_backend.py`
  - Include Halide in accepted backend names and unknown-name error expectation.
- Modify: `tests/test_runtime_api.py`
  - Include Halide in float64 explicit-backend rejection.
- Modify: `docs/dev/halide-android-port-plan.md`
  - Add an implementation status section and correct Vulkan/Android maturity wording.
- Modify: `docs/dev/research-halide-port.md`
  - Add a 2026-05-27 implementation note for the foundation now present in this repo.

## Tasks

### Task 1: Add failing tests for the new Halide backend contract

- [ ] Add tests proving `select_backend("halide")` is accepted by normalization and is strict when the optional dependency is missing.
- [ ] Add an optional live test that imports Halide and checks the Halide matrix kernel against `np.matmul(rgb, matrix.T)` with float32 tolerance `1e-6`.
- [ ] Add a runtime test that `float_precision='float64'` rejects explicit `compute_backend='halide'`.
- [ ] Run:

```bash
.venv/bin/python -m pytest tests/test_gpu_backend.py tests/test_halide_backend.py tests/test_runtime_api.py::TestRuntimeApi::test_float64_runtime_precision_rejects_explicit_gpu_backend -q
```

Expected before implementation: failures for unknown backend `halide`, missing modules, or missing rejection.

### Task 2: Add failing tests for Android AOT metadata

- [ ] Add tests for ABI mappings: `arm64-v8a -> arm-64-android`, `armeabi-v7a -> arm-32-android`, `x86_64 -> x86-64-android`, `x86 -> x86-32-android`.
- [ ] Add tests that unsafe CMake target/generator names are rejected.
- [ ] Add tests that rendered CMake contains `add_halide_library`, `FROM`, `GENERATOR`, `TARGETS`, and `AUTOSCHEDULER`.
- [ ] Run:

```bash
.venv/bin/python -m pytest tests/test_halide_android.py -q
```

Expected before implementation: import failure for `spektrafilm.halide.android`.

### Task 3: Implement the optional Halide backend and Android helpers

- [ ] Implement `HalideBackend` with:
  - `name = "halide"`.
  - `supports_gpu = True` so existing backend-dispatch code can route verified Halide kernels.
  - `requires_serial_runtime = True` as a conservative guard while host-JIT kernels are compiled and cached lazily.
  - strict `BackendUnavailableError` if `halide` cannot be imported.
  - strict rejection for non-float32 precision.
  - `matmul()` specialization for HWC float32 image arrays multiplied by a 3x3 matrix.
  - NumPy fallbacks for protocol operations not yet ported to Halide.
- [ ] Implement `spektrafilm.halide.availability`.
- [ ] Implement `spektrafilm.halide.android`.
- [ ] Wire `select_backend("halide")`, GUI option, runtime float64 guard, and optional dependency metadata.
- [ ] Re-run Task 1 and Task 2 tests until green.

### Task 4: Validate the live Halide path

- [ ] Install the optional dependency into the local virtualenv if it is missing:

```bash
.venv/bin/python -m pip install 'halide>=21,<22'
```

- [ ] Run the live parity test:

```bash
.venv/bin/python -m pytest tests/test_halide_backend.py::test_halide_backend_rgb_to_xyz_matches_numpy_reference_when_available -q
```

Expected after implementation and dependency install: pass. If the wheel is unavailable for the local Python/platform, the test may skip in CI but the strict unavailable-dependency test must still pass.

### Task 5: Update documentation

- [ ] Update `docs/dev/halide-android-port-plan.md` with the actual implemented foundation, Android CPU AOT default, and Vulkan caution.
- [ ] Update `docs/dev/research-halide-port.md` with the current repo status and a short usage note for `compute_backend='halide'`.
- [ ] Do not modify the `docs 2/` copies because `CLAUDE.md` limits edits to `docs/`, `src/`, `tests/`, `README.md`, and `pyproject.toml`.

### Task 6: Final verification and confidence loop

- [ ] Run targeted tests:

```bash
.venv/bin/python -m pytest tests/test_gpu_backend.py tests/test_halide_backend.py tests/test_halide_android.py tests/test_gpu_color_chain.py tests/test_runtime_api.py::TestRuntimeApi::test_float64_runtime_precision_rejects_explicit_gpu_backend -q
```

- [ ] Run import/compile sanity:

```bash
.venv/bin/python -m compileall src/spektrafilm/gpu src/spektrafilm/halide src/spektrafilm_gui -q
```

- [ ] Run repository whitespace check:

```bash
git diff --check
```

- [ ] Self-audit:
  - Does any new path silently fall back when the user explicitly requested Halide? It must not.
  - Does any float64 runtime path use a float32 Halide kernel? It must not.
  - Does documentation overclaim full Android app completion? It must not.
  - Does Android metadata imply Vulkan is ready on Android? It must not.
  - Does the live Halide parity test demonstrate numerical equivalence when the dependency is present? It must.
