# Spektrafilm GUI — Product Logic Review & UX Flow Audit

**Date:** 2026-05-27
**Scope:** Read-only analysis of all GUI source files in `src/spektrafilm_gui/`
**Goal:** Map user flows, identify pain points, compare to professional tools, propose improvements

---

## 1. Architecture Overview

The GUI is built on **napari** (scientific image viewer) with a custom Qt sidebar. Key layers:

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

## 2. Complete User Flow Diagram

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

## 3. State Machine Analysis

### 3.1 Application States

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

### 3.2 State Transitions (Controller Internals)

| Current State | Trigger | Next State | Notes |
|---|---|---|---|
| No image | `load_input_image` / `load_raw_image` | Image loaded | Creates preview cache |
| Image loaded | `request_auto_preview` | Auto preview queued | QTimer.singleShot(0) |
| Auto preview queued | Timer fires, no active sim | Preview running | `_run_scheduled_auto_preview` |
| Auto preview queued | Timer fires, sim active | Pending flag set | `_pending_auto_preview = True` |
| Any state | `run_preview` | Preview running | Full button press |
| Any state | `run_scan` | Scan running | Full resolution |
| Sim running | Sim finishes | Output ready | `_on_simulation_finished` |
| Sim running | Sim fails | Previous state | Error dialog shown |
| Sim running | Input changes | Generation mismatch | Result discarded |
| Sim running | New sim requested | Blocked | "Simulation already running" |
| Output ready | Param change + auto_preview | Auto preview queued | Cycle continues |

### 3.3 Profile Sync State Machine

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

### 3.4 Scan-for-Print Toggle State

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

## 4. Widget Hierarchy and Layout

### 4.1 Main Window Structure

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

### 4.2 Layer Stack (napari)

```
Bottom → Top:
  1. white_border  — White frame around image (padding)
  2. watermark     — Photo paper back texture
  3. input_preview — Scaled-down input image (sRGB preview)
  4. output        — Simulation result (appears with polaroid animation)
```

---

## 5. Pain Points and Confusing Flows

### 5.1 Critical UX Issues

**P1: Simulation blocks — no queue, no cancel**
- `_start_simulation()` at `controller.py:994` immediately returns if `_active_simulation_worker is not None` with only a status bar message "Simulation already running"
- No cancel button exists. Long-running scans on large images cannot be interrupted
- Auto-preview is deferred but the user gets no feedback about the queue

**P2: Overwhelming parameter count**
- The MAIN tab alone has ~15 collapsible sections with 100+ individual controls
- Professional tools like Lightroom show ~10 sliders by default, with advanced panels hidden
- The Profiles section (`SimulationSection`) hides 35 fields from its own form but they're exposed in other sections — confusing ownership

**P3: Film/Print in secondary tabs**
- The most creative decisions (halation, grain, couplers, diffusion) are in FILM/PRINT tabs
- Users must switch tabs to adjust these, breaking the "load → adjust → preview" flow
- The MAIN tab is dominated by technical I/O settings that are set once

**P4: Scan-for-print is a silent side-effect toggle**
- `_apply_scan_for_print_mode()` at `widget_sections.py:735` silently modifies `scan_white_correction`, `scan_black_correction`, and `glare.active`
- No confirmation, no visual indication of what changed
- State restoration on toggle-off depends on a fragile `_scan_for_print_restore_state` dict

**P5: Auto-preview is unpredictable**
- Connected to every widget change via `connect_auto_preview_signals()` at `app.py:210`
- `QTimer.singleShot(0)` coalesces, but rapid slider drags can queue many previews
- If a simulation is running, the pending flag is set but the user has no visibility
- `display.preview_max_size` and `display.output_interpolation` are explicitly excluded from auto-preview (line 221), but this isn't communicated

**P6: No undo/redo**
- State changes are immediate and irreversible
- `clone_gui_state()` exists but is only used for persistence, not history
- Professional tools (Lightroom, Capture One) all have full undo stacks

### 5.2 Moderate UX Issues

