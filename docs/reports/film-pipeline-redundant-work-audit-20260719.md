# Spektrafilm film-pipeline redundant-work audit

Date: 2026-07-19
Scope: `Simulator` / `SimulationPipeline` runtime path, CPU and MLX where
available, including plain SDR, metadata, RouteMaster/HDR, and the print/scan
stages.

This audit intentionally excludes the pre-existing profile provenance changes
already present in the worktree. No profile values, wavelength grids, LUT
resolution, precision policy, or physical model were changed here.

## Execution graph and baseline evidence

The measured path is:

`SimulationPipeline._preprocess` -> `FilmingStage.expose` ->
`FilmingStage.develop` -> optional `PrintingStage.expose/develop` ->
`ScanningStage.scan` / `scan_master` -> SDR projection or RouteMaster
materialization.

`process_with_master` uses the metadata-aware filming call and then builds the
route sidecars. `process` and the topology path use the plain filming call.

The GUI controller was also traced at its runtime boundary: plain requests use
the image-only process, HDR metadata requests use `process_with_metadata`, and
HDR export requests use `process_with_master`. Preview/display conversion and
export conversion are separate, intentionally typed boundaries after runtime
processing; they are not duplicate film/paper simulations.

Baseline measurements used:

- `cProfile` on a warmed 256x256 CPU print route: 15,660 calls; the profiling
  trace showed 10 `density_to_light` calls and 3 full callback entries through
  `PrintingStage._film_cmy_to_print_log_raw` per render.
- Opt-in call counting on four warmed 192x192 CPU renders: the print route
  entered `_film_cmy_to_print_log_raw` 12 times (three per render), while the
  film-scan route had no print callback. The normal route also entered the
  filming tc-LUT lookup six times including two construction-time mid-gray
  probes, and once per render thereafter; the existing LUT cache already
  prevents a rebuild.
- The old path calculated two full-size `_raw_luminance_y` arrays in every
  plain filming exposure even though `process` discarded both values.
- The existing MLX hot-path benchmark was run with two warm-ups and five
  synchronized steady-state samples at 256x256. The optimized current path
  reported warm-ups of 346.26 ms and 33.36 ms, then 31.57/32.78/30.22/32.96/
  30.79 ms; the first sample includes the normal MLX compilation/materializing
  effects and is not treated as steady state.

## Confirmed and fixed

### 1. Do not construct filming luminance sidecars for plain exposure

Original redundant work: `FilmingStage.expose()` delegated to
`expose_with_metadata()`, which computed luminance before and after the spatial
filming chain. Plain SDR, `process_with_metadata`'s image path, and topology
collection only need `log_raw`.

Implementation: both public methods now share `_expose_core`; the caller passes
`include_metadata=False` for the plain path and `True` for RouteMaster. The
metadata path keeps the original order and values.

Evidence:

- Plain calls counted zero luminance passes; metadata-aware RouteMaster calls
  counted exactly two.
- For four representative profile pairs, CPU optimized-vs-forced-old output
  was `array_equal=True`, `max_abs=0.0`. The same held for two MLX pairs. A
  separate plain and RouteMaster comparison on CPU and MLX also produced
  `array_equal=True`, `max_abs=0.0` for every returned field checked.
- Existing filming, RouteMaster, HDR projection, and full-pipeline tests pass.
- The change removes two approximately full-frame float32 sidecars from the
  ordinary MLX path, reducing both work and peak live data for large inputs.

### 2. Skip print black/white reference exposures when correction cannot use them

Original redundant work: `PrintingStage.expose()` always computed black and
white 1x1 reference exposures, even when scanner black/white correction was
disabled. The references are consumed only by negative-print correction.

Implementation: `ColorReferenceService.requires_printing_references()` owns
the condition: correction enabled, print route active, and print profile is
negative. `PrintingStage.expose()` computes the two references only under that
condition. Enabling a correction retains the old three callback entries (two
references plus the real image).

Evidence:

- Default correction-off count changed from 3 to 1 callback per print render.
- Correction-on count remains 3.
- The old-path emulation and optimized path were exactly equal for CPU and MLX
  across the representative profiles above.
