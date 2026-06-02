> 这是英文原文的中文翻译。权威版本请参考英文原文。

# Halide Android 移植计划

**日期：** 2026-05-28
**状态：** Android 应用/JNI 基础已存在。尚未发布完整渲染器、APK 产物或设备端 Halide 执行。

---

## 2026-05-28 实施修订

之前"JNI 尚未启动"和"Kotlin UI 尚未启动"的章节已过时。
本仓库现已包含 `android/` 应用基础，具备 Compose UI、ViewModel/StateFlow 状态管理、处理器契约以及 JNI/C++ 诊断桥接源码。JNI 桥接层有意设计为最小化且无占位符：它检查直接缓冲区地址/容量处理并暴露自检/版本方法，但不链接 Halide 内核或实现 Spektrafilm 渲染。

Android NDK 交叉编译在本地尚未验证通过，因为 SDK 没有包含完整 NDK（缺少 `build/cmake/android.toolchain.cmake`）。在安装 `ndk;28.2.13676358` 之前，`assembleDebug` 会因 NDK 预检失败而报错。详见 `docs/dev/android-port-status-20260528.md`。

## 1. 当前状态

### 1.1 Python JIT 后端 — 已完成

- 67/67 个 Halide 相关测试在本地主机上全部通过（`halide>=21,<22`，Python 3.13）
- `src/spektrafilm/gpu/halide_backend.py` 中有 12 个经过验证的 JIT 内核
- 所有内核均通过 NumPy 参考实现验证，容差为 `atol=1e-5..1e-6`
- 完整内核目录见 `docs/dev/halide-backend-implementation.md`

### 1.2 C++ AOT 生成器 — 源码存在，构建已验证

`src/spektrafilm/generators/` 中存在四个生成器源文件：

| 源文件 | 生成器数量 | 内核 |
|------------|-----------|---------|
| `spectral_generator.cpp` | 3 | density_to_light, light_to_raw, compute_density_spectral |
| `filter_generator.cpp` | 2 | gaussian_blur_fir, gaussian_blur_iir |
| `color_generator.cpp` | 3 | cctf_encode, cctf_decode, highlight_boost |
| `lut_generator.cpp` | 2 | interp_1d, lut_2d_cubic |

**总计：10 个生成器产生 10 个 AOT 编译内核。**

CMake 配置（`CMakeLists.txt`）定义了全部 10 个 `add_halide_library()` 目标和一个聚合的 `spektrafilm_halide_all` 接口库。构建默认使用 `host` 目标；可通过 `-DTARGET=arm-64-android` 覆盖以进行 Android 交叉编译。本地验证构建了完整的主机 AOT 目标集，并包含源码级防护，确保 `density_to_light` 按波长索引密度而非意外复用波长 0。

这**不**证明 Android NDK 交叉编译或 Android 设备运行时可行。这些仍属于未来的独立验证节点。

### 1.3 Android JNI — 尚未启动（基础已铺设 - 见顶部修订）

尚无 JNI 封装、Android NDK 项目或 `.so` 打包。

### 1.4 Kotlin UI — 尚未启动（基础已铺设 - 见顶部修订）

尚无 Kotlin/Compose 代码。

---

## 2. AOT 契约层

C++ 生成器在源码层面镜像了 Python JIT 公式。它们使用 Halide 的 C++ Generator API（`Halide::Generator<>` 基类），并通过 CMake 的 `add_halide_library()` 进行编译。当前验证证明了主机配置、生成器编译和主机 AOT 产物生成；尚未针对 NumPy 一致性测试用例执行生成的 C ABI。

### 2.1 Generator API 模式

每个生成器遵循相同结构：

```cpp
class MyKernelGenerator : public Generator<MyKernelGenerator> {
public:
    Input<Buffer<float, 3>> input{"input"};
    Input<float> param{"param"};
    Output<Buffer<float, 3>> output{"output"};

    void generate() {
        Var x("x"), y("y"), c("c");
        // ... 内核逻辑 ...
        output(x, y, c) = /* 表达式 */;
    }

    void schedule() {
        if (auto_schedule) return;
        // ... 手动调度 ...
    }
};

HALIDE_REGISTER_GENERATOR(MyKernelGenerator, my_kernel)
```

`add_halide_library()` CMake 函数：
1. 编译生成器可执行文件（主机端，构建时）
2. 运行生成器为目标平台生成 `.a`（静态库）+ `.h`（头文件）
3. 通过 `target_link_libraries()` 注册链接目标

### 2.2 源码级公式映射

生成的源码旨在匹配以下 Python JIT 公式。通过生成的 C ABI 进行运行时一致性验证是未来的测试节点。

