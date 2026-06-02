> 这是英文原文的中文翻译。权威版本请参考英文原文。

# ACES 色彩管理实施计划

> **面向智能体工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 来逐任务实施此计划。步骤使用复选框（`- [ ]`）语法进行跟踪。

**目标：** 添加一个显式的 ACES 参考色彩管理工作流，使用 ACEScg 作为场景线性工作空间，ACES2065-1 作为场景线性交换/导出空间，并在未选择该工作流时保留现有的 SDR/sRGB 行为。

**架构：** 保留现有的 `ColorEncoding` 契约作为权威的底层表示。在 `spektrafilm.color_management` 中添加更高层级的 `ColorManagementWorkflow` 预设层，通过运行时参数和 GUI 暴露它，并让映射器在构建 `IOParams` 之前应用预设。预设不得替换逐文件的 ICC/EXR 元数据检测；已加载文件的元数据在输入解释中仍然优先。

**技术栈：** Python 3.13、dataclasses、colour-science、OpenImageIO、Pillow/ImageCms、napari/Qt widgets、pytest。

---

## 证据与项目分析

本设计所参考的官方 ACES 指南：

- ACEScg 是用于 CGI/渲染/合成的 AP1 场景线性工作空间；它以浮点数存储，允许负值，且高于 1.0 的值不应作为正常处理步骤被钳位。
- ACES2065-1 是 AP0 场景线性核心/交换空间，是唯一的 ACES 交换格式。
- ACES 2 增加了改进的输出/渲染变换，但本项目目前不依赖 OCIO/OpenColorIO。添加 OCIO 依赖将超出所请求的支持范围，且对确定性的首次实现而言是不必要的。
- ASWF OpenColorIO-Config-ACES 仓库提供了生成的 ACES 配置，但其自身文档将配置生成定位为独立的包/工具关注点。Spektrafilm 已有 `colour-science` 矩阵和捆绑的 ICC/EXR 元数据支持，因此最佳的首次实现是使用这些现有原语的内部 ACES 工作流预设。

本地项目发现：

- `src/spektrafilm/color_management.py` 已定义了 `ColorEncoding`、ACES 色彩空间常量以及 ACES 空间的场景线性未钳位行为。
- `src/spektrafilm/runtime/params_schema.py` 拥有用于输入/输出色彩空间和裁剪标志的 `IOParams`，但没有高层级的工作流/预设字段。
- `src/spektrafilm_gui/state.py`、`src/spektrafilm_gui/options.py`、`src/spektrafilm_gui/params_mapper.py` 和 `src/spektrafilm_gui/widget_sections.py` 暴露了单独的输入/输出/保存控件，但用户必须手动正确组合它们。
- `src/spektrafilm/utils/raw_file_processor.py` 已通过线性 ACES2065-1 对 RAW 进行去马赛克，并可转换为 ACEScg。新工作流应在选择后使 ACEScg 成为默认的 RAW 目标。
- `src/spektrafilm/utils/io.py` 已能为非 EXR 格式读写 ACES EXR 色度坐标和 ACES ICC 配置文件。工作流应利用这些能力而非添加 OCIO。
- `src/spektrafilm_gui/controller.py` 根据记录的图层元数据保存输出。工作流必须保留该行为，仅更改预期的默认保存目标/编码。

## 设计

添加两种工作流模式：

- `manual`：当前行为。现有的单独输入/输出/保存控件仍具权威性。
- `aces_reference`：ACES 最佳实践模式。运行时输入首先从其标记的源空间转换为场景线性 ACEScg，运行时输出为场景线性 ACEScg，保存交换默认为场景线性 ACES2065-1，CCTF 被禁用，对于 ACES 运行时输出禁用负值和高光裁剪。

该工作流是有意保守的：

- 它尚未添加 OCIO 或 ACES 输出变换。GUI 预览仍使用现有的色度 sRGB/显示配置文件预览路径。
- 它不会静默地重新解释非 ACES 文件。加载文件时，现有文件元数据检测仍会更新输入控件。
- 它不会强制 PNG/JPEG 保存为线性 ACES。现有保存守卫仍会拒绝线性 PNG/JPEG 并引导用户使用 EXR 来存储场景线性 ACES。
- *（2026-05-25 备注：HDR 导出管线已升级为具有 RGB 增益图的双层 HDR 映射。ACES 工作流与该扩展 HDR 编码完全兼容。）*

## 文件

- 修改 `src/spektrafilm/color_management.py`：添加工作流枚举常量和 `apply_color_management_workflow_to_io`。
- 修改 `src/spektrafilm/runtime/params_schema.py`：添加 `SettingsParams.color_management_workflow`。
- 修改 `src/spektrafilm_gui/options.py`：暴露 `ColorManagementWorkflows`。
- 修改 `src/spektrafilm_gui/state.py`：添加 `SimulationState.color_management_workflow`，通过默认值持久化。
- 修改 `src/spektrafilm_gui/params_mapper.py`：映射工作流并将工作流预设应用到 IO。
- 修改 `src/spektrafilm_gui/widget_specs.py`：添加 GUI 枚举/规格文本。
- 修改 `src/spektrafilm_gui/widget_sections.py`：在输出部分显示工作流选择器。
- 修改 `src/spektrafilm_gui/controller_profile_sync.py`：在配置文件默认同步中保留工作流。
- 修改 `README.md`：记录 ACES 工作流行为和限制。
- 在 `tests/test_color_management.py`、`tests/gui/test_params_mapper.py`、`tests/gui/test_persistence.py` 和 `tests/gui/test_controller_output.py` 中添加或更新测试。

