# Backend Resident Float32 P4 HDR Grain Validation Result - 2026-06-08

## Current Result

P4 residency validation is implemented and measured, but the overall
"every GUI-selectable effect is both MLX/Metal-resident and strict CPU-parity"
goal is **not fully closed** because `jzazbz` cannot currently satisfy the
project-wide deterministic `1e-6` CPU-reference tolerance while staying on
Apple GPU float32.

Implemented evidence lives in:

- `tests/test_backend_resident_p4_hdr_grain.py`
- `tools/benchmark_backend_resident_p4_validation.py`
- `docs/reports/backend-resident-float32-p4-hdr-grain-validation-20260608.md`
- `docs/reports/backend-resident-float32-p4-validation-benchmark-20260608-215950.json`
- `docs/reports/backend-resident-float32-p4-validation-benchmark-20260608-215950.md`
- `docs/reports/backend-resident-float32-p4-validation-benchmark-20260608-224101.json`
- `docs/reports/backend-resident-float32-p4-validation-benchmark-20260608-224101.md`
- `docs/reports/backend-resident-float32-p4-validation-benchmark-20260608-224912.json`
- `docs/reports/backend-resident-float32-p4-validation-benchmark-20260608-224912.md`
- `docs/reports/backend-resident-float32-p4-validation-benchmark-20260609-110920.json`
- `docs/reports/backend-resident-float32-p4-validation-benchmark-20260609-110920.md`

Measured full-resolution RAW sample:

- `scratch/IMG_9121_converted.DNG` decoded through the GUI RAW path as
  `[3024, 4032, 3] float32`.
- All 25 benchmark workloads completed with `status=ok`.
- Maximum `unallowed_to_numpy` across benchmark runs was `0`.
- Latest real DNG rows still return `mlx.core.array mlx.core.float32`; the
  current slow path remains grain synchronization, not scanner spectral compute.
- After restoring resident MLX grain on 2026-06-09, the latest real DNG grain
  rows still returned `mlx.core.array mlx.core.float32` with `0` unallowed
  readbacks.

Validation gates run:

- `.venv/bin/python -m pytest tests/test_backend_resident_p4_hdr_grain.py tests/test_backend_resident_runtime_boundaries.py tests/test_gpu_color_chain.py tests/test_gamut_compression.py -q`
  - `153 passed, 3 warnings`
- `.venv/bin/python -m pytest --ignore=tests/gui -q`
  - `1497 passed, 7 skipped, 4 warnings`
- `.venv/bin/python -m pytest tests/gui/test_controller_runtime_module.py tests/gui/test_controller_layers.py tests/gui/test_controller_output.py tests/gui/test_controller_flow.py -q`
  - `87 passed`
- `git diff --check`
  - passed

## Residual Blocker

`jzazbz` is now backend-resident and has zero full-frame readbacks, but its
float32 JzAzBz/PQ forward-inverse path differs from the existing float64 CPU
reference by roughly `4e-4` worst-case on representative `[0, 1]` RGB samples.
This pass also fixed a separate overflow defect where very large OOG `jzazbz`
chroma could overflow `sqrt(az^2 + bz^2)`, produce NaN through the Reinhard
knee, and collapse through `nan_to_num()` to black. The new backend path uses
overflow-stable chroma radius and knee math, and the regression sample now
matches the documented `5e-4` JzAzBz tolerance instead of producing a large
finite-value mismatch.

Isolation work showed:

- Cmax lookup, lightness/chroma knee, and RGB matrix-only float32 paths are not
  the dominant error source.
- Float32 JzAzBz forward contributes roughly `3e-4` worst-case.
- Float32 JzAzBz inverse contributes roughly `2e-4` worst-case.
- Algebraic PQ rewrites using `log`, `log1p`, and `expm1` did not improve the
  error.
- A high-resolution 1D PQ LUT reduced the error to roughly `5e-6`, but still
  missed the `1e-6` gate and would introduce a new approximation table.
- A custom MLX Metal-kernel probe using Metal `precise::pow` did not improve
  the positive-domain ST2084 inverse enough to close the final RGB error.
- MLX reports GPU `float64` as unsupported, so exact CPU-reference parity cannot
  be restored by simply running the JzAzBz math in double precision on Metal.

Continuation probes on 2026-06-09 tightened that conclusion:

- Feeding an MLX `float64` tensor into the JzAzBz backend fails at GPU
  `matmul` with `ValueError: float64 is not supported on the GPU`; `float64`
  is therefore only an upper-bound diagnostic, not a production path for
  `gpu_precision="float32"`.
- Reimplementing the full per-pixel JzAzBz compression as a fused temporary
  `mx.fast.metal_kernel` with Metal `precise::pow` still measured around
  `3.9e-4` max error on `[0, 1]` RGB samples and around `7.4e-4` on the
  `[-0.2, 1.35]` regression domain, so graph fusion and `precise::pow` do not
  close the gap.
