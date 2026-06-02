# Superpowers Implementation Plans

This directory contains agentic implementation plans. A plan records intended work and verification steps; it is not proof that the implementation was completed. Prefer newer result documents and current tests when checking final state.

## Active Plans

| Path | Goal |
| --- | --- |
| [`2026-05-23-aces-color-management.md`](2026-05-23-aces-color-management.md) | Add an explicit ACES reference color-management workflow. |

## Archived Plans

33 completed plans have been moved to [`archive/`](archive/) on 2026-06-02. These include:

- **2026-05-23/24 HDR plans** (8): diffuse-white calibration, HDR photo mapping, scene-energy import, gain-map autoexposure, profile-aware export, auto-exposure, scene-linear EXR — all implemented via Dual-Layer HDR Mapping
- **2026-05-23/24 GPU/GUI plans** (3): Metal acceleration, film-simulation speed, GUI release hardening — completed
- **2026-05-27 Halide/Android plans** (3): Halide backend, Android port foundation, AOT contract — completed
- **2026-05-27 infra plans** (4): test hardening, memory fixes, GUI hardening, GPU color audit — completed
- **2026-05-28 Halide plans** (2): continuation, Android AOT contract — completed
- **2026-05-31 remediation plans** (10): adversarial review, GPU backend, MLX backend, color management, codex plugin, macOS liquid glass, documentation consolidation — all completed
- **2026-06-01 plans** (2): film-scan-aware HDR, upstream main sync — completed

For provenance, archived plans remain available under `archive/`.