## 任务

### 任务 1：色彩管理工作流契约

**文件：**
- 修改：`src/spektrafilm/color_management.py`
- 测试：`tests/test_color_management.py`

- [ ] 为 `apply_color_management_workflow_to_io` 编写失败测试：
  - `manual` 保持 `IOParams` 不变。
  - `aces_reference` 将输入/输出设为 ACEScg，关闭输出 CCTF，关闭输出裁剪最小/最大值，并通过辅助函数返回值将默认保存意图设为 ACES2065-1。
  - 未知工作流引发 `ValueError`。
- [ ] 运行 `.venv/bin/python -m pytest tests/test_color_management.py -q` 并确认新测试因辅助函数不存在而失败。
- [ ] 实现 `ColorManagementWorkflow = Literal["manual", "aces_reference"]`、常量和 `apply_color_management_workflow_to_io(io, workflow)`。
- [ ] 运行 `.venv/bin/python -m pytest tests/test_color_management.py -q` 并确认测试通过。

### 任务 2：运行时和 GUI 状态映射

**文件：**
- 修改：`src/spektrafilm/runtime/params_schema.py`
- 修改：`src/spektrafilm_gui/options.py`
- 修改：`src/spektrafilm_gui/state.py`
- 修改：`src/spektrafilm_gui/params_mapper.py`
- 测试：`tests/gui/test_params_mapper.py`
- 测试：`tests/gui/test_persistence.py`

- [ ] 编写失败的 GUI 映射器测试，展示 `color_management_workflow="aces_reference"` 将运行时设置和 IO 映射到 ACES 参考契约。
- [ ] 编写持久化测试，展示缺少 `color_management_workflow` 的旧版保存 GUI 状态 JSON 以 `manual` 加载。
- [ ] 运行 `.venv/bin/python -m pytest tests/gui/test_params_mapper.py tests/gui/test_persistence.py -q` 并确认新测试因缺少字段/枚举/辅助函数行为而失败。
- [ ] 添加 `SettingsParams.color_management_workflow = "manual"`。
- [ ] 添加包含 `manual` 和 `aces_reference` 的 `ColorManagementWorkflows` 枚举。
- [ ] 添加默认为 `manual` 的 `SimulationState.color_management_workflow`。
- [ ] 将状态值映射到运行时设置，并在普通 IO 映射之后调用工作流辅助函数。
- [ ] 运行 `.venv/bin/python -m pytest tests/gui/test_params_mapper.py tests/gui/test_persistence.py -q` 并确认测试通过。

### 任务 3：GUI 暴露和保存语义

**文件：**
- 修改：`src/spektrafilm_gui/widget_specs.py`
- 修改：`src/spektrafilm_gui/widget_sections.py`
- 修改：`src/spektrafilm_gui/controller_profile_sync.py`
- 测试：`tests/gui/test_controller_output.py`
- 测试：`tests/gui/test_app.py`

- [ ] 编写失败的测试，验证输出部分暴露 `color_management_workflow` 且应用信号连接包含工作流更改的预览刷新。
- [ ] 编写或调整保存测试，使 ACES 参考状态保存为 `.exr` 时使用 ACES2065-1 线性编码且不进行 CCTF 编码。
- [ ] 运行 `.venv/bin/python -m pytest tests/gui/test_controller_output.py tests/gui/test_app.py -q` 并确认新测试失败。
- [ ] 添加工作流枚举注册和工具提示。
- [ ] 将工作流选择器放置在输出部分顶部。
- [ ] 在配置文件同步字段中保留工作流，使胶片/打印配置文件更改不会静默重置它。
- [ ] 在 `app.py` 中将工作流更改连接到预览刷新。
- [ ] 运行 `.venv/bin/python -m pytest tests/gui/test_controller_output.py tests/gui/test_app.py -q` 并确认测试通过。

### 任务 4：文档和回归检查

**文件：**
- 修改：`README.md`

- [ ] 在 GUI 部分和色彩管理路线图部分记录 ACES 参考工作流。
- [ ] 运行目标测试：
  - `.venv/bin/python -m pytest tests/test_color_management.py tests/gui/test_params_mapper.py tests/gui/test_persistence.py tests/gui/test_controller_output.py tests/gui/test_app.py -q`
- [ ] 运行广泛的色彩/运行时健全性检查：
  - `.venv/bin/python -m pytest tests/test_image_io_color_metadata.py tests/test_raw_file_processor.py tests/test_gpu_color_chain.py tests/test_pipeline_smoke.py -q`
- [ ] 运行语法检查：
  - `python3 -m compileall -q src/spektrafilm src/spektrafilm_gui tests`
- [ ] 对照 ACES 事实和项目约束进行自查：
  - ACEScg 是运行时工作空间。
  - ACES2065-1 是交换保存默认值。
  - 线性 ACES 值未被钳位。
  - 现有手动模式保持不变。
  - GPU 和 HDR 行为未被禁用。

## 信心循环

在完成之前，询问："我是否有 100% 的事实信心认为此实现满足目标？"如果没有，检查每个剩余风险：

- 工作流字段存在于状态中但未被持久化或默认值不正确。
- GUI 更改未触发预览刷新。
- 保存路径使用过时的源编码进行转换。
- 线性 ACES 意外经过 PNG/JPEG。
- ACES 参考模式破坏了现有的手动模式测试。
- 现有的脏 GPU/HDR 更改被意外回退。

重复修复和验证，直到证据是当前且直接的。
