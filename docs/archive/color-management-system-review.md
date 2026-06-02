# SpektraFilm 色彩管理系统代码审查与整改方案

审查日期：2026-05-07

本文审查范围覆盖运行时色彩管线、RAW/普通图片导入、GUI 预览、显示变换、输出保存与元数据写入。结论基于当前代码、已有测试、`ISSUE_color_space_metadata.md`，以及官方/权威文档中的色彩管理实践。

## 结论概览

项目的核心方向是对的：仿真内部主要使用浮点线性 RGB 和光谱/XYZ 计算，输入输出色彩空间也已经暴露给 GUI。当前最需要补齐的是“色彩数据契约”，也就是每一张图像必须同时携带：

- RGB 色彩空间，例如 `sRGB`、`Display P3`、`ProPhoto RGB`、`ACES2065-1`
- 传递函数状态，例如线性还是已 CCTF 编码
- 数据用途，例如场景线性数据、显示预览数据、文件保存数据
- 文件元数据，例如 ICC、EXR chromaticities、OpenImageIO `oiio:ColorSpace`
- 是否允许负值或大于 1 的高动态范围值

现在代码里这些信息分散在 `IOParams`、GUI state、napari layer metadata 和保存函数参数里，缺少统一校验。因此有些路径已经“看起来能工作”，但遇到宽色域、线性 PNG/JPEG、ACES、EXR 或非 sRGB 显示器时仍会出现错误解释、过早裁剪或错误预览。

优先级最高的整改顺序是：

1. 修正内部中灰/自动平衡参考色彩空间不一致的问题。
2. 为保存输出建立“色彩空间 + 传递函数 + 文件格式”的兼容性检查。
3. 为 PNG/JPEG/EXR 增加真实文件元数据测试，而不仅是 mock 调用测试。
4. 去掉显示变换中的 sRGB 瓶颈，让 Display P3 等宽色域直接从源 ICC 转到显示器 ICC。
5. 让普通图片导入读取并回填 ICC/EXR chromaticities，而不是完全依赖用户手选。
6. 把输出裁剪从仿真核心移到显示/整数保存边界。

## 当前代码地图

运行时参数在 `src/spektrafilm/runtime/params_schema.py` 中定义：

- `IOParams.input_color_space` 默认 `ProPhoto RGB`
- `IOParams.input_cctf_decoding` 默认 `False`
- `IOParams.output_color_space` 默认 `sRGB`
- `IOParams.output_cctf_encoding` 默认 `True`

GUI 将状态映射到运行时参数的位置是 `src/spektrafilm_gui/params_mapper.py`：

- 输入色彩空间和输入 CCTF 由 GUI 传入运行时。
- 输出色彩空间由 GUI 传入运行时。
- `params.io.output_cctf_encoding = True` 被强制固定，这意味着 GUI 仿真结果总是按输出色彩空间做 CCTF 编码。

运行时主链路在 `src/spektrafilm/runtime/pipeline.py`：

1. `_preprocess()` 将输入转成 `np.double`，执行自动曝光，裁切/缩放。
2. `FilmingStage.expose()` 将 RGB 转为胶片三通道 raw exposure。
3. `PrintingStage.expose()` 用负片/正片密度和放大机光源曝光相纸。
4. `ScanningStage.scan()` 把胶片或相纸密度转 XYZ，再转输出 RGB。

I/O 相关逻辑主要在：

- `src/spektrafilm/utils/io.py`：普通图片读写、ICC profile bytes、EXR chromaticities、EXIF/IPTC/XMP 复制。
- `src/spektrafilm/utils/raw_file_processor.py`：RAW 导入、白平衡、ACES 中间空间、lensfun 校正、输出色彩空间转换。
- `src/spektrafilm_gui/controller_runtime.py`：输入预览、输出预览、显示 profile 变换。
- `src/spektrafilm_gui/controller.py`：RAW/文件加载、保存输出、把 layer metadata 用作保存源信息。

## 已经做得好的部分

- 运行时用 `colour-science` 做 RGB/XYZ/RGB 转换，而不是手写矩阵。
- RAW 导入使用 `rawpy.postprocess(gamma=(1, 1), no_auto_bright=True, output_bps=16)`，这符合“导入线性、关闭自动亮度”的方向。
- 保存代码已经有 `_ICC_PROFILES`，并且已把标准 ICC 文件打包到 `src/spektrafilm/data/icc/`。
- `save_image_oiio(..., color_space=...)` 当前会对 PNG/JPEG 写 ICC，对 EXR 写 `chromaticities`。
- GUI 输出 layer 会记录 `pipeline_float_output`、`pipeline_output_color_space`、`pipeline_output_cctf_encoding`，保存时不会盲目使用显示用 uint8 layer。
- 已有 GUI 测试覆盖“保存时是否按 layer metadata 做色彩空间转换”的逻辑。

