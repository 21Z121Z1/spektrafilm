# MLX Memory Residency Benchmark Note

The benchmark entry point added in this branch is:

```bash
.venv/bin/python tests/benchmarks/benchmark_mlx_memory_residency.py \
  --height 3000 --width 4000 --runs 3 \
  --output-json docs/reports/mlx-memory-residency-12mp.json \
  --output-markdown docs/reports/mlx-memory-residency-12mp.md
```

This note exists because the GitHub connector environment used for this commit cannot exercise the local macOS MLX/Metal runtime. Run the command above on the target workstation to produce the measured JSON and Markdown artifacts.
