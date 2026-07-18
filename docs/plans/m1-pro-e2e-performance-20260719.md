# M1 Pro end-to-end performance optimization plan

Date: 2026-07-19
Target: MacBookPro18,3, Apple M1 Pro (10 CPU cores), 16 GB unified memory

## Objective and invariants

Optimize the real Spektrafilm production pipeline for this Mac, including the
ordinary SDR route and RouteMaster/HDR export route. The reference is the
current `df811ff8` implementation. Film and paper profile data, wavelength and
LUT sampling, physical operations, defaults, public APIs, color-management
semantics, SDR appearance, HDR construction, output formats, and effective
float precision are fixed invariants. A candidate that cannot meet the
correctness and memory gates below will not be retained.

Pre-existing uncommitted profile/provenance work is outside this change and
will not be edited, staged, or committed.

## Measured execution graph

The production graph to benchmark is:

`input/RAW decode -> input color management -> crop/resize/auto-exposure ->`
`film expose -> film develop -> optional paper expose/develop -> scan master ->`
`SDR projection or RouteMaster/HDR projection -> output color/transfer -> encode`.

Preview is measured as a caller-selected size through the same simulation
stages. MLX measurements will explicitly evaluate/synchronize the returned
value within every timed interval. First-call compilation, warmed steady state,
cache memory, final materialization, and encoder time are reported separately.

## Baseline matrix

Before production edits, capture a reproducible reference output and timing
artifact for:

- about 12 MP and 50 MP deterministic linear inputs;
- CPU/NumPy and MLX float32, film-scan and film-plus-paper routes;
- representative negative/print, reversal-film, and high-dynamic-range inputs;
- SDR core simulation, RouteMaster/HDR rendering, and a real supported export;
- cold process/first render and repeated steady-state renders;
- synchronized wall time, per-stage time, MLX peak/cache memory, process RSS
  high water, conversion/sync counts, and output digests.

The 50 MP matrix may use fewer repetitions, but it must execute real per-pixel
work. A shape-only estimator is not an acceptance substitute.

## Profiling and implementation order

1. Add a reusable end-to-end benchmark/validation harness under `tests/benchmarks/` and
   record the unmodified baseline outside Git-tracked output.
2. Attribute CPU work with `cProfile` and stage timers; attribute MLX work with
   explicit synchronization, residency recording, operation counters, and
   peak/cache memory readings.
3. First pursue whole-pipeline wins: eliminate repeated full-frame work and
   materializations, keep arrays backend-resident, fuse compatible MLX passes,
   reuse immutable small derived tables with complete invalidation, and choose
   memory-bounded tile boundaries from measured data.
4. Then optimize remaining dominant kernels or CPU-only boundaries (including
   Metal/MLX or Accelerate-backed implementations where strict parity is
   demonstrated). Do not change a default from a microbenchmark alone.
5. Repeat the complete matrix after every retained architectural change and
   remove candidates that merely move work outside the timed/materialized
   boundary or regress 50 MP memory behavior.

## Baseline and retained directions

The synchronized 12 MP Portra 400 / Endura baseline was 12.240 s first-run and
25.597 s steady-state, with 12.40/12.53 GiB MLX peaks. The unmodified 50 MP
route exhausted Metal memory and did not complete. A first memory-safe
intermediate completed in 158.241 s with a 29.25 GiB MLX allocation high-water,
which confirmed that merely enabling completion was not sufficient.

Profiling identified three architectural causes rather than a spectral-model
cost: full-frame unreachable Poisson branches and retained RNG graphs, a large
batched 2D FFT workspace, and nine simultaneously resident interpolated grain
planes. Retained work therefore uses bounded lazy-graph evaluation, the exact
same full transform scheduled as chunked separable 1D FFT batches, and
layer-at-a-time interpolation. Large production stages now end explicit array
lifetimes, while HDR host materialization and the terminal encoder boundary
use bounded buffers and release projection-only state. No profile, sampling,
model operation, precision, parameter, output resolution, or route was changed.

## Correctness gates

- Preserve exact output when the optimized route retains operation order.
- For an equivalent float32 backend reordering, require `atol <= 1e-6` and
  report max/mean/percentile absolute error and ULP distribution; also validate
  finite values, monotonic ramps, tile seams, and repeated-run drift.
- Compare multiple film/paper profiles, ordinary and extreme parameters,
  disabled/enabled grain and halation, dimensions crossing tile boundaries,
  SDR, both RouteMaster modes, HDR gain/headroom fields, and final encoded
  image metadata/decodability.
- Keep the existing CPU/NumPy result as the authoritative behavior reference;
  no tolerance is widened and no existing xfail/skip is removed.

## Memory and lifecycle gates

- A real approximately 50 MP run must finish on 16 GB unified memory without
  unbounded retention. Record peak RSS and MLX peak/cache memory where the
  platform exposes them.
- Do not cache full-resolution image intermediates across renders. Reusable
  caches are limited to immutable profile-derived tables, compiled kernels, or
  explicitly bounded tiles and must invalidate on profile, backend, precision,
  LUT, color, and relevant parameter changes.
- Repeated profile/backend/size switches and consecutive runs must show no
  output drift, cache pollution, state leak, or monotonic live-memory growth.

## Completion

Run focused regressions plus the complete non-GUI suite, inspect the final diff,
record a concise report in `docs/reports/`, and create one focused local commit
containing only this optimization, its tests, benchmark harness, plan, and
report. If the measured safe speedup is below 2x at 50 MP, the report must show
the remaining synchronized hot spots and why eliminating them would violate an
invariant or the 16 GB memory limit.
