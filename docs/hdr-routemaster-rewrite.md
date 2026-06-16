# HDR RouteMaster Rewrite

Date: 2026-06-08

## Goal

The RouteMaster HDR architecture renders one full-resolution photographic
route, stores the shared material state in `RouteMaster`, and derives:

```text
RouteMaster
-> strict legacy SDR projection
-> HDR Light Table projection
-> Idealized HDR Paper projection
-> pre-rendered SDR/HDR pair export
```

HDR is not recovered from an SDR look. SDR is the bounded projection of the
same HDR-capable route/material state.

## Runtime Boundary

Implemented files:

- `src/spektrafilm/runtime/route_master.py`
- `src/spektrafilm/runtime/stages/filming.py`
- `src/spektrafilm/runtime/stages/scanning.py`
- `src/spektrafilm/runtime/pipeline.py`
- `src/spektrafilm/runtime/process.py`

`FilmingStage.expose_with_metadata()` records:

- `scene_y_raw`: scene authority after camera exposure compensation.
- `post_halation_y`: spatial highlight authority after highlight boost,
  diffusion, lens blur, halation, and filming black/white correction, before
  log exposure.

`ScanningStage.scan_master()` records:

- `route_linear_xyz`
- `route_linear_rgb`
- `route_luminance_y`
- `density_cmy`

`ScanningStage.project_sdr_legacy()` keeps the old output transform order:

```text
route_linear_rgb
-> output gamut compression
-> scanner blur / unsharp
-> CCTF
-> clip
```

`ScanningStage.scan()` remains the legacy wrapper and delegates to
`scan_master()` plus `project_sdr_legacy()`.

`RouteMaster.diagnostics` records the legacy SDR output transform policy:

- `output_color_space`
- `output_cctf_encoding`
- `output_clip_min`
- `output_clip_max`

The HDR projection layer uses these flags to decode CCTF SDR exactly once and
to preserve already-linear SDR without accidental darkening.

## RouteMaster Fields

`RouteMaster` stores the MVP route state:

- `mode`: `light_table` or `paper`
- `route_kind`: `film_scan` or `print_scan`
- `route_linear_rgb`
- `route_linear_xyz`
- `route_luminance_y`
- `sdr_legacy_rgb`
- `scene_y_raw`
- `post_halation_y`
- `density_cmy`
- `route_look_chroma`
- `material_detail_y`
- `diagnostics`

Full-resolution spectral density is intentionally not part of the MVP. It can
be added later as an explicit debug/future sidecar.

## SDR Contract

The hard contract is:

```python
SimulationPipeline.process(image) == SimulationPipeline.process_master(image, hdr_mode="paper").sdr_legacy_rgb
```

and, for a film-scan route:

```python
SimulationPipeline(process_params_with_scan_film).process(image)
== SimulationPipeline(...).process_master(image, hdr_mode="light_table").sdr_legacy_rgb
```

The focused tests use `atol=1e-9, rtol=0` for deterministic CPU paths.

## Negative Film

HDR Light Table only accepts a positive film/scan look. A raw negative scan is
diagnostic material, not a public HDR output. For negative film,
`SimulationPipeline.process_master(..., hdr_mode="light_table")` uses the
existing `render_negative_scan_positive_rgb()` path and marks diagnostics with
`profile_kind="positive_negative_scan"`. The positive route derives
`route_linear_xyz` from the positive linear route RGB and marks
`route_linear_xyz_source="positive_render_rgb_to_xyz"`; it no longer aliases
RGB into the XYZ field.

## Projection Layer

Implemented files:

- `src/spektrafilm/hdr/projection.py`
- `src/spektrafilm/hdr/light_table.py`
- `src/spektrafilm/hdr/ideal_paper.py`
- `src/spektrafilm/hdr/routemaster_export.py`

Default color policy:

```text
HDR luminance = route/material/scene-derived HDR luminance
HDR chroma = route_look_chroma
HDR RGB = route_look_chroma * HDR luminance
```

`scene_rgb` is not a default color authority in the RouteMaster projection
path. It remains legacy/auxiliary only.

Idealized HDR Paper uses `HDRProjectionConfig.diffuse_white_scene_anchor` as
the join anchor: scene/material energy at or below that anchor preserves the
legacy SDR print look, while values above it are extended continuously into
display headroom. `HDRProjectionConfig.paper_white` remains a
backward-compatible alias only; new code should not use it as an output
diffuse-white target. `HDRProjectionConfig.output_diffuse_white` scales the HDR
extension above the authored SDR base before headroom and gain-map metadata are
generated; it does not remap the preserved SDR base itself.
`HDRProjectionConfig.headroom_percentile` is used both for content headroom and
for the extension gain percentile.

## Tests

New tests:

- `tests/test_routemaster.py`
- `tests/test_hdr_routemaster_projection.py`
- `tests/test_hdr_routemaster_export.py`
- `tests/test_hdr_profile_cache.py`

They cover:

- RouteMaster field completeness.
- scan master to legacy SDR equivalence.
- `process()` to `process_master(...).sdr_legacy_rgb` equivalence.
- strict SDR equivalence with grain, halation, diffusion, scanner
  blur/unsharp, output gamut compression, CCTF, and clip settings.
- post-halation and density sidecars.
- Light Table paper-parameter isolation.
- Paper response to print exposure and paper profile.
- raw negative rejection and positive negative-scan route acceptance.
- positive negative-scan `route_linear_xyz` derivation from route RGB.
- linear SDR passthrough and one-time CCTF SDR decode.
- paper-white anchor behavior.
- HDR curve monotonicity and paper join continuity.
- route-look chroma preservation.
- gain-map high-frequency cleanliness and shared grain/material field.
- pre-rendered pair HEIC encoder isolation from `prepare_hdr_photo_renditions`.
- single `process_master()` call during RouteMaster export.
- legacy mode alias warnings.
- dynamic profile cache tone/spatial key behavior.
