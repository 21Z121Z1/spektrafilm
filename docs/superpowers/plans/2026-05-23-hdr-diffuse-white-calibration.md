# HDR Diffuse White Calibration Proposal

## Purpose

This document proposes how spektrafilm should establish a diffuse-white anchor for HDR still export.

The immediate problem is that the current HDR export path treats linear RGB values around `1.0` as if they already represent diffuse/reference white plus usable HDR headroom. That is not true for RAW imports. `rawpy` with `gamma=(1, 1)` and `no_auto_bright=True` produces linear RGB, but its numeric scale is still tied to LibRaw/camera white-level normalization, not to a scene-referred diffuse-white convention.

For the tested DNG:

- raw sensor normalized max is about `0.912` before demosaic/color conversion;
- rawpy linear output reaches the rendered ceiling, with max about `1.0` to `1.004` depending on white balance and output-space conversion;
- any tiny overshoot above `1.0` is not meaningful HDR headroom;
- the film/print/scan path then maps highlights into paper/reflectance white, so the final output remains below `1.0`.

Therefore, correct HDR export needs an explicit mapping:

```text
rawpy linear RGB value -> scene-relative exposure -> diffuse white = 1.0 -> HDR headroom above 1.0
```

## Definitions

### Sensor White

The value corresponding to camera sensor saturation or LibRaw/rawpy white-level normalization.

This is not diffuse white. It is closer to the maximum measurable signal before clipping.

### Diffuse White / Paper White / Reference White

The value assigned to a matte 100% diffuse reflector under scene illumination. For the HDR export transform, this becomes linear `1.0`.

Everything above this value is HDR headroom reserved for speculars, emissive light sources, glints, practical lamps, and other scene values brighter than a diffuse surface.

### Scene Energy

The scene-linear luminance or RGB energy we use to determine HDR highlight strength. It should come from input RAW/linear data before the film/print paper path compresses it into a display or reflectance rendition.

### Look RGB

The current film/print/scan output. This carries the spektrafilm color, tone, density, paper, glare, and scanner look. In print mode it is usually a reflectance-style image and should not be expected to contain values above `1.0`.

## Why `rawpy` Linear Is Not Enough

The RAW loader currently asks rawpy for:

```python
gamma=(1, 1)
no_auto_bright=True
output_bps=16
output_color=rawpy.ColorSpace.ACES
```

This is linear-light output, which is good. But the scale is still bounded by raw white-level normalization. It answers:

```text
"How close is this pixel to camera/rawpy output white?"
```

It does not answer:

```text
"How many stops above diffuse white is this scene point?"
```

A correctly exposed RAW can place diffuse white far below sensor saturation. For example:

```text
18% gray     -> 0.10 rawpy value
diffuse white -> 0.55 rawpy value
sensor white  -> 1.00 rawpy value
headroom      -> 1.00 / 0.55 = 1.8x, about 0.85 stops
```

A darker exposure might instead have:

```text
18% gray     -> 0.04
diffuse white -> 0.22
sensor white  -> 1.00
headroom      -> 4.5x, about 2.2 stops
```

Both images are linear, but the diffuse-white anchor is different. Without estimating or specifying it, we cannot author HDR responsibly.

## Tested Apple DNG Metadata Findings

The tested file:

```text
/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片/IDG_20260411_152822_608.DNG
```

is not a plain camera RAW. It is an Apple DNG with embedded Adobe/Apple HDR rendering metadata.

Important parsed tags:

```text
Make / Model: Apple / iPad mini (A17 Pro)
DNGVersion: 1.7.0.0
BlackLevel: 2112
WhiteLevel: 32767
LinearResponseLimit: 1
AsShotNeutral: 0.710002 1 0.38489
BaselineExposure: -0.68
ProfileName: Bonsai Embedded Color Profile SDR
ProfileName: Bonsai Embedded Color Profile HDR
Exposure2012: +1.60
HDREditMode: 1
HDRMaxValue: +2.30
ToneCurveName2012: Linear
```

