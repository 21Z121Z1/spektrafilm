# GUI MLX Full Render Benchmark - 20260604-143312

- Status: `ok`
- Backend: `mlx`
- Precision: `float32`
- Input shape: `[384, 512, 3]`
- Input dtype: `float32`
- Input nbytes: `2359296`

## Wall Time

| Metric | Seconds |
|---|---:|
| median | 0.076036 |
| min | 0.059970 |
| max | 0.085732 |

## GUI Phase Timings

| Phase | Median | Min | Max |
|---|---:|---:|---:|
| gui.display_prepare | 0.001209 | 0.001205 | 0.001316 |
| gui.display_uint8 | 0.001194 | 0.001189 | 0.001299 |
| gui.float_materialize | 0.000002 | 0.000002 | 0.000002 |
| gui.input_copy | 0.000000 | 0.000000 | 0.000000 |
| gui.input_dtype_convert | 0.000003 | 0.000003 | 0.000004 |
| gui.input_prepare | 0.000008 | 0.000008 | 0.000009 |
| gui.worker_total | 0.076009 | 0.059931 | 0.085705 |
| runtime.process | 0.074786 | 0.058710 | 0.084375 |

## Last Run Runtime Stages

| Stage | Seconds |
|---|---:|
| preprocess | 0.000238 |
| SpectralLUTService.get_filming_tc_lut | 0.000010 |
| SpectralLUTService.get_filming_tc_lut_backend | 0.000331 |
| filming.expose | 0.034977 |
| filming.develop | 0.013626 |
| PrintingStage.expose | 0.013397 |
| printing.expose | 0.013403 |
| PrintingStage.develop | 0.000440 |
| printing.develop | 0.000442 |
| SpectralLUTService.spectral_compute_scanner | 0.001124 |
| ScanningStage.scan | 0.002484 |
| scanning.scan_print | 0.002505 |
| SimulationPipeline.materialize | 0.019137 |

## Last Run Memory Estimates

| Key | Bytes |
|---|---:|
| gui.input_source_nbytes | 2359296 |
| gui.input_request_nbytes | 2359296 |
| gui.input_copy_nbytes | 0 |
| gui.float_materialize_copy_nbytes | 0 |
| gui.float_image_nbytes | 4718592 |
| gui.display_image_nbytes | 589824 |
| gui.hdr_scene_luminance_nbytes | 0 |
| gui.hdr_scene_rgb_nbytes | 0 |
