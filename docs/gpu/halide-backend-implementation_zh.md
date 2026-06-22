> 这是英文原文的中文翻译。权威版本请参考英文原文。

# Halide 后端实现 — 已验证状态

**日期：** 2026-05-28
**状态：** 67/67 项 Halide 相关测试在主机上通过（Python JIT + CMake/AOT 基础）

---

## 1. 架构

Halide 后端位于 `src/spektrafilm/gpu/halide_backend.py`。它实现了 spektrafilm 其余部分使用的 `ArrayBackend` 协议，但将非内核运算（逐元素数学运算、规约运算）委托给 NumPy，同时通过 Halide Python 绑定对选定的热点内核进行 JIT 编译。

### 1.1 HalideBackend 类

```
class HalideBackend:
    name = "halide"
    supports_gpu = True
    precision = "float32"   # only float32 is supported
    requires_serial_runtime = True
```

- 通过 `HalideBackend(halide_module=hl)` 构造，或自动导入 `halide`。
- 使用 `hl.get_host_target()` 进行 JIT — 运行时无交叉编译。
- 所有流水线作为实例属性缓存，并在首次调用时惰性构建。
- `cleanup()` 清除所有缓存的流水线，强制下次使用时重新构建。

### 1.2 流水线缓存策略

每种内核类型有各自的缓存模式：

| 内核 | 缓存字段 | 缓存键 |
|--------|------------|-----------|
| `rgb_to_xyz`（3x3 矩阵） | `_rgb_matrix_pipeline` | 单例 |
| `apply_lut_trilinear_3d` | `_trilinear_3d_cache` | `dict[int, pipeline]`，以 LUT 大小为键 |
| `density_to_light` | `_density_to_light_pipeline` | 单例 |
| `light_to_raw` | `_light_to_raw_pipeline` | 单例 |
| `compute_density_spectral` | `_compute_density_spectral_pipeline` | 单例 |
| `gaussian_blur_fir` | `_fir_blur_pipeline` + `_fir_blur_kernel_len` | 当核长度变化时重建 |
| `highlight_boost` | `_highlight_boost_pipeline` | 单例 |
| `cctf_encode` | `_cctf_encode_pipeline` | 单例 |
| `cctf_decode` | `_cctf_decode_pipeline` | 单例 |
| `interp_1d` | `_interp_1d_pipeline` + `_interp_1d_n` | 当 N 变化时重建 |
| `lut_2d_cubic` | `_lut_2d_pipeline` + `_lut_2d_size` | 当 LUT 大小变化时重建 |

流水线参数（标量、缓冲区）在每次 `realize()` 调用前通过 `Param.set()` / `ImageParam.set()` 设置。编译后的 Func 本身被复用。

### 1.3 调度

所有内核使用 `output.compile_jit(self.target)` 进行主机 JIT。常见的调度模式：

- `vectorize(x, 8)` — 沿宽度维度进行 SIMD 向量化
- `parallel(y)` — 沿高度维度使用线程池并行
- `unroll(c)` — 在编译时展开 3 通道维度
- `reorder(c, x, y)` — 通道优先布局以获得更好的向量化效果

---

## 2. 已验证的内核

Halide 相关测试套件共通过 67 项测试。Python JIT 内核通过 `np.allclose(atol=1e-5..1e-6)` 与 NumPy 参考实现进行数值一致性测试；C++ 生成器测试配置 CMake、构建主机 AOT 目标，并守护 `density_to_light` 波长索引契约。

### 2.1 RGB 3x3 矩阵乘法

**方法：** `rgb_to_xyz(rgb, matrix_3x3)`
**公式：** `output[x, y, c] = sum_i image[x, y, i] * matrix[i, c]`
**测试：** `test_halide_backend.py`（1 项测试，通过 `test_halide_backend_rgb_to_xyz_matches_numpy_reference`）

NumPy `[C,H,W]` 被转置为 Halide `[W,H,C]`，执行 realize，然后转置回来。矩阵作为 `[3,3]` 缓冲区直接传入。

### 2.2 三线性 3D LUT 插值

**方法：** `apply_lut_trilinear_3d(lut, image)`
**测试：**（通过后端集成测试覆盖）

标准三线性插值：8 角 lerp 加夹紧坐标。LUT 按大小缓存。LUT 从 `[L,L,L,3]` 转置为 `[3,L,L,L]` 供 Halide 使用。

### 2.3 density_to_light（光谱）

**方法：** `density_to_light(density, illuminant)`
**公式：** `light[w, y, c] = exp(-density[w, y, c] * ln(10)) * illuminant[c, w]`
**输入：** density `[3, H, 81]`，illuminant `[81, 3]`
**输出：** `[3, H, 81]`
**测试：** `test_halide_spectral.py` — 3 项测试（匹配 numpy、各种大小、无效形状）

使用 `exp(log10 * -x)` 代替 `pow(10, -x)` 以兼容 Halide。

### 2.4 light_to_raw（光谱）

