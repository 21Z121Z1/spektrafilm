# SpektraFilm GPU 硬件加速落地方案

本文档基于 2026-05-07 对当前项目代码的扫描、一次本地 512x512 样本计时、`cProfile` 抽样，以及 Apple/MLX/CuPy/PyTorch 官方资料检索结果编写。目标是说明：当前处理链路在哪里耗时、GPU 方案应该怎么落地、每一步怎样验收。

## 结论摘要

SpektraFilm 当前的核心运行链路是 Python + NumPy/SciPy/colour-science + Numba。项目已经做了 CPU 优化：`fast_interp`、`fast_interp_lut`、`fast_gaussian_filter`、`fast_stats` 均是 Numba 热点内核；同时 `SpectralLUTService` 已经用 3D LUT 加速光谱计算。下一步 GPU 化不应该从“全量重写”开始，而应该以“保留 CPU 为数值基准，逐步替换高 ROI 内核”为主。

推荐主线：

1. Apple Silicon/macOS 上优先采用 MLX 作为 Python 侧 GPU 后端原型，并用 `mlx.core.fast.metal_kernel` 补齐 2D/3D LUT、PCHIP/插值、随机颗粒等自定义内核。
2. 对高频图像算子保留向下演进路径：如果 MLX 原型通过性能和数值验收，再把关键稳定内核固化为原生 Metal/Metal Performance Shaders 后端。
3. CPU 路径必须保持默认可用，GPU 路径先以 `params.settings.compute_backend = "auto" | "cpu" | "mlx"` 形式挂入。
4. 第一批 GPU 加速目标放在 LUT 采样、RGB 到 raw、density/光谱矩阵计算、扫描输出、Gaussian/FFT 卷积，而不是先碰随机颗粒。随机颗粒属于第二阶段或第三阶段，因为像素级随机数的可重复性和统计验收更复杂。

## 相关官方资料检索

本次方案只引用官方或一手文档作为技术依据：

- Apple Metal Performance Shaders：Apple 官方说明 MPS 提供针对各 Metal GPU family 调优的数据并行图像/计算 primitives，并能与 `MTLCommandBuffer`、`MTLTexture`、`MTLBuffer` 和自定义 shader 一起使用。参考：https://developer.apple.com/documentation/metalperformanceshaders
- Apple `MTLComputeCommandEncoder`：官方计算管线流程是创建 compute pipeline state、绑定 buffer/texture、dispatch threads/threadgroups。参考：https://developer.apple.com/documentation/metal/mtlcomputecommandencoder/
- Apple `MPSImageGaussianBlur`：官方说明该 blur 面向图像处理需求，是近似 Gaussian；若需要解析精确 Gaussian，应使用 `MPSImageConvolution` 和显式权重。参考：https://developer.apple.com/documentation/metalperformanceshaders/mpsimagegaussianblur
- MLX：Apple MLX 是类 NumPy array framework，支持 CPU/GPU、多设备、统一内存、lazy evaluation。参考：https://ml-explore.github.io/mlx/build/html/index.html
- MLX 安装要求：Apple Silicon 上 PyPI 安装要求 M 系列芯片、native Python >= 3.10、macOS >= 14.0；也提供 CUDA 后端包。参考：https://ml-explore.github.io/mlx/build/html/install.html
- MLX 自定义 Metal kernels：MLX 官方支持通过 Python/C++ API 写自定义 Metal kernel，并提示每次创建 kernel 都可能创建并 JIT 编译新的 Metal library。参考：https://ml-explore.github.io/mlx/build/html/dev/custom_metal_kernels.html
- CuPy：官方定位是 NumPy/SciPy-compatible GPU array library，主要面向 NVIDIA CUDA 与 AMD ROCm，并提供 `cupy.fft`、`cupyx.scipy.ndimage`、`cupyx.scipy.signal`、随机数、custom CUDA kernels 等。参考：https://docs.cupy.dev/en/v13.4.1/overview.html
- PyTorch MPS：官方 `torch.mps` 是 Python 访问 Metal Performance Shaders 后端的接口，也提供 profiling 和 shader 编译入口；但本项目不是 tensor/NN 架构，PyTorch 不作为第一选择。参考：https://docs.pytorch.org/docs/2.11/mps.html

## 当前处理链路

入口主要有两条：

- GUI：`src/spektrafilm_gui/controller.py` 中 `_process_image_with_runtime()` 会 digest 参数，复用或更新 `Simulator`，再调用 `process(image_data)`。
- API/脚本：`src/spektrafilm/runtime/process.py` 暴露 `Simulator.process()`、`simulate()`、`simulate_preview()`。

核心编排在 `src/spektrafilm/runtime/pipeline.py`：

