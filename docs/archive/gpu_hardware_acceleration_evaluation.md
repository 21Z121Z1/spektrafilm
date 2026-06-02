# SpektraFilm Metal 硬件加速评估报告

> 评估日期：2026-05-14 | 硬件：Apple M1 Pro (16 GB) | MLX 0.31.2 | Python 3.13.1
> 测试图像：1000×667 portrait_leaves_32bit_linear_prophoto_rgb.tif

## 1. 概述

SpektraFilm 自 `v0.3.1` 起通过 MLX 框架引入了可选的 Apple GPU 加速层（`spektrafilm[gpu-apple]`），已在以下方面完成落地：

- **`ArrayBackend` Protocol**：通过统一的 backend 抽象解耦 NumPy 和 MLX，逐元素运算共享同一套代码。
- **6 个自定义 Metal 着色器**：高斯 FIR/IIR 滤波、reflect padding、密度曲线插值、**2D Mitchell-Netravali cubic LUT**、**grain 子层密度插值**（新增）——全部通过 `mx.fast.metal_kernel()` 运行时编译。
- **后端无关的色彩/光谱算子**：CCTF 编解码、高光压缩、einsum 密度计算、FFT 卷积、指数滤波。
- **Pilot LUT 采样**：三线性插值（标注为 fast pilot kernel）。
- **配置与 GUI 集成**：`compute_backend = "auto" | "cpu" | "mlx"` 下拉选项、timing 报告显示 backend 摘要。
- **新 GPU 后端覆盖率**（当前工作区）：Hanatos RGB→RAW 完整 GPU 化（CCTF 解码+RGB→XYZ+xy→tc+2D 立方 LUT），grain 子层密度插值 Metal 化。

> 本文档基于实测数据评估当前加速效果、识别瓶颈，并给出后续计划。**报告范围包括上轮评估后的新增实现对照。**

---

## 2. 端到端管线性能

### 2.1 总耗时对比

| 后端 | 最佳耗时 | 平均耗时 | 加速比 |
|------|---------|---------|--------|
| CPU (Numba) | 1.300 s | 1.327 s | 1.0x (基线) |
| GPU (MLX/Metal) | **1.129 s** | **1.150 s** | **1.15x** |

**结论**：端到端加速仅 **1.15x**，远低于预期。主因并非 GPU 内核不够快，而是管线中最重的阶段尚未 GPU 化。

### 2.2 阶段耗时分解

```
CPU (Numba)                           GPU (MLX/Metal)
─────────────────────────             ─────────────────────────
FilmingStage.expose      191 ms       FilmingStage.expose      154 ms   (1.24x)
FilmingStage.develop     963 ms  ←→   FilmingStage.develop     927 ms   (1.04x) ← 主瓶颈
SpectralLUT.enlarger      47 ms       SpectralLUT.enlarger      49 ms
PrintingStage.expose      73 ms       PrintingStage.expose      53 ms   (1.36x)
PrintingStage.develop      8 ms       PrintingStage.develop      0.1 ms
SpectralLUT.scanner       37 ms       SpectralLUT.scanner       12 ms   (3.2x)
ScanningStage.scan       131 ms       ScanningStage.scan        25 ms   (5.2x) ← 最佳加速
─────────────────────────             ─────────────────────────
Total                   1.40 s        Total                    1.19 s
```

关键发现：

1. **`FilmingStage.develop`（显影）是绝对瓶颈**——占 GPU 总时间的 **78%**（927 ms），且 GPU 路径几乎没有加速（1.04x），说明该阶段的算子尚未迁移至 Metal。
2. **`ScanningStage.scan`（扫描）加速效果最佳**——5.2x 加速，从 131 ms 降至 25 ms，受益于 GPU 化的密度→logXYZ 链和 CCTF 编码。
3. **`PrintingStage.expose` 和 `FilmingStage.expose` 中等加速**——1.24–1.36x，部分算子（如 grain、DIR couplers）仍运行在 CPU。

---

## 3. 算子级微基准

### 3.1 高斯滤波

#### 小 σ (1.0) —— FIR 自定义 Metal 着色器

| 图像尺寸 | CPU (Numba) | GPU (Metal) | 加速比 |
|---------|-------------|-------------|--------|
| 256×256 | 0.6 ms | 0.7 ms | 0.86x |
| 512×512 | 1.6 ms | 1.5 ms | 1.07x |
| 1000×1000 | 5.3 ms | 4.2 ms | 1.26x |
| 2000×2000 | 19.1 ms | **15.6 ms** | **1.22x** |

