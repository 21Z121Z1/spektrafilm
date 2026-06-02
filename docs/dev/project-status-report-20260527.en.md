> This is an English translation of the Chinese original. For the authoritative version, see the Chinese original.

> **STATUS: ARCHIVED** (2026-05-27). Version now 0.3.2. Test count grown to 814+.

# Spektrafilm Project Status Report

**Date:** May 27, 2026
**Version:** v0.3.1
**Branch:** develop
**Author:** Claude Code Automated Analysis

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Code Structure Analysis](#2-code-structure-analysis)
3. [Test Status](#3-test-status)
4. [Git History and Development Progress](#4-git-history-and-development-progress)
5. [Research Documentation Summary](#5-research-documentation-summary)
6. [Code Quality Assessment](#6-code-quality-assessment)
7. [GPU Acceleration Status and Precision Guarantees](#7-gpu-acceleration-status-and-precision-guarantees)
8. [Halide/Android Port Feasibility Assessment](#8-halideandroid-port-feasibility-assessment)
9. [Risks and Outstanding Items](#9-risks-and-outstanding-items)
10. [Next Steps Recommendations](#10-next-steps-recommendations)

---

## 1. Project Overview

### 1.1 Functional Positioning

Spektrafilm is an **image processing application that simulates the spectral characteristics of analog film photography**. Through a spectral simulation pipeline, it converts digital images into photos with authentic film aesthetics, covering:

- **Film Exposure Simulation**: Spectral upsampling, density curves, coupler reactions
- **Development Simulation**: Density spectrum computation, diffusion filtering, grain noise
- **Scanning Simulation**: CMY to XYZ color conversion, black-and-white correction, glare model
- **HDR Photo Output**: Gain Map HDR export, SDR base preservation
- **Color Management**: ACEScg working space, ICC profile embedding, CCTF encoding/decoding

### 1.2 Technology Stack

| Layer | Technology | Version |
|------|------|------|
| **Language** | Python | 3.13+ |
| **GUI Framework** | Qt (PySide6) + napari | 0.6.6 |
| **Numerical Computing** | NumPy | 2.4+ |
| **Color Science** | colour-science | 0.4.6+ |
| **Image I/O** | OpenImageIO | 3.1.11+ |
| **GPU Acceleration** | MLX (Apple Metal) / CuPy (CUDA) | Optional |
| **JIT Acceleration** | Numba | 0.64+ |
| **Signal Processing** | SciPy / pyFFTW | 1.17+ / 0.15+ |
| **Curve Fitting** | lmfit | 1.3.2+ |
| **RAW Processing** | rawpy (LibRaw) | 0.26+ |
| **Metadata** | exiv2 (pyexiv2) | 0.18+ |
| **License** | GPLv3 | -- |

### 1.3 Architecture Pattern

The project adopts a **layered pipeline architecture**:

```
Input RGB Image
    |
[Preprocessing] Auto Exposure -> Crop and Resize
    |
[Exposure Stage] Spectral Upsampling -> Highlight Boost -> Diffusion Filter -> Gaussian Blur -> Flare -> log10
    |
[Development Stage] Density Interpolation -> Coupler Reactions -> Grain Simulation
    |
[Print Exposure] Density Spectrum -> Light Intensity Conversion -> Diffusion Filter -> log10
    |
[Print Development] Density Interpolation
    |
[Scan Stage] CMY->XYZ -> Black-and-White Correction -> Glare -> XYZ->RGB -> Gaussian Blur+USM -> CCTF Encoding
    |
Output RGB Image
```

The core abstraction layer is the `ArrayBackend` protocol, supporting NumPy/CuPy/MLX three backends, enabling transparent CPU/GPU switching.

---

## 2. Code Structure Analysis

### 2.1 Module Breakdown

```
src/spektrafilm/          # Core library -- 66 Python files, 15,003 lines
├── config.py             #   14 lines -- Spectral constants, CIE CMFs, LMS basis data
├── color_management.py   #  ~150 lines -- Color space encoding presets, workflow selection
├── __init__.py           #    Version number export
├── model/                #   Physical model layer (8 modules)
│   ├── emulsion.py       #    Emulsion model -- density spectrum computation, development interpolation
│   ├── diffusion.py      #   609 lines -- Diffusion filter PSF, Gaussian/exponential blur
│   ├── grain.py          #    Grain model -- Poisson/binomial random, Gaussian blur
│   ├── couplers.py       #    Couplers -- einsum + Gaussian blur
│   ├── glare.py          #    Glare model -- lognormal random + Gaussian blur
│   ├── illuminants.py    #    Illuminant spectral distributions (precomputed data)
│   ├── color_filters.py  #   304 lines -- Dichroic color filters
│   ├── density_curves.py #    Density curves -- 1D linear interpolation
│   ├── parametric.py     #    Parametric curve fitting
│   └── stocks.py         #    Film/paper stock definitions
├── runtime/              #   Runtime pipeline layer (9 modules)
│   ├── pipeline.py       #   641 lines -- Core pipeline orchestration, GPU tiling
│   ├── process.py        #    Simulator convenience wrapper
│   ├── params_schema.py  #   246 lines -- Dataclass definitions
│   ├── params_builder.py #    Parameter building, profile adaptation
│   ├── api.py            #    Public API exports
│   ├── stages/           #    Pipeline stages
│   │   ├── filming.py    #   250 lines -- Exposure stage
│   │   ├── printing.py   #   170 lines -- Print stage
│   │   └── scanning.py   #    Scan stage
│   └── services/         #    Service layer
│       ├── spectral_lut_compute.py  # 288 lines -- Spectral LUT computation
│       ├── resize.py                 # Resize service
│       ├── color_reference.py        # Color reference correction
│       └── filter_enlarger_source.py # Enlarger light source filter
├── gpu/                  #   GPU backend layer (8 modules)
│   ├── backend.py        #    ArrayBackend protocol definition
│   ├── numpy_backend.py  #    NumPy CPU backend
│   ├── mlx_backend.py    #    MLX Metal backend (macOS)
│   ├── cupy_backend.py   #    CuPy CUDA backend
│   ├── metal_serialization.py # Metal serialization (macOS)
│   └── kernels/          #    Backend-portable GPU kernels
│       ├── color.py      #   315 lines -- Matrix multiplication, CCTF, highlight boost
│       ├── density.py    #   486 lines -- 1D interpolation, einsum, 10^x
│       ├── filters.py    #   637 lines -- Gaussian FIR/IIR, FFT convolution
│       └── lut.py        #   533 lines -- 2D/3D LUT interpolation (Mitchell-Netravali)
├── utils/                #   Utility layer (22 modules)
│   ├── hdr_photo.py      # 1,360 lines -- HDR photo processing (largest file)
│   ├── hdr_curve_profiles.py # 1,050 lines -- HDR curve profiles
│   ├── io.py             #   926 lines -- Image I/O, ICC embedding
│   ├── fast_interp_lut.py#   837 lines -- Numba 2D Mitchell-Netravali cubic LUT
│   ├── spectral_upsampling.py # 653 lines -- RGB->spectral upsampling
│   ├── raw_file_processor.py  # 618 lines -- RAW file processing
│   ├── fast_gaussian_filter.py# 413 lines -- Numba FIR/IIR Gaussian
│   ├── fast_stats.py     #   340 lines -- Numba RNG (Poisson, binomial, lognormal)
│   ├── fast_interp.py    #    Numba 1D linear interpolation
│   ├── fft_gaussian_filter.py # FFT Gaussian filter
│   ├── autoexposure.py   #    Auto exposure
│   ├── crop_resize.py    #    Crop and resize
│   ├── conversions.py    #    Density/light intensity conversion
│   ├── lut.py            #    LUT computation orchestration
│   ├── preview.py        #    Preview scaling
│   ├── plotting.py       #    Visualization (matplotlib)
│   └── ...               #    Other utilities
└── profiles/             #   Profile I/O
    └── io.py             #   335 lines -- JSON profile loading

src/spektrafilm_gui/      # GUI layer -- 24 Python files, 7,428 lines
├── app.py                #    Entry point -- creates viewer, widgets, controller
├── state.py              #    11 dataclass sections (GuiState)
├── widget_specs.py       #    Widget metadata (labels, tooltips, ranges)
├── widget_editors.py     #    Custom Qt editors
├── widget_sections.py    #    20+ section classes
├── widgets.py            #    WidgetBundle -- unified container
├── napari_layout.py      #   542 lines -- Main window layout
├── state_bridge.py       #    Bidirectional state synchronization
├── params_mapper.py      #    GuiState -> RuntimePhotoParams
├── controller.py         #    GuiController -- core interaction orchestration
├── controller_runtime.py #    SimulationWorker (QRunnable), display transforms
├── controller_layers.py  #    napari layer management, Polaroid animation
├── controller_persistence.py # 112 lines -- Save/load/reset
├── controller_profile_sync.py # Profile changes -> batch widget updates
├── persistence.py        #   112 lines -- JSON serialization
├── theme.py / theme_palette.py / theme_styles.py # Theme system
├── polaroid_animation.py #    Polaroid print animation
├── icons.py              #    Icon management
└── virtual_photo_paper_back.py # 284 lines -- Virtual photo paper back
```

### 2.2 Core Pipeline Details

The core pipeline is in `runtime/pipeline.py` (641 lines):

1. **Preprocessing** (`_preprocess_input_image`): Type conversion, channel cropping, auto exposure
2. **GPU Tiling** (`_process_preprocessed_with_gpu_tiles`): Default 2M pixels/tile, configurable
3. **Exposure Stage** (`filming.py`): Spectral upsampling -> highlight boost -> diffusion filter -> Gaussian blur -> flare -> log10
4. **Development Stage** (`filming.py`): Density interpolation -> coupler reactions -> grain simulation
5. **Print Exposure** (`printing.py`): Density spectrum -> light intensity -> diffusion -> log10
6. **Print Development** (`printing.py`): Density interpolation
7. **Scan Stage** (`scanning.py`): CMY->XYZ -> black-and-white correction -> glare -> XYZ->RGB -> USM -> CCTF

**Key Data Dimensions:** Spectral range 380-780nm, step size 5nm, 81 wavelengths total.

---

## 3. Test Status

### 3.1 Test Overview

```
Test run time: 13.15 seconds
Total collected: 471 tests
Passed: 458
Skipped: 13
Failed: 0
Warnings: 11
```

### 3.2 Test File Distribution

| Category | File Count | Description |
|------|--------|------|
| GPU Backend Tests | 7 | test_gpu_backend, test_gpu_color_chain, test_gpu_density, test_gpu_filters, test_gpu_highlight_boost, test_gpu_lut, test_gpu_pipeline |
| GPU Precision Validation | 1 | test_gpu_validate -- `np.allclose(atol=1e-6)` assertions |
| Pipeline Integration Tests | 4 | test_pipeline_smoke, test_pipeline_lut_lifecycle, test_runtime_api, test_regression_baselines |
| Model Unit Tests | 5 | test_emulsion, test_couplers, test_grain, test_parametric, test_spectral_upsampling |
| HDR Feature Tests | 3 | test_hdr_photo, test_hdr_curve_profiles, test_image_io_color_metadata |
| Color Management Tests | 2 | test_color_management, test_color_reference |
| I/O and Metadata Tests | 3 | test_exif_metadata, test_raw_file_processor, test_raw_smoke |
| Utility Tests | 6 | test_autoexposure, test_crop_resize, test_edge_cases, test_fft_gaussian_filter, test_lut, test_numba_warmup |
| Other | 4 | test_enlarger_filters, test_filming_stage, test_photo_params, test_profiles |
| **Total** | **35 files** | **Non-GUI tests** |

### 3.3 Skipped Tests (13)

All are GUI-related tests that are automatically skipped on a headless Linux server. They involve:
- Widget tests requiring QApplication
- napari viewer rendering tests
- QMessageBox popup tests

### 3.4 Warning Details (11)

| Type | Count | Source |
|------|------|------|
| DeprecationWarning | 4 | `IOParams.full_image` deprecated (setter is a no-op) |
| UserWarning | 1 | `apply_database_neutral_print_filters` neutral filter not found |
| Other DeprecationWarning | 6 | Runtime API compatibility paths |

---

## 4. Git History and Development Progress

### 4.1 Recent Commits (20)

```
95c2a70 test: add boundary and security tests for format_elapsed_time and _validate_path_component
f2f3944 fix: autonomous improvement -- GPU backend precision fixes, diffusion/grain model updates, IO and HDR utilities improvements
489f11f autonomous: round 5 improvements [skip ci]
cfa2f06 fix: autonomous improvements -- gpu color kernel, calibration targets, HDR profiles, IO utils, raw processor, and code quality review docs
6824399 autonomous: round 4 improvements [skip ci]
a5f402f autonomous: round 3 improvements [skip ci]
94f135e refactor: code quality review round 3 - cleanup and improvements
7c9e66e autonomous: round 2 improvements [skip ci]
0222288 refactor: code quality round 2 - math_ops extraction, pipeline/io cleanup, test improvements
fef8aaf autonomous: round 1 improvements [skip ci]
2851e07 fix: catch Exiv2Error in read_image_metadata for robustness
9e93bd8 refactor: code quality improvements from autonomous review
108f99b refactor: code review fixes - simplify pipeline/io, clean controller, improve tests, add dtypes module
37fc4bc docs: Halide/Android research + test fixes from autonomous loop
ddf98ae docs: add GUI, memory, Halide/Android research + autonomous pipeline fixes
a4003a9 docs: add research documents and code quality review
57c5112 test: add new test modules from autonomous improvement loop
cfa283c fix: code review round 1 - H2 path-to-white toggle, M2 HDR mapping validation, L1 README cleanup
765b6e5 chore: add Claude Code project config and autonomous loop script
f68a154 Align HDR RAW validation fallback checks
```

### 4.2 Development Rhythm

- **Total commits (recent 20):** 20
- **Since 2026-05-20:** 37 commits
- **Development mode:** Autonomous loop + manual review hybrid
- **Commit style:** Conventional Commits (fix/refactor/test/docs/chore)
- **Current branch status:** Clean (no uncommitted changes)

### 4.3 Development Phase Breakdown

| Phase | Content | Commits |
|------|------|------|
| **Foundation Setup** | Project initialization, core pipeline | f68a154 and earlier |
| **Code Review Round 1** | H2 path-to-white, M2 HDR validation, L1 README cleanup | cfa283c |
| **Autonomous Improvement Loops 1-5** | Incremental fixes, documentation generation, test additions | fef8aaf -> 489f11f |
| **Code Quality Review Rounds 2-6** | Refactoring, cleanup, common module extraction | 0222288 -> 94f135e |
| **GPU Precision Fixes** | Backend precision, diffusion/grain model updates | f2f3944 |
| **Security Tests** | Boundary tests, path validation tests | 95c2a70 |

---

## 5. Research Documentation Summary

The project contains 25 research documents covering technical investigations, code reviews, and implementation planning:

### 5.1 Code Review Documents

| Document | Key Findings |
|------|----------|
| **code-review-2026-05-26.md** | Comprehensive workspace review. Found 1 Critical (HDR Rendition EXR saves incorrect output), 3 High (ACEScg ICC mapping missing, GUI path-to-white toggle ineffective, HDR copy memory pressure), 4 Medium, 1 Low. |
| **code-quality-review-round-1~6.md** | Six rounds of code quality review. Round 6 found 45 issues: inconsistent type annotations (8), error handling (5), dead code (7), code duplication (4), API consistency (6), test coverage gaps (8), performance anti-patterns (5), security concerns (2). |

### 5.2 Technical Research Documents

| Document | Key Findings |
|------|----------|
| **research-gpu-color-management.md** | Comprehensive research on GPU acceleration and color management. Evaluated CuPy/MLX/JAX/Taichi/wgpu-py frameworks, confirmed ArrayBackend protocol design is correct. Recommends adding Taichi/Vulkan as GPU backends for Linux without CUDA. For color management, recommends integrating OCIO for ACES output transforms. |
| **deep-research-implementation-patterns.md** | Deep research on implementation patterns. Covers colour-science GPU acceleration (no native GPU support, requires dispatch via ArrayBackend), OCIO ACES workflows, ICC v4 profile creation, HDR gain map encoding (ISO 21496), Vulkan/WebGPU compute shaders, GPU tiling, ACES tone mapping, OIIO HDR metadata, Array API standard. |
| **research-halide-port.md** | Halide port research. Halide v21.0.0 supports CUDA/Metal/Vulkan/OpenCL, Python bindings installable via pip. A single pipeline definition can compile to all backends, eliminating the current three-backend maintenance burden. Performance expectations: 3-10x faster than NumPy on CPU, competitive with CuPy/MLX on GPU. |
| **research-memory-management.md** | Deep research on memory management. Audited pipeline peak memory (5-6 full-size arrays simultaneously present), 4K image peak ~480MB. Recommendations: CuPy memory pool management, MLX memory limits, tracemalloc analysis, pre-allocated buffer pools, memory-mapped I/O. |
| **research-memory-optimization-patterns.md** | Memory optimization patterns. Covers lazy evaluation, in-place operations (`out=` parameter), `__slots__` dataclasses (already adopted), weak-reference LRU caches, streaming/tiling processing, GPU memory pool management, shared memory. Lazy collection of HDR copies can save ~384MB/image. |
| **research-gui-color-hdr.md** | GUI color management and HDR preview. Current preview pipeline: float32 -> PIL.ImageCms ICC transform -> uint8 sRGB -> napari/VisPy. Evaluated Qt6 color management API, HDR surface rendering, soft proofing implementation strategies. |
| **research-gui-aesthetics.md** | GUI aesthetics and UX research. Architecture audit, theme style analysis, dark theme recommendations, widget improvements, layout optimization, high DPI support, color accuracy, accessibility, QML vs Widgets evaluation. |
| **research-gui-product-logic.md** | GUI product logic review. User flow mapping, pain point identification, comparison with professional tools, improvement suggestions. |
| **research-implementation-round-1~5.md** | Five rounds of implementation research. Progressively implemented ACEScg ICC mapping, HDR Rendition EXR, HDRPhotoMapping validation, Display P3 linear ICC, ISO 21496-1 gain map metadata, GPU tiling, Oklch perceptual gamut mapping, and more. |

### 5.3 Planning Documents

| Document | Core Content |
|------|----------|
| **halide-android-port-plan.md** | Complete Android port plan. Three phases: extract C++ compute core (2-3 months) -> Halide rewrite (2-3 months) -> Android integration (1-2 months). ~85% of compute operations can be directly expressed in Halide. |
| **test-improvement-plan.md** | Test improvement plan. 5 priorities: P1 FFT Gaussian filter precision, P2 crop/resize boundaries, P3 parametric density curve boundaries, P4 HDRPhotoMapping validation coverage, P5 ColorReferenceService unit tests. |
| **2026-05-26-develop-upstream-branch-integration-plan.md** | Upstream branch integration plan. |
| **autonomous-loop.log** | Autonomous loop run log. |

---

## 6. Code Quality Assessment

### 6.1 Issues Fixed

Based on code review documents and commit history, the following issues have been fixed during the autonomous improvement loops:

| Priority | Issue | Status | Fix Commit |
|--------|------|------|----------|
| **C1** | HDR Rendition EXR saves incorrect output | ✅ Fixed | cfa2f06 (added save_hdr_rendition_exr helper function) |
| **H1** | ACEScg ICC mapping missing | ✅ Fixed | cfa2f06 (added to _ICC_FILENAMES) |
| **H2** | GUI path-to-white toggle ineffective | ✅ Fixed | cfa283c (controller passes profile_hdr_path_to_white_strength=0.0) |
| **M2** | HDRPhotoMapping validation incomplete | ✅ Fixed | cfa283c (extended __post_init__ validation) |
| **L1** | README references non-existent package | ✅ Fixed | cfa283c (removed spektrafilm_profile_creator reference) |
| -- | GPU backend precision issues | ✅ Fixed | f2f3944 |
| -- | Diffusion/grain model updates | ✅ Fixed | f2f3944 |
| -- | IO and HDR utility improvements | ✅ Fixed | f2f3944 |
| -- | Path validation security tests | ✅ Added | 95c2a70 |

### 6.2 Outstanding Items

| Priority | Issue | Description |
|--------|------|------|
| **M1** | HDR SDR-base test expectation conflict | `preserve_sdr_base=True` default behavior is inconsistent with earlier test expectations. Need to decide on default behavior and update tests. |
| **M4** | save_image_oiio API boundary unclear | Tests/documentation expect it to accept HEIC/HDR parameters, but implementation treats it as a controller-level special case. Need to clarify ownership boundaries. |
| **H3** | GUI preview always computes full-size HDR copies | Each preview/scan computes scene_luminance and scene_rgb copies (~366MiB for a 4000x6000 image). Need an on-demand collection flag. |
| -- | FloatArray type alias inconsistency | Model layer uses float64, runtime and GPU use float32. Type aliases create incorrect contracts. |
| -- | Model layer functions missing type annotations | 8+ `backend=None` parameters in couplers.py, grain.py, diffusion.py lack annotations. |
| -- | GPU backend methods missing docstrings | ArrayBackend protocol and all three implementations lack docstrings. |

### 6.3 Code Quality Review Round 6 Findings Statistics

| Category | Count | Severity |
|------|------|----------|
| Type Annotations and Docstrings | 8 | Medium-Low |
| Error Handling | 5 | Medium-High |
| Dead Code and Unused Imports | 7 | Low-Medium |
| Code Duplication | 4 | Medium |
| API Consistency | 6 | Medium |
| Test Coverage Gaps | 8 | Medium-High |
| Performance Anti-patterns | 5 | Medium |
| Security Concerns | 2 | Low |
| **Total** | **45** | -- |

---

## 7. GPU Acceleration Status and Precision Guarantees

### 7.1 Backend Architecture

```
ArrayBackend Protocol (gpu/backend.py)
    ├── NumpyBackend    -- CPU fallback, always available
    ├── MlxBackend      -- Apple Metal (macOS Apple Silicon)
    └── CupyBackend     -- CUDA (NVIDIA GPU)
```

**Selection Cascade:** `auto` -> MLX/Metal -> CuPy/CUDA -> NumPy fallback.

### 7.2 GPU Kernel Coverage

| Kernel Category | File | Operations | Backend Support |
|----------|------|------|----------|
| Color Transform | `gpu/kernels/color.py` (315 lines) | 3x3 matrix multiplication, CCTF encoding/decoding, highlight boost | NumPy + MLX Metal + CuPy |
| Density Computation | `gpu/kernels/density.py` (486 lines) | 1D interpolation, einsum, 10^x | NumPy + MLX Metal + CuPy |
| Spatial Filtering | `gpu/kernels/filters.py` (637 lines) | Gaussian FIR/IIR, FFT convolution, reflect padding | NumPy + MLX Metal + CuPy |
| LUT Sampling | `gpu/kernels/lut.py` (533 lines) | 2D Mitchell-Netravali cubic, 3D trilinear | NumPy + MLX Metal + CuPy |

### 7.3 Precision Guarantee Mechanism

**Core Constraint (CLAUDE.md):** GPU output must be numerically identical to CPU/NumPy output within float32 precision (`atol=1e-6`).

**Implementation Measures:**
- float32 throughout (no float16 unless explicitly opted in by user)
- Same algorithms, same order of operations
- Every GPU kernel has a corresponding test asserting `np.allclose(gpu_result, cpu_result, atol=1e-6)`
- If a GPU backend cannot match precision, fall back to CPU

**Test Coverage:** 7 GPU-specific test files + 1 precision validation file, covering color chain, density, filtering, highlight boost, LUT, and full pipeline.

### 7.4 GPU Tiling

`pipeline.py` implements automatic GPU tiling:
- **Default Budget:** 2,000,000 pixels/tile (~24MB float32 RGB)
- **Configuration:** `SPEKTRAFILM_GPU_TILE_PIXELS` environment variable
- **Overlap Computation:** Automatically calculated based on lens blur, flare scatter, and diffusion size

### 7.5 Known Limitations

- **CuPy backend lacks memory pool management:** GPU memory is not released between pipeline runs
- **MLX backend lacks memory limit settings:** May cause OOM on Apple Silicon
- **No tracemalloc integration:** Memory issues are difficult to diagnose

---

## 8. Halide/Android Port Feasibility Assessment

### 8.1 Halide Overview

Halide v21.0.0 is an image processing DSL with a core advantage: **separation of algorithm from schedule**. A single pipeline definition can compile to CPU (x86/ARM), CUDA, Metal, Vulkan, OpenCL.

### 8.2 Portability Assessment

| Operation Category | Count | Portability | Halide Adaptation |
|----------|------|----------|-------------|
| Element-wise math (exp, log, pow, select) | ~15 | **Excellent** | Native Halide |
| Matrix multiplication (3x3, einsum) | ~8 | **Excellent** | Halide reduction |
| 1D interpolation | ~4 | **Excellent** | Halide + clamp |
| 2D/3D LUT sampling | ~3 | **Excellent** | Halide + lookup |
| Gaussian blur (FIR) | ~5 | **Excellent** | Halide convolve |
| Gaussian blur (IIR) | ~3 | **Good** | Halide scan |
| Exponential filtering | ~3 | **Good** | Multi-pass Gaussian |
| FFT convolution | ~2 | **Medium** | External FFT or spatial decomposition |
| Random operations (RNG) | ~3 | **Poor** | Preprocess with C++ RNG |
| Color science initialization | ~10 | **Not applicable** | Precomputed static data |
| File I/O | ~5 | **Not applicable** | Native Android API |
| GUI | 24 files | **Not applicable** | Kotlin/Jetpack Compose |

**Conclusion:** ~85% of compute-intensive operations can be directly expressed in Halide. The remaining 15% (FFT, RNG) can be handled through hybrid approaches.

### 8.3 Dependency Replacement Strategy

| Dependency | Replacement | Effort |
|------|----------|--------|
| colour-science | Precomputed matrices + static spectral data | Medium |
| scipy | Mostly already replaced by custom implementations | Low-Medium |
| NumPy | Halide replaces compute graph | **This is the port itself** |
| Numba | Halide replaces (existing Metal/CuPy reference) | Low |
| opt-einsum | Nested loops or BLAS | Low |
| matplotlib/napari/qtpy | Skip (GUI rewritten in Kotlin) | Not applicable |

### 8.4 Port Roadmap

| Phase | Timeline | Goal |
|------|------|------|
| **Phase 1: Extract C++ Compute Core** | 2-3 months | Pure C++ library, no Python dependencies, output consistent with Python version |
| **Phase 2: Halide Rewrite** | 2-3 months | Replace performance-critical C++ loops with Halide pipeline, ARM optimization |
| **Phase 3: Android Integration** | 1-2 months | JNI bridging, Kotlin UI, image I/O, profile management |

### 8.5 Key Risks

| Risk | Severity | Mitigation |
|------|------|----------|
| Grain model randomness | High | Preprocess with C++ RNG -> Halide buffer |
| colour-science dependency depth | High | Hot paths already precomputed, low impact |
| FFT diffusion filtering | Medium | Use spatial convolution for small kernels, or integrate FFTW |
| Numerical precision consistency | Medium | ARM NEON float32 meets `atol=1e-6` |
| Profile data size | Low | Load on demand, active pipeline ~50KB |

---

## 9. Risks and Outstanding Items

### 9.1 Technical Risks

| Risk | Impact | Likelihood | Mitigation |
|------|------|--------|----------|
| HDR copy memory pressure (H3) | High | High | Add `collect_hdr_metadata` flag, skip copy computation during preview |
| GUI HEIC test causes pytest abort (M3) | Medium | Medium | Monkey-patch HEIC encoder, mock QMessageBox |
| save_image_oiio API boundary unclear (M4) | Medium | Medium | Clearly document API responsibilities, rename helper functions |
| Float32/Float64 type mixing | Low | Medium | Unify type aliases, add mypy checks |
| No GPU memory pool management | Medium | Low | Add CuPy/MLX memory pool configuration |

### 9.2 To-Do Checklist

**Must Fix (before integration):**
- [ ] M1: Decide on `preserve_sdr_base=True` default behavior, update earlier HDR test expectations
- [ ] M4: Clarify API boundary between `save_image_oiio` and specialized HDR helper functions

**Should Fix Soon:**
- [ ] H3: Add `collect_hdr_metadata` flag to avoid computing full-size HDR copies during preview
- [ ] Test coverage: FFT Gaussian filter precision tests, crop/resize boundary tests
- [ ] Type annotations: Unify FloatArray alias, supplement model layer type hints

**Optional Optimizations:**
- [ ] GPU memory pool management (CuPy/MLX)
- [ ] tracemalloc memory analysis integration
- [ ] Weak-reference LUT cache
- [ ] Pre-allocated pipeline buffer pool

**Requires Product Decision:**
- [ ] Should HEIC SDR base preserve current SDR appearance (`preserve_sdr_base=True`) or the legacy `sdr_paper_white=0.9` tone mapping?
- [ ] Should HDR copies be retained after every scan, or only collected during explicit HDR export?

---

## 10. Next Steps Recommendations

### 10.1 Short-term (1-2 Weeks)

1. **Resolve M1 test expectation conflict** -- Decide on SDR base default behavior, update earlier tests in `test_hdr_photo.py`
2. **Add P1 tests (FFT Gaussian filter)** -- `test_fft_gaussian_filter.py`, verify consistency with scipy reference implementation
3. **Add P2 tests (crop/resize boundaries)** -- `test_crop_resize.py`, cover boundary clamping logic
4. **Clarify M4 API boundary** -- Document `save_image_oiio` responsibilities, rename if necessary

### 10.2 Mid-term (1-2 Months)

1. **Implement H3 memory optimization** -- Add `SimulationRequest.collect_hdr_metadata` flag
2. **GPU memory pool management** -- CuPy `free_all_blocks()` + MLX `set_memory_limit()`
3. **OCIO optional integration** -- For ACES output transforms (RRT+ODT)
4. **Cross-platform HDR gain map** -- Replace macOS-only HEIC encoder

### 10.3 Long-term (3-6 Months)

1. **Halide backend prototype** -- As a fourth ArrayBackend option, starting with color matrix kernels
2. **Vulkan/Taichi backend** -- GPU acceleration for Linux without CUDA
3. **Android port** -- Follow three-phase plan in halide-android-port-plan.md
4. **ISO 21496-1 gain map JPEG** -- Cross-platform HDR photo output

---

## Appendix: Key Metrics Summary

| Metric | Value |
|------|------|
| Core library file count | 66 |
| Core library lines of code | 15,003 |
| GUI file count | 24 |
| GUI lines of code | 7,428 |
| Test file count | 35 (non-GUI) |
| Test lines of code | 8,313 |
| Tests collected | 471 |
| Tests passed | 458 |
| Tests skipped | 13 |
| Tests failed | 0 |
| Largest source file | hdr_photo.py (1,360 lines) |
| Research document count | 25 |
| Code review rounds | 6 |
| Autonomous improvement loop rounds | 5 |
| Recent 37 commits time span | 2026-05-20 ~ 2026-05-27 |
| Project version | 0.3.1 |
| Python version requirement | 3.13+ |
