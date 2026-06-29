# Spektrafilm Documentation Map

This is the canonical router for Markdown documentation in this workspace.

## Read First

| Path | Use |
| --- | --- |
| [`../README.md`](../README.md) | Project overview, install/run notes, package layout, and user-facing context. |
| [`curve_analysis/README.md`](curve_analysis/README.md) | Generated film+paper HDR curve-analysis corpus and summary report. |

## Bilingual Documentation

All active documentation is available in both English and Chinese. The primary language is noted in each entry. Translation files follow the naming convention:
- English original - Chinese translation: filename_zh.md
- Chinese original - English translation: filename.en.md

The spectral_film_simulations.md (English) and spectral_film_simulations_zh.md (Chinese) pair predates this convention.

## Current Status And Active Work

| Path | Notes |
| --- | --- |
| [`halide-mlx-parity-plan-20260531.md`](halide-mlx-parity-plan-20260531.md) | Current Halide/MLX parity plan, benchmark contract, acceptance standards, and self-audit questions. [中文](halide-mlx-parity-plan-20260531_zh.md) |
| [`upstream-sync-plan-20260602.md`](upstream-sync-plan-20260602.md) | Current upstream sync plan. [中文](upstream-sync-plan-20260602_zh.md) |

## HDR, Color, GPU, And Export

| Path | Notes |
| --- | --- |
| [`color-management-hdr-review-2026-05-31.md`](color-management-hdr-review-2026-05-31.md) | Current color-management/HDR code review, remediation notes, verification status, and remaining risks. [English](color-management-hdr-review-2026-05-31.en.md) |
| [`hdr_profile_aware_raw_validation.md`](hdr_profile_aware_raw_validation.md) | Real ProRAW validation for profile-aware HDR export; companion JSON is `hdr_profile_aware_raw_validation.json`. [English](hdr_profile_aware_raw_validation.en.md) |
| [`film-scan-aware-hdr.md`](film-scan-aware-hdr.md) | Canonical `film_scan_aware` positive film-scan HDR semantics, negative raw diagnostic split, sampling contract, and limitations. |
| [`film-scan-aware-negative-positive-plan.md`](film-scan-aware-negative-positive-plan.md) | Implementation plan for negative-film raw-vs-positive film-scan HDR route separation. |
| [`hdr-film-scan-aware.md`](hdr-film-scan-aware.md) | Compatibility entry point that links to the canonical film-scan-aware HDR document. [中文](hdr-film-scan-aware_zh.md) |
| [`hdr_exr_output_plan.md`](hdr_exr_output_plan.md) | Scene-linear EXR export plan for unclipped HDR archives. [English](hdr_exr_output_plan.en.md) |
| [`hdr/gain-map-HDR分析报告.md`](hdr/gain-map-HDR分析报告.md) | ISO 21496-1 gain-map HDR integration analysis. [English](hdr/gain-map-HDR-analysis-report.en.md) |
| [`hdr/research-gui-color-hdr.md`](hdr/research-gui-color-hdr.md) | GUI color and HDR rendering research. |
| [`heic-iso21496-compliance.md`](heic-iso21496-compliance.md) | Current ISO 21496-1 / HEIC `tmap` validator, CoreImage post-encode repair, fail-closed export behavior, and Mac openability gates. |
| [`hdr-export-pipeline.md`](hdr-export-pipeline.md) | Current RouteMaster pre-rendered SDR/HDR pair export boundary and ISO/Mac HEIC validation contract. |
| [`hdr-routemaster-rewrite-implementation-report.md`](hdr-routemaster-rewrite-implementation-report.md) | RouteMaster rewrite completion report, including SDR equivalence, two HDR modes, pair export, and ISO/HEIC hardening evidence. |
| [`gpu/research-gpu-color-management.md`](gpu/research-gpu-color-management.md) | GPU acceleration and color-management research. [中文](gpu/research-gpu-color-management_zh.md) |
| [`gpu/mlx-optimization-report-20260530.md`](gpu/mlx-optimization-report-20260530.md) | MLX backend performance optimization report. [English](gpu/mlx-optimization-report-20260530.en.md) |
| [`gpu/halide-backend-implementation.md`](gpu/halide-backend-implementation.md) | Verified Halide backend state. [中文](gpu/halide-backend-implementation_zh.md) |
| [`gpu/halide-deep-research.md`](gpu/halide-deep-research.md) | Deep research for the Halide Android port. [中文](gpu/halide-deep-research_zh.md) |
| [`architecture/research-memory-management.md`](architecture/research-memory-management.md) | Memory management and leak detection research. [中文](architecture/research-memory-management_zh.md) |
| [`architecture/research-android-app-architecture.md`](architecture/research-android-app-architecture.md) | Android port architecture research. [中文](architecture/research-android-app-architecture_zh.md) |
| [`reports/android-port-status-20260528.md`](reports/android-port-status-20260528.md) | Android porting status report. [中文](reports/android-port-status-20260528_zh.md) |

## Development Reports And Plans

| Path | Notes |
| --- | --- |
| [`reports/public-surface-hygiene-report-20260622.md`](reports/public-surface-hygiene-report-20260622.md) | Repository Public Surface Hygiene Report. |
| [`reports/mlx-memory-residency-governance-20260629.md`](reports/mlx-memory-residency-governance-20260629.md) | Opt-in MLX memory residency governance, peak-budget policy, resize fallback policy, RouteMaster sidecar helpers, and benchmark artifact contract. |
| [`sdr-upstream-conformance.md`](sdr-upstream-conformance.md) | Locked-upstream SDR conformance harness, commands, thresholds, allowlist, and refresh process. |
| [`issue_positive_film_print_exposure.md`](issue_positive_film_print_exposure.md) | Issue draft for positive-film print-exposure behavior. Bug still exists in `state.py:342`. [中文](issue_positive_film_print_exposure_zh.md) |

## Root-Level Project Documents

| Path | Notes |
| --- | --- |
| [`../CHANGELOG.md`](../CHANGELOG.md) | Release and change history. |
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | Contribution workflow and expectations. |

## Research Source Material

| Path | Notes |
| --- | --- |
| [`spectral_film_simulations.md`](spectral_film_simulations.md) | English source-material writeup from the spectral film simulation thread. [中文](spectral_film_simulations_zh.md) |
| [`spectral_film_simulations_zh.md`](spectral_film_simulations_zh.md) | Chinese translation of the same source material. [English](spectral_film_simulations.md) |

## Generated And Data-Adjacent Documentation

| Path | Notes |
| --- | --- |
| [`curve_analysis/`](curve_analysis/) | Generated curve-analysis corpus: one summary report plus 160 per-combination film+paper reports. |
| [`../src/spektrafilm/data/hdr_curve_profiles/README.md`](../src/spektrafilm/data/hdr_curve_profiles/README.md) | Runtime HDR curve-profile data contract. |
| [`../src/spektrafilm/data/icc/README.md`](../src/spektrafilm/data/icc/README.md) | Bundled ICC profile notes. |
