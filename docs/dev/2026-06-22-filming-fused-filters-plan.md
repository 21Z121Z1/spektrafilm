# Filming Fused Filter Chain Implementation Plan

Date: 2026-06-22

## Current Probe Failures

- The draft fused path changed a constant image, which proves the FFT boundary handling was not energy preserving.
- Lens blur plus halation crashed during transfer-function multiplication because `(H, W, 1)` and `(H, W, 3)` components were multiplied in place.
- The draft runtime wired fused filtering into CPU production as well as GPU, which would change CPU output semantics before acceptance.

## Implementation Targets

- Keep the existing serial CPU chain as the production CPU behavior.
- Enable the fused path only for MLX-capable backends with `mx.fft`.
- Use the NumPy fused implementation as the strict reference for MLX fused parity.
- Keep old serial filter functions and tests unchanged.

## Acceptance Gates

- Fused inactive filters return the original array unchanged.
- Fused constants remain constant for lens, scatter, halation bounces, diffusion, and combined cases.
- Fused impulse responses stay centered.
- MLX fused matches NumPy fused within `1e-6` on supported systems.
- CPU runtime dispatch stays serial; MLX runtime dispatch calls fused.
- Benchmarks must report runtime, peak memory, output residency, and NumPy fused parity before promoting the optimization as complete.
