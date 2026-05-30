# Modern Recovery Peak Budget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add and validate a profile-preserving HDR mode named `modern_recovery_peak_budget` that recovers shoulder-compressed highlight EV while enforcing a fixed profile-relative EV peak budget without changing existing SDR rendering behavior.

**Architecture:** Keep SDR and legacy profile curve semantics unchanged. The modern mode lives behind `HDRPhotoMapping.profile_hdr_mode` and is only consumed by the profile-preserving curve path; `profile_curve_mode="legacy_graft"` ignores it. Gain-map/headroom metadata remains content-derived through `_content_headroom()` rather than written from the target EV budget.

**Tech Stack:** Python 3.13, NumPy, dataclasses, existing Spektrafilm HDR photo utilities, PySide GUI state/widget plumbing, `uv run --extra dev pytest`.

---

## Current Code Paths Found

- `src/spektrafilm/utils/hdr_curve_profiles.py`
  - `ProfilePreservingHDRCurveResult` is the strict-preserving diagnostics return type.
  - `ProfileHDRCurveResult`, `budget_recovery_gain_ev()`, and `profile_modern_recovery_budgeted_gain_ev()` already exist, but need completion against the requested API and diagnostics.
  - `build_profile_preserving_hdr_curve()` already branches on `mapping.profile_hdr_mode`; strict-preserving remains the default branch and returns `ProfilePreservingHDRCurveResult` when diagnostics are requested.
  - The modern branch computes `h = s_profile * 2**gain_ev` and returns `ProfileHDRCurveResult`, but the budget helper does not yet support `active_mask`, does not report all requested budget metadata, and hard-cap behavior currently changes the "scale gain only" invariant for the direct helper test.
- `src/spektrafilm/utils/hdr_photo.py`
  - `HDRPhotoMapping` already has `profile_hdr_mode`, `profile_hdr_target_peak_ev`, `profile_hdr_normalize_percentile`, `profile_hdr_budget_hard_cap`, `profile_hdr_recovery_ratio`, `profile_hdr_recovery_knee_ev`, and `profile_hdr_recovery_full_ev`.
  - Validation covers mode, target peak, and recovery ratio, but still needs percentile, hard-cap boolean compatibility, and ordered recovery knee/full validation.
  - `_prepare_profile_aware_renditions()` already accepts either diagnostics type through shared fields `s_profile`, `h_profile`, and `look_white`.
  - `build_hdr_debug_sidecar()` already detects `ProfileHDRCurveResult` and includes modern diagnostics, but should be checked against the requested names and stats.
  - `_content_headroom()` is still the content-derived headroom path used by HEIC payload export; the target EV budget must not be copied into GainMapMax/headroom.
- GUI files
  - `src/spektrafilm_gui/state.py` already includes `profile_hdr_mode`, `profile_hdr_target_peak_ev`, and `profile_hdr_recovery_ratio` on `HdrExportState` and default construction.
  - `src/spektrafilm_gui/options.py` already has `ProfileHDRModes`.
  - `src/spektrafilm_gui/widget_specs.py` already registers `profile_hdr_mode` and widget specs for target EV and recovery ratio.
  - `src/spektrafilm_gui/widget_sections.py` enables/disables the new controls in `HdrExportSection._sync_mode()`, but does not hide/show rows.
  - `src/spektrafilm_gui/controller.py` already passes the three GUI-exposed modern fields into `hdr_mapping_kwargs`.
- Tests
  - Initial command: `uv run --extra dev pytest tests/test_hdr_curve_profiles.py tests/test_hdr_photo.py -v`.
  - Baseline before edits: 64 passed, 9 failed.
  - Modern-relevant failures: `test_budget_scales_gain_not_profile_ev`, `test_modern_recovery_uses_compressed_ev`, and `test_gain_map_max_matches_actual_h_over_s`.
  - Existing baseline/stale-test failures also appeared in generic SDR-base tests and unsafe-profile fallback expectations. These must not be fixed by changing SDR behavior unless that behavior is already intended by current code.

## Exact Files To Change

- Modify `src/spektrafilm/utils/hdr_curve_profiles.py`
  - Complete `budget_recovery_gain_ev()` with `active_mask`, requested diagnostics keys, finite/percentile guards, baseline-preserving effective target logic, and budget scaling that only multiplies `raw_gain_ev`.
  - Ensure modern diagnostics include `raw_h_ev` and `final_h_ev` at the helper level and in `ProfileHDRCurveResult`.
  - Defensively reject unknown `profile_hdr_mode`.
  - Preserve the strict-preserving branch and defaults.
