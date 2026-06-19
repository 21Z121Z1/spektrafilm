# MLX Spectral Fused Kernel Baseline + Raw Pixel-Thread v1

- Suite: mlx_spectral_fused_baseline
- Seed: 20260619
- Status: ok

## Recommendation

- accept_raw_pixel_thread_v1: `True`
- replace_production_recommended: `True`
- Reason: accepted: pixel-thread v1 preserves current raw output and materially improves a meaningful full-render contributor
- Raw wall share: 30.65%
- Max raw/xyz fused median ratio: 3.025x
- Median speedup raw pixel-thread v1: 3.049x
- P90 speedup raw pixel-thread v1: 3.050x
- Peak memory ratio raw pixel-thread v1: 1.000x
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
| cmy_to_log_raw_unfused_backend_chain | 1.667 ms | 4.643 ms | 1.340 ms | 4.801 ms | 24.8 MiB | 0.602x | 1.788e-07 | 2.678e-08 | 0.000e+00 | 0.000e+00 | 2.384e-07 | 2.810e-08 |
| cmy_to_log_raw_fused_metal | 1.003 ms | 1.710 ms | 0.796 ms | 1.998 ms | 4.5 MiB | 1.000x | 2.384e-07 | 3.747e-08 | 2.384e-07 | 2.810e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_v1 | 0.794 ms | 1.580 ms | 0.587 ms | 2.037 ms | 4.5 MiB | 1.264x | 2.384e-07 | 3.747e-08 | 2.384e-07 | 2.810e-08 | 0.000e+00 | 0.000e+00 |

- Median speedup fused vs unfused: 1.662x
- Median speedup raw pixel-thread v1 vs current: 1.264x
- P90 speedup raw pixel-thread v1 vs current: 1.083x
- Peak memory ratio raw pixel-thread v1 vs current: 1.000x

#### cmy_to_log_xyz

| Path | Median | P90 | Min | Max | Peak memory | Speedup vs current | Max diff vs NumPy | Mean diff vs NumPy | Max diff vs unfused | Mean diff vs unfused | Max diff vs current | Mean diff vs current |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cmy_to_log_xyz_unfused_backend_chain | 1.542 ms | 5.357 ms | 1.359 ms | 6.847 ms | 24.8 MiB | n/a | 2.384e-07 | 3.814e-08 | 0.000e+00 | 0.000e+00 | n/a | n/a |
| cmy_to_log_xyz_fused_metal | 0.531 ms | 1.019 ms | 0.480 ms | 1.985 ms | 4.5 MiB | n/a | 3.576e-07 | 6.093e-08 | 2.384e-07 | 3.179e-08 | n/a | n/a |

- Median speedup fused vs unfused: 2.904x
- Median speedup raw pixel-thread v1 vs current: n/a
- P90 speedup raw pixel-thread v1 vs current: n/a
- Peak memory ratio raw pixel-thread v1 vs current: n/a

- Raw fused / XYZ fused median ratio: 1.889x

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
| cmy_to_log_raw_unfused_backend_chain | 28.019 ms | 31.863 ms | 19.486 ms | 32.101 ms | 297.0 MiB | 0.391x | 2.384e-07 | 2.675e-08 | 0.000e+00 | 0.000e+00 | 2.384e-07 | 2.823e-08 |
| cmy_to_log_raw_fused_metal | 10.962 ms | 13.666 ms | 10.230 ms | 13.754 ms | 54.0 MiB | 1.000x | 2.384e-07 | 3.732e-08 | 2.384e-07 | 2.823e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_v1 | 3.151 ms | 4.333 ms | 2.530 ms | 4.400 ms | 54.0 MiB | 3.478x | 2.384e-07 | 3.732e-08 | 2.384e-07 | 2.823e-08 | 0.000e+00 | 0.000e+00 |

- Median speedup fused vs unfused: 2.556x
- Median speedup raw pixel-thread v1 vs current: 3.478x
- P90 speedup raw pixel-thread v1 vs current: 3.154x
- Peak memory ratio raw pixel-thread v1 vs current: 1.000x

#### cmy_to_log_xyz