## 主要问题

### P0：中灰/打印平衡参考硬编码走了默认 sRGB 路径

位置：`src/spektrafilm/runtime/stages/filming.py`

`_compute_density_spectral_midgray_to_balance_print()` 使用 `rgb_midgray = [[[0.184, 0.184, 0.184]]]` 作为中灰，再调用 `_simple_rgb_to_density_spectral()`。但 `_simple_rgb_to_density_spectral()` 内部调用 `_rgb_to_film_raw(rgb)` 时没有传入当前 `self._io.input_color_space` 和 `self._io.input_cctf_decoding`，于是落回 `_rgb_to_film_raw()` 的默认参数 `color_space="sRGB"` 和 `apply_cctf_decoding=False`。

这会造成一个隐藏不一致：真实输入曝光按 GUI 选定的 input color space 计算，但打印平衡参考中灰按线性 sRGB 计算。对 sRGB/D65、ProPhoto/D50、ACES AP0 这样的不同白点和不同原色，虽然 RGB 数字都是中性 `[0.184, 0.184, 0.184]`，其 XYZ 白点和经过 chromatic adaptation 后的光谱重建不一定等价。结果可能表现为不同输入色彩空间下打印平衡、曝光补偿或色偏不稳定。

应该做：

```python
raw = self._rgb_to_film_raw(
    rgb,
    color_space=self._io.input_color_space,
    apply_cctf_decoding=self._io.input_cctf_decoding,
)
```

更稳妥的做法是新增一个明确概念：`reference_midgray_encoding`。如果业务上确实希望“打印中灰永远按某个参考观测条件定义”，就不要依赖 `_rgb_to_film_raw()` 默认值，而是在参数中显式写出参考空间、参考白点和传递函数。

验收测试：

- 在 `tests/test_filming_stage.py` 增加测试，mock `_rgb_to_film_raw()`，断言 `_simple_rgb_to_density_spectral()` 传入当前 `IOParams` 的 input color space/CCTF。
- 增加集成测试：同一线性中性灰图，在 `sRGB`、`ProPhoto RGB`、`ACES2065-1` 输入设置下，输出中性轴不应出现不可解释的色偏跳变。

### P0：显示变换先压到 sRGB，宽色域预览会被提前裁剪

位置：`src/spektrafilm_gui/controller_runtime.py`

当前 `apply_display_transform()` 的路径是：

1. `colour.RGB_to_RGB(image_data, output_color_space, "sRGB", apply_cctf_encoding=True)`
2. 转成 uint8 sRGB。
3. 用 Pillow ImageCms 从 sRGB profile 转到当前显示器 profile。

这有一个明显瓶颈：如果输出色彩空间是 `Display P3`，但显示器本身也是 P3 或更宽，当前代码仍然先把图像压进 sRGB，再转显示器。超出 sRGB 的颜色会在 uint8 化前被裁掉或压扁，宽色域输出在预览阶段失去意义。

应该做：

- 对 `sRGB`、`Display P3`、`Adobe RGB (1998)`、`ProPhoto RGB`、`ITU-R BT.2020` 等 ICC 可描述空间，直接用“输出色彩空间 ICC -> 显示器 ICC”的变换。
- 在进入 ImageCms 前，只做该输出空间自己的 CCTF 编码，不要统一转 sRGB。
- 如果输出是 `ACES2065-1` 或其它 scene-linear 空间，不应直接 ICC 到显示器。应走 view transform，例如 OCIO/ACES 输出变换，再交给显示器 ICC。

建议实现：

```python
source_profile = source_profile_for_color_space(output_color_space)
encoded_for_source_profile = encode_for_icc_profile(image_data, output_color_space)
source_image = PILImage.fromarray(to_uint8(encoded_for_source_profile), mode="RGB")
display_image = ImageCms.profileToProfile(
    source_image,
    source_profile,
    display_profile,
    outputMode="RGB",
)
```

验收测试：

- 在 `tests/gui/test_controller_output.py` 增加 Display P3 预览测试：`ImageCms.profileToProfile()` 的 source profile 不应是硬编码 sRGB。
- 构造一个 Display P3 内但 sRGB 外的红/绿测试色，开启 display transform 时不应在转换到显示 profile 前被 sRGB 裁剪。

### P1：保存逻辑写入了色彩元数据，但没有校验传递函数与文件格式是否匹配

位置：`src/spektrafilm/utils/io.py`、`src/spektrafilm_gui/controller.py`

当前 `save_image_oiio()` 支持 `color_space` 参数：

