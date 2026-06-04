# MLX GUI Full Render Hot Path Report - 2026-06-03

## Goal

Improve Spektrafilm GUI MLX full-render observability and warm-run behavior for 12MP DNG processing without changing SDR rendering semantics, weakening HDR HEIC/gain-map export, or lowering default output quality.

## Baseline And Audit

- Test DNG: `/Users/retriedstormtrooper/Downloads/IMG_4897/IMG_4897.DNG`
- Shape after Spektrafilm RAW load: `(3024, 4032, 3)`, 12.19 MP, `float64`
- User-reported GUI baseline before this pass: MLX GPU full render about 16-17s, CPU about 21-24s for a 12MP RAW.
- Current source audit found three confirmed hot-path issues:
  - `fft_convolve_same_backend()` forced `mx.eval()` and `mx.metal.clear_cache()` inside the MLX diffusion FFT helper.
  - `SimulationPipeline.update()` cleaned the MLX backend on every GUI parameter update, even when backend and precision did not change.
  - non-preview MLX `process()` cleaned the backend after every full render, hiding the cost and destroying warm-run cache locality.
- Current GUI worker only exposed one total elapsed string, so runtime process, materialization, display transform, and layer update were not separable.

## Changes

- Removed the intermediate `mx.eval(convolved)` and `mx.metal.clear_cache()` from `src/spektrafilm/gpu/kernels/filters.py`.
- Added MLX backend reuse across `SimulationPipeline.update()` when `compute_backend` and `gpu_precision` are unchanged.
- Added cleanup policy settings:
  - `settings.gpu_aggressive_cleanup: bool = False`
  - `settings.gpu_cleanup_cache_threshold_mb: float | None = 8192.0`
- Changed cleanup behavior:
  - same-backend warm updates no longer clean by default;
  - backend replacement still cleans the old MLX backend;
  - full render cleans only when aggressive cleanup is enabled or MLX cache memory exceeds the threshold.
- Added runtime timings for normal end-to-end pipeline stages:
  - `preprocess`
  - `filming.expose`
  - `filming.develop`
  - `printing.expose`
  - `printing.develop`
  - `scanning.scan_print` / `scanning.scan_film`
  - `SimulationPipeline.materialize`
  - `SimulationPipeline.mlx_cleanup` when cleanup runs
- Added GUI worker/controller phase timings:
  - `gui.input_conversion`
  - `runtime.process`
  - `gui.display_prepare`
  - `gui.float_materialize`
  - `gui.worker_total`
  - `gui.layer_update`
- Persisted GUI phase timings into output layer metadata as `pipeline_phase_timings`.
- Extended `scripts/benchmark_mlx_runtime_hotpath.py` with:
  - visible load/decode progress;
  - load and resize timings;
  - `--only-backend {all,cpu,mlx}`;
  - `--skip-gpu-validate`.

## Performance Evidence

Artifacts:

- `docs/dev/benchmark-artifacts/mlx_gui_full_render_20260603/benchmark-20260604-000926.json`
- `docs/dev/benchmark-artifacts/mlx_gui_full_render_20260603/benchmark-20260604-000926.md`
- `docs/dev/benchmark-artifacts/mlx_gui_full_render_20260603/benchmark-20260603-235842.json`
- `docs/dev/benchmark-artifacts/mlx_gui_full_render_20260603/benchmark-20260603-235842.md`

### MLX Full-Res, No-Grain Benchmark Script

Command:

```bash
.venv/bin/python scripts/benchmark_mlx_runtime_hotpath.py \
  --input /Users/retriedstormtrooper/Downloads/IMG_4897/IMG_4897.DNG \
  --size full \
  --warmups 1 \
  --runs 2 \
  --no-preview-640 \
  --no-type-trace \
  --only-backend mlx \
  --skip-gpu-validate \
  --out-dir docs/dev/benchmark-artifacts/mlx_gui_full_render_20260603
```

Result:

- Load/decode: 2.3250s
- Warmup process: 4.2001s
- Timed runs: 3.6481s, 4.6971s
- Best timed wall: 3.6481s
- Average timed wall: 4.1726s
- Last pipeline total: 4.6229s

Largest last-run stages:

| Stage | Seconds |
| --- | ---: |
| `filming.expose` | 2.9535 |
| `scanning.scan_print` | 0.8275 |
| `SimulationPipeline.materialize` | 0.6330 |
| `filming.develop` | 0.1809 |
| `preprocess` | 0.0243 |

Conversion counters stayed at small final `to_numpy` counts:

- `backend.asarray`: 160 calls, about 24.87 GB input counted by trace wrappers
- `backend.to_numpy`: 4 calls, 48 bytes input/output counted by trace wrappers

MLX memory probe on the same no-grain path:

- Run 1 wall: 4.8102s, cache about 6.389 GB
- Run 2 wall: 5.9625s, cache about 6.389 GB
- The 8GB cache threshold did not trigger, preserving the fast no-grain warm path.

### MLX Full-Res, Default-Quality Diagnostic

This diagnostic kept grain and halation active, did not enable `gpu_validate`, and used the new default 8GB cache cleanup threshold.

Result:

- Load/decode: 0.9370s
- Cold process wall: 22.6179s
- Warm process wall: 33.6113s
- Cold MLX peak memory: about 12.35 GB
- Warm MLX peak memory: about 12.35 GB
- Cache after each process: 0, because threshold cleanup triggered
- Cleanup time: 0.8491s cold, 1.4842s warm

Largest warm stages:

| Stage | Seconds |
| --- | ---: |
| `scanning.scan_print` | 22.7918 |
| `SpectralLUTService.spectral_compute_scanner` | 22.7713 |
| `SimulationPipeline.materialize` | 2.7036 |
| `preprocess` | 2.4795 |
| `filming.expose` | 1.8253 |
| `filming.develop` | 0.5520 |

Before adding threshold cleanup, a default-quality diagnostic in the same session produced a 55.3870s warm process with no cleanup. The threshold cleanup reduced that observed memory-pressure failure mode, but default-quality warm timing is still not back to the user's reported 16-17s on this machine.

### CPU Smoke

Full-res CPU script run did not complete after more than 120s and was terminated. That result is not a valid CPU baseline and likely reflects a parameter mismatch or local runtime state.

CPU smoke on the same DNG downsampled to 1024x768:

- Load/decode: 3.135s
- Resize: 0.117s
- CPU process total/wall: 2.623s / 2.624s

## Validation

Regression tests added or updated:

- `tests/test_gpu_filters.py`
- `tests/test_pipeline_lut_lifecycle.py`
- `tests/gui/test_controller_runtime_module.py`
- `tests/gui/test_controller_flow.py`
- `tests/test_mlx_runtime_hotpath_benchmark.py`

Commands and results:

```bash
.venv/bin/python -m pytest \
  tests/test_gpu_backend.py \
  tests/test_gpu_filters.py \
  tests/test_gpu_pipeline.py \
  tests/test_pipeline_lut_lifecycle.py \
  tests/gui/test_controller_runtime_module.py \
  tests/gui/test_controller_flow.py \
  tests/test_mlx_runtime_hotpath_benchmark.py -q
```

Result: 93 passed, 3 skipped.

```bash
.venv/bin/python -m pytest \
  tests/test_hdr_photo.py \
  tests/test_gain_map.py \
  tests/test_hdr_profile_validation_tool.py \
  tests/test_hdr_curve_profiles.py -q
```

Result: 226 passed.

```bash
.venv/bin/python -m compileall -q src/spektrafilm src/spektrafilm_gui scripts/benchmark_mlx_runtime_hotpath.py
git diff --check
```

Result: passed with no output.

## SDR And HDR Safety

- No SDR math path was intentionally changed.
- CPU backend code paths remain covered by the broader GPU/runtime tests and the 1024x768 CPU benchmark smoke.
- HDR HEIC/gain-map unit coverage passed. Existing unrelated dirty changes in `src/spektrafilm/utils/hdr_photo.py` and `tests/test_hdr_photo.py` were present before this pass and were not edited by this work.
- No HDR settings were merged into ordinary SDR settings.
- No save/export code was removed.

## Remaining Bottlenecks

1. Default-quality MLX is now observably dominated by scanner spectral computation, especially `SpectralLUTService.spectral_compute_scanner`.
2. Default-quality full-res runs exceed the no-grain benchmark because grain-active density data makes downstream scanner work much heavier.
3. Final materialization is still visible at 0.63s no-grain and 2.70s default-quality warm.
4. Grain MLX still has Python channel/sublayer loops and many random/filter launches. This was audited but not fused in this pass because preserving grain statistics needs a separate validation matrix.
5. CPU full-res baseline could not be reproduced locally with the benchmark script; only the smaller CPU smoke is valid evidence from this run.

## Follow-Up Route

- Add a scanner-specific MLX optimization pass:
  - compare direct spectral scanner vs scanner LUT on default-quality 12MP;
  - verify SDR delta before considering any default setting change;
  - consider a fused `cmy_to_log_xyz -> XYZ -> RGB` MLX/Metal kernel for scanner output.
- Add a grain-specific pass:
  - collect per-channel/sublayer timing and kernel launch counts;
  - create statistical parity tests for grain mean/std/autocorrelation;
  - then evaluate vectorized MLX grain or a fused Metal grain kernel.
- Add an explicit GUI benchmark harness that exercises real `execute_simulation_request()` and `prepare_output_display_image()` on a headless viewer fake, so GUI display timing is measured in CI-style smoke tests.
- Add optional HEIC encode timing to the benchmark script once a stable small HDR sample is available.

## Confidence

I have high confidence in the specific implemented changes and test evidence:

- the diffusion FFT MLX helper no longer synchronizes or clears cache internally;
- same-backend GUI warm updates no longer force MLX cleanup or backend replacement;
- GUI/runtime phase timings are observable;
- HDR unit coverage still passes.

I do not have 100% factual confidence that this fully reaches the user's reported GUI default-quality 16-17s target on this machine. The remaining uncertainty is the default-quality scanner spectral bottleneck and local full-res CPU mismatch. More user-aligned GUI state, a saved preset, or an exact reproduction of the user's 16-17s parameter set is needed before claiming complete performance closure.
