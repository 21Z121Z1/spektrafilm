# HDR Export Pipeline

Date: 2026-06-05

## New Pair Export Flow

RouteMaster HDR export is:

```text
master = simulator.process_master(image, hdr_mode="light_table" or "paper")
projection = render_hdr_pair_from_master(master, hdr_mode=...)
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
- `export_hdr_heic_from_simulator()`

`export_hdr_heic_from_simulator()` calls `process_master()` once, projects the
pair, then calls `save_hdr_photo_heic_from_pair()`.

## Gain Map Metadata

The projection layer reuses existing format helpers:

- `encode_gain_map_log2()`
- `build_iso_21496_1_gain_map_metadata()`
- `validate_gain_map()`

Gain map metadata is a carrier contract for the rendered pair. It is not where
photographic HDR semantics are created.

## Dynamic Profile Cache

`src/spektrafilm/hdr/profile_cache.py` adds `build_route_profile_cache_key()`.

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
- paper white anchor policy for paper mode

Excluded from the key:

- grain random field
- halation image content
- diffusion image content
- lens blur image content
- scanner blur/unsharp image content
- paper glare spatial content

Spatial and random material enters HDR through `RouteMaster`, not through a
profile cache baseline.

