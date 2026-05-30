# Test Coverage Gap & Quality Review

> Generated 2026-05-28 — REVIEW-ONLY pass (no source code modified)
> 608 tests across 42 test files analyzed

---

## P0 — Critical Gaps (behavior that could silently break production)

### TEST-001: No test for diffusion filter energy conservation
- **Severity**: P0
- **Evidence**: `module_contracts.md` §7 — "Energy-conserving: output integrates ~ input energy"; `validation_matrix.md` row marked **UNTESTED**
- **Untested behavior**: `model/diffusion.py::apply_diffusion_filter_um` — output sum should approximate input sum. A filter that leaks or gains energy would produce incorrect HDR luminance.
- **Risk**: Silent HDR luminance drift. A regression in kernel normalization would go undetected.
- **Suggested test**: Apply diffusion filter to a uniform image with known total energy. Assert `abs(sum(output) - sum(input)) / sum(input) < 0.01` for each channel.

### TEST-002: No test for pipeline timing/backend cleanup after exceptions
- **Severity**: P0
- **Evidence**: `module_contracts.md` §1 — "Timings cleared on each process()"; "Backend cache cleaned after process()"; `validation_matrix.md` rows marked **UNTESTED**
- **Untested behavior**: If `process()` throws, `self.timings` may retain stale data, and GPU backend cache may leak memory.
- **Risk**: Memory leak on GPU backends (MLX/CuPy), stale timing data confusing debug output.
- **Suggested test**: Monkeypatch `_pipeline` to raise, catch exception, assert `pipeline.timings == {}` and `cleanup()` was called.

### TEST-003: No test for GPU tiling overlap correctness
- **Severity**: P0
- **Evidence**: `validation_matrix.md` — "GPU tiling overlap correctness — No test verifies seamless tile boundaries" marked **UNTESTED**
- **Untested behavior**: `runtime/pipeline.py::_process_with_gpu_tiles` — tile boundaries may produce visible seams if overlap handling is wrong.
- **Risk**: Visible seam artifacts in large images processed on GPU.
- **Suggested test**: Process a gradient image through tiling with overlap, compare against full-image result. Assert `max(abs(tiled - full)) < epsilon`.

### TEST-004: No test for grain RNG state save/restore
- **Severity**: P0
- **Evidence**: `module_contracts.md` §8 — "fast_stats path modifies global np.random state"; `validation_matrix.md` marked **UNTESTED**
- **Untested behavior**: `model/grain.py::apply_grain` with `use_fast_stats=True` — must save and restore `np.random` state.
- **Risk**: Non-deterministic behavior in surrounding code; grain may affect auto-exposure or other stochastic components.
- **Note**: `test_grain.py::test_layer_particle_model_fast_stats_restores_global_rng_state` tests the lower-level function but NOT the full `apply_grain` path with `use_fast_stats=True`.
- **Suggested test**: Call `apply_grain` with `use_fast_stats=True` on a non-trivial image, assert `np.random` state is unchanged afterward.

---

## P1 — High Severity Gaps

### TEST-005: No test for digest_params idempotency
- **Severity**: P1
- **Evidence**: `module_contracts.md` §3 — "`digest_params(digest_params(p))` is idempotent"; `validation_matrix.md` marked **UNTESTED**
- **Untested behavior**: Re-digesting params should be safe. If halation presets or filter lookups modify state non-idempotently, double-digestion could produce wrong parameters.
- **Risk**: Calling `digest_params` twice (e.g., from `simulate()` then user code) could change behavior.
- **Suggested test**: `digest_params(p1)` then `digest_params(p1)` again, assert all fields identical via deep comparison.

### TEST-006: Diffusion PSF per-channel normalization untested
- **Severity**: P1
- **Evidence**: `module_contracts.md` §7 — "PSF is per-channel (halo warmth redistributes R/G/B differently)"; `validation_matrix.md` marked **UNTESTED**
- **Untested behavior**: `model/diffusion.py` — per-channel PSF should normalize to 1.0 per channel to preserve energy.
- **Risk**: Halo warmth could cause color casts if normalization drifts.
- **Suggested test**: Apply diffusion filter with known per-channel scatter values. Assert each channel's output sum matches input sum within tolerance.

