# Public API Contracts

> Auto-generated audit of every public function, class, and CLI entry point in
> `spektrafilm` (v0.3.1). Source snapshot: branch `audit/upstream-baseline-20260528`.

---

## 1. CLI Entry Point

Defined in `pyproject.toml`:

```
[project.scripts]
spektrafilm = "spektrafilm_gui.app:main"
```

### `spektrafilm_gui.app:main`

| Field | Value |
|-------|-------|
| File:line | `src/spektrafilm_gui/app.py:310` |
| Signature | `def main() -> None` |
| Docstring | *(none)* |
| Notes | Launches napari viewer with full GUI. Calls `create_app()` then `napari.run()`. |

---

## 2. Package `spektrafilm` (top-level)

**`src/spektrafilm/__init__.py`** re-exports:

```python
__all__ = [
    "load_profile",
    "save_profile",
    "RuntimePhotoParams",
    "init_params",
    "digest_params",
    "Simulator",
    "simulate",
    "simulate_preview",
    "AgXPhoto",       # legacy for ART
    "photo_params",   # legacy for ART
]
```

---

## 3. Module `spektrafilm.profiles.io`

**File:** `src/spektrafilm/profiles/io.py`

### Constants

| Name | Type | Description |
|------|------|-------------|
| `PROFILE_TYPES` | `frozenset[str]` | `{'negative', 'positive'}` |
| `PROFILE_SUPPORTS` | `frozenset[str]` | `{'film', 'paper'}` |
| `PROFILE_STAGES` | `frozenset[str]` | `{'filming', 'printing'}` |
| `PROFILE_USES` | `frozenset[str]` | `{'still', 'cine'}` |
| `PROFILE_ANTIHALATION` | `frozenset[str]` | `{'strong', 'weak', 'no'}` |
| `PROFILE_CHANNEL_MODELS` | `frozenset[str]` | `{'color', 'bw'}` |

### Classes

#### `ProfileInfo` (dataclass)

| Field | Type | Default |
|-------|------|---------|
| `stock` | `str` | `''` |
| `name` | `str` | `''` |
| `type` | `str` | `'negative'` |
| `support` | `str` | `'film'` |
| `stage` | `str` | `'filming'` |
| `use` | `str` | `'still'` |
| `antihalation` | `str` | `'weak'` |
| `target_print` | `str \| None` | `None` |
| `channel_model` | `str` | `'color'` |
| `densitometer` | `str` | `'status_M'` |
| `log_sensitivity_density_over_min` | `float` | `0.2` |
| `reference_illuminant` | `str` | `'D55'` |
| `viewing_illuminant` | `str` | `'D50'` |
| `fitted_cmy_midscale_neutral_density` | `Any` | `None` |
| `log_exposure_midscale_neutral` | `Any` | `None` |

Properties: `is_positive`, `is_negative`, `is_paper`, `is_film`, `is_color`, `is_bw`, `is_filming`, `is_printing`, `is_still`, `is_cine` (all `-> bool`).

#### `ProfileData` (dataclass)

| Field | Type | Default |
|-------|------|---------|
| `wavelengths` | `np.ndarray` | empty float64 vector |
| `log_sensitivity` | `np.ndarray` | empty (0,3) matrix |
| `bandpass_hanatos2025` | `np.ndarray` | empty (0,3) matrix |
| `hanatos2025_adaptation_bandpass_params` | `np.ndarray` | empty vector |
| `hanatos2025_adaptation_surface_params` | `np.ndarray` | empty vector |
| `channel_density` | `np.ndarray` | empty (0,3) matrix |
| `base_density` | `np.ndarray` | empty vector |
| `midscale_neutral_density` | `np.ndarray` | empty vector |
| `log_exposure` | `np.ndarray` | empty vector |
| `density_curves` | `np.ndarray` | empty (0,3) matrix |
| `density_curves_layers` | `np.ndarray` | empty (0,3,3) tensor |

#### `Profile` (dataclass)

| Field | Type | Default |
|-------|------|---------|
| `info` | `ProfileInfo` | `ProfileInfo()` |
| `data` | `ProfileData` | `ProfileData()` |

Methods:
- `clone(self) -> Profile`
- `update_info(self, **changes) -> Profile`
- `update_data(self, **changes) -> Profile`
- `update(self, *, info=None, data=None) -> Profile`

Properties: same as `ProfileInfo` (delegates to `self.info`).

### Functions

| Function | Signature | Re-exported via `__init__.py` |
|----------|-----------|-------------------------------|
| `profile_from_dict` | `(data: Any) -> Profile` | No |
| `profile_to_dict` | `(data) -> dict` | No |
| `save_profile` | `(profile: Profile, suffix: str = '') -> None` | **Yes** (`spektrafilm`, `spektrafilm.runtime`) |
| `load_profile` | `(stock: str) -> Profile` | **Yes** (`spektrafilm`, `spektrafilm.runtime`) |
| `load_processed_profile` | alias for `load_profile` | **Yes** (`spektrafilm.profiles`) |
| `save_processed_profile` | alias for `save_profile` | **Yes** (`spektrafilm.profiles`) |

---

## 4. Module `spektrafilm.runtime.params_schema`

**File:** `src/spektrafilm/runtime/params_schema.py`

### Dataclasses (all fields with defaults)

#### `DiffusionFilterParams`

| Field | Type | Default |
|-------|------|---------|
| `active` | `bool` | `False` |
| `filter_family` | `str` | `"black_pro_mist"` |
| `strength` | `float` | `0.5` |
| `spatial_scale` | `float` | `1.0` |
| `halo_warmth` | `float` | `0.0` |
| `core_intensity` | `float` | `1.0` |
| `core_size` | `float` | `1.0` |
| `halo_intensity` | `float` | `1.0` |
| `halo_size` | `float` | `1.0` |
| `bloom_intensity` | `float` | `1.0` |
| `bloom_size` | `float` | `1.0` |

#### `CameraParams`

| Field | Type | Default |
|-------|------|---------|
| `exposure_compensation_ev` | `float` | `0.0` |
| `auto_exposure` | `bool` | `True` |
| `auto_exposure_method` | `str` | `"scene_linear"` |
| `lens_blur_um` | `float` | `0.0` |
| `film_format_mm` | `float` | `35.0` |
| `filter_uv` | `tuple[float, float, float]` | `(0.0, 410.0, 8.0)` |
| `filter_ir` | `tuple[float, float, float]` | `(0.0, 675.0, 15.0)` |
| `diffusion_filter` | `DiffusionFilterParams` | default factory |

