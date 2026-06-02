> 这是英文原文的中文翻译。权威版本请参考英文原文。

# Halide / MLX 对等计划 - 2026-05-31

## 目标

在不改变 Spektrafilm 模拟语义的前提下，尽可能使实验性 Halide 后端达到当前 MLX 运行时路径的水平。验收标准基于实际挂钟时间、同步阶段计时、最终物化成本、相对于 CPU float64 和 MLX float32 的输出精度，以及测试。

## 当前架构审计

### 运行时后端流程

- `RuntimePhotoParams.settings.compute_backend` 和 `gpu_precision` 在 `SimulationPipeline.__init__` 中选择。
- `select_backend()` 返回 CPU、MLX、CuPy 或显式 Halide。`auto` 仍优先选择 MLX，然后是 CuPy，最后是 CPU；Halide 为严格手动选择。
- 选定的后端传递给 `SpectralLUTService`、`FilmingStage`、`PrintingStage` 和 `ScanningStage`。
- `SimulationPipeline.process()` 始终在 `_pipeline()` 退出时将最终输出物化为 `np.asarray(..., dtype=np.float64)`。这是端到端挂钟时间的一部分，必须单独报告。

### MLX 实现

- `MlxBackend` 是基于 `mlx.core` 的真实即时/延迟数组后端，具有 Metal 可用性探测和显式 `eval()` / `synchronize()` 钩子。
- MLX 性能来自阶段局部驻留：阶段代码调用后端操作进行高光增强、对数/幂运算、密度插值、光谱 LUT 应用、光谱链操作、滤波器和 CCTF。
- `gpu/kernels/density.py`、`filters.py`、`lut.py` 和 `color.py` 包含 MLX 特有的自定义 Metal 内核或 MLX 原生操作，用于密度插值、高斯/IIR 滤波器、LUT、高光增强、CCTF 和矩阵变换。
- `PrintingStage` 预先将静态光谱表转换为后端数组，`SpectralLUTService` 保留后端 LUT 副本。这避免了重复的 numpy 到 MLX 传输。

### Halide 实现

- `HalideBackend` 目前使用 Python Halide JIT，目标为 `hl.get_host_target()`。仅支持 float32，并按实例缓存 Func 管道。
- 其通用的 `ArrayBackend` 方法大多委托给 NumPy / opt_einsum。这意味着选择 `compute_backend="halide"` 并不会自动使正常运行时路径使用 Halide 内核。
- 已实现的 Halide JIT 内核包括 RGB 矩阵、3D LUT、光谱微内核、FIR 模糊、CCTF 编码/解码、1D 插值和 2D LUT，但大多数正常内核分发仍然绕过它们。
- `gpu/kernels/lut.py` 通过 `backend.apply_lut_trilinear_3d()` 将 3D LUT 分发到 Halide。密度、滤波器和 CCTF 运行时路径大多通过通用协议方法或 CPU 转换回退。
- 现有文档记录了相同的问题：Halide 在许多微内核上是正确的，在 3D LUT 上速度较快，但端到端较慢，因为管道不是粗粒度或融合的。

### 阶段级差异

- `FilmingStage.expose()` 受益于后端高光增强、LUT、滤波器和后端 log10。Halide 仅获得部分收益，因为许多后端辅助函数不会分发到 Halide 特定方法。
- `FilmingStage.develop()` 调用后端密度插值。MLX 使用 Metal 插值内核；Halide 目前通过后端转换回退到 CPU 插值。
- `PrintingStage.expose()` 是主要目标。MLX 保持静态光谱表驻留并使用后端操作。Halide 目前对大多数链通过 NumPy 进行物化或计算，因此失去了 Halide 融合的优势。
- `ScanningStage.scan()` 是第二个主要目标。CMY 到 log XYZ 链可以融合为一个 Halide 管道；目前它被表达为独立的后端协议操作。
- 颗粒度仍然是兼容性路径。主要精度/性能验证使用颗粒度关闭和光晕开启；颗粒度开启仅作为冒烟测试。

## 为什么 Halide 目前比 CPU 慢

