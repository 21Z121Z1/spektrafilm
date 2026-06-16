# Backend Resident Float32 P4 Validation Benchmark - 20260608-211737

## Config

- Backend: `cpu`
- Precision: `float32`
- Runs: `1`
- Warmups: `0`
- Include real: `True`
- Real input: `scratch/IMG_9121_converted.DNG`

## Results

| Sample | Workload | Backend | Status | Runtime | Total | Sync | Preview | Export | Output | HDR Y | Unallowed to_numpy |
|---|---|---|---|---:|---:|---:|---:|---:|---|---|---:|
| synthetic_256 | runtime_grain_off_hdr_off | cpu | ok | 0.419432s | 0.419432s | 0.000002s | 0.000000s | 0.000000s | numpy.ndarray float64 | None None | 0 |
| synthetic_256 | runtime_grain_off_hdr_on | cpu | ok | 0.221523s | 0.221523s | 0.000002s | 0.000000s | 0.000000s | numpy.ndarray float64 | numpy.ndarray float32 | 0 |
| synthetic_256 | runtime_grain_on_hdr_off | cpu | ok | 0.244923s | 0.244923s | 0.000002s | 0.000000s | 0.000000s | numpy.ndarray float64 | None None | 0 |
| synthetic_256 | runtime_grain_on_hdr_on | cpu | ok | 0.246836s | 0.246836s | 0.000002s | 0.000000s | 0.000000s | numpy.ndarray float64 | numpy.ndarray float32 | 0 |
| synthetic_256 | preview_only_grain_off_hdr_off | cpu | ok | 0.216681s | 0.218219s | 0.000002s | 0.001538s | 0.000000s | numpy.ndarray float64 | None None | 0 |
| synthetic_256 | export_only_grain_off_hdr_off | cpu | ok | 0.209868s | 0.209939s | 0.000002s | 0.000000s | 0.000071s | numpy.ndarray float64 | None None | 0 |
| synthetic_256 | preview_export_grain_off_hdr_off | cpu | ok | 0.212531s | 0.213093s | 0.000002s | 0.000516s | 0.000046s | numpy.ndarray float64 | None None | 0 |
| synthetic_512x384 | runtime_grain_off_hdr_off | cpu | ok | 0.707039s | 0.707039s | 0.000002s | 0.000000s | 0.000000s | numpy.ndarray float64 | None None | 0 |
| synthetic_512x384 | runtime_grain_off_hdr_on | cpu | ok | 0.609148s | 0.609148s | 0.000002s | 0.000000s | 0.000000s | numpy.ndarray float64 | numpy.ndarray float32 | 0 |
| synthetic_512x384 | runtime_grain_on_hdr_off | cpu | ok | 0.665245s | 0.665245s | 0.000002s | 0.000000s | 0.000000s | numpy.ndarray float64 | None None | 0 |
| synthetic_512x384 | runtime_grain_on_hdr_on | cpu | ok | 0.703715s | 0.703715s | 0.000003s | 0.000000s | 0.000000s | numpy.ndarray float64 | numpy.ndarray float32 | 0 |
| synthetic_512x384 | preview_only_grain_off_hdr_off | cpu | ok | 0.593999s | 0.595462s | 0.000002s | 0.001463s | 0.000000s | numpy.ndarray float64 | None None | 0 |
| synthetic_512x384 | export_only_grain_off_hdr_off | cpu | ok | 0.592590s | 0.592790s | 0.000034s | 0.000000s | 0.000200s | numpy.ndarray float64 | None None | 0 |
| synthetic_512x384 | preview_export_grain_off_hdr_off | cpu | ok | 0.730629s | 0.733942s | 0.000002s | 0.002011s | 0.001302s | numpy.ndarray float64 | None None | 0 |
| real_dng | runtime_grain_off_hdr_off | cpu | ok | 0.214301s | 0.214301s | 0.000002s | 0.000000s | 0.000000s | numpy.ndarray float64 | None None | 0 |
| real_dng | runtime_grain_off_hdr_on | cpu | ok | 0.173839s | 0.173839s | 0.000002s | 0.000000s | 0.000000s | numpy.ndarray float64 | numpy.ndarray float32 | 0 |
| real_dng | runtime_grain_on_hdr_off | cpu | ok | 0.186612s | 0.186612s | 0.000002s | 0.000000s | 0.000000s | numpy.ndarray float64 | None None | 0 |
| real_dng | preview_export_grain_off_hdr_off | cpu | ok | 0.175512s | 0.175964s | 0.000001s | 0.000405s | 0.000047s | numpy.ndarray float64 | None None | 0 |
