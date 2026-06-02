# MLX 计算后端评审与修复报告

日期：2026-05-31
范围：`src/spektrafilm/gpu/*`、runtime filming/printing/scanning 的 MLX 数据驻留路径、LUT wrapper、profile 数据校验对 GPU 验证的影响。

## 结论

本轮确认并修复了 4 个真实存在的 MLX 后端问题：

1. `compute_backend="auto" + gpu_precision="float64"` 会先尝试 MLX 并报错。现在 `auto+float64` 明确回退 CPU；显式 `compute_backend="mlx" + float64` 仍然报错。
2. `FilmingStage._rgb_to_film_raw()` 的 Hanatos 2D LUT GPU 路径会在 LUT 后立即 `np.asarray(...)`，导致全帧 MLX -> CPU materialization。现在 LUT 输出和亮度因子相乘继续留在 MLX。
3. `PrintingStage._spectral_compute_enlarger_gpu()` 的非 LUT 路径会通过 `_film_cmy_to_print_log_raw()` 转成 NumPy，再包回 MLX。现在主 GPU spectral chain 可返回 backend array。
4. LUT wrapper 对已经准备好的 MLX LUT/image 仍会再次调用 `mx.array(...)`。现在 `prepared_lut` 贯穿 `compute_with_lut()` 和 2D/3D MLX dispatcher，并用 dtype-aware helper 避免重复 copy。

额外补了 profile 校验回归：`channel_density` 允许测量缺口 `NaN`，但拒绝 `Inf`。这是 GPU pipeline 验证的必要前置条件，因为 film profile 的 spectral 数据可能存在真实缺口。

## 官方 MLX 依据

本轮对照的是官方 MLX 0.31.2 文档：

- Lazy evaluation：MLX 会延迟执行；`np.asarray`、打印、`array.item()` 等会触发隐式 evaluation。因此性能计时必须包含 `mx.eval()`、`mx.synchronize()` 或最终 NumPy materialization，不能只看未同步 stage wall time。
  https://ml-explore.github.io/mlx/build/html/usage/lazy_evaluation.html
- Data types：MLX 默认浮点为 `float32`；`float64` arrays 只支持 CPU operations，在 GPU 上使用会抛异常。
  https://ml-explore.github.io/mlx/build/html/python/data_types.html
- Unified memory：Apple Silicon 下 CPU/GPU 共享内存池，但仍应减少无意义 array wrapping 和隐式 materialization，按 operation/stream 选择设备。
  https://ml-explore.github.io/mlx/build/html/usage/unified_memory.html
- Compilation：可融合的 element-wise 图适合 `mx.compile`，但输入 dtype/shape 变化会导致重新编译。本轮没有盲目引入 compile，因为当前主要问题是错误 materialization 和 LUT copy。
  https://ml-explore.github.io/mlx/build/html/usage/compile.html

## 加速效果

轻量当前环境 benchmark（512x512，GPU 显式 `backend.eval`，随机固定 seed）：

```text
backend=mlx, precision=float32
cpu density_interp 512: best=8.804ms avg=10.206ms
mlx density_interp 512: best=0.540ms avg=1.024ms
density speedup=16.31x

cpu 3d_lut 512: best=69.218ms avg=153.761ms
mlx 3d_lut 512: best=5.909ms avg=14.383ms
lut speedup=11.71x

cpu cmy_to_log_xyz 512: best=137.070ms avg=178.118ms
mlx cmy_to_log_xyz 512: best=17.728ms avg=26.861ms
cmy_to_log_xyz speedup=7.73x
```

解释：

- MLX 对高度并行的 per-pixel interpolation、3D LUT、spectral matrix chain 加速明显。
- 端到端加速低于微核加速，因为 pipeline 中仍有 CPU reference/color-reference 小计算、LUT 构建、最终 materialization、IIR/halation 等串行或 memory-bound 部分。
- 既有 2026-05-30 报告显示 1000x667 端到端 MLX 约 1.11x，12MP 大图在优化路径下可达数倍；但这些数字必须区分 synced 与 unsynced。未同步 MLX stage timing 会把真实工作推迟到后续 stage 或最终 `np.asarray`。

## float32 精度影响

