# MLX Memory Residency Governance Plan - 2026-06-29

## Goal

Implement opt-in MLX memory residency governance for Spektrafilm: unified sync/materialization profiling, safe runtime peak-budget policy, explicit preprocess resize fallback policy, field-level RouteMaster sidecar helpers, and memory/residency benchmark artifacts without changing SDR/HDR math or default behavior.

## Non-goals

- Do not change HDR projection math, SDR film/print/scanner math, percentile algorithms, precision staircase behavior, or tile assembly defaults.
- Do not turn memory-budget enforcement on by default.
- Do not treat the final HEIC/encoder materialization boundary as a residency bug.
- Do not introduce a default native MLX resize path until parity is proven.
- Do not use performance benchmark results as a performance-optimization driver; benchmark output is evidence for memory/residency strategy only.

## Evidence Read

Local evidence:

- `docs/README.md` for project/doc structure.
- `docs/gpu/mlx-optimization-report-20260530.md` for existing full-frame MLX to NumPy residency breakpoints.
- `docs/reports/mlx-tile-assembly-benchmark-20260624-200634.md` for current tile assembly evidence and the decision not to change defaults.
- `deep-research-report.md` and `deep-research-report-2.md` for prior memory/residency context.
- Runtime, GPU, HDR, and required tests listed in the task request.
- Precise `rg` pass over materialization, sidecar, tiling, cleanup, cache, and route fields.

External primary-source guidance:

- MLX arrays use lazy evaluation and require explicit evaluation/synchronization at host boundaries.
- MLX exposes memory introspection such as peak and cache memory and cache clearing; profiling should sample those around materialization/sync operations.
- Apple Metal resource lifetime guidance supports treating retained cache/resource memory separately from live payloads and favoring explicit lifecycle boundaries for high-water debugging.
- Large-image memory strategy should prefer conservative tiling and explicit budgets, with warning/soft-enforcement before fail-fast behavior.

## Design

### 1. Unified Residency Profiling

Implement a single opt-in recorder in `src/spektrafilm/gpu/residency.py` and keep backend call interception in `MlxBackend`.

Recorder fields:

- operation: `asarray`, `to_numpy`, `eval`, `synchronize`, `cleanup`, `clear_cache`
- backend name
- caller label
- elapsed seconds
- shape, dtype, nbytes
- category: scalar, small_array, full_frame, materialize, final_encoder_boundary, sync, cleanup
- allowed/reason for materialization diagnostics
- MLX peak/cache memory before and after when available

Compatibility:

- Default off via contextvar; no runtime overhead beyond a no-op check.
- Existing `record_backend_residency()` remains the public context manager.
- Existing `summary()` keys remain available and are extended with new operation counts.
- JSON and Markdown export helpers write benchmark/test artifacts.

Static guard strategy:

- Add a test that scans production residency-sensitive files for direct `np.asarray(mx_array)`-style materialization in known boundaries.
- Prefer changing runtime output materialization to call `backend.to_numpy()` for GPU arrays so final readbacks are visible to the recorder.

### 2. Runtime Peak Budget Policy

Add settings:

- `gpu_peak_budget_mb: float | None = None`
- `gpu_budget_policy: "off" | "warn" | "soft_enforce" | "fail" = "off"`

Behavior:

- `off`: exact legacy behavior.
- `warn`: estimate memory after preprocess shape is known and record warnings/diagnostics only.
- `soft_enforce`: conservatively enable/set spectral and spatial tile rows when the estimate exceeds budget; keep sidecar policy minimal unless the user explicitly chose full/on-demand behavior.
- `fail`: fail fast only for clearly over-budget combinations after shape, backend, precision, materialize policy, HDR mode, route sidecar policy, upscale factor, LUT/direct spectral, and tiling settings are considered.

The first estimator is intentionally coarse: it estimates bytes per pixel from RGB/spectral/materialization/sidecar factors and uses large safety multipliers for HDR full sidecars and non-LUT direct spectral paths. It will not claim exact resident memory.

### 3. Preprocess Resize Fallback Policy

Add setting:

- `gpu_resize_policy: "cpu_fallback" | "warn" | "fail" | "native_if_available" = "cpu_fallback"`

