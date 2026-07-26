# HDR 下的胶片模拟：全面审查与实施指南

日期：2026-07-26
范围：`src/spektrafilm/hdr/`、`runtime/route_master.py`、`utils/hdr_*.py`、`utils/gain_map*.py`、GUI HDR 导出面板，以及与胶片管线（filming → printing → scanning）的全部交界面。
方法：代码逐模块审查 + 行业最佳实践调研（ACES 2.0、ITU-R BT.2408、ISO 21496-1、Filmbox/Video Village、John Daro 胶片 HDR 重制工作流、Apple EDR/Adaptive HDR、游戏引擎 HDR）。

---

## 0. TL;DR

**我们的架构方向是对的，而且在照片类产品里属于第一梯队的设计。** RouteMaster 单次渲染 → SDR 印片 look 逐像素保留 → 高光延伸只从场景侧能量（`scene_y_raw` / `post_halation_y`）取材 → ISO 21496-1 gain map 承载显示自适应 —— 这正是业界"负片展开（unroll）"哲学（Filmbox Pro Highlight Unroll、John Daro 的负片 PQ 重制）在 Adaptive HDR 照片生态下的正确形态。`docs/internal/dev/2026-06-08-chemical-highlight-rolloff-hdr.md` 里那句"自然的 HDR 高光不能事后从 SDR look 里拉出来，能量必须来自 diffuse white 以上的场景值"，与行业结论完全一致。

**但对照最佳实践，有五个关键差距**（详见 §7 完整清单）：

1. **化学肩部 profile 是静态的**：用户调整 `density_curve_gamma`、print exposure、Chemistry（curve morph）、preflash 后，SDR 变了，但驱动 HDR 滚降形状的 `shoulder_severity` 等指标仍是出厂采样值。`hdr/profile_cache.py` 为此设计的动态重采样键从未接进生产。**这是"调整胶片模拟时 HDR 应如何响应"这个问题上唯一真正的缺口。**
2. **没有 EDR 实时预览**：HDR 只在导出 HEIC 时生成，调参全程只能看 SDR，验证靠导出后开 Preview.app。macOS 的 `NSScreen.maximumExtendedDynamicRangeColorComponentValue` + Metal EDR 层是现成的解法（`docs/hdr/research-gui-color-hdr.md` 已调研、未实现）。
3. **path-to-white 强度不随 headroom 缩放**：paper 模式固定 0.12。感知上亮度越高色彩显得越浓（Hunt 效应），所以去饱和必须随峰值亮度增强——ACES 2.0 的色度压缩参数从 100 nit 的 2.4 升到 1000 nit 的 ≈10.3（4 倍多）。我们在 headroom 2× 和 8× 下用同一强度，高 headroom 显示器上延伸高光会偏"霓虹"。
4. **参考白自适应是空壳**：`reference_white.resolve_reference_white` 开头就 `del master`，只支持 `manual_scene_anchor`。图像自适应 diffuse-white 检测（BT.2408 语义下的"参考白"）有数据结构、无实现。
5. **PQ/HLG 是死代码 + GUI 枚举陷阱**：`hdr/transfer.py` 的 PQ/HLG 没有任何编码出口（只产 gain-map linear pair）；GUI `HDRHeadroomModes` 列出的 `modern_recovery_peak_budget` 会在导出时直接抛异常（`hdr_settings.py:27-28` 只接受 `content_percentile`）。

---

## 0.5 落地状态（2026-07-26 同日实施）

阶段 1 与阶段 2 已全部落地并通过测试（新增 `tests/test_hdr_projection_improvements.py` 13 例 + 既有 HDR/RouteMaster/GUI 相关套件约 450 例全绿）：

| 项 | 状态 | 实现位置 |
|---|---|---|
| P0-(a) 动态肩部 profile 接线 | ✅ 已实现 | `hdr/profile_cache.py:get_dynamic_print_curve_profile`（按 tone 参数键缓存）→ `routemaster_export.export_hdr_heic_from_simulator` → `project_hdr_ideal_paper(chemical_profile=…)`；采样器 `utils/hdr_curve_profiles.py:sample_runtime_print_curve_profile`（CPU 确定性、实测 ~0.3s）；diagnostics 新增 `chemical_profile_origin` |
| P0-(c) GUI 枚举陷阱 | ✅ 已修复 | `options.py` 移除 `modern_recovery_peak_budget`；`hdr_settings.py` 归一化旧存档值；导出侧 fail-closed 校验保留 |
| P0-(d) path-to-white 随 headroom 缩放 | ✅ 已实现 | `projection.py:_effective_path_to_white_strength`（β=0.5/档，参考 headroom 4.0），NumPy 与 MLX 双路；diagnostics 输出 input/effective |
| P1-(b) 软肩化 | ✅ 已实现 | `ideal_paper.py:_soft_clip_gain`（二次膝、非渐近达峰）与 `_smooth_max`（交点精确、处处 C1、不低于 min）；`_apply_highlight_detail` 的 `min(…, sdr·H)` 硬帽保留（gain map 值域保证），列为后续观察项 |
| P1-(c) span 解耦 | ✅ 已实现 | `_extension_gain`（双路）与 `_chemical_print_hdr_y` 的 span_end 固定为 `max_headroom`；内容百分位仅决定最终 headroom 元数据；裁剪稳定性有测试；顺带省掉一次全图排序 |
| P1-(d) 分类收紧 | ✅ 已实现 | `_classify_polarity` 增加幅度预算（违例合计 ≤ 0.1% 曲线跨度），大单点反转不再判 safe |
| P1-(f) sidecar 移点 | ✅ 已实现 | `runtime/stages/filming.py:_expose_core`：`scene_y_raw` 在 highlight boost 之后采集；SDR 路径不受影响（等价契约测试通过） |

行为语义变化（有意为之，已同步 `docs/hdr-modes.md` 与 `docs/hdr-export-pipeline.md`）：
1. 低动态场景的高光延伸比旧实现保守（span 不再向内容峰值自适应收窄）——换来构图无关的确定性渲染；
2. headroom 8× 时高光去饱和强度从 0.12 提升到 ~0.18，2× 时降到 ~0.06；
3. paper 模式对 `boost_ev` 现在有 HDR 响应（重建能量进入场景权威）。

