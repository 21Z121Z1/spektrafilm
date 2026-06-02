# Restore HDR Export Settings After GUI Refactor Completion Report

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore GUI HDR HEIC gain-map export wiring after the upstream GUI refactor, while moving HDR export controls into an independent GUI settings category.

**Architecture:** Keep the runtime HDR algorithms and image I/O contracts intact. Add a GUI-owned HDR export state object, render it in its own panel, persist it through GUI state save/load, and have the controller translate that explicit export state plus output-layer scene sidecars into `save_image_oiio(..., hdr_mapping_kwargs=...)` only for HDR-capable exports.

**Tech Stack:** Python dataclasses, Qt/napari GUI widgets, existing `spektrafilm.utils.io.save_image_oiio`, `spektrafilm.utils.hdr_photo.HDRPhotoMapping`, and pytest.

---

## Completion Status

Status: implemented and locally verified on 2026-06-02.

Summary:

- Added an independent GUI HDR export state, manifest, widget section, persistence path, and standalone `HDR` tab.
- Restored controller-side HDR scene sidecar propagation from runtime results to output layer metadata.
- Restored explicit HEIC/HEIF HDR gain-map save dispatch through `save_image_oiio()` and the existing HDR photo writer.
- Kept default SDR and ordinary PNG/JPEG/TIFF/EXR save behavior isolated from HDR settings.
- Added regression tests for state, persistence, manifest layout, controller save kwargs, missing-sidecar errors, ordinary save isolation, HEIC quality dispatch, and GUI app fixture construction.

Task-owned implementation files:

- `src/spektrafilm_gui/hdr_settings.py`
- `src/spektrafilm_gui/options.py`
- `src/spektrafilm_gui/param_manifest.py`
- `src/spektrafilm_gui/state.py`
- `src/spektrafilm_gui/persistence.py`
- `src/spektrafilm_gui/state_bridge.py`
- `src/spektrafilm_gui/widgets.py`
- `src/spektrafilm_gui/napari_layout.py`
- `src/spektrafilm_gui/controller.py`
- `src/spektrafilm/utils/io.py`

Task-owned test files:

- `tests/gui/test_app.py`
- `tests/gui/test_controller_flow.py`
- `tests/gui/test_controller_output.py`
- `tests/gui/test_layout.py`
- `tests/gui/test_persistence.py`
- `tests/gui/test_state_bridge.py`
- `tests/gui/test_widgets.py`
- `tests/test_image_io_color_metadata.py`

## Implementation Result

Independent HDR category:

- `HDRExportSettings` now owns GUI HDR export choices separately from compute, film, paper, scanner, and ordinary output sections.
- `HDR_EXPORT_MANIFEST` is rendered through the refactored path-keyed widget system.
- `WidgetBundle.hdr`, `GUI_STATE_SECTION_NAMES`, and `build_controls_panel()` place HDR controls in a standalone `HDR` tab.
- GUI state serialization includes a normalized `hdr` section, and missing older state files default to SDR-safe HDR export settings.

HEIC HDR export wiring:

- `OUTPUT_HDR_SCENE_ENERGY_KEY = "pipeline_hdr_scene_energy"` is restored in the GUI controller.
- Simulation finish paths attach `result.hdr_scene_energy` to output layer metadata.
- `save_output_layer()` accepts `.heic` and `.heif` file targets.
- HEIC/HEIF HDR gain-map export requires `gui_state.hdr.hdr_heic_gain_map_enabled = True`; otherwise it raises a clear error instead of silently producing an HDR file.
- Profile-aware and film-scan-aware HEIC HDR exports require scene sidecar metadata and fail loudly when the sidecar is missing.
- Generic, profile-aware, and film-scan-aware modes build distinct `hdr_mapping_kwargs` from the independent HDR state.
- Film-scan-aware export samples a runtime film-scan curve profile and passes `paper=None`, preserving the original route semantics.
- Non-HEIC ordinary save formats return the old color-space/CCTF kwargs only and do not pass HDR mapping kwargs.

