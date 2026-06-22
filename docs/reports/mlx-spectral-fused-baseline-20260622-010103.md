# MLX Spectral Fused Kernel Baseline + Raw Pixel-Thread v1

- Suite: mlx_spectral_fused_baseline
- Seed: 20260619
- Status: ok

## Recommendation

- accept_raw_pixel_thread_v1: `True`
- replace_production_recommended: `True`
- Reason: accepted: pixel-thread v1 preserves channel-thread baseline output and materially improves a meaningful full-render contributor
- Raw wall share: 25.12%
- Max raw/xyz fused median ratio: 1.757x
- Median speedup raw pixel-thread v1: 2.669x
- P90 speedup raw pixel-thread v1: 2.747x
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
| cmy_to_log_raw_unfused_backend_chain | 1.778 ms | 2.941 ms | 1.548 ms | 6.378 ms | 27.2 MiB | 0.622x | 1.788e-07 | 2.678e-08 | 0.000e+00 | 0.000e+00 | 2.384e-07 | 2.810e-08 |
| cmy_to_log_raw_channel_thread_baseline | 1.413 ms | 2.531 ms | 0.973 ms | 3.049 ms | 6.0 MiB | 0.782x | 2.384e-07 | 3.747e-08 | 2.384e-07 | 2.810e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_v1 | 1.105 ms | 1.793 ms | 0.642 ms | 3.383 ms | 6.0 MiB | 1.000x | 2.384e-07 | 3.747e-08 | 2.384e-07 | 2.810e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_v1_tg64 | 0.755 ms | 1.231 ms | 0.596 ms | 3.061 ms | 6.0 MiB | 1.464x | 2.384e-07 | 3.747e-08 | 2.384e-07 | 2.810e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_v1_tg128 | 0.697 ms | 1.106 ms | 0.540 ms | 1.508 ms | 6.0 MiB | 1.585x | 2.384e-07 | 3.747e-08 | 2.384e-07 | 2.810e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_v1_tg512 | 0.990 ms | 3.645 ms | 0.870 ms | 5.801 ms | 6.0 MiB | 1.117x | 2.384e-07 | 3.747e-08 | 2.384e-07 | 2.810e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_k_template | 0.723 ms | 1.919 ms | 0.624 ms | 3.553 ms | 6.0 MiB | 1.529x | 2.384e-07 | 3.747e-08 | 2.384e-07 | 2.810e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_table_cache | 0.843 ms | 2.530 ms | 0.688 ms | 3.784 ms | 6.0 MiB | 1.311x | 2.384e-07 | 3.747e-08 | 2.384e-07 | 2.810e-08 | 0.000e+00 | 0.000e+00 |

- Median speedup fused vs unfused: 1.609x
- Median speedup raw pixel-thread v1 vs current: 1.279x
- P90 speedup raw pixel-thread v1 vs current: 1.412x
- Peak memory ratio raw pixel-thread v1 vs current: 1.000x

#### cmy_to_log_xyz

| Path | Median | P90 | Min | Max | Peak memory | Speedup vs current | Max diff vs NumPy | Mean diff vs NumPy | Max diff vs unfused | Mean diff vs unfused | Max diff vs current | Mean diff vs current |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cmy_to_log_xyz_unfused_backend_chain | 1.858 ms | 2.858 ms | 1.528 ms | 4.773 ms | 27.2 MiB | n/a | 2.384e-07 | 3.814e-08 | 0.000e+00 | 0.000e+00 | n/a | n/a |
| cmy_to_log_xyz_fused_metal | 0.629 ms | 0.996 ms | 0.590 ms | 1.698 ms | 6.0 MiB | n/a | 3.576e-07 | 6.093e-08 | 2.384e-07 | 3.179e-08 | n/a | n/a |

