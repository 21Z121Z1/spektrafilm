# Color Management HDR Review Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Review and harden Spektrafilm's color-management and HDR processing so runtime, GUI, preview, save/export, and documentation carry the same explicit color/HDR contract.

**Architecture:** Keep the existing `IOParams` fields as the runtime source of truth and add a small workflow selector above them. GUI state maps to runtime params through `params_mapper`; runtime returns optional HDR scene metadata; controller/runtime display code consumes actual output encoding instead of assuming encoded sRGB. SDR behavior remains the default, and ACES/HDR behavior is opt-in.

**Tech Stack:** Python dataclasses, NumPy, Colour Science, Pillow ImageCms, OpenImageIO, Qt/napari GUI, pytest.

---

## Current Findings

Best-practice references checked during planning:

- ACES official docs define ACEScg as a scene-linear working space for CGI/rendering and compositing, with AP1 primaries and floating point storage: https://docs.acescentral.com/encodings/acescg/
- OpenColorIO ACES docs expose roles where `scene_linear` and `compositing_linear` map to ACEScg, while `default` maps to ACES2065-1: https://opencolorio.readthedocs.io/en/v2.4.0/configurations/aces_1.0.3.html
- Qt documents Display P3 as a wide-gamut display space with sRGB transfer, and lists named color-space transforms rather than requiring a forced sRGB intermediate: https://doc.qt.io/qt-6/qcolorspace.html
- OpenEXR standard attributes define `chromaticities` and `whiteLuminance` as the RGB color-characteristic metadata used to convert pixels to CIE XYZ: https://openexr.com/en/latest/StandardAttributes.html
- Android Ultra HDR states gain-map HDR must remain backward compatible with SDR and must include metadata that explains how to reconstruct HDR without clipping highlights or crushing shadows: https://developer.android.com/media/platform/hdr-image-format
- ITU-R BT.2408 is the in-force HDR operational practice reference family for HDR reference levels: https://www.itu.int/pub/R-REP-BT.2408

Observed repo issues to fix:

- `spektrafilm.color_management` exists, but `SettingsParams`, GUI state, persistence, and `params_mapper` do not expose or apply the workflow selector.
- GUI mapping currently hardcodes `params.io.output_cctf_encoding = True`, so ACES scene-linear/HDR output can be silently encoded as display output.
- GUI defaults created from runtime params hardcode `output_color_space="sRGB"` instead of preserving runtime params or workflow.
- Preview display transform converts everything through sRGB before applying the monitor profile, which loses wide-gamut Display P3 intent and mishandles linear ACES output.
- Controller stores output-layer metadata with `output_cctf_encoding=True` even when the runtime output is linear.
- File load has `load_image_payload()` available but the GUI path still discards input color metadata.
- The runtime simulator exposes only pixels, so HDR photo export cannot consume simulation scene-energy metadata without recomputing or guessing.
- `FilmingStage._compute_density_spectral_midgray_to_balance_print()` feeds encoded/mismatched midgray into `_rgb_to_film_raw()` and ignores current `input_color_space` / CCTF settings.

## File Structure

- Modify `src/spektrafilm/runtime/params_schema.py` to add `SettingsParams.color_management_workflow`.
- Modify `src/spektrafilm_gui/options.py`, `src/spektrafilm_gui/state.py`, `src/spektrafilm_gui/widget_specs.py`, and `src/spektrafilm_gui/params_mapper.py` to expose and map the workflow.
- Modify `src/spektrafilm/runtime/process.py`, `src/spektrafilm/runtime/pipeline.py`, and `src/spektrafilm/runtime/stages/filming.py` to return optional HDR scene metadata and use the active input encoding for midgray.
- Modify `src/spektrafilm_gui/controller_runtime.py`, `src/spektrafilm_gui/controller.py`, and `src/spektrafilm_gui/controller_layers.py` to carry actual output CCTF state and scene metadata through preview/save.
- Modify focused tests under `tests/` and `tests/gui/` before production changes.
- Create a final review report under `docs/color-management-hdr-review-2026-05-31.md`.

