# Spektrafilm Halide/Android Port Analysis

**Date:** 2026-05-27
**Scope:** Architecture analysis for porting the spectral film simulation core from Python/NumPy to C++/Halide on Android

---

## 0. Current Implementation Status (2026-05-27)

This repository now contains the first verified Halide/Android port foundation:

- `compute_backend="halide"` is accepted by the backend selector as a strict optional backend. If the `halide` Python package is missing, explicit Halide selection raises `BackendUnavailableError` instead of silently falling back.
- The local development environment verified `halide==21.0.0` on Python 3.13.
- The first host-JIT Halide kernels are present under `src/spektrafilm/gpu/halide_backend.py`: 3D trilinear LUT sampling and the `rgb_to_xyz`/3x3 color matrix path.
- `src/spektrafilm/halide/android.py` provides tested Android ABI to Halide target mappings:
  - `arm64-v8a -> arm-64-android`
  - `armeabi-v7a -> arm-32-android`
  - `x86_64 -> x86-64-android`
  - `x86 -> x86-32-android`
- `render_add_halide_library()` renders a validated CMake `add_halide_library()` snippet for future AOT generator integration.
- Runtime float64 mode rejects explicit `halide`, matching the existing precision policy for accelerator backends.

This is not the full Android app or the full C++ rewrite. The implemented state is a tested Phase 1/Phase 2 foundation: optional host Halide kernels plus Android AOT metadata. The next native step is to create C++ Halide generators and link their AOT outputs into an Android NDK/JNI library.

**Important correction:** Android should default to CPU AOT Halide first. Halide's Vulkan backend exists, but official Vulkan documentation still describes Android platform support as work in progress, so Android Vulkan must remain experimental until validated on target devices.

## 1. Dependency Graph of the Processing Pipeline

```
Input RGB Image
       |
       v
[Preprocessing] ─── auto_exposure (colour.RGB_to_XYZ, NumPy stats)
       |            crop_and_rescale (NumPy)
       v
[FilmingStage.expose]
  ├─ rgb_to_film_raw ─── spectral_upsampling (colour.RGB_to_XYZ, scipy.interpolate, LUT)
  ├─ boost_highlights ─── Numba kernel (exp, element-wise)
  ├─ diffusion_filter_um ─── FFT convolution (scipy.signal.fftconvolve) or Gaussian mixture
  ├─ gaussian_blur_um ─── IIR/FIR Gaussian (Numba or custom Metal/CuPy kernels)
  ├─ halation_um ─── Gaussian + exponential blur passes
  └─ log10
       |
       v
[FilmingStage.develop]
  ├─ interpolate_exposure_to_density ─── 1D linear interp (Numba or Metal kernel)
  ├─ dir_couplers ─── einsum + Gaussian/exponential blur (Numba or GPU kernels)
  └─ grain ─── stochastic: Poisson/Binomial (scipy.stats or Numba), Gaussian blur
       |
       v
[PrintingStage.expose]
  ├─ compute_density_spectral ─── einsum (channel_density @ density_cmy)
  ├─ density_to_light ─── 10^(-density) * illuminant
  ├─ light_to_raw ─── einsum (light @ sensitivity)
  ├─ diffusion_filter_um ─── (same as above)
  └─ log10
       |
       v
[PrintingStage.develop]
  └─ interpolate_exposure_to_density ─── (same as above)
       |
       v
[ScanningStage.scan]
  ├─ cmy_to_log_xyz ─── density_spectral → light → XYZ (einsum chain)
  ├─ black_white_correction ─── NumPy ops
  ├─ glare ─── stochastic: lognormal (scipy.stats or Numba), Gaussian blur
  ├─ xyz_to_rgb ─── 3x3 matrix multiply
  ├─ gaussian_blur + unsharp_mask
  └─ cctf_encoding ─── sRGB/ProPhoto/BT.2020 transfer functions
       |
       v
Output RGB Image
```

---

## 2. Module-by-Module Portability Assessment

