# M1 Pro phase-two performance and precision result

Date: 2026-07-19

Machine: MacBookPro18,3, Apple M1 Pro, 16 GiB unified memory, macOS 26.5.1

Reference: `eac7b623` plus the untouched profile/provenance worktree

## Outcome

Two production changes passed the fixed precision and memory gates:

1. The MLX balanced Hanatos CPU fallback now combines RGB-to-XYZ and CAT16 into
   one cached float64 matrix pass before the existing float32 upload. The CPU
   path and the Mitchell LUT remain unchanged. On the stable 12 MP repeats,
   filming exposure fell from 2.07-2.14 s to 1.58-1.61 s; the final output is
   bitwise identical.
2. MLX preview rendering now retains at most materialized film and print CMY
   when the estimated post-crop/resize output is at most 4 MP. Scanner/output
   updates reuse print CMY, print updates reuse film CMY, and
   film/input/profile changes invalidate both. Direct scan,
   metadata/HDR, full render, oversized, non-contiguous, and non-MLX paths clear
   or bypass the cache.

No model, profile value, wavelength, LUT sample, interpolation rule, RNG call,
effect, dtype, output dimension, SDR/HDR rule, encoder quality, or phase-one
full-resolution lifetime control changed.

## Measured bottlenecks

The pre-edit synchronized 12 MP steady tail attributed 2.07-2.14 s to film
exposure, 0.97-1.00 s to film development/grain, and 0.52-0.54 s to scan. The
balanced Hanatos fallback performed a 144 MB MLX-to-NumPy boundary and two
full-frame float64 color-matrix passes before re-upload. This was the only
measured boundary that could be removed without changing the LUT or float32
result.

The final 49.77 MP steady medians remain dominated by film development/grain
(13.44 s), film exposure (10.99 s), scan (2.06 s), and input preprocessing
(2.07 s). The automated MLX residency counter recorded 43 `eval` calls, two
synchronizations, and three terminal `to_numpy` operations per repeated render.
MLX does not expose a trustworthy Metal command-dispatch count through this
runner, so no dispatch-count reduction is claimed. No evidence justified
disabling row-contiguity protection on existing custom kernels.

The 50 MP HDR export decomposition was:

| Component | Time |
|---|---:|
| RouteMaster core | 32.76 s |
| Chemical-paper HDR projection | 17.52 s |
| Raw encoder payload construction | 3.462 s |
| Swift/CoreImage encode | 3.985 s |
| Complete export call | 60.55 s |

The system encoder is therefore not the main remaining bottleneck. Chemical
projection is host-side because the MLX replacement failed the behavioral
parity contract described below.

## Precision staircase

The executable contract is
`tests/precision/staircase_contract.json`. It was locked before the accepted
production edit and evaluates:

```text
CPU float64 -> CPU float32 -> unfused MLX float32 -> candidate MLX float32
```

Every stage reports MAE, RMS, P95/P99/P99.9/max absolute and relative error,
float32 ULP distribution, worst pixel/channel/input condition, NaN/Inf counts,
and clipping classification changes. Terminal checks add Delta E 2000 tonal
and saturation partitions, 10-bit SDR/gain-map codes, HDR nits, headroom, and
capacity.

The four declared cases are now executed rather than only listed:

| Case | Profile | Route | Shape | Grain/spatial | Output |
|---|---|---|---:|---|---|
| negative_chemical_sdr | Kodak Portra 400 | chemical print | 11x17 | off/off | SDR |
| negative_chemical_hdr_grain | Fujifilm C200 | chemical print | 13x19 | on/on | HDR |
| positive_direct_sdr | Fujifilm Provia 100F | direct scan | 9x16 | off/on | SDR |
| positive_direct_hdr_grain | Kodak Ektachrome 100 | direct scan | 12x15 | on/off | HDR |

These cases use the actual profile density curves, 81-sample channel/base
density spectra and route-specific scan medium. Missing measured spectral
bands retain the production `density_to_light` NaN-to-zero boundary. Chemical
cases expose paper log exposure and CMY; direct cases intentionally do not
invent paper stages.

All aggregate and per-case relations passed the predeclared thresholds. Key
terminal results were:

| Relation/result | Maximum observed |
|---|---:|
| CPU64 -> final candidate Delta E 2000 | 2.535e-5 across actual-profile cases |
| CPU64 -> candidate HDR luminance | 6.166e-5 nit across actual-profile cases |
| CPU64 -> candidate SDR 10-bit code difference | 0 |
| CPU64 -> candidate gain-map 10-bit code difference | 0 |
| Current MLX -> candidate final SDR/HDR/gain map | bitwise identical |
| Hanatos fallback CPU64 intermediate error | 2.132e-14 |
| Hanatos float32 raw/log/final output | bitwise identical |

The aggregate synthetic stress image also passed all five relations. Its
CPU64-to-candidate Delta E 2000 maximum was 8.531e-6 and HDR maximum error was
1.549e-4 nit. There were no new non-finite values or clipping changes.

Grain validation used the same pre-generated Poisson counts for the math
staircase. The separate native-RNG audit passed its fixed sampling budgets:
maximum relative variance difference 0.00876, spatial autocorrelation
difference 0.00374, channel-correlation difference 0.00185, and relative power
spectrum difference 0.0272. RNG keys, shapes, call count, and layer order were
not changed.

