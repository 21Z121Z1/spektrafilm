# Backend Resident Float32 P2 Runtime Boundaries - 20260608-213148

- Image shape: `[384, 512, 3]`
- Warmups: `0`
- Runs: `1`
- Scanner LUT: `False`

## Summary

| Case | Status | Output | Median Runtime | Sync | Explicit NumPy | Unallowed to_numpy | Max Abs Diff vs CPU | Max Abs Diff vs CPU Direct |
|---|---|---|---:|---:|---:|---:|---:|---:|
| cpu_default | ok | numpy.ndarray float64 | 1.133454s | 0.000102s | 0.000064s | 0 | 0 | 0 |
| mlx_backend | ok | mlx.core.array mlx.core.float32 | 0.111261s | 0.000129s | 0.109456s | 0 | 6.4131e-06 | 6.4131e-06 |

## Stage Trace

### cpu_default

| Tap | Type | Dtype | Shape |
|---|---|---|---|
| `log_e_film` | `numpy.ndarray` | `float64` | `[384, 512, 3]` |
| `cmy_film` | `numpy.ndarray` | `float64` | `[384, 512, 3]` |
| `log_e_print` | `numpy.ndarray` | `float64` | `[384, 512, 3]` |
| `cmy_print` | `numpy.ndarray` | `float64` | `[384, 512, 3]` |
| `rgb_out` | `numpy.ndarray` | `float64` | `[384, 512, 3]` |

### mlx_backend

| Tap | Type | Dtype | Shape |
|---|---|---|---|
| `log_e_film` | `mlx.core.array` | `mlx.core.float32` | `[384, 512, 3]` |
| `cmy_film` | `mlx.core.array` | `mlx.core.float32` | `[384, 512, 3]` |
| `log_e_print` | `mlx.core.array` | `mlx.core.float32` | `[384, 512, 3]` |
| `cmy_print` | `mlx.core.array` | `mlx.core.float32` | `[384, 512, 3]` |
| `rgb_out` | `mlx.core.array` | `mlx.core.float32` | `[384, 512, 3]` |

## Notes

- Residency diagnostics are active only inside the timed `process()` call.
- Explicit sync and explicit NumPy conversion happen after diagnostics to avoid classifying validation/export inspection as runtime leakage.
- This is a runtime-boundary diagnostic, not a 12MP RAW performance proof.
