> 这是英文原文的中文翻译。权威版本请参考英文原文。

> **状态：已完成**。Android 基础框架已存在于 android/ 目录下。参见 android-port-status-20260528.md。

# Android 移植实现计划 - 2026-05-28

## 目标

构建一个经过验证的 Spektrafilm Android 移植基础框架，诚实地说明当前已实现的功能：一个包含 Kotlin/Compose 状态架构的原生 Android 项目，与 `RuntimePhotoParams` 对齐的类型化参数序列化，稳定的处理桥接合约，JNI/原生概念验证源码、测试和文档。本次迭代不会声称在 Android 上实现了完整的 Spektrafilm 渲染。

## 当前仓库现状

- 仓库中目前不存在 `android/` 项目、Gradle wrapper、Android manifest、Kotlin 源码、Compose UI、JNI wrapper 或 APK 构建产物。
- `pyproject.toml` 要求 Python `~=3.13`，依赖包括 `numpy~=2.4`、`scipy~=1.17`、`colour-science~=0.4.6`、`scikit-image~=0.26`、`numba~=0.64`、`OpenImageIO~=3.1.11`、`rawpy~=0.26.1`、`exiv2~=0.18.1` 和 `lensfunpy~=1.18.0`。
- `RuntimePhotoParams` 位于 `src/spektrafilm/runtime/params_schema.py`。它是一个 dataclass 树，包含 `film` 和 `print` 所需的 `Profile` 实例；配置文件名称目前不是一等可序列化的运行时字段。
- `digest_params()` 会修改并返回同一个 `RuntimePhotoParams` 对象。现有测试断言了运行时默认值、film/print 配置文件默认值和幂等性。
- 运行时按阶段模块拆分，位于 `src/spektrafilm/runtime/stages/`：filming、printing 和 scanning。桌面端管道在本次迭代中必须保持不变。
- 现有的 Android/Halide 支持仅在 Python 端：`src/spektrafilm/halide/android.py` 将 Android ABI 映射到 Halide 目标字符串，并在 `tests/test_halide_android.py` 中有单元测试覆盖。
- `src/spektrafilm/generators/` 包含四个 C++ Halide generator 文件和一个包含 10 个 `add_halide_library()` 目标的 CMake 项目。
- Host Halide generator 的配置和构建已使用已安装的 Python Halide CMake 包在本地验证通过。构建在 `/tmp/spektrafilm-halide-generators-host` 下生成了所有 host AOT 库。
- 本地 Android SDK 位于 `$HOME/Library/Android/sdk`，包含 API 34、35 和 36 平台以及 build-tools 30.0.3、34.0.0、35.0.0、35.0.1 和 36.0.0。
- 本地未安装 Android NDK。不存在 `$ANDROID_NDK/build/cmake/android.toolchain.cmake` 路径可用于 Android 交叉编译。
- 本地 Gradle 版本为 9.4.1。官方 Android 文档指出 AGP 9.2 需要 Gradle 9.4.1、SDK build-tools 36.0.0 和最低 JDK 17。
- 当前本地 Java 命令根据启动上下文报告 JDK 24/25。AGP 至少需要 JDK 17；验证必须报告实际使用的 JDK。

## 研究文档有效性

### 仍然有效

- `research-android-app-architecture.md` 在方向上是正确的，应用应使用 Kotlin、Jetpack Compose、ViewModel、StateFlow、协程取消、预览/导出分离以及 direct/native buffer 规范。
- 其内存警告是有效的：全分辨率 float32 buffer 在 Android 上太大，不能随意复制，因此桥接合约必须分别暴露预览和全分辨率路径。
- 其首选的处理边界——Direct `ByteBuffer` 加上 JNI/原生处理——比尝试在 Android Python 中运行整个桌面端技术栈更适合当前仓库。
- `halide-android-port-plan.md` 是准确的，目前确实不存在 JNI、Android NDK 项目、Kotlin UI、APK 或设备端 Android 实现。
- Halide AOT 方向仍然有效。Host generator 项目目前在 `Halide_DIR` 指向已安装的 Halide CMake 包时可以配置和构建。
- `arm64-v8a -> arm-64-android` 默认值在 NDK 工具链存在时仍然是正确的生产目标。

### 过时、推测性、矛盾或未验证

