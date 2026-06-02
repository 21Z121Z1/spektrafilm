> 这是英文原文的中文翻译。权威版本请参考英文原文。

# 全工作区代码审查 - Spektrafilm - 2026-05-26

审查目标：对 Spektrafilm 仓库状态进行只读的全工作区审查，特别关注 SDR 保留、感知配置文件的 HDR 导出、颜色管理、GPU/MLX/Metal 路径、数值精度、Qt 运行时行为、胶片/配置文件默认值以及测试有效性。

## 发现摘要

- 严重：1
- 高：3
- 中：4
- 低：1

## 严重发现

### C1. HDR 渲染 EXR 模式已暴露并报告成功，但实际保存的是场景线性存档 — 已修复

- 文件/符号：src/spektrafilm_gui/controller.py:543, src/spektrafilm_gui/controller.py:552, src/spektrafilm_gui/controller.py:594, src/spektrafilm_gui/controller.py:628; src/spektrafilm/utils/io.py:477; tests/gui/test_controller_output.py:498; tests/test_image_io_color_metadata.py:168; README.md:254.
- 观察到的问题：控制器检测到 hdr_exr_mode == "hdr_rendition" 并收集元数据，但非 HEIC 保存分支仅将 encoding 和 white_luminance 传递给 save_image_oiio。它从未传递 exr_mode、scene_luminance、scene_rgb 或 hdr_mapping_kwargs，且 save_image_oiio 没有对应的参数。
用户可见的状态仍然显示 EXR 已保存为 HDR 渲染。
- 这是缺陷/风险的原因：显式的 HDR 渲染 EXR UI 路径静默地写入现有的输出浮点层，而不是已创建的 HDR 渲染。这是一个错误的导出，可能导致 HDR 验证、交接和归档工作流无效。
- 预期行为：scene_linear_archive 写入现有的渲染浮点输出，whiteLuminance=203；hdr_rendition 写入与 HEIC/HDR 照片导出使用的相同已创建 HDR 渲染，同时保留 EXR 颜色元数据。
- 证据：
  - README 文档将 HDR 渲染 EXR 记录为一个独立的显式模式。
  - tests/gui/test_controller_output.py::test_save_output_layer_hdr_rendition_exr_passes_explicit_mode_and_sidecar 因 KeyError: 'exr_mode' 而失败。
  - tests/test_image_io_color_metadata.py::test_archive_exr_does_not_call_hdr_rendition_mapping 失败，因为测试调用了文档记录的 API 形状，但 save_image_oiio 拒绝了 scene_luminance。
- 具体建议修复方案：
  - 要么扩展 save_image_oiio，添加 exr_mode、scene_luminance、scene_rgb 和 hdr_mapping_kwargs 参数，要么在 save_hdr_photo_heic 旁添加一个专用的 save_hdr_rendition_exr 辅助函数。
  - 在 GuiController.save_output_layer 中，为 exr_save 和 hdr_exr_mode == "hdr_rendition" 传递显式的 HDR 渲染模式和元数据。
  - 保持存档 EXR 的默认行为不变，并确保它永远不会调用 HDR 映射。
- 建议测试：
  - 使 test_save_output_layer_hdr_rendition_exr_passes_explicit_mode_and_sidecar 通过。
  - 使 test_hdr_rendition_exr_uses_authored_hdr_mapping 通过，并断言像素与存档输出不同。
  - 添加控制器级别测试，确保状态文本在 HDR 渲染辅助函数未被调用时不能声称 HDR 渲染。
- 修复风险：中等。它涉及导出路由和颜色/HDR 元数据，但可以在显式 hdr_rendition 后面隔离。

## 高级发现

### H1. ACEScg ICC 配置文件存在但未被映射，导致 TIFF ICC 导出和显示变换 ICC 转换中断 — 已修复

- 文件/符号：src/spektrafilm/utils/io.py:157, src/spektrafilm/utils/io.py:211, src/spektrafilm/utils/io.py:222, src/spektrafilm_gui/controller_runtime.py:181, src/spektrafilm_gui/controller_runtime.py:191, tests/test_image_io_color_metadata.py:294, tests/gui/test_controller_runtime_module.py:193.
- 观察到的问题：src/spektrafilm/data/icc/ellelstone/ACEScg-elle-V2-g10.icc 和 ACEScg-elle-V2-srgbtrc.icc 已被捆绑，但 _ICC_FILENAMES 和 _ICC_PROFILES 不包含 "ACEScg"。resolve_icc_profile_bytes("ACEScg", cctf_encoding=False) 返回 None。
- 这是缺陷/风险的原因：ACES 参考工作流使用 ACEScg 作为场景线性工作空间，但 ACEScg TIFF 导出省略了 ICC 元数据，显示变换回退到 sRGB 配置文件创建。
- 具体建议修复方案：
  - 将 ("ACEScg", False): "ellelstone/ACEScg-elle-V2-g10.icc" 添加到 _ICC_FILENAMES。
  - 仅当 UI 确实可以生成编码的 ACEScg 时，才考虑 ("ACEScg", True): "ellelstone/ACEScg-elle-V2-srgbtrc.icc"；否则明确拒绝编码的 ACEScg 输出。
  - 将 "ACEScg" 添加到 _ICC_PROFILES，或更新 _known_color_space_from_icc_profile 使其也遍历 _ICC_FILENAMES 变体。
