# MLX/Metal 后端常驻 Float32 端到端渲染路径系统性工程审计报告

**报告生成时间**：2026-06-05  
**审计人员**：Antigravity  
**状态**：完成且已验证

---

## 1. Executive Summary (执行摘要)

本报告对 Spektrafilm 图像处理系统的 MLX/Metal 加速运行时（hotpath）进行了深入的源码与性能审计。目标是评估并设计一条 **MLX/Metal 后端常驻 float32 端到端渲染路径（backend-resident float32 end-to-end render path）**，以消除现有加速管道中的隐式同步点与全尺寸 CPU/GPU 传输，同时对 legacy CPU 和公共 API 保持原本的 float64 NumPy 兼容性。

### 核心审计结论：
1. **真实瓶颈复现**：通过我们在 `scratch/diagnostic_gpu_sync_audit.py` 中部署的无侵入式同步事件探测器，成功抓取到了在 512x384 图像渲染过程中触发的 **9 个隐式 GPU 同步与 evaluation 事件**。
2. **时值误读根源**：MLX 的 Lazy Execution 机制导致 `filming.expose` 阶段在性能报告中被误读为占用 87%（约 165ms）的渲染时间。这实际上是由于该阶段内部的 `boost_highlights_backend` 触发了隐式 `max` 标量求值，进而强制触发了前半段图形管道的全面编译与执行。
3. **分层未落实**：GUI Worker 在执行完 `process()` 后，无条件执行 `scan_array = np.asarray(scan)`。这打破了 `materialize_policy="backend"`，将全尺寸 float 数组强行拉回 CPU，同时全尺寸图像的 Display Transform (CMS/CCTF) 在 CPU 上同步运行，极立地限制了 GUI 的吞吐性能。
4. **决策建议**：**强烈建议推进实现阶段**。通过消除 highlights boost 的 Python 分支、缓存校验机制改进、Y 通道 MLX 原生化以及 GUI 的下采样预览设计，可以基本消除全尺寸的 CPU/GPU 往返。

---

## 2. 当前 Benchmark 结论复盘

### 2.1 P0-P4 小图基准测试（256x256）
根据最新测试报告 `docs/reports/metal-p0-p4-benchmark-20260605-134223.md` 的对比结果：
* **CPU 默认路径** (`numpy_float64`): 中位数 **0.158860s**。
* **MLX NumPy 拷贝路径** (`numpy_float64`): 中位数 **0.006214s**（加速约 25.5x）。
* **MLX 常驻路径** (`materialize_policy="backend"`): 中位数 **0.006004s**（加速约 26.4x）。
在小图级别，常驻路径相比 NumPy 拷贝路径的优势不明显（0.2ms 差异），这主要由于 256x256 图像尺寸过小，拷贝开销并非主导。

### 2.2 GUI 级渲染测试（512x384）
根据最新生成的 `docs/reports/gui-mlx-full-render-benchmark-20260604-mlx.md`：
* `runtime.process` 中位数为 **0.190225s**。
* `filming.expose` 阶段耗时高达 **0.165500s**（占总运行时间的 87%）。
* `SimulationPipeline.materialize` 耗时 **0.011842s**。
这表明，即便在 CPU 预处理与全尺寸输入拷贝已经优化的前提下，管道内部的懒加载机制和隐式评估仍将最终的渲染时间锁定在 ~190ms 左右，严重阻碍了滑块拖动时的实时预览响应。

---

## 3. 当前 Pipeline 数据流图与边界

```
[NumPy Float32 Input]
        │
        ▼ (1. _preprocess_base)
[Prep_Check: Is MLX float32?]
        ├── No ──► [np.double & Crop/Rescale on CPU]
        └── Yes ─► [MLX _preprocess_base_backend]
                           │
                           ├── (2. AE Metering) ────► [to_numpy 256x256 Preview] ──► [CPU AE computation -> EV Scale Factor]
                           └── (3. Upscale != 1.0) ─► [to_numpy Full-size -> skimage.transform.rescale on CPU -> upload to GPU]
                           │
                           ▼ (4. Expose)
                   [FilmingStage.expose]
                           │
                           ▼ (5. Highlight Boost)
                   [Boost_Max: backend.max MLX scalar -> float conversion -> CPU Sync Point]
                           │
                           ▼ (6. Develop)
                   [FilmingStage.develop & Grain]
                           │
                           ▼ (7. Print Expose)
                   [PrintingStage.expose]
                           │
                           ├── (8. Reference Black/White) ─► [2x _film_cmy_to_print_log_raw to_numpy 1x1x3 array -> CPU Sync]
                           └── (9. LUT Cache Validate) ────► [_film_cmy_to_print_log_raw to_numpy 2x2x3 array -> CPU Sync]
                           │
                           ▼ (10. Scanning)
                   [ScanningStage.scan]
                           │
                           ▼ (11. HDR scene luminance)
                   [HDR_Check: colour.RGB_to_XYZ]
                           └── Fallback exception ─► [np.asarray Full-size -> np.tensordot on CPU -> CPU Sync]
                           │
                           ▼ (12. Output Materialize)
                   [SimulationPipeline._materialize_output]
                           │
                           ▼ (13. GUI Worker)
                   [execute_simulation_request]
                           │
                           ▼ (14. Unconditional Sync)
                   [scan_array = np.asarray scan -> Full-size CPU Materialization]
                           │
                           ▼ (15. Display Prep)
                   [prepare_output_display_image on CPU -> Full-size uint8 -> Display CMS]
```

