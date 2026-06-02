> 这是英文原文的中文翻译。权威版本请参考英文原文。

# macOS Liquid Glass 应用

日期：2026-05-31

## 概述

本次实现为 Spektrafilm 添加了一个原生 macOS 应用，位于 `macos/SpektrafilmMac`。
该应用是一个基于 AppKit 托管的 SwiftUI 应用，具备原生的 Dock/窗口生命周期、Xcode 生成的 `.app`
捆绑包、本地 Apple Development 签名、强化运行时，以及通过 Python 桥接连接到现有胶片模拟运行时的能力。

该应用有意不在 Swift 中重新实现胶片模拟。Swift 负责桌面 UI、
文件面板、命令状态、预览图像展示和进程编排。Python 负责 GUI
默认值、配置文件发现、运行时参数映射、模拟、预览 PNG 写入和最终图像导出。

## 使用的最佳实践参考

- Apple Developer，[`glassEffect(_:in:)`](https://developer.apple.com/documentation/swiftui/view/glasseffect%28_%3Ain%3A%29)：自定义 Liquid Glass 通过 SwiftUI `glassEffect` 应用。
- Apple Developer，[将 Liquid Glass 应用于自定义视图](https://developer.apple.com/documentation/SwiftUI/Applying-Liquid-Glass-to-custom-views)：优先使用标准 SwiftUI 组件；使用 `GlassEffectContainer` 分组自定义玻璃视图。
- WWDC25，[使用新设计构建 SwiftUI 应用](https://developer.apple.com/videos/play/wwdc2025/323/)：在添加应用特定的玻璃效果之前，优先使用原生导航、工具栏、控件和系统材质。

本应用中的设计决策：

- `NavigationSplitView`、工具栏命令、表单、选择器、切换开关、步进器和 `.inspector` 承载主要的桌面结构。
- 自定义 Liquid Glass 仅限于预览画布命令/状态栏。
- `LiquidGlassPanel` 有可用性限制：macOS 26+ 使用 `GlassEffectContainer` 加 `.glassEffect(.regular.interactive())`；旧系统使用 `.regularMaterial`。
- 该应用避免使用不透明的自定义界面，以免与系统玻璃效果冲突。
- 空状态和导航行避免使用说明性文字；命令和参数标签承担交互功能。

## 新增或更改的文件

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

生成的/本地的构建产物由 `macos/SpektrafilmMac/.gitignore` 忽略：

- `.build/`
- `Config/Info.plist`
- `DerivedData/`
- `dist/`
- `SpektrafilmMac.xcodeproj/`

## 架构

`SpektrafilmMacApp` 使用 AppKit 委托入口点，而非原始的 SwiftPM 可执行文件启动。
这为 LaunchServices 提供了一个真正的应用捆绑包、常规激活策略、前台激活和一个保留的 `NSWindow`。

`project.yml` 是 Xcode 应用捆绑包的来源。它设置：

- `PRODUCT_BUNDLE_IDENTIFIER=org.spektrafilm.mac`
- `Info.plist` 中的 `SpektrafilmRepoRoot=$(SPEKTRAFILM_REPO_ROOT)`
- 本地 Apple Development 签名
- `ENABLE_HARDENED_RUNTIME=YES`

强化运行时设置是 macOS 26 上此本地构建所必需的。没有它，LaunchServices
可以启动进程，但 AppleSystemPolicy 会拒绝该应用。

`SpektrafilmAppModel` 管理当前输入文件、预览图像、选定的工作流部分、渲染
配置、状态文本、禁用状态和异步渲染操作。它调用
`SpektrafilmPythonClient`，后者运行由 `PythonBridgeCommandBuilder` 构建的确定性命令。

`RepoRootResolver` 按以下顺序解析 Python 仓库：

1. `SPEKTRAFILM_REPO_ROOT`
2. 捆绑包 `Info.plist` 中的 `SpektrafilmRepoRoot`
3. 暂存的 `dist/` 应用位置
4. 当前目录回退

## Python 桥接

`src/spektrafilm_gui/macos_bridge.py` 提供：

- `describe` 用于目录/默认值发现。
- `render` 用于预览或完整扫描。
- `BridgeRenderOptions` 用于类型化命令输入。
- `build_state_from_options()` 用于复用 Python GUI 默认值和参数映射。

该桥接对重型运行时依赖使用延迟导入，因为当前本地 Python 3.13
环境在动态加载某些编译扩展模块时可能会挂起。单元测试使用
注入的图像/运行时/保存/颜色依赖，因此无需导入完整的模拟栈即可验证桥接行为。

轻量级目录路径已通过以下命令验证：

```bash
PYTHONPATH=src /opt/homebrew/bin/python3.14 -m spektrafilm_gui.macos_bridge describe
```

报告了 22 个胶片配置文件、6 个打印配置文件、默认胶片 `kodak_gold_200` 和默认相纸
`kodak_supra_endura`。

## 构建与运行

从仓库根目录使用显式解释器形式：

```bash
/bin/zsh -f ./script/build_and_run.sh --verify
```

Codex Run action 在 `.codex/environments/environment.toml` 中连接到相同的命令。
直接 shebang 形式在当前 Codex/macOS 进程环境中可能仍然不可靠，因此
显式的 `/bin/zsh -f` 形式是规范的本地命令。

运行脚本：

1. 终止任何正在运行的 `SpektrafilmMac`
2. 运行 `swift build --package-path macos/SpektrafilmMac`
3. 使用 XcodeGen 重新生成 `SpektrafilmMac.xcodeproj`
4. 通过 `xcodebuild` 构建签名的应用
5. 暂存 `macos/SpektrafilmMac/dist/SpektrafilmMac.app`
6. 清除暂存的扩展属性（如 `com.apple.provenance`），否则即使有有效的本地签名也可能触发
   AppleSystemPolicy 拒绝
7. 为本地执行签名原始 SwiftPM 自检二进制文件
8. 运行 `SpektrafilmMac --self-check`
9. 使用 LaunchServices 打开暂存的应用
10. 确认活跃的非僵尸应用进程

## 验证快照

最后一次代码编辑后的新鲜验证：

- `PYTHONFAULTHANDLER=1 uv run --extra dev pytest tests/gui/test_macos_bridge.py -q -o faulthandler_timeout=30`：通过，3 个测试。
- `swift test --package-path macos/SpektrafilmMac`：通过，10 个 Swift 测试。
- `PYTHONPATH=src /opt/homebrew/bin/python3.14 -m spektrafilm_gui.macos_bridge describe`：通过，22 个胶片配置文件和 6 个打印配置文件。
- `/bin/zsh -f ./script/build_and_run.sh --verify`：通过；自检打印 `SpektrafilmMac self-check OK: 22 film profiles, 6 print profiles`。
- `codesign --verify --deep --strict --verbose=2 macos/SpektrafilmMac/dist/SpektrafilmMac.app`：通过。
- `codesign -dvvv macos/SpektrafilmMac/dist/SpektrafilmMac.app`：显示 `flags=0x10000(runtime)`、Apple Development 权限、TeamIdentifier `BL2M85D9LA`、Runtime Version `26.5.0`。
- 启动后的进程验证显示暂存的应用从 `macos/SpektrafilmMac/dist/SpektrafilmMac.app/Contents/MacOS/SpektrafilmMac` 运行。
- 最后一次由暂存捆绑包上的 `com.apple.provenance` 引起的 LaunchServices 失败已被复现，
  通过在 `ditto` 之后清除扩展属性修复，并通过相同的 `--verify` 路径重新验证。

`spctl --assess` 未被用作通过/失败的门禁，因为当前主机间歇性报告
`Too many open files`；`codesign --verify --deep --strict` 和 LaunchServices 进程验证
是此开发构建的可靠本地门禁。

## 已知边界

这是一个开发应用捆绑包，而非经过公证的分发包。渲染仍然依赖于
本地仓库和 Python/`uv` 环境。分发阶段应该嵌入或打包
Python 运行时，使用 Developer ID 证书签名，启用公证，并决定如何打包 OIIO/RAW
支持。

通过完整 Python 运行时的直接渲染仍然受到在 Python 3.13 中观察到的本地编译扩展
加载问题的限制。应用、目录路径、命令构建、桥接映射、
自检、签名和捆绑包启动已通过验证；完整图像渲染质量仍然由
现有的 Python 运行时测试和示例工作流覆盖，而非由此 macOS 应用包装器更改覆盖。
