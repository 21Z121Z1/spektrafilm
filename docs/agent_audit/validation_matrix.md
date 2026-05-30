# Validation Matrix

> Generated 2026-05-28 — Phase 1 Quality Audit

Each contract/invariant from `module_contracts.md` is mapped to the tests that validate it.

---

## 1. SimulationPipeline Contracts

| Contract | Validating Tests | Status |
|----------|-----------------|--------|
| process() returns (H,W,3) finite non-negative | `test_pipeline_smoke.py::test_pipeline_processes_small_image` | COVERED |
| Runtime dtype is float32 or float64 | `test_pipeline_smoke.py` (implicit) | WEAK |
| GPU tiling only activates with GPU + no debug + no stochastic | `test_gpu_pipeline.py::test_pipeline_processes_small_image_with_mlx_backend` | WEAK |
| Backend auto fallback: MLX → CuPy → NumPy | `test_gpu_backend.py::test_select_backend_auto_fallback_*` | COVERED |
| float64 forces CPU | `test_gpu_backend.py` (implicit) | WEAK |
| Timings cleared on each process() | Not tested | **UNTESTED** |
| Backend cache cleaned after process() | Not tested | **UNTESTED** |
| Debug mode routing (output/inject/off) | `test_pipeline_smoke.py::test_pipeline_debug_*` | COVERED |
| soft_update mutates specific fields | `test_runtime_api.py::test_simulator_soft_update_*` | COVERED |

## 2. RuntimePhotoParams Contracts

| Contract | Validating Tests | Status |
|----------|-----------------|--------|
| film/print must be Profile instances | `test_photo_params.py` | COVERED |
| All sub-params have defaults | `test_photo_params.py::test_default_params_construction` | COVERED |
| DiffusionFilterParams defaults are sensible | `test_edge_cases.py` (implicit) | WEAK |

## 3. digest_params Contracts

| Contract | Validating Tests | Status |
|----------|-----------------|--------|
| Idempotent re-digestion | Not explicitly tested | **UNTESTED** |
| Preview mode zeroes spatial/stochastic effects | `test_runtime_api.py::test_digest_params_preview_mode` | COVERED |
| Debug mode zeroes spatial effects | `test_runtime_api.py::test_digest_params_debug_*` | COVERED |
| Halation presets from (use, antihalation) | `test_runtime_api.py` (implicit) | WEAK |
| Neutral filter database silent on missing | `test_runtime_api.py` (implicit) | WEAK |

## 4. Profile I/O Contracts

| Contract | Validating Tests | Status |
|----------|-----------------|--------|
| load_profile validates shape constraints | `test_profiles.py::test_load_profile_*` | COVERED |
| Stock name regex `^[A-Za-z0-9_-]+$` | `test_profiles.py::test_validate_stock_name_*` | COVERED |
| Profile type ∈ {negative, positive} | `test_profiles.py::test_validate_profile_type` | COVERED |
| JSON round-trip | `test_profiles.py::test_profile_round_trip` | COVERED |
| Missing profile raises FileNotFoundError | `test_profiles.py::test_load_missing_profile` | COVERED |

## 5. Backend Selection Contracts

| Contract | Validating Tests | Status |
|----------|-----------------|--------|
| CPU backend always succeeds | `test_gpu_backend.py::test_select_backend_cpu` | COVERED |
| Explicit GPU raises BackendUnavailableError on failure | `test_gpu_backend.py::test_select_backend_*_raises` | COVERED |
| auto prefers MLX → CuPy → NumPy | `test_gpu_backend.py::test_select_backend_auto_*` | COVERED |
| Backend protocol compliance | `test_gpu_backend.py::test_numpy_backend_protocol` | COVERED |

## 6. Emulsion/Development Contracts

| Contract | Validating Tests | Status |
|----------|-----------------|--------|
| develop() = develop_simple + dir_couplers + grain | `test_emulsion.py::test_top_level_develop_matches_manual_pipeline` | COVERED |
| Density curves normalized to non-negative | `test_emulsion.py` (implicit) | WEAK |
| Grain bypassed on GPU when inactive | `test_gpu_density.py` (implicit) | WEAK |
| Dir couplers zero → identity | `test_couplers.py::test_zero_couplers_returns_original_curves` | COVERED |
| Dir couplers matrix diagonal when no interlayer | `test_couplers.py::test_no_interlayer_inhibition_is_diagonal` | COVERED |

## 7. Diffusion Filter Contracts

| Contract | Validating Tests | Status |
|----------|-----------------|--------|
| Energy conservation (output ≈ input energy) | Not tested | **UNTESTED** |
| No-op when inactive or strength ≤ 0 | `test_edge_cases.py` (implicit) | WEAK |
| Family ∈ {glimmerglass, black_pro_mist, pro_mist, cinebloom} | `test_edge_cases.py` (implicit) | WEAK |
| PSF per-channel (halo warmth) | Not tested | **UNTESTED** |
| Kernel radius = 8 * lambda_max | Not tested | **UNTESTED** |