- Modify `src/spektrafilm/utils/hdr_photo.py`
  - Complete `HDRPhotoMapping` validation for modern fields.
  - Keep `_prepare_profile_aware_renditions()` on shared result fields.
  - Keep HEIC headroom based on `_content_headroom(hdr_rgb, percentile=...)`.
  - Add any minimal compatibility needed for the prewritten GainMapMax test only if it does not alter existing behavior.
- Modify GUI files only if inspection or tests show gaps:
  - `src/spektrafilm_gui/state.py`
  - `src/spektrafilm_gui/options.py`
  - `src/spektrafilm_gui/widget_specs.py`
  - `src/spektrafilm_gui/widget_sections.py`
  - `src/spektrafilm_gui/controller.py`
- Modify `tests/test_hdr_curve_profiles.py` and `tests/test_hdr_photo.py` only to repair malformed/stale tests that contradict current public APIs or the hard SDR-preservation constraint.

## Expected Return Types And Diagnostics

- Strict preserving:
  - `build_profile_preserving_hdr_curve(..., return_diagnostics=False)` returns `np.ndarray`.
  - `build_profile_preserving_hdr_curve(..., return_diagnostics=True)` returns `ProfilePreservingHDRCurveResult`.
  - Fields stay unchanged: `s_profile`, `h_profile`, `gain_ev`, `slope`, `diffuse_white`, `look_white`, `visual_peak`.
- Modern recovery:
  - `profile_modern_recovery_budgeted_gain_ev(..., return_diagnostics=False)` returns `np.ndarray`.
  - `profile_modern_recovery_budgeted_gain_ev(..., return_diagnostics=True)` returns a dict containing `gain_ev`, `raw_gain_ev`, `slope`, `scene_ev`, `profile_ev`, `raw_h_ev`, `final_h_ev`, `compressed_ev`, `target_peak_ev`, `effective_target_peak_ev`, `raw_peak_ev_before_budget`, `actual_peak_ev_after_budget`, `budget_scale`, `budget_was_applied`, `normalize_percentile`, and `hard_cap`.
  - `build_profile_preserving_hdr_curve(..., modern mode, return_diagnostics=True)` returns `ProfileHDRCurveResult`.

## Implementation Tasks

- [x] Inspect the named files and tests.
- [x] Run the focused tests before production edits and record the baseline failures.
- [x] Write this plan document before code edits.
- [x] Patch `budget_recovery_gain_ev()` so the direct helper tests pass and requested diagnostics are present.
- [x] Patch `profile_modern_recovery_budgeted_gain_ev()` diagnostics and shape handling.
- [x] Patch `build_profile_preserving_hdr_curve()` for unknown mode validation and correct modern final diagnostics after monotonic/min-gain constraints.
- [x] Patch `HDRPhotoMapping` validation for the remaining modern fields.
- [x] Repair or adapt malformed prewritten tests only where they call nonexistent APIs or assert stale SDR behavior.
- [x] Run targeted HDR tests and any relevant GUI tests.
- [x] Run `git diff --check`.
- [x] Manually inspect the final diff for SDR behavior changes, headroom misuse, GUI state propagation, validation gaps, and unrelated files.
- [x] Update this document with completed changes, validation results, and limitations.

## Risks And Mitigations

- Risk: accidentally changing authored SDR behavior to satisfy stale SDR tests.
  - Mitigation: do not alter `preserve_sdr_base=True` behavior or generic SDR output code unless the current code and hard constraints both require it; prefer test repair for stale assertions.
- Risk: treating `profile_hdr_target_peak_ev` as HEIC GainMapMax/headroom.
  - Mitigation: leave `HDRPhotoRenditions.headroom` derived from actual `hdr_rgb` content through `_content_headroom()`.
- Risk: modern budget clamps the profile baseline instead of only scaling recovery gain.
  - Mitigation: compute `effective_target_peak_ev = max(target_peak_ev, percentile(p_ev))`, binary-search only the raw gain scale, and clamp only gain with lower bound zero.
- Risk: strict-preserving regression.
  - Mitigation: keep its code path and result dataclass unchanged, then run existing strict profile-preserving tests.

