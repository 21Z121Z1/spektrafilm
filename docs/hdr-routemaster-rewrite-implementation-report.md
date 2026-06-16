# HDR RouteMaster Rewrite Implementation Report

Date: 2026-06-08

Final validation update: 2026-06-09

## 1. New Goal

Implement the Spektrafilm HDR RouteMaster rewrite:

```text
single full-resolution photographic route render
-> RouteMaster
-> SDR projection
-> HDR Light Table projection
-> Idealized HDR Paper projection
-> pre-rendered SDR/HDR pair export
```

The architecture must preserve legacy SDR output, derive SDR/HDR from the same
material state, expose only two public HDR modes, and keep HEIC saving as an
encode-only layer.

## 2. RouteMaster

Implemented in `src/spektrafilm/runtime/route_master.py`.

`RouteMaster` includes:

- `mode`
- `route_kind`
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

`ScanMasterResult` and `FilmingExposureResult` define the stage-level handoff
contracts.

Completion hardening added SDR output-transform diagnostics:

- `output_color_space`
- `output_cctf_encoding`
- `output_clip_min`
- `output_clip_max`

These flags let projection preserve already-linear SDR and decode legacy CCTF
SDR exactly once.

## 3. SDR Strict Equivalence

Focused tests passing:

```text
.venv/bin/python -m pytest tests/test_routemaster.py tests/test_hdr_routemaster_projection.py tests/test_hdr_routemaster_export.py tests/test_hdr_profile_cache.py -q
54 passed
```

The P0 tests assert:

- `scan_master()` plus `project_sdr_legacy()` equals legacy `scan()`.
- `SimulationPipeline.process(image)` equals
  `SimulationPipeline.process_master(image, hdr_mode="paper").sdr_legacy_rgb`
  for deterministic CPU print-scan route.
- film-scan SDR equivalence holds for positive/reversal film.
- `process_master()` does not mutate later `process()` output.
- strict SDR equivalence now explicitly covers deterministic grain, halation,
  camera diffusion, scanner blur/unsharp, output gamut compression, CCTF on/off,
  clip on/off, print-scan, positive/reversal film-scan, and negative film plus
  paper.

## 4. ScanningStage Boundary

Implemented in `src/spektrafilm/runtime/stages/scanning.py`.

New public methods:

- `scan_master(density_channels) -> ScanMasterResult`
- `project_sdr_legacy(scan_master) -> np.ndarray`

Legacy `scan()` delegates to:

```text
scan_master()
-> project_sdr_legacy()
```

The RouteMaster physical cut is before output gamut compression, scanner
blur/unsharp, CCTF, and clipping. These remain in the SDR projection to preserve
legacy behavior.

## 5. process_master

Implemented in:

- `src/spektrafilm/runtime/pipeline.py`
- `src/spektrafilm/runtime/process.py`
- `src/spektrafilm/runtime/api.py`
- `src/spektrafilm/runtime/__init__.py`
- `src/spektrafilm/__init__.py`

APIs:

- `SimulationPipeline.process_master(image, hdr_mode=...)`
- `Simulator.process_master(image, hdr_mode=...)`
- `simulate_master(image, params, hdr_mode=...)`

`process_master()` forces the route required by the requested HDR mode:

- `light_table` -> `io.scan_film=True`
- `paper` -> `io.scan_film=False`

Diagnostics include `route_render_count=1`.

## 6. HDR Light Table

Implemented in `src/spektrafilm/hdr/light_table.py`.

Rules:

- accepts only `film_scan`;
- ignores paper/print state by route construction;
- rejects diagnostic raw negative masters;
- allows negative film only after positive negative-scan rendering;
- derives positive negative-scan `route_linear_xyz` from the positive route
  RGB instead of aliasing RGB as XYZ;
- uses `post_halation_y` as spatial HDR authority;
- preserves route-look chroma by default.

Tests passing:

- `test_light_table_does_not_respond_to_paper_params`
- `test_negative_film_light_table_requires_positive_rendering`
- `test_negative_positive_scan_route_xyz_not_rgb_alias`
- `test_hdr_light_table_curve_monotonic`
- `test_route_look_chroma_preserved_by_default`
- `test_scene_rgb_is_auxiliary_not_default`

## 7. Idealized HDR Paper

Implemented in `src/spektrafilm/hdr/ideal_paper.py`.

Rules:

- accepts only `print_scan`;
- at or below the diffuse-white scene anchor, preserves legacy SDR print look;
- above the diffuse-white scene anchor, extends highlights from scene/material
  energy;
- uses `HDRProjectionConfig.diffuse_white_scene_anchor` as the paper join
  anchor; `HDRProjectionConfig.paper_white` remains only as a backward-compatible
  alias for old callers;
- applies `HDRProjectionConfig.output_diffuse_white` to the HDR extension above
  the authored SDR base before headroom and gain-map metadata are generated;
- uses `HDRProjectionConfig.headroom_percentile` in the luminance extension
  gain percentile;
