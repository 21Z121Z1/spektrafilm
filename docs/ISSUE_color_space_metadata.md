# English Version (GitHub Issue)

## Bug: Saved images do not embed the selected color space (ICC profile / chromaticities)

### Description

When saving an output image, the **Saving color space** dropdown in the Output section is respected for pixel-level color space conversion (the `colour.RGB_to_RGB()` call works correctly), but the resulting file contains **no color space metadata** — no ICC profile for PNG/JPEG, and no chromaticities attribute for EXR.

As a result, any downstream application that opens the saved file will default to **sRGB**, regardless of the user's actual selection (e.g. Display P3, Adobe RGB, ProPhoto RGB).

### Steps to Reproduce

1. Load an input image and run a simulation (Preview or Scan).
2. In the **Output** section, set **Saving color space** to `Display P3` (or any non-sRGB space).
3. Click **SAVE** and export as PNG or JPEG.
4. Open the saved file in any color-managed viewer (e.g. Preview.app, Photoshop, GIMP).
5. Inspect the embedded ICC profile — there is none; the file is assumed to be sRGB.

### Expected Behavior

The saved file should contain an ICC profile (for PNG/JPEG) or chromaticities metadata (for EXR) that corresponds to the selected saving color space, so that downstream applications can correctly interpret the image data.

### Actual Behavior

- **PNG/JPEG**: No ICC profile is embedded. Applications default to sRGB.
- **EXR**: No `chromaticities` attribute is set on the `ImageSpec`. Applications default to sRGB primaries.

The pixel data itself is correctly converted — only the metadata is missing.

### Root Cause

`save_image_oiio()` in `src/spektrafilm/utils/io.py` creates an `oiio.ImageSpec` with only width, height, channels, and data type. No color space attributes are attached. The `write_image_metadata()` function copies source EXIF/IPTC/XMP tags but does not handle ICC profiles or color space descriptors.

### Proposed Fix

1. Add a `color_space` parameter to `save_image_oiio()`.
2. For PNG/JPEG: Embed an ICC profile via Pillow (`PIL.Image.save(icc_profile=...)`), since OIIO's libpng has issues with small ICC v4 profiles.
3. For EXR: Set the `chromaticities` attribute on the `ImageSpec` from colour-science primaries.
4. Bundle standard ICC v2 profiles (sRGB, Display P3, DCI-P3, Adobe RGB, BT.2020, ProPhoto RGB) in `src/spektrafilm/data/icc/` for cross-platform support.
5. Update `save_output_layer()` in `controller.py` to pass `saving_color_space` to the save function.

---

# 中文版本（对照）

## Bug：保存的图片未嵌入所选色域的 ICC 配置文件 / 色度信息

### 描述

在保存输出图片时，Output 面板中的 **Saving color space** 下拉菜单在像素层面的色域转换上是正确的（`colour.RGB_to_RGB()` 调用正常工作），但输出文件中**没有嵌入任何色域元数据** —— PNG/JPEG 没有 ICC 配置文件，EXR 没有 chromaticities 属性。

因此，任何下游应用程序打开保存的文件时都会默认使用 **sRGB**，忽略用户实际选择的色域（如 Display P3、Adobe RGB、ProPhoto RGB）。

### 复现步骤

1. 加载输入图片并运行模拟（Preview 或 Scan）。
2. 在 **Output** 面板中，将 **Saving color space** 设为 `Display P3`（或其他非 sRGB 色域）。
3. 点击 **SAVE**，导出为 PNG 或 JPEG。
4. 在任何支持色彩管理的查看器中打开保存的文件（如 Preview.app、Photoshop、GIMP）。
5. 检查嵌入的 ICC 配置文件 —— 不存在，文件被默认当作 sRGB。

### 预期行为

保存的文件应包含与所选保存色域对应的 ICC 配置文件（PNG/JPEG）或 chromaticities 元数据（EXR），以便下游应用程序正确解读图片数据。

### 实际行为

- **PNG/JPEG**：未嵌入 ICC 配置文件，应用程序默认使用 sRGB。
- **EXR**：`ImageSpec` 上未设置 `chromaticities` 属性，应用程序默认使用 sRGB 原色。

像素数据本身转换正确 —— 只是缺少元数据。

### 根本原因

`src/spektrafilm/utils/io.py` 中的 `save_image_oiio()` 创建 `oiio.ImageSpec` 时只设置了宽高、通道数和数据类型，未附加任何色域属性。`write_image_metadata()` 函数复制源文件的 EXIF/IPTC/XMP 标签，但不处理 ICC 配置文件或色域描述符。

### 修复方案

1. 为 `save_image_oiio()` 添加 `color_space` 参数。
2. PNG/JPEG：通过 Pillow 嵌入 ICC 配置文件（`PIL.Image.save(icc_profile=...)`），因为 OIIO 的 libpng 对小型 ICC v4 配置文件存在兼容性问题。
3. EXR：从 colour-science 的原色数据中提取色度信息，设置 `ImageSpec` 的 `chromaticities` 属性。
4. 在 `src/spektrafilm/data/icc/` 中打包标准 ICC v2 配置文件（sRGB、Display P3、DCI-P3、Adobe RGB、BT.2020、ProPhoto RGB）以支持跨平台。
5. 更新 `controller.py` 中的 `save_output_layer()`，将 `saving_color_space` 传递给保存函数。
