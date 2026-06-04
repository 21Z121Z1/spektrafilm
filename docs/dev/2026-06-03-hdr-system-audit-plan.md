# HDR System Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Perform a read-first, evidence-driven audit of Spektrafilm's HDR runtime, GUI, I/O, tests, and docs, then apply only minimal tested fixes for proven blocking bugs.

**Architecture:** Treat HDR as four linked contracts: runtime scene sidecar generation, GUI state/save dispatch, I/O format routing, and HDR curve/rendition math. The audit must classify findings as implementation bugs, naming or semantic ambiguity, test gaps, environment limits, or upstream/history issues, and must preserve default SDR preview/export plus ordinary PNG/JPEG/TIFF/EXR saves.

**Tech Stack:** Python, NumPy, OpenImageIO, pytest, Qt/napari GUI controller tests, macOS CoreImage/ImageIO HEIC HDR encoder, Swift smoke checker where available.

---

## Live Baseline

- Branch: `develop`, tracking `origin/develop`.
- Current HEAD: `fa1c771 Fix profile_kind assertions and add strict HDR export fallback guardrail test`.
- Upstream baseline: `origin/develop` at `391d907 Fix negative scan positive rendering trigger logic and add tests`.
- Pre-existing untracked files observed before this audit: `debug_mlx.py`, `debug_pipeline.py`, `docs.zip`, `dump_metal.py`, `scratch_mlx_perf.py`, `test_emulsion_nan.py`, `test_kernel_math.py`, `test_mlx_reshape.py`, `test_pipeline_mlx.py`.
- These pre-existing untracked files are out of scope and must not be modified.

## File Map

- Runtime sidecar:
  - `src/spektrafilm/runtime/pipeline.py`
  - `src/spektrafilm/runtime/process.py`
  - `tests/test_runtime_api.py`
- HDR curve and gain-map math:
  - `src/spektrafilm/utils/hdr_photo.py`
  - `src/spektrafilm/utils/hdr_curve_profiles.py`
  - `src/spektrafilm/data/hdr_curve_profiles/curve_profiles_v2.json`
  - `src/spektrafilm/data/hdr_curve_profiles/samples/*.json`
  - `tests/test_hdr_photo.py`
  - `tests/test_hdr_curve_profiles.py`
  - `tests/test_hdr_profile_validation_tool.py`
- Image I/O and format dispatch:
  - `src/spektrafilm/utils/io.py`
  - `src/spektrafilm/data/macos/hdr_heif_encoder.swift`
  - `tests/test_image_io_color_metadata.py`
  - `tests/test_gain_map.py`
- GUI state, widgets, persistence, and save dispatch:
  - `src/spektrafilm_gui/hdr_settings.py`
  - `src/spektrafilm_gui/options.py`
  - `src/spektrafilm_gui/param_manifest.py`
  - `src/spektrafilm_gui/widgets.py`
  - `src/spektrafilm_gui/state.py`
  - `src/spektrafilm_gui/state_bridge.py`
  - `src/spektrafilm_gui/persistence.py`
  - `src/spektrafilm_gui/controller_runtime.py`
  - `src/spektrafilm_gui/controller.py`
  - `tests/gui/test_controller_output.py`
  - `tests/gui/test_layout.py`
  - `tests/gui/test_persistence.py`
  - `tests/gui/test_state_bridge.py`
  - `tests/gui/test_widgets.py`
- Required audit docs:
  - `docs/README.md`
  - `docs/README_zh.md`
  - `docs/color-management-hdr-review-2026-05-31.md`
  - `docs/profile-aware-hdr-audit-plan.md`
  - `docs/profile-aware-hdr-audit-plan_zh.md`
  - `docs/profile-aware-hdr-audit-report.md`
  - `docs/film-scan-aware-hdr.md`
  - `docs/film-scan-aware-negative-positive-plan.md`
  - `docs/hdr_exr_output_plan.md`
  - `docs/hdr_profile_aware_raw_validation.md`
  - `docs/hdr_profile_aware_raw_validation.json`
  - `docs/dev/2026-06-02-restore-hdr-export-settings-after-gui-refactor.md`
  - `docs/dev/modern_recovery_peak_budget_plan.md`
