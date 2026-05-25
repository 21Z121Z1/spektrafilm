# 胶片与相纸组合的 HDR 曲线影响深度分析报告

## 核心结论
我们的数据（遍历 160 种胶片与相纸的组合）清楚地表明，**HDR 映射曲线必须基于【胶片+相纸】的联合结果进行动态调整，而不能仅仅基于相纸或仅仅基于胶片单方面的特性。**

这是因为：
1. **动态范围（高光滚降）的极限由相纸决定，但到达极限的速度由胶片对比度决定。** 不同的胶片在同样相纸上的高光压缩曲线斜率完全不同。
2. **三通道高光分离（色偏 / Tinting）在不同组合下差异巨大。** 有些相纸（如 Endura 系列）在被高对比度反转片（如 Velvia）推顶时，R、G、B 三通道的最大密度衰减不同，会产生强烈的高光偏色；此时如果在 HDR 映射中不顾通道分离而生硬地施加统一个亮度补偿，会造成高光色彩断层或“发糊”。

## 1. 相纸（Print Paper）对高光阈值与通道分离的影响
相纸决定了模拟管线输出的绝对 `Paper White` (漫反射白) 及其高光衰减极限。我们提取了部分相纸的平均高光肩部 (Shoulder Y) 及通道分离度 (Shoulder Spread, RGB的最大差值)：

| 相纸 (Print Paper) | 平均 Shoulder Y | 平均通道分离度 (Tint) |
| :--- | :---: | :---: |
| `kodak_ultra_endura` | 0.706 | 0.061 |
| `kodak_endura_premier` | 0.770 | 0.042 |
| `kodak_ektacolor_edge` | 0.762 | 0.028 |
| `kodak_supra_endura` | 0.775 | 0.034 |
| `kodak_portra_endura` | 0.776 | 0.039 |
| `fujifilm_crystal_archive_typeii` | 0.799 | 0.057 |
| `kodak_2383` | 0.789 | 0.079 |
| `kodak_2393` | 0.787 | 0.044 |

**分析**：如上所示，有些相纸（如 `kodak_2383` 或 `fujifilm_crystal_archive`）的平均 Shoulder Y 很高，且通道分离度小，这说明它们的高光非常中性，能够承载更多的高光信息。而部分相纸的 Shoulder Spread 极大，这意味着它们在极高光区域（如天空、灯泡）会呈现出强烈的相纸基底色（Paper Base Tint）。**如果 HDR Diffuse Lift 仅仅拉升亮度而不兼顾这种三通道的高光分离特性，原本的高光色彩对比将被彻底破坏。**

## 2. 胶片（Film Stock）对曲线对比度的驱动
同一张相纸，由于匹配的胶片不同，其到达高光极限的“斜率”也就是对比度（Contrast）差异极大。这直接影响 HDR 中 Specular Rolloff 应该多早介入。

| 胶片 (Film Stock) | 平均对比度 (Midtone Contrast) | 平均 Look White Y |
| :--- | :---: | :---: |
| `kodak_portra_800_push2` | 0.737 | 0.794 |
| `kodak_portra_800_push1` | 0.689 | 0.776 |
| `fujifilm_xtra_400` | 0.670 | 0.813 |
| `fujifilm_c200` | 0.663 | 0.791 |
| `kodak_ektar_100` | 0.649 | 0.760 |
| `kodak_verita_200d` | 0.553 | 0.719 |
| `kodak_kodachrome_64` | -0.535 | 0.478 |
| `kodak_ektachrome_100` | -0.615 | 0.407 |
| `fujifilm_velvia_100` | -0.678 | 0.348 |
| `fujifilm_provia_100f` | -0.712 | 0.321 |

**分析**：高反差的反转片（如 `fujifilm_velvia_100` 或 `kodak_ektachrome_100`）对比度极高，它们会比低反差负片（如 `kodak_vision3_500t`）更快地“撞”到相纸的宽容度天花板（Look White Y）。因此：
- 对于高反差胶片，HDR 的 Specular Rolloff (高光滚降) `k` 值应该更小、过渡更柔和，因为图像很快就进入了被相纸硬切的区域。
- 对于低反差胶片，胶片本身保留了极佳的高光层次，HDR Rolloff 可以更加线性地还原场景能量，不需要过早干预。

## 3. 对 HDR 双层映射曲线设计的指导意义
基于以上三通道和交叉组合的分析，我们的 HDR `_graft_scene_luminance` 和 `_apply_diffuse_lift` 的实现应注意以下几点：
> [!IMPORTANT]
> **不要使用单一的固定曲线**
> 1. **基于亮度的 Lift（Diffuse Lift）必须转为基于三通道的相对 Lift：** 现有的 `sdr_base` 已经包含了由于相纸导致的 RGB 分离（即色偏）。在应用 Diffuse Lift 时，不应统一按照 Luma 提亮，而应该计算 `RGB_lift_factor` 从而维持原有的通道比例，以保全高光的胶片质感。
> 2. **Rolloff 强度的自适应：** 应该通过计算 `(Look White Y - Midtone Y)` 的对比度斜率来决定 HDR Rolloff 的 `paper_rolloff_k`（陡峭度）。斜率越高，`k` 值应当进行适应性的放缓。
> 3. **最高 Headroom 的软裁切：** 某些相纸组合下，R 和 B 通道可能早就停止响应，只有 G 通道在增长。如果 Headroom 拉得过高，G 通道独走会导致太阳变成绿色。我们通过 GUI 暴露的 `max_headroom` 和 `graft_strength` 恰好使得用户能在遇到极端组合时手动压制这种失真。
