# Metal/MLX Exactness-Preserving Optimization - 2026-07-26

Machine: MacBookPro18,3 (Apple M1 Pro, 16 GiB), macOS 26.5, MLX 0.31.2, Python 3.13.

## Goal and bar

Follow-up implementation pass after `docs/reports/metal-mlx-implementation-audit-plan-20260630.md`
and the 2026-07-19 M1 Pro bounding work. Find and land speed / memory improvements in the
MLX/Metal path under a strict gate:

- No precision loss and no value change: every landed change must be **bit-identical** on the
  MLX path (same digests), or a pure host-side overhead removal that does not touch the
  computation graph values.
- No behavior change: no default strategy, threshold, precision policy, fallback, tiling
  layout, or public API changes. Evaluation/cache cadence is treated the same way the
  2026-07-19 pass treated it: an "evaluation boundary only" scheduling detail, with the
  constraint that the M1 Pro 16 GiB memory envelope from
  `docs/reports/m1-pro-e2e-performance-20260719.md` (12 MP ≈ 3.0 GiB MLX peak,
  49.77 MP ≈ 6.35 GiB MLX peak, cache excursions up to ≈ 1.1 GiB were already accepted)
  must not regress meaningfully.

Verification tools used:

- bitwise comparisons (`np.ndarray.view(np.uint32/64)` equality) for candidate rewrites;
- `scripts/benchmark_mlx_runtime_hotpath.py` (12 MP end-to-end, stage timings);
- `tests/benchmarks/benchmark_m1_pro_e2e.py` (synchronized timings, MLX peak/cache, and
  deterministic output digests);
- the GPU regression suites (`tests/test_gpu_*`, `tests/test_backend_resident_*`,
  `tests/test_hdr_projection_*`, materialize-policy and fused/tile tests).

## Where the time goes today (baseline evidence)

12 MP (4000x3000) MLX float32 end-to-end via `scripts/benchmark_mlx_runtime_hotpath.py`
(warmup 1, run 2, no gpu_validate): total ≈ 3.99 s.

| Stage | ms |
|---|---:|
| filming.expose | 2520 |
| scanning.scan_print | 1006 |
| — SpectralLUTService.spectral_compute_scanner | 276 |
| SimulationPipeline.materialize | 234 |
| filming.develop | 208 |
| preprocess | 24 |
| printing.expose + develop | 2 |

Inside `filming.expose`, instrumenting `spektrafilm/gpu/kernels/fused_ops.py` at 12 MP
(halation active, 3 bounces, scatter 1.0; chunked-FFT path since 12 MP ≥ 8 MP threshold):

| Sub-phase | ms | calls |
|---|---:|---:|
| fused filter total | 1275 | |
| `_chunked_rfft2_mlx` | 607 | 3 |
| `_chunked_irfft2_mlx` | 355 | 3 |
| `_build_transfer_channel_mlx` | 185 | 3 |
| `mx.eval` (all, overlaps above) | 997 | 169 |
| `mx.clear_cache` | 3 | 172 |

Isolated microbenchmark of one 3080x4096 real 2D FFT decomposition (values all bitwise
identical across variants, confirming the 2026-07-19 "chunked == full" equivalence):

| Variant | ms | MLX peak MB |
|---|---:|---:|
| chunked 256, eval+clear_cache per chunk (current) | 21.8 | 202 |
| chunked 256, eval per chunk, no per-chunk clear | 9.3 | 404 |
| chunked 256, eval+clear every 4 chunks | 15.4 | 391 |
| whole `mx.fft.rfft2` | 2.7 | 454 |

The in-pipeline cost of the same pass is ~10x the isolated cost (≈ 200 ms per channel)
even though the FFT math itself is single-digit milliseconds. Two hypotheses were
tested against that gap and both were falsified in-pipeline: gating the per-chunk
`clear_cache` calls cut them from 172 to 12 but left the pass cost within noise, and
batching the per-chunk `mx.eval` calls 4:1 (bit-identical, verified) did not separate
from noise either (see rejected item 7). The residual cost rides on the per-chunk
evaluation boundaries themselves under real memory pressure — i.e. it is the price of
the 2026-07-19 memory bound, not recoverable overhead around it.