The sensor-domain normalization implied by standard DNG tags is:

```text
raw_normalized = (raw - 2112) / (32767 - 2112)
sensor white = 1.0
```

For this image, measured values are:

```text
raw sensor normalized max: 0.912
raw sensor normalized p99.9: 0.860
rawpy ACES linear luminance max: 1.000
rawpy ACES linear luminance p99.9: 0.952
pixels with any rawpy RGB channel >= 0.999: about 0.69%
```

This confirms that DNG `WhiteLevel` gives sensor/reference white, not scene diffuse white. The image is close to rawpy's rendered ceiling, but the sensor data itself does not hit the DNG white level.

The HDR metadata is still useful. `HDRMaxValue=+2.30` appears to describe Adobe Camera Raw HDR output headroom:

```text
2 ** 2.30 = 4.92x SDR/reference white
```

If we assumed rawpy max `~1.0` should become that HDR peak, the implied diffuse-white anchor would be:

```text
diffuse_white_rawpy ~= 1.0 / 4.92 = 0.20
```

But if we also include the Adobe rendering exposure tags:

```text
Exposure2012 + BaselineExposure = +1.60 - 0.68 = +0.92 EV
2 ** 0.92 = 1.89x
```

then the implied anchor moves to roughly:

```text
diffuse_white_rawpy ~= 1.0 * 1.89 / 4.92 = 0.39
```

The two plausible interpretations differ by nearly one stop. That is the key result: even rich DNG metadata does not expose a single unambiguous `diffuse_white_raw` value. It exposes sensor limits, color conversion metadata, and an HDR rendering intent.

Implementation consequence:

- DNG metadata can seed a `metadata-authored HDR` mode.
- It can read `HDRMaxValue`, embedded HDR profile information, and Adobe exposure settings as rendering hints.
- It cannot replace a physical scene reference if the user wants true diffuse-white calibration.
- A later Adobe/Apple DNG mode may reverse-engineer a more precise middle-gray anchor from `BaselineExposure`, `AsShotNeutral`, embedded DNG profiles, gain tables, and ACR HDR tags. That should be treated as compatibility with Adobe/Apple rendering intent, not as a universal physical calibration.

## Calibration Inputs

There is no single perfect automatic method. We should support several modes with different reliability.

### 1. User-Picked Diffuse White

User selects a known matte white or bright neutral surface in the image.

Recommended anchor:

```text
diffuse_white_raw = robust percentile of selected patch luminance
```

Use a luminance measure in the input/export RGB space:

```python
Y = RGB_to_XYZ(linear_rgb, input_space).Y
diffuse_white_raw = percentile(Y_patch, 90 or 95)
```

Pros:

- most accurate when a white card, paper, wall, or known diffuse highlight exists;
- avoids confusing lamps/speculars with diffuse white;
- easy to explain to photographers.

Cons:

- requires UI work;
- user can pick a specular or clipped area accidentally.

Validation:

- selected patch must have finite positive values;
- reject if too many pixels are near sensor saturation;
- warn if patch is highly chromatic, because a colored object is not a neutral diffuse-white anchor.

### 2. User-Picked 18% Gray

User selects a known gray card or neutral midtone.

Formula:

```text
diffuse_white_raw = gray_raw / 0.184
```

If we want a more photographic white margin, we can expose a setting:

```text
diffuse_white_raw = gray_raw * 2 ** diffuse_white_over_middle_gray_ev
```

With `diffuse_white_over_middle_gray_ev = log2(1 / 0.184) = 2.44 EV`, this is equivalent to assigning 18% gray to linear `0.184` and diffuse white to `1.0`.

Pros:

- robust if a gray card exists;
- connects naturally to exposure and film calibration.

Cons:

- gray card not always present;
- midgray in a creative scene may not be obvious.

### 3. Auto Diffuse White From Image Statistics

Estimate diffuse white from highlights while excluding likely speculars/clipped pixels.

Possible algorithm:

```python
Y = scene_luminance(input_linear_rgb)
valid = finite(Y) and Y > 0
highlight = upper percentile range, e.g. 95th to 99.5th percentile
candidate = percentile(Y[valid], p)
diffuse_white_raw = candidate / diffuse_white_scene_percentile_target
```

Simpler first version:

```text
diffuse_white_raw = percentile(Y, 99.0)
```

Then after normalization:

```text
scene_hdr = input_linear_rgb / diffuse_white_raw
```

Pros:

- no user interaction;
- likely better than treating rawpy `1.0` as diffuse white.

Cons:

- can mistake practical lamps/speculars for diffuse white;
- can fail on low-key/night scenes with no white objects;
- can fail on high-key images where much of the frame is white;
- image percentile is an aesthetic exposure decision, not a physical measurement.

Mitigations:

- cap `diffuse_white_raw` to a range relative to sensor white, e.g. `[0.05, 0.95]`;
- use a safer default floor such as `0.10` sensor-relative for auto mode until better exposure metadata is available;
- compare `p99` against the image median and mark low-key scenes as low-confidence when both are very low;
- avoid mapping a very dark `p99` directly to diffuse white in night scenes because that turns preserved darkness into forced HDR brightness and amplifies noise;
- allow exposure compensation in EV;
- use chroma/saturation filters to prefer neutral highlights;
- use a "highlight weighted" but not "single hot pixel" estimator;
- expose the inferred headroom to the user.

Low-key fallback:

```python
p99 = percentile(Y[valid], 99.0)
median = percentile(Y[valid], 50.0)

if p99 < min_auto_diffuse_white_raw and median < low_key_median_threshold:
    diffuse_white_raw = min_auto_diffuse_white_raw
    confidence = "low"
    method = "auto_floor_low_key"
else:
    diffuse_white_raw = clamp(p99, min_auto_diffuse_white_raw, max_auto_diffuse_white_raw)
```

The purpose of the floor is not to make the result more physically accurate. It prevents the auto estimator from destroying the exposure intent of dark scenes. The UI should show that this is an estimate and should encourage a gray/white patch pick when accuracy matters.

### 4. Exposure-Metadata Based Estimate

Use camera exposure metadata, ISO, aperture, shutter, and a calibration constant to infer scene luminance.

Pros:

- in principle physically meaningful;
- could work well with calibrated cameras.

Cons:

- requires camera response/calibration;
- ISO/exposure metadata is not enough by itself to know scene diffuse white;
- rawpy normalization and camera matrices complicate the absolute scale;
- not suitable as first implementation.

Recommendation: defer this.

## Recommended Product Model

Add a new concept:

```python
HDRDiffuseWhitePolicy
```

Fields:

```python
mode: "auto" | "white_patch" | "gray_patch" | "manual"
manual_diffuse_white_raw: float | None
gray_reflectance: float = 0.184
auto_percentile: float = 99.0
exposure_compensation_ev: float = 0.0
min_diffuse_white_raw: float = 1e-4
min_auto_diffuse_white_raw: float = 0.10
max_diffuse_white_raw: float = 1.0
low_key_median_threshold: float = 0.03
max_headroom: float = 8.0
```

The result should be:

```python
HDRDiffuseWhiteCalibration(
    diffuse_white_raw: float,
    input_color_space: str,
    method: str,
    headroom: float,
    diagnostics: dict,
)
```

Normalization:

```python
scene_hdr_rgb = input_linear_rgb / diffuse_white_raw
scene_hdr_rgb *= 2 ** exposure_compensation_ev
```

Then:

```text
diffuse white -> 1.0
specular/practical highlights -> >1.0
sensor/raw saturation -> approximately 1 / diffuse_white_raw
```

Headroom policy:

```python
headroom = min(max(percentile(scene_hdr_rgb, 99.99), 1.0), max_headroom)
```

Do not let one hot pixel set headroom.

## Correct Signal Model For Film Simulation

