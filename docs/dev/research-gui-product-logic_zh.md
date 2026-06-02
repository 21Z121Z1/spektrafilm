> 这是英文原文的中文翻译。权威版本请参考英文原文。

# Spektrafilm GUI — 产品逻辑审查与用户体验流程审计

**日期：** 2026-05-27
**范围：** 对 `src/spektrafilm_gui/` 中所有 GUI 源文件的只读分析
**目标：** 绘制用户流程图、识别痛点、与专业工具对比、提出改进建议

---

## 1. 架构概述

GUI 基于 **napari**（科学图像查看器）构建，配有自定义 Qt 侧边栏。关键层次结构：

```
app.py                          Entry point — creates viewer, widgets, controller
  ├── state.py                  11 dataclass sections (GuiState)
  ├── widget_specs.py           Metadata: labels, tooltips, min/max/step
  ├── widget_editors.py         Custom Qt widgets (FloatEditor, BoolEditor, EnumEditor, etc.)
  ├── widget_primitives.py      CollapsibleSection, HeaderDivider
  ├── widget_sections.py        20+ section classes, each wrapping a state dataclass
  ├── widgets.py                WidgetBundle — single dataclass holding all sections
  ├── napari_layout.py          Main window: splitter(viewer | sidebar tabs)
  ├── state_bridge.py           Bidirectional: collect_gui_state ↔ apply_gui_state
  ├── params_mapper.py          GuiState → RuntimePhotoParams
  ├── controller.py             GuiController — orchestrates all interactions
  ├── controller_runtime.py     SimulationWorker (QRunnable), display transforms
  ├── controller_layers.py      napari layer management, polaroid animation
  ├── controller_persistence.py Save/load/redefault actions
  ├── controller_profile_sync.py Profile change → bulk widget update
  ├── persistence.py            JSON serialization, QSettings for dialog dirs
  ├── options.py                Enums for all dropdowns
  ├── polaroid_animation.py     Polaroid develop animation on output layer reveal
  └── theme*.py                 Dark theme palette and stylesheet
```

---

## 2. 完整用户流程图

