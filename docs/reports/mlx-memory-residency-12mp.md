# MLX Memory Residency Benchmark

- generated_at: `2026-06-29T15:44:55`
- image: `3000x4000`
- runs: `3`

| scenario | median s | peak MiB | cache MiB | to_numpy | asarray | eval | sync | cleanup | clear_cache | resize | sidecar | final boundary | warnings/failures |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| mlx_scan_only_backend_minimal | 2.6524 | 1385.1 | 0.0 | 3 | 72 | 11 | 1 | 1 | 1 | 0 | 0 | 1 |  |
| mlx_hdr_light_table_backend_minimal | 6.2246 | 1699.7 | 0.0 | 6 | 72 | 12 | 1 | 1 | 1 | 0 | 0 | 1 |  |
| mlx_hdr_paper_backend_minimal | 4.0936 | 2483.9 | 0.0 | 6 | 97 | 14 | 1 | 1 | 1 | 0 | 0 | 1 |  |
| mlx_paper_chemical_fallback_backend_full | 4.5855 | 3170.6 | 0.0 | 13 | 97 | 21 | 1 | 1 | 1 | 0 | 7 | 1 |  |
| mlx_scan_numpy_float32 | 2.4448 | 3170.6 | 0.0 | 4 | 72 | 10 | 1 | 1 | 1 | 0 | 0 | 1 |  |
| mlx_scan_numpy_float64 | 2.6806 | 3170.6 | 0.0 | 4 | 72 | 10 | 1 | 1 | 1 | 0 | 0 | 1 |  |
| mlx_scan_backend_resize_1_25_warn | 24.8634 | 3170.6 | 0.0 | 4 | 78 | 13 | 1 | 1 | 1 | 1 | 0 | 1 | MLX preprocess resize used CPU fallback and broke backend residency. |
