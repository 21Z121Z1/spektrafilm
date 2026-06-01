# ACES Output Transform HDR Metadata Encoding Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use test-driven-development to add failing coverage first. Keep edits scoped to ACES preview, HDR metadata validation, and GUI runtime/save encoding split. Do not revert unrelated dirty worktree changes.

**Goal:** Remove the three remaining risks from `docs/color-management-hdr-review-2026-05-31.md`: replace linear ACES preview's sRGB approximation with a named ACES output-view transform, validate HDR scene sidecars and gain-map metadata with real samples/tooling, and split GUI manual runtime output encoding from save encoding.

**Architecture:** Add a small colour-management display-view helper for ACES scene-linear output, route GUI runtime CCTF through a new `SimulationState.output_cctf_encoding`, keep saving CCTF as a separate file-export control, and extend the existing profile-aware HDR raw validation script/report with explicit Android Ultra HDR / ISO gain-map / EXR metadata checks. The runtime defaults stay SDR-compatible.

**Tech Stack:** Python dataclasses, NumPy, Colour Science already in the project, Pillow ImageCms, OpenImageIO/OpenEXR CLI verification where available, existing pytest-style GUI/runtime tests, existing local DNG validation samples.

**Implementation status (2026-05-31):** Completed. The final implementation adds a local ACES SDR video output view, preserves scene-linear highlights before preview rendering, splits runtime/save CCTF state in GUI and macOS bridge, refreshes real DNG HDR metadata validation, and updates the review report.

---

### Task 1: Establish Current Contracts And External References

**Files:** `docs/color-management-hdr-review-2026-05-31.md`, `src/spektrafilm_gui/controller_runtime.py`, `src/spektrafilm_gui/state.py`, `src/spektrafilm_gui/params_mapper.py`, `tools/validate_profile_aware_hdr_raw_samples.py`

**Step 1: Read official references and map them to local boundaries**
- Use ACES Output Transform docs as the preview reference: scene-linear ACES to display-referred output is a named Output Transform, not a raw RGB-to-sRGB conversion.
- Use OpenColorIO ACES docs as the longer-term config option, but do not add an unverified heavyweight runtime dependency unless local/package reality supports it.
- Use Android Ultra HDR v1.1 docs for the JPEG gain-map metadata expectation: Ultra HDR and ISO 21496-1 metadata should be encoded together for cross-platform compatibility.
- Use OpenEXR/OpenImageIO metadata docs for EXR/OIIO attribute assertions.

**Step 2: Confirm local constraints**
- Verify `PyOpenColorIO` is not a current dependency and local Python imports may hang in the current dyld state.
- Prefer an explicit local ACES output-view helper over adding an unvalidated dependency in this turn.

### Task 2: Add Failing Tests For The Three Risks

**Files:** `tests/gui/test_controller_runtime_module.py`, `tests/gui/test_params_mapper.py`, `tests/gui/test_persistence.py`, `tests/gui/test_controller_flow.py`, `tests/gui/test_controller_output.py`

**Step 1: ACES preview**
- Add or update a test so ACEScg/ACES2065-1 linear preview calls a dedicated ACES output-view function and reports a status containing `ACES`.
- The test must fail against the old `"sRGB view approximation"` branch.

**Step 2: GUI runtime/save encoding split**
- Add mapper tests where `output_cctf_encoding=True` and `saving_cctf_encoding=False` under manual workflow produce runtime output CCTF `True`.
- Add default/persistence tests for the new state field.
- Add controller tests so async/sync simulation request fallback defaults use `state.simulation.output_cctf_encoding`, not saving CCTF.
- Add save tests proving file export still uses `saving_cctf_encoding`.

**Step 3: HDR metadata validation**
- Add testable helpers to the validation script so metadata expectations can be inspected without requiring a full DNG run in unit tests.
- Assert Android/ISO gain-map metadata checks and EXR attribute checks are represented in the generated report JSON/markdown.

