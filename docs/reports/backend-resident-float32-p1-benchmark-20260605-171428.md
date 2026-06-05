# Backend Resident Float32 P1 Benchmark - 20260605-171428

- Image source: `generated`
- Image shape: `[384, 512, 3]`
- Image dtype: `float32`
- Warmups: `1`
- Runs: `2`

## Summary

| Case | Status | Backend | Policy | Output | Median Wall | Materialize | Sync | Explicit NumPy | Max Abs Diff vs CPU |
|---|---|---|---|---|---:|---:|---:|---:|---:|
| cpu_default | ok | cpu | numpy_float64 | numpy.ndarray float64 | 0.556335s | 0.000004s | 0.000003s | 0.000002s | 0 |
| mlx_numpy_float64 | ok | mlx | numpy_float64 | numpy.ndarray float64 | 0.020521s | 0.013958s | 0.000075s | 0.000003s | 2.23611e-06 |
| mlx_numpy_float32 | ok | mlx | numpy_float32 | numpy.ndarray float32 | 0.017497s | 0.013009s | 0.000066s | 0.000002s | 2.23611e-06 |
| mlx_backend | ok | mlx | backend | mlx.core.array mlx.core.float32 | 0.019660s | 0.000001s | 0.015122s | 0.000017s | 2.23611e-06 |

## Notes

- `SimulationPipeline.materialize` records pipeline policy cost.
- `Sync` is an explicit benchmark-side backend eval/synchronize after `process()`.
- `Explicit NumPy` is a benchmark-side conversion for validation/export-style inspection.
- This P1 benchmark is a residency/materialization diagnostic, not a 12MP RAW performance proof.
