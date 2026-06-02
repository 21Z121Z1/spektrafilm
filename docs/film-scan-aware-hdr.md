# Film-Scan-Aware HDR

`film_scan_aware` is positive film-scan HDR. It is not a raw negative preview mode.

The intended negative-film route is:

```text
scene linear luminance
-> film exposure/development
-> film density / raw negative scan
-> negative-to-positive scan rendering
-> positive film-scan SDR look
-> profile-aware HDR target/gain
```

For positive or reversal film, the route is shorter because the film scan is already a positive image:

```text
scene linear luminance
-> film exposure/development
-> positive/reversal film scan
-> positive film-scan SDR look
-> profile-aware HDR target/gain
```

## Mode Split

| Mode | Profile source | SDR base meaning | Print/paper route |
| --- | --- | --- | --- |
| `generic` | No profile curve | Supplied authored look | Not profile-driven |
| `profile_aware` | `route="print_scan"` film to paper to scan | Virtual paper-print SDR look | Uses print/paper |
| `film_scan_aware` | `route="film_scan"` positive film-scan profile | Positive film-scan SDR look | Bypasses print/paper |

`profile_aware` is print/profile-aware HDR recovery: film -> paper/print -> scan SDR plus HDR recovery from the scene sidecar.

`film_scan_aware` is film-scan HDR: film -> scan -> positive rendering SDR plus HDR recovery from the same positive film-scan curve. Paper profile, print exposure, enlarger filters, preflash, print diffusion, and print glare do not define this profile.

## Raw Negative Scan Is Diagnostic Only

Negative film density increases as scene exposure increases. A raw negative scan therefore has inverted luminance ordering:

```text
scene_y increases -> negative density increases -> transmittance decreases -> raw scan luminance decreases
```

That raw scan is physically meaningful, but it is not safe as a profile-aware HDR curve. It may be sampled as `profile_kind="raw_negative_scan"` for diagnostics. It is allowed to classify as `polarity="decreasing"`, but it must not be marked `safe_for_profile_aware_hdr=True` and must not be used as `film_scan_aware` HDR input.

## Positive Negative-Film Scan Rendering

For negative film, the default `sample_runtime_film_scan_curve_profile()` output is `profile_kind="positive_negative_scan"`.

The renderer works in the linear, unclipped scanner RGB sampling space:

1. sample the raw negative film scan with `io.scan_film=True`;
2. estimate clear-film and dense-negative scanner references per channel;
3. convert raw transmittance to relative density;
4. normalize per-channel density range for scanner white/black balance;
5. apply a soft positive display shoulder.

This is not a blind `1.0 - output` over arbitrary display RGB. The operation is only valid because profile sampling disables output CCTF and final scanner clipping, so it works on linear scanner RGB before SDR clipping can erase highlight shape.

The generated profile stores `negative_scan_render` metadata. `film_scan_aware` uses that same metadata to render the supplied raw negative scan into the positive SDR base before applying HDR gain. That keeps the SDR base, profile sampling, and HDR gain on the same positive film-scan route.

## Why The Curve Must Be Increasing

The profile-preserving HDR path builds:

- `s_profile`: the SDR profile luminance at the scene-luminance coordinate;
- `h_profile`: the HDR target luminance at the same coordinate;
- `hdr_gain = h_profile / s_profile`.

If `s_profile` is decreasing, brighter scene values can map to darker profile values. That reverses display ordering and can make highlight gain unstable around small denominators. Therefore `safe_for_profile_aware_hdr=True` is only valid for positive, increasing profile curves. The polarity safety check must stay strict; the profile itself must be rendered into an increasing positive curve.

## Positive/Reversal Film

Positive and reversal stocks, such as `fujifilm_provia_100f` and `kodak_ektachrome_100`, are not passed through negative inversion. Their default film-scan profile kind is `positive_film_scan`, and their natural increasing scan response is used directly.

## Sampling Contract

Film-scan profile sampling:

- uses a neutral `scene_y` ramp;
- forces `params.io.scan_film=True`;
- bypasses `PrintingStage`;
- disables stochastic and spatial effects;
- disables auto exposure;
- disables output CCTF;
- disables final scanner min/max clipping for profile sampling;
- preserves scanner white/black behavior and film-render parameters that are part of the film-scan route.

Print/paper parameters are isolated from `film_scan_aware`. Changing paper profile, print exposure, enlarger filters, preflash, or print glare should not change a film-scan profile. Changing film stock, film curve/gamma behavior, or scanner correction behavior can change it.

## Limitations

- No HDR mode can restore information that was already clipped in the input RAW or scene source.
- Scanner/gamut/headroom constraints still bound the final output.
- The positive negative-film renderer is a pragmatic density-normalized scan rendering model, not a complete color-managed scanner inversion model.
- Simple `1.0 - output` over final display RGB is not recommended and is not the implemented model.
- SDR export still clips the authored SDR base to `[0, 1]`; the profile sampler is less-clipped so HDR gain can see highlight shape before SDR clipping.

## Validation

Core validation commands:

```bash
uv run --extra dev pytest tests/test_hdr_photo.py tests/test_hdr_curve_profiles.py -q
.venv/bin/python -m compileall -q src tests
git diff --check
```

Required invariants:

- `kodak_gold_200` raw diagnostic scan can be decreasing and unsafe.
- `kodak_gold_200` default film-scan profile is `positive_negative_scan`, increasing, and safe.
- positive/reversal film is not negative-inverted.
- `h_profile >= s_profile` for profile-preserving HDR.
- negative-film SDR base, profile sampling, and HDR gain use the same positive-rendering metadata.
