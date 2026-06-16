# Backend Resident Float32 P3 GUI Preview Export Plan - 2026-06-08

## Gate Status

P1 and P2 are closed in:

- `docs/reports/backend-resident-float32-p1-foundation-20260608.md`
- `docs/reports/backend-resident-float32-p2-runtime-boundaries-20260608.md`

P2 explicitly allows P3. This plan is P3 only. P4 remains blocked until the
P3 report proves the GUI preview/export gate.

## Refined P3 /goal

Split the GUI worker preview path from explicit export materialization without
changing CPU/default runtime semantics:

- runtime `process()` may return NumPy or backend arrays according to the P1
  `materialize_policy`;
- GUI display preparation may explicitly materialize the render output only for
  preview/display conversion and records that as preview materialization;
- the GUI must not persistently create a full NumPy float export image during a
  normal preview/scan update when the runtime result is backend-resident;
- full float export materialization happens only when the save/export path asks
  for it, records a separate export timing, and uses the recorded render
  metadata for color conversion;
- existing GUI save, output layer, status, HDR metadata sidecar, and CPU/default
  behavior remain compatible.

## Audit Evidence

Current P3 boundary:

- `src/spektrafilm_gui/controller_runtime.py` defines
  `SimulationResult.float_image: np.ndarray`.
- `execute_simulation_request()` runs `scan_array = np.asarray(scan)` before
  display preparation, stores `gui.float_materialize`, and returns the
  materialized array as `float_image`.
- `src/spektrafilm_gui/controller_layers.py` stores
  `np.asarray(float_image, dtype=np.float32)` in output layer metadata, causing
  a second persistent full float copy for backend arrays.
- `src/spektrafilm_gui/controller.py::save_output_layer()` already has an
  output-layer fallback when float metadata is missing, but when float metadata
  exists it calls `np.asarray(float_image_data)` without export-specific timing.
- `tools/benchmark_gui_mlx_full_render.py` reports `float_shape` and
  `float_dtype` from `SimulationResult.float_image`, so it currently treats the
  worker float materialization as inherent to preview.

Allowed P3 CPU boundaries:

- Display preparation can materialize the current runtime result into CPU memory
  because the existing display transform stack is NumPy/Pillow/colour based.
- Explicit save/export can materialize a full float NumPy array.
- HDR HEIC export remains an explicit save path and is not rewritten in P3.

Disallowed P3 behavior:

- Normal worker completion must not force a persistent full NumPy float export
  image when `materialize_policy="backend"` returns a backend array.
- Layer metadata must not force backend arrays through `np.asarray(...,
  dtype=np.float32)` during preview update.
- Benchmarks must not merge runtime, preview materialization, display, and
  export materialization into one opaque timing.

## Implementation Scope

Planned code changes:

- `src/spektrafilm_gui/controller_runtime.py`
  - Allow `SimulationResult.float_image` to hold backend arrays or `None`.
  - Remove worker-level full export materialization.
  - Add preview materialization timing inside `prepare_output_display_image()`.
  - Add an explicit export materialization helper used by save/export paths.
  - Update phase timing summary to report preview/display/export separately.
- `src/spektrafilm_gui/controller_layers.py`
  - Store output float/export source metadata without converting to NumPy.
  - Keep old NumPy array behavior compatible, including no-copy reuse for
    existing float32 arrays.
- `src/spektrafilm_gui/controller.py`
  - Pass the raw runtime result/export source through layer metadata.
  - Materialize the full float image only in `save_output_layer()`.
  - Record export materialization timing in output layer metadata when present.
- `tools/benchmark_gui_mlx_full_render.py`
  - Add materialize-policy and explicit-export controls.
  - Report runtime source type/dtype separately from display and export.
- GUI tests covering worker, layer metadata, and explicit save materialization.

## Not In Scope

- No global float32 conversion.
- No float16.
- No rewrite of the display transform stack to run on MLX/Metal.
- No rewrite of HDR HEIC RouteMaster export.
- No grain/stochastic/HDR sidecar residency work; that is P4.
- No claim that synthetic GUI-like benchmarks prove 12MP RAW performance.

## Risk Analysis

- Save correctness risk: if raw backend metadata is stored, explicit save must
  convert it before colour conversion and `save_image_oiio()`. A helper with a
  test will cover this.
- Metadata compatibility risk: tests and older callers may expect NumPy
  metadata. NumPy arrays remain accepted and are stored without a copy when they
  are already float32.
- Timing wording risk: `gui.float_materialize` currently means worker-created
  export image. P3 replaces it with `gui.preview_materialize` and
  `gui.export_materialize`; tests and benchmark output must be updated.
- Display-memory risk: preview still requires a CPU/display materialization.
  The report must explicitly state this is not a GPU display rewrite.

## Verification Plan

Targeted P3 tests:

- `.venv/bin/python -m pytest tests/gui/test_controller_runtime_module.py tests/gui/test_controller_layers.py tests/gui/test_controller_output.py tests/gui/test_controller_flow.py -q`

Regression gates:

- `.venv/bin/python -m pytest tests/test_runtime_materialize_policy.py tests/test_backend_resident_float32.py tests/test_gpu_highlight_boost_sync.py -q`
- `.venv/bin/python -m pytest tests/test_backend_resident_runtime_boundaries.py tests/test_spectral_lut_service.py -q`
- `.venv/bin/python -m pytest tests/test_pipeline_smoke.py::test_midgray_input_produces_expected_output_values tests/test_regression_baselines.py tests/test_upstream_parity.py::TestGoldenReference::test_midgray_output_golden_reference -q`
- `.venv/bin/python -m pytest --ignore=tests/gui -q`

Benchmarks:

- `.venv/bin/python tools/benchmark_gui_mlx_full_render.py --backend cpu --runs 2 --warmups 1 --materialize-policy numpy_float64 --no-write`
- `.venv/bin/python tools/benchmark_gui_mlx_full_render.py --backend mlx --precision float32 --runs 2 --warmups 1 --materialize-policy backend --no-write`
- `.venv/bin/python tools/benchmark_gui_mlx_full_render.py --backend mlx --precision float32 --runs 2 --warmups 1 --materialize-policy backend --export --no-write`

If MLX is unavailable, the benchmark must report failure/skip honestly; CPU and
targeted tests still need to pass.

## Rollback Strategy

P3 is isolated to GUI runtime/layer/save code and the GUI-like benchmark. If the
gate fails, revert the P3 files only and keep P1/P2 intact. The fallback
behavior remains simple: store a NumPy float image in output metadata exactly as
before.

## P3 Gate

P3 can advance to P4 only if:

- P1/P2 regression gates remain green.
- `materialize_policy="backend"` GUI worker completion keeps the runtime output
  source as a backend array rather than a persistent NumPy float export image.
- Display image generation still works and records preview materialization.
- Explicit save/export materializes the full float image on demand and records
  export materialization.
- GUI tests and benchmark output document the separated timings.
- The P3 report lists known limits and explicitly allows P4.
