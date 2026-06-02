> 这是英文原文的中文翻译。权威版本请参考英文原文。

# GUI 研究加固实施

日期：2026-05-27

## 目标

将以下文件中的可操作发现转化为经过测试的 GUI 改进，而不假装更广泛的项目（如真正的 HDR 预览、工作线程取消或撤销功能）可以仅通过表面样式安全解决：

- `docs/archive/docs-2-legacy-20260531/dev/research-gui-product-logic.md`
- `docs/archive/docs-2-legacy-20260531/dev/research-gui-aesthetics.md`
- `docs/archive/docs-2-legacy-20260531/dev/research-gui-color-hdr.md`

实施计划最初编写于
`docs/superpowers/plans/2026-05-27-gui-research-hardening.md`。

## 应用的外部参考

- Qt `QAbstractSlider.tracking`
  (`https://doc.qt.io/qt-6/qabstractslider.html#tracking-prop`)：对昂贵的预览相关滑块禁用跟踪，使提交的值在释放时更改，同时拖动反馈仍可更新本地 UI 标签。
- Qt 无障碍指南 (`https://doc.qt.io/qt-6/accessible.html`)：从可见标签和工具提示/规格描述中分配可访问名称和描述，以便辅助客户端获得有用的控件元数据。
- Qt 样式表参考 (`https://doc.qt.io/qt-6/stylesheet-reference.html`)：
  键盘焦点需要可见状态；全局移除轮廓和边框会使 GUI 更难操作。
- Qt 高 DPI 指南
  (`https://doc.qt.io/qtforpython-6.10/overviews/qtdoc-highdpi.html`)：Qt
  控件已使用与设备无关的坐标，因此手动
  `devicePixelRatioF()` 缩放不是正确的通用 GUI 修复方法。
- Apple HIG 滑块指南
  (`https://developer.apple.com/design/human-interface-guidelines/sliders`)：
  滑块适用于有界的连续值，特别是当快速视觉调优很重要时。

## 已修复的实际问题

### 1. 有界浮点控件仅使用数值调节框

研究要求为预览调优参数提供更具触感的控制。实际代码中已有 `SliderFloatEditor`，但 `DataclassSection` 从未为有界浮点字段选择它。这使得有限范围控件的扫描和调优速度较慢。

已实现：

- `DataclassSection` 现在对具有有限 `minimum`、有限 `maximum`、正 `step` 且最多 256 个滑块步长的浮点字段使用 `SliderFloatEditor`。
- 无界浮点字段仍使用 `FloatEditor`。
- 非常宽的技术保护范围（如 `-100..100` 曝光补偿，`0.25` 步长）仍保留为数值调节框，而不是变成密集滑块。
- `SliderFloatEditor` 禁用滑块跟踪，因此昂贵的自动预览工作不会为每个拖动刻度提交。
- 拖动仍通过 `sliderMoved` 更新本地数字标签。

覆盖范围：

- `tests/gui/test_widgets.py::test_bounded_float_fields_use_slider_editor_and_unbounded_fields_use_spinbox`
- `tests/gui/test_widgets.py::test_slider_float_editor_commits_on_value_changed_but_only_previews_dragged_label`

### 2. 焦点样式被移除

当前主题明确移除了常见控件的边框和轮廓。这使得键盘焦点和活动控件更难看到。

已实现：

- 添加了中性控件边框。
- 添加了悬停边框颜色。
- 使用现有的强调色标记添加了焦点边框颜色。
- 添加了适合现有暗色主题的 QSlider 凹槽、手柄和子页面样式。
- 添加了微妙的状态栏顶部边框。

覆盖范围：

- 由 GUI 导入/布局测试和 `compileall` 覆盖；这是样式契约而非业务逻辑。

### 3. 控件缺少可编程可访问名称

控件规格已有标签和工具提示，但编辑器未接收可编程可访问名称/描述。

已实现：

- `DataclassSection._apply_specs()` 从规格标签或生成的字段标签设置 `accessibleName`。
- `DataclassSection._apply_specs()` 从工具提示设置 `accessibleDescription`。
- `TupleEditor` 和 `SliderFloatEditor` 将可访问名称/描述传播到其子控件。

覆盖范围：

- 现有的 GUI 控件构造测试覆盖了此路径。

### 4. 控件选项卡混合了工作流程阶段和技术分类

