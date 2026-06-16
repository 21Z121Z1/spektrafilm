# HDR Modes

Date: 2026-06-08

Spektrafilm exposes two RouteMaster HDR modes.

The GUI HDR export selector exposes only these public ids. Older project files
or scripted callers that still contain legacy mode strings are normalized at
load/export boundaries.

## HDR Light Table

Public id: `light_table`

Meaning:

```text
film -> scan / light table / transmissive display -> HDR display
```

Route kind: `film_scan`

Responds to:

- film exposure
- camera exposure compensation
- auto exposure when enabled
- film stock
- film density curve
- film dye response
- halation
- film grain and dye-cloud-like density structure
- camera diffusion
- lens blur
- scanner/scan rendering
- HDR headroom policy
- HDR color policy

Does not respond to:

- print exposure
- paper profile
- paper density curve
- paper shoulder
- paper diffuse-white anchor
- preflash
- enlarger filters
- paper glare
- paper texture

Positive and reversal film can be routed directly. Negative film cannot be
exported as a raw negative HDR scan; it must first become a positive film-scan
look. The current RouteMaster path uses positive negative-scan rendering and
rejects diagnostic raw negative masters in `project_hdr_light_table()`. The
positive negative-scan route stores a derived XYZ sidecar instead of reusing
RGB as fake XYZ.

## Idealized HDR Paper

Public id: `paper`

Meaning:

```text
film -> photographic paper print -> idealized digital HDR paper -> HDR display
```

Route kind: `print_scan`

Real photographic paper is a reflective medium and cannot physically carry HDR
display headroom. Idealized HDR Paper is a counterfactual digital medium:

- at or below the diffuse-white scene anchor, it follows the real photographic
  print/SDR look;
- above the diffuse-white scene anchor, it uses scene/material-derived energy to
  extend highlights into HDR display headroom.

Internally, the paper projection first tries `paper_rolloff_strategy="chemical_print"`.
That strategy uses the exact sampled film+paper print-scan curve when the
profile is increasing, marked safe, has valid RGB samples, and the scene has
headroom above diffuse white. Missing, unsafe, non-print-scan, or SDR-only
inputs fall back to the generic scene-extension path with diagnostics rather
than claiming natural chemical rolloff.

Responds to:

- film exposure
- print exposure
- film stock
- paper profile
- paper tone/density curve and shoulder
- diffuse-white scene anchor
- halation
- film grain and dye-cloud-like density structure
- paper-side diffusion
- scanner/final display transform
- HDR headroom policy
- HDR color policy

## Legacy Compatibility

The old mapping names remain compatibility aliases in
`spektrafilm.hdr.routemaster_export.normalize_hdr_mode()` and GUI state
normalization:

- `film_scan_aware` -> `light_table`
- `profile_aware` -> `paper`
- `generic` -> legacy/internal fallback mapped to `paper` with a warning

These aliases are not the public RouteMaster HDR modes.

## GUI Export Boundary

GUI HEIC export builds `HDRProjectionConfig` from `HDRExportSettings` at the
RouteMaster export boundary. The public GUI settings always preserve the
authored SDR base. Compatibility fields that are not meaningful for RouteMaster
projection fail closed instead of being silently ignored: `preserve_sdr_base`
must stay true, `hdr_scene_source` must stay `output_layer_metadata`, and
`hdr_headroom_mode` must stay `content_percentile`.

## Color Policy

Both public modes default to route-look chroma:

```text
route_chroma = route_linear_rgb / route_luminance_y
hdr_rgb = route_chroma * hdr_luminance_y
```

This prevents the HDR projection from silently restoring RAW/source chroma that
the film, scan, or print route intentionally changed.
