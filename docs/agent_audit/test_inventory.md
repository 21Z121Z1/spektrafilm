# Test Inventory

> Generated 2026-05-28 — Phase 1 Quality Audit
> 608 non-GUI tests collected across 42 test files

---

## Test Files by Module

### `test_hdr_photo.py` — 132 tests
- **Module**: `utils/hdr_photo.py`
- **Coverage**: HDRPhotoMapping validation (40+ edge cases), paper rolloff (logistic + logarithmic), generic/profile-aware renditions, gain map encoding, Oklch gamut mapping, SDR base preservation, diffuse lift, path-to-white, highlight color modes, ISO 21496-1 metadata, debug sidecar
- **Quality**: HIGH — extensive parametric validation, edge case coverage for __post_init__ constraints, round-trip tests for gain map encode/decode
- **NOT covered**: macOS HEIC encoder subprocess (platform-dependent), Swift toolchain errors

### `test_gain_map.py` — 43 tests
- **Module**: `utils/gain_map.py`, `utils/gain_map_io.py`, `utils/gain_map_metadata.py`
- **Coverage**: compute/normalize/denormalize round-trip, apply_gain_map with various headroom targets, weight factor, JPEG MPF save/load round-trip, HEIF save, metadata serialization, XMP generation
- **Quality**: HIGH — round-trip invariants well tested, edge cases (zero span, equal headroom)
- **NOT covered**: HEIF load path (requires pillow-heif), ISOBMFF binary patching

### `test_edge_cases.py` — 41 tests
- **Module**: Various (runtime, model, utils)
- **Coverage**: NaN/inf handling, zero-size arrays, extreme values, negative densities, empty profiles, boundary conditions
- **Quality**: HIGH — tests robustness at system boundaries

### `test_runtime_api.py` — 29 tests
- **Module**: `runtime/api.py`, `runtime/process.py`, `runtime/params_builder.py`
- **Coverage**: `simulate`, `simulate_preview`, `Simulator`, `init_params`, `digest_params`, preview mode, soft_update, params builder, metal serialization
- **Quality**: MEDIUM — tests public API surface, some integration tests with small images
- **NOT covered**: Large image GPU tiling, concurrent access

### `test_image_io_color_metadata.py` — 24 tests
- **Module**: `utils/io.py`
- **Coverage**: ICC profile read/write round-trip, color space detection from ICC/EXR/chromaticities, ICC embedding in PNG/JPEG/TIFF, EXR chromaticities, color encoding from file
- **Quality**: HIGH — tests real ICC profile byte matching
- **NOT covered**: save_hdr_rendition_exr, HEIC I/O paths

### `test_hdr_curve_profiles.py` — 23 tests
- **Module**: `utils/hdr_curve_profiles.py`
- **Coverage**: FilmPrintHDRCurveProfile construction, curve evaluation, profile-preserving HDR curves, dynamic curve building, monotonicity enforcement, polarity detection
- **Quality**: MEDIUM — tests curve properties and invariants

### `test_gpu_color_chain.py` — 18 tests
- **Module**: `gpu/kernels/color.py`
- **Coverage**: RGB↔XYZ matrix computation, CCTF encode/decode for sRGB/P3/ProPhoto/BT2020/AdobeRGB, backend dispatch (NumPy/CuPy/MLX), highlight boost
- **Quality**: HIGH — numerical parity tests against colour-science reference

### `test_halide_color.py` — 17 tests
- **Module**: `gpu/halide_backend.py` (color operations)
- **Coverage**: Halide RGB matrix, CCTF encode/decode, highlight boost
- **Quality**: MEDIUM — tests Halide-specific JIT kernels against NumPy reference

### `test_gpu_backend.py` — 16 tests
- **Module**: `gpu/backend.py`, `gpu/numpy_backend.py`, `gpu/mlx_backend.py`, `gpu/cupy_backend.py`
- **Coverage**: Backend selection (auto/cpu/mlx/cupy), protocol compliance, fallback behavior, tiled_processing, backend_summary
- **Quality**: MEDIUM — tests selection logic, some backends skipped on Linux

