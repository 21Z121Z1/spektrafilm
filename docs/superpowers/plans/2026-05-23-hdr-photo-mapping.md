# HDR Photo Mapping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Export HDR photos from spektrafilm as natural, scene-linear film simulations with an explicit diffuse/paper-white anchor, a controlled SDR rendition, and an HDR gain-map rendition instead of a simple clipped base image.

**Architecture:** Keep the runtime scanner output scene-linear and unclipped for HDR mode. At file-export time, derive a normalized HDR rendition where diffuse/paper white is `1.0` (using a Dual-Layer Mapping consisting of a Diffuse Lift and a Specular Rolloff curve to extend the paper-limited simulation), derive a separate tone-mapped SDR base rendition where diffuse white lands below clipping, and pass both renditions to the macOS CoreImage HEIF encoder so Apple generates the gain map from author-controlled SDR/HDR pairs.

**Tech Stack:** Python 3.13, NumPy, colour-science, OpenImageIO, PySide/Qt GUI, Swift/CoreImage HEIF representation, pytest.

---

## Goal Definition

`/goal`: Implement correct HDR output mapping for still-photo export.

Success means:

- EXR remains the high-fidelity scene-linear export path and records the intended reference/diffuse white luminance metadata.
- HEIC/HEIF HDR photo export no longer uses `clip(hdr, 0, 1)` as the SDR base.
- HEIC/HEIF export constructs two same-colorimetry linear renditions:
  - HDR rendition: scene-linear scan normalized by an explicit diffuse-white anchor.
  - SDR base rendition: hue-preserving tone-mapped fallback image with diffuse white below hard clipping and specular highlights compressed into the remaining SDR range.
- Gain-map headroom is bounded by an authoring policy, not by one arbitrary hot pixel.
- Runtime film simulation behavior stays scene-linear; output mapping is an export/view transform, not a change to film density/scanning physics.

## References And Conclusions

- ITU-R BT.2408-6 defines HDR Reference White/diffuse white as the nominal signal for a 100% Lambertian reflector and gives 203 cd/m2 as the reference-white luminance for PQ or 1000 cd/m2 HLG production. This supports using an explicit diffuse-white anchor and reserving headroom for brighter speculars.
- ACES documentation separates a scene-linear representation from an output transform: rendering/tone mapping happens for a target display and should not be confused with scene-referred image values. This supports keeping spektrafilm runtime scene-linear and adding mapping only at export.
- Adobe Gain Map documentation says authoring software should create both SDR and HDR renditions in the same linear colorimetry, then derive the gain map from their log ratio. This directly invalidates the current simple-clamp SDR base.
- Android Ultra HDR documentation also models gain maps in log space with creator-controlled max content boost. This supports capping/export-policy headroom rather than letting one outlier set the whole image headroom.
- Apple CoreGraphics/CoreImage HDR documentation exposes content headroom and HDR gain-map representation options; CoreGraphics has extended-linear color spaces such as extended linear Display P3. This supports feeding CoreImage linear SDR/HDR sources plus content headroom.
- **Dual-Layer HDR Mapping (Diffuse Lift + Specular Rolloff):** The simulation SDR aesthetic includes natural high-light compression (e.g., scene_y=1.0 maps to look_y=0.83). Rather than just "grafting" highlights which breaks midtones, HDR generation uses a two-layer approach:
  1. A **Diffuse Lift** uncompresses the paper-limited `look_y` locally around `scene_y=1.0` to reach the true HDR diffuse target (`1.0`).
  2. A **Specular Rolloff** uses a filmic/logistic curve to extract and compress high energy (`scene_y > 1.0`), smoothly adding it as a delta on top of the diffuse layer without hard clipping.

## Current Blockers

*(Update 2026-05-25: These blockers have been largely resolved. `hdr_photo.py` now uses Dual-Layer HDR Mapping (Diffuse Lift + Specular Rolloff). The unlifted SDR and lifted HDR renditions are separated and sent to the Swift encoder, which generates color (RGB) gain maps (`hdrGainMapAsRGB=true`). An "HDR Export Settings" GUI panel allows explicit control over parameters like `hdr_diffuse_lift_strength`, `max_headroom`, and rolloff.)*

