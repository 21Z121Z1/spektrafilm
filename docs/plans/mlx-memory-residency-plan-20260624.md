# MLX Memory Residency Governance Plan — 2026-06-24

## Self-set `/goal`

`/goal Establish an opt-in, source-backed MLX memory residency governance layer that makes sync, materialize, cache, and encoder-boundary transitions observable; adds conservative runtime memory-budget and resize-fallback policy primitives with safe defaults; and introduces explicit RouteMaster sidecar on-demand helpers without changing SDR/HDR mathematics, percentile algorithms, or tile assembly defaults.`

## Scope boundary

This task is limited to full-chain memory occupancy, residency, synchronization, materialization, cache lifetime, and sidecar residency policy. It must not change HDR curve mathematics, SDR film simulation mathematics, percentile behavior, spectral precision, compile strategy, or tile assembly defaults. Benchmarking is used only to validate residency and memory-policy observability.

## Sources read

Repository context:

- `docs/README.md` identifies current docs as the source of truth and warns that archive docs are evidence, not active guidance.
- `docs/dev/mlx-optimization-report-20260530.md` documents the existing MLX runtime path: CPU default, GPU opt-in, float32 MLX, stage-level backend residency, and earlier performance work.
- `docs/reports/mlx-tile-assembly-benchmark-20260624-200634.md` concludes `.at.add` should remain the tile assembly default; this task therefore must not change `_write_tile()` strategy.
- Runtime source, GPU backend source, RouteMaster source, HDR projection/export source, and current residency/RouteMaster tests were inspected for materialization boundaries.

External primary-source constraints:

- MLX exposes active/peak/cache memory APIs, reset peak memory, memory/cache limits, and cache clearing.
- MLX arrays on Apple silicon live in unified memory, but lazy evaluation and stream scheduling still require explicit observation of eval/sync/materialize boundaries.
- MLX `async_eval` and streams are available, but this task does not change scheduling semantics.
- Apple Metal resource lifetime guidance supports explicit ownership/lifetime reasoning rather than relying on incidental cache behavior.

## Current findings

1. `ResidencyRecorder` records backend `asarray` and `to_numpy`, but it does not uniformly profile `eval`, `synchronize`, `cleanup`, or cache clearing, and it lacks JSON/Markdown artifact output.
2. `MlxBackend.cleanup()` clears MLX cache internally, while `tile_utils._maybe_clear_backend_cache()` looks for `backend.clear_cache`; a profiling proxy should expose this boundary for diagnostics without changing default runtime semantics.
3. Backend preprocess resize with `upscale_factor != 1.0` goes through `skimage.transform.rescale`, so MLX + `materialize_policy="backend"` explicitly breaks residency. It is currently only timing-recorded, not policy-controlled.
4. `hdr_route_sidecar_policy="minimal"` avoids several debug arrays, while `"full"` materializes all sidecars. Projection already computes `route_look_chroma` and default `material_detail_y` lazily in some backend paths, but there is no explicit helper API for field-level sidecar demand.
5. Final HEIC encoding necessarily requires contiguous host buffers. This boundary must be labeled as an encoder boundary, not treated as a residency bug.
6. Direct `np.asarray(mx_array)` and `np.ascontiguousarray(mx_array)` calls can bypass backend-level recording unless guarded statically or wrapped at explicit boundaries.

## Implementation plan

### 1. Unified opt-in residency profiling

Add a profiling layer under `spektrafilm.gpu`:

- A profile event model with operation, label, category, shape, dtype, nbytes, elapsed time, allowed/reason, peak memory, and cache memory before/after.
- JSON/Markdown artifact helpers.
- An explicit backend proxy that preserves backend semantics while recording `asarray`, `to_numpy`, `eval`, `synchronize`, `cleanup`, and `clear_cache` calls.
- A pipeline attachment helper for tests/benchmarks to wrap an already-constructed pipeline and stage backends.
- A static guard for direct NumPy materialization patterns.

Default runtime behavior remains unchanged unless a caller explicitly activates residency recording and installs the proxy.

### 2. Conservative memory-budget policy primitives

Add policy primitives with the intended runtime settings:

- `gpu_peak_budget_mb: float | None = None`
- `gpu_budget_policy: "off" | "warn" | "soft_enforce" | "fail" = "off"`

The first version is conservative. `warn` records potential over-budget combinations. `soft_enforce` recommends smaller spectral/spatial tile rows and minimal sidecars. `fail` can fail fast when an explicit budget is exceeded. The default remains `off`.

### 3. Explicit preprocess resize fallback policy

Add policy primitives for the intended setting:

- `gpu_resize_policy: "cpu_fallback" | "warn" | "fail" | "native_if_available" = "cpu_fallback"`

The default preserves compatibility. `warn` and `fail` make the residency break explicit for full-res/backend-resident runs. Preview mode is exempt from fail-fast behavior. `native_if_available` is feature-gated; no native resize path is enabled by default.

### 4. RouteMaster sidecar on-demand helpers

Keep the existing `RouteMaster` dataclass fields intact. Add explicit helpers for:

- `route_look_chroma`
- `material_detail_y`
- `route_linear_xyz`
- `density_cmy`

The helpers distinguish backend-resident computation from explicit NumPy materialization. They update diagnostics counters for on-demand accesses and materializations. For backend-resident `material_detail_y` without a stored sidecar, the helper returns the existing projection-equivalent ones fallback rather than forcing a median materialization.

### 5. Memory benchmark artifact

Add `tests/benchmarks/benchmark_mlx_memory_residency.py`. It must emit JSON and Markdown with wall-clock median, peak/cache memory, `to_numpy`, `asarray`, `eval`, `synchronize`, `cleanup`, `clear_cache`, resize fallback count, RouteMaster sidecar materialization count, final encoder-boundary materialization, warnings, and fail-fast reasons.

## Validation plan

Run the requested targeted test set and full non-GUI suite:

```bash
.venv/bin/python -m pytest tests/test_route_master_sidecars.py -q
.venv/bin/python -m pytest tests/test_backend_resident_p4_hdr_grain.py -q
.venv/bin/python -m pytest tests/test_preprocess_resize_backend_residency.py -q
.venv/bin/python -m pytest tests/test_spatial_tiling.py -q
.venv/bin/python -m pytest tests/test_gpu_pipeline.py -q
.venv/bin/python -m pytest tests/test_hdr_projection_backend.py -q
.venv/bin/python -m pytest tests/test_mlx_memory_residency_governance.py -q
.venv/bin/python -m pytest --ignore=tests/gui -q
git diff --check
```

Run at least one residency benchmark:

```bash
.venv/bin/python tests/benchmarks/benchmark_mlx_memory_residency.py \
  --height 3000 --width 4000 --runs 3 \
  --output-json docs/reports/mlx-memory-residency-12mp.json \
  --output-markdown docs/reports/mlx-memory-residency-12mp.md
```

## Completion self-check

Before completion, verify that the implementation did not alter SDR/HDR math, percentile algorithms, or tile assembly defaults; budget enforcement remains opt-in; resize fallback preserves compatibility by default; preview and CPU paths are not fail-fast affected; final HEIC encoder materialization is treated as an encoder boundary; and all benchmark/test claims are backed by actual artifacts or explicitly marked as unavailable in the execution environment.
