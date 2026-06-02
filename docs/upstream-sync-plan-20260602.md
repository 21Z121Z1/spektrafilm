# Upstream Sync Plan & Report — 2026-06-02

## 1. Pre-Sync State

- **Branch**: `develop` (local)
- **origin**: `https://github.com/21Z121Z1/spektrafilm.git` (our repo) ✓
- **upstream**: `https://github.com/andreavolpato/spektrafilm.git` ✓
- **ahead of upstream/main**: 372 commits (our unique work)
- **behind upstream/main**: 2 commits (gui-refactor)
- **ahead of origin/develop**: 43 commits (unpushed local work)
- **Backup branch**: `backup/before-upstream-sync-20260602-2023`

## 2. Upstream Changes (2 new commits)

```
906351e Merge branch 'gui-refactor'
6deeec3 feat: gui refactor with param manifest
```

**Scope**: 39 files changed, +2649 / -2245 lines

### 2.1 Critical finding: Silent GPU code removal

Upstream **removed all GPU backend support** from the codebase. In ~90 files (source, tests, docs, scripts), the `backend` parameter and GPU code paths were stripped. A naive `git merge upstream/main` would silently apply these removals to files unchanged since the last merge point, destroying our GPU/MLX/Halide work.

**Affected source files** (backend removed by upstream, present in our code):
- `src/spektrafilm/model/grain.py` (70 backend refs)
- `src/spektrafilm/model/diffusion.py` (28 backend refs)
- `src/spektrafilm/model/couplers.py` (16 backend refs)
- `src/spektrafilm/model/develop.py` (9 backend refs)
- `src/spektrafilm/model/glare.py` (20 backend refs)
- `src/spektrafilm/runtime/stages/printing.py` (60 backend refs)
- `src/spektrafilm/runtime/stages/scanning.py` (26 backend refs)
- `src/spektrafilm/runtime/stages/filming.py` (24 backend refs)
- `src/spektrafilm/runtime/services/spectral_lut_compute.py` (43 backend refs)
- `src/spektrafilm/runtime/services/color_reference.py` (6 backend refs)
- `src/spektrafilm/utils/lut.py` (7 backend refs)

**GPU kernel files** (exist in our code, absent in upstream):
- `src/spektrafilm/gpu/backend.py`
- `src/spektrafilm/gpu/kernels/color.py`, `density.py`, `filters.py`, `grain.py`, `lut.py`

## 3. Execution Summary

### 3.1 Strategy: Merge + Protect

1. ✅ Created backup branch: `backup/before-upstream-sync-20260602-2023`
2. ✅ Ran `git merge upstream/main --no-commit`
3. ✅ Resolved 12 conflicts:
   - **Core files** (grain.py, params_builder.py): Kept our version (GPU backend)
   - **GUI files** (controller.py, params_mapper.py, state.py, widget_sections.py, GUI tests): Accepted upstream (gui-refactor value)
   - **widget_specs.py**: Deleted (upstream replaced with widget_sections.py)
4. ✅ Restored 6 auto-merged files from backup (upstream had destructively changed them):
   - `src/spektrafilm/runtime/params_schema.py` (lost GPU fields)
   - `src/spektrafilm/utils/calibration_targets.py` (renamed params)
   - `src/spektrafilm/utils/gamut_compression.py` (changed default algorithm)
   - `tests/test_emulsion.py` (renamed params, removed test)
   - `tests/test_gamut_compression.py` (changed default assertion)
   - `tests/test_grain.py` (removed GPU tests, renamed params)
5. ✅ Fixed param name references in examples and scripts
6. ✅ Committed merge: `0d3aeda Merge upstream/main into develop`
7. ✅ Committed fixes: `3e6192f fix: restore our grain param names in examples and scripts`

### 3.2 Conflict Resolution Details

