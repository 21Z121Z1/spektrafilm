# Spektrafilm macOS Liquid Glass App Implementation Plan

Status: implemented and under final verification on 2026-05-31.

## Goal

Create a native macOS app for Spektrafilm that mirrors the core Python GUI workflow, uses Liquid
Glass according to current Apple guidance, and delegates film simulation to the existing Python
runtime instead of duplicating runtime logic in Swift.

## Research Conclusions

Apple guidance found for this implementation supports this shape:

- Prefer standard SwiftUI desktop structure first: `NavigationSplitView`, toolbars, inspectors,
  forms, pickers, toggles, and steppers.
- Use system-provided glass/material behavior before adding custom chrome.
- Use custom `glassEffect` only where the app has a genuine custom surface.
- Group related custom glass elements with `GlassEffectContainer`.
- Availability-gate Liquid Glass so older macOS releases retain a material fallback.

Implementation choice:

- Main app structure uses native SwiftUI controls and AppKit window lifecycle.
- Custom Liquid Glass is limited to one preview canvas command/status strip.
- `LiquidGlassPanel` uses `GlassEffectContainer(spacing: 8)` and
  `.glassEffect(.regular.interactive(), in: RoundedRectangle(cornerRadius: 8, style: .continuous))`
  on macOS 26+, with `.regularMaterial` fallback.

## Architecture

The implementation is split into three boundaries:

- Swift app target `SpektrafilmMac`: app lifecycle, window, toolbar, sidebar, preview canvas,
  inspector, file panels, and user action state.
- Swift core target `SpektrafilmMacCore`: models, profile catalog reading, repo-root resolution,
  Python command construction, process execution, JSON decoding, and self-check.
- Python bridge `src/spektrafilm_gui/macos_bridge.py`: current GUI defaults, profile catalog,
  GUI state mapping, runtime parameter mapping, preview rendering, scan output, and metadata handoff.

The app bundle is produced by XcodeGen plus `xcodebuild` from `macos/SpektrafilmMac/project.yml`.
This was chosen over raw SwiftPM executable launch because a SwiftUI/AppKit GUI needs a real `.app`
bundle for LaunchServices, foreground activation, bundle identifier, signing, and process policy.

## Files

- [x] Create `docs/superpowers/plans/2026-05-31-macos-liquid-glass-app.md`
- [x] Create `docs/dev/2026-05-31-macos-liquid-glass-app.md`
- [x] Create `src/spektrafilm_gui/macos_bridge.py`
- [x] Create `tests/gui/test_macos_bridge.py`
- [x] Create `macos/SpektrafilmMac/Package.swift`
- [x] Create `macos/SpektrafilmMac/project.yml`
- [x] Create `macos/SpektrafilmMac/.gitignore`
- [x] Create `macos/SpektrafilmMac/Sources/SpektrafilmMac/SpektrafilmMacApp.swift`
- [x] Create `macos/SpektrafilmMac/Sources/SpektrafilmMac/Stores/SpektrafilmAppModel.swift`
- [x] Create `macos/SpektrafilmMac/Sources/SpektrafilmMac/Views/ContentView.swift`
- [x] Create `macos/SpektrafilmMac/Sources/SpektrafilmMac/Views/SidebarView.swift`
- [x] Create `macos/SpektrafilmMac/Sources/SpektrafilmMac/Views/PreviewCanvasView.swift`
- [x] Create `macos/SpektrafilmMac/Sources/SpektrafilmMac/Views/InspectorView.swift`
- [x] Create `macos/SpektrafilmMac/Sources/SpektrafilmMac/Support/LiquidGlassSupport.swift`
- [x] Create `macos/SpektrafilmMac/Sources/SpektrafilmMacCore/Models/SpektrafilmModels.swift`
- [x] Create `macos/SpektrafilmMac/Sources/SpektrafilmMacCore/Services/PythonBridgeCommandBuilder.swift`
- [x] Create `macos/SpektrafilmMac/Sources/SpektrafilmMacCore/Services/SpektrafilmPythonClient.swift`
- [x] Create `macos/SpektrafilmMac/Sources/SpektrafilmMacCore/Support/AppSelfCheck.swift`
- [x] Create `macos/SpektrafilmMac/Tests/SpektrafilmMacCoreTests/SpektrafilmMacCoreTests.swift`
- [x] Create `script/build_and_run.sh`
- [x] Create `.codex/environments/environment.toml`

## Task 1: Python Bridge

- [x] Add bridge tests for catalog/default exposure.
- [x] Add bridge tests for mapping `BridgeRenderOptions` into current Python GUI state.
- [x] Add bridge render test with injected image/runtime/save/color hooks.
- [x] Implement `describe_catalog()`.
- [x] Implement `BridgeRenderOptions`.
- [x] Implement `build_state_from_options()`.
- [x] Implement `render()` with preview and scan modes.
- [x] Implement manual CLI parsing for `describe` and `render`.
- [x] Lazy-load heavy runtime, color, profile, and image I/O imports so catalog and tests do not
  depend on full compiled-extension startup.
- [x] Remove pytest `tmp_path` fixture from the bridge test because the current Python 3.13 host can
  hang while importing `getpass` during tmpdir setup.

Verification:

```bash
PYTHONFAULTHANDLER=1 uv run --extra dev pytest tests/gui/test_macos_bridge.py -q -o faulthandler_timeout=30
```