```text
SimulationPipeline.process(image)
  -> _preprocess(image)
     -> np.double / 取前三通道
     -> FilmingStage.auto_exposure()
     -> ResizingService.crop_and_rescale()
  -> scan_film ? _pipeline_scan_film() : _pipeline_print()

_pipeline_print(rgb)
  -> FilmingStage.expose(rgb)
  -> FilmingStage.develop(log_raw_film)
  -> PrintingStage.expose(cmy_film)
  -> PrintingStage.develop(log_raw_print)
  -> ScanningStage.scan(cmy_print)

_pipeline_scan_film(rgb)
  -> FilmingStage.expose(rgb)
  -> FilmingStage.develop(log_raw_film)
  -> ScanningStage.scan(cmy_film)
```

### 1. 预处理

文件：

- `src/spektrafilm/runtime/pipeline.py`
- `src/spektrafilm/runtime/services/resize.py`
- `src/spektrafilm/utils/autoexposure.py`

主要计算：

- 输入转 `float64` NumPy array。
- 自动曝光：`colour.RGB_to_XYZ()` 后取 Y 通道，做 median 或 center-weighted weighted sum。
- crop。
- `skimage.transform.rescale()`，order=3 用于 full/scale，order=0 用于小 preview。

GPU 价值：

- 自动曝光和 resize 有 GPU 化价值，但不是第一优先级。原因是 preview 下输入较小，且 resize 当前由 `skimage` 完成；若先 GPU 化核心 stage，可保留预处理在 CPU，避免一开始重写太多。

### 2. FilmingStage.expose

文件：

- `src/spektrafilm/runtime/stages/filming.py`
- `src/spektrafilm/utils/spectral_upsampling.py`
- `src/spektrafilm/model/diffusion.py`
- `src/spektrafilm/utils/numba_boost_hightlights.py`
- `src/spektrafilm/utils/fast_gaussian_filter.py`

主要计算：

- 根据胶片 sensitivity、UV/IR filter、Hanatos bandpass 构造光谱 sensitivity。
- `rgb_to_raw_hanatos2025()`：
  - `colour.RGB_to_XYZ()` 得到 XYZ；
  - XYZ -> xy -> triangular/square coordinate；
  - `apply_lut_cubic_2d()` 从 Hanatos spectra/raw LUT 采样；
  - 乘亮度尺度 `b`。
- highlight boost：`boost_highlights()` 是 Numba elementwise 内核。
- camera diffusion filter：`apply_diffusion_filter_um()` 会构造 PSF 并 `fftconvolve`。
- lens blur：`fast_gaussian_filter()`。
- halation：scatter Gaussian + exponential Gaussian-mixture + 多次 bounce Gaussian。
- black/white filming correction。
- `log10(max(raw, 0) + 1e-10)`。

GPU 价值：

- 很高。这里包含了大量 per-pixel 数学、2D LUT、Gaussian/FFT 卷积、log/power。只要保持数据常驻 GPU，就能减少多次 CPU 内存扫描。

### 3. FilmingStage.develop

文件：

- `src/spektrafilm/runtime/stages/filming.py`
- `src/spektrafilm/model/emulsion.py`
- `src/spektrafilm/model/density_curves.py`
- `src/spektrafilm/model/couplers.py`
- `src/spektrafilm/model/grain.py`

主要计算：

- `develop_simple()`：`interpolate_exposure_to_density()` 对每个像素/通道做 1D density curve 插值，底层是 `fast_interp()`。
- DIR couplers：
  - 矩阵计算 coupler correction；
  - 根据 density silver 做 `contract('ijk, km->ijm')`；
  - `fast_gaussian_filter()` 扩散；
  - 再插值回 density。
- grain：
  - 单层或三子层；
  - `fast_binomial`、`fast_poisson`、`fast_lognormal_from_mean_std`；
  - Gaussian blur；
  - micro-structure。

GPU 价值：

- 插值、矩阵、DIR correction 很适合 GPU。
- grain 计算量高，但随机数验收复杂。建议先保留 CPU 或做 opt-in GPU grain，等 deterministic/statistical tests 完整后再默认开启。

### 4. PrintingStage.expose/develop

文件：

- `src/spektrafilm/runtime/stages/printing.py`
- `src/spektrafilm/runtime/services/spectral_lut_compute.py`
- `src/spektrafilm/utils/lut.py`
- `src/spektrafilm/utils/fast_interp_lut.py`
- `src/spektrafilm/utils/conversions.py`

主要计算：

- 黑白参考：`_film_cmy_to_print_log_raw()`。
- `SpectralLUTService.spectral_compute_enlarger()`：
  - 直接光谱计算，或
  - 3D LUT：`compute_with_lut()` -> `_create_lut_3d()` -> `apply_lut_3d()`。
- `_film_cmy_to_print_log_raw()`：
  - `compute_density_spectral()`；
  - `density_to_light()`；
  - `contract("ijk, kl->ijl", light, sensitivity)`；
  - midgray exposure factor 和 preflash。
- print diffusion filter。
- log raw print。
- `develop_simple()` density curve 插值。

GPU 价值：

- 很高。这里的光谱映射和 3D LUT 是当前大热点之一。更重要的是，`SpectralLUTService` 现在只缓存 raw LUT，没有缓存 PCHIP slopes/cell bounds；`apply_lut_pchip_3d()` 每次都会 `prepare_lut_pchip_3d()`。即使不做 GPU，也应先把 prepared LUT 缓存起来。

