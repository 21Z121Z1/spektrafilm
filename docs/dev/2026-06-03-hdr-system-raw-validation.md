# Profile-Aware HDR ProRAW Validation

Command: `uv run python tools/validate_profile_aware_hdr_raw_samples.py --sample-dir "/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片/RAW_DNG_JPEG_批量导出" --max-samples 4 --output docs/dev/2026-06-03-hdr-system-raw-validation.md --diagnostic-scan-limit 32`
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
| IMG_1476_converted.DNG | 0.0000/0.9956/0.0143/0.1659/0.3705 | 0.00000 | 1.000/0.153/0.335 | 0.1659 | 2.234 | postprocess_percentile / medium |
| IMG_0847_converted.DNG | 0.0000/1.0000/0.0005/0.0783/0.4388 | 0.00000 | 1.000/0.064/0.329 | 0.1000 | 4.388 | postprocess_percentile / low |
| IMG_9071_converted.DNG | 0.0000/1.0000/0.0035/0.3407/1.0000 | 0.00236 | 1.057/0.233/1.000 | 0.3407 | 2.935 | postprocess_percentile / medium |
| IMG_9131_converted.DNG | 0.0000/1.0000/0.0033/0.6225/1.0000 | 0.00207 | 1.009/0.492/1.000 | 0.6225 | 1.606 | postprocess_percentile / medium |

## Sidecar And SDR Preservation

| File | validation shape | sidecar shape | finite nonnegative | process vs metadata max abs | auto exposure scale invariant |
| --- | --- | --- | ---: | ---: | ---: |
| IMG_1476_converted.DNG | [576, 768, 3] | [576, 768] | True | 2.980e-08 | True |
| IMG_0847_converted.DNG | [576, 768, 3] | [576, 768] | True | 2.980e-08 | True |
| IMG_9071_converted.DNG | [576, 768, 3] | [576, 768] | True | 2.980e-08 | True |
| IMG_9131_converted.DNG | [768, 576, 3] | [768, 576] | True | 2.980e-08 | True |

## HDR Rendition And Curve Conformance

| File | headroom | SDR RMSE vs S_profile | HDR RMSE vs H_profile | highlight separation ratio | max log-gain jump | HDR highlight span > look |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| IMG_1476_converted.DNG | 1.094 | 0.0190 | 0.0539 | 4.193 | 0.114 | False |
| IMG_0847_converted.DNG | 1.362 | 0.0172 | 0.1993 | 6.419 | 0.110 | True |
| IMG_9071_converted.DNG | 1.379 | 0.0153 | 0.2593 | 5.684 | 0.132 | True |
| IMG_9131_converted.DNG | 1.222 | 0.0277 | 0.1316 | 2.735 | 0.105 | True |

## Gain-Map And EXR Metadata Checks

| File | Android container | ISO metadata roundtrip | ISO gain-map warnings | JPEG probe metadata | JPEG probe gain map | EXR attributes tracked |
| --- | ---: | ---: | --- | ---: | ---: | --- |
| IMG_1476_converted.DNG | True | True | none | True | True | chromaticities, colorInteropID, oiio:ColorSpace, whiteLuminance, hdrHeadroom |
| IMG_0847_converted.DNG | True | True | none | True | True | chromaticities, colorInteropID, oiio:ColorSpace, whiteLuminance, hdrHeadroom |
| IMG_9071_converted.DNG | True | True | none | True | True | chromaticities, colorInteropID, oiio:ColorSpace, whiteLuminance, hdrHeadroom |
| IMG_9131_converted.DNG | True | True | none | True | True | chromaticities, colorInteropID, oiio:ColorSpace, whiteLuminance, hdrHeadroom |

## Fallback Cases

| File | missing sidecar | unsafe profile fallback | unsafe profile rejected | missing profile fallback | missing profile rejected | low-confidence RAW white |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| IMG_1476_converted.DNG | True | False | True | False | True | False |
| IMG_0847_converted.DNG | True | False | True | False | True | True |
| IMG_9071_converted.DNG | True | False | True | False | True | False |
| IMG_9131_converted.DNG | True | False | True | False | True | False |

## Limitations

- Runtime validation uses a bounded downsampled RGB array for speed; RAW diagnostics come from the full DNG decode.
- Real-image curve conformance is statistical because chroma, texture, glare, grain, and gamut compression prevent exact per-pixel curve matching.
- SDR preservation is checked as `Simulator.process()` vs `Simulator.process_with_metadata()` on the same RAW-derived validation array; historical pre-change arrays are not available in this script.

Machine-readable diagnostics: `docs/dev/2026-06-03-hdr-system-raw-validation.json`