- A NumPy mixed-precision lower-bound probe showed that exact PQ with float32
  forward arithmetic still leaves about `2.3e-6` max error, exact PQ with
  float32 inverse arithmetic leaves about `2.6e-6`, and both float32 stages
  leave about `3.7e-6`. Exact PQ plus double-precision non-PQ arithmetic can
  fall below `1e-6`, which points to compensated float32 arithmetic, not just a
  better scalar `pow`, as the remaining resident route.
- The wider `[-0.2, 1.35]` domain can produce negative LMS values that map
  through signed PQ to very large intermediate LMS' values before the chroma
  compressor pulls the result back to finite RGB. Simple finite-domain PQ LUTs
  are therefore not robust enough for the current GUI/test domain.

The honest choices are therefore:

- keep `jzazbz` resident with a documented precision exception;
- fall `jzazbz` back to CPU and fail the residency goal for that GUI option;
- implement a custom higher-precision Metal/JzAzBz path, likely via compensated
  float32 arithmetic or another explicitly validated method.

### 2026-06-22 follow-up

A per-exponent specialization pass chose option (a) — keep resident with a documented exception — after reaching the float32 precision floor:

- `inv_m2` in the forward PQ EOTF now uses `exp(exponent * log(x))`, which matches numpy/libm better than Metal `pow` / `exp2(log2)` for this small exponent.
- The representative worst-case error fell from ~`1.5e-4` to ~`7e-5`.
- The full-kernel error vs CPU float64 is now ~`5.4e-5`, matching the faithful float32 double-single simulation floor (~`5.5e-5`).
- Performance is unchanged (~0.18 ms for a 2K frame).

The remaining ~`5e-5` gap to `1e-6` is structural: it comes from the float32 double-single arithmetic itself, not from the transcendental implementation. Apple Silicon Metal does not support `float64`, so closing the gap would require triple-float or another higher-precision scheme. The `xfail` markers and precision-contract NON-COMPLIANT status remain.

## Gate Status

P1, P2, and P3 are closed:

- `docs/reports/backend-resident-float32-p1-foundation-20260608.md`
- `docs/reports/backend-resident-float32-p2-runtime-boundaries-20260608.md`
- `docs/reports/backend-resident-float32-p3-gui-preview-export-20260608.md`

P3 explicitly allows P4. This plan is P4 only.

## Refined P4 /goal

Validate and isolate the remaining non-resident boundaries for HDR metadata,
RouteMaster sidecars, grain/stochastic effects, and full-render benchmarks
without changing SDR semantics or CPU/default public API behavior.

P4 completion means:

- HDR scene-luminance metadata materialization is explicit, timed, and allowed
  only when metadata is requested.
- RouteMaster/HDR export sidecars materialize through explicit timing rather
  than accidental `np.asarray()` calls.
- Grain ON/OFF behavior is benchmarked and classified. Supported MLX grain
  paths should stay backend-resident; unsupported/non-MLX GPU grain fallbacks
  remain explicit CPU boundaries.
- Synthetic 256x256, synthetic 512x384 GUI-like, and real DNG validation use
  separate rows when the sample exists.
- Benchmarks distinguish runtime, final materialization, preview, export,
  HDR sidecar, grain, and GPU sync where applicable.
- P1/P2/P3 tests remain green.

## Audit Evidence

HDR metadata:

- `SimulationPipeline.process_with_metadata()` calls `_preprocess_with_metadata()`.
- `_preprocess_with_metadata()` computes `HDRSceneEnergyMetadata.scene_luminance`
  via `_scene_luminance()`.
- `_scene_luminance()` returns NumPy `float32` because HDR metadata is a
  CPU-facing sidecar, but the current backend path can rely on implicit
  conversion inside colour/NumPy helpers.

RouteMaster/HDR export:

- `SimulationPipeline.process_master()` returns `RouteMaster`, whose fields are
  annotated as `np.ndarray`.
- `_build_route_master()` materializes route RGB/XYZ/Y, SDR RGB, scene Y,
  post-halation Y, and density CMY sidecars.
- `_positive_render_negative_scan_master()` also materializes route RGB and
  scene Y for positive negative-scan rendering.
- HDR HEIC export uses `process_master()` through
  `export_hdr_heic_from_simulator()`.

Grain/stochastic effects:

- `digest_params()` disables grain/glare when
  `debug.deactivate_stochastic_effects=True`.
- `apply_grain()` has MLX-aware paths for standard and layered grain.
- Existing grain tests cover MLX no-transfer for supported paths and deterministic
  fixed-seed behavior.