### 5. ScanningStage.scan

文件：

- `src/spektrafilm/runtime/stages/scanning.py`
- `src/spektrafilm/model/glare.py`
- `src/spektrafilm/model/diffusion.py`

主要计算：

- `_density_to_rgb()`：
  - scanner 3D LUT 或直接 spectral calculation；
  - `10 ** log_xyz`；
  - black/white xyz correction；
  - viewing illuminant XYZ；
  - optional glare；
  - `colour.XYZ_to_RGB()`。
- scanner lens blur 和 unsharp mask。
- optional output CCTF encoding + clip。

GPU 价值：

- 高。scanner spectral LUT、XYZ/RGB 矩阵、CCTF/clip 都是 per-pixel；blur/unsharp 也是典型 GPU 图像算子。`colour.XYZ_to_RGB()` 当前在 CPU 库内执行，GPU 化时应把所需矩阵预先求出并在 GPU 上执行。

## 本地热点样本

运行方式：使用 512x512 `float64` 随机图，先 warm 一次，再计第二次；命令通过 `uv run python -c ...` 执行。

| 场景 | 总耗时 | 主要热点 |
| --- | ---: | --- |
| `fast_no_spatial_no_lut` | 584 ms | `PrintingStage.expose` 246 ms，`ScanningStage.scan` 263 ms，两个 direct spectral compute 各约 222-228 ms |
| `fast_no_spatial_lut17` | 142 ms | `ScanningStage.scan` 58.2 ms，`FilmingStage.expose` 34.9 ms，`PrintingStage.expose` 33.5 ms |
| `spatial_halation_couplers_lut17_no_stochastic` | 181 ms | `FilmingStage.expose` 66.4 ms，`ScanningStage.scan` 62.3 ms，`PrintingStage.expose` 34.5 ms |

`cProfile` 对第三个场景的抽样重点：

- `ScanningStage.scan()` 累计约 163 ms，其中 `_density_to_rgb()` 约 130 ms。
- `compute_with_lut()` 两次累计约 88 ms。
- `apply_lut_3d()`/`apply_lut_pchip_3d()` 两次累计约 81 ms。
- `prepare_lut_pchip_3d()` 两次累计约 60 ms，其中 monotonicity warning 检查约 59 ms。
- `colour` 库内部 `vecmul` 约 67 ms。
- `fast_gaussian_filter()` 九次累计约 31 ms。
- `interpolate_exposure_to_density()` 三次累计约 21 ms。

解读：

- 已启用 LUT 后，direct spectral compute 从最大热点变成了 LUT sampling、colour matrix、blur、插值。
- GPU 化前先缓存 prepared PCHIP LUT 是低风险收益项。
- GPU 化不应只替换一个函数；如果每个 stage 都把 GPU array 拉回 CPU，拷贝和同步会吞掉收益。

## 后端选择

### 推荐路径 A：MLX 原型 + 自定义 Metal kernel

适用：

- 当前项目是 Python 项目；
- 开发机路径显示为 macOS，本项目依赖 Python 3.13/3.14 wheel；
- 主要目标应是 Apple Silicon GPU。

优点：

- MLX Python API 类 NumPy，接入成本低于手写 Objective-C++ extension。
- MLX 使用统一内存，CPU/GPU 共享内存模型对本项目这种 NumPy 迁移更友好。
- 官方支持 `mx.compile()`、FFT、convolution、`mx.einsum`/`matmul`、random、custom Metal kernel。
- 可先做 prototype，验证 ROI，再决定是否把内核固化到原生 Metal extension。

风险：

- MLX 是 lazy evaluation，计时必须显式 `mx.eval()`/`mx.synchronize()`。
- MLX custom Metal kernel 如果每次创建都会 JIT 编译，应在模块加载或 backend 初始化时缓存 kernel 对象。
- 当前 CPU 为 `float64`，GPU 后端多数图像计算应以 `float32` 为主。必须通过容忍度和 perceptual metrics 验收。
- `colour-science` 复杂色彩变换不能直接“自动跑 GPU”，需要把矩阵/CCTF拆出来。

### 路径 B：原生 Metal/MPS Python extension

适用：

- MLX 原型证明 ROI，但部分算子需要更稳定的打包、控制和性能；
- 需要直接使用 `MPSImageGaussianBlur`、`MPSImageConvolution`、`MTLTexture` 或 GPU counter capture；
- 想让 SpektraFilm 不依赖 MLX 的 lazy graph 行为。

优点：

- 对 Metal buffer/texture、command queue、pipeline state、threadgroup size 有完整控制。
- 可以直接使用 MPS 高性能图像 primitives。
- 对 GUI/打包可控。

风险：

- 需要 Objective-C++/Swift/C++ extension 与 Python 包构建；
- macOS/Xcode/SDK 版本约束更强；
- 维护成本高于 MLX。

建议：不要第一阶段就走全原生 Metal。先以 MLX 验证 GPU 化收益，保留内核算法和测试，再迁移最热的 2-3 个内核。

