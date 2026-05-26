# HDR EXR 输出实现方案

本文档记录 spektrafilm 当前图像处理链路中和 HDR EXR 输出有关的关键路径、阻塞点，以及一套可落地的实现方案。目标很明确：保存 `.exr` 时，输出像素应允许保留 scene-linear 的高光值，RGB 通道可以大于 `1.0`。

## 目标

1. `.exr` 输出保留浮点 HDR 数据，至少在高光区域允许 `max(rgb) > 1.0`。
2. PNG/JPEG 和 napari 预览仍维持现有 SDR 行为，不因为 HDR EXR 改动而破坏 GUI 显示。
3. EXR 输出默认使用线性数据，不做 CCTF 编码，不做上限裁切。
4. 保留色彩空间元数据，EXR 写入 `chromaticities`，避免下游应用把宽色域或 ACES 数据误读为 sRGB。
5. 默认行为尽量兼容当前工程：普通用户不启用 HDR 输出时，runtime 仍返回 `0..1` 范围内的显示用结果。

## 资料和搜索结论

### 官方资料

- OpenEXR 官方技术介绍说明 OpenEXR 存储 16-bit 或 32-bit 浮点像素，适合高动态范围图像；并明确 `1.0` 不是裁切上限，亮于纸白、火焰、高光等可以使用更大的像素值表示。参考：[Technical Introduction to OpenEXR](https://openexr.com/en/latest/TechnicalIntroduction.html)。
- OpenEXR 标准属性中，`chromaticities` 用于 RGB 图像的 CIE `(x, y)` 原色和白点描述，`whiteLuminance` 也可描述 RGB `(1, 1, 1)` 的亮度含义。参考：[OpenEXR Standard Attributes](https://openexr.com/en/latest/StandardAttributes.html)。
- OpenImageIO 的 `ImageOutput` 写图流程是通过 `ImageSpec` 指定宽高、通道数、像素格式，再用 `write_image()` 写入像素。当前项目中的 `save_image_oiio()` 使用方式和官方模式一致。参考：[OpenImageIO ImageOutput: Writing Images](https://openimageio.readthedocs.io/en/latest/imageoutput.html)。

### 本项目搜索结论

本地搜索重点覆盖了 `exr/openexr/hdr/imwrite/save/export/output/clip/cctf/srgb/linear` 等关键词。结论如下：

- EXR 写出函数不是主要瓶颈。`src/spektrafilm/utils/io.py` 的 `save_image_oiio()` 对 `.exr` 已经支持 `half` 和 `float`，且不会像 PNG/JPEG 分支那样 `np.clip(image_data, 0, 1)`。
- 当前 runtime 的最终扫描阶段会把输出裁到 `0..1`。阻塞点在 `src/spektrafilm/runtime/stages/scanning.py` 的 `_apply_cctf_encoding_and_clip()`，最后一行是 `np.clip(rgb, a_min=0, a_max=1)`。
- GUI 保存路径优先使用输出 layer metadata 里的浮点图像，而不是 8-bit 预览图。因此只要 runtime 返回 HDR 浮点图，`save_output_layer()` 可以把它传给 `save_image_oiio()`。
- GUI 预览路径会裁切到 `0..1` 并转为 `uint8`，这是合理的显示路径，不应作为保存 EXR 的数据源。
- 目前 GUI/runtime 有几处把输出编码状态硬编码为 `True`，实现 HDR EXR 时必须改掉，否则保存时会把线性 HDR 数据误认为已经做过 CCTF 编码，或者在保存色域转换时做错 decoding。

我也做了两个小验证：

1. `save_image_oiio()` 写入 `[[0.25, 1.5, 4.0]]` 到 `/tmp/spektrafilm_hdr_probe.exr` 后再读回，结果保留为 `[0.25, 1.5, 4.0]`，`max=4.0`。这说明 OIIO EXR 写读路径本身可以保存大于 1 的值。
2. 现有完整模拟链路在很亮输入下仍返回 `<= 1` 的结果。一次 probe 使用高亮输入，输出最大值约为 `0.8157`。这和扫描末端裁切逻辑一致。

## 当前处理链路

### 1. 输入读取

GUI 文件导入入口在：

- `src/spektrafilm_gui/controller.py::GuiController.load_input_image()`
- `src/spektrafilm/utils/io.py::load_image_oiio()`

`load_image_oiio()` 的行为：

- `uint8` 和 `uint16` 会归一化到 `0..1`。
- `half` 和 `float` 会按原格式读取，不做 `0..1` 归一化。
- 因此输入 EXR/TIFF float 可以保留大于 `1.0` 的源数据。

RAW 导入入口在：

- `src/spektrafilm_gui/controller.py::GuiController.load_raw_image()`
- `src/spektrafilm/utils/raw_file_processor.py::load_and_process_raw_file()`

RAW 当前经 `rawpy.postprocess(... output_bps=16)` 后除以 `65535.0`，更偏向 `0..1` 的线性工作图。HDR EXR 输出的核心不在 RAW 读取，而在模拟输出端是否允许 scene-linear 大于 `1.0`。

### 2. GUI 缓存和预览

输入图像会被存入：

- `GuiController._current_input_image`
- `GuiController._current_preview_image`

预览转换在：

- `src/spektrafilm_gui/controller_runtime.py::prepare_input_color_preview_image()`
- `src/spektrafilm_gui/controller_runtime.py::prepare_output_display_image()`
- `src/spektrafilm_gui/controller_runtime.py::normalized_image_data()`

这些函数会 `np.clip(..., 0, 1)`，并最终生成 `uint8` 预览图。这一层是显示链路，裁切是合理的，不应作为 EXR 保存数据源。

### 3. Runtime 主链路

入口：

- `src/spektrafilm/runtime/process.py::simulate()`
- `src/spektrafilm/runtime/process.py::Simulator.process()`
- `src/spektrafilm/runtime/pipeline.py::SimulationPipeline.process()`

主要阶段：

1. `SimulationPipeline._preprocess()`
   - 转 `np.double`。
   - 执行 auto exposure。
   - crop/resize。
2. `FilmingStage.expose()`
   - RGB 到 film raw。
   - camera exposure compensation。
   - highlight boost、diffusion、lens blur、halation。
   - 转 `log_raw`。
3. `FilmingStage.develop()`
   - film raw 到 CMY density。
4. `PrintingStage.expose()`
   - negative density 经 enlarger 光源投射到 print raw。
   - print exposure 和 correction。
   - 转 `log_raw_print`。
5. `PrintingStage.develop()`
   - print raw 到 print CMY density。
6. `ScanningStage.scan()`
   - density 到 XYZ。
   - black/white correction。
   - glare。
   - XYZ 到输出 RGB。
   - CCTF 编码和裁切。

当前 HDR 被最后一步吃掉。

### 4. 扫描阶段的关键阻塞点

`src/spektrafilm/runtime/stages/scanning.py`：

```python
def scan(self, density_channels: np.ndarray) -> np.ndarray:
    rgb = self._density_to_rgb(density_channels, use_lut=self._settings.use_scanner_lut)
    rgb = self._apply_blur_and_unsharp(rgb)
    return self._apply_cctf_encoding_and_clip(rgb)
```

`_density_to_rgb()` 返回的是线性 RGB：

```python
return colour.XYZ_to_RGB(
    xyz,
    colourspace=self._io.output_color_space,
    apply_cctf_encoding=False,
    illuminant=illuminant_xy,
)
```

但 `_apply_cctf_encoding_and_clip()` 末尾固定裁切：

```python
return np.clip(rgb, a_min=0, a_max=1)
```

这就是 EXR 输出无法大于 `1.0` 的核心原因。

### 5. 黑白校正的潜在阻塞点

`src/spektrafilm/runtime/services/color_reference.py::_correction_fucntion()` 里有：

```python
return np.clip(m * y + q, 0, 1)
```

默认 `ScannerParams.black_correction` 和 `white_correction` 都是 `False`，所以通常不会触发。但如果用户启用扫描白点或黑点校正，这里也会把 Y 压到 `0..1`。HDR 模式下需要让这段逻辑遵守同一个输出裁切策略，至少不能固定裁掉高光。

### 6. 保存路径

GUI 保存入口：

- `src/spektrafilm_gui/controller.py::GuiController.save_output_layer()`

关键行为：

```python
float_image_data = self._output_layer_float_data()
if float_image_data is None:
    image_data = runtime.normalized_image_data(np.asarray(output_layer.data)[..., :3])
else:
    image_data = np.asarray(float_image_data)[..., :3]
```

这点对 HDR 是好消息：只要 output layer 有 `OUTPUT_FLOAT_DATA_KEY`，保存用的是 runtime 浮点结果，不是预览 `uint8` 图。

随后会根据 layer metadata 里的 `source_color_space/source_cctf_encoding` 和 GUI 的 `saving_color_space/saving_cctf_encoding` 做色彩转换：

```python
image_data = colour.RGB_to_RGB(
    image_data,
    source_color_space,
    saving_color_space,
    apply_cctf_decoding=source_cctf_encoding,
    apply_cctf_encoding=saving_cctf_encoding,
)
```

最后调用：

```python
save_image_oiio(filepath, image_data, color_space=saving_color_space)
```

这里还有两个需要修正的点：

- 当前模拟完成时 `_on_simulation_finished()` 和 `_run_simulation()` 都把 output layer metadata 的 `output_cctf_encoding` 写死为 `True`。
- `params_mapper._apply_io()` 也把 `params.io.output_cctf_encoding = True` 写死。

如果 HDR 模式使用线性输出，这些硬编码必须改成真实参数值。

### 7. EXR 写出函数

`src/spektrafilm/utils/io.py::save_image_oiio()` 当前逻辑：

- PNG/JPEG：固定 `np.clip(image_data, 0, 1)`，转 `uint8`。
- EXR 16-bit：转 `np.float16`，`ImageSpec(..., "half")`。
- EXR 32-bit：转 `np.float32`，`ImageSpec(..., "float")`。
- `color_space` 不为空时，会写 `chromaticities`。

因此 EXR 分支原则上已经满足保存 HDR 浮点值的需求。需要做的是确保传进来的 `image_data` 没有被 runtime 和 GUI 上游裁掉。

## 推荐设计

推荐把“用于显示的 SDR 输出”和“用于 EXR 保存的 scene-linear 输出”分开处理，而不是删除所有裁切。这样 GUI 仍然稳定，EXR 可以 HDR。

### 新增 runtime 输出裁切参数

在 `src/spektrafilm/runtime/params_schema.py::IOParams` 中新增：

```python
output_clip_min: bool = True
output_clip_max: bool = True
```

含义：

- `output_clip_min=True`：输出负值裁到 `0`。推荐 HDR EXR 初期保留这个开关为 `True`，避免宽色域转换或锐化产生负像素影响普通后期软件。
- `output_clip_max=True`：输出高光裁到 `1`。HDR EXR 模式必须设为 `False`。

默认值都为 `True`，保持当前行为。

### 扫描阶段按参数裁切

把 `ScanningStage._apply_cctf_encoding_and_clip()` 改为参数化：

```python
def _apply_cctf_encoding_and_clip(self, rgb: np.ndarray) -> np.ndarray:
    if self._io.output_cctf_encoding:
        rgb = colour.RGB_to_RGB(
            rgb,
            self._io.output_color_space,
            self._io.output_color_space,
            apply_cctf_decoding=False,
            apply_cctf_encoding=True,
        )

    if getattr(self._io, "output_clip_min", True):
        rgb = np.maximum(rgb, 0.0)
    if getattr(self._io, "output_clip_max", True):
        rgb = np.minimum(rgb, 1.0)
    return rgb
```

HDR EXR 参数组合：

```python
params.io.output_cctf_encoding = False
params.io.output_clip_min = True
params.io.output_clip_max = False
```

普通 SDR 参数组合保持：

```python
params.io.output_cctf_encoding = True
params.io.output_clip_min = True
params.io.output_clip_max = True
```

### 黑白校正遵守同一裁切策略

在 `ColorReferenceService` 初始化时保存输出裁切配置：

```python
self._output_clip_min = getattr(io_params, "output_clip_min", True)
self._output_clip_max = getattr(io_params, "output_clip_max", True)
```

把 `_correction_fucntion()` 中固定的：

```python
return np.clip(m * y + q, 0, 1)
```

改成：

```python
value = m * y + q
if self._output_clip_min:
    value = np.maximum(value, 0.0)
if self._output_clip_max:
    value = np.minimum(value, 1.0)
return value
```

这样启用白点校正时，HDR 模式仍可保留 `>1` 的亮度。

### GUI 添加 HDR EXR 输出开关

建议在 GUI 的 Simulation 区域新增一个布尔项：

```python
hdr_exr_output: bool
```

建议文案：

- Label: `HDR EXR output`
- Tooltip: `Keep the simulation output scene-linear for EXR saving; disables output CCTF and highlight clipping. Preview remains SDR.`

需要改的文件：

- `src/spektrafilm_gui/state.py`
  - `SimulationState` 新增 `hdr_exr_output: bool`
  - `gui_state_from_params()` 默认 `False`
- `src/spektrafilm_gui/widget_specs.py`
  - `GUI_WIDGET_SPECS["simulation"]["hdr_exr_output"]`
- `src/spektrafilm_gui/widget_sections.py`
  - 把新控件放到 Output 区域，靠近 `output_color_space/saving_color_space/saving_cctf_encoding`
- `src/spektrafilm_gui/state_bridge.py`
  - collect/apply 新状态
- `src/spektrafilm_gui/persistence.py`
  - 如果 persistence 是 dataclass 泛型序列化，确认新增字段能保存和读取
- `tests/gui/*`
  - 更新状态、控件和 persistence 相关测试

在 `src/spektrafilm_gui/params_mapper.py::_apply_io()` 中使用该开关：

```python
hdr_output = bool(getattr(state.simulation, "hdr_exr_output", False))

params.io.output_color_space = state.simulation.output_color_space
params.io.output_cctf_encoding = not hdr_output
params.io.output_clip_min = True
params.io.output_clip_max = not hdr_output
```

注意：当前 `_apply_io()` 硬编码 `params.io.output_cctf_encoding = True`，必须改掉。

### 输出 layer metadata 不再硬编码 CCTF

当前异步路径：

```python
self._set_or_add_output_layer(
    result.display_image,
    float_image=result.float_image,
    output_color_space=result.output_color_space,
    output_cctf_encoding=True,
    use_display_transform=result.use_display_transform,
)
```

需要让 `SimulationResult` 携带真实的 `output_cctf_encoding`：

```python
@dataclass(slots=True)
class SimulationResult:
    mode_label: str
    display_image: np.ndarray
    float_image: np.ndarray
    output_color_space: str
    output_cctf_encoding: bool
    use_display_transform: bool
    status_message: str
```

`execute_simulation_request()` 从 `request.params.io.output_cctf_encoding` 填入：

```python
output_cctf_encoding = bool(getattr(request.params.io, "output_cctf_encoding", True))
```

然后 `_on_simulation_finished()` 改为：

```python
output_cctf_encoding=result.output_cctf_encoding,
```

同步路径 `_run_simulation()` 也改为：

```python
output_cctf_encoding=params.io.output_cctf_encoding,
```

否则保存时 `save_output_layer()` 会把线性 HDR 输出误当作 CCTF 编码数据处理。

### EXR 保存时强制线性

`saving_cctf_encoding` 对 PNG/JPEG 有意义，但 HDR EXR 最好固定为线性。建议在 `save_output_layer()` 里根据扩展名处理：

```python
ext = Path(filepath).suffix.lower()
if ext == ".exr":
    saving_cctf_encoding = False
```

这样即使 GUI 中 `Saving CCTF encoding` 勾选了，保存 EXR 时也不会把 HDR 数据编码成显示传递函数。

如果希望更透明，可以在保存状态栏追加提示：

```python
status_suffix = " (EXR saved as linear HDR)"
```

### 推荐 EXR 色彩空间

为 HDR EXR 推荐使用：

1. `ACES2065-1`
2. `ITU-R BT.2020`
3. `ProPhoto RGB`

其中 `ACES2065-1` 是最适合开放高光范围的归档或后期交换选择。当前 `colorspace_chromaticities()` 从 `colour.RGB_COLOURSPACES` 取原色和白点，理论上可为以上色彩空间写 `chromaticities`。

需要注意 `_ICC_PROFILES` 里没有 `ACES2065-1`，但这只影响 PNG/JPEG 的 ICC 嵌入，不影响 EXR 的 `chromaticities`。

### EXR bit depth

当前 `save_image_oiio()` 默认 `bit_depth=32`，对 HDR EXR 很稳妥。可以先不加 UI。

建议策略：

- 第一阶段：EXR 默认写 32-bit float，确保验证简单且不引入精度争议。
- 后续阶段：新增 `exr_bit_depth` 选项，允许 `16 half` 或 `32 float`。

OpenEXR `half` 范围足够表示常见 HDR 高光，但如果后续要保留非常宽范围的中间数据或做数值分析，`float` 更直接。

## 具体实施顺序

### 第 1 步：runtime 参数化裁切

文件：

- `src/spektrafilm/runtime/params_schema.py`
- `src/spektrafilm/runtime/stages/scanning.py`
- `src/spektrafilm/runtime/services/color_reference.py`

改动：

1. `IOParams` 新增 `output_clip_min/output_clip_max`。
2. `ScanningStage._apply_cctf_encoding_and_clip()` 使用 `np.maximum/np.minimum` 分开裁切。
3. `ColorReferenceService` 的黑白校正裁切也使用同一策略。

验收：

- 默认参数下现有 pipeline smoke 测试仍应全部通过。
- 手动设置 `params.io.output_cctf_encoding=False`、`params.io.output_clip_max=False` 后，扫描阶段不再主动裁掉大于 `1.0` 的 RGB。

### 第 2 步：GUI 暴露 HDR 模式

文件：

- `src/spektrafilm_gui/state.py`
- `src/spektrafilm_gui/widget_specs.py`
- `src/spektrafilm_gui/widget_sections.py`
- `src/spektrafilm_gui/state_bridge.py`
- `src/spektrafilm_gui/params_mapper.py`
- `tests/gui/test_params_mapper.py`
- `tests/gui/test_state_bridge.py`
- `tests/gui/test_widgets.py`
- `tests/gui/test_persistence.py`

改动：

1. 增加 `hdr_exr_output` 状态和控件。
2. 控件状态变化连接 `controller.request_auto_preview`。
3. `_apply_io()` 中 HDR 模式设置：
   - `output_cctf_encoding=False`
   - `output_clip_min=True`
   - `output_clip_max=False`
4. 默认 `hdr_exr_output=False`。

验收：

- 默认状态下 `params.io.output_cctf_encoding is True`，`output_clip_max is True`。
- 开启 HDR 后 `params.io.output_cctf_encoding is False`，`output_clip_max is False`。

### 第 3 步：修正 output layer metadata

文件：

- `src/spektrafilm_gui/controller_runtime.py`
- `src/spektrafilm_gui/controller.py`
- `tests/gui/test_controller_runtime_module.py`
- `tests/gui/test_controller_flow.py`
- `tests/gui/test_controller_output.py`

改动：

1. `SimulationResult` 新增 `output_cctf_encoding`。
2. `execute_simulation_request()` 从 `request.params.io.output_cctf_encoding` 取真实值。
3. `_on_simulation_finished()` 和 `_run_simulation()` 不再硬编码 `True`。

验收：

- output layer metadata 中 `OUTPUT_CCTF_ENCODING_KEY` 和 runtime 参数一致。
- 保存时 `save_output_layer()` 的 `source_cctf_encoding` 正确，不会对线性 HDR 数据做错误解码。

### 第 4 步：EXR 保存策略

文件：

- `src/spektrafilm_gui/controller.py`
- `src/spektrafilm/utils/io.py`
- `tests/gui/test_controller_output.py`
- 新增或扩展 `tests/test_exr_io.py`

改动：

1. `save_output_layer()` 识别 `.exr` 扩展名。
2. `.exr` 保存时强制 `saving_cctf_encoding=False`。
3. `save_image_oiio()` 文档注释更新，明确 PNG/JPEG 是 SDR 输出，EXR 保留浮点范围。
4. 可选：`save_image_oiio()` 为 EXR 设置更多 metadata：
   - `chromaticities` 已有。
   - 可考虑 `spec.attribute("oiio:ColorSpace", color_space)`。
   - 可考虑 `spec.attribute("whiteLuminance", 1.0)`，但这需要团队先定义 `1.0` 的语义。OpenEXR 中 `1.0` 通常不代表裁切上限。

验收：

- 保存 EXR 时，如果输入浮点图有 `4.0`，读回仍为 `4.0`。
- 保存 PNG/JPEG 时仍裁到 SDR。

### 第 5 步：测试和回归

建议新增测试：

```python
def test_save_exr_preserves_values_above_one(tmp_path):
    image = np.array([[[0.25, 1.5, 4.0]]], dtype=np.float32)
    path = tmp_path / "hdr.exr"

    save_image_oiio(str(path), image, bit_depth=32, color_space="ACES2065-1")
    loaded = load_image_oiio(str(path))

    np.testing.assert_allclose(loaded[..., :3], image, rtol=0, atol=1e-6)
    assert np.max(loaded) > 1.0
```

建议新增 scanning 裁切单元测试：

```python
def test_scanning_output_can_disable_highlight_clip():
    io = SimpleNamespace(
        output_cctf_encoding=False,
        output_color_space="ACES2065-1",
        output_clip_min=True,
        output_clip_max=False,
    )
    stage = object.__new__(ScanningStage)
    stage._io = io

    rgb = np.array([[[-0.1, 0.5, 2.0]]], dtype=np.float64)
    out = stage._apply_cctf_encoding_and_clip(rgb)

    np.testing.assert_allclose(out, [[[0.0, 0.5, 2.0]]])
```

建议新增 GUI metadata 测试：

```python
def test_simulation_result_records_linear_hdr_encoding_flag(...):
    ...
    params.io.output_cctf_encoding = False
    result = execute_simulation_request(...)
    assert result.output_cctf_encoding is False
```

建议新增端到端验收脚本或测试：

1. 使用高光输入图，例如小图中一块 `rgb=[8, 8, 8]`。
2. 关闭 auto exposure 或固定 exposure，开启 HDR EXR 输出。
3. 输出色彩空间设为 `ACES2065-1` 或 `ITU-R BT.2020`。
4. 保存 `.exr`。
5. 用 `load_image_oiio()` 或 `oiiotool --stats` 检查 `max > 1.0`。

## 推荐用户操作流程

实现完成后，推荐 GUI 用户这样使用：

1. 输入文件使用线性 scene-referred TIFF/EXR，或 RAW 导入后避免过早 tone mapping。
2. `Output color space` 选择 `ACES2065-1`、`ITU-R BT.2020` 或 `ProPhoto RGB`。
3. 开启 `HDR EXR output`。
4. `Saving color space` 和 `Output color space` 保持一致，减少保存时二次转换。
5. 保存文件扩展名使用 `.exr`。
6. 在下游软件里按 scene-linear/HDR 工作流查看，预览时需要显示变换或 tone mapping，不能直接用普通 SDR 查看器判断亮度。

## 风险和注意事项

### 预览不是 HDR

napari 预览仍会把图像裁到 `0..1` 并转 `uint8`。这不影响 EXR 保存，因为保存优先使用 output layer 的浮点 metadata。预览看不到大于 `1.0` 的差异是预期行为。

### CCTF 必须谨慎

HDR EXR 应写线性数据。若保存时 `saving_cctf_encoding=True`，高光值可能被显示传递函数改写，甚至在某些色彩空间函数里出现不可预期行为。建议 `.exr` 保存强制 `saving_cctf_encoding=False`。

### 白黑校正可能压高光

如果启用 `scan_white_correction`，当前 `ColorReferenceService` 会把 Y 裁到 `0..1`。HDR 模式必须同步修改这里，否则即使扫描末端不裁切，高光也可能在校正阶段被压掉。

### 大于 1 不一定自然出现

取消裁切只是必要条件，不保证任何输入都会产生 `>1`。如果输入、曝光、print/scanner 参数最终都落在纸白以下，输出仍可能小于等于 `1`。验收应该使用明确的高光输入和参数组合。

### 宽色域转换可能产生负值

线性宽色域转换中，某些 out-of-gamut 颜色可能出现负通道。第一阶段建议保留 `output_clip_min=True`，只开放高光上限。如果后续要做更严格的色彩科学或 ACES pipeline，可以再增加“是否保留负值”的高级选项。

## 最小代码改动清单

第一阶段最小闭环：

1. `IOParams` 加 `output_clip_min=True`、`output_clip_max=True`。
2. `ScanningStage._apply_cctf_encoding_and_clip()` 按参数裁切。
3. `ColorReferenceService._correction_fucntion()` 按参数裁切。
4. GUI 增加 `hdr_exr_output`，映射到：
   - `params.io.output_cctf_encoding = False`
   - `params.io.output_clip_min = True`
   - `params.io.output_clip_max = False`
5. `SimulationResult` 和 output layer metadata 记录真实 `output_cctf_encoding`。
6. `.exr` 保存强制线性，即 `saving_cctf_encoding=False`。
7. 新增 EXR round-trip 测试和扫描裁切测试。

完成这组改动后，`save_image_oiio()` 已有的 EXR float 写入能力就可以真正发挥作用，EXR 输出将能保留大于 `1.0` 的 HDR 值。
