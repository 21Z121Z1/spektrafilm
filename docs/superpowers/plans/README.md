# Superpowers Implementation Plans

This directory contains agentic implementation plans. A plan records intended work and verification steps; it is not proof that the implementation was completed. Prefer newer result documents and current tests when checking final state.

## 2026-05-31 Active Plans

| Path | Goal |
| --- | --- |
| [`2026-05-31-adversarial-review-remediation.md`](2026-05-31-adversarial-review-remediation.md) | Remediate reproducible defects from the 2026-05-30 adversarial review reports. |
| [`2026-05-31-markdown-documentation-consolidation.md`](2026-05-31-markdown-documentation-consolidation.md) | Consolidate and organize Markdown documentation across the workspace. |
| [`2026-05-31-mlx-backend-review-fixes.md`](2026-05-31-mlx-backend-review-fixes.md) | Fix MLX backend review issues around precision selection, residency, copies, and documentation evidence. |
| [`2026-05-31-mlx-postprocessing-effects.md`](2026-05-31-mlx-postprocessing-effects.md) | Evaluate and harden MLX backend routing for halation, diffusion, grain, and related postprocessing effects. |

## HDR, Color, And Export Plans

| Path | Goal |
| --- | --- |
| [`2026-05-23-aces-color-management.md`](2026-05-23-aces-color-management.md) | Add an explicit ACES reference workflow. |
| [`2026-05-23-hdr-diffuse-white-calibration.md`](2026-05-23-hdr-diffuse-white-calibration.md) | Establish a diffuse-white anchor for HDR export. |
| [`2026-05-23-hdr-photo-mapping-execution.md`](2026-05-23-hdr-photo-mapping-execution.md) | Execute HDR photo mapping implementation. |
| [`2026-05-23-hdr-photo-mapping.md`](2026-05-23-hdr-photo-mapping.md) | Implement HDR photo export with explicit diffuse/paper-white anchor. |
| [`2026-05-24-auto-exposure-scene-linear.md`](2026-05-24-auto-exposure-scene-linear.md) | Improve automatic exposure for scene-linear, ACES, and HDR inputs. |
| [`2026-05-24-hdr-scene-linear-exr.md`](2026-05-24-hdr-scene-linear-exr.md) | Make HDR EXR export an explicit scene-linear archive. |
| [`2026-05-24-raw-hdr-scene-energy-import.md`](2026-05-24-raw-hdr-scene-energy-import.md) | Add RAW import scene-energy sidecar diagnostics. |
| [`2026-05-24-scene-energy-hdr-gainmap-autoexposure.md`](2026-05-24-scene-energy-hdr-gainmap-autoexposure.md) | Add scene-energy sidecar support for HDR gain-map export. |
| [`2026-05-25-profile-aware-hdr-photo-export.md`](2026-05-25-profile-aware-hdr-photo-export.md) | Implement profile-aware SDR/HDR tone-curve mapping. |

## GPU, Halide, GUI, Memory, And Test Plans

| Path | Goal |
| --- | --- |
| [`2026-05-23-metal-processing-acceleration.md`](2026-05-23-metal-processing-acceleration.md) | Complete Apple Silicon Metal acceleration across hot-path kernels. |
| [`2026-05-24-film-simulation-lossless-speed.md`](2026-05-24-film-simulation-lossless-speed.md) | Speed up film simulation without loosening precision. |
| [`2026-05-24-gui-release-hardening.md`](2026-05-24-gui-release-hardening.md) | Harden GUI preview, output saving, metadata, and workers. |
| [`2026-05-27-gpu-color-management-audit-fixes.md`](2026-05-27-gpu-color-management-audit-fixes.md) | Reconcile GPU color-management research with real code defects. |
| [`2026-05-27-gui-research-hardening.md`](2026-05-27-gui-research-hardening.md) | Convert GUI research findings into low-risk improvements. |
| [`2026-05-27-halide-android-port-foundation.md`](2026-05-27-halide-android-port-foundation.md) | Add a verified Halide/Android foundation without overclaiming completeness. |
| [`2026-05-27-halide-backend.md`](2026-05-27-halide-backend.md) | Add optional Halide backend and first LUT kernel. |
| [`2026-05-27-memory-management-fixes.md`](2026-05-27-memory-management-fixes.md) | Remove real memory pressure bugs. |
| [`2026-05-27-test-system-hardening.md`](2026-05-27-test-system-hardening.md) | Make pytest assumptions truthful and maintainable. |
| [`2026-05-28-halide-android-aot-contract.md`](2026-05-28-halide-android-aot-contract.md) | Turn Halide/Android foundation into a verified AOT pre-JNI contract. |
| [`2026-05-28-halide-continuation.md`](2026-05-28-halide-continuation.md) | Continue Halide backend work from the 2026-05-28 base. |
