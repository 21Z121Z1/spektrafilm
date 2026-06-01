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

## Current Status And Active Work

| Path | Notes |
| --- | --- |
| [`dev/2026-05-31-autonomous-session-coordination-plan.md`](dev/2026-05-31-autonomous-session-coordination-plan.md) | Current coordination guardrails for the dirty workspace and concurrent GPU/MLX/Halide work. |
| [`dev/2026-05-31-markdown-documentation-audit.md`](dev/2026-05-31-markdown-documentation-audit.md) | This workspace Markdown audit: inventory, classification, consolidation changes, and verification evidence. |
| [`halide-mlx-parity-plan-20260531.md`](halide-mlx-parity-plan-20260531.md) | Current Halide/MLX parity plan, benchmark contract, acceptance standards, and self-audit questions. |
| [`dev/2026-05-30-adversarial-code-review-v5.md`](dev/2026-05-30-adversarial-code-review-v5.md) | Latest adversarial review snapshot: confirmed medium/low findings and review gaps. |
| [`dev/2026-05-30-adversarial-code-review.md`](dev/2026-05-30-adversarial-code-review.md) | Earlier 2026-05-30 adversarial review report. Read with v5 before taking action. |
| [`sdr-parity-guarantee.md`](sdr-parity-guarantee.md) | SDR parity contract against upstream and verification commands. Treat as high-signal, but re-run checks before relying on it. |
| [`upstream-parity-report.md`](upstream-parity-report.md) | 2026-05-30 upstream parity report for branch relation, changed files, and default-impact analysis. |

## HDR, Color, GPU, And Export

| Path | Notes |
| --- | --- |
| [`color-management-hdr-review-2026-05-31.md`](color-management-hdr-review-2026-05-31.md) | Current 2026-05-31 color-management/HDR code review, remediation notes, verification status, and remaining risks. |
| [`hdr_profile_aware_raw_validation.md`](hdr_profile_aware_raw_validation.md) | Real ProRAW validation for profile-aware HDR export; companion JSON is `hdr_profile_aware_raw_validation.json`. |
| [`hdr_exr_output_plan.md`](hdr_exr_output_plan.md) | Scene-linear EXR export plan for unclipped HDR archives. |
| [`color-management-hdr-deep-review.md`](color-management-hdr-deep-review.md) | Color management and HDR remediation verification report. |
| [`color-management-system-review.md`](color-management-system-review.md) | Runtime, RAW import, GUI preview, and output saving color-management review. |
| [`color_management_code_review.md`](color_management_code_review.md) | Chinese color-management code review. |
| [`color_management_report.md`](color_management_report.md) | Chinese color-management analysis and best-practices report. |
| [`gpu_hardware_acceleration_plan.md`](gpu_hardware_acceleration_plan.md) | Original Metal hardware acceleration implementation plan. |
| [`gpu_hardware_acceleration_evaluation.md`](gpu_hardware_acceleration_evaluation.md) | Apple M1 Pro Metal acceleration evaluation. |
| [`GPU_CODE_REVIEW.md`](GPU_CODE_REVIEW.md) | Chinese Metal GPU acceleration system review. |
| [`dev/2026-05-31-mlx-postprocessing-effects.md`](dev/2026-05-31-mlx-postprocessing-effects.md) | MLX feasibility, implementation notes, and tests for halation, diffusion, grain, and related postprocessing filters. |
| [`dev/gpu-cpu-parity-audit-20260530.md`](dev/gpu-cpu-parity-audit-20260530.md) | GPU/CPU numerical parity audit for MLX, Halide, and CuPy availability. |
| [`dev/mlx-optimization-report-20260530.md`](dev/mlx-optimization-report-20260530.md) | MLX backend performance optimization report. |
| [`dev/gpu-benchmark-20260530.md`](dev/gpu-benchmark-20260530.md) | GPU backend benchmark and raw timing appendix. |

## Development Reports And Plans

| Path | Notes |
| --- | --- |
| [`dev/README.md`](dev/README.md) | Full index for direct files under `docs/dev/`. |
| [`superpowers/plans/README.md`](superpowers/plans/README.md) | Agentic implementation plan index. These are task plans, not necessarily current product state. |
| [`implementation_plan.md`](implementation_plan.md) | Color-management and HDR EXR fusion refactor plan. |
| [`upstream_migration.md`](upstream_migration.md) | Upstream merge migration document. |
| [`CODE_REVIEW.md`](CODE_REVIEW.md) | Chinese v0.3.1 code review. Superseded in parts by later dev/audit docs. |
| [`memory_management_review.md`](memory_management_review.md) | Chinese memory-management review. |
| [`issue_positive_film_print_exposure.md`](issue_positive_film_print_exposure.md) | Issue draft for positive-film print-exposure behavior. |
| [`ISSUE_color_space_metadata.md`](ISSUE_color_space_metadata.md) | Issue draft for missing color-space metadata in saved images. |

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
| [`spectral_film_simulations.md`](spectral_film_simulations.md) | English source-material writeup from the spectral film simulation thread. |
| [`spectral_film_simulations_zh.md`](spectral_film_simulations_zh.md) | Chinese translation of the same source material. |

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

The former top-level `docs 2/` tree now lives under [`archive/docs-2-legacy-20260531/`](archive/docs-2-legacy-20260531/).
