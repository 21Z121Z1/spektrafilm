# Architecture Index

> Generated 2026-05-28 — Phase 1 Quality Audit

## Package Structure

```
src/spektrafilm/           — Core library (simulation engine)
src/spektrafilm/gpu/       — GPU backend abstraction layer
src/spektrafilm/model/     — Physical film/paper models
src/spektrafilm/profiles/  — Film/paper profile I/O
src/spektrafilm/runtime/   — Pipeline orchestration
src/spektrafilm/utils/     — Image I/O, HDR, math, filters
src/spektrafilm/halide/    — Halide availability detection
src/spektrafilm_gui/       — Qt GUI (not audited — skipped on Linux)
```

---

## Core Library Modules

### `spektrafilm/__init__.py` (19 LOC)
- **Purpose**: Public package exports — re-exports from profiles, runtime.
- **Dependencies**: `profiles.io`, `runtime.api`, `runtime.process`, `runtime.params_schema`
- **Public API**: `load_profile`, `save_profile`, `RuntimePhotoParams`, `init_params`, `digest_params`, `Simulator`, `simulate`, `simulate_preview`, `AgXPhoto`, `photo_params`

### `spektrafilm/config.py` (15 LOC)
- **Purpose**: Global spectral constants and standard observer data.
- **Dependencies**: `numpy`, `colour`
- **Public API**: `LOG_EXPOSURE`, `SPECTRAL_SHAPE`, `STANDARD_OBSERVER_CMFS`, `STANDARD_OBSERVER_LMS`

### `spektrafilm/color_management.py` (176 LOC)
- **Purpose**: Color management workflow presets, color encoding descriptors, IO-to-encoding mapping.
- **Dependencies**: `colour`, `runtime.params_schema` (TYPE_CHECKING only)
- **Public API**: `ColorEncoding`, `ColorManagementWorkflowPreset`, `is_aces_scene_linear_space`, `color_management_workflow_preset`, `apply_color_management_workflow_to_io`, `input_encoding_from_io`, `output_encoding_from_io`, `ACES_INTERCHANGE_COLOR_SPACE`, `ACES_WORKING_COLOR_SPACE`

---

## GPU Backend Layer (`spektrafilm/gpu/`)

### `gpu/backend.py` (204 LOC)
- **Purpose**: Backend protocol definition, selection logic, GPU tiling utility.
- **Dependencies**: None (imports backends lazily)
- **Public API**: `ArrayBackend` (Protocol), `BackendUnavailableError`, `BackendInfo`, `select_backend`, `backend_summary`, `tiled_processing`

### `gpu/numpy_backend.py` (70 LOC)
- **Purpose**: CPU fallback backend using NumPy + opt_einsum.
- **Dependencies**: `numpy`, `opt_einsum`
- **Public API**: `NumpyBackend`

### `gpu/mlx_backend.py` (127 LOC)
- **Purpose**: Apple MLX/Metal GPU backend.
- **Dependencies**: `mlx.core` (optional), `gpu.backend`
- **Public API**: `MlxBackend`

### `gpu/cupy_backend.py` (114 LOC)
- **Purpose**: CUDA/ROCm GPU backend via CuPy.
- **Dependencies**: `cupy` (optional), `gpu.backend`
- **Public API**: `CupyBackend`

### `gpu/halide_backend.py` (830 LOC)
- **Purpose**: Halide JIT backend for CPU-optimized kernels (trilinear 3D LUT, RGB matrix, spectral ops, FIR blur, CCTF, interpolation).
- **Dependencies**: `halide` (optional), `numpy`, `opt_einsum`, `gpu.backend`
- **Public API**: `HalideBackend` — extends ArrayBackend with `rgb_to_xyz`, `apply_lut_trilinear_3d`, `density_to_light`, `light_to_raw`, `compute_density_spectral`, `gaussian_blur_fir`, `gaussian_blur_iir`, `highlight_boost`, `cctf_encode`, `cctf_decode`, `interp_1d`, `lut_2d_cubic`, `generate_grain_buffer`

### `gpu/metal_serialization.py` (16 LOC)
- **Purpose**: Thread-safe MLX/Metal runtime serialization via RLock.
- **Dependencies**: `threading`
- **Public API**: `serialized_metal_runtime` (context manager)

### `gpu/kernels/color.py` (327 LOC)
- **Purpose**: Backend-portable colour transforms — RGB↔XYZ matrices, CCTF encode/decode, highlight boost.
- **Dependencies**: `colour`, `numpy`
- **Public API**: `precompute_rgb_to_xyz_matrix`, `precompute_xyz_to_rgb_matrix`, `precompute_cctf_decode_matrix`, `rgb_to_xyz`, `xyz_to_rgb`, `cctf_decoding_transfer_backend`, `cctf_decoding_backend`, `cctf_encoding_backend`, `boost_highlights_backend`

