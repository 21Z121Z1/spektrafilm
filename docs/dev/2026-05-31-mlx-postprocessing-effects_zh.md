> 这是英文原文的中文翻译。权威版本请参考英文原文。

# MLX 后处理效果可行性与实现

日期：2026-05-31

范围：评估并加固 MLX 后端路径在空间后处理效果方面的表现，包括：光晕（halation）、漫射（diffusion）、颗粒（grain），以及运行时管线使用的邻近模糊/锐化滤镜。

## 结论

将这些效果连接到 MLX 在 Apple Silicon 上是可行且合适的，但有一个精度约束：

- 光晕是良好的 MLX 目标。当前活跃路径是高光增强加高斯和指数高斯混合滤波，这些都可以保持为 MLX 数组。
- 漫射是良好的 MLX 目标。运行时在 CPU 上根据参数构建小型 PSF，然后使用 MLX 反射填充和 FFT 卷积来处理全图工作。
- 颗粒作为 MLX 统计后端是可行的。对于固定的 MLX 种子应该是确定性的且统计上合理的，但不期望与 CPU SciPy/NumPy RNG 路径在像素级别上完全一致。
- MLX GPU 后处理必须使用 `float32` 或 `float16`。`float64` 属于 CPU 参考范畴，因为 MLX 文档明确指出 `float64` 数组仅支持 CPU 操作，在 GPU 上会失败。

实现方式使全图的光晕、漫射和颗粒操作保持在 MLX 上驻留，直到调用方显式物化最终输出。

## 来源检查

当前 MLX 0.31.2 文档和本地运行时共同塑造了实现方式：

- MLX 使用惰性求值：操作记录一个计算图，计算在 `eval()` 时发生。因此基准测试和测试需要在计时或断言之前进行显式求值。
- Apple Silicon MLX 使用统一内存，因此数组不需要手动的 CPU/GPU 传输。这并不意味着调用方应该在 GPU 路径的中间将全图转换为 NumPy。
- MLX 通过 `mx.fast.metal_kernel` 支持自定义 Metal 内核，当前滤镜代码已经将其用于反射填充和高斯 IIR 内核。
- MLX 暴露 FFT API，这使得现有的漫射 PSF 卷积非常适合使用。
- MLX 暴露带键的随机 API，这使得在后端上实现确定性的固定种子统计颗粒成为可能。

主要参考文献：

- <https://ml-explore.github.io/mlx/build/html/usage/lazy_evaluation.html>
- <https://ml-explore.github.io/mlx/build/html/usage/unified_memory.html>
- <https://ml-explore.github.io/mlx/build/html/python/data_types.html>
- <https://ml-explore.github.io/mlx/build/html/dev/custom_metal_kernels.html>

## 工作区发现

相关当前文件：

- `src/spektrafilm/model/diffusion.py` 已经为光晕、高斯模糊和漫射滤镜调用接受 `backend` 参数。
- `src/spektrafilm/gpu/kernels/filters.py` 提供后端感知的高斯、指数、反射填充和 FFT 卷积辅助函数。
- `src/spektrafilm/model/grain.py` 在提供后端时通过 MLX 路由颗粒生成。
- 运行时阶段将选定的后端传递到相机漫射、镜头模糊、光晕、印刷漫射、扫描仪模糊和反锐化滤镜。

本地 MLX 探测结果：

- `mlx.__version__ == 0.31.2`
- `mx.metal.is_available() == True`
- `select_backend("mlx")` 成功并在后端返回 `float32` 数组。

## 实现变更

### 光晕

红色测试暴露了光晕散射尾部可能路由到 `exponential_filter_backend()`，该函数之前为 MLX 高斯组件选择了 `_precision="float64"`。MLX 拒绝 GPU `float64`，然后回退路径通过 `backend.to_numpy()` 物化了全图。

修复：

- `exponential_filter_backend()` 现在默认使用 `_precision="float32"`。
- `gaussian_filter_backend()` 和混合 sigma 辅助函数显式传递精度。
- 需要精确 CPU 参考行为的调用方仍然可以请求 `_precision="float64"`，接受在 MLX 上的 CPU 回退。

### 漫射

当前漫射滤镜路径不需要生产修复。一个驻留测试现在保护 MLX 路径在应用漫射 PSF 卷积时不会将全图物化到 CPU。

