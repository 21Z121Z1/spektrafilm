# Filming Fused Filters Benchmark

Date: 2026-06-22

## Scope

This report evaluates the current Level B fused filming spatial chain against the existing serial MLX chain. The benchmark uses:

- Script: `tests/benchmarks/benchmark_filming_fused_filters.py`
- Backend: MLX
- Repeats: 3 timed repeats after one warmup
- Reference mode: `small`, using a 256x256 NumPy fused reference for parity checks
- Parameters: active glimmerglass diffusion, lens blur, halation scatter, and halation bounces from the benchmark script

The benchmark records backend residency, median/P90/min/max time, MLX peak memory, and fused MLX parity against NumPy fused reference where available.

## Results

| Shape | Pixels | Path | Median ms | P90 ms | Peak memory | NumPy fused max diff | Status |
| --- | ---: | --- | ---: | ---: | ---: | ---: | --- |
| 1500x2667x3 | 4.00 MP | serial_mlx | 352.05 | 415.02 | 3.68 GB | n/a | passed |
| 1500x2667x3 | 4.00 MP | fused_mlx | 387.01 | 431.17 | 2.28 GB | 5.07e-7 | passed |
| 1800x2800x3 | 5.04 MP | serial_mlx | 445.55 | 532.39 | 4.31 GB | n/a | passed |
| 1800x2800x3 | 5.04 MP | fused_mlx | 475.32 | 512.37 | 2.70 GB | 5.07e-7 | passed |
| 2000x3000x3 | 6.00 MP | serial_mlx | 557.00 | 598.21 | 4.87 GB | n/a | passed |
| 2000x3000x3 | 6.00 MP | fused_mlx | 437.03 | 537.52 | 3.04 GB | 5.96e-7 | passed |
| 2500x3200x3 | 8.00 MP | serial_mlx | n/a | n/a | n/a | n/a | Metal OOM during warmup |
| 2500x3200x3 | 8.00 MP | fused_mlx | 628.30 | 694.55 | 3.80 GB | 5.36e-7 | passed |
| 2700x3300x3 | 8.91 MP | fused_mlx | 683.55 | 745.33 | 4.16 GB | 5.36e-7 | passed |
| 2800x3600x3 | 10.08 MP | fused_mlx | n/a | n/a | n/a | n/a | Metal OOM during warmup |
| 3000x4000x3 | 12.00 MP | serial_mlx | n/a | n/a | n/a | n/a | Metal OOM during warmup |
| 3000x4000x3 | 12.00 MP | fused_mlx | n/a | n/a | n/a | n/a | Metal OOM during warmup |

## Interpretation

- Fused MLX is not a 12MP-ready optimization in the current implementation. Both serial MLX and fused MLX hit Metal OOM at 3000x4000.
- Fused MLX does reduce peak memory by roughly 37-38% in the sizes where serial also runs.
- Fused MLX becomes faster around the 6MP test point: 437.03 ms vs 557.00 ms, a 1.27x median speedup.
- At 4-5MP, fused MLX is slower than serial MLX despite using less memory, so the transfer-function construction overhead still matters at smaller sizes.
- Fused MLX expands the feasible image size on this machine: serial MLX OOMs at 8MP, while fused MLX runs through 8.91MP.
- Fused MLX parity against the small NumPy fused reference stays under 1e-6 in every successful run.

## Conclusion

The current Level B fused chain is a memory-reduction win and a medium-large-image speed win, but it does not yet satisfy the original 12MP acceleration target. The next optimization target should be peak memory in the fused path, especially avoiding simultaneous residency of the padded image FFT, transfer components, and intermediate transfer-function arrays at 10-12MP.
