# MLX 3D LUT Benchmark

- Image: 64x65x3 float32
- LUT: 9x9x9x3 float32
- Warmup: 2
- Runs: 5
- Compile/setup excluded: True
- Threadgroup: [256, 1, 1]

| Path | Median | P90 | Min | Max | Peak memory | Max diff vs NumPy |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| mlx_ops_baseline | 0.817 ms | 1.091 ms | 0.730 ms | 1.249 ms | 1.0 MiB | 1.157e-07 |
| metal_kernel | 0.241 ms | 0.266 ms | 0.229 ms | 0.272 ms | 0.4 MiB | 8.134e-08 |

## Metal vs MLX Ops

- Median speedup: 3.395x
- Max diff vs MLX ops baseline: 1.788e-07
