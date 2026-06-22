# HDR RouteMaster Rewrite Plan

Date: 2026-06-05

## 2026-06-08 Completion Audit Update

This pass is a RouteMaster hardening/completion pass, not a restart. The
current worktree already contains the core RouteMaster implementation and the
first round of docs/tests:

- `src/spektrafilm/runtime/route_master.py` defines `RouteMaster`,
  `ScanMasterResult`, `FilmingExposureResult`, `HDRMode`, and `RouteKind`.
- `src/spektrafilm/runtime/stages/scanning.py` already exposes
  `scan_master()`, `project_sdr_legacy()`, and the legacy `scan()` wrapper.
- `src/spektrafilm/runtime/stages/filming.py` already exposes
  `expose_with_metadata()` with `scene_y_raw` and `post_halation_y`.
- `src/spektrafilm/runtime/pipeline.py`,
  `src/spektrafilm/runtime/process.py`, `src/spektrafilm/runtime/api.py`,
  `src/spektrafilm/runtime/__init__.py`, and `src/spektrafilm/__init__.py`
  already expose `process_master()` / `simulate_master()` entry points.
- `src/spektrafilm/hdr/projection.py`,
  `src/spektrafilm/hdr/light_table.py`,
  `src/spektrafilm/hdr/ideal_paper.py`,
  `src/spektrafilm/hdr/routemaster_export.py`, and
  `src/spektrafilm/hdr/profile_cache.py` already contain the first projection,
  pair export, and route-profile-cache implementation.
- `tests/test_routemaster.py`, `tests/test_hdr_routemaster_projection.py`,
  `tests/test_hdr_routemaster_export.py`, and
  `tests/test_hdr_profile_cache.py` already cover the main P0/P1/P2/P3
  contracts.

Current non-mutating verification before this completion pass:

```text
.venv/bin/python -m pytest tests/test_routemaster.py tests/test_hdr_routemaster_projection.py tests/test_hdr_routemaster_export.py tests/test_hdr_profile_cache.py -q
29 passed

.venv/bin/python -m pytest tests/test_runtime_api.py tests/test_hdr_photo.py tests/test_hdr_curve_profiles.py tests/test_gain_map.py tests/test_image_io_color_metadata.py -q
260 passed

.venv/bin/python -m pytest tests/test_pipeline_smoke.py -q
9 passed

.venv/bin/python -m pytest --ignore=tests/gui -q
1408 passed, 7 skipped

git diff --check
passed
```

Remaining completion gaps identified by code audit:

- `RouteMaster.diagnostics` needs to carry the legacy SDR output-transform
  flags (`output_cctf_encoding`, `output_clip_min`, `output_clip_max`) so HDR
  projection can distinguish CCTF-encoded SDR from already-linear SDR.
- `spektrafilm.hdr.projection._sdr_rgb()` must decode legacy SDR only when the
  RouteMaster actually came from a CCTF-encoded SDR projection; already-linear
  SDR must pass through unchanged.
- `HDRProjectionConfig.paper_white` and `headroom_percentile` must affect the
  paper/HDR extension math instead of being ignored by the luminance extension
  helpers.
- Negative-film Light Table positive rendering must not fake
  `route_linear_xyz` by copying positive RGB. It must derive XYZ from the
  positive RGB route or explicitly mark XYZ as unavailable.
- P0 strict-equivalence tests need explicit matrix coverage for grain,
  halation, diffusion, scanner blur/unsharp, output gamut compression, CCTF,
  clip flags, positive/reversal film scan, and negative film plus paper.
- GUI/public HDR mode wiring still needs final cleanup so the public surface
  exposes `light_table` and `paper`, while legacy strings restore/export
  through compatibility aliases.

## New /goal

Spektrafilm HDR RouteMaster rewrite:

```text
single full-resolution photographic route render
-> RouteMaster
-> SDR projection
-> HDR Light Table projection
-> Idealized HDR Paper projection
-> pre-rendered SDR/HDR pair export
```

