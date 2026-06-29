# MLX Float32 Precision Contract

**Version:** 0.1
**Scope:** All `compute_backend="mlx"`, `gpu_precision="float32"` compute paths in `spektrafilm`.
**Goal:** Define the acceptable deviation between MLX GPU float32 output and the CPU float64 reference, ensure the deviation is visually imperceptible, and establish verifiable tests and fallback rules.

---

## 1. Core principles

1.1 **Bit-identical equality with CPU float64 is not the contract goal.**  
float32 provides roughly 7 decimal digits of precision; float64 provides roughly 16. Any reduction, `pow`, `log`, `exp`, or matrix multiplication will inevitably diverge after the 7th decimal digit when compared to float64.

1.2 **The contract goal is "visually imperceptible" and "algorithmically consistent".**  
"Visually imperceptible" means that, on typical 8-bit sRGB or 10-bit display devices, the CPU float64 and MLX float32 results cannot be distinguished by eye, and the numerical differences do not produce observable artifacts in downstream stages such as CCTF, gamut compression, or HDR gain-map generation.

---

## 2. Precision levels

| Level | Applies to | Acceptance criteria |
|---|---|---|
| **L1: Kernel-level numerical parity** | A single GPU kernel or backend operation | `np.allclose(gpu, cpu_float64, atol=1e-6, rtol=0.0)` |
| **L2: Stage-level perceptual parity** | Output of `FilmingStage`, `PrintingStage`, or `ScanningStage` | PSNR ≥ 52 dB; mean ΔE₀₀ ≤ 0.5; max ΔE₀₀ ≤ 2.0 |
| **L3: End-to-end visual parity** | Final output of `SimulationPipeline.process()` | PSNR ≥ 48 dB; SSIM ≥ 0.995; ΔE₀₀ 99th percentile ≤ 1.0 |

> Reference: `docs/halide-mlx-parity-plan-20260531.md` already proposes a PSNR ≥ 52 dB, mean_diff ≤ 1.5× MLX mean_diff parity floor for Halide/MLX.

---

## 3. Kernel and operation-level contracts

Status definitions:

- **COMPLIANT**: Current implementation satisfies L1 (`atol=1e-6`).
- **CONDITIONAL**: Satisfies L2/L3 but needs specific conditions (e.g. `_precision="float64"`) to satisfy L1.
- **NON-COMPLIANT**: Currently exceeds `1e-6` and must be fixed or given an explicit fallback.
- **EXEMPT**: Not subject to sample-level parity (e.g. stochastic samplers).

