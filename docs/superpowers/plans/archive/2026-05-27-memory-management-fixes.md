# Memory Management Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the real memory pressure bugs found in the current runtime/GUI/GPU paths without changing film simulation output quality.

**Architecture:** Keep `Simulator.process()` as the normal array-only path and make HDR sidecar collection an explicit request property. Make `scene_rgb` opt-in because current GUI export settings do not expose `source_chroma`, while `scene_luminance` remains available when HDR output is enabled. Add backend cleanup hooks so CuPy and MLX can release free GPU cache blocks after a top-level pipeline run.

**Tech Stack:** Python 3.13, NumPy, Qt GUI controller/runtime modules, MLX, CuPy, pytest.

---

## Evidence And Scope

- Requested documents read:
  - `docs/archive/docs-2-legacy-20260531/dev/research-memory-management.md`
  - `docs/archive/docs-2-legacy-20260531/dev/research-memory-optimization-patterns.md`
- Current source confirms the real H3 issue from `docs/dev/code-review-2026-05-26.md`: `GuiController._process_image_with_runtime()` calls `process_with_metadata()` whenever available, so normal preview/scan pays for full-frame `scene_luminance`, full-frame `scene_rgb`, and profile characterization.
- Current `HDRSceneEnergyMetadata.scene_rgb` is already typed as optional, and GUI mapping kwargs do not expose `hdr_highlight_color_mode="source_chroma"`, so retaining `scene_rgb` by default is unnecessary memory cost.
- Current `CupyBackend` and `MlxBackend` expose `synchronize()` but no cleanup hook. Official CuPy docs say pools preserve freed blocks and `free_all_blocks()` releases free blocks; official MLX docs expose `clear_cache()`.
- Not implementing broader pipeline buffer reuse, memmap I/O, or stage fusion in this pass. Those change pipeline ownership and are explicitly larger architecture work. The current request can be fulfilled by fixing actual sidecar and GPU cache lifecycle issues first.
- Not copying the research doc's MLX `set_memory_limit(0.8)` style: current MLX documentation specifies byte counts, not fractions.

## Task 1: Make HDR Metadata Collection Explicit In The GUI Runtime Request

**Files:**
- Modify: `src/spektrafilm_gui/controller_runtime.py`
- Modify: `src/spektrafilm_gui/controller.py`
- Test: `tests/gui/test_controller_runtime_module.py`
- Test: `tests/gui/test_controller_flow.py`

- [ ] **Step 1: Write failing request-routing tests**

Add tests proving:

```python
def test_execute_simulation_request_defaults_to_array_only_runtime_path():
    request = SimulationRequest(..., collect_hdr_scene_energy=False)
    def run(image, params, *, collect_hdr_scene_energy=False, collect_hdr_scene_rgb=False):
        assert collect_hdr_scene_energy is False
        assert collect_hdr_scene_rgb is False
        return np.full((2, 2, 3), 0.5, dtype=np.float32)
```

And a GUI controller test proving SDR default calls `FakeSimulator.process()` rather than `process_with_metadata()`.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/gui/test_controller_runtime_module.py tests/gui/test_controller_flow.py::test_process_image_with_runtime_uses_process_for_sdr_output_by_default -q
```

Expected: failure because `SimulationRequest` has no `collect_hdr_scene_energy` field and the controller always chooses `process_with_metadata()` when present.

- [ ] **Step 3: Implement request flags**

Add to `SimulationRequest`:

```python
collect_hdr_scene_energy: bool = False
collect_hdr_scene_rgb: bool = False
```

Update `execute_simulation_request()` to pass these flags to `run_simulation_fn`.

Update `GuiController._start_simulation()`:

```python
collect_hdr_scene_energy = bool(getattr(state.simulation, "hdr_exr_output", False))
collect_hdr_scene_rgb = self._hdr_export_requires_scene_rgb(state)
```

Add `_hdr_export_requires_scene_rgb()` returning true only when a future/hidden HDR export state explicitly asks for `hdr_highlight_color_mode == "source_chroma"`.

- [ ] **Step 4: Update `_process_image_with_runtime()`**

Change signature:

```python
def _process_image_with_runtime(
    self,
    image_data: np.ndarray,
    params,
    *,
    collect_hdr_scene_energy: bool = False,
    collect_hdr_scene_rgb: bool = False,
) -> np.ndarray:
```

Call `process_with_metadata(image_data, include_scene_rgb=collect_hdr_scene_rgb)` only when `collect_hdr_scene_energy` is true and the simulator supports it. Otherwise call `process(image_data)`.

- [ ] **Step 5: Verify GREEN**

Run the same targeted tests and confirm they pass.

## Task 2: Make Runtime `scene_rgb` Sidecar Optional

**Files:**
- Modify: `src/spektrafilm/runtime/pipeline.py`
- Modify: `src/spektrafilm/runtime/process.py`
- Test: `tests/test_runtime_api.py`

- [ ] **Step 1: Write failing metadata tests**

Add tests proving:

```python
metadata = _hdr_scene_energy_metadata(..., include_scene_rgb=False)
assert metadata.scene_rgb is None

