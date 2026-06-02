# GPU 后端处理加速 Code Review 报告

日期：2026-05-31

## 结论

当前实现已经不是“未接入”的状态：`SimulationPipeline` 会按 `settings.compute_backend/gpu_precision` 选择后端，GUI 状态也会写回这些设置；MLX 路线覆盖了主要的 LUT、光谱、密度曲线、色彩矩阵、模糊/扩散、grain 和扫描后处理路径。

但审计前它还不能称为完整 GPU 驻留：scanner 的 `SpectralLUTService` 会在 LUT/直算路径中提前 `np.asarray()`，分层 grain 的 density-layer 插值仍先走 CPU，print 扫描默认启用的 glare 是 CPU-only，黑白校正用 `np.clip` 也会破坏 backend array。这些是这轮已经修复的核心问题。

完成度判断：

| 区域 | 完成度 | 说明 |
| --- | ---: | --- |
| 后端选择与 GUI 设置 | 85% | GUI 已映射到 runtime；文案已修正，不再误导“需要重启”和“GPU float64”。 |
| MLX 默认处理链 | 80% | 主链路已接入，已补 scanner/grain/glare/correction 缺口；仍需要真实 pytest/样张验证。 |
| CuPy 路线 | 55% | 通用 array/LUT/filters 存在；prepared LUT 复用已修；本机未验证，grain 主模型仍以 MLX 为主。 |
| Halide 路线 | 40% | 目前是 host JIT/实验性热 kernel 后端，不是官方意义上的 GPU schedule/AOT 后端。 |
| 测试覆盖 | 70% | 已补回归测试；但当前主机 `.venv` Python 动态库加载阻塞，未能跑完 pytest。 |

## 审计范围

重点阅读了 GPU 相关实现和接入点：

- `src/spektrafilm/gpu/`：backend selection、MLX/CuPy/Halide/Numpy 后端、color/density/filter/LUT/grain kernels。
- `src/spektrafilm/runtime/`：pipeline、filming/printing/scanning stage、LUT service、color reference service。
- `src/spektrafilm/model/`：grain、glare、diffusion、emulsion/couplers 的 backend 调用点。
- `src/spektrafilm_gui/`：state、params mapper、widget specs、controller runtime worker。
- `tests/`：GPU backend、pipeline、grain、spectral LUT、GUI runtime 相关测试。

## 参考的最佳实践

- MLX lazy evaluation：中途转 NumPy 或访问内存会触发求值；频繁 `eval()` 会增加固定开销。https://ml-explore.github.io/mlx/build/html/usage/lazy_evaluation.html
- MLX compile：优先编译外层纯函数；形状变化会触发重编译，`shapeless=True` 需要谨慎。https://ml-explore.github.io/mlx/build/html/usage/compile.html
- MLX custom Metal kernels：kernel 对象应构建一次重复使用，避免每次 JIT；必要时处理 stride 以避免隐式连续化拷贝。https://ml-explore.github.io/mlx/build/html/dev/custom_metal_kernels.html
- CuPy memory/performance：默认 memory pool 能减少分配/同步；GPU benchmark 需要 CUDA event/warm-up，不能只用 CPU wall clock。https://docs.cupy.dev/en/stable/user_guide/memory.html 和 https://docs.cupy.dev/en/stable/user_guide/performance.html
- Halide GPU：只有 target 有 GPU feature 且 schedule 使用 `gpu_tile`/`gpu_blocks` 等 GPU 调度时才是 GPU 路径。https://halide-lang.org/tutorials/tutorial_lesson_12_using_the_gpu.html

## 已修复的问题

### 1. Scanner 光谱计算提前 NumPy 物化

位置：`src/spektrafilm/runtime/services/spectral_lut_compute.py`

问题：`_spectral_compute()` 一开始就 `np.asarray(cmy_data)`，GPU direct path 又强制 float64；GPU LUT path 在 `apply_lut_trilinear_3d_backend()` 后再 `np.asarray(..., dtype=np.float64)`。这会让 scanner 阶段提前离开 MLX/CuPy，违背 MLX lazy evaluation 和 backend-resident 设计。

修复：

- GPU direct path 直接 `backend.asarray(cmy_data)` 后调用 spectral callable。
- GPU LUT path 只把小型 test/LUT 构建结果转 NumPy，图像数据归一化和 LUT 采样保持 backend array。
- GPU LUT 返回 backend array，只在最终 pipeline 输出边界转 NumPy。

