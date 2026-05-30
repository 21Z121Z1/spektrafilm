# Performance & Memory Risk Review

> Generated 2026-05-28 — Phase 2 Performance Audit
>
> **Scope**: REVIEW-ONLY — no source code modified.

---

## Summary

| Severity | Count | Description |
|----------|-------|-------------|
| P0 | 2 | Critical — causes incorrect results or crashes under load |
| P1 | 7 | High — large measurable impact on typical workloads |
| P2 | 14 | Medium — moderate impact, fixable with targeted changes |
| P3 | 10 | Low — minor impact or edge-case only |

---

## P0 — Critical

### PERF-001: Thread-unsafe global RNG in Numba parallel loops

**File**: `utils/fast_stats.py:49`, `model/grain.py:43`

**Evidence**: `fast_poisson`, `fast_binomial`, and `fast_lognormal` use `np.random.rand()` / `np.random.randn()` inside `@njit(parallel=True)` with `prange`. Numba's parallel mode dispatches threads from a pool; the legacy global RNG is **not** thread-safe. Under concurrent execution, random streams can collide, producing correlated or biased samples. `grain.py:43` compounds this by calling `np.random.seed()` globally, which is a process-wide mutation.

**Estimated impact**: Incorrect grain statistics — biased Poisson/binomial samples, non-reproducible results across runs with the same seed, potential data corruption in stochastic grain simulation.

**Minimal fix**: Replace `np.random.rand()` / `np.random.randn()` with Numba's `np.random.RandomState` or the newer `numba.np.random` parallel-safe generators. For `grain.py`, stop mutating global state; pass a seed to a local `RandomState`.

**Validation**: Run `fast_poisson` in a `ThreadPoolExecutor` with 8 threads on a 1000x1000 array and verify the variance matches the expected Poisson variance (lambda) to within 1%.

---

### PERF-002: `boost_highlights` silently upgrades float32 → float64, breaking in-place semantics

**File**: `utils/numba_boost_highlights.py:77`, `runtime/stages/filming.py:76`

**Evidence**: `boost_highlights` at line 77 does `x = np.asarray(x, dtype=np.float64)`. When the pipeline passes a float32 array with `out=raw` (also float32), the function's internal `x` becomes a float64 copy. The `_boost_curve_kernel` writes float64 to `y` (the float32 `out` buffer), causing truncation. Worse, line 93 `y = out` means the kernel writes to the original float32 buffer, but the float64 `x` copy is never freed.

**Estimated impact**: 576MB unnecessary allocation per frame for 6000x4000x3 images. The float64→float32 truncation in the kernel is numerically harmless but the memory spike is severe.

**Minimal fix**: Either (a) respect the input dtype and compile the kernel for float32, or (b) document that `boost_highlights` always operates in float64 and remove the `out` parameter.

**Validation**: Profile memory usage of `FilmingStage.expose` on a 6000x4000 image; verify peak allocation matches expectation.

---

## P1 — High

### PERF-003: Per-channel `ascontiguousarray` copies in `_apply_per_channel`

**File**: `utils/fast_gaussian_filter.py:257-259`

**Evidence**: For a 3-channel HxWxC image, line 258 does `np.ascontiguousarray(image[:, :, ch])` for each channel. A slice from a contiguous HxWxC array has strides `(W*8, 8)` for float64 — not C-contiguous. Each call copies the entire channel.

**Estimated impact**: 3 extra copies of `H*W*8` bytes each. For 6000x4000 float64: 3 * 192MB = **576MB** of temporary allocations per gaussian filter call. Since gaussian filters are called 5-10 times per pipeline (halation, lens blur, scanner blur, unsharp mask, diffusion), this can be **3-6 GB** of cumulative allocation pressure.

**Minimal fix**: After `image = np.ascontiguousarray(image)` at line 241, extract channels via `image.reshape(-1, 3)[:, ch].reshape(H, W)` which is already contiguous, or use `np.asfortranarray` and operate column-wise.

**Validation**: Benchmark `fast_gaussian_filter(img3d, 1.0)` before/after on 6000x4000x3 image; measure peak RSS.

---

### MEM-001: `_gaussian_filter_2d_large` allocates two full-image temporaries

