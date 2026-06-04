# HDR Naturalness Audit

Date: 2026-06-03
Refreshed: 2026-06-04

Scope: current `develop` checkout of `spektrafilm-main`, focused on whether HDR export paths are content-derived or authored/synthetic. This audit intentionally does not change production behavior.

## Executive Conclusion

The current HDR system has real content-derived inputs, but most user-visible HDR photo export modes are not pure natural HDR.

- `generic` with `scene_luminance` is the closest current content-derived path, but it still applies display/print constraints such as diffuse lift, paper rolloff, graft strength, headroom percentile, and `max_headroom`.
- `profile_aware` / `profile_preserving` is best classified as `authored_profile_hdr`: it uses real scene luminance as the coordinate, but the HDR extension comes from sampled film/paper SDR profiles and authored controls such as `profile_hdr_peak_ev`, `profile_hdr_min_gain`, shoulder capacity, path-to-white, and gamut/chroma rendering.
- `modern_recovery_peak_budget` is best classified as `budgeted_highlight_recovery`: it explicitly uses `recovery_ratio`, `target_peak_ev`, percentile normalization, and optional hard caps to shape highlight recovery.
- `film_scan_aware` is currently `film_scan_authored_hdr`, not natural film-scan HDR. The current source correctly renders negative-film scan profiles into positive scan profiles before gain construction, but the HDR gain is still profile-shaped recovery rather than scanner-measured natural dynamic range.
- HEIC/JPEG gain-map and EXR metadata paths are mostly format plumbing. They can carry either natural or authored HDR depending on which SDR/HDR pair is fed into them.
- Scene-linear archive EXR is the current path that can preserve real HDR values without applying the authored HDR photo mapping.

Recommendation: keep the authored modes, but rename and group them honestly. Add a separate `natural_scene_hdr` mode that refuses to synthesize HDR when there is no RAW/scene-linear/HDR sidecar/existing gain-map evidence.

## Reference Baseline

Primary references consulted and classification implications:

- Apple HDR app guidance and APIs: <https://developer.apple.com/documentation/uikit/supporting-hdr-images-in-your-app>, <https://developer.apple.com/documentation/imageio/kcgimageauxiliarydatatypehdrgainmap>, <https://developer.apple.com/documentation/coreimage/ciimageoption/expandtohdr>, <https://developer.apple.com/documentation/coreimage/ciimage/applyinggainmap(_:)> and <https://developer.apple.com/documentation/coreimage/kciimagerepresentationhdrgainmapimage>. Apple documents HDR gain maps as auxiliary HDR information that can be expanded/applied/read/written; that makes gain-map plumbing a carrier of an SDR/HDR pair, not proof that the HDR rendition is content-natural.
- Android Ultra HDR image format: <https://developer.android.com/media/platform/hdr-image-format>. Android describes JPEG gain-map signaling, metadata handling, SDR fallback when metadata is invalid, and rendering on SDR or HDR displays; this supports separating content/rendition provenance from compatibility encoding.
- ISO 21496-1:2025 public standard page: <https://www.iso.org/standard/86775.html>. ISO frames the topic as gain map metadata for image conversion and dynamic range conversion; it is format metadata, not a license to synthesize scene energy.
- OpenEXR scene-linear guidance and overview: <https://openexr.com/en/latest/SceneLinear.html> and <https://openexr.com/en/latest/index.html>. OpenEXR distinguishes scene-referred scene-linear storage from display-ready JPEG-like imagery; scene-linear archive EXR is the cleanest current path for preserving real HDR values.
- ACES Input/Output Transform docs: <https://docs.acescentral.com/system-components/input-transforms/> and <https://docs.acescentral.com/system-components/output-transforms/>. ACES separates camera/input transforms into scene-referred relative exposure values from output transforms that render those values for display; this is the benchmark for not confusing scene energy with display/authored rendering.

Working definitions for this audit:

- **Content-derived HDR / natural HDR**: HDR values come from RAW or scene-linear data, real exposure latitude, an existing HDR/gain-map sidecar, multi-exposure fusion, or traceable scene reconstruction. The SDR base is a display rendering; the HDR rendition or gain map carries real extra scene brightness relative to that base.
- **Authored or synthetic HDR**: HDR extension comes from target EVs, profile targets, min gain, recovery ratios, budgets, hard caps, safe headroom, path-to-white, chroma grafting, synthetic `h_profile`, or similar active rules. It may be visually useful, but should not be described as content-natural dynamic range.
- **Display/format constraints**: `max_headroom`, gamut compression, clipping, tone mapping, reference white, and auxiliary metadata can be necessary constraints. They must be separated from the step that creates HDR content.
- **Creative HDR**: Artistic/authored HDR modes are acceptable if the UI and documentation identify them as creative/authored and do not imply physical film/paper/scanner HDR.

## Command Evidence

Required repository snapshot:

```text
$ git status -sb
## develop...origin/develop
?? debug_mlx.py
?? debug_pipeline.py
?? docs.zip
?? dump_metal.py
?? grep_results.txt
?? scratch_mlx_perf.py
?? test_emulsion_nan.py
?? test_kernel_math.py
?? test_mlx_reshape.py
?? test_pipeline_mlx.py
?? tools/research_natural_hdr_film_sim.py
```

```text
$ git log --oneline --decorate -n 50
d9e31d2 (HEAD -> develop, origin/develop) Optimize MLX computing backend, avoid redundant evaluate/cache clear, and add architecture documentation
fa1c771 Fix profile_kind assertions and add strict HDR export fallback guardrail test
391d907 Fix negative scan positive rendering trigger logic and add tests
38ffa49 fix(mlx): remove pre-scan cleanup and disable cleanup during GUI preview
52e9fc3 fix: handle NaN values, ensure MLX memory cleanup, and update GUI process_with_metadata
e5feb5d perf: remove MLX hard sync points in LUT compute and color reference to enable asynchronous dispatch
5abb30e chore: save current state before MLX optimization
31943dc feat(gpu): implement MLX backend for output gamut compression
00c67f7 fix: compute backend GUI switch now correctly propagates to pipeline
3e27ad2 docs: record MLX hot path benchmark results
d721fda docs: update upstream sync post-commit report
40e387b chore: finalize upstream sync state
949cf43 (backup/before-upstream-sync-20260602-2303) fix: handle Optional/float|None union types in GUI editor resolution
f0ca402 feat: add GPU compute backend section to ADVANCED tab
0f2d538 fix: add output_cctf_encoding parameter to _prepare_output_display_image
0e25f8c fix: adapt GUI code and tests to our param names and state structure
28dd4b6 fix: use our grain param names in GUI manifest
39c9051 docs: record upstream sync plan and report
3e6192f fix: restore our grain param names in examples and scripts
0d3aeda Merge upstream/main into develop
1320342 (backup/before-upstream-sync-20260602-2023) refactor: remove debug_mode pipeline path and simplify process()
906351e (upstream/main, upstream/dev) Merge branch 'gui-refactor'
6deeec3 (upstream/gui-refactor) feat: gui refactor with param manifest
7e82205 docs: record upstream sync report
966e7c3 Merge upstream main into develop
be287ac (backup/before-upstream-sync-20260601-1804) feat: preserve film-scan aware gui hdr export before upstream sync
202db06 feat: preserve film-scan aware hdr export mode before upstream sync
ccfd67e feat: preserve film-scan hdr curve profile support before upstream sync
1ff22b1 docs: record local cleanup audit before upstream sync
ee66de6 (backup/before-upstream-sync-20260601-1755) chore: stop tracking matplotlib font cache
3a8f957 test: preserve gui hdr export mapping coverage before upstream sync
f7e39f7 test: preserve film-scan hdr mapping coverage before upstream sync
6ba553f test: preserve hdr curve route coverage before upstream sync
1a26ba7 chore: preserve local work before upstream sync
500bc42 merge: pr#40 from paperdigits/patch-1
894a801 Add coffee link in readme.
6ec371b fix: black level of jzazbz/cam16ucs gamut compress
cd254ba fix: spektrafilm license now in package data
0a44600 Merge branch 'dev'
a8674f0 chore: add useful links to the readme
0377654 chore: readme support statement
ac16d86 fix: install dependency and pyproject
e9022e6 docs: comprehensive documentation update - audit, status headers, new files
67d116a merge: sync with origin/develop and resolve conflicts
1888ff4 fix(halide): AOT generator bugs - match Python JIT reference
7cb4f87 Merge sync/upstream-merge-20260529 into develop
6696c52 Merge remote-tracking branch 'upstream/main' into sync/upstream-merge-20260529
eac6b85 feat: optimize i/o gamut compress and use CAT16
```

Required grep:

```text
$ git grep -nE "...requested HDR expression..." src tests docs tools scripts macos
Total output lines: 7714

$ git grep -lE "...requested HDR expression..." src tests docs tools scripts macos | wc -l
449
```

The full raw grep output is too large to reproduce usefully here. I used it to locate the current hot paths, then grounded the classifications below in current source and tests rather than archived documents.

Current source windows read:

- `src/spektrafilm/utils/hdr_photo.py`: `HDRPhotoMapping`, generic/profile/film-scan dispatch, `_prepare_curve_profile_renditions()`, `_apply_hdr_color_recovery()`, `_graft_scene_luminance()`, `_content_headroom()`, gain-map metadata helpers.
- `src/spektrafilm/utils/hdr_curve_profiles.py`: runtime profile sampling, positive negative-scan rendering, `build_profile_hdr_curve()`, `build_profile_preserving_hdr_curve()`, `profile_modern_recovery_budgeted_gain_ev()`, `budget_recovery_gain_ev()`.
- `src/spektrafilm/runtime/pipeline.py`: `HDRSceneEnergyMetadata`, `process_with_metadata()`, `_scene_luminance()`.
- `src/spektrafilm/utils/io.py`: HEIC/HEIF HDR photo dispatch, scene-linear EXR archive, authored HDR rendition EXR.
- `src/spektrafilm/color_management.py`: ACES scene-linear detection and SDR preview transform.
- `src/spektrafilm_gui/controller.py`, `hdr_settings.py`, `param_manifest.py`, `options.py`: GUI HDR export state and save dispatch.
- Tests in `tests/test_hdr_photo.py`, `tests/test_hdr_curve_profiles.py`, `tests/test_image_io_color_metadata.py`, and `tests/gui`.

## Classification Table

