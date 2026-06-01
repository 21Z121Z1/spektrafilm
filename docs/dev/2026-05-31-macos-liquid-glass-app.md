# macOS Liquid Glass App

Date: 2026-05-31

## Summary

This implementation adds a native macOS app for Spektrafilm under `macos/SpektrafilmMac`.
It is an AppKit-hosted SwiftUI app with a native Dock/window lifecycle, Xcode-generated `.app`
bundle, local Apple Development signing, hardened runtime, and a Python bridge into the existing
film simulation runtime.

The app intentionally does not reimplement film simulation in Swift. Swift owns the desktop UI,
file panels, command state, preview image presentation, and process orchestration. Python owns GUI
defaults, profile discovery, runtime parameter mapping, simulation, preview PNG writing, and final
image export.

## Best-Practice References Used

- Apple Developer, [`glassEffect(_:in:)`](https://developer.apple.com/documentation/swiftui/view/glasseffect%28_%3Ain%3A%29): custom Liquid Glass is applied through SwiftUI `glassEffect`.
- Apple Developer, [Applying Liquid Glass to custom views](https://developer.apple.com/documentation/SwiftUI/Applying-Liquid-Glass-to-custom-views): use standard SwiftUI components first; group custom glass views with `GlassEffectContainer`.
- WWDC25, [Build a SwiftUI app with the new design](https://developer.apple.com/videos/play/wwdc2025/323/): prefer native navigation, toolbars, controls, and system materials before adding app-specific glass.

Design consequences in this app:

- `NavigationSplitView`, toolbar commands, forms, pickers, toggles, steppers, and `.inspector` carry the main desktop structure.
- Custom Liquid Glass is limited to the preview canvas command/status strip.
- `LiquidGlassPanel` is availability-gated: macOS 26+ uses `GlassEffectContainer` plus `.glassEffect(.regular.interactive())`; older systems use `.regularMaterial`.
- The app avoids opaque custom chrome that would fight system glass.
- Empty states and navigation rows avoid instructional prose; commands and parameter labels carry the interaction.

## Files Added Or Changed

- `macos/SpektrafilmMac/Package.swift`
- `macos/SpektrafilmMac/project.yml`
- `macos/SpektrafilmMac/.gitignore`
- `macos/SpektrafilmMac/Sources/SpektrafilmMac/SpektrafilmMacApp.swift`
- `macos/SpektrafilmMac/Sources/SpektrafilmMac/Stores/SpektrafilmAppModel.swift`
- `macos/SpektrafilmMac/Sources/SpektrafilmMac/Views/*.swift`
- `macos/SpektrafilmMac/Sources/SpektrafilmMac/Support/LiquidGlassSupport.swift`
- `macos/SpektrafilmMac/Sources/SpektrafilmMacCore/Models/SpektrafilmModels.swift`
- `macos/SpektrafilmMac/Sources/SpektrafilmMacCore/Services/*.swift`
- `macos/SpektrafilmMac/Sources/SpektrafilmMacCore/Support/AppSelfCheck.swift`
- `macos/SpektrafilmMac/Tests/SpektrafilmMacCoreTests/SpektrafilmMacCoreTests.swift`
- `src/spektrafilm_gui/macos_bridge.py`
- `tests/gui/test_macos_bridge.py`
- `src/spektrafilm/__init__.py`
- `src/spektrafilm/runtime/__init__.py`
- `src/spektrafilm/profiles/io.py`
- `src/spektrafilm/runtime/params_builder.py`
- `script/build_and_run.sh`
- `.codex/environments/environment.toml`

Generated/local build outputs are ignored by `macos/SpektrafilmMac/.gitignore`:

- `.build/`
- `Config/Info.plist`
- `DerivedData/`
- `dist/`
- `SpektrafilmMac.xcodeproj/`

## Architecture

`SpektrafilmMacApp` uses an AppKit delegate entrypoint instead of a raw SwiftPM executable launch.
That gives LaunchServices a real app bundle, regular activation policy, foreground activation, and
a retained `NSWindow`.

`project.yml` is the source for the Xcode app bundle. It sets:

- `PRODUCT_BUNDLE_IDENTIFIER=org.spektrafilm.mac`
- `SpektrafilmRepoRoot=$(SPEKTRAFILM_REPO_ROOT)` in `Info.plist`
- local Apple Development signing
- `ENABLE_HARDENED_RUNTIME=YES`

The hardened runtime setting is required for this local build on macOS 26. Without it, LaunchServices
can spawn the process and then AppleSystemPolicy rejects the app.

`SpektrafilmAppModel` owns current input file, preview image, selected workflow section, render
configuration, status text, disabled states, and async render actions. It calls
`SpektrafilmPythonClient`, which runs the deterministic command built by `PythonBridgeCommandBuilder`.

`RepoRootResolver` resolves the Python repository from, in order:

1. `SPEKTRAFILM_REPO_ROOT`
2. `SpektrafilmRepoRoot` in the bundle `Info.plist`
3. the staged `dist/` app location
4. current directory fallback

## Python Bridge

`src/spektrafilm_gui/macos_bridge.py` provides:

- `describe` for catalog/default discovery.
- `render` for preview or full scan.
- `BridgeRenderOptions` for typed command inputs.
- `build_state_from_options()` to reuse the Python GUI defaults and parameter mapping.

The bridge uses lazy imports around heavy runtime dependencies because the current local Python 3.13
environment can hang while dynamically loading some compiled extension modules. Unit tests use
injected image/runtime/save/color dependencies so they validate bridge behavior without importing the
full simulation stack.

The lightweight catalog path was verified with:

```bash
PYTHONPATH=src /opt/homebrew/bin/python3.14 -m spektrafilm_gui.macos_bridge describe
```

It reported 22 film profiles, 6 print profiles, default film `kodak_gold_200`, and default paper
`kodak_supra_endura`.

## Build And Run

Use the explicit interpreter form from the repository root:

```bash
/bin/zsh -f ./script/build_and_run.sh --verify
```

The Codex Run action is wired to the same command in `.codex/environments/environment.toml`.
The direct shebang form may still be unreliable in the current Codex/macOS process environment, so
the explicit `/bin/zsh -f` form is the canonical local command.

The run script:

1. kills any running `SpektrafilmMac`
2. runs `swift build --package-path macos/SpektrafilmMac`
3. regenerates `SpektrafilmMac.xcodeproj` with XcodeGen
4. builds the signed app through `xcodebuild`
5. stages `macos/SpektrafilmMac/dist/SpektrafilmMac.app`
6. clears staging xattrs such as `com.apple.provenance`, which can otherwise trigger
   AppleSystemPolicy rejection despite a valid local signature
7. signs the raw SwiftPM self-check binary for local execution
8. runs `SpektrafilmMac --self-check`
9. opens the staged app with LaunchServices
10. confirms a live non-zombie app process

## Validation Snapshot

Fresh validation after the last code edits:

- `PYTHONFAULTHANDLER=1 uv run --extra dev pytest tests/gui/test_macos_bridge.py -q -o faulthandler_timeout=30`: passed, 3 tests.
- `swift test --package-path macos/SpektrafilmMac`: passed, 10 Swift tests.
- `PYTHONPATH=src /opt/homebrew/bin/python3.14 -m spektrafilm_gui.macos_bridge describe`: passed, 22 film profiles and 6 print profiles.
- `/bin/zsh -f ./script/build_and_run.sh --verify`: passed; self-check printed `SpektrafilmMac self-check OK: 22 film profiles, 6 print profiles`.
- `codesign --verify --deep --strict --verbose=2 macos/SpektrafilmMac/dist/SpektrafilmMac.app`: passed.
- `codesign -dvvv macos/SpektrafilmMac/dist/SpektrafilmMac.app`: shows `flags=0x10000(runtime)`, Apple Development authority, TeamIdentifier `BL2M85D9LA`, Runtime Version `26.5.0`.
- Process verification after launch showed the staged app running from `macos/SpektrafilmMac/dist/SpektrafilmMac.app/Contents/MacOS/SpektrafilmMac`.
- A final LaunchServices failure caused by `com.apple.provenance` on the staged bundle was reproduced,
  fixed by clearing xattrs after `ditto`, and reverified through the same `--verify` path.

`spctl --assess` was not used as a pass/fail gate because the current host intermittently reports
`Too many open files`; `codesign --verify --deep --strict` and LaunchServices process verification
are the reliable local gates for this development build.

## Known Boundary

This is a development app bundle, not a notarized distribution package. Rendering still depends on
the local repository and Python/`uv` environment. A distribution phase should embed or vendor the
Python runtime, sign with a Developer ID certificate, enable notarization, and decide how OIIO/RAW
support is packaged.

Direct rendering through the full Python runtime remains constrained by the local compiled-extension
loading issue observed in Python 3.13. The app, catalog path, command construction, bridge mapping,
self-check, signing, and bundle launch are verified; full-image render quality remains covered by
the existing Python runtime tests and sample workflows, not by this macOS app wrapper change.
