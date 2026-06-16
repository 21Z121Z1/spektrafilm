# Adversarial Review Targeted Fixes Plan - 2026-06-08

## Goal

Address the highest-priority non-conflicting findings from `docs/reviews/adversarial_full_repo_review_20260608.md` in the current dirty `spektrafilm-main` workspace without interfering with active concurrent threads.

## Thread Coordination

Read-only thread inspection found:

- Current active thread `019ea727-91c0-7290-a23e-63303ca2fd7e` is hardening HEIF / ISO 21496 / RouteMaster export behavior. It is actively editing `src/spektrafilm/utils/heif_iso21496.py`, `src/spektrafilm/utils/hdr_photo.py`, `src/spektrafilm/utils/gain_map_io.py`, `tests/test_heif_iso21496.py`, `tests/test_hdr_routemaster_export.py`, `tests/test_hdr_photo.py`, `tests/test_tier3_fixes.py`, `docs/hdr-export-pipeline.md`, `docs/hdr-routemaster-rewrite-implementation-report.md`, `docs/heic-iso21496-compliance.md`, `docs/README.md`, and `docs/hdr-routemaster-rewrite-plan.md`.
- Older completed RouteMaster thread `019e9706-e25c-7252-9e07-f5c27cc8b905` introduced the RouteMaster architecture, projection tests, and pair export API.
- Continuation check on 2026-06-09 found active threads in the same workspace:
  - `019ea73e-43e5-75d2-94b7-8e0062d5f755`, actively changing MLX/Metal grain residency files.
  - `019eaa31-62db-71e0-a85d-cd5a39c8d231`, actively diagnosing RouteMaster `paper` HDR headroom/export behavior.
  - `019ea786-ba4c-7b21-964f-29362b5e2d22`, completed a read/report-only Metal precision study under `analysis/metal_float32_precision/`.
  - `019ea768-a8ff-7d83-8ea4-125845528847`, completed RouteMaster HDR GUI response testing and documentation updates.

This pass will avoid HEIF/export/docs files currently owned by the active thread. The first implementation target was `SF-20260608-002`, because it is high severity, reproducible, and scoped to `src/spektrafilm/runtime/stages/printing.py`, `src/spektrafilm/runtime/pipeline.py`, and a runtime/GPU test. After that fix passed focused validation, the next non-conflicting target was `SF-20260608-001`, scoped to grain stochastic parity and backend-residency tests. With both non-conflicting High findings fixed, the next safe Medium targets are `SF-20260608-004`, scoped to runtime topology injection side effects, and `SF-20260608-008`, scoped to unreachable GPU enlarger LUT dead code.

The 2026-06-09 continuation avoids grain/residency, RouteMaster projection, HEIF/gain-map, and active HDR docs. The safe next target is `SF-20260608-010`, because it is limited to GUI worker exception handling and its dedicated GUI runtime module tests.

## Finding Targeted First

`SF-20260608-002`: MLX `soft_update()` can use stale backend print illuminant tables after enlarger filter changes.

Current reproduction before edits:

```text
soft_rebuilt_max_abs 0.5651497840881348
soft_rebuilt_allclose_1e5 False
base_soft_max_abs 0.25006216764450073
```

## Best Local Pattern

Use the repository's existing cache invalidation style:

- `SpectralLUTService.set_hanatos2025_adaptation()` clears cached LUT/backend arrays when the adaptation changes.
- `SpectralLUTService.set_input_gamut_compress()` clears cached LUT state when the input gamut compression spec changes.
- Backend LUT caches are explicitly reset when their CPU LUT changes.

Apply the same direct ownership model here: `PrintingStage` owns backend spectral tables and should expose a narrow refresh method. `SimulationPipeline.soft_update()` should call it when it mutates enlarger fields that feed `EnlargerService.enlarger_filtered_illuminant()`.

## Implementation Plan

1. Add `PrintingStage.refresh_backend_spectral_tables()` as a public/narrow stage method that reruns `_precompute_spectral_tables()`.
2. Make `_precompute_spectral_tables()` clear cached backend table attributes when no GPU backend is active, then rebuild all cached backend arrays for GPU.
3. In `SimulationPipeline.soft_update()`, track whether `c_filter_neutral`, `m_filter_neutral`, or `y_filter_neutral` changed.
4. After mutations, call `self._printing_stage.refresh_backend_spectral_tables()` only when a filter changed.
5. Add a focused MLX test proving soft-updated output matches a freshly rebuilt pipeline after an enlarger filter update.
6. Run the new focused test, existing edge-case soft-update tests, and a relevant backend-residency slice.

## Explicit Non-Goals In This Pass

- Do not edit active HEIF/ISO files.
- Do not change HDR projection files while the RouteMaster/HEIF thread is active.
- Do not clean, revert, commit, push, or rewrite unrelated dirty files.

## Validation Commands

```bash
.venv/bin/python -m pytest tests/test_backend_resident_runtime_boundaries.py::test_mlx_soft_update_enlarger_filters_matches_rebuilt_pipeline -q
.venv/bin/python -m pytest tests/test_edge_cases.py::TestPipelineSoftUpdate -q
.venv/bin/python -m pytest tests/test_backend_resident_runtime_boundaries.py -q
```