## Decisions confirmed against measurements (not landed, with reasons)

These were candidate ideas that measurement or the exactness gate killed. Recorded so the
next audit does not re-litigate them:

1. **Raising `_CHUNKED_FFT_MIN_PIXELS` / whole-frame `rfft2`**: 8x faster isolated and
   bitwise identical, but the chunked scheduling exists precisely to remove the large 2D
   FFT transient on 16 GiB at 49.77 MP. Threshold moves are a strategy change; out of scope.
2. **`mx.partition`-based percentile** in `hdr/projection.py`: order statistics are
   value-identical to `mx.sort` selection (verified incl. duplicate ties), but MLX 0.31.2
   `mx.partition` is ~1.8x *slower* than `mx.sort` at 24 M elements (92.7 ms vs 50.3 ms).
   Rejected on measurement.
3. **`mx.repeat` → broadcasting** in `_apply_path_to_white_backend` /
   `_compress_highlight_gamut_backend`: bitwise identical and same wall clock, and MLX
   peak memory was byte-identical (1344.1 MB both ways at 24 MP) — the lazy evaluator
   already handles it. No measurable win; not worth churn.
4. **Dropping the `mx.ones(...) *` seed multiply in the fused transfer builders**:
   NOT value-safe. Metal flushes float32 subnormals to zero, so `1.0 * x != x` bitwise
   when `x` is subnormal (measured: `1e-38 → 0.0`), and complex64 multiply also changes
   signed-zero patterns. Gaussian transfer tails do reach subnormal magnitudes, so the
   ones-multiply is (accidentally) semantic. Left exactly as is.
5. **Tile assembly `.at[].add` → concat**: already benchmarked 2026-06-24; kept per that
   report's gates. Not re-opened.
6. **Two-pass separable small-sigma Gaussian FIR**, **rfft2 in
   `fft_convolve_same_backend`**: change float32 summation order/algorithm → change bits.
   Rejected by the gate.
7. **Batching `mx.eval` every 4 chunks in `_chunked_rfft2/_irfft2`**: implemented,
   verified bit-identical end-to-end (same 12 MP pipeline digest), then **reverted**.
   Interleaved A/B/C at 12 MP (two passes, 3 runs each, medians of totals):
   original clear-every-chunk 2.84/2.95 s; budget-gated clears only 3.30/2.17 s;
   budget-gated + eval-every-4 2.52/2.68 s. The spread between passes of the same
   config (±0.5 s) exceeds the spread between configs, so the eval-batching benefit is
   unproven on this machine; the per-chunk eval cadence from 2026-07-19 was restored.
   The budget-gated clearing went through the same scrutiny and ended as an opt-in
   knob with a behavior-preserving default (landed change 1): gated clears are a
   strict subset of the previous clears, but the retained cache trended worse for
   wall clock at 49.77 MP under memory pressure, so the default stays 0.

## Landed changes

Each item lists motivation, the exactness argument, and its verification. Implemented in
this order; the doc was updated as each landed.

### 1. Cache-clear budget knob, default-off after measurement
(`spektrafilm/gpu/mlx_cache.py`)

- **What**: the per-chunk / per-tile / per-component / per-grain-state
  `mx.clear_cache()` calls in `gpu/kernels/fused_ops.py`, `gpu/kernels/tile_utils.py`,
  the Poisson loop of `gpu/kernels/grain.py`, and
  `model/grain.py::_materialize_large_grain_state` now go through
  `maybe_clear_cache(...)`. With the **default budget of 0 the cadence is byte-for-byte
  the 2026-07-19 clear-every-time behavior**; a positive
  `SPEKTRAFILM_MLX_CACHE_CLEAR_BUDGET_MB` gates clears on `mx.get_cache_memory()`.
  Stage-level boundaries (`_materialize_large_mlx_stage`, `MlxBackend.cleanup`, the
  final encoder boundary, preview-cache stores) and all `mx.eval` boundaries are
  untouched.
