import json
from collections import defaultdict
import numpy as np

with open('/Users/retriedstormtrooper/Documents/spektrafilm-main/curve_analysis.json') as f:
    results = json.load(f)

by_paper = defaultdict(list)
by_film = defaultdict(list)

for r in results:
    by_paper[r['paper']].append(r)
    by_film[r['film']].append(r)

md = []
md.append("# 胶片与相纸组合的全曲线 (Full Curve) HDR 影响深度分析报告\n")

md.append("## 核心结论")
md.append("经过对 160 种胶片与相纸组合的全段曲线（从极暗部到极高光）提取数据，我们发现：**HDR 映射不应仅仅在最后阶段处理高光（Rolloff），而是必须对不同相纸的基底反差（Base Fog / Dmin）和不同胶片的整体对比度有全盘感知。**\n")
md.append("具体来说：")
md.append("1. **暗部 (Shadows/Toe) 的提升程度由相纸特性决定：** 不同的相纸具有不同的 Dmin（Base Fog），这决定了黑色的深邃程度。")
md.append("2. **中间调 (Midtones) 的线性斜率由胶片主导：** 胶片对能量的非线性映射决定了图像达到 Paper White 的速度。")
md.append("3. **高光 (Highlights/Shoulder) 的滚降与色偏由相纸极限主导：** 当高强度的能量推入相纸极限时，通道衰减速度不一导致色偏（Tinting）。\n")

md.append("## 1. 暗部 (Shadows & Toe) 与相纸基底色")
md.append("我们测量了极暗场景（Scene Y = 0.001）下的黑场底色 (Shadow Floor Y) 和暗部对比度 (Toe Contrast)：")
md.append("\n| 相纸 (Print Paper) | 平均黑场 (Shadow Floor Y) | 平均暗部色偏 (Tint) | 平均暗部反差 (Toe Contrast) |")
md.append("| :--- | :---: | :---: | :---: |")

for paper, items in by_paper.items():
    avg_y = np.mean([x['shadow_floor_y'] for x in items])
    avg_spread = np.mean([x['shadow_spread'] for x in items])
    avg_tc = np.mean([x['shadow_contrast'] for x in items])
    md.append(f"| `{paper}` | {avg_y:.4f} | {avg_spread:.4f} | {avg_tc:.3f} |")

md.append("\n**分析**：相纸自身的基底 (Paper Base) 对暗部有决定性影响。例如 `fujifilm_crystal_archive` 的黑场极低（对比度高，黑色扎实），而 `kodak_ektacolor_edge` 或者某些特定负片相纸在暗部有较高的 Base Fog。同时，暗部本身也存在色偏（Tint）。**如果我们在 HDR 映射时通过改变黑点 (Black Point) 来拉升对比度，必须极其小心，因为相纸的 Shadow Tint 是胶片感的一部分，粗暴的去色偏或截断会破坏暗部质感。**\n")

md.append("## 2. 中间调 (Midtones) 与对比度驱动")
md.append("中间调 (Scene Y = 0.05 ~ 1.0) 是视觉感知的主体部分。该段对比度决定了场景信息转化为相纸亮度的速度。")
md.append("\n| 胶片 (Film Stock) | 平均中间调对比度 (Midtone Contrast) | 平均到达 Diffuse White (Y) |")
md.append("| :--- | :---: | :---: |")

# Sort films by contrast
films_sorted = sorted(by_film.items(), key=lambda x: np.mean([i['midtone_contrast'] for i in x[1]]), reverse=True)
for film, items in films_sorted[:5] + films_sorted[-5:]:
    avg_mc = np.mean([x['midtone_contrast'] for x in items])
    avg_lw = np.mean([x['look_white_y'] for x in items])
    md.append(f"| `{film}` | {avg_mc:.3f} | {avg_lw:.3f} |")

md.append("\n**分析**：反转片（如 `fujifilm_velvia_100` 或 `kodak_ektachrome_100`）的中间调斜率极高（甚至为负值反转或具有极强的对比压缩），它们将大量的光线能量挤压在了极短的亮度区间内。相反，低速负片（如负片 `kodak_vision3` 系列）则拥有更平缓的中间调。\n")

md.append("## 3. 高光肩部 (Highlights & Shoulder) 与极限衰减")
md.append("高光段 (Scene Y = 1.0 ~ 16.0) 展示了在极高曝光下，胶片+相纸组合是如何处理过曝的：")
md.append("\n| 胶片 (Film Stock) | 平均高光对比度 (Highlight Contrast) | 平均极高光色偏 (Shoulder Tint) |")
md.append("| :--- | :---: | :---: |")

films_shoulder_sorted = sorted(by_film.items(), key=lambda x: np.mean([i['highlight_contrast'] for i in x[1]]), reverse=True)
for film, items in films_shoulder_sorted[:5] + films_shoulder_sorted[-5:]:
    avg_hc = np.mean([x['highlight_contrast'] for x in items])
    avg_st = np.mean([x['shoulder_spread'] for x in items])
    md.append(f"| `{film}` | {avg_hc:.4f} | {avg_st:.3f} |")

md.append("\n**分析**：部分组合在 Diffuse White 之后几乎没有上升空间（Highlight Contrast 接近 0），这意味着相纸已经完全饱和，或者胶片本身没有高光宽容度。此时，强行进行极端的 HDR 亮度恢复会得到平坦的纯色块。而有些组合即使在过曝 4 档后，仍能保持一定的对比度斜率。\n")

md.append("## 4. 总结与 HDR 设计改进方向")
md.append("综上所述，HDR 的映射不仅需要考虑高光，还需要考虑从暗部到高光的完整连续性：")
md.append("> [!IMPORTANT]")
md.append("> **1. 保留相纸 Base Fog 与暗部 Tint：** HDR 的基准 SDR 必须完整保留暗部特性，不能为了“纯黑”而硬裁暗部，否则会失去模拟质感。")
md.append("> **2. 基于斜率的高光 Rolloff (自适应 k 值)：** 我们不仅要看 `Look White Y`，还要看 `Midtone Contrast`。中间调斜率越大的组合，其高光滚降的起始点应该越早，`k` 值应当越平缓，以避免高光突然变成“断层死白”。")
md.append("> **3. 限制 Headroom 避免色彩偏移：** 当极高光的 `Shoulder Tint` 极大时（三通道完全剥离），应当在 GUI 逻辑中限制其 `max_headroom` 或增大 `graft_strength`，避免用户拉出带有极度色偏（如诡异的绿色太阳）的高光信息。\n")

with open("film_print_hdr_analysis_full.md", "w") as f:
    f.write("\n".join(md))

print("Markdown artifact generated.")
