# GPU Backend 100 Percent Completion Report

日期：2026-05-31

## 结论

本轮把 GPU 后端完成度推进到“可验证完成”的状态，但这里的 100% 不是宣称所有未来优化都已经做完，而是：

- MLX/Metal 是当前 Apple Silicon 上的 production GPU backend，已接入 runtime、GUI 参数流、光谱直算/LUT、density/color/filter/grain/glare/scanner 后处理等主路径，并通过当前本机测试。
- `gpu_validate=True` 不再是假 `ok`，会实际重跑 CPU reference、计算误差指标并在超容差时失败。
- CuPy 路径按 CUDA/ROCm 硬件门控保留，代码路径和测试 skip 语义正确；当前 Apple Silicon 环境无法给 CUDA 实测结论。
- Halide 仍标注为 explicit experimental/JIT backend。虽然现有 Halide spectral/JIT parity 测试通过，并且已有本地性能报告显示 direct spectral path 很快，但没有 GPU target/schedule/AOT 证据前，不把它计入 production GPU。
- 文档、测试和 golden baselines 已更新到当前工作区的确定性输出。

因此，本报告把完成度评为：

| Backend/Area | 完成度 | 证据边界 |
| --- | ---: | --- |
| MLX/Metal production path | 100% | 当前 Apple Silicon 本机通过 targeted GPU tests、non-GUI full suite、GUI suite 和 real `gpu_validate` smoke。 |
| GUI/runtime 参数接入 | 100% | GUI tests 通过；backend/precision 文案与 runtime 行为一致；worker failure path 覆盖。 |
| `gpu_validate` correctness | 100% | CPU reference 对比、容差、失败抛错、debug/non-GPU skip 均有测试。 |
| CuPy path | 100% hardware-gated | 本机无 CUDA/ROCm，不声称性能实测；代码路径和 skip 边界保留。 |
| Halide path | 100% experimental boundary | JIT parity/generator tests 通过；文档明确不是 production GPU。 |

## 本轮新增/修复

### 1. 真实 GPU validation

修改：

- `src/spektrafilm/runtime/params_schema.py`
- `src/spektrafilm/runtime/pipeline.py`
- `tests/test_gpu_validate.py`

行为：

- 新增 `SettingsParams.gpu_validate` 和 `SettingsParams.gpu_validation_tolerance`。
- `SimulationPipeline.process()` 会把原始输入和当前 backend 输出交给 `_run_gpu_validate()`。
- 验证器 deep-copy 当前 params，强制 `compute_backend="cpu"`、`gpu_precision="float64"`、`gpu_validate=False`，避免递归验证。
- 输出 `status/backend/reference_backend/precision/tolerance/shape/reference_shape/max_abs_diff/mean_abs_diff/finite`。
- shape mismatch、非有限值或超过容差会抛 `RuntimeError`，GUI worker 能按普通失败路径上报。
- debug 模式继续 explicit skip；CPU fallback/non-GPU backend 也 explicit skip，不再假装 GPU ok。

实测 MLX smoke：

```text
backend mlx
shape (4, 4, 3)
validation {'status': 'ok', 'backend': 'mlx', 'reference_backend': 'cpu', 'precision': 'float32', 'tolerance': 1e-05, 'shape': (4, 4, 3), 'reference_shape': (4, 4, 3), 'max_abs_diff': 2.088169911984572e-07, 'mean_abs_diff': 1.3243073424910415e-07, 'finite': True}
```

### 2. Glare backend array residency

修改：

- `src/spektrafilm/model/glare.py`
- `tests/test_glare.py`

问题：

- 前一版只在 backend 有 `mx` 或 `cp` 属性时才把 `illuminant_xyz` 转成 backend array，导致 generic GPU-like backend test 证明的 backend math 没有发生。

修复：

- array conversion 判断改为 `supports_gpu`。
- stochastic sampler 仍只对 MLX/CuPy 启用；Halide/generic backend 不误进 MLX/CuPy random path。

### 3. Input CCTF 与 print-balance reference 解耦

修改：

- `src/spektrafilm/runtime/stages/filming.py`
- `tests/test_pipeline_smoke.py`
- `tests/test_upstream_parity.py`

问题：

- `FilmingStage.__init__()` 计算 18% 灰 print-balance reference 时，复用了 `io.input_cctf_decoding`。当输入是 sRGB 编码并启用 CCTF decoding 时，内部 reference `0.184` 也被当成 encoded value 解码，导致输出大幅偏亮。

修复：

- print-balance 的 `rgb_midgray` 和 exposure-compensated reference 固定按 scene-linear `0.184` 解释，即 `apply_cctf_decoding=False`。
- `test_cctf_encoded_midgray_matches_linear_midgray` 恢复通过。
- 当前确定性输出发生约 `4e-5` 的 baseline 漂移，已更新 `pipeline_smoke` 和 upstream parity golden 值。

### 4. Profile save test hook 修复

修改：

- `src/spektrafilm/profiles/io.py`

问题：

- 安全测试 monkeypatch `spektrafilm.profiles.io.pkg_resources.files`，但代码在函数内部 import，模块上没有 `pkg_resources` 属性。

修复：

- `importlib.resources` 移到模块级别，测试能在构造 resource path 前验证 path traversal 已被拒绝。

## 已复核的既有 GPU 接入状态

来自本轮代码复核和上一轮已落地修复：

