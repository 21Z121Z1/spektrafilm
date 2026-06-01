# Profile-Aware HDR Audit Plan

**Goal:** Determine whether the current profile-aware HDR curve path is mathematically correct, physically/semantically coherent, and sufficiently covered by tests, without changing existing behavior unless a concrete bug is proven.

**Scope:** Read-only audit of the `profile_aware` / `profile_preserving` / `modern_recovery_peak_budget` implementation on the local `develop` worktree tracking `origin/develop`.

**Constraint:** Do not modify production behavior during the audit. Any possible fix must first be justified in the audit report with file, function, impact, and regression evidence.

---

## Core Files

- `src/spektrafilm/utils/hdr_photo.py`
  - `HDRPhotoMapping`
  - `prepare_hdr_photo_renditions()`
  - `_prepare_profile_aware_renditions()`
  - `_content_headroom()`
  - `_apply_hdr_highlight_color()`
  - `_apply_path_to_white()`
  - `_gamut_compress_luma_preserving()`
  - `gamut_map_oklch()`
- `src/spektrafilm/utils/hdr_curve_profiles.py`
  - `FilmPrintHDRCurveProfile`
  - `build_profile_preserving_hdr_curve()`
  - `profile_relative_hdr_gain_ev()`
  - `profile_modern_recovery_budgeted_gain_ev()`
  - `budget_recovery_gain_ev()`
  - `sample_runtime_curve_profile()`
- `src/spektrafilm/data/hdr_curve_profiles/curve_profiles_v2.json`
- `src/spektrafilm/data/hdr_curve_profiles/samples/*.json`
- `src/spektrafilm/data/hdr_curve_profiles/README.md`
- `tests/test_hdr_photo.py`
- `tests/test_hdr_curve_profiles.py`
- `tools/validate_profile_aware_hdr_raw_samples.py`
- Relevant docs:
  - `docs/superpowers/plans/2026-05-25-profile-aware-hdr-photo-export.md`
  - `docs/dev/modern_recovery_peak_budget_plan.md`
  - `docs/hdr_profile_aware_raw_validation.md`
  - `docs/hdr_profile_aware_raw_validation.json`

## Math Invariants To Verify

- `scene_luminance` is required for `hdr_mapping_mode="profile_aware"` and is normalized exactly once to `diffuse_white`.
- `s_profile` is finite, nonnegative, and monotonic for valid increasing profiles.
- `h_profile` is finite, nonnegative, and monotonic after enforcement.
- In strict-preserving mode, `h_profile >= s_profile * profile_hdr_min_gain` within floating tolerance.
- `hdr_gain = h_profile / s_profile` is finite and smooth except where guarded by epsilon near black.
- Low and mid tones stay close to unity gain when the profile shoulder has not compressed scene EV.
- `modern_recovery_peak_budget` uses `scene_ev - profile_ev` as compressed EV, scales only recovery gain, and does not change the strict/profile baseline except through explicit constraints.
- Peak budget and hard cap limit final profile-relative EV without introducing local nonmonotonic artifacts.
- `headroom` metadata is derived from actual HDR content/profile gain and is not copied directly from `profile_hdr_target_peak_ev`.
- Clipping to `safe_max_headroom` / `max_headroom` does not silently invalidate the intended profile target for ordinary samples.
- Unsafe decreasing or nonmonotonic profiles are rejected rather than silently producing plausible-looking HDR output.

## Physical And Imaging Semantics To Verify

- The sampled curve represents film plus print/paper SDR output behavior, not direct HDR film physics.
- `profile_aware` is best described as preserving the SDR print/profile look while using scene sidecar energy for authored HDR highlight recovery.
- Paper/print shoulder and display headroom are not treated as the same physical quantity.
- SDR base output preserves the user's current look exactly, while HDR target is an alternate rendition built from the sidecar and profile curve.
- Dynamic runtime curve sampling does not incorrectly treat temporary user look edits as a stable physical film/print profile.
- Naming such as `paper_rolloff_*`, `profile_aware`, and `film_scan_aware` implications are checked for semantic drift.

## Code Path Questions

- `HDRPhotoMapping`
  - Validate all profile-aware parameters for finite ranges, enum values, and mode compatibility.
  - Check interactions among `profile_hdr_peak_ev`, `profile_hdr_target_peak_ev`, `profile_hdr_recovery_ratio`, `profile_hdr_min_gain`, `profile_hdr_max_chroma_gain`, path-to-white parameters, `headroom_percentile`, and `max_headroom`.