**File**: `utils/fast_gaussian_filter.py:216-217`

**Evidence**: Lines 216-217 allocate `tmp` and `output` as `np.empty_like(image)`. The horizontal pass writes to `tmp`, then the vertical pass reads `tmp` and writes to `output`. `tmp` is never read again.

**Estimated impact**: 2 * H * W * 8 bytes. For 6000x4000 float64: 384MB. The vertical pass could write in-place to `tmp`, halving the allocation.

**Minimal fix**: Reuse `tmp` as the output buffer: `_iir_vertical(tmp, tmp, ...)` and return `tmp`. Verify the IIR vertical pass reads `tmp[i,j]` before writing to `tmp[i,j]` (it does — the recurrence uses `output[i,j0+k]` as both read and write, which is safe for in-place).

**Validation**: Verify `_iir_vertical` output is bit-identical when writing in-place vs. to a separate buffer.

---

### PERF-004: Diffusion filter PSF recomputed every frame

**File**: `model/diffusion.py:585-592`

**Evidence**: `apply_diffusion_filter_um` calls `diffusion_filter_psf(...)` on every invocation. The PSF depends only on `(family, spatial_scale, pixel_size_um, halo_warmth, overrides)` — all constant across frames in a batch. For cinebloom at strength=2, the PSF can be a 1001x1001x3 float64 array (~24MB) that takes ~10ms to compute.

**Estimated impact**: ~10ms per frame, ~24MB allocation per frame for large filters. In a batch of 100 images, that's 1s wasted and 2.4GB cumulative allocation.

**Minimal fix**: Cache the PSF keyed on `(family, spatial_scale, pixel_size_um, halo_warmth, overrides)` in a module-level LRU or on the `DiffusionFilterParams` object.

**Validation**: Time `apply_diffusion_filter_um` on consecutive calls with identical params; verify second call is >10x faster.

---

### PERF-005: Per-channel FFT convolution in diffusion filter CPU path

**File**: `model/diffusion.py:602-607`

**Evidence**: The CPU path at lines 602-607 loops over channels, calling `fftconvolve` per channel. Each call does a 2D FFT of the padded image and the PSF, multiplies, and inverse FFTs. For 3 channels, that's 6 FFTs + 3 IFFTs instead of 1 batched 3D FFT.

**Estimated impact**: ~2x slower than necessary for the CPU convolution path. For a 1001x1001 PSF on a 6000x4000 image, each `fftconvolve` takes ~200ms, so 3 channels = 600ms vs ~350ms for a batched approach.

**Minimal fix**: Stack channels into a 3D array and use `scipy.signal.fftconvolve` with `axes=(0,1)` to batch across the channel dimension.

**Validation**: Time the diffusion filter before/after on a 3-channel image.

---

### PERF-006: MLX `fft_convolve_same_backend` calls `mx.metal.clear_cache()` after every convolution

**File**: `gpu/kernels/filters.py:634`

**Evidence**: Line 634 calls `mx.metal.clear_cache()` after every FFT convolution. This forces Metal to discard cached shader compilations and buffer allocations. Subsequent convolutions must re-compile and re-allocate.

**Estimated impact**: Metal shader recompilation can take 10-100ms per kernel. If the diffusion filter is applied per-frame, this adds significant overhead.

**Minimal fix**: Remove the `clear_cache()` call. Let the pipeline's `_cleanup_backend_cache` handle cleanup at the end of `process()`.

**Validation**: Profile MLX diffusion filter throughput before/after removing the per-call clear.

---

### PERF-007: `HalideBackend.gaussian_blur_iir` falls back to sequential NumPy per channel

**File**: `gpu/halide_backend.py:455-478`

**Evidence**: Lines 474-478 loop over channels and call `_gaussian_filter_2d_large` (Numba) per channel sequentially. The Halide backend claims `supports_gpu = True` but IIR blur is actually slower than the Numba parallel path because it doesn't use `prange` across channels.

**Estimated impact**: For 3-channel images, this is ~3x slower than the Numba path. IIR blur is the dominant blur for halation (sigma often 10-50px).

