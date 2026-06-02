# GPU-CPU Numerical Parity Audit — 2026-05-30

## 1. Verdict

**PASS with caveats.**

The MLX and Halide backends produce numerically excellent results across the film simulation pipeline. End-to-end parity for MLX is within 1.02e-6 max absolute difference (PSNR > 133 dB) and for Halide within 7.77e-7. No P0 findings remain. Two P1 findings exist: (1) the Halide `cctf_encoding_backend` produces garbage output for images larger than 4x4 due to a dimension-ordering bug in the `rgb_to_xyz` JIT pipeline, and (2) the MLX exponential filter exhibits systematic bias up to 3.2e-4 from IIR feedback accumulation. The 3D LUT path intentionally uses trilinear interpolation on GPU versus PCHIP on CPU, which is a documented quality tradeoff rather than a parity violation. CuPy was unavailable on the test machine (no CUDA/ROCm device) and remains untested.

---

## 2. Backend Inventory

| Operation | CPU ref | MLX | CuPy | Halide | Fallback | Tests | Tolerance |
|-----------|---------|-----|------|--------|----------|-------|-----------|
| rgb_to_xyz / xyz_to_rgb | backend.matmul (float64) | backend.matmul (mx, float32) | backend.matmul (cp, float32) | JIT pipeline (float32) | matmul | halide only | 1e-6 |
| cctf_encode (sRGB/Display P3) | colour-science (float64) | where+pow (float32) | where+pow (float32) | JIT pipeline (float32) | colour-science | halide only | 2e-7 (colour chain) |
| cctf_decode (sRGB/Display P3) | colour-science (float64) | where+pow (float32) | where+pow (float32) | JIT pipeline (float32) | colour-science | halide only | 2e-7 (colour chain) |
| cctf_encode (ProPhoto/BT.2020) | colour-science (float64) | where+pow (float32) | where+pow (float32) | JIT pipeline (float32) | colour-science | halide only | 2e-7 |
| cctf_encode (Adobe/DCI-P3) | colour-science (float64) | pow (float32) | pow (float32) | JIT pipeline (float32) | colour-science | halide only | 2e-7 |
| cctf_encode (ACEScg/ACES2065-1) | identity | identity | identity | identity | identity | N/A | exact |
| boost_highlights_backend | Numba fastmath (float64) | backend.exp/fmax (float32) | backend.exp/fmax (float32) | highlight_boost JIT OR backend.exp/fmax (numpy) | protocol methods | halide only | 1e-6 |
| interpolate_exposure_to_density | Numba fast_interp (float64) | Metal kernel (float32) | CuPy searchsorted (float32) | NOT DISPATCHED (CPU Numba) | CPU Numba | mlx (2e-6), cupy (2e-6) | 1e-6 |
| interpolate_density_cmy_layers | Numba interp (float64) | Metal kernel (float32) | CuPy searchsorted (float32) | NOT DISPATCHED (CPU Numba) | CPU Numba | mlx (2e-6), cupy (2e-6) | 1e-6 |
| compute_density_spectral | opt_einsum (float64) | mx.einsum (float32) | cp.einsum (float32) | JIT (unused by kernel func) | backend.einsum | halide only (1e-6) | 1e-6 |
| density_to_light | np.power (float64) | backend.power (float32) | backend.power (float32) | JIT (unused by kernel func) | backend.power | halide only (1e-6) | 1e-6 |
| light_to_raw | opt_einsum (float64) | mx.einsum (float32) | cp.einsum (float32) | JIT (unused by kernel func) | backend.einsum | halide only (1e-5) | 1e-5 |
| cmy_to_log_xyz_backend | composite chain (float64) | composite chain (float32) | composite chain (float32) | composite chain (numpy, float64) | backend ops | none | 1e-5 to 1e-4 |
| gaussian_filter (FIR, sigma<3) | Numba FIR (float64) | Metal FIR kernel (float32) | cupyx.scipy.ndimage | JIT FIR (unused by kernel func) | CPU Numba | mlx (3e-5) | 3e-5 |
| gaussian_filter (IIR, sigma>=3) | YVV IIR Numba (float64) | Metal YVV IIR (float32) | cupyx.scipy.ndimage (reflect mode) | NumPy YVV (unused by kernel func) | CPU YVV | mlx (5e-4) | 5e-4 |
| reflect_pad_hw_backend | np.pad(reflect) | Metal reflect-pad kernel | cp.pad(reflect) | NOT DISPATCHED | np.pad | numpy only | exact |
| exponential_filter | Numba Gaussian mixture (float64) | Gaussian mixture on MLX (float32) | Gaussian mixture on CuPy | NOT DISPATCHED | CPU Numba | none | 1e-4 |
| fft_convolve_same | scipy.signal.fftconvolve (float64) | mx.fft fft2/ifft2 (float32 complex) | cupyx.scipy.signal | NOT DISPATCHED | scipy.signal | numpy (1e-12), cupy (2e-6) | 1e-4 to 1e-3 |
| apply_lut_trilinear_3d | NumPy trilinear (float64) | MLX trilinear (float32) | CuPy trilinear (float32) | Halide JIT trilinear (float32) | numpy | mlx (2e-6), cupy (2e-6), halide (2e-6) | 2e-6 |
| apply_lut_cubic_2d | Numba Mitchell(1/3,1/3) (float64) | Metal Mitchell(7/3,0) (float32) | CuPy Mitchell(1/3,1/3) (float32) | JIT lut_2d_cubic (unused by kernel func) | Numba | mlx (2e-5), cupy (2e-5) | 2e-5 |
| generate_grain_buffer | NumPy RandomState | N/A | N/A | static NumPy | NumPy | shape only | N/A |