#### `EnlargerParams`

| Field | Type | Default |
|-------|------|---------|
| `illuminant` | `str` | `"TH-KG3"` |
| `print_exposure` | `float` | `1.0` |
| `print_exposure_compensation` | `bool` | `True` |
| `normalize_print_exposure` | `bool` | `True` |
| `y_filter_shift` | `float` | `0.0` |
| `m_filter_shift` | `float` | `0.0` |
| `y_filter_neutral` | `float` | `55` |
| `m_filter_neutral` | `float` | `65` |
| `c_filter_neutral` | `float` | `0` |
| `lens_blur` | `float` | `0.0` |
| `diffusion_filter` | `DiffusionFilterParams` | default factory |
| `preflash_exposure` | `float` | `0.0` |
| `preflash_y_filter_shift` | `float` | `0.0` |
| `preflash_m_filter_shift` | `float` | `0.0` |

#### `ScannerParams`

| Field | Type | Default |
|-------|------|---------|
| `lens_blur` | `float` | `0.0` |
| `white_correction` | `bool` | `False` |
| `black_correction` | `bool` | `False` |
| `white_level` | `float` | `0.98` |
| `black_level` | `float` | `0.01` |
| `unsharp_mask` | `tuple[float, float]` | `(0.7, 0.7)` |

#### `GrainParams`

| Field | Type | Default |
|-------|------|---------|
| `active` | `bool` | `True` |
| `sublayers_active` | `bool` | `True` |
| `agx_particle_area_um2` | `float` | `0.2` |
| `agx_particle_scale` | `tuple[float, float, float]` | `(0.8, 1.0, 2.0)` |
| `agx_particle_scale_layers` | `tuple[float, float, float]` | `(2.5, 1.0, 0.5)` |
| `density_min` | `tuple[float, float, float]` | `(0.07, 0.08, 0.12)` |
| `uniformity` | `tuple[float, float, float]` | `(0.97, 0.97, 0.99)` |
| `blur` | `float` | `0.65` |
| `blur_dye_clouds_um` | `float` | `1.0` |
| `micro_structure` | `tuple[float, float]` | `(0.2, 30)` |
| `n_sub_layers` | `int` | `1` |

#### `HalationParams`

| Field | Type | Default |
|-------|------|---------|
| `active` | `bool` | `True` |
| `scatter_amount` | `float` | `1.0` |
| `scatter_spatial_scale` | `float` | `1.0` |
| `halation_amount` | `float` | `1.0` |
| `halation_spatial_scale` | `float` | `1.0` |
| `scatter_core_um` | `tuple[float, float, float]` | `(2.2, 2.0, 1.6)` |
| `scatter_tail_um` | `tuple[float, float, float]` | `(9.3, 9.7, 9.1)` |
| `scatter_tail_weight` | `tuple[float, float, float]` | `(0.78, 0.65, 0.67)` |
| `boost_ev` | `float` | `0.0` |
| `boost_range` | `float` | `0.3` |
| `protect_ev` | `float` | `4.0` |
| `halation_strength` | `tuple[float, float, float]` | `(0.05, 0.015, 0.0)` |
| `halation_first_sigma_um` | `tuple[float, float, float]` | `(65.0, 65.0, 65.0)` |
| `halation_n_bounces` | `int` | `3` |
| `halation_bounce_decay` | `float` | `0.5` |
| `halation_renormalize` | `bool` | `True` |

#### `DirCouplersParams`

| Field | Type | Default |
|-------|------|---------|
| `active` | `bool` | `True` |
| `amount` | `float` | `1.0` |
| `inhibition_samelayer` | `float` | `1.0` |
| `inhibition_interlayer` | `float` | `1.0` |
| `gamma_samelayer_rgb` | `tuple[float, float, float]` | `(0.341, 0.324, 0.273)` |
| `gamma_interlayer_r_to_gb` | `tuple[float, float]` | `(0.355, 0.305)` |
| `gamma_interlayer_g_to_rb` | `tuple[float, float]` | `(0.154, 0.358)` |
| `gamma_interlayer_b_to_rg` | `tuple[float, float]` | `(0.171, 0.225)` |
| `diffusion_size_um` | `float` | `20.0` |
| `diffusion_tail_um` | `float` | `200.0` |
| `diffusion_tail_weight` | `float` | `0.06` |

#### `GlareParams`

| Field | Type | Default |
|-------|------|---------|
| `active` | `bool` | `True` |
| `percent` | `float` | `0.03` |
| `roughness` | `float` | `0.7` |
| `blur` | `float` | `0.5` |

#### `FilmRenderingParams`

| Field | Type | Default |
|-------|------|---------|
| `density_curve_gamma` | `float` | `1.0` |
| `grain` | `GrainParams` | default factory |
| `halation` | `HalationParams` | default factory |
| `dir_couplers` | `DirCouplersParams` | default factory |
| `glare` | `GlareParams` | default factory |

#### `PrintRenderingParams`

| Field | Type | Default |
|-------|------|---------|
| `density_curve_gamma` | `float` | `1.0` |
| `glare` | `GlareParams` | default factory |

#### `IOParams`

| Field | Type | Default |
|-------|------|---------|
| `input_color_space` | `str` | `"ProPhoto RGB"` |
| `input_cctf_decoding` | `bool` | `False` |
| `output_color_space` | `str` | `"sRGB"` |
| `output_cctf_encoding` | `bool` | `True` |
| `output_clip_min` | `bool` | `True` |
| `output_clip_max` | `bool` | `True` |
| `crop` | `bool` | `False` |
| `crop_center` | `tuple[float, float]` | `(0.5, 0.5)` |
| `crop_size` | `tuple[float, float]` | `(0.1, 0.1)` |
| `upscale_factor` | `float` | `1.0` |
| `scan_film` | `bool` | `False` |

Deprecated property: `full_image` (always returns `True`, setter is no-op).

#### `DebugParams`

| Field | Type | Default |
|-------|------|---------|
| `deactivate_spatial_effects` | `bool` | `False` |
| `deactivate_stochastic_effects` | `bool` | `False` |
| `print_timings` | `bool` | `False` |
| `debug_mode` | `str` | `'off'` |
| `output_film_log_raw` | `bool` | `False` |
| `output_film_density_cmy` | `bool` | `False` |
| `output_print_density_cmy` | `bool` | `False` |
| `inject_film_density_cmy` | `bool` | `False` |