### 路径 C：CuPy CUDA/ROCm 可选后端

适用：

- 未来要支持 Linux + NVIDIA/AMD 工作站。

优点：

- 对 NumPy/SciPy API 覆盖广；
- `cupyx.scipy.ndimage`、`cupyx.scipy.signal`、`cupy.fft`、random 和 custom CUDA kernel 对本项目很有用。

限制：

- CuPy 官方主线是 NVIDIA CUDA/AMD ROCm，不解决 Apple Silicon/Metal。
- 需要项目先抽象 backend，否则会把代码分裂成 NumPy、MLX、CuPy 三份。

建议：先完成 backend protocol，再把 CuPy 作为后续扩展，不作为本轮 Apple GPU 加速主线。

### 路径 D：PyTorch MPS

适用：

- 如果未来引入 ML 模型或 tensor-heavy 工作流。

不推荐作为当前主线：

- 项目不是 PyTorch 架构；
- 需要迁移大量 NumPy/colour/Scipy 逻辑；
- 自定义图像 LUT/PCHIP/胶片随机颗粒依然要写 custom kernel。

## 建议架构

新增一个很薄的 backend 层，不要把 GPU 分支散落到每个 model 函数里。

建议目录：

```text
src/spektrafilm/gpu/
  __init__.py
  backend.py
  numpy_backend.py
  mlx_backend.py
  capabilities.py
  kernels/
    lut.py
    color.py
    density.py
    filters.py
    random.py
  validation.py
```

### Backend protocol

`backend.py` 定义最小接口：

```python
class ArrayBackend(Protocol):
    name: str
    supports_gpu: bool

    def asarray(self, value, dtype=None): ...
    def to_numpy(self, value): ...
    def eval(self, *values): ...
    def synchronize(self): ...

    def exp(self, x): ...
    def log10(self, x): ...
    def maximum(self, x, y): ...
    def clip(self, x, lo, hi): ...
    def matmul(self, a, b): ...
    def einsum(self, pattern, *values): ...
```

然后把项目特有内核放在 `kernels/` 中，而不是强行把所有 NumPy API 包一遍。

### 参数开关

在 `src/spektrafilm/runtime/params_schema.py` 的 `SettingsParams` 增加：

```python
compute_backend: str = "auto"  # "auto", "cpu", "mlx"
gpu_precision: str = "float32" # first GPU target
gpu_validate: bool = False     # shadow compare CPU/GPU on selected paths
```

行为：

- `"cpu"`：完全走现有路径。
- `"auto"`：若 MLX 可用且 `mlx.core.metal.is_available()` 为真，则使用 MLX；否则静默 CPU fallback，并在 timing/debug 中记录原因。
- `"mlx"`：强制 MLX；若不可用则抛出明确错误。

### 数据驻留原则

GPU 加速成功的关键不是某个算子快，而是整段 pipeline 不反复在 CPU/GPU 间来回。

原则：

- `SimulationPipeline.process()` 在 `_preprocess()` 后只做一次 `backend.asarray()`。
- 每个 stage 返回 backend array。
- 只有最终给 GUI 或 API 返回时才 `backend.to_numpy()`。
- profile 常量、LUT、density curves、CMFS、illuminant、sensitivity、channel_density 要在 `Simulator`/service 生命周期内缓存 GPU copy。
- `SpectralLUTService` 不仅缓存 raw LUT，还要缓存 GPU LUT 和 prepared PCHIP slopes/cell bounds。

### CPU fallback 原则

每个 GPU 内核都应有 CPU 等价函数：

- GPU 不可用；
- 输入 dtype/shape 不支持；
- 用户启用 debug output；
- stochastic exact reproducibility 模式；
- 单元测试中需要 baseline；

都可以走 CPU fallback。

## 分阶段实施

### Phase 0：基线、计时、低风险 CPU 优化

目标：先让后续验收可重复。

要做：

1. 新增 `scripts/benchmark_runtime_backend.py`：
   - 输入尺寸：`256x256`、`512x512`、`1024x1024`、`2048` long edge；
   - 场景：no LUT/direct、LUT17、spatial no stochastic、full default；
   - 每个场景区分 cold start、warm start；
   - 输出 JSON：总耗时、stage timings、mean/max memory、输出摘要。
2. 在 `SpectralLUTService` 中缓存 prepared PCHIP 数据：
   - 当前 `apply_lut_pchip_3d(lut, image)` 每次都会 `prepare_lut_pchip_3d(lut)`；
   - 改为服务层持有 `enlarger_lut_prepared_memory`、`scanner_lut_prepared_memory`；
   - 新增 `apply_lut_pchip_3d_prepared(prepared, image)` public API。
3. 建立 `docs/performance_baselines/` 或 `artifacts/benchmarks/` 输出约定。

验收：

- `uv run pytest tests/test_lut.py tests/test_pipeline_smoke.py tests/test_regression_baselines.py`
- benchmark JSON 可稳定生成。
- 缓存 prepared LUT 后，512x512 `fast_no_spatial_lut17` 场景应比当前 142 ms 有可见下降；若低于 10% 也可接受，但不能变慢。
- 输出与原 CPU path 一致：existing regression baseline 不变。

