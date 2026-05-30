# ACES Color Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicit ACES reference color-management workflow that uses ACEScg as the scene-linear working space, ACES2065-1 as the scene-linear interchange/export space, and preserves existing SDR/sRGB behavior unless the workflow is selected.

**Architecture:** Keep the existing `ColorEncoding` contract as the authoritative low-level representation. Add a higher-level `ColorManagementWorkflow` preset layer in `spektrafilm.color_management`, expose it through runtime params and the GUI, and make the mapper apply the preset before building `IOParams`. The preset must not replace per-file ICC/EXR metadata detection; loaded file metadata still wins for input interpretation.

**Tech Stack:** Python 3.13, dataclasses, colour-science, OpenImageIO, Pillow/ImageCms, napari/Qt widgets, pytest.

---

## Evidence And Project Analysis

Official ACES guidance used for this design:

- ACEScg is the AP1 scene-linear working space for CGI/rendering/compositing; it is stored as floating point, allows negative values, and values above 1.0 should not be clamped as a normal processing step.
- ACES2065-1 is the AP0 scene-linear core/interchange space and is the only ACES interchange format.
- ACES 2 adds improved output/rendering transforms, but this project does not currently depend on OCIO/OpenColorIO. Adding an OCIO dependency would be larger than the requested support and unnecessary for a deterministic first implementation.
- The ASWF OpenColorIO-Config-ACES repository provides generated ACES configs, but its own docs position config generation as a separate package/tooling concern. Spektrafilm already has `colour-science` matrices and bundled ICC/EXR metadata support, so the best first implementation is an internal ACES workflow preset using those existing primitives.

Local project findings:

- `src/spektrafilm/color_management.py` already defines `ColorEncoding`, ACES color-space constants, and scene-linear unclipped behavior for ACES spaces.
- `src/spektrafilm/runtime/params_schema.py` has `IOParams` for input/output color spaces and clipping flags, but no high-level workflow/preset field.
- `src/spektrafilm_gui/state.py`, `src/spektrafilm_gui/options.py`, `src/spektrafilm_gui/params_mapper.py`, and `src/spektrafilm_gui/widget_sections.py` expose individual input/output/saving controls, but users must manually combine them correctly.
- `src/spektrafilm/utils/raw_file_processor.py` already demosaics RAW through linear ACES2065-1 and can convert to ACEScg. The new workflow should make ACEScg the default RAW target when selected.
- `src/spektrafilm/utils/io.py` already reads/writes ACES EXR chromaticities and ACES ICC profiles for non-EXR formats. The workflow should use these capabilities rather than adding OCIO.
- `src/spektrafilm_gui/controller.py` saves output based on recorded layer metadata. The workflow must preserve that behavior and only change the intended default save target/encoding.

## Design

Add two workflow modes:

- `manual`: current behavior. Existing individual input/output/save controls remain authoritative.
- `aces_reference`: ACES best-practice mode. Runtime input is first converted from its tagged source space into scene-linear ACEScg, runtime output is scene-linear ACEScg, saved interchange defaults to scene-linear ACES2065-1, CCTF is disabled, negative and highlight clipping are disabled for ACES runtime output.

The workflow is intentionally conservative:

- It does not add OCIO or ACES Output Transforms yet. GUI preview remains the existing colorimetric sRGB/display-profile preview path.
- It does not silently reinterpret non-ACES files. Existing file metadata detection still updates the input controls when loading a file.
- It does not force PNG/JPEG to save linear ACES. Existing save guards still reject linear PNG/JPEG and guide users toward EXR for scene-linear ACES.
- *(Note 2026-05-25: The HDR export pipeline was upgraded to Dual-Layer HDR Mapping with RGB gain maps. The ACES workflow remains fully compatible with this extended HDR encoding.)*

## Files

- Modify `src/spektrafilm/color_management.py`: add workflow enum constants and `apply_color_management_workflow_to_io`.
- Modify `src/spektrafilm/runtime/params_schema.py`: add `SettingsParams.color_management_workflow`.
- Modify `src/spektrafilm_gui/options.py`: expose `ColorManagementWorkflows`.
- Modify `src/spektrafilm_gui/state.py`: add `SimulationState.color_management_workflow`, persist it through defaults.
- Modify `src/spektrafilm_gui/params_mapper.py`: map workflow and apply workflow preset to IO.
- Modify `src/spektrafilm_gui/widget_specs.py`: add GUI enum/spec text.
- Modify `src/spektrafilm_gui/widget_sections.py`: show workflow selector in Output.
- Modify `src/spektrafilm_gui/controller_profile_sync.py`: keep workflow across profile default sync.
- Modify `README.md`: document ACES workflow behavior and limitations.
- Add or update tests in `tests/test_color_management.py`, `tests/gui/test_params_mapper.py`, `tests/gui/test_persistence.py`, and `tests/gui/test_controller_output.py`.

## Tasks

### Task 1: Color Management Workflow Contract

