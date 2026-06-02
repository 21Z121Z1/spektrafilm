> 这是英文原文的中文翻译。权威版本请参考英文原文。

# 自主会话协调计划

**日期：** 2026-05-31
**协调线程：** `019e792e-d732-71c1-b9bc-bc18b0c063ed`
**工作区：** `/Users/retriedstormtrooper/Documents/spektrafilm-main`

## 目标

协调当前 `spektrafilm-main` 的活跃工作，避免干扰并发的 GPU/MLX/Halide 审查工作，仅合并可以通过有针对性的测试和仓库验证证明的高置信度修复。

## 当前工作区事实

- 当前检出分支为 `develop`，且不是独立的 git worktree：`.git` 和 git 公共目录为同一路径。
- 工作树已包含大量未提交的修改，涵盖 GPU 内核、MLX/Halide 后端、运行时阶段、模型代码、GUI 参数、测试、基准测试脚本和文档。
- 近期活跃的 Codex 线程正在同一仓库中进行 MLX/Halide 审查和对抗性审查，因此本协调线程必须避免大规模的重叠重写。
- 已从当前工作树以只读提示请求了一个单独的后台 worktree 审计线程。
- 本仓库最强的本地约定仍然是：除非正在更改显式启用路径，否则保留 SDR 行为；通过 `uv run --extra dev ...` 或 `.venv/bin/python` 而非直接使用 `python3` 进行验证。

## 外部参考检查