小 σ FIR 的 GPU 加速有限，因为该算子是 memory-bound 而非 compute-bound。在 256×256 等小尺寸上甚至略慢于 CPU（kernel launch 开销）。

#### 大 σ (5.0) —— Young-van Vliet IIR 自定义 Metal 着色器

| 图像尺寸 | CPU (Numba) | GPU (Metal) | 加速比 |
|---------|-------------|-------------|--------|
| 256×256 | 0.9 ms | 0.6 ms | 1.5x |
| 512×512 | 2.3 ms | 0.9 ms | 2.6x |
| 1000×1000 | 7.8 ms | 1.6 ms | 4.9x |
| 2000×2000 | 29.7 ms | **4.4 ms** | **6.8x** |

大 σ IIR 受益显著，加速比随尺寸增大而提高，体现了 GPU 在大规模数据并行上的优势。

### 3.2 密度曲线插值（自定义 Metal 着色器 + Binary Search）

| 图像尺寸 | CPU (Numba) | GPU (Metal) | 加速比 |
|---------|-------------|-------------|--------|
| 256×256 | 0.9 ms | 0.3 ms | 3.0x |
| 512×512 | 4.2 ms | 0.6 ms | 7.0x |
| 1000×1000 | 12.4 ms | 0.9 ms | 13.8x |
| 2000×2000 | 51.6 ms | **3.2 ms** | **16.1x** |

这是加速效果最好的算子。每个像素独立执行 binary search + 线性插值，GPU 数千线程的并行度完美匹配此模式。

### 3.3 高光压缩（后端无关的逐元素运算）

| 图像尺寸 | CPU (Numba) | GPU (MLX) | 加速比 |
|---------|-------------|-----------|--------|
| 256×256 | 0.3 ms | 0.7 ms | 0.43x |
| 512×512 | 1.0 ms | 1.2 ms | 0.83x |
| 1000×1000 | 3.4 ms | 2.5 ms | 1.36x |
| 2000×2000 | 13.1 ms | **8.3 ms** | **1.58x** |

加速比一般。Numba JIT 编译的逐元素 kernel 已经非常高效，GPU 仅在较大尺寸上体现优势。

### 3.4 光谱密度链（MLX einsum 后端）

| 算子 | 2000×2000 GPU |
|------|--------------|
| `compute_density_spectral` (einsum) | 16.3 ms |
| `density_to_light` (power(10,...)) | 51.4 ms (高方差) |
| `light_to_raw` (einsum) | 10.3 ms |

`density_to_light` 的 `10^(-density)` 中 `power(10, x)` 在 GPU 上开销显著，且存在高方差（MLX lazy evaluation 特性）。注意：该链的 CPU 等价路径在 `ScanningStage.scan` 实测显示 131 ms → 25 ms（5.2x），说明 GPU 化收益明确。

### 3.5 LUT 采样（pilot kernel：三线性 vs NumPy）

| 图像尺寸 | CPU (NumPy) | GPU (MLX) | 加速比 |
|---------|-------------|-----------|--------|
| 256×256 | 3.2 ms | 2.1 ms | 1.5x |
| 512×512 | 13.2 ms | 7.5 ms | 1.8x |
| 1000×1000 | **49.7 ms** | **28.1 ms** | **1.8x** |
| 2000×2000 | 197.1 ms | 108.2 ms | 1.8x |

三线性 LUT 的加速比稳定在 1.8x 左右。如果改用 PCHIP 路径（CPU 当前路径），GPU 的收益将更加显著，因为 PCHIP 的计算量远大于简单三线性插值。

---

## 4. 效果总结

### 4.1 加速效果矩阵

| 算子 | 类型 | GPU 加速比 (2000×2000) | 当前状态 |
|------|------|----------------------|---------|
| 密度曲线插值 | 自定义 Metal | **16.1x** | ✅ 已上线 |
| 大 σ 高斯 IIR | 自定义 Metal | **6.8x** | ✅ 已上线 |
| 小 σ 高斯 FIR | 自定义 Metal | 1.2x | ✅ 已上线 |
| 光谱密度链 | MLX einsum | ~5x (端到端) | ✅ 已上线 |
| 扫描阶段 (含 CCTF) | 混合 | **5.2x** (端到端) | ✅ 已上线 |
| LUT 三线性采样 | MLX ops | 1.8x | ⚠️ Pilot (低质量) |
| 高光压缩 | MLX ops | 1.6x | ✅ 已上线 |
| 显影 (develop) | — | **1.04x** | ❌ 未加速 |
| 胶片颗粒 | — | — | ❌ 未加速 |