| Component / file / function | Current mode or parameter | Content source | HDR extension source | Classification | Default on? | Affects SDR? | Keep? | Rename? | Remove from default HDR path? | Recommended alternative |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `runtime/pipeline.py::HDRSceneEnergyMetadata` / `_scene_luminance()` | Scene sidecar after auto exposure/crop | Preprocessed input RGB luminance | None; metadata only | Content-derived input metadata | Metadata only when `process_with_metadata()` is used | No direct SDR change | Yes | No | No | Preserve as `scene_energy` contract; add provenance fields for RAW/EXR/HDR sidecar source |
| `hdr_photo.py::_prepare_generic_renditions()` with `scene_luminance` | `hdr_mapping_mode="generic"` | `scene_luminance` sidecar plus authored look RGB | `_graft_scene_luminance()` uses diffuse lift, paper rolloff, graft strength, caps | Content-derived but display constrained | GUI default mapping is generic, but HEIC gain map is off | HDR export SDR base only | Yes | Maybe: `scene_luminance_graft` | No, but separate from strict natural mode | Natural mode should disable synthetic diffuse lift/rolloff unless explicitly selected |
| `hdr_photo.py::_prepare_generic_renditions()` without sidecar | Generic fallback | Input image pixels | Input divided by `diffuse_white`, optional fallback paper rolloff | Ambiguous / needs proof | Yes if caller omits sidecar | HDR export SDR base only | Keep as compatibility | Yes: `input_float_hdr_or_fallback` | Yes for `natural_scene_hdr` | Require explicit existing-HDR input proof or refuse natural HDR |
| `hdr_photo.py::_graft_scene_luminance()` | `diffuse_white`, `hdr_diffuse_white_target`, `graft_*`, `paper_rolloff_*` | Sidecar scene luminance | Diffuse lift + paper/specular graft | Creative tone-mapped HDR when controls are active | Used by generic sidecar | HDR rendition only | Keep | Yes: `authored_scene_graft` | Yes from pure natural mode | `natural_scene_hdr` should use scene luminance directly or with display-only cap |
| `hdr_photo.py::_apply_rolloff()` | `paper_rolloff_*`, `max_headroom` | Scene luminance | Paper/logarithmic rolloff compression | Creative tone-mapped HDR / display constraint | Enabled in mapping defaults | HDR rendition only | Keep | No if documented | Remove from natural generation; allow as display rendering | Split into `display_tone_mapping` |
| `hdr_photo.py::_content_headroom()` | `headroom_percentile` | Output HDR pixels or gain | Robust percentile headroom | Content-derived but display constrained | Yes | Metadata/cap only | Yes | No | No | Keep as metadata estimator, but distinguish absolute pixel peak vs gain ratio |
| `HDRPhotoMapping.max_headroom` | Export cap | None | Hard cap on generic; profile path also uses profile `safe_max_headroom` | Display/format constraint | Default 8.0 | HDR rendition only | Yes | No | No | Treat only as cap, never as evidence of real content peak |
| Profile defaults `safe_max_headroom` | Profile cap | Profile database defaults | Cap/clipping for profile HDR | Display/format constraint that participates in generation | Yes for profile routes | HDR rendition only | Yes | Maybe `profile_safe_cap` | No as cap; yes as natural evidence | Use with `min(mapping.max_headroom, safe_max_headroom)` semantics if user cap must be hard |
| `profile_aware` route | `hdr_mapping_mode="profile_aware"` | Scene luminance sidecar + film/paper selection | `h_profile / s_profile` from sampled SDR profile and authored parameters | Profile-authored HDR | Not HEIC default; selectable | SDR base preserved in HDR file | Yes | Yes: `authored_profile_hdr` | Yes from natural mode | Keep as explicit creative/profile recovery |
| `hdr_curve_profiles.py::build_profile_preserving_hdr_curve()` strict branch | `profile_hdr_mode="strict_preserving"` | `scene_y` coordinate and sampled SDR profile | `profile_relative_hdr_gain_ev()`, peak EV, strength, knee, shoulder slope, min gain, soft clip | Profile-authored HDR | Default inside profile path | HDR rendition only | Yes | Yes: `strict_profile_authored_recovery` | Yes | Document as authored recovery, not physical film/paper HDR |
| `profile_hdr_peak_ev` | Default 1.5 EV | None | Authored visual peak | Profile-authored HDR | Yes in strict branch | HDR rendition only | Yes | Maybe `authored_peak_ev` | Yes | UI should label as authored peak |
| `profile_hdr_strength`, `profile_hdr_knee_ev`, `profile_hdr_softness_ev` | Strict branch controls | None | Shape of synthetic recovery | Profile-authored HDR | Yes in strict branch | HDR rendition only | Yes | Maybe | Yes | Group under Authored / Creative HDR |
| `profile_hdr_min_gain=1.0` | Recovery floor | None | Forces `h_profile >= s_profile` | Profile-authored HDR | Yes | HDR rendition only | Yes for recovery mode | Maybe `recovery_only_floor` | Yes | Keep only in authored recovery modes |
| `profile_hdr_enforce_monotonic` | Monotonic HDR target | None | Sorting/accumulate constraint | Display/rendering constraint | Yes | HDR rendition only | Yes | No | No | Keep as safety invariant |
| `modern_recovery_peak_budget` | `profile_hdr_mode="modern_recovery_peak_budget"` | Scene/profile compression estimate | Recovery ratio + target EV budget + hard cap | Synthetic / budgeted HDR | GUI can select via headroom mode | HDR rendition only | Yes | Yes: `budgeted_highlight_recovery` | Yes | Explicit creative authored mode |
| `profile_modern_recovery_budgeted_gain_ev()` | Recovery budget helper | Scene EV, profile EV | `recovery_ratio * compressed_ev`, target peak budget | Synthetic / budgeted HDR | Only when mode selected | HDR rendition only | Yes | No if parent renamed | Yes | Use as authored highlight-recovery algorithm |
| `budget_recovery_gain_ev()` | `target_peak_ev`, percentile, hard cap | None | Scales raw gain to a target | Synthetic / budgeted HDR | Only modern branch | HDR rendition only | Yes | No if parent renamed | Yes | Do not expose as natural headroom |
| `build_dynamic_curve_profile()` | Dynamic profile samples | Runtime scene/look samples | Converts user/current look samples into profile defaults | Ambiguous / needs proof | Only if caller supplies samples | Can alter HDR generation | Keep with provenance | Yes: `dynamic_authored_profile` | Yes | Require provenance and explicit user opt-in |
| `legacy_graft` | `profile_curve_mode="legacy_graft"` | Scene luminance and profile | Legacy diffuse/specular graft | Creative tone-mapped HDR | Not default | HDR rendition only | Keep as fallback | Yes: `legacy_authored_graft` | Yes | Deprecate behind debug/compatibility |
| `film_scan_aware` | `hdr_mapping_mode="film_scan_aware"` | Scene luminance + film-scan profile | Positive scan profile-shaped `h_profile / s_profile` | Profile-authored HDR | Not default | HDR rendition only | Yes | Yes: `film_scan_authored_hdr` | Yes | Future `natural_film_scan_hdr` requires measured scanner multi-exposure/high-bit source |
| `sample_runtime_film_scan_curve_profile()` positive film route | `positive_film_scan` | Runtime film-scan sampled ramp | Sampled positive scan SDR profile | Profile-authored HDR input | Only film-scan mode | No direct SDR change | Yes | No | Yes from natural mode | Preserve paper isolation |
| `sample_runtime_film_scan_curve_profile()` negative film route | `positive_negative_scan` | Raw negative scan sampled ramp | Positive negative-scan rendering + sampled profile | Creative / profile-authored HDR input | Only negative film-scan mode | Changes HDR SDR base for negative scan | Yes | Maybe | Yes | Keep diagnostics; improve proof with real scanner samples |
| `raw_negative_scan` profile kind | Diagnostic only | Raw negative scan | None safe for HDR; rejected by `film_scan_aware` | Ambiguous / diagnostic, not HDR generation | No | No | Yes as diagnostic | No | Yes | Continue rejecting for gain construction |
| `hdr_highlight_color_mode="source_chroma"` | Source chroma graft | `scene_rgb` if consistent with sidecar | Chroma from scene RGB multiplied by authored `h_profile` | Ambiguous / creative color recovery | Off by default | HDR rendition only | Keep | Yes: `scene_chroma_recovery` | Yes | Mark as color rendering, not natural luminance |
| `hdr_highlight_color_mode="bounded_look_chroma"` | Saturation boost and chroma limit | Authored SDR look | Highlight chroma boost gated by gain/luma | Creative tone-mapped HDR | Off by default | HDR rendition only | Keep | Yes | Yes | Creative color rendering group |
| `profile_hdr_path_to_white_*` / `hdr_highlight_path_to_white` | Path-to-white | None | Desaturates high EV toward luma | Creative tone-mapped HDR | Profile strength default 0.30 | HDR rendition only | Keep | Yes | Yes | Label as highlight color rendering |
| `gamut_map_oklch()` | Oklch perceptual gamut mapping | HDR RGB after generation | Chroma compression into selected gamut/headroom | Display/format constraint; can change color semantics | Optional | HDR rendition only | Yes | No | No as constraint; yes as generator | Put under Display/Format constraints |
| Luma-preserving compression in `_apply_hdr_color_recovery()` | Default gamut mode | HDR RGB after generation | Reduces chroma above max channel cap | Display/format constraint | Yes default | HDR rendition only | Yes | No | No | Keep but document |
| `encode_gain_map_log2()` | Gain map normalization | SDR/HDR pair | Encodes `log2(hdr_luma/sdr_luma)` | Metadata-only / format plumbing | Used by gain-map export | No | Yes | No | No | `compatibility_gainmap_export` |
| `build_iso_21496_1_gain_map_metadata()` | `HDRCapacityMax=headroom` | Rendition headroom | Metadata from generated pair | Metadata-only / format plumbing | Used by gain-map export | No | Yes | No | No | Ensure headroom provenance is not overstated |
| `save_hdr_photo_heic()` / Swift encoder | HEIC HDR photo export | Prepared SDR/HDR renditions | Encodes existing generated pair | Metadata-only / format plumbing | Only explicit HEIC gain-map save | No production SDR change | Yes | No | No | Compatibility writer only |
| `save_image_oiio()` HEIC branch | Requires linear, unclipped encoding | Caller pixels + optional sidecars | Delegates to HDR photo mapping | Format dispatch | Only HEIC/HEIF | No ordinary format impact | Yes | No | No | Keep strict rejection of CCTF/clipped input |
| `save_image_oiio()` EXR `scene_linear_archive` | Default EXR mode | Caller scene-linear pixels | None; writes raw float EXR | Content-derived HDR if input is real scene-linear | Default EXR mode | No | Yes | No | No | Use for `natural_scene_hdr` archival output |
| `save_image_oiio()` EXR `hdr_rendition` | Explicit EXR rendition | Caller pixels + sidecars | Applies same authored HDR photo mapping | Creative tone-mapped HDR | Not default | No | Yes | Yes: `authored_hdr_rendition_exr` | Yes | Keep separate from archive EXR |
| `aces_sdr_video_view_transform()` | ACES SDR view | ACES scene-linear pixels | Display transform, not HDR generation | Display constraint / preview rendering | Only ACES preview | Preview only | Yes | No | No | Keep as display view |
| GUI `HDRExportSettings` | Generic default, gain map disabled | Output-layer metadata | User-selectable mapping and caps | UI / routing | HEIC gain map disabled by default | No ordinary save impact | Yes | Regroup labels | No | Split into Natural / Authored / Compatibility groups |
| GUI `hdr_headroom_mode` | `content_percentile` or `modern_recovery_peak_budget` | None | Switches authored budget mode | Synthetic / budget control | Content percentile default | HDR export only | Yes | Yes | Yes from natural mode | Move to Authored / Creative HDR |
| `params_mapper.py::_apply_io()` | Hardcodes `output_cctf_encoding=True` | None | Forces GUI runtime output encoding | Ambiguous adjacent UX risk | Yes in GUI mapping | Can affect scene-linear export UX | Needs review | No | Not HDR generation | Future natural HDR GUI must expose true output encoding/caps |

