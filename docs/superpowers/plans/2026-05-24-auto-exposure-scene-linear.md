# Auto Exposure Scene-Linear Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve spektrafilm's automatic exposure system and make the default meter usable for scene-linear / ACES / HDR inputs.

**Architecture:** Keep auto exposure at the camera stage before RGB-to-film conversion, but move the metering logic into a robust utility contract. Add a `scene_linear` log-average meter that treats `0.184` as middle gray, handles values above `1.0` without clipping the input image, ignores invalid samples, clamps negative luminance to black for metering, and limits extreme EV output. Preserve the existing camera-style methods as explicit choices.

**Tech Stack:** Python 3.13, NumPy, colour-science, dataclasses/enums, pytest.

---

## Project Findings

- Runtime auto exposure currently lives in `src/spektrafilm/runtime/stages/filming.py` and calls `spektrafilm.utils.autoexposure.measure_autoexposure_ev()` on a resized preview before cropping/rescaling.
- The current autoexposure utility computes luminance through `colour.RGB_to_XYZ`, divides the selected statistic by `0.184`, then returns `-log2(exposure)`.
- Existing GUI/runtime state already exposes `auto_exposure` and `auto_exposure_method`; the enum currently lists `center_weighted`, `matrix`, `multi_zone`, `partial`, `highlight_weighted`, `median`, and `average`.
- ACES / scene-linear infrastructure already exists: `src/spektrafilm/color_management.py` treats `ACES2065-1` and `ACEScg` as linear, unclipped scene encodings, and the `aces_reference` workflow converts inputs to scene-linear `ACEScg`.
- Current failure evidence:
  - negative linear RGB can produce `nan` exposure compensation;
  - black inputs emit divide-by-zero warnings before falling back;
  - scene-linear HDR highlights can dominate mean-style meters, e.g. mostly middle gray with a bright specular strip currently reports about `-2.25 EV`; *(Note 2026-05-25: SDR contrast destruction during HDR scaling has been mitigated by the new Dual-Layer HDR Mapping and Diffuse Lift system, which helps retain perceptual midtones).*
  - unknown method names silently fall back to `0 EV`, hiding configuration errors.

## Design Decisions

- Add `scene_linear` as the default auto-exposure method in runtime params and GUI defaults.
- Implement `scene_linear` as a center-weighted log-average luminance meter:
  - convert input RGB to luminance in the declared input color space;
  - force ACES scene-linear spaces to skip CCTF decoding even if a caller passes a stale `True`;
  - ignore non-finite samples, clamp negative luminance to `0` for metering only;
  - use a Gaussian center weight like the existing center-weighted meter;
  - cap the log-average input at a high weighted percentile so speculars and lamps do not drag diffuse exposure down;
  - floor the log-average input from a low positive percentile so zeros do not create infinite EV;
  - return `0 EV` when there is no positive finite signal;
  - clamp output to a finite EV range to avoid pathological amplification.
- Keep old methods available and make them safer:
  - no `nan` or `inf` EV returns;
  - no silent unknown-method fallback;
  - small images must not break `matrix` cell splitting.
- Keep the pipeline shape unchanged: `FilmingStage.auto_exposure()` still scales the original image by `2 ** measured_ev`, then downstream exposure compensation continues in `expose()`.
- Document the difference between automatic exposure and physical diffuse-white calibration: this feature sets camera exposure for film simulation; it does not solve scene-energy calibration for HDR export.
- Preserve unrelated dirty worktree changes. Only touch files directly needed for this feature and tests/docs.

## Files

- Create: `tests/test_autoexposure.py`
  - Unit tests for scene-linear log-average behavior, ACES CCTF override, invalid-value handling, and unknown-method errors.
- Modify: `src/spektrafilm/utils/autoexposure.py`
  - Add robust luminance preparation, weighted percentile/log-average helpers, finite EV handling, and the `scene_linear` method.
- Modify: `src/spektrafilm/runtime/params_schema.py`
  - Change the runtime default auto-exposure method to `scene_linear`.
- Modify: `src/spektrafilm_gui/options.py`
  - Add `scene_linear` to `AutoExposureMethods`.
