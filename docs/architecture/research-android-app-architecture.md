# Android App Architecture Research — Spektrafilm

> Research document for designing an Android photo editing / film simulation app.
> Date: 2026-05-28

---

## 2026-05-28 Implementation Amendment

The architecture recommendation remains valid and is now partially implemented
under `android/`: Compose UI, immutable UI state, `SpektrafilmViewModel`,
`StateFlow`, debounced/cancellable preview processing, export state, undo/redo,
and a direct `ByteBuffer` processor boundary.

The current native path is diagnostic only. It validates JNI/direct-buffer
plumbing and does not perform real Spektrafilm film/print/scan rendering. See
`docs/dev/android-port-status-20260528.md` for exact validation and gaps.

## 1. Photo Editing App Architectures on Android

### 1.1 How Commercial Apps Structure Their Pipelines

**Snapseed** (Google)
- C++ NDK core for all image processing, JNI bridge to Kotlin/Java UI
- Non-destructive, stack-based editing model (similar to adjustment layers)
- Custom HDR/tonemapping pipeline, proprietary "U Point" selective adjustment tech
- All processing is CPU-based (no GPU shaders) — prioritizes predictability over raw speed

**Adobe Lightroom Mobile**
- Adobe Camera Raw (ACR) engine ported to mobile via shared C++ codebase
- Cloud-synced, non-destructive editing: stores XMP parametric metadata, re-renders on demand
- Pipeline: RAW decode → demosaic → lens correction → tone mapping → local adjustments → export
- Uses Adobe Sensei (on-device ML) for masking, subject detection, auto-tones

**VSCO**
- GPU-accelerated shader-based pipeline (OpenGL ES, moving to Vulkan)
- Preset-driven architecture: film emulation LUTs applied as GPU shader passes
- Pipeline: capture → decode → LUT application → grain/film effects → export
- Key insight: LUT application on GPU is essentially a texture lookup — very fast

### 1.2 Common Architectural Patterns (2025–2026)

1. **GPU-first processing** — Vulkan compute shaders for pixel-level work, OpenGL ES for composition
2. **Non-destructive editing** — store parameters only, re-render on demand
3. **Hybrid Kotlin + C++ (NDK)** — Kotlin for UI/ViewModel, C++ for hot processing loops
4. **On-device ML** — TFLite / NNAPI for masks, segmentation, auto-enhance
5. **Kotlin coroutines Flow** — reactive pipeline that can be cancelled on parameter change

### 1.3 Real-time Preview vs Batch Processing

| Aspect | Real-time Preview | Batch / Export |
|--------|------------------|----------------|
| Resolution | Downscaled (1–2 MP) | Full resolution |
| Precision | float16 or uint8 LUT | float32 |
| Latency budget | < 16ms per frame | No hard limit |
| Processing | GPU shaders | CPU or tiled GPU |
| Architecture | RenderEffect / AGSL | Coroutine + Dispatchers.Default |

**Pattern: Dual-path pipeline**

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

The preview path renders a downscaled version immediately; the full-resolution render runs in the background and replaces the preview when done. This is the same pattern spektrafilm already uses with `simulate_preview` vs `simulate`.

---

## 2. Android Image Processing Best Practices

### 2.1 Memory Management for Large Images

**The problem**: A 4000×3000 image at float32 with 3 channels = 144 MB. Android's per-app memory limit is typically 256–512 MB. Two copies = OOM.

**Bitmap allocation limits**:
- Android `Bitmap` uses native memory (post-API 26), not Java heap
- But `Bitmap.Config.ARGB_8888` is 4 bytes/pixel (uint8 per channel) — only 48 MB for 4000×3000
- For float32 processing, you need off-heap buffers, not Bitmaps

**Recommended allocation strategies**:

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

**Memory budget for spektrafilm on Android**:

| Image size | ARGB_8888 (Bitmap) | float32 × 3ch | float32 × 4ch |
|-----------|-------------------|---------------|---------------|
| 2000×1500 | 12 MB | 36 MB | 48 MB |
| 4000×3000 | 48 MB | 144 MB | 192 MB |
| 6000×4000 | 96 MB | 288 MB | 384 MB |

**Strategy**: The pipeline must use tiling for images > ~2000×1500 on mobile. Spektrafilm already has `tiled_processing()` in `gpu/backend.py` — this pattern translates directly.

### 2.2 Allocation Lifecycle

```
Load (Bitmap)
    → copyPixelsToBuffer(ByteBuffer)     // convert to raw float
    → NativeProcessing (NDK/Halide)       // float32 in native memory
    → copyPixelsFromBuffer(ByteBuffer)    // back to Bitmap
    → Display (ImageView / Compose Canvas)
```