The goal is not a new HDR recovery hack. It is a strict SDR-preserving architecture where HDR is derived from the same high-information photographic material state as SDR. The save layer must encode already-rendered SDR/HDR pairs and must not re-run the simulator, re-sample full-resolution profiles, regenerate grain, or reconstruct HDR from the SDR look.

## Audit Summary

### Runtime and stage boundaries checked

- `src/spektrafilm/runtime/pipeline.py`
  - `SimulationPipeline.process()` delegates to `_process_result(..., include_metadata=False)`.
  - `SimulationPipeline.process_with_metadata()` returns `SimulationPipelineResult(image, hdr_scene_energy)`.
  - `_pipeline_scan_film()` runs `FilmingStage.expose()`, `FilmingStage.develop()`, then `ScanningStage.scan()`.
  - `_pipeline_print()` runs filming, printing, then `ScanningStage.scan()`.
  - `_preprocess_with_metadata()` currently captures `HDRSceneEnergyMetadata.scene_luminance` immediately after auto exposure and crop/rescale. This is too early for RouteMaster HDR because it does not include halation, diffusion, lens blur, grain, dye-cloud blur, print, or scanner route state.
- `src/spektrafilm/runtime/stages/filming.py`
  - `FilmingStage.expose()` converts RGB to film raw, applies exposure, highlight boost, diffusion, lens blur, halation, black/white exposure correction, then returns log exposure.
  - The correct `post_halation_y` extraction point is after `apply_halation_um()` and black/white filming exposure correction, before `safe_log10_backend()` / `np.log10(...)`.
- `src/spektrafilm/runtime/stages/printing.py`
  - `PrintingStage.expose()` handles film density to print log raw, print exposure, exposure compensation, preflash, and enlarger diffusion.
  - `PrintingStage.develop()` applies print density curves/morphs.
- `src/spektrafilm/runtime/stages/scanning.py`
  - `ScanningStage.scan()` currently combines density-to-spectral/XYZ/RGB, black/white correction, glare, output gamut compression, scanner blur/unsharp, CCTF encoding, and clipping.
  - This confirms the required split: `scan_master()` must expose physical route data, while `project_sdr_legacy()` must preserve the old output order exactly.
- `src/spektrafilm/runtime/services/color_reference.py`
  - Negative film scan black/white correction is intentionally bypassed.
  - Positive film and print black/white corrections depend on `ScanningStage.cmy_to_log_xyz`.
  - RouteMaster must keep this service contract intact.

### HDR utilities and export code checked

- `src/spektrafilm/utils/hdr_photo.py`
  - `HDRPhotoMapping` currently exposes `generic`, `profile_aware`, and `film_scan_aware`.
  - `prepare_hdr_photo_renditions()` still creates SDR/HDR pairs inside the save utility, including profile sampling, scene luminance graft, color recovery, gamut compression, and headroom decisions.
  - `_prepare_curve_profile_renditions()` contains useful algorithms for positive negative scan rendering validation, profile monotonicity, profile-preserving curves, route-aware profile checks, route-look gain, and path-to-white behavior.
  - `save_hdr_photo_heic()` currently calls `prepare_hdr_photo_renditions()` and then writes payloads through the Swift CoreImage helper. This is the layer that must be decoupled.
  - `encode_gain_map_log2()`, `build_iso_21496_1_gain_map_metadata()`, and `validate_gain_map()` are reusable format/gain-map helpers.
- `src/spektrafilm/utils/hdr_curve_profiles.py`
  - `HDRCurveProfile` already has `route`, `profile_kind`, `negative_scan_render`, and safe profile metadata.
  - `sample_runtime_curve_profile()` and `sample_runtime_film_scan_curve_profile()` are reusable for small ramp cache/profile sampling, but must not be called from the pair encoder.
  - `render_negative_scan_positive_rgb()` is the existing migration path for negative film light-table output when the raw scan is a decreasing diagnostic.
- `src/spektrafilm/utils/io.py`
  - `save_image_oiio()` gates HEIC/HEIF HDR export behind explicit linear unclipped `ColorEncoding`.
  - Non-HEIC save paths return normal SDR output behavior.
  - HEIC currently forwards `hdr_mapping_kwargs`, `scene_luminance`, and `scene_rgb` to `save_hdr_photo_heic()`.

