# Spektrafilm Documentation Map

This is the canonical router for Markdown documentation in this workspace. Start here before using older review notes, implementation plans, or generated reports as current truth.

## Read First

| Path | Use |
| --- | --- |
| [`../README.md`](../README.md) | Project overview, install/run notes, package layout, and user-facing context. |
| [`dev/README.md`](dev/README.md) | Current development reports, active coordination docs, GPU/MLX/Halide notes, Android work, and older review rounds. |
| [`agent_audit/README.md`](agent_audit/README.md) | 2026-05-28 audit entry points, accepted findings, review dimensions, contracts, and validation matrix. |
| [`curve_analysis/README.md`](curve_analysis/README.md) | Generated film+paper HDR curve-analysis corpus and summary report. |
| [`archive/README.md`](archive/README.md) | Preserved legacy documentation snapshots. Archive docs are evidence, not the active source of truth. |

## Bilingual Documentation

All active documentation is available in both English and Chinese. The primary language is noted in each entry. Translation files follow the naming convention:
- English original - Chinese translation: filename_zh.md
- Chinese original - English translation: filename.en.md

The spectral_film_simulations.md (English) and spectral_film_simulations_zh.md (Chinese) pair predates this convention.

## Current Status And Active Work

| Path | Notes |
| --- | --- |
| [`dev/2026-05-31-autonomous-session-coordination-plan.md`](dev/2026-05-31-autonomous-session-coordination-plan.md) | Current coordination guardrails for the dirty workspace and concurrent GPU/MLX/Halide work. [中文](dev/2026-05-31-autonomous-session-coordination-plan_zh.md) |
| [`dev/2026-05-31-markdown-documentation-audit.md`](dev/2026-05-31-markdown-documentation-audit.md) | This workspace Markdown audit: inventory, classification, consolidation changes, and verification evidence. [中文](dev/2026-05-31-markdown-documentation-audit_zh.md) |
| [`halide-mlx-parity-plan-20260531.md`](halide-mlx-parity-plan-20260531.md) | Current Halide/MLX parity plan, benchmark contract, acceptance standards, and self-audit questions. [中文](halide-mlx-parity-plan-20260531_zh.md) |
| [`dev/2026-05-30-adversarial-code-review-v5.md`](dev/2026-05-30-adversarial-code-review-v5.md) | Latest adversarial review snapshot: confirmed medium/low findings and review gaps. |
| [`upstream-sync-plan-20260602.md`](upstream-sync-plan-20260602.md) | Current upstream sync plan. [中文](upstream-sync-plan-20260602_zh.md) |
| [`dev/2026-06-01-upstream-main-sync-report.md`](dev/2026-06-01-upstream-main-sync-report.md) | Latest upstream sync completion report. [中文](dev/2026-06-01-upstream-main-sync-report_zh.md) |
| [`dev/2026-05-31-sdr-parity-goal-plan.md`](dev/2026-05-31-sdr-parity-goal-plan.md) | Current SDR parity verification plan. [中文](dev/2026-05-31-sdr-parity-goal-plan_zh.md) |

## HDR, Color, GPU, And Export

