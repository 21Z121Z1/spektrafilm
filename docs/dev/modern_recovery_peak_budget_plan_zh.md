> 这是英文原文的中文翻译。权威版本请参考英文原文。

# Modern Recovery Peak Budget 实现计划

> **致智能体工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐步实现本计划。步骤使用复选框（`- [ ]`）语法进行跟踪。

**目标：** 添加并验证一个名为 `modern_recovery_peak_budget` 的保留配置文件的 HDR 模式，该模式恢复肩部压缩的高光 EV，同时强制执行固定的配置文件相对 EV 峰值预算，且不改变现有的 SDR 渲染行为。

**架构：** 保持 SDR 和传统配置文件曲线语义不变。新模式位于 `HDRPhotoMapping.profile_hdr_mode` 之后，仅由保留配置文件的曲线路径使用；`profile_curve_mode="legacy_graft"` 会忽略它。增益图/动态范围元数据仍通过 `_content_headroom()` 从内容派生，而非从目标 EV 预算写入。

**技术栈：** Python 3.13、NumPy、dataclasses、现有 Spektrafilm HDR 照片工具、PySide GUI 状态/部件管道、`uv run --extra dev pytest`。

---

## 发现的当前代码路径

- `src/spektrafilm/utils/hdr_curve_profiles.py`
  - `ProfilePreservingHDRCurveResult` 是严格保留的诊断返回类型。
  - `ProfileHDRCurveResult`、`budget_recovery_gain_ev()` 和 `profile_modern_recovery_budgeted_gain_ev()` 已存在，但需要根据请求的 API 和诊断完成。
  - `build_profile_preserving_hdr_curve()` 已根据 `mapping.profile_hdr_mode` 分支；严格保留仍是默认分支，当请求诊断时返回 `ProfilePreservingHDRCurveResult`。
  - 现代分支计算 `h = s_profile * 2**gain_ev` 并返回 `ProfileHDRCurveResult`，但预算辅助函数尚不支持 `active_mask`，未报告所有请求的预算元数据，且硬限制行为当前改变了直接辅助函数测试的"仅缩放增益"不变量。
- `src/spektrafilm/utils/hdr_photo.py`
  - `HDRPhotoMapping` 已包含 `profile_hdr_mode`、`profile_hdr_target_peak_ev`、`profile_hdr_normalize_percentile`、`profile_hdr_budget_hard_cap`、`profile_hdr_recovery_ratio`、`profile_hdr_recovery_knee_ev` 和 `profile_hdr_recovery_full_ev`。
  - 验证覆盖模式、目标峰值和恢复比率，但仍需要百分位数、硬限制布尔兼容性和有序恢复拐点/完整验证。
  - `_prepare_profile_aware_renditions()` 已通过共享字段 `s_profile`、`h_profile` 和 `look_white` 接受任一诊断类型。
  - `build_hdr_debug_sidecar()` 已检测 `ProfileHDRCurveResult` 并包含现代诊断，但应根据请求的名称和统计进行检查。
  - `_content_headroom()` 仍是 HEIC 负载导出使用的内容派生动态范围路径；目标 EV 预算不得复制到 GainMax/动态范围中。
- GUI 文件
  - `src/spektrafilm_gui/state.py` 已在 `HdrExportState` 和默认构造上包含 `profile_hdr_mode`、`profile_hdr_target_peak_ev` 和 `profile_hdr_recovery_ratio`。
  - `src/spektrafilm_gui/options.py` 已有 `ProfileHDRModes`。
  - `src/spektrafilm_gui/widget_specs.py` 已注册 `profile_hdr_mode` 以及目标 EV 和恢复比率的部件规格。
  - `src/spektrafilm_gui/widget_sections.py` 在 `HdrExportSection._sync_mode()` 中启用/禁用新控件，但不隐藏/显示行。
  - `src/spektrafilm_gui/controller.py` 已将三个 GUI 暴露的现代字段传入 `hdr_mapping_kwargs`。
- 测试
  - 初始命令：`uv run --extra dev pytest tests/test_hdr_curve_profiles.py tests/test_hdr_photo.py -v`。
  - 编辑前基线：64 通过，9 失败。
  - 现代相关失败：`test_budget_scales_gain_not_profile_ev`、`test_modern_recovery_uses_compressed_ev` 和 `test_gain_map_max_matches_actual_h_over_s`。
  - 现有基线/过期测试失败也出现在通用 SDR 基础测试和不安全配置文件回退预期中。除非当前代码已有意图，否则不得通过更改 SDR 行为来修复这些问题。

## 需要更改的确切文件