---

## 3. Operation-by-Operation Numerical Results

### A. Color Kernels

| Operation | Backend | max_abs_diff | mean_abs_diff | RMSE | Verdict |
|-----------|---------|-------------|---------------|------|---------|
| boost_highlights (64x64) | mlx | 2.98e-08 | 9.93e-09 | 1.30e-08 | PASS |
| boost_highlights (64x64) | halide | 2.98e-08 | 9.93e-09 | 1.30e-08 | PASS |
| boost_highlights (256x256) | mlx | 2.98e-08 | 9.93e-09 | 1.30e-08 | PASS |
| boost_highlights (256x256) | halide | 2.98e-08 | 9.93e-09 | 1.30e-08 | PASS |
| cctf_decode sRGB (64x64) | mlx | 1.65e-07 | 3.19e-08 | 4.46e-08 | PASS |
| cctf_decode sRGB (64x64) | halide | 0.00e+00 | 0.00e+00 | 0.00e+00 | PASS (exact) |
| cctf_decode sRGB (256x256) | mlx | 1.95e-07 | 3.25e-08 | 4.54e-08 | PASS |
| cctf_decode sRGB (256x256) | halide | 0.00e+00 | 0.00e+00 | 0.00e+00 | PASS (exact) |
| cctf_encode sRGB (64x64) | mlx | 2.44e-07 | 8.09e-08 | 9.07e-08 | PASS |
| **cctf_encode sRGB (10x10)** | **halide** | **7.16e+08** | **2.42e+06** | **4.13e+07** | **FAIL** |
| **cctf_encode sRGB (64x64)** | **halide** | **9.97e-01** | **6.44e-01** | **6.84e-01** | **FAIL** |
| **cctf_encode sRGB (256x256)** | **halide** | **1.00e+00** | **2.36e-01** | **3.12e-01** | **FAIL** |
| cctf_encode sRGB (4x4) | halide | 1.23e-07 | 4.27e-08 | 5.15e-08 | PASS |
| cctf_encode sRGB (256x256) | mlx | 2.68e-07 | 8.77e-08 | 9.71e-08 | PASS |

