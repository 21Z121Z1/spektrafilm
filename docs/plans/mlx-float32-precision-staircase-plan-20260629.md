# MLX Float32 Precision Staircase Plan - 2026-06-29

## Goal

`/goal Build a test-only, reproducible MLX float32 precision staircase for Spektrafilm that compares CPU float64, CPU float32 legacy/reference, CPU float32 same-order, MLX float32 unfused, MLX float32 compiled/fused where available, and MLX LUT/tile paths across SDR/HDR stage probes, with metrics sufficient to support or falsify whether MLX float32 error is near the float32 theoretical floor, without changing production defaults or user-facing pipeline math.`

## Evidence Read

- Historical precision reports: `deep-research-report.md`, `deep-research-report-2.md`, and `docs/gpu/mlx-optimization-report-20260530.md` show MLX float32 and CPU float32 are close to CPU float64 by PSNR, but do not prove MLX is at the float32 theoretical floor.
- Backend architecture: `select_backend()` does not expose float64 GPU paths and must not register a test backend in production selection.
- Existing CPU backend: `NumpyBackend` preserves NumPy behavior and does not force float32 after every primitive, so it is not a same-order float32 oracle.
- MLX backend: MLX arrays are lazy, support explicit `eval`/`synchronize`, and include compiled elementwise paths plus fused Metal spectral kernels. This requires separate unfused/compiled/fused staircase layers.
- Kernel risk areas: spectral reductions in `cmy_to_log_raw` and `cmy_to_log_xyz`, IIR/exponential filters, 3D LUT trilinear interpolation, CCTF pow/log domains, tile assembly, percentile/headroom, and gain-map `log2(hdr_luma / sdr_luma)`.
- HDR risk areas: RouteMaster projection and HDR photo export use float32 luminance/headroom/gain-map math; PSNR alone is insufficient because gain-map error is naturally measured in EV/log2 space.

## External Primary Sources Used

- NumPy `sum` documentation: pairwise summation is sometimes used and can change the effective error model depending on axis/contiguity.
- NumPy `spacing` and `nextafter` documentation: ULP-adjacent probes should use representable float spacing rather than decimal guesses.
- Nicholas J. Higham, floating-point summation error analysis: reduction order controls the forward error bound, so "same dtype" is not enough.
- NVIDIA floating-point / IEEE 754 GPU documentation: floating-point operations are non-associative, and GPU operation order can differ from scalar CPU order.
- MLX documentation for lazy evaluation and `mx.compile`: execution and fusion boundaries must be considered independent variables.
- Android Ultra HDR / gain-map documentation and local ISO 21496 code paths: gain-map validation should include log-domain boost/EV error, not just image-space PSNR.
- CIEDE2000 references are relevant for perceptual colour deltas, but this task will not introduce a new heavy dependency. If an existing dependency exposes Delta E cheaply, it may be reported as optional; otherwise the core metrics remain numeric, luminance, and EV based.

## Staircase Layers

1. CPU float64 reference
   - Current production CPU math where available, materialized as float64.
   - Purpose: high precision baseline, not an MLX-equivalent order oracle.
2. CPU float32 legacy/reference
   - Existing CPU path with float32 input/materialization or NumPy vectorized float32 where already used.
   - Purpose: quantify dtype-only gap against CPU float64.
3. CPU float32 same-order reference
   - New test-only backend/helper under `src/spektrafilm/testing/`.
   - Purpose: simulate MLX fast-path operation order, constants, clamp/epsilon choices, reduction order, pow/log input domains, and tile partitioning as closely as practical.
4. MLX float32 unfused
   - Backend operations expressed as ordinary MLX ops, with explicit eval/synchronize around measurement.
   - Purpose: isolate lazy MLX op precision without Metal fused kernels.
5. MLX float32 compiled/fused
   - `compiled_elementwise` and fused Metal paths when available.
   - Purpose: determine whether fusion/reordering creates a separate precision signature.
6. MLX float32 LUT/tile paths
   - Trilinear 3D LUT and tile assembly stress probes.
   - Purpose: catch interpolation, boundary, and seam-specific errors.

## Same-Order Reference Design

