# Backend Resident Float32 P4 Validation Benchmark - 20260608-211653

## Config

- Backend: `mlx`
- Precision: `float32`
- Runs: `1`
- Warmups: `0`
- Include real: `True`
- Real input: `scratch/IMG_9121_converted.DNG`

## Results

| Sample | Workload | Backend | Status | Runtime | Total | Sync | Preview | Export | Output | HDR Y | Unallowed to_numpy |
|---|---|---|---|---:|---:|---:|---:|---:|---|---|---:|
| synthetic_256 | runtime_grain_off_hdr_off | mlx | ok | 0.321682s | 0.321682s | 0.086475s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_256 | runtime_grain_off_hdr_on | mlx | ok | 0.061984s | 0.061984s | 0.018127s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | numpy.ndarray float32 | 0 |
| synthetic_256 | runtime_grain_on_hdr_off | mlx | ok | 0.092767s | 0.092767s | 0.038915s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_256 | runtime_grain_on_hdr_on | mlx | ok | 0.092905s | 0.092905s | 0.037408s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | numpy.ndarray float32 | 0 |
| synthetic_256 | preview_only_grain_off_hdr_off | mlx | ok | 0.043369s | 0.044663s | 0.006964s | 0.001295s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_256 | export_only_grain_off_hdr_off | mlx | ok | 0.058239s | 0.058293s | 0.015777s | 0.000000s | 0.000054s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_256 | preview_export_grain_off_hdr_off | mlx | ok | 0.042867s | 0.043498s | 0.005928s | 0.000614s | 0.000017s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_512x384 | runtime_grain_off_hdr_off | mlx | ok | 0.077223s | 0.077223s | 0.040294s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_512x384 | runtime_grain_off_hdr_on | mlx | ok | 0.085733s | 0.085733s | 0.031597s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | numpy.ndarray float32 | 0 |
| synthetic_512x384 | runtime_grain_on_hdr_off | mlx | ok | 0.180054s | 0.180054s | 0.131355s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_512x384 | runtime_grain_on_hdr_on | mlx | ok | 0.126962s | 0.126962s | 0.063349s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | numpy.ndarray float32 | 0 |
| synthetic_512x384 | preview_only_grain_off_hdr_off | mlx | ok | 0.054567s | 0.056623s | 0.015930s | 0.002056s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_512x384 | export_only_grain_off_hdr_off | mlx | ok | 0.061909s | 0.061957s | 0.024403s | 0.000000s | 0.000048s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_512x384 | preview_export_grain_off_hdr_off | mlx | ok | 0.076080s | 0.077933s | 0.032113s | 0.001835s | 0.000018s | mlx.core.array mlx.core.float32 | None None | 0 |
| real_dng | runtime_grain_off_hdr_off | mlx | ok | 0.055293s | 0.055293s | 0.011770s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| real_dng | runtime_grain_off_hdr_on | mlx | ok | 0.052970s | 0.052970s | 0.006115s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | numpy.ndarray float32 | 0 |
| real_dng | runtime_grain_on_hdr_off | mlx | ok | 0.100699s | 0.100699s | 0.043298s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| real_dng | preview_export_grain_off_hdr_off | mlx | ok | 0.047049s | 0.047591s | 0.006565s | 0.000524s | 0.000018s | mlx.core.array mlx.core.float32 | None None | 0 |
