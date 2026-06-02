> 这是英文原文的中文翻译。权威版本请参考英文原文。

# Profile-Aware HDR 审计计划

**目标：** 确定当前 profile-aware HDR 曲线路径在数学上是否正确、在物理/语义上是否连贯、以及测试覆盖是否充分，除非有确凿的 bug 被证实，否则不改变现有行为。

**范围：** 对本地 `develop` 工作树上跟踪 `origin/develop` 的 `profile_aware` / `profile_preserving` / `modern_recovery_peak_budget` 实现进行只读审计。

**约束：** 审计期间不得修改生产行为。任何可能的修复必须首先在审计报告中提供文件、函数、影响和回归证据作为依据。

---

## 核心文件

- `src/spektrafilm/utils/hdr_photo.py`
  - `HDRPhotoMapping`
  - `prepare_hdr_photo_renditions()`
  - `_prepare_profile_aware_renditions()`
  - `_content_headroom()`
  - `_apply_hdr_highlight_color()`
  - `_apply_path_to_white()`
  - `_gamut_compress_luma_preserving()`
  - `gamut_map_oklch()`
- `src/spektrafilm/utils/hdr_curve_profiles.py`
  - `FilmPrintHDRCurveProfile`
  - `build_profile_preserving_hdr_curve()`
  - `profile_relative_hdr_gain_ev()`
  - `profile_modern_recovery_budgeted_gain_ev()`
  - `budget_recovery_gain_ev()`
  - `sample_runtime_curve_profile()`
- `src/spektrafilm/data/hdr_curve_profiles/curve_profiles_v2.json`
- `src/spektrafilm/data/hdr_curve_profiles/samples/*.json`
- `src/spektrafilm/data/hdr_curve_profiles/README.md`
- `tests/test_hdr_photo.py`
- `tests/test_hdr_curve_profiles.py`
- `tools/validate_profile_aware_hdr_raw_samples.py`
- 相关文档：
  - `docs/superpowers/plans/2026-05-25-profile-aware-hdr-photo-export.md`
  - `docs/dev/modern_recovery_peak_budget_plan.md`
  - `docs/hdr_profile_aware_raw_validation.md`
  - `docs/hdr_profile_aware_raw_validation.json`

## 需要验证的数学不变量

- `hdr_mapping_mode="profile_aware"` 时需要 `scene_luminance`，且仅归一化到 `diffuse_white` 一次。
- `s_profile` 对于有效的递增配置文件是有限的、非负的且单调的。
- `h_profile` 在强制执行后是有限的、非负的且单调的。
- 在严格保持模式下，`h_profile >= s_profile * profile_hdr_min_gain` 在浮点容差范围内成立。
- `hdr_gain = h_profile / s_profile` 是有限且平滑的，除了在接近黑色处有 epsilon 保护的地方。
- 当配置文件肩部未压缩场景 EV 时，低色调和中间色调保持接近单位增益。
- `modern_recovery_peak_budget` 使用 `scene_ev - profile_ev` 作为压缩的 EV，仅缩放恢复增益，并且不通过显式约束更改严格/配置文件基线。
- 峰值预算和硬上限限制最终的配置文件相对 EV，而不引入局部非单调伪影。
- `headroom` 元数据源自实际的 HDR 内容/配置文件增益，而非直接从 `profile_hdr_target_peak_ev` 复制。
- 裁剪到 `safe_max_headroom` / `max_headroom` 不会静默地使普通样本的预期配置文件目标失效。
- 不安全的递减或非单调配置文件会被拒绝，而非静默地生成看似合理的 HDR 输出。

## 需要验证的物理和成像语义

- 采样曲线代表胶片加打印/冲印纸 SDR 输出行为，而非直接的 HDR 胶片物理特性。
- `profile_aware` 最恰当地描述为保留 SDR 打印/配置文件外观，同时使用场景附属数据能量进行授权的 HDR 高光恢复。
- 纸张/打印肩部和显示余量不被视为相同的物理量。
- SDR 基础输出精确保留用户当前的外观，而 HDR 目标是从附属数据和配置文件曲线构建的替代呈现。
- 动态运行时曲线采样不会错误地将临时用户外观编辑视为稳定的物理胶片/打印配置文件。
- 检查 `paper_rolloff_*`、`profile_aware` 和 `film_scan_aware` 等命名是否存在语义漂移。

## 代码路径问题

- `HDRPhotoMapping`
  - 验证所有 profile-aware 参数的有限范围、枚举值和模式兼容性。
  - 检查 `profile_hdr_peak_ev`、`profile_hdr_target_peak_ev`、`profile_hdr_recovery_ratio`、`profile_hdr_min_gain`、`profile_hdr_max_chroma_gain`、path-to-white 参数、`headroom_percentile` 和 `max_headroom` 之间的交互。