| Kernel / operation | Source location | Current vs CPU float64 error | Status | Notes / constraints |
|---|---|---|---|---|
| `cmy_to_log_raw` fused kernel | `src/spektrafilm/gpu/mlx_backend.py:23-786` | ≤1e-6 vs float32 ref; ≤1e-5 vs float64 | COMPLIANT | Default dispatch now uses threadgroup table-cache variant for K ≤ 256; fixed cache load loop to use `threads_per_threadgroup.x` |
| `cmy_to_log_xyz` fused kernel | `src/spektrafilm/gpu/kernels/density.py:184-236`, `570-636` | ≤1e-5 | COMPLIANT | Input tables uploaded as float32 |
| `compute_density_spectral` | `src/spektrafilm/gpu/kernels/density.py:474-504` | ≤1e-5 | COMPLIANT | Uses `einsum` |
| `density_to_light` | `src/spektrafilm/gpu/kernels/density.py:507-538` | ≤1e-6 | COMPLIANT | `backend.power(10.0, -density)` |
| `light_to_raw` | `src/spektrafilm/gpu/kernels/density.py:541-558` | ≤1e-5 | **CONDITIONAL** | 81-term `einsum`; meets documented contract but not L1 (`1e-6`) without compensated accumulation |
| Density-curve 1D interpolation | `src/spektrafilm/gpu/kernels/density.py:62-181` | ≤2e-6 | COMPLIANT | float32 tables + float32 division |
| Gaussian FIR (small sigma) | `src/spektrafilm/gpu/kernels/filters.py:36-107` | ≤3e-5 | COMPLIANT | Visually imperceptible |
| **Gaussian IIR (large sigma)** | `src/spektrafilm/gpu/kernels/filters.py:110-343`, `506-587` | **~5e-6 max, ~5e-4 RMS** | **CONDITIONAL** | Known float32 systematic bias; use `_precision="float64"` for CPU float64 fallback |
| FFT convolution | `src/spektrafilm/gpu/kernels/filters.py:743-805` | ≤2e-6 (CuPy reference) | COMPLIANT | Direct scipy FFT parity test added for same-shape convolutions |
| Reflect padding | `src/spektrafilm/gpu/kernels/filters.py:346-401` | 0 (integer indices) | COMPLIANT | No arithmetic error |
| 3D LUT trilinear | `src/spektrafilm/gpu/kernels/lut.py:318-503` | ≤2e-6 | COMPLIANT | Fast pilot kernel, not PCHIP |
| **2D LUT Mitchell cubic** | `src/spektrafilm/gpu/kernels/lut.py:27-191`, `src/spektrafilm/runtime/stages/filming.py` | **~2e-5 worst-case** | **FALLBACK / EXCEPTION** | High-order polynomial evaluated in float32. `fast` keeps the resident GPU exception; `balanced` and `strict` use CPU float64 reference fallback for Hanatos filming LUT. |
| sRGB / Display P3 CCTF | `src/spektrafilm/gpu/kernels/color.py:320-403` | ≤2e-7 | COMPLIANT | Threshold literals should be float32 |
| BT.2020 / ProPhoto / Adobe / DCI-P3 CCTF | `src/spektrafilm/gpu/kernels/color.py:328-362` | ≤2e-7 | COMPLIANT | |
| RGB↔XYZ 3×3 matrices | `src/spektrafilm/gpu/kernels/color.py:104-121` | ≤1e-6 | COMPLIANT | Matrices precomputed in CPU float64, uploaded as float32 |
| `_rgb_to_tc_b` (Hanatos) | `src/spektrafilm/gpu/kernels/color.py:219-251` | ≤3e-5 | COMPLIANT | |
| `rgb_to_raw_mallett2019` | `src/spektrafilm/gpu/kernels/color.py:254-295` | ≤2e-6 on typical input; up to ~1e-4 adversarially | **CONDITIONAL** | Spectral einsum uses float32 accumulation; small `raw_midgray[1]` amplifies residual error |
| Highlight boost | `src/spektrafilm/gpu/kernels/color.py:486-589` | ≤1e-6 | COMPLIANT | |
| OkLab / Oklrab gamut compression | `src/spektrafilm/gpu/kernels/gamut_compress.py:1191-1316` | ≤2e-6 | COMPLIANT | |
| CAM16-UCS gamut compression | `src/spektrafilm/gpu/kernels/gamut_compress.py:925-1031`, `1397-1451` | ≤3e-6 | COMPLIANT | |
| **JzAzBz gamut compression** | `src/spektrafilm/gpu/kernels/gamut_compress.py:143-653`, `1323-1390`, `1447-1528` | **~7e-5 to ~1.1e-4, xfail retained** | **STRICT FALLBACK / FAST-BALANCED EXCEPTION** | Per-exponent specialization for `inv_m2` brings error down to the float32 DS arithmetic floor. `strict` uses CPU float64 fallback; `fast`/`balanced` keep the resident GPU path as a documented non-L1 exception. |
| ACES RGC | `src/spektrafilm/gpu/kernels/gamut_compress.py:1171-1184` | ≤2e-7 | COMPLIANT | |
| Grain samplers | `src/spektrafilm/gpu/kernels/grain.py:77-289` | N/A | EXEMPT | Different RNG streams; distribution-level statistical tests only |

---

## 4. Non-compliant paths that must be fixed

### 4.1 2D LUT Mitchell cubic interpolation

