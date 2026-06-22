# MLX Spectral Fused Kernel Baseline + Raw Pixel-Thread v1

- Suite: mlx_spectral_fused_baseline
- Seed: 20260619
- Status: ok

## Recommendation

- accept_raw_pixel_thread_v1: `True`
- replace_production_recommended: `True`
- Reason: accepted: pixel-thread v1 preserves channel-thread baseline output and materially improves a meaningful full-render contributor
- Raw wall share: 16.30%
- Max raw/xyz fused median ratio: 1.333x
- Median speedup raw pixel-thread v1: 2.505x
- P90 speedup raw pixel-thread v1: 2.337x
- Peak memory ratio raw pixel-thread v1: 1.000x
- Max diff raw pixel-thread v1 vs channel-thread baseline: 0.000e+00

## Kernel Microbenchmarks

### preview_256x256

- Image: 256x256x3 float32
- Profiles: kodak_portra_400 -> kodak_portra_endura
- Spectral length K: 81
- Compile/setup excluded: True
- Static table conversion excluded: True
- NumPy reference computed: True
- Warmup: 3
- Runs: 10

#### cmy_to_log_raw

| Path | Median | P90 | Min | Max | Peak memory | Speedup vs current | Max diff vs NumPy | Mean diff vs NumPy | Max diff vs unfused | Mean diff vs unfused | Max diff vs current | Mean diff vs current |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cmy_to_log_raw_unfused_backend_chain | 2.471 ms | 2.811 ms | 1.451 ms | 3.192 ms | 26.3 MiB | 0.380x | 1.788e-07 | 2.678e-08 | 0.000e+00 | 0.000e+00 | 2.384e-07 | 2.810e-08 |
| cmy_to_log_raw_channel_thread_baseline | 2.069 ms | 2.146 ms | 1.968 ms | 2.156 ms | 6.0 MiB | 0.454x | 2.384e-07 | 3.747e-08 | 2.384e-07 | 2.810e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_v1 | 0.939 ms | 1.003 ms | 0.889 ms | 1.139 ms | 6.0 MiB | 1.000x | 2.384e-07 | 3.747e-08 | 2.384e-07 | 2.810e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_v1_tg64 | 0.923 ms | 1.002 ms | 0.886 ms | 1.012 ms | 6.0 MiB | 1.018x | 2.384e-07 | 3.747e-08 | 2.384e-07 | 2.810e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_v1_tg128 | 0.908 ms | 1.055 ms | 0.881 ms | 1.078 ms | 6.0 MiB | 1.034x | 2.384e-07 | 3.747e-08 | 2.384e-07 | 2.810e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_v1_tg512 | 0.926 ms | 0.949 ms | 0.884 ms | 0.953 ms | 6.0 MiB | 1.015x | 2.384e-07 | 3.747e-08 | 2.384e-07 | 2.810e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_k_template | 0.890 ms | 1.006 ms | 0.866 ms | 1.012 ms | 6.0 MiB | 1.056x | 2.384e-07 | 3.747e-08 | 2.384e-07 | 2.810e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_table_cache | 0.653 ms | 0.709 ms | 0.609 ms | 0.803 ms | 6.0 MiB | 1.437x | 2.384e-07 | 3.747e-08 | 2.384e-07 | 2.810e-08 | 0.000e+00 | 0.000e+00 |

- Median speedup fused vs unfused: 2.631x
- Median speedup raw pixel-thread v1 vs current: 2.202x
- P90 speedup raw pixel-thread v1 vs current: 2.139x
- Peak memory ratio raw pixel-thread v1 vs current: 1.000x

#### cmy_to_log_xyz

| Path | Median | P90 | Min | Max | Peak memory | Speedup vs current | Max diff vs NumPy | Mean diff vs NumPy | Max diff vs unfused | Mean diff vs unfused | Max diff vs current | Mean diff vs current |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cmy_to_log_xyz_unfused_backend_chain | 1.375 ms | 1.557 ms | 1.359 ms | 2.842 ms | 26.3 MiB | n/a | 2.384e-07 | 3.814e-08 | 0.000e+00 | 0.000e+00 | n/a | n/a |
| cmy_to_log_xyz_fused_metal | 0.705 ms | 0.789 ms | 0.628 ms | 0.871 ms | 6.0 MiB | n/a | 3.576e-07 | 6.093e-08 | 2.384e-07 | 3.179e-08 | n/a | n/a |

