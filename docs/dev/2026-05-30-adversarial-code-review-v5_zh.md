> 这是英文原文的中文翻译。权威版本请参考英文原文。

# 对抗性代码审查 v5 — 2026-05-30

## 摘要

- **发现候选问题：** 55 个（从 74 个原始问题中筛选出的非低置信度项）
- **已确认：** 23 个
- **已驳回：** 45 个（经对抗性验证）
- **审查维度：** 正确性、安全性、性能、边界情况、架构、测试

---

## 已确认的发现

### 中等严重性 (5)

#### M1: `scanning.py` 缩进缺陷 — 第 165-166 行在 `if` 块外部
- **文件：** `src/spektrafilm/runtime/stages/scanning.py:165-166`
- **验证者：** 第 165-166 行与 `if` 语句处于相同的缩进级别（8 个空格），而定义 `m`、`q` 和 `correction_func` 的第 161-164 行位于 `if` 块内部（12 个空格）。当 `_black_correction` 和 `_white_correction` 均未设置时会抛出 `NameError`，不过所有调用方都有防护措施。

#### M2: 每次调用 `apply_lut_pchip_3d` 时 PCHIP 斜率都会被重新计算
- **文件：** `src/spektrafilm/utils/fast_interp_lut.py`
- **验证者：** 尽管文档字符串说明斜率应只准备一次，但每次调用时都会重新计算。不过对于 32^3 Numba-JIT LUT，绝对开销很小，因此"高严重性"夸大了其影响。

#### M3: `_film_cmy_to_print_raw` 缓存未命中时重复应用 LUT
- **文件：** `src/spektrafilm/runtime/services/spectral_lut_compute.py`
- **验证者：** 缓存未命中时的重复 LUT 应用确实存在，但仅三线性插值步骤被浪费（不包括开销较大的 PCHIP LUT 创建），且仅影响每种 LUT 类型的首次调用。

#### M4: `SimulationPipeline.update()` 重新进入 `__init__` — 脆弱的重新初始化
- **文件：** `src/spektrafilm/runtime/pipeline.py:142-144`
- **验证者：** 确认为架构问题。重新进入构造函数会创建新的阶段对象并重新注入共享可变状态。

#### M5: `RuntimePhotoParams` 缺少验证错误路径测试
- **文件：** `tests/`
- **验证者：** 没有任何测试文件包含 `pytest.raises` 或任何断言来验证使用无效的 `film_format_mm`、`upscale_factor` 或 `lut_resolution` 值构造 `RuntimePhotoParams` 时是否会抛出 `ValueError`。

### 低严重性 (18)

#### L1: `np.interp` 中 x 轴降序 — 不会执行插值
- **文件：** `src/spektrafilm/utils/autoexposure.py`
- **验证者：** 对于降序 x 轴，每个元素都满足 `x <= xp[0]`，因此外层 `cp.where` 始终选择 `fp[0]`。由于 `log_exposure` 始终是升序的，该路径不可达。

#### L2: 包含拼写错误的重复文件 — `numba_boost_hightlights.py` 与 `numba_boost_highlights.py`
- **文件：** `src/spektrafilm/utils/numba_boost_hightlights.py`
- **验证者：** 两个文件均存在且存在实质差异（拼写错误版本中有 float64 强制转换和 dtype 检查）。生产代码从拼写错误命名的文件导入；正确命名的文件是孤立文件。

#### L3: grain 循环中浪费的 `np.repeat` 分配
- **文件：** `src/spektrafilm/model/grain.py:39,43`
- **验证者：** np.repeat 分配确实存在且浪费，但是临时性的（循环中每次只有一个）。修复需要修改 fast_interp 的核心接口。

#### L4: 每次 `_fetch_coeffs` 调用创建 4 个 `RegularGridInterpolator` 实例
- **文件：** `src/spektrafilm/runtime/services/spectral_lut_compute.py:76`
- **验证者：** `_fetch_coeffs` 仅被 `compute_lut_spectra` 调用，而后者是一次性 LUT 生成步骤，因此性能影响可忽略不计。

#### L5: 结构性缺陷 `_correction_fucntion` — 引用未定义变量
- **文件：** `src/spektrafilm/runtime/stages/scanning.py:165-166`
- **验证者：** 第 165-166 行在 `if` 块外部并引用未定义变量，但所有三个调用方在调用该函数之前都有提前返回的防护，因此不可能触发。

#### L6: `lognorm_from_mean_std` 引用未导入的 `scipy`
- **文件：** `src/spektrafilm/model/grain.py:247`
- **验证者：** 如果被调用会抛出 `NameError`，但它是死代码，从未在模块外部被调用。

#### L7: `scanning.py` 中使用 `print()` 而非 `logging.warning()`
- **文件：** `src/spektrafilm/runtime/stages/scanning.py:133`
- **验证者：** 第 133 行使用 `print(f"Warning: ...")` 而非 `logging.warning()`，且未导入 `logging` 模块。

#### L8: GPU 路径在无防护的情况下重复归一化
- **文件：** `src/spektrafilm/runtime/services/spectral_lut_compute.py:141`
- **验证者：** GPU 路径重复了归一化操作但没有 `lut.py:41` 中的防护。仅在 GPU 后端激活且前一次调用已填充缓存后，后续调用出现 `data_min==data_max` 时才会触发 —— 极端边界情况。

#### L9: `np.random` 全局状态变更 — 非线程安全
- **文件：** `src/spektrafilm/model/grain.py:22-57`
- **验证者：** 该函数通过 `get_state/set_state` 显式保存/恢复 `np.random` 全局状态，这本质上不是线程安全的。实际风险很小，因为流水线不会从多个线程调用。