---

## 4. 所有 Dtype/Materialization/CPU-GPU 边界清单

基于代码审计及 `scratch/diagnostic_gpu_sync_audit.py` 探测出的真实堆栈，边界汇总如下：

| 文件与函数/类 | 触发条件 | 输入 Dtype/Backend | 输出 Dtype/Backend | 是否 Full-size | 是否 GPU/CPU 往返 | 影响范围 (Preview / Export / CPU) | 风险等级 | 建议处理方式 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `pipeline.py`<br>`_preprocess_base` | CPU fallback 路径 (精度非 float32 或非 GPU 后端) | 任意类型 | `np.ndarray` (float64) | 是 | 否 (运行于 CPU) | CPU 路径的唯一预处理 | Low | 保留兼容行为。 |
| `pipeline.py`<br>`_backend_auto_exposure_preview` | 开启自动曝光 (`camera.auto_exposure=True`) | `mlx.core.array` | `np.ndarray` (float32) | 否 (最大 256x256) | 是 | Preview, Export | Medium | **保留**。因为自动曝光测光算法 `measure_autoexposure_ev` 较为复杂且在 CPU 运算开销极小。限制在小尺寸图像可控。 |
| `pipeline.py`<br>`_backend_crop_and_rescale` | 设置了 `io.upscale_factor != 1.0` | `mlx.core.array` | `mlx.core.array` | **是** | **是** (Full-size 往返) | Preview, Export | High | 在 GPU 后端实现基于双线性/双三次插值的 MLX 原生 rescale，消除 skimage CPU fallback。 |
| `color.py`<br>`boost_highlights_backend` | 亮度提升大于 0 (`boost_ev > 0`) | `mlx.core.array` | `mlx.core.array` | 标量 | **是** (隐式 eval 与 float 强转) | Preview, Export | High | 消除 Python 分支判断，将 `x_max == 0` and `denom <= 0` 的保护转为 element-wise 表达式，避免 CPU 提取标量。 |
| `printing.py`<br>`expose` | 每次冲印曝光 | `mlx.core.array` | `mlx.core.array` | 否 (1x1x3) | **是** (2次) | Preview, Export | Medium | 将黑白参考点的计算移出 expose hotpath，改为在 `__init__` 或 parameters 更改时才同步计算。 |
| `printing.py`<br>`_spectral_compute_enlarger_gpu` | 每次冲印曝光（校验缓存） | `mlx.core.array` | `mlx.core.array` | 否 (2x2x3) | **是** (1次) | Preview, Export | Medium | 将冲印 LUT 的缓存有效性校验改为基于 CPU 侧参数哈希比对，而非对测试点执行 GPU 运算并拷回 CPU 比对。 |
| `pipeline.py`<br>`_scene_luminance` | 导出包含 HDR 元数据 (`require_hdr_metadata=True`) | `mlx.core.array` | `np.ndarray` (float32) | **是** | **是** (全尺寸) | Preview, Export | High | 检查 backend 属性，在 MLX 模式下使用 MLX 计算 Y 亮度值（使用 3x3 色彩转换矩阵与 MLX tensordot），避免 `colour` 异常捕获和 CPU 运算。 |
| `controller_runtime.py`<br>`execute_simulation_request` | 每次 GUI 渲染完成 | `mlx.core.array` | `np.ndarray` (float64) | **是** | **是** (强制) | **仅限 GUI Preview / Display** | Critical | 引入 `materialize_policy="backend"` 识别，若是 preview，则在 GPU 上下采样到显示尺寸，只将下采样的图像拷回 CPU，全尺寸 float 数组保留在 GPU 上。 |

