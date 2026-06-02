> 这是英文原文的中文翻译。权威版本请参考英文原文。

# Android 移植状态 - 2026-05-28

## 概述

本次工作在 `android/` 下添加了 Android 移植的基础框架。这是一个原生
Android/Kotlin 项目，包含 Compose UI、ViewModel/StateFlow 状态管理、与当前
`RuntimePhotoParams` 默认值对齐的确定性参数序列化、单元测试覆盖，
以及 JNI/C++ 诊断桥接源码。

本项目未在 Android 上实现完整的 Spektrafilm 胶片/打印/扫描渲染流程。
原生处理器仅用于诊断：它验证 Direct `ByteBuffer` 和 float32 RGB 缓冲区的
JNI 管道。

## 基于证据的决策

- 未集成 Chaquopy。官方 Chaquopy 17.0 支持 Python 3.10-3.14 和
  AGP 7.3-9.2，但 Python 3.13 的包索引不提供 Spektrafilm 的依赖图：
  NumPy 可用版本为 `1.26.2`，而非仓库要求的 `numpy~=2.4`，且 SciPy 在
  已检查的 Chaquopy 索引中没有 Python 3.13 的 wheel。参见：
  - https://chaquo.com/chaquopy/doc/current/versions.html
  - https://chaquo.com/pypi-13.1/numpy/
  - https://chaquo.com/pypi-13.1/scipy/
- 使用 AGP 9.2 配合 Gradle 9.4.1。AGP 9 不再支持旧版
  `org.jetbrains.kotlin.android` 插件，因为 Kotlin 支持已内置。
  因此构建仅应用 AGP 加 Kotlin Compose 和序列化插件。
- 使用 JDK 21 进行 Android 验证。机器上也有 JDK 24/25，但验证命令
  固定使用 JDK 21，以避免将更新的 JVM 组合作为 Android 应用缺陷进行测试。
- Android 原生打包由精确的 NDK 预检控制。本地 SDK 仅有一个不完整的
  `ndk/28.2.13676358/.installer` 目录（来自一次尝试的 AGP 自动配置），
  而非包含 `build/cmake/android.toolchain.cmake` 的完整 NDK。
- 现有的 Halide 主机 AOT 生成器构建仍然是本地 Halide 可用性的最有力证明。
  Android 交叉编译仍需完整的 NDK 和未来的 Halide AOT 集成。

## 已实现的组件

- `android/settings.gradle.kts`、根目录/应用 Gradle 文件、Android manifest
  和应用资源。
- 用于示例预览/导出流程和参数控制的 Compose 屏幕。
- `SpektrafilmViewModel` 使用不可变 UI 状态、`StateFlow`、防抖的
  `flatMapLatest` 预览处理、导出状态、错误信息、自检状态和基于撤销/重做的
  参数编辑。
- `SpektrafilmParams` 及嵌套的可序列化参数类，在 Android 模型有对应字段的地方
  默认值与当前运行时默认值匹配。
- `SpektrafilmProcessor` 契约，包含预览/全分辨率模式、进度、自检、
  结果诊断和直接 float 图像边界。
- 直接 float 图像分配在计算字节数之前通过溢出安全的边界检查验证尺寸，
  使无效的大尺寸在任何分配尝试之前就会失败。
- `SpektrafilmViewModel` 将原生自检异常报告为显式的自检不可用状态，
  而非使协程作用域崩溃。
- JNI/C++ 诊断桥接源码：
  - `nativeVersion()`
  - `nativeSelfTest()`
  - 带有 null/容量检查的 direct-buffer float32 复制/缩放入口点
- 参数序列化、编辑历史、direct-buffer 契约、处理器模式和
  ViewModel 取消/状态行为的单元测试。

## 构建和验证命令

使用 JDK 21 进行可重复的本地验证：

```bash
export JAVA_HOME="$(/usr/libexec/java_home -v 21)"
export ANDROID_HOME="$HOME/Library/Android/sdk"
```

Kotlin/JVM 单元验证：

```bash
gradle -p android testDebugUnitTest --no-daemon --max-workers=1 --stacktrace --console=plain
```

原生打包验证：