- `_prepare_profile_aware_renditions()`
  - 确认 `scene_luminance` 是必需的。
  - 确认 `s_profile`、`h_profile` 和 `hdr_gain` 在同一场景坐标上对齐。
  - 确认 `hdr_rgb = look * hdr_gain` 在可选颜色恢复之前保留 SDR 外观和预期亮度。
  - 确认内容余量和配置文件增益余量不会错误地膨胀或缩小有效载荷元数据。
  - 检查安全配置文件余量是否可能与映射级别的 `max_headroom` 冲突。
- `build_profile_preserving_hdr_curve()`
  - 确认模式分派、未知模式拒绝、最小增益语义、单调强制执行、软裁剪以及 `visual_peak = look_white * 2**peak_ev`。
- `modern_recovery_peak_budget`
  - 确认原始恢复增益、预算缩放、硬上限、百分位归一化、诊断以及约束后的单调行为。
- 颜色恢复和色域处理
  - 比较 `off`、`source_chroma` 和 `bounded_look_chroma`。
  - 检查 `scene_rgb` 和 `scene_luminance` 之间的发散回退。
  - 验证色度增益限制、path-to-white 和色域压缩顺序。
  - 验证亮度保持压缩在可能时保持目标亮度，并在目标亮度超过余量时有界地失败。

## 测试命令

首先运行以下专注的命令：

```bash
uv run --extra dev pytest tests/test_hdr_photo.py -q
uv run --extra dev pytest tests/test_hdr_curve_profiles.py -q
```

如果环境缺少依赖项或测试文件缺失，请将结果分别分类为环境/测试覆盖/实现。

## 最小实验

仅创建临时的、非生产性的验证脚本或内联 Python 代码片段，除非报告证明需要永久的回归测试。

- 中性渐变
  - 检查 `s_profile` 单调性。
  - 检查 `h_profile` 单调性。
  - 检查 `h_profile >= s_profile`。
  - 检查低/中间色调增益接近 1。
  - 检查高光增益平滑度和最大增益 EV 跳变。
- 用户外观缩放
  - 检查 SDR 基础等于输入外观。
  - 检查 HDR 目标按比例跟踪用户外观。
  - 检查当场景附属数据不变时，配置文件增益独立于用户曝光缩放。
- 热像素
  - 检查单个极端样本不会主导百分位余量。
  - 检查有效载荷裁剪不会破坏普通样本。
- 不安全配置文件
  - 检查递减/非单调配置文件是否被拒绝。
- 现代恢复峰值预算
  - 检查配置文件基线不被预算缩放。
  - 检查原始恢复增益被预算缩放。
  - 检查最终峰值遵守目标和硬上限。
  - 检查最终配置文件保持单调或产生显式解释。

## 已知风险列表

- 采样配置文件可能已经在 1.0 处被扫描仪/输出裁剪，在 HDR 恢复之前丢失高光形状。
- `profile_hdr_min_gain=1.0` 可能阻止合法的压缩 HDR 目标。
- 配置文件默认的 `safe_max_headroom` 可能与 `HDRPhotoMapping.max_headroom` 冲突。
- 如果实际 HDR RGB 在颜色/色域约束后较低，`headroom = max(content_headroom, profile_gain_headroom)` 可能高估元数据。
- `source_chroma` 可能放大极端场景 RGB 色度。
- Path-to-white 可能减少饱和高光并可能扰乱亮度。
- 当请求的亮度超过 `max_headroom` 时，亮度保持色域压缩可能定义不明确。
- 动态曲线配置文件可能将授权的外观调整与物理配置文件形状混为一谈。
- 如果调用方传递已预归一化的场景亮度，漫反射白色归一化可能会重复。
- 遗留的 paper-rolloff 命名可能仍然渗入 profile-aware 语义。
- 测试可能比实际配置文件数据库条目更彻底地覆盖合成配置文件。

## 验收标准

- 审计报告存在于 `docs/profile-aware-hdr-audit-report.md`。
- 报告包含执行摘要、证据、发现、建议的后续步骤和置信度循环。
- 每个发现被分类为关键、主要、次要或非问题，并注明文件/函数/影响/建议。
- 运行专注测试或记录未运行的具体原因。
- 最小实验覆盖上述不变量或明确记录无法运行实验的原因。
- 最终结论将实现 bug、命名/语义歧义、测试差距和环境限制分开。
- 现有生产行为保持不变，除非已证实的阻塞问题被单独修复并通过测试验证。