- `research-android-porting-strategies.md` 中的 Chaquopy 建议对于当前声明的 Spektrafilm 而言是过时的。Chaquopy 17.0 支持 Python 3.10-3.14 和 AGP 7.3-9.2，但其原生 Android 包索引不提供 Python 3.13 所需的 Spektrafilm 技术栈：
  - Chaquopy 有 `cp313` 的 `numpy-1.26.2` wheel，而非 Spektrafilm 所需的 `numpy~=2.4`。
  - Chaquopy 的 `scipy` 索引止步于 `cp310` wheel，不提供 `cp313` SciPy wheel，更不用说 `scipy~=1.17`。
  - `colour-science` 是纯 Python，但它依赖兼容的 NumPy/SciPy；仅凭纯 Python 状态并不能使 Spektrafilm 依赖图变得可行。
- 旧版 `research-android-port.md` 依赖表错误地指出对于当前依赖集，NumPy/SciPy/colour 通过 Chaquopy 很容易使用。
- 关于预构建的 scikit-image、Pillow、rawpy、OpenImageIO、exiv2 和 lensfunpy 可通过 Chaquopy 使用的说法，对于当前 Python 版本未经验证，不得作为实现基础。
- Vulkan 和 AGSL 说明是有用的未来研究方向，但本次迭代不会添加 GPU 计算后端。当前本地验证目标是 native CPU/JNI 合约加上现有 Halide AOT generator 证据。
- Android 交叉编译在本地未验证，因为缺少 NDK。实现必须清晰地失败或记录确切的设置命令，而不是假装已构建了 Android `.so` 输出。

## 具体实现范围

1. 添加 `android/` Gradle 项目，使用：
   - AGP `9.2.0`
   - Kotlin Android 插件 `2.3.21`
   - Compose BOM `2026.05.00`
   - `compileSdk = 36`
   - `minSdk = 26`
   - `targetSdk = 36`
   - `arm64-v8a` 作为主要原生 ABI
2. 添加 Kotlin 应用结构：
   - `MainActivity`
   - 适用于导入/预览/导出流程的 Compose 编辑界面
   - 不可变的 `SpektrafilmUiState`
   - 使用 `StateFlow` 的 `SpektrafilmViewModel`
   - 防抖和可取消的预览处理
   - 导出状态和错误报告
   - 参数编辑的有界撤销/重做历史
3. 添加 Android 参数模型和序列化：
   - `SpektrafilmParams`
   - 嵌套的 camera/enlarger/scanner/render/settings 参数数据类
   - 与当前 `RuntimePhotoParams` 默认值对齐的默认值
   - 确定性 JSON 序列化/反序列化
   - 默认值、序列化、编辑 reducer 和撤销/重做的单元测试
4. 添加处理桥接合约：
   - `SpektrafilmProcessor`
   - `ProcessingRequest`、`ProcessingResult`、`ProcessingProgress`、`ProcessorSelfTest`
   - 预览/全分辨率分离
   - 用于未来原生代码的 direct `ByteBuffer` 图像边界
   - 不虚假声称诊断处理等同于 Spektrafilm 渲染
5. 添加原生/JNI 概念验证源码：
   - `libspektrafilm_android`
   - `nativeVersion()`
   - `nativeSelfTest()`
   - 最小化的 direct-buffer float32 RGB 操作，验证原生字节序、direct-buffer 地址处理、维度和错误返回
   - 可独立链接原生代码并在提供 `SPEKTRAFILM_HALIDE_AOT_DIR` 时可选链接 Halide 产物的 CMake
6. 添加 Gradle/原生预检行为：
   - 已记录的 NDK 要求
   - 缺少 NDK/Halide AOT 路径时清晰的 Gradle 任务或构建消息
   - 不静默替换为原生 stub
7. 添加文档：
   - 保留此实施前计划
   - 添加 `docs/dev/android-port-status-20260528.md`
   - 在三份 Android 研究文档中添加标注日期的实现说明，关于 Chaquopy 可行性和已实现的基础框架
   - 仅在需要时添加简洁的 README 指引

## 非目标和延期工作

- 本次不进行 `SimulationPipeline` 的完整 C++ 移植。
- 本次不集成 Chaquopy。
- 不声称 Android 预览/导出执行了真正的 Spektrafilm film/print/scan 渲染。
- 除非项目构建完成后已有可运行设备，否则不进行 Android 设备或模拟器插桩测试。
- 不实现 Vulkan、AGSL、CameraX、MediaStore 导出、RAW/DNG 导入、HDR 显示管道或 Play Store 打包。
- 不更改桌面端 Python 运行时行为、SDR 渲染、配置文件行为、HDR 导出或现有 GUI 语义。
- 本次迭代不安装本地 NDK。