- **Why default-off**: a 256 MiB budget was implemented, verified bit-identical, and
  then measured end-to-end. 12 MP: within run-to-run noise. 49.77 MP paper route
  (4 process runs, 2 measurements each, this 16 GiB machine, active system swap):
  process CPU time **improved** ~14% (means 34.6 s → 29.8 s), MLX peak byte-identical
  (6.35 GiB) and end cache identical (1.19 GiB), but synchronized wall clock trended
  ~3 s **worse** (means ≈33.4 s → ≈36.4 s) — under memory pressure the retained cache
  competes with the OS pager, which is exactly the regime the 2026-07-19 pass tuned
  for. On a 16 GiB machine the aggressive cadence is the right default; the knob is
  kept (documented in the module) for machines with more unified memory, where the
  isolated chunk-pass benefit (21.8 ms → 9.3 ms without per-chunk clears at 12 MP FFT
  size) is real and paging is absent.
- **Why exact**: `clear_cache` frees *unused* pooled buffers only; it can never affect
  values, op order, or eval order. Verified: identical 49.77 MP output digests across
  all four runs, budget 0 and 256 alike (`446cdbde…`), and identical 12 MP pipeline
  digests (`3458b6e8…`).
- **Tests**: `tests/test_mlx_cache_budget.py` (default clears every call; env budget
  gates; invalid env falls back; missing probe clears conservatively).

Measured evidence for the knob decision (49.77 MP, 8640x5760, paper route,
`--disable-auto-exposure`, one process per cell, first + steady run each):

| Run | Budget | sync core s (first/steady) | CPU s (first/steady) | MLX peak | digest |
|---|---|---|---|---|---|
| A  | 0 (orig) | 36.48 / 32.25 | 34.4 / 32.7 | 6.35 GiB | `446cdbde…` |
| A2 | 0 (orig) | 28.91 / 35.83 | 39.1 / 32.1 | 6.35 GiB | `446cdbde…` |
| B  | 256 MiB  | 36.94 / 38.58 | 29.8 / 29.6 | 6.35 GiB | `446cdbde…` |
| B2 | 256 MiB  | 33.94 / 36.11 | 32.9 / 27.0 | 6.35 GiB | `446cdbde…` |

### 2. `MlxBackend` host-overhead fast paths (`gpu/mlx_backend.py`)

- **What**:
  - `asarray` / `to_numpy` / `eval` short-circuit the residency-profiling context manager
    when no `ResidencyRecorder` is active (0.96 µs → 0.06 µs per call measured; these are
    the most frequently called backend entry points). Recording behavior when a recorder
    IS active is unchanged.
  - `_is_mlx_array` uses a cached `isinstance` check against `mx.array` instead of a
    per-call `type(value).__module__.startswith("mlx.")` string test. (Alias kept as an
    instance-level callable so `tile_utils` and tests that call
    `backend._is_mlx_array(...)` see the same API.)
  - `nan_to_num` caches the per-dtype `big` clamp constant instead of rebuilding
    `np.finfo(...).max` + `mx.array` on every call. Same op sequence, same values.
  - `fmax` takes a fast path when `y` is a Python non-NaN scalar:
    `where(isnan(x), y, maximum(x, y))`, skipping the inner full-frame
    `where(isnan(y), …)` whose condition is constant-false. Bitwise-verified equal to
    the triple-`where` for scalar `y` (including NaN/±inf/-0.0 in `x`); the general
    two-array form is untouched. `fmax` sits in `safe_log10_backend`,
    `boost_highlights_backend`, and the tc-coordinate chain, all full-frame call sites.
- **Why exact**: profiling short-circuits and type checks do not touch arrays; the
  `fmax`/`nan_to_num` rewrites were verified bitwise on special values.
