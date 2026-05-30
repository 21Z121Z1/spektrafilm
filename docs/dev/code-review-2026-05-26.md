# Full Workspace Code Review - Spektrafilm - 2026-05-26

Review goal: read-only full-workspace review of the Spektrafilm repository state, with special focus on SDR preservation, profile-aware HDR export, color management, GPU/MLX/Metal paths, numeric precision, Qt runtime behavior, film/profile defaults, and test validity.

## Findings Summary

- Critical: 1
- High: 3
- Medium: 4
- Low: 1

## Critical Findings

### C1. HDR Rendition EXR mode is exposed and reports success, but saves the scene-linear archive instead — FIXED

- File/symbol: src/spektrafilm_gui/controller.py:543, src/spektrafilm_gui/controller.py:552, src/spektrafilm_gui/controller.py:594, src/spektrafilm_gui/controller.py:628; src/spektrafilm/utils/io.py:477; tests/gui/test_controller_output.py:498; tests/test_image_io_color_metadata.py:168; README.md:254.
- Observed problem: the controller detects hdr_exr_mode == "hdr_rendition" and collects sidecar data, but the non-HEIC save branch only passes encoding and white_luminance to save_image_oiio. It never passes exr_mode, scene_luminance, scene_rgb, or hdr_mapping_kwargs, and save_image_oiio has no parameters for them.
The user-visible status still says EXR saved as HDR rendition.
- Why this is a bug/risk: the explicit HDR Rendition EXR UI path silently writes the existing output float layer instead of the authored HDR rendition. That is a wrong export and can invalidate HDR validation, handoff, and archival workflows.
- Expected behavior: scene_linear_archive writes the existing rendered float output with whiteLuminance=203; hdr_rendition writes the same authored HDR rendition used by HEIC/HDR photo export, while preserving EXR color metadata.
- Evidence:
  - README documents HDR Rendition EXR as a distinct explicit mode.
  - tests/gui/test_controller_output.py::test_save_output_layer_hdr_rendition_exr_passes_explicit_mode_and_sidecar fails with KeyError: 'exr_mode'.
  - tests/test_image_io_color_metadata.py::test_archive_exr_does_not_call_hdr_rendition_mapping fails because tests call the documented API shape but save_image_oiio rejects scene_luminance.
- Concrete suggested fix:
  - Either extend save_image_oiio with exr_mode, scene_luminance, scene_rgb, and hdr_mapping_kwargs, or add a dedicated save_hdr_rendition_exr helper beside save_hdr_photo_heic.
  - In GuiController.save_output_layer, pass the explicit HDR rendition mode and sidecars for exr_save and hdr_exr_mode == "hdr_rendition".
  - Keep archive EXR default behavior unchanged and ensure it never calls HDR mapping.
- Suggested tests:
  - Make test_save_output_layer_hdr_rendition_exr_passes_explicit_mode_and_sidecar pass.
  - Make test_hdr_rendition_exr_uses_authored_hdr_mapping pass and assert pixels differ from archive output.
  - Add a controller-level test that status text cannot claim HDR rendition unless the HDR rendition helper was called.
- Risk of fix: medium. It touches export routing and color/HDR metadata, but can be isolated behind explicit hdr_rendition.

## High Findings

### H1. ACEScg ICC profiles exist but are not mapped, breaking TIFF ICC export and display-transform ICC conversion — FIXED

- File/symbol: src/spektrafilm/utils/io.py:157, src/spektrafilm/utils/io.py:211, src/spektrafilm/utils/io.py:222, src/spektrafilm_gui/controller_runtime.py:181, src/spektrafilm_gui/controller_runtime.py:191, tests/test_image_io_color_metadata.py:294, tests/gui/test_controller_runtime_module.py:193.
- Observed problem: src/spektrafilm/data/icc/ellelstone/ACEScg-elle-V2-g10.icc and ACEScg-elle-V2-srgbtrc.icc are bundled, but _ICC_FILENAMES and _ICC_PROFILES do not include "ACEScg". resolve_icc_profile_bytes("ACEScg", cctf_encoding=False) returns None.
- Why this is a bug/risk: ACES reference workflow uses ACEScg as the scene-linear working space, but ACEScg TIFF export omits ICC metadata and display transform falls back to sRGB profile creation.
- Concrete suggested fix:
  - Add ("ACEScg", False): "ellelstone/ACEScg-elle-V2-g10.icc" to _ICC_FILENAMES.
  - Consider ("ACEScg", True): "ellelstone/ACEScg-elle-V2-srgbtrc.icc" only if the UI can genuinely produce encoded ACEScg; otherwise reject encoded ACEScg output clearly.
  - Add "ACEScg" to _ICC_PROFILES or update _known_color_space_from_icc_profile to iterate _ICC_FILENAMES variants too.