### `test_exif_metadata.py` — 16 tests
- **Module**: `utils/io.py` (metadata functions)
- **Coverage**: read/write metadata round-trip, source tag preservation, override tags, saving_color_space tagging, TIFF bit depth round-trip, ICC embedding
- **Quality**: HIGH — tests real EXIF/XMP tag values

### `test_photo_params.py` — 15 tests
- **Module**: `runtime/params_schema.py`
- **Coverage**: RuntimePhotoParams construction, sub-params defaults, IOParams deprecated full_image, settings validation
- **Quality**: LOW-MEDIUM — mostly construction/smoke tests

### `test_halide_filters.py` — 14 tests
- **Module**: `gpu/halide_backend.py` (filter operations)
- **Coverage**: Halide FIR blur, IIR blur, reflect padding
- **Quality**: MEDIUM — numerical parity against CPU reference

### `test_fft_gaussian_filter.py` — 14 tests
- **Module**: `utils/fft_gaussian_filter.py`
- **Coverage**: FFT Gaussian filter vs scipy reference, edge cases
- **Quality**: MEDIUM

### `test_raw_file_processor.py` — 12 tests
- **Module**: `utils/raw_file_processor.py`
- **Coverage**: RAW file processing, various formats
- **Quality**: LOW — mostly smoke tests

### `test_profiles.py` — 12 tests
- **Module**: `profiles/io.py`
- **Coverage**: Profile load/save round-trip, validation, profile_from_dict, stock name validation
- **Quality**: MEDIUM

### `test_gpu_lut.py` — 12 tests
- **Module**: `gpu/kernels/lut.py`
- **Coverage**: 2D cubic LUT (Mitchell-Netravali), 3D trilinear LUT, 2D bilinear LUT — CPU/MLX/CuPy parity
- **Quality**: HIGH — numerical parity tests across backends

### `test_color_reference.py` — 12 tests
- **Module**: `runtime/services/color_reference.py`
- **Coverage**: Color reference service, exposure correction
- **Quality**: MEDIUM

### `test_autoexposure.py` — 12 tests
- **Module**: `utils/autoexposure.py`
- **Coverage**: Auto-exposure measurement, various methods, edge cases
- **Quality**: MEDIUM

### `test_halide_spectral.py` — 11 tests
- **Module**: `gpu/halide_backend.py` (spectral operations)
- **Coverage**: Halide density_to_light, light_to_raw, compute_density_spectral
- **Quality**: MEDIUM

### `test_halide_android.py` — 11 tests
- **Module**: `halide/android.py`
- **Coverage**: Android Halide backend availability and operations
- **Quality**: LOW — mostly availability checks

### `test_gpu_density.py` — 10 tests
- **Module**: `gpu/kernels/density.py`
- **Coverage**: Backend density spectral, density_to_light, light_to_raw, interpolate_exposure_to_density, CMY layers — CPU/MLX/CuPy parity
- **Quality**: HIGH — strict numerical parity tests (rtol/atol 1e-12)

### `test_color_management.py` — 10 tests
- **Module**: `color_management.py`
- **Coverage**: Input/output encoding mapping, ACES scene-linear contract, workflow presets, ColorEncoding validation
- **Quality**: HIGH — tests encoding invariants and ACES forcing

### `test_parametric.py` — 9 tests
- **Module**: `model/parametric.py`
- **Coverage**: Parametric density curve generation
- **Quality**: LOW

### `test_lut.py` — 9 tests
- **Module**: `utils/lut.py`
- **Coverage**: LUT generation utilities
- **Quality**: MEDIUM

### `test_pipeline_smoke.py` — 8 tests
- **Module**: `runtime/pipeline.py`
- **Coverage**: End-to-end pipeline with small images, print and scan-film paths, debug modes, soft_update
- **Quality**: MEDIUM — smoke tests, not deep correctness

### `test_grain.py` — 8 tests
- **Module**: `model/grain.py`
- **Coverage**: Grain particle model, sublayer grain, grain application to density
- **Quality**: LOW-MEDIUM — basic statistical checks

### `test_crop_resize.py` — 8 tests
- **Module**: `utils/crop_resize.py`
- **Coverage**: Crop center, resize image
- **Quality**: LOW

