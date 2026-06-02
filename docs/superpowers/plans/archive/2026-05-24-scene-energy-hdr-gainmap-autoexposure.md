# Scene-Energy HDR Gain-Map Auto-Exposure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a scene-energy sidecar to simulation output and use it for natural HEIC/HEIF HDR gain-map export linked to the same auto-exposure path as the film simulation.

**Architecture:** Keep the simulated film/print/scan output as the authored look. During runtime preprocessing, derive a post-auto-exposure scene-linear luminance sidecar from the exact image entering the simulation, estimate diffuse white/headroom from that signal, and store it on the output layer. During HDR photo export, build the SDR base from the film look and build the HDR rendition using a Dual-Layer Mapping approach (Diffuse Lift + Specular Rolloff): first lifting the paper-limited diffuse white to a true HDR diffuse white anchor, and then smoothly grafting specular scene luminance onto that lifted base, bounded by the existing headroom policy.

**Tech Stack:** Python 3.13, NumPy, colour-science, PySide/Qt GUI, CoreImage Swift HEIF encoder, pytest.

---

## Evidence And Decisions

*(Update 2026-05-25: Dual-Layer Mapping is now successfully implemented in `_graft_scene_luminance`. The Swift encoder now outputs color gain maps (`hdrGainMapAsRGB=true`) using separated unlifted SDR and lifted HDR renditions. A new "HDR Export Settings" GUI panel controls these capabilities.)*

- Existing focused tests for RAW diagnostics, HDR photo payload splitting, EXR reference white, and controller save routing passed: `22 passed in 0.52s`.
- The Swift encoder compiles far enough to emit the new two-payload usage string when run as `xcrun swift src/spektrafilm/data/macos/hdr_heif_encoder.swift`.
- A local DNG smoke produced finite diagnostics for `/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片/IDG_20260411_152822_608.DNG`, including `diffuse_white_estimate=0.9733272194862366`, `headroom_estimate=1.0274037137560403`, and finite raw sensor statistics.
- OpenEXR scene-linear convention supports values above `1.0` and uses approximately `0.18` for a correctly exposed 18% gray card; `1.0` is not a clamp limit.
- ITU-R BT.2408 HDR practice supports treating diffuse/reference white around `203 cd/m2` while preserving brighter headroom for highlights.
- Adobe/Android/Apple gain-map workflows all depend on separate SDR and HDR renditions, not a clipped HDR image used as the SDR base.
- Photographic paper curves have toe, straight-line, shoulder, and Dmax behavior, so a paper-limited print look should not be treated as recovered scene energy.

## Task 1: Runtime Scene-Energy Metadata Tests

**Files:**
- Modify: `tests/test_runtime_api.py`
- Modify: `tests/gui/test_controller_runtime_module.py`

- [ ] Add tests proving `Simulator.process()` remains a NumPy-array API while `Simulator.process_with_metadata()` returns the same rendered output plus scene-energy metadata.
- [ ] Add a focused pipeline test that auto exposure changes the sidecar luminance in the same direction as the image entering the film simulation.
- [ ] Add a controller-runtime test proving `SimulationResult` carries optional HDR scene-energy metadata.
- [ ] Run the new tests and verify they fail because the metadata API does not exist yet.

## Task 2: Runtime Scene-Energy Implementation

**Files:**
- Modify: `src/spektrafilm/runtime/pipeline.py`
- Modify: `src/spektrafilm/runtime/process.py`
- Modify: `src/spektrafilm/runtime/api.py`
- Modify: `src/spektrafilm_gui/controller_runtime.py`

- [ ] Add `HDRSceneEnergyMetadata` with `scene_luminance`, `diffuse_white_estimate`, `headroom_estimate`, `auto_exposure_ev`, `method`, and `confidence`.
- [ ] Refactor preprocessing so the runtime measures auto exposure once, applies it to the input, crops/resizes the result, and computes scene-energy metadata from that exact post-auto-exposure image.
- [ ] Preserve `process()` as the legacy array-returning API and add `process_with_metadata()` to return the rendered image plus metadata.
- [ ] Extend `SimulationResult` so GUI workers can carry the optional metadata without changing preview image behavior.