#### `SettingsParams`

| Field | Type | Default |
|-------|------|---------|
| `color_management_workflow` | `str` | `"manual"` |
| `compute_backend` | `str` | `"auto"` |
| `float_precision` | `str` | `"float32"` |
| `gpu_precision` | `str` | `"float32"` |
| `gpu_validate` | `bool` | `False` |
| `rgb_to_raw_method` | `str` | `"hanatos2025"` |
| `spectral_negative_rgb` | `str` | `"clip"` |
| `spectral_xy_out_of_bounds` | `str` | `"clip"` |
| `spectral_report_stats` | `bool` | `True` |
| `hanatos2025_sensitivity_adaptation` | `bool` | `False` |
| `bandpass_hanatos2025` | `bool` | `True` |
| `use_enlarger_lut` | `bool` | `False` |
| `use_scanner_lut` | `bool` | `False` |
| `lut_resolution` | `int` | `17` |
| `use_fast_stats` | `bool` | `False` |
| `preview_max_size` | `int` | `640` |
| `preview_mode` | `bool` | `False` |
| `neutral_print_filters_from_database` | `bool` | `True` |

#### `RuntimePhotoParams` (dataclass) — re-exported at top level

| Field | Type | Default |
|-------|------|---------|
| `film` | `Profile` | *(required)* |
| `print` | `Profile` | *(required)* |
| `film_render` | `FilmRenderingParams` | default factory |
| `print_render` | `PrintRenderingParams` | default factory |
| `camera` | `CameraParams` | default factory |
| `enlarger` | `EnlargerParams` | default factory |
| `scanner` | `ScannerParams` | default factory |
| `io` | `IOParams` | default factory |
| `debug` | `DebugParams` | default factory |
| `settings` | `SettingsParams` | default factory |

---

## 5. Module `spektrafilm.runtime.params_builder`

**File:** `src/spektrafilm/runtime/params_builder.py`

### Functions

| Function | Signature | Re-exported |
|----------|-----------|-------------|
| `apply_database_neutral_print_filters` | `(params: RuntimePhotoParams, *, database=None, warn_missing: bool = True) -> RuntimePhotoParams` | No |
| `digest_params` | `(params: RuntimePhotoParams, apply_stocks_specifics: bool = True) -> RuntimePhotoParams` | **Yes** (`spektrafilm`, `spektrafilm.runtime`, `spektrafilm.runtime.api`) |
| `init_params` | `(film_profile: str = "kodak_portra_400", print_profile: str = "kodak_portra_endura") -> RuntimePhotoParams` | **Yes** (`spektrafilm`, `spektrafilm.runtime`, `spektrafilm.runtime.api`) |

---

## 6. Module `spektrafilm.runtime.process`

**File:** `src/spektrafilm/runtime/process.py`

### Classes

#### `Simulator` — re-exported at top level

```python
class Simulator:
    def __init__(self, params: RuntimePhotoParams): ...
    def process(self, image: np.ndarray) -> np.ndarray: ...
    def process_with_metadata(self, image: np.ndarray, *, include_scene_rgb: bool = False) -> SimulationPipelineResult: ...
    def update_params(self, params: RuntimePhotoParams) -> None: ...
    def soft_update(self, **kwargs) -> None: ...
    def get_timings(self) -> dict[str, float]: ...
    def get_total_elapsed_time(self) -> float | None: ...
    def format_timings(self) -> str: ...
    def print_timings(self) -> None: ...
```

#### `AgXPhoto(Simulator)` — legacy

```python
class AgXPhoto(Simulator):
    def __init__(self, params: RuntimePhotoParams): ...
```

Auto-digests params on construction.

### Functions

| Function | Signature | Re-exported |
|----------|-----------|-------------|
| `simulate` | `(image, params: RuntimePhotoParams, digest_params_first: bool = True, print_timings: bool = False) -> np.ndarray` | **Yes** |
| `simulate_preview` | `(image, params: RuntimePhotoParams, digest_params_first: bool = True, print_timings: bool = False) -> np.ndarray` | **Yes** |
| `photo_params` | `(film_profile: str, print_profile: str) -> RuntimePhotoParams` | **Yes** (legacy) |

---

## 7. Module `spektrafilm.runtime.pipeline`

**File:** `src/spektrafilm/runtime/pipeline.py`

### Classes

#### `HDRSceneEnergyMetadata` (frozen dataclass)

| Field | Type |
|-------|------|
| `scene_luminance` | `np.ndarray` |
| `diffuse_white_estimate` | `float` |
| `headroom_estimate` | `float` |
| `auto_exposure_ev` | `float` |
| `method` | `str` |
| `confidence` | `str` |
| `profile_scene_y` | `np.ndarray \| None` |
| `profile_look_y` | `np.ndarray \| None` |
| `scene_rgb` | `np.ndarray \| None` |

#### `SimulationPipelineResult` (frozen dataclass)

| Field | Type |
|-------|------|
| `image` | `np.ndarray` |
| `hdr_scene_energy` | `HDRSceneEnergyMetadata \| None` |

#### `SimulationPipeline` (internal orchestrator)

```python
class SimulationPipeline:
    def __init__(self, params: RuntimePhotoParams, update_params: bool = False, *, _reused_lut_service: SpectralLUTService | None = None) -> None: ...
    def process(self, image: np.ndarray) -> np.ndarray: ...
    def process_with_metadata(self, image: np.ndarray, *, include_scene_rgb: bool = False) -> SimulationPipelineResult: ...
    def update(self, params: RuntimePhotoParams) -> None: ...
    def soft_update(self, exposure_compensation_ev=None, print_exposure=None, c_filter_neutral=None, m_filter_neutral=None, y_filter_neutral=None, film_density_curves=None, print_density_curves=None) -> None: ...
    def get_timings(self) -> dict[str, float]: ...
    def get_total_elapsed_time(self) -> float | None: ...
    def format_timings(self) -> str: ...
    def print_timings(self) -> None: ...
```

### Functions

| Function | Signature |
|----------|-----------|
| `characterize_pipeline_profile` | `(pipeline: SimulationPipeline) -> tuple[np.ndarray, np.ndarray]` |

---

## 8. Module `spektrafilm.runtime.stages`

**`src/spektrafilm/runtime/stages/__init__.py`** re-exports:

```python
__all__ = ["FilmingStage", "PrintingStage", "ScanningStage"]
```

### `FilmingStage` (`src/spektrafilm/runtime/stages/filming.py`)

```python
class FilmingStage:
    def __init__(self, film, film_render_params, camera_params, io_params, settings_params,
                 lut_service, resize_service, enlarger_service, color_reference_service,
                 backend=None): ...
    def auto_exposure(self, image: np.ndarray) -> np.ndarray: ...
    def auto_exposure_with_ev(self, image: np.ndarray) -> tuple[np.ndarray, float]: ...
    def expose(self, image: np.ndarray) -> np.ndarray: ...
    def develop(self, log_raw: np.ndarray) -> np.ndarray: ...
```

### `PrintingStage` (`src/spektrafilm/runtime/stages/printing.py`)

```python
class PrintingStage:
    def __init__(self, film, film_render_params, print_profile, print_render_params,
                 enlarger_params, settings_params, lut_service, enlarger_service,
                 resize_service, color_reference_service, backend=None): ...
    def expose(self, cmy_film_density: np.ndarray) -> np.ndarray: ...
    def develop(self, log_raw: np.ndarray) -> np.ndarray: ...
```

### `ScanningStage` (`src/spektrafilm/runtime/stages/scanning.py`)

```python
class ScanningStage:
    def __init__(self, film, film_render_params, print_profile, print_render_params,
                 scanner_params, io_params, settings_params, lut_service,
                 color_reference_service, backend=None): ...
    def scan(self, density_channels: np.ndarray, output_encoding: ColorEncoding | None = None) -> np.ndarray: ...
```

---

## 9. Module `spektrafilm.runtime.services`

**`src/spektrafilm/runtime/services/__init__.py`** re-exports:

```python
__all__ = ["EnlargerService", "SpectralLUTService", "ResizingService", "ColorReferenceService"]
```

### `EnlargerService` (`src/spektrafilm/runtime/services/filter_enlarger_source.py`)

```python
class EnlargerService:
    def __init__(self, enlarger_params): ...
    def enlarger_filtered_illuminant(self, light_source) -> np.ndarray: ...
    def enlarger_neutral_illuminant(self, light_source) -> np.ndarray: ...
    def preflash_filtered_illuminant(self, light_source) -> np.ndarray: ...
```

### `SpectralLUTService` (`src/spektrafilm/runtime/services/spectral_lut_compute.py`)

```python
class SpectralLUTService:
    def __init__(self, lut_resolution: int, *, gpu_backend=None): ...
    @property
    def lut_resolution(self) -> int: ...
    def clear(self) -> None: ...
    def memory_info(self) -> dict[str, int]: ...
    def spectral_compute_enlarger(self, cmy_data, spectral_calculation, data_min, data_max, *, use_lut=False): ...
    def spectral_compute_scanner(self, cmy_data, spectral_calculation, data_min, data_max, *, use_lut=False): ...
    def get_filming_tc_lut(self, sensitivity, sensitivity_adaptation=False, bandpass_params=None, surface_params=None, reference_illuminant='D55'): ...
```

### `ResizingService` (`src/spektrafilm/runtime/services/resize.py`)

```python
class ResizingService:
    def __init__(self, io_params, film_format_mm: float): ...
    def crop_and_rescale(self, image: np.ndarray) -> np.ndarray: ...
    def small_preview(self, image: np.ndarray, max_size: int = 256) -> np.ndarray: ...
```

### `ColorReferenceService` (`src/spektrafilm/runtime/services/color_reference.py`)

```python
class ColorReferenceService:
    def __init__(self, film_profile, film_render, print_profile, print_render,
                 black_correction, white_correction, black_level, white_level,
                 io_params, output_encoding=None): ...
    def black_white_filming_exposure_correction(self): ...
    def black_white_printing_exposure_correction(self): ...
    def black_white_xyz_correction(self, xyz): ...
```

---

## 10. Module `spektrafilm.model.emulsion`

**File:** `src/spektrafilm/model/emulsion.py`

### Type Aliases

| Name | Definition |
|------|------------|
| `FloatArray` | `NDArray[np.float64]` |
| `ProfileType` | `Literal['negative', 'positive']` |

### Functions

| Function | Signature |
|----------|-----------|
| `compute_density_spectral` | `(channel_density: FloatArray, density_cmy: FloatArray, base_density: FloatArray | None = None) -> FloatArray` |
| `develop_simple` | `(log_raw: FloatArray, log_exposure: FloatArray, density_curves: FloatArray, gamma_factor: float = 1.0, backend=None) -> FloatArray` |
| `develop` | `(log_raw: FloatArray, pixel_size_um: float, log_exposure: FloatArray, density_curves: FloatArray, density_curves_layers: FloatArray, dir_couplers: DirCouplersParams, grain: GrainParams, profile_type: ProfileType, gamma_factor: float = 1.0, bypass_grain: bool = False, use_fast_stats: bool = False, backend=None) -> FloatArray` |

---

## 11. Module `spektrafilm.model.diffusion`

**File:** `src/spektrafilm/model/diffusion.py`

### Constants

| Name | Type | Description |
|------|------|-------------|
| `DIFFUSION_FILTER_FAMILIES` | `tuple[str, ...]` | `('glimmerglass', 'black_pro_mist', 'pro_mist', 'cinebloom')` |

### Functions

| Function | Signature |
|----------|-----------|
| `apply_unsharp_mask` | `(image, sigma=0.0, amount=0.0, *, backend=None) -> np.ndarray` |
| `apply_halation_um` | `(raw, halation, pixel_size_um, *, backend=None) -> np.ndarray` |
| `apply_gaussian_blur` | `(data, sigma, *, backend=None) -> np.ndarray` |
| `apply_gaussian_blur_um` | `(data, sigma_um, pixel_size_um, *, backend=None) -> np.ndarray` |
| `apply_diffusion_filter_mm` | `(data, diffusion_filter_params, pixel_size_um) -> np.ndarray` |
| `apply_diffusion_filter_um` | `(image, diffusion_filter, pixel_size_um, *, backend=None) -> np.ndarray` |
| `diffusion_filter_psf` | `(kernel_shape: tuple[int, int], *, family: str, spatial_scale: float, pixel_size_um: float, halo_warmth: float = 0.0, overrides: dict | None = None) -> np.ndarray` |

---

## 12. Module `spektrafilm.model.couplers`