### Phase 1：MLX backend 框架和 LUT pilot

目标：最小可用 GPU backend，不改模型语义。

要做：

1. `pyproject.toml` 增加可选依赖：

   ```toml
   [project.optional-dependencies]
   dev = ["pytest"]
   gpu-apple = ["mlx>=0.31"]
   ```

2. 新增 `src/spektrafilm/gpu/backend.py`、`mlx_backend.py`、`numpy_backend.py`。
3. 新增 `SettingsParams.compute_backend` 等参数。
4. 实现 MLX 版：
   - `apply_lut_cubic_2d_mlx()`：先直接用 MLX ops 或 custom Metal kernel 对齐当前 `apply_lut_cubic_2d()`；
   - `apply_lut_pchip_3d_mlx()` 或先实现 `apply_lut_trilinear_3d_mlx()` 作为低精度快速路径；
   - `compute_with_lut_gpu()`：normalize + sample 融合，输出 backend array。
5. 在 `SpectralLUTService.spectral_compute_enlarger/scanner()` 添加 backend-aware 分支。

优先顺序：

1. Hanatos 2D LUT：影响 `FilmingStage.expose()`。
2. 3D spectral LUT：影响 `PrintingStage.expose()` 与 `ScanningStage.scan()`。
3. 缓存 GPU LUT：避免每帧上传。

验收：

- 新增 `tests/test_gpu_lut.py`，在无 MLX/无 Metal 环境下 skip。
- 2D LUT kernel：
  - synthetic affine/quadratic LUT；
  - CPU vs GPU max abs <= `2e-4`，RMSE <= `5e-5`。
- 3D LUT kernel：
  - 若实现 PCHIP，CPU vs GPU max abs <= `5e-4`，RMSE <= `1e-4`；
  - 若先实现 trilinear，full pipeline 必须标记为 `"gpu_fast_lut"`，不得冒充 PCHIP exact。
- `uv run pytest tests/test_lut.py tests/test_gpu_lut.py tests/test_pipeline_smoke.py`
- 512x512 no-spatial LUT 场景 warm run 至少快于 CPU LUT path 1.5x，或为 Phase 2 提供明确 profile 证据。

### Phase 2：per-pixel 色彩/光谱链路 GPU 化

目标：把 Filming/Printing/Scanning 中不含空间卷积和随机数的 per-pixel 大段融合到 GPU。

要做：

1. 将 `rgb_to_raw_hanatos2025()` 拆成 GPU 友好步骤：
   - CPU 端预先求 input color space -> XYZ 的 3x3 matrix 和参考 white；
   - GPU 上做 RGB -> XYZ、xy/tc、2D LUT、乘亮度 `b`。
2. 将 `compute_density_spectral()`、`density_to_light()`、`contract("ijk, kl->ijl")` 改为 backend kernel：
   - `density_spectral = density_cmy @ channel_density.T + base_density`；
   - `light = pow(10, -density_spectral) * illuminant`；
   - `raw_or_xyz = light @ sensitivity_or_cmfs`。
3. 将 `ScanningStage._density_to_rgb()` 中 `colour.XYZ_to_RGB()` 替换为预计算矩阵 + CCTF kernel。
4. 将 `boost_highlights()`、`log10`、`pow(10, x)`、black/white correction、clip/CCTF 走 backend。

验收：

- 新增 `tests/test_gpu_color_chain.py`。
- 用固定输入：
  - gray ramp 16/64；
  - RGB primaries patches；
  - random 64x64；
  - `img/targets/cc_halation.png` resize 256。
- 无 spatial/stochastic，CPU direct vs GPU direct：
  - max abs <= `3e-3`；
  - mean abs <= `3e-4`；
  - DeltaE00 p95 <= `0.5`，max <= `1.5`。
- full `simulate()` 支持 `compute_backend="mlx"`，输出 shape/finite/bounded。
- 512x512 no-spatial LUT warm run <= CPU LUT path 的 60%，或达到 <= 85 ms。

### Phase 3：density curve、DIR couplers 和 Gaussian/FFT 空间效果

目标：把剩余确定性重计算热点迁到 GPU。

要做：

1. 1D density curve interpolation GPU kernel：
   - 输入 `log_raw HxWx3`、`x_axis Kx3 or K`、`density_curves Kx3`；
   - 与 `fast_interp()` 一样支持 endpoint clamp 和 right-biased exact-match 语义；
   - 若 `log_exposure` 等距，可加 fast path，否则保留 binary search。
2. DIR couplers：
   - GPU 上做 density silver、matrix correction；
   - Gaussian diffusion 走 GPU filter；
   - 再调用 GPU interpolation。
3. Gaussian blur：
   - 小 sigma：custom separable FIR Metal kernel；
   - 大 sigma：优先使用 MLX FFT/convolution 或 MPSImageGaussianBlur；
   - 注意 `MPSImageGaussianBlur` 是近似 Gaussian，若某些验收需要解析一致，应使用显式 convolution kernel。
