# DNG Natural HDR Luminance Research

Date: 2026-06-04

Scope: DNG/RAW Natural HDR Film Simulation brightness semantics for the current `develop` checkout. This pass adds a research estimator and tests, but does not change production HDR rendering or GUI behavior.

## 1. Executive Summary

Spektrafilm cannot know physical diffuse white from an ordinary user DNG by reading `WhiteLevel`, display metadata, paper/profile data, or user target EV. `WhiteLevel` is a sensor/ADC saturation reference for RAW normalization and clipping diagnostics. Natural HDR can only be claimed when scene-linear data contains traceable values above a measured or defensibly estimated diffuse-white anchor, and when authored controls are not creating that headroom.

This pass adds `tools/research_dng_diffuse_white_estimation.py` and `tests/test_dng_diffuse_white_estimation.py`. The research tool defines RAW diagnostics, scene luminance, diffuse-white estimate, and Natural HDR provenance dataclasses; it runs synthetic fixtures and bounded real-DNG scans; and it emits JSON/CSV diagnostics. Synthetic tests prove these guardrails:

- measured white-card/gray-card regions can support `natural_scene_hdr_verified`;
- low-key photos do not get a low percentile promoted into huge fake headroom;
- snow/white-wall scenes keep large neutral diffuse candidates instead of treating all bright area as specular;
- tiny saturated neon/light-source highlights are not treated as diffuse white;
- clipped RAW highlights downgrade or refuse Natural HDR;
- active authored controls force `authored_hdr_from_raw`;
- `WhiteLevel` is recorded as sensor saturation metadata, not diffuse white.

## 2. Deep Research To DNG Rules

The supplied `/Users/retriedstormtrooper/Downloads/deep-research-report.md` resolves the key semantic boundary: Natural HDR Film Simulation must start from scene-referred or traceable film/scan energy and produce SDR/HDR output transforms from one shared Scene-Film Master State. It also says gain maps are compatibility packaging, not evidence of HDR origin.

The DNG-specific rules are:

- RAW sensor data must first be black-subtracted and normalized with DNG/LibRaw black and white-level metadata.
- Scene luminance must be computed from scene-linear RGB or a stronger scene representation, not gamma-encoded display RGB.
- Diffuse white must be measured, calibrated, or estimated separately from `WhiteLevel`.
- Values above normalized diffuse white are headroom candidates only when they are not clipped beyond recovery and not created by authored controls.
- SDR/HDR outputs must branch after the scene/film state. A gain map may encode the pair but may not define the pair.

## 3. DNG/RAW Brightness Terms

| Term | Meaning | Natural HDR use |
| --- | --- | --- |
| raw code value | DNG sensor sample before full interpretation. | Input to black/white normalization only. |
| sensor-normalized raw | `(raw - BlackLevel) / (WhiteLevel - BlackLevel)`. | Clipping and dynamic-range diagnostics; not diffuse white. |
| camera-linear RGB | Demosaiced, white-balanced, camera matrix converted linear RGB. | Scene-referred estimate if provenance is recorded. |
| scene-linear working RGB | Spektrafilm working light values, such as ACES/linear RGB. | Correct source for scene luminance and film exposure. |
| scene luminance Y | Linear luminance from known primaries/coefficients. | Basis for diffuse-white anchor and headroom. |
| diffuse white | Ordinary scene white under the capture illumination/exposure. | Recommended normalization point `Y=1.0`. |
| sensor saturation white | Sensor/ADC saturation boundary, represented by DNG `WhiteLevel`. | Clipping boundary only. |
| display reference white | Output transform reference, such as HDR reference white. | Display mapping only. |
| paper white | Print/output substrate white. | Print route/output reference only. |
| headroom | `scene_y / diffuse_white` above `1.0`, when traceable. | Natural HDR candidate range. |

## 4. Strict White Separation

`WhiteLevel`, sensor saturation, diffuse white, display white, and paper white are separate variables:

- `WhiteLevel` belongs to capture normalization and clipping diagnostics.
- sensor saturation says where RAW values stop carrying information.
- diffuse white anchors scene interpretation and exposure semantics.
- display reference white maps diffuse white into an output family.
- paper white is part of print/output viewing, not scene truth.

The new estimator records `WhiteLevel` in `raw_metadata_summary` and explicitly adds the assumption that `WhiteLevel` remains sensor saturation metadata. The unit test `test_whitelevel_is_recorded_as_sensor_saturation_not_diffuse_white()` asserts that a `white_level=4095` diagnostic does not become the diffuse-white estimate.

## 5. No-Chart Diffuse White Estimation

The implemented estimator is intentionally layered rather than a single percentile:

1. `measured_gray_or_white_card`: uses an explicit mask or user-confirmed measured region. This is the only path that can produce `natural_scene_hdr_verified`.
2. `user_assisted_white_anchor`: uses a user override. It remains low confidence unless the user marks it as a measured chart/white/gray region.
3. `neutral_high_key_statistics`: handles large neutral bright regions such as snow, fog, white walls, and cyc walls.
4. `low_key_conservative_statistics`: protects dark scenes from using a tiny low percentile as diffuse white and fabricating huge headroom.
5. `semantic_highlight_guarded_statistics`: detects small saturated colored highlights as likely emissive/specular candidates, not diffuse white.
6. `highlight_guarded_statistics`: handles small intense highlight distributions without promoting them to diffuse white.

This is still a research heuristic. It outputs confidence, warnings, and downgrade classes rather than claiming measurement where no measurement exists.

## 6. Confidence System

| Confidence | Meaning | Natural HDR eligibility |
| --- | --- | --- |
| high | Measured or user-confirmed calibration anchor, finite, positive, not materially clipped. | Can claim `natural_scene_hdr_verified` when headroom exists and authored controls are inactive. |
| medium | Stable image/statistical estimate with RAW evidence and no severe clipping. | Can claim `natural_scene_hdr_estimated`; UI must label estimated, not measured. |
| low | Low-key, small emissive highlights, near clipping, or unstable anchor. | Downgrade to `scene_derived_heuristic_hdr` if headroom exists. |
| invalid | Non-finite estimate, severe clipping, no reliable headroom, or SDR-only source. | Refuse Natural HDR; use `sdr_only` or authored mode. |

## 7. Natural HDR Eligibility Classes

The estimator emits both `recommended_mode` and `natural_hdr_class`:

- `natural_scene_hdr_verified`: measured diffuse white, RAW/scene evidence, no authored headroom controls.
- `natural_scene_hdr_estimated`: medium-confidence estimate, RAW/scene evidence, no authored controls.
- `scene_derived_heuristic_hdr`: scene data contains possible headroom, but diffuse-white confidence is low.
- `authored_hdr_from_raw`: profile target EV, budget recovery, path-to-white, source/bounded chroma, manual headroom, or equivalent controls are active.
- `sdr_only_or_unrecoverable`: no reliable headroom, severe clipping, invalid estimate, or SDR-only source.

## 8. DNG To Scene-Film Master State

Recommended production data flow:

```text
DNG input
-> read RAW metadata
-> black subtraction / WhiteLevel normalization
-> clipping diagnostics
-> demosaic
-> white balance
-> camera-to-scene working RGB
-> scene-linear RGB
-> scene luminance Y with recorded coefficients
-> diffuse white estimate/provenance
-> normalize scene by diffuse white
-> SceneReferredRawState
-> film exposure / log-exposure domain
-> film density / dye / stock response
-> Scene-Film Master State
-> SDR Output Transform
-> HDR Output Transform
-> optional gain-map export of the finished SDR/HDR pair
```

`WhiteLevel` appears only before scene RGB as a sensor-normalization and clipping input. Display reference white, 203 nits, paper white, and gain-map metadata appear only after the master state as output or packaging concepts.