- `src/spektrafilm/utils/hdr_photo.py` currently treats the maximum RGB channel as content headroom. A single `100.0` pixel makes the whole image advertise +6.64 stops, which can flatten normal highlights.
- `src/spektrafilm/data/macos/hdr_heif_encoder.swift` currently creates the SDR base by clamping the HDR CIImage to `[0, 1]`. That clips all SDR highlight detail and leaves SDR fallback appearance to a hard cutoff.
- There is no explicit diffuse-white or paper-white mapping policy in HDR photo export. `1.0` is implicitly used as every kind of white at once.
- The Swift encoder uses one color-space object for float input and encoded HEIF output. Linear float input should use an extended-linear color space where available; 8-bit base output should use the matching encoded display color space.
- GUI EXR save path does not pass `whiteLuminance`, despite `save_image_oiio()` supporting it.

## File Structure

- Modify `src/spektrafilm/utils/hdr_photo.py`
  - Add `HDRPhotoMapping` and `HDRPhotoRenditions`.
  - Add `prepare_hdr_photo_renditions()` with validation, diffuse-white normalization, hue-preserving SDR tone mapping, and bounded headroom.
  - Update `save_hdr_photo_heic()` to write separate SDR and HDR raw float payloads.
  - Restrict HEIC-friendly export spaces to spaces with reliable CoreImage encoded/linear pairs; fall back to Display P3.
- Modify `src/spektrafilm/data/macos/hdr_heif_encoder.swift`
  - Accept separate SDR and HDR RGBA float raw files.
  - Use linear CGColorSpace for CIImage inputs and encoded CGColorSpace for HEIF output.
  - Remove the internal `CIColorClamp` SDR base generation.
- Modify `src/spektrafilm_gui/controller.py`
  - Pass `white_luminance=203.0` for EXR HDR saves.
- Modify tests:
  - `tests/test_hdr_photo.py`
  - `tests/test_image_io_color_metadata.py`
  - `tests/gui/test_controller_output.py`

## Task 1: Add Failing HDR Mapping Tests

**Files:**
- Modify: `tests/test_hdr_photo.py`
- Modify: `tests/test_image_io_color_metadata.py`
- Modify: `tests/gui/test_controller_output.py`

- [ ] **Step 1: Replace the headroom-only test with mapping behavior tests**

```python
from spektrafilm.utils.hdr_photo import (
    HDRPhotoMapping,
    _rgba_float_payload,
    prepare_hdr_photo_renditions,
)


def test_hdr_photo_mapping_builds_authored_sdr_and_hdr_renditions() -> None:
    image = np.array([[[1.0, 1.0, 1.0], [4.0, 4.0, 4.0]]], dtype=np.float32)
    mapping = HDRPhotoMapping(diffuse_white=1.0, sdr_paper_white=0.9, max_headroom=4.0)

    renditions = prepare_hdr_photo_renditions(image, mapping=mapping)

    assert renditions.headroom == pytest.approx(4.0)
    np.testing.assert_allclose(renditions.hdr_rgb[0, 0], [1.0, 1.0, 1.0])
    np.testing.assert_allclose(renditions.sdr_rgb[0, 0], [0.9, 0.9, 0.9])
    np.testing.assert_allclose(renditions.sdr_rgb[0, 1], [1.0, 1.0, 1.0])
```

- [ ] **Step 2: Add hue-preservation and headroom-cap tests**

