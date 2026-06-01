# 色彩管理与 HDR 处理代码审查报告

日期：2026-05-31
本轮更新：修复上一版报告列出的三项剩余风险，并刷新真实 RAW/HDR metadata 验证。

范围：`src/spektrafilm/color_management.py`、runtime 参数/管线/阶段、GUI state/mapper/controller、macOS bridge、ImageIO HDR/ICC/gain-map 接口、`tools/validate_profile_aware_hdr_raw_samples.py`、相关测试与验证报告。

## 结论

当前色彩管理与 HDR 处理已经从“底层能力存在但接入不完整”推进到“GUI/runtime/export 关键路径已接入并有回归测试”的状态。

已完成的关键修复：

- SDR 默认路径保持 `sRGB + CCTF + clip`，默认行为没有被 ACES/HDR 改动破坏。
- `aces_reference` workflow 运行时固定为 `ACEScg` scene-linear 输入/输出，保存默认为 `ACES2065-1` linear interchange，并关闭运行时高光/负值夹断。
- GUI manual workflow 拆分了 runtime output encoding 与 save encoding：`output_cctf_encoding` 只控制模拟输出，`saving_cctf_encoding` 只控制文件保存。
- 线性 ACES preview 不再走普通 sRGB approximation 分支；GUI 与 macOS bridge 现在调用 `aces_sdr_video_view_transform()`，并在 ACES/scene-linear 预览中保留大于 1.0 的高光再进行显示渲染。
- HDR scene-energy sidecar 仍由 `process_with_metadata()` 产出并传入保存路径；真实 DNG 验证脚本现在同时检查 sidecar、Android Ultra HDR/ISO gain-map metadata、JPEG MPF probe 和 EXR attribute 预期。
- gain-map JPEG XMP 现在包含 Android Ultra HDR/GContainer 所需的 `Container:Directory`、`Primary`、`GainMap` item 语义和 secondary item length。

## 参考依据

- ACES Output Transforms：ACES 官方把 Output Transform 定义为从 scene-linear ACES 到特定显示设备编码的输出渲染链。https://docs.acescentral.com/system-components/output-transforms/
- ACEScg：ACEScg 是 AP1、scene-linear、浮点 CGI/rendering/compositing 工作空间。https://docs.acescentral.com/encodings/acescg/
- OpenColorIO ACES 配置：OCIO 的 ACES config 把 ACEScg 作为 scene/compositing linear，并提供 ACES output colorspaces。https://opencolorio.readthedocs.io/en/v2.4.0/configurations/aces_1.0.3.html
- Qt QColorSpace：Display P3 是 wide-gamut display space，预览链不应无条件压到 sRGB 中间件。https://doc.qt.io/qt-6/qcolorspace.html
- OpenEXR Standard Attributes：`chromaticities` 与 `whiteLuminance` 描述 RGB 图像色度与白亮度。https://openexr.com/en/latest/StandardAttributes.html
- Android Ultra HDR v1.1：JPEG gain-map 需要 XMP `Container:Directory`、`Primary/GainMap` item 语义，并建议同时编码 Ultra HDR 与 ISO 21496-1 metadata。https://developer.android.com/media/platform/hdr-image-format

## 修复详情

### 1. ACES Preview 从 sRGB Approximation 改为明确 Output View

旧风险：

- 线性 ACES preview 只做 `RGB_to_RGB(..., "sRGB")`，等价于普通 sRGB 显示近似。
- 预览入口会先把 float 图像裁到 `0..1`，这会在显示渲染前丢失 HDR 高光。

本轮修复：

- 新增 `aces_sdr_video_view_transform()`，入口只接受 `ACES2065-1` 或 `ACEScg` scene-linear RGB。
- helper 先转换到 linear sRGB primaries，再走本地 ACES-style SDR video rendering curve 与 sRGB display encoding，输出 `0..1` display-referred code values。
- GUI `controller_runtime.apply_display_transform()` 对 ACES scene-linear 输出调用该 helper，状态文本为 `Display transform: ACES SDR video output transform`。
- `controller_runtime.prepare_output_display_image()` 与 `macos_bridge._display_preview_image()` 对 ACES/linear scene 预览只裁负值，不再裁掉大于 1.0 的 scene highlights。

边界说明：

- 这已经不再是未命名的 sRGB approximation，但仍不是 OCIO/CTL 精确 ACES 2 Output Transform。要达到 studio 级跨软件逐像素一致性，下一步应接入 OCIO Studio/CG ACES config 或项目内实现 ACES 官方 CTL/Output Transform。
- 本项目当前修复目标是把 GUI/runtime 预览从错误/含混的 sRGB 分支迁移到明确、可测试、保留 HDR 高光的 ACES SDR output view。

### 2. Runtime Output Encoding 与 Save Encoding 已拆分

旧风险：

- GUI manual workflow 暴露了 workflow selector，但 runtime output CCTF 仍复用 save CCTF。
- 这会让“运行时线性输出、保存时编码输出”或反向组合无法被准确表达。

本轮修复：