If MLX is unavailable, the MLX-specific tests should skip rather than fail.

## Second Finding Target

`SF-20260608-001`: MLX grain uses a normal approximation and violates the CPU parity contract.

Current reproduction before edits:

```text
layer_max_abs 0.7232514023780823
layer_allclose_1e6 False
apply_max_abs 0.528042197227478
apply_allclose_1e6 False
```

## Best Local Pattern For Grain

The project GPU rule is correctness-first: GPU output must match CPU/NumPy within float32 tolerance, or the operation must explicitly fall back to CPU. Existing code already uses explicit CPU fallbacks for unsupported GPU operations and tracks readbacks through `spektrafilm.gpu.residency`.

For grain, exact MLX stochastic parity would require reproducing SciPy/NumPy seeded Poisson and variable-n binomial sampling exactly. The current MLX implementation instead used a normal approximation. The conservative fix is therefore:

1. Materialize grain inputs through a named `_grain_cpu_reference_numpy()` boundary.
2. Run the existing CPU grain reference with the same public parameters and seeds.
3. Upload the result back to the backend as float32, preserving the backend-returning API.
4. Mark this readback as an allowed, explicit correctness fallback in residency diagnostics.
5. Replace the old "no materialization" tests with fixed-seed CPU-vs-MLX parity tests and explicit fallback assertions.

## Additional Validation Commands

```bash
.venv/bin/python -m pytest tests/test_grain.py -q
.venv/bin/python -m pytest tests/test_backend_resident_p4_hdr_grain.py -q
.venv/bin/python -m pytest tests/test_backend_resident_runtime_boundaries.py -q
git diff --check -- src/spektrafilm/model/grain.py src/spektrafilm/gpu/residency.py tests/test_grain.py tests/test_backend_resident_p4_hdr_grain.py docs/plans/adversarial-review-targeted-fixes-plan-20260608.md docs/reports/adversarial-review-targeted-fixes-20260608.md docs/reports/backend-resident-float32-p4-hdr-grain-validation-20260608.md
```

## Third Finding Target

`SF-20260608-004`: mid-pipeline topology injection can skip preprocess side effects and crash active spatial DIR couplers.

Current reproduction before edits:

```text
TypeError unsupported operand type(s) for /: 'float' and 'NoneType'
```

Root cause:

- `_process_topology()` seeded only the requested injected tap.
- Injecting at `Tap.LOG_E_FILM` skipped preprocess, so `ResizingService.pixel_size_um` remained `None`.
- Active spatial DIR couplers convert microns to pixels by dividing by `pixel_size_um`.

Best local pattern:

- Preserve the normal RGB input path: preprocess remains the owner of crop/upscale and pixel-size state.
- For explicit injection after preprocess, infer `pixel_size_um` from the injected image geometry once, using the same film-format-to-max-dimension formula as preprocess.
- Reject injected values without height/width geometry with a clear `ValueError`.

Additional validation:

```bash
.venv/bin/python -m pytest tests/test_pipeline_smoke.py::test_topology_inject_log_e_film_initializes_pixel_size_for_spatial_couplers tests/test_pipeline_smoke.py::test_topology_inject_after_preprocess_requires_image_geometry -q
.venv/bin/python -m pytest tests/test_pipeline_smoke.py -q
```

## Fourth Finding Target

`SF-20260608-008`: GPU enlarger LUT mode unconditionally falls back to direct spectral computation and leaves dead LUT code below.

Best local pattern:

- Keep the exact direct backend fallback because the CPU LUT path is PCHIP-like while the current backend 3D LUT kernel is trilinear.
- Preserve `PrintingStage.gpu_lut_direct_fallback` timing so users and benchmarks can see the explicit fallback.
- Remove the unreachable backend LUT cache/application branch below the return instead of leaving misleading dead code.

Validation:

```bash
.venv/bin/python -m pytest tests/test_backend_resident_runtime_boundaries.py::test_mlx_spectral_lut_requests_use_exact_backend_direct_fallback tests/test_gpu_pipeline.py::test_printing_non_lut_gpu_path_does_not_materialize_to_numpy -q
```

## Fifth Finding Target

`SF-20260608-010`: `SimulationWorker.run()` catches `BaseException` and converts fatal interrupts into ordinary GUI failure signals.

Best local pattern:

- Treat normal simulation failures as `Exception` and keep the existing `failed` signal path.
- Let `BaseException` subclasses such as `KeyboardInterrupt`, `SystemExit`, and explicit abort sentinels propagate instead of making the worker look like a recoverable failed render.
- Keep the change inside `src/spektrafilm_gui/controller_runtime.py` and `tests/gui/test_controller_runtime_module.py`, avoiding active grain/HDR/HEIF files.

Validation:

```bash
.venv/bin/python -m pytest tests/gui/test_controller_runtime_module.py::test_simulation_worker_emits_failure_message tests/gui/test_controller_runtime_module.py::test_simulation_worker_reraises_base_exception -q
git diff --check -- src/spektrafilm_gui/controller_runtime.py tests/gui/test_controller_runtime_module.py docs/plans/adversarial-review-targeted-fixes-plan-20260608.md docs/reports/adversarial-review-targeted-fixes-20260608.md
```
