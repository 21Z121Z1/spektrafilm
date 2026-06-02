# Adversarial Review Report - 2026-05-28

## Scope

Workspace: `/Users/retriedstormtrooper/Documents/spektrafilm-main`

Head commit at review time: `1cdc46bff27bdc35cd1296cfdc083ceee4851369`

The review followed the useful parts of OpenAI's `/codex:adversarial-review` implementation from `openai/codex-plugin-cc`: choose the live git target, collect repository evidence, default to skepticism, report only grounded material risks, and prefer one defensible blocker over broad style feedback. Unlike the upstream slash command, this task then implemented fixes because the user explicitly requested review plus remediation.

## Upstream Mechanism Summary

The upstream command is implemented by:

- `plugins/codex/commands/adversarial-review.md`
- `plugins/codex/scripts/codex-companion.mjs`
- `plugins/codex/scripts/lib/git.mjs`
- `plugins/codex/prompts/adversarial-review.md`
- `plugins/codex/schemas/review-output.schema.json`

The command is review-only. It resolves the target as dirty working tree or branch diff, collects full inline diff only for small reviews, otherwise provides a lightweight summary and tells Codex to inspect with read-only git commands. The prompt asks Codex to break confidence in the change, focus on hidden assumptions and failure modes, and return compact JSON with file/line findings, confidence, and concrete recommendations.

## Current Workspace Notes

The workspace contains many pre-existing untracked files and several modified files outside this patch's write set, including Halide/Android/docs work. Those were treated as current workspace context and were not reverted. The fixes in this pass touched only the HDR, gain-map, ICC/I/O, spectral LUT, and regression-test files listed below.

## Findings Fixed

### HDR-C-001: Oklch gamut mapping did not actually compress Display P3 primaries

`gamut_map_oklch()` returned early when the input was within the working color space range, so Display P3 green skipped the sRGB-gamut check. After that, the binary search initialized its low bound at the original chroma, making the search a no-op.

Fix:

- Check gamut after converting to linear sRGB.
- Use a real `[0, C]` chroma binary search.
- Add a regression proving mapped Display P3 green is inside sRGB gamut and has lower Oklch chroma.

### HDR-C-002: Near-black gain-map encoding saturated tiny shadow lifts

`encode_gain_map_log2()` divided by an `_EPS32` SDR luminance floor, so SDR black plus tiny HDR shadow lift normalized to full-headroom gain.

Fix:

- Add a practical SDR luminance floor for gain-map division.
- Add a regression proving a `1e-4` HDR shadow lift over SDR black does not saturate the gain map.

### HDR path-to-white validation accepted values above 1.0

`HDRPhotoMapping.hdr_highlight_path_to_white` was only checked for non-negative values.

Fix:

- Validate the legacy strength as `[0, 1]`, matching the modern profile-aware strength contract.
- Extend parameterized constructor validation tests.

### FMT-004: HEIF gain-map save silently changed requested output format

When `pillow-heif` was missing, `save_gain_map_heif("x.heif", ...)` wrote `x.jpg` instead of failing. That can hide format mismatches and produce an output path the caller did not request.

Fix:

- Raise `ImportError` when HEIF dependencies are unavailable.
- Document that callers must explicitly choose `save_gain_map_jpeg()` for JPEG/MPF fallback.
- Update tests to assert no `.heif` or sibling `.jpg` is written on dependency failure.

### FMT-005/FMT-006: Linear DCI-P3 ICC was missing and TIFF bypassed the resolver

Linear DCI-P3 had no dedicated ICC mapping, and the OpenImageIO/TIFF path used `_load_icc_profile()` directly instead of the public resolver.

Fix:

- Add `src/spektrafilm/data/icc/DCI-P3-linear.icc` with identity `curv` TRCs.
- Add `("DCI-P3", False)` to `_ICC_FILENAMES`.
- Use `resolve_icc_profile_bytes()` in the non-EXR OIIO path.
- Add ICC resolver and linear-TRC regressions.

### FMT-008: Negative half-float EXR overflow was not covered

The existing warning only checked positive values above `float16.max`; large negative values could still cast to `-inf` without the project warning.

Fix:

- Warn on absolute half-float overflow.
- Suppress NumPy's duplicate cast overflow warning after the project warning is emitted.
- Add negative-overflow coverage.

### Spectral LUT precision downgrade

`compute_lut_spectra()` returned `float16`, violating the repository's zero precision-loss GPU/color constraint.

Fix:

- Return `float32`.
- Add a monkeypatched precision regression.

### Regression hardening

Additional tests now lock existing intended behavior:

- README public API import uses `init_params` and `simulate`.
- `boost_highlights()` accepts active float32 `out` buffers.
- `apply_grain_to_density()` does not mutate its input.
- Mid-gray pipeline smoke now asserts a deterministic reference value, not only broad ranges.

## Verification

Commands run in the current workspace:

- `uv run --extra dev pytest -q tests/test_hdr_photo.py tests/test_gain_map.py tests/test_tier3_fixes.py tests/test_image_io_color_metadata.py tests/test_exif_metadata.py tests/test_spectral_upsampling.py tests/test_numba_warmup.py tests/test_grain.py tests/test_pipeline_smoke.py tests/test_photo_params.py`
  - Result: `280 passed in 2.07s`
- `uv run --extra dev pytest -q`
  - Result: `814 passed, 5 skipped in 53.87s`
- `uv run --extra dev python -m compileall -q src/spektrafilm src/spektrafilm_gui tests scripts`
  - Result: passed
- `git diff --check`
  - Result: passed

## Remaining Risk Assessment

No material blocking findings remain from the adversarial pass that are both current-state reproducible and scoped to this goal. The working tree still contains unrelated modified and untracked Halide/Android/docs work; the full suite is green against that current state, but those unrelated changes should be reviewed as their own integration topic before commit.