4. Diffusion filter：
   - PSF 仍可 CPU 构造并上传；
   - channel-wise FFT convolution 改为 MLX FFT 或原生 Metal/MPS convolution；
   - 对 `apply_diffusion_filter_um()` 的 `fftconvolve` 做 GPU 替换。
5. Halation：
   - scatter core/tail、多 bounce Gaussian 全部复用 GPU Gaussian；
   - 多个 Gaussian pass 可在一个 command/compiled function 中组织，减少同步。

验收：

- 新增 `tests/test_gpu_density.py`、`tests/test_gpu_filters.py`。
- `fast_interp()` parity：
  - random log exposure，max abs <= `1e-6` for float64 CPU reference vs float32 GPU 可放宽到 `2e-5`。
- Gaussian：
  - 小 sigma custom FIR vs CPU `fast_gaussian_filter_small()`：RMSE <= `2e-5`，max abs <= `2e-4`。
  - 大 sigma approximate path vs CPU IIR：RMSE <= `2e-3`，max abs <= `1e-2`；边缘单独统计。
- Diffusion filter：
  - 能量守恒误差：每通道 sum 相对误差 <= `1e-3`；
  - output finite，非负；
  - 与 CPU `apply_diffusion_filter_um()` mean abs <= `1e-3`。
- 512x512 spatial/no-stochastic/LUT17 warm run <= CPU path 的 50%，或达到 <= 90 ms。
- 1024x1024 spatial/no-stochastic/LUT17 warm run 至少 3x CPU。

### Phase 4：随机颗粒和 glare GPU 化

目标：完成 full default 的 GPU path。

难点：

- 当前 CPU path 的随机数来自 NumPy/SciPy/Numba，不同平台很难逐像素 bit-exact。
- 颗粒的视觉结果更适合统计验收，而不是逐像素验收。

要做：

1. 增加 deterministic stateless PRNG：
   - 输入 global seed、pixel index、channel、sublayer；
   - 输出 uniform/normal；
   - 可实现 PCG/Philox 风格 hash RNG。
2. GPU 版：
   - Poisson；
   - Binomial；
   - lognormal from mean/std；
   - micro-structure；
   - glare roughness。
3. 参数：
   - `grain.random_backend = "cpu_exact" | "gpu_statistical"`；
   - 默认先保持 CPU exact，GPU grain opt-in。

验收：

- 统计测试：
  - 固定 density 输入，GPU grain 的 mean/std/skew 与 CPU reference 或理论值相对误差 <= `3%`；
  - 不同 channel/sublayer 无明显相关性：相关系数绝对值 <= `0.03`；
  - seed 稳定：同一 seed 两次 GPU 输出 bitwise identical 或 allclose identical。
- 视觉测试：
  - 256/512 patch 输出 RMS granularity 与 CPU reference 相差 <= `5%`；
  - blur 后功率谱径向 profile 相差 <= `5%`。
- full default 512x512 warm run 至少快于 CPU full default 2x。

### Phase 5：GUI/API 集成和打包

目标：用户可开关，失败可回退，调试可解释。

要做：

1. GUI 增加 compute backend 选项：
   - Auto；
   - CPU；
   - Apple GPU / MLX。
2. `Simulator.format_timings()` 显示 backend 名称、GPU 可用性和 fallback 原因。
3. GUI 状态映射更新：
   - `src/spektrafilm_gui/params_mapper.py`
   - widget specs/sections。
4. 错误策略：
   - `"auto"` 下 GPU 初始化失败：status 提示后 CPU fallback；
   - `"mlx"` 下失败：抛出明确异常，避免用户误以为用了 GPU。
5. 打包：
   - `gpu-apple` optional dependency；
   - 文档说明 macOS、Apple Silicon、native Python 要求。

验收：

- GUI tests 增加 backend 参数映射。
- Auto 模式无 GPU 环境测试：不崩溃，走 CPU。
- 强制 MLX 无 GPU 测试：明确错误。
- GUI preview 多次运行无内存持续增长；可通过 MLX memory API 或进程 RSS 做 smoke 监测。

### Phase 6：可选 CUDA/CuPy 后端

目标：在 Linux/NVIDIA/AMD 上复用同一个 backend protocol。

要做：

- `src/spektrafilm/gpu/cupy_backend.py`
- optional deps:

  ```toml
  gpu-cuda = ["cupy-cuda12x"]
  ```

- 将 LUT、filters、FFT、random 映射到 CuPy/CuPyX。

验收：

- 与 MLX 同一套 kernel parity tests；
- 若无 CUDA/ROCm，tests skip。

## 需要修改的文件清单

第一轮建议修改：

- `pyproject.toml`
  - 增加 `gpu-apple` optional dependency。
- `src/spektrafilm/runtime/params_schema.py`
  - 增加 `compute_backend`、`gpu_precision`、`gpu_validate`。
- `src/spektrafilm/runtime/pipeline.py`
  - 在 pipeline 初始化/处理入口选择 backend；
  - 确保最终输出转回 NumPy。