I/O contract:

- `save_image_oiio()` now accepts `hdr_photo_quality` and forwards it to the HEIC gain-map encoder.
- The existing HDR photo utility remains the writer; this change does not replace the core gain-map implementation.

## Verification Results

Focused requested gates:

- `uv run pytest tests/gui/test_controller_output.py -q` -> `21 passed`
- `uv run pytest tests/test_hdr_photo.py tests/test_hdr_curve_profiles.py -q` -> `173 passed`
- `uv run pytest tests/gui/test_layout.py -q` -> `18 passed`

Added scoped gates:

- `uv run pytest tests/gui/test_persistence.py tests/gui/test_state_bridge.py tests/gui/test_widgets.py -q` -> `27 passed`
- `uv run pytest tests/test_image_io_color_metadata.py -q` -> `26 passed`
- `uv run pytest tests/gui/test_app.py -q` -> `17 passed`
- `uv run pytest tests/gui/test_controller_flow.py tests/gui/test_controller_runtime_module.py tests/gui/test_controller_layers_animation.py tests/gui/test_controller_persistence.py -q` -> `47 passed`
- `uv run pytest tests/gui -q` -> `169 passed`

Real HEIC smoke:

- Command: synthetic tiny HDR image plus scene sidecar through `save_image_oiio(..., hdr_mapping_kwargs=..., hdr_photo_quality=0.91)`.
- Output: `/tmp/spektrafilm-gui-hdr-smoke.heic`
- `file` reported: `ISO Media, HEIF Image HEVC Main or Main Still Picture Profile`.
- `sips` reported: `format: heic`, `pixelWidth: 2`, `pixelHeight: 2`.
- `mdls` reported `kMDItemContentType = "public.heic"`.
- `strings` showed HEIF/HDR auxiliary markers including `tmap`, `auxl`, `auxC`, and `urn:mpeg:hevc:2015:auxid:1`.

Environment note:

- This repository does not currently include a strict HEIF gain-map parser that can assert the full item graph in Python. The local macOS smoke therefore verifies real HEIC creation and auxiliary/tone-map markers, while the pytest suite verifies controller dispatch and encoder kwargs.

## Remaining Risks

- The final commit cannot be made safely while unrelated staged documentation archive changes are already present in the index. Staging this task wholesale would mix the HDR restoration with that unrelated work.
- Some unrelated source/test files are dirty in the working tree outside this task. They were not reverted or normalized.

## Initial Audit Snapshot

Date: 2026-06-02.

Branch and HEAD:

- Branch: `develop`
- HEAD: `949cf43 fix: handle Optional/float|None union types in GUI editor resolution`
- Working tree: already dirty before this task, mostly documentation archive moves/deletions plus `docs/README.md`, `docs/dev/README.md`, `docs/superpowers/plans/README.md`, and `uv.lock`. This task must not revert or normalize that unrelated work.

Required audit commands run:

- `git status -sb`
- `git log --oneline --decorate -n 50`
- `git grep -nE "hdr_mapping_mode|HDRMappingModes|HDR mapping|film_scan_aware|profile_aware|hdr_mapping_kwargs|OUTPUT_HDR_SCENE_ENERGY|scene_luminance|scene_energy|sample_runtime_film_scan_curve_profile|gain map|gainmap|HDRGainMap|write_hdr|hdr_photo" -- src tests docs`

## HDR Preservation Commit Semantics

