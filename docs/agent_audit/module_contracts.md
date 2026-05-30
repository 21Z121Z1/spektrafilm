# Module Contracts

> Generated 2026-05-28 — Phase 1 Quality Audit

---

## 1. `runtime/pipeline.py` — SimulationPipeline

### Input Types/Constraints
- `RuntimePhotoParams`: Deep-copied at init; must contain valid `Profile` instances for film and print
- `image`: `np.ndarray`, shape `(H, W, 3)` or `(H, W, 4)`, any float dtype — converted to runtime dtype
- `compute_backend`: `"auto"`, `"cpu"`, `"mlx"`, `"cupy"`, `"halide"` — float64 forces CPU

### Output Types/Guarantees
- `process()` → `np.ndarray`, shape `(H, W, 3)`, dtype = runtime float precision (default float32)
- `process_with_metadata()` → `SimulationPipelineResult(image, hdr_scene_energy)` — image same as above
- Output is always non-negative, finite, and in scene-linear or display-referred space per `IOParams`

### Invariants
- Pipeline is stateless between `process()` calls (timings cleared, backend cache cleaned)
- `_runtime_dtype` is always float32 or float64, never float16
- GPU tiling only activates when: GPU backend active, no debug mode, no stochastic effects, image > `SPEKTRAFILM_GPU_TILE_PIXELS`
- `_preprocess` always: converts to contiguous float array, strips alpha, applies auto-exposure, crops/rescales
- `_pipeline_print`: expose_film → develop_film → expose_print → develop_print → scan
- `_pipeline_scan_film`: expose_film → develop_film → scan (no print stage)
- Backend fallback: auto → MLX → CuPy → NumPy (with fallback_reason)

### Error Modes
- `TypeError` if params not `RuntimePhotoParams`
- `ValueError` if float64 requested with GPU backend
- `BackendUnavailableError` if explicit GPU backend can't initialize
- Graceful fallback to CPU for `auto` backend

### Side Effects
- Mutates `self.timings` dict during process
- Sets `self._last_elapsed_time` after each process
- GPU backends allocate/release device memory

---

## 2. `runtime/params_schema.py` — RuntimePhotoParams

### Input Types/Constraints
- `film`, `print`: Must be `Profile` instances (enforced in `__post_init__`)
- All sub-params are dataclasses with defaults
- `IOParams.output_clip_min/max`: Booleans controlling output clipping
- `SettingsParams.compute_backend`: String enum
- `SettingsParams.lut_resolution`: Positive integer

### Output Types/Guarantees
- Immutable after construction (deep-copied by pipeline)
- All fields have sensible defaults for zero-config usage

### Invariants
- `film` and `print` are always `Profile` instances
- `DiffusionFilterParams.strength` ∈ [0, ∞) (clamped by caller)
- `GrainParams.agx_particle_area_um2` > 0

### Error Modes
- `TypeError` if `film` or `print` not `Profile`

### Side Effects
- None (pure data)

---

## 3. `runtime/params_builder.py` — digest_params

### Input Types/Constraints
- `params`: `RuntimePhotoParams` — mutated in-place AND returned
- `apply_stocks_specifics`: bool — whether to apply stock-specific overrides

### Output Types/Guarantees
- Returns the same `params` object (mutated)
- Preview mode zeroes out spatial/stochastic effects
- Debug mode zeroes out spatial effects when `deactivate_spatial_effects=True`
- Halation presets applied from `(use, antihalation)` lookup table

### Invariants
- `digest_params(digest_params(p))` is idempotent (re-digesting is safe)
- Neutral print filters database lookup is silent on missing entries

### Error Modes
- `FileNotFoundError` silently caught for neutral filter database
- `UserWarning` emitted when stock-specific filters not found

### Side Effects
- Mutates `params` in-place

---

## 4. `profiles/io.py` — Profile / load_profile

### Input Types/Constraints
- `stock`: String matching `^[A-Za-z0-9_-]+$`
- Profile JSON must have `info` and `data` keys

### Output Types/Guarantees
- `Profile` with validated `ProfileInfo` and `ProfileData`
- `ProfileData` arrays are always `np.ndarray` with correct shapes
- `density_curves` shape: `(K, 3)`, `log_exposure` shape: `(K,)`, same K
- `channel_density` shape: `(N, 3)`, `wavelengths` shape: `(N,)`, same N
- `base_density` shape: `(N,)`

### Invariants
- `_validate_profile` checks all shape constraints
- Profile types: `negative` or `positive`
- Profile supports: `film` or `paper`
- Profile stages: `filming` or `printing`

### Error Modes
- `ValueError` for invalid stock name, type, support, stage, use, antihalation, channel_model
- `FileNotFoundError` for missing profile JSON
- `json.JSONDecodeError` for malformed JSON

### Side Effects
- Reads from `spektrafilm/data/profiles/` package resources

---

## 5. `gpu/backend.py` — select_backend

### Input Types/Constraints
- `name`: `"auto"`, `"cpu"`, `"mlx"`, `"cupy"`, `"cuda"`, `"halide"`
- `precision`: `"float32"` or `"float16"`

### Output Types/Guarantees
- Returns an `ArrayBackend` implementation
- `auto` prefers MLX → CuPy → NumPy fallback
- Explicit GPU names raise `BackendUnavailableError` on failure
- `cpu` always succeeds

### Invariants
- `backend.supports_gpu` is True for MLX, CuPy, Halide; False for NumPy
- `backend.requires_serial_runtime` is True for MLX and Halide
- All backends implement the full `ArrayBackend` protocol

### Error Modes
- `BackendUnavailableError` for explicit GPU backend failures
- `ValueError` for invalid backend name

