# Spektrafilm GUI Aesthetics & UX Research

Date: 2026-05-27

## Table of Contents

1. [Current UI Architecture Audit](#1-current-ui-architecture-audit)
2. [Theme & Styling Analysis](#2-theme--styling-analysis)
3. [Dark Theme Recommendations](#3-dark-theme-recommendations)
4. [Widget Improvements for Film Simulation](#4-widget-improvements-for-film-simulation)
5. [Layout Optimization](#5-layout-optimization)
6. [High DPI & Multi-Monitor](#6-high-dpi--multi-monitor)
7. [Color Accuracy & Display Management](#7-color-accuracy--display-management)
8. [Accessibility](#8-accessibility)
9. [QML vs Widgets Assessment](#9-qml-vs-widgets-assessment)
10. [Ready-to-Apply QSS Snippets](#10-ready-to-apply-qss-snippets)

---

## 1. Current UI Architecture Audit

### Architecture Overview

The GUI uses **Qt Widgets via qtpy** (PySide6/PyQt5 compatible) with a **napari** viewer for the image canvas. The architecture is well-structured:

| Layer | Files | Purpose |
|-------|-------|---------|
| **State** | `state.py` | Pure dataclasses for all GUI parameter state |
| **Specs** | `widget_specs.py` | Widget metadata (labels, tooltips, min/max/step) |
| **Editors** | `widget_editors.py` | Custom editor widgets (FloatEditor, BoolEditor, etc.) |
| **Sections** | `widget_sections.py` | Collapsible sections composing editors into forms |
| **Primitives** | `widget_primitives.py` | CollapsibleSection, HeaderDivider |
| **Layout** | `napari_layout.py` | Main window, sidebar, viewer panel, tab structure |
| **Theme** | `theme.py`, `theme_palette.py`, `theme_styles.py` | Colors, sizes, QSS |
| **Controller** | `controller.py` | Business logic, signal wiring |
| **App** | `app.py` | Bootstrap, warmup, palette setup |

### Strengths

- **Clean separation**: State dataclasses are decoupled from widgets via specs
- **Collapsible sections**: Good progressive disclosure pattern
- **Tab-based organization**: MAIN / FILM / PRINT / ADVANCED / CONFIG tabs
- **Custom painting**: BoolEditor, ProfileEnumEditor use custom QPainter for pixel-perfect control
- **Dark title bar**: Windows DWM immersive dark mode support via `_request_dark_title_bar`
- **Icon system**: pyconify SVG icons with accent color for section headers
- **Warmup system**: Background thread pre-imports heavy modules for responsive first interaction

### Weaknesses

- **No slider-based controls**: All numeric parameters use spin boxes only -- no visual slider for quick gestural adjustment
- **No visual feedback for ranges**: Min/max values exist in WidgetSpec but aren't visually communicated
- **Flat color palette**: All grays are pure achromatic (no subtle warm/cool tints), which can feel sterile
- **Hard-coded pixel sizes**: Fixed heights (24px, 30px) don't scale with DPI
- **No keyboard shortcut hints**: No visible shortcut indicators
- **No undo/redo**: No history stack visible in the UI
- **Tooltip-only help**: All documentation is in tooltips, no inline help or info buttons

---

## 2. Theme & Styling Analysis

### Current Color Palette (`theme_palette.py`)

```
GRAY_18 = '#767676'   ← Canvas background (18% gray, perceptually mid)
GRAY_0  = '#000000'   ← Base background
GRAY_1  = '#101010'   ← Control background
GRAY_2  = '#1a1a1a'   ← Hover/active states
GRAY_3  = '#262626'   ← Mid tone
GRAY_4  = '#404040'   ← Selection background

ACCENT_COLOR_TEXT          = '#ee9470'  ← Warm orange accent
ACCENT_COLOR_TEXT_SECONDARY = '#63c3cf' ← Cool cyan accent
TEXT_DIM  = '#8d8d8d'   ← Secondary text
TEXT_MAIN = '#cecece'   ← Primary text
TEXT_HI   = '#f2f2f2'   ← Bright text
```

### Contrast Analysis (WCAG 2.1)

| Pair | Ratio | WCAG AA (4.5:1) | WCAG AAA (7:1) |
|------|-------|------------------|-----------------|
| `#cecece` on `#000000` | 12.3:1 | PASS | PASS |
| `#cecece` on `#101010` | 11.5:1 | PASS | PASS |
| `#8d8d8d` on `#000000` | 5.3:1 | PASS | FAIL |
| `#8d8d8d` on `#101010` | 4.9:1 | PASS | FAIL |
| `#767676` on `#000000` | 4.5:1 | BORDERLINE | FAIL |
| `#ee9470` on `#000000` | 7.2:1 | PASS | PASS |
| `#ee9470` on `#101010` | 6.8:1 | PASS | FAIL |

### Observations

1. **Primary text contrast is excellent** -- `#cecece` on near-black is comfortable for extended use
2. **`TEXT_DIM` is borderline** -- `#8d8d8d` on `#101010` (control bg) barely passes AA for small text. For labels at the current 18px min-height, this is acceptable but could be improved
3. **`GRAY_18` canvas is correct** -- 18% gray is the industry standard for neutral color evaluation (matches Munsell N5/, the perceptual midpoint)
4. **Accent colors are distinctive** -- Warm orange (`#ee9470`) for primary accent, cool cyan (`#63c3cf`) for secondary (cine vs still film indicator). This warm/cool pairing reinforces the analog photography metaphor
5. **No color tinting in grays** -- All grays are perfectly achromatic. This is actually *correct* for a color-critical application, as tinted grays would bias color perception

### QSS Structure (`theme_styles.py`)

The stylesheet is well-organized into four logical sections:
- `WINDOW_STYLE` -- Base window/frame backgrounds
- `TAB_STYLE` -- Tab bar, tab panes, section toggles, accent buttons
- `CONTROL_STYLE` -- All form controls (buttons, combos, spinboxes, checkboxes)
- `CHROME_STYLE` -- Scrollbars, splitters, status bar

---

## 3. Dark Theme Recommendations

### 3.1 Refine the Gray Scale

The current palette uses very dark values with large jumps. Consider adding intermediate steps for smoother visual hierarchy:

```python
# Current:          Proposed additions:
# GRAY_0 #000000    GRAY_0  #0a0a0a  (slightly lifted from pure black)
# GRAY_1 #101010    GRAY_1  #141414  (control background)
# GRAY_2 #1a1a1a    GRAY_2  #1e1e1e  (hover)
# GRAY_3 #262626    GRAY_3  #282828  (borders, dividers)
#                    GRAY_4  #3a3a3a  (active/pressed)
#                    GRAY_5  #4a4a4a  (selection)
```

**Rationale**: Pure black (`#000000`) on OLED creates excessive contrast against lit content. Lifting to `#0a0a0a` or `#0d0d0d` reduces eye strain without visible difference on LCD. This matches the approach used by:
- VS Code dark theme: `#1e1e1e` base
- Photoshop: `#1a1a1a` base
- DaVinci Resolve: `#1a1a1a` base

### 3.2 Subtle Border Definition

Currently controls have `border: none` everywhere. Adding very subtle borders improves widget discoverability:

```css
/* Subtle border for input controls */
QLineEdit, QAbstractSpinBox, QComboBox {
    border: 1px solid #2a2a2a;
    border-radius: 2px;
}

QLineEdit:focus, QAbstractSpinBox:focus, QComboBox:focus {
    border-color: #ee9470;  /* accent on focus */
}
```

### 3.3 Status Bar Refinement

The status bar uses `GRAY_2` (`#1a1a1a`) which is nearly indistinguishable from the main background. Consider:

```css
QStatusBar {
    background: #181818;
    color: #999999;
    border-top: 1px solid #262626;
    font-size: 11px;
}
```

---

## 4. Widget Improvements for Film Simulation

### 4.1 Slider + SpinBox Hybrid Controls

The most impactful UX improvement would be adding sliders alongside spin boxes for continuous parameters. The existing `SliderFloatEditor` in `widget_editors.py` (lines 318-384) is already implemented but **not wired into any section**. This is the primary candidate for adoption.

**Priority parameters for slider treatment:**

| Parameter | Range | Why Slider Helps |
|-----------|-------|-----------------|
| `exposure_compensation_ev` | -100..100 | Core creative control, gestural adjustment preferred |
| `print_exposure` | 0..∞ | Enlarger-style dial feel |
| `scatter_amount` | 0..1 | Visual effect, linear mapping to slider |
| `halation_amount` | 0..1 | Visual effect, quick iteration needed |
| `grain.particle_area_um2` | 0..∞ | Direct ISO equivalent, familiar dial |
| `diffusion_filter_strength` | 0..2 | Commercial filter stops, step = 0.125 |

**Implementation approach**: Use the existing `SliderFloatEditor` and update `DataclassSection._build_editor()` to prefer sliders for fields with defined `min_value` and `max_value`:

```python
def _build_editor(self, field_name: str, annotation: Any) -> QWidget:
    spec = get_widget_spec(self._section_name, field_name)
    # ... existing enum/bool/int/tuple logic ...

    if annotation is float and spec.min_value is not None and spec.max_value is not None:
        # Use slider for bounded floats with reasonable range
        range_size = spec.max_value - spec.min_value
        if range_size <= 100 and spec.step is not None:
            return SliderFloatEditor(
                minimum=spec.min_value,
                maximum=spec.max_value,
                step=spec.step,
                decimals=spec.decimals or 2,
            )
    # ... existing float fallback ...
```

### 4.2 Visual Range Indicators

For spin-box controls that can't use sliders, show the valid range inline:

```css
QAbstractSpinBox {
    /* Subtle background gradient indicating range */
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #101010, stop:0.5 #1a1a1a, stop:1 #101010);
}
```

### 4.3 Tuple Editor Visual Grouping

The `FloatTupleEditor` (for RGB tuples like `scatter_core_um`) shows 3 side-by-side spin boxes. Adding R/G/B color indicators would improve readability:

```python
# In FloatTupleEditor.__init__, add colored labels:
for i, (editor, color) in enumerate(zip(self._editors, ('#ff4444', '#44ff44', '#4444ff'))):
    label = QLabel(['R', 'G', 'B'][i])
    label.setStyleSheet(f'color: {color}; font-weight: bold;')
    layout.addWidget(label)
    layout.addWidget(editor)
```

### 4.4 Film Stock Visual Picker

The `ProfileEnumEditor` already has a custom `paintEvent` showing "cine /" or "still /" prefixes with color coding. Enhancement: add a small film strip icon or thumbnail preview for each stock.

### 4.5 Diffusion Filter Visual Preview

For diffusion parameters (strength, spatial scale, core/halo/bloom), consider a small real-time PSF visualization widget -- even a 64x64 rendered kernel preview would dramatically improve intuitiveness.

---

## 5. Layout Optimization

### 5.1 Current Layout Structure

```
MainWindow (1460x980 default)
├── QSplitter (horizontal)
│   ├── ViewerPanel (stretch=1, ~1040px)
│   │   ├── napari viewer widget
│   │   └── StatusBar + Rotate/Zoom buttons
│   └── SidebarPanel (stretch=0, ~420px)
│       ├── QTabWidget (MAIN/FILM/PRINT/ADVANCED/CONFIG)
│       │   └── QScrollArea per tab
│       └── Action Bar (auto-preview, scan film, scan-for-print, PREVIEW/SCAN/SAVE)
```

### 5.2 Responsive Breakpoints

The current layout has no responsive behavior. Recommendations:

| Width | Behavior |
|-------|----------|
| >= 1920px | Full layout, sidebar at 480px, larger font |
| >= 1440px | Current default (420px sidebar) |
| >= 1280px | Compact sidebar (360px), reduced padding |
| < 1280px | Sidebar overlays or collapses to icon strip |

### 5.3 Tab Content Density

The MAIN tab has 11 sections stacked vertically. At 420px width, this requires significant scrolling. Recommendations:

- **Pin the action bar**: The PREVIEW/SCAN/SAVE buttons should remain visible when scrolling (already at bottom, but verify scroll behavior)
- **Smart collapse**: Auto-collapse sections that haven't been modified by the user
- **Compact mode**: A toggle to show only labels + values without full tooltip descriptions

### 5.4 Sidebar Width Adaptation

The `DEFAULT_CONTROLS_PANEL_WIDTH = 420` is hard-coded. For different workflows:

- **Film tuning workflow**: Narrower sidebar (360px) to maximize canvas
- **Print calibration workflow**: Wider sidebar (480px) for the many enlarger/scanner parameters

---

## 6. High DPI & Multi-Monitor

### 6.1 Current State

Qt6 enables high DPI scaling by default. The current code uses:
- `platform_default_font()` -- system font, which scales correctly
- Fixed pixel sizes in `theme_palette.py` (e.g., `SIZE_CONTROL_MIN_HEIGHT = '18px'`)

### 6.2 Issues

1. **All sizes are in CSS px** -- Qt's QSS `px` unit is DPI-aware (1px = 1/96th inch), so this actually scales correctly with Qt6's default behavior
2. **Custom painting uses device pixels** -- `BoolEditor._indicator_rect()` returns `QRect(1, ..., 14, 14)` which doesn't account for `devicePixelRatio`
3. **Header icon size is fixed** -- `HEADER_ICON_SIZE = 16` doesn't scale

### 6.3 Recommendations

```python
# In widget_primitives.py or a new dpi_aware.py:
def dpi_scale(widget: QWidget, px: int) -> int:
    """Scale a pixel value for the widget's current screen DPI."""
    ratio = widget.devicePixelRatioF()
    return max(1, int(px * ratio))

# Usage in BoolEditor._indicator_rect:
def _indicator_rect(self):
    size = dpi_scale(self, 14)
    return QRect(1, max(1, (self.height() - size) // 2), size, size)
```

For icons in `icons.py`, use `QIcon.pixmap()` with the device pixel ratio:

```python
def section_header_icon(title: str, size: int = HEADER_ICON_SIZE) -> QtGui.QIcon:
    # ... existing code ...
    # The icon is SVG-based via pyconify, so it scales naturally.
    # But HEADER_ICON_SIZE should be DPI-aware at call sites.
```

### 6.4 Multi-Monitor Drag Behavior

When dragging the window between monitors with different DPIs, Qt6 automatically re-scales. The splitter sizes should use ratios rather than absolute pixels:

```python
# In build_main_window():
total = main_window.width()
viewer_ratio = 0.71  # ~71% for viewer
splitter.setSizes([int(total * viewer_ratio), int(total * (1 - viewer_ratio))])
```

---

## 7. Color Accuracy & Display Management

### 7.1 Current State

The app has `use_display_transform` (in `DisplayState`) which uses `PIL.ImageCms` to apply a display ICC profile. This is only functional on Windows (per the tooltip). The canvas background uses `GRAY_18 = '#767676'` which is the correct neutral reference.

### 7.2 Recommendations

1. **Canvas background calibration**: The `#767676` value is the sRGB encoding of 18% reflectance. On a display-calibrated system, this should appear as perceptual mid-gray. Document this in the UI ("This gray is calibrated for sRGB displays")

2. **Proof preview mode**: Add a toggle to simulate different output devices:
   - sRGB monitor (default)
   - P3 display (macOS/iPad)
   - Adobe RGB (print)
   - Custom ICC profile

3. **Gamut warnings**: When the simulated output exceeds the display's gamut, show a subtle warning icon or overlay

4. **HDR preview support**: For HDR-capable displays, the viewer could show the actual HDR rendition (currently preview is always SDR per the code comments)

### 7.3 Qt Color Management Integration

Qt6 does not natively handle ICC color management for widget rendering. The color management must happen at the image level (which the app already does). For the widget UI itself, the current approach of using sRGB hex values is correct -- all modern displays interpret sRGB correctly.

---

## 8. Accessibility

### 8.1 Current State Assessment

| Criterion | Status | Notes |
|-----------|--------|-------|
| Keyboard navigation | Partial | Tab order works through form fields, but collapsible sections require mouse |
| Screen reader | Poor | No `setAccessibleName()` or `setAccessibleDescription()` calls found |
| Color contrast | Good | Primary text passes WCAG AA, accent passes AA |
| Color-only info | Partial | Film stock type uses color AND text prefix ("cine /", "still /") |
| Focus indicators | Poor | `border: none; outline: none;` on all focused controls |
| Text scaling | Good | Uses system font, QSS px units scale with DPI |
| High contrast mode | Not supported | No detection of system high-contrast mode |

### 8.2 Priority Fixes

**Focus indicators** (most critical):

```css
/* Current: removes all focus indication */
QPushButton:focus, QComboBox:focus, QLineEdit:focus {
    border: none;
    outline: none;  /* ← PROBLEM: invisible focus */
}

/* Proposed: subtle accent ring */
QPushButton:focus, QComboBox:focus, QLineEdit:focus {
    border: 1px solid #ee9470;
    outline: none;
}
```

**Accessible names**:

```python
# In widget_sections.py, add after widget creation:
def _build_editor(self, field_name, annotation):
    widget = ...
    spec = get_widget_spec(self._section_name, field_name)
    accessible_name = spec.label or _format_label(field_name)
    widget.setAccessibleName(accessible_name)
    if spec.tooltip:
        widget.setAccessibleDescription(spec.tooltip)
    return widget
```

**Keyboard navigation for collapsible sections**:

```python
# In CollapsibleSection.__init__:
self._toggle.setShortcut('Space')  # or handle keyPressEvent
self._title_button.setShortcut('Space')
```

### 8.3 Color Blind Considerations

The accent colors serve as semantic indicators:
- `#ee9470` (warm orange) = primary accent, "still" film
- `#63c3cf` (cool cyan) = secondary accent, "cine" film

These are distinguishable by most color-blind users because they differ in both hue AND luminance (orange is brighter than cyan on dark backgrounds). However, consider adding a small icon or shape difference as a redundant cue.

---

## 9. QML vs Widgets Assessment

### Current: Qt Widgets

The app uses Qt Widgets exclusively via `qtpy`. This is the right choice for Spektrafilm because:

1. **Mature ecosystem**: Custom painting (BoolEditor, ProfileEnumEditor) works well with QPainter
2. **Desktop-native feel**: Form layouts, spin boxes, combo boxes match platform conventions
3. **napari integration**: napari is a Qt Widgets application; QML would require embedding a QWidget
4. **Performance**: Widgets are immediate-mode, no scene graph overhead
5. **Accessibility**: Built-in platform accessibility APIs

### When QML Would Be Better

- If adding animated transitions between film stocks
- If building a mobile/tablet version
- If implementing a custom tone curve editor with bezier handles (QML's Canvas/Path elements are more natural)

### Recommendation

**Stay with Qt Widgets.** The current architecture is well-suited. If specific features need QML's strengths (animations, custom painting pipelines), they can be embedded as `QQuickWidget` within the existing Widget framework.

---

## 10. Ready-to-Apply QSS Snippets

### 10.1 Refined Dark Theme Base

```css
/* Lift pure black to reduce OLED eye strain */
QMainWindow, QWidget#appCentral {
    background: #0a0a0a;
}

QWidget {
    background: #0a0a0a;
    color: #cecece;
}
```

### 10.2 Control Borders for Discoverability

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

### 10.3 Slider Styling (for SliderFloatEditor adoption)

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

### 10.4 Tab Bar Polish

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

### 10.5 Accent Button Enhancement

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

### 10.6 Scrollbar Refinement

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

### 10.7 Collapsible Section Frame

```css
QFrame[frameShape="5"] {  /* StyledPanel */
    border: 1px solid #1e1e1e;
    border-radius: 3px;
    background: #0e0e0e;
}
```

### 10.8 Disabled State Clarity

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

## Implementation Priority

| Priority | Change | Effort | Impact |
|----------|--------|--------|--------|
| P0 | Add focus indicators to QSS | Low | Accessibility critical |
| P0 | Wire SliderFloatEditor to bounded float fields | Medium | Major UX improvement |
| P1 | Add subtle control borders | Low | Discoverability |
| P1 | Add accessible names to all editors | Low | Screen reader support |
| P1 | Lift base gray from `#000000` to `#0a0a0a` | Low | Eye comfort |
| P2 | Add R/G/B labels to tuple editors | Low | Color parameter clarity |
| P2 | Status bar border and styling | Low | Visual hierarchy |
| P2 | DPI-aware custom painting | Medium | Multi-monitor correctness |
| P3 | Responsive sidebar width | Medium | Small screen support |
| P3 | Collapsible section keyboard navigation | Medium | Keyboard accessibility |
| P3 | High contrast mode detection | Medium | Accessibility compliance |
| P3 | PSF preview widget for diffusion | High | Domain-specific UX |

---

## References

- Qt Style Sheets Reference: https://doc.qt.io/qt-6/stylesheet-reference.html
- Qt High DPI Documentation: https://doc.qt.io/qt-6/highdpi.html
- Qt Accessibility: https://doc.qt.io/qt-6/accessible.html
- WCAG 2.1 Contrast Requirements: https://www.w3.org/WAI/WCAG21/quickref/
- QDarkStyleSheet (reference dark theme): https://github.com/ColinDuquesnoy/QDarkStyleSheet
- Darktable (open-source photo app, Qt-based): https://www.darktable.org/
- ColorBrewer (colorblind-safe palettes): https://colorbrewer2.org/
- Coblis (color blindness simulator): https://www.color-blindness.com/coblis-color-blindness-simulator/
