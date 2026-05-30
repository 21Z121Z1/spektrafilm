# fujifilm_xtra_400 + kodak_portra_endura 曲线分析

## 组合基本数据
- **胶片 (Film)**: `fujifilm_xtra_400`
- **相纸 (Paper)**: `kodak_portra_endura`

## 全曲线数据指标
| 区域 | 指标名称 | 取值 | 描述 |
| :--- | :--- | :--- | :--- |
| **暗部/趾部** | Shadow Floor Y | `0.0704` | 极暗处的黑场基底亮度 (Dmin) |
| | Shadow Tint (Spread) | `0.0287` | 极暗处的 RGB 色偏程度 |
| | Toe Contrast | `0.1838` | 暗部上升斜率 |
| **中间调** | Midtone Contrast | `0.7246` | 主体对比度 (Gamma) |
| | Look White Y | `0.7678` | SDR 基准下的相纸白点 (Diffuse White) |
| **高光肩部** | Shoulder Y | `0.9138` | 极高光滚降到达的极限亮度 |
| | Highlight Contrast | `0.0097` | 极高光的压缩后斜率 |
| | Shoulder Tint (Spread)| `0.0080` | 极高光区域的通道衰减色偏 |

## 拟合数学公式 (5-Parameter Generalized Logistic Function)
为了追求更高的精确度，特别是为了拟合胶片曲线趾部 (Toe) 和肩部 (Shoulder) 的**不对称性**，我们采用了 5 参数的理查兹曲线 (Richards Curve) 进行高精度拟合（Y vs $\log_2(\text{scene\_luminance})$，即 EV）。
其理论曲线公式如下：
$$ Y(EV) = D_{min} + \frac{D_{max} - D_{min}}{(1 + \nu e^{-k(EV - EV_0)})^{\frac{1}{\nu}}} $$

**具体参数取值为：**
- **$D_{min}$ (暗部底色基准)** = `0.0707`
- **$D_{max}$ (高光极限量)** = `0.9169`
- **$k$ (反差/坡度)** = `1.1288`
- **$EV_0$ (曝光中点)** = `-1.3527`
- **$\nu$ (不对称系数)** = `0.8028`

> 这意味着，在 HDR 的数学推导中，您可以直接使用以下极高精度的函数来模拟或逆推 fujifilm_xtra_400 与 kodak_portra_endura 的全段亮度转移特性：
> $$ Y = 0.0707 + \frac{0.8462}{(1 + 0.8028 \cdot e^{-1.1288(EV - -1.3527)})^{\frac{1}{0.8028}}} $$

## 针对此组合的详细分析与 HDR 建议
### 1. 暗部表现 (Shadows)
该组合的暗部反差 (`0.1838`) 较平缓，暗部细节保留较多。

### 2. 中间调表现 (Midtones)
中间调对比度极高 (`0.7246`)。这意味着胶片将光线能量迅速推向了相纸的宽容度极限，使得画面反差强烈、色彩浓郁。

### 3. 高光与滚降 (Highlights & Rolloff)
在过曝区域，相纸已经基本达到了其物理极限，高光对比度极低 (`0.0097`)，几乎呈现平坦的纯色块。
极高光的通道分离度适中 (`0.0080`)，三通道高光相对中性，非常适合进行激进的 HDR Diffuse Lift 映射，不易产生严重的色彩断层。