# MLX 3D LUT Trilinear Metal Kernel Acceptance

Date: 2026-06-19

Scope: v0 `spektrafilm_lut_trilinear_3d` correctness and launch-only threadgroup sweep.
The kernel math was not changed for this pass. No vectorized load, loop unroll,
tiling, or one-thread-per-pixel rewrite was attempted.

## Acceptance Benchmark

Artifacts:

- `docs/reports/mlx-lut-trilinear-3d-acceptance-20260619-220053.json`
- `docs/reports/mlx-lut-trilinear-3d-acceptance-20260619-220053.md`

All timed regions exclude kernel compile/setup. The full-res case skips the
NumPy reference materialization to avoid adding a large extra CPU allocation;
it still checks Metal output against the MLX ops baseline.

| Case | MLX ops median | Metal median | Metal p90 | Peak memory MLX ops | Peak memory Metal | Median speedup | Max diff vs MLX ops |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 256x256, LUT 17 | 2.227 ms | 0.348 ms | 0.377 ms | 12.1 MiB | 4.6 MiB | 6.396x | 1.788e-07 |
| 768x1024, LUT 33 | 10.603 ms | 0.756 ms | 1.298 ms | 144.4 MiB | 54.4 MiB | 14.017x | 1.788e-07 |
| 3024x4032, LUT 33 | 228.497 ms | 10.742 ms | 12.130 ms | 2233.2 MiB | 837.7 MiB | 21.272x | 1.788e-07 |

Result: the v0 Metal kernel is accepted as a real-size improvement over the
MLX array-ops baseline. The numerical delta is below visible relevance and
stays within the existing LUT test tolerance.

## Threadgroup Sweep

Artifact:

- `docs/reports/mlx-lut-trilinear-3d-threadgroup-sweep-20260619-220126.md`

Acceptance criteria for replacing the current launch size:

- median improves by more than 3% versus the current accepted implementation,
- p90 does not regress by more than 3%,
- peak memory does not clearly increase.

| Case | TG 64 median / p90 | TG 128 median / p90 | TG 256 median / p90 | TG 512 median / p90 | Case decision |
| --- | ---: | ---: | ---: | ---: | --- |
| 256x256, LUT 17 | 0.324 / 0.338 ms | 0.299 / 0.327 ms | 0.353 / 0.393 ms | 0.299 / 0.326 ms | 128 accepted for this small case |
| 768x1024, LUT 33 | 0.969 / 1.433 ms | 1.040 / 2.170 ms | 0.975 / 1.920 ms | 1.085 / 1.150 ms | keep 256 |
| 3024x4032, LUT 33 | 10.696 / 12.108 ms | 8.143 / 8.230 ms | 7.973 / 8.011 ms | 7.980 / 8.024 ms | keep 256 |

Global decision: keep threadgroup size 256. The small preview case prefers 128,
but the medium and full-res cases do not show a stable, cross-size improvement.
The full-res case is the strongest hot-path proxy and 256 remains the best
median there.

## Next Optimization Gate

Do not proceed directly to vectorized loads, loop unroll, or tiling from this
data. The next meaningful optimization dimension is changing thread semantics
from one output channel per thread to one pixel per thread writing three output
channels. That should be evaluated in a separate branch of benchmarks because
it changes the output mapping and coordinate reuse behavior.
