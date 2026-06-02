# Film Scan Aware HDR Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an independent `film_scan_aware` HDR mapping mode that builds HDR gain from the film exposure/development/scan route instead of the film-to-paper-to-scan route.

**Architecture:** Preserve `generic` and existing `profile_aware` behavior. Generalize HDR curve profiles so every profile records a route (`print_scan` or `film_scan`), add deterministic film-scan neutral-ramp sampling that forces `io.scan_film=True` and disables final scanner clipping for sampling, then reuse the existing profile-preserving HDR curve builder. GUI/export wiring only passes the new mode when explicitly selected; SDR preview and ordinary output paths remain unchanged.

**Tech Stack:** Python 3.13, NumPy, Spektrafilm runtime pipeline, pytest, OpenImageIO export helpers, Qt GUI state/mapper/controller plumbing.

---

## Audit Summary

Current `profile_aware`:

- `HDRPhotoMapping.hdr_mapping_mode` currently accepts `generic` and `profile_aware`.
- `profile_aware` requires a `scene_luminance` sidecar and resolves a `FilmPrintHDRCurveProfile` from either `mapping.curve_profile` or `(mapping.film, mapping.paper)`.
- `_prepare_profile_aware_renditions()` preserves the authored SDR look as `sdr_rgb = clip(look, 0, 1)`.
- The HDR target is built through `build_profile_preserving_hdr_curve()` unless `profile_curve_mode="legacy_graft"`, then applied as `hdr_gain = h_profile / s_profile` to the authored look.
- `profile_hdr_mode="modern_recovery_peak_budget"` already exists under the profile-preserving curve core and must be reused.

Current `scan_film`:

- `SimulationPipeline._pipeline()` switches on `params.io.scan_film`.
- `False` route: expose film, develop film, expose print, develop print, scan print.
- `True` route: expose film, develop film, scan film; print exposure, paper density curves, paper glare, enlarger filters, and print preflash do not run.
- `ScanningStage` already chooses film density/base/illuminant and disables print glare when `io.scan_film=True`.
- `ScanningStage._apply_cctf_encoding_and_clip()` honors `io.output_clip_min` and `io.output_clip_max`, so profile sampling can avoid final `[0, 1]` clipping by setting both to `False`.

Semantic split:

- `profile_aware` remains print-scan aware: film plus paper define the SDR profile source.
- `film_scan_aware` is film-scan aware: film route and scanner state define the SDR profile source; paper/enlarger/print adjustments must not enter the profile key or sampling route.
- `generic` remains sidecar/graft based and does not require a curve profile.

Expected adjustment response for `film_scan_aware`:

- Responds to film stock, camera exposure when explicitly represented in the profile-sampling params, film gamma, couplers, halation, and scanner white/black correction.
- Spatial and stochastic effects are disabled for the sampled curve but remain part of the already-authored image look.
- Scanner lens blur and unsharp mask are spatial effects; they can affect the authored look, but not the neutral one-dimensional curve profile.
- Does not respond to print paper, print exposure, enlarger filters, preflash, print diffusion, or print glare.

## Files

- Modify `src/spektrafilm/utils/hdr_curve_profiles.py`
  - Add `HDRCurveProfile` with `route`, `paper: str | None`, and backwards-compatible `FilmPrintHDRCurveProfile` alias.
  - Keep existing print-scan database loading compatible when route is missing.
  - Add `sample_runtime_film_scan_curve_profile()` and shared sampling parameter preparation.
  - Keep `sample_runtime_curve_profile()` as the print-scan sampler with unchanged defaults.
- Modify `src/spektrafilm/utils/hdr_photo.py`
  - Add `film_scan_aware` to accepted mapping modes and rendition metadata.
  - Resolve route-specific profiles and reuse `_prepare_profile_aware_renditions()` as a generic profile-route implementation.
  - Require `scene_luminance` for `film_scan_aware`.
- Modify `src/spektrafilm_gui/options.py`, `src/spektrafilm_gui/state.py`, `src/spektrafilm_gui/widget_specs.py`
  - Add an explicit HDR mapping mode selector with `generic`, `profile_aware`, and `film_scan_aware`.