- Median speedup fused vs unfused: 2.954x
- Median speedup raw pixel-thread v1 vs current: n/a
- P90 speedup raw pixel-thread v1 vs current: n/a
- Peak memory ratio raw pixel-thread v1 vs current: n/a

- Raw fused / XYZ fused median ratio: 1.757x

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
| cmy_to_log_raw_unfused_backend_chain | 19.787 ms | 20.889 ms | 17.968 ms | 21.127 ms | 326.3 MiB | 0.146x | 2.384e-07 | 2.675e-08 | 0.000e+00 | 0.000e+00 | 2.384e-07 | 2.823e-08 |
| cmy_to_log_raw_channel_thread_baseline | 7.720 ms | 10.055 ms | 6.848 ms | 10.634 ms | 72.0 MiB | 0.375x | 2.384e-07 | 3.732e-08 | 2.384e-07 | 2.823e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_v1 | 2.892 ms | 3.564 ms | 2.524 ms | 5.081 ms | 72.0 MiB | 1.000x | 2.384e-07 | 3.732e-08 | 2.384e-07 | 2.823e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_v1_tg64 | 2.840 ms | 3.474 ms | 2.578 ms | 5.783 ms | 72.0 MiB | 1.019x | 2.384e-07 | 3.732e-08 | 2.384e-07 | 2.823e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_v1_tg128 | 2.909 ms | 3.802 ms | 2.527 ms | 4.120 ms | 72.0 MiB | 0.994x | 2.384e-07 | 3.732e-08 | 2.384e-07 | 2.823e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_v1_tg512 | 2.765 ms | 3.345 ms | 2.520 ms | 4.611 ms | 72.0 MiB | 1.046x | 2.384e-07 | 3.732e-08 | 2.384e-07 | 2.823e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_k_template | 2.700 ms | 3.208 ms | 2.482 ms | 6.105 ms | 72.0 MiB | 1.071x | 2.384e-07 | 3.732e-08 | 2.384e-07 | 2.823e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_table_cache | 3.064 ms | 3.761 ms | 2.653 ms | 6.085 ms | 72.0 MiB | 0.944x | 2.384e-07 | 3.732e-08 | 2.384e-07 | 2.823e-08 | 0.000e+00 | 0.000e+00 |

- Median speedup fused vs unfused: 6.841x
- Median speedup raw pixel-thread v1 vs current: 2.669x
- P90 speedup raw pixel-thread v1 vs current: 2.821x
- Peak memory ratio raw pixel-thread v1 vs current: 1.000x

#### cmy_to_log_xyz

| Path | Median | P90 | Min | Max | Peak memory | Speedup vs current | Max diff vs NumPy | Mean diff vs NumPy | Max diff vs unfused | Mean diff vs unfused | Max diff vs current | Mean diff vs current |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cmy_to_log_xyz_unfused_backend_chain | 19.361 ms | 20.347 ms | 16.898 ms | 20.819 ms | 326.3 MiB | n/a | 2.384e-07 | 3.810e-08 | 0.000e+00 | 0.000e+00 | n/a | n/a |
| cmy_to_log_xyz_fused_metal | 3.041 ms | 3.474 ms | 2.741 ms | 5.042 ms | 72.0 MiB | n/a | 3.576e-07 | 6.095e-08 | 2.980e-07 | 3.177e-08 | n/a | n/a |

- Median speedup fused vs unfused: 6.366x
- Median speedup raw pixel-thread v1 vs current: n/a
- P90 speedup raw pixel-thread v1 vs current: n/a
- Peak memory ratio raw pixel-thread v1 vs current: n/a