**density_to_light：** `output(c, y, w) = fast_exp(-density(c, y, w) * ln(10)) * illuminant(w, c)`

**light_to_raw：** `output(c, y, s) = sum_k light(c, y, k) * sensitivity(k, s)`（RDom 遍历 81）

**compute_density_spectral：** `output(c, y, w) = sum_k density_cmy(c, y, k) * channel_density(w, k)`（RDom 遍历 3）

**cctf_encode：** `select(v <= threshold, linear_slope * v, alpha * fast_pow(v, 1/gamma) - (alpha - 1))`

**cctf_decode：** `select(v <= linear_slope * threshold, v / linear_slope, fast_pow((v + (alpha - 1)) / alpha, gamma))`

**highlight_boost：** `select(v < threshold, v * scale, pivot + (v - pivot) * fast_exp(-(v - pivot) * scale))`

**gaussian_blur_fir：** 两遍可分离卷积，使用 `mirror_interior` 边界条件，`RDom` 遍历核宽度。

**gaussian_blur_iir：** Young-van Vliet 4 阶递归滤波器（因果 + 反因果，水平 + 垂直方向）。这是一个完整的 Halide IIR 实现，使用 `RDom` 更新定义——不同于 Python JIT 后端，后者因 Python JIT 无法表达递归 Func 而回退到 NumPy。

**interp_1d：** 线性插值，包含等间距快速路径和 `clamp` 边界。

**lut_2d_cubic：** Mitchell-Netravali（B=1/3，C=1/3）4x4 双三次插值，`clamp` 边界。

### 2.3 CMake 目标配置

```cmake
# 默认为 host；通过 -DTARGET=arm-64-android 覆盖
if(NOT DEFINED TARGET)
    set(TARGET host)
endif()

# 每个 add_halide_library() 调用为 ${TARGET} 生成 .a + .h
add_halide_library(density_to_light FROM spectral_generator ...)
# ...（共 10 个）

# 聚合便捷目标
add_library(spektrafilm_halide_all INTERFACE)
target_link_libraries(spektrafilm_halide_all INTERFACE
    density_to_light light_to_raw compute_density_spectral
    gaussian_blur_fir gaussian_blur_iir
    cctf_encode cctf_decode highlight_boost
    interp_1d lut_2d_cubic)
```

### 2.4 构建命令（主机验证）

```bash
cmake -S src/spektrafilm/generators \
      -B /tmp/spektrafilm-halide-generators-check \
      -DHalide_DIR=/path/to/halide/lib/cmake/Halide \
      -DTARGET=host
cmake --build /tmp/spektrafilm-halide-generators-check
```

Android 交叉编译：
```bash
cmake .. -DTARGET=arm-64-android \
         -DCMAKE_TOOLCHAIN_FILE=$ANDROID_NDK/build/cmake/android.toolchain.cake \
         -DANDROID_ABI=arm64-v8a \
         -DHalide_DIR=/path/to/halide-android/lib/cmake/Halide
```

---

## 3. 生成器未覆盖的操作

以下操作**未**作为 AOT 生成器实现：

| 操作 | 原因 |
|-----------|--------|
| `rgb_to_xyz`（3x3 矩阵乘法） | 由通用 `einsum`/`matmul` 覆盖——如有需要可添加生成器 |
| `apply_lut_trilinear_3d` | 存在于 Python JIT 中，尚未移植到 C++ 生成器 |
| `generate_grain_buffer` | RNG——无法在 Halide 中表达。需要 C++ 预处理 |
| FFT 卷积 | 需要外部 FFT 库或空间域分解 |
| 所有非内核操作 | 逐元素数学运算、归约——由 NumPy（Python）或 C++ 循环处理 |

---

## 4. 后续步骤（未来工作，非本次会话）

### 4.1 Android NDK 项目设置

- 创建 `android/` 目录，包含 `build.gradle`、`CMakeLists.txt`
- 配置 NDK 工具链，目标为 `arm64-v8a`
- 为 Android 主机构建 Halide（或使用预构建的 Halide Android 发行版）
- 为 `arm-64-android` 交叉编译 10 个生成器
- 将生成的 `.a` 文件链接为共享库（`libspektrafilm.so`）

### 4.2 JNI 封装层

- `SpektrafilmEngine` C++ 类封装整个流水线
- JNI 方法：`processImage(ByteBuffer, Params)`、`setProfile(String)`、`getVersion()`
- 直接 ByteBuffer 传递实现零拷贝图像 I/O
- 参数编组通过扁平 C 结构体（匹配 `params_schema.py` dataclass）

### 4.3 Kotlin 集成

- Jetpack Compose UI 用于参数调整
- CameraX 集成用于实时预览
- MediaStore 用于导入/导出
- 从捆绑资源中选择配置文件

