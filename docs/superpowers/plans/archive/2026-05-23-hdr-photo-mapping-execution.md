# HDR Photo Mapping Execution Plan

## /goal

Implement correct HDR still-photo export mapping for spektrafilm.

The export path must keep runtime simulation output scene-linear, then at photo-export time build two author-controlled renditions:

- an HDR rendition normalized by an explicit diffuse/paper-white anchor;
- an SDR base rendition produced by a hue-preserving shoulder tone map.

HEIC/HEIF export must pass those two renditions to the macOS CoreImage encoder so the gain map is derived from authored SDR/HDR pairs, not from a clipped HDR image. EXR export must remain the high-fidelity scene-linear path and record the project HDR reference-white luminance metadata.

## Current Findings

*(Update 2026-05-25: Many of these findings have been addressed. Dual-Layer HDR Mapping (Diffuse Lift + Specular Rolloff) is implemented. The Swift encoder now receives separated unlifted SDR and lifted HDR renditions and uses `hdrGainMapAsRGB=true` to create color gain maps. GUI controls for these HDR parameters (e.g., `hdr_diffuse_lift_strength`, `max_headroom`) have been added.)*

- `src/spektrafilm/utils/hdr_photo.py` already has initial `HDRPhotoMapping` and `HDRPhotoRenditions` scaffolding, but `save_hdr_photo_heic()` still writes only one raw HDR payload and the Swift side still creates its SDR base by `CIColorClamp`.
- The current Python SDR tone map is a simple max-channel scale-to-one for values above diffuse white. It passes the narrow hue-ratio tests but does not implement the documented monotonic shoulder with `sdr_paper_white` as the diffuse-white landing point and compressed highlight range above it.
- `src/spektrafilm/data/macos/hdr_heif_encoder.swift` accepts one RGBA float file and one color space object. The final contract needs separate SDR and HDR raw files plus split encoded/linear color spaces.
- `save_image_oiio()` correctly keeps HEIC mapping inside `save_hdr_photo_heic()` and rejects CCTF/clipped HDR-photo inputs.
- `src/spektrafilm_gui/controller.py` currently writes literal `203.0` for EXR `white_luminance`; this should use `HDR_REFERENCE_WHITE_LUMINANCE_NITS`.
- README already documents initial HDR photo support, but it still needs to state the authored SDR/HDR rendition mapping and the `whiteLuminance=203` anchor.

## Implementation Steps

1. Preserve the HEIC dispatch boundary.
   - Leave generic IO dispatch passing the original scene-linear source into `save_hdr_photo_heic()`.
   - Keep runtime simulation and GUI preview behavior untouched.

2. Complete Python HDR mapping.
   - Validate `HDRPhotoMapping` values.
   - Normalize input RGB by `diffuse_white`.
   - Clamp negative HDR-photo distribution values to zero.
   - Compute headroom using a robust percentile, floored at `1.0` and capped by `max_headroom`.
   - Reject HEIC export if the final headroom is below `MIN_HDR_PHOTO_HEADROOM`.
   - Produce the SDR base through per-pixel max-channel intensity, preserving channel ratios and compressing highlights into `[sdr_paper_white, 1.0]` with a logarithmic shoulder.
   - **Implement Dual-Layer HDR Mapping** (✅ Completed): 
     - Safely estimate `look_diffuse_white_reference` from `scene_y ~ 1.0`, falling back to `profile_fallback` for low-key scenes to prevent false highlight boosting.
     - Apply a **Diffuse Lift** layer from `hdr_diffuse_lift_start` to `hdr_diffuse_lift_end` to uncompress the paper-limited look white back to true HDR `1.0`.
     - Apply a **Specular Rolloff** using a logistic curve to smoothly compress highlight energy, adding it as an extended delta above the diffuse baseline without hard clipping.
     - *(Note: GUI parameters `hdr_diffuse_lift_strength`, `graft_strength`, `paper_rolloff_exposure_scale`, `paper_rolloff_k`, and `max_headroom` now dynamically control this mapping.)*
   - Generate separate contiguous RGBA float payloads for SDR headroom `1.0` and HDR headroom `renditions.headroom`.

3. Update macOS Swift encoder. (✅ Partially Completed)
   - Change CLI usage to:
     `hdr_heif_encoder.swift <sdr-rgba-f32-raw> <hdr-rgba-f32-raw> <output.heic> <width> <height> <color-space> <headroom> <quality>`.
   - Read and validate both raw payloads.
   - Use extended-linear color spaces for float `CIImage` inputs.
   - Use encoded display color spaces for HEIF output.
   - Remove the internal `CIColorClamp` SDR base generation.
   - Export `heifRepresentation(of: sdrImage, format: .RGBA8, colorSpace: encodedColorSpace, options: [.hdrImage: hdrImage, .hdrGainMapAsRGB: true, quality])`. *(Updated `hdrGainMapAsRGB` to true)*

4. Wire EXR reference white through a shared constant.
   - Import `HDR_REFERENCE_WHITE_LUMINANCE_NITS` into `src/spektrafilm_gui/controller.py`.
   - Use that constant for EXR `white_luminance`.

5. Update documentation.
   - Clarify that HEIC/HEIF HDR photos use authored SDR and HDR linear renditions.
   - Clarify that linear `1.0` is the diffuse-white anchor and EXR writes `whiteLuminance=203`.

6. Verification and self-audit.
   - Run targeted HDR/photo tests.
   - Run the broader color-management and GUI output tests named in the source plan.
   - Run Swift parse check where the local toolchain supports it.
   - Run `compileall` and `git diff --check`.
   - Re-read the implementation against the checklist:
     HEIC has separate SDR/HDR inputs, runtime remains scene-linear, diffuse white is explicit, headroom is bounded, EXR and HEIC paths stay distinct, and unrelated in-flight repository edits are preserved.
