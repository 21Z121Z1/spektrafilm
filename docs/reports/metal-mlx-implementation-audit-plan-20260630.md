# Metal/MLX Implementation Audit Plan - 2026-06-30

## Goal

Produce a source-grounded audit of Spektrafilm's current Apple Silicon MLX/Metal implementation and identify concrete improvement opportunities without changing runtime behavior in this pass.

## Scope

- Inspect current MLX backend selection, dtype policy, residency accounting, materialization boundaries, custom Metal kernels, fused MLX paths, HDR projection, tile assembly, and benchmark/test coverage.
- Cross-check recommendations against existing Spektrafilm precision and SDR parity constraints.
- Use primary sources for external best-practice claims, preferring official MLX and Apple Metal documentation.
- Write the durable output as a dated report under `docs/reports/`.

## Out Of Scope

- No production code changes.
- No default strategy changes for tile assembly, HDR projection, precision policy, or fallback behavior.
- No generated benchmark artifacts unless an existing test or lightweight command is needed to verify the documentation edits.
- No edits outside `docs/`, because this is a documentation/audit task.

## Audit Passes

1. Map the current implementation surface:
   - `src/spektrafilm/gpu/backend.py`
   - `src/spektrafilm/gpu/mlx_backend.py`
   - `src/spektrafilm/gpu/residency.py`
   - `src/spektrafilm/gpu/precision_policy.py`
   - `src/spektrafilm/gpu/kernels/*.py`
   - `src/spektrafilm/hdr/projection.py`
   - runtime materialization points in `src/spektrafilm/runtime/`
2. Review existing reports and benchmark evidence:
   - `docs/gpu/mlx-optimization-report-20260530.md`
   - `docs/reports/mlx-float32-color-precision-audit-20260629.md`
   - `docs/reports/mlx-float32-color-precision-plan-20260629.md`
   - `docs/reports/mlx-memory-residency-12mp.md`
   - `docs/reports/mlx-memory-residency-24mp.md`
   - `docs/reports/mlx-tile-assembly-benchmark-20260624-200634.md`
3. Review relevant regression and benchmark tests:
   - `tests/test_gpu_*`
   - `tests/test_backend_resident_*`
   - `tests/test_runtime_materialize_policy.py`
   - `tests/test_hdr_projection_*`
   - `tests/benchmarks/*mlx*`
   - `benchmarks/benchmark_mlx_tile_assembly.py`
4. Compare against primary-source MLX/Metal guidance:
   - MLX custom Metal kernels and compilation APIs.
   - MLX lazy evaluation, memory/cache controls, streams/devices, dtypes.
   - Apple Metal shader/memory/threadgroup guidance.
5. Produce prioritized recommendations:
   - correctness and precision gates,
   - residency and synchronization boundaries,
   - kernel API/launch hygiene,
   - memory pressure and cache management,
   - benchmark methodology,
   - observability and documentation.

## Acceptance

- Final report names concrete files/functions and explains each recommendation's expected value, risk, and verification gate.
- Existing unresolved constraints are preserved explicitly instead of hidden behind "best practice" language.
- `docs/README.md` links to the final report.
- Documentation edits are syntax-checked enough to catch broken Markdown structure.
