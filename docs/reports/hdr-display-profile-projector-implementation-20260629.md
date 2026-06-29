# HDR Display/Profile Projector Implementation - 2026-06-29

## Goal

Upgrade Spektrafilm RouteMaster HDR projection into a display/profile-aware linear gain-map projector that preserves legacy SDR output, keeps HEIC gain-map export as linear SDR base plus linear HDR alternate, clarifies reference white/diffuse white/peak headroom semantics, improves highlight chroma/gamut protection and highlight-only detail restoration, adds PQ/HLG transfer helpers for future direct HDR exports, and documents/verifies the behavior with focused tests and a local commit.

## Architecture Before and After

Before this task, `HDRProjectionConfig` was mostly a collection of headroom and white-point scalar controls. Projection already used RouteMaster as the pair authority and already built SDR base plus HDR alternate before handing the pair to the HEIC/gain-map encoder.

After this task, `HDRProjectionConfig` resolves an explicit `HDRDisplayProfile`:

- `profile_id`
- `color_primaries`
- `output_color_volume`
- `transfer_function`
- `reference_white_nits`
- `peak_nits`
- `max_headroom`
- `black_nits`
- `output_diffuse_white`
- `content_headroom_percentile`

Existing callers remain compatible. A legacy call such as `HDRProjectionConfig(max_headroom=5.0, display_reference_white_nits=203.0)` now builds a default `gain-map-linear-pair` display profile with peak nits derived from reference white times headroom.

## Boundary Decisions

RouteMaster remains the only HDR projection intermediate. The route projectors still return `HDRProjectionResult` from `paper` or `light_table`, and `routemaster_export` still passes the resulting pair to `hdr_photo.save_hdr_photo_heic_from_pair()`.

The HEIC gain-map pair remains a linear pair:

- SDR base: linearized SDR output from `RouteMaster.sdr_legacy_rgb`
- HDR alternate: linear HDR RGB from RouteMaster projection
- Gain map: computed from the linear base and linear alternate

PQ and HLG helpers were added in `spektrafilm.hdr.transfer` for future direct HDR export paths only. They are not called by gain-map pair projection or HEIC pair construction.

## Luminance Semantics

- `reference_white_nits`: display luminance assigned to scene/reference diffuse white for metadata and diagnostics.
- `diffuse_white_scene_anchor`: scene-domain join point where the authored SDR print/light-table look is preserved.
- `output_diffuse_white`: scaling of the HDR extension above the SDR base; it does not rescale the preserved SDR base.
- `peak_nits`: display-profile peak luminance.
- `max_headroom`: peak/reference-white ratio.
- `content_headroom_percentile`: percentile used to measure exported content headroom.
- `black_nits`: carried in display profile and standards metadata as a reserved/display diagnostic floor.

Projection diagnostics now record the display profile, measured content headroom, reference-white calibration, max headroom, output diffuse white, and the linear gain-map pair encoding boundary.

## Highlight Color Protection

The primary color strategy is still route luminance-ratio chroma: `route_look_chroma` when available, otherwise `route_linear_rgb / route_luminance_y`. This preserves route hue and avoids per-channel tone mapping.

A new highlight gamut compression step runs before final clipping. It first tries luminance-preserving compression toward the current luminance axis. If the requested color is outside the output color volume because luminance itself is already above the display limit, it falls back to peak-channel scaling to preserve hue instead of forcing the highlight to neutral white. Diagnostics report the strategy, compressed pixel count, and pre-compression bounds for NumPy projection; the MLX backend performs the same compression without materializing statistics.

Path-to-white remains route-specific and bounded. It is still disabled for `light_table` by default and mild for `paper`, with existing chemical tint guard behavior preserved.

## Highlight Detail Restoration

The old `material_detail_y` math divided the gain by detail and then multiplied by detail again, which largely canceled the detail signal. The new logic applies detail only to the HDR extension:

`hdr_y = base_y + max(target_y - base_y, 0) * bounded_detail_factor`

