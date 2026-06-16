# Adversarial Review Targeted Fixes - 2026-06-08

## Scope

This report records the first targeted fix pass after `docs/reviews/adversarial_full_repo_review_20260608.md`.

The workspace is dirty and another active thread is currently hardening HEIF / ISO 21496 / RouteMaster export behavior. To avoid interference, this pass intentionally did not edit HEIF/export files, active HDR docs, or active ISO tests.

## Thread Coordination

Read-only thread inspection found active thread `019ea727-91c0-7290-a23e-63303ca2fd7e` editing:

- `src/spektrafilm/utils/heif_iso21496.py`
- `src/spektrafilm/utils/hdr_photo.py`
- `src/spektrafilm/utils/gain_map_io.py`
- `tests/test_heif_iso21496.py`
- `tests/test_hdr_routemaster_export.py`
- `tests/test_hdr_photo.py`
- `tests/test_tier3_fixes.py`
- `docs/hdr-export-pipeline.md`
- `docs/hdr-routemaster-rewrite-implementation-report.md`
- `docs/heic-iso21496-compliance.md`
- `docs/README.md`
- `docs/hdr-routemaster-rewrite-plan.md`

Continuation inspection on 2026-06-09 found current active threads in the same workspace:

- `019ea73e-43e5-75d2-94b7-8e0062d5f755`: actively changing MLX/Metal grain residency files, including `src/spektrafilm/model/grain.py`, `src/spektrafilm/gpu/residency.py`, `tests/test_grain.py`, and `tests/test_backend_resident_p4_hdr_grain.py`.
- `019eaa31-62db-71e0-a85d-cd5a39c8d231`: actively diagnosing RouteMaster `paper` HDR headroom/export behavior for a real DNG.
- `019ea786-ba4c-7b21-964f-29362b5e2d22`: completed a report-only Metal precision study under `analysis/metal_float32_precision/`.
- `019ea768-a8ff-7d83-8ea4-125845528847`: completed RouteMaster HDR GUI response tests and documentation updates.

This targeted-fix pass has edited only:

- `src/spektrafilm/runtime/stages/printing.py`
- `src/spektrafilm/runtime/pipeline.py`
- `src/spektrafilm/model/grain.py`
- `src/spektrafilm/gpu/residency.py`
- `tests/test_grain.py`
- `tests/test_pipeline_smoke.py`
- `tests/test_backend_resident_p4_hdr_grain.py`
- `tests/test_backend_resident_runtime_boundaries.py`
- `src/spektrafilm_gui/controller_runtime.py`
- `tests/gui/test_controller_runtime_module.py`
- `docs/plans/adversarial-review-targeted-fixes-plan-20260608.md`
- `docs/reports/adversarial-review-targeted-fixes-20260608.md`
- `docs/reports/backend-resident-float32-p4-hdr-grain-validation-20260608.md`

## Fixed Findings

### SF-20260608-001

Finding: MLX grain used a normal approximation and violated the CPU parity contract.

Before fix reproduction:

```text
layer_result_type mlx.core array mlx.core.float32
layer_max_abs 0.7232514023780823
layer_allclose_1e6 False
apply_result_type mlx.core array mlx.core.float32
apply_max_abs 0.528042197227478
apply_allclose_1e6 False
```

Root cause:

- `_layer_particle_model_gpu()` sampled Poisson on MLX and then approximated variable-n binomial sampling with a rounded normal distribution.
- Existing MLX grain tests asserted deterministic output, plausible mean, and backend residency, but did not compare fixed-seed MLX output to CPU reference output.
- This contradicted the project rule that GPU output must be CPU-close or explicitly fall back.

Fix:

- Removed the MLX normal-approximation path from `_layer_particle_model_gpu()`.
- Added `_grain_cpu_reference_numpy()` and `_grain_reference_to_backend()` as the explicit CPU-reference fallback boundary.
- Routed MLX `layer_particle_model()`, `apply_grain_to_density()`, and layered grain through the CPU reference when exact stochastic backend parity cannot be guaranteed, then uploaded the float32 result back to MLX.
- Marked `_grain_cpu_reference_numpy` as an allowed residency diagnostic stack so the fallback is visible and distinguished from accidental full-frame materialization.
- Replaced the old "MLX grain does not materialize" assertion with CPU-reference fallback and fixed-seed CPU-vs-MLX parity tests.
- Updated P4 residency tests so grain still must return backend-resident float32 output while explicitly proving the correctness fallback readback occurs.

After fix reproduction:

```text
layer_result_type mlx.core array mlx.core.float32
layer_max_abs 0.0
layer_allclose_1e6 True
apply_result_type mlx.core array mlx.core.float32
apply_max_abs 0.0
apply_allclose_1e6 True
```

Interpretation: MLX grain now returns an MLX float32 array whose fixed-seed stochastic values match the CPU reference exactly for the reproducer. This intentionally gives up grain residency for correctness; the boundary is named and recorded rather than hidden.

### SF-20260608-002

