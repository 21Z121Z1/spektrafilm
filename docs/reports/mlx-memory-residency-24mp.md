# MLX Memory Residency Benchmark

- generated_at: `2026-06-29T15:47:24`
- image: `4000x6000`
- runs: `1`

| scenario | median s | peak MiB | cache MiB | to_numpy | asarray | eval | sync | cleanup | clear_cache | resize | sidecar | final boundary | warnings/failures |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| mlx_scan_only_backend_minimal | 8.1028 | 2495.3 | 0.0 | 3 | 72 | 11 | 1 | 1 | 1 | 0 | 0 | 1 |  |
| mlx_hdr_paper_backend_minimal | 8.8334 | 4692.6 | 0.0 | 6 | 97 | 14 | 1 | 1 | 1 | 0 | 0 | 1 |  |