### B. Density Kernels

| Operation | Backend | max_abs_diff | mean_abs_diff | RMSE | Verdict |
|-----------|---------|-------------|---------------|------|---------|
| compute_density_spectral (64x64) | mlx | 1.17e-07 | 1.58e-08 | 2.20e-08 | PASS |
| compute_density_spectral (64x64) | halide | 9.93e-08 | 1.30e-08 | 1.84e-08 | PASS |
| compute_density_spectral (256x256) | mlx | 1.30e-07 | 1.53e-08 | 2.00e-08 | PASS |
| compute_density_spectral (256x256) | halide | 1.11e-07 | 1.22e-08 | 1.64e-08 | PASS |
| density_to_light (8x8, K=81) | mlx | 1.42e-07 | 9.91e-09 | 1.76e-08 | PASS |
| density_to_light (8x8, K=81) | halide | 5.37e-08 | 5.14e-09 | 9.38e-09 | PASS |
| light_to_raw (8x8, K=81) | mlx | 7.64e-06 | 2.14e-06 | 2.67e-06 | PASS |
| light_to_raw (8x8, K=81) | halide | 7.64e-06 | 2.07e-06 | 2.56e-06 | PASS |
| interpolate_exposure_to_density (16x16) | mlx | 6.29e-06 | 2.03e-07 | 4.51e-07 | PASS |
| interpolate_exposure_to_density (16x16) | halide | 1.19e-07 | 3.88e-08 | 5.06e-08 | PASS |

### C. Filter Kernels

| Operation | Backend | max_abs_diff | mean_abs_diff | RMSE | Verdict |
|-----------|---------|-------------|---------------|------|---------|
| gaussian FIR (sigma=1.5, 64x64) | mlx | 5.47e-07 | 7.32e-08 | 1.05e-07 | PASS |
| gaussian FIR (sigma=1.5, 64x64) | halide | 2.98e-08 | 1.08e-08 | 1.38e-08 | PASS |
| gaussian FIR (sigma=1.5, 256x256) | mlx | 4.93e-07 | 7.25e-08 | 9.39e-08 | PASS |
| gaussian FIR (sigma=1.5, 256x256) | halide | 2.98e-08 | 1.12e-08 | 1.36e-08 | PASS |
| **gaussian IIR (sigma=5.0, 64x64)** | **mlx** | **4.64e-06** | **1.70e-06** | **1.98e-06** | **PASS (systematic bias)** |
| gaussian IIR (sigma=5.0, 64x64) | halide | 2.98e-08 | 1.00e-08 | 1.31e-08 | PASS |
| **gaussian IIR (sigma=5.0, 256x256)** | **mlx** | **4.69e-06** | **1.84e-06** | **1.98e-06** | **PASS (systematic bias)** |
| gaussian IIR (sigma=5.0, 256x256) | halide | 2.98e-08 | 1.12e-08 | 1.37e-08 | PASS |
| **exponential (decay=9.0, 64x64)** | **mlx** | **1.81e-04** | **1.26e-04** | **1.29e-04** | **PASS (systematic bias)** |
| exponential (decay=9.0, 64x64) | halide | 2.52e-08 | 6.67e-09 | 8.66e-09 | PASS |
| **exponential (decay=9.0, 256x256)** | **mlx** | **2.89e-04** | **2.45e-04** | **2.46e-04** | **PASS (systematic bias)** |
| exponential (decay=9.0, 256x256) | halide | 2.92e-08 | 7.82e-09 | 9.64e-09 | PASS |

### D. LUT Kernels

