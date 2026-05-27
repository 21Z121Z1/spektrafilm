# Halide Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a strict optional Halide backend to Spektrafilm, wire it into backend selection and GUI/runtime options, and migrate the first high-value LUT kernel to real Halide JIT while preserving CPU/NumPy parity and existing default behavior.

**Architecture:** Keep the current `ArrayBackend` contract as the integration layer and add `HalideBackend` as an explicit backend, not as an automatic default. General eager array operations use NumPy-backed fallback because Halide is a staged DSL, while selected kernels call cached Halide JIT pipelines through backend helper methods. This avoids pretending that every eager NumPy-like operation is fused, and gives the project a verified path for future AOT/full-pipeline migration.

**Tech Stack:** Python 3.13, optional `halide>=21,<22`, NumPy, pytest, current `spektrafilm.gpu` backend abstractions.

---

## Evidence Used

- Local docs: `docs/dev/research-halide-port.md`, `docs/dev/halide-android-port-plan.md`, `docs 2/dev/research-halide-port.md`.
- Local code: `src/spektrafilm/gpu/backend.py`, `src/spektrafilm/gpu/kernels/lut.py`, `src/spektrafilm/runtime/pipeline.py`, `src/spektrafilm/runtime/services/spectral_lut_compute.py`, `src/spektrafilm_gui/options.py`, `README.md`.
- Official Halide docs checked on 2026-05-27:
  - Python bindings support `Func`, `Buffer`, `realize`, and the Python buffer protocol.
  - CMake docs support both JIT and AOT through `add_halide_library` and Python extension helpers.
  - GPU lesson shows explicit target detection and per-`Func` GPU scheduling; it does not justify silently using a GPU target in `auto`.
  - Autoscheduler docs say estimates are required and current autoscheduling is CPU-oriented; this should be future work, not hidden in this patch.

## Design Decision

1. Add `compute_backend="halide"` as an explicit strict backend.
2. Add optional package extra `halide = ["halide>=21,<22"]`.
3. Do not include Halide in `auto` yet. JIT startup cost and dependency size should remain user opt-in.
4. Implement real Halide execution first for 3D trilinear LUT sampling because `SpectralLUTService` already routes GPU-capable backends to `gpu_trilinear`, and the NumPy/CuPy/MLX reference implementations are compact and well tested.
5. Keep unsupported operations deterministic by delegating eager array ops to NumPy in `HalideBackend`, with `supports_gpu=True` so existing LUT dispatch can select the Halide kernel. The backend summary and docs must make clear that this is an explicit Halide JIT pilot backend, not full pipeline fusion.

## Task 1: Backend Selection Contract

**Files:**
- Modify: `src/spektrafilm/gpu/backend.py`
- Create: `src/spektrafilm/gpu/halide_backend.py`
- Modify: `tests/test_gpu_backend.py`

- [ ] **Step 1: Write failing tests**

```python
def test_select_backend_accepts_halide_name_when_available() -> None:
    try:
        backend = select_backend("halide")
    except BackendUnavailableError:
        return

    assert backend.name == "halide"
    assert backend.supports_gpu
    assert backend_summary(backend, runtime_gpu_enabled=True) == "halide"


def test_select_backend_rejects_unknown_backend_name() -> None:
    with pytest.raises(ValueError, match="halide"):
        select_backend("vulkan")
```

- [ ] **Step 2: Verify red**

Run:

```bash
.venv/bin/python -m pytest tests/test_gpu_backend.py::test_select_backend_rejects_unknown_backend_name tests/test_gpu_backend.py::test_select_backend_accepts_halide_name_when_available -q
```

Expected: the new Halide test fails because `"halide"` is not an accepted backend.

- [ ] **Step 3: Implement minimal selection**

Add `HalideBackend`, import it lazily from `_select_halide_backend()`, and extend `_normalize_backend_name()` to accept `"halide"`.

- [ ] **Step 4: Verify green**

Run the same targeted command and expect both selected tests to pass or the Halide-specific test to return early with `BackendUnavailableError` when the optional package is absent.

## Task 2: HalideBackend Eager API

**Files:**
- Modify: `src/spektrafilm/gpu/halide_backend.py`
- Modify: `tests/test_gpu_backend.py`

- [ ] **Step 1: Write failing operation tests**

```python
def test_halide_backend_exposes_required_array_ops() -> None:
    try:
        backend = select_backend("halide")
    except BackendUnavailableError:
        pytest.skip("halide optional dependency is unavailable")

    values = np.array([-4.0, -1.0, 0.0, 2.0, 9.0], dtype=np.float32)
    np.testing.assert_allclose(backend.abs(values), np.abs(values))
    np.testing.assert_allclose(backend.pow(np.abs(values), 0.5), np.sqrt(np.abs(values)), atol=1e-6)
    np.testing.assert_allclose(backend.power(10.0, values), np.power(10.0, values), atol=1e-6)
```

- [ ] **Step 2: Verify red**

Run:

```bash
.venv/bin/python -m pytest tests/test_gpu_backend.py::test_halide_backend_exposes_required_array_ops -q
```

Expected: failure until `HalideBackend` implements the protocol.

- [ ] **Step 3: Implement fallback eager methods**

Use NumPy for eager ArrayBackend methods. Keep `requires_serial_runtime=False`, `supports_gpu=True`, `fallback_reason=None`, `to_numpy()` as `np.asarray`, and validate `precision` is `"float32"` only because the first Halide JIT kernels are float32.

- [ ] **Step 4: Verify green**

Run the same targeted command.

## Task 3: Halide 3D Trilinear LUT Kernel

**Files:**
- Modify: `src/spektrafilm/gpu/halide_backend.py`
- Modify: `src/spektrafilm/gpu/kernels/lut.py`
- Modify: `tests/test_gpu_lut.py`

