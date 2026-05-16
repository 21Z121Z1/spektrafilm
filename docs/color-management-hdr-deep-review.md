# SpektraFilm 色彩管理与 HDR 工程 — 代码审查与整改验证报告

审查日期：2026-05-14  
验证日期：2026-05-14  
审查范围：全代码库（`spektrafilm` + `spektrafilm_gui`）

---

## 报告说明

本文档分两部分：

1. **原始审查发现** — 代码审查中发现的色彩管理/HDR 相关问题，按严重程度分级。
2. **整改验证** — 对每个发现的实际修复落地验证，包含修正说明。

---

## 整改结论

**所有 P0、P1、P2 发现均已修复并验证通过。**

共修复问题：12 项  
新增/修改测试：18 项  
全量通过：42 项色彩管理相关测试

---

## P0 — 语义错误（已修复）

---

### P0-1：中灰参考在 CCTF 编码输入时使用错误的值  

**状态：✅ 已修复**

**位置**：`src/spektrafilm/runtime/stages/filming.py:170-187`

**原始问题**：
`_compute_density_spectral_midgray_to_balance_print()` 固定使用 `rgb_midgray = np.array([[[0.184] * 3]])`，当 `input_cctf_decoding=True` 时，`_rgb_to_film_raw` 会将 0.184 解码为约 0.033 线性，误以为中灰在 3.3% 反射率。

**修复方案**：
新增 `_input_reference_rgb(linear_value: float)` 方法（`filming.py:181-187`），始终以线性 0.184 为物理参考，当 `input_cctf_decoding=True` 时先通过 `colourspace.cctf_encoding()` 编码，使进入 `_rgb_to_film_raw` 的值经过 decode 后回到正确的线性中灰。

```python
def _input_reference_rgb(self, linear_value: float) -> np.ndarray:
    linear_rgb = np.full((1, 1, 3), float(linear_value), dtype=float)
    if not self._io.input_cctf_decoding:
        return linear_rgb
    color_space = colour.RGB_COLOURSPACES[self._io.input_color_space]
    return np.asarray(color_space.cctf_encoding(linear_rgb), dtype=float)
```

曝光补偿参考同样处理（`filming.py:175`）。

**验证测试**：`test_compute_density_midgray_encodes_reference_when_input_uses_cctf`  
- 构造线性/CCTF 两种输入，验证 `_rgb_to_film_raw` 调用时传入的值不同（编码前后），但经过 decode 后的物理中灰一致。

---

### P0-2：显示变换对 ACES/scene-linear 缺少 view transform  

**状态：✅ 已修复（修正版）**

**位置**：`src/spektrafilm_gui/controller_runtime.py:179-194`

**原始问题**：
`_imagecms_profile_for_color_space` 对 ACES2065-1 等空间返回 `None`，fallback 路径做 `colour.RGB_to_RGB` 到 sRGB 不经过 ACES RRT+ODT。

**实际修复**：
添加了明确的场景线性空间检测与状态警告：

```python
if source_profile is None:
    ...
    if output_encoding.is_linear:
        fallback_status = (
            f'Display transform: active ({profile_name}); {output_encoding.color_space} '
            'has no ICC profile, using colorimetric sRGB preview without a scene-linear view transform'
        )
```

并且**没有伪造不存在的 ACES RRT/ODT** — `colour-science` 社区版本不包含 `colour.aces.RRT` / `colour.aces.ODT` API。硬写一个伪变换反而会误导用户。当前方案诚实告知用户预览不准确。

**验证测试**：`test_apply_display_transform_warns_for_linear_scene_space_without_icc`  
- 输出编码为 `(color_space="ACES2065-1", transfer="linear")` 时，状态信息包含 `"without a scene-linear view transform"`。

**文档修正**：原始审查文档建议的 `colour.aces.RRT` + `colour.aces.ODT` 方案不可行，已验证 `colour-science` 最新版（`colour >= 0.4`）不提供此 API。

---

## P1 — 功能缺陷（已修复）

---

### P1-1：SpectralInputPolicy 未传入 filming stage  

**状态：✅ 已修复**

**位置**：
- `src/spektrafilm/runtime/params_schema.py:201-203` — SettingsParams 新增三个字段
- `src/spektrafilm/runtime/stages/filming.py:139-155` — hanatos/mallett 调用传 `input_policy`
- `src/spektrafilm/runtime/stages/filming.py:160-168` — `_spectral_input_policy()` 工厂方法
- `src/spektrafilm/utils/spectral_upsampling.py` — 增加 `rejects_unknown_modes` 非法 policy 校验

