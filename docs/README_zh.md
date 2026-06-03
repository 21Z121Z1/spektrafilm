> 这是英文原文的中文翻译。权威版本请参考英文原文。

# Spektrafilm 文档索引

这是本工作区 Markdown 文档的权威路由表。在使用较旧的评审记录、实施计划或生成的报告作为当前依据之前，请先查阅此文档。

## 首先阅读

| 路径 | 用途 |
| --- | --- |
| [`../README.md`](../README.md) | 项目概述、安装/运行说明、包结构以及面向用户的上下文。 |
| [`dev/README.md`](dev/README.md) | 当前开发报告、活跃的协调文档、GPU/MLX/Halide 笔记、Android 开发工作以及较旧的评审轮次。 |
| [`agent_audit/README.md`](agent_audit/README.md) | 2026-05-28 审计入口、已接受的发现、评审维度、约定和验证矩阵。 |
| [`curve_analysis/README.md`](curve_analysis/README.md) | 生成的胶片+相纸 HDR 曲线分析语料库和汇总报告。 |
| [`archive/README.md`](archive/README.md) | 保留的遗留文档快照。归档文档作为证据存在，不是当前的权威信息来源。 |

## 双语文档

所有活跃文档均提供英文和中文版本。每条记录标注主要语言。翻译文件遵循以下命名约定：
- 英文原文 - 中文翻译：filename_zh.md
- 中文原文 - 英文翻译：filename.en.md

spectral_film_simulations.md（英文）和 spectral_film_simulations_zh.md（中文）这一对文件早于此约定。

## 当前状态与活跃工作

| 路径 | 说明 |
| --- | --- |
| [`dev/2026-05-31-autonomous-session-coordination-plan.md`](dev/2026-05-31-autonomous-session-coordination-plan.md) | 当前针对脏工作区和并发 GPU/MLX/Halide 工作的协调保护措施。 [中文](dev/2026-05-31-autonomous-session-coordination-plan_zh.md) |
| [`dev/2026-05-31-markdown-documentation-audit.md`](dev/2026-05-31-markdown-documentation-audit.md) | 本工作区 Markdown 审计：清单、分类、合并变更和验证证据。 [中文](dev/2026-05-31-markdown-documentation-audit_zh.md) |
| [`halide-mlx-parity-plan-20260531.md`](halide-mlx-parity-plan-20260531.md) | 当前 Halide/MLX 对等计划、基准测试约定、验收标准和自查问题。 [中文](halide-mlx-parity-plan-20260531_zh.md) |
| [`dev/2026-05-30-adversarial-code-review-v5.md`](dev/2026-05-30-adversarial-code-review-v5.md) | 最新对抗性评审快照：已确认的中/低级别发现和评审缺口。 |
| [`upstream-sync-plan-20260602.md`](upstream-sync-plan-20260602.md) | 当前上游同步计划。 [中文](upstream-sync-plan-20260602_zh.md) |
| [`dev/2026-06-01-upstream-main-sync-report.md`](dev/2026-06-01-upstream-main-sync-report.md) | 最新上游同步完成报告。 [中文](dev/2026-06-01-upstream-main-sync-report_zh.md) |
| [`dev/2026-05-31-sdr-parity-goal-plan.md`](dev/2026-05-31-sdr-parity-goal-plan.md) | 当前 SDR 对等验证计划。 [中文](dev/2026-05-31-sdr-parity-goal-plan_zh.md) |

## HDR、色彩、GPU 与导出

| 路径 | 说明 |
| --- | --- |
| [`color-management-hdr-review-2026-05-31.md`](color-management-hdr-review-2026-05-31.md) | 当前 2026-05-31 色彩管理/HDR 代码评审、修复说明、验证状态和剩余风险。 [英文](color-management-hdr-review-2026-05-31.en.md) |
| [`hdr_profile_aware_raw_validation.md`](hdr_profile_aware_raw_validation.md) | 用于配置感知 HDR 导出的真实 ProRAW 验证；配套 JSON 文件为 `hdr_profile_aware_raw_validation.json`。 [英文](hdr_profile_aware_raw_validation.en.md) |
| [`film-scan-aware-hdr.md`](film-scan-aware-hdr.md) | 规范的 `film_scan_aware` 正片扫描 HDR 语义、负片原始诊断拆分、采样约定和限制。 |
| [`film-scan-aware-negative-positive-plan.md`](film-scan-aware-negative-positive-plan.md) | 负片原始数据与正片扫描 HDR 路由分离的实施计划。 |
| [`hdr-film-scan-aware.md`](hdr-film-scan-aware.md) | 指向规范胶片扫描感知 HDR 文档的兼容性入口。 [中文](hdr-film-scan-aware_zh.md) |
| [`hdr_exr_output_plan.md`](hdr_exr_output_plan.md) | 用于未裁剪 HDR 存档的场景线性 EXR 导出计划。 [英文](hdr_exr_output_plan.en.md) |
| [`dev/2026-05-31-mlx-postprocessing-effects.md`](dev/2026-05-31-mlx-postprocessing-effects.md) | MLX 可行性、实施说明以及光晕、扩散、颗粒和相关后处理滤镜的测试。 [中文](dev/2026-05-31-mlx-postprocessing-effects_zh.md) |
| [`dev/mlx-optimization-report-20260530.md`](dev/mlx-optimization-report-20260530.md) | MLX 后端性能优化报告。 |
| [`dev/gpu-benchmark-20260530.md`](dev/gpu-benchmark-20260530.md) | GPU 后端基准测试和原始计时附录。 [中文](dev/gpu-benchmark-20260530_zh.md) |
| [`dev/halide-backend-implementation.md`](dev/halide-backend-implementation.md) | 已验证的 Halide 后端状态。 [中文](dev/halide-backend-implementation_zh.md) |
| [`dev/halide-deep-research.md`](dev/halide-deep-research.md) | Halide Android 移植的深度研究。 |
| [`dev/halide-android-port-plan.md`](dev/halide-android-port-plan.md) | Halide Android 移植计划。 [中文](dev/halide-android-port-plan_zh.md) |
| [`dev/research-halide-port.md`](dev/research-halide-port.md) | Halide 重写可行性研究。 [中文](dev/research-halide-port_zh.md) |
| [`dev/research-gpu-color-management.md`](dev/research-gpu-color-management.md) | GPU 加速和色彩管理研究。 [中文](dev/research-gpu-color-management_zh.md) |
| [`dev/gain-map-HDR分析报告.md`](dev/gain-map-HDR分析报告.md) | ISO 21496-1 增益图 HDR 集成分析。 [英文](dev/gain-map-HDR-analysis-report.en.md) |
| [`dev/modern_recovery_peak_budget_plan.md`](dev/modern_recovery_peak_budget_plan.md) | 配置保持的 HDR 恢复峰值预算计划。 [中文](dev/modern_recovery_peak_budget_plan_zh.md) |