- `SimulationState` 新增 `output_cctf_encoding`。
- `params_mapper._apply_io()` 将 `params.io.output_cctf_encoding` 映射为 `state.simulation.output_cctf_encoding`，不再读取 `saving_cctf_encoding`。
- `OutputSection` 同时显示 `output_color_space`、`output_cctf_encoding`、`saving_color_space`、`saving_cctf_encoding`。
- GUI controller 的 async/sync fallback、output layer metadata、display transform request 均使用 runtime `output_cctf_encoding`。
- save path 继续使用 `saving_color_space` 与 `saving_cctf_encoding`，并按 source runtime encoding 解码/转换后保存。
- macOS bridge 增加 `BridgeRenderOptions.output_cctf_encoding`、CLI defaults 和 `--output-cctf-encoding` / `--no-output-cctf-encoding`。

验证覆盖：

- manual workflow 下 runtime `output_cctf_encoding=True`、saving `saving_cctf_encoding=False` 可独立成立。
- 旧 GUI JSON 缺字段时回填默认 `True`。
- controller fallback 和 macOS bridge 均有独立测试。

### 3. HDR Scene Luminance 与 Gain-Map Metadata 已用真实样张验证

旧风险：

- `scene_luminance` 来自 auto-exposure 与 crop/rescale 后的输入场景 RGB，缺少真实 HDR photo metadata 验证。
- Apple/Android/ISO gain-map metadata 是否完整缺少自动检查。

本轮修复：

- `tools/validate_profile_aware_hdr_raw_samples.py` 修复 stale RAW API import，并在真实 DNG 验证中输出 metadata checks。
- 验证脚本现在对每个样张检查：
  - `process_with_metadata()` sidecar shape、finite/nonnegative、与 process output 的一致性；
  - auto-exposure 全局缩放下 sidecar 中位数保持 scale-invariant；
  - Android Ultra HDR/GContainer XMP 是否包含 `Container:Directory`、`Primary`、`GainMap`；
  - ISO 21496-1 binary metadata serialize/deserialize roundtrip；
  - gain-map 数值域与 validation warning；
  - JPEG probe 是否同时包含 ISO URN、GContainer XMP 与 MPF gain-map；
  - EXR export 应跟踪的 attributes：`chromaticities`、`colorInteropID`、`oiio:ColorSpace`、`whiteLuminance`、`hdrHeadroom`。
- `GainMapMetadata.to_xmp(gain_map_length=...)` 现在生成 Android Ultra HDR-compatible `Container:Directory`。
- `save_gain_map_jpeg()` 写入实际 gain-map JPEG byte length，并保持 MPF payload。

真实样张结果：

- 样张目录：`/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片/RAW_DNG_JPEG_批量导出`
- 发现 DNG：365 个；本轮抽样验证 4 个，覆盖普通曝光、低调、强高光、近白裁剪样张。
- 最新报告：`docs/hdr_profile_aware_raw_validation.md`
- 所有 4 个样张均通过 sidecar finite/nonnegative、process parity、auto-exposure scale-invariant、Android container、ISO metadata roundtrip、JPEG metadata/gain-map probe、EXR attribute tracking 检查。

边界说明：

- 本轮验证证明项目生成的 metadata 结构和本地 probe 符合 Android Ultra HDR/ISO/OpenEXR 预期；它不是 Apple Photos、Android Gallery 或第三方 ISO decoder 的人工/设备渲染验收。
- 对复杂 HDR photo export，仍建议保留设备验收 runbook：生成 HEIC/JPEG/EXR 样张，在 Apple Photos、Android 15+ Ultra HDR viewer、至少一个 ISO 21496-1 decoder 中检查识别和显示。

## 当前代码路径完整度

| 路径 | 当前状态 |
| --- | --- |
| SDR manual runtime | 默认 `sRGB + CCTF + clip`，保持兼容 |
| ACES reference runtime | `ACEScg + linear + unclipped` |
| ACES reference save | `ACES2065-1 + linear` |
| GUI runtime output CCTF | 独立字段 `output_cctf_encoding` |
| GUI save CCTF | 独立字段 `saving_cctf_encoding` |
| GUI ACES preview | `aces_sdr_video_view_transform()` |
| macOS bridge ACES preview | 同步调用 `aces_sdr_video_view_transform()` |
| HDR sidecar | `process_with_metadata()` 输出并传入 save path |
| Android/ISO gain-map JPEG | XMP GContainer + ISO metadata + MPF probe |
| EXR HDR metadata | `chromaticities`、`colorInteropID`、`oiio:ColorSpace`、`whiteLuminance`、`hdrHeadroom` 被验证脚本跟踪 |

## 主要修改文件