### `test_spectral_upsampling.py` — 7 tests
- **Module**: `utils/spectral_upsampling.py`
- **Coverage**: Hanatos2025 method, Mallett2019 method, input policy validation
- **Quality**: MEDIUM

### `test_pipeline_lut_lifecycle.py` — 7 tests
- **Module**: `runtime/services/spectral_lut_compute.py`
- **Coverage**: LUT service lifecycle, LUT caching, resolution changes
- **Quality**: MEDIUM

### `test_gpu_filters.py` — 7 tests
- **Module**: `gpu/kernels/filters.py`
- **Coverage**: Gaussian filter backend dispatch, FFT convolution, reflect padding — CPU/MLX/CuPy parity
- **Quality**: HIGH — numerical parity tests

### `test_numba_warmup.py` — 6 tests
- **Module**: `utils/numba_warmup.py`
- **Coverage**: Numba JIT warmup
- **Quality**: LOW

### `test_halide_backend.py` — 6 tests
- **Module**: `gpu/halide_backend.py`
- **Coverage**: HalideBackend init, cleanup, basic operations
- **Quality**: LOW

### `test_regression_baselines.py` — 5 tests
- **Module**: `regression_baselines.py`
- **Coverage**: Regression baseline comparisons
- **Quality**: MEDIUM

### `test_enlarger_filters.py` — 5 tests
- **Module**: `runtime/services/filter_enlarger_source.py`
- **Coverage**: Enlarger filter service
- **Quality**: LOW

### `test_couplers.py` — 5 tests
- **Module**: `model/couplers.py`
- **Coverage**: Directional couplers matrix, zero couplers, zero density, manual pipeline match
- **Quality**: MEDIUM — tests mathematical invariants

### `test_halide_lut.py` — 4 tests
- **Module**: `gpu/halide_backend.py` (LUT operations)
- **Coverage**: Halide trilinear 3D LUT, 2D cubic LUT
- **Quality**: MEDIUM

### `test_filming_stage.py` — 3 tests
- **Module**: `runtime/stages/filming.py`
- **Coverage**: Filming stage expose/develop
- **Quality**: LOW — minimal coverage

### `test_gpu_pipeline.py` — 2 tests
- **Module**: `runtime/pipeline.py` (GPU path)
- **Coverage**: MLX backend pipeline, MLX LUT pipeline
- **Quality**: LOW — only 2 tests, skipped without Metal

### `test_emulsion.py` — 2 tests
- **Module**: `model/emulsion.py`
- **Coverage**: develop() matches manual pipeline (negative + positive)
- **Quality**: MEDIUM — tests decomposition invariant

### `test_raw_smoke.py` — 1 test
- **Module**: `utils/raw_file_processor.py`
- **Coverage**: RAW smoke test
- **Quality**: LOW

### `test_gpu_validate.py` — 1 test
- **Module**: `gpu/backend.py` (validation)
- **Coverage**: GPU validation
- **Quality**: LOW

### `test_gpu_highlight_boost.py` — 1 test
- **Module**: `gpu/kernels/color.py` (highlight boost)
- **Coverage**: Backend highlight boost
- **Quality**: LOW

---

## Summary Statistics

| Category | Tests | Files |
|----------|-------|-------|
| HDR photo/export | 175 | 3 (hdr_photo, gain_map, hdr_curve_profiles) |
| GPU density/spectral | 28 | 2 (gpu_density, gpu_color_chain) |
| GPU filters/LUT | 33 | 3 (gpu_filters, gpu_lut, halide_filters) |
| Runtime pipeline | 46 | 4 (runtime_api, pipeline_smoke, gpu_pipeline, pipeline_lut) |
| Model (emulsion, grain, couplers, diffusion) | 15 | 3 (emulsion, grain, couplers) |
| Color management | 10 | 1 |
| I/O and metadata | 40 | 2 (image_io, exif_metadata) |
| Edge cases | 41 | 1 |
| Profiles | 12 | 1 |
| Halide backend | 49 | 5 (halide_backend, halide_color, halide_filters, halide_spectral, halide_lut) |
| Other | ~159 | Various |