## 8. Grain Contracts

| Contract | Validating Tests | Status |
|----------|-----------------|--------|
| No-op when inactive/bypass | `test_grain.py::test_grain_inactive_*` | COVERED |
| Sublayer model uses 3 sublayers | `test_grain.py` (implicit) | WEAK |
| Micro-structure multiplicative | Not tested | **UNTESTED** |
| RNG state save/restore for fast_stats | Not tested | **UNTESTED** |

## 9. Image I/O Contracts

| Contract | Validating Tests | Status |
|----------|-----------------|--------|
| JPEG clipped to [0,1] uint8 | `test_exif_metadata.py` (implicit) | WEAK |
| PNG uint16, clipped [0,1] | `test_image_io_color_metadata.py` (implicit) | WEAK |
| EXR no clip, half/float | `test_image_io_color_metadata.py` (implicit) | WEAK |
| TIFF 8/16/32-bit with ZIP | `test_exif_metadata.py::test_save_image_oiio_tiff_bit_depths_roundtrip` | COVERED |
| ICC profile embedded when available | `test_exif_metadata.py::test_save_image_oiio_embeds_icc_profile_when_available` | COVERED |
| ICC profile skipped when missing | `test_exif_metadata.py::test_save_image_oiio_skips_icc_when_profile_missing` | COVERED |
| Metadata write preserves ICC bytes | `test_exif_metadata.py::test_write_metadata_carries_source_tags_*` | COVERED |
| Color space tagging in EXIF/XMP | `test_exif_metadata.py::test_write_metadata_records_saving_color_space` | COVERED |
| HEIC requires linear, unclipped, explicit encoding | Not tested on Linux | **PLATFORM-DEPENDENT** |

## 10. HDR Photo Contracts

| Contract | Validating Tests | Status |
|----------|-----------------|--------|
| HDRPhotoMapping __post_init__ validation (40+ fields) | `test_hdr_photo.py::TestHDRPhotoMapping*` (40+ tests) | COVERED |
| headroom ≥ 1.01 | `test_hdr_photo.py::test_prepare_renditions_*` | COVERED |
| preserve_sdr_base=True: SDR = clipped look | `test_hdr_photo.py::test_sdr_base_preserves_look` | COVERED |
| preserve_sdr_base=False: SDR = tone-mapped | `test_hdr_photo.py::test_sdr_base_tone_mapped` | COVERED |
| Paper rolloff logistic | `test_hdr_photo.py::test_paper_rolloff_logistic_*` | COVERED |
| Paper rolloff logarithmic | `test_hdr_photo.py::test_paper_rolloff_logarithmic_*` | COVERED |
| Profile-aware mode requires scene_luminance | `test_hdr_photo.py::test_profile_aware_requires_luminance` | COVERED |
| Profile-aware mode requires increasing curve | `test_hdr_photo.py::test_profile_aware_requires_safe_curve` | COVERED |
| Oklch gamut mapping | `test_hdr_photo.py::test_gamut_map_oklch_*` | COVERED |
| Diffuse lift | `test_hdr_photo.py::test_diffuse_lift_*` | COVERED |
| Path-to-white desaturation | `test_hdr_photo.py::test_path_to_white_*` | COVERED |
| Highlight color modes (off/source_chroma/bounded) | `test_hdr_photo.py::test_highlight_color_mode_*` | COVERED |
| ISO 21496-1 metadata construction | `test_hdr_photo.py::test_build_iso_21496_1_gain_map_metadata` | COVERED |
| macOS HEIC encoder invocation | Not testable on Linux | **PLATFORM-DEPENDENT** |

## 11. Gain Map Contracts

| Contract | Validating Tests | Status |
|----------|-----------------|--------|
| Round-trip: denormalize(normalize(g)) ≈ g | `test_gain_map.py::test_normalize_denormalize_round_trip` | COVERED |
| apply with h_target=h_alternate → full HDR | `test_gain_map.py::test_apply_gain_map_full_headroom` | COVERED |
| apply with h_target=h_baseline → baseline | `test_gain_map.py::test_apply_gain_map_no_gain` | COVERED |
| Weight factor ∈ [0,1] or [-1,0] | `test_gain_map.py::test_compute_weight_*` | COVERED |
| JPEG MPF save/load round-trip | `test_gain_map.py::test_save_load_jpeg_round_trip` | COVERED |
| Metadata binary serialization round-trip | `test_gain_map.py::test_gain_map_metadata_*` | COVERED |
| XMP packet generation | `test_gain_map.py::test_build_gain_map_xmp_packet` | COVERED |

## 12. Color Management Contracts