## 9. Current Code Audit

| File / function | Current input/source | Scene luminance source | Diffuse white source | Risk | Recommended direction |
| --- | --- | --- | --- | --- | --- |
| `src/spektrafilm/utils/raw_file_processor.py::load_and_process_raw_file()` | RAW via `rawpy.postprocess()` into linear ACES RGB | Not returned by this function | None | RAW conversion loses black/white/clipping provenance for later Natural HDR decisions. | Add a future `read_dng_capture_state()` returning RGB plus `RawCaptureDiagnostics`. |
| `src/spektrafilm/runtime/pipeline.py::HDRSceneEnergyMetadata` | Preprocessed input image | `_scene_luminance()` after auto exposure/crop | None | Sidecar is scene-energy metadata, not a DNG diffuse-white provenance record. | Extend metadata only in a future production pass; keep current sidecar semantics. |
| `src/spektrafilm/runtime/pipeline.py::_preprocess_with_metadata()` | Runtime RGB after auto exposure | Auto-exposed/cropped RGB luminance | None | User/runtime exposure normalization can hide the distinction between capture anchor and look/output exposure. | Natural DNG state should be built before user look/output adjustments redefine brightness. |
| `tools/validate_profile_aware_hdr_raw_samples.py::_raw_processing_diagnostics()` | Real DNG validation sample | Rawpy postprocess statistics | `max(p99, 0.1)` percentile | Useful validation, but still a percentile estimate. | Supersede with confidence/downgrade estimator for Natural HDR decisions. |
| `src/spektrafilm/utils/hdr_photo.py::HDRPhotoMapping` | HDR export mapping params | Optional `scene_luminance` sidecar | `diffuse_white`, `diffuse_white_override`, profile defaults | Many fields author headroom or color rendering. | Keep as authored/creative HDR; disallow these controls from Natural HDR evidence. |
| `src/spektrafilm/utils/hdr_photo.py::_prepare_generic_renditions()` | Linear image plus optional sidecar | Sidecar or input image fallback | `mapping.diffuse_white` | Without provenance, generic fallback can be ambiguous. | A future `natural_scene_hdr` mode should refuse missing RAW/scene/HDR evidence. |
| `src/spektrafilm/utils/hdr_photo.py::_prepare_curve_profile_renditions()` | Look RGB plus scene sidecar | `scene_luminance / diffuse_white` | mapping value/override | Profile `h_profile/s_profile` constructs authored recovery. | Keep as `authored_profile_hdr` or `film_scan_authored_hdr`, not Natural HDR. |
| `src/spektrafilm/utils/hdr_photo.py::_content_headroom()` | HDR pixels or gain ratio | Output/gain result | None | Good metadata estimator, but not source proof. | Label as output/gain headroom, not natural scene headroom. |
| GUI HDR settings | User export controls | Output-layer sidecar | User values | Natural and creative concepts can look adjacent in UI. | Future UI should split Natural HDR, Authored/Creative HDR, and Compatibility Export. |
| HEIC/Ultra HDR/gain-map writers | SDR/HDR pair | Already generated pair | Pair metadata | Packaging can be mistaken for Natural HDR proof. | Keep as compatibility export only. |

## 10. Conflict With `profile_aware` And `modern_recovery_peak_budget`

Current `profile_aware` is valuable, but it is authored profile recovery:

- `profile_hdr_peak_ev`, `profile_hdr_strength`, `profile_hdr_min_gain`, and profile curve parameters shape the HDR target.
- `modern_recovery_peak_budget` explicitly uses recovery ratio and target EV budget.
- path-to-white and highlight chroma controls are output rendering controls.
- changing profile or budget parameters can change HDR gain while scene data is unchanged.

Therefore these modes may export useful HDR, but the estimator classifies them as `authored_hdr_from_raw` if their controls are active.

## 11. Recommended API

Implemented in research form:

- `RawCaptureDiagnostics`: black/white levels, channel clipping, raw percentiles, warnings.
- `SceneLuminanceState`: scene RGB, scene Y, working space, coefficients, optional normalized state.
- `DiffuseWhiteEstimate`: value, method, confidence, provenance, assumptions, warnings, headroom, measured/heuristic/user flags, mode and class.
- `NaturalHDRProvenance`: source type, raw summary, diffuse-white method, class, disallowed controls, downgrade reason.

Recommended future production functions:

- `read_dng_capture_state(path) -> RawCaptureState`
- `compute_scene_linear_rgb_from_dng(raw_state) -> SceneLinearRGB`
- `compute_scene_luminance_y(scene_rgb, working_space) -> SceneLuminanceState`
- `estimate_diffuse_white_from_dng(scene_state, diagnostics, user_anchor) -> DiffuseWhiteEstimate`
- `classify_dng_natural_hdr_eligibility(estimate, active_controls) -> NaturalHDRProvenance`
- `normalize_scene_by_diffuse_white(scene_state, estimate) -> SceneReferredRawState`
- `build_scene_film_master_state(scene_state, film_route) -> SceneFilmMasterState`
- `render_sdr_from_scene_film_state(master_state, output_target) -> np.ndarray`
- `render_hdr_from_scene_film_state(master_state, output_target) -> np.ndarray`
- `encode_gainmap_from_pair(sdr, hdr, provenance) -> container`

## 12. GUI / UX Recommendation

Split HDR into three groups:

### Natural HDR From RAW

- Eligibility: Verified / Estimated / Heuristic / Not eligible.
- Diffuse white: Auto estimate, pick white/gray region, use metadata estimate, conservative default.
- Confidence badge: High / Medium / Low / Invalid.
- Warnings: no calibration target, clipped highlights, low-key uncertainty, emissive highlights, user exposure does not redefine scene white.
- Export: Natural HDR EXR, Natural HDR HEIC only when eligible, SDR fallback.

### Authored / Creative HDR

- profile-aware recovery.
- modern recovery peak budget.
- source chroma / bounded look chroma.
- path-to-white.
- target EV / manual headroom.

### Compatibility Export

- Apple HEIC gain map.
- ISO 21496 gain map.
- Android Ultra HDR JPEG.
- EXR scene-linear archive.

Natural HDR controls must not include target EV, profile peak, budget recovery, path-to-white, or manual headroom as headroom generators.

## 13. Minimal Experiment Results

Synthetic command:

```bash
.venv/bin/python tools/research_dng_diffuse_white_estimation.py \
  --synthetic \
  --json-output /tmp/spektrafilm-dng-natural-hdr-synthetic.json \
  --csv-output /tmp/spektrafilm-dng-natural-hdr-synthetic.csv
```

Result: exit 0, JSON 562 lines, CSV 8 lines.

| Case | Method | Confidence | Recommended mode | Class | Headroom |
| --- | --- | --- | --- | --- | ---: |
| measured_white_card | measured_gray_or_white_card | high | natural_scene_hdr | natural_scene_hdr_verified | 3.000 |
| normal_unclipped_raw | neutral_high_key_statistics | medium | sdr_only | sdr_only_or_unrecoverable | 1.030 |
| low_key_tiny_highlight | low_key_conservative_statistics | low | scene_derived_heuristic_hdr | scene_derived_heuristic_hdr | 4.000 |
| snow_white_wall | neutral_high_key_statistics | medium | natural_scene_hdr | natural_scene_hdr_estimated | 1.526 |
| neon_emissive_highlights | semantic_highlight_guarded_statistics | low | scene_derived_heuristic_hdr | scene_derived_heuristic_hdr | 8.000 |
| clipped_highlights | neutral_high_key_statistics | low | sdr_only | sdr_only_or_unrecoverable | 1.028 |
| authored_controls_active | measured_gray_or_white_card | high | authored_hdr | authored_hdr_from_raw | 3.000 |