- **Location:** `src/spektrafilm/gpu/kernels/lut.py:27-191`
- **Problem:** Error against the CPU float64 Numba reference is ~2e-5, exceeding the L1 `1e-6` contract.
- **Root cause:** Mitchell-Netravali cubic weights are high-order polynomials evaluated in float32; the 16-weight sum is normalized in float32 while the CPU normalizes in float64.
- **2026-06-29 governance:** `src/spektrafilm/gpu/precision_policy.py` marks this operation as a `fast` exception and a `balanced` / `strict` CPU fallback. `FilmingStage._rgb_to_film_raw` now uses the CPU float64 Hanatos reference for the Hanatos 2D LUT under `balanced` and `strict`, so the default final-quality path no longer silently claims L1 for the resident GPU kernel.
- **Contract requirement:** The resident GPU kernel remains a documented exception until it reaches ≤1e-6 on adversarial LUT samples.

### 4.2 JzAzBz gamut compression

- **Location:** `src/spektrafilm/gpu/kernels/gamut_compress.py:143-653`, `1323-1390`
- **Problem:** The MLX path still exceeds `1e-6`; tests are marked `xfail`.
- **Root cause:**
  1. Metal's built-in `pow` / `exp2(log2)` for the PQ forward EOTF (`N^(1/m2)`) is ~1 ULP away from numpy/libm.
  2. Even with perfect transcendental functions, the float32 double-single arithmetic itself has a round-trip floor of roughly `5.5e-5` versus the CPU float64 reference.
  3. Apple Silicon Metal does not expose `double`/`float64`, so the DS floor cannot be breached without a much larger refactor (e.g., triple-float).
- **Current status after 2026-06-22 optimization:** Per-exponent specialization (`inv_m2` uses `exp(exponent * log(x))`) reduces the representative worst-case error from ~`1.5e-4` to ~`7e-5`, and the full-kernel error vs CPU float64 is ~`5.4e-5` (at the float32 DS floor).
- **2026-06-29 governance:** `strict` calls the CPU float64 `compress_rgb(..., algorithm="jzazbz")` reference through `compress_rgb_backend(..., precision_policy="strict")` and uploads the result back to the backend array type. `fast` and `balanced` keep the resident GPU path, but policy metadata marks it as an exception and forbids an L1-compliance claim. Existing strict parity xfails remain unchanged.
- **Contract requirement:** The resident path remains non-L1. Reaching L1 requires CPU fallback or a future higher-precision kernel design.

---

## 5. Recommended implementation measures

### 5.1 Add compensated accumulation to spectral reductions

In `cmy_to_log_raw` and `cmy_to_log_xyz` Metal kernels, replace the simple float accumulator with Kahan or double-single accumulation. Example:

```metal
float raw_hi = 0.0f;
float raw_lo = 0.0f;
for (uint k = 0; k < K; k++) {
    float y = light * sensitivity[k * 3 + c] - raw_lo;
    float t = raw_hi + y;
    raw_lo = (t - raw_hi) - y;
    raw_hi = t;
}
```

Expected effect: reduce vs-CPU-float64 error from ~1e-5 to ~1e-6 for large K.

### 5.2 Cast CCTF thresholds to float32

All CCTF threshold literals in `src/spektrafilm/gpu/kernels/color.py` (e.g. `0.0031308`, `0.04045`, `0.018`, `0.081`) should be explicitly `np.float32` so GPU and CPU float32 reference paths take the same branch at threshold boundaries.

### 5.3 Keep Gaussian IIR as a documented conditional path

The float32 IIR bias is structurally unavoidable. Do not change the default; instead:

- Document the ~5e-6 max / ~5e-4 RMS bias in this contract.
- Preserve and advertise `_precision="float64"` in `gaussian_filter_large_backend` for callers who need exact parity.

### 5.4 Fix or restrict 2D LUT Mitchell cubic

Options, in order of preference:

1. **Implement double-single Mitchell weight evaluation** inside the Metal kernel.
2. **Split the kernel:** use float64-correct CPU reference for final-output color transforms, keep the GPU kernel only for internal coordinate lookups where 2e-5 is acceptable.
3. **Fall back to CPU reference** unconditionally until the GPU path meets L1.