### `gpu/kernels/density.py` (486 LOC)
- **Purpose**: Backend-portable density/spectral operations — interpolation, density-to-light, light-to-raw, CMY→log(XYZ) chain.
- **Dependencies**: `numpy`, `model.density_curves` (CPU fallback)
- **Public API**: `interpolate_exposure_to_density_backend`, `interpolate_density_cmy_layers_backend`, `compute_density_spectral`, `density_to_light`, `light_to_raw`, `cmy_to_log_xyz_backend`

### `gpu/kernels/filters.py` (637 LOC)
- **Purpose**: Backend-portable Gaussian blur (FIR small-sigma, IIR large-sigma), exponential filter, FFT convolution, reflect padding.
- **Dependencies**: `utils.fast_gaussian_filter`, `numpy`
- **Public API**: `gaussian_filter_backend`, `gaussian_filter_small_backend`, `gaussian_filter_large_backend`, `exponential_filter_backend`, `fft_convolve_same_backend`, `reflect_pad_hw_backend`

### `gpu/kernels/lut.py` (536 LOC)
- **Purpose**: Backend-portable LUT interpolation — 2D cubic (Mitchell-Netravali), 3D trilinear, 2D bilinear.
- **Dependencies**: `numpy`
- **Public API**: `apply_lut_cubic_2d_backend`, `apply_lut_trilinear_3d_backend`, `apply_lut_bilinear_2d_mlx`, `apply_lut_bilinear_2d_numpy`, `apply_lut_cubic_2d_mlx`, `apply_lut_cubic_2d_cupy`, `apply_lut_trilinear_3d_mlx`, `apply_lut_trilinear_3d_cupy`

---

## Physical Models (`spektrafilm/model/`)

### `model/emulsion.py` (92 LOC)
- **Purpose**: Film emulsion development — density spectral computation, simple and full develop pipelines.
- **Dependencies**: `numpy`, `opt_einsum`, `model.couplers`, `model.grain`, `gpu.kernels.density`, `runtime.params_schema`
- **Public API**: `compute_density_spectral`, `develop_simple`, `develop`

### `model/density_curves.py` (64 LOC)
- **Purpose**: Exposure-to-density interpolation and CMY layer interpolation.
- **Dependencies**: `utils.fast_interp`, `numpy`
- **Public API**: `interpolate_exposure_to_density`, `interp_density_cmy_layers`, `_interp_density_cmy_layers_cpu`

### `model/couplers.py` (195 LOC)
- **Purpose**: Directional coupler colour correction — matrix computation, exposure correction, density curve modification.
- **Dependencies**: `numpy`, `scipy.ndimage`, `utils.fast_gaussian_filter`, `runtime.params_schema`
- **Public API**: `compute_dir_couplers_matrix`, `compute_density_curves_before_dir_couplers`, `compute_exposure_correction_dir_couplers`, `apply_density_correction_dir_couplers`

### `model/grain.py` (246 LOC)
- **Purpose**: Film grain simulation — particle model (Poisson-binomial, gamma-beta), sublayer grain, micro-structure.
- **Dependencies**: `numpy`, `scipy`, `model.density_curves`, `utils.fast_stats`, `utils.fast_gaussian_filter`, `runtime.params_schema`
- **Public API**: `layer_particle_model`, `apply_grain_to_density`, `apply_grain_to_density_layers`, `apply_grain`

### `model/diffusion.py` (609 LOC)
- **Purpose**: Diffusion filter PSF model (glimmerglass, black pro-mist, pro-mist, cinebloom), halation (scatter + back-reflection), unsharp mask.
- **Dependencies**: `numpy`, `scipy.ndimage`, `scipy.signal`, `gpu.kernels.filters`
- **Public API**: `apply_unsharp_mask`, `apply_halation_um`, `apply_gaussian_blur`, `apply_gaussian_blur_um`, `apply_diffusion_filter_mm`, `diffusion_filter_psf`, `apply_diffusion_filter_um`, `DIFFUSION_FILTER_FAMILIES`

### `model/glare.py` (23 LOC)
- **Purpose**: Stochastic glare overlay using lognormal random fields.
- **Dependencies**: `numpy`, `utils.fast_stats`, `utils.fast_gaussian_filter`
- **Public API**: `add_glare`, `compute_random_glare_amount`

