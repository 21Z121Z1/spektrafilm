# HDR System Audit Report

Date: 2026-06-03

Scope: runtime HDR sidecar flow, GUI HDR save dispatch, image I/O routing, HDR curve/rendition math, HEIC encoder smoke tests, and targeted regression coverage.

## Executive Result

- Fixed one proven HDR-only implementation bug: profile-aware and film-scan-aware HDR renditions could exceed the user-selected `HDRPhotoMapping.max_headroom` when the curve profile's `safe_max_headroom` was higher.
- No changes were made to default SDR preview/export behavior.
- No changes were made to ordinary PNG/JPEG/TIFF saving or scene-linear archive EXR behavior.
- The only production source change is in the HDR profile rendition path: `src/spektrafilm/utils/hdr_photo.py`.
- Added one regression test in `tests/test_hdr_photo.py`.

## Changed Files

- `src/spektrafilm/utils/hdr_photo.py`
  - `_prepare_curve_profile_renditions()` now uses `min(mapping.max_headroom, profile.defaults.safe_max_headroom)` as the effective cap for HDR color recovery, clipping, and reported headroom.
- `tests/test_hdr_photo.py`
  - Added `test_profile_aware_mapping_respects_mapping_headroom_below_profile_safe_cap()`.
- `docs/dev/2026-06-03-hdr-system-audit-plan.md`
  - Plan artifact requested by the audit.
- `docs/dev/2026-06-03-hdr-system-audit-report.md`
  - This report.

## Source Contract Map

Runtime:

- `SimulationPipeline.process()` returns `_process_result(..., include_metadata=False).image`, preserving the plain image API (`src/spektrafilm/runtime/pipeline.py:166`).
- `SimulationPipeline.process_with_metadata()` returns the same pipeline output plus `HDRSceneEnergyMetadata` (`src/spektrafilm/runtime/pipeline.py:172`).
- Metadata is produced after auto exposure and crop/rescale, then stores finite non-negative scene luminance and input color interpretation (`src/spektrafilm/runtime/pipeline.py:412`, `src/spektrafilm/runtime/pipeline.py:428`).

GUI save dispatch:

- Non-HEIC/HEIF saves return only `color_space` and `cctf_encoding`; no HDR mapping sidecar is passed (`src/spektrafilm_gui/controller.py:421`).
- HEIC/HEIF requires `hdr_heic_gain_map_enabled=True` and fails loudly for missing profile/film scene-luminance sidecars (`src/spektrafilm_gui/controller.py:437`).
- GUI HDR settings map `hdr_peak_headroom` to `HDRPhotoMapping.max_headroom` (`src/spektrafilm_gui/controller.py:464`).

Image I/O:

- HEIC/HEIF HDR export requires an explicit linear `ColorEncoding`, rejects CCTF-encoded input, and rejects clipped highlights (`src/spektrafilm/utils/io.py:643`).
- Ordinary PNG/JPEG paths still clip to display integer output and return empty HDR diagnostics (`src/spektrafilm/utils/io.py:688`).
- Scene-linear archive EXR remains unchanged; only `exr_mode="hdr_rendition"` invokes HDR mapping (`src/spektrafilm/utils/io.py:668`).

HEIC encoder:

- The Swift encoder writes a primary SDR image with `CIImageRepresentationOption.hdrImage`, `hdrGainMapAsRGB`, and content headroom (`src/spektrafilm/data/macos/hdr_heif_encoder.swift:111`, `src/spektrafilm/data/macos/hdr_heif_encoder.swift:130`).

## Findings

### F-1: Implementation Bug, Fixed

Profile-aware and film-scan-aware HDR used `profile.defaults.safe_max_headroom` as the render cap and final headroom cap, ignoring a lower user-selected `mapping.max_headroom`.

Pre-fix proof:

```text
test_profile_aware_mapping_respects_mapping_headroom_below_profile_safe_cap
expected mapping.max_headroom <= 2.0
actual renditions.headroom = 2.6889960765838623
actual max HDR payload = 2.527656316757202
profile safe cap = 6.0
```

Fix:

```python
effective_max_headroom = min(float(mapping.max_headroom), float(profile.defaults.safe_max_headroom))
```

This cap is now used for color recovery, clipping, and final headroom (`src/spektrafilm/utils/hdr_photo.py:638`). The fix is limited to the profile/film HDR rendition path and does not affect generic SDR or ordinary format saves.

### F-2: Test Gap, Fixed

The generic path already capped by `mapping.max_headroom`, but the profile-aware path did not have a regression for "mapping cap lower than profile safe cap." Added coverage at `tests/test_hdr_photo.py:740`.

### F-3: Semantic Ambiguity, Documented

`hdr_peak_headroom` is a user target/cap, while `safe_max_headroom` is a profile safety cap. The correct production behavior is the lower of the two. The code now enforces that, but future docs/UI text should keep "target/cap" separate from profile safety limits.

### F-4: Environment Limitation, Documented

The real HEIC smoke file contains HDR auxiliary metadata, but this host's `CGImageSourceCopyAuxiliaryDataInfoAtIndex(..., kCGImageAuxiliaryDataTypeHDRGainMap)` did not expose an auxiliary dictionary. Other tools did confirm the auxiliary structure:

```text
strings: auxl, auxC, urn:mpeg:hevc:2015:auxid:1, tmap, rhvcC, qhvcC
exiftool: AuxiliaryImageType = urn:mpeg:hevc:2015:auxid:1
exiftool: auxiliary color profile = BT.2020 / PQ
ImageIO properties: Headroom = 2.53499, ProfileName = Display P3
```

Classification: environment/tool exposure limitation, not an implementation bug proven in this audit.

### F-5: Upstream/History Issue, Not Fixed

`uv run --extra dev pytest tests/gui -q` currently fails two non-HDR assertions in `tests/gui/test_controller_runtime_module.py`. The implementation appends elapsed timing to `status_message` (`src/spektrafilm_gui/controller_runtime.py:331`), while the tests expect the older exact string without ` | 0.00s`.

Result:

```text
2 failed, 167 passed
```

Classification: current GUI test drift/history issue. It is unrelated to HDR export math and was intentionally not changed in this audit.

### F-6: UX/Test Boundary, Not Fixed

HEIC HDR export requires `saving_cctf_encoding=False` so `save_image_oiio()` receives linear unclipped data. Current defaults keep `SimulationWorkflowState.saving_cctf_encoding=True` (`src/spektrafilm_gui/state.py:78`) to preserve ordinary SDR save behavior. Existing GUI HEIC tests explicitly set `saving_cctf_encoding=False` before saving. This is acceptable for this audit because changing the default would affect ordinary export behavior, but a future UX pass should consider extension-aware save prompts or auto-linearization for HEIC only.

## Experiments

Post-fix synthetic invariant bundle:

```json
{
  "profile_mapping_cap_probe_after_fix": {
    "mapping_max_headroom": 2.0,
    "profile_safe_max_headroom": 6.0,
    "rendition_headroom": 2.0,
    "hdr_max": 2.0,
    "respects_mapping_cap": true
  },
  "rejection_checks": {
    "missing_sidecar": "ValueError: profile-aware HDR mapping requires a scene luminance sidecar.",
    "unsafe_profile": "ValueError: profile_aware requires a safe increasing curve profile, but got unsafe decreasing."
  },
  "film_scan_profiles": {
    "negative_auto": {
      "film": "kodak_gold_200",
      "profile_kind": "positive_negative_scan",
      "polarity": "increasing",
      "safe": true,
      "has_negative_render": true
    },
    "positive_auto": {
      "film": "fujifilm_provia_100f",
      "profile_kind": "positive_film_scan",
      "polarity": "increasing",
      "safe": true,
      "has_negative_render": false
    },
    "raw_negative": {
      "film": "kodak_gold_200",
      "profile_kind": "raw_negative_scan",
      "polarity": "decreasing",
      "safe": false,
      "has_negative_render": false
    }
  }
}
```

Runtime parity probe:

```json
{
  "fresh_plain_repeat_diff": 0.0004637986421585083,
  "fresh_meta_repeat_diff": 0.0009839683771133423,
  "fresh_plain_vs_meta_diff": 0.000189855694770813,
  "same_sim_plain_then_meta_diff": 0.0006843358278274536,
  "same_sim_meta_then_plain_diff": 0.0015240460634231567
}
```

Interpretation: the tiny differences also occur between fresh plain runs, so this audit does not classify them as a metadata-path bug. The HDR sidecar itself was finite, non-negative, and shape-matched.

HEIC smoke:

```text
created: /tmp/spektrafilm-hdr-system-smoke-20260603/tiny_hdr.heic
size: 2184 bytes
file: ISO Media, HEIF Image HEVC Main or Main Still Picture Profile
sips: pixelWidth=4, pixelHeight=2, format=heic, space=RGB
heif-info: image 4x2 primary, compatible brands include tmap, MiHE, MiHB
exiftool: AuxiliaryImageType=urn:mpeg:hevc:2015:auxid:1
heif-convert: wrote /tmp/spektrafilm-hdr-system-smoke-20260603/tiny_hdr.png
converted PNG: 4x2 RGBA
```

## Verification Commands

Passing:

```bash
uv run --extra dev pytest tests/test_hdr_photo.py::test_profile_aware_mapping_respects_mapping_headroom_below_profile_safe_cap -q
uv run --extra dev pytest tests/test_hdr_photo.py -q
uv run --extra dev pytest tests/test_hdr_curve_profiles.py -q
uv run --extra dev pytest tests/test_image_io_color_metadata.py -q
uv run --extra dev pytest tests/gui/test_controller_output.py -q
uv run --extra dev pytest tests/gui/test_layout.py tests/gui/test_persistence.py tests/gui/test_state_bridge.py tests/gui/test_widgets.py -q
```

Observed results:

```text
1 passed
146 passed
35 passed
26 passed
21 passed
45 passed
```

Known failing command:

```bash
uv run --extra dev pytest tests/gui -q
```

Observed result:

```text
2 failed, 167 passed
```

Failures are the unrelated status-message timing expectations described in F-5.

## Confidence Loop

- Re-read source boundaries after the fix: runtime, GUI controller save dispatch, image I/O, HDR math, and Swift encoder.
- Confirmed the new regression fails before the source fix and passes after it.
- Confirmed ordinary non-HEIC save dispatch remains outside HDR mapping.
- Confirmed HEIC smoke can produce, inspect, and decode a tiny HDR file on this host.
- Remaining uncertainty is external rendered appearance in Apple Photos or Android Gallery; this audit did not include device/app visual acceptance.
