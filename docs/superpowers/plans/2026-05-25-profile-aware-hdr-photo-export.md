# Profile-Aware HDR Photo Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement profile-aware paired SDR/HDR tone-curve mapping for Spektrafilm HDR photo export while proving existing SDR rendering and non-HDR save paths remain unchanged.

**Architecture:** Keep the existing runtime SDR film/print/scan path as the source of `look_rgb`. Add HDR-only export-time helpers that use per-pixel `scene_luminance` plus a machine-readable film/paper curve profile to build authored SDR and HDR renditions. Preserve scene-linear archive EXR; add a separate explicit HDR rendition EXR route.

**Tech Stack:** Python 3.13, NumPy, colour-science, pytest, OpenImageIO, Swift/CoreImage encoder for HEIC gain-map delivery.

---

## Baseline Evidence

- Requested slice 1: `uv run --extra dev pytest -q tests/test_hdr_photo.py tests/test_image_io_color_metadata.py tests/gui/test_controller_output.py` -> `74 passed`.
- Requested slice 2: `uv run --extra dev pytest -q tests/test_raw_file_processor.py tests/test_runtime_api.py tests/gui/test_controller_runtime_module.py tests/gui/test_controller_flow.py` -> `71 passed`.
- Existing SDR/golden slice: `uv run --extra dev pytest -q tests/test_regression_baselines.py tests/test_pipeline_smoke.py` -> `13 passed`.
- Checkout is dirty before this task. Existing modified/untracked HDR work must be preserved, not reverted.

## Implementation Tasks

### Task 1: Lock SDR And Non-HDR Boundaries

- [ ] Add tests proving `Simulator.process()` and `simulate()` outputs match existing regression baselines.
- [ ] Add tests proving generic PNG/TIFF/JPEG/EXR save paths do not instantiate or call profile-aware HDR mapping.
- [ ] Add tests proving runtime `look_rgb` is identical with profile-aware code present until explicit HDR export/rendition is requested.
- [ ] Add tests proving HEIC SDR base is the authored SDR fallback and not a modified runtime preview/output path.

### Task 2: Curve-Profile V2 Data And Loader

- [ ] Add `src/spektrafilm/utils/hdr_curve_profiles.py` with cached dataclasses and safe missing/invalid JSON behavior.
- [ ] Add profile analysis/export helpers that sample actual deterministic runtime profile behavior on neutral ramps.
- [ ] Write compact `data/hdr_curve_profiles/curve_profiles_v2.json`, per-profile samples, and `data/hdr_curve_profiles/README.md`.
- [ ] Add tests for schema, finite floats, exact scene_y=1.0 anchor, increasing/decreasing polarity, unsafe fallback, and loader behavior.

### Task 3: Paired SDR/HDR Curve Mapping

- [ ] Extend `HDRPhotoMapping` with explicit `hdr_mapping_mode`, film/paper identifiers, and optional overrides without deleting existing advanced parameters.
- [ ] Add a full-domain paired curve builder: `S_profile(scene_y)`, `H_profile(scene_y)`, smooth gain/log-gain, monotonic safe-profile behavior.
- [ ] Use `scene_luminance` as the HDR coordinate and `look_rgb` as film color/texture; do not infer physical headroom from `look_rgb` alone.
- [ ] Add diagnostics for missing sidecar, missing profile, unsafe polarity, and bad fit quality.

### Task 4: HEIC And EXR Routing

- [ ] Keep HEIC encoder payload contract as authored SDR float payload plus authored HDR float payload.
- [ ] Wire film/paper identifiers and scene-luminance sidecar from controller output metadata into HDR photo export.
- [ ] Add explicit EXR mode: `scene_linear_archive` writes existing output float data; `hdr_rendition` writes authored HDR rendition.
- [ ] Preserve `whiteLuminance=203` for scene-linear EXR metadata where applicable.

### Task 5: Real ProRAW Validation

- [ ] Add `tools/validate_profile_aware_hdr_raw_samples.py`.
- [ ] Inspect `/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片/RAW_DNG_JPEG_批量导出`, select up to four representative DNG samples, and record why.
- [ ] Validate RAW diagnostics, sidecar alignment, SDR preservation, profile-aware HDR boundedness, fallback cases, and binned tone-curve conformance.
- [ ] Write `docs/hdr_profile_aware_raw_validation.md` with selected samples, metrics, limitations, and actual command used.

### Task 6: Final Verification

- [ ] Run targeted curve/profile/HDR/controller tests.
- [ ] Run requested baseline slices again.
- [ ] Run `uv run python -m compileall -q src/spektrafilm src/spektrafilm_gui tests`.
- [ ] Run `git diff --check`.
- [ ] Separate baseline/pre-existing issues from any task regressions in final report.