| Path | Notes |
| --- | --- |
| [`color-management-hdr-review-2026-05-31.md`](color-management-hdr-review-2026-05-31.md) | Current 2026-05-31 color-management/HDR code review, remediation notes, verification status, and remaining risks. [English](color-management-hdr-review-2026-05-31.en.md) |
| [`hdr_profile_aware_raw_validation.md`](hdr_profile_aware_raw_validation.md) | Real ProRAW validation for profile-aware HDR export; companion JSON is `hdr_profile_aware_raw_validation.json`. [English](hdr_profile_aware_raw_validation.en.md) |
| [`film-scan-aware-hdr.md`](film-scan-aware-hdr.md) | Canonical `film_scan_aware` positive film-scan HDR semantics, negative raw diagnostic split, sampling contract, and limitations. |
| [`film-scan-aware-negative-positive-plan.md`](film-scan-aware-negative-positive-plan.md) | Implementation plan for negative-film raw-vs-positive film-scan HDR route separation. |
| [`hdr-film-scan-aware.md`](hdr-film-scan-aware.md) | Compatibility entry point that links to the canonical film-scan-aware HDR document. [中文](hdr-film-scan-aware_zh.md) |
| [`hdr_exr_output_plan.md`](hdr_exr_output_plan.md) | Scene-linear EXR export plan for unclipped HDR archives. [English](hdr_exr_output_plan.en.md) |
| [`dev/2026-05-31-mlx-postprocessing-effects.md`](dev/2026-05-31-mlx-postprocessing-effects.md) | MLX feasibility, implementation notes, and tests for halation, diffusion, grain, and related postprocessing filters. [中文](dev/2026-05-31-mlx-postprocessing-effects_zh.md) |
| [`dev/mlx-optimization-report-20260530.md`](dev/mlx-optimization-report-20260530.md) | MLX backend performance optimization report. |
| [`dev/gpu-benchmark-20260530.md`](dev/gpu-benchmark-20260530.md) | GPU backend benchmark and raw timing appendix. [中文](dev/gpu-benchmark-20260530_zh.md) |
| [`dev/halide-backend-implementation.md`](dev/halide-backend-implementation.md) | Verified Halide backend state. [中文](dev/halide-backend-implementation_zh.md) |
| [`dev/halide-deep-research.md`](dev/halide-deep-research.md) | Deep research for the Halide Android port. |
| [`dev/halide-android-port-plan.md`](dev/halide-android-port-plan.md) | Halide Android port plan. [中文](dev/halide-android-port-plan_zh.md) |
| [`dev/research-halide-port.md`](dev/research-halide-port.md) | Halide rewrite feasibility research. [中文](dev/research-halide-port_zh.md) |
| [`dev/research-gpu-color-management.md`](dev/research-gpu-color-management.md) | GPU acceleration and color-management research. [中文](dev/research-gpu-color-management_zh.md) |
| [`dev/gain-map-HDR分析报告.md`](dev/gain-map-HDR分析报告.md) | ISO 21496-1 gain-map HDR integration analysis. [English](dev/gain-map-HDR-analysis-report.en.md) |
| [`dev/modern_recovery_peak_budget_plan.md`](dev/modern_recovery_peak_budget_plan.md) | Profile-preserving HDR recovery peak-budget plan. [中文](dev/modern_recovery_peak_budget_plan_zh.md) |

## Development Reports And Plans

| Path | Notes |
| --- | --- |
| [`dev/README.md`](dev/README.md) | Full index for direct files under `docs/dev/`. |
| [`superpowers/plans/README.md`](superpowers/plans/README.md) | Agentic implementation plan index. 1 active plan (ACES color management); 33 completed plans archived. |
| [`issue_positive_film_print_exposure.md`](issue_positive_film_print_exposure.md) | Issue draft for positive-film print-exposure behavior. Bug still exists in `state.py:342`. [中文](issue_positive_film_print_exposure_zh.md) |

## Root-Level Project Documents

| Path | Notes |
| --- | --- |
| [`../CHANGELOG.md`](../CHANGELOG.md) | Release and change history. |
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | Contribution workflow and expectations. |
| [`../CLAUDE.md`](../CLAUDE.md) | Local agent instructions for implementation and review work. |
| [`../CLAUDE-RESEARCH.md`](../CLAUDE-RESEARCH.md) | Local agent instructions for GPU and color-management research work. |

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

## Archive Policy

Archived documentation is preserved because older plans, review rounds, and duplicate snapshots are useful for provenance. Do not treat archived files as current implementation guidance without comparing them to:

1. current source and tests,
2. this documentation map,
3. the newest relevant `docs/dev/` reports,
4. the newest relevant `docs/superpowers/plans/` plan.

### 2026-06-02 Archive Sweep

The following groups were archived on 2026-06-02 after cross-referencing against current code and tests:

- **Root-level color/HDR reviews** (5 files): superseded by `color-management-hdr-review-2026-05-31.md`
- **Root-level GPU reviews** (4 files): superseded by `dev/` GPU docs and `halide-mlx-parity-plan-20260531.md`
- **Root-level plans/migration** (5 files): completed or superseded by upstream sync reports
- **dev/ adversarial reviews** (6 files): superseded by `2026-05-30-adversarial-code-review-v5.md`
- **dev/ completed plans** (4 files): all marked COMPLETED
- **dev/ code-quality rounds** (14 files): all historical review rounds
- **dev/ stale GPU reports** (4 files): superseded by 2026-05-31 GPU reports
- **superpowers/plans/ completed plans** (33 files): all completed plans moved to `superpowers/plans/archive/`

Total archived: 77 files moved to `archive/`, `archive/dev/`, and `superpowers/plans/archive/`.

The former `docs-2-legacy-20260531/` directory was removed on 2026-06-02 after confirming all unique files were preserved in `archive/dev/`.
