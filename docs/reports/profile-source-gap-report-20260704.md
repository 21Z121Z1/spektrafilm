# Spektrafilm 内置 Profile 物理数据与模型缺口分析报告 (Gap Report)

**报告日期**: 2026-07-04  
**审计人员**: Antigravity  

本报告旨在汇总 Spektrafilm 28 个内置胶卷与相纸 profile 在官方数据源约束下的缺失、数据占位/过度拟合问题以及维度表示局限性，并为下一阶段物理拟合（Constrained Refit）提供候选修复队列的输入参数规范（Refit Input Spec）。

---

## 1. 核心物理缺口与限制分析

经过对柯达、富士官方技术 brochure、datasheet 的完整检索以及与内置 JSON 文件的数值比对，识别出以下核心物理缺口：

### 1.1 彩色负片 CMY 染料吸收光谱缺失（普遍缺口）
*   **物理现象**：在 C-41 冲洗彩色负片（包括 Portra 160/400/800, Ektar 100, Gold 200, UltraMax 400, C200, Pro 400H, Superia X-TRA 400 以及 ECN-2 电影负片 Vision3 系列）中，**官方 datasheet 从未发表过单独的 Cyan, Magenta, Yellow 纯染料光谱吸收密度曲线**。
*   **官方数据局限**：柯达（如 E-4050）与富士的技术手册中，只提供了一张复合的 `Spectral Dye Density Curves`，其中仅画出两条曲线：
    1.  `Minimum Density` (D-min)：未曝光片基的橙色面具吸收。
    2.  `Midscale Neutral`：中性曝光点处（例如 1.0 视觉中性密度处）的复合染料吸收。
*   **Profile 现状**：当前 profile 中的 `channel_density` (单独的 [81, 3] CMY 矩阵) 是原作者通过“解混/解混度”算法（Unmixing）或模型优化反推出来的，并非来自官方直接测量数据。这导致三通道纯染料光谱吸收的形状存在一定的重构不确定性。

### 1.2 富士 Pro 400H 的第四感光层降维误差（架构限制）
*   **物理现象**：富士专业负片 `fujifilm_pro_400h` 的一个核心物理专利是拥有**第四个感光层（Fourth color-correction layer，蓝绿色感光层）**。该层用于在混合光源或荧光灯下抑制绿/洋红偏色，模拟人眼真实色彩匹配函数。
*   **Profile 现状**：Spektrafilm 当前的 `log_sensitivity` schema 仅支持 RGB 三通道（形状为 `[81, 3]`）。因此在建立 Pro 400H 的感光度 profile 时，原作者直接将第四层物理感光度丢弃，并将其在三通道上进行了“降维表征”。这导致 Pro 400H 在特定色温或人工光源下的色彩模拟失真，无法重现该胶片原厂独特的色彩补偿功能。

### 1.3 电影印片与 RA-4 相纸的归一化与绝对密度偏差（数值与语义偏差）
*   **物理现象**：
    1.  **电影印片 2383/2393**：柯达官方 2383 和 2393 的 datasheet 明确指出，其发表的 `Spectral Dye Density Curves` 在 Y 轴上标注为 "Normalized Density"，即代表其进行了峰值归一化（Peak-normalized，将 CMY 三色染料的最大吸收度拉平到 1.0），或者是将曲线在特定光源（5400K 氙弧投影灯）下归一化为 1.0 的视觉中性密度（Visual Neutral Density of 1.0）。
    2.  **RA-4 相纸系列**：与电影印片类似，大部分 RA-4 印相纸（如 Endura Premier、Supra Endura 等）在官方技术说明书中所发表的染料吸收光谱曲线同样是进行了**归一化到 1.0 视觉中性密度**的曲线，而不是代表相纸最大染料负荷下的绝对物理反射光密度。
*   **Profile 现状与残差**：
    在当前的 `kodak_2383` profile 中，其特征曲线（density_curves）在 1.0 log exposure 处的绝对密度高企至 `R=3.65, G=3.07, B=2.88`。而在官方 Status A 实测数据中，在此处的投影光密度仅在 0.65D 左右。
    *   `kodak_2383` 灵敏度 MAE: **1.449 log10**。
    *   `kodak_2383` 特征曲线 MAE: **1.278D**，RMSE: **1.597D**。
    这证明当前的 2383 曲线并非代表绝对物理密度，而是为数字显示（如 HDR 曲线匹配）进行了大幅度拉伸与视觉优化的结果。若将其直接用于模拟光学相纸印制过程，会产生过高的对比度和饱和度偏差。这一归一化语义的混淆也同样存在于大部分相纸 profile 中，是后续 Tier 1 constrained refit 必须解决的重要物理语义转换缺口。

### 1.4 数据重用与通用占位（数据冗余）
*   **感光度继承**：`kodak_supra_endura` 复制了 `kodak_portra_endura` 的 `log_sensitivity`（哈希均为 `46688d1a`），这说明 Supra 并没有使用其自身的相纸感光度曲线，而是继承了 Portra 相纸的数据。
*   **片基占位**：`fujifilm_crystal_archive_typeii` 与 `kodak_supra_endura` 共享了完全相同的 `base_density`（哈希均为 `81843b19`），说明片基的反射吸收采用了相同的通用占位数值。
*   **推挽继承**：`kodak_portra_800_push1` 和 `push2` 的所有光谱字段（敏感度、片基、中性密度等）均与基础款一模一样，物理上虽然正确（曝光时感光涂层未变），但缺乏针对推挽冲洗可能引起的光谱染料轻微偏移的描述。

