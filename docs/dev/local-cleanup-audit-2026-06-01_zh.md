> 这是英文原文的中文翻译。权威版本请参考英文原文。

# 本地清理审计 - 2026-06-01

范围：`/Users/retriedstormtrooper/Documents/spektrafilm-main`

本审计将已移除的可重建缓存与仍需手动决策的剩余项目分开处理。审计有意不建议在没有明确理由的情况下删除已跟踪的源文件、已跟踪的验证样本或本地 IDE/代理状态。

## 已完成的清理

移除被忽略的、可重建的缓存/构建输出后，工作区大小从大约 `2.9G` 减少到 `2.3G`。`du` 结果为近似值，实际回收空间约为 `600M`。

已移除：

| 路径 | 可安全移除的原因 |
| --- | --- |
| `build/` | 本地 Halide/测试构建输出。 |
| `android/.gradle/` | 此检出的 Gradle 缓存。 |
| `android/app/build/` | Android 应用构建中间产物和合并的资源。 |
| `android/app/.cxx/` | Android 外部原生/CMake 中间产物。 |
| `macos/SpektrafilmMac/DerivedData/` | Xcode 派生数据。 |
| `macos/SpektrafilmMac/.build/` | SwiftPM 构建产物。 |
| `macos/SpektrafilmMac/dist/` | 本地 macOS 分发输出。 |
| `.pytest_cache/` | Pytest 运行缓存。 |
| `spektrafilm.egg-info/`、`src/spektrafilm.egg-info/` | 可编辑安装/安装元数据。 |
| `__pycache__/` 目录 | Python 字节码缓存，包括 `.venv` 内的缓存。 |
| `.DS_Store` 文件 | Finder 元数据。 |
| 从 Git 跟踪中移除的 `.matplotlib/fontlist-v390.json` | 机器本地的 Matplotlib 字体缓存。该文件在重新生成时保留于本地，`.matplotlib/` 目录现已被忽略。 |

## 剩余的手动清理候选项

| 优先级 | 路径 | 大小 | 当前状态 | 建议 |
| --- | ---: | ---: | --- | --- |
| 高 | `.venv/` | `2.1G` | 被忽略的本地 Python 环境 | 仅在准备好重新创建依赖时删除。基准命令为 `uv sync`；根据工作流需要添加可选的额外项，如 `--extra dev`、`--extra halide` 或 `--extra gpu-apple`。 |
| 中 | `.venv/lib/python3.13/site-packages/colour/htmlcov/` | `75M` | `.venv` 内第三方包的覆盖率 HTML | 如果保留 `.venv`，这是安全的节省空间方式；重新安装依赖后可能会再次出现。 |
| 低 | `docs/dev/autonomous-loop.log` | `32K` | 被忽略的本地日志 | 如果不再需要会话历史记录，可删除。 |
| 低 | `artifacts/`、`debug/` | `0B` | 被忽略的空输出目录 | 如需更简洁的根目录，可使用 `rmdir artifacts debug` 移除。 |
| 需审查 | `.claude/`、`.codex/` | `48K`、`4K` | 被忽略的本地代理状态 | 除非有意清除本地代理/会话配置，否则请保留。 |
| 需审查 | `android/local.properties` | `4K` | 被忽略的 Android SDK 路径/配置 | 如果 Android 构建仍需要本地 SDK 配置，请保留。 |
| 需审查 | `macos/SpektrafilmMac/Config/` | `4K` | 被忽略的本地应用配置 | 删除前请检查；macOS 应用工作区可能需要此配置。 |
| 需审查 | `macos/SpektrafilmMac/SpektrafilmMac.xcodeproj/` | `28K` | 被忽略的 Xcode 项目元数据 | 删除前请检查；生成的或本地 IDE 项目状态可能仍有用。 |

如选择继续操作，手动命令如下：

```bash
# 回收空间最大，但之后需要重新安装依赖。
rm -rf .venv
uv sync

# 保留虚拟环境的同时进行较小的清理。
rm -rf .venv/lib/python3.13/site-packages/colour/htmlcov
rm -f docs/dev/autonomous-loop.log
rmdir artifacts debug 2>/dev/null
```

## 请勿作为本地清理删除的项目

以下项目看起来像缓存或体积较大，但它们已被跟踪或与项目相关：

| 路径 | 大小 | 保留原因 |
| --- | ---: | --- |
| `scratch/IMG_9121_converted.DNG` | `9.4M` | 已跟踪的验证/样本制品。 |
| `output.heic` | `4K` | 已跟踪的输出/样本制品。 |
| `docs/dev/benchmark-artifacts/` | `476K` | 已跟踪的基准测试证据。 |
| `android/app/src/main/assets/profiles/hanatos2025_lut.bin` | `11M` | 已跟踪的 Android 运行时资源。 |
| `src/spektrafilm/data/luts/spectral_upsampling/*` | `~10M` | 已跟踪的仿真数据。 |
| `img/` | `18M` | 已跟踪的 README/测试图片资源。 |
| `.git/` | `155M` | 仓库历史和对象数据库。请勿删除；仅在需要时使用 Git 维护命令。 |

## 清理后当前被忽略的项目

剩余的被忽略路径为预期的本地状态：

```text
.claude/
.codex/
.matplotlib/
.venv/
android/local.properties
docs/dev/autonomous-loop.log
macos/SpektrafilmMac/Config/
macos/SpektrafilmMac/SpektrafilmMac.xcodeproj/
```

如果不再需要这些路径，请在确认上述权衡后手动移除。