- `6ba553f test: preserve hdr curve route coverage before upstream sync`: added curve-profile route tests around profile-aware HDR behavior.
- `f7e39f7 test: preserve film-scan hdr mapping coverage before upstream sync`: added `film_scan_aware` HDR photo tests requiring scene luminance and film-scan profile routing.
- `3a8f957 test: preserve gui hdr export mapping coverage before upstream sync`: added GUI controller tests for generic/profile-aware/film-scan-aware save kwargs.
- `ccfd67e feat: preserve film-scan hdr curve profile support before upstream sync`: added runtime film-scan curve-profile sampling support.
- `202db06 feat: preserve film-scan aware hdr export mode before upstream sync`: added `film_scan_aware` to `HDRPhotoMapping`, GUI enum/state/widget specs in the old flat GUI.
- `be287ac feat: preserve film-scan aware gui hdr export before upstream sync`: wired old controller save path to HEIC/EXR HDR kwargs, film-scan curve sampling, and `OUTPUT_HDR_SCENE_ENERGY_KEY`.

## Current State

HDR core:

- Present. `src/spektrafilm/utils/hdr_photo.py` still defines `HDRPhotoMapping`, `save_hdr_photo_heic`, `prepare_hdr_photo_renditions`, `generic`, `profile_aware`, and `film_scan_aware`.
- Present. `src/spektrafilm/utils/hdr_curve_profiles.py` still defines `sample_runtime_film_scan_curve_profile`.
- Present. `src/spektrafilm/utils/io.py` still accepts `scene_luminance`, `scene_rgb`, `hdr_mapping_kwargs`, and dispatches HEIC/HEIF to `save_hdr_photo_heic`.

GUI enum:

- Present. `src/spektrafilm_gui/options.py` still defines `HDRMappingModes` with `generic`, `profile_aware`, and `film_scan_aware`.

GUI manifest/control:

- Missing. `src/spektrafilm_gui/param_manifest.py` has no HDR manifest or HDR `ParamSpec`.
- Missing. `src/spektrafilm_gui/widgets.py` has no HDR section in `WidgetBundle`.
- Missing. `src/spektrafilm_gui/napari_layout.py` does not place an HDR panel on any tab.

GUI state save/load:

- Missing. `src/spektrafilm_gui/state.py` has no HDR state dataclass or `GuiState.hdr`.
- Missing. `src/spektrafilm_gui/state_bridge.py` does not collect/apply an HDR section.
- Missing. `src/spektrafilm_gui/persistence.py` does not serialize/normalize HDR settings.

Output-layer scene sidecar:

- Runtime still exposes sidecar data through `SimulationResult.hdr_scene_energy` in `src/spektrafilm_gui/controller_runtime.py`.
- Broken at the GUI layer. `src/spektrafilm_gui/controller_layers.py` stores float output/color metadata but not HDR scene metadata.
- Broken at the controller layer. `src/spektrafilm_gui/controller.py` no longer defines `OUTPUT_HDR_SCENE_ENERGY_KEY` and `_on_simulation_finished()` does not attach the sidecar to the output layer.

Controller save path:

- Broken. `save_output_layer()` now calls `save_image_oiio(filepath, image_data, color_space=..., cctf_encoding=...)` without `ColorEncoding`, `scene_luminance`, `scene_rgb`, or `hdr_mapping_kwargs`.
- Broken. HEIC/HEIF extensions are absent from the save dialog filter.
- Broken. There is no controller guard for the required scene sidecar when HDR HEIC gain-map export is selected.

Tests:

- Existing tests still remember the old intended behavior in `tests/gui/test_controller_output.py`, but they currently refer to pre-refactor flat fields such as `gui_state.simulation.hdr_mapping_mode`.
- Core HDR tests in `tests/test_hdr_photo.py` and `tests/test_hdr_curve_profiles.py` still cover profile-aware and film-scan-aware semantics.
- I/O tests in `tests/test_image_io_color_metadata.py` still cover `save_image_oiio` HEIC/HDR dispatch and `hdr_mapping_kwargs`.

## Classification

UI detached:

- HDR mapping mode and HDR export options are not rendered in the new path-keyed GUI.
- The old `HDRMappingModes` enum survived, but no new manifest/section uses it.

Export wiring detached:

- Output-layer HDR scene sidecars are not copied into napari layer metadata.
- `save_output_layer()` does not build HDR mapping kwargs or pass scene sidecars.
- HEIC/HDR save selection is not reachable from the GUI save dialog.

Actually missing code:

- A new independent GUI HDR settings dataclass/class.
- A new HDR manifest/section in the refactored widget architecture.
- HDR persistence normalization/serialization.
- Controller helpers that translate independent HDR settings into `HDRPhotoMapping` kwargs.
- Tests aligned to the new `GuiState.hdr` architecture.

Not missing:

- HDR algorithms.
- HEIC gain-map encoder helper.
- `save_image_oiio` HDR contract.
- Film-scan curve-profile sampler.

## New HDR Settings Category Design

Add `src/spektrafilm_gui/hdr_settings.py`:

- `HDRExportSettings`
  - `hdr_mapping_mode: str = "generic"`
  - `hdr_heic_gain_map_enabled: bool = False`
  - `hdr_scene_source: str = "output_layer_metadata"`
  - `hdr_diffuse_white_target: float = 1.0`
  - `hdr_peak_headroom: float = 8.0`
  - `hdr_headroom_mode: str = "content_percentile"`
  - `headroom_percentile: float = 99.9`
  - `preserve_sdr_base: bool = True`
  - `gain_map_mode: str = "rgb"`
  - `heic_quality: float = 0.95`

Add enum classes in `src/spektrafilm_gui/options.py`:

- `HDRSceneSources`: `output_layer_metadata`
- `HDRHeadroomModes`: `content_percentile`, `modern_recovery_peak_budget`
- `HDRGainMapModes`: `rgb`, `luma`

Add `HDR_EXPORT_MANIFEST` in `src/spektrafilm_gui/param_manifest.py` with title `HDR Export`. This manifest must not be included in compute/backend settings, film, paper, scanner, or ordinary output settings.

Add `GuiState.hdr: HDRExportSettings` in `src/spektrafilm_gui/state.py`, clone it in `clone_gui_state()`, initialize it in `gui_state_from_params()`, and add a `hdr_to_dict()`/`normalize_hdr_dict()` pair for persistence.

Add a `WidgetBundle.hdr: ParamsGroupSection`, create it with `ParamsGroupSection(HDR_EXPORT_MANIFEST)`, include `hdr` in `state_bridge.GUI_STATE_SECTION_NAMES`, and place `widgets.hdr` as a standalone `HDR` tab in `napari_layout.build_controls_panel()`. A separate tab is the least ambiguous way to keep it out of `ADVANCED` compute, film, print, scanner, and ordinary output sections.

## HEIC HDR Gain-Map GUI Export Path

The intended path is:

1. Runtime simulation produces `SimulationResult.hdr_scene_energy`.
2. Controller stores that object under `OUTPUT_HDR_SCENE_ENERGY_KEY = "pipeline_hdr_scene_energy"` on the output layer.
3. User saves to `.heic` or `.heif` with `gui_state.hdr.hdr_heic_gain_map_enabled = True`.
4. Controller builds a linear scene `ColorEncoding` for `save_image_oiio`.
5. Controller extracts `scene_luminance` and `scene_rgb` from output-layer HDR scene metadata.
6. Controller builds `hdr_mapping_kwargs` from `gui_state.hdr`:
   - `generic`: minimal generic kwargs only when explicit HEIC HDR gain-map export is enabled.
   - `profile_aware`: include `film`, `paper`, scene sidecar, diffuse white, headroom, gain-map mode, and profile mode.
   - `film_scan_aware`: include `film`, `paper=None`, sampled film-scan `curve_profile`, scene sidecar, diffuse white, headroom, gain-map mode, and profile mode.
7. `save_image_oiio()` dispatches to `save_hdr_photo_heic()`.
8. Existing HDR helper writes the CoreImage gain-map HEIC on macOS, or raises a clear environment error if the platform/toolchain cannot do so.

