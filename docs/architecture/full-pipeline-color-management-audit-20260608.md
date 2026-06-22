# Spektrafilm Full-Pipeline Color Management Audit - 2026-06-08

Scope: read-only audit of the current dirty workspace. No production code was
changed for this report. The target contract is stricter than "looks plausible":
RAW import, RGB-to-spectral conversion, runtime projection, display preview, SDR
export, HDR/EXR export, and Ultra HDR metadata are checked against ACES/OCIO and
file-format best-practice expectations.

## Findings

### P1 / High: ACES display preview is not an OCIO/CTL-equivalent ACES Output Transform

Status: **not strict-ACES/OCIO compliant for studio display consistency**.

Evidence:

- `src/spektrafilm/color_management.py:79-109` defines
  `aces_sdr_video_view_transform()` as a local, deterministic Stephen Hill-style
  SDR fit. Its docstring explicitly says this is local until an OCIO ACES config
  dependency ships.
- `src/spektrafilm_gui/controller_runtime.py:300-318` routes ACES scene-linear
  GUI preview through that helper and labels it as an ACES SDR video output
  transform.
- `pyproject.toml:49` already depends on `opencolorio~=2.5`, but the runtime
  preview path does not call OCIO or CTL.
- Prior project documentation already records the same boundary:
  `docs/color-management-hdr-review-2026-05-31.en.md:48-51` and
  `docs/color-management-hdr-review-2026-05-31.en.md:204-207`.

Impact:

- ACEScg/ACES2065-1 scene-linear data can be carried correctly, but preview
  pixels are not guaranteed to match Resolve/Nuke/OCIO ACES views per pixel.
- This is acceptable as a local preview approximation, but it must not be marked
  as a studio-grade ACES Output Transform pass.

Recommendation:

- Integrate an OCIO processor for the project ACES view/display pair and add a
  golden-image parity test against the selected ACES config.
- Rename/status-text the current helper as "local ACES-style SDR preview" until
  OCIO/CTL parity is proven.

### P2 / Medium: Untagged prepared images can enter with `ColorEncoding=None`

Status: **metadata contract is strong for Spektrafilm-authored files, weaker for
external untagged files**.

Evidence:

- `src/spektrafilm/utils/io.py:314-350` returns `None` when ICC, OIIO
  colorspace, `colorInteropID`, and EXR `chromaticities` do not map to a known
  color space.
- Audit smoke observed `read_image_color_encoding(...) == None` for
  `img/test/portrait_leaves_32bit_linear_prophoto_rgb.tif`.
- GUI/runtime can still proceed using user-selected input settings, which is
  correct for manual operation but leaves room for silent mismatch.

Impact:

- A linear ProPhoto/ACES TIFF without ICC or OIIO tags can be interpreted through
  the wrong manually selected input space.
- This is not a Spektrafilm export regression; it is an import-time ambiguity for
  third-party or legacy assets.

Recommendation:

- Surface a visible warning when `load_image_payload().color_encoding is None`
  for non-RAW files.
- Add an explicit "assume selected input profile" audit/status note in GUI and
  CLI paths.
- Consider optional sidecar policy for known untagged test/scan folders.

### P2 / Medium: RAW import return dtype contract drifts after colour conversion

Status: **linear encoding is correct, dtype contract is inconsistent**.

Evidence:

- `src/spektrafilm/utils/raw_file_processor.py:382-415` documents return as
  `float32`.
- `src/spektrafilm/utils/raw_file_processor.py:418-443` demosaics to `float32`,
  but `colour.RGB_to_RGB(...)` can return `float64` when converting from
  ACES2065-1 to another output color space.
- Audit smoke on
  `07_历史批量归档_DNG/IMG20240311182516.DNG`
  produced `float64` arrays for ProPhoto and ACEScg RAW imports.

Impact:

- Color correctness is not harmed by higher precision, but memory and backend
  residency assumptions can be wrong, especially for large DNG files and GPU
  paths that expect float32.

Recommendation:

- Either cast the converted RAW result back to `float32` before return, or update
  the public contract/tests to accept `float64` after colour-science conversion.
- Given the project GPU constraint, casting back to explicit `float32` is the
  better default unless a caller opts into higher precision.

### P3 / Residual: Ultra HDR/HEIC device rendering is still outside local proof

Status: **local metadata probes pass; external app/device rendering remains
manual validation**.

Evidence:

- `tools/validate_profile_aware_hdr_raw_samples.py` successfully validated a
  real DNG sample from the user's RAW directory.
- The generated audit output at
  `/tmp/spektrafilm-color-audit-profile-aware-raw.md` reports Android container
  metadata, ISO metadata roundtrip, JPEG probe metadata/gain-map, and EXR
  attributes present.
- The same output states the runtime validation uses a bounded downsampled RGB
  array for speed and does not prove real device rendering.