Result: 3 passed.

## Task 2: Swift Core

- [x] Add SwiftPM package with `SpektrafilmMac` executable and `SpektrafilmMacCore` library.
- [x] Add tests for default render configuration.
- [x] Add tests for repo-root resolution from environment, `Info.plist`, and staged bundle path.
- [x] Add tests for describe, preview, and scan command construction.
- [x] Add tests for app self-check success/failure.
- [x] Implement models, profile catalog loading, command builder, async process runner, and self-check.

Verification:

```bash
swift test --package-path macos/SpektrafilmMac
```

Result: 10 Swift tests passed.

## Task 3: Native macOS App

- [x] Implement AppKit delegate lifecycle with `NSApplication.shared`, regular activation policy,
  retained delegate, retained `NSWindow`, transparent titlebar, and unified compact toolbar style.
- [x] Implement `NavigationSplitView` desktop layout.
- [x] Implement toolbar actions for Import, Preview, Scan, and Inspector.
- [x] Implement inspector with profile, color, exposure, effects, compute, and preview-size controls.
- [x] Implement async model actions with disabled states while rendering.
- [x] Implement file dialogs with `NSOpenPanel` and `NSSavePanel`.
- [x] Implement preview canvas image display and state text.
- [x] Remove instructional sidebar/empty-state prose during final UI self-review.

## Task 4: Liquid Glass

- [x] Use native controls first instead of custom chrome for the main app structure.
- [x] Add one custom glass surface for the preview command/status strip.
- [x] Gate Liquid Glass behind `#available(macOS 26.0, *)`.
- [x] Provide `.regularMaterial` fallback for older macOS.
- [x] Use 8 px rounded rectangles for glass/material surfaces.
- [x] Avoid decorative gradients, orbs, and opaque backgrounds over the sidebar or toolbar.

## Task 5: Build, Signing, And Run Integration

- [x] Add XcodeGen `project.yml`.
- [x] Build a real signed `.app` bundle through `xcodebuild`.
- [x] Enable hardened runtime to avoid AppleSystemPolicy launch denial.
- [x] Stage `macos/SpektrafilmMac/dist/SpektrafilmMac.app`.
- [x] Clear staged bundle xattrs after `ditto` so `com.apple.provenance` does not trigger
  AppleSystemPolicy rejection on local LaunchServices startup.
- [x] Add self-check mode to validate repo-root and profile availability without UI automation.
- [x] Add `script/build_and_run.sh` with `run`, `--debug`, `--logs`, `--telemetry`, and `--verify`.
- [x] Wire Codex Run action to `/bin/zsh -f ./script/build_and_run.sh`.
- [x] Treat explicit `/bin/zsh -f` as canonical because direct shebang launch can be unreliable in
  the current Codex/macOS execution path.

Verification:

```bash
/bin/zsh -f ./script/build_and_run.sh --verify
```

Result: exit 0; self-check printed `SpektrafilmMac self-check OK: 22 film profiles, 6 print profiles`.

## Task 6: Documentation And Final Gates

- [x] Write implementation report in `docs/dev/2026-05-31-macos-liquid-glass-app.md`.
- [x] Update this plan with implementation status and verification evidence.
- [x] Verify lightweight Python catalog path:

```bash
PYTHONPATH=src /opt/homebrew/bin/python3.14 -m spektrafilm_gui.macos_bridge describe
```

Result: 22 film profiles, 6 print profiles, default film `kodak_gold_200`, default paper
`kodak_supra_endura`.

- [x] Verify staged app signing:

```bash
codesign --verify --deep --strict --verbose=2 macos/SpektrafilmMac/dist/SpektrafilmMac.app
codesign -dvvv macos/SpektrafilmMac/dist/SpektrafilmMac.app
```

Result: app is valid on disk, satisfies its designated requirement, has `flags=0x10000(runtime)`,
Apple Development authority, TeamIdentifier `BL2M85D9LA`, and Runtime Version `26.5.0`.

- [x] Run final `git diff --check` after documentation edits.
- [x] Stop the launched development app before final response.
- [x] Mark the goal complete only after final gates are read.

## Confidence Checklist

- [x] Does the app build as a real `.app` bundle, not a raw executable?
- [x] Does it use current SwiftUI desktop structure before custom glass?
- [x] Does custom Liquid Glass stay grouped and availability-gated?
- [x] Does the Swift app avoid duplicating film simulation logic?
- [x] Does the Python bridge reuse existing GUI defaults and runtime mapping?
- [x] Does every render action have disabled/error states?
- [x] Are generated build outputs ignored?
- [x] Is local signing and hardened runtime verified?
- [x] Are staging xattrs cleared before LaunchServices verification?
- [x] Does LaunchServices keep the staged app process alive?
- [x] Did tests and build/run verification run fresh after the last code edit?
- [x] Did `git diff --check` run after the final documentation edit?

## Known Boundary

This is a development app bundle. It depends on the local repository and Python/`uv` environment for
rendering. A distribution phase should vendor or embed Python, sign with Developer ID, notarize the
bundle, and decide how OIIO/RAW support is packaged.

`spctl --assess` is not a reliable local gate on the current host because it intermittently returns
`Too many open files`. The reliable development gates are Swift tests, bridge tests, self-check,
LaunchServices launch, and strict codesign verification.
