# Android 应用架构研究 — Spektrafilm

> 这是英文原文的中文翻译。权威版本请参考英文原文。

> 设计 Android 照片编辑 / 胶片模拟应用的研究文档。
> 日期：2026-05-28

---

## 2026-05-28 实施补充说明

架构建议仍然有效，目前已在 `android/` 下部分实现：
Compose UI、不可变 UI 状态、`SpektrafilmViewModel`、
`StateFlow`、防抖/可取消的预览处理、导出状态、撤销/重做，
以及基于直接 `ByteBuffer` 的处理器边界。

当前的原生路径仅用于诊断。它验证了 JNI/直接缓冲区的
管道连接，但并未执行真正的 Spektrafilm 胶片/打印/扫描渲染。请参阅
`docs/dev/android-port-status-20260528.md` 了解具体的验证情况和差距。

## 1. Android 上的照片编辑应用架构

### 1.1 商业应用如何构建其处理管线

**Snapseed** (Google)
- C++ NDK 核心负责所有图像处理，通过 JNI 桥接 Kotlin/Java UI
- 非破坏性、基于图层栈的编辑模型（类似调整图层）
- 自定义 HDR/色调映射管线，专有的 "U Point" 局部调整技术
- 所有处理均基于 CPU（无 GPU 着色器）——优先考虑可预测性而非原始速度

**Adobe Lightroom Mobile**
- Adobe Camera Raw (ACR) 引擎通过共享 C++ 代码库移植到移动端
- 云端同步的非破坏性编辑：存储 XMP 参数化元数据，按需重新渲染
- 管线：RAW 解码 → 去马赛克 → 镜头校正 → 色调映射 → 局部调整 → 导出
- 使用 Adobe Sensei（设备端 ML）进行蒙版、主体检测、自动色调调整

**VSCO**
- 基于 GPU 加速着色器的管线（OpenGL ES，正在向 Vulkan 迁移）
- 预设驱动架构：胶片模拟 LUT 作为 GPU 着色器通道应用
- 管线：拍摄 → 解码 → LUT 应用 → 颗粒/胶片效果 → 导出
- 关键洞察：在 GPU 上应用 LUT 本质上是纹理查找——非常快速

### 1.2 常见架构模式（2025-2026）

1. **GPU 优先处理** — Vulkan 计算着色器用于像素级工作，OpenGL ES 用于合成
2. **非破坏性编辑** — 仅存储参数，按需重新渲染
3. **混合 Kotlin + C++ (NDK)** — Kotlin 用于 UI/ViewModel，C++ 用于热处理循环
4. **设备端 ML** — TFLite / NNAPI 用于蒙版、分割、自动增强
5. **Kotlin 协程 Flow** — 响应式管线，可在参数变更时取消

### 1.3 实时预览与批处理

| 方面 | 实时预览 | 批处理 / 导出 |
|--------|------------------|----------------|
| 分辨率 | 缩小（1-2 MP） | 全分辨率 |
| 精度 | float16 或 uint8 LUT | float32 |
| 延迟预算 | 每帧 < 16ms | 无硬性限制 |
| 处理方式 | GPU 着色器 | CPU 或分块 GPU |
| 架构 | RenderEffect / AGSL | Coroutine + Dispatchers.Default |

**模式：双路径管线**

```
┌─────────────┐     ┌─────────────────┐     ┌──────────────┐
│ User adjusts │────▶│ Preview path     │────▶│ Quick update │
│ parameter    │     │ (downscaled,GPU) │     │ (< 16ms)     │
└─────────────┘     └─────────────────┘     └──────────────┘
                                                      │
                           ┌──────────────────────────┘
                           ▼
                    ┌─────────────────┐     ┌──────────────┐
                    │ Full-res path    │────▶│ Export result │
                    │ (tiled, float32) │     │ (async)      │
                    └─────────────────┘     └──────────────┘
```

预览路径立即渲染缩小版本；全分辨率渲染在后台运行，完成后替换预览。这与 spektrafilm 已经使用的 `simulate_preview` vs `simulate` 模式相同。

---

## 2. Android 图像处理最佳实践

### 2.1 大图像的内存管理