- Modify: `src/spektrafilm_gui/widget_specs.py`
  - Clarify the auto-exposure tooltip for the default scene-linear meter.
- Modify: `tests/test_photo_params.py`
  - Update default-param contract for the new default method.
- Modify: `tests/gui/test_params_mapper.py`
  - Update default GUI-state expectation for the new default method.
- Modify: `tests/test_pipeline_smoke.py`
  - Keep the integration smoke coverage aligned with the new default meter and add a scene-linear HDR smoke if unit tests do not cover enough.
- Modify: `README.md`
  - Briefly document the new default meter and its limits.

## Tasks

### Task 1: Failing Autoexposure Utility Tests

- [ ] Add `tests/test_autoexposure.py`.
- [ ] Test that uniform scene-linear `0.8` maps to `log2(0.184 / 0.8)` with `method="scene_linear"`.
- [ ] Test that mostly middle-gray scene-linear input with a bright specular region remains near `0 EV` under `method="scene_linear"`.
- [ ] Test that ACES scene-linear spaces ignore a stale `apply_cctf_decoding=True` flag.
- [ ] Test that negative, NaN, and Inf luminance contamination returns finite EV and does not propagate `nan`.
- [ ] Test that an unknown method raises `ValueError`.
- [ ] Run `.venv/bin/python -m pytest tests/test_autoexposure.py -q` and confirm the new tests fail for the current implementation.

### Task 2: Implement Robust Metering

- [ ] Rewrite `src/spektrafilm/utils/autoexposure.py` around small helpers:
  - `_effective_apply_cctf_decoding()`;
  - `_luminance_y()`;
  - `_meterable_luminance()`;
  - `_weighted_percentile()`;
  - `_center_weights()`;
  - `_scene_linear_log_average_luminance()`;
  - `_exposure_ev_from_luminance()`.
- [ ] Keep `measure_autoexposure_ev()` API compatible.
- [ ] Add `method="scene_linear"`.
- [ ] Raise `ValueError` for unsupported methods.
- [ ] Run `.venv/bin/python -m pytest tests/test_autoexposure.py -q` and confirm the tests pass.

### Task 3: Default And GUI Contract

- [ ] Change `CameraParams.auto_exposure_method` default to `"scene_linear"`.
- [ ] Add `scene_linear` to `AutoExposureMethods`.
- [ ] Update tooltip text to explain the default is a robust scene-linear/log-average meter.
- [ ] Update default-contract tests in `tests/test_photo_params.py` and `tests/gui/test_params_mapper.py`.
- [ ] Run `.venv/bin/python -m pytest tests/test_photo_params.py tests/gui/test_params_mapper.py -q`.

### Task 4: Runtime Smoke Coverage

- [ ] Add or adjust pipeline smoke coverage so auto exposure still normalizes bright inputs with the new default.
- [ ] Add scene-linear HDR smoke coverage if unit tests do not prove runtime behavior through `simulate()`.
- [ ] Run `.venv/bin/python -m pytest tests/test_pipeline_smoke.py -q`.

### Task 5: Documentation

- [ ] Update `README.md` near the exposure controls to describe `scene_linear` auto exposure.
- [ ] State that this is a metering/exposure feature, not physical diffuse-white calibration.

### Task 6: Verification And Self-Audit Loop

- [ ] Run targeted auto exposure, params, GUI mapper, pipeline, color-management, and raw-import tests.
- [ ] Run the full suite with `uv run --extra dev pytest -q` if the environment allows it.
- [ ] Run `.venv/bin/python -m compileall src tests` and `git diff --check`.
- [ ] Self-audit requirements:
  - plan document exists before implementation edits;
  - scene-linear auto exposure is available and default;
  - ACES linear spaces are not accidentally CCTF-decoded;
  - invalid samples cannot produce `nan` or `inf` EV;
  - old explicit methods still work;
  - GUI mapping and defaults stay consistent;
  - documentation explains scope and limitation;
  - unrelated dirty worktree changes are not reverted.
- [ ] If any item lacks evidence, add tests or code fixes and repeat verification.
