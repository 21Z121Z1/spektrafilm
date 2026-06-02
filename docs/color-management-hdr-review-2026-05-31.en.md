> This is an English translation of the Chinese original. For the authoritative version, see the Chinese original.

# Color Management and HDR Processing Code Review Report

Date: 2026-05-31
This update: fixes the three remaining risks listed in the previous report and refreshes the real RAW/HDR metadata validation.

Scope: `src/spektrafilm/color_management.py`, runtime parameters/pipeline/stages, GUI state/mapper/controller, macOS bridge, ImageIO HDR/ICC/gain-map interfaces, `tools/validate_profile_aware_hdr_raw_samples.py`, related tests and validation reports.

## Conclusion

Color management and HDR processing have progressed from "underlying capabilities exist but integration is incomplete" to "GUI/runtime/export critical paths are integrated and have regression tests."

Key fixes completed:

- The SDR default path remains `sRGB + CCTF + clip`; the default behavior has not been broken by ACES/HDR changes.
- `aces_reference` workflow runtime is fixed to `ACEScg` scene-linear input/output; save defaults to `ACES2065-1` linear interchange, and disables runtime highlight/negative clamping.
- GUI manual workflow has split runtime output encoding from save encoding: `output_cctf_encoding` only controls simulation output, `saving_cctf_encoding` only controls file saving.
- Linear ACES preview no longer goes through the normal sRGB approximation branch; GUI and macOS bridge now call `aces_sdr_video_view_transform()`, and preserve highlights above 1.0 in ACES/scene-linear preview before display rendering.
- HDR scene-energy sidecar is still produced by `process_with_metadata()` and passed to the save path; the real DNG validation script now checks sidecar, Android Ultra HDR/ISO gain-map metadata, JPEG MPF probe, and EXR attribute expectations simultaneously.
- Gain-map JPEG XMP now includes `Container:Directory`, `Primary`, `GainMap` item semantics and secondary item length required by Android Ultra HDR/GContainer.

## References

- ACES Output Transforms: ACES officially defines the Output Transform as the output rendering chain from scene-linear ACES to a specific display device encoding. https://docs.acescentral.com/system-components/output-transforms/
- ACEScg: ACEScg is AP1, scene-linear, floating-point CGI/rendering/compositing workspace. https://docs.acescentral.com/encodings/acescg/
- OpenColorIO ACES configuration: OCIO's ACES config uses ACEScg as the scene/compositing linear and provides ACES output colorspaces. https://opencolorio.readthedocs.io/en/v2.4.0/configurations/aces_1.0.3.html
- Qt QColorSpace: Display P3 is a wide-gamut display space; the preview chain should not unconditionally compress into sRGB middleware. https://doc.qt.io/qt-6/qcolorspace.html
- OpenEXR Standard Attributes: `chromaticities` and `whiteLuminance` describe the chromaticity and white luminance of RGB images. https://openexr.com/en/latest/StandardAttributes.html
- Android Ultra HDR v1.1: JPEG gain-map requires XMP `Container:Directory`, `Primary/GainMap` item semantics, and recommends simultaneously encoding Ultra HDR and ISO 21496-1 metadata. https://developer.android.com/media/platform/hdr-image-format

## Fix Details

### 1. ACES Preview Changed from sRGB Approximation to Explicit Output View

Previous risk:

- Linear ACES preview only performed `RGB_to_RGB(..., "sRGB")`, equivalent to a normal sRGB display approximation.
- The preview entry would first clip the float image to `0..1`, losing HDR highlights before display rendering.

Fixes in this round:

- Added `aces_sdr_video_view_transform()`, which only accepts `ACES2065-1` or `ACEScg` scene-linear RGB at the entry point.
- The helper first converts to linear sRGB primaries, then applies a local ACES-style SDR video rendering curve and sRGB display encoding, outputting `0..1` display-referred code values.
- GUI `controller_runtime.apply_display_transform()` calls this helper for ACES scene-linear output, with status text `Display transform: ACES SDR video output transform`.
- `controller_runtime.prepare_output_display_image()` and `macos_bridge._display_preview_image()` only clamp negative values for ACES/linear scene preview, no longer clipping scene highlights above 1.0.

Boundary notes:

- This is no longer an unnamed sRGB approximation, but it is still not the OCIO/CTL exact ACES 2 Output Transform. To achieve studio-level cross-software per-pixel consistency, the next step would be to integrate the OCIO Studio/CG ACES config or implement the official ACES CTL/Output Transform within the project.
- The current fix goal of this project is to migrate the GUI/runtime preview from the incorrect/ambiguous sRGB branch to an explicit, testable ACES SDR output view that preserves HDR highlights.

### 2. Runtime Output Encoding and Save Encoding Have Been Split

Previous risk:

- GUI manual workflow exposed a workflow selector, but runtime output CCTF still reused save CCTF.
- This prevented combinations like "runtime linear output, save encoded output" or the reverse from being accurately expressed.

Fixes in this round:

- `SimulationState` has added `output_cctf_encoding`.
- `params_mapper._apply_io()` maps `params.io.output_cctf_encoding` to `state.simulation.output_cctf_encoding`, no longer reading `saving_cctf_encoding`.
- `OutputSection` simultaneously displays `output_color_space`, `output_cctf_encoding`, `saving_color_space`, `saving_cctf_encoding`.
- GUI controller's async/sync fallback, output layer metadata, and display transform request all use runtime `output_cctf_encoding`.
- Save path continues to use `saving_color_space` and `saving_cctf_encoding`, and decodes/converts from source runtime encoding before saving.
- macOS bridge has added `BridgeRenderOptions.output_cctf_encoding`, CLI defaults, and `--output-cctf-encoding` / `--no-output-cctf-encoding`.

Validation coverage:

- Under manual workflow, runtime `output_cctf_encoding=True` and saving `saving_cctf_encoding=False` can independently hold.
- Old GUI JSON missing fields are backfilled with default `True`.
- Controller fallback and macOS bridge both have independent tests.

### 3. HDR Scene Luminance and Gain-Map Metadata Validated with Real Samples

Previous risk:

- `scene_luminance` came from auto-exposure and the RGB of the input scene after crop/rescale, lacking real HDR photo metadata validation.
- Whether Apple/Android/ISO gain-map metadata was complete lacked automated checking.

Fixes in this round:

- `tools/validate_profile_aware_hdr_raw_samples.py` fixed stale RAW API imports and outputs metadata checks in real DNG validation.
- The validation script now checks for each sample:
  - `process_with_metadata()` sidecar shape, finite/nonnegative, and consistency with process output;
  - Sidecar median remains scale-invariant under auto-exposure global scaling;
  - Whether Android Ultra HDR/GContainer XMP contains `Container:Directory`, `Primary`, `GainMap`;
  - ISO 21496-1 binary metadata serialize/deserialize roundtrip;
  - Gain-map numerical range and validation warnings;
  - Whether JPEG probe simultaneously contains ISO URN, GContainer XMP, and MPF gain-map;
  - EXR export attributes to track: `chromaticities`, `colorInteropID`, `oiio:ColorSpace`, `whiteLuminance`, `hdrHeadroom`.
- `GainMapMetadata.to_xmp(gain_map_length=...)` now generates Android Ultra HDR-compatible `Container:Directory`.
- `save_gain_map_jpeg()` writes the actual gain-map JPEG byte length and maintains the MPF payload.

Real sample results:

- Sample directory: `/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片/RAW_DNG_JPEG_批量导出`
- DNG files found: 365; 4 sampled for validation in this round, covering normal exposure, low-key, strong highlight, and near-white clipping samples.
- Latest report: `docs/hdr_profile_aware_raw_validation.md`
- All 4 samples passed sidecar finite/nonnegative, process parity, auto-exposure scale-invariant, Android container, ISO metadata roundtrip, JPEG metadata/gain-map probe, and EXR attribute tracking checks.

Boundary notes:

- This round of validation proves that the metadata structure and local probe generated by the project conform to Android Ultra HDR/ISO/OpenEXR expectations; it is not a manual/device rendering acceptance by Apple Photos, Android Gallery, or third-party ISO decoders.
- For complex HDR photo export, it is still recommended to retain a device acceptance runbook: generate HEIC/JPEG/EXR samples, and check recognition and display in Apple Photos, Android 15+ Ultra HDR viewer, and at least one ISO 21496-1 decoder.

## Current Code Path Completeness

| Path | Current Status |
| --- | --- |
| SDR manual runtime | Default `sRGB + CCTF + clip`, maintains compatibility |
| ACES reference runtime | `ACEScg + linear + unclipped` |
| ACES reference save | `ACES2065-1 + linear` |
| GUI runtime output CCTF | Independent field `output_cctf_encoding` |
| GUI save CCTF | Independent field `saving_cctf_encoding` |
| GUI ACES preview | `aces_sdr_video_view_transform()` |
| macOS bridge ACES preview | Synchronous call to `aces_sdr_video_view_transform()` |
| HDR sidecar | `process_with_metadata()` output and passed to save path |
| Android/ISO gain-map JPEG | XMP GContainer + ISO metadata + MPF probe |
| EXR HDR metadata | `chromaticities`, `colorInteropID`, `oiio:ColorSpace`, `whiteLuminance`, `hdrHeadroom` tracked by validation script |

## Main Modified Files

