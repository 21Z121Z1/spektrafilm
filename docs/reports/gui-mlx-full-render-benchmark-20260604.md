# GUI MLX Full Render Benchmark - 2026-06-04

## Scope

This report summarizes the headless GUI-like full-render worker benchmark added in `tools/benchmark_gui_mlx_full_render.py`.

The benchmark uses a synthetic `512x384` float32 image, the real GUI input preparation helper, `controller_runtime.execute_simulation_request()`, and the runtime pipeline with grain/stochastic effects disabled. It is a focused copy/timing regression benchmark, not a replacement for a 12MP default-quality RAW benchmark.

Artifacts:

- `docs/reports/gui-mlx-full-render-benchmark-20260604-cpu.json`
- `docs/reports/gui-mlx-full-render-benchmark-20260604-cpu.md`
- `docs/reports/gui-mlx-full-render-benchmark-20260604-mlx.json`
- `docs/reports/gui-mlx-full-render-benchmark-20260604-mlx.md`

## Commands

```bash
uv run python tools/benchmark_gui_mlx_full_render.py --backend cpu
uv run python tools/benchmark_gui_mlx_full_render.py --backend mlx --precision float32
```

## Results

| Backend | Precision | Median wall | Min | Max | Speed vs CPU |
|---|---|---:|---:|---:|---:|
| CPU | float64 | 0.657018s | 0.548733s | 0.981479s | 1.00x |
| MLX | float32 | 0.076036s | 0.059970s | 0.085732s | 8.64x |

## GUI Copy Evidence

| Backend | Input request bytes | Input copy bytes | Float image bytes | Display image bytes |
|---|---:|---:|---:|---:|
| CPU | 4,718,592 | 4,718,592 | 4,718,592 | 589,824 |
| MLX | 2,359,296 | 0 | 4,718,592 | 589,824 |

The MLX float32 path now keeps the GUI request input at float32 and avoids the pre-worker full-size float64 copy. The runtime still returns a float64 NumPy output, so the saved/exportable float image remains 4,718,592 bytes for this benchmark. That is the remaining runtime materialization boundary, not a GUI pre-dispatch copy.

## Phase Timing Summary

| Phase | CPU median | MLX median |
|---|---:|---:|
| `gui.input_prepare` | 0.000124s | 0.000008s |
| `gui.input_dtype_convert` | 0.000121s | 0.000003s |
| `gui.input_copy` | 0.000121s | 0.000000s |
| `runtime.process` | 0.652957s | 0.074786s |
| `gui.float_materialize` | 0.000000s | 0.000002s |
| `gui.display_uint8` | 0.001216s | 0.001194s |
| `gui.display_prepare` | 0.001228s | 0.001209s |
| `gui.worker_total` | 0.656636s | 0.076009s |

## Remaining Boundaries

- `SimulationPipeline._preprocess_base()` still converts to float64 internally.
- `SimulationPipeline._materialize_output()` still returns float64 NumPy output for the public runtime API.
- Full-size display output is still generated for the napari output layer; display-sized previews are intentionally deferred.
- This benchmark disables grain/stochastic effects. Default-quality 12MP RAW performance remains dominated by runtime scanner/grain work from the earlier 2026-06-03 report.
