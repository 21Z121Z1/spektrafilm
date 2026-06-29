# MLX Float32 Color Precision Audit - 2026-06-29

## Goal

Implement executable governance for MLX float32 colour precision relative to
CPU float64 references without pretending that Apple GPU paths provide real
float64. The policy target is visual/algorithmic parity where appropriate, with
explicit L1 exceptions and CPU fallback where strict parity is requested.

Plan document: `docs/reports/mlx-float32-color-precision-plan-20260629.md`.

## Sources Checked

Primary or implementation sources:

- Apple MLX data type docs: `float64` exists, but CPU-only operations are the
  supported route; GPU float64 is not available.
  <https://ml-explore.github.io/mlx/build/html/python/data_types.html>
- Apple Metal resources and Metal Shading Language specification: custom MLX
  Metal kernels are bounded by Metal shader scalar support and should not claim
  GPU double precision.
  <https://developer.apple.com/metal/resources/>
  <https://developer.apple.com/metal/Metal-Shading-Language-Specification.pdf>
- NumPy `sum` docs: floating-point summation error is real; NumPy may use
  partial pairwise summation for better precision.
  <https://numpy.org/doc/2.3/reference/generated/numpy.sum.html>
- scikit-image metrics docs: PSNR and SSIM are standard full-reference image
  metrics; floating-point `data_range` must be explicit.
  <https://scikit-image.org/docs/0.25.x/api/skimage.metrics.html>
- ACES encodings: ACES2065-1 and ACEScg are scene-linear encodings and must not
  receive SDR CCTF encoding/decoding.
  <https://docs.acescentral.com/encodings/aces2065-1/>
  <https://docs.acescentral.com/encodings/acescg/>
- Colour docs: CPU reference semantics for RGB/XYZ, Delta E, and JzAzBz are
  provided by `colour`.
  <https://colour.readthedocs.io/en/master/generated/colour.RGB_to_XYZ.html>
  <https://colour.readthedocs.io/en/latest/generated/colour.delta_E.html>
  <https://colour.readthedocs.io/en/latest/colour.models.html>

Repository sources checked are listed in the plan document and include the
GPU/MLX kernels, runtime stages, color management, precision contract, prior GPU
research docs, and all relevant GPU/color tests.

## Implemented Governance

- Added `src/spektrafilm/gpu/precision_policy.py`.
  - Policies: `fast`, `balanced`, `strict`.
  - Operations: `lut_2d_mitchell`, `gamut_jzazbz`, `spectral_reduction`,
    `rgb_xyz_matrix`, `cctf`, `hdr_gain_map`.
  - Decisions include `allow_gpu`, `fallback_to_cpu`, `l1_compliant_claim`,
    `status`, reason, and metric budgets.
  - Added reusable `precision_metrics()`.

- Added `SettingsParams.color_precision_policy`.
  - Default: `balanced`.
  - `RuntimePhotoParams.__post_init__` validates the value.

- Wired runtime fallback.
  - Hanatos 2025 2D Mitchell LUT:
    - `fast`: resident GPU path remains available as documented exception.
    - `balanced`: CPU float64 Hanatos reference fallback.
    - `strict`: CPU float64 Hanatos reference fallback.
  - JzAzBz output gamut compression:
    - `fast`: resident GPU path remains available as documented exception.
    - `balanced`: resident GPU path remains available but policy says non-L1
      exception.
    - `strict`: CPU float64 `compress_rgb` fallback, then upload result to the
      backend if needed.
  - Spectral reductions:
    - `fast` / `balanced`: current GPU float32 paths remain conditional.
    - `strict`: runtime Mallett filming, print spectral exposure, and scan
      spectral XYZ reductions use CPU/reference accumulation rather than the
      float32 GPU reduction.

- Added `tools/audit_color_precision.py`.
  - Supports `--operation`, `--backend cpu|mlx`, `--seed`, `--policy`,
    `--format markdown|json`, and `--output`.
  - Reports max_abs, mean_abs, relative error, RMSE, PSNR, and luminance error
    when applicable.
  - MLX unavailability is reported as skipped rather than crashing.

## Path Status

