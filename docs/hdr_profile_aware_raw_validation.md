# Profile-Aware HDR ProRAW Validation

Command: `uv run python tools/validate_profile_aware_hdr_raw_samples.py --sample-dir "/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片/RAW_DNG_JPEG_批量导出" --max-samples 4 --output docs/hdr_profile_aware_raw_validation.md`
Sample directory: `/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片/RAW_DNG_JPEG_批量导出`
Discovered DNG files: 365
DNG files inspected for selection diagnostics: 32

## Selected Samples

| File | Reason | Dimensions | Paired exports |
| --- | --- | ---: | --- |
| IMG_1476_converted.DNG | normal_or_balanced_exposure | 4032x3024 | IMG_1476_preview.jpg |
| IMG_0847_converted.DNG | low_key_or_darkest_sensor_median | 4032x3024 | IMG_0847_preview.jpg |
| IMG_9071_converted.DNG | bright_highlight_sensor_p999 | 4032x3024 | none found |
| IMG_9131_converted.DNG | most_clipped_or_near_white_sensor_values | 4032x3024 | none found |

## RAW Diagnostics

| File | rawpy min/max/p50/p99/p999 | rawpy clip | sensor max/p99/p999 | diffuse white | headroom | confidence |
| --- | --- | ---: | --- | ---: | ---: | --- |
| IMG_1476_converted.DNG | 0.0044/0.9956/0.0147/0.1768/0.3873 | 0.00000 | 1.000/0.153/0.335 | 0.1768 | 2.191 | auto_percentile / medium |
| IMG_0847_converted.DNG | 0.0000/1.0000/0.0006/0.0890/0.5480 | 0.00000 | 1.000/0.064/0.329 | 0.1000 | 5.480 | auto_floor_low_key / low |
| IMG_9071_converted.DNG | 0.0000/1.0000/0.0043/0.4372/1.0000 | 0.00163 | 1.057/0.233/1.000 | 0.4372 | 2.287 | auto_percentile / medium |
| IMG_9131_converted.DNG | 0.0000/1.0000/0.0040/0.7654/1.0000 | 0.00171 | 1.009/0.492/1.000 | 0.7654 | 1.306 | auto_percentile / medium |

## Sidecar And SDR Preservation

| File | validation shape | sidecar shape | finite nonnegative | process vs metadata max abs | auto exposure direction |
| --- | --- | --- | ---: | ---: | ---: |
| IMG_1476_converted.DNG | [576, 768, 3] | [576, 768] | True | 0.000e+00 | True |
| IMG_0847_converted.DNG | [576, 768, 3] | [576, 768] | True | 0.000e+00 | True |
| IMG_9071_converted.DNG | [576, 768, 3] | [576, 768] | True | 0.000e+00 | True |
| IMG_9131_converted.DNG | [768, 576, 3] | [768, 576] | True | 0.000e+00 | True |

## HDR Rendition And Curve Conformance

| File | headroom | SDR RMSE vs S_profile | HDR RMSE vs H_profile | highlight separation ratio | max log-gain jump | HDR highlight span > look |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| IMG_1476_converted.DNG | 3.163 | 0.0000 | 0.0182 | 19.381 | 0.247 | True |
| IMG_0847_converted.DNG | 4.609 | 0.0005 | 0.0002 | 29.079 | 0.273 | True |
| IMG_9071_converted.DNG | 4.601 | 0.0001 | 0.0000 | 28.732 | 0.271 | True |
| IMG_9131_converted.DNG | 4.104 | 0.0000 | 0.0000 | 26.176 | 0.263 | True |

## Fallback Cases

| File | missing sidecar | unsafe profile fallback | missing profile fallback | low-confidence RAW white |
| --- | ---: | ---: | ---: | ---: |
| IMG_1476_converted.DNG | True | True | True | False |
| IMG_0847_converted.DNG | True | True | True | True |
| IMG_9071_converted.DNG | True | True | True | False |
| IMG_9131_converted.DNG | True | True | True | False |

## Limitations

- Runtime validation uses a bounded downsampled RGB array for speed; RAW diagnostics come from the full DNG decode.
- Real-image curve conformance is statistical because chroma, texture, glare, grain, and gamut compression prevent exact per-pixel curve matching.
- SDR preservation is checked as `Simulator.process()` vs `Simulator.process_with_metadata()` on the same RAW-derived validation array; historical pre-change arrays are not available in this script.

Machine-readable diagnostics: `docs/hdr_profile_aware_raw_validation.json`