| Contract | Validating Tests | Status |
|----------|-----------------|--------|
| ACES spaces force linear + unclipped | `test_color_management.py::test_aces_io_encodings_force_scene_linear_unclipped_contract` | COVERED |
| Input encoding maps cctf_decoding → transfer | `test_color_management.py::test_input_encoding_from_io_*` | COVERED |
| Output encoding maps SDR/HDR contracts | `test_color_management.py::test_output_encoding_from_io_*` | COVERED |
| ColorEncoding rejects unknown color space | `test_color_management.py::test_color_encoding_rejects_unknown_color_space` | COVERED |
| ACES reference workflow sets correct contracts | `test_color_management.py::test_aces_reference_workflow_*` | COVERED |
| Manual workflow leaves IO unchanged | `test_color_management.py::test_manual_color_management_workflow_*` | COVERED |

## 13. GPU Parity Contracts

| Contract | Validating Tests | Status |
|----------|-----------------|--------|
| Density spectral CPU = NumPy backend (1e-12) | `test_gpu_density.py::test_density_spectral_backend_matches_cpu_reference` | COVERED |
| Density-to-light CPU = NumPy backend (1e-12) | `test_gpu_density.py::test_density_to_light_and_light_to_raw_match_cpu_reference` | COVERED |
| Interpolate exposure→density CPU = NumPy (1e-12) | `test_gpu_density.py::test_interpolate_exposure_to_density_backend_matches_cpu_reference` | COVERED |
| Interpolate CMY layers CPU = NumPy (1e-12) | `test_gpu_density.py::test_interpolate_density_cmy_layers_backend_matches_cpu_reference` | COVERED |
| Interpolate CMY layers MLX = CPU (2e-6) | `test_gpu_density.py::test_interpolate_density_cmy_layers_mlx_matches_cpu_reference_when_available` | COVERED |
| Interpolate exposure→density CuPy = CPU (2e-6) | `test_gpu_density.py::test_interpolate_exposure_to_density_cupy_matches_cpu_reference_when_available` | COVERED |
| Gaussian filter small MLX = CPU (3e-5) | `test_gpu_filters.py::test_gaussian_filter_small_mlx_matches_cpu_reference_when_available` | COVERED |
| Gaussian filter large MLX = CPU (5e-4) | `test_gpu_filters.py::test_gaussian_filter_large_mlx_matches_cpu_reference_when_available` | COVERED |
| FFT convolution CuPy = scipy (2e-6) | `test_gpu_filters.py::test_fft_convolve_same_cupy_matches_scipy_reference_when_available` | COVERED |
| 2D cubic LUT MLX = CPU | `test_gpu_lut.py::test_apply_lut_cubic_2d_mlx_matches_cpu` | COVERED |
| 3D trilinear LUT MLX = CPU | `test_gpu_lut.py::test_apply_lut_trilinear_3d_mlx_matches_cpu` | COVERED |
| Halide 3D LUT = NumPy | `test_halide_lut.py::test_halide_trilinear_3d_matches_numpy` | COVERED |
| Halide RGB matrix = NumPy | `test_halide_color.py::test_halide_rgb_to_xyz_*` | COVERED |
| Halide spectral ops = NumPy | `test_halide_spectral.py::test_halide_density_to_light_*` | COVERED |

---

## UNTESTED High-Risk Behavior

### Critical
1. **Pipeline timing/backend cleanup after exceptions** — If process() throws, backend cache may leak
2. **Energy conservation in diffusion filter** — No test verifies output integrates ≈ input
3. **Grain RNG state save/restore** — fast_stats path modifies global np.random state
4. **GPU tiling overlap correctness** — No test verifies seamless tile boundaries

### High
5. **digest_params idempotency** — No explicit test that re-digesting is safe
6. **Pipeline soft_update print balance invalidation** — Complex interaction between exposure_compensation and density_spectral_midgray
7. **Diffusion PSF per-channel normalization** — Halo warmth redistribution not tested for energy preservation
8. **HDR rendition EXR round-trip** — save_hdr_rendition_exr not tested (was the C1 fix)

### Medium
9. **Large image GPU tiling** — No test with image > SPEKTRAFILM_GPU_TILE_PIXELS
10. **Concurrent Simulator access** — Metal serialization lock not tested under contention
11. **Preview mode completeness** — Not all spatial effects verified as zeroed
12. **Profile-aware HDR with dynamic curves** — build_dynamic_curve_profile path undertested

---

## Tests That Only Test Happy Paths

| Test File | Issue |
|-----------|-------|
| `test_pipeline_smoke.py` | Only tests small 4×4 images, no edge cases (empty, single pixel, very large) |
| `test_filming_stage.py` | Only 3 tests, all happy-path with default params |
| `test_grain.py` | No tests for extreme density values, zero particle area, or negative uniformity |
| `test_parametric.py` | No edge cases for parametric curves |
| `test_raw_smoke.py` | Single smoke test, no error cases |
| `test_gpu_validate.py` | Single test, no validation failure paths |
| `test_gpu_highlight_boost.py` | Single test, no edge cases (zero boost, negative threshold) |
| `test_halide_backend.py` | No error path tests (invalid inputs, shape mismatches) |
| `test_halide_android.py` | Mostly availability checks, no functional edge cases |
