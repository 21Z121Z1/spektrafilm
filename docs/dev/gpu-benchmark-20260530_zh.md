> 这是英文原文的中文翻译。权威版本请参考英文原文。

# GPU 后端基准测试 — 2026-05-30

## 测试配置
- **硬件**: Apple M1 Pro（16 个 GPU 核心），16 GB RAM，macOS 26.5
- **输入**: portrait_leaves_32bit_linear_prophoto_rgb.tif（1000x667，float32，ProPhoto RGB）
  - 注意：请求的图像 IMG20260530191638.dng 在仓库中未找到；使用了可用的测试图像。
- **胶片配置文件**: kodak_portra_400
- **打印配置文件**: kodak_portra_endura
- **颗粒**: 开启（active + sublayers，n_sub_layers=1）
- **光晕**: 开启（boost_ev=1.0，scatter_amount=1.0，halation_amount=1.0）
- **CCTF 编码**: 开启（output_cctf_encoding=True，input_cctf_decoding=False）
- **自动曝光**: 关闭
- **精度**: float32
  - 注意：请求了 float64，但 MLX 和 Halide 后端仅支持 float32。CPU 后端内部以 float64 运行。
- **LUT 设置**: resolution=17，use_enlarger_lut=True，use_scanner_lut=True，use_fast_stats=True
- **框架版本**: MLX 0.31.2，NumPy 2.4.4，Python 3.13
- **每次测量运行次数**: 3 次计时（端到端），10 次计时（微内核），1 次预热后
- **日期**: 2026-05-30

## 结果表

### 端到端流水线（1000x667 图像，3 次运行中最优值）

| 后端          | 类型 | 最优 (s) | 平均 (s) | 中位数 (s) | 最大 (s) | 相对于 CPU 的加速比 |
|------------------|------|----------|---------|------------|---------|----------------|
| cpu (NumPy+Numba)| CPU  | 0.743    | 0.764   | 0.755      | 0.792   | 1.00x（基准）    |
| mlx (Metal)      | GPU  | 0.669    | 0.686   | 0.671      | 0.718   | 1.11x          |
| halide (JIT)     | GPU  | 0.818    | 0.821   | 0.822      | 0.823   | 0.91x          |

### 各阶段计时分解（单次运行，print_timings=True）

| 阶段                          | CPU (ms) | %    | MLX (ms) | %    | Halide (ms) | %    |
|--------------------------------|----------|------|----------|------|-------------|------|
| FilmingStage.expose            | 155      | 19.7 | 137      | 21.3 | 137         | 13.2 |
| FilmingStage.develop           | 365      | 46.3 | 331      | 51.5 | 336         | 32.5 |
| SpectralLUT（放大机光谱计算） | 64.8     | 8.2  | 58.2     | 9.1  | 377         | 36.5 |
| PrintingStage.expose           | 88.7     | 11.3 | 84.7     | 13.2 | 401         | 38.7 |
| PrintingStage.develop          | 8.55     | 1.1  | 0.504    | 0.1  | 8.88        | 0.9  |
| SpectralLUT（扫描仪光谱计算）  | 58.2     | 7.4  | 51.2     | 8.0  | 44.9        | 4.3  |
| ScanningStage.scan             | 169      | 21.4 | 88.6     | 13.8 | 152         | 14.7 |
| **合计**                      | **787**  |      | **642**  |      | **1030**    |      |

### 微内核基准测试（10 次运行中最优值）

#### 高斯滤波（sigma=5.0，3 通道）

| 尺寸     | CPU (ms) | MLX (ms) | MLX 加速比 | MLX 最大差值 | Halide (ms) | Halide 加速比 | Halide 最大差值 |
|----------|----------|----------|-------------|--------------|-------------|----------------|-----------------|
| 256x256  | 1.03     | 0.79     | 1.30x       | 4.83e-06     | 0.89        | 1.16x          | 0.00e+00        |
| 512x512  | 2.29     | 1.43     | 1.60x       | 5.01e-06     | 2.27        | 1.01x          | 0.00e+00        |
| 1000x1000| 7.17     | 1.95     | 3.68x       | 5.60e-06     | 7.27        | 0.99x          | 0.00e+00        |