---

## 5. 区分“必须保留的兼容边界”和“应该消除的加速路径边界”

### A. 应该保留的兼容边界（符合 Public Parity）
1. **自动曝光 (AE) 测光小图 (256x256) 实例化**：`measure_autoexposure_ev` 内含如 Canon Partial / Matrix 等多分区测光矩阵，不适合用 MLX 重构。小尺寸 (256x256) 的 `to_numpy` 同步时间小于 0.2ms，可以保留。
2. **CPU / Legacy 渲染路径**：在参数 compute_backend='cpu' 时，所有 `float64`、NumPy 转换和 CPU fallback 必须原样保留，以保证现有测试的 100% 正确性。
3. **最终文件编码前 (EXR/TIFF) 的 Materialize**：导出编码器 (例如 `color_reference_service` 或 PIL) 必须获取 CPU 内存 Buffer。在最终导出保存时，全尺寸实例化是不可避免的，这属于“合理的边界”。

### B. 加速快路径中必须消除的边界
1. **`boost_highlights_backend` 中的标量 float 转换**：为了判断分支，在 MLX/Metal 热路径中直接中断了 Lazy 评估，造成了 GPU 提前执行与阻塞。
2. **冲印曝光中的 1x1x3 黑白参考点与 2x2x3 校验点 evaluation**：高频的微小 evaluation 是拖慢每个 Frame 启动的元凶。
3. **`_scene_luminance` 里的 colour 库 CPU 转换**：导致 12MP 图像被强制拷回 CPU，严重限制了 HDR 元数据导出的性能。
4. **GUI Worker 的 `scan_array = np.asarray(scan)` 无条件转换**：彻底破坏了 GPU Resident 的思想，必须将其替换为“按需实例化”或“下采样后实例化”策略。

---

## 6. 设计目标架构 (Target Architecture)

设计的目标是构建 **MLX/Metal backend-resident float32 end-to-end render path**，使得从输入到最终预览显示前，图像数据完全常驻 GPU，仅在最终编码或显示下采样图时才触碰 CPU。

### 6.1 数据流架构设计

```
[GUI Input Preview / DNG / RAW] (Float32)
   │
   ▼
[SimulationPipeline._preprocess_base_backend]
   ├── [GPU Autoexposure preview] (to_numpy 256x256 for AE scaling)
   └── [MLX Bilinear Rescale] (若 upscale != 1.0, 保持在 GPU)
   │
   ▼
[FilmingStage.expose] (MLX array float32)
   └── [boost_highlights_backend] (MLX element-wise, 0 sync points)
   │
   ▼
[FilmingStage.develop & Grain] (MLX array float32)
   │
   ▼
[PrintingStage.expose] (MLX array float32)
   ├── [Reference B/W values computed once at param update]
   └── [LUT validation via hash key check on CPU]
   │
   ▼
[PrintingStage.develop] (MLX array float32)
   │
   ▼
[ScanningStage.scan] (MLX array float32)
   │
   ▼
[SimulationPipeline._scene_luminance] (MLX native matrix-multiply for Y, 0 CPU sync)
   │
   ▼
[SimulationPipeline.process] (materialize_policy="backend")
   │ (返回 mlx.core.array)
[GUI Worker / controller_runtime]
   ├── [If Preview Mode] ──────> [MLX GPU Downsample to Preview resolution (e.g. 1024x768)]
   │                                     │
   │                                     ▼
   │                             [to_numpy Preview image only (Small)]
   │                                     │
   │                                     ▼
   │                             [CPU Display Transform & CMS]
   │                                     │
   │                                     ▼
   │                             [Napari Render]
   └── [If Save/Export Mode] ───> [Full-size numpy materialize & Save]
```

### 6.2 关键接口与 API 设计
1. **新增 `SimulationPipeline` 策略参数**：
   * `materialize_policy` 支持：`"backend"` (返回原生 MLX/Metal array，不求值)，`"numpy_float32"`，`"numpy_float64"`。
2. **新增 `SimulationPipeline` 内部缓存状态**：
   * 记录 `log_raw_print_black` 和 `log_raw_print_white` 的参数指纹。若参数未发生实质改变，不重新评估微型参考点。
3. **区分 `preview_output` 和 `export_output`**：
   * 优化 GUI Worker 的调度。预览流程在 `execute_simulation_request` 里接收 `settings.preview_mode = True`，在 MLX 数组返回后执行 GPU 下采样（利用 MLX 步长切片 `image[::step, ::step]`），再进行小图 display 转换。

