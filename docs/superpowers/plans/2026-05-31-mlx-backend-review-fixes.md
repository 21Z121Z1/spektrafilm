# MLX Backend Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the MLX compute backend strict about real numerical safety, avoid confirmed CPU round-trips in the active GPU path, and document the actual acceleration and float32 precision envelope.

**Architecture:** Keep CPU behavior unchanged. Treat explicit GPU requests as strict, but let `compute_backend="auto"` fall back to CPU when the requested precision is CPU-only. Preserve MLX arrays across stage boundaries until the final pipeline materialization.

**Tech Stack:** Python 3.13, NumPy, MLX, pytest, Spektrafilm runtime stages and GPU kernel wrappers.

---

## Review Findings Driving This Plan

1. `select_backend("auto", precision="float64")` currently raises `ValueError` from `MlxBackend`, even though the GUI exposes `float64` as CPU-exact precision. `auto + float64` should select CPU with a fallback reason. Explicit `compute_backend="mlx"` with `float64` should remain a clear error because MLX/Metal evaluation rejects GPU float64.
2. `FilmingStage._rgb_to_film_raw()` runs the 2D MLX LUT and then immediately calls `np.asarray(raw_backend) * b[..., None]`, forcing MLX -> CPU materialization before the rest of `FilmingStage.expose()` copies the image back to MLX.
3. `PrintingStage._spectral_compute_enlarger_gpu()` in the non-LUT path calls `_film_cmy_to_print_log_raw()`, which ends with `self._backend.to_numpy(raw)`, then immediately wraps that NumPy result with `self._backend.asarray(...)`. This is a full-frame GPU -> CPU -> GPU transfer in the main GPU path.
4. LUT helper functions copy MLX arrays unnecessarily. `apply_lut_trilinear_3d_backend()` prepares `lut_mx`, but `apply_lut_trilinear_3d_mlx()` calls `mx.array(lut, dtype=mx.float32)` again. `apply_lut_cubic_2d_mlx()` similarly copies an MLX input image. `compute_with_lut(..., prepared_lut=...)` computes `gpu_lut` but does not pass it to the backend dispatcher.
5. Existing docs mix unsynchronized MLX timings with synchronized timings. The final document must state that MLX lazy evaluation hides work unless `mx.eval()` or final NumPy materialization is included.

## Task 1: Backend Precision Selection

**Files:**
- Modify: `src/spektrafilm/gpu/mlx_backend.py`
- Modify: `src/spektrafilm/gpu/backend.py`
- Test: `tests/test_gpu_backend.py`

- [ ] **Step 1: Write failing tests**

Add tests proving:

```python
def test_select_backend_auto_float64_falls_back_to_cpu() -> None:
    backend = select_backend("auto", precision="float64")
    assert backend.name == "cpu"
    assert "float64" in (backend.fallback_reason or "")


def test_select_backend_mlx_float64_is_strict_error() -> None:
    with pytest.raises((BackendUnavailableError, ValueError), match="float64"):
        select_backend("mlx", precision="float64")
```

- [ ] **Step 2: Verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_gpu_backend.py::test_select_backend_auto_float64_falls_back_to_cpu tests/test_gpu_backend.py::test_select_backend_mlx_float64_is_strict_error -q
```

Expected before implementation: first test fails because `auto + float64` raises.

- [ ] **Step 3: Implement selection**

Change `select_backend()` so `requested == "auto" and precision == "float64"` returns `NumpyBackend(fallback_reason="GPU backends require float32 precision; using CPU for float64.")`. Keep explicit GPU backends strict.

- [ ] **Step 4: Verify GREEN**

Run the same targeted test command. Expected: 2 passed.

## Task 2: Filming Stage MLX Residency

**Files:**
- Modify: `src/spektrafilm/runtime/stages/filming.py`
- Test: `tests/test_gpu_pipeline.py`

- [ ] **Step 1: Write failing test**

Add an MLX-only regression:

```python
def test_filming_rgb_to_raw_keeps_mlx_array_after_lut_when_available() -> None:
    _require_mlx_backend()
    params = make_fast_test_params()
    params.settings.compute_backend = "mlx"
    pipeline = SimulationPipeline(params)
    image = np.ones((4, 4, 3), dtype=np.float64) * 0.184

    raw = pipeline._filming_stage._rgb_to_film_raw(image)

    assert pipeline._array_backend._is_mlx_array(raw)
```

- [ ] **Step 2: Verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_gpu_pipeline.py::test_filming_rgb_to_raw_keeps_mlx_array_after_lut_when_available -q
```

Expected before implementation: fails because current code returns NumPy.

- [ ] **Step 3: Implement residency fix**

In the MLX branch, multiply the 2D LUT output by `backend.asarray(b[..., None])` instead of materializing with `np.asarray(...)`.

- [ ] **Step 4: Verify GREEN**

Run the same targeted command. Expected: 1 passed.