| Path | Median | P90 | Min | Max | Peak memory | Speedup vs current | Max diff vs NumPy | Mean diff vs NumPy | Max diff vs unfused | Mean diff vs unfused | Max diff vs current | Mean diff vs current |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cmy_to_log_xyz_unfused_backend_chain | 27.001 ms | 31.427 ms | 24.721 ms | 31.610 ms | 297.0 MiB | n/a | 2.384e-07 | 3.810e-08 | 0.000e+00 | 0.000e+00 | n/a | n/a |
| cmy_to_log_xyz_fused_metal | 4.387 ms | 6.070 ms | 2.954 ms | 6.388 ms | 54.0 MiB | n/a | 3.576e-07 | 6.095e-08 | 2.980e-07 | 3.177e-08 | n/a | n/a |

- Median speedup fused vs unfused: 6.155x
- Median speedup raw pixel-thread v1 vs current: n/a
- P90 speedup raw pixel-thread v1 vs current: n/a
- Peak memory ratio raw pixel-thread v1 vs current: n/a

- Raw fused / XYZ fused median ratio: 2.499x

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
| cmy_to_log_raw_unfused_backend_chain | 326.392 ms | 330.333 ms | 323.789 ms | 330.771 ms | 4604.7 MiB | 0.451x | n/a | n/a | 0.000e+00 | 0.000e+00 | 2.980e-07 | 2.823e-08 |
| cmy_to_log_raw_fused_metal | 147.187 ms | 148.361 ms | 135.145 ms | 148.826 ms | 837.3 MiB | 1.000x | n/a | n/a | 2.980e-07 | 2.823e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_v1 | 48.267 ms | 48.642 ms | 45.908 ms | 48.664 ms | 837.3 MiB | 3.049x | n/a | n/a | 2.980e-07 | 2.823e-08 | 0.000e+00 | 0.000e+00 |

- Median speedup fused vs unfused: 2.218x
- Median speedup raw pixel-thread v1 vs current: 3.049x
- P90 speedup raw pixel-thread v1 vs current: 3.050x
- Peak memory ratio raw pixel-thread v1 vs current: 1.000x

#### cmy_to_log_xyz

| Path | Median | P90 | Min | Max | Peak memory | Speedup vs current | Max diff vs NumPy | Mean diff vs NumPy | Max diff vs unfused | Mean diff vs unfused | Max diff vs current | Mean diff vs current |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cmy_to_log_xyz_unfused_backend_chain | 324.944 ms | 325.529 ms | 314.292 ms | 325.741 ms | 4604.7 MiB | n/a | n/a | n/a | 0.000e+00 | 0.000e+00 | n/a | n/a |
| cmy_to_log_xyz_fused_metal | 48.662 ms | 49.976 ms | 47.244 ms | 50.553 ms | 837.3 MiB | n/a | n/a | n/a | 3.576e-07 | 3.176e-08 | n/a | n/a |

- Median speedup fused vs unfused: 6.678x
- Median speedup raw pixel-thread v1 vs current: n/a
- P90 speedup raw pixel-thread v1 vs current: n/a
- Peak memory ratio raw pixel-thread v1 vs current: n/a

- Raw fused / XYZ fused median ratio: 3.025x

## End-To-End Attribution

- Image shape: [768, 1024, 3]
- Runs: 3
- Wall median: 52.388 ms

| Kernel | Calls | Shapes | Total | Median | P90 | Wall share |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| cmy_to_log_raw | 9 | 1x1x3: 6, 768x1024x3: 3 | 46.787 ms | 0.967 ms | 14.152 ms | 30.65% |
| cmy_to_log_xyz | 3 | 768x1024x3: 3 | 15.811 ms | 4.950 ms | 6.063 ms | 10.36% |

| Stage | Total | Wall share |
| --- | ---: | ---: |
| PrintingStage.expose | 50.313 ms | 32.96% |
| PrintingStage.develop | 2.559 ms | 1.68% |
| ScanningStage.scan | 19.110 ms | 12.52% |
| SpectralLUTService.spectral_compute_enlarger | 0.000 ms | 0.00% |
| SpectralLUTService.spectral_compute_scanner | 15.863 ms | 10.39% |