**问题**：一张 4000x3000 的图像以 float32 存储、3 个通道 = 144 MB。Android 每个应用的内存限制通常为 256-512 MB。两份副本 = OOM（内存溢出）。

**Bitmap 分配限制**：
- Android `Bitmap` 使用原生内存（API 26 之后），而非 Java 堆
- 但 `Bitmap.Config.ARGB_8888` 是每像素 4 字节（每通道 uint8）——4000x3000 仅需 48 MB
- 对于 float32 处理，需要使用堆外缓冲区，而非 Bitmap

**推荐的分配策略**：

```kotlin
// Option 1: Direct ByteBuffer (off-heap, GC-transparent)
val buffer = ByteBuffer.allocateDirect(
    width * height * 3 * 4  // 3 channels × float32
).order(ByteOrder.nativeOrder())

// Option 2: HardwareBuffer (API 26+, zero-copy GPU↔CPU sharing)
val hwBuffer = HardwareBuffer.create(
    width, height,
    HardwareBuffer.RGBA_FP16,  // or RGBA_8888
    1,  // layers
    HardwareBuffer.USAGE_GPU_SAMPLED_IMAGE or
        HardwareBuffer.USAGE_CPU_WRITE_OFTEN
)

// Option 3: NDK AHardwareBuffer (for native C++/Halide code)
// Accessed via NDK: AHardwareBuffer_lock/unlock for CPU access
// Can be imported as Vulkan texture or EGLImage for GPU access
```

**Spektrafilm 在 Android 上的内存预算**：

| 图像大小 | ARGB_8888 (Bitmap) | float32 x 3通道 | float32 x 4通道 |
|-----------|-------------------|---------------|---------------|
| 2000x1500 | 12 MB | 36 MB | 48 MB |
| 4000x3000 | 48 MB | 144 MB | 192 MB |
| 6000x4000 | 96 MB | 288 MB | 384 MB |

**策略**：在移动端，对于大于约 2000x1500 的图像，管线必须使用分块处理。Spektrafilm 已经在 `gpu/backend.py` 中有 `tiled_processing()`——此模式可以直接移植。

### 2.2 分配生命周期

```
Load (Bitmap)
    → copyPixelsToBuffer(ByteBuffer)     // convert to raw float
    → NativeProcessing (NDK/Halide)       // float32 in native memory
    → copyPixelsFromBuffer(ByteBuffer)    // back to Bitmap
    → Display (ImageView / Compose Canvas)
```

关键规则：
- **任何时候都不要持有超过一个全分辨率 float32 缓冲区**
- **使用 `Bitmap.Config.HARDWARE`** 用于仅显示的 Bitmap（保留在 GPU 内存中）
- **池化 ByteBuffers** — 跨帧复用，而非反复分配/释放
- **显式清理** — `HardwareBuffer.close()`，`ByteBuffer` 变为可被 GC 回收

### 2.3 线程模型

```kotlin
// Main thread: UI only
// Dispatchers.Default: CPU-heavy processing (matches thread pool to CPU cores)
// Dispatchers.IO: File I/O (load/save images)
// Custom single-thread dispatcher: Halide serial runtime (if needed)

class ImageProcessingViewModel : ViewModel() {
    private val _result = MutableStateFlow<ProcessingResult?>(null)
    val result: StateFlow<ProcessingResult?> = _result

    fun processImage(input: Bitmap, params: FilmParams) {
        viewModelScope.launch(Dispatchers.Default) {
            // Cancellation support: check isActive between pipeline stages
            ensureActive()
            val preprocessed = preprocess(input)

            ensureActive()
            val filmed = filmStage.process(preprocessed)

            ensureActive()
            val printed = printStage.process(filmed)

            _result.value = ProcessingResult(printed)
        }
    }
}
```

### 2.4 RenderEffect / RenderNode 用于实时滤镜（API 31+）

```kotlin
// RenderEffect lets you apply GPU-accelerated effects to any View
// Available: blur, color filter, shader effects (AGSL)
val blurEffect = RenderEffect.createBlurEffect(
    radiusX, radiusY, Shader.TileMode.CLAMP
)
val colorFilterEffect = RenderEffect.createColorFilterEffect(
    ColorMatrixColorFilter(colorMatrix)
)
val chainedEffect = RenderEffect.createChainEffect(blurEffect, colorFilterEffect)
imageView.setRenderEffect(chainedEffect)
```