```
┌─────────────────────────────────────────────────────────────────────┐
│                        APPLICATION STARTUP                          │
│  app.py:create_app()                                                │
│    ├─ Create napari Viewer (hidden)                                 │
│    ├─ Apply dark palette                                            │
│    ├─ Create WidgetBundle (all 20+ sections)                        │
│    ├─ Load saved default GUI state (or factory default)             │
│    ├─ Apply state to widgets via state_bridge.apply_gui_state()     │
│    ├─ Initialize GuiController                                      │
│    │    ├─ sync_display_transform_availability()                    │
│    │    ├─ show_startup_placeholder() → black 3:2 placeholder       │
│    │    └─ connect_controller_signals()                             │
│    ├─ Build main window (splitter: viewer | sidebar)                │
│    └─ Schedule background warmup (JIT numba, colour module)         │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        IMAGE LOADING                                │
│                                                                     │
│  Path A: Import RGB (FilePickerSection)                             │
│    ├─ Browse → QFileDialog → load_input_image(path)                 │
│    ├─ load_image_oiio(path) → float32 array                        │
│    ├─ read_image_color_encoding(path) → auto-set color space/CTTF  │
│    ├─ _set_or_add_input_stack(image)                                │
│    │    ├─ resize_for_preview(max_size)                             │
│    │    ├─ prepare_input_color_preview_image() → sRGB preview       │
│    │    └─ set_or_add_input_preview_layer()                         │
│    │         ├─ Create white_border layer (white frame)             │
│    │         ├─ Create watermark layer (photo paper back)           │
│    │         ├─ Create input_preview layer                          │
│    │         └─ Home camera view                                    │
│    └─ request_auto_preview_if_enabled()                             │
│                                                                     │
│  Path B: Import Raw (LoadRawSection)                                │
│    ├─ Browse → QFileDialog → load_raw_image(path)                   │
│    ├─ load_and_process_raw_file(path, wb, temp, tint, lens_corr)   │
│    │    └─ Returns RawProcessingResult(image, diagnostics)          │
│    ├─ Store diagnostics on preview layer metadata                   │
│    └─ Same input stack setup as Path A                              │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    FILM SELECTION & PARAMETER ADJUSTMENT             │
│                                                                     │
│  SimulationSection (Profiles tab, MAIN)                             │
│    ├─ film_stock: ProfileEnumEditor (cine/still prefix rendering)   │
│    │    └─ textActivated → apply_film_profile_defaults()            │
│    │         ├─ build_params_from_state(current_state)              │
│    │         ├─ digest_after_selection(params)                      │
│    │         │    ├─ digest_params() (resolve stock specifics)      │
│    │         │    └─ Set scan_film based on is_positive             │
│    │         ├─ gui_state_from_params(digested) → synced_state      │
│    │         └─ apply_profile_sync_state() → bulk update widgets    │
│    │              (updates 80+ fields across 8 sections)            │
│    ├─ print_paper: ProfileEnumEditor                                │
│    │    └─ textActivated → apply_print_profile_defaults()           │
│    │         └─ Same flow, also sets scan_film=False                │
│    └─ All other parameters editable in their respective sections    │
│                                                                     │
│  Auto-preview trigger chain:                                        │
│    Any widget change → request_auto_preview()                       │
│      → QTimer.singleShot(0) → _run_scheduled_auto_preview()        │
│        → _run_preview(report_status=False)                          │
│          → _start_simulation(source=preview_layer)                  │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         PREVIEW & SCAN                              │
│                                                                     │
│  PREVIEW button (preview_requested signal)                          │
│    → run_preview() → _start_simulation(source=preview_layer)        │
│    ├─ Uses _current_preview_image (downscaled)                      │
│    ├─ preview_mode=True → disables grain, halation, blurs, USM      │
│    ├─ SimulationWorker(QRunnable) on QThreadPool                    │
│    │    ├─ _process_image_with_runtime(image, params)               │
│    │    │    ├─ digest_params(params, apply_stocks_specifics)       │
│    │    │    ├─ Simulator(digested_params) or update_params()       │
│    │    │    └─ process_with_metadata(image) → float output         │
│    │    └─ prepare_output_display_image() → uint8 display           │
│    │         ├─ CCTF encoding if linear output                      │
│    │         └─ Display transform (ICC profile) if enabled          │
│    └─ _on_simulation_finished(result)                               │
│         ├─ Check input_generation (discard if input changed)        │
│         ├─ _set_or_add_output_layer()                               │
│         │    ├─ Polaroid animation (1600ms) on first reveal         │
│         │    ├─ Crossfade animation on subsequent runs              │
│         │    └─ Store float data + color metadata in layer          │
│         └─ Update status bar                                        │
│                                                                     │
│  SCAN button (scan_requested signal)                                │
│    → run_scan() → _start_simulation(source=input_layer)             │
│    ├─ Uses _current_input_image (full resolution)                   │
│    ├─ preview_mode=False → full pipeline                            │
│    └─ Same worker/result flow as preview                            │
│                                                                     │
│  During simulation:                                                 │
│    ├─ All action buttons disabled                                   │
│    ├─ Status bar: "Computing preview/scan..."                       │
│    ├─ If auto_preview triggers while running → _pending=True        │
│    └─ On finish → replay pending auto_preview                       │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          OUTPUT / SAVE                              │
│                                                                     │
│  SAVE button → save_output_layer()                                  │
│    ├─ Check output layer exists                                     │
│    ├─ Determine default extension (.jpg or .exr based on HDR)       │
│    ├─ QFileDialog with last-used directory memory                   │
│    ├─ Get float data from output layer metadata                     │
│    ├─ Color space conversion (source → saving)                      │
│    ├─ Read + copy source metadata (EXIF etc.)                       │
│    ├─ Collect HDR metadata if HDR photo/EXR rendition               │
│    │    ├─ scene_luminance from layer metadata                      │
│    │    ├─ scene_energy_metadata from layer metadata                │
│    │    └─ Build hdr_mapping_kwargs from HdrExportState             │
│    ├─ save_image_oiio(filepath, data, **kwargs)                     │
│    ├─ write_image_metadata(filepath, source_metadata)               │
│    └─ Status bar: "Saved to {path} (...)"                           │
│                                                                     │
│  Output formats:                                                    │
│    ├─ JPG/PNG/TIF — CCTF-encoded, clipped, with ICC profile        │
│    ├─ EXR (scene_linear_archive) — linear float, unclipped          │
│    ├─ EXR (hdr_rendition) — authored HDR with gain map params       │
│    └─ HEIC HDR — gain map JPEG for HDR displays                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. 状态机分析

### 3.1 应用状态

```
                    ┌──────────────┐
                    │   STARTUP    │
                    │ (no image)   │
                    └──────┬───────┘
                           │ load image
                           ▼
                    ┌──────────────┐
                    │ IMAGE_LOADED │◄─────────────────────┐
                    │ (preview     │                      │
                    │  cached)     │                      │
                    └──────┬───────┘                      │
                           │                              │
              ┌────────────┼────────────┐                 │
              ▼            ▼            ▼                 │
     ┌────────────┐ ┌───────────┐ ┌──────────┐          │
     │ AUTO_PREVIEW│ │ PREVIEW   │ │  SCAN    │          │
     │ (queued)   │ │ RUNNING   │ │ RUNNING  │          │
     └──────┬─────┘ └─────┬─────┘ └────┬─────┘          │
            │             │             │                 │
            └─────────────┼─────────────┘                 │
                          ▼                               │
                   ┌──────────────┐                       │
                   │ OUTPUT_READY │─── save ──► saved     │
                   │ (layer       │                       │
                   │  visible)    │─── param change ──────┘
                   └──────────────┘