Scene-sidecar policy:

- For `.heic`/`.heif` with `hdr_heic_gain_map_enabled=True`, missing `scene_luminance` is an error for `profile_aware` and `film_scan_aware`.
- Missing sidecar must never silently degrade to generic HDR or ordinary SDR.
- Standard `.jpg`, `.jpeg`, `.png`, `.tif`, `.tiff`, and default `.exr` saves remain unaffected by HDR settings.

## Fix Steps

### Task 1: Failing Tests For Independent HDR GUI State

- [ ] Add tests that `PROJECT_DEFAULT_GUI_STATE.hdr` exists and defaults to `generic` with `hdr_heic_gain_map_enabled=False`.
- [ ] Add persistence round-trip tests that `hdr_mapping_mode`, `hdr_peak_headroom`, and `hdr_heic_gain_map_enabled` survive `gui_state_to_dict()` / `gui_state_from_dict()`.
- [ ] Add manifest/layout tests that `HDR_EXPORT_MANIFEST.title == "HDR Export"`, `HDR_EXPORT_MANIFEST` is not `COMPUTE_MANIFEST`, and the controls panel places `widgets.hdr` outside the `ADVANCED` tab.
- [ ] Run the new tests and confirm they fail for missing `GuiState.hdr`, manifest, and layout wiring.

### Task 2: Implement HDR State, Manifest, Widget, Bridge, Layout, Persistence

- [ ] Create `src/spektrafilm_gui/hdr_settings.py`.
- [ ] Add HDR enums to `options.py`.
- [ ] Add `HDR_EXPORT_MANIFEST` and include it in `ALL_MANIFESTS`.
- [ ] Add `hdr` to `GuiState`, cloning, defaults, persistence serialization, and normalization.
- [ ] Add `widgets.hdr`, create it in `create_widget_bundle()`, and include it in `state_bridge`.
- [ ] Add a standalone `HDR` tab in `napari_layout.py`.
- [ ] Run Task 1 tests and `uv run pytest tests/gui/test_layout.py -q`.

### Task 3: Failing Tests For Output Sidecar And Controller Save Wiring

- [ ] Update `tests/gui/test_controller_output.py` to use `gui_state.hdr` and nested refactor state fields instead of old flat `gui_state.simulation.*` aliases.
- [ ] Add a test that `_set_or_add_output_layer(..., hdr_scene_energy=...)` stores `OUTPUT_HDR_SCENE_ENERGY_KEY`.
- [ ] Add a test that `.png` save with HDR settings enabled does not pass `hdr_mapping_kwargs`.
- [ ] Add a test that `.heic` save with HDR disabled produces a clear error instead of accidental HDR export.
- [ ] Add a test that `.heic` `profile_aware` passes `scene_luminance`, `scene_rgb` when present, `film`, `paper`, and configured HDR settings.
- [ ] Add a test that `.heic` `film_scan_aware` passes `paper=None` and a dynamic film-scan `curve_profile`.
- [ ] Add a test that missing sidecar in `profile_aware`/`film_scan_aware` raises or reports an explicit save error.
- [ ] Run the updated controller tests and confirm they fail before controller edits.

### Task 4: Restore Controller HDR Export Wiring

- [ ] Import/use `ColorEncoding` in `controller.py`.
- [ ] Restore `OUTPUT_HDR_SCENE_ENERGY_KEY`.
- [ ] Restore a `sample_runtime_film_scan_curve_profile()` wrapper that converts dict samples to curve profiles if needed.
- [ ] Extend `_set_or_add_output_layer()` to attach HDR scene metadata.
- [ ] Pass `result.output_cctf_encoding` and `result.hdr_scene_energy` through `_on_simulation_finished()`.
- [ ] Build `_hdr_mapping_kwargs(gui_state)` from `gui_state.hdr`, not `gui_state.simulation`.
- [ ] Pass `encoding`, `scene_luminance`, `scene_rgb`, and `hdr_mapping_kwargs` into `save_image_oiio()` only for explicit HEIC/HEIF HDR gain-map export.
- [ ] Keep PNG/JPEG/TIFF/standard EXR save behavior unchanged.
- [ ] Run `uv run pytest tests/gui/test_controller_output.py -q`.