metadata = _hdr_scene_energy_metadata(..., include_scene_rgb=True)
assert metadata.scene_rgb.shape == image.shape
```

Add a simulator API test proving `Simulator.process_with_metadata(image, include_scene_rgb=True)` forwards the flag.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_runtime_api.py::TestRuntimeApi::test_hdr_scene_energy_metadata_omits_scene_rgb_by_default tests/test_runtime_api.py::TestRuntimeApi::test_hdr_scene_energy_metadata_can_include_scene_rgb tests/test_runtime_api.py::TestRuntimeApi::test_simulator_process_with_metadata_forwards_scene_rgb_flag -q
```

Expected: failure because the flag does not exist and `scene_rgb` is always computed.

- [ ] **Step 3: Implement optional sidecar**

Add `include_scene_rgb: bool = False` to `_hdr_scene_energy_metadata()`, `_preprocess_input_image_with_metadata()`, `SimulationPipeline.process_with_metadata()`, and `Simulator.process_with_metadata()`.

Compute `scene_rgb` only under that flag. Keep `scene_luminance`, scalar metadata, and profile curves unchanged when metadata collection is requested.

- [ ] **Step 4: Verify GREEN**

Run the targeted `tests/test_runtime_api.py` slice and confirm it passes.

## Task 3: Add GPU Backend Cache Cleanup Hooks

**Files:**
- Modify: `src/spektrafilm/gpu/backend.py`
- Modify: `src/spektrafilm/gpu/numpy_backend.py`
- Modify: `src/spektrafilm/gpu/cupy_backend.py`
- Modify: `src/spektrafilm/gpu/mlx_backend.py`
- Modify: `src/spektrafilm/runtime/pipeline.py`
- Test: `tests/test_gpu_backend.py`
- Test: `tests/test_runtime_api.py`

- [ ] **Step 1: Write failing backend cleanup tests**

Add tests using fake CuPy and fake MLX modules:

```python
def test_cupy_backend_cleanup_releases_default_memory_pools(monkeypatch):
    backend = CupyBackend()
    backend.cleanup()
    assert calls == ["sync", "device-free", "pinned-free"]
```

```python
def test_mlx_backend_cleanup_clears_cache_after_synchronize(monkeypatch):
    backend = MlxBackend()
    backend.cleanup()
    assert calls == ["eval", "sync", "clear-cache"]
```

Add a pipeline test proving top-level `process()` calls backend cleanup once after result materialization.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_gpu_backend.py::test_cupy_backend_cleanup_releases_default_memory_pools tests/test_gpu_backend.py::test_mlx_backend_cleanup_clears_cache_after_synchronize tests/test_runtime_api.py::TestRuntimeApi::test_pipeline_process_cleans_up_gpu_backend_after_materialization -q
```

Expected: failure because `cleanup()` and pipeline cleanup do not exist.

- [ ] **Step 3: Implement backend cleanup**

Add optional `cleanup()` to the backend protocol and no-op `NumpyBackend.cleanup()`.

For `CupyBackend`, store:

```python
self._mempool = cp.get_default_memory_pool()
self._pinned_mempool = cp.get_default_pinned_memory_pool()
```

and implement:

```python
def cleanup(self) -> None:
    self.synchronize()
    self._mempool.free_all_blocks()
    self._pinned_mempool.free_all_blocks()
```

For `MlxBackend`, call `synchronize()` then `mx.clear_cache()` when present, falling back to `mx.metal.clear_cache()` for older installations.

In `SimulationPipeline`, call a private `_cleanup_backend_cache()` in `finally` for `process()` and `process_with_metadata()`.

- [ ] **Step 4: Verify GREEN**

Run the targeted backend/runtime tests and confirm they pass.

## Task 4: Documentation And Final Verification

**Files:**
- Modify or create: `docs/dev/memory-management-implementation-2026-05-27.md`
- Modify if needed: `README.md`

- [ ] **Step 1: Write implementation notes**

Document the final contract:

- normal GUI preview/scan uses array-only runtime unless HDR output is enabled;
- `process_with_metadata()` collects `scene_luminance` and scalar HDR metadata, but `scene_rgb` is opt-in;
- CuPy/MLX cleanup frees cache/free blocks after top-level processing;
- MLX memory limit accepts bytes, so fraction examples from older notes were not implemented.

- [ ] **Step 2: Run targeted verification**

Run:

```bash
.venv/bin/python -m pytest tests/test_runtime_api.py tests/test_gpu_backend.py tests/gui/test_controller_runtime_module.py tests/gui/test_controller_flow.py tests/gui/test_controller_output.py -q
```

- [ ] **Step 3: Run broader non-GUI verification**

Run:

```bash
.venv/bin/python -m pytest --ignore=tests/gui -q
```

- [ ] **Step 4: Run syntax and whitespace checks**

Run:

```bash
.venv/bin/python -m compileall src tests
git diff --check
```

- [ ] **Step 5: 100% confidence self-audit loop**

Before completion, re-open:

- call sites for `process_with_metadata`;
- save-output behavior for HEIC and HDR-rendition EXR;
- backend fake tests and real backend fallback behavior;
- generated diff.

If any gap remains, add the missing failing test first, then implement the smallest fix and repeat verification.