新增测试：

- `test_spectral_compute_gpu_direct_path_keeps_backend_array_resident`
- `test_spectral_compute_gpu_lut_path_returns_backend_result_without_numpy_transfer`

### 2. 分层 grain density-layer 插值没有接入 MLX backend

位置：`src/spektrafilm/model/grain.py`

问题：`apply_grain(... sublayers_active=True, backend=mlx)` 先调用 CPU `interp_density_cmy_layers()`，然后才进入 GPU layered grain。大图会在最昂贵的分层插值处回 CPU。

修复：

- MLX backend 下改用 `interpolate_density_cmy_layers_backend()`。
- 非 MLX GPU backend 保守转回 CPU grain，避免 CuPy/Halide 误进 MLX-only grain sampler。

新增测试：

- `test_apply_grain_layered_mlx_uses_backend_layer_interpolation`

### 3. Print 扫描默认 glare 是 CPU-only

位置：`src/spektrafilm/model/glare.py`、`src/spektrafilm/runtime/stages/scanning.py`

问题：`GlareParams.active=True` 是默认值，print 扫描路径会调用 `add_glare()`。原实现使用 CPU lognormal + Gaussian filter，导致 scanner 默认路径回 CPU。

修复：

- `add_glare()` 增加 `backend` 参数。
- MLX/CuPy backend 下使用 `fast_lognormal_from_mean_std_backend()` 和 `gaussian_filter_backend()`。
- Halide 这类没有 MLX/CuPy stochastic sampler 的 backend 保持 CPU fallback。

新增测试：

- `tests/test_glare.py::test_add_glare_passes_backend_and_keeps_backend_math`

### 4. 黑白校正会用 NumPy clip 破坏 backend array

位置：`src/spektrafilm/runtime/services/color_reference.py`、`src/spektrafilm/runtime/pipeline.py`

问题：scanner 黑白校正开启时，`correction_func()` 用 `np.clip()`，会把 backend array 拉回 NumPy；曝光校正中的 midgray 标量也可能保留 backend scalar，后续进入 NumPy 插值时行为不稳定。

修复：

- `ColorReferenceService` 接收 backend。
- GPU backend 下用 `backend.clip()`。
- 曝光校正需要标量时显式通过 `backend.to_numpy()` 转为 Python float。

新增测试：

- `test_backend_correction_uses_backend_clip`

### 5. CuPy prepared 3D LUT 未被实际使用

位置：`src/spektrafilm/gpu/kernels/lut.py`

问题：`apply_lut_trilinear_3d_backend(..., prepared_lut=...)` 的 MLX 分支已使用 prepared LUT，但 CuPy 分支仍传原始 `lut`，会重复 `cp.asarray()`。

修复：

- CuPy 分支也使用 `prepared_lut if prepared_lut is not None else lut`。

### 6. GUI/runtime 语义不一致

位置：`src/spektrafilm_gui/widget_specs.py`、`src/spektrafilm_gui/controller_runtime.py`

问题：

- GUI tooltip 说 backend 需要 restart，但 controller 会在后续 preview/process run 更新 params/pipeline。
- tooltip 说 float64 GPU 与 CPU 完全一致，但当前 explicit GPU + float64 会拒绝，`auto+float64` 会落回 CPU。
- worker 只捕获普通异常，Metal/worker 边界的非标准异常可能没有 failure signal。

修复：

- 更新 tooltip，说明 backend 下次预览/处理生效，float64 是 CPU reference path。
- worker 内部把 `BaseException` 子类收敛成 failure signal，避免 QRunnable 静默失败。

新增测试：

- `test_simulation_worker_emits_failure_message_for_base_exception`

## 加速空间