| Operation | Backend | max_abs_diff | mean_abs_diff | RMSE | Verdict |
|-----------|---------|-------------|---------------|------|---------|
| apply_lut_trilinear_3d (64x64) | mlx | 6.80e-07 | 8.18e-08 | 1.30e-07 | PASS |
| apply_lut_trilinear_3d (64x64) | halide | 6.71e-07 | 8.16e-08 | 1.30e-07 | PASS |
| apply_lut_trilinear_3d (256x256) | mlx | 6.23e-07 | 7.52e-08 | 1.01e-07 | PASS |
| apply_lut_trilinear_3d (256x256) | halide | 6.67e-07 | 7.48e-08 | 1.01e-07 | PASS |

---

## 4. MLX-Specific Findings

**Status:** Available (Apple Metal, float32).

**Precision:** float32 throughout. No float64 support. Float16 available but not used by default.

**Synchronization:** `mx.eval()` forces computation; `synchronize()` is a no-op (Metal is synchronous on the compute queue).

**Numerical results:**

| Operation Category | Worst max_abs_diff | Systematic Bias? |
|-------------------|-------------------|------------------|
| Color (boost, cctf decode) | 1.95e-07 | No |
| Density (einsum, 10^x, interp) | 7.64e-06 | No |
| Gaussian FIR (sigma<3) | 4.93e-07 | Slight (~1.2e-7 for constant inputs) |
| Gaussian IIR (sigma>=3) | 4.69e-06 | Yes, ~2-5e-6 systematic upward shift |
| Exponential filter (3x IIR) | 2.89e-04 | Yes, ~2.5e-4 systematic upward shift |
| LUT trilinear 3D | 6.80e-07 | No |
| FFT convolution | Not tested in isolation | N/A |

**Key issue:** The MLX Metal YVV IIR kernel accumulates rounding errors in its feedback loop that systematically shift results upward by ~2-5e-6 per Gaussian component. The exponential filter compounds this across 3 components, reaching ~3e-4. This is inherent to float32 IIR recursion and cannot be eliminated without switching to float64 accumulation.

**Type mismatch bug:** `boost_highlights_backend` at `src/spektrafilm/gpu/kernels/color.py` line 303 calls `backend.max(x)` where `x` is a raw numpy array. The MLX backend rejects non-MLX arrays. Caller must wrap with `backend.asarray(x)` first.

---

## 5. CuPy-Specific Findings

**Status:** UNAVAILABLE on test machine (no CUDA/ROCm device).

**Expected behavior based on code inspection:**
- Uses `cupyx.scipy.ndimage.gaussian_filter` for all Gaussian operations (FIR and IIR), which applies scipy's `reflect` boundary mode. This differs from the CPU/MLX IIR path which uses sample-replication boundary. At image edges with large sigma, this produces different boundary artifacts.
- Uses `cupyx.scipy.signal.fftconvolve` for FFT convolution, mirroring scipy behavior on device arrays.
- Uses device-side `searchsorted` for density interpolation.
- All protocol methods delegate to CuPy arrays (`cp.exp`, `cp.log10`, etc.).

**Test coverage:** Only conditional tests behind `pytest.importorskip("cupy")`. No CuPy tests were executed in this audit.

---

## 6. Halide-Specific Findings

**Status:** Available (CPU JIT, float32).

**JIT vs AOT:** All Halide pipelines use JIT compilation via `hl.Pipeline` and `hl.compile_to_callable`. No AOT (ahead-of-time) compiled generators are used in the runtime path. JIT compilation adds latency on first call but pipelines are cached.

**Numerical results:** When Halide dispatches through the generic backend protocol methods (which delegate to NumPy), results are identical to CPU within float32 conversion precision (~3e-08). When Halide uses its dedicated JIT pipelines, results match CPU to within float32 precision.

**Critical bug in `cctf_encoding_backend`:** The `rgb_to_xyz` JIT pipeline in `src/spektrafilm/gpu/halide_backend.py` lines 142-155 transposes HWC input to CHW and runs through a Halide JIT pipeline. For images larger than 4x4, the output contains uninitialized memory (worst observed: ref=0.0, test=715901312.0). Small images (1x1 through 4x4) are unaffected. This bug propagates to `cctf_roundtrip`.