Do not expect the `film -> print paper -> scan print` output to be HDR by itself. In print mode the output is fundamentally paper/print reflectance. A real lamp, specular, or sun glint can expose the negative much more strongly, but after printing and scanning it can still become paper white.

The implementation should therefore split the data into two signals:

1. `look_rgb`
   - the current output layer float data;
   - carries the film/print/scan appearance;
   - controls color, density, contrast, paper response, glare, scanner behavior, and overall appearance;
   - can remain in the `0..1` paper/reflectance range.

2. `scene_energy`
   - derived from RAW/input linear data using diffuse-white calibration;
   - represents scene/highlight energy before the paper-white bottleneck;
   - can be RGB or luminance-only;
   - can exceed diffuse white after normalization;
   - may optionally receive a controlled highlight expansion pass.

HDR export combines these two signals. The SDR fallback comes from `look_rgb`; HDR headroom comes from `scene_energy`.

### Luminance Graft

For a luminance sidecar:

```python
hdr_luma = scene_energy / diffuse_white
look_luma = luminance(look_rgb)
hdr_rgb = look_rgb * hdr_luma[..., None] / max(look_luma[..., None], eps)
```

For an RGB scene sidecar:

```python
look_y = luminance(look_rgb)
scene_y = luminance(scene_hdr_rgb)
hdr_luma = tone_or_scale(scene_y)
hdr_rgb = look_rgb * hdr_luma[..., None] / max(look_y[..., None], eps)
```

This preserves film hue/chroma relationships from `look_rgb` while restoring HDR luminance headroom from the calibrated scene signal.

After grafting, apply a project headroom policy:

```python
hdr_rgb = compress_or_clip_to_headroom(hdr_rgb, max_headroom)
```

where `max_headroom` should be user-visible, for example `4x`, `8x`, or `16x`.

Recommended safeguards:

- only graft above a soft threshold near diffuse white;
- leave shadows/midtones mostly controlled by `look_rgb`;
- use a smooth blend so the result does not look pasted-on;
- avoid hue explosions when `look_luma` is nearly zero;
- estimate advertised HEIC headroom from robust percentiles, not one hot pixel.

Example blend:

```python
w = smoothstep(0.75, 1.25, scene_y)
hdr_y = (1 - w) * look_y + w * scene_y
hdr_rgb = look_rgb * hdr_y[..., None] / max(look_y[..., None], eps)
```

For extremely bright sources, apply a shoulder:

```python
hdr_y = compress_to_headroom(hdr_y, max_headroom)
```

This should be the HDR rendition passed to HEIC/HEIF and optionally EXR HDR photo export.

### Gamut Management And Highlight Desaturation

The luminance graft can create wide-gamut HDR excursions. `look_rgb` may contain filmic high-light color, halation warmth, or scanner/paper coloration. Multiplying that chroma by `4x`, `8x`, or `16x` can push the result outside Display P3 or Rec.2020 delivery gamut and produce harsh clipping on HDR displays.

Do not treat "all bright lights become white" as a physical law. Sodium lamps, LEDs, neon, lasers, screens, and colored speculars can stay chromatic. The correct rule is more practical:

```text
preserve the film look where possible,
but compress impossible output-gamut excursions smoothly,
and provide a path to white for extreme neutral/specular highlights.
```

Recommended output step:

```python
hdr_rgb = luminance_graft(look_rgb, scene_energy)
hdr_rgb = compress_to_headroom(hdr_rgb, max_headroom)
hdr_rgb = compress_gamut_with_highlight_desaturation(
    hdr_rgb,
    working_space="ACEScg",
    output_space="Display P3",
    desaturation_start=1.0,
    desaturation_end=max_headroom,
)
```

Implementation notes:

- apply desaturation in a luminance/chroma representation, not by independently clipping RGB channels;
- use a smooth curve above diffuse white so there is no visible color break at `1.0`;
- make desaturation strength configurable because colored light sources should not always become white;
- run gamut compression after headroom compression and before final HEIC/EXR delivery encoding;
- keep the SDR base from `look_rgb` unchanged so SDR fallback retains the intended film appearance.