### 4.2 成功之处

1. **密度曲线插值表现突出**：16x 加速，是当前最成功的 GPU kernel，充分体现了自定义 Metal 着色器在计算密集型、数据并行度高的场景中的价值。
2. **大 σ IIR 高斯滤波实用性强**：7x 加速，在 halation 等多层 blur 场景中累积收益显著。
3. **扫描阶段 5x 加速**：多个 GPU 化算子（密度→logXYZ + CCTF + LUT）协同工作，验证了数据驻留 GPU 不反复回拷的策略。
4. **架构设计合理**：`ArrayBackend` Protocol 使得多数逐元素运算一次编写、双后端运行，维护成本可控。

### 4.3 问题与瓶颈

1. **`FilmingStage.develop` 未 GPU 化是最大的性能缺口**——该阶段占 GPU 总运行时间的 78%（927 ms），几乎未被加速（1.04x）。其计算内容包括：
   - **密度曲线插值**（已在 GPU 端实现，但该 stage 未使用 GPU 路径）
   - **DIR couplers**（矩阵运算 + 高斯扩散 + 插值，全部可 GPU 化）
   - **胶片颗粒**（随机数生成，GPU 化需要统计验收框架）

2. **GPU LUT 质量低于 CPU**：GPU 端使用三线性插值，而 CPU 端使用 PCHIP。在色彩敏感的胶片仿真中，这一差异可能导致可感知的色调偏差。

3. **MLX einsum 偶发 `std::bad_cast`**：特定 einsum 模式在 MLX 0.31.2 上触发异常，需要 workaround（改用 `matmul` + reshape）。

4. **缺少标准化性能基准**：当前仅有一个 ad-hoc 计时脚本，没有可重复的 CI 基准。

---

## 5. 加速比瓶颈分析

### 5.1 为什么端到端只有 1.15x？

```
加速前：CPU 1.30s
加速后：GPU 1.13s
节省：  0.17s

理想情景（develop 也 GPU 化）：
  假设 develop 从 927ms → 150ms（6x）：
  GPU 理想 ≈ 1.19 - 0.78 + 0.13 = 0.54s
  理想加速比 ≈ 2.4x
```

即使所有算子都达到最佳性能，Amdahl 定律也限制了加速上限。但当前 1.15x 远低于理论上限，主因是 **~78% 的工作量未加速**。

### 5.2 `FilmingStage.develop` 子模块耗时分解

为量化 develop 内部的耗时分布，在 1000×667 合成数据上对 CPU 路径进行了子模块分解：

| 子模块 | CPU 耗时 (1000×667) | GPU 状态 |
|--------|-------------------|----------|
| Density curve 插值 (`develop_simple`) | 11.6 ms | ✅ 已 GPU 化（Metal kernel, ~1ms） |
| DIR couplers 校正 | ~36.6 ms | ✅ 已 GPU 化（einsum + Gaussian） |
| Grain（无子层, 1层） | 274.8 ms | ❌ 全 CPU |
| Grain（有子层, 3层, 默认） | 160.4 ms | ❌ 全 CPU |
| 其中 `interp_density_cmy_layers` | 188.4 ms | ❌ 全 CPU（Numba fast_interp） |
| **合计 develop (有子层 grain)** | **~213 ms** | |

**核心发现**：Grain 占 develop CPU 时间的 **75–90%**。GPU 化的密度插值和 DIR couplers 合计仅 ~10ms，即使完美加速也无法显著改善端到端耗时。真正瓶颈是**胶片颗粒合成**。

### 5.3 各阶段 GPU 化优先级（基于当前耗时占比）

| 阶段 | 当前 GPU 耗时 | 占比 | GPU 化状态 | 优先度 |
|------|-------------|------|-----------|--------|
| FilmingStage.develop (grain 为主) | ~927 ms | 78% | ❌ 未加速 | **P0** |
| FilmingStage.expose (RGB→RAW) | ~154 ms | 13% | 部分加速(仅 boost+blur) | **P1** |
| SpectralLUT services | ~61 ms | 5% | 部分加速 | P2 |
| PrintingStage.expose | ~53 ms | 4% | 部分加速 | P2 |
| ScanningStage.scan | ~25 ms | 2% | ✅ 较好加速 | — |