### 2.1 Core Pipeline (`runtime/`)

| Module | Portability | Notes |
|--------|------------|-------|
| `pipeline.py` | **High** | Orchestration only. All heavy compute delegated to stages. Thin wrapper that can become C++ entry point. |
| `process.py` | **High** | Thin `Simulator` wrapper. The `Simulator` class is just a convenience layer around `SimulationPipeline`. |
| `params_schema.py` | **High** | Pure dataclasses. Can be directly mapped to C++ structs or protobuf. |
| `params_builder.py` | **Medium** | Profile-specific parameter adjustment. Pure Python logic, no heavy compute. Straightforward C++ translation. |
| `api.py` | **High** | Re-exports only. |

### 2.2 Pipeline Stages (`runtime/stages/`)

| Module | Portability | Notes |
|--------|------------|-------|
| `filming.py` | **Medium** | Calls into colour-science (RGB_to_XYZ, colour spaces), spectral upsampling, and all spatial filters. The stage orchestration logic is straightforward C++; the colour-science calls need custom replacements. |
| `printing.py` | **High** | Pure compute: density spectral math, 10^x, einsum, diffusion filter. All operations are already backend-portable via ArrayBackend. |
| `scanning.py` | **Medium** | Colour-science dependency for XYZ-to-RGB matrix computation (init-time only). Runtime path is pure compute. |

### 2.3 Film/Print Models (`model/`)

| Module | Portability | Notes |
|--------|------------|-------|
| `emulsion.py` | **High** | Core compute: einsum for density spectral, interpolation for development. Already has GPU backend paths. |
| `diffusion.py` | **High** | Gaussian/exponential filters, FFT convolution. All operations have GPU backend equivalents. The diffusion filter PSF construction is CPU-only init-time math. |
| `grain.py` | **Medium** | Stochastic (Poisson/Binomial random variates). Uses scipy.stats or custom Numba implementations. The grain model is the hardest to port due to RNG requirements. |
| `couplers.py` | **High** | einsum + Gaussian blur. Fully backend-portable. |
| `glare.py` | **Medium** | Stochastic (lognormal RNG) + Gaussian blur. |
| `illuminants.py` | **High** | Precomputed spectral distributions loaded from data files. Blackbody spectrum is simple math. |
| `color_filters.py` | **High** | Dichroic filter application is element-wise multiply. Uses scipy.special.erf at init time for filter shape generation. |
| `density_curves.py` | **High** | 1D linear interpolation. Already has Numba and GPU backend paths. |
| `parametric.py` | **High** | Parametric curve fitting — init-time only, not in the hot path. |

### 2.4 GPU Kernels (`gpu/kernels/`)

| Module | Portability | Notes |
|--------|------------|-------|
| `color.py` | **High** | Matrix multiply, CCTF encoding/decoding (piecewise math), highlight boost. All are element-wise or matmul — ideal for Halide. |
| `density.py` | **High** | 1D interpolation, einsum, 10^x. All backend-portable. Already has MLX Metal kernels. |
| `filters.py` | **High** | Gaussian FIR/IIR, exponential filter, FFT convolution, reflect padding. Already has MLX Metal and CuPy implementations. |
| `lut.py` | **High** | 2D/3D LUT interpolation (Mitchell-Netravali cubic, trilinear, bilinear). Already has MLX Metal and CuPy implementations. |

### 2.5 Utilities (`utils/`)