- [MLX 惰性求值文档](https://ml-explore.github.io/mlx/build/html/usage/lazy_evaluation.html) 确认操作是惰性的，计算在执行 `eval()` 时发生；这支持在 MLX 基准测试中要求同步计时，而不信任未同步的计时结果。
- [MLX 统一内存文档](https://ml-explore.github.io/mlx/build/html/usage/unified_memory.html) 确认数组存在于统一内存中，操作在执行时选择执行设备；这支持尽量减少不必要的 CPU/MLX 转换开销，但不能消除强制求值以进行验证的需求。
- [Halide 命名空间文档](https://halide-lang.org/docs/namespace_halide.html) 将 `fast_pow` 描述为近似的 Float32 操作；在精度敏感的颜色传输函数中将其替换为 `pow` 与本仓库面向对等性的测试一致。

## 本次协调通过已确认的高价值缺口

`src/spektrafilm/model/grain.py` 仍然允许公共辅助函数 `apply_grain_to_density(..., n_sub_layers=0)` 通过除以零产生 NaN。一个新测试目前将此损坏行为记录为预期行为。这是错误的契约：无效的 grain 层数应尽早以明确的 `ValueError` 失败，与新的 `GrainParams.__post_init__` 验证保持一致。

## 实施范围

1. 将预期 `n_sub_layers=0` 产生 NaN 的回归测试替换为要求对零值和负值产生明确 `ValueError` 失败的测试。
2. 在 `apply_grain_to_density()` 顶部添加最小防护，使直接调用者获得与 `GrainParams` 相同的明确契约。
3. 运行针对 grain 和 photo-param 验证的有针对性测试。
4. 运行不会掩盖活跃并发工作的轻量级仓库检查：`git diff --check` 和 `compileall`。
5. 如果有针对性的验证暴露了更广泛的问题，将其分类为由本协调修复引起、预先存在的未提交工作、缺失的本地工具链或并发工作所致。

## 执行结果

协调器拥有的变更：

- `apply_grain_to_density()` 现在在除以零或产生 NaN 之前，对 `n_sub_layers < 1` 抛出 `ValueError`。
- `tests/test_grain.py` 现在断言公共辅助函数拒绝零值和负值的子层数。
- `scripts/benchmark_halide_mlx_parity.py` 已添加，以满足工作树中已存在的 Halide/MLX 基准辅助测试。

从并发的 GPU/profile/filter 工作中验证的当前工作区行为：

- Filter 加载现在将 Akima 超出范围的 NaN/inf 值转换为 `0.0`。
- Profile 加载/保存现在在资源查找之前拒绝不安全的预设名称，且 `ProfileData` 在构造期间执行形状和值验证。
- MLX LUT 路径在调用者提供已准备好的 MLX 数组时避免冗余的 `mx.array()` 转换。
- Halide 融合的 CMY 到 log XYZ/raw 路径与 NumPy 参考在动态光谱长度和清晰的 NaN 光值（如通用后端路径）上匹配。

在最终观察到的工作区状态上完成的验证：

- `.venv/bin/python -m pytest tests/test_grain.py::TestApplyGrain::test_apply_grain_to_density_rejects_invalid_sub_layers -q` -> `2 passed`。
- `.venv/bin/python -m pytest tests/test_grain.py -q` -> `12 passed`。
- `.venv/bin/python -m pytest tests/test_photo_params.py::TestRuntimePhotoParamsValidation -q` -> `6 passed`。
- `.venv/bin/python -m pytest tests/test_edge_cases.py tests/test_profiles.py -q` -> `66 passed`。
- `.venv/bin/python -m pytest tests/test_gpu_lut.py::test_compute_with_lut_gpu_trilinear_reuses_prepared_backend_arrays tests/test_gpu_lut.py::test_trilinear_3d_lut_mlx_prepared_arrays_avoid_mx_array_copy tests/test_gpu_lut.py::test_cubic_2d_lut_mlx_prepared_arrays_avoid_mx_array_copy -q` -> `3 passed`。
- `.venv/bin/python -m pytest tests/test_halide_spectral.py::test_fused_cmy_to_log_xyz_matches_numpy_for_hwc_runtime_shape tests/test_halide_spectral.py::test_fused_cmy_to_log_raw_matches_numpy_for_printing_chain 'tests/test_gpu_density.py::test_cmy_to_log_xyz_backend_matches_cpu_reference[halide]' -q` -> `3 passed`。
- `.venv/bin/python -m pytest tests/test_halide_spectral.py::test_fused_cmy_to_log_xyz_zeroes_nan_light_like_generic_backend tests/test_halide_spectral.py::test_fused_cmy_to_log_raw_zeroes_nan_light_like_generic_backend -q` -> `2 passed`。
- `.venv/bin/python -m compileall -q src tests scripts` -> 通过。
- `git diff --check` -> 通过。
- `.venv/bin/python -m pytest --ignore=tests/gui -q` -> `686 passed, 7 skipped, 1 warning`。

剩余的警告是预先存在的 `tests/test_autoexposure.py::test_legacy_autoexposure_methods_remain_finite_on_small_images[matrix]` 在 `src/spektrafilm/utils/autoexposure.py:121` 中的除以零运行时警告；测试通过，且不属于本次协调修复的范围。

## 非目标

- 不重写当前由活跃线程处理的更广泛的 MLX/Halide 优化。
- 不回退或规范化现有的未提交文件，除非它们直接阻碍本次修复。
- 在其他活跃线程仍在更改同一工作树时，不声称仓库已完全准备好发布。
- 除非用户明确要求提交，否则不进行提交。

## 100% 置信度循环

在标记目标完成之前，执行了以下循环：

1. 重新阅读更改的测试和实现。
2. 检查无效的 `n_sub_layers` 是否仍能通过直接 CPU 或 MLX 调用到达除以零的路径。
3. 重新运行有针对性的测试并阅读输出。
4. 重新运行 `git diff --check` 和 `compileall`。
5. 如果最终状态与本计划不同，则更新本文档或另一个当前文档。
6. 如果任何答案没有事实支持，则修补或记录差距并重复相关验证。

本次通过的最终答案：无效的 `n_sub_layers` 现在已在公共辅助函数边界处被阻止，已知的有针对性的失败在当前工作区中均为绿色，非 GUI 测试套件正在通过。仓库仍是一个包含许多不相关活跃编辑的脏共享工作树，因此置信度适用于当前已测试的状态，而非作为未来发布单元的未审查并发差异。
