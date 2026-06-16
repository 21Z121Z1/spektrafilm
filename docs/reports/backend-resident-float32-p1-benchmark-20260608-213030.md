# Backend Resident Float32 P1 Benchmark - 20260608-213030

- Image source: `generated`
- Image shape: `[384, 512, 3]`
- Image dtype: `float32`
- Warmups: `0`
- Runs: `1`

## Summary

| Case | Status | Backend | Policy | Output | Median Wall | Materialize | Sync | Explicit NumPy | Max Abs Diff vs CPU |
|---|---|---|---|---|---:|---:|---:|---:|---:|
| cpu_default | ok | cpu | numpy_float64 | numpy.ndarray float64 | 0.600654s | 0.000003s | 0.000002s | 0.000003s | 0 |
| mlx_numpy_float64 | ok | mlx | numpy_float64 | numpy.ndarray float64 | 0.178705s | 0.150157s | 0.000128s | 0.000004s | 2.23611e-06 |
| mlx_numpy_float32 | ok | mlx | numpy_float32 | numpy.ndarray float32 | 0.037913s | 0.032534s | 0.000070s | 0.000004s | 2.23611e-06 |
| mlx_backend | ok | mlx | backend | mlx.core.array mlx.core.float32 | 0.022794s | 0.000002s | 0.017974s | 0.000018s | 2.23611e-06 |

## Notes

- `SimulationPipeline.materialize` records pipeline policy cost.
- `Sync` is an explicit benchmark-side backend eval/synchronize after `process()`.
- `Explicit NumPy` is a benchmark-side conversion for validation/export-style inspection.
- This P1 benchmark is a residency/materialization diagnostic, not a 12MP RAW performance proof.