- 修改 `src/spektrafilm/utils/hdr_curve_profiles.py`
  - 使用 `active_mask`、请求的诊断键、有限/百分位保护、保留基线的有效目标逻辑以及仅缩放 `raw_gain_ev` 的预算缩放来完成 `budget_recovery_gain_ev()`。
  - 确保现代诊断在辅助函数级别和 `ProfileHDRCurveResult` 中包含 `raw_h_ev` 和 `final_h_ev`。
  - 防御性拒绝未知的 `profile_hdr_mode`。
  - 保留严格保留分支和默认值。
- 修改 `src/spektrafilm/utils/hdr_photo.py`
  - 完成 `HDRPhotoMapping` 对现代字段的验证。
  - 保持 `_prepare_profile_aware_renditions()` 使用共享结果字段。
  - 保持 HEIC 动态范围基于 `_content_headroom(hdr_rgb, percentile=...)`。
  - 仅在不改变现有行为的情况下，为预写的 GainMapMax 测试添加所需的最小兼容性。
- 仅在检查或测试显示差距时修改 GUI 文件：
  - `src/spektrafilm_gui/state.py`
  - `src/spektrafilm_gui/options.py`
  - `src/spektrafilm_gui/widget_specs.py`
  - `src/spektrafilm_gui/widget_sections.py`
  - `src/spektrafilm_gui/controller.py`
  - `src/spektrafilm_gui/controller.py`
- 仅在调用不存在的 API 或断言过期 SDR 行为时修改 `tests/test_hdr_curve_profiles.py` 和 `tests/test_hdr_photo.py` 以修复格式错误/过期的测试。

## 预期返回类型和诊断

- 严格保留：
  - `build_profile_preserving_hdr_curve(..., return_diagnostics=False)` 返回 `np.ndarray`。
  - `build_profile_preserving_hdr_curve(..., return_diagnostics=True)` 返回 `ProfilePreservingHDRCurveResult`。
  - 字段保持不变：`s_profile`、`h_profile`、`gain_ev`、`slope`、`diffuse_white`、`look_white`、`visual_peak`。
- 现代恢复：
  - `profile_modern_recovery_budgeted_gain_ev(..., return_diagnostics=False)` 返回 `np.ndarray`。
  - `profile_modern_recovery_budgeted_gain_ev(..., return_diagnostics=True)` 返回包含 `gain_ev`、`raw_gain_ev`、`slope`、`scene_ev`、`profile_ev`、`raw_h_ev`、`final_h_ev`、`compressed_ev`、`target_peak_ev`、`effective_target_peak_ev`、`raw_peak_ev_before_budget`、`actual_peak_ev_after_budget`、`budget_scale`、`budget_was_applied`、`normalize_percentile` 和 `hard_cap` 的字典。
  - `build_profile_preserving_hdr_curve(..., modern mode, return_diagnostics=True)` 返回 `ProfileHDRCurveResult`。

## 实现任务

- [x] 检查命名的文件和测试。
- [x] 在生产编辑前运行聚焦测试并记录基线失败。
- [x] 在代码编辑前编写此计划文档。
- [x] 修补 `budget_recovery_gain_ev()` 以使直接辅助函数测试通过并呈现请求的诊断。
- [x] 修补 `profile_modern_recovery_budgeted_gain_ev()` 诊断和形状处理。
- [x] 修补 `build_profile_preserving_hdr_curve()` 以进行未知模式验证和单调/最小增益约束后正确的现代最终诊断。
- [x] 修补 `HDRPhotoMapping` 验证以覆盖剩余现代字段。
- [x] 仅在调用不存在的 API 或断言过期 SDR 行为时修复或适配格式错误的预写测试。
- [x] 运行聚焦 HDR 测试和任何相关 GUI 测试。
- [x] 运行 `git diff --check`。
- [x] 手动检查最终差异，查看 SDR 行为更改、动态范围误用、GUI 状态传播、验证差距和无关文件。
- [x] 使用完成的更改、验证结果和限制更新此文档。

## 风险和缓解措施

- 风险：为满足过期 SDR 测试而意外更改已编写的 SDR 行为。
  - 缓解：除非当前代码和硬约束都要求，否则不要更改 `preserve_sdr_base=True` 行为或通用 SDR 输出代码；优先修复过期断言的测试。
- 风险：将 `profile_hdr_target_peak_ev` 视为 HEIC GainMapMax/动态范围。
  - 缓解：让 `HDRPhotoRenditions.headroom` 通过 `_content_headroom()` 从实际 `hdr_rgb` 内容派生。
- 风险：现代预算钳制配置文件基线而非仅缩放恢复增益。
  - 缓解：计算 `effective_target_peak_ev = max(target_peak_ev, percentile(p_ev))`，仅对原始增益缩放进行二分搜索，并仅以零为下限钳制增益。
