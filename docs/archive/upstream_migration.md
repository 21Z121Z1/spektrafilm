# 上游合并迁移文档

## 背景

本地 `develop`（fork: `21Z121Z1/spektrafilm`）与上游 `upstream/dev`（`andreavolpato/spektrafilm`）发生了分支分歧：

- **本地**多了 4 个提交：GPU backend、ColorEncoding/HDR、SpectralInputPolicy、简洁 ICC 集
- **上游**多了 7 个提交：profile creator 重构、hanatos2025 bandpass+surface、TIFF 输出、ICC/EXIF 元数据、coupler diffusion tail、代码清理

两者在相同源文件上做了不同方向的修改，直接 merge 会有大量冲突。

## 决策记录

### 1. 以本地为基准

**决定**：保留本地全部代码（GPU、ColorEncoding、SpectralInputPolicy），手动移植上游新功能。

**理由**：本地 GPU 加速是核心性能改进，ColorEncoding 提供了更完整的色彩管线。上游的功能是附加性的（新光谱模型、新输出格式），可以叠加上去。

### 2. ICC 配置文件方案

**决定**：采用上游的 ellelstone + saucecontrol 完整 ICC 集。

**理由**：上游提供了更多变体（不同 gamma、不同 V2/V4 版本），覆盖更多色彩空间（ACES、Gray 等），与 EXIF 色彩空间标签的映射更完整。代价是文件体积增加 ~500KB。

### 3. 不执行文件清理

**决定**：不上游的 `archive/`、`proto/`、`scripts/`、`examples/` 清理，也不删除 `uv.lock`。

**理由**：这些目录包含实验代码和工具脚本，删除可能影响工作流。`uv.lock` 包含本地 GPU 依赖项。

### 4. pyproject.toml 剥离 profile_creator

**决定**：接受上游改动，移除 `spektrafilm_profile_creator` 的包注册。

**理由**：主代码（`spektrafilm`、`spektrafilm_gui`）完全不依赖 profile_creator。开发模式下（`pip install -e .` / `uv`）包仍然可导入，只是构建 wheel 时不包含。profile_creator 仅被 `scripts/` 和 `examples/` 中的工具脚本引用。

## 手动移植的上游功能

| # | 功能 | 来源提交 | 文件 | 移植方式 |
|---|---|---|---|---|
| 1 | `STANDARD_OBSERVER_LMS` | `d383f7d` | `config.py` | 纯新增，无冲突 |
| 2 | `hanatos2025_adaptation_*` 字段 | `d383f7d` | `profiles/io.py` | 纯新增字段 + `__post_init__` 初始化 |
| 3 | `diffusion_tail_um` / `diffusion_tail_weight` | `3a7a09b` | `params_schema.py` | 新增字段到 `DirCouplersParams` |
| 4 | `hanatos2025_sensitiviy_adaptation` | `d383f7d` | `params_schema.py` | 新增字段到 `SettingsParams` |
| 5 | Coupler exponential tail | `3a7a09b` | `model/couplers.py` | GPU 路径：混合 fallback；CPU 路径：`fast_gaussian_filter` + `fast_exponential_filter` 加权组合 |
| 6 | Bandpass+surface 函数 | `d383f7d` | `utils/spectral_upsampling.py` | 在 `SpectralInputPolicy` 类后、`Mallett2019` 前插入。保留本地全部代码 |
| 7 | `compute_hanatos2025_adaptation_tc_lut` | `d383f7d` | `utils/spectral_upsampling.py` | 在 `compute_hanatos2025_tc_lut` 后新增 |
| 8 | Adaptation LUT 缓存 | `d383f7d` | `runtime/services/spectral_lut_compute.py` | 扩展 `get_filming_tc_lut` 方法签名 |
| 9 | Adaptation 路径 | `d383f7d` | `runtime/stages/filming.py` | 在 `_rgb_to_film_raw` 中添加 adaptation 分支 |
| 10 | ICC 完整集 | `54e947c` | `data/icc/` | `git checkout upstream/dev -- src/spektrafilm/data/icc/` + 删除本地简单 ICC |
| 11 | `_load_icc_profile` | `54e947c` | `utils/io.py` | 替换本地 `_ICC_PROFILES` + `resolve_icc_profile_bytes` |
| 12 | `_set_color_space_tags` | `353af42` | `utils/io.py` | 新增函数，在 `write_image_metadata` 中调用 |
| 13 | TIFF 8/16/32-bit | `57bf072` | `utils/io.py` | 在 `save_image_oiio` 的 EXR 分支前插入 TIFF 分支 |
| 14 | `test_exif_metadata.py` | `353af42` + `54e947c` + `57bf072` | `tests/` | 从上游复制，适配本地 API |

## 测试结果

- **305 passing**, 0 个新失败
- 6 个预存失败：3 个 profiles_creator 回归基线 + 3 个 pipeline snapshot（合并前已存在）

## 注意点

### spectral_upsampling.py 的冲突最大

上游在此文件中做了两件事：
1. 删除了本地新增的 `SpectralInputPolicy`、`rgb_to_raw_hanatos2025_backend`、`precompute_hanatos2025_constants`
2. 新增了 bandpass+surface 函数

移植策略：**保留本地完整文件**，手动在中间插入上游的新函数。`rgb_to_raw_hanatos2025` 签名保持不变（adaptation 由 `spectral_lut_compute.py` 在 LUT 层面处理）。

### io.py 是第二冲突区域

上游改了三次 `io.py`（EXIF → ICC → TIFF），本地完全重写了。移植需要：

1. ICC 函数替换（`_ICC_PROFILES` → `_ICC_FILENAMES` + `_load_icc_profile`）
2. TIFF 分支插入（EXR 和 error 之间）
3. EXIF 标签集成到本地的 `write_image_metadata`
4. 更新 ICC 检测函数（`_known_color_space_from_icc_profile`、`_known_color_space_from_chromaticities`）
5. 使 `source_metadata` 可选以兼容上游测试

### couplers.py 的默认值变更

添加 `diffusion_tail_um=200.0`、`diffusion_tail_weight=0.06` 后，改变了 DIR couplers 的默认行为。这导致 regression snapshot 测试产生微小差异（~4e-6 abs diff）。

如果希望行为完全不变，可以将默认值改为 `0.0`，让用户显式启用。

### 备份分支

执行合并前创建了 `backup/develop-before-merge` 分支（已删除），对应 commit `a3196a5`。
