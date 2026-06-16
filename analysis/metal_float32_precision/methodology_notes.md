# Methodology Notes

本方法论只用于设计测量，不替代当前 Spektrafilm 源码事实和本次样片实测。

## External References

1. Apple Metal / Metal Shading Language
   - 来源：
     - [Metal Shading Language Specification](https://developer.apple.com/metal/Metal-Shading-Language-Specification.pdf)
     - [MTLCompileOptions.fastMathEnabled](https://developer.apple.com/documentation/metal/mtlcompileoptions/1515484-fastmathenabled)
   - 对测量设计的影响：
     - 把 Metal/MLX 路径视为可能存在 FMA、fast math、`half`/`float`、kernel 内插值和异步求值差异的 GPU 浮点实现。
     - 指标必须看 stage-by-stage，而不能只看最终图像；否则无法区分早期 float32 舍入、LUT 插值、log/pow 和最后 clip/encode 的误差贡献。
     - 记录 dtype、NaN/Inf、负值、clamp 数量，避免 GPU fast path 把非有限值处理差异隐藏掉。

2. NVIDIA Floating Point and IEEE 754
   - 来源：[Floating Point and IEEE 754 Compliance for NVIDIA GPUs](https://docs.nvidia.com/cuda/floating-point/index.html)
   - 对测量设计的影响：
     - CPU/GPU 浮点差异不只来自精度位数，也可能来自 FMA、表达式重排和规约顺序。
     - 本研究把“数值精度误差”和“backend 实现差异”分开，不把所有 CPU/MLX 差异直接归因为 float32。
     - 使用绝对误差、相对误差、RMSE、MAE、percentile 和 max，而不是只用 `np.allclose`。

3. OpenColorIO CPU/GPU processor model
   - 来源：[OpenColorIO Documentation](https://opencolorio.readthedocs.io/)
   - 对测量设计的影响：
     - 色彩管线验证应区分 CPU reference、GPU shader/render path、LUT/interpolation precision 和 display transform。
     - 本研究把 pipeline tap、display buffer、export roundtrip 分层测量。

4. Colour Science
   - 来源：
     - [Colour `delta_E`](https://colour.readthedocs.io/en/latest/generated/colour.delta_E.html)
     - [Colour RGB/XYZ transforms](https://colour.readthedocs.io/en/latest/)
   - 对测量设计的影响：
     - 对最终 display-referred RGB 计算 CIEDE2000；对线性或 HDR 中间态不强行解释为人眼可见差异。
     - 报告中将 ΔE2000 用作 sRGB display 近似感知指标，并标注其限制。

5. scikit-image metrics
   - 来源：[skimage.metrics](https://scikit-image.org/docs/stable/api/skimage.metrics.html)
   - 对测量设计的影响：
     - 对最终图像计算 PSNR 和 SSIM，并显式设置/记录 data range，避免默认范围误用。
     - PSNR/SSIM 只用于结构性 sanity check，不替代色彩误差指标。

6. ITU HDR/WCG color-difference guidance
   - 来源：
     - [ITU-R BT.2124](https://www.itu.int/rec/R-REC-BT.2124)
     - [ITU-R BT.2100](https://www.itu.int/rec/R-REC-BT.2100)
   - 对测量设计的影响：
     - HDR/WCG 场景更适合使用 ICtCp / ΔEITP 类指标或显式 luminance/EV error。
     - 本次脚本记录 EV error 和 luminance error；ΔEITP 未实际实现，报告中列为后续 CI 增强项。

7. OpenImageIO
   - 来源：
     - [OpenImageIO documentation](https://openimageio.readthedocs.io/)
     - [OpenImageIO ImageBufAlgo compare](https://openimageio.readthedocs.io/en/latest/imagebufalgo.html)
   - 对测量设计的影响：
     - 导出验证不能只比较编码前 buffer，必须读回最终文件，统计量化/clip/ICC 之后的像素差异。
     - 本次实现 PNG16 encode/decode roundtrip；EXR/HDR HEIC 只做静态路径分析，未把 HEIC 读回纳入实测。

8. rawpy / LibRaw
   - 来源：[rawpy API documentation](https://letmaik.github.io/rawpy/api/rawpy.RawPy.html#rawpy.RawPy.postprocess)
   - 对测量设计的影响：
     - RAW decode 参数 `output_bps`、`gamma`、`no_auto_bright`、white balance 会改变后续 reference 的起点。
     - 本研究从 GUI 同源 RAW loader 输出之后建立 CPU float64 reference，因为当前 loader 已返回 `float32`。

9. OpenEXR
   - 来源：[OpenEXR Technical Introduction](https://openexr.com/en/latest/TechnicalIntroduction.html)
   - 对测量设计的影响：
     - 区分 float32 EXR、half EXR、integer PNG/TIFF 的量化风险。
     - 报告把 half/float32/uint16 导出视为单独的编码层风险，而不是 pipeline float32 计算误差。

## Metric Set

本研究使用以下指标：

- 基础统计：shape、dtype、min、max、mean、std、NaN、+Inf、-Inf、负值、>1、<=0、>=1。
- 数值误差：absolute error p50/p90/p95/p99/p99.9/max、relative error p50/p90/p95/p99/p99.9/max、MAE、RMSE、max signed/min signed error。
- 亮度误差：Rec.709 luma Y absolute percentiles；EV error `abs(log2((metal + eps) / (cpu + eps)))` percentiles。
- 感知/图像指标：PSNR、SSIM、CIEDE2000。
- 诊断产物：error heatmap、error histogram、high-error-pixel CSV。

## Measurement Layers

1. Pipeline tap 层：`rgb_in`、`rgb_pre`、`log_e_film`、`cmy_film`、`log_e_print`、`cmy_print`、`rgb_out`。
2. Materialized output 层：`materialized_rgb_out`，模拟 GUI/export 取出 runtime 输出时的 dtype 策略。
3. Export roundtrip 层：PNG16 save/read，隔离整数量化和文件编码后的差异。
4. Synthetic 层：灰阶、暗部、高光、饱和 RGB、near-clip，定位误差热区。

## Important Limitations

- 本次没有修改生产代码添加新 hook；只能使用现有 topology tap 和公开可导入路径。
- 本次实测 PNG16 roundtrip；HDR HEIC/gain map 路径已静态追踪，但没有对 HEIC 文件读回做端到端数值验证。
- ΔE2000 只对 clipped/display RGB 有意义；对 HDR 线性场景不作感知等价结论。