- Median speedup fused vs unfused: 1.950x
- Median speedup raw pixel-thread v1 vs current: n/a
- P90 speedup raw pixel-thread v1 vs current: n/a
- Peak memory ratio raw pixel-thread v1 vs current: n/a

- Raw fused / XYZ fused median ratio: 1.333x

### medium_768x1024

- Image: 768x1024x3 float32
- Profiles: kodak_portra_400 -> kodak_portra_endura
- Spectral length K: 81
- Compile/setup excluded: True
- Static table conversion excluded: True
- NumPy reference computed: True
- Warmup: 3
- Runs: 10

#### cmy_to_log_raw

| Path | Median | P90 | Min | Max | Peak memory | Speedup vs current | Max diff vs NumPy | Mean diff vs NumPy | Max diff vs unfused | Mean diff vs unfused | Max diff vs current | Mean diff vs current |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cmy_to_log_raw_unfused_backend_chain | 14.627 ms | 15.628 ms | 14.435 ms | 16.058 ms | 315.0 MiB | 0.174x | 2.384e-07 | 2.675e-08 | 0.000e+00 | 0.000e+00 | 2.384e-07 | 2.823e-08 |
| cmy_to_log_raw_channel_thread_baseline | 6.364 ms | 6.420 ms | 6.327 ms | 6.447 ms | 72.0 MiB | 0.399x | 2.384e-07 | 3.732e-08 | 2.384e-07 | 2.823e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_v1 | 2.540 ms | 2.747 ms | 2.446 ms | 2.925 ms | 72.0 MiB | 1.000x | 2.384e-07 | 3.732e-08 | 2.384e-07 | 2.823e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_v1_tg64 | 2.537 ms | 3.156 ms | 2.487 ms | 3.218 ms | 72.0 MiB | 1.001x | 2.384e-07 | 3.732e-08 | 2.384e-07 | 2.823e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_v1_tg128 | 2.454 ms | 2.536 ms | 2.416 ms | 2.749 ms | 72.0 MiB | 1.035x | 2.384e-07 | 3.732e-08 | 2.384e-07 | 2.823e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_v1_tg512 | 2.547 ms | 3.538 ms | 2.473 ms | 3.875 ms | 72.0 MiB | 0.998x | 2.384e-07 | 3.732e-08 | 2.384e-07 | 2.823e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_k_template | 2.400 ms | 2.905 ms | 2.354 ms | 5.823 ms | 72.0 MiB | 1.059x | 2.384e-07 | 3.732e-08 | 2.384e-07 | 2.823e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_table_cache | 2.657 ms | 4.780 ms | 2.626 ms | 4.939 ms | 72.0 MiB | 0.956x | 2.384e-07 | 3.732e-08 | 2.384e-07 | 2.823e-08 | 0.000e+00 | 0.000e+00 |

- Median speedup fused vs unfused: 5.758x
- Median speedup raw pixel-thread v1 vs current: 2.505x
- P90 speedup raw pixel-thread v1 vs current: 2.337x
- Peak memory ratio raw pixel-thread v1 vs current: 1.000x

#### cmy_to_log_xyz

| Path | Median | P90 | Min | Max | Peak memory | Speedup vs current | Max diff vs NumPy | Mean diff vs NumPy | Max diff vs unfused | Mean diff vs unfused | Max diff vs current | Mean diff vs current |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cmy_to_log_xyz_unfused_backend_chain | 14.298 ms | 14.442 ms | 14.209 ms | 14.691 ms | 315.0 MiB | n/a | 2.384e-07 | 3.810e-08 | 0.000e+00 | 0.000e+00 | n/a | n/a |
| cmy_to_log_xyz_fused_metal | 2.443 ms | 2.458 ms | 2.405 ms | 2.461 ms | 72.0 MiB | n/a | 3.576e-07 | 6.095e-08 | 2.980e-07 | 3.177e-08 | n/a | n/a |

- Median speedup fused vs unfused: 5.852x
- Median speedup raw pixel-thread v1 vs current: n/a
- P90 speedup raw pixel-thread v1 vs current: n/a
- Peak memory ratio raw pixel-thread v1 vs current: n/a

- Raw fused / XYZ fused median ratio: 1.040x

### full_3024x4032

- Image: 3024x4032x3 float32
- Profiles: kodak_portra_400 -> kodak_portra_endura
- Spectral length K: 81
- Compile/setup excluded: True
- Static table conversion excluded: True
- NumPy reference computed: False
- Warmup: 2
- Runs: 5