- PNG/JPEG：通过 Pillow `icc_profile` 写 ICC。
- EXR：写 `chromaticities`。

我用临时文件做了轻量验证：

- `Display P3` JPEG 确实有 ICC，读取到约 536 bytes。
- `Display P3` EXR 确实有 `chromaticities`，但没有 `oiio:ColorSpace`。

问题在于，保存函数只知道 `color_space`，不知道这张图是线性的还是 CCTF 编码的。于是可能发生这些错误：

- 用户保存 `saving_cctf_encoding=False` 的 Display P3 PNG/JPEG，文件却嵌入标准 Display P3 ICC。很多软件会把它当作标准 Display P3 编码图像显示，线性数据会变暗。
- 用户选择 `ACES2065-1` 保存 PNG/JPEG，当前 `_ICC_PROFILES` 没有 ACES ICC，结果会保存无 ICC 的 8-bit 图像。
- EXR 只写 `chromaticities`，没有写 `oiio:ColorSpace`，下游无法知道更高层语义。
- PNG 路径总是转 `uint8`，而代码注释写的是 16-bit PNG I/O。高质量胶片仿真输出被降到 8-bit。

应该做：

1. `save_image_oiio()` 不再只接收 `color_space`，而是接收一个完整 encoding 对象：

```python
@dataclass(frozen=True)
class ColorEncoding:
    color_space: str
    transfer: Literal["linear", "cctf"]
    role: Literal["scene", "display"]
```

2. 保存前做兼容性检查：

- JPEG：只允许 `transfer="cctf"` 的显示/输出空间。JPEG 不适合作为线性 HDR/scene-linear 容器。
- PNG：默认只允许 `transfer="cctf"`，除非项目提供了明确的 linear ICC profile。
- EXR：默认推荐 `transfer="linear"`，保留 float/half，不裁剪，写 chromaticities 和 `oiio:ColorSpace`。

3. 如果用户选择了不兼容组合，GUI 应阻止保存或给出明确状态：

- “Linear Display P3 cannot be tagged with the standard Display P3 ICC. Enable Saving CCTF encoding or choose EXR.”
- “ACES2065-1 PNG/JPEG export is disabled unless an ACES ICC/profile policy is added. Use EXR.”

4. PNG 增加 16-bit 保存：

```python
img_uint16 = np.clip(image_data, 0, 1) * 65535.0
pil_image = PIL.Image.fromarray(img_uint16.astype(np.uint16), mode="RGB")
```

实际 Pillow 对 RGB 16-bit PNG 的模式支持需要单独验证；如果 Pillow 路径不可行，可继续用 OpenImageIO 写像素，再用 Pillow 或 OIIO 写 ICC，但必须有测试确认 ICC 没丢。

验收测试：

- `tests/test_image_io_color_metadata.py::test_jpeg_embeds_display_p3_icc`
- `tests/test_image_io_color_metadata.py::test_exr_writes_chromaticities_and_oiio_colorspace`
- `tests/test_image_io_color_metadata.py::test_linear_png_without_linear_icc_is_rejected`
- `tests/test_image_io_color_metadata.py::test_png_16bit_path_preserves_depth`
- 保存后再调用 `write_image_metadata()`，确认 ICC profile 没被 exiv2 写元数据步骤移除。

### P1：普通图片导入不读取 ICC/EXR 色彩元数据

位置：`src/spektrafilm/utils/io.py`、`src/spektrafilm_gui/controller.py`

`load_image_oiio()` 读取像素和 bit depth，但没有读取：

- ICC profile
- OpenEXR `chromaticities`
- OpenImageIO `oiio:ColorSpace`
- CICP / nclx 等色彩标识

GUI 当前完全依赖用户手动选择 `input_color_space` 和 `apply_cctf_decoding`。这对手工工作流可以接受，但不应作为默认色彩管理策略。尤其 README 推荐用户导入 16/32-bit TIFF/EXR、linear ProPhoto 或 linear Rec2020，项目应至少能读到文件自带 profile 并提示/回填。

应该做：

1. 新增数据结构：

```python
@dataclass(frozen=True)
class ImagePayload:
    pixels: np.ndarray
    color_encoding: ColorEncoding | None
    source_metadata: ImageMetadata | None
```

2. 将 `load_image_oiio()` 拆成：

- `read_image_pixels_oiio(path) -> np.ndarray`
- `read_image_color_metadata(path) -> ColorEncoding | None`
- `load_image_payload(path) -> ImagePayload`

3. 读取优先级建议：