| Path | Status | Handling |
|---|---|---|
| CCTF thresholds | compliant | Existing float32 thresholds retained; tests cover sRGB branch boundaries and ACES no-op. |
| ACES2065-1 / ACEScg CCTF | compliant | Scene-linear encode/decode no-op tested. |
| RGB/XYZ matrices | compliant | CPU float64 precompute and backend float32 upload semantics tested for dtype, shape, finite values, and roundtrip. |
| 2D LUT Mitchell cubic | fallback / fast exception | Balanced/strict CPU fallback in Hanatos filming; fast keeps GPU residency but does not claim L1. |
| JzAzBz gamut compression | strict fallback / fast-balanced exception | Strict CPU fallback; fast/balanced retain resident MLX DS kernel as non-L1 exception. Existing xfails retained. |
| Spectral reductions | conditional / strict fallback | No broad Kahan rewrite in this pass; strict CPU fallback plus adversarial budget tests and audit metrics. |
| HDR/gain-map float32 | conditional, unchanged | Policy documents the risk but does not alter HDR projection/export semantics. No HDR code was modified. |

## Audit Results

Environment: this machine has MLX available (`selected_backend=mlx`,
`gpu_precision=float32`).

Command:

```bash
.venv/bin/python tools/audit_color_precision.py --backend mlx --operation all --format markdown --policy balanced --seed 20260629
```

Result:

| Operation | Policy status | max_abs | mean_abs | max_rel | RMSE | PSNR |
|---|---|---:|---:|---:|---:|---:|
| cctf | compliant | 5.426e-07 | 1.4355e-07 | 9.96886e-07 | 1.7224e-07 | 137.55 dB |
| rgb-xyz | compliant | 3.52456e-07 | 6.72145e-08 | 2.02298e-04 | 9.65285e-08 | 142.572 dB |
| lut2d | fallback | 0 | 0 | 0 | 0 | inf |
| jzazbz | exception | 9.64753e-05 | 1.65446e-05 | 5.93299e-04 | 2.42473e-05 | 92.5076 dB |
| spectral | conditional | 1.21653e-06 | 1.95971e-07 | 4.76072e-07 | 2.86009e-07 | 144.101 dB |

Additional fast-path probe:

```bash
.venv/bin/python tools/audit_color_precision.py --backend mlx --operation lut2d,jzazbz --format markdown --policy fast --seed 20260629
```

The smooth LUT probe showed low error on this sample (`max_abs=3.58061e-07`),
but that does not clear the documented adversarial/worst-case L1 exception.
JzAzBz fast remained non-L1 (`max_abs=1.11813e-04`).

## Verification

Commands run:

```bash
python -m pytest tests/test_gpu_precision_policy.py tests/test_gpu_color_precision_budget.py tests/test_filming_stage.py -q
```

Result: failed because the shell `python` has no `pytest` installed.

Equivalent repository runner:

```bash
.venv/bin/python -m pytest tests/test_gpu_precision_policy.py tests/test_gpu_color_precision_budget.py tests/test_filming_stage.py -q
```

Result: `28 passed`.

Required commands with repository runner:

```bash
.venv/bin/python -m pytest tests/test_color_management.py tests/test_gpu_backend.py tests/test_gpu_color_chain.py -q
```

Result: `93 passed`.

```bash
.venv/bin/python -m pytest tests/test_gpu_precision_policy.py tests/test_gpu_color_precision_budget.py -q
```

Result: `20 passed`.

```bash
.venv/bin/python tools/audit_color_precision.py --help
```

Result: help printed successfully.

Additional related suite:

```bash
.venv/bin/python -m pytest tests/test_gpu_pipeline.py tests/test_gamut_compression.py tests/test_spatial_tiling.py tests/test_gpu_lut.py tests/test_gpu_density.py -q
```

Result: `174 passed, 6 skipped, 4 xfailed`. Existing JzAzBz strict parity xfails
remain in place.

## Remaining Risks

- The resident 2D Mitchell GPU kernel is not globally proven L1-compliant. It is
  governed by fallback in balanced/strict and remains a fast exception.
- JzAzBz on MLX is still structurally above L1 because Metal does not provide a
  real float64 GPU path and the double-single kernel has a float32 arithmetic
  floor. Strict fallback is the current correct solution.
- Spectral GPU reductions were not rewritten with Kahan or pairwise Metal
  accumulation in this pass. The risk is now explicit through policy, strict
  fallback, adversarial tests, and audit metrics.
- The audit tool reports numerical metrics; it does not yet compute ΔE or SSIM.
  PSNR and luminance error are available. DeltaE can be added once a stable
  representative image corpus is selected.
- `docs/README.md` was intentionally not modified. Add this report and the plan
  to the docs router manually in a follow-up.
