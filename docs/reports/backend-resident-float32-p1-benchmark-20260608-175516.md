# Backend Resident Float32 P1 Benchmark - 20260608-175516

- Image source: `generated`
- Image shape: `[384, 512, 3]`
- Image dtype: `float32`
- Warmups: `1`
- Runs: `2`

## Summary

| Case | Status | Backend | Policy | Output | Median Wall | Materialize | Sync | Explicit NumPy | Max Abs Diff vs CPU |
|---|---|---|---|---|---:|---:|---:|---:|---:|
| cpu_default | ok | cpu | numpy_float64 | numpy.ndarray float64 | 0.465964s | 0.000002s | 0.000002s | 0.000001s | 0 |

## Notes

- `SimulationPipeline.materialize` records pipeline policy cost.
- `Sync` is an explicit benchmark-side backend eval/synchronize after `process()`.
- `Explicit NumPy` is a benchmark-side conversion for validation/export-style inspection.
- This P1 benchmark is a residency/materialization diagnostic, not a 12MP RAW performance proof.