```python
def test_hdr_photo_sdr_tone_map_preserves_hue_ratios() -> None:
    image = np.array([[[4.0, 2.0, 1.0]]], dtype=np.float32)
    mapping = HDRPhotoMapping(diffuse_white=1.0, sdr_paper_white=0.9, max_headroom=4.0)

    renditions = prepare_hdr_photo_renditions(image, mapping=mapping)

    np.testing.assert_allclose(renditions.sdr_rgb[0, 0], [1.0, 0.5, 0.25], rtol=1e-6)


def test_hdr_photo_headroom_caps_extreme_outliers() -> None:
    image = np.array([[[0.25, 1.5, 100.0]]], dtype=np.float32)
    mapping = HDRPhotoMapping(diffuse_white=1.0, sdr_paper_white=0.9, max_headroom=8.0)

    renditions = prepare_hdr_photo_renditions(image, mapping=mapping)
    payload = _rgba_float_payload(renditions.hdr_rgb, headroom=renditions.headroom)

    assert renditions.headroom == pytest.approx(8.0)
    assert float(payload[..., :3].max()) == pytest.approx(8.0)
```

- [ ] **Step 3: Update the IO dispatch test to assert mapped HDR data reaches the encoder**

```python
def fake_save_hdr_photo_heic(filename, image_data, *, color_space) -> None:
    captured["filename"] = filename
    captured["image_data"] = image_data.copy()
    captured["color_space"] = color_space
```

Expected behavior after implementation: `image_data` remains the original scene-linear source passed into `save_image_oiio()`; the HDR mapping happens inside `save_hdr_photo_heic()`, not inside generic IO dispatch.

- [ ] **Step 4: Add GUI EXR metadata test**

```python
def test_save_output_layer_exr_writes_hdr_reference_white_luminance(monkeypatch) -> None:
    float_image = np.full((2, 2, 3), 1.5, dtype=np.float32)
    output_layer = _make_output_layer(
        float_image,
        output_color_space="Display P3",
        output_cctf_encoding=False,
    )
    controller = GuiController(viewer=object(), widgets=object())
    captured: dict[str, object] = {}
    gui_state = make_test_controller_gui_state()
    gui_state.simulation.saving_color_space = "Display P3"

    _configure_save_output(monkeypatch, controller, output_layer, gui_state, captured, filepath="output.exr")
    _capture_saved_output(monkeypatch, captured)

    controller.save_output_layer()

    assert captured["save_kwargs"]["white_luminance"] == pytest.approx(203.0)
```

- [ ] **Step 5: Run tests and verify RED**

Run:

```bash
python3 -m pytest tests/test_hdr_photo.py tests/gui/test_controller_output.py::test_save_output_layer_exr_writes_hdr_reference_white_luminance -q
```

Expected: fails because `HDRPhotoMapping`, `prepare_hdr_photo_renditions()`, and EXR `white_luminance` wiring do not exist yet.

## Task 2: Implement Python HDR Photo Mapping

**Files:**
- Modify: `src/spektrafilm/utils/hdr_photo.py`

- [ ] **Step 1: Add mapping/rendition data structures**

```python
@dataclass(frozen=True, slots=True)
class HDRPhotoMapping:
    diffuse_white: float = 1.0
    sdr_paper_white: float = 0.9
    max_headroom: float = 8.0
    shoulder_strength: float = 4.0


@dataclass(frozen=True, slots=True)
class HDRPhotoRenditions:
    sdr_rgb: np.ndarray
    hdr_rgb: np.ndarray
    headroom: float
```

- [ ] **Step 2: Add `prepare_hdr_photo_renditions()`**

Implementation requirements:

- Validate `diffuse_white > 0`.
- Normalize image by `diffuse_white`.
- Clamp negative HDR photo values to zero for the distribution target.
- Set headroom to `min(max(max_rgb, 1.0), mapping.max_headroom)`.
- Reject headroom below `MIN_HDR_PHOTO_HEADROOM`.
- Build SDR base using per-pixel max-channel intensity and a monotonic shoulder:

```python
below = intensity <= 1.0
mapped = intensity * mapping.sdr_paper_white
mapped[~below] = mapping.sdr_paper_white + (1.0 - mapping.sdr_paper_white) * (
    np.log1p(mapping.shoulder_strength * (clipped_intensity[~below] - 1.0))
    / np.log1p(mapping.shoulder_strength * (headroom - 1.0))
)
scale = mapped / np.maximum(intensity, 1e-8)
sdr = np.clip(hdr * scale[..., None], 0.0, 1.0)
```