### TEST-007: HDR rendition EXR round-trip untested
- **Severity**: P1
- **Evidence**: `validation_matrix.md` — "save_hdr_rendition_exr not tested (was the C1 fix)" marked **UNTESTED**
- **Untested behavior**: `utils/io.py::save_hdr_rendition_exr` — applies paper rolloff + diffuse lift before writing EXR.
- **Risk**: EXR HDR export could produce incorrect luminance values.
- **Suggested test**: Save HDR rendition to EXR, load back, verify rolloff was applied and values are within expected headroom.

### TEST-008: Pipeline soft_update print balance invalidation untested
- **Severity**: P1
- **Evidence**: `validation_matrix.md` — "Complex interaction between exposure_compensation and density_spectral_midgray" marked **UNTESTED**
- **Untested behavior**: `soft_update(exposure_compensation_ev=X)` should invalidate cached midgray balance. If it doesn't, subsequent prints use stale balance.
- **Risk**: Print exposure changes don't take effect until full pipeline rebuild.
- **Suggested test**: Soft-update exposure, process image, compare with freshly-built pipeline at same exposure. Assert close match.

### TEST-009: Large image GPU tiling integration test missing
- **Severity**: P1
- **Evidence**: `validation_matrix.md` — "No test with image > SPEKTRAFILM_GPU_TILE_PIXELS" marked **UNTESTED**
- **Untested behavior**: The actual tiling codepath in `pipeline.py` is never tested with a real large image on GPU.
- **Risk**: The tiling math (tile sizes, overlap, synchronization) could be wrong for real workloads.
- **Suggested test**: Monkeypatch tile threshold to small value, process 32x32 image, verify output matches non-tiled path.

---

## P2 — Medium Severity Gaps

### TEST-010: crop_image weak assertions — no value verification
- **Severity**: P2
- **Evidence**: `tests/test_edge_cases.py::TestCropImageBoundaryConditions` — lines 128-159
- **Issue**: Tests assert `cropped.ndim == 3` and `shape[0] > 0` but never verify pixel values are correct. A crop that returns random data would pass.
- **Risk**: Regression in crop logic (wrong offsets, wrong interpolation) would go undetected.
- **Suggested fix**: Add assertions that cropped values match expected sub-region of input.

### TEST-011: Raw file processor only tests happy path
- **Severity**: P2
- **Evidence**: `tests/test_raw_file_processor.py` — 12 tests, all use monkeypatched `rawpy`, no error paths
- **Untested behavior**: Missing `rawpy` dependency, corrupt RAW file, unsupported format, zero-size RAW output, I/O errors.
- **Risk**: Import errors or unhandled exceptions in production RAW processing.
- **Suggested test**: Test with missing rawpy (import error), test with malformed path, test with zero-size postprocess output.

### TEST-012: Grain tests missing extreme value coverage
- **Severity**: P2
- **Evidence**: `tests/test_grain.py` — 8 tests, all use moderate density values (0.3-0.9)
- **Untested behavior**: Zero particle area, negative uniformity, extreme density (0.0 or 10.0), zero-size image, grain with `micro_structure` active.
- **Risk**: Division by zero or NaN in grain calculations with edge-case inputs.
- **Suggested test**: Parametrize with `agx_particle_area_um2=0.01`, density=0.0, density=10.0.

### TEST-013: Parametric density curves — no edge case tests
- **Severity**: P2
- **Evidence**: `tests/test_parametric.py` — 9 tests, all use standard parameters
- **Untested behavior**: `gamma=0`, `density_max=0`, `log_exposure_0` outside range, single-point log_exposure, empty log_exposure array.
- **Risk**: Division by zero or NaN when gamma=0.
- **Suggested test**: `parametrize` with edge-case values, assert finite output.

### TEST-014: Profile I/O — no malformed JSON test
- **Severity**: P2
- **Evidence**: `tests/test_profiles.py` — 12 tests, no error path for corrupted JSON
- **Untested behavior**: Malformed JSON, missing `info`/`data` keys, wrong array shapes in JSON, NaN in JSON.
- **Risk**: Cryptic errors when loading user-provided profile files.
- **Suggested test**: `pytest.raises` for each corruption type.