**AGSL（Android Graphics Shading Language，API 33+）**：Android 对 RenderScript 的替代方案。使用类 GLSL 语言编写自定义 GPU 着色器，在 Android GPU 上运行：

```kotlin
val agslShader = RuntimeShader("""
    uniform float brightness;
    uniform shader input;
    half4 main(float2 coord) {
        half4 color = input.eval(coord);
        color.rgb *= brightness;
        return color;
    }
""")
agslShader.setFloatUniform("brightness", 1.5f)
```

**局限性**：AGSL/RenderEffect 非常适合预览质量的效果，但无法表达完整的 spektrafilm 光谱管线（三线性 3D LUT、光谱密度曲线等）。

---

## 3. Halide 在移动端的应用

### 3.1 Halide 的 Android 支持

Halide 官方支持 Android 作为目标操作系统。根据 Halide README：

- **目标三元组**：`arm-64-android`、`arm-32-android`、`x86-64-android`、`x86-32-android`
- **AOT 编译**：生成 `.a` 静态库 + `.h` 头文件，可从 C/NDK 调用
- **NEON 自动向量化**：`vectorize(x, 8)` 直接映射到 ARM 上的 NEON SIMD 内在函数
- **Vulkan 计算**（测试版）：可在 Android 上生成 Vulkan 计算着色器
- **自动调度器**：`Adams2019` 自动调度器可针对移动 ARM 目标进行优化

Spektrafilm 已经拥有：
- `halide/android.py` — Android 目标映射和 CMake `add_halide_library()` 渲染
- `generators/CMakeLists.txt` — CMake 配置，支持 `TARGET` 变量覆盖用于交叉编译
- 4 个生成器 C++ 文件，产出 10 个 AOT 编译的内核

### 3.2 交叉编译设置

```cmake
# Cross-compile for Android arm64
cmake -S src/spektrafilm/generators -B build-android \
    -DCMAKE_TOOLCHAIN_FILE=$ANDROID_NDK/build/cmake/android.toolchain.cmake \
    -DANDROID_ABI=arm64-v8a \
    -DANDROID_PLATFORM=android-24 \
    -DTARGET=arm-64-android \
    -DHalide_DIR=/path/to/halide-android/lib/cmake/Halide

cmake --build build-android
```

生成的 `.a` 和 `.h` 文件通过 NDK 链接到 Android 共享库（`.so`）中：

```cmake
# In the app's CMakeLists.txt
add_library(spektrafilm_native SHARED
    jni_bridge.cpp
)
target_link_libraries(spektrafilm_native
    PRIVATE density_to_light light_to_raw compute_density_spectral
            gaussian_blur_fir gaussian_blur_iir
            cctf_encode cctf_decode highlight_boost
            interp_1d lut_2d_cubic
)
```

### 3.3 JNI 桥接模式

```cpp
// jni_bridge.cpp
#include <jni.h>
#include <android/bitmap.h>
#include <HalideBuffer.h>
#include "density_to_light.h"

extern "C" JNIEXPORT void JNICALL
Java_com_spektrafilm_processing_NativePipeline_densityToLight(
    JNIEnv *env, jobject /* this */,
    jobject inputBuffer, jobject outputBuffer,
    jint width, jint height, jint channels
) {
    // Lock the AHardwareBuffer for CPU access
    void *inputPtr = env->GetDirectBufferAddress(inputBuffer);
    void *outputPtr = env->GetDirectBufferAddress(outputBuffer);

    // Wrap in Halide::Runtime::Buffer (zero-copy)
    Halide::Runtime::Buffer<float> halideInput(
        static_cast<float *>(inputPtr), channels, width, height);
    Halide::Runtime::Buffer<float> halideOutput(
        static_cast<float *>(outputPtr), channels, width, height);

    // Call the AOT-compiled pipeline
    density_to_light(halideInput, halideOutput);
}
```

### 3.4 Google 在 Pixel 相机中对 Halide 的使用

