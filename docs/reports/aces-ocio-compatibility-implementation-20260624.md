# ACES / OCIO Compatibility Implementation Report — 2026-06-24

## Summary

This change adds a conservative ACES compatibility layer without changing the default manual SDR workflow. The new layer gives Spektrafilm a stable place to expose ACEScg / ACES2065-1 conversions, local ACES-style SDR preview, optional official/configured OCIO view rendering, ACES RGC wrapper access, and a project-local transform manifest for future AMF work.

## ACES support layers in Spektrafilm

Spektrafilm now separates five layers:

1. Workflow preset: `color_management_workflow_preset("aces_reference")` keeps runtime input/output in ACEScg scene-linear/unclipped and marks saving as ACES2065-1 scene-linear.
2. Working/interchange conversion: `to_acescg()`, `acescg_to_aces2065_1()`, and `aces2065_1_to_acescg()` use colour-science RGB colourspace definitions.
3. Local preview: `render_aces_local_sdr_preview()` and legacy `aces_sdr_video_view_transform()` produce deterministic 0..1 sRGB display-referred preview values for GUI/useful smoke paths.
4. Official/configured view: `load_aces_ocio_config()` and `render_aces_ocio_view()` use PyOpenColorIO when available and do not silently fall back if OCIO is missing or no config can be found.
5. Manifest: `build_aces_transform_manifest()` emits project-local metadata fields for working/interchange space, input/output space, display/view, OCIO diagnostics, implementation kind, and Transform ID placeholders.

## ACES2065-1, ACEScg, ACEScct, and ACEScc roles

ACES2065-1 remains the interchange/archive scene-linear encoding using AP0 primaries. ACEScg remains the practical scene-linear working space using AP1 primaries. ACEScct and ACEScc remain log grading encodings and are not promoted to runtime scene-linear pipeline defaults by this change.

## Local preview versus official Output Transform

`aces_sdr_video_view_transform()` remains a Spektrafilm-local deterministic preview. It should not be described as an official ACES Output Transform, RRT+ODT, Academy Viewing Transform, CTL implementation, or Studio Config result. Official/configured view rendering is available only through `render_aces_ocio_view()` with a real OCIO config and PyOpenColorIO processor.

## Optional OCIO path and failure modes

OCIO is optional. If PyOpenColorIO is unavailable, the compatibility layer raises `AcesOcioUnavailableError` with an installation/configuration-oriented message. If PyOpenColorIO is available but an ACES built-in config cannot be loaded, the error lists attempted built-in config names and asks for an explicit `config_path`. This avoids the dangerous failure mode where a user thinks an official ACES view has run when the code actually used a local fallback.

## ACES RGC and output gamut compression

The new `apply_aces_reference_gamut_compression()` wrapper calls the existing `compress_rgb_aces_rgc()` implementation. This keeps ACES RGC-family compression distinct from perceptual output gamut compression options such as OkLch, Oklrab, JzAzBz, and CAM16-UCS. ACES RGC operates on the achromatic per-channel distance and does not perform perceptual lightness compression.

## Manifest, AMF, and Transform IDs

The manifest builder is intentionally project-local. It preserves AMF-relevant fields but does not claim AMF conformance. It also refuses to infer or invent Transform IDs: if no Transform ID is supplied, `transform_id` is `None` and `transform_id_status` is `not_provided_do_not_infer`.

## LUT creator boundary

This change does not open ACEScg or ACES2065-1 scene-linear LUT input roles. The current LUT creator path still lacks a scene-linear shaper design; enabling those roles without shaper support would generate misleading or low-quality LUT behavior. Future work should design a scene-linear shaper or OCIO-backed LUT bake path before opening those roles.

## Searched references and decisions

- ACESCentral documentation was used for the system split between encodings, Output Transforms, Look Transforms, Reference Gamut Compression, AMF, and Transform IDs. Adopted: terminology and boundary discipline. Rejected: claiming local preview is an official Output Transform.
- OpenColorIO documentation was used for built-in configs, `Config.CreateFromBuiltinConfig`, file-based config loading, display/view processors, roles, and processors. Adopted: optional official/configured view path. Rejected: making OCIO a default hard dependency.
- colour-science documentation was used for ACES colourspace conversion and CCTF boundaries. Adopted: colour-science conversion for RGB colourspace transforms. Rejected: using colour-science as an official ACES Output Transform engine.
- Resolve/Nuke/OCIO practice was treated as evidence that ACES RGC and ACES display/view transforms should remain named, inspectable pipeline steps. Adopted: explicit diagnostics and wrapper separation. Rejected: hiding RGC inside generic perceptual gamut compression.
- ACES 2.0 direction was treated as forward-looking. Adopted: manifest extensibility and conservative naming. Rejected: hardcoding ACES 2.0 transform names before project support is tested.

## Test commands

Required local checks in this checkout:

```bash
.venv/bin/python -m pytest tests/test_color_management.py tests/test_aces_compat.py -q
git diff --check
```

Optional checks when PyOpenColorIO is installed:

```bash
.venv/bin/python -m pytest tests/test_aces_compat.py -q -k ocio
```

If LUT creator registry code is changed in a later patch, run the LUT creator test subset as well. This implementation does not change the LUT creator runtime registry.

## Validation in this execution environment

Validated in `/Users/retriedstormtrooper/Documents/Projects/Active/spektrafilm-main` with the project virtual environment:

```bash
.venv/bin/python -m pytest tests/test_color_management.py tests/test_aces_compat.py -q
# 27 passed in 0.12s

.venv/bin/python -m pytest tests/test_aces_compat.py -q -k ocio
# 4 passed, 12 deselected in 0.08s

git diff --check
# passed with no output
```

PyOpenColorIO is available in this environment, so the OCIO smoke path executed instead of skipping.

## Self-review

- Local preview is explicitly labelled `spektrafilm_local` and is not called official ACES.
- Missing PyOpenColorIO is explicit and cannot silently use local fallback.
- The `aces_reference` workflow values are preserved.
- Runtime does not import from `spektrafilm_lut_creator`.
- ACES scene-linear LUT input roles remain closed pending shaper work.
- No official Transform ID is fabricated.
- ACES RGC remains separated from generic perceptual gamut compression.
- Manual SDR defaults are unchanged.
