# MLX Float32 Color Precision Governance Plan - 2026-06-29

## Goal

Establish executable MLX float32 color precision governance for Spektrafilm:
audit current GPU/MLX color paths against the existing precision contract and
primary-source guidance, add a fast / balanced / strict policy surface, wire
runtime fallback or exception decisions for known high-risk operations, add a
reproducible audit tool and tests, update the precision contract and audit
report, run the required verification commands, and commit locally without
pushing.

## Sources Reviewed Before Implementation

Repository sources and docs reviewed before this plan:

- `docs/README.md`
- `deep-research-report.md`
- `deep-research-report-2.md`
- `docs/mlx-float32-precision-contract.md`
- `docs/gpu/mlx-optimization-report-20260530.md`
- `docs/gpu/research-gpu-color-management.md`
- `docs/halide-mlx-parity-plan-20260531.md`
- GPU/backend/runtime files listed in the user request, including
  `gpu/backend.py`, `gpu/mlx_backend.py`, `gpu/kernels/{color,density,lut,gamut_compress,filters}.py`,
  runtime stages, `params_schema.py`, `utils/gamut_compression.py`, and
  `color_management.py`.
- Existing GPU/color tests, including all `tests/test_gpu_*.py`,
  `tests/test_spatial_tiling.py`, `tests/test_color_management.py`, and
  `scratch_precision_test.py`.

Primary/first-party or implementation sources checked:

- Apple MLX data type documentation: MLX supports `float64`, but `float64`
  arrays only work with CPU operations; GPU `float64` raises.
  <https://ml-explore.github.io/mlx/build/html/python/data_types.html>
- Apple Metal Shading Language specification/resources: Metal shader scalar
  types are the authoritative boundary for custom kernels; Apple publishes the
  MSL specification PDF from the Metal resources page.
  <https://developer.apple.com/metal/resources/>
  <https://developer.apple.com/metal/Metal-Shading-Language-Specification.pdf>
- NumPy `sum` documentation: direct floating-point summation accumulates
  rounding error; NumPy often uses partial pairwise summation for better
  precision.
  <https://numpy.org/doc/2.3/reference/generated/numpy.sum.html>
- scikit-image metrics documentation: PSNR and SSIM are standard full-reference
  image metrics, with care required for floating-point `data_range`.
  <https://scikit-image.org/docs/0.25.x/api/skimage.metrics.html>
- ACES documentation: ACES2065-1 is linear AP0; ACEScg is photometrically
  linear AP1, so CCTF encode/decode must be no-op for these scene-linear spaces.
  <https://docs.acescentral.com/encodings/aces2065-1/>
  <https://docs.acescentral.com/encodings/acescg/>
- Colour documentation: RGB to XYZ supports chromatic adaptation parameters;
  Colour exposes Delta E and JzAzBz conversions used by the CPU reference.
  <https://colour.readthedocs.io/en/master/generated/colour.RGB_to_XYZ.html>
  <https://colour.readthedocs.io/en/latest/generated/colour.delta_E.html>
  <https://colour.readthedocs.io/en/latest/colour.models.html>

## Current Code Findings

- MLX/Metal cannot provide a true GPU float64 path. Strict parity must mean CPU
  float64 fallback or explicit unavailable status, never fake GPU double.
- `select_backend(..., precision="float64")` already rejects explicit GPU
  float64 and falls back to CPU for `auto`.
- CCTF threshold literals in `gpu/kernels/color.py` are already explicitly
  float32 for sRGB / Display P3 and BT.2020. ACES2065-1 and ACEScg already use
  no-op CCTF functions. This needs tests, not another rewrite.
- RGB <-> XYZ matrices are precomputed in CPU float64 and then uploaded to the
  backend as float32. This is the right semantic split; tests need to lock dtype,
  shape, finiteness, and roundtrip behavior.
- Hanatos 2025 2D Mitchell LUT still dispatches through
  `apply_lut_cubic_2d_backend` in the GPU filming path. Existing contract marks
  it non-compliant at L1. Balanced/strict must not silently use this as an L1
  path.
- JzAzBz gamut compression still uses the resident MLX double-single Metal
  kernel. Existing xfails and contract identify a structural float32 floor. Do
  not claim L1 compliance. Strict needs CPU fallback or explicit unavailable.