### Profiles and data checked

- `src/spektrafilm/data/profiles/`
  - Film and paper stock data are route inputs. Paper profiles must not affect HDR Light Table.
- `src/spektrafilm/data/hdr_curve_profiles/`
  - Existing v2 curve database and samples are useful for compatibility and dynamic small-ramp profile fallbacks.
  - Existing README already distinguishes film-scan route profiles, but RouteMaster docs must supersede "profile-aware HDR" as the primary public architecture.

### Tests checked for migration

- `tests/test_runtime_api.py`
  - Existing public runtime wrapper tests cover `Simulator.process()`, `process_with_metadata()`, and serial backend delegation.
- `tests/test_pipeline_smoke.py`
  - Existing smoke tests cover print/scan route distinction, LUT parity, auto exposure, and stable SDR output.
- `tests/test_hdr_photo.py`
  - Existing HDR tests cover old mappings, scene luminance graft, profile-aware behavior, film-scan-aware route checks, negative-film positive rendering, source chroma, path-to-white, gamut compression, and HEIC command payload creation.
- `tests/test_hdr_curve_profiles.py`
  - Existing tests cover curve profile schema, runtime sampling, film-scan route isolation, negative raw diagnostics, negative-to-positive scan rendering, and positive/reversal scan behavior.
- `tests/test_gain_map.py`
  - Existing tests cover gain map metadata and application. New high-frequency cleanliness tests should live here or in a new RouteMaster HDR test module.
- `tests/test_image_io_color_metadata.py` and GUI tests
  - Existing tests cover save dispatch and GUI HDR export wiring. RouteMaster pair export should add narrower unit tests first and only migrate GUI once the core path is stable.

### Existing docs checked

- `docs/dev/2026-06-03-hdr-system-audit-report.md`
  - Confirms the current implementation bug focus and the existing verification stack.
- `docs/dev/2026-06-03-hdr-naturalness-audit.md`
  - Classifies current `profile_aware`, `modern_recovery_peak_budget`, and `film_scan_aware` as authored/profile-shaped HDR, not physical natural HDR.
- `docs/profile-aware-hdr-audit-report.md`
  - Documents current profile-aware behavior as authored HDR recovery and warns against describing it as physical HDR paper.
- `docs/film-scan-aware-negative-positive-plan.md`
  - Documents the required negative-film raw diagnostic versus positive negative-scan route split.
- `docs/hdr-film-scan-aware.md`
  - Compatibility entry point for current film-scan-aware HDR docs.

### External references checked

- Apple Core Image exposes an auxiliary HDR gain map option (`CIImageOption.auxiliaryHDRGainMap`) and Apple HDR sample docs describe reading and writing HDR/gain-map imagery through Core Image and ImageIO. This supports treating the encoder as a carrier for an SDR/HDR pair, not as the place where photographic HDR semantics should be created.
- Android Ultra HDR v1.1 describes a backward-compatible SDR primary plus logarithmic gain map secondary image, GContainer metadata, and ISO 21496-1 compatibility. It emphasizes pair/metadata encoding and decoding.
- ISO 21496-1:2025 defines gain map metadata for dynamic range conversion between two image representations. This supports keeping metadata/encoding separate from RouteMaster projection.

## RouteMaster Architecture

Add `src/spektrafilm/runtime/route_master.py` with:

- `RouteMaster`
  - `mode`: `"light_table"` or `"paper"`
  - `route_kind`: `"film_scan"` or `"print_scan"`
  - `route_linear_rgb`
  - `route_linear_xyz`
  - `route_luminance_y`
  - `sdr_legacy_rgb`
  - `scene_y_raw`
  - `post_halation_y`
  - `density_cmy`
  - `route_look_chroma`
  - `material_detail_y`
  - `diagnostics`
- `ScanMasterResult`
  - `route_linear_rgb`
  - `route_linear_xyz`
  - `route_luminance_y`
  - `density_cmy`
  - `diagnostics`

