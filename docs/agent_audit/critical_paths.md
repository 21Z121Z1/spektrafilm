# Critical Paths

> Generated 2026-05-28 — Phase 1 Quality Audit

---

## 1. Main Processing Pipeline

**Path**: Input RGB → Spectral Upsampling → Film Exposure → Film Development → Print Exposure → Print Development → Scanning → Output RGB

```
simulate(image, params)
  └─ Simulator.process(image)
       └─ SimulationPipeline._pipeline(image)
            ├─ _preprocess(image)
            │    ├─ np.ascontiguousarray + dtype cast + strip alpha
            │    ├─ auto_exposure_with_ev (FilmingStage)
            │    └─ crop_and_rescale (ResizingService)
            ├─ _preprocess_input_image_with_metadata [if HDR metadata requested]
            │    └─ _hdr_scene_energy_metadata (luminance, diffuse_white, headroom)
            └─ _process_runtime_array(preprocessed)
                 ├─ [print path] _pipeline_print
                 │    ├─ FilmingStage.expose
                 │    │    ├─ _rgb_to_film_raw (hanatos2025 or mallett2019 spectral upsampling)
                 │    │    ├─ exposure_compensation_ev
                 │    │    ├─ boost_highlights (halation highlight boost)
                 │    │    ├─ apply_diffusion_filter_um (camera diffusion)
                 │    │    ├─ apply_gaussian_blur_um (camera lens blur)
                 │    │    ├─ apply_halation_um (scatter + back-reflection)
                 │    │    └─ log10(raw + eps)
                 │    ├─ FilmingStage.develop
                 │    │    ├─ interpolate_exposure_to_density (density curves)
                 │    │    ├─ apply_density_correction_dir_couplers
                 │    │    └─ apply_grain (stochastic, CPU-only)
                 │    ├─ PrintingStage.expose
                 │    │    ├─ _film_cmy_to_print_log_raw (spectral: CMY→density→light→raw)
                 │    │    ├─ print_exposure * exposure_correction
                 │    │    ├─ apply_diffusion_filter_um (enlarger diffusion)
                 │    │    └─ log10(raw + eps)
                 │    ├─ PrintingStage.develop
                 │    │    └─ interpolate_exposure_to_density (print density curves)
                 │    └─ ScanningStage.scan
                 │         ├─ cmy_to_log_xyz (spectral: CMY→density→light→XYZ)
                 │         ├─ XYZ_to_RGB (colour space conversion)
                 │         ├─ apply_gaussian_blur (scanner lens blur)
                 │         ├─ apply_unsharp_mask
                 │         ├─ black/white level correction
                 │         └─ CCTF encoding (if output_encoding.is_cctf_encoded)
                 └─ [scan-film path] _pipeline_scan_film
                      ├─ FilmingStage.expose
                      ├─ FilmingStage.develop
                      └─ ScanningStage.scan
```

**Key dependencies**: `colour` library for RGB↔XYZ transforms, spectral upsampling LUTs, density curve interpolation

**Critical invariant**: Output must be finite, non-negative, and within encoding bounds

---

## 2. HDR Processing Path

**Path**: Linear scene RGB → Scene luminance → Paper rolloff / Diffuse lift → HDR gain → Gamut mapping → SDR+HDR renditions → Gain map → HEIC/EXR export

```
save_image_oiio(filename, image, exr_mode="hdr_rendition")
  └─ prepare_hdr_photo_renditions(image, mapping, scene_luminance)
       ├─ [generic mode]
       │    ├─ _graft_scene_luminance (scene_y → diffuse lift → specular rolloff → merge)
       │    │    ├─ _prepare_scene_luminance (validate + normalize)
       │    │    ├─ _paper_logistic_progress / _paper_logarithmic_progress
       │    │    └─ smoothstep graft weighting
       │    └─ _content_headroom (percentile-based)
       └─ [profile_aware mode]
            ├─ _resolve_curve_profile (film+paper → curve profile)
            ├─ build_profile_preserving_hdr_curve / build_dynamic_curve_profile
            ├─ _apply_hdr_color_recovery
            │    ├─ [off] look * gain
            │    ├─ [source_chroma] chroma from scene_rgb * h_profile
            │    ├─ [bounded_look_chroma] saturation boost in highlights
            │    ├─ _smoothstep path_to_white desaturation
            │    └─ gamut_map_oklch / luma_preserving compression
            └─ _content_headroom

save_hdr_photo_heic(filename, image, mapping, color_space)
  └─ prepare_hdr_photo_renditions(...)
  └─ _rgba_float_payload (SDR + HDR)
  └─ Swift/CoreImage encoder subprocess (macOS only)

save_gain_map_jpeg / save_gain_map_heif
  └─ compute_gain_map (log2 gain)
  └─ normalize_gain_map ([0,1] + metadata)
  └─ JPEG MPF / HEIF container assembly
```

**Key files**: `utils/hdr_photo.py` (1387 LOC), `utils/hdr_curve_profiles.py` (1049 LOC), `utils/gain_map.py`, `utils/gain_map_io.py`

**Critical invariant**: `headroom >= 1.01` (MIN_HDR_PHOTO_HEADROOM), SDR base ∈ [0, 1], HDR ∈ [0, headroom]

---

## 3. Color Management Path

**Path**: Input ICC/EXR metadata → ColorEncoding → Pipeline I/O encoding → Output ICC embedding