**File:** `src/spektrafilm/model/couplers.py`

| Function | Signature |
|----------|-----------|
| `compute_density_curves_before_dir_couplers` | `(density_curves, log_exposure, dir_couplers_matrix, positive=False) -> np.ndarray` |
| `compute_dir_couplers_matrix` | `(couplers_params: DirCouplersParams = DirCouplersParams()) -> np.ndarray` |
| `compute_exposure_correction_dir_couplers` | `(log_raw, density_cmy, density_max, dir_couplers_matrix, diffusion_size_pixel, diffusion_tail_size_pixel=0.0, diffusion_exp_tail_weight=0.0, high_exposure_couplers_shift=0.0, positive=False, backend=None) -> np.ndarray` |
| `apply_density_correction_dir_couplers` | `(density_cmy, log_raw, pixel_size_um, log_exposure, density_curves, dir_couplers, profile_type, gamma_factor=1.0, backend=None) -> np.ndarray` |

---

## 13. Module `spektrafilm.model.color_filters`

**File:** `src/spektrafilm/model/color_filters.py`

### Classes

#### `DichroicFilters`

```python
class DichroicFilters:
    def __init__(self, brand='thorlabs'): ...
    def plot(self) -> None: ...
    def apply(self, illuminant, filter_transmittance_values=None) -> np.ndarray: ...
    def apply_cc(self, illuminant, filter_cc_values=None) -> np.ndarray: ...
    def create_custom_filters(self, edges=None, transitions=None) -> None: ...
```

#### `GenericFilter`

```python
class GenericFilter:
    def __init__(self, name='KG3', type='heat_absorbing', brand='schott', data_in_percentage=False, load_from_database=True): ...
    def apply(self, illuminant, value=1.0) -> np.ndarray: ...
```

### Module-level Filter Instances

| Name | Type |
|------|------|
| `dichroic_filters` | `DichroicFilters \| None` |
| `thorlabs_dichroic_filters` | `DichroicFilters \| None` |
| `edmund_optics_dichroic_filters` | `DichroicFilters \| None` |
| `durst_digital_light_dicrhoic_filters` | `DichroicFilters \| None` |
| `custom_dichroic_filters` | `DichroicFilters \| None` |
| `schott_kg1_heat_filter` | `GenericFilter \| None` |
| `schott_kg3_heat_filter` | `GenericFilter \| None` |
| `schott_kg5_heat_filter` | `GenericFilter \| None` |
| `generic_lens_transmission` | `GenericFilter \| None` |

All may be `None` if data files are missing at import time.

### Functions

| Function | Signature |
|----------|-----------|
| `create_combined_dichroic_filter` | `(wavelength: np.ndarray, transitions: list[float], edges: list[float]) -> np.ndarray` |
| `sigmoid_erf` | `(x: np.ndarray, center: float, width: float = 1.0) -> np.ndarray` |
| `compute_band_pass_filter` | `(filter_uv: list[float] | None = None, filter_ir: list[float] | None = None) -> np.ndarray` |
| `color_enlarger` | `(light_source, filter_cc_values=(0,65,55), filters=custom_dichroic_filters) -> np.ndarray` |

---

## 14. Module `spektrafilm.model.illuminants`

**File:** `src/spektrafilm/model/illuminants.py`

### Enum

```python
class Illuminants(Enum):
    lamp = 'TH-KG3'
```

### Functions

| Function | Signature |
|----------|-----------|
| `black_body_spectrum` | `(temperature: float) -> colour.SpectralDistribution` |
| `standard_illuminant` | `(type: str = 'D65', return_class: bool = False) -> colour.SpectralDistribution \| np.ndarray` |

Supported illuminant types: `'TH-KG3'`, `'TH-KG3-L'`, `'T'`, `'K75P'`, `'BB{temperature}'`, or any key in `colour.SDS_ILLUMINANTS`.

---

## 15. Module `spektrafilm.model.glare`

**File:** `src/spektrafilm/model/glare.py`

| Function | Signature |
|----------|-----------|
| `add_glare` | `(xyz: np.ndarray, illuminant_xyz: np.ndarray, glare) -> np.ndarray` |
| `compute_random_glare_amount` | `(amount: float, roughness: float, blur: float, shape: tuple[int, ...]) -> np.ndarray` |

---

## 16. Module `spektrafilm.model.parametric`

**File:** `src/spektrafilm/model/parametric.py`

| Function | Signature |
|----------|-----------|
| `parametric_density_curves_model` | `(log_exposure, gamma, log_exposure_0, density_max, toe_size, shoulder_size) -> np.ndarray` |

---

## 17. Module `spektrafilm.model.stocks`

**File:** `src/spektrafilm/model/stocks.py`

### Enums

```python
class FilmStocks(Enum):
    kodak_ektar_100, kodak_portra_160, kodak_portra_400, kodak_portra_800,
    kodak_portra_800_push1, kodak_portra_800_push2, kodak_gold_200,
    kodak_ultramax_400, kodak_vision3_50d, kodak_vision3_250d,
    kodak_verita_200d, kodak_vision3_200t, kodak_vision3_500t,
    fujifilm_pro_400h, fujifilm_c200, fujifilm_xtra_400,
    kodak_ektachrome_100, kodak_kodachrome_64, fujifilm_velvia_100,
    fujifilm_provia_100f

class PrintPapers(Enum):
    kodak_ultra_endura, kodak_endura_premier, kodak_ektacolor_edge,
    kodak_supra_endura, kodak_portra_endura,
    fujifilm_crystal_archive_typeii, kodak_2383, kodak_2393
```

---

## 18. Module `spektrafilm.config`

**File:** `src/spektrafilm/config.py`

### Constants

| Name | Type | Value |
|------|------|-------|
| `LOG_EXPOSURE` | `np.ndarray` | `np.linspace(-3, 4, 256)` |
| `SPECTRAL_SHAPE` | `colour.SpectralShape` | `(380, 780, 5)` |
| `STANDARD_OBSERVER_CMFS` | `colour.MultiSpectralDistributions` | CIE 1931 2-degree aligned to `SPECTRAL_SHAPE` |
| `STANDARD_OBSERVER_LMS` | `colour.MultiSpectralDistributions` | Stockman & Sharpe 2-degree aligned to `SPECTRAL_SHAPE` |

---

## 19. Module `spektrafilm.utils`

**`src/spektrafilm/utils/__init__.py`** re-exports:

```python
__all__ = ['load_and_process_raw_file']
```

### 19.1 `spektrafilm.utils.io`

**File:** `src/spektrafilm/utils/io.py`

#### Dataclasses

- `ImageMetadata(exif, iptc, xmp)` — frozen
- `ImagePayload(pixels: np.ndarray, color_encoding: ColorEncoding | None, source_metadata: ImageMetadata | None)` — frozen

#### Functions

| Function | Signature |
|----------|-----------|
| `read_image_metadata` | `(filename: str) -> ImageMetadata \| None` |
| `write_image_metadata` | `(filename: str, source_metadata: ImageMetadata \| None = None, *, saving_color_space: str \| None = None, saving_cctf_encoding: bool = True) -> None` |
| `read_image_color_encoding` | `(filename: str) -> ColorEncoding \| None` |
| `load_image_payload` | `(filename: str) -> ImagePayload` |
| `resolve_icc_profile_bytes` | `(color_space: str, cctf_encoding: bool = True) -> bytes \| None` |
| `colorspace_chromaticities` | `(color_space: str) -> tuple[float, ...] \| None` |
| `load_image_oiio` | `(filename: str \| Path, *, dtype: np.dtype = np.float32) -> np.ndarray` |
| `save_image_oiio` | `(filename: str, image_data: np.ndarray, bit_depth: int \| None = None, *, color_space: str \| None = None, cctf_encoding: bool = True, encoding: ColorEncoding \| None = None, white_luminance: float \| None = None, scene_luminance: np.ndarray \| None = None, scene_rgb: np.ndarray \| None = None, hdr_mapping_kwargs: dict \| None = None, exr_mode: str = "scene_linear_archive") -> tuple[str, ...]` |
| `save_hdr_rendition_exr` | `(filename: str, image_data: np.ndarray, *, color_space: str, bit_depth: int = 32, scene_luminance=None, scene_rgb=None, hdr_mapping_kwargs=None, white_luminance=None) -> tuple[str, ...]` |
| `save_neutral_print_filters` | `(neutral_print_filters) -> None` |
| `read_neutral_print_filters` | `() -> dict` |
| `load_dichroic_filters` | `(wavelengths, brand='thorlabs') -> np.ndarray` |
| `load_filter` | `(wavelengths, name='KG3', brand='schott', filter_type='heat_absorbing', percent_transmittance=False) -> np.ndarray` |

### 19.2 `spektrafilm.utils.raw_file_processor`

**File:** `src/spektrafilm/utils/raw_file_processor.py`

#### Dataclasses

- `ExifData(make, model, lens_make, lens_model, focal_length, f_number)` — frozen
- `RawImportDiagnostics(...)` — frozen, 15 fields
- `RawProcessingResult(image: np.ndarray, diagnostics: RawImportDiagnostics)` — frozen

#### Functions

| Function | Signature | Re-exported |
|----------|-----------|-------------|
| `load_and_process_raw_file` | `(raw_path, white_balance='as_shot', temperature=None, tint=None, lens_correction=False, output_colorspace="ACES2065-1", output_cctf_encoding=False, output_dtype=np.float32, lens_info_out=None, return_diagnostics=False) -> np.ndarray \| RawProcessingResult` | **Yes** (`spektrafilm.utils`) |
| `estimate_raw_hdr_import_diagnostics` | `(rgb: np.ndarray, *, raw_sensor_stats=None, auto_percentile=99.0, headroom_percentile=99.9, min_auto_diffuse_white=0.10, low_key_median_threshold=0.03, max_headroom=8.0) -> RawImportDiagnostics` | No |

### 19.3 `spektrafilm.utils.autoexposure`

**File:** `src/spektrafilm/utils/autoexposure.py`

#### Constants

| Name | Value |
|------|-------|
| `MIDDLE_GRAY_LUMINANCE` | `0.184` |
| `MIN_METER_LUMINANCE` | `1e-8` |
| `MAX_AUTO_EXPOSURE_EV` | `12.0` |
| `SCENE_LINEAR_HIGHLIGHT_PERCENTILE` | `80.0` |
| `SCENE_LINEAR_FLOOR_PERCENTILE` | `1.0` |

#### Functions

| Function | Signature |
|----------|-----------|
| `measure_autoexposure_ev` | `(image, color_space='sRGB', apply_cctf_decoding=True, method='center_weighted') -> float` |

Methods: `'scene_linear'`, `'average'`, `'median'`, `'center_weighted'`, `'partial'`, `'matrix'`, `'multi_zone'`, `'highlight_weighted'`.

### 19.4 `spektrafilm.utils.measure`

**File:** `src/spektrafilm/utils/measure.py`

| Function | Signature |
|----------|-----------|
| `measure_gamma` | `(log_exposure, density_curves, density_0=0.25, density_1=1.0) -> np.ndarray` |
| `measure_slopes_at_exposure` | `(log_exposure, density_curves, log_exposure_reference=0.0, log_exposure_range=np.log10(2**2)) -> np.ndarray` |
| `measure_density_min` | `(log_exposure, density_curves, info_type, control_plot=False) -> np.ndarray` |

### 19.5 `spektrafilm.utils.conversions`

**File:** `src/spektrafilm/utils/conversions.py`

| Function | Signature |
|----------|-----------|
| `density_to_light` | `(density: np.ndarray, light: np.ndarray) -> np.ndarray` |
| `compute_aces_conversion_matrix` | `(sensitivity: np.ndarray, illuminant: np.ndarray) -> np.ndarray` |

### 19.6 `spektrafilm.utils.crop_resize`

**File:** `src/spektrafilm/utils/crop_resize.py`

| Function | Signature |
|----------|-----------|
| `crop_image` | `(image, center=(0.5,0.5), size=(0.1, 0.1)) -> np.ndarray` |

### 19.7 `spektrafilm.utils.preview`

**File:** `src/spektrafilm/utils/preview.py`

| Function | Signature |
|----------|-----------|
| `resize_for_preview` | `(image: np.ndarray, max_size: int) -> np.ndarray` |

### 19.8 `spektrafilm.utils.spectral_upsampling`

**File:** `src/spektrafilm/utils/spectral_upsampling.py`

#### Dataclass

```python
@dataclass(frozen=True, slots=True)
class SpectralInputPolicy:
    negative_rgb: NegativeRGBPolicy = "clip"
    xy_out_of_bounds: XYOutOfBoundsPolicy = "clip"
    report_stats: bool = True
```

