# HDR RouteMaster Rewrite Implementation Report

Date: 2026-06-05

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

## 3. SDR Strict Equivalence

Focused tests passing:

```text
uv run --extra dev pytest tests/test_routemaster.py tests/test_hdr_routemaster_projection.py tests/test_hdr_routemaster_export.py tests/test_hdr_profile_cache.py -q
28 passed
```

The P0 tests assert:

- `scan_master()` plus `project_sdr_legacy()` equals legacy `scan()`.
- `SimulationPipeline.process(image)` equals
  `SimulationPipeline.process_master(image, hdr_mode="paper").sdr_legacy_rgb`
  for deterministic CPU print-scan route.
- film-scan SDR equivalence holds for positive/reversal film.
- `process_master()` does not mutate later `process()` output.

Manual diagnostic for the existing smoke failure showed the current split and
the legacy helper are identical for fast params:

```text
old center [0.46483247 0.4597758  0.46409895]
new center [0.46483247 0.4597758  0.46409895]
diff max 0.0
```

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
- uses `post_halation_y` as spatial HDR authority;
- preserves route-look chroma by default.

Tests passing:

- `test_light_table_does_not_respond_to_paper_params`
- `test_negative_film_light_table_requires_positive_rendering`
- `test_hdr_light_table_curve_monotonic`
- `test_route_look_chroma_preserved_by_default`
- `test_scene_rgb_is_auxiliary_not_default`

## 7. Idealized HDR Paper

Implemented in `src/spektrafilm/hdr/ideal_paper.py`.

Rules:

- accepts only `print_scan`;
- below paper white, preserves legacy SDR print look;
- above paper white, extends highlights from scene/material energy;
- responds to print exposure and paper profile through the print route;
- documents the mode as a counterfactual digital medium, not physical HDR
  paper.

Tests passing:

- `test_paper_mode_responds_to_print_exposure`
- `test_paper_mode_responds_to_paper_profile`
- `test_hdr_ideal_paper_curve_monotonic`
- `test_hdr_ideal_paper_curve_continuity`

## 8. Export Layer

Implemented in:

- `src/spektrafilm/utils/hdr_photo.py`
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

Real macOS pair smoke:

```text
uv run python - <<'PY'
...
save_hdr_photo_heic_from_pair(out, sdr, hdr, color_space="Display P3", headroom=2.0, quality=0.8)
PY

diagnostics ()
exists True size 2187
```

## 9. Legacy Modes

Implemented in `src/spektrafilm/hdr/routemaster_export.py`:

- `film_scan_aware` maps to `light_table` with `DeprecationWarning`.
- `profile_aware` maps to `paper` with `DeprecationWarning`.
- `generic` is legacy/internal and maps to `paper` with `DeprecationWarning`.

`src/spektrafilm/utils/hdr_photo.py` now marks `generic`, `profile_aware`, and
`film_scan_aware` as legacy compatibility modes.

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
uv run --extra dev pytest tests/test_routemaster.py tests/test_hdr_routemaster_projection.py tests/test_hdr_routemaster_export.py tests/test_hdr_profile_cache.py -q
28 passed

uv run --extra dev pytest tests/test_runtime_api.py -q
9 passed

uv run --extra dev pytest tests/test_hdr_photo.py tests/test_hdr_curve_profiles.py tests/test_gain_map.py tests/test_image_io_color_metadata.py -q
251 passed

uv run --extra dev pytest tests/gui/test_controller_output.py tests/gui/test_controller_runtime_module.py -q
35 passed

uv run --extra dev pytest tests/test_gpu_backend.py -q
21 passed

uv run --extra dev pytest tests/test_pipeline_smoke.py -q -k 'not midgray_input_produces_expected_output_values'
8 passed, 1 deselected

uv run python -m compileall -q src/spektrafilm tests/test_routemaster.py tests/test_hdr_routemaster_projection.py tests/test_hdr_routemaster_export.py tests/test_hdr_profile_cache.py
passed

git diff --check
passed
```

Known baseline debt:

```text
uv run --extra dev pytest tests/test_pipeline_smoke.py::test_midgray_input_produces_expected_output_values -q
failed
```

The same test also failed in a clean temporary `HEAD` worktree with the same
actual center value:

```text
actual [0.46483247 0.4597758  0.46409895]
expected [0.46369073 0.46374183 0.46358347]
```

This is not caused by the RouteMaster rewrite. The RouteMaster split was
separately checked against the current legacy helper at zero diff for fast
params.

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
- Migrate GUI export onto `export_hdr_heic_from_simulator()` after UX/state
  migration, while keeping the already implemented core encoder boundary.

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
- Route-look chroma is the default HDR color authority.
- The HEIC pair encoder is encode-only and passed both mock isolation tests and
  a real macOS smoke.
- Legacy HDR mode names are mapped with warnings.
- Related runtime, HDR, gain-map, profile, GUI controller, and backend tests
  passed, except for the clean-HEAD baseline smoke debt documented above.

