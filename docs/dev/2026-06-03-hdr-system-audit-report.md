# HDR System Audit Report

Date: 2026-06-04

Scope: runtime HDR sidecar flow, GUI HDR state/save dispatch, image I/O routing, HDR curve/rendition math, RAW validation, HEIC smoke checks, tests, and docs. This is a current-tree revalidation of the existing 2026-06-03 report.

## Executive Summary

- Current audited tree: `develop` at `d9e31d2`, with additional uncommitted local changes present outside this audit. I did not revert or edit those source/test changes.
- No new production HDR blocking bug was proven in this pass, so I did not change production behavior.
- The previously reported implementation bug is still fixed: profile-aware and film-scan-aware HDR now cap output by `min(mapping.max_headroom, profile.defaults.safe_max_headroom)`.
- Default SDR preview/export and ordinary PNG/JPEG/TIFF/default EXR save behavior remain outside HDR mapping kwargs.
- The provided RAW historical archive triggered a loud no-fake-HDR rejection on `IMG_4865.DNG`; the adjacent converted-DNG batch completed real RAW validation with 4/4 samples passing sidecar, metadata, JPEG probe, and EXR attribute checks.
- HEIC smoke succeeded for one synthetic tiny HEIC and one RAW-derived CLI HEIC. File/parser markers and ImageIO headroom properties are present; this pass did not verify Apple Photos or Android Gallery rendered HDR activation.

## Current HDR Architecture And Data Flow

Runtime path:

```text
input image / RAW
-> Simulator.process() or Simulator.process_with_metadata()
-> SimulationPipeline._preprocess_base()
-> print or scan pipeline
-> SimulationPipelineResult(image, hdr_scene_energy?)
```

- `SimulationPipeline.process()` returns `_process_result(..., include_metadata=False).image`, preserving the plain image API.
- `SimulationPipeline.process_with_metadata()` returns the same output plus `HDRSceneEnergyMetadata`.
- `_preprocess_with_metadata()` records `scene_luminance`, auto-exposure EV, input color space, and input CCTF decoding after auto exposure and crop/rescale.

GUI path:

```text
GuiState.hdr
-> HDR manifest/widgets/state bridge/persistence
-> controller output layer metadata
-> save_output_layer()
-> _save_output_kwargs()
```

- `GuiState.hdr` is independent from ordinary simulation output/save settings.
- Non-HEIC/HEIF saves return only `color_space` and `cctf_encoding`.
- Explicit HEIC/HEIF gain-map export requires `hdr_heic_gain_map_enabled=True`.
- `profile_aware` and `film_scan_aware` HEIC export require `scene_luminance` and fail loudly if the sidecar is missing.

I/O and format path:

```text
save_image_oiio()
-> HEIC/HEIF: explicit linear unclipped ColorEncoding -> save_hdr_photo_heic()
-> EXR scene_linear_archive: writes provided linear pixels
-> EXR hdr_rendition: applies HDR mapping and records HDR metadata
-> PNG/JPEG: requires CCTF-encoded data, clips to display integer output
```

HDR mapping path:

```text
generic: optional scene_luminance graft -> content headroom
profile_aware: print-scan profile + scene sidecar -> h_profile / s_profile gain
film_scan_aware: positive film-scan profile + scene sidecar -> h_profile / s_profile gain
modern_recovery_peak_budget: budgets recovery gain EV only; does not rewrite profile baseline
```

## Verified-Passing Invariants

- Default non-HEIC saves do not pass `hdr_mapping_kwargs`, `scene_luminance`, or `scene_rgb`.
- `process()` and `process_with_metadata().image` match on RAW-derived validation samples with max absolute difference about `2.98e-08`.
- `profile_aware` requires `scene_luminance`.
- `s_profile` and `h_profile` are finite, non-negative, and monotone on the neutral-ramp probe.
- `hdr_gain = h_profile / max(s_profile, eps)` is finite and smooth on the neutral-ramp probe.
- `h_profile >= s_profile * profile_hdr_min_gain` holds on the probe.
- Mapping-level `max_headroom` is honored below profile `safe_max_headroom`.
- Headroom is derived from rendered content/profile gain, not copied directly from target EV.
- A single hot pixel does not dominate percentile headroom at `headroom_percentile=99.0`.
- Unsafe decreasing/raw negative profiles are rejected.
- `film_scan_aware` uses positive-rendered negative-film profiles and does not negative-render positive/reversal film.
- ACES/scene-linear preview/save docs remain aligned with current code: ACES preview preserves scene highlights before SDR output transform; normal SDR defaults remain `sRGB + CCTF`.