阶段 3（EDR 实时预览、HDR 范围可视化、元数据注入）与阶段 4（PQ 交付、P3 limiting、遗留栈清理）未在本次实施，见 §8。

## 1. 物理背景：为什么"胶片模拟 × HDR"天然成立

这一节是全文的理论根基，后面所有结论都从这里推出。

**负片是 HDR 捕获介质，相纸是 SDR 显示介质。**

- 彩色负片的宽容度可达 **12 档以上**（部分乳剂 12~18 档），远超相纸能再现的范围。
- Kodak Cineon 体系把负片扫描编码在 10-bit log 上：95 = Dmin 黑，**685 = 90% 白卡**，每档 90 码值 → 95–685 只覆盖约 **6.5 档**"正常"区间；685 以上全是负片肩部保留的高光信息，常规输出时被软剪切。
- 印片胶片（如 2383）最陡处 gamma ≈ 5，相纸的曝光动态范围只有约 89:1（负片约 708:1）。被 685 剪切的高光印到 2383 上不是白色，而是约 80% 亮度的粉灰色——这就是"胶片高光滚降"的物理来源：**滚降主要发生在负片肩部 + 相纸 Dmin 趾部的串联**，而不是某条抽象的 tone curve。
- 因此 HDR 显示对胶片模拟的意义非常明确：**显示器的 headroom 用来展示负片捕获了、但相纸展示不了的那 4~6 档高光**，同时中低调保持印片的颜色个性。这不是"给胶片 look 加亮度"，而是"把印片强加的高光压缩部分地退回去"。

我们的管线结构与这个物理模型精确同构（`runtime/topology.py`、`stages/filming.py` → `stages/printing.py` → `stages/scanning.py`）：

```
输入(线性场景光) → FILMING(光谱上采样→曝光→D-logE→DIR→颗粒) = 负片
              ├─ sidecar: scene_y_raw（曝光后、halation 前的场景能量）
              ├─ sidecar: post_halation_y（halation 后的空间能量）
              → PRINTING(放大机光源/滤镜→相纸曲线) → SCANNING(密度→光谱→XYZ→RGB)
              → route_linear_rgb（纸面反射率，纸白 Y≈0.8–0.95，Dmax 压黑）
              → 输出色域压缩 → CCTF → [0,1] = sdr_legacy_rgb（SDR look）
```

SDR 输出的白就是纸基白（Dmin），黑就是 Dmax——这是一个**天然的 display-referred SDR 渲染**。负片阶段丢弃的信息由两个 sidecar 保存，供 HDR 投影使用。这个"能量从场景侧取、look 从印片侧取"的分离，正是行业结论的教科书式实现。

---

## 2. 行业最佳实践：HDR 下的胶片模拟到底该怎么做

### 2.1 两种正统哲学（以及我们选的第三条路）

**哲学 A：忠实印片（print-faithful）。** 把整张印片当作一个物理对象"投影"进 HDR 容器。Filmbox 的默认行为：选 ST2084 输出时，接触印片直接映射到 PQ 的约 **200 nits 纸白**——官方类比是"用更亮的灯泡投影这张印片"，默认效果等同于在 200 nits 亮度下看 SDR。优点：绝对忠实、零 hue/对比破坏；缺点：几乎不使用 HDR headroom，被 HDR 用户批评（这正是 Filmbox 挨批后加 Unroll 的原因）。

**哲学 B：展开负片（unroll the negative）。** 保持印片 look 的颜色与中低调，把印片特性曲线的肩部"展开"，让负片保留的高光 latitude 进入 headroom：

- Filmbox Pro（2025-08）的 **Highlight Unroll** 滑杆：让额外动态范围穿过 print transform，高光最高到 1000 nits；官方明说这"**不对应任何照相化学过程**，是为了在保持胶片感的同时获得更动态的图像"。初版 unroll 上限约 400 nits。
- John Daro（好莱坞资深调色师）的胶片 HDR 重制流程："让胶片落在它被拍摄时的位置，但为 PQ 显示做 tone-map"——以导演认可的答案拷贝（14 fL 放映）为基准锁定匹配，再向上展开；**必须做高光再平衡**，因为"过去在印片上是白色/剪切的东西现在可见了"；强高光会改变画面对比结构（观众瞳孔收缩），要"滚降高光或抬起阴影让对比比例与原始一致"；常用 **LMT 把色域限制在原拍摄乳剂的色域内**。
- 数据点：负片重制的高光通常到几百~1000 nits，个别特效元素（Speed Racer 的闪电）到 4000 nits——但那是极端案例，不是常态。

**我们的选择（paper 模式）实质上是哲学 B 的逐像素精确化，而且比 Filmbox 更"化学"**：`hdr/ideal_paper.py` 在 `scene_y ≤ diffuse_white_anchor` 处逐像素保留 SDR（`hdr_y = where(scene_y <= white, sdr_y, extension)`，`ideal_paper.py:259`），以上才按**实测的化学肩部指标**（`shoulder_severity`、`highlight_slope/midtone_slope`，从 160 个 胶片×相纸 组合的全管线采样得来）决定展开多少。Filmbox 的 unroll 是一个全局滑杆；我们的是按乳剂组合标定的。这个设计点值得自豪，也值得在文档/营销中明确表述。

`light_table` 模式则对应另一种真实观察方式（负片放在光台上直接看/扫描），能量权威是 `post_halation_y`，完全绕过相纸——两种模式覆盖了"胶片的两种物理观看方式"，语义划分干净（`docs/hdr-modes.md` 有逐参数的响应矩阵）。

### 2.2 SDR/HDR 一致性：grade once, output many

