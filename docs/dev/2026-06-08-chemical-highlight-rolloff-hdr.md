# 基于胶片化学路径的自然 HDR 高光滚降研究

Date: 2026-06-08

Scope: current `spektrafilm-main` worktree and the RouteMaster HDR architecture
present on 2026-06-08. This document began as a research and implementation
handoff.

Implementation status, 2026-06-09: the v1 RouteMaster `paper` projection now
preserves `output.rgb` in loaded HDR curve profiles, resolves exact film+paper
print-scan profiles, validates the profile before use, applies internal
`paper_rolloff_strategy="chemical_print"` only when the profile is safe and the
source has scene headroom above diffuse white, and records explicit fallback
diagnostics otherwise. Gain-map and HEIC export remain downstream pair encoders.

## 核心结论

自然 HDR 高光滚降不能从 SDR look 事后拉亮，也不能用一条固定 filmic tone curve 替代。对 Spektrafilm 来说，正确的 v1 方向是：

```text
scene-linear RGB / Y
-> camera exposure and optional auto exposure
-> film exposure / log exposure
-> film density and dye response
-> print exposure
-> paper density / reflectance response
-> scanner or display projection
-> SDR and HDR output renditions
-> gain-map or EXR export
```

高光额外亮度必须来自 scene-referred values above diffuse white。胶片和相纸只决定这些高光如何被压缩、染色、保留或变钝。Gain map、HEIC `tmap`、Apple EDR、Android Ultra HDR 和 EXR 都是输出或封装语义，不是自然高光能量的来源。

当前工作树已经有新的 RouteMaster HDR 边界：

- `light_table`: `film -> scan / light table / transmissive display -> HDR display`
- `paper`: `film -> photographic paper print -> idealized digital HDR paper -> HDR display`

本研究主要落在 `paper` 模式。`light_table` 应继续作为 film-scan 路线，不应混入 print paper 的 shoulder。

## 外部基线

最可靠的共同点是分层：scene 内容、photochemical/print 渲染、display 输出、gain-map 封装必须分开。