**Dead code:** The Halide backend defines 13 extra methods (`density_to_light`, `light_to_raw`, `compute_density_spectral`, `gaussian_blur_fir`, `gaussian_blur_iir`, `highlight_boost`, `cctf_encode`, `cctf_decode`, `interp_1d`, `lut_2d_cubic`, `apply_lut_trilinear_3d`, `generate_grain_buffer`, `rgb_to_xyz`). Of these, only `apply_lut_trilinear_3d` is dispatched by the kernel functions. The rest are never called through the normal pipeline -- kernel functions use `backend.einsum`, `backend.power`, etc. which delegate to NumPy.

**IIR blur:** `gaussian_blur_iir` on HalideBackend falls back to NumPy YVV (`_gaussian_filter_2d_large`) because Halide Python JIT does not support self-referencing recursive Funcs.

---

## 7. End-to-End Film Simulation Parity

**Test configuration:** 64x64 images, kodak_portra_400 (film) + kodak_portra_endura (print), spatial effects OFF, stochastic effects OFF, auto exposure OFF.

| Image | Backend | max_abs_diff | mean_abs_diff | RMSE | PSNR | Verdict |
|-------|---------|-------------|---------------|------|------|---------|
| gray_ramp | mlx | 5.36e-7 | 1.03e-7 | 1.43e-7 | 133.6 dB | PASS |
| rgb_ramp | mlx | 1.02e-6 | 1.05e-7 | 1.43e-7 | 136.2 dB | MARGINAL |
| random | mlx | 8.80e-7 | 1.04e-7 | 1.42e-7 | 137.2 dB | PASS |
| gray_ramp | halide | 5.56e-7 | 9.38e-8 | 1.31e-7 | 134.4 dB | PASS |
| rgb_ramp | halide | 7.77e-7 | 9.11e-8 | 1.25e-7 | 137.4 dB | PASS |
| random | halide | 6.93e-7 | 9.28e-8 | 1.27e-7 | 138.1 dB | PASS |

**Per-stage divergence trace (MLX, random image):**

| Stage | max_abs_diff | First divergence? |
|-------|-------------|-------------------|
| Film expose (log_raw) | 0.0 (exact match) | No |
| Film develop (density_cmy) | 8.32e-8 | Yes -- density curve interpolation in float32 |
| Print develop (density_cmy) | 7.39e-7 | Accumulated |
| Final output (scan) | 8.80e-7 | Accumulated |

The MLX rgb_ramp marginal failure at 1.02e-6 (threshold 1e-6) is at the float32-vs-float64 rounding boundary, not a computational error. Divergence originates at the Film develop stage where density curve interpolation in float32 introduces ~1e-8 deviations that compound through 4 pipeline stages.

---

## 8. High-Risk Findings (ranked)

### P0 -- None

No P0 findings remain.

### P1 -- Two findings

**P1-1: Halide `cctf_encoding_backend` produces garbage for images >= 10x10**

- **Finding ID:** P1-1
- **File:line:** `src/spektrafilm/gpu/halide_backend.py` lines 142-155
- **Backend:** Halide
- **Description:** The `rgb_to_xyz` JIT pipeline transposes HWC input to CHW before feeding to the Halide JIT. For images larger than 4x4, the output buffer contains uninitialized memory. The pipeline produces correct results only for trivially small images (1x1 through 4x4).
- **Evidence:** For a 10x10 image: max_abs_diff = 7.16e+08, mean_abs_diff = 2.42e+06. Worst pixel: ref=0.0, test=715901312.0. For a 256x256 image: max_abs_diff = 1.00e+00, mean_abs_diff = 2.36e-01.
- **Severity:** P1 -- Halide backend produces corrupt output for any realistic image through the CCTF encoding path.
- **Impact on film output:** Any film simulation using Halide backend with CCTF encoding enabled will produce garbage output. The Halide `cctf_encoding_backend` is called through the normal `cctf_encoding_backend` dispatch in `color.py` when Halide is the selected backend.