- [ ] **Step 3: Update payload generation**

Use `_rgba_float_payload(renditions.sdr_rgb, headroom=1.0)` for the base and `_rgba_float_payload(renditions.hdr_rgb, headroom=renditions.headroom)` for the HDR rendition.

- [ ] **Step 4: Run Task 1 tests and verify GREEN**

Run:

```bash
python3 -m pytest tests/test_hdr_photo.py -q
```

Expected: HDR mapping tests pass.

## Task 3: Update Swift/CoreImage Encoder

**Files:**
- Modify: `src/spektrafilm/data/macos/hdr_heif_encoder.swift`

- [ ] **Step 1: Change CLI contract**

New usage:

```text
hdr_heif_encoder.swift <sdr-rgba-f32-raw> <hdr-rgba-f32-raw> <output.heic> <width> <height> <color-space> <headroom> <quality>
```

- [ ] **Step 2: Add color-space split**

Use encoded spaces for HEIF output:

```swift
case "sRGB": CGColorSpace(name: CGColorSpace.sRGB)
case "Display P3": CGColorSpace(name: CGColorSpace.displayP3)
case "ITU-R BT.2020": CGColorSpace(name: CGColorSpace.itur_2020)
```

Use linear spaces for float CIImage inputs:

```swift
case "sRGB": CGColorSpace(name: CGColorSpace.extendedLinearSRGB)
case "Display P3": CGColorSpace(name: CGColorSpace.extendedLinearDisplayP3)
case "ITU-R BT.2020": CGColorSpace(name: CGColorSpace.extendedLinearITUR_2020)
```

- [x] **Step 3: Build separate `sdrImage` and `hdrImage`**

Both images use `.RGBAf`; `sdrImage.settingContentHeadroom(1.0)` and `hdrImage.settingContentHeadroom(headroom)`.

- [x] **Step 4: Export using authored SDR base**

Call `context.heifRepresentation(of: sdrImage, format: .RGBA8, colorSpace: encodedColorSpace, options: [.hdrImage: hdrImage, .hdrGainMapAsRGB: true, quality])`. *(Note: Updated to use `hdrGainMapAsRGB: true` for color gain maps)*

- [ ] **Step 5: Verify Swift parses**

Run:

```bash
xcrun swift src/spektrafilm/data/macos/hdr_heif_encoder.swift
```

Expected: exits non-zero with the updated usage string, proving the script compiles far enough to parse arguments.

## Task 4: Wire EXR White Luminance

**Files:**
- Modify: `src/spektrafilm_gui/controller.py`

- [ ] **Step 1: Import the HDR reference white constant**

```python
from spektrafilm.utils.hdr_photo import HDR_REFERENCE_WHITE_LUMINANCE_NITS
```

- [ ] **Step 2: Pass metadata for EXR only**

```python
save_kwargs = {"encoding": saving_encoding}
if exr_save:
    save_kwargs["white_luminance"] = HDR_REFERENCE_WHITE_LUMINANCE_NITS
save_image_oiio(filepath, image_data, **save_kwargs)
```

- [ ] **Step 3: Run GUI output tests**

Run:

```bash
python3 -m pytest tests/gui/test_controller_output.py -q
```

Expected: passes.

## Task 5: Documentation And Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README HDR note**

Document that HDR photo export uses an authored SDR base plus HDR rendition, diffuse white is anchored at linear `1.0`, and EXR records `whiteLuminance=203`.

- [ ] **Step 2: Run targeted verification**

Run:

```bash
python3 -m pytest tests/test_hdr_photo.py tests/test_image_io_color_metadata.py tests/gui/test_controller_output.py tests/test_color_management.py tests/gui/test_params_mapper.py -q
python3 -m compileall -q src/spektrafilm src/spektrafilm_gui tests
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 3: Self-audit before completion**

Check:

- Does HEIC have separate SDR and HDR inputs?
- Does HDR runtime stay scene-linear?
- Is diffuse/paper white explicit?
- Is headroom bounded?
- Are EXR and HEIC paths separate?
- Are pre-existing GPU/color-management changes preserved?
