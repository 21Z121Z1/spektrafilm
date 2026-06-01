# MLX Compile Element-Wise Chain Implementation - 2026-05-31

## Scope

This pass implements guarded `mx.compile` use for MLX-only pure element-wise chains. CPU behavior, explicit `float64` CPU routing, Halide fused spectral routing, LUT interpolation semantics, and final pipeline materialization are unchanged.

## Official MLX Constraints Used

- `mx.compile()` can reduce graph size by fusing operations and removing common work.
- The first call to a compiled function traces and compiles the graph.
- Normal compiled functions recompile when input shapes change.
- `shapeless=True` avoids shape-triggered recompilation, but it is unsafe for graphs that depend on static shape. Spektrafilm image processing keeps the default shape-aware behavior.
- Compiled functions must not inspect or materialize arrays. This implementation keeps `print`, `np.asarray`, `.item()`, `mx.eval()`, `mx.synchronize()`, and scalar reductions outside compiled chains.

References:

- MLX compilation docs: https://ml-explore.github.io/mlx/build/html/usage/compile.html
- MLX lazy evaluation docs: https://ml-explore.github.io/mlx/build/html/usage/lazy_evaluation.html

## Implementation

`MlxBackend.compiled_elementwise(name, function, *sample_args)` caches compiled callables by:

- operation name
- MLX input shape
- MLX input dtype

The helper returns the original function if the current MLX module does not expose `compile`, keeping fake/test modules and older MLX builds safe.

Compiled production chains:

- `density_to_light`: `10 ** (-density) * illuminant`, followed by finite cleanup.
- CCTF encode/decode transfer functions in `gpu/kernels/color.py`.
- Highlight boost's per-pixel exponential curve after `x_max` has already been reduced to a Python scalar. Runtime scalar parameters are passed as a `(4,)` backend array, so changing exposure parameters does not require Python closure recompilation.

Intentionally not compiled:

- `safe_log10(max(x, 0) + 1e-10)`: benchmarked as slower when compiled.
- `einsum`, `matmul`, LUT gather/interpolation, Gaussian IIR/FIR, FFT convolution, and custom Metal kernels.
- Any path that converts to NumPy, synchronizes, prints, or branches on tensor values.

## Benchmark

Command:

```bash
.venv/bin/python scripts/benchmark_mlx_compile_elementwise.py --height 512 --width 512 --iterations 10
```

Artifact:

- `docs/dev/benchmark-artifacts/mlx_compile_elementwise_20260531/benchmark-20260531-172206.md`
- `docs/dev/benchmark-artifacts/mlx_compile_elementwise_20260531/benchmark-20260531-172206.json`

Results use fixed `512x512x3` float32 input, fixed seed `20260531`, 3 warmup iterations, 10 timed iterations, and explicit `mx.eval()` plus `mx.synchronize()` per timed sample.

| Chain | Baseline median | Compiled median | Median speedup | Max abs diff | Production decision |
|---|---:|---:|---:|---:|---|
| `safe_log10` | 0.399 ms | 0.719 ms | 0.555x | 0.000e+00 | Do not compile |
| `density_to_light` | 27.368 ms | 3.349 ms | 8.171x | 0.000e+00 | Compile |
| `cctf_encode_srgb` | 0.680 ms | 0.466 ms | 1.461x | 2.384e-07 | Compile transfer chains |
| `boost_highlights` | 0.513 ms | 0.273 ms | 1.878x | 0.000e+00 | Compile |

## Verification

Fresh targeted verification after rejecting compiled `safe_log10`:

```text
.venv/bin/python -m pytest tests/test_gpu_backend.py tests/test_gpu_color_chain.py tests/test_gpu_density.py tests/test_gpu_pipeline.py -q
76 passed, 4 skipped
```

Final verification:

```text
.venv/bin/python -m pytest tests/test_gpu_backend.py tests/test_gpu_lut.py tests/test_gpu_filters.py tests/test_gpu_density.py tests/test_gpu_color_chain.py tests/test_gpu_pipeline.py tests/test_gpu_primitives.py -q
115 passed, 7 skipped

.venv/bin/python -m pytest --ignore=tests/gui -q
701 passed, 7 skipped, 1 warning

.venv/bin/python -m compileall -q src/spektrafilm tests scripts
passed

git diff --check
passed
```

## Self-Audit

- No compiled function performs materialization, synchronization, printing, `.item()`, or scalar reduction.
- Cache keys are shape/dtype-specific. Shape changes create a separate compiled callable instead of using shapeless compilation.
- Benchmark timing includes evaluation and synchronization.
- `safe_log10` was removed from production compilation after benchmark evidence showed negative speedup.
- Numerical differences are zero for `density_to_light`, `safe_log10`, and `boost_highlights`; CCTF encode diff is within float32 epsilon.
- Existing dirty-worktree changes were not reverted.