### Task 3: Implement ACES Output Preview Helper

**Files:** `src/spektrafilm/color_management.py`, `src/spektrafilm_gui/controller_runtime.py`

**Step 1: Add a named ACES SDR output-view helper**
- Implement `aces_sdr_video_view_transform()` as an explicit ACES scene-linear preview transform for SDR sRGB display.
- Convert ACES scene-linear RGB through Colour into linear sRGB primaries before the local fitted ACES SDR video output view.
- Preserve values above 1.0 until the display-view transform; only negative scene values are clipped at the preview boundary.
- Apply a bounded ACES-style rendering curve and sRGB display encoding, with clear naming and documentation that this is Spektrafilm's local ACES SDR video view until an OCIO config is installed.

**Step 2: Route linear ACES preview through the helper**
- Replace the old `RGB_to_RGB(... output=sRGB)` approximation branch.
- Return a status that explicitly says `Display transform: ACES SDR video output transform`.
- Keep failure fallback unchanged so GUI does not crash if the transform raises.

### Task 4: Split Runtime Output Encoding From Save Encoding

**Files:** `src/spektrafilm_gui/state.py`, `src/spektrafilm_gui/widget_specs.py`, `src/spektrafilm_gui/widget_sections.py`, `src/spektrafilm_gui/params_mapper.py`, `src/spektrafilm_gui/controller.py`

**Step 1: Add GUI state field**
- Add `SimulationState.output_cctf_encoding`.
- In `gui_state_from_params()`, seed it from `params.io.output_cctf_encoding`.
- Default manual state remains `sRGB + output CCTF true + saving CCTF true`.

**Step 2: Map params correctly**
- Use `state.simulation.output_cctf_encoding` for runtime `params.io.output_cctf_encoding`.
- Leave `saving_cctf_encoding` for `save_image_oiio()` only.
- Keep `aces_reference` workflow overriding runtime output to linear ACEScg through the existing workflow helper.

**Step 3: Expose and persist safely**
- Add widget spec text for runtime output CCTF and keep it hidden or colocated with existing output settings consistently with current GUI layout.
- Ensure old persisted JSON missing the new field backfills from `PROJECT_DEFAULT_GUI_STATE`.

### Task 5: Extend Real-Sample HDR Metadata Validation

**Files:** `tools/validate_profile_aware_hdr_raw_samples.py`, `docs/hdr_profile_aware_raw_validation.md`, `docs/hdr_profile_aware_raw_validation.json`

**Step 1: Make metadata checks explicit**
- Add validation output sections for:
  - scene-luminance sidecar shape/finite/nonnegative and process parity,
  - Android Ultra HDR / ISO gain-map compatibility expectations,
  - EXR metadata/chromaticity expectations where EXR export is available.
- Keep real DNG selection bounded for runtime.

**Step 2: Run the existing local sample validation when feasible**
- Use the existing sample directory from the prior validation report.
- If Python dynamic library loading still blocks the run, document exact blocker and keep the script/report updated with the best available previous evidence.

### Task 6: Update Documentation And Verification

**Files:** `docs/color-management-hdr-review-2026-05-31.md`, `docs/hdr_profile_aware_raw_validation.md`, possibly `docs/README.md`

**Step 1: Update risk status**
- Replace the three remaining-risk bullets with implemented status and any residual limitations.
- Cite official reference URLs in the document, not just chat.

**Step 2: Verification**
- Run targeted tests if the environment allows.
- Always run `py_compile` on changed Python files and `git diff --check`.
- If pytest/imports hang again, capture that as an environment blocker rather than claiming full pytest success. In the final run, targeted related pytest completed successfully with plugin autoload disabled.

**Step 3: Self-review loop**
- Re-read the final diff for old `saving_cctf_encoding` runtime fallbacks and old `sRGB view approximation` status.
- Confirm no SDR default changed.
- Confirm docs do not claim stronger Apple/Android device-rendering validation than was actually run.