**Files:**
- Modify: `src/spektrafilm/color_management.py`
- Test: `tests/test_color_management.py`

- [ ] Write failing tests for `apply_color_management_workflow_to_io`:
  - `manual` leaves `IOParams` unchanged.
  - `aces_reference` sets input/output to ACEScg, output CCTF off, output clip min/max off, and default save intent to ACES2065-1 through helper return values.
  - Unknown workflows raise `ValueError`.
- [ ] Run `.venv/bin/python -m pytest tests/test_color_management.py -q` and confirm the new tests fail because the helper does not exist.
- [ ] Implement `ColorManagementWorkflow = Literal["manual", "aces_reference"]`, constants, and `apply_color_management_workflow_to_io(io, workflow)`.
- [ ] Run `.venv/bin/python -m pytest tests/test_color_management.py -q` and confirm the tests pass.

### Task 2: Runtime And GUI State Mapping

**Files:**
- Modify: `src/spektrafilm/runtime/params_schema.py`
- Modify: `src/spektrafilm_gui/options.py`
- Modify: `src/spektrafilm_gui/state.py`
- Modify: `src/spektrafilm_gui/params_mapper.py`
- Test: `tests/gui/test_params_mapper.py`
- Test: `tests/gui/test_persistence.py`

- [ ] Write failing GUI mapper tests showing `color_management_workflow="aces_reference"` maps runtime settings and IO to the ACES reference contract.
- [ ] Write a persistence test showing older saved GUI state JSON without `color_management_workflow` loads as `manual`.
- [ ] Run `.venv/bin/python -m pytest tests/gui/test_params_mapper.py tests/gui/test_persistence.py -q` and confirm the new tests fail for missing fields/enum/helper behavior.
- [ ] Add `SettingsParams.color_management_workflow = "manual"`.
- [ ] Add `ColorManagementWorkflows` enum with `manual` and `aces_reference`.
- [ ] Add `SimulationState.color_management_workflow` defaulting to `manual`.
- [ ] Map the state value into runtime settings and call the workflow helper after ordinary IO mapping.
- [ ] Run `.venv/bin/python -m pytest tests/gui/test_params_mapper.py tests/gui/test_persistence.py -q` and confirm the tests pass.

### Task 3: GUI Exposure And Save Semantics

**Files:**
- Modify: `src/spektrafilm_gui/widget_specs.py`
- Modify: `src/spektrafilm_gui/widget_sections.py`
- Modify: `src/spektrafilm_gui/controller_profile_sync.py`
- Test: `tests/gui/test_controller_output.py`
- Test: `tests/gui/test_app.py`

- [ ] Write failing tests that the Output section exposes `color_management_workflow` and app signal wiring includes preview refresh for workflow changes.
- [ ] Write or adjust save tests so ACES reference state saving to `.exr` uses ACES2065-1 linear encoding and does not CCTF encode.
- [ ] Run `.venv/bin/python -m pytest tests/gui/test_controller_output.py tests/gui/test_app.py -q` and confirm the new tests fail.
- [ ] Add workflow enum registration and tooltip.
- [ ] Place workflow selector at the top of the Output section.
- [ ] Keep workflow in profile sync fields so film/print profile changes do not silently reset it.
- [ ] Wire workflow changes to preview refresh in `app.py`.
- [ ] Run `.venv/bin/python -m pytest tests/gui/test_controller_output.py tests/gui/test_app.py -q` and confirm the tests pass.

### Task 4: Documentation And Regression Sweep

**Files:**
- Modify: `README.md`

- [ ] Document the ACES reference workflow in the GUI section and the color-management roadmap section.
- [ ] Run targeted tests:
  - `.venv/bin/python -m pytest tests/test_color_management.py tests/gui/test_params_mapper.py tests/gui/test_persistence.py tests/gui/test_controller_output.py tests/gui/test_app.py -q`
- [ ] Run broad color/runtime sanity checks:
  - `.venv/bin/python -m pytest tests/test_image_io_color_metadata.py tests/test_raw_file_processor.py tests/test_gpu_color_chain.py tests/test_pipeline_smoke.py -q`
- [ ] Run syntax check:
  - `python3 -m compileall -q src/spektrafilm src/spektrafilm_gui tests`
- [ ] Self-audit against ACES facts and project constraints:
  - ACEScg is runtime working space.
  - ACES2065-1 is interchange save default.
  - Linear ACES values are unclipped.
  - Existing manual mode remains unchanged.
  - GPU and HDR behavior are not disabled.

## Confidence Loop

Before completion, ask: "Do I have 100% factual confidence that this implementation meets the goal?" If not, inspect each remaining risk:

- A workflow field exists in state but is not persisted or defaults incorrectly.
- GUI changes do not trigger preview refresh.
- Save path converts with a stale source encoding.
- Linear ACES accidentally goes through PNG/JPEG.
- ACES reference mode breaks existing manual-mode tests.
- Existing dirty GPU/HDR changes are accidentally reverted.

Repeat fix and verification until the evidence is current and direct.