### TEST-015: Halide backend — no error path tests
- **Severity**: P2
- **Evidence**: `tests/test_halide_backend.py` — 6 tests, all happy path; `validation_matrix.md` notes "No error path tests (invalid inputs, shape mismatches)"
- **Untested behavior**: Invalid input shapes, unsupported dtypes, JIT compilation failures, cleanup after errors.
- **Risk**: Crashes or memory leaks when Halide backend receives bad input.
- **Suggested test**: Assert proper error for mismatched shapes, float64 input (unsupported), zero-size arrays.

### TEST-016: Diffusion filter — no invalid family test
- **Severity**: P2
- **Evidence**: `module_contracts.md` §7 — "ValueError for unknown filter family"; `test_edge_cases.py::TestStrengthToScatter` tests family but not full `apply_diffusion_filter_um`
- **Untested behavior**: `model/diffusion.py::apply_diffusion_filter_um` with unknown family string.
- **Risk**: Silent misbehavior instead of clear error.
- **Suggested test**: `pytest.raises(ValueError)` for `apply_diffusion_filter_um` with `filter_family="invalid"`.

### TEST-017: Image I/O — clipping behavior only implicitly tested
- **Severity**: P2
- **Evidence**: `validation_matrix.md` — JPEG/PNG/EXR clipping contracts all marked **WEAK**
- **Untested behavior**: JPEG output clipping to [0,1] uint8, PNG uint16, EXR no-clip behavior.
- **Risk**: Wrong bit depth or clipping could produce washed-out or clipped output.
- **Suggested test**: Save image with values > 1.0 and < 0.0 to each format, reload, verify clipping behavior matches contract.

### TEST-018: HDRPhotoMapping — missing field validation gaps
- **Severity**: P2
- **Evidence**: `tests/test_hdr_photo.py` — extensive `__post_init__` validation tests (40+ parametrized cases) but some newer fields may be untested
- **Untested behavior**: `profile_hdr_path_to_white_strength` passthrough to color recovery (H2 from code review), some compound validation (e.g., strength > 0 but start_ev > end_ev).
- **Risk**: Invalid mapping configurations pass validation silently.
- **Suggested test**: Add parametrized cases for any fields added after the initial validation sweep.

### TEST-019: Grain micro-structure multiplicative behavior untested
- **Severity**: P2
- **Evidence**: `module_contracts.md` §8 — "Micro-structure applies multiplicative lognormal clumping"; `validation_matrix.md` marked **UNTESTED**
- **Untested behavior**: `micro_structure=(sigma, threshold)` parameters in `GrainParams` — the lognormal clumping effect.
- **Risk**: Grain texture quality regression with micro-structure enabled.
- **Suggested test**: Compare grain output with `micro_structure=(0,0)` vs `(0.3, 0.5)`, assert they differ and both are finite.

### TEST-020: concurrent Simulator access untested
- **Severity**: P2
- **Evidence**: `validation_matrix.md` — "Metal serialization lock not tested under contention" marked **UNTESTED**
- **Untested behavior**: Multiple threads calling `Simulator.process()` simultaneously with a Metal backend.
- **Risk**: Race condition, crash, or corrupted output on macOS with MLX backend.
- **Suggested test**: Use `concurrent.futures.ThreadPoolExecutor` to process 4 images in parallel, assert all results are finite and correct.

---

## P3 — Low Severity / Quality Issues

### TEST-021: GPU backend tests silently pass when backends unavailable
- **Severity**: P3
- **Evidence**: `tests/test_gpu_backend.py::test_select_backend_mlx_is_strict_when_requested` (line 85-93) — `except BackendUnavailableError: return` silently passes
- **Issue**: On Linux without MLX/CuPy, these tests pass without testing anything. Should use `pytest.skip()` to make the skip visible.
- **Risk**: False confidence that GPU code is tested when it's not.
- **Suggested fix**: Replace `return` with `pytest.skip(str(exc))` in GPU backend tests.