## Focused Findings

### 1. `profile_aware` / `profile_preserving`

Evidence:

- `HDRPhotoMapping` declares `profile_hdr_peak_ev`, `profile_hdr_strength`, `profile_hdr_knee_ev`, `profile_hdr_min_gain`, `profile_hdr_path_to_white_*`, and `profile_hdr_mode` controls.
- `prepare_hdr_photo_renditions()` dispatches `profile_aware` and `film_scan_aware` into `_prepare_curve_profile_renditions()`.
- `_prepare_curve_profile_renditions()` requires `scene_luminance`, resolves a film/paper or film-scan profile, builds `s_profile` and `h_profile`, then computes `hdr_gain = h_profile / s_profile`.
- `build_profile_preserving_hdr_curve()` documents the returned `h_profile` as authored HDR target luminance, not measured HDR scene energy.

Conclusion:

- `h_profile` is not real scene energy. It is built from the SDR film/paper or film-scan profile plus authored gain rules.
- `hdr_gain = h_profile / s_profile` is profile-shaped synthetic gain.
- `profile_hdr_peak_ev` and `profile_hdr_target_peak_ev` prescribe target brightness behavior rather than reading content peak brightness.
- `profile_hdr_min_gain=1.0` explicitly makes this recovery-only; it prevents the profile HDR target from going below the SDR profile target.
- The current name `profile_aware` is accurate only if read as "profile-aware authored recovery." It is misleading if users read it as physical film/paper natural HDR.