- [ ] **Step 1: Write failing parity test**

```python
def test_trilinear_3d_lut_halide_matches_numpy_reference_when_available() -> None:
    try:
        backend = select_backend("halide")
    except BackendUnavailableError as exc:
        pytest.skip(str(exc))

    lut = _make_3d_lut(7).astype(np.float32)
    image = np.array(
        [
            [[0.0, 0.1, 0.2], [0.3, 0.4, 0.5]],
            [[0.6, 0.7, 0.8], [1.0, 0.25, 0.75]],
        ],
        dtype=np.float32,
    )

    actual = apply_lut_trilinear_3d_backend(lut, image, backend)
    expected = apply_lut_trilinear_3d_numpy(lut, image)
    np.testing.assert_allclose(backend.to_numpy(actual), expected, rtol=2e-6, atol=2e-6)
```

- [ ] **Step 2: Verify red**

Run:

```bash
.venv/bin/python -m pytest tests/test_gpu_lut.py::test_trilinear_3d_lut_halide_matches_numpy_reference_when_available -q
```

Expected: failure because dispatch currently falls back through NumPy rather than a Halide helper, or because `HalideBackend` lacks the method.

- [ ] **Step 3: Implement cached Halide JIT**

In `HalideBackend.apply_lut_trilinear_3d()`, build a `hl.Func` that:

- accepts `lut` as `hl.ImageParam(hl.Float(32), 4)` with dimensions `(r, g, b, c)`;
- accepts `image` as `hl.ImageParam(hl.Float(32), 3)` with dimensions `(x, y, c)` after transposing Spektrafilm arrays from HWC to WHC;
- clamps coordinates to `[0, size - 1]`;
- computes `idx0`, `idx1`, `frac`, eight corner samples, and linear blends in the same order as `apply_lut_trilinear_3d_numpy()`;
- realizes into `(width, height, 3)` and transposes back to HWC;
- caches the compiled `Func` by LUT size, width, height, and channel count.

- [ ] **Step 4: Wire dispatch**

Update `apply_lut_trilinear_3d_backend()` to call `backend.apply_lut_trilinear_3d()` when present before the generic fallback branch.

- [ ] **Step 5: Verify green**

Run:

```bash
.venv/bin/python -m pytest tests/test_gpu_lut.py::test_trilinear_3d_lut_halide_matches_numpy_reference_when_available tests/test_gpu_lut.py::test_compute_with_lut_gpu_trilinear_without_gpu_falls_back_to_cpu_lut -q
```

Expected: Halide parity passes when installed; CPU fallback remains unchanged.

## Task 4: Runtime and GUI Option Wiring

**Files:**
- Modify: `src/spektrafilm_gui/options.py`
- Modify: `src/spektrafilm_gui/widget_specs.py`
- Modify: `src/spektrafilm/runtime/pipeline.py`
- Modify: relevant tests if existing expectations enumerate backend values.

- [ ] **Step 1: Write/update failing tests**

Update backend selection expectations to include `"halide"` where the enum is user-facing. Add a runtime precision test if needed:

```python
with pytest.raises(ValueError, match="float64 runtime precision"):
    params.settings.compute_backend = "halide"
    params.settings.float_precision = "float64"
    SimulationPipeline(params)
```

- [ ] **Step 2: Verify red**

Run affected targeted tests.

- [ ] **Step 3: Implement wiring**

Add `halide = "halide"` to `ComputeBackends`, update widget tooltip, and treat explicit `"halide"` like other non-float64 accelerator backends in `SimulationPipeline._reinitialize()`.

- [ ] **Step 4: Verify green**

Run affected targeted tests.

## Task 5: Dependency and Documentation

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock` if `uv lock` can refresh it without unrelated churn.
- Modify: `README.md`
- Create or modify: `docs/dev/halide-backend-implementation.md`

- [ ] **Step 1: Dependency tests**

Add the optional extra:

```toml
halide = ["halide>=21,<22"]
```

Run:

```bash
uv lock
```

Expected: lock succeeds and includes Halide metadata.

- [ ] **Step 2: Documentation**

Document:

- `compute_backend="halide"` is explicit opt-in.
- Install with `spektrafilm[halide]`.
- First shipped Halide kernel is 3D trilinear LUT JIT.
- Full pipeline fusion/AOT Android remains future work.
- Precision contract remains float32 `np.allclose(..., atol=1e-6)` or tighter.

## Task 6: Verification and Self-Audit Loop

**Files:**
- No new files unless documentation needs correction.

- [ ] **Step 1: Targeted Halide tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_gpu_backend.py tests/test_gpu_lut.py -q
```

- [ ] **Step 2: Runtime/LUT integration smoke**

Run:

```bash
.venv/bin/python -m pytest tests/test_pipeline_lut_lifecycle.py tests/test_runtime_api.py -q
```

- [ ] **Step 3: Full non-GUI suite**

Run:

```bash
.venv/bin/python -m pytest --ignore=tests/gui -q
```

- [ ] **Step 4: Static sanity**

Run:

```bash
.venv/bin/python -m compileall src/spektrafilm tests
git diff --check
```

- [ ] **Step 5: 100% confidence audit**

Ask:

- Did a real Halide code path execute in tests, not just a fallback?
- Does missing Halide fail strictly for explicit `halide` without breaking `auto`?
- Are dtype and HWC/WHC layout conversions documented and tested?
- Does the implementation avoid claiming full-pipeline fusion?
- Did docs reflect the exact shipped scope and future limits?

If any answer is no, add a focused failing test or documentation correction, implement the fix, and repeat targeted plus full verification.
