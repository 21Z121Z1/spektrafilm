# Profile-Aware HDR Audit Report

Date: 2026-06-01

## Executive Summary

Current `profile_aware` is mostly coherent as an authored HDR recovery path: it preserves the user-authored SDR look, uses `scene_luminance` as the HDR coordinate, applies profile-derived gain through `h_profile / s_profile`, and rejects explicitly unsafe decreasing profiles. It should be described as print/profile-aware HDR recovery, not as physical HDR paper output.

No Critical blocker was found for the default path with the current curve database. I did find one Major implementation bug: `HDRPhotoMapping.max_headroom` is ignored in the profile-aware path when the profile default `safe_max_headroom` is higher. I also found one Major validation gap: future curve samples with a single local monotonicity violation can still be classified as safe if summary slopes remain positive.

Recommendation: keep using `profile_aware` for default exports after documenting its semantics, but fix the `max_headroom` cap before claiming mapping-level headroom controls are honored. Keep any `film_scan_aware` mode as a separate route/mode; do not fold it into this audit or rename existing behavior without an explicit migration.

## Evidence

### Code Paths Read

- `src/spektrafilm/utils/hdr_photo.py`
  - `HDRPhotoMapping` declares `hdr_mapping_mode`, `max_headroom`, profile-preserving controls, color recovery controls, and modern budget controls at lines 56-133.
  - `__post_init__()` validates enum/range values at lines 135-238.
  - `prepare_hdr_photo_renditions()` dispatches `profile_aware` separately from generic mapping at lines 478-489.
  - `_prepare_profile_aware_renditions()` requires `scene_luminance`, resolves a static or dynamic profile, rejects unsafe/non-increasing profiles, builds `s_profile`/`h_profile`, computes `hdr_gain`, applies color recovery, and returns the clipped SDR/HDR pair at lines 536-637.
  - `_apply_hdr_color_recovery()` implements `off`, `source_chroma`, `bounded_look_chroma`, chroma limiting, path-to-white, and gamut compression at lines 640-757.
  - `_content_headroom()` uses a robust percentile instead of `np.max()` at lines 996-1008.
- `src/spektrafilm/utils/hdr_curve_profiles.py`
  - Current working tree has route-aware `HDRCurveProfile` / `FilmPrintHDRCurveProfile` alias fields at lines 40-59.
  - `_classify_polarity()` allows a small count of monotonicity violations at lines 96-106.
  - `build_curve_profile_sample()` computes safety from polarity, white, midtone slope, and highlight slope at lines 147-208.
  - `budget_recovery_gain_ev()` preserves profile baseline and scales only recovery gain at lines 688-810.
  - `profile_modern_recovery_budgeted_gain_ev()` computes compressed EV and budgeted gain at lines 813-887.
  - `build_profile_preserving_hdr_curve()` dispatches strict vs modern, enforces min gain and monotonic HDR output, and returns diagnostics at lines 980-1138.

### Test Commands

- Requested commands:
  - `uv run --extra dev pytest tests/test_hdr_photo.py -q`
  - `uv run --extra dev pytest tests/test_hdr_curve_profiles.py -q`
- Result: both commands produced no pytest output for more than two minutes and were terminated. Exit after termination: `143`.
- Environment check: `.venv/bin/python -c "print(...)"` / Homebrew Python 3.13 hung in this execution environment; `/opt/homebrew/bin/python3.12` was killed with `-9`. This is an environment/runtime issue, not an implementation failure.
- Alternative evidence command:
  - `/Users/retriedstormtrooper/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m py_compile src/spektrafilm/utils/hdr_photo.py src/spektrafilm/utils/hdr_curve_profiles.py tests/test_hdr_photo.py tests/test_hdr_curve_profiles.py`
  - Result: passed.

### Minimal Experiments

Run with bundled Python by loading the target modules directly, because the repo venv Python was not usable from this shell.

- Neutral ramp:
  - `s_profile` monotonic: true.
  - `h_profile` monotonic: true.
  - `h_profile >= s_profile`: true.
  - low/mid-tone max gain EV at `scene_y <= 1.0`: `0.0`.
  - max adjacent gain EV jump: `0.1736`.