Impact:

- The file/container contract is locally strong, but Apple Photos, Android
  Gallery, and third-party ISO 21496-1 decoder behavior still require device/app
  acceptance tests.

Recommendation:

- Keep device rendering as a separate release gate. Do not collapse metadata
  roundtrip success into "visible HDR accepted by target apps."

## Evidence Matrix

| Stage | Current evidence | Audit status |
| --- | --- | --- |
| RAW demosaic | `rawpy.postprocess` configured with `output_color=ACES`, `output_bps=16`, `no_auto_bright=True`, `gamma=(1,1)` in `src/spektrafilm/utils/raw_file_processor.py:83-103`. | Pass for linear RAW entry. |
| RAW white balance | As-shot uses camera WB; daylight/tungsten/custom use colour-science adaptation in linear ACES RGB, `src/spektrafilm/utils/raw_file_processor.py:41-70` and `:116-130`. | Pass with explicit model; no sensor black/white diagnostics returned by this API. |
| Lens correction | Lensfun operates after linear float demosaic and before final output color-space conversion, `src/spektrafilm/utils/raw_file_processor.py:292-369` and `:422-443`. | Pass for linear-domain ordering. |
| ACES workflow preset | `aces_reference` sets input/output to ACEScg scene-linear, save to ACES2065-1 scene-linear, and disables clipping, `src/spektrafilm/color_management.py:131-142`. | Pass for scene-linear working/interchange contract. |
| Hanatos spectral upsampling | RGB -> XYZ uses explicit input color space, CCTF decode flag, reference illuminant, and CAT16; input-gamut compression is baked into the LUT, `src/spektrafilm/utils/spectral_upsampling.py:182-223` and `:450-519`. | Pass with explicit color/illuminant contract. |
| Mallett spectral path | Converts input RGB to linear sRGB, uses Mallett sRGB basis with selected reference illuminant, then sensor sensitivity, `src/spektrafilm/utils/spectral_upsampling.py:407-442`; GPU mirror is in `src/spektrafilm/gpu/kernels/color.py:254-294`. | Pass as a method-specific sRGB-basis path; document that it is not arbitrary-RGB spectral recovery. |
| Runtime scan/projection | Density -> XYZ -> output RGB uses output color space, then output gamut compression, then CCTF/clip in `src/spektrafilm/runtime/stages/scanning.py:62-69` and `:99-151`. | Pass for ordinary SDR projection; HDR/ACES correctness depends on chosen encoding flags. |
| GUI display projection | ACES scene-linear preview uses local `aces_sdr_video_view_transform()`, `src/spektrafilm_gui/controller_runtime.py:300-318`. | High risk under strict ACES/OCIO. |
| Ordinary export | PNG/JPEG reject linear `ColorEncoding`, embed ICC when available, and clip to integer format, `src/spektrafilm/utils/io.py:688-714`. | Pass for SDR display formats. |
| EXR export | EXR rejects CCTF, writes float/half data, `chromaticities`, `colorInteropID`, `oiio:ColorSpace`, optional `whiteLuminance`, `hdrHeadroom`, `src/spektrafilm/utils/io.py:713-768`. | Pass for scene-linear interchange metadata. |
| HDR rendition EXR | `save_hdr_rendition_exr()` forces linear scene encoding and `exr_mode="hdr_rendition"`, `src/spektrafilm/utils/io.py:795-857`. | Pass in local smoke. |
| HEIC/Ultra HDR | HEIC path requires explicit linear unclipped HDR encoding and routes through `save_hdr_photo_heic`, `src/spektrafilm/utils/io.py:643-663`. | Pass for local guards/metadata probes; device rendering unproven. |

## Audit Smoke Results

Focused tests rerun on this workspace:

```bash
.venv/bin/python -m pytest \
  tests/test_color_management.py \
  tests/test_image_io_color_metadata.py \
  tests/test_raw_file_processor.py \
  tests/test_spectral_upsampling.py \
  tests/test_gpu_color_chain.py -q
```

Result:

```text
98 passed in 1.84s
```

RAW/IO bounded smoke used:

- Sample:
  `07_历史批量归档_DNG/IMG20240311182516.DNG`
- Temporary output:
  `/var/folders/9m/l8brh8z93lb589gnms27vrrm0000gn/T/spektrafilm-color-audit-_4y7uhe_/`

Observed:

- RAW ProPhoto import: shape `[3072,4096,3]`, dtype `float64`, finite, min
  `-0.0007277744`, max `1.0511104556`.
- 64x64 SDR runtime crop: dtype `float32`, finite, min `0.12319809`, max
  `0.5879144`, encoding `sRGB/cctf/display`, clipped.
- PNG/JPEG saved with ICC; OIIO readback reported
  `oiio_ColorSpace=srgb_rec709_scene`.
