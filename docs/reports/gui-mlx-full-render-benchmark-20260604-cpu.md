# GUI MLX Full Render Benchmark - 20260604-143245

- Status: `ok`
- Backend: `cpu`
- Precision: `float64`
- Input shape: `[384, 512, 3]`
- Input dtype: `float32`
- Input nbytes: `2359296`

## Wall Time

| Metric | Seconds |
|---|---:|
| median | 0.657018 |
| min | 0.548733 |
| max | 0.981479 |

## GUI Phase Timings

| Phase | Median | Min | Max |
|---|---:|---:|---:|
| gui.display_prepare | 0.001228 | 0.001193 | 0.003646 |
| gui.display_uint8 | 0.001216 | 0.001172 | 0.003609 |
| gui.float_materialize | 0.000000 | 0.000000 | 0.000000 |
| gui.input_copy | 0.000121 | 0.000111 | 0.011131 |
| gui.input_dtype_convert | 0.000121 | 0.000111 | 0.011131 |
| gui.input_prepare | 0.000124 | 0.000113 | 0.011146 |
| gui.worker_total | 0.656636 | 0.548691 | 0.981449 |
| runtime.process | 0.652957 | 0.547452 | 0.980242 |

## Last Run Runtime Stages

| Stage | Seconds |
|---|---:|
| FilmingStage.auto_exposure | 0.000004 |
| preprocess | 0.000488 |
| SpectralLUTService.get_filming_tc_lut | 0.000145 |
| filming.expose | 0.222525 |
| filming.develop | 0.088762 |
| SpectralLUTService.spectral_compute_enlarger | 0.031508 |
| PrintingStage.expose | 0.050397 |
| printing.expose | 0.050411 |
| PrintingStage.develop | 0.010078 |
| printing.develop | 0.010177 |
| SpectralLUTService.spectral_compute_scanner | 0.033380 |
| ScanningStage.scan | 0.175034 |
| scanning.scan_print | 0.175044 |
| SimulationPipeline.materialize | 0.000002 |

## Last Run Memory Estimates

| Key | Bytes |
|---|---:|
| gui.input_source_nbytes | 2359296 |
| gui.input_request_nbytes | 4718592 |
| gui.input_copy_nbytes | 4718592 |
| gui.float_materialize_copy_nbytes | 0 |
| gui.float_image_nbytes | 4718592 |
| gui.display_image_nbytes | 589824 |
| gui.hdr_scene_luminance_nbytes | 0 |
| gui.hdr_scene_rgb_nbytes | 0 |