- **Guarded by**: existing residency/recorder tests (recording path unchanged), plus
  NEW `tests/test_gpu_backend.py::test_mlx_fmax_scalar_fast_path_matches_general_form`
  asserting bit-equality against the general form on NaN/±inf/-0.0.

### 3. Deterministic `compiled_elementwise` cache keys (`gpu/mlx_backend.py`)

- **What**: the cache key was `(name, id(function), hash(co_code), arg signatures)`.
  Closures are re-created per call, so `id(function)` only hits when CPython happens to
  reuse the freed address; under real allocation pressure this silently degrades to
  re-`mx.compile` + re-trace (~0.8 ms per call site per frame, measured 2.12 ms vs 1.33 ms
  per call for a 1000x1000x3 sRGB-encode chain). The new key is
  `(name, co_code hash, co_consts hash, closure-cell signature, arg signatures)` — fully
  deterministic across calls, and *stricter* where it matters: closure cell values
  participate by value for hashable scalars and by identity for objects, so two chains
  with identical bytecode but different captured constants can never share an entry
  (`hash(co_code)` alone cannot distinguish `value + 1.0` from `value + 2.0`; constants
  live in `co_consts`, which the old key ignored — the old key was carried by the `id()`
  term, the new key carries it explicitly).
- **Why exact**: a cache hit now requires identical bytecode, identical constants,
  identical captured values/objects, and identical arg shapes/dtypes — the compiled trace
  for such a pair is the same graph by construction. Misses only add a compile, never
  change values. Objects captured by identity are kept alive by the cached compiled
  function's own closure, so a stored `id()` can never be recycled while its entry lives.
- **Measured**: instrumenting `mx.compile` across steady-state 3 MP pipeline frames:
  old key re-compiled 1 chain per frame ([1, 1, 1, 1]), new key none ([0, 0, 0, 0]).
- **Guarded by**: `tests/test_gpu_backend.py::test_mlx_compiled_elementwise_cache_*`
  (same-name different-functions stay distinct; stable shape/dtype reuses; NEW:
  per-call re-created closures with identical captures must hit — the old key only
  passed that by allocator luck — and closures with different captured constants must
  miss).

### 4. CPU-side constant preparation caching in the JzAzBz gamut kernel
(`gpu/kernels/gamut_compress.py`)

- **What**: `_compress_rgb_jzazbz_chroma_mlx_kernel` re-ran `_split_float32_hi_lo` on the
  C_max table and every constant matrix on each frame, then re-uploaded ~22 arrays. The
  hi/lo splits and the numpy-side constant set are now `lru_cache`d per output color
  space (the underlying `_get_output_c_max_table` was already cached, so inputs are
  stable by construction). Uploads still go through `backend.asarray` per call (they are
  tiny and keeping them per-call avoids holding device buffers for inactive spaces).
- **Why exact**: identical numpy arrays in, identical device arrays out; caching pure
  CPU preprocessing of immutable inputs.

### 5. HDR projection percentile: kept `mx.sort` (documented, no code change)

`_percentile_backend` stays sort-based per measurement (see rejected item 2). The
profile diagnostic label `mx.sort_percentile` therefore also stays accurate.

## Verification

- [x] Bitwise digest parity, 12 MP full pipeline (Portra 400 / Endura, ProPhoto input,
      grain off, stochastic off): digest `3458b6e8307c2430…` identical before any change,
      after each landed change, and in the final state.
- [x] Bitwise digest parity, 49.77 MP paper route with default effects
      (`benchmark_m1_pro_e2e.py --width 8640 --height 5760 --route paper
      --disable-auto-exposure`): digest `446cdbdec404dc30…` identical across all four
      runs (budget 0 and budget 256 alike); MLX peak byte-identical at 6.35 GiB.
- [x] Candidate rewrites bitwise-verified on special values before landing
      (`fmax` scalar path, `nan_to_num` constant cache); FTZ killed the ones-multiply
      idea (see rejected item 4).
