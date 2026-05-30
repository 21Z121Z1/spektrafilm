# Changelog

All notable changes to Spektrafilm are documented in this file.

## [0.3.2] - 2026-05-30

### Added

- **Halide GPU backend** for AOT-compiled spectral and grain generators, targeting desktop and Android GPU acceleration with bit-identical output to the CPU/NumPy reference.
- **HDR gain map I/O** (`gain_map_io`) for reading, writing, and validating ISO 21496-1 gain map metadata embedded in JPEG/HEIC files.
- **HDR photo mapping** (`HDRPhotoMapping`) dataclass that captures the full HDR rendering pipeline state -- base/reel HDR curves, gain map parameters, tone-map settings, and SDR/HDR rendition targets.
- **ACEScg ICC profile** support, registered in the colour-space ICC profile table so that ACEScg linear images can be round-tripped with correct embedded ICC metadata.
- **HDR EXR export** (`save_hdr_rendition_exr`) for writing full-dynamic-range spectral renders as 32-bit float OpenEXR with scene-referred linear colour.
- **Android foundation** -- build scripts (`build_halide_aot_android.sh`), Gradle project skeleton, JNI bridge plan, and architectural research docs for a future Android port.
- **Spectral upsampling** improvements including Smits (2019) and Jakob & Hanika (2019) methods with full test coverage.
- **Numba-accelerated grain simulation** (`numba_warmup`) with ahead-of-time JIT compilation warm-up for consistent first-frame latency.
- **814+ automated tests** covering spectral pipelines, HDR photo mapping, gain map I/O, ICC metadata, Halide generators, grain simulation, EXIF metadata, and tier-3 fixes.

### Changed

- **`init_params` API** consolidated and simplified; the `PhotoParams` initialisation interface now exposes a cleaner set of named parameters with validation in `__post_init__`.
- **Removed `profile_creator`** module and its CLI entry-point from the package; profile creation is no longer part of the spektrafilm distribution (see `README.md` for details).
- **Python 3.13 minimum** -- the project now requires Python >= 3.13 (`requires-python = "~=3.13"`) to leverage modern typing, performance improvements, and Numba compatibility.

### Fixed

- **HDR SDR-base preservation** -- the `preserve_sdr_base=True` default is now honoured correctly, and related test expectations have been reconciled.
- **HDRPhotoMapping validation** -- `__post_init__` now validates all profile-HDR fields (base curve, gain map strength, tone-map range) instead of silently accepting invalid combinations.
- **GUI path-to-white toggle** -- the `profile_hdr_path_to_white_strength` parameter is now passed through correctly from the GUI controls to the rendering pipeline.
- **`save_image_oiio` API boundary** -- ownership and return-value contract clarified; callers now receive the written file path and metadata is written atomically.
- **README accuracy** -- removed stale references to `spektrafilm_profile_creator`, corrected the directory tree, and updated feature descriptions to reflect the current codebase.