小型 PSF 构建仍然在 CPU 侧进行且大小为参数级别。这是可以接受的，因为图像大小的卷积通过后端反射填充和 FFT 运行。

### 颗粒

红色测试暴露了 `_layer_particle_model_gpu()` 中的全图传输：

- 代码求值了 `seeds`，
- 将完整的 `seeds` 图像转换为 NumPy，
- 仅使用 `max()` 来决定是否运行二项近似。

修复：

- 移除该 CPU 物化。
- 始终运行向量化的 MLX 正态近似来处理 `Binomial(seeds, p)`。
- 将结果钳制到 `[0, seeds]`，这自然地处理了零颗粒像素。

这保持了固定种子 MLX 颗粒的确定性，并将图像大小的随机工作保持在 MLX 上。

公开的 `layer_particle_model()` 还有一个非默认的 `gamma_beta` 方法。该方法不是本次迭代的 MLX 加速目标，因此传递 MLX 后端现在会回退到 CPU 参考路径，而不是静默返回全零颗粒图像。未知的颗粒粒子方法现在会抛出 `ValueError`。

## 测试覆盖

添加了聚焦测试：

- `test_halation_mlx_stays_on_device_when_available`
- `test_diffusion_filter_mlx_stays_on_device_when_available`
- `test_apply_grain_to_density_mlx_does_not_materialize_when_available`
- `test_apply_grain_to_density_mlx_is_deterministic_for_fixed_seed`
- `test_apply_grain_to_density_mlx_statistics_are_plausible`
- `test_layer_particle_model_mlx_falls_back_for_gamma_beta`
- `test_layer_particle_model_rejects_unknown_method`

这些测试通过 monkeypatch 使 `backend.to_numpy()` 在 MLX 计算内部失败，而全图 CPU 物化将是回归问题。最终断言有意仅在 `backend.eval()` 之后才进行物化。

## 验证

修复前的 TDD 红色失败：

- 光晕驻留失败，因为 MLX `float64` 高斯 IIR 抛出异常，然后回退路径调用了 `backend.to_numpy(image)`。
- 颗粒驻留在 `backend.to_numpy(seeds).max()` 处失败。

修复后的聚焦绿色检查：

```bash
.venv/bin/python -m pytest tests/test_gpu_filters.py::test_halation_mlx_stays_on_device_when_available tests/test_gpu_filters.py::test_diffusion_filter_mlx_stays_on_device_when_available -q
# 2 passed

.venv/bin/python -m pytest tests/test_grain.py::TestApplyGrain::test_apply_grain_to_density_mlx_does_not_materialize_when_available -q
# 1 passed

.venv/bin/python -m pytest tests/test_grain.py -q
# 16 passed
```

本次变更的最终更广泛验证：

```bash
.venv/bin/python -m pytest tests/test_gpu_filters.py tests/test_grain.py -q
# 32 passed, 1 skipped

.venv/bin/python -m pytest tests/test_gpu_backend.py tests/test_gpu_lut.py tests/test_gpu_filters.py tests/test_gpu_density.py tests/test_gpu_color_chain.py tests/test_gpu_pipeline.py tests/test_gpu_primitives.py tests/test_grain.py -q
# 133 passed, 7 skipped

.venv/bin/python -m pytest --ignore=tests/gui -q
# 701 passed, 7 skipped, 1 warning

.venv/bin/python -m compileall -q src tests
# passed

git diff --check
# passed
```

## 已知边界

- MLX 颗粒是统计性的。固定种子在 MLX 上应该是确定性的，但与 CPU SciPy/NumPy RNG 的像素级一致性不是正确性目标。
- 默认的 `poisson_binomial` 颗粒方法是 MLX 加速方法。旧版 `gamma_beta` 方法在提供后端时回退到 CPU。
- 当调用方写入图像或比较数组时，最终输出仍需物化。
- 小型参数数组、PSF、LUT 表和颜色参考值可以在 CPU 上构建；受保护的边界是图像大小的中间传输。
- `compute_backend="auto"` 配合 `float64` 应保持 CPU 参考行为。显式的 GPU `float64` 应该严格失败，而不是静默假装已加速。
- MLX 惰性求值意味着没有 `eval()`/同步的计时不是可靠的证据。