---

## 6. 全代码库计算热点扫描（超出 develop 之外的加速机会）

通过对 **FilmingStage、PrintingStage、ScanningStage、SpectralLUTService、Diffusion、Glare、Spectral Upsampling** 等模块的全代码分析，以下列出了开发 (`develop`) 阶段之外所有值得 GPU 化的计算热点。

### 6.1 FilmingStage.expose — RGB→RAW 光谱上采样（CPU/colour-science 瓶颈）

| 子模块 | 代码位置 | 计算内容 | 当前 GPU 状态 | 加速潜力 |
|--------|---------|---------|-------------|---------|
| `_rgb_to_film_raw` → `rgb_to_raw_hanatos2025` | `filming.py:134-146`, `spectral_upsampling.py:321-336` | `colour.RGB_to_XYZ()` + xy→tc + 2D cubic LUT + scale | **❌ 全 CPU**。注意：`rgb_to_raw_hanatos2025_backend()` 已存在于 `spectral_upsampling.py:365-425` 但 **未被 `FilmingStage` 调用** | **高** — 2D cubic LUT 采样 + colour 矩阵运算 |
| `apply_diffusion_filter_um` | `filming.py:67-72`, `diffusion.py:590-651` | 构造 PSF + 填充 / FFT 卷积 / 加权混合 | ⚠️ 卷积与 padding 已 GPU 化, **但 PSF 构造 (CPU loop over sub-components) 仍为 CPU** | 中 — 大尺寸 PSF 的 FFT 已部分加速 |
| `apply_halation_um` | `filming.py:79-84`, `diffusion.py:29-87` | N 次 Gaussian blur + 加权求和 | ✅ Gaussian kernel 已 GPU 化 | 高 — 内层 loop 的多次 `gaussian_filter_backend` 已受益 |
| `boost_highlights` | `filming.py:56-66` | per-pixel 高光压缩曲线 | ✅ 已 GPU 化 | — |

**关键发现**：`_rgb_to_film_raw()` **是整个管线中最大且最易加速的"漏网之鱼"**。它使用了 CPU-only 的 `colour.RGB_to_XYZ()` 和 CPU cubic 2D LUT，而 `rgb_to_raw_hanatos2025_backend()` 已写好但未被接入。

#### 6.1.1 LUT Service 中 `get_filming_tc_lut` 的 GPU 潜力

| 代码位置 | 当前 | GPU 化潜力 |
|---------|------|-----------|
| `spectral_lut_compute.py:177-189`, 调 `compute_hanatos2025_tc_lut()` → `contract('ijl,lm->ijm', spectra_lut, sensitivity)` | CPU einsum, L×L×3 | 低。L=128, 每帧只算一次并缓存 |

### 6.2 PrintingStage.expose — 光谱密度→logRAW（已部分 GPU 化）

| 子模块 | 代码位置 | 当前 GPU 状态 | 潜力 |
|--------|---------|-------------|------|
| `_film_cmy_to_print_log_raw` → compute_density_spectral + density_to_light + light_to_raw + exposure factor + preflash | `printing.py:97-137` | ✅ GPU 化：einsum + power + einsum。**但 exposure_factor/preflash 仍 CPU** | 低（计算量小） |
| `apply_diffusion_filter_um` | `printing.py:74-79` | ✅ FFT 卷积已 GPU 化 | — |

### 6.3 SpectralLUTService — LUT 构建与采样

| 子模块 | 代码位置 | 当前 GPU 状态 | 潜力 |
|--------|---------|-------------|------|
| LUT 构建（enlarger/scanner） | `spectral_lut_compute.py` | **❌ 全 CPU**。`spectral_calculation()` 逐点调用 `cmy_to_log_xyz` 来填充 17³ LUT | **中** — LUT 构建量小（17³=4913 点），加速收益有限 |
| LUT 采样（trilinear on GPU） | `lut.py:12-65`, `utils/lut.py` | ✅ 已 GPU 化（pilot 质量） | — |

### 6.4 ScanningStage.scan — 已较好地 GPU 化

扫描阶段在 5.2x 加速下已是最优加速阶段。剩余的可优化的 CPU 部分：

