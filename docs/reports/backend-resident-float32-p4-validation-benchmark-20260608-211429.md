# Backend Resident Float32 P4 Validation Benchmark - 20260608-211429

## Config

- Backend: `cpu`
- Precision: `float32`
- Runs: `1`
- Warmups: `0`
- Include real: `False`
- Real input: `/Users/retriedstormtrooper/Documents/Projects/Active/spektrafilm-main/scratch/IMG_9121_converted.DNG`

## Results

| Sample | Workload | Backend | Status | Runtime | Total | Sync | Preview | Export | Output | HDR Y | Unallowed to_numpy |
|---|---|---|---|---:|---:|---:|---:|---:|---|---|---:|
| synthetic_256 | runtime_grain_off_hdr_off | cpu | ok | 0.403900s | 0.403900s | 0.000002s | 0.000000s | 0.000000s | numpy.ndarray float64 | None None | 0 |
| synthetic_256 | runtime_grain_off_hdr_on | cpu | ok | 0.226310s | 0.226310s | 0.000002s | 0.000000s | 0.000000s | numpy.ndarray float64 | numpy.ndarray float32 | 0 |
| synthetic_256 | runtime_grain_on_hdr_off | cpu | ok | 0.244546s | 0.244546s | 0.000002s | 0.000000s | 0.000000s | numpy.ndarray float64 | None None | 0 |
| synthetic_256 | runtime_grain_on_hdr_on | cpu | ok | 0.247329s | 0.247329s | 0.000002s | 0.000000s | 0.000000s | numpy.ndarray float64 | numpy.ndarray float32 | 0 |
| synthetic_256 | preview_only_grain_off_hdr_off | cpu | ok | 0.217607s | 0.218931s | 0.000002s | 0.001324s | 0.000000s | numpy.ndarray float64 | None None | 0 |
| synthetic_256 | export_only_grain_off_hdr_off | cpu | ok | 0.215477s | 0.215579s | 0.000002s | 0.000000s | 0.000102s | numpy.ndarray float64 | None None | 0 |
| synthetic_256 | preview_export_grain_off_hdr_off | cpu | ok | 0.223612s | 0.224278s | 0.000002s | 0.000613s | 0.000052s | numpy.ndarray float64 | None None | 0 |
| synthetic_512x384 | runtime_grain_off_hdr_off | cpu | ok | 0.740106s | 0.740106s | 0.000002s | 0.000000s | 0.000000s | numpy.ndarray float64 | None None | 0 |
| synthetic_512x384 | runtime_grain_off_hdr_on | cpu | ok | 0.640552s | 0.640552s | 0.000002s | 0.000000s | 0.000000s | numpy.ndarray float64 | numpy.ndarray float32 | 0 |
| synthetic_512x384 | runtime_grain_on_hdr_off | cpu | ok | 0.682802s | 0.682802s | 0.000002s | 0.000000s | 0.000000s | numpy.ndarray float64 | None None | 0 |
| synthetic_512x384 | runtime_grain_on_hdr_on | cpu | ok | 0.679174s | 0.679174s | 0.000002s | 0.000000s | 0.000000s | numpy.ndarray float64 | numpy.ndarray float32 | 0 |
| synthetic_512x384 | preview_only_grain_off_hdr_off | cpu | ok | 0.606853s | 0.608433s | 0.000002s | 0.001580s | 0.000000s | numpy.ndarray float64 | None None | 0 |
| synthetic_512x384 | export_only_grain_off_hdr_off | cpu | ok | 0.593032s | 0.593171s | 0.000002s | 0.000000s | 0.000140s | numpy.ndarray float64 | None None | 0 |
| synthetic_512x384 | preview_export_grain_off_hdr_off | cpu | ok | 0.596898s | 0.598528s | 0.000002s | 0.001501s | 0.000129s | numpy.ndarray float64 | None None | 0 |