CPU reference 仍可用 float64；MLX GPU 实际是 float32。float32 对本管线的影响分三类：

1. 单个稳定 kernel：density interpolation、3D LUT、CMY->logXYZ 这类路径通常在 `1e-7` 到 `1e-5` max abs diff 量级。
2. LUT 路径：GPU trilinear 与 CPU reference/高阶插值或不同 evaluation order 会出现更大的局部差异；测试使用更合理的 LUT resolution 后，4x4/64x64 smoke 路径仍能在 `1e-5` 到 `2e-4` 量级通过。
3. 全流程空间效应：halation / exponential / gaussian / 多 stage log-power 组合会累积 float32 舍入误差。既有 12MP 报告中 MLX f32 vs CPU f64 的端到端最大差异约 `5e-2`、mean diff 约 `1e-3`，PSNR 约 53 dB；这主要是 float32 全流程累积和空间滤波，而不是单个 MLX kernel 错误。

实际回答“MLX GPU 结果会与 CPU 差多远”：

- 快速测试和 deterministic 小图：通常应在 `1e-5` 级别匹配 CPU reference。
- LUT 开启且分辨率较低：可放宽到 `2e-4` 或更高，差异主要来自插值近似。
- 含全尺寸 halation/空间滤波的真实图：局部 max diff 可到 `~5e-2`，mean diff 通常在 `~1e-3`。这种差异应作为 float32 quality envelope 管理；若用户要求 float64 数值 reference，必须使用 CPU。
- 随机 grain 不适合作逐像素 parity；应比较统计分布或关闭 stochastic effect。

## 验证记录

修复前新增测试均确认过 RED；修复后验证如下：

```text
.venv/bin/python -m pytest tests/test_gpu_backend.py::test_select_backend_auto_float64_falls_back_to_cpu tests/test_gpu_backend.py::test_select_backend_mlx_float64_is_strict_error -q
2 passed

.venv/bin/python -m pytest tests/test_gpu_pipeline.py::test_filming_rgb_to_raw_keeps_mlx_array_after_lut_when_available tests/test_gpu_pipeline.py::test_printing_non_lut_gpu_path_does_not_materialize_to_numpy -q
2 passed

.venv/bin/python -m pytest tests/test_gpu_lut.py::test_compute_with_lut_gpu_trilinear_reuses_prepared_backend_arrays tests/test_gpu_lut.py::test_trilinear_3d_lut_mlx_prepared_arrays_avoid_mx_array_copy tests/test_gpu_lut.py::test_cubic_2d_lut_mlx_prepared_arrays_avoid_mx_array_copy -q
3 passed

.venv/bin/python -m pytest tests/test_gpu_backend.py tests/test_gpu_lut.py tests/test_gpu_filters.py tests/test_gpu_density.py tests/test_gpu_color_chain.py tests/test_gpu_pipeline.py tests/test_gpu_primitives.py -q
110 passed, 7 skipped

.venv/bin/python -m pytest --ignore=tests/gui -q
686 passed, 7 skipped, 1 warning

.venv/bin/python -m compileall -q src tests
passed

git diff --check
passed
```

唯一 warning：

```text
tests/test_autoexposure.py::test_legacy_autoexposure_methods_remain_finite_on_small_images[matrix]
RuntimeWarning: divide by zero encountered in log2
```

这是既有 legacy autoexposure 小图 warning，不属于本轮 MLX 后端问题。

## 剩余边界

- CPU 仍是唯一 float64 reference 后端；MLX float64 不应模拟或静默降级为 GPU float32。
- `mx.compile` 已在后续独立 pass 中按稳定 shape/dtype 缓存接入部分 element-wise chain。结论见 `docs/dev/2026-05-31-mlx-compile-elementwise.md`：`density_to_light`、CCTF transfer、highlight boost 编译后有收益；`safe_log10` 编译后为负收益，保持未编译。
- Halide pipeline parity 在本轮不是目标；MLX/CuPy pipeline parity 测试已从 Halide 中分离，避免 Halide 的独立问题污染 MLX 回归。
- 大图 benchmark 需要固定输入、关闭/固定 stochastic grain，并明确 synced vs unsynced，否则数字不可比较。