- `src/spektrafilm/runtime/services/spectral_lut_compute.py`
  - 缓存 CPU prepared LUT；
  - 缓存 GPU LUT；
  - backend-aware spectral compute。
- `src/spektrafilm/utils/fast_interp_lut.py`
  - 暴露 prepared LUT public apply 函数；
  - 避免每帧重复 monotonicity scan。
- `src/spektrafilm/utils/lut.py`
  - 支持传入 prepared LUT / backend。
- `src/spektrafilm/utils/spectral_upsampling.py`
  - 分离可预计算 color matrix 和 GPU kernel 逻辑。
- `src/spektrafilm/model/diffusion.py`
  - filter backend dispatch。
- `src/spektrafilm/model/density_curves.py`
  - interpolation backend dispatch。
- `src/spektrafilm/model/emulsion.py`
  - density spectral backend dispatch。
- `src/spektrafilm/model/grain.py`
  - 后续随机 backend dispatch。
- 新增 `src/spektrafilm/gpu/*`。
- 新增 tests：
  - `tests/test_gpu_backend.py`
  - `tests/test_gpu_lut.py`
  - `tests/test_gpu_color_chain.py`
  - `tests/test_gpu_density.py`
  - `tests/test_gpu_filters.py`
  - `tests/test_gpu_grain.py`
- 新增 benchmark：
  - `scripts/benchmark_runtime_backend.py`

## 验收标准

### 基础功能验收

每个阶段必须满足：

```bash
uv run pytest tests/test_lut.py
uv run pytest tests/test_pipeline_smoke.py
uv run pytest tests/test_regression_baselines.py
```

GPU 环境下还要满足：

```bash
uv run pytest tests/test_gpu_backend.py tests/test_gpu_lut.py
uv run pytest tests/test_gpu_color_chain.py tests/test_gpu_density.py tests/test_gpu_filters.py
```

随机颗粒阶段再增加：

```bash
uv run pytest tests/test_gpu_grain.py
```

### 数值验收

分层验收，不要用一个阈值覆盖所有环节：

| 层级 | 输入/场景 | 指标 |
| --- | --- | --- |
| kernel exact-ish | LUT、1D interp、matrix、log/pow | RMSE <= `1e-4`，max abs <= `5e-4`；复杂 PCHIP 可放宽到 max abs <= `1e-3` |
| non-spatial pipeline | gray ramp、RGB patches、random 64/256 | mean abs <= `3e-4`，max abs <= `3e-3`，DeltaE00 p95 <= `0.5` |
| spatial deterministic | halation、Gaussian、diffusion、DIR couplers | mean abs <= `1e-3`，max abs <= `1e-2`，边缘区域单独统计 |
| stochastic | grain/glare | mean/std/skew、RMS granularity、功率谱等统计一致；不要求逐像素等同 CPU |
| final display | sRGB output | finite、bounded `[0, 1]`，无 NaN/Inf，无明显 banding/edge artifact |

### 性能验收

所有性能都要区分 cold start 和 warm run。GPU kernel JIT、LUT build、Numba compile 不计入 steady-state，但要单独记录。

建议通过新增脚本输出 JSON：

```bash
uv run python scripts/benchmark_runtime_backend.py --backend cpu --sizes 512 1024
uv run python scripts/benchmark_runtime_backend.py --backend mlx --sizes 512 1024
```

第一阶段目标：

- 512x512 no-spatial LUT warm run：GPU <= CPU 的 60%，或 <= 85 ms。
- 512x512 spatial/no-stochastic LUT warm run：GPU <= CPU 的 50%，或 <= 90 ms。
- 1024x1024 spatial/no-stochastic LUT warm run：GPU 至少 3x CPU。
- Preview mode long edge 640：目标 <= 50 ms warm run。
- 无 GPU 时 CPU 性能不得回退超过 5%。

### 稳定性验收

- `compute_backend="auto"` 在无 GPU/无 MLX 环境下必须 CPU fallback。
- `compute_backend="mlx"` 在无 GPU/无 MLX 环境下必须明确报错。
- 连续处理 50 张 512x512 图像，进程内存/MLX active memory 不持续线性增长。
- GUI 中连续调整参数并重跑，旧 GPU LUT/常量缓存能够被正确失效或复用。
- debug output 模式仍能输出 film log raw、film density、print density。

### 画质验收

固定样例：

- `gray_ramp_16`
- `green_patch_8`
- `img/targets/cc_halation.png`
- `img/targets/it87_test_chart_2.jpg`
- `img/test/portrait_leaves_32bit_linear_prophoto_rgb.tif`

输出：

- CPU output；
- GPU output；
- absolute diff heatmap；
- DeltaE map；
- stage timing JSON。

通过条件：

- 非随机场景无肉眼可见色偏、banding、边缘 halo 错位。
- spatial 场景的 halo/diffusion 能量守恒指标通过。
- GPU fast LUT 如果采用 trilinear 而非 PCHIP，文档和 UI/参数里必须标明质量等级。

## 具体实现建议