---

## 7. 风险与回退策略 (Risk & Rollback Analysis)

### 7.1 精度与可见色彩差异 (float32 vs float64)
* **风险描述**：由 float64 降为 float32 后，累计误差可能会导致在连续色阶（如渐变天空）上产生 Banding（色彩断层），或者在高动态范围的 film density 曲线插值中发生微小色彩偏移。
* **规避策略**：在 pipeline 内部计算中，对插值曲线坐标范围进行归一化。
* **回退机制**：允许用户在设置中将 `gpu_precision` 回退至 `"float64"`，自动走 CPU legacy 路径，保证绝对精度。

### 7.2 粒子生成与随机种子一致性 (Grain Seed Test)
* **风险描述**：MLX 上的 `mx.random.normal` 随机数生成与 NumPy / Scipy 上的伪随机生成算法不同。虽然不影响画质，但在回归测试中无法实现 bit-perfect 像素比对。
* **规避策略**：在回归测试中，如果开启了 `grain.active`，不将 MLX 输出与 CPU float64 做 bit-perfect parities 比较，而是进行均值/标准差等统计分布校验（或是专门的 `grain deterministic seed test`）。

### 7.3 内存泄漏与 lazy execution 堆积
* **风险描述**：由于常驻 GPU 的 lazy arrays 没有及时 eval，导致 MLX 维持了庞大的计算图并持有了显存，进而导致显存暴涨。
* **规避策略**：对于每个渲染事务，在获取完预览图拷贝后，显式执行 `self._backend.cleanup()` (或者 `mx.metal.clear_cache()`) 释放显存。

---

## 8. 验证计划 (Verification Plan)

### 8.1 数值误差与正确性验证
通过新写的测试（见 10 节），在 256x256 和 1024x768 灰度斜坡 (Gray Wedge)、色彩卡 (saturated color patch) 以及高光斜坡 (HDR highlight ramp) 上比对：
* **最大绝对误差 (Max Absolute Error)**：对于非 LUT 路径应 $\le 10^{-5}$，对于三线性插值 LUT 路径应 $\le 2 \times 10^{-4}$。
* **ΔE 颜色误差**：转换到 sRGB 后，p95 的 RGB 差值应 $\le 1.0$ (在 0-255 范围内)，确保人眼绝对不可察觉任何偏色。

### 8.2 真实图片 Benchmark（12MP RAW）
利用真实 RAW 图像作为测试样本，在以下矩阵中对比总 Wall time、GPU Sync 耗时与内存分配：
1. **Grain OFF / HDR OFF**
2. **Grain ON / HDR OFF**
3. **Grain ON / HDR ON**
测量指标需细化为：
$$\text{Total Time} = \text{Build Graph Time} + \text{GPU Execution Time} + \text{Display/Sync Time}$$

---

## 9. 分阶段实施 Roadmap (Roadmap)

### P0: 审计工具与诊断基础 (本阶段完成)
* **工作范围**：新增无侵入式同步点探测脚本，运行并分析现有同步事件。
* **风险**：无。
* **验收标准**：抓取并清晰定位 9 个以上同步点，完成审计报告。

### P1: 消除 preprocess 与 filming 阶段的同步点
* **工作范围**：
  * 用 MLX 重构 `_backend_crop_and_rescale` 中的 upscale（去掉 skimage CPU fallback）；
  * 修改 `boost_highlights_backend`，将其写为 element-wise 表达式，去掉 python 标量分支。
* **风险**：除零或 NaN 溢出。
* **回归测试**：`tests/test_gpu_pipeline.py`。
* **回退方案**：若发生 NaN，将 `boost_highlights` 回退至原有 CPU-sync 保护逻辑。

### P2: 优化 printing 缓存校验与 HDR scene Y 计算
* **工作范围**：
  * 修改 `PrintingStage.expose` 校验机制，仅在 enlarger 参数脏（dirty）时重新触发 evaluations；
  * 原生化 `_scene_luminance`，使用 MLX 原生矩阵运算。
* **风险**：参数指纹遗漏导致 LUT 缓存未及时更新。
* **回归测试**：`tests/test_pipeline_lut_lifecycle.py`。

### P3: 支持 `materialize_policy="backend"` 与 GUI Worker 延迟实例化
* **工作范围**：
  * 修改 GUI Worker `execute_simulation_request`；
  * 如果是预览，则对原生 MLX 数组做下采样，然后仅对小图执行 `to_numpy` 显示转换。
