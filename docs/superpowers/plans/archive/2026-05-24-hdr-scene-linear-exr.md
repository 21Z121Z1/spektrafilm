# HDR Scene-Linear EXR Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make spektrafilm's HDR EXR export an explicit scene-linear output archive that preserves unclipped linear runtime values and records the reference-white luminance contract.

**Architecture:** Treat the simulated print/scan output as the rendered look, not as recoverable original scene energy. HDR EXR saves the runtime's linear output rendition without display CCTF or highlight clipping and tags it with `whiteLuminance=203`; future gain-map or sidecar work can graft calibrated scene energy onto that look, but this phase must not fake HDR headroom from a paper-limited image.

**Tech Stack:** Python 3.13, NumPy, colour-science, OpenImageIO, PySide/Qt GUI, pytest.

---

## Signal Model Decision

The paper/print/scan model can legitimately put paper white around `0.8`. That is not a bug in scene-linear EXR by itself: it means the saved linear output is a rendered reflectance/look where the brightest paper tone is below the `1.0` reference-white convention. Dividing it back up to force white to `1.0` would change the look unless a matching view transform also compensated for the scale.

Therefore this phase uses a conservative contract:

- runtime HDR output disables display CCTF and highlight clipping;
- EXR saves the actual linear runtime output values as authored by the current simulation;
- EXR writes `whiteLuminance=203` so consumers know the project reference-white luminance;
- EXR does not invent values above `1.0` when the simulated paper look has compressed them below `1.0`;
- a future scene-energy sidecar or luminance-graft phase is required for physically meaningful HDR headroom while preserving the paper look. *(Update 2026-05-25: A Dual-Layer HDR Mapping with Diffuse Lift and Specular Rolloff is now implemented for HEIC/HDR rendering, addressing this need).*

## Files

- Modify: `tests/gui/test_controller_output.py`
  - Add regression coverage that saving EXR preserves the float metadata payload rather than the clipped 8-bit preview layer.
  - Add regression coverage that EXR save constructs a linear scene encoding with unclipped highlights.
- Modify: `README.md`
  - Clarify that HDR EXR is a scene-linear archive of the rendered output, not recovered camera scene energy.
  - Clarify that values below `1.0` are valid when the paper/scan look places diffuse paper white below reference white.

No production-code change is expected unless tests expose a gap, because the current implementation already routes EXR saves through `ColorEncoding(... transfer="linear", role="scene", clip_highlights=False)` and passes `white_luminance=HDR_REFERENCE_WHITE_LUMINANCE_NITS`.

## Task 1: Add EXR Contract Tests

**Files:**
- Modify: `tests/gui/test_controller_output.py`

- [ ] **Step 1: Add a test that EXR save uses stored float output, not preview pixels**

Add this test near the existing EXR save tests:

```python
def test_save_output_layer_exr_uses_unclipped_float_metadata_not_preview_pixels(monkeypatch) -> None:
    float_image = np.array(
        [[[0.25, 1.5, 3.0], [0.1, 0.2, 0.3]]],
        dtype=np.float32,
    )
    preview = np.uint8(np.clip(float_image, 0.0, 1.0) * 255)
    output_layer = FakeLayer(
        preview,
        metadata={
            OUTPUT_FLOAT_DATA_KEY: float_image,
            OUTPUT_COLOR_SPACE_KEY: 'Display P3',
            OUTPUT_CCTF_ENCODING_KEY: False,
        },
    )
    controller = GuiController(viewer=object(), widgets=object())
    captured: dict[str, object] = {}
    gui_state = make_test_controller_gui_state()
    gui_state.simulation.saving_color_space = 'Display P3'
    gui_state.simulation.saving_cctf_encoding = True

    _configure_save_output(
        monkeypatch,
        controller,
        output_layer,
        gui_state,
        captured,
        filepath='output.exr',
        selected_filter='Images (*.exr)',
    )
    _capture_saved_output(monkeypatch, captured)

    controller.save_output_layer()

    saved_path, saved_image = captured['saved']
    assert saved_path == 'output.exr'
    np.testing.assert_allclose(saved_image, float_image)
    assert float(np.max(saved_image)) > 1.0
```

- [ ] **Step 2: Add a test that EXR save declares the scene-linear unclipped contract**