**P7: HDR export controls have confusing visibility**
- `HdrExportSection._sync_mode()` at `widget_sections.py:791` shows/hides widgets based on `hdr_mapping_mode`
- Generic mode: shows 5 controls, hides 3
- Profile-aware mode: shows 3, hides 5
- But `path_to_white_enabled` is always visible with no context about which mode it applies to

**P8: Output section placement and duplication**
- Output color space appears in both `SimulationSection` (hidden) and `OutputSection` (visible)
- `color_management_workflow` in OutputSection controls input conversion, not output — misleading placement
- `hdr_exr_output` toggle is in OutputSection but affects the entire pipeline behavior

**P9: Crop section is collapsed by default and hidden in MAIN**
- `PreviewCropSection` is collapsed by default and its fields are also hidden in `InputImageSection`
- Users must know to expand "Crop and upscale" to use it
- No visual crop overlay on the image — parameters are entered blind

**P10: Profile sync overwrites user changes**
- When changing film_stock, `apply_profile_sync_state()` at `controller_profile_sync.py:110` overwrites 80+ fields
- Any manual tuning is lost without warning
- No "revert to profile defaults" button for individual sections

**P11: Saving workflow is disconnected**
- SAVE button is in the action bar at the bottom of the sidebar
- Default filename is derived from input path — if no input was loaded, it's "output.jpg"
- No batch save, no save presets, no format-specific quality settings

**P12: Warmup is silent and can fail**
- `_warmup_full_gui()` at `app.py:60` runs in a background thread with bare `except BaseException: return`
- If warmup fails, the first preview/scan will be slow with no explanation
- No progress indicator for warmup completion

### 5.3 Minor Issues

**P13:** `runtime_float_precision` is in the Experimental section — users might change it without understanding memory implications

**P14:** The `classic_soft` diffusion filter family is listed in `DiffusionFilterFamilies` enum but not documented in tooltips

**P15:** `scan_unsharp_mask` is a tuple [sigma, amount] — no individual labels for the two components in the UI

**P16:** The polaroid animation plays on every first output, even when the user just wants to see results quickly

---

## 6. Missing Features vs. Professional Tools

| Feature | Lightroom | Capture One | DxO FilmPack | Spektrafilm | Priority |
|---|---|---|---|---|---|
| **Undo/Redo** | Full history panel | Full history | Full history | None | HIGH |
| **Before/After** | Side-by-side, split | Before/after toggle | A/B compare | None | HIGH |
| **Presets/Styles** | Hundreds built-in | Styles + presets | Film presets | Film profiles only | MEDIUM |
| **Batch Processing** | Full batch | Batch variants | Batch | None | MEDIUM |
| **Histogram** | Live, per-channel | Live, per-channel | Live | None | MEDIUM |
| **Virtual Copies** | Multiple variants | Variants | None | None | LOW |
| **Crop Overlay** | Visual, rule of thirds | Visual crop tool | Visual | Numeric only | HIGH |
| **Lens Profiles** | Extensive library | Lens correction | Lens modules | Basic RAW correction | LOW |
| **Tone Curve** | Parametric + point | Curve editor | Curve | Gamma factor only | MEDIUM |
| **Color Grading** | Color wheels, HSL | Color editor | Color channels | Filter shifts only | MEDIUM |
| **Spot Removal** | Clone/heal | Spot removal | None | N/A (film sim) | N/A |
| **Export Presets** | Multiple presets | Process recipes | Export presets | None | MEDIUM |
| **Keyboard Shortcuts** | Extensive | Customizable | Limited | None visible | LOW |
| **Soft Proofing** | Full soft proof | Soft proof | Proof | Display transform | MEDIUM |
| **GPU Acceleration** | GPU preview | GPU processing | None | CPU/GPU backend | DONE |
| **HDR Display** | HDR output | HDR | None | HDR export | DONE |
| **Metadata Editing** | Full EXIF/IPTC | Metadata | Basic | Copy-through only | LOW |

---

## 7. Proposed Improvements (Priority Ranked)

### PRIORITY 1 — Critical Fixes

#### 7.1.1 Fix HDR Path-to-White Toggle (Bug H2)
**File:** `controller.py:569`
**Issue:** `profile_hdr_path_to_white_strength` is hardcoded to 0.30 when enabled, ignoring the actual toggle state
**Fix:** Wire `path_to_white_enabled` to the actual HdrExportState value, not a conditional constant
**Effort:** Small