- Implement `Float32ReferenceBackend` in `src/spektrafilm/testing/float32_reference_backend.py`; never register it in `select_backend()`.
- Every backend primitive coerces floating arrays/scalars to `np.float32` and returns float32 after the primitive where meaningful.
- Constants used by helpers are explicit `np.float32`.
- Reductions use deterministic serial accumulation for supported patterns instead of blindly calling NumPy vectorized reductions.
- Required primitive surface:
  - `asarray`, `zeros`, `eval`, `synchronize`, `cleanup`, `to_numpy`
  - `clip`, `where`, `maximum`, `max`, `max_array`, `fmax`, `nan_to_num`, `abs`
  - `exp`, `log10`, `log2`, `pow`, `power`
  - `einsum`, `matmul`
- Add same-order spectral helpers for the MLX fused kernel shapes:
  - `cmy_to_log_raw_same_order`
  - `cmy_to_log_xyz_same_order`
- Add same-order LUT and gain-map helpers only as test/benchmark instrumentation, not production replacements.
- Limitations must be reported: NumPy scalar operations can approximate C/Metal float behavior but cannot guarantee bit-identical Metal libm `pow/log` behavior.

## Precision Metrics

Core metrics in `src/spektrafilm/testing/precision_metrics.py`:

- finite/NaN/Inf counts
- max absolute difference
- mean absolute difference
- RMSE
- PSNR
- relative error histogram
- float32 ULP distance and ULP histogram
- luminance Y error
- gain-map delta EV from raw `log2(hdr_luma / max(sdr_luma, 1e-3))`
- HDR headroom difference
- monotonicity violation count
- tile seam statistics and optional compact seam heatmap

## Benchmark Design

New benchmark: `tests/benchmarks/benchmark_precision_staircase.py`

CLI:

```bash
.venv/bin/python tests/benchmarks/benchmark_precision_staircase.py \
  --height 3000 --width 4000 --runs 3 \
  --output-json docs/reports/precision-staircase-12mp.json \
  --output-markdown docs/reports/precision-staircase-12mp.md
```

Options:

- `--height`, `--width`
- `--runs`
- `--seed`
- `--scenario`
- `--output-json`
- `--output-markdown`
- `--raw-image` optional; synthetic scenarios remain mandatory so the benchmark is reproducible without local private files.

Synthetic scenarios:

- smooth ramp
- random bounded RGB
- near-black / near-white stress
- HDR scene luminance ramp
- tile seam stress

Required output:

- environment block with Python, NumPy, MLX availability, backend status, shape, run count, seed, and selected scenario(s)
- per-layer and per-stage metrics
- explicit skipped MLX layers if MLX/Metal is unavailable
- conclusion block that may say "not proven" when evidence is insufficient

## Stage Probes

Report stages:

- preprocess / input conversion
- `filming.expose`
- `filming.develop`
- `printing.expose`
- `printing.develop`
- `scanning.scan_film`
- `scanning.scan_print`
- RouteMaster projection light_table
- RouteMaster projection paper generic
- paper chemical fallback
- gain_map encode
- final materialize

Implementation detail:

- The first benchmark pass will use focused deterministic probes for the major numeric kernels behind those stages.
- If a full stage cannot be cleanly instrumented without production hooks, the report will mark it as `not_instrumented` and include the next hook design instead of pretending coverage exists.

## Falsification Criteria

Do not claim "near theoretical limit" unless all are supported by measurements:

- CPU float32 same-order vs MLX float32 error is much smaller than CPU float64 vs CPU float32 error.
- Pointwise kernels are mostly within 0-2 ULP, with explained tails.
- gain-map delta EV P99 and P99.9 stay below declared thresholds.
- HDR headroom and monotonicity show no structural bias.
- Tile seam stress shows no fixed-direction seam.
- compiled/fused vs unfused differences are small or explained by known operation-order changes.

If any condition fails or remains unmeasured, the final report must say the conclusion is not proven and identify the missing evidence or bottleneck.

## Tests

Run at minimum:

```bash
.venv/bin/python -m pytest tests/test_precision_metrics.py -q
.venv/bin/python -m pytest tests/test_precision_staircase.py -q
.venv/bin/python -m pytest tests/test_gpu_pipeline.py -q
.venv/bin/python -m pytest tests/test_hdr_projection_backend.py -q
.venv/bin/python -m pytest tests/test_hdr_photo.py tests/test_hdr_curve_profiles.py -q
.venv/bin/python -m pytest --ignore=tests/gui -q
git diff --check
```

The final commit must stage only this task's source/tests/docs/report artifacts and must not include unrelated existing worktree changes.