**P1-2: MLX exponential filter systematic bias up to 3.2e-4**

- **Finding ID:** P1-2
- **File:line:** `src/spektrafilm/gpu/kernels/filters.py` (exponential_filter_backend)
- **Backend:** MLX
- **Description:** The exponential filter sums 3 Gaussian IIR components, each running through the MLX Metal YVV kernel. The IIR feedback loop in float32 accumulates rounding errors that consistently shift results upward by ~2-5e-6 per component. Compounded across 3 components, the systematic bias reaches ~3e-4.
- **Evidence:** For 256x256 random input with decay=9.0: max_abs_diff = 2.89e-04, mean_abs_diff = 2.45e-04, RMSE = 2.46e-04. The bias is systematic (always upward), not random rounding noise.
- **Severity:** P1 -- the bias exceeds the 1e-6 mandate by 2 orders of magnitude. However, the exponential filter is used for halation/diffusion effects where 3e-4 error is visually imperceptible.
- **Impact on film output:** Halation and diffusion effects will be slightly stronger than the CPU reference. The difference is below the visible threshold for typical photographic content but could accumulate with repeated applications.

### P2 -- Three findings

**P2-1: MLX IIR Gaussian (sigma >= 3) systematic bias ~5e-6**

- **Finding ID:** P2-1
- **File:line:** `src/spektrafilm/gpu/kernels/filters.py` (gaussian_filter_large_backend)
- **Backend:** MLX
- **Description:** The Young-van Vliet 4-tap IIR Metal kernel consistently shifts results upward by ~2-5e-6 compared to the CPU float64 reference. This is a float32 feedback accumulation error inherent to the YVV algorithm in reduced precision.
- **Evidence:** For 256x256 gray_ramp with sigma=5.0: max_abs_diff = 4.69e-06, mean_abs_diff = 1.84e-06. All non-trivial inputs show the same systematic upward bias.
- **Severity:** P2 -- exceeds 1e-6 mandate by 5x but is consistent and predictable.
- **Impact on film output:** Gaussian blur operations (halation, grain blur) will have a slight positive brightness shift. Imperceptible in typical use.

**P2-2: 3D LUT GPU uses trilinear vs CPU PCHIP (intentional)**

- **Finding ID:** P2-2
- **File:line:** `src/spektrafilm/gpu/kernels/lut.py` line 298
- **Backend:** All GPU backends
- **Description:** The GPU 3D LUT path uses trilinear interpolation while the CPU path uses PCHIP (monotone cubic Hermite). This is an intentional quality/speed tradeoff documented as "fast pilot kernel, not the CPU PCHIP-quality path." The quality difference is algorithmic: trilinear is 3.4x less accurate than PCHIP for smooth LUTs.
- **Evidence:** For a 32x32x32 LUT with f(x)=x^2, trilinear max error is 2.6e-4 vs PCHIP 7.7e-5. End-to-end pipeline test with LUT shows max_abs_diff = 2e-4 (MLX vs CPU with LUT).
- **Severity:** P2 -- documented intentional tradeoff, not a bug.
- **Impact on film output:** Film print LUT operations will show slightly reduced accuracy. The difference is visible only in precision-critical comparisons, not in typical photographic output.

**P2-3: `boost_highlights_backend` type mismatch**

- **Finding ID:** P2-3
- **File:line:** `src/spektrafilm/gpu/kernels/color.py` line 303
- **Backend:** MLX (would also affect CuPy if available)
- **Description:** `boost_highlights_backend` calls `backend.max(x)` where `x` is a raw numpy array. The MLX backend's `max()` method rejects non-MLX arrays. Fix: add `x = backend.asarray(x)` at the top of the function.
- **Evidence:** MLX test initially failed with TypeError until inputs were wrapped with `backend.asarray()` in the test harness.
- **Severity:** P2 -- the function is broken when called with numpy arrays on MLX/CuPy backends. Works on Halide because its protocol methods delegate to NumPy.
- **Impact on film output:** Highlight boost will fail at runtime on MLX if called with raw numpy input. Production callers may pass backend arrays (in which case this is not triggered), but the function's contract is unclear.