### Task 5: HEIC HDR Gain-Map Contract Verification

- [ ] Run `uv run pytest tests/test_hdr_photo.py tests/test_hdr_curve_profiles.py -q`.
- [ ] Run `uv run pytest tests/test_image_io_color_metadata.py -q`.
- [ ] If local macOS CoreImage export can run, add/run a small GUI-controller-to-HEIC smoke using monkeypatched dialog and real `save_image_oiio()` on a tiny synthetic HDR output plus sidecar.
- [ ] If real HEIC export cannot run because the local environment lacks ImageIO/CoreImage/Swift capability, record the exact exception in this document and keep the synthetic dispatch tests as the enforceable contract.

### Task 6: Final Verification And Report Conversion

- [ ] Run requested tests:
  - `uv run pytest tests/gui/test_controller_output.py -q`
  - `uv run pytest tests/test_hdr_photo.py tests/test_hdr_curve_profiles.py -q`
  - `uv run pytest tests/gui/test_layout.py -q`
- [ ] Run added scoped tests for state/manifest/persistence and HEIC dispatch.
- [ ] Run `git diff --check`.
- [ ] Update this file from plan/audit snapshot into a completion report with changed files, tests, environment limits, and remaining risks.
- [ ] Stage only task-owned files.
- [ ] Commit with a message covering GUI HDR export wiring, independent HDR settings, and GUI HDR HEIC gain-map export.

## Test Plan

Required:

- `uv run pytest tests/gui/test_controller_output.py -q`
- `uv run pytest tests/test_hdr_photo.py tests/test_hdr_curve_profiles.py -q`
- `uv run pytest tests/gui/test_layout.py -q`

Additional:

- GUI HDR state/persistence tests.
- HDR settings manifest tests.
- `save_output_layer()` HDR kwargs tests.
- HEIC HDR gain-map dispatch tests.
- Ordinary save-path regression tests for PNG/JPEG/TIFF/EXR.
- `uv run pytest tests/test_image_io_color_metadata.py -q`.

## Acceptance Criteria

- HDR core utility remains the existing implementation, not a fake replacement.
- Old HDR semantics are migrated into the new GUI architecture; the GUI refactor is not rolled back.
- GUI contains an independent `HDR Export` category.
- HDR settings are not mixed into ordinary simulation settings, advanced compute settings, film, paper, or scanner sections.
- HDR settings persist through state save/load.
- HDR settings affect only explicit HDR export/render mapping.
- Default SDR preview/output/save behavior remains unchanged.
- `generic`, `profile_aware`, and `film_scan_aware` do not contaminate each other.
- `save_output_layer()` constructs correct HDR export parameters.
- Output layers carry HDR scene sidecar metadata.
- Missing scene sidecar for profile-aware/film-scan-aware HDR HEIC export fails loudly.
- GUI can explicitly select and dispatch HDR HEIC gain-map export.
- Real HEIC gain-map verification is recorded if supported by the local macOS toolchain; otherwise the environment limitation is explicit.

## Completion Self-Check

Before marking this complete:

- Confirm this is not only a UI-control restoration; save/export wiring must be verified.
- Confirm HDR settings are not inside normal simulation or compute settings.
- Confirm GUI HEIC export dispatches the HDR gain-map path, not ordinary HEIC.
- Confirm profile-aware and film-scan-aware use different mapping semantics.
- Confirm SDR preview/output and ordinary saves are not changed.
- Confirm tests cover GUI, state, controller, HDR helper, and export dispatch.