Type aliases: `NegativeRGBPolicy = Literal["clip", "warn", "error", "compress"]`, `XYOutOfBoundsPolicy = Literal["clip", "warn", "error"]`.

#### Module-level constant

`DEFAULT_SPECTRAL_INPUT_POLICY = SpectralInputPolicy()`

#### Functions

| Function | Signature |
|----------|-----------|
| `compute_lut_spectra` | `(lut_size=128, smooth_steps=1, lut_coeffs_filename='hanatos_irradiance_xy_coeffs_250304.lut') -> np.ndarray` |
| `compute_hanatos2025_tc_lut` | `(sensitivity, spectra_lut=HANATOS2025_SPECTRA_LUT) -> np.ndarray` |
| `compute_hanatos2025_adaptation_tc_lut` | `(sensitivity, bandpass_params, surface_params, reference_illuminant, spectra_lut=HANATOS2025_SPECTRA_LUT) -> np.ndarray` |
| `rgb_to_raw_mallett2019` | `(RGB, sensitivity, color_space='sRGB', apply_cctf_decoding=True, reference_illuminant='D65', input_policy=None) -> np.ndarray` |
| `rgb_to_raw_hanatos2025` | `(rgb, sensitivity, color_space, apply_cctf_decoding, reference_illuminant, sensitivity_adaptation=False, bandpass_params=None, surface_params=None, tc_lut=None, input_policy=None) -> np.ndarray` |
| `rgb_to_raw_hanatos2025_backend` | `(rgb, sensitivity, color_space, apply_cctf_decoding, reference_illuminant, tc_lut=None, *, sensitivity_adaptation=False, bandpass_params=None, surface_params=None, backend=None, precomputed=None, input_policy=None) -> np.ndarray` |
| `precompute_hanatos2025_constants` | `(color_space, apply_cctf_decoding, reference_illuminant) -> tuple` (LRU cached) |
| `rgb_to_smooth_spectrum` | `(rgb, color_space, apply_cctf_decoding, reference_illuminant, input_policy=None) -> np.ndarray` |
| `poly2d_deg3` | `(tc: np.ndarray, params: np.ndarray, center_tc=(0.0, 0.0)) -> np.ndarray` |
| `locked_logistic_rising` | `(x: np.ndarray, mu: float, sigma: float, nu: float) -> np.ndarray` |
| `eval_poly3_warp_log_exposure_surface` | `(params, illuminant_xy) -> np.ndarray` |
| `eval_logiflex8_spectral_bandpass` | `(params: np.ndarray) -> np.ndarray` |
| `eval_erf4_spectral_bandpass` | `(params: np.ndarray) -> np.ndarray` |
| `eval_spectral_bandpass` | `(params: np.ndarray, model: str = 'logiflex8') -> np.ndarray` |

### 19.9 `spektrafilm.utils.lut`

**File:** `src/spektrafilm/utils/lut.py`

| Function | Signature |
|----------|-----------|
| `compute_with_lut` | `(data, function, xmin=(0.0,0.0,0.0), xmax=(1.0,1.0,1.0), steps=32, lut=None, *, prepared_lut=None, method='pchip', return_prepared=False, gpu_backend=None) -> tuple` |
| `warmup_luts` | `() -> None` |

### 19.10 `spektrafilm.utils.fast_interp_lut`

**File:** `src/spektrafilm/utils/fast_interp_lut.py`

| Function | Signature |
|----------|-----------|
| `mitchell_weight` | `(t, B=1/3, C=1/3) -> float` (numba `@njit`) |
| `safe_index` | `(idx, L) -> int` (numba `@njit`) |
| `clamp_coordinate` | `(coord, L) -> float` (numba `@njit`) |
| `cubic_coordinate_base_fraction` | `(coord, L) -> tuple[int, float]` (numba `@njit`) |
| `linear_interp_lut_at_2d` | `(lut, x, y) -> np.ndarray` (numba `@njit`) |
| `cubic_interp_lut_at_3d` | `(lut, r, g, b) -> np.ndarray` |
| `apply_lut_cubic_3d` | `(lut, image) -> np.ndarray` |
| `prepare_lut_pchip_3d` | `(lut) -> tuple` |
| `apply_lut_pchip_3d_prepared` | `(prepared_lut, image) -> np.ndarray` |
| `apply_lut_pchip_3d` | `(lut, image) -> np.ndarray` |
| `apply_lut_3d` | `(lut, image, method='pchip') -> np.ndarray` |
| `cubic_interp_lut_at_2d` | `(lut, x, y) -> np.ndarray` |
| `apply_lut_cubic_2d` | `(lut, image) -> np.ndarray` |
| `apply_lut_cubic_scipy` | `(lut, image) -> np.ndarray` |

### 19.11 `spektrafilm.utils.fast_interp`

**File:** `src/spektrafilm/utils/fast_interp.py`

| Function | Signature |
|----------|-----------|
| `fast_interp` | `(image, x_axis, y_vals) -> np.ndarray` (numba `@njit parallel`) |
| `np_interp_for_image` | `(image, x_axis, y_vals) -> np.ndarray` |
| `warmup_fast_interp` | `() -> None` |

### 19.12 `spektrafilm.utils.fast_gaussian_filter`

**File:** `src/spektrafilm/utils/fast_gaussian_filter.py`

| Function | Signature |
|----------|-----------|
| `fast_gaussian_filter` | `(image, sigma, truncate=3.0) -> np.ndarray` |
| `fast_gaussian_filter_small` | `(image, sigma, truncate=3.0) -> np.ndarray` |
| `fast_gaussian_filter_large` | `(image, sigma) -> np.ndarray` |
| `fast_exponential_filter` | `(image, decay_constant, *, n_gaussians=3, truncate=3.0) -> np.ndarray` |
| `warmup_fast_gaussian_filter` | `() -> None` |

### 19.13 `spektrafilm.utils.fast_stats`

**File:** `src/spektrafilm/utils/fast_stats.py`

| Function | Signature |
|----------|-----------|
| `fast_binomial` | `(N_arr, p_arr) -> np.ndarray` (numba `@njit parallel`) |
| `fast_poisson` | `(lam_arr) -> np.ndarray` (numba `@njit parallel`) |
| `fast_lognormal` | `(mu_arr, sigma_arr) -> np.ndarray` (numba `@njit parallel`) |
| `fast_lognormal_from_mean_std` | `(mean_arr, std_arr) -> np.ndarray` (numba `@njit parallel`) |
| `warmup_fast_stats` | `() -> None` |