### Task 1: Red Tests For Workflow Mapping And Persistence

**Files:**
- Modify: `tests/gui/test_params_mapper.py`
- Modify: `tests/gui/test_persistence.py`
- Modify: `tests/test_photo_params.py`

- [ ] **Step 1: Add failing tests**

```python
def test_aces_reference_workflow_maps_runtime_io_to_linear_aces() -> None:
    state = PROJECT_DEFAULT_GUI_STATE.copy()
    state.simulation.color_management_workflow = "aces_reference"
    state.simulation.output_color_space = "sRGB"
    state.simulation.saving_color_space = "sRGB"
    state.simulation.saving_cctf_encoding = True

    params = build_params_from_state(state)

    assert params.settings.color_management_workflow == "aces_reference"
    assert params.io.input_color_space == "ACES2065-1"
    assert params.io.input_cctf_decoding is False
    assert params.io.output_color_space == "ACEScg"
    assert params.io.output_cctf_encoding is False
    assert params.io.output_clip_min is None
    assert params.io.output_clip_max is None
```

- [ ] **Step 2: Run the red tests**

Run:

```bash
.venv/bin/python -m pytest tests/gui/test_params_mapper.py tests/gui/test_persistence.py tests/test_photo_params.py -q
```

Expected: failure because `SimulationState.color_management_workflow` and `SettingsParams.color_management_workflow` do not exist.

- [ ] **Step 3: Implement mapping**

Add the workflow field, enum, widget spec, schema defaults, and call `apply_color_management_workflow_to_io()` after GUI state has been mapped to runtime params.

- [ ] **Step 4: Run the tests again**

Run:

```bash
.venv/bin/python -m pytest tests/gui/test_params_mapper.py tests/gui/test_persistence.py tests/test_photo_params.py -q
```

Expected: pass.

### Task 2: Red Tests For Runtime HDR Scene Metadata

**Files:**
- Modify: `tests/test_runtime_api.py`
- Modify: `tests/test_filming_stage.py`

- [ ] **Step 1: Add failing tests**

```python
def test_simulator_process_with_metadata_returns_scene_luminance() -> None:
    params = RuntimePhotoParams()
    params.settings.color_management_workflow = "aces_reference"
    simulator = Simulator(digest_params(params))
    image = np.full((4, 4, 3), 0.18, dtype=np.float32)

    result = simulator.process_with_metadata(image)

    assert result.image.shape == image.shape
    assert result.hdr_scene_energy is not None
    assert result.hdr_scene_energy.scene_luminance.shape == image.shape[:2]
    assert np.all(np.isfinite(result.hdr_scene_energy.scene_luminance))
```

- [ ] **Step 2: Run the red tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_runtime_api.py::test_simulator_process_with_metadata_returns_scene_luminance tests/test_filming_stage.py -q
```

Expected: failure because `process_with_metadata()` does not exist and midgray ignores the active input encoding.

- [ ] **Step 3: Implement metadata and midgray fix**

Add `SimulationPipelineResult`, `HDRSceneEnergyMetadata`, `process_with_metadata()`, `auto_exposure_with_ev()`, and make midgray conversion call `_rgb_to_film_raw()` with current `input_color_space` and `input_cctf_decoding`.

- [ ] **Step 4: Run the tests again**

Run:

```bash
.venv/bin/python -m pytest tests/test_runtime_api.py tests/test_filming_stage.py -q
```

Expected: pass.

### Task 3: Red Tests For GUI Preview, Metadata, And Save Contract

**Files:**
- Modify: `tests/gui/test_controller_runtime_module.py`
- Modify: `tests/gui/test_controller_output.py`
- Modify: `tests/gui/test_controller_flow.py`
- Modify: `tests/gui/test_controller_layers.py`

- [ ] **Step 1: Add failing tests**

```python
def test_execute_simulation_request_preserves_output_cctf_encoding() -> None:
    request = SimulationRequest(
        image=np.full((2, 2, 3), 0.18, dtype=np.float32),
        params=RuntimePhotoParams(),
        output_color_space="ACEScg",
        output_cctf_encoding=False,
        use_display_transform=True,
    )

    result = execute_simulation_request(request, run_simulation_fn=lambda image, params: image)

    assert result.output_color_space == "ACEScg"
    assert result.output_cctf_encoding is False
