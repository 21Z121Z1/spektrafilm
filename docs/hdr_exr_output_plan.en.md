> This is an English translation of the Chinese original. For the authoritative version, see the Chinese original.

# HDR EXR Output Implementation Plan

This document records the key paths, blocking points, and an actionable implementation plan related to HDR EXR output in spektrafilm's current image processing pipeline. The goal is clear: when saving `.exr`, the output pixels should allow scene-linear highlight values, and RGB channels can be greater than `1.0`.

## Goals

1. `.exr` output preserves floating-point HDR data, at least allowing `max(rgb) > 1.0` in highlight regions.
2. PNG/JPEG and napari preview maintain existing SDR behavior, without breaking GUI display due to HDR EXR changes.
3. EXR output uses linear data by default, with no CCTF encoding and no upper clipping.
4. Preserve color space metadata; EXR writes `chromaticities` to prevent downstream applications from misreading wide-gamut or ACES data as sRGB.
5. Default behavior should be compatible with the current project as much as possible: when ordinary users do not enable HDR output, the runtime still returns display-ready results within the `0..1` range.

## Research and Search Conclusions

### Official References

- The OpenEXR official technical introduction states that OpenEXR stores 16-bit or 32-bit floating-point pixels, suitable for high dynamic range images, and explicitly notes that `1.0` is not a clipping limit -- highlights brighter than paper white, flames, etc. can be represented with larger pixel values. Reference: [Technical Introduction to OpenEXR](https://openexr.com/en/latest/TechnicalIntroduction.html).
- In the OpenEXR standard attributes, `chromaticities` is used for CIE `(x, y)` primaries and white point description of RGB images, and `whiteLuminance` can also describe the luminance meaning of RGB `(1, 1, 1)`. Reference: [OpenEXR Standard Attributes](https://openexr.com/en/latest/StandardAttributes.html).
- OpenImageIO's `ImageOutput` writing workflow specifies width, height, channel count, and pixel format via `ImageSpec`, then writes pixels with `write_image()`. The current project's `save_image_oiio()` usage is consistent with the official pattern. Reference: [OpenImageIO ImageOutput: Writing Images](https://openimageio.readthedocs.io/en/latest/imageoutput.html).

### Project Search Conclusions

The local search covered keywords including `exr/openexr/hdr/imwrite/save/export/output/clip/cctf/srgb/linear`. The conclusions are as follows:

- The EXR write function is not the main bottleneck. `src/spektrafilm/utils/io.py`'s `save_image_oiio()` already supports `half` and `float` for `.exr`, and does not `np.clip(image_data, 0, 1)` like the PNG/JPEG branch does.
- The current runtime's final scanning stage clips output to `0..1`. The blocking point is in `src/spektrafilm/runtime/stages/scanning.py`'s `_apply_cctf_encoding_and_clip()`, where the last line is `np.clip(rgb, a_min=0, a_max=1)`.
- The GUI save path prefers the floating-point image from the output layer metadata rather than the 8-bit preview image. Therefore, as long as the runtime returns an HDR floating-point image, `save_output_layer()` can pass it to `save_image_oiio()`.
- The GUI preview path clips to `0..1` and converts to `uint8`, which is a reasonable display path and should not serve as the data source for saving EXR.
- Currently the GUI/runtime has several places that hardcode the output encoding status to `True`. When implementing HDR EXR, these must be changed; otherwise, linear HDR data will be incorrectly treated as having undergone CCTF encoding during saving, or decoding errors will occur during gamut conversion.

I also performed two small verifications:

1. After `save_image_oiio()` wrote `[[0.25, 1.5, 4.0]]` to `/tmp/spektrafilm_hdr_probe.exr` and read it back, the result was preserved as `[0.25, 1.5, 4.0]` with `max=4.0`. This confirms that the OIIO EXR read/write path can preserve values greater than 1.
2. The existing full simulation pipeline still returns `<= 1` results even with very bright inputs. A probe with bright input produced an output maximum of approximately `0.8157`. This is consistent with the clipping logic at the end of scanning.

## Current Processing Pipeline

### 1. Input Reading

The GUI file import entry points are at:

- `src/spektrafilm_gui/controller.py::GuiController.load_input_image()`
- `src/spektrafilm/utils/io.py::load_image_oiio()`

`load_image_oiio()` behavior:

- `uint8` and `uint16` are normalized to `0..1`.
- `half` and `float` are read in their original format without `0..1` normalization.
- Therefore, input EXR/TIFF float can preserve source data greater than `1.0`.

RAW import entry points are at:

- `src/spektrafilm_gui/controller.py::GuiController.load_raw_image()`
- `src/spektrafilm/utils/raw_file_processor.py::load_and_process_raw_file()`

RAW currently goes through `rawpy.postprocess(... output_bps=16)` then divided by `65535.0`, leaning toward a `0..1` linear working image. The core of HDR EXR output is not in RAW reading, but in whether the simulation output end allows scene-linear values greater than `1.0`.

### 2. GUI Cache and Preview

The input image is stored in:

- `GuiController._current_input_image`
- `GuiController._current_preview_image`

Preview conversion is at:

- `src/spektrafilm_gui/controller_runtime.py::prepare_input_color_preview_image()`
- `src/spektrafilm_gui/controller_runtime.py::prepare_output_display_image()`
- `src/spektrafilm_gui/controller_runtime.py::normalized_image_data()`

These functions apply `np.clip(..., 0, 1)` and ultimately generate `uint8` preview images. This layer is the display pipeline, and clipping is reasonable -- it should not serve as the data source for EXR saving.

### 3. Runtime Main Pipeline

Entry points:

- `src/spektrafilm/runtime/process.py::simulate()`
- `src/spektrafilm/runtime/process.py::Simulator.process()`
- `src/spektrafilm/runtime/pipeline.py::SimulationPipeline.process()`

Main stages:

1. `SimulationPipeline._preprocess()`
   - Convert to `np.double`.
   - Execute auto exposure.
   - Crop/resize.
2. `FilmingStage.expose()`
   - RGB to film raw.
   - Camera exposure compensation.
   - Highlight boost, diffusion, lens blur, halation.
   - Convert to `log_raw`.
3. `FilmingStage.develop()`
   - Film raw to CMY density.
4. `PrintingStage.expose()`
   - Negative density projected through enlarger light source to print raw.
   - Print exposure and correction.
   - Convert to `log_raw_print`.
5. `PrintingStage.develop()`
   - Print raw to print CMY density.
6. `ScanningStage.scan()`
   - Density to XYZ.
   - Black/white correction.
   - Glare.
   - XYZ to output RGB.
   - CCTF encoding and clipping.

Currently, HDR is eliminated by this last step.

### 4. Key Blocking Point in the Scanning Stage

`src/spektrafilm/runtime/stages/scanning.py`:

```python
def scan(self, density_channels: np.ndarray) -> np.ndarray:
    rgb = self._density_to_rgb(density_channels, use_lut=self._settings.use_scanner_lut)
    rgb = self._apply_blur_and_unsharp(rgb)
    return self._apply_cctf_encoding_and_clip(rgb)
```

`_density_to_rgb()` returns linear RGB:

```python
return colour.XYZ_to_RGB(
    xyz,
    colourspace=self._io.output_color_space,
    apply_cctf_encoding=False,
    illuminant=illuminant_xy,
)
```

But `_apply_cctf_encoding_and_clip()` applies a fixed clip at the end:

```python
return np.clip(rgb, a_min=0, a_max=1)
```

This is the core reason why EXR output cannot exceed `1.0`.

### 5. Potential Blocking Point in Black/White Correction

In `src/spektrafilm/runtime/services/color_reference.py::_correction_fucntion()`:

```python
return np.clip(m * y + q, 0, 1)
```

By default, `ScannerParams.black_correction` and `white_correction` are both `False`, so this is usually not triggered. However, if the user enables scanning white or black point correction, this will also clamp Y to `0..1`. In HDR mode, this logic needs to respect the same output clipping strategy -- at a minimum, it must not unconditionally clip highlights.

### 6. Save Path

GUI save entry point:

- `src/spektrafilm_gui/controller.py::GuiController.save_output_layer()`

Key behavior:

```python
float_image_data = self._output_layer_float_data()
if float_image_data is None:
    image_data = runtime.normalized_image_data(np.asarray(output_layer.data)[..., :3])
else:
    image_data = np.asarray(float_image_data)[..., :3]
```

This is good news for HDR: as long as the output layer has `OUTPUT_FLOAT_DATA_KEY`, saving uses the runtime floating-point result, not the preview `uint8` image.

Subsequently, color conversion is performed based on `source_color_space/source_cctf_encoding` from the layer metadata and `saving_color_space/saving_cctf_encoding` from the GUI:

```python
image_data = colour.RGB_to_RGB(
    image_data,
    source_color_space,
    saving_color_space,
    apply_cctf_decoding=source_cctf_encoding,
    apply_cctf_encoding=saving_cctf_encoding,
)
```

Then it calls:

```python
save_image_oiio(filepath, image_data, color_space=saving_color_space)
```

There are still two points that need to be fixed here:

- Currently, when simulation completes, both `_on_simulation_finished()` and `_run_simulation()` hardcode the output layer metadata's `output_cctf_encoding` to `True`.
- `params_mapper._apply_io()` also hardcodes `params.io.output_cctf_encoding = True`.

If HDR mode uses linear output, these hardcodings must be changed to actual parameter values.

### 7. EXR Write Function

`src/spektrafilm/utils/io.py::save_image_oiio()` current logic:

- PNG/JPEG: fixed `np.clip(image_data, 0, 1)`, convert to `uint8`.
- EXR 16-bit: convert to `np.float16`, `ImageSpec(..., "half")`.
- EXR 32-bit: convert to `np.float32`, `ImageSpec(..., "float")`.
- When `color_space` is not empty, writes `chromaticities`.

Therefore, the EXR branch in principle already satisfies the requirement for saving HDR floating-point values. What needs to be done is to ensure that the incoming `image_data` has not been clipped by the runtime and GUI upstream.

## Recommended Design

The recommendation is to separate "SDR output for display" from "scene-linear output for EXR saving" rather than removing all clipping. This way, the GUI remains stable and EXR can be HDR.

### New Runtime Output Clipping Parameters

Add to `src/spektrafilm/runtime/params_schema.py::IOParams`:

```python
output_clip_min: bool = True
output_clip_max: bool = True
```

Meaning:

- `output_clip_min=True`: clip negative output values to `0`. It is recommended to keep this switch `True` for HDR EXR in the initial phase to avoid negative pixels from wide-gamut conversion or sharpening affecting ordinary post-processing software.
- `output_clip_max=True`: clip highlight output values to `1`. HDR EXR mode must set this to `False`.

Both default to `True` to maintain current behavior.

### Scanning Stage Clips by Parameters

Change `ScanningStage._apply_cctf_encoding_and_clip()` to be parameterized:

```python
def _apply_cctf_encoding_and_clip(self, rgb: np.ndarray) -> np.ndarray:
    if self._io.output_cctf_encoding:
        rgb = colour.RGB_to_RGB(
            rgb,
            self._io.output_color_space,
            self._io.output_color_space,
            apply_cctf_decoding=False,
            apply_cctf_encoding=True,
        )

    if getattr(self._io, "output_clip_min", True):
        rgb = np.maximum(rgb, 0.0)
    if getattr(self._io, "output_clip_max", True):
        rgb = np.minimum(rgb, 1.0)
    return rgb
```

HDR EXR parameter combination:

```python
params.io.output_cctf_encoding = False
params.io.output_clip_min = True
params.io.output_clip_max = False
```

Ordinary SDR parameter combination remains:

```python
params.io.output_cctf_encoding = True
params.io.output_clip_min = True
params.io.output_clip_max = True
```

### Black/White Correction Respects the Same Clipping Strategy

Save the output clipping configuration when `ColorReferenceService` is initialized:

```python
self._output_clip_min = getattr(io_params, "output_clip_min", True)
self._output_clip_max = getattr(io_params, "output_clip_max", True)
```

Change the fixed clipping in `_correction_fucntion()` from:

```python
return np.clip(m * y + q, 0, 1)
```

to:

```python
value = m * y + q
if self._output_clip_min:
    value = np.maximum(value, 0.0)
if self._output_clip_max:
    value = np.minimum(value, 1.0)
return value
```

This way, when white point correction is enabled, HDR mode can still preserve luminance values `>1`.

### Add HDR EXR Output Toggle to GUI

It is recommended to add a new boolean item in the GUI's Simulation section:

```python
hdr_exr_output: bool
```

Suggested labels:

- Label: `HDR EXR output`
- Tooltip: `Keep the simulation output scene-linear for EXR saving; disables output CCTF and highlight clipping. Preview remains SDR.`

Files to modify:

- `src/spektrafilm_gui/state.py`
  - Add `hdr_exr_output: bool` to `SimulationState`
  - Default `False` in `gui_state_from_params()`
- `src/spektrafilm_gui/widget_specs.py`
  - `GUI_WIDGET_SPECS["simulation"]["hdr_exr_output"]`
- `src/spektrafilm_gui/widget_sections.py`
  - Place the new control in the Output section, near `output_color_space/saving_color_space/saving_cctf_encoding`
- `src/spektrafilm_gui/state_bridge.py`
  - Collect/apply the new state
- `src/spektrafilm_gui/persistence.py`
  - If persistence uses generic dataclass serialization, confirm the new field can be saved and loaded
- `tests/gui/*`
  - Update state, widget, and persistence related tests

Use this toggle in `src/spektrafilm_gui/params_mapper.py::_apply_io()`:

```python
hdr_output = bool(getattr(state.simulation, "hdr_exr_output", False))

params.io.output_color_space = state.simulation.output_color_space
params.io.output_cctf_encoding = not hdr_output
params.io.output_clip_min = True
params.io.output_clip_max = not hdr_output
```

Note: The current `_apply_io()` hardcodes `params.io.output_cctf_encoding = True` -- this must be changed.

### Output Layer Metadata Should No Longer Hardcode CCTF

The current async path:

```python
self._set_or_add_output_layer(
    result.display_image,
    float_image=result.float_image,
    output_color_space=result.output_color_space,
    output_cctf_encoding=True,
    use_display_transform=result.use_display_transform,
)
```

`SimulationResult` needs to carry the real `output_cctf_encoding`:

```python
@dataclass(slots=True)
class SimulationResult:
    mode_label: str
    display_image: np.ndarray
    float_image: np.ndarray
    output_color_space: str
    output_cctf_encoding: bool
    use_display_transform: bool
    status_message: str
```

`execute_simulation_request()` populates from `request.params.io.output_cctf_encoding`:

```python
output_cctf_encoding = bool(getattr(request.params.io, "output_cctf_encoding", True))
```

Then `_on_simulation_finished()` changes to:

```python
output_cctf_encoding=result.output_cctf_encoding,
```

The synchronous path `_run_simulation()` also changes to:

```python
output_cctf_encoding=params.io.output_cctf_encoding,
```

Otherwise, `save_output_layer()` will treat linear HDR output as CCTF-encoded data during saving.

### Force Linear for EXR Saving

`saving_cctf_encoding` is meaningful for PNG/JPEG, but HDR EXR is best fixed to linear. It is recommended to handle this by file extension in `save_output_layer()`:

```python
ext = Path(filepath).suffix.lower()
if ext == ".exr":
    saving_cctf_encoding = False
```

This way, even if `Saving CCTF encoding` is checked in the GUI, saving EXR will not encode HDR data with a display transfer function.

For greater transparency, a hint can be appended to the status bar:

```python
status_suffix = " (EXR saved as linear HDR)"
```

### Recommended EXR Color Spaces

For HDR EXR, the following are recommended:

1. `ACES2065-1`
2. `ITU-R BT.2020`
3. `ProPhoto RGB`

Among these, `ACES2065-1` is the most suitable choice for archiving or post-production exchange with open highlight ranges. Currently, `colorspace_chromaticities()` retrieves primaries and white points from `colour.RGB_COLOURSPACES`, and in theory can write `chromaticities` for the above color spaces.

Note that `_ICC_PROFILES` does not include `ACES2065-1`, but this only affects ICC embedding for PNG/JPEG, not EXR's `chromaticities`.

### EXR Bit Depth

Currently `save_image_oiio()` defaults to `bit_depth=32`, which is very safe for HDR EXR. No UI addition is needed initially.

Suggested strategy:

- Phase 1: EXR defaults to writing 32-bit float to ensure simple verification and avoid precision disputes.
- Later phases: Add an `exr_bit_depth` option allowing `16 half` or `32 float`.

OpenEXR `half` range is sufficient for common HDR highlights, but if very wide-range intermediate data or numerical analysis is needed later, `float` is more straightforward.

## Implementation Order

### Step 1: Runtime Parameterized Clipping

Files:

- `src/spektrafilm/runtime/params_schema.py`
- `src/spektrafilm/runtime/stages/scanning.py`
- `src/spektrafilm/runtime/services/color_reference.py`

Changes:

1. Add `output_clip_min/output_clip_max` to `IOParams`.
2. `ScanningStage._apply_cctf_encoding_and_clip()` uses `np.maximum/np.minimum` for separate clipping.
3. `ColorReferenceService`'s black/white correction clipping also uses the same strategy.

Acceptance criteria:

- With default parameters, existing pipeline smoke tests should all pass.
- After manually setting `params.io.output_cctf_encoding=False` and `params.io.output_clip_max=False`, the scanning stage no longer proactively clips RGB values greater than `1.0`.

### Step 2: GUI Exposes HDR Mode

Files:

- `src/spektrafilm_gui/state.py`
- `src/spektrafilm_gui/widget_specs.py`
- `src/spektrafilm_gui/widget_sections.py`
- `src/spektrafilm_gui/state_bridge.py`
- `src/spektrafilm_gui/params_mapper.py`
- `tests/gui/test_params_mapper.py`
- `tests/gui/test_state_bridge.py`
- `tests/gui/test_widgets.py`
- `tests/gui/test_persistence.py`

Changes:

1. Add `hdr_exr_output` state and widget.
2. Widget state change connects to `controller.request_auto_preview`.
3. In `_apply_io()`, HDR mode sets:
   - `output_cctf_encoding=False`
   - `output_clip_min=True`
   - `output_clip_max=False`
4. Default `hdr_exr_output=False`.

Acceptance criteria:

- In default state, `params.io.output_cctf_encoding is True` and `output_clip_max is True`.
- After enabling HDR, `params.io.output_cctf_encoding is False` and `output_clip_max is False`.

### Step 3: Fix Output Layer Metadata

Files:

- `src/spektrafilm_gui/controller_runtime.py`
- `src/spektrafilm_gui/controller.py`
- `tests/gui/test_controller_runtime_module.py`
- `tests/gui/test_controller_flow.py`
- `tests/gui/test_controller_output.py`

Changes:

1. Add `output_cctf_encoding` to `SimulationResult`.
2. `execute_simulation_request()` retrieves the real value from `request.params.io.output_cctf_encoding`.
3. `_on_simulation_finished()` and `_run_simulation()` no longer hardcode `True`.

Acceptance criteria:

- `OUTPUT_CCTF_ENCODING_KEY` in output layer metadata is consistent with the runtime parameter.
- `source_cctf_encoding` in `save_output_layer()` is correct during saving, avoiding incorrect decoding of linear HDR data.

### Step 4: EXR Save Strategy

Files:

- `src/spektrafilm_gui/controller.py`
- `src/spektrafilm/utils/io.py`
- `tests/gui/test_controller_output.py`
- New or extended `tests/test_exr_io.py`

Changes:

1. `save_output_layer()` recognizes the `.exr` extension.
2. Force `saving_cctf_encoding=False` when saving `.exr`.
3. Update `save_image_oiio()` docstring, clarifying that PNG/JPEG is SDR output while EXR preserves floating-point range.
4. Optional: `save_image_oiio()` sets additional metadata for EXR:
   - `chromaticities` is already implemented.
   - Consider `spec.attribute("oiio:ColorSpace", color_space)`.
   - Consider `spec.attribute("whiteLuminance", 1.0)`, but this requires the team to first define the semantics of `1.0`. In OpenEXR, `1.0` does not typically represent a clipping limit.

Acceptance criteria:

- When saving EXR, if the input floating-point image has `4.0`, reading it back still yields `4.0`.
- Saving PNG/JPEG still clips to SDR.

### Step 5: Testing and Regression

Suggested new tests:

```python
def test_save_exr_preserves_values_above_one(tmp_path):
    image = np.array([[[0.25, 1.5, 4.0]]], dtype=np.float32)
    path = tmp_path / "hdr.exr"

    save_image_oiio(str(path), image, bit_depth=32, color_space="ACES2065-1")
    loaded = load_image_oiio(str(path))

    np.testing.assert_allclose(loaded[..., :3], image, rtol=0, atol=1e-6)
    assert np.max(loaded) > 1.0
```

Suggested new scanning clipping unit test:

```python
def test_scanning_output_can_disable_highlight_clip():
    io = SimpleNamespace(
        output_cctf_encoding=False,
        output_color_space="ACES2065-1",
        output_clip_min=True,
        output_clip_max=False,
    )
    stage = object.__new__(ScanningStage)
    stage._io = io

    rgb = np.array([[[-0.1, 0.5, 2.0]]], dtype=np.float64)
    out = stage._apply_cctf_encoding_and_clip(rgb)

    np.testing.assert_allclose(out, [[[0.0, 0.5, 2.0]]])
```

Suggested new GUI metadata test:

```python
def test_simulation_result_records_linear_hdr_encoding_flag(...):
    ...
    params.io.output_cctf_encoding = False
    result = execute_simulation_request(...)
    assert result.output_cctf_encoding is False
```

Suggested end-to-end acceptance script or test:

1. Use a bright input image, e.g., a small image with a patch of `rgb=[8, 8, 8]`.
2. Disable auto exposure or fix exposure, and enable HDR EXR output.
3. Set output color space to `ACES2065-1` or `ITU-R BT.2020`.
4. Save as `.exr`.
5. Use `load_image_oiio()` or `oiiotool --stats` to verify `max > 1.0`.

## Recommended User Workflow

After implementation, the recommended workflow for GUI users is:

1. Use linear scene-referred TIFF/EXR for input files, or avoid premature tone mapping after RAW import.
2. Select `ACES2065-1`, `ITU-R BT.2020`, or `ProPhoto RGB` for `Output color space`.
3. Enable `HDR EXR output`.
4. Keep `Saving color space` and `Output color space` consistent to reduce secondary conversion during saving.
5. Use `.exr` as the file extension.
6. View in downstream software using a scene-linear/HDR workflow. Preview requires display transform or tone mapping -- luminance cannot be judged directly with a normal SDR viewer.

## Risks and Considerations

### Preview Is Not HDR

The napari preview will still clip the image to `0..1` and convert to `uint8`. This does not affect EXR saving because saving prioritizes the output layer's floating-point metadata. Not seeing differences above `1.0` in the preview is expected behavior.

### CCTF Must Be Handled Carefully

HDR EXR should write linear data. If `saving_cctf_encoding=True` during saving, highlight values may be altered by the display transfer function, or unexpected behavior may occur in certain color space functions. It is recommended to force `saving_cctf_encoding=False` for `.exr` saving.

### White/Black Correction May Compress Highlights

If `scan_white_correction` is enabled, the current `ColorReferenceService` will clip Y to `0..1`. HDR mode must also modify this; otherwise, even if the scanning stage does not clip, highlights may still be compressed during the correction stage.

### Values Greater Than 1 Do Not Necessarily Appear Naturally

Removing clipping is only a necessary condition and does not guarantee that any input will produce `>1`. If input, exposure, and print/scanner parameters all fall below paper white, the output may still be less than or equal to `1`. Acceptance testing should use explicit bright inputs and parameter combinations.

### Wide-Gamut Conversion May Produce Negative Values

In linear wide-gamut conversion, certain out-of-gamut colors may produce negative channels. In the first phase, it is recommended to keep `output_clip_min=True` and only open the highlight upper limit. If stricter color science or ACES pipeline work is needed later, an advanced option for "whether to preserve negative values" can be added.

## Minimum Code Change Checklist

First-phase minimum closed loop:

1. Add `output_clip_min=True` and `output_clip_max=True` to `IOParams`.
2. `ScanningStage._apply_cctf_encoding_and_clip()` clips by parameters.
3. `ColorReferenceService._correction_fucntion()` clips by parameters.
4. GUI adds `hdr_exr_output`, mapped to:
   - `params.io.output_cctf_encoding = False`
   - `params.io.output_clip_min = True`
   - `params.io.output_clip_max = False`
5. `SimulationResult` and output layer metadata record the real `output_cctf_encoding`.
6. `.exr` saving forces linear, i.e., `saving_cctf_encoding=False`.
7. Add EXR round-trip test and scanning clipping test.

After completing this set of changes, `save_image_oiio()`'s existing EXR float writing capability can truly take effect, and EXR output will be able to preserve HDR values greater than `1.0`.
