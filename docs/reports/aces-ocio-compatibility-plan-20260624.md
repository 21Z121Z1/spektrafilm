# ACES / OCIO Compatibility Plan — 2026-06-24

## /goal

Implement a conservative ACES compatibility layer for Spektrafilm that improves ACEScg / ACES2065-1 conversion, separates local ACES-style preview from official OCIO view rendering, exposes optional OpenColorIO diagnostics without making OCIO a runtime hard dependency, wraps the existing ACES RGC-family output gamut compression path, and emits a project-local transform manifest suitable for future AMF integration. Preserve the existing `spektrafilm.color_management` public API and the current `aces_reference` workflow contract. Do not open ACES scene-linear LUT input roles unless a scene-linear shaper is implemented and tested.

## Facts confirmed before implementation

- `color_management.py` already defines `ACES2065-1` as interchange and `ACEScg` as working space, and the `aces_reference` preset keeps runtime input/output in ACEScg scene-linear/unclipped while saving defaults to ACES2065-1 scene-linear.
- `aces_sdr_video_view_transform()` is a deterministic Spektrafilm-local SDR preview based on a fitted ACES-style curve. It is not an official CTL/OCIO ACES Output Transform.
- `utils/gamut_compression.py` already has an `aces_rgc` output gamut compression option and a native per-channel ACES Reference Gamut Compression family implementation.
- `pyproject.toml` includes `opencolorio` only in the `dev` extra; therefore official OCIO view support must remain optional.
- LUT creator ACES scene-linear roles are intentionally constrained because there is no scene-linear shaper support in the current LUT input path.

## Implementation plan

1. Add `src/spektrafilm/aces_compat.py` as a narrow compatibility layer. It will own ACES context/diagnostics dataclasses, conversion helpers, local preview wrapper, optional OCIO config loading, optional OCIO view rendering, RGC wrapper, and manifest construction.
2. Keep `src/spektrafilm/color_management.py` as the stable public API module. Re-export selected compatibility helpers from it, and delegate `aces_sdr_video_view_transform()` to `render_aces_local_sdr_preview()` without changing its signature or semantics.
3. Implement optional OCIO support with explicit failure modes. If PyOpenColorIO is missing, raise `AcesOcioUnavailableError`. If no built-in or user config can be loaded, raise a detailed error listing attempted config names. Never silently fall back to the local preview.
4. Implement ACES conversion helpers with `colour.RGB_to_RGB()` and explicit `apply_cctf_decoding` / `apply_cctf_encoding=False` behavior. Preserve dtype/shape where practical and force finite float32 output for runtime consistency.
5. Implement `build_aces_transform_manifest()` as a project-local dict. It must use `implementation_kind` and placeholder transform-id fields without inventing official ACES Transform IDs.
6. Add `tests/test_aces_compat.py` covering AP0/AP1 roundtrips, neutral-axis preservation, high-saturation finite behavior, CCTF decoding behavior, local preview range, old color-management API compatibility, aces_reference invariance, OCIO skip/failure behavior, manifest fields, RGC behavior, and LUT scene-linear input still being intentionally silenced.
7. Add an implementation report in `docs/reports/aces-ocio-compatibility-implementation-20260624.md` documenting the support layers, official/local boundary, OCIO activation, RGC relation, AMF/Transform ID limits, LUT shaper deferral, searched references, and test commands.

## Acceptance checks

- `python -m pytest tests/test_color_management.py tests/test_aces_compat.py -q`
- If PyOpenColorIO is installed, the OCIO smoke test must execute; otherwise it must skip or raise `AcesOcioUnavailableError` clearly.
- `git diff --check`
- No default manual SDR workflow behavior changes.
- No runtime dependency from `spektrafilm` to `spektrafilm_lut_creator`.
- No official ACES Output Transform claims for local preview.
- No fabricated AMF or Transform ID values.