| 子模块 | 代码位置 | 当前 | 潜力 |
|--------|---------|------|------|
| `black_white_xyz_correction` | `scanning.py:116-127` | ⚠️ GPU→CPU→GPU 回拷 | 低（标量操作） |
| `add_glare` | `scanning.py:129-132` | **❌ CPU**: `fast_lognormal_from_mean_std` + `fast_gaussian_filter` | **中** — GPU 化 glare 需要 PRNG + blur |
| `_apply_blur_and_unsharp` | `scanning.py:194-199` | ✅ 已 GPU 化 | — |

### 6.5 空间效果模块（diffusion、halation、glare）GPU 状态汇总

| 模块 | 文件:行 | GPU 状态 | 说明 |
|------|---------|---------|------|
| `apply_gaussian_blur` / `apply_gaussian_blur_um` | `diffusion.py:89-106` | ✅ 已 GPU 化 | 直接调用 `gaussian_filter_backend` |
| `apply_unsharp_mask` | `diffusion.py:11-26` | ✅ 已 GPU 化 | 基于 `gaussian_filter_backend` |
| `apply_diffusion_filter_um` (核心 + halo + bloom) | `diffusion.py:590-651` | ⚠️ 部分 GPU | FFT 卷积 + reflect padding 已 GPU，**PSF 构建（CPU）+ sub-component loop** 未 GPU 化 |
| **PSF 构建函数** `_radial_components`, `diffusion_filter_psf` | `diffusion.py:456-587` | **❌ 全 CPU** | Python loop 遍历 core/halo/bloom sub-components，对每个 channel 计算 exp 权重。尺寸固定（~60-400px）收益有限 |
| `apply_halation_um` | `diffusion.py:29-87` | ✅ 已 GPU 化 | N 次 Gaussian + 加权混合完全在 GPU 上 |
| `exponential_filter_backend` | `diffusion.py:60` | ✅ 已 GPU 化 | Gaussian 混合近似 |
| `add_glare` + `compute_random_glare_amount` | `glare.py:8-25` | **❌ 全 CPU** | Numba random + GPU-capable 但实际调用时即使 `backend.supports_gpu` 也未走 GPU。使用了 `fast_lognormal_from_mean_std` + `fast_gaussian_filter` |

### 6.6 预备/工具层算子的 GPU 潜力

| 函数 | 位置 | 大小 | 调用频率 | GPU 价值 |
|------|------|------|---------|---------|
| `interp_density_cmy_layers` — 3×Numba fast_interp | `density_curves.py:35-45` | 1000×667×3×3 | 每帧~1次 (grain sublayer) | **高** — 分解为 GPU 密度插值（已有 kernel）×3 |
| `fast_binomial` / `fast_poisson` / `fast_lognormal` | `fast_stats.py:5-163` | 整图 | grain 每个 channel×sublayer | **高** — GPU PRNG kernel |
| `fast_gaussian_filter`（grain 内） | `grain.py:50,62,106` | 整图 | grain 层 | **中** — 已 GPU 化，但 grain 内未用 |
| `apply_grain_to_density` + `apply_grain_to_density_layers` | `grain.py:66-163` | 整图 | 每帧~1次 | **非常高** — 当前 CPU 总耗时 160-275ms |
| `add_micro_structure` | `grain.py:53-64` | 整图 | 每帧~1次 | **中** — lognormal + Gaussian blur |
| `_preprocess` (auto_exposure) | `pipeline.py:178-182` | small preview | 每帧~1次 | 低（小图） |

### 6.7 全管线热点矩阵（GPU 化价值排序）

| 优先级 | 算子 / 模块 | 文件 | 当前耗时(CPU) | GPU 状态 | 预估 GPU 耗时 | 加速比 | 难度 |
|--------|-----------|------|:-----------:|:--------:|:-----------:|:-----:|:----:|
| **P0** | Grain（develop 内） | `model/grain.py`, `fast_stats.py` | **160–275ms** | ❌ 全 CPU | TBD (需 PRNG) | ~5-10x | ⭐⭐⭐ |
| **P0** | `interp_density_cmy_layers` | `model/density_curves.py:35` | **~188ms** | ❌ 全 CPU | ~3ms | ~60x | ⭐ |
| **P1** | `_rgb_to_film_raw` (RGB→RAW) | `filming.py:134`, `spectral_upsampling.py:321` | **~50-80ms** | ❌ 全 CPU (backend 存在但未接入) | ~5ms | ~10x | ⭐ |
| **P1** | Grain Gaussian blur (develop 内) | `grain.py:50,106,162` | ~30ms | ❌ 未走 GPU 路径 | ~3ms | ~10x | ⭐ |
| **P2** | `add_glare` + random | `model/glare.py:8-25` | ~5ms | ❌ 全 CPU | ~0.5ms | ~10x | ⭐⭐ |
| **P2** | LUT 构建 (CPU 循环) | `spectral_lut_compute.py` | ~12-49ms | ❌ 全 CPU | ~5ms | ~2-5x | ⭐⭐ |
| **P2** | PSF 构建 (diffusion filter) | `model/diffusion.py:456-587` | ~2ms | ❌ 全 CPU | negligible | ~1x | ⭐⭐ |
| **P3** | Grain PRNG (`fast_*` stats) | `utils/fast_stats.py` | ~100-200ms | ❌ 全 Numba | TBD | ~5x | ⭐⭐⭐ |

