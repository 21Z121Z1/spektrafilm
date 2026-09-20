# 原生预编译执行层

这是[空间算子基础](native-metal-spatial.md)的实验性扩展。CPU/MLX 生产后端的
选择、默认参数、profile、依赖锁和误差门槛不变。其他项目不同硬件上的基准不能
证明本实现更快。

## 唯一模型来源

Python 从本仓库 CPU 模型准备不可变常量。`program.py` 根据最后一次读取安排
缓冲区，`executor.py` 管理 C 句柄，`execution.mm` 管理 Metal 队列，离线编译的
内核执行运算。不导入 MLX，也不在 C++ 里再写一套 profile 拟合、滤波系数、
DIR 反解、色彩科学或摄影策略。

这是独立编写，不宣称具备人员隔离条件的严格净室开发：此前上下文已包含
SpektraLab 源码。未导入对方源码或资源；数值依据是本仓库 CPU 模型和公开算法。

## 已实现的契约

程序不可变、无环，包含通道检查和内容指纹；不可达节点被删除，重复常量只存一份。
缓冲区只在最后一个读者之后复用，输入和已经返回的图像不可变。

全部缓冲区使用 shared、tracked 存储。顺序计算编码器保证节点依赖，不在节点之间
等待 CPU。每个程序提交一次、等待一次，只回读四字节状态，不回读每个中间图像。
内存池只复用已完成且没有外部持有者的缓冲区。预算覆盖池、输出、常量、临时空间
和纹理后备存储；这是缓冲区字节数，不是进程 RSS。可显式释放闲置池。

Gaussian FIR/IIR 保留原数值契约。IIR 使用带填充的 32×32 线程组转置和补偿递归。
加权 Gaussian 累加可融合到最后一遍滤波，但保留 Gaussian 结果的 float32 舍入。

执行算子包括仿射、矩阵、曲线插值、光谱积分、对数/指数、乘法、Gaussian、
加权 Gaussian、分层颗粒和对数正态微结构。波长只存在于寄存器循环中，不分配
HxWx81 张量。缺失密度波段整体归零，不单独改写某个染料系数。

`prepare_spatial` 对应 CPU 串行镜头、散射和光晕链；`prepare_development` 对应
真实的胶片对数曝光到 CMY 负片显影，包括 CPU 准备的 DIR 常量与可选颗粒。
不合法的 DIR 反解曝光轴直接拒绝。

`NativeSession` 缓存一个输入和一个负片，不设 4 MP 硬阈值，也不自动积累无限 LRU。
仅改变打印程序时重用负片；胶片常量、种子或输入改变时失效。新的胶片/打印事务
失败，不发布新的缓存条目。

`ResidentImage.texture()` 在 GPU 上打包 RGBA32Float、alpha 为一，返回具有明确
生命周期的纹理借用句柄，没有主机图像往返。但它不是零运算，也不是 packed RGB
的直接视图。没有自动赋予色彩空间，CMY 密度不能直接视作显示 RGB。外部 GPU
读操作必须在释放租约前完成。未接入产品 UI；`TextureLease.numpy()` 仅显式诊断回读。

## 必须区分的两种一致性

CPU 串行空间滤波不是现有 MLX fused FFT。例如 CPU 指数拟合权重之和为 0.9999，
MLX FFT 会重新归一化。直接替换不能称为逐位不变，旧路径继续保留。

随机采样契约为 `philox4x32-10-thinned-poisson-v1`：64 位种子作为 key，counter 为
`(pixel-low, pixel-high, stream, block)`。0..8 标识染料子层/通道，9..11 标识各通道
独立微结构；简单颗粒模式使用 `3*layer+channel`。分割独立采样时必须传全局像素
起点；这不代表空间模糊可以无重叠分块。

Poisson thinning 保持 Poisson→binomial 的分布，不保持随机实现。Knuth/PTRS 不以
正态分布近似泊松；现有 MLX 颗粒路径确实使用正态近似，其旧摘要不是新采样器目标。
采样接受条件仍受 float32 与 23 位开区间均匀数的有限精度约束。速率超出 [0, 2^20]、
256 次尝试耗尽或非有限结果，均使整个结果失败，不偷偷切换分布。

## 使用和验证

代码示例见英文文档。显式构建和验证：

```sh
uv run --frozen python -m spektrafilm.gpu.native_metal.build --output build/native
uv run --frozen python -m pytest tests/native_metal -q
uv run --frozen python tests/native_metal/benchmark_execution.py \
  --bundle build/native --width 4000 --height 3000 --output /tmp/native-12mp.json
```

现有 CI 的 native 矩阵运行这些测试。macOS 必须实际编译和执行 Metal；缺少工具或
设备是失败。Linux 只证明主机算术和程序契约。检查覆盖公开 Philox 向量、CPU
float32/64 Gaussian、一致的转置/融合结果、真实 profile DIR、颗粒矩/PSD/相关性、
全局像素确定性、预算恢复、缓存事务失败、并发句柄和纹理内容/生命周期。
数值门槛仍为 `atol=rtol=1e-6`，随机统计门槛独立固定。

基准只测光谱上采样之后的胶片阶段，不是 RAW 到 RGB 或完整打印。交替测量顺序，
双方都得到 NumPy 输出，记录输入/程序指纹和硬件，并在报告时间之前断言一致性。
50 MP 必须单独在足够内存上验证，不能从小图结果推断。

## 尚未晋升

未注册到生产后端工厂，未切换默认路径。任意相机/放大机扩散 PSF 没有被 Gaussian
近似替代。光谱上采样、完整打印/扫描/色彩/HDR 输出和产品 UI 仍需各自验收。
新后端尚未加入现有完整 precision staircase；算子/阶段测试不能代替该门槛。
公开算法及本仓库模型来源见英文文档。