- Frostbite 的经典结论：**HDR 是基准版本，SDR 从同一渲染派生**，一套 grade 输出所有目标；分级在 display mapping 之前的稳定空间做。
- ACES 2.0 的核心设计目标之一就是 SDR 与 HDR 输出的外观匹配（100-nit 709 母版与 1000-nit PQ 母版的创意差异比 1.x 小得多）。
- 照片生态的对应物就是 gain map：**一个文件、两个 rendition、显示端按当前 headroom 插值**。创作者同时掌控 SDR 与 HDR 两端，而不是把 SDR 交给浏览器的自动 tone map。

我们的 RouteMaster 合同（`process(image) == process_master(image).sdr_legacy_rgb` 硬等价，`tests/test_routemaster.py`）+ 同一次渲染派生 SDR/HDR pair，是这个原则的严格实现。✅

### 2.3 亮度锚点：参考白放哪里

| 锚点 | 数值 | 来源 |
|---|---|---|
| HDR 参考白（diffuse/graphics white） | **203 nits**（PQ 信号 58%，HLG 75%） | ITU-R BT.2408 |
| 实际影视内容的 diffuse white | 常见 80–100 nits（比 2408 保守） | 业界实测讨论 |
| ACES 2.0 中灰（0.18）输出 | 100nit 峰值→10 nits；1000→14.5；4000→16.8（**随峰值缓升**，不锁死） | ACES 2.0 tonescale |
| SDR→HDR 直通缩放 | ×2.0（100→203），注意别让 SDR 白亮过 HDR 内容 | BT.2408 |
| 影院 | SDR 影院 48 nits；Dolby Vision 影院 108 nits | ACES/Dolby |
| Apple EDR | **1.0 = SDR 参考白（跟随用户亮度设置），headroom 动态** | Apple WWDC21 |
| 实际设备 headroom | iPhone ≈3 档，XDR 屏 ≈4 档 | Greg Benz 实测 |

要点：**在 gain map / EDR 生态里没有绝对 nits**——一切相对于 SDR 白。所以"纸白锚在多少 nits"这个问题在我们的 HEIC 输出里的正确答案是：**纸白 = SDR rendition 的白 = EDR 1.0**，HDR rendition 只在其上按 headroom 延伸。我们默认 `output_diffuse_white=1.0`、`preserve_sdr_base=True`，正确 ✅。`display_reference_white_nits=203` 只是诊断字段（GUI tooltip 也如此声明），但注意 §7-P2 里提到的三处 nits 语义不一致。

### 2.4 平均亮度纪律（APL discipline）

PQ 的设计意图是**扩大亮度范围而不是抬高平均亮度**：HDR 内容的 APL 应与 SDR 相当，100 nits 以上只留给高光细节。硬件上还有 OLED 的 ABL：大面积高亮会触发全屏限亮。Android Ultra HDR 规范同样要求 SDR 化时不得剪切高光/压碎阴影/破坏局部对比。Adobe gain map 规范明确建议：如果只有少量极亮像素（如 +6EV 的镜面高光），宁可把 HDR capacity 标为 +3 而不是 +6，避免整体被压暗。

我们的 `preserve_sdr_base=True` + 只延伸 diffuse white 以上 + `headroom_percentile=99.9` 内容自适应封顶，完全符合这套纪律 ✅。

---

## 3. 我们的现状：架构审查摘要

（完整细节在 `docs/hdr-routemaster-rewrite.md` 系列；此处只列与差距分析相关的骨架。）

**信号流**：`process_with_master()` 跑一次完整路由 → `RouteMaster{route_linear_rgb, route_luminance_y, sdr_legacy_rgb, scene_y_raw, post_halation_y, ...}` → `hdr/ideal_paper.py`（paper）或 `hdr/light_table.py`（light_table）→ `hdr/projection.py:_build_result`（chroma 从 route look × hdr_y、path-to-white、output diffuse white、高光色域压缩、percentile headroom 封顶、log2 gain map）→ `utils/hdr_photo.py:save_hdr_photo_heic_from_pair`（仅编码，拒绝再算）→ `data/macos/hdr_heif_encoder.swift`（CoreImage，extended linear 空间，SDR `.settingContentHeadroom(1.0)` + HDR `.settingContentHeadroom(headroom)`，输出 gain-map HEIC）→ `heif_iso21496.py` 结构验证 + CoreImage `tmap` min/max 修复，失败即删文件报错。

**化学滚降核心公式**（`ideal_paper.py:91-152`）：

```
ratio            = scene_y / diffuse_white_anchor
chemical_progress = clip((profile_y(ratio) − profile_y(1)) / (shoulder_limit_y − profile_y(1)), 0, 1)
span_end         = max(1.25, min(max_headroom, percentile(ratio, 99.9)))
scene_excess     = clip((ratio − 1) / (span_end − 1), 0, 1)
progress         = smoothstep(1, span_end, ratio)
softness         = 1.8 + (0.7 − 1.8) · clip(highlight_slope/midtone_slope, 0, 1)
compressed_excess = scene_excess / (1 + chemical_progress · severity · softness · 2 · scene_excess)
gain             = clip(1 + progress · compressed_excess · (max_headroom − 1) · strength, 1, max_headroom)
hdr_y            = max(强度调制后的 sdr_y·gain, sdr_y + progress·compressed_excess·(max_headroom − sdr_y)·strength)
```

其中 `strength = paper_extension_strength(0.55) · (1 − 0.35·severity) · tint_guard`。肩部越"死"（severity→1）的组合展开越保守——**化学证据驱动展开量**，这是全行业没人做到的粒度。

**gain map**（`utils/gain_map.py` 按 ISO 21496-1:2025 A.1/A.2/(2)/(3) 逐条实现；`hdr_photo.py:1709` 导出编码 `gain = clip(log2(hdr/max(sdr,1e-3))/log2(headroom), 0, 1)`；元数据 `gain_map_min=0, gain_map_max=log2(headroom), offset=1/1023, hdr_capacity_max=headroom`）。JPEG（MPF+APP2）与 HEIF 双容器、Adobe XMP 兼容层、ISOBMFF `tmap` 逐 box 验证齐全。