- 建议测试：
  - 使 test_acescg_tiff_icc_roundtrips_as_linear_encoding 通过。
  - 添加对 resolve_icc_profile_bytes("ACEScg", cctf_encoding=False) 的直接测试。
  - 添加显示变换测试，使用伪造的 ImageCmsProfile 证明 ICC 路径被使用。

### H2. GUI "启用路径到白色" 开关未能禁用感知配置文件的 HDR 路径到白色 — 已修复

- 文件/符号：src/spektrafilm_gui/state.py:365, src/spektrafilm_gui/widget_specs.py:680, src/spektrafilm_gui/controller.py:560, src/spektrafilm_gui/controller.py:569, src/spektrafilm/utils/hdr_photo.py:95, src/spektrafilm/utils/hdr_photo.py:110, src/spektrafilm/utils/hdr_photo.py:662.
- 观察到的问题：GUI 状态暴露了 path_to_white_enabled，控制器仅将其映射到旧版 hdr_highlight_path_to_white。感知配置文件的 HDR 颜色恢复使用 profile_hdr_path_to_white_strength，该值保持在默认的 0.30。
- 这是缺陷/风险的原因：用户可以在 GUI 中禁用路径到白色，但在感知配置文件的 HDR 导出中仍然会得到高光去饱和/中和。
- 具体建议修复方案：
  - 在 GuiController.save_output_layer 中，当 path_to_white_enabled 为 false 时，也传递 profile_hdr_path_to_white_strength=0.0。
  - 如果启用时的期望默认值是 0.30，则显式传递它，而不是依赖 HDRPhotoMapping 默认值。
- 建议测试：
  - 控制器测试：设置 gui_state.hdr_export.path_to_white_enabled=False 并断言 HDRPhotoMapping.profile_hdr_path_to_white_strength == 0.0。
  - HDR 单元测试：当等效 GUI 映射禁用路径到白色时，感知配置文件的高光保持饱和。

### H3. GUI 预览/全扫描始终计算和存储全尺寸 HDR 元数据，造成大量内存压力 — 延期

- 文件/符号：src/spektrafilm_gui/controller.py:926, src/spektrafilm/runtime/pipeline.py:299, src/spektrafilm/runtime/pipeline.py:140, src/spektrafilm/runtime/pipeline.py:143, src/spektrafilm/runtime/pipeline.py:542, src/spektrafilm_gui/controller.py:699, src/spektrafilm_gui/controller_layers.py:421.
- 观察到的问题：GuiController._process_image_with_runtime 在 process_with_metadata 存在时始终调用它，用于普通预览和扫描。process_with_metadata 始终构建 scene_luminance 和 scene_rgb 元数据，并尝试动态配置文件表征，然后 GUI 将这些元数据存储在输出层上。
- 这是缺陷/风险的原因：一张 4000x6000 的 float32 图像大约增加 366 MiB 的元数据数组。这破坏了所声称的大型 RAW/低内存优先级。
- 具体建议修复方案：
  - 向 SimulationRequest 添加请求标志，如 collect_hdr_metadata。
  - 对于普通 SDR 预览/扫描使用 Simulator.process()，仅当用户启用/需要 HDR 导出元数据时使用 process_with_metadata()。
  - 考虑仅当映射模式需要源 RGB 颜色恢复时存储 scene_rgb，或在显式 HDR 导出时为全分辨率扫描重新计算元数据。

## 中级发现

### M1. HDR SDR 基础测试期望与当前 SDR 保留实现冲突 — 已修复

- 文件/符号：src/spektrafilm/utils/hdr_photo.py:49, src/spektrafilm/utils/hdr_photo.py:454, tests/test_hdr_photo.py:24, README.md:256.
- 观察到的问题：HDRPhotoMapping.preserve_sdr_base 默认为 True，通用 HDR 渲染创建将原始图像裁剪到 sdr_rgb 中。第一个 HDR 照片单元测试仍然期望漫反射白映射到 sdr_paper_white=0.9。
- 具体建议修复方案：
  - 确定当前 preserve_sdr_base=True 默认值是否是预期的分支行为。
  - 如果是，更新早期 HDR 照片测试以断言 SDR 基础保留，并将旧的色调映射覆盖移到 preserve_sdr_base=False。
  - 如果否，更改默认行为并添加回归测试证明 SDR 输出不会全局变暗。

### M2. 现代配置文件 HDR 映射参数接受无效范围 — 已修复

