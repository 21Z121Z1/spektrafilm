# M1 Pro phase-two performance and precision plan

Date: 2026-07-19

Reference: `eac7b623` plus the pre-existing, untouched profile/provenance worktree

## Fixed scope

Retain the phase-one FFT, grain streaming, lazy-graph, HDR row-bounding, and
export-lifetime controls. Preserve every model step, profile field, wavelength,
LUT sample and interpolation rule, RNG key/shape/call order, float32 MLX dtype,
SDR/HDR meaning, output resolution, and encoder setting. CPU behavior is
immutable. No profile/provenance file is part of this change.

## Measured starting point

The first phase reported 2.94 s steady 12 MP, 22-24 s 49.77 MP core, 15.36 s
49.77 MP chemical HDR projection, and 48.98 s full HDR HEIC. A phase-two
12 MP five-repeat run on the same commit was affected by active system swap;
its last two synchronized runs were 3.60/3.74 s. Their dispatch intervals were
2.07-2.14 s filming exposure, 0.97-1.00 s film development/grain, and
0.52-0.54 s scan/projection. Residency recording showed a 144 MB MLX-to-NumPy
readback followed by re-upload at the balanced Hanatos 2D LUT precision
fallback. These numbers are attribution evidence, not a speedup baseline until
the pressure-free repeat is recorded.

## Precision staircase contract

The executable harness will use fixed deterministic patch, grey ramp, shadow,
white/HDR highlight, negative/out-of-range, wide-gamut, smooth-gradient,
high-frequency, and odd-boundary-size cases. It will cover representative
negative/print and positive/direct-scan profiles, effects off/on, and SDR/HDR.
Snapshots are collected at film log exposure, film CMY density, print log
exposure, print CMY density, scan log spectral/XYZ, route/output linear RGB,
pre-encode SDR, HDR luminance/headroom, gain map, and decoded output where the
public runtime exposes them.

The immutable comparison order is CPU float64, CPU float32, current unfused MLX
float32, then candidate MLX float32. Every numeric stage reports MAE, RMS,
P95/P99/P99.9/max absolute error, finite-relative error, ULP distribution,
worst index/value/input class, NaN/Inf counts, and clamp/clipping classification.
Final color adds Delta E 2000 by tonal/saturation region and quantized code
differences; HDR adds luminance/headroom, gain-map code/reconstruction, capacity,
and ISO 21496 metadata equality.

Thresholds are fixed before production edits:

- Scheduling, lifetime, reuse, tiling, and expression-order-preserving changes
  must be bitwise equal to the current MLX float32 reference.
- A changed float32 expression is rejected if its stage max absolute error
  against current MLX exceeds `1e-6`, if CPU64-to-candidate RMS/MAE/max exceeds
  CPU64-to-current-MLX by more than five percent plus one float32 ULP at the
  reference magnitude, or if any finite/clamp/gamut/HDR classification changes.
- SDR code differences must be zero for schedule-only work and at most one code
  at the declared final bit depth for an approved arithmetic reorder; Delta E
  2000 must remain below 0.02 at P99 and below 0.05 at maximum.
- HDR headroom/capacity/ISO fields must be identical. HDR luminance error must
  remain below half of the final encoded luminance quantization step. Gain-map
  codes may differ by at most one only for approved arithmetic reorders, with
  reconstruction within the same half-step bound.
- Any new NaN/Inf, changed clipping/classification, systematic tonal or
  saturation bias, or threshold relaxation rejects the candidate.

Grain math is compared with shared pre-generated random fields across CPU64,
CPU32, current MLX32, and candidate MLX32. Native RNG is evaluated separately
for mean, variance, quantiles, spatial/channel correlation, exposure-binned
strength, and power spectrum. A candidate intended to preserve the MLX pattern
must additionally be element-for-element identical.

## Implementation order

1. Land the executable contract and record the pre-edit staircase report.
2. Record synchronized cold/warm stage, dispatch/residency, MLX/RSS/swap, and
   encoder substage baselines; use Metal capture where callable.
3. Measure the balanced Hanatos fallback boundary and test only implementations
   that preserve its CPU64 behavior or pass the predeclared arithmetic gate.
4. Measure deterministic work after grain RNG and moderate scan/color fusion
   boundaries. Keep spectral wavelength accumulation order and safe math.
5. Remove proven duplicate HDR/gain-map/color conversions or host copies. Report
   CoreImage time separately.
6. Implement GUI reuse only for bounded preview intermediates with complete
   parameter keys and invalidation; never retain a full-resolution export graph.
7. Re-run the staircase, focused and full tests, 12/50 MP core/HDR/export matrix,
   five warm repeats, profile/size switches, and memory-growth checks.

## Candidate rejection rules

Reject a candidate that changes RNG sequencing or spectral reduction order,
uses fast/relaxed math or reduced precision, adds an implicit contiguous copy,
spills enough registers to erase end-to-end benefit, increases the 50 MP MLX or
process peak beyond the phase-one envelope, only improves a microbenchmark, or
does not provide a repeatable synchronized wall-time improvement above run
noise. Rejected experiments remain documented but are not connected to the
production path.

## Completion status

- Precision contract and pre-candidate aggregate baseline: complete.
- Four declared profile/route/grain/spatial/output cases executed: complete.
- Synchronized 12 MP, 49.77 MP, HDR projection/export and preview updates:
  complete.
- Accepted production changes: combined-matrix balanced Hanatos fallback and
  bounded MLX preview-stage reuse.
- Rejected experiments: resident fast Hanatos, larger FFT batching, untiled
  scan, reordered DIR FIR, and MLX chemical HDR projection.
- Focused and complete non-GUI regression: see the paired result report.