```
load_image_payload(filename)
  └─ load_image_oiio (pixel data)
  └─ read_image_color_encoding
       ├─ _known_color_space_from_oiio (oiio:ColorSpace attribute)
       ├─ _known_encoding_from_icc_profile (ICC byte matching)
       └─ _known_color_space_from_chromaticities (EXR chromaticities)
       → ColorEncoding(color_space, transfer, role, clip_negatives, clip_highlights)

SimulationPipeline.__init__
  └─ output_encoding_from_io(io) → ColorEncoding

ScanningStage.scan
  └─ [if cctf_encoded] cctf_encoding_backend(rgb, color_space, backend)

save_image_oiio
  └─ [if color_space] resolve_icc_profile_bytes → embed ICC
  └─ write_image_metadata → EXIF ColorSpace + Xmp.photoshop.ICCProfile

apply_color_management_workflow_to_io(io, workflow)
  └─ [manual] no-op
  └─ [aces_reference] forces ACEScg in/out, ACES2065-1 saving
```

**ICC profile registry**: `_ICC_FILENAMES` maps `(color_space, cctf_encoding)` → bundled ICC path
**Supported spaces**: sRGB, Display P3, DCI-P3, Adobe RGB, ProPhoto RGB, BT.2020, ACES2065-1, ACEScg

**Critical invariant**: ACES spaces always force linear transfer, unclipped

---

## 4. GPU vs CPU Execution Paths

**Path**: Backend selection → ArrayBackend protocol → Kernel dispatch

```
select_backend("auto")
  ├─ try MlxBackend (requires mlx + Metal)
  ├─ try CupyBackend (requires cupy + CUDA/ROCm)
  └─ fallback NumpyBackend (always succeeds)

SimulationPipeline._runtime_array(image)
  └─ [if supports_gpu] backend.asarray(image)
  └─ [else] np.asarray(image, dtype=runtime_dtype)

Kernel dispatch pattern (example: gaussian_filter_backend):
  ├─ [CPU] fast_gaussian_filter (Numba FIR/IIR)
  ├─ [CuPy] cupyx.scipy.ndimage.gaussian_filter
  ├─ [MLX] custom Metal kernels (FIR for small σ, YVV IIR for large σ)
  └─ [Halide] custom Halide JIT (FIR, YVV IIR via NumPy fallback)
```

**GPU-specific paths**:
- **MLX**: Custom Metal kernels for density interpolation, Gaussian blur (FIR + IIR), LUT sampling
- **CuPy**: CuPy-native ops + cupyx.scipy for filtering
- **Halide**: JIT-compiled kernels for trilinear 3D LUT, RGB matrix, spectral ops, FIR blur, CCTF, interpolation; NumPy fallback for IIR

**Critical invariant**: GPU output must be numerically identical to CPU within float32 epsilon (atol=1e-6 per CLAUDE.md)

**GPU tiling**: Large images split into overlapping tiles when `SPEKTRAFILM_GPU_TILE_PIXELS` exceeded; overlap computed from maximum kernel radius

---

## 5. External File I/O Paths

### Image Loading
```
load_image_oiio(filename)
  └─ OpenImageIO ImageInput.open → read_image → normalize to [0,1] float
  Supported: JPEG, PNG (8/16-bit), TIFF (8/16/32-bit), EXR (half/float), HEIF

load_image_payload(filename)
  └─ load_image_oiio + read_image_color_encoding + read_image_metadata
```

### Image Saving
```
save_image_oiio(filename, image)
  ├─ JPEG: uint8, clipped [0,1], ICC via APP2
  ├─ PNG: uint16, clipped [0,1], ICC via iCCP
  ├─ TIFF: 8/16/32-bit, ZIP compression, ICC via tag
  ├─ EXR: half/float, no clip, chromaticities + colorInteropID
  ├─ HEIC/HEIF: macOS Swift/CoreImage encoder (gain map HDR)
  └─ HDR rendition EXR: apply HDR mapping, write with whiteLuminance + hdrHeadroom
```

### Profile I/O
```
load_profile(stock)
  └─ importlib.resources → spektrafilm/data/profiles/{stock}.json
  └─ JSON parse → profile_from_dict → _validate_profile

save_profile(profile)
  └─ profile_to_dict → _json_safe → json.dump → spektrafilm/data/profiles/{stock}.json
```

### Filter/Illuminant Data
```
load_filter(wavelengths, name, brand, filter_type)
  └─ spektrafilm/data/filters/{filter_type}/{brand}/{name}.csv

standard_illuminant(name)
  └─ spektrafilm/data/illuminants/{name}.csv

read_neutral_print_filters()
  └─ spektrafilm/data/filters/neutral_print_filters.json
```

### Metadata I/O
```
read_image_metadata(filename) → exiv2.ImageFactory.open → EXIF/IPTC/XMP
write_image_metadata(filename, source_metadata)
  └─ exiv2: copy source tags + override Orientation/DateTime/Software/dimensions
  └─ EXIF ColorSpace + Xmp.photoshop.ICCProfile for color space tagging
```

### Gain Map I/O
```
save_gain_map_jpeg(output_path, base, gain_map, metadata)
  └─ PIL JPEG encode → MPF APP2 assembly → ISO 21496-1 binary metadata

save_gain_map_heif(output_path, base, gain_map, metadata)
  └─ pillow-heif encode → ISOBMFF tmap brand patch

load_gain_map(path)
  └─ JPEG: APP2 segment parsing → MPF extraction → metadata deserialization
  └─ HEIF: pillow-heif open → second image = gain map
```

**Critical invariants**:
- ICC profile preserved through metadata write (verified by byte comparison)
- HEIC export requires macOS + Swift toolchain
- Profile names validated against `^[A-Za-z0-9_-]+$` regex
- All file I/O uses absolute paths or package resources