Decision:

- Keep: yes.
- Rename/relabel: yes, to `authored_profile_hdr` or `profile_authored_recovery`.
- Remove from default natural HDR path: yes.
- Downgrade to creative/authored mode: yes.

### 2. `modern_recovery_peak_budget`

Evidence:

- `profile_modern_recovery_budgeted_gain_ev()` computes `compressed_ev = max(scene_ev - profile_ev, 0)`.
- It multiplies that by `recovery_ratio`, highlight onset, and profile shoulder weight.
- `budget_recovery_gain_ev()` then scales the recovery so `p_ev + gain_ev` fits `target_peak_ev`, optionally hard-capping each sample.

Conclusion:

- `budget_recovery_gain_ev` is explicitly an authored scaling step.
- `target_peak_ev` specifies where highlights should land.
- If content has no highlight energy above the recovery knee, the current math produces no gain. But when highlight energy exists, the peak is authored toward the budget.
- If the scene has more real dynamic range than the budget allows, the budget compresses it.
- This should be named `budgeted_highlight_recovery` or `authored_highlight_recovery`, not natural HDR.

Decision:

- Keep: yes.
- Rename/relabel: yes.
- Remove from default natural HDR path: yes.
- Creative/authored: yes.

### 3. Generic HDR Mapping

Evidence:

- With `scene_luminance`, generic mapping calls `_graft_scene_luminance()`.
- Without `scene_luminance`, generic mapping derives `hdr_rgb` from the input image and optional fallback rolloff.
- `_content_headroom()` and `max_headroom` constrain the output.

Conclusion:

- With a real scene sidecar, generic mapping is content-derived but display constrained.
- Without a sidecar, the path is ambiguous. It is natural only if the input image itself is already real scene-linear HDR. Otherwise it can synthesize an HDR rendition from an SDR/preview look.
- Missing true HDR sidecar should not silently claim natural HDR.

Decision:

- Keep as compatibility/generic export.
- For `natural_scene_hdr`, require explicit scene/RAW/HDR evidence or refuse.

### 4. `film_scan_aware`

Evidence:

- `film_scan_aware` resolves `route="film_scan"` profiles and rejects mismatched routes.
- Raw negative scan diagnostic profiles are rejected.
- Negative film defaults to `positive_negative_scan`, which renders raw negative scan output into a positive scan profile before HDR gain.
- Film-scan profile sampling bypasses print/paper output; current GUI passes `paper=None` for film-scan-aware export.

Conclusion:

- Current source no longer uses raw negative luminance directly as the HDR profile curve.
- The route is still profile-shaped authored HDR. It does not measure scanner headroom, scanner multi-exposure data, or high-bit scanner scene energy.
- Paper/print parameters should not affect film-scan HDR. Current route intends to isolate them.
- If a negative HDR output appears inverted or semantically wrong, the likely issue is in positive negative-scan rendering/provenance or current look/source mismatch, not because the raw negative diagnostic profile is directly accepted.

Decision:

- Keep: yes.
- Rename/relabel: `film_scan_authored_hdr`.
- Future natural route: `natural_film_scan_hdr` only when scanner/multi-exposure/high-bit source evidence exists.

### 5. Color Recovery, Path-To-White, And Gamut

Evidence:

- `source_chroma` validates `scene_rgb` against `scene_luminance`, but then combines scene chroma with authored `h_profile`.
- `bounded_look_chroma` boosts authored look chroma in highlights.
- `path_to_white` pulls high-EV color toward luma.
- Gamut compression compresses chroma to fit Display P3/Rec.2020/working headroom.

Conclusion:

- `source_chroma` can preserve real scene chroma where sidecar and scene RGB agree, but luminance remains authored if `h_profile` is authored.
- `bounded_look_chroma` and path-to-white are creative rendering controls.
- Gamut mapping is a display/format constraint. It is necessary, but it changes the final color rendering and should not be treated as natural HDR generation.

Decision:

- Keep them as color-rendering controls.
- UI should group them under Authored / Creative HDR or Display Constraints.

### 6. Headroom Metadata

Evidence:

- Generic headroom comes from `_content_headroom(hdr_rgb)`, capped by `max_headroom`.
- Profile headroom is `min(max(content_headroom, profile_gain_headroom), safe_max_headroom)`.
- Gain-map metadata writes `HDRCapacityMax=headroom`.

Conclusion:

- In profile-aware mode, headroom can exceed absolute HDR pixel max because it also tracks gain-ratio capacity from `h_profile / s_profile`.
- This can be valid for gain-map reconstruction capacity, but it can overstate "actual pixel peak" if the UI/doc calls it content peak headroom.
- `max_headroom` and `safe_max_headroom` are export/rendering limits, not proof that content naturally has that much headroom.