#### L10: `init_params()` 在导入时求值 — 导入时 I/O
- **文件：** `src/spektrafilm/runtime/params_builder.py:10`
- **验证者：** `init_params()` 在模块导入期间的函数定义时被求值一次，触发两次 `load_profile()` 调用来从磁盘读取和解析 JSON 文件。真正的问题是导入时 I/O 而非可变共享状态。

#### L11: 缺少 `smoothstep`、眩光和 grain 模糊函数的测试
- **文件：** `tests/`
- **验证者：** 这些函数是委托给已测试工具函数的薄包装，通过流水线冒烟测试进行了验证。属于小缺口而非中等严重性风险。

#### L12: `runtime_float_dtype` 死代码；`validate_float_dtype` 未测试
- **文件：** `src/spektrafilm/utils/dtypes.py`
- **验证者：** `runtime_float_dtype` 零调用方（死代码）。`validate_float_dtype` 是一个简单的单行防护，仅从 `load_image_oiio` 中以安全默认值 `dtype=np.float32` 调用。

#### L13: `resize_for_preview` — 零非模拟测试覆盖
- **文件：** `src/spektrafilm/utils/preview.py`
- **验证者：** 所有测试引用都是 monkeypatch 替换 —— 没有测试调用实际函数。

#### L14: `build_hdr_debug_sidecar` — 零测试覆盖
- **文件：** `src/spektrafilm/utils/hdr_photo.py`
- **验证者：** 生产代码中零调用方，但它是简单的诊断 JSON 构建器，其失败不会影响图像输出。

#### L15: `standard_illuminant` — 无专用测试
- **文件：** `src/spektrafilm/model/illuminants.py`
- **验证者：** 每个测试调用点都通过 monkeypatch 替换了它。没有测试直接调用任何分支。

#### L16: HEIF gain map 加载/补丁/元数据路径未测试
- **文件：** `src/spektrafilm/utils/gain_map_io.py`
- **验证者：** 没有测试文件引用 `_load_gain_map_heif`、`_patch_heif_for_iso21496` 或 `_gainmap_metadata_to_iso_dict`。现有 HEIF 测试仅验证 `ImportError` 防护。

#### L17: `gamma_beta` 分支 — 死代码
- **文件：** `src/spektrafilm/model/grain.py`
- **验证者：** 没有调用方传递 `method='gamma_beta'`（均使用默认值 `poisson_binomial`）。`GrainParams` 没有 `method` 字段。零测试覆盖该路径。

#### L18: `_remove_sRGB_cctf` 的测试容差过宽
- **文件：** `tests/test_color_reference.py`
- **验证者：** 范围检查 `0.20 < result < 0.22`（允许约 6.5% 偏差）比必要的更宽。`pytest.approx(0.2140, abs=1e-4)` 会是更精确的回归防护。

---

## 已驳回的发现 (45)

所有 45 个已驳回的发现均经独立质疑验证被拒绝。常见驳回原因：
- **不可达代码路径** — 所有调用方都对边界情况有防护
- **死代码** — 函数在生产中从未被调用
- **有意设计** — 行为是设计如此，不是 bug
- **影响可忽略** — 操作仅运行一次或作用于极小数组
- **标准模式** — "问题"实际上是常见/可接受的模式

---

## 差距分析

### 未审查的模块

本次审查从 74 个非 `__init__` Python 文件中检查了约 12 个源文件。未审查的重要模块：

| 模块 | 行数 | 关注点 |
|--------|-------|---------|
| `model/diffusion.py` | 666 | 最大的模型文件，无测试，未审查 |
| `utils/fast_interp_lut.py` | 827 | Numba-JIT LUT 插值，无测试 |
| `utils/hdr_photo.py` | 1391 | 最大的工具文件，调用 `subprocess.run()` |
| `utils/gain_map_io.py` | 516 | 二进制解析代码，无 IO 测试 |
| `utils/fast_gaussian_filter.py` | 413 | 性能关键的 numba 工具，无测试 |
| `utils/fast_stats.py` | 353 | 性能关键的 numba 工具，无测试 |
| `runtime/stages/filming.py` | — | 仅审查了 `scanning.py` |
| `runtime/stages/printing.py` | — | 仅审查了 `scanning.py` |
| `runtime/api.py` | — | 未审查 |
| `spektrafilm_gui/` | 24 个文件 | 审查中零提及 |

### 六个审查维度遗漏的模式

1. **numba 内核中的 `fastmath=True`** — `numba_boost_highlights.py` 和 `numba_boost_hightlights.py` 使用 `@njit(fastmath=True)`，启用了不安全的浮点优化（重结合、FMA 收缩），可能违反"零精度/质量损失"约束。

2. **资源管理** — `utils/io.py` 使用手动 `.close()` 调用打开 OIIO `ImageInput` 句柄（4 处），而非上下文管理器。异常时会泄漏句柄。

3. **模块级可变 GPU 内核缓存** — `gpu/kernels/density.py` 和 `gpu/kernels/filters.py` 使用模块级全局变量进行内核缓存，无线程安全保障。

4. **整个 GUI 包未审查** — `spektrafilm_gui/` 中 24 个文件零覆盖。

---

## 结论

经过 v4 修复后，代码库处于**良好状态**。5 个中等严重性发现中：
- 2 个是结构性/架构问题（M4 流水线重新初始化，M2 斜率重新计算）
- 2 个是性能微问题（M3 重复 LUT，M2 斜率重新计算）
- 1 个是缺失测试（M5 验证错误路径）

未确认任何严重或高严重性问题。低严重性发现主要是死代码、内部函数缺失测试以及可忽略的边界情况。