Google 在 Pixel 相机 ISP（图像信号处理器）管线中广泛使用 Halide：

- **HDR+ 管线**：多帧合并、降噪、色调映射——全部使用 Halide 编写
- **Night Sight（夜景模式）**：通过 Halide 实现长曝光堆叠和降噪
- **Super Res Zoom（超级分辨率变焦）**：使用 Halide 管线实现多帧超分辨率
- **自动调度器**：Google 开发了 Adams2019 自动调度器（现已包含在 Halide 中），专门用于自动调优这些移动管线

Google 经验中的关键洞察：**Halide 将算法与调度分离对移动端至关重要**。同一算法可以针对以下场景进行不同的调度：
- ARM big.LITTLE 核心（大核与小核使用不同的分块大小）
- 不同的内存层次结构（不同 SoC 的 L1/L2 缓存大小不同）
- 不同的 NEON 宽度（ARM64 为 128 位，ARM32 为 64 位）

### 3.5 性能预期

基于已发布的基准测试和 Halide 的设计：

| 操作 | 手写 NEON | Halide（自动调度） | 备注 |
|-----------|-------------------|----------------------|-------|
| 3x3 均值滤波 | ~1.0x（基线） | 2-4x | Halide 与相邻阶段融合 |
| 三线性 3D LUT (64³) | ~1.0x | 1.5-3x | 分块 + 预取 |
| 矩阵乘法 (3x3) | ~1.0x | ~1.0x | 足够简单，NEON 已是最优 |
| 多阶段管线（5+ 阶段） | ~1.0x | 3-10x | **融合是 Halide 的最大优势** |

最大的收益来自**跨阶段融合**：当您将 CCTF 解码 → 密度 → 光照 → CCTF 编码串联时，Halide 可以融合相邻阶段，使中间结果保留在寄存器中，而非写入内存。在 4000x3000 的图像上，这可以节省数百 MB 的内存带宽。

---

## 4. 应用架构模式

### 4.1 推荐方案：MVVM + Jetpack Compose + Coroutines Flow

```
┌─────────────────────────────────────────────────────────────┐
│                        UI Layer                              │
│  Jetpack Compose — @Composable functions                     │
│  Observe StateFlow from ViewModel                            │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ FilmSimScreen                                         │    │
│  │   ├── ImageViewer (displays processed result)        │    │
│  │   ├── ParameterSliders (exposure, grain, etc.)       │    │
│  │   ├── PresetSelector (film stock presets)            │    │
│  │   └── ExportButton                                   │    │
│  └─────────────────────────────────────────────────────┘    │
└────────────────────────┬────────────────────────────────────┘
                         │ StateFlow<UiState>
┌────────────────────────▼────────────────────────────────────┐
│                    ViewModel Layer                            │
│  FilmSimViewModel                                            │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ - params: MutableStateFlow<FilmParams>               │    │
│  │ - previewResult: StateFlow<Bitmap?>                  │    │
│  │ - fullResResult: StateFlow<ProcessingResult?>        │    │
│  │ - isProcessing: StateFlow<Boolean>                   │    │
│  │                                                      │    │
│  │ init {                                               │    │
│  │   params.debounce(50ms)                              │    │
│  │     .flatMapLatest { processPreview(it) }            │    │
│  │     .collect { previewResult.value = it }            │    │
│  │ }                                                    │    │
│  └─────────────────────────────────────────────────────┘    │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                   Domain Layer                                │
│  SpektrafilmNative (C++ via JNI)                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Pipeline: load → expose → develop → scan → export    │    │
│  │ Uses Halide AOT kernels for hot loops                │    │
│  │ Float32 throughout, tiled for large images           │    │
│  └─────────────────────────────────────────────────────┘    │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                    Data Layer                                 │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ FilmStockRepository (bundled profiles, user presets) │    │
│  │ ImageRepository (load/save, format conversion)       │    │
│  │ SettingsStore (DataStore / SharedPreferences)        │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 作为 Kotlin Flow 的处理管线

```kotlin
class FilmSimViewModel(
    private val processor: SpektrafilmProcessor
) : ViewModel() {

    data class UiState(
        val preview: Bitmap? = null,
        val isProcessing: FullResState = FullResState.Idle,
        val params: FilmParams = FilmParams.DEFAULT
    )

    sealed class FullResState {
        object Idle : FullResState()
        data class Processing(val progress: Float) : FullResState()
        data class Done(val uri: Uri) : FullResState()
        data class Error(val message: String) : FullResState()
    }

    private val _state = MutableStateFlow(UiState())
    val state: StateFlow<UiState> = _state.asStateFlow()

    // Preview job: cancels and restarts on every parameter change
    private var previewJob: Job? = null

    fun onParamChanged(key: String, value: Float) {
        val newParams = _state.value.params.withChange(key, value)
        _state.update { it.copy(params = newParams) }

        previewJob?.cancel()
        previewJob = viewModelScope.launch(Dispatchers.Default) {
            // Debounce rapid slider changes
            delay(50)

            val input = currentInputImage ?: return@launch
            val downscaled = processor.downscale(input, maxDimension = 1024)

            ensureActive()
            val result = processor.processPreview(downscaled, newParams)

            _state.update { it.copy(preview = result) }
        }
    }

    fun onExportRequested() {
        viewModelScope.launch(Dispatchers.Default) {
            _state.update { it.copy(isProcessing = FullResState.Processing(0f)) }

            try {
                val input = currentInputImage ?: return@launch
                val result = processor.processFullResolution(
                    input, _state.value.params
                ) { progress ->
                    _state.update { it.copy(isProcessing = FullResState.Processing(progress)) }
                }

                val uri = saveToDisk(result)
                _state.update { it.copy(isProcessing = FullResState.Done(uri)) }
            } catch (e: CancellationException) {
                throw e  // Don't swallow coroutine cancellation
            } catch (e: Exception) {
                _state.update { it.copy(isProcessing = FullResState.Error(e.message ?: "Unknown error")) }
            }
        }
    }
}
```

### 4.3 用于非破坏性编辑的撤销/重做栈

```kotlin
class EditHistory<T>(private val maxSize: Int = 50) {
    private val undoStack = ArrayDeque<T>()
    private val redoStack = ArrayDeque<T>()
    private var current: T? = null