- [x] Test suites green with MLX present: `test_gpu_*` (204 passed / 8 skipped),
      `test_backend_resident_*` + `test_runtime_materialize_policy` + `test_gpu_pipeline`
      + `test_gpu_validate` (73 passed / 2 skipped), `test_hdr_projection_backend` +
      `test_hdr_routemaster_*` + `test_grain` + `test_gpu_density` (137 passed /
      2 skipped), `-k "fused or tile"` (58 passed / 4 skipped), plus the new
      `test_mlx_cache_budget.py` and the two new `test_gpu_backend.py` guards.
- [x] Complete non-GUI suite (`pytest --ignore=tests/gui -q`): **1759 passed,
      20 skipped, 4 xfailed** in 88 s; the 6 warnings are the pre-existing
      numerical-domain warnings noted in the 2026-07-19 report.

## Results

Attribution caveat: this machine had fluctuating background load and multi-GiB system
swap activity during the session, and interleaved A/B runs of the *same* configuration
differed by up to ±0.5 s at 12 MP and several seconds at 50 MP. End-to-end wall-clock
deltas at or below that level are reported but not claimed as wins. The claims this
pass stands behind are the controlled ones:

- `compiled_elementwise` re-traces per steady frame: **1 → 0** (measured by counting
  `mx.compile` calls over repeated `process()`; each avoided re-trace ≈ 0.8 ms of
  host time at 3 MP, and the cache is now deterministic instead of
  allocator-address-dependent).
- `asarray`/`to_numpy`/`eval` host overhead with no recorder active:
  **0.96 µs → 0.06 µs per call** (microbenchmark; these wrap every backend touch).
- `fmax(x, scalar)`: one full-frame `where` op removed per call, bitwise identical;
  sits inside `safe_log10_backend` (every expose), `boost_highlights_backend`, and the
  tc chain.
- JzAzBz gamut kernel CPU-side constant prep (hi/lo splits incl. the C_max table) now
  cached per color space instead of per frame.
- Cache-clear budget knob: default 0 keeps behavior identical; opt-in budget measured
  −14% process CPU at 49.77 MP (table in landed change 1) but is deliberately not the
  default on 16 GiB hardware because wall clock under memory pressure trended worse.

Raw same-harness end-to-end numbers, for the record
(`benchmark_mlx_runtime_hotpath.py`, 12 MP DNG, `mlx_full_res_validate_false`,
warmups 1, runs 2; before = start of session, after = final state, hours apart under
different background load — the delta overstates what the landed changes alone justify):

| Metric | Before | After |
|---|---:|---:|
| total | 3.994 s | 2.809 s |
| filming.expose | 2.520 s | 1.919 s |
| scanning.scan_print | 1.006 s | 0.606 s |
| filming.develop | 0.208 s | 0.208 s |
| materialize | 0.234 s | 0.060 s |

49.77 MP paper route: see the four-run table in landed change 1 (MLX peak 6.35 GiB in
every configuration, digest identical in every configuration).

## Follow-ups intentionally left open

- The chunked-FFT threshold itself (8 MP) and chunk sizes (256) are strategy constants
  from the 2026-07-19 pass; revisiting them needs a 50 MP memory study, not this gate.
- `scanning.scan_print` (≈1 s at 12 MP) is dominated by the spectral scanner LUT +
  full-frame color chain; nothing exactness-preserving and material was found this pass.
- CuPy/Halide backends were not touched.

## HDR projection path assessment - 2026-07-27