### TEST-022: Regression baselines — only 5 cases, limited coverage
- **Severity**: P3
- **Evidence**: `tests/regression_baselines.py` — 5 `RegressionCase` entries; `tests/baselines/` — 5 `.npz` files
- **Issue**: Only covers `kodak_portra_400` + `kodak_portra_endura` and one Fuji pair. No coverage for: scan-film mode, HDR output, LUT path, ACES workflow, halide backend, grain/stochastic effects.
- **Risk**: Regressions in uncovered paths go undetected.
- **Suggested fix**: Add cases for scan-film mode, LUT path, and at least one more film stock.

### TEST-023: Regression baseline tolerance is loose (rtol=1.5e-3)
- **Severity**: P3
- **Evidence**: `tests/regression_baselines.py::assert_matches_baseline` — `rtol=1.5e-3, atol=1e-6`
- **Issue**: 0.15% relative tolerance allows meaningful numerical drift to go undetected. GPU parity tests use `rtol=1e-12` for CPU backends.
- **Risk**: Slow numerical drift accumulates undetected.
- **Suggested fix**: Tighten to `rtol=1e-4` or use per-case tolerances.

### TEST-024: conftest.py has minimal fixtures — high boilerplate
- **Severity**: P3
- **Evidence**: `tests/conftest.py` — only 3 fixtures (`small_rgb_image`, `default_params`, `portra_400_profile`)
- **Issue**: Most test files create their own synthetic data inline (density curves, LUT arrays, image fixtures). This leads to ~30% boilerplate across tests.
- **Suggested fix**: Add shared fixtures for common test data: `density_curves_3ch`, `density_cmy_2x2`, `lut_3d_7`, `sample_image_6x7`.

### TEST-025: Several modules have zero direct test coverage
- **Severity**: P3
- **Evidence**: Source module listing vs test file listing
- **Untested modules**:
  - `model/glare.py` — Glare model (only tested implicitly through pipeline)
  - `model/illuminants.py` — Illuminant spectra
  - `utils/preview.py` — Preview generation
  - `utils/calibration_targets.py` — Calibration target data
  - `utils/dtypes.py` — Dtype utilities
  - `utils/fast_stats.py` — Fast statistical operations
  - `utils/fast_interp.py` — Fast interpolation
  - `utils/math_ops.py` — Math operations
  - `runtime/stages/printing.py` — Print stage
  - `runtime/services/resize.py` — Resize service
  - `gpu/metal_serialization.py` — Metal serialization lock
  - `halide/availability.py` — Halide availability checking
- **Risk**: Regressions in these modules go completely undetected.
- **Suggested fix**: Add at least smoke tests for each module.

### TEST-026: test_gpu_validate.py — single test, no validation failure paths
- **Severity**: P3
- **Evidence**: `tests/test_gpu_validate.py` — 1 test for "skipped in debug mode"
- **Untested behavior**: GPU validation when enabled, validation failure detection, validation with mismatched CPU/GPU results.
- **Suggested test**: Test with `gpu_validate=True` in non-debug mode, test with intentionally mismatched results.

### TEST-027: test_gpu_highlight_boost.py — single test
- **Severity**: P3
- **Evidence**: `tests/test_gpu_highlight_boost.py` — 1 test for tiled vs full with `x_max`
- **Untested behavior**: Zero boost, negative threshold, boost with NaN input, boost with all-zero input.
- **Suggested test**: Parametrize edge cases.

### TEST-028: test_filming_stage.py — only 3 tests, all with monkeypatched internals
- **Severity**: P3
- **Evidence**: `tests/test_filming_stage.py` — 3 tests, all use `object.__new__` and `setattr`
- **Issue**: Tests bypass the normal constructor, so initialization logic is untested. All tests use monkeypatching.
- **Suggested fix**: Add at least one integration test that creates `FilmingStage` through its constructor.

### TEST-029: tests that would pass even if code was broken
- **Severity**: P3
- **Evidence**:
  - `test_edge_cases.py::TestCropImageBoundaryConditions` — asserts `ndim == 3` and `shape[0] > 0` (any 3D output passes)
  - `test_halide_android.py` — mostly availability checks that pass when Halide is unavailable
  - `test_gpu_backend.py::test_select_backend_auto_returns_usable_backend` — asserts `name in {"cpu", "mlx", "cupy"}` and `isinstance(backend.supports_gpu, bool)` (trivially true)
- **Suggested fix**: Replace shallow assertions with value-level checks.

