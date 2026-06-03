> 这是英文原文的中文翻译。权威版本请参考英文原文。

# 开发文档索引

本目录包含工作报告、研究笔记、实现记录和审查轮次。较新的日期文档可作为更强的路由提示，但在进行代码更改之前，请根据当前源代码和测试验证结论。

## 当前协调与审查

| 路径 | 说明 |
| --- | --- |
| [`2026-05-31-autonomous-session-coordination-plan.md`](2026-05-31-autonomous-session-coordination-plan.md) | 当前脏工作树协调计划和非目标。[中文](2026-05-31-autonomous-session-coordination-plan_zh.md) |
| [`2026-05-31-markdown-documentation-audit.md`](2026-05-31-markdown-documentation-audit.md) | 文档清理中的 Markdown 清单、分类、合并变更和验证证据。[中文](2026-05-31-markdown-documentation-audit_zh.md) |
| [`2026-05-31-sdr-parity-goal-plan.md`](2026-05-31-sdr-parity-goal-plan.md) | 当前计划：用可验证的检查和修正的文档替换过时的 SDR 一致性保证。[中文](2026-05-31-sdr-parity-goal-plan_zh.md) |
| [`2026-05-30-adversarial-code-review-v5.md`](2026-05-30-adversarial-code-review-v5.md) | 最新的对抗性审查快照，包含已确认的发现和差距。 |
| [`2026-06-01-upstream-main-sync-report.md`](2026-06-01-upstream-main-sync-report.md) | 最新的上游同步完成报告。[中文](2026-06-01-upstream-main-sync-report_zh.md) |
| [`2026-06-01-local-cleanup-audit-2026-06-01.md`](2026-06-01-local-cleanup-audit-2026-06-01.md) | 近期本地清理审计。[中文](2026-06-01-local-cleanup-audit-2026-06-01_zh.md) |
| [`code-review-2026-05-26.md`](code-review-2026-05-26.md) | 2026-05-26 的完整工作区审查。CLAUDE.md 引用此文件中的旧审查发现。[中文](code-review-2026-05-26_zh.md) |

## GPU、MLX、Halide 与色彩

| 路径 | 说明 |
| --- | --- |
| [`2026-05-31-mlx-postprocessing-effects.md`](2026-05-31-mlx-postprocessing-effects.md) | MLX 可行性、实现说明以及光晕、扩散、颗粒和相关后处理滤镜的测试。[中文](2026-05-31-mlx-postprocessing-effects_zh.md) |
| [`2026-05-31-mlx-compile-elementwise.md`](2026-05-31-mlx-compile-elementwise.md) | MLX 编译优化说明。[中文](2026-05-31-mlx-compile-elementwise_zh.md) |
| [`mlx-optimization-report-20260530.md`](mlx-optimization-report-20260530.md) | MLX 后端连接和性能优化报告。 |
| [`gpu-benchmark-20260530.md`](gpu-benchmark-20260530.md) | 基准测试配置、计时表和原始基准测试输出。[中文](gpu-benchmark-20260530_zh.md) |
| [`benchmark-artifacts/halide_mlx_parity_20260531/`](benchmark-artifacts/halide_mlx_parity_20260531/) | 生成的 Halide/MLX 一致性基准测试产物，包含同步的阶段计时和精度说明。此目录可能在基准测试任务活跃期间增长。 |
| [`halide-backend-implementation.md`](halide-backend-implementation.md) | 已验证的 Halide 后端状态。[中文](halide-backend-implementation_zh.md) |
| [`halide-deep-research.md`](halide-deep-research.md) | Halide Android 移植的深度研究。 |
| [`halide-android-port-plan.md`](halide-android-port-plan.md) | Halide Android 移植计划。[中文](halide-android-port-plan_zh.md) |
| [`research-halide-port.md`](research-halide-port.md) | Halide 重写可行性研究。[中文](research-halide-port_zh.md) |
| [`research-gpu-color-management.md`](research-gpu-color-management.md) | GPU 加速和色彩管理研究。[中文](research-gpu-color-management_zh.md) |
| [`gain-map-HDR分析报告.md`](gain-map-HDR分析报告.md) | ISO 21496-1 增益图 HDR 集成分析。[English](gain-map-HDR-analysis-report.en.md) |
| [`modern_recovery_peak_budget_plan.md`](modern_recovery_peak_budget_plan.md) | 保持配置文件的 HDR 恢复峰值预算计划。[中文](modern_recovery_peak_budget_plan_zh.md) |