Follow-on review of the HDR export projection (`hdr/projection.py`,
`hdr/ideal_paper.py`, `hdr/light_table.py`, `hdr/routemaster_export.py`).
Assessment only - no code changed in this pass. Same machine and bar as above.
Timings: synthetic 4032x3024 frame (12.19 MP, seed 7, 0.5% hot pixels x6), warm
best-of-2/3, `kodak_portra_400` + `kodak_portra_endura`, MLX pipeline
(`compute_backend="mlx"`, `gpu_precision="float32"`,
`materialize_policy="backend"` - the GUI's MLX configuration).

### Production reality: the MLX projection path is dark

`hdr/projection.py` contains a complete MLX implementation of the generic
projection (`_build_result_backend`, `_build_hdr_y_from_route_backend`,
`_build_paper_generic_result_backend`), but three gates keep every real export
on the numpy path:

1. **CCTF gate.** `_sdr_rgb_backend` requires the master diagnostic
   `output_cctf_encoding=False`; the GUI hard-codes
   `params.io.output_cctf_encoding = True` (`spektrafilm_gui/params_mapper.py`,
   `_apply_io`), and `benchmark_m1_pro_e2e.py` sets `True` as well. This alone
   disables the backend path for every GUI export, both modes.
2. **Chemical-profile gate.** `project_hdr_ideal_paper` only *attempts* the
   backend path when no HDR curve profile exists for the film+paper pair.
   `curve_profiles_v2.json` covers 20 films x 8 papers = 160 = every bundled
   combination (128 safe -> numpy chemical rolloff; 32 unsafe -> numpy generic
   fallback). Paper-mode backend projection is reachable only for
   custom/unidentified stocks.
3. **Negative-scan gate.** Light-table masters for negative films go through
   `_positive_render_negative_scan_master`, which returns a numpy
   `sdr_legacy_rgb` (`runtime/pipeline.py` route), so `_is_mlx_array` fails
   even with gates 1-2 open.

Measured consequence (projection = `render_hdr_pair_from_master` only):

| Configuration (12.19 MP) | Projection | Path taken |
|---|---:|---|
| paper, production (cctf=True, safe profile) | 3.835 s | numpy chemical |
| light_table, production (cctf=True) | 3.536 s | numpy generic |
| paper, cctf=False, safe profile | 2.621 s | numpy chemical (decode skipped) |
| paper, cctf=False, profile identity stripped | **0.173 s** | **MLX generic** |
| light_table, cctf=False (negative film, gate 3) | 2.179 s | numpy generic |

The existing MLX path is ~20x faster than the numpy generic path it mirrors.
Linear x4.08 extrapolation to 49.77 MP gives ~14.4-15.6 s for the production
chemical projection, which cross-checks against the measured 15.358 s in
`m1-pro-e2e-performance-20260719.md`. During those seconds the GPU is idle and
the film pipeline's MLX buffers are still resident.

### Where the production chemical projection spends its time (12.19 MP)

| Block | Time | Notes |
|---|---:|---|
| `_sdr_rgb` x2 | 0.740 s x2 | colour CCTF decode; called in `project_hdr_ideal_paper` AND again in `_build_result` |
| standards statistics | 0.838 s | `_scene_luminance_summary` x2 (scene 0.500 + render 0.338); 4 separate full-frame `np.percentile` each |
| `_chemical_print_hdr_y` | 0.535 s | incl. 0.298 s full-frame profile curve interp |
| `_compress_highlight_gamut` | 0.267 s | numpy twin already uses broadcast (no `np.repeat`) |
| `_headroom` | 0.205 s | max-channel + percentile |
| `_apply_path_to_white` | 0.147 s | materializes full-frame `np.repeat(hdr_y, 3)` |
| `_route_chroma` | 0.136 s | derived (sidecar policy "minimal" leaves `route_look_chroma=None`) |
| `encode_gain_map_log2` | 0.076 s | |
| `_scene_authority` x3 | 0.006 s x3 | validated three times per projection |

Caveat: the synthetic frame has ratio>1 fraction 0.50 (much hotter than typical
photos), so the curve-interp and percentile shares shrink on LDR-ish content;
the `_sdr_rgb` double decode does not.

### Tier 1 - bit-exact, no behavior change (implementable under this bar)

1. **Deduplicate `_sdr_rgb`.** Computed twice per paper projection
   (`project_hdr_ideal_paper` and again inside `_build_result`); same pure
   function of the same immutable master -> byte-identical reuse.
   Measured -0.74 s at 12 MP (~19% of the production projection), ~-3.0 s at
   49.77 MP. The same plumbing dedupes `_scene_authority` (x3 -> x1) and shares
   `luminance_y(sdr)`; with backend-resident masters that also removes
   duplicate MLX->host copies.
2. **numpy `_apply_path_to_white`: `np.repeat` -> broadcast.** Measured
   bit-identical (`.tobytes()` equal) and -0.03-0.05 s at 12 MP; removes an
   H x W x 3 float32 transient (~600 MB at 49.77 MP). The numpy
   `_compress_highlight_gamut` already uses the broadcast form; only the
   MLX twin materializes `mx.repeat` - same one-line fix there.
3. **MLX-path twins** (currently dark, same exactness arguments, keeps the
   path healthy for Tier 2): dedupe `_sdr_rgb_backend` (x3 per paper-generic
   projection) and repeated `_as_y_backend` validation (each validation is a
   full `isfinite`+`all`+sync: measured 6.2 ms RGB + 2.1 ms Y per call at
   12 MP), `mx.repeat` -> broadcast x2, `y*0+limit` full-frame constants ->
   scalars, and the material-detail-is-ones scalar shortcut (must keep the
   final `extension * c` multiply - Metal FTZ, see rejected item 4 above).
   Error-raising order for invalid inputs is preserved by keeping first
   occurrences of each validation.
4. **Route-pipeline reuse for mode-flipped exports** (`process_with_master`
   builds a complete new `SimulationPipeline` whenever `io.scan_film` doesn't
   match the requested route - every light-table export from a paper-mode GUI
   session pays full pipeline construction). Host-side and deterministic, but
   holding a second pipeline needs a 16 GiB memory check first. Tier 1.5.

Estimated Tier-1 total on the production paper route: ~0.8 s of 3.8 s at
12 MP; ~3.2 s of ~15.5 s at 49.77 MP. Verification: digest A/B of the exported
HEIC pair plus the projection diagnostics, same harness as above.

### Tier 2 - requires sign-off (bits or metadata change on affected routes)

- **A. Linear-master export route.** Decouple the RouteMaster SDR domain from
  the GUI's encoded output (the pipeline has the linear SDR before
  `_apply_cctf_encoding_and_clip`; the projection decodes right back today),
  keep the negative-scan positive render backend-resident, and let
  light_table + paper-generic ride the existing MLX path: 3.5 s -> ~0.2 s
  class at 12 MP (~20x on the measured pair). Changes bits (decode round-trip
  vs direct linear; CPU vs GPU float) and the backend path deliberately omits
  the full-frame standards statistics (metadata content differs - that is why
  this is Tier 2).
