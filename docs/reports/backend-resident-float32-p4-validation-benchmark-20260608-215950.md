# Backend Resident Float32 P4 Validation Benchmark - 20260608-215950

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
| synthetic_256 | runtime_grain_off_hdr_off | mlx | backend | print_scan | none | ok | 0.286871s | 0.286871s | 0.049699s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_256 | runtime_grain_off_hdr_on | mlx | backend | print_scan | hdr_metadata | ok | 0.058935s | 0.058935s | 0.017252s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | numpy.ndarray float32 | 0 |
| synthetic_256 | runtime_grain_on_hdr_off | mlx | backend | print_scan | grain | ok | 0.098765s | 0.098765s | 0.048683s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_256 | runtime_grain_on_hdr_on | mlx | backend | print_scan | grain,hdr_metadata | ok | 0.097575s | 0.097575s | 0.029342s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | numpy.ndarray float32 | 0 |
| synthetic_256 | runtime_scan_film_grain_off_hdr_off | mlx | backend | scan_film | none | ok | 0.025862s | 0.025862s | 0.005957s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_256 | preview_only_grain_off_hdr_off | mlx | backend | print_scan | preview | ok | 0.058443s | 0.059835s | 0.012952s | 0.001392s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_256 | export_only_grain_off_hdr_off | mlx | backend | print_scan | export | ok | 0.046155s | 0.046201s | 0.009676s | 0.000000s | 0.000046s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_256 | preview_export_grain_off_hdr_off | mlx | backend | print_scan | preview,export | ok | 0.040553s | 0.041183s | 0.007767s | 0.000615s | 0.000014s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_256 | runtime_grain_off_hdr_off_scanner_lut_on | mlx | backend | print_scan | scanner_lut | ok | 0.049221s | 0.049221s | 0.012644s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_512x384 | runtime_grain_off_hdr_off | mlx | backend | print_scan | none | ok | 0.077569s | 0.077569s | 0.030066s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_512x384 | runtime_grain_off_hdr_on | mlx | backend | print_scan | hdr_metadata | ok | 0.074117s | 0.074117s | 0.026252s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | numpy.ndarray float32 | 0 |
| synthetic_512x384 | runtime_grain_on_hdr_off | mlx | backend | print_scan | grain | ok | 0.161327s | 0.161327s | 0.113357s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_512x384 | runtime_grain_on_hdr_on | mlx | backend | print_scan | grain,hdr_metadata | ok | 0.123074s | 0.123074s | 0.052101s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | numpy.ndarray float32 | 0 |
| synthetic_512x384 | runtime_scan_film_grain_off_hdr_off | mlx | backend | scan_film | none | ok | 0.033355s | 0.033355s | 0.010215s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_512x384 | preview_only_grain_off_hdr_off | mlx | backend | print_scan | preview | ok | 0.057732s | 0.059994s | 0.021913s | 0.002261s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_512x384 | export_only_grain_off_hdr_off | mlx | backend | print_scan | export | ok | 0.059987s | 0.060036s | 0.024383s | 0.000000s | 0.000048s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_512x384 | preview_export_grain_off_hdr_off | mlx | backend | print_scan | preview,export | ok | 0.061595s | 0.063149s | 0.027108s | 0.001536s | 0.000018s | mlx.core.array mlx.core.float32 | None None | 0 |
| synthetic_512x384 | runtime_grain_off_hdr_off_scanner_lut_on | mlx | backend | print_scan | scanner_lut | ok | 0.061996s | 0.061996s | 0.028712s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| real_dng | runtime_grain_off_hdr_off | mlx | backend | print_scan | none | ok | 3.973058s | 3.973058s | 3.803326s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| real_dng | runtime_grain_off_hdr_on | mlx | backend | print_scan | hdr_metadata | ok | 5.291137s | 5.291137s | 2.865405s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | numpy.ndarray float32 | 0 |
| real_dng | runtime_grain_on_hdr_off | mlx | backend | print_scan | grain | ok | 79.132910s | 79.132910s | 77.968661s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| real_dng | runtime_scan_film_grain_off_hdr_off | mlx | backend | scan_film | none | ok | 3.367730s | 3.367730s | 0.506578s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| real_dng | preview_export_grain_off_hdr_off | mlx | backend | print_scan | preview,export | ok | 2.044055s | 3.068667s | 1.960935s | 1.024471s | 0.000141s | mlx.core.array mlx.core.float32 | None None | 0 |
| real_dng | runtime_grain_off_hdr_off_scanner_lut_on | mlx | backend | print_scan | scanner_lut | ok | 2.342079s | 2.342079s | 2.157087s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
| real_dng | runtime_grain_on_hdr_off_scanner_lut_on | mlx | backend | print_scan | grain,scanner_lut | ok | 52.226787s | 52.226787s | 51.785288s | 0.000000s | 0.000000s | mlx.core.array mlx.core.float32 | None None | 0 |