| Module | Portability | Notes |
|--------|------------|-------|
| `spectral_upsampling.py` | **Medium** | Core math is portable (LUT lookup, polynomial eval). But init-time uses `colour.RGB_to_XYZ`, `colour.RGB_COLOURSPACES`, `scipy.interpolate.RegularGridInterpolator`, and `scipy.special.erf`. |
| `fast_gaussian_filter.py` | **High** | Numba JIT kernels for FIR/IIR Gaussian. The algorithms (Young-van Vliet IIR, separable FIR) are well-known and directly expressible in Halide. |
| `fast_interp.py` | **High** | Numba 1D linear interpolation. Trivial in Halide. |
| `fast_interp_lut.py` | **High** | Numba 2D Mitchell-Netravali cubic LUT. Already ported to Metal/CuPy. |
| `fast_stats.py` | **Medium** | Numba RNG (Poisson, Binomial, Lognormal). Needs native RNG replacement. |
| `numba_boost_hightlights.py` | **High** | Numba element-wise kernel. Already ported to backend-agnostic version in `gpu/kernels/color.py`. |
| `autoexposure.py` | **Medium** | Uses `colour.RGB_to_XYZ` for luminance. Stats (percentile, weighted average) are NumPy — portable to Halide reductions. |
| `conversions.py` | **Medium** | `density_to_light` is trivial (10^x). `rgb_to_raw_aces_idt` uses colour-science. |
| `crop_resize.py` | **High** | NumPy array slicing/scaling. |
| `hdr_photo.py` | **Medium** | HDR tone-curve fitting — uses scipy/numpy math. |
| `lut.py` | **High** | LUT computation orchestration. |
| `io.py` | **Low** | File I/O (CSV, JSON). Not needed in the compute core. |
| `raw_file_processor.py` | **Low** | Uses rawpy (LibRaw bindings). Needs native RAW decoder on Android. |
| `plotting.py` | **None** | matplotlib — GUI only, skip. |
| `preview.py` | **High** | Simple resize. |
| `timings.py` | **High** | perf_counter wrappers. |
| `measure.py` | **Low** | GUI measurement tools. |

### 2.6 Profiles (`profiles/`)

| Module | Portability | Notes |
|--------|------------|-------|
| `io.py` | **Medium** | JSON loading via `importlib.resources`. On Android, profiles would be assets loaded via NDK file I/O or bundled as binary data. |

### 2.7 Color Management (`color_management.py`)

| Module | Portability | Notes |
|--------|------------|-------|
| `color_management.py` | **Medium** | Uses `colour.RGB_COLOURSPACES` for validation. The actual runtime logic (encoding presets, workflow selection) is pure Python data mapping. |

### 2.8 Configuration (`config.py`)

| Module | Portability | Notes |
|--------|------------|-------|
| `config.py` | **High** | Constants: spectral shape (380-780nm, 5nm steps = 81 wavelengths), CIE CMFs, LMS fundamentals. All precomputed NumPy arrays that become static C++ data. |

---

## 3. Core Compute Kernel Inventory

These are the hot-path operations that Halide would replace:

### 3.1 Spectral Operations (per-pixel, per-wavelength)

| Kernel | Operation | Current Implementation | Halide Strategy |
|--------|-----------|----------------------|-----------------|
| `compute_density_spectral` | `einsum('ijk,lk->ijl', density_cmy, channel_density)` | MatMul over wavelength | Halide reduction over K dimension |
| `density_to_light` | `10^(-density) * illuminant` | Element-wise | Halide element-wise + fast exp |
| `light_to_raw` | `einsum('ijk,kl->ijl', light, sensitivity)` | MatMul over wavelength | Halide reduction over K dimension |
| `cmy_to_log_xyz` | Chain of above + log10 | Composite | Fused Halide pipeline |

### 3.2 Interpolation

| Kernel | Operation | Current Implementation | Halide Strategy |
|--------|-----------|----------------------|-----------------|
| `interpolate_exposure_to_density` | 1D linear interp per channel | Numba JIT / Metal kernel | Halide with `clamp` + linear blend |
| `interp_density_cmy_layers` | 1D interp across layers | Numba JIT / Metal kernel | Same as above, extra layer dimension |
| `apply_lut_cubic_2d` | Mitchell-Netravali 2D LUT | Numba / Metal / CuPy | Halide with precomputed weight LUT |
| `apply_lut_trilinear_3d` | Trilinear 3D LUT | MLX / CuPy | Halide trilinear |