### TEST-031: Color management tests import GUI module on headless server
- **Severity**: P1
- **Evidence**: `tests/test_color_management.py:6` — `from spektrafilm_gui.options import RGBColorSpaces`
- **Gap**: The entire test file imports from `spektrafilm_gui` at module level. On headless Linux CI where GUI is not installed, this causes `ModuleNotFoundError` and all 10 color management tests silently disappear from the suite.
- **Risk**: All color management encoding, ACES workflow, and validation tests are effectively disabled on the CI platform that needs them most.
- **Suggested fix**: Move `from spektrafilm_gui.options import RGBColorSpaces` inside `test_gui_rgb_color_spaces_include_acescg_working_space` with `pytest.importorskip("spektrafilm_gui")`.

### TEST-032: Pipeline smoke tests have zero value-level assertions
- **Severity**: P1
- **Evidence**: `tests/test_pipeline_smoke.py` — `_assert_valid_output` only checks shape, finiteness, and [0,1] bounds
- **Gap**: No test asserts that a specific input produces a specific output value. The pipeline could return uniform random noise in [0,1] and every smoke test would pass. `test_uniform_gray_output_is_stable_and_artifact_free` checks reproducibility but not correctness.
- **Risk**: Regressions in film simulation accuracy (wrong density curves, incorrect color transforms, broken LUT application) would go completely undetected by smoke tests.
- **Suggested fix**: Add at least one test with a known mid-gray input that asserts output values against a stored reference (even `atol=0.05`).

### TEST-033: LUT path comparison tolerance is too loose
- **Severity**: P2
- **Evidence**: `tests/test_pipeline_smoke.py:200` — `np.testing.assert_allclose(result_lut, result_direct, atol=0.02)`
- **Gap**: 2% absolute tolerance on a [0,1] scale for a 17-point LUT on uniform gray input is extremely loose. A LUT interpolation bug producing 1.5% error would pass.
- **Risk**: LUT indexing errors, wrong interpolation method, or boundary handling bugs go undetected.
- **Suggested fix**: Tighten to `atol=0.005` for uniform gray, or add a test with a color ramp that exercises non-trivial LUT interpolation regions.

### TEST-034: conftest.py small_rgb_image fixture uses float64
- **Severity**: P2
- **Evidence**: `tests/conftest.py:32` — `image = np.ones((16, 16, 3), dtype=np.float64)`
- **Gap**: The fixture creates float64 images while the GPU contract and production pipeline use float32. Tests using this fixture may exercise different code paths than production.
- **Risk**: float64 inputs bypass GPU float32 conversion logic, masking precision issues. Tests pass with float64 but production fails with float32.
- **Suggested fix**: Change fixture to `dtype=np.float32` or add a `small_rgb_image_f32` variant.

### TEST-035: JPEG gain map metadata roundtrip uses conditional assertion
- **Severity**: P2
- **Evidence**: `tests/test_gain_map.py:566-568` — `if loaded["metadata"] is not None: assert ...`
- **Gap**: If `load_gain_map` fails to extract metadata, the test silently passes without checking anything. The conditional degrades the test to a no-op on failure.
- **Risk**: A regression in JPEG MPF metadata embedding goes undetected because the test degrades gracefully instead of failing.
- **Suggested fix**: Assert `loaded["metadata"] is not None` unconditionally, then check values.

### TEST-036: Non-finite input testing is incomplete for HDR photo
- **Severity**: P2
- **Evidence**: `tests/test_hdr_photo.py:177-181` — only tests `np.inf` in `_prepare_hdr_rgb`
- **Gap**: Missing tests for `np.nan`, `-np.inf`, mixed finite/non-finite arrays, and non-finite values through the full `prepare_hdr_photo_renditions` pipeline (not just the internal `_prepare_hdr_rgb`).
- **Risk**: NaN propagation through rolloff, graft, or gamut mapping could produce silently corrupted output that downstream finite checks miss.
- **Suggested fix**: Add parametrized test for NaN, -Inf, and mixed non-finite inputs to both `_prepare_hdr_rgb` and `prepare_hdr_renditions`.