**方法：** `light_to_raw(light, sensitivity)`
**公式：** `output[c_in, y, c_out] = sum_wl light[wl, y, c_out] * sensitivity[c_in, wl]`
**输入：** light `[3, H, 81]`，sensitivity `[81, 3]`
**输出：** `[3, H, 3]`
**测试：** `test_halide_spectral.py` — 3 项测试

使用 `RDom` 对 81 个波长进行规约。

### 2.5 compute_density_spectral（光谱）

**方法：** `compute_density_spectral(density_cmy, channel_density)`
**公式：** `output[w, y, c] = sum_k density[w, y, k] * channel[w, k]`
**输入：** density_cmy `[3, H, 81]`，channel_density `[3, 81]`
**输出：** `[3, H, 81]`
**测试：** `test_halide_spectral.py` — 3 项测试

使用 `RDom` 对 3 个通道进行规约。

### 2.6 gaussian_blur_fir（可分离 FIR）

**方法：** `gaussian_blur_fir(image, kernel_1d)`
**输入：** image `[C, H, W]`，kernel_1d `[K]`（奇数长度）
**输出：** `[C, H, W]`
**测试：** `test_halide_filters.py` — 5 项测试（scipy 参考、单位核、缓存重建、无效输入）

两遍可分离：先水平后垂直。边界条件对 x 使用 `BoundaryConditions.mirror_image`，对 y 使用手动计算的 `_mirror_y` 函数（因为对带有 RDom 的 Func 使用 `mirror_interior` 可能产生不正确的边界访问）。当核长度变化时流水线重建。

### 2.7 gaussian_blur_iir（基于 NumPy 的 YVV）

**方法：** `gaussian_blur_iir(image, sigma)`
**输入：** image `[C, H, W]`，sigma >= 0.5
**输出：** `[C, H, W]`
**测试：** `test_halide_filters.py` — 4 项测试

**此内核不使用 Halide JIT。** Halide Python JIT 不支持自引用递归 Func，因此实现回退到 `spektrafilm.utils.fast_gaussian_filter._gaussian_filter_2d_large`（NumPy YVV）。结果在数值上与 Halide 扫描产生的结果相同。

### 2.8 highlight_boost

**方法：** `highlight_boost(image, *, threshold, boost, offset=0.0)`
**公式：** `select(v < threshold, v, (v + offset) * boost)`
**输入：** image `[C, H, W]`
**输出：** `[C, H, W]`
**测试：** `test_halide_filters.py` — 5 项测试

参数作为 `hl.Param` 标量传入，在每次 `realize()` 前设置。

### 2.9 cctf_encode（sRGB）

**方法：** `cctf_encode(linear, *, gamma, threshold, a, b, c_coeff, d_coeff)`
**公式：** `select(x <= threshold, a*x + b, c_coeff * pow(x, 1/gamma) - d_coeff)`
**输入：** linear `[C, H, W]`
**输出：** encoded `[C, H, W]`
**测试：** `test_halide_color.py` — 5 项测试（sRGB 随机、低于/高于/精确阈值、自定义参数）

### 2.10 cctf_decode（sRGB 逆运算）

**方法：** `cctf_decode(encoded, *, gamma, threshold, a, b, c_coeff, d_coeff)`
**公式：** `select(x <= encoded_threshold, (x - b)/a, pow((x + d_coeff)/c_coeff, gamma))`
**输入：** encoded `[C, H, W]`
**输出：** linear `[C, H, W]`
**测试：** `test_halide_color.py` — 6 项测试（往返、随机、低于/高于阈值、自定义参数、过渡区单调性）

**编码阈值**计算为 `a * threshold + b`（即编码函数应用于线性域阈值的结果）。这对于正确的往返行为至关重要。

### 2.11 interp_1d（一维线性插值）

**方法：** `interp_1d(values, positions, query)`
**输入：** values `[N]`，positions `[N]`（升序），query `[H, W]`
**输出：** `[H, W]`
**测试：** `test_halide_color.py` — 4 项测试

在 query 上使用 `constant_exterior` 边界，然后使用 select 链查找包围区间。超出范围的查询被夹紧到最近端点。当 N 变化时流水线重建。

### 2.12 lut_2d_cubic（Mitchell-Netravali 双三次）

**方法：** `lut_2d_cubic(lut, image)`
**输入：** lut `[size, size, C]`，image `[H, W, 2]`（归一化 0-1）
**输出：** `[H, W, C]`
**测试：** `test_halide_lut.py` — 4 项测试

使用 Mitchell-Netravali 核，B=1/3，C=1/3。4x4 双三次足迹加夹紧边界。LUT 从 `[size, size, C]` 转置为 `[C, size, size]` 供 Halide 使用，输出转置回来。

### 2.13 附加测试

- **Grain 缓冲区：** `generate_grain_buffer()` — 纯 NumPy，非 Halide 内核。3 项测试。
- **后端基础设施：** 后端选择、精度拒绝、清理、探测 — `test_halide_backend.py`。
- **流水线缓存：** 光谱流水线复用和清理 — `test_halide_spectral.py` 中 2 项测试。
- **C++ AOT 生成器基础：** CMake 配置、完整主机 AOT 目标构建和 `density_to_light` 源契约 — `test_halide_generators.py` 中 3 项测试。