### 3.3 Spatial Filters

| Kernel | Operation | Current Implementation | Halide Strategy |
|--------|-----------|----------------------|-----------------|
| Gaussian FIR (small sigma) | Separable 2D convolution | Numba / Metal kernel | Halide `convolve` or separable `Func` |
| Gaussian IIR (large sigma) | Young-van Vliet 4-tap IIR | Numba / Metal kernel | Halide IIR scan |
| Exponential filter | Gaussian mixture approx | Numba / Metal kernel | Multiple Halide Gaussian passes |
| FFT convolution | 2D FFT for diffusion PSF | scipy.fft / Metal FFT | Halide FFT or spatial-domain convolution |
| Reflect padding | Boundary handling | Numba / Metal kernel | Halide `BoundaryConditions::mirror_interior` |
| Unsharp mask | blur + subtract + scale | Composite | Fused Halide pipeline |

### 3.4 Color Transforms

| Kernel | Operation | Current Implementation | Halide Strategy |
|--------|-----------|----------------------|-----------------|
| `rgb_to_xyz` / `xyz_to_rgb` | 3x3 matmul | backend.matmul | Halide reduction (3 elements) |
| CCTF encoding/decoding | Piecewise power functions | Backend element-wise | Halide `select` chains |
| `boost_highlights` | Piecewise exp curve | Numba / Backend | Halide `select` + `exp` |

### 3.5 Stochastic Operations

| Kernel | Operation | Current Implementation | Halide Strategy |
|--------|-----------|----------------------|-----------------|
| Grain (Poisson + Binomial) | Per-pixel random deviates | Numba / scipy.stats | **Not expressible in Halide.** Needs separate RNG pass. |
| Glare (Lognormal) | Per-pixel random deviates | Numba / scipy.stats | Same — needs separate RNG pass. |

---

## 4. External Library Replacement Map

### 4.1 colour-science (CRITICAL)

**Used for:**
- `colour.RGB_to_XYZ` / `colour.XYZ_to_RGB` — color space conversion matrices
- `colour.RGB_COLOURSPACES` — colorspace definitions (whitepoints, matrices, transfer functions)
- `colour.adaptation.matrix_chromatic_adaptation_VonKries` — chromatic adaptation (CAT02)
- `colour.SDS_ILLUMINANTS` / `colour.SDS_LIGHT_SOURCES` — standard illuminant spectral data
- `colour.MSDS_CMFS` — CIE color matching functions
- `colour.recovery.MSDS_BASIS_FUNCTIONS_sRGB_MALLETT2019` — spectral upsampling basis
- `colour.colorimetry.blackbody_spectral_radiance` — Planck's law
- `colour.matrix_idt` — ACES IDT matrix computation
- `colour.SpectralDistribution` — spectral data container with alignment

**Replacement strategy:**
- **Matrices (RGB_to_XYZ, CAT02, etc.):** Precompute at init time, store as static 3x3 float arrays. The code already does this via `precompute_rgb_to_xyz_matrix()` etc.
- **Transfer functions (CCTF):** Already implemented as backend-portable piecewise functions in `gpu/kernels/color.py`. Direct C++ translation.
- **Standard illuminants/CMFs:** Bundle as static data arrays (81 floats each). Already stored as NumPy arrays in `config.py`.
- **Spectral upsampling basis (Mallett2019):** Bundle the basis functions as static data.
- **Chromatic adaptation:** Precompute CAT02 matrix at init time. Already done in the hot path.
- **Blackbody spectrum:** Simple Planck formula — trivial C++ implementation.

**Effort:** Medium. Most colour-science usage is init-time matrix extraction that's already been precomputed for the GPU paths.

### 4.2 scipy