### TEST-037: No test for empty or single-pixel images through HDR pipeline
- **Severity**: P2
- **Evidence**: `tests/test_hdr_photo.py` — no test with `np.zeros((0, 0, 3))` or `np.zeros((1, 1, 3))`
- **Gap**: Percentile-based headroom computation and gain map encoding may behave unexpectedly with degenerate input sizes. Empty images could cause division by zero; single-pixel images exercise untested percentile edge cases.
- **Risk**: Crashes or NaN output when processing cropped or generated images with unusual dimensions.
- **Suggested fix**: Add test with single-pixel image through full pipeline, and verify empty image raises a clear error.

### TEST-038: encode_gain_map_log2 not tested with all-zero SDR
- **Severity**: P2
- **Evidence**: `tests/test_hdr_photo.py:1526-1533` — only tests identical SDR/HDR (zero gain)
- **Gap**: `encode_gain_map_log2` computes `log2(sdr / max(sdr, eps))` which could produce `-inf` when SDR is exactly zero if the `max(eps)` guard doesn't cover all code paths.
- **Risk**: Gain map with -inf values would corrupt downstream JPEG/HEIF encoding.
- **Suggested fix**: Add test with all-zero SDR input and verify all output values are finite.

### TEST-039: gain_map_statistics only tested for trivial 2x2 case
- **Severity**: P2
- **Evidence**: `tests/test_hdr_photo.py:1747-1755` — single 2x2 gain map
- **Gap**: Missing tests for all-zero map, all-one map, map with NaN/Inf, empty map. The `fraction_zero` and `fraction_one` metrics are only tested for one case.
- **Risk**: Statistics computation could produce incorrect results for degenerate inputs (e.g., `fraction_one` counting NaN as 1.0, or division by zero on empty map).
- **Suggested fix**: Add parametrized tests for all-zero, all-one, and NaN-containing gain maps.

### TEST-040: save_hdr_photo_heic never tested on non-Darwin platform
- **Severity**: P2
- **Evidence**: `tests/test_hdr_photo.py` — all HEIC tests monkeypatch `platform.system()` to `"Darwin"`
- **Gap**: No test verifies the function's behavior on Linux (the actual CI platform). Should raise a clear error rather than silently fail or produce corrupt output.
- **Risk**: If the function has a Linux code path that silently produces bad output instead of raising, it goes undetected.
- **Suggested fix**: Add test without Darwin monkeypatch that verifies `OSError` or `PlatformError` is raised on Linux.

### TEST-030: Redundant test coverage
- **Severity**: P3
- **Evidence**:
  - `test_edge_cases.py::TestHdrPhotoColorSpace` duplicates `test_hdr_photo.py::test_hdr_photo_color_space_*` (4 overlapping tests)
  - `test_pipeline_smoke.py::test_auto_exposure_normalizes_bright_inputs` partially duplicates `test_autoexposure.py` coverage
  - `test_edge_cases.py::TestPipelineSoftUpdate` partially duplicates `test_runtime_api.py::test_soft_update_*`
- **Suggested fix**: Consolidate duplicated tests into one canonical location.

---

## Summary

| Severity | Count | Description |
|----------|-------|-------------|
| P0 | 4 | Critical invariants with zero test coverage |
| P1 | 7 | High-risk behavior gaps |
| P2 | 19 | Medium-quality or coverage gaps |
| P3 | 10 | Low-severity quality issues |
| **Total** | **40** | |

### Top 5 Recommendations (by risk/reward)

1. **TEST-031**: Fix color management GUI import — restores 10 tests on headless CI (immediate value)
2. **TEST-032**: Add value-level assertions to pipeline smoke tests — prevents silent accuracy regressions
3. **TEST-001**: Add diffusion filter energy conservation test — prevents silent HDR luminance drift
4. **TEST-004**: Add grain RNG state restoration test — prevents non-deterministic behavior
5. **TEST-005**: Add digest_params idempotency test — prevents double-digest bugs

### Modules Most in Need of Tests

1. `model/glare.py` — zero coverage, used in every print pipeline
2. `runtime/stages/printing.py` — zero coverage, core pipeline stage
3. `model/illuminants.py` — zero coverage, spectral correctness depends on it
4. `gpu/metal_serialization.py` — zero coverage, concurrency correctness
5. `runtime/services/resize.py` — zero coverage, image preprocessing