**GUI 响应**：所有 HDR 设置只在导出时消费（不进 `RuntimePhotoParams`）；开启 gain map 后全分辨率 Scan 会缓存 RouteMaster，键为 SHA-256(输入指纹 + 全部 GUI 状态 + hdr_mode + 保存色彩空间)（`controller.py:244-262`）——**任何参数变化都会使缓存失效并在导出时全量重渲染**。

**测试**：行为规格级覆盖（两模式的参数响应矩阵、SDR 等价、锚点移动、化学 fallback、单调性/连续性、分块精确性、gain map 高频清洁度、SDR/HDR 共享同一颗粒实现、MLX 驻留、编码器 fail-closed）。这套测试面在同类项目中罕见地完整 ✅。

---

## 4. 高光如何在 HDR 下柔和地滚降

### 4.1 曲线设计的行业要求

ACES 2.0 tonescale（Michaelis-Menten 族，作用在 JMh 的 J 上）的设计要求就是一份权威 checklist：

1. **S 形**（趾 + 肩）；
2. **单调**；
3. **非渐近**——曲线要真实到达峰值，而不是无限逼近（否则高光永远差一点、gain map 封顶时出现死区）；
4. **处处连续**、全浮点域有定义；
5. 中灰 log-log 斜率（对比度）< 1.55；
6. **中灰输出随峰值亮度缓升**（10→14.5→16.8 nits @ 100/1000/4000）——HDR 不是把中灰锁死在 SDR 位置，是整体轻微展开。

显示端二次映射用 BT.2390 EETF（BT.2408-4 参数化：Lb/Lw/Lmin/Lmax），MovieLabs 的实测结论：**MaxCLL ≤ 目标峰值时不要 tone map**（直通），且五种 EETF 里为保色相最终推荐 maxRGB 法。

### 4.2 我们的滚降公式分析（结论：形态正确，有四个可改进点）

对照上面六条：

- **连接处连续性 ✅（C0/C1）**：`ratio→1⁺` 时 `scene_excess→0` 且 `smoothstep` 在端点导数为 0，所以从 SDR 段进入延伸段既无跳变也无斜率折点。测试里已有单调性 + 连续性守卫。
- **单调 ✅**：`x/(1+kx)` 对 x 单调；`progress`、`gain` 均单调不减。分类器把非单调 profile 标 unsafe → generic fallback。
- **非渐近 ⚠️ 半满足**：`x/(1+kx)` 本身渐近于 `1/k`，靠 `clip(gain, 1, max_headroom)` 收尾。当 `chemical_progress·severity·softness·2 > 1` 时曲线在 `scene_excess=1` 处远低于 1 → 实际峰值到不了 `max_headroom`（这是"化学保守"的本意，可接受），但当参数组合让 gain 顶到 clip 时会产生硬折点。建议：把 clip 换成到 `max_headroom` 的软肩（如再套一层 Michaelis-Menten 或 `tanh` 逼近段），保证到达峰值且 C1。
- **`max(existing_chemical_y, display_extension_y)` 的折点 ⚠️**（`ideal_paper.py:152`）：两条曲线交叉处 max() 产生 C1 不连续。平滑替代：`softmax_τ(a,b) = τ·log(exp(a/τ)+exp(b/τ))` 或 smooth-max 混合。梯度渐变天空上这类折点是 banding 的常见来源（gain map 8-bit 量化会放大它）。
- **`span_end` 依赖 99.9 百分位 ⚠️**：滚降的"到达点"由构图统计决定。裁剪掉一个高光、或连拍中高光面积变化，整条肩部形状随之改变——单张没问题，批量/序列不稳定（§7-P1-c）。
- **中灰缓升未做（设计选择，建议维持但记录）**：我们严格 `preserve_sdr_base`，中灰与 SDR 完全一致。这比 ACES 的缓升更保守，对"印片 look 忠实"是对的；但应在文档里明示"我们有意不做 ACES 式中灰上移"，避免未来误改。

### 4.3 显示端的第二次滚降：交给 gain map，不要自作聪明

ISO 21496-1 的显示端行为：目标 headroom H 与元数据 Mlo/Mhi 比较，`W = clamp((H−M_base)/(M_alt−M_base),0,1)`，`display = (base+k)·2^(W·G)−k`——**显示器 headroom 不足时的"滚降"就是这个插值**，Apple 再叠加其 tmap 优化曲线。我们正确地只产出两个诚实的 rendition + 元数据，把自适应留给平台 ✅。**不要**在导出侧为"低端显示器"预烤第二层 EETF——那会双重滚降。

需要补的是另一条线：当未来输出 **PQ/HLG 视频帧或 LUT**（`spektrafilm_lut_creator` 已有 Rec.2100 PQ/HLG 色彩空间注册但无 verified delivery target）时，才需要实现 BT.2390 EETF + MaxCLL 语义，见 §7-P1-e。

### 4.4 直接回答"高光如何柔和滚降"

1. 滚降的**形状**来自化学证据（我们已做，且是差异化优势）；
2. 滚降的**终点**必须真实到达 `min(内容峰值, max_headroom)`，全程 C1（补软肩、去 max() 折点）；
3. 滚降的**起点**是 diffuse white 锚，锚以下逐像素不动（已做）；
4. 显示端的再滚降交给 gain map 插值（已做）；
5. 滚降参数必须**跟随用户当前的胶片参数**重新采样，而不是出厂静态值（未做——§6 核心差距）。

---

## 5. 高光处的色彩该怎么处理

### 5.1 物理参照：胶片高光的颜色行为

- 相纸/印片高光趋向**纸白**：三层染料在 Dmin 附近都接近透明，高光必然去饱和——胶片从不产生"霓虹高光"。
- 同时胶片存在**真实的 hue skew**：每层独立的特性曲线（本质是"逐通道 tone mapping"）会把亮饱和色推向 R/G/B/C/M/Y 六个方向（即 "notorious six"）。Bram Stout 的分析指出**胶片本身就有这种偏移**，它抬高了亮部的感知亮度，是"胶片感"的一部分，不是缺陷。
- 被剪切的高光在 2383 上呈粉灰（非纯白）——印片高光有自己的**染色（tint）**，这正是我们 `highlight_tint_spread` 指标捕捉的东西。