- Kodak sensitometry material uses density versus log exposure as the core photographic response model. The useful implementation takeaway is not a specific curve constant, but that toe, straight-line section, shoulder, gamma, density range, and D-logE / D-logH relationships are the right coordinates for film and paper response. Sources: [Kodak Basic Photographic Sensitometry Workbook](https://www.kodak.com/content/products-brochures/Film/Basic-Photographic-Sensitometry-Workbook.pdf), [Kodak Motion Picture Glossary](https://www.kodak.com/en/motion/page/glossary-of-motion-picture-terms/).
- ACES Output Transforms explicitly treat display rendering as an output transform from scene-linear values, including tone scale, chroma compression, gamut compression, and display encoding. This supports keeping chemical rolloff upstream of HEIC/gain-map packaging and downstream of scene authority. Source: [ACES Output Transforms](https://docs.acescentral.com/system-components/output-transforms/).
- Apple HDR image APIs use a reference-white / EDR headroom model and Adaptive HDR as an SDR plus HDR/gain-map pair. The gain map describes a relationship between two renditions; it does not create the physical HDR content. Sources: [WWDC23 Support HDR images in your app](https://developer.apple.com/videos/play/wwdc2023/10181/), [WWDC24 Use HDR for dynamic image experiences in your app](https://developer.apple.com/videos/play/wwdc2024/10177/), [ImageIO HDR gain-map auxiliary data](https://developer.apple.com/documentation/imageio/kcgimageauxiliarydatatypehdrgainmap).
- Android Ultra HDR similarly defines a primary image plus gain map metadata for deriving an HDR representation. It is a compatibility container, not a film response model. Source: [Android Ultra HDR Image Format](https://developer.android.com/media/platform/hdr-image-format).
- OpenEXR scene-linear guidance is the clean archival reference: scene-linear values can exceed `1.0` and need tone/display rendering before viewing. Source: [OpenEXR Scene-Linear Image Representation](https://openexr.com/en/latest/SceneLinear.html).
- Reinhard-style photographic tone reproduction and Hable/filmic tone mapping are useful mathematical examples for continuous shoulder shapes, but they should remain fallback/output-rendering references. They do not contain Spektrafilm's measured film, dye, paper, enlarger, and scanner data.

## 当前仓库证据

The strongest local source is `docs/curve_analysis/curve_analysis.json`, summarized by `docs/curve_analysis/film_print_hdr_analysis.md`. It covers 160 film and paper combinations. The data confirms that HDR shoulder behavior is a joint film+paper property.

Paper averages from the current corpus:

| Paper | Avg look white Y | Avg shoulder Y | Avg midtone slope | Avg highlight slope | Avg shoulder spread |
| --- | ---: | ---: | ---: | ---: | ---: |
| `kodak_ultra_endura` | 0.664 | 0.706 | 0.462 | 0.0028 | 0.061 |
| `kodak_ektacolor_edge` | 0.693 | 0.762 | 0.457 | 0.0046 | 0.028 |
| `kodak_endura_premier` | 0.722 | 0.770 | 0.508 | 0.0032 | 0.042 |
| `kodak_supra_endura` | 0.667 | 0.775 | 0.447 | 0.0072 | 0.034 |
| `kodak_portra_endura` | 0.664 | 0.776 | 0.429 | 0.0075 | 0.039 |
| `kodak_2393` | 0.682 | 0.787 | 0.481 | 0.0070 | 0.044 |
| `kodak_2383` | 0.666 | 0.789 | 0.461 | 0.0082 | 0.079 |
| `fujifilm_crystal_archive_typeii` | 0.689 | 0.799 | 0.462 | 0.0074 | 0.057 |

Film averages from the same corpus show two important clusters:

| Film group | Examples | Observed behavior |
| --- | --- | --- |
| Negative color films | Portra, Gold, Vision3, Ektar, C200, X-TRA | Increasing curves, shoulder around `0.91`, low highlight slope around `0.0068` to `0.0127`, low shoulder spread around `0.018` to `0.022`. These are safe candidates for chemical print HDR rolloff. |
| Reversal/positive stocks in print-paper analysis | Provia, Velvia, Ektachrome, Kodachrome | Decreasing or unsafe print-scan curves in the current corpus, low shoulder Y around `0.156` to `0.275`, high channel spread up to `0.235`. Do not use as default print-paper HDR recovery inputs. Route through `light_table` or classify as diagnostic/authored unless a positive scan route is explicitly proven. |

Extremes matter:

- `fujifilm_xtra_400` on `kodak_2383` reaches `shoulder_y=0.955` with `shoulder_spread=0.078`, so it can carry high paper output but needs tint-aware highlight handling.
- `kodak_ektar_100` on `kodak_ektacolor_edge` reaches `shoulder_y=0.899` with very low `shoulder_spread=0.002`, so it can tolerate a more neutral high-light extension.
- `fujifilm_velvia_100` on `fujifilm_crystal_archive_typeii` reaches only `shoulder_y=0.327` with `shoulder_spread=0.262` and negative highlight slope. Treat this as unsafe for print-paper natural HDR recovery.

The current `src/spektrafilm/data/hdr_curve_profiles/README.md` says the bundled profiles use a neutral scene-linear RGB ramp with `scene_y=1.0` as diffuse white and record luminance plus channel diagnostics. That is exactly the first implementation substrate for chemical rolloff.

## What Film And Print Should Control

### Film stock controls

Film should influence:

- how quickly scene exposure reaches the shoulder;
- midtone contrast and highlight compression speed;
- layer/channel separation caused by dye density response;
- whether the route is safe for increasing HDR mapping;
- whether a negative, positive, or reversal route is semantically valid.

Negative color films usually allow smoother, longer highlight preservation. Push processing and high-contrast stocks should enter compression earlier and with less recovery.

Positive/reversal film should not be forced into the paper HDR recovery path just because the output can be made brighter. If the sampled curve is decreasing or nonmonotonic, HDR gain can invert scene order. That is a hard safety failure for `paper`.

### Print paper controls

Print paper should influence:

- paper white and shoulder limit;
- reflection-density saturation;
- channel spread in near-white highlights;
- how much path-to-white is allowed;
- how aggressively output headroom can be extended before paper tint becomes unnatural.

The current corpus shows paper identity strongly changes `shoulder_y` and `shoulder_spread`. `kodak_ultra_endura` has lower average shoulder Y, while `fujifilm_crystal_archive_typeii`, `kodak_2383`, and `kodak_2393` sit higher but can show larger tint spread. A fixed shoulder curve cannot preserve those differences.

### Joint film+paper controls

The high-value implementation detail is the joint response:

```text
scene_y -> sampled RGB print/scan response for selected film + selected paper
```

The joint curve decides:

- where the SDR print look joins HDR extension;
- how fast the shoulder flattens;
- whether per-channel highlight ratios are preserved or attenuated;
- whether a combination is safe enough for natural HDR or must fall back.

Do not implement `paper_rolloff_k` as only a paper lookup or only a film lookup. It should be derived from the sampled joint profile, with paper and film summaries used only as fallback defaults.

## Recommended Architecture

### Public mode boundary

Keep public HDR mode names exactly as current RouteMaster docs describe:

- `light_table`: no paper profile, no print exposure, no paper shoulder.
- `paper`: print-scan route, idealized HDR paper.

Add the chemical rolloff as an internal strategy inside `paper`, not as a new top-level public mode for v1. Suggested internal name:

```python
paper_rolloff_strategy = "chemical_print"
```

The current `project_hdr_ideal_paper()` keeps legacy SDR below diffuse white and extends highlights above it from `scene_y_raw`. That is a good boundary. The missing piece is replacing the generic `_extension_gain()` shoulder with a profile-derived chemical shoulder.

### Data model

Extend or wrap `HDRCurveProfile` so the projection layer can access per-channel sampled output, not just `sdr_luminance_y`.

Minimum shape:

```python
@dataclass(frozen=True, slots=True)
class ChemicalPrintRolloffProfile:
    film: str
    paper: str
    scene_y: np.ndarray
    output_rgb: np.ndarray
    output_y: np.ndarray
    look_diffuse_white_y: float
    shoulder_limit_y: float
    midtone_slope: float
    highlight_slope: float
    shoulder_severity: float
    highlight_tint_spread: float
    safe_for_natural_paper_hdr: bool
```

The data already exists in each sample JSON under:

- `input_domain.scene_y`
- `output.rgb`
- `output.luminance_y`
- `metrics.*`

Current `curve_profile_from_sample()` drops `output.rgb`; the implementation should either preserve it in `HDRCurveProfile` or load a companion chemical profile object at the RouteMaster projection boundary.

### Projection algorithm

For `paper` mode only:

1. Decode or obtain linear `sdr_rgb` from `master.sdr_legacy_rgb`.
2. Use `master.scene_y_raw` as the scene authority.
3. Compute `ratio = scene_y_raw / diffuse_white_scene_anchor`.
4. Preserve exact legacy SDR for `ratio <= 1.0`.
5. For `ratio > 1.0`, evaluate the selected film+paper chemical profile in log2 scene domain.
6. Derive a shoulder progress from the sampled joint profile:

```text
profile_y_at_white = profile(scene_y=1.0)
profile_y_at_scene = profile(scene_y=ratio)
remaining_paper_capacity = shoulder_limit_y - profile_y_at_white
used_capacity = profile_y_at_scene - profile_y_at_white
chemical_progress = clamp(used_capacity / max(remaining_paper_capacity, eps), 0, 1)
```

7. Convert scene headroom to output HDR headroom with a smooth compression whose onset and softness are derived from `chemical_progress`, `shoulder_severity`, and `highlight_slope / midtone_slope`.
8. Preserve `master.route_look_chroma` by default. Only apply path-to-white as a bounded output rendering decision, and reduce it when `highlight_tint_spread` is high.
9. Clamp to `max_headroom` only at the projection output, then build the SDR/HDR pair for the encoder.

The result should be continuous at diffuse white:

```text
scene_y <= diffuse_white_anchor:
  hdr_rgb = sdr_rgb

scene_y > diffuse_white_anchor:
  hdr_y = max(sdr_y, sdr_y * chemical_gain(scene_y, profile, config))
  hdr_rgb = route_look_chroma * hdr_y
```

### Chemical gain sketch

The exact curve can be tuned, but the implementation should obey these constraints:

```python
scene_ev = log2(max(scene_y / diffuse_white_anchor, eps))
severity = profile.shoulder_severity
tint = profile.highlight_tint_spread
slope_ratio = profile.highlight_slope / max(profile.midtone_slope, eps)

softness = lerp(1.8, 0.7, clamp(slope_ratio, 0, 1))
extension_strength = config.paper_extension_strength * (1.0 - 0.35 * severity)
tint_guard = 1.0 - clamp(tint / 0.12, 0, 0.5)
effective_strength = extension_strength * tint_guard
```

Interpretation:

- Higher shoulder severity means less synthetic-looking extension.
- Lower highlight slope means stronger rolloff.
- Higher tint spread means less path-to-white and less aggressive headroom.
- Safe negative color print profiles can keep more scene energy than unsafe or decreasing profiles.

Do not use this sketch as a blind fixed formula. Treat it as the starting point for tests and visual validation against the corpus.

## Fallback And Safety Policy

The projection should fail closed or downgrade explicitly:

| Condition | Behavior |
| --- | --- |
| `master.route_kind != "print_scan"` | Reject chemical paper rolloff and use `light_table` rules only. |
| Missing film or paper identifier | Use current generic `paper` projection and add a diagnostic. |
| No matching curve profile | Use current generic `paper` projection and add a diagnostic. |
| `safe_for_profile_aware_hdr=False` | Do not use chemical natural rolloff. Use generic `paper` or authored fallback with warning diagnostics. |
| `midtone_slope <= 0` or `highlight_slope < 0` | Reject natural paper HDR for that profile. |
| `highlight_tint_spread` above configured threshold | Reduce path-to-white and headroom strength. Do not neutralize highlights by force. |
| SDR-only source with no scene headroom | Produce identical SDR/HDR luminance below or at `1.0`; do not invent headroom. |

Diagnostics should record:

- `paper_rolloff_strategy`
- `chemical_profile_source`
- `chemical_profile_safe`
- `chemical_shoulder_severity`
- `chemical_highlight_tint_spread`
- `chemical_highlight_slope`
- `chemical_midtone_slope`
- fallback reason if any

## Implementation Steps

1. Add per-channel curve access.
   - Preserve `output.rgb` when loading HDR curve profile samples.
   - Keep existing luminance-only consumers compatible.

2. Add a chemical profile resolver.
   - Prefer exact film+paper profile for `paper`.
   - Exclude `film_scan` profiles from print-paper rolloff.
   - Reuse dynamic profile cache keys only when they represent the same deterministic route settings.

3. Add a chemical shoulder helper.
   - Inputs: `RouteMaster`, `HDRProjectionConfig`, chemical profile.
   - Output: `hdr_y` for `paper` projection.
   - Must preserve `sdr_y` at and below diffuse white.

4. Wire into `project_hdr_ideal_paper()`.
   - Keep current generic `_extension_gain()` as fallback.
   - Add diagnostics showing whether chemical rolloff or fallback was used.

5. Keep export unchanged.
   - `save_hdr_photo_heic_from_pair()` remains an encoder for a pre-rendered pair.
   - Do not move film/paper logic into `hdr_photo.py` or HEIC metadata.

6. Add GUI later only after projection semantics are stable.
   - First expose as internal default or hidden strategy.
   - Public controls should remain `paper` and `light_table`.

## Test Plan

Focused tests:

- `tests/test_hdr_routemaster_projection.py`
  - paper chemical rolloff preserves SDR below diffuse white;
  - output is monotonic for safe negative film+paper profiles;
  - `hdr_luminance_y >= sdr_y` for the projected pair;
  - high tint-spread profile reduces path-to-white or headroom strength;
  - unsafe decreasing profile falls back with diagnostics.

- `tests/test_hdr_curve_profiles.py`
  - loaded profile retains `output_rgb`;
  - exact film+paper profile selection works;
  - film-scan profiles are not returned for paper rolloff;
  - unsafe profile criteria reject negative slope and nonmonotonic curves.

- `tests/test_hdr_routemaster_export.py`
  - pair export still uses one `process_master()` call;
  - HEIC encoder receives already-rendered SDR/HDR pair;
  - gain-map metadata does not contain film/print semantics.

Visual and numeric corpus checks:

- Generate neutral ramps for representative pairs:
  - `kodak_portra_400` + `kodak_portra_endura`
  - `kodak_ektar_100` + `kodak_ektacolor_edge`
  - `fujifilm_xtra_400` + `kodak_2383`
  - unsafe reversal example such as `fujifilm_velvia_100` + `fujifilm_crystal_archive_typeii`
- Confirm safe pairs differ in onset, compression, and tint behavior.
- Confirm unsafe reversal examples do not produce natural print-paper HDR.

Required repo gate after implementation:

```bash
.venv/bin/python -m pytest --ignore=tests/gui -q
```

## Acceptance Criteria

The feature is done only when:

- `paper` projection uses selected film+paper chemical data when safe.
- `light_table` remains independent of paper profile and print exposure.
- SDR output and preview remain unchanged.
- Gain-map/HEIC export remains a pure pair encoder.
- The new diagnostics prove which shoulder path was used.
- Unsafe or missing profiles downgrade explicitly, without silent natural-HDR claims.
- Tests cover both safe negative print profiles and unsafe reversal/diagnostic profiles.

## Open Questions

- Whether dynamic route profile generation should become the default for paper mode, or whether bundled profiles are sufficient for v1.
- Whether `post_halation_y` should influence `paper` chemical rolloff above diffuse white, or remain exclusive to `light_table`/spatial highlight authority.
- Whether per-channel chemical profile output should directly shape HDR chroma, or only constrain luma/path-to-white while `route_look_chroma` remains the color authority.
- What threshold should classify `highlight_tint_spread` as high. The corpus suggests `0.12` is a reasonable first guardrail because safe negative print profiles are usually far below it, while unsafe reversal cases often exceed it.

## Recommended First Implementation Default

For v1, implement chemical rolloff as an internal default for `paper` only when all are true:

- exact film+paper profile exists;
- profile route is `print_scan`;
- profile is increasing and safe;
- `midtone_slope > 0`;
- `highlight_slope >= 0`;
- source has scene authority above diffuse white.

Otherwise keep current `paper` projection and record the fallback reason.

This gives a conservative path: safe negative print combinations gain a more photographic shoulder, while questionable routes avoid false natural-HDR claims.