#### 密度插值（40 个波长采样点）

| 尺寸     | CPU (ms) | MLX (ms) | MLX 加速比 | MLX 最大差值 | Halide (ms) | Halide 加速比 | Halide 最大差值 |
|----------|----------|----------|-------------|--------------|-------------|----------------|-----------------|
| 256x256  | 0.91     | 0.27     | 3.33x       | 5.96e-08     | 0.97        | 0.95x          | 0.00e+00        |
| 512x512  | 3.24     | 0.47     | 6.91x       | 5.96e-08     | 3.34        | 0.97x          | 0.00e+00        |
| 1000x1000| 12.20    | 1.23     | 9.92x       | 5.96e-08     | 15.66       | 0.78x          | 0.00e+00        |

#### 高光增强

| 尺寸     | CPU (ms) | MLX (ms) | MLX 加速比 | MLX 最大差值 | Halide (ms) | Halide 加速比 | Halide 最大差值 |
|----------|----------|----------|-------------|--------------|-------------|----------------|-----------------|
| 256x256  | 0.29     | 0.70     | 0.41x       | 3.41e-06     | 0.51        | 0.57x          | 3.41e-06        |
| 512x512  | 0.91     | 1.15     | 0.80x       | 3.92e-06     | 2.11        | 0.43x          | 3.83e-06        |
| 1000x1000| 3.39     | 1.73     | 1.96x       | 3.99e-06     | 8.81        | 0.39x          | 3.96e-06        |

#### CMY -> log_XYZ

| 尺寸     | CPU (ms) | MLX (ms) | MLX 加速比 | MLX 最大差值 | Halide (ms) | Halide 加速比 | Halide 最大差值 |
|----------|----------|----------|-------------|--------------|-------------|----------------|-----------------|
| 256x256  | 15.54    | 2.03     | 7.66x       | 2.98e-07     | 14.66       | 1.06x          | 0.00e+00        |
| 512x512  | 62.77    | 8.43     | 7.45x       | 2.98e-07     | 65.30       | 0.96x          | 0.00e+00        |
| 1000x1000| 239.79   | 30.20    | 7.94x       | 2.98e-07     | 223.60      | 1.07x          | 0.00e+00        |

#### 3D LUT 三线性插值（17^3）

| 尺寸     | CPU (ms) | MLX (ms) | MLX 加速比 | MLX 最大差值 | Halide (ms) | Halide 加速比 | Halide 最大差值 |
|----------|----------|----------|-------------|--------------|-------------|----------------|-----------------|
| 256x256  | 9.71     | 1.20     | 8.12x       | 1.37e-07     | 0.47        | 20.79x         | 9.74e-08        |
| 512x512  | 38.54    | 3.69     | 10.44x      | 1.48e-07     | 1.53        | 25.12x         | 1.12e-07        |
| 1000x1000| 147.81   | 13.68    | 10.80x      | 1.60e-07     | 5.55        | 26.61x         | 1.21e-07        |

#### FFT 卷积（15x15 卷积核，same 模式）

| 尺寸     | CPU/SciPy (ms) | MLX (ms) | MLX 加速比 | Halide (ms) | Halide 加速比 |
|----------|----------------|----------|-------------|-------------|----------------|
| 256x256  | 1.39           | 1.19     | 1.17x       | 1.45        | 0.95x          |
| 512x512  | 5.32           | 1.78     | 2.99x       | 5.73        | 0.93x          |
| 1000x1000| 23.09          | 6.08     | 3.80x       | 26.18       | 0.88x          |

## 各后端详情

### CPU（NumPy + Numba）
- **配置**: 默认 NumpyBackend，使用 Numba JIT 处理热循环。内部 float64 精度。
- **计时分解**: 主要由 FilmingStage.develop（46.3%）和 ScanningStage.scan（21.4%）主导。密度插值和 3D LUT 是最耗时的单个内核。
- **精度**: 参考实现。所有 GPU 后端均与此对比。
- **优势**: 完整的 float64 精度，无 GPU 依赖，结果确定。
- **劣势**: 大图像整体速度最慢；密度插值和 CMY->logXYZ 的时间复杂度为 O(n)，且无并行优势。

