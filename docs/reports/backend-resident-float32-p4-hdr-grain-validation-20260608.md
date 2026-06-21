# Backend Resident Float32 P4 HDR/Grain Validation - 2026-06-08

## Scope

Target: Python GUI runtime photographic adjustments after image/RAW load and
before GUI preview/export should stay MLX/Metal resident at full resolution with
`gpu_precision="float32"` and `materialize_policy="backend"`.

Non-goals remain RAW decode, GUI display materialization, explicit export
materialization, and HDR/RouteMaster sidecar encoding. Those are explicit CPU
boundaries and are timed separately.

## Implementation Results

- Added MLX backend output gamut compression for `jzazbz` and `cam16ucs`.
- Hardened backend perceptual-chroma radius and Reinhard knee math against
  float32 overflow so large OOG `jzazbz` chroma no longer collapses through
  `nan_to_num()` to black.
- Added `rgb_to_raw_mallett2019_backend()` and routed `FilmingStage` through it
  when a float32 GPU backend is active.
- Added P4 HDR/grain/RouteMaster tests and a GUI-adjustment residency matrix
  covering halation, grain, DIR couplers, camera/enlarger diffusion, glare,
  chemistry, scanner blur/unsharp, scan-film and print routes, all output gamut
  algorithms, and both RGB-to-raw methods.
- Added `tools/benchmark_backend_resident_p4_validation.py` with explicit
  backend, precision, materialize policy, route, flags, output type/dtype,
  readback summary, stage timings, sync time, and real-sample skip reasons.

## Validation Evidence

Targeted tests:

```text
.venv/bin/python -m pytest tests/test_backend_resident_p4_hdr_grain.py tests/test_backend_resident_runtime_boundaries.py tests/test_gpu_color_chain.py tests/test_gamut_compression.py -q
152 passed, 3 warnings in 10.66s
```

Regression gates:

```text
.venv/bin/python -m pytest --ignore=tests/gui -q
1497 passed, 7 skipped, 4 warnings in 67.05s

.venv/bin/python -m pytest tests/gui/test_controller_runtime_module.py tests/gui/test_controller_layers.py tests/gui/test_controller_output.py tests/gui/test_controller_flow.py -q
87 passed in 1.37s

git diff --check
passed
```

Benchmark:

```text
.venv/bin/python tools/benchmark_backend_resident_p4_validation.py --backend mlx --runs 1 --warmups 0 --include-real --include-scanner-lut
```

Artifacts:

- `docs/reports/backend-resident-float32-p4-validation-benchmark-20260608-215950.json`
- `docs/reports/backend-resident-float32-p4-validation-benchmark-20260608-215950.md`
- `docs/reports/backend-resident-float32-p4-validation-benchmark-20260608-224101.json`
- `docs/reports/backend-resident-float32-p4-validation-benchmark-20260608-224101.md`
- `docs/reports/backend-resident-float32-p4-validation-benchmark-20260608-224912.json`
- `docs/reports/backend-resident-float32-p4-validation-benchmark-20260608-224912.md`
- `docs/reports/backend-resident-float32-p4-validation-benchmark-20260609-110920.json`
- `docs/reports/backend-resident-float32-p4-validation-benchmark-20260609-110920.md`

The real sample decoded through the GUI RAW path at full resolution:
`scratch/IMG_9121_converted.DNG -> [3024, 4032, 3] float32`.

All 25 benchmark workloads completed with `status=ok`; maximum
`unallowed_to_numpy` across all runs was `0`.

## Real DNG MLX Results

