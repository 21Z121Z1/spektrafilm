# Backend Resident Float32 P3 GUI Preview Export Report - 2026-06-08

## Executive Summary

P3 GUI preview/export separation is complete and the P3 gate is closed.

The GUI worker no longer creates a persistent full NumPy float export image
before display when the runtime returns a backend-resident array. Display
preparation now records `gui.preview_materialize`, output layer metadata stores
the raw export source without forcing `np.asarray(..., dtype=np.float32)`, and
explicit save/export materializes the full float image through
`gui.export_materialize`.

P4 is allowed to start, with a fresh HDR/grain/full-render audit and plan.

## Modified P3 Files

- `src/spektrafilm_gui/controller_runtime.py`
- `src/spektrafilm_gui/controller_layers.py`
- `src/spektrafilm_gui/controller.py`
- `tests/gui/test_controller_runtime_module.py`
- `tests/gui/test_controller_layers.py`
- `tests/gui/test_controller_output.py`
- `tools/benchmark_gui_mlx_full_render.py`
- `docs/plans/backend-resident-float32-p3-gui-preview-export-plan-20260608.md`
- `docs/reports/backend-resident-float32-p3-gui-preview-export-20260608.md`

The working tree also contains P1/P2 files and unrelated HDR/GUI changes that
were already present; P3 did not revert them.

## What Changed

GUI worker:

- Removed the worker-level `scan_array = np.asarray(scan)` export materialize
  step from `execute_simulation_request()`.
- `SimulationResult.float_image` now carries the runtime export source as
  `object | None`, so it can be a NumPy array, MLX array, or compatible backend
  object.
- `prepare_output_display_image()` records `gui.preview_materialize` for the
  display CPU materialization boundary.
- Added `materialize_export_image()` for explicit full-float export
  materialization and `gui.export_materialize` timing.
- Status timing summary now reports `process`, `preview`, `display`, and
  `export` when present.

Layer/save path:

- Output layer metadata stores the raw float/export source without converting
  it to NumPy.
- Existing float32 NumPy arrays remain stored without a copy.
- `save_output_layer()` materializes the full float export image on demand via
  `runtime.materialize_export_image()`.
- Existing fallback behavior remains: if no float/export source metadata exists,
  save uses normalized output layer display data.

Benchmark:

- `tools/benchmark_gui_mlx_full_render.py` now supports
  `--materialize-policy`, `--export`, and `--no-write`.
- Benchmark output reports export source type/dtype separately from display
  image and explicit export image.
- Benchmark output separates worker wall time from total wall time.

## Default Behavior

CPU/default runtime behavior remains governed by P1:

- default `settings.materialize_policy` is still `numpy_float64`;
- CPU/default `runtime.process()` still returns NumPy float64;
- GUI CPU/default preview stores the existing runtime NumPy output source and
  does not change SDR rendering semantics.

P3 changes only when and where GUI export materialization occurs.

## Preview Boundary

P3 does not rewrite the display transform stack to run on MLX/Metal. Preview
still materializes CPU display input because the existing GUI display path uses
NumPy, Pillow/ImageCms, and colour conversions.

The corrected boundary is:

- preview materialization: `gui.preview_materialize`;
- display conversion: `gui.display_uint8` and `gui.display_prepare`;
- explicit export materialization: `gui.export_materialize`, only when save or
  benchmark `--export` requests it.

## Tests

P3 focused GUI slice:

```text
.venv/bin/python -m pytest tests/gui/test_controller_runtime_module.py tests/gui/test_controller_layers.py tests/gui/test_controller_output.py tests/gui/test_controller_flow.py -q
84 passed in 1.96s
```

P1 focused gate:

```text
.venv/bin/python -m pytest tests/test_runtime_materialize_policy.py tests/test_backend_resident_float32.py tests/test_gpu_highlight_boost_sync.py -q
15 passed in 1.91s
```

P2 focused gate:

```text
.venv/bin/python -m pytest tests/test_backend_resident_runtime_boundaries.py tests/test_spectral_lut_service.py -q
11 passed in 3.00s
```

SDR/golden gate:

```text
.venv/bin/python -m pytest tests/test_pipeline_smoke.py::test_midgray_input_produces_expected_output_values tests/test_regression_baselines.py tests/test_upstream_parity.py::TestGoldenReference::test_midgray_output_golden_reference -q
7 passed in 1.56s
```

Full non-GUI gate:

```text
.venv/bin/python -m pytest --ignore=tests/gui -q
1408 passed, 7 skipped, 1 warning in 90.44s
```

Diff hygiene:

```text
git diff --check
passed with no output
```

Static materialization scan:

```text
rg -n "gui\\.float_materialize|float_materialize_copy|scan_array = np\\.asarray\\(scan\\)|np\\.asarray\\(float_image, dtype=np\\.float32\\)" src/spektrafilm_gui tests/gui tools/benchmark_gui_mlx_full_render.py
```

Only negative assertions in `tests/gui/test_controller_runtime_module.py`
matched. No implementation path retained the old worker export materialization
key or forced layer metadata conversion.

## Benchmark Results

CPU default GUI-like benchmark:

```text
.venv/bin/python tools/benchmark_gui_mlx_full_render.py --backend cpu --runs 2 --warmups 1 --materialize-policy numpy_float64 --no-write
status ok
median wall_seconds 0.240592s
export_source_type numpy.ndarray
export_source_dtype float64
export requested false
median gui.preview_materialize 0.000003s
median gui.display_prepare 0.001422s
```

MLX/backend preview benchmark:

```text
.venv/bin/python tools/benchmark_gui_mlx_full_render.py --backend mlx --precision float32 --runs 2 --warmups 1 --materialize-policy backend --no-write
status ok
median wall_seconds 0.063829s
export_source_type mlx.core.array
export_source_dtype mlx.core.float32
export requested false
median gui.preview_materialize 0.019041s
median gui.display_prepare 0.020500s
no gui.export_materialize phase
```

MLX/backend explicit-export benchmark:

```text
.venv/bin/python tools/benchmark_gui_mlx_full_render.py --backend mlx --precision float32 --runs 2 --warmups 1 --materialize-policy backend --export --no-write
status ok
median wall_seconds 0.068318s
export_source_type mlx.core.array
export_source_dtype mlx.core.float32
export requested true
export dtype float32
median gui.preview_materialize 0.024401s
median gui.display_prepare 0.025899s
median gui.export_materialize 0.000011s
```

These are 512x384 GUI-like synthetic runs only. They prove the P3 boundary and
type/timing contract, not 12MP RAW performance.

## Correctness Validation

- Focused GUI tests prove display image generation still works, output layer
  metadata can store backend-like export sources without materializing, and
  save materializes lazy export sources exactly on demand.
- P1/P2 focused tests and SDR/golden tests remained green.
- Full non-GUI tests remained green.
- MLX preview benchmark output source stayed `mlx.core.array` with
  `mlx.core.float32` dtype under `materialize_policy="backend"`.
- Explicit export converted that source to NumPy `float32` only when requested.

## Known Limitations

- The display preview path still materializes CPU data. P3 separates preview
  and export semantics; it does not implement a Metal-native display preview.
- Explicit export after preview may be cheap in the synthetic benchmark because
  preview has already forced a display synchronization. The important P3
  contract is that persistent full float export image creation is no longer part
  of normal worker completion.
- HDR HEIC export remains its own explicit path and is not made backend
  resident in P3.
- No 12MP RAW/DNG P3 benchmark was run in this stage.

## Self Review

- Default CPU/public API behavior: preserved by P1 settings and revalidated by
  P1, SDR/golden, and full non-GUI tests.
- MLX backend policy: benchmark confirms GUI worker export source is
  `mlx.core.array` float32.
- Preview/export split: worker has no `gui.float_materialize`; preview records
  `gui.preview_materialize`; explicit export records `gui.export_materialize`.
- Tests and benchmark: targeted P3 tests, P1/P2 gates, full non-GUI suite, and
  GUI-like benchmarks passed.
- Documentation: P3 plan and report are present.

## Gate Decision

P3 is complete and allowed to advance to P4.

P4 must start with its own audit and plan, focused on HDR sidecar,
scene-luminance/scene-rgb, grain/stochastic effects, synthetic and real-sample
validation, and explicit preview/export/HDR/grain benchmark matrix separation.