## Relationship To Existing Diffusion Highlight Boost

The existing `boost_highlights()` function is the closest internal precedent for this design.

In the diffusion/halation path, it works in raw exposure units:

```text
protect subject values below midgray * 2 ** protect_ev
increase energy in the highlight region with a controlled curve
send the boosted energy into halation/scatter
```

It is scale-invariant if `midgray` is scaled with the raw domain. Tests already verify this property.

Conceptually, this models a real photographic fact: the energy that creates halation or scatter can be stronger than the clipped or paper-limited image later shown to the viewer. The high-light energy exists before the display/print bottleneck.

This is useful for HDR export because it shows a stable pattern:

- define a reference exposure point;
- protect midtones;
- expand high values with a controlled authoring curve;
- never pretend the boost recovers measured data.

That is almost exactly the HDR export problem. We should not search the final print scan for values above `1.0`. Instead, we should maintain or reconstruct a `scene_energy` sidecar from input/raw exposure, then use that sidecar to drive HDR luminance.

`boost_highlights()` should not be the only source of HDR information. It is an optional policy after diffuse-white normalization:

```python
scene_hdr_rgb = boost_highlights(
    scene_hdr_rgb,
    boost_ev=hdr_highlight_boost_ev,
    boost_range=hdr_highlight_boost_range,
    protect_ev=hdr_protect_ev,
    midgray=0.184,
)
```

This is an authoring control for practical lights and bloom, not a physical RAW recovery.

Recommended default:

- measured/estimated input energy creates the base `scene_energy`;
- highlight boost defaults to zero;
- when enabled, boost is clearly labeled as authored HDR headroom;
- midtones stay locked to the calibrated diffuse-white/middle-gray scale.

## Recommended Architecture

The new HDR export architecture should be:

```text
RAW/input linear data
  -> diffuse-white anchor
  -> scene_energy sidecar
  -> optional authored highlight boost
  -> max headroom policy

film/print/scan simulation
  -> look_rgb

HDR export
  -> SDR base from look_rgb
  -> HDR rendition from luminance graft(scene_energy, look_rgb)
  -> HEIC gain map or HDR EXR rendition
```

This separates responsibilities cleanly:

- `look_rgb` owns the spektrafilm look.
- `scene_energy` owns HDR brightness/headroom.
- diffuse-white calibration owns the mapping between RAW numbers and scene-relative exposure.
- headroom policy owns final delivery limits.

This also makes the current failure understandable: the HEIC encoder rejects the image because `look_rgb <= 1.0`; that is correct behavior for a paper-limited output. The fix is not to force print output above `1.0`, but to provide a real HDR sidecar at export time.

### Gain Map Export Fit

This architecture is naturally aligned with gain-map HDR still images.

The export package should contain:

1. SDR base:
   - derived directly from `look_rgb`;
   - tone mapped to a normal SDR image;
   - used by non-HDR viewers;
   - preserves the paper-limited spektrafilm appearance.

2. HDR rendition or gain signal:
   - derived from `scene_energy` grafted onto `look_rgb`;
   - carries highlight headroom;
   - bounded by project `max_headroom`;
   - gamut-managed for the target delivery space.

Conceptually, a luminance gain map is:

```python
gain = hdr_luma / max(sdr_luma, eps)
log_gain = log2(gain)
```

The current macOS CoreImage path can provide separate SDR and HDR images and let the platform encoder generate the HEIC gain map. Longer term, an explicit ISO 21496-1-compatible gain-map writer could compute and store the gain map directly. The important design point is that the SDR base and HDR rendition are separate authored images; the SDR base must not be produced by clamping HDR pixels.

## Proposed Implementation Phases

### Phase 1: Make The Problem Visible

Add diagnostics to the output layer metadata:

```python
input_linear_min
input_linear_max
input_linear_p99
input_linear_p999
output_float_min
output_float_max
output_float_p99
hdr_diffuse_white_raw
hdr_headroom_estimate
```