- Raw fused / XYZ fused median ratio: 0.951x

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
| cmy_to_log_raw_unfused_backend_chain | 309.510 ms | 319.356 ms | 275.532 ms | 323.153 ms | 5058.3 MiB | 0.142x | n/a | n/a | 0.000e+00 | 0.000e+00 | 2.980e-07 | 2.823e-08 |
| cmy_to_log_raw_channel_thread_baseline | 120.523 ms | 121.296 ms | 118.361 ms | 121.779 ms | 1116.4 MiB | 0.364x | n/a | n/a | 2.980e-07 | 2.823e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_v1 | 43.850 ms | 44.149 ms | 40.895 ms | 44.339 ms | 1116.4 MiB | 1.000x | n/a | n/a | 2.980e-07 | 2.823e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_v1_tg64 | 42.785 ms | 43.602 ms | 38.074 ms | 43.761 ms | 1116.4 MiB | 1.025x | n/a | n/a | 2.980e-07 | 2.823e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_v1_tg128 | 43.325 ms | 43.458 ms | 40.531 ms | 43.528 ms | 1116.4 MiB | 1.012x | n/a | n/a | 2.980e-07 | 2.823e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_v1_tg512 | 42.159 ms | 43.762 ms | 39.751 ms | 44.631 ms | 1116.4 MiB | 1.040x | n/a | n/a | 2.980e-07 | 2.823e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_k_template | 40.936 ms | 41.577 ms | 38.795 ms | 41.618 ms | 1116.4 MiB | 1.071x | n/a | n/a | 2.980e-07 | 2.823e-08 | 0.000e+00 | 0.000e+00 |
| cmy_to_log_raw_pixel_thread_table_cache | 45.551 ms | 46.142 ms | 43.077 ms | 46.322 ms | 1116.4 MiB | 0.963x | n/a | n/a | 2.980e-07 | 2.823e-08 | 0.000e+00 | 0.000e+00 |

- Median speedup fused vs unfused: 7.058x
- Median speedup raw pixel-thread v1 vs current: 2.749x
- P90 speedup raw pixel-thread v1 vs current: 2.747x
- Peak memory ratio raw pixel-thread v1 vs current: 1.000x

#### cmy_to_log_xyz

| Path | Median | P90 | Min | Max | Peak memory | Speedup vs current | Max diff vs NumPy | Mean diff vs NumPy | Max diff vs unfused | Mean diff vs unfused | Max diff vs current | Mean diff vs current |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cmy_to_log_xyz_unfused_backend_chain | 294.869 ms | 297.892 ms | 291.887 ms | 298.200 ms | 5058.3 MiB | n/a | n/a | n/a | 0.000e+00 | 0.000e+00 | n/a | n/a |
| cmy_to_log_xyz_fused_metal | 46.298 ms | 46.992 ms | 44.637 ms | 47.101 ms | 1116.4 MiB | n/a | n/a | n/a | 3.576e-07 | 3.176e-08 | n/a | n/a |

- Median speedup fused vs unfused: 6.369x
- Median speedup raw pixel-thread v1 vs current: n/a
- P90 speedup raw pixel-thread v1 vs current: n/a
- Peak memory ratio raw pixel-thread v1 vs current: n/a

- Raw fused / XYZ fused median ratio: 0.947x

## End-To-End Attribution

- Image shape: [768, 1024, 3]
- Runs: 3
- Wall median: 42.958 ms

| Kernel | Calls | Shapes | Total | Median | P90 | Wall share |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| cmy_to_log_raw | 9 | 1x1x3: 6, 768x1024x3: 3 | 36.306 ms | 0.951 ms | 11.474 ms | 25.12% |
| cmy_to_log_xyz | 3 | 768x1024x3: 3 | 21.327 ms | 4.806 ms | 10.648 ms | 14.76% |

| Stage | Total | Wall share |
| --- | ---: | ---: |
| PrintingStage.expose | 40.149 ms | 27.78% |
| PrintingStage.develop | 1.257 ms | 0.87% |
| ScanningStage.scan | 24.992 ms | 17.29% |
| SpectralLUTService.spectral_compute_enlarger | 0.000 ms | 0.00% |
| SpectralLUTService.spectral_compute_scanner | 21.387 ms | 14.80% |