- `SpectralLUTService` GPU direct/LUT path 保持图像数据 backend-resident；只把小型 test/LUT 构建边界转 NumPy。
- MLX layered grain 使用 backend density-layer interpolation。
- scanner glare 使用 MLX/CuPy backend random/filter path，非支持 backend 保守 CPU fallback。
- scanner black/white correction 和 CCTF/clip 在 GPU path 使用 backend ops。
- CuPy 3D LUT 使用 prepared LUT，避免重复转 device array。
- GUI backend/precision 文案已和 runtime 行为一致。
- `SimulationWorker.run()` 能把 `BaseException` 子类收敛成 failure signal。

## 验证证据

所有命令在 `/Users/retriedstormtrooper/Documents/spektrafilm-main` 执行。pytest 使用 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`，避免外部插件影响项目测试。

```text
.venv/bin/python -S -m py_compile src/spektrafilm/runtime/pipeline.py src/spektrafilm/runtime/params_schema.py tests/test_gpu_validate.py
pass

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest tests/test_gpu_validate.py -q
3 passed in 2.21s

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest tests/test_gpu_validate.py tests/test_gpu_pipeline.py tests/test_spectral_lut_service.py tests/test_grain.py tests/test_glare.py tests/test_color_reference.py tests/gui/test_controller_runtime_module.py -q
54 passed, 2 skipped in 3.26s

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest --ignore=tests/gui -q
722 passed, 7 skipped, 1 warning in 58.84s

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest tests/gui -q
152 passed in 41.02s

.venv/bin/python -m compileall -q src tests
pass

git diff --check
pass
```

Additional GPU/Halide slices were also run while isolating a broad dynamic-loader stall:

- GPU backend/primitives/density/color/filter/LUT/highlight/FFT/LUT tests: all passed individually.
- Halide backend/color/filter/LUT/spectral tests: all passed individually.
- Halide Android/generator CMake tests: `17 passed in 119.70s`.

One broad hand-built pytest command that mixed many GPU/Halide files was terminated after it sat idle in macOS `dyld` dynamic loading. This did not reproduce in the full non-GUI suite, which completed successfully.

## Best-Practice Basis

The implementation choices follow official/primary sources:

- MLX lazy evaluation: keep arrays resident and avoid accidental NumPy conversion until output/validation boundaries. <https://ml-explore.github.io/mlx/build/html/usage/lazy_evaluation.html>
- MLX compilation: compile pure tensor chains only with stable shape behavior and tested cache semantics. <https://ml-explore.github.io/mlx/build/html/usage/compile.html>
- MLX custom Metal kernels: cache kernel objects and avoid unnecessary per-call JIT/contiguous conversion. <https://ml-explore.github.io/mlx/build/html/dev/custom_metal_kernels.html>
- CuPy performance/memory: use memory pools and CUDA-event-aware benchmark methodology. <https://docs.cupy.dev/en/stable/user_guide/performance.html> and <https://docs.cupy.dev/en/stable/user_guide/memory.html>
- Halide GPU: call a path GPU only when target features and schedule use GPU tiling/blocking. <https://halide-lang.org/tutorials/tutorial_lesson_12_using_the_gpu.html>

## Remaining Acceleration Space

These are future optimization opportunities, not current completion blockers:

1. Input preprocessing remains CPU/NumPy float64: `_preprocess_base()` still copies input to NumPy and runs autoexposure/crop before backend entry. Moving resize/crop and input CCTF normalization onto MLX could lower peak memory for very large images.
2. MLX outer-chain compile can go further: scanner `XYZ -> correction -> glare -> RGB -> CCTF -> clip` has more fusion potential, but random/stateful glare and shape-sensitive code need guarded compile tests.
3. Large-image tiling is not fully stage-aware: generic tiling exists, but production runtime does not yet choose tiles from backend memory pressure. A stage-aware tiled pipeline could reduce Metal peak memory.
4. FFT/filter sync points need benchmark-driven tuning: explicit `eval/clear_cache` can protect memory but may reduce lazy fusion. Keep only where measured peak-memory wins justify it.
5. Halide true GPU/AOT remains future work: existing host JIT kernels are useful and tested, but a production Halide GPU path needs target feature checks, GPU schedule, and preferably persistent AOT artifacts.
6. CuPy needs real CUDA/ROCm hardware evidence: local Apple Silicon can only validate skip/dispatch semantics.

## Remaining Precision Space

1. MLX/CuPy float32 is validated against CPU float64 by tolerance, not bit-exact equality. MLX does not provide the project’s CPU float64 reference path on Metal.
2. LUT paths use trilinear GPU interpolation in several places; CPU reference paths may use higher-order interpolation. Higher LUT resolution, tetrahedral interpolation, or backend PCHIP equivalents could reduce LUT-path error.
3. Halide float32/JIT kernels should keep visual-diff artifacts and PSNR gates if promoted beyond experimental.
4. Stochastic grain/glare precision includes RNG distribution parity, not only deterministic array math. Current tests verify supported paths, but film-look parity should also use image-level perceptual baselines.

## Final Self-Review

- Is there any GPU setting that silently falls back to CPU without being documented? No known production MLX fallback remains in the verified main path. CuPy and Halide boundaries are explicit.
- Does `gpu_validate` prove real parity when enabled? Yes; it runs CPU reference and records metrics, and real MLX smoke passed.
- Does GUI pass backend settings into runtime? Yes; GUI tests passed and widget tooltips no longer contradict runtime precision rules.
- Are Halide/CuPy limitations truthfully represented? Yes; CuPy is hardware-gated, Halide is experimental/JIT.
- Is every new production change backed by test or validation? Yes; all new changes are covered by focused tests plus full non-GUI and GUI suites.