- 风险：严格保留回归。
  - 缓解：保持其代码路径和结果数据类不变，然后运行现有严格配置文件保留测试。

## 验证命令

- `uv run --extra dev pytest tests/test_hdr_curve_profiles.py tests/test_hdr_photo.py -v`
- `uv run --extra dev pytest tests/gui -q`（如果 GUI 测试依赖可用且控制器/部件更改已涉及）
- `git diff --check`

## 完成的更改

- `budget_recovery_gain_ev()` 现在：
  - 接受 `active_mask`；
  - 验证目标 EV 和百分位数；
  - 使用保守的高百分位方法测量预算百分位数；
  - 仅将有效目标提升到测量的配置文件基线峰值；
  - 二分搜索仅缩放 `raw_gain_ev` 的缩放；
  - 报告 `target_peak_ev`、`effective_target_peak_ev`、`normalize_percentile`、`hard_cap`、`active_sample_count`、`raw_h_ev` 和 `final_h_ev`。
- `profile_modern_recovery_budgeted_gain_ev()` 现在使用仅关键字目标转发预算并暴露 `raw_h_ev` / `final_h_ev` 诊断。
- `build_profile_preserving_hdr_curve()` 现在防御性拒绝未知的 `profile_hdr_mode` 值，并使用预算辅助函数的原始 H EV 诊断返回现代诊断。
- `HDRPhotoMapping` 现在验证现代百分位数、硬限制布尔兼容性、非负恢复比率和有序恢复拐点/完整 EV 值。
- 配置文件感知 HEIC 动态范围现在包含来自 `h_profile / s_profile` 的真实内容派生配置文件增益动态范围，而非使用 `profile_hdr_target_peak_ev` 作为元数据。
- `HdrExportSection._sync_mode()` 现在在 HDR 映射不是 `profile_aware` 时禁用并隐藏现代配置文件控件。
- 测试仅在预写断言过期或格式错误时进行调整：
  - 默认 SDR 基础测试现在断言已编写的 SDR 保留；
  - 色调映射特定测试选择 `preserve_sdr_base=False`；
  - 现代恢复配置文件夹具使用匹配的样本长度；
  - GainMapMax 测试使用当前 `HDRPhotoMapping` / `prepare_hdr_photo_renditions()` API。

## 验证结果

- 编辑前的初始失败运行：
  - `uv run --extra dev pytest tests/test_hdr_curve_profiles.py tests/test_hdr_photo.py -v`
  - 结果：64 通过，9 失败。
- 实现后的聚焦 HDR 验证：
  - `.venv/bin/pytest tests/test_hdr_curve_profiles.py tests/test_hdr_photo.py -v`
  - 结果：73 通过，耗时 0.60 秒。
- 轻量级 GUI 部件验证：
  - `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/gui/test_widgets.py -q`
  - 结果：12 通过，耗时 2.41 秒。
- 作用域语法验证：
  - `.venv/bin/python -m py_compile src/spektrafilm/utils/hdr_curve_profiles.py src/spektrafilm/utils/hdr_photo.py src/spektrafilm_gui/widget_sections.py tests/test_hdr_curve_profiles.py tests/test_hdr_photo.py`
  - 结果：通过。
- 更广泛的 GUI/控制器验证：
  - `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/gui/test_controller_output.py::test_save_output_layer_heic_passes_profile_aware_film_paper -vv`
  - 结果：Python 进程在运行 `GuiController.save_output_layer()` 时在 PySide/Qt 内部中止。
- `uv` 重建/同步后的最终收集：
  - `.venv/bin/pytest tests/test_hdr_curve_profiles.py tests/test_hdr_photo.py -v`
  - 结果：在 `tests/conftest.py` 导入期间被 `src/spektrafilm/color_management.py` 中无关的未解决合并标记阻塞。
- `git diff --check`：
  - 结果：在包括 `README.md`、`src/spektrafilm/color_management.py`、运行时/GUI 合并冲突文件和颜色管理测试在内的无关未解决合并标记上失败。使用 `rg` 检查的聚焦 HDR 文件不包含冲突标记。

## 已知限制和当前阻塞

- 工作树当前在无关文件中包含未解决的合并冲突标记。它们阻塞了正常的 pytest 收集和 `git diff --check`，但此处未解决以保持此功能的作用域。
- `uv run` 在验证期间重建/同步了本地环境，并似乎刷新了工作树的部分内容；此后，直接 `.venv/bin/pytest` 成为更安全的验证路径。
- `src/spektrafilm_gui/controller.py` 和 `src/spektrafilm_gui/state.py` 当前在狭窄的现代 HDR 行之外有未解决的冲突标记。所需的现代 HDR 字段/kwargs 已存在，但在解决这些更广泛的冲突之前，这些文件不能被视为完全验证。