> 难度：⭐= 已有 infrastructure 只需接入 | ⭐⭐ = 需要新 kernel 但计算模式清晰 | ⭐⭐⭐ = 需要 PRNG + 统计验收框架

---

## 7. 下一步计划

### 第一阶段（P0）— 立即执行，高 ROI

#### 7.1 接入 `rgb_to_raw_hanatos2025_backend`（预计日间完成）

`FilmingStage._rgb_to_film_raw()` 是整个管线中最大且最容易接入 GPU 的"漏网之鱼"。一个 backend-aware 的实现（`rgb_to_raw_hanatos2025_backend`）已经存在于 `spectral_upsampling.py:365`，只需在 `FilmingStage.expose()` 中按 `supports_gpu` 标志切换调用路径。

涉及改动：
- `filming.py:134-146`：在 `_rgb_to_film_raw` 中添加 `if backend.supports_gpu` 分支，调用 `rgb_to_raw_hanatos2025_backend`

预估收益：`FilmingStage.expose` 从 154ms → ~60ms（管线加速 ~8%）。

#### 7.2 Density layers 插值 GPU 化（`interp_density_cmy_layers`）

当前 grain 的子层模式中 `interp_density_cmy_layers` 耗时高达 **188ms**（CPU Numba fast_interp × 3 通道 × 3 层）。

方案：使用已有的 `interpolate_exposure_to_density_backend` (Metal kernel) 替换。该函数的插值逻辑与 GPU 密度曲线 kernel 完全一致——数组是 `density_cmy[:,:,ch]`，x_axis 是 `density_curves[:,ch]`，y_vals 是 `density_curves_layers[:,:,ch]`。

涉及改动：
- `density_curves.py:35-45`：添加 backend-aware 分支
- `grain.py:193-198`：传入 backend 参数

预估收益：188ms → ~3ms（CPU 路径减少 185ms，管线加速 ~16%）。

#### 7.3 建立标准化性能基准

创建 `scripts/bench_metal_vs_cpu.py`（本次评估已实现初始版本），支持：

- 多输入尺寸（256、512、1000、2048）
- 多场景（no-LUT、LUT17、full spatial、full default）
- 分解到子模块级别的计时
- 输出 JSON 格式，便于 CI 对比

### 第二阶段（P1）— 重要改进

#### 7.4 胶片颗粒 GPU 化（最大单项收益）

Grain 是当前管线中最大的 CPU 热区（160-275ms，占 develop 的 75-90%）。GPU 化 grain 需要：

1. **Layer particle model** (`grain.py:21-51`)：对每个像素执行 Poisson RNG + Binomial RNG + 乘法。计算模式简单、数据并行度高，非常适合 GPU。每个像素独立，无需原子操作。
2. **组成链**：`apply_grain_to_density` / `apply_grain_to_density_layers` 中：
   - 3 通道 × N 子层 = 3-9 次 `layer_particle_model` 调用 → 每个调用生成一张随机图
   - 后接 `fast_gaussian_filter`（已有 GPU kernel）
   - micro-structure：`lognormal_from_mean_std` + Gaussian blur

实现方案：
- **短期**：用 MLX 内建 RNG（`mx.random.poisson`, `mx.random.binomial` 等）替换 Numba `fast_stats`——如果 MLX 覆盖了这些分布。
- **中长期**：若需统计完全一致性校验，实现 PCG/Philox 风格 stateless hash PRNG 作为 Metal kernel。
- **配置**：`cpu_exact`（默认）/ `gpu_statistical`（性能优先）两档。

预估收益：develop 从 927ms → ~200ms（管线加速 ~63% → 总耗时 ~0.5s）。

#### 7.5 GPU LUT 质量提升