### Side Effects
- MLX/Metal probe allocates a test array

---

## 6. `model/emulsion.py` — develop

### Input Types/Constraints
- `log_raw`: `(H, W, 3)` float array
- `density_curves`: `(K, 3)` float array
- `density_curves_layers`: `(K, 3, 3)` float array
- `pixel_size_um`: positive float
- `profile_type`: `"negative"` or `"positive"`

### Output Types/Guarantees
- Returns `(H, W, 3)` density CMY array
- Density values are non-negative for negative film

### Invariants
- `develop_simple` → `apply_dir_couplers` → `apply_grain` ordering
- Grain bypassed when GPU backend active and grain inactive
- Density curves normalized to non-negative before interpolation

### Error Modes
- Interpolation extrapolation clamped to curve endpoints

### Side Effects
- Grain uses random number generation (seeded or unseeded)

---

## 7. `model/diffusion.py` — apply_diffusion_filter_um

### Input Types/Constraints
- `image`: `(H, W, 3)` float array
- `diffusion_filter`: `DiffusionFilterParams` dataclass
- `pixel_size_um`: positive float

### Output Types/Guarantees
- Returns `(H, W, 3)` filtered image, same dtype
- Energy-conserving: output integrates ≈ input energy

### Invariants
- PSF is per-channel (halo warmth redistributes R/G/B differently)
- `p_s` (deflected fraction) ∈ [0, 0.99]
- Kernel radius = `8 * bloom_max_lambda_um * spatial_scale / pixel_size_um`
- Family ∈ {glimmerglass, black_pro_mist, pro_mist, cinebloom}

### Error Modes
- `ValueError` for unknown filter family
- Graceful no-op when strength ≤ 0 or inactive

### Side Effects
- FFT convolution allocates temporary arrays

---

## 8. `model/grain.py` — apply_grain

### Input Types/Constraints
- `density_cmy`: `(H, W, 3)` float array
- `grain`: `GrainParams` dataclass
- `density_curves`: `(K, 3)` for max density lookup

### Output Types/Guarantees
- Returns `(H, W, 3)` density with grain noise added
- Grain is stochastic — different seeds produce different results

### Invariants
- No-op when `grain.active = False` or `bypass_grain = True`
- Sublayer model uses 3 sublayers by default
- Micro-structure applies multiplicative lognormal clumping
- Final blur applied after grain composition

### Error Modes
- Graceful no-op on inactive/bypass

### Side Effects
- Calls `np.random` (legacy) for fast_stats path — saves/restores global state

---

## 9. `utils/io.py` — save_image_oiio

### Input Types/Constraints
- `filename`: Path with supported extension (jpg, png, tif, exr, heic, heif)
- `image_data`: `(H, W, 3)` float array
- `bit_depth`: 8, 16, 32 (format-dependent defaults)
- `color_space`: Optional colour space name for ICC embedding

### Output Types/Guarantees
- Returns `tuple[str, ...]` of HDR diagnostics (empty for standard formats)
- File written to disk with correct format/precision
- ICC profile embedded when available

### Invariants
- JPEG/PNG always clipped to [0, 1]
- EXR never clipped
- TIFF supports 8/16/32 bit with ZIP compression
- HEIC/HEIF requires linear, unclipped, explicit encoding
- HDR rendition EXR applies paper rolloff + diffuse lift before writing

### Error Modes
- `ValueError` for unsupported extension, encoding mismatch, empty image
- `OSError` for I/O failures
- `HDRPhotoExportError` for macOS-only HEIC path

### Side Effects
- Writes file to disk
- Reads ICC profiles from package resources
- HEIC export invokes Swift subprocess (macOS only)

---

## 10. `utils/hdr_photo.py` — HDRPhotoMapping / prepare_hdr_photo_renditions

### Input Types/Constraints
- `image_data`: `(H, W, 3)` float32 linear RGB, finite, non-empty
- `mapping`: `HDRPhotoMapping` with extensive validation in `__post_init__`
- `scene_luminance`: `(H, W)` float32, finite, non-negative

### Output Types/Guarantees
- `HDRPhotoRenditions`: hdr_rgb (0 to headroom), sdr_rgb (0 to 1), headroom ≥ 1.01
- Profile-aware mode requires valid increasing curve profile

### Invariants
- `preserve_sdr_base=True` (default): SDR base = clipped original look
- `preserve_sdr_base=False`: SDR base = tone-mapped via logistic/logarithmic rolloff
- Headroom computed from content percentile, clamped to max_headroom
- Gamut mapping: luma-preserving or Oklch perceptual

### Error Modes
- `ValueError` for headroom < 1.01, invalid mapping parameters, missing scene luminance
- `HDRPhotoExportError` for platform-specific encoder failures

### Side Effects
- HEIC export writes to temp directory, invokes Swift subprocess

---

## 11. `utils/gain_map.py` — ISO 21496-1 Gain Map

### Input Types/Constraints
- `baseline`, `alternate`: Same-shape float32 arrays
- `g_min`, `g_max`: Float bounds from normalization
- `gamma`: Encoding gamma exponent

### Output Types/Guarantees
- `compute_gain_map` → float32 log2 gain
- `normalize_gain_map` → [0, 1] float32 + min/max metadata
- `apply_gain_map` → reconstructed alternate, non-negative float32
- `compute_weight` → [0, 1] or [-1, 0] float

### Invariants
- Round-trip: `denormalize(normalize(g))` ≈ `g` (within float32 precision)
- `apply_gain_map` with h_target = h_alternate reconstructs full HDR
- `apply_gain_map` with h_target = h_baseline returns baseline (no gain)

### Error Modes
- `ValueError` for shape mismatch

### Side Effects
- None (pure computation)