- `_prepare_profile_aware_renditions()`
  - Confirm `scene_luminance` is mandatory.
  - Confirm `s_profile`, `h_profile`, and `hdr_gain` are aligned on the same scene coordinate.
  - Confirm `hdr_rgb = look * hdr_gain` preserves SDR look and intended luminance before optional color recovery.
  - Confirm content headroom and profile gain headroom cannot incorrectly inflate or shrink payload metadata.
  - Check whether safe profile headroom can conflict with mapping-level `max_headroom`.
- `build_profile_preserving_hdr_curve()`
  - Confirm mode dispatch, unknown mode rejection, min-gain semantics, monotonic enforcement, soft clipping, and `visual_peak = look_white * 2**peak_ev`.
- `modern_recovery_peak_budget`
  - Confirm raw recovery gain, budget scaling, hard cap, percentile normalization, diagnostics, and monotonic behavior after constraints.
- Color recovery and gamut handling
  - Compare `off`, `source_chroma`, and `bounded_look_chroma`.
  - Check divergence fallback between `scene_rgb` and `scene_luminance`.
  - Verify chroma gain limit, path-to-white, and gamut compression order.
  - Verify luma-preserving compression keeps target luminance when possible and fails boundedly when target luma exceeds headroom.

## Test Commands

Run these focused commands first:

```bash
uv run --extra dev pytest tests/test_hdr_photo.py -q
uv run --extra dev pytest tests/test_hdr_curve_profiles.py -q
```

If the environment lacks dependencies or a test file is missing, classify the result as environment/test-coverage/implementation separately.

## Minimal Experiments

Create only temporary, non-production validation scripts or inline Python snippets unless the report proves that a permanent regression test is required.

- Neutral ramp
  - Check `s_profile` monotonic.
  - Check `h_profile` monotonic.
  - Check `h_profile >= s_profile`.
  - Check low/mid-tone gain near 1.
  - Check highlight gain smoothness and max gain EV jump.
- User look scaling
  - Check SDR base equals input look.
  - Check HDR target tracks user look proportionally.
  - Check profile gain is independent of user exposure scale when scene sidecar is unchanged.
- Hot pixel
  - Check one extreme sample does not dominate percentile headroom.
  - Check payload clipping does not destroy ordinary samples.
- Unsafe profile
  - Check decreasing/nonmonotonic profile is rejected.
- Modern recovery peak budget
  - Check profile baseline is not budget-scaled.
  - Check raw recovery gain is budget-scaled.
  - Check final peak respects target and hard cap.
  - Check final profile remains monotonic or produces an explicit explanation.

## Known Risk List

- Sampled profile may already be scanner/output clipped at 1.0, losing highlight shape before HDR recovery.
- `profile_hdr_min_gain=1.0` may prevent legal compressive HDR targets.
- Profile defaults `safe_max_headroom` may conflict with `HDRPhotoMapping.max_headroom`.
- `headroom = max(content_headroom, profile_gain_headroom)` may overstate metadata if actual HDR RGB is lower after color/gamut constraints.
- `source_chroma` can amplify extreme scene RGB chroma.
- Path-to-white can reduce saturated highlights and possibly disturb luminance.
- Luma-preserving gamut compression may be ill-defined when requested luma exceeds `max_headroom`.
- Dynamic curve profiles may conflate authored look tweaks with physical profile shape.
- Diffuse-white normalization may be duplicated if callers pass pre-normalized scene luminance.
- Legacy paper-rolloff naming may still leak into profile-aware semantics.
- Tests may cover synthetic profiles more thoroughly than real profile database entries.

## Acceptance Criteria

- The audit report exists at `docs/profile-aware-hdr-audit-report.md`.
- The report includes executive summary, evidence, findings, recommended next steps, and a confidence loop.
- Every finding is classified as Critical, Major, Minor, or Non-issue and names file/function/impact/recommendation.
- Focused tests are run or a concrete reason is recorded for not running them.
- Minimal experiments cover the invariants above or explicitly document why an experiment could not be run.
- The final conclusion separates implementation bugs, naming/semantic ambiguity, test gaps, and environment limitations.
- Existing production behavior remains unchanged unless a proven blocker is separately fixed with tests.