### 5.5 JzAzBz double-single optimization (closed at the float32 floor)

Completed measures:

- Added second-order Taylor expansion to `ds_signed_pow` in `gamut_compress.py:278-288`.
- Removed the unused `pq_eotf_derivative_jz` helper.
- Added per-exponent specialization: `ds_signed_pow_exp_log` for `inv_m2`, which uses `exp(exponent * log(x))` because Metal's `exp(log)` is closer to numpy/libm than `pow` or `exp2(log2)` for this small exponent.
- Tightened `ds_safe_div` epsilon from `1e-12` to `1e-20`.

Measured result:

- Representative xfail max error: ~`7e-5` (down from ~`1.5e-4`).
- Full-kernel error vs CPU float64: ~`5.4e-5`, matching the faithful float32 DS simulation floor (~`5.5e-5`).
- No measurable performance regression; 2K frame kernel median remains ~0.18 ms.

Remaining gap to `1e-6` is structural: it requires precision beyond float32 double-single on Apple Silicon Metal. The viable next steps are therefore:

1. **Document a precision exception** for `jzazbz` at L1 while keeping the resident GPU path (current approach).
2. **Fall back to CPU float64** in `compress_rgb_jzazbz_chroma_backend` for callers who need L1 parity (loses full-frame residency).
3. **Investigate triple-float or other higher-precision Metal arithmetic** (large effort, significant performance risk).

---

## 6. Testing and CI requirements

6.1 **Every new GPU kernel must include:**
- A CPU float64 reference implementation or a reference to an existing CPU function.
- A unit test asserting `np.allclose(gpu, cpu, atol=1e-6, rtol=0.0)`.
- Boundary tests for NaN, Inf, zero, very large/small values, and non-aligned dimensions.

6.2 **CI precision audit:**

```bash
.venv/bin/python -m pytest tests/test_gpu_*.py -v --tb=short
```

must pass, and each kernel's maximum absolute error should be reported.

6.3 **End-to-end visual audit (recommended):**

Add a tool or test that runs the full pipeline on CPU float64 and MLX float32 with fixed input and computes PSNR, SSIM, and ΔE₀₀. Report:

- Per-stage snapshot differences.
- Final output PSNR / SSIM / ΔE₀₀ percentiles.

---

## 6.4 Executable precision governance

As of 2026-06-29, colour precision policy is executable rather than only
documented:

- `SettingsParams.color_precision_policy` accepts `fast`, `balanced`, and
  `strict`; the default is `balanced`.
- `src/spektrafilm/gpu/precision_policy.py` is the source of truth for
  operation decisions, fallback requirements, non-L1 exceptions, and common
  precision metrics.
- `tools/audit_color_precision.py` can audit `cctf`, `rgb-xyz`, `lut2d`,
  `jzazbz`, and `spectral` subsets on `cpu` or `mlx` with a fixed seed and
  Markdown/JSON output.

Policy semantics:

- `fast`: preserve backend residency and allow documented GPU exceptions.
- `balanced`: recommended default. Avoid silent use of the known non-compliant
  2D Mitchell LUT in the final-quality Hanatos path; keep JzAzBz resident but
  explicitly classify it as a non-L1 exception.
- `strict`: use CPU float64 fallback for 2D Mitchell LUT, JzAzBz gamut
  compression, and spectral reductions when those operations need CPU-reference
  parity. Do not invent a GPU float64 path.

2026-06-29 MLX balanced audit (`seed=20260629`):

| Operation | Status | max_abs | mean_abs | PSNR |
|---|---|---:|---:|---:|
| CCTF | compliant | 5.426e-07 | 1.4355e-07 | 137.55 dB |
| RGB/XYZ | compliant | 3.52456e-07 | 6.72145e-08 | 142.572 dB |
| 2D Mitchell LUT | fallback | 0 | 0 | inf |
| JzAzBz | exception | 9.64753e-05 | 1.65446e-05 | 92.5076 dB |
| Spectral Mallett reduction | conditional | 1.21653e-06 | 1.95971e-07 | 144.101 dB |