### `model/illuminants.py` (66 LOC)
- **Purpose**: Standard illuminant loading (D50, D55, D65, A, etc.) from bundled CSV data.
- **Dependencies**: `numpy`, `colour`, `config`
- **Public API**: `standard_illuminant`

### `model/color_filters.py` (304 LOC)
- **Purpose**: UV/IR bandpass filter computation, dichroic filter loading.
- **Dependencies**: `numpy`, `config`
- **Public API**: `compute_band_pass_filter`

### `model/stocks.py` (39 LOC)
- **Purpose**: Enumerations of known film stocks and print papers.
- **Dependencies**: None
- **Public API**: `FilmStocks`, `PrintPapers`

### `model/parametric.py` (18 LOC)
- **Purpose**: Parametric density curve generation.
- **Dependencies**: `numpy`
- **Public API**: (minimal — used internally)

---

## Profile I/O (`spektrafilm/profiles/`)

### `profiles/io.py` (335 LOC)
- **Purpose**: Film/paper profile loading/saving, validation, JSON serialization.
- **Dependencies**: `numpy`, `json`, `importlib.resources`
- **Public API**: `Profile`, `ProfileData`, `ProfileInfo`, `PROFILE_TYPES`, `PROFILE_SUPPORTS`, `PROFILE_STAGES`, `PROFILE_USES`, `PROFILE_ANTIHALATION`, `PROFILE_CHANNEL_MODELS`, `profile_from_dict`, `profile_to_dict`, `load_profile`, `save_profile`

---

## Runtime Pipeline (`spektrafilm/runtime/`)

### `runtime/api.py` (23 LOC)
- **Purpose**: Compatibility re-exports for the older runtime API module path.
- **Dependencies**: `runtime.params_builder`, `runtime.pipeline`, `runtime.process`, `runtime.params_schema`
- **Public API**: `Simulator`, `simulate`, `simulate_preview`, `RuntimePhotoParams`, `HDRSceneEnergyMetadata`, `SimulationPipelineResult`, `init_params`, `digest_params`

### `runtime/process.py` (180 LOC)
- **Purpose**: User-facing `Simulator` class and convenience `simulate`/`simulate_preview` functions. Handles Metal serialization.
- **Dependencies**: `runtime.pipeline`, `runtime.params_builder`, `runtime.params_schema`, `gpu.metal_serialization`, `utils.preview`
- **Public API**: `Simulator`, `simulate`, `simulate_preview`, `AgXPhoto`, `photo_params`

### `runtime/pipeline.py` (692 LOC)
- **Purpose**: Core simulation pipeline orchestrator — composes Filming/Printing/Scanning stages, handles GPU tiling, debug modes, HDR metadata.
- **Dependencies**: `colour`, `numpy`, `color_management`, `utils.dtypes`, `runtime.services`, `runtime.params_schema`, `runtime.stages`, `gpu.backend`, `utils.hdr_curve_profiles`, `utils.timings`
- **Public API**: `SimulationPipeline`, `SimulationPipelineResult`, `HDRSceneEnergyMetadata`, `characterize_pipeline_profile`

### `runtime/params_schema.py` (246 LOC)
- **Purpose**: All runtime parameter dataclasses — camera, enlarger, scanner, grain, halation, dir couplers, glare, film/print rendering, IO, debug, settings.
- **Dependencies**: `profiles.io`
- **Public API**: `RuntimePhotoParams`, `CameraParams`, `EnlargerParams`, `ScannerParams`, `GrainParams`, `HalationParams`, `DirCouplersParams`, `GlareParams`, `FilmRenderingParams`, `PrintRenderingParams`, `IOParams`, `DebugParams`, `SettingsParams`, `DiffusionFilterParams`

### `runtime/params_builder.py` (217 LOC)
- **Purpose**: Parameter digestion — applies stock-specific overrides, halation presets, preview mode, debug switches, neutral print filter database lookup.
- **Dependencies**: `profiles.io`, `runtime.params_schema`, `utils.io`
- **Public API**: `digest_params`, `init_params`, `apply_database_neutral_print_filters`

### `runtime/stages/filming.py` (250 LOC)
- **Purpose**: Filming stage — RGB→raw conversion, exposure, halation, diffusion filter, development.
- **Dependencies**: `gpu.kernels.color`, `model.color_filters`, `model.diffusion`, `utils.numba_boost_highlights`, `model.emulsion`, `utils.autoexposure`, `utils.spectral_upsampling`, `utils.timings`
- **Public API**: `FilmingStage`

### `runtime/stages/printing.py` (170 LOC)
- **Purpose**: Printing stage — enlarger exposure, diffusion filter, print development.
- **Dependencies**: `gpu.kernels.density`, `model.diffusion`, `model.emulsion`, `model.illuminants`, `utils.conversions`, `utils.timings`
- **Public API**: `PrintingStage`

