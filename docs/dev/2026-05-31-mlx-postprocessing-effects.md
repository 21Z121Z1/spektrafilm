# MLX Postprocessing Effects Feasibility And Implementation

Date: 2026-05-31

Scope: evaluate and harden the MLX backend path for spatial postprocessing effects: halation, diffusion, grain, and adjacent blur/sharpen filters used by the runtime pipeline.

## Conclusion

Connecting these effects to MLX is feasible and appropriate on Apple Silicon, with one precision constraint:

- Halation is a good MLX target. The active path is highlight boost plus Gaussian and exponential Gaussian-mixture filtering, all of which can remain as MLX arrays.
- Diffusion is a good MLX target. The runtime builds a small PSF from parameters on CPU, then uses MLX reflect padding and FFT convolution for the full-image work.
- Grain is feasible as an MLX statistical backend. It should be deterministic for a fixed MLX seed and statistically plausible, but it is not expected to be pixel-identical to the CPU SciPy/NumPy RNG path.
- MLX GPU postprocessing must use `float32` or `float16`. `float64` is CPU-reference territory because MLX documents that `float64` arrays only work with CPU operations and fail on GPU.

The implementation keeps full-image halation, diffusion, and grain operations resident on MLX until the caller explicitly materializes the final output.

## Source Check

Current MLX 0.31.2 documentation and the local runtime shape the implementation:

- MLX uses lazy evaluation: operations record a graph and computation happens at `eval()`. Benchmarks and tests therefore need explicit evaluation before timing or assertions.
- Apple Silicon MLX uses unified memory, so arrays do not need manual CPU/GPU transfers. This does not mean callers should convert full images to NumPy in the middle of a GPU path.
- MLX supports custom Metal kernels through `mx.fast.metal_kernel`, and the current filter code already uses this for reflect padding and Gaussian IIR kernels.
- MLX exposes FFT APIs, which makes the existing diffusion PSF convolution a good fit.
- MLX exposes keyed random APIs, which makes deterministic fixed-seed statistical grain possible on the backend.

Primary references:

- <https://ml-explore.github.io/mlx/build/html/usage/lazy_evaluation.html>
- <https://ml-explore.github.io/mlx/build/html/usage/unified_memory.html>
- <https://ml-explore.github.io/mlx/build/html/python/data_types.html>
- <https://ml-explore.github.io/mlx/build/html/dev/custom_metal_kernels.html>

## Workspace Findings

Relevant current files:

- `src/spektrafilm/model/diffusion.py` already accepts `backend` for halation, Gaussian blur, and diffusion filter calls.
- `src/spektrafilm/gpu/kernels/filters.py` provides backend-aware Gaussian, exponential, reflect-pad, and FFT convolution helpers.
- `src/spektrafilm/model/grain.py` routes grain generation through MLX when a backend is supplied.
- Runtime stages pass the selected backend into camera diffusion, lens blur, halation, print diffusion, scanner blur, and unsharp filters.

Local MLX probe:

- `mlx.__version__ == 0.31.2`
- `mx.metal.is_available() == True`
- `select_backend("mlx")` succeeds and returns `float32` arrays on the backend.

## Implementation Changes

### Halation

The red test exposed that the halation scatter tail could route through `exponential_filter_backend()`, which previously selected `_precision="float64"` for MLX Gaussian components. MLX rejects GPU `float64`, then the fallback materialized the full image with `backend.to_numpy()`.

Fix:

- `exponential_filter_backend()` now defaults to `_precision="float32"`.
- `gaussian_filter_backend()` and mixed-sigma helpers pass precision explicitly.
- Callers that need exact CPU-reference behavior can still request `_precision="float64"`, accepting a CPU fallback on MLX.

### Diffusion

No production fix was required for the current diffusion filter path. A residency test now guards that the MLX path does not materialize the full image on CPU while applying the diffusion PSF convolution.

