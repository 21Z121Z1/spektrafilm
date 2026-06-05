# HDR Modes

Date: 2026-06-05

Spektrafilm exposes two RouteMaster HDR modes.

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
- paper white
- preflash
- enlarger filters
- paper glare
- paper texture

Positive and reversal film can be routed directly. Negative film cannot be
exported as a raw negative HDR scan; it must first become a positive film-scan
look. The current RouteMaster path uses positive negative-scan rendering and
rejects diagnostic raw negative masters in `project_hdr_light_table()`.

## Idealized HDR Paper

Public id: `paper`

Meaning:

```text
film -> photographic paper print -> idealized digital HDR paper -> HDR display
```

Route kind: `print_scan`

Real photographic paper is a reflective medium and cannot physically carry HDR
display headroom. Idealized HDR Paper is a counterfactual digital medium:

- below paper white, it follows the real photographic print/SDR look;
- above paper white, it uses scene/material-derived energy to extend highlights
  into HDR display headroom.

Responds to:

- film exposure
- print exposure
- film stock
- paper profile
- paper tone/density curve and shoulder
- paper white anchor
- halation
- film grain and dye-cloud-like density structure
- paper-side diffusion
- scanner/final display transform
- HDR headroom policy
- HDR color policy

## Legacy Compatibility

The old mapping names remain compatibility aliases in
`spektrafilm.hdr.routemaster_export.normalize_hdr_mode()`:

- `film_scan_aware` -> `light_table`
- `profile_aware` -> `paper`
- `generic` -> legacy/internal fallback mapped to `paper` with a warning

These aliases are not the public RouteMaster HDR modes.

## Color Policy

Both public modes default to route-look chroma:

```text
route_chroma = route_linear_rgb / route_luminance_y
hdr_rgb = route_chroma * hdr_luminance_y
```

This prevents the HDR projection from silently restoring RAW/source chroma that
the film, scan, or print route intentionally changed.