- Plan：`docs/superpowers/plans/2026-05-31-aces-output-transform-hdr-metadata-encoding-split.md`
- 色彩管理：`src/spektrafilm/color_management.py`
- GUI runtime/display：`src/spektrafilm_gui/controller_runtime.py`
- GUI state/mapper/widgets：`src/spektrafilm_gui/state.py`、`src/spektrafilm_gui/params_mapper.py`、`src/spektrafilm_gui/widget_specs.py`、`src/spektrafilm_gui/widget_sections.py`
- GUI controller/save：`src/spektrafilm_gui/controller.py`
- macOS bridge：`src/spektrafilm_gui/macos_bridge.py`
- Gain-map metadata/io：`src/spektrafilm/utils/gain_map_metadata.py`、`src/spektrafilm/utils/gain_map_io.py`
- HDR validation：`tools/validate_profile_aware_hdr_raw_samples.py`、`docs/hdr_profile_aware_raw_validation.md`、`docs/hdr_profile_aware_raw_validation.json`
- Tests：`tests/test_color_management.py`、`tests/test_gain_map.py`、`tests/test_hdr_profile_validation_tool.py`、`tests/gui/test_controller_runtime_module.py`、`tests/gui/test_params_mapper.py`、`tests/gui/test_persistence.py`、`tests/gui/test_controller_flow.py`、`tests/gui/test_macos_bridge.py`

## 验证

已运行并通过：

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /usr/bin/perl -e 'alarm shift; exec @ARGV' 120 \
  uv run --extra dev pytest -q \
  tests/gui/test_controller_runtime_module.py::test_prepare_output_display_image_uses_aces_output_transform_for_linear_scene \
  tests/gui/test_macos_bridge.py::test_display_preview_preserves_aces_scene_highlights \
  tests/test_color_management.py::test_aces_sdr_video_view_transform_is_named_output_view_with_srgb_encoding
```

结果：`3 passed in 2.64s`

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /usr/bin/perl -e 'alarm shift; exec @ARGV' 240 \
  uv run --extra dev pytest -q \
  tests/test_color_management.py \
  tests/test_gain_map.py \
  tests/test_hdr_profile_validation_tool.py \
  tests/gui/test_params_mapper.py \
  tests/gui/test_persistence.py \
  tests/gui/test_controller_runtime_module.py \
  tests/gui/test_controller_flow.py \
  tests/gui/test_controller_output.py \
  tests/gui/test_macos_bridge.py
```

结果：`130 passed in 4.93s`

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /usr/bin/perl -e 'alarm shift; exec @ARGV' 900 \
  uv run --extra dev pytest -q
```

结果：`875 passed, 7 skipped, 1 warning in 52.84s`

```bash
/usr/bin/perl -e 'alarm shift; exec @ARGV' 900 \
  uv run python tools/validate_profile_aware_hdr_raw_samples.py \
  --sample-dir "/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片/RAW_DNG_JPEG_批量导出" \
  --max-samples 4 \
  --diagnostic-scan-limit 32 \
  --output docs/hdr_profile_aware_raw_validation.md
```

结果：完成 4 个真实 DNG 样张验证并刷新 `docs/hdr_profile_aware_raw_validation.md/json`。

最终收尾已运行并通过：

```bash
.venv/bin/python -m py_compile \
  src/spektrafilm/color_management.py \
  src/spektrafilm_gui/controller_runtime.py \
  src/spektrafilm_gui/state.py \
  src/spektrafilm_gui/widget_specs.py \
  src/spektrafilm_gui/widget_sections.py \
  src/spektrafilm_gui/params_mapper.py \
  src/spektrafilm_gui/controller.py \
  src/spektrafilm_gui/macos_bridge.py \
  src/spektrafilm/utils/gain_map_metadata.py \
  src/spektrafilm/utils/gain_map_io.py \
  tools/validate_profile_aware_hdr_raw_samples.py
```

```bash
git diff --check
```

## 当前剩余限制

- ACES preview 已从旧 sRGB approximation 修复为明确的本地 ACES SDR output view，并保留 scene highlights；但它仍不是 OCIO/CTL 精确 ACES 2 Output Transform。专业跨软件显示一致性需要接入 OCIO ACES config 或官方 CTL 参考实现。
- HDR metadata 已用真实 DNG 生成物和本地 JPEG/EXR metadata probe 验证；尚未完成 Apple Photos、Android Gallery、第三方 ISO decoder 的设备级显示验收。
- GUI 和 macOS bridge 已拆分 runtime/save encoding；外部直接调用 runtime/save API 的脚本仍需要显式传入正确的 `output_cctf_encoding`、`saving_cctf_encoding` 和 `scene_luminance`。

## 自检

- 是否还有旧的 `linear scene preview, using sRGB view approximation`？没有；ACES scene-linear 路径改为 `Display transform: ACES SDR video output transform`。
- ACES preview 是否还会在 transform 前裁掉 HDR 高光？不会；GUI 与 macOS bridge 的 ACES/linear branch 只裁负值，不裁大于 1.0 的值。
- manual workflow 是否还复用 saving CCTF 作为 runtime output CCTF？不会；mapper/controller/bridge 均使用独立 `output_cctf_encoding`。
- SDR 默认是否改变？没有；默认仍为 `manual`、runtime `sRGB + CCTF`、saving `sRGB + CCTF`。
- 能否声称“100% 没有任何外部显示差异风险”？不能。能 100% 确认的是本报告列出的本地代码路径、回归测试和真实样张 metadata probe 已闭环；外部设备渲染一致性需要单独的设备验收。