**Minimal fix**: Either (a) implement Halide IIR scan, or (b) call the Numba function with `prange` parallelism across channels, or (c) mark the Halide backend as not supporting IIR and fall through to Numba.

**Validation**: Benchmark IIR blur on Halide vs NumpyBackend for a 3-channel 6000x4000 image with sigma=20.

---

### MEM-002: `_compute_gaussian_kernel_fft` allocates 4 full-size arrays per call

**File**: `utils/fft_gaussian_filter.py:87-98`

**Evidence**: Lines 92-98 create `fx`, `fy` (1D), `FX`, `FY` (2D meshgrids), `freq2`, and `kernel_fft` — 4 arrays of size H*W. For a padded 6700x4700 image: 4 * 6700 * 4700 * 8 = ~1GB.

**Estimated impact**: 1GB temporary allocation per FFT gaussian filter call. The kernel FFT depends only on (H, W, sigma) and could be cached.

**Minimal fix**: Cache `kernel_fft` keyed on `(H, W, sigma)` in a module-level dict or LRU cache.

**Validation**: Verify memory usage of `fft_gaussian_filter` before/after on a large image.

---

## P2 — Medium

### PERF-008: `fast_lognormal_from_mean_std` allocates two intermediate arrays

**File**: `utils/fast_stats.py:195-196`

**Evidence**: Lines 195-196 allocate `mu_arr` and `sigma_arr`, then pass them to `fast_lognormal` which allocates `result`. For 6000x4000 float64: 3 * 192MB = 576MB.

**Estimated impact**: 576MB peak allocation. Called from grain micro-structure computation.

**Minimal fix**: Fuse the mu/sigma computation into a single kernel that writes the lognormal result directly, avoiding the intermediate arrays.

**Validation**: Memory profile `add_micro_structure` before/after.

---

### PERF-009: `apply_diffusion_filter_mm` unnecessary `data.copy()` when radius=0

**File**: `model/diffusion.py:122`

**Evidence**: Line 122: `result = ... data.copy()` when `radius <= 0`. The copy is only needed because the FFT path modifies `result` in place. But when `radius <= 0` and `iterations == 0`, the function returns `data.copy()` unchanged.

**Impact**: Unnecessary full-image copy for edge case.

**Minimal fix**: Return `data` directly when `iterations <= 0` or `diffusion_fraction <= 0`.

**Validation**: Verify the function returns unmodified input for zero iterations.

---

### PERF-010: `_warn_if_lut_not_monotonic_3d` creates `np.diff` per line

**File**: `utils/fast_interp_lut.py:343`

**Evidence**: Line 343 calls `np.diff(line)` for every line in the LUT. For a 33^3 LUT: 3 axes * 3 channels * 33^3 = ~324K calls, each allocating a small array.

**Impact**: ~50ms overhead on first LUT preparation. Not per-frame, but adds up if LUTs are rebuilt.

**Minimal fix**: Pre-allocate a scratch buffer for diffs and reuse it across lines.

**Validation**: Time `prepare_lut_pchip_3d` before/after on a 33^3 LUT.

---

### PERF-011: `apply_halation_um` N sequential gaussian passes for bounces

**File**: `model/diffusion.py:80-83`

**Evidence**: Lines 80-83 loop over `N` bounces, each calling `gaussian_filter_backend`. For N=3, that's 3 full-image gaussian filters with increasing sigma. Each creates its own temporary.

**Impact**: For a 6000x4000 image, 3 gaussian filters at sigma 10-50px take ~300-900ms total. Could potentially fuse into a single weighted sum of gaussians applied in the frequency domain.

**Minimal fix**: Apply all bounce gaussians in a single FFT-domain pass: `sum(w_k * G(sigma_k))` in frequency space.

**Validation**: Benchmark halation before/after on a 3-channel image with 3 bounces.

---

### PERF-012: FFT gaussian filter `FFTW_MEASURE` planner effort

**File**: `utils/fft_gaussian_filter.py:106-108`

**Evidence**: Lines 106-108 use `planner_effort='FFTW_MEASURE'` which can take seconds on first call for a new image size. Subsequent calls with the same size reuse the plan.

**Impact**: First call to `fft_gaussian_filter` for a new image size can be 2-10 seconds slower than expected.

