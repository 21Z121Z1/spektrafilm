# GUI MLX Full Render Benchmark - 20260605-134640

- Status: `ok`
- Backend: `mlx`
- Precision: `float32`
- Input shape: `[384, 512, 3]`
- Input dtype: `float32`
- Input nbytes: `2359296`

## Wall Time

| Metric | Seconds |
|---|---:|
| median | 0.191702 |
| min | 0.186486 |
| max | 0.197510 |

## GUI Phase Timings

| Phase | Median | Min | Max |
|---|---:|---:|---:|
| gui.display_prepare | 0.001207 | 0.001143 | 0.001435 |
| gui.display_uint8 | 0.001195 | 0.001133 | 0.001422 |
| gui.float_materialize | 0.000001 | 0.000001 | 0.000001 |
| gui.input_copy | 0.000000 | 0.000000 | 0.000000 |
| gui.input_dtype_convert | 0.000003 | 0.000003 | 0.000003 |
| gui.input_prepare | 0.000007 | 0.000007 | 0.000010 |
| gui.worker_total | 0.191672 | 0.186463 | 0.197486 |
| runtime.process | 0.190225 | 0.185243 | 0.196330 |

## Last Run Runtime Stages

| Stage | Seconds |
|---|---:|
| preprocess | 0.000253 |
| SpectralLUTService.get_filming_tc_lut | 0.000019 |
| SpectralLUTService.get_filming_tc_lut_backend | 0.000347 |
| filming.expose | 0.165500 |
| filming.develop | 0.012485 |
| PrintingStage.expose | 0.004169 |
| printing.expose | 0.004172 |
| PrintingStage.develop | 0.000373 |
| printing.develop | 0.000374 |
| SpectralLUTService.spectral_compute_scanner | 0.000731 |
| ScanningStage.scan | 0.001664 |
| scanning.scan_print | 0.001667 |
| SimulationPipeline.materialize | 0.011842 |

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
