# Memory Management Implementation Notes

Date: 2026-05-27

## Scope

This implementation addresses the real memory-management issues confirmed in
the current Spektrafilm runtime and GUI paths after reviewing:

- `docs/archive/docs-2-legacy-20260531/dev/research-memory-management.md`
- `docs/archive/docs-2-legacy-20260531/dev/research-memory-optimization-patterns.md`
- current `src/spektrafilm/runtime`, `src/spektrafilm/gpu`, and
  `src/spektrafilm_gui` call sites

The change intentionally does not implement broad pipeline buffer reuse,
memmap I/O, or stage fusion. Those are larger architecture changes and were
not required to remove the confirmed sidecar and GPU cache pressure found in
the live code.

## Confirmed Issues

### 1. GUI runtime collected HDR sidecars by default

`GuiController._process_image_with_runtime()` used `process_with_metadata()`
whenever the simulator exposed it. That made normal preview and scan runs pay
for full-frame HDR metadata even when the output path only needed an array.

For a 6000 x 4000 image, one float32 RGB sidecar is about 275 MiB:

```text
6000 * 4000 * 3 * 4 bytes = 274.7 MiB
```

The previous default path could keep both `scene_luminance` and `scene_rgb`
sidecars alive on the output layer, plus profile characterization work.

### 2. `scene_rgb` was computed even though it is optional

`HDRSceneEnergyMetadata.scene_rgb` is already optional. The current HDR photo
path only needs it for source-chroma highlight recovery. The normal HDR
mapping path can use `scene_luminance` and scalar metadata without the RGB
sidecar.

### 3. GPU backend caches had no top-level cleanup hook

CuPy and MLX backends exposed synchronization but no runtime-level cleanup.
That left free GPU memory pool blocks and MLX cache entries alive after a
top-level pipeline run.

## Implemented Contract

### GUI runtime requests

`SimulationRequest` now carries explicit collection flags:

```python
collect_hdr_scene_energy: bool = False
collect_hdr_scene_rgb: bool = False
```

Normal preview and scan use `Simulator.process()`. The GUI only requests
`process_with_metadata()` when HDR output is enabled.

`collect_hdr_scene_rgb` is only enabled when HDR metadata is requested and the
HDR export state explicitly asks for:

```python
hdr_highlight_color_mode == "source_chroma"
```

### Runtime metadata

`SimulationPipeline.process_with_metadata()` and
`Simulator.process_with_metadata()` now accept:

```python
include_scene_rgb: bool = False
```

By default, metadata collection still records:

- `scene_luminance`
- diffuse white estimate
- headroom estimate
- auto exposure EV
- profile scene/look curves

It does not allocate `scene_rgb` unless the caller explicitly asks for it.

### Backend cleanup

All array backends now expose `cleanup()`.

`SimulationPipeline.process()` and `SimulationPipeline.process_with_metadata()`
call backend cleanup in a `finally` block after materializing the result and
recording elapsed time.

Backend behavior:

- NumPy: no-op.
- CuPy: synchronize, then release default and pinned memory pool free blocks.
- MLX: synchronize, then call `mx.clear_cache()` when present, falling back to
  `mx.metal.clear_cache()` for older installations.

## Search-Backed Decisions

The research notes mentioned memory limits and pool management. Current
upstream documentation led to these implementation choices:

- CuPy memory pools intentionally retain freed blocks; `free_all_blocks()` is
  the correct explicit release hook for free pool blocks.
- MLX memory limits use byte counts. Fraction-style examples such as
  `set_memory_limit(0.8)` were not implemented because they do not match the
  current API contract.
- NumPy in-place and `out=` patterns remain valid, but changing the spectral
  pipeline to buffer reuse is separate architecture work. This pass only
  changes paths with confirmed waste and direct tests.

## Verification Results

Targeted regression tests:

```bash
.venv/bin/python -m pytest tests/test_runtime_api.py::TestRuntimeApi::test_hdr_scene_energy_metadata_omits_scene_rgb_by_default tests/test_runtime_api.py::TestRuntimeApi::test_hdr_scene_energy_metadata_can_include_scene_rgb tests/test_runtime_api.py::TestRuntimeApi::test_simulator_process_with_metadata_forwards_scene_rgb_flag tests/test_runtime_api.py::TestRuntimeApi::test_pipeline_process_cleans_up_gpu_backend_after_materialization tests/test_gpu_backend.py::test_mlx_backend_cleanup_clears_cache_after_synchronize tests/test_gpu_backend.py::test_cupy_backend_cleanup_releases_default_memory_pools tests/gui/test_controller_runtime_module.py::test_execute_simulation_request_passes_hdr_collection_flags tests/gui/test_controller_flow.py::test_process_image_with_runtime_uses_process_for_sdr_output_by_default tests/gui/test_controller_flow.py::test_process_image_with_runtime_collects_metadata_when_requested -q
```

Result: 9 passed.

Related runtime/GPU/GUI suite:

```bash
.venv/bin/python -m pytest tests/test_runtime_api.py tests/test_gpu_backend.py tests/gui/test_controller_runtime_module.py tests/gui/test_controller_flow.py tests/gui/test_controller_output.py -q
```

Result: 123 passed.

Full test suite:

```bash
.venv/bin/python -m pytest -q
```

Result: 734 passed, 6 skipped.

Syntax and whitespace checks:

```bash
.venv/bin/python -m compileall src tests
git diff --check
```

Result: both passed.