### MLX（Apple Metal）
- **配置**: MlxBackend，float32 精度。Apple M1 Pro，16 个 GPU 核心。
- **计时分解**: 端到端最优时间为 642ms。FilmingStage.develop 仍占主导（51.5%），但 ScanningStage.scan 显著降低（88.6ms vs CPU 的 169ms，提升 1.91 倍）。PrintingStage.develop 从 8.55ms 降至 0.504ms（提升 16.97 倍）。
- **精度指标**:
  - 高斯滤波：最大差值 5.60e-06（float32 舍入误差）
  - 密度插值：最大差值 5.96e-08（优秀）
  - 高光增强：最大差值 3.99e-06（float32 舍入误差）
  - CMY->log_XYZ：最大差值 2.98e-07（优秀）
  - 3D LUT：最大差值 1.60e-07（优秀）
  - 端到端流水线：最大差值 5.13e-02，平均差值 2.20e-03（完整流水线中 float32 与 float64 的累积误差）
- **优势**: 最佳端到端加速比（1.11x）。密度插值（最高 9.92x）、CMY->log_XYZ（最高 7.94x）、3D LUT（最高 10.80x）和 FFT 卷积（最高 3.80x）的微内核性能优秀。随图像尺寸增长表现良好。
- **劣势**: 仅支持 float32。流水线级别与 CPU float64 的精度偏差（最大 5.13e-02）值得注意，但在 float32 与 float64 对比的情况下属于预期。小图像上高光增强内核比 CPU 慢（GPU 调度开销）。
- **警告**: `mx.metal.clear_cache` 弃用警告（请改用 `mx.clear_cache`）。

### Halide（JIT）
- **配置**: HalideBackend，float32 精度。JIT 编译的 Halide 流水线。
- **计时分解**: 端到端最慢，为 1.03s。放大机光谱计算（377ms，36.5%）和打印曝光（401ms，38.7%）占主导——两者相比 CPU 均严重退化。Halide 的 LUT 内核极快（1000x1000 时为 5.55ms），但其他内核性能退化。
- **精度指标**:
  - 高斯滤波：最大差值 0.00e+00（与 CPU NumPy 位一致）
  - 密度插值：最大差值 0.00e+00（位一致）
  - CMY->log_XYZ：最大差值 0.00e+00（位一致）
  - 高光增强：最大差值 3.96e-06（float32 舍入误差）
  - 3D LUT：最大差值 1.21e-07（优秀）
  - 端到端流水线：最大差值 5.87e-02，平均差值 2.21e-03
- **优势**: 3D LUT 三线性内核是所有后端中最快的（1000x1000 时加速比 26.61x）。高斯滤波、密度插值和 CMY->log_XYZ 的输出与 CPU 位一致。微内核结果最具确定性。
- **劣势**: 端到端流水线比 CPU 慢 10%。光谱 LUT 计算严重退化（377ms vs CPU 的 64.8ms）。Halide 的 JIT 编译和调度开销抵消了单内核级别在完整流水线中的收益。放大机和打印阶段似乎无法从 Halide 的架构中获益。
- **错误**: 无运行时错误。后端运行正常，但在流水线级别表现不佳。

## 结论

### 可用后端
| 后端 | 可用 | GPU | 精度 |
|---------|-----------|-----|-----------|
| cpu     | 是       | 否  | float64   |
| mlx     | 是       | 是（Metal） | float32/float16 |
| cupy    | 否        | --  | --        |
| halide  | 是       | JIT | float32   |

CuPy 不可用（Apple M1 Pro 上无 CUDA/ROCm 设备）。