- Suggested tests:
  - Make test_acescg_tiff_icc_roundtrips_as_linear_encoding pass.
  - Add direct tests for resolve_icc_profile_bytes("ACEScg", cctf_encoding=False).
  - Add display-transform test with a fake ImageCmsProfile that proves the ICC path is used.

### H2. The GUI "Enable Path to White" toggle does not disable profile-aware HDR path-to-white — FIXED

- File/symbol: src/spektrafilm_gui/state.py:365, src/spektrafilm_gui/widget_specs.py:680, src/spektrafilm_gui/controller.py:560, src/spektrafilm_gui/controller.py:569, src/spektrafilm/utils/hdr_photo.py:95, src/spektrafilm/utils/hdr_photo.py:110, src/spektrafilm/utils/hdr_photo.py:662.
- Observed problem: the GUI state exposes path_to_white_enabled, and the controller maps it only to legacy hdr_highlight_path_to_white. Profile-aware HDR color recovery uses profile_hdr_path_to_white_strength, which remains at the default 0.30.
- Why this is a bug/risk: a user can disable path-to-white in the GUI and still get highlight desaturation/neutralization in profile-aware HDR exports.
- Concrete suggested fix:
  - In GuiController.save_output_layer, also pass profile_hdr_path_to_white_strength=0.0 when path_to_white_enabled is false.
  - If the desired default when enabled is 0.30, pass it explicitly instead of relying on HDRPhotoMapping defaults.
- Suggested tests:
  - Controller test: set gui_state.hdr_export.path_to_white_enabled=False and assert HDRPhotoMapping.profile_hdr_path_to_white_strength == 0.0.
  - HDR unit test: profile-aware highlights remain saturated when the GUI-equivalent mapping disables path-to-white.

### H3. GUI preview/full scan always computes and stores full-size HDR sidecars, creating large memory pressure — DEFERRED

- File/symbol: src/spektrafilm_gui/controller.py:926, src/spektrafilm/runtime/pipeline.py:299, src/spektrafilm/runtime/pipeline.py:140, src/spektrafilm/runtime/pipeline.py:143, src/spektrafilm/runtime/pipeline.py:542, src/spektrafilm_gui/controller.py:699, src/spektrafilm_gui/controller_layers.py:421.
- Observed problem: GuiController._process_image_with_runtime calls process_with_metadata whenever it exists, for normal preview and scan. process_with_metadata always builds scene_luminance and scene_rgb sidecars and attempts dynamic profile characterization, then the GUI stores those sidecars on the output layer.
- Why this is a bug/risk: a 4000x6000 float32 image adds about 366 MiB of sidecar arrays. This undermines the stated large RAW/low-memory priority.
- Concrete suggested fix:
  - Add a request flag to SimulationRequest such as collect_hdr_metadata.
  - Use Simulator.process() for ordinary SDR preview/scan and process_with_metadata() only when the user has enabled/needs HDR export sidecars.
  - Consider storing scene_rgb only when a mapping mode requires source RGB color recovery, or recomputing sidecars on explicit HDR export for full-resolution scans.

## Medium Findings

### M1. HDR SDR-base test expectations conflict with the current SDR-preservation implementation — FIXED

- File/symbol: src/spektrafilm/utils/hdr_photo.py:49, src/spektrafilm/utils/hdr_photo.py:454, tests/test_hdr_photo.py:24, README.md:256.
- Observed problem: HDRPhotoMapping.preserve_sdr_base defaults to True, and generic HDR rendition creation clips the original image into sdr_rgb. The first HDR photo unit test still expects diffuse white to map to sdr_paper_white=0.9.
- Concrete suggested fix:
  - Decide whether the current preserve_sdr_base=True default is the intended branch behavior.
  - If yes, update early HDR photo tests to assert SDR-base preservation and move old tone-map coverage to preserve_sdr_base=False.
  - If no, change default behavior and add regression tests proving SDR output is not globally darkened.

### M2. Modern profile-HDR mapping parameters are accepted with invalid ranges — FIXED