MVP storage will be full-resolution RGB/XYZ/Y/density sidecars only. Full-resolution spectral density is explicitly future/debug work.

RouteMaster construction:

```text
preprocess
-> filming.expose_with_metadata
-> filming.develop
-> optional printing.expose/develop
-> scanning.scan_master
-> scanning.project_sdr_legacy
-> RouteMaster
```

For P0, `project_sdr_legacy(scan_master)` must reproduce the old `scan()` result. The first implementation will keep output gamut compression, scanner blur/unsharp, CCTF, and clip in the projection path to preserve SDR. A later refactor may reclassify scanner optical effects more cleanly after proof.

## ScanningStage Split

Add:

- `ScanningStage.scan_master(density_channels) -> ScanMasterResult`
- `ScanningStage.project_sdr_legacy(scan_master) -> np.ndarray`
- Keep `ScanningStage.scan(density_channels) -> np.ndarray`

Behavior:

- `scan()` becomes a wrapper:

```text
scan_master(density_channels)
-> project_sdr_legacy(scan_master)
```

- `scan_master()` stops before output transform:
  - density channels
  - spectral density / density-to-light
  - XYZ
  - black/white XYZ correction
  - glare
  - linear output RGB
  - route luminance Y
- `project_sdr_legacy()` applies the old projection sequence:
  - output gamut compression
  - scanner blur/unsharp
  - CCTF encoding
  - min/max clipping

This preserves the current old behavior, including the current placement of output gamut compression before scanner blur/unsharp.

## SDR Strict Equivalence Strategy

P0 blocks all P1/P2 work until proven.

Tests:

- `test_scan_master_project_sdr_legacy_equivalence`
- `test_routemaster_sdr_equivalence_film_scan`
- `test_routemaster_sdr_equivalence_print_scan`
- `test_process_master_does_not_change_process_output`

CPU target:

- `np.testing.assert_allclose(..., atol=1e-9, rtol=0)` for deterministic CPU float64 paths.
- If exact bit equality holds, assert it in focused tests.

GPU/MLX target:

- Use the existing `_gpu_validation_tolerance()` rules from `SimulationPipeline`.
- For this first RouteMaster rewrite, main tests will default to CPU to avoid conflating architecture correctness with backend parity. GPU parity remains a targeted follow-up if the local MLX environment is stable.

Coverage matrix:

- print scan route
- film scan route
- negative film plus paper
- positive/reversal film scan
- grain enabled
- halation enabled
- camera diffusion enabled
- scanner blur/unsharp enabled
- output gamut compression enabled
- CCTF and clip settings toggled

## HDR Light Table Strategy

Add `src/spektrafilm/hdr/light_table.py`.

Public API:

```python
project_hdr_light_table(master: RouteMaster, config: HDRProjectionConfig) -> HDRProjectionResult
```

Rules:

- Accept only `master.route_kind == "film_scan"`.
- Do not read paper profile, print exposure, preflash, enlarger filters, paper density curve, paper white, paper glare, or paper texture.
- Use `scene_y_raw` as scene authority and `post_halation_y` as spatial highlight authority.
- Use `route_luminance_y` and `route_look_chroma` as route look/material anchors.
- Negative film must have a positive output look before HDR projection. Raw negative scan masters will be rejected unless diagnostics explicitly identify a positive negative-scan rendering.
- Default color uses route-look chroma, not `scene_rgb`.
- Path-to-white is weak to moderate and route-aware.

The initial projection will use a monotonic HDR luminance extension based on:

```text
scene/post-halation authority
-> normalized relative headroom
-> bounded route/material detail
-> route look chroma
```

This will intentionally reuse only low-risk math from the current HDR code: monotonic shaping, content headroom, route-aware chroma scaling, and gain map metadata.

## Idealized HDR Paper Strategy

Add `src/spektrafilm/hdr/ideal_paper.py`.

Public API:

```python
project_hdr_ideal_paper(master: RouteMaster, config: HDRProjectionConfig) -> HDRProjectionResult
```

Rules:

- Accept only `master.route_kind == "print_scan"`.
- Paper white and below must preserve the legacy SDR print look.
- Above paper white, extend highlights with scene/material-derived energy from `scene_y_raw`, `post_halation_y`, and route energy.
- Print exposure and paper profile are already baked into RouteMaster through the print route; tests will prove that changing print exposure or paper profile changes paper HDR output.
- The docs must state that real photographic paper is a reflective medium and cannot physically carry HDR display headroom. "Idealized HDR Paper" is a counterfactual digital medium.

Curve contract:

- Monotonic.
- Continuous at the join point.
- Prefer C1 continuity by using smoothstep/blended derivatives rather than a hard graft.
- No discontinuity between SDR paper curve and HDR extension.

## Export and HEIC Save Decoupling

Add or modify in `src/spektrafilm/utils/hdr_photo.py`:

```python
save_hdr_photo_heic_from_pair(
    filename,
    sdr_rgb,
    hdr_rgb,
    *,
    color_space,
    headroom=None,
    quality=0.95,
    metadata=None,
    gain_map_mode="rgb",
)
```

Rules:

- Validate finite same-shape RGB pairs.
- Derive headroom from HDR payload if omitted.
- Encode pair through the existing Swift CoreImage helper.
- Do not call `Simulator`.
- Do not call `prepare_hdr_photo_renditions()`.
- Do not sample runtime profiles.
- Do not access film/paper profiles.
- Do not perform HDR recovery.

Keep `save_hdr_photo_heic()` and `prepare_hdr_photo_renditions()` as legacy compatibility paths, with deprecation warnings or docstrings marking `generic`, `profile_aware`, `film_scan_aware`, `modern_recovery_peak_budget`, `profile_preserving`, and `source_chroma` as legacy/internal or compatibility modes.

Add `src/spektrafilm/hdr/routemaster_export.py`:

```text
master = simulator.process_master(image, hdr_mode)
projection = project_hdr(master, config)
save_hdr_photo_heic_from_pair(path, projection.sdr_rgb, projection.hdr_rgb, ...)
```

Instrumentation:

- RouteMaster pipeline diagnostics include scan count / route render count.
- Export tests monkeypatch stages/encoder to prove only one full-resolution route render.

## Dynamic Profile Cache Strategy

Add `src/spektrafilm/hdr/profile_cache.py`.

The cache is not allowed to block P0/P1. It is allowed to wrap the existing small-ramp samplers:

- `sample_runtime_curve_profile()`
- `sample_runtime_film_scan_curve_profile()`

Cache key includes deterministic tone baseline parameters:

- `hdr_mode`
- `route_kind`
- film stock
- paper stock for paper mode
- camera exposure compensation
- fixed auto exposure EV if present
- film density curve gamma
- print density curve morph
- print exposure for paper mode
- enlarger neutral filters for paper mode
- preflash for paper mode
- scanner black/white correction
- viewing/scanner illuminant
- paper white anchor policy

Cache key excludes:

- grain random field
- halation image content
- diffusion image content
- lens blur image content
- scanner blur image content
- local image-dependent effects

Those excluded values enter the HDR projection only through `RouteMaster` fields such as `post_halation_y`, `route_luminance_y`, and `material_detail_y`.

## Test Plan

New tests:

- `tests/test_routemaster.py`
  - `test_routemaster_fields_complete`
  - `test_routemaster_sdr_equivalence_film_scan`
  - `test_routemaster_sdr_equivalence_print_scan`
  - `test_scan_master_project_sdr_legacy_equivalence`
  - `test_process_master_does_not_change_process_output`
  - `test_post_halation_y_shape_and_finiteness`
  - `test_density_cmy_sidecar_shape_and_finiteness`
- `tests/test_hdr_routemaster_projection.py`
  - `test_light_table_does_not_respond_to_paper_params`
  - `test_paper_mode_responds_to_print_exposure`
  - `test_paper_mode_responds_to_paper_profile`
  - `test_negative_film_light_table_requires_positive_rendering`
  - `test_hdr_light_table_curve_monotonic`
  - `test_hdr_ideal_paper_curve_monotonic`
  - `test_hdr_ideal_paper_curve_continuity`
  - `test_route_look_chroma_preserved_by_default`
  - `test_scene_rgb_is_auxiliary_not_default`
  - `test_gain_map_high_frequency_cleanliness`
  - `test_grain_shared_between_sdr_and_hdr_projection`
