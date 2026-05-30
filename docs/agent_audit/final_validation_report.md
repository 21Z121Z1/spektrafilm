# Final Validation Report

Generated: 2026-05-28

## Summary

The current adversarial-review remediation pass is complete against the live workspace state. The previous version of this file reported stale Halide failures; that no longer reflects the current repository because the full pytest suite now passes.

## Validation Results

| Gate | Result |
|------|--------|
| Targeted audit regression suite | `280 passed in 2.07s` |
| Full pytest suite | `814 passed, 5 skipped in 53.87s` |
| Compile check | Passed |
| Diff whitespace check | Passed |

Commands:

```bash
uv run --extra dev pytest -q tests/test_hdr_photo.py tests/test_gain_map.py tests/test_tier3_fixes.py tests/test_image_io_color_metadata.py tests/test_exif_metadata.py tests/test_spectral_upsampling.py tests/test_numba_warmup.py tests/test_grain.py tests/test_pipeline_smoke.py tests/test_photo_params.py
uv run --extra dev pytest -q
uv run --extra dev python -m compileall -q src/spektrafilm src/spektrafilm_gui tests scripts
git diff --check
```

## Fixes Covered

- `HDR-C-001`: Oklch gamut mapping now checks linear-sRGB gamut and uses a real low/high chroma search.
- `HDR-C-002`: Near-black gain-map log encoding now avoids treating tiny shadow lifts as full-headroom specular gain.
- Legacy `hdr_highlight_path_to_white`: constructor validation now rejects values outside `[0, 1]`.
- `FMT-004`: HEIF gain-map export now raises `ImportError` when `pillow-heif` is unavailable instead of writing an unrequested JPEG fallback.
- `FMT-005` / `FMT-006`: DCI-P3 linear ICC is bundled and the OIIO/TIFF path uses `resolve_icc_profile_bytes()`.
- `FMT-008`: half EXR export warns on absolute positive or negative float16 overflow.
- Spectral LUT precision: `compute_lut_spectra()` returns `float32`, not `float16`.

Additional regression hardening:

- README public API import path is covered.
- Active float32 highlight-boost `out` buffers are covered.
- Grain application input non-mutation is covered.
- Mid-gray pipeline smoke includes a deterministic value assertion.

## Notes

The live worktree contains additional unrelated modified and untracked Halide/Android/docs files. They were not reverted. The validation results above were run against that current state.
