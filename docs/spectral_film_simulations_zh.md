# 从零开始的胶片仿真

> **来源**: [https://discuss.pixls.us/t/48209](https://discuss.pixls.us/t/48209)
> **帖子数**: 710 | **浏览量**: 30676
> **抓取时间**: 2026-05-15 05:37

---

---

## #1 **Andrea** (@arctic) · 2025-02-09 19:35

> **TL;DR**
>
> 我正在探索使用已发布的数据表和基本原理来模拟全模拟彩色摄影过程（底片 + 相纸）。目标是利用基于物理的模型（包含光谱计算、颗粒、成色剂、光晕等）重现 Kodak 和 Fujifilm 的标志性外观，该模型提供了超越标准 LUT 的可调性。更多详情和代码可在 GitHub ([agx-emulsion](https://github.com/andreavolpato/agx-emulsion)) 上获取；此处的所有结果均使用 [v0.1.0](https://github.com/andreavolpato/agx-emulsion/releases/tag/v0.1.0-alpha) 版本（已有点旧），请查看 `main` 分支中的改进。

# [](#p-356352-the-true-color-of-film-negatives-1)胶片底片的真实颜色

不久前，我在网上看到了一场关于"胶片底片的真实颜色"的讨论。虽然记不清确切来源，但关键的结论是：最终颜色在很大程度上取决于成像过程的第二阶段——无论是扫描仪的色彩处理，还是模拟 RA4 彩色反转冲印过程。模拟冲印似乎是定义这种外观最真实的方式，尤其是因为相关公司（主要是 Kodak）花费了数十年来完善它。

这个想法促使我探索模拟彩色摄影的完整模拟流程。我显然不是暗房技术或色彩科学的专家，起初我严重低估了这项挑战的难度。幸运的是，我找到了一些不错的书籍章节 [1,2,3]。胶片乳剂非常精密，依赖于精细调控的化学工艺，涉及卤化银、多种染料成色剂，以及一点魔法。作为一名受过训练的化学家，我对制造胶片所需的所有科学和工程充满深深的敬佩。对于任何对胶片制造感兴趣的人，我强烈推荐观看 SmarterEveryDay 关于 Kodak 的系列视频（[Kodak 如何制造胶片？](https://www.youtube.com/watch?v=HQKy1KJpSVc) 共3集、[Kodak 胶片化学原理](https://www.youtube.com/watch?v=zJ8aNPStQ8M)、[Kodak 胶片质量控制过程](https://www.youtube.com/watch?v=VIH0dEMyv9w)）。

## [](#p-356352-goal-and-motivation-2)目标与动机

我的目标是仅使用数据表和基础知识，模拟从胶片拍摄到最终相纸的整个模拟摄影过程。我希望从公开的光谱数据出发，重现 Kodak 和 Fujifilm 产品的外观。例如，Portra 胶片及其配套相纸旨在为肤色提供微妙的色调偏移和完美的对比度，而消费级胶片和相纸则更饱和且更通用。这些特性中，有多少可以从零开始重现？

虽然胶片仿真 LUT 有类似的目标，但它们通常缺乏精细调优的灵活性。相比之下，完全基于物理的流程可以更好地重现底片加 RA4 冲印过程的真实多样性，通过提供可调参数来定制最终外观。当然，这种方法也带来了模拟摄影的固有限制，因此你需要欣赏（或怀念）模拟过程才能接受这些约束。

## [](#p-356352-negative-and-print-exposure-3)底片与相纸曝光

这里有一些试条来展示仿真的能力。整个成像过程分为两步：底片和相纸。可以控制两种不同的曝光，放大机中的彩色滤镜可以平衡相纸的颜色。以下是 Kodak Gold 200 在不同底片曝光补偿下的虚拟扫描。

[[![two_uncles_negative_exposure_ramp_gold_200_crystal_archive](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/e/ae8cef80194d9b42dee6698530f25c0f747e7443_2_690x517.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/e/ae8cef80194d9b42dee6698530f25c0f747e7443_2_690x517.png)

two_uncles_negative_exposure_ramp_gold_200_crystal_archive1920×1440 1.23 MB](/uploads/short-url/oU922nJGUM66nS3ow8h2knX2s0j.png?dl=1)

以下试条是在 Fujifilm Crystal Archive TypeII 相纸上以不同相纸曝光（和恒定的良好底片曝光）进行的虚拟冲印。

[[![two_uncles_print_exposure_ramp_gold_200_crystal_archive](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/3/135d60cb67ad1b429cf0e85dce629389ced623e1_2_690x517.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/3/135d60cb67ad1b429cf0e85dce629389ced623e1_2_690x517.png)

two_uncles_print_exposure_ramp_gold_200_crystal_archive1920×1440 1.71 MB](/uploads/short-url/2Lj8hzlLBUbVQAfl4YTfVgO07N7.png?dl=1)

原始文件来自这张 Play Raw [两个台湾叔叔在下棋](https://discuss.pixls.us/t/two-taiwanese-uncles-playing-chess/47116)，感谢 [@streetfighter](/u/streetfighter)。

## [](#p-356352-the-challenge-of-using-datasheets-4)使用数据表的挑战

已发布的数据是用密度计（RGB 或漫射）测量的，需要解混以引用每个通道独立显影的密度。如果有人感兴趣，我可以更深入地介绍我正在做的工作。这并不复杂，但我应该写下一些形式化和数学内容。大多数情况下，数据在"解混"后并不自洽，我需要应用一些合理的修正。我假设胶片在冲印时应能还原出接近中性的 18% 灰色，即使在欠曝或过曝的情况下，放大机滤镜值保持不变。到目前为止，Kodak 数据在默认情况下表现良好，而 Fujifilm 数据则更棘手，通常需要额外的修正。

以下是在不同曝光下拍摄的中性渐变虚拟冲印示例，并在虚拟冲印过程中进行了补偿以产生大致相同的曝光。首先分析 Kodak Portra 400，未修正和经过解混后。它看起来如预期般中性，只是在过曝时略带一些暖色调。

[[![gradient_exposure_ramp_portra_400_no_corrections_portra_endura](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/8/1807f6aec89f4813566acbda1bf9a6fa953a14cd_2_690x517.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/8/1807f6aec89f4813566acbda1bf9a6fa953a14cd_2_690x517.png)

gradient_exposure_ramp_portra_400_no_corrections_portra_endura1920×1440 587 KB](/uploads/short-url/3qAwjCP6888WOzUZorvQTWZbM8B.png?dl=1)

以下是 Fujifilm Pro 400h 解混后的效果。它有强烈的色调偏移，在这种状态下不太可用。可能需要进行额外的校准，但数据表中没有说明？

[[![gradient_exposure_ramp_pro_400h_uncorrected_portra_endura](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/8/1859e6b2aae15692fa2a93466cc3c304c55b9d72_2_690x517.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/8/1859e6b2aae15692fa2a93466cc3c304c55b9d72_2_690x517.png)

gradient_exposure_ramp_pro_400h_uncorrected_portra_endura1920×1440 566 KB](/uploads/short-url/3tq4rpciFg6ZkvgGtfWqdcyMbbY.png?dl=1)

在对密度特性曲线进行修正后，基准曝光下的渐变相当中性。但在极端过曝/欠曝时仍有细微偏移。

[[![gradient_exposure_ramp_pro_400h_portra_endura](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/d/3d653bfcf994d37b5cb355527f5fc087bcb23070_2_690x517.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/d/3d653bfcf994d37b5cb355527f5fc087bcb23070_2_690x517.png)

gradient_exposure_ramp_pro_400h_portra_endura1920×1440 581 KB](/uploads/short-url/8L81bZ0Hm2qB1A7mJzORpUkCp9e.png?dl=1)

# [](#p-356352-preliminary-results-5)初步结果

由于模拟胶片设计在肤色和自然绿色上表现良好，我挑选了一些彩色肖像照片来自 [100% Free Raw Photos - Download Raw Files For Editing Now](http://signatureedits.com/free-raw-photos) 进行展示（"默认" darktable 图像的文件名中包含了完整的署名信息）。

### [](#p-356352-kodak-portra-400-vs-fujifilm-pro-400h-6)Kodak Portra 400 vs Fujifilm Pro 400h

[[![Signature Edits Free Raw Files - Tag @signatureeditsco IMG_0913](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/2/52ddb2fc96f5109343071d68a322f6814a9ee4da_2_222x333.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/2/52ddb2fc96f5109343071d68a322f6814a9ee4da_2_222x333.jpeg)

Signature Edits Free Raw Files - Tag @signatureeditsco IMG_09131334×2000 990 KB](/uploads/short-url/bP48JqHX6UOvaboxaMLnWz7TZLI.jpeg?dl=1)

[[![leaves_portra_400_portra_endura_11cpl_-4y7m_0.9pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/7/0733e7e0be5f0c17d064338b473933ef6344c026_2_222x333.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/7/0733e7e0be5f0c17d064338b473933ef6344c026_2_222x333.png)

leaves_portra_400_portra_endura_11cpl_-4y7m_0.9pe1334×2000 4.34 MB](/uploads/short-url/11Iy5OlaxZc4Qsjxg10MVzsA9z8.png?dl=1)

[[![leaves_pro_400h_portra_endura_10cpl_-4y7m_0.9pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/5/f52a4fe7f32be668584e1c2b24133c22f688ee4d_2_222x333.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/5/f52a4fe7f32be668584e1c2b24133c22f688ee4d_2_222x333.png)

leaves_pro_400h_portra_endura_10cpl_-4y7m_0.9pe1334×2000 4.3 MB](/uploads/short-url/yYPDhvvqh0NFaUAbKxo0gu4Ffk1.png?dl=1)

从左到右：

(i) 使用 darktable 导出的图像，使用 sigmoid 对比度设置为 2，[xmp](/uploads/short-url/6PCT0ha8KVerrZztMR8gbeeiqz1.xmp) (13.7 KB)

(ii) Kodak Portra 400 和 Kodak Portra Endura 相纸

(iii) Fujifilm Pro 400h 和 Kodak Portra Endura 相纸

部分设置：-4Y 和 7M 放大机滤镜，0.9 相纸曝光。仿真的输入是来自 darktable 的 16bit PNG，设置与 XMP 文件相同，但 sigmoid 已停用且曝光量已减少以避免裁剪。

总体而言，Pro 400h 的绿色偏冷，对比度略高于 Portra 400。

[[![Detty Studio](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/3/a34dc3ff7a1f2d0bbfb7fda664ed9f7809f148e7_2_222x333.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/3/a34dc3ff7a1f2d0bbfb7fda664ed9f7809f148e7_2_222x333.jpeg)

Detty Studio1333×2000 1.68 MB](/uploads/short-url/niErgoyKew0e5IAxdsMNY7WmTiv.jpeg?dl=1)

[[![reds_portra_400_portra_endura_11cpl_-3y15m_1p4pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/a/1afab84ce9d2ee92edd633d45ce393c83580cee8_2_222x333.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/a/1afab84ce9d2ee92edd633d45ce393c83580cee8_2_222x333.png)

reds_portra_400_portra_endura_11cpl_-3y15m_1p4pe1333×2000 4.17 MB](/uploads/short-url/3QFzUpldHC6aJzcfNF2gjUkHWm4.png?dl=1)

[[![reds_pro_400h_portra_endura_10cpl_0y7m_1p4pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/8/e8b9b06d04e4e0de6447695dc2b2510547c5357c_2_222x333.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/8/e8b9b06d04e4e0de6447695dc2b2510547c5357c_2_222x333.png)

reds_pro_400h_portra_endura_10cpl_0y7m_1p4pe1333×2000 4.11 MB](/uploads/short-url/xcMBQ9D1nNGmwinnnATWdH5uMeo.png?dl=1)

从左到右：

(i) 使用 darktable 导出的图像，使用 sigmoid 对比度设置为 2，[xmp](/uploads/short-url/mF4v4vAsLCSWvKM0rsGInGoS7AJ.xmp) (9.7 KB)

(ii) Kodak Portra 400 和 Kodak Portra Endura 相纸

(iii) Fujifilm Pro 400h 和 Kodak Portra Endura 相纸

部分设置：Portra 400 使用 -3Y 和 15M 放大机滤镜，Pro 400h 使用 0Y -7M，1.4 相纸曝光。

[[![credit @signatureeditsco - signatureedits.com _MG_3186](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/d/4df02027342fea8db43567803c4918b944ae6c82_2_222x333.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/d/4df02027342fea8db43567803c4918b944ae6c82_2_222x333.jpeg)

credit @signatureeditsco - signatureedits.com _MG_31861333×2000 1.68 MB](/uploads/short-url/b7tenBevQffeaphozq3BBpoNTRU.jpeg?dl=1)

[[![blues_portra_400_portra_endura_11cpl_-6y10m_1pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/b/fb51facdbb8f5dd47bb0d08732e169156f4652d8_2_222x333.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/b/fb51facdbb8f5dd47bb0d08732e169156f4652d8_2_222x333.png)

blues_portra_400_portra_endura_11cpl_-6y10m_1pe1332×2000 4.31 MB](/uploads/short-url/zRhu7lQ4fQD8oNSwnL4gLIq70Ok.png?dl=1)

[[![blues_pro_400h_portra_endura_10cpl_-6y10m_1pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/4/7469a5d3b9e4ba53e1ba6a3ade9c400f25be356c_2_222x333.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/4/7469a5d3b9e4ba53e1ba6a3ade9c400f25be356c_2_222x333.png)

blues_pro_400h_portra_endura_10cpl_-6y10m_1pe1332×2000 4.24 MB](/uploads/short-url/gBPJCDASt4l5EmymTpsygbRiyao.png?dl=1)

从左到右：

(i) 使用 darktable 导出的图像，使用 sigmoid 对比度设置为 2，[xmp](/uploads/short-url/75o1ToNGhPeN57XHMmqE8z0bt5p.xmp) (9.6 KB)

(ii) Kodak Portra 400 和 Kodak Portra Endura 相纸

(iii) Fujifilm Pro 400h 和 Kodak Portra Endura 相纸

部分设置：-6Y 和 10M 放大机滤镜，1.0 相纸曝光。

Pro 400h 的蓝色调与 Portra 400 相比更偏冷色。

<details>
<summary>
色卡对比 (Kodak Portra 400 vs Fujifilm Pro 400h)</summary>

[[![cc2005_kodak_portra_400_auc_kodak_portra_endura_uc](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/8/381c3967edfcdda21424ba9718c9cea2a155f51f_2_690x492.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/8/381c3967edfcdda21424ba9718c9cea2a155f51f_2_690x492.png)

cc2005_kodak_portra_400_auc_kodak_portra_endura_uc2100×1500 136 KB](/uploads/short-url/80ncVuz3v4mY7tOoekczakrZwKP.png?dl=1)

[[![cc2005_fujifilm_pro_400h_auc_kodak_portra_endura_uc](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/6/f6f02dadde665994a5164d2d54ff4af37a21664b_2_690x492.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/6/f6f02dadde665994a5164d2d54ff4af37a21664b_2_690x492.png)

cc2005_fujifilm_pro_400h_auc_kodak_portra_endura_uc2100×1500 135 KB](/uploads/short-url/zew2kJGL9R8PUsSulQ8JS4TaPk7.png?dl=1)

在色卡中，外方块显示 sRGB 输入（场景参照），内方块是模拟冲印。相纸曝光大致针对 Neutral 5 色块平衡。

</details>

### [](#p-356352-consumer-print-papers-7)消费级相纸

[[![leaves_portra_400_crystal_archive_typeii_11cpl_-2y1m_0.9pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/4/a48dd25901b177272520012d98d5c70e81209dd3_2_222x333.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/4/a48dd25901b177272520012d98d5c70e81209dd3_2_222x333.png)

leaves_portra_400_crystal_archive_typeii_11cpl_-2y1m_0.9pe1334×2000 4.42 MB](/uploads/short-url/ntI9IhCnzijX6HRJOAGioJRa5P5.png?dl=1)

[[![leaves_portra_400_ektacolor_edge_11cpl_-2y0m_0.9pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/6/66a30b6c3369d4ae02eedef88b27562cf5a12625_2_222x333.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/6/66a30b6c3369d4ae02eedef88b27562cf5a12625_2_222x333.png)

leaves_portra_400_ektacolor_edge_11cpl_-2y0m_0.9pe1334×2000 4.38 MB](/uploads/short-url/eDY1seaVK7t8MG1uJS2E1z8uJJr.png?dl=1)

[[![leaves_portra_400_endura_premier_11cpl_-2y3m_0.9pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/b/eb295838aa352278ce5833a36f3b04fb245fa7e5_2_222x333.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/b/eb295838aa352278ce5833a36f3b04fb245fa7e5_2_222x333.png)

leaves_portra_400_endura_premier_11cpl_-2y3m_0.9pe1334×2000 4.5 MB](/uploads/short-url/xykMJjXB0zDlp0o3kMPbgq0V4i1.png?dl=1)

从左到右：

(i) Kodak Portra 400 和 Fujifilm Crystal Archive TypeII 相纸（伽马因子 1.1）

(ii) Kodak Portra 400 和 Kodak Ektacolor Edge 相纸

(iii) Kodak Portra 400 和 Kodak Endura Premier 相纸

请记住，饱和度水平是随意猜测的，可以通过降低胶片中 DIR 成色剂的浓度来全局降低所有冲印的饱和度。

<details>
<summary>
色卡对比 (消费级相纸)</summary>

[[![cc2005_kodak_portra_400_auc_fujifilm_crystal_archive_typeii_uc](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/1/414a156700db5b2f77bee7e703198986af0324e2_2_690x492.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/1/414a156700db5b2f77bee7e703198986af0324e2_2_690x492.png)

cc2005_kodak_portra_400_auc_fujifilm_crystal_archive_typeii_uc2100×1500 135 KB](/uploads/short-url/9jzL3sXZcQtOsJHW37C7j99DKUy.png?dl=1)

[[![cc2005_kodak_portra_400_auc_kodak_ektacolor_edge_uc](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/e/fed761c4df7386b2b20042fc2e5f3d15cea4bcc8_2_690x492.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/e/fed761c4df7386b2b20042fc2e5f3d15cea4bcc8_2_690x492.png)

cc2005_kodak_portra_400_auc_kodak_ektacolor_edge_uc2100×1500 135 KB](/uploads/short-url/AmqJknFaTpVrl4MGYAlxY5Z3gAU.png?dl=1)

[[![cc2005_kodak_portra_400_auc_kodak_endura_premier_uc](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/c/1cae9a9dc28004b862b3e97274478d9cf4951cb1_2_690x492.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/c/1cae9a9dc28004b862b3e97274478d9cf4951cb1_2_690x492.png)

cc2005_kodak_portra_400_auc_kodak_endura_premier_uc2100×1500 137 KB](/uploads/short-url/45JsiBow5svh4xk8NaT3wZ6A91L.png?dl=1)

外方块显示 sRGB 输入（场景参照），内方块是模拟冲印。相纸曝光大致针对 Neutral 5 色块平衡。

</details>

### [](#p-356352-other-film-stocks-8)其他胶片类型

[[![tag @ryanbreitkreutz - free raws from @signatureeditsco DSC01513](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/3/a3cc2d517e8fec0595f667c849d4ee42f6df3cf1_2_222x333.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/3/a3cc2d517e8fec0595f667c849d4ee42f6df3cf1_2_222x333.jpeg)

tag @ryanbreitkreutz - free raws from @signatureeditsco DSC015131330×2000 1.63 MB](/uploads/short-url/nn1h2SchrXFizcLFtqZJX9ocAJX.jpeg?dl=1)

[[![windows_portra_400_crystal_archive_typeii_1p1gamma_1p1cpl_-1y1m_105pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/5/c5fd6aead26e9c86eb9d9c98728788f4755f44d2_2_222x333.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/5/c5fd6aead26e9c86eb9d9c98728788f4755f44d2_2_222x333.png)

windows_portra_400_crystal_archive_typeii_1p1gamma_1p1cpl_-1y1m_105pe1330×2000 4.73 MB](/uploads/short-url/sfv0oUovJCesJKMKTxX0iihyG3M.png?dl=1)

[[![windows_pro_400h_crystal_archive_typeii_1p1gamma_10cpl_-1y1m_105pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/0/b014d2b7967788abb65d8da8dc73748894deea0f_2_222x333.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/0/b014d2b7967788abb65d8da8dc73748894deea0f_2_222x333.png)

windows_pro_400h_crystal_archive_typeii_1p1gamma_10cpl_-1y1m_105pe1330×2000 4.68 MB](/uploads/short-url/p7GEblRSAVdL5zUh3I84JxX4t7V.png?dl=1)

[[![windows_vision3_50d_crystal_archive_typeii_1p1gamma_1p1cpl_-1y1m_105pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/c/dc7b07b777e2dfc6bea93bfa5b0bdc8eeeab4438_2_222x333.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/c/dc7b07b777e2dfc6bea93bfa5b0bdc8eeeab4438_2_222x333.png)

windows_vision3_50d_crystal_archive_typeii_1p1gamma_1p1cpl_-1y1m_105pe1330×2000 4.62 MB](/uploads/short-url/vssDkuX3OfNd7pULXN5dqlTn7cs.png?dl=1)

[[![windows_gold_200_crystal_archive_typeii_1p1gamma_1p1cpl_-1y1m_105pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/9/894cfb60658079d2036b4e7e8ba5984645bbf10a_2_222x333.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/9/894cfb60658079d2036b4e7e8ba5984645bbf10a_2_222x333.png)

windows_gold_200_crystal_archive_typeii_1p1gamma_1p1cpl_-1y1m_105pe1330×2000 4.7 MB](/uploads/short-url/jACltVPm2qYlzd6S0JC3Ljb85nk.png?dl=1)

[[![windows_c200_crystal_archive_typeii_1p1gamma_1p1cpl_-1y1m_105pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/6/568751978ac4f4faa5b5f346e4eef085f0bcdc0e_2_222x333.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/6/568751978ac4f4faa5b5f346e4eef085f0bcdc0e_2_222x333.png)

windows_c200_crystal_archive_typeii_1p1gamma_1p1cpl_-1y1m_105pe1330×2000 4.74 MB](/uploads/short-url/clsYQNeYCf4ucfmAUaH9GiuWqjY.png?dl=1)

从左到右，从上到下：

(i) 使用 darktable 导出的图像，使用 sigmoid 对比度设置为 2，[xmp](/uploads/short-url/yNa5ydEkOZssonVMEcL5AoyNN4e.xmp) (8.2 KB)

(ii) Kodak Portra 400

(iii) Fujifilm Pro 400h

(iv) Kodak Vision3 50d

(v) Kodak Gold 200

(vi) Fujifilm C200

全部在 Fujifilm Crystal Archive TypeII 上冲印，使用 -1Y 1M 放大机滤镜，1.1 相纸伽马因子，1.05 相纸曝光。

<details>
<summary>
色卡对比 (多种底片在 Fujifilm Crystal Archive TypeII 上)</summary>

[[![cc2005_kodak_portra_400_auc_fujifilm_crystal_archive_typeii_uc](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/1/414a156700db5b2f77bee7e703198986af0324e2_2_690x492.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/1/414a156700db5b2f77bee7e703198986af0324e2_2_690x492.png)

cc2005_kodak_portra_400_auc_fujifilm_crystal_archive_typeii_uc2100×1500 135 KB](/uploads/short-url/9jzL3sXZcQtOsJHW37C7j99DKUy.png?dl=1)

[[![cc2005_fujifilm_pro_400h_auc_fujifilm_crystal_archive_typeii_uc](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/2/42d916d616acfa367580554719554ca7d2575e40_2_690x492.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/2/42d916d616acfa367580554719554ca7d2575e40_2_690x492.png)

cc2005_fujifilm_pro_400h_auc_fujifilm_crystal_archive_typeii_uc2100×1500 133 KB](/uploads/short-url/9xmCIFHPWPw8z2Nx5TjAPidaDQc.png?dl=1)

[[![cc2005_kodak_vision3_50d_uc_fujifilm_crystal_archive_typeii_uc](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/e/7e699fd0a0393adafacb6c0f8ee761df5f87c930_2_690x492.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/e/7e699fd0a0393adafacb6c0f8ee761df5f87c930_2_690x492.png)

cc2005_kodak_vision3_50d_uc_fujifilm_crystal_archive_typeii_uc2100×1500 136 KB](/uploads/short-url/i2isxbF7cuw2HsDO6FUQ3BMAyzK.png?dl=1)

[[![cc2005_kodak_gold_200_auc_fujifilm_crystal_archive_typeii_uc](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/1/c1536254cfda57b8b4ca0ff6b583128132e2db99_2_690x492.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/1/c1536254cfda57b8b4ca0ff6b583128132e2db99_2_690x492.png)

cc2005_kodak_gold_200_auc_fujifilm_crystal_archive_typeii_uc2100×1500 135 KB](/uploads/short-url/rAeNGF6P5ZXthldnYoZezfKvann.png?dl=1)

[[![cc2005_fujifilm_c200_auc_fujifilm_crystal_archive_typeii_uc](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/b/abf1f9341905edc464fb273a6bc4aa3232e29030_2_690x492.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/b/abf1f9341905edc464fb273a6bc4aa3232e29030_2_690x492.png)

cc2005_fujifilm_c200_auc_fujifilm_crystal_archive_typeii_uc2100×1500 133 KB](/uploads/short-url/ox64xhEMNjt6chjYitTKqOeRphS.png?dl=1)

外方块显示 sRGB 输入（场景参照），内方块是模拟冲印。相纸曝光大致针对 Neutral 5 色块平衡。

</details>

Kodak Portra 400 和 Gold 200 有相似的特性，但 Portra 的色调更柔和（粉彩效果）。Vision3 50d 更中性和平坦。Pro 400h 和 C200 也类似，但比 Kodak 更饱和。

更多结果可在我的 Play Raw 历史记录中找到（[Profile - arctic - discuss.pixls.us](https://discuss.pixls.us/u/arctic/activity)），并非所有质量都好。大部分进展发生在假期期间，所以早期的作品可能看起来有些奇特。以下是另外一些与 darktable 基础编辑的对比（同样使用 sigmoid 对比度设置为 2）。

[[![Copy of MonumentValley-tag@christianbmeza - from signatureedits.com](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/6/b6cd44b07a45db2f8ec7ef5ae7d9c6b6ff00e513_2_690x461.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/6/b6cd44b07a45db2f8ec7ef5ae7d9c6b6ff00e513_2_690x461.jpeg)

Copy of MonumentValley-tag@christianbmeza - from signatureedits.com2000×1338 1.42 MB](/uploads/short-url/q58Gt0cqwVuewQW9u4bOj22FAxJ.jpeg?dl=1)

[[![desert_fujifilm_c200_supra_endura_1stops_09pe_-4Y2M](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/5/551749c91a82b9ec67ec3768221f6aa7665ee627_2_690x461.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/5/551749c91a82b9ec67ec3768221f6aa7665ee627_2_690x461.png)

desert_fujifilm_c200_supra_endura_1stops_09pe_-4Y2M2000×1338 4.19 MB](/uploads/short-url/c8KtKgXp00PMa13wJGAsqTw42zB.png?dl=1)

上面是 darktable 使用 sigmoid 的输出，下面是 Fujifilm C200 和 Kodak Supra Endura 相纸的仿真结果，+1 档曝光补偿，0.9 相纸曝光，-4Y 2M 滤镜。

[[![Copy of DSC_2070 - from signatureedits.com](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/0/f04cc9dc25ac3e9fc30eba75c6c62187b8eddb3f_2_690x460.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/0/f04cc9dc25ac3e9fc30eba75c6c62187b8eddb3f_2_690x460.jpeg)

Copy of DSC_2070 - from signatureedits.com2000×1335 1010 KB](/uploads/short-url/yhN6ULTGF5Xe8tWBcrwYfDKlMGX.jpeg?dl=1)

[[![portrait_leaves_kodak_portra_fuji_crystal_archiveii_1ev_065pe_-3Y-4M_11cpl](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/f/4f05d8c65f507ee8b879c32dd07854913ab5464a_2_690x460.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/f/4f05d8c65f507ee8b879c32dd07854913ab5464a_2_690x460.png)

portrait_leaves_kodak_portra_fuji_crystal_archiveii_1ev_065pe_-3Y-4M_11cpl2000×1335 4.24 MB](/uploads/short-url/bh4fiNQtWnBUJN6OZCTLBMOcI0q.png?dl=1)

上面 darktable 输出，下面使用 Kodak Portra 400 和 Fujifilm Crystal Archive TypeII 仿真，+1 档曝光补偿，0.65 相纸曝光，-3Y -4M 滤镜。

# [](#p-356352-grain-9)颗粒

仿真为每个通道构建了三个子层，模仿现代彩色负片，其中每个彩色层由 2-3 个具有不同感光度的子层组成，以增加宽容度。每个层和子层的随机特性通过考虑更快的层（即具有更大颗粒）具有更多噪点来模拟。

[[![grain_particle_area_ramp_portra_400_portra_endura](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/3/43692319e93252fb32a5ed7724dee5a47e0649b8_2_690x517.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/3/43692319e93252fb32a5ed7724dee5a47e0649b8_2_690x517.png)

grain_particle_area_ramp_portra_400_portra_endura1920×1440 2.48 MB](/uploads/short-url/9ClfeEGhSqOHzUk8lEqWmmAb2RO.png?dl=1)

以上是 Kodak Portra 400 在 Kodak Portra Endura 上冲印的几条试条，垂直尺寸为 1 mm。虚拟卤化银颗粒（后转化为染料云）的平均颗粒面积发生了变化。近似地，颗粒面积应与 ISO 大致成正比。在消费级胶片中，颗粒直径范围约为 0.2 - 2 微米，即 0.03-3.2 平方微米。

[[![grain_chart_datasheet_kodak_vision3_50d](https://d2x313g9lpht1q.cloudfront.net/original/3X/1/8/1871ee67d3fbc37d4ba3d4027588b45d8642cd05.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/1/8/1871ee67d3fbc37d4ba3d4027588b45d8642cd05.png)

grain_chart_datasheet_kodak_vision3_50d646×584 30.7 KB](/uploads/short-url/3ufysW4gDcBPNGPg1GLgtBPJCgB.png?dl=1)

[[![grain_chart_kodak_vision3_50d](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/e/aeafb5188d4bcf6fefd91e7ced45b1c9e0ccdd3a_2_350x270.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/e/aeafb5188d4bcf6fefd91e7ced45b1c9e0ccdd3a_2_350x270.png)

grain_chart_kodak_vision3_50d1920×1440 265 KB](/uploads/short-url/oVlwW58UdDePVuZ2AEOmvw8dVeq.png?dl=1)

左边是我能找到的唯一此类数据——来自 Kodak Vision3 50d（其他 Vision3 也有）。右边是同一胶片类型的仿真中虚拟测量的相同数据，颗粒参数相应调整。通过处理中性渐变的虚拟照片，计算每个曝光下的标准差并绘制图表。从峰值可以大致看出每个通道的子层结构。

以下是 Kodak Portra 400 和 Kodak Portra Endura 的高放大倍率裁剪示例。

[[![lowres_portra](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/0/e0f6c228831c0fee83666fa0df648f1280f526a1_2_666x1000.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/0/e0f6c228831c0fee83666fa0df648f1280f526a1_2_666x1000.png)

lowres_portra1332×1999 3.73 MB](/uploads/short-url/w67D76nGiuXIxd5pb4T2eqTJNLP.png?dl=1)

[[![print_016](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/8/9808ce9f0b9674417f6962480e6b0e0ba31d6a15_2_340x340.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/8/9808ce9f0b9674417f6962480e6b0e0ba31d6a15_2_340x340.png)

print_016901×901 1.39 MB](/uploads/short-url/lGXrzhOgvdvUEGAuGN0OByw68h7.png?dl=1)

[[![neg_016](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/b/5b241b0ff27620f1a7f970dcfc0d1ec3e71ea118_2_340x340.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/b/5b241b0ff27620f1a7f970dcfc0d1ec3e71ea118_2_340x340.png)

neg_016901×901 950 KB](/uploads/short-url/d0gNY2Bl8rCEVEM3DoxxiFAmeec.png?dl=1)

[[![print_004](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/7/675e65395d0cc0b279a4051a2d0b910a946fb105_2_340x340.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/7/675e65395d0cc0b279a4051a2d0b910a946fb105_2_340x340.png)

print_004900×900 1.32 MB](/uploads/short-url/eKrq56jmOwra0tiYkjmGWkUAeCV.png?dl=1)

[[![neg_004](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/5/45bb8ebe2da5a295aee9213e36876cf99f58d52d_2_340x340.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/5/45bb8ebe2da5a295aee9213e36876cf99f58d52d_2_340x340.png)

neg_004900×900 1.14 MB](/uploads/short-url/9WSMIoynEfx4hKleDyBm0iQqqrb.png?dl=1)

[[![print_001](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/a/ba98cd284037eeba637049ae30339370d8eafe3a_2_340x340.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/a/ba98cd284037eeba637049ae30339370d8eafe3a_2_340x340.png)

print_001896×896 985 KB](/uploads/short-url/qCIbt4IKnJz7w3gJfRagnrp2EMq.png?dl=1)

[[![neg_001](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/c/fc6661c7214e7eede7391af9148c2881888b2a1b_2_340x340.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/c/fc6661c7214e7eede7391af9148c2881888b2a1b_2_340x340.png)

neg_001896×896 958 KB](/uploads/short-url/A0PFQ9AdMRstQ1bNKcca21HC9gT.png?dl=1)

左边是冲印效果，右边是底片的虚拟扫描。在高放大倍率下，孤立的染料云变得可见。最高放大倍率的裁剪区域大小为 0.35x0.35 mm，相当于 5.4 十亿像素的图像。我想我们可以用它打印一张非常大的海报。

# [](#p-356352-saturation-with-dir-couplers-10)使用 DIR 成色剂的饱和度控制

底片的饱和度水平通过显影抑制剂释放型成色剂（DIR couplers）控制。当一个层中形成大量密度时，DIR 成色剂被释放，可以抑制附近区域（同一层和相邻层）的密度形成。DIR 成色剂在相邻层中的扩散产生增加的饱和度（其他通道密度降低，即更纯净的颜色），这也称为层间效应。

以下是来自 [signatureedits.com](http://signatureedits.com) 原始文件的几个示例，使用 Fujifilm C200 和 Fujifilm Crystal Archive TypeII。

[[![dir_couplers_ramp_car_fuji_c200_crystal_archive](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/e/6ecd03d18eb73cbed57a2c323e27082300bc4fd6_2_690x517.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/e/6ecd03d18eb73cbed57a2c323e27082300bc4fd6_2_690x517.png)

dir_couplers_ramp_car_fuji_c200_crystal_archive1920×1440 1.7 MB](/uploads/short-url/fObLnvWtHVT7M5FfA6Fr3xULBS6.png?dl=1)

曝光补偿 +1 档，0.65 相纸曝光，0Y 15M 滤镜偏移。Fujifilm 底片倾向于产生非常饱和的红色，尤其是在较高的 DIR 成色剂用量下。我发现合理的值范围是 0.8-1.2。

[[![dir_couplers_ramp_temple_fuji_c200_crystal_archive](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/9/992f67c8e71244303e3b4032c33b2f30403dac61_2_690x517.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/9/992f67c8e71244303e3b4032c33b2f30403dac61_2_690x517.png)

dir_couplers_ramp_temple_fuji_c200_crystal_archive1920×1440 2.52 MB](/uploads/short-url/lR8ClTCCIioADhJPtRzz10va7wB.png?dl=1)

曝光补偿 +2 档，0.6 相纸曝光，0Y 0M 滤镜偏移。

[[![desert_kodak_gold_endura_premier_0cpl_09pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/5/9558d567aeba8367c158ba4e42cd4fe42bc47964_2_690x460.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/5/9558d567aeba8367c158ba4e42cd4fe42bc47964_2_690x460.png)

desert_kodak_gold_endura_premier_0cpl_09pe2000×1334 4.98 MB](/uploads/short-url/ljbt1TFGv1ztDwj1N3YmJKQ5heA.png?dl=1)

[[![desert_kodak_gold_endura_premier_1cpl_09pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/d/2d22f867d1a4983962ac7614839cea4f54d295bd_2_690x460.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/d/2d22f867d1a4983962ac7614839cea4f54d295bd_2_690x460.png)

desert_kodak_gold_endura_premier_1cpl_09pe2000×1334 5.01 MB](/uploads/short-url/6ripp8BV0No6aBr2GUcpHXdJZPD.png?dl=1)

在这张沙漠照片示例中，上图没有使用 DIR 成色剂，下图使用了 1.0 的 DIR 成色剂用量。使用 Kodak Gold 200、Kodak Endura Premier 和 0.9 相纸曝光。

# [](#p-356352-halation-11)光晕效应

有了基于物理的模型，我们可以在流程的正确阶段以模糊的形式引入光晕效应。通常红色通道是受影响最大的，因为它位于胶片堆叠的背面。部分光线穿过乳剂层和支撑材料，然后被反射回来，产生模糊，再次曝光乳剂。例如，添加 3% 的红色、0.3% 的绿色和 0.1% 的蓝色模糊光晕光，sigma 为 200 微米，得到以下结果。

[[![halation_dots](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/b/9b88a7383a7f51a0efcbfb6b278bcc66846cfc61_2_690x115.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/b/9b88a7383a7f51a0efcbfb6b278bcc66846cfc61_2_690x115.png)

halation_dots3000×500 1.52 MB](/uploads/short-url/mbUMJAGrMvwTh81yfegHLASLYs1.png?dl=1)

在这张测试图像中，每个点的曝光增加 1 档。到达最右边的点时，总共增加了 14 档。这张图片的长边尺寸为 35 mm。

[[![armchair_vision3_crystal_archive_0halation_-4Y5M_3ev_04pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/5/a5317b8084975f5fb79ebcadc4bd0b09cb9d707a_2_690x460.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/5/a5317b8084975f5fb79ebcadc4bd0b09cb9d707a_2_690x460.jpeg)

armchair_vision3_crystal_archive_0halation_-4Y5M_3ev_04pe4000×2672 608 KB](/uploads/short-url/nzmNuraycwCPW3flndOLTs98jh0.jpeg?dl=1)

[[![armchair_vision3_crystal_archive_8halation_-4Y5M_3ev_04pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/d/3d0c3178b4836063d85bc7975c53f93e785c1bfe_2_690x460.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/d/3d0c3178b4836063d85bc7975c53f93e785c1bfe_2_690x460.jpeg)

armchair_vision3_crystal_archive_8halation_-4Y5M_3ev_04pe4000×2672 598 KB](/uploads/short-url/8I3ftvgl9ZJA7uNbHmPB0AXt2xM.jpeg?dl=1)

在此示例中，上方没有光晕，下方红色通道有 8% 的光晕。使用 Kodak Vision3 模拟 Cinestill，在 Fujifilm Crystal Archive Type II 上冲印，放大机滤镜 -4Y 5M，+3 档曝光补偿和 0.4 相纸曝光。原始文件来自 [signatureedits.com](http://signatureedits.com)。

[[![tree_branches_kodak_gold_200_crystal_archive_preflash005_4Y10M_04pe_2ev_halation0](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/4/044d83f86aaf9984eaa20df0b3c86d2f258e8018_2_340x460.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/4/044d83f86aaf9984eaa20df0b3c86d2f258e8018_2_340x460.png)

tree_branches_kodak_gold_200_crystal_archive_preflash005_4Y10M_04pe_2ev_halation01440×1920 5.82 MB](/uploads/short-url/C3Z8xVPO9Um47b2CcvFEoGXZAA.png?dl=1)

[[![tree_branches_kodak_gold_200_crystal_archive_preflash005_4Y10M_04pe_2ev_halation3](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/d/0d967fd7160c667b203679832d914c72e4407296_2_340x460.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/d/0d967fd7160c667b203679832d914c72e4407296_2_340x460.png)

tree_branches_kodak_gold_200_crystal_archive_preflash005_4Y10M_04pe_2ev_halation31440×1920 5.75 MB](/uploads/short-url/1WcEkGbcLqBS9rEkOEONCWT5Ufc.png?dl=1)

另一个光晕更微妙的例子，来自一张 Play Raw [Nice day for a nap under a tree](https://discuss.pixls.us/t/nice-day-for-a-nap-under-a-tree/43635)，感谢 [@lphilpot](/u/lphilpot)。注意背光树枝周围的暖色光晕。右侧图像使用 3% 红光光晕。Kodak Gold 200 和 Fujifilm Crystal Archive TypeII，+2 档，0.4 相纸曝光。

# [](#p-356352-wanna-try-it-12)想试试吗？

你可以在 GitHub 仓库 [agx-emulsion](https://github.com/andreavolpato/agx-emulsion) 找到更多技术信息。如果你有冒险精神，可以安装它。请记住，我更像是一名科学家而非开发者，所以不要期望太高。我将这个项目视为对胶片仿真模型的探索，代码仍然相当混乱，绝不是生产级代码。这里的所有照片都是使用 [v0.1.0](https://github.com/andreavolpato/agx-emulsion/releases/tag/v0.1.0-alpha) 版本创建的。

# [](#p-356352-some-issues-13)一些问题

- 流程最开始的 RGB 到光谱转换使用了 [4] 方法，非常简单，但要求输入图像转换为 sRGB。我确信有更好的方法。如果有人有建议，将非常感激。[@hanatos](/u/hanatos) 如果我没记错，你有一些关于这个主题的论文？
  [![:grin:](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)
- 它是用 Python 编写的，速度相当慢（2K 图像需要很多秒）。临时 GUI 没有色彩管理，只是一个用于交互的占位符。此外，它有很多参数，可能会让人非常困惑。
- 你的意见可能最重要。根据我使用的数据，我猜测仿真的准确度大约在 60-85% 或更高，但这并不能说明什么。
  [![:smiley:](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)
  任何关于如何与现实结果进行比较的建议都欢迎。有能用肉眼判断的胶片色彩专家吗？
  [![:nerd_face:](https://discuss.pixls.us/images/emoji/apple/nerd_face.png?v=12)](https://discuss.pixls.us/images/emoji/apple/nerd_face.png?v=12)

> 最终，我的目标是完善模型及其配置文件，然后在某些帮助下使其在高效的 GPU 代码上运行，比如 vkdt。我将把这个帖子用作日志本，记录一些更新，希望能保持动力。如果这个项目足够新颖，我可能还想发表一篇科学论文/做一次演示。

## [](#p-356352-references-14)参考文献

[1] Giorgianni, Madden, Digital Color Management, 第2版, 2008 Wiley

[2] Hung, The Reproduction of Color, 第6版, 2004 Wiley

[3] Jakobson, Ray, Attridge, Axford, The Manual of Photography, 第9版, 2000 Focal Press

[4] Mallett, Yuksel, Spectral Primary Decomposition for Rendering with sRGB Reflectance, Eurographics Symposium on Rendering - DL-only and Industry Track, 2019, doi:10.2312/SR.20191216

---

## #2 **Bastian Bechtold** (@bastibe) · 2025-02-09 21:37

这太迷人了！非常感谢你的这篇文章和分享的代码！

我不会假装理解其中的化学原理。但你关于彩色分级曲线和 DIR 成色剂的提示已经提供了非常值得思考的内容，我一定会深入研究的。

---

## #3 **jo** (@hanatos) · 2025-02-10 07:45

哇，太酷了！感谢你发布这个惊人的工作成果和这篇文章！再次强调，你在这里呈现的图像质量是我以前在数字流程中从未见过的，我认为这展现了对该主题全新的尊重。我会更详细地研究它，并且非常有意愿将你的代码移植到 GPU 上

[![:smiley:](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)

会有很多问题……我已经在想你是如何用 sRGB 光谱上采样来处理的……

---

## #4 **Andrea** (@arctic) · 2025-02-10 09:51

掩蔽成色剂也是现代彩色胶卷工作方式中相当有趣的一部分。我一直对未曝光显影胶片片基的强烈颜色感到困惑。事实证明，这不仅仅是化学反应的副产品，它还有功能性作用。这是一种颜色掩膜，随着曝光增加而密度降低。这用来平衡层中形成的 CMY 主染料的非期望吸收。相当于给染料增加了一种"负吸收"（相对于片基）。

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/f/4/f403021fcdfd95c28f381d31e17f34360dfc6d10.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/f/4/f403021fcdfd95c28f381d31e17f34360dfc6d10.jpeg)

image635×613 70.4 KB](/uploads/short-url/yOCWMfYgX8OJI7nCVUIwuCOav04.jpeg?dl=1)

这是我在谷歌搜索"masking couplers"时找到的一段摘录，解释得比其他来源更好，Hunt 书中的图片比较复杂。据说也来自这个论坛 [pdf link](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/c/ccc6c05a897732c28c5c396120ce83eb7b5c5194.pdf)，但不清楚来自哪个讨论。

---

## #5 **Andrea** (@arctic) · 2025-02-10 10:02

当然，我很乐意讨论更多！

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

> **@hanatos** (帖子 #3):
> 已经 wondering how you'd get away with sRGB spectral upsampling…

胶片层的感光度光谱相当宽且光谱分离。这可能部分原因是输入不那么关键。但我仍然不太了解这个步骤的细微差别。

> **@hanatos** (帖子 #3):
> 你在这里展示的图像质量是我在数字流程中从未见过的

我认为使用全吸收光谱流程和受密度抑制启发的饱和度增强（模仿层间效应），可能有助于解释为什么图像看起来非常"浓郁"并具有胶片色彩。深入探讨这个问题的根源并更好地归纳概括可能会很有趣。

---

## #6 **jo** (@hanatos) · 2025-02-10 10:26

好吧，我快速看了一下代码，但我不会说 Python 来拯救我的祖母

[![:smiley:](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)

几个问题：

你有张量图收缩，太酷了！你用了多少个光谱波段？我们有内存问题吗？

如果我没理解错，这里的光谱量是某些染料/显影颗粒等的*密度*。我的意思是，这些是 <span class="math">[0,\infty)</span>，而不是透射率/颜色那样的 <span class="math">[0,1]</span>，对吧？但即使有抑制剂也永远不会为负？

平滑光谱很好，它们可以很好地压缩。选择合适的表示对于高效实现可能很重要。

是的，我想我可以提供各种可能和不可能的光谱上采样方法的代码。

---

## #7 **Andrea** (@arctic) · 2025-02-10 13:52

> **@hanatos** (帖子 #6):
> 你用了多少个光谱波段？我们有内存问题吗？

我使用的光谱范围是 380-780 nm，步长 5 nm。可能有点过度，但我观察了光谱，目测步长以确保不过度破坏峰值。10 nm 的步长在创建配置文件时的解混/拟合中看起来太粗糙了。实际仿真的输出可能没有那么敏感。它在 `agx_emulsion/config.py` 中的 `SPECTRAL_SHAPE = colour.SpectralShape(380, 780, 5)` 常量中配置。目前还没有测试过更改它。配置文件在这种情况下需要重新计算。

这是计算中使用的实际光谱和曲线示例：

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/9/e9d48b6352bfda17e814a52d7fdf73529ddb7dd0_2_690x229.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/9/e9d48b6352bfda17e814a52d7fdf73529ddb7dd0_2_690x229.png)

image1200×400 64.7 KB](/uploads/short-url/xmyCKMb7j7EnYYdrOG8VI6rQsLK.png?dl=1)

左侧曲线是层的有效吸收；中心曲线是对数曝光到密度的转换，然后通过右侧的 CMY 光谱缩放，得到每个像素的最终密度光谱。这同时适用于底片和相纸。

对于较大的图像，我确实有内存问题。目前，我完全没有针对内存进行优化。

[![:grin:](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)

我主要专注于模型的"质量"。

> **@hanatos** (帖子 #6):
> 如果我没理解错，这里的光谱量是某些染料/显影颗粒等的密度。

有密度（与染料量成正比，也与透射率相关）和曝光（吸收/透射的光量等，代码中有时称为 `raw`）。两者都是正数且无上界。在特性密度曲线的插值和抑制剂计算中，曝光以 log10(曝光) 的形式使用，或称为 `log_raw`，范围为 <span class="math">(-\infty, \infty)</span>。

以下是 `emulsion.py` 中胶片部分的核心代码：

```
log_raw = np.log10(raw + 1e-10)
density_cmy = self._interpolate_density_with_curves(log_raw)
density_cmy = self._apply_density_correction_dir_couplers(density_cmy, log_raw, pixel_size_um)
density_cmy = self._apply_grain(density_cmy, pixel_size_um, compute_reference_exposure)
density_spectral = self._compute_density_spectral(density_cmy)

```

每个像素中的 CMY 密度（非光谱，`density_cmy` 有三个通道）通过分段随机的方式进行"分块"以生成颗粒，使用泊松/二项式随机数。

---

## #8 **Jakob Andrén** (@jandren) · 2025-02-10 15:29

太喜欢了！

我在研究 sigmoid 模块时就想学习这些内容，特别是关于更好处理宽色域的方法，但没能找到像你这样的好资源。我会抽时间阅读这些资料并尝试你的成果。期待跟进你的进展。

---

## #9 **Daniel, who likes dt and digikam** (@DanielLikesDT) · 2025-02-10 21:16

我也成功运行了你的软件（我在 pycharm / matplotlib 中遇到问题，不得不将 img 文件夹复制到 gui 文件夹中）——这很棒！我只能测试你的颗粒效果，必须说：这是一种非常平滑的颗粒。不错。

如果你需要有人测试功能或做些简单的工作（我懂一点点 Python），我很乐意帮忙。这看起来非常有前景。

---

## #10 **Andrea** (@arctic) · 2025-02-11 00:14

嘿 [@jandren](/u/jandren)！很高兴听到你对此感兴趣。

我可以添加一些图表，可能会引发讨论，或者至少触发一些思考。

网上有时你可以找到针对"压力测试图像"测试的 LUT。对于 sRGB 输入，经常使用这个（[3dlutcreator 链接](https://3dlutcreator.com/3d-lut-creator---materials-and-luts.html)）：

[[![cc05](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/b/1bb1926201ac71ef9a682c974e15d8f0d0fa92f2_2_200x100.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/b/1bb1926201ac71ef9a682c974e15d8f0d0fa92f2_2_200x100.png)

cc051000×500 454 KB](/uploads/short-url/3WZkVwGlxx4MzSWNr280TayBq0i.png?dl=1)

我不太喜欢它，因为它一开始就不太平滑。但让我们来看看。

只取左方块（实际上只取图像的几列）并在色度图中绘制，得到以下结果。

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/d/7/d733c953565f2e8a4c3a7401fea5d7db99ccee61.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/d/7/d733c953565f2e8a4c3a7401fea5d7db99ccee61.png)

image630×628 69.3 KB](/uploads/short-url/uHLBHmUb33HQsmG4wKlUsOK7Eyt.png?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/d/f/dfd14008653d3acc4c0c3d86e6cf03c61310c051.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/d/f/dfd14008653d3acc4c0c3d86e6cf03c61310c051.jpeg)

image389×389 20.1 KB](/uploads/short-url/vVYN7nrQ9dxxVQYnOwlaq2nCkLv.jpeg?dl=1)

所有 sRGB 的极限值都达到了。压力测试图像的下部在色域边缘运行，而上部则去饱和并趋向 D65 白点。

我很好奇色度图在仿真后会被如何映射。压力测试图像不是场景参照的，所以冲印会相当暗（宽容度小），但可能仍能提供一些见解。

以下是使用高饱和度 Kodak Gold 和 Endura Premier 相纸的结果。

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/f/7/f7801a63278f5e21e5ac03619a02bc1aaac7b2eb.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/f/7/f7801a63278f5e21e5ac03619a02bc1aaac7b2eb.png)

image630×628 106 KB](/uploads/short-url/zjuotvMcuqHMQzeVFGQ7jY1bULN.png?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/1/6/1646f62fdbb6ef07e07b29e2007774e1f2bbf249.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/1/6/1646f62fdbb6ef07e07b29e2007774e1f2bbf249.jpeg)

image389×389 21.3 KB](/uploads/short-url/3b4xq00mmg1Ikx4319MQnbWhUc9.jpeg?dl=1)

以下是使用低饱和度 Portra 胶片和相纸的结果。

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/1/7/174f886aec86b7a1d7928bcce6ca76ca2aa53abb.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/1/7/174f886aec86b7a1d7928bcce6ca76ca2aa53abb.png)

image630×628 89.3 KB](/uploads/short-url/3kdnzCcAdn1Ajlg8ogt5F51Tr7B.png?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/8/e/8e33c94eeb551a0023e7e16d05ea5f4d52d5734e.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/8/e/8e33c94eeb551a0023e7e16d05ea5f4d52d5734e.jpeg)

image389×389 19.4 KB](/uploads/short-url/khYKESlBXDGg7MxLAvpYrgqhZ6e.jpeg?dl=1)

我注意到阴影现在向黑色去饱和，从白到黑的曲线大多平滑，有一些奇怪的扭曲（曲线来自压力测试图像的列）。色域也延伸到了 sRGB 之外，尤其是在蓝绿色一侧。

---

## #11 **Andrea** (@arctic) · 2025-02-11 00:23

太好了，你成功运行了程序！我很高兴有人感兴趣

[![:smiley:](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)

---

## #12 **Artaga** (@Artaga734) · 2025-02-11 12:22

我已经成功启动了程序，并尝试了一些自己的照片。目前我基本上保持默认设置，只调整了胶片类型、相纸和相纸曝光。我非常喜欢结果的感觉，尤其是红隼那张。感谢你的工具 [@arctic](/u/arctic)！

Kodak Gold 200 和 ektacolor（左）- Kodak Gold 200 和 Fujifilm Crystal Archive（右）

[[![bench_ektacolor](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/2/02318448a7c4b71e5578891ed9ba06f4b004218d_2_241x301.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/2/02318448a7c4b71e5578891ed9ba06f4b004218d_2_241x301.jpeg)

bench_ektacolor1638×2048 788 KB](/uploads/short-url/jp2JlafVCEkpwHEo8SiDuu4o1L.jpeg?dl=1)

[[![bench_fuji](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/2/227152ddd2b100e5c45b65e12b9047bd4f3491c6_2_241x301.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/2/227152ddd2b100e5c45b65e12b9047bd4f3491c6_2_241x301.jpeg)

bench_fuji1638×2048 813 KB](/uploads/short-url/4UH1N4VQv43POD8PCLV6VTwPZBk.jpeg?dl=1)

红隼使用 Fujifilm C200 和 Kodak Supra Endura

原始有点曝光不足：

[[![robin2_c200_supra_endura](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/f/0fb4d75b62c9dd9f8ce2d867e025f21b1770eaa2_2_34x25.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/f/0fb4d75b62c9dd9f8ce2d867e025f21b1770eaa2_2_34x25.jpeg)

robin2_c200_supra_endura2048×1535 273 KB](/uploads/short-url/2eWBYV8861a4fuBoKbUvNJ4jNS2.jpeg?dl=1)

更多曝光（左）- 更改颜色滤镜 y shift +2 m shift +3（右）

[[![robin2_c200_supra_endura_y_p0_m_p0_pexp_1_5](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/a/0af1b21475e82c4b3f6c7b1535d025f9b16e6340_2_276x206.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/a/0af1b21475e82c4b3f6c7b1535d025f9b16e6340_2_276x206.jpeg)

robin2_c200_supra_endura_y_p0_m_p0_pexp_1_52048×1535 335 KB](/uploads/short-url/1yOBwmfqFYeU2qDl3SRZDjbjPag.jpeg?dl=1)

[[![robin2_c200_endura_premier_y_p2_m_p3_pexp_1_5](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/9/e94110c78b186833273c07e69cb9df7616462366_2_276x206.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/9/e94110c78b186833273c07e69cb9df7616462366_2_276x206.jpeg)

robin2_c200_endura_premier_y_p2_m_p3_pexp_1_52048×1535 325 KB](/uploads/short-url/xhsEtKGPq9PJBBpD9gcwSkWdKei.jpeg?dl=1)

使用 Crystal Archive 相纸：

[[![robin2_c200_crystal_archive_y_p0_m_p0_pexp_1_5](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/1/819d8f8d82b3547308a96721757118c8e2aba367_2_517x387.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/1/819d8f8d82b3547308a96721757118c8e2aba367_2_517x387.jpeg)

robin2_c200_crystal_archive_y_p0_m_p0_pexp_1_52048×1535 340 KB](/uploads/short-url/iuDaih2eVTAGrUrMqMSF3oHQ0th.jpeg?dl=1)

---

## #13 **Andrea** (@arctic) · 2025-02-11 12:26

太棒了！

[![:sunglasses:](https://discuss.pixls.us/images/emoji/apple/sunglasses.png?v=12)](https://discuss.pixls.us/images/emoji/apple/sunglasses.png?v=12)

如果你想玩，我建议你更改以下内容：

- 相纸曝光：使图像变亮或变暗
- 底片曝光：如果阴影欠曝，增加它，否则对图像影响不大
- 关键是使用颜色滤镜。Y 滤镜使图像变暖或变冷，M 滤镜使图像更偏洋红或绿色。本质上是白平衡的微调。

这是 RA4 冲印控制系统的核心。

---

## #14 **Daniel, who likes dt and digikam** (@DanielLikesDT) · 2025-02-11 19:47

真是一个怪物级的软件——在最积极的意义上。

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/4/b4c38d909b2372be1e352b7fa40490e5f88cd411_2_690x290.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/4/b4c38d909b2372be1e352b7fa40490e5f88cd411_2_690x290.jpeg)

image2600×1093 1.57 MB](/uploads/short-url/pN6UJm2untnKYybywuaIMBKMFvH.jpeg?dl=1)

它完全耗尽了我那台不算差的配备 32GB RAM 的台式电脑，仅仅为了计算上面可见的裁剪图像。许多按钮感觉像魔法，但它们按工具提示所说的那样工作（预闪对于对模拟胶片显影一无所知的人来说是一个巨大的惊喜）。太棒了。请继续努力。

---

## #15 **Andrea** (@arctic) · 2025-02-12 08:03

未来肯定需要做一些优化来减少内存使用。

[![:grin:](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)

关于预闪，我有一个非常好的例子来自一张 Play Raw [High contrasts in a man made wilderness](https://discuss.pixls.us/t/high-contrasts-in-a-man-made-wilderness/43415)，来自 [@Popanz](/u/popanz)。

相纸的宽容度有限且对比度预定义，而底片可以捕捉非常大的动态范围（轻松超过 10 档）。预闪是冲印过程中的一种简单技巧，用于保留一些高光细节。相纸在底片投影之前用一些光线进行预闪，即使其变得更灰并抑制高光（有关真实示例，请观看此视频 [https://www.youtube.com/watch?v=lcx4ag7iygI](https://www.youtube.com/watch?v=lcx4ag7iygI)）。代价是对比度和饱和度降低。

[[![garden_pro_400h_crystal_archive_typeii_1.0cpl_0preflash_0Y0M_015pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/3/5394800ce895e24536b8901c3e20a8b7e0ab56fa_2_690x460.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/3/5394800ce895e24536b8901c3e20a8b7e0ab56fa_2_690x460.png)

garden_pro_400h_crystal_archive_typeii_1.0cpl_0preflash_0Y0M_015pe1999×1334 5.14 MB](/uploads/short-url/bVnMZJa9zPH8YCX3R0uuivXNqMG.png?dl=1)

[[![garden_pro_400h_crystal_archive_typeii_1.0cpl_001preflash_0Y0M_015pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/4/54842f9e8b81f4b38172d4381a30e2fd8881fc9d_2_690x460.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/4/54842f9e8b81f4b38172d4381a30e2fd8881fc9d_2_690x460.png)

garden_pro_400h_crystal_archive_typeii_1.0cpl_001preflash_0Y0M_015pe1999×1334 5.07 MB](/uploads/short-url/c3FjvSo4sKL0VT13uiT4FyOkJL7.png?dl=1)

使用 Fujifilm Pro 400h 搭配 +4 档曝光补偿，Fujifilm Crystal Archive TypeII 搭配 0.15 相纸曝光。

上方没有预闪，下方有 0.01 的预闪曝光通过未曝光的胶片片基（在仿真中，默认情况下预闪曝光被认为是通过未曝光的胶片）。你也可以通过更改放大机滤镜来为预闪着色，与底片冲印曝光不同。

---

## #16 **Steven** (@123sg) · 2025-02-12 13:46

太棒了……我没有足够的知识来理解涉及的所有内容，但我能认识到这背后巨大的工作量，结果看起来令人惊叹。

我目前完全使用 Windows，等有时间我会考虑设置一个虚拟机……

除非我忽略了明显的东西，有更好的方法让它运行？

[![:wink:](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)

---

## #17 **Daniel, who likes dt and digikam** (@DanielLikesDT) · 2025-02-12 14:02

你可以在 Windows 上运行它——没问题。只需安装 pycharm 或其他 Python IDE 即可。

---

## #18 **Artaga** (@Artaga734) · 2025-02-12 16:10

我可以确认它在 Windows 上使用 Pycharm 运行，只需确保从 Pycharm 的 IDE 直接运行时工作目录正确即可。

如果在小屏幕（如笔记本电脑）上测试，我发现将这一行改为以下内容很有用：

```
viewer.window.add_dock_widget(simulation, area="right", name='main', tabify=True)
# 将 tabify 改为 True

```

否则运行按钮会超出画面。

---

## #19 **Andrea** (@arctic) · 2025-02-12 17:08

我通常从终端直接从主包文件夹运行 GUI，例如，如果使用 `conda` 并按照仓库 README 中的说明操作：

```
> conda activate agx-emulsion
> cd \path\to\main\repo\folder\
> python agx_emulsion\gui\main.py

```

请记住，所有与 GUI 相关的内容都非常简陋。

---

## #20 **nosle** (@nosle) · 2025-02-12 19:02

我的 Python 技能几乎为零，运行的是 debian，似乎没有 conda。我尝试使用 venv，执行时出现了段错误。有人有建议吗？

这看起来是个很棒的项目！

---

## #21 **Liam Collod** (@liam_collod) · 2025-02-13 15:38

非常酷的项目！我还没有时间深入探索，但它看起来很迷人。

对于那些难以安装的人，现在你可以使用 [uv](https://docs.astral.sh/uv) 来管理和安装 Python 程序。

即使你的系统上什么都没有安装（甚至没有 python），你只需要执行以下命令：

<pre data-code-wrap="bash"><code class="lang-bash"># ！你只需要在首次执行此命令来安装 uv！
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

cd path/to/agx-emulsion/download/dir

# ！你只需要首次执行此命令！
# 这需要一些时间来运行，因为它需要缓存所有依赖项
uv run --python 3.11 --with-requirements requirements.txt --no-project --with-editable . imageio_download_bin freeimage

# 这是你每次启动程序时调用的命令
uv run --python 3.11 --with-requirements requirements.txt --no-project --with-editable . agx_emulsion/gui/main.py
</code></pre>

以上适用于 Windows 上的 powershell，在其他系统上你可能只需要根据其手册编辑命令来安装 uv：[Installation | uv](https://docs.astral.sh/uv/getting-started/installation/#standalone-installer)

还有 [@arctic](/u/arctic)，为了去除烦人的 imageio 下载步骤，你可以使用其他图像 IO 库，比如 [OpenImageIO](https://openimageio.readthedocs.io)，他们最近发布了 [pip 包](https://pypi.org/project/OpenImageIO/)。

---

## #22 **Steven** (@123sg) · 2025-02-13 19:50

我现在已经在 Windows 11 上运行了——后来意识到我只需要安装 Anaconda，然后基本上按照 readme 中的说明操作……

我喜欢它！要充分利用还需要很多学习，我理解它仍处于实验阶段，但一些照片上的结果让我很满意。在这里分享了一张 [Capture Challenge] Charge your battery and take some photos - #2913 by 123sg](https://discuss.pixls.us/t/capture-challenge-charge-your-battery-and-take-some-photos/31798/2913)

---

## #23 **nosle** (@nosle) · 2025-02-13 20:00

感谢 uv 的提示。在 debian 上，我创建了一个 venv 环境，用 pip 安装了 uv，然后复制粘贴了你的 uv 命令。成功了！

---

## #24 **Felix Kloss** (@luator) · 2025-02-13 21:04

这看起来真的太棒了！我刚刚快速试了一下，主要使用默认设置（过多的选项有点让我不知所措 :D），结果看起来真的很棒。当我有时间时，我肯定还会再玩一会儿。

---

## #25 **Sakari** (@flannelhead) · 2025-02-13 21:13

看到你从基本原理和底层化学过程出发取得了如此大的进展，真是太棒了。目前看起来很棒，期待深入了解代码并进一步尝试！

要使用超出 sRGB 范围的图像需要什么？[这个仓库](https://github.com/sobotka/Testing_Imagery)是测试图像的宝库，大多数是线性 BT.709 编码的 OpenEXR，其中一些分量有负值。据我所知，该程序期望使用 sRGB 逆 EOTF 编码的值。

---

## #26 **nosle** (@nosle) · 2025-02-13 21:41

经过测试，我感觉我就像在看我自己的扫描件！花了一些时间来理解这些旋钮的作用，因为我从未自己冲印过彩色胶片。

我很好奇为什么我的照片需要高达 -40 ev 的曝光补偿才能显示东西？

我从 Rawtherapee 导出，导入的文件看起来对比度很高，而在其他查看器中则非常平坦。

---

## #27 **Steven** (@123sg) · 2025-02-13 22:11

> **@nosle** (帖子 #26):
> 导入的文件看起来对比度很高

我也注意到了，从 darktable 导入 16bit tiff，但一旦我运行模拟，它们就正常了——多余的对比度消失了。

> **@nosle** (帖子 #26):
> 我很好奇为什么我的照片需要高达 -40 ev 的曝光补偿才能显示东西？

我的不需要那么多……有趣——可能是色彩配置文件的问题？我使用了自动曝光。

---

## #28 **Andrea** (@arctic) · 2025-02-13 22:12

> **@liam_collod** (帖子 #21):
> 对于那些难以安装的人，现在你可以使用 uv 来管理和安装 Python 程序。
> 即使你的系统上什么都没有安装（甚至没有 python），你只需要执行以下命令：

非常感谢你的说明，我之前不知道 `uv`！我一定会看看。

> **@liam_collod** (帖子 #21):
> 还有 @arctic，为了去除烦人的 imageio 下载步骤，你可以使用其他图像 IO 库，比如 OpenImageIO，他们最近发布了 pip 包。

哦不错！也是个好建议。

> **@flannelhead** (帖子 #25):
> 要使用超出 sRGB 范围的图像需要什么？

目前限制输入色彩空间的是我在流程最开始时将 RGB 转换为光谱数据的方式。我使用的是这个 [colour.recovery.RGB_to_sd_Mallett2019](https://colour.readthedocs.io/en/develop/generated/colour.recovery.RGB_to_sd_Mallett2019.html#colour.recovery.RGB_to_sd_Mallett2019)，它非常方便、稳健且快速，但仅适用于 sRGB。不同的光谱输入转换可以允许更宽的色域。我感觉到，鉴于胶片层的宽吸收特性，这不会太大改变结果。但当然，我们应该实验并验证。

> **@nosle** (帖子 #26):
> 我很好奇为什么我的照片需要高达 -40 ev 的曝光补偿才能显示东西？

这听起来非常奇怪，在使用相机自动曝光时，我从未使用过超过几 ev 的补偿。你能分享一个 .pp3 或你使用的低分辨率文件以便我重现吗？你是否导出 16bit PNG 并使用 `filepicker` 小部件导入？如果直接用 napari 导入可能无法正常工作，会转换为 8 位。

---

## #29 **Andrea** (@arctic) · 2025-02-13 22:13

> **@123sg** (帖子 #22):
> 我喜欢它！要充分利用还需要很多学习，我理解它仍处于实验阶段，但一些照片上的结果让我很满意。在这里分享了一张 [Capture Challenge] Charge your battery and take some photos - #2913 by 123sg

看起来令人印象深刻！

[![:slightly_smiling_face:](https://discuss.pixls.us/images/emoji/apple/slightly_smiling_face.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slightly_smiling_face.png?v=12)

---

## #30 **Andrea** (@arctic) · 2025-02-13 22:31

我在主分支上做了一些小的优化。

主要是我将光谱计算的波长步长从 5 nm 减少到了 10 nm，牺牲了一点精度以提高效率。我没有注意到大的变化，但光谱（尤其是滤镜和胶片/相纸吸收）的采样看起来有点粗糙。

通过这些微小的变化，我成功在我的笔记本电脑（32GB 内存）上处理了一张 20 百万像素的图像。Kodak Gold 200 和 Portra Endura，原始文件来自 [signatureedits.com](http://signatureedits.com)。

[[![gold200_portra_default](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/b/3b9087f6f23486265d8231924174eb5a286ec712_2_666x999.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/b/3b9087f6f23486265d8231924174eb5a286ec712_2_666x999.jpeg)

gold200_portra_default3753×5634 2.23 MB](/uploads/short-url/8uVPhTnQ4nETehAk16eq3KSIzv4.jpeg?dl=1)

我还在考虑几个主要的优化方案，可以促进向 GPU 的移植（我想），并大幅减少内存需求，同时保持 5 nm 步长。我很快会进行原型设计并在这里更新。

---

## #31 **Bob** (@PhotoPhysicsGuy) · 2025-02-14 00:28

哇！

[@arctic](/u/arctic)，我不知道有谁能以这种深度模拟胶片。

你基本上模仿了胶片显影的每一个物理步骤。从我所见，这确实值得。

预闪和 DIR 模拟，合适的颗粒尺寸分布模拟？

我震惊了。

这个模拟的完整性超出了我的理解。

致敬。

我会去找找我的 Kodak 资料，它们描述了 70 年代或 80 年代的电影胶片（在 Vision 胶片之前）……在我的硬盘某处。

我的脑子彻底被炸开了。

编辑：找到了！来自 ECN-2 显影化学之前。甚至包含染料老化估算图……

[![:smirk:](https://discuss.pixls.us/images/emoji/apple/smirk.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smirk.png?v=12)

---

## #32 **Y** (@Y69) · 2025-02-14 06:31

多么彻底的方法！

可惜，在我的机器上它在 `libpython3` 中段错误了——我需要正确调试它

[![:frowning:](https://discuss.pixls.us/images/emoji/apple/frowning.png?v=12)](https://discuss.pixls.us/images/emoji/apple/frowning.png?v=12)

---

## #33 **Daniel, who likes dt and digikam** (@DanielLikesDT) · 2025-02-14 06:47

你可能尝试升级 requirements 中的所有导入模块。这帮助我让东西运行起来。使用 pycharm。

---

## #34 **Andrea** (@arctic) · 2025-02-14 08:41

谢谢你，[@PhotoPhysicsGuy](/u/photophysicsguy)。

> **@PhotoPhysicsGuy** (帖子 #31):
> 编辑：找到了！来自 ECN-2 显影化学之前。甚至包含染料老化估算图……

有意思！我有点成了 Kodak 技术文档的收藏者。如果能看看这些就好了。我的技术文档来源是这些网站：[Index of /docs/film](https://125px.com/docs/film/)、[Photographic & Darkroom Products by Brand](https://www.digitaltruth.com/products/)、[Browse The Analog Film Stock Library | Filmtypes](https://www.filmtypes.com/films)、[https://analogfilm.space/](https://analogfilm.space/)。

我还注意到 Kodak 较旧的数据表质量往往更高。较新的可能直接复制粘贴了旧数据表中的图片，所以当我可以选择时，通常选择最旧的。

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

> **@PhotoPhysicsGuy** (帖子 #31):
> 合适的颗粒尺寸分布模拟？

关于颗粒，我用三个正态 CDF（用于三个子层）拟合特性曲线 D-LogE。如果我们假设每层中卤化银颗粒的面积呈对数正态分布（大致如此，来自旧参考文献），且灵敏度与颗粒面积成正比，这是一个尚可的最小模型。因此多层结构直接来源于曲线本身。以下是拟合结构的示例图。

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/7/2/7240a569d3f6171375730a6fd3f461de2f37b19d.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/7/2/7240a569d3f6171375730a6fd3f461de2f37b19d.png)

image567×432 44.6 KB](/uploads/short-url/giIVZwyKVsxOJKiLYDaF3NOvvbL.png?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/8/4/847b945676dd57683df85038ee754cfac91886b6.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/8/4/847b945676dd57683df85038ee754cfac91886b6.png)

image576×432 45.8 KB](/uploads/short-url/iTZNdvKhisjVtHFhGCcs1I4DivA.png?dl=1)

然后通过调整每层的二项式（显影概率）和泊松（颗粒随机位置）分布，我们可以模拟出不错的 RMS 颗粒度剖面。

有一个方面让我感到非常惊讶，那就是胶片内置了"化学锐化"。在高密度区域释放的 DIR 成色剂在空间中扩散（约 10-15 um），并在局部产生对比度，抑制周围较低密度的图像部分。这对我来说听起来有点疯狂。

---

## #35 **Bob** (@PhotoPhysicsGuy) · 2025-02-14 10:10

> **@arctic** (帖子 #34):
> 我的技术文档来源是这些网站：

哦，这太好了！

> **@arctic** (帖子 #34):
> 然后通过调整每层的二项式和泊松分布，我们可以模拟出不错的 RMS 颗粒度剖面。

"不错"在这里有点轻描淡写了。我会认为这是一个非常复杂的颗粒模型。也可能是我不知道其他的颗粒建模工作。

> **@arctic** (帖子 #34):
> DIR 成色剂在高密度区域释放，在空间中扩散（约 10-15 um），并在局部产生对比度，抑制周围较低密度的图像部分。这对我来说听起来有点疯狂。

啊！这就是为什么一些胶片的 MTF 图在较高频率下传输系数大于 1。我一直以为只有显影罐中那种局部显影剂耗尽才能做到这一点（就像 Filmulator 中模拟的那样），这在电影胶片显影中当然是不可能的。

> **@arctic** (帖子 #34):
> 如果能看看这些就好了。

当然！我会私信给你。

---

## #36 **Bastian Bechtold** (@bastibe) · 2025-02-14 11:01

> **@arctic** (帖子 #34):
> DIR 成色剂在高密度区域释放，在空间中扩散（约 10-15 um），并在局部产生对比度，抑制周围较低密度的图像部分。这对我来说听起来有点疯狂。

我认为这就是 filmulator 实现的内容！

（顺便说一句，化学锐化显然在小区域内起作用；我相信"中画幅风格"的一部分就是这种锐化相对于底片尺寸的不同大小。似乎一些图像编辑程序在锐化算法中仍然依赖像素尺寸，这对高百万像素图像表现出类似的差异。）

---

## #37 **Bob** (@PhotoPhysicsGuy) · 2025-02-14 11:24

> **@bastibe** (帖子 #36):
> （顺便说一句，化学锐化显然在小区域内起作用；我相信"中画幅风格"的一部分就是这种锐化相对于底片尺寸的不同大小。似乎一些图像编辑程序在锐化算法中仍然依赖像素尺寸，这对高百万像素图像表现出类似的差异。）

我 100% 同意这一点。

---

## #38 **Andrea** (@arctic) · 2025-02-14 17:42

> **@PhotoPhysicsGuy** (帖子 #35):
> 我一直以为只有显影罐中那种局部显影剂耗尽才能做到这一点

据我了解，DIR 成色剂的锐化会在正常搅拌的显影过程中发生，并且只会影响非常短的范围，取决于成色剂分子在乳剂相中的扩散特性。一个合理的猜测是 10-15 um，但我需要一个更好的参考来源。

[![:grin:](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)

> **@bastibe** (帖子 #36):
> 我认为这就是 filmulator 实现的内容！

我之前不知道，我绝对应该更深入地研究一下 filmulator 项目。

> **@bastibe** (帖子 #36):
> （顺便说一句，化学锐化显然在小区域内起作用；我相信"中画幅风格"的一部分就是这种锐化相对于底片尺寸的不同大小。似乎一些图像编辑程序在锐化算法中仍然依赖像素尺寸，这对高百万像素图像表现出类似的差异。）

我也同意这一点。在仿真中，DIR 成色剂的扩散参数以微米为单位。因此更改底片尺寸（`film_format_mm`）会考虑到这一点。

---

## #39 **Y** (@Y69) · 2025-02-14 19:00

酷，切换到兼容版本解决了我的问题。作为 PR 提交了。

---

## #40 **Ted Cousins** (@cedric) · 2025-02-14 22:35

> **@arctic** (帖子 #38):
> Chat-GPT 建议 10-15 um

注意 [@arctic](/u/arctic) ，几天前管理员严厉告诉我<span class="bbcode-u">停止</span>引用 AI 回复……

---

## #41 **nosle** (@nosle) · 2025-02-14 22:48

> **@arctic** (帖子 #28):
> 这听起来很奇怪，我从未在相机自动曝光激活时使用超过几 ev 的补偿。你能分享一个 .pp3 或你使用的低分辨率文件以便我复现吗？你是导出 16 位 PNG 并使用文件选择器小部件导入的吗？直接使用 napari 导入可能效果不佳，并会转换为 8 位。

我现在已经在两台电脑和来自不同相机的文件上进行了测试。所有都需要 -30 到 -40 ev 之间的补偿。

无聊的示例照片：

[[![beach02](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/e/7ecc682760e97abe8d4a939311b546d33b48c4a9_2_690x457.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/e/7ecc682760e97abe8d4a939311b546d33b48c4a9_2_690x457.jpeg)

beach022048×1358 476 KB](/uploads/short-url/i5I6fZAH1MOppBIUaljdAyjqCPn.jpeg?dl=1)

[[![beach02](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/e/4e088f17bbbc5ebd91aaa69fcaad36eef6436c01_2_690x457.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/e/4e088f17bbbc5ebd91aaa69fcaad36eef6436c01_2_690x457.png)

beach021024×679 3.4 MB](/uploads/short-url/b8jzYbzSRX6rhvNJdOwR90VbDqx.png?dl=1)

[beach02.pp3](/uploads/short-url/kJmozPAqxoh1lRZC9X7cbVgeMlS.pp3) (15.0 KB)

[[![2025-02-14-234126_1397x663_scrot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/8/48e5230109749e2dd13ee9a82c80bbd83fe7649a_2_690x327.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/8/48e5230109749e2dd13ee9a82c80bbd83fe7649a_2_690x327.png)

2025-02-14-234126_1397x663_scrot1397×663 989 KB](/uploads/short-url/aoRiFhvR1qTZmZdogNEqTlEF29c.png?dl=1)

---

## #42 **Cameron Rad** (@cameronrad) · 2025-02-15 05:46

哇，这真是太棒了！干得漂亮！我期待进一步折腾它，并见证它的发展。

[![:slightly_smiling_face:](https://discuss.pixls.us/images/emoji/apple/slightly_smiling_face.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slightly_smiling_face.png?v=12)

另外感谢 [@liam_collod](/u/liam_collod) 提供那些安装说明。这让我在 macOS 系统上安装变得极其简单。

---

## #43 **Daniel, who likes dt and digikam** (@DanielLikesDT) · 2025-02-15 11:29

[@arctic](/u/arctic) ：有没有办法查看没有重度模拟的图像版本（而不取消选择整个图层）？

我真的很希望能够看到哪些设置对图像产生了什么影响。

目前感觉像是试错（这很可能就是当年真实的工作方式）。

另一个问题是，不管设置如何，我都会丢失大量细节。我遗漏了什么？还是说它本就该这样工作？

---

## #44 **Andrea** (@arctic) · 2025-02-15 12:15

> **@DanielLikesDT** (帖子 #43):
> 有没有办法查看没有重度模拟的图像版本（而不取消选择整个图层）？

目前我认为切换图层是唯一的方法。通过重命名图层，你可以保存使用不同设置完成的快照并进行比较

我同意界面目前非常粗糙。我不打算坚持使用 `napari`+`magicgui`，它只是一个能快速测试想法的临时 GUI（并让人们在现阶段尝试）。我认为这个模拟应该更像一个模块，集成到其他地方，这些功能已经就位。

> **@DanielLikesDT** (帖子 #43):
> 我真的很希望能够看到哪些设置对图像产生了什么影响。

当然有很多控制项。如果感到不知所措，可以从这些开始：

> **@arctic** (帖子 #13):
> 打印曝光：调亮或调暗图像
> 负片曝光：如果阴影变得曝光不足则提升它，否则对图像影响不大
> 关键是使用颜色滤镜。Y 滤镜使图像变暖或变冷，M 滤镜使图像更偏品红或更偏绿。本质上是微调白平衡。

另外：

- 颗粒 >> 颗粒面积 um2，用于增加或减少颗粒
- 成色剂 >> 定向成色剂量，用于增加或减少饱和度

如果需要，我可以扩展 README 添加更好的快速入门指南。

> **@DanielLikesDT** (帖子 #43):
> 另一个问题是，不管设置如何，我都会丢失大量细节。我遗漏了什么？还是说它本就该这样工作？

在生成颗粒后，密度级别默认应用了一个小的高斯模糊（颗粒 >> 模糊 = 0.6 像素）。你可以将其设置为 0.55 或 0.5，甚至为零。"扫描仪"中也有锐化处理，如果完全关闭颗粒模糊，我会将 `扫描 USM 锐化` 设置为 (0.7, 0)。我通常在图像的一小部分裁剪上使用"输入 >> 裁剪"和"计算完整图像"（全分辨率裁剪图像）来测试这些参数。然后对纹理满意后，再回到使用缩略预览的未裁剪编辑。

我认为这部分是有意为之，以获得更平滑相关的颗粒纹理，并且在更高分辨率的图像上效果更好。尤其是在优化模拟后，全分辨率处理不会花费太长时间。

---

## #45 **Andrea** (@arctic) · 2025-02-15 12:19

不确定为什么会发生这种情况，但我提交了一个应该能解决此问题的小修复。感谢提供的文件。

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

---

## #46 **** (@ChrisB) · 2025-02-16 18:59

你好，

你的项目看起来很有前景，我饶有兴致地阅读了这个讨论。

我已经能够运行这个应用（感谢 Liam！），但到目前为止我还没能得到"好"的结果。

我尝试了以下操作：

- 将一个 "linear_rec709" exr 文件（"线性"传递函数和 "bt.709" 基色）加载到 Nuke 中
- 将其转换为 16 位 png。这部分让我很困惑：我应该保持传递函数为"线性"还是不应该？

然后我将 png 加载到软件中，得到了奇怪的结果。图像看起来非常暗或完全褪色。

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/1/31f8b5644c8539fb8771ee7a7114c30131d47ccd_2_690x388.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/1/31f8b5644c8539fb8771ee7a7114c30131d47ccd_2_690x388.jpeg)

image980×552 115 KB](/uploads/short-url/784fBuhheGQ5nxmtNxnukE9InpP.jpeg?dl=1)

也许我对这些参数感到困惑：

- "apply cctf decoding"（应用 CCTF 解码）
- "output cctf decoding"（输出 CCTF 解码）
- "compute full image"（计算完整图像）

感谢帮助！

---

## #47 **nosle** (@nosle) · 2025-02-16 19:47

根据我的测试，我建议先从不调整任何设置开始。然后关闭自动曝光，手动调节曝光。

完整图像复选框会创建一个应用了当前设置的全分辨率图层。当未勾选时，会创建一个低分辨率版本来判断整体效果。该预览的大小、裁剪等由输入选项卡决定。

该软件运行极慢，所以我建议在对整体色调满意之前不要勾选完整图像框。

---

## #48 **Ted Cousins** (@cedric) · 2025-02-16 20:11

> **@nosle** (帖子 #41):
> 所有都需要 -30 到 -40 ev 之间的补偿。

请帮我弄明白——"ev"是指曝光补偿中的档位吗？

---

## #49 **Andrea** (@arctic) · 2025-02-16 20:36

欢迎来到 pixls.us [@ChrisB](/u/chrisb)！

> **@ChrisB** (帖子 #46):
> 将其转换为 16 位 png。这部分让我很困惑：我应该保持传递函数为"线性"还是不应该？

我通常从 darktable 导出时应用了传递函数的 16 位 PNG，然后在 GUI 中保持勾选"apply cctf decoding"框。如果你导出时没有应用传递函数，则取消勾选"apply cctf decoding"框。

"output cctf decoding"框控制是否对输出图像应用传递函数。请记住，napari 不支持色彩管理，总是以 sRGB（带传递函数）显示图像。底层数据仍然应在正确的色彩空间和 CCTF 中。我从 `colour-science` 包借用了所有颜色计算。

> **@ChrisB** (帖子 #46):
> "compute full image"（计算完整图像）

正如 [@nosle](/u/nosle) 所说，这将使程序计算全分辨率图像。默认情况下会计算缩略预览，因为该程序目前非常慢（但仍然比冲洗真实的 RA4 试纸条快）

[![:yum:](https://discuss.pixls.us/images/emoji/apple/yum.png?v=12)](https://discuss.pixls.us/images/emoji/apple/yum.png?v=12)

。

> **@cedric** (帖子 #48):
> "ev"是指档位

是的，你说得对。

---

## #50 **Ted Cousins** (@cedric) · 2025-02-16 21:03

> **@arctic** (帖子 #49):
> Ted Cousins:

"ev"是指档位

是的，你说得对。

</blockquote>
</aside>

有趣但令人费解……我计算 -30 EV 的衰减因子是 9.3^(-10)

[![:hushed:](https://discuss.pixls.us/images/emoji/apple/hushed.png?v=12)](https://discuss.pixls.us/images/emoji/apple/hushed.png?v=12)

所以我一定遗漏了什么。例如，在我的显示器屏幕上，只需要 -9 EV 就能从白色降到黑色。我确实知道显示器的亮度不是曝光。但话说回来，安塞尔·亚当斯的"场景"也只跨越 10 EV。

我不理解什么？

---

## #51 **Andrea** (@arctic) · 2025-02-16 22:04

> **@cedric** (帖子 #50):
> 有趣但令人费解……我计算 -30 EV 的衰减因子是 9.3^(-10)

这可能是一个奇怪的 bug，可能是整数溢出。确实 30ev 不正常，我在使用模拟时通常只设置过曝或欠曝几档。

---

## #52 **Ted Cousins** (@cedric) · 2025-02-16 22:26

> **@arctic** (帖子 #51):
> Ted Cousins:

我不理解什么？

这可能是一个奇怪的 bug，可能是整数溢出。确实 30ev 不正常，我在使用模拟时通常只设置过曝或欠曝几档。

</blockquote>
</aside>

明白了。谢谢！

---

## #53 **** (@ChrisB) · 2025-02-17 13:21

谢谢你的回答！

我认为我的问题主要是关于让输入（png）处于预期状态。

所以（根据我的一些联系人），我需要执行以下操作来转换我的文件：

- 归一化
- 将色域转换为 Rec.709
- 应用 sRGB OECF

（归一化指的是降低曝光，直到 exr 中的最大值等于 1.0。16 位 png 是整数数据类型，因此不支持大于 1.0 的像素值。）

我会尽快尝试。谢谢！

---

## #54 **Andrea** (@arctic) · 2025-02-17 16:21

另外请确保，无论传递函数是否应用（以及相应的复选框是否勾选），你的数据都是场景参考的，即（不带传递函数的）RGB 值应与到达相机传感器的光量成比例。

如果应用了其他非线性变换，图像很可能看起来会褪色。例如在 darktable 中，这些变换包括 sigmoid、filmic 或 base-curve。该模拟已经应用了一条源自真实特性曲线数据的 sigmoid 电影曲线，该曲线假定输入是场景参考的。

> **@ChrisB** (帖子 #53):
> （归一化指的是降低曝光，直到 exr 中的最大值等于 1.0。16 位 png 是整数数据类型，因此不支持大于 1.0 的像素值。）

完全正确！调整曝光以避免超出 PNG 16 位范围也是必要的。

---

## #55 **** (@ChrisB) · 2025-02-17 20:59

谢谢！我想我现在已经让它工作了。

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/2/52731fc95b8ad7177f6a537fc9e64c5cc9062b5d_2_690x387.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/2/52731fc95b8ad7177f6a537fc9e64c5cc9062b5d_2_690x387.jpeg)

image1703×956 278 KB](/uploads/short-url/bLnNUhNjqmmsSMiVvrN9Ryq5QaF.jpeg?dl=1)

现在我只需要以 20k 分辨率渲染

[![:wink:](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)

---

## #56 **Nate Weatherly** (@NateWeatherly) · 2025-02-17 22:29

Andrea。这太不可思议了。多年来，我一直试图使用密度曲线、打印模拟配置文件/LUT、自定义配置文件、商业 DaVinci Resolve power grades、DCTL 等来建立从线性数字 → 负片 → 打印的管线，而你这里的结果比我见过的任何东西都要好。在静态摄影软件领域，没有其他类似的东西。我无法评价模拟的技术"精度"，因为我从未做过模拟 RA-4 打印，但我可以说结果绝对看起来像胶片，而且是以最好的方式。

短期内，出于测试/实验的目的，有几点请求……是否有可能添加更多的输出色彩空间？在 Mac 上，只要有一个 ImageP3 或 DisplayP3 输出 ICC 配置文件，就能非常接近色彩管理的预览。另外，添加一个将设置重置为默认值的按钮会让实验更容易。

为了好玩，我尝试匹配 Noritsu 胶片扫描。我记不清是什么胶片了，但 400H + 富士 Crystal Archive 非常接近。我调整了打印伽马因子，然后裁剪到黑白点，我猜这也是对我的胶片扫描所做的处理。左边是胶片，右边是 AGX：

[[![Screen Shot 2025-02-17 at 5.28.42 PM](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/a/aad5d3068dad0dfee217303d0af720b182cb49f0_2_690x371.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/a/aad5d3068dad0dfee217303d0af720b182cb49f0_2_690x371.png)

Screen Shot 2025-02-17 at 5.28.42 PM4144×2230 16.2 MB](/uploads/short-url/onhhLaYr2bLjuZok3Nv35f4E28o.png?dl=1)

---

## #57 **Andrea** (@arctic) · 2025-02-17 23:22

> **@ChrisB** (帖子 #55):
> 谢谢！我想我现在已经让它工作了。

太好了！

[![:star_struck:](https://discuss.pixls.us/images/emoji/apple/star_struck.png?v=12)](https://discuss.pixls.us/images/emoji/apple/star_struck.png?v=12)

这是什么类型的图像？这是你做的渲染吗，我很好奇！

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

> **@ChrisB** (帖子 #55):
> 现在我只需要以 20k 分辨率渲染

很快我们就能处理更大的分辨率了！我正在尝试将光谱计算转移到中间 LUT，这应该能消除内存瓶颈，并使代码更清晰以便于 GPU 移植。此外，我正在用 Numba 测试一些小的优化（对我来说完全是新东西），以实现更快的颗粒合成。

所以也许不是 20k，但希望轻松达到 8k-6k。

[![:grin:](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)

---

## #58 **Andrea** (@arctic) · 2025-02-17 23:54

感谢你的反馈 [@NateWeatherly](/u/nateweatherly)！

> **@NateWeatherly** (帖子 #56):
> 在静态摄影软件领域，没有其他类似的东西。我无法评价模拟的技术"精度"，因为我从未做过模拟 RA-4 打印，但我可以说结果绝对看起来像胶片，而且是以最好的方式。

我也认为静态摄影在基于物理的模拟方面有所欠缺。有一些来自视频程序的选择：例如 [Dehancer](https://www.dehancer.com/shop/pslr/film) 也适用于 Lightroom、Capture1 和 Photoshop，或者 [Filmbox](https://videovillage.com/filmbox/) 但仅限 DaVinci Resolve。但据我所知，没有真正致力于物理模拟静态摄影的产品。我见过的那些总是与电影行业相关，或者是定制程度较低的配置文件/LUT（例如 RNI 和 VSCO）。

> **@NateWeatherly** (帖子 #56):
> 有一个 ImageP3 或 DisplayP3 输出 ICC

我刚刚在主分支的 GUI 中添加了 DisplayP3。我在 `colour-science` [RGB 色彩空间](https://colour.readthedocs.io/en/master/generated/colour.RGB_to_RGB.html)中没有找到 ImageP3。ImageP3 与 P3-D65 相同吗？

> **@NateWeatherly** (帖子 #56):
> 为了好玩，我尝试匹配 Noritsu 胶片扫描。我记不清是什么胶片了，但 400H + 富士 Crystal Archive 非常接近。我调整了打印伽马因子，然后裁剪到黑白点，我猜这也是对我的胶片扫描所做的处理。左边是胶片，右边是 AGX：

我喜欢这个对比！感谢分享。这正是我们推动项目前进和改进结果所需的那种参考。Noritsu 扫描更偏绿，我认为这在虚拟彩色放大器中无法修复。裙子和肤色惊人地接近！

照片也很棒！你用了什么镜头拍出那种旋转焦外？

---

## #59 **Nate Weatherly** (@NateWeatherly) · 2025-02-18 02:10

> **@arctic** (帖子 #58):
> 我也认为静态摄影在基于物理的模拟方面有所欠缺。有一些来自视频程序的选择：例如 Dehancer 也适用于 Lightroom、Capture1 和 Photoshop，或者 Filmbox 但仅限 DaVinci Resolve。但据我所知，没有真正致力于物理模拟静态摄影的产品。我见过的那些总是与电影行业相关，或者是定制程度较低的配置文件/LUT（例如 RNI 和 VSCO）。

我没有试过 Filmbox，但我用过几个版本的 Dehancer，很难得到我喜欢的结果。不管什么原因，你的变换中的色彩更加纯净和有机。显然 VSCO 做了大量研究和工作来测量档案胶卷和富士 Frontier 扫描仪响应，但它们在应用中的实现过于简单和有限，所以实际上没什么用。

所有 Lightroom/C1 LUT 配置文件能做的只是模拟一种曝光和扫描仪响应下的胶片，3D LUT 的分辨率根本不足以像你的变换那样将"欠曝"的线性图像映射到胶片的动态范围。你对负片和打印的自动曝光和曝光补偿的实现方式非常聪明。迫不及待想看看这个项目会走向何方！

> **@arctic** (帖子 #58):
> 我刚刚在主分支的 GUI 中添加了 DisplayP3。我在 colour-science RGB 色彩空间中没有找到 ImageP3。ImageP3 与 P3-D65 相同吗？

谢谢！那会很有帮助。据我所知，ImageP3 基本上与 DisplayP3 相同。Apple 将其包含在 macOS 中，并表示应该用于图像，但我看不出有什么区别。Display/Image P3 具有与 P3-D65 相同的基色和白点，但使用分段 sRGB 传递函数，而 P3-D65 使用像 DCI-P3 一样的伽马 2.6。

> **@arctic** (帖子 #58):
> 我喜欢这个对比！感谢分享。这正是我们推动项目前进和改进结果所需的那种参考。Noritsu 扫描更偏绿，我认为这在虚拟彩色放大器中无法修复。裙子和肤色惊人地接近！

是的，我还尝试将其他几张图像匹配到胶片扫描，这些扫描的阴影中通常有更多的蓝色。我在想这是否与胶片在深蓝/紫外光谱部分相比数码相机和光谱仪有更强的响应有关？也许有办法可选地将紫外曝光添加到 sRGB 光谱重建中？

> **@arctic** (帖子 #58):
> 照片也很棒！你用了什么镜头拍出那种旋转焦外？

谢谢！我不太确定，但我认为是徕卡 Summilux 35mm FLE。我认为出现旋转是因为我没注意，把它用在了 Techart pro AF 转接环上，这意味着浮动元件没有根据距离进行调整。另外，在索尼传感器上使用旁轴玻璃也会造成一些这样的效果。

哦，关于白平衡的问题——线性数字图像应该进行白平衡以获得中性图像，还是设置为 5500K 以匹配胶片的原生响应？

---

## #60 **Bob** (@PhotoPhysicsGuy) · 2025-02-18 12:21

> **@arctic** (帖子 #57):
> 这是什么类型的图像？

不确定是否有帮助，但在 ACES 2.0 工作组中经常出现一批图片（合成和真实世界的），我记得这张也是。这些参考图片作为各种输入来测试 DRT 实现。

此外，该工作组中还有一些*光谱*渲染，特别是用光谱纯波长（包括曝光渐变）照明的 Cornell box！

我很想看看所有这些图片通过 "agx-emulsion" 后的效果。但我不知道从工作组获取这些图片有多容易。

但也许 [@ChrisB](/u/chrisb) 可以详细说明一下。

一篇好文章：

[ACES 2.0 Workgroup DRT dev thread.](https://community.acescentral.com/t/aces-2-0-cam-drt-development/4700)

---

## #61 **Paul Matthijsse** (@paulmatth) · 2025-02-18 14:25

你好，在 Xubuntu 24.04 上打开文件有问题，有 8GB RAM（也许是 RAM 太低？）。

我按照 Github 上的安装说明使用 conda 进行安装。一切安装正常，程序启动。但当我把照片拖到应用程序上时，什么也没有打开/发生。控制台中有错误消息。

```
(agx-emulsion) paul@graveyron:~/apps/agx-emulsion$ python agx_emulsion/gui/main.py
MESA-LOADER: failed to open nouveau: /usr/lib/dri/nouveau_dri.so: kan gedeeld objectbestand niet openen: Bestand of map bestaat niet (search paths /usr/lib/x86_64-linux-gnu/dri:\$${ORIGIN}/dri:/usr/lib/dri, suffix _dri)
failed to load driver: nouveau
MESA-LOADER: failed to open nouveau: /usr/lib/dri/nouveau_dri.so: kan gedeeld objectbestand niet openen: Bestand of map bestaat niet (search paths /usr/lib/x86_64-linux-gnu/dri:\$${ORIGIN}/dri:/usr/lib/dri, suffix _dri)
failed to load driver: nouveau
MESA-LOADER: failed to open swrast: /usr/lib/dri/swrast_dri.so: kan gedeeld objectbestand niet openen: Bestand of map bestaat niet (search paths /usr/lib/x86_64-linux-gnu/dri:\$${ORIGIN}/dri:/usr/lib/dri, suffix _dri)
/home/paul/apps/agx-emulsion/agx_emulsion/gui/main.py:24: FutureWarning: Public access to Window.qt_viewer is deprecated and will be removed in
v0.6.0. It is considered an "implementation detail" of the napari
application, not part of the napari viewer model. If your use case
requires access to qt_viewer, please open an issue to discuss.
 layer_list = viewer.window.qt_viewer.dockLayerList
WARNING: QOpenGLWidget: Failed to create context
WARNING: QOpenGLWidget: Failed to create context
WARNING: composeAndFlush: QOpenGLContext creation failed
WARNING: composeAndFlush: makeCurrent() failed
WARNING: composeAndFlush: makeCurrent() failed
WARNING: composeAndFlush: makeCurrent() failed

```

程序在这里卡住了。

似乎找不到 nouveau 驱动。我的系统上它不在 /usr/lib/dri 中（该文件夹不存在）。`locate nouveau` 显示如下：/usr/lib/xorg/modules/drivers/nouveau_drv.so。

以下是 inxi -G 的输出

```
(agx-emulsion) paul@graveyron:~/apps/agx-emulsion$ inxi -G
Graphics:
 Device-1: NVIDIA GT218 [GeForce 210] driver: nouveau v: kernel
 Display: x11 server: X.Org v: 21.1.11 driver: X: loaded: modesetting
 unloaded: fbdev,vesa dri: nouveau gpu: nouveau resolution: 1920x1080~60Hz
 API: EGL v: 1.4,1.5 drivers: nouveau,swrast
 platforms: x11,surfaceless,device
 API: OpenGL v: 4.5 compat-v: 3.3 vendor: mesa v: 24.0.9-0ubuntu0.1
 renderer: NVA8

```

有什么想法吗？

---

## #62 **Paul Matthijsse** (@paulmatth) · 2025-02-18 14:42

好的，所以我把 /usr/lib/xorg/modules/drivers/nouveau_drv.so 复制到 /usr/lib/dri（创建的文件夹）并将驱动程序重命名为 nouveau_dri.so。

我启动程序，现在出现了另一个错误消息：

```
(agx-emulsion) paul@graveyron:~/apps/agx-emulsion$ python agx_emulsion/gui/main.py
MESA-LOADER: failed to open nouveau: /usr/lib/dri/nouveau_dri.so: undefined symbol: xf86CrtcConfigPrivateIndex (search paths /usr/lib/x86_64-linux-gnu/dri:\$${ORIGIN}/dri:/usr/lib/dri, suffix _dri)
failed to load driver: nouveau
MESA-LOADER: failed to open nouveau: /usr/lib/dri/nouveau_dri.so: undefined symbol: xf86CrtcConfigPrivateIndex (search paths /usr/lib/x86_64-linux-gnu/dri:\$${ORIGIN}/dri:/usr/lib/dri, suffix _dri)

```

---

## #63 **Andrea** (@arctic) · 2025-02-18 20:45

我没有试过 Dehancer（或 Filmbox），只是欣赏过他们网站上华丽的和 Youtube 上的一些视频。

[![:star_struck:](https://discuss.pixls.us/images/emoji/apple/star_struck.png?v=12)](https://discuss.pixls.us/images/emoji/apple/star_struck.png?v=12)

由于它们要在视频上运行，我猜它们在整体计算效率上有不同的优先级。我认为 `agx-emulsion` 中的模拟并不真实，因为它不是基于真实的配置文件扫描。有很多合理的猜测。同时它又是一个端到端的基于物理的模型，因此在更多边界条件下可能更"稳健"和"平滑"，即它可能更平滑地失败。

> **@NateWeatherly** (帖子 #59):
> 是的，我还尝试将其他几张图像匹配到胶片扫描，这些扫描的阴影中通常有更多的蓝色。我在想这是否与胶片在深蓝/紫外光谱部分相比数码相机和光谱仪有更强的响应有关？也许有办法可选地将紫外曝光添加到 sRGB 光谱重建中？

我正在考虑在负片的趾部区域添加一个"色调"控制，这应该能为独立调整阴影色调增加一些灵活性。同时它应该能控制严重欠曝负片的颜色，这种颜色变化可能很大（仅看网上的例子），我猜取决于显影条件。这在我的待办列表中。

> **@NateWeatherly** (帖子 #59):
> 哦，关于白平衡的问题——线性数字图像应该进行白平衡以获得中性图像，还是设置为 5500K 以匹配胶片的原生响应？

这是个好问题。一开始我总是用 darktable 校正白平衡。最近我开始将白平衡固定为 5500K，我喜欢这样得到的结果，例如日落照片，我倾向于用这种方式保留更多暖色调。我没有做过严肃的比较，但我怀疑由于放大机滤光和相纸吸收中的串扰（不如数字白平衡精确），应该会有微妙的差异。而且这听起来更正确。

柯达和富士据说分别平衡于 5500K 和 6500K。我没有好的参考来支持这一点，但这是我目前在 sRGB 光谱上采样中使用的。[Mallett2019] 的算法应该只在 6500K 下效果很好，在 5500K 下还行，在更低色温下效果不好。钨丝灯平衡的胶片将不得不等待更好的上采样算法实现。**我仍然倾向于使用 5500K 作为输入的默认白平衡。**

---

## #64 **Andrea** (@arctic) · 2025-02-18 20:52

> **@PhotoPhysicsGuy** (帖子 #60):
> 一篇好文章：
> ACES 2.0 Workgroup DRT dev thread.

谢谢！那个帖子读起来非常刺激，其中有大量精彩的可视化和色彩科学。我有点震惊

[![:face_with_spiral_eyes:](https://discuss.pixls.us/images/emoji/apple/face_with_spiral_eyes.png?v=12)](https://discuss.pixls.us/images/emoji/apple/face_with_spiral_eyes.png?v=12)

我会读一读的。

> **@PhotoPhysicsGuy** (帖子 #60):
> 在 ACES 2.0 工作组中经常出现一批图片（合成和真实世界的），我记得这张也是。这些参考图片作为各种输入来测试 DRT 实现。

拥有能展示问题的图像会很棒！我相当确定我们会发现很多问题。

[![:grin:](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)

我会寻找那些图片，当然，如果你知道在哪里可以找到它们，我很乐意被指路 [@ChrisB](/u/chrisb)。

---

## #65 **Andrea** (@arctic) · 2025-02-18 20:58

这看起来像是一个 GPU 驱动程序问题，应该与 `agx-emusion` 无关（它不使用 GPU）。据我所知，napari 使用 GPU 加速。尝试独立运行 napari，在终端中运行：

```
> conda activate agx-emulsion
> napari

```

然后尝试加载同一张图像。如果你有同样的问题，恐怕我不是最擅长找到解决方案的人。如果你有更多信息，也许给我发私信，这样我们能让这个帖子有更多自由讨论的空间。

---

## #66 **** (@ChrisB) · 2025-02-18 22:45

这确实是我为 ACES 2.0 工作组提供的一个渲染。

你可以在这里找到这些图片：

- [Output Transform Image Submissions](https://www.dropbox.com/scl/fo/fhzx0bcwcjylek1oz7kjc/ACGfmi0EHeufVOQPZLvvk7w?rlkey=53cp61955hbns8x46j6cf8k55&e=1&dl=0)（大多数以 ACES2065-1 编码）
- [Gralk Git](https://github.com/gralk/images)（以线性 - eGamut 编码）
- [ACES ODT Sample Frames](https://github.com/ampas/ACES_ODT_SampleFrames) -（我想是以 ACES2065-1 编码）

这是另一个例子：

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/b/5bac5ec7d9aba20a735ba49709c4bab0d3ac80b1_2_690x294.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/b/5bac5ec7d9aba20a735ba49709c4bab0d3ac80b1_2_690x294.jpeg)

image1306×558 195 KB](/uploads/short-url/d4YKA9rSKzv53h6DjNe1QgP2veN.jpeg?dl=1)

关于 ACES 2.0 线程（CAM DRT），我会"谨慎"对待。在图像形成中使用颜色外观模型至少是有高度争议的。

---

## #67 **Paul Matthijsse** (@paulmatth) · 2025-02-19 09:22

> **@arctic** (帖子 #65):
> 也许给我发私信

已发。

---

## #68 **Andrea** (@arctic) · 2025-02-19 19:32

> **@ChrisB** (帖子 #66):
> 你可以在这里找到这些图片：

感谢提供链接！

[![:smiley:](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)

我会用它们做实验。它们会很有用，因为我将把输入色彩空间扩展到更大的范围。

漂亮的乐高渲染。你觉得背景中的乐高人仔有红色渐变问题吗？还是这张图片用来揭示什么特别的东西？

---

## #69 **jo** (@hanatos) · 2025-02-19 20:28

> **@arctic** (帖子 #68):
> 我将把输入色彩空间扩展到更大的范围。

关于这个

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

那会在哪里发生？我目前对代码的理解是，它将是胶片代码的第一步之一，输入图像被转换为线性光 rgb，然后通过密度查找表得到 cmy 密度。我认为这就是在那些很长的 json 文件中预计算的配置文件……（我想把它们作为查找纹理）你是如何/在哪里计算它的？我假设内部有一个线性 rgb → 光谱 → 翻转颗粒密度管线？

我可能会直接使用一个简单的全色域 sigmoid 发射上采样方法，将 srgb 的 rgb 转换为光谱。这需要一个从 xy 色度到参数光谱系数的简单 2D 查找表（可以提供查找表）。一些更破碎/基于矩阵的输入设备变换会为你提供输入图像的 rgb 值，这些值甚至远远超出光谱轨迹。我在 aces 线程中见过一些。我们无法上采样这些坐标，它们需要先被钳位到真实刺激（不希望在某些波长上有负能量）。

---

## #70 **Andrea** (@arctic) · 2025-02-19 23:47

目前，我正在优化管线，使其更清晰高效。如果有任何看起来很蠢的地方，请尽管直说。

我将所有的光谱计算限制在三个 LUT 中（3D LUT 1、2 和 3）。

我现在可以计算 100MP 的图像而不会耗尽内存！不过计算仍然需要很久。

[![:joy:](https://discuss.pixls.us/images/emoji/apple/joy.png?v=12)](https://discuss.pixls.us/images/emoji/apple/joy.png?v=12)

[[![gold200_portra_default_84MP](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/e/fee9dd09f3c3ebdd33c54fe716f6b977225a84cb_2_100x150.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/e/fee9dd09f3c3ebdd33c54fe716f6b977225a84cb_2_100x150.jpeg)

gold200_portra_default_84MP7506×11268 12.7 MB](/uploads/short-url/An4kjfylTR7KU7SDqU5fTFZvoH9.jpeg?dl=1)

（抱歉图片很大，但我已经压缩了很多）

感谢 [@Artaga734](/u/artaga734) 帮助进行了一些代码性能分析！

我附上了一个管线的小示意图，可能比我的脏代码更清晰。我指定了 LUT 的输入输出。所有变量都是 3 通道图像。

[[![agx-emulsion_pipeline_0.2.0](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/0/30c33c6e7f34ecc182d9c9ee890112a85d6e726c_2_690x858.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/0/30c33c6e7f34ecc182d9c9ee890112a85d6e726c_2_690x858.png)

agx-emulsion_pipeline_0.2.01933×2405 382 KB](/uploads/short-url/6Xnd0UcadiZ0sBOLsGxbSm5hQzq.png?dl=1)

你可以清晰地看到成像系统的两个步骤（胶片 + 打印）。3D LUT 涵盖了相机、放大机和扫描仪（或者更准确地说，在我们的眼睛中）发生的光谱计算。我认为一些神奇的事情发生在 3D LUT2 和 3D LUT3 中，通道之间存在微妙的串扰，光谱密度平滑地饱和，逐渐在染料吸收峰周围消耗光线。

> **@hanatos** (帖子 #69):
> 我目前对代码的理解是，它将是胶片代码的第一步之一，输入图像被转换为线性光 rgb

正是如此！它将位于管线的最开始。我正在将输入图像 >> 线性 rgb >> 光谱上采样 x 胶片感光度 >> 胶片每层的曝光（3 通道）。

你说得对，3D LUT1 可以只用 xy 色度变成 2D。我之前没想到！

[![:smiley:](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)

这是标准做法吗？

> **@hanatos** (帖子 #69):
> 我可能会直接使用一个简单的全色域 sigmoid 发射上采样方法，将 srgb 的 rgb 转换为光谱。这需要一个从 xy 色度到参数光谱系数的简单 2D 查找表（可以提供查找表）。

那实际上会非常棒！我不知道"全色域 sigmoid 发射上采样"方法，你有参考资料吗？这是你推荐的最佳质量结果的方法吗？我也在尝试使用 [colour.recovery.LUT3D_Jakob2019](https://colour.readthedocs.io/en/latest/generated/colour.recovery.LUT3D_Jakob2019.html) 在 3D LUT 中预计算光谱，并存储在 3D LUT1 中使用（这仍然是你的

[![:grin:](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)

，我浏览了那篇论文，它是一项了不起的工作）。你觉得它是不是有点杀鸡用牛刀？

另外我注意到在 *Jakobs2019* 中，光谱在极端亮度值（10^-4 和接近 1）下变化很大。例如，我在一个 32x32x32 的网格中计算了 ACES2065-1 空间所有可能值的光谱（这可能很蠢）。我将值限制在 0 到 0.1 之间，步长 32。我限制到 0.1，因为接近 1 的值会使较窄的光谱展宽很多。这是方法的局限还是有意为之？

---

## #71 **Alberto** (@agriggio) · 2025-02-20 06:19

（TL;DR：我也要说一声*巨大的感谢*！继续阅读风险自负）

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

嗨，

我只是想加入这个了不起项目的粉丝群。过去 10 天我一直在玩它，基本上从它发布的那一刻起。我一直惊叹于如此轻易就能得到出色的结果。为 [@arctic](/u/arctic) 点赞！

所以我立刻开始思考如何将其融入我的工作流程。代码太复杂了，无法直接"借用/窃取"，而且它需要对整个胶片处理管线的深入了解，这是我根本不具备的（尽管上面的示意图对掌握全局帮助很大）。

起初，我尝试看看是否能使用更传统的数字调色和色彩分级工具来匹配渲染效果。嗯，是的，你可以接近，但这需要相当多的工作，而且越接近，"标准数字"的方式就越脆弱（意思是：你可能对某一张图片接近，但要获得稳健的东西似乎困难得多）。

因此，我开始思考另一种方式，现在我有了我认为足够满足我目的的东西。基本上，我扩展了 ART 对 3dLUT 插件的支持，使其能够使用"外部计算的 3dLUT"，可以运行任意代码以 CLF 格式计算 LUT，然后在 ART 管线中使用。经过一些基础工作（实际上只是几个小时的编码），我让一些东西工作了。我现在可以享受 [@arctic](/u/arctic) 的作品（*）在 ART 中的美妙之处——这让我很开心

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

这里有一个小演示，只是为了证明我没有瞎编：



（如你所见，改变设置后（重新）计算 LUT 需要一些时间，但（a）这是缓存的，所以重新应用相同的设置会很快，（b）我的笔记本确实已经很老了……）

（*）注意：这只适用于 AgX-emulsion 的"调色"部分；我不得不关闭所有的空间处理（例如颗粒、光晕和其他基于扩散的过程）。这*对我来说*不是什么大问题，因为我主要对调色感兴趣，而且 ART 有一些（远没那么准确和令人信服，但仍然）伪造颗粒和光晕的其他方法。但绝对需要记住这一点。

---

## #72 **jo** (@hanatos) · 2025-02-20 08:38

太棒了，感谢示意图，确实帮助很大！起初我以为需要存储光谱帧缓冲区作为中间数据，并一直在想压缩它们的方法，但似乎并非如此，所以太好了。关于光谱上采样：

> **@arctic** (帖子 #70):
> 你说得对，3D LUT1 可以只用 xy 色度变成 2D。我之前没想到！这是标准做法吗？

不，通常我们做 3D，因为反射光谱的饱和度和亮度有一个联合限制（Mac Adam 极限，每个波长不能反射超过 100%，所以越彩色意味着越少的反射/越暗）。这意味着较暗的反射光谱形状有更多自由，在上采样算法中包含这一点很重要。

现在我们处理的是*发射*，即无界信号，而不是*反射*。

我说的"全色域 sigmoid 发射上采样"指的是 [Jakob 2019]（sigmoid 部分），但使用一个跨越整个光谱轨迹（全色域）的查找表。而且它应该用于发射，而不是反射。这与有界 sigmoid 并不自然匹配，但我们总是可以按比例放大整体能量，保持形状不变。我过去做的是使用一个关于 xy 色度的 2D 表（或者直接在 2D/rec2020 中做类似的事情，因为那是我的工作空间），在某个中等亮度下做 sigmoid 上采样，然后按比例放大光谱以匹配输入信号的能量。

> **@arctic** (帖子 #70):
> 例如，我在一个 32x32x32 的网格中计算了 ACES2065-1 空间所有可能值的光谱

你是怎么做到的？`colour` 代码是只读取预计算的系数文件，还是运行高斯/牛顿优化器？这里的 sigmoidal 函数类几乎可以一直代表光谱到末端……但那是光谱轨迹/Mac Adam 极限的末端。ACES AP0/2065-1 基本上就是 XYZ 切掉红色角落以获得更好的外观：[https://facelessuser.github.io/coloraide/images/aces2065-1.png](https://facelessuser.github.io/coloraide/images/aces2065-1.png)

这意味着有些值在光谱轨迹之外，需要虚构刺激/没有有效的光谱功率分布作为表示。也许你碰到了这个区域？

---

## #73 **Andrea** (@arctic) · 2025-02-20 16:05

嘿 [@agriggio](/u/agriggio)！非常欣赏这条消息和你的工作。那真是太快了！我喜欢你在 GUI 中如何提炼出核心要素，包含调色所需的所有基本参数。干得好！

[![:grinning:](https://discuss.pixls.us/images/emoji/apple/grinning.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grinning.png?v=12)

> **@agriggio** (帖子 #71):
> 我一直惊叹于如此轻易就能得到出色的结果。

我在某种程度上也在从模拟的输出中学习。它塑造了我的审美，回顾我以前处理过的图像，它告诉我有时候我应该更大胆地使用对比度和饱和度（但要用正确的"方式"），模拟正在选择能舒适做到这一点的正确调色板。我猜想研究 LUT 实际上是如何塑造颜色的，可能会提供一些通用的见解，以开发模拟输出的通用高效工具。

> **@agriggio** (帖子 #71):
> （*）注意：这只适用于 AgX-emulsion 的"调色"部分；我不得不关闭所有的空间处理（例如颗粒、光晕和其他基于扩散的过程）。这对我来说不是什么大问题，因为我主要对调色感兴趣，而 ART 有一些伪造颗粒和光晕的其他方法。

对颗粒模拟的兴趣是我进入这个项目的入口，但这也完全合理。

[![:blush:](https://discuss.pixls.us/images/emoji/apple/blush.png?v=12)](https://discuss.pixls.us/images/emoji/apple/blush.png?v=12)

作为附注，我认为要更真实地模拟模拟胶片+打印系统，我会改变打印伽马，如果可能的话保持胶片伽马不变。这也更有道理，因为 DIR 成色剂的工作原理基于胶片中的密度值。

---

## #74 **Andrea** (@arctic) · 2025-02-20 16:32

> **@hanatos** (帖子 #72):
> 不，通常我们做 3D，因为反射光谱的饱和度和亮度有一个联合限制（Mac Adam 极限）。现在我们处理的是发射，即无界信号，而不是反射。

确实很有道理，感谢澄清！

> **@hanatos** (帖子 #72):
> 你是怎么做到的？colour 代码是只读取预计算的系数文件，还是运行高斯/牛顿优化器？

`colour` 包两者都能做到。回想一下 [Jakob2019] 补充材料中的预计算系数 LUT，运行优化器（计算成本更高），或者根据需要计算新的 LUT。我肯定是在比较虚构区域中的光谱。这就是我得到的，正好在视觉轨迹绿色一侧的边缘之外。

我从系数 LUT 得到了这个光谱：

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/8/4/84943a99f6a3fff84898d387e8034d07f791a2b9.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/8/4/84943a99f6a3fff84898d387e8034d07f791a2b9.png)

image580×455 57.6 KB](/uploads/short-url/iUQBvV3SJ4fwmjbwDeNtDsZaRjb.png?dl=1)

<details>
<summary>
代码</summary>

<pre data-code-wrap="python"><code class="lang-python">import numpy as np
import colour
import colour_datasets
import matplotlib.pyplot as plt

LUT_SIZE = 32
RGB_MAX_VALUE = 0.2

lut_aces = colour_datasets.load("4050598")['ACES2065-1']
spectral_shape = colour.SpectralShape(380, 780, 5)
wl = spectral_shape.wavelengths
x = np.linspace(0.0,1.0,LUT_SIZE)

lut_spectra = np.zeros((LUT_SIZE, LUT_SIZE, LUT_SIZE, np.size(wl)))
for i in np.arange(LUT_SIZE):
 for j in np.arange(LUT_SIZE):
 for k in np.arange(LUT_SIZE):
 rgb = np.array([x[i],x[j],x[k]]) * RGB_MAX_VALUE
 sd = lut_aces.RGB_to_sd(rgb, spectral_shape)
 lut_spectra[i,j,k,:] = sd[:]
 print('Fraction computed:',(i+1)/LUT_SIZE)

plt.plot(wl,lut_spectra[0,:,0,:].transpose())
plt.ylim((0,1))
plt.xlabel('Wavelegth (nm)')
plt.ylabel('Reflectance')
plt.title('ACES2065-1 - RGB=[0,x,0] - x_range=[0,0.2]')
</code></pre>

</details>

这是来自求解器的例子：

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/9/a/9a8e35cf8c407b61f2a6d5b71c6ad03344eefc7a.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/9/a/9a8e35cf8c407b61f2a6d5b71c6ad03344eefc7a.png)

image580×455 16.6 KB](/uploads/short-url/m3gdi7Zmd1FQia7LF8cUzTnPtX4.png?dl=1)

<details>
<summary>
代码</summary>

<pre data-code-wrap="python"><code class="lang-python">import numpy as np
import matplotlib.pyplot as plt
import colour

rgb = np.array([0.00,0.05,0.00])
xyz = colour.RGB_to_XYZ(rgb, colourspace='ACES2065-1')
out, _ = colour.recovery.find_coefficients_Jakob2019(xyz)
sd = colour.recovery.sd_Jakob2019(out, colour.SpectralShape(380, 780, 5))

plt.plot(sd.wavelengths, sd[:])
plt.ylim([0, None])
plt.xlabel('Wavelength (nm)')
plt.ylabel('Reflectance')
plt.title('ACES2065-1 - RGB=[0,0.05,0]')
</code></pre>

</details>

求解器更尖锐，但我猜我们不应该太关心这个区域。

---

## #75 **Jed Smith** (@jedsmith) · 2025-02-21 05:09

你好 [@arctic](/u/arctic)

我也想插一句，对你的项目表示赞赏。我一直在折腾它，对其方法印象深刻且感兴趣。

扩展 [@ChrisB](/u/chrisb) 在上面[回复](https://discuss.pixls.us/t/spectral-film-simulations-from-scratch/48209/53)中的内容，我想知道你是否对添加 `exr` 作为输入图像格式感兴趣？除了是一种普遍糟糕的图像格式外，`png` 确实不是为编码"场景参考"像素数据而设计的。将"场景线性"图像向下乘并以 16 位线性 exr 编码是非常低效和低质量的，因为量化的工作方式（在一个向下乘的"场景线性"图像上，16 位线性分布在 0-1 范围内会将大部分图像数据放在最低区域，导致编码数据的精度位数更少）。另一种解决方法是添加一些"场景参考"传递函数，以对数编码对图像数据进行编码，并将其存储为 16 位 png。但现在 openimageio 作为 python wheel 可用，并且可以通过 `uv` / `pip` 安装，也许值得研究 exr 支持？

如果我有空的话，很乐意提供帮助！

再次感谢你的出色工作，期待进一步折腾它。

---

## #76 **Andrea** (@arctic) · 2025-02-21 12:49

嘿 [@jedsmith](/u/jedsmith)，很高兴你成功折腾了它！感谢你的评论。

同时听取了 [@ChrisB](/u/chrisb) 和 [@liam_collod](/u/liam_collod) 的反馈，我刚刚在主分支上添加了一些更新，包括加载 `exr` 文件（32 位和 16 位）的功能。我现在按照建议使用 OpenImageIO，并且不再需要下载 freeimage 后端。我快速测试了一下，似乎工作正常，但如果你用更多的 exr 文件测试，请告诉我效果如何。

主分支现在还有一些优化，用一些 `numba` 函数加速颗粒合成，所有光谱计算现在都在 3D LUT 之后。内存瓶颈也应该大幅减少。

我用新包更新了依赖项。为了与 `numba` 兼容，我不得不回退到稍旧版本的 `numpy`。

输入色彩空间现在也可以不同于 sRGB，但会在管线的最开始内部转换为 sRGB 并进行裁剪，以使用 [Mallett2019] 光谱上采样。色彩空间必须在输入选项卡中选择。更大的空间即将到来（正在开发中）。

---

## #77 **Jakob Andrén** (@jandren) · 2025-02-21 18:21

太好了，那我就不需要提交我今天早上做的 .exr 实现的 PR 了！

使用线性 .exr 文件绝对是一个工作流程的改进，可以在 darktable 中激活 sigmoid 调整曝光，然后在导出时停用它。只需加载并取消激活"input/apply cctf encoding"，无需自动曝光！

我必须承认，目前我是纯粹的调色用户之一，但这已经足够有趣了。在这一点上，我无法对其正确性说太多，只能说看起来不错，而且我喜欢这种第一性原理的方法。期待更深入的研究，特别是更宽的色域输入以及后续如何处理。

我喜欢用图表作为图像的补充，所以这里展示的是使用来自 [ACES](https://acescentral.com/knowledge-base-2/using-aces-reference-images/) 的 syntheticChart.01 的结果。

[[![Simulation result ACES chart](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/5/2503c76ad7043d72889dae7337d88d3a2e1928b7_2_690x363.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/5/2503c76ad7043d72889dae7337d88d3a2e1928b7_2_690x363.jpeg)

Simulation result ACES chart2048×1080 196 KB](/uploads/short-url/5hrLihCme9XHRlzPWdDZbiVkezl.jpeg?dl=1)

kodak_gold_200 + kodak_endura_premier

除关闭所有空间效果和颗粒外，未使用自动曝光/补偿或其他默认值外的变化。

中间的水平条在中心为零，向右为负，所以"负"颜色出了问题。

一些颜色后来去饱和了，但没有像普通的每通道方法那样严重，如果你只是将色域裁剪到它们边界的话。

---

## #78 **Liam Collod** (@liam_collod) · 2025-02-21 20:32

很酷的更新！它让我测试了一些我有的胶片对比素材：
<aside class="onebox allowlistedgeneric" data-onebox-src="https://mrlixm.github.io/assets/chkpad1/">
 <header class="source">

[![图片128](https://d2x313g9lpht1q.cloudfront.net/original/3X/7/3/73b3848f9f3adea2109c8d2c87f9c73a0a1e82d5.svg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/7/3/73b3848f9f3adea2109c8d2c87f9c73a0a1e82d5.svg)

 [Liam Collod Website](https://mrlixm.github.io/assets/chkpad1/)
 </header>

 <article class="onebox-body">

[![图片129](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/c/acab4d5666e9b217c619c99082209ae583777665_2_690x411.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/c/acab4d5666e9b217c619c99082209ae583777665_2_690x411.png)

### [film-vs-digital asset chkpad1](https://mrlixm.github.io/assets/chkpad1/)

assets for comparison of film photography rendering against arbitrary digital photography rendering

 </article>

</aside>

我不能说场景构图是展示色彩再现最合适的，因为它相当平淡，但我认为它仍然很有趣。

所以我将数字源 exr 通过模拟运行，得到了这个：

[[![2025_02_21_210148_2481x914](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/8/e8badb50851566a5b8998ace0120fb1132094824_2_690x254.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/8/e8badb50851566a5b8998ace0120fb1132094824_2_690x254.jpeg)

2025_02_21_210148_2481x9142481×914 269 KB](/uploads/short-url/xcP6VEoqON1kXW3CqA6HyiNUSSE.jpeg?dl=1)

- 左边是胶片参考，经过主观调整并使用[我的个人胶片扫描工作流程](https://youtu.be/0H__azbRYPw)生成；注意我不得不将胶片参考的饱和度提高 +1.25（使用"最大亮度数学"），因为它相当平淡，难以与模拟结果比较。
- 右边是使用具有 sRGB 基色的数字源图像（为了安全，我重新转换了提供的 BT.2020 exr）的模拟结果。我再次降低了定向成色剂以尝试匹配胶片参考的饱和度。

所以这个对比中有很多偏差和问题，但直接来看，我可以注意到底部的青色色块完全爆炸了，这非常有趣。

由于这个色块问题让我想起了什么，我决定进行第二次测试：

[[![2025_02_21_211358_2317x913](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/f/3f9214ac0cb445f42afe6a321212827f23c36588_2_690x271.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/f/3f9214ac0cb445f42afe6a321212827f23c36588_2_690x271.png)

2025_02_21_211358_2317x9132317×913 1.69 MB](/uploads/short-url/94n3xSUxspjOXBjuTT0XUF9CP44.png?dl=1)

- 左边是相同的参考（编辑：**请忽略左边的图像**，它是数字图像经过任意图像形成的结果，请使用前一张图片中的参考，抱歉）
- 右边我现在使用了已经去马赛克到原生相机色彩空间的数字源（文件未提供，我自己做的），然后在胶片模拟应用中仅将其解释为 sRGB；基本上跳过了所有比色变换。这次为了补偿，我不得不增加定向成色剂的量。

现在我们可以看到蓝色色块不再爆炸，整体色调感觉更接近胶片参考。

<hr>

我不能从这个小小的实验中得出太多结论，但可以提出现问题，即源图像的编码和解码似乎也对使整个图像形成管线更接近模拟胶片起着重要作用。

---

## #79 **jo** (@hanatos) · 2025-02-22 07:56

> **@arctic** (帖子 #74):
> 求解器更尖锐

嗯，我认为 32 的立方可能分辨率不是很高……也许边缘附近的离散化会大大改变结果。另一个要考虑的是色域的限制。这些有界光谱落在 MacAdam 极限内，即不能有负能量（横向超出光谱轨迹），也不能太亮（反射率 <= 100%）。我认为在巨大的 AP0 色域中，你会遇到这两个极限。优化器在这种情况下可能会发散，也可能不会。

但是的，请看私信了解特殊情况的上采样代码，希望很快能在上游看到它

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

---

## #80 **Andrea** (@arctic) · 2025-02-22 14:12

好样的 [@jandren](/u/jandren)！

> **@jandren** (帖子 #77):
> 在这一点上，我无法对其正确性说太多，只能说看起来不错，而且我喜欢这种第一性原理的方法。

确实，我也担心仅仅依靠第一性原理可能无法实现真实胶卷输出的真正胶片模拟。需要一些真实的参考来更好地理解。也许可以考虑将模型的一部分拟合到一些真实数据上。我认为更准确的说法是，输出在模型限制范围内受到胶卷/相纸数据的启发。

> **@jandren** (帖子 #77):
> 中间的水平条在中心为零，向右为负，所以"负"颜色出了问题。

我不太明白关于负颜色的这部分。我找到了这个[页面](https://community.acescentral.com/t/aces-synthetic-chart/4600/2)，上面描述了这个测试图像的设计原理。但负颜色应该展示关于调色管线的什么信息呢？

---

## #81 **Andrea** (@arctic) · 2025-02-22 14:56

这绝对超级有趣 [@liam_collod](/u/liam_collod)，感谢分享这个素材。

我认为这是一个相当受控制的对比。

另外，我看了你用 Nuke 做胶片反转的视频，非常酷！我对你决定使用相机色彩空间而不进行转换特别感兴趣。这听起来确实是一种避免任何物理上不可能的负值的稳健方法。

> **@liam_collod** (帖子 #78):
> 但直接来看，我可以注意到底部的青色色块完全爆炸了，这非常有趣。

我也在一些测试中注意到青色爆炸，但尚未解决或定位根本原因。正如你的实验所展示的，这很可能与 RGB 数据的光谱上采样有关。根据与 [@hanatos](/u/hanatos) 的讨论，我怀疑这部分是因为上采样算法被优化为在应用 XYZ 灵敏度时最小化误差。胶卷负片的灵敏度可能与标准观察者有很大差异。例如柯达 Portra 400：

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/9/4/944242fd835440268106abf6fdcfebd49c21db60.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/9/4/944242fd835440268106abf6fdcfebd49c21db60.png)

image569×455 42.2 KB](/uploads/short-url/l9yD674ZCG3QSDFqGHkdoQWk31m.png?dl=1)

胶卷吸收范围更宽，灵敏度重叠更少。我的推理是，从 RGB 上采样的光谱没有对 XYZ 灵敏度之外的光谱区域施加良好的约束。因此生成的光谱可能在可见光谱边缘（胶卷吸收而眼睛不吸收的区域）有不合理的值。但我不是这个主题的专家，无法深入阐述。我需要在这上面花更多心思。

> **@liam_collod** (帖子 #78):
> 右边我现在使用了已经去马赛克到原生相机色彩空间的数字源（文件未提供，我自己做的），然后在胶片模拟应用中仅将其解释为 sRGB；基本上跳过了所有比色变换。

这个小实验，尽管有所有局限性，确实激发了我的思考，我相信会引发一些不错的思考和讨论！感谢分享！

[![:grinning:](https://discuss.pixls.us/images/emoji/apple/grinning.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grinning.png?v=12)

我想说的是，我们从 raw 解码图像的方式，以及它进入光谱管线的方式，有着巨大的影响。

---

## #82 **jo** (@hanatos) · 2025-02-22 15:08

……如果我要把东西烘焙到图像中作为 lut。配置文件 json，它们都是相同的形状/波长范围吗？我在想我可以制作一张图像，比如 log_sensitivities，其中每一行对应一种胶卷。但这只有在它们通常都相同而只有数据不同的情况下才是好主意。

---

## #83 **Andrea** (@arctic) · 2025-02-22 15:24

所有的光谱数据都在相同的波长轴上表示（N 个波长数据点）。根据版本不同，380-780 每 10 nm，或 380-780 每 5 nm。我倾向于保持 5 nm 表示，这是我早期发现的最优值。

光谱数据包括：

- 胶卷对数灵敏度（`log_sensitivity`）：RGB 层的 Nx3 数组
- 染料密度吸收光谱（`dye_density`）：[C,M,Y,最小密度,介质中性密度] 的 Nx5 数组
  注：介质中性密度实际上不是必需的。它仅用于制作配置文件。

还有密度特性曲线数据，全部在对数曝光尺度（M 个点）上表示，采样相当密集，因为我后来对它们使用线性插值。

包括：

- 层的特性曲线（`density_curves`）：RGB 通道的 Mx3
- 每个子层的特性曲线（`density_curves_layers`）：Mx3x3 表示 [对数曝光, 子层, rgb-层]，用于多层颗粒合成

---

## #84 **jo** (@hanatos) · 2025-02-23 11:31

感谢你的所有解释！我想我有很多细节弄错了，而且我忽略了所有涉及制作图像的归一化和照明……但我至少能得到可识别的像素了：

[[![20250223_12h27m28s_grim](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/2/222826471675701b67de54c369f176039b1e2485_2_690x657.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/2/222826471675701b67de54c369f176039b1e2485_2_690x657.png)

20250223_12h27m28s_grim1353×1290 571 KB](/uploads/short-url/4SafKbmSGOa4W8nQRpUfpdEGE6x.png?dl=1)

我没有使用任何 3d lut（也许我应该烘焙这样的东西），所以它在进行完整的光谱上采样和积分。这使得它有点慢，全 raw 分辨率在这里处理了 27ms。

另外我在 log10 上遇到了一些数值问题，我*认为*我可以用自然 exp/log 并相应地缩放 lut。

---

## #85 **Jakob Andrén** (@jandren) · 2025-02-23 12:38

关于我如何解读那些"负颜色"及其在图表中的用途的尝试：

我将线性 RGB 输入值基本上视为没有真正限制的 3D 坐标，即我们可以在该空间中的任何位置。所以我们应该测试我们的算法对所有可能的输入是否稳健，并以合理快速的方式进行，确保那些保持黑色的区域是测试方法之一。

让我对这些光谱内容感到兴奋的是，我们可以通过说光谱必须是正的来更好地定义有效颜色的边界。相比之下，例如 rec-709（sRGB）基色远小于光谱轨迹，因此有效的 RGB 坐标中含有负值！

> 这使得它有点慢，全 raw 分辨率在这里处理了 27ms。

[![:rofl:](https://discuss.pixls.us/images/emoji/apple/rofl.png?v=12)](https://discuss.pixls.us/images/emoji/apple/rofl.png?v=12)

我想你可以在你把"m"从"ms"前面去掉之后再叫它慢。

---

## #86 **** (@mikae1) · 2025-02-23 12:53

> **@hanatos** (帖子 #84):
> 感谢你的所有解释！我想我有很多细节弄错了，而且我忽略了所有涉及制作图像的归一化和照明……但我至少能得到可识别的像素了：

等等……你已经开始把 Python 代码移植到 C 了？还是这是在 [ART 中实现的](https://discuss.pixls.us/t/spectral-film-simulations-in-art/48442/)？

> **@jandren** (帖子 #85):
> 全 raw 分辨率在这里处理了 27ms。

我想你可以在你把"m"从"ms"前面去掉之后再叫它慢。

我同意，那真是太快了！

[![:raised_hands:](https://discuss.pixls.us/images/emoji/apple/raised_hands.png?v=12)](https://discuss.pixls.us/images/emoji/apple/raised_hands.png?v=12)

---

## #87 **jo** (@hanatos) · 2025-02-23 13:08

> **@jandren** (帖子 #85):
> 你把"m"从"ms"前面去掉

嘿，我绝对没有这个计划

[![:smiley:](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)

我想更多地了解结果是如何形成的，哪些参数是必不可少的，然后实现颗粒和预闪光等（现在省略了不少东西），然后再进行性能优化。

是的，负 RGB 完全可以。负光谱能量不行。我几天前创建的 sigmoidal 光谱上采样表格会上采样*所有东西*，甚至在光谱轨迹内也是有意义的。轨迹之外，它只是使用内插法给你一个接近你请求坐标的正光谱。

> **@mikae1** (帖子 #86):
> 等等……你已经开始把 Python 代码移植到 C 了？

glsl。我真的不会说 python，而且我绝对讨厌软件堆叠工具链（比如 latex 包中的 shellscript 之类的东西）。

## #88 **** (@mikae1) · 2025-02-23 13:52

> **@hanatos** (帖子 #87):
> glsl.

太酷了！希望你们已经准备好迎接一波热爱颗粒的YouTube博主，一旦这个变得更易用的话。

[![:wink:](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)

---

## #89 **** (@commutergraphics) · 2025-02-23 14:22

这看起来真的很棒，我一直在想象如何以有趣的方式操控颗粒，已经有一阵子了。虽然对胶片来说不太忠实，但我一直在思考一些事情，比如不同色调级别使用不同大小的颗粒，通过模拟来进行实验，然后也许做一些傻事，比如把底层颗粒排列成完美的网格或者不同类型的随机图案等，这些是胶片做不到的。也许可以像在 darktable 中遮罩区域然后对它们应用不同的实例，像是弗兰肯斯坦胶片，天空用 Velvia，鸟类用 Astia。

---

## #90 **Andrea** (@arctic) · 2025-02-23 17:35

> **@hanatos** (帖子 #84):
> 我没有使用任何 3D LUT（也许我应该烘焙这些），所以它执行完整的光谱上采样和积分。这有点慢，全原始分辨率在这里处理需要 27 毫秒。

27 毫秒，太疯狂了！我认为"相机"3D LUT 和"扫描仪"3D LUT 可以烘焙。我不确定"放大机"那个，因为用 CMY 滤镜进行色彩平衡会改变 LUT，而这是主要控制之一。

你能在管线末尾看到结果就已经很了不起了！

[![:grin:](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)

> **@jandren** (帖子 #85):
> 我认为线性 RGB 输入值本质上就是 3D 坐标，没有真正的限制，也就是说我们可以处于该空间中的任何位置。所以我们应该以合理快速的方式测试算法对所有可能输入的鲁棒性，确保那些保持黑色的区域是测试方法之一。

谢谢你的评论，有道理。负的 ACES2065-1 值肯定在可见色域之外，所以我想对于可见图像的测试计算来说，这算是一个极端区域，但在光谱处理中可能更有意义。

---

## #91 **jo** (@hanatos) · 2025-02-23 18:32

…我无论如何都无法从中得到中性的还原效果：

[[![20250223_19h29m22s_grim](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/d/cde99825b6fcee19dab4ec6f412109826df9bd15_2_690x616.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/d/cde99825b6fcee19dab4ec6f412109826df9bd15_2_690x616.png)

20250223_19h29m22s_grim1774×1584 1.74 MB](/uploads/short-url/tnAm0wMdZOKBFe1ye4sdl412s1D.png?dl=1)

这是放大机滤镜设置为 0.005,0.008,1…

有没有什么地方会导致整体色彩平衡出现问题？哦，还有这个灯，它本身有没有基础光谱？现在我只是在混合 thorlabs 的滤镜…

我也没有使用任何 D50 或 D55 照明体…但我觉得照明体 E 相差不太远。

---

## #92 **Andrea** (@arctic) · 2025-02-23 18:33

我实现并测试了一点 [@hanatos](/u/hanatos) 的光谱上采样方法。它在 `agx-emulsion` 的 `large-color-space` 分支中可用，经过更多测试后我会将其移到 `main` 分支。

我有一些初步的定性结果（使用 [signatureedits.com](http://signatureedits.com) 的原始文件）。我认为总体而言对饱和色彩有影响。来自 hanatos 的新方法（这里称为 `hanatos2025`）可以为可见色域内的任何三刺激值生成光谱。我认为它的简洁性和结果都很棒。旧方法称为 `mallett2019`，仅对 sRGB 有效，因此在进行光谱上采样之前会转换并将数值裁剪到 sRGB。

我导出了一些线性 Rec2020 中的测试原始图像并运行了一些模拟。

以下是几个对比，我只更改了上采样方法，保持所有其他参数不变（除非另有说明）。

（左）`hanatos2025` 和（右）`mallett2019`，Kodak Portra 400 和 Portra Endura

[[![hanatos2025_portra_portra](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/e/9e2c3ce9da10c2693c6fe6f26b22c6504dc4ddad_2_330x220.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/e/9e2c3ce9da10c2693c6fe6f26b22c6504dc4ddad_2_330x220.png)

hanatos2025_portra_portra2000×1334 3.75 MB](/uploads/short-url/mzgdCtE043aEz1zbNzCYO4hWxZz.png?dl=1)

[[![mallett2019_portra_portra](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/f/2f5b812246944df6298a4b9c1375b41f56deb501_2_330x220.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/f/2f5b812246944df6298a4b9c1375b41f56deb501_2_330x220.png)

mallett2019_portra_portra2000×1334 3.72 MB](/uploads/short-url/6KWuhAvs0hn4Hq77WkssM3k835v.png?dl=1)

附带说明，我还在虚拟相机上添加了一个带通滤波器（滤除 400 nm 以下的近紫外和 680 nm 以上的光）。最棘手的问题是一些胶片如 Portra 400 具有非常蓝/近紫外吸收，而上采样方法确实无法限制当 XYZ 灵敏度降至零时会发生什么。

滤波器看起来像这样：

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/6/06b69d7f293316265e727ce44256329670a16c1b.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/6/06b69d7f293316265e727ce44256329670a16c1b.png)

image560×455 38.2 KB](/uploads/short-url/Xo7cp8ZVk3vXdxlx6K3ZwwmdV9.png?dl=1)

蓝色显示的是标准观察者 XYZ 灵敏度的总和。带通滤波器切掉了光谱中无法由上采样方法约束的部分（这些方法优化以最小化 XYZ 误差）。

我从项目一开始就注意到，Portra 中的红色相比其他胶片偏粉。现在它们表现得更合理了。

（左）`hanatos2025` 带滤波器，和（右）`hanatos2025` 不带滤波器，Kodak Portra 400 和 Portra Endura

[[![hanatos2025_portra_portra](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/e/9e2c3ce9da10c2693c6fe6f26b22c6504dc4ddad_2_330x220.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/e/9e2c3ce9da10c2693c6fe6f26b22c6504dc4ddad_2_330x220.png)

hanatos2025_portra_portra2000×1334 3.75 MB](/uploads/short-url/mzgdCtE043aEz1zbNzCYO4hWxZz.png?dl=1)

[[![hanatos2025_portra_portra_noUVfilter_-15Y0M](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/e/1eecbc7fa59397907d25432e1ebf0c5091e29443_2_330x220.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/e/1eecbc7fa59397907d25432e1ebf0c5091e29443_2_330x220.png)

hanatos2025_portra_portra_noUVfilter_-15Y0M2000×1334 3.78 MB](/uploads/short-url/4pzwONUjDNYgXlek6v5VcdLFMsP.png?dl=1)

我补偿了没有带通滤波器的图像（-15Y）以平衡一下暖色调。

（左）`hanatos2025` 和（右）`mallett2019`，Kodak Portra 400 和 Portra Endura

[[![hanatos2025_portra](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/9/e945ab159ec1beb90ef1a7834c6f73a1382168b0_2_330x220.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/9/e945ab159ec1beb90ef1a7834c6f73a1382168b0_2_330x220.png)

hanatos2025_portra2000×1335 3.93 MB](/uploads/short-url/xhCvSNCH115AII9KBvYP6d9luc8.png?dl=1)

[[![mallett2019_portra](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/f/8f239cb3dc22f3e3d147cdf0ad6334c72ba9c284_2_330x220.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/f/8f239cb3dc22f3e3d147cdf0ad6334c72ba9c284_2_330x220.png)

mallett2019_portra2000×1335 3.96 MB](/uploads/short-url/kqgzLyCrV99v8aLvVQdgaMNc9tG.png?dl=1)

[[![hanatos2025_portra_crop](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/b/cbfdd2179d5289774411f51b01d5ac45ad5f7b6f.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/b/cbfdd2179d5289774411f51b01d5ac45ad5f7b6f.png)

hanatos2025_portra_crop560×560 420 KB](/uploads/short-url/t6AJyvLhBzd26rzu6Sbqa8vyIP5.png?dl=1)

[[![mallett2019_portra_crop](https://d2x313g9lpht1q.cloudfront.net/original/3X/2/7/275b85d0eb737316903f9e9f25ceef5d4f5dc1a6.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/2/7/275b85d0eb737316903f9e9f25ceef5d4f5dc1a6.png)

mallett2019_portra_crop560×560 432 KB](/uploads/short-url/5CaHT2Yg0m119byO6yJ5ADFijnE.png?dl=1)

背景的裁剪显示 `hanatos2025` 在高饱和度的黄色花朵中更平滑，保留了到花朵中心的平滑色彩过渡。

（左）`hanatos2025` 和（右）`mallett2019`，Kodak Gold 200 和 Portra Endura

[[![hanatos2025_gold_portra](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/9/09dd326e0ae7cec93a4d159eb9d91b2a0e1d1630_2_330x480.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/9/09dd326e0ae7cec93a4d159eb9d91b2a0e1d1630_2_330x480.png)

hanatos2025_gold_portra1334×2000 3.8 MB](/uploads/short-url/1pgcZIfaNwwpmRWl1JOQUvdehig.png?dl=1)

[[![mallett2019_gold_portra](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/f/eff4afb3285ae56adbfa24d20187d0bc8eff98a2_2_330x480.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/f/eff4afb3285ae56adbfa24d20187d0bc8eff98a2_2_330x480.png)

mallett2019_gold_portra1334×2000 3.84 MB](/uploads/short-url/yeKlULgTTL9FixxRmPcFxE5whSW.png?dl=1)

在这张人像中，`hanatos2025` 保留了一些饱和度，我认为与头发失焦边缘的过渡更令人愉悦。图像似乎也更有"深度"。

（左）`hanatos2025` 和（右）`mallett2019`，Kodak Gold 200 和 Portra Endura

[[![hanatos2025_gold_portra](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/a/2aea684b8e1f283095ff1dc903dc27fc1bb910e9_2_330x220.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/a/2aea684b8e1f283095ff1dc903dc27fc1bb910e9_2_330x220.png)

hanatos2025_gold_portra2000×1335 4.36 MB](/uploads/short-url/67EgHcwBINqsey2lEJnjBi9DwDv.png?dl=1)

[[![mallett2019_gold_portra](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/1/31113d6e3573cdc279f29015291706ce01d0a623_2_330x220.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/1/31113d6e3573cdc279f29015291706ce01d0a623_2_330x220.png)

mallett2019_gold_portra2000×1335 4.34 MB](/uploads/short-url/704kC8zQ6p3BM3yZ48rRxCBaImv.png?dl=1)

某些特殊颜色肯定比其他颜色受影响更大，比如青柠绿。

我还用这张压力测试图像做了一些快速测试，探索色彩空间的边缘和去饱和路径。这张压力测试图像之前已经在线程中出现过。

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/d/3/d33774e3718fe35c9b6ee523d8d176bf1b30f6c2.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/d/3/d33774e3718fe35c9b6ee523d8d176bf1b30f6c2.png)

image630×628 69.3 KB](/uploads/short-url/u8vyOiEOgBgI2joU7k4FYQVeud4.png?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/1/4/146687c64a75cf4b4b8491a2916f149179ba861f.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/1/4/146687c64a75cf4b4b8491a2916f149179ba861f.jpeg)

image389×389 20.3 KB](/uploads/short-url/2UtdCzBQmPKk3HMUyEvBcgGJ1CL.jpeg?dl=1)

这是我将图像作为 sRGB 导入并启用 cctf 解码时的结果。

（左）`hanatos2025` 和（右）`mallett2019`，Kodak Portra 400 和 Portra Endura

[[![hanatos2025_srgb_cctf_1pe_0stops](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/5/a59d110edd572634e1810f6d7055b2536474bd1f_2_330x165.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/5/a59d110edd572634e1810f6d7055b2536474bd1f_2_330x165.png)

hanatos2025_srgb_cctf_1pe_0stops1000×500 543 KB](/uploads/short-url/nD5in6yFuBsiPFGkzr2twCtVGYD.png?dl=1)

[[![mallett2019_srgb_cctf_1pe_0stops](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/b/5bbbb129d8e303ba8b2d4018f620ed5c85016a52_2_330x165.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/b/5bbbb129d8e303ba8b2d4018f620ed5c85016a52_2_330x165.png)

mallett2019_srgb_cctf_1pe_0stops1000×500 542 KB](/uploads/short-url/d5vzQsfj8cNNrDnzRiwCk8lHchc.png?dl=1)

通过增加 2 档曝光和 0.25 打印曝光，我们可以揭示"青色灾难"，这也是 [@liam_collod](/u/liam_collod) 在他的测试中注意到的。新方法在这方面似乎稍差一些。

（左）`hanatos2025` 和（右）`mallett2019`，Kodak Portra 400 和 Portra Endura

[[![hanatos2025_srgb_cctf_025pe_2stops](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/0/e067f943026718f3c5801b98060396d327f060b5_2_330x165.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/0/e067f943026718f3c5801b98060396d327f060b5_2_330x165.png)

hanatos2025_srgb_cctf_025pe_2stops1000×500 337 KB](/uploads/short-url/w1bIo9i40qFBHlAR2nR3TGCPcQB.png?dl=1)

[[![mallett2019_srgb_cctf_025pe_2stops](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/c/2c34f298bf1a587ec16e8eb4a70eac831c94f3ff_2_330x165.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/c/2c34f298bf1a587ec16e8eb4a70eac831c94f3ff_2_330x165.png)

mallett2019_srgb_cctf_025pe_2stops1000×500 342 KB](/uploads/short-url/6j4rO2D5KrQhAtWrKw0YUeYnlGT.png?dl=1)

我们也可以将图像作为线性 Rec2020 导入，并探索 Rec2020 色彩空间的边缘。

（左）`hanatos2025` 和（右）`mallett2019`，Kodak Portra 400 和 Portra Endura

[[![hanatos2025_rec2020_linear_1pe_0stops](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/c/bc80d1968b0f038386c012b647d71809eb4a83b6_2_330x165.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/c/bc80d1968b0f038386c012b647d71809eb4a83b6_2_330x165.png)

hanatos2025_rec2020_linear_1pe_0stops1000×500 540 KB](/uploads/short-url/qTzKWQkndQ7PACA4raCLjW6DYYm.png?dl=1)

[[![mallett2019_rec2020_linear_1pe_0stops](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/5/65c52ba75501c73ff0d5dff9d47f1644e787d928_2_330x165.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/5/65c52ba75501c73ff0d5dff9d47f1644e787d928_2_330x165.png)

mallett2019_rec2020_linear_1pe_0stops1000×500 556 KB](/uploads/short-url/ewiEWCkkBE96LbDtnLg22oawcbK.png?dl=1)

0 档，1.0 打印曝光

[[![hanatos2025_rec2020_linear_025pe_2stops](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/4/24b0897098952591ba2e55668b99efe71d23025b_2_330x165.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/4/24b0897098952591ba2e55668b99efe71d23025b_2_330x165.png)

hanatos2025_rec2020_linear_025pe_2stops1000×500 355 KB](/uploads/short-url/5ezpSEQeWMRumrQgN53cIh8lJNh.png?dl=1)

[[![mallett2019_rec2020_linear_025pe_2stops](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/d/6de5cc84c0fcedc90c525ee88257be6dec1ca595_2_330x165.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/d/6de5cc84c0fcedc90c525ee88257be6dec1ca595_2_330x165.png)

mallett2019_rec2020_linear_025pe_2stops1000×500 359 KB](/uploads/short-url/fGcnWn3TUrECvyfercV0VmCiKHz.png?dl=1)

+2 档，0.25 打印曝光

`hanatos2025` 在 Rec2020 的非常蓝的角落存在一些问题，而 `mallett2019` 的 sRGB 裁剪非常明显。在大色彩空间上的表现 `hanatos2025` 明显更好，这并不令人意外。

---

## #93 **Andrea** (@arctic) · 2025-02-23 18:45

> **@hanatos** (帖子 #91):
> …我无论如何都无法从中得到中性的还原效果：

这也曾是我长期以来的巨大挣扎。我见过所有可能的奇怪颜色。

彩色放大机使用钨丝灯泡（约 3200K），相纸的灵敏度是针对它平衡的，即与红色相比，它们对蓝色的灵敏度更强。在模拟中，我使用 3200K 的黑体发射光谱。

这是 Kodak Portra Endura 灵敏度的一个例子。

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/6/a6ba9b6fbf83b15f08191b275dc652e34cd3e7e1.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/6/a6ba9b6fbf83b15f08191b275dc652e34cd3e7e1.png)

image474×403 33.4 KB](/uploads/short-url/nMX3YtLpu8fdfWGPE8Y2vIrHHeV.png?dl=1)

现在我总是将青滤镜固定在 0.35（在 0-1 范围内），平均而言黄滤镜为 0.6-0.8，品红滤镜为 0.4-0.6。python 包中使用的值在 `agx_emulsion/data/profiles` 中拟合的中性滤镜 `.json` 文件中。

另外，在实际暗房工作流程中，不应触碰 C 滤镜，只应使用 Y 和 M 滤镜。

> **@hanatos** (帖子 #91):
> 我也没有使用任何 D50 或 D55 照明体…但我觉得照明体 E 相差不太远。

这可能是对的，我只是用它们作为查看印相（D50，用于计算最终的 XYZ >> RGB 以查看印相）和 kodak 中性密度测量（D55）的推荐值。但在模拟中并未使用（或者说 `mallett2019` 使用了它们）。

---

## #94 **jo** (@hanatos) · 2025-02-23 18:52

> **@arctic** (帖子 #92):
> hanatos2025 在 Rec2020 的非常蓝的角落存在一些问题，

嗯，这会不会是光谱峰值比用于积分的 5nm 间隔窄得多的情况？这或许可以解释某种蓝色形状的亮度急剧下降。我想既然我们知道峰值在哪里，我们可以设计专门的正交规则/蒙特卡洛重要性采样。

---

## #95 **Andrea** (@arctic) · 2025-02-23 19:05

我最终以 1 nm 分辨率计算光谱（应该足够了吧？），用 2.5 nm sigma 高斯核（约 6 nm FWHM）进行模糊，然后以 5 nm 步长重新采样。问题可能仍然存在。我可以尝试模糊更多，看看亮度下降是否改善。

编辑：

这是以 0.5 nm 步长计算光谱，用 10 nm sigma 模糊，然后以 5 nm 步长重新采样的结果。

[[![hanatos2025_rec2020_linear_025pe_2stops_05nm_compu_10nmsigma_blur](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/6/360003eff2d464f12b1f0c38ba2644a893dd6953_2_690x345.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/6/360003eff2d464f12b1f0c38ba2644a893dd6953_2_690x345.png)

hanatos2025_rec2020_linear_025pe_2stops_05nm_compu_10nmsigma_blur1000×500 333 KB](/uploads/short-url/7HHOC4tagJSV9RuciwxgeBhdRF9.png?dl=1)

---

## #96 **jo** (@hanatos) · 2025-02-24 07:55

嗯好吧谢谢。所以你是说它看起来就是这样。这些渐变图像是怎么生成的？可能是某种 HSV 的东西然后转换成 RGB，然后简单地被重新解释为 Rec2020…没人说这本身就是平滑的。

---

## #97 **Andrea** (@arctic) · 2025-02-24 08:52

> **@hanatos** (帖子 #96):
> 这些渐变图像是怎么生成的？可能是某种 HSV 的东西然后转换成 RGB

更糟，只是色彩空间边缘上的一些任意渐变。"压力测试图像"的底部部分是通过将下面的 RGB 图从 0 缩放到 1 制作的。

确实我不太喜欢它。我只是在（非科学场合）比较胶片模拟时看到过它们。所以我同意这是一个有点愚蠢的定性比较。

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/0/50fb35a9749c6b61e90e4929e7039f82d696b18c.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/0/50fb35a9749c6b61e90e4929e7039f82d696b18c.png)

image547×420 32.7 KB](/uploads/short-url/byopwNsrMSXBdmhstKXDaZl4ona.png?dl=1)

CIECAM16 明度看起来非常尖锐，所以不连续性应该是预期的。我得找到更好的方法。

此外，光谱与灵敏度的相互作用以及胶片模拟管线的后续部分可能并不简单。

---

## #98 **jo** (@hanatos) · 2025-02-24 12:15

一些更详细的问题：

- density_cmy 是每个像素 3 个通道，按名称分别保存 c、m、y，是按这个顺序吗？因为灯滤镜的顺序是 ymc。
- 如何得到 density_cmy？是通过 density_curves lut 对 log_raw (rgb) 进行逐通道查找吗？比如 log_raw.r → density_curves.r → density_cmy.r？
- 如何从 density_cmy 和染料密度得到光谱密度？dye_density 是三个光谱量，所以我将 density_cmy.r 乘以 dye_density.r[wavelength]，对 r,g,b 分别做，然后求和三个光谱？（然后加上最小密度/第四通道乘以某个常数，与 density_cmy 无关）
- 滤镜是透射滤镜，对吗？所以我通过将"强度"与常数 1.0 光谱混合来混入滤镜的"强度"，然后乘以所有三个光谱滤镜（对于 c,m,y）。

---

## #99 **Bob** (@PhotoPhysicsGuy) · 2025-02-24 12:58

> **@hanatos** (帖子 #96):
> 没人说这本身就是平滑的。

这是你拥有的任何 RGB 立方体的外表面。立方体的角和边不平滑（这是显然的），但立方体的面可以尽可能平滑。

青色表现不同于黄色这一点很奇怪，恕我直言。

（在测试 LUT 或 DRT 时，立方体的面至少应该保持平滑，不产生更多扭结。此外，色域边缘和角落也可以被转换为平滑的边缘/角落。例如，通道串扰会平滑边缘。这是一个压力测试，因为它对输入 RGB 基向量及其混合进行采样。如果输出是平滑的，那么靠近 [0,0,0] 到 [1,1,1] 轴的东西可能也表现良好，除非是非常糟糕的 LUT。）

---

## #100 **Andrea** (@arctic) · 2025-02-24 14:57

> **@hanatos** (帖子 #98):
> density_cmy 是每个像素 3 个通道，按名称分别保存 c、m、y，是按这个顺序吗？因为灯滤镜的顺序是 ymc。

顺序 CMY（类似于 RGB）对于变量 `density_cmy` 是正确的，并在各处使用，除了放大机滤镜。选择将拟合的中性滤镜设为 YMC 是因为研究物理放大机数据表的结果，例如我读过一些 Durst 的资料。

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/9/8/986093b3fabcf138539a7b18d63f46c6a4249446.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/9/8/986093b3fabcf138539a7b18d63f46c6a4249446.jpeg)

image597×523 31.9 KB](/uploads/short-url/lJZuqfUC3majZCCY8AIgi21JSey.jpeg?dl=1)

在 Durst 的物理设备和他们的手册中，滤镜的顺序通常是 YMC。Y 大致控制色温，M 控制色调。对于代码来说这可能是一个不幸的选择。

> **@hanatos** (帖子 #98):
> 如何得到 density_cmy？是通过 density_curves lut 对 log_raw (rgb) 进行逐通道查找吗？比如 log_raw.r → density_curves.r → density_cmy.r？

是的！

我将 `raw` 计算为辐照度光谱和灵敏度的乘积，然后在波长上积分。

<pre data-code-wrap="python"><code class="lang-python">raw = contract('ijk,km->ijm', spectra, sensitivity)
</code></pre>

我确保 `raw` 被归一化，使得我认为应该是图像中中灰色的任何值都为 1（仅通过绿色通道归一化）。并应用曝光。

<pre data-code-wrap="python"><code class="lang-python">illuminant = spectra_lut[-1,-1,-1] # spectrum for input linear RGB=[1,1,1]
raw_midgray = np.einsum('k,km->m', illuminant*0.184, sensitivity) # use 0.184 as midgray reference
raw /= raw_midgray[1]

raw *= 2**exposure_ev
</code></pre>

然后我对 `density_curves`（同样是 RGB/CMY 顺序）进行线性插值，该曲线在 x 轴变量 `log_exposure` 上表示，两者都在 json 中，使用计算出的 `log_raw` 数据（`log10(raw)`）。

> **@hanatos** (帖子 #98):
> 如何从 density_cmy 和染料密度得到光谱密度？dye_density 是三个光谱量，所以我将 density_cmy.r 乘以 dye_density.r[wavelength]，对 r,g,b 分别做，然后求和三个光谱？（然后加上最小密度/第四通道乘以某个常数，与 density_cmy 无关）

听起来没错！

`density_cmy` 逐通道乘以 `dye_density` 光谱。第四列 `dye_density[:,3]` 是最小密度，它是相加的。

<pre data-code-wrap="python"><code class="lang-python">def compute_density_spectral(profile, density_cmy):
    density_spectral = contract('ijk, lk->ijl', density_cmy, profile.data.dye_density[:, 0:3])
    density_spectral += profile.data.dye_density[:, 3] * profile.data.tune.dye_density_min_factor
    return density_spectral
</code></pre>

在这段代码片段中：`ij` 是图像的像素，`k` 是 CMY 通道，`l` 是波长。

> **@hanatos** (帖子 #98):
> 滤镜是透射滤镜，对吗？所以我通过将"强度"与常数 1.0 光谱混合来混入滤镜的"强度"，然后乘以所有三个光谱滤镜（对于 c,m,y）。

滤镜是透射式的，来自 Thorlabs 数据表（仅 CMY 那些）：

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/f/f/ff4296d49ca52ccfa45f220f183f0c223997fb37.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/f/f/ff4296d49ca52ccfa45f220f183f0c223997fb37.png)

image918×567 33.8 KB](/uploads/short-url/Aq8q8JPRlC4ToEmqvRlzTV3UhTh.png?dl=1)

在我的代码中，我混合滤镜并将它们应用到 3200K 黑体照明体，代码如下：

```
dimmed_filters = 1 - (1-filters)*ymc_filter_values # following durst 605 wheels values, with 170 max
total_filter = np.prod(dimmed_filters, axis=1)
filtered_illuminant = illuminant*total_filter

```

这里 `filters` 是一个数组 [波长, ymc_channels]，`ymc_filter_values` 是一个 1D 数组，三个滤镜值在 0-1 范围内。

---

## #101 **Andrea** (@arctic) · 2025-02-24 15:00

> **@PhotoPhysicsGuy** (帖子 #99):
> 这是你拥有的任何 RGB 立方体的外表面。立方体的角和边不平滑（这是显然的），但立方体的面可以尽可能平滑。
> 青色表现不同于黄色这一点很奇怪，恕我直言。

那说得通。

我正在调查青色异常行为，这仅在过曝胶片时才明显。所以可能应该保留/手动引入一些通道间的串扰来保证去饱和。这很可能与胶片/相纸配置文件创建的某些方面密切相关。

---

## #102 **jo** (@hanatos) · 2025-02-24 15:17

太棒了。我想大部分情况下我做的完全一样。我想大概是曲线/X 位置的某种对齐…以及对 M Y 滤镜的练习。但我已经喜欢已有的结果了：

[[![20250224_15h26m49s_grim](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/b/2be98001c1933e663df73e1424580a04782694ba_2_690x626.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/b/2be98001c1933e663df73e1424580a04782694ba_2_690x626.png)

20250224_15h26m49s_grim1521×1380 1.75 MB](/uploads/short-url/6gsNLGUICDL3nUY5p92EuI7QYci.png?dl=1)

现在我想在清理和推送之前至少做*一些*颗粒…

---

## #103 **Andrea** (@arctic) · 2025-02-24 15:38

真快！

[![:star_struck:](https://discuss.pixls.us/images/emoji/apple/star_struck.png?v=12)](https://discuss.pixls.us/images/emoji/apple/star_struck.png?v=12)

越来越接近了

[![:+1:](https://discuss.pixls.us/images/emoji/apple/+1.png?v=12)](https://discuss.pixls.us/images/emoji/apple/+1.png?v=12)

干得好！

如果你需要任何关于颗粒的输入，我可以帮忙。

我在模拟颗粒时使用泊松和二项式随机数。并根据颗粒大小（或者说每个颗粒的密度量）应用高斯模糊。我想 GPU 上有疯狂快速的随机数生成器。

---

## #104 **jo** (@hanatos) · 2025-02-24 15:46

> **@arctic** (帖子 #103):
> 如果你需要任何关于颗粒的输入，我可以帮忙。

是的请。

[![:smiley:](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)

那个数据。每个密度 3x3。那是什么？像是 1e-80 之类的，显然不再是 32 位浮点数了。而且，如果我没读错的话，它是按照 density_curves 给出的数据位置重采样的。我可以直接将它重采样到均匀的密度分布吗？这样我就可以对所有配置一视同仁，并存储在同一个纹理中。

编辑：也许我没有看完整的数组…对于更高的密度，数字变得正常多了…

---

## #105 **Andrea** (@arctic) · 2025-02-24 16:59

> **@hanatos** (帖子 #104):
> 那个数据。每个密度 3x3。那是什么？像是 1e-80 之类的，显然不再是 32 位浮点数了。而且，如果我没读错的话，它是按照 density_curves 给出的数据位置重采样的。

在 json 中有 `density_curve_layers`。这个数组同样在相同的 `log_exposure` 轴上表示 [log_exposure, sub_layers, main_layer]。子层从最敏感的大颗粒到最不敏感的小颗粒排序。

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/a/aa2d10a824e367d1e3da8250f336f5f509e0eb55.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/a/aa2d10a824e367d1e3da8250f336f5f509e0eb55.png)

image567×432 44.6 KB](/uploads/short-url/ohrIJbYZCWmWLGkWD74IzJ6BRWt.png?dl=1)

上面是一个例子，其中 RGB 总和是 `density_curves`，而剩下的九条曲线是 `density_curves_layers`。`density_curves_layers` 沿子层轴的总和得到 `density_curves`。我们也可以有它们的函数版本，基于高斯 CDF。

用密度而不是 log_exposure 进行插值的奇怪事情是 DIR 成色剂模型的结果。当应用 DIR 成色剂时，我们需要做一些技巧，`log_raw`-`density_cmy` 的关系不再简单地由 `density_curves` 给出。为了解决这个问题，由于 `density_curves` 是单调的，我使用它来根据成色剂后层的最终总密度（`density_cmy`）插值给定子层的密度（`density_cmy_layers`）。另一种方法是输出一个有效的 `log_raw_after_dir_couplers` 并用它进行插值。

---

## #106 **Jakob Andrén** (@jandren) · 2025-02-24 18:25

哈哈你们两个真是快得疯狂！

关于测试光谱上采样的话题，我内心的工程师喜欢任何 RGB 输入都能有稳健且平滑的结果的证明。RGB 色域边界是生成这种结果的一种方式。这是我在用一些 python 黑客手段生成的另一种可能性。

[[![Constant sum test clipped preview](https://d2x313g9lpht1q.cloudfront.net/original/3X/6/8/6849a506d28a69b843f46f3995ac26fa5f8ca788.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/6/8/6849a506d28a69b843f46f3995ac26fa5f8ca788.png)

Constant sum test clipped preview1111×1127 33.8 KB](/uploads/short-url/eSzrgHRE6itZSqE4AJFN48lIMhW.png?dl=1)

[constant_sum.exr](/uploads/short-url/iAED154mxIU4alW6i6WHxrCD6SF.exr) (3.7 MB)

以及如果你想修改任何东西的脚本。

[generate_constant_sum_slice.py](/uploads/short-url/kMGvxq7emYczD196CjHZnr66gSj.py) (948 Bytes)

它提供了 RGB 体积的一个等和切片，即一个法线为 [1, 1, 1] 的平面，有效三角形周围有大量的"负色"。确保这个测试平面在低、中和高曝光（即"所有情况"）下都能良好工作，这应该是光谱上采样工作良好的一个很好的证明。这是我计划测试的内容，但我无法在你这么快的节奏下及时提供结果，所以我希望一个建议的测试图像能有所帮助。

我的期望是，所有颜色，甚至单色激光，最终都会变白。

---

## #107 **** (@mikae1) · 2025-02-24 20:06

> **@hanatos** (帖子 #102):
> 我已经喜欢已有的结果了

[![:star_struck:](https://discuss.pixls.us/images/emoji/apple/star_struck.png?v=12)](https://discuss.pixls.us/images/emoji/apple/star_struck.png?v=12)

> **@hanatos** (帖子 #102):
> 现在我想在清理和推送之前至少做一些颗粒…

从管线角度来看，实现颗粒很有意思。在插值*之后*添加颗粒是隐藏插值伪影的最佳方法之一。如果图像通过 Alien Skin Exposure 的彩色胶片模拟进行后插值处理，我那 2100 万像素的 5D Mark II 文件在最长边接近 100 厘米时看起来非常棒。我在做展览打印工作时经常使用这个。这总是意味着我不能在 darktable 或 Lightroom 中完成所有工作。

另一方面，对已经应用了颗粒的图像进行放大，看起来相当糟糕。

我已经很久没有试过 vkdt 了（看起来很快就会改变！），是否可以在插值/放大之后放置模块/效果？

---

## #108 **jo** (@hanatos) · 2025-02-24 20:43

> **@mikae1** (帖子 #107):
> 是否可以在插值/放大之后放置模块/效果？

嗯，我有显式的 resize 节点，如果两端不一致，它们会指示图在何处更改分辨率。对于胶片模拟，我可能会制作一个显式的上采样功能，从输入图像进行插值 / Catmull-Rom 插值，然后在输出尺寸上模拟颗粒。

无法告诉你我有多享受*生成*噪点。通常我整天都在试图*减少*估计器中的噪点…

[[![20250224_21h43m05s_grim](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/0/7035b639b90f322bf9eb84ee90c8334e0ad46c59_2_659x1000.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/0/7035b639b90f322bf9eb84ee90c8334e0ad46c59_2_659x1000.png)

20250224_21h43m05s_grim907×1375 2.14 MB](/uploads/short-url/g0EykxpXKbxk6HkEAPoyakiAFvP.png?dl=1)

---

## #109 **** (@mikae1) · 2025-02-24 21:00

> **@hanatos** (帖子 #108):
> 对于胶片模拟，我可能会制作一个显式的上采样功能，从输入图像进行插值 / Catmull-Rom 插值，然后在输出尺寸上模拟颗粒。

如果我理解对了，那意味着颗粒是在上采样之后应用的？那就太…棒了！

> **@hanatos** (帖子 #108):
> 无法告诉你我有多享受生成噪点。通常我整天都在试图减少估计器中的噪点…

并不是所有的噪点/颗粒都是相同的！享受你的上采样伪装吧。

[![:smiley:](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)

---

## #110 **Andrea** (@arctic) · 2025-02-25 00:41

> **@jandren** (帖子 #106):
> 哈哈你们两个真是快得疯狂！

我最近有些空闲时间（虽然不总是这样），对 [@hanatos](/u/hanatos) 的光谱上采样方法有点过于兴奋了。

[![:grin:](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)

在我看来，它在实际测试中确实改进了结果。至少我更喜欢图像了。

> **@jandren** (帖子 #106):
> 以及如果你想修改任何东西的脚本。
> generate_constant_sum_slice.py (948 Bytes)

谢谢分享！

[![:smiley:](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)

> **@jandren** (帖子 #106):
> 我的期望是，所有颜色，甚至单色激光，最终都会变白。

我不是专家，但这听起来是一个合理的期望。

对于我正在做的胶片模拟，我担心如果某个通道的灵敏度在单色激光的波长处恰好为零（目前的数据就是这种情况），那么该层将不会产生密度。使得最终印相更难达到白色。此外，如果显影过程中在某一层产生的染料（假设是对激光有非零灵敏度的那一层）在光谱的所有区域都没有残余吸收，那么达到白色可能会更加困难。这也是因为存在可以产生的最大密度。

这是很好的输入。我可以尝试使灵敏度平滑衰减，使它们永远不会恰好为零。在正常条件下这不会太大改变最终图像，但会改善过曝时的去饱和行为。

> **@jandren** (帖子 #106):
> 这是我计划测试的内容，但我无法在你这么快的节奏下及时提供结果，所以我希望一个建议的测试图像能有所帮助。

我应该如何处理这里的负色？可能是我实现的一个限制：例如，如果我在线性 Rec2020 中导入图像，我无法要求在此之外生成光谱。hanatos 的算法实际上可以在整个可见色域上工作，但为了优化，我预烘焙了一个 Rec2020 LUT。

我应该例如在线性 Rec709 中导入吗？这是你所设想的吗？

目前我计算了一些默认模拟（Kodak Gold 和 Portra Endura），在线性 sRGB (Rec 709) 中导入。可能我们应该隔离光谱上采样部分来更好地研究这个方面，而且与胶片模拟的交互在我看来也非常有趣。另外，它们看起来色彩丰富且有趣，值得分享。

它们可能会显示我代码中的一些明显错误。可以肯定的是，在光谱上采样之前，我转换到线性 Rec2020 并裁剪负值，保留上界无界。这样才能使用我的光谱 LUT。

（左）hanatos2025，（右）mallett2019

[[![hanatos2025_linear_srgb](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/d/ad7a440424f0c1fe294969437ef61f850a0a0f46_2_330x330.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/d/ad7a440424f0c1fe294969437ef61f850a0a0f46_2_330x330.png)

hanatos2025_linear_srgb1024×1024 904 KB](/uploads/short-url/oKEyr1kAx5kr54h08zTVu8Nn7MO.png?dl=1)

[[![mallett2019_linear_srgb](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/5/f57ba01555795b24dcd5263cf3fb7bbe00bc07b6_2_330x330.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/5/f57ba01555795b24dcd5263cf3fb7bbe00bc07b6_2_330x330.png)

mallett2019_linear_srgb1024×1024 1.22 MB](/uploads/short-url/z1DQtaBJSkWAZg5cZF9zqVAR8cS.png?dl=1)

---

## #111 **Andrea** (@arctic) · 2025-02-25 00:45

这可真是颗粒！！！

[![:sunglasses:](https://discuss.pixls.us/images/emoji/apple/sunglasses.png?v=12)](https://discuss.pixls.us/images/emoji/apple/sunglasses.png?v=12)

不能说在这张图像上看着很享受

[![:smile:](https://discuss.pixls.us/images/emoji/apple/smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smile.png?v=12)

，但这是一个好的开始！我对你的速度感到惊讶，当然还有 vkdt 的速度。

---

## #112 **jo** (@hanatos) · 2025-02-25 07:39

> **@arctic** (帖子 #111):
> 这可真是颗粒！！！

嘿嘿是的，完全无厘头，基本上就是 `binom(poisson(something made up of thin air that looks almost like the density))`。当然不是它最终会看起来/在你的代码中看起来的样子。

---

## #113 **jo** (@hanatos) · 2025-02-25 15:31

不确定这张测试图像是否特别相关。我的意思是这些坐标远远超出了范围：

[[![20250225_16h21m28s_grim](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/6/86b83a438a49b1c599b6378d6df36ddc97aaf5d6_2_690x426.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/6/86b83a438a49b1c599b6378d6df36ddc97aaf5d6_2_690x426.png)

20250225_16h21m28s_grim1981×1224 366 KB](/uploads/short-url/jdMGAcIRIsiBrnMih4noLucwdN4.png?dl=1)

任何哪怕部分有意义的输入设备变换都会确保这些值稍微更真实一些。这些甚至不接近光谱轨迹。这里我标记了所有在超大的 Rec2020 色域内（它触及光谱轨迹的边界）的值（将输入解释为 rec709/线性）：

[[![20250225_16h23m56s_grim](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/2/f227f2b1b226d0fbcb947c989de4740a6bad744f_2_690x436.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/2/f227f2b1b226d0fbcb947c989de4740a6bad744f_2_690x436.png)

20250225_16h23m56s_grim1914×1212 195 KB](/uploads/short-url/yyd8r9ioUGpUxyLK8xiLnVWwa1F.png?dl=1)

编辑：这是光谱轨迹：

[[![20250225_16h35m04s_grim](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/f/dfdba257f4445baea8b13e5dc7e1adc6964b7757_2_690x515.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/f/dfdba257f4445baea8b13e5dc7e1adc6964b7757_2_690x515.png)

20250225_16h35m04s_grim1582×1183 117 KB](/uploads/short-url/vWl2tr7DXXHFW3Yb4oMsQNEpVVd.png?dl=1)

所以如果真要说，它会测试上采样图的色域外修复。

---

## #114 **Andrea** (@arctic) · 2025-02-25 22:49

> **@hanatos** (帖子 #113):
> 20250225_16h21m28s_grim1981×1224 366 KB
> 20250225_16h21m28s_grim1981×1224 366 KB

绘制 xy 色度图非常能说明图像的极端范围。谢谢分析！

在这些评论之后，我找了些乐子，也尝试制作了另一个场景参考测试图像，更侧重于验证整个模拟的平滑性；同时试图保持在足够大的色域内，以有意义地展示光谱上采样的能力。我还希望它是 HDR 的。

我的尝试看起来像这样：

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/f/af71edfdbf0d7ffd1a660cd02da1d06590b4fe53.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/f/af71edfdbf0d7ffd1a660cd02da1d06590b4fe53.png)

image554×296 21.9 KB](/uploads/short-url/p23EksHrRLD6tqhDQQp0NexsERJ.png?dl=1)

[gradient_hdr_rgb.exr](/uploads/short-url/poUxhtqgMeUXuLowQ7ok1Gp1ex.exr) (390.8 KB)

<details>
<summary>
Code</summary>

<pre data-code-wrap="python"><code class="lang-python">from agx_emulsion.utils.io import save_image_oiio
import numpy as np
import scipy.ndimage
import matplotlib.pyplot as plt

N = 64
x=np.linspace(0, 1, 2*N)
y=np.logspace(12, -6, 4*N, base=2) * 0.184
z = np.zeros_like(x)
grad_rg = np.stack((x,1-x,z), axis=-1)
grad_gb = np.stack((z,x,1-x), axis=-1)
grad_br = np.stack((1-x,z,x), axis=-1)
grad = np.concatenate((grad_br,grad_gb,grad_rg, grad_br,grad_gb,grad_rg), axis=0)
grad = scipy.ndimage.gaussian_filter(grad, (2*N/4,0), mode='wrap')
grad = grad[:8*N,:]
grad /= np.sum(grad,axis= -1)[:,None]
grad = grad[np.newaxis,:,:] * y[:,np.newaxis,np.newaxis]
grad = np.fliplr(grad)
save_image_oiio('gradient_rgb.exr', grad, bit_depth=32)
plt.imshow(grad)
</code></pre>

</details>

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/b/5/b5611747375800ce105d2dcbe021c97a2c796a8c.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/b/5/b5611747375800ce105d2dcbe021c97a2c796a8c.png)

image547×403 29.8 KB](/uploads/short-url/pSyrbDif9CWvhWwPhH7hrADh8YY.png?dl=1)

图像是通过用对数间隔的幅度缩放这些 RGB 轮廓制作的。基础轮廓的 RGB 之和为 1，强度范围从 -6 到 +10 档的 0.184 中灰（即 [0.184,0.184,0.184] * 缩放因子）。

如果解释为 Rec2020，它涵盖了 xy 色度空间中的这个轮廓：

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/9/a/9a7e3fd3e24fde1771f9479e5283c387e9987b45.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/9/a/9a7e3fd3e24fde1771f9479e5283c387e9987b45.png)

image630×605 54.2 KB](/uploads/short-url/m2I18FwEY9YVzpEd86tfRk7LS0R.png?dl=1)

它不会到边缘，但试图保持平滑。

使用默认模拟（停用自动曝光）我们得到：

Kodak Gold 200 和 Kodak Portra Endura，（左）hanatos2025（右）mallett2019

[[![gradient_hdr_rgb_gold_portra](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/0/a0f8e19ac05c3465f0a055fdbedb5f0632272ea0.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/0/a0f8e19ac05c3465f0a055fdbedb5f0632272ea0.png)

gradient_hdr_rgb_gold_portra448×256 56 KB](/uploads/short-url/mY1CuQCK19Q2dBpmhfECb3vGayY.png?dl=1)

[[![gradient_hdr_rgb_gold_portra_mallett2019](https://d2x313g9lpht1q.cloudfront.net/original/3X/b/3/b3cb9eba2a9c2a5130915cf2fdae4b946781e398.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/b/3/b3cb9eba2a9c2a5130915cf2fdae4b946781e398.png)

gradient_hdr_rgb_gold_portra_mallett2019448×256 53.9 KB](/uploads/short-url/pExIHWpndgjRUSEiZCenJsZm9S0.png?dl=1)

以及 Kodak Portra 400 和 Kodak Portra Endura，（左）hanatos2025（右）mallett2019

[[![gradient_hdr_rgb_portra_portra](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/c/acf45cfb37256b46058ba5a8c4dfd82181b40676.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/c/acf45cfb37256b46058ba5a8c4dfd82181b40676.png)

gradient_hdr_rgb_portra_portra448×256 55 KB](/uploads/short-url/oG1FA4WO8UV7g0ZcgZ0R52EqWKW.png?dl=1)

[[![gradient_hdr_rgb_portra_portra_mallett2019](https://d2x313g9lpht1q.cloudfront.net/original/3X/1/d/1d141ff0564a686290e400e0c4b918b93a0c51ff.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/1/d/1d141ff0564a686290e400e0c4b918b93a0c51ff.png)

gradient_hdr_rgb_portra_portra_mallett2019448×256 53.8 KB](/uploads/short-url/49eXKDkhbptjAUlLMRVPUIYNs9F.png?dl=1)

我仔细看了看青色区域，以了解"青色不连续性"。如果我们在 x 轴大约 2/3 处取一个垂直截面，我们得到：

（左）sRGB 输出，（右）线性 Rec2020 输出

[[![gradient_hdr_rgb_gold_portra_section310_srgb](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/d/0d3dd46ec7ef5d34131a0be8b6cd0c5da1f4aff9.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/d/0d3dd46ec7ef5d34131a0be8b6cd0c5da1f4aff9.png)

gradient_hdr_rgb_gold_portra_section310_srgb547×420 22.9 KB](/uploads/short-url/1T8FXWuDMcc81ieCwdee9htUUop.png?dl=1)

[[![gradient_hdr_rgb_gold_portra_section310_linear_rec2020](https://d2x313g9lpht1q.cloudfront.net/original/3X/e/f/eff8670205ef0f564955c0f6bda3c9c8bcbd5f53.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/e/f/eff8670205ef0f564955c0f6bda3c9c8bcbd5f53.png)

gradient_hdr_rgb_gold_portra_section310_linear_rec2020547×420 23 KB](/uploads/short-url/yeSjx879awNe9Bb0tcK4Gmi6aXN.png?dl=1)

sRGB 明显在裁剪，造成了青色中的硬边缘。

输出到 Rec2020（然后在此处浏览器中重新解释为 sRGB）显示了平滑的青色过渡（使用 Kodak Gold 200 和 Portra Endura）。

[[![gradient_hdr_rgb_gold_portra_rec2020](https://d2x313g9lpht1q.cloudfront.net/original/3X/d/8/d86a9e862f0423c042ead2aaa2341efb9563fba1.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/d/8/d86a9e862f0423c042ead2aaa2341efb9563fba1.png)

gradient_hdr_rgb_gold_portra_rec2020448×256 48.7 KB](/uploads/short-url/uSvyZ4oz3JcdEe7tKQJd01j4ynn.png?dl=1)

一切看起来都相当平滑。

也许我们在模拟中过度提高了饱和度（虽然我觉得图像的饱和度水平令人愉悦），或者说物理印相可达到的饱和度无法很好地适应 sRGB 色域，导致容易裁剪。可能是两者的结合。

---

## #115 **** (@ZeroEcks) · 2025-02-25 23:14

感谢你们的出色工作，我试用了这个以及 ART 集成。我觉得非常令人兴奋。

我注意到的唯一突出问题是，在 macos 上使用 agx_emulsiom GUI（未进行色彩管理）时，保存的图层与预览窗口相比，伽马/对比度有显著差异。不幸的是，这有点阻碍实际使用，但可以通过之后调整黑点和对比度部分修复。

我认为这些模拟可能成为开源摄影的真正杀手级功能，我对这些可能性感到兴奋，比如导出底片，我可以使用常规的胶片工作流程来处理，试图统一我的工作流程。我还认为颗粒和光晕效果相当逼真，最终解决了在胶片拍摄的图像中，像素不应该是细节的最小单位的问题。

---

## #116 **Bob** (@PhotoPhysicsGuy) · 2025-02-25 23:17

> **@arctic** (帖子 #114):
> 也许我们在模拟中过度提高了饱和度，或者说物理印相可达到的饱和度无法很好地适应 sRGB 色域，导致容易裁剪。可能是两者的结合。

也许是 Daniele Siragusano 曾经展示过投影印片胶片的色度图？！实际上我记不清是谁了，也许是 Troy Sobotka。

但是它惊人地大，几乎达到了可见光谱的蓝和红角落。

印相中的染料可以在两个通道中足够密集，使得产生的蓝色和红色基本上只传输可见光谱边缘的光。

所以是的，至少在蓝色和红色中，色域远比 sRGB 大。

但我想你可以自己试试，将测试图像不是插入到管线中的负片曝光部分，而是插入到末端，看看你的光谱印相色域在 xy 色度平面上的范围。

编辑：（我知道这有点轶事性质，但我正在试图找到那个色度图…但我找不到。）

---

## #117 **jo** (@hanatos) · 2025-02-26 16:09

一些带有颗粒的初始图像：

这是数码干净版，供参考：

[[![2025-02-26-165519_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/6/564aad62c5b56c0d382dd030d99068fcd540fe03_2_690x388.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/6/564aad62c5b56c0d382dd030d99068fcd540fe03_2_690x388.png)

2025-02-26-165519_hyprshot2160×1215 970 KB](/uploads/short-url/cjn3Ae0t6nP76aUbJ2bKTRENPl9.png?dl=1)

以及应用了颗粒的版本：

[[![2025-02-26-165530_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/c/fcc86d00078661a1f961caac64e699984fe3cd63_2_690x388.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/c/fcc86d00078661a1f961caac64e699984fe3cd63_2_690x388.png)

2025-02-26-165530_hyprshot2160×1215 1.03 MB](/uploads/short-url/A4dJqV9fwlO6KK3AwEDPItobAnV.png?dl=1)

这是按层的颗粒，即只显示三个层中一个层的颗粒，其他两个层以数码干净方式显影：

[[![2025-02-26-165549_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/3/c31ebcc062cae72f49e3ddc96522b85708a6d92b_2_690x388.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/3/c31ebcc062cae72f49e3ddc96522b85708a6d92b_2_690x388.png)

2025-02-26-165549_hyprshot2160×1215 990 KB](/uploads/short-url/rQ6XAye1l4VZC2EFRJETmQKiikX.png?dl=1)

[[![2025-02-26-165557_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/5/1589ef8ce43ef6e2b30fb9b3eeaed3db4010c4f3_2_690x388.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/5/1589ef8ce43ef6e2b30fb9b3eeaed3db4010c4f3_2_690x388.png)

2025-02-26-165557_hyprshot2160×1215 1.01 MB](/uploads/short-url/34xyh8WEna4qTrIW17AquvtlXGj.png?dl=1)

[[![2025-02-26-165607_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/5/7514bc1a236295735738abb043c9df35812f12d2_2_690x388.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/5/7514bc1a236295735738abb043c9df35812f12d2_2_690x388.png)

2025-02-26-165607_hyprshot2160×1215 1.01 MB](/uploads/short-url/gHKhRq3zE8eScdOPXlWqSECElZo.png?dl=1)

我只是从 agx gui 中取了颗粒颜色/层面积乘数。我的数学不太干净，希望不会被抓到

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

好消息是，应用颗粒后速度只是稍微慢了一点。从 25 毫秒上升到 28 毫秒（全分辨率）。

我发现颗粒对图像有贡献，使其看起来更清晰，这非常酷。

下一步：使 2 倍或 4 倍上采样选项可用，然后实现 DIR。

---

## #118 **Chris E** (@elstoc) · 2025-02-26 16:30

> **@hanatos** (帖子 #117):
> 我发现颗粒对图像有贡献，使其看起来更清晰。

这正是我看到你的图像时的想法。不过，当你同时看两者时，原始图像明显更清晰（例如睫毛）。

---

## #119 **Bastian Bechtold ** (@bastibe) · 2025-02-26 16:49

> **@hanatos** (帖子 #117):
> 我发现颗粒对图像有贡献，使其看起来更清晰。

我有时会对看起来太柔和的图像添加噪点以便打印。纹理纸也有类似的效果。

---

## #120 **jo** (@hanatos) · 2025-02-26 19:19

哦天哪，我不得不再说一遍…这个模拟真是太酷了。我刚刚轻松花了一个小时转换了一堆照片。最随意的镜头在应用了 filmsim 后都变成了魔法…肤色深沉，阴影令人兴奋…滚降柔和恰到好处…

我唯一挣扎的是白平衡，我可能会将白平衡权重的 json/列表转换为一些随胶片/相纸组合变化的 vkdt 预设。如果有人想测试我的 WIP，vkdt git master 已经包含了。（[文档在此](https://jo.dreggn.org/vkdt/src/pipe/modules/filmsim/readme.html)，你需要 `filmsim.lut` 数据文件，然后将 `filmsim.pst` 应用到任何你想要的图像上：在暗房模式下按 `ctrl-p`，输入 `filmsim` 然后按 `enter`）。

---

## #121 **** (@mikae1) · 2025-02-26 21:10

> **@hanatos** (帖子 #120):
> 哦天哪，我不得不再说一遍…这个模拟真是太酷了。

我非常认同你的兴奋！我在看到 [@arctic](/u/arctic) 神秘的 PlayRaw 贡献几个月后，就给他发了早期的粉丝私信。

[![:smiley:](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)

[这个例子](https://discuss.pixls.us/t/cabo-santa-maria-boa-vista/43527/9) 在五月引起了我的注意。

可惜的是，我还没能成功地在我基于 Fedora 的 Aurora 安装上使用 `pip` 运行它，所以目前我只能等待你们在这个帖子中的更新。

[![:smiley:](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)

看到有人推荐 `uv`。希望这周末试试！也许你的 vkdt 实现可以让像我这样的 Python 白痴更容易上手。

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

> **@hanatos** (帖子 #120):
> 我刚刚轻松花了一个小时转换了一堆照片。最随意的镜头在应用了 filmsim 后都变成了魔法…肤色深沉，阴影令人兴奋…滚降柔和恰到好处…

是的，我在看到的许多例子中，滚降看起来好得不可思议。至于颜色…我们不应忘记 Kodak 花了一个世纪来完善他们的色彩。他们的目标不仅仅是准确还原色彩，还要让眼睛感到愉悦。

我真诚地*不*认为对胶片的兴奋纯粹基于炒作或潮流。当然也有实体的元素，但人们花费大量时间试图在 Lightroom 中实现恰当的胶片色彩，最后却用 Adobe 的单色颗粒来收尾…

有点让我惊讶的是，经过约 19 年的 Lightroom 和约 15 年的 darktable，我们仍然停留在彩色图像的单色颗粒上，没有任何尝试去复制胶片的其他特性（比如光晕）。而电影调色师们则拥有所有闪亮的玩具。有 Filmbox、Dehancer，DaVinci Resolve 最近也有了一个很棒的本地 Film Look Creator。Film Look Creator 的目标不是模拟任何特定胶片，而是提供具有大量控制的类胶片效果。在很多方面它看起来与我在这个帖子中看到的非常相似。

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/3/83ccb6c8d8d0ce0796518bbeceb0fbdaecac499a_2_690x716.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/3/83ccb6c8d8d0ce0796518bbeceb0fbdaecac499a_2_690x716.png)

image1230×1278 98.1 KB](/uploads/short-url/iNX94AF72Ozi2KcigTxpB70MqEy.png?dl=1)

使用 darktable 几年后，我对手头的工具还算*基本*满意。在过去的 12 年里，我一直使用试图在数字上模仿 Portra 400 NC 或 VC 外观的工作流程，以前在 Lightroom 中用 VSCO 预设/配置文件，现在在 darktable 中用 G'MIC sRGB Cube LUT。

它并不能复制我看到的 [@arctic](/u/arctic) 的 PlayRaw 例子中胶片的微妙之处。

如果 [@arctic](/u/arctic) 的 filmsim 进入开源软件，我认为我们可以期待开源替代品对 Adobe 产品带来真正的冲击。在静帧软件领域确实没有类似的东西，而需求似乎仍然巨大。

> **@hanatos** (帖子 #117):
> 我发现颗粒对图像有贡献，使其看起来更清晰。

这是一个有趣的观察。正如我早些时候在这个帖子中所说，这是让上采样/插值伪影消失的好方法。我们部分地根据"颗粒层"的清晰度来判断底层图像的清晰度。

---

## #122 **Andrea** (@arctic) · 2025-02-27 00:30

> **@ZeroEcks** (帖子 #115):
> 我注意到的唯一突出问题是，在 macos 上使用 agx_emulsiom GUI（未进行色彩管理）时，保存的图层与预览窗口相比，伽马/对比度有显著差异。不幸的是，这有点阻碍实际使用，但可以通过之后调整黑点和对比度部分修复。

是的，抱歉，这真的只是一个勉强能用的单文件 gui 解决方案。你可以尝试将你的显示器/系统配置文件与 sim 的输出配置文件匹配。上面 [@NateWeatherly](/u/nateweatherly) 在线程中提到了将 DisplayP3 作为可行的解决方案来获得一个过得去的色彩管理预览。看看那个！这里是帖子的链接：

> **@NateWeatherly** (帖子 #56):
> 在 Mac 上，只要有一个 ImageP3 或 DisplayP3 输出 ICC 配置文件，就离色彩管理预览很近了。

另外，我不太热衷于把它作为最终解决方案。我认为其他软件（vkdt、darktable、rawtherapee、art…）有更好的人机界面，所以可能不需要重建所有东西。我把它看作一个技术演示，我在上面非常自如地修改和深入细节。如果它要成为实际工作的可行解决方案，我将来可能会拼凑出更好的东西。目前我的重点一直是引擎和"外观"。但谢谢你的批评！

[![:smiley:](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)

我会记在心里的。

---

## #123 **Andrea** (@arctic) · 2025-02-27 00:41

> **@hanatos** (帖子 #117):
> 从 25 毫秒上升到 28 毫秒（全分辨率）。

我惊掉了下巴，即使它是一个简化版

[![:grin:](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)

…3 毫秒可能比我 hacky python 中仅颗粒生成所需的时间快将近 4 个数量级。

> **@hanatos** (帖子 #117):
> 我发现颗粒对图像有贡献，使其看起来更清晰。

我完全同意这一点，我喜欢放大并添加颗粒的想法。而且在靠近看时看不到像素！通常"像素窥视者"带有负面含义，但我想"颗粒窥视者"只有一种时髦的正面光环。

> **@hanatos** (帖子 #117):
> 我的数学不太干净，希望不会被抓到

嘿嘿，我认为它看起来已经非常棒了！如果你需要一点关于我对颗粒模型假设的背景，我会写一些东西。如果对你有帮助的话！

[![:blush:](https://discuss.pixls.us/images/emoji/apple/blush.png?v=12)](https://discuss.pixls.us/images/emoji/apple/blush.png?v=12)

> **@hanatos** (帖子 #120):
> 我刚刚轻松花了一个小时转换了一堆照片。

我也对此感到内疚，有时候我想在上面工作，但我就是被引导去在随机图片上无休止地尝试。

> **@hanatos** (帖子 #120):
> 我唯一挣扎的是白平衡，我可能会将白平衡权重的 json/列表转换为一些随胶片/相纸组合变化的 vkdt 预设。

我创建滤镜中性值的方法是拟合输入中的单个灰色像素（[0.184,0.184,0.184]），以获得与输出相同的灰色值（我实际上拟合 Y 滤镜、M 滤镜和打印曝光）。我发现滤镜中性值对管线相当敏感，所以不确定它们能否完全保持不变。如果它们能，那就太棒了。

我快速看了一下代码，我很荣幸看到这样的努力，我会尝试多理解一些。而且我还会尝试在我的桌面上用 GPU 运行它，它最近一直在吃灰。

---

## #124 **Olivier** (@olliwa) · 2025-02-27 01:32

在 win11 上也能用

[![:+1:](https://discuss.pixls.us/images/emoji/apple/+1.png?v=12)](https://discuss.pixls.us/images/emoji/apple/+1.png?v=12)

只需解压最新版本

只需两个修正来创建 *filmsim.lut*

```
pip install -r requirements.txt
...
cd agx_emulsion/data/profiles

```

---

## #125 **Andrea** (@arctic) · 2025-02-27 01:59

好评论 [@mikae1](/u/mikae1)！如果你需要任何关于 python 部分的帮助，请告诉我。

> **@mikae1** (帖子 #121):
> 我们不应忘记 Kodak 花了一个世纪来完善他们的色彩。他们的目标不仅仅是准确还原色彩，还要让眼睛感到愉悦。

我 100% 同意，我希望深入挖掘并理解是光谱数据中哪些通用准则编码了这些，目前感觉有些难以捉摸，但可能至少可以部分合理化正在发生的事情。

> **@mikae1** (帖子 #121):
> Film Look Creator 的目标不是模拟任何特定胶片，而是提供具有大量控制的类胶片效果。在很多方面它看起来与我在这个帖子中看到的非常相似。

拥有一个不依赖于光谱数据中隐含的无法理解的知识的通用工具听起来非常酷！

为了好玩，我做了一个对比，使用我在电脑上找到的你引用的 playraw 中的一些图像，全部使用相同的基础数据。我在过去几个月中在不同的阶段处理了几次。它们是独立编辑的（色彩平衡不完全匹配），但我认为它们很好地展示了模拟的演进过程。

[[![sea_side](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/e/9e6bb774262cb644c5cec0b6a894e65ceaebe97e_2_330x220.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/e/9e6bb774262cb644c5cec0b6a894e65ceaebe97e_2_330x220.png)

sea_side1920×1281 4.43 MB](/uploads/short-url/mBsdLOzCUl8EYRim2MY7wgWd6YC.png?dl=1)

[[![sea_side2](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/4/04c4474ee7924311bc44bcd70a821aecc6428632_2_330x220.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/4/04c4474ee7924311bc44bcd70a821aecc6428632_2_330x220.png)

sea_side21920×1281 4.43 MB](/uploads/short-url/GaqX6xDrSS7T4sqKVUV2v05Q1I.png?dl=1)

[[![sea_side_3_dir_couplers](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/2/d2efabc7f0ce44d302f28635876e13918b894455_2_330x220.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/2/d2efabc7f0ce44d302f28635876e13918b894455_2_330x220.png)

sea_side_3_dir_couplers1920×1281 3.76 MB](/uploads/short-url/u61LdxaEk0mPBZcvHMDlkEKwoDz.png?dl=1)

[[![sea_side_4_large_gamt](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/b/fb11ae32a1c925354d70140288ad9f5008b2846a_2_330x220.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/b/fb11ae32a1c925354d70140288ad9f5008b2846a_2_330x220.png)

sea_side_4_large_gamt3000×2002 10.4 MB](/uploads/short-url/zP3IY1NXUfoQGyBsOe5roEv5q30.png?dl=1)

按顺序：

(a) 原始 play raw 提交

(b) 添加更精细的掩蔽成色剂

(c) DIR 成色剂的早期版本

(d) `large-color-gamut` 分支的当前默认输出，从 (c) 我们得到了新的更有效的 DIR 成色剂，加上新的 hanatos 的光谱上采样（以及更多内容）。仅负片/打印曝光从默认值更改。

全部使用 Kodak Portra 400 和 Kodak Ektacolor Edge。

哦天哪…我也不得不再说一次，大色彩空间输入带来的微妙但令人满意的变化让我惊叹。

[![:star_struck:](https://discuss.pixls.us/images/emoji/apple/star_struck.png?v=12)](https://discuss.pixls.us/images/emoji/apple/star_struck.png?v=12)

因为我怎么也看不够，这里还有一张来自 [signatureedits.com](http://signatureedits.com) 的对比照片，全部使用默认设置（Kodak Gold 和 Supra Endura）。输入为 32 位线性 ProPhoto RGB。

（左）darktable 基础编辑，（中）mallett2019，（右）hanatos2025

[[![Signature Edits Free RawsIMG_5824](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/6/c6d1c9ce48945a4b290110428cacf05e852da719_2_220x330.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/6/c6d1c9ce48945a4b290110428cacf05e852da719_2_220x330.jpeg)

Signature Edits Free RawsIMG_58241998×3000 825 KB](/uploads/short-url/smQ0wJQVrWx5vGregBnBn48oO3n.jpeg?dl=1)

[[![mallett2019_gold_supra_default](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/e/2ed8570831a6170b0b209b7cbfb149207ff06d9b_2_220x330.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/e/2ed8570831a6170b0b209b7cbfb149207ff06d9b_2_220x330.png)

mallett2019_gold_supra_default1998×3000 10.6 MB](/uploads/short-url/6Gpt8f0SujtfCr2538Hr073sABB.png?dl=1)

[[![hanatos2025_gold_supra_default](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/2/12dbcaf97f48f794fffb02eced4b5cb6f22655ab_2_220x330.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/2/12dbcaf97f48f794fffb02eced4b5cb6f22655ab_2_220x330.png)

hanatos2025_gold_supra_default1998×3000 10.4 MB](/uploads/short-url/2GPuUj60yogY6M901TJMDrnp5Dt.png?dl=1)

即使试图更好地匹配两个胶片模拟，即通过放大机滤镜，我也无法让它们感觉相同。darktable 的超基础编辑使用相同的白平衡，使用对比度为 2 的 sigmoid，以及 30% 全局鲜艳度的色彩平衡 rgb。

---

## #126 **Andrea** (@arctic) · 2025-02-27 03:21

> **@PhotoPhysicsGuy** (帖子 #116):
> 也许是 Daniele Siragusano 曾经展示过投影印片胶片的色度图？！实际上我记不清是谁了，也许是 Troy Sobotka。

嗯有意思！我试图在学术搜索引擎上快速查找，但没有找到。

我从我手头的书中找到了这些通用数据。确实看起来相当宽，尤其是红蓝两侧。

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/4/54b5cb368b764e77327c9f83d5b5bedf035426c8.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/4/54b5cb368b764e77327c9f83d5b5bedf035426c8.png)

image901×495 26.2 KB](/uploads/short-url/c5nB8kczby7wqBLpqqPL3iML88M.png?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/9/c96b7dc58f3c8fc0286f6a05a0ee8a53e2d7a42e.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/9/c96b7dc58f3c8fc0286f6a05a0ee8a53e2d7a42e.png)

image723×418 30.7 KB](/uploads/short-url/sJQgMboqAa4U3rrBzMVCW3iCcF0.png?dl=1)

来源：The manual of photography photographic and digital imaging（第九版），Ralph Jacobson, Sidney Ray, Focal Press，2000 年，第 388-390 页。

> **@PhotoPhysicsGuy** (帖子 #116):
> 但我想你可以自己试试，将测试图像不是插入到管线中的负片曝光部分，而是插入到末端，看看你的光谱印相色域在 xy 色度平面上的范围。

这也非常有趣，还没试过只输入用于打印的图像，或者管线的任何中间步骤。应该不会太难，我想我可以将线性 RGB 值解释为相纸的有效曝光，然后从那开始计算。

---

## #127 **jo** (@hanatos) · 2025-02-27 10:22

> **@arctic** (帖子 #123):
> 如果你需要一点关于我对颗粒模型假设的背景，我会写一些东西。如果对你有帮助的话！

是的，我们可能应该讨论一下这个。目前我只是考虑一个像素内有"大量"颗粒，使得空间白噪声分布特性转化为某种高斯滤波的白噪声（更蓝一点）。这就像每个像素看到的颗粒数量的不均匀性。现在我真的想用期望值 = 显影密度的二项式/泊松随机变量来采样哪些颗粒会转化。我做的任何事可能都是错的，因为它只是用过多的噪点淹没了整个图像。泊松分布有一些基本的不直观之处，我永远无法完全凭直觉理解…每个粒子带来自己的方差…所以每个像素更多光子意味着更多方差。与蒙特卡洛估计器完全相反！不管怎样，每个像素的已显影颗粒数量目前就直接是期望值 <span class="math">n\cdot p</span>。

> **@arctic** (帖子 #123):
> 我创建滤镜中性值的方法是拟合输入中的单个灰色像素（[0.184,0.184,0.184]），以获得与输出相同的灰色值（我实际上拟合 Y 滤镜、M 滤镜和打印曝光）。我发现滤镜中性值对管线相当敏感，所以不确定它们能否完全保持不变。如果它们能，那就太棒了。

对的。我想差异很微妙但可能存在（例如，我使用 YMC 滤镜的相当粗略的近似）。我在 vkdt 中有 Nelder-Mead/Adam 优化器，理论上可以包装处理图并拟合模块参数以匹配拾取的颜色/损失模块输出。我会尝试那个拟合步骤，看看会发生什么。

哦还有一件事：我没有使用包络函数。我认为管线不会荧光，即波长之间不会交换能量（除了中间投影到 cmy/rgb 密度）。最后，扫描步骤投影到 1931 CMF，它已经在 400 和 700 nm 处有衰减，就像上采样例程的假设一样。你有没有一张特定的图像和设置可以展示青色问题？我想尝试复现…

---

## #128 **Bob** (@PhotoPhysicsGuy) · 2025-02-27 11:07

> **@arctic** (帖子 #126):
> 我从手头的书中找到了这些通用数据。看起来确实相当宽，尤其是红蓝两侧。

太好了！看起来这些色域确实超过了 sRGB 色域。我并*没有*声称"色域越大越好"，而是说在调整 DIR 成色剂设置时需要牢记这一点。

---

## #129 **jo** (@hanatos) · 2025-02-27 13:56

再次看成色剂和非局部的部分。也许你能用简单的非 Python 术语给我解释一下这段代码应该做什么？

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

它在曝光值和密度值之间来回插值了很多内容，我迷失了方向。

根据我的理解，构造了一个 3x3 的成色剂矩阵，并将其应用于（归一化的、可能经过曝光偏移的）密度曲线，对 3 条曲线进行逐分量相乘。为什么要归一化？不做归一化的矩阵乘法不是一样的吗？归一化只是为了处理非零曝光偏移的情况？

那么为什么你可以直接从 log 曝光中减去结果（那不是密度值吗）？为什么又要从 log 曝光回到密度？然后从密度到 log_raw_correction？为什么要对 log 曝光校正进行线性滤波/高斯模糊？我们不应该对线性场景参考光值进行模糊处理吗？我猜这里的半径可以相当大。然后最终，校正/模糊后的 log raw 再次通过校正后的密度曲线回到密度。

这感觉像是在绕圈子，可能是因为用 Python 写起来很容易？这里的概念到底是什么？

---

## #130 **Andrea** (@arctic) · 2025-02-27 14:39

> **@hanatos** (帖子 #127):
> 是的，我们可能应该讨论一下这个问题。[…] 现在我真的想用二项/泊松随机变量，期望值等于显影密度，来采样哪些颗粒会显影。

关于颗粒的假设是：每一层都有一个可由颗粒覆盖的总面积，该面积与最大密度成正比。因此每个子层拥有这个面积的一部分。

我使用复合的"二项分布(泊松分布, p)"。泊松分布用于粒子的 xy 点过程在平面上的分布，即每个像素桶里最终有多少颗粒。二项分布用于显影概率 (p)，即与密度/最大密度成正比。实际上，颗粒在表面上的分布并非完全随机，所以我添加了一个简单的饱和度模型来考虑堆积效应，即由于遮挡导致方差比泊松分布小。我通过模拟更多的颗粒数量来降低相对方差，并在最后对密度进行缩放。

还有一个关于灰雾的小问题。即使没有曝光，也存在一个始终显影的最小密度，我们需要将其考虑在内。

顺便说一下，我用 `numba` 写了一些代码，计算二项分布和泊松分布的近似值，可能更接近你的实现。本质上，我使用一组近似方法在不同区间计算随机数。例如对于二项分布，从直接的伯努利采样到正态分布近似。代码在 `large-color-gamut` 分支的 `agx_emulsion/utils/fast_stats.py` 中，可能会用到。

这是单个层的行为。

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/8/e/8e607401872bbd71822ba452262bfcaeeab11983.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/8/e/8e607401872bbd71822ba452262bfcaeeab11983.png)

image584×432 50.3 KB](/uploads/short-url/kjwrWzqwY2q1v6YiXx8Y3kRQ6uT.png?dl=1)

<details>
<summary>
单层最小颗粒代码，同时也用于生成 RMS 图。</summary>

<pre data-code-wrap="python"><code class="lang-python">import scipy
import numpy as np
import matplotlib.pyplot as plt

poisson_rvs = scipy.stats.poisson.rvs
binomial_rvs = scipy.stats.binom.rvs
# beta_rvs = scipy.stats.beta.rvs
n_particles = 1000 # 平均每像素
dmax = 1.0
od_particle = dmax/n_particles

samples = 1000
le = np.linspace(-3, 3, 512) # log 曝光
p = scipy.stats.norm.cdf(le) # 简单密度曲线
p = np.tile(p, (samples, 1))

samples_sat = []
uniformity = [0.5, 0.7, 0.9, 0.95]
for i, uni in enumerate(uniformity):
 saturation = 1 - p*uni*(1-1e-6)
 samples_sat_max = poisson_rvs(n_particles/saturation, size=p.shape)
 samples_sat.append(binomial_rvs(samples_sat_max, p)*saturation*od_particle)

seeds = poisson_rvs(n_particles, size=p.shape)
samples_binom_poisson = binomial_rvs(seeds, p)*od_particle
samples_binom = binomial_rvs(n_particles, p)*od_particle # 完美排序的情况
# samples_beta = beta_rvs(p*(n_particles-1), (1-p)*(n_particles-1), size=p.shape)*n_particles*od_particle

plt.plot(le, np.std(samples_binom_poisson, axis=0), label='二项分布(泊松分布)')
plt.plot(le, np.std(samples_sat[0], axis=0), label='二项分布(泊松分布) 均匀度=0.5')
plt.plot(le, np.std(samples_sat[1], axis=0), label='二项分布(泊松分布) 均匀度=0.7')
plt.plot(le, np.std(samples_sat[2], axis=0), label='二项分布(泊松分布) 均匀度=0.9')
plt.plot(le, np.std(samples_sat[3], axis=0), label='二项分布(泊松分布) 均匀度=0.95')
plt.plot(le, np.std(samples_binom, axis=0), label='二项分布')
# plt.plot(le, np.std(samples_beta, axis=0))
plt.xlabel('Log 曝光')
plt.ylabel('RMS 颗粒度')
plt.legend()
</code></pre>

</details>

> **@hanatos** (帖子 #127):
> 我没有使用包络函数。我以为流水线不会产生荧光，即波长之间不会交换能量

我不太理解关于包络的评论。这个上下文中的包络是什么？

可以肯定的是，我创建的这张测试图显示出了这个问题。

[gradient_hdr_rgb.exr](/uploads/short-url/dSLvnmpgJjpuS6iuFYksycL2lMe.exr) (390.8 KB)

你可以用线性 Rec2020 或线性 ProPhoto RGB 导入它。

（左）被解释为线性 Rec2020，（右）被解释为线性 ProPhoto RGB

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/9/a/9a7e3fd3e24fde1771f9479e5283c387e9987b45.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/9/a/9a7e3fd3e24fde1771f9479e5283c387e9987b45.png)

image630×605 54.2 KB](/uploads/short-url/m2I18FwEY9YVzpEd86tfRk7LS0R.png?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/f/afc6471b99473e702711ee7e0c05c5d9ea314ac1.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/f/afc6471b99473e702711ee7e0c05c5d9ea314ac1.png)

image630×605 54 KB](/uploads/short-url/p4YmEUgBPMPILSqZE2bNvJulfQl.png?dl=1)

输出在大输出色彩空间中仍然是平滑的，所以出于某种原因，我们在青色一侧碰到了输出 sRGB 的硬裁切。

> **@arctic** (帖子 #10):
> image630×628 106 KB image389×389 21.3 KB

就像之前在这些测试中展示的一样。但为什么会发生这种情况以及这是否是照片的预期行为，则是另一个话题。好在我记得在处理过的真实世界图片中，没有遇到过令人困扰的问题。

正如 [@PhotoPhysicsGuy](/u/photophysicsguy) 所评论的，通过查看真实数据，相纸的色域相当大，超越了 sRGB，在青色一侧也是如此。

---

## #131 **jo** (@hanatos) · 2025-02-27 14:56

啊，我指的是上面这张图中的带通包络函数，明确截断了极端波长：

 [[![图片224](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/6/06b69d7f293316265e727ce44256329670a16c1b.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/6/06b69d7f293316265e727ce44256329670a16c1b.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/6/06b69d7f293316265e727ce44256329670a16c1b.png)

---

## #132 **Andrea** (@arctic) · 2025-02-27 15:10

> **@hanatos** (帖子 #127):
> 我以为流水线不会产生荧光，

确实没有荧光/磷光效应，但根据我的经验，当胶片的感光度比 CIE 1931 CMF 更宽时，会出现令人不悦的颜色，尤其是红色。而当感光度在可见光谱范围内更窄时，这类问题就会少很多。所以这与输入输出的光谱范围关系不大，而在于胶片感知光的方式。我可以提供更多例子来支持这一改进。当然我也接受被证伪。

[![:grin:](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)

我稍后会回答关于成色剂的问题，我很喜欢你评论中的困惑，它完美地解释了代码中的那些杂技般的操作。请相信我，在我的脑海和笔记中，是有一定逻辑的。但它可能会在别人的审视下崩溃。我会尽力解释。

---

## #133 **jo** (@hanatos) · 2025-02-27 18:15

> **@arctic** (帖子 #132):
> 我稍后会回答关于成色剂的问题，

不用急，不赶时间！我只是有点上头了…… 我 meantime 会再看看颗粒的问题。

对了，我现在已经做了 YM 滤镜拟合。我也需要拟合青色，但即便如此，一些胶片和相纸的组合还是出现了负的滤镜百分比…… 这不太让人放心。这是将 0.184 输入匹配到输出端的 0.5*D50…… 有时候当我尝试直接匹配时，能得到更令人愉悦的肤色（使用正的滤镜权重）。不管怎样，继续玩下去很开心！

---

## #134 **Andrea** (@arctic) · 2025-02-27 22:01

> **@hanatos** (帖子 #129):
> 再次看成色剂和非局部的部分。也许你能用简单的非 Python 术语给我解释一下这段代码应该做什么？

别担心，不着急

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

我试着写下推理过程，但可能比我想象的更复杂。总之，这里是我尝试解释我的灵感来源，并试图证明各个步骤的合理性。

DIR 成色剂是在密度形成时（与之成对）释放的化学物质，会抑制更多密度的形成。它们会进行空间扩散，通常为 10-15 微米（目前我没有这方面的参考文献，只是一个合理的猜测），每一层厚度为 2-5 微米。所以它们既在层间扩散，也在成像平面上扩散。这些距离非常小，比颗粒略大。作为参考，优质镜头的典型 PSF 为 2-3 微米，较差的为 5 微米以上。

如果能做一个小的动力学方案来模拟适当的抑制动力学，并积分微分方程，那就太好了，但我想计算量会相当大。

我的大胆假设和推理如下：

- 无论我们做什么，我们都要尊重 `density_curves` 数据。这些数据是通过用中性光照（d55 或 d65）曝光胶片测量得到的，同时在所有层中产生密度。
- 密度是显影染料浓度的度量（[朗伯-比尔定律](https://en.wikipedia.org/wiki/Beer%E2%80%93Lambert_law)）。由于密度-浓度的比例关系取决于吸收效率，我通过除以 `max_density` 进行归一化，使得每层中的染料量在 0-1 范围内可比。
- 我首先假设用原始 `density_curves` 计算出的 `density_cmy_0` 是在该层上形成的密度的第一估计值。
- 现在我假设在一层上生成的 DIR 成色剂的量与归一化的 `density_cmy_0` 成正比，因为它们是在显影过程中以成对方式形成的。这当然是一个近似。
- 成色剂在层间和空间中扩散，即高斯模糊。
- 接下来我假设胶片的显影和一层中达到的密度量在给定显影时间下是动力学控制的。因此一层上产生的密度是"显影速度 × 显影时间"（至少在远离最大密度时如此）。显影时间是固定的。而显影速度会随着抑制而改变。
- 我假设 log 曝光与显影过程的反应速度（每秒产生的密度）成正比。光产生银中心，这将加速卤化银 + 显影剂 → 银（以及后来的染料）的反应。如果光产生了更多的银中心，局部就会产生更多的密度。我们可以进一步假设 `log_raw`（从趾部交点开始）与银中心（或至少有一个可显影银中心的颗粒）的数量成线性关系。在这个假设下，`log_raw` 是物质（潜影颗粒）数量的度量。这当然是另一种简化。
- 抑制剂会局部减缓显影，导致更少的卤化物转化为银。我们可以将其理解为抑制剂能够去除/抑制银中心，即实际上减少了 log 曝光（`log_raw`）。因此 `log_raw_corrected` 被计算为 `log_raw` 减去该层和位置存在的抑制剂的量。
- 如果我们在此停止并用正常的 `density_curves` 重新插值 `log_raw_corrected`，我们将降低对比度，我们的模拟将不再与数据匹配。为了解决这个问题，我们可以生成一组新的虚拟密度曲线，仿佛抑制剂没有活动时一样：`density_curves_0`。这些曲线对比度更高，并且在中性光照下对胶片应用抑制剂后，它们恰好给出 `density_curves`。现在我们的胶片尊重原始数据，而中间调基本保持不变。饱和色则在原本密度较低的通道上密度更小。

当然，我们需要确保抑制剂的量被校准到合理的效果。我们可以从归一化密度中减去带有抑制剂的 `log_raw`，其依据是这两者都可以解释为某种物质的量（银中心/带银中心的颗粒以及抑制银中心的化学物质）。

DIR 成色剂在空间 xy 方向上的作用是增加清晰度。我们对来自密度的成色剂量进行模糊处理，是因为我们将其解释为移动的物质。

这是密度曲线的一个例子：

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/8/e/8e9a3c6d055150b77d2b6d028601eb7ec2753f8d.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/8/e/8e9a3c6d055150b77d2b6d028601eb7ec2753f8d.png)

image567×432 21.7 KB](/uploads/short-url/klwfuYa4yHZmu7YXHuvQp45MFXf.png?dl=1)

当 dir_couplers_amount = 1.0 时，我们在各层中得到这个量的成色剂：

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/e/cef422a6fe7d990ace4578923ee30117f3f0de31.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/e/cef422a6fe7d990ace4578923ee30117f3f0de31.png)

image567×432 20.9 KB](/uploads/short-url/twNpP44E2u2XQKe4huziIIEB5Kx.png?dl=1)

位于堆叠中间层的绿色从两侧接收。

这是成色剂矩阵，说明了从起始层扩散到各层的 DIR 成色剂量：

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/4/040e60460b198417eb11909a2f6c9946281c256f.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/4/040e60460b198417eb11909a2f6c9946281c256f.png)

image504×435 5.63 KB](/uploads/short-url/zSI32cAaA3OFapVA2k2KICAdwX.png?dl=1)

这是应用成色剂前后的密度曲线。施加成色剂前的密度曲线（虚线）是虚拟的，从未实际发生在胶片上：

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/8/58910540660feff587e1bdd13d2e11ad1f96dc03.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/8/58910540660feff587e1bdd13d2e11ad1f96dc03.png)

image567×432 35.5 KB](/uploads/short-url/cDuIMYkVFqerpNgsTmDgiBhoyGv.png?dl=1)

这个描述可能在科学上有不够严谨之处，我也许可以完善这些假设，使表述更加准确。但我认为最终的算法是一种能够产生抑制效果的最简单可行的方案。我们当然可以把它做得更复杂、更符合实际情况。

---

## #135 **Andrea** (@arctic) · 2025-02-27 22:05

哇，你能实时拟合滤镜，这太棒了。这也为对配置文件进行更大幅度的修改提供了可能性，而无需担心损失一个可靠的中性点用于滤镜。

> **@hanatos** (帖子 #133):
> 我也需要拟合青色，但即便如此，一些胶片和相纸的组合还是出现了负的滤镜百分比……

相纸的感光度是经过校准的，用于配合通过典型底片过滤后的钨丝灯。负的滤镜值可能表明与实际情况相比有所偏差。在现实世界中，即使不怎么动青色滤镜，一切也应该可以做到。

> **@hanatos** (帖子 #133):
> 0.5*D50 在输出端……

我想知道为什么是 0.5 * D50 而不是 0.184 * D50，以及这有没有区别。

---

## #136 **jo** (@hanatos) · 2025-02-28 13:30

> **@arctic** (帖子 #130):
> 单层最小颗粒代码，同时也用于生成 RMS 图。

太好了，谢谢。现在如果我每像素使用 1000 个颗粒，并在我过滤后的伪泊松分布之上加一个二项分布，我觉得效果开始好多了。二项分布解决了一些过于蓝噪声规则的外观。我可能还要再考虑一下饱和度部分，还没有建模这个。

> **@arctic** (帖子 #135):
> 相纸的感光度是经过校准的，用于配合通过典型底片过滤后的钨丝灯。负的滤镜值可能表明与实际情况相比有所偏差。

显然它对 YMC 滤镜非常敏感。我用一些更平滑的版本替换了这些滤镜，重新运行拟合后，现在所有值都在 <span class="math">[0,1]</span> 范围内为正，符合预期。但我仍然觉得 `kodak supra|portra endura` 有一些黄色偏色问题。可能还是我粗糙的滤镜近似导致的。

> **@arctic** (帖子 #135):
> 我想知道为什么是 0.5 * D50 而不是 0.184 * D50，以及这有没有区别。

啊，我当时想的是因为这是一个显示变换…… 但你说得对，gamma 之后会在此基础上叠加。让我用 0.184 重新运行一下，看看效果。

（思考成色剂的问题……）

---

## #137 **Jiyone** (@Jiyone) · 2025-02-28 17:11

我想知道你们是否会在不久的将来添加一些黑白胶片和黑白相纸，比如具有不同密度层的 ilford 多反差相纸。

---

## #138 **nosle** (@nosle) · 2025-02-28 22:21

除了 [@Jiyone](/u/jiyone) 上面的问题之外，添加更多的模拟有多复杂？用于制作更多模拟的数据是否容易获得？

有谁知道旧的 nc 版 Portra 与新的不带前缀版本有多大区别？

---

## #139 **** (@mikae1) · 2025-02-28 22:36

> **@nosle** (帖子 #138):
> 除了 @Jiyone 上面的问题之外，添加更多的模拟有多复杂？用于制作更多模拟的数据是否容易获得？

我猜在这里：

> **@arctic** (帖子 #34):
> 我的技术文档来源是这些网站：Index of /docs/film, Photographic & Darkroom Products by Brand, Browse The Analog Film Stock Library | Filmtypes, https://analogfilm.space/。

---

## #140 **** (@mikae1) · 2025-02-28 22:39

> **@arctic** (帖子 #125):
> (d) 当前 `large-color-gamut` 分支的默认输出，从 (c) 我们得到了新的更有效的 DIR 成色剂，以及新的 hanatos 的光谱上采样（以及更多内容）。只更改了负片/相纸的曝光默认值。

是的，看起来确实不错！我被图片下边缘的"绿色调"以及沉船阴影吸引住了。它看起来非常有胶片感（不是 filmic rgb 那种意义上的

[![:grinning:](https://discuss.pixls.us/images/emoji/apple/grinning.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grinning.png?v=12)

）。

> **@arctic** (帖子 #125):
> 即使尝试更好地匹配这两种胶片模拟，即使用放大机滤镜，我也无法让它们感觉相同。darktable 基础编辑使用相同的白平衡，使用对比度为 2 的 sigmoid，以及色彩平衡 RGB 的 30% 全局鲜艳度。

你对 mallett2019 与 hanatos2025 的看法如何？我一直在路上，只能用手机屏幕判断对比，但我相信在几乎所有情况下我都更喜欢 hanatos2025。

> **@arctic** (帖子 #125):
> 拥有一个不依赖于光谱数据中那些未被理解的隐含知识的通用工具，听起来非常酷！

是的，这让我想起了你之前在帖子中提到的，这个工具不是基于测量而是基于技术文档。另外，我想在某个时候，这些胶片需要换个名字了。Godak Bortra？

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

---

## #141 **Andrea** (@arctic) · 2025-02-28 23:41

> **@hanatos** (帖子 #136):
> 显然它对 YMC 滤镜非常敏感。我用一些更平滑的版本替换了这些滤镜，重新运行拟合后，现在所有值都在 [0,1] 范围内为正，符合预期。但我仍然觉得 `kodak supra|portra endura` 有一些黄色偏色问题。可能还是我粗糙的滤镜近似导致的。

Kodak Portra 和 Supra Endura 共享相同的感光度（和染料扩散密度）。它们是姊妹相纸，只是对比度不同。根据我的经验，它们也是最容易在模型开发中显示色彩问题的，并且在我开始添加更多物理上有意义的滤镜和光源之前，它们长期持续给出不一致的结果。

比较感光度，它们有相当多的蓝-绿交叉串扰。特别是绿色感光度相比其他相纸非常偏蓝。所以我猜测滤镜在 Portra（和 Supra）的 500 nm 过渡区非常关键。

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/3/e/3e3983899737cdff8b063639b2fd2b2793b841f6.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/3/e/3e3983899737cdff8b063639b2fd2b2793b841f6.png)

image596×455 55.6 KB](/uploads/short-url/8SsPcYdHE38Ld5fdziUyZxtTMVM.png?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/4/8/482c0b3819d4545b683637916c46ce48921fe060.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/4/8/482c0b3819d4545b683637916c46ce48921fe060.png)

image596×455 53.8 KB](/uploads/short-url/aisJXG6GA4fVGJHw9vNzQlu0KwE.png?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/1/01e7c62389d887af7cc270692364e9d62245784c.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/1/01e7c62389d887af7cc270692364e9d62245784c.png)

image596×455 52.9 KB](/uploads/short-url/gR39MvuzByqecXO0QV321k6msY.png?dl=1)

Portra（和 Supra）的肤色也是所有相纸中最好的，这一点与我尝试的其他相纸不同。我开始想，我是否应该尝试不同于从 Thorlabs 获得的标准比色滤镜组。也许有专门为彩色放大机设计的二向色滤镜，性能更好？

---

## #142 **Andrea** (@arctic) · 2025-03-01 00:00

> **@Jiyone** (帖子 #137):
> 我想知道你们是否会在不久的将来添加一些黑白胶片和黑白相纸，比如具有不同密度层的 ilford 多反差相纸。

这绝对是我的兴趣所在和长期计划。

[![:star_struck:](https://discuss.pixls.us/images/emoji/apple/star_struck.png?v=12)](https://discuss.pixls.us/images/emoji/apple/star_struck.png?v=12)

 我喜欢黑白颗粒感图像！

我过去已经探索过一些黑白颗粒的模拟（一些非常早期的简单颗粒模型例子 [Embrace the noise! - #20 by arctic](https://discuss.pixls.us/t/embrace-the-noise/17248/20) + 之后几年的一些帖子）。当前的颗粒模型更加复杂且是多层的，使用了适当的密度曲线。加上打印步骤，应该能更好地表现颗粒的滚降特性。

我非常好奇想尝试多反差相纸和推拉显影，因为有很多相关的曲线。这真是超级令人兴奋的东西！当然我需要一些时间。我还有一份全职工作

[![:laughing:](https://discuss.pixls.us/images/emoji/apple/laughing.png?v=12)](https://discuss.pixls.us/images/emoji/apple/laughing.png?v=12)

，但我很希望能花更多时间在这类模型上。

---

## #143 **Andrea** (@arctic) · 2025-03-01 00:09

> **@nosle** (帖子 #138):
> 除了 @Jiyone 上面的问题之外，添加更多的模拟有多复杂？用于制作更多模拟的数据是否容易获得？
> 有谁知道旧的 nc 版 Portra 与新的不带前缀版本有多大区别？

正如 [@mikae1](/u/mikae1) 指出的，周围有大量的数据表可用。制作配置文件不仅仅是获取曲线（以准确的方式），还需要一个通道分离和调整的过程，以确保输出是正常的。此外，大多数时候染料扩散密度并不适用于单独的 CMY 通道，需要以一种符合现有数据的方式合理地重建它们。目前只有 Portra 真正做到了几乎开箱即用，所有其他负片都需要或多或少的调整（以最小的拟合方式）。

相纸的配置文件更加直接，因为通常没有彩色成色染料，预测起来也稍微容易一些。不过富士胶片不为其相纸发布特征密度曲线。

我使用 WebPlotDigitizer 手动从 PDF 中获取了所有数据。然后手动处理它们以确保它们能正确表现（主要是确保它们能够在不出现过度色偏的情况下再现中性灰渐变，对密度曲线进行最小限度的修改）。有一些代码用于制作配置文件，但数据应该逐案评估，因为你永远不知道什么时候会遇到不一致和错误。

---

## #144 **Andrea** (@arctic) · 2025-03-01 00:16

> **@mikae1** (帖子 #140):
> 你对 mallett2019 与 hanatos2025 的看法如何？我一直在路上，只能用手机屏幕判断对比，但我相信在几乎所有情况下我都更喜欢 hanatos2025。

[@hanatos](/u/hanatos) 的光谱上采样算法在任何可能的方面都比 [Mallett2019] 好得多。而且它只增加了非常少的计算开销和一些复杂性。它适用于整个可见光谱轨迹，并允许输入数据有更高的饱和度。在主观判断结果时，在我看来，它增加了明显的"深度感和真实感"（基于物理意义）。

我已经完全停止使用 sRGB 工作流程，这应该能说明我的看法。

[![:slightly_smiling_face:](https://discuss.pixls.us/images/emoji/apple/slightly_smiling_face.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slightly_smiling_face.png?v=12)

---

## #145 **Andrea** (@arctic) · 2025-03-01 10:32

大家好！刚刚合并了 `large-color-gamut` 分支，其中包含了新的光谱上采样方法。现在推荐的工作流程是将 RAW 文件导出到一个大的线性 RGB 空间，如 ProPhoto RGB 或 Rec2020，并使用 `hanatos2025` 作为光谱上采样方法。所有这些都已成为新的默认设置。

其他变化包括：

- 一些函数用 Numba 重写，以提高效率，并在模型的这个测试/开发阶段更快迭代。现在在我的笔记本电脑上，一张 600 万像素（3000x2000）的模拟需要 10 秒。预览模式下 GUI 更新需要 1-2 秒，在点击 `compute_full_image` 之前，颗粒和光晕效果被禁用。Numba 加速的函数包括：
 <ul>
 <li>3D 和 2D 查找表三次插值
- 用于泊松、二项和对数正态分布的近似随机数生成器
- 对于较大图像，线性插值比 `np.interp` 更快

</li>
<li>添加了 pyFFTW 作为依赖项，用于执行更快的并行 FFT 高斯滤波以模拟光晕。通常具有相当大的卷积核</li>
<li>为相机添加了一个光谱带通滤波器（UV 和 IR 截止），并非设计为可更改，但在 GUI 中暴露出来供尝试</li>
</ul>

由于一些内容发生了变化，如果你碰巧尝试并发现了问题，请告诉我。谢谢！

---

## #146 **** (@ChrisB) · 2025-03-01 17:22

> **@arctic** (帖子 #68):
> 漂亮的乐高渲染。你认为背景中的乐高小人是否有红色渐变问题？还是这张图片用来揭示什么特别的问题？

前景的乐高积木和背景的乐高小人使用了 ACEScg 原色。有点像 [@liam_collod](/u/liam_collod) 的龙渲染，目的是看看图像形成的"鲁棒性"如何。

关于渐变，我认为这确实是好的图像形成的关键方面之一。我想为此写一篇小文章。

我很想再次测试这个应用程序，因为它似乎在过去的几周里发生了很多变化！

---

## #147 **** (@ChrisB) · 2025-03-01 17:52

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/7/97744216f1a0e216d27033fd2b47ae27d0ff331f_2_690x388.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/7/97744216f1a0e216d27033fd2b47ae27d0ff331f_2_690x388.jpeg)

image1173×660 157 KB](/uploads/short-url/lBPb9VC9vPL99PNjChCmGwuATRJ.jpeg?dl=1)

应用更新不错！我只需拖放一个 exr，选择色彩空间就行了！很酷！

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/a/7af8b402be64da0a5f4362442220e0d85078a63d_2_690x385.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/a/7af8b402be64da0a5f4362442220e0d85078a63d_2_690x385.jpeg)

image957×535 67.6 KB](/uploads/short-url/hxR5UZJr5gHgfOwftjXqo5HylVr.jpeg?dl=1)

---

## #148 **Cameron Rad** (@cameronrad) · 2025-03-01 19:21

可能只是我的设置问题，但不幸的是我无法在我的 MacOS ARM（M2 Ultra）系统上运行了。我认为可能是 Numba 的问题。当我尝试运行 [@liam_collod](/u/liam_collod) 上面提供的命令时，我得到了这个结果。

```
Numba workqueue 线程层正在终止：检测到并发访问。

 - workqueue 线程层不是线程安全的，不能由多个线程并发访问。并发访问通常通过嵌套的并行区域启动或从多个 Python 线程调用 Numba parallel=True 函数发生。
 - 尝试使用 TBB 线程层作为替代方案，因为它本身就是线程安全的。文档：https://numba.readthedocs.io/en/stable/user/threading-layer.html

```

我尝试更新了代码的一些部分，进展了一些，然后遇到了这个错误。

` ValueError: No threading layer could be loaded. HINT: One of: Intel TBB is required, try: $ conda/pip install tbb OR Intel OpenMP is required, try: $ conda/pip install intel-openmp`

我认为这些在基于 ARM 的 Mac 上无法安装。

---

## #149 **Andrea** (@arctic) · 2025-03-01 19:44

好的！谢谢测试。

你能试试把这段代码放在 `main.py` 的最顶部吗？

```
import os
os.environ["NUMBA_THREADING_LAYER"] = "TBB"

```

我读到这可以解决这类问题。如果 numba 确实有问题，我可能会将其设为可选加速，或者学习如何以更安全的方式使用它。

---

## #151 **Cameron Rad** (@cameronrad) · 2025-03-01 19:59

不幸的是，这对我的设置不起作用。我收到一个错误，提示需要安装 tbb。

```
ValueError: No threading layer could be loaded.
HINT:
Intel TBB is required, try:
$ conda/pip install tbb

```

如果我把 tbb 添加到依赖项中，或者尝试用 pip 手动安装，它也不起作用，因为似乎没有适用于我系统的 tbb wheel 包。

```
╰─▶ 因为所有版本的 tbb 都没有匹配的平台标签的 wheel（例如 `macosx_15_0_arm64`），并且你需要 tbb，我们可以得出结论你的需求无法满足。

 提示：`tbb`（v2022.0.0）的 wheel 可用于以下平台：`manylinux_2_28_x86_64`，`win_amd64`

```

---

## #152 **Y** (@Y69) · 2025-03-01 20:02

是的，在 Linux 上遇到了同样的问题。即使在强制 Numba 使用 Intel TBB 并通过 `pip install tbb` 提供 TBB 之后

[![:confused:](https://discuss.pixls.us/images/emoji/apple/confused.png?v=12)](https://discuss.pixls.us/images/emoji/apple/confused.png?v=12)

---

## #153 **Andrea** (@arctic) · 2025-03-01 20:18

我明白了，这不太好。如果这个问题真的解决不了，我会把 numba 函数做成可选的。我没想到这会带来这么大的破坏

[![:grin:](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)

 抱歉！

---

## #154 **Y** (@Y69) · 2025-03-01 20:21

让事情支持多线程是件好事

[![:wink:](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)

---

## #155 **Cameron Rad** (@cameronrad) · 2025-03-01 21:17

我通过这样做暂时让它工作了。我替换了所有

`parallel=True` 为 `parallel=False`。

我还把它添加到了 main.py 的顶部

```
import os
os.environ["NUMBA_THREADING_LAYER"] = "threadsafe"

```

现在它又为我打开了。虽然很慢，但能打开和运行了。

---

## #156 **Cameron Rad** (@cameronrad) · 2025-03-01 22:07

所以我逐个文件地开始重新启用 `parallel=True`，试图缩小问题发生的范围，我认为问题出在 `fast_gaussian_filter.py`。一旦我在那里启用 `parallel=True`，我就无法再启动它。在 `fast_interp_lut.py`、`fast_interp.py`、`fast_stats.py` 和 `fft_gaussian_filter.py` 中启用它似乎不会导致应用程序启动问题。

我还测试了从 `main.py` 中移除

```
import os
os.environ["NUMBA_THREADING_LAYER"] = "workqueue"

```

并仅在 `fast_gaussian_filter.py` 中将 `parallel=True` 改为 `parallel=False`，然后它启动了。

---

## #157 **Andrea** (@arctic) · 2025-03-02 00:31

感谢你对此进行调查，既然使用 `parallel=False` 的增益不到 2 倍（相对于之前的约 3-4 倍），我暂时在 `main` 分支中恢复到了 scipy 的 `gaussian_filter`。希望这样能在所有平台上更稳定地工作。

[![:+1:](https://discuss.pixls.us/images/emoji/apple/+1.png?v=12)](https://discuss.pixls.us/images/emoji/apple/+1.png?v=12)

---

## #159 **jo** (@hanatos) · 2025-03-02 17:58

> **@arctic** (帖子 #141):
> Portra（和 Supra）的肤色也是所有相纸中最好的，这一点与我尝试的其他相纸不同。我开始想，我是否应该尝试不同于从 Thorlabs 获得的标准比色滤镜组。也许有专门为彩色放大机设计的二向色滤镜，性能更好？

有趣，是的，也许有更好的滤镜。我对 Thorlabs 滤镜有一些或多或少（更少）准确的解析拟合。特别是 500nm 对我来说很麻烦。当我将品红和黄色重叠，使它们总和为 1 但在 500nm 处交叉时，我在优化后得到了正/表现良好的滤镜权重。如果我能更好地匹配你的数据，权重就会失控。

我现在使用的是 2856K 的钨丝灯，而不是 3200K，因为目测你的图表，400nm 处的低值和 800nm 处的高值看起来更像这样（没有科学数据驱动的理由）。我想也许我的结果现在看起来好了一些（？）。我还加了一个带通滤镜，但到目前为止还看不出有多大区别。

我注意到在使用 Portra 胶片/相纸时，我可以通过调整胶片曝光与相纸曝光来控制"白平衡"。也许这个自动曝光部分就是我的 Portra 看起来与 agx-emulsion 如此不同的原因，因为除此之外我现在得到了非常相似的结果（目前没有光晕和成色剂）。

---

## #160 **** (@mikae1) · 2025-03-02 20:27

好的，我才刚开始玩 agx-emulsion，但这远远超出了我的预期！

[![:exploding_head:](https://discuss.pixls.us/images/emoji/apple/exploding_head.png?v=12)](https://discuss.pixls.us/images/emoji/apple/exploding_head.png?v=12)

 *出色的*工作！

[![:medal_sports:](https://discuss.pixls.us/images/emoji/apple/medal_sports.png?v=12)](https://discuss.pixls.us/images/emoji/apple/medal_sports.png?v=12)

---

## #161 **Jed Smith** (@jedsmith) · 2025-03-02 22:21

我想知道是否有可能找到像 Kodak 2383 这样的电影印片胶片的光谱响应特性。除了相纸之外，支持该成像流水线在美学上可能会很有趣。

---

## #162 **Andrea** (@arctic) · 2025-03-02 22:49

> **@hanatos** (帖子 #159):
> 当我将品红和黄色重叠，使它们总和为 1 但在 500nm 处交叉时，我在优化后得到了正/表现良好的滤镜权重。如果我能更好地匹配你的数据，权重就会失控。

干得好，听你这么说很有趣。也许我也应该重新审视滤镜，尝试使用一些与你更可靠的结果更相似的东西。如果你有任何进一步的见解，我洗耳恭听！

> **@hanatos** (帖子 #159):
> 我现在使用的是 2856K 的钨丝灯，而不是 3200K，因为目测你的图表，400nm 处的低值和 800nm 处的高值看起来更像这样（没有科学数据驱动的理由）。

我使用较冷色温的理由来自研究 Durst M605 的手册

[Durst_M605.pdf](/uploads/short-url/euuy2uGObEomDuF4rmE7EC1zphn.pdf) (7.1 MB)，其中他们使用了一种应该比钨丝灯更冷的卤钨灯。我并没有花太多精力去优化输出。

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/1/21df2edc127265dace2f5fe6ac13efe7066d59ec_2_500x500.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/1/21df2edc127265dace2f5fe6ac13efe7066d59ec_2_500x500.jpeg)

image937×882 225 KB](/uploads/short-url/4PDVhPMvks2KhwGgGdgzgs5x5ve.jpeg?dl=1)

> **@hanatos** (帖子 #159):
> 我想也许我的结果现在看起来好了一些

太棒了！

[![:sunglasses:](https://discuss.pixls.us/images/emoji/apple/sunglasses.png?v=12)](https://discuss.pixls.us/images/emoji/apple/sunglasses.png?v=12)

关于带通滤镜的效果，我认为我之前也发布过的这张来自 signatureedits 的图片，[复古红色汽车图片](https://www.signatureedits.com/wp-admin/admin-ajax.php?action=useyourdrive-download&account_id=103498887174941726250&id=1IChRf9tEvOljWAOkiav1fG1IX2G-gfEO&dl=1&listtoken=d8b65b66692c59f215d41b174d2a67af)，是一个非常有挑战性的。如果不使用滤镜并使用 Kodak Portra 400，很难获得令人满意的红色，Kodak Gold 200 也是如此。尤其是引擎盖顶部的反射。

> **@hanatos** (帖子 #159):
> 我注意到在使用 Portra 胶片/相纸时，我可以通过调整胶片曝光与相纸曝光来控制"白平衡"。也许这个自动曝光部分就是我的 Portra 看起来与 agx-emulsion 如此不同的原因，因为除此之外我现在得到了非常相似的结果（目前没有光晕和成色剂）。

即使 Portra 400 有很宽的宽容度，过度曝光也会有偏移。根据我的经验，最好的效果是在保留暗部阴影的前提下使用最小的负片曝光。此外，配置文件是使用我的流水线优化的（仅优化 `density_curves`，目标是针对一系列负片曝光获得中灰中性打印输出，使用拟合程序）。

对于 Portra 400，与原始数据相比变化不大。未进一步修正的原始配置文件是 `kodak_portra_400_au`，而 `kodak_portra_400_auc` 对密度曲线进行了一个小修正。`kodak_portra_400_au` 只做了密度的"解混"，完全不依赖于 `agx-emulsion` 流水线。请注意，并非所有 `_au` 配置文件都能给出好结果，大多数在 `agx-emulsion` 中会受到严重色偏的影响。

---

## #163 **Andrea** (@arctic) · 2025-03-02 22:56

是的，有不错的数据可用，[数据表](https://www.kodak.com/content/products-brochures/motion-picture/KODAK-VISION-Color-Print-Film-2383-3383-technical-information.pdf)看起来质量很好，包含所有必要的数据。我同意电影印片胶片会非常有趣。这在与 [@PhotoPhysicsGuy](/u/photophysicsguy) 的讨论中已经提到过。我把它加入了待配置胶片的未来列表。

---

## #164 **Cameron Rad** (@cameronrad) · 2025-03-03 07:26

我认为如果可以的话，创建一个虚拟的 Fuji Frontier 扫描仪模型会很有趣。然后可以用来结合现实世界的测试/扫描来验证结果和胶片模拟。我相信 VSCO 最终就是这样做出来的。这里有一些相关文章：

- [VSCO Film X & The Imaging Lab | VSCO Engineering](https://eng.vsco.co/vsco-film-x-&-the-imaging-lab/)
- [How VSCO Builds Film-Like Smartphone Photo Filters in Its Lab | WIRED](https://www.wired.com/story/vsco-film-photo-filters/)
- [‎Inside VSCO's Imaging Lab : App Store Story](https://apps.apple.com/us/story/id1445632852)

这里有一些与 Fuji Frontier 相关的专利。第一个链接我认为有一张使用了波长 LED 的图表。

- [US20010026369A1 - 光源装置及原稿读取装置 - Google Patents](https://patents.google.com/patent/US20010026369A1/en)
- [US20030081211A1 - 光源装置及图像读取装置 - Google Patents](https://patents.google.com/patent/US20030081211A1/en)
- [US6751349B2 - 图像处理系统 - Google Patents](https://patents.google.com/patent/US6751349B2/en)
- [US6067109A - 图像读取方法 - Google Patents](https://patents.google.com/patent/US6067109A/en)
- [US6791721B1 - 图像读取装置 - Google Patents](https://patents.google.com/patent/US6791721B1/en)
- [US6665434B1 - 用于校正图像色彩不平衡的装置、方法及记录介质 - Google Patents](https://patents.google.com/patent/US6665434B1/en)
- [US4893178A - 自动照相打印设备的模拟器，包括反相电路和光谱特性补偿 - Google Patents](https://patents.google.com/patent/US4893178A/en)

---

## #165 **Andrea** (@arctic) · 2025-03-03 21:51

> **@cameronrad** (帖子 #164):
> VSCO Film X & The Imaging Lab | VSCO Engineering
> How VSCO Builds Film-Like Smartphone Photo Filters in Its Lab | WIRED
> ‎Inside VSCO's Imaging Lab : App Store Story

读到这些，我对 VSCO 有了新的敬意。他们做这些特性分析一定很享受。

> **@cameronrad** (帖子 #164):
> 第一个链接我认为有一张使用了波长 LED 的图表。

感谢你搜索专利文献。

拥有 LED 光源光谱是一个好的开始。我猜最难的部分是理解他们从原始扫描文件（校准/变换矩阵/曲线等）开始的实际数据处理流水线是什么。VSCO（和 Negative Lab Pro）可能通过使用彩色测试图对扫描仪的输入/输出进行配置来解决这个问题。

如果我们能找到任何关于扫描仪处理方法背后原理的完整资料，我们可以尝试从基本原理出发进行一些工作。不过我打赌这很难找到。

我正在浏览这些专利以寻找线索。

---

## #166 **Andrea** (@arctic) · 2025-03-04 00:21

我有用 Kodak Vision Premier 彩色印片胶片 2393 进行的初步测试。

我在使用我的放大机光源拟合打印滤镜时遇到困难（我将不得不改变它相对于 RA-4 相纸使用的光源，或者尝试理解这个问题）。

对比使用的是 Kodak Ultramax 400，碰巧可以被拟合。

（左）Kodak 2393，（右）Kodak Portra Endura

[[![ultramax_kodak_2393](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/3/03a0c32f1ef8df8152ce86a178d06e60f910acc7_2_330x490.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/3/03a0c32f1ef8df8152ce86a178d06e60f910acc7_2_330x490.jpeg)

ultramax_kodak_23931998×3000 1.01 MB](/uploads/short-url/w5RAxN7uO1ehevxU8DHqxiGsHZ.jpeg?dl=1)

[[![ultramax_portra_endura](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/1/81969078d071887162aca1eb8b2f9c3ff920de77_2_330x490.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/1/81969078d071887162aca1eb8b2f9c3ff920de77_2_330x490.jpeg)

ultramax_portra_endura1998×3000 949 KB](/uploads/short-url/iuoaVIG7gQ17pnbzGXKizM8YD1Z.jpeg?dl=1)

我注意到非常深的黑色。密度曲线几乎达到 6 OD！

我不确定我们是否应该混合摄影胶片和电影印片胶片。这可能是一件异端的事情。

[![:laughing:](https://discuss.pixls.us/images/emoji/apple/laughing.png?v=12)](https://discuss.pixls.us/images/emoji/apple/laughing.png?v=12)

 但这就是首次测试的结果。

---

## #167 **Bastian Bechtold ** (@bastibe) · 2025-03-04 07:23

> **@arctic** (帖子 #165):
> cameronrad:

VSCO Film X & The Imaging Lab | VSCO Engineering
How VSCO Builds Film-Like Smartphone Photo Filters in Its Lab | WIRED
‎Inside VSCO's Imaging Lab : App Store Story

读到这些，我对 VSCO 有了新的敬意。他们做这些特性分析一定很享受。

</blockquote>
</aside>

我完全不知道他们对胶片模拟有这么认真。我一直以为他们只是一个简单的预设应用程序，但这让我对他们的工作有了更多的尊重！

---

## #168 **jo** (@hanatos) · 2025-03-04 08:14

只想提一下，我遇到了一些关于高度饱和/窄光谱的问题：[Problem with filmsim artifacts · Issue #164 · hanatos/vkdt · GitHub](https://github.com/hanatos/vkdt/issues/164) 并分享一个新的上采样 LUT。我知道 agx-emulsion 使用密集采样和一些正则化以获得更好的积分，所以可能不会有什么问题。我现在使用一个光谱上采样的 LUT，它会在接近光谱轨迹边界之前停止产生更窄的峰值。因此，对于非物理刺激的修复也更加平滑：

[spectra-em.lut](/uploads/short-url/s3BxvFjjWfUiMEtJjPBfPMbBF0F.lut) (4.0 MB)

---

## #169 **Nate Weatherly** (@NateWeatherly) · 2025-03-04 21:09

> **@arctic** (帖子 #166):
> 我在使用我的放大机光源拟合打印滤镜时遇到困难（我将不得不改变它相对于 RA-4 相纸使用的光源，或者尝试理解这个问题）。
> 对比使用的是 Kodak Ultramax 400，碰巧可以被拟合。

不确定这是否有帮助，但之前我在研究胶片扫描时，发现了这个 Kodak 的带通滤镜专利，它可以用来移除光谱中有问题的部分，使不同的扫描仪光源表现得更相似。也许加入这个滤镜能解决你遇到的一些拟合问题？

[Kodak_Printing_Filter_Patent.pdf](/uploads/short-url/6cf9QUUK2axQ61ThJUaHrynZR23.pdf) (682.1 KB)

---

## #170 **Jakob Andrén** (@jandren) · 2025-03-04 21:53

我提出测试图像的想法是想看看光谱上采样在到达光谱边界时的表现。我会尝试自己做些测试，看看是否能提供一些见解。使用 hanatos 大色域光谱上采样方法的新结果确实好多了，所以一切都很令人期待！

我还意识到另一个测试源可以是真实的高光谱图像！以下是我目前找到的一些不错的来源。

1. 哥伦比亚大学成像与视觉实验室的多光谱图像数据库，规模不大但图像选择不错。[CAVE](https://cave.cs.columbia.edu/repository/Multispectral)
2. 中国 Bian Lab 的大型*高光谱成像数据集*，需要申请访问权限，我还没试过，但看起来可行。[GitHub - bianlab/Hyperspectral-imaging-dataset](https://github.com/bianlab/Hyperspectral-imaging-dataset?tab=readme-ov-file)
3. 哈佛的一个数据集，质量较低：[Statistics of Real-World Hyperspectral Images](https://vision.seas.harvard.edu/hyperspec/index.html)
4. 用旋转线阵相机拍摄的低质量和分辨率数据集：[danaroth/icvl · Datasets at Hugging Face](https://huggingface.co/datasets/danaroth/icvl) 直接 git clone 链接即可下载。
5. 人脸数据集，同样需要申请访问权限，我还没试过。但人脸当然很有趣！[GitHub - hyperspectral-skin/Hyper-Skin-2023: Introducing Hyper-Skin data with 2 types of data pairs: 1. (RGB, VIS), 2. (MSI, NIR)](https://github.com/hyperspectral-skin/Hyper-Skin-2023?tab=readme-ov-file)
6. 最后一个看起来非常有希望，说是开放的，但我无法访问。如果有人能访问，可以添加到这里：[GitHub - boazarad/ARAD_1K: ARAD_1K Spectral Image Dataset](https://github.com/boazarad/ARAD_1K)

我还知道于默奥当地一家从事高光谱图像的公司。如果你有任何具体可行的想法，想要一张高光谱测试图片，我或许可以请他们用他们的相机拍一两张。

---

## #171 **Todd Prior** (@priort) · 2025-03-05 04:40

哈哈，顺便提一下，我们刚有一个来自那所大学的学生来访问我们。她在加拿大这里呆了几个星期。她在演讲中介绍了一些关于该地区和大学的背景信息。那看起来是世界上最可爱的地方之一……

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

---

## #172 **** (@mikae1) · 2025-03-05 08:28

> **@arctic** (帖子 #166):
> 我注意到非常深的黑色。

看起来非常不错！这跟我有一个问题相关。我把一些照片送去用 Fuji Crystal Archive 纸张打印。对于这些照片，我觉得应该禁用 agx-emulsion 的相纸模拟部分，否则它们会被"双重覆纸"，导致黑色非常灰白。

对于应该在屏幕上查看的文件（上传到我的网站或社交媒体），我希望启用相纸模拟。

这是否可能实现（以及我的想法是否正确）？

**编辑：** 也许一种方法是我假设我已经扫描了一张纸质打印件。在暗房时代扫描纸质打印件后，我当然会设置黑白场。是否可以在 agx-emulsion 中作为最后一步提供黑白场控制？

但是，我仍然会"两次应用"相纸的"色彩特性"？

我也许还应该提一下，我非常欣赏 agx-emulsion 包含了纸张特性。我遇到的大多数其他胶片模拟方案都试图模拟扫描仪（通常是 Frontier 或 Noritsu）的色彩特性。然而，负片胶片从来就不是为了被扫描而设计的，它是为了被打印而存在的。

---

## #173 **Andrea** (@arctic) · 2025-03-05 11:23

谢谢 [@hanatos](/u/hanatos) 更新了 LUT 并分享了 GitHub 问题！

我已经替换了旧的。

确实，只看系数图，它们在越过光谱轨迹后看起来平滑多了。

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/f/2/f218a61672f0c064ea3ef084ac5881895e4a7785.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/f/2/f218a61672f0c064ea3ef084ac5881895e4a7785.png)

image516×149 12.4 KB](/uploads/short-url/yxGmaFZurdcobIOfQhllMYtJ7Fj.png?dl=1)

我在同一张[花卉照片](https://discuss.pixls.us/t/dealing-with-yellow-color-shift/48530)（我导出为线性 ProPhoto RGB）上比较了旧 LUT 和新 LUT。

（左）新 LUT - （右）旧 LUT

[[![flower_fuji400h_crystal_05pe_2Y_10M_newlut](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/2/32c6b72f92b67502b9ec247f95d839565d519c04_2_330x220.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/2/32c6b72f92b67502b9ec247f95d839565d519c04_2_330x220.jpeg)

flower_fuji400h_crystal_05pe_2Y_10M_newlut3000×2000 911 KB](/uploads/short-url/7fbCpZYGniA4GVdOuiR4FgvYN3S.jpeg?dl=1)

[[![flower_fuji400h_crystal_05pe_2Y_10M_oldlut](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/e/0ea46a1c628d325874244fc90355b8b4a75ca970_2_330x220.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/e/0ea46a1c628d325874244fc90355b8b4a75ca970_2_330x220.jpeg)

flower_fuji400h_crystal_05pe_2Y_10M_oldlut3000×2000 911 KB](/uploads/short-url/25wWlh4tQXeDskJ8XwwEwH8rqMw.jpeg?dl=1)

确实如你所料，效果不太明显。

但这仍然很棒，也许我可以稍微放宽正则化。

---

## #174 **Andrea** (@arctic) · 2025-03-05 11:45

太喜欢这些专利草图了！

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/e/b/eb045cca8f0e1c0b33f4a002446d5bb7a89fe220.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/e/b/eb045cca8f0e1c0b33f4a002446d5bb7a89fe220.png)

image1051×286 15.9 KB](/uploads/short-url/xx3yefNaPM604iUhzILQ6FbWOS4.png?dl=1)

我读了部分专利，同意他们建议添加大约 500 nm 和 610 nm 的窄带滤光，可能有助于减少"问题"区域并统一不同光源（光源 + 滤光）的输出。

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/7/e7466ae24fcfcc1b5a2dc7abef44882d4dc969a7_2_400x290.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/7/e7466ae24fcfcc1b5a2dc7abef44882d4dc969a7_2_400x290.png)

image867×578 26.9 KB](/uploads/short-url/wZXacmfeZQU2HIIV2mgQnqDov8b.png?dl=1)

这是推荐的滤波器，它也会使光源略微暖一些，比红色部分更多地减少蓝色部分。

我也很好奇它对 Portra 胶片和相纸会有什么效果，尤其是是否会让它更接近消费级胶片和相纸。

感谢 [@NateWeatherly](/u/nateweatherly)！

---

## #175 **Andrea** (@arctic) · 2025-03-05 13:03

> **@jandren** (帖子 #170):
> 我会尝试自己做些测试，看看是否能提供一些见解。

那就太好了！期待中！

这也是一个很棒的仓库列表！

将高光谱图像作为参考可能很有趣，通过一些 hack 可以直接用于输入。此外，拥有真实物体真实代表性光谱的良好数据库也可能很有趣。

> **@jandren** (帖子 #170):
> 我还知道于默奥当地一家从事高光谱图像的公司。如果你有任何具体可行的想法，想要一张高光谱测试图片，我或许可以请他们用他们的相机拍一两张。

哦，不错，有好的朋友很重要。我没有什么具体的想法，但可以记在心上。你能多介绍一下他们的相机吗？我纯粹是出于技术好奇。我想有很多方法可以制作高光谱图像。

---

## #176 **Andrea** (@arctic) · 2025-03-05 13:34

> **@mikae1** (帖子 #172):
> 但是，我仍然会"两次应用"相纸的"色彩特性"？

我猜胶片和相纸在模拟打印过程中的物理交互是我们希望保留的，因为它编码了部分外观。它确实编码了色彩偏移和风格，比如比较 Portra 和 Endura Premier。

我不是专家，但我相信当使用现代打印机和数字工作流程在相纸上打印时，这个过程会优化以追求最大的色彩准确性。换句话说，打印机被校准以尽可能在物理上匹配输入的数码 RGB 文件和输出的打印颜色（在正确的观察条件下观察打印件时）。尽管如此，纸张的物理限制仍然存在，比如白点和黑点。

这个挑战可以重新表述为：

*在 `agx-emulsion` 中，我们如何确保导出的文件在使用现代打印机打印在相纸上时，能尽可能接近我们使用胶片（+放大机）拍摄同一原始场景时所能制作的模拟打印件？*

考虑到这个用例，我们当然应该谨慎地停用部分模拟。例如，特征性的白/黑点和眩光即使在使用数字打印工作流程时也会在相纸上重现。打印机对此无能为力。

例如，我相信现代打印机已经以最佳方式考虑了观察眩光补偿，因为它们被设计为适应数字摄影师的工作流程。图片是在屏幕上由希望在打印时获得好结果的人编辑的。

用于模拟打印的相纸特征曲线肯定编码了观察眩光补偿（比预期更深的阴影，因为它们会被眩光照亮），所以我们应该移除它，并确保我们在经过校准的屏幕上看到的图像具有我们想要的深度的阴影。

所以概括来说，我认为在这个用例中，添加黑白场控制、禁用随机眩光以及使用观察眩光补偿移除控制，应该会有所帮助。也许我们可以有一个 `simulate_for_print` 复选框来实现这一点。

在屏幕上查看模拟图像时，我们应该模拟所有的纸张特性。

这样说是否合理，还是我遗漏了什么？

---

## #177 **jo** (@hanatos) · 2025-03-05 16:15

我尝试实现了成色剂。

[[![out](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/f/efd0f146cbcc3ce62769eb588e9abc40970dbf69_2_690x332.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/f/efd0f146cbcc3ce62769eb588e9abc40970dbf69_2_690x332.jpeg)

out2244×1080 851 KB](/uploads/short-url/ydvLU49xL0n6gB1bDuYGfY3W13b.jpeg?dl=1)

这是 `couplers=0.0, 0.2, ..1.0`。在我屏幕上看，它增加了不少色彩饱和度…… 但 pixls 预览看起来像是被钳制了。可能是我的 Firefox 试图做色彩管理然后失败了。所以这里还有一个 `couplers=0.0,0.5,1.0,1.5,2.0` 的楔形图：

[[![out2](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/5/75556afc993c5d2be12943ff3217526de74fccad_2_690x422.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/5/75556afc993c5d2be12943ff3217526de74fccad_2_690x422.jpeg)

out21765×1080 793 KB](/uploads/short-url/gJYS0s24CtEqhuscEnYMxk5wp9b.jpeg?dl=1)

2.0 完全过头了，但对我来说没问题

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

不管怎样…… 我用了你的近似，又加了一些。一个简化是我假设释放的成色剂取决于 log 曝光，而不是密度。所以它几乎是线性的…… 没有饱和。不确定在某些地方会不会出问题…… 但它在密度查找之前发生，提前调整了曝光，所以对黑/白仍有平滑过渡。

更准确地说，我假设测量的密度曲线依赖于 log 曝光 <span class="math">D(e)</span>，这些曲线是通过使用中性色测试条渐变获得的。我假设它在局部是平坦/恒定的，或者向稍微更暗和稍微更亮的地方扩散的程度相同，所以空间扩散在某种程度上相互抵消。在这种情况下，实际的校正后 log 曝光 <span class="math">e_0 = e - K*e</span>，由初始曝光与空间和层间的核 <span class="math">K</span> 的卷积减去得到，这简化为仅与层扩散矩阵 <span class="math">M</span> 的相互作用，即 <span class="math">e_0 = e - M\cdot e</span>。所以我声称实际的密度-曝光函数 <span class="math">D_0(e)</span> 被观测为 <span class="math">D(e) = D_0(e - M\cdot e)</span>。这仅在测试条的上下文中有效，对于中性色的 <span class="math">e</span>。

由此我计算实际的密度函数 <span class="math">D_0(e) = D((I-M)^{-1}\cdot e)</span>，这将产生与没有成色剂时完全相同的效果，但仅在 <span class="math">e</span> 为中性色时成立。

这对你有任何意义吗？近似太多了吗？

成色剂 <span class="math">M\cdot e</span> 的模糊半径与图片较长边成比例，在普通 RAW 图像中大约为 20 像素，我想。我喜欢大半径带来的局部对比度增强。

额外的好处是，显示缓冲区现在有了 mipmap，所以缩小时可以更真实地看到颗粒效果。2x 和 4x 缩放也能用…… 但 4x 真的需要*大量* GPU 内存……

这些还没有推送，但不久后会推送。

---

## #178 **** (@niklasiivari) · 2025-03-05 19:16

[@hanatos](/u/hanatos) 你知道这里出了什么问题吗？尝试使用 vkdt filmsim，但图片总是发紫，无论怎么调整颜色或滤镜都无法修复。在两台不同的电脑上都发生了，OpenSUSE Tumbleweed（试过 AppImage 和编译）和 Windows 上都是如此。

我已经按照 GitHub 页面上的说明创建了 filmsim.lut。

[[![Screenshot From 2025-03-05 21-07-27](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/a/0afa515fe66aaae1fe9ef8ccf00df3aca7fa3dcc_2_690x405.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/a/0afa515fe66aaae1fe9ef8ccf00df3aca7fa3dcc_2_690x405.png)

Screenshot From 2025-03-05 21-07-271943×1142 667 KB](/uploads/short-url/1z74QR87chRXzbc8MXgZtcwVEzW.png?dl=1)

---

## #179 **jo** (@hanatos) · 2025-03-06 09:12

> **@niklasiivari** (帖子 #178):
> 尝试使用 vkdt filmsim，但图片总是发紫

……你能给我一个 raw + cfg 文件让我看看是否能重现吗？

---

## #180 **** (@niklasiivari) · 2025-03-06 11:45

给你：

[_DSC0375.NEF.cfg](/uploads/short-url/fH7DLhCq3Ahd1Ljorjy36wz3iZa.cfg) (3.8 KB)

[_DSC0375.NEF](/uploads/short-url/ne3SC6ExYUAme4tqWFywZUFC7yc.NEF) (25.5 MB)

---

## #181 **Andrea** (@arctic) · 2025-03-06 12:23

> **@hanatos** (帖子 #177):
> out2244×1080 851 KB
> out2244×1080 851 KB

这看起来确实相当有前景！考虑到简化模型。

[![:grinning:](https://discuss.pixls.us/images/emoji/apple/grinning.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grinning.png?v=12)

我有点担心当你加强抑制时出现的更白的光晕，但可能正如你所说，完全过头了。

希望我正确理解了你的近似。这里有一些评论。

> **@hanatos** (帖子 #177):
> 这对你有任何意义吗？近似太多了吗？

我认为不让抑制量饱和可能违反了"质量守恒"。我的意思是，在化学中，你可以生成的反应产物量受限于反应物的量。如果反应物用完了，反应就会停止。由于抑制剂分子是在乳剂中产生主染料（CMY）的同时释放的，那么当我们达到最大密度时，抑制剂也应该达到最大值。或者如果没有产生密度，抑制效应就不应该存在，因为它们一开始就没有被产生。

仅使用 M*e 没有考虑这种饱和。这在照片中密度饱和的区域（趾部之前和肩部之后）可能过于剧烈，但在线性部分应该仍然没问题。所以问题可能在于我们是否能接受这个近似。

我对层间效应和 DIR 成色剂的建模也来自于研究 Hunt 书中的一些示意图 [Hunt, The reproduction of color, 第 6 版, Wiley 2004]。在第 256 页，有一个关于层间效应在胶片上如何工作的示意图。

[[![hunt_page_256](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/6/c6305fd335bbfdb7371b628c565ac6e4334e6ef1.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/6/c6305fd335bbfdb7371b628c565ac6e4334e6ef1.png)

hunt_page_256690×512 98.6 KB](/uploads/short-url/shgbcoyC1uQvI44RVoiXQpOcyKB.png?dl=1)

这是针对正片的，但概念应该适用。让我们关注图(c)，它展示了一些测试楔的实验，其中两个通道（红色和绿色，C 和 M 层）的曝光保持恒定，而蓝色曝光按照一个渐变变化（Y 层）。最终的 C 和 M 密度将受到 Y 通道中显影的密度量的影响。

我写了一个小脚本来用你的模型和当前 `agx-emulsion` 中的模型重现图(c)中的实验。

两个模型在使用中性渐变作为曝光时，密度曲线不受影响。

[[![Figure_1](https://d2x313g9lpht1q.cloudfront.net/original/3X/4/0/40ade0e80fd4694a31999c16f8029c3cb6173e2d.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/4/0/40ade0e80fd4694a31999c16f8029c3cb6173e2d.png)

Figure_1640×480 23.4 KB](/uploads/short-url/9eb5Er668S7abZjfOwsgGn2TNdX.png?dl=1)

[[![Figure_2](https://d2x313g9lpht1q.cloudfront.net/original/3X/2/a/2ac4d0d7f0144e493d0f4f9de82a7157b0a09f31.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/2/a/2ac4d0d7f0144e493d0f4f9de82a7157b0a09f31.png)

Figure_2640×480 24.1 KB](/uploads/short-url/66lJeNambVnbnYwgUPiKABNLxMl.png?dl=1)

当只有蓝光曝光使用渐变而其他通道使用恒定曝光时，效果如下。

[[![Figure_3](https://d2x313g9lpht1q.cloudfront.net/original/3X/2/e/2e0d84f10bb4c5deac12f3baa0c607acd0cb138e.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/2/e/2e0d84f10bb4c5deac12f3baa0c607acd0cb138e.png)

Figure_3640×480 27.4 KB](/uploads/short-url/6zoVzAGQYMv9zZNAE1rzlIPPo5w.png?dl=1)

[[![Figure_4](https://d2x313g9lpht1q.cloudfront.net/original/3X/3/e/3e049d53794d155f2225e2d32bab378035f10824.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/3/e/3e049d53794d155f2225e2d32bab378035f10824.png)

Figure_4640×480 34.3 KB](/uploads/short-url/8QDumOxER0bTrlNOizNP5LTJI6o.png?dl=1)

<details>
<summary>
用于生成图表的代码</summary>

<pre data-code-wrap="python"><code class="lang-python">import numpy as np
import matplotlib.pyplot as plt

def curve(e, ks):
 y = np.zeros((3, e.shape[0]))
 for i, k in enumerate(ks):
 gamma = k[0]
 e0 = k[1]
 ymax = k[2]
 c1 = k[3]
 c2 = k[4]
 y[i] = ( gamma/c1 * np.log10(1 + 10**(c1 * (e - e0) ) )
 - gamma/c2 * np.log10(1 + 10**(c2 * (e - e0 - ymax/gamma)))
 )
 return y

k0 = [[ 0.6, -1.4, 2.00, 2, 1],
 [ 0.6, -1.5, 1.95, 2, 1],
 [ 0.6, -1.6, 2.05, 2, 1]]
k0 = np.array(k0)

N = 1024
e = np.linspace(-4,5,N) # log 曝光
dc = curve(e, k0) # 密度曲线

def plot_density(e, dc, ax=None, add_labels=True, alpha=1):
 if ax is None:
 _, ax = plt.subplots()
 # colors = ['tab:red', 'tab:green', 'tab:blue']
 colors = ['tab:cyan', 'tab:pink', 'gold']
 for i in np.arange(3):
 if add_labels==True:
 # l='RGB'[i]
 l='CMY'[i]
 else: l ='_nolegend_'
 ax.plot(e, dc[i], color=colors[i], label=l, alpha=alpha)
 ax.set_xlabel('Log 曝光')
 ax.set_ylabel('密度')
</code></pre>

</details>
 ax.legend()

def interp_with_curves(x, e, dc):
 if np.size(e.shape) == 1:
 e = np.vstack((e,e,e))
 d = np.zeros((3, e.shape[1]))
 for i in np.arange(3):
 d[i] = np.interp(x[i], e[i], dc[i])
 return d

##############################################################################
# 模型

def density_dir_model_a(raw, e, dc, M):
 e = np.vstack((e,e,e)) # 对数曝光
 d_max = np.max(dc, axis=1)

 d_max = d_max[:,None]
 raw_mid = e - np.einsum('ck, cm->mk', dc/d_max, M)
 dc0 = interp_with_curves(e, raw_mid, dc) # 密度曲线 0，抑制前

 d0 = interp_with_curves(raw, e, dc)
 raw_corr = raw - np.einsum('ck, cm->mk', d0/d_max, M) # 校正后的对数曝光

 d = interp_with_curves(raw_corr, e, dc0)
 return d

def density_dir_model_hanatos(raw, e, dc, M):
 M = M*0.1 # 缩减抑制矩阵以大致匹配模型
 e = np.vstack((e,e,e)) # 对数曝光

 e_mid_corr = np.einsum('ck, cm->mk', e, np.linalg.inv(np.eye(3)-M))
 dc0 = interp_with_curves(e_mid_corr, e, dc) # 密度曲线 0，抑制前

 raw_corr = raw - np.einsum('ck, cm->mk', e, M) # 校正后的对数曝光
 d = interp_with_curves(raw_corr, e, dc0)
 return d

##############################################################################
# 测试模型
M = np.ones((3,3))/3

def test_models(e, dc, M, density_model, e_levels=[-1, 0, 1, 4], experiment='neutral_ramp'):
 _, ax = plt.subplots()
 alpha = [0.3,0.5,0.7,1]
 for i, ei in enumerate(e_levels):
 if experiment=='rg_constant':
 raw = np.vstack((ei*np.ones(N), ei*np.ones(N), e))
 elif experiment=='g_constant':
 raw = np.vstack((e, ei*np.ones(N), e))
 elif experiment=='neutral_ramp':
 raw = np.vstack((e, e, e))
 d = density_model(raw, e, dc, M)
 plot_density(e, d, ax=ax, add_labels=False, alpha=alpha[i])

# 中性渐变
test_models(e, dc, M, density_dir_model_hanatos, experiment='neutral_ramp')
plt.title('hanatos DIR 成色剂模型 - 中性渐变')

test_models(e, dc, M, density_dir_model_a, experiment='neutral_ramp')
plt.title('当前 agx-emulsion DIR 成色剂模型 - 中性渐变')

# hunts 图(c) 实验 第256页
test_models(e, dc, M, density_dir_model_hanatos, experiment='rg_constant')
plt.title('hanatos DIR 成色剂模型')

test_models(e, dc, M, density_dir_model_a, experiment='rg_constant')
plt.title('当前 agx-emulsion DIR 成色剂模型')
plt.show()
</code></pre>

</details>

请告诉我是否我的 Python 代码实现与你的意思不符。

我认为在对数曝光低于 2（或高于 2.5）时发生的情况不现实，因为 Y 层无法释放抑制剂，不应影响 C 和 M（或者已经在另一侧耗尽所有可释放的抑制剂）。因此，在趾部之前（或肩部之后），C 和 M 染料的密度不应再变化，因为 Y 层不再受到减少（或增加）曝光的影响。

我还认为，如果 C 和 M 层能产生抑制剂，它们也应该影响 Y 层。C 和 M 上的密度越高，Y 层受到的抑制就越大（这在 Hunt 的草图中没有真正体现，可能是因为他对齐了黄色曲线以使草图更清晰）。

在我看来，在这种基于物理的模拟中，重现从物理角度讲合理的东西对最终效果非常有帮助。但当然，我们可以选择有助于计算效率或便利性的方案。我觉得这有点过于违背过程的化学性质了。

[![:grin:](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)

 你怎么看？

---

## #182 **jo** (@hanatos) · 2025-03-06 13:01

> **@niklasiivari** (帖子 #180):
> 给你：

嗯，我这边能用。这是我的 LUT，也许是生成时出了什么问题：

[filmsim.lut](/uploads/short-url/upRe0PddpftEQAUZLq6fsYy8II6.lut) (144.0 KB)

---

## #183 **** (@niklasiivari) · 2025-03-06 13:07

谢谢，现在完美运行了！

这是用仓库里相同的脚本创建的吗？我猜我可能缺少一些所需的 python 库，但运行时没有看到任何错误，我尝试在 venv 中使用 agx 依赖项以及使用系统包运行，所以不清楚。

---

## #184 **jo** (@hanatos) · 2025-03-06 13:10

嗯，我们永远找不到原因了

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 我应该把这个打包发布。我总是对把生成的文件检入 git 犹豫不决，但在这个情况下便利性上的提升相当可观……

---

## #185 **jo** (@hanatos) · 2025-03-06 13:19

> **@arctic** (帖子 #181):
> 违反了"质量守恒"

对。我想守恒能量。谢谢你找到这些额外的图！我会考虑如何优化代码让它不拖慢速度……

---

## #186 **Bob** (@PhotoPhysicsGuy) · 2025-03-06 15:41

> **@hanatos** (帖子 #185):
> 我想守恒能量。

但你想守恒的是哪种能量呢？

模拟过程将来自场景光场（或光子通量）的光子能量转化为"击碎"预先沉积的卤化银形成银，在不同层中对不同波长敏感。

从那时起，就是化学反应中的质量比了。至少我认为 DIR 成色剂本身不具有光敏性。（编辑：当然，我可能搞错了）

我认为这也意味着：完全可以"升转换"红外曝光来调制可见光（Kodak Aerochrome），或者"降转换"X 射线曝光来调制可见光（典型的模拟 X 光片）。

彩色负片中的增感剂可以对不同波长的光敏感，而这些波长与形成的染料在正片中透过的波长不同。

我认为这打破了我理解中的能量守恒。

---

## #187 **jo** (@hanatos) · 2025-03-06 15:43

质量就是能量，我想说的就是这个。在我的领域，我们通常保持物质/你可以触摸的东西不变，所以我最关心的通常是能量守恒，这是同一回事。

---

## #188 **Andrea** (@arctic) · 2025-03-06 17:14

最终爱因斯坦展示了质量与能量的关系 <span class="math">E=mc^2</span>，所以我们完全可以以能量的概念重新诠释拉瓦锡的质量守恒定律

[![:grin:](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)

---

## #189 **jo** (@hanatos) · 2025-03-06 17:18

> **@niklasiivari** (帖子 #183):
> 这是用仓库里相同的脚本创建的吗？我猜我可能缺少一些所需的 python 库，但运行时没有看到任何错误，我尝试在 venv 中使用 agx 依赖项以及使用系统包运行，所以不清楚。

我可以确认新创建的 lut 会变紫。在 agx-emulsion 仓库中进行 git bisect 后，我发现：0cdb191086811c73de0d06b42124591397a49ac8 是第一个坏提交。得看看是怎么回事。它确实替换了所有 profile json 文件，但很可能只是我的 python 转换没有正确理解它。我相信数据从 10nm 间距切换到了 5nm，而我的 python 有点过于依赖假设了

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 我肯定能修好。

---

## #190 **Nate Weatherly** (@NateWeatherly) · 2025-03-06 19:04

[@arctic](/u/arctic) 你能多介绍一下补偿消除因子/密度/过渡吗？这是否旨在降低"打印"中的黑色，以视觉上补偿显示器与打印相比相对更深的黑色，类似于 Davinci Resolve 色彩转换节点中的 EOTF（即 REC709 编码 TF 与 Gamma 2.4 显示 TF 之间的差异）？

我一直在试着调整它，但无论使用什么值，输出都看不到任何差异。我确认它已激活且眩光百分比设为零。尝试了计算全图，结果仍然一样。我遗漏了什么吗？

另外，只是好奇为什么 Kodak Endura Premier 相纸比其他纸张对比度大这么多。我注意到 Portra 400 数据表指定该胶片设计用于在 Endura Premier 上打印，但结果比我的 Portra 400 扫描件对比度大得多，甚至在像扫描一样调整黑白点之后更是如此。这是否与 Endura Premier 是为数字打印而非光学打印设计有关？谢谢！

---

## #191 **** (@mikae1) · 2025-03-06 20:15

我运行了 `vkdt-rawler-pentablet-0.9.99-353-g8c9e66c4-x86_64.AppImage` [@hanatos](/u/hanatos)。里面能找到 agx-emulsion 模块吗？我尝试用"按名称筛选模块"搜索"emulsion"、"agx"和"film"，但没有找到。

---

## #192 **** (@mikae1) · 2025-03-06 20:47

> **@arctic** (帖子 #173):
> 确实如你所预测，效果不太明显。

谢谢。我在这两个之间切换，正准备写：说实话，在我看来差别不大。

[![:smiley:](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)

> **@arctic** (帖子 #176):
> 我想胶片和相纸在模拟打印过程中的物理相互作用正是我们希望保留的，因为它编码了部分外观。它确实编码了色偏和风格，比如比较 Portra 和 Endura Premier 就知道了。

如我之前所说，我想这都归结于我们想要模拟什么。2010 年代初的 VSCO Lightroom 和 Adobe Camera Raw 预设和配置文件尽可能地模拟了 Noritsu 和 Frontier 扫描仪对多种胶片的表现。他们显然没有想到使用技术文档这个绝妙的主意。

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

> **@arctic** (帖子 #176):
> 在屏幕上查看模拟图像时，我们应该模拟所有纸张的特性。

对于一种本应用于打印的媒介（负片），我认为模拟纸张输出更有意义。但即便如此，要在数字领域使用纸质副本，我们最终还是需要扫描它。如果我们想模拟整个链条，我认为应该是这样的：

1. (C-41) 胶片冲洗
2. (RA-4) 相纸冲洗
3. 扫描

扫描步骤可以用黑白点以及可能的曲线控制和直方图来表示。如果 agx-emulsion 在 vkdt 或 darktable 中实现，我们可以直接在全新炫酷的 emulsion 色调映射模块之后放置色阶和曲线模块。

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

但要让黑白点控制在 agx-emulsion 中真正可用，还是需要一个直方图。

---

## #193 **Andrea** (@arctic) · 2025-03-07 00:14

> **@NateWeatherly** (帖子 #190):
> 你能多介绍一下补偿消除因子/密度/过渡吗？这是否旨在降低"打印"中的黑色，以视觉上补偿显示器与打印相比相对更深的黑色，类似于 Davinci Resolve 色彩转换节点中的 EOTF（即 REC709 编码 TF 与 Gamma 2.4 显示 TF 之间的差异）？

相纸会反射部分入射光，产生眩光。这实际上会提亮阴影。相纸的设计也通过使阴影比预期更深来抵消观看时的眩光，并将这一点编码在密度曲线中。

`agx-emulsion` 具有随机眩光模拟功能，应该可以补偿这一点，同时还在打印最黑的区域添加一些噪点。

正如与 [@mikae1](/u/mikae1) 讨论的那样，对于打印，我们可能不希望添加最终真实纸张上已经存在的随机眩光。所以在这种情况下，观看眩光补偿消除可以通过稍微改变相纸的密度曲线来提亮一点阴影。

下面是一个示例，展示了 `transition`=0.3 和 `density`=1.2 的效果。

`density` 定义补偿生效时的密度。

`transition` 定义从不受影响区域到补偿区域的过渡宽度（以密度值表示）。

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/2/7/27d0aeac84726ada3aed964f4db04c2a708f3d1e.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/2/7/27d0aeac84726ada3aed964f4db04c2a708f3d1e.png)

image857×480 49.4 KB](/uploads/short-url/5GdII7E206MfdwzXnuqc2BClGEK.png?dl=1)

> **@NateWeatherly** (帖子 #190):
> 我一直在试着调整它，但无论使用什么值，输出都看不到任何差异。我确认它已激活且眩光百分比设为零。尝试了计算全图，结果仍然一样。我遗漏了什么吗？

你发现了一个 bug！谢谢！补偿实际上并没有生效。我刚向 `main` 分支推送了一个修复，启用了观看眩光补偿消除。有时间再测试一下吧。

> **@NateWeatherly** (帖子 #190):
> 另外，只是好奇为什么 Kodak Endura Premier 相纸比其他纸张对比度大这么多。

我认为它对比度非常大是因为它是一种消费级相纸，旨在给普通消费者带来一些惊艳效果（有点像耳机中的低音和高音增强）。但我不是真实相纸的专家，因为我从未使用过真正的 RA-4 相纸。

> **@NateWeatherly** (帖子 #190):
> 但结果比我的 Portra 400 扫描件对比度大得多，甚至在像扫描一样调整黑白点之后更是如此。

负片具有巨大的宽容度，在扫描中我们实际上可以保留很多宽容度，并轻松生成对比度更低的图像。RA-4 相纸经过优化，可以提供令人愉悦且令人满意的对比度。根据我有限的体验，它比你预期的对比度更大——相比于普通的负片扫描。但可能比我更有经验的人可以发表评论并提出更好的见解。

最终，模拟做的是数据所编码的内容，所以如果我们信任数据（以及将其数字化的"猴子"），这就是相纸应有的对比度。

---

## #194 **Andrea** (@arctic) · 2025-03-07 00:15

搜索 `filmsim`！

[![:wink:](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)

---

## #195 **Andrea** (@arctic) · 2025-03-07 00:27

> **@mikae1** (帖子 #192):
> (C-41) 胶片冲洗
> (RA-4) 相纸冲洗
> 扫描

目前，扫描步骤更像是对人类观看打印品时视觉的模拟。在我看来，这甚至可能比想要模拟扫描仪更好。

> **@mikae1** (帖子 #192):
> 扫描步骤可以用黑白点以及可能的曲线控制和直方图来表示。如果 agx-emulsion 在 vkdt 或 darktable 中实现，我们可以直接在全新炫酷的 emulsion 色调映射模块之后放置色阶和曲线模块。

确实！但我们可能可以添加一个开关，进行"分析式"黑白点校正，使白色真正为白，黑色真正为黑。对于白色，已经有 `special` >> `print_density_min_factor`，当设置为 0 时，会去除纸张基底的吸收，使打印品中的白色变为 [1,1,1]。由于我们知道相纸的最大密度（通常约为 2.5/3），我们还可以估算黑点并进行自动校正，使黑色变为 [0,0,0]。我会考虑如何巧妙地实现这一点！

---

## #196 **** (@mikae1) · 2025-03-07 08:22

> **@arctic** (帖子 #195):
> 目前，扫描步骤更像是对人类观看打印品时视觉的模拟。在我看来，这甚至可能比想要模拟扫描仪更好。

抱歉造成混淆。我**并不是**说步骤 3 的目的是模拟扫描仪的特性（像 VSCO 的 Noritsu/Frontier 尝试那样），而是假设一个*完美*的数字化过程，同时具备调整黑白点和曲线的能力（以便导出的文件可以送去打印）。

这可能变得更多是哲学性的而非技术性的，但当我们从 agx-emulsion 导出图片（或"保存选定图层"）时，这相当于扫描打印品。我的想法是，给用户对这个"扫描"过程的基本控制是有意义的。

> **@arctic** (帖子 #193):
> 相纸会反射部分入射光，产生眩光。这实际上会提亮阴影。相纸的设计也通过使阴影比预期更深来抵消观看时的眩光，并将这一点编码在密度曲线中。
> agx-emulsion 具有随机眩光模拟功能，应该可以补偿这一点，同时还在打印最黑的区域添加一些噪点。
> 正如与 @mikae1 讨论的那样，对于打印，我们可能不希望添加最终真实纸张上已经存在的随机眩光。所以在这种情况下，观看眩光补偿消除可以通过稍微改变相纸的密度曲线来提亮一点阴影。

谢谢你的重申。我现在意识到这听起来多么棒，也许对你的应用来说已经足够了。我会下载并试一试。总还有 GIMP 可以做进一步的"扫描后"校正。

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 当 agx-emulsion 在其他应用（如 vkdt 或 darktable）中实现时，可以在必要时通过在 agx-emulsion 之后放置的模块来应用色阶和曲线。

说到 darktable。将 GLSL 代码移植为 C 语言模块用于 darktable 有多难？也许该问 [@hanatos](/u/hanatos)、[@flannelhead](/u/flannelhead) 或 [@Pascal_Obry](/u/pascal_obry)？

> **@arctic** (帖子 #194):
> 搜索 filmsim！

哎呀，没有结果！

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/8/c81c79db825c3af28f14ca0c18ebbcc6d31705d8.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/8/c81c79db825c3af28f14ca0c18ebbcc6d31705d8.jpeg)

image374×577 80.6 KB](/uploads/short-url/sygve2342U1mEerWQaHooPoRYLe.jpeg?dl=1)

---

## #197 **jo** (@hanatos) · 2025-03-07 09:01

> **@mikae1** (帖子 #196):
> 哎呀，没有结果！

[[![2025-03-07-095945_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/9/398b92ba2b04b9e28967e46bb3f2469c013ae68d_2_690x454.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/9/398b92ba2b04b9e28967e46bb3f2469c013ae68d_2_690x454.png)

2025-03-07-095945_hyprshot1335×879 303 KB](/uploads/short-url/8d4fuGgqNL3bmzkEJfxmVYCOqrb.png?dl=1)

必须在这个^对话框里，即应用预设或按快捷键 ctrl-p。

另外，如果你拉取最新版本，vkdt 现在带有优秀的 5nm 间距 filmsim.lut。这意味着所有人都必须删除他们的 `~/.config/vkdt/data/filmsim.lut`，因为 home 目录中的文件会优先（而且很可能是旧版 lut）。

---

## #198 **** (@mikae1) · 2025-03-07 10:22

> **@mikae1** (帖子 #196):
> 当从 agx-emulsion 导出图片（或"保存选定图层"）时，这相当于扫描打印品。

我当然想得比开发进度超前了很多，但这实际上可以成为一个有趣的设计特色。"计算全图"复选框可以移除，"运行"可以替换为"预览"和"扫描"按钮。这样计算时间突然就有意义了。

[![:wink:](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)

Epson Scan 称之为预览和扫描：

[[![epson_scan_scan](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/a/5a17a05b3def2eb8957272c8067e8ee0c5a53252_2_690x631.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/a/5a17a05b3def2eb8957272c8067e8ee0c5a53252_2_690x631.png)

epson_scan_scan837×766 123 KB](/uploads/short-url/cQZAGjjK6xMvAN7DUtKLLCidAHw.png?dl=1)

VueScan 也称之为预览和扫描：

[[![vuescan_scan](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/5/05120cf2832e9dbf10ac20b2ce7ff63ce531cd4e_2_521x1000.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/5/05120cf2832e9dbf10ac20b2ce7ff63ce531cd4e_2_521x1000.png)

vuescan_scan668×1280 107 KB](/uploads/short-url/IR3KGpUDrGHdbkJ18txT4NREqW.png?dl=1)

"保存"将保存预览或全图（取决于上次渲染的方式）。

---

## #199 **Andrea** (@arctic) · 2025-03-08 07:36

> **@mikae1** (帖子 #198):
> Epson Scan 称之为预览和扫描：

这是一个非常好的建议，尤其是这是一个为慢速"处理"优化的 UI，就像平板扫描仪的负片扫描一样。而且它与 `agx-emulsion` 的慢处理有些契合

[![:grin:](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)

，因为它需要预览才能使用。裁剪控件也非常相似。

谢谢你的建议。我快速看了一下 `magicgui` 的功能。这个库非常适合快速制作极其简洁的代码 GUI，但可能缺乏通用性。我找到了一个添加多个按钮的解决方案，但这会破坏其他小部件的对齐。我会再花些精力在这上面。同时在做一个简单的 settings 侧边栏文件，这对我比较东西时追踪一些测试很有用。

---

## #200 **jo** (@hanatos) · 2025-03-08 17:02

看我的代码，我想 python 应该是这样的

```
def density_dir_model_hanatos(raw, e, dc, M):
 M = M*0.1 # 缩减抑制矩阵以大致匹配模型
 e = np.vstack((e,e,e)) # 对数曝光

 # 计算成色剂：
 c = np.einsum('ck, cm->mk', raw, M)
 # 将成色剂应用于原始曝光：
 raw = raw - c;
 # 现在应用我们的假 D_0(.)，假设是单色的（所以我们使其为单色并应用 3 次）
 e_corr = np.zeros_like(raw)
 e_corr[0,:] = np.einsum('ck, cm->mk', np.vstack((raw[0,:],raw[0,:],raw[0,:])), np.linalg.inv(np.eye(3)-M))[0,:]
 e_corr[1,:] = np.einsum('ck, cm->mk', np.vstack((raw[1,:],raw[1,:],raw[1,:])), np.linalg.inv(np.eye(3)-M))[1,:]
 e_corr[2,:] = np.einsum('ck, cm->mk', np.vstack((raw[2,:],raw[2,:],raw[2,:])), np.linalg.inv(np.eye(3)-M))[2,:]
 # 现在我们唯一调用 D lut 的地方：
 d = interp_with_curves(e_corr, e, dc)
 return d

```

并不比你的图好多少：

[[![20250308_17h58m10s_grim](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/f/bfb6d0d09528db86b23ce777d4a5069526692cab_2_690x303.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/f/bfb6d0d09528db86b23ce777d4a5069526692cab_2_690x303.png)

20250308_17h58m10s_grim2419×1065 190 KB](/uploads/short-url/rlYSpGt6DG8lOFHm59KASdCd2wb.png?dl=1)

想法是我只需要调用密度 lut *一次*，其余部分可以解析处理。另外，困扰我的是我们无法将测量到的密度曲线逆向为成色剂之前在胶片中实际发生的"真实"曲线。我尝试运行了一些不动点迭代作为离线预处理，但结果看起来很糟糕。我可能有 bug，因为我的 python 水平很差，但也可能这种方法根本行不通。结果匹配了你之前描述的不受控制的色偏——当没有将密度曲线作为数据处理时。

---

## #201 **Jonathan Bieler** (@jonathanBieler) · 2025-03-08 17:33

我上传了用胶片和数码拍摄的同一张照片用于测试：[树与溪流：数码与胶片](https://discuss.pixls.us/t/tree-above-stream-digital-film/48707)

我试图比较用 agx-emulsion 转换的数码与胶片，但很难接近，尽管我可能搞错了什么。

---

## #202 **nosle** (@nosle) · 2025-03-08 20:50

> **@nosle** (帖子 #138):
> 有人知道不同的 NC portra 和较新的无后缀版本有多大差别吗？

自问自答。快速搜索了一下，一些人似乎认为无后缀的 portra 在某种程度上介于旧的 NC 和 VC portra 之间。具体来说，160 最像 160 NC，400 偏向 VC，800 最像 VC。

我最初提问的原因是，我发现 agx 模拟产生了比我的胶片样本更鲜艳、"失真"的图像。有了关于新 portra 的这些信息，这就说得通了，因为 400 应该比 NC 更鲜艳、对比度更高。

最近我只拍了 160 portra，它接近我记忆中 160 NC 的样子。

所以我们现在需要 160 的模拟来获得那些更 earthy、对比度更低的色调。我的 agx 模拟看起来相当"尖锐"。

---

## #203 **** (@mikae1) · 2025-03-08 21:42

> **@arctic** (帖子 #199):
> 尤其是这是一个为慢速"处理"优化的 UI，就像平板扫描仪的负片扫描一样。而且它与 agx-emulsion 的慢处理有些契合，因为它需要预览才能使用。

是的，这就是我的想法。额外加分的是让"扫描"在图像处理时垂直增长（[7m19s](https://www.youtube.com/watch?v=MYC1xii3HmM#t=7m19s)）。

[![:wink:](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)

> **@arctic** (帖子 #199):
> 同时在做一个简单的 settings 侧边栏文件，这对我比较东西时追踪一些测试很有用。

那太好了！我不得不靠截图来记录设置。另一种方式是将设置嵌入为 XMP 元数据（像 Adobe 那样）。

> **@jonathanBieler** (帖子 #201):
> 我试图比较用 agx-emulsion 转换的数码与胶片，但很难接近，尽管我可能搞错了什么。

考虑到一张彩色负片离可用图像有多远，如果你将其数字化，有超过一百万种方式去解读一张负片。它本意是用彩色放大机在相纸上打印。这就是 agx-emulsion 试图模拟的过程。

---

## #204 **Andrea** (@arctic) · 2025-03-09 14:03

> **@hanatos** (帖子 #200):
> 20250308_17h58m10s_grim2419×1065 190 KB

好的，这样更有意义，黄色层看起来好多了！

> **@hanatos** (帖子 #200):
> 另外，困扰我的是我们无法将测量到的密度曲线逆向为成色剂之前在胶片中实际发生的"真实"曲线。

其实这也困扰我。

[![:smile:](https://discuss.pixls.us/images/emoji/apple/smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smile.png?v=12)

 在考虑这个建模部分的解决方案时，依赖密度的双重 LUT 插值感觉有点不干净。然而，这给出了最好的结果，并且听起来更扎根于过程的化学性质。

---

## #205 **Andrea** (@arctic) · 2025-03-09 19:58

> **@nosle** (帖子 #202):
> 自问自答。快速搜索了一下，一些人似乎认为无后缀的 portra 在某种程度上介于旧的 NC 和 VC portra 之间。具体来说，160 最像 160 NC，400 偏向 VC，800 最像 VC。

我在 125px 数据库上找到了这份来自 Kodak 的 [文件](https://125px.com/docs/film/kodak/PORTRA_Film_Q&A.pdf)，里面有关于 Portra 的一些问答。

他们说："PORTRA 160NC 和 PORTRA 400NC 胶片与上一代具有相同的对比度和色彩饱和度。新 PORTRA 160VC 和 PORTRA 400VC 胶片的对比度有所降低，色彩饱和度有所提高（通过层间层间效应实现）。"

他们指出，区别基于"层间层间效应"，指的是乳剂中普通彩色成色剂与 DIR 成色剂的比例。

> **@nosle** (帖子 #202):
> 所以我们现在需要 160 的模拟来获得那些更 earthy、对比度更低的色调。我的 agx 模拟看起来相当"尖锐"。

我将来一定会添加 Portra 160 和 800。在当前 Portra 400 模拟中，你可以尝试减少 DIR 成色剂的量（它们的量目前只是猜测，根据你的感知可能太高了，这是很好的反馈，使用 `dir couplers amount`），你也可以通过 `print gamma factor` 降低相纸的 gamma 来调整对比度（也会影响饱和度）。

以下是使用 Kodak Portra 和 Endura Premier 的示例。这是当前的默认输出：

[[![portra_400_endura_premier](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/3/d34c9f1c1136f212c4440b6fffc037a3294b2e61_2_666x1000.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/3/d34c9f1c1136f212c4440b6fffc037a3294b2e61_2_666x1000.jpeg)

portra_400_endura_premier2000×3000 678 KB](/uploads/short-url/u9eUeXKWulTPw45kNbJ9zrdLVGp.jpeg?dl=1)

（左）成色剂减少至 0.7，（右）成色剂减少至 0.5

[[![portra_400_endura_premier_07cpl](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/c/7c2aea3ede3fdee090f4805fee59d9f35edd6068_2_330x480.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/c/7c2aea3ede3fdee090f4805fee59d9f35edd6068_2_330x480.jpeg)

portra_400_endura_premier_07cpl2000×3000 671 KB](/uploads/short-url/hIr9nLWMiQAFKKzCYdXYesVifK8.jpeg?dl=1)

[[![simulation result_05cpl](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/5/6528410ffd14391c20175994736fa5b19cbbd7f7_2_330x480.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/5/6528410ffd14391c20175994736fa5b19cbbd7f7_2_330x480.jpeg)

simulation result_05cpl2000×3000 667 KB](/uploads/short-url/eqSt3qHWlokNi6sMBYGv3OqodbV.jpeg?dl=1)

（左）成色剂 0.5 且 print gamma factor 0.9，（右）成色剂 0.5 且 print gamma factor 0.75

[[![portra_400_endura_premier_05cpl_09gamma](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/7/276bb640876dab22a8db8b22b3e2cfdd046baf3b_2_330x480.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/7/276bb640876dab22a8db8b22b3e2cfdd046baf3b_2_330x480.jpeg)

portra_400_endura_premier_05cpl_09gamma2000×3000 640 KB](/uploads/short-url/5CJomZ6E5iGe1tnUjMlEmXaH6UH.jpeg?dl=1)

[[![portra_400_endura_premier_05cpl_075gamma](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/0/30ad70d3c81c413195b6c49b30e77d4a9c1bfc21_2_330x480.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/0/30ad70d3c81c413195b6c49b30e77d4a9c1bfc21_2_330x480.jpeg)

portra_400_endura_premier_05cpl_075gamma2000×3000 588 KB](/uploads/short-url/6WCvQpCzYYLMUbHp8GYar81kumB.jpeg?dl=1)

这是一个中间的"非尖锐"版本，成色剂 0.7 且 print gamma factor 0.9。

[[![simulation result_07cpl_09gamma](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/c/4c5c1ce7347a0cb19c83468bc4dc656cd921be6c_2_666x1000.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/c/4c5c1ce7347a0cb19c83468bc4dc656cd921be6c_2_666x1000.jpeg)

simulation result_07cpl_09gamma2000×3000 645 KB](/uploads/short-url/aTvDBjfK1kWImd3yTnfwp9aFGu8.jpeg?dl=1)

---

## #206 **nosle** (@nosle) · 2025-03-09 20:06

感谢提供关于那些滑块的更多信息。我会尝试一下！我想我之前测试时对成色剂滑块太保守了。

不过关于那份 Kodak PDF，它似乎是 2006 年的，那是在无后缀调整之前。无后缀的 Portra 160 于 2011 年发布。这份 PDF 虽然关于更早一轮的胶片调校，但仍然很有意思。

---

## #207 **Andrea** (@arctic) · 2025-03-09 20:07

> **@jonathanBieler** (帖子 #201):
> 我试图比较用 agx-emulsion 转换的数码与胶片，但很难接近，尽管我可能搞错了什么。

我完全同意 [@mikae1](/u/mikae1) 的评论，当你数字化负片时，解读它们的方式可以极大地改变输出，需要做出选择。因此，比较和"输出匹配"并非既定的或直接的。

负片旨在尽可能多地捕捉场景，并产生一个需要被解读的中间图像，其本质上是低 gamma（和对比度）的。

---

## #208 **nosle** (@nosle) · 2025-03-09 20:32

> **@jonathanBieler** (帖子 #201):
> 我试图比较用 agx-emulsion 转换的数码与胶片，但很难接近，尽管我可能搞错了什么。

你用了什么流程？你保存了 agx "负片"并在 dt 中与胶片"扫描"一起冲洗吗？

Agx 输出通常内置了打印过程对吗？这意味着纸张的特性也会影响结果。你拍摄的负片无法模拟那部分过程？

---

## #209 **** (@commutergraphics) · 2025-03-09 20:59

这里有一些非常漂亮的例子

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

---

## #210 **** (@mikae1) · 2025-03-10 18:44

> **@arctic** (帖子 #205):
> 你也可以通过 print gamma factor 降低相纸的 gamma 来调整对比度（也会影响饱和度）。

哦，很有帮助！完全忽略了这一点。gamma 为 1 应该是技术资料中的"正确"值吗？说到所有这些设置，有没有办法将设置保存为默认值？我的设置似乎在关闭和重新打开 napari 时消失了。

---

## #211 **Andrea** (@arctic) · 2025-03-11 21:49

> **@mikae1** (帖子 #210):
> gamma 为 1 应该是技术资料中的"正确"值吗？

没错，当 `print gamma factor`=1 时，相纸的密度曲线就是数据表中的曲线。大于或小于 1 的因子会相应地拉伸密度曲线。纸张的有效 gamma 是"原始 gamma x `print gamma factor`"。

> **@mikae1** (帖子 #210):
> 有没有办法将设置保存为默认值？我的设置似乎在关闭和重新打开 napari 时消失了。

不幸的是，默认设置目前硬编码在 gui 文件中（最简单、最快速的实现）。所以目前没有简单的方法保存预设或新的默认值。当然你可以手动修改 python gui 文件，但对于未来的更新来说这不是很好的解决方案。当我在未来实现设置文件的加载时，就可以了。

---

## #212 **** (@mikae1) · 2025-03-11 22:04

> **@arctic** (帖子 #211):
> 没错，当 print gamma factor=1 时，相纸的密度曲线就是数据表中的曲线。

> **@arctic** (帖子 #211):
> 不幸的是，默认设置目前硬编码在 gui 文件中（最简单、最快速的实现）。

谢谢确认！

负片尺寸设置会改变颗粒尺度吗？我一直在想我是多么喜欢 Alien Skin Exposure 处理颗粒缩放的方式。

[[![aseg](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/8/c807354cd2f0df15a6a7f654369bc1b4c36cd164.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/8/c807354cd2f0df15a6a7f654369bc1b4c36cd164.jpeg)

aseg682×578 76.5 KB](/uploads/short-url/sxwW872ktW35KnUYgT7Lxcwr0sQ.jpeg?dl=1)

可以设置胶片格式，颗粒大小会自动正确缩放。我 24 MP 的文件在默认设置下，agx-emulsion 中的默认颗粒大小看起来有点小。我一直在调大。"看起来小"是基于我 15 年前每天扫描负片时的经验。所以，我很可能判断有误。

[![:smiley:](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)

---

## #213 **Andrea** (@arctic) · 2025-03-11 22:14

我探索了让彩色相纸工作的解决方案，发现了一个我之前忽略的小细节。通常放大机和电影印片头中的灯室都有吸热滤镜，可以有效阻挡 NIR 及以上波段的光。这是为了防止过多热量沉积在负片上，这种热量由诸如卤钨灯或碳弧灯等光源产生。

快速搜索后，Schott 的吸热玻璃就是这类滤镜的一个例子。特别是"KG 3"是电影印片头中常见的典型滤镜。

[[![COLOR-FILT-XMIT-9-800w](https://d2x313g9lpht1q.cloudfront.net/original/3X/4/9/499f1adca5895299d6e7cce86a4f825a16013a82.gif)](https://d2x313g9lpht1q.cloudfront.net/original/3X/4/9/499f1adca5895299d6e7cce86a4f825a16013a82.gif)

COLOR-FILT-XMIT-9-800w709×600 30.7 KB](/uploads/short-url/avhJDuSfF7jmpZzkrlUZFWsUR0K.gif?dl=1)

[来自 [Newport](https://www.newport.com/f/heat-absorbing-glass-filters)]

将这一滤镜添加到彩色放大机中，神奇地修复了所有胶片在 Kodak 2393 相纸上打印时的中性 YMC 滤镜匹配问题。

我还使用 Kodak 2393 作为参考打印介质重新优化了 Kodak Vision3 50D，而不是像我对所有其他摄影胶片所做的那样使用 Kodak Portra Endura。

以下是将这些新添加内容加入 `main` 分支后的示例：

darktable 默认编辑：sigmoid（contrast=2），其他所有设置与输入到 agx-emulsion 的图像相同

[[![Signature Edits Free RawsIMG_5824](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/a/6a8b0ffbc29d14a64dd91b8cf9913d5519cebb6d_2_330x480.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/a/6a8b0ffbc29d14a64dd91b8cf9913d5519cebb6d_2_330x480.jpeg)

Signature Edits Free RawsIMG_58241332×1999 529 KB](/uploads/short-url/fcwycY8gJEu5Tx8uP80ckBX3ViR.jpeg?dl=1)

（左）kodak vision3 50d 在 kodak 2393 上，（右）在 kodak supra endura 上

[[![kodak_vision3_50d_kodak_2393_default_09pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/e/1ecb435c29c02b5d77ba9dd887c605c7cbb8f886_2_330x480.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/e/1ecb435c29c02b5d77ba9dd887c605c7cbb8f886_2_330x480.png)

kodak_vision3_50d_kodak_2393_default_09pe1998×3000 9.84 MB](/uploads/short-url/4opOqwbf4uFEXVYu21YqCFLLJ42.png?dl=1)

[[![kodak_vision3_50d_kodak_supra_endura_default_09pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/8/d8563f0c780638ccc25ad9491d73e6a8be2837cb_2_330x480.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/8/d8563f0c780638ccc25ad9491d73e6a8be2837cb_2_330x480.png)

kodak_vision3_50d_kodak_supra_endura_default_09pe1998×3000 9.68 MB](/uploads/short-url/uRNUKUbRHxTbrTi2hVtn2SPR1Jp.png?dl=1)

（左）kodak gold 200 在 kodak 2393 上，（右）在 kodak supra endura 上

[[![kodak_gold_200_kodak_2393_default_09pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/e/7ea4f66247ddaed84091ba7b5209fcc3fd8eecf8_2_330x480.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/e/7ea4f66247ddaed84091ba7b5209fcc3fd8eecf8_2_330x480.png)

kodak_gold_200_kodak_2393_default_09pe1998×3000 10.1 MB](/uploads/short-url/i4lAGn5x5TP2fw5Z14G4WeOeTnq.png?dl=1)

[[![kodak_gold_200_kodak_supra_endura_default_09pe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/f/8ff30c3b17f6c6cfa20bebe18758c30900dd101a_2_330x480.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/f/8ff30c3b17f6c6cfa20bebe18758c30900dd101a_2_330x480.png)

kodak_gold_200_kodak_supra_endura_default_09pe1998×3000 9.96 MB](/uploads/short-url/kxr0m2CJLZdmiiPkIqh0ZlXL64O.png?dl=1)

Kodak Vision3 50D 在 Kodak 2393 上打印具有非常中性的色彩。最接近 darktable 直接编辑的效果。此外，普通摄影胶片，如 Kodak Gold 200，从这些示例来看，在电影打印胶片 Kodak 2393 上打印时看起来也稍微更中性一些。

---

## #214 **Andrea** (@arctic) · 2025-03-11 22:29

> **@mikae1** (帖子 #212):
> 负片尺寸设置会改变颗粒尺度吗？我一直在想我是多么喜欢 Alien Skin Exposure 处理颗粒缩放的方式。

负片尺寸影响颗粒的统计数据。更小的负片会更颗粒感。在极端放大倍数下，它也影响染料云的大小。

我相信在正常放大倍数（正常扫描）下，颗粒的大小主要受扫描/打印设备分辨率的影响。你可以使用 `grain blur` 和 `scan lens blur`（均以像素为单位）来微调。我通常不动 `scan lens blur`。

对于大约 20 MP 的文件，我对 `grain blur` = 0.85-0.95 相当满意。试试看。

这可以自动化，但我发现需要对最终的图像空间"单位"进行精确控制。无论如何，外观的主体是由随机粒子模型完成的，该模型对负片尺寸完全响应。

> **@mikae1** (帖子 #212):
> 15 年前每天扫描负片时

这听起来经验丰富啊

[![:blush:](https://discuss.pixls.us/images/emoji/apple/blush.png?v=12)](https://discuss.pixls.us/images/emoji/apple/blush.png?v=12)

！所以你绝对是最有发言权的！

---

## #215 **Sébastien Guyader** (@sguyader) · 2025-03-11 23:27

对于视频调色，调色师经常使用 Kodak 2383 而不是 2393。显然 [2393 的黑色更深](https://cinematography.com/index.php?/forums/topic/101086-color-density-and-dynamic-range-of-kodak-vision-2383/)，但 [Cullen Kelly](https://www.youtube.com/watch?v=ar-KL3X0Pcw) 等调色大师似乎大多数时候选择 2383。

---

## #216 **Andrea** (@arctic) · 2025-03-11 23:35

谢谢你的评论和链接，我也会数字化 2383 的数据并进行比较。

[![:+1:](https://discuss.pixls.us/images/emoji/apple/+1.png?v=12)](https://discuss.pixls.us/images/emoji/apple/+1.png?v=12)

---

## #217 **Tim Wood** (@streetfighter) · 2025-03-12 04:43

这个软件能产生漂亮的输出，而且整个想法在我看来非常有趣。希望能看到它作为 darktable 的模块！

[@arctic](/u/arctic) 你有没有考虑过将逻辑作为 darktable 的模块来实现，而不是将其打包为独立的工具？

---

## #218 **** (@mikae1) · 2025-03-12 04:49

> **@streetfighter** (帖子 #217):
> @arctic 你有没有考虑过将逻辑作为 darktable 的模块来实现，而不是将其打包为独立的工具？

它是用 Python 写的，而 darktable 是用 C 写的，所以没那么容易。[@hanatos](/u/hanatos) 已将其移植到 GLSL 用于 vkdt。在 [这个](https://discuss.pixls.us/t/spectral-film-simulations-from-scratch/48209/196) 帖子中，我问了一些 darktable 开发者移植到 darktable 有多难，但还没有看到回复。

> **@streetfighter** (帖子 #217):
> 这个软件能产生漂亮的输出

我完全同意！我现在已经用了很多次，基本功能开始变得更直观了。不过还没有深入研究所有选项。

[![:smile:](https://discuss.pixls.us/images/emoji/apple/smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smile.png?v=12)

---

## #219 **jo** (@hanatos) · 2025-03-12 08:36

> **@mikae1** (帖子 #218):
> @hanatos 已将其移植到 GLSL 用于 vkdt。

我想我快达到功能完备了。[这里是模块文档草稿](https://jo.dreggn.org/vkdt/src/pipe/modules/filmsim/readme.html)，包含来自 [@arctic](/u/arctic) 原帖的一些解释。目前还没有光晕效果，但有成色剂，最多可以放大 4 倍（如果你的 GPU 支持的话）。我可能会继续做性能改进/更好的光谱整合/也许尝试稍微更好或更快的颗粒和成色剂实现。

> **@mikae1** (帖子 #218):
> 移植到 darktable 有多难

我退出这个领域了，但我觉得会很繁琐。你可能需要做 2 次（cpu 和 opencl），根据某些其他模块及其在 vkdt 中的对应版本判断，可能会慢 10 倍到 100 倍。还有裁剪 roi/多流水线处理和 gtk gui 的问题，这将是额外的工作量。vkdt 有 DAG，不是线性流水线，所以我很容易路由所需的 lut 纹理。不知道 dt 现在是怎么做的。

---

## #220 **** (@g-man) · 2025-03-12 13:22

> **@streetfighter** (帖子 #217):
> @arctic 你有没有考虑过将逻辑作为 darktable 的模块来实现，而不是将其打包为独立的工具？

我认为这个工具是一个概念验证和快速开发的产物。Andrea 在他的原帖中强调了这一点。一旦过程确定下来，就可以看到它基于当前许可证（GPL3）被复制到其他软件中。

目前，我们等待这项出色的工作。

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

---

## #221 **Andrea** (@arctic) · 2025-03-13 00:21

> **@streetfighter** (帖子 #217):
> @arctic 你有没有考虑过将逻辑作为 darktable 的模块来实现，而不是将其打包为独立的工具？

我同意 [@hanatos](/u/hanatos)、[@mikae1](/u/mikae1) 和 [@g-man](/u/g-man) 的回答！

把这个 python 项目视为一个技术演示。输出还不错，有潜力，但我仍在探索和完善。例如，自一个月前以来，得益于从本论坛开始的反馈和贡献，它已经改进很多！我对此非常高兴！

> **@sguyader** (帖子 #215):
> 对于视频调色，调色师经常使用 Kodak 2383 而不是 2393。

我数字化了 Kodak 2383 数据表中的曲线图（还没提交，我想检查一些其他东西）。

它看起来比 2393 更鲜艳、更色彩丰富。总的来说，我发现 2383 数据产生的输出更具吸引力。如果我们相信模拟预测的结果足够接近现实生活，我就理解为什么它被偏好。不过 2383 数据的模拟看起来不够中性。

（左）kodak vision3 50d 和 2383，（右）2393

[[![desert_kodak_vision3_50d_kodak_2383_default](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/b/5b38a2d1d348fd3485e6da1047d53a780ab64e5b_2_330x220.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/b/5b38a2d1d348fd3485e6da1047d53a780ab64e5b_2_330x220.jpeg)

desert_kodak_vision3_50d_kodak_2383_default3000×2000 742 KB](/uploads/short-url/d0YN66IcIJ5OE0TBIsoXz5E6UHx.jpeg?dl=1)

[[![desert_kodak_vision3_50d_kodak_2393_default](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/e/be76870476005bdc3546cab0c213fe55c02d1a21_2_330x220.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/e/be76870476005bdc3546cab0c213fe55c02d1a21_2_330x220.jpeg)

desert_kodak_vision3_50d_kodak_2393_default3000×2000 691 KB](/uploads/short-url/raUF7jGRp4qR0RgA7FuNwqmuEIF.jpeg?dl=1)

（左）kodak vision3 50d 和 2383，（右）2393

[[![kodak_vision3_50d_kodak_2383_default](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/4/0433e82ed8866167429a98e4820ab2c0aef8e39c_2_330x480.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/4/0433e82ed8866167429a98e4820ab2c0aef8e39c_2_330x480.jpeg)

kodak_vision3_50d_kodak_2383_default1998×3000 615 KB](/uploads/short-url/Bb7rr8f2YnJww5SidyzTT9Nq7q.jpeg?dl=1)

[[![kodak_vision3_50d_kodak_2393_default](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/f/1ffe53156a2149fa2ca6a9ca904ecd9abddb0a44_2_330x480.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/f/1ffe53156a2149fa2ca6a9ca904ecd9abddb0a44_2_330x480.jpeg)

kodak_vision3_50d_kodak_2393_default1998×3000 589 KB](/uploads/short-url/4z1GK5D5tAjGRUbPW23govHsW1K.jpeg?dl=1)

（左）kodak vision3 50d 和 2383，（右）2393

[[![sunset_crop_girl_kodak_vision3_50d_kodak_2383_default](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/5/154d0eea2030c2ede6d25c418af429db780f79aa_2_330x480.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/5/154d0eea2030c2ede6d25c418af429db780f79aa_2_330x480.jpeg)

sunset_crop_girl_kodak_vision3_50d_kodak_2383_default2000×3000 534 KB](/uploads/short-url/32r7Evd431YuTv8eW3JQ6Sm9gn0.jpeg?dl=1)

[[![sunset_crop_girl_kodak_vision3_50d_kodak_2393_default](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/c/5ca19c8e4051920046f2f699dab98d83e6ca7202_2_330x480.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/c/5ca19c8e4051920046f2f699dab98d83e6ca7202_2_330x480.jpeg)

sunset_crop_girl_kodak_vision3_50d_kodak_2393_default2000×3000 504 KB](/uploads/short-url/ddsb3QG70qlhih9nnD7aJVKxNSO.jpeg?dl=1)

其他所有设置都是当前 `main` 分支的默认值。只需加载图像并计算输出。

> **@hanatos** (帖子 #219):
> 我想我快达到功能完备了。这里是模块文档草稿，包含来自 @arctic 原帖的一些解释。

那是对原帖的一个很好的精炼总结。干得好！

我在想这些参数：

- `filter m` 曝光相纸时，调入这么多品红滤镜
- `filter y` 曝光相纸时，调入这么多黄滤镜
- `tune m` 微调品红滤镜。可以视为红/绿色调
- `tune y` 微调黄滤镜。可以视为暖/冷白平衡色温

`filter m` 和 `filter y` 是中性拟合的滤镜值吗？

---

## #222 **Cameron Rad** (@cameronrad) · 2025-03-13 03:20

这里是一些应用了 2383 和 2393 3D LUT 的图像。这是来自 Koji 的 LUT。

2383 左 / 2393 右

<div class="lightbox-wrapper">[[![2383](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/f/ff930131b5b0726ddd6590368b8bbb12fe0678ac_2_690x524.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/f/ff930131b5b0726ddd6590368b8bbb12fe0678ac_2_690x524.jpeg)

23834096×3112 12.1 MB](/uploads/short-url/AsUI56GrsksQRDjMAsqWRmUkw7q.jpeg?dl=1)

[[![2393](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/f/9fa8ae7d15d1c409722e4ee9d76ff60f2e12eba9_2_690x524.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/f/9fa8ae7d15d1c409722e4ee9d76ff60f2e12eba9_2_690x524.jpeg)

23934096×3112 12.2 MB](/uploads/short-url/mMpjCrWuhwtMClU5UeNLVRUEYKR.jpeg?dl=1)

</div>

<div class="lightbox-wrapper">[[![5219_2383](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/8/5856ccfa467972c52222cb6bb4dc245b019b76de_2_690x525.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/8/5856ccfa467972c52222cb6bb4dc245b019b76de_2_690x525.jpeg)

5219_23834152×3164 19.2 MB](/uploads/short-url/cBtZc8wUeioLQGRuQlkG5NN3dLM.jpeg?dl=1)

[[![5219_2393](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/9/89468ceed346ee8ac2347db6988098241e1e2765_2_690x525.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/9/89468ceed346ee8ac2347db6988098241e1e2765_2_690x525.jpeg)

5219_23934152×3164 19.8 MB](/uploads/short-url/jAozatAQ5gyo6H1asOUvDnGWeZT.jpeg?dl=1)

</div>

Adobe 也有一些内置的模拟/LUT。这是他们的版本。

2383 左 / 2393 右。

<div class="lightbox-wrapper">[[![2383 Adobe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/e/5ecfc9f557a27824e573a44e9b9a7de9c52733ea_2_690x524.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/e/5ecfc9f557a27824e573a44e9b9a7de9c52733ea_2_690x524.jpeg)

2383 Adobe4096×3112 9.51 MB](/uploads/short-url/dwK4cXnsk6z3skKqWEWlfOz3d2y.jpeg?dl=1)

[[![2393 Adobe](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/8/680ae00961a68b2ca3ff731fee51d9a347e5f746_2_690x524.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/8/680ae00961a68b2ca3ff731fee51d9a347e5f746_2_690x524.jpeg)

2393 Adobe4096×3112 9.62 MB](/uploads/short-url/eQoXjZqTNC8j8XUibHaV8vaPVEa.jpeg?dl=1)

</div>

这里还有三个不同的 2383 LUT 应用于同一测试图像。左：Koji 2383，中：Resolve 2383（D60），右：另一个通常白点约为 D55 的 2383 LUT，但我为本示例做了适配。

<div class="lightbox-wrapper">[[![2383-1](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/f/ff930131b5b0726ddd6590368b8bbb12fe0678ac_2_690x524.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/f/ff930131b5b0726ddd6590368b8bbb12fe0678ac_2_690x524.jpeg)

2383-14096×3112 12.1 MB](/uploads/short-url/AsUI56GrsksQRDjMAsqWRmUkw7q.jpeg?dl=1)

[[![2383-2](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/b/bbcabb71692b64cc8cf72c30547744f7102896fd_2_690x524.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/b/bbcabb71692b64cc8cf72c30547744f7102896fd_2_690x524.jpeg)

2383-24096×3112 12.1 MB](/uploads/short-url/qNhDBbVjZa11BxrvWwpHU9yRM9T.jpeg?dl=1)

[[![2383-3](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/2/82f2c0a40310a11a371fdbca2905c8c3a7c4650b_2_690x524.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/2/82f2c0a40310a11a371fdbca2905c8c3a7c4650b_2_690x524.jpeg)

2383-34096×3112 12.3 MB](/uploads/short-url/iGqai5DuOScvZf3s7TBICJmilVV.jpeg?dl=1)

</div>

以下是不同白点下的 Resolve 2383 LUT。D55、D60、D65。

<div class="lightbox-wrapper">[[![2383-d55](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/e/be6e1460fd9b0a528f26c864a8871e9f166f8f03_2_690x524.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/e/be6e1460fd9b0a528f26c864a8871e9f166f8f03_2_690x524.jpeg)

2383-d554096×3112 12 MB](/uploads/short-url/raCyXrxquUtacZBBwW90A60M2lB.jpeg?dl=1)

[[![2383-d60](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/b/bbcabb71692b64cc8cf72c30547744f7102896fd_2_690x524.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/b/bbcabb71692b64cc8cf72c30547744f7102896fd_2_690x524.jpeg)

2383-d604096×3112 12.1 MB](/uploads/short-url/qNhDBbVjZa11BxrvWwpHU9yRM9T.jpeg?dl=1)

[[![2383-d65](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/c/ac4360eb1483159ab3c09f9948168be3a1ce9851_2_690x524.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/c/ac4360eb1483159ab3c09f9948168be3a1ce9851_2_690x524.jpeg)

2383-d654096×3112 12.2 MB](/uploads/short-url/ozUtWarlajQSK96mGXKJ6xYJHXz.jpeg?dl=1)

</div>

---

## #223 **jo** (@hanatos) · 2025-03-13 07:09

> **@arctic** (帖子 #221):
> filter m 和 filter y 是中性拟合的滤镜值吗？

对，这些直接来自中性拟合器。我希望把它们隐藏在 UI 中/只在某些高级设置中显示，只展示 `tune` 对应的控件。最终的滤镜权重就是 `filter m + tune m * 0.1`，并限制在 <span class="math">[0,1]</span> 范围内。

---

## #224 **Sébastien Guyader** (@sguyader) · 2025-03-13 12:20

> **@arctic** (帖子 #221):
> 如果我们相信模拟预测的结果足够接近现实生活，我就理解为什么它被偏好。不过 2383 数据的模拟看起来不够中性。

2383 确实有自己的风格，这就是为什么它被电影制作人和调色师广泛欣赏和使用。我喜欢你用得到的结果！

---

## #225 **Andrea** (@arctic) · 2025-03-14 12:27

谢谢 [@cameronrad](/u/cameronrad)，很好的对比。

这三个来源之间已经存在差异。

我想知道这些 LUT 是如何制作的？你有什么见解吗？

由于相纸（或电影胶片）的外观只有在投影负片后才能实现，我想知道他们如何能仅提取最终打印介质的 LUT。我猜需要对输入做出很强的假设。或者可能默认假设了"Vision3 输入"。

在你的对比中，2383 看起来更温暖、更有风格化，无论是来自 Koji 还是 Adobe。这是一个好迹象，与我们从 `agx-emulsion` 和技术文档数据中得到的结果一致。

当你说 LUT 针对某个白点进行了优化时，你的意思是中性灰色输入会根据白点在输出时产生不同的色调吗？

---

## #226 **jo** (@hanatos) · 2025-03-14 17:54

现在 vkdt 中已经实现了大部分 agx-emulsion 流水线，我正在更仔细地逐一检查，找出差异，并弄清楚哪些是问题，哪些只是不同……

我仍然不确定我的噪声模型是否与你的可比，正在对一个合成渐变做更多测试（值得指出的是，这通过一个虚拟 ND 滤镜运行，该滤镜不是线性透射渐变，只在左半部分左右接近）。

我使用程序化噪声模式来计算每个像素中颗粒数的变化。这有点像是泊松部分。然后我使用二项分布来采样这些颗粒是否显影。二项分布在边缘处有一些内置的方差减少，对于 p=0 和 p=1。不确定为什么我在你的图中看不到这个，我相信是因为泊松部分占主导地位？或者也许是因为我对二项分布使用了大 N 高斯近似。

总之，这里有一些结果：波形直方图显示的是原始值，而不是像你上面的颗粒图那样的标准差，但你也可以看到方差如何向极端（白/黑）压缩。增加渐变的曝光：

[[![2025-03-14-152757_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/6/96396c90b536c5cd6751a6479da72f9f473670b4_2_690x457.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/6/96396c90b536c5cd6751a6479da72f9f473670b4_2_690x457.png)

2025-03-14-152757_hyprshot1384×918 235 KB](/uploads/short-url/lqWEmORBpgoVD5ubm5RAUDyjBPu.png?dl=1)

[[![2025-03-14-152811_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/1/91b84a73de673e1f1ac7ade4aba3b53c2895bb75_2_690x457.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/1/91b84a73de673e1f1ac7ade4aba3b53c2895bb75_2_690x457.png)

2025-03-14-152811_hyprshot1384×918 223 KB](/uploads/short-url/kN64Cn4Y6RpHglVKmHLHBaAKPul.png?dl=1)

[[![2025-03-14-152822_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/6/06bb59b4de666fe9ec47e11a6a770796f306abef_2_690x457.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/6/06bb59b4de666fe9ec47e11a6a770796f306abef_2_690x457.png)

2025-03-14-152822_hyprshot1384×918 191 KB](/uploads/short-url/XygccjCgLQ8IML0IVjZPcT4Mph.png?dl=1)

这是使用较低的 `uniform` 参数时的情况，这意味着每个像素中颗粒数的变化更大，呈现出整体更颗粒感的外观。这增加了另一个方差来源，因此波形中的点云爆发了。颗粒的大小没有影响，因为它被测试条的高度积分掉了。

[[![2025-03-14-152844_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/2/0220f3058bc38c31377a91ed7083eceef1c9aa59_2_690x457.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/2/0220f3058bc38c31377a91ed7083eceef1c9aa59_2_690x457.png)

2025-03-14-152844_hyprshot1384×918 348 KB](/uploads/short-url/iPy0qnQxWkd7Zcq19bom7j0z8d.png?dl=1)

这是负片，非常欠曝（-5ev）以拉伸范围，在测试条右端的深色区域（将变成黑色）显示出一些量化伪影：

[[![2025-03-14-154551_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/3/43936912cb924c7be06cc360580641266a62d1d7_2_690x457.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/3/43936912cb924c7be06cc360580641266a62d1d7_2_690x457.png)

2025-03-14-154551_hyprshot1384×918 208 KB](/uploads/short-url/9DNOAsO5VOiYN2L0xTGjtpzkwSj.png?dl=1)

这个是 `uniform=1`，但将其设为零只是整体上增加了方差，除了在黑色区域，它保持与上图相同。

为了完整性，这里是处理图 `.cfg` 文件：

[test.cfg](/uploads/short-url/u3byV9CwQnxDETiJ91It1gKNkn1.cfg) (1.6 KB)

我得多盯着这些条看一会儿，但我认为噪声模型可能属于"不同，但我对它满意"的类别。我可能想调整参数，也许弄个组合框放几个 ISO 速度等级。

---

## #227 **nosle** (@nosle) · 2025-03-14 19:25

简单评论一下，我大约一小时前编译的，Endura Premium 似乎是唯一看起来合理的相纸。不过我不知道我在 vtkd 中做了什么，所以请谨慎看待。用 Endura 的模拟看起来还行。其他相纸非常偏黄。

打开"模拟颗粒"时看到的颗粒看起来真的很奇怪，完全不像 agx app。颗粒对比度很大、有像素感，一点也不像模拟质感。

另外想知道相纸曝光在两个 app 中是否工作方式相同？在 vktd 中感觉不同。

---

## #228 **** (@qosch) · 2025-03-14 23:39

我在 vkdt 中玩了一下，它用起来挺有趣的，但即使花了很多时间，我也无法输出一张看起来不"过火"的图像。

我现在没用颗粒功能，暂时将成色剂设为 0。Tune m 和 tune y 似乎像是白平衡。所以在调整 m 和 y 得到中性色彩后，还有胶片和相纸以及 4 个滑块，其中每 2 个似乎做的是差不多的事情。

关于胶片和相纸，我从 Portra 400 和 Portra Endura 开始的。

你的节点编辑器中的图是什么样的？我现在用这个：

[[![grafik](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/1/b16326ec826c10d6650ec3c8193da5799699c7ab_2_690x190.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/1/b16326ec826c10d6650ec3c8193da5799699c7ab_2_690x190.png)

grafik1972×544 69.4 KB](/uploads/short-url/pjeWyQudplRWzsEOat7BKePQcDV.png?dl=1)

禁用 filmsim 后，图像应该是什么样子？正确白平衡和曝光，我猜？

我也不介意要一个 cfg 文件来比较结果，以确保不是 AMD 专属的 bug

[![:wink:](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)

---

## #229 **jo** (@hanatos) · 2025-03-15 17:54

下一个：我从一开始就看到的奇怪色偏。我打印了所有对数光谱功率和密度等缓冲区，并与对应的 agx 输出进行了比较。它们当然有些分歧，即早期阶段更相似。钨丝灯与 3200K 的放大器和滤镜透过率造成了相当大的差异。

结果发现，初始胶片曝光步骤在我这边校准为比 agx-emulsion 代码亮 1ev。

另外：如果密度是 NaN，这意味着无限密度，而不是零

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 这带来了相当大的变化。总之，我就不拿调试输出来烦你了，也许看一个示例，测试图像的负片：

[[![vkdt-scan-negative](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/5/5511121814504dcf08926056d74cd6749c8be0b2.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/5/5511121814504dcf08926056d74cd6749c8be0b2.jpeg)

vkdt-scan-negative512×256 14 KB](/uploads/short-url/c8x9QeRrIvw8UyU27bHjUAZ8Fiy.jpeg?dl=1)

[[![agx-scan-negative](https://d2x313g9lpht1q.cloudfront.net/original/3X/8/6/864721baf574db4cac04ceeec74bc2479abdf026.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/8/6/864721baf574db4cac04ceeec74bc2479abdf026.png)

agx-scan-negative512×256 27.5 KB](/uploads/short-url/j9SnzdRsXDOuoeknwNRRVLzU778.png?dl=1)

以及最终渲染，agx-emulsion 中使用默认设置并禁用所有花哨功能，以及对应的 vkdt 渲染：

<div class="lightbox-wrapper">[[![agx-img](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/b/bb87f248ba56c8ad92c16bd8560fb8c167d692c9_2_332x500.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/b/bb87f248ba56c8ad92c16bd8560fb8c167d692c9_2_332x500.jpeg)

agx-img3733×5610 2.64 MB](/uploads/short-url/qKYy9qFKeXZiwvAsBNaUqRAjggx.jpeg?dl=1)

[[![vkdt-img](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/4/5406c7e553c1f18b0ea9f212717e7016f52f3fe2_2_332x500.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/4/5406c7e553c1f18b0ea9f212717e7016f52f3fe2_2_332x500.jpeg)

vkdt-img3735×5610 5.64 MB](/uploads/short-url/bZkDovfddp8ZHRxCIvx36mQ5glQ.jpeg?dl=1)

</div>

两者都使用大约 -0.5 ev 的相纸曝光，没有自动曝光。我不得不在 vkdt 中稍微调整 m 和 y 滤镜，但也不算太多（不是追求最佳匹配，只是从远处目测了几秒钟，从背景就能看出来）。现在重新拟合所有中性值，我想我终于可以把 `filter c` 保持恒定，并为另外两个获得有效值了。这是朝着等效输出的重要一步。只有完全正确时，科学才是魔法……

---

## #230 **Andrea** (@arctic) · 2025-03-17 16:03

仅从波形判断，颗粒似乎表现相当好，并且对一致性的响应也符合我的预期。

> **@hanatos** (帖子 #226):
> 我使用程序化噪声模式来计算每个像素中颗粒数的变化。这有点像是泊松部分。然后我使用二项分布来采样这些颗粒是否显影。二项分布在边缘处有一些内置的方差减少，对于 p=0 和 p=1。不确定为什么我在你的图中看不到这个，我相信是因为泊松部分占主导地位？或者也许是因为我对二项分布使用了大 N 高斯近似。

在密度值的极端情况下，我使用 `density_min`（即灰雾）在密度（超过基底 + 灰雾）接近零时提升方差，并且如你所说，我减少 `uniformity` 以在接近最大密度时增加方差。我回忆起下面的图作为参考。在那个简化脚本中，我省略了 `density_min`，但它会提升图的左侧部分。

这就是你提到的吗？

> **@arctic** (帖子 #130):
> image584×432 50.3 KB

作为评论，当在相纸上打印时，灰雾或一致性的效果可能不太明显。大多数时候我们只打印负片的"线性部分"。所以 p=0 或 p=1 的行为主要与模拟欠曝或过曝相关。

> **@hanatos** (帖子 #226):
> 我可能想调整参数，也许弄个组合框放几个 ISO 速度等级。

当与真实的 ISO 速度等级和 RMS 颗粒度比较时，我通常会计算一个带有渐变的测试图像（像你那样），像素大小等于测量中使用的密度计孔径面积（圆形，直径 48um）。标准偏差乘以 1000 应该调整到接近测量值，对于不同的像素大小，我们相信粒子模型能很好地缩放。彩色胶片 RMS 颗粒度的通常范围是 5-30，取决于 ISO。

## #231 **Andrea** (@arctic) · 2025-03-17 16:19

> **@hanatos** (帖子 #229):
> 事实证明，在我的设置中，初始胶片曝光步骤的校准比 agx-emulsion 代码中亮 1ev。

这确实会增加一些过曝时出现的色偏，在消费级胶片上更为明显。而 Portra 400 则更为稳定。

> **@hanatos** (帖子 #229):
> 现在重新拟合所有中性值，我想我终于可以将滤镜 c 保持恒定，并为另外两个获得有效值。我认为这是迈向等效输出的重要一步。科学只有在完全正确的情况下才是魔法……

这也是一个非常好的信号！根据实际情况，青色滤镜也应该设为零，但我无法做到这一点，因为品红滤镜需要负值。

肖像照的对比也越来越接近了。在示例中，仍然有一些残留的品红色调，很可能可以通过 m 滤镜进行调整。

我正在尝试调整配置文件生成脚本。有几个部分我打算重新思考关于灵敏度分离的问题。特别是因为我想尝试一下钨丝灯平衡胶片，我认为目前的效果不会很好。

上周末我添加了一些新的胶片数据：

- Ektar 100
- Portra 系列中缺失的型号：160、800、800（增感 1 档）、800（增感 2 档）

我很喜欢 Ektar 100 的配置文件

[![:star_struck:](https://discuss.pixls.us/images/emoji/apple/star_struck.png?v=12)](https://discuss.pixls.us/images/emoji/apple/star_struck.png?v=12)

---

## #232 **jo** (@hanatos) · 2025-03-17 17:42

> **@arctic** (帖子 #231):
> 上周末我添加了一些新的胶片数据：

看到了！我正在处理白平衡的问题。你现在对 2383 和 2392 使用 LED 光源了吗？你是怎么拟合的？目前对我最有效的方法是对整个域进行完全随机的搜索，然后用 nelder mead 进行优化。

---

## #233 **** (@mikae1) · 2025-03-17 20:19

> **@arctic** (帖子 #231):
> 上周末我添加了一些新的胶片数据：

Ektar 100
Portra 系列中缺失的型号：160、800、800（增感 1 档）、800（增感 2 档）

我很喜欢 Ektar 100 的配置文件

酷！我刚下载了 [https://github.com/andreavolpato/agx-emulsion/archive/refs/heads/main.zip](https://github.com/andreavolpato/agx-emulsion/archive/refs/heads/main.zip)，但我看到的唯一新胶片是 kodak_vision3_50d。kodak_ektar_100 并不在其中。

根据 [https://github.com/andreavolpato/agx-emulsion/commit/fa5956c9aae8821a23602851452d652b7e32f0e6](https://github.com/andreavolpato/agx-emulsion/commit/fa5956c9aae8821a23602851452d652b7e32f0e6) 来看，它应该在那里。奇怪？

---

## #234 **Andrea** (@arctic) · 2025-03-17 22:50

对于电影彩色印片胶片，我使用了同样的 3200K（钨丝卤素灯）。数据看起来有些奇怪，尤其是 2393，还需要进一步思考。目前尚不清楚测量密度曲线和灵敏度时的实验条件是什么，以及我应该如何考虑这些因素，以更好地平衡配置文件，使其与虚拟放大机更加兼容。

对于我添加的所有胶片型号，都在放大机中加入了热滤镜（Schott KG3），再加上真实镜头的透射特性，以模拟放大机镜头。显然，使用普通玻璃的镜头会从大约 400-380 nm 处开始截止紫外线。

最后，总滤镜看起来与虚拟相机中使用的非常相似。所以我可能会用一个通用滤镜来代替它，而不依赖实际的实验数据。

[[![heat_filter_lens_transmittance](https://d2x313g9lpht1q.cloudfront.net/original/3X/1/5/15c292eab55e44bcd866bdc1d6cf6dd26c061d4c.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/1/5/15c292eab55e44bcd866bdc1d6cf6dd26c061d4c.png)

heat_filter_lens_transmittance640×480 29.2 KB](/uploads/short-url/36uTLLRqx1hO3K77IDxMpS7VrMo.png?dl=1)

我还更换了放大机的二向色滤镜。我找到了一份远程 PDF，其中包含 Durst 放大机真实二向色滤镜的测量数据（[http://www.jollinger.com/photo/cam-coll/manuals/enlargers/durst/Durst_Enlarger_Guide.pdf](http://www.jollinger.com/photo/cam-coll/manuals/enlargers/durst/Durst_Enlarger_Guide.pdf)）。在我看来，它们针对染料过渡和纸张吸收进行了更好的优化。Thorlabs 和 Edmund Optics 的是通用型，适用于广泛的应用，但它们更"漏光"。

[[![thorlabs](https://d2x313g9lpht1q.cloudfront.net/original/3X/8/e/8e366dcbabb574b590695436e141b64c7f96ce22.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/8/e/8e366dcbabb574b590695436e141b64c7f96ce22.png)

thorlabs640×219 21.7 KB](/uploads/short-url/ki4pG25gxegqci4DMrNY7HEBQeS.png?dl=1)

[[![edmund_optics](https://d2x313g9lpht1q.cloudfront.net/original/3X/e/4/e4443572e2b326320234e32b88aa5175968f7086.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/e/4/e4443572e2b326320234e32b88aa5175968f7086.png)

edmund_optics640×219 21.7 KB](/uploads/short-url/wzkZZEeQPfNhU3flxoQkFmxlw8K.png?dl=1)

[[![durst_digital_light](https://d2x313g9lpht1q.cloudfront.net/original/3X/e/4/e4e7a44c814b779ef150e483089c3ad724e09112.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/e/4/e4e7a44c814b779ef150e483089c3ad724e09112.png)

durst_digital_light640×219 21.9 KB](/uploads/short-url/wEZ9w6BINAVceajkCn95d6EXhlg.png?dl=1)

---

## #235 **Andrea** (@arctic) · 2025-03-17 23:02

> **@mikae1** (帖子 #233):
> 奇怪？

这确实很奇怪。我下载 `main.zip` 文件时能看到这些数据。

我又做了一次小提交，也许你可以再试一次。

我还看到 [@Y69](/u/y69) 用 Ektar 100 拍了一张非常不错的 raw 照片。

---

## #236 **jo** (@hanatos) · 2025-03-18 07:40

> **@nosle** (帖子 #227):
> 只是快速评论一下，我大约一小时前编译的，Endura premium 似乎是唯一看起来正常的相纸。现在我不知道我在用 vtkd 做什么

> **@qosch** (帖子 #228):
> 我在 vkdt 里玩了一下，真的很有趣，但即使花了大量时间，我也无法得到一张看起来不"夸张"的图像。

我不想在这里 hijack arctic 的帖子，这里正在讨论新的胶片型号和光谱模型……也许可以开一个新帖子专门讨论 mondane vkdt 的 bug？我推送了一些修复和新胶片（portra 系列 + ektar），期间破坏了旧的配置文件，所以有些事情可能已经修复了。为了让颗粒看起来非常好，我想我需要更详细地研究一些特性。

> **@arctic** (帖子 #234):
> 对于我添加的所有胶片型号，都在放大机中加入了热滤镜（Schott KG3），再加上真实镜头的透射特性，以模拟放大机镜头。显然，使用普通玻璃的镜头会从大约 400-380 nm 处开始截止紫外线。

哈哈，真不错。我认为这个"包络"函数的形状看起来很像我自己手动调出来的：从 380 到 400 nm 快速上升，然后向 800 nm 缓慢衰减。不过滤镜应用的位置可能有所不同。我把它放在管线的起始处，假设波长之间直到最后才会交换能量（参见我对荧光的评论），但这是不正确的。密度的形成方式完全允许波长之间的一些串扰，所以在曝光阶段应用滤镜可能很重要。

> **@arctic** (帖子 #234):
> 我还更换了放大机的二向色滤镜。我找到了一份远程 PDF，其中包含 Durst 放大机真实二向色滤镜的测量数据

……而这一个更像我的平滑近似，它在过渡时将滤镜总和设为 1！这样拟合起来更容易/更稳健，而且我有点自豪现在可以通过类似 thorlabs 的滤镜收敛所有胶片/相纸组合。我也应该尝试一下类似 durst 的滤镜。

---

## #237 **** (@mikae1) · 2025-03-18 10:01

> **@arctic** (帖子 #235):
> 这确实很奇怪。我下载 main.zip 文件时能看到这些数据。
> 我又做了一次小提交，也许你可以再试一次。
> 我还看到 @Y69 用 Ektar 100 拍了一张非常不错的 raw 照片。

删除了旧的 agx-emulsion 目录并重新下载了 master。之后我运行了：

```
uv run --python 3.11 --with-requirements requirements.txt --no-project --with-editable .
uv run --python 3.11 --with-requirements requirements.txt --no-project --with-editable . agx_emulsion/gui/main.py

```

还是不行。我现在有的：

- kodak_portra_400
- kodak_ultramax_400
- kodak_gold_200
- kodak_vision3_50d
- fujifilm_pro_400h
- fujifilm_xtra_400
- fujifilm_c200

[![:woozy_face:](https://discuss.pixls.us/images/emoji/apple/woozy_face.png?v=12)](https://discuss.pixls.us/images/emoji/apple/woozy_face.png?v=12)

 我先等等看后续代码更新能否解决这个问题。

---

## #238 **Benjamin** (@piratenpanda) · 2025-03-18 10:14

有人在 mesa 25 和 AMD 硬件上运行这个吗？我用 arch，napari 无法正常显示。其他东西比如 glxgears 等都工作正常，所以我很困惑可能漏掉了什么。错误信息如下：

<pre data-code-wrap="python"><code class="lang-python">WARNING: qglx_findConfig: Failed to finding matching FBConfig for QSurfaceFormat(version 2.0, options QFlags<QSurfaceFormat::FormatOption>(), depthBufferSize 0, redBufferSize 1, greenBufferSize 1, blueBufferSize 1, alphaBufferSize 0, stencilBufferSize 0, samples 0, swapBehavior QSurfaceFormat::SingleBuffer, swapInterval 1, colorSpace QSurfaceFormat::DefaultColorSpace, profile QSurfaceFormat::NoProfile)
WARNING: qglx_findConfig: Failed to finding matching FBConfig for QSurfaceFormat(version 2.0, options QFlags<QSurfaceFormat::FormatOption>(), depthBufferSize 0, redBufferSize 1, greenBufferSize 1, blueBufferSize 1, alphaBufferSize 0, stencilBufferSize 0, samples 0, swapBehavior QSurfaceFormat::SingleBuffer, swapInterval 1, colorSpace QSurfaceFormat::DefaultColorSpace, profile QSurfaceFormat::NoProfile)
WARNING: Could not initialize GLX
</code></pre>

当使用 "export QT_XCB_GL_INTEGRATION=none" 时，我得到一个黑色窗口，有可点击的菜单等，但什么都看不到。

如有任何提示，将不胜感激。

编辑：在此找到了解决方案：

[https://www.reddit.com/r/NobaraProject/comments/1fb2o4v/after_updating_to_nobara40_anaconda_navigator_not/](https://www.reddit.com/r/NobaraProject/comments/1fb2o4v/after_updating_to_nobara40_anaconda_navigator_not/)

`conda install -c conda-forge libstdcxx-ng` 解决了问题。现在可以开始玩了

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

---

## #239 **** (@mikae1) · 2025-03-18 10:53

> **@hanatos** (帖子 #236):
> 我不想在这里 hijack arctic 的帖子，这里正在讨论新的胶片型号和光谱模型……也许可以开一个新帖子专门讨论 mondane vkdt 的 bug？

我只能代表我自己说，两种讨论在这个帖子里进行，我并不介意。

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

我喜欢关注这个开发过程，即使我只能理解你们讨论的一小部分内容。

[![:smiley:](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)

---

## #240 **Sébastien Guyader** (@sguyader) · 2025-03-18 11:29

> **@mikae1** (帖子 #237):
> 还是不行。我现在有的：

kodak_portra_400
kodak_ultramax_400
kodak_gold_200
kodak_vision3_50d
fujifilm_pro_400h
fujifilm_xtra_400
fujifilm_c200

 我先等等看后续代码更新能否解决这个问题。

我使用 `git` 克隆了仓库，所有最新添加的内容都在这里。

---

## #241 **Y** (@Y69) · 2025-03-18 13:43

我的情况是，我直接拉取了（`git pull origin main`）变更。

当你使用你的链接下载主分支的快照 ZIP 文件时，它包含新的模拟数据。请验证以下路径是否存在：`agx-emulsion-main/agx_emulsion/data/film/negative/kodak_ektar_100/`。

---

## #242 **** (@mikae1) · 2025-03-18 13:52

> **@Y69** (帖子 #241):
> 请验证以下路径是否存在：agx-emulsion-main/agx_emulsion/data/film/negative/kodak_ektar_100/。

正如我之前写的，kodak_ektar_100 在 napari 中显示了。但其他的（比如 kodak_portra_800_push2）没有。似乎它们都在那里，但在 napari 中不显示。

```
agx-emulsion/agx_emulsion/data/film/
├── negative
│ ├── fujifilm_c200
│ │ ├── density_curve_b.csv
│ │ ├── density_curve_g.csv
│ │ ├── density_curve_r.csv
│ │ ├── dye_density_mid.csv
│ │ ├── dye_density_min.csv
│ │ ├── info.txt
│ │ ├── log_sensitivity_b.csv
│ │ ├── log_sensitivity_g.csv
│ │ └── log_sensitivity_r.csv
│ ├── fujifilm_pro_400h
│ │ ├── density_curve_b.csv
│ │ ├── density_curve_g.csv
│ │ ├── density_curve_r.csv
│ │ ├── dye_density_mid.csv
│ │ ├── dye_density_min.csv
│ │ ├── info.txt
│ │ ├── log_sensitivity_b.csv
│ │ ├── log_sensitivity_g.csv
│ │ └── log_sensitivity_r.csv
│ ├── fujifilm_xtra_400
│ │ ├── density_curve_b.csv
│ │ ├── density_curve_g.csv
│ │ ├── density_curve_r.csv
│ │ ├── dye_density_mid.csv
│ │ ├── dye_density_min.csv
│ │ ├── info.txt
│ │ ├── log_sensitivity_b.csv
│ │ ├── log_sensitivity_g.csv
│ │ └── log_sensitivity_r.csv
│ ├── generic_a
│ │ ├── dye_density_c.csv
│ │ ├── dye_density_m.csv
│ │ ├── dye_density_y.csv
│ │ └── info.txt
│ ├── kodak_ektar_100
│ │ ├── density_curve_b.csv
│ │ ├── density_curve_g.csv
│ │ ├── density_curve_r.csv
│ │ ├── dye_density_mid.csv
│ │ ├── dye_density_min.csv
│ │ ├── info.txt
│ │ ├── log_sensitivity_b.csv
│ │ ├── log_sensitivity_g.csv
│ │ └── log_sensitivity_r.csv
│ ├── kodak_gold_200
│ │ ├── density_curve_b_corrected.csv
│ │ ├── density_curve_b.csv
│ │ ├── density_curve_g.csv
│ │ ├── density_curve_r.csv
│ │ ├── dye_density_mid.csv
│ │ ├── dye_density_min.csv
│ │ ├── info.txt
│ │ ├── log_sensitivity_b.csv
│ │ ├── log_sensitivity_g.csv
│ │ └── log_sensitivity_r.csv
│ ├── kodak_portra_160
│ │ ├── density_curve_b.csv
│ │ ├── density_curve_g.csv
│ │ ├── density_curve_r.csv
│ │ ├── dye_density_mid.csv
│ │ ├── dye_density_min.csv
│ │ ├── info.txt
│ │ ├── log_sensitivity_b.csv
│ │ ├── log_sensitivity_g.csv
│ │ └── log_sensitivity_r.csv
│ ├── kodak_portra_400
│ │ ├── density_curve_b.csv
│ │ ├── density_curve_g.csv
│ │ ├── density_curve_r.csv
│ │ ├── dye_density_mid.csv
│ │ ├── dye_density_min.csv
│ │ ├── info.txt
│ │ ├── log_sensitivity_b.csv
│ │ ├── log_sensitivity_g.csv
│ │ └── log_sensitivity_r.csv
│ ├── kodak_portra_800
│ │ ├── density_curve_b.csv
│ │ ├── density_curve_g.csv
│ │ ├── density_curve_r.csv
│ │ ├── dye_density_mid.csv
│ │ ├── dye_density_min.csv
│ │ ├── info.txt
│ │ ├── log_sensitivity_b.csv
│ │ ├── log_sensitivity_g.csv
│ │ └── log_sensitivity_r.csv
│ ├── kodak_portra_800_push1
│ │ ├── density_curve_b.csv
│ │ ├── density_curve_g.csv
│ │ ├── density_curve_r.csv
│ │ └── info.txt
│ ├── kodak_portra_800_push2
│ │ ├── density_curve_b.csv
│ │ ├── density_curve_g.csv
│ │ ├── density_curve_r.csv
│ │ └── info.txt
│ ├── kodak_ultramax_400
│ │ ├── density_curve_b.csv
│ │ ├── density_curve_g.csv
│ │ ├── density_curve_r.csv
│ │ ├── dye_density_mid.csv
│ │ ├── dye_density_min.csv
│ │ ├── info.txt
│ │ ├── log_sensitivity_b.csv
│ │ ├── log_sensitivity_g.csv
│ │ └── log_sensitivity_r.csv
│ └── kodak_vision3_50d
│ ├── density_curve_b.csv
│ ├── density_curve_g.csv
│ ├── density_curve_r.csv
│ ├── dye_density_c.csv
│ ├── dye_density_m.csv
│ ├── dye_density_mid.csv
│ ├── dye_density_min.csv
│ ├── dye_density_y.csv
│ ├── log_sensitivity_b.csv
│ ├── log_sensitivity_g.csv
│ └── log_sensitivity_r.csv
└── positive
  └── fujifilm_provia_100f
  ├── density_curve_b.csv
  ├── density_curve_g.csv
  ├── density_curve_r.csv
  ├── dye_density_c.csv
  ├── dye_density_m.csv
  ├── dye_density_y.csv
  ├── log_sensitivity_b.csv
  ├── log_sensitivity_g.csv
  └── log_sensitivity_r.csv

17 directories, 114 files

```

---

## #243 **jo** (@hanatos) · 2025-03-18 15:22

新数据对我来说有效。有趣的是，看到不同胶片在拟合白平衡/滤镜权重下的微妙差异：[https://jo.dreggn.org/filmtab/table.html](https://jo.dreggn.org/filmtab/table.html) 。portra/portra 组合无疑非常出色。我使用了一些自动曝光，所以 Portra 800 的增感版本在整体亮度上看起来相似。当然，需要一些手动微调（包括曝光）才能真正看起来很棒。

<details>
<summary>
生成表格的脚本</summary>

<pre data-code-wrap="bash"><code class="lang-bash">#!/bin/bash

films=(
kodak_ektar_100
kodak_portra_160
kodak_portra_400
kodak_portra_800
kodak_portra_800_push1
kodak_portra_800_push2
kodak_gold_200
kodak_ultramax_400
kodak_vision3_50d
fujifilm_pro_400h
fujifilm_xtra_400
fujifilm_c200
)

papers=(
kodak_endura_premier
kodak_ektacolor_edge
kodak_supra_endura
kodak_portra_endura
fujifilm_crystal_archive_typeii
kodak_2383
kodak_2393
)

n_films=${#films[@]}
n_papers=${#papers[@]}
# ${films[0]}

cat << EOF > table.html
<html>
<body>
<table style="width:100%">
EOF

echo '<tr><th>film/paper</th>' >> table.html
for paper in "${papers[@]}"
do
 echo "<th>$(echo $paper | sed -e 's/_/ /g')</th>" >> table.html
done
echo '</tr>' >> table.html

f=0
for film in "${films[@]}"
do
 p=0
 echo "<tr><td>$(echo $film | sed -e 's/_/ /g')</td>" >> table.html
 for paper in "${papers[@]}"
 do
 echo "<td><img style=\"width:12vw\" src=\"img_${film}_${paper}.jpg\"/></td>" >> table.html
 vkdt cli -d none -g img_0000.exr.cfg \
 --width 256 --height 256 \
 --quality 92 \
 --filename img_${film}_${paper} \
 --output main \
 --config "param:filmsim:01:ev film:1.0" \
 "param:filmsim:01:film:$f" \
 "param:filmsim:01:paper:$p" \
 "param:filmsim:01:filter c:-1.0"
 p=$((p+1))
 done
 echo '</tr>' >> table.html
 f=$((f+1))
done

cat << EOF >> table.html
</table>
</body>
</html>
EOF
</code></pre>

</details>

---

## #244 **Y** (@Y69) · 2025-03-18 15:40

这很奇怪。我在 napari GUI 中可以看到其他的：

[![20250318-163623_snap](https://d2x313g9lpht1q.cloudfront.net/original/3X/3/6/36ad5f02660d7e176a5e90d2d9bc6b6a34a5d31b.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/3/6/36ad5f02660d7e176a5e90d2d9bc6b6a34a5d31b.png)

---

## #245 **Andrea** (@arctic) · 2025-03-18 17:25

我认为这跟 Python 包的安装有关。

如果你使用 `pip install -e .`，"-e" 是必需的，用于创建符号链接，这样对包文件夹所做的每一个更改都可以在已安装的包中使用。你可以尝试卸载并重新安装这个 Python 包。

---

## #246 **Andrea** (@arctic) · 2025-03-18 17:32

我喜欢这个对比表格！！！

[![:star_struck:](https://discuss.pixls.us/images/emoji/apple/star_struck.png?v=12)](https://discuss.pixls.us/images/emoji/apple/star_struck.png?v=12)

 我会尝试用 agx-emulsion 制作类似的东西，这样更容易检查差异，尤其是在更极端的组合中。"电影印片胶片——摄影负片"的组合是实验性的，我认为在实际中从未打算使用。

---

## #247 **Andrea** (@arctic) · 2025-03-18 22:12

按照你的想法 [@hanatos](/u/hanatos)，我做了一个 `agx-emulsion` 当前默认输出的对比表格。

Ektacolor Edge 相纸是一个异常值，可能存在问题，显示出绿色色偏。调整滤镜后，我仍然可以从中获得看起来不错的图像，但在那种情况下，中性输入颜色在相片上不会是中性，而是带有轻微的品红色偏。

总的来说，我认为 `agx-emulsion` 中拟合的中性滤镜并不能始终提供一致的输出，需要手动调整来中和轻微的色偏并找到妥协的平衡。但它们仍然是合理的起点。

[[![collage](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/7/77fe35a0519f090a8bf58e5ac3846d58c9198570_2_455x1000.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/7/77fe35a0519f090a8bf58e5ac3846d58c9198570_2_455x1000.jpeg)

collage2221×4860 746 KB](/uploads/short-url/h7vsxiW5jZ3KaL4kcsTxGZhAfIY.jpeg?dl=1)

<details>
<summary>
Python 脚本</summary>

<pre data-code-wrap="python"><code class="lang-python">from agx_emulsion.model.process import photo_params, photo_process
from agx_emulsion.model.stocks import FilmStocks, PrintPapers
from agx_emulsion.utils.io import load_image_oiio
import numpy as np
import matplotlib.pyplot as plt

image = load_image_oiio('portrait_256.tif')

N = np.size(FilmStocks)
M = np.size(PrintPapers)

photos = np.zeros((N, M, image.shape[0], image.shape[1], 3))
for i, film in enumerate(FilmStocks):
 print(i)
 for j, paper in enumerate(PrintPapers):
 params = photo_params(film.value, paper.value)
 params.negative.grain.active = False
 params.negative.halation.active = False
 params.print_paper.glare.active = False
 params.io.full_image = True
 params.scanner.unsharp_mask = (0,0)
 photos[i,j] = photo_process(image, params)

collage = np.vstack([np.hstack([photos[i,j] for j in range(M)]) for i in range(N)])
fig, ax = plt.subplots(figsize=(10,18))
ax.imshow(collage)
ax.set_yticks(image.shape[0] * np.arange(N) + image.shape[0]//2)
ax.set_yticklabels(film.name for film in FilmStocks)
ax.set_xticks(image.shape[1] * np.arange(M) + image.shape[1]//2)
ax.set_xticklabels([paper.name for paper in PrintPapers], rotation=90)
ax.xaxis.tick_top()

plt.savefig('collage.jpg', bbox_inches='tight', dpi=300)
</code></pre>

</details>

---

## #248 **Cameron Rad** (@cameronrad) · 2025-03-19 04:58

> **@arctic** (帖子 #225):
> 我想知道这些 LUT 是如何制作的？你有什么见解吗？
> 由于印相纸（或电影印片胶片）的效果只有在投射负片后才能实现，我想知道他们如何能分离出仅针对最终印片介质的 LUT。我想必须对输入做出一些严苛的假设。或者可能默认假设是"Vision3 输入"。

我需要翻看我的资料才能找出这些 LUT 具体是如何制作的。我知道其中一个 2383 LUT 标记为 K2254-K2383。所以它是中间片和 2383 的组合效果。这是 2254 的数据表。[Color Digital Intermediate Film 2254](https://kodakcraftprodcontent.z13.web.core.windows.net/content/products-brochures/motion-picture/KODAK-VISION3-2254-technical-information.pdf)

---

## #249 **** (@mikae1) · 2025-03-19 07:42

> **@mikae1** (帖子 #242):
> 似乎它们都在那里，但在 napari 中不显示。

用 git 克隆而不是下载 zip 文件解决了问题。

---

## #250 **Sakari** (@flannelhead) · 2025-03-19 22:01

大家好 [@arctic](/u/arctic) 和其他人，

我非常享受阅读这个帖子——非常感谢你们在这里付出的努力。

这项工作启发了我，让我也开始进行实验。我对 [Blender 的图像形成](https://blenderartists.org/t/feedback-development-filmic-baby-step-to-a-v2/1361663)（巧合的是也被称为 AgX）背后的理念非常熟悉，所以我想看看这些想法如何用于模拟负片胶片 + 印片过程，就像你在这里所做的那样。

目前，这个实验以 [CTL 脚本](https://acescentral.com/knowledge-base-2/ctl/) 的形式存在，用于 ART。它不使用光谱数据，而是在所有阶段基于三刺激值数据，并使用矩阵来考虑光谱灵敏度和染料特性。它实现了整个过程，包括曝光负片、将密度转换为透射率、曝光相纸以及读取反射率。我当然不是第一个有这个想法的人——我相信 Mastodon 上的 barselino 一直在做[非常类似的事情](https://mastodon.social/@barselino/110790980536800634)，在看到你的模拟后，我又回顾了那些帖子。

在负片和相纸曝光阶段，所有三个三刺激值分量都使用相同的曲线，并且这些曲线没有匹配到任何特定的数据集。这可能忽略了一些这些曲线的创意方面，但另一面是，中性轴保持中性是给定的。

每个阶段的混合矩阵都是可控的，这为最终结果提供了一些不错的创意控制。不过，还不能非常直观地将这些与任何熟悉的术语联系起来，所以最好的办法可能是提供预设来大致匹配某些熟悉的胶片+相纸的外观。

事情仍然处于非常初级的阶段，还有很多东西可以尝试，但只是想在这里打个招呼。至少我设法实现了一个 DIR 成色剂的版本，尽管忽略了像素邻域的影响，因为 CTL 脚本根本无法采样相邻像素……

以下是一些目前的结果。参数是快速调整的，这些肯定没有你的那么精致。不过，我认为它们仍然有一些不错的韵味，有点摆脱了某种"数码"感。

[[![20250225_0032](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/d/5d937129c4467a6590578f9c7ab699e124f77df1_2_690x459.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/d/5d937129c4467a6590578f9c7ab699e124f77df1_2_690x459.jpeg)

20250225_00321024×682 123 KB](/uploads/short-url/dlOit1wy9vmKVPgg1PzV7yvaHrr.jpeg?dl=1)

[处理黄色色偏 - @raublekick 的 Play Raw](https://discuss.pixls.us/t/dealing-with-yellow-color-shift/48530)

[[![PXL_20210711_223155650](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/4/1451dbf639f67db71014698b16c78d465ccdb10d_2_690x516.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/4/1451dbf639f67db71014698b16c78d465ccdb10d_2_690x516.jpeg)

PXL_20210711_2231556501024×767 246 KB](/uploads/short-url/2TKVMzGdJRTF6QtsG3sfeyPNzBz.jpeg?dl=1)

[实现粉彩色调 - @nish 的 Play Raw](https://discuss.pixls.us/t/achieving-pastel-colors/42031)

[[![5D3_9253](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/d/8da4d765ede65f335dce3f037f7e752f77c89739_2_690x460.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/d/8da4d765ede65f335dce3f037f7e752f77c89739_2_690x460.jpeg)

5D3_92531024×683 133 KB](/uploads/short-url/kd2uEtQeP0o8i8ANvItGSvgZRMd.jpeg?dl=1)

[伙计们，我刚发现了 LED - @ilia3101 的 Play Raw](https://discuss.pixls.us/t/guys-i-just-discovered-leds/28404)

[[![blue_bar_709](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/3/c3c2e426d5c3046ca5f383118fb55a7a6683a38a_2_690x388.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/3/c3c2e426d5c3046ca5f383118fb55a7a6683a38a_2_690x388.jpeg)

blue_bar_7091024×576 174 KB](/uploads/short-url/rVMES8EQtSUH9X1qhGZPVhsFkxA.jpeg?dl=1)

[GitHub - sobotka/Testing_Imagery/blue_bar_709.exr](https://github.com/sobotka/Testing_Imagery/blob/main/blue_bar_709.exr)

[[![Signature Edits Free Raw Files - Tag @signatureeditsco IMG_0913](https://d2x313g9lpht1q.cloudfront.net/original/3X/9/b/9b64d7d86c4bd78e4b8d910de79d4e85333332cb.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/9/b/9b64d7d86c4bd78e4b8d910de79d4e85333332cb.jpeg)

Signature Edits Free Raw Files - Tag @signatureeditsco IMG_0913683×1024 145 KB](/uploads/short-url/maG3Vzldfh6hPy6ZbC7serSVhEv.jpeg?dl=1)

来源：[signatureedits.com](http://signatureedits.com) 免费 raw 文件

附注：如果我能完成这项工作并让它能被其他人使用，我会开一个新帖子。

---

## #251 **Andrea** (@arctic) · 2025-03-20 20:04

嘿 [@flannelhead](/u/flannelhead)，这太酷了！也谢谢你的赞赏评论。

> **@flannelhead** (帖子 #250):
> 不使用光谱数据，而是在所有阶段基于三刺激值数据，并使用矩阵来考虑光谱灵敏度和染料特性。

我认为这是一个非常有趣的话题："我们能在多大程度上简化问题，同时保留最终风格的大部分特征"。看到像你这样用最基本的东西来模拟各个步骤的项目，同时获得控制权并通过更简单的参数驱动模拟，真的很酷。

像 `agx-emulsion` 这样使用完整数据的一个缺点是失去了一些控制，随意改动可能会导致相当不可预测的结果。

我想尝试实验的问题之一是推断"光谱管线到底增加了什么"，以及是否可能将这种效果简化并以某种方式在三刺激值模拟中建模。直觉上，光谱模拟确实增加了一些东西。当负片的密度增加时，透过负片的透射光谱并不仅仅是缩放，而是由于主要吸收峰的饱和而发生的波段偏移。但这些效应对最终外观的影响有多大，这是一个值得探索的有趣问题。

> **@flannelhead** (帖子 #250):
> 只是想在里打个招呼。至少我设法实现了一个 DIR 成色剂的版本，尽管忽略了像素邻域的影响，因为 CTL 脚本根本无法采样相邻像素……

很高兴你成功模拟了 DIR 成色剂的抑制剂。如果你愿意在任何时候分享脚本，我会很有兴趣关注你的实验。我不太了解 CTL 脚本，所以能看到一些不同的东西很酷。

结果确实很有希望！

[![:sunglasses:](https://discuss.pixls.us/images/emoji/apple/sunglasses.png?v=12)](https://discuss.pixls.us/images/emoji/apple/sunglasses.png?v=12)

在我最初实验的时候，我也花了相当长的时间才得到像样的色彩

[![:laughing:](https://discuss.pixls.us/images/emoji/apple/laughing.png?v=12)](https://discuss.pixls.us/images/emoji/apple/laughing.png?v=12)

---

## #252 **Jakob Andrén** (@jandren) · 2025-03-21 14:48

仅使用三刺激值表示就能得到相当不错的结果！有没有添加什么魔法技巧来处理比如色域外的颜色裁剪？

对于矩阵表示，是否可以定义胶片和相纸的基础颜色，然后将其视为两者之间的变换？这样用户可以在全局坐标中定义它们，我们计算相对的变换？

可能从我这里说出来并不令人惊讶，你密度使用了什么曲线？你的帖子启发我去检查旧色调曲线工具中的胶片和相纸密度曲线。以下是 Kodak Portra 400 和 Kodak Endura Premier 的结果：

<div class="lightbox-wrapper">[[![Kodak Portra 400 vs sigmoid](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/4/a41ac0d4221f5ade708d2ff9b66195e0c4e6f600_2_690x366.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/4/a41ac0d4221f5ade708d2ff9b66195e0c4e6f600_2_690x366.png)

Kodak Portra 400 vs sigmoid2555×1356 149 KB](/uploads/short-url/npJCFv16CuhiOtW6x9efY0ECakM.png?dl=1)

[[![Kodak Endura Premier vs sigmoid](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/d/2d69728be098e83bd8ba2ee666e0472a8fa515a2_2_690x418.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/d/2d69728be098e83bd8ba2ee666e0472a8fa515a2_2_690x418.png)

Kodak Endura Premier vs sigmoid2282×1383 145 KB](/uploads/short-url/6tJpbKECX3bkh5clI6XeMWMh0e6.png?dl=1)

[[![Film and paper vs sigmoid](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/d/0dc340917e85f54611d238088aca761b03872139_2_690x370.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/d/0dc340917e85f54611d238088aca761b03872139_2_690x370.png)

Film and paper vs sigmoid2370×1274 139 KB](/uploads/short-url/1XKx372k1ju3kUz4gfxkTaa2VlL.png?dl=1)

</div>

我很高兴看到模拟胶片和相纸的属性可以相当好地独立建模。S 形模块中使用的公式与胶片+相纸的情况很接近，但不幸的是，据我目前所见，并不完全一致。也许可以作为一个非破坏性变更引入，但我需要更仔细地研究这个问题。加上光谱部分，我们将得到一个相当重要的模块升级。

---

## #253 **Sakari** (@flannelhead) · 2025-03-21 21:25

> **@arctic** (帖子 #251):
> 我想尝试实验的问题之一是推断"光谱管线到底增加了什么"，以及是否可能将这种效果简化并以某种方式在三刺激值模拟中建模。直觉上，光谱模拟确实增加了一些东西。当负片的密度增加时，透过负片的透射光谱并不仅仅是缩放，而是由于主要吸收峰的饱和而发生的波段偏移。

是的确实，这非常有趣，很可能需要做出一些取舍，最好是有意识地做出这些取舍。

> **@arctic** (帖子 #251):
> 如果你愿意在任何时候分享脚本，我会很有兴趣关注你的实验。

是的，我一定会分享的！

---

## #254 **Sakari** (@flannelhead) · 2025-03-21 21:47

> **@jandren** (帖子 #252):
> 有没有添加什么魔法技巧来处理比如色域外的颜色裁剪？

目前没有使用魔法技巧。数据以线性 Rec. 709 编码的 RGB（由 ART 提供）输入，负分量被单独裁剪为零。这部分需要更好的处理，因为并非所有通常的困难图像（例如 Troy 测试图像仓库中的 Red Xmas 和 Nightclub）都能像我上面展示的示例那样得到良好处理。

不过，从那时起，事情就得到了很好的控制。最关键的一点是要确保没有一个矩阵包含负元素。试想一下：三刺激值分量中的一个具有更大的透射率，绝不可能导致某些相纸层中的密度降低。

> **@jandren** (帖子 #252):
> 对于矩阵表示，是否可以定义胶片和相纸的基础颜色，然后将其视为两者之间的变换？这样用户可以在全局坐标中定义它们，我们计算相对的变换？

嗯，这是一个有趣的问题。到目前为止，主要控制只是在管线的各个阶段对单独的 RGB 分量进行旋转和偏移。因此，事物会微妙（或不太微妙地）地向一个方向或另一个方向偏移，目前我只是通过目视并根据 Andrea 光谱模拟的结果来调整。我不确定色度坐标方法在这里是否有意义，因为意图是更接近光谱处理。

有几个阶段会发生某种光谱投影。管线如下：

1. 线性 Rec.709 RGB 输入
2. 将负瓣裁剪为零
3. 胶片偏移/旋转矩阵——这对应于胶片的光谱灵敏度
4. 胶片密度曲线
5. (DIR 成色剂)
6. 胶片密度到透射率
7. 相纸偏移/旋转矩阵——这是胶片光谱染料密度和相纸光谱灵敏度之间的关系所在。
8. 相纸密度曲线
9. 相纸密度到反射率
10. 最终旋转矩阵——同时考虑相纸染料反射光谱

至少在阶段 3、7 和 10，各种光谱可以被纳入考虑，并且可以进行创意控制。探索以何种方式最友好地暴露这些参数，肯定会很有趣。

> **@jandren** (帖子 #252):
> 可能从我这里说出来并不令人惊讶，你密度使用了什么曲线？

目前使用的是 [Troy 的仓库](https://github.com/sobotka/SB2383-Configuration-Generation/blob/main/sigmoid.py) 中的曲线。当前的曲线只是非常快速地目视确定的，应该进行改进。

> **@jandren** (帖子 #252):
> 你的帖子启发我去检查旧色调曲线工具中的胶片和相纸密度曲线。以下是 Kodak Portra 400 和 Kodak Endura Premier 的结果

结果不错，似乎总的结果确实很接近了。

> **@jandren** (帖子 #252):
> S 形模块中使用的公式与胶片+相纸的情况很接近，但不幸的是，据我目前所见，并不完全一致。

也许是否精确并不重要，如果一个人可以从一个更简单的模型推导出期望的美学效果。

---

## #255 **jo** (@hanatos) · 2025-03-22 13:11

我有一个关于化学过程的问题。刚刚看了一下硬盘上一些旧胶片扫描。这是什么：

[![img_0000](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/e/ce361ca817dbfbc87e632cc7628f1dc6312a1e91.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/e/ce361ca817dbfbc87e632cc7628f1dc6312a1e91.jpeg)

我目前实现的成色剂是*抑制*的，也就是说负片不会显影太多，也就是图像变得更亮，对吧？那黑色的边缘是什么？这难道也是某种成色剂吗？而且半径非常大。

---

## #256 **Andrea** (@arctic) · 2025-03-22 14:15

> **@hanatos** (帖子 #255):
> 我有一个关于化学过程的问题。刚刚看了一下硬盘上一些旧胶片扫描。这是什么：

有趣。你能提供一下这张图片的背景信息吗？我们看的是什么？比例尺是多少？负片是如何反转的？

我很确定有一些化学/扩散效应是我们没有考虑的。例如，显影剂的浓度可能存在局部效应，在高密度区域会被消耗，在我看来这会起到抑制作用。

DIR 成色剂释放的抑制剂应该在较低密度侧产生低密度边缘，在较高密度侧产生高密度边缘（因为在第二种情况下，它不像在高密度区域中部那样受到抑制，在高密度区域中部，所有方向都提供抑制剂并扩散到其中）。

---

## #257 **jo** (@hanatos) · 2025-03-22 14:33

> **@arctic** (帖子 #256):
> 有趣。你能提供一下这张图片的背景信息吗？我们看的是什么？比例尺是多少？负片是如何反转的？

*咳咳* 是的。我唯一确定知道的是，这张图片是 20 多年前扫描的，我想是 35mm 胶片。

编辑：我们看到：一个人跳进可能是 jerlov 水型 1C 的荧光绿/青/蓝色海洋中。

这些图像是在嗯，某个实验室扫描的？宽 2088 像素。这里的图像在高度上裁剪了，但宽度没有裁剪（但我进行了修复和缩小，因为上面有人物）。我猜这是某种颜色鲜艳的消费级胶片，但我无法告诉你是哪一种。颗粒远低于像素级别，我认为我无法判断像素间的相关性。

这种黑色边缘只出现在这种额外的青色/蓝色水域和边缘。不能肯定地说它必须是亮边或暗边，可能只是不同的层/颜色通道。

> **@arctic** (帖子 #256):
> 在较低密度侧产生低密度边缘

对，这就是我看到的局部对比度增加。这种极端情况会导致边缘较亮的一侧出现白色边缘（在正片中）。

但是，是的，我也对这种大扩散半径感到惊讶。我的成色剂不会扩散*那么*远，而且如果我没理解错的话，你之前表示我们不一定会期望它有太大的空间影响。

哦顺便说一下，我还实现了一个代码路径，它以扫描的模拟胶片负片作为输入，只进行虚拟印片。它勉强能用，但需要手动调整白平衡，而且我发现为了更好地处理结果，需要减去升高的黑点或对负片应用曲线。

---

## #258 **Andrea** (@arctic) · 2025-03-22 14:59

> **@hanatos** (帖子 #257):
> 我们看到：一个人跳进可能是 jerlov 水型 1C 的荧光绿/青/蓝色海洋中。

现在我看到了！谢谢！这效果确实非常大。

一开始我还以为是照片的某个微小的细节。

如果能看看负片就好了。我很好奇实验室是否做了某种自动局部对比度调整。

> **@hanatos** (帖子 #257):
> 哦顺便说一下，我还实现了一个代码路径，它以扫描的模拟胶片负片作为输入，只进行虚拟印片。它勉强能用，但需要手动调整白平衡，而且我发现为了更好地处理结果，需要减去升高的黑点或对负片应用曲线。

这太酷了！我对此有过一些想法，但最近一直没有时间去尝试。你是如何解决将扫描的 RGB 输入转换为染料密度这个问题的？你是绕过这一步直接进行光谱上采样吗？

---

## #259 **jo** (@hanatos) · 2025-03-22 15:26

> **@arctic** (帖子 #258):
> 如果能看看负片就好了。我很好奇实验室是否做了某种自动局部对比度调整。

嗯好问题！我找找看，不确定我还有没有负片。

> **@arctic** (帖子 #258):
> 你是如何解决将扫描的 RGB 输入转换为染料密度这个问题的？你是绕过这一步直接进行光谱上采样吗？

是的没错。我将扫描图像解释为透射率，并对它进行上采样以获得近似的光谱功率。好的一面是，上采样对碰撞系数/密度之类的不起作用，但对于透射率来说是有意义的。

---

## #260 **** (@mikae1) · 2025-03-22 21:30

嘿 [@arctic](/u/arctic)！我确定你发过一张用 agx-emulsion 做的黑白图像。我在你的活动记录里找过了，找不到。是一张女性的照片。是我梦到的吗？

---

## #261 **Andrea** (@arctic) · 2025-03-22 22:37

还没有黑白配置文件

[![:grin:](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)

 但我收集了更多的黑白胶片数据表，我会很快开始为此修改管线。我没有把程序设计得足够抽象，使这些改动变得容易。工作上我还有繁忙的一周，但之后希望能有更多的空闲时间和脑力来尝试新事物！

[![:star_struck:](https://discuss.pixls.us/images/emoji/apple/star_struck.png?v=12)](https://discuss.pixls.us/images/emoji/apple/star_struck.png?v=12)

如果你指的是这个 [拥抱噪点！ - #20 by arctic](https://discuss.pixls.us/t/embrace-the-noise/17248/20)，那是早期对自适应颗粒的一些实验，我从未真正完成或分享。概念上，它与这里的颗粒引擎的一个子层相差不远。那是一个简单的脚本，没有密度曲线，我应该还保留着它。

---

## #262 **** (@mikae1) · 2025-03-23 13:17

> **@arctic** (帖子 #261):
> 如果你指的是这个 拥抱噪点！ - #20 by arctic，那是早期对自适应颗粒的一些实验，我从未真正完成或分享。

啊，我明白了！是的，那就是我想的那个帖子

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

---

## #263 **Nate Weatherly** (@NateWeatherly) · 2025-03-24 17:01

> **@arctic** (帖子 #261):
> 还没有黑白配置文件，但我收集了更多的黑白胶片数据表，我会很快开始为此修改管线。我没有把程序设计得足够抽象，使这些改动变得容易。工作上我还有繁忙的一周，但之后希望能有更多的空闲时间和脑力来尝试新事物！

如果你还没看到的话，这个 Xtol 数据表的德语版本包含大量胶片的 Xtol 曲线，除了 Kodak 之外，还包括 Ilford、Agfa 和 Fuji：[https://125px.com/docs/techpubs/kodak/xtolEntwickler.pdf](https://125px.com/docs/techpubs/kodak/xtolEntwickler.pdf)

---

## #264 **Nate Weatherly** (@NateWeatherly) · 2025-03-24 17:26

> **@hanatos** (帖子 #255):
> 我有一个关于化学过程的问题。刚刚看了一下硬盘上一些旧胶片扫描。这是什么：
> 我目前实现的成色剂是抑制的，也就是说负片不会显影太多，也就是图像变得更亮，对吧？那黑色的边缘是什么？这难道也是某种成色剂吗？而且半径非常大。

可能是放大机/扫描仪镜头散射？或者，取决于扫描仪，是为了增加清晰度或控制动态范围的数码处理（像是 fuji frontier 那种）？

另外，我真的需要知道……这到底是什么鬼东西？？？被啃过的红薯？疙疙瘩瘩的多毛乳头？

[![:sweat_smile:](https://discuss.pixls.us/images/emoji/apple/sweat_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/sweat_smile.png?v=12)

---

## #265 **jo** (@hanatos) · 2025-03-25 08:35

> **@NateWeatherly** (帖子 #264):
> 另外，我真的需要知道……这到底是什么鬼东西？？？

咳咳，既然你坚持：那是船长潜到船底下去割缠在螺旋桨上的绳子，不幸的是，它是塑料做的，熔化成了一个大疙瘩……

---

## #266 **Andrea** (@arctic) · 2025-03-27 01:11

[@hanatos](/u/hanatos)，我想知道你是否有从负片扫描直接转换的图像可以展示。有什么酷的东西分享一下吗？只是很好奇

[![:grinning:](https://discuss.pixls.us/images/emoji/apple/grinning.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grinning.png?v=12)

与此同时，我将完整的 Vision3 系列加入了数据中。

这是更新后的肤色测试表：

[[![collage_2025_03_27](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/f/df7964a83793cba9d7fa96ba040e251bf1ffd723_2_390x1000.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/f/df7964a83793cba9d7fa96ba040e251bf1ffd723_2_390x1000.jpeg)

collage_2025_03_271899×4860 705 KB](/uploads/short-url/vSWyHc53rqwyTY49H3UWMOjLxOb.jpeg?dl=1)

Vision3 系列一致地比专用摄影胶片更中性。

我还在思考配置文件的制作。我想让灵敏度的分离更加严谨。显然，在测量相纸灵敏度的实验中，光源被一个模拟中性曝光胶片的滤镜过滤了。我应该加入这一点，看看是否有改进，特别是对于后来的滤镜中性拟合。

周末进行的另一项小调查是关于 3DLUT 的，它编码了放大机和扫描仪中发生的情况。显然它们非常平滑，所以我把 LUT 的默认尺寸减小到了 17x17x17x3，稍微加快了计算速度。

这是 Kodak Gold 200 和 Kodak Endura Premier 的放大机 3DLUT 示例。曲线的颜色编码了其他通道中输入密度的量（因此不是 x 轴）。

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/6/263adc7f4a510383df5ddec03099889543ac6835_2_690x669.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/6/263adc7f4a510383df5ddec03099889543ac6835_2_690x669.png)

image705×684 72.7 KB](/uploads/short-url/5scfJ681GUzFy6vaw4ySMqbgy7b.png?dl=1)

由于配置文件中添加了遮蔽成色剂，串扰并不多。

有人知道一种很好的可视化/表示这些 3D LUT 的方法吗？我只是在每个维度上绘制了几个切片。

---

## #267 **jo** (@hanatos) · 2025-03-28 10:22

哇真不错！那我需要重建我的胶片 LUT 了！也许在某个时候，预计算的 3D LUT 对我加速计算也会很有用。这可能对实时 raw 视频处理很有意义。

总之，我做了一个短视频处理这个 [playraw](https://discuss.pixls.us/t/tree-above-stream-digital-film/48707/15)：



我首先处理数码 raw → filmsim + 印片，然后处理扫描负片 → 虚拟印片。正如你所见，我需要一些非物理的相纸 gamma 来更好地匹配对比度。而且由于我不知道胶片型号，我不得不花相当多的时间调整滤镜才能达到近似中性的渲染（没有来自拟合器的预计算数据）。

---

## #268 **Jonathan Bieler** (@jonathanBieler) · 2025-03-28 12:25

酷，胶片是 Kodak Gold 200。另外作为参考，我在帖子中加入了直出 jpeg，那是清晨拍摄的，所以光线偏蓝。

---

## #269 **Nate Weatherly** (@NateWeatherly) · 2025-03-28 15:07

啊，是的，我对从螺旋桨上清理绳索太熟悉了，只不过我的情况通常只是拖钓马达，不需要潜水

[![:sweat_smile:](https://discuss.pixls.us/images/emoji/apple/sweat_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/sweat_smile.png?v=12)

---

## #270 **jo** (@hanatos) · 2025-03-28 19:00

> **@jonathanBieler** (帖子 #268):
> 酷，胶片是 Kodak Gold 200。另外作为参考，我在帖子中加入了直出 jpeg，那是清晨拍摄的，所以光线偏蓝。

啊，谢谢，那就有道理了。似乎 Kodak Gold 200 可以解释我看到的一些灰雾/最小密度。不幸的是，校准显然不是绝对的。不知道扫描过程中发生了什么，以及这是否也会影响白点。如果我保持 Kodak Gold 和特定印相纸组合的拟合值，它会变得非常蓝（将青色滤镜设为 0.3，而不是我上面做的 0.7…0.8）。

---

## #271 **Revanza Pratamasyah** (@Revanza_Pratamasyah) · 2025-04-13 07:38

> **@arctic** (帖子 #19):
> python agx_emulsion\gui\main.py

你好，首先非常感谢你为这个项目付出的努力！

但是，我在安装上遇到了困难，你能帮我解决安装问题吗？

[[![Screenshot (70)](https://d2x313g9lpht1q.cloudfront.net/original/3X/9/3/939d4aee25bb75c70dfa933c316e042f3ec165ae.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/9/3/939d4aee25bb75c70dfa933c316e042f3ec165ae.png)

Screenshot (70)1896×1012 33 KB](/uploads/short-url/l3RbxLytra55kfsCJPktq8PlVKu.png?dl=1)

这是我收到的命令。

---

## #272 **Y** (@Y69) · 2025-04-13 09:37

看起来你下载的是二月份的 `0.1.0-alpha` 版本 ZIP 包，对吧？如果是的话，尝试用 `git clone` 这个项目来获取最新的更新。

---

## #274 **Revanza Pratamasyah** (@Revanza_Pratamasyah) · 2025-04-13 10:21

> **@liam_collod** (帖子 #21):
> uv run --python 3.11 --with-requirements requirements.txt --no-project --with-editable . agx_emulsion/gui/main.py

嗨，谢谢你的帮助，我已经用 UV 成功下载了最新包，它自动打开了 GUI。如果我想再次打开 GUI，我应该使用同样的命令下载文件，还是可以直接运行已经下载好的？

谢谢！

---

## #275 **** (@mikae1) · 2025-04-13 10:23

嗨！我想知道在后续版本中 `requirements.txt` 去哪了？我 `git clone` 了仓库，但在里面找不到 `requirements.txt`，并且我收到了 `error: File not found: requirements.txt`。

---

## #276 **Revanza Pratamasyah** (@Revanza_Pratamasyah) · 2025-04-13 11:39

嗨，只需按照 GitHub 上的说明，使用 CMD 通过 UV 方法下载 emulsion。完成后，它会自动打开 GUI 供你编辑照片。*不要忘记先安装 UV

但是，下次你想启动 emulsion 时，你必须通过 CMD 运行 "main.py"，命令是 "uv run main.py"

它位于 "agx_emulsion\gui" 中，但要找到完整下载文件的位置，只需在 agx emulsion 下载过程中或之后查看 CMD 即可。

---

## #277 **Felix Kloss** (@luator) · 2025-04-13 18:28

你现在可以直接使用

<pre data-code-wrap="sh"><code class="lang-sh">uvx --from git+https://github.com/andreavolpato/agx-emulsion.git agx-emulsion
</code></pre>

来运行最新版本（参见 README）。

requirements.txt 已被移除，因为使用 uv 或 pip 时不再需要它。

---

## #278 **Andrea** (@arctic) · 2025-04-14 21:46

依赖项已经嵌入 `setup.py`，会被自动解析。我们也更新了仓库中的安装指南。

[![:wink:](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)

---

## #279 **** (@mikae1) · 2025-04-16 06:06

谢谢！终于注意到指南已经更新了。

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 似乎现在安装自动去 `~/.cache/uv/` 了？

---

## #280 **Felix Kloss** (@luator) · 2025-04-16 11:16

是的，当你使用 uvx 时，它会安装到缓存目录，所以第一次会自动下载，然后使用缓存的版本（除非仓库有更新）。

但如果你更喜欢的话，也可以 pip 安装到一个手动创建的虚拟环境中。

---

## #281 **David Otero Navarro** (@David_Otero_Navarro) · 2025-04-25 09:27

这太棒了！我本来正在考虑做类似的事情来反转我的彩色负片扫描，所以你真是帮我省了一大堆工作

[![:joy:](https://discuss.pixls.us/images/emoji/apple/joy.png?v=12)](https://discuss.pixls.us/images/emoji/apple/joy.png?v=12)

.

---

## #282 **Steven** (@123sg) · 2025-04-30 11:56

嗨，

我一直很忙，几乎没有时间花在这个上面。现在因为健康原因在休息，所以有时间再玩一下了。

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

当尝试在 Windows 上按照 readme 使用 uv 运行时，我遇到了这个错误：

```
(base) PS C:\Users\SG3> uvx --from git+https://github.com/andreavolpato/agx-emulsion.git agx-emulsion
 Updating https://github.com/andreavolpato/agx-emulsion.git (HEAD) x Failed to resolve `--with` requirement
 `-> Git operation failed
(base) PS C:\Users\SG3>

```

我是不是做了什么傻事？关于 failed to resolve --with requirement 的部分（滚动查看）让我很困惑。

我之前通过 pip 和 conda 安装过，但想尝试 uv 的方式。我对包管理器不太懂，可能很明显……

## #283 **Benjamin** (@piratenpanda) · 2025-04-30 13:00

你正在使用哪个 uv 版本？

---

## #284 **Steven** (@123sg) · 2025-04-30 13:13

`uv 0.7.1 (90f46f89a 2025-04-30)`

顺便说一下，在 Powershell 中运行

---

## #285 **Sébastien Guyader** (@sguyader) · 2025-05-05 12:45

我看到你似乎是在 conda 环境中运行 `uv`，你是通过 conda 安装的 `uv` 吗？

---

## #286 **** (@mino) · 2025-05-14 18:24

很棒的项目！我也想试试乳剂模拟，但在安装时遇到了问题。

在 distrobox 内的 fedora 41 上运行，已安装依赖（据我所知）：python、git、gcc

尝试 `uvx --from git+https://github.com/andreavolpato/agx-emulsion.git agx-emulsion` 失败，因为 apparently 无法构建 vispy（[输出](https://pastebin.com/bm9CJ9Md)）

使用 pip 出现类似问题（[输出](https://pastebin.com/e5jphLYe)）

有人能给我一些进一步排查的提示吗？或者告诉我缺少了什么？

---

## #287 **Todd Prior** (@priort) · 2025-05-14 18:45

你可以试试这里步骤 1 和 2 的信息……第三步是 ART 中的特定实现，但前两步可能对你有帮助……

[https://art.pixls.us/AgXEmulsionLutHowto](https://art.pixls.us/AgXEmulsionLutHowto)

---

## #288 **** (@tankist02) · 2025-05-14 21:33

我在 F41 上（真实系统，没有用 distrobox）使用 pip 和 conda 方法都安装成功了。

---

## #289 **** (@evilgenivs) · 2025-05-15 02:28

我真的很不喜欢这个软件。/sarcasm 因为（多年来）我终于在 darktable 中得到了我想要的色调，而同一天我发现了这个……不可思议的胶片模拟，太棒了。我等不及更多更新了！

---

## #290 **** (@mino) · 2025-05-15 13:32

以防有人搜索这个问题。我解决了，原来我缺少 python3-devel 和 PyQt5 作为依赖。要在 Fedora 41 distrobox 中运行，我安装了 `git` `gcc` `python` `uv` `python3-devel` 和 `PyQt5`，然后通过 pip 方式和 `uv` 都成功安装了 agx-emulsion。

这太好玩了。[@arctic](/u/arctic) 的工作令人惊叹且极其迷人！

[![250412_090048_DSC02448-portra160](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/b/8b271977880f0e55ecdaa940b909162e68d15fad_2_665x1000.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/b/8b271977880f0e55ecdaa940b909162e68d15fad_2_665x1000.jpeg)

250412_090048_DSC02448-portra1603472×5219 1.56 MB](/uploads/short-url/jR08AWljQMnWdMdH7E5dpSddlJb.jpeg?dl=1)

---

## #291 **Billal** (@Billal) · 2025-05-25 12:22

当我按照 ART 页面文档中的所有步骤操作时，它显示 LUT 无效。

我成功启动了 Napari，但测试图像似乎无法正常工作。

希望有人能帮忙！

---

## #292 **Billal** (@Billal) · 2025-05-25 12:36

[![Capture](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/e/5ea4ab7274fae91beca8d5c983ac0149ef2256da_2_690x388.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/e/5ea4ab7274fae91beca8d5c983ac0149ef2256da_2_690x388.png)

Capture1364×768 227 KB](/uploads/short-url/dvfGuUiO5kggPCa3PZBQSz24Uwq.png?dl=1)

看看这张图片；当我更改设置时，似乎没有任何效果！

---

## #293 **Billal** (@Billal) · 2025-05-25 15:39

[![Capture &](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/8/c865f5e6aff53b2a5d2c51743194712091b672ac_2_690x375.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/8/c865f5e6aff53b2a5d2c51743194712091b672ac_2_690x375.png)

Capture &1356×737 389 KB](/uploads/short-url/sANWv3zV0bP1GirZiMSGyEYSkUY.png?dl=1)

看看我打开胶片模拟时收到的消息，以及颜色校正选项卡中的相同消息

---

## #294 **Alberto** (@agriggio) · 2025-05-25 16:01

你好，

如果独立应用无法正常工作，说明安装过程中出了问题。在解决这个问题之前，恐怕 ART 这边也无能为力，抱歉。

---

## #295 **** (@mino) · 2025-05-25 19:44

ART 方面我不好说，但在 napari 中，你可能需要在右侧面板中向下滚动并"运行"模拟！

---

## #296 **Steven** (@123sg) · 2025-05-25 20:21

> **@mino** (帖子 #295):
> 向下滚动

没错——在我的 win 11 机器上，我也需要做一些拖放模块重新排列才能看到运行按钮

---

## #297 **Billal** (@Billal) · 2025-05-25 20:30

我试试看，谢谢

---

## #298 **Billal** (@Billal) · 2025-05-25 22:55

[![simulation result1](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/3/f396d308568e5b0b593b064e032766f195b25db6_2_664x1000.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/3/f396d308568e5b0b593b064e032766f195b25db6_2_664x1000.jpeg)

simulation result11993×3000 8.11 MB](/uploads/short-url/yKTaedKObqNbEidKgJoKI8SAuNw.jpeg?dl=1)

我成功处理了一张自己的图片，不得不说，我从未见过有任何软件能如此接近这个效果……简直令人难以置信。唯一的缺点是所需的处理能力以及使用上的难度，除此之外，它令人着迷。

衷心感谢 [@arctic](/u/arctic)。

---

## #299 **Revanza Pratamasyah** (@Revanza_Pratamasyah) · 2025-05-28 03:51

大家好，我想知道是否可以只使用这个软件进行颗粒模拟？我一直在调整设置，但找不到禁用"色彩配置文件"的方法。

---

## #300 **None** (@lanidor) · 2025-05-28 15:48

我偶然发现了这个项目，必须为 [@arctic](/u/arctic) 实现它点赞。过去三年我一直在拍摄胶片，没有哪个插件能如此接近胶片效果（Yedlin 也非常接近，但他的代码不公开，而且需要 Nuke 才能运行）。

我想分享一个小技巧：在 Darktable 中添加一个窄黑框就像胶片边缘一样，应该作为反转时的最暗点。另外，如果将 Napari 的背景设置为白色，评估对比度和白平衡会更容易。

加入 Agfa 胶片会很麻烦吗？我喜欢它们的外观——柔和的色彩搭配浓密的主色调，可惜他们已经停产了（NC500 应该类似，但颗粒太粗了）。

再次感谢！

[AGFA.F-AF-E5.pdf](/uploads/short-url/uNSea7tB0kBvfJPE99CxJUDVkY6.pdf) (163.7 KB)

---

## #301 **John Apolozan** (@JApolozan) · 2025-06-02 02:59

你好 Andrea (arctic)，

首先感谢你创建了这个项目。虽然我的 Python 已经非常生疏了（上次用的时候 Barack Obama 还在任），但我认为你创造了一个极其接近且优雅的真实胶片模拟。我测试过的最接近的结果是 Filmulator。

我将 Fuji 400 (X-Tra) 的数字化图像与同场景用 D810 拍摄的数码照片进行了比较。虽然我不会在这里贴出图片（好朋友的肖像），但我可以说，使用 ART 集成版的 agx-emulsion 并从默认值开始，效果非常接近。为了增加参考，我比较了高级 Noritsu 扫描仪（迷你冲印店）和我的 DSLR 数字化结果。虽然颜色略有不同（专有配置文件和不寻常的分段对比度曲线），但大致效果一致，氛围和感觉都在。

另外，我还将 Portra 400 的亚光纸打印件与模拟结果进行了比较，它们非常接近，当然我没有确切的参考帧，所以只能相信自己的眼睛。

我有 ColorChecker SG 和 Passport 目标板在不同曝光级别下的扫描图，分别在 D50、StdA 和闪光灯照明下拍摄，如果你觉得对某些胶卷有用的话：Portra 400、Fuji 400、Pro Image 100 和 Ektar 100。

再次感谢你在该项目上的工作，期待代码的进一步发展。

此致，

John

---

## #302 **WG** (@BPH3647) · 2025-06-02 18:03

有人有在 MacOS 上验证 Napari 启动版本是否正常运行的小技巧吗？过去几周我已经熟悉了它，从暗房打印的角度来看，它很直观，但我总觉得它没有正确编译。

我下载了一张 [@arctic](/u/arctic) 使用的示例图片，并将其匹配到他的 Darktable 输出，但当我在 Agx 中使用相同的设置时，似乎无法匹配示例输出。

下面是我的一些设置截图和对比。

- 我的 .NEF 转换 vs [@arctic](/u/arctic) 上传的 jpeg
 [![DT_Screen-01](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/5/a59bb3d18d34257c64909af542c2574666297349_2_690x920.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/5/a59bb3d18d34257c64909af542c2574666297349_2_690x920.jpeg)
 DT_Screen-013000×4000 1.17 MB](/uploads/short-url/nD2n9MsTAgapXFZbMWKrgBoNLrH.jpeg?dl=1)
- Agx 中使用的设置 V1 系列 | 详见下方备注
 [![Agx_Screen-01](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/e/7e12e5f0f0f2a4d858730e41327c8d4046180127_2_690x687.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/e/7e12e5f0f0f2a4d858730e41327c8d4046180127_2_690x687.jpeg)
 Agx_Screen-013000×2989 626 KB](/uploads/short-url/hZiEkwkV8ut4SpO69y2LYRbHnzp.jpeg?dl=1)
- 结果 jpeg 与 [@arctic](/u/arctic) 的 jpeg 对比
 [![PS_Screen-01](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/5/05696f1622508fd5bdd8fedcc26f92ca522bd39e_2_604x1000.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/5/05696f1622508fd5bdd8fedcc26f92ca522bd39e_2_604x1000.jpeg)
 PS_Screen-013000×4964 1.07 MB](/uploads/short-url/LShgApygf2Qi82IO5ZgeQ5ByZE.jpeg?dl=1)

至于 darktable 中使用的设置：我翻阅了这个和另一个帖子，试图找到尽可能多的关于初始 Raw 转换导出设置的信息。除了这些之外，我还尝试了许多色彩配置文件的组合。最终得到的结果仍然不匹配。在 photoshop 中处理的 sRGB 文件与从帖子中下载的示例 JPEG 匹配。

Agx 中让我犹豫的设置是"cctf 编/解码"，但无论我怎么勾选/取消勾选组合，都无法更接近。

我完全卡住了！最终结果的对比度和裁切与我预期的相差很大。

直接从 Github 加载应用是否可能是原因？我只有几个小时来尝试弄明白 cuda 方法，但我对此完全不在行，能成功在终端中加载已经算是幸运了。我也想尝试 ART 程序，但同样，我完全不知道如何在 Mac 上安装它。

为这大段文字道歉！

---

## #303 **jo** (@hanatos) · 2025-06-02 18:22

你把 jpg 导入 agx-emulsion 了吗？你把输入色彩空间设置成了 bt2020，但截图看起来实际上是 sRGB。cctf 也不确定（如果输入确实是 sRGB/jpg，你应该勾选这个框，但是吗？）。

---

## #304 **WG** (@BPH3647) · 2025-06-02 21:31

> **@priort** (帖子 #287):
> ART 中使用 agx-emulsion 的光谱胶片模拟 | ART raw image processor

嘿 [@hanatos](/u/hanatos)

我从 darktable 导出了一个 16bit Tiff，使用 Linear Rec2020 配置文件，然后加载到 agx 中。JPEG 是我用来验证直方图是否与 [@arctic](/u/arctic) 的原始转换结果相似。

---

## #305 **John Apolozan** (@JApolozan) · 2025-06-03 17:13

我将 ISO 400 测光的 Portra 400 扫描结果与数码相机在相同等效曝光下拍摄的图像进行了比较，并应用了默认设置的 agx-emulsion（附上 .xmp 和 .arp 作为参考）。

[![Dslr0567](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/7/07a23ac1326cdd7a4551e8330d4f4cd499e1fab7_2_690x238.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/7/07a23ac1326cdd7a4551e8330d4f4cd499e1fab7_2_690x238.jpeg)

Dslr05672047×707 387 KB](/uploads/short-url/15wUSxZjlrIIlItOnOCIjbamSr5.jpeg?dl=1)

[Dslr0567.NEF.xmp](/uploads/short-url/9oM85779j2wAw2i54woWFb3NRG2.xmp) (11.7 KB)

[![_8105001](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/2/725ee8f466a3a29b57cc2ffa31596bf67a0e521b_2_690x211.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/2/725ee8f466a3a29b57cc2ffa31596bf67a0e521b_2_690x211.jpeg)

_81050012048×629 271 KB](/uploads/short-url/gjLM4lpcspkk2f0Zn4SgSxDQSJJ.jpeg?dl=1)

[_8105001.jpg.out.arp](/uploads/short-url/rC581vJlhj6sInOvztVCcpzBYmT.arp) (11.5 KB)

虽然不完全相同，但感觉和氛围都在。很可能底片的打印属性可以进一步调整以匹配 agx 设置，或者反过来。

再次感谢你创建了这个神奇的工具并将其集成到 ART 中。

此致，

John

---

## #306 **jo** (@hanatos) · 2025-06-04 07:26

哇，太酷了！你能也分享一下这里的 raw/扫描/输入图像吗？黑色部分的亮度/色调响应看起来有些不同，我很想用数据来玩玩

[!:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

---

## #307 **John Apolozan** (@JApolozan) · 2025-06-04 18:45

你好 jo，

希望这能行。请原谅我凌乱的客厅/摄影实验室

[!:smiley:](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)

照片拍摄间隔几分钟，相同的光线、镜头、光圈和测光。拍摄时使用的镜头是尼康 105mm f/2.5，使用尼康 Micro-NIKKOR 60mm AF-S G 镜头进行数字化。附加了带有胶片边缘的帧用于橙色遮罩校正。

[_8105001.NEF](/uploads/short-url/r6IcGPQBZcs8Z5wKj2hyoQoNGrb.NEF) (39.2 MB)

[Dslr0567.NEF](/uploads/short-url/3MyCujwekVjeyhCltt4zx6ujPGU.NEF) (48.8 MB)

[Dslr0568.NEF](/uploads/short-url/9n5fhVBwziyNU0dh0P2rVme037y.NEF) (37.1 MB)

---

## #308 **MrWhoMan** (@Yuri_Andronachi) · 2025-07-01 13:35

这很有趣。

有人能解释一下输入图像应该处于什么状态吗？假设我有一张 RAW 或 ARW 文件。

应该是低对比度的还是完全未经处理的？我需要以某种方式准备它吗？

---

## #309 **Benjamin** (@piratenpanda) · 2025-07-01 13:51

我将编辑后的 raw 文件导出为 32bit exr，使用 linear ProRec 色彩空间。效果不错，尽管初始渲染有些偏差，需要先按运行按钮才能获得正确的渲染。

---

## #310 **MrWhoMan** (@Yuri_Andronachi) · 2025-07-01 13:58

谢谢。你用什么软件导出 exr？

---

## #311 **Benjamin** (@piratenpanda) · 2025-07-01 14:03

darktable

---

## #312 **** (@mikae1) · 2025-07-01 18:20

> **@Yuri_Andronachi** (帖子 #308):
> 有人能解释一下输入图像应该处于什么状态吗？假设我有一张 RAW 或 ARW 文件。应该是低对比度的还是完全未经处理的？我需要以某种方式准备它吗？

我是这样使用的：

1. darktable 模块（不使用色调映射器，即不使用 sigmoid、filmic rgb 或 base curve）
 [![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/7/7/77aaffb9408f8326126fd05d4b614ffafb7626ef.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/7/7/77aaffb9408f8326126fd05d4b614ffafb7626ef.png)
 image497×721 44.6 KB](/uploads/short-url/h4Dbjsj8bitUwbrEcBeXRi9uEd9.png?dl=1)
2. darktable 导出
 [![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/6/9/6943a6251a2da324fe6551570a30b1c84e0ee415.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/6/9/6943a6251a2da324fe6551570a30b1c84e0ee415.png)
 image325×490 26.9 KB](/uploads/short-url/f1d4rGDYRsHlJPGXJ7nB16uNr5r.png?dl=1)
3. agx-emulsion 输入设置
 [![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/8/5/856ab36445f12608e3b77cfac0e942d181a121f9.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/8/5/856ab36445f12608e3b77cfac0e942d181a121f9.png)
 image564×333 24.9 KB](/uploads/short-url/j2g6KuHmVETLfoCGjv1SEGOZW8F.png?dl=1)

---

## #313 **nosle** (@nosle) · 2025-07-06 16:15

你的对比证实了我的体验。我很难降低数码模拟的"冲击力"，使其匹配我习惯的模拟胶片效果。

如果有人能弄清楚哪些设置可以柔化和降低对比度以接近扫描胶片的效果，那将非常感谢分享一些技巧。

---

## #314 **jo** (@hanatos) · 2025-07-07 07:24

胶片响应不是线性的，所以你可以通过调整曝光将图像信号置于黑色被压缩或提升的范围内。这里我在应用胶片模拟之前减少了曝光，基本上欠曝了 4 档，然后通过纸张打印曝光（截图中的 `ev paper`）进行补偿：

[![2025-07-07-091536_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/a/fad9c45df3081035bd9b15f64c7920868d322e54_2_690x391.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/a/fad9c45df3081035bd9b15f64c7920868d322e54_2_690x391.png)

2025-07-07-091536_hyprshot2484×1410 922 KB](/uploads/short-url/zN7VKeKIB3ISAqqMQFi98UaA1SY.png?dl=1)

作为参考，这是应用 filmsim 预设后使用默认设置的图像：

[![2025-07-07-091543_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/c/4c0d1e7109426eb00f8076e878f3a7969033f76e_2_690x391.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/c/4c0d1e7109426eb00f8076e878f3a7969033f76e_2_690x391.png)

2025-07-07-091543_hyprshot2484×1410 1.08 MB](/uploads/short-url/aQMotYjMmqUBi1bmHC8efVwmFIO.png?dl=1)

不确定这是否是你想问的？

---

## #315 **Alberto** (@agriggio) · 2025-07-07 08:14

> **@hanatos** (帖子 #314):
> 不确定这是否是你想问的？

你也可以通过调整"print gamma"来降低输出的对比度。也许 [@nosle](/u/nosle) 想说的是这个？

---

## #316 **jo** (@hanatos) · 2025-07-07 08:51

没错。我不想主动推荐 gamma，因为它有点非物理（尽管有用）。

归根结底，胶片配置文件中还有 `min density` 参数，可能匹配不够精确。在更改配置文件之前，我肯定会先评估我们在"辅助"软件中的所有选项。

---

## #317 **nosle** (@nosle) · 2025-07-07 10:35

谢谢提示 [@hanatos](/u/hanatos) , [@agriggio](/u/agriggio) 我做了一些快速测试，方向是对的。

---

## #318 **** (@mino) · 2025-07-07 12:23

那是 vkdt 中的 agx-emulsion 吗？

---

## #319 **jo** (@hanatos) · 2025-07-07 12:39

是的。这个集成已经很长时间了……这提醒我确实应该发布一个版本了。快想不出还有什么借口不把东西做完/合并到 1.0 了。

---

## #320 **** (@niklasiivari) · 2025-07-07 16:11

你好，只是好奇，是否有计划在 vkdt 中实现 agx-emulsion 中缺失的一些功能？我主要对光晕和打印预闪感兴趣。

当然，我这里没有任何催促的意思，我对 filmsim 模块提供的结果非常满意，这只是我有时会期待的东西

[!:sweat_smile:](https://discuss.pixls.us/images/emoji/apple/sweat_smile.png?v=12)

.

另外我还注意到，品红和黄色滤镜在不同胶卷上的效果差异很大，例如，对于 portra 800，-1 品红滤镜调整效果非常强，而对于 portra 400，效果则要微妙得多，有时甚至不足以在不使用颜色模块中额外的白平衡调整的情况下获得中性色调。

---

## #321 **jo** (@hanatos) · 2025-07-08 08:05

好问题。光晕肯定会有的。预闪我忘了，因为我对这个过程不太了解。你用它来实现什么效果？

滤镜是光谱滤镜，而胶片具有光谱响应……所以同样的滤镜在不同的胶卷上显然会有不同的重叠，从而表现出不同强度的效果。

顺便说一下，微调滑块可以通过直接输入数值来超范围使用（点击数字而不是滑块）。或者使用三个自动匹配的青/品红/黄色滑块（非微调），它们的影响会更大。白平衡绝对是我在使用 filmsim 时最挣扎的问题。

---

## #322 **** (@niklasiivari) · 2025-07-08 08:48

说实话，预闪的目的可能通过调整胶片曝光 - 纸张曝光平衡就能实现，因为它旨在保留高光细节。看起来增加负片曝光对此很有帮助！

所以，不必太优先考虑这个，即使没有我也完全ok。

另外感谢关于滤镜的解释，你确定要在 GUI 中隐藏非微调滑块吗？在某些情况下让它们可见可能会有用？

---

## #323 **jo** (@hanatos) · 2025-07-08 11:18

> **@niklasiivari** (帖子 #322):
> 你确定要在 GUI 中隐藏非微调滑块吗？在某些情况下让它们可见可能会有用？

嗯，我希望能减少令人困扰的大量 UI 元素。也许一个白平衡点测工具可以消除调整滤镜的需要？或者一个更紧凑的小部件专门用于这些滤镜权重？得想想。与此同时，这里有一个补丁，可以在涉及纸张打印时取消隐藏滤镜：

<pre data-code-wrap="diff"><code class="lang-diff">--- a/src/pipe/modules/filmsim/params.ui
+++ b/src/pipe/modules/filmsim/params.ui
@@ -17,7 +17,7 @@ size:slider:0.5:2.0
 uniform:slider:0:1.0
 group:process:0
 enlarge:combo:1x resolution:2x resolution:4x resolution
-group:process:2
+group:process:101
 filter c:slider:0:1
 filter m:slider:0:1
 filter y:slider:0:1
</code></pre>

---

## #324 **** (@niklasiivari) · 2025-07-08 12:52

白平衡工具在某些情况下确实可能有用，因为在 filmsim 之前在颜色模块中设置白平衡常常会产生相当奇怪的结果。我认为微调滑块对我来说也足够了，大多数情况下它们够用，当不够时，在滑块范围之外输入数值应该也能解决问题。

---

## #325 **jo** (@hanatos) · 2025-07-10 17:42

现在 master 分支有了光晕。虽然对减少选项没什么帮助：

[![2025-07-10-194126_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/6/8617b3102721a73478c585dd98f3f51115119fd0_2_690x388.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/6/8617b3102721a73478c585dd98f3f51115119fd0_2_690x388.png)

2025-07-10-194126_hyprshot2880×1620 1.48 MB](/uploads/short-url/j8eKVyTZAtKFnLbKx3zllCLj59S.png?dl=1)

---

## #326 **** (@niklasiivari) · 2025-07-10 19:50

> **@hanatos** (帖子 #325):
> 现在 master 分支有了光晕。

太棒了！！

是的，不那么重要的东西应该保持隐藏，以保持界面整洁。

---

## #327 **** (@niklasiivari) · 2025-07-18 11:52

光晕对成色剂效果的影响非常大，这相当有趣。我在玩最近的 playraw 投稿（[链接](https://discuss.pixls.us/t/how-would-you-edit-this-photo/51197)），这是 vkdt 中的 filmsim，fujifilm 400h 和 kodak 2393，成色剂设置为 1，默认光晕量，然后关闭光晕：

[![Screenshot 2025-07-18 144242](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/e/fe56df4d8c125b58ca51f4312f82359c612aecd1_2_690x512.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/e/fe56df4d8c125b58ca51f4312f82359c612aecd1_2_690x512.png)

Screenshot 2025-07-18 1442422126×1579 3.84 MB](/uploads/short-url/AhZoPtMW9gKdnkF9tOh57gg8HxD.png?dl=1)

[![Screenshot 2025-07-18 144303](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/5/35b6fb37aa9f49112f143c7032ca098d716797b9_2_690x509.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/5/35b6fb37aa9f49112f143c7032ca098d716797b9_2_690x509.png)

Screenshot 2025-07-18 1443032129×1572 4.07 MB](/uploads/short-url/7Fblb6OOozrg79ix4cE24eoJrRv.png?dl=1)

可以看出，当启用光晕时，成色剂的效果更加自然，饱和度增加的同时，高对比度边缘的明显光晕现象大大减少。

---

## #328 **jo** (@hanatos) · 2025-07-18 12:16

有趣，感谢这个观察。

我不完全确定应用成色剂和光晕哪种方式最物理……特别是哪个先应用？另外，与原始的 agx-emulsion 相比，我稍微增加了一些成色剂支持的半径（见上面关于摄影参考的讨论，其中一张特定图像显示的光晕区域要大得多）。

另外，据我所知，kodak 2393 纸张还是实验性的。

---

## #329 **** (@niklasiivari) · 2025-07-18 12:26

[edit] 刚才说了一些胡话，我认为光晕应该先发生，因为它发生在曝光期间，而成色剂在显影时发生，对吗？

是的，成色剂量 1.0 已经相当极端了，但在 0.25 范围内，光晕问题也一直困扰着我的一些特定图像，所以我认为这是光晕的一个受欢迎的效果（此外光晕本身看起来就很棒）。

针对最后一点，我测试了其他胶片-纸张组合，无论使用哪种组合，差异和效果都是一样的！

总之，对我来说光晕让效果更好看，至于物理准确性我就不知道了

[!:smiley:](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)

---

## #330 **** (@Aaron_b) · 2025-08-15 18:32

你好，我一直有看到你的一些"play-raw"示例，看到最终结果真的很酷。

我也一直在做自己的胶片模拟。有趣的是，我们对类似问题得出了不同的解决方案。我从负片开始，但卡在了模拟扫描过程上。最近，我完成了一个反转片（ektachrome）的模拟，效果非常满意。我不打算开源，但如果你感兴趣，我可能会在这里或通过消息分享一些细节。

也许我会带着一些新想法重新审视我的负片尝试。

---

## #331 **Tanishq Dubey** (@dubey) · 2025-09-02 20:03

你好！首先，感谢你提供了这么丰富的信息宝库！

我一直在做自己的胶片模拟版本，最近终于有了一组用数码和胶片拍摄的照片。（以下图片中，第一张是胶片，第二张是数码——这些都是在 Darktable 中反转的，没有其他校正）

[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/f/1f1597ca70c2ed432ff50f462f316beb4a35edc5_2_332x500.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/f/1f1597ca70c2ed432ff50f462f316beb4a35edc5_2_332x500.jpeg)

image3862×5812 9.19 MB](/uploads/short-url/4qZ3YTyPfbNTDn7zN841yLwjJ6l.jpeg?dl=1)

[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/5/650a447e3ff2c95cef07090c6809813bd0def362_2_333x500.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/5/650a447e3ff2c95cef07090c6809813bd0def362_2_333x500.jpeg)

image1007×1511 610 KB](/uploads/short-url/epQdNQ12XGtWczWdlL0t8QpmXvk.jpeg?dl=1)

我发现，如果不模拟扫描过程或打印过程，像 Portra 400 这样的胶卷会呈现出非常平坦的外观和强烈的青/蓝色调。我通过自己的扫描能够复现这个效果（如附件图片所示），但我想知道扫描实验室是如何得到完全不同的效果的：

[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/f/5f3593dfba2dfda470192081dc16859f396fdf75_2_336x500.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/f/5f3593dfba2dfda470192081dc16859f396fdf75_2_336x500.jpeg)

image1440×2142 837 KB](/uploads/short-url/dAg9fGjj6Iz2k5q1KZCp9SUw3Rj.jpeg?dl=1)

真的只是扫描配置文件对图像做了这么大的调整吗？我觉得既然我的模拟图像与我家庭扫描的颜色匹配，我的模拟过程是正确的，但我想更接近实验室提供的效果。有人有建议吗？

---

## #332 **Jimmy Qiu** (@Jimmy_Qiu) · 2025-09-03 17:34

负片是为打印而设计的，而不是用普通数码相机扫描。可以把相纸想象成一种只能看到特定波长光的动物。所以，当你通过相机看负片时，当然看起来不对。实验室扫描仪的光谱灵敏度与相纸相似，所以结果更接近实际打印的效果。如果你只是在数码扫描上反转负片，你会得到一个误读的图像，这不是 Kodak 的意图。

---

## #333 **István Kovács** (@kofa) · 2025-09-04 10:48

你用了 *negadoctor* 吗？它可以处理红色/橙色的胶片基底，这很可能会在反转图像后给你带来蓝/绿色偏移。

<aside class="onebox allowlistedgeneric" data-onebox-src="https://darktable-org.github.io/dtdocs/en/module-reference/processing-modules/negadoctor/">
 <header class="source">

 [darktable user manual](https://darktable-org.github.io/dtdocs/en/module-reference/processing-modules/negadoctor/)
 </header>

 <article class="onebox-body">


### [negadoctor](https://darktable-org.github.io/dtdocs/en/module-reference/processing-modules/negadoctor/)


Process scanned film negatives.
You can obtain an image of a negative using a film scanner, or by photographing it against a white light (e.g. a light table or computer monitor) or off-camera flash.
🔗preparation If the image of the negative was...

 </article>









</aside>

 [![图片397](https://d2x313g9lpht1q.cloudfront.net/original/3X/f/2/f2f0514e9a48be55db958a6442bce1c749cad028.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/f/2/f2f0514e9a48be55db958a6442bce1c749cad028.jpeg)](https://www.youtube.com/watch?v=DiNlHBZE888)

还是说你的目的是想自己做所有事情，以学习和/或改进流程？

---

## #334 **Benjamin** (@piratenpanda) · 2025-09-13 09:33

搭配像 KMZ Helios 58 mm f2 这样的老镜头效果非常好

<div class="lightbox-wrapper">[![helios1_small](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/0/10163142c5ed51d7ea8f155f23866d0f74919c26_2_666x1000.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/0/10163142c5ed51d7ea8f155f23866d0f74919c26_2_666x1000.jpeg)

helios1_small800×1200 193 KB](/uploads/short-url/2ijbzcW5zSNbmU8s6y29HyAkGwu.jpeg?dl=1)

[![helios2_small](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/2/f265b38871604d0d3976d67191ea4a9dca67904a_2_690x459.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/2/f265b38871604d0d3976d67191ea4a9dca67904a_2_690x459.jpeg)

helios2_small1200×800 137 KB](/uploads/short-url/yAlroAuTApak9wM4WJgzwgHw8Ns.jpeg?dl=1)

[![helios3_small](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/c/9cb9cab9cb5be2ec0353f459227c93c5880f5b5f_2_666x1000.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/c/9cb9cab9cb5be2ec0353f459227c93c5880f5b5f_2_666x1000.jpeg)

helios3_small800×1200 139 KB](/uploads/short-url/mmsxE7k2q7Xuet6FLvv7BDuXSUf.jpeg?dl=1)

</div>

---

## #335 **** (@Thomsen) · 2025-09-25 10:23

你好！我一直在广泛寻找适合静帧照片的好胶片模拟，这看起来真是一颗隐藏的宝石！我在 Davinci Resolve 中做过调色师，但对这里提到的 RAW 编辑器没有经验。

通过 python 成功安装了 0.1.0 版本，并试图通读这个 megathread，但如果以下问题已经有人回答过了，请原谅我：

对于这个工作流程，哪个应用程序最合适且功能最全？（VKDT、Darktable、ART）——针对色彩、光晕、颗粒等。

我看到有些程序使用 LUT，这在视频领域通常意味着较差的图像质量和压缩的色彩数据——而且 LUT 不传递颗粒、光晕等。python 版本的处理与其他程序基于 LUT 的处理有区别吗？

有计划发布 1.0 版本吗？等待它有意义吗？

---

## #336 **jo** (@hanatos) · 2025-09-25 10:48

> **@Thomsen** (帖子 #335):
> 对于这个工作流程，哪个应用程序最合适且功能最全？（VKDT、Darktable、ART）——针对色彩、光晕、颗粒等。

我只能说 vkdt，它相当忠实地实现了 python 原版的大部分功能，但有一些差异。它支持正片 raw 的处理、负片扫描、多层颗粒、光晕和 DIR 成色剂，尽管不是像素级一致的实现。vkdt 在 GPU 上实现算法，这使得等待结果更容易（快得多）。

darktable 没有实现这些功能，不过有一个叫"AgX"的东西（与"agx emulsion"不同），那是 troy 的复杂色调映射引擎，不基于胶片模拟或光谱输入。

ART 实现了一种类似于/等同于 LUT 方法的功能，它不传递颗粒、光晕或 DIR 成色剂。

（各位维护者，如果这些信息过时或有误，请纠正我 ;)）

> **@Thomsen** (帖子 #335):
> python 版本的处理与其他程序基于 LUT 的处理有区别吗？

有，见上。我记得 ART 使用某种逐像素的外部脚本。我不知道它是否先经过离散化/量化 LUT，或者是否至少能避免这类伪影。

> **@Thomsen** (帖子 #335):
> 有计划发布 1.0 版本吗？等待它有意义吗？

我知道 vkdt 1.0 有计划，但不能代表 *agx emulsion*。因为这是开源的……我认为等待 1.0 没什么意义。

---

## #337 **** (@Thomsen) · 2025-09-25 16:46

我现在在 VKDT 中测试了一些旧照片。毫无疑问，这是我不做任何编辑就能得到的最佳色彩和质感。

关于光晕的问题：高光看起来很棒，辉光效果很好，但光晕对中间调的影响似乎比我在模拟胶片中通常看到的要大——大幅降低了中间调的对比度。这是有意为之还是我遗漏了什么设置？（只是按原样使用节点预设）。

---

## #338 **nosle** (@nosle) · 2025-09-25 19:58

我一直在测试这个线程中的一些旧图像。我不得不说，现在 vkdt 和 agx 按照所述配方生成的图像看起来都不太像样本了。总的来说，结果比原始结果更"不自然"。仿佛效果变得更强烈了。

你看到了什么？是我失去了感觉，还是开发进展改变了那么多结果？

---

## #339 **Benjamin** (@piratenpanda) · 2025-09-26 10:27

或者搭配 Super Takumar 50 1.4：
[![rose_takumar_small](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/b/6bd1f4601f324d6c576f45149f6948c8aac8b76b_2_668x1000.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/b/6bd1f4601f324d6c576f45149f6948c8aac8b76b_2_668x1000.jpeg)

rose_takumar_small1003×1500 259 KB](/uploads/short-url/fnOUJarKA3nQLUkDfnD8OvJYA1d.jpeg?dl=1)

---

## #340 **jo** (@hanatos) · 2025-09-26 11:42

> **@Thomsen** (帖子 #337):
> 但光晕对中间调的影响似乎比我在模拟胶片中通常看到的要大

嗯，你能举个例子吗？我只是用默认权重实现了卷积。如果只是调整这些值的问题，我可以更新默认值。

> **@nosle** (帖子 #338):
> 是我失去了感觉，还是开发进展改变了那么多结果？

我不知道有这样的变化。我知道我们实验过的一件事是曝光纸张时的自动白平衡。你总可以手动调整。

---

## #341 **nosle** (@nosle) · 2025-09-26 11:51

我在 agx 应用中也看到了类似的色调，所以要么是我变了，要么是两个应用自初始版本以来都发生了变化。有时间我会展示示例。我的绿色在 portra 下基本上是棕色/黄色，根据我的胶片经验，我期待的是不同的效果——绿色应该变得更暗，带点蓝色调？

---

## #342 **** (@Thomsen) · 2025-09-26 11:52

> 嗯，你能举个例子吗？我只是用默认权重实现了卷积。如果只是调整这些值的问题，我可以更新默认值。

有高光和对比度的区域，**无**光晕：

[![Highlights w o halation](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/d/2d60dfe76f4e9062070ae3887960bce3fb15eb39_2_345x296.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/d/2d60dfe76f4e9062070ae3887960bce3fb15eb39_2_345x296.jpeg)

Highlights w o halation796×685 125 KB](/uploads/short-url/6tr2qi0iL8hmh6a1jV0u0wFy56N.jpeg?dl=1)

有高光和对比度的区域，**有**光晕。看起来令人愉悦，光晕表现符合预期。

[![Highlights w halation](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/9/29ae738464e7414d2a8ffc1b1019b6dbfd2e882f_2_345x287.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/9/29ae738464e7414d2a8ffc1b1019b6dbfd2e882f_2_345x287.jpeg)

Highlights w halation798×666 107 KB](/uploads/short-url/5WJkQUcBvQT3W4Lg9rxl4fV2BLp.jpeg?dl=1)

中间调区域，**无**光晕：

[![Midtones w o halation](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/7/a794c7fc81688a7d4b5b697d6f750303c7ed2cc9_2_517x381.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/7/a794c7fc81688a7d4b5b697d6f750303c7ed2cc9_2_517x381.jpeg)

Midtones w o halation1398×1033 409 KB](/uploads/short-url/nUuuZgq9Yk8s0SGJFf1FXL05cGR.jpeg?dl=1)

中间调区域，**有**光晕：一切看起来都很有发光感，就像用很强的黑柔滤镜拍摄一样。即使是树底部的较暗区域也被洗白了。这通常不是胶卷的预期行为，即使去除了防光晕层（如 Cinestill 等）也是如此。

[![midtones w halation](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/f/4f4428bded26d8bee9da89c42f889db64afc67fd_2_517x383.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/f/4f4428bded26d8bee9da89c42f889db64afc67fd_2_517x383.jpeg)

midtones w halation1393×1032 348 KB](/uploads/short-url/bjdKwNdP5fqtzUK8trcy8rBrqep.jpeg?dl=1)

---

## #343 **** (@Thomsen) · 2025-09-26 11:58

> 如果只是调整这些值的问题，我可以更新默认值。

调整光晕设置时，我无法在不减少整个图像光晕的情况下消除中间调的这种效果。

Cinestill 800T 扫描示例。这应该是市面上最容易产生光晕的胶卷了，但尽管高光疯狂辉光，中间调和阴影却保持了完美的清晰度。

[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/b/9b600dae69cfcfa6a419de0bbbec6640e57e9f47_2_690x459.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/b/9b600dae69cfcfa6a419de0bbbec6640e57e9f47_2_690x459.jpeg)

image2048×1365 1.05 MB](/uploads/short-url/mavNGR2fIXN73Chooy85usPm8lh.jpeg?dl=1)

---

## #345 **** (@Thomsen) · 2025-09-26 12:25

抱歉连发了三条，我是论坛新手

[!:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

但在原帖中，光晕似乎没有以同样的方式影响中间调：

> **@arctic** (帖子 #1):
> tree_branches_kodak_gold_200_crystal_archive_preflash005_4Y10M_04pe_2ev_halation31440×1920 5.75 MB

---

## #346 **jo** (@hanatos) · 2025-09-26 12:44

嗯，也许是成色剂和光晕之间相互作用的不同？你启用了成色剂吗（默认是启用的）？我会做一些实验并留意这个问题。我也不想让中间调变得模糊。

---

## #347 **** (@Thomsen) · 2025-09-26 12:51

成色剂已启用。但增加成色剂值不知为何也使图像更亮了。在原帖中，它们似乎只影响饱和度和色彩深度。

考虑到这些意外的行为，我在想是不是我设置错了什么，或者是因为我运行的是 Windows 夜间构建版本？

你在 Linux 上也有同样的中间调退化问题吗？

我的节点树设置正确吗？

[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/a/dac86da54ac3eb7979864bacf9c17d0dbb545b94_2_517x181.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/a/dac86da54ac3eb7979864bacf9c17d0dbb545b94_2_517x181.jpeg)

image1234×433 73.2 KB](/uploads/short-url/vdrvgd9aEZe21DjJa7xQYFwKD2c.jpeg?dl=1)

---

## #348 **jo** (@hanatos) · 2025-09-26 12:56

嗯，你是不是把 filmsim lut 作为主图像文件打开了？应该是这样的：

[![20250926_14h55m24s_grim](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/b/ebe38951587ba05103b070693de5270235615cce_2_690x226.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/b/ebe38951587ba05103b070693de5270235615cce_2_690x226.png)

20250926_14h55m24s_grim2082×684 85.5 KB](/uploads/short-url/xELHoWR7v6SpLZ8xQbOhETMn3Vc.png?dl=1)

---

## #349 **** (@Thomsen) · 2025-09-26 12:59

> **@hanatos** (帖子 #348):
> 嗯，你是不是把 filmsim lut 作为主图像文件打开了？应该是这样的：

抱歉，filmsim lut 只是在输入之上。

[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/5/65b2d58a93a382be6a21574d43945443dbe79b71_2_689x229.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/5/65b2d58a93a382be6a21574d43945443dbe79b71_2_689x229.jpeg)

image1231×409 76.9 KB](/uploads/short-url/evFnf8uPhAmx6A3WzsmdAxCEH17.jpeg?dl=1)

现在匹配你的了，但中间调退化问题依旧。

---

## #350 **jo** (@hanatos) · 2025-09-26 13:06

哦，当然，我想我可以重现你的意思了。

---

## #351 **** (@tankist02) · 2025-09-26 17:54

当我在 ART 中选择 Kodak Portra 400 时，我看到暗棕色的绿色。如果切换到 Kodak Gold 200，绿色会变得更绿一些

---

## #352 **nosle** (@nosle) · 2025-09-26 21:04

这是本线程顶部图像的一些样本。按照第一个帖子中列出的设置复现。

[![2025-09-26-225941_1139x707_scrot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/0/405839773b44957b95b9284cb2e4f4def8df42b9_2_690x428.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/0/405839773b44957b95b9284cb2e4f4def8df42b9_2_690x428.png)

2025-09-26-225941_1139x707_scrot1139×707 547 KB](/uploads/short-url/9bdzQvvAB4iT33ouWuzGaOagmFj.png?dl=1)

[![2025-09-26-230056_1517x967_scrot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/1/0157c01d07b8baad8141f5350c57525425edb07c_2_690x439.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/1/0157c01d07b8baad8141f5350c57525425edb07c_2_690x439.png)

2025-09-26-230056_1517x967_scrot1517×967 1.32 MB](/uploads/short-url/bStSwNHsO1iSYNZBhtW71yG08s.png?dl=1)

我无法在 vkdt 中复现设置，因为配方是为 agx 设计的，设置比例不同等。但问题是颜色偏差很大，严重偏色。

这是上面我复现的他示例列表中第三张图像的参考。

 [![图片413](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/5/f52a4fe7f32be668584e1c2b24133c22f688ee4d_2_222x333.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/5/f52a4fe7f32be668584e1c2b24133c22f688ee4d_2_222x333.png)

对我来说，portra endura 纸张比我看到的样片更偏棕/黄色

---

## #353 **jo** (@hanatos) · 2025-09-27 15:28

感谢你提供带有示例的准确描述！我现在不在电脑前，等我回来再看。

先排除一些简单的问题，你的色彩管理设置是什么？

---

## #354 **nosle** (@nosle) · 2025-09-27 16:09

显示器已校色，运行 colormngr、xicc 加载系统配置文件（没有桌面环境，只有 openbox）。校准设备是比较旧的非专业产品。

如果能知道其他人用这个线程中的一些图像得到什么结果会很有趣。我觉得在这个过程中发生了一些变化。只是不确定是我的设置/工作流程的问题还是软件的变化。

---

## #355 **jo** (@hanatos) · 2025-09-27 16:17

啊，你有没有通过 vkdt read-icc 告诉 vkdt 获取配置文件？

---

## #357 **** (@Thomsen) · 2025-09-27 17:10

> **@hanatos** (帖子 #350):
> 哦，当然，我想我可以重现你的意思了。

光晕似乎也柔化了颗粒，而成色剂在关闭光晕时行为异常。也许与操作顺序有关，或者至少这些设置之间存在相互影响。

> **@nosle** (帖子 #352):
> 这是上面我复现的他示例列表中第三张图像的参考。
> 对我来说，portra endura 纸张比我看到的样片更偏棕/黄色

我通过冷却白平衡并在胶片转换前增加饱和度，成功获得了一些更好的绿色——实际上是在增加色彩分离度。

"Apply preset whitebalance-camera" 是一个不错的起点，但我不得不让它更冷才能匹配第一个帖子中参考的绿色。

不过有一个问题："tune m"和"tune y"控制可以受益于更大的范围。正负 1 似乎有些局限。

[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/a/1ae4aaf09ba92e04cb674d111a69ce2962ccbb29_2_690x564.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/a/1ae4aaf09ba92e04cb674d111a69ce2962ccbb29_2_690x564.jpeg)

image1335×1093 303 KB](/uploads/short-url/3PUkCtZSJZJMCTma4xCtRjlIL4B.jpeg?dl=1)

---

## #358 **nosle** (@nosle) · 2025-09-27 17:42

没有！正在检查那个标志，但找不到文档。它输出标签但不启动 vkdt。不过在我的设置中，有无配置文件差别很小。

> **@Thomsen** (帖子 #357):
> 我通过冷却白平衡并在胶片转换前增加饱和度，成功获得了一些更好的绿色——实际上是在增加色彩分离度。
> "Apply preset whitebalance-camera" 是一个不错的起点，但我不得不让它更冷才能匹配第一个帖子中参考的绿色。

你的结果看起来很接近。不过这过程挺复杂的，我不记得以前需要这样。

> **@Thomsen** (帖子 #357):
> "Apply preset whitebalance-camera" 是一个不错的起点，

是的，我也这样做了

---

## #359 **** (@Thomsen) · 2025-09-28 07:53

> **@nosle** (帖子 #358):
> 你的结果看起来很接近。不过这过程挺复杂的，我不记得以前需要这样。

根据我的观察，图像似乎经历了与原帖中相同的色彩转换过程。

如果我们不得不使用色彩曲线或局部调整来匹配原帖，那可能转换过程有问题。但我只做了影响整个图像的编辑——拉冷色调和增加饱和度——结果非常接近。

根据我的经验，在应用任何色彩转换之前，找到完美的白平衡是非常重要的一步。

---

## #360 **** (@Thomsen) · 2025-09-28 08:47

这张实际上更难匹配，尤其是肤色。

当在转换前的颜色节点中增加饱和度时，我注意到了彩色伪影。尤其是绿色变得更暗且出现噪点。

[@hanatos](/u/hanatos) filmsim 节点是在有限的色彩空间中工作吗？

[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/d/cd5c6a9046d1131acc0e30c5a6b98ff8b99f1161_2_690x437.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/d/cd5c6a9046d1131acc0e30c5a6b98ff8b99f1161_2_690x437.jpeg)

image1252×793 272 KB](/uploads/short-url/tiHSHQxKderyxQvqLEbRJvpNtct.jpeg?dl=1)

---

## #361 **** (@mikae1) · 2025-09-28 20:07

我只想说，我再次以极大的兴趣关注这个线程。

[!:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

这又一次提醒我需要学习 vkdt。能有一个解释基本概念的视频介绍就太好了，我一直没找到。

> **@Thomsen** (帖子 #357):
> 光晕似乎也柔化了颗粒

是的，我也注意到了。似乎顺序搞错了？

---

## #362 **Upperechelonstr8up** (@upperechelonstr8up) · 2025-09-29 06:08

请继续这个项目，拓展它的可能性！这是我见过最棒的胶片模拟器，早就该有了，我会持续关注这个项目的任何进展！

---

## #363 **Benjamin** (@piratenpanda) · 2025-09-29 06:22

我也是这样想的。[@arctic](/u/arctic) 我们怎么支持你？你接受捐赠吗？

---

## #364 **jo** (@hanatos) · 2025-09-29 06:26

> **@Thomsen** (帖子 #357):
> "tune m"和"tune y"控制可以受益于更大的范围。正负 1 似乎有些局限。

这些是微调参数。我把实际的白平衡系数从 GUI 中隐藏起来以减少杂乱，这可能不是个好选择。总的来说，这种曝光纸张的白平衡很难做对，我在这范围上也遇到过不少问题。作为一种变通方法，你总是可以点击数字并输入远超出范围的值（有点麻烦，但至少能用）。

> **@nosle** (帖子 #358):
> 没有！正在检查那个标志，但找不到文档。它输出标签但不启动 vkdt。不过在我的设置中，有无配置文件差别很小。

好的，记下了：我得改进这些文档。`vkdt read-icc your-monitor-profile.icc` 会创建一个包含 gamma + rec2020-to-display 矩阵的文件 `display.profile`，如果该文件位于 `~/.config/vkdt/display.DP-1`（例如，如果你的显示器在 wayland 或 xorg 中被命名为 `DP-1`），vkdt 会读取它。更现代的 wayland 配置允许我们使用 rec2020 作为合成器色彩空间（例如 kde 和 hyprland 支持），所以你可以把单位矩阵放入这个文件中。我会更新文档……

> **@Thomsen** (帖子 #360):
> 当在转换前的颜色节点中增加饱和度时，我注意到了彩色伪影。尤其是绿色变得更暗且出现噪点。

从噪点过渡来看，这些可能超出了光谱轨迹。

> **@Thomsen** (帖子 #360):
> @hanatos filmsim 节点是在有限的色彩空间中工作吗？

它在光谱空间中工作。这也意味着它会在处理之前将任何输入颜色上采样为光谱。你能试试应用 `gamut` 预设吗？即在暗房模式下按 `ctrl-p`，输入 `gamut` 然后按 `enter`？它会在 `colour` 模块中加载一个保留色调的表格，允许你提高饱和度而不超出光谱轨迹限制。光谱上采样对非物理输入是容忍的，但如果超出太多，结果就没太大意义了。

---

## #365 **jo** (@hanatos) · 2025-09-29 07:27

> **@piratenpanda** (帖子 #363):
> 我也是这样想的。[@arctic](/u/arctic) 我们怎么支持你？你接受捐赠吗？

同意。有什么我们能帮忙的吗？我想项目/代码上可能有一些有用的工作可以做，我觉得也许我们可以

- 帮助理清操作顺序的见解
- 研究颗粒、光晕和成色剂之间的相互作用

以及其他有趣的方向：

- 添加更多胶卷，这个线程中提到了一些
- 添加黑白胶片处理代码路径

我觉得黑白主要就是阅读一些文献然后剥离所有颜色功能，也许我们中的爱好者可以先迈出第一步。添加更多胶卷我认为需要 [@arctic](/u/arctic) 所做的一些仔细目测、数据处理、归一化然后导入代码。这至少需要一份详细的操作指南。

---

## #366 **** (@Thomsen) · 2025-09-29 12:57

> **@hanatos** (帖子 #364):
> 这些是微调参数。我把实际的白平衡系数从 GUI 中隐藏起来以减少杂乱，这可能不是个好选择。总的来说，这种曝光纸张的白平衡很难做对，我在这范围上也遇到过不少问题。作为一种变通方法，你总是可以点击数字并输入远超出范围的值（有点麻烦，但至少能用）。

啊，我明白了。我也遇到了同样的白平衡困难，所以也许包含白平衡系数会有帮助？或许可以做一个可折叠的子菜单叫"白平衡调整"之类的？

> **@hanatos** (帖子 #364):
> 它在光谱空间中工作。这也意味着它会在处理之前将任何输入颜色上采样为光谱。你能试试应用 gamut 预设吗？即在暗房模式下按 ctrl-p，输入 gamut 然后按 enter？它会在 colour 模块中加载一个保留色调的表格，允许你提高饱和度而不超出光谱轨迹限制。光谱上采样对非物理输入是容忍的，但如果超出太多，结果就没太大意义了。

加载预设后什么也没发生。

有没有办法在 filmsim 节点之后增加饱和度？

我一直在寻找简单的 HSL 工具之类的，但除了 Color 节点之外，找不到任何增加饱和度的方法，而 Color 节点似乎在 filmsim 之后不能再次添加。

> **@mikae1** (帖子 #361):
> Thomsen:

光晕似乎也柔化了颗粒

是的，我也注意到了。似乎顺序搞错了？

</blockquote>
</aside>

我同意操作顺序可能有问题，因为它影响了颗粒。

另外，我注意到光晕在改变胶片曝光时不受影响。负片中的光晕与曝光非常相关——只有最亮的曝光才能完全烧穿并反射为光晕。

[@arctic](/u/arctic) 的原始实现似乎只影响高对比度和高曝光区域，而不是整个图像。

我可能会在有空时对 python 脚本和 VKDT 之间的光晕进行比较。

---

## #367 **Anna** (@betazoid) · 2025-10-01 15:03

对于想要第一次尝试的人来说，推荐使用哪个"版本"——原始的 python 程序、ART 还是 vkdt？

---

## #368 **nosle** (@nosle) · 2025-10-01 15:43

在我看来，原始版本是另一回事。它处理颗粒和光晕的方式在我看来更接近胶片。这些对于胶片效果也非常重要。

不幸的是，它在速度和易用性方面也是另一回事——极其缓慢且繁琐！

## #369 **Anna** (@betazoid) · 2025-10-02 10:48

让我能勉强工作的方法，只有通过 vkdt。我试了很久 ART，但它一直抱怨输入值有问题之类的。

在 vkdt 的 nightly appimage 中，read-icc 似乎不再正常工作，或者工作机制变了。它能显示 ICC 配置文件的值，但下次启动 vkdt 时，又会选择 sRGB 作为显示配置文件。@hanatos 你为什么把这个弄坏了？而且我无法让 appimage 在 (x)wayland 上运行，只能在 kde-plasma-x11 上跑。不过，我不知道 vkdt 用的是哪个 GPU，Nvidia 还是 Intel。感觉像是在用 Intel。

编辑：我后来还是把原始程序搞定了。原来我得把邮件工具窗口从程序窗口分离出来才能看到运行按钮。

有很多工具可以玩很久了……

---

## #370 **Anna** (@betazoid) · 2025-10-02 11:47

原始 Python 工具中的色彩管理怎么样？我的笔记本屏幕基本上是 P3 色域的——如果我选择 DisplayP3 作为输出色彩空间，我能看到大致准确的色彩吗？抱歉，我没看完整篇帖子，可能已经有人问过这个问题了？

---

## #371 **Anna** (@betazoid) · 2025-10-02 13:28

非常酷的工具。希望它最终能成为一个 darktable 模块。

---

## #372 **jo** (@hanatos) · 2025-10-02 15:18

> **@Thomsen** (帖子 #366):
> 我同意操作顺序可能有问题，因为它影响了颗粒效果。

颗粒是在光晕之后添加的，而且光晕是应用于线性原始输入，公式与 Python 版本等效。我的意思是，尝试为低/中亮度区域添加一些额外保护是有道理的，但 Python 版本也没有这个功能。

我能看到的唯一一点不同是耦合剂 vs 光晕。

---

## #373 **jo** (@hanatos) · 2025-10-02 15:51

> **@betazoid** (帖子 #369):
> 让我能勉强工作的方法，只有通过 vkdt。我试了很久 ART，但它一直抱怨输入值有问题之类的。

> **@betazoid** (帖子 #369):
> 你为什么把这个弄坏了 @hanatos？

哈哈，深呼吸！我觉得这三个项目中的任何一个都无法从你的文字中提取出任何可操作的调试信息。

> **@betazoid** (帖子 #370):
> 原始 Python 工具中的色彩管理怎么样？[…]
> 如果我选择 DisplayP3 作为输出色彩空间，我能看到大致准确的色彩吗？

不能。

> **@betazoid** (帖子 #371):
> 非常酷的工具。

是的。

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

---

## #374 **Sébastien Guyader** (@sguyader) · 2025-10-02 16:47

> **@betazoid** (帖子 #369):
> 我试了很久 ART，但它一直抱怨输入值有问题之类的。

几个问题可能导致此消息，其中两个是缓存中存在旧数据（因此请先清理 ART 缓存）以及 ART 脚本找不到你的 AGX Python 环境。

---

## #375 **** (@tankist02) · 2025-10-02 20:12

如果你能提供更多关于你的 ART + AgX 设置的细节，也许我们能帮忙？

---

## #376 **Anna** (@betazoid) · 2025-10-02 23:29

没关系，我已经弄好了。我只需要找到 venv 的正确路径。

---

## #377 **Anna** (@betazoid) · 2025-10-02 23:32

> **@hanatos** (帖子 #373):
> 不能。

但我认为如果输出配置文件与显示器色彩空间大致相同，颜色就是大致正确的。问题只在于，当我从 agx-emulsion 保存图片时，文件中没有嵌入任何配置文件。也许我可以修复这个问题。

---

## #378 **Anna** (@betazoid) · 2025-10-02 23:36

> **@hanatos** (帖子 #373):
> 哈哈，深呼吸！我觉得这三个项目中的任何一个都无法从你的文字中提取出任何可操作的调试信息。

```
anna@zbook:~/Downloads$ ./vkdt-rawler-glfw3.4-0.9.99-815-gdc9dbc4c-x86_64.AppImage
[gui] vkdt 0.9.99-815-gdc9dbc4c (c) 2020--2025 johannes hanika
[gui] glfwGetVersionString() : 3.4.0 Wayland X11 GLX Null EGL OSMesa monotonic
[gui] monitor [0] eDP-1 at 0 0
[gui] vk extension required by GLFW:
[gui] VK_KHR_surface
[gui] VK_KHR_wayland_surface
[ERR] failed to init gui/swapchain

```

这是在 Debian 13/新 HP 笔记本上，带 Nvidia+Intel/KDE Plasma/Wayland

```
anna@zbook:~/Downloads$ ./vkdt-rawler-glfw3.4-0.9.99-815-gdc9dbc4c-x86_64.AppImage read-icc /home/anna/hp.icc
tag rXYZ 0.507935 0.240265 0.0039978
tag gXYZ 0.29306 0.691589 0.0451508
tag bXYZ 0.163208 0.0681458 0.775757
tag rTRC 2.20703
tag gTRC 2.20703
tag bTRC 2.20703
anna@zbook:~/Downloads$ ./vkdt-rawler-glfw3.4-0.9.99-815-gdc9dbc4c-x86_64.AppImage
[gui] vkdt 0.9.99-815-gdc9dbc4c (c) 2020--2025 johannes hanika
[gui] glfwGetVersionString() : 3.4.0 Wayland X11 GLX Null EGL OSMesa monotonic
[gui] monitor [0] eDP-1 at 0 0
[gui] vk extension required by GLFW:
[gui] VK_KHR_surface
[gui] VK_KHR_xcb_surface
[gui] no gamepad found
[gui] no display profile file display.eDP-1, using sRGB!

```

看起来新的 read-icc 还没完成？

编辑：我通过设置以下环境变量在 plasma/wayland 上运行了 vkdt：

`env SDL_VIDEODRIVER=x11 XDG_SESSION_TYPE=x11 ./vkdt-rawler-glfw3.4-0.9.99-815-gdc9dbc4c-x86_64.AppImage`

编辑：我现在已经把 agx-emulsion、ART 和 vkdt 都搞定了。vkdt 的色彩管理也能用，虽然有点笨拙。不过，这三个应用程序我得到了不同的结果。ART 和 agx-emulsion 比较接近，vkdt 似乎有点偏黄，当然可以通过白平衡修复，但源文件差异不大，白平衡也非常相似。我稍后会发示例图片。

---

## #379 **jo** (@hanatos) · 2025-10-05 08:18

> **@betazoid** (帖子 #378):
> 看起来新的 read-icc 还没完成？

啊。我不得不用一种合适的语言重写它，因为 Arch Linux 的打包系统有充分理由地抱怨 Python 版本引入了 numpy 依赖。对于矩阵乘法来说，这似乎有点重量级。

---

## #380 **Matej Špoljar** (@Matej_Spoljar) · 2025-10-07 21:21

这真的超级有趣，它很可能是最好的胶片模拟工具，除了你在 Baselight 或 Genesis 中能找到的那些

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

但我也得到了奇怪的棕黄色绿色，尤其是 Portra 的效果，示例图片与样本（uv agx 版本和 vkdt）差异很大

---

## #381 **** (@tankist02) · 2025-10-07 23:57

我也在 ART 中使用 AgX 时遇到了奇怪的色彩（红色太多）。使用 Kodak Gold 200 可以稍微缓解问题，但还不够。提高定向耦合剂用量和降低胶片伽马因子会有所帮助。

---

## #382 **** (@mino) · 2025-10-08 05:09

我也遇到过这个问题。将模拟纸张切换为 Fuji Crystal 给了我更漂亮的色彩。

---

## #383 **Anna** (@betazoid) · 2025-10-08 08:04

也能确认棕绿色的存在。

---

## #384 **** (@Thomsen) · 2025-10-08 09:58

我喜欢这种模拟给这家繁忙的披萨店带来的电影感。

富士 X-m5 搭配 35mm f0.95 镜头。

柯达 Ektar 100 胶片配柯达 Supra Endura 相纸

[[![Stockholm (18)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/b/fb47c493256bdd819a3d387618a0e724e7e53b1f_2_690x345.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/b/fb47c493256bdd819a3d387618a0e724e7e53b1f_2_690x345.jpeg)

Stockholm (18)6240×3120 4.77 MB](/uploads/short-url/zQVBDrApuK9zql4PlToRPpdf56v.jpeg?dl=1)

[[![Stockholm (17)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/d/0d5619d74bb01e566c3b2bcb3500fd3127b2e2f2_2_690x345.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/d/0d5619d74bb01e566c3b2bcb3500fd3127b2e2f2_2_690x345.jpeg)

Stockholm (17)6240×3120 4.75 MB](/uploads/short-url/1TYG0qQN5aie35MbhCQ8QlT1a02.jpeg?dl=1)

---

## #385 **jo** (@hanatos) · 2025-10-08 10:04

我有一些本地更改，可能会再测试一下然后推送。首先是关于为光晕添加显式的中间调保护。

新版本：

[[![2025-10-08-113304_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/4/24035cf8c84a6183901dd6c27df6189b407a1931_2_690x540.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/4/24035cf8c84a6183901dd6c27df6189b407a1931_2_690x540.png)

2025-10-08-113304_hyprshot2071×1621 2.61 MB](/uploads/short-url/58AosrH1EpHq4XnVfxYSH3We8Hn.png?dl=1)

旧版本，注意树上缆线的细节少了很多（可能需要对比两图）：

[[![2025-10-08-113254_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/7/7767ca1a7b29501a68ae3115925352a68595e2c5_2_690x540.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/7/7767ca1a7b29501a68ae3115925352a68595e2c5_2_690x540.png)

2025-10-08-113254_hyprshot2071×1621 2.49 MB](/uploads/short-url/h2jbAp7CAnkVkWa1AfY1QigR40t.png?dl=1)

无光晕效果，供参考：

[[![2025-10-08-113249_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/4/f401321ab995fde7b30b7085e33bb10919902a58_2_690x540.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/4/f401321ab995fde7b30b7085e33bb10919902a58_2_690x540.png)

2025-10-08-113249_hyprshot2071×1621 2.66 MB](/uploads/short-url/yOz40m0xYCqsPSFHSMrvYIcxPjW.png?dl=1)

第二个是关于颗粒效果的。当前默认，单倍频程蓝噪声：

[[![2025-10-08-112957_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/1/11d16494ef226c9babafaeb647f175eba328ae79_2_690x540.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/1/11d16494ef226c9babafaeb647f175eba328ae79_2_690x540.png)

2025-10-08-112957_hyprshot2071×1621 2.45 MB](/uploads/short-url/2xCJPwPhnRzz9Dbxzejs5MIQW93.png?dl=1)

新版本，双倍频程蓝噪声，重复结构有更多随机的破碎感：

[[![2025-10-08-112946_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/d/dd201d4ae112f8fd0a3a276c463fb8fc923f2324_2_690x540.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/d/dd201d4ae112f8fd0a3a276c463fb8fc923f2324_2_690x540.png)

2025-10-08-112946_hyprshot2071×1621 2.48 MB](/uploads/short-url/vyakcorhSbl06I2CzO53aqShwFu.png?dl=1)

---

## #386 **** (@Thomsen) · 2025-10-08 10:14

看起来非常有前景！颗粒效果确实更令人满意了。

光晕在中间调退化问题上也更好用了。

不过高光边缘看起来有点锐利——可能需要更柔和的衰减？

---

## #387 **** (@Thomsen) · 2025-10-08 12:54

一些我用 Cinestill 胶片拍摄的光晕样本，如果能用上的话：

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/f/0f482e0f3e6d60436ca2844a0032caf9c5aae0a1_2_690x422.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/f/0f482e0f3e6d60436ca2844a0032caf9c5aae0a1_2_690x422.jpeg)

image1114×682 177 KB](/uploads/short-url/2bbO1qm16UWYGXkdkNNnPpQ3LDH.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/3/4367f4a00ba5993a36f18e8cca977b811f252e4c_2_690x300.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/3/4367f4a00ba5993a36f18e8cca977b811f252e4c_2_690x300.jpeg)

image1239×540 162 KB](/uploads/short-url/9CiIhKAXeO5IvkgUZf5wrz7j1kU.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/7/5731e769bfb732d68a683a285b1649d09a2a4752_2_689x476.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/7/5731e769bfb732d68a683a285b1649d09a2a4752_2_689x476.jpeg)

image1279×883 353 KB](/uploads/short-url/crmsr6C29fiyIoYlYWFPwpIkGps.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/e/4e3a1419ceea8d803672e14bfbf8012473788704_2_689x425.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/e/4e3a1419ceea8d803672e14bfbf8012473788704_2_689x425.jpeg)

image1371×846 475 KB](/uploads/short-url/ba1FS2gipmXd0RcIupiMDwbvbus.jpeg?dl=1)

---

## #388 **jo** (@hanatos) · 2025-10-08 13:02

谢谢！但看起来还是比我的衰减柔和一些：

[[![2025-10-08-145939_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/d/1d9d40812fc335fa44dd6260936466dcbfa5820f_2_690x546.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/d/1d9d40812fc335fa44dd6260936466dcbfa5820f_2_690x546.png)

2025-10-08-145939_hyprshot1975×1563 1.31 MB](/uploads/short-url/4dYKXAA0w92nRcoU4t2iWTwrfNJ.png?dl=1)

[[![2025-10-08-145932_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/a/ca480916e1fba372e24c373b031e87f079998341_2_690x546.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/a/ca480916e1fba372e24c373b031e87f079998341_2_690x546.png)

2025-10-08-145932_hyprshot1975×1563 1.32 MB](/uploads/short-url/sRsMDbVonIk9ZY5rdX3npm2zhcd.png?dl=1)

[[![2025-10-08-145814_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/9/e98110548f0ca9e8ebc20d0449b72b8a131b1763_2_690x546.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/9/e98110548f0ca9e8ebc20d0449b72b8a131b1763_2_690x546.png)

2025-10-08-145814_hyprshot1975×1563 1.16 MB](/uploads/short-url/xjFLE9rKAzbsXOJS0hRebgv7vH5.png?dl=1)

[[![2025-10-08-145810_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/b/0b43962aa4dbd1d7a67a67d77d2e7d371240317f_2_690x546.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/b/0b43962aa4dbd1d7a67a67d77d2e7d371240317f_2_690x546.png)

2025-10-08-145810_hyprshot1975×1563 1.15 MB](/uploads/short-url/1BE3so6yJrCoQO2rPdvSy5pMTnx.png?dl=1)

[[![2025-10-08-145739_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/3/939e9ad31d60be84202e7b4e7a86c7be15b3d0c0_2_690x546.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/3/939e9ad31d60be84202e7b4e7a86c7be15b3d0c0_2_690x546.png)

2025-10-08-145739_hyprshot1975×1563 1.1 MB](/uploads/short-url/l3TZPLCUAs85dFkZJaDd5UI7EVa.png?dl=1)

[[![2025-10-08-145734_hyprshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/1/a1b3cbc2cc8a5927b4d53e5924300bab65364953_2_690x546.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/1/a1b3cbc2cc8a5927b4d53e5924300bab65364953_2_690x546.png)

2025-10-08-145734_hyprshot1975×1563 1.09 MB](/uploads/short-url/n4u5c0Ecm98np6zd0l9j0LGOfTl.png?dl=1)

---

## #389 **** (@Toast) · 2025-10-08 16:41

看起来 git 仓库已经有一段时间没有更新了。原作者还在继续开发这个项目吗？还是说讨论已经转向其他项目对其进行整合/扩展了？

---

## #390 **** (@commutergraphics) · 2025-10-08 20:05

我想知道在这个工具中加入一个 RGB 基色风格的色彩调整器会不会有帮助？这样就不用知道该调整哪个模拟参数来修复奇怪的色彩了。

---

## #391 **** (@tankist02) · 2025-10-08 20:11

也许吧，但我更倾向于在一个地方调整所有参数——如果可能的话，就用 AgX 参数。

---

## #392 **** (@commutergraphics) · 2025-10-08 20:14

在 darktable 中的 agx（非胶片模拟器）里，加入了基色调整部分以便快速调整，和 sigmoid 一样。

---

## #393 **** (@tankist02) · 2025-10-08 20:17

我知道，我关注 DT 的开发，虽然我已经不再使用它了。对我来说太复杂了，我更喜欢 ART 那种能快速编辑并获得出色结果的方式。

---

## #394 **Todd Prior** (@priort) · 2025-10-08 20:22

我没用过，但 ART 里可能有一个基色 CTL……如果有人需要的话……ART 通过这些脚本增加了太多功能了……

---

## #395 **** (@tankist02) · 2025-10-08 20:26

ART 在通道混合器工具（色彩选项卡）中有全局基色校正。还可以通过颜色/色调校正中的 CTL 脚本相对色彩滤镜进行局部调整。

---

## #396 **** (@commutergraphics) · 2025-10-08 20:28

是的，它似乎从其他编辑器快速获得了新功能。

---

## #397 **Todd Prior** (@priort) · 2025-10-08 20:32

是的，我当时不在电脑前……我想这是我记得的那个：

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/6/9/69c0f69c287f2695bdac8bfadd7fd1e45b6b13fb.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/6/9/69c0f69c287f2695bdac8bfadd7fd1e45b6b13fb.png)

image302×436 10.7 KB](/uploads/short-url/f5xyuOH6jG2DogafUWsZbdOK2f1.png?dl=1)

---

## #398 **** (@tankist02) · 2025-10-08 20:37

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/e/cefecd85fea272e8d6991ed83140b12041f829ad.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/e/cefecd85fea272e8d6991ed83140b12041f829ad.png)

image478×849 34.5 KB](/uploads/short-url/txagPrVYRqBSbMEkOaX4llVAh1r.png?dl=1)

我试过这个做快速编辑，它确实可以在使用某些柯达胶片/纸张组合时抑制 AgX 中的红色。

---

## #399 **** (@Bruno) · 2025-10-13 17:33

嘿 [@arctic](/u/arctic)，我正在寻找一个可以写学士论文的课题，我真的很想写关于如何在数字领域正确模拟模拟胶片曝光的内容。在网上搜索时，我从未找到过已经做过这个的人。偶然发现了你的项目，被你开发的这个过程以及结果深深震撼了。这真的是独一无二的。

在玩了一段时间后，我想知道：如何保存/导出图像？

---

## #400 **Ted Cousins** (@cedric) · 2025-10-13 19:15

> **@Bruno** (帖子 #399):
> 我正在寻找一个可以写学士论文的课题，我真的很想写关于如何在数字领域正确模拟模拟胶片曝光的内容。在网上搜索时，我从未找到过已经做过这个的人。偶然发现了你的项目，被你开发的这个过程以及结果深深震撼了。这真的是独一无二的。
> 在玩了一段时间后，我想知道：如何保存/导出图像？

RawTherapee 内置了胶片模拟功能，这正是你想要的。

它使用一种叫做 HaldCLUT 的 PNG 图像格式，你可以从网上下载更多并添加到 RT 中。

一些资源在这里：[Pat David: Film Emulation in RawTherapee](https://patdavid.net/2015/03/film-emulation-in-rawtherapee/)

把它们存放在这里：

C:\Users<用户名>\AppData\Local\RawTherapee5\HaldCLUT

希望这有帮助……

---

## #401 **** (@mikae1) · 2025-10-13 19:30

> **@Bruno** (帖子 #399):
> 在玩了一段时间后，我想知道：如何保存/导出图像？

文件

[![:arrow_right:](https://discuss.pixls.us/images/emoji/apple/arrow_right.png?v=12)](https://discuss.pixls.us/images/emoji/apple/arrow_right.png?v=12)

保存选定图层…

你也可以使用 [vkdt](https://github.com/hanatos/vkdt) 来访问 [@arctic](/u/arctic) 作品的另一个实现。

> **@Bruno** (帖子 #399):
> 被这个以及结果深深震撼了。这真的是独一无二的。

我同意。这确实是独一无二的。

---

## #402 **おばけちゃん** (@ghost) · 2025-10-14 00:04

首先，衷心感谢参与这个项目的所有人。

其次，这并非批评，但你的研究确实不够充分。

这项技术本身并非独一无二——以前已经被多次尝试过。从核心上讲，这种方法不仅限于胶片；它本质上是一种重拍（虚拟相机）模拟。

这个项目的"独特"和宝贵之处在于，过程中相当大的一部分内容被公开了。当然，并非所有内容都公开了。

以下是两个基于光谱的胶片模拟工作，其中至少有一些线索是公开的：

1. "Film Simulation for Video Games（SIGGRAPH 2010）" by tri-Ace Inc.

这是为一个日本游戏项目开发的，基于胶片规格表进行胶片模拟。

[https://research.tri-ace.com/](https://research.tri-ace.com/)

- "Film Simulation for Video Games" SIGGRAPH 2010
- "Physically Based Lighting for Rendering" CEDEC 2010
- "Renderist no tame no camera (kougaku) riron to post effect（面向渲染师的相机（光学）理论与后期效果）" CEDEC 2007

<ol start="2">
<li>"C-105 Vision (FilmLight)" by Daniele Siragusano</li>
</ol>

这是为 TCAMv2 和 TCAMv3 开发的。

相关的还有"Smooth Spectra (SIGGRAPH 2022)"：

- [https://www.youtube.com/watch?v=JtSJr-je8qY&t=8220s](https://www.youtube.com/watch?v=JtSJr-je8qY&t=8220s)
- [https://blog.selfshadow.com/publications/s2022-spectral-course/s2022_spectral_course_notes.pdf](https://blog.selfshadow.com/publications/s2022-spectral-course/s2022_spectral_course_notes.pdf)

在每个例子中，这些方法都不能完美再现胶片相机拍摄的效果。它们可以朝这个目标努力，但要达到一个完整的高保真模拟，仍缺少很多信息。

在当前实现中，通过 GUI 保存的图层以 8 位输出导出。

如前所述，你可以使用 vkdt，修改实验性 GUI 以在保存图层时写入非 8 位输出，或者直接调用 Python 程序中定义的函数来处理图像。

---

## #403 **Mica** (@paperdigits) · 2025-10-14 01:54

你好 [@ghost](/u/ghost)，欢迎来到论坛。

> **@ghost** (帖子 #402):
> 其次，这并非批评，但你的研究确实不够充分。

那么研究和实现中缺乏的是什么？你能详细说明一下吗？

---

## #404 **おばけちゃん** (@ghost) · 2025-10-14 02:44

抱歉，我忘了附上 C-105 Vision 的视频链接。

就是这个：[Colour Online: Creating the look for Netflix's 'Tribes of Europa'](https://vimeo.com/521822858#chapter=2896841)

---

## #405 **おばけちゃん** (@ghost) · 2025-10-14 02:59

谢谢——我的重点是针对 Bruno 声称的"我从未找到过已经做过这个的人"，尽管他正在计划写一篇论文。如果我的评论违反了论坛政策或有不妥之处，我表示歉意。

---

## #406 **Mica** (@paperdigits) · 2025-10-14 03:01

> **@ghost** (帖子 #405):
> 如果我的评论违反了论坛政策或有不妥之处，我表示歉意。

没有，看起来是很有趣的阅读材料，谢谢澄清！

---

## #407 **István Kovács** (@kofa) · 2025-10-14 06:49

这不是添加基色的原因。基色是**核心**功能；曲线的重要性较低。但不要将 dt agx 扯入无关的讨论。

---

## #408 **** (@Bruno) · 2025-10-15 08:42

你好 [@ghost](/u/ghost)，

我的措辞有点误导，我的意思是找不到一个公开可用且能够工作的工具，试图模拟彩色负片胶片层的曝光过程然后打印/扫描。也就是从原始图像到最终模拟的完整流程。当然，这个领域确实有研究，也有开发过类似工具，只是用途略有不同。

---

## #409 **** (@Bruno) · 2025-10-15 08:44

谢谢！

---

## #410 **Andrea** (@arctic) · 2025-10-15 20:44

大家好，很抱歉长期缺席。生活有点让我吃不消，但我正在慢慢赶上，并计划重新进入状态

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

并了解我错过了什么。

我同意 [@ghost](/u/ghost) 的观点，这里的工作不应被视为完全新颖。我的意思是，核心知识已经被消化得如此透彻，以至于有整本书都在讲这个，包括我大部分工作所依据的书籍，例如 Digital Color Management by Giorgianni Madden 2008 Wiley。

而且可能有无数的类似尝试。

我相信新颖的方面是：

- 使用了 [@hanatos](/u/hanatos) 的前沿光谱升采样器
- 使用仅基于数据手册的光谱数据作为输入，以及微调配置文件以确保曝光时灰度输出稳定的方法
- 实现合理饱和度的简单耦合剂抑制模型
- 多层颗粒模型

总的来说，这个项目最初是一个颗粒模拟，最终找到了作为完整摄影过程模型的最佳实现方式。所以我同意这个项目重新实现了大量常识性的摄影知识（因为轮子总是不厌其烦地被重新发明

[![:stuck_out_tongue:](https://discuss.pixls.us/images/emoji/apple/stuck_out_tongue.png?v=12)](https://discuss.pixls.us/images/emoji/apple/stuck_out_tongue.png?v=12)

，是它们不是我们）

[@Bruno](/u/bruno) 如果你想聊聊或者需要一些意见/帮助，请告诉我，想到你打算写关于这些主题的论文，真有趣。我甚至有点嫉妒

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

---

## #411 **jo** (@hanatos) · 2025-10-16 06:38

很高兴看到你回来了。很遗憾听说你经历了一段艰难时期，希望未来一切顺利。

我相信 [@ghost](/u/ghost) 指的是 [@Bruno](/u/bruno) 关于先前工作研究的评论，假设这是在谈论文献引用。而且研究本身就是要勤勉地拼凑微小的碎片，直到它们成为新的东西。我不会贬低你的工作。我们中没有人能在你不在的时候引入新的胶片类型，这可不*那么*简单。

---

## #412 **** (@Toast) · 2025-10-22 09:32

我刚刚阅读了 [Digitizing film using DSLR and RGB LED lights - #22 by damirk](https://discuss.pixls.us/t/digitizing-film-using-dslr-and-rgb-led-lights/18825/22)，想知道这种方法是否能与这个软件很好地融合。然后我在想，如果有一个具有多种不同光谱 LED 的光源，我们可以循环使用来构建一个不仅仅是 RGB 输入光谱的源图像，那会不会有价值？

LED 很小，很容易实现不同灯泡的密集阵列。它们可以通过软件控制。我在想这样一个流程：

1. 在没有底片的情况下，用每种颜色的 LED 拍摄一张图像。用以计算传感器+拜耳滤镜的原始响应，并修复背光亮度均匀性的任何不一致。同时根据需要校准光线亮度或曝光。
2. 放置胶片后，用每种颜色的光线拍摄一张图像，用第 1 步获得的信息校正捕获的数据。
3. 生成光谱图像并导入底片处理流程。

这一切都必须自动化，否则会太繁琐，所以在使用时，只需按设置按钮（无底片），然后对每张底片按拍摄按钮。

这样会得到有意义更好的结果吗？

---

## #413 **jo** (@hanatos) · 2025-10-22 09:59

> **@Toast** (帖子 #412):
> 这样会得到有意义更好的结果吗？

可能吧！没有什么比真实数据更好的了……在你开始构建硬件之前，我建议先用现有数据验证一些整体思路。可以在这里搜索：[Hyperspectral Imaging Open Ecosystem](https://hsi.yale.edu/resource/103)，那里有高光谱图像的链接，比如 [Spectral scene database · ISET/isetcam Wiki · GitHub](https://github.com/ISET/isetcam/wiki/Spectral-scene-database)，这些可能是胶片模拟的绝佳输入。最好结合标准格式的光谱图像，例如 [https://cgg.mff.cuni.cz/wp-content/uploads/2021/06/jcgt_2021_spectral_exr.pdf](https://cgg.mff.cuni.cz/wp-content/uploads/2021/06/jcgt_2021_spectral_exr.pdf) 或 [Compression of Spectral Images using Spectral JPEG XL](https://momentsingraphics.de/JCGT2025.html)

---

## #414 **** (@Toast) · 2025-10-22 18:55

哇，谢谢，这些太棒了。它们也凸显了一个问题——虽然我对硬件很熟悉，但我的数学和软件可能有点欠缺！不过我认为这个想法至少在物理上是可行的。

---

## #415 **Anna** (@betazoid) · 2025-10-25 12:33

在 ART 和 vkdt 的实现中，有推荐的工作流程吗？我的意思是，在 agxemulsion 内部和外部都有做类似事情的滑块，例如调整亮度——是建议先使用 art/vkdt 工具，还是只在 agxemulsion 外部做一个宽泛的编辑，然后在 agxemulsion 内部做剩下的？

我经常遇到这种情况：我关掉曲线/色调映射，然后调整亮度，再打开 agxemulsion，然后照片突然变得很亮或很暗——这种情况下，是建议用 agxemulsion 的滑块修复，还是用 ART/vkdt 的滑块？

---

## #416 **jo** (@hanatos) · 2025-10-27 08:43

有什么理由要先编辑图像再打开胶片模拟？我把它看作是一种显示变换，我不会在没有胶片曲线的情况下尝试编辑图像（除非是为 HDR 显示器做母版制作）。

使用胶片/相纸曝光会产生非常不同的结果，要根据艺术意图来使用。胶片曝光等同于在前面模块中曝光输入。

---

## #417 **Daniel Rheaume** (@RTLdan) · 2025-10-29 23:38

哇，多么了不起的项目！

我是从 Nico 在 Demystify color 那里了解到这个项目的。我相信你会看到更多人从那里过来！

总之，希望能得到一些建议！

当我在 DaVinci Resolve 中创建并使用负片和打印 LUT 的组合时，我基本上是这样设置节点结构的：

IDT（到 DWG/DI）→ 负片 → 根据需要添加配光 → 打印胶片 → ODT（R709/G2.4）

我马上注意到对比度相当极端，这使得我需要在流程中的某个地方进行对比度调整。

如果我在负片之前放一个对比度节点，我担心我会向它发送一个它不期望的 Log 图像。我通常在那个阶段需要将对比度降低约 50%。另外，我试过在负片和打印节点之间的"配光"部分中放置一个对比度节点。这样可行，但似乎有时会引起强烈的色相偏移。我不确定这对配光过程是否正常，还是说我搞乱了打印 LUT 的预期输入，进一步偏离了模拟的预期算法。最后，我在打印模拟之后做了对比度调整。这看起来最自然，因为我们本质上是在给打印后的图像调色，但它会使部分图像因为已经被曲线的趾部/肩部影响而出现裁切/压缩，所以这不是一个理想的整体对比度保持方式，它更适合作为后期调色的微调。

我是不是漏掉了什么？还是以上都需要结合？

不确定这里是否有什么我没注意到的意图，关于每个 LUT 接收什么输入。

非常感谢大家的帮助！

此致，

-Daniel

---

## #418 **Mica** (@paperdigits) · 2025-10-30 03:04

> **@RTLdan** (帖子 #417):
> 哇，多么了不起的项目！
> 我是从 Nico 在 Demystify color 那里了解到这个项目的。我相信你会看到更多人从那里过来！

你好 [@RTLdan](/u/rtldan)，欢迎！这里讨论了好几个软件，你能告诉我你指的是哪一个，并给我们链接一下提到该软件的教程吗？

谢谢！

---

## #419 **Daniel Rheaume** (@RTLdan) · 2025-10-30 04:04

哦，我的错！抱歉没说清楚——我正在试用 Jan Lohse 的 Spectral Film Lut（[GitHub - JanLohse/spectral_film_lut: Generate LUT for film emulation based on film datasheets.](https://github.com/JanLohse/spectral_film_lut)）。

除了那个 GitHub 上的 README，我没有任何教程！

另外，提前道歉，我之前已经读了很多这个帖子的内容，但还没看完。所以如果已经讨论过了，请见谅！

希望这有帮助，谢谢！

-Daniel

---

## #420 **Mica** (@paperdigits) · 2025-10-30 04:54

哦，那看起来是个很酷的项目，但我不认为这个帖子是关于那个软件的，而是关于一个叫做 agx-emulsion 的不同软件。

---

## #421 **jo** (@hanatos) · 2025-10-30 08:11

> **@RTLdan** (帖子 #419):
> 我正在试用 Jan Lohse 的 Spectral Film Lut

哦不错，还有黑白胶片！

---

## #422 **Olli** (@okke) · 2025-10-30 09:40

这也是一个有趣的项目，即使是不同的。但这个问题仍然有道理，对比度可能有点过大。在使用 vkdt 实现时，我经常需要提高曝光，尝试调整参数，而且经常还需要在 filmsim 节点之前（局部或全局）提亮阴影。

---

## #423 **jo** (@hanatos) · 2025-10-30 09:56

也许发一个具体的例子，比如 playraw？

---

## #424 **** (@mikae1) · 2025-10-30 12:40

> **@RTLdan** (帖子 #417):
> 我是从 Nico 在 Demystify color 那里了解到这个项目的。我相信你会看到更多人从那里过来！

酷。

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

他在哪里提到了 agx-emulsion？我在[他的频道](https://www.youtube.com/@demystifycolor/videos)上没找到。

> **@RTLdan** (帖子 #419):
> 我正在试用 Jan Lohse 的 Spectral Film Lut（GitHub - JanLohse/spectral_film_lut: Generate LUT for film emulation based on film datasheets.）。

有意思！一个 Python 项目。我想知道构建一个 .AppImage 有多难。

我知道这不是 darktable 的帖子，但遗憾的是 darktable 中的 LUT 3D 模块[相当有限](https://discuss.pixls.us/t/linear-to-log-for-film-emulation-in-darktable-are-1d-luts-possible/40847)。但也许可以在 [Spectral Film LUT](https://github.com/JanLohse/spectral_film_lut) 中创建可用于 darktable 的 LUT？

另外，darktable 中的颗粒模块只有单色，而且颗粒是在插值前应用的。

---

## #426 **Olli** (@okke) · 2025-10-31 09:06

我有时间的时候会找一些。不过通常情况是这样的，例如部分在阴影中的人脸变得太暗，所以我必须找其他方法。

---

## #427 **jo** (@hanatos) · 2025-10-31 10:54

好的，谢谢。如果你觉得更方便的话，也可以私下分享给我。我不是卖图片的……

有时候这是关于平衡打印和胶片曝光的问题，有时候我发现自己只是太习惯数字动态范围了，以至于胶片（模拟）显得有限。但我想确保我准确理解你的问题。

---

## #428 **** (@niklasiivari) · 2025-10-31 18:30

我发现*分区*模块在我觉得阴影太暗时非常有帮助。与曲线加绘制蒙版相比，它通常能带来更自然的结果。

---

## #429 **nosle** (@nosle) · 2025-10-31 19:29

所以继续上面的色偏等讨论。最近 ART 中的光谱胶片模拟让我有机会进行比较。请注意，我不期望效果相同，但我认为它很好地说明了色偏问题。另外，我不记得我最初测试 AGX filmsim 时有这么严重的色偏。

vkdt

[[![2025-10-31-202514_1193x1009_scrot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/6/f6acec26c0e3f77c841aaff51075bc13821235c2_2_690x583.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/6/f6acec26c0e3f77c841aaff51075bc13821235c2_2_690x583.png)

2025-10-31-202514_1193x1009_scrot1193×1009 1.09 MB](/uploads/short-url/zcbWqBIAwaEmm1ss4g4ekBn94hc.png?dl=1)

ART

[[![2025-10-31-203020_1372x817_scrot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/d/7dc14f71757b6a0c96b260f85ee0dff6f1d83057_2_690x410.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/d/7dc14f71757b6a0c96b260f85ee0dff6f1d83057_2_690x410.png)

2025-10-31-203020_1372x817_scrot1372×817 1.15 MB](/uploads/short-url/hWtQEAbkOeeC2pwWW2V7LkPOWt9.png?dl=1)

后面这个效果才是我对 Portra 160 的期待，因为我也拍过一些。

---

## #430 **jo** (@hanatos) · 2025-11-01 18:37

优化器中可能存在问题，影响打印时的白平衡匹配。现在 <s>hyprland</s> libdecor 里有一个 bug，所以右边的图像被拉伸了。

左：agx-emulsion 原始 Python，右：vkdt（portra 160, supra endura）。

[[![20251101_19h32m05s_grim](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/3/d39f481fc928fa4bb5b611c695031996687cf138_2_690x397.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/3/d39f481fc928fa4bb5b611c695031996687cf138_2_690x397.png)

20251101_19h32m05s_grim2175×1254 2.32 MB](/uploads/short-url/uc60mkf3VSDqv9zlMrCvXPCiaqk.png?dl=1)

我需要确保它现在按预期工作，然后重新运行白平衡脚本。

---

## #431 **Olli** (@okke) · 2025-11-02 08:31

现在重新看我之前遇到问题的照片，我想我知道主要问题是什么了：我在和 darktable 对比，而 darktable 会自动添加一些曝光补偿并抵消曝光补偿。当禁用曝光补偿并将 sigmoid 对比度设置为 2.0 时，情况就非常相似了。vkdt 的默认色调曲线相比之下对比度太低，以至于曝光差异不那么明显。胶片模拟的动态范围/对比度确实有点限制，所以经常需要使用选择性曝光或分区功能。或者调整胶片模拟中的参数，但这些参数不是正交的，需要反复调整（也是技术问题）。

很高兴听到白平衡可能会有变化，我也一直在处理这个问题。我会检查最新更改，看看是否有需要 playraw 的情况（由于对比度或白平衡问题）。

---

## #432 **Anna** (@betazoid) · 2025-11-02 09:22

我想我确实在这里提过白平衡的 bug，是吧？

---

## #433 **** (@Thomsen) · 2025-11-02 13:17

我也遇到过在 VKDT 中管理对比度的问题。降低对比度总是比增加对比度更难做到令人满意。从你的例子来看，VKDT 的默认对比度曲线似乎比 agx 更强。

> **@hanatos** (帖子 #430):
> 20251101_19h32m05s_grim2175×1254 2.32 MB
> 20251101_19h32m05s_grim2175×1254 2.32 MB

除了默认对比度之外，我记得也读到过 VKDT 中遗漏了 AGX 的预闪光方法。这似乎是管理高对比度图像的一个好方法。也许值得重新审视？

> **@arctic** (帖子 #15):
> 关于预闪光，我有一个很好的例子来自 Play Raw 的高对比度图像，来自 @Popanz。
> 相纸的宽容度有限，对比度是预设的，而负片可以捕捉非常大的动态范围（轻松超过 10 档）。预闪光是一种简单的打印过程技巧，用于保留一些高光细节。相纸在负片投影前用一些光线预闪光，即使其变得更灰，压低高光（看看这个视频中的真实例子 https://www.youtube.com/watch?v=lcx4ag7iygI）。代价是对比度和饱和度降低。
> garden_pro_400h_crystal_archive_typeii_1.0cpl_0preflash_0Y0M_015pe1999×1334 5.14 MB
> garden_pro_400h_crystal_archive_typeii_1.0cpl_001preflash_0Y0M_015pe1999×1334 5.07 MB

---

## #434 **jo** (@hanatos) · 2025-11-03 07:57

> **@okke** (帖子 #431):
> 我会检查最新更改

现在已经推送了：

[[![grim](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/2/d290d95e67db9420cef8e8d0717130875bfe06f8_2_690x360.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/2/d290d95e67db9420cef8e8d0717130875bfe06f8_2_690x360.png)

grim3046×1590 2.64 MB](/uploads/short-url/u2KBBAwSoUdMMXaWXu0OqP0JMTK.png?dl=1)

> **@betazoid** (帖子 #432):
> 我想我确实在这里提过白平衡的 bug，是吧？

我不记得了。但如果你没有用图片展示，我可能确实会忽略文字。我是个视觉型的人……

> **@Thomsen** (帖子 #433):
> 除了默认对比度之外，我记得也读到过 VKDT 中遗漏了 AGX 的预闪光方法。这似乎是管理高对比度图像的一个好方法。也许值得重新审视？

对，当然不是在范围之外

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

不过不确定对比度差异从何而来。两幅图像中没有其他曲线参与。也许只是曝光上的微小差异将数值推到了胶片响应曲线的不同斜率上。

---

## #435 **Daniel Rheaume** (@RTLdan) · 2025-11-03 20:05

抱歉回复晚了！

Demystify Color 的参考可能是在付费墙后面。我是订阅用户，所以我看不到哪些是免费的哪些是付费的。他主要是作为一名 Resolve 调色师来探讨的。这个系列还在进行中。AGX Emulsion 只在第 1 部分被简要提及，但他将 AGX Emulsion 和 Spectral Film LUT 与新的 Genesis 插件进行了比较，后者有意对其工作原理保密。我猜测 Genesis 也在使用光谱方法。

关于我的对比度问题，部分原因可能是我测试的胶片类型（5207/2383）。其他胶片感觉更容易控制。尽管如此，整体对比度对我来说仍然偏高。到目前为止我得到的最佳效果来自于模拟前的一些塑形，以及一个模拟后的节点来控制打印对比度。模拟后对比度调整的缺点在于，一旦高光/阴影通过 LUT 处理后，那个后节点很难拉回阴影或高光细节。正如你所料，这就像试图撤销打印。但如果我在模拟前放太多对比度调整，我又担心会过度影响负片胶片模拟期望的输入，使其显得苍白无力。

有两个问题我仍然困惑——

1. AGX Emulsion 在 Resolve 视频工作流中的应用：
   有没有人真正从 AGX Emulsion 导出过 LUT？我试过用 ChatGPT 和命令行来实现，但遇到了瓶颈。我不是程序员，但我可以在指导下使用命令行工具。以目前的实现，LUT 导出是否可行？理想情况下，我希望有单独的负片和打印阶段 LUT，就像 Spectral Film Luts 那样，还是说这超出了当前的范围？我非常喜欢 AGX 的精细程度，看起来它比 SFL 目前更高级。

2. Resolve 中胶片模拟的色调映射预期
   在 Resolve 中，我将相机 → DWG/DI 进行处理，然后 DWG/DI → 显示。我的监看设置为 Rec.709 / gamma 2.4，已校准，但亮度设置为 200 尼特，因为我并不是经常在暗室工作。色彩空间变换工具提供了几种 log→显示 的色调映射选项。ChatGPT 建议明确设置 100 尼特的最大输入映射，因为它假设这符合胶片模拟的意图。我已经将 Spectral Film LUTs 的输出设置为 DWG/DI，但它们内部对场景 vs 显示映射有一些假设，而且据我所知没有文档说明。我可能会尽快联系开发者。

然而，总的来说，有人知道这些模拟在显示参考色调映射方面期望什么吗？我们应该以严格的 100 尼特假设为目标，还是算法期望其他设置（尤其是在 200 尼特监看时）？

再次感谢大家开发这个很棒的项目！

---

## #436 **** (@mikae1) · 2025-11-03 23:09

> **@RTLdan** (帖子 #435):
> LUT 导出是否可行？

在 agx-emulsion 中打开一个 Hald CLUT 身份文件，直接处理该文件并导出。然后你可以将 Hald CLUT 转换为 cube。以前有一个脚本可以实现：[https://github.com/sobotka/hald2cube](https://github.com/sobotka/hald2cube)

也许还有其他选择。如果没有，也许那个 LLM 愿意帮你。

这里有一个身份文件：[链接](https://rawpedia.rawtherapee.com/index.php?title=File:Hald_CLUT_Identity_12.png)

但你可能想生成一个自己的身份文件，使用比 sRGB 更宽的色彩空间。根据 [RawPedia](https://rawpedia.rawtherapee.com/Film_Simulation)，sRGB 的做法如下：

```
magick hald:12 -depth 16 -colorspace sRGB hald12_16bit.tif

```

我把 `convert` 换成了 `magick`，因为现在是这么用的。

---

## #437 **Daniel Rheaume** (@RTLdan) · 2025-11-03 23:15

谢谢！这个想法非常有趣！我得研究一下 hald 图像的使用！

---

## #438 **jo** (@hanatos) · 2025-11-04 07:48

……补充一下，请记住要禁用自动曝光/眩光/光晕/耦合剂，因为这些不是逐像素处理的，而是至少在局部范围内起作用。

---

## #439 **** (@Christian-B) · 2025-11-04 08:30

> **@mikae1** (帖子 #436):
> 然后你可以将 Hald CLUT 转换为 cube。以前有一个脚本可以实现：https://github.com/sobotka/hald2cube

这个链接好像失效了，但这里有另一篇有趣的文章。
<aside class="onebox allowlistedgeneric" data-onebox-src="https://marcrphoto.wordpress.com/2025/08/11/diy-png-to-cube-converter/">
 <header class="source">


[![图片448](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/d/add855b0e0c036829cc730447c58ba4d8f194197.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/d/add855b0e0c036829cc730447c58ba4d8f194197.png)

 [Open Source Photography – 11 Aug 25](https://marcrphoto.wordpress.com/2025/08/11/diy-png-to-cube-converter/)
 </header>

 <article class="onebox-body">


[![图片449](https://d2x313g9lpht1q.cloudfront.net/original/3X/7/f/7f8512d58bcca671a41d92d15a7cdf31f348e359.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/7/f/7f8512d58bcca671a41d92d15a7cdf31f348e359.jpeg)

### [DIY PNG to Cube Converter](https://marcrphoto.wordpress.com/2025/08/11/diy-png-to-cube-converter/)


5 minutes read time 🎬 From PNG to .CUBE – Take Full Control of Your Film Simulations So, you've created a killer film look in RawTherapee, ART or anything else that spits out PNGs. You're happy. It…

 </article>











</aside>

来自布鲁塞尔的问候，

Christian

---

## #440 **Todd Prior** (@priort) · 2025-11-04 15:13

<aside class="onebox allowlistedgeneric" data-onebox-src="https://www.color.io/free-online-lut-converter">
 <header class="source">


[![图片450](https://d2x313g9lpht1q.cloudfront.net/original/3X/6/f/6f49657a50f195fc9b751181382af7bcaac6db3d.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/6/f/6f49657a50f195fc9b751181382af7bcaac6db3d.png)

 [color.io](https://www.color.io/free-online-lut-converter)
 </header>

 <article class="onebox-body">


[![图片451](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/4/a4da2eb2e46096b7f7aad08497f1254b6e09f8af_2_690x430.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/4/a4da2eb2e46096b7f7aad08497f1254b6e09f8af_2_690x430.jpeg)

### [Free Online LUT Converter And Previewer | Color.io](https://www.color.io/free-online-lut-converter)


Preview and convert 3D LUTs for most applications, cameras, game engines and more with the free color.io 3D LUT converter that runs directly in your browser.

 </article>











</aside>

---

## #441 **Ryan Cara** (@Ryan_Cara) · 2025-11-08 03:14

> **@mikae1** (帖子 #436):
> 什么

希望能有更新！HALD 的色彩空间让我很困惑。我一直在尝试将一些 AGX emulsion 的效果转换为 LUT，但一直不太成功。

---

## #442 **Yogansh Bhatt** (@Yogansh_Bhatt) · 2025-12-18 14:40

不仅是摄影，因为 VKDT 支持 MCRAW，我和其他一些人开始发现你的项目有巨大的价值！它令人着迷，几乎感觉像魔法……现在已经上瘾了！

非常感谢你创造了这个！

---

## #444 **Aurelien** (@Aurelien_05) · 2026-02-22 14:52

大家好，我在搜索胶片模拟文章时偶然发现了这个帖子。非常感谢你创造了这个；最终效果非常漂亮，与我用过的其他胶片模拟应用截然不同。和这里的许多成员一样，我希望你能继续投入时间进一步完善这个项目。

过去一周，我阅读了本主题中 400 多条评论，并用自己的一些图像进行了实验。我是 Mac 用户，对 Python 完全不了解。这也是我第一次安装 Darktable 和 ART——正是在阅读此帖后专门为了尝试 AgX 模拟而安装的。我查看了其他 Mac 用户的评论，但仍有一些未解答的问题，希望能得到创建者和社区的帮助。

1. 首先，我想确认输入图像所需的状态。根据我的了解，它应该是线性 ProPhoto 或 Rec 2020 色彩空间中的 16-32 位 TIFF 或 EXR。我的理解是否正确，即不应应用 Sigmoid、Filmic 或 Base-curve 变换？

[[![save darkable](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/9/9908db491e13e072435af8535c598e6592da7094_2_690x316.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/9/9908db491e13e072435af8535c598e6592da7094_2_690x316.jpeg)

save darkable2048×939 295 KB](/uploads/short-url/lPO1K6zY8yEIRTUyjT5Xd1unNVW.jpeg?dl=1)

> **@ZeroEcks** (帖子 #115):
> 我注意到的唯一突出问题是，在 macOS 上使用 agx_emulsion GUI 时，由于没有色彩管理，保存图层时的伽马/对比度与查看窗口相比差异很大。不幸的是，这有点阻碍实际使用，但通过之后调整黑点和对比度可以在一定程度上修复。

> **@NateWeatherly** (帖子 #56):
> 在 Mac 上，只要有一个 ImageP3 或 DisplayP3 输出 ICC 配置文件，就能非常接近色彩管理的预览效果。

> **@arctic** (帖子 #122):
> 而且我并不是特别想把这个作为最终解决方案。我认为其他软件（vkdt, darktable, rawtherapee, art…）有更好的人机界面，所以可能不需要重新构建一切。我把它看作一个技术演示，我非常擅长在这个基础上进行修改，并在细节上走极端。如果它要成为实际工作的可行解决方案，我将来可能会做更好的东西。目前我的重点一直是引擎和"外观"。但谢谢你的批评！我记在心里了。

关于我在 Mac 上的设置：我在 Napari 中使用"输出色彩空间 = Display P3 或 DCI P3"。通过"保存图层"保存的图像通常与 Napari 查看器中显示的相比明显去饱和。我也非常喜欢图层控制中的滑块——它们在预览中产生了很好的效果，对于调整对比度和伽马非常方便。但是，当我"保存图层"时，这些调整并未应用到最终图像中；它们似乎只影响 Napari 界面。

有人找到过修复方法吗？我为此困扰了好几天，因为 Napari 中的颜色看起来完美，但导出的结果完全不同。这是 Mac 特有的问题，还是 Windows 用户也会遇到？这可能是我安装方面的错误吗？我该如何修复？

[[![run](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/a/0a1d6efad388872b34d9363cce3901b4200e13c2_2_690x578.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/a/0a1d6efad388872b34d9363cce3901b4200e13c2_2_690x578.jpeg)

run2048×1718 557 KB](/uploads/short-url/1rtPOvgCRQdqA8bjXHDLmruqW8W.jpeg?dl=1)

[[![export](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/a/ca3b2c010e9885be7f600603a854962407ec88f8_2_690x399.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/a/ca3b2c010e9885be7f600603a854962407ec88f8_2_690x399.jpeg)

export2048×1185 840 KB](/uploads/short-url/sR1dTUz0kuhWGXWW5nNHuVl5AXm.jpeg?dl=1)

<ol start="3">
<li>从 Darktable 导出图像并通过文件选择器加载到 Napari 后，图像看起来非常不同。它显得对比度极高，阴影被压缩，高光过曝。我不确定这是否会影响点击"运行"后的最终结果。这是正常行为，还是我做错了什么？</li>
</ol>

[[![raw export Darkable](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/2/b25d04a4bd1db08d3bd658621fd562b85ee32daa_2_690x511.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/2/b25d04a4bd1db08d3bd658621fd562b85ee32daa_2_690x511.jpeg)

raw export Darkable2050×1520 760 KB](/uploads/short-url/prShn1sgg2M7MCdGkLob0BN8EXg.jpeg?dl=1)

[[![load pics](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/b/7b79f05034460a70d4d6691d663594c0566ea949_2_690x704.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/b/7b79f05034460a70d4d6691d663594c0566ea949_2_690x704.jpeg)

load pics2502×2556 789 KB](/uploads/short-url/hCjYQppsSbtA4ZImcS8eJnIJRMt.jpeg?dl=1)

<ol start="4">
<li>我注意到人们经常将 AgX Emulsion 与 vkdt 或 ART 一起使用。我能否直接对 RAW 文件使用它，还是需要先将 RAW 导出为线性 ProPhoto RGB 文件？

我一直在尝试让"agx_emulsion"在 ART 中工作，已经折腾了好几天。虽然 ART 中出现了该选项，但效果似乎不起作用——移动滑块或更改胶片模拟对图像没有产生任何视觉变化。有 Mac 用户成功解决过这个问题吗？如果能有一个简要指南，我将不胜感激。</li>
</ol>

[[![Screenshot 2026-02-22 at 21.50.43](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/8/68ddcfc931b5553fb726ca177b953de6a07bc84d_2_690x453.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/8/68ddcfc931b5553fb726ca177b953de6a07bc84d_2_690x453.png)

Screenshot 2026-02-22 at 21.50.433154×2074 2.34 MB](/uploads/short-url/eXGSWE769ITNFwjesuFjiPLg5lj.png?dl=1)

<ol start="5">
<li>我的主要工作流程一直在 Capture One 或 Lightroom Classic 中。有没有办法从 C1 或 LrC 导出带有线性 ProPhoto RGB 配置文件的文件，并且与 Darktable 的输出等效？</li>
</ol>

提前感谢您的帮助！

---

## #445 **** (@tankist02) · 2026-02-22 22:16

在最后一张截图中，颜色/色调校正工具没有打开（名称左侧的图标）。

---

## #446 **** (@lambda) · 2026-02-22 22:46

这真是太棒了！希望它能成为 Darktable 的主线功能。

---

## #447 **Georg N** (@geni1105) · 2026-02-23 10:59

在 vkdt 中，AgX Emulsion 作为"filmsim"节点内置，参见 [vkdt: filmsim: artic's sophisticated spectral analog film simulation saturation with DIR couplers the filmsim data](https://jo.dreggn.org/vkdt/src/pipe/modules/filmsim/readme.html)

它可以直接应用于原始图像，事实上这也是默认的使用方式，因为它取代了 filmcurv 模块。
</parameter>

## #448 **None** (@sahuaro.senorita) · 2026-02-23 16:41

> **@Aurelien_05** (帖子 #444):
> 我是一个 Mac 用户，对 Python 完全没有了解。

那咱们就是两个人了！你是怎么在 Mac 上跑起来的？几周前我花了好几天试着让它运行并尽力排查问题，但后来放弃了，因为新版本的 macOS 似乎破坏了兼容性。

---

## #449 **Aurelien** (@Aurelien_05) · 2026-02-24 02:35

我在初始安装时遇到了一些错误。最后我把终端里的错误信息复制粘贴到 ChatGPT 里找解决方案。

---

## #451 **** (@Cristian) · 2026-02-24 10:10

我最近几天用了 agx-emulsion，我的结论是：这太出色了，非常棒！这是我用过的最好的胶片模拟应用，继续加油！在我尝试过那么多预设、LUT 和其他软件（比如 DXO Filmpack）之后，这是我最喜欢的。我只希望它将来能作为 Darktable 的一个模块被集成进去。

---

## #452 **** (@mikae1) · 2026-02-28 15:24

> **@Cristian** (帖子 #451):
> 这太出色了，非常棒！这是我用过的最好的胶片模拟应用

我完全同意。对于静态摄影来说，它绝对是*最棒*的。

> **@Cristian** (帖子 #451):
> 继续加油。

这个项目上次更新是 11 个月前了，所以我不抱太大希望。我不知道 [@agriggio](/u/agriggio) 和 [@hanatos](/u/hanatos) 是否还在为 ART 和 vkdt 继续开发。

> **@Cristian** (帖子 #451):
> 我只希望它将来能作为 Darktable 的一个模块被集成进去。

同感！这是个性能问题，但 [@hanatos](/u/hanatos) 已经证明 GPU 加速对性能*大有*帮助。在 vkdt 中运行非常流畅！

---

## #453 **jo** (@hanatos) · 2026-02-28 15:46

……嗯，我还在 vkdt 中微调一些东西，比如更可控的耦合剂和光晕。仍然缺少一些功能（主要可能是预闪）。

vkdt 的 GPU 管线与 darktable 的截然不同。抱歉我以前把 dt 的管线设计成那样，当时觉得是个好主意。即使不考虑所有 CPU 回退/复制代码，仍然存在大量 CPU 同步以及整体上太多没有为真正快速执行/新硬件而设计的地方。不确定它还能有多流畅，这是一场注定失败的战斗。好的一面是，它对当年的硬件兼容性很好，而且 CPU 代码路径让贡献者更容易参与。

---

## #455 **Yogansh Bhatt** (@Yogansh_Bhatt) · 2026-03-17 07:32

[[![Screenshot_20260317-125950](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/0/f09af13610244ecf8543ba4f535b414d66779e3d_2_449x1000.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/0/f09af13610244ecf8543ba4f535b414d66779e3d_2_449x1000.png)

Screenshot_20260317-1259501344×2992 65.8 KB](/uploads/short-url/ykuypPyYS6N4l40dcthVZoGOjJX.png?dl=1)

不知道它会怎么运行，但希望我能尽快测试一下我心爱的 Kodachrome64 : )

---

## #456 **jo** (@hanatos) · 2026-03-17 08:13

哇，真棒！正片和大量的重构工作正在进行中。

---

## #457 **Yogansh Bhatt** (@Yogansh_Bhatt) · 2026-03-17 09:03

经过漫长的沉寂之后，他好像回来了！而且一回来就加入了正片！

我敢肯定下一步就是一些黑白胶片了。

等不及了！

另外问一个不相关的问题，我所有的照片在 d65 转换后似乎都非常暖，我要么使用色彩模块中的通道，要么选择预设并找到一些中性色来开始使用 filmsim。这正常吗？

其中很多是富士 X-H2S 的 RAW 文件，还有一些是我的 Pixel 的 RAW 文件。我几乎总是需要调整白平衡，这时我觉得自己搞乱了 filmsim 模块的输入。我也尝试调整 Y 和 C 滤镜而不是使用色彩模块来调整（假设为了 d65 输入，它们必须保持 1-1-1），但这不太方便……不知道我做错了什么，希望你能指点一下！

---

## #458 **** (@mikae1) · 2026-03-17 11:45

好发现

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 非常感谢为这个精彩项目添加的每一行代码。你会把正片也加到 vkdt 中吗，[@hanatos](/u/hanatos)？

---

## #459 **jo** (@hanatos) · 2026-03-17 11:53

> **@Yogansh_Bhatt** (帖子 #457):
> 另外问一个不相关的问题

也许可以另开一个帖子并上传一些照片？我看到照片会理解得更快

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

filmsim 模块中的滤镜经过优化，我记得是为了产生 D50 中性色，并且应该与原始的 agx-emulsion Python 版本相同。

> **@mikae1** (帖子 #458):
> 你会把正片也加到 vkdt 中吗，@hanatos？

当然。需要了解具体有哪些改动，并回忆如何导入 .json 文件。

---

## #460 **** (@mikae1) · 2026-03-17 11:56

> **@hanatos** (帖子 #459):
> 当然。需要了解具体有哪些改动，并回忆如何导入 .json 文件。

好的，谢谢！

[![:slightly_smiling_face:](https://discuss.pixls.us/images/emoji/apple/slightly_smiling_face.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slightly_smiling_face.png?v=12)

[![:+1:](https://discuss.pixls.us/images/emoji/apple/+1.png?v=12)](https://discuss.pixls.us/images/emoji/apple/+1.png?v=12)

---

## #461 **** (@CarVac) · 2026-03-17 12:01

这真是一个很酷的项目！它几乎与 Filmulator 完全相反，Filmulator 主要关注扩散/消耗效应的控制，并且刻意避免模仿颗粒或特定胶片的色彩。因为它的目标不同：在编辑时快速做出决策。

> **@arctic** (帖子 #256):
> 我相当肯定有些化学/扩散效应我们还没有考虑到。例如，显影剂的浓度可能存在局部效应，在高密度区域被消耗，在我看来这会产生抑制作用。

---

## #462 **** (@Cristian) · 2026-03-17 12:01

太好了，我很高兴看到正片的更新以及这个项目的持续性。希望未来能看到一些黑白胶片。

---

## #463 **Yogansh Bhatt** (@Yogansh_Bhatt) · 2026-03-17 12:03

谢谢，我会的！我还有很多工作流程方面的问题想请教。

---

## #464 **** (@mikae1) · 2026-03-17 20:34

> **@CarVac** (帖子 #461):
> 这真是一个很酷的项目！它几乎与 Filmulator 完全相反，Filmulator 主要关注扩散/消耗效应的控制，并且刻意避免模仿颗粒或特定胶片的色彩。因为它的目标不同：在编辑时快速做出决策。

我已经很久没看过 Filmulator 了。我一直很喜欢这个想法，但从未觉得它的结果有胶片感——尽管名字里带着"Film"。我希望它有点像 DaVinci Resolve 中的 Film Look Creator。它不试图模拟任何特定胶片，而是模拟胶片般的特性（比如光晕、彩色颗粒、胶片般的色彩等）。

---

## #465 **** (@CarVac) · 2026-03-17 20:50

我喜欢胶片拍摄的结果，总是觉得对实验室扫描件应用一条简单的曲线就看起来很不错，但我从未迷恋过诸如光晕和颗粒这类技术缺陷。所以我选择模拟显影过程中的某些方面，只实现我在意的改进。

我想 Filmulator 这个名字对于寻找胶片感外观的人来说确实有误导性，但 SimpleBetterJPEGifier（对它能为我实现的效果的更精确描述）又不太顺口。

也许我可以在网站上放一些更好的说明信息？

---

## #466 **** (@Thomsen) · 2026-03-21 13:33

在极光照片上测试 filmsim！

[[![Nordlys 1](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/8/788047d78136dc4b67176aa45b7b566ab6fb4e69_2_690x458.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/8/788047d78136dc4b67176aa45b7b566ab6fb4e69_2_690x458.jpeg)

Nordlys 14416×2936 19.3 MB](/uploads/short-url/hc08stC3AS41HCFOm4qudMorHZf.jpeg?dl=1)

[[![20260321_Stockholm_0000](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/a/4a283da7581a539e16b7d3ab047c770e69060d1f_2_494x750.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/a/4a283da7581a539e16b7d3ab047c770e69060d1f_2_494x750.jpeg)

20260321_Stockholm_00002913×4416 3.99 MB](/uploads/short-url/aA1y041FI3xUZd3KFEpTO78KhMb.jpeg?dl=1)

还有一段延时视频：
<aside class="onebox allowlistedgeneric" data-onebox-src="https://e.pcloud.link/publink/show?code=XZ0M1GZTKa7stdpbX8aJ5a47TmvNbcG4N07">
 <header class="source">

[![图片465](https://d2x313g9lpht1q.cloudfront.net/original/3X/d/d/dd87d6a17000924d83c83021f22bd98fe9d38b30.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/d/d/dd87d6a17000924d83c83021f22bd98fe9d38b30.png)

 [pCloud](https://e.pcloud.link/publink/show?code=XZ0M1GZTKa7stdpbX8aJ5a47TmvNbcG4N07)
 </header>

 <article class="onebox-body">

[![图片466](https://d2x313g9lpht1q.cloudfront.net/original/3X/f/0/f0af0bf6a23181dcca305babab1bd95ecc9389fa.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/f/0/f0af0bf6a23181dcca305babab1bd95ecc9389fa.jpeg)

### [极光延时 filmsim.mov - 通过 pCloud 共享](https://e.pcloud.link/publink/show?code=XZ0M1GZTKa7stdpbX8aJ5a47TmvNbcG4N07)

在 pCloud 中存储视频。与合适的人共享。在任何设备上访问。立即创建免费账户！

 </article>

</aside>

---

## #467 **Upperechelonstr8up** (@upperechelonstr8up) · 2026-03-28 04:22

我希望未来能看到这个项目做的一件事，就是逆向重现老式的 technicolor/eastmancolor/90 年代胶片。我从未见过任何胶片模拟工具（*或者实际上任何现代胶片*）能模拟出那种不完美的、几乎像*油画*一样的质感，我寻找了多年，想要找到一种准确模拟它的方法，但收效甚微，因为每个胶片模拟插件/滤镜都只关心改变色彩关系。对我来说，那看起来一直就像做了色彩校正的数字图像，在我看来和其他东西没什么区别。*总得有什么方法可以实现吧，对吧？* 希望大家能理解我在说什么，就是那种绘画般的效果，一定是当年感光化学工艺不像现在这样精炼和完美的结果——远处的物体几乎会模糊成画面上的污迹。在那个电影和彩色摄影看起来不像真实、也不像合成，而是呈现出动态绘画外观的时代。在我对这个主题的所有研究中，这个工具是我见过的离这个效果最接近的（但仍然差一点）。我可能是整个帖子里技术最不熟练的人，甚至从未拿过胶片相机，所以请告诉我你们的想法。

---

## #468 **Terry Pinfold** (@Terry) · 2026-03-28 09:35

> **@upperechelonstr8up** (帖子 #467):
> 模拟那种不完美的、几乎像油画一样的质感

我的回答有点跑题。我是伴随着胶片长大的，并且以拍摄和处理胶片为职业。我并不想回到胶片感的外观，因为我拥抱数字图像本身的价值。但我经常希望给我的图像增加更多绘画感。可以是水彩效果或油画效果。那是我希望看到的一种模拟。

---

## #469 **** (@Cristian) · 2026-03-28 09:56

有意思，我对这种油画效果很好奇；我很希望能够至少部分地将它应用到数字照片上。你能给我们看一些具有这种效果的胶片照片示例吗？

---

## #470 **Upperechelonstr8up** (@upperechelonstr8up) · 2026-03-28 15:20

嘿，我的账号每帖只能发 4 张图片，所以我用跟帖回复。抱歉造成不便。

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/d/1d35126ce5a9248bae8f516d344ebfd074bb4b45_2_690x288.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/d/1d35126ce5a9248bae8f516d344ebfd074bb4b45_2_690x288.jpeg)

image1443×604 113 KB](/uploads/short-url/4anyh3frmvlG31gq3fsjENSjsb3.jpeg?dl=1)

首先，这是一部使用胶片拍摄的新电影的画面。我认为这看起来不错，别误会，但我感觉新的胶片看起来太完美了，太像数字了。下面是我说的一些例子。

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/7/b7f4add80a4e2fa79e7dc54e1a03b654c849b83f_2_690x291.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/7/b7f4add80a4e2fa79e7dc54e1a03b654c849b83f_2_690x291.jpeg)

image1460×617 146 KB](/uploads/short-url/qflBaR8iSE9sGQUH2lGC6Ri2yrZ.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/9/198ecc04966799b60c4b2479b88fcb63722b3758_2_690x289.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/9/198ecc04966799b60c4b2479b88fcb63722b3758_2_690x289.jpeg)

image1459×612 199 KB](/uploads/short-url/3E5Sqhuctvo2PdmS39xqf7xrUus.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/4/545a035e13fcca4d10fa17fd4343f0e84f54d5d5.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/4/545a035e13fcca4d10fa17fd4343f0e84f54d5d5.jpeg)

image824×445 68.3 KB](/uploads/short-url/c2cXvvUsHej51Dn8AFsDU8Vg1y5.jpeg?dl=1)

---

## #471 **Upperechelonstr8up** (@upperechelonstr8up) · 2026-03-28 15:21

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/3/6365e7a5c59569ec71268956bd84ed77bbb861c3_2_690x388.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/3/6365e7a5c59569ec71268956bd84ed77bbb861c3_2_690x388.jpeg)

image1600×900 328 KB](/uploads/short-url/ebjBbtdTlvZkZuXlIOTTrz5nSPp.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/3/f36f4c3385e6d5beb87cbc58686bc3412982547e_2_690x388.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/3/f36f4c3385e6d5beb87cbc58686bc3412982547e_2_690x388.jpeg)

image1600×900 291 KB](/uploads/short-url/yJwtJ2ngYZs5aOeh4kLUyDvgmWa.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/0/6020e6435a2d30163a020ec4837ee3485d68b4af_2_690x388.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/0/6020e6435a2d30163a020ec4837ee3485d68b4af_2_690x388.jpeg)

image1600×900 260 KB](/uploads/short-url/dIok5evvaI0mbAZQNKxt3FcFljF.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/3/d3edd8a0db1375ea5fc62612e674166cda26c910_2_690x500.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/3/d3edd8a0db1375ea5fc62612e674166cda26c910_2_690x500.jpeg)

image1073×779 193 KB](/uploads/short-url/ueOkqf40nabcVpyTKti7NQp7Dsk.jpeg?dl=1)

即使是像《雨中曲》这样颗粒不那么明显的电影，仍然能够呈现出一种现代胶片尤其是数字所缺乏的柔和感。

---

## #472 **Upperechelonstr8up** (@upperechelonstr8up) · 2026-03-28 15:21

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/2/626eada7206dbd5bf016b7e74f777c238f054a64_2_690x313.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/2/626eada7206dbd5bf016b7e74f777c238f054a64_2_690x313.jpeg)

image1920×872 84.5 KB](/uploads/short-url/e2LUZVmYrIOy00SdlZsFvRUKEte.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/3/0330e43881af25d0db07d5f21eb9700418ee5560.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/3/0330e43881af25d0db07d5f21eb9700418ee5560.jpeg)

image800×320 96.4 KB](/uploads/short-url/sebhniXR6JOmfJeCvJ8YDB2iUE.jpeg?dl=1)

这种外观之间的转变似乎发生在 2008-2010 年左右。事实上，2007 年的一部塔伦蒂诺电影是最后一个能够准确呈现这种效果的例子之一。

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/d/0d3acd94500c1be3265a4a7aeccc913023efd0cd_2_690x291.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/d/0d3acd94500c1be3265a4a7aeccc913023efd0cd_2_690x291.jpeg)

image1394×588 118 KB](/uploads/short-url/1T2bUgCCBG2ZePmOY9BhFBjjpff.jpeg?dl=1)

而且不是灰尘和划痕的问题。事实上，我认为灰尘和划痕是这种风格中最不重要的元素之一。

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/c/2c7ae57f97c66e0a4fc5b3046c507aafaae3dcb4_2_690x296.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/c/2c7ae57f97c66e0a4fc5b3046c507aafaae3dcb4_2_690x296.jpeg)

image1393×599 207 KB](/uploads/short-url/6lujpTUOPjsoPclvlvNRE8HPEiw.jpeg?dl=1)

---

## #473 **upperechelonst9up** (@upperechelonst9up) · 2026-03-28 15:30

你好，还是我。我还有更多例子，以及新旧胶片差异的例子，但 pixls.us 只允许我回复 3 次。如果需要更多背景，我很乐意重写我的回复。

---

## #474 **Nuno Paulino** (@hatsnp) · 2026-03-28 17:14

请记住，当时的许多扫描都使用了较老的技术，可能无法准确反映电影院中实际放映的效果，以及更忠于最终产品的现代扫描会是什么样子。

另外，我认为你的比较并不公平。比如《浴血战场》中有很多镜头是在直射阳光下拍摄的，这与《黄金三镖客》等进行对比会更好。

---

## #475 **** (@Cristian) · 2026-03-28 17:30

谢谢，我现在完全理解你说的是什么效果了。是的，我同意你的看法，这些画面太棒了，看看那些色彩多美啊，有些人可能会说它们是柔和的。我记得我还是新手编辑照片的时候，会把饱和度滑块拉满来获得更"鲜艳"的色彩

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 很高兴我已经过了那个阶段。

你看过这个吗？[https://www.youtube.com/watch?v=za20Kb2VSN8&t=504s](https://www.youtube.com/watch?v=za20Kb2VSN8&t=504s)

我想你可能会觉得它有趣。

还有你应该读这本书：[LIFELIKE: A book on color in digital photography – Dehancer Blog](https://blog.dehancer.com/lifelike-book/)

---

## #476 **Upperechelonstr8up** (@upperechelonstr8up) · 2026-03-28 17:40

在我被截断之前的原始示例中，我实际上确实使用了《木兰花》和《血色将至》（均由 PTA 执导）的画面来区分新旧胶片的外观。

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/9/c9ac29166682ea51bcec81f3332574e97df231e3.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/9/c9ac29166682ea51bcec81f3332574e97df231e3.jpeg)

image1024×424 65.8 KB](/uploads/short-url/sM4P4p1gNa28J4u9g0lLUBAM351.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/3/5/3529b71484779bdda8ba4803cacd5bbd100c5fc6.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/3/5/3529b71484779bdda8ba4803cacd5bbd100c5fc6.jpeg)

image1024×536 104 KB](/uploads/short-url/7AiGaRs9LWmh4SEhO1o464ZWQoC.jpeg?dl=1)

另外，我发送的大多数扫描都来自 4K 重制版，但我确实认为这种外观的吸引力部分来自胶片随时间的自然老化。不过，现代胶片和 2008-2009 年之前的胶片之间的区别是明显的。

---

## #477 **Upperechelonstr8up** (@upperechelonstr8up) · 2026-03-28 17:50

我会去看看这些！但我认为，虽然色彩非常美丽，远超大多数现代摄影作品，但真正让这种效果与众不同的不是色彩。而是这些色彩以一种既有机又不完美的方式相互融合并溢出边缘。有些现代电影拥有与经典作品一样好的调色板，但仍然未能达到这种特殊的质感。就个人而言，我真的不理解如果最终看起来像 Arri Alexa 的话，现在拍摄胶片有什么意义。

---

## #478 **Nuno Paulino** (@hatsnp) · 2026-03-28 18:19

这在我看来似乎只是拉高黑色电平和柔和光线的编辑决策，再次说明，我认为这不是一个好的对比

---

## #479 **Terry Pinfold** (@Terry) · 2026-03-28 19:06

我看了很多最新发布的韩剧，它们的摄影经常非常出色。我觉得这在很大程度上取决于素材如何调色。在 1970 年代，大多数电影在处理夜景时都相当令人作呕。似乎是在日光下拍摄，然后欠曝，再用类似钨丝灯的白平衡来给夜景添加蓝色。Technicolor 是有史以来最出色的彩色胶片之一。原因在于它使用的是三条黑白胶片而不是彩色胶片。然后这些胶片被用来制作供放映用的自然而鲜艳的彩色拷贝。这个过程与现在数码相机使用的 RGB 传感器非常相似。我们可以将图像编辑得在色彩和分辨率上都呈现出类似过去胶片质感的柔和效果，也可以制作出艳丽鲜艳的色彩并最大限度提高锐度来产生某种现代诠释。技巧在于通过编辑来实现你的期望。

---

## #480 **Yogansh Bhatt** (@Yogansh_Bhatt) · 2026-03-29 16:22

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/5/e5d05672b8f3c7c0068bae869670f60bc2e713ca_2_690x406.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/5/e5d05672b8f3c7c0068bae869670f60bc2e713ca_2_690x406.jpeg)

image1919×1130 434 KB](/uploads/short-url/wN1Hx8Y8L0ycTyH4mrPorAg2ObE.jpeg?dl=1)

各位，我们有了正片！

我太喜欢了 : )

Kodachrome 64 我来了！

我知道它还在开发中，还有很多东西比如 RAW 导入等正在搭建中，这很棒！

我一直刷新提交记录，终于看到它在 dev 和 refactor 分支上运行了。

---

## #481 **** (@Cristian) · 2026-03-29 16:48

太好了，我喜欢 Kodachrome 64 的效果！我今天刚买了 Fred Herzog 的摄影集 *A Color Legacy*，被他的照片深深吸引了。他用的是 Kodachrome 胶片，照片具有我们这里讨论的那种**油画**般的质感。你可以在这里看到他的部分作品：[The Estate of Fred Herzog | Artists | Equinox Gallery](https://www.equinoxgallery.com/our-artists/fred-herzog/)

---

## #482 **Benjamin** (@piratenpanda) · 2026-03-29 17:24

kodak 和 fuji provia velvia 给我的颜色是反转的。我做错了什么？

编辑：啊，我需要勾选扫描胶片

---

## #483 **Andrea** (@arctic) · 2026-03-29 23:07

是的，过去几周我有心境重新投入这个项目了

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 并享受了重构和打下一些基础工作的乐趣，这样在试验正片时不会失去方向。正片的处理方式目前仍然有点凑合，我需要探索更多方面，但配置文件已经显示出一些胶片的特征。饱和度可能完全不对，抑制耦合剂的量也需要调整。它们还没有"发布"，因为还不完善。

为了趣味性，我还给 GUI 添加了一些生活质量改进，那里也是大工程进行中。我实现了帖子中提出的一些想法，待办清单里还有几个。

[[![gui_screenshot](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/6/f6f0d2c3ab6abdc04e5b9cec7b3aea4c7c4e61f7_2_690x431.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/6/f6f0d2c3ab6abdc04e5b9cec7b3aea4c7c4e61f7_2_690x431.png)

gui_screenshot1920×1200 1.52 MB](/uploads/short-url/zexpZF7tFKNpjWftJqG50rLUkOX.png?dl=1)

我将项目重命名为 `spektrafilm`，遵循了论坛中一些成员的建议，他们指出 agx-emulsion 这个名字与 agx 色调映射器太相似容易造成混淆（顺便说一句，那个作品也非常出色）。我认为新名字也与项目更加契合。

---

## #484 **Tim** (@Soupy) · 2026-03-30 05:36

> **@upperechelonstr8up** (帖子 #467):
> 我希望未来能看到这个项目做的一件事，就是逆向重现老式的 technicolor/eastmancolor/90 年代胶片。我从未见过任何胶片模拟工具（或者实际上任何现代胶片）能模拟出那种不完美的、几乎像油画一样的质感，我寻找了多年，想要找到一种准确模拟它的方法，但收效甚微，因为每个胶片模拟插件/滤镜都只关心改变色彩关系。

[1932-1953 年的 Technicolor](https://filmcolors.org/timeline-entry/1301/)（《乱世佳人》《红菱艳》《绿野仙踪》等）是使用三条独立胶片拍摄的。[1954 年以后的 Technicolor](https://filmcolors.org/timeline-entry/1445/)（《无因的反叛》《教父》《迷魂记》等）则使用单条胶片（或三合一）拍摄，但我相信仍然使用相同的染料转印工艺。正是这些（或其中之一）造就了你很可能所指的经典 technicolor 效果。我们还要记住，不同的摄影技术也在"这种效果"中发挥了一定作用。

我不确定链接网站对这些光谱胶片模拟是否有用，但它是一个关于老式胶片库存的信息宝库。

---

## #485 **Yogansh Bhatt** (@Yogansh_Bhatt) · 2026-03-30 08:41

非常好的决定！

这个项目对我来说一直就像一场探索之旅。Spektrafilm 这个名字贴切得多，而且我们可以直接运行 spektrafilm 而不是之前的脚本，这也是一个虽小但好的改进🙂

根据我对负片的经验，富士相机等设备拍摄的图像已经有很好的对比度，但我的 Pixel DNG 文件通常缺乏饱和度和对比度，所以与它玩耍比其他工具更有回报，因为我们有多种方式可以通过胶片和相纸来实现。

现在有了正片，相纸控制就用不上了，我对显影过程没有任何经验，所以不知道那该如何处理。

我会每天运行 git pull。

---

## #486 **** (@Cristian) · 2026-03-30 09:06

感谢更新。继续加油！

---

## #487 **Upperechelonstr8up** (@upperechelonstr8up) · 2026-03-30 13:23

你能展示一下模拟前的图像是什么样子吗，做个对比？

---

## #488 **jo** (@hanatos) · 2026-03-30 14:01

看到更新真是太棒了！你能给我一些更新的提示吗？我注意到你把 dye_density 移到了 channel_density、base_density……还有别的变化吗？可能是不同的归一化或缩放？

另外正片似乎只是一个相对较小的改动，只在几个地方翻转了符号，是这样吗？

[编辑] 最重要的微妙变化：空数据点现在是 `null` 而不是 `NaN`

---

## #489 **Andrea** (@arctic) · 2026-03-30 21:53

我把原来的 dye_density 拆分成了 channel_density、base_density、midscale_neutral_density。这样做是为了以后黑白配置文件能有更干净的代码，而且命名也更清晰。

我没有做太多其他改动，我简化了负片的配置文件创建过程，去除了之前不必要的密度曲线拟合。所以没有大的变化，主要是重构。我想添加黑白电平校正，并增加保存"供打印用"图像的选项。

目前，正片处理只是反转了抑制耦合剂的 log_exposure 校正符号。结果还可以，但我还没有做足够的研究来确定这是最佳方法。我主要工作在获取数据和探索配置文件创建方面。

`null` 似乎是 JSON 对缺失值的合规方式。

我稍微调整了配置文件信息，现在指定了类型（负片或正片）、通道模型（彩色或黑白）和支持介质（胶片或相纸）

---

## #490 **jo** (@hanatos) · 2026-03-31 07:00

谢谢！我想我已经让这个重新跑起来了。目前我对正片的立场就是它简单地跳过了打印步骤，使用我先前就有的"扫描胶片"代码路径。我会做一些清理/测试然后推送。

---

## #491 **Andrea** (@arctic) · 2026-03-31 11:27

有彩色正片相纸的数据，比如 Kodak Ektachrome Radiance，可以添加到正片打印中，我会看看。

---

## #492 **Terry Pinfold** (@Terry) · 2026-04-01 01:09

在旅行中测试了几个相对较新的镜头，包括一个 9mm f2.8 AstrHori 镜头时，我想到了这个帖子。我觉得胶片的一些效果不仅仅是胶片本身，还有当时较柔和的镜头。现在有了数码，我们有非常锐利的镜头和编辑选项可以使图像更加锐利。数字编辑中经典 USM 蒙版的概念源于大画幅胶片时代。我想知道这里有多少胶片摄影师曾经为打印胶片制作过 USM 锐化蒙版。如果有人说自己做过锐化胶片图像的处理，我会很惊讶。

---

## #493 **None** (@Anthonygansauer) · 2026-04-01 11:29

我读这个帖子有一段时间了，并且一直在专业领域使用这个软件。这是改变游戏规则的东西！我实际上主要拍摄胶片和 RA4 打印，Andrea，如果你需要任何实际测试，请告诉我！我可以使用 Endura，但主要使用 DPii 相纸。

[anthonygansauer.com](http://anthonygansauer.com)

---

## #494 **Todd Prior** (@priort) · 2026-04-01 15:02

感谢分享……我喜欢"pride not hate"菜单下的那张照片……你模特的表情和场景太棒了……

欢迎来到论坛……

---

## #495 **** (@Cristian) · 2026-04-01 15:06

很棒的照片！

---

## #496 **** (@tankist02) · 2026-04-01 18:37

最近 spektrafilm 和 ART 中添加了一些正片的支持。

获取最新的 spektrafilm 仓库并切换到 dev 分支：

```
git clone --recursive https://github.com/andreavolpato/spektrafilm.git
cd spektrafilm
git switch dev
```

按照安装步骤操作： [https://github.com/andreavolpato/spektrafilm/tree/dev](https://github.com/andreavolpato/spektrafilm/tree/dev)

我在 Fedora 43/Gnome 系统上使用了 conda 方式。

获取 ART 仓库的最新更改，并根据你的系统更新 ART_agx_film.json 中的命令行。例如，我的配置是：

```
"command" : "/home/andrew/.conda/envs/spektrafilm/bin/python3.13 spektrafilm_mklut.py --server",
```

这里有几个例子：

Provia 100F：

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/3/6364e34ad50dc248987502b41bb87ac7c25451e3_2_690x388.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/3/6364e34ad50dc248987502b41bb87ac7c25451e3_2_690x388.jpeg)

image3840×2160 1.44 MB](/uploads/short-url/ebhq5CVDdrcJ7DTEyfaLPEchPQ7.jpeg?dl=1)

Kodachrome 64：

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/a/2afcc78091385d1267a045e991b5f6dc465c8680_2_690x388.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/a/2afcc78091385d1267a045e991b5f6dc465c8680_2_690x388.jpeg)

image3840×2160 1.35 MB](/uploads/short-url/68hD7gFG6Ihyo8QEeL0K9zaBZtK.jpeg?dl=1)

---

## #497 **Todd Prior** (@priort) · 2026-04-02 04:20

我正在 Windows 上使用 1.26.3 版尝试这个……我下载了新脚本，但我很久没有构建过 ART 了，所以想知道这会不会是我的问题？？。Spektrafilm 已安装并能运行 GUI，但我要么找不对 JSON 文件中 Python 行的正确命令语法，要么需要一个更新版本的 ART 构建，但我无法让集成在 ART 中正常工作。

---

## #499 **None** (@Anthonygansauer) · 2026-04-03 17:41

一个很酷的功能是添加放大机漫射效果！当你在放大机镜头上放置漫射片时，阴影会产生辉光而不是高光，因为一切都是反转的，这是一种非常有趣的效果，我认识很多从事编辑和时尚行业的人都在使用它。我会发一个 Jack Orton 使用这种方法的例子。

[fd360964903bb03732b0058283087f0ecd6c4598-1200x1500|690x862](/uploads/short-url/2VmtAmRwiVB53SRkGzufoW3vYIA.jpeg)

---

## #500 **Andrea** (@arctic) · 2026-04-06 01:29

天哪，喜欢你的照片！

[![:star_struck:](https://discuss.pixls.us/images/emoji/apple/star_struck.png?v=12)](https://discuss.pixls.us/images/emoji/apple/star_struck.png?v=12)

 也感谢你的欣赏！

完整模拟的一个弱点是饱和度通过抑制耦合剂量的校准，这完全是肉眼估测的（或者让用户按自己喜欢调整）。找到确定饱和度水平可靠起点的方法会很有意思。我想在这方面，与真正使用 RA4 打印的专家一起微调应该是最好的输入。

[![:blush:](https://discuss.pixls.us/images/emoji/apple/blush.png?v=12)](https://discuss.pixls.us/images/emoji/apple/blush.png?v=12)

> **@Anthonygansauer** (帖子 #499):
> 一个很酷的功能是添加放大机漫射效果！当你在放大机镜头上放置漫射片时，阴影会产生辉光而不是高光，因为一切都是反转的，这是一种非常有趣的效果，我认识很多从事编辑和时尚行业的人都在使用它。我会发一个 Jack Orton 使用这种方法的例子。

我会做实验并回来反馈！看起来非常酷

---

## #501 **Terry Pinfold** (@Terry) · 2026-04-06 02:29

> **@Anthonygansauer** (帖子 #499):
> 你可以让阴影产生辉光而不是高光，因为一切都是反转的

DT 有没有一个模块可以让我反转图像来尝试复制这个建议的技术？

---

## #502 **Revanza Pratamasyah** (@Revanza_Pratamasyah) · 2026-04-07 03:32

大家好，有没有人知道为什么会这样："An executable named `spektrafilm` is not provided by package `agx-emulsion`."

可用的可执行文件有：

- agx-emulsion.exe"？

---

## #503 **Andrea** (@arctic) · 2026-04-07 05:54

看一下 `dev` 分支，由于大幅重构，我不敢合并到 `main` 分支，但也许现在可以了，因为我对目前状态更有信心，觉得没有搞砸太多，也做了一些测试

---

## #505 **Rafael** (@dark_photon) · 2026-04-07 11:46

抱歉也在这里发一下，除了在 Spectral film in Art 帖子之外！

如果有人想要一种简单的安装方式（在 Linux 上），我写了一个 Nix 派生文件：[GitHub - rafaelcgs10/spektrafilm-art: Spektrafilm and Art bundled together · GitHub](https://github.com/rafaelcgs10/spektrafilm-art)

---

## #506 **WG** (@BPH3647) · 2026-04-07 23:17

我之前也对某个分支的开发者提到过同样的事。我试过近似模拟，但它只是基于"扫描负片"功能，然后通过 Photoshop 和负片反转软件如 NLP 进行往返转换。不值得费力。

很希望能在 spektrafilm 中看到一个版本！或者甚至只是一个简单的"打印负片"开关，跳过初始的负片转换。

（顺便说一句，我记得你在 lightlurking 上发过的帖子。网站越来越好看了！）

---

## #507 **WG** (@BPH3647) · 2026-04-07 23:40

我通过光晕功能创建过高光辉光效果。也许可以在打印阶段基于光晕脚本来构建这个功能？将 CMY 固定为白色/中性色，并添加一个 sigma 用于高斯模糊？在现实中通常是两步曝光，所以可能会使事情复杂化。通常是 15-30% 的曝光时间，在镜头前放置防牛顿玻璃/香烟包装塑料/黑 Pro Mist 滤镜，然后剩下的正常成像时间。

附注：刚刚测试了今天的 dev 分支，请不要取消"打印密度最小因子"！

---

## #508 **** (@mikae1) · 2026-04-08 06:01

我如何用 `uv` 运行 spektrafilm 分支？对于 agx-emulsion，我使用这个脚本：

```
#!/bin/bash
cd ~/Python/agx-emulsion/
uvx --from git+https://github.com/andreavolpato/agx-emulsion.git agx-emulsion

```

我尝试创建：

```
#!/bin/bash
cd ~/Python/spektrafilm/
uvx --from git+https://github.com/andreavolpato/spektrafilm/tree/dev.git spektrafilm

```

但出现了：

```
Updating https://github.com/andreavolpato/spektrafilm/tree/dev.git (HEAD)
× Failed to resolve `--with` requirement
 ╰─▶ Git operation failed

```

---

## #509 **Andrea** (@arctic) · 2026-04-08 09:38

> **@Anthonygansauer** (帖子 #499):
> 一个很酷的功能是添加放大机漫射效果！

我快速尝试实现了放大机漫射。当然可以调整模糊核的形状，增强光晕或辉光尾部

无滤镜

[[![print_scan_no_filter](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/9/f981414380255b845ac1c9fcb7a686098f943e30_2_690x862.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/9/f981414380255b845ac1c9fcb7a686098f943e30_2_690x862.jpeg)

print_scan_no_filter1200×1500 807 KB](/uploads/short-url/zBdOGIKBiVa3kpk1f31u2SdsN32.jpeg?dl=1)

滤镜强度 1/4

[[![print_scan_0.25](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/c/7ceeac2827e21ae4f1d7b502ca4db748b8437424_2_690x862.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/c/7ceeac2827e21ae4f1d7b502ca4db748b8437424_2_690x862.jpeg)

print_scan_0.251200×1500 723 KB](/uploads/short-url/hPcyHNNq6tQw1ZqX8BKFlDXovMU.jpeg?dl=1)

其他滤镜强度 1/8、1/2 和 1

<div class="lightbox-wrapper">[[![print_scan_0.125](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/5/1569b43cd78d255d116dfe1bcddebece7617eafd_2_690x862.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/5/1569b43cd78d255d116dfe1bcddebece7617eafd_2_690x862.jpeg)

print_scan_0.1251200×1500 755 KB](/uploads/short-url/33quNA2mFncaVInGp6OAKnkMk9v.jpeg?dl=1)

[[![print_scan_0.5](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/7/f7735ec53cc97ee002d0c4f447271453b25a93fd_2_690x862.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/7/f7735ec53cc97ee002d0c4f447271453b25a93fd_2_690x862.jpeg)

print_scan_0.51200×1500 683 KB](/uploads/short-url/zj376WboqXkAVaX1UEGY6DXQVCR.jpeg?dl=1)

[[![print_scan_1](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/6/96c8416750d440615f291d9d8d6b00b2c96f9a8a_2_690x862.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/6/96c8416750d440615f291d9d8d6b00b2c96f9a8a_2_690x862.jpeg)

print_scan_11200×1500 636 KB](/uploads/short-url/lvSFhWZYV1JHMo7hG7KtavnRguu.jpeg?dl=1)

</div>

这里是可能需要调整的扩散核

[[![psf_kernel](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/d/5d9cc14b655b456e357509be4cfd1f8341209d4e_2_690x207.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/d/5d9cc14b655b456e357509be4cfd1f8341209d4e_2_690x207.png)

psf_kernel1600×480 101 KB](/uploads/short-url/dm8fyvjBGWBCBpxvhiXFlhbjhue.png?dl=1)

---

## #510 **Andrea** (@arctic) · 2026-04-08 09:41

> **@BPH3647** (帖子 #507):
> 附注：刚刚测试了今天的 dev 分支，请不要取消"打印密度最小因子"！

我的想法是使用扫描仪中新增的黑白校正控制来实现类似的效果。我对打印密度最小因子的主要担忧是，基础光谱密度可能不是色彩中性的，因此可能会对色彩平衡产生一些影响。

---

## #511 **Andrea** (@arctic) · 2026-04-08 09:43

还没有测试过 uv

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 我会去看一下

---

## #512 **Mica** (@paperdigits) · 2026-04-08 15:52

> **@dark_photon** (帖子 #505):
> 如果有人想要一种简单的安装方式（在 Linux 上），我写了一个 Nix 派生文件：GitHub - rafaelcgs10/spektrafilm-art: Spektrafilm and Art bundled together · GitHub

我是 nixpkgs 中 ART 的维护者，我不介意把它也放进去

[![:wink:](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)

---

## #513 **None** (@Anthonygansauer) · 2026-04-08 15:57

就这样你就搞定了！太厉害了！！！

---

## #514 **** (@Thomsen) · 2026-04-09 11:42

> **@arctic** (帖子 #509):
> 我快速尝试实现了放大机漫射。

很好的补充！这里的初步实现似乎有一个相当硬的衰减，造成了明显的暗色光晕，使效果看起来与照片不够融合。

花了一些时间才找到实际的模拟参考，但据我所见，衰减是非常柔和的：

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/e/ce76ebfbcc5f1b9efb653867525b7dfcbf71c5c2_2_517x646.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/e/ce76ebfbcc5f1b9efb653867525b7dfcbf71c5c2_2_517x646.jpeg)

image1080×1350 215 KB](/uploads/short-url/tst99P9PZUoysMcSxpdv3HIJq0y.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/4/84ebaf275c0bcbd5741f348dfc7519ca2cca792b_2_517x623.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/4/84ebaf275c0bcbd5741f348dfc7519ca2cca792b_2_517x623.jpeg)

image1080×1302 260 KB](/uploads/short-url/iXRYAbPr35wyhiFaVI9Dx8EKRDl.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/e/9ecb7f661018988b1a129067e95c435472777584_2_517x373.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/e/9ecb7f661018988b1a129067e95c435472777584_2_517x373.jpeg)

image1080×781 137 KB](/uploads/short-url/mELqMKFOtnzJFggWyY04P836EBK.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/6/c692c09b9eb9ddbebc97507e7e83129a18fbcda0_2_517x376.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/6/c692c09b9eb9ddbebc97507e7e83129a18fbcda0_2_517x376.jpeg)

image1080×786 317 KB](/uploads/short-url/skEXbIx7mKTbDK8bqmrKn840i9G.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/f/cfb029b3749f91aee033ed7a7020b0408c90d5c8_2_517x595.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/f/cfb029b3749f91aee033ed7a7020b0408c90d5c8_2_517x595.jpeg)

image712×820 95.5 KB](/uploads/short-url/tDiglrHkiFP3Vog16sYgLqKoO1y.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/6/3668f44615b5398cceef6cc0bd3c135cf8e93e3a_2_517x641.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/6/3668f44615b5398cceef6cc0bd3c135cf8e93e3a_2_517x641.jpeg)

image750×930 108 KB](/uploads/short-url/7LkE61yKm1aswc25fbLsog1zgJs.jpeg?dl=1)

---

## #515 **Andrea** (@arctic) · 2026-04-09 18:14

感谢参考照片！

---

## #516 **None** (@Anthonygansauer) · 2026-04-10 13:51

哈哈，第三张照片是我的作品之一！

有一点需要注意的是，如果曝光时间是 4 秒，而我想添加漫射效果，我需要在 50% 漫射的情况下增加大约 1/3 档的密度。

基础打印曝光：

4秒 f8

带漫射的打印曝光：

2.5秒 f8 + 2.5秒 镜头前加漫射片

（通常我用的是冲卷后装胶片的那种塑料负片袋）

不知道这对 Andre 有没有帮助，因为打印是一个很依赖个人经验和感觉的过程。

---

## #517 **** (@Thomsen) · 2026-04-10 17:24

拍得好！

[![:wink:](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)

---

## #518 **Anna** (@betazoid) · 2026-04-11 03:35

[[![IMG_0805](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/3/6348c014decde2a78f018f819fca13abffbf305c_2_690x517.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/3/6348c014decde2a78f018f819fca13abffbf305c_2_690x517.jpeg)

IMG_08053264×2448 1.28 MB](/uploads/short-url/eaj8sn0OwM0KNRzqYbFg6JCAV1q.jpeg?dl=1)

Spektrafilm/ART/vkdt 工作坊 @ Grazer Linuxtage。

[@arctic](/u/arctic) [@agriggio](/u/agriggio) [@grubernd](/u/grubernd) [@hanatos](/u/hanatos)

希望我/我们没有传播太多错误信息。

特别感谢 [@grubernd](/u/grubernd) 参与讨论。

---

## #519 **** (@Thomsen) · 2026-04-11 13:46

当你的数码照片登上 Reddit 的 AnalogCommunity 社区顶部时，你就知道这个模拟有多好

[![:wink:](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/a/8a501ec75897eac4e0403827469fb7274e3231ba_2_690x683.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/a/8a501ec75897eac4e0403827469fb7274e3231ba_2_690x683.jpeg)

image987×978 300 KB](/uploads/short-url/jJzxXrnkL6kLUOTRi9odykBrkmu.jpeg?dl=1)

---

## #520 **** (@age) · 2026-04-12 09:33

我在想一种自动中和胶片模拟引入的色偏的方法，虽然可能不太符合这个帖子的精神，但它可能有用。

色偏可以通过 RGB 曲线或数学运算来消除。

让我们从一张原始图像开始：

[[![original](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/4/249a2a6eb3f671ffbf03b93e061f18aa53427e1d_2_690x460.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/4/249a2a6eb3f671ffbf03b93e061f18aa53427e1d_2_690x460.jpeg)

original1920×1281 1.32 MB](/uploads/short-url/5dNue5rvltxYuW3g2Cev3ujvV6d.jpeg?dl=1)

第一步是对原始图像应用胶片模拟，我们可以称这个图像为 rgb_film_simulation_cc（实际上这个图像中的每个像素都是 RGB 胶片模拟结果乘以一个色偏因子）：

[[![rgb_film_simulation](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/8/18d09d48cfdd3cd855820c07e8279e348dbb54cc_2_690x460.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/8/18d09d48cfdd3cd855820c07e8279e348dbb54cc_2_690x460.jpeg)

rgb_film_simulation1920×1281 1.44 MB](/uploads/short-url/3xwpDK5LXE3UEOJ4opfwtowsBbK.jpeg?dl=1)

第二步是对原始图像的灰度版本应用胶片模拟，我们可以称这个图像为 gray_film_simulation_cc（实际上这个图像中的每个像素都是灰度胶片模拟结果乘以一个色偏因子）：

[[![gray_film_simulation](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/b/2b93091d662eb1a206090088438ead1ebfd9febd_2_690x460.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/b/2b93091d662eb1a206090088438ead1ebfd9febd_2_690x460.jpeg)

gray_film_simulation1920×1281 1.18 MB](/uploads/short-url/6dtyjSNWvYJsBLWlvWzbW9RSioB.jpeg?dl=1)

第三步是去除第二步中最新图像的饱和度：

[[![gray](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/c/2c2deec986e25f28ab87d863243fd64528878c74_2_690x460.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/c/2c2deec986e25f28ab87d863243fd64528878c74_2_690x460.jpeg)

gray1920×1281 1.01 MB](/uploads/short-url/6iPpZmDqoBsScuHUcTygzJ0bLsE.jpeg?dl=1)

现在我们只需要应用以下表达式：

无色偏的胶片模拟 = (rgb_film_simulation_cc / gray_film_simulation_cc) * gray

这是结果：

[[![_MG_3199_04](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/a/7aa10cc8f50338fb48b82cf110a99fe1dfeaa0dc_2_690x460.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/a/7aa10cc8f50338fb48b82cf110a99fe1dfeaa0dc_2_690x460.jpeg)

_MG_3199_041920×1281 1.43 MB](/uploads/short-url/huPiyweR8qMVvX010gaC4LAw2Li.jpeg?dl=1)

它的工作原理？

这一部分

**(rgb_film_simulation_cc / gray_film_simulation_cc)**

可以写成

**(rgb_film_simulation * color_cast) / (gray_film_simulation * color_cast)**

结果就没有色偏了

**rgb_film_simulation / gray_film_simulation**

我们只需要将这个结果乘以 gray_film_simulation 图像，就能得到无色偏的 rgb_film_simulation

**rgb_film_simulation / gray_film_simulation * gray_film_simulation**

---

## #521 **Charles** (@Xerxes1138) · 2026-04-12 10:07

你好，

我用 pip 从 dev 分支安装了 spektrafilm。

程序运行正常，但当我尝试保存结果时，出现了"segmentation fault"错误然后崩溃。

我试过小尺寸图像和不同的输出文件类型，都没有效果。

你知道可能是什么原因吗？

注意，我是在 Windows 10 上测试的，还没在 Linux 上试过，而且 agx-emulsion 之前运行得很好。

非常感谢这个工具，这是我找了很久的东西！

---

## #522 **Andrea** (@arctic) · 2026-04-13 14:31

> **@betazoid** (帖子 #518):
> Spektrafilm/ART/vkdt 工作坊 @ Grazer Linuxtage。

哇！这太棒了！效果怎么样？

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 你愿意分享一下经验吗？

> **@Thomsen** (帖子 #519):
> 当你的数码照片登上 Reddit 的 AnalogCommunity 社区顶部时，你就知道这个模拟有多好

那真是张很棒的照片，它值得所有的点赞！

> **@Xerxes1138** (帖子 #521):
> 程序运行正常，但当我尝试保存结果时，出现了"segmentation fault"错误然后崩溃。

有没有更多信息可以调查？你使用的 Python 版本是什么？你试过干净安装吗？

---

## #523 **Andrea** (@arctic) · 2026-04-13 14:46

嘿 age，谢谢你的分享！这提醒我需要回到配置文件创建方面可以改进的几个问题上。我对此并不完全满意。

解决并最小化模拟的色偏是创建胶片配置文件时的核心挑战。实际上，核心原则之一是将中性灰输入映射到中性灰输出（实际上，我尝试通过最小限度修改特征密度曲线来校正中性灰渐变）。因为我不想过多干扰原始数据，所以有些许色偏是预料之中的。我认为色偏总体上应该是中性的，即阴影和高光应该以相反的方向偏移，而中间调应该保持相对中性。

有一点需要注意，如果虚拟放大机正在使用黄和品红滤镜进行色彩校正，那么中性灰输入产生有色偏的输出是正常的。如果中性灰出现强色偏，那可能是意外的（错误/失误），或者是一种有挑战性的胶片。你是否一直注意到不想要的色偏？你能只通过优化放大机滤镜来修复吗？如果是这样，问题可能出在预计算的中性放大机滤镜上。

---

## #524 **Gustavo Adolfo** (@gadolf) · 2026-04-13 16:39

你好！

我打不开 navari：

```
gustavo@CAURJ004:~/.local/bin$ /home/gustavo/.local/bin/uvx --from git+https://github.com/andreavolpato/spektrafilm.git spektrafilm
An executable named `spektrafilm` is not provided by package `agx-emulsion`.
The following executables are available:
- agx-emulsion

```

这是 Debian 12

注意：我之前成功从 main 分支安装了版本。Navari 可以打开界面，但我打不开 .exr 文件，所以我决定尝试 dev 分支

---

## #525 **Andrea** (@arctic) · 2026-04-13 18:22

试试这个命令：

```
uvx --from git+https://github.com/andreavolpato/spektrafilm.git@dev spektrafilm

```

我也更新了 readme。

> **@mikae1** (帖子 #508):
> 我如何用 `uv` 运行 spektrafilm 分支？对于 agx-emulsion，我使用这个脚本：

应该也回答了你之前的问题，[@mikae1](/u/mikae1)

---

## #526 **Charles** (@Xerxes1138) · 2026-04-13 18:45

我试了干净安装，装的是 Python 3.13。除了"segmentation fault"之外，我没有更多信息了。

也许我可以在程序运行时启用某种调试，但我不知道怎么做。

---

## #527 **Charles** (@Xerxes1138) · 2026-04-13 18:50

这也解决了我的问题！

---

## #528 **Vicer Fx** (@Vicer_Fx) · 2026-04-13 20:18

我认为你的例子更多与摄影风格有关，而不是使用的胶片本身。照明与现代电影真的很不一样

---

## #529 **** (@mikae1) · 2026-04-14 04:46

> **@arctic** (帖子 #525):
> uvx --from git+https://github.com/andreavolpato/spektrafilm.git@dev spektrafilm

酷，运行得很好！谢谢！相比 agx-emulsion 时代，用户体验上有了质的飞跃。

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

---

## #530 **Anna** (@betazoid) · 2026-04-14 14:25

> **@arctic** (帖子 #522):
> 哇！这太棒了！效果怎么样？你愿意分享一下经验吗？

我的印象是它取得了很大的成功。大约有 30 名参与者，这很棒，因为我在 Libre Graphics Meeting 之前的照片编辑工作坊只有 2-5 人参加。就我的"教学方法"而言，这是一个梦想——参与者真正参与其中，不仅仅是听讲，我们进行了富有成果的对话，特别要感谢 [@grubernd](/u/grubernd)，他是一名专业摄影师。我认为这是我在会议上迄今为止最成功、最"愉快"的工作坊。当然，大多数听众只是 Linux 爱好者，没有太多照片编辑经验，但他们很快就理解了重点，我想我可以说服他们中的一些人，spektrafilm 是一个出色的软件。当然，我还不知道实际的反馈是什么。会议上我不认识很多人，所以没怎么和人交流。整个会议只有两天，工作坊在周五，演讲在周六。嗯，虽然我绝对不是获奖演员，但因为我更像是在对话，所以实际上能够开口说话。只有一件事是我自己的错：我们只有投影仪，没有大屏幕（我本应该向组织者要一个屏幕），但用来展示 Kodak Portra 和 Kodak Gold 之间的区别已经足够了。

---

## #531 **Andrea** (@arctic) · 2026-04-15 18:07

听起来很成功！我非常高兴！感谢你分享这些见解，恭喜有 30 名参与者和这个好主意

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

## #532 **Upperechelonstr8up** (@upperechelonstr8up) · 2026-04-18 05:01

不，我指的是不同颜色之间以柔和且不完美的方式相互融合，而不是生硬干净的。针对这个话题进一步研究后，我觉得答案可能跟胶片型号有关。一个明显的例子（同样发生在2000年代末）可以在《绝命毒师》第一季和第二季之后的区别中看到。我听说这跟剧组从富士胶片换成了柯达胶片有关（以及换了不同的摄影师）。具体用了什么型号我不清楚，但我猜用的柯达胶片可能是某种更新更干净的改良版本，后来在业内广泛普及。

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/9/298f491d205f8947640111f7c9b4c502b8af3a49_2_690x339.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/9/298f491d205f8947640111f7c9b4c502b8af3a49_2_690x339.jpeg)

image1920×946 496 KB](/uploads/short-url/5VEyZ3PCfWNivrEJ3nHIe3jcrVv.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/c/fc5216bd3cdfa8c1c35b763618c89fc8ffa154f4_2_690x339.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/c/fc5216bd3cdfa8c1c35b763618c89fc8ffa154f4_2_690x339.jpeg)

image1920×946 275 KB](/uploads/short-url/A08cdsskZVIoWhoj8R95Uyxqscs.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/5/6513bd054f3c51fd1827b27eb54bf532ddd591a8_2_690x339.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/5/6513bd054f3c51fd1827b27eb54bf532ddd591a8_2_690x339.jpeg)

image1920×946 197 KB](/uploads/short-url/eqavQTKb1qpCfZ3LksVD2eq4gvC.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/d/6d7f9beea76f19681949be0a2d475f3eda98655f_2_690x339.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/d/6d7f9beea76f19681949be0a2d475f3eda98655f_2_690x339.jpeg)

image1920×946 377 KB](/uploads/short-url/fCFrCDUTWHNwv0hXHXx9Wxs7QBN.jpeg?dl=1)

第一季如上

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/7/a7bf16aa1d1aa7433464ba4bb5136d3caba20e3b_2_690x339.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/7/a7bf16aa1d1aa7433464ba4bb5136d3caba20e3b_2_690x339.jpeg)

image1920×946 361 KB](/uploads/short-url/nVX8R9mGHDiuiLWSBZqspdAqzaP.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/9/b917b755ae9962de02db7f07ca5f2c5507667aa8_2_690x339.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/9/b917b755ae9962de02db7f07ca5f2c5507667aa8_2_690x339.jpeg)

image1920×946 295 KB](/uploads/short-url/qpp8UcqOlflLmu17CL9MLq7XVvG.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/2/e2cad287e80ace6129a1988a207acab60a56a28e_2_690x339.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/2/e2cad287e80ace6129a1988a207acab60a56a28e_2_690x339.jpeg)

image1920×946 325 KB](/uploads/short-url/wmis6pj2XaNf3oOmvAqT6vzR4bI.jpeg?dl=1)

第三季如上

我不认为这两组图像的灯光差别很大，我已经尽量找相似构图的镜头了。胶片干净得多，在我看来，第三季的画面完全可以被认为是数码拍摄的，差别会非常小。

---

## #533 **** (@Thomsen) · 2026-04-18 08:14

可惜他们也换了摄影师，这就很难比较了。我大概理解你想表达的老胶片的感觉，但我不确定这到底是不同胶片型号、冲洗工艺、数字化流程（更多锐化），还是不同的摄影风格造成的。

我会认为这两组画面的灯光差别很大（比胶片型号的差别更大）：

强烈的阳光，阴影被压暗：

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/6/e683387af989a82f70545a91056ba9157410e953_2_345x169.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/6/e683387af989a82f70545a91056ba9157410e953_2_345x169.jpeg)

image1035×508 162 KB](/uploads/short-url/wTcXl5s6ffTDvBKZkdNR7MygPDR.jpeg?dl=1)

非常柔和的主光（Kinoflo或柔光箱）：

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/e/5ecedce9fa8b3226aec745cb328cddbc709d5de5_2_345x169.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/e/5ecedce9fa8b3226aec745cb328cddbc709d5de5_2_345x169.jpeg)

image1035×508 90.3 KB](/uploads/short-url/dwI5d2GOuR50H53CFKutr0yKGX3.jpeg?dl=1)

背光，带一点柔和的暖色补光提亮脸部

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/5/15efabcfa60457c6788ccb1f2e8c08e2d3116172_2_345x169.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/5/15efabcfa60457c6788ccb1f2e8c08e2d3116172_2_345x169.jpeg)

image1035×508 91.9 KB](/uploads/short-url/383weA8D1ZToInESj83fFGVT5cu.jpeg?dl=1)

低角度太阳，可能经过柔化（比第一季的外景镜头柔和温暖得多）

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/5/85ed609a2293bc3e93e908003a9b5cd44531093a_2_345x169.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/5/85ed609a2293bc3e93e908003a9b5cd44531093a_2_345x169.jpeg)

image1035×508 94.6 KB](/uploads/short-url/j6M55YIADzGNcqwBibx6mlcEZZw.jpeg?dl=1)

---

## #534 **WG** (@BPH3647) · 2026-04-18 14:32

可以理解！我用的方式相反。当一切看起来都不错，但高光部分还需要额外轻微压低时，这是个很好的方法。我把它和预闪结合使用，但额外的闪光对图像的影响比 `min` 函数更大且不同——至少在我看来是这样。

基础色调可能比你想象的更像一个特性，因为 RA-4 相纸确实有一种天然的基础色调，影响了最终效果。近年来的 Endura 实际上有相当暖的基底（有些批次甚至带绿色调）。

这是我试图与供应商核对 Endura 卷差异时做的对比。

[[![Kodak-Kodak-Compare-02](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/9/8934277a47b61f3700807a9faf419816d1d73465_2_345x455.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/8/9/8934277a47b61f3700807a9faf419816d1d73465_2_345x455.jpeg)

Kodak-Kodak-Compare-021364×1800 1.22 MB](/uploads/short-url/jzL9voTaZ7wT7CLLBx2PUfIcoJv.jpeg?dl=1)

我确实把这款软件用得很充分了，有些功能可能难以割舍，哈哈。最新版本的功能做得非常好，保存设置的功能让我的桌面免于堆满截图

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

---

## #535 **** (@mikae1) · 2026-04-18 22:02

> **@BPH3647** (帖子 #534):
> 保存设置的功能让我的桌面免于堆满截图

哈哈，感同身受！之前不知道有保存设置这个功能，谢谢！

---

## #536 **Andrea** (@arctic) · 2026-04-20 17:28

这很有意思，谢谢你的比较！

我们可以添加一个可调节的自定义基底，这样就可以创造性地调整最小密度和色偏，同时知道这会对预优化的中性灰校准产生一些影响。

我会试试看。

---

## #537 **None** (@Anthonygansauer) · 2026-04-20 19:17

如何在没有打印模拟的情况下使用反转片？

---

## #538 **Andrea** (@arctic) · 2026-04-20 19:51

目前在主分支和开发分支中，反转片默认不经过打印流程而直接扫描，但你随时可以点击/取消点击"扫描胶片"来切换。

---

## #539 **Vicer Fx** (@Vicer_Fx) · 2026-04-21 21:21

我这几天一直在摆弄这个工具，我爱上它了。你们有计划添加更老的胶片型号吗？我觉得能看到一些 Kodak 5247/5248 或 EXR 会很好。

---

## #540 **Andrea** (@arctic) · 2026-04-22 00:28

如果有特别外观或值得添加的胶片型号，那真是个非常好的主意！

很乐意了解那些被喜爱或者有历史意义的型号。

我找到了这个关于 5247 的资料：https://125px.com/docs/motionpicture/kodak/ti0835.pdf

还有这个关于 5248 EXR 的资料：https://125px.com/docs/motionpicture/kodak/5248.pdf

这个资料池里还有其他值得添加的吗？

https://125px.com/docs/motionpicture/kodak/

以及

> **@upperechelonstr8up** (帖子 #532):
> 不，我指的是不同颜色之间以柔和且不完美的方式相互融合，而不是生硬干净的。针对这个话题进一步研究后，我觉得答案可能跟胶片型号有关。

我想有一些老胶片的数据文件可能有助于获得老照片的感觉，所以拥有它们肯定不会有害处

[![:wink:](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)

> **@Thomsen** (帖子 #533):
> 我会认为这两组画面的灯光差别很大（比胶片型号的差别更大）

即使我同意 @Thomsen 的观点，即摄影、灯光、冲洗工艺和模拟后期制作对最终效果影响很大，胶片型号也只是众多因素之一。

---

## #541 **Tim** (@Soupy) · 2026-04-22 02:03

> **@arctic** (帖子 #540):
> 如果有特别外观或值得添加的胶片型号，那真是个非常好的主意！
> 很乐意了解那些被喜爱或者有历史意义的型号。

奥托克罗姆微粒彩屏干板！

---

## #542 **** (@Thomsen) · 2026-04-22 07:32

> **@arctic** (帖子 #540):
> 这个资料池里还有其他值得添加的吗？
> Index of /docs/motionpicture/kodak

如果你将来涉足黑白领域，Double-X 和 Tri-X 都是非常棒的胶片！

---

## #543 **Vicer Fx** (@Vicer_Fx) · 2026-04-22 19:33

https://125px.com/docs/motionpicture/kodak/lab/h15386.pdf 这是一款90年代的打印胶片，用于《阿甘正传》

https://filmcolors.org/wp-content/uploads/2015/02/Carl_Erwin_etal_Print5384_1982.pdf 这一款曾与 5247 搭配使用，用于《星球大战》、《夺宝奇兵》等。

我还觉得 Eterna 会是一个很好的补充（这个仓库也有其他数据文件）：[spectral_film_lut/datasheets/Fuji_3513DI.pdf at main · JanLohse/spectral_film_lut · GitHub](https://github.com/JanLohse/spectral_film_lut/blob/main/datasheets/Fuji_3513DI.pdf)

---

## #545 **None** (@Anthonygansauer) · 2026-04-22 23:00

[[![Datasheet](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/d/4dbfa176b22811ece7aa0e03d27450a526942c44_2_690x552.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/d/4dbfa176b22811ece7aa0e03d27450a526942c44_2_690x552.jpeg)

Datasheet5906×4725 3.79 MB](/uploads/short-url/b5NkAL07EhqVNiJNIxuJMr060yo.jpeg?dl=1)

没想到 TIFF 不能在聊天中打开，这里放 JPG

---

## #546 **None** (@Anthonygansauer) · 2026-04-22 23:14

调整打印曝光后，颜色真的非常非常接近了，只是色彩密度稍微有点偏差，需要把红色和蓝色压暗一点（或者也可能是因为这不是一个精确的比较）。

---

## #547 **Andrea** (@arctic) · 2026-04-23 00:01

谢谢你的对比 @Anthonygansauer！

你愿意也分享一下通过调整打印参数得到的更接近的匹配结果吗？

**附注**：能否编辑你之前发的那张 120MB PNG 的帖子，换成一个更小的文件？控制在几 MB 以内是对论坛维护者的巨大帮助，他们需要管理存储空间

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

我很高兴你提到红色和蓝色的评论。你说到了这个模拟中目前还不够稳固的一个非常有趣的点，我近期想在这个方面多下功夫。

你可以试着自己玩玩，使用 `advanced`>>`spectral upsampling` 面板中的 IR 和 UV 滤镜。目前这些数值只是目测的，但待办事项中有"找到更好的方法与真实图像匹配"。所以你的这个洞见非常宝贵。

本质上它们是虚拟滤镜，用于限制胶片感光度超出标准观察者灵敏度（人眼视觉）的蓝色和红色光谱区域。目前它们还非常随意，但对于控制光谱上采样算法在人类视觉区域之外的无约束行为是必要的。

[[![band_pass_and_portra_sensitivities](https://d2x313g9lpht1q.cloudfront.net/original/3X/3/8/3826a963bcb5dad6401167a08be5fdf1cd032cae.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/3/8/3826a963bcb5dad6401167a08be5fdf1cd032cae.png)

band_pass_and_portra_sensitivities640×494 59.1 KB](/uploads/short-url/80JznpYS67JBezJ8IupzSeasjP8.png?dl=1)

以上是当前默认滤镜的曲线图，可以看到在蓝色区域有一个明显的截止，而在红色一侧我们稍微宽松一些。

麻烦的是，在调整它们的同时也在干扰色彩平衡，总是需要重新优化打印滤镜。

这里有个例子：

[[![645nm -10Y -10M](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/b/cb72f594ac06ff2d262ca0b382d7930be942c42b.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/b/cb72f594ac06ff2d262ca0b382d7930be942c42b.jpeg)

645nm -10Y -10M640×426 160 KB](/uploads/short-url/t1NdZsiSRjmATL342aIQeS3QG0P.jpeg?dl=1)

[[![default filters](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/3/5391696b174d95949d8aa44227a91c0c155312be.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/3/5391696b174d95949d8aa44227a91c0c155312be.jpeg)

default filters640×426 164 KB](/uploads/short-url/bVhaKrdxGA1zCqXCpkQfaeSSfPU.jpeg?dl=1)

（左）410nm，8nm / 645nm，15nm 且 -10Y/-10M （右）默认，即 410nm，8nm / 675nm，15nm。所有其他参数完全相同且为默认。

每个滤镜有两个参数：（i）过渡中心，（ii）过渡宽度，单位均为纳米。

蓝色侧的工作原理与 UV 滤镜类似。

拥有高质量的数码/模拟对比对确实是猜测这些参数的一种方法。在理想世界中，我们应该为每种胶片优化一组滤镜，但总得有个起点。

[![:grin:](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)

---

## #548 **** (@mikae1) · 2026-04-23 14:42

我一直从 kodakprofessional.com 和 fujifilm.com 收集数据文件，并用 Wayback Machine 归档。它们可能也存在于那个在这个论坛上流传的开放目录里，但这里有来自可信来源的（希望是）最新版本。

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

搜索 `filetype:pdf "spectral" site:kodakprofessional.com`：

- [KODAK PROFESSIONAL PORTRA 160 Film](https://web.archive.org/web/20260423141218/https://kodakprofessional.com/sites/default/files/2025-07/e4051.pdf)
- [KODAK PROFESSIONAL PORTRA 400 Film](https://web.archive.org/web/20260423141234/https://kodakprofessional.com/sites/default/files/2025-07/e4050.pdf)
- [KODAK PROFESSIONAL PORTRA 800 Film](https://web.archive.org/web/20260423080046/https://kodakprofessional.com/sites/default/files/2025-07/e4040.pdf)
- KODAK GOLD 200 Film[[1](https://web.archive.org/web/20260423141334/https://kodakprofessional.com/sites/default/files/wysiwyg/E7022-1.pdf)][[2](https://web.archive.org/web/20260423141645/https://kodakprofessional.com/sites/default/files/wysiwyg/pro/resources/E7022%20Gold%20tech%20sheet.pdf)]
- [KODAK PROFESSIONAL EKTAR 100 Film](https://web.archive.org/web/20260423141327/https://www.kodakprofessional.com/sites/default/files/2025-07/e4046.pdf)
- [KODAK ULTRA MAX 400 Film](https://web.archive.org/web/20260423141703/https://www.kodakprofessional.com/sites/default/files/wysiwyg/KodakUltraMax400TechSheet-1.pdf)
- [KODAK PROFESSIONAL T-MAX 100 Film](https://web.archive.org/web/20260423141745/https://www.kodakprofessional.com/sites/default/files/wysiwyg/pro/resources/f4016_TMax_100.pdf)
- [KODAK PROFESSIONAL TRI-X 320 and 400 Films](https://web.archive.org/web/20260423141727/https://kodakprofessional.com/sites/default/files/wysiwyg/film/f4017_trix_320400.pdf)

搜索 `filetype:pdf site:fujifilm.com "spectral"`：

- [FUJICOLOR C200](https://web.archive.org/web/20260423143037/https://asset.fujifilm.com/master/emea/files/2020-10/98c3d5087c253f51c132a5d46059f131/films_c200_datasheet_01.pdf)
- [FUJICOLOR PRO 400H PROFESSIONAL](https://web.archive.org/save/https://asset.fujifilm.com/master/emea/files/2020-10/a6cb96275e4957ddc7b3ca932b7755e5/films_pro-400h_datasheet_01.pdf)
- [FUJICOLOR SUPERIA X-TRA 400 [CH]](https://web.archive.org/web/20260423143044/https://asset.fujifilm.com/master/emea/files/2020-10/9a958fdcc6bd1442a06f71e134b811f6/films_superia-xtra400_datasheet_01.pdf)
- [FUJICHROME PROVIA 100F Professional [RDPIII]](https://web.archive.org/web/20260423143257/https://asset.fujifilm.com/master/emea/files/2020-10/2c27854d5609945fbe7e48afc61f815d/films_provia-100f_datasheet_01.pdf)
- [FUJICHROME Velvia 100 Professional [RVP100]](https://web.archive.org/web/20260423143110/https://asset.fujifilm.com/master/emea/files/2020-10/2f3c7f90a0b0c6e605e84f98b7d489c2/films_velvia-100_datasheet_01.pdf)
- [FUJICHROME Velvia RVP for Professionals](https://web.archive.org/web/20260423143121/https://asset.fujifilm.com/www/us/files/2020-03/64873257f4644939d7bd75d95600a561/AF3-960E.pdf)
- [FUJICOLOR Nexia Zoom Master 800](https://web.archive.org/web/20260423143132/https://asset.fujifilm.com/www/jp/files/2019-09/47ce4268600cbc8f9d4d6cd15edb8e25/rd_report_ff_rd046_002.pdf)
- [Fujichrome PROVIA 400X](https://web.archive.org/web/20260423143344/https://asset.fujifilm.com/www/jp/files/2019-10/9de33adc9ad4a37e6be7947a9b289d55/rd_report_ff_rd052_002.pdf)
- [Fujicolor Super400/Nexia H400](https://web.archive.org/web/20260423143440/https://asset.fujifilm.com/www/jp/files/2019-09/016eb45e2174d5a03a79717257aa0118/rd_report_ff_rd044_002.pdf)
- [ETERNA-RDS 35mm Type 4791 (PET)](https://web.archive.org/web/20260423143501/https://asset.fujifilm.com/www/us/files/2023-10/8cb7293542ed10e48caad7eaacc5365a/eterna_rds.pdf)
- [NEOPAN 100 ACROS](https://web.archive.org/web/20260423143606/https://asset.fujifilm.com/www/us/files/2020-04/299395cd078366c7a2956af612ca9fdb/NeopanAcros100.pdf)
- [NEOPAN 100 ACROSII (135)](https://web.archive.org/web/20260423143628/https://asset.fujifilm.com/www/ca/files/2020-07/fb477bd9803b3c27ab592edcf9f3567c/AF3-0258E_PIB-NEOPAN-100-ACROSII-135-3_data-sheet.pdf)
- [NEOPAN 100 ACROSII (120)](https://web.archive.org/web/20260423143613/https://asset.fujifilm.com/www/au/files/2020-10/fe47fac3c002c381e48434f565fe44af/NEOPAN-100-ACROSII.pdf)
- [NEOPAN 1600 SUPER PRESTO](https://web.archive.org/web/20260423143627/https://asset.fujifilm.com/www/jp/files/2019-12/a80cda9888a206303c836f7ffd99709b/datasheet_neopan1600superpresto_en_01.pdf)
- [NEOPAN SS (135)](https://web.archive.org/web/20260423143802/https://asset.fujifilm.com/www/jp/files/2019-12/5cff4aeedafee45ce703f57552de76e6/datasheet_neopanss_en_01.pdf)
- [Development of New Color Reversal Film FUJICHROME "Velvia 100F and 100", and "ASTIA 100F"](https://web.archive.org/web/20260423143805/https://asset.fujifilm.com/www/jp/files/2019-10/d2a435c2e3c6481447ecdbc0c29d75f0/rd_report_ff_rd049_003.pdf)

---

## #549 **Andrea** (@arctic) · 2026-04-23 14:58

谢谢！！！我会把这些文件收集到我的个人收藏中，并尽快决定接下来数字化哪些。最近的矢量格式数据文件更容易数字化，因为可以轻松地从标签和网格中分离出来。

> **@mikae1** (帖子 #548):
> Development of New Color Reversal Film FUJICHROME "Velvia 100F and 100", and "ASTIA 100F"

我彻底爱上这个文件了

[![:heart_eyes:](https://discuss.pixls.us/images/emoji/apple/heart_eyes.png?v=12)](https://discuss.pixls.us/images/emoji/apple/heart_eyes.png?v=12)

我不懂日语，但它看起来信息量比一般的数据文件大得多，并且暗示了现代反转片高级内部运作的许多深度细节，比如看起来像是掩蔽成色剂（我目前没有在反转片中模拟）、颜色匹配函数、不同胶片的对比。它真的太美了。

顺便说一句，有趣的事实。数字化数据文件是一个非常手动化的过程，经过几天尝试修复 Kodak Portra 和 Supra 相纸的奇怪行为后，我发现它们的感光度波长轴拉伸了 50 nm（这相当大）。在尝试用更新方式处理数据文件时，理解绿色和这些相纸的问题让我快疯了。最后我一周前修好了它，现在主分支也没问题了。但钻牛角尖式的问题追踪也让我发现了额外的有趣细节。

---

## #550 **** (@mikae1) · 2026-04-23 15:11

没问题！

[![:heart:](https://discuss.pixls.us/images/emoji/apple/heart.png?v=12)](https://discuss.pixls.us/images/emoji/apple/heart.png?v=12)

> **@arctic** (帖子 #549):
> 我彻底爱上这个文件了，我不懂日语，但它看起来信息量比一般的数据文件大得多，并且暗示了现代反转片高级内部运作的许多深度细节，比如看起来像是掩蔽成色剂（我目前没有在反转片中模拟）、颜色匹配函数、不同胶片的对比。它真的太美了。

哦，我觉得我还找到了更多类似的，但当时以为它们可能没意思

[![:smiley:](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)

可能得再找找看！

---

## #551 **jo** (@hanatos) · 2026-04-23 15:26

> **@arctic** (帖子 #549):
> 最后我一周前修好了它，现在主分支也没问题了。

哎呀！我需要更新我的数据！

---

## #552 **Andrea** (@arctic) · 2026-04-23 15:39

更好的配置文件也即将推出，主要是更好地中性化了反转片，使白平衡在所选参考光源下在不同胶片间更加一致。这可能会去除一些特定特征，但会使配置文件更可用和可预测（并消除数据可能的色偏问题）。

另外还有一个更复杂的非线性方式来处理状态密度的分离（这对曲线的高密度部分很重要）。我还有一些测试要做，但会更新进展，以及它们是否会在最终视觉效果上显示出明显差异。

---

## #553 **None** (@Anthonygansauer) · 2026-04-23 19:33

[[![example](https://d2x313g9lpht1q.cloudfront.net/original/3X/e/c/ec362ede6d2181bcbb462d62605d0ab56c0cc2fc.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/e/c/ec362ede6d2181bcbb462d62605d0ab56c0cc2fc.jpeg)

example268×224 50.7 KB](/uploads/short-url/xHCLITdqKX7V3RkQ1XDPjtfEZYM.jpeg?dl=1)

匹配了密度和曝光，完全没有做颜色调整。几乎完美匹配。这真的太不可思议了

---

## #554 **None** (@Anthonygansauer) · 2026-04-23 19:41

过几天我会用我的尼康 F4 做一个真正的测试，因为我有两个 24mm 镜头可以适配我的 Lumix 和尼康。这真的是突破性的东西，伙计。

我对任何 Kodachrome 模拟都非常兴奋，因为它主要被使用的时候我还没出生呢，但我欣赏的所有那些国家地理、街头和摄影记者的作品——我迫不及待地想看到它的进一步发展！

---

## #555 **** (@mikae1) · 2026-04-23 19:43

> **@mikae1** (帖子 #550):
> 可能得再找找看！

这里有一些可能有趣的：

- [Fujifilm Professional Data Guide](https://web.archive.org/web/20260423192431/https://asset.fujifilm.com/www/ca/files/2020-03/d52487c5c6f84e7f935c299491c5c1ff/ProfessionalFilmDataGuide.pdf)
- [Development of Motion-picture Recording Film ETERNA-RDI](https://web.archive.org/web/20260423193633/https://asset.fujifilm.com/www/jp/files/2019-12/086cdc8636ea5ed63f24d1d3fc3df626/ff_rd053_001_en.pdf)
- [Development of Fujichrome ASTIA100](https://web.archive.org/web/20260423194023/https://asset.fujifilm.com/www/jp/files/2019-10/e4c329ecef963aa7eb37aabe23eb0364/rd_report_ff_rd043_001.pdf)

> **@arctic** (帖子 #549):
> 顺便说一句，有趣的事实。数字化数据文件是一个非常手动化的过程，经过几天尝试修复 Kodak Portra 和 Supra 相纸的奇怪行为后，我发现它们的感光度波长轴拉伸了 50 nm（这相当大）。这让我快疯了，最后我一周前修好了它。

这挺疯狂的，发现得好！喜欢听这些开发故事！

[![:smiley:](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)](https://discuss.pixls.us/images/emoji/apple/smiley.png?v=12)

---

## #556 **jo** (@hanatos) · 2026-04-24 07:10

<pre data-code-wrap="diff"><code class="lang-diff"> [
  null,
 - 1.012518727450156,
 - 1.7554564241334116
 + -1.2157949931727523,
 + -0.4946460830254054
  ],
</code></pre>

哦，是不是所有东西都变暗了很多？这是来自 portra 160 数据的 `log_sensitivity` 表。我还应该以什么其他方式重新归一化？如果不做进一步调整，所有东西都会渲染成黑色。当然也需要重新校准白平衡。

[编辑：暂时我把胶片曝光光强乘以了 `*1000.0`，大致恢复正常了。已更新 vkdt 数据至上游版本]

---

## #557 **Andrea** (@arctic) · 2026-04-24 12:31

在负片和正片中，我使用中灰 = [0.184, 0.184, 0.184] 的上采样光谱进行归一化（这本质上是经过带通滤波的参考光源，我把带通视为光谱上采样的一部分）。因此，当输入中灰时，三个通道的 log exposure 为零。光谱上采样光谱使用的代码与你去年分享给我的非常相似，希望我没有在那里添加其他奇怪的归一化。

对于打印介质，我使用由参考目标胶卷（Kodak 用 Portra 400，电影 Kodak 用 Vision3 250d，Fuji 相纸用 Pro 400h）的中密度值和放大机滤镜设置为 Y50M50(C0) CC 单位（100 柯达 CC 单位等于 1 OD，对于 Durst 放大机，100 步大约相当于 50CC）衰减后的打印光源来归一化感光度。这样，我就能在合理的范围内拟合出中性滤镜，而不会过多地推高放大机滤镜的密度。我还更改了滤镜的刻度，现在采用密度线性（因为真实放大机就是这样），避免滤镜值崩溃到 1。

---

## #558 **jo** (@hanatos) · 2026-04-27 09:22

> **@arctic** (帖子 #557):
> 在负片和正片中，我使用中灰 = [0.184, 0.184, 0.184] 的上采样光谱进行归一化（这本质上是经过带通滤波的参考光源，我把带通视为光谱上采样的一部分）。

啊，不错。听起来不错。我需要考虑一下紫色线上的颜色（有*凹陷*而非*凸起*的光谱）是会衰减到零，还是仅仅在最大评估范围处被截断。中灰光谱会衰减到零吗？还是这更多是关于 lambda 的频率域而非紫外线和近红外？

> **@arctic** (帖子 #557):
> 我还更改了滤镜的刻度，现在采用密度线性（因为真实放大机就是这样），避免滤镜值崩溃到

这听起来真的很有用。这是一个 UI 变更/破坏历史（但我一直在 filmsim 模块中这样做），但也是可能有助于白平衡优化器更稳定的东西。我可能也会尝试这个，尽可能贴近你的实现可能是个好主意。即使这些特定的变化更像是恒定的归一化偏移或参数灵敏度变化，很可能可以通过用户设置来补偿，通常不会导致不同的输出/表现力。

---

## #559 **Andrea** (@arctic) · 2026-04-27 19:12

> **@hanatos** (帖子 #558):
> 中灰光谱会衰减到零吗？还是这更多是关于 lambda 的频率域而非紫外线和近红外？

我不太确定极端紫色线的情况，我相当确定它会有问题，但周末我得到了一个支线任务的结果：尝试为每种胶片优化带通滤镜。结果可能对这些问题提供一些见解（也可能有陷阱）。当然欢迎任何反馈！

我写了一个小型优化器，拟合一个 6 参数的带通模型，以最小化真实测量光谱与上采样版本之间的 delta 曝光（损失函数是每个通道 log exposure 差值的总和）。很明显，这个问题本身就不完美，没有完美的解决方案，但对于许多胶片型号我们似乎可以做得不错，对其中一些则可以做得很好。

本质上，我们比较的是 integral(真实光谱 x 感光度) 和 integral(上采样光谱 x 感光度 x 带通)。我们可以将其视为减少近紫外/红外感光度或减少近紫外/红外上采样光谱能量。我使用以下指标监控结果：

\rho_i
= \max_{c \in \{R,G,B\}}
\frac{\left|H^{\mathrm{true}}_{i,c} - H^{\mathrm{hat}}_{i,c}\right|}{H^{\mathrm{true}}_{i,c}}.

其中 H^true 是真实测量光谱的曝光量，H^hat 是上采样带通光谱的曝光量。作为参考值，我们可以使用 1/20 档作为能产生可感知差异的最小 delta 曝光量，对应 rho_i 标度约为 0.035（rho_i < tau_phot = 0.035 应该非常优秀）。我们还可以将未校正情况下 rho_i > 8*tau_phot 的光谱定义为困难光谱。

我正尝试注入关于可见光谱边缘典型光谱行为的知识，以驯服上采样器。数据集由以下组成：(i) otsu2018 原始光谱数据集（他们在其上采样方法中使用的），(ii) nist 皮肤数据集，(iii) 森林颜色（锚定两个最重要的记忆色），以及 (iv) Munsell 数据集（损失中占比 50/20/20/10）。

[[![f02_xy-coverage__shared_corpus](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/1/21b64692e8bdc46548f0f9ef144a1c46b3c80ff1_2_690x509.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/1/21b64692e8bdc46548f0f9ef144a1c46b3c80ff1_2_690x509.png)

f02_xy-coverage__shared_corpus1992×1472 337 KB](/uploads/short-url/4OehnJ98LqBWcuZ3bTSs8dMvWvv.png?dl=1)

[[![f01_envelope__shared_corpus](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/7/c7c748f5b3214f63587a309e71d215b49d8b08ce_2_690x305.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/7/c7c748f5b3214f63587a309e71d215b49d8b08ce_2_690x305.png)

f01_envelope__shared_corpus2194×972 129 KB](/uploads/short-url/svjYVJoXUHcF18rgmHWkZ67CejY.png?dl=1)

可以看到皮肤和植被反射在近红外区有很强的能量，而 Munsell 有一些光谱在 400 nm 以下有能量。

如果现在为 **kodak_portra_400** 进行优化，并计算所有光谱的 rho_i，得到：

[[![f04_sens-window__kodak_portra_400_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c3](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/6/76e3c9c041ad83c4616e2cced766129b2a0bb886_2_690x727.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/6/76e3c9c041ad83c4616e2cced766129b2a0bb886_2_690x727.png)

f04_sens-window__kodak_portra_400_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c31925×2029 326 KB](/uploads/short-url/gXKngrjU67V9k8Kb0aaowcOcKr4.png?dl=1)

[[![f07_rho-ecdf__kodak_portra_400_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c3](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/6/067563145ff0a37634b3d281f62d273f2964a43c_2_690x665.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/6/067563145ff0a37634b3d281f62d273f2964a43c_2_690x665.png)

f07_rho-ecdf__kodak_portra_400_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c31457×1406 121 KB](/uploads/short-url/V8mEuO1f84gPH1ZoEaAq2ioUjy.png?dl=1)

[[![f06_xy-residual__kodak_portra_400_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c3](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/b/bbba4dafb240564bb1d4194fe132bf0541728e4b_2_690x391.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/b/bbba4dafb240564bb1d4194fe132bf0541728e4b_2_690x391.png)

f06_xy-residual__kodak_portra_400_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c31964×1114 346 KB](/uploads/short-url/qMIriw0humbWFLrqwr0limJnhrB.png?dl=1)

效果还可以，如预期远非完美，但对于典型的非尖峰光源泛化良好。

[[![f12_cross-illuminant__kodak_portra_400_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c3](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/2/a2ff1e5b49995e1c3813d3cb59170343ac6c1af3_2_690x448.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/2/a2ff1e5b49995e1c3813d3cb59170343ac6c1af3_2_690x448.png)

f12_cross-illuminant__kodak_portra_400_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c32188×1421 187 KB](/uploads/short-url/nfVWetGPOUBo4A8wa21qU7DbtKz.png?dl=1)

有些胶卷表现稍好一些，比如 **fujifilm_velvia_100**：

[[![f04_sens-window__fujifilm_velvia_100_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c3](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/b/0bb7644bb25942a749a70ea59ce160aa2e9cddbf_2_690x727.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/b/0bb7644bb25942a749a70ea59ce160aa2e9cddbf_2_690x727.png)

f04_sens-window__fujifilm_velvia_100_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c31925×2029 326 KB](/uploads/short-url/1FEamUJo2dN92uqHjOukgCNauu3.png?dl=1)

[[![f06_xy-residual__fujifilm_velvia_100_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c3](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/8/b80eecfb4183fe70f95b3e17f20d6f15d0f2debd_2_690x391.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/b/8/b80eecfb4183fe70f95b3e17f20d6f15d0f2debd_2_690x391.png)

f06_xy-residual__fujifilm_velvia_100_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c31964×1114 353 KB](/uploads/short-url/qgfPD4Mim2fjM2moL9FVHNNoyYZ.png?dl=1)

[[![f07_rho-ecdf__fujifilm_velvia_100_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c3](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/2/e2120c6593971015f0166dc72d53edd0ca4cccc7_2_690x663.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/2/e2120c6593971015f0166dc72d53edd0ca4cccc7_2_690x663.png)

f07_rho-ecdf__fujifilm_velvia_100_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c31463×1406 120 KB](/uploads/short-url/wfUzLzTf3PpPLlu2BiSElCDP01N.png?dl=1)

但你说得对，紫色受影响最大，会损失曝光，而非常饱和的紫色可能问题很大：

[[![f14_colorchecker_test__fujifilm_velvia_100_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c3](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/f/af1c3190464bfd891d9cb8ecdb88e2ac69d34c49_2_690x247.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/f/af1c3190464bfd891d9cb8ecdb88e2ac69d34c49_2_690x247.png)

f14_colorchecker_test__fujifilm_velvia_100_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c32194×788 93.8 KB](/uploads/short-url/oZ5XDmRr32r8gi3gpyspRaj7gHD.png?dl=1)

（我把校正和未校正的曝光量绘制成 sRGB，我知道这是亵渎

[![:see_no_evil:](https://discuss.pixls.us/images/emoji/apple/see_no_evil.png?v=12)](https://discuss.pixls.us/images/emoji/apple/see_no_evil.png?v=12)

但显示了在校正色块时修正的方向）

但对于 **kodak_portra_400**，我们仍然看到色卡紫色的改善：

[[![f14_colorchecker_test__kodak_portra_400_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c3](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/b/5b83642dd3606cdef86d2729e76b6993ac5989db_2_690x247.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/b/5b83642dd3606cdef86d2729e76b6993ac5989db_2_690x247.png)

f14_colorchecker_test__kodak_portra_400_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c32194×788 96.4 KB](/uploads/short-url/d3yXaO97EPGzY3HzeLBzXjWXrfB.png?dl=1)

[小更新]

我快速计算了 xy 平面上通道平均的 log_exposure 偏移 int(感光度 x 上采样光谱 x 窗口) / int(感光度 x 上采样光谱)，以更好地展示两种示例胶卷沿紫色线的曝光变化。这也是我们想要的对蓝色/红色的曝光改善，即我们通过基于语料库往返误差优化的带通滤波器减少它们的曝光量。对于不在语料库中且不影响问题的非常纯的颜色，欠曝可能过于严重。即使将它们加入优化，也可能不会显著改变整体改善。它可能会偏向更宽的带通滤波器，减少典型色域颜色的收益。因此语料库应该模拟我们想要成像的典型光谱，我们可能只能容忍紫色线上窄带光谱的问题。我确信一定有聪明的方法来解决这些问题，增加更多复杂性，但目前我对任何能获得的小改进都感到满意。

[[![f15_gain_map__kodak_portra_400_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c3](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/2/629dbe1a8aef29ee68e5c509d5e8bc5cd4d9b5ba_2_330x330.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/2/629dbe1a8aef29ee68e5c509d5e8bc5cd4d9b5ba_2_330x330.png)

f15_gain_map__kodak_portra_400_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c31167×1127 144 KB](/uploads/short-url/e4oKKzb8seSSqM1hwS714BtcTLI.png?dl=1)

[[![f15_gain_map__fujifilm_velvia_100_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c3](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/7/a7b305b5a50350c43a69269252c7051fb37ade5e_2_330x330.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/7/a7b305b5a50350c43a69269252c7051fb37ade5e_2_330x330.png)

f15_gain_map__fujifilm_velvia_100_hanatos2025_log_mse_perchan6_D55_3cab88db60a471c31167×1127 130 KB](/uploads/short-url/nVxi2Ux5BGDx94NcHFrJzpixu2O.png?dl=1)

---

## #560 **Vicer Fx** (@Vicer_Fx) · 2026-04-27 22:44

有一件事我发现自己在使用正片配置文件时想做，就是改变它们的白平衡。我在处理负片时通常使用打印滤镜。将来是否可以对正片做类似的功能？

顺便说一句，这些是我这几天跑的一些测试，我越来越喜欢这个程序了。是用一台不太好的智能手机拍摄的 RAW：

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/8/c8c162cab9446faedd99cfbc9a6aa7e47a6a5afe_2_690x912.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/8/c8c162cab9446faedd99cfbc9a6aa7e47a6a5afe_2_690x912.jpeg)

image975×1290 336 KB](/uploads/short-url/sDXOVMcxyN20EkO8CqvTrHJbrlA.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/8/f851abda516c5431cecc4bfec2926e725d21f151_2_690x919.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/8/f851abda516c5431cecc4bfec2926e725d21f151_2_690x919.jpeg)

image970×1293 316 KB](/uploads/short-url/zqJolfrRhVqgjo1DYAcL6Tx87Kx.jpeg?dl=1)

[[![image](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/1/91f4fe5c54b3f723843ca35fb72074ce0dddb385_2_690x920.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/1/91f4fe5c54b3f723843ca35fb72074ce0dddb385_2_690x920.jpeg)

image971×1295 247 KB](/uploads/short-url/kPc825ewK0MhtKR8AHRz1NBWmt7.jpeg?dl=1)

---

## #561 **Andrea** (@arctic) · 2026-04-28 04:47

> **@Vicer_Fx** (帖子 #560):
> 有一件事我发现自己在使用正片配置文件时想做，就是改变它们的白平衡。我在处理负片时通常使用打印滤镜。将来是否可以对正片做类似的功能？

即使反转片的打印不像负片那样普及（或者曾经不普及

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

），正片打印纸是存在的，并且计划中会有它。

目前你可以在处理 raw 时安全地更改白平衡，最终打印过程试图解决一个非常相似的问题，但在模拟介质和模拟工具的约束下。根据我的经验，结果是公平的，但由于 spektrafilm 遵循纯粹主义方法，使用虚拟放大机进行白平衡会让我感觉更好。

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

你能用智能手机的 raw 拍出好照片，太棒了！

---

## #562 **Andrea** (@arctic) · 2026-04-29 21:28

我刚刚在主仓库里上传了过去几周的一些更新：

- 更好的中性化配置文件。现在 Kodak Ultra Endura 是一种我觉得想用的好相纸了，之前几乎没法用。
- 更柔和的扩散滤镜和预设，模拟 GlimmerGlass/Black-Pro-Mist/Pro-Mist/CineBloom，可用于相机和放大机。
- 基于 Hanatos 方法，为每种胶片优化了用于光谱上采样的带通光谱滤镜，整体上红色和蓝色的色彩再现略好（过曝和过饱和减少），曝光误差从 20-15% 降低到约 5-10%（基于真实测量光谱曝光的往返测试粗略估算）。
- 抑制成色剂矩阵针对负片进行了算法上的初步优化，仍在进行中。
- 更好的散射光晕模型，可以拉伸高光以恢复可能被剪切的亮点辐照度。
- Kodak Verita 200d 电影胶片配置文件。

过去几周的开发不是最干净的，但我非常有动力，需要一些乐趣。我会清理的。我不是真正的程序员，这点应该很明显了

[![:laughing:](https://discuss.pixls.us/images/emoji/apple/laughing.png?v=12)](https://discuss.pixls.us/images/emoji/apple/laughing.png?v=12)

由于过去一个月有多个升级，我决定对硬盘随机文件夹中存放的一些不错的照片和 raw 文件进行快速编辑。其中很多我回忆过去用 agx-emulsion 很难获得好的效果。每次编辑大多使用默认设置，只有少量参数在每张图下方列出。所有 raw 文件直接加载到 spektrafilm 中，10-20 秒内完成编辑并保存为预览（计算仍然是一个痛点，时间远长于编辑本身！）。没有可爱的颗粒纹理

[![:cry:](https://discuss.pixls.us/images/emoji/apple/cry.png?v=12)](https://discuss.pixls.us/images/emoji/apple/cry.png?v=12)

我大量使用了扩散滤镜，并且只用了 Kodak 静物系列。它们都有非常相似的色彩灵魂，共享相同的 DIR 成色剂矩阵。因此饱和度某种程度上是民主分配的（我怀疑真实化学配方是否如此）。经过一些使用后，你会熟悉各胶片的冲击力度。恒定的 DIR 成色剂矩阵可能增强了这种饱和度/对比度的渐变。

基本上按饱和度和对比度排序大致如下：

Kodak Portra 160

Kodak Portra 400

Kodak Portra 800

Kodak Gold - Kodak UltraMax

Kodak Ektar

以及

Kodak Portra Endura

Kodak Supra Endura

Kodak Ektacolor Edge（稍旧的外观）

Kodak Endura Premier

Kodak Ultra Endura（复古外观）有点另类，具有独特个性

好的用户体验会使得这个尺度非常明确。

根据需要混合搭配胶片和相纸是一种快速而粗糙的方式，可以获得令人印象深刻的丰富色彩库。太阳底下无新事，我知道，但熟悉它们会让你在编辑时感到非常舒适。例如，Portra 胶片 + Portra 相纸是最中性和温和的。Ektar + Endura Premier 在尺度的另一端非常鲜艳。当需要更多或更少饱和度时，我们仍然可以用虚拟化学增减成色剂来作弊。

Ektar + Ultra Endura 的组合让我有些意外，对于需要一些个性且沉闷的照片来说，这是一个非常好的组合。Gold + Supra 是 Spektrafilm 的默认设置，位于冲击力堆叠的中上位置。

以下是编辑作品：

[[![001](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/6/56c7091e77f7ea5ae94cbf281a976f44a5705a31_2_426x640.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/6/56c7091e77f7ea5ae94cbf281a976f44a5705a31_2_426x640.jpeg)

001682×1024 346 KB](/uploads/short-url/cnFuE7YNdHLpyLvM42bYbbllhRf.jpeg?dl=1)

001 - signature edits JaroslavKriz33_IMG_3475.CR2

wb as-shot, kodak ektar+ultra, 0Y0M 1.1PE, cinebloom 0.5

[[![002](https://d2x313g9lpht1q.cloudfront.net/original/3X/3/a/3aa9d9995bf98ee79319f03aedcc3d1286c90703.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/3/a/3aa9d9995bf98ee79319f03aedcc3d1286c90703.jpeg)

002426×640 176 KB](/uploads/short-url/8mXAU2KMOgx7vh3FcdUK7Oj4Esb.jpeg?dl=1)

002 - signature edits Signature Edits Free RawsIMG_5824.CR2

wb as-shot, -6Y-4M 0.9PE, kodak gold+supra

[[![003](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/2/02985129441973fc86c62186aee7cdc2851d0f41.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/2/02985129441973fc86c62186aee7cdc2851d0f41.jpeg)

003640×427 124 KB](/uploads/short-url/mXi956muPKtcueaW4jPDmYTP7X.jpeg?dl=1)

003 - signature edits Signature Edits free raw files tag <span class="mention">@signatureeditsco</span> IMG_4563.cr2

wb daylight, kodak gold+ultra, 0.86PE -4Y-2M, pro-mist 0.5

[[![004](https://d2x313g9lpht1q.cloudfront.net/original/3X/f/2/f2efbfb01878dbbc0f0c2a71c986814c6e34d300.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/f/2/f2efbfb01878dbbc0f0c2a71c986814c6e34d300.jpeg)

004640×427 160 KB](/uploads/short-url/yF7cQDGkWn2kxsYVsmNTvYFMYdq.jpeg?dl=1)

004 - signature edits Free Raw Files - Tag <span class="mention">@signatureeditsco</span> - _MG_2862.CR2

wb as-shot, kodak gold+supra, 1.1PE -10Y0M, enlarger pro-mist 0.5

[[![005](https://d2x313g9lpht1q.cloudfront.net/original/3X/1/e/1e49661d302eeb02128490971a81c79ce3d52b2c.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/1/e/1e49661d302eeb02128490971a81c79ce3d52b2c.jpeg)

005640×427 131 KB](/uploads/short-url/4jVzZq9RB6vFhf5ZuVgKgT48TBW.jpeg?dl=1)

005 - play raw 5D3_0104.CR2 [Difficult orange flower](https://discuss.pixls.us/t/difficult-orange-flower/27001)

wb as-shot, kodak portra160+supra, 1.4PE 5Y15M, couplers 0.75, glimmerglass 2

[[![006](https://d2x313g9lpht1q.cloudfront.net/original/3X/d/c/dc64abe14f6c72bd846dbb20d9a09df33c0a9dcf.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/d/c/dc64abe14f6c72bd846dbb20d9a09df33c0a9dcf.jpeg)

006640×426 123 KB](/uploads/short-url/vrGJjW5a8aTeBQxFwV8rsQyoxgb.jpeg?dl=1)

006 - play raw 20250225_0032.CR3 [Dealing with yellow color shift](https://discuss.pixls.us/t/dealing-with-yellow-color-shift/48530)

wb as-shot, kodak portra800+supra, 0.6PE 5Y0M, couplers 0.85

[[![007](https://d2x313g9lpht1q.cloudfront.net/original/3X/8/7/87dd572bdfcb59f08c41b9f512a43f57e5a29877.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/8/7/87dd572bdfcb59f08c41b9f512a43f57e5a29877.jpeg)

007640×427 94.8 KB](/uploads/short-url/jnUG3Fj1zDgQIneyUX5AyXR2Fmv.jpeg?dl=1)

007 - play raw 20240422_0008.CR2 [Fishing for a sunset](https://discuss.pixls.us/t/fishing-for-a-sunset/43275)

wb as-shot, kodak portra400+supra, 0.58PE 10Y0M, couplers 0.85, cinebloom 0.5

[[![008](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/a/5ad5f568e17cb363d3f29c6f6de98b130ac1f838.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/a/5ad5f568e17cb363d3f29c6f6de98b130ac1f838.jpeg)

008640×427 157 KB](/uploads/short-url/cXznlD0HD8GKZZ1cIFZDovUo5QI.jpeg?dl=1)

008 - play raw 7E4A0518.CR3 [[PlayRaw] Flower](https://discuss.pixls.us/t/playraw-flower/47431)

wb as-shot, kodak ultramax+supra, 1.5PE -2Y15M, enlarger black-pro-mist 0.5

[[![009](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/3/03dff35218c9e7f737ec3437cd63a82a619f796a.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/3/03dff35218c9e7f737ec3437cd63a82a619f796a.jpeg)

009640×424 125 KB](/uploads/short-url/yhf8fWEAyGXsajaDYbLdlz8gJQ.jpeg?dl=1)

009 - play raw IMGP2775.DNG [Pride orange smile, sharpness and color challenge](https://discuss.pixls.us/t/pride-orange-smile-sharpness-and-color-challenge/46225)

wb as-shot, kodak gold+supra, 0.5PE -5Y-2M, black-pro-mist 0.5

[[![010](https://d2x313g9lpht1q.cloudfront.net/original/3X/6/a/6a8d2a22c7e2639359120d2b194a1257199c30b1.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/6/a/6a8d2a22c7e2639359120d2b194a1257199c30b1.jpeg)

010640×427 137 KB](/uploads/short-url/fcB3rMiKPTddTdg9bB7xfb3cBH3.jpeg?dl=1)

010 - play raw _DSC5869.ARW [Golden Gate sunset](https://discuss.pixls.us/t/golden-gate-sunset/55098)

wb as-shot, kodak portra400+supra, 0.9PE 2Y-6M, couplers 0.74, glimmerglass 1

---

## #563 **Andrea** (@arctic) · 2026-04-29 21:33

[[![011](https://d2x313g9lpht1q.cloudfront.net/original/3X/b/5/b5fb8dfba633fd30482e1213e4eae6675c05cf3c.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/b/5/b5fb8dfba633fd30482e1213e4eae6675c05cf3c.jpeg)

011640×427 169 KB](/uploads/short-url/pXTnhcc4rQnnvRezdjMcwtGqsaM.jpeg?dl=1)

play raw - IMGP9542.DNG [Winter photo editing](https://discuss.pixls.us/t/winter-photo-editing/47259)

wb as-shot, kodak gold+supra, 0.76PE -1Y-2M, black-pro-mist 0.5

[[![012](https://d2x313g9lpht1q.cloudfront.net/original/3X/7/d/7d2488d5ce287e51a95dd0a52b671784b990a7b9.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/7/d/7d2488d5ce287e51a95dd0a52b671784b990a7b9.jpeg)

012640×427 128 KB](/uploads/short-url/hR3Xr0gKMcwqGZFLndMZbaRUBn3.jpeg?dl=1)

play raw - DSCF8379.raf [Playing with different light colors](https://discuss.pixls.us/t/playing-with-different-light-colors/48178)

wb as-shot, kodak gold+supra, 1PE 0Y0M (一切默认)

[[![013](https://d2x313g9lpht1q.cloudfront.net/original/3X/e/c/ecb72bd702353f6f4f1bbde7dd278ef7373f31b5.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/e/c/ecb72bd702353f6f4f1bbde7dd278ef7373f31b5.jpeg)

013640×427 138 KB](/uploads/short-url/xM57MSjZsYE93jO7YcWTb7MmEyF.jpeg?dl=1)

play raw - R0000418.DNG [Office building at night, London](https://discuss.pixls.us/t/office-building-at-night-london/43642)

wb tungsten, kodak vision3 500t+ultra, 0.5PE 5Y0M, highlights boost ev 10 boost range 0.5, halation (30%,0.5%,0) 200um, enlarger pro.mist 0.5

[[![014](https://d2x313g9lpht1q.cloudfront.net/original/3X/f/b/fb164903445ec78938dea1afd37ffcda10294df0.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/f/b/fb164903445ec78938dea1afd37ffcda10294df0.jpeg)

014640×427 127 KB](/uploads/short-url/zPdADtXZ2B5cNPkehoTR7iDQKXu.jpeg?dl=1)

play raw - 2024-02-25_12-13-25.NEF [Ocean Overlook to Play With](https://discuss.pixls.us/t/ocean-overlook-to-play-with/47407)

wb as-shot, koadk ektar+ultra, 0.8PE -12Y-2M, couplers 1.3

[[![015](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/7/5764fd79c7adfb65d9ecec6f4cfcd2351d985fa8.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/7/5764fd79c7adfb65d9ecec6f4cfcd2351d985fa8.jpeg)

015640×426 228 KB](/uploads/short-url/ct7UrdahEEvWPKijKEfS6NlAW4U.jpeg?dl=1)

play raw - 20250412_0039.ARW [Frame within a frame - #2 by Zbyma72age](https://discuss.pixls.us/t/frame-within-a-frame/49429/2)

wb as-shot, kodak ektar+ultra, 1PE 8Y3M

[[![016](https://d2x313g9lpht1q.cloudfront.net/original/3X/9/9/99fd498cc26750df8258e2cfb4cf633c5502be5c.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/9/9/99fd498cc26750df8258e2cfb4cf633c5502be5c.jpeg)

016426×640 193 KB](/uploads/short-url/lYfIy0BHgFM1j6ec9EAnw01iLHS.jpeg?dl=1)

paly raw - 2014-09-04_19-09-27.cr2 [A tree in the sun](https://discuss.pixls.us/t/a-tree-in-the-sun/43109)

wb as-shot, kodak ektar+ultra, 0.5PE 15Y5M, glimmerglass 1

[[![017](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/2/0299388c4c56f14360339932e06da592d8ce6ff9.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/2/0299388c4c56f14360339932e06da592d8ce6ff9.jpeg)

017640×427 192 KB](/uploads/short-url/mZecZiDJyLVkUPfqSbRAiFYpzH.jpeg?dl=1)

play raw - DSC_5188.NEF [Cologne train station by night](https://discuss.pixls.us/t/cologne-train-station-by-night/39092)

wb as-shot, kodak ektar-ultra, 0.5PE 30M5Y, black-pro-mist 0.5

[[![018](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/0/00b3ea80400c3455dbd5f65cab9e193bbc03bf90.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/0/00b3ea80400c3455dbd5f65cab9e193bbc03bf90.jpeg)

018640×427 122 KB](/uploads/short-url/6dt27xWbvJVkQYGTqXpo7PU6Pe.jpeg?dl=1)

play raw 20241031_0873.RAF [Dramatic Shadows Exercise](https://discuss.pixls.us/t/dramatic-shadows-exercise/47398)

wb as-shot, kodak ektar-ultra, 0.8PE -13Y-4M, pro-mist 0.5

[[![019](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/c/ac626449496468395610de9c12c0d178f1ce710e.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/c/ac626449496468395610de9c12c0d178f1ce710e.jpeg)

019640×427 97.9 KB](/uploads/short-url/oAYVyd9kEQVnMOuknjIaKl3TORo.jpeg?dl=1)

play raw DSC07735.ARW [I have to share this with you all....](https://discuss.pixls.us/t/i-have-to-share-this-with-you-all/48259)

wb as-shot, kodak ektar+ultra, 0.6PE -16Y-12M, couplers 1.3

很难说清楚改进在哪里，很多可能是安慰剂效应，但我感觉图像比以前更"令人满意"了，以前光谱上采样中的带通滤波器是随意设置的，没有控制。

---

## #564 **Mica** (@paperdigits) · 2026-04-30 01:06

> **@arctic** (帖子 #562):
> 我不是真正的程序员

抱歉老大，你有一个能运行的程序，不断改进，还有用户。

[![:wink:](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)

---

## #565 **None** (@lanidor) · 2026-04-30 10:28

谢谢 @arctic 的更新，颜色现在看起来真的很好！我想问一下，有没有办法调整颗粒行为？目前黑色区域完全是黑的，这在我扫描的图像中看不到。我试过 *Glare*，但它看起来均匀且单色。我附上一个例子：第一张是用 Spektrafilm 处理的数码图像，第二张是用 Minolta Dimage Scan Elite 5400 II 扫描的反转负片。我可以提供更多独立例子，这是唯一一张我用数码和胶片拍摄同一场景的。

[[![Spektrafilm](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/8/d8dc3d9ee239a0edf1a72e46f4b1eade02739fc5_2_690x460.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/d/8/d8dc3d9ee239a0edf1a72e46f4b1eade02739fc5_2_690x460.jpeg)

Spektrafilm7694×5138 2.84 MB](/uploads/short-url/uWqZP3nzQkZ5jaw6FgUETvuFmNn.jpeg?dl=1)

[[![Gold200-DimageScan5400II-q45](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/8/08b13ba939e9653dce01ac8c324519d6eeaab270_2_690x457.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/8/08b13ba939e9653dce01ac8c324519d6eeaab270_2_690x457.jpeg)

Gold200-DimageScan5400II-q457800×5168 3.44 MB](/uploads/short-url/1eTxt5ar8WdudeGAESmJ5Ob03pC.jpeg?dl=1)

---

## #566 **** (@Thomsen) · 2026-04-30 11:56

干得漂亮！颜色看起来非常好。但纹理和"感觉"在低图像分辨率和相机扩散滤镜下有点难以评估。

你有新模型的高分辨率非扩散例子吗？

---

## #567 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-04-30 14:21

这些看起来太惊艳了！

你改变了我的生活，我非常感激能发现这个程序。

请继续按照你感到舒适的速度改进和探索吧

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

再次感谢你的工作！

---

## #568 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-04-30 15:10

我想我发现在最新的主分支版本中选择不同反转片时，DIR 成色剂有一个 bug。已在 GitHub 页面上提交问题！

---

## #569 **None** (@Anthonygansauer) · 2026-04-30 23:51

[[![123](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/b/fb040249eb63766cbe2f7333d523bde5d1ae8cc8_2_690x862.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/b/fb040249eb63766cbe2f7333d523bde5d1ae8cc8_2_690x862.jpeg)

1231000×1250 1.17 MB](/uploads/short-url/zOAqV3wQNq2EWPZaZ2J9qvw2Hxe.jpeg?dl=1)

让它与我的打印风格匹配了！这个程序真棒。

很快将会有一个 1:1 对比：通过这个流程处理的 raw 图像与使用真实的 Portra 400 拍摄并打印在 Fuji Type II 上的相同图像，迫不及待想分享

---

## #570 **Todd Prior** (@priort) · 2026-05-01 03:50

我非常喜欢这些颜色，但我觉得它特别暗？？？

---

## #571 **** (@Thomsen) · 2026-05-01 09:01

真漂亮！你用了数码放大机扩散吗？

---

## #572 **** (@mikae1) · 2026-05-01 10:15

> **@Anthonygansauer** (帖子 #569):
> 让它与我的打印风格匹配了！这个程序真棒。

不错！你用了什么设置来达到那种效果？

> **@priort** (帖子 #570):
> 我非常喜欢这些颜色，但我觉得它特别暗？？？

有点暗，但是一种风格选择？在数码时代，很多摄影师（包括我）某种程度上被困在"把数据分布到直方图上"的思维里。

我认为从传统画家那里汲取更多灵感是有益的。试着在 Vermeer 的画作中找出任何接近 255/255/255 的东西。其原因不仅仅是技术上的（老化、有限的颜料范围、颜料成本）。

[[![pieter-de-hooch-binnenplaats-met-rokende-man-en-drinkende-vrouw-mh0835-mauritshuis](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/d/5df2f78e159683b5de7d51373097b27ced8b9d1a_2_690x830.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/d/5df2f78e159683b5de7d51373097b27ced8b9d1a_2_690x830.jpeg)

pieter-de-hooch-binnenplaats-met-rokende-man-en-drinkende-vrouw-mh0835-mauritshuis1200×1444 1.62 MB](/uploads/short-url/dp6Xt3Xsr3IRlZXa6nyu1rYr0dI.jpeg?dl=1)

---

## #573 **Nuno Paulino** (@hatsnp) · 2026-05-01 10:24

当修复工作从这些古老画作上去除 10 层清漆，露出更自然的色调时，总是一种享受。

---

## #574 **None** (@Anthonygansauer) · 2026-05-01 12:49

"特别"暗？可能我只是太习惯这种风格了，我不觉得特别暗。强烈的阳光下你要么舍弃阴影要么舍弃高光，我宁愿保住高光。

---

## #575 **None** (@Anthonygansauer) · 2026-05-01 12:51

说得再好不过了。Sargent、Vermeer、Eakins、Manet 是我打印和构图时的巨大灵感来源！

---

## #576 **Todd Prior** (@priort) · 2026-05-01 14:01

我在校准过的显示器上看，有几个人的脸几乎完全在黑暗中……所以可能是我这边的问题，或者你选的显示亮度较高（至少比我的高），或者这完全就是你想要的效果……只是一个观察

---

## #577 **** (@europlatus) · 2026-05-01 16:48

> **@priort** (帖子 #576):
> 有几个人的脸几乎完全在黑暗中……所以可能是我这边的问题

所有脸在我屏幕上都能看到。听起来是你那边的问题。

---

## #578 **Todd Prior** (@priort) · 2026-05-01 17:35

嗯，我得检查一下。我用的标准亮度是 120 cd/m2

---

## #579 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-05-01 18:04

想分享一些我用 spektrafilm 编辑的照片

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

有些已经是 6 个月前的了！可惜有些照片我没有 raw 文件，不然可以看看模拟效果提升了多少。

我的目标是创造高质量中画幅胶片扫描的外观，颗粒很少，而不是真实的暗房打印。请欣赏！

<div class="lightbox-wrapper">[[![2](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/7/a712c707641725f7199a8fb1ebf91489f8e7df68_2_689x472.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/7/a712c707641725f7199a8fb1ebf91489f8e7df68_2_689x472.jpeg)

24960×3400 676 KB](/uploads/short-url/nPZY1iAfvFtPslXIvYJ5yjDG2DK.jpeg?dl=1)

[[![16](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/2/72af90cc6f0f0108b8f1a0edbafe928096b7c002_2_690x912.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/2/72af90cc6f0f0108b8f1a0edbafe928096b7c002_2_690x912.jpeg)

163032×4009 463 KB](/uploads/short-url/gmyzUA9TD6VJiuRNuf3uhI3QdmG.jpeg?dl=1)

[[![21](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/5/c5ff52e97c18dc6b4bd4ad4b472b0780a4b46041_2_690x527.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/5/c5ff52e97c18dc6b4bd4ad4b472b0780a4b46041_2_690x527.jpeg)

214248×3246 852 KB](/uploads/short-url/sfz5C6ymaO11Y34cLlW950dhofT.jpeg?dl=1)

[[![output41](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/c/3c45e70f77d36daf7a1675348b6a860268544213_2_690x504.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/c/3c45e70f77d36daf7a1675348b6a860268544213_2_690x504.jpeg)

output414630×3382 1.12 MB](/uploads/short-url/8BcpEHjNNplvfjUZt4z2QQrbEaL.jpeg?dl=1)

</div>

---

## #580 **** (@mino) · 2026-05-01 18:47

这些太美了，谢谢分享 :-)! 那张城市照片完全就是托尼霍克职业滑板 2 里威尼斯海滩的水平 ;-)。

---

## #581 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-05-01 19:19

我想多发一些，但我是这个论坛的新成员，还不能哈哈！

---

## #582 **Andrea** (@arctic) · 2026-05-01 23:05

> **@lanidor** (帖子 #565):
> 想问一下，有没有办法调整颗粒行为

我将来会尝试改进颗粒效果，它还没有得到模型其他部分那样的关注。你可以尝试提高 `grain >> density_min`，这会增加灰雾度，即图像未曝光部分的颗粒。不过，在虚拟相纸上打印时，你可能看不到太大变化，因为在正确曝光的负片和打印中，动态范围大致落在负片曲线的线性部分。

> **@Thomsen** (帖子 #566):
> 你有新模型的高分辨率非扩散例子吗？

有的，我会贴几张有问题的图片，在前后对比中展示差异

> **@Anthonygansauer** (帖子 #569):
> 让它与我的打印风格匹配了！这个程序真棒。

看起来太惊艳了，我非常感谢你建议探索放大机中的扩散滤镜。

总的来说，我非常感谢大家的所有反馈，这里涌现了大量好主意。

> **@Anthonygansauer** (帖子 #569):
> 很快将会有一个 1:1 对比：通过这个流程处理的 raw 图像与使用真实的 Portra 400 拍摄并打印在 Fuji Type II 上的相同图像，迫不及待想分享

那听起来非常有用，我期待看到更多比较！

> **@Mateusz_Grabowski** (帖子 #567):
> 你改变了我的生活，我非常感激能发现这个程序。

这个评论让我受宠若惊

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

> **@Mateusz_Grabowski** (帖子 #579):
> 我的目标是创造高质量中画幅胶片扫描的外观，颗粒很少，而不是真实的暗房打印。

很酷的照片，谢谢分享。从理论上讲，将胶片尺寸从 35mm 改为 70mm（或你目标中的胶片尺寸）应该会以物理上有意义的方式考虑颗粒的缩放。也就是说，如果你认为 35mm 的颗粒在某个参数集下是合理的，那么改变胶片尺寸会为大尺寸胶片提供相同的渲染效果。

---

## #583 **Aedan** (@chaert-s) · 2026-05-01 23:45

大家好，

这看起来是一个了不起的项目！巧合的是，我也一直在考虑开发一个非常类似的工具，看来我可能会加入进来！

首先，我要脱帽致敬，这看起来真的太棒了！非常感谢你投入的工作和奉献，制作出如此精确、接近真实的工具！

我有一个想法，你可以改进颗粒模拟的准确性。我想到 Newson 等人的 "Realistic Film Grain Rendering" 和 "A Stochastic Film Grain Model for Resolution-Independent Rendering" 这两篇论文。它们有一个非常扎实的方法。我还没有深入了解你的代码，但看起来你可能已经采用了这些论文中的一些元素，但似乎省略了昂贵的蒙特卡洛估计？如果添加这个用于"最终质量"渲染，可能会改善颗粒效果？

第二个想法是将其移植到 C#/C++ 以获得更快的推理。Python 是一门很棒的语言，设置起来非常快，但代价是内存膨胀和执行速度较慢。

如果你允许的话，我想尝试将这个很酷的工具移植到 C 变体，并尝试让它用于视频，作为一个真正的胶片模拟工具，用于 DaVinci Resolve 或其他视频编辑程序？

祝好，

Aedan

---

## #584 **Yogansh Bhatt** (@Yogansh_Bhatt) · 2026-05-02 03:03

VKDT 运行得非常漂亮！那些 GPU 着色器真快。你可能想看看 filmsim，那是移植到那里的模块。

---

## #585 **Ryan Cara** (@Ryan_Cara) · 2026-05-02 03:24

我一直在开发一个小工具，可以根据 Spektrafilm 中制作的 json 预设导出 LUT（来自 ART 的 spektrafilm_mklut.py 脚本），如果有人想试试的话。我想在即将到来的视频拍摄中使用它们。

<aside class="onebox githubrepo" data-onebox-src="https://github.com/ryancara/Spektrafilm-LUT-Generator">
 <header class="source">

 [github.com](https://github.com/ryancara/Spektrafilm-LUT-Generator)
 </header>

 <article class="onebox-body">




[![图片594](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/8/0809706a8090d3db85d31b732f21a06f98928269.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/8/0809706a8090d3db85d31b732f21a06f98928269.png)


### [GitHub - ryancara/Spektrafilm-LUT-Generator: Generates a CLF or Cube LUT from Arctic's...](https://github.com/ryancara/Spektrafilm-LUT-Generator)


<span class="github-repo-description">从 Arctic 的 Spektrafilm 光谱胶片模拟应用生成 CLF 或 Cube LUT。</span>

 </article>











</aside>

在 Spektrafilm 的 GUI 中加入这个功能可能是个很酷的功能

[![:blush:](https://discuss.pixls.us/images/emoji/apple/blush.png?v=12)](https://discuss.pixls.us/images/emoji/apple/blush.png?v=12)

---


## #586 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-05-02 06:58

在我看来，LUT 导出的功能非常必要。我已经成功创建了 haldclut 并将其转换为 cube lut，但目前仅限于 srgb 色彩空间。在 DaVinci Resolve 中处理视频时效果很棒！

另外，如果能绕过胶片模拟，只保留打印模拟就好了。我确实在拍胶片，昨天突然想到，如果能将负片的线性 DSLR 扫描导入 spektrafilm，只使用相纸打印模拟，那该多好！

或者，能够单独导出打印 LUT 并在其他软件中应用也可以

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

当然，如果能单独导出胶片 LUT 而不包含打印部分，那就更好了

[![:slightly_smiling_face:](https://discuss.pixls.us/images/emoji/apple/slightly_smiling_face.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slightly_smiling_face.png?v=12)

 也许用 Cineon Film Log 格式也可以。

---

## #587 **jo** (@hanatos) · 2026-05-02 08:23

> **@Ryan_Cara** (帖子 #585):
> 导出一个 LUT

请记住，LUT 无法编码某些非全局效果（成色剂、光晕、颗粒）。

> **@Yogansh_Bhatt** (帖子 #584):
> VKDT 运行得非常漂亮！那些 GPU 着色器太快了

谢谢

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 vkdt 在 16MP 图像上使用成色剂、颗粒和光晕只需要 15ms（RTX 4080S）。不确定你针对的是哪种视频输出分辨率，在 2k 下这是个位数毫秒级。vkdt 有 ffmpeg/prores 输入和输出，如果你遇到任何特定视频格式的问题，请告诉我。

---

## #588 **Ryan Cara** (@Ryan_Cara) · 2026-05-02 08:23

我确实也尝试过让 HALD 工作，但没能弄清楚色彩空间的问题。另外，我相信你可以绕过打印部分，直接获取胶片感光乳剂的 LUT

[![:slightly_smiling_face:](https://discuss.pixls.us/images/emoji/apple/slightly_smiling_face.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slightly_smiling_face.png?v=12)

 （反之则不行）。

---

## #589 **** (@Thomsen) · 2026-05-02 11:31

在此呈现——光谱胶片模拟中的挪威女王。

[[![Queen](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/1/51c3b915c43749b12a727db16d7915704dcbd131_2_690x459.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/1/51c3b915c43749b12a727db16d7915704dcbd131_2_690x459.jpeg)

Queen5000×3327 2.37 MB](/uploads/short-url/bFk0BbPrW3x43iBrR6AUwpQAtYR.jpeg?dl=1)

（她的外套是个麻烦，红色通道过曝得厉害。多亏在 VKDT 中用 ych 色度 vs 色度曲线才拉了回来）。

---

## #590 **** (@mino) · 2026-05-02 12:13

看来 [@arctic](/u/arctic) 获得了“*国际王室认可*”徽章。好照片

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 ！

---

## #591 **Ryan Cara** (@Ryan_Cara) · 2026-05-02 12:17

> **@hanatos** (帖子 #587):
> 请记住，LUT 无法编码某些非全局效果（成色剂、光晕、颗粒）。

所有成色剂参数都是非全局的吗？我原本以为"数量"滑块（DIR 全局乘数）是可以用 LUT 编码的（像 ART 中那样）？

颗粒、光晕和扩散已经没有被考虑在内了。

我真的需要测试一下 VKDT 中的视频功能！

---

## #592 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-05-02 12:50

有一些参数会影响锐度。我把它们设为 0，LUT 似乎工作得非常好。不过我没有对它们进行压力测试。

---

## #593 **None** (@Anthonygansauer) · 2026-05-02 19:37

[[![Low Res01](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/d/1d0404981e2b2f702af5d1f9219b81af6e30eb7d_2_690x862.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/d/1d0404981e2b2f702af5d1f9219b81af6e30eb7d_2_690x862.jpeg)

Low Res011000×1250 1.22 MB](/uploads/short-url/48GsddQKds41vpMUxHAazs0g4Ut.jpeg?dl=1)

[[![Low Res 02](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/5/1510681b701fd267c79fcb5c45c527ff42fae2a4_2_690x862.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/5/1510681b701fd267c79fcb5c45c527ff42fae2a4_2_690x862.jpeg)

Low Res 021000×1250 822 KB](/uploads/short-url/30lb2fyOWU1yQzvSGowNU2WggFm.jpeg?dl=1)

一张是数字 RAW 经过 spektral 处理，一张是胶片暗房打印，数字的所有调整都在程序中完成，在 Photoshop 中做了一些轻微的分色调调整！这东西太震撼了

---

## #594 **None** (@Anthonygansauer) · 2026-05-02 19:43

哦对了，我也在 Photoshop 中匹配了边框，并进行了锐化以匹配 6x7 的细节。

[[![low res raw](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/9/e98625159c33bbe75887302c62e712e90ac6ae07_2_690x862.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/9/e98625159c33bbe75887302c62e712e90ac6ae07_2_690x862.jpeg)

low res raw1000×1250 706 KB](/uploads/short-url/xjQEAukM3p9dkWLUdto3P6SdQbl.jpeg?dl=1)

这是归一化后的 RAW

---

## #595 **None** (@Anthonygansauer) · 2026-05-02 19:45

[[![film scan low res](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/a/1ab90920980e84428fcbdfb15082d1298a99ef74_2_690x845.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/a/1ab90920980e84428fcbdfb15082d1298a99ef74_2_690x845.jpeg)

film scan low res1000×1226 1.19 MB](/uploads/short-url/3OoQMmw7nobIaUWRZ31zF9we9FO.jpeg?dl=1)

这是用 Noritsu 扫描仪扫描的胶片

---

## #596 **WG** (@BPH3647) · 2026-05-02 22:06

这让我后悔当初在处理控制条流程时没有买一台密度计。

[@arctic](/u/arctic) 关于导出/保存的快速问题：

有没有办法指定保存的文件类型？我用的是 M1 Mac，主分支，在正片成色剂修复之前。它通常保存为 .png，但也有个奇怪的习惯，会随机选择 .jpg。早期版本导出了 .tif，希望能回到那个格式，因为它符合我的工作流程。

---

## #597 **WG** (@BPH3647) · 2026-05-02 22:14

[@Anthonygansauer](/u/anthonygansauer) 你抢先一步做了对比！真棒！你觉得需要花多少时间去调整那些精细的设置（成色剂/红外和紫外滤镜）？

分享一些 Json 设置文件应该会很有趣。

---

## #598 **None** (@Anthonygansauer) · 2026-05-03 00:25

需要编辑的地方不多！预闪用得很多，比我想象的要多。我会把 RAW 和打印文件放到 Google Drive 上，供大家自己尝试。我回到电脑后也会把保存的设置文件链接发出来

---

## #599 **jo** (@hanatos) · 2026-05-03 08:28

> **@Ryan_Cara** (帖子 #591):
> 所有成色剂参数都是非全局的吗？

嗯，成色剂会先扩散一点，然后才会发挥作用/影响颜色。

> **@Ryan_Cara** (帖子 #591):
> 我原本以为"数量"滑块（DIR 全局乘数）是可以用 LUT 编码的（像 ART 中那样）？

抱歉，不知道 ART 中是如何实现的。也许只是忽略了扩散，假设它保持在亚像素级别。

---

## #600 **Andrea** (@arctic) · 2026-05-03 11:50

> **@chaert-s** (帖子 #583):
> 我想到了"真实胶片颗粒渲染"和"用于分辨率无关渲染的随机胶片颗粒模型"，都是 Newson 等人写的。

嘿 Aedan，欢迎来到论坛

我深入阅读了这篇论文，我认为这是一项很棒的工作。它有很多优点，但也有不足（顺便说一句，很乐意深入讨论这个问题

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 ）。spektrafilm 中的实现在某些层面上做了简化，在其他方面则要先进得多。最终目标是匹配真实胶片的测量漫射 RMS 颗粒度曲线——真正的胶片颗粒外观，真实的真理。

例如来自 kodak vision3 250d 的以下数据：

[[![image](https://d2x313g9lpht1q.cloudfront.net/original/3X/8/3/8315b9bc08f02575641138325a63b3ae34062b10.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/8/3/8315b9bc08f02575641138325a63b3ae34062b10.png)

image608×567 28.9 KB](/uploads/short-url/iHD5Ux95J3ZiluUJVB1ZQCGlvfW.png?dl=1)

Newson 等人的模型在设置分辨率无关问题方面令人印象深刻，但他们未能将模型精细调整到真实数据上。在这个过程中你很快就会意识到，至少如果你想在"正确的表示/流程步骤"中处理彩色胶片，你需要胶片模拟的周边部分。论文中展示的彩色应用非常仓促，我相信它可能与测量的漫射颗粒度相差甚远。

这种追求更好颗粒的努力也是我的切入点，这也是我在这个玩具项目的早期历史中非常简短的小结。

> **@chaert-s** (帖子 #583):
> 我想到的第二件事是将其移植到 C#/C++ 以获得更快的推理速度。

我把 Python 实现看作一个快速而粗糙的测试平台。模型仍在大量开发中。在过去几周里，我几乎每天都在 GUI 中修改参数输入

[![:rofl:](https://discuss.pixls.us/images/emoji/apple/rofl.png?v=12)](https://discuss.pixls.us/images/emoji/apple/rofl.png?v=12)

 而 Python 给了我这样的人一种实现方式。目前我更多地专注于数学和概念（通过分享我简陋的小 GUI 和 pixls.us 这个神奇的地方，获得了大量聪明反馈和想法）。

[@hanatos](/u/hanatos) 的 super vkdt 实现是我能想到的最佳性能，比 Python 实现快了三个数量级

[![:exploding_head:](https://discuss.pixls.us/images/emoji/apple/exploding_head.png?v=12)](https://discuss.pixls.us/images/emoji/apple/exploding_head.png?v=12)

无论如何，好主意永远是好主意，我相信探索视频方面会很有趣。只是目前摄影是我的驱动力，因为它也是我的爱好。

> **@Thomsen** (帖子 #589):
> 在此呈现——光谱胶片模拟中的挪威女王。

这让我会心一笑

> **@Anthonygansauer** (帖子 #593):
> 一张是数字 RAW 经过 spektral 处理，一张是胶片暗房打印，数字的所有调整都在程序中完成，在 Photoshop 中做了一些轻微的分色调调整！这东西太震撼了

太棒了！非常感谢你带来这类数据和对比。我看到衬衫的颜色有些不同，还有一些其他的小偏移，但总体非常惊人。照片和模特也很棒！在理想世界中，拥有这种模拟/真实数据至少原则上能让我们实现简单的色彩调优策略。不过不确定我们是否想打开那个潘多拉魔盒。作为一个非常简单的第一步，拥有这样的对比可以说是验证抑制成色剂总体量的最佳方式。

总之很棒 [@Anthonygansauer](/u/anthonygansauer) ！

> **@BPH3647** (帖子 #596):
> 有没有办法指定保存的文件类型？

目前如果你在文件名中添加扩展名，它就会以该格式保存。我最近把默认格式从 png 改成了 jpg。我认为对于保存高分辨率图像来说，这是更合理的默认设置。不过在某个地方添加默认格式输出选项很容易。我记下了这个建议。

> **@Anthonygansauer** (帖子 #598):
> 预闪用得很多

这非常有趣，也符合关于论文基础的讨论 >> 那里可以做一些工作

> **@BPH3647** (帖子 #534):
> 这是我试图解决与供应商之间关于 Endura 胶卷差异时做的对比。
> Kodak-Kodak-Compare-021364×1800 1.22 MB

> **@hanatos** (帖子 #599):
> 抱歉，不知道 ART 中是如何实现的

ART 是通过绕过所有非局部和随机效应来计算 LUT，本质上只编码了平场的"平均"输出（减去目前仅随机的眩光）。

---

## #601 **Andrea** (@arctic) · 2026-05-03 12:07

> **@Thomsen** (帖子 #566):
> 但纹理和"感觉"有点难以评价

以下是用新模型生成的一些全分辨率裁切：

（我顺便添加了长程成色剂扩散，尚未提交。它使 MTF 在低频处提升了几个百分点，并考虑了由于不均匀性或显影剂扩散导致的 Levy 型扩散，如果你仔细观察，会看到抑制成色剂长程扩散带来的一点局部对比度）。

[[![no_coupler_diffusion_no_halation-scattering](https://d2x313g9lpht1q.cloudfront.net/original/3X/4/0/40f605d5563a2e6b2e63e13c4f2b3c21b34968c2.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/4/0/40f605d5563a2e6b2e63e13c4f2b3c21b34968c2.png)

no_coupler_diffusion_no_halation-scattering563×563 637 KB](/uploads/short-url/9gFET6ObVi62EBahAf9QwjyWJO2.png?dl=1)

[[![only_halation-scattering](https://d2x313g9lpht1q.cloudfront.net/original/3X/4/e/4e7f86a94f1adb63f445b15afcad2db38a0f14ce.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/4/e/4e7f86a94f1adb63f445b15afcad2db38a0f14ce.png)

only_halation-scattering563×563 628 KB](/uploads/short-url/bcqsT3jso9SsQiom2GRYj0HGav4.png?dl=1)

[[![full_diffusion_model](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/0/0050722925c9020f3fb359fb00ea5a176ce9e80c.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/0/0050722925c9020f3fb359fb00ea5a176ce9e80c.png)

full_diffusion_model563×563 630 KB](/uploads/short-url/2MlZcOy00RMW0GWEPKa3Tn9vDm.png?dl=1)

（左）无扩散效果，（中）仅光晕/散射，（右）完整扩散模型。

[[![only_dir_coupler_diffusion](https://d2x313g9lpht1q.cloudfront.net/original/3X/7/b/7b8ba22b27a5a1e5ac2392b08830dd92703776fb.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/7/b/7b8ba22b27a5a1e5ac2392b08830dd92703776fb.png)

only_dir_coupler_diffusion563×563 646 KB](/uploads/short-url/hCVTjBycS7cm0tY9vNMwKg1b0bp.png?dl=1)

这里仅展示 DIR 成色剂扩散，无光晕/散射，供参考。

目前默认参数基于对我信赖的参考 portra 400 胶片的粗略调整，当然我们还可以做更多，比如现代/复古/旧式预设，或者半自动分析所有胶卷的特性。这些天我只是希望一天能有 48 小时，并且不需要为了买食物而工作

[![:rofl:](https://discuss.pixls.us/images/emoji/apple/rofl.png?v=12)](https://discuss.pixls.us/images/emoji/apple/rofl.png?v=12)

这里是 portra 400 数据手册 MTF 与模型模拟 MTF 测量的对比

[[![mtf_kodak_portra_400](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/3/c356c71cb374353073f7066fa26761abb06b8df3.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/3/c356c71cb374353073f7066fa26761abb06b8df3.png)

mtf_kodak_portra_400560×562 23.6 KB](/uploads/short-url/rS31GQXNSUeSNAU58ckuKpAA25R.png?dl=1)

[[![mtf_simulated_kodak_portra_400_mod0.2_2-100cy](https://d2x313g9lpht1q.cloudfront.net/original/3X/1/2/12a39c11fdf33611e1dc8bd25098cfb48215753b.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/1/2/12a39c11fdf33611e1dc8bd25098cfb48215753b.png)

mtf_simulated_kodak_portra_400_mod0.2_2-100cy630×630 39.5 KB](/uploads/short-url/2ET7QmArvOwTsw87mXR3aKf5rnR.png?dl=1)

---

## #602 **** (@slazaar) · 2026-05-04 09:01

大家好，

首先，我想说我很欣赏这个项目以及这里令人难以置信的丰富讨论——它在我上手过程中提供了巨大的帮助。

我有一个新手问题，可能对其他人也有帮助，尤其是在最近更新之后。

根据 README，我的理解是推荐的工作流程：

**RAW → darktable → 32-bit float TIFF（线性，无 filmic/sigmoid，ProPhoto RGB）**

这对于 RAW 文件（无需转换）来说按预期工作。

但是，我不确定我的 TIFF 工作流程，以及我是否在早期引入了问题。

目前我的做法是：

**RAW → Photoshop → Adobe RGB TIFF → darktable → 线性 ProPhoto RGB**

当我通过 *import rgb* 导入这些 TIFF 时，结果似乎有问题——所以我想知道 Photoshop 步骤（以及 Adobe RGB 转换）是否导致与预期输入不匹配。

[[![Screenshot 2026-05-04 at 6.59.46 PM](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/9/e94f07fe7e78087db6c7cff694f4af0097cc685c_2_689x463.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/9/e94f07fe7e78087db6c7cff694f4af0097cc685c_2_689x463.png)

Screenshot 2026-05-04 at 6.59.46 PM2558×1718 2.6 MB](/uploads/short-url/xhWzBmTQGy0H0yRymLtlzXNszbm.png?dl=1)

如果能把这个问题弄清楚就太好了，因为我想很多人会希望在 Photoshop 中修图，然后使用 spectral film 作为最终处理。

再次感谢大家分享的所有工作和知识——非常感谢任何指导！

---

## #603 **Ryan Cara** (@Ryan_Cara) · 2026-05-04 12:14

我认为如果可能的话，在 Spekatrafilm 之后做 Photoshop 工作会容易得多。Spektrafilm 现在可以加载 RAW 文件。

如果你坚持要先用 Photoshop，可能需要先做几个步骤。当将 RAW 导入 Photoshop 时，它会打开"Camera Raw"——确保你使用的是线性相机配置文件。之后，你需要确保它是以正确的色彩空间/伽玛值导入 Photoshop 的，以便保持在场景参考模式下（这通常在 Camera Raw 窗口的底部……或者有一个设置齿轮）。

之后你需要从 Photoshop 导出，也要保持场景参考模式。所以是线性/Prophoto？然后你可以把它导入 Spektra。

不过我认为在场景线性模式下用 Photoshop 工作会很困难，除非它应用了显示变换！

编辑：其实没有我想象的那么复杂。我上传了一个小视频展示这个过程。你需要一个线性相机配置文件。我用的是 Cobalt 的，但自己做一个也不难。

（另外，视频中我没有展示，但你需要将 Spektrafilm 中的输入色彩空间改为 ACES2065-1）：

<aside class="onebox googledrive" data-onebox-src="https://drive.google.com/file/d/1zOHb2yeEPDe_SleImqx_6pvzAFIMPlUv/view?usp=share_link">
 <header class="source">

 [drive.google.com](https://drive.google.com/file/d/1zOHb2yeEPDe_SleImqx_6pvzAFIMPlUv/view?usp=share_link)
 </header>

 <article class="onebox-body">
 [](https://drive.google.com/file/d/1zOHb2yeEPDe_SleImqx_6pvzAFIMPlUv/view?usp=share_link)

### [How to.mov](https://drive.google.com/file/d/1zOHb2yeEPDe_SleImqx_6pvzAFIMPlUv/view?usp=share_link)

Google Drive file.

 </article>











</aside>

---

## #604 **None** (@Anthonygansauer) · 2026-05-04 15:22

[[![dwonsized](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/e/1eb39be1330a607409334082dca5dfe8a1b9340c_2_690x552.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/e/1eb39be1330a607409334082dca5dfe8a1b9340c_2_690x552.jpeg)

dwonsized1000×800 953 KB](/uploads/short-url/4nB8kHvQm77n50CeixVTjwamFpG.jpeg?dl=1)

简直难以置信

---

## #605 **None** (@Anthonygansauer) · 2026-05-04 15:34

[https://drive.google.com/drive/folders/1ryifCcPHbDQoFiofn46u1Wiymi4RoxdE?usp=sharing](https://drive.google.com/drive/folders/1ryifCcPHbDQoFiofn46u1Wiymi4RoxdE?usp=sharing)

这是 Google Drive 链接，大家可以自己匹配和尝试！

包括：

使用 Pentax 67ii + 105mm f2.4 + Portra 400 + Fuji DPii 相纸的 RA4 打印，由 Epson V600 扫描

同一帧使用 Noritsu HS-1800 扫描仪的胶片扫描

使用 50mm f1.4 拍摄的同一帧的 Lumix S5ii 数字 RAW

用于匹配打印效果的 GUI 参数预设

---

## #606 **None** (@Anthonygansauer) · 2026-05-04 15:53

[[![For group](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/f/9f73cd1b6fd6003fa84a78a74be0a822134e24f7_2_690x862.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/f/9f73cd1b6fd6003fa84a78a74be0a822134e24f7_2_690x862.jpeg)

For group1000×1250 760 KB](/uploads/short-url/mKA1hG3cUTtOOYxJgl0zk14zEZ9.jpeg?dl=1)

[[![Digital Emulation _2](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/8/785a8afaec38aa4f0cbfa9f04f2b2095f977d78d_2_690x862.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/8/785a8afaec38aa4f0cbfa9f04f2b2095f977d78d_2_690x862.jpeg)

Digital Emulation _21000×1250 1.2 MB](/uploads/short-url/haHhAyyuNtSjZEaQfgx6QWslO3P.jpeg?dl=1)

另一个测试

上面是真实胶片 + RA4 打印扫描

下面是数字模拟。

所有编辑都是匹配黑点

---

## #608 **** (@Cristian) · 2026-05-04 16:17

太棒了！能分享一下这张照片的 GUI 参数预设吗？

---

## #610 **None** (@Anthonygansauer) · 2026-05-04 16:50

就是 Google Drive 里的那个！

---

## #611 **** (@Cristian) · 2026-05-04 17:00

谢谢！

---

## #612 **None** (@Anthonygansauer) · 2026-05-04 17:50

[[![IMG_6798](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/f/9f0d6b74d2d2eca7129e3cd3323e0a1b2e3464bc_2_690x504.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/f/9f0d6b74d2d2eca7129e3cd3323e0a1b2e3464bc_2_690x504.jpeg)

IMG_67981284×939 1.54 MB](/uploads/short-url/mH2FvvgASoNrzbqnapvaaPwwWQs.jpeg?dl=1)

[

再附上一张 Ektachrome 100 模拟，纯属娱乐。我亲自拍摄了 -5EV 到 +5EV 的色卡，用我的 Lumix S5ii 拍摄 Vlog，用我的 Nikon F4 拍摄 Ektachrome，然后进行匹配。Lumix S5 系列的优点在于你可以对静态照片使用 3D LUT。这张照片是相机直出。基本上是无限的 Ektachrome！我还没有进行 1:1 测试，但很快了！

---

## #613 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-05-04 18:45

哦哇！我有 S5IIX，所以那个 3D LUT 功能可能用得上。目前只用于视频预览。

我的两卷 120 格式的 Velvia 50 和 E100 还在等某个特殊的场合

[![:wink:](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)

---

## #614 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-05-04 18:52

这是我昨天用 spektrafilm 导出的 haldclut 制作的视频。包含成色剂！

 <iframe src="https://www.youtube.com/embed/_MZatpGIlRo?feature=oembed&wmode=opaque" width="480" height="360" frameborder="0" allowfullscreen="" class="youtube-onebox" seamless="seamless" sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox allow-presentation"></iframe>

所有内容都是用 lumix s5iix 以 5000K 白平衡在 V-Log 模式下使用 Helios 44-2 镜头拍摄的。

只用了 Kodak 200D 打印在 2393 上的 LUT。

在 DaVinci Resolve 中只调整了曝光、对比度和中继点，加上一些 gate weave 和光晕效果。部分片段做了微小的饱和度和打印机灯光调整。跳过了颗粒，因为无论我怎么做，经过 YT 压缩后都无法看起来很好。敬请欣赏！

---

## #615 **** (@mikae1) · 2026-05-04 19:58

> **@arctic** (帖子 #601):
> 这些天我只是希望一天能有 48 小时，并且不需要为了买食物而工作

如果这个项目能获得更多曝光，我相信通过众筹这不是一个无法实现的目标。但我想这也伴随着资助者（他们并不总是熟悉开源软件开发）的新期望。

> **@Ryan_Cara** (帖子 #603):
> 我认为如果可能的话，在 Spekatrafilm 之后做 Photoshop 工作会容易得多。Spektrafilm 现在可以加载 RAW 文件。

这样灵活性会差很多，而且会把值推到 Spektrafilm 设定的"边界"之外。

我的做法是像往常一样在 darktable 中编辑，开启 sigmoid。在 sigmoid 之后/之上放置 `LUT 3D` 模块，使用 Portra 400 NC 的 LUT。然后在 darktable 中使用组合了蒙版的 `tone equalizer` 和 `rgb curve` 模块进行透视校正、降噪和局部加减光。准备好后，禁用 `sigmoid`、`LUT 3D` 和 `color balance rgb`，以线性 ProPhoto RGB 导出为 32 位（浮点）OpenEXR，然后在 Spektrafilm 中打开。效果很好，但有点繁琐。至少比实际暗房要简单。

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 希望有一天能看到 Spektrafilm 集成到 darktable 中……

---

## #616 **None** (@sahuaro.senorita) · 2026-05-04 20:30

大家好，可能是个愚蠢的问题，但我终于（看似）在我的 Mac 上用 uv 成功安装了这个。完成后终端显示"已安装 1 个可执行文件：**spektrafilm**"——但我不知道在哪里找到这个可执行文件，也不知道如何运行它。抱歉如果这很明显，但下一步是什么？我如何找到并运行它？

---

## #617 **** (@mikae1) · 2026-05-04 20:35

> **@sahuaro.senorita** (帖子 #616):
> 我如何找到并运行它？

像这样：

> **@arctic** (帖子 #525):
>
```
uvx --from git+https://github.com/andreavolpato/spektrafilm.git@dev spektrafilm

```

---

## #619 **Ryan Cara** (@Ryan_Cara) · 2026-05-04 23:36

我同意，但 Salazar 想在使用 Spektrafilm 之前用 Photoshop 进行修图工作！我提供的方法会把值推到边界之外吗？如果是的话，[@slazaar](/u/slazaar)，也许值得走 Darktable（导出 Prophoto RGB Linear）→ Photoshop → Spektrafilm 的路线。从 Prophoto RGB（伽玛值为 1.8）转换为 ACES 2065-1 可能不太理想，但不幸的是 Camera Raw 在这方面似乎缺少一些选项。

---

## #620 **** (@slazaar) · 2026-05-05 02:04

非常有帮助——谢谢两位（+mikae1）

我对 darktable 还比较陌生，但看到它对 RAW 管线的控制能力真的很有趣。

我通常使用 Capture One 工作，但据我所知，它除了提供一个线性曲线选项外，并不能真正提供场景线性工作流（我认为 Camera Raw 也是如此），所以这开启了一种不同的处理方式。

我会尝试一些建议的方法——很高兴除了常规的 C1 / Camera Raw 路线之外还有其他准备文件的选项。

---

## #621 **None** (@Anthonygansauer) · 2026-05-05 02:07

[[![digital chart](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/0/c04b95a267f06766fa63646e609cc948e0003a2a_2_690x552.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/c/0/c04b95a267f06766fa63646e609cc948e0003a2a_2_690x552.jpeg)

digital chart1000×800 776 KB](/uploads/short-url/rr7C1SaSHxAzl7wuXsUxpoksZcK.jpeg?dl=1)

[[![RA4 Chart](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/8/68895fe91605c8357a05ff0136e4bc9d91ddec53_2_690x552.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/8/68895fe91605c8357a05ff0136e4bc9d91ddec53_2_690x552.jpeg)

RA4 Chart1000×800 514 KB](/uploads/short-url/eULYO21bOiQtsm2lEBeCxiySgaT.jpeg?dl=1)

在 Google Drive 中添加了一个 RAW 文件 + 色卡的 RA4 打印，供大家尝试匹配。正在努力让数字匹配打印效果，也许你们可以试试？

portra 400 + Fuji DPii

Lumix S5ii RAW

[https://drive.google.com/drive/u/0/folders/1ryifCcPHbDQoFiofn46u1Wiymi4RoxdE](https://drive.google.com/drive/u/0/folders/1ryifCcPHbDQoFiofn46u1Wiymi4RoxdE)

---

## #622 **** (@RoughDraftWriting) · 2026-05-05 04:45

太美了！你只是把 hald 图像拉进 spectra film 吗？你是如何得到 LUT 输出并让它在 Resolve 中工作的？我很想制作一些适用于 DWG/DWI 的 spektrafilm LUT。

---

## #623 **John A** (@John_A) · 2026-05-05 05:19

这个模拟与 Genesis 有什么不同吗？

---

## #624 **Ryan Cara** (@Ryan_Cara) · 2026-05-05 05:50

你可以试试我上周发布的这个工具，使用 CST 从 DWG/intermediate 转换到 AP0/Linear。

<aside class="onebox githubrepo" data-onebox-src="https://github.com/ryancara/Spektrafilm-LUT-Generator">
 <header class="source">

 [github.com](https://github.com/ryancara/Spektrafilm-LUT-Generator)
 </header>

 <article class="onebox-body">




[![图片625](https://d2x313g9lpht1q.cloudfront.net/original/3X/2/9/29a0b4676637c17dd2e4d0782c924c6a7574c29c.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/2/9/29a0b4676637c17dd2e4d0782c924c6a7574c29c.png)


### [GitHub - ryancara/Spektrafilm-LUT-Generator: Generates a CLF or Cube LUT from Arctic's...](https://github.com/ryancara/Spektrafilm-LUT-Generator)


<span class="github-repo-description">Generates a CLF or Cube LUT from Arctic's Spektrafilm spectral film simulation app.</span>

 </article>











</aside>

另外也有人指出 VKDT 非常适合视频。这周我试了一下，效果很好……尤其是 LUT 无法实现的 Spektral 的所有空间特性。

---

## #625 **** (@janogarcia) · 2026-05-05 06:37

目前为止模拟模拟打印和 S5II RAW 的例子真是太棒了。

[![:ok_hand:](https://discuss.pixls.us/images/emoji/apple/ok_hand.png?v=12)](https://discuss.pixls.us/images/emoji/apple/ok_hand.png?v=12)

[![:sparkles:](https://discuss.pixls.us/images/emoji/apple/sparkles.png?v=12)](https://discuss.pixls.us/images/emoji/apple/sparkles.png?v=12)

至于同样出色的 S5II 机内 Ektachrome LUT，能否分享一下？

我还没有 S5II/S5IIx，但我很乐意用一些 RAW 样本进行实验，并尝试使用 Lattice 将其适配到 Magic Lantern RAW 视频（Canon 5D III）上。

---

## #626 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-05-05 07:44

是的，我就是这样做的。不过仅限于 srgb。我在 DWG 中进行了所有调色，并将 LUT 放在色彩空间转换到 rec709/2.4 之后的最后一个节点。效果足够好！

---

## #627 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-05-05 07:46

希望这周末有空的时候试试

[![:slightly_smiling_face:](https://discuss.pixls.us/images/emoji/apple/slightly_smiling_face.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slightly_smiling_face.png?v=12)

---

## #628 **Dissipatio ** (@Dissipatio) · 2026-05-05 07:59

Andrea，谢谢。

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

Spectral 太棒了。

我使用 DxO 进行光学校正和 AI 预锐化/降噪，导出为线性 DNG，然后使用 Spectral。

---

## #629 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-05-05 08:01

我找到了一个很好很简单的程序叫 PNG2Cube。可以将 hald 图像转换为 cube lut。

---

## #630 **jo** (@hanatos) · 2026-05-05 08:13

> **@arctic** (帖子 #559):
> hanatos:

中间灰的光谱会衰减到零吗？还是说这更多的是关于频域（相对于波长），而不仅仅是紫外和近红外？

我不确定极端的紫色线，我相当确定它会有问题，但在周末我从一个支线任务中得到了些结果：尝试为每种胶卷优化带通滤波器。结果可能对这些问题提供一些见解（也可能有陷阱）。当然欢迎任何反馈！

</blockquote>
</aside>

哈哈，你跟得太快了，我跟不上

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

这是 cc24 中一些绿色和饱和品红色的图：

[[![20260505_09h53m20s_grim](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/9/a9ba287b0eabb806df557e4b03d6654270e42b32.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/9/a9ba287b0eabb806df557e4b03d6654270e42b32.png)

20260505_09h53m20s_grim565×715 74.7 KB](/uploads/short-url/odtx8rBxmDn6umgDL4RoLXfApHQ.png?dl=1)

由于 sigmoid 光谱的性质，它们基于二次/抛物线，要么有峰要么有谷。在蓝色、白色和红色之间的这个粗略三角形中的任何东西都有一个"谷"的形状，不会在边缘处衰减到零。

这些光谱经过优化，可以在针对 1931 CMF 和 D65 光源积分时往返/精确重现 RGB 值。如果我理解正确的话，你基本上是在尝试校正这一点，使上采样更接近特定胶片感光剂灵敏度的同色异谱空间，而不是人类观察者的 CMF。

如果这确实在视觉上产生很大差异，那就打开了一个全新的兔子洞……在这种情况下，最好为每种胶卷的灵敏度优化光谱上采样（然后可以达到近乎完美的匹配），同时也提出了一个问题，即这是否应该作为设备输入变换进行，即使用原始相机 RGB 作为输入。这已经是一个非常不适定的问题（vkdt 有一些基于相机光谱灵敏度的输入设备变换，如果你拥有它们的话）。我有点犹豫是否要在这里添加事后修正，尽管光谱加窗是有意义的。

顺便问一下，窗口的模拟对应物是什么？胶片中有红外/紫外阻挡层吗，还是这通常发生在玻璃/镀膜中？我的意思是，在实际的模拟世界中，这取决于胶卷本身，还是仅仅是数据的数值后处理？

---

## #631 **Andrea** (@arctic) · 2026-05-05 11:58

> **@Anthonygansauer** (帖子 #605):
> 这是 Google Drive 链接，大家可以自己匹配和尝试！

非常感谢，接下来几天我会很忙，但我很快就会试试！太棒了！

我特别想试试色卡照片，因为我在周末对光谱上采样的灵敏度适应模型做了一些改进。

> **@Anthonygansauer** (帖子 #606):
> 上面是真实胶片 + RA4 打印扫描

这些太出色了！！！

> **@Anthonygansauer** (帖子 #612):
> Lumix S5 系列的优点在于你可以对静态照片使用 3D LUT。

我最终买了 Lumix S9 并进行了实验，我买这台相机纯粹是为了静态照片的 3D LUT 功能，以及使用 log 视频管线（VLog）拍摄静态照片的能力。在我看来，Lumix 视频管线的纹理非常好，不像静态管线那么过度锐化，噪点也更平滑。我很快会发一些照片。这里有几张随机 SOOC 的照片，刚好在我手机上。

[[![P1000602](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/e/aeb783b5fb743c852a64eb98d4a937a7dbbc20f2_2_690x253.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/e/aeb783b5fb743c852a64eb98d4a937a7dbbc20f2_2_690x253.jpeg)

P10006026000×2208 3.17 MB](/uploads/short-url/oVCfZbfNYcgWEpD2XBKl3DWWQsG.jpeg?dl=1)

[[![P1000501](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/3/a36ad4b06b4b9889fd1ee930cc9f8342a55e516d_2_690x253.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/3/a36ad4b06b4b9889fd1ee930cc9f8342a55e516d_2_690x253.jpeg)

P10005016000×2208 4.58 MB](/uploads/short-url/njEI7AOfYnyrAj9pRpt3xedSc0t.jpeg?dl=1)

我找不到代码实验的记录，但我有 VLog LUT 计算脚本，非常 WIP，非常简陋，但至少 LUT 可以使用相机的完整动态范围（Lumix S9 只有 12 位，因为松下太邪恶了，直接屏蔽了更高 SNR 的慢速读出模式，啊啊啊，我知道相机没有机械快门，但……就是邪恶）。

> **@Mateusz_Grabowski** (帖子 #614):
> 这是我昨天用 spektrafilm 导出的 haldclut 制作的视频。包含成色剂！

色彩非常浓郁！

> **@sahuaro.senorita** (帖子 #616):
> "已安装 1 个可执行文件：spektrafilm"

如果你使用 `uv install tool ...`，你应该可以在终端中从任何位置运行 `spektrafilm` 命令

---

## #632 **** (@Thomsen) · 2026-05-05 12:58

> **@arctic** (帖子 #631):
> 我买这台相机纯粹是为了静态照片的 3D LUT 功能

只想确认一下——Lumix 相机无法处理所有的光谱功能，对吧？只能处理对比度/色彩的 LUT？

---

## #633 **** (@Thomsen) · 2026-05-05 12:59

Magic Lantern，即被破解的 Canon 操作系统，出现在我的脑海中。想象一下，如果能直接在相机内完成整个 Spectral 模拟……

---

## #634 **Andrea** (@arctic) · 2026-05-05 13:06

> **@hanatos** (帖子 #630):
> 如果我理解正确的话，你基本上是在尝试校正这一点，使上采样更接近特定胶片感光剂灵敏度的同色异谱空间，而不是人类观察者的 CMF。

我从真实光谱出发，可以计算它们在 1931 CMF 上的投影以及在胶片灵敏度上的投影（真实值）。然后我用真实光谱计算 XYZ，并使用你的算法进行上采样。我得到一个在重新投影到 1931 CMF 时具有零误差 XYZ 值的光谱，但不可避免地会在胶片灵敏度上产生大误差。

原因正是 sigmoid 光谱的特性——如果是"谷"类型，就会有紫外/红外波瓣。但即使在可见范围边缘是"峰"型，也可能延伸到近紫外和近红外区域。

于是就有了优化带通上采样的想法，它可以减少与真实光谱曝光的往返误差。

> **@hanatos** (帖子 #630):
> 我有点犹豫是否要在这里添加事后修正，尽管光谱加窗是有意义的。

那我可太有罪了！我在周末试图超越最优的每通道带通。

[![:stuck_out_tongue:](https://discuss.pixls.us/images/emoji/apple/stuck_out_tongue.png?v=12)](https://discuss.pixls.us/images/emoji/apple/stuck_out_tongue.png?v=12)

我想说它在视觉上有差异，而且我认为从无带通到有带通是非常明显的。它可以达到几乎视觉上察觉不到的差异（超过一半语料库的平均最大误差 <2/20 EV，90%+ 的语料库 <3/20 EV）。修正添加了一个"简单"的每通道参数化曝光校正图，位于 xy 平面上（tc 坐标）。

以下是一个使用 D55 光源的 colorchecker 反射数据集示例，投影在 kodak_portra_400 灵敏度上。外圈是真实的反射光谱曝光（以直通 sRGB 显示，所以不是真实颜色，但有助于看到差异）。

（左）未校正（`hanatos2025` 光谱），（中）带通处理，（右）带通加每通道曝光校正。

[[![f4_colorchecker_kodak_portra_400 - Copy](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/2/12b976d65e8138f1b5c1577f1b9c7aa23dd441f2_2_690x183.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/1/2/12b976d65e8138f1b5c1577f1b9c7aa23dd441f2_2_690x183.png)

f4_colorchecker_kodak_portra_400 - Copy4770×1271 74.9 KB](/uploads/short-url/2FDWSEDpELuefuioOakQa3kXs42.png?dl=1)

结果相当不错，即使它是一个校正过程，因此本质上不太优雅。我把它看作原始算法的灵敏度适应。由于灵敏度与 CMF 差别不大，这种适应可以用每通道 15-20 个参数（带通参数和 2D 平面平滑函数的参数）来编码。好处是它似乎保留了你底层 sigmoid 算法的一些优良特性，即在 xy 平面上具有平滑的解。

以下是一个在 xy 平面上拟合的 2D 函数示例。我使用饱和函数，因此它可以任意限定在我们允许的最大校正范围内。

[[![f5_topographic_kodak_portra_400](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/a/6ab2d7a01723faa3904bdd09e8c245025d7d074e_2_690x205.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/6/a/6ab2d7a01723faa3904bdd09e8c245025d7d074e_2_690x205.png)

f5_topographic_kodak_portra_4005063×1511 398 KB](/uploads/short-url/fdTMlabAskkT3cqp7B0Rx4189BA.png?dl=1)

以下还展示了一些来自 `colour-science` 的光谱数据集的 log 曝光误差图。第一列只是 `hanatos2025` 往返误差，中间是仅带通，右侧是带通加平面校正。

[[![f2_pancake_kodak_portra_400](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/3/331f12fdc56592c9e80576e0196f07d203d292e5_2_690x552.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/3/3/331f12fdc56592c9e80576e0196f07d203d292e5_2_690x552.png)

f2_pancake_kodak_portra_4006000×4800 2.17 MB](/uploads/short-url/7ieVtSf2FnGA7uNptE4Lks7S9Bb.png?dl=1)

我们不能期望一个完美的平面薄饼，因为同色异谱空间本来就应当略有不同。但我们可以将其压缩到最小程度。

总体而言，带通是共享的，计算廉价且简单，三个曝光校正的计算成本也不高。这是一个肮脏的解决方案，但似乎工作得还行，并且不需要为每种胶卷在三角坐标中提供一个新的 sigmoid 光谱 LUT。但它仍然是一个校正，可能让人感觉不干净

[![:laughing:](https://discuss.pixls.us/images/emoji/apple/laughing.png?v=12)](https://discuss.pixls.us/images/emoji/apple/laughing.png?v=12)

使用 RAW 文件的 RGB 工作似乎是合乎逻辑的可移植标准，即使上述方式意味着`相机灵敏度曝光 -> RGB -> 光谱 -> 灵敏度适应 -> 胶片灵敏度曝光`；但它与相机灵敏度无关（我们相信制造商/校准者，RAW 文件的 RGB 是良好的估计值）。

无论如何，上述误差是针对真实光谱的，所以它表明这个过程虽然不优雅，但参数数量紧凑，并且在现实世界中是可行的。

> **@hanatos** (帖子 #630):
> 顺便问一下，窗口的模拟对应物是什么？

在模拟相机中，镜头具有紫外线吸收功能，会对近紫外区域进行温和的带通滤波，近红外则更开放。胶片可能也有彩色滤镜，但这已经包含在灵敏度中（毕竟它们是对有效感光过程的密度测量）。

但在这里，窗口负责处理 sigmoid 光谱的波瓣相对于真实光谱的超调，仅此而已。"谷"型 sigmoid 光谱是一种特殊的同色异谱体，具有巨大的不可见贡献（甚至 X 射线

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 ）。带通只是驯服了这些，以模拟真实光谱语料库的平均行为。本质上，我们将语料库的趋势注入带通和 2D 平面中，希望简单的带通+平面模型能够用少量参数泛化上采样算法的灵敏度适应变换（误差足够低）。

如果我们想以与相机灵敏度无关的方式优化 sigmoid 光谱（即从 RGB → XYZ 开始），我猜这个过程最终仍然需要依赖光谱数据集来最小化上采样光谱在胶片灵敏度上的往返误差，同时保持原始光谱的指定 XYZ。这是因为我们没有任何胶片曝光的真实值。

但这不是我的领域，我可能做出了巨大的错误假设

[![:grin:](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)

---

## #635 **Yogansh Bhatt** (@Yogansh_Bhatt) · 2026-05-05 13:10

如果你有安卓机的话，可以看看 Motioncam Pro

[![:slightly_smiling_face:](https://discuss.pixls.us/images/emoji/apple/slightly_smiling_face.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slightly_smiling_face.png?v=12)

mcraw 是 vkdt 原生支持的，如果你想让你的智能手机输出惊人的图像/视频，你可能会对它感兴趣（它不是自由开源软件，所以我不喜欢在 pixls 上提到它，但它最初是由一个独立开发者开始的，所以我的负罪感稍微少一点）。

---

## #636 **Andrea** (@arctic) · 2026-05-05 13:11

它们可以完成所有可以编码在 VLog 3D LUT 中的内容，即对于一组固定参数的完整 spektrafilm 计算结果，减去非局部和随机效果（光晕、散射、颗粒、扩散滤镜、成色剂扩散等）。我认为这就像在相机中拥有 ART 实现，但只能使用固定的预设。白平衡效果很好，因为 spektrafilm 的设计目标就是保持 18% 中灰输入到输出不变。

---

## #637 **Yogansh Bhatt** (@Yogansh_Bhatt) · 2026-05-05 13:15

当然，这与 [@Thomsen](/u/thomsen) 建议的方向一致。我甚至看到了 filmsim 和 Spektrafilm 的非常 WIP 的移植版本，但要看开发者是否会完成并发布它（当然应该是自由开源软件）。我相信这些安卓设备从这些惊人的项目中受益匪浅……几乎达到了 Magic Lantern 的水平。

---

## #638 **** (@yairs) · 2026-05-05 14:17

这看起来真不错！能分享一下你这个的 json 文件吗？

---

## #639 **** (@RoughDraftWriting) · 2026-05-05 14:36

看起来很有趣，可惜我没能在我的 Mac 上成功运行你的 LUT 生成器或 VKDT。可能是我操作有误

[![:sweat_smile:](https://discuss.pixls.us/images/emoji/apple/sweat_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/sweat_smile.png?v=12)

[[![Screenshot 2026-05-05 at 7.35.31 AM](https://d2x313g9lpht1q.cloudfront.net/original/3X/3/a/3af9479a5a989452e67b3939a72f214306e5424a.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/3/a/3af9479a5a989452e67b3939a72f214306e5424a.png)

Screenshot 2026-05-05 at 7.35.31 AM245×281 24.3 KB](/uploads/short-url/8pHLTMYiJh1LmRrGFYQDuB0or9g.png?dl=1)

尽管我有适当的权限，但我只收到这条消息。

---

## #640 **None** (@sahuaro.senorita) · 2026-05-05 14:46

> **@arctic** (帖子 #631):
> 如果你使用 uv install tool ...，你应该可以在终端中从任何位置运行 spektrafilm 命令

非常抱歉，但我不懂怎么做。我基本上从不使用终端，除非有可以粘贴进去的命令。

---

## #642 **** (@mikae1) · 2026-05-05 20:23

> **@sahuaro.senorita** (帖子 #640):
> 非常抱歉，但我不懂怎么做。我基本上从不使用终端，除非有可以粘贴进去的命令。

创建持久安装：

```
uv tool install git+https://github.com/andreavolpato/spektrafilm.git@dev

```

启动：

```
spektrafilm

```

升级：

```
uv tool upgrade spektrafilm

```

只需将这些复制粘贴到你的终端中即可。

---

## #643 **Ryan Cara** (@Ryan_Cara) · 2026-05-05 23:19

在终端中试试这个：

> cd /path/to/your/downloaded/Spektrafilm-LUT-Generator
>
> chmod +x launch_mac.command

然后重新运行

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

或者

> conda activate spektrafilm
>
> python "/path/to/Spektrafilm-LUT-Generator-main/spektrafilm_state_to_lut_gui.py"

---

## #644 **None** (@sahuaro.senorita) · 2026-05-06 01:04

> **@mikae1** (帖子 #642):
> 启动：

```
spektrafilm

```

非常感谢！我不敢相信竟然这么简单。

---

## #645 **** (@cometface589) · 2026-05-06 07:58

如何导出高分辨率文件？我按下保存按钮后，得到的都是非常低分辨率的文件。

---

## #646 **Benjamin** (@piratenpanda) · 2026-05-06 09:27

你在之前按了 scan 按钮来计算高分辨率图像吗？

---

## #647 **** (@mikae1) · 2026-05-06 11:03

> **@Ryan_Cara** (帖子 #619):
> 我提供的方法会把值推到边界之外吗？如果是的话，@slazaar，也许值得走 Darktable（导出 Prophoto RGB Linear）→ Photoshop → Spektrafilm 的路线。

如果需要在 Photoshop 中处理，这就是我推荐的顺序，是的。

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

---

## #648 **jo** (@hanatos) · 2026-05-06 11:20

> **@arctic** (帖子 #634):
> 我从真实光谱出发，可以计算它们在 1931 CMF 上的投影以及在胶片灵敏度上的投影（真实值）。然后我用真实光谱计算 XYZ，并使用你的算法进行上采样。我得到一个在重新投影到 1931 CMF 时具有零误差 XYZ 值的光谱，但不可避免地会在胶片灵敏度上产生大误差。

好的，到目前为止这符合预期

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

> **@arctic** (帖子 #634):
> 原因正是 sigmoid 光谱的特性——如果是"谷"类型，就会有紫外/红外波瓣。但即使在可见范围边缘是"峰"型，也可能延伸到近紫外和近红外区域。

不对。灵敏度是加窗的，CMF 和胶片灵敏度都是如此。所以再额外加窗，你是在改变 R/G/B 响应的比例（窗口在红外范围内衰减得非常柔和）。

将这种额外的误差校正拟合到某些特定的光谱形状似乎是随意的，但你在这里使用的是一套相当相关的光谱。你的误差图大部分在"谷"形状区域，这相当有说服力。为了减少我们这里漂浮的额外数据/校正项的数量……如果我尝试引入一些固定的/静态的加窗，并在循环中重新优化光谱 LUT，这有意义吗？我假设它不会对 XYZ 往返的行为产生太大改变，但会为我们提供加窗的光谱上采样。这不能解决同色异谱不匹配的问题，但现在我很好奇……

---

## #649 **** (@mikae1) · 2026-05-06 11:34

> **@sahuaro.senorita** (帖子 #644):
> mikae1:

启动：

```
spektrafilm

```

非常感谢！我不敢相信竟然这么简单。

</blockquote>
</aside>

上面已经说过了，但现在这个帖子里的不同讨论有点难以跟进了。

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

也许 Spektrafilm——以及它在 ART 和 vkdt 中的实现——很快应该拥有自己的类别了，[@paperdigits](/u/paperdigits) 和 [@hanatos](/u/hanatos)？那些不太接近开发和 Linux 的人似乎正在发现 Spektrafilm（这很棒！），一个用于解决安装问题之类的支持帖可能是个好主意。

---

## #650 **** (@cometface589) · 2026-05-06 14:49

哦天哪，我完全错过了那部分。有没有办法保存为 16 位 tif，还是目前只有 JPG？当我尝试保存时，没有看到保存为 tif 的选项，只有 jpg。谢谢你对扫描部分的帮助！

---

## #651 **Mica** (@paperdigits) · 2026-05-06 14:59

> **@mikae1** (帖子 #649):
> 以及它在 ART 和 vkdt 中的实现——很快应该拥有自己的类别了，@paperdigits 和 @hanatos？

当然，如果 [@arctic](/u/arctic) 觉得有用的话。

---

## #652 **** (@mikae1) · 2026-05-06 15:32

> **@cometface589** (帖子 #650):
> 有没有办法保存为 16 位 tif，还是目前只有 JPG？当我尝试保存时，我没有看到保存为 tif 的选项，只有 jpg。

TIFF 选项已经没有了。如果你想要无损，使用 PNG（我相信只有 8 位）或 OpenEXR（更多位）。

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

---

## #653 **Georg N** (@geni1105) · 2026-05-06 16:19

这是个好建议，谢谢！我和其他许多人可能都会非常感激有一个单独的安装问题帖子。

例如，我目前卡在从 agx-emulsion（在 python 3.11 上正常运行）升级到 spektrafilm（显然需要 python 3.13，但 pip 会报错

ERROR: Ignored the following versions that require a different python version: 0.4.0 Requires-Python >=3.8,<3.11; 0.4.1 Requires-Python >=3.8,<3.11; 0.4.2 Requires-Python >=3.9,<3.12; 0.4.3 Requires-Python >=3.9,<3.12; 0.4.4 Requires-Python >=3.9,<3.13; etc. etc.

有什么提示吗？谢谢！

(MacOS 15.7)

---

## #654 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-05-06 17:06

好吧，这是我在这里发的最后一个视频！（也许应该有人建个专门分享 spektrafilm 作品的主题？）

 <iframe src="https://www.youtube.com/embed/TeI1RHc0Wd0?feature=oembed&wmode=opaque" width="480" height="360" frameborder="0" allowfullscreen="" class="youtube-onebox" seamless="seamless" sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox allow-presentation"></iframe>

Lumix S5IIX 使用 V-Log 搭载 TTartisan 35mm f1.4 镜头。（全画幅相机上用 APS-C 镜头有一些有趣的优点！）

Portra 800 配 Fuji Crystal Archive 相纸。

曝光、对比度和微小的饱和度和色调调整在 DWG 色彩空间中进行。LUT 在转换到 rec709/2.4 后应用。

大家春天快乐！

---

## #655 **** (@mino) · 2026-05-06 17:50

太美了，尤其是开场镜头。我觉得这非常适合作为那个 spektrafilm 展示帖的第一帖

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

 ！

## #656 **** (@europlatus) · 2026-05-06 17:57

> **@priort** (帖子 #578):
> > Ya I will have to check I run a pretty standard 120 cd/m2

仅供参考，我刚刚校准了显示器，亮度降低了，显然我之前显示器亮度设置得有点高。再看看那张照片，确实显得很暗。考虑到光线条件，我觉得栏杆的白色应该是亮白色，接近照片边框的白色，但实际上明显更暗。不过，我仍然能看到所有人的脸，这种风格显然是为了高对比度但动态范围较低，模仿老胶片的风格。

前排穿白色衣服的人右边那个穿蓝色牛仔裤的人，只有半张脸可见，但没有人完全被遮挡。

我怀疑大多数人的显示器设置得比校准显示器更亮。就像你把电视调到电影模式，突然变得昏暗、偏暖且色彩 muted。它旨在准确显示导演的意图，但这并不是人们看普通电视广播时所习惯的效果。

---

## #657 **Todd Prior** (@priort) · 2026-05-06 18:54

如果所谓的"感知量化器"（perceptual quantitizer）传递曲线变得更普及就好了……我不太完全理解，但一旦你有了亮的高位深显示器，我认为这些曲线使用绝对值可以取代 SDR gamma，这样当你换到不同的显示器——甚至是设置到其他默认水平的更亮的显示器——你的图像会显示漫射白到你定义的任何值？我想？**SMPTE ST 2084**

但在这里，这无疑是一张高对比度、深黑色的图像，所以在 SDR 显示器上，不同峰值亮度水平的用户之间看起来很可能不同……我的 Acer 显示器还有一个叫 black boost 的功能，我认为这是一种黑点补偿，会提亮阴影并提供更多细节，但我把它关掉了……其他人可能启用了类似的功能，进一步改变了对渲染的感知……这些胶片模拟所能实现的色彩和氛围是毋庸置疑的……我感到遗憾，因为我真的没有太多时间去深入探索它们……

---

## #658 **** (@mikae1) · 2026-05-06 20:24

> **@geni1105** (帖子 #653):
> > 我和可能许多其他人真的很希望有一个单独的安装问题帖子。

"新话题"按钮就在论坛第一页的顶部，[我按下去了](https://discuss.pixls.us/t/spektrafilm-troubleshooting-installing-upgrading-etc/57453)。

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

---

## #659 **Tim** (@Soupy) · 2026-05-06 23:46

这个模块应该叫"我简直不敢相信这不是胶片！"

---

## #660 **Upperechelonstr8up** (@upperechelonstr8up) · 2026-05-07 06:30

使用这样的 LUT 与手动/通过脚本在 SpektraFilm 中导出每一帧相比，会产生不同的结果吗？

---

## #661 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-05-07 08:11

我不知道色彩方面如何，但你肯定会失去颗粒、光晕等效果。

---

## #662 **John A** (@John_A) · 2026-05-07 11:31

MTF 是内置的，还是需要额外添加？

---

## #663 **Ryan Cara** (@Ryan_Cara) · 2026-05-07 14:29

如前所述，你确实会失去颗粒和光晕。但还有一些空间特征你也会错过，这些特征会轻微影响色彩！如果你的目标是将此用于视频，目前最忠实的实现是 VKDT。

[![:innocent:](https://discuss.pixls.us/images/emoji/apple/innocent.png?v=12)](https://discuss.pixls.us/images/emoji/apple/innocent.png?v=12)

话虽如此，使用 LUT 仍然可以看起来很棒！

---

## #664 **Gonçalo** (@ggoncalo) · 2026-05-07 15:08

大家好！第一次在这里发帖。

我昨天通过 Reddit 的一个帖子了解到 SpektraFilm，我对它的效果以及项目投入的细节和研究水平印象深刻。我毫不怀疑这将是胶片模拟领域的游戏规则改变者，所以我在我的 Mac 上安装并试用了。

我调整了一些设置，但有几件事想问一下，以确保我充分利用了这个软件：

1. 推荐的工作流程是什么？
   在 Darktable/Lightroom/C1 等软件中进行基本的 RAW 编辑 → SpektraFilm → Photoshop（如果需要）？还是你建议直接在 SpektraFilm 中打开 RAW 文件？如果之前使用其他编辑器，你是否导出为 ProPhoto 色彩空间？
2. 这可能是我犯的愚蠢错误，但我按"保存"似乎只能导出低分辨率的 JPEG。我无法导出无损文件。我漏掉了什么？无损导出只能通过命令行实现吗？

---

## #665 **Todd Prior** (@priort) · 2026-05-07 15:31

[@Soupy](/u/soupy) 我忍不住了……

> **@Soupy** (帖子 #659):
> > 这个模块应该叫"我简直不敢相信这不是胶片！"

<iframe src="https://www.youtube.com/embed/mqtsgH_wnn4?feature=oembed&wmode=opaque" width="480" height="360" frameborder="0" allowfullscreen="" class="youtube-onebox" seamless="seamless" sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox allow-presentation"></iframe>

---

## #666 **Gonçalo** (@ggoncalo) · 2026-05-07 17:07

这太疯狂了。两个问题：你是通过肉眼对比来匹配胶片和数字，还是使用某种脚本？另外，那个 3D LUT 功能只适用于 JPEG，还是在 RAW 文件中也有？

---

## #667 **Steven** (@123sg) · 2026-05-07 17:15

> **@ggoncalo** (帖子 #664):
> > 但我想按"保存"似乎只能导出低分辨率的 JPEG。我无法导出无损文件。我漏掉了什么？

我自己也还在学习中，但你需要按"SCAN"按钮，完成调整后（因为它相对较慢），然后再像你之前那样进行保存。

我也花了一点时间才意识到。

[![:wink:](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)

> **@ggoncalo** (帖子 #664):
> > 在 Darktable/Lightroom/C1 等软件中进行基本的 RAW 编辑 → SpektraFilm → Photoshop

据我所知，要获得准确模拟的全部好处，输入需要是线性文件，所以不能应用色调曲线——在 darktable 中只需关闭色调映射器（Sigmoid/AgX/filmic），但我不确定在其他软件中如何操作。

---

## #668 **** (@Cristian) · 2026-05-07 17:22

1. 我直接在 SpektraFilm 中打开 raw 文件，这省去了我在其他软件中打开 raw 的麻烦，也节省了硬盘空间。
2. 调整完成后，点击 scan，然后以全分辨率保存 jpeg。这个项目还在开发中，所以扫描需要一些时间。
3. 编辑愉快！
   [![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

---

## #669 **Gonçalo** (@ggoncalo) · 2026-05-07 17:28

非常感谢 Cristian！

---

## #670 **Gonçalo** (@ggoncalo) · 2026-05-07 17:29

非常感谢 Steven！

---

## #671 **None** (@Anthonygansauer) · 2026-05-07 17:37

我首先做了 RA4 打印。扫描后，在程序中使用其虚拟放大机设置匹配数字版本。我将其保存为预设以便每次使用，但仍在完善中，还不是 100% 准确，大概 70% 的准确度，仍在探索一些更复杂的耦合剂设置。

---

## #672 **Andrea** (@arctic) · 2026-05-07 18:13

> **@hanatos** (帖子 #648):
> > 将这个额外的误差校正拟合到特定的光谱形状似乎是武断的

我部分同意这一点，这里再对问题做些评论。从 XYZ 上采样不可避免地会丢失超过 1931 cmfs 的所有信息。如果一个实际测量的光谱与另一个光谱在 1931 cmfs 为零的范围内不同，那么该信息不可避免地会丢失，因为上采样器会返回完全相同的光谱。因此，如果我们想要减少真实光谱胶片曝光的往返误差，我们需要从其他地方找到该先验信息，并以某种方式将其嵌入上采样算法中。

我们只能希望典型的自然反射光谱在超过 1931 cmfs 几十纳米的范围内足够平滑（胶片灵敏度没那么宽），以便信息能够很好地压缩。如果我们对语料库的质量和完整性有信心，那么带通+曲面只是在少数参数中拟合该信息的一种方法。上采样+带通+曲面更像是一个黑盒，用于将 XYZ → 合理的 RGB 胶片曝光（合理是指在给定少数参数的情况下误差最小）。

上采样为可见中心部分提供了 cmfs-零误差基础，带通+曲面在 xy 景观上编码了先验信息的曝光变形，从而减少往返误差。（还没试过，但我很确定，在给定固定上采样算法的情况下，带通可以编码为一组胶片灵敏度上的表面对数曝光校正，嗯，我会在这个方向继续思考）。

> **@hanatos** (帖子 #648):
> > 如果我尝试引入一些固定/静态的窗口化，并重新优化光谱 LUT（将其纳入循环），这样合理吗？我假设这不会对 XYZ 往返的行为产生太大影响，但会为我们提供窗口化的光谱上采样。这不会解决同色异谱不匹配问题，但现在我很好奇……

我认为添加一个平滑的带通窗口并重新优化上采样算法是个好主意！我相信这将为胶片灵敏度提供一个更好的同色异谱基础，其表现会好得多，尤其是对于在蓝色/红色端有峰值或带有旁瓣的光谱。因此，无论我们之后决定做什么，从一开始在胶片灵敏度上的误差就会更小。

用什么窗口？特定的形状有多重要？好问题。

这里做几个具有挑衅性的实验，供大家"思考"。

我尝试了一个方波带通，边缘位于蓝色和红色 LMS 灵敏度的第 1 百分位。在这种情况下，我们是在裁剪上采样光谱，同时在 1931 cmfs 上基本保持零误差。然后我拟合了一个多项式曲面进行对数曝光校正。

[[![f3_ecdf_kodak_portra_400](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/9/99973e23eee3870d744cf03e54b0b02c22d793de_2_300x250.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/9/99973e23eee3870d744cf03e54b0b02c22d793de_2_300x250.png)

f3_ecdf_kodak_portra_4002107×1658 186 KB](/uploads/short-url/lUJ5wi5lc8wW7xHks9BQ68NXFz8.png?dl=1)

[[![f2_pancake_kodak_portra_400](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/7/476000f1ad263c503adc2d93dafbeb0b2af52075_2_300x250.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/7/476000f1ad263c503adc2d93dafbeb0b2af52075_2_300x250.png)

f2_pancake_kodak_portra_4006000×4800 2 MB](/uploads/short-url/abpApMW5xKKjdA8ryZGDi66inBj.png?dl=1)

类似地，我们可以使用平滑的逻辑斯蒂窗口形状，其拐点位于相同的百分位边界。在这种情况下，我们可以同时拟合窗口和曲面。

[[![f3_ecdf_kodak_portra_400](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/1/51794a241cdd1414310e655eba3a45297bbdfdff_2_300x250.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/1/51794a241cdd1414310e655eba3a45297bbdfdff_2_300x250.png)

f3_ecdf_kodak_portra_4002107×1658 186 KB](/uploads/short-url/bCKxhRtibcmhZFeGSBNIAUABYVF.png?dl=1)

[[![f2_pancake_kodak_portra_400](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/0/9036deb399604674110d3c9f31e2101ccdc746b6_2_300x250.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/9/0/9036deb399604674110d3c9f31e2101ccdc746b6_2_300x250.png)

f2_pancake_kodak_portra_4006000×4800 1.98 MB](/uploads/short-url/kzMjt6vFeYPWKgKzc3iV8mvHi0m.png?dl=1)

使用平滑窗口，本质上，我们从曲面中移除了一些校正职责。平滑的逻辑斯蒂窗口在波长域中对上采样光谱进行变形，而我们根据先验信息知道，旁瓣对胶片灵敏度不利，因此这是一个很好的作用空间。

,
[[![f3b_train_val_test_kodak_portra_400](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/8/0853bf4f1617d1ade00ebd8caa2f38c4a5e8ceed_2_300x250.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/0/8/0853bf4f1617d1ade00ebd8caa2f38c4a5e8ceed_2_300x250.png)

f3b_train_val_test_kodak_portra_4002425×1658 250 KB](/uploads/short-url/1bFfluIptsD3AH7hq8my94yvT0F.png?dl=1)

[[![f3b_train_val_test_kodak_portra_400](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/6/e6d2ee1a5063e7c41f8b19e747477028e835b3ae_2_300x250.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/e/6/e6d2ee1a5063e7c41f8b19e747477028e835b3ae_2_300x250.png)

f3b_train_val_test_kodak_portra_4002468×1658 245 KB](/uploads/short-url/wVXJuRnveMHQngzm1Y03FyMiaPY.png?dl=1)

窗口对大多数往返误差的影响不大（平滑窗口的损失略低），但它似乎有助于使相同的最小曲面模型（本例中每通道 11 个参数）具有更强的泛化能力，例如对肤色更好（如果仅在 otsu+munsell 上训练，肤色是最难处理的光谱）。

如果让窗口在可见范围内裁剪更多，我们甚至可以获得稍好的结果。我可以尝试仅为几种胶片重新优化窗口（无曲面），看看是否能找到一个好的平均窗口。你有偏好的 sigmoid 形状吗？你认为哪种适合光谱约束？

[更新] 清晨思考：如果你的优化窗口形状类似于 D55（日光胶片的典型目标），会怎样？比如 D55 的平滑版本，或者更激进的窗口化版本，其中间部分类似于 D55。这对优化来说是不是也是一个好选择？疯狂的想法？这个想法是在看到使用更好的追尾正则化器优化窗口的平滑形状后产生的。

另外，对于光谱胶片应用，采用 D55 参考上采样是否合理？

举个例子：（仍然严重依赖于 sigmoid 形状和优化超参数，我会进行调整）

[[![f1_anatomy_kodak_portra_400](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/b/abe87028d201e13cdea844ed1f9b2b4aa1a33cb0_2_300x400.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/b/abe87028d201e13cdea844ed1f9b2b4aa1a33cb0_2_300x400.png)

f1_anatomy_kodak_portra_4002371×2955 465 KB](/uploads/short-url/owLDUSjhWuD3kdrgAAr7WPbsZCo.png?dl=1)

[[![f3_ecdf_kodak_portra_400](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/c/fc91d99dc32b488f6ea080d977e100faab7162b2_2_300x250.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/c/fc91d99dc32b488f6ea080d977e100faab7162b2_2_300x250.png)

f3_ecdf_kodak_portra_4002107×1658 154 KB](/uploads/short-url/A2kNTVN8qXDTVkcNCrnSThHqnMS.png?dl=1)

---

## #673 **Andrea** (@arctic) · 2026-05-07 18:24

> **@paperdigits** (帖子 #651):
> > 当然，如果 @arctic 觉得有用的话。

好主意，谢谢。

我也应该开一个关于硬核色彩讨论的帖子。

[![:grin:](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)](https://discuss.pixls.us/images/emoji/apple/grin.png?v=12)

---

## #674 **Andrea** (@arctic) · 2026-05-07 18:28

基础实现在 `main` 分支中，但目前我还没有提交基于 portra 400 的 MTF 微调结果，所以 MTF 可能还不够真实。我会尽快提交。

---

## #675 **Andrea** (@arctic) · 2026-05-07 18:29

> **@Mateusz_Grabowski** (帖子 #654):
> > 好了，这是最后一个视频

这太美了！这不应该成为最后一个。

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

也祝你春天快乐！

---

## #676 **Mica** (@paperdigits) · 2026-05-08 16:47

> **@arctic** (帖子 #673):
> > 好主意，谢谢。
> > 我也应该开一个关于硬核色彩讨论的帖子。

我有点迟钝。这是对某个分类的"同意"吗？应该是 Software > Spektrafilm。

---

## #677 **Andrea** (@arctic) · 2026-05-08 17:14

我把帖子旁边出现的标签误认为是分类了。实际上我认为标签暂时就够了。

让项目再成熟一些，边走边看吧。谢谢你明确指出来（同时也感谢你一直以来对论坛的支持，这值得经常提一下）。

---

## #678 **jo** (@hanatos) · 2026-05-08 17:56

> **@arctic** (帖子 #677):
> > 我把帖子旁边出现的标签误认为是分类了。实际上我认为标签暂时就够了。

我觉得你太谦虚了。

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

但实际上，也许我们应该把最近的一些色彩/技术性讨论分出来，放到单独的话题中，不管是不是分类？

---

## #679 **Andrea** (@arctic) · 2026-05-08 18:16

听起来不错！

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

这里可以作为 [SpektraFilm 技术讨论](https://discuss.pixls.us/t/spektrafilm-tech-discussions/57512)的大本营。

---

## #680 **Revanza Pratamasyah** (@Revanza_Pratamasyah) · 2026-05-08 21:56

你好 Mateusz

我想学习你从 SpektraFilm 获取 LUT 的逐步方法。你能分享详细的步骤吗？

提前感谢！

---

## #681 **Vicer Fx** (@Vicer_Fx) · 2026-05-10 01:13

嘿，我对于通过终端安装东西还比较新手，如果不会占用你太多时间，你能制作一个小视频展示在 conda 中的安装过程吗？

---

## #682 **Gonçalo** (@ggoncalo) · 2026-05-10 01:45

[[![Captura de ecrã 2026-05-10, às 02.40.01](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/2/a233dc631c451fca76cf278aaa5c5b2dfcea6215_2_690x459.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/a/2/a233dc631c451fca76cf278aaa5c5b2dfcea6215_2_690x459.png)

Captura de ecrã 2026-05-10, às 02.40.011654×1102 2.9 MB](/uploads/short-url/n8UsCArzqu62Uf0yZSmuf10f5fT.png?dl=1)

[[![Captura de ecrã 2026-05-10, às 02.39.44](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/f/4fca65d858afa415c67959ee5fd3e59f38c161cb_2_690x461.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/4/f/4fca65d858afa415c67959ee5fd3e59f38c161cb_2_690x461.png)

Captura de ecrã 2026-05-10, às 02.39.442130×1424 5.88 MB](/uploads/short-url/bnRm2CK2RzuW5v6OUlkZ1Gbsq4r.png?dl=1)

大家好！

有人遇到导出时饱和度下降的问题吗？为了节省存储空间，这两张都是截图，但我认为可以看出差异。上面的是 SpektraFilm 中的图像，下面的是导出的图像。我的输出/保存色彩空间都是 sRGB。

---

## #683 **Todd Prior** (@priort) · 2026-05-10 02:30

请确保你尝试启用 hqp 来评估图像……即高质量预览，然后在导出时设置 hqr …reprocessing 为 yes……这应该能很好地匹配，最后检查一下你的显示配置文件设置和使用的是什么……这是控制预览在显示器上显示样子的配置文件。

---

## #684 **WG** (@BPH3647) · 2026-05-10 03:50

我这边一直存在色彩空间嵌入的问题，也许你也有同样的问题。只需指定一个 sRGB 色彩空间，颜色应该就会恢复正常。

---

## #685 **Gonçalo** (@ggoncalo) · 2026-05-10 15:12

抱歉，在哪里启用 hqp？我只有一个"Preview"选项。导出时，我一按"Save"就完成了，没有重处理的选项或其他导出选项。奇怪。

至于其他设置，我的输入色彩空间设置为 ProPhoto RGB，输出/保存色彩空间为 sRGB。我试过启用和禁用"Scan for print"，但问题依旧。

---

## #686 **Todd Prior** (@priort) · 2026-05-10 15:38

我现在在手机上，没法截图。它在底部的功能区栏中，悬停在图标上……我想它在 Raw overexposure 旁边。它使用完整的图像数据，所以最准确但也更慢……

---

## #687 **Gonçalo** (@ggoncalo) · 2026-05-10 15:52

[[![Captura de ecrã 2026-05-10, às 16.46.40](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/b/5ba4a1a973bb6d396df36e0c5b290328c39fa4f6_2_690x106.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/5/b/5ba4a1a973bb6d396df36e0c5b290328c39fa4f6_2_690x106.png)

Captura de ecrã 2026-05-10, às 16.46.402868×444 221 KB](/uploads/short-url/d4IaBV92zl97OJ6PpbsTT82duzc.png?dl=1)

我找不到那个选项。就好像我用的应用版本不同，但我确定是最新的版本。

---

## #688 **Mica** (@paperdigits) · 2026-05-10 16:15

> **@priort** (帖子 #686):
> > 我现在在手机上，没法截图。它在底部的功能区栏中，悬停在图标上……我想它在 Raw overexposure 旁边。它使用完整的图像数据，所以最准确但也更慢

这是关于 SpektraFilm 的，不是 darktable。我认为 SpektraFilm 中没有高质量选项。

---

## #689 **Gonçalo** (@ggoncalo) · 2026-05-10 16:25

这就解释了困惑，虽然我的问题与图像质量无关，而是导出文件的色彩偏移。似乎大多数人都没有遇到这个问题，所以我想知道我哪里做错了。

---

## #690 **Andrea** (@arctic) · 2026-05-10 16:35

我认为这是显示配置文件和显示器校准的问题。当前在简单 SpektraFilm GUI 中运行图像查看器的 `napari` 不支持色彩管理。所以有点简陋。

你在 Windows 上吗？如果是，你试过在 CONFIG 选项卡下点击和取消点击"use display transform"按钮吗？如果显示变换被获取，状态栏会有提示。目前这仅在 Windows 上有效。

没有显示变换的情况下，你只能依赖 MAIN 选项卡中的"output color space"，将其设置为某种能匹配你显示器校准的设置。也许你的操作系统中有 sRGB 配置文件或设置？在这种情况下，sRGB 输出可能会改善情况。

---

## #691 **Georg N** (@geni1105) · 2026-05-10 18:21

你的显示器色彩空间是什么？如果比 sRGB 更宽，那么将输出色彩空间设置为 sRGB 时，图像会显得过饱和。

---

## #692 **Todd Prior** (@priort) · 2026-05-10 18:41

抱歉，我以为工作流程中用了 darktable……

---

## #693 **Gonçalo** (@ggoncalo) · 2026-05-11 03:58

现在我明白了！我用的 Mac 屏幕色域是 Display P3，比 sRGB 更宽。我之前不熟悉 napari，但如果它不支持色彩管理，那就解释得通了。希望未来能加入 ICC 感知的显示管理。

总之 [@arctic](/u/arctic)，祝贺你建立了这个项目，也感谢你抽时间提供帮助。

---

## #694 **Andrea** (@arctic) · 2026-05-11 05:25

谢谢！

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

你应该尝试将输出色彩空间设置为 Display P3，如果我没记错的话，很早就添加了这个选项，正是为了在 Mac 上有更好的色彩还原。

---

## #695 **Georg N** (@geni1105) · 2026-05-11 09:08

没错，我在我的 iMac 上就是这样做的，使用 DisplayP3 色域。

祝贺并非常感谢你的出色工作！

---

## #696 **Andrea** (@arctic) · 2026-05-11 18:39

> **@mikae1** (帖子 #652):
> > TIFF 选项不见了

> **@cometface589** (帖子 #650):
> > 有没有办法保存为 16 位 tif

16 位 TIFF 回来了

> **@mikae1** (帖子 #652):
> > OpenEXR（更多位数，大概）

exr 默认为 16 位

---

## #697 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-05-11 19:28

1. 下载或创建 Hald CLUT 恒等表。
   由于我有 ImageMagick，我使用以下命令创建了我的：
   "convert hald:12 -depth 16 -colorspace sRGB hald12_16bit.tif"
   你也可以下载这个：
   [File:Hald CLUT Identity 12.png - RawPedia](https://rawpedia.rawtherapee.com/index.php?title=File:Hald_CLUT_Identity_12.png)
2. 将 Hald CLUT 导入 SpektraFilm
2. 在 Input 选项卡中选择输入色彩空间为 srgb，并勾选"apply cctf decoding"为 ON
3. 在 exposure 选项卡中，我取消勾选了自动曝光和自动补偿。
   camera compensation ev 设为 0，print exposure 设为 1
4. 关闭光晕、颗粒、预闪和扩散
5. 我保留耦合器开启，但重要的是将 diffusion size um 设为 0
6. 在 scanner 选项卡中，将 unsharp mask 和 blur 设为 0
7. 按 scan 并保存为 .png
8. 使用 PNG2Cube 程序将 Hald CLUT 文件转换为 .cube 文件。程序使用非常简单，说明如下：

<aside class="onebox allowlistedgeneric" data-onebox-src="https://picturefx.itch.io/png2cube-converter-for-linux-and-windows">
 <header class="source">

[![图片671](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/9/c9ef2b6d427684a3bfd30216c351bd57e600e505.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/c/9/c9ef2b6d427684a3bfd30216c351bd57e600e505.png)

 [itch.io](https://picturefx.itch.io/png2cube-converter-for-linux-and-windows)
 </header>

 <article class="onebox-body">

[![图片672](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/d/2d32f92481bc18e3ae20b699478a4e92bbdf4d72_2_690x690.png)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/2/d/2d32f92481bc18e3ae20b699478a4e92bbdf4d72_2_690x690.png)

### [PNG2Cube Converter for Linux and Windows by PictureFX](https://picturefx.itch.io/png2cube-converter-for-linux-and-windows)

 </article>

</aside>

<ol start="10">
<li>在将素材转换为 rec709/gamma 2.4 后使用这些 LUT。</li>
</ol>

我创建了一个"预设"，包含我用于 LUT 的确切设置：

<aside class="onebox googledrive" data-onebox-src="https://drive.google.com/file/d/1gYLJefcqmVg0Kul8S5ZlNQJcrpa4kAkx/view?usp=sharing">
 <header class="source">

 [drive.google.com](https://drive.google.com/file/d/1gYLJefcqmVg0Kul8S5ZlNQJcrpa4kAkx/view?usp=sharing)
 </header>

 <article class="onebox-body">
 [](https://drive.google.com/file/d/1gYLJefcqmVg0Kul8S5ZlNQJcrpa4kAkx/view?usp=sharing)

### [LUT-CREATION.json](https://drive.google.com/file/d/1gYLJefcqmVg0Kul8S5ZlNQJcrpa4kAkx/view?usp=sharing)

Google Drive file.

 </article>

</aside>

你可以在 SpektraFilm 中使用"load from file"来应用这些设置。

有一件事我搞不明白，就是 PNG2Cube 生成的 .cube 文件的大小。每个 LUT 超过 50MB，这不应该！我怀疑是 Hald 图像的分辨率太大了。然而，用 DaVinci Resolve 重新导出为 65 点 cube 后，文件大小就合适了。

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

我能让这一切工作起来简直是个奇迹，因为大多数时候我根本不知道自己在做什么！

目前这样运行良好，但我真的希望 [@arctic](/u/arctic) 将来能实现专用的 LUT 导出菜单，提供仅打印和仅胶片的 LUT 选项！

---

## #698 **Vicer Fx** (@Vicer_Fx) · 2026-05-11 21:52

非常感谢

---

## #699 **Revanza Pratamasyah** (@Revanza_Pratamasyah) · 2026-05-12 04:25

非常感谢你这篇深入的指南 Mateusz！！！

---

## #700 **Andrea** (@arctic) · 2026-05-12 04:46

> **@Mateusz_Grabowski** (帖子 #697):
> > 目前这样运行良好，但我真的希望 @arctic 将来能实现专用的 LUT 导出菜单，提供仅打印和仅胶片的 LUT 选项！

正在为此努力研究一个好的解决方案。

[![:+1:](https://discuss.pixls.us/images/emoji/apple/+1.png?v=12)](https://discuss.pixls.us/images/emoji/apple/+1.png?v=12)

---

## #701 **Vesnic** (@Vesnic) · 2026-05-12 13:07

这绝对精彩、惊艳、美丽、华丽。一切美好的祝福！

我知道你可能被问过很多次这个问题，但有没有一点点可能，能把这个变成 Resolve 的 OFX 插件？

我是一个零编程技能的人，但知道了一点"氛围编程"，我有点想踏入浑水，看看能不能移植它。

感谢任何回复！

---

## #702 **Ryan Cara** (@Ryan_Cara) · 2026-05-12 14:24

这当然是可能的。但由于事物变化和更新的速度和频率，我不认为这会是目前的优先事项。

[![:person_shrugging:](https://discuss.pixls.us/images/emoji/apple/person_shrugging.png?v=12)](https://discuss.pixls.us/images/emoji/apple/person_shrugging.png?v=12)

分别提供打印和胶片的 LUT 导出选项，将允许在两者之间放置某些效果，这对 Resolve 用户来说会很棒！令人兴奋。

[![:innocent:](https://discuss.pixls.us/images/emoji/apple/innocent.png?v=12)](https://discuss.pixls.us/images/emoji/apple/innocent.png?v=12)

---

## #703 **Vesnic** (@Vesnic) · 2026-05-12 14:30

那将会太棒了！说真的。我相信 [@arctic](/u/arctic) 知道市面上有一个叫 Genesis 的"最佳插件"之一，售价大约 2000 美元，还没有这个好。：）当然我不是在比较什么，只是说这很讽刺。

---

## #704 **WG** (@BPH3647) · 2026-05-12 14:45

> **@arctic** (帖子 #696):
> > 16 位 TIFF 回来了

非常感谢！

---

## #705 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-05-12 16:26

> **@Ryan_Cara** (帖子 #702):
> > 分别提供打印和胶片的 LUT 导出选项，将允许在两者之间放置某些效果，这对 Resolve 用户来说会很棒！令人兴奋

我也等不及要在我的胶片扫描上使用打印 LUT 了！虽然不确定具体怎么做，但也许 Resolve 21 中新的"photo"页面会派上用场。

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

确实令人兴奋！

---

## #706 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-05-12 16:52

昨晚的散步：

Lumix S5IIX, V-Log Open Gate, TTartisan 35mm f1.4, 5000K WB, Ultramax 400 on Fuji Crystal Archive

<iframe src="https://www.youtube.com/embed/xIflnwhb2HA?feature=oembed&wmode=opaque" width="480" height="360" frameborder="0" allowfullscreen="" class="youtube-onebox" seamless="seamless" sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox allow-presentation"></iframe>

光线基本上完美！只调整了曝光。没有改变对比度或饱和度。

我惊叹于经过多年的学习和尝试，现在要得到我想要的效果是如此容易。

感谢 [@arctic](/u/arctic)！

---

## #707 **Andrea** (@arctic) · 2026-05-12 18:37

> **@Ryan_Cara** (帖子 #702):
> > 但由于事物变化和更新的速度和频率

是的，事情远未完成（例如，技术讨论帖中有一些关于胶片阶段准确性下一步重大进展的激动人心的讨论；我希望这将有助于更接近 [@Anthonygansauer](/u/anthonygansauer) 的样本）。总之，事情进展得相当快。

我对这个项目感到非常兴奋（如果还不够明显的话）。

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

），我正在努力平衡睡眠和日常工作，同时避免过度劳累。

待办事项列表中有几个里程碑和想法。LUT 导出当然是一个重要的优先事项，它将实现在其他程序中的轻松集成（当然不包含非局域和随机效果）。而且 LUT 目前很灵活，如果发生重大变化，可以轻松重新导出。另外，我有一台 Lumix 相机，所以我更有动力为其创建漂亮的新 LUT！

> **@Mateusz_Grabowski** (帖子 #705):
> > 我也等不及要在我的胶片扫描上使用打印 LUT 了！

我将在同一光谱框架内探索反转负片扫描的问题，这不像应用打印 LUT 那么简单，但我心中有一个清晰的蓝图可以尝试。我相信这将是一个有趣的小挑战！

> **@Vesnic** (帖子 #703):
> > 那将会太棒了！说真的。我相信 @arctic 知道市面上有一个叫 Genesis 的"最佳插件"之一，售价大约 2000 美元

我了解市面上可用的插件，我相信它们已经在包含（或即将包含）基于物理的光谱管线。它们有完全不同的资金和资源，以及许多开发人员来部署功能。所以这永远不会是一场公平的竞赛，不幸的是。

但开源/开放科学的美妙之处在于可以与这么多善良和有能力的人合作。

所以提醒一下，这个项目不是"免费啤酒"意义上的免费。

[![:wink:](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)](https://discuss.pixls.us/images/emoji/apple/wink.png?v=12)

而是开源的，没有 pixls.us 上许多人的帮助和支持，这是不可能实现的。所以请记住感谢在这里为这个美好环境做出贡献的每个人，尤其是 [@hanatos](/u/hanatos)，他为胶片阶段的准确性做出了巨大贡献，这是输出效果如此出色的重要原因之一。

> **@Mateusz_Grabowski** (帖子 #706):
> > 光线基本上完美！

惊艳！！！

---

## #708 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-05-12 19:46

> **@arctic** (帖子 #707):
> > 我将在同一光谱框架内探索反转负片扫描的问题，这不像应用打印 LUT 那么简单，但我心中有一个清晰的蓝图可以尝试。我相信这将是一个有趣的小挑战！

哦，太棒了！我的想法是在"仅打印"LUT 下编辑反转的扫描件，就像我现在对视频做的一样。

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

但能够在 SpektraFilm 引擎中处理它听起来令人兴奋！

如果需要，我很乐意重新扫描并分享我的一些负片来测试这个功能。

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

---

## #709 **** (@RoughDraftWriting) · 2026-05-13 03:45

即使按照所有这些步骤操作，我最终总是得到损坏的 LUT。

[![:sweat:](https://discuss.pixls.us/images/emoji/apple/sweat.png?v=12)](https://discuss.pixls.us/images/emoji/apple/sweat.png?v=12)

[[![Still 2026-05-12 204432_1.13.1](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/1/71c4b7b0b629d94256e6a650dbba359e0a0b6dff_2_690x388.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/7/1/71c4b7b0b629d94256e6a650dbba359e0a0b6dff_2_690x388.jpeg)

Still 2026-05-12 204432_1.13.13840×2160 4.57 MB](/uploads/short-url/gerq0JJHl3pED4b71oSsiPGrOX5.jpeg?dl=1)

---

## #710 **** (@RoughDraftWriting) · 2026-05-13 03:46

太不可思议了！

---

## #711 **Ryan Cara** (@Ryan_Cara) · 2026-05-13 04:54

我真的认为使用为 Rec709/sRGB 制作的 CUBE 不会看起来理想，因为 SpektraFilm 实际上是设计为场景线性输入的。我想在某些情况下可能还行，但在其他情况下就会出问题。

我建议试试我之前发布的工具（基于 ART 的实现，输入和输出都是 Ap0/Linear）：

<aside class="onebox githubrepo" data-onebox-src="https://github.com/ryancara/Spektrafilm-LUT-Generator">
 <header class="source">

 [github.com](https://github.com/ryancara/Spektrafilm-LUT-Generator)
 </header>

 <article class="onebox-body">

[![图片684](https://d2x313g9lpht1q.cloudfront.net/original/3X/2/9/29a0b4676637c17dd2e4d0782c924c6a7574c29c.png)](https://d2x313g9lpht1q.cloudfront.net/original/3X/2/9/29a0b4676637c17dd2e4d0782c924c6a7574c29c.png)

### [GitHub - ryancara/Spektrafilm-LUT-Generator: Generates a CLF or Cube LUT from Arctic's...](https://github.com/ryancara/Spektrafilm-LUT-Generator)

<span class="github-repo-description">Generates a CLF or Cube LUT from Arctic's Spektrafilm spectral film simulation app.</span>

 </article>

</aside>

如果你无法解决，我可以通过私信帮助你让它工作。

或者等待 Arctic 的官方解决方案。

[![:blush:](https://discuss.pixls.us/images/emoji/apple/blush.png?v=12)](https://discuss.pixls.us/images/emoji/apple/blush.png?v=12)

---

## #712 **Vesnic** (@Vesnic) · 2026-05-13 05:44

嗯，这里的问题很常见，高光处的色偏甚至可能与恢复高光有关。如果你在 Resolve 中恢复高光，有时会出现这种情况。既然你很可能是在视频编辑软件或最多 Lightroom 中操作的，试试不要勾选"恢复高光"的复选框。

---

## #713 **Vesnic** (@Vesnic) · 2026-05-13 05:48

用你的方法，我看到以下内容被忽略了：

- 颗粒
- 光晕
- 打印眩光
- 镜头模糊
- 锐化蒙版
- 裁剪/预览/放大设置
- raw 白平衡加载设置
- 显示画布/填充设置

但耦合器没有？那太好了，因为耦合器的饱和度非常酷！

---

## #714 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-05-13 07:54

是的，这看起来像是高光裁剪、不当的色调映射或错误的色彩管理。我以前用某些 LUT 遇到过类似问题。如果你在 Resolve 中使用 CST，尝试更改色调映射和色域映射方法，也许再调整一下"Use Custom Max Input"设置。

对于 rec709 色彩空间的 LUT，在节点序列中"在下方"或之前工作非常重要。用我的方法创建的 LUT 之后不应再进行任何编辑，否则很容易出问题。

---

## #715 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-05-13 07:56

我试过安装它，但对我来说太难了。

[![:sweat_smile:](https://discuss.pixls.us/images/emoji/apple/sweat_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/sweat_smile.png?v=12)

但既然我的 LUT 对我有用，我就等 Arctic 的实现吧。

它们肯定比我的更灵活、更准确！

[![:slightly_smiling_face:](https://discuss.pixls.us/images/emoji/apple/slightly_smiling_face.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slightly_smiling_face.png?v=12)

---

## #716 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-05-13 08:18

看看不应用 LUT 时的直方图。我的猜测是，你图像中建筑物最亮的部分超出了直方图的范围。这些 LUT 无法处理超出色域的信息。尝试在 LUT 之前降低白点。

稍后我会分享一些我的 LUT 的 Google Drive 链接，你可以进一步排查问题。

[![:slightly_smiling_face:](https://discuss.pixls.us/images/emoji/apple/slightly_smiling_face.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slightly_smiling_face.png?v=12)

---

## #717 **Ryan Cara** (@Ryan_Cara) · 2026-05-13 11:10

> **@arctic** (帖子 #600):
> > ART 跳过了所有非局域和随机效果来计算 LUT，本质上只编码了平场的"平均"输出（减去目前仅随机的眩光）。

耦合器提供的任何非空间相关的饱和度都会被保留！

---

## #718 **Revanza Pratamasyah** (@Revanza_Pratamasyah) · 2026-05-14 02:33

我想知道你是否改变了绿色色调？那些郁郁葱葱的绿色太美了。

---

## #719 **Mateusz Grabowski** (@Mateusz_Grabowski) · 2026-05-14 05:20

没有！这是因为 5000K 白平衡。SpektraFilm 默认输出很暖的色调，所以我在相机中把色温降下来。再加上 Fuji Crystal Archive 相纸有最好的绿色表现。Kodak 的东西对我来说太暖了，它的绿色几乎变成了黄色。

---

## #720 **** (@Thomsen) · 2026-05-14 07:23

[@arctic](/u/arctic) 或 [@hanatos](/u/hanatos) 你们觉得在使用胶片模拟时，拍摄未压缩 raw 和压缩 raw 有区别吗？

---

## #721 **** (@Thomsen) · 2026-05-14 14:21

另外，.dng 文件够用吗？

---

## #722 **Andrea** (@arctic) · 2026-05-14 14:36

压缩 raw 文件没问题。如果是无损压缩，你只是需要更多的计算来解包；如果是有损压缩，它们智能地减少了信息量，但可能实际上不可感知。两者都会被当作 raw 处理，并转换为胶片模拟的线性 RGB 输入。

对 dng 不是特别有经验，但它应该只是 raw 文件的通用标准，所以有损/无损取决于原始制造商的 raw。转换为线性 RGB 输入应该没有问题。

---

## #723 **Aedan** (@chaert-s) · 2026-05-14 15:49

我可能有好消息要告诉你！

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

我正在开发一个 SpektraFilm 的 OFX（DaVinci Resolve）移植版本，已经几乎稳定到可以分享给大家了，不过这对某些人来说可能也是好坏参半的消息。由于我有 Mac/iOS 背景，我的版本目前是用 Apple 的原生 GPU API Metal 编写的，所以暂时无法在 Windows 上使用。

希望下周能准备好分享给大家！

---

## #724 **Andrea** (@arctic) · 2026-05-14 22:49

> **@Thomsen** (帖子 #566):
> > "感觉"有点难以评价

我在跟进这个问题，决定做一些比较。目标是停下来评估一下最近在胶片阶段"驯服"方面的进展。

这将有助于在 [SpektraFilm 技术讨论帖](https://discuss.pixls.us/t/spektrafilm-tech-discussions/57512) 中与 [@hanatos](/u/hanatos) 进行的姐妹讨论和开发。

简要总结：

- `hanatos2025` 算法从 RGB 输入生成光谱。它被设计为对人类视觉（标准观察者）产生零误差。
- 胶片灵敏度可能比人类视觉更宽，包括 UV 和 IR 侧（portra 400 是最宽的之一），并且它们具有不同的形状。
- 我们很早就注意到红色和蓝色有问题，在 `hanatos2025` 上采样之后添加了 IR 和 UV 滤镜。这是通过目测来获得漂亮的红色。
- 最近，我尝试为每种胶片优化一个通用窗口滤波器，旨在最小化实际测量光谱上的误差。
- 更近期，我尝试为每种胶片优化一个通用的 2D 曝光校正（色度 → RGB 对数曝光校正）。

2D 校正非常初级，可能不是最终的解决方案。肤色仍然有问题，这里有意让曲面不对其进行校正。肤色有独特的光谱反射率，在 550-570 nm 的绿红范围内有一个讨厌的下降，需要特别处理（敬请期待，更多内容即将发布）。

现在先看看一些照片，如果差异很小，请不要生我的气。"感觉"是由生活中和胶片模拟中许多微小的事情共同累积而成的。

[![:slight_smile:](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)](https://discuss.pixls.us/images/emoji/apple/slight_smile.png?v=12)

以下一系列图片分别为：

001 - 纯 `hanatos2025` 算法

002 - `hanatos2025` + 目测 UV 和 IR 滤镜

003 - 每种胶片的优化窗口滤波器

004 - 每种胶片的优化 2D 曲面（预计会使肤色偏冷，大约 -0.15ev 红色 +0.1ev 蓝色，我们会找到一个解决方案……）

所有四张图片组共享相同的白点，因为校正操作被设计为不影响白色。这意味着，例如，如果图像的红色看起来太偏洋红，打印滤镜可以修正，但代价是破坏白色和所有其他正确的颜色。

所有参数相同。全部使用 portra 400 和 supra endura 或 fuji crystal archive。

尝试关注红色、肤色和蓝色。

<div class="lightbox-wrapper">[[![car_001_hanatos2025](https://d2x313g9lpht1q.cloudfront.net/original/3X/b/0/b05969bc0ffc91c72258c65562fd6a743462b12f.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/b/0/b05969bc0ffc91c72258c65562fd6a743462b12f.jpeg)

car_001_hanatos2025640×427 177 KB](/uploads/short-url/pa3Bhud5qbg1mHbNZoCdpyVsLKv.jpeg?dl=1)

[[![car_002_hanatos2025_ir_uv](https://d2x313g9lpht1q.cloudfront.net/original/3X/b/1/b14e54668deb1459e7d66566bc81c58c44ac556a.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/b/1/b14e54668deb1459e7d66566bc81c58c44ac556a.jpeg)

car_002_hanatos2025_ir_uv640×427 178 KB](/uploads/short-url/piwkDuUlVKhUZWx1c4H1Kc1BS0G.jpeg?dl=1)

[[![car_003_hanatos2025_window](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/0/00b18e644edd93d914548bbadde4e74c2e377183.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/0/0/00b18e644edd93d914548bbadde4e74c2e377183.jpeg)

car_003_hanatos2025_window640×427 177 KB](/uploads/short-url/68pzqFhmanmERvG3LGtrY8dHNx.jpeg?dl=1)

[[![car_004_hanatos2025_window_surface](https://d2x313g9lpht1q.cloudfront.net/original/3X/6/d/6d4038b72aa7d16640f3d0a232272de45cf301a8.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/6/d/6d4038b72aa7d16640f3d0a232272de45cf301a8.jpeg)

car_004_hanatos2025_window_surface640×427 178 KB](/uploads/short-url/fAtDzDN6ocs0MxE5h7aItP2T25y.jpeg?dl=1)

</div>
<hr>

<div class="lightbox-wrapper">[[![portrait_001_hanatos2025](https://d2x313g9lpht1q.cloudfront.net/original/3X/f/1/f179aab8f496a07a84ca1b542e3d5f80e6f4d4b6.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/f/1/f179aab8f496a07a84ca1b542e3d5f80e6f4d4b6.jpeg)

portrait_001_hanatos2025426×640 151 KB](/uploads/short-url/ysbJUohl7DRVIIjtNqJlUKoPmrI.jpeg?dl=1)

[[![portrait_002_hanatos2025_ir_uv](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/2/523f3496dd994261e84e6f3394068f1696c98b42.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/2/523f3496dd994261e84e6f3394068f1696c98b42.jpeg)

portrait_002_hanatos2025_ir_uv426×640 151 KB](/uploads/short-url/bJAzjsMSRUTtlnsMXwC6sDLoeEa.jpeg?dl=1)

[[![portrait_003_hanatos2025_window](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/6/566faeb2ad4b7b933072e0469eb9b93b9418ba86.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/6/566faeb2ad4b7b933072e0469eb9b93b9418ba86.jpeg)

portrait_003_hanatos2025_window426×640 150 KB](/uploads/short-url/ckEl8wpCcbWTYQPAVDnWHBm4Czk.jpeg?dl=1)

[[![portrait_004_hanatos2025_window_surface](https://d2x313g9lpht1q.cloudfront.net/original/3X/6/1/619a4b76882fb2394ea18a689d5851b2b866b6b5.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/6/1/619a4b76882fb2394ea18a689d5851b2b866b6b5.jpeg)

portrait_004_hanatos2025_window_surface426×640 149 KB](/uploads/short-url/dVqT9TadIdoQavSvEQRtratkYzr.jpeg?dl=1)

</div>
<hr>

<div class="lightbox-wrapper">[[![portrait_flower_001_hanatos2025](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/1/51ecb465ae7eb56be3ee99679b44ef9af5c28224.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/1/51ecb465ae7eb56be3ee99679b44ef9af5c28224.jpeg)

portrait_flower_001_hanatos2025426×640 182 KB](/uploads/short-url/bGJOnojc0KLBGMEJE6RQDG1sSzy.jpeg?dl=1)

[[![portrait_flower_002_hanatos2025_ir_uv](https://d2x313g9lpht1q.cloudfront.net/original/3X/2/e/2ed188cf3a7916a9efdc49cf3c134800a8edb34d.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/2/e/2ed188cf3a7916a9efdc49cf3c134800a8edb34d.jpeg)

portrait_flower_002_hanatos2025_ir_uv426×640 182 KB](/uploads/short-url/6GaT7v2SvanG0AaO7V8sXbK9vsh.jpeg?dl=1)

[[![portrait_flower_003_hanatos2025_window](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/5/a5c46a1f40ab7ed8b6da38ed6a9d263a0d5b79ff.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/5/a5c46a1f40ab7ed8b6da38ed6a9d263a0d5b79ff.jpeg)

portrait_flower_003_hanatos2025_window426×640 181 KB](/uploads/short-url/nErB7UTi9NjVqHEh5WdgSOdfCV1.jpeg?dl=1)

[[![portrait_flower_004_hanatos2025_window_surface](https://d2x313g9lpht1q.cloudfront.net/original/3X/2/1/21cdfbe69a7cdaf689f541017a0f16dc1a439ca9.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/2/1/21cdfbe69a7cdaf689f541017a0f16dc1a439ca9.jpeg)

portrait_flower_004_hanatos2025_window_surface426×640 180 KB](/uploads/short-url/4P34F089Qp6OLY677khJRvVjTcd.jpeg?dl=1)

</div>
<hr>

<div class="lightbox-wrapper">[[![portrait_leaves_001_hanatos2025](https://d2x313g9lpht1q.cloudfront.net/original/3X/d/2/d241e8797b3b10cae8d6ad8edc6f2ed463a15136.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/d/2/d241e8797b3b10cae8d6ad8edc6f2ed463a15136.jpeg)

portrait_leaves_001_hanatos2025640×427 114 KB](/uploads/short-url/u01twIW5kTni6ksSPj8F0bw5fJs.jpeg?dl=1)

[[![portrait_leaves_002_hanatos2025_ir_uv](https://d2x313g9lpht1q.cloudfront.net/original/3X/e/5/e53e43ca2ca40caf426be132983e95dab323dc53.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/e/5/e53e43ca2ca40caf426be132983e95dab323dc53.jpeg)

portrait_leaves_002_hanatos2025_ir_uv640×427 113 KB](/uploads/short-url/wHYK20SRWvvCHJ1kbSnT2RTmFY7.jpeg?dl=1)

[[![portrait_leaves_003_hanatos2025_window](https://d2x313g9lpht1q.cloudfront.net/original/3X/7/2/72b6af234e1427ad516c6ada3c257da57cb2173a.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/7/2/72b6af234e1427ad516c6ada3c257da57cb2173a.jpeg)

portrait_leaves_003_hanatos2025_window640×427 112 KB](/uploads/short-url/gmNPuKrlYiIkfJjipDNIqKrqkGu.jpeg?dl=1)

[[![portrait_leaves_004_hanatos2025_window_surface](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/c/5c8342fc82fc18af40201413c81e1ef9b1732a7b.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/5/c/5c8342fc82fc18af40201413c81e1ef9b1732a7b.jpeg)

portrait_leaves_004_hanatos2025_window_surface640×427 111 KB](/uploads/short-url/dcp9ymZ7GYWCdGTskpz6PtBycNd.jpeg?dl=1)

</div>
<hr>

<div class="lightbox-wrapper">[[![portrait_tree_001_hanatos2025](https://d2x313g9lpht1q.cloudfront.net/original/3X/7/9/7941b83c4afdbbff348839278db034bd307c491b.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/7/9/7941b83c4afdbbff348839278db034bd307c491b.jpeg)

portrait_tree_001_hanatos2025427×640 145 KB](/uploads/short-url/hiGzOyrlyEbGXhAF3795HpwfCwr.jpeg?dl=1)

[[![portrait_tree_002_hanatos2025_ir_uv](https://d2x313g9lpht1q.cloudfront.net/original/3X/7/7/772b696b6578c44386ac6d2afd375e74c6447312.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/7/7/772b696b6578c44386ac6d2afd375e74c6447312.jpeg)

portrait_tree_002_hanatos2025_ir_uv427×640 146 KB](/uploads/short-url/h0dPm569mvahCMwF8FqxAMZXytc.jpeg?dl=1)

[[![portrait_tree_003_hanatos2025_window](https://d2x313g9lpht1q.cloudfront.net/original/3X/d/2/d2e1f60d3a12fb1c229beff3a60ee9110682dfe6.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/d/2/d2e1f60d3a12fb1c229beff3a60ee9110682dfe6.jpeg)

portrait_tree_003_hanatos2025_window427×640 145 KB](/uploads/short-url/u5yo4DngjO1ZyZDTxBbuFC2vkNg.jpeg?dl=1)

[[![portrait_tree_004_hanatos2025_window_surface](https://d2x313g9lpht1q.cloudfront.net/original/3X/4/8/486220c08b69531a6a98bc0a1d3d00a5c60fe88d.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/4/8/486220c08b69531a6a98bc0a1d3d00a5c60fe88d.jpeg)

portrait_tree_004_hanatos2025_window_surface427×640 144 KB](/uploads/short-url/akkCbWp0k2nNmmqhQtrRMLcweoB.jpeg?dl=1)

</div>
<hr>

<div class="lightbox-wrapper">[[![sunflowers_001_hanatos2025](https://d2x313g9lpht1q.cloudfront.net/original/3X/1/f/1f9005e8c4d61a448b40a9090c740e3cf468baeb.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/1/f/1f9005e8c4d61a448b40a9090c740e3cf468baeb.jpeg)

sunflowers_001_hanatos2025426×640 166 KB](/uploads/short-url/4vdmUNT48Xs4YJpZAH0oAdnRoGT.jpeg?dl=1)

[[![sunflowers_002_hanatos2025_ir_uv](https://d2x313g9lpht1q.cloudfront.net/original/3X/4/3/436bc33d948e081fc5df6301fc8b69a9ec635fa7.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/4/3/436bc33d948e081fc5df6301fc8b69a9ec635fa7.jpeg)

sunflowers_002_hanatos2025_ir_uv426×640 165 KB](/uploads/short-url/9CqRZVYPKfburFCInwrI21i9pt5.jpeg?dl=1)

[[![sunflowers_003_hanatos2025_window](https://d2x313g9lpht1q.cloudfront.net/original/3X/3/8/384a89891da99ee531f58f3f583b30abad6d6a85.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/3/8/384a89891da99ee531f58f3f583b30abad6d6a85.jpeg)

sunflowers_003_hanatos2025_window426×640 164 KB](/uploads/short-url/81YqT09sGE0g0TdDi86LTMe3hKl.jpeg?dl=1)

[[![sunflowers_004_hanatos2025_window_surface](https://d2x313g9lpht1q.cloudfront.net/original/3X/7/d/7d59acccabb235e91015f36b1b8913e4b480b6d4.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/7/d/7d59acccabb235e91015f36b1b8913e4b480b6d4.jpeg)

sunflowers_004_hanatos2025_window_surface426×640 164 KB](/uploads/short-url/hSTOjNNmfeu1eOqqMCj2IPrFtCA.jpeg?dl=1)

</div>

几点评论（也是个人观点，不要当成科学结论）：

- 未过滤的 `hanatos2025` 饱和度最高，因为 uv 和 ir 尾部增加了通道分离。在最初未过滤的时候，耦合器也较低。每次校正 001→002→003→004 都在抑制过冲颜色的饱和度，同时也增加了欠饱和颜色的饱和度（不那么张扬，有点不易察觉）。
- 由于过冲饱和度得到了抑制，耦合器随时间稳步增加。在最初只有 `hanatos2025` 的时候，我们承受不了大量的帧间效应，因为图像会很快出问题。现在我们有更多的余量，因为颜色在饱和度上更加平衡。
- 这不是色彩偏好的问题，而是追求最准确的色彩。色彩偏好可以在此基础上叠加（饱和度、色偏等）。需要验证的是，更"正确"的模拟应该能提供更好的肤色。

最后还有 [@Anthonygansauer](/u/anthonygansauer) 的图像。我没有花太多精力去匹配扫描件，但当胶片算法稳定后，我会再试一次。你可以注意到目标中主要变化的颜色。

<div class="lightbox-wrapper">[[![antony_target_001_hanatos2025](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/d/ad94e71b7c075e6fc38defdf9f48568ee4c352e7.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/a/d/ad94e71b7c075e6fc38defdf9f48568ee4c352e7.jpeg)

antony_target_001_hanatos2025640×426 127 KB](/uploads/short-url/oLzCKPAjdqpqdQfXd4ui77mhgAT.jpeg?dl=1)

[[![antony_target_002_hanatos2025_ir_uv](https://d2x313g9lpht1q.cloudfront.net/original/3X/3/7/376b41f8d2e52e69424d0d9a350bfc80c6d00b8f.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/3/7/376b41f8d2e52e69424d0d9a350bfc80c6d00b8f.jpeg)

antony_target_002_hanatos2025_ir_uv640×426 128 KB](/uploads/short-url/7Ug3Gv3X9b1lxoAXlLHM9KKvNuv.jpeg?dl=1)

[[![antony_target_003_hanatos2025_window](https://d2x313g9lpht1q.cloudfront.net/original/3X/9/2/9296a3b8c95c77819e63b45b034f66eb8a602386.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/9/2/9296a3b8c95c77819e63b45b034f66eb8a602386.jpeg)

antony_target_003_hanatos2025_window640×426 128 KB](/uploads/short-url/kUMsaK9SlKvF02WAwa0KppXxGcK.jpeg?dl=1)

[[![antony_target_004_hanatos2025_window_surface](https://d2x313g9lpht1q.cloudfront.net/original/3X/2/a/2aa2cd706ad2901174f587f12b028c07adb52f16.jpeg)](https://d2x313g9lpht1q.cloudfront.net/original/3X/2/a/2aa2cd706ad2901174f587f12b028c07adb52f16.jpeg)

antony_target_004_hanatos2025_window_surface640×426 127 KB](/uploads/short-url/65aR6nJukIrjPSKVaJN2HZ26h38.jpeg?dl=1)

</div>

以及参考的 RA-4 打印版本

[[![antony_target_005_analog](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/9/f933e483473c0d7e456df2fb8eb754168c081dea_2_690x551.jpeg)](https://d2x313g9lpht1q.cloudfront.net/optimized/3X/f/9/f933e483473c0d7e456df2fb8eb754168c081dea_2_690x551.jpeg)

antony_target_005_analog1208×965 168 KB](/uploads/short-url/zyy4ju1m0eQNkygFOqciaE6c8lQ.jpeg?dl=1)

---

## #725 **Tim** (@Soupy) · 2026-05-15 00:31

在广色域校准显示器上观看，基于非常不科学的"感觉"，我在几乎所有情况下都更喜欢 003，其次是 004 和 002。不过，与 [@Anthonygansauer](/u/anthonygansauer) 的图像相比，004 对我来说看起来最匹配。

---

## #726 **Bob** (@PhotoPhysicsGuy) · 2026-05-15 01:48

同意。仅凭"感觉"，003 全程胜出。与 RA-4 扫描件相比，004 更接近。色彩检查器色块显示，模拟结果的饱和度比 RA-4 扫描件高很多。香槟杯也是如此。是不是耦合器强度太高了？

---

*本文档由 Discourse 抓取工具自动生成*
*原始链接: https://discuss.pixls.us/t/48209*