**Used for:**
- `scipy.interpolate.RegularGridInterpolator` — spectral upsampling coefficient lookup (init-time)
- `scipy.ndimage.gaussian_filter` — replaced by custom Numba/Metal/CuPy implementations
- `scipy.ndimage.fourier_gaussian` — FFT-based Gaussian (init-time diffusion filter shape)
- `scipy.signal.fftconvolve` — FFT convolution for diffusion filters
- `scipy.special.erf` — error function for filter shapes and bandpass models
- `scipy.stats.gamma/beta/binom/poisson` — grain RNG (replaced by Numba `fast_stats`)
- `scipy.fft.next_fast_len` — FFT padding optimization

**Replacement strategy:**
- **RegularGridInterpolator:** One-time LUT generation. Port the cubic interpolation to C++ or precompute offline.
- **gaussian_filter:** Already replaced by custom implementations. Halide equivalents exist.
- **fftconvolve:** For Android, either use Halide's FFT generator or a native FFT library (FFTW/Ne10/Vulkan FFT).
- **erf:** Standard math library function (`std::erf` in C++).
- **stats RNG:** Replace with C++ `<random>` or a fast PRNG library. The Numba `fast_stats` implementations show the algorithms (Knuth Poisson, normal approximation for binomial).
- **next_fast_len:** Trivial algorithm.

**Effort:** Low-Medium. Most scipy usage is already bypassed by custom implementations.

### 4.3 NumPy

**Used for:** Everything. Every array operation.

**Replacement strategy:** Halide replaces the compute graph. Array storage becomes Halide buffers or raw float arrays. The `ArrayBackend` protocol already abstracts this — the Halide backend would implement the same interface.

**Effort:** This IS the port. The ArrayBackend protocol is the abstraction layer.

### 4.4 Numba

**Used for:**
- `fast_gaussian_filter.py` — FIR/IIR Gaussian kernels
- `fast_interp.py` — 1D linear interpolation
- `fast_interp_lut.py` — 2D Mitchell-Netravali cubic LUT
- `fast_stats.py` — RNG (Poisson, Binomial, Lognormal)
- `numba_boost_hightlights.py` — highlight boost curve

**Replacement strategy:** These are the exact kernels Halide would replace. The Numba code serves as a reference implementation. The Metal/CuPy kernels in `gpu/kernels/` are the GPU reference implementations.

**Effort:** Low — these are already ported to Metal/CuPy. Halide is a cleaner target.

### 4.5 opt-einsum

**Used for:** `contract('ijk,lk->ijl', ...)` — tensor contractions over spectral dimensions.

**Replacement strategy:** These are all simple matrix multiplications over the wavelength dimension (K=81). In Halide, these become reduction over a small dimension. In C++, they're just nested loops or BLAS calls.

**Effort:** Low.

### 4.6 Other Dependencies (Not Needed for Core)

| Dependency | Usage | Android Replacement |
|-----------|-------|-------------------|
| `matplotlib` | Plotting/debug | Skip entirely |
| `napari` | 3D viewer | Skip entirely |
| `qtpy` / `PySide6` | GUI framework | Kotlin/Jetpack Compose |
| `Pillow` | Image I/O | Android Bitmap API or stb_image |
| `OpenImageIO` | EXR/HDR I/O | OpenEXR native library |
| `rawpy` | RAW file loading | LibRaw (already native C++) |
| `exiv2` | EXIF metadata | Android ExifInterface or libexiv2 |
| `lensfunpy` | Lens correction | lensfun (native C library) |
| `PyYAML` | Config loading | Skip or use native JSON |
| `pyconify` | SVG icons | Skip (GUI only) |
| `lmfit` | Curve fitting | Skip or port specific fits |
| `scikit-image` | Image utilities | Skip (not used in hot path) |

---

## 5. Proposed Android Architecture

### 5.1 Layer Diagram