- `tests/test_hdr_routemaster_export.py`
  - `test_save_hdr_photo_heic_from_pair_does_not_call_simulator`
  - `test_export_route_master_single_full_res_render`
  - `test_no_duplicate_scan_when_exporting_hdr`
  - `test_heic_encoder_accepts_pre_rendered_pair`
  - `test_gain_map_metadata_valid`
  - `test_legacy_profile_aware_alias_warns_or_maps_to_paper`
  - `test_legacy_film_scan_aware_alias_warns_or_maps_to_light_table`
- `tests/test_hdr_profile_cache.py`
  - `test_dynamic_profile_cache_key_changes_for_tone_params`
  - `test_dynamic_profile_cache_key_ignores_spatial_random_params`

Existing suites to run after implementation:

```bash
uv run --extra dev pytest tests/test_routemaster.py tests/test_hdr_routemaster_projection.py tests/test_hdr_routemaster_export.py tests/test_hdr_profile_cache.py -q
uv run --extra dev pytest tests/test_runtime_api.py tests/test_pipeline_smoke.py -q
uv run --extra dev pytest tests/test_hdr_photo.py tests/test_hdr_curve_profiles.py tests/test_gain_map.py tests/test_image_io_color_metadata.py -q
uv run --extra dev pytest tests/gui/test_controller_output.py -q
uv run python -m compileall -q src/spektrafilm tests
git diff --check
```

If HEIC platform tools are available:

```bash
uv run python - <<'PY'
# small RouteMaster pair HEIC smoke using save_hdr_photo_heic_from_pair
PY
```

Then inspect with `file`, `sips`, `mdls`, and `strings` for HEIC/tmap/auxiliary gain-map markers, as used in the prior HDR export verification.

## Risks, Unknowns, and Rollback

Risks:

- Moving output gamut compression or scanner blur across the master/projection boundary could change SDR. Mitigation: keep the legacy projection order in `project_sdr_legacy()` for P0.
- Negative film light-table semantics can be wrong if raw negative scan is projected as HDR. Mitigation: reject raw negative diagnostics; require positive negative-scan diagnostics.
- GPU backend array materialization can hide extra CPU transfers. Mitigation: keep backend arrays through stage work where possible and materialize once in RouteMaster construction; record diagnostics when materialization is forced.
- Grain/high-frequency structure can leak into gain maps if SDR/HDR diverge. Mitigation: both SDR and HDR projections use the same RouteMaster. Add high-frequency cleanliness tests; only then add low/high frequency separation if evidence requires it.
- Save-layer compatibility can regress GUI export. Mitigation: keep legacy save APIs and add new pair API separately, then migrate explicit RouteMaster export flow.

Unknowns:

- Apple Photos/device-side HDR activation cannot be fully proven by local Python tests. It remains a manual/device validation boundary.
- Full MLX/GPU RouteMaster parity may depend on backend stability. P0 correctness will be proven on CPU first and GPU tolerance will use existing runtime validation rules.
- Idealized HDR Paper highlight extension is an authored counterfactual medium. The implementation must be honest about that in docs and tests.

Rollback:

- `ScanningStage.scan()` remains a compatibility wrapper, so ordinary process/export rollback is to switch callers back to `scan()`.
- `save_hdr_photo_heic()` remains legacy, so HEIC export rollback is to route GUI through the existing compatibility path.
- New files are isolated under `src/spektrafilm/runtime/route_master.py` and `src/spektrafilm/hdr/`, making a surgical revert possible.

## Phased Implementation Checklist

### P0: RouteMaster and strict SDR