#### cmy_to_log_raw

| Path | Median | P90 | Min | Max | Peak memory | Speedup vs current | Max diff vs NumPy | Mean diff vs NumPy | Max diff vs unfused | Mean diff vs unfused | Max diff vs current | Mean diff vs current |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cmy_to_log_raw_unfused_backend_chain | 251.727 ms | 254.941 ms | 231.773 ms | 256.635 ms | 4883.8 MiB | 0.147x | n/a | n/a | 0.000e+00 | 0.000e+00 | 2.980e-07 | 2.823e-08 |
| cmy_to_log_raw_channel_thread_baseline | 104.635 ms | 113.117 ms | 100.782 ms | 118.671 ms | 1116.4 MiB | 0.353x | n/a | n/a | 2.980e-07 | 2.823e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_v1 | 36.962 ms | 38.429 ms | 36.371 ms | 38.459 ms | 1116.4 MiB | 1.000x | n/a | n/a | 2.980e-07 | 2.823e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_v1_tg64 | 37.240 ms | 37.885 ms | 36.171 ms | 37.934 ms | 1116.4 MiB | 0.993x | n/a | n/a | 2.980e-07 | 2.823e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_v1_tg128 | 37.511 ms | 37.851 ms | 36.771 ms | 37.951 ms | 1116.4 MiB | 0.985x | n/a | n/a | 2.980e-07 | 2.823e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_v1_tg512 | 37.677 ms | 38.488 ms | 37.265 ms | 38.692 ms | 1116.4 MiB | 0.981x | n/a | n/a | 2.980e-07 | 2.823e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_k_template | 35.264 ms | 35.604 ms | 34.294 ms | 35.769 ms | 1116.4 MiB | 1.048x | n/a | n/a | 2.980e-07 | 2.823e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_table_cache | 38.961 ms | 39.799 ms | 38.619 ms | 39.841 ms | 1116.4 MiB | 0.949x | n/a | n/a | 2.980e-07 | 2.823e-08 | 0.000e+00 | 0.000e+00 |

- Median speedup fused vs unfused: 6.810x
- Median speedup raw pixel-thread v1 vs current: 2.831x
- P90 speedup raw pixel-thread v1 vs current: 2.944x
- Peak memory ratio raw pixel-thread v1 vs current: 1.000x

#### cmy_to_log_xyz

| Path | Median | P90 | Min | Max | Peak memory | Speedup vs current | Max diff vs NumPy | Mean diff vs NumPy | Max diff vs unfused | Mean diff vs unfused | Max diff vs current | Mean diff vs current |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cmy_to_log_xyz_unfused_backend_chain | 248.197 ms | 256.766 ms | 238.167 ms | 259.849 ms | 4883.8 MiB | n/a | n/a | n/a | 0.000e+00 | 0.000e+00 | n/a | n/a |
| cmy_to_log_xyz_fused_metal | 36.671 ms | 37.002 ms | 35.911 ms | 37.100 ms | 1116.4 MiB | n/a | n/a | n/a | 3.576e-07 | 3.176e-08 | n/a | n/a |

- Median speedup fused vs unfused: 6.768x
- Median speedup raw pixel-thread v1 vs current: n/a
- P90 speedup raw pixel-thread v1 vs current: n/a
- Peak memory ratio raw pixel-thread v1 vs current: n/a

- Raw fused / XYZ fused median ratio: 1.008x

## End-To-End Attribution

- Image shape: [768, 1024, 3]
- Runs: 3
- Wall median: 45.576 ms

| Kernel | Calls | Shapes | Total | Median | P90 | Wall share |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| cmy_to_log_raw | 9 | 1x1x3: 6, 768x1024x3: 3 | 45.665 ms | 1.856 ms | 15.420 ms | 16.30% |
| cmy_to_log_xyz | 3 | 768x1024x3: 3 | 17.036 ms | 6.108 ms | 6.806 ms | 6.08% |

| Stage | Total | Wall share |
| --- | ---: | ---: |
| PrintingStage.expose | 51.365 ms | 18.33% |
| PrintingStage.develop | 1.314 ms | 0.47% |
| ScanningStage.scan | 19.669 ms | 7.02% |
| SpectralLUTService.spectral_compute_enlarger | 0.000 ms | 0.00% |
| SpectralLUTService.spectral_compute_scanner | 17.092 ms | 6.10% |