### `runtime/stages/scanning.py` (217 LOC)
- **Purpose**: Scanning stage — CMY→RGB conversion, lens blur, unsharp mask, black/white correction, colour encoding.
- **Dependencies**: `colour`, `gpu.kernels.color`, `gpu.kernels.density`, `gpu.kernels.filters`, `model.diffusion`, `utils.timings`
- **Public API**: `ScanningStage`

### `runtime/services/` (4 files)
- **Purpose**: Shared services — `SpectralLUTService` (LUT lifecycle), `EnlargerService` (illuminant filtering), `ResizingService` (crop/rescale), `ColorReferenceService` (exposure balance).
- **Dependencies**: Various model and utils modules

---

## Utilities (`spektrafilm/utils/`)

### `utils/io.py` (946 LOC)
- **Purpose**: Image I/O via OpenImageIO — load/save PNG/JPEG/TIFF/EXR, ICC profile management, EXIF/metadata writing, HDR photo export dispatch, neutral filter database.
- **Dependencies**: `colour`, `exiv2`, `OpenImageIO`, `PIL`, `scipy.interpolate`, `color_management`, `utils.dtypes`, `utils.hdr_photo`
- **Public API**: `load_image_oiio`, `save_image_oiio`, `save_hdr_rendition_exr`, `load_image_payload`, `read_image_color_encoding`, `read_image_metadata`, `write_image_metadata`, `resolve_icc_profile_bytes`, `colorspace_chromaticities`, `ImageMetadata`, `ImagePayload`

### `utils/hdr_photo.py` (1387 LOC)
- **Purpose**: HDR photo export — paper rolloff, scene luminance grafting, profile-aware HDR curves, diffuse lift, gamut mapping (Oklch), gain map encoding, HEIC export via Swift/CoreImage.
- **Dependencies**: `numpy`, `math`, `platform`, `subprocess`, `utils.hdr_curve_profiles`, `utils.math_ops`, `gpu.kernels.color`
- **Public API**: `HDRPhotoMapping`, `HDRPhotoRenditions`, `ISO21496GainMapMetadata`, `save_hdr_photo_heic`, `prepare_hdr_photo_renditions`, `build_iso_21496_1_gain_map_metadata`, `encode_gain_map_log2`, `build_gain_map_xmp_packet`, `validate_gain_map`, `gamut_map_oklch`, `build_hdr_debug_sidecar`

### `utils/gain_map.py` (231 LOC)
- **Purpose**: ISO 21496-1 gain map computation — compute, normalize, denormalize, apply, weight factor.
- **Dependencies**: `numpy`
- **Public API**: `compute_gain_map`, `normalize_gain_map`, `denormalize_gain_map`, `compute_weight`, `apply_gain_map`

### `utils/gain_map_io.py` (540 LOC)
- **Purpose**: Gain map JPEG (MPF) and HEIF container I/O — save/load dual-image files with ISO 21496-1 metadata.
- **Dependencies**: `numpy`, `PIL`, `utils.gain_map`, `utils.gain_map_metadata`
- **Public API**: `save_gain_map_jpeg`, `save_gain_map_heif`, `load_gain_map`

### `utils/gain_map_metadata.py` (248 LOC)
- **Purpose**: Gain map metadata serialization (binary + XMP) per ISO 21496-1.
- **Dependencies**: `numpy`, `struct`, `dataclasses`
- **Public API**: `GainMapMetadata`, `GainMapChannel`

### `utils/hdr_curve_profiles.py` (1049 LOC)
- **Purpose**: Film-print HDR curve profiles — profile-preserving curves, modern recovery peak budget, dynamic curve building.
- **Dependencies**: `numpy`, `dataclasses`
- **Public API**: `FilmPrintHDRCurveProfile`, `ProfilePreservingHDRCurveResult`, `ProfileHDRCurveResult`, `build_profile_hdr_curve`, `build_profile_preserving_hdr_curve`, `evaluate_profile_sdr_curve`, `get_hdr_curve_profile`, `build_dynamic_curve_profile`, `luminance_y`

### `utils/spectral_upsampling.py` (653 LOC)
- **Purpose**: RGB→spectral upsampling — Hanatos2025 method, Mallett2019 method.
- **Dependencies**: `colour`, `numpy`, `config`
- **Public API**: `SpectralInputPolicy`, `precompute_hanatos2025_constants`, `rgb_to_raw_hanatos2025_backend`, `rgb_to_raw_mallett2019`