旧选项卡为 `MAIN`、`FILM`、`PRINT`、`ADVANCED` 和 `CONFIG`。`MAIN` 混合了导入/加载/裁剪/输出/HDR 关注点，使第一个工作流程屏幕过于宽泛。

已实现：

- 新的工作流程分组：
  - `IMPORT`：文件选择、原始加载、裁剪、输入图像、相机。
  - `FILM`：模拟、曝光、光晕、耦合剂、颗粒。
  - `PRINT`：放大机、扩散、眩光、预闪光、扫描仪。
  - `OUTPUT`：HDR 导出和输出。
  - `ADVANCED`：光谱上采样、调优、特殊选项、相机扩散。
  - `CONFIG`：GUI/显示/Napari 图层控件。
- 模拟操作栏保持固定在选项卡下方。

覆盖范围：

- `tests/gui/test_layout.py::test_build_controls_panel_groups_controls_by_workflow_stage`

### 5. 排队自动预览没有用户可见的状态

当工作线程已活动时请求预览，控制器设置了 `_pending_auto_preview` 但未告知用户工作已排队。

已实现：

- `_run_scheduled_auto_preview()` 现在报告：
  `Preview queued; it will run after the current simulation finishes`。

覆盖范围：

- `tests/gui/test_controller_flow.py::test_request_auto_preview_reports_queued_preview_when_worker_is_active`

### 6. HDR Path-To-White 禁用需要回归测试

生产控制器已将 GUI 开关映射到旧版和配置文件感知的 path-to-white 强度值。无需生产更改，但该行为足够重要需要锁定。

已实现：

- 添加了回归测试，证明禁用 GUI 开关会将
  `path_to_white_strength=0.0` 和
  `profile_path_to_white_strength=0.0` 传递到 `save_hdr_photo_heic()`。

覆盖范围：

- `tests/gui/test_controller_output.py::test_save_output_layer_disables_profile_path_to_white_when_gui_toggle_is_off`

## 明确的非目标

这些项目已考虑但在本次迭代中故意未实现：

- 工作线程取消：Qt `QRunnable` 无法安全地从外部终止。真正的取消功能需要在模拟循环中进行协作取消。
- 撤销：安全的撤销需要信号抑制和状态历史契约。仅按钮的更改将不可靠。
- 真正的 HDR 预览：当前的 Napari/Qt 显示路径不是经过验证的 HDR 呈现表面。导出元数据的正确性与屏幕上的 HDR 呈现是分开的。
- 手动高 DPI 缩放：Qt 已处理与设备无关的坐标。添加手动缩放会有双重缩放的风险。
- 仅 QColorSpace 的 HDR 修复：图像颜色空间标记对资产有用，但它不会使当前查看器成为真正的 HDR 显示管线。

## 已更改的文件

- `src/spektrafilm_gui/widget_sections.py`
- `src/spektrafilm_gui/widget_editors.py`
- `src/spektrafilm_gui/theme_palette.py`
- `src/spektrafilm_gui/theme_styles.py`
- `src/spektrafilm_gui/napari_layout.py`
- `src/spektrafilm_gui/controller.py`
- `tests/gui/test_widgets.py`
- `tests/gui/test_layout.py`
- `tests/gui/test_controller_flow.py`
- `tests/gui/test_controller_output.py`
- `tests/gui/test_controller_runtime_module.py`
- `docs/superpowers/plans/2026-05-27-gui-research-hardening.md`
- `docs/dev/gui-research-hardening-implementation.md`

## 验证

运行的命令：

```bash
.venv/bin/python -m pytest -q tests/gui
.venv/bin/python -m pytest --ignore=tests/gui -q
.venv/bin/python -m compileall -q src/spektrafilm src/spektrafilm_gui tests
git diff --check
```

结果：

- `tests/gui`：186 通过。
- 非 GUI 套件：549 通过，6 跳过，13 警告。
- `compileall`：通过。
- `git diff --check`：通过。

非 GUI 警告是现有的数值/弃用警告，不是由 GUI 更改引入的。

## 置信度检查

完成前的自审结果：

- 每个已实现的 GUI 行为都有专注的覆盖范围或由现有的构造/导入测试覆盖。
- 现有的 SDR/HDR 导出行为未被扩大或重新路由。
- 未添加虚假取消、虚假撤销或虚假 HDR 预览。
- GUI 选项卡分组现在遵循用户工作流程，而不是将所有控件作为技术分类公开。
- 完整的 GUI 和非 GUI 测试套件在当前工作区状态下通过。