| Workload | Route | Flags | Runtime | Sync | Output | Unallowed readbacks |
|---|---|---|---:|---:|---|---:|
| runtime_grain_off_hdr_off | print_scan | none | 3.011s | 2.912s | `mlx.core.array mlx.core.float32` | 0 |
| runtime_grain_off_hdr_on | print_scan | hdr_metadata | 4.959s | 2.862s | `mlx.core.array mlx.core.float32` | 0 |
| runtime_grain_on_hdr_off | print_scan | grain | 19.226s | 18.513s | `mlx.core.array mlx.core.float32` | 0 |
| runtime_scan_film_grain_off_hdr_off | scan_film | none | 3.248s | 0.559s | `mlx.core.array mlx.core.float32` | 0 |
| preview_export_grain_off_hdr_off | print_scan | preview,export | 1.301s total | 1.050s | `mlx.core.array mlx.core.float32` | 0 |
| runtime_grain_off_hdr_off_scanner_lut_on | print_scan | scanner_lut | 1.641s | 1.592s | `mlx.core.array mlx.core.float32` | 0 |
| runtime_grain_on_hdr_off_scanner_lut_on | print_scan | grain,scanner_lut | 33.272s | 32.972s | `mlx.core.array mlx.core.float32` | 0 |

After restoring resident MLX grain (`SF-20260609-001`), the latest
full-resolution DNG benchmark artifact
`backend-resident-float32-p4-validation-benchmark-20260609-110920.md` still
completed all 25 workloads with `Unallowed to_numpy = 0`. The updated real DNG
grain rows were:

| Workload | Route | Flags | Runtime | Sync | Output | Unallowed readbacks |
|---|---|---|---:|---:|---|---:|
| runtime_grain_on_hdr_off | print_scan | grain | 9.007s | 8.657s | `mlx.core.array mlx.core.float32` | 0 |
| runtime_grain_on_hdr_off_scanner_lut_on | print_scan | grain,scanner_lut | 9.469s | 9.142s | `mlx.core.array mlx.core.float32` | 0 |

Scanner timings on the full-resolution DNG were not the dominant measured
runtime: `SpectralLUTService.spectral_compute_scanner` stayed around
0.002-0.004s in these benchmark rows, and `ScanningStage.scan` stayed around
0.012-0.015s. The current high-cost full-resolution path is grain, where most
wall time appears at MLX synchronization.

## Accuracy Notes

- `cam16ucs` backend output matched CPU reference within `3e-6` in the
  regression test matrix.
- `jzazbz` stays backend-resident with no readback, but it does **not** meet
  the project-wide `1e-6` deterministic CPU/NumPy parity target against the
  existing float64 CPU reference. A NumPy float32 reproduction of the same
  JzAzBz/PQ formula shows the same class of error, and MLX reports that
  float64 is not supported on the GPU. The original P4 coverage therefore used
  a documented `5e-4` absolute tolerance for this one algorithm; the 2026-06-09
  follow-up below keeps strict `1e-6` assertions as expected-failing gates
  instead. Falling back to CPU would restore strict parity but would reintroduce
  the full-frame readback gap this P4 work was meant to close.
- Follow-up precision probes on 2026-06-09 confirmed that this is not a simple
  MLX graph-fusion issue: an MLX `float64` diagnostic fails GPU `matmul`, a
  fused temporary Metal kernel with `precise::pow` still misses by roughly
  `4e-4`, and PQ LUT probes reach only the low `1e-6` to `5e-6` range while
  failing to robustly cover the wider out-of-gamut regression domain. The only
  remaining resident route that matches the evidence is a compensated
  float32/higher-precision JzAzBz implementation, or a product decision to
  remove/flag `jzazbz` as a precision exception.
- A targeted OOG regression sample now verifies that extreme `jzazbz` chroma is
  finite and does not collapse to zero after backend processing. This closes a
  separate overflow/NaN defect, but not the stricter `1e-6` parity blocker.
- Grain stochastic parity is intentionally statistical, not pixel-identical.
  MLX grain must stay resident for the GUI runtime path; fixed-seed CPU parity
  is not a valid reason to perform a full-frame readback.

## JzAzBz Strict Precision Follow-up - 2026-06-09

The latent resident MLX custom JzAzBz kernel has now been wired into
`compress_rgb_jzazbz_chroma_backend()` for MLX custom-kernel-capable backends.
The kernel was strengthened with double-single constants and matrices for the
JzAzBz forward/inverse chain, overflow-stable chroma radius math, and
double-single Cmax table/grid interpolation metadata. This preserves the
resident/no-full-frame-readback contract.

