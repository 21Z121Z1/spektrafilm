# GPU 后端完整审计与修复计划

日期：2026-05-31

## 目标

对 `spektrafilm-main` 的 GPU 后端处理加速实现做一次端到端 code review，并在同一轮工作中修复应当立即修复的接入缺口。重点不是重写架构，而是确认当前 MLX/CuPy/Halide 后端、模拟管线和 GUI 设置是否真实接通，尽量保持数组在后端驻留，只在最终输出边界回到 NumPy。

## 外部最佳实践依据

- MLX lazy evaluation：中途打印、转 NumPy 或访问内存会触发求值；频繁 `eval()` 有固定开销，应该在自然外层迭代或输出边界批量求值。
  - https://ml-explore.github.io/mlx/build/html/usage/lazy_evaluation.html
- MLX `compile()`：纯函数适合编译，外层函数编译通常比只编译内层更有优化空间；形状变化会触发重编译，`shapeless=True` 需要谨慎。
  - https://ml-explore.github.io/mlx/build/html/usage/compile.html
- MLX custom Metal kernels：kernel 对象应构建一次重复使用；默认会确保行连续，必要时用 shape/stride 避免隐式拷贝。
  - https://ml-explore.github.io/mlx/build/html/dev/custom_metal_kernels.html
- CuPy memory/performance：默认 memory pool 能减少分配和同步开销；GPU 计时必须使用 CUDA events 或官方 benchmark helper，避免 CPU 计时误判异步执行。
  - https://docs.cupy.dev/en/stable/user_guide/memory.html
  - https://docs.cupy.dev/en/stable/user_guide/performance.html
- Halide GPU：只有 target 启用 GPU feature 且 schedule 使用 `gpu_tile`/`gpu_blocks` 等 GPU 调度时，才应称为真实 GPU 路径；host JIT + CPU schedule 只能视为实验性 CPU/JIT 后端。
  - https://halide-lang.org/tutorials/tutorial_lesson_12_using_the_gpu.html
  - https://halide-lang.org/docs/struct_halide_1_1_target.html

## 已定位的风险

1. `SpectralLUTService._spectral_compute()` 在进入 GPU scanner LUT 或直算路径前会 `np.asarray(cmy_data)`，并且 LUT 路径在 GPU 后又 `np.asarray(..., dtype=np.float64)`。这会让 scanner 阶段过早离开 MLX/CuPy，违背 lazy evaluation 和后端驻留原则。
2. `model.grain.apply_grain()` 的 sublayers 路径先调用 CPU `interp_density_cmy_layers()`，再进入 `apply_grain_to_density_layers(..., backend=backend)`。已有 backend density-layer 插值 kernel 没有被接入，分层 grain 在 MLX 管线中仍有大图 CPU 物化。
3. GUI 文案仍提示 `compute_backend` 需要 restart，且 `gpu_precision=float64` “matches CPU exactly”。当前 `select_backend()` 对 explicit GPU + float64 会报错，auto + float64 会落回 CPU；文案会误导调试。
4. `SimulationWorker.run()` 只捕获常规异常。Metal/MLX/Qt worker 边界如果冒出非标准异常，可能导致线程失败而没有 GUI failure signal；需要用测试确认是否应收敛为统一失败消息。

## 测试优先步骤

1. 在 `tests/test_spectral_lut_service.py` 增加 fake GPU backend 测试：
   - direct path 不应对 backend array 做 `np.asarray()`；
   - GPU LUT cache hit 应返回 backend array，不应在 service 内转 NumPy。
2. 在 `tests/test_grain.py` 增加 MLX sublayers 回归：
   - monkeypatch CPU `interp_density_cmy_layers()` 抛错；
   - `apply_grain(..., backend=mlx)` 应走 `interpolate_density_cmy_layers_backend()` 并返回 MLX array。
3. 在 GUI runtime 测试中覆盖 worker 对 `BaseException` 子类的失败信号收敛。

## 实现步骤

1. 修改 `SpectralLUTService._spectral_compute()`：
   - CPU 语义保持 float64；
   - GPU direct path 直接把输入转 backend array 后调用 `spectral_calculation()`；
   - GPU LUT path 用 backend array 做归一化和 LUT 采样，返回 backend array；
   - 只让非 GPU 路径维持 NumPy/float64 输出。
2. 修改 `model.grain.apply_grain()`：
   - MLX 支持时用 `spektrafilm.gpu.kernels.density.interpolate_density_cmy_layers_backend()`；
   - 非 MLX GPU 后端仍保守回到 CPU，避免 CuPy/Halide 误入 MLX-only grain sampler。
3. 修改 GUI tooltip：
   - `compute_backend` 改为“下次预览/处理生效”；
   - `gpu_precision` 明确 float64 是 CPU reference，GPU 后端使用 float32。
4. 修改 `SimulationWorker.run()` 失败边界：
   - 将 worker 内部任意 `BaseException` 转成 `failed` signal；
   - 保持 finished signal 不被误发。

## 验证计划

按从窄到宽运行：

```bash
.venv/bin/python -m pytest tests/test_spectral_lut_service.py tests/test_grain.py tests/gui/test_controller_runtime_module.py -q
.venv/bin/python -m pytest tests/test_gpu_backend.py tests/test_gpu_lut.py tests/test_gpu_filters.py tests/test_gpu_density.py tests/test_gpu_color_chain.py tests/test_gpu_pipeline.py tests/test_gpu_primitives.py tests/test_spectral_lut_service.py tests/test_grain.py tests/gui/test_params_mapper.py tests/gui/test_controller_runtime_module.py -q
.venv/bin/python -m compileall -q src/spektrafilm src/spektrafilm_gui tests
git diff --check
```

如果 targeted GPU 测试通过，再根据耗时决定是否运行更大范围 pytest。任何失败先按现象定位再修复，不把环境缺失和实现通过混在一起。

## 完成标准

- scanner 光谱 LUT/直算路径在 GPU backend 下不再在 service 内提前 NumPy 物化。
- MLX 分层 grain 的密度层插值接入 backend kernel。
- GUI 设置文案与当前 backend 选择语义一致。
- 新回归测试能覆盖上述风险。
- 最终新增或更新一篇详细 Markdown code review 报告，包含完成度评估、已修复问题、剩余加速空间、精度空间、验证证据和仍未完成的真实 GPU/Halide边界。
