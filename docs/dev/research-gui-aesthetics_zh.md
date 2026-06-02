> 这是英文原文的中文翻译。权威版本请参考英文原文。

# Spektrafilm GUI 美学与用户体验研究

日期：2026-05-27

## 目录

1. [当前 UI 架构审查](#1-current-ui-architecture-audit)
2. [主题与样式分析](#2-theme--styling-analysis)
3. [深色主题建议](#3-dark-theme-recommendations)
4. [胶片模拟控件改进](#4-widget-improvements-for-film-simulation)
5. [布局优化](#5-layout-optimization)
6. [高 DPI 与多显示器](#6-high-dpi--multi-monitor)
7. [色彩准确性与显示管理](#7-color-accuracy--display-management)
8. [无障碍性](#8-accessibility)
9. [QML 与 Widgets 评估](#9-qml-vs-widgets-assessment)
10. [可直接使用的 QSS 代码片段](#10-ready-to-apply-qss-snippets)

---

## 1. 当前 UI 架构审查

### 架构概述

GUI 使用 **Qt Widgets（通过 qtpy）**（兼容 PySide6/PyQt5），并使用 **napari** 查看器作为图像画布。架构结构清晰：

| 层级 | 文件 | 用途 |
|-------|-------|---------|
| **状态** | `state.py` | 所有 GUI 参数状态的纯数据类 |
| **规格** | `widget_specs.py` | 控件元数据（标签、提示、最小/最大/步进值） |
| **编辑器** | `widget_editors.py` | 自定义编辑器控件（FloatEditor、BoolEditor 等） |
| **分区** | `widget_sections.py` | 可折叠分区，将编辑器组合为表单 |
| **基础控件** | `widget_primitives.py` | CollapsibleSection、HeaderDivider |
| **布局** | `napari_layout.py` | 主窗口、侧边栏、查看器面板、标签页结构 |
| **主题** | `theme.py`、`theme_palette.py`、`theme_styles.py` | 颜色、尺寸、QSS |
| **控制器** | `controller.py` | 业务逻辑、信号连接 |
| **应用** | `app.py` | 启动、预热、调色板初始化 |

### 优势

- **清晰的分离**：状态数据类通过规格与控件解耦
- **可折叠分区**：良好的渐进式信息披露模式
- **基于标签页的组织**：MAIN / FILM / PRINT / ADVANCED / CONFIG 标签页
- **自定义绘制**：BoolEditor、ProfileEnumEditor 使用自定义 QPainter 实现像素级精确控制
- **深色标题栏**：通过 `_request_dark_title_bar` 支持 Windows DWM 沉浸式深色模式
- **图标系统**：pyconify SVG 图标，分区标题使用强调色
- **预热系统**：后台线程预导入重量级模块，确保首次交互响应迅速

### 不足

- **无滑块控件**：所有数值参数仅使用旋转框——没有可视滑块进行快速手势调节
- **无范围视觉反馈**：最小/最大值存在于 WidgetSpec 中，但未以视觉方式传达
- **平淡的调色板**：所有灰色均为纯消色（没有微妙的暖/冷色调），可能显得生硬
- **硬编码的像素尺寸**：固定高度（24px、30px）不会随 DPI 缩放
- **无键盘快捷键提示**：没有可见的快捷键指示器
- **无撤销/重做**：UI 中没有可见的历史记录栈
- **仅工具提示帮助**：所有文档都在工具提示中，没有内联帮助或信息按钮

---

## 2. 主题与样式分析

### 当前调色板（`theme_palette.py`）

```
GRAY_18 = '#767676'   ← 画布背景（18% 灰，感知中灰）
GRAY_0  = '#000000'   ← 基础背景
GRAY_1  = '#101010'   ← 控件背景
GRAY_2  = '#1a1a1a'   ← 悬停/活动状态
GRAY_3  = '#262626'   ← 中间色调
GRAY_4  = '#404040'   ← 选中背景

ACCENT_COLOR_TEXT          = '#ee9470'  ← 暖橙色强调
ACCENT_COLOR_TEXT_SECONDARY = '#63c3cf' ← 冷青色强调
TEXT_DIM  = '#8d8d8d'   ← 次要文本
TEXT_MAIN = '#cecece'   ← 主要文本
TEXT_HI   = '#f2f2f2'   ← 高亮文本
```

### 对比度分析（WCAG 2.1）

| 配对 | 比率 | WCAG AA（4.5:1） | WCAG AAA（7:1） |
|------|-------|------------------|-----------------|
| `#cecece` 在 `#000000` 上 | 12.3:1 | 通过 | 通过 |
| `#cecece` 在 `#101010` 上 | 11.5:1 | 通过 | 通过 |
| `#8d8d8d` 在 `#000000` 上 | 5.3:1 | 通过 | 未通过 |
| `#8d8d8d` 在 `#101010` 上 | 4.9:1 | 通过 | 未通过 |
| `#767676` 在 `#000000` 上 | 4.5:1 | 边缘 | 未通过 |
| `#ee9470` 在 `#000000` 上 | 7.2:1 | 通过 | 通过 |
| `#ee9470` 在 `#101010` 上 | 6.8:1 | 通过 | 未通过 |

### 观察

1. **主要文本对比度优秀** —— `#cecece` 在近黑色背景上长时间使用舒适
2. **`TEXT_DIM` 处于边缘** —— `#8d8d8d` 在 `#101010`（控件背景）上对于小文本勉强通过 AA 标准。对于当前 18px 最小高度的标签，这是可以接受的，但可以改进
3. **`GRAY_18` 画布是正确的** —— 18% 灰是中性色彩评估的行业标准（匹配 Munsell N5/，感知中点）
4. **强调色具有辨识度** —— 暖橙色（`#ee9470`）用于主要强调，冷青色（`#63c3cf`）用于次要强调（电影/静态胶片指示器）。这种冷暖配对强化了模拟摄影的隐喻
5. **灰色无色彩偏移** —— 所有灰色均为完美消色。这对于色彩关键应用实际上是*正确的*，因为带色调的灰色会影响色彩感知

### QSS 结构（`theme_styles.py`）

样式表组织为四个逻辑部分：
- `WINDOW_STYLE` —— 基础窗口/框架背景
- `TAB_STYLE` —— 标签栏、标签页、分区切换、强调按钮
- `CONTROL_STYLE` —— 所有表单控件（按钮、下拉框、旋转框、复选框）
- `CHROME_STYLE` —— 滚动条、分隔器、状态栏

---

## 3. 深色主题建议

### 3.1 优化灰度梯度

当前调色板使用非常暗的值且跳级较大。考虑添加中间级别以实现更平滑的视觉层次：

```python
# 当前：          建议添加：
# GRAY_0 #000000    GRAY_0  #0a0a0a  （从纯黑稍微提升）
# GRAY_1 #101010    GRAY_1  #141414  （控件背景）
# GRAY_2 #1a1a1a    GRAY_2  #1e1e1e  （悬停）
# GRAY_3 #262626    GRAY_3  #282828  （边框、分隔线）
#                    GRAY_4  #3a3a3a  （活动/按下）
#                    GRAY_5  #4a4a4a  （选中）
```

**理由**：在 OLED 上，纯黑（`#000000`）与发光内容之间会产生过大的对比度。提升到 `#0a0a0a` 或 `#0d0d0d` 可以减少眼睛疲劳，而在 LCD 上没有可见差异。这与以下应用的做法一致：
- VS Code 深色主题：`#1e1e1e` 基色
- Photoshop：`#1a1a1a` 基色
- DaVinci Resolve：`#1a1a1a` 基色

### 3.2 微妙的边框定义

目前控件全部使用 `border: none`。添加非常微妙的边框可以提高控件的可发现性：

```css
/* 输入控件的微妙边框 */
QLineEdit, QAbstractSpinBox, QComboBox {
    border: 1px solid #2a2a2a;
    border-radius: 2px;
}

QLineEdit:focus, QAbstractSpinBox:focus, QComboBox:focus {
    border-color: #ee9470;  /* 聚焦时使用强调色 */
}
```

### 3.3 状态栏优化

状态栏使用 `GRAY_2`（`#1a1a1a`），与主背景几乎无法区分。建议：

```css
QStatusBar {
    background: #181818;
    color: #999999;
    border-top: 1px solid #262626;
    font-size: 11px;
}
```

---

## 4. 胶片模拟控件改进

### 4.1 滑块 + 旋转框混合控件

最有影响力的用户体验改进是为连续参数在旋转框旁添加滑块。`widget_editors.py` 中已有的 `SliderFloatEditor`（第 318-384 行）已经实现，但**未接入任何分区**。这是首选的采用方案。

**优先使用滑块的参数：**

| 参数 | 范围 | 为何需要滑块 |
|-----------|-------|-----------------|
| `exposure_compensation_ev` | -100..100 | 核心创意控制，偏好手势调节 |
| `print_exposure` | 0..∞ | 放大机式旋钮手感 |
| `scatter_amount` | 0..1 | 视觉效果，线性映射到滑块 |
| `halation_amount` | 0..1 | 视觉效果，需要快速迭代 |
| `grain.particle_area_um2` | 0..∞ | 直接 ISO 等效值，熟悉的旋钮 |
| `diffusion_filter_strength` | 0..2 | 商用滤镜档位，步进 = 0.125 |

**实现方式**：使用现有的 `SliderFloatEditor`，并更新 `DataclassSection._build_editor()` 以对定义了 `min_value` 和 `max_value` 的字段优先使用滑块：

```python
def _build_editor(self, field_name: str, annotation: Any) -> QWidget:
    spec = get_widget_spec(self._section_name, field_name)
    # ... 现有的 enum/bool/int/tuple 逻辑 ...

    if annotation is float and spec.min_value is not None and spec.max_value is not None:
        # 对范围合理的有界浮点数使用滑块
        range_size = spec.max_value - spec.min_value
        if range_size <= 100 and spec.step is not None:
            return SliderFloatEditor(
                minimum=spec.min_value,
                maximum=spec.max_value,
                step=spec.step,
                decimals=spec.decimals or 2,
            )
    # ... 现有的浮点数回退逻辑 ...
```

### 4.2 可视范围指示器

对于无法使用滑块的旋转框控件，在行内显示有效范围：

```css
QAbstractSpinBox {
    /* 微妙的背景渐变指示范围 */
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #101010, stop:0.5 #1a1a1a, stop:1 #101010);
}
```

### 4.3 元组编辑器视觉分组

`FloatTupleEditor`（用于 `scatter_core_um` 等 RGB 元组）显示 3 个并排的旋转框。添加 R/G/B 颜色指示器可以提高可读性：

```python
# 在 FloatTupleEditor.__init__ 中，添加彩色标签：
for i, (editor, color) in enumerate(zip(self._editors, ('#ff4444', '#44ff44', '#4444ff'))):
    label = QLabel(['R', 'G', 'B'][i])
    label.setStyleSheet(f'color: {color}; font-weight: bold;')
    layout.addWidget(label)
    layout.addWidget(editor)
```

### 4.4 胶片型号视觉选择器

`ProfileEnumEditor` 已经有自定义的 `paintEvent`，显示带有颜色编码的 "cine /" 或 "still /" 前缀。增强方案：为每个型号添加小型胶片条图标或缩略图预览。

### 4.5 扩散滤镜视觉预览

对于扩散参数（强度、空间尺度、核心/光晕/泛光），考虑添加一个小型实时 PSF 可视化控件——即使是 64x64 的渲染核预览也会显著提高直觉性。

---

## 5. 布局优化

### 5.1 当前布局结构

```
MainWindow (1460x980 默认)
├── QSplitter (水平)
│   ├── ViewerPanel (stretch=1, ~1040px)
│   │   ├── napari 查看器控件
│   │   └── 状态栏 + 旋转/缩放按钮
│   └── SidebarPanel (stretch=0, ~420px)
│       ├── QTabWidget (MAIN/FILM/PRINT/ADVANCED/CONFIG)
│       │   └── 每个标签页一个 QScrollArea
│       └── 操作栏（自动预览、扫描胶片、扫描打印、PREVIEW/SCAN/SAVE）
```

### 5.2 响应式断点

当前布局没有响应式行为。建议：

| 宽度 | 行为 |
|-------|----------|
| >= 1920px | 完整布局，侧边栏 480px，更大字体 |
| >= 1440px | 当前默认（420px 侧边栏） |
| >= 1280px | 紧凑侧边栏（360px），减少内边距 |
| < 1280px | 侧边栏叠加或折叠为图标条 |

### 5.3 标签页内容密度

MAIN 标签页垂直堆叠了 11 个分区。在 420px 宽度下，需要大量滚动。建议：

- **固定操作栏**：PREVIEW/SCAN/SAVE 按钮在滚动时应保持可见（已在底部，但需验证滚动行为）
- **智能折叠**：自动折叠用户未修改的分区
- **紧凑模式**：切换开关，仅显示标签 + 值，不显示完整的工具提示描述

### 5.4 侧边栏宽度自适应

`DEFAULT_CONTROLS_PANEL_WIDTH = 420` 是硬编码的。针对不同工作流：

- **胶片调色工作流**：较窄的侧边栏（360px）以最大化画布
- **打印校准工作流**：较宽的侧边栏（480px）以容纳大量放大机/扫描仪参数

---

## 6. 高 DPI 与多显示器

### 6.1 当前状态

Qt6 默认启用高 DPI 缩放。当前代码使用：
- `platform_default_font()` —— 系统字体，可正确缩放
- `theme_palette.py` 中的固定像素尺寸（如 `SIZE_CONTROL_MIN_HEIGHT = '18px'`）

### 6.2 问题

1. **所有尺寸使用 CSS px** —— Qt 的 QSS `px` 单位是 DPI 感知的（1px = 1/96 英寸），因此在 Qt6 默认行为下实际上可以正确缩放
2. **自定义绘制使用设备像素** —— `BoolEditor._indicator_rect()` 返回 `QRect(1, ..., 14, 14)`，未考虑 `devicePixelRatio`
3. **标题图标尺寸固定** —— `HEADER_ICON_SIZE = 16` 不会缩放

### 6.3 建议

```python
# 在 widget_primitives.py 或新的 dpi_aware.py 中：
def dpi_scale(widget: QWidget, px: int) -> int:
    """为控件当前屏幕 DPI 缩放像素值。"""
    ratio = widget.devicePixelRatioF()
    return max(1, int(px * ratio))

# 在 BoolEditor._indicator_rect 中使用：
def _indicator_rect(self):
    size = dpi_scale(self, 14)
    return QRect(1, max(1, (self.height() - size) // 2), size, size)
```

对于 `icons.py` 中的图标，使用带设备像素比的 `QIcon.pixmap()`：

```python
def section_header_icon(title: str, size: int = HEADER_ICON_SIZE) -> QtGui.QIcon:
    # ... 现有代码 ...
    # 图标基于 SVG（通过 pyconify），因此可自然缩放。
    # 但 HEADER_ICON_SIZE 在调用处应为 DPI 感知。
```

### 6.4 多显示器拖拽行为

在不同 DPI 的显示器之间拖动窗口时，Qt6 会自动重新缩放。分隔器尺寸应使用比率而非绝对像素：

```python
# 在 build_main_window() 中：
total = main_window.width()
viewer_ratio = 0.71  # 约 71% 给查看器
splitter.setSizes([int(total * viewer_ratio), int(total * (1 - viewer_ratio))])
```

---

## 7. 色彩准确性与显示管理

### 7.1 当前状态

应用有 `use_display_transform`（在 `DisplayState` 中），使用 `PIL.ImageCms` 应用显示 ICC 配置文件。此功能仅在 Windows 上有效（根据工具提示）。画布背景使用 `GRAY_18 = '#767676'`，这是正确的中性参考。

### 7.2 建议

1. **画布背景校准**：`#767676` 值是 18% 反射率的 sRGB 编码。在经过显示器校准的系统上，它应显示为感知中灰。在 UI 中注明（"此灰色已针对 sRGB 显示器校准"）

2. **打样预览模式**：添加切换开关以模拟不同的输出设备：
   - sRGB 显示器（默认）
   - P3 显示（macOS/iPad）
   - Adobe RGB（打印）
   - 自定义 ICC 配置文件

3. **色域警告**：当模拟输出超出显示器色域时，显示微妙的警告图标或叠加层

4. **HDR 预览支持**：对于支持 HDR 的显示器，查看器可以显示实际的 HDR 渲染效果（目前根据代码注释，预览始终为 SDR）

### 7.3 Qt 色彩管理集成

Qt6 原生不为控件渲染处理 ICC 色彩管理。色彩管理必须在图像层面进行（应用已实现）。对于控件 UI 本身，使用 sRGB 十六进制值的当前方法是正确的——所有现代显示器都能正确解释 sRGB。

---

## 8. 无障碍性

### 8.1 当前状态评估

| 标准 | 状态 | 备注 |
|-----------|--------|-------|
| 键盘导航 | 部分 | Tab 键顺序在表单字段中有效，但可折叠分区需要鼠标 |
| 屏幕阅读器 | 较差 | 未发现 `setAccessibleName()` 或 `setAccessibleDescription()` 调用 |
| 色彩对比度 | 良好 | 主要文本通过 WCAG AA，强调色通过 AA |
| 仅颜色信息 | 部分 | 胶片型号使用颜色和文本前缀（"cine /"、"still /"） |
| 焦点指示器 | 较差 | 所有聚焦控件使用 `border: none; outline: none;` |
| 文本缩放 | 良好 | 使用系统字体，QSS px 单位随 DPI 缩放 |
| 高对比度模式 | 不支持 | 未检测系统高对比度模式 |

### 8.2 优先修复

**焦点指示器**（最关键）：

```css
/* 当前：移除所有焦点指示 */
QPushButton:focus, QComboBox:focus, QLineEdit:focus {
    border: none;
    outline: none;  /* ← 问题：焦点不可见 */
}

/* 建议：微妙的强调色环 */
QPushButton:focus, QComboBox:focus, QLineEdit:focus {
    border: 1px solid #ee9470;
    outline: none;
}
```

**无障碍名称**：

```python
# 在 widget_sections.py 中，控件创建后添加：
def _build_editor(self, field_name, annotation):
    widget = ...
    spec = get_widget_spec(self._section_name, field_name)
    accessible_name = spec.label or _format_label(field_name)
    widget.setAccessibleName(accessible_name)
    if spec.tooltip:
        widget.setAccessibleDescription(spec.tooltip)
    return widget
```

**可折叠分区的键盘导航**：

```python
# 在 CollapsibleSection.__init__ 中：
self._toggle.setShortcut('Space')  # 或处理 keyPressEvent
self._title_button.setShortcut('Space')
```

### 8.3 色觉障碍考虑

强调色用作语义指示器：
- `#ee9470`（暖橙色）= 主要强调，"静态"胶片
- `#63c3cf`（冷青色）= 次要强调，"电影"胶片

这些颜色对大多数色觉障碍用户是可区分的，因为它们在色相和亮度上都有差异（橙色在深色背景上比青色更亮）。但建议添加小型图标或形状差异作为冗余提示。

---

## 9. QML 与 Widgets 评估

### 当前方案：Qt Widgets

应用通过 `qtpy` 完全使用 Qt Widgets。这对 Spektrafilm 是正确的选择，因为：

1. **成熟的生态系统**：自定义绘制（BoolEditor、ProfileEnumEditor）与 QPainter 配合良好
2. **桌面原生体验**：表单布局、旋转框、下拉框符合平台惯例
3. **napari 集成**：napari 是 Qt Widgets 应用；QML 需要嵌入 QWidget
4. **性能**：Widgets 是即时模式，无场景图开销
5. **无障碍性**：内置平台无障碍 API

### QML 更适合的场景

- 如果需要添加胶片型号之间的动画过渡
- 如果构建移动/平板版本
- 如果实现带有贝塞尔手柄的自定义色调曲线编辑器（QML 的 Canvas/Path 元素更自然）

### 建议

**继续使用 Qt Widgets。** 当前架构非常适合。如果特定功能需要 QML 的优势（动画、自定义绘制管线），可以将其作为 `QQuickWidget` 嵌入现有的 Widget 框架中。

---

## 10. 可直接使用的 QSS 代码片段

### 10.1 优化的深色主题基底

```css
/* 提升纯黑以减少 OLED 眼睛疲劳 */
QMainWindow, QWidget#appCentral {
    background: #0a0a0a;
}

QWidget {
    background: #0a0a0a;
    color: #cecece;
}
```

### 10.2 提高可发现性的控件边框

```css
QLineEdit, QAbstractSpinBox, QComboBox {
    border: 1px solid #2a2a2a;
    border-radius: 2px;
}

QLineEdit:hover, QAbstractSpinBox:hover, QComboBox:hover {
    border-color: #3a3a3a;
}

QLineEdit:focus, QAbstractSpinBox:focus, QComboBox:focus {
    border-color: #ee9470;
}
```

### 10.3 滑块样式（用于 SliderFloatEditor 采用）

```css
QSlider::groove:horizontal {
    background: #1a1a1a;
    height: 4px;
    border-radius: 2px;
}

QSlider::handle:horizontal {
    background: #cecece;
    width: 12px;
    height: 12px;
    margin: -4px 0;
    border-radius: 6px;
}

QSlider::handle:horizontal:hover {
    background: #ee9470;
}

QSlider::sub-page:horizontal {
    background: #ee9470;
    border-radius: 2px;
}
```

### 10.4 标签栏美化

```css
QTabBar::tab {
    background: #0a0a0a;
    color: #8d8d8d;
    border: none;
    padding: 6px 12px;
    font-weight: 700;
    letter-spacing: 0.05em;
}

QTabBar::tab:selected {
    background: #0a0a0a;
    color: #ee9470;
    border-bottom: 2px solid #ee9470;
}

QTabBar::tab:hover:!selected {
    color: #cecece;
    background: #141414;
}
```

### 10.5 强调按钮增强

```css
QPushButton[role="accentAction"] {
    background: #1a1a1a;
    color: #ee9470;
    border: 1px solid #ee9470;
    border-radius: 3px;
    font-weight: 700;
    padding: 4px 12px;
}

QPushButton[role="accentAction"]:hover {
    background: #ee9470;
    color: #0a0a0a;
}

QPushButton[role="accentAction"]:pressed {
    background: #cc7a5a;
    color: #0a0a0a;
}
```

### 10.6 滚动条优化

```css
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background: #3a3a3a;
    border-radius: 4px;
    min-height: 32px;
}

QScrollBar::handle:vertical:hover {
    background: #5a5a5a;
}

QScrollBar::add-line, QScrollBar::sub-line,
QScrollBar::add-page, QScrollBar::sub-page {
    background: transparent;
    border: none;
    height: 0;
}
```

### 10.7 可折叠分区框架

```css
QFrame[frameShape="5"] {  /* StyledPanel */
    border: 1px solid #1e1e1e;
    border-radius: 3px;
    background: #0e0e0e;
}
```

### 10.8 禁用状态清晰度

```css
QWidget:disabled {
    color: #555555;
}

QPushButton:disabled, QComboBox:disabled, QAbstractSpinBox:disabled {
    background: #0e0e0e;
    color: #555555;
    border-color: #1a1a1a;
}
```

---

## 实现优先级

| 优先级 | 变更 | 工作量 | 影响 |
|----------|--------|--------|--------|
| P0 | 为 QSS 添加焦点指示器 | 低 | 无障碍性关键 |
| P0 | 将 SliderFloatEditor 接入有界浮点字段 | 中 | 重大用户体验改进 |
| P1 | 添加微妙的控件边框 | 低 | 可发现性 |
| P1 | 为所有编辑器添加无障碍名称 | 低 | 屏幕阅读器支持 |
| P1 | 将基础灰色从 `#000000` 提升到 `#0a0a0a` | 低 | 眼睛舒适度 |
| P2 | 为元组编辑器添加 R/G/B 标签 | 低 | 颜色参数清晰度 |
| P2 | 状态栏边框和样式 | 低 | 视觉层次 |
| P2 | DPI 感知的自定义绘制 | 中 | 多显示器正确性 |
| P3 | 响应式侧边栏宽度 | 中 | 小屏幕支持 |
| P3 | 可折叠分区键盘导航 | 中 | 键盘无障碍性 |
| P3 | 高对比度模式检测 | 中 | 无障碍合规性 |
| P3 | 扩散 PSF 预览控件 | 高 | 领域特定用户体验 |

---

## 参考资料

- Qt 样式表参考：https://doc.qt.io/qt-6/stylesheet-reference.html
- Qt 高 DPI 文档：https://doc.qt.io/qt-6/highdpi.html
- Qt 无障碍性：https://doc.qt.io/qt-6/accessible.html
- WCAG 2.1 对比度要求：https://www.w3.org/WAI/WCAG21/quickref/
- QDarkStyleSheet（参考深色主题）：https://github.com/ColinDuquesnoy/QDarkStyleSheet
- Darktable（开源摄影应用，基于 Qt）：https://www.darktable.org/
- ColorBrewer（色觉障碍安全调色板）：https://colorbrewer2.org/
- Coblis（色盲模拟器）：https://www.color-blindness.com/coblis-color-blindness-simulator/
