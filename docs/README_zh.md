> 这是英文原文的中文翻译。权威版本请参考英文原文。

# Spektrafilm 文档索引

这是本工作区 Markdown 文档的权威路由表。

## 首先阅读

| 路径 | 用途 |
| --- | --- |
| [`../README.md`](../README.md) | 项目概述、安装/运行说明、包结构以及面向用户的上下文。 |
| [`curve_analysis/README.md`](curve_analysis/README.md) | 生成的胶片+相纸 HDR 曲线分析语料库和汇总报告。 |

## 双语文档

所有活跃文档均提供英文和中文版本。每条记录标注主要语言。翻译文件遵循以下命名约定：
- 英文原文 - 中文翻译：filename_zh.md
- 中文原文 - 英文翻译：filename.en.md

spectral_film_simulations.md（英文）和 spectral_film_simulations_zh.md（中文）这一对文件早于此约定。

## 当前状态与活跃工作

| 路径 | 说明 |
| --- | --- |
| [`halide-mlx-parity-plan-20260531.md`](halide-mlx-parity-plan-20260531.md) | 当前 Halide/MLX 对等计划、基准测试约定、验收标准和自查问题。 [中文](halide-mlx-parity-plan-20260531_zh.md) |
| [`upstream-sync-plan-20260602.md`](upstream-sync-plan-20260602.md) | 当前上游同步计划。 [中文](upstream-sync-plan-20260602_zh.md) |

## HDR、色彩、GPU 与导出

| 路径 | 说明 |
| --- | --- |
| [`color-management-hdr-review-2026-05-31.md`](color-management-hdr-review-2026-05-31.md) | 当前色彩管理/HDR 代码评审、修复说明、验证状态和剩余风险。 [英文](color-management-hdr-review-2026-05-31.en.md) |
| [`hdr_profile_aware_raw_validation.md`](hdr_profile_aware_raw_validation.md) | 用于配置感知 HDR 导出的真实 ProRAW 验证；配套 JSON 文件为 `hdr_profile_aware_raw_validation.json`。 [英文](hdr_profile_aware_raw_validation.en.md) |
| [`film-scan-aware-hdr.md`](film-scan-aware-hdr.md) | 规范的 `film_scan_aware` 正片扫描 HDR 语义、负片原始诊断拆分、采样约定和限制。 |
| [`film-scan-aware-negative-positive-plan.md`](film-scan-aware-negative-positive-plan.md) | 负片原始数据与正片扫描 HDR 路由分离的实施计划。 |
| [`hdr-film-scan-aware.md`](hdr-film-scan-aware.md) | 指向规范胶片扫描感知 HDR 文档的兼容性入口。 [中文](hdr-film-scan-aware_zh.md) |
| [`hdr_exr_output_plan.md`](hdr_exr_output_plan.md) | 用于未裁剪 HDR 存档的场景线性 EXR 导出计划。 [英文](hdr_exr_output_plan.en.md) |
| [`hdr/gain-map-HDR分析报告.md`](hdr/gain-map-HDR分析报告.md) | ISO 21496-1 增益图 HDR 集成分析。 [英文](hdr/gain-map-HDR-analysis-report.en.md) |
| [`hdr/research-gui-color-hdr.md`](hdr/research-gui-color-hdr.md) | GUI 色彩和 HDR 渲染研究。 |
| [`heic-iso21496-compliance.md`](heic-iso21496-compliance.md) | 当前 ISO 21496-1 / HEIC `tmap` 验证器、CoreImage 编码后修复、故障静默导出行为以及 Mac 打开性校验。 |
| [`hdr-export-pipeline.md`](hdr-export-pipeline.md) | 当前 RouteMaster 预渲染 SDR/HDR 对导出边界和 ISO/Mac HEIC 验证合同。 |
| [`hdr-routemaster-rewrite-implementation-report.md`](hdr-routemaster-rewrite-implementation-report.md) | RouteMaster 重写完成报告，包括 SDR 等效性、两种 HDR 模式、成对导出以及 ISO/HEIC 硬化证据。 |
| [`gpu/research-gpu-color-management.md`](gpu/research-gpu-color-management.md) | GPU 加速和色彩管理研究。 [中文](gpu/research-gpu-color-management_zh.md) |
| [`gpu/mlx-optimization-report-20260530.md`](gpu/mlx-optimization-report-20260530.md) | MLX 后端性能优化报告。 [英文](gpu/mlx-optimization-report-20260530.en.md) |
| [`gpu/halide-backend-implementation.md`](gpu/halide-backend-implementation.md) | 已验证的 Halide 后端状态。 [中文](gpu/halide-backend-implementation_zh.md) |
| [`gpu/halide-deep-research.md`](gpu/halide-deep-research.md) | Halide Android 移植的深度研究。 [中文](gpu/halide-deep-research_zh.md) |
| [`architecture/research-memory-management.md`](architecture/research-memory-management.md) | 内存管理和内存泄露检测研究。 [中文](architecture/research-memory-management_zh.md) |
| [`architecture/research-android-app-architecture.md`](architecture/research-android-app-architecture.md) | Android 端口架构研究。 [中文](architecture/research-android-app-architecture_zh.md) |
| [`reports/android-port-status-20260528.md`](reports/android-port-status-20260528.md) | Android 端口状态报告。 [中文](reports/android-port-status-20260528_zh.md) |

## 开发报告与计划

| 路径 | 说明 |
| --- | --- |
| [`reports/public-surface-hygiene-report-20260622.md`](reports/public-surface-hygiene-report-20260622.md) | 仓库公开暴露面整理报告。 |
| [`issue_positive_film_print_exposure.md`](issue_positive_film_print_exposure.md) | 正片打印曝光行为的问题草稿。该缺陷仍存在于 `state.py:342`。 [中文](issue_positive_film_print_exposure_zh.md) |

## 根目录级项目文档

| 路径 | 说明 |
| --- | --- |
| [`../CHANGELOG.md`](../CHANGELOG.md) | 发布和变更历史。 |
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | 贡献工作流程和期望。 |

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