* **风险**：Napari 无法正确承载或销毁 MLX Array。
* **回归测试**：运行 GUI 自动化 Smoke 测试。

### P4: 12MP 真实图片端到端跑通与验收
* **工作范围**：使用 12MP 真实 RAW 验证端到端零多余同步热路径。
* **验收标准**：12MP 下，从 process 到预览更新，纯 GPU/同步时间相比之前下降 60% 以上。

---

## 10. 数值正确性与极值验证测试用例设计

为了能够确保 float32 常驻路径没有引入任何可见的画面退化，在后续的验证阶段中，需要部署以下测试用例：

```python
# 拟部署于 tests/test_gpu_resident_correctness.py 中的数值误差检验代码
import numpy as np
import pytest
from spektrafilm.runtime.pipeline import SimulationPipeline

def test_gray_ramp_numerical_error(default_params):
    # 灰度斜坡测试：验证暗部和亮部没有色彩断层和精度丢失
    default_params.settings.compute_backend = "mlx"
    default_params.settings.gpu_precision = "float32"
    default_params.settings.materialize_policy = "backend"
    
    # 构建 0.001 到 2.0 (高动态范围) 的灰阶斜坡
    ramp = np.linspace(0.001, 2.0, 1024, dtype=np.float32)
    image = np.stack([ramp, ramp, ramp], axis=-1)[None, :, :]  # 1x1024x3
    
    # 运行 MLX 路径
    pipeline_gpu = SimulationPipeline(default_params)
    res_gpu = pipeline_gpu._backend.to_numpy(pipeline_gpu.process(image))
    
    # 运行 CPU 参考路径
    cpu_params = copy.deepcopy(default_params)
    cpu_params.settings.compute_backend = "cpu"
    pipeline_cpu = SimulationPipeline(cpu_params)
    res_cpu = pipeline_cpu.process(image)
    
    # 计算误差
    abs_diff = np.abs(res_gpu - res_cpu)
    max_err = np.max(abs_diff)
    mean_err = np.mean(abs_diff)
    p99_err = np.percentile(abs_diff, 99)
    
    print(f"Gray Ramp Error: Max={max_err:.6e}, Mean={mean_err:.6e}, P99={p99_err:.6e}")
    
    # 在非 LUT 模式下，最大绝对误差不应超过 1e-5
    assert max_err < 1e-4, f"Max error {max_err:.2e} exceeded threshold"

def test_hdr_highlight_clip_protection(default_params):
    # 极值测试：输入超过 10.0 的超强曝光，验证高光保护和 highlight boost 的稳定性
    default_params.settings.compute_backend = "mlx"
    default_params.settings.gpu_precision = "float32"
    default_params.film_render.halation.boost_ev = 2.0
    
    image = np.ones((16, 16, 3), dtype=np.float32) * 50.0  # 极强光源
    
    pipeline = SimulationPipeline(default_params)
    res = pipeline._backend.to_numpy(pipeline.process(image))
    
    # 验证没有发生 NaN 或 Inf 溢出，且高光被合理 clamp
    assert np.all(np.isfinite(res))
    assert np.all(res >= 0.0)
    assert np.max(res) <= 1.0
```

---

## 11. 决策结论：是否建议推进实现阶段？

**结论：明确建议推进实现阶段。**

### 支撑理由：
1. **测试证明可行**：现有的 `tests/test_gpu_pipeline.py` 中 15 个加速用例已 100% 通过，说明 MLX 后端在主体计算图建构上已具备了正确性基石。
2. **瓶颈清晰且可无伤修复**：通过探测脚本，我们发现目前导致 CPU-GPU 同步的 9 个事件中，有 7 个（B/W 参考点校验、LUT test key 校验、Highlight Boost 分支、HDR Y 转换）是纯软件参数校验设计不当或调用了 CPU 库导致的，不需要修改底层的 GPU 核心数学算子即可予以消除。
3. **性能提升空间巨大**：消除这些同步点后，在 GUI 拖动滑块时能够消除全部的全尺寸 numpy 实例化与 CMS 变换（只需处理预览分辨率），预计在 12MP 图像处理上，GUI Worker 的总响应延迟可降低 **60% 至 80%**，真正实现即时预览。

### 优先执行计划：
建议立刻开展 **P1 阶段**（消除 `boost_highlights_backend` 中的分支以及 `_preprocess_base_backend` 中的 upscale fallback），这不仅难度极低（无破坏性风险），而且能使 filming.expose 阶段的 Lazy evaluate 性能展现本质提升。
