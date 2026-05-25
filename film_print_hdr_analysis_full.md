# 胶片与相纸组合的全曲线 (Full Curve) HDR 影响深度分析报告

## 核心结论
经过对 160 种胶片与相纸组合的全段曲线（从极暗部到极高光）提取数据，我们发现：**HDR 映射不应仅仅在最后阶段处理高光（Rolloff），而是必须对不同相纸的基底反差（Base Fog / Dmin）和不同胶片的整体对比度有全盘感知。**

具体来说：
1. **暗部 (Shadows/Toe) 的提升程度由相纸特性决定：** 不同的相纸具有不同的 Dmin（Base Fog），这决定了黑色的深邃程度。
2. **中间调 (Midtones) 的线性斜率由胶片主导：** 胶片对能量的非线性映射决定了图像达到 Paper White 的速度。
3. **高光 (Highlights/Shoulder) 的滚降与色偏由相纸极限主导：** 当高强度的能量推入相纸极限时，通道衰减速度不一导致色偏（Tinting）。

## 1. 暗部 (Shadows & Toe) 与相纸基底色
我们测量了极暗场景（Scene Y = 0.001）下的黑场底色 (Shadow Floor Y) 和暗部对比度 (Toe Contrast)：

| 相纸 (Print Paper) | 平均黑场 (Shadow Floor Y) | 平均暗部色偏 (Tint) | 平均暗部反差 (Toe Contrast) |
| :--- | :---: | :---: | :---: |
| `kodak_ultra_endura` | 0.2171 | 0.0374 | 0.152 |
| `kodak_endura_premier` | 0.2324 | 0.0358 | 0.140 |
| `kodak_ektacolor_edge` | 0.2445 | 0.0341 | 0.298 |
| `kodak_supra_endura` | 0.2298 | 0.0125 | 0.268 |
| `kodak_portra_endura` | 0.2390 | 0.0148 | 0.348 |
| `fujifilm_crystal_archive_typeii` | 0.2376 | 0.0277 | 0.245 |
| `kodak_2383` | 0.2025 | 0.0182 | 0.551 |
| `kodak_2393` | 0.1972 | 0.0081 | 0.585 |

**分析**：相纸自身的基底 (Paper Base) 对暗部有决定性影响。例如 `fujifilm_crystal_archive` 的黑场极低（对比度高，黑色扎实），而 `kodak_ektacolor_edge` 或者某些特定负片相纸在暗部有较高的 Base Fog。同时，暗部本身也存在色偏（Tint）。**如果我们在 HDR 映射时通过改变黑点 (Black Point) 来拉升对比度，必须极其小心，因为相纸的 Shadow Tint 是胶片感的一部分，粗暴的去色偏或截断会破坏暗部质感。**

## 2. 中间调 (Midtones) 与对比度驱动
中间调 (Scene Y = 0.05 ~ 1.0) 是视觉感知的主体部分。该段对比度决定了场景信息转化为相纸亮度的速度。

| 胶片 (Film Stock) | 平均中间调对比度 (Midtone Contrast) | 平均到达 Diffuse White (Y) |
| :--- | :---: | :---: |
| `kodak_portra_800_push2` | 0.774 | 0.793 |
| `fujifilm_xtra_400` | 0.764 | 0.813 |
| `kodak_portra_800_push1` | 0.753 | 0.776 |
| `fujifilm_c200` | 0.745 | 0.791 |
| `kodak_ektar_100` | 0.730 | 0.760 |
| `kodak_verita_200d` | 0.680 | 0.719 |
| `kodak_kodachrome_64` | -0.459 | 0.478 |
| `kodak_ektachrome_100` | -0.534 | 0.407 |
| `fujifilm_velvia_100` | -0.596 | 0.348 |
| `fujifilm_provia_100f` | -0.625 | 0.321 |

**分析**：反转片（如 `fujifilm_velvia_100` 或 `kodak_ektachrome_100`）的中间调斜率极高（甚至为负值反转或具有极强的对比压缩），它们将大量的光线能量挤压在了极短的亮度区间内。相反，低速负片（如负片 `kodak_vision3` 系列）则拥有更平缓的中间调。

## 3. 高光肩部 (Highlights & Shoulder) 与极限衰减
高光段 (Scene Y = 1.0 ~ 16.0) 展示了在极高曝光下，胶片+相纸组合是如何处理过曝的：

| 胶片 (Film Stock) | 平均高光对比度 (Highlight Contrast) | 平均极高光色偏 (Shoulder Tint) |
| :--- | :---: | :---: |
| `kodak_verita_200d` | 0.0127 | 0.020 |
| `kodak_vision3_200t` | 0.0122 | 0.020 |
| `kodak_vision3_250d` | 0.0121 | 0.020 |
| `kodak_vision3_500t` | 0.0121 | 0.019 |
| `kodak_vision3_50d` | 0.0116 | 0.019 |
| `fujifilm_xtra_400` | 0.0068 | 0.022 |
| `fujifilm_velvia_100` | -0.0096 | 0.160 |
| `fujifilm_provia_100f` | -0.0110 | 0.110 |
| `kodak_kodachrome_64` | -0.0135 | 0.235 |
| `kodak_ektachrome_100` | -0.0145 | 0.146 |

**分析**：部分组合在 Diffuse White 之后几乎没有上升空间（Highlight Contrast 接近 0），这意味着相纸已经完全饱和，或者胶片本身没有高光宽容度。此时，强行进行极端的 HDR 亮度恢复会得到平坦的纯色块。而有些组合即使在过曝 4 档后，仍能保持一定的对比度斜率。

## 4. 总结与 HDR 设计改进方向
综上所述，HDR 的映射不仅需要考虑高光，还需要考虑从暗部到高光的完整连续性：
> [!IMPORTANT]
> **1. 保留相纸 Base Fog 与暗部 Tint：** HDR 的基准 SDR 必须完整保留暗部特性，不能为了“纯黑”而硬裁暗部，否则会失去模拟质感。
> **2. 基于斜率的高光 Rolloff (自适应 k 值)：** 我们不仅要看 `Look White Y`，还要看 `Midtone Contrast`。中间调斜率越大的组合，其高光滚降的起始点应该越早，`k` 值应当越平缓，以避免高光突然变成“断层死白”。
> **3. 限制 Headroom 避免色彩偏移：** 当极高光的 `Shoulder Tint` 极大时（三通道完全剥离），应当在 GUI 逻辑中限制其 `max_headroom` 或增大 `graft_strength`，避免用户拉出带有极度色偏（如诡异的绿色太阳）的高光信息。