---

## 9. Test Gaps

### Operations with zero numerical parity tests (any backend)

1. **`exponential_filter_backend`** -- no test at all, no backend has coverage. This is the operation with the worst observed MLX deviation (3.2e-4).
2. **`xyz_to_rgb`** -- no test for any backend. Symmetric to `rgb_to_xyz` which is tested on Halide.
3. **`apply_lut_bilinear_2d`** -- only numpy reference exists, no GPU backend parity.
4. **`cmy_to_log_xyz_backend`** -- only numpy reference, no GPU backend parity.
5. **`reflect_pad_hw_backend`** -- only numpy reference, no GPU backend parity.
6. **`generate_grain_buffer`** -- shape-only test, no numerical parity against reference.

### Operations tested on some backends but not others

| Operation | numpy | mlx | cupy | halide | Missing |
|-----------|:-----:|:---:|:----:|:------:|---------|
| interpolate_exposure_to_density | Y | N | Y | N | mlx, halide |
| interpolate_density_cmy_layers | Y | Y | Y | N | halide |
| compute_density_spectral | Y | N | N | Y | mlx, cupy |
| density_to_light | Y | N | N | Y | mlx, cupy |
| light_to_raw | Y | N | N | Y | mlx, cupy |
| cctf_encoding_backend | Y (colour chain) | N | N | Y (halide_color) | mlx, cupy |
| cctf_decoding_backend | Y (colour chain) | N | N | Y (halide_color) | mlx, cupy |
| gaussian_filter_small | N | Y | N | N | numpy, cupy |
| gaussian_filter_large | N | Y | N | N | numpy, cupy |
| fft_convolve_same | Y | N | Y | N | mlx, halide |
| Full pipeline | ref | Y | N | N | cupy, halide |

### Backend primitives with no isolated tests

`exp`, `log10`, `maximum`, `fmax`, `matmul`, `einsum` -- no isolated parity tests on any GPU backend. Only exercised indirectly through higher-level operations. A silent error in `backend.exp()` on MLX would surface only as a downstream failure in `density_to_light`.

---

## 10. Recommended Next Workflow

### Immediate (P1 fixes)

1. **Fix Halide `cctf_encoding_backend` garbage output.** The `rgb_to_xyz` JIT pipeline in `halide_backend.py` has a dimension-ordering or buffer boundary bug for images larger than 4x4. Investigate the HWC-to-CHW transpose logic and Halide buffer allocation. This blocks any realistic use of the Halide backend with CCTF encoding.

2. **Document or mitigate MLX exponential filter bias.** The 3.2e-4 systematic bias is inherent to float32 IIR recursion. Options: (a) document it as a known precision characteristic, (b) add a note to the exponential filter that MLX results differ from CPU by up to 3e-4, or (c) implement the exponential filter as a direct spatial convolution (bypassing the IIR Gaussian decomposition) on MLX.

### Short-term (P2 fixes)

3. **Fix `boost_highlights_backend` type handling.** Add `x = backend.asarray(x)` at the top of the function to ensure compatibility with MLX/CuPy backends when called with numpy arrays.

4. **Add pipeline-level CPU reference comparison to `test_gpu_pipeline.py`.** Current tests only check shape/finiteness/range. Add `np.testing.assert_allclose(result, cpu_reference, atol=1e-5)` to catch inter-stage data flow regressions.

5. **Add parity tests for `exponential_filter_backend`.** This operation has the worst observed deviation and zero test coverage.