See `docs/reports/mlx-float32-color-precision-audit-20260629.md`.

## 7. Exceptions and disclaimers

The following are not covered by the L1 numerical-parity contract:

- **Grain samplers:** GPU and CPU use different RNG streams; only distribution-level statistical equivalence is required.
- **`gpu_precision="float16"`:** The contract automatically degrades to L3.
- **Apple Silicon Metal without `double` support:** `_precision="float64"` for IIR filters will trigger a CPU fallback, which may reduce performance.

---

## 8. Related files

| File | Purpose |
|---|---|
| `src/spektrafilm/gpu/mlx_backend.py` | MLX backend and `cmy_to_log_raw` kernels |
| `src/spektrafilm/gpu/kernels/density.py` | `cmy_to_log_xyz`, density-curve interpolation |
| `src/spektrafilm/gpu/kernels/filters.py` | Gaussian FIR/IIR, FFT convolution |
| `src/spektrafilm/gpu/kernels/lut.py` | 2D/3D LUT interpolation |
| `src/spektrafilm/gpu/kernels/color.py` | CCTF, matrix transforms, highlight boost |
| `src/spektrafilm/gpu/kernels/gamut_compress.py` | Gamut compression, including JzAzBz double-single kernel |
| `src/spektrafilm/gpu/kernels/grain.py` | Stochastic samplers |
| `tests/test_gpu_density.py` | Spectral-chain precision tests |
| `tests/test_gpu_filters.py` | Filter precision tests |
| `tests/test_gpu_lut.py` | LUT precision tests |
| `tests/test_gpu_color_chain.py` | Color-chain precision tests |
| `tests/test_gamut_compression.py` | Gamut-compression precision tests |
| `docs/dev/research-gpu-color-management.md` | Original ZERO precision-loss constraint |
| `docs/halide-mlx-parity-plan-20260531.md` | Halide/MLX parity floor |

---

## 9. Decisions log

| Date | Decision | Rationale |
|---|---|---|
| 2026-06-19 | L1 global standard is `atol=1e-6` | Accepted by maintainers; 2D LUT Mitchell must be fixed |
| 2026-06-19 | Do not introduce `strict_parity` setting | Avoids params_schema and GUI configuration changes |
| 2026-06-19 | JzAzBz short-term strategy: continue optimizing double-single kernel | Rather than falling back to CPU float64 immediately |
| 2026-06-22 | `compiled_elementwise` cache key must include function identity (`id` and `__code__.co_code` hash) | Previously keyed only on `name`, causing different functions with the same name to return the same compiled object |
| 2026-06-22 | `MlxBackend.fmax` must use NaN-ignoring semantics to match NumPy/CPU behaviour | Found via adversarial review; required for `np.where(np.isnan(x), y, np.maximum(x, y))` parity |
| 2026-06-22 | `MlxBackend.nan_to_num` must use dtype-aware replacement limits | `float16` and `float32` need different finite fill values |
| 2026-06-22 | `cmy_to_log_xyz` kernel skips NaN spectral table entries | Prevents NaN propagation from malformed lookup tables |
| 2026-06-22 | CCTF threshold literals must be plain Python `float(np.float32(...))` | `np.float32` scalars inside `mx.compile` closures trigger "Attempting to eval an array during function transformations" |
| 2026-06-22 | Enable `cmy_to_log_raw_pixel_thread_table_cache` as default for K ≤ 256 | Fixes threadgroup cache load loop to use `threads_per_threadgroup.x` so all K entries are loaded when grid has fewer threads than K |
| 2026-06-22 | `light_to_raw` and `rgb_to_raw_mallett2019` reclassified as CONDITIONAL | Float32 spectral `einsum` accumulation does not meet L1 (`1e-6`) for adversarial inputs; documented measured bounds |
| 2026-06-29 | Add `fast` / `balanced` / `strict` precision policy and audit tool | Makes MLX float32 exceptions executable: balanced/strict fall back for 2D Mitchell LUT, strict falls back for JzAzBz and spectral reductions, and fast preserves resident GPU exceptions |