## 验证命令

已运行的编辑前和发现验证：

```bash
git status --short --branch
.venv/bin/python - <<'PY'
import halide, numpy, scipy, colour
print("halide", halide.install_dir())
print("numpy", numpy.__version__)
print("scipy", scipy.__version__)
print("colour", colour.__version__)
PY
cmake -S src/spektrafilm/generators -B /tmp/spektrafilm-halide-generators-host \
  -DHalide_DIR=$(.venv/bin/python - <<'PY'
from pathlib import Path
import halide
print(Path(halide.install_dir()) / "lib/cmake/Halide")
PY
) -DTARGET=host
cmake --build /tmp/spektrafilm-halide-generators-host -j2
```

实现后计划的验证：

```bash
git status --short
git diff --check
gradle -p android testDebugUnitTest
ANDROID_HOME="$HOME/Library/Android/sdk" gradle -p android testDebugUnitTest
ANDROID_HOME="$HOME/Library/Android/sdk" gradle -p android assembleDebug
.venv/bin/python -m pytest tests/test_halide_android.py tests/test_halide_generators.py -q
.venv/bin/python -m pytest tests/test_photo_params.py tests/test_runtime_api.py -q
.venv/bin/python -m compileall src/spektrafilm/gpu src/spektrafilm/halide src/spektrafilm/runtime -q
```

预期分类：

- 如果 Gradle 能解析 Android 依赖，`testDebugUnitTest` 应该通过。
- 如果 AGP 在原生构建前需要已安装的 NDK 且本地不存在 NDK，`assembleDebug` 预期会在本地失败。该失败必须归类为缺少本地工具链失败，而非代码成功。
- 由于未安装 Android NDK，Halide generator 的 Android 交叉编译在本地被跳过。

## 风险和缓解措施

- **错误的 Chaquopy 假设：** 不添加 Chaquopy。记录确切的 wheel 不匹配情况，仅在依赖集发生变化或构建了原生 wheel 时才保留未来路径。
- **AGP/Kotlin/Compose 版本不匹配：** 使用官方 AGP 9.2 / Gradle 9.4.1 指引，来自官方 AGP 示例的 Kotlin 2.3.21，以及来自官方 Compose 文档的 Compose BOM 2026.05.00。
- **缺少 NDK：** 保持原生代码真实，但如果无法运行则将 Android 原生构建验证归类为被缺少 NDK 阻塞。提供确切的安装和构建命令。
- **虚假处理：** 将任何非原生回退诊断路径命名为仅用于诊断。UI 文案和文档必须声明原生 Spektrafilm 渲染尚未实现。
- **DirectByteBuffer 误用：** 原生代码必须验证 direct buffer、字节容量、维度和操作边界。Kotlin 必须使用 `ByteOrder.nativeOrder()` 分配 buffer。
- **不可取消的预览：** ViewModel 预览必须使用防抖 `StateFlow` 和 `flatMapLatest`/job 取消，以便快速滑块编辑取消过时的工作。
- **全分辨率内存复制：** 桥接模型必须区分预览和全分辨率请求，并保持 float32 buffer 分配明确。
- **桌面端回归：** 除与行为无关的文档/测试外，不编辑桌面端运行时模块。运行有针对性的 Python 测试。
- **文档过度声称：** 状态文档和研究修订必须区分"基础框架存在"和"Android Spektrafilm 渲染器存在"。
- **脏工作区：** 将更改限定在 `android/`、直接相关的文档和测试范围内。不删除或重写无关的未跟踪文件。

## 100% 置信度退出检查

最终回复前，重新检查：

- Chaquopy 声明与官方 Chaquopy 文档和包索引一致。
- Android Gradle/Kotlin/Compose 版本与官方指引匹配。
- 原生构建状态以确切的本地工具链事实报告。
- 没有将不支持的代码路径描述为真正的 Spektrafilm 处理。
- 单元测试覆盖参数序列化、ViewModel 取消/状态、撤销/重做和处理器合约。
- 文档和代码对当前能力和缺失部分的描述一致。
- 现有桌面端行为除文档和验证外保持不变。