- In the same synchronized 256x256 MLX comparison, steady-state median was
  16.16 ms optimized versus 16.94 ms with the old dead work; the print-stage
  timing was 0.36 ms versus 2.53 ms. CPU medians were 162.52 ms versus
  162.17 ms, so no CPU speedup is claimed because that difference is noise.
- In a 128x128 paper RouteMaster comparison, CPU medians were 38.71 ms versus
  39.82 ms and MLX medians were 8.77 ms versus 11.26 ms. These are supporting
  measurements, not a claim of a fixed percentage on all hardware.

## Evidence-backed opportunities not implemented

- **Cache every profile-derived sensitivity/illuminant scalar:** the audit
  confirmed repeated construction in filming, printing, and scanning. The
  arrays are small relative to pixel work, while mutable enlarger filter
  fields, `soft_update`, backend changes, LUT settings, and profile replacement
  create several invalidation dimensions. The existing LUT and backend-table
  caches already cover the large reusable objects. No change was made without a
  material end-to-end gain and a complete key/refresh design.
- **Cache `standard_illuminant`/normalization inside scanning:** repeated per
  render, but not a measured dominant cost; it is also coupled to output color
  space and viewing profile. Deferred as low-value.
- **Add a global `load_profile` cache:** profile objects are mutable and callers
  clone/update them. A global cache would need ownership and copy semantics
  that could silently share state across GUI tasks. Profile loading is setup
  work, not a hot per-image stage. Rejected for this audit.
- **Bypass output gamut compression for `algorithm='off'`:** the helper has a
  no-op branch, but its current CPU/backend dtype coercion is part of the
  established diagnostic behavior. Changing the caller to return the input
  object directly would alter dtype/layout and possibly downstream behavior.
  Deferred pending an explicit identity-contract test.
- **Remove CPU/MLX resize transfers or change tile assembly:** existing reports
  and residency tests identify the resize fallback and MLX tile assembly as
  explicit, policy-controlled boundaries. Changing them would require a
  separate parity and memory study; this audit leaves their behavior intact.
- **Share RouteMaster sidecars across export callers:** the current
  `minimal`/`full`/`on_demand` policy is already an explicit lifecycle contract.
  Full sidecars are intentionally materialized only when requested, so no
  duplicate was proven in the default route.

## Safety and memory checks

- Full non-GUI suite: **1719 passed, 20 skipped, 4 xfailed** in 73.57 s.
  Six existing runtime warnings were reported by the suite; none came from the
  changed files.
- Focused MLX/residency/HDR/RouteMaster set: **95 passed**.
- GUI controller runtime/display boundary tests: **21 passed**. The remaining
  GUI tests were not needed for this runtime-only change and are subject to
  the repository's display/QApplication requirement.
- MLX residency benchmark at 256x256, three runs after warm-up: median 84.22
  ms, 3 `to_numpy`, 35 `asarray`, 3 `eval`, 1 synchronize, 1 cleanup, zero
  route-sidecar materializations, and one final encoder boundary. No fail-fast
  reason was recorded.
- CPU repeated-render `tracemalloc` check: after three warm-up renders and 12
  repeated renders, the top-ten net allocation delta was 1.6 KiB; no
  monotonic task-state growth was observed.
- A 50 MP shape-only MLX budget preflight used 5760x8640. Estimated peaks were
  7403.9 MiB for backend/minimal, 11960.2 MiB for numpy-float64/full, and
  13668.8 MiB for full sidecars with tiling disabled; all remain below 16 GiB
  in the estimator. With an 8192 MiB soft budget, the existing policy selected
  512-row spectral and spatial tiles. The optimization removes two ordinary
  full-frame luminance sidecars and therefore does not increase this estimate.
  A real 50 MP render was not forced because the existing project evidence
  already identifies that configuration as close to the 16 GB unified-memory
  limit; the shape-only preflight is the safe validation boundary here.

## Final assessment

Two safe optimizations were implemented and regression-tested. They remove
provably dead work from the ordinary path and preserve the metadata/HDR path.
The remaining repeated profile-derived setup work is real but either small or
has invalidation/lifecycle risk disproportionate to the measured benefit. The
plan and this report are the durable evidence for the decision not to widen the
patch.
