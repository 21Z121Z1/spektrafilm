# Full Workspace Code Review - Spektrafilm - 2026-05-26

Review goal: read-only full-workspace review of the Spektrafilm repository state, with special focus on SDR preservation, profile-aware HDR export, color management, GPU/MLX/Metal paths, numeric precision, Qt runtime behavior, film/profile defaults, and test validity.

## Repository State At Review Start

- Live workspace at start: `/Users/retriedstormtrooper/Documents/spektrafilm-main`.
- Start branch: `main-sync...upstream/main [ahead 14]`.
- Start commit reviewed: `30f7436a56a1fc9a684f9fc85bb21b5617c4821f` (`30f7436 Revert "refactor: GPU kernel improvements - async-safe highlight boost, density/LUT/diffusion/grain refinements"`).
- Start dirty worktree status:
  - `?? .matplotlib/`
  - `?? scratch/`
  - `?? scratch_precision_test.py`
- Remotes:
  - `origin https://github.com/21Z121Z1/spektrafilm.git`
  - `upstream https://github.com/andreavolpato/spektrafilm.git`
- Merge/rebase/cherry-pick state at review start: no `MERGE_HEAD`, no `rebase-merge`, no `rebase-apply`, no `CHERRY_PICK_HEAD`.
- Worktree coordination: the live workspace was not a linked git worktree (`.git` was the common dir). To keep the review read-only while preserving the dirty start state, I reviewed an rsync snapshot at `/private/tmp/spektrafilm-full-review-20260526`, excluding `.git`, `.venv`, Python caches, pytest/mypy/ruff caches, and `.matplotlib`.
- Active-change observation: while the review was running, the live workspace changed to branch `develop...origin/develop [ahead 38]` with production-file modifications in `src/spektrafilm/utils/io.py` and `src/spektrafilm_gui/controller.py`, plus many untracked docs/artifacts. The findings below are for the start snapshot at `30f7436a`, not the later live branch state.

## Review Scope

Reviewed source/runtime areas:

- Python package source under `src/spektrafilm`, including runtime pipeline, params, model, profiles, color management, image I/O, RAW processing, HDR photo/export helpers, HDR curve profiles, GPU backends/kernels, interpolation, diffusion, grain, glare, and utility modules.
- GUI/runtime source under `src/spektrafilm_gui`, including controller save paths, thread worker boundaries, state mapping, widget specs, layer metadata, display transforms, app wiring, persistence, and profile synchronization.
- macOS HDR encoder source: `src/spektrafilm/data/macos/hdr_heif_encoder.swift`.
- Test suites under `tests`, including HDR photo, image I/O/color metadata, RAW processing, runtime API, GPU filters/backend/density/LUT, GUI controller flow/output/runtime/app/widgets, smoke/regression, and params tests.
- Scripts and tools under `scripts` and `tools`, including HDR curve export/evaluation and RAW validation tooling.
- Config/build files: `pyproject.toml`, `pytest.ini`, package data, project script entry point, optional GPU extras, and `.github/FUNDING.yml`.
- Behavior docs: `README.md`, `docs/superpowers/plans/*`, `docs/hdr_profile_aware_raw_validation.*`, `src/spektrafilm/data/hdr_curve_profiles/README.md`, and generated curve-analysis docs as context.

Intentionally skipped or sampled:

- `.git`, `.venv`, caches, `.matplotlib`, `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `.DS_Store`, and generated binary outputs were skipped.
- Large image/binary assets and sample exports were not decoded unless referenced by tests or docs.
- Generated HDR curve sample JSON files were sampled structurally and by loader/tests rather than read one-by-one; the behavior-critical code is in `hdr_curve_profiles.py`, the index, and tests.
- Untracked scratch files were treated as context only, not production behavior.

Inventory notes:

- The snapshot contained 517 meaningful source/test/script/tool/doc/config files matching `*.py`, `*.swift`, `*.json`, `*.md`, `*.toml`, `*.ini`, `*.yaml`, and `*.yml` under `src`, `tests`, `scripts`, `tools`, and `docs`.
- `pyproject.toml` declares Python `~=3.13`, package data under `src/spektrafilm/data/**/*`, GUI assets, and optional GPU extras for MLX and CuPy.
- `pytest.ini` discovers `tests` and disables napari plugin loading.

## Methodology

- Captured git state, remotes, commit SHA, dirty state, and merge/rebase/cherry-pick indicators before review.
- Created a read-only snapshot to avoid interfering with the live workspace and possible branch-integration work.
- Enumerated source/test/tool/doc files with `find`, `rg`, `git ls-files`, AST parsing, and line-count summaries.
- Read major runtime, GUI, HDR, color, RAW, GPU, film/profile, and test modules directly.
- Used targeted searches for `TODO`, `FIXME`, `HACK`, `BUG`, `float16`, `float64`, `cpu`, `fallback`, `profile`, `icc`, `hdr`, `exr`, `heic`, `mlx`, `metal`, `thread`, `QRunnable`, and exception handling.
- Discovered commands from `README.md`, `pyproject.toml`, `pytest.ini`, and project plans. The safe verification commands used the repo `.venv` and the snapshot `src` directory first on `PYTHONPATH`.
- Ran targeted tests and compile checks in the snapshot. Full-suite execution was attempted first and aborted in a GUI test; targeted re-runs isolated the blockers.
- Checked likely defects against primary/authoritative references where useful:
  - NumPy `percentile` API documentation for percentile parameter bounds: <https://numpy.org/doc/stable/reference/generated/numpy.percentile.html>
  - Qt `QApplication` documentation for application object requirements before widgets: <https://doc.qt.io/qt-6/qapplication.html>
  - OpenImageIO metadata documentation for EXR/color metadata context: <https://openimageio.readthedocs.io/en/latest/stdmetadata.html>
  - ACEScg and ACES workflow documentation: <https://docs.acescentral.com/encodings/acescg/>
  - Apple Core Image HDR/gain-map documentation: <https://developer.apple.com/documentation/coreimage>
  - Adobe Gain Map documentation for SDR/HDR rendition model: <https://helpx.adobe.com/camera-raw/using/gain-map.html>

Verification commands and results:

- Full suite attempt: `python -m pytest tests -q` aborted after early failures in `tests/gui/test_controller_output.py::test_save_output_layer_heic_passes_profile_aware_film_paper`, with `QWidget: Must construct a QApplication before a QWidget`.
- Corrected snapshot import setup used:
  - `PYTHONPATH=/private/tmp/spektrafilm-full-review-20260526/src:/private/tmp/spektrafilm-full-review-20260526`
  - `MPLCONFIGDIR=/private/tmp/spektrafilm-review-mpl`
- `tests/test_hdr_photo.py -q -x -s`: failed on `test_hdr_photo_mapping_builds_authored_sdr_and_hdr_renditions`.
- `tests/test_image_io_color_metadata.py -q -x -s`: failed on `test_archive_exr_does_not_call_hdr_rendition_mapping`.
- `tests/gui/test_controller_output.py::test_save_output_layer_hdr_rendition_exr_passes_explicit_mode_and_sidecar -q -s`: failed with missing `exr_mode` in save kwargs.
- `tests/test_image_io_color_metadata.py::test_acescg_tiff_icc_roundtrips_as_linear_encoding -q -s`: failed because no ICC bytes were embedded for ACEScg TIFF.
- `tests/test_runtime_api.py -q -x -s`: passed, `18 passed`, with one expected warning from a deliberately partial pipeline test double.
- `tests/test_runtime_api.py tests/test_gpu_filters.py tests/test_raw_file_processor.py tests/gui/test_controller_runtime_module.py -q -x -s`: failed after 42 passes and 1 skip on ACEScg display-transform ICC handling.
- `python -m compileall -q` over `src/spektrafilm`, `src/spektrafilm_gui`, `tests`, `tools`, and `scripts`: passed.

## Findings Summary

- Critical: 1
- High: 3
- Medium: 4
- Low: 1

## Critical Findings

### C1. HDR Rendition EXR mode is exposed and reports success, but saves the scene-linear archive instead

- File/symbol: `src/spektrafilm_gui/controller.py:543`, `src/spektrafilm_gui/controller.py:552`, `src/spektrafilm_gui/controller.py:594`, `src/spektrafilm_gui/controller.py:628`; `src/spektrafilm/utils/io.py:477`; `tests/gui/test_controller_output.py:498`; `tests/test_image_io_color_metadata.py:168`; `README.md:254`.
- Observed problem: the controller detects `hdr_exr_mode == "hdr_rendition"` and collects sidecar data, but the non-HEIC save branch only passes `encoding` and `white_luminance` to `save_image_oiio`. It never passes `exr_mode`, `scene_luminance`, `scene_rgb`, or `hdr_mapping_kwargs`, and `save_image_oiio` has no parameters for them. The user-visible status still says `EXR saved as HDR rendition`.
- Why this is a bug/risk: the explicit HDR Rendition EXR UI path silently writes the existing output float layer instead of the authored HDR rendition. That is a wrong export and can invalidate HDR validation, handoff, and archival workflows.
- Expected behavior: `scene_linear_archive` writes the existing rendered float output with `whiteLuminance=203`; `hdr_rendition` writes the same authored HDR rendition used by HEIC/HDR photo export, while preserving EXR color metadata.
- Evidence:
  - README documents HDR Rendition EXR as a distinct explicit mode.
  - `tests/gui/test_controller_output.py::test_save_output_layer_hdr_rendition_exr_passes_explicit_mode_and_sidecar` fails with `KeyError: 'exr_mode'`.
  - `tests/test_image_io_color_metadata.py::test_archive_exr_does_not_call_hdr_rendition_mapping` fails because tests call the documented API shape but `save_image_oiio` rejects `scene_luminance`.
- External reference: OpenImageIO supports EXR metadata attributes such as chromaticities and other typed attributes; the project can keep archive/rendition behavior explicit while writing correct EXR metadata. Apple/Adobe gain-map docs also model HDR delivery as authored SDR/HDR renditions, not as a relabeled SDR archive.
- Concrete suggested fix:
  - Either extend `save_image_oiio` with `exr_mode`, `scene_luminance`, `scene_rgb`, and `hdr_mapping_kwargs`, or add a dedicated `save_hdr_rendition_exr` helper beside `save_hdr_photo_heic`.
  - In `GuiController.save_output_layer`, pass the explicit HDR rendition mode and sidecars for `exr_save and hdr_exr_mode == "hdr_rendition"`.
  - Keep archive EXR default behavior unchanged and ensure it never calls HDR mapping.
- Suggested tests:
  - Make `test_save_output_layer_hdr_rendition_exr_passes_explicit_mode_and_sidecar` pass.
  - Make `test_hdr_rendition_exr_uses_authored_hdr_mapping` pass and assert pixels differ from archive output.
  - Add a controller-level test that status text cannot claim HDR rendition unless the HDR rendition helper was called.
- Risk of fix: medium. It touches export routing and color/HDR metadata, but can be isolated behind explicit `hdr_rendition`.
- Blocks branch integration/push: yes.

## High Findings

### H1. ACEScg ICC profiles exist but are not mapped, breaking TIFF ICC export and display-transform ICC conversion

- File/symbol: `src/spektrafilm/utils/io.py:157`, `src/spektrafilm/utils/io.py:211`, `src/spektrafilm/utils/io.py:222`, `src/spektrafilm_gui/controller_runtime.py:181`, `src/spektrafilm_gui/controller_runtime.py:191`, `tests/test_image_io_color_metadata.py:294`, `tests/gui/test_controller_runtime_module.py:193`.
- Observed problem: `src/spektrafilm/data/icc/ellelstone/ACEScg-elle-V2-g10.icc` and `ACEScg-elle-V2-srgbtrc.icc` are bundled, but `_ICC_FILENAMES` and `_ICC_PROFILES` do not include `"ACEScg"`. `resolve_icc_profile_bytes("ACEScg", cctf_encoding=False)` returns `None`.
- Why this is a bug/risk: ACES reference workflow uses ACEScg as the scene-linear working space, but ACEScg TIFF export omits ICC metadata and display transform falls back to sRGB profile creation. This can cause wrong previews, weak metadata round-tripping, and failed tests in the color-management workflow.
- Expected behavior: linear ACEScg should resolve to the bundled linear ACEScg ICC; if encoded ACEScg is ever supported, it should resolve to an appropriate encoded profile or be explicitly rejected.
- Evidence:
  - Probe output: `ACEScg False 0`, `ACEScg True 0`; ACES2065-1 and sRGB resolved to nonzero ICC byte counts.
  - `test_acescg_tiff_icc_roundtrips_as_linear_encoding` fails because `_icc_bytes_from_spec(spec)` is `None`.
  - `test_apply_display_transform_uses_acescg_icc_profile_when_available` fails because `_imagecms_profile_for_color_space("ACEScg")` returns `None` and the fake ImageCms module lacks the fallback `createProfile`.
- External reference: ACES documents ACEScg as an AP1 linear working space, while ACES2065-1 is the AP0 interchange/archive encoding. That supports explicit ICC mapping for ACEScg in display/file workflows.
- Concrete suggested fix:
  - Add `("ACEScg", False): "ellelstone/ACEScg-elle-V2-g10.icc"` to `_ICC_FILENAMES`.
  - Consider `("ACEScg", True): "ellelstone/ACEScg-elle-V2-srgbtrc.icc"` only if the UI can genuinely produce encoded ACEScg; otherwise reject encoded ACEScg output clearly.
  - Add `"ACEScg"` to `_ICC_PROFILES` or update `_known_color_space_from_icc_profile` to iterate `_ICC_FILENAMES` variants too.
- Suggested tests:
  - Make `test_acescg_tiff_icc_roundtrips_as_linear_encoding` pass.
  - Add direct tests for `resolve_icc_profile_bytes("ACEScg", cctf_encoding=False)`.
  - Add display-transform test with a fake `ImageCmsProfile` that proves the ICC path is used.
- Risk of fix: low to medium. It should be metadata-only, but color-profile matching can affect preview paths and needs snapshot testing.
- Blocks branch integration/push: yes for ACES reference/color-management work.

### H2. The GUI "Enable Path to White" toggle does not disable profile-aware HDR path-to-white

- File/symbol: `src/spektrafilm_gui/state.py:365`, `src/spektrafilm_gui/widget_specs.py:680`, `src/spektrafilm_gui/controller.py:560`, `src/spektrafilm_gui/controller.py:569`, `src/spektrafilm/utils/hdr_photo.py:95`, `src/spektrafilm/utils/hdr_photo.py:110`, `src/spektrafilm/utils/hdr_photo.py:662`.
- Observed problem: the GUI state exposes `path_to_white_enabled`, and the controller maps it only to legacy `hdr_highlight_path_to_white`. Profile-aware HDR color recovery uses `profile_hdr_path_to_white_strength`, which remains at the default `0.30`.
- Why this is a bug/risk: a user can disable path-to-white in the GUI and still get highlight desaturation/neutralization in profile-aware HDR exports. This is directly user-visible color/HDR behavior.
- Expected behavior: disabling the GUI toggle should disable both legacy and profile-aware path-to-white behavior, or the GUI should expose separate controls with clear labels.
- Evidence:
  - Probe output with `path_to_white_enabled=False`: `legacy_hdr_highlight_path_to_white= 0.0`, `profile_hdr_path_to_white_strength= 0.3`.
  - `tests/test_hdr_photo.py` explicitly constructs mappings that disable both legacy and profile-aware path-to-white, which implies both controls matter.
- External reference: no external reference needed; the defect is a local GUI-to-runtime contract mismatch.
- Concrete suggested fix:
  - In `GuiController.save_output_layer`, also pass `profile_hdr_path_to_white_strength=0.0` when `path_to_white_enabled` is false.
  - If the desired default when enabled is `0.30`, pass it explicitly instead of relying on `HDRPhotoMapping` defaults.
- Suggested tests:
  - Controller test: set `gui_state.hdr_export.path_to_white_enabled=False` and assert `HDRPhotoMapping.profile_hdr_path_to_white_strength == 0.0`.
  - HDR unit test: profile-aware highlights remain saturated when the GUI-equivalent mapping disables path-to-white.
- Risk of fix: low. It changes only the disabled-toggle behavior; enabled default remains the same if passed explicitly.
- Blocks branch integration/push: yes if profile-aware HDR GUI behavior is in scope.

### H3. GUI preview/full scan always computes and stores full-size HDR sidecars, creating large memory pressure

- File/symbol: `src/spektrafilm_gui/controller.py:926`, `src/spektrafilm/runtime/pipeline.py:299`, `src/spektrafilm/runtime/pipeline.py:140`, `src/spektrafilm/runtime/pipeline.py:143`, `src/spektrafilm/runtime/pipeline.py:542`, `src/spektrafilm_gui/controller.py:699`, `src/spektrafilm_gui/controller_layers.py:421`.
- Observed problem: `GuiController._process_image_with_runtime` calls `process_with_metadata` whenever it exists, for normal preview and scan. `process_with_metadata` always builds `scene_luminance` and `scene_rgb` sidecars and attempts dynamic profile characterization, then the GUI stores those sidecars on the output layer.
- Why this is a bug/risk: a 4000x6000 float32 image adds about 366 MiB of sidecar arrays before accounting for the rendered output, preview data, raw input, GPU/CPU intermediate arrays, and dynamic profile sampling. This undermines the stated large RAW/low-memory priority and can make normal SDR preview/scan pay HDR-export costs.
- Expected behavior: normal SDR preview/output should avoid HDR sidecar and dynamic profile work unless an HDR export path requires it, or the app should make this memory cost explicit and bounded.
- Evidence:
  - Probe output: `(1000, 1000, 3) 15.3 MiB sidecars`; `(4000, 6000, 3) 366.2 MiB sidecars`.
  - README documents `Simulator.process()` as the array-returning API and `process_with_metadata()` as the metadata path; GUI currently always chooses the metadata path.
- External reference: none required; this is local memory arithmetic from stored float32 arrays.
- Concrete suggested fix:
  - Add a request flag to `SimulationRequest` such as `collect_hdr_metadata`.
  - Use `Simulator.process()` for ordinary SDR preview/scan and `process_with_metadata()` only when the user has enabled/needs HDR export sidecars.
  - Consider storing `scene_rgb` only when a mapping mode requires source RGB color recovery, or recomputing sidecars on explicit HDR export for full-resolution scans.
- Suggested tests:
  - GUI/runtime test proving default preview uses `process()` and does not store `HDR_SCENE_ENERGY_METADATA_KEY`.
  - HDR export test proving sidecars are collected and preserved when HDR save is requested.
  - A memory-shape test proving no `scene_rgb` sidecar is stored for SDR-only output.
- Risk of fix: medium. It changes when metadata is available for later export; the UX may need an explicit "run HDR-ready scan" or background recompute path.
- Blocks branch integration/push: should block a large-RAW/HDR release; otherwise should be fixed soon.

## Medium Findings

### M1. HDR SDR-base test expectations conflict with the current SDR-preservation implementation

- File/symbol: `src/spektrafilm/utils/hdr_photo.py:49`, `src/spektrafilm/utils/hdr_photo.py:454`, `tests/test_hdr_photo.py:24`, `README.md:256`.
- Observed problem: `HDRPhotoMapping.preserve_sdr_base` defaults to `True`, and generic HDR rendition creation clips the original image into `sdr_rgb`. The first HDR photo unit test still expects diffuse white to map to `sdr_paper_white=0.9`.
- Why this is a bug/risk: the test suite is red, and the failing assertion appears to encode an older tone-mapped SDR base model. This can hide real regressions because it is unclear whether the production code or the test is now authoritative.
- Expected behavior: tests should assert the intended contract. If SDR preservation is intended, diffuse-white input should remain visually stable in the SDR base; if the older sdr-paper-white mapping is intended, the implementation should not default to `preserve_sdr_base=True`.
- Evidence:
  - Targeted test failure: actual `[1.0, 1.0, 1.0]`, expected `[0.9, 0.9, 0.9]`.
  - README states HEIC/HEIF saves authored SDR base plus authored HDR rendition; Spektrafilm-specific priorities emphasize SDR baseline stability.
- External reference: Adobe/Apple gain-map docs support authored SDR and HDR renditions, but they do not dictate Spektrafilm's SDR aesthetic. This is primarily a product/test contract decision.
- Concrete suggested fix:
  - Decide whether the current `preserve_sdr_base=True` default is the intended branch behavior.
  - If yes, update early HDR photo tests to assert SDR-base preservation and move old tone-map coverage to `preserve_sdr_base=False`.
  - If no, change default behavior and add regression tests proving SDR output is not globally darkened.
- Suggested tests:
  - `test_hdr_photo_mapping_preserves_sdr_base_by_default`.
  - `test_hdr_photo_mapping_tone_maps_sdr_base_when_preserve_sdr_base_false`.
- Risk of fix: low for test-only change; high if production default changes.
- Blocks branch integration/push: yes until tests and product intent are reconciled.

### M2. Modern profile-HDR mapping parameters are accepted with invalid ranges

- File/symbol: `src/spektrafilm/utils/hdr_photo.py:118`, `src/spektrafilm/utils/hdr_photo.py:121`, `src/spektrafilm/utils/hdr_photo.py:181`, `src/spektrafilm/utils/hdr_curve_profiles.py:892`, `src/spektrafilm/utils/hdr_curve_profiles.py:897`.
- Observed problem: `HDRPhotoMapping.__post_init__` validates `profile_hdr_mode`, target peak, and recovery ratio, but accepts invalid `profile_hdr_normalize_percentile`, negative `profile_hdr_recovery_knee_ev`, negative or reversed recovery spans, zero `profile_hdr_max_chroma_gain`, and reversed path-to-white EV ranges.
- Why this is a bug/risk: invalid values can crash later or produce nonsensical HDR curves. Example: `profile_hdr_normalize_percentile=-1.0` constructs successfully, then fails in `np.percentile` with `ValueError: Percentiles must be in the range [0, 100]`.
- Expected behavior: invalid mapping inputs should fail at construction with clear local messages, or be clamped deliberately and documented.
- Evidence:
  - Probe output: invalid fields were accepted at construction.
  - Rendering with `profile_hdr_normalize_percentile=-1.0` later raised NumPy's percentile range error.
  - Rendering with negative recovery knee and reversed path-to-white EV range completed, meaning the authored HDR curve can silently ignore or invert intended controls.
- External reference: NumPy documents percentile `q` in the inclusive range `[0, 100]`.
- Concrete suggested fix:
  - Extend `HDRPhotoMapping.__post_init__` validation:
    - `0 < profile_hdr_normalize_percentile <= 100`
    - finite `profile_hdr_recovery_knee_ev >= 0`
    - `profile_hdr_recovery_full_ev > profile_hdr_recovery_knee_ev`
    - finite `profile_hdr_max_chroma_gain >= 1`
    - `profile_hdr_path_to_white_start_ev < profile_hdr_path_to_white_end_ev`
    - `0 <= profile_hdr_path_to_white_strength <= 1`
  - Keep validation messages specific to the bad field.
- Suggested tests:
  - Parametrized invalid-constructor tests for every modern profile-HDR field.
  - Test that `build_profile_preserving_hdr_curve` receives only validated percentiles and EV ranges.
- Risk of fix: low to medium. Existing callers with bad values will fail earlier; that is usually desirable but may surface hidden configs.
- Blocks branch integration/push: no by itself, but should fix soon.

### M3. GUI HEIC tests call the real encoder and can abort pytest through QMessageBox without QApplication

- File/symbol: `tests/gui/test_controller_output.py:65`, `tests/gui/test_controller_output.py:395`, `src/spektrafilm_gui/controller.py:582`, `src/spektrafilm_gui/controller.py:601`.
- Observed problem: `_capture_saved_output` monkeypatches `save_image_oiio` and `write_image_metadata`, but HEIC tests exercise `save_hdr_photo_heic` without replacing it. When the real HEIC path raises, the controller catches it and calls `QMessageBox.critical`; in the test process there is no `QApplication`, so Qt aborts the interpreter.
- Why this is a bug/risk: this turns an ordinary test failure into a fatal process abort, preventing the full suite from reporting all failures. It is a CI/review blocker even if the production GUI has a QApplication.
- Expected behavior: GUI unit/integration tests should monkeypatch the HEIC encoder and QMessageBox boundary; production should still report save errors through the GUI.
- Evidence:
  - Full suite and single-test run abort with `QWidget: Must construct a QApplication before a QWidget`.
  - Stack trace points at `GuiController.save_output_layer` line 601 from `test_save_output_layer_heic_passes_profile_aware_film_paper`.
- External reference: Qt requires a `QApplication` object before constructing widgets.
- Concrete suggested fix:
  - Add a HEIC-specific capture helper that monkeypatches `controller_module.save_hdr_photo_heic`.
  - Monkeypatch `QMessageBox.critical` in error-path tests, or use a Qt test fixture that owns a QApplication.
  - Add a controller test that save errors call the reporting boundary without constructing real dialogs in headless tests.
- Suggested tests:
  - Re-run `tests/gui/test_controller_output.py` without fatal abort.
  - Add one explicit HEIC error-path test that asserts the critical dialog function is called with the exception message.
- Risk of fix: low; test harness only unless dialog abstraction is introduced.
- Blocks branch integration/push: yes while the full suite aborts.

### M4. `save_image_oiio` and HDR export API boundaries are unclear and inconsistent across tests/docs

- File/symbol: `src/spektrafilm/utils/io.py:477`, `src/spektrafilm_gui/controller.py:157`, `tests/test_image_io_color_metadata.py:137`, `tests/test_image_io_color_metadata.py:204`, `docs/superpowers/plans/2026-05-24-scene-energy-hdr-gainmap-autoexposure.md:55`.
- Observed problem: tests and plans expect `save_image_oiio` to accept HEIC/HDR sidecar arguments, while the implementation treats HEIC as a controller-level special case and `save_image_oiio` as generic raster/EXR writing only.
- Why this is a bug/risk: this ambiguity caused red tests and likely contributed to C1. It is hard to reason about which layer owns HDR rendition generation.
- Expected behavior: one explicit boundary:
  - Generic image I/O writes normal formats and archive EXR only; HEIC/HDR rendition EXR have dedicated helpers.
  - Or `save_image_oiio` becomes the single dispatch API and accepts explicit HDR kwargs.
- Evidence:
  - `save_image_oiio` signature has no HDR sidecar parameters.
  - Multiple tests call it with `scene_luminance`, `hdr_mapping_kwargs`, or expect HEIC dispatch behavior.
- External reference: OpenImageIO is appropriate for generic raster/EXR output, while platform HEIC gain-map authoring is a separate CoreImage/Swift path; either layering is valid if consistent.
- Concrete suggested fix:
  - Choose and document the ownership boundary.
  - Rename helpers if needed, for example `save_standard_image_oiio`, `save_hdr_rendition_exr`, and `save_hdr_photo_heic`.
  - Update tests to target the chosen API layer.
- Suggested tests:
  - Contract tests for archive EXR, HDR rendition EXR, and HEIC routing at the owning layer.
  - Negative tests ensuring generic PNG/TIFF/JPEG never invoke HDR mapping.
- Risk of fix: medium. This affects public-ish utility APIs and controller routing.
- Blocks branch integration/push: covered by C1; this should be fixed as part of that work.

## Low Findings

### L1. README still advertises a missing `src/spektrafilm_profile_creator` package

- File/symbol: `README.md:53`.
- Observed problem: the README tree lists `src/spektrafilm_profile_creator/`, but the reviewed source tree contains `src/spektrafilm` and `src/spektrafilm_gui` only.
- Why this is a bug/risk: developer onboarding and package discovery are misleading.
- Expected behavior: docs should match the current package layout or mark removed/future tools clearly.
- Evidence: file inventory found no `src/spektrafilm_profile_creator` package.
- External reference: none needed.
- Concrete suggested fix: update the README tree to the current packages, or restore/package the profile creator if it is still intended.
- Suggested tests: no code test needed; docs review check is enough.
- Risk of fix: low.
- Blocks branch integration/push: no.

## Verified Intentional Or Not Flagged As Bugs

- SDR preservation in `hdr_photo.py` appears intentional in the current branch: the default `preserve_sdr_base=True` keeps the authored SDR base visually stable. The red test should be resolved by product/test decision, not blindly changing the code.
- Positive-film defaults and Provia/Velvia coupler gamma behavior are covered by `tests/test_photo_params.py` and GUI mapper tests. I did not find a clear Provia/Velvia default regression in the reviewed snapshot.
- GPU/MLX tiling and float64 restrictions are intentional and tested: `SimulationPipeline` rejects explicit GPU backends with `float64`, and stochastic grain/glare disables tiling. This matches the local Metal acceleration plan and tests.
- QRunnable worker `except BaseException` is intentional at the Qt worker boundary and covered by GUI runtime tests. I did not flag it as a production bug.
- RAW import diagnostics are documented as automatic estimates, not physical diffuse-white truth. I did not treat estimate-based headroom as a defect.

## Final Prioritized Action List

Must fix before push/integration:

1. Implement or remove/block HDR Rendition EXR mode so it cannot silently save the wrong export.
2. Fix ACEScg ICC mapping and display-transform/profile round-tripping.
3. Fix the profile-aware path-to-white GUI toggle contract.
4. Make the test suite non-aborting and reconcile the HDR SDR-base test expectation.

Should fix soon:

1. Validate all modern profile-HDR mapping parameters at construction.
2. Split normal SDR preview/scan from expensive HDR sidecar collection, or make the HDR-ready memory cost explicit.
3. Clarify `save_image_oiio` versus dedicated HDR helper ownership and update tests accordingly.

Optional cleanup:

1. Update the README source tree to remove or explain `src/spektrafilm_profile_creator`.
2. Keep generated analysis docs/artifacts clearly separated from source-reviewed behavior.

Needs user/product decision:

1. Confirm whether default HEIC SDR base should preserve the current SDR look (`preserve_sdr_base=True`) or continue the older `sdr_paper_white=0.9` tone-map contract.
2. Decide whether HDR sidecars should always be retained after every scan for convenient later export, or only collected on explicit HDR-ready runs.

## Self-Audit

Question: Have I reviewed every meaningful code area and produced actionable findings backed by local evidence and, where useful, external best-practice search?

Answer: yes for the reviewed start snapshot. The report covers source, GUI, HDR export, color management, RAW import, GPU/MLX/Metal paths, numeric precision, Qt runtime, film/profile defaults, scripts/tools, tests, configs, and behavior docs. Skipped files are either generated, binary, cache, sample output, or large data artifacts whose behavior is mediated through reviewed code/tests.

## Final Workspace Status

Final live workspace status after writing the report:

```text
## develop...origin/develop
?? .matplotlib/
?? docs/curve_analysis.zip
?? docs/curve_analysis/
?? docs/dev/2026-05-26-full-workspace-code-review.md
?? docs/dev/modern_recovery_peak_budget_plan.md
?? docs/hdr_profile_aware_raw_validation.json
?? docs/hdr_profile_aware_raw_validation.md
?? docs/superpowers/
?? output.heic
?? scratch/
?? scratch_precision_test.py
?? tests/scratch_headroom.py
```

The review added only this report file. `git diff --name-only -- src tests pyproject.toml pytest.ini README.md scripts tools .github` returned no paths after the report write, so this review did not modify production code, tests, configs, scripts, tools, or existing docs.