## Validation Commands

- `uv run --extra dev pytest tests/test_hdr_curve_profiles.py tests/test_hdr_photo.py -v`
- `uv run --extra dev pytest tests/gui -q` if GUI test dependencies are available and the controller/widget changes are touched.
- `git diff --check`

## Completed Changes

- `budget_recovery_gain_ev()` now:
  - accepts `active_mask`;
  - validates target EV and percentile;
  - measures budget percentiles with a conservative higher-percentile method;
  - raises the effective target only to the measured profile baseline peak;
  - binary-searches a scale that multiplies only `raw_gain_ev`;
  - reports `target_peak_ev`, `effective_target_peak_ev`, `normalize_percentile`, `hard_cap`, `active_sample_count`, `raw_h_ev`, and `final_h_ev`.
- `profile_modern_recovery_budgeted_gain_ev()` now forwards the budget using the keyword-only target and exposes `raw_h_ev` / `final_h_ev` diagnostics.
- `build_profile_preserving_hdr_curve()` now rejects unknown `profile_hdr_mode` values defensively and returns modern diagnostics using the budget helper's raw-H EV diagnostics.
- `HDRPhotoMapping` now validates modern percentile, hard-cap boolean compatibility, non-negative recovery ratio, and ordered recovery knee/full EV values.
- Profile-aware HEIC headroom now includes the real content-derived profile gain headroom from `h_profile / s_profile`, rather than using `profile_hdr_target_peak_ev` as metadata.
- `HdrExportSection._sync_mode()` now disables and hides the modern profile controls when HDR mapping is not `profile_aware`.
- Tests were adjusted only where the prewritten assertions were stale or malformed:
  - default SDR-base tests now assert authored SDR preservation;
  - tone-map-specific tests opt into `preserve_sdr_base=False`;
  - the modern recovery profile fixture uses matching sample lengths;
  - the GainMapMax test uses the current `HDRPhotoMapping` / `prepare_hdr_photo_renditions()` API.

## Validation Results

- Initial red run before edits:
  - `uv run --extra dev pytest tests/test_hdr_curve_profiles.py tests/test_hdr_photo.py -v`
  - Result: 64 passed, 9 failed.
- Focused HDR validation after implementation:
  - `.venv/bin/pytest tests/test_hdr_curve_profiles.py tests/test_hdr_photo.py -v`
  - Result: 73 passed in 0.60s.
- Lightweight GUI widget validation:
  - `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/gui/test_widgets.py -q`
  - Result: 12 passed in 2.41s.
- Scoped syntax validation:
  - `.venv/bin/python -m py_compile src/spektrafilm/utils/hdr_curve_profiles.py src/spektrafilm/utils/hdr_photo.py src/spektrafilm_gui/widget_sections.py tests/test_hdr_curve_profiles.py tests/test_hdr_photo.py`
  - Result: passed.
- Broader GUI/controller validation:
  - `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/gui/test_controller_output.py::test_save_output_layer_heic_passes_profile_aware_film_paper -vv`
  - Result: Python process aborted inside PySide/Qt while running `GuiController.save_output_layer()`.
- Final collection after `uv` rebuild/sync:
  - `.venv/bin/pytest tests/test_hdr_curve_profiles.py tests/test_hdr_photo.py -v`
  - Result: blocked during `tests/conftest.py` import by unrelated unresolved merge markers in `src/spektrafilm/color_management.py`.
- `git diff --check`:
  - Result: failed on unrelated unresolved merge markers across existing files including `README.md`, `src/spektrafilm/color_management.py`, runtime/GUI merge-conflict files, and color-management tests. The scoped HDR files checked with `rg` did not contain conflict markers.

## Known Limitations And Current Blockers

- The worktree currently contains unresolved merge-conflict markers in unrelated files. They block normal pytest collection and `git diff --check`, but were not resolved here to keep this feature scoped.
- `uv run` rebuilt/synced the local environment during validation and appeared to refresh parts of the working tree; after that, direct `.venv/bin/pytest` became the safer verification path.
- `src/spektrafilm_gui/controller.py` and `src/spektrafilm_gui/state.py` currently have unresolved conflict markers outside the narrow modern HDR lines. The required modern HDR fields/kwargs are present, but the files cannot be treated as fully validated until those broader conflicts are resolved.