---

## 3. CCTF 公式契约

CCTF（编码色彩传递函数）编码/解码对必须是精确的逆运算。以下公式是**契约** — 任何未来的更改都必须保持可逆性。

### 3.1 编码（线性 → 编码）

```
f(x) = { a * x + b                          if x <= threshold
        { c_coeff * pow(x, 1/gamma) - d_coeff  otherwise
```

对于 sRGB：`a=12.92, b=0.0, c_coeff=1.055, d_coeff=0.055, gamma=2.4,
threshold=0.0031308`。

### 3.2 解码（编码 → 线性）

```
encoded_threshold = a * threshold + b

f_inv(y) = { (y - b) / a                           if y <= encoded_threshold
            { pow((y + d_coeff) / c_coeff, gamma)    otherwise
```

**关键点：** 解码阈值在*编码空间*中，而非线性空间中。解码阈值为 `a * threshold + b`（线性阈值的编码结果）。这确保了分段分支精确对齐。

### 3.3 往返不变量

对于 `[0, 1]` 中的任意 `x`：
```
decode(encode(x)) ≈ x   (在 float32 精度范围内)
```

这由 `TestCctfDecode.test_srgb_roundtrip` 和 `TestCctfDecode.test_transition_region_roundtrip`（阈值边界处的单调性检查）验证。

### 3.4 历史 Bug 说明

之前的版本在解码分支中使用了*线性域阈值*，这导致阈值边界处出现不可逆的不连续性。修复方案（计算 `encoded_threshold = a * threshold + b`）确保编码和解码的分段边界在完全相同的点相交。

---

## 4. 维度约定

Halide 使用**列主序**维度排序；NumPy 使用**行主序**。后端在边界处通过显式转置来处理这一差异。

| NumPy 形状 | Halide 形状 | Func 索引 | realize() 参数 |
|------------|-------------|--------------|----------------|
| `[C, H, W]` | `[W, H, C]` | `Func[x, y, c]` | `[W, H, C]` |
| `[H, W]` | `[W, H]` | `Func[x, y]` | `[W, H]` |
| `[N]` | `[N]` | `Func[i]` | `[N]` |
| `[H, W, 2]` | `[2, W, H]` | `Func[c, x, y]` | `[width, height, channels]` |

一般模式：
1. `np.ascontiguousarray(np.transpose(array, (2, 0, 1)))` — NumPy → Halide
2. `np.ascontiguousarray(np.transpose(result, (1, 2, 0)))` — Halide → NumPy

对于 2D LUT，LUT 从 `[size, size, C]` 转置为 `[C, size, size]`。

---

## 5. 当前限制

### 5.1 IIR 高斯使用 NumPy 回退

`gaussian_blur_iir` 委托给 `fast_gaussian_filter._gaussian_filter_2d_large`。Halide Python JIT 无法表达自引用递归 Func（YVV 4-tap 滤波器需要 `y[n] = b0*x[n] + b1*x[n-1] + ... - a1*y[n-1] - ...`）。C++ AOT 生成器*确实*有 Halide IIR 实现（参见 `filter_generator.cpp`），因为 C++ 生成器支持通过 `RDom` 更新定义实现递归 Func。

### 5.2 Grain 使用 NumPy

`generate_grain_buffer()` 是纯 NumPy（`np.random.RandomState`）。Halide 是确定性数据流语言，无法表达 RNG。在设备上，grain 将使用预生成的随机缓冲区（C++ RNG → Halide 缓冲区）。

### 5.3 无 Vulkan 调度

后端仅使用 `hl.get_host_target()`。Halide 的 Vulkan 后端存在但未被使用。未来的 Android 工作将使用 AOT 编译的 ARM 目标。

### 5.4 仅支持 float32

后端在构造时拒绝 `precision="float64"`。所有缓冲区为 `hl.Float(32)`。这符合项目的 GPU 精度策略。

### 5.5 无自动调度器

流水线使用手写调度（`vectorize`、`parallel`、`unroll`）。Halide 的自动调度器可以进一步优化，但尚未集成。

---

## 6. 验证命令

在将 Halide/Android 基础视为最新之前，使用以下本地检查：

```bash
.venv/bin/python -m pytest tests/test_halide_backend.py tests/test_halide_color.py tests/test_halide_lut.py tests/test_halide_spectral.py tests/test_halide_filters.py tests/test_halide_android.py tests/test_halide_generators.py -q
.venv/bin/python -m pytest tests/test_gpu_backend.py tests/test_gpu_lut.py tests/test_gpu_color_chain.py -q
```

生成器测试使用已安装的 Halide CMake 包配置 CMake 项目，在主机上构建四个生成器可执行文件，检查 `density_to_light` 波长索引契约，并构建主机 AOT 目标。

这仍然不能证明 Android 设备上的执行。JNI、APK 打包、Android NDK 下的 `arm-64-android` 交叉编译以及设备一致性测试仍为未来工作。