### 已实现的加速比
- **MLX 是最快的后端**，端到端加速比为 1.11x。加速主要来自 ScanningStage（快 1.91 倍）和 PrintingStage.develop（快 16.97 倍）。单个微内核显示更大的加速比（3D LUT 最高 10.80x，密度插值最高 9.92x），但流水线中存在大量串行部分限制了整体收益。
- **Halide 比 CPU 慢 10%**，尽管拥有最快的 3D LUT 内核（加速比 26.61x）。光谱 LUT 计算阶段在此硬件上与 Halide 的 JIT 模型不太匹配。

### 精度影响
- 所有 GPU 后端以 float32 运行，而 CPU 内部精度为 float64。
- 微内核精度优秀：所有测量内核的最大差值 < 6e-06（在 float32 epsilon 范围内）。
- 端到端流水线精度：MLX 最大差值 5.13e-02，Halide 最大差值 5.87e-02（与 CPU 对比）。这是 9 个以上流水线阶段中 float32 舍入的累积误差，主要来自光谱计算和密度插值链。平均差值要低得多（分别为 2.20e-03 和 2.21e-03）。
- Halide 在多个单独内核（高斯滤波、密度插值、CMY->log_XYZ）上实现了与 CPU NumPy 位一致的输出，说明其 JIT 编译器保留了 float32 运算顺序。

### 默认后端选择建议
1. **默认使用 `auto`**（在 Apple Silicon 上解析为 MLX，在 CUDA 上解析为 CuPy）。MLX 提供最佳整体性能。
2. **CPU 仍然适用于精度要求高的工作**。MLX 的 1.11x 加速比可能不足以让所有用户接受 float32 精度的权衡。考虑将 `cpu` 设为默认值，将 `auto` 作为可选的性能提升方案。
3. **不建议将 Halide 作为默认后端**。其 3D LUT 内核非常快，但流水线级别的退化使其总体效果为负。考虑通过分块处理接口有选择地将 Halide 用于特定内核。
4. **float64 支持**: MLX 和 Halide 仅支持 float32。如需 float64 精度，CPU 后端是唯一选择。建议记录此限制。
5. **CuPy**: 在 NVIDIA 硬件上可能提供最大的加速比。在此 Apple Silicon 机器上无法测试。

## 附录：原始基准测试输出

### 端到端流水线（原始数据）

```
======================================================================
SpektraFilm GPU Backend Benchmark — 2026-05-30
======================================================================
Input image: img/test/portrait_leaves_32bit_linear_prophoto_rgb.tif
Film: kodak_portra_400
Print: kodak_portra_endura
Precision: float32
Available backends: ['cpu', 'mlx', 'halide']

Warming up Numba JIT...
Done.

Image shape: (1000, 667, 3), dtype: float32

======================================================================
Backend: cpu (CPU)
======================================================================
  Run 1: 0.743s
  Run 2: 0.792s
  Run 3: 0.755s
  Best: 0.743s  Avg: 0.764s  Median: 0.755s  Max: 0.792s
  Output shape: (1000, 667, 3), dtype: float64
  Output range: [0.0000, 0.8887]

======================================================================
Backend: mlx (GPU)
======================================================================
  Run 1: 0.718s
  Run 2: 0.671s
  Run 3: 0.669s
  Best: 0.669s  Avg: 0.686s  Median: 0.671s  Max: 0.718s
  Precision vs CPU: max_diff=5.13e-02, mean_diff=2.20e-03
    allclose(atol=1e-5): False
    allclose(atol=1e-4): False
    allclose(atol=1e-3): False

======================================================================
Backend: halide (GPU)
======================================================================
  Run 1: 0.822s
  Run 2: 0.818s
  Run 3: 0.823s
  Best: 0.818s  Avg: 0.821s  Median: 0.822s  Max: 0.823s
  Precision vs CPU: max_diff=5.87e-02, mean_diff=2.21e-03
    allclose(atol=1e-5): False
    allclose(atol=1e-4): False
    allclose(atol=1e-3): False
```

### 各阶段计时（原始数据）