## Performance results

All core times include `eval`, synchronization and output materialization.

| Workload | First | Steady median | Min-max | MLX peak |
|---|---:|---:|---:|---:|
| 12 MP paper, five steady | 3.649 s | 3.135 s | 3.067-3.751 s | 3.168 GB |
| 49.77 MP paper, five steady | 26.44 s | 29.36 s | 28.36-29.72 s | 6.818 GB |
| 49.77 MP HDR HEIC complete | n/a | 60.55 s | one full export | 7.216 GB core |

The output digests remain the phase-one values:

- 12 MP: `36ec069336c7f12e4243666e3152a724f2124d87c12bf72aefc823310676862a`
- 49.77 MP: `5bab44a71caedffa0528d52583c0d89900886e01eb1df97677dbc0809fdea62e`

The 12 MP pre-edit pressure-free tail was 3.60-3.74 s, while the final median
was 3.135 s. The reliable stage-level change is film exposure, down about 24%
on stable repeats. The whole-run comparison is directionally about 13% but is
not treated as a controlled machine-isolated benchmark.

The phase-two 50 MP measurements were slower than the phase-one 22-24 s core
and 48.98 s HDR export. The machine showed noisy system-wide swap movement even
though per-process swap remained zero. Consequently this report does not claim
a 50 MP core or HDR-export speedup. The final 50 MP MLX peak stayed at the
phase-one 6.35 GiB envelope; process peak footprint was about 12.09 GB and did
not cross the 16 GB device limit.

The real HDR HEIC was 68,029,021 bytes and passed ISO 21496 validation with no
errors. Its dynamic metadata sidecar was byte-for-byte equal to the phase-one
artifact: headroom 2.0, reference white 203 nits, mastering peak 406 nits,
target peak 1 EV, and display primaries/white point were unchanged. The
existing optional `clli` advisory warnings remained unchanged.

## Preview updates

Twenty alternating updates per class were compared with forced full
recomputation at 1600x1200. Every output was bitwise equal.

| Update | Cached median | Full median | Speedup | Cached range |
|---|---:|---:|---:|---:|
| Scanner | 0.145 s | 0.542 s | 3.75x | 0.137-0.151 s |
| Print | 0.155 s | 0.543 s | 3.51x | 0.150-0.161 s |
| Output | 0.138 s | 0.512 s | 3.72x | 0.132-0.139 s |

Across the 20-run sequences the MLX allocator cache remained in the
1.24-1.30 GB range instead of growing monotonically. Input-size switching,
Portra-to-C200 profile switching, direct-scan transition, metadata rendering,
and return to preview were also tested against fresh pipelines.

## Rejected experiments

- Backend-resident fast Hanatos was about 35% faster but changed the final
  output by up to 0.01109 (P99.9 0.00156); rejected.
- Raising the full-frame FFT threshold had no repeatable end-to-end gain and
  added 144 MB to MLX peak; rejected.
- Untiled scan was bitwise and about 8.5 ms faster, only about 0.24% end to end;
  not merged.
- A separable DIR FIR was faster but changed accumulation order; the locked
  evidence did not justify it, so it was not connected.
- MLX chemical HDR projection could remove the 17.52 s NumPy fallback, but the
  fixed behavioral reference required final gain-map/HDR arrays to remain
  bitwise. On a 257x263 encoded-SDR stress case it changed seven SDR codes and
  five gain-map codes (all by one), with HDR max error 3.576e-7. It was rejected
  and removed from the production diff despite the small numerical error.

No relaxed/fast math, reduced precision, altered reduction tree, custom RNG,
or new full-resolution retained graph is present in the accepted diff.

## Regression

- Final precision generator: `all_contract_failures: []` across the aggregate,
  four actual-profile cases, shared-random grain, native RNG statistics, and
  Hanatos fallback audit.
- Focused production/precision/HDR suite: 121 passed, 2 skipped.
- Complete non-GUI suite: 1,752 passed, 20 skipped, 4 expected failures, and
  six existing numerical-domain warnings in 80.63 s.
- `git diff --check`: clean.

## Reproduction

```bash
.venv/bin/python tests/precision/generate_precision_report.py \
  --native-grain --hanatos-fallback \
  --output /tmp/spektrafilm-precision-final.json

.venv/bin/python tests/benchmarks/benchmark_m1_pro_e2e.py \
  --width 4000 --height 3000 --route paper --runs 5

.venv/bin/python tests/benchmarks/benchmark_m1_pro_e2e.py \
  --width 8640 --height 5760 --route paper --runs 5

.venv/bin/python tests/benchmarks/benchmark_m1_pro_e2e.py \
  --width 8640 --height 5760 --route hdr-paper --runs 0 \
  --export-heic /tmp/spektrafilm-phase2-final-50mp.heic

.venv/bin/python tests/benchmarks/benchmark_m1_pro_preview_updates.py \
  --width 1600 --height 1200 --runs 20 --kind scanner

.venv/bin/python -m pytest --ignore=tests/gui -q
```
