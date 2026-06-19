# MLX Spectral Fused Kernel Baseline + Raw Pixel-Thread v1

- Suite: mlx_spectral_fused_baseline
- Seed: 20260619
- Status: ok

## Recommendation

- accept_raw_pixel_thread_v1: `False`
- replace_production_recommended: `False`
- Reason: rejected: cmy_to_log_raw_pixel_thread_v1 peak memory increased too much
- Raw wall share: 31.08%
- Max raw/xyz fused median ratio: 2.615x
- Median speedup raw pixel-thread v1: 2.474x
- P90 speedup raw pixel-thread v1: 2.673x
- Peak memory ratio raw pixel-thread v1: 1.143x
- Max diff raw pixel-thread v1 vs current: 0.000e+00

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
| cmy_to_log_raw_unfused_backend_chain | 1.614 ms | 1.768 ms | 1.444 ms | 1.804 ms | 24.8 MiB | 0.794x | 1.788e-07 | 2.678e-08 | 0.000e+00 | 0.000e+00 | 2.384e-07 | 2.810e-08 |
| cmy_to_log_raw_fused_metal | 1.282 ms | 2.008 ms | 1.103 ms | 2.021 ms | 5.3 MiB | 1.000x | 2.384e-07 | 3.747e-08 | 2.384e-07 | 2.810e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_v1 | 0.559 ms | 0.603 ms | 0.502 ms | 0.616 ms | 6.0 MiB | 2.291x | 2.384e-07 | 3.747e-08 | 2.384e-07 | 2.810e-08 | 0.000e+00 | 0.000e+00 |

- Median speedup fused vs unfused: 1.259x
- Median speedup raw pixel-thread v1 vs current: 2.291x
- P90 speedup raw pixel-thread v1 vs current: 3.331x
- Peak memory ratio raw pixel-thread v1 vs current: 1.143x

#### cmy_to_log_xyz

| Path | Median | P90 | Min | Max | Peak memory | Speedup vs current | Max diff vs NumPy | Mean diff vs NumPy | Max diff vs unfused | Mean diff vs unfused | Max diff vs current | Mean diff vs current |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cmy_to_log_xyz_unfused_backend_chain | 1.839 ms | 3.072 ms | 1.424 ms | 3.089 ms | 27.0 MiB | n/a | 2.384e-07 | 3.814e-08 | 0.000e+00 | 0.000e+00 | n/a | n/a |
| cmy_to_log_xyz_fused_metal | 0.642 ms | 0.684 ms | 0.571 ms | 0.740 ms | 7.5 MiB | n/a | 3.576e-07 | 6.093e-08 | 2.384e-07 | 3.179e-08 | n/a | n/a |

- Median speedup fused vs unfused: 2.864x
- Median speedup raw pixel-thread v1 vs current: n/a
- P90 speedup raw pixel-thread v1 vs current: n/a
- Peak memory ratio raw pixel-thread v1 vs current: n/a

- Raw fused / XYZ fused median ratio: 1.997x

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
| cmy_to_log_raw_unfused_backend_chain | 13.804 ms | 13.929 ms | 13.729 ms | 13.953 ms | 297.0 MiB | 0.459x | 2.384e-07 | 2.675e-08 | 0.000e+00 | 0.000e+00 | 2.384e-07 | 2.823e-08 |
| cmy_to_log_raw_fused_metal | 6.334 ms | 7.033 ms | 6.213 ms | 7.625 ms | 63.0 MiB | 1.000x | 2.384e-07 | 3.732e-08 | 2.384e-07 | 2.823e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_v1 | 2.560 ms | 2.631 ms | 2.445 ms | 2.672 ms | 72.0 MiB | 2.474x | 2.384e-07 | 3.732e-08 | 2.384e-07 | 2.823e-08 | 0.000e+00 | 0.000e+00 |

- Median speedup fused vs unfused: 2.179x
- Median speedup raw pixel-thread v1 vs current: 2.474x
- P90 speedup raw pixel-thread v1 vs current: 2.673x
- Peak memory ratio raw pixel-thread v1 vs current: 1.143x

#### cmy_to_log_xyz