#### 7.1.2 Add Simulation Cancel Button
**Files:** `controller.py`, `widget_sections.py`, `controller_runtime.py`
**Issue:** No way to cancel a running simulation
**Fix:**
- Add `cancel_requested` signal to `SimulationSection`
- Add cancel button next to PREVIEW/SCAN (visible only during simulation)
- In `GuiController._start_simulation`, store worker reference
- Add `cancel()` method that calls `worker.signals.finished.disconnect()` and lets GC collect
- The `SimulationWorker.run()` should check a cancellation flag periodically (via the pipeline's existing progress callback if available)
**Effort:** Medium

#### 7.1.3 Add Undo/Redo State History
**Files:** `controller.py`, new `controller_history.py`
**Fix:**
- Maintain a `list[GuiState]` history stack and an index
- On each parameter change (debounced 500ms), push `collect_gui_state()` to history
- Ctrl+Z pops to previous state, Ctrl+Y pushes forward
- Maximum ~50 states to bound memory
- Use existing `clone_gui_state()` for safe copies
**Effort:** Medium-Large

### PRIORITY 2 — UX Improvements

#### 7.2.1 Before/After Comparison Mode
**Files:** `controller.py`, `controller_layers.py`, `widget_sections.py`
**Fix:**
- Add a "Compare" toggle button in the action bar
- When active: show input_preview layer and output layer side-by-side (napari layer visibility toggle)
- Or: use napari's built-in layer blending modes for split-view
- Keyboard shortcut: `\` key to toggle
**Effort:** Medium

#### 7.2.2 Reorganize Sidebar Tabs
**File:** `napari_layout.py:398`
**Current:** MAIN / FILM / PRINT / ADVANCED / CONFIG
**Proposed:**
```
IMPORT    — FilePicker, LoadRaw, Crop/Upscale, InputImage, Camera
FILM      — Profiles (film_stock, print_paper), Exposure, Halation, Couplers, Grain
PRINT     — Enlarger, Diffusion, Glare, Preflashing, Scanner
OUTPUT    — Color workflow, Output space, HDR, Save settings
ADVANCED  — Spectral upsampling, Tune, Special, Camera diffusion
CONFIG    — GUI config, Display, napari layers
```
**Rationale:** Groups by workflow stage, not by domain. Film creative controls are on the same tab as film selection.
**Effort:** Medium

#### 7.2.3 Show HDR Controls Contextually
**File:** `widget_sections.py:791`
**Current:** Generic and profile-aware controls are shown/hidden based on mode
**Fix:** Also show/hide the entire HDR Export section header based on `hdr_exr_output` toggle state. When HDR output is off, collapse the section and dim the header. Add a brief mode description label.
**Effort:** Small

#### 7.2.4 Make Scan-for-Print Changes Transparent
**File:** `widget_sections.py:735`
**Fix:**
- Show a confirmation tooltip or inline note listing what will change
- Add a visual indicator (highlighted border) on modified controls
- Consider making it a mode selector rather than a toggle (like Lightroom's "Process Version")
**Effort:** Small-Medium

#### 7.2.5 Add Live Histogram Overlay
**Files:** `controller_layers.py` or new module
**Fix:**
- After simulation completes, compute histogram from float output data
- Display as a semi-transparent overlay on the viewer canvas (napari custom widget)
- Per-channel RGB + luminance
- Toggle via Display section
**Effort:** Medium-Large

### PRIORITY 3 — Professional Features

#### 7.3.1 Quick Presets System
**Files:** New `presets.py`, `widget_sections.py`, `persistence.py`
**Fix:**
- Define preset format: `{name, description, partial_state_diff}`
- Ship built-in presets: "Portra 400 default", "Tri-X pushed", "Cinestill 800T night", etc.
- User presets saved to `~/.spektrafilm/presets/`
- Preset selector dropdown in the Profiles section
- Apply preset via `apply_gui_state_sections()` with selective section names
**Effort:** Medium

#### 7.3.2 Crop Overlay with Visual Feedback
**Files:** `controller_layers.py`, `widget_sections.py`
**Fix:**
- When crop is enabled, add a semi-transparent overlay showing the crop region on the input preview
- Update overlay position/size when crop_center or crop_size changes
- Allow drag-to-select crop region on the image (napari shapes layer)
**Effort:** Large

#### 7.3.3 Batch Processing
**Files:** New `controller_batch.py`, `widget_sections.py`
**Fix:**
- "Batch" button next to SAVE
- Select multiple input files via QFileDialog
- Apply current GUI state to all inputs
- Save with configurable naming template (`{input_stem}_film_{stock}.{ext}`)
- Progress dialog with cancel
**Effort:** Large

#### 7.3.4 Export Presets / Process Recipes
**Files:** `persistence.py`, new section
**Fix:**
- Save/load combinations of output settings (color space, CCTF, HDR mode, format)
- Named presets like "Web sRGB JPG", "Print AdobeRGB TIF", "Archive EXR"
- Apply on save via dropdown
**Effort:** Small-Medium

#### 7.3.5 Keyboard Shortcuts
**Files:** `app.py`, `napari_layout.py`
**Fix:**
- Ctrl+O: Open image
- Ctrl+S: Save output
- Ctrl+Z/Y: Undo/Redo
- Space: Toggle preview/scan
- `\`: Before/after toggle
- 1-5: Switch tabs
**Effort:** Small

---

## 8. Specific Code Changes Needed

### 8.1 Bug Fixes

| ID | File:Line | Issue | Change |
|---|---|---|---|
| H2 | `controller.py:569` | Hardcoded path_to_white_strength | Read from `gui_state.hdr_export.profile_hdr_path_to_white_strength` or add a dedicated field |
| H2 | `state.py:119` | `path_to_white_enabled` default but no strength field | Add `profile_hdr_path_to_white_strength: float = 0.30` to HdrExportState |
| M2 | `state.py:111-122` | HdrExportState has no `__post_init__` validation | Add validation for range constraints on all float fields |
| M4 | `controller.py:581-593` | `save_image_oiio` call builds complex kwargs dict | Extract HDR save logic into dedicated helper function |

### 8.2 Structural Improvements

| ID | File | Change |
|---|---|---|
| U1 | New `controller_history.py` | Undo/redo state stack with debounced push |
| U2 | `controller.py` | Add `_cancel_active_simulation()` method |
| U3 | `widget_sections.py` | Add cancel button to SimulationSection action bar |
| U4 | `napari_layout.py:398` | Reorganize tab structure (see 7.2.2) |
| U5 | `widget_sections.py:791` | HDR section visibility tied to hdr_exr_output |
| U6 | New `presets.py` | Preset loading/saving infrastructure |
| U7 | `controller_layers.py` | Add histogram overlay rendering |

### 8.3 State Bridge Improvements

| ID | File | Change |
|---|---|---|
| S1 | `state_bridge.py:41-44` | `auto_preview` and `scan_film` are handled specially outside the normal section pattern — should be part of SimulationSection's `get_state()`/`set_state()` |
| S2 | `controller_profile_sync.py` | Add `exclude_fields` parameter so profiles don't overwrite user-tuned output settings |

---

## 9. Summary of Key Findings

1. **The architecture is sound** — dataclass state, bidirectional bridge, background worker pattern are all good foundations
2. **The main UX problem is overwhelming complexity** — 100+ parameters with no progressive disclosure
3. **Missing professional basics** — no undo, no before/after, no presets, no histogram
4. **Simulation is a bottleneck** — no cancel, no queue, no progress indication beyond status bar text
5. **HDR path has a real bug** — the path_to_white_strength passthrough is broken (H2)
6. **Profile sync is destructive** — changing film stock overwrites all manual tuning without warning
7. **The tab organization doesn't match the workflow** — creative controls are hidden in secondary tabs
8. **The polaroid animation is charming** but adds 1.6s to every first preview — should be toggleable

The highest-impact changes for user experience would be: (1) fix the H2 bug, (2) add undo/redo, (3) reorganize tabs, and (4) add before/after comparison. These four changes alone would bring the UX closer to professional tools while preserving the existing architecture.