## Task 3: Printing Stage Non-LUT Round-Trip Removal

**Files:**
- Modify: `src/spektrafilm/runtime/stages/printing.py`
- Test: `tests/test_gpu_pipeline.py`

- [ ] **Step 1: Write failing test**

Add an MLX-only regression that patches `backend.to_numpy` to fail while calling `_spectral_compute_enlarger_gpu()` with LUT disabled:

```python
def test_printing_non_lut_gpu_path_does_not_materialize_to_numpy(monkeypatch) -> None:
    _require_mlx_backend()
    params = make_fast_test_params()
    params.settings.compute_backend = "mlx"
    params.settings.use_enlarger_lut = False
    pipeline = SimulationPipeline(params)
    backend = pipeline._array_backend
    density = backend.asarray(np.full((4, 4, 3), 0.2, dtype=np.float32))

    def fail_to_numpy(_value):
        raise AssertionError("unexpected MLX to NumPy transfer")

    monkeypatch.setattr(backend, "to_numpy", fail_to_numpy)
    result = pipeline._printing_stage._spectral_compute_enlarger_gpu(density)

    assert backend._is_mlx_array(result)
```

- [ ] **Step 2: Verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_gpu_pipeline.py::test_printing_non_lut_gpu_path_does_not_materialize_to_numpy -q
```

Expected before implementation: fails at `_film_cmy_to_print_log_raw()`.

- [ ] **Step 3: Implement backend-return mode**

Split `_film_cmy_to_print_log_raw()` so the GPU chain can return the backend array without `to_numpy`. Keep tiny reference callers returning NumPy where CPU color-reference code expects NumPy.

- [ ] **Step 4: Verify GREEN**

Run the same targeted command. Expected: 1 passed.

## Task 4: LUT Wrapper Copy Avoidance

**Files:**
- Modify: `src/spektrafilm/gpu/kernels/lut.py`
- Modify: `src/spektrafilm/utils/lut.py`
- Test: `tests/test_gpu_lut.py`

- [ ] **Step 1: Write failing tests**

Add MLX tests that monkeypatch `mx.array` after creating prepared arrays and prove the prepared LUT/image path no longer calls `mx.array` on already-prepared MLX arrays.

- [ ] **Step 2: Verify RED**

Run the new LUT test names with:

```bash
.venv/bin/python -m pytest tests/test_gpu_lut.py -q
```

Expected before implementation: prepared-array tests fail.

- [ ] **Step 3: Implement no-copy wrappers**

Use a local `_as_mlx_array(mx, value, dtype)` helper that returns the value unchanged when `type(value).__module__.startswith("mlx.")` and dtype already matches. Pass `prepared_lut=gpu_lut` through `compute_with_lut()`.

- [ ] **Step 4: Verify GREEN**

Run the LUT tests. Expected: all pass or MLX-only tests skip on non-Metal hosts.

## Task 5: Documentation and Evidence

**Files:**
- Create: `docs/dev/2026-05-31-mlx-backend-review.md`

- [ ] **Step 1: Write final review document**

Include:
- Confirmed issues fixed in this pass.
- Official MLX conclusions: lazy evaluation requires explicit eval/sync for honest timing; MLX defaults floating arrays to float32; MLX GPU rejects float64.
- Current measured acceleration: targeted micro tests pass; if benchmark scripts are run, record command, hardware, and result.
- Float32 precision envelope: micro-kernel diffs generally `1e-7` to `1e-5`; large IIR/exponential halation can reach about `1e-4` to `5e-2` end-to-end depending on spatial effects and LUT mode; stochastic grain is not pixel-parity comparable.

- [ ] **Step 2: Verify docs reference current code**

Run:

```bash
rg -n "float64|to_numpy|np.asarray|prepared_lut|lazy|eval|float32" docs/dev/2026-05-31-mlx-backend-review.md src/spektrafilm/gpu src/spektrafilm/runtime/stages
```

Expected: document references are concrete and no stale claims about unsupported `float16` MLX precision remain.

## Task 6: Final Verification

**Files:**
- All files touched above.

- [ ] **Step 1: Run targeted GPU suite**

```bash
.venv/bin/python -m pytest tests/test_gpu_backend.py tests/test_gpu_lut.py tests/test_gpu_filters.py tests/test_gpu_density.py tests/test_gpu_color_chain.py tests/test_gpu_pipeline.py tests/test_gpu_primitives.py -q
```

Expected: pass, with optional skips for unavailable GPU backends.

- [ ] **Step 2: Run broader non-GUI suite**

```bash
.venv/bin/python -m pytest --ignore=tests/gui -q
```

Expected: pass. If local generated artifacts appear, audit them before final reporting.

- [ ] **Step 3: Run diff hygiene**

```bash
git diff --check
git status --short
```

Expected: no whitespace errors. Status should show only intentional existing/user changes plus this pass's additions.