1. 运行时未调用大多数 Halide JIT 内核。`HalideBackend` 中的方法存在，但 `gpu/kernels/density.py`、`filters.py` 和颜色分发不像 MLX 方法那样被触及。
2. Halide 被用作许多小的 JIT 内核，而不是粗粒度的融合管道。Python 边界成本、`Buffer` 构造、转置和逐内核分发抵消了收益。
3. 通用的 `HalideBackend.einsum()`、`power()`、`log10()` 和 `matmul()` 是 NumPy 操作，而非 Halide 操作。
4. 光谱路径创建或隐含巨大的 `H x W x 81` 中间结果（`density_spectral`、`light`）。MLX 通过设备驻留的延迟执行可以更好地容忍这一点；Halide 应融合这些归约，使中间结果不被单独物化。
5. 计时运行可能包含 Halide JIT 编译。基准测试必须将预热/JIT 与计时运行分开。
6. Halide 上的 `supports_gpu=True` 目前表示"实验性加速器后端"，不一定是 Metal/GPU 目标。除非测量证明有真正的端到端收益，否则主机目标应保持实验性。

## 待验证假设

- H1：将 `cmy_to_log_xyz_backend()` 分发到融合的 Halide CMY 到 logXYZ 管道，与通用 NumPy/opt_einsum 相比，减少 `ScanningStage.scan` 时间。
- H2：将 `PrintingStage._film_cmy_to_print_log_raw()` 分发到融合的 Halide CMY 到 logRaw 管道，通过消除单独的 `density_spectral` 和 `light` 物化，减少 `PrintingStage.expose` 时间。
- H3：排除 JIT 的预热 Halide 运行明显快于当前 Halide 挂钟时间，即使首次运行仍然较慢。
- H4：Halide 精度保持在现有 float32 范围内：全管道相对于 CPU float64 的 PSNR >= 52 dB，且 mean_diff 不超过相同配置下 MLX mean_diff 的 1.5 倍。
- H5：如果 Halide 在融合光谱路径后仍然比 CPU 慢，则剩余瓶颈在于密度插值、光晕 IIR/指数滤波器、Python Buffer 构造或仅主机 Halide 目标限制。

## 计划文件更改

### 基准测试和诊断

- 创建 `scripts/benchmark_halide_mlx_parity.py`
  - 加载已知的本地 DNG 或确定性生成的回退。
  - 运行 CPU float64、CPU float32（如支持）、MLX float32（如可用）和 Halide float32（如可用）。
  - 支持 `--size full` 和 `--size 2048x1536`。
  - 将预热/JIT 与计时运行分开。
  - 报告挂钟时间、同步阶段时间、最终物化时间、输出形状/dtype/后端和转换计数器。
  - 将 JSON 和 Markdown 工件写入 `docs/dev/benchmark-artifacts/`。

- 在 `tests/test_halide_mlx_benchmark.py` 中添加基准测试辅助函数的测试。
  - 保持单元测试为合成且快速；不要在 pytest 中运行完整的 12MP。

### Halide 分发和融合内核

- 修改 `src/spektrafilm/gpu/halide_backend.py`
  - 为 HWC 运行时数组添加融合的 `cmy_to_log_xyz()`。
  - 为打印曝光光谱链添加融合的 `cmy_to_log_raw()`。
  - 按波长数和输出通道数缓存融合管道。
  - 保留现有微内核 API 和清理行为。

- 修改 `src/spektrafilm/gpu/kernels/density.py`
  - 当存在时，将 `cmy_to_log_xyz_backend()` 分发到 `backend.cmy_to_log_xyz()`。
  - 保持现有 MLX/CuPy/CPU 语义不变。

- 修改 `src/spektrafilm/runtime/stages/printing.py`
  - 对 Halide 使用 `backend.cmy_to_log_raw()`（如可用）。
  - 保持当前 MLX 路径和 CPU 路径完整。
  - 不禁用光晕、光谱模拟、LUT 或扫描语义。

- 可选修改 `src/spektrafilm/gpu/kernels/filters.py`，仅在基准测试数据证明滤波器占主导后进行。初始范围是光谱融合，因为它是已知最大的 Halide 端到端瓶颈。

### 测试

- 扩展 `tests/test_halide_spectral.py`
  - 验证融合的 `cmy_to_log_xyz()` 和 `cmy_to_log_raw()` 与 NumPy 参考实现的一致性。
  - 验证管道缓存重用和清理。

- 扩展 `tests/test_gpu_density.py`
  - 验证通用 `cmy_to_log_xyz_backend()` 在存在时分发到后端专用方法。

- 扩展 `tests/test_gpu_pipeline.py` 或添加专注的集成测试
  - 使用配置了 LUT/空间效果的小图像 Halide 管道运行测试，以验证融合路径。