- Add failing RouteMaster field and SDR equivalence tests.
- Add `ScanMasterResult` and `RouteMaster`.
- Split `ScanningStage.scan_master()` and `project_sdr_legacy()`.
- Keep `scan()` behavior unchanged.
- Add `FilmingStage.expose_with_metadata()` or equivalent internal method to return log raw plus `scene_y_raw` and `post_halation_y`.
- Add `SimulationPipeline.process_master()` and `Simulator.process_master()`.
- Materialize RouteMaster fields once and record diagnostics.
- Prove `process(image) == process_master(image).sdr_legacy_rgb`.

### P1: HDR projections

- Add `HDRProjectionConfig` and `HDRProjectionResult`.
- Add `project_hdr_light_table()`.
- Add `project_hdr_ideal_paper()`.
- Add route-look chroma helper and default color policy.
- Add monotonic and continuity tests.
- Add paper-parameter isolation/responsiveness tests.
- Add negative-film raw scan rejection tests.

### P2: Pair export

- Add `save_hdr_photo_heic_from_pair()`.
- Add `render_hdr_pair_from_master()` / `export_route_master_hdr_heic()` in `src/spektrafilm/hdr/routemaster_export.py`.
- Add no simulator/no duplicate scan tests.
- Keep legacy save path intact but marked legacy.

### P3: Dynamic profile cache

- Add cache key dataclass/helper.
- Wrap small-ramp profile sampling only.
- Add key include/exclude tests.
- Keep full-resolution image-dependent fields outside the cache key.

### P4: Legacy cleanup and docs

- Mark `generic`, `profile_aware`, `film_scan_aware`, `modern_recovery_peak_budget`, `profile_preserving`, and `source_chroma` as legacy/internal compatibility concepts.
- Add `docs/hdr-routemaster-rewrite.md`.
- Add `docs/hdr-modes.md`.
- Add `docs/hdr-export-pipeline.md`.
- Add `docs/hdr-routemaster-rewrite-implementation-report.md`.

## Completion Bar

Before marking this goal complete, the implementation report must answer:

- RouteMaster implemented and complete?
- SDR strict equivalence proven?
- ScanningStage output transform split without SDR change?
- `process_master()` performs one full-resolution route render?
- HDR Light Table implemented and isolated from paper params?
- Idealized HDR Paper implemented and responsive to paper/print route params?
- Save layer decoupled into pre-rendered pair encoding?
- Legacy HDR modes marked and compatibility preserved?
- Tests passed, failed, or skipped with concrete commands and reasons?
- Remaining future work does not invalidate the current goal?

## 2026-06-08 ISO 21496-1 / HEIC Audit Addendum

This addendum was written before the ISO/HEIC compliance hardening edits. The
authoritative standard references checked for this pass are the local files in
`docs/reference/standards/`.
The standards README says to search by clause or keyword instead of loading the
full standards into context.

Files and clauses checked:

- `ISO_21496-1_2025_2053497278426656768.md`
  - 4.2: gain-map dimensions can differ from the baseline only when metadata
    and resampling rules make that explicit.
  - 4.3 and 5.2.4: gain-map component count is either one achromatic component
    or three RGB components, and metadata must say which.
  - 4.4: gain-map quantization should be at least eight bits per component.
  - 4.5: gain-map orientation must match the baseline.
  - 5.2.5.2 through 5.2.5.6: per-channel min/max/offset/gamma fields must be
    valid; max must be greater than or equal to min; gamma must be positive.
  - 5.2.6 and 5.2.7: baseline and alternate HDR headroom are explicit
    metadata and alternate headroom must differ from baseline headroom.
  - 5.3.2 through 5.3.4: baseline colorimetry is required, alternate
    colorimetry should be present, and the gain-map application primaries flag
    identifies whether baseline or alternate primaries are used.
  - 6.2.1 through 6.2.2: stored gain maps are normalized/gamma-coded and
    resampled before application if dimensions differ.
  - C.2: `GainMapMetadata` is a big-endian binary payload, with nonzero
    denominators and RGB channel order when multichannel.
  - C.3: file formats supporting ISO 21496-1 gain maps must define
    identification, baseline image, gain-map pixel data, binary metadata
    storage, baseline color space, and alternate color space.
