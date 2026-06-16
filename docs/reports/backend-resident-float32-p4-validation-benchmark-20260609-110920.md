# Backend Resident Float32 P4 Validation Benchmark - 20260609-110920

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
| synthetic_256 | runtime_grain_off_hdr_off | mlx | backend | print_scan | none | ok | 0.190227s | 0.190227s | 0.015792s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_256 | runtime_grain_off_hdr_on | mlx | backend | print_scan | hdr_metadata | ok | 0.039031s | 0.039031s | 0.008830s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | numpy.ndarray float32 | 0 |
| synthetic_256 | runtime_grain_on_hdr_off | mlx | backend | print_scan | grain | ok | 0.071134s | 0.071134s | 0.032834s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_256 | runtime_grain_on_hdr_on | mlx | backend | print_scan | grain,hdr_metadata | ok | 0.068551s | 0.068551s | 0.027814s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | numpy.ndarray float32 | 0 |
| synthetic_256 | runtime_scan_film_grain_off_hdr_off | mlx | backend | scan_film | none | ok | 0.017309s | 0.017309s | 0.002675s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_256 | preview_only_grain_off_hdr_off | mlx | backend | print_scan | preview | ok | 0.034565s | 0.035621s | 0.004505s | 0.001056s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_256 | export_only_grain_off_hdr_off | mlx | backend | print_scan | export | ok | 0.053912s | 0.053968s | 0.023942s | 0.000000s | 0.000056s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_256 | preview_export_grain_off_hdr_off | mlx | backend | print_scan | preview,export | ok | 0.028757s | 0.029256s | 0.003731s | 0.000485s | 0.000013s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_256 | runtime_grain_off_hdr_off_scanner_lut_on | mlx | backend | print_scan | scanner_lut | ok | 0.035869s | 0.035869s | 0.008130s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_512x384 | runtime_grain_off_hdr_off | mlx | backend | print_scan | none | ok | 0.050785s | 0.050785s | 0.024806s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_512x384 | runtime_grain_off_hdr_on | mlx | backend | print_scan | hdr_metadata | ok | 0.062904s | 0.062904s | 0.021457s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | numpy.ndarray float32 | 0 |
| synthetic_512x384 | runtime_grain_on_hdr_off | mlx | backend | print_scan | grain | ok | 0.082829s | 0.082829s | 0.042236s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_512x384 | runtime_grain_on_hdr_on | mlx | backend | print_scan | grain,hdr_metadata | ok | 0.095778s | 0.095778s | 0.043806s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | numpy.ndarray float32 | 0 |
| synthetic_512x384 | runtime_scan_film_grain_off_hdr_off | mlx | backend | scan_film | none | ok | 0.023030s | 0.023030s | 0.009459s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_512x384 | preview_only_grain_off_hdr_off | mlx | backend | print_scan | preview | ok | 0.042614s | 0.044213s | 0.017412s | 0.001599s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_512x384 | export_only_grain_off_hdr_off | mlx | backend | print_scan | export | ok | 0.041271s | 0.041332s | 0.016488s | 0.000000s | 0.000061s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_512x384 | preview_export_grain_off_hdr_off | mlx | backend | print_scan | preview,export | ok | 0.038674s | 0.040152s | 0.013051s | 0.001461s | 0.000016s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_512x384 | runtime_grain_off_hdr_off_scanner_lut_on | mlx | backend | print_scan | scanner_lut | ok | 0.041840s | 0.041840s | 0.014599s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| real_dng | runtime_grain_off_hdr_off | mlx | backend | print_scan | none | ok | 1.601621s | 1.601621s | 1.549984s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| real_dng | runtime_grain_off_hdr_on | mlx | backend | print_scan | hdr_metadata | ok | 3.095386s | 3.095386s | 1.862011s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | numpy.ndarray float32 | 0 |
| real_dng | runtime_grain_on_hdr_off | mlx | backend | print_scan | grain | ok | 9.007377s | 9.007377s | 8.656852s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| real_dng | runtime_scan_film_grain_off_hdr_off | mlx | backend | scan_film | none | ok | 3.403251s | 3.403251s | 0.880695s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| real_dng | preview_export_grain_off_hdr_off | mlx | backend | print_scan | preview,export | ok | 1.588987s | 1.691219s | 1.552951s | 0.102206s | 0.000026s | mlx.core.array mlx.core.float32 | None None | 0 |
| real_dng | runtime_grain_off_hdr_off_scanner_lut_on | mlx | backend | print_scan | scanner_lut | ok | 1.533064s | 1.533064s | 1.499252s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| real_dng | runtime_grain_on_hdr_off_scanner_lut_on | mlx | backend | print_scan | grain,scanner_lut | ok | 9.469362s | 9.469362s | 9.142442s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