- Spectral reductions (`cmy_to_log_raw`, `cmy_to_log_xyz`, `light_to_raw`,
  `rgb_to_raw_mallett2019`) use float32 GPU accumulation. A low-risk kernel-wide
  Kahan rewrite is not justified in this pass; policy, adversarial tests, and
  audit budgets will make the limitation executable and visible.
- HDR/gain-map paths use float32 log/exp/percentile operations but are outside
  the direct implementation surface unless touched. The policy must not change
  HDR projection/export semantics.

## Implementation Plan

1. Add `src/spektrafilm/gpu/precision_policy.py`.
   - Define `fast`, `balanced`, `strict`.
   - Define operation IDs for 2D Mitchell LUT, JzAzBz gamut compression,
     spectral reductions, RGB/XYZ matrices, CCTF, HDR gain-map.
   - Return explicit decisions: allow GPU, fallback to CPU, exception status,
     L1 compliance claim, reason, and default budgets.
   - Include reusable precision metric helpers: max abs, mean abs, relative
     error, RMSE, PSNR, optional luminance error.

2. Add runtime policy surface.
   - Add `SettingsParams.color_precision_policy` with default `balanced` and
     validation.
   - Wire `FilmingStage._rgb_to_film_raw` so Hanatos 2D Mitchell LUT:
     - `fast`: keep resident GPU path with documented exception.
     - `balanced`: CPU fallback for this known non-compliant high-risk path.
     - `strict`: CPU fallback.
   - Wire `compress_rgb_backend` / `ScanningStage` so JzAzBz:
     - `fast`: keep resident GPU path with documented exception.
     - `balanced`: keep resident GPU path, but policy marks it exception and
       non-L1; no silent L1 claim.
     - `strict`: CPU fallback using the existing float64 reference, then upload
       output to backend if a GPU caller expects backend arrays.

3. Add `tools/audit_color_precision.py`.
   - `--operation` subset, `--backend cpu|mlx`, `--seed`, `--format markdown|json`,
     `--policy`.
   - Report max_abs, mean_abs, max/mean relative error, RMSE, PSNR, and
     luminance error where applicable.
   - Run in CPU-only environments; MLX backend unavailable must be reported as a
     skip, not a crash.

4. Add tests.
   - `tests/test_gpu_precision_policy.py`: policy normalization, settings
     validation, decision matrix for fast/balanced/strict, non-L1 exception
     accounting.
   - `tests/test_gpu_color_precision_budget.py`: CCTF threshold boundaries,
     ACES no-op CCTF, RGB/XYZ matrix precompute semantics and roundtrip,
     Mitchell LUT fallback decision, JzAzBz non-L1/strict fallback decision,
     spectral adversarial budget, and CPU-only auditability.
   - Update existing tests only where the new default balanced policy changes
     residency assumptions; use explicit `color_precision_policy="fast"` for
     tests whose purpose is residency rather than precision governance.

5. Update docs.
   - Narrow update to `docs/mlx-float32-precision-contract.md` with the new
     executable policy/tool and runtime fallback outcomes.
   - Add `docs/reports/mlx-float32-color-precision-audit-20260629.md` covering
     source research, path status, fixes/fallbacks/exceptions, test results, and
     remaining risks.
   - Do not edit `docs/README.md`; note later router update as manual follow-up.

6. Verification and commit.
   - Run required pytest commands.
   - Run `python tools/audit_color_precision.py --help`.
   - Run minimal MLX audit if MLX is available; otherwise run CPU/reference
     audit and record skip reason.
   - Run `git diff --check`.
   - Commit locally with a message describing MLX float32 color precision
     governance. Do not push.

## Completion Self-Audit Criteria

Before finishing, re-check that:

- Visual parity and L1 kernel parity are not conflated.
- JzAzBz structural float32 error is not presented as fixed.
- Final-quality paths do not silently use the non-compliant 2D Mitchell GPU LUT
  under balanced/strict.
- Strict mode does not accidentally take fast resident GPU paths for known
  exceptions.
- The policy does not over-fallback everything and erase the fast MLX residency
  option.
- CCTF thresholds, negative handling, and ACES scene-linear no-op behavior are
  covered by tests.
- Default SDR CPU/NumPy behavior is preserved.