The detail factor is gated by a smooth mask above diffuse white and bounded by `min_detail` / `max_detail`. This prevents midgray and diffuse-white-and-below regions from changing and caps highlight detail so local noise cannot grow without bound. The chemical paper path uses the same helper for both its chemical gain branch and display-budget branch.

## Research Sources and How They Were Used

- ITU-R BT.2100: used to keep PQ and HLG as separate transfer functions with clear boundaries rather than mixing them into gain-map pair math. Source: https://www.itu.int/rec/R-REC-BT.2100
- ITU-R BT.2408: used for HDR Reference White / diffuse white terminology and the common 203 nit engineering default. In Spektrafilm this is metadata/diagnostic reference white, not an SDR-base rescale. Source: https://www.itu.int/rec/R-REC-BT.2408
- Android Ultra HDR image format: used to confirm the backward-compatible SDR base plus gain map/metadata model and display-adaptive headroom semantics. Source: https://developer.android.com/media/platform/hdr-image-format
- Adobe Gain Map specification: used for base/alternate rendition and headroom framing; adopted as conceptual validation, not as a replacement for Spektrafilm's existing encoder boundary. Source: https://helpx.adobe.com/camera-raw/using/gain-map.html
- ACES Reference Gamut Compression: used to justify explicit saturated-highlight compression instead of silent clipping; adapted conservatively to Spektrafilm's RGB/luminance-ratio route instead of importing an ACES pipeline. Source: https://docs.acescentral.com/system-components/output-transforms/technical-details/gamut-compress/
- Apple HDR/gain-map ecosystem documentation and WWDC material: used to keep the Apple-facing HEIC path backward-compatible and gain-map based; rejected as a reason to PQ-encode the alternate before gain-map calculation. Source: https://developer.apple.com/videos/play/wwdc2023/10181/

## Tests Run

- `.venv/bin/python -m pytest tests/test_hdr_display_profile_projection.py tests/test_hdr_transfer.py -q`
  - Result: `10 passed`, with two warnings from colour's HLG implementation evaluating both branches of an internal `np.where`.
- `.venv/bin/python -m pytest tests/test_hdr_projection_backend.py tests/test_hdr_projection_static_guards.py tests/test_hdr_display_profile_projection.py tests/test_hdr_transfer.py -q`
  - Result: `18 passed`, with the same two HLG warnings.
- `.venv/bin/python -m pytest tests/test_hdr_curve_profiles.py tests/test_hdr_photo.py tests/test_gain_map.py tests/test_color_management.py -q`
  - Result: `243 passed`.
- `python -m pytest tests/test_hdr_curve_profiles.py tests/test_hdr_photo.py tests/test_gain_map.py tests/test_color_management.py -q`
  - Result: not runnable in the pyenv shim environment: `/Users/retriedstormtrooper/.pyenv/versions/3.13.14/bin/python: No module named pytest`. The same test set passed under the repository venv command above.
- `.venv/bin/python -m pytest tests/test_hdr_routemaster_projection.py tests/test_hdr_projection_backend.py tests/test_hdr_projection_static_guards.py tests/test_hdr_routemaster_export.py tests/test_hdr_standards.py tests/test_hdr_display_profile_projection.py tests/test_hdr_transfer.py -q`
  - Result: `74 passed`, with the same two HLG warnings.
- `.venv/bin/python -m pytest --ignore=tests/gui -q`
  - Result: `1700 passed, 8 skipped, 4 xfailed`, with six warnings from existing autoexposure/gamut tests and the new colour HLG helper tests.
- `.venv/bin/python -m pytest tests/gui/test_persistence.py tests/gui/test_state_bridge.py tests/gui/test_controller_output.py tests/gui/test_controller_flow.py tests/gui/test_controller_runtime_module.py tests/gui/test_macos_bridge.py -q`
  - Result: `116 passed`.
- `git diff --check`
  - Result: passed.

## Follow-Up Note

`docs/README.md` was intentionally not modified to avoid conflicts with parallel documentation work. A maintainer should add this report to the docs router/index when that file is next edited.