1. **Halide 还不是真 GPU 后端**：当前 Python Halide backend 使用 host target/JIT 和手写热 kernel cache。若要达到 Halide 官方 GPU 路径，需要 target 探测 GPU feature、使用 `gpu_tile`/`gpu_blocks` schedule，并最好生成 AOT artifact。否则报告和 GUI 中应继续标注为 experimental/JIT。
2. **MLX 外层融合仍有空间**：scanner 后处理可考虑把 `10**log_xyz -> correction -> glare -> XYZ_to_RGB -> CCTF` 做成少数外层纯函数并用 `mx.compile()`；随机 glare 需要显式处理 RNG/state，形状变化也会触发重编译，不能盲目套 compile。
3. **大图 tiling 还没有成为统一 runtime 策略**：已有 generic tiling helper，但默认 pipeline 没有按 backend memory watermark 自动分块。HDR/高分辨率图可以通过 stage-aware tiling 减少峰值内存。
4. **FFT/滤波中的同步点需要基准确认**：MLX FFT convolution 内部有显式 `eval/clear_cache` 风格的内存控制。它可能保护大图内存，也可能打断 lazy fusion；需要用真实样张和峰值内存一起比较。
5. **CuPy 需要真实设备基准**：CuPy 路径应按官方建议用 CUDA events/warm-up 做 benchmark，且确认 CUB/cuTENSOR reduction、memory pool、prepared LUT 是否真的减少传输。
6. **stochastic kernels 可继续提升质量/速度**：MLX grain 目前用近似采样保持驻留。可以增加统计质量基准，而不是用逐像素 parity 要求随机模型。

## 精度空间

1. **CPU float64 仍是 reference**：`gpu_precision=float64` 现在正确落到 CPU reference。GPU 路径以 float32 为主要目标，不应承诺 bit-exact parity。
2. **LUT 构建应继续保留 float64 参考**：这轮只避免图像数据提前物化；静态 LUT/test cache 仍可用 float64/NumPy 构建，保证校验和插值基准稳定。
3. **混合精度可局部引入**：光谱积分、白黑校正、长链曝光计算可考虑 CPU/float64 reference 与 GPU/float32 production 双轨；float16 不建议默认开放给影像质量路径。
4. **误差预算需要按阶段定义**：density/log/XYZ/RGB/CCTF 各阶段应有独立容差，而不是只看最终 RGB；grain/glare 属随机模型，应看统计分布、均值、方差和视觉阈值。

## 验证结果

已完成：

```bash
git diff --check
.venv/bin/python -S - <<'PY'
import ast
from pathlib import Path
...
PY
```

结果：

- `git diff --check` 通过。
- 14 个本轮触及的 Python 文件 AST parse 通过。

未完成：

```bash
.venv/bin/python -m pytest tests/test_spectral_lut_service.py tests/test_grain.py tests/test_glare.py tests/test_color_reference.py tests/gui/test_controller_runtime_module.py -q
```

阻塞原因：当前 `.venv` 的 Homebrew Python 3.13 在导入动态扩展时挂起。复现包括：

- `.venv/bin/python -c "import numpy; print(numpy.__version__)"` 15 秒超时。
- `.venv/bin/python -m pytest ...` 无输出挂起。
- `sample` 显示进程卡在 macOS `dyld` 的 `dlopen -> fcntl` 栈。
- Codex bundled Python 能导入 NumPy，但缺少项目测试需要的 `scipy/colour/pytest/qtpy/mlx`。

因此我不能诚实地宣称“pytest 已通过”或“事实 100% confidence”。当前代码经过静态验证和路径级审计，但还需要在 `.venv` Python 动态加载恢复后运行 targeted/full pytest 与真实样张 smoke。

## 100% 信心复查

第一轮自问后不满足 100%：发现 scanner service 和 layered grain 仍然 CPU materialize。已修。

第二轮自问后仍不满足 100%：发现默认 glare 和黑白校正也会破坏 scanner backend 驻留。已修。

第三轮自问后仍不能达到事实 100%：不是因为代码路径还有明确已知缺口，而是因为运行时验证被当前主机 Python/dyld 阻塞。结论是：本轮实现达到可提交前审计标准的“静态和结构 confidence”，但没有达到可发布标准的“事实 100% confidence”。恢复 Python import 后必须补跑 pytest 和至少一张真实样张的 CPU/GPU 对比。

## 后续必须补跑的命令

```bash
.venv/bin/python -m pytest tests/test_spectral_lut_service.py tests/test_grain.py tests/test_glare.py tests/test_color_reference.py tests/gui/test_controller_runtime_module.py -q
.venv/bin/python -m pytest tests/test_gpu_backend.py tests/test_gpu_lut.py tests/test_gpu_filters.py tests/test_gpu_density.py tests/test_gpu_color_chain.py tests/test_gpu_pipeline.py tests/test_gpu_primitives.py tests/test_spectral_lut_service.py tests/test_grain.py tests/test_glare.py tests/test_color_reference.py tests/gui/test_params_mapper.py tests/gui/test_controller_runtime_module.py -q
.venv/bin/python -m compileall -q src/spektrafilm src/spektrafilm_gui tests
git diff --check
```