GUI status after scan could include:

```text
Scan completed. Output max 0.81, estimated HDR headroom 1.7x from input.
```

This prevents silent fake HDR.

### Phase 2: Auto Diffuse White Calibration

Implement an initial automatic estimator:

```python
Y = luminance(input_linear_rgb)
p99 = percentile(Y, 99.0)
median = percentile(Y, 50.0)
diffuse_white_raw = robust_auto_anchor(p99, median, min_auto_diffuse_white_raw)
```

Store the resulting `scene_hdr_rgb` or at least its luminance in output metadata.

Use this only for HDR export. Do not change the core film/print simulation. If the estimator hits the low-key floor, record `confidence="low"` and show that in diagnostics.

### Phase 3: HDR Export Luminance Graft

At export time:

- EXR archive mode can continue saving current `look_rgb` as linear reflectance/output;
- HDR photo mode builds:
  - SDR base from `look_rgb`;
  - HDR rendition from `look_rgb` plus `scene_hdr` luminance graft;
  - highlight desaturation/gamut compression for the delivery color space;
  - gain map from those two renditions.

> **Update 2026-05-25**: This phase has been completed and enhanced. The simple luminance graft was replaced with a Dual-Layer HDR Mapping (Diffuse Lift + Specular Rolloff) to prevent SDR contrast from being destroyed by HDR scaling. The SDR base and HDR rendition are now explicitly separated before being sent to the CoreImage encoder. Furthermore, the Swift encoder was updated to use `hdrGainMapAsRGB=true`, generating color (RGB) gain maps instead of luma-only.

This keeps SDR fallback faithful to spektrafilm and lets HDR carry actual highlight headroom.

### Phase 4: User Controls

Add GUI controls:

```text
HDR white anchor:
  Auto
  Pick diffuse white
  Pick 18% gray
  Manual value

HDR max headroom:
  2x / 4x / 8x / 16x

HDR highlight boost:
  EV amount
  protect EV

HDR gamut handling:
  Highlight desaturation strength
  Target delivery gamut
```

> **Update 2026-05-25**: A dedicated "HDR Export Settings" GUI panel has been added. It controls `hdr_diffuse_lift_strength`, `graft_strength`, `paper_rolloff_exposure_scale`, `paper_rolloff_k`, and `max_headroom`.

Expose diagnostics:

```text
Diffuse white raw: 0.47
Estimated headroom: 2.1x
HDR output max: 4.0x
```

### Phase 5: Physical/Camera Calibration

Longer term:

- support per-camera calibration;
- read DNG calibration metadata more carefully;
- add a DNG rendering-intent mode for Apple/Adobe DNGs with HDR profile metadata;
- attempt an Adobe-compatible middle-gray anchor only when the required DNG/XMP/profile tags are present and diagnostics can prove the interpretation;
- use exposure metadata to improve defaults;
- allow saved calibration presets for a camera body.

## Open Questions

1. Should `.exr` default to current linear film/print output or to the new HDR rendition?

   Recommendation:
   - `.exr` from normal Save should probably remain "current output archive";
   - add explicit "HDR photo EXR" or use `.heic/.heif` for HDR rendition.

2. Should HDR export use input RAW directly or film-stage raw exposure?

   Input RAW is simpler and more stable.
   Film-stage raw exposure includes camera diffusion/halation pre-processing but is more internal and stock-dependent.

   Recommendation:
   - first use input linear RGB for `scene_hdr`;
   - later experiment with film raw exposure sidecar for more physically integrated halation.

3. What default auto percentile?

   Reasonable first choices:
   - `99.0` for general scenes;
   - `99.5` for preserving more brightness;
   - avoid `100` because it lets one clipped or noisy pixel dominate.

   Guardrail:
   - never let percentile alone map an extremely dark scene to diffuse white;
   - use a sensor-relative floor and median/low-key diagnostics;
   - when confidence is low, prefer saving SDR or requiring a manual gray/white anchor.