## Findings

### Critical

No current Critical HDR implementation bug was proven.

### Major

#### F-1: Historical implementation bug remains fixed

- Category: implementation bug, fixed before this revalidation.
- File/function: `src/spektrafilm/utils/hdr_photo.py`, `_prepare_curve_profile_renditions()`.
- Evidence: current code computes `effective_max_headroom = min(float(mapping.max_headroom), float(profile.defaults.safe_max_headroom))` and uses it for color recovery, clipping, and final headroom.
- Impact if unfixed: user-selected HDR headroom caps could be exceeded in profile-aware or film-scan-aware export.
- Suggested fix: already applied; keep the cap regression.
- Fixed status: fixed.
- Corresponding test: `tests/test_hdr_photo.py::test_profile_aware_mapping_respects_mapping_headroom_below_profile_safe_cap`; full `tests/test_hdr_photo.py` passed.

#### F-2: RAW validator aborts on no-headroom selected historical sample

- Category: test/validation tooling gap.
- File/function: `tools/validate_profile_aware_hdr_raw_samples.py`, `_validate_sample()`.
- Evidence: running the user-provided archive path selected `IMG_4865.DNG` and aborted with `ValueError: HEIC HDR photo export requires linear image values above SDR white (1.0).`
- Impact: the validator cannot produce a partial report for mixed RAW archives where a selected sample has no valid HDR headroom. This does not prove production should generate HDR; the production guard is correct because it prevents fake HDR.
- Suggested fix: future validator work should record the sample as `no_hdr_headroom_rejected` and continue to the next candidate.
- Fixed status: not fixed in this audit because it is a validation-tool gap, not a production HDR blocker.
- Corresponding test: none added in this pass.

### Minor

#### F-3: `profile_aware` naming still needs semantic guardrails

- Category: naming/semantic ambiguity.
- File/function: docs and `HDRPhotoMapping.hdr_mapping_mode`.
- Evidence: `profile_aware` uses the SDR print/profile look plus scene sidecar for authored HDR recovery; it is not physical HDR paper output.
- Impact: users may overinterpret the mode as "the print profile itself becomes HDR."
- Suggested fix: continue documenting it as print/profile-aware HDR recovery and keep `film_scan_aware` as a separate positive film-scan route.
- Fixed status: documented in current docs; still worth preserving in UI wording.
- Corresponding test: not applicable.

#### F-4: HEIC export UX depends on linear save settings

- Category: UX/test boundary.
- File/function: `src/spektrafilm_gui/controller.py`, `_save_output_kwargs()` and `src/spektrafilm/utils/io.py`, `save_image_oiio()`.
- Evidence: HEIC/HEIF HDR export requires explicit linear, unclipped `ColorEncoding`; default GUI save CCTF remains true to preserve SDR behavior.
- Impact: users must explicitly use the HDR HEIC path/settings; changing the default would risk ordinary SDR export behavior.
- Suggested fix: future UX pass could add extension-aware prompting or HEIC-only linearization.
- Fixed status: not fixed in this audit; not a current implementation blocker.
- Corresponding test: `tests/gui/test_controller_output.py` covers HEIC dispatch and ordinary-save guardrails.

### Non-Issue / Environment / History

#### F-5: HEIC marker levels are distinct from rendered HDR activation