```

### 3.2 状态转换（控制器内部）

| 当前状态 | 触发条件 | 下一状态 | 备注 |
|---|---|---|---|
| 无图像 | `load_input_image` / `load_raw_image` | 图像已加载 | 创建预览缓存 |
| 图像已加载 | `request_auto_preview` | 自动预览排队 | QTimer.singleShot(0) |
| 自动预览排队 | 定时器触发，无活动模拟 | 预览运行中 | `_run_scheduled_auto_preview` |
| 自动预览排队 | 定时器触发，模拟正在进行 | 设置待处理标志 | `_pending_auto_preview = True` |
| 任意状态 | `run_preview` | 预览运行中 | 完整按钮触发 |
| 任意状态 | `run_scan` | 扫描运行中 | 全分辨率 |
| 模拟运行中 | 模拟完成 | 输出就绪 | `_on_simulation_finished` |
| 模拟运行中 | 模拟失败 | 前一状态 | 显示错误对话框 |
| 模拟运行中 | 输入变化 | 代际不匹配 | 结果被丢弃 |
| 模拟运行中 | 请求新模拟 | 被阻止 | "Simulation already running" |
| 输出就绪 | 参数变更 + 自动预览 | 自动预览排队 | 循环继续 |

### 3.3 配置文件同步状态机

```
film_stock change (textActivated)
  → apply_film_profile_defaults(stock)
    → build_params_from_state(current)
    → digest_after_selection(params)
      → digest_params(params)        [resolve stock-specific defaults]
      → scan_film = is_positive      [positive film → show scan]
    → gui_state_from_params(digested)
    → apply_profile_sync_state()
      → For each section in PROFILE_SYNC_FIELDS:
        → widget.value = synced_value
      → Special: scan_film via set_scan_film_value()
    → _next_runtime_digest_applies_stock_specifics = True