**Minimal fix**: Use `FFTW_ESTIMATE` for interactive use, `FFTW_MEASURE` for batch processing. Or pre-warm the FFTW plan at startup.

**Validation**: Time first vs second call to `fft_gaussian_filter` with the same image size.

---

### PERF-013: `HalideBackend` image transpose per LUT application

**File**: `gpu/halide_backend.py:175-176`

**Evidence**: Lines 175-176 transpose image from HxWx3 to 3xHxW and LUT from LxLxLx3 to 3xLxLxL. For a 6000x4000 image, the image transpose copies 576MB.

**Impact**: ~100ms per LUT application for the transpose alone.

**Minimal fix**: Design the Halide pipeline to accept HxWx3 layout directly, or keep the CHW layout through the entire pipeline to avoid repeated transposes.

**Validation**: Benchmark `apply_lut_trilinear_3d` on Halide before/after eliminating the transpose.

---

### PERF-014: `CupyBackend.to_numpy` forces sync on every call

**File**: `gpu/cupy_backend.py:56-59`

**Evidence**: Line 58 calls `self.synchronize()` before `cp.asnumpy`. If `to_numpy` is called multiple times in sequence (e.g., for different intermediate arrays), each call stalls the GPU pipeline.

**Impact**: GPU pipeline stalls can add 1-5ms per sync point.

**Minimal fix**: Remove the sync from `to_numpy` and let the caller manage sync points. The pipeline already syncs at stage boundaries.

**Validation**: Profile GPU utilization during a pipeline run; verify no unnecessary stalls.

---

### PERF-015: `_scene_luminance_y` RGB→XYZ conversion for HDR metadata

**File**: `runtime/pipeline.py:84-89`

**Evidence**: Lines 84-89 call `colour.RGB_to_XYZ(rgb, ...)` which internally allocates the 3x3 matrix, does the multiply, and returns a full XYZ array. Only `xyz[..., 1]` (the Y channel) is used.

**Impact**: ~2x more computation than needed (computing X and Z that are discarded).

**Minimal fix**: Extract just the Y-row of the RGB→XYZ matrix and do a dot product: `Y = rgb @ matrix_y.T`.

**Validation**: Verify `_scene_luminance_y` output is identical before/after.

---

### MEM-003: `copy.deepcopy(params)` in pipeline init

**File**: `runtime/pipeline.py:210`

**Evidence**: Line 210 does `self._params = copy.deepcopy(params)`. If `params` contains numpy arrays (density_curves, channel_density, etc.), `deepcopy` copies all of them. For a typical profile with 1024-point density curves: small. But if params carry large precomputed arrays, this could be significant.

**Impact**: Typically small (~1MB), but can be larger with custom profiles.

**Minimal fix**: Use `copy.copy` for the top-level dataclass and only deepcopy mutable numpy arrays that will be modified.

**Validation**: Profile `SimulationPipeline.__init__` allocation.

---

### MEM-004: `add_micro_structure` allocates full-size `clumping` + two `np.ones_like` temporaries

**File**: `model/grain.py:62-63`

**Evidence**: Lines 62-63 call `fast_lognormal_from_mean_std(np.ones_like(density_cmy_out), np.ones_like(density_cmy_out) * sigma)`. This creates two temporary arrays the same size as the output, plus the `fast_lognormal_from_mean_std` internals create two more.

**Impact**: 4 * H * W * 3 * 8 bytes. For 6000x4000: 2.3GB peak.

**Minimal fix**: Pre-allocate `np.ones` once and scale, or pass `sigma` as a scalar to a specialized kernel.

**Validation**: Memory profile `add_micro_structure` before/after.

---

### PERF-016: `apply_grain_to_density` mutates input array

**File**: `model/grain.py:95`

**Evidence**: Line 95: `density_cmy += density_min`. This modifies the input array in place. The caller (`develop` in emulsion.py) passes `density_cmy` which is the output of `apply_density_correction_dir_couplers`. If the caller expects the input to be preserved, this is a bug.

**Impact**: Silent data corruption if the caller reuses `density_cmy` after calling `apply_grain_to_density`.

**Minimal fix**: Work on a copy: `density_cmy = density_cmy + density_min`.

