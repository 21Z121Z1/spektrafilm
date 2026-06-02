# Film-Scan-Aware Negative Positive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development before changing implementation code. This plan is the working goal document requested for the negative-film `film_scan_aware` fix.

**Goal:** Make `film_scan_aware` HDR use a positive film-scan SDR/profile route for negative film stocks while preserving raw negative scans as diagnostics only.

**Architecture:** Keep the existing `scan_film=True` runtime route and `film_scan_aware` HDR mode, but split film-scan sampling into two explicit routes: `raw_negative_scan` and `positive_negative_scan`. Raw negative scan remains the physical decreasing density response. Positive negative scan renders that raw scan into a positive SDR film-scan look, and only that positive increasing curve is eligible for `safe_for_profile_aware_hdr=True` and HDR gain construction.

**Tech Stack:** Python 3.13, NumPy, Spektrafilm runtime pipeline, `ScanningStage`, `sample_runtime_film_scan_curve_profile()`, profile-preserving HDR curves, pytest.

---

## Current Code Path

`HDRPhotoMapping.hdr_mapping_mode` currently accepts `generic`, `profile_aware`, and `film_scan_aware` in `src/spektrafilm/utils/hdr_photo.py`. `prepare_hdr_photo_renditions()` dispatches both profile modes to `_prepare_curve_profile_renditions()`. For `film_scan_aware`, `_resolve_curve_profile()` either uses an explicit `curve_profile` or calls `sample_runtime_film_scan_curve_profile(film=mapping.film)`.

`_prepare_curve_profile_renditions()` requires `scene_luminance`, checks that `film_scan_aware` receives a `route="film_scan"` profile, rejects profiles whose `polarity` is not `"increasing"` or whose `safe_for_profile_aware_hdr` is false, computes `s_profile` and `h_profile`, then applies `hdr_gain = h_profile / s_profile` to the authored SDR look. The safety check is correct; the bug is that negative-film sampling can still feed it a raw decreasing scan.

`SimulationPipeline._pipeline()` switches on `params.io.scan_film`. With `scan_film=False`, the route is:

1. `FilmingStage.expose()`
2. `FilmingStage.develop()`
3. `PrintingStage.expose()`
4. `PrintingStage.develop()`
5. `ScanningStage.scan()`

With `scan_film=True`, the print and paper route is bypassed:

1. `FilmingStage.expose()`
2. `FilmingStage.develop()`
3. `ScanningStage.scan()`

That bypass is required for film-scan-aware HDR and must remain intact.

## How `sample_runtime_film_scan_curve_profile()` Samples

The sampler in `src/spektrafilm/utils/hdr_curve_profiles.py` creates or receives runtime params, deep-copies them through `_prepare_profile_sampling_params()`, and forces:

- `io.scan_film=True`;
- stochastic and spatial effects disabled;
- scanner LUT and enlarger LUT disabled;
- auto exposure disabled;
- input and output CCTF disabled;
- scanner output min/max clipping disabled for film-scan profile sampling.

It then builds a neutral `scene_y` ramp with `neutral_scene_y_samples()`, processes it through `Simulator(sampled_params).process()`, and passes the resulting RGB samples to `build_curve_profile_sample(route="film_scan", paper=None)`.

The current defect is that this sampled output is the direct scan of developed film density. For a negative film stock such as `kodak_gold_200`, that raw scan is a diagnostic negative image: larger scene luminance develops denser film, transmits less scan light, and therefore produces lower raw scan luminance. On a small live baseline, `kodak_gold_200` returned `polarity="decreasing"` and `safe_for_profile_aware_hdr=False`.

## Why `ScanningStage` Bypasses Print/Paper

`ScanningStage._density_to_rgb()` chooses film density/base/viewing illuminant when `io.scan_film=True`, and print density/base/viewing illuminant plus print glare when `io.scan_film=False`. The direct film-scan route therefore does not use paper profile, print exposure, enlarger filters, preflash, print diffusion, or print glare. That isolation is correct and must be preserved.

The fix must stay inside the film-scan route. It must not route negative film through `PrintingStage`, must not use paper profiles as a workaround, and must not let print/paper parameters affect `film_scan_aware` profile sampling.

## Why Raw Negative Scan Is Decreasing

Negative film density increases as scene exposure increases. A scanner measuring the developed negative sees higher density as lower transmittance. In the raw negative scan:

`scene_y up -> film exposure/development up -> density up -> transmittance down -> raw scan RGB/Y down`

That is physically meaningful as a debug/diagnostic curve, but it is not an SDR positive image curve.

## Why HDR Profile Curves Must Be Positive And Increasing

Profile-aware HDR constructs `s_profile` as the SDR profile luminance at a scene luminance coordinate and `h_profile` as the HDR target luminance at the same coordinate. The later gain is `h_profile / s_profile`. If `s_profile` decreases while scene luminance increases, highlights can be interpreted as darker SDR profile values, making gain ratios unstable and reversing display ordering. The safety check must therefore keep rejecting decreasing profiles.

For `film_scan_aware`, the required meaning is:

`scene linear luminance -> film exposure/development -> film density/raw negative scan -> negative-to-positive scan rendering -> positive film-scan SDR look -> profile-aware HDR target/gain`

The profile source and the authored SDR base must be the same positive film-scan look.

## Route Definitions

`raw_negative_scan`:

- physical bottom-up scan of developed negative density;
- allowed to classify as `polarity="decreasing"` for negative film;
- only for diagnostics, debug output, and curve checks;
- never allowed as `film_scan_aware` HDR profile input;
- must not be marked `safe_for_profile_aware_hdr=True` when decreasing.