```
┌─────────────────────────────────────────────────┐
│                  Kotlin UI Layer                 │
│  Jetpack Compose + CameraX + MediaStore         │
│  - Image picker / camera capture                │
│  - Parameter adjustment sliders                 │
│  - Preview (real-time via JNI)                  │
│  - Profile selection                            │
│  - Export (JPEG/PNG/EXR)                        │
├─────────────────────────────────────────────────┤
│                  JNI Bridge                      │
│  - SpektrafilmEngine (C++ class)                │
│  - Parameter marshalling (flat structs)          │
│  - Image buffer passing (direct ByteBuffer)     │
├─────────────────────────────────────────────────┤
│              C++ Runtime Core                    │
│  - SimulationPipeline (C++ port)                │
│  - RuntimeParams (C++ structs)                  │
│  - Profile loading (JSON/binary)                │
│  - Service orchestration                        │
├─────────────────────────────────────────────────┤
│            Halide Compute Layer                  │
│  - Spectral operations (density, light, raw)    │
│  - Interpolation kernels                        │
│  - Spatial filters (Gaussian, exponential)      │
│  - Color transforms (matmul, CCTF)              │
│  - LUT sampling (2D cubic, 3D trilinear)        │
│  - Highlight boost                              │
├─────────────────────────────────────────────────┤
│          Supporting Native Libraries             │
│  - FFT (FFTW / Ne10 / custom)                   │
│  - RNG (for grain/glare stochastic effects)     │
│  - JSON parsing (nlohmann/json or rapidjson)    │
│  - Image I/O (stb_image, OpenEXR, LibRaw)       │
│  - Colour science data (static arrays)          │
└─────────────────────────────────────────────────┘
```

### 5.2 Halide Integration Strategy

**Option A: Halide as a Library (Recommended)**
- Write Halide generators for each kernel family
- Ahead-of-time compile generators for ARM (arm64-v8a)
- Link compiled `.a` files into the C++ runtime
- Benefits: No runtime JIT, predictable performance, smaller binary
- Halide's autoscheduler can optimize for mobile GPU tile sizes

**Option B: Halide JIT at Runtime**
- Use Halide's JIT compiler on-device
- Benefits: Can adapt to specific device capabilities
- Drawbacks: Larger binary, runtime compilation latency, more complex

**Recommendation:** Option A. The kernel shapes are known at compile time. The existing Metal/CuPy kernels demonstrate that each operation has a fixed algorithmic structure.

### 5.3 Data Pipeline

```
Profile JSON files ──> C++ Profile loader ──> Static arrays
                                                │
Spectral data (CMFs, illuminants, LUTs) ───────>│
                                                │
                                                v
                                    Halide::Runtime::Buffer<float>
                                    (preallocated, reused across frames)
```

### 5.4 Memory Management

The existing pipeline already has a tiling strategy for GPU memory (`_process_with_gpu_tiles`). This maps directly to Android:
- Allocate a fixed-size Halide buffer pool
- Tile large images to stay within GPU memory limits
- The `SpectralLUTService` caching pattern translates to persistent native buffers

---

## 6. Phased Migration Plan

### Phase 1: Extract Compute Core (2-3 months)

**Goal:** Create a clean C++ compute library with no Python dependencies.

1. **Define C++ parameter structs** — Map `params_schema.py` dataclasses to C++ POD structs with JSON deserialization
2. **Port profile loading** — JSON parser for profile files, static array storage for spectral data
3. **Port the ArrayBackend interface** — Abstract base class with NumPy-equivalent operations
4. **Port color science init** — Precompute all matrices (RGB_to_XYZ, CAT02, CCTF coefficients) as static data
5. **Port spectral operations** — `compute_density_spectral`, `density_to_light`, `light_to_raw` as C++ functions
6. **Port interpolation** — 1D linear interp, 2D cubic LUT, 3D trilinear LUT
7. **Port spatial filters** — Gaussian FIR/IIR (Young-van Vliet), exponential filter, reflect padding
8. **Port color transforms** — 3x3 matmul, CCTF encoding/decoding, highlight boost
9. **Port stage orchestration** — FilmingStage, PrintingStage, ScanningStage as C++ classes
10. **Port the pipeline** — SimulationPipeline as C++ class
11. **Validation** — Compare C++ output against Python reference for all test cases