- User look scaling:
  - SDR equals user look: true.
  - HDR tracks scaled `h_profile`: true.
  - Actual HDR max: `1.1106`.
  - Rendition headroom: `1.4491`, higher than actual max because profile gain headroom is included.
- Hot pixel:
  - One `64x` sample among 1000 pixels with `headroom_percentile=99.0` did not dominate headroom.
  - Headroom and ordinary HDR max stayed at `1.2710`.
- Unsafe profile:
  - Explicit `polarity="decreasing", safe_for_profile_aware_hdr=False` was rejected.
- Modern recovery peak budget:
  - Budget scale: `0.9613`.
  - Target peak EV: `2.03`.
  - Final peak EV: `2.03`.
  - Baseline preserved: true.
- Current profile database:
  - Loaded profiles: `160`.
  - Safe profiles: `128`.
  - Unsafe profiles: `32`.
  - Safe profiles with actual monotonicity violations: `0`.
  - Maximum sampled SDR luminance: `0.8730`; no sampled profile is clipped near `1.0`.

## Findings

### Major: `HDRPhotoMapping.max_headroom` Is Ignored By `profile_aware`

- File/function: `src/spektrafilm/utils/hdr_photo.py`, `_prepare_profile_aware_renditions()`.
- Evidence: the profile-aware branch sets `safe_max_headroom = profile.defaults.safe_max_headroom` and uses that value for color recovery, clipping, and final headroom at lines 607-624. It never combines it with `mapping.max_headroom`.
- Experiment: with `mapping.max_headroom=2.0`, profile `safe_max_headroom=6.0`, and higher `profile_hdr_peak_ev`, the rendition returned `headroom=2.0999` and `hdr_max=2.0117`.
- Impact: callers cannot rely on `HDRPhotoMapping.max_headroom` as a hard export cap for profile-aware HDR, even though it is validated and honored by the generic path.
- Recommended fix: use `profile_headroom = min(float(mapping.max_headroom), float(profile.defaults.safe_max_headroom))` or an equivalently named effective cap, then use it for `_apply_hdr_color_recovery()`, clipping, and final headroom. Add a regression test where `mapping.max_headroom < profile.defaults.safe_max_headroom`.

### Major: Curve Safety Classification Allows Local Nonmonotonic Profiles

- File/function: `src/spektrafilm/utils/hdr_curve_profiles.py`, `_classify_polarity()` and `build_curve_profile_sample()`.
- Evidence: `_classify_polarity()` permits at least one increasing-curve violation, and `safe_for_profile_aware_hdr` does not inspect violation magnitude. Synthetic cases with one large local drop can report `polarity="increasing"` and `safe_for_profile_aware_hdr=True` if the coarse mid/high slopes remain positive.
- Impact: future generated profiles or dynamic profiles can pass safety while violating the core `s_profile` monotonic invariant. `h_profile` is later monotonic-enforced, but `hdr_gain = h_profile / s_profile` can still become unstable around the local drop.
- Current database impact: no current safe profile in `curve_profiles_v2.json` showed an actual monotonicity violation, so this is a forward-validation gap rather than evidence that the shipped DB is corrupt.
- Recommended fix: require zero negative `sdr_luminance_y` deltas beyond a small absolute/relative noise tolerance for `safe_for_profile_aware_hdr`, or perform explicit monotonic smoothing and record that smoothing in diagnostics. Add tests for a one-drop profile with positive summary slopes.

### Minor: The Name `profile_aware` Needs Documentation Guardrails

- File/function: docs/API semantics around `HDRPhotoMapping.hdr_mapping_mode` and profile database docs.
- Evidence: the v2 database README says profiles are sampled Spektrafilm film/paper tone curves; the implementation uses the SDR look plus scene sidecar to construct HDR recovery, not physical HDR paper output.
- Impact: users may read `profile_aware` as "the film/paper profile itself becomes HDR." The implementation is better understood as preserving print/profile SDR appearance while recovering scene-side highlight energy.
- Recommended fix: document this as "print/profile-aware HDR recovery." If a film-scan-only route is desired, keep it as a separate `film_scan_aware` mode with explicit route/profile provenance.

