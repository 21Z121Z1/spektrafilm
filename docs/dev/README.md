# Development Documentation Index

This directory contains working reports, research notes, implementation records, and review rounds. Treat newer dated documents as stronger routing hints, but verify conclusions against current source and tests before making code changes.

## Current Coordination And Review

| Path | Notes |
| --- | --- |
| [`2026-05-31-autonomous-session-coordination-plan.md`](2026-05-31-autonomous-session-coordination-plan.md) | Current dirty-worktree coordination plan and non-goals. [中文](2026-05-31-autonomous-session-coordination-plan_zh.md) |
| [`2026-05-31-markdown-documentation-audit.md`](2026-05-31-markdown-documentation-audit.md) | Markdown inventory, classification, consolidation changes, and verification evidence from the documentation cleanup. [中文](2026-05-31-markdown-documentation-audit_zh.md) |
| [`2026-05-31-sdr-parity-goal-plan.md`](2026-05-31-sdr-parity-goal-plan.md) | Current plan to replace stale SDR parity guarantees with verifiable checks and corrected documentation. [中文](2026-05-31-sdr-parity-goal-plan_zh.md) |
| [`2026-05-30-adversarial-code-review-v5.md`](2026-05-30-adversarial-code-review-v5.md) | Latest adversarial review snapshot with confirmed findings and gaps. |
| [`2026-06-01-upstream-main-sync-report.md`](2026-06-01-upstream-main-sync-report.md) | Latest upstream sync completion report. [中文](2026-06-01-upstream-main-sync-report_zh.md) |
| [`2026-06-01-local-cleanup-audit-2026-06-01.md`](2026-06-01-local-cleanup-audit-2026-06-01.md) | Recent local cleanup audit. [中文](2026-06-01-local-cleanup-audit-2026-06-01_zh.md) |
| [`code-review-2026-05-26.md`](code-review-2026-05-26.md) | Full workspace review from 2026-05-26. Referenced by CLAUDE.md for older review findings. [中文](code-review-2026-05-26_zh.md) |

## GPU, MLX, Halide, And Color

| Path | Notes |
| --- | --- |
| [`2026-05-31-mlx-postprocessing-effects.md`](2026-05-31-mlx-postprocessing-effects.md) | MLX feasibility, implementation notes, and tests for halation, diffusion, grain, and related postprocessing filters. [中文](2026-05-31-mlx-postprocessing-effects_zh.md) |
| [`2026-05-31-mlx-compile-elementwise.md`](2026-05-31-mlx-compile-elementwise.md) | MLX compile optimization notes. [中文](2026-05-31-mlx-compile-elementwise_zh.md) |
| [`mlx-optimization-report-20260530.md`](mlx-optimization-report-20260530.md) | MLX backend connection and performance optimization report. |
| [`gpu-benchmark-20260530.md`](gpu-benchmark-20260530.md) | Benchmark configuration, timing tables, and raw benchmark output. [中文](gpu-benchmark-20260530_zh.md) |
| [`benchmark-artifacts/halide_mlx_parity_20260531/`](benchmark-artifacts/halide_mlx_parity_20260531/) | Generated Halide/MLX parity benchmark artifacts with synced stage timing and precision notes. This directory may grow while benchmark jobs are active. |
| [`halide-backend-implementation.md`](halide-backend-implementation.md) | Verified Halide backend state. [中文](halide-backend-implementation_zh.md) |
| [`halide-deep-research.md`](halide-deep-research.md) | Deep research for the Halide Android port. |
| [`halide-android-port-plan.md`](halide-android-port-plan.md) | Halide Android port plan. [中文](halide-android-port-plan_zh.md) |
| [`research-halide-port.md`](research-halide-port.md) | Halide rewrite feasibility research. [中文](research-halide-port_zh.md) |
| [`research-gpu-color-management.md`](research-gpu-color-management.md) | GPU acceleration and color-management research. [中文](research-gpu-color-management_zh.md) |
| [`gain-map-HDR分析报告.md`](gain-map-HDR分析报告.md) | ISO 21496-1 gain-map HDR integration analysis. [English](gain-map-HDR-analysis-report.en.md) |
| [`modern_recovery_peak_budget_plan.md`](modern_recovery_peak_budget_plan.md) | Profile-preserving HDR recovery peak-budget plan. [中文](modern_recovery_peak_budget_plan_zh.md) |

## Android Port

| Path | Notes |
| --- | --- |
| [`android-port-status-20260528.md`](android-port-status-20260528.md) | Android port status report. [中文](android-port-status-20260528_zh.md) |
| [`research-android-app-architecture.md`](research-android-app-architecture.md) | Android app architecture research. [中文](research-android-app-architecture_zh.md) |
| [`research-android-port.md`](research-android-port.md) | Android port research and strategy. |
| [`research-android-porting-strategies.md`](research-android-porting-strategies.md) | Android porting strategy comparison. |

## GUI, Memory, Tests, And Hardening

| Path | Notes |
| --- | --- |
| [`research-gui-aesthetics.md`](research-gui-aesthetics.md) | GUI aesthetics and UX research. [中文](research-gui-aesthetics_zh.md) |
| [`research-gui-color-hdr.md`](research-gui-color-hdr.md) | GUI color-management and HDR preview research. [中文](research-gui-color-hdr_zh.md) |
| [`research-gui-product-logic.md`](research-gui-product-logic.md) | GUI product logic and UX flow audit. [中文](research-gui-product-logic_zh.md) |
| [`gui-research-hardening-implementation.md`](gui-research-hardening-implementation.md) | Implementation record for GUI research hardening. [中文](gui-research-hardening-implementation_zh.md) |
| [`research-memory-management.md`](research-memory-management.md) | Memory-management deep research. [中文](research-memory-management_zh.md) |
| [`research-memory-optimization-patterns.md`](research-memory-optimization-patterns.md) | Memory-optimization pattern research. [中文](research-memory-optimization-patterns_zh.md) |
| [`memory-management-implementation-2026-05-27.md`](memory-management-implementation-2026-05-27.md) | Memory-management implementation notes. [中文](memory-management-implementation-2026-05-27_zh.md) |
| [`test-system-hardening-2026-05-27.md`](test-system-hardening-2026-05-27.md) | Test-system hardening completion notes. [中文](test-system-hardening-2026-05-27_zh.md) |
| [`项目状态报告-20260527.md`](项目状态报告-20260527.md) | Chinese project status report from 2026-05-27. [English](project-status-report-20260527.en.md) |

## Archived Documents

The following document groups were moved to `docs/archive/dev/` on 2026-06-02 after cross-referencing against current code and tests:

- **Code-quality review rounds** (rounds 1-6, review-round-7, review-round-8): all historical, superseded by later reviews
- **Research-implementation rounds** (rounds 1-5): all completed
- **Older adversarial reviews** (2026-05-28 reports, 2026-05-30 pre-v5, remediation report, codex plugin review): superseded by `2026-05-30-adversarial-code-review-v5.md`
- **Completed implementation plans** (halide-impl-plan, accepted-p0-p1, upstream integration, test-improvement-plan): all marked COMPLETED
- **Stale GPU reports** (gpu-cpu-parity-audit, gpu-backend-100-percent-completion, gpu-backend-full-code-review, mlx-backend-review): superseded by 2026-05-31 reports
- **deep-research-implementation-patterns**: absorbed into P0/P1 plan

For provenance, these files remain available under `docs/archive/dev/`.

## Reference Code

`xdremux-ref/` contains reference Python modules copied from the XDRemux project for HEIF/gain-map I/O comparison. It is reference material, not part of the Spektrafilm runtime package.
