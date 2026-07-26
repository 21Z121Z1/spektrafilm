# HDR Export Pipeline

Date: 2026-06-08

## New Pair Export Flow

RouteMaster HDR export is:

```text
master = simulator.process_master(image, hdr_mode="light_table" or "paper")
projection = render_hdr_film_pair_from_master(master, hdr_mode=...)
save_hdr_photo_heic_from_pair(path, projection.sdr_rgb, projection.hdr_rgb, ...)
```

The full-resolution photographic route render runs once.

## Encoder Boundary

`src/spektrafilm/utils/hdr_photo.py` now exposes:

```python
save_hdr_photo_heic_from_pair(
    filename,
    sdr_rgb,
    hdr_rgb,
    *,
    color_space,
    headroom=None,
    quality=0.95,
    metadata=None,
    gain_map_mode="rgb",
)
```

This function only validates and encodes an already-rendered SDR/HDR pair. It
does not:

- call `Simulator`;
- call `prepare_hdr_photo_renditions`;
- sample runtime curve profiles;
- inspect film or paper profiles;
- regenerate grain or other spatial material;
- perform HDR recovery from the SDR image.

The old `save_hdr_photo_heic()` and `prepare_hdr_photo_renditions()` path stays
available for legacy callers, but it is no longer the RouteMaster export path.

## RouteMaster Export Helper

`src/spektrafilm/hdr/routemaster_export.py` contains:

- `normalize_hdr_mode()`
- `render_hdr_pair_from_master()`
- `render_hdr_film_pair_from_master()`
- `export_hdr_heic_from_simulator()`

`export_hdr_heic_from_simulator()` calls `process_master()` once, projects the
pair, then calls `save_hdr_photo_heic_from_pair()`.

GUI export now passes the public RouteMaster mode ids (`paper` or
`light_table`) to this helper. Legacy GUI state values are normalized before
export.

The GUI-to-projection conversion lives in
`src/spektrafilm_gui/hdr_settings.py::hdr_projection_config_from_settings()`.
It maps the current diffuse-white GUI control to
`HDRProjectionConfig.diffuse_white_scene_anchor` and
`output_diffuse_white`. The RouteMaster projection preserves the authored SDR
base, then applies `output_diffuse_white` to the HDR extension above that SDR
base before gain-map/headroom metadata is generated. It derives scene authority
from the RouteMaster sidecars and supports only content-percentile headroom
budgeting; incompatible legacy GUI fields raise before export.

## Gain Map Metadata

The projection layer reuses existing format helpers:

- `encode_gain_map_log2()`
- `build_iso_21496_1_gain_map_metadata()`
- `validate_gain_map()`

Gain map metadata is a carrier contract for the rendered pair. It is not where
photographic HDR semantics are created.

## Dynamic Profile Cache

`src/spektrafilm/hdr/profile_cache.py` adds `build_route_profile_cache_key()`
and, since 2026-07-26, the production wiring
`get_dynamic_print_curve_profile(params)`: `export_hdr_heic_from_simulator()`
resamples the paper-mode chemical profile with the simulator's current tone
parameters (deterministic CPU ramp via
`sample_runtime_print_curve_profile()`, ~0.3 s, cached on the key below) and
passes it to `project_hdr_ideal_paper()`. Sampling failures fall back to the
static bundled profile; the origin is recorded in projection diagnostics as
`chemical_profile_origin`.

Since 2026-07-27 the same pattern calibrates the light-table negative
positive render: `get_dynamic_negative_scan_render_metadata(params)` samples a
deterministic neutral ramp through the film-scan route (CPU backend, output
gamut compression and scanner sharpening disabled so the ramp domain equals
the raw scanner RGB the render consumes) and caches the film-base /
density-range references on the light-table variant of the key. The pipeline's
`_positive_render_negative_scan_master()` consumes it, recording
`negative_scan_render_origin` in RouteMaster diagnostics; only if calibration
fails does it fall back to the legacy content-statistics estimate
(`content_statistics_fallback:*`).

Included in the key:

- HDR mode
- route kind
- film stock
- paper stock for paper mode
- camera exposure compensation
- fixed auto exposure EV when supplied
- film density curve gamma
- print density curve morph for paper mode
- print exposure for paper mode
- neutral enlarger filters for paper mode
- preflash exposure for paper mode
- scanner black/white correction and levels
- viewing illuminant
- output color space
- diffuse-white scene-anchor policy for paper mode

Excluded from the key:

- grain random field
- halation image content
- diffusion image content
- lens blur image content
- scanner blur/unsharp image content
- paper glare spatial content

Spatial and random material enters HDR through `RouteMaster`, not through a
profile cache baseline.

## SDR Encoding Boundary

RouteMaster projection treats `sdr_legacy_rgb` according to its recorded output
transform flags:

- `output_cctf_encoding=True`: decode the legacy SDR projection to linear RGB
  once before pair encoding.
- `output_cctf_encoding=False`: preserve already-linear SDR as-is.

This keeps the pair encoder independent from the runtime while avoiding double
decoding or accidental linear-SDR darkening.

## ISO 21496-1 / HEIC Validation Boundary

RouteMaster HEIC export keeps CoreImage as the default writer because it is the
Mac-compatible path. Spektrafilm now validates the file after CoreImage returns
instead of trusting marker strings.

`src/spektrafilm/utils/heif_iso21496.py` parses the relevant HEIF item graph:

- `ftyp`
- file-level `meta`
- `pitm`
- `iinf` / `infe`
- `iref`
- `iprp` / `ipco` / `ipma`
- `iloc`
- `idat`

Hard errors reject the export and remove the partial output:

- `tmap` item and `tmap` compatible brand must agree.
- The `tmap` item must have exactly one `dimg` reference with two inputs, ordered
  base image first and gain-map image second.
- The base input must have `colr`.
- The gain-map input must be hidden and must have `nclx` `colr` with colour
  primaries and transfer characteristics set to `2`.
- The `tmap` item must have alternate-image `colr`.
- The `ToneMapImage` payload version must be `0`.
- The remaining payload must parse as ISO 21496-1 C.2 `GainMapMetadata`.
- Metadata must have finite values, `minimum_version == 0`,
  `writer_version >= minimum_version`, non-negative and distinct headrooms,
  `gain_map_max >= gain_map_min`, and `gamma > 0`.

Advisory conditions such as missing `clli` remain warnings so Mac-compatible
files are not rejected for optional viewing-condition hints.

CoreImage currently writes the correct `tmap` item graph, but its C.2 channel
range fields can appear in the opposite order from the ISO 21496-1 C.2 markdown
reference. `repair_coreimage_tmap_min_max_order()` performs a same-size repair
only when every channel exhibits that exact invalid `min > max` pattern, then the
normal validator must pass. Arbitrary malformed HEIF files still fail closed.

`save_gain_map_heif()` follows the same rule: if the ISOBMFF patcher is
unavailable, declines the file, or the post-patch ISO validator reports hard
errors, Spektrafilm deletes the partial HEIF and raises instead of leaving a
non-`tmap` file while claiming ISO 21496-1 support.

The real macOS smoke gate is
`tests/test_hdr_routemaster_export.py::test_coreimage_pair_export_writes_iso_tmap_and_is_mac_openable`.
On Darwin with `swift`/`xcrun` and `sips`, it writes a small SDR/HDR pair,
validates the ISO `tmap` graph, checks `sips` openability, and checks Swift
ImageIO can create a `CGImage` from the result. Apple Photos visual HDR
activation remains a separate manual/device acceptance boundary.
