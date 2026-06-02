> 这是英文原文的中文翻译。权威版本请参考英文原文。

# MLX Compile Element-Wise Chain 实现 - 2026-05-31

## 范围

本次修改实现了针对 MLX 专属纯逐元素链的受控 `mx.compile` 使用。CPU 行为、显式 `float64` CPU 路由、Halide 融合光谱路由、LUT 插值语义以及最终管线物化均保持不变。

## 使用的官方 MLX 约束

- `mx.compile()` 可以通过融合操作和消除重复计算来缩减计算图规模。
- 对已编译函数的首次调用会触发计算图的追踪和编译。
- 普通已编译函数会在输入形状变化时重新编译。
- `shapeless=True` 可避免因形状变化触发的重新编译，但对于依赖静态形状的计算图而言是不安全的。Spektrafilm 图像处理保持默认的形状感知行为。
- 已编译函数不得检视或物化数组。本实现将 `print`、`np.asarray`、`.item()`、`mx.eval()`、`mx.synchronize()` 和标量归约操作置于已编译链之外。

参考文档：

- MLX 编译文档：https://ml-explore.github.io/mlx/build/html/usage/compile.html
- MLX 延迟求值文档：https://ml-explore.github.io/mlx/build/html/usage/lazy_evaluation.html

## 实现

`MlxBackend.compiled_elementwise(name, function, *sample_args)` 通过以下条件缓存已编译的可调用对象：

- 操作名称
- MLX 输入形状
- MLX 输入 dtype

如果当前 MLX 模块未暴露 `compile` 方法，该辅助函数将返回原始函数，从而保证模拟/测试模块和旧版 MLX 构建的安全性。

已编译的生产链：

- `density_to_light`：`10 ** (-density) * illuminant`，后接有限值清理。
- `gpu/kernels/color.py` 中的 CCTF 编码/解码传递函数。
- 高光提升中的逐像素指数曲线（在 `x_max` 已归约为 Python 标量之后）。运行时标量参数以 `(4,)` 后端数组形式传递，因此修改曝光参数无需重新编译 Python 闭包。

有意未编译的操作：

- `safe_log10(max(x, 0) + 1e-10)`：基准测试表明编译后反而更慢。
- `einsum`、`matmul`、LUT gather/插值、高斯 IIR/FIR、FFT 卷积和自定义 Metal 内核。
- 任何转换为 NumPy、执行同步、打印或基于张量值进行分支的路径。

## 基准测试

命令：

```bash
.venv/bin/python scripts/benchmark_mlx_compile_elementwise.py --height 512 --width 512 --iterations 10
```

产物：

- `docs/dev/benchmark-artifacts/mlx_compile_elementwise_20260531/benchmark-20260531-172206.md`
- `docs/dev/benchmark-artifacts/mlx_compile_elementwise_20260531/benchmark-20260531-172206.json`

结果基于固定的 `512x512x3` float32 输入、固定种子 `20260531`、3 次预热迭代、10 次计时迭代，以及每次计时采样时显式调用 `mx.eval()` 和 `mx.synchronize()`。

| 链 | 基线中位数 | 已编译中位数 | 中位数加速比 | 最大绝对差异 | 生产决策 |
|---|---:|---:|---:|---:|---|
| `safe_log10` | 0.399 ms | 0.719 ms | 0.555x | 0.000e+00 | 不编译 |
| `density_to_light` | 27.368 ms | 3.349 ms | 8.171x | 0.000e+00 | 编译 |
| `cctf_encode_srgb` | 0.680 ms | 0.466 ms | 1.461x | 2.384e-07 | 编译传递链 |
| `boost_highlights` | 0.513 ms | 0.273 ms | 1.878x | 0.000e+00 | 编译 |

## 验证

在拒绝编译 `safe_log10` 之后进行的新鲜定向验证：

```text
.venv/bin/python -m pytest tests/test_gpu_backend.py tests/test_gpu_color_chain.py tests/test_gpu_density.py tests/test_gpu_pipeline.py -q
76 passed, 4 skipped
```

最终验证：

```text
.venv/bin/python -m pytest tests/test_gpu_backend.py tests/test_gpu_lut.py tests/test_gpu_filters.py tests/test_gpu_density.py tests/test_gpu_color_chain.py tests/test_gpu_pipeline.py tests/test_gpu_primitives.py -q
115 passed, 7 skipped

.venv/bin/python -m pytest --ignore=tests/gui -q
701 passed, 7 skipped, 1 warning

.venv/bin/python -m compileall -q src/spektrafilm tests scripts
passed

git diff --check
passed
```

## 自查审计

- 没有已编译函数执行物化、同步、打印、`.item()` 或标量归约操作。
- 缓存键按形状/dtype 区分。形状变化会创建单独的已编译可调用对象，而非使用无形状编译。
- 基准测试计时包含求值和同步时间。
- `safe_log10` 在基准测试证据显示负加速比后已从生产编译中移除。
- `density_to_light`、`safe_log10` 和 `boost_highlights` 的数值差异为零；CCTF 编码的差异在 float32 精度范围内。
- 已有的工作树未提交变更未被回退。