### 5.2 分工原则（这是本节的核心结论）

**锚点以下：让胶片模拟的逐通道物理发生，保留全部 skew/tint——那是 look 本身。
锚点以上的延伸段：保色相 + 随亮度增强的去饱和（path-to-white），不引入任何新的 skew。**

理由：延伸段是"反事实的数字介质"（我们的 diagnostics 里自己就这么写：`paper_medium: counterfactual_digital`），没有对应的化学参照；此时引入逐通道行为只会产生与印片 look 无关的新偏色。ACES 2.0 的整个架构（tonescale 只动 J、色度压缩只动 M、h 恒定）就是这个原则的系统化。我们 `_build_result` 用 route look chroma × hdr_y + path-to-white + luma-preserving 色域压缩，方向正确 ✅。

### 5.3 Hunt 效应：去饱和强度必须随 headroom 缩放（当前缺失，P0）

同一色度在更高亮度下**感知上更浓**（Hunt 效应）。所以延伸得越高，需要的去饱和越强，否则高光在高 headroom 显示器上发"荧光感"。ACES 2.0 的数据点：色度压缩强度参数 `compression = 2.4 + 2.4·3.3·log10(L_peak/100)` —— 100 nit 时 2.4，1000 nit 时 ≈10.3；同时暗部反向的饱和恢复从 1.3 降到 ≈0.4。

我们的现状：`paper_path_to_white_strength = 0.12` 常数（light_table 为 0），对 headroom 2× 和 8× 一视同仁。建议（保持我们的 EV 相对参数化）：

```
strength_eff = strength_base · (1 + β · log2(headroom))     # β ≈ 0.5~1.0，实验标定
```

并让 path-to-white 的 EV 窗口终点跟随 `log2(headroom)`（旧管线的 1.25→2.25EV 窗口在 headroom=8（3 档）时应延伸到 ~3EV，否则最亮一档失去去饱和梯度）。`light_table` 的 0 也值得复查：底片在光台上看，高光染料同样趋向透明白，物理上并非"无 path-to-white"。

### 5.4 色相路径：hue-linear 空间与 Abney 补偿

去饱和的路径必须在**感知 hue-linear** 空间上走直线，否则"变白的过程中变色"（Abney 效应：恒定 XYZ 色度下加白，感知色相会漂移；蓝色尤其明显）。现代实践（AgX 系、Khronos PBR Neutral、AgMax）在 path-to-white 上显式做 hue 校正。我们已有 Oklch 压缩 + JzAzBz 逐像素 fallback（`_needs_jzazbz_fallback`）——工具齐了，但 path-to-white 本身在什么空间走、是否补偿 Abney，值得写一个针对蓝色 LED/霓虹高光的金样测试确认。`tint_guard` 目前只是"强染色肩部就把延伸和去饱和减半"的标量保护，更好的做法是**沿印片染色方向去饱和**（终点不是中性白而是纸白色调），让延伸段与印片高光的粉灰基调连续。

### 5.5 色域纪律

- 乳剂光谱敏感度 + 染料光谱本身构成天然的"乳剂色域 LMT"（Daro 在 HDR 重制里手动加的东西我们免费拥有）✅。
- 输出侧已有 chroma knee + lightness rolloff 的色域压缩（SDR）和 luma-preserving/Oklch 压缩（HDR）✅。
- 缺口：swift 编码器支持 Rec.2020 容器，但没有 **P3 limiting**（行业惯例：2020 容器内限制在 P3-D65 体积，见 Daro 的交付清单与 ACES white limiting）。若用户选 2020 输出，延伸高光可能落在没有任何消费级显示器能显示的色度上。
- gain map 模式：`rgb`（逐通道）忠实传输我们已保色相的 HDR rendition；`luma` 强制三通道同比例（更保守，忽略通道差异）。默认 `rgb` 与保色相 HDR 配套，一致 ✅。注意 `rgb` 模式下 SDR 与 HDR 的任何色度差都会烙进 gain map——如果未来在 HDR rendition 上做独立的色彩处理（如 5.3 的强化去饱和），要复查 8-bit gain map 量化是否在平滑天空上产生色度 banding（已有 gain map 高频清洁度测试可扩展）。

### 5.6 直接回答"高光处的色彩该怎么处理"

1. 锚下：逐通道化学，全保留；
2. 锚上：色相锁定（hue-linear 空间）、朝**纸白色调**（非纯中性白）去饱和；
3. 去饱和强度和窗口随 `log2(headroom)` 缩放（Hunt）；
4. 强染色肩部沿染色方向收敛而不是简单减半；
5. 蓝色/窄带光源单独金样验证（Abney + notorious six 的高发区）；
6. 2020 容器加 P3 limiting。

---

## 6. 调整胶片模拟参数时，HDR 系统应该如何响应

### 6.1 原则

**单一真源（single source of truth）**：SDR 与 HDR 必须永远从同一份参数状态、同一次渲染派生。gain map 是派生物，不是独立的创意层。行业里所有反面教材（LUT 在推曝光后崩坏、SDR/HDR 分开 grade 后漂移）都源于违反这条。

我们已满足的部分 ✅：
- 任何 GUI 参数变化 → RouteMaster 缓存 SHA 签名失效 → 导出时全管线重渲染（`controller.py:500-607`）。响应机制是**彻底重算**，永不修补旧结果——正确且稳健。
- 颗粒在 SDR/HDR 间共享同一次实现（测试 `test_hdr_routemaster_projection.py:586`）——两个 rendition 的噪声场逐像素一致，gain map 不会把颗粒差编码成噪声（这是很多人会犯的错）。
- 两种模式的参数响应/不响应边界有文档和测试（light_table 无视全部相纸参数；paper 响应 print exposure、相纸曲线、EV、胶片选择、放大机滤镜、gamma、morph）。

### 6.2 应该成立的响应语义（参数 × HDR 行为矩阵）

