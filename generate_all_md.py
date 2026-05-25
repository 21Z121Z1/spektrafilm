import json
import os
import numpy as np

# Load the data
with open('/Users/retriedstormtrooper/Documents/spektrafilm-main/curve_analysis.json') as f:
    results = json.load(f)

# Calculate global stats to provide relative context
all_shadow_floor = [r['shadow_floor_y'] for r in results]
all_shadow_spread = [r['shadow_spread'] for r in results]
all_shadow_contrast = [r['shadow_contrast'] for r in results]
all_midtone_contrast = [r['midtone_contrast'] for r in results]
all_look_white = [r['look_white_y'] for r in results]
all_shoulder_spread = [r['shoulder_spread'] for r in results]
all_highlight_contrast = [r['highlight_contrast'] for r in results]

median_sc = np.median(all_shadow_contrast)
median_mc = np.median(all_midtone_contrast)
median_ss = np.median(all_shoulder_spread)
median_hc = np.median(all_highlight_contrast)

output_dir = "/Users/retriedstormtrooper/Documents/spektrafilm-main/docs/curve_analysis"
os.makedirs(output_dir, exist_ok=True)

for r in results:
    film = r['film']
    paper = r['paper']
    sf = r['shadow_floor_y']
    ss = r['shadow_spread']
    sc = r['shadow_contrast']
    mc = r['midtone_contrast']
    lw = r['look_white_y']
    sy = r['shoulder_y']
    shs = r['shoulder_spread']
    hc = r['highlight_contrast']
    fit_dmin = r.get('fit_dmin', 0.0)
    fit_dmax = r.get('fit_dmax', 1.0)
    fit_k = r.get('fit_k', 1.0)
    fit_x0 = r.get('fit_x0', 0.0)
    fit_nu = r.get('fit_nu', 1.0)
    
    md = []
    md.append(f"# {film} + {paper} 曲线分析")
    md.append("\n## 组合基本数据")
    md.append(f"- **胶片 (Film)**: `{film}`")
    md.append(f"- **相纸 (Paper)**: `{paper}`")
    
    md.append("\n## 全曲线数据指标")
    md.append("| 区域 | 指标名称 | 取值 | 描述 |")
    md.append("| :--- | :--- | :--- | :--- |")
    md.append(f"| **暗部/趾部** | Shadow Floor Y | `{sf:.4f}` | 极暗处的黑场基底亮度 (Dmin) |")
    md.append(f"| | Shadow Tint (Spread) | `{ss:.4f}` | 极暗处的 RGB 色偏程度 |")
    md.append(f"| | Toe Contrast | `{sc:.4f}` | 暗部上升斜率 |")
    md.append(f"| **中间调** | Midtone Contrast | `{mc:.4f}` | 主体对比度 (Gamma) |")
    md.append(f"| | Look White Y | `{lw:.4f}` | SDR 基准下的相纸白点 (Diffuse White) |")
    md.append(f"| **高光肩部** | Shoulder Y | `{sy:.4f}` | 极高光滚降到达的极限亮度 |")
    md.append(f"| | Highlight Contrast | `{hc:.4f}` | 极高光的压缩后斜率 |")
    md.append(f"| | Shoulder Tint (Spread)| `{shs:.4f}` | 极高光区域的通道衰减色偏 |")
    
    md.append("\n## 拟合数学公式 (5-Parameter Generalized Logistic Function)")
    md.append("为了追求更高的精确度，特别是为了拟合胶片曲线趾部 (Toe) 和肩部 (Shoulder) 的**不对称性**，我们采用了 5 参数的理查兹曲线 (Richards Curve) 进行高精度拟合（Y vs $\\log_2(\\text{scene\_luminance})$，即 EV）。")
    md.append("其理论曲线公式如下：")
    md.append("$$ Y(EV) = D_{min} + \\frac{D_{max} - D_{min}}{(1 + \\nu e^{-k(EV - EV_0)})^{\\frac{1}{\\nu}}} $$")
    md.append("\n**具体参数取值为：**")
    md.append(f"- **$D_{{min}}$ (暗部底色基准)** = `{fit_dmin:.4f}`")
    md.append(f"- **$D_{{max}}$ (高光极限量)** = `{fit_dmax:.4f}`")
    md.append(f"- **$k$ (反差/坡度)** = `{fit_k:.4f}`")
    md.append(f"- **$EV_0$ (曝光中点)** = `{fit_x0:.4f}`")
    md.append(f"- **$\\nu$ (不对称系数)** = `{fit_nu:.4f}`")
    md.append(f"\n> 这意味着，在 HDR 的数学推导中，您可以直接使用以下极高精度的函数来模拟或逆推 {film} 与 {paper} 的全段亮度转移特性：")
    md.append(f"> $$ Y = {fit_dmin:.4f} + \\frac{{{fit_dmax - fit_dmin:.4f}}}{{(1 + {fit_nu:.4f} \\cdot e^{{-{fit_k:.4f}(EV - {fit_x0:.4f})}})^{{\\frac{{1}}{{{fit_nu:.4f}}}}}}} $$")

    md.append("\n## 针对此组合的详细分析与 HDR 建议")
    
    # Analyze shadows
    md.append("### 1. 暗部表现 (Shadows)")
    if sc > median_sc:
        md.append(f"该组合的暗部反差 (`{sc:.4f}`) 较强，黑场较为深邃。")
    else:
        md.append(f"该组合的暗部反差 (`{sc:.4f}`) 较平缓，暗部细节保留较多。")
        
    if ss > 0.03:
        md.append(f"**注意**：在暗部存在较强的色偏 (`{ss:.4f}`)，这是该相纸基底色带来的模拟胶片质感。在进行 HDR 扩展或黑点调整时，切忌强制进行灰平衡或裁切，否则会破坏该组合独有的暗部氛围。")
        
    # Analyze midtones
    md.append("\n### 2. 中间调表现 (Midtones)")
    if mc > median_mc:
        md.append(f"中间调对比度极高 (`{mc:.4f}`)。这意味着胶片将光线能量迅速推向了相纸的宽容度极限，使得画面反差强烈、色彩浓郁。")
    else:
        md.append(f"中间调对比度较低 (`{mc:.4f}`)。画面过渡相对平缓，高光部分具有更为线性的响应空间。")

    # Analyze highlights
    md.append("\n### 3. 高光与滚降 (Highlights & Rolloff)")
    if hc < 0.01:
        md.append(f"在过曝区域，相纸已经基本达到了其物理极限，高光对比度极低 (`{hc:.4f}`)，几乎呈现平坦的纯色块。")
    else:
        md.append(f"在过曝区域，曲线依然保持着一定的攀升能力 (`{hc:.4f}`)，高光宽容度表现较好。")

    if shs > 0.08:
        md.append(f"**警告 (高光色偏)**：极高光的通道分离度非常高 (`{shs:.4f}`)。这是由于某一个或两个通道（通常是 Red 或 Blue）已经完全停止响应，而其他通道仍在增长导致。如果在这个组合上使用过大的 `max_headroom`，将会拉出诡异的偏色高光（例如发绿或发洋红）。HDR 的 `paper_rolloff_k` 需要设置得更平滑，且建议启用 `graft_strength` 来压制分离。")
    else:
        md.append(f"极高光的通道分离度适中 (`{shs:.4f}`)，三通道高光相对中性，非常适合进行激进的 HDR Diffuse Lift 映射，不易产生严重的色彩断层。")

    filename = f"{film}_on_{paper}.md"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w") as f_out:
        f_out.write("\n".join(md))

print(f"Generated 160 analysis documents in {output_dir}")
