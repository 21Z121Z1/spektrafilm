# Film-Scan-Aware HDR Mapping

`film_scan_aware` is an HDR export mode for cases where the authored SDR look is a scan of the developed film, not a scan of a virtual paper print.

## Modes

| Mode | Profile source | Sidecar | Use case |
| --- | --- | --- | --- |
| `generic` | No profile curve | Optional | Basic HDR graft from scene luminance. |
| `profile_aware` | `route="print_scan"` film + paper profile | Required | Preserve a virtual paper-print look while recovering HDR headroom. |
| `film_scan_aware` | `route="film_scan"` film exposure/development/scan profile | Required | Preserve a film-scan look and map film density response into an HDR display rendition. |

`profile_aware` remains unchanged. It models the complete film to paper to scan chain and uses the sampled print-scan SDR curve as the source profile.

`film_scan_aware` is separate. It samples the runtime with `io.scan_film=True`, so the curve is built from film exposure, film development, and scanner response. The printing stage is bypassed.

## Physical Semantics

Paper is a reflective medium with a limited paper white and print density range. It can produce a convincing SDR print look, but it is not an HDR display medium.

Film-scan-aware HDR treats film as the recording medium and the scanner as the bridge into a digital HDR display path. It does not mean film itself displays HDR. It means the film density response can carry scene separation that is better mapped into HDR before being compressed by virtual paper.

## What Affects The Curve

`film_scan_aware` curve sampling is intended to respond to:

- film stock,
- film exposure and film density curve behavior when represented in the sampling params,
- film gamma,
- couplers,
- halation when it changes the non-spatial neutral response,
- scanner white and black correction.

Curve sampling disables stochastic and spatial effects. Grain, lens blur, unsharp mask, and similar spatial terms may still be visible in the authored image look, but they are not part of the one-dimensional neutral curve profile.

`film_scan_aware` does not use:

- print paper as a profile key,
- print exposure,
- enlarger Y/M/C filters,
- preflash,
- print diffusion,
- print glare.

## Export Behavior

The SDR base is always the supplied authored look clipped to SDR range. For `film_scan_aware`, that authored look should be a film-scan output, so run/export from the `scan_film` route when using this mode.

The HDR target reuses `build_profile_preserving_hdr_curve()` and the existing `modern_recovery_peak_budget` option. The new mode changes the profile source and route semantics; it does not introduce a separate recovery algorithm.

## Sampling Contract

The film-scan sampler:

- uses a neutral `scene_y` ramp,
- forces `params.io.scan_film=True`,
- disables stochastic and spatial effects,
- disables auto exposure,
- disables output CCTF,
- disables scanner output min/max clipping during profile sampling.

Disabling output clipping is important because a `[0, 1]` scanner clamp would hide highlight separation in the sampled curve and make the HDR target look like a clipped SDR scan.

## Limitations

- Clipped RAW or scene input cannot be reconstructed by any mapping mode.
- Positive/reversal film can have much lower exposure latitude than negative film.
- HDR output is still bounded by selected headroom and gamut mapping.
- GUI export preserves the current output layer. For true film-scan-aware SDR preservation, the output layer should have been generated with `scan_film` enabled.
