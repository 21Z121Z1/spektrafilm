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

The positive render's film-base and per-channel density-range references are
calibrated from a deterministic neutral ramp through the film-scan route with
the current film-side tone parameters
(`spektrafilm.hdr.profile_cache.get_dynamic_negative_scan_render_metadata()`,
cached on the film-scan cache key; ramp domain matches the raw
pre-gamut-compression scanner RGB the render consumes). Image content never
influences the calibration, so reframing or cropping the same scene keeps
identical positive rendering and a global scene/illuminant cast survives the
inversion instead of being auto-white-balanced away. The metadata origin is
recorded in diagnostics as `negative_scan_render_origin`
(`dynamic_resample`/`dynamic_resample_cached`; a
`content_statistics_fallback:*` origin marks the legacy composition-dependent
estimate that remains only as a fail-safe).

Like the paper mode, the projection keeps the authored SDR base pixel-for-pixel
at or below the diffuse-white anchor (masked on the light table's own
post-halation authority); only the extension zone above the anchor is rebuilt
from route chroma. The extension desaturates toward white with the same
strength as the paper mode (dyes on a light table go transparent toward the
illuminant), Hunt-scaled with headroom and reported as
`path_to_white_strength_effective`.

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

The chemical profile itself comes from one of two origins (recorded in
diagnostics as `chemical_profile_origin`):

- `dynamic_resample` — the export path resamples the print-scan curve with the
  simulator's *current* tone parameters (film density curve gamma, print
  exposure, enlarger neutral filters, print curve morph/Chemistry, preflash)
  via `spektrafilm.hdr.profile_cache.get_dynamic_print_curve_profile()`, so
  the HDR shoulder metrics follow user adjustments. Results are cached on the
  tone-parameter cache key.
- `static_bundled` — direct projection calls without a dynamic profile use the
  factory-sampled `(film, paper)` profile from
  `data/hdr_curve_profiles/curve_profiles_v2.json` (also the fallback when
  dynamic sampling fails).

An unsafe dynamic profile (for example a user curve morph that breaks
monotonicity) goes through the same safety classification and falls back to
the generic scene extension with a diagnostic reason.

The extension span above the diffuse-white anchor is fixed by the configured
`max_headroom` (`extension_span_policy="fixed_max_headroom"`); content
statistics only bound the final headroom metadata. Crops or framing changes of
the same scene therefore keep identical per-pixel rendering. The path-to-white
desaturation strength scales with `log2(max_headroom)` relative to the 4.0
reference headroom (Hunt effect: brighter extension needs stronger
desaturation), reported as `path_to_white_strength_effective`.

Responds to:

- film exposure
- print exposure
- film stock
- paper profile
- paper tone/density curve and shoulder (including Chemistry/curve morph via
  dynamic profile resampling)
- diffuse-white scene anchor
- highlight-boost reconstruction (`halation.boost_ev/boost_range/protect_ev`);
  the scene energy authority `scene_y_raw` is sampled after highlight boost,
  so reconstructed pre-clip irradiance drives HDR extension
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
RouteMaster export boundary. The panel exposes only the projection's real
degrees of freedom: mapping mode, peak headroom, a reference-white EV trim,
HEIC quality, and (in the collapsed Advanced area) headroom percentile and
gain-map mode. Everything else is fixed by the RouteMaster contract rather
than validated at export time: the authored SDR base is always the preserved
base rendition, scene authority always comes from the film pipeline, the
diffuse-white anchor sits at scene 1.0 (trimmed by the EV control), the HDR
delta is encoded 1:1 (no output diffuse-white rescaling), and headroom
budgeting is always content-percentile based. Legacy persisted GUI states
containing the removed fields (`hdr_scene_source`, `hdr_diffuse_white_target`,
`hdr_reference_white_mode`, `hdr_output_diffuse_white`,
`hdr_display_reference_white_nits`, `hdr_headroom_mode`, `preserve_sdr_base`)
load cleanly; those keys are dropped on load.

## Color Policy

Both public modes default to route-look chroma:

```text
route_chroma = route_linear_rgb / route_luminance_y
hdr_rgb = route_chroma * hdr_luminance_y
```

This prevents the HDR projection from silently restoring RAW/source chroma that
the film, scan, or print route intentionally changed.