| 用户调整 | SDR 变化 | HDR 应有的响应 | 现状 |
|---|---|---|---|
| 曝光补偿 / auto-exposure EV | 整体密度 | 锚点在场景域平移 → 高光展开的起始点跟着走；EV 已进 scene_y_raw 的尺度 | ✅（测试覆盖"reference-white EV 移动 onset 且不改 SDR"） |
| 换胶片 / 换相纸 | look 全变 | 换用该组合的化学肩部指标（severity、slopes、tint） | ✅ 静态 profile 按 (film, paper) 查表 |
| `density_curve_gamma`（负片 gamma） | 对比变化 | **肩部指标应重采样**——gamma 直接改变 midtone_slope/highlight_slope 比 | ❌ 用出厂值 |
| print exposure / 放大机 CMY 滤镜 | 密度/色平衡 | 同上：纸白落点、shoulder_limit_y 都会移动 | ❌ 用出厂值 |
| Chemistry（`developer_exhaustion` 等 curve morph） | **专门用来改肩部软硬** | 这是最讽刺的一条：用户显式调"高光滚降柔软度"，HDR 的滚降参数却纹丝不动 | ❌ 用出厂值 |
| preflash | 高光压缩 | 同上 | ❌ 用出厂值 |
| halation `boost_ev/boost_range` | 高光 glow 能量 | 影响 post_halation_y（light_table 权威）✅；paper 模式权威是 halation **前**的 scene_y_raw（glow 不驱动延伸——设计权衡，见 §7-P1-g） | ⚠️ 语义需记录 |
| 颗粒参数 | 噪声结构 | SDR/HDR 共享 | ✅ |
| 裁剪/构图 | 内容统计 | headroom 与 span_end 随 99.9 百分位漂移 | ⚠️ 稳定性问题（§7-P1-c） |
| HDR 面板参数（锚点、headroom、strength…） | 无 | 只影响投影，不触碰胶片管线 | ✅ 边界干净 |

### 6.3 核心差距：把 `profile_cache.py` 接进生产（P0）

`RouteProfileCacheKey` 已经设计好（键包含 density_curve_gamma、print exposure、morph、滤镜、preflash——正是上表所有 ❌ 项），`docs/hdr-export-pipeline.md` 的 Dynamic Profile Cache 一节写了方案，测试 `test_hdr_profile_cache.py` 也在——**只差接线**。实施要点：

1. 导出（及未来 HDR 预览）时，若 tone 相关参数偏离出厂默认，用当前参数在 34 个 scene_y 采样点上以 `debug.lut_mode`（确定性、无空间/随机效应）重跑中性斜坡 → 重算 `shoulder_severity` 等指标（工具链 `tools/export_hdr_curve_profiles.py` 的逻辑抽成库函数即可）；
2. 以 `RouteProfileCacheKey` 缓存，参数不变不重采样；34×3 像素的管线成本是毫秒级；
3. 重采样结果同样过 safe/unsafe 分类（此时"用户把曲线调成非单调"会正确地落到 generic fallback）；
4. 保留静态 profile 作为默认参数下的快路径与回退。

### 6.4 第二差距：实时反馈（P0）

现状是"盲调"：HDR 效果只有导出 HEIC 后在 Preview.app 里才能看到。应做的（`docs/hdr/research-gui-color-hdr.md` 已调研）：

1. **EDR 预览层**：napari/Qt 之上加 Metal EDR surface（`CAMetalLayer.wantsExtendedDynamicRangeContent`，extended linear 空间直接喂 HDR rendition 的线性值）；
2. 查询 `NSScreen.maximumExtendedDynamicRangeColorComponentValue`（+ `didChangeScreenParametersNotification` 监听），按当前 headroom 应用 ISO 21496 的 W 插值——**预览的数学 = 消费端的数学**，所见即所得；
3. 预览分辨率下（≤4MP、颗粒已关）HDR 投影是纯 per-pixel NumPy/MLX 运算，成本远低于胶片管线本身，可挂在现有 preview 流水线末端；
4. 配套 UI：headroom 读数、HDR 区域可视化（学 Lightroom：按 f-stop 分色显示超出 SDR 的区域、黄/红标示超出当前显示器能力的像素）、SDR/HDR 一键 A/B。
5. 过渡期最低成本方案：导出后自动用 Preview.app 打开 + 在状态栏显示 gain map 统计（headroom、>1 像素占比）。

---

## 7. 完整遗漏清单（按优先级）

### P0 — 正确性/核心体验

- **(a) 动态肩部 profile 未接线**：tone 参数改变后 HDR 滚降形状与实际化学状态脱节。`hdr/profile_cache.py` 生产端零引用。→ §6.3。
- **(b) 无 EDR 实时预览**：HDR 调参盲飞。→ §6.4。
- **(c) GUI 枚举陷阱**：`HDRHeadroomModes` 含 `modern_recovery_peak_budget`（`options.py:47-49`），`hdr_projection_config_from_settings` 只接受 `content_percentile`（`hdr_settings.py:27-28`）——用户选中即导出报错。移除该选项或实现该模式。
- **(d) path-to-white 不随 headroom 缩放**（Hunt 效应）：固定 0.12/0.0。→ §5.3 公式。

### P1 — 显著质量/能力缺口