The strict `1e-6` parity goal is still not closed. On the current MLX/Metal
test run, deterministic JzAzBz cases still miss the CPU float64 reference by
roughly `1e-4` on representative unit/wide samples, and the targeted large-OOG
sample misses by roughly `6e-6`. The tests now keep the `1e-6` assertions as
`xfail(strict=True)` so an unexpected pass promotes the gate, but the report
does not claim closure. A CPU fallback would satisfy precision but would violate
the P4 residency target, so it remains rejected for this goal.

## Targeted Grain Residency Update

Follow-up fix `SF-20260609-001` restored the intended grain residency contract:

- `src/spektrafilm/model/grain.py` now routes MLX `poisson_binomial` grain
  through backend stochastic samplers and backend Gaussian blur.
- `src/spektrafilm/gpu/residency.py` no longer allow-lists
  `_grain_cpu_reference_numpy`; a full-frame grain readback would now be
  reported as an unallowed residency event.
- `tests/test_grain.py` now asserts that supported MLX grain paths do not
  materialize to NumPy during computation, while retaining deterministic
  fixed-seed backend behavior and statistical plausibility checks.
- `tests/test_backend_resident_p4_hdr_grain.py` now asserts grain output remains
  MLX float32 without any `_grain_cpu_reference_numpy` readback marker.

Validation:

```text
.venv/bin/python -m pytest tests/test_grain.py -q
22 passed in 0.87s

.venv/bin/python -m pytest tests/test_backend_resident_p4_hdr_grain.py -q
24 passed in 5.00s

.venv/bin/python -m pytest tests/test_backend_resident_p4_hdr_grain.py tests/test_backend_resident_runtime_boundaries.py tests/test_gpu_color_chain.py tests/test_gamut_compression.py -q
153 passed, 3 warnings in 6.96s
```

## JzAzBz Precision Optimization Follow-up - 2026-06-22

A targeted round of per-exponent specialization in `src/spektrafilm/gpu/kernels/gamut_compress.py` closed the remaining slack in the resident JzAzBz path:

- Replaced the first-order `ds_signed_pow` Taylor correction with a second-order expansion.
- Removed the unused `pq_eotf_derivative_jz` helper.
- Added `ds_signed_pow_exp_log`, which evaluates `exp(exponent * log(x))` instead of `exp2(exponent * log2(x))`.
- Wired `ds_signed_pow_exp_log` only for the `inv_m2` exponent (`N^(1/m2)`) in the forward PQ EOTF, because this is the dominant transcendental error source and `exp(log)` matches numpy/libm better than Metal `pow` or `exp2(log2)` for this small exponent.
- Tightened `ds_safe_div` from `1e-12` to `1e-20`.

Results:

- Representative xfail max absolute error dropped from ~`1.5e-4` to ~`7e-5`.
- Full-kernel error vs CPU float64 reference is now ~`5.4e-5`, essentially at the faithful float32 double-single simulation floor (~`5.5e-5`).
- 2K frame JzAzBz kernel median remains ~0.18 ms, with no measurable performance regression.
- Full non-GUI suite: `1579 passed, 7 skipped, 4 xfailed`.

Root-cause analysis confirmed that the remaining gap to `1e-6` is not a kernel bug but a float32 precision floor: even a faithful Python double-single simulation using numpy transcendentals reaches only ~`5.5e-5` vs the CPU float64 reference. Apple Silicon Metal does not support `double`, so further improvement would require triple-float or another higher-precision arithmetic scheme. The `xfail` markers and NON-COMPLIANT contract status remain in place.

## Boundaries

- Preview and export still materialize by design after runtime completion.
- HDR scene luminance and RouteMaster sidecars materialize as explicit, timed
  CPU sidecars.
- Public CPU/default behavior remains unchanged: `numpy_float64` is still the
  default materialization policy.
