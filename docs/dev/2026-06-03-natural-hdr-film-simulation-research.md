# Natural HDR Film Simulation Research

Date: 2026-06-03

Scope: current `develop` worktree for `https://github.com/21Z121Z1/spektrafilm`, plus external HDR / gain-map / ACES / film-sensitometry references. This is a research, audit, architecture, and minimal-prototype document. It does not rewrite production HDR behavior.

## External Best-Practice Baseline

The strongest common thread across current references is that scene content, output rendering, and gain-map packaging are separate layers.

- Apple EDR/HDR APIs use an EDR scale where reference white is `1.0` and values above that are display headroom. WWDC23 also distinguishes ISO HDR default reference white / diffuse white metadata from display peak and says ISO HDR defaults reference white to 203 cd/m2 with values above that as headroom. Sources: [WWDC23 Support HDR images in your app](https://developer.apple.com/videos/play/wwdc2023/10181/), [ImageIO HDR gain-map auxiliary data](https://developer.apple.com/documentation/imageio/kcgimageauxiliarydatatypehdrgainmap), [Core Image applyingGainMap](<https://developer.apple.com/documentation/coreimage/ciimage/applyinggainmap(_:)>).
- Apple Adaptive HDR is explicitly a dual-rendition / gain-map approach: a backward-compatible SDR baseline plus per-pixel gain-map information that relates SDR and HDR. Apple recommends saving an Adaptive HDR file from edited SDR and HDR images, with Core Image calculating the gain map; ImageIO can also save an SDR CGImage plus ISO gain-map auxiliary data. Source: [WWDC24 Use HDR for dynamic image experiences in your app](https://developer.apple.com/videos/play/wwdc2024/10177/).
- ISO 21496-1:2025 defines gain-map metadata for dynamic-range conversion between two image representations. This makes gain map a conversion/encoding mechanism, not the source of physical scene energy. Source: [ISO 21496-1:2025](https://www.iso.org/standard/86775.html).
- Android Ultra HDR v1.1 stores a primary image plus a secondary gain-map image with GContainer XMP. Its gain-map metadata defines how to interpret and apply the map to produce the HDR representation; Android recommends supporting both Ultra HDR v1 and ISO 21496-1 metadata for compatibility. Source: [Android Ultra HDR Image Format](https://developer.android.com/media/platform/hdr-image-format).
- OpenEXR is the cleanest reference for scene-linear archive semantics: OpenEXR images are intended to be scene-referred and linear-light; a pixel value of `1000` means one thousand times the represented light of value `1`. Tone mapping is required before display. Sources: [OpenEXR Scene-Linear Image Representation](https://openexr.com/en/latest/SceneLinear.html), [OpenEXR Standard Attributes](https://openexr.com/en/latest/StandardAttributes.html).
- ACES Output Transforms convert scene-linear ACES to output-referred images encoded for a specific display. The output transform includes tone scale, chroma compression, gamut compression, and display encoding. Source: [ACES Output Transforms](https://docs.acescentral.com/system-components/output-transforms/).
- ACES Reference Gamut Compression is a technical correction for problematic out-of-gamut scene values; it does not claim to recover the true color of those pixels, and creative modifications are downstream. Source: [ACES Reference Gamut Compression](https://docs.acescentral.com/rgc/overview/).
- ITU-R BT.2408 treats HDR reference white / diffuse white as an operational HDR production reference; 203 cd/m2 is a widely used HDR reference-white level, but it is not display peak white. Source: [ITU-R BT.2408-7](https://www.itu.int/pub/R-REP-BT.2408-7-2023).
- Film response is exposure/density based. Kodak defines D-log E / D-log H as density plotted against log exposure, and laboratory aim density ties printing control to controlled densities, not display peak luminance. Sources: [Kodak Motion Picture Glossary](https://www.kodak.com/en/motion/page/glossary-of-motion-picture-terms/), [Kodak Laboratory Tools and Techniques](https://www.kodak.com/en/motion/page/laboratory-tools-and-techniques/).

## Term Definitions

- `scene-referred RGB`: RGB values proportional to light in the represented scene, before display rendering. Values can exceed `1.0`.
- `scene-linear luminance Y`: luminance computed from scene-linear RGB with a defined RGB colorimetry. In this design, it is the primary internal brightness coordinate.
- `display-referred RGB`: RGB already rendered for a display, with tone scale, gamut mapping, transfer function, and viewing assumptions applied.
- `SDR reference white`: SDR display white anchor, typically the brightest intended SDR white under the SDR output transform.
- `HDR reference white`: HDR operational output reference, often 203 cd/m2 in current HDR guidance. It anchors ordinary white in HDR output; it is not peak white.
- `diffuse white`: scene-referred anchor for ordinary white diffuse material under the intended exposure. In the recommended internal model, `Y=1.0`.
- `specular highlight`: scene contribution above diffuse white from mirror-like reflection or intense illumination.
- `sensor saturation white`: RAW sensor clipping or DNG `WhiteLevel`; a sensor capture boundary, not a scene diffuse-white definition.
- `paper white`: print/display rendering white for virtual paper or final display. It is output/rendering semantics, not the scene anchor.
- `display peak white`: maximum luminance a target display or output mastering container can represent.
- `headroom`: ratio or EV above a reference white. Internally, scene headroom is scene `Y / diffuse_white`; output headroom is HDR rendition relative to output reference white or gain-map capacity.
- `gain map`: per-pixel conversion data describing how to map one rendition to another, usually SDR to HDR. It encodes the difference between renditions and should not be treated as the source of HDR content.
- `tone mapping`: rendering/compression from a higher dynamic range to a lower or display-limited range.
- `gamut compression`: technical or creative mapping to fit colors into a target gamut while avoiding hard clipping or artifacts.
- `film exposure`: amount of scene light delivered to the film model, normally represented in exposure or log-exposure domain.
- `film density`: processed film optical density response to exposure, often modeled by D-log H curves.
- `print exposure`: exposure of print material from a negative or source, part of output/look rendering.
- `scan exposure`: scanner/capture exposure or normalization used to digitize film density into RGB.
- `film look`: combined visible result of film response, print/scan rendering, spectral/dye effects, grain/halation/glare, and output transform.
- `natural HDR film simulation`: scene-referred film rendering where HDR headroom comes from real scene values above diffuse white, then SDR and HDR are output transforms from the same scene/film response.
- `authored/creative HDR film simulation`: artistically useful HDR where profile curves, target EV, min gain, budgets, or manual highlight color rules create or reshape HDR appearance beyond measured scene energy.

## Current Repository Snapshot

Required commands were run on 2026-06-03:

```bash
git status -sb
git log --oneline --decorate -n 50
git grep -nE "hdr|HDR|scene_luminance|scene_energy|hdr_scene_energy|diffuse_white|reference_white|white_level|headroom|gain_map|gainmap|profile_aware|profile_preserving|modern_recovery_peak_budget|film_scan_aware|negative|positive|density|print|paper|film|exposure|log|linear|ACES|EXR|HEIC|heic|tmap|auxC|gamut|chroma|luminance|tone|rolloff|shoulder|toe" src tests docs tools scripts macos
```

Observed state:

- Branch: `develop...origin/develop [ahead 1]`.
- Pre-existing untracked local files: `debug_mlx.py`, `debug_pipeline.py`, `docs.zip`, `dump_metal.py`, `scratch_mlx_perf.py`, `test_emulsion_nan.py`, `test_kernel_math.py`, `test_mlx_reshape.py`, `test_pipeline_mlx.py`.
- `HEAD`: `fa1c771 Fix profile_kind assertions and add strict HDR export fallback guardrail test`.
- The required `git grep` returned about 29k lines; the relevant current surfaces are `src/spektrafilm/runtime/pipeline.py`, `src/spektrafilm/utils/hdr_photo.py`, `src/spektrafilm/utils/hdr_curve_profiles.py`, `src/spektrafilm/utils/io.py`, `src/spektrafilm/color_management.py`, GUI HDR state/controller files, and the HDR tests/docs listed below.

Current pipeline facts from source:

- `SimulationPipeline.process_with_metadata()` returns the final rendered image plus `HDRSceneEnergyMetadata`.
- `_preprocess_with_metadata()` computes `scene_luminance` after auto exposure and crop/rescale.
- `_scene_luminance()` tries the configured input color space / CCTF path and falls back to Rec.709 coefficients.
- Normal `process()` still returns only the final SDR/display-rendered image, so the default SDR preview/export path is separate from HDR metadata export.
- `save_image_oiio()` requires explicit linear `ColorEncoding` for HEIC/HEIF HDR and passes `scene_luminance` / `scene_rgb` into `save_hdr_photo_heic()`.
- EXR `scene_linear_archive` preserves values; EXR `hdr_rendition` invokes `prepare_hdr_photo_renditions()` and writes `whiteLuminance` / `hdrHeadroom`.

Current pipeline graph:

```text
input image / RAW / scene source
-> color input decoding and optional auto exposure
-> SimulationPipeline._preprocess_with_metadata()
   -> scene_luminance sidecar for HDR export metadata
-> emulsion / film / paper / scanner / tone pipeline
-> display-referred look RGB
   -> default SDR preview/export path
   -> optional HDR export path
      -> generic scene-luminance graft OR profile-aware / film-scan-aware curve path
      -> SDR/HDR pair
      -> HEIC/JPEG gain-map compatibility encoding or EXR HDR rendition
```

## 1. Problem Statement

Current `profile_aware` / `profile_preserving` / `modern_recovery_peak_budget` can be useful, but they should not be described as natural HDR. The core issue is semantic: several controls create or shape headroom with profile curves, target EV, min gain, recovery budgets, chroma grafting, or path-to-white logic. Those are creative HDR rendering decisions, not evidence that the source scene actually contained that headroom.

Natural HDR film simulation should not mean “take an SDR film look and pull highlights brighter.” It should mean:

```text
scene-referred HDR content
-> camera/exposure normalization
-> film exposure/density/print-or-scan response
-> SDR output transform
-> HDR output transform
-> optional gain-map encoding of the SDR/HDR pair
```

The key rule: HDR extra brightness must originate in real scene-referred values above diffuse white, not from `profile_hdr_target_peak_ev`, `profile_hdr_min_gain`, `modern_recovery_peak_budget`, profile-curve shoulder recovery, or gain-map metadata.

Default SDR preview/export must remain unchanged. Any natural HDR implementation should be an explicit independent HDR rendition/export path, with clear names and GUI isolation.

## 2. Proposed Mental Model

Recommended model:

```text
scene-linear input
-> validate scene HDR provenance
-> camera/exposure normalization
-> define diffuse white anchor
-> film exposure domain
-> film negative/reversal response
-> density / dye / spectral or RGB approximation
-> print / scan / display rendering decision
-> produce SDR rendition
-> produce HDR rendition from same scene-referred film response
-> encode SDR/HDR pair as HEIC/JPEG gain map
```

Judgment:

- Film simulation should primarily operate in exposure, log exposure, and density domains. Final SDR RGB gain expansion is a compatibility or creative rendering layer.
- HDR should not be manufactured by profile target EV. It should come from scene-linear content above diffuse white.
- SDR and HDR should be two output transforms from one scene-referred film rendering, not SDR output plus synthetic gain.
- Gain map should describe the difference between the SDR and HDR renditions. It should not be the source of HDR.
- Profile-aware recovery can remain valuable, but it belongs under authored/profile-shaped HDR unless it is driven by a validated scene-rendered film model with content-derived headroom.

## 3. HDR Brightness Definition

Recommended internal definition:

- Use scene-linear luminance `Y` as the primary internal brightness coordinate.
- Define `Y=1.0` as diffuse white by default for natural HDR processing. This is a scene anchor, not sensor white, paper white, or display peak white.
- Treat `Y>1.0` as specular/emissive/headroom content.
- Treat `Y<=1.0` as ordinary diffuse material and shadows.
- SDR reference white, HDR reference white, and display peak white are output constraints. They must not redefine scene content.
- Derive headroom from scene content or from actual HDR rendition pixel statistics. Do not write target EV directly into headroom metadata.
- DNG `WhiteLevel` can help detect sensor saturation or normalize RAW data. It cannot identify diffuse white.

Diffuse-white estimation strategy:

1. User explicitly specifies diffuse white.
2. RAW metadata, exposure, calibration, or capture context estimates it.
3. Image statistics estimate it with a clear `heuristic` flag.
4. SDR-only input uses current SDR reference white only as a display anchor; it must not claim physical HDR.

Current code comparison:

- `pipeline._scene_luminance()` gives useful scene-luminance sidecar data, but it is after auto exposure and crop/rescale. It is good enough for bounded validation, but the doc/API should avoid calling it physically absolute.
- `tools/validate_profile_aware_hdr_raw_samples.py` estimates diffuse white from RAW/postprocess percentiles and marks low confidence. That is a practical heuristic, not a physical diffuse-white proof.
- `hdr_render_ev` multiplies `scene_y` during HDR rendering. That should be labeled creative/rendering EV, not scene energy.

## 4. HDR Color Definition

Recommended internal definition:

- Define HDR color in scene-linear RGB, preferably in a wide-gamut scene space such as ACEScg or another explicitly declared working space.
- Distinguish scene chromaticity, film dye/density response, output gamut mapping, and highlight path-to-white.
- Do not use per-channel clipping as a color definition.
- Do not unconditionally force HDR highlights to white. A path-to-white may be a film/print/display rendering decision, not content truth.
- Gamut compression is an output or technical correction layer. It should not fabricate scene content.
- SDR/HDR renditions should preserve hue continuity unless film response or output transform explains the change.
- OKLab/OKLCH/JzAzBz/ICtCp-like perceptual operations belong to output rendering or gamut/chroma protection, not scene physical content.

Current code comparison:

- `source_chroma` uses `scene_rgb` only if its luminance matches `scene_luminance` within 5%; this is a useful validation guard.
- `bounded_look_chroma` boosts saturation from the authored look; this is creative output rendering, not scene color definition.
- `profile_hdr_path_to_white_*` and `hdr_highlight_path_to_white` are rendering choices. They should be named and documented as such.
- `gamut_map_oklch()` is a technical output constraint; it should stay downstream of scene/film content definition.

## 5. Diffuse White Definition

Recommended definition:

- `diffuse_white` is the scene-referred normalization anchor for ordinary white diffuse objects under the selected scene exposure.
- It is not display peak white.
- It is not paper white.
- It is not DNG `WhiteLevel`.
- It is not scanner white level.
- Specular highlights, emissive sources, sun glints, and lamps may be above diffuse white.
- Paper white is part of print/display rendering. Apple/ISO gain-map `reference white`, `diffuse white luminance`, and capacity/headroom metadata describe output interpretation, not the internal scene anchor.

RAW-specific:

- `WhiteLevel` / sensor white is saturation boundary.
- `AsShotNeutral` / white balance defines neutral axis, not brightness anchor.
- Exposure compensation and print exposure change rendering, not physical diffuse white.

SDR-only input:

- No true HDR information exists. The system cannot naturally generate HDR. It may generate authored/creative HDR if explicitly labeled.

Existing HDR gain map / EXR / scene sidecar:

- These can support natural HDR if the HDR component is treated as input scene or validated HDR rendition provenance, and diffuse white/headroom estimation is explainable and testable.

## 6. Existing HDR Mode Audit

Recommended classifications:

1. `Natural scene HDR film simulation`
2. `Scene-derived but display-constrained HDR`
3. `Authored/creative HDR film rendering`
4. `Profile-shaped synthetic HDR`
5. `Compatibility/export-only gain-map encoding`
6. `Ambiguous / needs proof`

| Mode / component | File / function | Input source | Brightness definition | Color definition | Diffuse white definition | Headroom source | True scene HDR? | Artificial target/profile/budget? | SDR impact | Current risk | Classification | Keep? | Rename? | Remove from default HDR? |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| generic, no `scene_luminance` | `hdr_photo._prepare_generic_renditions()` | `image_data` float values | `image / diffuse_white` | input RGB ratios plus rolloff | `mapping.diffuse_white` | content percentile of computed HDR | only if input is already scene/HDR | `max_headroom`, rolloff, diffuse lift can shape it | SDR preserved by default | Ambiguous: SDR-like float >1 can become HDR without provenance | Ambiguous / needs proof | Keep as low-level helper | `generic_authored_hdr` unless provenance is known | Yes |
| generic with `scene_luminance` | `_graft_scene_luminance()` | authored look + sidecar | sidecar normalized to diffuse white, rolloff/graft | look RGB scaled to target Y | `mapping.diffuse_white`, look white estimate | content percentile capped by `max_headroom` | partially, if sidecar is true scene HDR | graft/lift/rolloff parameters shape output | SDR preserved by default | Good content link, but lift/graft are rendering controls | Scene-derived but display-constrained HDR | Keep | `scene_luminance_graft_hdr` | Not natural default until provenance validated |
| profile-aware strict/profile-preserving | `_prepare_curve_profile_renditions()`, `build_profile_preserving_hdr_curve()` | look + scene sidecar + sampled SDR profile | `h_profile / s_profile` gain on scene coordinate | look gain, optional source/ bounded chroma, path-to-white, gamut compression | scene normalized to `diffuse_white`, profile look white | actual HDR content/profile gain percentile | scene-derived coordinate, but profile creates HDR target | `profile_hdr_peak_ev`, `profile_hdr_min_gain`, strength, knee, softness | SDR preserved | Can be mistaken for physical/natural HDR | Authored/creative HDR film rendering / Profile-shaped synthetic HDR | Keep | `authored_profile_hdr` or `profile_shaped_highlight_recovery` | Yes |
| `modern_recovery_peak_budget` | `profile_modern_recovery_budgeted_gain_ev()` | scene sidecar + SDR profile | compressed EV recovery under target budget | same as profile-aware caller | same as profile-aware | recovery target bounded by `profile_hdr_target_peak_ev` then content headroom | content-aware, but budget-authored | yes: target EV, ratio, knee, hard cap | SDR preserved | Can create/cap toward target instead of natural headroom | Authored/creative HDR film rendering | Keep | `budgeted_highlight_recovery` | Yes |
| `film_scan_aware`, positive film scan | `_resolve_curve_profile()`, `sample_runtime_film_scan_curve_profile()` | film scan route profile + sidecar | positive scan curve + profile HDR gain | positive scan look + profile color recovery | same as profile-aware | content/profile gain | closer to natural if scan contains real retained density info | still uses profile target/gain path | SDR base is positive scan look | Semantics better than print route, but still profile-shaped recovery | Scene-derived but display-constrained HDR / authored film-scan HDR | Keep | split `natural_film_scan_hdr` and `authored_film_scan_hdr` | Remove from natural default until separated |
| raw negative scan diagnostic | `render_negative_scan_positive_rgb()`, raw diagnostic profile rejection | raw negative scan samples | density normalized positive rendering when allowed | scanner RGB density approximation | not a scene diffuse anchor by itself | none unless rendered positive and sidecar exists | no, diagnostic alone | not directly | no default | Raw negative decreasing curve is unsafe for HDR gain | Diagnostic / needs proof | Keep as diagnostic | `diagnostic_negative_scan_hdr` only if exported | Yes |
| `source_chroma` | `_apply_hdr_color_recovery()` | validated `scene_rgb` plus sidecar | `h_profile` target luminance | scene chromaticity where luminance agrees | caller-defined | inherited from profile | can preserve scene color if `scene_rgb` is true scene data | blend and max-chroma controls | SDR preserved | Good guard, but still output/rendering blend | Scene-derived output color recovery | Keep | document as `scene_chroma_output_recovery` | No natural default without scene RGB proof |
| `bounded_look_chroma` | `_apply_hdr_color_recovery()` | authored SDR look | gain-expanded look saturation | output chroma boost | caller-defined | inherited | no | saturation boost/chroma limit | SDR preserved | Creative graft may be mistaken for content color | Authored/creative HDR film rendering | Keep | `creative_look_chroma_boost` | Yes |
| path-to-white | `_apply_hdr_color_recovery()` | profile HDR target | EV relative to look white | desaturation toward luma | look white/profile | inherited | no | path start/end/strength | SDR preserved | Collapses color as rendering choice | Authored/creative HDR film rendering | Keep | `highlight_render_path_to_white` | Yes |
| OKLCH / luma gamut compression | `gamut_map_oklch()`, luma preserving branch | HDR output pixels | target gamut/headroom limits | output compression | none | inherited | no | target gamut/headroom | SDR preserved | Should not define scene content | Output constraint | Keep | no, but document layer | No |
| ISO/Android/Apple gain-map encoding | `encode_gain_map_log2()`, `build_iso_21496_1_gain_map_metadata()`, `save_gain_map_jpeg()`, `save_hdr_photo_heic()` | existing SDR/HDR pair | log2 HDR/SDR ratio | luma/RGB gain map | metadata/output white only | actual pair/headroom metadata | no; packaging only | no content creation if inputs are valid pair | should not affect SDR base | Risk only if upstream HDR pair is synthetic but unlabeled | Compatibility/export-only gain-map encoding | Keep | `compatibility_gainmap_export` | No |

Summary of non-conforming pieces for natural HDR:

- `profile_hdr_peak_ev`, `profile_hdr_target_peak_ev`, `profile_hdr_min_gain`, and `profile_hdr_recovery_ratio` are creative/profile controls. They are not natural HDR evidence.
- `modern_recovery_peak_budget` intentionally enforces a target peak budget. That is useful but not natural.
- `bounded_look_chroma`, `path_to_white`, and gamut compression are output rendering decisions.
- Generic no-sidecar HDR can be natural only when the input array is explicitly scene-linear HDR; otherwise it is ambiguous.
- Gain-map metadata must never be used as proof that the upstream HDR rendition was natural.

## 7. Recommended Architecture

### `natural_scene_hdr_film`

Definition:

- Input must contain true scene-referred HDR content: RAW high-bit-depth scene estimate, EXR scene-linear, existing validated HDR gain map decoded to HDR scene/rendition, `scene_energy` / `scene_luminance` sidecar, or multi-exposure fusion.
- Without true HDR content, do not generate HDR. Output SDR only or raise a clear error.
- `diffuse_white` is a scene anchor.
- Extra HDR brightness comes from scene values above diffuse white.
- Film simulation acts in exposure/density domain.
- SDR and HDR are output transforms from the same scene/film rendering.

### `natural_film_scan_hdr`

Definition:

- Input is a real high-bit-depth film scan or multi-exposure scan.
- Negative film must first pass through explicit negative-to-positive optical/print/scan rendering.
- HDR comes from real scan/density information retained above the SDR rendition, not profile target peak.

### `authored_profile_hdr`

Definition:

- Current `profile_aware` / `profile_preserving` belongs here unless further provenance proves otherwise.
- It may use profile curves and target headroom for visual HDR.
- UI must label it creative/authored; it should not be the natural HDR default.

### `budgeted_highlight_recovery`

Definition:

- Current `modern_recovery_peak_budget` belongs here.
- Target EV, budget, recovery ratio, and min gain are creative parameters.
- It must not be natural HDR default.

### `compatibility_gainmap_export`

Definition:

- Encodes an existing SDR/HDR pair as HEIC/JPEG gain map.
- Handles Apple / ISO / Ultra HDR metadata.
- Does not create HDR content.

## 8. Minimal Prototype And Experiments

Added non-production script:

```bash
tools/research_natural_hdr_film_sim.py
```

Run:

```bash
.venv/bin/python tools/research_natural_hdr_film_sim.py --format json
.venv/bin/python tools/research_natural_hdr_film_sim.py --format markdown
```

The script implements a tiny research-only model:

- scene-linear RGB arrays;
- `diffuse_white` anchor;
- simple film-like log exposure response;
- SDR/HDR renditions from the same scene/film response;
- no HDR headroom when `scene_luminance <= diffuse_white`;
- comparisons against current profile-aware helpers with synthetic profiles.

Experiment plan:

- A: no true HDR content. Expected: natural path emits no `>1.0` headroom. Any current mode that does should be authored/synthetic.
- B: real highlight content. Expected: HDR appears only where scene `Y > 1.0`.
- C: same content, different film profile. Expected: natural HDR spatial distribution remains content-driven; strong profile-dependent headroom indicates authored/profile-shaped behavior.
- D: same profile, different content. Expected: natural HDR varies with content; target-EV convergence indicates budgeted creative recovery.
- E: exposure/print exposure adjustment. Expected: user/rendering exposure changes the rendition but not physical diffuse white.
- F: colored highlights. Expected: separate scene chromaticity, film dye response, path-to-white, and gamut compression.
- G: diffuse-white anchor. Expected: changing the anchor changes computed headroom and must be explicit or tagged heuristic.

Measured prototype results on this worktree:

```text
.venv/bin/python tools/research_natural_hdr_film_sim.py --format markdown
```

| Experiment | Natural headroom | Current/probe headroom | Alignment | Verdict | Interpretation |
| --- | ---: | ---: | ---: | --- | --- |
| A no true HDR content | 1.0000 | n/a | 1.0000 | pass | Natural path emits no HDR headroom when all scene `Y <= 1.0`. |
| B real highlight content | 7.6695 | 1.3730 | 1.0000 | pass | Natural headroom follows real scene highlight energy; the profile-shaped probe compresses this toward its authored curve. |
| C same content, different profiles | 7.6695 | 0.0000 delta | 1.0000 | inspect | The tiny proxy did not show a profile delta for the selected synthetic profiles; production review must still classify the target-EV/min-gain controls as authored because the source code builds `h_profile / s_profile`. |
| D same profile, different content | 7.6695 | 2.7508 | 1.0000 | inspect_budget_cap | Modern recovery is content-aware but budget-constrained by an authored target. |
| E exposure/print exposure adjustment | 7.8066 | 7.6695 | 1.0000 | diffuse_anchor_unchanged | Rendering exposure changes the look; it does not redefine physical diffuse white. |
| F colored highlights | 4.4951 | n/a | 0.9944 | separate_content_from_output_rendering | Color handling needs separate scene chromaticity, film response, path-to-white, and gamut-compression stages. |
| G diffuse-white anchor | 3.8166 | 7.6695 | 1.0000 | anchor_changes_headroom | Changing `diffuse_white` from `1.0` to `2.0` halves the effective headroom scale, so the anchor must be explicit or marked heuristic. |

Prototype caveat: the first version imported `spektrafilm.utils.hdr_photo`; on this machine that route blocked in dynamic-library loading through the package initializer and RAW-processing dependencies. The final prototype avoids production imports and uses a small self-contained proxy for the current profile-shaped equations. The production source audit above remains the authority for current behavior.

## 9. Code/API Direction

Suggested internal concepts:

- `SceneReferredHDR`: carries scene RGB/Y, color space, CCTF state, provenance, and whether values above diffuse white are real.
- `DiffuseWhiteAnchor`: explicit/user, RAW metadata estimate, calibrated estimate, heuristic estimate, or SDR display fallback.
- `FilmExposureState`: exposure/log-exposure values entering film response.
- `FilmDensityResponse`: negative/reversal density response and optional dye/spectral approximation.
- `SDRRendition`: display-referred SDR output transform result.
- `HDRRendition`: display-referred HDR output transform result plus headroom statistics.
- `GainMapExportPair`: validated SDR/HDR pair for compatibility encoding.

Suggested API direction:

- `validate_scene_hdr_inputs(input, provenance) -> SceneReferredHDR`
- `estimate_diffuse_white(scene, method) -> DiffuseWhiteAnchor`
- `process_scene_referred(scene, diffuse_white, film_profile) -> FilmExposureState / FilmDensityResponse`
- `render_sdr_from_scene(film_response, output_transform) -> SDRRendition`
- `render_hdr_from_scene(film_response, output_transform, reference_white) -> HDRRendition`
- `encode_gainmap_pair(sdr, hdr, metadata_target) -> GainMapExportPair`

Suggested GUI grouping:

- `Natural HDR`: enabled only when input provenance supports real scene HDR. Controls: diffuse white anchor method, scene input validation status, output reference white, HDR output transform. No target EV/min gain/budget controls.
- `Creative/Authored HDR`: profile-shaped recovery, budgeted recovery, creative chroma/path-to-white controls. Label as authored.
- `Compatibility Export`: HEIC/JPEG gain-map metadata, Apple/ISO/Ultra HDR toggles, JPEG/HEIF quality, RGB/luma gain map.
- `Diagnostics`: scene luminance sidecar stats, diffuse-white estimate confidence, headroom histogram, gain-map spatial alignment.

## 10. Implementation Guardrails

- Do not alter default SDR preview/export.
- Do not let `target EV`, `profile peak`, `min gain`, or `budget recovery` appear in natural HDR code paths.
- Require explicit scene HDR provenance for `natural_scene_hdr_film`.
- Treat SDR-only input as SDR unless the user selects creative/authored HDR.
- Keep current `profile_aware` working, but rename/label it so users do not mistake it for natural HDR.
- Keep `modern_recovery_peak_budget` as authored recovery.
- Keep gain-map export as packaging of an already-built pair.

## 11. Research Conclusion

Natural HDR in Spektrafilm should happen before output encoding, from scene-linear values above a clearly defined diffuse-white anchor, through the same film exposure/density response that also produces the SDR rendition. The gain map should be the final compatibility encoding of an SDR/HDR pair.

Current Spektrafilm already has useful ingredients: scene-luminance sidecar capture, linear/ACES-aware color management, EXR scene-linear archive support, gain-map metadata, and mode isolation for `profile_aware` / `film_scan_aware`. The main semantic problem is naming and default-path discipline: `profile_aware`, `profile_preserving`, and `modern_recovery_peak_budget` should be treated as authored/profile-shaped HDR until a new `natural_scene_hdr_film` path is implemented with strict scene provenance and no synthetic target-EV controls.

## 12. Follow-Up Issues

Recommended implementation issues:

1. Add a new `natural_scene_hdr_film` path, probably near `src/spektrafilm/utils/hdr_photo.py` but backed by a clearer scene/HDR data model rather than more flags on `HDRPhotoMapping`.
2. Add scene HDR provenance and diffuse-white confidence types around `src/spektrafilm/runtime/pipeline.py`, `src/spektrafilm/utils/io.py`, GUI state/persistence, and HDR export settings.
3. Split current GUI controls into `Natural HDR`, `Creative/Authored HDR`, `Compatibility Export`, and `Diagnostics`.
4. Rename or relabel `profile_aware` / `profile_preserving` to `authored_profile_hdr` or `profile_shaped_highlight_recovery`.
5. Rename or relabel `modern_recovery_peak_budget` to `budgeted_highlight_recovery`.
6. Split `film_scan_aware` into natural high-bit-depth film-scan HDR, authored film-scan HDR, and diagnostic negative-scan handling.
7. Add tests mirroring experiments A-G before production implementation.
8. Add import/export tests proving gain-map encoding consumes an existing SDR/HDR pair and does not create HDR content by itself.
9. Add UI copy/tests preventing SDR-only input from being labeled natural HDR.

## 13. Direct Answers

1. In Spektrafilm, natural HDR film simulation should be a scene-referred film rendering where HDR energy comes from real scene values above diffuse white, then SDR and HDR are two output transforms from that same response.
2. HDR color should be defined in scene-linear RGB or a declared wide-gamut scene space before output rendering.
3. HDR brightness should be defined internally as scene-linear luminance `Y`.
4. Diffuse white should be the scene-referred ordinary-white anchor, typically `Y=1.0`. It should not be DNG `WhiteLevel`, sensor clipping, paper white, display peak white, or gain-map capacity metadata.
5. Current `profile_aware` is not natural HDR by default. It is scene-sidecar-aware, but the HDR target is profile-shaped and uses authored controls.
6. Current `modern_recovery_peak_budget` is not natural HDR. It is budgeted creative highlight recovery.
7. Current `film_scan_aware` is mixed. Positive high-bit-depth scan handling is a useful starting point, but the current mode still uses profile-shaped recovery, so classify it as scene-derived/authored until split.
8. True `natural_scene_hdr_film` minimally needs validated scene-referred HDR input, scene-linear RGB/Y, declared colorimetry, a diffuse-white anchor, film exposure/density response, and separate SDR/HDR output transforms.
9. SDR-only input should not allow natural HDR. It may allow explicitly labeled creative/authored HDR.
10. Next files to change are `src/spektrafilm/utils/hdr_photo.py`, `src/spektrafilm/runtime/pipeline.py`, `src/spektrafilm/utils/io.py`, GUI HDR state/settings/persistence/widgets, and the focused HDR tests.

## 14. Verification Results

Commands run in this pass:

```bash
.venv/bin/python -m py_compile tools/research_natural_hdr_film_sim.py
.venv/bin/python tools/research_natural_hdr_film_sim.py --format json
.venv/bin/python tools/research_natural_hdr_film_sim.py --format markdown
.venv/bin/python -m pytest tests/test_hdr_photo.py -q
.venv/bin/python -m pytest tests/test_hdr_curve_profiles.py -q
.venv/bin/python -m pytest tests/test_image_io_color_metadata.py -q
.venv/bin/python -m pytest tests/gui/test_controller_output.py -q
.venv/bin/python -m pytest tests/gui -q
.venv/bin/python -m compileall -q src tests tools scripts
git diff --check -- docs/dev/2026-06-03-natural-hdr-film-simulation-research.md tools/research_natural_hdr_film_sim.py
git diff --no-index --check /dev/null docs/dev/2026-06-03-natural-hdr-film-simulation-research.md
git diff --no-index --check /dev/null tools/research_natural_hdr_film_sim.py
```

Results:

- Prototype compile: passed.
- Prototype JSON and Markdown runs: passed.
- `tests/test_hdr_photo.py`: 145 passed.
- `tests/test_hdr_curve_profiles.py`: 35 passed.
- `tests/test_image_io_color_metadata.py`: 26 passed.
- `tests/gui/test_controller_output.py`: 21 passed.
- `tests/gui -q`: 167 passed, 2 failed. Both failures are in `tests/gui/test_controller_runtime_module.py`; current code appends a runtime duration like `| 0.00s`, while those tests still expect the older status string without duration. This was not caused by the new research doc or prototype.
- `compileall`: passed.
- `git diff --check`: passed for tracked diff state.
- `git diff --no-index --check` and trailing-whitespace scans on the two untracked research files: passed.

## 15. Remaining Uncertainty

Remaining uncertainty is implementation-specific, not conceptual:

- True RAW diffuse-white estimation needs calibrated samples or explicit user input; a single SDR-looking image cannot prove physical diffuse white.
- Apple/ISO/Ultra HDR metadata behavior can be specified from docs, but device/app rendering differences still need real viewer validation when production export changes happen.
- The prototype uses a tiny self-contained proxy for profile-shaped HDR equations. It validates the natural-vs-authored distinction, not production image quality.

Confidence loop answer: yes, this pass has enough source, test, prototype, and external-reference evidence to separate scene-derived natural HDR, authored creative HDR, and export-only gain-map encoding. The remaining uncertainties are about future implementation fidelity and platform rendering, not about the classification boundary.