- **(a) 参考白自适应是空壳**：`reference_white.py:28` `del master`；只有手动锚。应实现图像自适应候选（如场景亮度直方图的 diffuse-white 检测，参考 BT.2408 的 58%/75% 语义与 highlight_weighted 测光的既有代码），作为"Auto"模式供选，保留手动覆盖。
- **(b) 滚降曲线的两处 C1 折点**：`clip(gain, 1, max_headroom)` 顶部硬剪 + `max(chemical, display_extension)` 交叉折点（`ideal_paper.py:152`）。→ §4.2 软肩/smooth-max。
- **(c) headroom/span_end 的统计不稳定**：99.9 百分位随裁剪/构图跳变；批量处理同一场景的多张会得到不同肩部。缓解：百分位在**对数域**上做、加 hysteresis 或按会话锁定（"锁定 headroom"开关）、把 `span_end` 与 `content headroom` 解耦（span_end 用 max_headroom，内容统计只决定元数据）。
- **(d) 单调性分类容忍度**：`_classify_polarity` 允许 ~2% 局部违例仍标 safe（`hdr_curve_profiles.py:111-121`；audit 报告遗留项）。收紧或在违例区间做局部单调化（PAVA）后再用。
- **(e) PQ/HLG 交付链路缺失**：`hdr/transfer.py` 无出口；LUT creator 注册了 Rec.2100 PQ/HLG 空间但 `delivery_targets.py` 只验证了 `lumix_realtime_vlog`。若目标包含视频/外部 grading 生态（Resolve 用户），需要：PQ 输出变换（含 BT.2390 EETF、203 nits 参考白约定、MaxCLL/MaxFALL 元数据）+ 至少一个 verified HDR delivery target。若不做，删掉死代码并在文档声明"HDR 输出 = gain-map HEIC only"。
- **(f) 输入已剪切时延伸平顶**：`scene_y_raw` 取自 highlight boost **之前**（流程图 sidecar 顺序），输入本身剪切时 ratio 平顶 → 延伸段整片同值（banding 高危）。而 boost（`boost_ev`）恰恰是为重建 pre-clip 能量设计的。建议：sidecar 改取 boost 之后（halation 之前），或提供开关并记录语义。
- **(g) paper 模式下 halation glow 不进 HDR**：权威是 halation 前的 `scene_y_raw`，强 halation 时 SDR 的 glow 与 HDR 延伸的空间分布可能出现可见边界。这是合理的设计权衡（glow 已烙进 look），但需要：金样对照（强 halation + 高光场景）+ 文档明示；若出现 halo 断裂，考虑 `max(scene_y_raw, α·post_halation_y)` 的混合权威。
- **(h) 高光颗粒在 HDR 下的放大**：延伸段 gain 最高 8×，颗粒调制的绝对振幅同步放大，PQ 显示上高光颗粒可能"闪"（Daro 在 HDR 重制中专门做高光降噪再混回）。已有 material_detail(0.75–1.25) 调制，建议加"高光颗粒阻尼"选项并做 1000-nit 显示器目检。
- **(i) Rec.2020 容器无 P3 limiting**。→ §5.5。
- **(j) HEIC 无法携带拍摄元数据**：`save_hdr_photo_heic_from_pair` 拒绝 metadata（`hdr_photo.py:531-535`），EXIF/来源信息只在 `.hdr.json` sidecar，GUI 状态栏自认"不支持"。消费生态（Photos 按日期/镜头整理）受损。可行方案：编码后用 CGImageDestination/exiftool 二次注入并重跑 ISO 验证。

### P2 — 卫生/一致性/生态

- **(a) 遗留三模式栈**：`hdr_photo.py` 里 ~1200 行 `generic`/`profile_aware`/`film_scan_aware` 映射已被 RouteMaster 取代仍在船上（含冗余包装 `_prepare_profile_aware_renditions`）。计划性删除或明确标记 deprecated。
- **(b) nits 语义三处不一致**：ISO 元数据默认 `sdr_white_luminance=100`（`hdr_photo.py:1667-1706`），投影配置/GUI 诊断 203，BT.2408 参考白 203 但 Apple EDR 实际是"用户亮度即 SDR 白"。统一为一个来源并在文档写清"仅诊断，不影响像素"。
- **(c) 样本 JSON 缺 route/profile_kind 字段**（读取时默认 `print_scan`）：单文件脱离 summary 后丢失路由信息。补字段 + 校验。
- **(d) 代码卫生**：拼写错误兼容模块 `numba_boost_hightlights.py`；`stages/scanning.py:163-164` 注释重复行；audit 报告中已修复项（`max_headroom` min 化，`hdr_photo.py:961`）与未修项混排，建议在报告顶部加状态表。
- **(e) 生态提示**：浏览器（尤其 iOS WebKit）对 HDR 静态图支持仍不均；分享路径文档应提示"HEIC gain map 在 Apple 相册/信息生态内最可靠，Web 需转 Ultra HDR JPEG"（我们已有 JPEG MPF 写出器，可作为导出选项露出）。
- **(f) macOS Tahoe EDR 已知 bug**：外接三方 HDR 显示器睡眠唤醒后 `maximumExtendedDynamicRangeColorComponentValue` 卡在 1.0——实现 EDR 预览时需要容错（fallback 到 `maximumPotentialExtendedDynamicRangeColorComponentValue` + 手动覆盖）。

---

## 8. 落地路线图

**阶段 1（正确性，1–2 周量级）**
P0-(c) 枚举修复（一行级）；P1-(d) 分类收紧；P0-(d) path-to-white 随 headroom 缩放 + 蓝色高光金样；P1-(b) 软肩替换 clip/max；P1-(f) sidecar 取样点移到 boost 之后。全部有现成测试文件可挂。

**阶段 2（响应性）**
P0-(a) 动态 profile 重采样接线（复用 `tools/export_hdr_curve_profiles.py` 逻辑 + `RouteProfileCacheKey`）；P1-(c) headroom 稳定性策略。验收标准：拉动 Chemistry `developer_exhaustion` 滑杆，导出 HDR 的 `chemical_shoulder_severity` diagnostics 随之变化。

**阶段 3（体验）**
P0-(b) EDR 预览（Metal 层 + headroom 查询 + W 插值）；Lightroom 式 HDR 范围可视化；SDR/HDR A/B；P1-(j) 元数据注入。

**阶段 4（生态扩展，按需）**
P1-(e) PQ 交付（或正式砍掉）；P1-(i) P3 limiting；P2-(e) Ultra HDR JPEG 导出选项露出；P2-(a) 遗留栈清理。

---

## 9. 参考资料