- RAW ACEScg import: dtype `float64`, finite, min `-4.906e-05`, max
  `1.05948539`.
- ACEScg runtime output: dtype `float32`, finite, min `0.0211739`, max
  `0.20815808`, encoding `ACEScg/linear/scene`, `clip_highlights=false`.
- ACEScg EXR readback: float format, `oiio:ColorSpace=ACEScg`,
  `colorInteropID=ACEScg`, ACEScg `chromaticities` present, no ICC.
- Synthetic HDR rendition EXR with input max `2.0`: `whiteLuminance=203.0`,
  `hdrHeadroom=2.0`, ACEScg chromaticities and colorspace attributes present.
- HDR HEIC export correctly rejected non-HDR input with
  `HEIC HDR photo export requires linear image values above SDR white (1.0)`.

Profile-aware RAW/HDR validation command:

```bash
.venv/bin/python tools/validate_profile_aware_hdr_raw_samples.py \
  --sample-dir "RAW_DNG照片" \
  --max-samples 1 \
  --diagnostic-scan-limit 4 \
  --output /tmp/spektrafilm-color-audit-profile-aware-raw.md
```

Observed from `/tmp/spektrafilm-color-audit-profile-aware-raw.md`:

- DNG files discovered: `754`; files inspected for selection diagnostics: `4`.
- Selected sample: `IDG_20260410_140916_153 2.DNG`, `4032x3024`.
- Sidecar shape `[576,768]`, finite/nonnegative, process-vs-metadata max abs
  `2.980e-08`, auto exposure scale invariant.
- HDR headroom `1.092`; Android container true; ISO metadata roundtrip true;
  JPEG probe metadata/gain map true.
- EXR tracked attributes: `chromaticities`, `colorInteropID`,
  `oiio:ColorSpace`, `whiteLuminance`, `hdrHeadroom`.

## External Baseline Used

- [ACEScg](https://docs.acescentral.com/encodings/acescg/): AP1,
  scene-linear, floating-point ACES working/rendering/compositing encoding.
- [ACES Output Transforms](https://docs.acescentral.com/system-components/output-transforms/):
  scene-linear ACES must be rendered through an output transform for the target
  display/device encoding.
- [OpenColorIO ACES config](https://opencolorio.readthedocs.io/en/v2.4.0/configurations/aces_1.0.3.html):
  ACES configs expose roles and output colorspaces; this is the appropriate
  implementation route for cross-application parity.
- [rawpy Params](https://letmaik.github.io/rawpy/api/rawpy.Params.html):
  RAW postprocess parameters include output color, bit depth, gamma, and auto
  brightness controls.
- [Jakob/Hanika 2019](https://rgl.epfl.ch/publications/Jakob2019Spectral) and
  [Mallett/Yuksel 2019](https://diglib.eg.org/items/bbffa865-e99c-4c1f-bd33-70102dc8af78):
  spectral upsampling/decomposition methods require explicit RGB-space,
  illuminant, and transfer-function assumptions.
- [OpenEXR Standard Attributes](https://openexr.com/en/latest/StandardAttributes.html):
  `chromaticities` and `whiteLuminance` are standard EXR color/luminance
  attributes.
- [OpenImageIO metadata](https://openimageio.readthedocs.io/en/v2.3.19.0/stdmetadata.html):
  OIIO uses standard metadata names such as `oiio:ColorSpace`, `ICCProfile`, and
  `chromaticities`.
- [Android Ultra HDR v1.1](https://developer.android.com/media/platform/hdr-image-format):
  gain-map JPEGs require container and gain-map metadata semantics; local
  metadata roundtrip is necessary but not sufficient for rendered acceptance.

## Fix Order

1. **OCIO ACES display/output transform integration.** Add an OCIO-backed view
   transform path and golden parity tests. Keep the current fit as a fallback
   only.
2. **Untagged image import UX.** Warn when non-RAW files have no detectable color
   encoding and record the assumed manual input encoding in diagnostics/status.
3. **RAW dtype contract.** Cast converted RAW output to `float32` or update the
   documented contract and tests. The project GPU policy favors explicit
   `float32`.
4. **Device validation runbook.** Add a repeatable Apple Photos / Android Gallery
   acceptance checklist separate from local metadata probes.

## Bottom Line

Spektrafilm's scene-linear working-space, spectral-conversion, SDR file export,
EXR metadata, and local HDR metadata contracts are in substantially good shape
in this dirty workspace. The strict failing point is ACES display/output
management: the current ACES preview is a local ACES-style SDR fit, not an
OCIO/CTL-equivalent Output Transform. Treat RAW dtype drift and untagged external
file imports as medium-priority contract hardening, and keep device-rendered HDR
acceptance as a separate manual gate.