Behavior:

- Default `cpu_fallback`: legacy path, `backend.to_numpy()` -> CPU cubic rescale -> `backend.asarray()`.
- `warn`: same fallback, but record explicit warning and countable timing.
- `fail`: for MLX/backend-resident full-resolution processing, raise before the fallback. Preview mode is allowed to fall back so preview is not mis-hit.
- `native_if_available`: feature-gated. Since no parity-proven native resize exists yet, it currently records that native resize is unavailable and falls back like `warn`.
- CPU backend behavior stays unchanged.

### 4. RouteMaster Sidecar On-demand Helpers

Extend `hdr_route_sidecar_policy` to include `"on_demand"` while preserving dataclass field access:

- `minimal`: fields stay minimal; helper calls are explicit.
- `full`: current full materialization path remains.
- `on_demand`: fields stay unset unless already available; diagnostics mark the policy; explicit helpers compute supported fields without implicit full-frame `to_numpy`.

Helpers in `runtime/route_master.py`:

- `get_route_look_chroma(master, backend_policy="backend"|"numpy", backend=None)`
- `get_material_detail_y(master, backend_policy="backend"|"numpy", backend=None)`

Rules:

- If a requested field already exists, return it in the requested residency form.
- Backend-resident computations use MLX operations when the source fields are MLX arrays.
- NumPy conversion of backend arrays requires an explicit backend with `to_numpy`; otherwise raise instead of hidden `np.asarray()`.
- No recomputation of route XYZ without color-space context.

### 5. Benchmark Artifact

Add `tests/benchmarks/benchmark_mlx_memory_residency.py` with CLI output:

- JSON: `docs/reports/mlx-memory-residency-YYYYMMDD-HHMMSS.json`
- Markdown: `docs/reports/mlx-memory-residency-YYYYMMDD-HHMMSS.md`

The benchmark records:

- scenario, image size, run count
- wall-clock median
- MLX peak/cache MiB
- counts for `asarray`, `to_numpy`, `eval`, `synchronize`, `cleanup`
- resize fallback count
- route sidecar materialization count
- final encoder boundary materialization count
- warnings and fail-fast reasons

The script supports the requested 12MP/24MP matrix where feasible, and the required completion run will persist a 12MP artifact.

## Implementation Steps

1. Extend settings validation and defaults.
2. Expand residency recorder and MLX backend interception.
3. Route runtime output materialization through backend readback where needed.
4. Add budget estimation/application after preprocess shape is known.
5. Add explicit resize fallback policy.
6. Add RouteMaster on-demand helpers and policy validation.
7. Add focused tests for policies, profiler output, static guard, and sidecar helpers.
8. Add benchmark script and run at least one persisted artifact.
9. Run required tests, `git diff --check`, and commit.

## Verification Commands

Required:

```bash
.venv/bin/python -m pytest tests/test_route_master_sidecars.py -q
.venv/bin/python -m pytest tests/test_backend_resident_p4_hdr_grain.py -q
.venv/bin/python -m pytest tests/test_preprocess_resize_backend_residency.py -q
.venv/bin/python -m pytest tests/test_spatial_tiling.py -q
.venv/bin/python -m pytest tests/test_gpu_pipeline.py -q
.venv/bin/python -m pytest tests/test_hdr_projection_backend.py -q
.venv/bin/python -m pytest --ignore=tests/gui -q
git diff --check
```

Benchmark:

```bash
.venv/bin/python tests/benchmarks/benchmark_mlx_memory_residency.py \
  --height 3000 --width 4000 --runs 3 \
  --output-json docs/reports/mlx-memory-residency-12mp.json \
  --output-markdown docs/reports/mlx-memory-residency-12mp.md
```

## Completion Self-check

- Evidence supports current memory/residency conclusions.
- No SDR/HDR math, percentile, precision staircase, or tile default changes.
- Budget enforcement is opt-in and default-off.
- Preview and CPU backend behavior are preserved.
- All new policies are disableable or compatible by default.
- Final encoder materialization is counted as an explicit boundary, not a bug.
- Direct `np.asarray(mx_array)` bypass risk is covered by code changes and static tests.