- `ISO_IEC_23008-12_2025_Amd_1_2025_2053793830344998912.md`
  - 6.6.2.4: a `tmap` derived image item uses exactly two `dimg` inputs; the
    first is the base image and the second is the gain-map image.
  - 6.6.2.4: the base item must have `colr`; the gain-map input item must have
    an `nclx` `colr` with colour primaries and transfer characteristics set to
    `2`; the `tmap` derived item must have alternate-image `colr`.
  - 6.6.2.4: the gain-map input item should be hidden.
  - 6.6.2.4: the `ToneMapImage` payload version must be `0`, followed by the
    ISO 21496-1 binary `GainMapMetadata` payload.
  - 10.2.6: files containing a tone-map derived item must include the `tmap`
    compatible brand, and a file advertising `tmap` must contain at least one
    tone-map derived item.
  - Annex J.7: the example uses `heic` major brand, `tmap/mif1/heic`
    compatible brands, `dimg` links, `colr` properties, and an `altr` group for
    backward compatibility.

Current Spektrafilm evidence before this hardening pass:

- `src/spektrafilm/data/macos/hdr_heif_encoder.swift` writes the RouteMaster
  pre-rendered SDR/HDR pair through CoreImage HEIF representation options. A
  live temporary smoke on this machine produced a Mac-openable HEIC with
  `ftyp` compatible brands `mif1`, `tmap`, `MiHE`, `miaf`, `MiHB`, `heic`.
- The same live smoke parsed as a real `tmap` item graph: `tmap` item `4`,
  `dimg` inputs `[1, 3]`, hidden gain-map auxiliary item, `tmap` `nclx`
  BT.2020/PQ `colr`, and a 142-byte `ToneMapImage` payload whose first byte is
  version `0` and whose remaining 141 bytes parse as three-channel ISO
  `GainMapMetadata`.
- `src/spektrafilm/utils/gain_map_metadata.py` already implements the C.2
  binary payload shape, but validation is too weak for ISO invariants.
- `src/spektrafilm/utils/gain_map_io.py::save_gain_map_heif()` currently
  writes a dual-image HEIF and then tries to call a missing `_isobmff_patch`
  module. When the patch path fails, it logs and leaves a non-`tmap` HEIF. That
  is not acceptable for a function claiming ISO 21496-1 HEIF output.
- Existing documentation only records `strings`-level markers for HEIC smoke.
  That is too weak; completion evidence must include an item graph and metadata
  payload validator plus Apple-native openability gates.

Hardening strategy for this pass:

- Keep CoreImage as the default RouteMaster HEIC writer because it is the
  strongest Mac-openable path and already emits the expected ISO `tmap` family
  in live smoke tests.
- Add a local pure-Python HEIF ISO validator under `src/spektrafilm/utils/` so
  Spektrafilm can prove the `tmap` graph, color properties, hidden gain-map
  item, and binary metadata payload after encode.
- Call that validator from `save_hdr_photo_heic_from_pair()` after CoreImage
  returns. If hard ISO errors are present, raise `HDRPhotoExportError`.
- Strengthen `GainMapMetadata` validation for finite values, version ordering,
  headroom ordering/non-equality, nonnegative unsigned headrooms, max/min
  ordering, and positive gamma.
- Change `save_gain_map_heif()` to fail closed: if patching is unavailable or
  validation fails, remove partial output and raise instead of silently leaving
  a noncompliant HEIF.
- Update `docs/hdr-export-pipeline.md` and
  `docs/hdr-routemaster-rewrite-implementation-report.md` from marker-only
  evidence to ISO item-graph plus Mac ImageIO/sips evidence. Apple Photos visual
  HDR activation remains a manual/device boundary separate from local ISO and
  Mac-openability validation.

Post-hardening note: live CoreImage output was confirmed to write a valid
Mac-openable `tmap` item graph, but the first two C.2 per-channel range fields
can appear in the opposite order from the local ISO 21496-1 C.2 reference. The
implementation now performs a same-size repair only for that exact all-channel
`min > max` pattern, then runs the normal hard validator. Other malformed HEIF
outputs still fail closed and are deleted.