`positive_negative_scan`:

- a negative-film scan rendered into a positive image in the film-scan route;
- required for negative film default `film_scan_aware` sampling;
- required to classify as `polarity="increasing"`;
- required to be `safe_for_profile_aware_hdr=True`;
- used by SDR base generation, profile sampling, and HDR gain construction.

Positive/reversal film:

- should not be passed through the negative inversion/rendering model;
- keeps its natural film-scan response;
- must stay increasing and safe when the stock is already positive/reversal.

## Implementation Plan

1. Add tests first in `tests/test_hdr_curve_profiles.py`:
   - raw `kodak_gold_200` diagnostic sampling returns `profile_kind="raw_negative_scan"`, may be decreasing, and is not safe;
   - default `sample_runtime_film_scan_curve_profile(film="kodak_gold_200")` returns `profile_kind="positive_negative_scan"`, `polarity="increasing"`, `safe_for_profile_aware_hdr=True`, monotonic `sdr_luminance_y`, no hard highlight plateau, and no early `[0, 1]` clipping;
   - `fujifilm_provia_100f` and/or `kodak_ektachrome_100` returns a positive/reversal film-scan profile without applying negative inversion;
   - paper/enlarger/print parameter changes do not alter film-scan profiles, while film/scanner parameters do.

2. Add tests in `tests/test_hdr_photo.py`:
   - a raw negative diagnostic profile is rejected by `film_scan_aware`;
   - a positive negative-film profile can drive `h_profile >= s_profile`;
   - the SDR base supplied to `film_scan_aware` stays the positive film-scan look;
   - scene ordering is preserved: brighter scene samples produce brighter SDR/HDR output than darker samples.

3. Implement route separation in `src/spektrafilm/utils/hdr_curve_profiles.py`:
   - add a `FilmScanProfileKind` type with `raw_negative_scan`, `positive_negative_scan`, and `positive_film_scan`;
   - add sample metadata field `profile_kind`;
   - add an optional argument such as `scan_profile_kind="positive"` / `diagnostic_raw_negative=False` so default calls return the positive profile while diagnostic calls can request raw negative;
   - resolve film type from `params.film.is_negative` / `params.film.is_positive`, not from curve shape alone.

4. Implement negative-to-positive rendering:
   - process the neutral ramp through the existing film-scan route to get raw scanner RGB;
   - for negative film default sampling, convert raw scan values to a positive rendering in linear scan space before `build_curve_profile_sample()`;
   - estimate scanner black/white normalization from the sampled raw curve using robust low/high references after sorting by scene luminance;
   - invert the normalized raw scan so higher scene exposure maps to higher positive luminance;
   - apply per-channel balancing and a smooth display-domain shoulder without hard clipping the highlight profile;
   - avoid a blind final `1.0 - output` on arbitrary encoded/clipped output. The operation is allowed only because sampling disables output CCTF and scanner clipping, so the inversion happens on linear scanner RGB after finite normalization.

5. Keep `ScanningStage` and `SimulationPipeline` route behavior unchanged unless an export/runtime helper is needed to generate the positive SDR base. If a helper is added, it must still operate after `scan_film=True` scanning and must not call `PrintingStage`.

6. Update docs:
   - this plan document;
   - `docs/hdr-film-scan-aware.md`;
   - add `docs/film-scan-aware-hdr.md` if the canonical requested path is not already present.

7. Verify and self-review:
   - prove the default negative film profile is positive and monotonic by test and by a live diagnostic printout;
   - prove raw negative diagnostic remains decreasing/unsafe;
   - prove positive/reversal film is not inverted;
   - prove paper/print parameters are isolated;
   - run the requested tests and `git diff --check`.

## Acceptance Criteria

- `sample_runtime_film_scan_curve_profile(film="kodak_gold_200")` defaults to a positive negative-film scan rendering.
- Default negative-film film-scan profile has `route="film_scan"`, `profile_kind="positive_negative_scan"`, `polarity="increasing"`, and `safe_for_profile_aware_hdr=True`.
- Raw negative diagnostic profile has `profile_kind="raw_negative_scan"` and cannot be used as safe `film_scan_aware` HDR input.
- `s_profile` is monotonic increasing for the default negative-film film-scan profile.
- `h_profile >= s_profile` and HDR gain has no highlight explosion caused by a tiny denominator.
- Highlight headroom is smooth and not erased by a hard scanner `[0, 1]` clamp.
- `film_scan_aware` SDR base, profile sampling, and HDR gain are all based on the same positive film-scan route.
- Positive/reversal films are not inverted by negative-film logic.
- `generic`, `profile_aware`, print-scan-aware behavior, SDR preview/output defaults, `io.scan_film=False`, and GUI parameter mapping remain unchanged.

## Test Commands

Primary requested validation:

```bash
uv run --extra dev pytest tests/test_hdr_photo.py tests/test_hdr_curve_profiles.py -q
```

Focused development validation:

```bash
.venv/bin/python -m pytest tests/test_hdr_curve_profiles.py -q
.venv/bin/python -m pytest tests/test_hdr_photo.py -q
```

Final hygiene:

```bash
.venv/bin/python -m compileall -q src tests
git diff --check
```

If `uv` or the project venv fails for environment reasons, report it separately from implementation failures and include any successful fallback evidence.

## Completion Self-Check

Before marking the goal complete, answer this directly:

Did the implementation prove that `film_scan_aware` outputs a positive monotonic increasing curve for negative film, instead of merely bypassing or weakening the polarity safety check?

If the answer is not backed by tests and live sampled metrics, continue fixing.
