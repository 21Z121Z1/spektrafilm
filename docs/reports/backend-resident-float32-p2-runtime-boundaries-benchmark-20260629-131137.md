# Backend Resident Float32 P2 Runtime Boundaries - 20260629-131137

- Image shape: `[96, 128, 3]`
- Warmups: `0`
- Runs: `1`
- Scanner LUT: `False`

## Summary

| Case | Status | Output | Median Runtime | Sync | Explicit NumPy | Peak Memory | Unallowed to_numpy | Max Abs Diff vs CPU | Max Abs Diff vs CPU Direct |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| cpu_default | ok | numpy.ndarray float64 | 0.030827s | 0.000001s | 0.000001s | n/a | 0 | 0 | 0 |
| mlx_backend | ok | mlx.core.array mlx.core.float32 | 0.030863s | 0.000221s | 0.024651s | 0.8 MiB | 0 | 5.06071e-06 | 5.06071e-06 |

## Stage Trace

### cpu_default

| Tap | Type | Dtype | Shape |
|---|---|---|---|
| `log_e_film` | `numpy.ndarray` | `float64` | `[96, 128, 3]` |
| `cmy_film` | `numpy.ndarray` | `float64` | `[96, 128, 3]` |
| `log_e_print` | `numpy.ndarray` | `float64` | `[96, 128, 3]` |
| `cmy_print` | `numpy.ndarray` | `float64` | `[96, 128, 3]` |
| `rgb_out` | `numpy.ndarray` | `float64` | `[96, 128, 3]` |

### mlx_backend

| Tap | Type | Dtype | Shape |
|---|---|---|---|
| `log_e_film` | `mlx.core.array` | `mlx.core.float32` | `[96, 128, 3]` |
| `cmy_film` | `mlx.core.array` | `mlx.core.float32` | `[96, 128, 3]` |
| `log_e_print` | `mlx.core.array` | `mlx.core.float32` | `[96, 128, 3]` |
| `cmy_print` | `mlx.core.array` | `mlx.core.float32` | `[96, 128, 3]` |
| `rgb_out` | `mlx.core.array` | `mlx.core.float32` | `[96, 128, 3]` |

## Notes

- Residency diagnostics cover the timed `process()` call and the explicit post-process sync.
- Explicit NumPy conversion happens after diagnostics to avoid classifying validation/export inspection as runtime leakage.
- This is a runtime-boundary diagnostic, not a 12MP RAW performance proof.