## Android 移植

| 路径 | 说明 |
| --- | --- |
| [`android-port-status-20260528.md`](android-port-status-20260528.md) | Android 移植状态报告。[中文](android-port-status-20260528_zh.md) |
| [`research-android-app-architecture.md`](research-android-app-architecture.md) | Android 应用架构研究。[中文](research-android-app-architecture_zh.md) |
| [`research-android-port.md`](research-android-port.md) | Android 移植研究和策略。 |
| [`research-android-porting-strategies.md`](research-android-porting-strategies.md) | Android 移植策略比较。 |

## GUI、内存、测试与加固

| 路径 | 说明 |
| --- | --- |
| [`research-gui-aesthetics.md`](research-gui-aesthetics.md) | GUI 美学和用户体验研究。[中文](research-gui-aesthetics_zh.md) |
| [`research-gui-color-hdr.md`](research-gui-color-hdr.md) | GUI 色彩管理和 HDR 预览研究。[中文](research-gui-color-hdr_zh.md) |
| [`research-gui-product-logic.md`](research-gui-product-logic.md) | GUI 产品逻辑和用户体验流程审计。[中文](research-gui-product-logic_zh.md) |
| [`gui-research-hardening-implementation.md`](gui-research-hardening-implementation.md) | GUI 研究加固的实现记录。[中文](gui-research-hardening-implementation_zh.md) |
| [`research-memory-management.md`](research-memory-management.md) | 内存管理深度研究。[中文](research-memory-management_zh.md) |
| [`research-memory-optimization-patterns.md`](research-memory-optimization-patterns.md) | 内存优化模式研究。[中文](research-memory-optimization-patterns_zh.md) |
| [`memory-management-implementation-2026-05-27.md`](memory-management-implementation-2026-05-27.md) | 内存管理实现说明。[中文](memory-management-implementation-2026-05-27_zh.md) |
| [`test-system-hardening-2026-05-27.md`](test-system-hardening-2026-05-27.md) | 测试系统加固完成说明。[中文](test-system-hardening-2026-05-27_zh.md) |
| [`项目状态报告-20260527.md`](项目状态报告-20260527.md) | 2026-05-27 的中文项目状态报告。[English](project-status-report-20260527.en.md) |

## 已归档文档

以下文档组在 2026-06-02 与当前代码和测试交叉引用后，已移至 `docs/archive/dev/`：

- **代码质量审查轮次**（第 1-6 轮、review-round-7、review-round-8）：全部为历史文档，已被后续审查取代
- **研究实现轮次**（第 1-5 轮）：全部已完成
- **较早的对抗性审查**（2026-05-28 报告、2026-05-30 v5 之前版本、补救报告、codex 插件审查）：已被 `2026-05-30-adversarial-code-review-v5.md` 取代
- **已完成的实现计划**（halide-impl-plan、accepted-p0-p1、upstream integration、test-improvement-plan）：全部标记为已完成
- **过时的 GPU 报告**（gpu-cpu-parity-audit、gpu-backend-100-percent-completion、gpu-backend-full-code-review、mlx-backend-review）：已被 2026-05-31 报告取代
- **deep-research-implementation-patterns**：已并入 P0/P1 计划

为保留来源信息，这些文件仍在 `docs/archive/dev/` 下可用。

## 参考代码

`xdremux-ref/` 包含从 XDRemux 项目复制的参考 Python 模块，用于 HEIF/增益图 I/O 比较。这是参考资料，不是 Spektrafilm 运行时包的一部分。
