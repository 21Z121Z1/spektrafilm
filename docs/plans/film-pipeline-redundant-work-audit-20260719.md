# Film pipeline redundant-work audit plan

## Scope and initial execution graph

The audit follows the canonical runtime path rather than isolated helpers:

`Simulator` / `simulate*` -> `SimulationPipeline` -> preprocess and topology taps ->
`FilmingStage` -> `PrintingStage` -> `ScanningStage` -> output/materialization.

The same pipeline also exposes `process_with_metadata` and `process_with_master`,
where the RouteMaster/HDR export path may share the photographic stages but has
additional sidecar and encoder boundaries. Profile loading and derived spectral,
enlarger, LUT, color-reference, and backend tables are inspected separately from
per-pixel work. GUI preview/save behavior is treated as a caller of these same
boundaries, not as a second implementation.

## Measurement method

1. Record a clean, repository-preserving baseline: interpreter/dependency state,
   targeted non-GUI tests, and representative CPU timings.
2. Instrument stage/service entry points and expensive conversion/materialization
   boundaries with opt-in counters/timings. Use call counts and array metadata to
   distinguish duplicate work from required repeated output passes.
3. Run warm-up plus synchronized steady-state measurements for CPU and MLX when
   available. For MLX, keep lazy execution and explicit `eval`/`to_numpy` at the
   measured boundary; record first-run and steady-state separately.
4. Use focused `cProfile`/`pstats`, allocation/count probes, existing benchmark
   scripts, and targeted topology/HDR tests. Do not infer a hot spot from static
   code reading alone.

## Candidate questions

- Are profile-derived arrays and service tables rebuilt when only downstream
  parameters change, or when the same profile is reused?
- Do topology taps, preview, SDR, HDR, and RouteMaster paths recompute a shared
  photographic stage or materialize/convert the same value more than once?
- Are no-op settings (disabled effects, unity resize, identity color operation,
  or absent optional LUT) still allocating and traversing full arrays?
- Do CPU/MLX boundaries introduce avoidable `asarray`, `astype`, copy,
  synchronization, or NumPy materialization in the hot path?
- Does tile assembly or output conversion duplicate work or retain data beyond
  the required lifetime, especially for 50 MP inputs?

## Correctness and safety gates

Any implementation must have an explicit cache key/invalidating owner or a
strictly local no-op fast path. It must preserve current float precision,
operation semantics, output layout, and user-visible SDR/HDR behavior. Tests will
cover multiple built-in film/paper pairs, default and boundary parameters,
CPU/MLX where available, SDR/HDR, tile-boundary dimensions, disabled/no-op
settings, repeated profile use, profile/parameter/backend switching, and a
memory-bounded 50 MP smoke or documented hardware limitation. Comparisons use
exact equality where the operation is unchanged and the repository's strictest
appropriate tolerance only where an existing backend requires it.

## Deliverables

- This plan, updated if the measured graph changes.
- A concise audit report separating confirmed fixes, evidenced but deferred
  opportunities, and rejected unsafe/low-value options.
- Targeted regression tests and benchmark output with first-run/steady-state
  context.
- One focused local commit containing only the audit/optimization changes; all
  pre-existing user changes remain untouched.

## Measured implementation decision

The first measurement pass confirmed two safe local skips: plain filming was
building two discarded full-frame luminance sidecars, and print exposure was
building two discarded black/white reference exposures when correction was
disabled. Both were implemented with explicit caller/parameter guards. The
profile-derived scalar/table cache ideas were measured but deferred because
their arrays are small and their invalidation surface includes mutable
`soft_update` fields, backend selection, and profile replacement. Detailed
measurements, exact-output checks, and the final rejection ledger are in
[`../reports/film-pipeline-redundant-work-audit-20260719.md`](../reports/film-pipeline-redundant-work-audit-20260719.md).