- Modify `src/spektrafilm_gui/controller.py`
  - Include HEIC/HEIF in the save filter.
  - Pass `hdr_mapping_kwargs` based on GUI state.
  - For `film_scan_aware`, sample a dynamic film-scan curve profile from current runtime params and pass it as `curve_profile`.
- Modify tests:
  - `tests/test_hdr_curve_profiles.py`
  - `tests/test_hdr_photo.py`
  - `tests/test_image_io_color_metadata.py`
  - `tests/gui/test_controller_output.py`
- Add docs:
  - `docs/hdr-film-scan-aware.md`

## TDD Tasks

### Task 1: Route-Aware Curve Profiles

- [ ] Add tests that construct a `HDRCurveProfile(route="film_scan", paper=None)` and verify it is not keyed as `(film, paper)`.
- [ ] Add loader round-trip expectations that legacy database entries default to `route="print_scan"`.
- [ ] Implement `HDRCurveProfile` while preserving `FilmPrintHDRCurveProfile(...)` imports and construction.
- [ ] Run `tests/test_hdr_curve_profiles.py` and keep existing profile-aware tests green.

### Task 2: Film-Scan Profile Sampling

- [ ] Add a test that monkeypatches runtime sampling and proves `sample_runtime_film_scan_curve_profile()` sets `params.io.scan_film=True`, disables stochastic/spatial effects, disables auto exposure, disables CCTF, disables scanner output clipping, and returns `route="film_scan"` with `paper is None`.
- [ ] Add a test that print-scan sampling keeps `route="print_scan"` and paper identity.
- [ ] Implement the shared sampling prep and film-scan sampler.
- [ ] Run the new tests and a small real `kodak_portra_400` sampling smoke.

### Task 3: `film_scan_aware` HDR Renditions

- [ ] Add tests:
  - missing `scene_luminance` raises;
  - mode uses a `film_scan` profile and reports `mapping_mode_used="film_scan_aware"`;
  - SDR base preserves the supplied film-scan look;
  - HDR highlights gain headroom over SDR;
  - changing only paper on the mapping does not change the curve;
  - changing the film-scan profile changes the curve.
- [ ] Implement mode validation, route-specific profile resolution, and shared profile-route rendering.
- [ ] Keep existing `profile_aware` assertions unchanged.

### Task 4: Export And GUI Wiring

- [ ] Add an `HDRMappingModes` enum and `SimulationState.hdr_mapping_mode`.
- [ ] Add tests proving controller save passes:
  - no profile kwargs for `generic`;
  - `profile_aware` uses current film and paper;
  - `film_scan_aware` passes a dynamic `curve_profile` whose route is `film_scan`.
- [ ] Add a save filter that includes HEIC/HEIF.
- [ ] Ensure `save_image_oiio()` accepts `film_scan_aware` through existing `HDRPhotoMapping(**hdr_mapping_kwargs)`.

### Task 5: Documentation And Verification

- [ ] Write `docs/hdr-film-scan-aware.md` explaining the three modes, physical semantics, limitations, and adjustment response matrix.
- [ ] Run targeted tests:
  - `.venv/bin/python -m pytest tests/test_hdr_curve_profiles.py tests/test_hdr_photo.py tests/test_image_io_color_metadata.py -q`
  - `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/gui/test_controller_output.py -q`
- [ ] Run broader verification if targeted tests pass:
  - `.venv/bin/python -m pytest --ignore=tests/gui -q`
  - `.venv/bin/python -m compileall -q src tests tools`
  - `git diff --check`
- [ ] Final self-review:
  - confirm default SDR and `profile_aware` routes are unchanged;
  - confirm film-scan sampler cannot enter printing stage;
  - confirm profile sampling is not capped by scanner `[0,1]` clipping;
  - confirm paper/enlarger fields are not used in the `film_scan` key;
  - confirm docs match code and tests.

## Risks

- Existing worktree is dirty and shared. Mitigation: only edit the files listed above and inspect every target before patching.
- Dynamic film-scan sampling during GUI save is more expensive than static database lookup. Mitigation: sampling uses a small neutral ramp, disabled LUTs/spatial/stochastic effects, and only runs for explicit `film_scan_aware` export.
- `film_scan_aware` can only preserve a true film-scan SDR base if the authored output layer is itself a film scan. Mitigation: docs state this clearly; the core API preserves the supplied look, and GUI users should run `scan_film` before exporting in this mode.