- Plan: `docs/superpowers/plans/2026-05-31-aces-output-transform-hdr-metadata-encoding-split.md`
- Color management: `src/spektrafilm/color_management.py`
- GUI runtime/display: `src/spektrafilm_gui/controller_runtime.py`
- GUI state/mapper/widgets: `src/spektrafilm_gui/state.py`, `src/spektrafilm_gui/params_mapper.py`, `src/spektrafilm_gui/widget_specs.py`, `src/spektrafilm_gui/widget_sections.py`
- GUI controller/save: `src/spektrafilm_gui/controller.py`
- macOS bridge: `src/spektrafilm_gui/macos_bridge.py`
- Gain-map metadata/io: `src/spektrafilm/utils/gain_map_metadata.py`, `src/spektrafilm/utils/gain_map_io.py`
- HDR validation: `tools/validate_profile_aware_hdr_raw_samples.py`, `docs/hdr_profile_aware_raw_validation.md`, `docs/hdr_profile_aware_raw_validation.json`
- Tests: `tests/test_color_management.py`, `tests/test_gain_map.py`, `tests/test_hdr_profile_validation_tool.py`, `tests/gui/test_controller_runtime_module.py`, `tests/gui/test_params_mapper.py`, `tests/gui/test_persistence.py`, `tests/gui/test_controller_flow.py`, `tests/gui/test_macos_bridge.py`

## Validation

Run and passed:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /usr/bin/perl -e 'alarm shift; exec @ARGV' 120 \
  uv run --extra dev pytest -q \
  tests/gui/test_controller_runtime_module.py::test_prepare_output_display_image_uses_aces_output_transform_for_linear_scene \
  tests/gui/test_macos_bridge.py::test_display_preview_preserves_aces_scene_highlights \
  tests/test_color_management.py::test_aces_sdr_video_view_transform_is_named_output_view_with_srgb_encoding
```

Result: `3 passed in 2.64s`

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /usr/bin/perl -e 'alarm shift; exec @ARGV' 240 \
  uv run --extra dev pytest -q \
  tests/test_color_management.py \
  tests/test_gain_map.py \
  tests/test_hdr_profile_validation_tool.py \
  tests/gui/test_params_mapper.py \
  tests/gui/test_persistence.py \
  tests/gui/test_controller_runtime_module.py \
  tests/gui/test_controller_flow.py \
  tests/gui/test_controller_output.py \
  tests/gui/test_macos_bridge.py
```

Result: `130 passed in 4.93s`

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /usr/bin/perl -e 'alarm shift; exec @ARGV' 900 \
  uv run --extra dev pytest -q
```

Result: `875 passed, 7 skipped, 1 warning in 52.84s`

```bash
/usr/bin/perl -e 'alarm shift; exec @ARGV' 900 \
  uv run python tools/validate_profile_aware_hdr_raw_samples.py \
  --sample-dir "/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片/RAW_DNG_JPEG_批量导出" \
  --max-samples 4 \
  --diagnostic-scan-limit 32 \
  --output docs/hdr_profile_aware_raw_validation.md
```

Result: Completed 4 real DNG sample validations and refreshed `docs/hdr_profile_aware_raw_validation.md/json`.

Final cleanup has been run and passed:

```bash
.venv/bin/python -m py_compile \
  src/spektrafilm/color_management.py \
  src/spektrafilm_gui/controller_runtime.py \
  src/spektrafilm_gui/state.py \
  src/spektrafilm_gui/widget_specs.py \
  src/spektrafilm_gui/widget_sections.py \
  src/spektrafilm_gui/params_mapper.py \
  src/spektrafilm_gui/controller.py \
  src/spektrafilm_gui/macos_bridge.py \
  src/spektrafilm/utils/gain_map_metadata.py \
  src/spektrafilm/utils/gain_map_io.py \
  tools/validate_profile_aware_hdr_raw_samples.py
```

```bash
git diff --check
```

## Current Remaining Limitations

- ACES preview has been fixed from the old sRGB approximation to an explicit local ACES SDR output view and preserves scene highlights; however, it is still not the OCIO/CTL exact ACES 2 Output Transform. Professional cross-software display consistency requires integrating the OCIO ACES config or the official CTL reference implementation.
- HDR metadata has been validated with real DNG artifacts and local JPEG/EXR metadata probes; device-level display acceptance by Apple Photos, Android Gallery, or third-party ISO decoders has not yet been completed.
- GUI and macOS bridge have split runtime/save encoding; scripts that directly call the runtime/save API still need to explicitly pass the correct `output_cctf_encoding`, `saving_cctf_encoding`, and `scene_luminance`.

## Self-Check

- Is there still the old `linear scene preview, using sRGB view approximation`? No; the ACES scene-linear path has been changed to `Display transform: ACES SDR video output transform`.
- Will ACES preview still clip HDR highlights before the transform? No; the ACES/linear branch in both GUI and macOS bridge only clips negative values, not values above 1.0.
- Does manual workflow still reuse saving CCTF as runtime output CCTF? No; mapper/controller/bridge all use the independent `output_cctf_encoding`.
- Has the SDR default changed? No; the default is still `manual`, runtime `sRGB + CCTF`, saving `sRGB + CCTF`.
- Can we claim "100% no risk of any external display discrepancy"? No. What can be 100% confirmed is that the local code paths, regression tests, and real sample metadata probes listed in this report are closed-loop; external device rendering consistency requires separate device acceptance.