Decision:

- Keep metadata.
- Add UI/docs distinction between absolute HDR pixel peak, gain-map ratio headroom, and user/export cap.

## Natural HDR Experiments

The repo now contains an untracked research-only Python probe, `tools/research_natural_hdr_film_sim.py`. I did not add it to git. It builds tiny scene-linear arrays and compares a strict "emit HDR only where scene luminance exceeds diffuse white" model with profile-shaped proxies for current `profile_aware` and `modern_recovery_peak_budget` equations.

Command:

```text
.venv/bin/python tools/research_natural_hdr_film_sim.py --format markdown
```

Output:

```text
| Experiment | Natural headroom | Current/probe headroom | Alignment | Verdict | Notes |
| --- | ---: | ---: | ---: | --- | --- |
| A_no_true_hdr_content | 1.0000 | n/a | 1.0000 | pass | Natural path keeps headroom at 1.0 when scene_luminance <= diffuse white. Any mode that emits >1.0 here should be labeled authored/synthetic. |
| B_real_highlight_content | 7.6695 | 1.3730 | 1.0000 | pass | Natural HDR energy is spatially aligned with scene values above diffuse white. |
| C_same_content_different_profiles | 7.6695 | 0.0000 | 1.0000 | authored_if_large_delta | profile-shaped headroom delta=0.0 Natural HDR distribution should be primarily content driven; profile changes may alter film rendering, not invent highlight locations. |
| D_same_profile_different_content | 7.6695 | 2.7508 | 1.0000 | inspect_budget_cap | modern low-dynamic headroom=None modern high-dynamic headroom=2.75080943107605 If different scenes collapse toward the same target EV, the mode is budgeted creative recovery. |
| E_exposure_print_exposure_adjustment | 7.8066 | 7.6695 | 1.0000 | diffuse_anchor_unchanged | Changing exposure/render intent changes the rendition but does not redefine physical diffuse white. Current hdr_render_ev should be treated as creative rendering, not as scene energy. |
| F_colored_highlights | 4.4951 | n/a | 0.9944 | separate_content_from_output_rendering | Scene chromaticity, film dye response, path-to-white, and gamut compression are separate decisions. source_chroma and bounded_look_chroma should be documented as output/rendering controls unless scene_rgb is validated. |
| G_diffuse_white_anchor | 3.8166 | 7.6695 | 1.0000 | anchor_changes_headroom | headroom diffuse_white=1.0: 7.6695 headroom diffuse_white=2.0: 3.8166 The anchor must be explicit or tagged heuristic; DNG WhiteLevel is not this anchor. |
```

Experiment interpretation:

- **A. No highlight content**: the research natural rule emits no HDR above SDR white. Current production `generic` and `profile_aware` should be considered synthetic/authored if they emit >1.0 in this case.
- **B. Real highlight content**: the natural model puts all HDR energy in real highlight regions. The profile-aware proxy is much lower headroom and profile-shaped, which supports "profile-authored recovery" rather than "natural scene HDR."
- **C. Same content, different profiles**: this simplified proxy showed no headroom delta for the chosen soft/hard synthetic profiles, so it is not proof of profile-driven inflation. The source-level evidence remains stronger: production `h_profile` is built from the selected curve profile and authored parameters.
- **D. Same profile, different content**: low dynamic content does not emit modern-budget headroom; high dynamic content does. That is useful content gating, but the target EV, ratio, slope windows, percentile, and hard cap still make it authored/budgeted.
- **E. Exposure / print exposure adjustment**: changing display/render intent changes rendition headroom without redefining physical scene energy. `hdr_render_ev` and look exposure belong in creative rendering, not natural provenance.
- **F. Colored highlights**: natural luminance provenance, scene chroma, path-to-white, and gamut compression are separate decisions. `source_chroma` and `bounded_look_chroma` are color rendering controls unless tied to validated scene RGB.
- **G. Diffuse white anchor**: changing diffuse white changes headroom. A natural HDR mode must record whether diffuse white is real metadata, a scene estimate, or a user-authored anchor.

RAW/DNG validation:

- The user-provided historical DNG archive exists and contains hundreds of DNG files. A bounded command against that folder was attempted:

```text
.venv/bin/python tools/validate_profile_aware_hdr_raw_samples.py --sample-dir /Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片/RAW_DNG_历史批量归档 --max-samples 2 --output /tmp/spektrafilm_hdr_profile_aware_raw_validation_history.md --diagnostic-scan-limit 8
```

It was stopped after roughly three minutes because it had only reached `Scanning RAW sensor stats 1/375` and had not written a partial report. I do not count that as validation evidence.

- Existing tracked current-doc evidence remains `docs/hdr_profile_aware_raw_validation.md`: four DNG samples passed sidecar finite/nonnegative checks, SDR preservation, Android/ISO metadata roundtrip, JPEG probe metadata/gain-map checks, and EXR metadata checks. The headroom range was `1.094..1.379`. This validates metadata plumbing and statistical profile conformance, but not physical/natural HDR or device display behavior.

