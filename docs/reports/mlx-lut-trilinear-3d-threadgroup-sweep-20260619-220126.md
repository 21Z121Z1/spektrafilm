# MLX 3D LUT Benchmark Suite

- Suite: threadgroup-sweep
- Seed: 20260619

## preview_256_lut17

- Image: 256x256x3 float32
- LUT: 17x17x17x3 float32
- Warmup: 5
- Runs: 30
- Compile/setup excluded: True

- MLX ops baseline median: 2.382 ms
- MLX ops baseline p90: 2.457 ms
- MLX ops baseline peak memory: 11.3 MiB

| Threadgroup | Median | P90 | Min | Max | Peak memory | Max diff vs NumPy | Max diff vs MLX ops | Decision |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 64 | 0.324 ms | 0.338 ms | 0.296 ms | 0.358 ms | 4.6 MiB | 9.551e-08 | 1.788e-07 | accepted |
| 128 | 0.299 ms | 0.327 ms | 0.271 ms | 0.341 ms | 4.6 MiB | 9.551e-08 | 1.788e-07 | accepted |
| 256 | 0.353 ms | 0.393 ms | 0.316 ms | 0.445 ms | 4.6 MiB | 9.551e-08 | 1.788e-07 | baseline |
| 512 | 0.299 ms | 0.326 ms | 0.277 ms | 0.369 ms | 4.6 MiB | 9.551e-08 | 1.788e-07 | rejected |

- Accepted threadgroup size: 128

## medium_768x1024_lut33

- Image: 768x1024x3 float32
- LUT: 33x33x33x3 float32
- Warmup: 5
- Runs: 30
- Compile/setup excluded: True

- MLX ops baseline median: 10.617 ms
- MLX ops baseline p90: 14.850 ms
- MLX ops baseline peak memory: 135.4 MiB

| Threadgroup | Median | P90 | Min | Max | Peak memory | Max diff vs NumPy | Max diff vs MLX ops | Decision |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 64 | 0.969 ms | 1.433 ms | 0.744 ms | 3.683 ms | 54.4 MiB | 1.075e-07 | 1.788e-07 | rejected |
| 128 | 1.040 ms | 2.170 ms | 0.751 ms | 4.110 ms | 54.4 MiB | 1.075e-07 | 1.788e-07 | rejected |
| 256 | 0.975 ms | 1.920 ms | 0.737 ms | 5.277 ms | 54.4 MiB | 1.075e-07 | 1.788e-07 | baseline |
| 512 | 1.085 ms | 1.150 ms | 0.736 ms | 1.333 ms | 54.4 MiB | 1.075e-07 | 1.788e-07 | rejected |

- Accepted threadgroup size: 256

## full_3024x4032_lut33

- Image: 3024x4032x3 float32
- LUT: 33x33x33x3 float32
- Warmup: 3
- Runs: 10
- Compile/setup excluded: True

- MLX ops baseline median: 217.937 ms
- MLX ops baseline p90: 228.381 ms
- MLX ops baseline peak memory: 2093.6 MiB

| Threadgroup | Median | P90 | Min | Max | Peak memory | Max diff vs NumPy | Max diff vs MLX ops | Decision |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 64 | 10.696 ms | 12.108 ms | 8.158 ms | 12.645 ms | 837.7 MiB | n/a | 1.788e-07 | rejected |
| 128 | 8.143 ms | 8.230 ms | 8.127 ms | 8.234 ms | 837.7 MiB | n/a | 1.788e-07 | rejected |
| 256 | 7.973 ms | 8.011 ms | 7.943 ms | 8.033 ms | 837.7 MiB | n/a | 1.788e-07 | baseline |
| 512 | 7.980 ms | 8.024 ms | 7.937 ms | 8.032 ms | 837.7 MiB | n/a | 1.788e-07 | rejected |

- Accepted threadgroup size: 256