**Deliverable:** Standalone C++ library that processes images identically to the Python version.

### Phase 2: Halide Rewrite (2-3 months)

**Goal:** Replace performance-critical C++ loops with Halide pipelines.

1. **Set up Halide build system** — CMake integration, AOT compilation for arm64-v8a
2. **Port Gaussian filters** — Halide separable FIR + IIR (Young-van Vliet)
3. **Port spectral einsum** — Halide reduction pipelines for density/light/raw
4. **Port interpolation** — Halide 1D/2D/3D interpolation with boundary handling
5. **Port color transforms** — Halide matmul + CCTF chains
6. **Port diffusion filter** — Either Halide FFT or spatial-domain convolution
7. **Port LUT sampling** — Halide 2D Mitchell-Netravali + 3D trilinear
8. **Optimize with autoscheduler** — Use Halide's autoscheduler for ARM targets
9. **Handle stochastic effects** — Grain and glare need a pre-generated random buffer approach:
   - Generate random deviates in a separate pass (C++ RNG -> Halide buffer)
   - Feed the random buffer into the Halide grain/glare pipeline
10. **Validation** — Bit-exact comparison against Phase 1 C++ output

**Deliverable:** Halide-accelerated compute core with ARM-optimized kernels.

### Phase 3: Android Integration (1-2 months)

**Goal:** Ship as an Android library with Kotlin UI.

1. **JNI bridge** — Expose `SpektrafilmEngine` class to Kotlin
2. **Kotlin UI** — Jetpack Compose interface for parameter adjustment
3. **Image I/O** — CameraX integration, MediaStore for import/export
4. **Profile management** — Bundle profiles as Android assets
5. **Preview mode** — Real-time preview using the existing preview resize logic
6. **Export** — JPEG/PNG via Android APIs, EXR via OpenEXR native
7. **Performance tuning** — Profile on target devices, adjust tile sizes
8. **Testing** — End-to-end comparison against desktop Python output

**Deliverable:** Android app that runs the full film simulation pipeline.

---

## 7. Risk Assessment and Mitigation

### 7.1 High Risk: Grain Model Stochasticity

**Problem:** The grain model uses per-pixel random deviates (Poisson, Binomial, Lognormal). Halide is a deterministic dataflow language — it cannot express random number generation.

**Mitigation:**
- Generate random deviates in a pre-pass using C++ `<random>` or a fast PRNG (e.g., xoroshiro128+)
- Store results in a Halide `Buffer<int64>` / `Buffer<float>`
- Feed the random buffer into the Halide grain pipeline as an input
- The existing `fast_stats.py` Numba implementations provide reference algorithms
- For deterministic results across devices, use a seeded PRNG

**Impact:** Grain will be a two-pass operation (RNG pass + Halide compute pass). This adds memory traffic but keeps the Halide kernels pure.

### 7.2 High Risk: colour-science Dependency Depth

**Problem:** `colour-science` is a large library with deep dependency chains. Some operations (e.g., `colour.matrix_idt`, `colour.recovery`) involve complex matrix algebra.

**Mitigation:**
- All colour-science usage in the hot path has already been precomputed for GPU backends
- The `gpu/kernels/color.py` module demonstrates that init-time matrix extraction covers all runtime needs
- Spectral data (CMFs, illuminants, basis functions) are static arrays that can be bundled as binary data
- The Mallett2019 basis functions are the only non-trivial colour-science dependency — they're loaded once at startup

**Impact:** Low. The codebase has already been refactored to minimize colour-science calls in the hot path.

### 7.3 Medium Risk: FFT for Diffusion Filters

**Problem:** The diffusion filter uses `scipy.signal.fftconvolve` for large PSF kernels. Halide doesn't have a built-in FFT.