**Validation**: Verify that `develop()` output is correct when called twice with the same input.

---

### PERF-017: `grain.py` `layer_particle_model` `gamma_beta` path uses slow scipy.stats

**File**: `model/grain.py:32-34`

**Evidence**: Lines 32-34 call `scipy.stats.gamma.rvs` and `scipy.stats.beta.rvs` which generate random variates element-by-element in Python. For a 6000x4000 image, that's 24M Python-level function calls.

**Impact**: ~10-60 seconds per call depending on array size. The `poisson_binomial` path with `use_fast_stats=True` is ~100x faster.

**Minimal fix**: Either (a) deprecate the `gamma_beta` path, or (b) implement a Numba-accelerated version.

**Validation**: Benchmark `layer_particle_model` with both methods on a 6000x4000 image.

---

### PERF-018: Pipeline `_runtime_array` may copy arrays unnecessarily

**File**: `runtime/pipeline.py:650-653`

**Evidence**: Line 653 does `np.asarray(image, dtype=self._runtime_dtype)`. If `image` is already the correct dtype, `np.asarray` returns a view (no copy). But if the dtype differs, it copies. The pipeline calls `_runtime_array` at every stage transition (expose → develop → scan), potentially copying the full image 3-4 times.

**Impact**: For float32 pipeline with float32 intermediates, no copies. For float64 pipeline or mixed dtypes: 3-4 copies of 576MB each.

**Minimal fix**: Add a dtype check: `if image.dtype == self._runtime_dtype: return image`.

**Validation**: Verify no unnecessary copies by logging `_runtime_array` calls with dtype checks.

---

### PERF-019: `_preprocess_input_image` strips alpha with slice copy

**File**: `runtime/pipeline.py:595`

**Evidence**: Line 595: `np.ascontiguousarray(np.asarray(image, dtype=self._runtime_dtype)[:, :, 0:3])`. If image is already 3-channel and contiguous, `[:, :, 0:3]` is a view. But `np.ascontiguousarray` checks contiguity and copies if needed. For RGBA input, the slice forces a copy.

**Impact**: For RGBA input: one extra copy of `H*W*4*4` bytes (float32) → `H*W*3*4` bytes. For 6000x4000: ~288MB copy.

**Minimal fix**: Only call `np.ascontiguousarray` if the slice is not contiguous.

**Validation**: Profile preprocessing allocation for 3-channel vs 4-channel input.

---

## P3 — Low

### PERF-020: `warmup_fast_interp` uses float64, production may use float32

**File**: `utils/fast_interp.py:110-112`

**Evidence**: Lines 110-112 create `float64` dummy arrays for warmup. Numba compiles separate specializations per dtype. If production uses float32, the warmup doesn't precompile the float32 version.

**Impact**: First float32 call incurs JIT compilation (~1-5 seconds).

**Minimal fix**: Warm up with both float32 and float64.

**Validation**: Verify JIT compilation doesn't happen on first production call.

---

### PERF-021: `fft_gaussian_filter` recomputes kernel FFT per channel for 3D images

**File**: `utils/fft_gaussian_filter.py:55-62`

**Evidence**: Lines 55-62 loop over channels, each calling `_fft_gaussian_filter_2d` which recomputes `_compute_gaussian_kernel_fft`. If all channels have the same sigma, the kernel FFT is identical.

**Impact**: 2 redundant kernel FFT computations for 3-channel images with scalar sigma.

**Minimal fix**: Cache or share the kernel FFT when sigma is the same across channels.

**Validation**: Verify output is identical before/after.

---

### PERF-022: `_halo_channel_weights` allocates per call

**File**: `model/diffusion.py:374`

**Evidence**: Line 374 allocates `np.empty((3, n), dtype=np.float64)` per call. Called from `_radial_components` which is called from `diffusion_filter_psf`. Small allocation (3 * 4 = 96 bytes for n=4).

**Impact**: Negligible. Included for completeness.

**Minimal fix**: Pre-allocate in the caller.

---

### MEM-005: `compute_density_spectral` redundant `np.asarray` call

**File**: `model/emulsion.py:23`