- New audit outputs:
  - Create: `docs/dev/2026-06-03-hdr-system-audit-plan.md`
  - Create: `docs/dev/2026-06-03-hdr-system-audit-report.md`
- If a blocking bug is proven:
  - Modify only the minimal source/test files required by the failing test.
  - Update `docs/dev/2026-06-03-hdr-system-audit-report.md` with the fix and evidence.

## Task 1: Requested Repo And Documentation Baseline

**Files:**
- Read: `src/`, `tests/`, `docs/`, `tools/`, `scripts/`, `macos/`
- Create: `docs/dev/2026-06-03-hdr-system-audit-plan.md`

- [x] **Step 1: Run repository status**

Run:

```bash
git status -sb
```

Expected: record the branch, ahead/behind state, and any pre-existing untracked files.

- [x] **Step 2: Run recent history baseline**

Run:

```bash
git log --oneline --decorate -n 50
```

Expected: record the current HEAD, upstream baseline, and recent HDR/GPU/GUI changes that may affect the audit.

- [x] **Step 3: Run requested HDR grep**

Run:

```bash
git grep -nE "hdr_mapping_mode|HDRMappingModes|HDR mapping|film_scan_aware|profile_aware|profile_preserving|modern_recovery_peak_budget|hdr_mapping_kwargs|OUTPUT_HDR_SCENE_ENERGY|scene_luminance|scene_energy|hdr_scene_energy|sample_runtime.*curve|gain map|gainmap|HDRGainMap|save_hdr|save_hdr_photo|writeHEIF|auxC|tmap|EXR|ACES|diffuse_white|headroom" -- src tests docs tools scripts macos
```

Expected: use live matches to identify current source, test, and doc surfaces. Do not treat `docs/archive/` as current fact unless live code or tests support it.

- [ ] **Step 4: Read required docs and cross-check against live code**

Read the required docs listed in the File Map. For each doc, classify claims as current, stale, historical, or environment-gated by checking live source and tests.

## Task 2: Runtime HDR Data Flow Audit

**Files:**
- Read: `src/spektrafilm/runtime/pipeline.py`
- Read: `src/spektrafilm/runtime/process.py`
- Read/Test: `tests/test_runtime_api.py`

- [ ] **Step 1: Trace `process()`**

Confirm `SimulationPipeline.process()` calls `_process_result(..., include_metadata=False)` and returns only `.image`, preserving the SDR/runtime output contract.

- [ ] **Step 2: Trace `process_with_metadata()`**

Confirm `SimulationPipeline.process_with_metadata()` returns `SimulationPipelineResult(image, hdr_scene_energy)` and that `_pipeline_with_metadata()` uses the same print/scan path as `_pipeline()`.

- [ ] **Step 3: Trace sidecar generation**

Confirm `_preprocess_with_metadata()` builds `HDRSceneEnergyMetadata(scene_luminance, auto_exposure_ev, input_color_space, input_cctf_decoding)` after auto exposure and crop/resize, and `_scene_luminance()` returns finite non-negative float32 luminance.

- [ ] **Step 4: Verify process parity**

Run a synthetic runtime comparison proving `process()` and `process_with_metadata().image` match for SDR output, or document the exact difference and cause.

## Task 3: GUI HDR State And Save Dispatch Audit

**Files:**
- Read: `src/spektrafilm_gui/hdr_settings.py`
- Read: `src/spektrafilm_gui/options.py`
- Read: `src/spektrafilm_gui/param_manifest.py`
- Read: `src/spektrafilm_gui/widgets.py`
- Read: `src/spektrafilm_gui/state.py`
- Read: `src/spektrafilm_gui/state_bridge.py`
- Read: `src/spektrafilm_gui/persistence.py`
- Read: `src/spektrafilm_gui/controller_runtime.py`
- Read: `src/spektrafilm_gui/controller.py`
- Test: `tests/gui/test_controller_output.py`
- Test: `tests/gui/test_layout.py`
- Test: `tests/gui/test_persistence.py`
- Test: `tests/gui/test_state_bridge.py`
- Test: `tests/gui/test_widgets.py`