---

## 2. 核心审计组数值残差汇总 (MAE / RMSE)

通过对核心审计组的 profile 数值与官方 datasheet 的关键测定点进行比对，计算出的绝对残差（MAE/RMSE）如下：

| Profile | Sensitivity MAE (log10) | Density Curves MAE (D) | Density Curves RMSE (D) | 物理偏差定性 |
| ------- | ----------------------- | ---------------------- | ----------------------- | ------------ |
| `kodak_portra_400` | 0.834 | 0.249 | 0.287 | 灵敏度基准整体平移；低曝光区特征曲线偏平。 |
| `kodak_portra_800` | 0.943 | 0.295 | 0.342 | 光谱敏感度高度平移；特征曲线暗部与官方不符。 |
| `fujifilm_pro_400h` | 0.633 | 0.303 | 0.345 | 缺失第四层导致的感光度平移；特征曲线存在线性偏差。 |
| `kodak_verita_200d` | 0.808 | 0.311 | 0.364 | 灵敏度整体平移；特征曲线在 ECN-2 下的暗部偏低。 |
| `kodak_vision3_500t` | 0.471 | 0.417 | 0.481 | 特征曲线在 Status M 下的线性响应范围偏窄。 |
| `kodak_2383` | 1.449 | 1.278 | 1.597 | 特征曲线光密度发生数倍放大，极度压缩暗部。 |

*注：Sensitivity MAE 主要是由于 Spektrafilm 的内部物理模型将所有感光度都做了归一化与缩放，与官方 datasheet 上的绝对物理敏感度（erg/cm² 的倒数）存在整体的 Log 平移（约 0.5 到 1.5 个 Log 单位）。*

---

## 3. Refit-readiness 修复就绪度排名与 Spec 规范

根据官方数据完整度、Profile 风险系数以及用户可见的模拟真实性影响，给出下一阶段数值修复就绪度排名（Top 3）：

### 排名 1: `kodak_portra_400`
*   **可用物理约束**：
    *   官方 E-4050 提供完整的 D-min (Minimum Density) 复合吸收曲线。
    *   官方 E-4050 提供 1.0 视觉中性密度下的 Midscale Neutral 复合吸收曲线。
    *   官方 E-4050 提供 Status M 特征曲线（R/G/B 三色，EC-41 冲洗）。
    *   官方 E-4050 提供三色 Spectral Sensitivity 敏感度曲线（350 - 700 nm）。
*   **缺失约束**：分离的 C/M/Y 纯染料吸收光谱曲线（需解混）。
*   **推荐修复策略**：`composite_to_channel_constrained_refit`（Tier 1 约束物理重构）。在保证 C/M/Y 相加后完美符合官方 D-min 与 Midscale Neutral 复合的前提下，用平滑性和非负约束重新拟合 CMY 染料吸收，并修复特征曲线的 MAE (0.249D)。
*   **机器可读 Spec (Refit Spec)**:
    ```json
    "refit_spec": {
        "refit_candidate": true,
        "usable_constraints": [
            "minimum_density_curve",
            "midscale_neutral_curve",
            "characteristic_curves_rgb",
            "spectral_sensitivity_rgb"
        ],
        "missing_constraints": [
            "separated_cmy_dye_density"
        ],
        "recommended_refit_type": "composite_to_channel_constrained_refit"
    }
    ```

### 排名 2: `kodak_2383`
*   **可用物理约束**：
    *   官方 H-1-2383 提供了 C, M, Y 纯染料的 peak-normalized 吸收曲线。
    *   官方 H-1-2383 提供了三色 Spectral Sensitivity 敏感度曲线。
    *   官方 H-1-2383 提供了 Status A 特征曲线。
*   **缺失约束**：绝对尺度的 CMY 纯染料吸收光谱。
*   **推荐修复策略**：`normalized_to_absolute_constrained_refit`（Tier 1 绝对密度标定拟合）。引入 2383 的 Status A 绝对特征曲线，对其归一化的染料光谱的最大绝对吸收度进行物理标定，消除目前高达 1.597D 的特征曲线 RMSE，避免电影模拟中暗部死黑和色调偏色。
*   **机器可读 Spec (Refit Spec)**:
    ```json
    "refit_spec": {
        "refit_candidate": true,
        "usable_constraints": [
            "characteristic_curves_rgb",
            "spectral_sensitivity_rgb",
            "normalized_cmy_dye_density"
        ],
        "missing_constraints": [
            "absolute_cmy_dye_density"
        ],
        "recommended_refit_type": "normalized_to_absolute_constrained_refit"
    }
    ```

### 排名 3: `kodak_portra_800`
*   **可用物理约束**：
    *   官方 E-4040 提供 D-min 与 Midscale Neutral 复合曲线。
    *   官方 E-4040 提供 Status M 特征曲线与 RGB 敏感度曲线。
*   **缺失约束**：分离的 C/M/Y 纯染料吸收光谱。
*   **推荐修复策略**：`composite_to_channel_constrained_refit`，并同步纠正其 push 1/push 2 变体中特征曲线的拟合偏差（MAE 0.295D）。
*   **机器可读 Spec (Refit Spec)**:
    ```json
    "refit_spec": {
        "refit_candidate": true,
        "usable_constraints": [
            "minimum_density_curve",
            "midscale_neutral_curve",
            "characteristic_curves_rgb",
            "spectral_sensitivity_rgb"
        ],
        "missing_constraints": [
            "separated_cmy_dye_density"
        ],
        "recommended_refit_type": "composite_to_channel_constrained_refit"
    }
    ```