```bash
gradle -p android assembleDebug --no-daemon --max-workers=1 --stacktrace --console=plain
```

今天的预期本地结果：`assembleDebug` 在打包前失败，错误信息为：

```text
Android NDK 28.2.13676358 with build/cmake/android.toolchain.cmake is required
for Spektrafilm native builds. Install it with: sdkmanager "ndk;28.2.13676358"
```

安装 NDK 后，重新运行 `assembleDebug`。如果之后 Halide AOT 库可用，
通过 CMake 缓存变量 `SPEKTRAFILM_HALIDE_AOT_DIR` 传入其目录并添加显式
链接目标，然后才能声称具有真正的 Halide 处理能力。

## 2026-05-28 验证快照

本工作区的最新验证使用：

```bash
JAVA_HOME=/Library/Java/JavaVirtualMachines/jdk-21.jdk/Contents/Home
```

结果：

- `gradle -p android clean testDebugUnitTest --no-daemon --max-workers=1 --stacktrace --console=plain`：
  `BUILD SUCCESSFUL in 24s`，共执行 25 个任务。
- `gradle -p android assembleDebug --no-daemon --max-workers=1 --stacktrace --console=plain`：
  在 `:app:spektrafilmNativePreflight` 处按预期失败，因为本地 SDK
  不包含带有 `build/cmake/android.toolchain.cmake` 的完整
  `ndk/28.2.13676358`；此结果在 `clean` 后重新检查，按设计在 18s 内失败。
- `.venv/bin/python -m pytest tests/test_halide_android.py tests/test_halide_generators.py -q`：
  `14 passed in 34.16s`。
- `.venv/bin/python -m pytest tests/test_halide_backend.py tests/test_halide_color.py tests/test_halide_lut.py tests/test_halide_spectral.py tests/test_halide_filters.py tests/test_halide_android.py tests/test_halide_generators.py -q`：
  `67 passed in 42.49s`。
- `.venv/bin/python -m pytest tests/test_photo_params.py tests/test_runtime_api.py -q`：
  `45 passed in 0.52s`；运行完成后发出了已知的无头 Metal 设备 atexit 警告。
- `.venv/bin/python -m compileall src/spektrafilm/gpu src/spektrafilm/halide src/spektrafilm/generators tests -q`：
  通过。
- `c++ -std=c++17 -Wall -Wextra -Werror -I/Library/Java/JavaVirtualMachines/jdk-21.jdk/Contents/Home/include -I/Library/Java/JavaVirtualMachines/jdk-21.jdk/Contents/Home/include/darwin -fsyntax-only android/app/src/main/cpp/spektrafilm_android_jni.cpp`：
  通过。
- `git diff --check`：通过。

## 已知限制

- 本次未完成 Android 设备/模拟器的仪器化测试运行。
- 不存在 Chaquopy 桥接，因为当前的包证据不支持仓库的 Python 3.13 依赖集。
- Android 上没有完整的 Spektrafilm 渲染器。UI 文案、处理器诊断和文档均
  将原生路径描述为仅用于诊断。
- 由于缺少完整的 NDK，本地未完成 Android Halide 交叉编译。
- AGP 9 内置的 Kotlin 未自动将应用类 jar 放到本地
  `compileDebugUnitTestKotlin` 类路径上。构建添加了一个精确的
  `testImplementation(files(...classes.jar))` 依赖和任务依赖，以便
  单元测试能针对 AGP 生成的应用类 jar 进行编译。

## 后续步骤

1. 安装完整的 NDK 28.2.13676358 并重新运行 `assembleDebug`。
2. 原生打包成功后，为 `NativeSpektrafilmProcessor` 添加一个小型 Android
   仪器化测试。
3. 为 `arm-64-android` 交叉编译一个 Halide AOT 内核，将其链接到
   `libspektrafilm_android`，并添加 direct-buffer 一致性测试。
4. 在接入真正的导出之前，定义 Android 侧的分块/全分辨率图像边界。
5. 仅当 Spektrafilm 的依赖集发生变化或项目为 NumPy/SciPy 和原生 I/O 依赖
   构建了自有 Android wheel 时，才重新考虑 Python-on-Android 方案。