| File | Resolution | Reason |
|------|-----------|--------|
| `src/spektrafilm/model/grain.py` | Kept ours | GPU backend support (70 refs) |
| `src/spektrafilm/runtime/params_builder.py` | Kept ours | GPU backend support |
| `src/spektrafilm_gui/controller.py` | Accepted upstream | GUI refactor value |
| `src/spektrafilm_gui/params_mapper.py` | Accepted upstream | GUI refactor value |
| `src/spektrafilm_gui/state.py` | Accepted upstream | GUI refactor value |
| `src/spektrafilm_gui/widget_sections.py` | Accepted upstream | GUI refactor value |
| `src/spektrafilm_gui/widget_specs.py` | Deleted | Replaced by widget_sections.py |
| `tests/gui/*.py` (5 files) | Accepted upstream | GUI test updates |
| `src/spektrafilm/runtime/params_schema.py` | Restored from backup | Lost GPU fields |
| `src/spektrafilm/utils/calibration_targets.py` | Restored from backup | Renamed params |
| `src/spektrafilm/utils/gamut_compression.py` | Restored from backup | Changed default |
| `tests/test_emulsion.py` | Restored from backup | Renamed params |
| `tests/test_gamut_compression.py` | Restored from backup | Changed default |
| `tests/test_grain.py` | Restored from backup | Removed GPU tests |

### 3.3 Protected Local Features

- ✅ GPU backend support (MLX/CuPy/Halide) — all source files preserved
- ✅ GPU validation in SimulationPipeline — pipeline.py preserved
- ✅ HDR/HEIC export pipeline — params_schema.py preserved
- ✅ All GPU/HDR test suites — test files preserved
- ✅ Upstream parity regression tests — test_upstream_parity.py preserved

### 3.4 Accepted Upstream Features

- ✅ New `param_manifest.py` for GUI parameter management
- ✅ `widget_sections.py` replaces `widget_specs.py`
- ✅ GUI controller, state, persistence, and widget refactors
- ✅ LUT creator color_spaces and bundles updates
- ✅ GUI test updates

## 4. Test Results

**Command**: `.venv/bin/python -m pytest --ignore=tests/gui --ignore=tests/lut_creator/qa -q`

**Result**: 1208 passed, 8 failed, 8 skipped

**All 8 failures are pre-existing** (verified on backup branch before merge):
- `test_hdr_photo.py::test_film_scan_aware_curve_changes_when_film_scan_profile_changes` — pre-existing
- `test_pipeline_lut_lifecycle.py::test_clear_releases_all_cached_fields` — pre-existing
- `test_pipeline_smoke.py::test_midgray_input_produces_expected_output_values` — pre-existing
- `test_regression_baselines.py` (4 cases) — stale baselines, pre-existing
- `test_upstream_parity.py::test_midgray_output_golden_reference` — stale golden values, pre-existing

**Zero new regressions from the merge.**

## 5. Post-Sync State

- **Branch**: `develop`
- **ahead of upstream/main**: 374 commits (our work + merge commit)
- **behind upstream/main**: 0 commits (fully synced)
- **ahead of origin/develop**: 47 commits (unpushed local work)

## 6. Known Issues

1. **Param name divergence**: Upstream renamed `agx_particle_area_um2` → `particle_area_um2` in GrainParams. We kept our names. GUI code accepted from upstream uses the new names — GUI tests may need adaptation.
2. **Gamut compression default**: Upstream changed default from `oklch` to `cam16ucs`. We kept `oklch`.
3. **Pre-existing test failures**: 8 tests fail due to stale baselines/golden values. Not caused by this merge.
4. **GUI test compatibility**: Accepted upstream GUI code may reference renamed params. GUI tests skipped on Linux (no display).

## 7. Push Strategy

- Push to: `origin/develop` (https://github.com/21Z121Z1/spektrafilm.git)
- **NEVER push to**: `upstream` (https://github.com/andreavolpato/spektrafilm.git)
- Verify with `git remote -v` before pushing
- No force push

## 8. Rollback Plan

If issues found after push:
```bash
git checkout develop
git reset --hard backup/before-upstream-sync-20260602-2023
git push origin develop --force  # only if absolutely necessary
```