Bounded real-DNG command:

```bash
.venv/bin/python tools/research_dng_diffuse_white_estimation.py \
  --sample-dir "/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片/RAW_DNG_历史批量归档" \
  --max-samples 3 \
  --json-output /tmp/spektrafilm-dng-natural-hdr-real.json
```

Result: exit 0. The first three sorted DNGs were rawpy-incompatible RGB/linear DNG-style files and were recorded as `RAW image is not flat`. The scanner then continued and produced three diagnostics:

| File | Method | Confidence | Recommended mode | Class | White | Headroom | Clip |
| --- | --- | --- | --- | --- | ---: | ---: | ---: |
| `IMG20240311182516.DNG` | semantic_highlight_guarded_statistics | low | scene_derived_heuristic_hdr | scene_derived_heuristic_hdr | 0.2487 | 4.002 | 0.00051 |
| `IMG20250812060811_Converted.DNG` | semantic_highlight_guarded_statistics | low | scene_derived_heuristic_hdr | scene_derived_heuristic_hdr | 0.0862 | 1.801 | 0.00000 |
| `IMG20251023145009_converted.DNG` | low_key_conservative_statistics | low | scene_derived_heuristic_hdr | scene_derived_heuristic_hdr | 0.1841 | 1.412 | 0.00000 |

Interpretation: with no white card, no measured lighting, and heuristic-only anchor stability, these real DNG samples are allowed to preserve scene-derived headroom for investigation but are not verified Natural HDR.

## 14. Test Commands And Current Results

Commands run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest tests/test_dng_diffuse_white_estimation.py -q
```

Result: `8 passed in 0.04s`.

```bash
uv run --extra dev pytest tests/test_dng_diffuse_white_estimation.py -q
```

Result: `8 passed in 0.03s`.

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest \
  tests/test_dng_diffuse_white_estimation.py \
  tests/test_hdr_photo.py \
  tests/test_hdr_curve_profiles.py \
  tests/test_image_io_color_metadata.py -q
```

Result: `215 passed in 9.79s`.

```bash
uv run --extra dev pytest tests/test_hdr_photo.py -q
uv run --extra dev pytest tests/test_hdr_curve_profiles.py -q
uv run --extra dev pytest tests/test_image_io_color_metadata.py -q
QT_QPA_PLATFORM=offscreen uv run --extra dev pytest tests/gui/test_controller_output.py -q
QT_QPA_PLATFORM=offscreen uv run --extra dev pytest tests/gui -q
```

Results:

- `tests/test_hdr_photo.py`: `146 passed in 1.58s`.
- `tests/test_hdr_curve_profiles.py`: `35 passed in 4.24s`.
- `tests/test_image_io_color_metadata.py`: `26 passed in 0.53s`.
- `tests/gui/test_controller_output.py`: `21 passed in 2.91s`.
- `tests/gui`: `177 passed in 5.63s`.

```bash
.venv/bin/python -m compileall -q src tests tools scripts
git diff --check
```

Results: both passed.

```bash
.venv/bin/python tools/research_dng_diffuse_white_estimation.py --synthetic ...
```

Result: exit 0.

```bash
.venv/bin/python tools/research_dng_diffuse_white_estimation.py --sample-dir ".../RAW_DNG_历史批量归档" --max-samples 3 ...
```

Result: exit 0, 3 successful DNG diagnostics and 3 classified decode errors.

No validation failures remain in the scoped gates.

## 15. Follow-Up Implementation Issues