### 19.14 `spektrafilm.utils.timings`

**File:** `src/spektrafilm/utils/timings.py`

| Function | Signature |
|----------|-----------|
| `timeit` | `(label=None, *, include_class=True) -> Callable` — decorator |
| `format_elapsed_time` | `(seconds: float) -> str` |
| `format_timings` | `(timings: dict[str, float], total_elapsed_time: float \| None = None, header: str = "Simulation timings") -> str` |

### 19.15 `spektrafilm.utils.numba_warmup`

**File:** `src/spektrafilm/utils/numba_warmup.py`

| Function | Signature |
|----------|-----------|
| `warmup` | `() -> None` |

Calls `warmup_fast_stats`, `warmup_luts`, `warmup_fast_interp`, `warmup_fast_gaussian_filter`, `warmup_boost_highlights`.

---

## 20. Package `spektrafilm_gui`

**`src/spektrafilm_gui/__init__.py`** — empty (no public re-exports).

### 20.1 `spektrafilm_gui.app`

**File:** `src/spektrafilm_gui/app.py`

#### Dataclass

```python
@dataclass(slots=True)
class GuiApp:
    viewer: Any
    widgets: WidgetBundle
    controller: GuiController
    main_window: QtWidgets.QMainWindow
```

#### Functions

| Function | Signature |
|----------|-----------|
| `main` | `() -> None` — **CLI entry point** |
| `create_app` | `() -> GuiApp` |
| `initialize_controller` | `(*, viewer, widgets, controller_cls=GuiController, connect_signals_fn=connect_controller_signals) -> GuiController` |
| `build_main_window_for_app` | `(*, viewer, widgets, controller=None, ...) -> Any` |
| `connect_auto_preview_signals` | `(controller: GuiController, widgets: WidgetBundle) -> None` |
| `connect_controller_signals` | `(controller: GuiController, widgets: WidgetBundle) -> None` |
| `gray_18_canvas_enabled` | `(widgets: WidgetBundle) -> bool` |

---

## 21. Configuration Surfaces

### 21.1 Environment Variables

| Variable | Module | Default | Description |
|----------|--------|---------|-------------|
| `SPEKTRAFILM_GPU_TILE_PIXELS` | `runtime.pipeline` | `2_000_000` | Max pixels per GPU tile before splitting |
| `SPEKTRAFILM_MLX_TILE_PIXELS` | `runtime.pipeline` | `2_000_000` | Alias for MLX backend |

### 21.2 CLI Arguments

The `spektrafilm` CLI (`spektrafilm_gui.app:main`) takes no custom arguments — it launches the napari-based GUI directly.

### 21.3 Configuration via `RuntimePhotoParams` / `SettingsParams`

All runtime behavior is configured programmatically through the `RuntimePhotoParams` dataclass hierarchy. Key configuration surfaces:

| Surface | Params field | Description |
|---------|-------------|-------------|
| Compute backend | `settings.compute_backend` | `"auto"`, `"cpu"`, `"mlx"`, `"cupy"`, `"cuda"`, `"halide"` |
| Float precision | `settings.float_precision` | `"float32"` or `"float64"` |
| GPU precision | `settings.gpu_precision` | `"float32"` |
| Spectral method | `settings.rgb_to_raw_method` | `"hanatos2025"` or `"mallett2019"` |
| Input color space | `io.input_color_space` | Any `colour.RGB_COLOURSPACES` key |
| Output color space | `io.output_color_space` | Any `colour.RGB_COLOURSPACES` key |
| Film/print profiles | `film`, `print` | `Profile` objects loaded by stock name |
| Debug mode | `debug.debug_mode` | `"off"`, `"output"`, `"inject"` |

### 21.4 Bundled Data Files

- **Profiles:** `spektrafilm/data/profiles/*.json` — loaded via `load_profile(stock_name)`
- **Filters:** `spektrafilm/data/filters/` — dichroic filters, heat filters, lens transmission
- **LUTs:** `spektrafilm/data/luts/spectral_upsampling/` — Hanatos2025 irradiance LUT
- **ICC profiles:** `spektrafilm/data/icc/` — embedded in output images

---

## 22. Plugin / Extension Interfaces

### 21.5 Optional Dependencies

| Extra | Packages | Purpose |
|-------|----------|---------|
| `dev` | `pytest` | Testing |
| `halide` | `halide>=21,<22` | Halide compute backend |
| `gpu-apple` | `mlx>=0.31` | Apple Metal GPU backend |
| `gpu-cuda12` | `cupy-cuda12x>=13` | CUDA 12 GPU backend |
| `gpu-cupy-source` | `cupy>=13` | CuPy from source |

### Compute Backend Interface

The `select_backend(name, precision)` function (from `spektrafilm.gpu.backend`) returns an array backend object. Backend objects must implement:

- `supports_gpu: bool`
- `asarray(data) -> array`
- `to_numpy(array) -> np.ndarray`
- `synchronize() -> None` (optional)
- `cleanup() -> None` (optional)
- `requires_serial_runtime: bool` (optional)

No formal plugin registration exists — backends are selected by name string at runtime.

---

## 23. Re-export Summary

| Symbol | `spektrafilm` | `spektrafilm.runtime` | `spektrafilm.runtime.api` | `spektrafilm.profiles` | `spektrafilm.utils` |
|--------|:---:|:---:|:---:|:---:|:---:|
| `load_profile` | Y | Y | - | - | - |
| `save_profile` | Y | Y | - | - | - |
| `RuntimePhotoParams` | Y | Y | Y | - | - |
| `init_params` | Y | Y | Y | - | - |
| `digest_params` | Y | Y | Y | - | - |
| `Simulator` | Y | Y | Y | - | - |
| `simulate` | Y | Y | Y | - | - |
| `simulate_preview` | Y | - | Y | - | - |
| `AgXPhoto` | Y | - | - | - | - |
| `photo_params` | Y | - | - | - | - |
| `HDRSceneEnergyMetadata` | - | - | Y | - | - |
| `SimulationPipelineResult` | - | - | Y | - | - |
| `load_processed_profile` | - | - | - | Y | - |
| `save_processed_profile` | - | - | - | Y | - |
| `load_and_process_raw_file` | - | - | - | - | Y |