Key rules:
- **Never hold more than one full-resolution float32 buffer at a time**
- **Use `Bitmap.Config.HARDWARE`** for display-only bitmaps (stays in GPU memory)
- **Pool ByteBuffers** — reuse across frames instead of allocating/freeing
- **Explicit cleanup** — `HardwareBuffer.close()`, `ByteBuffer` becomes eligible for GC

### 2.3 Threading Model

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

### 2.4 RenderEffect / RenderNode for Real-time Filters (API 31+)

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

**AGSL (Android Graphics Shading Language, API 33+)**: Android's replacement for RenderScript. Write custom GPU shaders in a GLSL-like language that runs on the Android GPU:

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

**Limitation**: AGSL/RenderEffect are great for preview-quality effects but can't express the full spektrafilm spectral pipeline (trilinear 3D LUTs, spectral density curves, etc.).

---

## 3. Halide on Mobile

### 3.1 Halide's Android Support

Halide officially supports Android as a target OS. From the Halide README:

- **Target triples**: `arm-64-android`, `arm-32-android`, `x86-64-android`, `x86-32-android`
- **AOT compilation**: Generates `.a` static libraries + `.h` headers callable from C/NDK
- **NEON auto-vectorization**: `vectorize(x, 8)` maps directly to NEON SIMD intrinsics on ARM
- **Vulkan compute** (beta): Can target Vulkan compute shaders on Android
- **Autoscheduler**: `Adams2019` autoscheduler can optimize for mobile ARM targets

Spektrafilm already has:
- `halide/android.py` — Android target mapping and CMake `add_halide_library()` rendering
- `generators/CMakeLists.txt` — CMake config with `TARGET` variable override for cross-compilation
- 4 generator C++ files producing 10 AOT-compiled kernels

### 3.2 Cross-Compilation Setup

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

The generated `.a` and `.h` files are linked into an Android shared library (`.so`) via NDK:

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

### 3.3 JNI Bridge Pattern

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

### 3.4 Google's Use of Halide in Pixel Camera

Google uses Halide extensively in the Pixel camera ISP (Image Signal Processor) pipeline:

- **HDR+ pipeline**: Multi-frame merge, denoising, tonemapping — all written in Halide
- **Night Sight**: Long-exposure stacking and noise reduction via Halide
- **Super Res Zoom**: Multi-frame super-resolution using Halide pipelines
- **Autoscheduler**: Google developed the Adams2019 autoscheduler (now included in Halide) specifically to auto-tune these mobile pipelines

Key insight from Google's experience: **Halide's separation of algorithm from schedule is critical for mobile**. The same algorithm can be scheduled differently for:
- ARM big.LITTLE cores (different tile sizes for big vs LITTLE)
- Different memory hierarchies (L1/L2 cache sizes vary across SoCs)
- Different NEON widths (128-bit on ARM64, 64-bit on ARM32)

### 3.5 Performance Expectations

Based on published benchmarks and Halide's design:

| Operation | Hand-written NEON | Halide (autoscheduled) | Notes |
|-----------|-------------------|----------------------|-------|
| 3×3 box filter | ~1.0× (baseline) | 2–4× | Halide fuses with adjacent stages |
| Trilinear 3D LUT (64³) | ~1.0× | 1.5–3× | Tiling + prefetch |
| Matrix multiply (3×3) | ~1.0× | ~1.0× | Simple enough that NEON is already optimal |
| Multi-stage pipeline (5+ stages) | ~1.0× | 3–10× | **Fusion is where Halide shines** |

The biggest win is **inter-stage fusion**: when you chain CCTF decode → density → light → CCTF encode, Halide can fuse adjacent stages so intermediate results stay in registers rather than being written to memory. On a 4000×3000 image, this can save hundreds of MB of memory traffic.

---

## 4. App Architecture Patterns

### 4.1 Recommended: MVVM + Jetpack Compose + Coroutines Flow

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

### 4.2 Processing Pipeline as Kotlin Flow

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

### 4.3 Undo/Redo Stack for Non-destructive Editing

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

### 4.4 Image Pipeline with Cancellation

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

## 5. Distribution and Packaging

### 5.1 APK Size Considerations

| Component | Size estimate | Notes |
|-----------|--------------|-------|
| Kotlin/Java code | 2–5 MB | Compressed in APK |
| Halide AOT `.a` libraries (arm64-v8a) | 1–3 MB per generator × 10 | Compressed; static linking reduces final .so |
| Combined `libspektrafilm_native.so` | 3–8 MB | After linking + stripping |
| Film stock data (profiles, LUTs) | 5–20 MB | Depends on bundled stocks |
| ICC profiles | 1–2 MB | |
| **Total APK (arm64 only)** | **15–40 MB** | |
| **Total AAB (all ABIs)** | **30–80 MB** | Before ABI split |

### 5.2 Android App Bundle (AAB) for ABI Splits

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