- [ ] **Step 1: Verify independent HDR GUI state**

Confirm `GuiState.hdr` is separate from runtime compute settings and includes `hdr_mapping_mode`, `hdr_heic_gain_map_enabled`, scene source, diffuse white, peak headroom, headroom mode, percentile, SDR preservation, gain-map mode, and HEIC quality.

- [ ] **Step 2: Verify state bridge and persistence**

Confirm `apply_gui_state()` and `collect_gui_state()` include the HDR section and `gui_state_to_dict()` / `gui_state_from_dict()` round-trip HDR fields without leaking into compute/backend settings.

- [ ] **Step 3: Verify controller output sidecar**

Confirm `SimulationResult.hdr_scene_energy` is attached to output layer metadata under `OUTPUT_HDR_SCENE_ENERGY_KEY`.

- [ ] **Step 4: Verify save dispatch guards**

Confirm ordinary PNG/JPEG/TIFF/scene-linear EXR save paths do not pass `hdr_mapping_kwargs`, `scene_luminance`, or `scene_rgb`.

- [ ] **Step 5: Verify explicit HEIC/HDR path**

Confirm `.heic`/`.heif` requires `hdr_heic_gain_map_enabled=True`, builds `hdr_mapping_kwargs` from `GuiState.hdr`, passes sidecars for profile-aware modes, and fails loudly when required sidecar data is missing.

- [ ] **Step 6: Verify HEIC linear encoding contract**

Check whether GUI HEIC save can reach `save_image_oiio()` with an explicit linear `ColorEncoding(clip_highlights=False)`. If default GUI saving settings make HEIC unreachable, prove it with a failing test before classifying it as a blocking bug.

## Task 4: HDR Curve And Rendition Invariants

**Files:**
- Read: `src/spektrafilm/utils/hdr_photo.py`
- Read: `src/spektrafilm/utils/hdr_curve_profiles.py`
- Test: `tests/test_hdr_photo.py`
- Test: `tests/test_hdr_curve_profiles.py`

- [ ] **Step 1: Validate mapping mode routing**

Confirm `generic`, `profile_aware`, and `film_scan_aware` dispatch to the intended path and reject invalid modes.

- [ ] **Step 2: Validate scene sidecar requirements**

Confirm `profile_aware` and `film_scan_aware` require `scene_luminance`, and missing sidecars fail before writing fake HDR or ordinary HEIC.

- [ ] **Step 3: Validate diffuse-white normalization**

Confirm profile-aware scene luminance is normalized once by `mapping.diffuse_white` and that `diffuse_white_override` is used only as the profile-curve white reference.

- [ ] **Step 4: Validate profile math**

Run neutral-ramp experiments confirming:

```text
s_profile finite, non-negative, non-decreasing
h_profile finite, non-negative, non-decreasing
hdr_gain = h_profile / max(s_profile, eps) finite and smooth
h_profile >= s_profile * profile_hdr_min_gain within tolerance, unless a mode explicitly documents compression and tests it
```

- [ ] **Step 5: Validate headroom cap semantics**

Check `HDRPhotoMapping.max_headroom` against profile `safe_max_headroom`. If profile-aware output can exceed the mapping-level cap, prove with a failing test and classify severity before fixing.

- [ ] **Step 6: Validate modern recovery peak budget**

Confirm `modern_recovery_peak_budget` scales only recovery gain and does not change the profile baseline. Confirm reported headroom is derived from rendered content or gain-map requirement, not a blind copy of target EV.

- [ ] **Step 7: Validate color recovery order**

Confirm source chroma or bounded look chroma is applied before path-to-white and gamut compression, and that compression does not unboundedly change luminance.

- [ ] **Step 8: Validate film-scan semantics**

Confirm `film_scan_aware` uses positive, monotone, positive-rendered film-scan profiles; raw negative scan profiles are diagnostic only; positive/reversal film does not go through negative inversion.

## Task 5: Image I/O And Format Path Audit

**Files:**
- Read: `src/spektrafilm/utils/io.py`
- Read: `src/spektrafilm/data/macos/hdr_heif_encoder.swift`
- Test: `tests/test_image_io_color_metadata.py`
- Test: `tests/test_gain_map.py`

