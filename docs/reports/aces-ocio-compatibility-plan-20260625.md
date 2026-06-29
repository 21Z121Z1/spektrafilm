# ACES / OCIO Compatibility Implementation Plan

Date: 2026-06-25

## Goal

Implement a Spektrafilm ACES/OCIO compatibility layer that preserves existing SDR/manual and `aces_reference` behavior while adding tested ACEScg/ACES2065-1 conversion helpers, honest local-vs-official preview APIs, optional PyOpenColorIO loading and view-render smoke path, ACES RGC wrapper, transform manifest diagnostics with AMF/Transform ID placeholders, LUT scene-linear input guard tests, implementation documentation, required verification, and a local commit without pushing.

## Current Spektrafilm Boundary

- `src/spektrafilm/color_management.py` already exposes `ACES_INTERCHANGE_COLOR_SPACE = "ACES2065-1"`, `ACES_WORKING_COLOR_SPACE = "ACEScg"`, `color_management_workflow_preset()`, `apply_color_management_workflow_to_io()`, and `aces_sdr_video_view_transform()`.
- `aces_reference` currently configures runtime input/output as unclipped scene-linear ACEScg and returns saving defaults for ACES2065-1 scene-linear. This must not regress.
- `aces_sdr_video_view_transform()` is a deterministic local ACES-style SDR preview using a Stephen Hill fit. It must remain honest and must not be rebranded as an official ACES Output Transform.
- `utils/gamut_compression.py` already has an ACES RGC v1.3 output compression implementation and documents its relation to OCIO `FixedFunctionTransform(style=ACES_GamutComp13)`.
- `src/spektrafilm_lut_creator` has OCIO bundle config emission, but runtime must not depend on LUT creator. Its scene-linear ACES input spaces remain registered but silenced (`role=()`) pending a scene-linear shaper.
- PyOpenColorIO is optional/dev. In this workspace `.venv` has PyOpenColorIO 2.5.2 and built-in configs including `studio-config-v4.0.0_aces-v2.0_ocio-v2.5`, but production runtime must fail clearly if OCIO is absent.

## External Source Conclusions

Sources reviewed:

- ACES ACES2065-1 documentation: AP0 scene-linear interchange, linear transfer.
- ACES ACEScg documentation: AP1 scene-linear working space for CGI/render/compositing.
- ACES ACEScct/ACEScc docs: log AP1 encodings for grading/color timing, not Spektrafilm's scene-linear working storage.
- ACES Output Transform docs: official Output Transform maps scene-referred ACES2065-1 into display-specific code values via rendering and display-encoding submodules.
- ACES Reference Gamut Compression docs: RGC is a specific ACES gamut-compression operation, not the same as Spektrafilm's perceptual output compression family.
- ACES AMF and Transform ID docs: useful for future interchange metadata, but this task must not invent official Transform IDs.
- OpenColorIO docs and local PyOpenColorIO registry: official ACES/studio config path should use PyOpenColorIO config processors, roles, colorspaces, displays, and views. Built-in configs are available in OCIO 2.5.
- colour-science local implementation: `RGB_COLOURSPACES` includes ACES2065-1, ACEScg, ACEScct, ACEScc; ACES2065-1/ACEScg CCTFs are linear no-ops.

Adopt now:

- A small `src/spektrafilm/aces_compat.py` module.
- Colour-science based ACEScg/ACES2065-1 conversions and input-to-ACEScg helper.
- Optional OCIO view rendering with explicit diagnostics and clear failure.
- Project-local manifest dictionary with future AMF fields, explicit placeholders, and implementation-kind labels.
- Wrapper for existing ACES RGC implementation.

Defer:

- Full AMF XML writing and official Transform ID registration.
- Replacing local preview with official Output Transform by default.
- Re-implementing ACES 2 Output Transform locally.
- Opening ACEScg/ACES2065-1 scene-linear LUT input roles without a shaper.
- Adding runtime dependency from `spektrafilm` to `spektrafilm_lut_creator`.

## Implementation Steps

1. Add `src/spektrafilm/aces_compat.py`.
   - Dataclasses: `AcesContext`, `AcesTransformDiagnostics`.
   - Exceptions: clear OCIO unavailable/config/view errors.
   - Helpers: `is_ocio_available()`, `load_aces_ocio_config()`, `to_acescg()`, `acescg_to_aces2065_1()`, `aces2065_1_to_acescg()`, `render_aces_local_sdr_preview()`, `render_aces_ocio_view()`, `apply_aces_reference_gamut_compression()`, `build_aces_transform_manifest()`.
   - Keep API stable, typed, and independent of GUI/LUT creator.

2. Preserve `color_management.py` public API.
   - Keep constants and workflow functions unchanged.
   - Re-export selected new helpers only if useful.
   - Keep `aces_sdr_video_view_transform()` behavior and tests.

3. Add `tests/test_aces_compat.py`.
   - ACEScg/ACES2065-1 roundtrip shape/dtype/finite.
   - Neutral gray axis roundtrip preservation.
   - High-saturation AP0/AP1 samples finite.
   - `to_acescg()` from sRGB, Display P3, ProPhoto respects `apply_cctf_decoding`.
   - Local preview outputs 0..1 display-referred code values.
   - Old `aces_sdr_video_view_transform()` remains callable.
   - `aces_reference` workflow unchanged.
   - OCIO unavailable clear failure path or skip.
   - OCIO available minimal official view smoke path.
   - Manifest includes working/interchange/input/output/view/display/implementation/placeholder IDs.
   - ACES RGC wrapper finite, shape-preserving, neutral-preserving.
   - LUT creator ACES scene-linear input remains silenced.

4. Write implementation report.
   - New `docs/reports/aces-ocio-compatibility-implementation-20260625.md`.
   - Do not modify `docs/README.md`; report will note that docs router update is manual follow-up.

5. Verification.
   - `.venv/bin/python -m pytest tests/test_color_management.py tests/test_aces_compat.py -q`
   - If LUT creator files are unchanged, run only targeted LUT scene-linear guard through `tests/test_aces_compat.py`; no full LUT suite required.
   - OCIO smoke test should run in this workspace because PyOpenColorIO 2.5.2 is present; otherwise tests must skip/fail clearly by scenario.
   - `git diff --check`
   - Commit locally, do not push.

## Self-Audit Gates

Before completion, verify:

- Local preview is never described as official ACES Output Transform.
- Missing PyOpenColorIO never silently falls back to local preview for official view calls.
- `aces_reference` workflow values are unchanged.
- Runtime does not import LUT creator.
- ACES scene-linear LUT input remains silenced without shaper support.
- Manifest does not invent official Transform IDs.
- ACES RGC wrapper remains distinct from perceptual gamut compression.
- Default manual SDR workflow is untouched.
