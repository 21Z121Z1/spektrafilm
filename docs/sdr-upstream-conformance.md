# SDR Upstream Conformance

This repository keeps SDR rendering aligned with a locked upstream reference:

- Upstream: `https://github.com/andreavolpato/spektrafilm`
- Locked commit: `3bb2c2d2801ff68b92019cf1dbcbb133d60832bc`
- Contract file: `tests/alignment/upstream_lock.json`

The harness is intentionally separate from `gpu_validate`. `gpu_validate` compares this fork's GPU output against this fork's CPU output. SDR upstream conformance compares this fork against the locked upstream implementation.

## What It Compares

The runner compares these tap boundaries:

- `rgb_pre`
- `log_e_film`
- `cmy_film`
- `log_e_print`
- `cmy_print`
- `rgb_out`

For `scan_film=True`, print-route taps are skipped as route-inapplicable, not treated as failures.

## Modes

`upstream_compat` pins common SDR parameters explicitly so default drift does not pollute the result. It uses `sRGB` input with CCTF decoding disabled to match the locked upstream helper assumptions around the 18% gray print-balance reference. It is the gating mode for core conformance.

`product_sdr` derives current product defaults from `PROJECT_DEFAULT_GUI_STATE`, `build_params_from_state`, and `digest_after_selection`, then strips fields that locked upstream cannot represent. Use it to detect whether user-visible SDR output has intentionally moved away from upstream.

## Commands

Quick CPU conformance:

```bash
.venv/bin/python -m tools.sdr_alignment.run_alignment --mode upstream_compat --suite quick --backend cpu
```

Full CPU conformance:

```bash
.venv/bin/python -m tools.sdr_alignment.run_alignment --mode upstream_compat --suite full --backend cpu
```

Product SDR inspection:

```bash
.venv/bin/python -m tools.sdr_alignment.run_alignment --mode product_sdr --suite full --backend cpu --report-only
```

Optional Apple backend:

```bash
.venv/bin/python -m tools.sdr_alignment.run_alignment --mode upstream_compat --suite quick --backend mlx
```

Reports are written under `artifacts/sdr_alignment/` by default. Each run emits `report.json`, `report.md`, fixture/spec files, and `.npz` tap artifacts.

## Thresholds

CPU `upstream_compat` is strict:

- tap `max_abs <= 1e-8`
- tap `p99_abs <= 1e-9`
- tap `rmse <= 1e-10`
- final SDR SSIM `>= 0.999999`

Float32 backends use looser backend thresholds:

- direct path: `p99_abs <= 1e-5`, `max_abs <= 1e-4`
- LUT path: `p99_abs <= 2e-4`, `max_abs <= 5e-4`
- Halide keeps a separate larger tolerance only when explicitly selected

## Allowlist

Known intentional SDR differences must be added to `tests/alignment/allowlist.yml` with:

```yaml
differences:
  - mode: product_sdr
    fixture: gray_ramp_16_print
    tap: rgb_out
    metric: p99_abs
    threshold: 0.001
    reason: "Intentional product default LUT look drift reviewed in PR 123."
    owner: "@owner"
    review_by: "2026-12-31"
```

Expired entries fail schema tests. Do not use the allowlist to hide unreviewed `upstream_compat` regressions.

## Refreshing Upstream

Refresh only in a dedicated upstream baseline PR:

1. Update `tests/alignment/upstream_lock.json` to the new upstream commit and pyproject hash.
2. Run full `upstream_compat` CPU alignment.
3. Run `product_sdr --report-only`.
4. Review `report.md`, `.npz` tap artifacts, and skipped route taps.
5. Update this document if thresholds, fixtures, or review rules change.

Do not change SDR look to make a conformance failure pass. If product defaults intentionally diverge, document the reason and add an allowlist entry.
