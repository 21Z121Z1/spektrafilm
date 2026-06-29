# HDR Display/Profile Projector Plan - 2026-06-29

## Goal

Upgrade Spektrafilm RouteMaster HDR projection into a display/profile-aware linear gain-map projector that preserves legacy SDR output, keeps HEIC gain-map export as linear SDR base plus linear HDR alternate, clarifies reference white/diffuse white/peak headroom semantics, improves highlight chroma/gamut protection and highlight-only detail restoration, adds PQ/HLG transfer helpers for future direct HDR exports, and documents/verifies the behavior with focused tests and a local commit.

## Repository Context

- `RouteMaster` remains the single HDR pair intermediate for HEIC gain-map export. This task must not add a parallel HDR render chain.
- Public HDR routes remain `paper` and `light_table`; legacy aliases stay GUI compatibility shims only.
- HEIC export keeps the current boundary: `routemaster_export` renders SDR/HDR pair, `hdr_photo` encodes and validates. The encoder remains encode-only.
- SDR legacy output paths (`process()`, `project_sdr_legacy()`, ordinary JPG/PNG/TIFF/EXR saves) must not change.
- Existing worktree changes in GUI/backend materialization are treated as parallel user work. This task will avoid reverting them and will stage only files changed for this goal.

## Research Conclusions Applied to Spektrafilm

- ITU BT.2100 defines PQ and HLG as different HDR transfer systems and warns against intermixing transfer systems in one chain. Spektrafilm should isolate PQ/HLG helpers from the gain-map linear pair path.
- ITU BT.2408 defines HDR Reference White / diffuse white / graphics white as the nominal signal level for a 100% reflectance white card. The common 203 nit engineering default is useful for display diagnostics and metadata, not a reason to rescale Spektrafilm's SDR base.
- Android Ultra HDR and Adobe gain-map docs describe a backward-compatible base rendition plus gain map/metadata that reconstructs an alternate HDR rendition. Spektrafilm's existing linear SDR base + linear HDR alternate pair fits this model; pre-encoding the alternate to PQ/HLG before gain-map calculation would be a semantic bug.
- ACES Reference Gamut Compression preserves a zone of trusted colors and only compresses problematic saturated/out-of-gamut values. Spektrafilm should use luminance-ratio chroma from the route as the primary hue-preserving strategy, then use explicit gamut compression/desaturation for extreme high-saturation highlights instead of silent channel clipping.
- Highlight detail restoration must be gated to the HDR extension region. Current `material_detail_y` usage largely cancels algebraically, so the fix should apply bounded detail only to the highlight extension above diffuse white and should leave midgray/diffuse-white-and-below untouched.

## Implementation Plan

1. Add display/profile-aware configuration.
   - Introduce an `HDRDisplayProfile` dataclass or equivalent explicit profile object.
   - Keep `HDRProjectionConfig(max_headroom=..., display_reference_white_nits=...)` backwards-compatible.
   - Express display profile id, primaries/output color volume, transfer function, reference white nits, peak nits/max headroom, black nits, output diffuse white, and content headroom percentile.

2. Keep gain-map pair linear.
   - Default profile transfer function should be `gain-map-linear-pair`.
   - Diagnostics and standards metadata may record profile intent, but pair math must remain linear.
   - Add isolated PQ/HLG helper module for future direct HDR export, not used inside pair construction.

3. Improve luminance/headroom management.
   - Centralize effective display profile resolution.
   - Record diagnostics for reference white, diffuse white, output diffuse white, peak nits, max headroom, black nits, content percentile, and measured content headroom.
   - Preserve the authored SDR base below diffuse white and avoid abnormal diffuse-white lift.

4. Improve highlight color protection.
   - Continue using `route_look_chroma` / luminance-ratio route chroma as the color authority.
   - Add luma-preserving highlight gamut compression before final clipping.
   - Add explicit diagnostics for chroma strategy, path-to-white strength, and gamut compression.

5. Improve highlight detail restoration.
   - Replace the current detail-canceling math in generic and chemical paper paths.
   - Apply bounded material detail to the HDR extension only, with a smooth highlighter mask above diffuse white.
   - Record detail strategy diagnostics and add tests proving diffuse-white-and-below regions are not polluted.

6. Tests.
   - Add focused HDR display/profile projection tests.
   - Add transfer helper tests for finite, monotonic, and roundtrip behavior.
   - Extend existing projection tests only where needed; do not delete existing tests.
   - Run the required HDR/gain-map/color tests, new tests, `git diff --check`, and the non-GUI suite if feasible.

7. Documentation and commit.
   - Add `docs/reports/hdr-display-profile-projector-implementation-20260629.md`.
   - Do not modify `docs/README.md`; final report will note that docs routing can be updated manually later.
   - Commit only this task's files. Do not push.

## Initial Risk Checklist

- Verify SDR default outputs are not touched.
- Verify gain-map pair is not PQ/HLG encoded.
- Verify reference white, diffuse white, output diffuse white, and peak headroom are not conflated.
- Verify highlight hue is not destroyed by per-channel clipping or aggressive path-to-white.
- Verify detail restoration does not amplify noise or alter midgray/diffuse-white-and-below.
- Verify backend/MLX paths are not accidentally materialized by new projection code.
- Verify GUI cached RouteMaster export still receives compatible `HDRProjectionConfig`.