### 4.4 设备测试矩阵

- Pixel 6/7/8（ARM Cortex-A 系列 + Mali GPU）
- Samsung Galaxy S 系列（Exynos + Mali）
- OnePlus（Snapdragon + Adreno）
- 验证 float32 精度与主机 Python 输出的一致性（`atol=1e-5`）

---

## 5. 明确警告

**尚未发布任何 JNI、APK 或设备端 Android 代码。**

已有的：
- Python JIT/后端基础：在本地主机上通过 67/67 个 Halide 相关测试全面验证
- C++ AOT 生成器源码：4 个文件中共 10 个生成器，CMake 构建系统已配置
- CMake 可生成主机 `.a`/`.h` 文件（Android 交叉编译尚未验证）

尚不存在的：
- Android NDK 项目
- JNI 绑定
- Kotlin/Jetpack Compose UI
- 设备端测试
- Vulkan 计算调度
- APK 或应用包

---

## 附录：完整可移植性分析

如需逐模块的可移植性评估、依赖替换映射和风险分析，请参阅下方的早期分析文档（2026-05-27）。

---

### A. 依赖图

```
输入 RGB 图像
       |
       v
[预处理] ─── auto_exposure, crop_and_rescale
       |
       v
[FilmingStage.expose]
  ├─ rgb_to_film_raw ─── spectral_upsampling (LUT)
  ├─ boost_highlights ─── 分段指数
  ├─ diffusion_filter_um ─── FFT 或高斯混合
  ├─ gaussian_blur_um ─── FIR/IIR 高斯
  ├─ halation_um ─── 高斯 + 指数模糊
  └─ log10
       |
       v
[FilmingStage.develop]
  ├─ interpolate_exposure_to_density ─── 1D 插值
  ├─ dir_couplers ─── einsum + 模糊
  └─ grain ─── 随机（RNG + 模糊）
       |
       v
[PrintingStage.expose]
  ├─ compute_density_spectral ─── einsum
  ├─ density_to_light ─── 10^(-density) * illuminant
  ├─ light_to_raw ─── einsum
  └─ diffusion_filter_um + log10
       |
       v
[PrintingStage.develop]
  └─ interpolate_exposure_to_density
       |
       v
[ScanningStage.scan]
  ├─ cmy_to_log_xyz ─── density_spectral → light → XYZ
  ├─ black_white_correction
  ├─ glare ─── 随机
  ├─ xyz_to_rgb ─── 3x3 矩阵
  ├─ gaussian_blur + unsharp_mask
  └─ cctf_encoding ─── sRGB/ProPhoto/BT.2020
       |
       v
输出 RGB 图像
```

### B. 操作可移植性总结

| 操作类别 | 可移植性 | Halide 适配度 |
|----------------|-------------|------------|
| 逐元素数学运算（exp, log, pow, select） | 优秀 | Halide 原生 |
| 矩阵乘法（3x3, einsum） | 优秀 | Halide 归约 |
| 1D 插值 | 优秀 | Halide + clamp |
| 2D/3D LUT 采样 | 优秀 | Halide + lookup |
| 高斯模糊（FIR） | 优秀 | Halide convolve |
| 高斯模糊（IIR） | 良好 | Halide scan（仅 C++ 生成器） |
| FFT 卷积 | 中等 | 外部 FFT 或空间域分解 |
| 随机（RNG） | 差 | 预处理 C++ RNG |
| 色彩科学初始化 | 不适用 | 预计算静态数据 |
| 文件 I/O | 不适用 | Android 原生 API |

### C. 风险：胶片颗粒随机性

Halide 是确定性的——无法表达 RNG。颗粒模型需要两遍处理：在 C++ 中生成随机偏差（`<random>` 或 xoroshiro128+），存储到 Halide Buffer 中，然后输入颗粒计算流水线。现有的 `fast_stats.py` Numba 实现提供了参考算法。

### D. 风险：数值精度

ARM NEON float32 符合 IEEE 754 标准。项目的 `atol=1e-6` 容差应当可以实现。需在目标设备上验证。

### E. 外部库替换

| 依赖 | Android 替代方案 |
|-----------|-------------------|
| colour-science | 预计算矩阵 + 静态光谱数据数组 |
| scipy（interpolate, FFT） | 原生插值 + FFT 库（FFTW/Ne10） |
| Numba | Halide 生成器（已完成） |
| opt-einsum | Halide 归约或 C++ 循环 |
| matplotlib, napari | 跳过（仅 GUI 用途） |
| qtpy/PySide6 | Kotlin/Jetpack Compose |
| Pillow | Android Bitmap API 或 stb_image |
| OpenImageIO | OpenEXR 原生 |
| rawpy | LibRaw（已为原生 C++） |