- 如果有 ICC，先解析或映射到项目支持的 RGBColorSpaces。
- 如果是 EXR 且有 `oiio:ColorSpace`，优先使用它。
- 如果只有 `chromaticities`，尝试匹配到已知 colour-science 色彩空间，否则记录 primaries/whitepoint，提示“unknown RGB chromaticities”。
- 如果无元数据，沿用 GUI 选择，但状态栏提示“no color metadata, using selected input color space”。

4. GUI 加载图片后：

- 若文件 metadata 与当前 GUI 输入设置一致，直接加载。
- 若 metadata 可识别但与 GUI 设置不同，默认更新 GUI 输入设置，或至少状态栏提示。
- 对 EXR/float 文件默认假设 `transfer="linear"`，对 JPEG/PNG 默认假设 `transfer="cctf"`，但优先服从 ICC/CICP。

验收测试：

- 构造带 sRGB ICC 的 PNG，加载后 payload encoding 为 `sRGB + cctf`。
- 构造带 Display P3 ICC 的 JPEG，加载后 GUI input color space 自动变为 `Display P3`。
- 构造带 EXR chromaticities 的 EXR，加载后 payload encoding 能匹配 `Display P3` 或 `ACES2065-1`。
- 构造无元数据文件，确保保持旧行为但给出状态提示。

### P1：扫描输出过早裁剪，文件保存与调试路径失去越界信息

位置：`src/spektrafilm/runtime/stages/scanning.py`

`ScanningStage.scan()` 最后调用 `_apply_cctf_encoding_and_clip()`，无论输出是否线性，都会 `np.clip(rgb, 0, 1)`。这对 GUI 显示和 JPEG/PNG 保存是安全的，但对 EXR、ACES、调试、色域分析和未来 HDR/scene-linear 输出不够好。

问题：

- RGB 转换后出现负值或大于 1 值，可能意味着目标色域不足、白点适配异常或 glare/校正造成高亮越界。当前会直接抹掉证据。
- 如果保存 EXR，本来可以保留浮点越界信息，当前在运行时已丢失。
- 测试只验证“输出 bounded”，没有验证“哪里应该 bounded，哪里不应该 bounded”。

应该做：

- 将运行时输出分为 `render_rgb` 和 `display_rgb`。
- `ScanningStage` 默认返回未裁剪的 float RGB，但带上统计信息：min/max、负值比例、大于 1 比例。
- GUI 显示路径负责裁剪到 0..1 并转 uint8。
- JPEG/PNG 保存路径负责裁剪或做 gamut mapping。
- EXR 保存路径默认不裁剪。

为了兼容当前测试，可以分阶段做：

1. 先新增 `IOParams.clip_output: bool = True`，默认保持旧行为。
2. EXR 保存或高级 API 可以设置 `clip_output=False`。
3. 长期把默认行为改成“核心不裁剪，边界裁剪”。

验收测试：

- 当前 pipeline smoke tests 保持通过。
- 新增测试：`clip_output=False` 时，构造会产生超 1 RGB 的输入，输出保留超 1 值。
- GUI preview/save JPG 仍输出 uint8 bounded 图像。

### P2：光谱上采样对负值/越界/非物理 RGB 缺少显式策略

位置：`src/spektrafilm/utils/spectral_upsampling.py`

`_rgb_to_tc_b()` 把 RGB 转 XYZ，再用 `xy = np.clip(xy, 0, 1)` 限制 chromaticity。`rgb_to_raw_mallett2019()` 会对转换到线性 sRGB 的 `lrgb` 做 `np.clip(lrgb, 0, None)`。

这种“静默修正”对避免崩溃有用，但不利于色彩管理：

- 宽色域或白点转换可能产生小的负 RGB，这可能只是矩阵转换的正常副产物，也可能是输入色彩空间声明错了。
- 超出光谱重建 LUT 支持范围的颜色被直接夹到边界，可能造成饱和色 hue shift。
- 用户和测试都看不到有多少像素被修正。

应该做：

新增 `SpectralInputPolicy`：

```python
@dataclass(frozen=True)
class SpectralInputPolicy:
    negative_rgb: Literal["clip", "warn", "error", "compress"]
    xy_out_of_bounds: Literal["clip", "warn", "error"]
    report_stats: bool = True
```

运行时默认可以先用 `warn+clip` 保持兼容；批处理和测试可用 `error` 模式抓错。

验收测试：

- 输入包含小负值时，默认模式记录 stats，不崩溃。
- `error` 模式下小负值/越界 xy 抛出可读异常。
- LUT 边界行为有单元测试，不再只靠 `np.clip` 隐式通过。

### P2：RAW 导入的“输出编码开关”命名容易误导

位置：`src/spektrafilm_gui/controller.py`、`src/spektrafilm/utils/raw_file_processor.py`