- responds to print exposure and paper profile through the print route;
- documents the mode as a counterfactual digital medium, not physical HDR
  paper.

Tests passing:

- `test_paper_mode_responds_to_print_exposure`
- `test_paper_mode_responds_to_paper_profile`
- `test_hdr_ideal_paper_curve_monotonic`
- `test_hdr_ideal_paper_curve_continuity`
- `test_projection_respects_linear_sdr_without_cctf_decode`
- `test_projection_decodes_cctf_sdr_once`
- `test_paper_white_anchor_changes_hdr_join`
- `test_diffuse_white_scene_anchor_replaces_paper_white_alias`
- `test_projection_records_diffuse_white_semantics_in_diagnostics`
- `test_paper_mode_responds_to_camera_exposure`
- `test_paper_mode_responds_to_film_stock`
- `test_paper_mode_responds_to_enlarger_filter_color_adjustments`
- `test_paper_mode_responds_to_film_density_gamma`
- `test_paper_mode_responds_to_print_density_curve_morph`

## 8. Export Layer

Implemented in:

- `src/spektrafilm/utils/hdr_photo.py`
- `src/spektrafilm/utils/heif_iso21496.py`
- `src/spektrafilm/utils/gain_map_io.py`
- `src/spektrafilm/utils/gain_map_metadata.py`
- `src/spektrafilm/hdr/routemaster_export.py`

New encode-only API:

```python
save_hdr_photo_heic_from_pair(filename, sdr_rgb, hdr_rgb, ...)
```

It does not call:

- `Simulator`
- `prepare_hdr_photo_renditions`
- runtime profile sampling
- film/paper profile inspection
- HDR recovery logic

`export_hdr_heic_from_simulator()` calls `process_master()` exactly once, then
projects and saves the pair.

ISO/HEIC compliance hardening:

- `save_hdr_photo_heic_from_pair()` remains encode-only. It still does not call
  `Simulator`, `prepare_hdr_photo_renditions()`, runtime profile sampling,
  film/paper profiles, or HDR recovery.
- After CoreImage writes the HEIC, Spektrafilm validates the actual item graph
  and C.2 payload with `validate_heif_iso21496()`.
- Hard ISO errors delete the partial output and raise `HDRPhotoExportError`.
- The validator checks the `tmap` compatible brand, `tmap` item, single `dimg`
  reference with base/gain-map ordering, base `colr`, gain-map hidden flag,
  gain-map `nclx` colour primaries and transfer characteristics equal to `2`,
  tmap alternate `colr`, `ToneMapImage` version `0`, and parseable
  `GainMapMetadata`.
- `GainMapMetadata` validation now enforces finite values, version ordering,
  `minimum_version == 0`, non-negative and distinct HDR headrooms, channel count,
  `gain_map_max >= gain_map_min`, and `gamma > 0`.
- A live CoreImage output exposed a Mac-compatible but ISO-order-incompatible
  channel range payload where every channel appeared as `min > max`. The export
  path now performs a same-size repair only for that exact CoreImage pattern,
  then validates again. This keeps the CoreImage/Mac writer while making the
  emitted payload match ISO 21496-1 C.2.
- `save_gain_map_heif()` no longer fails open. If the ISOBMFF patcher is missing
  or post-patch ISO validation fails, the partial output is removed and the call
  raises.

Real macOS pair smoke is automated in
`tests/test_hdr_routemaster_export.py::test_coreimage_pair_export_writes_iso_tmap_and_is_mac_openable`.
On Darwin with `swift`/`xcrun` and `sips`, it writes a small RouteMaster-style
pre-rendered pair, validates the real ISO `tmap` graph, checks `sips`
openability, and checks Swift ImageIO can create a `CGImage`. On non-Darwin or
missing-tool environments it skips instead of weakening the non-GUI suite.

## 9. Legacy Modes

Implemented in `src/spektrafilm/hdr/routemaster_export.py`:

- `film_scan_aware` maps to `light_table` with `DeprecationWarning`.
- `profile_aware` maps to `paper` with `DeprecationWarning`.
- `generic` is legacy/internal and maps to `paper` with `DeprecationWarning`.

`src/spektrafilm/utils/hdr_photo.py` now marks `generic`, `profile_aware`, and
`film_scan_aware` as legacy compatibility modes.

GUI state/options now expose `paper` and `light_table` as public modes. Legacy
persisted values normalize as:

- `film_scan_aware` -> `light_table`
- `profile_aware` -> `paper`
- `generic` -> `paper`

## 10. Dynamic Profile Cache

Implemented in `src/spektrafilm/hdr/profile_cache.py`.

Tests passing:

- tone parameters change the key;
- spatial/random parameters do not change the key;
- paper tone/profile parameters are ignored for Light Table keys.

This is intentionally a key-layer implementation, not a blocking dependency for
P0/P1.

## 11. Verification

Passing commands:

```text
.venv/bin/python -m pytest tests/test_routemaster.py tests/test_hdr_routemaster_projection.py tests/test_hdr_routemaster_export.py tests/test_hdr_profile_cache.py -q
59 passed

.venv/bin/python -m pytest tests/test_gain_map.py tests/test_heif_iso21496.py tests/test_hdr_routemaster_export.py tests/test_hdr_photo.py tests/test_tier3_fixes.py -q
228 passed

.venv/bin/python -m pytest tests/test_gain_map.py tests/test_hdr_routemaster_export.py tests/test_hdr_photo.py tests/test_image_io_color_metadata.py -q
231 passed

.venv/bin/python -m pytest tests/test_heif_iso21496.py tests/test_tier3_fixes.py -q
23 passed

.venv/bin/python -m pytest --ignore=tests/gui -q
1495 passed, 7 skipped, 4 warnings

.venv/bin/python -m pytest --ignore=tests/gui -q
1495 passed, 7 skipped, 4 warnings

.venv/bin/python -m pytest tests/gui/test_controller_output.py tests/gui/test_state_bridge.py tests/gui/test_persistence.py -q
42 passed

git diff --check
passed
```

The final audit also investigated two earlier non-repeatable full-suite failures
seen before the two consecutive green full-suite runs:

- `tests/test_hdr_routemaster_projection.py::test_paper_projection_uses_safe_chemical_print_profile`
  failed once in the full run but passed in isolation, passed with the whole
  `test_hdr_routemaster_projection.py` file, and passed in the final RouteMaster
  focused command.
- `tests/test_backend_resident_p4_hdr_grain.py::test_grain_on_mlx_runtime_keeps_output_backend_resident`
  failed once in the full run but passed in isolation with residency event
  inspection, passed with the backend-resident file pair, and passed in both
  final full non-GUI runs.

No persistent implementation defect was found in either path after focused
reproduction attempts. The required completion gates are the current focused
commands above plus two consecutive full non-GUI passes.

The warnings are numeric warnings in existing autoexposure and gamut-compression
tests, not ISO/HEIC export failures:

- `tests/test_autoexposure.py::test_legacy_autoexposure_methods_remain_finite_on_small_images[matrix]`
- `tests/test_gamut_compression.py::TestBackendOutputGamutCompression::test_mlx_backend_matches_cpu_reference_without_full_frame_readback[cam16ucs-3e-06]`

Additional ISO/HEIC hardening tests:

- `tests/test_heif_iso21496.py`
- `tests/test_hdr_routemaster_export.py::test_coreimage_pair_export_writes_iso_tmap_and_is_mac_openable`
- `tests/test_hdr_routemaster_export.py::test_save_hdr_photo_heic_from_pair_fails_closed_on_iso_validation_error`
- `tests/test_hdr_photo.py::test_save_hdr_photo_heic_fails_closed_on_iso_validation_error`
- `tests/test_tier3_fixes.py::test_save_gain_map_heif_fails_closed_when_iso_patcher_missing`
- `tests/test_tier3_fixes.py::test_save_gain_map_heif_removes_partial_output_when_iso_validation_fails`

## 12. Future Work

Future work that does not block the current goal:

- Replace the first-pass monotonic HDR extension with calibrated photographic
  response curves sampled through the new route-aware cache.
- Add full GPU/MLX RouteMaster equivalence tests once the local backend timing
  and materialization policy are stable.
- Decide whether scanner blur/unsharp belongs physically in master or remains
  an SDR projection detail. It is intentionally left in projection for this P0
  rewrite to preserve SDR.
- Add optional debug-only spectral sidecars. They are not required for the MVP.
- Add external device/app rendering checks for Apple Photos / Android Gallery
  acceptance. Current automated validation covers local pair construction,
  gain-map metadata, encoder isolation, ISO `tmap` item-graph correctness, Mac
  `sips`/ImageIO openability, and non-GUI runtime behavior.

## 13. Confidence Statement

The current implementation reaches factual confidence for the requested core
goal because:

- RouteMaster exists and carries the required MVP fields.
- ScanningStage is split without changing current legacy SDR output under the
  focused equivalence tests and manual old/new helper comparison.
- `process_master()` renders one route and returns the shared SDR/material
  state.
- Both public HDR modes are implemented with route checks and behavior tests.
- Negative raw film-scan HDR output is rejected.
- Positive negative-scan Light Table uses a derived XYZ sidecar, not fake RGB
  values in the XYZ field.
- Public GUI mode state is reduced to `paper` and `light_table`, with legacy
  saved values normalized through compatibility aliases.
- Route-look chroma is the default HDR color authority.
- The HEIC pair encoder is encode-only and passed mock isolation tests plus a
  real macOS pair smoke with ISO `tmap` item-graph validation, C.2 payload
  validation, `sips` openability, and Swift ImageIO readback.
- Legacy HDR mode names are mapped with warnings.
- Related runtime, HDR, gain-map, profile, GUI controller, persistence, and
  non-GUI full-suite tests passed in this worktree.
