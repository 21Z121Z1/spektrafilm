# Backend Resident Float32 P4 Validation Benchmark - 20260608-211514

## Config

- Backend: `mlx`
- Precision: `float32`
- Runs: `1`
- Warmups: `0`
- Include real: `False`
- Real input: `/Users/retriedstormtrooper/Documents/Projects/Active/spektrafilm-main/scratch/IMG_9121_converted.DNG`

## Results

| Sample | Workload | Backend | Status | Runtime | Total | Sync | Preview | Export | Output | HDR Y | Unallowed to_numpy |
|---|---|---|---|---:|---:|---:|---:|---:|---|---|---:|
| synthetic_256 | runtime_grain_off_hdr_off | mlx | ok | 0.322425s | 0.322425s | 0.079782s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_256 | runtime_grain_off_hdr_on | mlx | ok | 0.050501s | 0.050501s | 0.010846s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | numpy.ndarray float32 | 0 |
| synthetic_256 | runtime_grain_on_hdr_off | mlx | ok | 0.086487s | 0.086487s | 0.037097s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_256 | runtime_grain_on_hdr_on | mlx | ok | 0.076293s | 0.076293s | 0.023542s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | numpy.ndarray float32 | 0 |
| synthetic_256 | preview_only_grain_off_hdr_off | mlx | ok | 0.056233s | 0.057393s | 0.015590s | 0.001160s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_256 | export_only_grain_off_hdr_off | mlx | ok | 0.048181s | 0.048244s | 0.014830s | 0.000000s | 0.000063s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_256 | preview_export_grain_off_hdr_off | mlx | ok | 0.051773s | 0.052385s | 0.013183s | 0.000596s | 0.000016s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_512x384 | runtime_grain_off_hdr_off | mlx | ok | 0.082523s | 0.082523s | 0.045206s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_512x384 | runtime_grain_off_hdr_on | mlx | ok | 0.071621s | 0.071621s | 0.023865s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | numpy.ndarray float32 | 0 |
| synthetic_512x384 | runtime_grain_on_hdr_off | mlx | ok | 0.115967s | 0.115967s | 0.071120s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_512x384 | runtime_grain_on_hdr_on | mlx | ok | 0.114237s | 0.114237s | 0.049882s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | numpy.ndarray float32 | 0 |
| synthetic_512x384 | preview_only_grain_off_hdr_off | mlx | ok | 0.045007s | 0.046995s | 0.014034s | 0.001988s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_512x384 | export_only_grain_off_hdr_off | mlx | ok | 0.056109s | 0.056167s | 0.022815s | 0.000000s | 0.000058s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_512x384 | preview_export_grain_off_hdr_off | mlx | ok | 0.058734s | 0.060267s | 0.028016s | 0.001520s | 0.000014s | mlx.core.array mlx.core.float32 | None None | 0 |