- [ ] **Step 1: Verify ordinary save behavior**

Confirm ordinary PNG/JPEG/TIFF and scene-linear archive EXR ignore HDR mapping sidecars and preserve existing encoding/clip behavior.

- [ ] **Step 2: Verify HEIC/HEIF HDR path**

Confirm `save_image_oiio()` requires an explicit linear unclipped `ColorEncoding` for HEIC/HEIF, constructs `HDRPhotoMapping`, and calls `save_hdr_photo_heic()` with color space, quality, sidecars, and gain-map mode.

- [ ] **Step 3: Verify EXR modes**

Confirm `exr_mode="scene_linear_archive"` writes unchanged linear data and `exr_mode="hdr_rendition"` applies HDR mapping and records `whiteLuminance` plus `hdrHeadroom`.

- [ ] **Step 4: Verify ACES and CCTF contracts**

Confirm ACES/scene-linear preview and save paths preserve highlight data until the SDR display transform, while PNG/JPEG display saves require CCTF-encoded data.

## Task 6: Required Pytest Verification

**Files:**
- Test: `tests/test_hdr_photo.py`
- Test: `tests/test_hdr_curve_profiles.py`
- Test: `tests/test_image_io_color_metadata.py`
- Test: `tests/gui/test_controller_output.py`
- Test: `tests/gui/test_layout.py`
- Test: `tests/gui/test_persistence.py`
- Test: `tests/gui/test_state_bridge.py`
- Test: `tests/gui/test_widgets.py`
- Test: `tests/gui`

- [ ] **Step 1: Run HDR photo tests**

Run:

```bash
uv run --extra dev pytest tests/test_hdr_photo.py -q
```

- [ ] **Step 2: Run HDR curve profile tests**

Run:

```bash
uv run --extra dev pytest tests/test_hdr_curve_profiles.py -q
```

- [ ] **Step 3: Run image I/O color metadata tests**

Run:

```bash
uv run --extra dev pytest tests/test_image_io_color_metadata.py -q
```

- [ ] **Step 4: Run GUI controller output tests**

Run:

```bash
uv run --extra dev pytest tests/gui/test_controller_output.py -q
```

- [ ] **Step 5: Run GUI state/layout/widget tests**

Run:

```bash
uv run --extra dev pytest tests/gui/test_layout.py tests/gui/test_persistence.py tests/gui/test_state_bridge.py tests/gui/test_widgets.py -q
```

- [ ] **Step 6: Run full GUI tests**

Run:

```bash
uv run --extra dev pytest tests/gui -q
```

## Task 7: Minimal Synthetic Experiments

**Files:**
- Temporary scripts or one-off Python snippets only unless a blocking bug is proven.
- Possible permanent tests only after a red/green loop proves a production bug.

- [ ] **Step 1: Neutral ramp**

Use `prepare_hdr_photo_renditions()` and `build_profile_preserving_hdr_curve()` to verify monotonic `s_profile`, monotonic `h_profile`, finite gain, and profile-min-gain behavior.

- [ ] **Step 2: Exposure scaling sample**

Verify the SDR base follows the user-authored look while HDR gain is based on sidecar/profile energy, not user exposure as physical profile input.

- [ ] **Step 3: Hot-pixel sample**

Verify robust percentile/headroom is not dominated by one high-value pixel unless `headroom_percentile=100`.

- [ ] **Step 4: Nonmonotonic profile**

Verify unsafe nonmonotonic/decreasing profiles are rejected and cannot generate fake HDR.

- [ ] **Step 5: Colored highlight sample**

Verify source chroma, bounded look chroma, path-to-white, and gamut compression order.

- [ ] **Step 6: Missing sidecar sample**

Verify profile-aware and film-scan-aware HEIC export fails loudly without `scene_luminance`.

- [ ] **Step 7: Negative and positive/reversal film samples**

Verify negative-film raw scan is not used directly as HDR gain profile, negative scans are positive-rendered for `film_scan_aware`, and positive/reversal film does not use negative inversion.

## Task 8: Real RAW And HEIC/HDR Smoke Validation