**Evidence**: Line 23: `np.asarray(channel_density)` inside `opt_einsum.contract`. If `channel_density` is already an ndarray, this is a no-op. If it's a GPU array, this forces a CPU copy.

**Impact**: Negligible for CPU path. For GPU path, the caller should pass CPU arrays or use the backend-aware version.

**Minimal fix**: Ensure callers pass ndarrays.

---

### PERF-023: `ScanningStage` holds references to backend arrays in closure

**File**: `runtime/stages/scanning.py:152-171`

**Evidence**: Lines 152-171 capture `channel_density_backend`, `base_density_backend`, `scan_illuminant_backend`, `cmfs_backend` in the `cmy_to_log_xyz` closure. These GPU arrays are held for the lifetime of the ScanningStage.

**Impact**: Keeps GPU arrays alive even when not in use. For small arrays (81x3), negligible.

**Minimal fix**: None needed — arrays are small.

---

### PERF-024: `_pipeline_debug` doesn't free intermediates

**File**: `runtime/pipeline.py:659-692`

**Evidence**: The debug pipeline at lines 659-692 doesn't `del` intermediates like the normal pipeline does. If `debug_mode == 'output'` and `output_film_density_cmy` is True, all prior intermediates (log_raw_film, etc.) are kept alive.

**Impact**: Extra memory during debug runs. Not production-relevant.

**Minimal fix**: Add `del` statements matching the normal pipeline.

---

### PERF-025: `_overrides_from_params` builds dict even when all defaults

**File**: `model/diffusion.py:438-451`

**Evidence**: Lines 444-451 build a dict of 6 keys every call, even when all values are 1.0 (the common case). The `any_set` check at line 449 short-circuits to return `None`, but the dict is still allocated.

**Impact**: Negligible (~100ns per call).

**Minimal fix**: Check `getattr` values before building the dict.

---

### MEM-006: `HalideBackend` caches JIT pipelines indefinitely

**File**: `gpu/halide_backend.py:60-73`

**Evidence**: Lines 60-73 declare 11 cached pipeline fields. Each holds Halide Func/Param references. These are cleared by `cleanup()` but accumulate between calls if `cleanup` is not called.

**Impact**: ~1-10MB per cached pipeline. Total ~50MB if all pipelines are cached.

**Minimal fix**: Already handled by `cleanup()` in pipeline's `finally` block.

---

### PERF-026: `tiled_processing` allocates `has_coverage` boolean array

**File**: `gpu/backend.py:173`

**Evidence**: Line 173: `has_coverage = np.zeros((h, w), dtype=bool)` is allocated and checked at line 200. For 6000x4000: ~24MB.

**Impact**: Negligible for correctness; adds one allocation.

**Minimal fix**: Remove the coverage check if tiling logic is trusted.

---

### MEM-007: `_pipeline_print` / `_pipeline_scan_film` hold peak memory at stage boundaries

**File**: `runtime/pipeline.py:637-648`

**Evidence**: The pipeline uses `del` to free intermediates, but `self._runtime_array()` at each transition may create a copy (see PERF-018). At the boundary between `develop` and `expose`, both `log_raw_film` and `cmy_film` may coexist briefly.

**Impact**: Brief peak of 2 full-image arrays at each stage boundary. For float32 6000x4000: ~576MB peak.

**Minimal fix**: Already mitigated by `del` statements.

---

## Appendix: Estimated Memory Budget (6000x4000 float32 image)

| Stage | Peak allocation | Notes |
|-------|----------------|-------|
| Preprocess | ~288 MB | Input copy + auto-exposure |
| Spectral upsampling | ~576 MB | LUT sampling output |
| Exposure + halation | ~864 MB | Diffusion PSF + blur temporaries |
| Development | ~1.7 GB | Grain + micro-structure (worst case) |
| Printing | ~864 MB | Print exposure + blur |
| Scanning | ~576 MB | CMY→RGB + blur + unsharp |
| **Total peak** | **~1.7 GB** | At grain stage |

With PERF-003 fix (per-channel contiguous copies): peak drops to ~1.1 GB.
With PERF-008 fix (fused lognormal kernel): peak drops to ~0.9 GB.
With MEM-004 fix (micro-structure temporaries): peak drops to ~0.7 GB.