With ABI splits enabled, users with arm64-v8a devices only download the arm64 `.so` — halving the effective download size.

### 5.3 Minimum SDK Version

| API Level | Android Version | Relevance |
|-----------|----------------|-----------|
| 24 (N) | 7.0 | HEIC support via `ImageDecoder`, `ByteBuffer` improvements |
| 26 (O) | 8.0 | `HardwareBuffer`, `ImageReader` improvements, native memory Bitmap |
| 28 (P) | 9.0 | HEIC encoding, `ImageDecoder` |
| 31 (S) | 12 | `RenderEffect`, AGSL shaders |
| 33 (T) | 13 | Full AGSL, improved `HardwareBuffer` |
| 34 (U) | 14 | `CameraX` RGBA_FP32 output |

**Recommendation: minSdk = 26 (Android 8.0)**

- `HardwareBuffer` (API 26) is essential for zero-copy GPU↔CPU image sharing
- 95%+ of active Android devices are on API 26+
- API 24 support would require fallback paths for `HardwareBuffer`

### 5.4 Play Store Requirements for Photo Apps

- **Permissions**: `READ_MEDIA_IMAGES` (API 33+) or `READ_EXTERNAL_STORAGE` (API ≤ 32)
- **Photo picker**: Google recommends using the built-in photo picker (`PickVisualMedia`) instead of storage permissions
- **Privacy policy**: Required if app accesses photos
- **Data safety**: Must declare what data the app collects/shares
- **64-bit requirement**: All native code must include arm64-v8a (mandatory since 2019)
- **Target API level**: Must target API 34+ for new apps (as of Aug 2024)

---

## 6. Concrete Architecture Proposal for Spektrafilm Android

### 6.1 Layer Diagram

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

### 6.2 Key Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| UI framework | Jetpack Compose | Modern, declarative, excellent animation support for sliders |
| Architecture | MVVM + StateFlow | Standard Android pattern, good Compose integration |
| Processing engine | C++ via NDK + Halide AOT | Reuses existing generators, float32 precision, NEON auto-vectorization |
| Memory management | Direct ByteBuffer + pooling | Off-heap, no GC pressure, compatible with JNI |
| Preview rendering | Downscaled to 1024px max | < 50ms per frame on mid-range devices |
| Full-res rendering | Tiled, coroutine-based | Reuse spektrafilm's tiling pattern, cancellation support |
| minSdk | 26 | HardwareBuffer + 95%+ device coverage |
| Distribution | AAB with ABI splits | Minimizes download size |

### 6.3 What Needs to Be Built

1. **C++ Pipeline Port** — Rewrite `SimulationPipeline` in C++, calling Halide AOT kernels
2. **JNI Bridge** — ByteBuffer-based interface between Kotlin and C++
3. **Data Format Port** — Film stock profiles (`.json`/`.yaml`) need C++ parser
4. **Kotlin UI** — Compose screens for editing, presets, export
5. **CI/CD** — CMake cross-compilation for Android in the build pipeline

### 6.4 What Can Be Reused Directly

- All 10 Halide AOT generators (just recompile with `-DTARGET=arm-64-android`)
- The pipeline stage architecture (filming → printing → scanning)
- The tiled processing pattern from `gpu/backend.py`
- The parameter schema (`RuntimePhotoParams`) as a serialization format
- Film stock profile data files

---

## 7. References

- [Halide Language](https://halide-lang.org/) — Official Halide site
- [Halide GitHub](https://github.com/halide/Halide) — Source, tutorials, examples
- [Halide AOT Compilation Tutorial](https://halide-lang.org/tutorials/tutorial_lesson_10_aot_compilation_generate.html) — Lesson 10
- [Halide Cross-Compilation Tutorial](https://halide-lang.org/tutorials/tutorial_lesson_11_cross_compilation.html) — Lesson 11
- [Halide GPU Tutorial](https://halide-lang.org/tutorials/tutorial_lesson_12_using_the_gpu.html) — Lesson 12
- [Halide Adams2019 Autoscheduler Paper](https://halide-lang.org/papers/autoscheduler2019.html) — SIGGRAPH 2019
- [Android HardwareBuffer](https://developer.android.com/ndk/reference/group/a-hardware-buffer) — NDK reference
- [Android RenderEffect](https://developer.android.com/reference/android/graphics/RenderEffect) — API 31+
- [Android AGSL Shaders](https://developer.android.com/develop/ui/compose/graphics/agsl) — Compose graphics
- [Jetpack Compose Architecture](https://developer.android.com/topic/architecture) — Google's guide
- [CameraX ImageAnalysis](https://developer.android.com/media/camera/camerax) — Camera integration
- Spektrafilm codebase: `src/spektrafilm/halide/android.py`, `generators/CMakeLists.txt`