```python
def test_save_output_layer_exr_uses_linear_scene_unclipped_encoding(monkeypatch) -> None:
    float_image = np.full((2, 2, 3), 1.5, dtype=np.float32)
    output_layer = _make_output_layer(
        float_image,
        output_color_space='Display P3',
        output_cctf_encoding=False,
    )
    controller = GuiController(viewer=object(), widgets=object())
    captured: dict[str, object] = {}
    gui_state = make_test_controller_gui_state()
    gui_state.simulation.saving_color_space = 'Display P3'
    gui_state.simulation.saving_cctf_encoding = True

    _configure_save_output(
        monkeypatch,
        controller,
        output_layer,
        gui_state,
        captured,
        filepath='output.exr',
        selected_filter='Images (*.exr)',
    )
    _capture_saved_output(monkeypatch, captured)

    controller.save_output_layer()

    save_encoding = captured['save_kwargs']['encoding']
    assert save_encoding.color_space == 'Display P3'
    assert save_encoding.transfer == 'linear'
    assert save_encoding.role == 'scene'
    assert save_encoding.clip_highlights is False
```

- [ ] **Step 3: Run the new tests and verify RED or existing GREEN**

Run:

```bash
uv run --extra dev pytest -q tests/gui/test_controller_output.py::test_save_output_layer_exr_uses_unclipped_float_metadata_not_preview_pixels tests/gui/test_controller_output.py::test_save_output_layer_exr_uses_linear_scene_unclipped_encoding
```

Expected: If the current implementation is complete, these may already pass. If they fail, fix the production boundary they expose before continuing.

## Task 2: Fix Any Exposed EXR Boundary Gaps

**Files:**
- Modify if needed: `src/spektrafilm_gui/controller.py`
- Modify if needed: `src/spektrafilm/utils/io.py`

- [ ] **Step 1: If EXR saves clipped preview pixels, route through output float metadata**

Expected controller logic:

```python
float_image_data = self._output_layer_float_data()
if float_image_data is None:
    image_data = runtime.normalized_image_data(np.asarray(output_layer.data)[..., :3])
else:
    image_data = np.asarray(float_image_data)[..., :3]
```

- [ ] **Step 2: If EXR save keeps display encoding, force linear scene save encoding**

Expected save routing:

```python
if exr_save or hdr_photo_save:
    saving_cctf_encoding = False
...
'output_clip_max': not (exr_save or hdr_photo_save),
```

- [ ] **Step 3: If EXR misses reference white metadata, pass the shared constant**

Expected save kwargs:

```python
save_kwargs = {"encoding": saving_encoding}
if exr_save:
    save_kwargs["white_luminance"] = HDR_REFERENCE_WHITE_LUMINANCE_NITS
```

## Task 3: Update README Signal Explanation

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Clarify what HDR EXR means**

Update the HDR EXR section to state:

```markdown
HDR EXR is a scene-linear archive of the simulated output rendition. If the selected paper/scan look places paper white around `0.8`, the EXR may also place that visual paper white below `1.0`; this preserves the look. It is not a claim that original camera scene energy has been recovered.
```

- [ ] **Step 2: Clarify the future sidecar boundary**

Add:

```markdown
Physically meaningful highlight headroom above that paper-limited rendition requires a separate input/scene-energy signal and a luminance-graft export transform. That belongs to the gain-map/HDR-rendition work, not to the basic EXR archive path. *(Update 2026-05-25: This has now been implemented using Dual-Layer HDR Mapping for HEIC exports).*
```

## Task 4: Verification And Confidence Loop

- [ ] **Step 1: Run targeted tests**

```bash
uv run --extra dev pytest -q tests/gui/test_controller_output.py::test_save_output_layer_exr_writes_hdr_reference_white_luminance tests/gui/test_controller_output.py::test_save_output_layer_appends_hdr_default_extension_when_panel_returns_stem tests/gui/test_controller_output.py::test_save_output_layer_exr_uses_unclipped_float_metadata_not_preview_pixels tests/gui/test_controller_output.py::test_save_output_layer_exr_uses_linear_scene_unclipped_encoding tests/test_image_io_color_metadata.py::test_exr_writes_chromaticities_colorspace_and_preserves_hdr_values tests/test_color_management.py::test_output_encoding_from_io_maps_hdr_exr_contract tests/gui/test_params_mapper.py::test_build_params_forces_acescg_input_and_output_scene_linear_contract
```

- [ ] **Step 2: Run static checks**

```bash
python3 -m compileall -q src/spektrafilm src/spektrafilm_gui tests
git diff --check
```

- [ ] **Step 3: Self-audit**

Ask these questions and fix any "no":

- Does EXR save the stored float output rather than the viewer preview?
- Does EXR force linear output even if GUI saving CCTF is enabled?
- Does EXR preserve values above `1.0`?
- Does EXR write `whiteLuminance=203`?
- Does the documentation avoid promising recovered physical scene energy?
- Are unrelated in-flight GPU/color-management changes untouched?