    val canUndo: Boolean get() = undoStack.isNotEmpty()
    val canRedo: Boolean get() = redoStack.isNotEmpty()

    fun push(state: T) {
        current?.let { undoStack.addLast(it) }
        if (undoStack.size > maxSize) undoStack.removeFirst()
        current = state
        redoStack.clear()
    }

    fun undo(): T? {
        if (!canUndo) return null
        current?.let { redoStack.addLast(it) }
        current = undoStack.removeLast()
        return current
    }

    fun redo(): T? {
        if (!canRedo) return null
        current?.let { undoStack.addLast(it) }
        current = redoStack.removeLast()
        return current
    }
}

// In ViewModel:
private val history = EditHistory<FilmParams>()

fun onParamChanged(key: String, value: Float) {
    val newParams = _state.value.params.withChange(key, value)
    history.push(newParams)
    _state.update { it.copy(params = newParams) }
    triggerPreview(newParams)
}

fun onUndo() {
    history.undo()?.let { params ->
        _state.update { it.copy(params = params) }
        triggerPreview(params)
    }
}
```

### 4.4 带取消功能的图像管线

```kotlin
interface SpektrafilmProcessor {
    fun downscale(image: Bitmap, maxDimension: Int): Bitmap

    suspend fun processPreview(
        input: Bitmap,
        params: FilmParams
    ): Bitmap

    suspend fun processFullResolution(
        input: Bitmap,
        params: FilmParams,
        onProgress: (Float) -> Unit
    ): Bitmap
}

class NativeSpektrafilmProcessor : SpektrafilmProcessor {
    init {
        System.loadLibrary("spektrafilm_native")
    }

    // Native methods backed by Halide AOT kernels
    external fun nativeProcess(
        inputBuffer: ByteBuffer,
        outputBuffer: ByteBuffer,
        width: Int,
        height: Int,
        params: ByteArray  // serialized FilmParams
    )

