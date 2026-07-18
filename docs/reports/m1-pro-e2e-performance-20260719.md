# M1 Pro end-to-end performance result

Date: 2026-07-19

Machine: MacBookPro18,3, Apple M1 Pro, 16 GiB unified memory

Reference: `df811ff8` plus the unchanged working-tree profile data present at baseline

## Result

The production MLX path now completes repeated 49.77 MP film-plus-paper renders
in about 22.0-24.4 seconds. The original path exhausted Metal memory at this
size. The first intermediate that could finish took 158.24 seconds; the final
path is 7.19x faster than that memory-safe intermediate. A real 49.77 MP HDR
HEIC export also completed, produced a 68,029,021-byte file, and passed the
repository ISO 21496 validator.

No profile data, wavelength count, LUT resolution, spatial resolution,
physical operation, default effect, float precision, SDR/HDR rule, public API,
or output format was changed.

## Synchronized timings

All core intervals include MLX evaluation and synchronization. The output was
materialized to NumPy inside the measured boundary; digests were computed only
after that boundary. First and repeated operations were measured in one
process, while old full-resolution outputs were released between operations.

| Workload | Reference | Final | Speedup | Final MLX peak | Final RSS peak |
|---|---:|---:|---:|---:|---:|
| 12 MP Portra 400 / Endura, first | 12.240 s | 3.184 s | 3.84x | 3.00 GiB | 2.65 GiB |
| 12 MP Portra 400 / Endura, steady median | 25.597 s | 2.937 s | 8.72x | 3.00 GiB | 2.65 GiB |
| 49.77 MP Portra 400 / Endura, first viable intermediate | 158.241 s | 21.997 s | 7.19x | 6.35 GiB | 9.85 GiB |
| 49.77 MP Portra 400 / Endura, repeated | did not complete before memory fixes | 24.446 s | n/a | 6.35 GiB | 9.61 GiB |

The 12 MP MLX high-water fell from 12.40/12.53 GiB to 3.00 GiB, a 76% reduction.
The 49.77 MP intermediate high-water fell from 29.25 GiB to 6.35 GiB, a 78%
reduction. The final two-run 50 MP process high-water reported by
`/usr/bin/time -l` was 13.84 GB (12.89 GiB peak footprint), and its per-process
swap count was zero. MLX cache memory remained 1.11 GiB across the first and
repeated render rather than growing monotonically. The system-wide swap
counter was noisy on the already pressure-loaded machine (+1.08 GiB net for
the two-run final measurement, with other repeats decreasing); it is recorded
separately and was not used to claim speedup.

Additional 12 MP production cases remained in the same range:

- Fujifilm Provia 100F film-scan, peak-linear input 16, auto-exposure disabled:
  3.099 s first / 2.853 s repeated.
- Kodak Ektar 100 / Endura Premier, peak-linear input 8:
  3.732 s first / 2.860 s repeated.

## HDR and export

The 49.77 MP safe chemical-paper projection changed from 20.636 s and a
16.79 GB process footprint to 15.358 s and 13.79 GB. Its headroom remained
2.0, HDR maximum remained 1.6038818359375, and every value was finite.

The final real 49.77 MP `hdr-paper` export measured:

- synchronized RouteMaster core: 25.974 s;
- full process + chemical projection + raw payload + CoreImage HEIC encode:
  48.979 s;
- RSS peak: 10.58 GiB; MLX peak: 7.28 GiB;
- MLX cache after the encoder boundary: effectively zero;
- HEIC size: 68,029,021 bytes;
- ISO 21496 validation: passed with no errors. The two advisory warnings were
  the existing absence of optional `clli` hints on the base and `tmap` items.

## Architecture changes

1. Full-frame filming FFTs keep the identical padding, transform lengths, and
   frequency response, but large transforms are scheduled as bounded batches
   of separable 1D FFTs. This removes the large transient 2D FFT workspace.
2. Grain sampling now omits mathematically unreachable Poisson branches using
   scalar lambda bounds while preserving the original random-key splits.
   Knuth loop state is periodically evaluated, and accumulated large grain
   layers end their lazy graphs explicitly.
3. Layered grain interpolates and consumes one of the nine dye planes at a
   time through a Metal kernel with the same interpolation arithmetic, instead
   of retaining an HxWx3x3 cube.
4. Large production stages have explicit MLX evaluation/lifetime boundaries;
   dead full-frame locals are released as soon as their consumer is complete.
5. Large HDR host-side CCTF and route-chroma work is row-bounded. Terminal HEIC
   export retains only its SDR/HDR encoder inputs, releases RouteMaster and
   projection-only buffers, synchronizes, and clears the MLX allocator cache.
6. The reusable benchmark records dispatch, synchronized evaluation,
   materialization, process RSS, MLX peak/cache, system swap, residency events,
   deterministic output digests, full HEIC time, and ISO validation.

## Correctness evidence

- A same-process replay of the original 12 MP algorithms and the optimized
  result was element-for-element identical: maximum, mean, and 99.9th
  percentile absolute error were all 0. The final digest is
  `36ec069336c7f12e4243666e3152a724f2124d87c12bf72aefc823310676862a`.
- Every retained 49.77 MP optimization stage produced the same digest,
  `5bab44a71caedffa0528d52583c0d89900886e01eb1df97677dbc0809fdea62e`.
- Forced tests show exact equality for full 2D versus chunked separable FFT,
  full-cube versus layer-streamed interpolation/grain, bounded versus original
  Poisson execution, and whole-frame versus row-bounded HDR materialization.
- The final 12 MP default, Provia/high-range, Ektar/Endura, 50 MP SDR, HDR, and
  export results were all finite. No tolerance was widened.
- Complete non-GUI suite: 1,732 passed, 20 skipped, 4 expected failures; the
  six warnings are pre-existing numerical-domain warnings covered by tests.

## Rejected and remaining work

A spatially tiled substitute for the full filming transform reduced one
microbenchmark peak, but changed values (maximum error 1.786e-4, mean error
1.45e-5, including boundary differences). It was rejected because it violates
the 1e-6 parity gate. Changing the MLX allocator limit also did not lower the
active working set and was not retained.

The remaining synchronized costs are the exact stochastic grain passes, the
full-resolution scan/color projection, chemical HDR profile evaluation, and
CoreImage encoding. Removing them would require fewer model steps, different
sampling/precision, changed random statistics, a non-equivalent spatial
approximation, or a backend port whose profile/CCTF execution cannot currently
prove the same result. Those options were not merged.

## Reproduction

```bash
.venv/bin/python tests/benchmarks/benchmark_m1_pro_e2e.py \
  --width 4000 --height 3000 --route paper --runs 2

.venv/bin/python tests/benchmarks/benchmark_m1_pro_e2e.py \
  --width 8640 --height 5760 --route paper --runs 1

.venv/bin/python tests/benchmarks/benchmark_m1_pro_e2e.py \
  --width 8640 --height 5760 --route hdr-paper --runs 0 \
  --export-heic /tmp/spektrafilm-50mp-hdr-paper.heic

.venv/bin/python -m pytest --ignore=tests/gui -q
```