## 开发报告与计划

| 路径 | 说明 |
| --- | --- |
| [`dev/README.md`](dev/README.md) | `docs/dev/` 下直接文件的完整索引。 |
| [`superpowers/plans/README.md`](superpowers/plans/README.md) | 智能实施计划索引。1 个活跃计划（ACES 色彩管理）；33 个已完成计划已归档。 |
| [`issue_positive_film_print_exposure.md`](issue_positive_film_print_exposure.md) | 正片打印曝光行为的问题草稿。该缺陷仍存在于 `state.py:342`。 [中文](issue_positive_film_print_exposure_zh.md) |

## 根目录级项目文档

| 路径 | 说明 |
| --- | --- |
| [`../CHANGELOG.md`](../CHANGELOG.md) | 发布和变更历史。 |
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | 贡献工作流程和期望。 |
| [`../CLAUDE.md`](../CLAUDE.md) | 用于实施和评审工作的本地智能体指令。 |
| [`../CLAUDE-RESEARCH.md`](../CLAUDE-RESEARCH.md) | 用于 GPU 和色彩管理研究工作的本地智能体指令。 |

## 研究源材料

| 路径 | 说明 |
| --- | --- |
| [`spectral_film_simulations.md`](spectral_film_simulations.md) | 来自光谱胶片模拟线程的英文源材料文章。 [中文](spectral_film_simulations_zh.md) |
| [`spectral_film_simulations_zh.md`](spectral_film_simulations_zh.md) | 同一源材料的中文翻译。 [英文](spectral_film_simulations.md) |

## 生成的与数据相关的文档

| 路径 | 说明 |
| --- | --- |
| [`curve_analysis/`](curve_analysis/) | 生成的曲线分析语料库：1 份汇总报告加上 160 份按胶片+相纸组合分类的报告。 |
| [`../src/spektrafilm/data/hdr_curve_profiles/README.md`](../src/spektrafilm/data/hdr_curve_profiles/README.md) | 运行时 HDR 曲线配置数据约定。 |
| [`../src/spektrafilm/data/icc/README.md`](../src/spektrafilm/data/icc/README.md) | 捆绑的 ICC 配置文件说明。 |

## 归档策略

归档文档被保留是因为较旧的计划、评审轮次和重复快照对溯源有价值。在未与以下内容进行比对之前，请勿将归档文件视为当前的实施指导：

1. 当前源代码和测试，
2. 本文档索引，
3. 最新的相关 `docs/dev/` 报告，
4. 最新的相关 `docs/superpowers/plans/` 计划。

### 2026-06-02 归档整理

以下分组在 2026-06-02 经过与当前代码和测试的交叉比对后被归档：

- **根目录级色彩/HDR 评审**（5 个文件）：被 `color-management-hdr-review-2026-05-31.md` 取代
- **根目录级 GPU 评审**（4 个文件）：被 `dev/` GPU 文档和 `halide-mlx-parity-plan-20260531.md` 取代
- **根目录级计划/迁移**（5 个文件）：已完成或被上游同步报告取代
- **dev/ 对抗性评审**（6 个文件）：被 `2026-05-30-adversarial-code-review-v5.md` 取代
- **dev/ 已完成计划**（4 个文件）：全部标记为已完成
- **dev/ 代码质量轮次**（14 个文件）：全部为历史评审轮次
- **dev/ 过期 GPU 报告**（4 个文件）：被 2026-05-31 GPU 报告取代
- **superpowers/plans/ 已完成计划**（33 个文件）：所有已完成计划移至 `superpowers/plans/archive/`

共计归档：77 个文件移至 `archive/`、`archive/dev/` 和 `superpowers/plans/archive/`。

原 `docs-2-legacy-20260531/` 目录在 2026-06-02 确认所有唯一文件已保存在 `archive/dev/` 中后被移除。