## 基准测试契约

基准测试工件必须包括：

- 输入标识：路径或生成种子、形状、dtype、兆像素。
- 配置：胶片配置文件、打印配置文件、颗粒度设置、光晕设置、LUT 设置、色彩空间、自动曝光状态。
- 后端标识：请求的后端、选定的后端、精度、Halide 目标、MLX 可用性。
- 预热/JIT 计时与计时运行分开。
- 每个后端的端到端挂钟时间。
- 每阶段同步计时：
  - preprocess
  - film.expose
  - film.develop
  - print.expose
  - print.develop
  - scan
- 最终物化和输出转换时间。
- 每阶段输入/输出元数据：
  - shape
  - dtype
  - Python 类型 / 后端类型
  - bytes
- 转换观察：
  - 调用 `backend.asarray`
  - 调用 `backend.to_numpy`
  - 显式最终 `np.asarray`
- 精度指标：
  - max_diff
  - mean_diff
  - median_diff
  - RMSE
  - PSNR
  - 每通道最大值和均值

未同步的仅分发计时仅允许作为次要上下文，不得用作性能判定。

## 验收标准

### 硬性最低要求

- Halide 输出必须保持有效且有限。
- CPU 默认行为和 MLX 行为不得退化。
- Halide 不得成为默认后端。
- Halide 不得通过禁用光晕、光谱模拟、LUT、扫描、输出 CCTF 或更改配置文件/大小语义来获得速度提升。
- 计时的 Halide 运行必须将 JIT/预热排除在计时运行之外。

### 精度

- 主要参考：CPU float64。
- 次要参考：MLX float32。
- 主要配置：`kodak_portra_400 / kodak_portra_endura`，颗粒度关闭，光晕开启。
- Halide 与 CPU 全管道下限：
  - PSNR >= 52 dB。
  - mean_diff <= 相同配置下 MLX mean_diff 的 1.5 倍。
  - max_diff 应处于 MLX 的数量级；如果 > 6e-2，记录并隔离来源。

### 性能

- 硬性目标：12MP Halide 挂钟时间快于 CPU float64。
- 首选目标：12MP Halide 挂钟时间 >= 2 倍 CPU 加速。
- 延伸目标：在当前 MLX 挂钟时间的 2 倍以内，或有基准测试支持的解释说明主机 Halide 为何无法达到。
- 2048x1536 必须单独测量，以揭示大小缩放和 JIT 摊销情况。

## 风险和回滚

- 融合的 Halide 光谱内核可能提高速度但增加编译时间。基准测试将单独报告预热。
- 融合内核可能重复光谱公式。测试必须锁定与现有 NumPy/MLX 链的对等性。
- Halide Python JIT 在此运行时可能仍然仅限主机，限制了相对于 MLX Metal 的速度。如果是这样，保持 Halide 实验性，并将 AOT/Metal/Generator 路线记录为后续工作。
- `Buffer` 维度排序容易出错。测试必须覆盖非方形图像和通道排序。
- 显式 Halide 分发之外的任何行为更改都是退化。CPU 和 MLX 路径是回滚边界。

## 实现顺序

1. 为融合 Halide 光谱方法和分发添加失败测试。
2. 实现基准测试辅助函数/脚本，附带合成快速测试。
3. 实现 `HalideBackend.cmy_to_log_xyz()` 并从 `gpu/kernels/density.py` 分发。
4. 实现 `HalideBackend.cmy_to_log_raw()` 并从 `PrintingStage` 分发。
5. 运行 Halide 专注测试和 GPU 对等测试。
6. 在 2048x1536 和 12MP（如本地 DNG 可用）上运行基准测试。
7. 将基准测试/精度结果保存到 `docs/dev/benchmark-artifacts/`。
8. 重新运行自审问题并决定 Halide 是否保持实验性。

## 结果文档中需回答的自审问题

- Halide 是否真正执行了 Halide 融合路径，还是静默回退到了 CPU？
- 计时运行是否排除了 JIT 和预热？
- 阶段计时是否已同步并与最终转换分开？
- 是否有任何加速来自渲染语义的更改？
- Halide 输出在数值上是否与 CPU 和 MLX 可比？
- CPU 或 MLX 行为是否退化？
- 12MP 和 2048x1536 输入是否均已测试或被如实跳过？
- 颗粒度关闭 + 光晕开启和颗粒度开启冒烟测试是否均已运行？
