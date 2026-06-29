# MLX Memory Residency Governance - 2026-06-29

## Scope

This pass adds opt-in MLX memory residency governance without changing SDR/HDR math or default output behavior.

Covered surfaces:

- Unified backend residency events for `asarray`, `to_numpy`, `eval`, `synchronize`, `cleanup`, and peak-budget checks.
- MLX memory snapshots for active/cache/peak memory when the installed MLX runtime exposes those counters.
- Runtime peak-budget policy controlled by `SettingsParams.mlx_peak_memory_budget_mb` and `mlx_peak_memory_policy`.
- Explicit preprocess resize fallback policy controlled by `preprocess_resize_backend_policy`.
- RouteMaster sidecar field helpers for policy-scoped iteration and byte accounting.
- Backend-resident runtime benchmark output extended with peak-memory evidence.

## Default Behavior

All new governance is opt-in.

- `mlx_memory_profile=False` by default.
- `mlx_peak_memory_budget_mb=None` by default, so no peak-memory policy is applied.
- `mlx_peak_memory_policy="warn"` by default and only matters when a budget is set.
- `preprocess_resize_backend_policy="cpu_fallback"` preserves the existing MLX resize fallback.
- `hdr_route_sidecar_policy="minimal"` remains unchanged.

The existing CPU/NumPy public output policy remains `materialize_policy="numpy_float64"` unless callers explicitly request `numpy_float32` or `backend`.

## Runtime Policy

When a peak budget is set for an MLX backend, the pipeline resets MLX peak memory at the start of the run when the runtime supports `reset_peak_memory()`.

After processing and GPU validation, the pipeline records:

- `SimulationPipeline.mlx_peak_memory_bytes`
- `SimulationPipeline.mlx_peak_memory_budget_bytes`
- `SimulationPipeline.mlx_peak_memory_over_budget` when peak exceeds budget
- `SimulationPipeline.mlx_peak_budget_unavailable` when MLX lacks peak counters

Policy behavior:

- `warn`: record diagnostics only.
- `cleanup`: record diagnostics and call backend cleanup on over-budget.
- `raise`: raise `MemoryError` on over-budget.

## Resize Fallback

MLX preprocess resize still uses the existing explicit CPU fallback:

`backend.to_numpy -> skimage.rescale(order=3) -> backend.asarray`

The fallback records:

- `SimulationPipeline.preprocess.resize_cpu_fallback`
- `SimulationPipeline.preprocess.resize_breaks_backend_residency`
- `SimulationPipeline.preprocess.resize_policy_cpu_fallback`

Set `preprocess_resize_backend_policy="error"` to reject the fallback for strict residency experiments.

## RouteMaster Sidecars

`spektrafilm.runtime.route_master` now exposes:

- `route_master_sidecar_fields(policy)`
- `iter_route_master_sidecars(route_master, policy=...)`
- `route_master_sidecar_nbytes(route_master, policy=...)`

The field policy is shared by runtime and GUI materialization/byte accounting so cached RouteMasters do not duplicate private sidecar lists.

## Benchmark Artifact

Use:

```bash
.venv/bin/python tools/benchmark_backend_resident_runtime_boundaries.py --backend all --precision float32
```

The tool writes JSON and Markdown under `docs/reports/` and now includes:

- per-run residency summaries,
- sync events inside the recorder window,
- peak memory bytes when MLX exposes peak counters,
- explicit NumPy validation timing outside the runtime-leakage recorder.

This benchmark is a runtime boundary and residency artifact, not a broad HDR quality or speed acceptance gate.