**Mitigation:**
- For small kernels (< 100px radius), use spatial-domain Halide convolution
- For large kernels, integrate a native FFT library (FFTW, Ne10, or VkFFT for Vulkan compute)
- The Metal backend already uses `mx.fft.fft2` — the same pattern applies
- Alternatively, the diffusion filter PSF can be decomposed into Gaussian sub-components (already done in the model), each of which is a separable convolution

**Impact:** Medium. The existing decomposition into Gaussian sub-components may eliminate the need for FFT entirely.

### 7.4 Medium Risk: Numerical Precision Parity

**Problem:** The project requires "numerically identical" GPU output. Halide on ARM may use different float32 implementations than x86 NumPy.

**Mitigation:**
- The CLAUDE.md constraint targets float32 epsilon (`atol=1e-6`)
- ARM NEON float32 should meet this tolerance
- Validate against the existing test suite's `np.allclose` assertions
- Use the existing `gpu_validate` flag infrastructure for cross-platform comparison

**Impact:** Low. The tolerance is already defined and ARM float32 is IEEE 754 compliant.

### 7.5 Medium Risk: Profile Data Size

**Problem:** Film profiles contain spectral data (81 wavelengths x 3 channels x multiple arrays). With 100+ profiles, this is significant memory.

**Mitigation:**
- Profiles are loaded on-demand (one film + one print at a time)
- The `SpectralLUTService` caching pattern means only a few LUTs are resident
- Spectral data arrays are small (81 x 3 = 243 floats per array)
- Total profile data per active pipeline: ~50KB

**Impact:** Low.

### 7.6 Low Risk: Raw File Support

**Problem:** `rawpy` (LibRaw) is used for RAW camera files. This is a native C++ library.

**Mitigation:**
- LibRaw is already available for Android (used by many camera apps)
- The RAW processing is a preprocessing step, not part of the simulation pipeline
- Can be integrated as a separate native module

**Impact:** Low.

### 7.7 Low Risk: Test Coverage for Parity

**Problem:** The existing test suite validates GPU/CPU parity for specific operations, but may not cover all edge cases for a full platform port.

**Mitigation:**
- The test suite includes: `test_gpu_pipeline.py`, `test_gpu_color_chain.py`, `test_gpu_density.py`, `test_gpu_filters.py`, `test_gpu_lut.py`, `test_gpu_highlight_boost.py`, `test_gpu_backend.py`
- These tests assert `np.allclose(gpu_result, cpu_result, atol=1e-6)`
- Extend these tests to compare Halide output against the NumPy reference
- The `test_pipeline_smoke.py` and `test_regression_baselines.py` provide end-to-end validation

**Impact:** Low. Good test infrastructure already exists.

---

## 8. Summary of Portability by Operation Class

| Operation Class | Count | Portability | Halide Fit |
|----------------|-------|-------------|------------|
| Element-wise math (exp, log, pow, select) | ~15 | **Excellent** | Native Halide |
| Matrix multiply (3x3, einsum) | ~8 | **Excellent** | Halide reduction |
| 1D interpolation | ~4 | **Excellent** | Halide with clamp |
| 2D/3D LUT sampling | ~3 | **Excellent** | Halide with lookup |
| Gaussian blur (FIR) | ~5 | **Excellent** | Halide convolve |
| Gaussian blur (IIR) | ~3 | **Good** | Halide scan |
| Exponential filter | ~3 | **Good** | Multiple Gaussian passes |
| FFT convolution | ~2 | **Medium** | External FFT or spatial decomposition |
| Stochastic (RNG) | ~3 | **Poor** | Pre-pass C++ RNG |
| Colour-science init | ~10 | **N/A** | Precomputed static data |
| File I/O | ~5 | **N/A** | Native Android APIs |
| GUI | 24 files | **N/A** | Kotlin/Jetpack Compose |

**Bottom line:** ~85% of the compute-heavy operations are directly expressible in Halide. The remaining 15% (FFT, RNG) can be handled with hybrid approaches. The codebase's existing `ArrayBackend` abstraction and the GPU kernel layer (`gpu/kernels/`) provide a clear blueprint for the port.