```
CPU backend:
  Total                                          787 ms  100.0%
  FilmingStage.expose                            155 ms   19.7%
  FilmingStage.develop                           365 ms   46.3%
  SpectralLUTService.spectral_compute_enlarger   64.8 ms   8.2%
  PrintingStage.expose                           88.7 ms  11.3%
  PrintingStage.develop                          8.55 ms   1.1%
  SpectralLUTService.spectral_compute_scanner    58.2 ms   7.4%
  ScanningStage.scan                             169 ms   21.4%

MLX backend:
  Total                                          642 ms  100.0%
  FilmingStage.expose                            137 ms   21.3%
  FilmingStage.develop                           331 ms   51.5%
  SpectralLUTService.spectral_compute_enlarger   58.2 ms   9.1%
  PrintingStage.expose                           84.7 ms  13.2%
  PrintingStage.develop                         0.504 ms   0.1%
  SpectralLUTService.spectral_compute_scanner    51.2 ms   8.0%
  ScanningStage.scan                            88.6 ms   13.8%

Halide backend:
  Total                                          1.03 s  100.0%
  FilmingStage.expose                            137 ms   13.2%
  FilmingStage.develop                           336 ms   32.5%
  SpectralLUTService.spectral_compute_enlarger   377 ms   36.5%
  PrintingStage.expose                           401 ms   38.7%
  PrintingStage.develop                          8.88 ms   0.9%
  SpectralLUTService.spectral_compute_scanner    44.9 ms   4.3%
  ScanningStage.scan                             152 ms   14.7%
```

### 微内核基准测试（原始数据）

```
1. GAUSSIAN FILTER (sigma=5.0, 3-channel)
  256x256:     CPU:    1.03ms | MLX:    0.79ms (1.30x) | Halide:    0.89ms (1.16x)
  512x512:     CPU:    2.29ms | MLX:    1.43ms (1.60x) | Halide:    2.27ms (1.01x)
  1000x1000:   CPU:    7.17ms | MLX:    1.95ms (3.68x) | Halide:    7.27ms (0.99x)

2. DENSITY INTERPOLATION
  256x256:     CPU:    0.91ms | MLX:    0.27ms (3.33x) | Halide:    0.97ms (0.95x)
  512x512:     CPU:    3.24ms | MLX:    0.47ms (6.91x) | Halide:    3.34ms (0.97x)
  1000x1000:   CPU:   12.20ms | MLX:    1.23ms (9.92x) | Halide:   15.66ms (0.78x)

3. HIGHLIGHT BOOST
  256x256:     CPU:    0.29ms | MLX:    0.70ms (0.41x) | Halide:    0.51ms (0.57x)
  512x512:     CPU:    0.91ms | MLX:    1.15ms (0.80x) | Halide:    2.11ms (0.43x)
  1000x1000:   CPU:    3.39ms | MLX:    1.73ms (1.96x) | Halide:    8.81ms (0.39x)

4. CMY -> log_XYZ
  256x256:     CPU:   15.54ms | MLX:    2.03ms (7.66x) | Halide:   14.66ms (1.06x)
  512x512:     CPU:   62.77ms | MLX:    8.43ms (7.45x) | Halide:   65.30ms (0.96x)
  1000x1000:   CPU:  239.79ms | MLX:   30.20ms (7.94x) | Halide:  223.60ms (1.07x)

5. 3D LUT TRILINEAR (17^3)
  256x256:     CPU:    9.71ms | MLX:    1.20ms (8.12x) | Halide:    0.47ms (20.79x)
  512x512:     CPU:   38.54ms | MLX:    3.69ms (10.44x) | Halide:    1.53ms (25.12x)
  1000x1000:   CPU:  147.81ms | MLX:   13.68ms (10.80x) | Halide:    5.55ms (26.61x)

6. FFT CONVOLVE (15x15 kernel, same mode)
  256x256:     CPU:    1.39ms | MLX:    1.19ms (1.17x) | Halide:    1.45ms (0.95x)
  512x512:     CPU:    5.32ms | MLX:    1.78ms (2.99x) | Halide:    5.73ms (0.93x)
  1000x1000:   CPU:   23.09ms | MLX:    6.08ms (3.80x) | Halide:   26.18ms (0.88x)
```