GUI 调用 RAW 导入时：

```python
output_colorspace=gui_state.input_image.input_color_space
output_cctf_encoding=gui_state.input_image.apply_cctf_decoding
```

这在逻辑上是自洽的：如果 pipeline 输入设置为“需要 CCTF decoding”，RAW 导入就把数据编码到该 CCTF；如果 pipeline 输入设置为“不需要 decoding”，RAW 导入就输出线性数据。

问题只是命名和 UI 心智负担很大。`apply_cctf_decoding` 是运行时输入解释方式，而传给 RAW 导入的却是 `output_cctf_encoding`。这很容易让后续维护者误改。

应该做：

- 在 GUI 层增加中间变量名：

```python
raw_output_should_be_cctf_encoded = gui_state.input_image.apply_cctf_decoding
```

- 或把 GUI 字段改名为 `input_transfer`，取值 `linear` / `cctf_encoded`。
- 状态栏显示 RAW 导入结果：`Loaded RAW as linear ProPhoto RGB` 或 `Loaded RAW as CCTF-encoded sRGB`。

验收测试：

- 保持当前 `tests/test_raw_file_processor.py`。
- 增加 GUI flow 测试，断言状态或 payload encoding 明确记录 RAW 输出 transfer。

## 搜索到的最佳实践

本次参考的官方/权威资料：