### `utils/fast_gaussian_filter.py` (413 LOC)
- **Purpose**: Fast Gaussian filtering — FIR (small sigma), IIR/YVV (large sigma), exponential filter.
- **Dependencies**: `numpy`, `scipy.ndimage`, `numba` (optional)
- **Public API**: `fast_gaussian_filter`, `fast_gaussian_filter_small`, `fast_exponential_filter`, `_gaussian_kernel_1d`, `_yvv_coeffs`, `_gaussian_filter_2d_large`

### `utils/fast_interp.py` (182 LOC)
- **Purpose**: Numba-accelerated 1D linear interpolation for density curves.
- **Dependencies**: `numpy`, `numba` (optional)
- **Public API**: `fast_interp`

### `utils/fast_interp_lut.py` (837 LOC)
- **Purpose**: Numba-accelerated 2D cubic (Mitchell-Netravali) LUT interpolation.
- **Dependencies**: `numpy`, `numba` (optional)
- **Public API**: `apply_lut_cubic_2d`

### `utils/fast_stats.py` (340 LOC)
- **Purpose**: Numba-accelerated statistical distributions — Poisson, binomial, lognormal.
- **Dependencies**: `numpy`, `numba` (optional)
- **Public API**: `fast_poisson`, `fast_binomial`, `fast_lognormal_from_mean_std`

### `utils/autoexposure.py` (245 LOC)
- **Purpose**: Scene-referenced auto-exposure measurement.
- **Dependencies**: `numpy`, `colour`, `utils.hdr_curve_profiles`
- **Public API**: `measure_autoexposure_ev`

### `utils/numba_boost_highlights.py` (165 LOC)
- **Purpose**: Numba-accelerated highlight boost curve.
- **Dependencies**: `numpy`, `numba` (optional)
- **Public API**: `boost_highlights`

### `utils/conversions.py` (45 LOC)
- **Purpose**: Density-to-light transmittance, ACES conversion matrix.
- **Dependencies**: `numpy`, `colour`, `config`
- **Public API**: `density_to_light`, `compute_aces_conversion_matrix`

### `utils/crop_resize.py` (29 LOC)
- **Purpose**: Image cropping and resizing helpers.
- **Dependencies**: `numpy`, `scipy.ndimage`
- **Public API**: `crop_center`, `resize_image`

### `utils/dtypes.py` (54 LOC)
- **Purpose**: Runtime float dtype validation and selection.
- **Dependencies**: `numpy`
- **Public API**: `validate_float_dtype`, `runtime_float_dtype`

### `utils/timings.py` (85 LOC)
- **Purpose**: Timing decorator and formatting.
- **Dependencies**: `time`, `functools`
- **Public API**: `timeit`, `format_timings`

### `utils/preview.py` (50 LOC)
- **Purpose**: Preview resize for interactive use.
- **Dependencies**: `numpy`, `scipy.ndimage`
- **Public API**: `resize_for_preview`

### `utils/lut.py` (177 LOC)
- **Purpose**: LUT generation and management utilities.
- **Dependencies**: `numpy`, `scipy.interpolate`
- **Public API**: LUT generation helpers

### `utils/fft_gaussian_filter.py` (180 LOC)
- **Purpose**: FFT-based Gaussian filtering for very large sigmas.
- **Dependencies**: `numpy`, `scipy.fft`
- **Public API**: `fft_gaussian_filter`

### `utils/raw_file_processor.py` (618 LOC)
- **Purpose**: RAW camera file processing via rawpy.
- **Dependencies**: `rawpy`, `numpy`, `colour`
- **Public API**: `process_raw_file`

### `utils/calibration_targets.py` (162 LOC)
- **Purpose**: ColorChecker and calibration target data.
- **Dependencies**: `numpy`
- **Public API**: calibration target arrays

### `utils/measure.py` (93 LOC)
- **Purpose**: Image quality measurement utilities (ΔE, etc.).
- **Dependencies**: `numpy`, `colour`
- **Public API**: measurement functions

### `utils/plotting.py` (183 LOC)
- **Purpose**: Diagnostic plotting utilities.
- **Dependencies**: `matplotlib`, `numpy`
- **Public API**: plotting helpers

---

## Halide Integration (`spektrafilm/halide/`)

### `halide/__init__.py` (0 LOC)
- **Purpose**: Package marker.

### `halide/availability.py` (45 LOC)
- **Purpose**: Halide availability detection.
- **Dependencies**: None
- **Public API**: availability check functions

### `halide/android.py` (92 LOC)
- **Purpose**: Android Halide backend support.
- **Dependencies**: `halide`
- **Public API**: Android-specific utilities