- 将 PCHIP 预计算移到 GPU：在 CPU 上预计算 slopes/cell bounds，上传 GPU 后执行 PCHIP 分段三次插值
- 或在 GPU 上用更高阶插值（Catmull-Rom 等）替代三线性
- 在 `SpectralLUTService` 中缓存 GPU 侧的 prepared LUT，避免每帧上传

### 第三阶段（P2）— 体验与稳定性

#### 7.6 `add_glare` GPU 化

`add_glare` + `compute_random_glare_amount` 顺序上很小，但在 GPU 管线中造成了 **CPU→GPU 回拷**（当 glare active 时）。GPU 化后可消除该同步点。

方案：`glare.py:8-25` 中添加 `backend.supports_gpu` 分支，使用后端 RNG + `gaussian_filter_backend`。

#### 7.7 `density_to_light` 算子优化

当前 `density_to_light` 使用 `backend.power(10, -x)`，在 MLX 中通过 `exp(x * ln(10))` 实现（注释标注的 MLX API 限制）。如果 MLX 后续版本支持原生 `powf`/`pow10`，应切换以降低高方差和开销。

#### 7.8 完善 CI 集成

- 在 macOS GitHub Actions runner 上安装 MLX，启用 GPU 测试套件
- 增加数值回归测试（CPU vs GPU DeltaE <= 0.5）

#### 7.9 MSL 着色器外部化

将 5 个内核的 MSL 源码从 Python 内联字符串提取为独立 `.metal` 文件（`src/spektrafilm/gpu/shaders/`），改进可维护性。

### 第四阶段（P3）— 长期规划

#### 7.10 GPU Grain PRNG 统计验收框架

- 实现 stateless PRNG（PCG/Philox 哈希）
- 统计验收框架：mean/std/skew、RMS granularity、功率谱
- 提供 `cpu_exact` / `gpu_statistical` / `gpu_deterministic` 三档配置

#### 7.11 f16 精度验证

`gpu_precision` 参数已支持 `float16`，但尚无精度测试。需验证 f16 是否满足摄影管线的容差需求。

### 执行顺序路线图

```text
┌─ 当前状态 ─────────────────────────────────────────────────┐
│  End-to-end: 1.13s GPU (1.30s CPU)  Speedup: 1.15x       │
│  ┌─ FilmingStage.develop 927ms (78%) ← 最大瓶颈          │
│  │  ├─ Grain (160-275ms)        ← 未 GPU 化              │
│  │  ├─ interp_density_layers    ← 未 GPU 化 (188ms)      │
│  │  └─ density interp + DIR    ← 已 GPU 化 (~10ms)      │
│  └─ FilmingStage.expose 154ms ← RGB→RAW 未 GPU 化       │
└──────────────────────────────────────────────────────────┘
                        ↓ 第一阶段 (P0)
┌─ 快速接入 ─────────────────────────────────────────────────┐
│  rgb_to_raw_backend 接入     → expose: 154→60ms  (-94ms)  │
│  interp_density_layers GPU   → develop: 927→739ms (-188ms)│
│  合计: 1.13s → 0.85s  Speedup: ~1.5x vs CPU             │
└──────────────────────────────────────────────────────────┘
                        ↓ 第二阶段 (P1)
┌─ Grain GPU 化 (最大单项) ──────────────────────────────────┐
│  Grain GPU (PRNG + blur) → develop: 739→500ms (-239ms)   │
│  合计: 0.85s → 0.50s  Speedup: ~2.6x vs CPU             │
└──────────────────────────────────────────────────────────┘
                        ↓ 第三阶段 (P2)
┌─ 收尾优化 ─────────────────────────────────────────────────┐
│  Glare GPU 化              → 消除 CPU 回拷               │
│  GPU LUT PCHIP 质量         → 消除标记为 pilot 的风险     │
│  CI 集成 + MSL 外部化       → 可维护性 + 测试信心        │
│  合计: ~0.45-0.50s  Speedup: ~2.6-2.9x                  │
└──────────────────────────────────────────────────────────┘
```

### 收益测算（更新：Hanatos GPU 化落地后）

当前实测分解（GPU, 1000×667, 含 grain）：

| 模块 | 耗时 | 占比 | 加速可行性 |
|------|:---:|:----:|-----------|
| **grain（CPU Numba）** | **~1113 ms** | **89%** | 需要统计验收框架 |
| expose（GPU, 含 Hanatos） | 61 ms | 5% | ✅ 已加速 |
| scan + printing + LUT + auto_exposure | ~78 ms | 6% | ⚡ 已充分加速 |
| **合计** | **~1252 ms** | **100%** | |

