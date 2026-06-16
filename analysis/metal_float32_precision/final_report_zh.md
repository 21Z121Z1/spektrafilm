# Spektrafilm GUI RAW 到导出路径中 MLX/Metal float32 相对 CPU float64 的精度影响研究

日期：2026-06-08  
工作区：`/Users/retriedstormtrooper/Documents/Projects/Active/spektrafilm-main`  
研究目录：`analysis/metal_float32_precision/`

## 摘要

本研究在不修改生产代码的前提下，追踪 Spektrafilm 当前 GUI 中 RAW/DNG 导入、参数传递、CPU/MLX runtime、preview、SDR 导出和 HDR HEIC 导出入口，并用 8 张真实 DNG 样片与 5 组合成样例实测 CPU NumPy float64 reference 与 MLX/Apple Metal float32 backend 的误差。

最关键的边界是：GUI RAW loader 已在 RAW decode 后执行 `astype(np.float32) / np.float32(65535.0)`，所以“CPU float64 reference”不是 RAW demosaic 前的绝对 float64 真值，而是从同一个 GUI RAW loader 输出的 float32 RGB buffer 之后开始成立。代码证据见 `src/spektrafilm/utils/raw_file_processor.py:418-420`、返回说明 `:412-415`，以及测试 `tests/test_raw_file_processor.py:96-109`、`tests/test_raw_smoke.py:10-15`。

在本机 `macOS-26.5.1 arm64`、Python 3.13.1、MLX Metal 可用的环境下，8 张 RAW/DNG 的 128px 缩采样工作图全部跑通。最终 `materialized_rgb_out` 的最大绝对误差范围是 `6.43e-05` 到 `1.51e-04`，最大 ΔE2000 是 `0.0234`，PSNR 最低约 `97.72 dB`，SSIM 最低约 `0.9999999827`。PNG16 导出再解码后最大绝对误差最高 `1.53e-04`，主要增加来自 16-bit PNG 量化阶梯。5 组合成样例中，饱和 RGB 最敏感，最终最大绝对误差 `2.10e-04`，PNG16 roundtrip 后 `2.14e-04`。

## 结论先行

1. 当前代码事实下，“Metal backend”应解释为 MLX backend 通过 Apple Metal 执行，而不是独立 `metal_backend.py`。`select_backend()` 对 `float64` GPU 明确拒绝或回落 CPU，MLX 只接受 `float32`/`float16`，默认 `float32`，证据见 `src/spektrafilm/gpu/backend.py:72-122`、`src/spektrafilm/gpu/mlx_backend.py:18-40`。

2. GUI RAW decode 本身已经降为 float32。CPU reference 的主要意义是：同一 RAW loader 输出之后，GUI 非 MLX 路径把输入提升为 `np.double`，runtime CPU preprocess 也使用 `np.double`；而 MLX float32 路径保持/转换为 `np.float32`。证据见 `src/spektrafilm_gui/controller.py:152-181`、`src/spektrafilm/runtime/pipeline.py:556-577`。

3. 已测样片中，最终可见差异在工程上很小：8 张真实 RAW 的最终最大 ΔE2000 均低于 `0.024`，PSNR 均高于 `97 dB`，SSIM 接近 1。按常用图像/色彩验证经验，这低于可见风险阈值；但这不是全分辨率、所有参数组合、HDR HEIC 文件读回的证明。

4. 误差增长主要不在 RAW 输入或 GUI 参数层，而在 film/print/scan 的 log/pow、LUT/插值、光谱求和、CCTF/clip 之后累积。实测 `rgb_in/rgb_pre` 最大误差约 `6e-08`，`log_e_print/cmy_print/rgb_out` 增长到 `2.6e-05`、`7.1e-05`、`1.5e-04`。这些差异包含 float32 精度、MLX kernel 表达式、CPU colour-science 路径与 backend 公式实现差异，不能全部归因于 float32。

5. SDR PNG16 export 的编码差异已实测，量化使 EV percentile 变大但绝对误差仍约 `1.5e-04` 级。HDR HEIC GUI 路径已静态确认可触发并会重新渲染 `process_master()`，但本次没有做 HEIC/gain map 文件读回验证，因此 HDR 导出精度结论只能写为“路径风险已定位，端到端数值影响未能确认”。

## 研究范围和限制

- 没有读取本地既有 README/docs/reports/notes/markdown/rst/txt 叙述性文件；本报告依据源码、测试代码、配置/样片清单、本次测量结果和外部公开资料。
- 没有修改生产代码；只新增 `analysis/metal_float32_precision/` 下的研究脚本、结果和报告。
- 真实 RAW 测量使用 `--max-working-size 128`，即缩采样后的 deterministic 工作图，不代表全分辨率性能或缓存行为。
- deterministic 模式关闭了可通过参数关闭的随机/空间效应：auto exposure、grain、glare、halation boost、部分 scanner correction；这有助于隔离数值差异，但不是默认 GUI 全特效感知评估。
- HDR HEIC 导出只做静态路径分析；未把 HEIC、gain map、sidecar 通过系统解码器读回做数值比较。
- 未新增生产 hook，因此只 dump 现有 topology taps，未能 dump 每个内部 spectral/LUT/gain-map 子数组。

## 外部最佳实践摘要

外部资料只影响指标和实验分层：

