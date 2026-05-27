# kodak_ektachrome_100 + fujifilm_crystal_archive_typeii 曲线分析

## 组合基本数据
- **胶片 (Film)**: `kodak_ektachrome_100`
- **相纸 (Paper)**: `fujifilm_crystal_archive_typeii`

## 全曲线数据指标
| 区域 | 指标名称 | 取值 | 描述 |
| :--- | :--- | :--- | :--- |
| **暗部/趾部** | Shadow Floor Y | `0.9213` | 极暗处的黑场基底亮度 (Dmin) |
| | Shadow Tint (Spread) | `0.0038` | 极暗处的 RGB 色偏程度 |
| | Toe Contrast | `-0.0051` | 暗部上升斜率 |
| **中间调** | Midtone Contrast | `-0.4031` | 主体对比度 (Gamma) |
| | Look White Y | `0.5381` | SDR 基准下的相纸白点 (Diffuse White) |
| **高光肩部** | Shoulder Y | `0.3091` | 极高光滚降到达的极限亮度 |
| | Highlight Contrast | `-0.0153` | 极高光的压缩后斜率 |
| | Shoulder Tint (Spread)| `0.2475` | 极高光区域的通道衰减色偏 |

## 拟合数学公式 (5-Parameter Generalized Logistic Function)
为了追求更高的精确度，特别是为了拟合胶片曲线趾部 (Toe) 和肩部 (Shoulder) 的**不对称性**，我们采用了 5 参数的理查兹曲线 (Richards Curve) 进行高精度拟合（Y vs $\log_2(\text{scene\_luminance})$，即 EV）。
其理论曲线公式如下：
$$ Y(EV) = D_{min} + \frac{D_{max} - D_{min}}{(1 + \nu e^{-k(EV - EV_0)})^{\frac{1}{\nu}}} $$

**具体参数取值为：**
- **$D_{min}$ (暗部底色基准)** = `0.9225`
- **$D_{max}$ (高光极限量)** = `0.3037`
- **$k$ (反差/坡度)** = `1.0873`
- **$EV_0$ (曝光中点)** = `-0.6687`
- **$\nu$ (不对称系数)** = `0.0010`

> 这意味着，在 HDR 的数学推导中，您可以直接使用以下极高精度的函数来模拟或逆推 kodak_ektachrome_100 与 fujifilm_crystal_archive_typeii 的全段亮度转移特性：
> $$ Y = 0.9225 + \frac{-0.6188}{(1 + 0.0010 \cdot e^{-1.0873(EV - -0.6687)})^{\frac{1}{0.0010}}} $$

## 针对此组合的详细分析与 HDR 建议
### 1. 暗部表现 (Shadows)
该组合的暗部反差 (`-0.0051`) 较平缓，暗部细节保留较多。

### 2. 中间调表现 (Midtones)
中间调对比度较低 (`-0.4031`)。画面过渡相对平缓，高光部分具有更为线性的响应空间。

### 3. 高光与滚降 (Highlights & Rolloff)
在过曝区域，相纸已经基本达到了其物理极限，高光对比度极低 (`-0.0153`)，几乎呈现平坦的纯色块。
**警告 (高光色偏)**：极高光的通道分离度非常高 (`0.2475`)。这是由于某一个或两个通道（通常是 Red 或 Blue）已经完全停止响应，而其他通道仍在增长导致。如果在这个组合上使用过大的 `max_headroom`，将会拉出诡异的偏色高光（例如发绿或发洋红）。HDR 的 `paper_rolloff_k` 需要设置得更平滑，且建议启用 `graft_strength` 来压制分离。