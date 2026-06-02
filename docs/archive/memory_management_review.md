# SpektraFilm 内存管理系统审查报告

审查日期：2026-05-16
基于外部 Code Review 报告的实施与补充审查。

## 概要

基于一份全面的内存管理系统 Code Review，本报告记录了对当前代码库的实际验证结果和已完成的修复。

## 调研发现：Code Review 与代码现实的差异

> **重要发现**：Code Review 中有多个问题引用了当前代码库中**不存在**的代码路径。

| Code Review 引用 | 代码库实际状态 |
|:---|:---|
| `MlxBackend` / `mlx_backend.py` | 不存在。`src/spektrafilm/gpu/kernels/` 仅有空的 `__pycache__` |
| `serialized_metal_runtime()` | 不存在 |
| `SPEKTRAFILM_MLX_TILE_PIXELS` / `_tile_core_rows()` | 不存在。`pipeline.py` 仅 221 行，无分块逻辑 |
| `gpu_precision` / `gpu_backend` in `SettingsParams` | 不存在。项目当前为纯 CPU 实现 |
| `mx.clear_cache()` / Metal cache 生命周期 | 无 MLX 依赖 |

这些差异可能因为：
1. Code Review 基于的是一个包含未提交 GPU 分支代码的快照
2. 或 GPU 后端处于计划/设计阶段但尚未进入工作树

## 已完成的修复

### P0：SpectralLUTService 生命周期（已修复）

**Bug**：`SimulationPipeline.__init__()` 在 `update_params=True` 时完全跳过 `SpectralLUTService` 重建。用户通过 GUI 修改 `lut_resolution` 后，旧 service 的 `_lut_resolution` 不更新，LUT 以旧分辨率计算。

**修复**：
- 移除 `update_params` 布尔标志
- 改为通过 `_reused_lut_service` 关键字参数传递旧实例
- 按 `lut_resolution` 判断是否复用：相同则复用（保留缓存），不同则重建
- 给 `SpectralLUTService` 增加 `lut_resolution` 只读属性供 pipeline 做 cache key 比较

**测试验证**：3 个专项测试通过
- `test_pipeline_update_rebuilds_lut_service_on_resolution_change`
- `test_pipeline_update_reuses_lut_service_when_resolution_unchanged`
- `test_pipeline_update_does_not_reuse_lut_service_when_resolution_differs`

### P2：SpectralLUTService 缓存管理 API（已完成）

新增方法：
- `clear()`：显式释放所有缓存数组和关联状态
- `memory_info()`：返回各缓存字段的近似字节数
- `timings` 中记录 enlarger/scanner LUT 的 `cache hit/miss`

**测试验证**：
- `test_clear_releases_all_cached_fields`
- `test_memory_info_reports_zero_when_caches_empty`
- `test_memory_info_reports_nonzero_after_caching`

### P2：Watermark LRU cache 上限（已修复）

**修改**：`_build_watermark_image` 的 `@lru_cache(maxsize=32)` 降至 `maxsize=4`。

**影响估算**：按 RGBA float32、长边 1024 px 计算，每个 watermark ≈ 4 MB。32 → 4 减少最多 ~112 MB 缓存上限。

### P2：GUI output 层 metadata 释放（已修复）

**修改**：在 `ViewerLayerService.hide_layer()` 和 `remove_layer()` 中，当目标为 output layer 时自动清理 `metadata` 中的大型 float32 数组。

新增 `_clear_output_layer_large_metadata()` 方法，在 output layer 被隐藏或移除时调用。

## 未来 GPU 集成的设计指导

以下内容来自 Code Review，虽不适用于当前代码，但在未来引入 MLX/Metal GPU 后端时应遵循：

### MLX tile budget

- `SPEKTRAFILM_MLX_TILE_PIXELS` 应约束含 overlap 的实际 tile 输入大小，而非仅 core rows
- 当 `max_input_rows <= 2 * overlap` 时应禁用分块或发出 warning
- 需要单元测试覆盖大 overlap 场景

### MLX/Metal cache 生命周期

- 不应每个 tile 后清 cache（破坏性能）
- 建议在以下时机清理：simulator 重建、backend 切换、处理完成后超阈值、测试/benchmark 之间
- `MlxBackend` 应提供 `memory_stats()`、`clear_cache()`、`reset_peak_memory()` 方法

### GPU backend 与 LUT service 联动

- 当 backend 在 CPU ↔ MLX 之间切换时，LUT service 的 cache key 应包含 backend kind
- 已实现的 `lut_resolution` cache key 机制可直接扩展加入 backend kind

## 预先存在的测试失败

完整测试套件中有 14 个预先存在的失败，**不是本次修改引入**的：
- `test_couplers.py`：2 个（dir coupler 管线匹配）
- `test_filming_stage.py`：1 个（bandpass hanatos）
- `test_profiles.py`：5 个（profile schema/round-trip）
- `test_regression_baselines.py`：5 个（pipeline 回归基线）
- `test_pipeline_lut_lifecycle.py`：基线 0 失败（新增 8 个全部通过）

## 修改文件清单

| 文件 | 变更类型 | 说明 |
|:---|:---|:---|
| `src/spektrafilm/runtime/pipeline.py` | 修改 | P0: 移除 `update_params` 标志，改为 cache key 复用 |
| `src/spektrafilm/runtime/services/spectral_lut_compute.py` | 修改 | P2: 增加 `lut_resolution` 属性、`clear()`、`memory_info()` |
| `src/spektrafilm_gui/controller_layers.py` | 修改 | P2: watermark maxsize 32→4，output layer metadata 释放 |
| `tests/test_pipeline_lut_lifecycle.py` | 新增 | 8 个测试覆盖 LUT lifecycle 和 pipeline update 行为 |
| `docs/memory_management_review.md` | 新增 | 本文档 |