4. What should happen when estimated headroom is <= 1?

   Options:
   - reject HEIC HDR export, as today;
   - allow authoring boost to create HDR;
   - save SDR HEIC/JPEG instead.

   Recommendation:
   - reject by default;
   - allow explicit "HDR highlight boost" to create authored HDR if the user wants.

## Recommended Next Step

Implement Phase 1 and Phase 2 together:

- compute diffuse-white estimate from the input linear image;
- store diagnostics and scene HDR luminance in output layer metadata;
- do not change film/print rendering yet;
- update HEIC export to use scene HDR luminance graft instead of relying on `look_rgb.max() > 1`.

This will turn the current failure mode from:

```text
HEIC export refuses because look_rgb <= 1
```

into:

```text
HEIC export uses calibrated scene headroom even when the print look is paper-white limited.
```

## Web Research Addendum

Sources checked:

- OpenEXR scene-linear documentation: https://openexr.com/en/latest/SceneLinear.html
- Adobe DNG 1.7.1.0 Specification: https://helpx.adobe.com/content/dam/help/en/camera-raw/digital-negative/jcr_content/root/content/flex/items/position/position-par/download_section_733958301/download-1/DNG_Spec_1_7_1_0.pdf
- Adobe gain map documentation: https://helpx.adobe.com/camera-raw/using/gain-map.html
- Adobe HDR output documentation: https://helpx.adobe.com/camera-raw/using/hdr-output.html
- ISO 21496-1 standard page: https://www.iso.org/standard/86775.html
- Android Ultra HDR image format documentation: https://developer.android.com/media/platform/hdr-image-format
- rawpy parameters documentation: https://letmaik.github.io/rawpy/api/rawpy.Params.html
- LibRaw maintainer notes on `no_auto_bright` / `no_auto_scale`: https://www.libraw.org/node/2325 and https://www.libraw.org/comment/5682
- darktable scene-referred pipeline documentation: https://docs.darktable.org/usermanual/3.8/en/special-topics/color-pipeline/
- darktable filmic RGB documentation: https://darktable-org.github.io/dtdocs/en/module-reference/processing-modules/filmic-rgb/

### Findings

OpenEXR documentation gives the useful target convention: scene-referred linear data should be proportional to scene light, and a correctly exposed 18% gray card is commonly represented as `0.18`. OpenEXR also emphasizes that `1.0` is not a clamp limit; it roughly represents a 100% reflector, with brighter values available for fire, highlights, and lights.

rawpy exposes `no_auto_bright`, `no_auto_scale`, `bright`, `exp_shift`, `highlight_mode`, and related rendering controls. This confirms that `gamma=(1, 1)` and `no_auto_bright=True` are not by themselves a full scene-linear calibration. They produce linear output, but the numeric scale still depends on raw conversion scaling choices and sensor white normalization unless we take control of scale.

DNG metadata has rendering-oriented exposure tags such as `BaselineExposure` and `BaselineExposureOffset`, both expressed in EV units for rendering. The DNG processing model maps raw values to "linear reference values" where zero light is `0.0` and the maximum useful value limited by sensor saturation or ADC clipping is `1.0`. That confirms the crucial distinction: raw/DNG `1.0` is sensor/reference saturation, not a measured diffuse-white anchor.

The DNG spec also makes camera calibration explicit: color conversion uses camera calibration matrices and can vary across calibration illuminants, profiles, and dynamic range profiles. This is exactly the metadata/calibration family the product cannot require for arbitrary camera RAW support.

ACES/linear-workflow discussions reinforce the same practical rule: `0.18` is the stable reference; `1.0` is approximately diffuse white, not display white; and if the capture camera/setup is unknown, determining "white" becomes harder and often requires a reference or assumption.