- ICC 的核心任务是让文件和设备通过 profile 描述色彩解释方式；跨应用交换图像时应嵌入或保留 ICC profile，而不是只依赖文件名或 UI 设置。[International Color Consortium](https://www.color.org/index.xalter)
- Pillow 在保存图像时支持 `icc_profile` 参数，ImageCms 基于 LittleCMS 做 profile transform，并提供显示 profile 获取和 `profileToProfile()`。[Pillow Image file formats](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html)、[Pillow ImageCms](https://pillow.readthedocs.io/en/latest/reference/ImageCms.html)
- OpenEXR 标准属性中有 `chromaticities`，用于记录 RGB primaries 和 white point；EXR 是更适合线性浮点影像交换的格式。[OpenEXR Standard Attributes](https://openexr.com/en/latest/StandardAttributes.html)
- OpenImageIO 定义了 `oiio:ColorSpace`、`ICCProfile`、`chromaticities`、CICP 等标准元数据名，建议在读写时统一使用这些字段。[OpenImageIO Standard Metadata](https://openimageio.readthedocs.io/en/latest/stdmetadata.html)
- `colour-science` 的 `RGB_to_RGB`/`RGB_to_XYZ`/`XYZ_to_RGB` 支持显式 CCTF encode/decode 和 chromatic adaptation，项目应显式指定这些参数并集中封装。[colour-science API](https://colour.readthedocs.io/en/develop/generated/colour.RGB_to_RGB.html)
- rawpy/LibRaw 的线性 RAW 导入应关闭自动亮度并使用线性 gamma；项目当前 `gamma=(1, 1)`、`no_auto_bright=True` 的方向是合理的。[rawpy API](https://letmaik.github.io/rawpy/api/rawpy.Params.html)
- OpenColorIO/ACES 的核心实践是把 scene-linear 数据和 display/view transform 分开；ACES/scene-linear 不应被当作普通显示 ICC 图像直接预览或保存为 JPEG。[OpenColorIO Documentation](https://opencolorio.readthedocs.io/en/latest/)、[ACES Documentation](https://docs.acescentral.com/)
- napari 的 layer 显示适合科学可视化，但不是完整色彩管理系统；项目 README 也已说明 napari 不 color-managed。因此 SpektraFilm 应自己完成源 profile 到显示 profile 的预览变换，或明确提示降级路径。[napari Image layer guide](https://napari.org/stable/howtos/layers/image.html)

落到本项目，最佳实践可以总结成一句话：

> 仿真核心只处理明确声明的线性浮点颜色；显示和文件输出是两个不同边界，必须分别做 view/display transform 和文件 profile/metadata 写入。

## 目标架构

建议新增一个小而集中、无 GUI 依赖的模块：

`src/spektrafilm/color_management.py`

核心类型：

```python
from dataclasses import dataclass
from typing import Literal

Transfer = Literal["linear", "cctf"]
ColorRole = Literal["scene", "display", "interchange"]

@dataclass(frozen=True)
class ColorEncoding:
    color_space: str
    transfer: Transfer
    role: ColorRole = "scene"
    allow_unbounded: bool = False

@dataclass(frozen=True)
class ColorMetadata:
    encoding: ColorEncoding
    icc_profile: bytes | None = None
    chromaticities: tuple[float, ...] | None = None
    oiio_color_space: str | None = None
```

核心函数：

```python
def validate_color_space(name: str) -> None: ...
def rgb_to_rgb(data, source: ColorEncoding, target: ColorEncoding) -> np.ndarray: ...
def resolve_icc_profile_bytes(encoding: ColorEncoding) -> bytes | None: ...
def chromaticities_for(encoding: ColorEncoding) -> tuple[float, ...] | None: ...
def ensure_save_compatible(encoding: ColorEncoding, extension: str) -> None: ...
def infer_encoding_from_oiio_spec(spec) -> ColorEncoding | None: ...
```

设计约束：

- `ColorEncoding.transfer="linear"` 表示数字值已经是线性光/场景量，不应贴标准显示 ICC，除非有对应 linear ICC。
- `ColorEncoding.transfer="cctf"` 表示数字值按该 RGB 色彩空间的 CCTF 编码，适合 PNG/JPEG + 标准 ICC。
- `role="scene"` 的 ACES/ProPhoto/Rec2020 可用于仿真输入和 EXR 交换；`role="display"` 的 sRGB/Display P3 可用于 GUI 预览和 JPEG/PNG。
- `allow_unbounded=True` 只应出现在 float/EXR/内部 buffer，不能用于 JPEG。

## 逐步整改方案

### 第 1 步：建立统一色彩契约

改动文件：

- 新增 `src/spektrafilm/color_management.py`
- 更新 `src/spektrafilm/runtime/params_schema.py`
- 更新 `src/spektrafilm_gui/options.py`
- 更新 `src/spektrafilm_gui/state.py`

怎么做：

1. 保留现有 `input_color_space`、`input_cctf_decoding`、`output_color_space`、`output_cctf_encoding` 字段，先不要破坏兼容。
2. 增加 helper，把旧字段转换为 `ColorEncoding`：

```python
def input_encoding_from_io(io: IOParams) -> ColorEncoding:
    return ColorEncoding(
        color_space=io.input_color_space,
        transfer="cctf" if io.input_cctf_decoding else "linear",
        role="scene",
        allow_unbounded=True,
    )

def output_encoding_from_io(io: IOParams) -> ColorEncoding:
    return ColorEncoding(
        color_space=io.output_color_space,
        transfer="cctf" if io.output_cctf_encoding else "linear",
        role="display" if io.output_cctf_encoding else "scene",
        allow_unbounded=not io.output_cctf_encoding,
    )
```

3. 所有新代码只传 `ColorEncoding`，旧字段只作为 UI 和兼容 API。
4. 给 GUI 文案补一个更明确的 tooltip：

- `Input transfer`: `linear` / `encoded`
- `Saving transfer`: `linear EXR` / `encoded image`

验收：

- 旧测试不需要大改。
- 新增 `tests/test_color_management.py` 验证旧字段到新 encoding 的映射。

### 第 2 步：修复中灰参考色彩空间

改动文件：

- `src/spektrafilm/runtime/stages/filming.py`
- `tests/test_filming_stage.py`

怎么做：

1. 修改 `_simple_rgb_to_density_spectral()`，传入当前 input encoding。
2. 如果业务上希望固定参考中灰，请新增参数，而不是使用 `_rgb_to_film_raw()` 默认值。
3. 在测试里 mock `_rgb_to_film_raw()`，确认 color space 和 CCTF 参数被传递。

建议 patch 形态：

```python
def _simple_rgb_to_density_spectral(self, rgb: np.ndarray) -> np.ndarray:
    raw = self._rgb_to_film_raw(
        rgb,
        color_space=self._io.input_color_space,
        apply_cctf_decoding=self._io.input_cctf_decoding,
    )
    ...
```

风险：

- 这可能改变默认输出，尤其默认 GUI 输入是 `ProPhoto RGB` 而旧参考实际是 sRGB。需要更新 regression baselines。
- 如果历史 look 是按 sRGB 中灰调出来的，可以临时加兼容开关，但应默认使用一致契约。

### 第 3 步：完善保存格式和元数据

改动文件：

- `src/spektrafilm/utils/io.py`
- `src/spektrafilm_gui/controller.py`
- `src/spektrafilm_gui/widget_sections.py`
- 新增 `tests/test_image_io_color_metadata.py`

怎么做：

1. 将 `save_image_oiio(filename, image_data, bit_depth=32, *, color_space=None)` 扩展为：

```python
def save_image(
    filename: str,
    image_data: np.ndarray,
    *,
    encoding: ColorEncoding,
    bit_depth: int | None = None,
) -> None:
    ensure_save_compatible(encoding, suffix)
    ...
```

2. 保存兼容矩阵：

| 格式 | 推荐 transfer | 推荐 bit depth | 元数据 |
| --- | --- | --- | --- |
| JPEG | `cctf` | 8-bit | ICC |
| PNG | `cctf` | 16-bit 优先，8-bit 可选 | ICC |
| EXR | `linear` | half/float | chromaticities + `oiio:ColorSpace` |

3. 对不兼容组合抛 `ValueError`，由 GUI 捕获并弹出错误。
4. EXR 写入：

```python
spec.attribute("chromaticities", oiio.TypeDesc("float[8]"), chromaticities)
spec.attribute("oiio:ColorSpace", oiio_color_space_token)
```

5. PNG/JPEG 写入：

```python
icc_bytes = resolve_icc_profile_bytes(encoding)
if icc_bytes is None:
    raise ValueError(...)
pil_image.save(filename, icc_profile=icc_bytes, ...)
```

6. 保存后复制 EXIF/IPTC/XMP 时，增加回归测试确认 ICC 仍在。

短期兼容做法：

- 保留旧 `save_image_oiio(... color_space=...)`，内部转换为 `ColorEncoding(color_space, "cctf")`。
- GUI 当前 `saving_cctf_encoding` 为 True 时行为保持；为 False 且格式非 EXR 时提示用户。

### 第 4 步：让显示变换直接使用源 ICC

改动文件：

- `src/spektrafilm_gui/controller_runtime.py`
- `src/spektrafilm/utils/io.py` 或新 `color_management.py`
- `tests/gui/test_controller_output.py`

怎么做：

1. 新增 `source_profile_for_display_transform(output_encoding)`。
2. 如果输出 encoding 是标准显示 RGB 且有 ICC：

- 不转 sRGB。
- 按自身 CCTF 编码。
- 用自身 ICC 作为 source profile。
- `profileToProfile(source_profile, display_profile)`。

3. 如果输出 encoding 是 ACES/scene-linear：

- 短期：用明确的 fallback 状态，例如 `Display transform: ACES output uses sRGB preview fallback`。
- 中期：引入 OCIO config，做 ACES view transform 到 sRGB/Display P3，再交给显示器 ICC。

4. `prepare_output_display_image()` 保留无 display profile 时的安全 fallback，但状态文案要说明“raw preview is not color managed”。

验收：

- Display P3 输出开启 display transform 时，测试确认 source profile 是 Display P3，不是 sRGB。
- sRGB 输出仍可走原路径或直接 sRGB profile。
- 无显示 profile 时不会崩溃，状态栏清楚。

### 第 5 步：读取输入文件色彩元数据

改动文件：

- `src/spektrafilm/utils/io.py`
- `src/spektrafilm_gui/controller.py`
- `tests/test_image_io_color_metadata.py`
- `tests/gui/test_controller_flow.py`

怎么做：

1. 新增 `read_image_color_metadata(filename)`。
2. 通过 OIIO `ImageInput.spec()` 读取：

- `ICCProfile`
- `oiio:ColorSpace`
- `chromaticities`
- CICP 相关属性

3. 实现匹配逻辑：

```python
def match_chromaticities_to_known_space(chroma, tolerance=1e-4) -> str | None:
    ...
```

4. `load_input_image()` 改为读取 payload：

```python
payload = load_image_payload(path)
image = payload.pixels[..., :3]
if payload.color_encoding is not None:
    apply_detected_input_encoding_to_gui(payload.color_encoding)
```

5. 如果 metadata 不可识别：

- 保持旧行为。
- 状态栏提示当前使用 GUI 选择。

验收：

- 加载带 ICC 的 Display P3 JPEG 后，GUI input color space 更新为 `Display P3`。
- 加载 EXR chromaticities 后，GUI 能识别对应空间或显示“unknown chromaticities”。
- 无 metadata 文件路径仍兼容。

### 第 6 步：拆分运行时输出裁剪与显示裁剪

改动文件：

- `src/spektrafilm/runtime/params_schema.py`
- `src/spektrafilm/runtime/stages/scanning.py`
- `src/spektrafilm_gui/controller_runtime.py`
- `tests/test_pipeline_smoke.py`

怎么做：

1. 增加 `IOParams.clip_output: bool = True`，先保持兼容。
2. `_apply_cctf_encoding_and_clip()` 拆成：

```python
def _apply_cctf_encoding(self, rgb): ...
def _clip_for_display_or_legacy(self, rgb): ...
```

3. 当 `clip_output=False` 时，运行时只 encode，不 clip。
4. GUI preview 和 JPEG/PNG 保存总是自己 clip。
5. EXR 保存默认不 clip。

验收：

- 旧 bounded tests 保持通过。
- 新增 unbounded EXR/advanced runtime test。

### 第 7 步：增加光谱输入 preflight

改动文件：

- `src/spektrafilm/utils/spectral_upsampling.py`
- `src/spektrafilm/runtime/params_schema.py`
- `tests/test_spectral_upsampling.py`

怎么做：

1. 在 RGB -> XYZ -> xy/tc 前统计：

- `rgb_min`
- `rgb_max`
- `negative_pixel_ratio`
- `xy_out_of_bounds_ratio`

2. 默认行为仍 clip，但将 stats 返回或记录到 timings/debug。
3. 高级模式可设置 `error`，用于测试/批处理。
4. 在 GUI 状态栏或日志里给出简短警告：

`Input contains 0.8% negative RGB values after color conversion; clipped for spectral upsampling.`

验收：

- 构造负值输入，默认产生 warning/stats。
- error 模式抛异常。
- 旧流程不崩。

## 建议测试矩阵

### 单元测试

- `tests/test_color_management.py`
  - 色彩空间名称校验。
  - `IOParams -> ColorEncoding` 映射。
  - 保存兼容矩阵。
  - chromaticities 与 known RGB space 匹配。

- `tests/test_image_io_color_metadata.py`
  - sRGB/Display P3/ProPhoto PNG/JPEG ICC 写入和读取。
  - EXR chromaticities 和 `oiio:ColorSpace` 写入和读取。
  - `write_image_metadata()` 后 ICC 不丢。
  - 不兼容保存组合抛出明确错误。

- `tests/test_filming_stage.py`
  - 中灰参考使用当前 input color space/CCTF。
  - input color space 改变时，参考函数参数跟随改变。

- `tests/test_spectral_upsampling.py`
  - 负值/越界策略。
  - `warn+clip` 和 `error` 模式。

### GUI 测试

- `tests/gui/test_controller_output.py`
  - Display P3 display transform 不再先用 sRGB profile。
  - 保存 `saving_cctf_encoding=False` 到 PNG/JPEG 被拒绝。
  - 保存 EXR 使用 linear encoding 并保留 float。

- `tests/gui/test_controller_flow.py`
  - 加载带 ICC 的输入图后 GUI input color space 自动回填或状态提示。
  - RAW 导入状态明确显示输出 transfer。

### 集成/回归测试

- 生成 18% 中灰、ColorChecker、P3 外 sRGB 内/外测试色。
- 比较 sRGB/Display P3/ProPhoto/ACES 输入下的中灰稳定性。
- 保存 PNG/JPEG/EXR 后用 Pillow/OIIO 读回元数据。
- 对 EXR 做不裁剪 round trip。

## 推荐实施顺序

第一批，小改但收益高：

1. 修复 `_simple_rgb_to_density_spectral()` 传参。
2. 添加真实文件 ICC/EXR metadata 测试。
3. 保存时禁止 linear PNG/JPEG 贴标准 ICC。
4. EXR 增加 `oiio:ColorSpace`。
5. 保存 PNG 至少不要注释声称 16-bit 但实际 8-bit。

第二批，架构收口：

1. 新增 `ColorEncoding`/`ColorMetadata`。
2. 将 `save_image_oiio()`、display transform、input loader 迁到统一模块。
3. GUI 引入 detected encoding 状态。

第三批，色彩专业化：

1. OCIO/ACES view transform。
2. 非裁剪 EXR/HDR 输出。
3. spectral upsampling preflight 和 gamut compression 策略。

## 兼容性和迁移

- 现有 GUI state JSON 仍保留旧字段。新增字段必须有默认值，参考 `persistence.py` 已支持 dataclass default。
- 旧 API `simulate(image, params)` 不应强制用户立刻迁移。
- `save_image_oiio(... color_space=...)` 可保留一版作为兼容 wrapper，但内部应转换到 `ColorEncoding(..., transfer="cctf")` 并在文档中标记 deprecated。
- 如果修复中灰参考导致 regression baselines 改变，应单独提交，并在变更说明中注明“旧版本中中灰参考实际固定为线性 sRGB”。

## 最终验收标准

整改完成后，应满足：

- 任意 output/saving color space 的数字转换和文件 metadata 一致。
- PNG/JPEG 不会保存未声明或错误声明的线性宽色域数据。
- EXR 能保留线性 float 数据、chromaticities 和 OpenImageIO 色彩空间标识。
- GUI Display P3 预览不会被 sRGB 中间转换提前裁剪。
- 普通图片导入能识别常见 ICC/EXR 色彩元数据，无法识别时清楚提示。
- 仿真核心的中灰参考、自动曝光、光谱上采样都使用同一套输入色彩契约。
- 测试既覆盖像素转换，也覆盖真实文件元数据，而不是只覆盖 mock 调用。