- **B. Chemical rolloff MLX port.** Removes the remaining ~2.6 s at 12 MP;
  the interp-kernel pattern already exists in the gamut_compress kernels.
  Changes bits on the 128 safe bundled combinations.
- **C. Below-white masked curve eval** in the numpy chemical path (below-white
  pixels are overwritten by `np.where(scene_y <= white, sdr_y, hdr_y)`):
  candidate -0.1-0.3 s at 12 MP; the ratio==1.0 boundary rounding argument
  holds on paper but this MUST be digest-A/B'd; medium fragility, do last or
  skip.

### Measured dead ends (this assessment)

- Merging the 4 separate `np.percentile` calls in `_scene_luminance_summary`
  into one vector call: 0.483 s -> 0.161 s for the block but **not**
  bit-identical (measured `identical_bits=False`) - rejected under this bar.
- `np.nanpercentile` -> `np.percentile` (inputs are validated finite):
  bit-identical here but no win (0.120 s vs 0.119 s at 12 M) - pointless churn.
- Carry-over from the July-26 pass: `mx.partition`/`mx.topk` percentile ideas
  stay dead on MLX 0.31.2 (topk routes through partition).

Suggested order: Tier 1 items 1-2 (production-visible, digest-verifiable
immediately), then 3, then decide Tier 2 A - it is the single biggest lever on
HDR export latency.
