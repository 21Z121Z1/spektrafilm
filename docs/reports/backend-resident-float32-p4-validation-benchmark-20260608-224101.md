# Backend Resident Float32 P4 Validation Benchmark - 20260608-224101

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
| synthetic_256 | runtime_grain_off_hdr_off | mlx | backend | print_scan | none | ok | 0.418765s | 0.418765s | 0.119387s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_256 | runtime_grain_off_hdr_on | mlx | backend | print_scan | hdr_metadata | ok | 0.062326s | 0.062326s | 0.013736s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | numpy.ndarray float32 | 0 |
| synthetic_256 | runtime_grain_on_hdr_off | mlx | backend | print_scan | grain | ok | 0.111595s | 0.111595s | 0.045476s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_256 | runtime_grain_on_hdr_on | mlx | backend | print_scan | grain,hdr_metadata | ok | 0.093139s | 0.093139s | 0.029321s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | numpy.ndarray float32 | 0 |
| synthetic_256 | runtime_scan_film_grain_off_hdr_off | mlx | backend | scan_film | none | ok | 0.033142s | 0.033142s | 0.009892s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_256 | preview_only_grain_off_hdr_off | mlx | backend | print_scan | preview | ok | 0.062749s | 0.064446s | 0.013381s | 0.001696s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_256 | export_only_grain_off_hdr_off | mlx | backend | print_scan | export | ok | 0.056706s | 0.056778s | 0.011178s | 0.000000s | 0.000072s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_256 | preview_export_grain_off_hdr_off | mlx | backend | print_scan | preview,export | ok | 0.105025s | 0.105597s | 0.016536s | 0.000558s | 0.000014s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_256 | runtime_grain_off_hdr_off_scanner_lut_on | mlx | backend | print_scan | scanner_lut | ok | 0.103057s | 0.103057s | 0.023613s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_512x384 | runtime_grain_off_hdr_off | mlx | backend | print_scan | none | ok | 0.176880s | 0.176880s | 0.053130s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_512x384 | runtime_grain_off_hdr_on | mlx | backend | print_scan | hdr_metadata | ok | 0.197829s | 0.197829s | 0.056637s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | numpy.ndarray float32 | 0 |
| synthetic_512x384 | runtime_grain_on_hdr_off | mlx | backend | print_scan | grain | ok | 0.143398s | 0.143398s | 0.065183s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_512x384 | runtime_grain_on_hdr_on | mlx | backend | print_scan | grain,hdr_metadata | ok | 0.208424s | 0.208424s | 0.073987s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | numpy.ndarray float32 | 0 |
| synthetic_512x384 | runtime_scan_film_grain_off_hdr_off | mlx | backend | scan_film | none | ok | 0.047730s | 0.047730s | 0.013137s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_512x384 | preview_only_grain_off_hdr_off | mlx | backend | print_scan | preview | ok | 0.113748s | 0.116535s | 0.047611s | 0.002787s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_512x384 | export_only_grain_off_hdr_off | mlx | backend | print_scan | export | ok | 0.085508s | 0.085580s | 0.025342s | 0.000000s | 0.000072s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_512x384 | preview_export_grain_off_hdr_off | mlx | backend | print_scan | preview,export | ok | 0.100272s | 0.102605s | 0.045048s | 0.002303s | 0.000029s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_512x384 | runtime_grain_off_hdr_off_scanner_lut_on | mlx | backend | print_scan | scanner_lut | ok | 0.074937s | 0.074937s | 0.019942s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| real_dng | runtime_grain_off_hdr_off | mlx | backend | print_scan | none | ok | 3.534890s | 3.534890s | 3.412934s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| real_dng | runtime_grain_off_hdr_on | mlx | backend | print_scan | hdr_metadata | ok | 5.292735s | 5.292735s | 3.389451s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | numpy.ndarray float32 | 0 |
| real_dng | runtime_grain_on_hdr_off | mlx | backend | print_scan | grain | ok | 55.543663s | 55.543663s | 54.871726s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| real_dng | runtime_scan_film_grain_off_hdr_off | mlx | backend | scan_film | none | ok | 3.220326s | 3.220326s | 0.632622s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| real_dng | preview_export_grain_off_hdr_off | mlx | backend | print_scan | preview,export | ok | 3.395504s | 4.672774s | 3.084911s | 1.277130s | 0.000139s | mlx.core.array mlx.core.float32 | None None | 0 |
| real_dng | runtime_grain_off_hdr_off_scanner_lut_on | mlx | backend | print_scan | scanner_lut | ok | 4.610460s | 4.610460s | 4.278639s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| real_dng | runtime_grain_on_hdr_off_scanner_lut_on | mlx | backend | print_scan | grain,scanner_lut | ok | 48.805941s | 48.805941s | 46.390905s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