```

- [ ] **Step 2: Run the red tests**

Run:

```bash
.venv/bin/python -m pytest tests/gui/test_controller_runtime_module.py tests/gui/test_controller_output.py tests/gui/test_controller_flow.py tests/gui/test_controller_layers.py -q
```

Expected: failures where code still assumes encoded output.

- [ ] **Step 3: Implement GUI flow**

Carry `output_cctf_encoding` and `hdr_scene_energy` in request/result/layer metadata. Update display conversion to use source ICC profiles for encoded display spaces and a linear fallback for ACES/HDR spaces. Update save code to use `ColorEncoding` and preserve scene metadata when available.

- [ ] **Step 4: Run the tests again**

Run:

```bash
.venv/bin/python -m pytest tests/gui/test_controller_runtime_module.py tests/gui/test_controller_output.py tests/gui/test_controller_flow.py tests/gui/test_controller_layers.py -q
```

Expected: pass.

### Task 4: Red Tests For Input Color Metadata Loading

**Files:**
- Modify: `tests/gui/test_controller_flow.py`
- Modify: `src/spektrafilm_gui/controller.py`

- [ ] **Step 1: Add failing test**

```python
def test_load_input_image_applies_payload_color_encoding_to_gui_state(monkeypatch) -> None:
    payload = ImagePayload(
        pixels=np.full((2, 2, 3), 0.5, dtype=np.float32),
        color_encoding=ColorEncoding(color_space="Display P3", transfer="cctf", role="display"),
        metadata={},
    )
    monkeypatch.setattr(controller_module, "load_image_payload", lambda path: payload)

    controller.load_input_image("input.heic")

    assert widgets.input_image.input_color_space.currentText() == "Display P3"
    assert widgets.input_image.apply_cctf_decoding.isChecked() is True
```

- [ ] **Step 2: Run the red test**

Run:

```bash
.venv/bin/python -m pytest tests/gui/test_controller_flow.py::test_load_input_image_applies_payload_color_encoding_to_gui_state -q
```

Expected: failure because load path still uses `load_image_oiio()`.

- [ ] **Step 3: Implement load metadata application**

Use `load_image_payload()` in GUI loading and apply the detected color encoding to `InputImageState` through `apply_gui_state_sections(..., section_names=("input_image",))`.

- [ ] **Step 4: Run the focused GUI tests**

Run:

```bash
.venv/bin/python -m pytest tests/gui/test_controller_flow.py tests/gui/test_state_bridge.py -q
```

Expected: pass.

### Task 5: Documentation And Verification

**Files:**
- Create: `docs/color-management-hdr-review-2026-05-31.md`
- Modify: `docs/README.md`

- [ ] **Step 1: Write the review report**

Include completion assessment, fixed findings, remaining limitations, source references, and exact verification commands.

- [ ] **Step 2: Link the report**

Add the new report to the docs router.

- [ ] **Step 3: Run final gates**

Run:

```bash
.venv/bin/python -m pytest tests/test_color_management.py tests/test_filming_stage.py tests/test_color_reference.py tests/test_image_io_color_metadata.py tests/test_runtime_api.py tests/gui/test_params_mapper.py tests/gui/test_persistence.py tests/gui/test_controller_runtime_module.py tests/gui/test_controller_output.py tests/gui/test_controller_flow.py tests/gui/test_controller_layers.py -q
.venv/bin/python -m compileall -q src/spektrafilm src/spektrafilm_gui
git diff --check
```

Expected: all pass.

## Completion Confidence Loop

- [ ] Ask whether any remaining path still assumes sRGB or encoded output.
- [ ] Ask whether any HDR export path can write metadata without scene-energy data.
- [ ] Ask whether any GUI-visible state can diverge from runtime params.
- [ ] Ask whether SDR default behavior changed unexpectedly.
- [ ] Re-run focused tests after every fix, then run final gates before marking the goal complete.