    override suspend fun processPreview(
        input: Bitmap,
        params: FilmParams
    ): Bitmap = withContext(Dispatchers.Default) {
        val buffer = bitmapToDirectBuffer(input)
        val output = ByteBuffer.allocateDirect(buffer.capacity())
            .order(ByteOrder.nativeOrder())

        nativeProcess(buffer, output, input.width, input.height, params.serialize())

        directBufferToBitmap(output, input.width, input.height)
    }
}
```

---

## 5. 分发与打包

### 5.1 APK 大小考虑

| 组件 | 大小估计 | 备注 |
|-----------|--------------|-------|
| Kotlin/Java 代码 | 2-5 MB | 在 APK 中已压缩 |
| Halide AOT `.a` 库（arm64-v8a） | 每个生成器 1-3 MB x 10 | 已压缩；静态链接可减小最终 .so |
| 合并后的 `libspektrafilm_native.so` | 3-8 MB | 链接 + 去符号后 |
| 胶片库存数据（配置文件、LUT） | 5-20 MB | 取决于捆绑的胶片种类 |
| ICC 配置文件 | 1-2 MB | |
| **APK 总大小（仅 arm64）** | **15-40 MB** | |
| **AAB 总大小（所有 ABI）** | **30-80 MB** | ABI 拆分前 |

### 5.2 用于 ABI 拆分的 Android App Bundle (AAB)

```gradle
android {
    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"))
        }
    }

    bundle {
        language.enableSplit = true
        density.enableSplit = true
        abi.enableSplit = true  // Only deliver native libs for user's ABI
    }

    defaultConfig {
        ndk {
            abiFilters += listOf("arm64-v8a", "armeabi-v7a")
            // Skip x86/x86_64 for production (emulator-only)
        }
    }
}
```

启用 ABI 拆分后，arm64-v8a 设备的用户仅下载 arm64 `.so`——实际下载大小减半。

### 5.3 最低 SDK 版本

| API 级别 | Android 版本 | 相关性 |
|-----------|----------------|-----------|
| 24 (N) | 7.0 | 通过 `ImageDecoder` 支持 HEIC，`ByteBuffer` 改进 |
| 26 (O) | 8.0 | `HardwareBuffer`、`ImageReader` 改进、原生内存 Bitmap |
| 28 (P) | 9.0 | HEIC 编码、`ImageDecoder` |
| 31 (S) | 12 | `RenderEffect`、AGSL 着色器 |
| 33 (T) | 13 | 完整 AGSL、改进的 `HardwareBuffer` |
| 34 (U) | 14 | `CameraX` RGBA_FP32 输出 |

**建议：minSdk = 26（Android 8.0）**

- `HardwareBuffer`（API 26）对于零拷贝 GPU-CPU 图像共享至关重要
- 95% 以上的活跃 Android 设备运行在 API 26+
- 支持 API 24 将需要 `HardwareBuffer` 的回退路径

### 5.4 照片应用的 Play Store 要求

- **权限**：`READ_MEDIA_IMAGES`（API 33+）或 `READ_EXTERNAL_STORAGE`（API ≤ 32）
- **照片选择器**：Google 建议使用内置的照片选择器（`PickVisualMedia`），而非存储权限
- **隐私政策**：如果应用访问照片则为必需
- **数据安全**：必须声明应用收集/共享的数据
- **64 位要求**：所有原生代码必须包含 arm64-v8a（自 2019 年起强制要求）
- **目标 API 级别**：新应用必须以 API 34+ 为目标（自 2024 年 8 月起）

---

## 6. Spektrafilm Android 的具体架构方案

### 6.1 层级图

```
┌─────────────────────────────────────────────────────────────────┐
│  Jetpack Compose UI                                              │
│  FilmSimApp → NavHost → { EditScreen, PresetsScreen, ExportScreen }│
└──────────────┬──────────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────────┐
│  ViewModel Layer (Kotlin)                                        │
│  EditViewModel: StateFlow<UiState>, UndoRedo history             │
│  PresetsViewModel: film stock catalog                            │
│  ExportViewModel: resolution/format selection, progress          │
└──────────────┬──────────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────────┐
│  Processing Bridge (Kotlin + JNI)                                │
│  SpektrafilmProcessor: preview/full-res dispatch                 │
│  ByteBuffer pooling (direct, native byte order)                  │
│  Cancellation via coroutine Job                                  │
└──────────────┬──────────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────────┐
│  Native Layer (C++ via NDK)                                      │
│  SpektrafilmPipeline: mirrors Python SimulationPipeline           │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ FilmingStage   → expose (spectral LUT, density curves)     │  │
│  │ PrintingStage  → expose (paper, enlarger filters)          │  │
│  │ ScanningStage  → scan (CCD response, CCTF encoding)        │  │
│  └────────────────────────────────────────────────────────────┘  │
│  Halide AOT kernels: 10 compiled generators                      │
│  Tiled processing for images > 2MP                               │
└──────────────┬──────────────────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────────────────┐
│  Data Layer                                                      │
│  FilmStockRepository: bundled + user-created profiles            │
│  ImageIO: Bitmap ↔ float32 buffer conversion                     │
│  Preferences: DataStore for user settings                        │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 关键技术决策