```

### 3.4 扫描用于打印的切换状态

```
scan_for_print ON:
  → Save current state {scan_white, scan_black, glare_active}
  → Set scan_white_correction = True
  → Set scan_black_correction = True
  → Set glare.active = False

scan_for_print OFF:
  → Restore saved state
  → Clear saved state
```

---

## 4. 控件层次结构与布局

### 4.1 主窗口结构

```
AppMainWindow (QMainWindow)
  └─ centralWidget (QWidget)
       └─ QHBoxLayout
            ├─ QSplitter (Horizontal)
            │    ├─ ViewerPanel (QFrame)
            │    │    ├─ napari viewer widget (takes most space)
            │    │    └─ StatusBar container (QHBoxLayout)
            │    │         ├─ QStatusBar (messages)
            │    │         ├─ ccw rotate button
            │    │         ├─ cw rotate button
            │    │         ├─ 100% zoom button
            │    │         ├─ 200% zoom button
            │    │         ├─ 400% zoom button
            │    │         └─ reset view button
            │    │
            │    └─ Sidebar (QFrame, 420px default)
            │         └─ QVBoxLayout
            │              ├─ QTabWidget (controlsTabWidget)
            │              │    ├─ TAB: "MAIN" (scrollable)
            │              │    │    ├─ FilePickerSection (Import RGB)
            │              │    │    ├─ LoadRawSection (Import Raw)
            │              │    │    ├─ PreviewCropSection (Crop and upscale)
            │              │    │    ├─ InputImageSection (Input)
            │              │    │    ├─ CameraSection (Camera)
            │              │    │    ├─ SimulationSection (Profiles)
            │              │    │    ├─ ExposureControlSection
            │              │    │    ├─ EnlargerSection
            │              │    │    ├─ ScannerSection
            │              │    │    ├─ HdrExportSection
            │              │    │    └─ OutputSection
            │              │    │
            │              │    ├─ TAB: "FILM" (scrollable)
            │              │    │    ├─ HalationSection
            │              │    │    ├─ CouplersSection
            │              │    │    ├─ GrainSection
            │              │    │    └─ CameraDiffusionSection
            │              │    │
            │              │    ├─ TAB: "PRINT" (scrollable)
            │              │    │    ├─ GlareSection
            │              │    │    ├─ PreflashingSection
            │              │    │    └─ DiffusionSection
            │              │    │
            │              │    ├─ TAB: "ADVANCED" (scrollable)
            │              │    │    ├─ SpectralUpsamplingSection
            │              │    │    ├─ TuneSection
            │              │    │    └─ SpecialSection
            │              │    │
            │              │    └─ TAB: "CONFIG" (scrollable)
            │              │         ├─ GuiConfigSection
            │              │         ├─ DisplaySection
            │              │         └─ CollapsibleSection("napari layers")
            │              │
            │              └─ SimulationSection.action_bar() (always visible)
            │                   ├─ Row: auto_preview ☐ | scan_film ☐ | scan_for_print ☐
            │                   └─ Row: [PREVIEW] [SCAN] [SAVE]
```

### 4.2 图层堆栈 (napari)

```
Bottom → Top:
  1. white_border  — White frame around image (padding)
  2. watermark     — Photo paper back texture
  3. input_preview — Scaled-down input image (sRGB preview)
  4. output        — Simulation result (appears with polaroid animation)