- Category: environment limitation.
- File/function: `src/spektrafilm/data/macos/hdr_heif_encoder.swift`, host ImageIO/metadata tools.
- Evidence: `strings` and `exiftool` show `tmap`, `auxC`, auxiliary HEVC ID, BT.2020/PQ auxiliary profile, and ImageIO `Headroom`; `CGImageSourceCopyAuxiliaryDataInfoAtIndex(..., kCGImageAuxiliaryDataTypeHDRGainMap)` returned nil on this host.
- Impact: this pass can confirm file structure and ImageIO properties, but not Apple Photos or Android Gallery display activation.
- Suggested fix: keep a device/display runbook for Level 3 rendered acceptance.
- Fixed status: environment-limited.
- Corresponding test: HEIC smoke commands below.

#### F-6: Uncommitted workspace changes are outside this audit

- Category: upstream/history/workspace state.
- File/function: current dirty worktree.
- Evidence: `git status -sb` shows modified GPU, runtime, GUI, docs, and test files beyond the audit docs.
- Impact: this report validates the current live tree, but unrelated dirty files should not be attributed to this audit.
- Suggested fix: isolate or commit those changes separately before publishing.
- Fixed status: not applicable.
- Corresponding test: final `git status -sb`.

## Test Commands And Results

Passing targeted gates:

```bash
uv run --extra dev pytest tests/test_hdr_photo.py -q
```

Result: `146 passed in 21.76s`.

```bash
uv run --extra dev pytest tests/test_hdr_curve_profiles.py -q
```

Result: `35 passed in 1.06s`.

```bash
uv run --extra dev pytest tests/test_image_io_color_metadata.py -q
```

Result: `26 passed in 0.15s`.

```bash
uv run --extra dev pytest tests/gui/test_controller_output.py -q
```

Result: `21 passed in 0.82s`.

```bash
uv run --extra dev pytest tests/gui/test_layout.py tests/gui/test_persistence.py tests/gui/test_state_bridge.py tests/gui/test_widgets.py -q
```

Result: `45 passed in 3.81s`.

```bash
uv run --extra dev pytest tests/gui -q
```

Result after current workspace changes settled: `176 passed in 2.26s`.

```bash
uv run --extra dev pytest tests/gui/test_controller_flow.py -q
```

Result: `33 passed in 0.67s`.

Real RAW validation, successful converted-DNG batch:

```bash
uv run python tools/validate_profile_aware_hdr_raw_samples.py --sample-dir "/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片/RAW_DNG_JPEG_批量导出" --max-samples 4 --output docs/dev/2026-06-03-hdr-system-raw-validation.md --diagnostic-scan-limit 32
```

Result: wrote `docs/dev/2026-06-03-hdr-system-raw-validation.md` and `.json`; 4 selected samples passed sidecar finite/nonnegative, process parity, Android Ultra HDR metadata, ISO metadata roundtrip, JPEG gain-map probe, and EXR attribute checks.

Historical archive attempt:

```bash
uv run python tools/validate_profile_aware_hdr_raw_samples.py --sample-dir "/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片/RAW_DNG_历史批量归档" --max-samples 4 --output docs/dev/2026-06-03-hdr-system-raw-validation.md --diagnostic-scan-limit 32
```

Result: failed on `IMG_4865.DNG` with a correct no-fake-HDR guard: `HEIC HDR photo export requires linear image values above SDR white (1.0).`

## Minimal Experiment Results

```json
{
  "neutral_ramp": {
    "s_profile_finite_nonnegative_monotone": true,
    "h_profile_finite_nonnegative_monotone": true,
    "gain_finite_smooth": true,
    "min_gain_respected": true,
    "headroom": 1.5476043224334717
  },
  "exposure_scaled_user_look": {
    "sdr_tracks_scaled_look": true,
    "gain_independent_of_user_scale": true
  },
  "hot_pixel": {
    "p99_headroom": 4.509138584136963,
    "p100_headroom": 7.9512939453125,
    "single_hot_pixel_not_p99_dominant": true
  },
  "rejections": {
    "nonmonotonic_or_decreasing_profile": "profile_aware requires a safe increasing curve profile, but got unsafe decreasing.",
    "missing_sidecar": "profile-aware HDR mapping requires a scene luminance sidecar.",
    "raw_negative_film_scan_profile": "film_scan_aware requires a safe increasing curve profile, but got unsafe decreasing."
  },
  "colored_highlight": {
    "finite": true,
    "bounded_by_headroom": true,
    "diagnostics": []
  },
  "film_scan": {
    "negative_auto_kind": "positive_negative_scan",
    "negative_auto_safe": true,
    "negative_auto_has_render": true,
    "positive_auto_kind": "positive_film_scan",
    "positive_auto_has_render": false,
    "positive_negative_runtime_diagnostics": ["negative_scan_positive_rendering"]
  }
}
```