- Unsupported GPU-like backends fall back through `backend.to_numpy()` and must
  remain classified as explicit CPU boundaries, not hidden hot-path residency.

Samples/benchmark inputs:

- Real local sample exists: `scratch/IMG_9121_converted.DNG`.
- Existing benchmarks cover P1/P2/P3 and older Metal P0-P4, but none currently
  generates the required P4 matrix with HDR/grain/preview/export separation.

## Implementation Scope

Planned code changes:

- `src/spektrafilm/runtime/pipeline.py`
  - Add an explicit sidecar materialization helper with timing.
  - Use it for HDR scene luminance and RouteMaster sidecars.
  - Preserve `materialize_policy="backend"` for normal output images.
- `src/spektrafilm/gpu/residency.py`
  - Mark the new HDR/RouteMaster sidecar helpers as allowed diagnostic
    readback locations.
- New or updated tests:
  - `tests/test_backend_resident_p4_hdr_grain.py`
  - verify process-with-metadata keeps image policy while sidecar is NumPy;
  - verify RouteMaster sidecars are NumPy and explicitly timed;
  - verify normal non-HDR backend runtime still has zero unallowed full-size
    readbacks;
  - verify grain ON MLX output is backend-resident when available.
- New benchmark:
  - `tools/benchmark_backend_resident_p4_validation.py`
  - cover CPU/MLX, grain ON/OFF, HDR metadata ON/OFF, preview/export ON/OFF,
    synthetic 256x256, synthetic 512x384, and real DNG if present.

## Not In Scope

- No float16.
- No SDR rendering semantic changes.
- No rewrite of HDR sidecar algorithms to MLX-native arrays; RouteMaster remains
  a CPU/export sidecar contract in P4.
- No rewrite of Apple HEIC encoder behavior.
- No claim that synthetic results prove 12MP RAW performance.

## Risk Analysis

- HDR sidecar correctness risk: forcing explicit `backend.to_numpy()` must not
  change the numeric `scene_luminance` result. Tests will compare finite shape
  and preserve output image residency.
- Residency diagnostic risk: allowing sidecar readbacks too broadly could hide
  normal runtime regressions. Allow-list additions will target helper names, and
  normal non-HDR runtime tests must still report zero unallowed readbacks.
- Grain risk: MLX stochastic grain is not bit-identical to CPU grain because it
  uses backend stochastic samplers and approximations. P4 will validate
  residency/finiteness and document this limitation, not claim CPU bit parity for
  grain ON.
- Benchmark risk: DNG load may be expensive or dependency-gated. If the local
  DNG path cannot load, the benchmark must record a skipped sample honestly.

## Verification Plan

Targeted P4 tests:

- `.venv/bin/python -m pytest tests/test_backend_resident_p4_hdr_grain.py tests/test_grain.py tests/test_routemaster.py tests/test_hdr_routemaster_export.py tests/test_hdr_routemaster_projection.py -q`

P1/P2/P3 gates:

- `.venv/bin/python -m pytest tests/test_runtime_materialize_policy.py tests/test_backend_resident_float32.py tests/test_gpu_highlight_boost_sync.py -q`
- `.venv/bin/python -m pytest tests/test_backend_resident_runtime_boundaries.py tests/test_spectral_lut_service.py -q`
- `.venv/bin/python -m pytest tests/gui/test_controller_runtime_module.py tests/gui/test_controller_layers.py tests/gui/test_controller_output.py tests/gui/test_controller_flow.py -q`
- `.venv/bin/python -m pytest --ignore=tests/gui -q`

Benchmarks:

- `.venv/bin/python tools/benchmark_backend_resident_p4_validation.py --backend cpu --runs 1 --warmups 0 --no-write`
- `.venv/bin/python tools/benchmark_backend_resident_p4_validation.py --backend mlx --precision float32 --runs 1 --warmups 0 --no-write`
- `.venv/bin/python tools/benchmark_backend_resident_p4_validation.py --backend mlx --precision float32 --runs 1 --warmups 0 --include-real --real-input scratch/IMG_9121_converted.DNG --no-write`

If MLX or the DNG loader is unavailable, the benchmark must report the skip
reason without fabricating results.

## Rollback Strategy

P4 code changes are limited to explicit sidecar materialization helpers,
residency allow-list labels, tests, benchmark, and docs. If validation fails,
revert these P4 files while keeping P1/P2/P3 intact.

## P4 Gate

P4 is complete only if:

- P1/P2/P3 gates remain green.
- HDR metadata does not break backend-policy image residency.
- RouteMaster sidecars are explicit CPU materialization boundaries.
- Grain ON/OFF is benchmarked and documented.
- Synthetic and real-sample availability are recorded truthfully.
- The P4 report states what is done, what remains P5, and whether the overall
  staged goal is satisfied.