```

---

## 5. 痛点与困惑流程

### 5.1 关键用户体验问题

**P1：模拟阻塞 — 无队列、无取消**
- `controller.py:994` 处的 `_start_simulation()` 在 `_active_simulation_worker is not None` 时立即返回，仅在状态栏显示消息 "Simulation already running"
- 没有取消按钮。对大图像的长时间扫描无法中断
- 自动预览被延迟，但用户无法看到队列状态

**P2：参数数量过多**
- 仅 MAIN 选项卡就有约 15 个可折叠节，包含 100 多个独立控件
- 专业工具如 Lightroom 默认仅显示约 10 个滑块，高级面板处于隐藏状态
- Profiles 节（`SimulationSection`）从其自身表单隐藏了 35 个字段，但这些字段在其他节中可见 — 归属关系令人困惑

**P3：胶片/打印功能在次要选项卡中**
- 最具创意的决策（光晕、颗粒、成色剂、扩散）位于 FILM/PRINT 选项卡中
- 用户必须切换选项卡才能调整这些设置，打断了"加载 → 调整 → 预览"的流程
- MAIN 选项卡主要被只需设置一次的技术 I/O 设置占据

**P4：扫描用于打印是一个静默的副作用切换**
- `widget_sections.py:735` 处的 `_apply_scan_for_print_mode()` 静默修改 `scan_white_correction`、`scan_black_correction` 和 `glare.active`
- 没有确认，没有关于更改内容的视觉指示
- 切换关闭时的状态恢复依赖于脆弱的 `_scan_for_print_restore_state` 字典

**P5：自动预览不可预测**
- 通过 `app.py:210` 处的 `connect_auto_preview_signals()` 连接到每个控件变更
- `QTimer.singleShot(0)` 进行合并，但快速拖动滑块可以排队多个预览
- 如果模拟正在运行，待处理标志被设置，但用户无法看到
- `display.preview_max_size` 和 `display.output_interpolation` 被明确排除在自动预览之外（第 221 行），但这并未传达给用户

**P6：没有撤销/重做**
- 状态变更是即时且不可逆的
- `clone_gui_state()` 存在但仅用于持久化，不用于历史记录
- 专业工具（Lightroom、Capture One）都具有完整的撤销栈

### 5.2 中等用户体验问题

**P7：HDR 导出控件的可见性令人困惑**
- `widget_sections.py:791` 处的 `HdrExportSection._sync_mode()` 根据 `hdr_mapping_mode` 显示/隐藏控件
- 通用模式：显示 5 个控件，隐藏 3 个
- 配置文件感知模式：显示 3 个，隐藏 5 个
- 但 `path_to_white_enabled` 始终可见，没有关于其适用模式的上下文说明

**P8：输出节的位置和重复**
- 输出颜色空间同时出现在 `SimulationSection`（隐藏）和 `OutputSection`（可见）中
- OutputSection 中的 `color_management_workflow` 控制的是输入转换，而非输出 — 位置具有误导性
- `hdr_exr_output` 切换在 OutputSection 中，但影响整个管道行为

**P9：裁剪节默认折叠且隐藏在 MAIN 中**
- `PreviewCropSection` 默认折叠，其字段也隐藏在 `InputImageSection` 中
- 用户必须知道展开 "Crop and upscale" 才能使用它
- 图像上没有可视裁剪叠加层 — 参数是盲输入的

**P10：配置文件同步覆盖用户更改**
- 更改 film_stock 时，`controller_profile_sync.py:110` 处的 `apply_profile_sync_state()` 覆盖 80 多个字段
- 任何手动调整都会丢失且没有警告
- 没有针对单个节的"恢复到配置文件默认值"按钮

**P11：保存工作流程脱节**
- SAVE 按钮在侧边栏底部的操作栏中
- 默认文件名从输入路径派生 — 如果没有加载输入，则为 "output.jpg"
- 没有批量保存、没有保存预设、没有格式特定的质量设置

**P12：预热是静默的且可能失败**
- `app.py:60` 处的 `_warmup_full_gui()` 在后台线程中运行，使用裸的 `except BaseException: return`
- 如果预热失败，第一次预览/扫描将变慢且没有解释
- 没有预热完成的进度指示器

### 5.3 小问题

**P13：** `runtime_float_precision` 位于实验性节中 — 用户可能在不理解内存影响的情况下更改它

**P14：** `classic_soft` 扩散滤镜系列列在 `DiffusionFilterFamilies` 枚举中，但未在工具提示中记录

**P15：** `scan_unsharp_mask` 是一个元组 [sigma, amount] — UI 中没有两个组件的单独标签

**P16：** Polaroid 动画在每次首次输出时播放，即使用户只想快速查看结果

---

## 6. 与专业工具对比缺失的功能

| 功能 | Lightroom | Capture One | DxO FilmPack | Spektrafilm | 优先级 |
|---|---|---|---|---|---|
| **撤销/重做** | 完整历史面板 | 完整历史记录 | 完整历史记录 | 无 | 高 |
| **前后对比** | 并排、分割 | 前后切换 | A/B 对比 | 无 | 高 |
| **预设/风格** | 内置数百种 | 风格 + 预设 | 胶片预设 | 仅胶片配置文件 | 中 |
| **批量处理** | 完整批量 | 批量变体 | 批量 | 无 | 中 |
| **直方图** | 实时、每通道 | 实时、每通道 | 实时 | 无 | 中 |
| **虚拟副本** | 多个变体 | 变体 | 无 | 无 | 低 |
| **裁剪叠加层** | 可视、三分法 | 可视裁剪工具 | 可视 | 仅数值 | 高 |
| **镜头配置文件** | 庞大库 | 镜头校正 | 镜头模块 | 基本 RAW 校正 | 低 |
| **色调曲线** | 参数化 + 点 | 曲线编辑器 | 曲线 | 仅伽马因子 | 中 |
| **色彩分级** | 色轮、HSL | 颜色编辑器 | 颜色通道 | 仅滤镜偏移 | 中 |
| **污点去除** | 克隆/修复 | 污点去除 | 无 | 不适用（胶片模拟） | 不适用 |
| **导出预设** | 多个预设 | 处理配方 | 导出预设 | 无 | 中 |
| **键盘快捷键** | 丰富 | 可自定义 | 有限 | 无可见的 | 低 |
| **软打样** | 完整软打样 | 软打样 | 打样 | 显示变换 | 中 |
| **GPU 加速** | GPU 预览 | GPU 处理 | 无 | CPU/GPU 后端 | 已完成 |
| **HDR 显示** | HDR 输出 | HDR | 无 | HDR 导出 | 已完成 |
| **元数据编辑** | 完整 EXIF/IPTC | 元数据 | 基本 | 仅复制传递 | 低 |

---

## 7. 建议改进（按优先级排序）

### 优先级 1 — 关键修复

#### 7.1.1 修复 HDR Path-to-White 切换（缺陷 H2）
**文件：** `controller.py:569`
**问题：** `profile_hdr_path_to_white_strength` 在启用时硬编码为 0.30，忽略实际切换状态
**修复：** 将 `path_to_white_enabled` 连接到实际的 HdrExportState 值，而不是条件常量
**工作量：** 小

#### 7.1.2 添加模拟取消按钮
**文件：** `controller.py`、`widget_sections.py`、`controller_runtime.py`
**问题：** 无法取消正在运行的模拟
**修复：**
- 在 `SimulationSection` 中添加 `cancel_requested` 信号
- 在 PREVIEW/SCAN 旁边添加取消按钮（仅在模拟期间可见）
- 在 `GuiController._start_simulation` 中存储 worker 引用
- 添加 `cancel()` 方法，调用 `worker.signals.finished.disconnect()` 并让 GC 回收
- `SimulationWorker.run()` 应定期检查取消标志（通过管道现有的进度回调，如果可用）
**工作量：** 中

#### 7.1.3 添加撤销/重做状态历史
**文件：** `controller.py`、新建 `controller_history.py`
**修复：**
- 维护一个 `list[GuiState]` 历史栈和索引
- 每次参数变更时（防抖 500ms），将 `collect_gui_state()` 推入历史记录
- Ctrl+Z 弹出到上一状态，Ctrl+Y 向前推进
- 最大约 50 个状态以限制内存
- 使用现有的 `clone_gui_state()` 进行安全复制
**工作量：** 中-大

### 优先级 2 — 用户体验改进

#### 7.2.1 前后对比模式
**文件：** `controller.py`、`controller_layers.py`、`widget_sections.py`
**修复：**
- 在操作栏中添加"对比"切换按钮
- 激活时：并排显示 input_preview 图层和 output 图层（napari 图层可见性切换）
- 或：使用 napari 内置的图层混合模式进行分割视图
- 键盘快捷键：`\` 键切换
**工作量：** 中

#### 7.2.2 重新组织侧边栏选项卡
**文件：** `napari_layout.py:398`
**当前：** MAIN / FILM / PRINT / ADVANCED / CONFIG
**建议：**
```
IMPORT    — FilePicker, LoadRaw, Crop/Upscale, InputImage, Camera
FILM      — Profiles (film_stock, print_paper), Exposure, Halation, Couplers, Grain
PRINT     — Enlarger, Diffusion, Glare, Preflashing, Scanner
OUTPUT    — Color workflow, Output space, HDR, Save settings
ADVANCED  — Spectral upsampling, Tune, Special, Camera diffusion
CONFIG    — GUI config, Display, napari layers
```
**理由：** 按工作流程阶段分组，而非按领域分组。胶片创意控件与胶片选择在同一选项卡上。
**工作量：** 中

#### 7.2.3 上下文显示 HDR 控件
**文件：** `widget_sections.py:791`
**当前：** 通用和配置文件感知控件根据模式显示/隐藏
**修复：** 同时根据 `hdr_exr_output` 切换状态显示/隐藏整个 HDR 导出节标题。当 HDR 输出关闭时，折叠该节并使标题变暗。添加简短的模式描述标签。
**工作量：** 小

#### 7.2.4 使扫描用于打印的更改透明化
**文件：** `widget_sections.py:735`
**修复：**
- 显示确认工具提示或内联注释，列出将要更改的内容
- 在修改的控件上添加视觉指示器（高亮边框）
- 考虑将其作为模式选择器而非切换（类似 Lightroom 的"处理版本"）
**工作量：** 小-中

#### 7.2.5 添加实时直方图叠加层
**文件：** `controller_layers.py` 或新模块
**修复：**
- 模拟完成后，从浮点输出数据计算直方图
- 作为半透明叠加层显示在查看器画布上（napari 自定义控件）
- 每通道 RGB + 亮度
- 通过 Display 节切换
**工作量：** 中-大

### 优先级 3 — 专业功能

#### 7.3.1 快速预设系统
**文件：** 新建 `presets.py`、`widget_sections.py`、`persistence.py`
**修复：**
- 定义预设格式：`{name, description, partial_state_diff}`
- 附带内置预设："Portra 400 default"、"Tri-X pushed"、"Cinestill 800T night" 等
- 用户预设保存到 `~/.spektrafilm/presets/`
- Profiles 节中的预设选择器下拉菜单
- 通过 `apply_gui_state_sections()` 使用选择性节名称应用预设
**工作量：** 中

#### 7.3.2 带可视反馈的裁剪叠加层
**文件：** `controller_layers.py`、`widget_sections.py`
**修复：**
- 启用裁剪时，在输入预览上添加显示裁剪区域的半透明叠加层
- 当 crop_center 或 crop_size 变化时更新叠加层位置/大小
- 允许在图像上拖拽选择裁剪区域（napari shapes 图层）
**工作量：** 大

#### 7.3.3 批量处理
**文件：** 新建 `controller_batch.py`、`widget_sections.py`
**修复：**
- SAVE 旁边的"批量"按钮
- 通过 QFileDialog 选择多个输入文件
- 将当前 GUI 状态应用到所有输入
- 使用可配置的命名模板保存（`{input_stem}_film_{stock}.{ext}`）
- 带取消功能的进度对话框
**工作量：** 大

#### 7.3.4 导出预设 / 处理配方
**文件：** `persistence.py`、新节
**修复：**
- 保存/加载输出设置的组合（颜色空间、CCTF、HDR 模式、格式）
- 命名预设如 "Web sRGB JPG"、"Print AdobeRGB TIF"、"Archive EXR"
- 保存时通过下拉菜单应用
**工作量：** 小-中

#### 7.3.5 键盘快捷键
**文件：** `app.py`、`napari_layout.py`
**修复：**
- Ctrl+O：打开图像
- Ctrl+S：保存输出
- Ctrl+Z/Y：撤销/重做
- 空格：切换预览/扫描
- `\`：前后切换
- 1-5：切换选项卡
**工作量：** 小

---

## 8. 需要的具体代码更改

### 8.1 缺陷修复

| ID | 文件:行 | 问题 | 更改 |
|---|---|---|---|
| H2 | `controller.py:569` | 硬编码的 path_to_white_strength | 从 `gui_state.hdr_export.profile_hdr_path_to_white_strength` 读取或添加专用字段 |
| H2 | `state.py:119` | `path_to_white_enabled` 有默认值但没有强度字段 | 在 HdrExportState 中添加 `profile_hdr_path_to_white_strength: float = 0.30` |
| M2 | `state.py:111-122` | HdrExportState 没有 `__post_init__` 验证 | 为所有浮点字段添加范围约束验证 |
| M4 | `controller.py:581-593` | `save_image_oiio` 调用构建复杂的 kwargs 字典 | 将 HDR 保存逻辑提取到专用辅助函数 |

### 8.2 结构改进

| ID | 文件 | 更改 |
|---|---|---|
| U1 | 新建 `controller_history.py` | 带防抖推送的撤销/重做状态栈 |
| U2 | `controller.py` | 添加 `_cancel_active_simulation()` 方法 |
| U3 | `widget_sections.py` | 在 SimulationSection 操作栏中添加取消按钮 |
| U4 | `napari_layout.py:398` | 重新组织选项卡结构（见 7.2.2） |
| U5 | `widget_sections.py:791` | HDR 节可见性与 hdr_exr_output 绑定 |
| U6 | 新建 `presets.py` | 预设加载/保存基础设施 |
| U7 | `controller_layers.py` | 添加直方图叠加层渲染 |

### 8.3 状态桥接改进

| ID | 文件 | 更改 |
|---|---|---|
| S1 | `state_bridge.py:41-44` | `auto_preview` 和 `scan_film` 在正常节模式之外被特殊处理 — 应成为 SimulationSection 的 `get_state()`/`set_state()` 的一部分 |
| S2 | `controller_profile_sync.py` | 添加 `exclude_fields` 参数，使配置文件不会覆盖用户调优的输出设置 |

---

## 9. 关键发现摘要

1. **架构是健全的** — dataclass 状态、双向桥接、后台 worker 模式都是良好的基础
2. **主要用户体验问题是压倒性的复杂性** — 100 多个参数，没有渐进式披露
3. **缺失专业基础功能** — 没有撤销、没有前后对比、没有预设、没有直方图
4. **模拟是瓶颈** — 没有取消、没有队列、除状态栏文本外没有进度指示
5. **HDR 路径存在真实缺陷** — path_to_white_strength 传递已损坏（H2）
6. **配置文件同步是破坏性的** — 更改胶片类型覆盖所有手动调优且没有警告
7. **选项卡组织与工作流程不匹配** — 创意控件隐藏在次要选项卡中
8. **Polaroid 动画很有魅力** 但为每次首次预览增加了 1.6 秒 — 应该可以切换

对用户体验影响最大的更改是：(1) 修复 H2 缺陷，(2) 添加撤销/重做，(3) 重新组织选项卡，(4) 添加前后对比。仅这四项更改就能使用户体验更接近专业工具，同时保留现有架构。