### 先修：缓存 prepared PCHIP LUT

当前 `apply_lut_pchip_3d()` 每次会：

```text
prepare_lut_pchip_3d(lut)
  -> _warn_if_lut_not_monotonic_3d()
  -> _prepare_lut_pchip_3d_impl()
```

本地 profile 显示 512x512 下两次 3D LUT 的 prepared/monotonicity 检查累计约 60 ms。建议先做：

```python
prepared = prepare_lut_pchip_3d(lut)
output = apply_lut_pchip_3d_prepared(prepared, image)
```

并在 `SpectralLUTService` 中按 enlarger/scanner 分别缓存。

这是 GPU 前置工作，因为 GPU 版也需要缓存 slopes/cell bounds。

### MLX LUT 内核策略

2D Hanatos LUT：

- 输入：`tc_raw HxWx2`，`tc_lut LxLx3`；
- 输出：`raw HxWx3`；
- 推荐 custom Metal kernel，直接实现 Mitchell cubic 或先实现 bilinear。

3D spectral LUT：

- 输入：`cmy HxWx3`，`lut LxLxLx3`；
- 输出：`log_raw/log_xyz HxWx3`；
- 快速方案：trilinear；
- 质量方案：PCHIP prepared slopes；
- 验收通过后再把 normalization 融合进 kernel，避免单独 `(data - xmin)/(xmax - xmin)` 的内存 pass。

### Gaussian/FFT 策略

当前 CPU `fast_gaussian_filter()` 有两条路径：

- sigma < 3：fused separable FIR；
- sigma >= 3：Young-van Vliet IIR。

GPU 可分为：

- 小 sigma：custom separable FIR，两 pass 或 fused tile。
- 大 sigma/halation：MPSImageGaussianBlur 或 FFT convolution。
- diffusion PSF：由于当前用 `fftconvolve`，MLX FFT 是最直接的 prototype。

注意：

- MPSImageGaussianBlur 官方说明是 approximate Gaussian；如果某些测试要求与 CPU IIR 或解析 Gaussian 高一致，需要用 custom convolution/MPSImageConvolution。
- GPU blur 边界模式必须对齐 CPU 当前的 reflect/replicate 语义，否则边缘误差会放大。

### 色彩转换策略

不要在 GPU path 中直接调用 `colour.RGB_to_XYZ()` 或 `colour.XYZ_to_RGB()` 每帧处理整图。建议：

1. CPU 端在参数 digest 或 stage 初始化时预计算：
   - input RGB -> XYZ matrix；
   - XYZ -> output RGB matrix；
   - illuminant/chromatic adaptation matrix；
   - CCTF piecewise 参数。
2. GPU 上执行 per-pixel matrix + piecewise CCTF。
3. 保留 `colour` CPU path 作为 reference。

### 随机颗粒策略

先不要为了 full GPU 而牺牲可重复性。建议三档：

- `cpu_exact`：当前 CPU/Numba/SciPy 行为，默认。
- `gpu_statistical`：GPU 统计一致，像素不逐一等同。
- `gpu_deterministic`：用自定义 stateless RNG，固定 seed 下逐像素稳定，但不承诺与 CPU 数列相同。

## 风险与缓解

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| GPU float32 与 CPU float64 差异 | regression baseline 失败或轻微色偏 | 分层容忍度、DeltaE 验收、CPU path 保持基准 |
| Host/GPU 往返过多 | 性能不升反降 | stage 内保持 backend array，只在最终输出转 NumPy |
| MLX lazy evaluation 计时不准 | benchmark 误判 | benchmark 中显式 `eval/synchronize` |
| LUT kernel JIT 或 prepared 重复 | cold/warm 混淆，帧间抖动 | kernel/LUT/prepared 缓存；cold start 单独报告 |
| Gaussian 边界语义不一致 | halo/blur 边缘 artifact | 单独边缘测试，明确 reflect/replicate 选择 |
| 随机颗粒不可逐像素对齐 | regression 不稳定 | stochastic path 使用统计验收，默认 CPU exact |
| MLX 平台限制 | 非 Apple Silicon 用户无法使用 | optional dependency + auto fallback |
| GUI 参数变更导致缓存陈旧 | 输出错误 | 缓存 key 包含 profile、LUT resolution、sensitivity、illuminant、filters、density curves |

## 推荐执行顺序

1. 做 Phase 0：benchmark 脚本 + prepared PCHIP LUT 缓存。
2. 做 Phase 1：MLX backend skeleton + 2D/3D LUT GPU pilot。
3. 做 Phase 2：filming/printing/scanning 的 per-pixel 光谱和色彩矩阵 GPU 化。
4. 做 Phase 3：Gaussian/FFT、density interpolation、DIR couplers。
5. 做 Phase 4：随机颗粒和 glare。
6. 做 Phase 5：GUI 开关、打包、文档。

这个顺序的好处是每一步都有清晰收益和可验收输出；即使中途停止，项目也已经获得 prepared LUT 缓存、benchmark、后端抽象和可选 GPU path，而不会落入半重写状态。