| Path | Median | P90 | Min | Max | Peak memory | Speedup vs current | Max diff vs NumPy | Mean diff vs NumPy | Max diff vs unfused | Mean diff vs unfused | Max diff vs current | Mean diff vs current |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cmy_to_log_xyz_unfused_backend_chain | 14.841 ms | 15.003 ms | 13.997 ms | 15.033 ms | 324.0 MiB | n/a | 2.384e-07 | 3.810e-08 | 0.000e+00 | 0.000e+00 | n/a | n/a |
| cmy_to_log_xyz_fused_metal | 2.422 ms | 2.494 ms | 2.381 ms | 2.537 ms | 90.0 MiB | n/a | 3.576e-07 | 6.095e-08 | 2.980e-07 | 3.177e-08 | n/a | n/a |

- Median speedup fused vs unfused: 6.128x
- Median speedup raw pixel-thread v1 vs current: n/a
- P90 speedup raw pixel-thread v1 vs current: n/a
- Peak memory ratio raw pixel-thread v1 vs current: n/a

- Raw fused / XYZ fused median ratio: 2.615x

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
| cmy_to_log_raw_unfused_backend_chain | 215.160 ms | 217.139 ms | 212.498 ms | 217.915 ms | 4604.7 MiB | 0.422x | n/a | n/a | 0.000e+00 | 0.000e+00 | 2.980e-07 | 2.823e-08 |
| cmy_to_log_raw_fused_metal | 90.887 ms | 90.899 ms | 90.816 ms | 90.906 ms | 976.8 MiB | 1.000x | n/a | n/a | 2.980e-07 | 2.823e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_v1 | 32.591 ms | 32.744 ms | 32.565 ms | 32.815 ms | 1116.4 MiB | 2.789x | n/a | n/a | 2.980e-07 | 2.823e-08 | 0.000e+00 | 0.000e+00 |

- Median speedup fused vs unfused: 2.367x
- Median speedup raw pixel-thread v1 vs current: 2.789x
- P90 speedup raw pixel-thread v1 vs current: 2.776x
- Peak memory ratio raw pixel-thread v1 vs current: 1.143x

#### cmy_to_log_xyz

| Path | Median | P90 | Min | Max | Peak memory | Speedup vs current | Max diff vs NumPy | Mean diff vs NumPy | Max diff vs unfused | Mean diff vs unfused | Max diff vs current | Mean diff vs current |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cmy_to_log_xyz_unfused_backend_chain | 221.969 ms | 227.344 ms | 208.013 ms | 230.186 ms | 5023.4 MiB | n/a | n/a | n/a | 0.000e+00 | 0.000e+00 | n/a | n/a |
| cmy_to_log_xyz_fused_metal | 43.914 ms | 51.340 ms | 36.060 ms | 55.038 ms | 1395.5 MiB | n/a | n/a | n/a | 3.576e-07 | 3.176e-08 | n/a | n/a |

- Median speedup fused vs unfused: 5.055x
- Median speedup raw pixel-thread v1 vs current: n/a
- P90 speedup raw pixel-thread v1 vs current: n/a
- Peak memory ratio raw pixel-thread v1 vs current: n/a

- Raw fused / XYZ fused median ratio: 2.070x

## End-To-End Attribution

- Image shape: [768, 1024, 3]
- Runs: 3
- Wall median: 52.740 ms

| Kernel | Calls | Shapes | Total | Median | P90 | Wall share |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| cmy_to_log_raw | 9 | 1x1x3: 6, 768x1024x3: 3 | 48.342 ms | 2.061 ms | 12.721 ms | 31.08% |
| cmy_to_log_xyz | 3 | 768x1024x3: 3 | 17.463 ms | 6.268 ms | 6.300 ms | 11.23% |

| Stage | Total | Wall share |
| --- | ---: | ---: |
| PrintingStage.expose | 52.424 ms | 33.70% |
| PrintingStage.develop | 2.028 ms | 1.30% |
| ScanningStage.scan | 20.952 ms | 13.47% |
| SpectralLUTService.spectral_compute_enlarger | 0.000 ms | 0.00% |
| SpectralLUTService.spectral_compute_scanner | 17.550 ms | 11.28% |