**Files:**
- Tool: `tools/validate_profile_aware_hdr_raw_samples.py`
- Output: `docs/dev/2026-06-03-hdr-system-raw-validation.md` if local RAW samples exist.
- Output: `docs/dev/2026-06-03-hdr-system-audit-report.md`

- [ ] **Step 1: Check for local RAW sample directory**

Use only a real local RAW/DNG/JPEG batch directory if discoverable or already known. If absent, record this as an environment limitation.

- [ ] **Step 2: Run real RAW validation if possible**

Run:

```bash
uv run python tools/validate_profile_aware_hdr_raw_samples.py --sample-dir "<local RAW_DNG_JPEG batch export directory>" --max-samples 4 --output docs/dev/2026-06-03-hdr-system-raw-validation.md --diagnostic-scan-limit 32
```

- [ ] **Step 3: Generate synthetic tiny HDR HEIC**

Use a tiny float32 linear Display P3 image plus scene sidecar through `save_image_oiio(..., encoding=ColorEncoding(...linear..., clip_highlights=False), hdr_mapping_kwargs=...)`.

- [ ] **Step 4: Generate GUI/CLI HEIC path smoke**

Exercise the GUI controller save dispatch into a real `save_image_oiio()` call where the local macOS toolchain permits it. If GUI requires a linear saving setting for HEIC, record that in the report and decide whether it is a usability/semantic issue or a blocking export bug.

- [ ] **Step 5: Inspect HEIC evidence levels**

Run available checks:

```bash
file <output.heic>
sips -g pixelWidth -g pixelHeight <output.heic>
mdls <output.heic>
strings <output.heic> | rg "tmap|auxC|auxl|urn:mpeg:hevc:2015:auxid|HDR|Gain|gain"
```

If feasible, add or run a temporary Swift/ImageIO checker to query auxiliary data and headroom metadata.

- [ ] **Step 6: Classify HEIC confidence**

In the report, distinguish:

```text
Level 1: File structure contains HDR/gain-map markers.
Level 2: ImageIO/CoreImage can read auxiliary gain-map/headroom metadata.
Level 3: Apple Photos/CoreImage actually triggers HDR headroom on display hardware.
```

Level 3 is allowed to remain device/environment-limited if no suitable display/device validation is available.

## Task 9: Blocking Bug Fix Gate

**Files:**
- Modify production source only if Tasks 1-8 prove a blocking bug.
- Modify tests before source code for every fix.
- Modify: `docs/dev/2026-06-03-hdr-system-audit-report.md`

- [ ] **Step 1: Apply systematic debugging**

For each suspected blocker, document root cause, reproduction, working reference path, and the exact invariant it violates.

- [ ] **Step 2: Write the failing test first**

Add the smallest failing pytest test that proves the blocker. Run it and record the failing output.

- [ ] **Step 3: Implement the minimal fix**

Change only the production lines needed to make the failing test pass. Do not refactor unrelated HDR, SDR, GUI, I/O, or docs surfaces.

- [ ] **Step 4: Run the fixed test and affected suite**

Run the new test, then the narrow affected suite, then the requested broader suite.

- [ ] **Step 5: Update audit report**

For every fixed finding, record file, function, evidence, impact, fix, test, and verification result.

## Task 10: Audit Report And Completion Verification

**Files:**
- Create/Update: `docs/dev/2026-06-03-hdr-system-audit-report.md`

- [ ] **Step 1: Write report sections**

The report must include:

```text
Executive summary
Current HDR architecture/data flow
Verified-passing invariants
Failed/risk items by Critical/Major/Minor/Non-issue
Per-finding: file, function, evidence, impact, suggested fix, fixed status, corresponding test
Test commands and complete results
Real HEIC/HDR smoke results
Environment limitations
Confidence loop
```

- [ ] **Step 2: Confidence loop**

End the report by asking: "Do I have factual 100% confidence in the current conclusions?" If not, list the highest-risk gaps and keep validating until the remaining uncertainty is only environment/device-limited.

- [ ] **Step 3: Final verification commands**

Run:

```bash
git diff --check
git status -sb
```

Also rerun any test command affected by a production fix.

