# MLX 3D LUT Benchmark Suite

- Suite: acceptance
- Seed: 20260619

## preview_256_lut17

- Image: 256x256x3 float32
- LUT: 17x17x17x3 float32
- Warmup: 5
- Runs: 30
- Compile/setup excluded: True

- Threadgroup: [256, 1, 1]

| Path | Median | P90 | Min | Max | Peak memory | Max diff vs NumPy | Max diff vs MLX ops |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| mlx_ops_baseline | 2.227 ms | 2.449 ms | 1.666 ms | 2.874 ms | 12.1 MiB | 1.277e-07 | n/a |
| metal_kernel | 0.348 ms | 0.377 ms | 0.321 ms | 0.476 ms | 4.6 MiB | 9.551e-08 | 1.788e-07 |

- Median speedup metal vs MLX ops: 6.396x

## medium_768x1024_lut33

- Image: 768x1024x3 float32
- LUT: 33x33x33x3 float32
- Warmup: 5
- Runs: 30
- Compile/setup excluded: True

- Threadgroup: [256, 1, 1]

| Path | Median | P90 | Min | Max | Peak memory | Max diff vs NumPy | Max diff vs MLX ops |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| mlx_ops_baseline | 10.603 ms | 11.223 ms | 10.419 ms | 17.127 ms | 144.4 MiB | 1.516e-07 | n/a |
| metal_kernel | 0.756 ms | 1.298 ms | 0.735 ms | 3.361 ms | 54.4 MiB | 1.075e-07 | 1.788e-07 |

- Median speedup metal vs MLX ops: 14.017x

## full_3024x4032_lut33

- Image: 3024x4032x3 float32
- LUT: 33x33x33x3 float32
- Warmup: 3
- Runs: 10
- Compile/setup excluded: True

- Threadgroup: [256, 1, 1]

| Path | Median | P90 | Min | Max | Peak memory | Max diff vs NumPy | Max diff vs MLX ops |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| mlx_ops_baseline | 228.497 ms | 287.191 ms | 215.723 ms | 302.615 ms | 2233.2 MiB | n/a | n/a |
| metal_kernel | 10.742 ms | 12.130 ms | 8.123 ms | 12.220 ms | 837.7 MiB | n/a | 1.788e-07 |

- Median speedup metal vs MLX ops: 21.272x