The small PSF construction remains CPU-side and parameter-sized. That is acceptable because the image-sized convolution runs through backend reflect padding and FFT.

### Grain

The red test exposed a full-image transfer in `_layer_particle_model_gpu()`:

- the code evaluated `seeds`,
- converted the full `seeds` image to NumPy,
- used `max()` only to decide whether to run the binomial approximation.

Fix:

- Remove that CPU materialization.
- Always run the vectorized MLX normal approximation for `Binomial(seeds, p)`.
- Clamp the result to `[0, seeds]`, which naturally handles zero-particle pixels.

This keeps fixed-seed MLX grain deterministic and keeps the image-sized random work on MLX.

The public `layer_particle_model()` also has a non-default `gamma_beta` method. That method is not an MLX acceleration target in this pass, so passing an MLX backend now falls back to the CPU reference path instead of silently returning an all-zero grain image. Unknown grain particle methods now raise `ValueError`.

## Test Coverage

Added focused tests:

- `test_halation_mlx_stays_on_device_when_available`
- `test_diffusion_filter_mlx_stays_on_device_when_available`
- `test_apply_grain_to_density_mlx_does_not_materialize_when_available`
- `test_apply_grain_to_density_mlx_is_deterministic_for_fixed_seed`
- `test_apply_grain_to_density_mlx_statistics_are_plausible`
- `test_layer_particle_model_mlx_falls_back_for_gamma_beta`
- `test_layer_particle_model_rejects_unknown_method`

These tests monkeypatch `backend.to_numpy()` to fail inside the MLX computation where full-image CPU materialization would be a regression. Final assertions intentionally materialize only after `backend.eval()`.

## Verification

TDD red failures before fixes:

- Halation residency failed because MLX `float64` Gaussian IIR raised, then the fallback called `backend.to_numpy(image)`.
- Grain residency failed at `backend.to_numpy(seeds).max()`.

Focused green checks after fixes:

```bash
.venv/bin/python -m pytest tests/test_gpu_filters.py::test_halation_mlx_stays_on_device_when_available tests/test_gpu_filters.py::test_diffusion_filter_mlx_stays_on_device_when_available -q
# 2 passed

.venv/bin/python -m pytest tests/test_grain.py::TestApplyGrain::test_apply_grain_to_density_mlx_does_not_materialize_when_available -q
# 1 passed

.venv/bin/python -m pytest tests/test_grain.py -q
# 16 passed
```

Final broader verification for this change:

```bash
.venv/bin/python -m pytest tests/test_gpu_filters.py tests/test_grain.py -q
# 32 passed, 1 skipped

.venv/bin/python -m pytest tests/test_gpu_backend.py tests/test_gpu_lut.py tests/test_gpu_filters.py tests/test_gpu_density.py tests/test_gpu_color_chain.py tests/test_gpu_pipeline.py tests/test_gpu_primitives.py tests/test_grain.py -q
# 133 passed, 7 skipped

.venv/bin/python -m pytest --ignore=tests/gui -q
# 701 passed, 7 skipped, 1 warning

.venv/bin/python -m compileall -q src tests
# passed

git diff --check
# passed
```

## Known Boundaries

- MLX grain is statistical. Fixed seed should be deterministic on MLX, but pixel parity against CPU SciPy/NumPy RNG is not a correctness target.
- The default `poisson_binomial` grain method is the MLX-accelerated method. The legacy `gamma_beta` method falls back to CPU when a backend is provided.
- Final output still has to materialize when the caller writes images or compares arrays.
- Small parameter arrays, PSFs, LUT tables, and color reference values may be constructed on CPU; the guarded boundary is image-sized intermediate transfer.
- `compute_backend="auto"` with `float64` should remain CPU-reference behavior. Explicit GPU `float64` should fail strictly instead of silently pretending to be accelerated.
- MLX lazy evaluation means timing without `eval()`/synchronization is not reliable evidence.