## HEIC / HDR Smoke Results

Generated:

- `/tmp/spektrafilm-hdr-system-smoke-20260604/synthetic_tiny_profile_aware.heic`, 4x2, 2201 bytes.
- `/tmp/spektrafilm-hdr-system-smoke-20260604/raw_img_1476_profile_aware.heic`, 768x576, 218665 bytes.

File and primary-image checks:

```text
file: ISO Media, HEIF Image HEVC Main or Main Still Picture Profile
sips synthetic: pixelWidth=4, pixelHeight=2, format=heic, space=RGB
sips RAW: pixelWidth=768, pixelHeight=576, format=heic, space=RGB
heif-convert synthetic: File contains 1 image; wrote PNG
```

Level 1, file structure markers:

```text
tmap
auxl
auxC
urn:mpeg:hevc:2015:auxid:1
rhvcC/qhvcC or phvcC/ohvcC
```

Level 2, metadata/tool recognition:

```text
exiftool: CompatibleBrands = mif1, tmap, MiHE, miaf, MiHB, heic
exiftool: AuxiliaryImageType = urn:mpeg:hevc:2015:auxid:1
exiftool: auxiliary profile = BT.2020/BT.2100 PQ
ImageIO synthetic: Headroom = 3.653502, ProfileName = Display P3
ImageIO RAW: Headroom = 1.301261, ProfileName = Display P3
ImageIO HDR auxiliary dictionary: nil on this host
```

Level 3, rendered HDR activation:

- Not verified in this pass. Apple Photos/CoreImage display-headroom activation and Android Gallery/Ultra HDR rendering remain device/app validation tasks.

## Environment Limitations

- The current worktree is dirty with unrelated modified source/test/docs files. The audit report and raw-validation doc are the only intentional audit artifacts from this pass.
- The provided historical RAW archive contains at least one sample that correctly fails HDR rendition due no above-SDR headroom. The validator currently aborts instead of continuing, so that specific archive did not produce a report.
- ImageIO exposed `Headroom` properties but not `kCGImageAuxiliaryDataTypeHDRGainMap` dictionaries on this host.
- Device/display-level HDR activation was not verified.

## Final Hygiene

```bash
git diff --check
```

Result: passed with no output.

```bash
git status -sb
```

Result: `develop...origin/develop` with a large dirty worktree. Audit-owned files from this pass are:

- `docs/dev/2026-06-03-hdr-system-audit-plan.md`
- `docs/dev/2026-06-03-hdr-system-audit-report.md`
- `docs/dev/2026-06-03-hdr-system-raw-validation.md`
- `docs/dev/2026-06-03-hdr-system-raw-validation.json`

Other modified/untracked source, test, docs, benchmark, and research files were already present or appeared as unrelated workspace state and were not reverted.

## Confidence Loop

Do I have factual 100% confidence in the current conclusions?

For code-level and local-file conclusions, yes: runtime sidecar generation, GUI dispatch, I/O routing, profile/film-scan invariants, RAW validation on the converted batch, and HEIC file markers were verified against the current tree.

For external rendered HDR acceptance, no: Apple Photos and Android Gallery behavior remains device/app-limited. The highest remaining risk is not a code-path blocker proven here; it is whether third-party viewers activate HDR headroom from the generated HEICs on real display hardware. That residual uncertainty is explicitly environment/device-limited.