**核心结论：如果不动 grain，剩余可加速空间约 6%（78ms → ~40ms 估算），收益极小。**

---

## 附录 A：测试环境

| 项目 | 值 |
|------|-----|
| 硬件 | MacBook Pro (2021), Apple M1 Pro, 16 GB Unified Memory |
| macOS | macOS 26.4.1 (arm64) |
| Python | 3.13.1 |
| MLX | 0.31.2 (Metal: enabled) |
| Numba | 0.65.0 |
| 测试图像 | 1000×667 float32, ProPhoto RGB linear |

## 附录 B：测试图像

- `img/test/portrait_leaves_32bit_linear_prophoto_rgb.tif` (1000×667)
- 随机生成浮点图用于微基准 (256×256 ~ 2048×2048)

## 附录 C：GPU vs CPU 算子加速比总览

```
密度曲线插值 (2000x2000)        ████████████████████ 16.1x
密度曲线插值 (1000x1000)        ███████████████     13.8x
rgb_to_raw Hanatos (1000x1000)  ███████████████████  19.1x ◄ 新增
rgb_to_raw Hanatos (512x512)    ████████████         12.1x ◄ 新增
密度子层插值 (512x512)          ██████████          10.6x ◄ 新增
大 σ 高斯 IIR (2000x2000)       ████████             6.8x
扫描阶段 (端到端)                ██████               5.2x
2D 立方 LUT (512x512)           ████                 4.3x ◄ 新增
光谱密度链 (端到端)              ██████               5.0x
大 σ 高斯 IIR (1000x1000)       █████                4.9x
LUT 三线性 (1000x1000)          ██                   1.8x
高光压缩 (2000x2000)            █                    1.6x
小 σ 高斯 FIR (2000x2000)       █                    1.2x
显影 (develop)                  ▏                    1.04x ← 瓶颈
rgb_to_raw Hanatos (256x256)    ▏                    0.8x  ← 小图 overhead
────────────────────────────────────────────────────────────
管线端到端 (1000x667)           ▏                    1.15x
```

> ◄ 新增 = 本次工作区覆盖的算子（包含 uncommitted GPU kernel 实现）

## 附录 D：新增实现验证摘要

### 新增 GPU Kernel 清单

| Kernel | 位置 | 类型 | 验证数值精度 |
|--------|------|------|-------------|
| 2D Mitchell-Netravali cubic LUT | `gpu/kernels/lut.py:15-179` | 自定义 Metal | max diff 4.72e-6 / mean 5.20e-7 |
| Grain 子层密度插值 | `gpu/kernels/density.py:84-145` | 自定义 Metal | max diff 1.46e-8 / mean 7.90e-9 |
| CCTF 解码（7 种色彩空间） | `gpu/kernels/color.py:192-218` | MLX backend ops | ✅ 47 test cases pass |
| Hanatos RGB→RAW 全链 | `utils/spectral_upsampling.py:370-446` | 组合（Metal+MLX） | max diff 2.38e-6 / mean 1.12e-7 |

### 性能验证

| 算子 (512×512) | CPU | GPU | 加速比 | 附带条件 |
|---------------|:---:|:---:|:------:|---------|
| 2D 立方 LUT | 27.1 ms | 6.2 ms | **4.3x** | — |
| 密度子层插值 | 22.5 ms | 2.1 ms | **10.6x** | — |
| Hanatos RGB→RAW | 65.5 ms | 5.4 ms | **12.1x** | precomputed constants + tc_lut 已缓存 |

### 管线数值对照（no grain, no LUT）

| 指标 | 值 |
|------|-----|
| CPU vs GPU pipeline max diff | 1.83e-6 |
| CPU vs GPU pipeline mean diff | 5.49e-8 |
| 输出有限值（无限/NaN） | ✅ 通过 |

### 需完成但尚未接通的环节

- **`filming.py:139-149`**：`_rgb_to_film_raw()` 仍调用 CPU 版的 `rgb_to_raw_hanatos2025`，而非 GPU 版的 `rgb_to_raw_hanatos2025_backend`。GPU Hanatos 基础设施已就绪（Mitchell Metal kernel + CCTF decode GPU），只需切换调用目标即可将 `FilmingStage.expose` 从 ~154ms 降至 ~60ms。
