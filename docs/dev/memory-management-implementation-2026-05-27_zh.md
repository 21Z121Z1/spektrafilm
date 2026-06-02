> 这是英文原文的中文翻译。权威版本请参考英文原文。

# 内存管理实现说明

日期：2026-05-27

## 范围

本实现针对在审查以下内容后确认的当前 Spektrafilm 运行时和 GUI 路径中的实际内存管理问题：

- `docs/archive/docs-2-legacy-20260531/dev/research-memory-management.md`
- `docs/archive/docs-2-legacy-20260531/dev/research-memory-optimization-patterns.md`
- 当前 `src/spektrafilm/runtime`、`src/spektrafilm/gpu` 和
  `src/spektrafilm_gui` 调用点

本次变更有意不实现大范围的流水线缓冲区复用、memmap I/O 或阶段融合。这些属于更大的架构变更，且并非移除在实际代码中发现的已确认的附带数据和 GPU 缓存压力所必需的。

## 已确认的问题

### 1. GUI 运行时默认收集 HDR 附带数据

`GuiController._process_image_with_runtime()` 在模拟器暴露该方法时使用了 `process_with_metadata()`。这使得正常的预览和扫描运行需要承担全帧 HDR 元数据的开销，即使输出路径只需要一个数组。

对于 6000 x 4000 的图像，一个 float32 RGB 附带数据大约为 275 MiB：

```text
6000 * 4000 * 3 * 4 bytes = 274.7 MiB
```

之前的默认路径可能会在输出层上同时保持 `scene_luminance` 和 `scene_rgb` 附带数据，加上配置文件特征化的工作。

### 2. `scene_rgb` 虽然是可选的但仍被计算

`HDRSceneEnergyMetadata.scene_rgb` 已经是可选的。当前 HDR 照片路径仅在源色度高光恢复时需要它。正常的 HDR 映射路径可以使用 `scene_luminance` 和标量元数据，而无需 RGB 附带数据。

### 3. GPU 后端缓存没有顶层清理钩子

CuPy 和 MLX 后端暴露了同步机制但没有运行时级清理。这导致在顶层流水线运行后，已释放的 GPU 内存池块和 MLX 缓存条目仍然存在。

## 已实现的契约

### GUI 运行时请求

`SimulationRequest` 现在携带显式的收集标志：

```python
collect_hdr_scene_energy: bool = False
collect_hdr_scene_rgb: bool = False
```

正常预览和扫描使用 `Simulator.process()`。GUI 仅在启用 HDR 输出时才请求 `process_with_metadata()`。

`collect_hdr_scene_rgb` 仅在请求 HDR 元数据且 HDR 导出状态显式要求以下内容时才启用：

```python
hdr_highlight_color_mode == "source_chroma"
```

### 运行时元数据

`SimulationPipeline.process_with_metadata()` 和
`Simulator.process_with_metadata()` 现在接受：

```python
include_scene_rgb: bool = False
```

默认情况下，元数据收集仍然记录：

- `scene_luminance`
- 漫反射白点估计
- 动态范围余量估计
- 自动曝光 EV
- 配置文件场景/外观曲线

除非调用方显式请求，否则不会分配 `scene_rgb`。

### 后端清理

所有数组后端现在都暴露 `cleanup()` 方法。

`SimulationPipeline.process()` 和 `SimulationPipeline.process_with_metadata()`
在物化结果并记录耗时后，在 `finally` 块中调用后端清理。

后端行为：

- NumPy：无操作。
- CuPy：同步后释放默认和固定内存池的空闲块。
- MLX：同步后调用 `mx.clear_cache()`（如果存在），对于旧版安装则回退到
  `mx.metal.clear_cache()`。

## 基于调研的决策

研究笔记提到了内存限制和池管理。当前上游文档促成了以下实现选择：

- CuPy 内存池有意保留已释放的块；`free_all_blocks()` 是释放池中空闲块的正确显式钩子。
- MLX 内存限制使用字节计数。未实现分数形式的示例（如 `set_memory_limit(0.8)`），因为它们与当前 API 契约不匹配。
- NumPy 原地操作和 `out=` 模式仍然有效，但将光谱流水线更改为缓冲区复用是单独的架构工作。本次修改仅更改已确认存在浪费的路径并添加直接测试。

## 验证结果

目标回归测试：

```bash
.venv/bin/python -m pytest tests/test_runtime_api.py::TestRuntimeApi::test_hdr_scene_energy_metadata_omits_scene_rgb_by_default tests/test_runtime_api.py::TestRuntimeApi::test_hdr_scene_energy_metadata_can_include_scene_rgb tests/test_runtime_api.py::TestRuntimeApi::test_simulator_process_with_metadata_forwards_scene_rgb_flag tests/test_runtime_api.py::TestRuntimeApi::test_pipeline_process_cleans_up_gpu_backend_after_materialization tests/test_gpu_backend.py::test_mlx_backend_cleanup_clears_cache_after_synchronize tests/test_gpu_backend.py::test_cupy_backend_cleanup_releases_default_memory_pools tests/gui/test_controller_runtime_module.py::test_execute_simulation_request_passes_hdr_collection_flags tests/gui/test_controller_flow.py::test_process_image_with_runtime_uses_process_for_sdr_output_by_default tests/gui/test_controller_flow.py::test_process_image_with_runtime_collects_metadata_when_requested -q
```

结果：9 项通过。

相关运行时/GPU/GUI 测试套件：

```bash
.venv/bin/python -m pytest tests/test_runtime_api.py tests/test_gpu_backend.py tests/gui/test_controller_runtime_module.py tests/gui/test_controller_flow.py tests/gui/test_controller_output.py -q
```

结果：123 项通过。

完整测试套件：

```bash
.venv/bin/python -m pytest -q
```

结果：734 项通过，6 项跳过。

语法和空白检查：

```bash
.venv/bin/python -m compileall src tests
git diff --check
```

结果：两项均通过。