- Apple Metal / MSL 和 `MTLCompileOptions.fastMathEnabled` 提醒 GPU 路径可能存在 FMA、fast math、`half`/`float`、kernel 表达式和异步求值差异；本研究因此做逐 tap 比较，并记录 NaN/Inf、clamp、dtype。参考：[Metal Shading Language Specification](https://developer.apple.com/metal/Metal-Shading-Language-Specification.pdf)、[MTLCompileOptions.fastMathEnabled](https://developer.apple.com/documentation/metal/mtlcompileoptions/1515484-fastmathenabled)。
- NVIDIA 浮点指南强调 CPU/GPU 差异可能来自 FMA、表达式重排和规约顺序；本报告因此区分“数值精度误差”和“backend 实现差异”。参考：[NVIDIA Floating Point and IEEE 754](https://docs.nvidia.com/cuda/floating-point/index.html)。
- OpenColorIO 的 CPU/GPU processor 思路支持将 pipeline buffer、GPU shader path、display transform 分层验证。参考：[OpenColorIO Documentation](https://opencolorio.readthedocs.io/)。
- Colour Science 提供 CIEDE2000 等色差函数；scikit-image 提供 PSNR/SSIM；本研究将它们用于最终 display RGB，而不把它们强加到 HDR 线性中间态。参考：[Colour delta_E](https://colour.readthedocs.io/en/latest/generated/colour.delta_E.html)、[skimage.metrics](https://scikit-image.org/docs/stable/api/skimage.metrics.html)。
- ITU BT.2124 / BT.2100 支持 HDR/WCG 场景使用 ICtCp/ΔEITP 或 luminance/EV 指标；本次实现 EV/luma error，ΔEITP 留作后续。参考：[ITU-R BT.2124](https://www.itu.int/rec/R-REC-BT.2124)、[ITU-R BT.2100](https://www.itu.int/rec/R-REC-BT.2100)。
- OpenImageIO 和 rawpy 文档影响导出 roundtrip 和 RAW decode 起点设计。参考：[OpenImageIO](https://openimageio.readthedocs.io/)、[rawpy postprocess](https://letmaik.github.io/rawpy/api/rawpy.RawPy.html#rawpy.RawPy.postprocess)、[OpenEXR](https://openexr.com/en/latest/TechnicalIntroduction.html)。

详细方法论记录见 `analysis/metal_float32_precision/methodology_notes.md`。

## 当前代码管线事实拆解

### RAW/DNG 导入

GUI RAW 入口是 `GuiController.load_raw_image()`：它从 GUI state 读取 white balance、temperature、tint、lens correction、input color space 和 input CCTF flag，然后调用 `load_and_process_raw_file()`，证据见 `src/spektrafilm_gui/controller.py:244-258`。RAW loader wrapper 在 `controller.py:136-137`。

RAW loader 在 `raw_file_processor._postprocess_params()` 中将 rawpy 配置为 ACES、16-bit、关闭 auto bright、线性 gamma，证据见 `src/spektrafilm/utils/raw_file_processor.py:83-130`。实际 decode 后立刻执行 `raw.postprocess(**params).astype(np.float32) / np.float32(65535.0)`，证据见 `:418-420`。后续 white balance adaptation、tint 和 colour-space conversion 见 `:429-443`。

测试也确认 RAW 输出契约：`tests/test_raw_file_processor.py:96-109` 断言 postprocess 参数和 `float32 / 65535`，`tests/test_raw_smoke.py:10-15` 断言 dtype 为 `np.float32`、3 通道、finite。

### GUI 参数进入 pipeline

`build_params_from_state()` 把 `GuiState` 映射到 runtime params，证据见 `src/spektrafilm_gui/params_mapper.py:10-27`。I/O 映射见 `:56-63`；settings 映射见 `:102-108`，其中 GUI 启用 enlarger/scanner LUT、`lut_resolution=17`、`use_fast_stats=True`。

GUI backend/precision enum 见 `src/spektrafilm_gui/options.py:80-96`；runtime 默认 `compute_backend="cpu"`、`gpu_precision="float32"`、`materialize_policy="numpy_float64"` 见 `src/spektrafilm/runtime/params_schema.py:228-248`。

GUI 在提交 simulation 前准备输入：如果 `compute_backend=="mlx"` 且 `gpu_precision=="float32"`，使用 `np.asarray(..., dtype=np.float32)`；否则使用 `np.double(image_data)`。证据见 `src/spektrafilm_gui/controller.py:144-181`。该函数被 preview worker 和 run simulation 调用，见 `controller.py:896-908`、`:976-984`。

### Backend selection

`SimulationPipeline.__init__()` 根据 settings 调用 `select_backend()`，并把 backend 注入 LUT service、color reference service 和 stages，证据见 `src/spektrafilm/runtime/pipeline.py:73-123`。

`select_backend()` 中，explicit CPU 返回 `NumpyBackend`；`precision=="float64"` 时 auto 回落 CPU，explicit GPU 直接报错；auto float32 优先 MLX 再 CuPy，证据见 `src/spektrafilm/gpu/backend.py:72-122`。`MlxBackend` 检查 MLX/Metal 可用性，只允许 `float32`/`float16`，float32 默认 `mx.float32`，见 `src/spektrafilm/gpu/mlx_backend.py:18-40`。`asarray()` 默认按 backend dtype 建 MLX array，`to_numpy()` 会 `eval`，证据见 `:56-75`。

### CPU float64 reference 路径

CPU backend 本身只是 NumPy wrapper，见 `src/spektrafilm/gpu/numpy_backend.py:20-79`。CPU preprocess 对输入执行 `np.double(np.array(image)[:, :, 0:3])`，见 `src/spektrafilm/runtime/pipeline.py:556-563`。Spectral LUT direct CPU 计算在不用 LUT 时强制 `np.float64`，见 `src/spektrafilm/runtime/services/spectral_lut_compute.py:142-149`。

因此 CPU reference 是“RAW loader float32 输出之后的 float64 runtime reference”，不是 RAW demosaic float64 ground truth。部分静态表、coefficients 和 colour-science 内部 dtype 可能不是纯 float64，报告不声称 CPU 全链路每个 scalar 都是 float64。

### MLX/Metal float32 路径

MLX backend 默认 float32，GPU preprocess 通过 `_backend_rgb_input()` 用 backend default dtype 接收 RGB，见 `src/spektrafilm/runtime/pipeline.py:565-577`、`:602-663`。GPU color kernels 显式要求 backend float32，见 `src/spektrafilm/gpu/kernels/color.py:123-138`。MLX 2D LUT Metal kernel 使用 `float`，输出 `mx.float32`，见 `src/spektrafilm/gpu/kernels/lut.py:32-221`。density interpolation 和 cmy-to-log-xyz Metal kernels也用 `float`、`pow`、`log10` 和 endpoint clamp，见 `src/spektrafilm/gpu/kernels/density.py:68-117`、`:126-236`。

本次追踪未发现 GUI RAW->MLX 主路径使用 float16 或 normalized texture；但 `MlxBackend` 支持 `float16` precision，如果 GUI/params 未来暴露或传入 float16，风险会显著不同。

## GUI RAW 到导出完整流程

文字流程图：

`GUI load_raw_image -> rawpy ACES16 linear decode -> float32 scene RGB -> GuiState/build_params_from_state -> _prepare_simulation_input_image -> SimulationPipeline(select_backend) -> topology(rgb_in/rgb_pre/log_e_film/cmy_film/log_e_print/cmy_print/rgb_out) -> materialize policy -> GUI preview uint8/display transform -> output layer float metadata -> SDR save_image_oiio OR HDR HEIC export_hdr_heic_from_simulator`

现有 topology taps 定义在 `src/spektrafilm/runtime/pipeline.py:871-886`。本研究脚本没有修改生产代码，只手动执行 topology node 并收集 state 中已有 taps。

## 每阶段 dtype / range / color semantics

| Stage | dtype/range/semantics | Code Evidence | Measured Notes |
|---|---|---|---|
| RAW loader output | `np.float32` RGB，默认线性 ACES/目标 input color space，可出现少量负值或 >1 | `raw_file_processor.py:418-443` | 8 张 RAW decoded source min 到 `-1.94e-04`，max 到 `1.0166`。 |
| GUI CPU input | `np.double` | `controller.py:159-164` | `stage_stats.csv` 中 CPU GUI prepared input 为 float64。 |
| GUI MLX input | `np.float32` | `controller.py:159-162` | `stage_stats.csv` 中 MLX GUI prepared input 为 float32。 |
| `rgb_pre` | CPU double / MLX backend float32，输入色彩语义 | `pipeline.py:556-577`, `602-663` | 真实 RAW `rgb_pre` max abs 约 `5.95e-08`。 |
| `log_e_film` | film raw log exposure | `filming.py:73-114` | 真实 RAW max abs 约 `9.51e-07`。 |
| `cmy_film` | film density channels | `filming.py:116-129` | 真实 RAW max abs 约 `5.40e-07`。 |
| `log_e_print` | print exposure log | `printing.py:77-115` | 真实 RAW max abs 约 `2.64e-05`。 |
| `cmy_print` | print density channels | `printing.py:189-211` | 真实 RAW max abs 约 `7.07e-05`。 |
| `rgb_out` | output RGB after scan/project/CCTF/clip | `scanning.py:72-124`, `213-240` | 真实 RAW max abs 最高 `1.51e-04`。 |
| GUI preview | normalized/clipped uint8 or display transformed image | `controller_runtime.py:378-416` | preview 与 export float buffer 不是同一数值层。 |
| SDR export input | default `np.float32` RGB | `controller_runtime.py:434-451`, `controller.py:488-532` | 本次 PNG16 roundtrip 已测。 |
| PNG/JPEG/TIFF/EXR encoding | PNG/JPEG clip/quantize；TIFF16 clip；TIFF32/EXR32 float32；EXR16 half | `utils/io.py:688-758` | PNG16 导出读回最高 max abs `1.53e-04`。 |
| HDR HEIC | linear HDR encoding required，gain map/renditions float32/clip | `utils/io.py:643-663`, `hdr_photo.py` grep 中多处 float32/clip | 静态确认，未读回验证。 |

## CPU float64 路径分析

CPU path 的 reference 价值来自：

- GUI 非 MLX 输入准备把 RAW loader 输出提升为 double，见 `controller.py:159-164`。
- Runtime CPU preprocess 再次使用 `np.double(np.array(...))`，见 `pipeline.py:556-563`。
- Direct spectral CPU 计算明确要求 float64，见 `spectral_lut_compute.py:147-149`。
- CPU color/scanner 中使用 colour-science、opt_einsum/NumPy，见 `scanning.py:99-108`、`:196-203`。

但 CPU reference 不是完美数学真值：

- RAW demosaic 和 loader output 已是 float32。
- 部分静态矩阵/coefficients 在源码中是 `np.float32`，例如 luminance coeffs `filming.py:133-138`。
- CPU 与 MLX 某些函数不是完全同一实现，例如 backend CCTF formulas vs `colour.RGB_to_RGB`，见 `gpu/kernels/color.py:445-479` 与 `scanning.py:225-235`。

## MLX/Metal float32 路径分析

MLX/Metal path 的事实：

- MLX backend 通过 MLX `mx` 检查 Apple Metal 可用性，见 `mlx_backend.py:27-32`。
- float32 precision 下 default dtype 是 `mx.float32`，见 `mlx_backend.py:34-40`。
- GPU color kernels拒绝非 float32，见 `gpu/kernels/color.py:123-138`。
- Hanatos RGB->tc/b 在 backend resident float32 中计算，见 `gpu/kernels/color.py:219-251`。
- 2D LUT Metal kernel 使用 float、floor、fabs、accumulate 和 output `mx.float32`，见 `gpu/kernels/lut.py:32-221`。
- density/scan kernel 使用 Metal `float`、binary search interpolation、`pow(10.0f, ...)`、`log10(...+1e-10f)`，见 `gpu/kernels/density.py:68-117`、`:126-236`。
- `to_numpy()` 会 `eval`，说明 MLX 异步执行在 materialization 时同步，见 `mlx_backend.py:67-75`。

未能确认：

- 未逐个审计所有 MLX generated kernel 是否使用 fast math 或是否禁用 FMA；当前代码没有在分析路径中显式设置 Metal `fastMathEnabled` 或 `precise`。
- 未确认 MLX 内部 `mx.matmul`、`mx.exp`、`mx.log10` 是否在所有设备上采用完全相同舍入/融合策略。

## 精度误差来源分类

### 计算精度误差

- RAW loader 输出 float32 被 CPU 提升到 float64 与 MLX 保持 float32，导致 `rgb_in/rgb_pre` 出现约 `6e-08` 级别差异。
- MLX kernel 中的 `float`、`pow`、`log10`、matrix multiply、LUT interpolation 会产生 float32 舍入。
- 多阶段 log/pow 和 spectral sum 会放大微小误差，尤其 print/scan 后段。

### Backend 实现差异

- `rgb_to_tc_b_backend()` 旨在 mirror CPU `_rgb_to_tc_b`，但 backend path 用 float32 矩阵和 backend transfer，见 `gpu/kernels/color.py:219-251`。
- 2D LUT CPU reference 使用 float64 contiguous inputs，MLX Metal kernel 使用 float32，见 `gpu/kernels/lut.py:203-232`。
- Scanner CPU `colour.XYZ_to_RGB` 与 GPU `xyz_to_rgb_backend` 矩阵路径不同，见 `scanning.py:99-108`。
- CCTF CPU 走 colour-science，GPU 走手写公式/矩阵，见 `scanning.py:225-235`、`gpu/kernels/color.py:445-479`。
- Code 已显式规避一个 backend 算法差异：CPU PCHIP LUT 与 backend 3D trilinear LUT 不等价时，GPU print/scanner 走 direct spectral fallback，见 `printing.py:126-139`、`spectral_lut_compute.py:156-168`。

### 导出编码差异

- PNG16 使用 `np.rint(np.clip(image_data,0,1)*65535).astype(np.uint16)`，证据 `utils/io.py:700-702`。
- JPEG 使用 uint8 clip，证据 `utils/io.py:703-710`。
- TIFF16 clip/uint16，TIFF32 float32，EXR16 half，EXR32 float32，证据 `utils/io.py:717-749`。
- ICC/profile/EXIF 写入会影响外部显示解释，但本次数值 roundtrip 只比较读回像素。

## 测量方法

脚本：`analysis/metal_float32_precision/measure_precision.py`

关键设计：

- RAW decode 使用 GUI 同源 `load_and_process_raw_file()`，参数为 `white_balance="as_shot"`、`output_colorspace="ProPhoto RGB"`、`output_cctf_encoding=False`。
- CPU reference 参数：`compute_backend="cpu"`、`gpu_precision="float64"`、`materialize_policy="numpy_float64"`。
- MLX/Metal candidate 参数：`compute_backend="mlx"`、`gpu_precision="float32"`、`materialize_policy="backend"`。
- 参数构建优先使用 `spektrafilm_gui.state.PROJECT_DEFAULT_GUI_STATE` 和 `build_params_from_state()`。
- deterministic 模式关闭 auto exposure、grain、glare、halation boost、scanner white/black correction 等可控非确定项。
- 逐 tap 比较：`rgb_in`、`rgb_pre`、`log_e_film`、`cmy_film`、`log_e_print`、`cmy_print`、`rgb_out`、`materialized_rgb_out`。
- 导出比较：PNG16 save/read roundtrip，比较 decoded CPU PNG 与 decoded MLX PNG。

输出文件：

- `analysis/metal_float32_precision/sample_inventory.csv`
- `analysis/metal_float32_precision/results/raw_128/metrics_summary.csv`
- `analysis/metal_float32_precision/results/raw_128/per_sample_metrics.json`
- `analysis/metal_float32_precision/results/raw_128/stage_stats.csv`
- `analysis/metal_float32_precision/results/synthetic_64/metrics_summary.csv`
- `analysis/metal_float32_precision/results/synthetic_64/per_sample_metrics.json`
- heatmap/histogram/high-error-pixel CSV 位于对应 results 子目录。

## 样片选择说明

样片根目录为 `/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片`。Inventory 共 754 个 RAW/DNG 文件，见 `sample_inventory.csv` 和 `results/raw_128/measurement_config.json`。

选择策略：

- 先按目录分组，优先选择不同目录来源；
- 在目录内优先选择大文件，覆盖不同设备/归档/转换来源；
- 再用 RAW loader 后统计确认覆盖暗部、接近高光、负值、>1 HDR-like 值和不同均值/标准差。

实际测量 8 张：

| sample_id | path | decoded shape | measured shape | source min/max | 说明 |
|---|---|---:|---:|---:|---|
| `IMG_4557` | `/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片/07_历史批量归档_DNG/IMG_4557.DNG` | 6048x8064x3 | 96x128x3 | `-5.98e-05` / `0.8140` | 低均值、含极少负值 |
| `IMG_0342_converted` | `/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片/04_批量导出_转换与预览/converted_DNG/IMG_0342_converted.DNG` | 6048x8064x3 | 96x128x3 | `0.00147` / `0.9575` | 转换 DNG，接近高光 |
| `IMG20260603204611.` | `/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片/01_散片原始DNG/IMG20260603204611..dng` | 8192x6144x3 | 128x96x3 | `0.00027` / `1.0166` | 有 >1 值，疑似 HDR/highlight 场景 |
| `IMG_9333` | `/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片/08_小归档_Archive1_DNG/IMG_9333.DNG` | 3024x4032x3 | 95x126x3 | `-1.06e-05` / `1.0008` | 低均值，少量负值与 >1 |
| `IMG_2972` | `/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片/03_成组拍摄/20260531_IDG_131302_390/IMG_2972.DNG` | 4032x3024x3 | 126x95x3 | `6.04e-05` / `0.9179` | 较高均值/标准差 |
| `IDG_20260410_140916_153_converted` | `/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片/02_转换DNG/IDG_20260410_140916_153_converted.DNG` | 3024x4032x3 | 95x126x3 | `-4.93e-05` / `0.9798` | 转换 DNG，含负值 |
| `IMG_4897` | `/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片/03_成组拍摄/20260528_IMG_4897/IMG_4897.DNG` | 3024x4032x3 | 95x126x3 | `0.000655` / `0.9958` | 低均值暗部样片 |
| `IMG_4536` | `/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片/07_历史批量归档_DNG/IMG_4536.DNG` | 6048x8064x3 | 96x128x3 | `-1.94e-04` / `0.9556` | 本次最终误差最高样片 |

## 指标定义

- Absolute error：`abs(mlx - cpu)`。
- Relative error：`abs(mlx - cpu) / max(abs(cpu), 1e-8)`。
- MAE：absolute error 平均值。
- RMSE：signed error 均方根。
- EV error：`abs(log2((max(mlx,0)+1e-8)/(max(cpu,0)+1e-8)))`。
- Luma Y：`0.2126R + 0.7152G + 0.0722B`。
- PSNR/SSIM：对 clipped `[0,1]` RGB 计算，用作结构性图像差异 sanity check。
- ΔE2000：对 clipped display RGB 近似转换到 Lab 后计算；不用于解释 HDR 线性中间态。

## 实际测量结果

环境见 `analysis/metal_float32_precision/results/raw_128/environment.json`：

- platform: `macOS-26.5.1-arm64-arm-64bit-Mach-O`
- machine: `arm64`
- Python: `3.13.1`
- `mlx_importable: true`
- `mlx_metal_available: true`

失败列表：

- `results/raw_128/failures.json`: `[]`
- `results/synthetic_64/failures.json`: `[]`

### 分阶段结果表：真实 RAW 8 张最大值

| Stage | samples | max abs error | worst sample | MAE at worst | RMSE at worst | max ΔE2000 at worst | PSNR at worst |
|---|---:|---:|---|---:|---:|---:|---:|
| `rgb_in` | 8 | `5.95e-08` | `IMG20260603204611.` | `2.60e-09` | `5.53e-09` | `1.05e-05` | `165.83` |
| `rgb_pre` | 8 | `5.95e-08` | `IMG20260603204611.` | `2.60e-09` | `5.53e-09` | `1.05e-05` | `165.83` |
| `log_e_film` | 8 | `9.51e-07` | `IMG_4557` | `8.78e-08` | `1.13e-07` | `8.68e-05` | `153.28` |
| `cmy_film` | 8 | `5.40e-07` | `IMG_2972` | `5.76e-08` | `8.26e-08` | `9.02e-05` | `142.97` |
| `log_e_print` | 8 | `2.64e-05` | `IMG_4536` | `4.16e-06` | `6.24e-06` | `0.00487` | `104.17` |
| `cmy_print` | 8 | `7.07e-05` | `IMG_4536` | `3.95e-06` | `6.79e-06` | `0.00952` | `110.35` |
| `rgb_out` | 8 | `1.51e-04` | `IMG_4536` | `4.12e-06` | `6.34e-06` | `0.02223` | `103.95` |
| `materialized_rgb_out` | 8 | `1.51e-04` | `IMG_4536` | `4.12e-06` | `6.34e-06` | `0.02223` | `103.95` |
| `export_png16_roundtrip` | 8 | `1.53e-04` | `IMG_4536` | `4.17e-06` | `8.59e-06` | `0.02131` | `101.32` |

数据来源：`analysis/metal_float32_precision/results/raw_128/metrics_summary.csv`。

### 分样片最终结果表：真实 RAW

| sample_id | final max abs | final MAE | final RMSE | final p99 abs | final max ΔE2000 | final PSNR | PNG16 roundtrip max abs |
|---|---:|---:|---:|---:|---:|---:|---:|
| `IMG_4557` | `8.14e-05` | `3.98e-06` | `6.61e-06` | `2.54e-05` | `0.02065` | `103.59` | `9.16e-05` |
| `IMG_0342_converted` | `8.03e-05` | `3.66e-06` | `5.26e-06` | `1.68e-05` | `0.01375` | `105.59` | `7.63e-05` |
| `IMG20260603204611.` | `9.07e-05` | `6.84e-06` | `1.30e-05` | `6.89e-05` | `0.02341` | `97.72` | `9.16e-05` |
| `IMG_9333` | `6.78e-05` | `3.73e-06` | `5.63e-06` | `1.77e-05` | `0.01656` | `104.99` | `7.63e-05` |
| `IMG_2972` | `1.07e-04` | `6.30e-06` | `1.05e-05` | `4.17e-05` | `0.01965` | `99.60` | `1.07e-04` |
| `IDG_20260410_140916_153_converted` | `8.60e-05` | `4.70e-06` | `8.53e-06` | `4.03e-05` | `0.02290` | `101.38` | `7.63e-05` |
| `IMG_4897` | `6.43e-05` | `2.93e-06` | `4.08e-06` | `9.48e-06` | `0.01226` | `107.79` | `7.64e-05` |
| `IMG_4536` | `1.51e-04` | `4.12e-06` | `6.34e-06` | `2.19e-05` | `0.02223` | `103.95` | `1.53e-04` |

### 合成样例结果

| sample_id | final max abs | final MAE | final max ΔE2000 | final PSNR | PNG16 roundtrip max abs | 解读 |
|---|---:|---:|---:|---:|---:|---|
| `synthetic_gray_ramp` | `4.58e-05` | `9.36e-06` | `0.00548` | `97.61` | `4.58e-05` | 平滑灰阶误差低 |
| `synthetic_shadow_ramp` | `9.35e-06` | `3.57e-06` | `0.00186` | `106.73` | `1.53e-05` | 暗部绝对误差最低，但相对/EV 对 near-zero 敏感 |
| `synthetic_highlight_ramp` | `1.04e-04` | `1.63e-05` | `0.01440` | `91.49` | `1.07e-04` | 高光/tone shoulder 区误差增加 |
| `synthetic_saturated_rgb` | `2.10e-04` | `1.51e-05` | `0.01363` | `90.41` | `2.14e-04` | 饱和色和 gamut/clamp 边界最敏感 |
| `synthetic_near_clip_mix` | `6.27e-05` | `2.61e-05` | `0.01028` | `89.79` | `6.11e-05` | near-clip 有较高 MAE，但 max 不最高 |

数据来源：`analysis/metal_float32_precision/results/synthetic_64/metrics_summary.csv`。

## 误差热区分析

Heatmap、histogram 和 high-error-pixel CSV 已为 `rgb_out`、`materialized_rgb_out` 输出：

- RAW：`analysis/metal_float32_precision/results/raw_128/error_heatmap_*_materialized_rgb_out.png`
- RAW high-error pixels：`analysis/metal_float32_precision/results/raw_128/high_error_pixels_*_materialized_rgb_out.csv`
- Synthetic：`analysis/metal_float32_precision/results/synthetic_64/error_heatmap_*_materialized_rgb_out.png`

结论：

- 真实样片误差不是从 RAW 输入开始放大，而是 print/scan 后段增长。
- `IMG_4536` 是真实 RAW 最坏样片；其 `cmy_print` 和 `rgb_out` 阶段为最大误差来源。
- 合成 `synthetic_saturated_rgb` 最坏，说明高饱和、gamut boundary、clip/tone boundary 组合是比普通灰阶更敏感的长期回归样例。
- `log_e_print` 的 relative/EV max 在 near-zero denominator 附近容易夸大；报告中优先看 absolute percentile、MAE/RMSE、ΔE/PSNR/SSIM。

## 暗部、高光、饱和色、clamp 附近专项分析

- 暗部：`synthetic_shadow_ramp` final max abs `9.35e-06`，绝对误差最低；但 EV 指标对接近 0 的像素敏感，需使用 epsilon 并结合 absolute error。
- 高光：`synthetic_highlight_ramp` final max abs `1.04e-04`，比灰阶更高，说明 tone shoulder/log/pow/highlight clamp 区域是重点。
- 饱和色：`synthetic_saturated_rgb` final max abs `2.10e-04`，本次最高；应作为 CI regression 必测。
- clamp 附近：`synthetic_near_clip_mix` final MAE `2.61e-05` 较高，说明边界区域影响更广，但 max 小于饱和色样例。
- 真实样片：`IMG20260603204611.` 有 `>1` RAW decoded 值，final max ΔE2000 最高 `0.02341`；仍很小，但适合作为 HDR/highlight regression fixture。

## SDR 导出影响

标准 SDR export 流程：

- GUI 从 output layer float metadata 取 `float_image_data`；
- `materialize_export_image()` 默认转 `np.float32` 并截取 3 通道，见 `controller_runtime.py:434-451`；
- 若保存色彩空间/CCTF 与 output layer 不同，使用 `colour.RGB_to_RGB` 转换，见 `controller.py:498-517`；
- `save_image_oiio()` 根据扩展名 clip/quantize/ICC，见 `utils/io.py:688-758`。

本次 PNG16 roundtrip 结果：

- RAW 最坏 max abs 从 final `1.5058e-04` 到 PNG16 `1.5265e-04`，增幅小。
- PNG16 p99 abs 通常落在 `1.5e-05` 到 `7.6e-05`，符合 16-bit 量化阶梯和 pipeline 差异叠加。
- 这说明在本次样片和参数下，SDR PNG16 编码不是主要误差来源；pipeline 后段差异更主要。

未测：

- JPEG uint8 的量化/有损压缩影响。
- TIFF16/TIFF32/EXR16/EXR32 roundtrip。
- ICC/profile 被外部应用解释后的视觉差异。

## HDR 导出影响

GUI HEIC/HEIF branch 在 `save_output_layer()` 中判断 suffix `.heic/.heif` 且 `hdr_heic_gain_map_enabled` 开启，证据见 `src/spektrafilm_gui/controller.py:403-451`。与 SDR branch 不同，它会：

- 用当前 GUI state 构建/digest params；
- 更新或创建 runtime simulator；
- 调用 `export_hdr_heic_from_simulator()`；
- 使用 `_current_input_image` 重新渲染，而不是直接保存 output layer float buffer。

`export_hdr_heic_from_simulator()` 调用 `simulator.process_master(image, hdr_mode=mode)`，渲染 HDR pair 后调用 `hdr_photo.save_hdr_photo_heic_from_pair()`，证据见 `src/spektrafilm/hdr/routemaster_export.py:66-89`。

HDR encode helper 要求 HEIC/HEIF 使用 linear HDR `ColorEncoding`，不能 CCTF encoded，不能 clip highlights，见 `src/spektrafilm/utils/io.py:643-663`。`hdr_photo.py` 中大量 `np.float32`、`np.clip`、gain map 计算、headroom、tone mapping 操作见 grep 结果记录在 `files_read.md`。

结论：

- HDR GUI 可触发路径已确认。
- HDR export 会重新渲染，所以 preview/output layer 与 HEIC 结果可能不是同一缓存结果。
- HDR path 内部 float32/clip/gain-map 风险较高，但本次未做 HEIC 文件读回，因此无法给出端到端 HDR 导出数值差异结论。

## GUI preview 与 final export 是否一致

不一致。

GUI preview 走 `prepare_output_display_image()`，先 `np.asarray(image_data)[..., :3]`，再 `normalized_image_data()`、clip、`uint8`，可选 display transform，证据见 `src/spektrafilm_gui/controller_runtime.py:378-416`。GUI output layer 同时保存 display image 和 `float_image` metadata，见 `controller_runtime.py:511-519`、`controller.py:921-938`。

SDR export 优先从 `float_image` metadata materialize，默认 `np.float32`，证据见 `controller.py:488-496`、`controller_runtime.py:434-451`。因此 preview 用于屏幕显示，export 用 float buffer；它们不是同一个数值对象。

HDR HEIC export 更不一致，因为它重新调用 simulator 的 RouteMaster/HDR pair 路径，见 `controller.py:422-451`、`hdr/routemaster_export.py:66-89`。

## 工程风险判断

当前 measured risk：

- 对 deterministic、缩采样 128px、8 张真实 DNG 和 5 组合成样例，MLX/Metal float32 相比 CPU reference 的最终差异很小，视觉上可接受的概率高。
- 最大实际差异集中在 print/scan 后段和饱和色/gamut/clip 边界。
- PNG16 导出不会显著放大本次误差。

主要工程风险：

- 当前 CI 若只测局部 kernel，无法覆盖 GUI RAW loader、params mapper、runtime materialization、export encode 的组合风险。
- HDR HEIC/gain map 未读回，不能宣称 HDR 导出数值一致。
- 全分辨率、auto exposure、grain、blur/halation、glare、ICC/display transform、JPEG/TIFF/EXR 等组合未覆盖。
- CPU/MLX 差异里包含 backend 实现差异；如果未来改动 GPU kernel、LUT fallback 或 CCTF formulas，不能只看 final allclose。

## 可接受阈值建议

建议作为初始 CI gate：

- RAW/synthetic deterministic pipeline final `materialized_rgb_out`：
  - max abs <= `5e-04`
  - p99 abs <= `1e-04`
  - MAE <= `5e-05`
  - RMSE <= `8e-05`
  - ΔE2000 max <= `0.10`
  - PSNR >= `80 dB`
  - SSIM >= `0.99999`
- Early taps：
  - `rgb_in/rgb_pre` max abs <= `1e-06`
  - `log_e_film/cmy_film` max abs <= `5e-06`
- Export PNG16 roundtrip：
  - max abs <= `7e-04`
  - p99 abs <= `2e-04`

这些阈值比本次实测宽，目的是给设备/MLX版本/输入差异留余量，同时仍能捕捉数量级回归。最终阈值应在更多全分辨率样片和默认 GUI 参数上校准。

## 推荐的长期回归测试方案

1. 固定 6-8 张小尺寸 RAW/DNG fixture 或从大样片生成不可逆小裁剪 fixture，避免 CI 拉取私人完整样片。
2. 增加 synthetic regression：gray、shadow、highlight、saturated RGB、near clip、HDR >1。
3. 使用现有 topology taps 保存 per-stage metrics；不要只测 final image。
4. 同时跑 CPU float64 reference 和 MLX float32；MLX 不可用时记录 skip，而不是静默 fallback。
5. 导出层至少覆盖 PNG16、TIFF32、EXR32；HDR HEIC 在 macOS runner 上增加 ImageIO/CoreImage readback 或 sidecar metadata validation。
6. 把 `metrics_summary.csv` 中的 max/p99/MAE/RMSE/ΔE/PSNR/SSIM 与阈值比较，并保存 heatmap 作为失败 artifact。
7. 对 GPU kernel 局部测试继续保持 `np.allclose`，但全链路测试使用 percentile + perceptual metrics。

## 当前测量方案盲点

- 没有全分辨率端到端图像测量。
- 没有默认随机 grain、glare、halation/blur 全开测量。
- 没有真实 GUI event loop 点击/导出操作验证；脚本通过现有可导入函数和 topology 模拟同源路径。
- 没有 HDR HEIC/gain map 文件读回。
- 没有 JPEG/TIFF/EXR roundtrip。
- 没有 ΔEITP/ICtCp。
- 没有精确分离 FMA/fast math 与一般 float32 舍入。

## 后续如果要提高一致性，应优先改哪里

不建议先重构生产代码。若需要提高一致性，优先级：

1. 建立 CI 级 per-stage precision harness，让回归先可见。
2. 对 `rgb_to_tc_b_backend` + 2D LUT、density interpolation、scanner spectral `cmy_to_log_xyz_backend` 增加更细粒度 kernel-vs-CPU reference fixtures。
3. 对 CCTF backend formulas 与 colour-science reference 加大样本覆盖，尤其 ProPhoto/BT.2020/Display P3。
4. 增加 HDR HEIC readback/metadata/gain-map verification。
5. 如果需要更严格一致性，审查 MLX Metal kernel 是否可控制 fast math/FMA 或重写部分累加顺序；否则把阈值定义为 float32 backend contract。

## 验证状态

- `measure_precision.py --inventory-only`: 成功。
- `measure_precision.py --synthetic-only --synthetic-size 64 --deterministic`: 成功。
- `measure_precision.py --deterministic --max-working-size 128 --samples ...`: 成功。
- `.venv/bin/python -m pytest --ignore=tests/gui -q`: `1486 passed, 7 skipped, 4 warnings in 108.10s`。

Git 状态说明：任务开始时 worktree 已有大量既有修改和未跟踪文档/源码/测试文件。本次只新增/修改 `analysis/metal_float32_precision/` 下文件；未修改生产代码。

## 自检

- 是否完全没有读取本地已有文档？是。未读取本地既有 README/docs/reports/notes/markdown/rst/txt。
- 是否只基于源代码、测试代码、配置和样片建立结论？是；外部资料只用于方法论。
- 是否搜索外部最佳实践？是，见 `methodology_notes.md`。
- 是否追踪 GUI RAW 导入到导出路径？是，见 `pipeline_trace.md`。
- 是否拆解 CPU float64 与 MLX/Metal float32 差异？是。
- 是否区分数值精度、backend 实现差异、导出编码差异？是。
- 是否设计并运行可复现测量？是，见 `measure_precision.py` 和 results。
- 是否诚实记录未确认点？是，HDR HEIC readback、全分辨率、默认随机效果等列为限制。
- 是否没有修改生产代码？是。

## 附录 A：读取过的代码文件列表

详见 `analysis/metal_float32_precision/files_read.md`。核心文件包括：

- `src/spektrafilm_gui/controller.py`
- `src/spektrafilm_gui/controller_runtime.py`
- `src/spektrafilm_gui/params_mapper.py`
- `src/spektrafilm/utils/raw_file_processor.py`
- `src/spektrafilm/runtime/pipeline.py`
- `src/spektrafilm/runtime/stages/filming.py`
- `src/spektrafilm/runtime/stages/printing.py`
- `src/spektrafilm/runtime/stages/scanning.py`
- `src/spektrafilm/gpu/backend.py`
- `src/spektrafilm/gpu/mlx_backend.py`
- `src/spektrafilm/gpu/kernels/color.py`
- `src/spektrafilm/gpu/kernels/lut.py`
- `src/spektrafilm/gpu/kernels/density.py`
- `src/spektrafilm/utils/io.py`
- `src/spektrafilm/utils/hdr_photo.py`
- `src/spektrafilm/hdr/routemaster_export.py`

## 附录 B：使用过的样片列表

详见 `analysis/metal_float32_precision/results/raw_128/measurement_config.json` 和 `files_read.md`。共实测 8 张，inventory 共 754 个 RAW/DNG 文件。

## 附录 C：运行命令

详见 `analysis/metal_float32_precision/commands_run.md`。

## 附录 D：输出文件清单

主要输出：

- `analysis/metal_float32_precision/measure_precision.py`
- `analysis/metal_float32_precision/methodology_notes.md`
- `analysis/metal_float32_precision/pipeline_trace.md`
- `analysis/metal_float32_precision/final_report_zh.md`
- `analysis/metal_float32_precision/commands_run.md`
- `analysis/metal_float32_precision/files_read.md`
- `analysis/metal_float32_precision/sample_inventory.csv`
- `analysis/metal_float32_precision/measurement_config.json`
- `analysis/metal_float32_precision/per_sample_metrics.json`
- `analysis/metal_float32_precision/metrics_summary.csv`
- `analysis/metal_float32_precision/results/inventory/*`
- `analysis/metal_float32_precision/results/synthetic_64/*`
- `analysis/metal_float32_precision/results/raw_128/*`

## 附录 E：参考资料链接

- [Apple Metal Shading Language Specification](https://developer.apple.com/metal/Metal-Shading-Language-Specification.pdf)
- [Apple MTLCompileOptions.fastMathEnabled](https://developer.apple.com/documentation/metal/mtlcompileoptions/1515484-fastmathenabled)
- [NVIDIA Floating Point and IEEE 754 Compliance](https://docs.nvidia.com/cuda/floating-point/index.html)
- [OpenColorIO Documentation](https://opencolorio.readthedocs.io/)
- [Colour `delta_E`](https://colour.readthedocs.io/en/latest/generated/colour.delta_E.html)
- [scikit-image metrics](https://scikit-image.org/docs/stable/api/skimage.metrics.html)
- [ITU-R BT.2124](https://www.itu.int/rec/R-REC-BT.2124)
- [ITU-R BT.2100](https://www.itu.int/rec/R-REC-BT.2100)
- [OpenImageIO Documentation](https://openimageio.readthedocs.io/)
- [rawpy RawPy.postprocess](https://letmaik.github.io/rawpy/api/rawpy.RawPy.html#rawpy.RawPy.postprocess)
- [OpenEXR Technical Introduction](https://openexr.com/en/latest/TechnicalIntroduction.html)