Finding: MLX `soft_update()` could use stale backend print illuminant tables after enlarger filter changes.

Before fix reproduction:

```text
soft_rebuilt_max_abs 0.5651497840881348
soft_rebuilt_allclose_1e5 False
base_soft_max_abs 0.25006216764450073
```

Root cause:

- `PrintingStage._precompute_spectral_tables()` cached `_backend_print_illuminant` at construction.
- `SimulationPipeline.soft_update(c_filter_neutral=..., m_filter_neutral=..., y_filter_neutral=...)` mutated the shared enlarger params but did not refresh that backend array.
- CPU-side small exposure-factor computations saw the updated filters, while backend spectral computation still used the stale cached illuminant.

Fix:

- Added `PrintingStage.refresh_backend_spectral_tables()`.
- Made `_precompute_spectral_tables()` clear backend-cache attributes when no GPU backend is active.
- Updated `SimulationPipeline.soft_update()` to refresh backend print tables whenever any neutral enlarger filter changes.
- Added `test_mlx_soft_update_enlarger_filters_matches_rebuilt_pipeline()`.

After fix reproduction:

```text
soft_rebuilt_max_abs 0.0
soft_rebuilt_allclose_1e5 True
base_soft_max_abs 0.36012569069862366
```

Interpretation: the soft-updated MLX pipeline now matches a freshly rebuilt pipeline exactly for the reproducer, while the filter update still has a visible numerical effect relative to the base render.

### SF-20260608-004

Finding: mid-pipeline topology injection could skip preprocess side effects and crash active spatial DIR couplers.

Before fix reproduction:

```text
TypeError unsupported operand type(s) for /: 'float' and 'NoneType'
```

Root cause:

- `_process_topology()` seeded only the requested injected tap and then called `run_topology()`.
- When callers injected at `Tap.LOG_E_FILM`, preprocess did not run, so `ResizingService.pixel_size_um` stayed `None`.
- Active spatial DIR couplers divide their micron radius by `pixel_size_um`, causing a `TypeError` before returning the requested `Tap.CMY_FILM`.

Fix:

- Added `SimulationPipeline._prepare_topology_injection_side_effects()`.
- For injection points after `Tap.RGB_IN`, the pipeline now infers `pixel_size_um` from injected image height/width with the same film-format/max-dimension formula used by preprocess.
- Invalid injected values without image geometry now raise a clear `ValueError`.
- Added real pipeline regression tests for default spatial DIR-coupler injection and invalid injected geometry.

After fix reproduction:

```text
ok (4, 4, 3) float64 True pixel_size 8750.0
```

Interpretation: the public-looking tap API can now run a default `LOG_E_FILM -> CMY_FILM` injection without requiring callers to manually seed hidden resize state. The normal RGB input path remains unchanged.

### SF-20260608-008

Finding: GPU enlarger LUT mode unconditionally fell back to exact direct spectral computation but left unreachable backend LUT code below the early return.

Root cause:

- `_spectral_compute_enlarger_gpu()` correctly avoided the backend LUT path when `use_enlarger_lut=True`, because the CPU LUT path uses the project's higher-order LUT behavior while the backend 3D LUT kernel is trilinear.
- The function returned from that exact fallback inside a `try/finally`, leaving the backend LUT cache/application block below as dead code.
- Existing tests asserted the fallback timing but did not force the code body to be cleaned up.

Fix:

- Removed the unreachable backend LUT cache/application branch and the now-unused `apply_lut_trilinear_3d_backend` import from `src/spektrafilm/runtime/stages/printing.py`.
- Preserved the exact direct fallback and `PrintingStage.gpu_lut_direct_fallback` timing diagnostic.

Validation:

```text
.venv/bin/python -m pytest tests/test_backend_resident_runtime_boundaries.py::test_mlx_spectral_lut_requests_use_exact_backend_direct_fallback tests/test_gpu_pipeline.py::test_printing_non_lut_gpu_path_does_not_materialize_to_numpy -q
2 passed in 1.34s
```

Interpretation: behavior stays correctness-first and traceable, while the misleading unreachable branch is gone.

### SF-20260608-010

Finding: `SimulationWorker.run()` caught `BaseException` and converted fatal interrupts into ordinary GUI failure signals.

Root cause:

- The worker used `except BaseException as exc` around the full simulation callback.
- That catch boundary includes process/control-flow exceptions such as `KeyboardInterrupt` and `SystemExit`, plus any explicit abort sentinel that subclasses `BaseException`.
- Existing tests encoded the unsafe behavior by expecting a custom `BaseException` subclass to emit `failed`.

Fix:

- Changed `SimulationWorker.run()` to catch `Exception` for normal recoverable simulation failures.
- Let `BaseException` subclasses propagate instead of emitting the ordinary `failed` signal.
- Updated the dedicated worker test so normal `ValueError` still emits `failed`, while a custom `WorkerAbort(BaseException)` is re-raised and emits neither `finished` nor `failed`.

Validation:

```text
.venv/bin/python -m pytest tests/gui/test_controller_runtime_module.py::test_simulation_worker_emits_failure_message tests/gui/test_controller_runtime_module.py::test_simulation_worker_reraises_base_exception -q
2 passed in 0.31s
```

Interpretation: ordinary simulation errors still go through the GUI failure channel, but fatal/control-flow aborts are no longer hidden as recoverable render failures.

## Validation

Commands run:

```bash
.venv/bin/python -m pytest tests/test_backend_resident_runtime_boundaries.py::test_mlx_soft_update_enlarger_filters_matches_rebuilt_pipeline -q
```

Result:

```text
1 passed in 1.04s
```

```bash
.venv/bin/python -m pytest tests/test_edge_cases.py::TestPipelineSoftUpdate -q
```

Result:

```text
6 passed in 3.51s
```

```bash
.venv/bin/python -m pytest tests/test_backend_resident_runtime_boundaries.py -q
```

Result:

```text
7 passed in 6.85s
```

```bash
.venv/bin/python -m pytest tests/test_grain.py -q
```

Result:

```text
22 passed in 0.82s
```

```bash
.venv/bin/python -m pytest tests/test_backend_resident_p4_hdr_grain.py -q
```

Result:

```text
24 passed in 7.72s
```

```bash
.venv/bin/python -m pytest tests/test_pipeline_smoke.py::test_topology_inject_log_e_film_initializes_pixel_size_for_spatial_couplers tests/test_pipeline_smoke.py::test_topology_inject_after_preprocess_requires_image_geometry -q
```

Result:

```text
2 passed in 1.05s
```

```bash
.venv/bin/python -m pytest tests/test_pipeline_smoke.py -q
```

Result:

```text
11 passed in 2.79s
```

```bash
.venv/bin/python -m pytest tests/test_grain.py tests/test_backend_resident_p4_hdr_grain.py tests/test_backend_resident_runtime_boundaries.py -q
```

Result:

```text
53 passed in 8.33s
```

```bash
.venv/bin/python -m pytest tests/gui/test_controller_runtime_module.py::test_simulation_worker_emits_failure_message tests/gui/test_controller_runtime_module.py::test_simulation_worker_reraises_base_exception -q
```

Result:

```text
2 passed in 0.31s
```

Note: the first attempt to run this pytest command inside the read-only sandbox failed before collection with `FileNotFoundError: No usable temporary directory found`, because pytest capture could not create temporary files. The same focused command passed when rerun with approved test execution outside the read-only sandbox.

```bash
.venv/bin/python -m pytest tests/gui/test_controller_runtime_module.py -q
```

Result:

```text
11 passed in 0.19s
```

```bash
git diff --check -- src/spektrafilm_gui/controller_runtime.py tests/gui/test_controller_runtime_module.py docs/plans/adversarial-review-targeted-fixes-plan-20260608.md docs/reports/adversarial-review-targeted-fixes-20260608.md
```

Result: passed with no whitespace errors.

## Remaining Findings

Not addressed in this pass:

- `SF-20260608-003`: `output_diffuse_white` diagnostic-only behavior. This touches active HDR projection semantics and should wait until the active RouteMaster/HEIF thread is complete.
- `SF-20260608-014`: paper HDR density-curve morph responsiveness. The active thread reported a full non-GUI suite passing after RouteMaster/HEIF changes; re-check after that thread completes before editing HDR projection files.
- `SF-20260608-009`: repository CI workflow remains open. Fixing it requires adding `.github/workflows/...`, which is outside the current AGENTS fix scope (`src/`, `tests/`, `docs/`, `README.md`, `pyproject.toml`) unless the user explicitly authorizes that path.
- Medium/Low findings from the review remain open unless fixed here or by other active work. `SF-20260608-004`, `SF-20260608-008`, and `SF-20260608-010` are fixed in this pass.

## Confidence

Confidence for `SF-20260608-002` is high. The original smoke reproducer failed before the fix and now reports zero soft-update-vs-rebuild difference. The focused MLX regression test and existing soft-update tests pass.

Confidence for `SF-20260608-001` is high for the targeted fixed-seed `poisson_binomial` grain paths. The original CPU-vs-MLX probe failed with max absolute differences above `0.5`; after the fix, both direct layer and `apply_grain_to_density()` probes report `0.0` max absolute difference and focused grain/P4 tests pass. The remaining tradeoff is performance: grain now has an explicit CPU-reference readback on MLX until an exact backend sampler exists.

Confidence for `SF-20260608-004` is high for the reported `LOG_E_FILM -> CMY_FILM` crash. The original smoke now succeeds, two real pipeline regression tests cover the hidden side effect and invalid geometry, and the full pipeline smoke file passes.

Confidence for `SF-20260608-008` is high. The change removes code that was provably unreachable after an unconditional return and preserves the existing exact direct fallback test.

Confidence for `SF-20260608-010` is high. The changed catch boundary is minimal, normal `Exception` behavior remains covered by the existing failure-signal test, and a new `BaseException` propagation test covers the exact unsafe behavior reported by the review.