darktable's scene-referred documentation reaches the same product conclusion from a user-interface angle: scene-referred pipelines lose fixed white, middle-gray, and black values, so those anchors must be set according to the scene and shooting conditions. Its filmic documentation uses pickers for middle gray and white, but explicitly treats those as assumptions about sampled regions and warns that automatic white/black detection can fail when no true white/black exists in the scene.

Adobe's gain map documentation describes the gain map as a quotient between HDR and SDR renditions. This directly supports the product architecture of an SDR `look_rgb` base plus an HDR `scene_energy`-driven rendition. ISO 21496-1 and Android Ultra HDR documentation confirm that gain-map HDR images are a standard delivery path, not just an Apple-specific trick.

### Consequence

For arbitrary RAW files from arbitrary cameras, there is no fully automatic, physically accurate diffuse-white solution from image data alone. A RAW pixel value is proportional to:

```text
scene radiance * exposure time * aperture transmission * ISO/gain path * sensor spectral response * raw-converter scale
```

Without knowing a scene reference, all of these can be multiplied by a constant and produce the same image ratios. So diffuse white is not observable as an absolute fact from one arbitrary image.

### The Camera-Agnostic Constraint

The user requirement is stricter than a typical raw converter:

```text
accept arbitrary camera RAW
do not require per-camera metadata calibration
do not require camera-specific profiles
still produce HDR that is honestly anchored to diffuse white
```

Under that constraint, the honest answer is:

```text
fully accurate automatic diffuse-white calibration is impossible from the image alone.
```

Reason:

```text
raw_linear = unknown_scale * scene_radiance
```

The unknown scale includes exposure time, aperture transmission, sensor gain, raw converter scaling, white balance gains, and camera spectral response. If every RAW value is multiplied by `k`, the image ratios and visual content are unchanged, but the diffuse-white value moves by `k`. A single arbitrary image cannot distinguish:

```text
matte white under dim light
gray object under bright light
specular highlight
lamp or emissive source
near-sensor saturation
```

Those cases can produce overlapping RAW values. The histogram can suggest a useful exposure anchor, but it cannot prove which pixels represent scene diffuse white.

### Camera-Agnostic Implementation Strategy

The product should therefore separate "calibration" from "estimation":

1. Accurate camera-agnostic mode:
   - user samples a known 18% gray card, white card, paper, neutral wall, or other diffuse reference;
   - spektrafilm computes the scale from the loaded image itself;
   - no camera database is needed;
   - this is the only mode we should call "calibrated".

2. Automatic camera-agnostic mode:
   - estimate an anchor from upper-percentile luminance after excluding clipped pixels, tiny hot pixels, and highly chromatic/specular-looking samples;
   - show diagnostics such as estimated diffuse-white raw value, headroom, clipped-pixel fraction, neutral-highlight fraction, and confidence;
   - label it "auto estimate", not "accurate calibration".

3. Authored HDR mode:
   - start from the calibrated or estimated anchor;
   - optionally expand values above diffuse white with a controlled highlight boost inspired by existing diffusion highlight handling;
   - label this as creative HDR authoring, not recovered scene measurement.

This preserves the important promise:

```text
spektrafilm can accept any camera RAW without per-camera calibration,
but it cannot infer physical diffuse white exactly unless the user gives it a scene reference.
```

### Implementable Accuracy Tiers

1. Accurate and camera-independent:
   - user picks 18% gray or a diffuse white patch;
   - spektrafilm derives the scale from the loaded linear image itself;
   - no camera database is needed.

2. Reasonable automatic default:
   - estimate a neutral, non-clipped upper percentile as diffuse white;
   - expose confidence/diagnostics;
   - call it "auto white anchor", not "calibration".

3. Artistic HDR authoring:
   - use a controllable highlight boost curve above the calibrated or estimated anchor;
   - explicitly label it as authored headroom, not recovered RAW data.

### Recommended Decision

The first robust spektrafilm implementation should make "pick gray / pick diffuse white" the accurate mode and use auto percentile only as a default convenience. This keeps the system camera-agnostic while avoiding the false promise that arbitrary RAW input contains enough information to infer diffuse white exactly.