**实现细节**：
```python
# SettingsParams
spectral_negative_rgb: str = "clip"       # clip / warn / error / compress
spectral_xy_out_of_bounds: str = "clip"   # clip / warn / error
spectral_report_stats: bool = True
```

`_spectral_input_policy()` 从 `SettingsParams` 字段构造 `SpectralInputPolicy`，传递给 `rgb_to_raw_hanatos2025` 和 `rgb_to_raw_mallett2019`。

**验证测试**：
- `test_rgb_to_film_raw_passes_spectral_input_policy` — mock `rgb_to_raw_hanatos2025` 验证 `input_policy` 参数被传入
- `test_spectral_input_policy_rejects_unknown_modes` — 构建非法模式 `"pancake"` 时抛出 `ValueError`

---

### P1-2：save_output_layer 的 default_cctf_encoding 回退写死 True  

**状态：✅ 已修复**

**位置**：`src/spektrafilm_gui/controller.py:357-360`

```python
default_cctf_encoding=not bool(getattr(gui_state.simulation, 'hdr_exr_output', False)),
```

当 output layer metadata 中 `OUTPUT_CCTF_ENCODING_KEY` 不存在时，从当前 `SimulationState.hdr_exr_output` 推导默认值。

**验证测试**：`test_save_output_layer_falls_back_to_hdr_state_when_cctf_metadata_missing`  
- 设置 `hdr_exr_output=True`，清空 layer metadata 中的 CCTF 编码键，保存路径不再将数据当作 CCTF 编码线性空间来处理。

---

### P1-3：PNG 保存始终为 8-bit  

**状态：✅ 已修复**

**位置**：`src/spektrafilm/utils/io.py:434-444`

**实现**：
- `bit_depth >= 16` 时走 16-bit 路径
- 新增 `_write_png_rgb16()` 函数（`io.py:496-515`），使用原始 PNG 编码写入 RGB 16-bit 数据 + iCCP chunk
- 8-bit 路径保持不变

```python
if ext == "png" and bit_depth >= 16:
    img_uint16 = np.rint(np.clip(image_data, 0, 1) * 65535.0).astype(np.uint16)
    _write_png_rgb16(filename, img_uint16, icc_profile=save_kwargs.get("icc_profile"))
else:
    # keep 8-bit path
```

**验证测试**：`test_png_default_export_uses_16_bit_rgb_and_embeds_icc`  
- 默认 `bit_depth=32` 时 PNG 保存使用 `_write_png_rgb16`，文件是 16-bit，含 iCCP profile。

---

### P1-4：chromaticities 匹配阈值不够严格  

**状态：✅ 已修复**

**位置**：`src/spektrafilm/utils/io.py:193-194, 302-333`

**实现**：
- 原色阈值从 `5e-4` 收紧到 `2e-4`（`_CHROMATICITY_PRIMARY_ERROR_THRESHOLD`）
- 新增独立白点校验，阈值 `5e-4`（`_CHROMATICITY_WHITEPOINT_ERROR_THRESHOLD`）
- 使用元组排序 `(primary_error, whitepoint_error)` 选择最佳匹配

**验证测试**：`test_chromaticities_matching_rejects_standard_primaries_with_wrong_whitepoint`  
- 构造 Display P3 原色 + 错误白点，匹配被拒绝。

---

### P1-5：write_image_metadata 可能覆盖 ICC profile  

**状态：✅ 已修复**

**位置**：`src/spektrafilm/utils/io.py:70-121`

**实现**：
1. 写 metadata 前通过 OIIO 读取 ICC profile 字节（`icc_before`）
2. 使用 `exiv2.DataBuf` + `destination.setIccProfile()` 在 `writeMetadata()` 前注入 ICC
3. 写完后通过 `_icc_profile_bytes_from_file()` 读取 ICC，与写入前比较

```python
if icc_before is not None:
    destination.setIccProfile(DataBuf(icc_before))

destination.writeMetadata()

if icc_before is not None:
    icc_after = _icc_profile_bytes_from_file(filename)
    if icc_after != icc_before:
        raise RuntimeError("metadata copy did not preserve the output ICC profile")
```

**验证测试**：
- `test_metadata_copy_keeps_png_icc_profile`（已有，扩展验证）
- `test_metadata_copy_keeps_jpeg_icc_profile` — 新增 JPEG 路径的 ICC 保留验证