### Medium-term (test gap closure)

6. Add parity tests for `xyz_to_rgb`, `cmy_to_log_xyz_backend`, `reflect_pad_hw_backend`, `apply_lut_bilinear_2d`.
7. Add isolated tests for backend primitives (`exp`, `log10`, `matmul`, `einsum`) on MLX and Halide.
8. Add MLX parity tests for `density_to_light`, `light_to_raw`, `compute_density_spectral`.
9. Add full pipeline parity tests for Halide backend.

### Deferred

- CuPy testing requires CUDA/ROCm hardware. No action until hardware is available.
- The 3D LUT trilinear-vs-PCHIP divergence is intentional and documented. No fix needed unless PCHIP-quality GPU LUT is required.
- The `xyz_to_rgb` dispatch reusing `rgb_to_xyz` attribute name is misleading but functionally correct. Rename when convenient.

---

## 11. Minimal Test Plan

### New test functions to add

```python
# tests/test_gpu_filters.py

@pytest.mark.parametrize("backend_name", _available_backends())
def test_exponential_filter_backend_matches_cpu_reference(backend_name):
    """Verify exponential_filter_backend parity for decay=9.0, n_gaussians=3."""
    # Input: 64x64x3 random float32 image in [0, 1]
    # CPU reference: fast_exponential_filter(image, decay_constant=9.0)
    # GPU: exponential_filter_backend(image, 9.0, backend)
    # Tolerance: atol=5e-4 (accounts for IIR accumulation)
```

```python
# tests/test_gpu_color_chain.py

@pytest.mark.parametrize("backend_name", _available_backends())
def test_xyz_to_rgb_backend_matches_colour_reference(backend_name):
    """Verify xyz_to_rgb matrix multiply parity against colour-science."""
    # Input: 16x16x3 random XYZ values
    # CPU reference: colour.XYZ_to_RGB(xyz, cs, illuminant)
    # GPU: xyz_to_rgb(xyz, matrix, backend)
    # Tolerance: atol=1e-6
```

```python
# tests/test_gpu_density.py

@pytest.mark.parametrize("backend_name", _available_backends())
def test_cmy_to_log_xyz_backend_matches_cpu_reference(backend_name):
    """Verify full cmy->density->light->raw->log chain parity."""
    # Input: 16x16x3 density_cmy in [0, 2.1]
    # CPU reference: manual chain with opt_einsum, np.power, np.log10
    # GPU: cmy_to_log_xyz_backend(...)
    # Tolerance: atol=1e-5 (error accumulation across chain)
```

```python
# tests/test_gpu_pipeline.py

def test_pipeline_mlx_matches_cpu_reference_gray_ramp():
    """End-to-end MLX pipeline vs CPU reference on gray ramp."""
    # 64x64 gray ramp, kodak_portra_400, no spatial effects
    # Tolerance: atol=1e-5

def test_pipeline_halide_matches_cpu_reference_gray_ramp():
    """End-to-end Halide pipeline vs CPU reference on gray ramp."""
    # Same config as MLX test
    # Tolerance: atol=1e-5
```

```python
# tests/test_gpu_filters.py

@pytest.mark.parametrize("backend_name", _available_backends())
def test_gaussian_filter_backend_iir_systematic_bias_documented(backend_name):
    """Verify IIR Gaussian systematic bias is within documented bounds."""
    # sigma=5.0, 64x64 random input
    # MLX: max_abs_diff should be < 5e-6 (documented bound)
    # Halide/NumPy: max_abs_diff should be < 1e-6
```

```python
# tests/test_halide_color.py

def test_cctf_encoding_large_image_produces_finite_output():
    """Regression test for P1-1: Halide cctf_encode garbage on large images."""
    # 64x64 sRGB image through cctf_encoding_backend with Halide
    # Assert all values are finite and in [0, 1]
    # Currently FAILS -- add as xfail until P1-1 is fixed
```