- 文件/符号：src/spektrafilm/utils/hdr_photo.py:118, src/spektrafilm/utils/hdr_photo.py:121, src/spektrafilm/utils/hdr_photo.py:181, src/spektrafilm/utils/hdr_curve_profiles.py:892, src/spektrafilm/utils/hdr_curve_profiles.py:897.
- 观察到的问题：HDRPhotoMapping.__post_init__ 验证 profile_hdr_mode、目标峰值和恢复比，但接受无效的 profile_hdr_normalize_percentile、负的 profile_hdr_recovery_knee_ev、负的或反转的恢复跨度、零 profile_hdr_max_chroma_gain 以及反转的路径到白色 EV 范围。
- 具体建议修复方案：
  - 扩展 HDRPhotoMapping.__post_init__ 验证：
    - 0 < profile_hdr_normalize_percentile <= 100
    - 有限的 profile_hdr_recovery_knee_ev >= 0
    - profile_hdr_recovery_full_ev > profile_hdr_recovery_knee_ev
    - 有限的 profile_hdr_max_chroma_gain >= 1
    - profile_hdr_path_to_white_start_ev < profile_hdr_path_to_white_end_ev
    - 0 <= profile_hdr_path_to_white_strength <= 1

### M3. GUI HEIC 测试调用真实编码器，可能通过 QMessageBox 在没有 QApplication 的情况下中止 pytest

- 文件/符号：tests/gui/test_controller_output.py:65, tests/gui/test_controller_output.py:395, src/spektrafilm_gui/controller.py:582, src/spektrafilm_gui/controller.py:601.
- 观察到的问题：_capture_saved_output 猴补丁了 save_image_oiio 和 write_image_metadata，但 HEIC 测试在不替换的情况下执行 save_hdr_photo_heic。当真实 HEIC 路径抛出异常时，控制器捕获它并调用 QMessageBox.critical；在测试进程中没有 QApplication，因此 Qt 中止了解释器。
- 具体建议修复方案：
  - 添加一个 HEIC 专用的捕获辅助函数，对 controller_module.save_hdr_photo_heic 进行猴补丁。
  - 在错误路径测试中对 QMessageBox.critical 进行猴补丁，或使用拥有 QApplication 的 Qt 测试夹具。

### M4. save_image_oiio 和 HDR 导出 API 边界不清晰，跨测试/文档不一致 — 已修复

- 文件/符号：src/spektrafilm/utils/io.py:477, src/spektrafilm_gui/controller.py:157, tests/test_image_io_color_metadata.py:137, tests/test_image_io_color_metadata.py:204, docs/superpowers/plans/2026-05-24-scene-energy-hdr-gainmap-autoexposure.md:55.
- 观察到的问题：测试和计划期望 save_image_oiio 接受 HEIC/HDR 元数据参数，而实现将 HEIC 视为控制器级别特殊情况，save_image_oiio 仅作为通用光栅/EXR 写入。
- 具体建议修复方案：
  - 选择并记录所有权边界。
  - 如有需要，重命名辅助函数，例如 save_standard_image_oiio、save_hdr_rendition_exr 和 save_hdr_photo_heic。
  - 更新测试以针对所选的 API 层。

## 低级发现

### L1. README 仍然宣传缺失的 src/spektrafilm_profile_creator 包 — 仍然存在

- 文件/符号：README.md:53.
- 观察到的问题：README 目录树列出了 src/spektrafilm_profile_creator/，但审查的源代码树仅包含 src/spektrafilm 和 src/spektrafilm_gui。
- 具体建议修复方案：更新 README 目录树以反映当前的包，或者如果仍然需要，恢复/打包配置文件创建器。

## 最终优先级操作列表

推送/集成前必须修复：

1. 实现或移除/阻止 HDR 渲染 EXR 模式，使其不能静默保存错误的导出。
2. 修复 ACEScg ICC 映射和显示变换/配置文件往返转换。
3. 修复感知配置文件的路径到白色 GUI 开关契约。
4. 使测试套件不中止，并调和 HDR SDR 基础测试期望。

应尽快修复：

1. 在构造时验证所有现代配置文件 HDR 映射参数。
2. 将普通 SDR 预览/扫描与昂贵的 HDR 元数据收集分开，或使 HDR 就绪的内存成本显式化。
3. 澄清 save_image_oiio 与专用 HDR 辅助函数的所有权，并相应更新测试。

可选清理：

1. 更新 README 源代码树以移除或解释 src/spektrafilm_profile_creator。
2. 将生成的分析文档/工件与源代码审查行为明确分离。

需要用户/产品决策：

1. 确认默认 HEIC SDR 基础是否应保留当前 SDR 外观（preserve_sdr_base=True）或继续旧的 sdr_paper_white=0.9 色调映射契约。
2. 决定 HDR 元数据是否应在每次扫描后始终保留以便后续方便导出，还是仅在显式 HDR 就绪运行时收集。