1. Add a production `RawCaptureState` that returns linear RGB plus black/white/clipping diagnostics from RAW import.
2. Extend `HDRSceneEnergyMetadata` or a new DNG-specific metadata object with diffuse-white provenance and confidence.
3. Add a `natural_scene_hdr` export mode that refuses missing RAW/scene/HDR provenance.
4. Split GUI HDR controls into Natural, Authored/Creative, and Compatibility groups.
5. Add user white/gray-region picking with an explicit measured-vs-heuristic flag.
6. Preserve existing `profile_aware`, `film_scan_aware`, and `modern_recovery_peak_budget` as authored modes.
7. Add real sample fixtures with measured white card/gray card and known clipping state.
8. Add device-level HEIC/Ultra HDR smoke tests only after Natural and Authored provenance are encoded in metadata.

## 16. Remaining Uncertainty

The remaining uncertainty is real, not a naming loophole:

- No ordinary DNG can reveal physical diffuse white without chart/lighting/cinematography evidence.
- The real-DNG smoke used user files without measured white-card ground truth.
- Some DNGs are not ordinary rawpy Bayer RAW files and need a separate linear-DNG/RGB-DNG path.
- The estimator is a research heuristic, not a trained semantic segmenter.
- HEIC/Ultra HDR device rendering was not part of this pass.
- Scanner/negative-film Natural HDR still needs real scanner dynamic-range evidence, not profile-shaped recovery.

## 17. Direct Answers Required By The Prompt

1. Can Spektrafilm directly know physical diffuse white from an ordinary DNG? No.
2. Without a chart, how should diffuse white be estimated? From scene-linear Y plus RAW clipping stats, metadata hints, neutral-region heuristics, emissive/highlight guards, and confidence/downgrade output.
3. When can an estimate support Natural HDR? When confidence is medium or high, clipping is not severe, real scene values above the anchor exist, and authored controls are inactive.
4. When is it only scene-derived heuristic HDR? Low confidence, no measured anchor, low-key ambiguity, emissive highlights, near clipping, or unstable anchor.
5. When must it be authored/creative HDR? Whenever target EV, budget recovery, profile peak/min gain, path-to-white, source/bounded chroma, or manual headroom creates/reshapes headroom.
6. What should DNG WhiteLevel do? Normalize RAW and diagnose sensor clipping only.
7. What is the relation between sensor saturation white and diffuse white? Sensor saturation is an upper capture boundary; diffuse white is a scene reference and may be far below saturation.
8. Can user exposure, auto exposure, or print exposure change scene diffuse white? No. They can change rendering or normalization, but must not redefine physical diffuse white.
9. Where should Natural HDR scene luminance Y come from? Scene-linear RGB or stronger scene/spectral data with recorded coefficients/provenance.
10. How should Natural HDR headroom be estimated from DNG? As values above diffuse white in scene-linear Y, bounded by clipping diagnostics and confidence.
11. Which existing HDR parameters must be banned from Natural HDR evidence? Profile peak/target EV, recovery budget, min gain, path-to-white, source/bounded chroma, manual headroom, gain-map metadata.
12. How should GUI explain estimated white point? Show measured/estimated/heuristic badges, warnings, and downgrade reasons; do not label heuristic anchors as verified.
13. What should change next? Add production RAW provenance state, Natural/Authored/Compatibility UI grouping, and a strict `natural_scene_hdr` mode after real measured fixtures exist.

## 18. Confidence Loop

Do I have factual confidence that measured diffuse white, estimated diffuse white, sensor white, display white, and paper white are separated in this new work? Yes for the research tool, tests, and document. The code stores `WhiteLevel` only in RAW diagnostics and tests that it does not become diffuse white.

Do I have factual confidence that target EV, budget recovery, profile peak, min gain, and path-to-white cannot become Natural HDR evidence in this new work? Yes for the research classifier: active controls force `authored_hdr_from_raw` even with a measured white card.

Do I have factual confidence that this is not a single percentile hack? Yes for the implemented estimator and tests: low-key, high-key neutral, saturated/emissive, clipping, measured, and authored cases take distinct paths with confidence and warnings.

What is not 100% closed? Physical truth for arbitrary user DNGs without a chart, real lighting measurement, semantic segmentation, and device rendering. Those are documented as real measurement limits, not implementation loopholes.