## Recommended Architecture

### `natural_scene_hdr`

- Inputs allowed: RAW/scene-linear data, trusted HDR sidecar, existing gain map, scene RGB/luminance generated from traceable scene reconstruction, or multi-exposure fusion.
- No real HDR evidence: do not generate HDR. Export SDR or raise a clear error.
- Allowed constraints: reference white, display cap, gamut compression, tone mapping for target display, metadata encoding.
- Disallowed generation controls: profile target peak, min gain floor, recovery ratio, budgeted peak EV, paper profile rolloff as HDR creation.

### `authored_profile_hdr`

- Current `profile_aware` / `profile_preserving` belongs here.
- Preserve the authored SDR look and use film/paper profile curves to build high-light recovery.
- UI copy should say "authored profile recovery" or "creative profile HDR", not physical film/paper HDR.

### `budgeted_highlight_recovery`

- Current `modern_recovery_peak_budget` belongs here.
- Make `target EV`, `recovery ratio`, and `hard cap` explicit creative controls.
- Do not use budget target as natural headroom evidence.

### `film_scan_authored_hdr`

- Current `film_scan_aware` belongs here if it continues to use profile-aware target/gain.
- Add `natural_film_scan_hdr` only for real scanner dynamic range evidence, such as high-bit scanner output, multi-exposure scanner capture, or existing HDR scanner sidecars.

### `compatibility_gainmap_export`

- Responsible only for encoding an existing SDR/HDR pair into HEIC/JPEG gain-map format.
- Should not generate HDR content.
- Should report whether the pair came from `natural_scene_hdr`, authored profile recovery, or budgeted recovery.

## GUI Grouping Recommendation

### Natural HDR

- `natural_scene_hdr`
- Scene source/provenance: RAW, scene-linear EXR, existing gain map, scene sidecar.
- Reference white / diffuse white only as interpretation metadata.
- Strict option: "Refuse HDR when no real HDR evidence exists."

### Authored / Creative HDR

- `authored_profile_hdr`
- `budgeted_highlight_recovery`
- `film_scan_authored_hdr`
- Profile peak EV, recovery ratio, min gain, path-to-white, source chroma, bounded look chroma, paper/profile rolloff.

### Compatibility / Export Encoding

- HEIC/JPEG gain-map enablement.
- Gain-map RGB/luma mode.
- HEIC quality.
- Max export headroom and safe caps.
- EXR archive vs authored rendition.

## Verification Results

Requested commands:

```text
$ uv run --extra dev pytest tests/test_hdr_photo.py -q
146 passed in 0.70s

$ uv run --extra dev pytest tests/test_hdr_curve_profiles.py -q
35 passed in 1.15s

$ uv run --extra dev pytest tests/test_image_io_color_metadata.py -q
26 passed in 0.22s

$ uv run --extra dev pytest tests/gui/test_controller_output.py -q
21 passed in 1.17s

$ uv run --extra dev pytest tests/gui -q
176 passed in 3.74s
```

Note: an earlier invalid run executed `uv run --extra dev pytest tests/gui -q` concurrently with `.venv/bin/python -m compileall -q src tests` and produced transient controller-flow failures inconsistent with the checked-in source. Representative failing tests passed in isolation, and the standalone full GUI rerun passed. I therefore use the standalone result above.

Other requested gates:

```text
$ .venv/bin/python -m compileall -q src tests
Result: passed, exit 0.

$ git diff --check
Result: passed, exit 0.
```

## Final Confidence Loop

Question: do I have factual 100% confidence distinguishing content-derived HDR from authored HDR in the audited paths?

Answer: I have source-level and test-supported confidence for the current code classifications above. I do not have 100% device/display confidence because this audit did not render HEIC/JPEG gain maps in Apple Photos, Android Gallery, or an ISO 21496-1 decoder.

What is fully supported by current evidence:

- `profile_aware` and `profile_preserving` are not pure natural HDR. They are profile-authored recovery paths using `h_profile / s_profile`.
- `modern_recovery_peak_budget` is synthetic/budgeted recovery by design.
- `film_scan_aware` is positive film-scan profile-authored recovery, not natural scanner HDR.
- Generic sidecar mapping is content-derived but constrained and partially authored by display/rolloff choices.
- Scene-linear archive EXR can preserve real HDR pixels when the input is real scene-linear HDR.

Remaining uncertainty:

- External HEIC/Ultra HDR rendering behavior on actual devices.
- Whether future dynamic profile sampling includes look tweaks that should be considered creative provenance rather than physical profile provenance.
- Whether current GUI output encoding hardcoding blocks a clean `natural_scene_hdr` UX; this is adjacent to the audit and should be tested in a future implementation pass.

No production behavior was changed in this audit.