**标准与官方文档**
- [ITU-R BT.2408（HDR 制作操作实践：203 nits 参考白、graphics white、肤色电平）](https://www.itu.int/dms_pub/itu-r/opb/rep/R-REP-BT.2408-8-2024-PDF-E.pdf)
- [ISO 21496-1:2025 gain map 标准](https://www.iso.org/standard/86775.html) ·「[Adobe gain map 白皮书（Eric Chan）](https://helpx.adobe.com/camera-raw/using/gain-map.html)」·「[Android Ultra HDR 格式规范](https://developer.android.com/media/platform/hdr-image-format)」·「[libultrahdr](https://github.com/google/libultrahdr)」
- [MovieLabs：PQ→HLG 映射最佳实践（EETF 对比、maxRGB 保色相结论）](https://movielabs.com/ngvideo/MovieLabs_Mapping_PQ_to_HLG_v1.0.pdf)
- ACES 2.0 官方技术文档：[Output Transforms 总览](https://docs.acescentral.com/system-components/output-transforms/technical-details/rendering-overview/) ·「[Tone Mapping / tonescale](https://docs.acescentral.com/system-components/output-transforms/technical-details/tone-mapping/)」·「[Chroma Compression（path-to-white 全部公式）](https://docs.acescentral.com/system-components/output-transforms/technical-details/chroma-compression/)」
- Apple：[WWDC21 Explore HDR rendering with EDR](https://developer.apple.com/videos/play/wwdc2021/10161/) ·「[WWDC23 Support HDR images in your app](https://developer.apple.com/videos/play/wwdc2023/10181/)」·「[WWDC24 Use HDR for dynamic image experiences](https://developer.apple.com/videos/play/wwdc2024/10177/)」·「[NSScreen.maximumExtendedDynamicRangeColorComponentValue](https://developer.apple.com/documentation/AppKit/NSScreen/maximumExtendedDynamicRangeColorComponentValue?language=objc)」

**胶片 × HDR 实践**
- [Filmbox Pro（Highlight Unroll 到 1000 nits）](https://videovillage.com/filmbox/) ·「[发布公告](https://videovillage.com/blog/2025/08/18/filmbox-pro.html)」·「[Filmbox 200 nits 纸白争论与开发者表态](https://daejeonchronicles.com/2023/10/29/filmbox-more-hdr-y-images-in-future-update/)」
- [John Daro：胶片内容的 PQ 母版制作（print-match、高光再平衡、乳剂 LMT、HDR 颗粒管理）](https://www.johndaro.com/blog/tag/PQ)
- [Daejeon Chronicles：HDR Reference White](https://daejeonchronicles.com/2021/02/13/hdr-reference-white/) ·「[实测：多数 HDR 剧集 diffuse white 远低于 203 nits](https://daejeonchronicles.com/2023/07/05/diffuse-white-level-of-most-episodic-hdr-content-nowhere-near-203-nits/)」
- [fylm.ai：ACES 印片模拟（AP1 原生测量、外壳 15% 色域映射）](https://fylm.ai/aces-print-film-emulation/) ·「[PixelToolsPost：胶片 look 的原理（D-logE、display-referred 本质）](https://pixeltoolspost.com/blogs/resolve/film-emulation-explained)」

**胶片物理**
- [Prolost：Digital Cinema Dynamic Range（Cineon 685、2383 上剪切高光呈粉灰）](https://prolost.com/blog/2008/2/22/digital-cinema-dynamic-range.html) ·「[Kodak Cineon 10-bit log 技术文档](https://www.dotcsw.com/doc/cineon1.pdf)」·「[Analog.cafe：胶片动态范围](https://www.analog.cafe/r/dynamic-range-in-film-photography-91uh)」

**色彩外观与 tone mapping 设计**
- [Bram Stout：Enhancing the ACES RRT（notorious six、胶片的 hue skew、AgX/PBR Neutral 对照、Abney 补偿）](https://bramstout.nl/en/webbooks/aces-rrt/)
- [ACES 2.0 colorist 视角变化综述（更缓的肩部膝点、SDR/HDR 匹配）](https://finalvfinal.com/aces-2-0-what-you-need-to-know-what-you-need-to-change/) ·「[Mixing Light：ACES 2.0 体积色域映射实测](https://mixinglight.com/color-grading-tutorials/aces-2-0-volumetric-gamut-mapping-in-action/)」
- [Frostbite：HDR color grading and display（grade once, output many）](https://www.ea.com/frostbite/news/high-dynamic-range-color-grading-and-display-in-frostbite) ·「[Unity HDRP HDR Output（paper white、校准菜单）](https://docs.unity3d.com/Packages/com.unity.render-pipelines.high-definition@14.0/manual/HDR-Output.html)」·「[Promit Roy：HDR 后补管线的陷阱](https://ventspace.wordpress.com/2017/10/20/games-look-bad-part-1-hdr-and-tone-mapping/)」

**照片 HDR 生态**
- [Eric Chan（Adobe）：High Dynamic Range Explained（Lightroom HDR 编辑模型）](https://blog.adobe.com/en/publish/2023/10/10/hdr-explained) ·「[Lightroom HDR 输出文档（HDR Limit、Visualize HDR）](https://helpx.adobe.com/lightroom-cc/using/hdr-output.html)」·「[ISO gain map 测试图集](https://people.csail.mit.edu/ericchan/hdr/jpeg-gain-map-iso.html)」
- [Greg Benz：Apple 的 ISO 21496-1 支持全解（设备 headroom 上限、生态碎片化）](https://gregbenzphotography.com/hdr-photos/apple-macos-ios-hdr-iso-gain-map-21496-1/) ·「[ISO gain maps 分享指南](https://gregbenzphotography.com/hdr-photos/iso-21496-1-gain-maps-share-hdr-photos/)」·「[Awesome Gain Maps 资料集](https://github.com/NMoroney/Awesome-Gain-Maps)」

**项目内部文档（交叉引用）**
- `docs/hdr-modes.md`、`docs/hdr-routemaster-rewrite*.md`、`docs/hdr-export-pipeline.md`、`docs/heic-iso21496-compliance.md`、`docs/hdr/gain-map-HDR-analysis-report.*`、`docs/internal/dev/2026-06-08-chemical-highlight-rolloff-hdr.md`、`docs/profile-aware-hdr-audit-report.md`、`docs/hdr/research-gui-color-hdr.md`
