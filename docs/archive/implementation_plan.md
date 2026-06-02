# 色彩管理系统与 HDR EXR 融合重构方案

本方案基于对 `color-management-system-review.md`（内功：底层架构）与 `hdr_exr_output_plan.md`（招式：业务落地）的综合评估，确立了“高内聚”的完美互补执行路径。

## 核心概念的“合并映射”

我们在底层的 `ColorEncoding` 数据结构中直接吸纳 HDR 方案提出的控制需求，彻底消灭零散的布尔开关技术债：

| HDR EXR 方案诉求 | CMS 方案对应概念 / 合并代码表达 |
| :--- | :--- |
| `output_cctf_encoding = False` | `ColorEncoding(transfer="linear")` |
| `output_clip_max = False` | `ColorEncoding(clip_highlights=False)` |
| `output_clip_min = True` | `ColorEncoding(clip_negatives=True)` |
| EXR 保存强制线性 | `ensure_save_compatible(encoding, ext=".exr")` 自动覆盖属性 |
| GUI 新增 `HDR EXR output` | GUI 选项直接生成预设的 `ColorEncoding` 实例传递给运行时 |

---

## 阶段执行路径 (The Golden Route)

建议按照以下 4 个阶段推进代码落地，既不破坏现有链路，又能最快拿到 HDR EXR 成果，并完成底层色彩管理的彻底净化。

### 阶段 1：建立色彩契约（打基建）
- 引入统一的 `ColorEncoding` 数据类：
  ```python
  @dataclass(frozen=True)
  class ColorEncoding:
      color_space: str
      transfer: Literal["linear", "cctf"]
      role: Literal["scene", "display"]
      clip_negatives: bool = True
      clip_highlights: bool = True
  ```
- 清理代码中所有硬编码的 `output_cctf_encoding = True`。
- 让 `SimulationResult` 和 GUI 输出图层（Layer Metadata）正确携带 `ColorEncoding` 对象。

### 阶段 2：打通 HDR 阻塞点（运行时动刀）
- **修改扫描端**：拆解 `_apply_cctf_encoding_and_clip`，根据 `encoding.transfer` 决定是否进行光电编码，根据 `encoding.clip_negatives` 和 `encoding.clip_highlights` 决定是否裁剪。
- **修复黑白校正死角**：将 `ColorReferenceService` 中的硬裁剪（`np.clip(m * y + q, 0, 1)`）替换为尊重 `ColorEncoding` 裁剪策略的逻辑。

### 阶段 3：文件 I/O 与 GUI 暴露（HDR EXR 落地）
- **统一保存逻辑**：改造 `save_image_oiio`，实施格式校验。遇到 `.exr` 保存时强制覆写为线性 HDR（`transfer="linear", clip_highlights=False`）；禁止将线性 HDR 存为标准 JPEG/PNG。
- **GUI 添加选项**：在面板新增 `HDR EXR output` 勾选框，勾选时自动装配激活 HDR 的 `ColorEncoding` 给引擎。
- 增加 EXR 的 float/half 写入及 `chromaticities` 的写入。

### 阶段 4：收尾色彩管理的进阶项（完善闭环）
- 修复中性灰 `_simple_rgb_to_density_spectral()` 硬编码 sRGB 路径问题。
- 修复普通图片的输入元数据读取（自动识别 EXR/ICC 色域）。
- 让显示器预览（Display Transform）直接读取源 ICC 进行转换，绕过 sRGB 中间瓶颈。

---

## 测试与验证 (Verification Plan)
- **单元测试**：为 `ColorEncoding` 的构建及映射增加测试；验证 `ScanningStage` 和 `ColorReferenceService` 在不同契约下的裁剪表现。
- **保存测试**：验证 `.exr` 写入能保留 `> 1.0` 的浮点值，并且写入了 `chromaticities`。验证 `.jpg/.png` 在线性 HDR 模式下被正确拦截或警告。
- **集成测试**：每次修改后使用 `XcodeGen` 生成项目并确保整体管线编译运行无误。

## 待确认事项 (User Review Required)
以上 4 个阶段构成了我们接下来的开发任务蓝图。如果确认无误，我们将从 **阶段 1：建立色彩契约** 开始实施编码。
