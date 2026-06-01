# Development Documentation Index

This directory contains working reports, research notes, implementation records, and review rounds. Treat newer dated documents as stronger routing hints, but verify conclusions against current source and tests before making code changes.

## Current Coordination And Review

| Path | Notes |
| --- | --- |
| [`2026-05-31-autonomous-session-coordination-plan.md`](2026-05-31-autonomous-session-coordination-plan.md) | Current dirty-worktree coordination plan and non-goals. |
| [`2026-05-31-markdown-documentation-audit.md`](2026-05-31-markdown-documentation-audit.md) | Markdown inventory, classification, consolidation changes, and verification evidence from the documentation cleanup. |
| [`2026-05-31-sdr-parity-goal-plan.md`](2026-05-31-sdr-parity-goal-plan.md) | Current plan to replace stale SDR parity guarantees with verifiable checks and corrected documentation. |
| [`2026-05-30-adversarial-code-review-v5.md`](2026-05-30-adversarial-code-review-v5.md) | Latest adversarial review snapshot with confirmed findings and gaps. |
| [`2026-05-30-adversarial-code-review.md`](2026-05-30-adversarial-code-review.md) | Earlier 2026-05-30 adversarial review report. |
| [`2026-05-28-adversarial-review-goal-plan.md`](2026-05-28-adversarial-review-goal-plan.md) | Goal plan for the 2026-05-28 adversarial review pass. |
| [`2026-05-28-adversarial-review-report.md`](2026-05-28-adversarial-review-report.md) | Results of the 2026-05-28 adversarial review pass. |
| [`code-review-2026-05-26.md`](code-review-2026-05-26.md) | Full workspace review from 2026-05-26. Older than the 2026-05-30/31 docs. |
| [`2026-05-26-full-workspace-code-review.md`](2026-05-26-full-workspace-code-review.md) | Verbose full-workspace review snapshot. |

## GPU, MLX, Halide, And Color

| Path | Notes |
| --- | --- |
| [`2026-05-31-mlx-postprocessing-effects.md`](2026-05-31-mlx-postprocessing-effects.md) | MLX feasibility, implementation notes, and tests for halation, diffusion, grain, and related postprocessing filters. |
| [`gpu-cpu-parity-audit-20260530.md`](gpu-cpu-parity-audit-20260530.md) | Numerical parity audit across CPU, MLX, Halide, and unavailable CuPy. |
| [`mlx-optimization-report-20260530.md`](mlx-optimization-report-20260530.md) | MLX backend connection and performance optimization report. |
| [`gpu-benchmark-20260530.md`](gpu-benchmark-20260530.md) | Benchmark configuration, timing tables, and raw benchmark output. |
| [`benchmark-artifacts/halide_mlx_parity_20260531/`](benchmark-artifacts/halide_mlx_parity_20260531/) | Generated Halide/MLX parity benchmark artifacts with synced stage timing and precision notes. This directory may grow while benchmark jobs are active. |
| [`halide-backend-implementation.md`](halide-backend-implementation.md) | Verified Halide backend state. |
| [`halide-impl-plan.md`](halide-impl-plan.md) | Original Halide backend implementation plan. |
| [`halide-deep-research.md`](halide-deep-research.md) | Deep research for the Halide Android port. |
| [`halide-android-port-plan.md`](halide-android-port-plan.md) | Halide Android port plan. |
| [`research-halide-port.md`](research-halide-port.md) | Halide rewrite feasibility research. |
| [`research-gpu-color-management.md`](research-gpu-color-management.md) | GPU acceleration and color-management research. |
| [`gain-map-HDR分析报告.md`](gain-map-HDR分析报告.md) | ISO 21496-1 gain-map HDR integration analysis. |
| [`modern_recovery_peak_budget_plan.md`](modern_recovery_peak_budget_plan.md) | Profile-preserving HDR recovery peak-budget plan. |

## Android Port

| Path | Notes |
| --- | --- |
| [`android-port-implementation-plan-20260528.md`](android-port-implementation-plan-20260528.md) | Android port implementation plan. |
| [`android-port-status-20260528.md`](android-port-status-20260528.md) | Android port status report. |
| [`research-android-app-architecture.md`](research-android-app-architecture.md) | Android app architecture research. |
| [`research-android-port.md`](research-android-port.md) | Android port research and strategy. |
| [`research-android-porting-strategies.md`](research-android-porting-strategies.md) | Android porting strategy comparison. |

## GUI, Memory, Tests, And Hardening

| Path | Notes |
| --- | --- |
| [`research-gui-aesthetics.md`](research-gui-aesthetics.md) | GUI aesthetics and UX research. |
| [`research-gui-color-hdr.md`](research-gui-color-hdr.md) | GUI color-management and HDR preview research. |
| [`research-gui-product-logic.md`](research-gui-product-logic.md) | GUI product logic and UX flow audit. |
| [`gui-research-hardening-implementation.md`](gui-research-hardening-implementation.md) | Implementation record for GUI research hardening. |
| [`research-memory-management.md`](research-memory-management.md) | Memory-management deep research. |
| [`research-memory-optimization-patterns.md`](research-memory-optimization-patterns.md) | Memory-optimization pattern research. |
| [`memory-management-implementation-2026-05-27.md`](memory-management-implementation-2026-05-27.md) | Memory-management implementation notes. |
| [`test-improvement-plan.md`](test-improvement-plan.md) | Older test-improvement plan; later hardening docs supersede parts of it. |
| [`test-system-hardening-2026-05-27.md`](test-system-hardening-2026-05-27.md) | Test-system hardening completion notes. |
| [`accepted-p0-p1-implementation-plan-2026-05-28.md`](accepted-p0-p1-implementation-plan-2026-05-28.md) | Accepted P0/P1 fix implementation plan. |
| [`2026-05-26-develop-upstream-branch-integration-plan.md`](2026-05-26-develop-upstream-branch-integration-plan.md) | Upstream branch integration plan. |
| [`项目状态报告-20260527.md`](项目状态报告-20260527.md) | Chinese project status report from 2026-05-27. |

## Historical Review And Research Rounds

These files are useful for provenance and regression hunting, but are not current by themselves:

- [`code-quality-review-round-1.md`](code-quality-review-round-1.md)
- [`code-quality-review-round-2.md`](code-quality-review-round-2.md)
- [`code-quality-review-round-3.md`](code-quality-review-round-3.md)
- [`code-quality-review-round-4.md`](code-quality-review-round-4.md)
- [`code-quality-review-round-5.md`](code-quality-review-round-5.md)
- [`code-quality-review-round-6.md`](code-quality-review-round-6.md)
- [`review-round-7.md`](review-round-7.md)
- [`review-round-8.md`](review-round-8.md)
- [`research-implementation-round-1.md`](research-implementation-round-1.md)
- [`research-implementation-round-2.md`](research-implementation-round-2.md)
- [`research-implementation-round-3.md`](research-implementation-round-3.md)
- [`research-implementation-round-4.md`](research-implementation-round-4.md)
- [`research-implementation-round-5.md`](research-implementation-round-5.md)
- [`deep-research-implementation-patterns.md`](deep-research-implementation-patterns.md)

## Reference Code

`xdremux-ref/` contains reference Python modules copied from the XDRemux project for HEIF/gain-map I/O comparison. It is reference material, not part of the Spektrafilm runtime package.