## Task 3: GUI Propagation And Save Routing Tests

**Files:**
- Modify: `tests/gui/test_controller_output.py`

- [ ] Add a test that `_on_simulation_finished()` stores scene luminance and diagnostics on the output layer metadata.
- [ ] Add a test that HEIC/HEIF save passes stored scene luminance into `save_image_oiio()`.
- [ ] Add a fallback test that old output layers without scene luminance still use existing HEIC behavior.
- [ ] Run the new tests and verify they fail before implementation.

## Task 4: GUI Propagation Implementation

**Files:**
- Modify: `src/spektrafilm_gui/controller.py`
- Modify: `src/spektrafilm_gui/controller_layers.py`

- [ ] Add output metadata keys for `HDR_SCENE_LUMINANCE_KEY` and `HDR_SCENE_ENERGY_METADATA_KEY`.
- [ ] Let output-layer metadata store optional scene-energy fields alongside existing float output/color encoding metadata.
- [ ] Pass stored scene luminance to `save_image_oiio()` only for HEIC/HEIF HDR photo saves.

## Task 5: HDR Photo Luminance Graft Tests

**Files:**
- Modify: `tests/test_hdr_photo.py`
- Modify: `tests/test_image_io_color_metadata.py`

- [ ] Add a test where paper-limited `look_rgb <= 1.0` plus `scene_luminance > 1.0` exports a valid HDR rendition instead of failing as SDR-only.
- [ ] Add a test proving the scene-luminance graft is bounded by `max_headroom` and robust against one hot pixel.
- [ ] Add an IO dispatch test proving HEIC scene luminance reaches `save_hdr_photo_heic()`.
- [ ] Run the new tests and verify they fail before implementation.

## Task 6: HDR Photo Luminance Graft Implementation

**Files:**
- Modify: `src/spektrafilm/utils/hdr_photo.py`
- Modify: `src/spektrafilm/utils/io.py`

- [ ] Extend `save_hdr_photo_heic()` and `save_image_oiio()` with optional `scene_luminance`.
- [ ] Add `prepare_hdr_photo_renditions(..., scene_luminance=...)`.
- [ ] Estimate dynamic look white using `scene_y ≈ 1.0` samples, falling back to profile defaults to prevent boosting low-key images.
- [x] Implement Dual-Layer Mapping: 
  1. **Diffuse Lift Layer:** Uncompress midtones and diffuse white from the paper-limited look up to `hdr_diffuse_white_target`. (Implemented in `_graft_scene_luminance` with explicit GUI controls)
  2. **Specular Rolloff Layer:** Extract extended high-light energy via a logistic/filmic curve and apply it as a specular delta extending above the diffuse baseline.
- [ ] Keep the SDR base from hue-preserving tone mapping of the final HDR rendition and keep the existing fallback path when no sidecar exists.

## Task 7: Documentation And Verification

**Files:**
- Modify: `README.md`

- [ ] Document scene-referred sidecar versus paper/print look, 203-nit diffuse/reference white, auto-estimate limits, and gain-map SDR/HDR rendition separation.
- [ ] Run:
  - `uv run --extra dev pytest -q tests/test_hdr_photo.py tests/test_raw_file_processor.py tests/gui/test_controller_flow.py tests/gui/test_controller_output.py tests/gui/test_controller_runtime_module.py tests/test_runtime_api.py`
  - `uv run --extra dev python -c "...load one DNG from /Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片 and print diagnostics..."`
  - `xcrun swift src/spektrafilm/data/macos/hdr_heif_encoder.swift`
  - `python3 -m compileall -q src/spektrafilm src/spektrafilm_gui tests`
  - `git diff --check`
- [ ] Self-audit until each answer is yes: runtime sidecar uses post-auto-exposure input, HEIC receives sidecar luminance, paper-limited look can produce HDR only when scene energy supports it, headroom is bounded, EXR remains a rendered-look archive, and old callers remain compatible.
