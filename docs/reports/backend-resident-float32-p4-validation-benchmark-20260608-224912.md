# Backend Resident Float32 P4 Validation Benchmark - 20260608-224912

## Config

- Backend: `mlx`
- Precision: `float32`
- Runs: `1`
- Warmups: `0`
- Include real: `True`
- Include scanner LUT workloads: `True`
- Real input: `/Users/retriedstormtrooper/Documents/Projects/Active/spektrafilm-main/scratch/IMG_9121_converted.DNG`

## Results

| Sample | Workload | Backend | Policy | Route | Flags | Status | Runtime | Total | Sync | Preview | Export | Output | HDR Y | Unallowed to_numpy |
|---|---|---|---|---|---|---|---:|---:|---:|---:|---:|---|---|---:|
| synthetic_256 | runtime_grain_off_hdr_off | mlx | backend | print_scan | none | ok | 0.519723s | 0.519723s | 0.306099s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_256 | runtime_grain_off_hdr_on | mlx | backend | print_scan | hdr_metadata | ok | 0.057711s | 0.057711s | 0.015290s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | numpy.ndarray float32 | 0 |
| synthetic_256 | runtime_grain_on_hdr_off | mlx | backend | print_scan | grain | ok | 0.093128s | 0.093128s | 0.032633s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_256 | runtime_grain_on_hdr_on | mlx | backend | print_scan | grain,hdr_metadata | ok | 0.097093s | 0.097093s | 0.036496s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | numpy.ndarray float32 | 0 |
| synthetic_256 | runtime_scan_film_grain_off_hdr_off | mlx | backend | scan_film | none | ok | 0.020523s | 0.020523s | 0.003526s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_256 | preview_only_grain_off_hdr_off | mlx | backend | print_scan | preview | ok | 0.049607s | 0.050793s | 0.009965s | 0.001187s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_256 | export_only_grain_off_hdr_off | mlx | backend | print_scan | export | ok | 0.050747s | 0.050802s | 0.011918s | 0.000000s | 0.000055s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_256 | preview_export_grain_off_hdr_off | mlx | backend | print_scan | preview,export | ok | 0.058488s | 0.059048s | 0.022594s | 0.000544s | 0.000016s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_256 | runtime_grain_off_hdr_off_scanner_lut_on | mlx | backend | print_scan | scanner_lut | ok | 0.061488s | 0.061488s | 0.026999s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_512x384 | runtime_grain_off_hdr_off | mlx | backend | print_scan | none | ok | 0.079633s | 0.079633s | 0.036495s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_512x384 | runtime_grain_off_hdr_on | mlx | backend | print_scan | hdr_metadata | ok | 0.088161s | 0.088161s | 0.029995s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | numpy.ndarray float32 | 0 |
| synthetic_512x384 | runtime_grain_on_hdr_off | mlx | backend | print_scan | grain | ok | 0.115273s | 0.115273s | 0.066387s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_512x384 | runtime_grain_on_hdr_on | mlx | backend | print_scan | grain,hdr_metadata | ok | 0.114614s | 0.114614s | 0.047906s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | numpy.ndarray float32 | 0 |
| synthetic_512x384 | runtime_scan_film_grain_off_hdr_off | mlx | backend | scan_film | none | ok | 0.033535s | 0.033535s | 0.014069s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_512x384 | preview_only_grain_off_hdr_off | mlx | backend | print_scan | preview | ok | 0.068431s | 0.070408s | 0.028593s | 0.001977s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_512x384 | export_only_grain_off_hdr_off | mlx | backend | print_scan | export | ok | 0.074009s | 0.074092s | 0.033429s | 0.000000s | 0.000084s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_512x384 | preview_export_grain_off_hdr_off | mlx | backend | print_scan | preview,export | ok | 0.078515s | 0.080456s | 0.032547s | 0.001922s | 0.000019s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_512x384 | runtime_grain_off_hdr_off_scanner_lut_on | mlx | backend | print_scan | scanner_lut | ok | 0.074405s | 0.074405s | 0.029059s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| real_dng | runtime_grain_off_hdr_off | mlx | backend | print_scan | none | ok | 3.010776s | 3.010776s | 2.912074s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| real_dng | runtime_grain_off_hdr_on | mlx | backend | print_scan | hdr_metadata | ok | 4.959268s | 4.959268s | 2.862372s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | numpy.ndarray float32 | 0 |
| real_dng | runtime_grain_on_hdr_off | mlx | backend | print_scan | grain | ok | 19.226032s | 19.226032s | 18.513333s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| real_dng | runtime_scan_film_grain_off_hdr_off | mlx | backend | scan_film | none | ok | 3.247695s | 3.247695s | 0.559148s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| real_dng | preview_export_grain_off_hdr_off | mlx | backend | print_scan | preview,export | ok | 1.121304s | 1.300983s | 1.049818s | 0.179637s | 0.000042s | mlx.core.array mlx.core.float32 | None None | 0 |
| real_dng | runtime_grain_off_hdr_off_scanner_lut_on | mlx | backend | print_scan | scanner_lut | ok | 1.641400s | 1.641400s | 1.592215s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| real_dng | runtime_grain_on_hdr_off_scanner_lut_on | mlx | backend | print_scan | grain,scanner_lut | ok | 33.272084s | 33.272084s | 32.972331s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