### Minor: Dynamic Profiles Need Provenance Boundaries

- File/function: `src/spektrafilm/utils/hdr_photo.py`, `_prepare_profile_aware_renditions()`.
- Evidence: when `profile_scene_y_samples` and `profile_look_y_samples` are both present, `build_dynamic_curve_profile()` replaces the static profile shape. There is no metadata proving whether those samples are a stable physical route or a temporary user-authored look.
- Impact: a caller could accidentally bake user look tweaks into a "profile" and then treat them as physical film/print behavior.
- Recommended fix: document the expected source of dynamic samples. If dynamic profile sampling remains public, include a route/provenance field and tests proving exposure/look edits are not silently treated as physical profile data unless explicitly requested.

### Non-Issue: `profile_hdr_min_gain=1.0` Is Coherent For Recovery-Only HDR

- File/function: `HDRPhotoMapping.profile_hdr_min_gain`, `build_profile_preserving_hdr_curve()`.
- Evidence: the strict and modern branches both enforce `h_profile >= s_profile * min_gain`.
- Impact: this cannot express an HDR rendition darker than the SDR profile, but that is consistent with the current recovery design.
- Recommendation: keep it for `profile_aware`; only relax it in a separately named compressive/creative mode.

### Non-Issue With Caveat: Headroom Can Exceed Absolute HDR Pixel Max

- File/function: `_prepare_profile_aware_renditions()`, `_content_headroom()`, gain-map metadata path.
- Evidence: user-look scaling produced actual HDR max `1.1106` and rendition headroom `1.4491` because the code takes `max(content_headroom, profile_gain_headroom)`.
- Interpretation: for gain-map style export, headroom as HDR/SDR gain capacity can legitimately exceed absolute HDR max. The caveat is that docs/tests must distinguish absolute display luminance headroom from gain-map ratio headroom.

### Non-Issue: Current Profile Database Does Not Appear Scanner-Clipped

- Evidence: database scan found max sampled SDR luminance `0.8730` and no sampled profile near `1.0`.
- Impact: the specific risk "profile samples already clipped to 1.0" is not present in the current database.
- Recommendation: keep a database validation test for max-channel/luminance clipping when regenerating profiles.

## Recommended Next Steps

- Fix `max_headroom` handling in `_prepare_profile_aware_renditions()` and add a regression test where mapping cap is lower than profile cap.
- Tighten profile safety classification so one large local drop cannot be marked safe.
- Add docs clarifying that current `profile_aware` is print/profile-aware HDR recovery from scene sidecar plus authored SDR look.
- Add database validation tests for monotonicity, clipping, route provenance, and safe/unsafe counts.
- Keep `film_scan_aware` separate. The current working tree now contains route/type-alias changes, tests referencing `film_scan_aware`, and `hdr_photo.py` acceptance for `generic`, `profile_aware`, and `film_scan_aware`; continue validating it as a separate route rather than folding it into print/profile-aware behavior.

## Confidence Loop

I do not have factual 100% confidence from full pytest because the repo venv/Homebrew Python is not currently usable in this shell. I increased confidence with direct source inspection, syntax compilation using bundled Python, targeted invariant experiments, database scans, and explicit environment classification.

Remaining uncertainty:

- Full `tests/test_hdr_photo.py` and `tests/test_hdr_curve_profiles.py` still need to be run in a healthy project Python environment.
- The HEIC/CoreImage encoder contract was reviewed by code path, not by a real HEIC export smoke in this run.
- The current worktree has newly integrated `film_scan` changes that should be validated separately before interpreting all HDR tests as clean signal.

Audit conclusion: the current default `profile_aware` design is acceptable as authored HDR recovery, with a required fix for mapping-level `max_headroom` and a required hardening pass for future profile safety validation.