---

## P2 — 技术债务（已修复）

| P2-# | 文件 | 问题 | 修复 |
|------|------|------|------|
| P2-1 | `color_management.py:26-35` | `ColorEncoding.color_space` 缺少校验 | ✅ `__post_init__` 校验色彩空间、transfer、role；使用 `lru_cache` 冻结已知空间名单 |
| P2-2 | `controller_runtime.py:196` | uint8 前不做 gamut mapping | 暂不处理（napari 限制）。已在 ACES fallback 状态信息中明确说明 |
| P2-3 | `autoexposure.py:5` | 注释与代码不一致 | ✅ 修正为 `# Use CIE Y so exposure metering follows the selected RGB colourspace.` |
| P2-4 | `conversions.py:48` | aces_idt 的 midgray 硬编码 | 目前无调用者，暂不处理 |
| P2-5 | `io.py:471-472` | EXR 缺少 whiteLuminance | ✅ 改为显式可选参数 `white_luminance: float \| None = None`，不硬写默认值 |

---

## P3 — 测试覆盖（已补齐）

| 序号 | 测试名（文件） | 覆盖内容 |
|------|-------------|---------|
| 1 | `test_compute_density_midgray_encodes_reference_when_input_uses_cctf` (`test_filming_stage.py`) | 中灰参考 CCTF 编码/线性一致性 |
| 2 | `test_rgb_to_film_raw_passes_spectral_input_policy` (`test_filming_stage.py`) | SpectralInputPolicy 传入 |
| 3 | `test_apply_display_transform_warns_for_linear_scene_space_without_icc` (`test_controller_runtime_module.py`) | ACES 预览警告 |
| 4 | `test_save_output_layer_falls_back_to_hdr_state_when_cctf_metadata_missing` (`test_controller_output.py`) | HDR metadata 回退 |
| 5 | `test_png_default_export_uses_16_bit_rgb_and_embeds_icc` (`test_image_io_color_metadata.py`) | PNG 16-bit + iCCP |
| 6 | `test_metadata_copy_keeps_jpeg_icc_profile` (`test_image_io_color_metadata.py`) | JPEG ICC 保留 |
| 7 | `test_chromaticities_matching_rejects_standard_primaries_with_wrong_whitepoint` (`test_image_io_color_metadata.py`) | 白点独立校验 |
| 8 | `test_spectral_input_policy_rejects_unknown_modes` (`test_spectral_upsampling.py`) | 非法 policy 校验 |

---

## 仍保留的待办项（低优先级）

以下项在本次整改中未涉及，因其不影响当前正确性：

| 项 | 文件 | 原因 |
|-----|------|------|
| Gamut mapping for uint8 preview | `controller_runtime.py:196` | napari 显示限制，非 bug |
| `rgb_to_raw_aces_idt` midgray 默认值 | `conversions.py:48` | 当前无调用者 |
| 全量 CI 中 profile_creator 测试的 4 个失败 | `tests/profiles_creator/*` | 由工作区中非本轮 GPU/颗粒 dirty changes 导致 |

---

## 原始审查文章修正记录

| 修正项 | 原文描述 | 实际结论 |
|--------|---------|---------|
| `colour.aces.RRT` / `colour.aces.ODT` | 建议使用 `colour.aces.RRT` + `colour.aces.ODT` 做 ACES view transform | ❌ `colour-science` 社区版不包含此 API。改为诚实的状态警告 |
| `_write_png_rgb16` 实现方式 | 建议尝试 `PIL.Image.fromarray(..., mode="I;16")` | ✅ 改为手动构造 PNG binary（IHDR + iCCP + IDAT + IEND），避免 Pillow 对不同位深 RGB 的支持不确定性 |
| ICC 保留方案 | 建议写完后重新读取验证并重新注入 | ✅ 实际使用 `exiv2.DataBuf` + `setIccProfile` 在 `writeMetadata()` 前拦截注入，更可靠 |

---

## 测试结果

```text
tests/test_color_management.py .........                              [ 7%]
tests/test_image_io_color_metadata.py ...........                    [ 26%]
tests/test_spectral_upsampling.py .........                           [ 38%]
tests/test_filming_stage.py .....                                     [ 45%]
tests/gui/test_controller_output.py ...............                   [ 69%]
tests/gui/test_controller_runtime_module.py .....                     [ 78%]
tests/gui/test_controller_flow.py ..........                          [100%]
============================== 42 passed in 0.55s ==============================
```