- File/symbol: src/spektrafilm/utils/hdr_photo.py:118, src/spektrafilm/utils/hdr_photo.py:121, src/spektrafilm/utils/hdr_photo.py:181, src/spektrafilm/utils/hdr_curve_profiles.py:892, src/spektrafilm/utils/hdr_curve_profiles.py:897.
- Observed problem: HDRPhotoMapping.__post_init__ validates profile_hdr_mode, target peak, and recovery ratio, but accepts invalid profile_hdr_normalize_percentile, negative profile_hdr_recovery_knee_ev, negative or reversed recovery spans, zero profile_hdr_max_chroma_gain, and reversed path-to-white EV ranges.
- Concrete suggested fix:
  - Extend HDRPhotoMapping.__post_init__ validation:
    - 0 < profile_hdr_normalize_percentile <= 100
    - finite profile_hdr_recovery_knee_ev >= 0
    - profile_hdr_recovery_full_ev > profile_hdr_recovery_knee_ev
    - finite profile_hdr_max_chroma_gain >= 1
    - profile_hdr_path_to_white_start_ev < profile_hdr_path_to_white_end_ev
    - 0 <= profile_hdr_path_to_white_strength <= 1

### M3. GUI HEIC tests call the real encoder and can abort pytest through QMessageBox without QApplication

- File/symbol: tests/gui/test_controller_output.py:65, tests/gui/test_controller_output.py:395, src/spektrafilm_gui/controller.py:582, src/spektrafilm_gui/controller.py:601.
- Observed problem: _capture_saved_output monkeypatches save_image_oiio and write_image_metadata, but HEIC tests exercise save_hdr_photo_heic without replacing it. When the real HEIC path raises, the controller catches it and calls QMessageBox.critical; in the test process there is no QApplication, so Qt aborts the interpreter.
- Concrete suggested fix:
  - Add a HEIC-specific capture helper that monkeypatches controller_module.save_hdr_photo_heic.
  - Monkeypatch QMessageBox.critical in error-path tests, or use a Qt test fixture that owns a QApplication.

### M4. save_image_oiio and HDR export API boundaries are unclear and inconsistent across tests/docs — FIXED

- File/symbol: src/spektrafilm/utils/io.py:477, src/spektrafilm_gui/controller.py:157, tests/test_image_io_color_metadata.py:137, tests/test_image_io_color_metadata.py:204, docs/superpowers/plans/2026-05-24-scene-energy-hdr-gainmap-autoexposure.md:55.
- Observed problem: tests and plans expect save_image_oiio to accept HEIC/HDR sidecar arguments, while the implementation treats HEIC as a controller-level special case and save_image_oiio as generic raster/EXR writing only.
- Concrete suggested fix:
  - Choose and document the ownership boundary.
  - Rename helpers if needed, for example save_standard_image_oiio, save_hdr_rendition_exr, and save_hdr_photo_heic.
  - Update tests to target the chosen API layer.

## Low Findings

### L1. README still advertises a missing src/spektrafilm_profile_creator package — STILL LIVE

- File/symbol: README.md:53.
- Observed problem: the README tree lists src/spektrafilm_profile_creator/, but the reviewed source tree contains src/spektrafilm and src/spektrafilm_gui only.
- Concrete suggested fix: update the README tree to the current packages, or restore/package the profile creator if it is still intended.

## Final Prioritized Action List

Must fix before push/integration:

1. Implement or remove/block HDR Rendition EXR mode so it cannot silently save the wrong export.
2. Fix ACEScg ICC mapping and display-transform/profile round-tripping.
3. Fix the profile-aware path-to-white GUI toggle contract.
4. Make the test suite non-aborting and reconcile the HDR SDR-base test expectation.

Should fix soon:

1. Validate all modern profile-HDR mapping parameters at construction.
2. Split normal SDR preview/scan from expensive HDR sidecar collection, or make the HDR-ready memory cost explicit.
3. Clarify save_image_oiio versus dedicated HDR helper ownership and update tests accordingly.

Optional cleanup:

1. Update the README source tree to remove or explain src/spektrafilm_profile_creator.
2. Keep generated analysis docs/artifacts clearly separated from source-reviewed behavior.

Needs user/product decision:

1. Confirm whether default HEIC SDR base should preserve the current SDR look (preserve_sdr_base=True) or continue the older sdr_paper_white=0.9 tone-map contract.
2. Decide whether HDR sidecars should always be retained after every scan for convenient later export, or only collected on explicit HDR-ready runs.
