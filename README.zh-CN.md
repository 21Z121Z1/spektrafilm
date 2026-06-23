![spektrafilm 横幅](img/readme/banner.jpg)

语言： [English](README.md) | 简体中文

> [!WARNING]
>
> **我热爱构建 spektrafilm**，已经在这个项目上投入了数百小时。现在它仍是一个夜晚和周末推进的项目。如果它能帮我支付一些账单，我就能继续为大家改进它。🙂 非常感谢任何形式的**支持**：[Buy me a coffee](https://buymeacoffee.com/andreavolpato)
>
> **2026/05/28 大规模 Git 历史清理**（140MB -> 45MB）--> 请重新 clone！
>

# 模拟摄影的光谱胶片模拟

本项目探索如何充分利用厂商数据表中的光谱测量数据，在一个端到端、基于物理并进行光谱计算的模型中，将这些数据转化为可信的胶片、相纸和扫描渲染，并支持交互式探索。

这里有一些有用链接和衍生项目：
- 项目讨论在 [discuss.pixls.us](https://discuss.pixls.us/c/software/spektrafilm/) 进行。
- 欢迎加入官方 [subreddit](https://www.reddit.com/r/spektrafilm/)。
- 一篇[高层次介绍文章](https://discuss.pixls.us/t/spectral-film-simulations-from-scratch/)可以作为理解光谱框架的温和入口。
- 投票选择你希望在 spektrafilm 中看到的[下一个胶片 stock](https://discuss.pixls.us/t/2026-q2-data-sheets-digitization-campaign/58032)。
- [hanatos](https://github.com/hanatos) 在 [vkdt](https://jo.dreggn.org/vkdt/src/pipe/modules/filmsim/readme.html) 中提供了一个极快的 Vulkan 实现。
- [Aedan](https://github.com/chaert-s) 开发了一个 [OFX 插件](https://spektrafilm.114c.de/)。
- [turbasvin](https://github.com/turbasvin) 正在开发一个快速的 [Rust 实现](https://github.com/turbasvin/spektrafilm-rs)。
- [agriggio](https://github.com/agriggio) 在 [ART](https://artraweditor.github.io/SpectralFilmSimHowto) 中提供了一个基于 LUT 的桥接方案。


在实践中，这个 Python 仓库是其他开发工作的**参考实现**，也是我继续扩展底层模型的地方。它可以从一张相机图像开始，让图像通过虚拟负片、相纸和扫描管线，并检查胶片 stock 数据、成色剂、放大机设置、颗粒、光晕以及其他摄影效应如何塑造最终结果。目标不仅是模仿一种泛泛的“胶片观感”，而是建立一个基于测量、能够预测摄影材料真实行为的模型。

![带颜色测试图像的 GUI 界面示例。](img/readme/gui_screenshot.png)

桌面 GUI 让你无需编写代码也能使用 Python 技术演示中的功能，
可以导入 RAW 文件或准备好的线性图像，探索不同胶片和相纸配置，
交互式调整模拟参数，并在较快的预览和更细致的最终扫描之间快速切换。
目前全分辨率导出非常慢。

> [!IMPORTANT]
>   spektrafilm（全部小写）开放用于研究、集成和生产用途。项目正在快速开发中，一些区域仍在构建，并且会快速变化。
>
> 如果你觉得它有用：
>  * 在插件描述、营销材料或署名中注明 spektrafilm（例如
>    “film modeling powered by `spektrafilm`” 或 “film modeling inspired by
>    `spektrafilm`”，参见 `CITATION.cff`）。
>  * 考虑给仓库点星或分享你的结果。
>  * 在学术工作中引用本仓库或 Zenodo DOI（参见 `CITATION.cff`）。
>  * 考虑[请我喝杯咖啡](https://www.buymeacoffee.com/andreavolpato)，为下一次通宵编码补充燃料 :)
>
>  *本项目使用 GPLv3 许可证*，因此任何衍生作品也必须以同一许可证开源。衍生作品包括任何包含 spektrafilm 代码，或直接受其方法启发的软件、插件或工具。
>
> *JSON 配置和 LUT 使用 CC BY-SA 4.0。*
>
>  如果 *GPLv3 与你的项目不兼容*，请联系我讨论其他选择。我非常愿意合作和集成，但我希望确保 spektrafilm 始终面向社区保持开源。
>
> LUT 使用严格的“*可商用、可自由分享、不可转售*”自定义[许可证](SPEKTRAFILM_LICENSE.txt)。
>
>  这有助于支撑开放的色彩科学。谢谢！


## 简介

该模拟从已发布的胶片 stock 数据出发，模拟负片或正片乳剂。下图展示了 Kodak Portra 400（数据表 e4050，2016）的曲线示例（注意，CMY 漫射密度是通用的，因为它们通常不会公开发布）。

![从 Kodak Portra 400 数据表提取的数据](img/readme/example_data_kodak_portra_400.png)

下一张图展示了 Kodak Portra Endura 相纸（数据表 e4021，2009）的数据示例。

![从 Kodak Ektacolor Edge 数据表提取的数据](img/readme/example_data_kodak_portra_endura.png)

左侧面板展示每个彩色层的光谱对数感光度。中间面板展示介质在参考光源下曝光于中性灰阶时，每一层的对数曝光—密度特性曲线。右侧面板展示化学显影过程中在介质上形成的染料吸收光谱。`Min` 和 `Mid` 分别表示未曝光但已冲洗介质的吸收值，以及中性灰“中间”曝光的吸收值。

从相机 RAW 文件得到的线性 RGB 数据开始，模拟会重建光谱数据，将穿过虚拟负片的光投射到相纸上，并使用带二向色滤镜的简化彩色放大机来平衡照片。最后，它会使用从相纸反射的光来扫描虚拟照片。

管线如下图所示，改编自 [^1]：![彩色摄影流程。](img/readme/pipeline_color_digital_management.png) 在这里，来自场景的光（也就是你的相机 RAW 文件）被曝光到具有特定光谱感光度的虚拟负片上；随后，化学过程通过密度曲线和更复杂的相互作用来生成染料密度，这些相互作用用于建模成色剂。虚拟负片会在特定照明体下投射到相纸上；相纸随后再次显影，但这里使用简单的密度曲线，并且在这种情况下不使用成色剂。相纸本身已经被设计为减少通道串扰，因为它不需要采样场景，只需要采样负片上的染料。

这条管线允许以物理上合理的方式加入许多特性。例如：

- 光晕
- 在负片上生成的胶片颗粒（使用随机模型）
- 对相纸进行预闪光以保留高光

根据我在胶片模拟中的实验经验，仅靠数据表曲线远远不足以复现体面的胶片观感。关键在于理解胶片乳剂包含成色剂：它们是在显影过程中与实际 CMY 染料一起产生的化学物质，对实现预期饱和度非常重要。主要成色剂包括：

- 遮罩成色剂，它会给未曝光但已冲洗的胶片带来典型的橙色。这些成色剂会在形成密度的位置被局部消耗，用来降低层吸收中的串扰影响，从而提高饱和度。遮罩成色剂的存在通过孤立染料吸收光谱中的负吸收贡献来模拟。举例来说，可参见更新后的 Portra 400 数据，其中加入了遮罩成色剂，并对印相密度特性曲线进行了反混合：![加入遮罩成色剂并反混合密度后的 Portra 400 数据。](img/readme/example_data_kodak_portra_400_couplers.png)

- 直接抑制成色剂，它们会在形成密度的位置被局部释放，并抑制相邻层或同一层中的密度形成。这会提高饱和度和反差。此外，如果允许这些成色剂在空间中扩散，它们还可以提高局部反差和感知锐度。

关于彩色成色剂的更详细描述可参见 Hunt 著作 [^2] 的第 15 章。

## 包结构

代码库在 `src/` 下组织为三个包：

1. [src/spektrafilm](src/spektrafilm)：运行时模拟管线（物理管线核心）、已处理配置的消费、GPU/HDR 辅助功能，以及工具代码。线性输入 / 线性输出，不依赖 GUI 或 LUT 创建器。
2. [src/spektrafilm_gui](src/spektrafilm_gui)：构建在运行时之上的桌面 Qt + napari GUI。
3. [src/spektrafilm_lut_creator](src/spektrafilm_lut_creator)：LUT 烘焙、QA 与 OCIO 配置输出。可在 1-LUT / 2-LUT / 3-LUT / 4-LUT 拓扑中构建 `.cube` / `.3dl` / Hald-CLUT PNG bundle，并可选输出用于管线集成的独立 OCIO 2 配置。可通过 `spektrafilm-lut` 命令行工具或 Python `BundleBuilder` API 驱动。

规范导入入口：

1. 运行时 API：
   [src/spektrafilm/runtime/api.py](src/spektrafilm/runtime/api.py)。
2. GUI 入口：[src/spektrafilm_gui/app.py](src/spektrafilm_gui/app.py)。
3. LUT bundle 构建器：
   [src/spektrafilm_lut_creator/builders.py](src/spektrafilm_lut_creator/builders.py)。

最小运行时 API：

```python
from spektrafilm import init_params, simulate

params = init_params(
    film_profile="kodak_portra_400",
    print_profile="kodak_portra_endura",
)
result = simulate(image, params)
```

最小 LUT 烘焙 API：

```python
from spektrafilm_lut_creator.builders import BundleBuilder
from spektrafilm_lut_creator.bundles import BundleSpec

spec = BundleSpec(
    film_profile="kodak_portra_400",
    print_profiles=("kodak_portra_endura",),
    input_color_space="Panasonic V-Log",
    output_color_space="sRGB",
    topology="1lut",
    resolution=33,
    ocio_config=True,   # 选择启用：同时输出一个独立 OCIO 2 配置
    qa=True,            # 选择启用：运行 QA 套件并输出 report.html
    target="lumix_realtime_vlog",  # 用于 Lumix realtime 的特殊 .cube 文件
)
builder = BundleBuilder(spec)
builder.write(builder.build())   # 输出到 build/lut_bundles/<auto-name>/
```

命令行中的等价用法如下。色彩空间接受规范注册名或 `short_tag` slug（`vlog`、`srgb`、`acescg` 等）：

```bash
spektrafilm-lut build \
    --film kodak_portra_400 \
    --print kodak_portra_endura \
    --input vlog --output srgb \
    --topology 1lut \
    --resolution 33 \
    --qa \
    --ocio-config \
    --out ./build/lut_bundles/

spektrafilm-lut list film         # 查看已注册的胶片配置
spektrafilm-lut list print        # 查看已注册的相纸配置
spektrafilm-lut list input        # 查看输入色彩空间
spektrafilm-lut list output       # 查看输出色彩空间
spektrafilm-lut list target       # 查看支持的目标（例如 lumix realtime）
```

对于复杂规格（嵌套的色域压缩设置、多相纸 bundle），可以传入 `--from spec.toml`，从 TOML 文件加载完整的 `BundleSpec`。

依赖方向：

1. `spektrafilm_gui` 依赖 `spektrafilm`。
2. `spektrafilm_lut_creator` 依赖 `spektrafilm`。
3. `spektrafilm`（运行时）不依赖任何更高层级的包。

## 文档地图

文档树有一个经过整理的路由入口：[docs/README.md](docs/README.md)。可以通过它找到当前开发报告、HDR/色彩/GPU 说明、生成的曲线分析文档、审计快照，以及归档的旧文档。

后处理效果的 MLX/Apple GPU 加速记录在 [docs/gpu/mlx-optimization-report-20260530.md](docs/gpu/mlx-optimization-report-20260530.md)。光晕和扩散使用确定性的后端滤波器/卷积；颗粒使用固定种子的确定性 MLX 采样，其一致性是统计意义上的，而不是与 CPU 像素级完全一致。

## 安装

> [!NOTE]
> spektrafilm 需要 Python 3.13 或更新版本。

目前我建议使用 `conda`+`pip` 或 `uv` 安装 spektrafilm，因为 Python 3.13 是该工作区经过测试的解释器版本线。

### 使用 `uv`

你可以使用 [uv](https://docs.astral.sh/uv/) 直接从 Git 仓库运行最新版本的 spektrafilm。默认安装现在已经包含桌面 GUI 和 LUT 创建器依赖；只有开发工具仍然是可选项：

```bash
uvx --python 3.13 --from git+https://github.com/andreavolpato/spektrafilm.git spektrafilm
```

也可以从本地工作副本运行：
```bash
uvx --python 3.13 --from /path/to/local/working_copy spektrafilm
```

或者，你可以永久安装 spektrafilm，这会提供 `spektrafilm` 命令：

```bash
uv tool install --python 3.13 git+https://github.com/andreavolpato/spektrafilm.git
```

完整开发时，请使用 `[dev]` 安装项目，在默认安装之上添加测试工具。

#### 安装 uv

在 Windows 下，可以使用以下命令安装 `uv`；该命令只需首次执行一次：
```bash
# ! 只有第一次安装 uv 时需要执行这个命令！
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```
macOS 和 Linux 的说明在[这里](https://docs.astral.sh/uv/getting-started/installation/#standalone-installer)。


### 使用 `pip`

你也可以正常使用 `pip`。默认安装已经包含 GUI 和 LUT 创建器依赖；`dev` 是唯一剩余的可选 extra。

```bash
# 安装默认包（包含桌面 app + LUT 创建器）：
git clone https://github.com/andreavolpato/spektrafilm.git
cd spektrafilm
pip install -e .

# 运行
spektrafilm
```
我建议创建一个干净的虚拟环境来安装依赖，例如使用 `conda`。

#### 使用 `conda`
在终端中：

```bash
conda create -n spektrafilm python=3.13
conda activate spektrafilm
```

进入仓库文件夹并运行以下命令安装 `spektrafilm` 包：

```bash
pip install -e .
```
激活环境后，通过以下命令启动 GUI：

```bash
spektrafilm
```
移除环境：
```bash
conda env remove -n spektrafilm
```

### 安装选项

| 安装命令 | 得到的内容 |
|---|---|
| `pip install -e .` | 默认安装：核心运行时 + GUI + LUT 创建器。提供 `spektrafilm` 和 `spektrafilm-lut` 两个命令。 |
| `pip install -e ".[dev]"` | 默认安装 + 测试工具（`pytest`、OCIO 配置验证）。 |

同样的 `[extras]` 语法也适用于 `uv pip install` 和 `uv tool install`。对于一次性 `uvx` 运行，请使用上文所示的 `--from`。

> [!NOTE]
> 在 Windows PowerShell 和 macOS zsh 中，请给方括号加引号，避免 shell glob 展开：`pip install -e ".[dev]"`。

## 测试

安装默认包和开发工具后，运行测试套件：

```bash
pip install -e ".[dev]"
python -m pytest tests -v
```

回归快照以提交的 `.npz` 文件形式存放在 `tests/baselines/` 中，并由 `tests/test_regression_baselines.py` 检查。当一次模拟变更是有意为之时，请手动重新生成快照：

```bash
python scripts/regenerate_test_baselines.py
```

pytest 运行期间绝不会自动更新快照文件。

## GUI
启动 GUI 时，会出现一个 `napari` 窗口。注意，`napari` 不进行色彩管理。我的工作方式是将屏幕和操作系统色彩配置设为 sRGB，并将模拟输出色彩空间也设为 sRGB。在 Windows 上，GUI 会尝试获取显示器配置文件并转换最终图像用于查看；如果成功，状态栏中会显示这一点。

你可以直接从 `import raw` 区域导入相机 RAW 文件。选择白平衡模式（`as shot`、`daylight`、`tungsten` 或 `custom`），在使用 `custom` 时设置色温和 tint，然后点击 `select file`。RAW 导入器使用 `rawpy`，并会把图像转换到当前的 `input color space` 和 `apply CCTF decoding` 设置。你可以使用 `reprocess raw` 重新加载同一个文件，并用新的设置重新处理。

> [!TIP]
> 将鼠标悬停在小组件和控件上，可以看到有用的提示信息。

你仍然可以通过 `file loader` 加载外部准备好的线性图像。如果你想使用完全手动的 RAW 显影工作流，或偏好在其他工具中进行预处理，这会很有用。为了获得最佳结果，请保持图像为 scene-referred 且线性，理想格式是宽色域色彩空间中的 16-bit 或 32-bit float TIFF/EXR，例如 linear Rec2020 或 linear ProPhoto RGB。

> [!IMPORTANT]
> `file loader` 使用 OpenImageIO 将 16-bit 和 32-bit 图像文件作为新图层导入。PNG、TIFF 和 EXR 已知可以工作，其他格式也可能可用。

请记住，这是一个高度实验性的项目，GUI 中暴露了许多几乎没有文档说明的控件。可以通过悬停查看控件提示，或直接探索代码。调整 `exposure_compensation_ev` 可以改变负片曝光。按下 `scan_film` 和 `PREVIEW/SCAN` 可以查看虚拟负片扫描。

如果要微调光晕，请调整 `scattering size`、`scattering strength`、`halation size` 和 `halation strength`。每个参数都有三个控件，分别定义其对三个颜色通道（RGB）的影响。`scattering size` 和 `halation size` 表示高斯模糊的 sigma 值。`scattering strength` 和 `halation strength` 表示散射或光晕光的百分比。`y filter shift` 和 `m filter shift` 是彩色放大机虚拟黄色和品红滤镜的控制项。它们表示相对于中性位置的步数偏移；中性位置也就是能让在正确参考照明体下拍摄的 18% 灰目标在最终照片中完全中性的起始设置。

管线中多个阶段都有用于施加镜头模糊的控件，例如相机镜头、彩色放大机镜头或扫描仪中。此外，还有一个用于模拟显影过程中扩散的密度模糊控件：`grain > blur`。扫描仪也通过简单的反锐化遮罩滤波器提供锐化控件。

例如，将一小块胶片裁切区域放大 12 倍后，可以看到染料云。

![带颜色测试图像的 GUI 界面示例。](img/readme/gui_grain_magnified.png)

这对我来说是最有吸引力的方面之一，尤其是当我设想打印大幅、高分辨率模拟图像，同时仍保留原始图片中不存在的这些底层颗粒细节时。

## 使用 darktable 手动准备输入图像

在 GUI 中直接导入 RAW 是最简单的工作流，但当你想更精确地控制输入渲染时，手动显影仍然很有用。

模拟期望输入线性的 scene-referred 文件，可以带有或不带有传递函数。我通常使用 [darktable](https://www.darktable.org/) 打开数码相机 RAW 文件，停用 `filmic` 或 `sigmoid` 做的非线性映射，并调整曝光以保留所有信息，同时避免裁剪。然后我将文件导出为 linear ProPhoto RGB 中的 32-bit float TIFF。

## GUI 使用示例

[观看 GUI 演示视频](https://github.com/user-attachments/assets/534746b5-87ec-4bd0-96c9-5214ef7e381b)

## 需要考虑的事项

- 对于全分辨率图像，该模拟相当慢。在我的笔记本上，处理 6MP 图像大约需要 10 秒。我通常用 `PREVIEW` 调整大多数数值。需要最终图像时，使用 `SCAN`，它会绕过图像缩放。
- 根据我构建配置时的经验，Fujifilm 数据不如 Kodak 数据自洽。

## 本 fork 的扩展工作

这个 fork 在上游 `spektrafilm` 的基础上，加入了围绕 Apple Silicon 加速、HDR 图像导出和面向显示的色彩管理的一组实验性工作。整体目标是继续以上游 SDR 胶片模拟行为作为参考路径，同时提供可选的本地加速基础设施，以及更稳健的 HDR 输出实验路径。

### Apple Silicon MLX / Metal 加速

运行时管线加入了面向 Apple Silicon 的可选 MLX 后端。默认后端仍然是 CPU，因此除非用户明确选择 GPU 计算，否则参考 SDR 路径不会改变。MLX 路径的设计目标是在可能的情况下让中间阶段数据保留在后端上，减少 spectral computation、density interpolation、LUT application、filtering、CCTF encode/decode 和矩阵色彩变换中的 CPU/GPU 往返。

当前加速工作主要集中在通过 MLX 和 Metal-backed operations 改善 Apple Silicon 上的实际渲染性能。CPU 输出仍然是主要正确性参考；GPU 路径被视为加速路径，必须在预期 float32 精度范围内保持胶片模拟语义。

CuPy 和 Halide 相关代码目前保留为实验性后端研究方向。它们不是这个 fork 的主要测试配置，不能在没有单独本地验证的情况下视为生产可用路径。

### HDR 投影与 gain-map 导出

这个 fork 加入了围绕 RouteMaster 思路展开的 HDR 工作，用于把摄影模拟 route 与最终输出投影拆分开。长期目标是只渲染一次摄影材料状态，然后从同一个状态派生 SDR 与 HDR 投影，而不是从已经渲染好的 SDR 图像重新推测 HDR 数据。

目前最有实际意义的方向是 idealized HDR paper projection：在普通漫反射白附近保留已创作的 SDR 印相观感，同时把部分高光能量扩展到 HDR headroom 中。这更适合理解为一种受 print route 启发的数字 HDR 投影，而不是声称物理摄影相纸本身具有 HDR 能力。

light-table HDR route 仍处于开发中，应视为正在推进的工作，而不是已经完成且语义稳定的模式。

在 HDR 文件输出方面，这个 fork 包含基于 gain map 的 HEIC 导出工作，输入是预先渲染好的 SDR/HDR pair。编码边界被刻意收窄：导出层只接收已经渲染好的 SDR 和 HDR 图像，负责写入文件并验证 gain-map 结构。导出路径包含 ISO 21496-1 / HEIC `tmap` 验证，并对硬结构错误采用 fail-closed 行为，避免在文件结构不符合预期时仍然声称 HDR 导出成功。

### 色彩管理与 macOS 显示预览

这个 fork 也细化了 runtime output、file saving 和 display preview 之间的边界。默认 SDR 行为仍保持 `sRGB + CCTF + clip`，以维持与上游式 SDR 渲染路径的兼容。scene-linear 和 ACES-oriented workflow 则采用更明确的处理方式，包括拆分 runtime output encoding 与 save encoding 控制。

在 macOS 上，GUI/bridge 的显示预览路径为 scene-linear 和 ACES-style 预览加入了更明确的 display transform。预览阶段不再在显示渲染前简单裁掉大于 1.0 的 scene highlights，而是可以把这些高光保留到 display transform 阶段，再生成可观看的 SDR preview。这还不是 OCIO/CTL 级 ACES Output Transform 的完整替代，但它让预览行为更清晰、更可测试，也更适合 HDR-aware scene-linear rendering 实验。

## 支持

spektrafilm 是我在业余时间开发的，经常是在 KTH 的研究工作结束后的深夜。如果你想支持持续开发，并为下一次通宵编码补充燃料，可以考虑[请我喝杯咖啡](https://buymeacoffee.com/andreavolpato)。你的贡献能帮助我投入更多时间到这个项目，并回馈 [pixls.us](https://discuss.pixls.us/) 社区。

## 参考文献

[^1]: Giorgianni, Madden, Digital Color Management, 2nd edition, 2008 Wiley
[^2]: Hunt, The Reproduction of Color, 6th edition, 2004 Wiley
[^3]: Mallett, Yuksel, Spectral Primary Decomposition for Rendering with sRGB Reflectance, Eurographics Symposium on Rendering - DL-only and Industry Track, 2019, doi:10.2312/SR.20191216

示例图像来自 [signatureedits.com](https://www.signatureedits.com/)/free-raw-photos。