| 决策 | 选择 | 理由 |
|----------|--------|-----------|
| UI 框架 | Jetpack Compose | 现代、声明式、对滑块有出色的动画支持 |
| 架构 | MVVM + StateFlow | 标准 Android 模式，与 Compose 良好集成 |
| 处理引擎 | C++ via NDK + Halide AOT | 复用现有生成器、float32 精度、NEON 自动向量化 |
| 内存管理 | Direct ByteBuffer + 池化 | 堆外、无 GC 压力、与 JNI 兼容 |
| 预览渲染 | 缩小至最大 1024px | 中端设备上每帧 < 50ms |
| 全分辨率渲染 | 分块、基于协程 | 复用 spektrafilm 的分块模式、支持取消 |
| minSdk | 26 | HardwareBuffer + 95%+ 设备覆盖 |
| 分发 | 带 ABI 拆分的 AAB | 最小化下载大小 |

### 6.3 需要构建的内容

1. **C++ 管线移植** — 用 C++ 重写 `SimulationPipeline`，调用 Halide AOT 内核
2. **JNI 桥接** — Kotlin 与 C++ 之间基于 ByteBuffer 的接口
3. **数据格式移植** — 胶片库存配置文件（`.json`/`.yaml`）需要 C++ 解析器
4. **Kotlin UI** — 用于编辑、预设、导出的 Compose 页面
5. **CI/CD** — 构建管线中 Android 的 CMake 交叉编译

### 6.4 可直接复用的内容

- 全部 10 个 Halide AOT 生成器（只需用 `-DTARGET=arm-64-android` 重新编译）
- 管线阶段架构（拍摄 → 打印 → 扫描）
- `gpu/backend.py` 中的分块处理模式
- 参数模式（`RuntimePhotoParams`）作为序列化格式
- 胶片库存配置数据文件

---

## 7. 参考资料

- [Halide Language](https://halide-lang.org/) — Halide 官方网站
- [Halide GitHub](https://github.com/halide/Halide) — 源码、教程、示例
- [Halide AOT Compilation Tutorial](https://halide-lang.org/tutorials/tutorial_lesson_10_aot_compilation_generate.html) — 第 10 课
- [Halide Cross-Compilation Tutorial](https://halide-lang.org/tutorials/tutorial_lesson_11_cross_compilation.html) — 第 11 课
- [Halide GPU Tutorial](https://halide-lang.org/tutorials/tutorial_lesson_12_using_the_gpu.html) — 第 12 课
- [Halide Adams2019 Autoscheduler Paper](https://halide-lang.org/papers/autoscheduler2019.html) — SIGGRAPH 2019
- [Android HardwareBuffer](https://developer.android.com/ndk/reference/group/a-hardware-buffer) — NDK 参考文档
- [Android RenderEffect](https://developer.android.com/reference/android/graphics/RenderEffect) — API 31+
- [Android AGSL Shaders](https://developer.android.com/develop/ui/compose/graphics/agsl) — Compose 图形
- [Jetpack Compose Architecture](https://developer.android.com/topic/architecture) — Google 指南
- [CameraX ImageAnalysis](https://developer.android.com/media/camera/camerax) — 相机集成
- Spektrafilm 代码库：`src/spektrafilm/halide/android.py`、`generators/CMakeLists.txt`
