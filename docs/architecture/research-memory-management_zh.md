> 这是英文原文的中文翻译。权威版本请参考英文原文。

# 内存管理深度研究 — Spektrafilm

日期：2026-05-27

## 目录

1. [当前内存使用审计](#1-current-memory-usage-audit)
2. [内存分析工具与集成](#2-memory-profiling-tools--integration)
3. [NumPy 内存优化技术](#3-numpy-memory-optimization-techniques)
4. [GPU 内存管理模式](#4-gpu-memory-management-patterns)
5. [Float32 与 Float16 精度权衡](#5-float32-vs-float16-precision-tradeoffs)
6. [无需完整分配的大图像处理](#6-large-image-processing-without-full-allocation)
7. [GPU VRAM 管理与核外处理](#7-gpu-vram-management--out-of-core-processing)
8. [Python GC 与 NumPy 循环引用](#8-python-gc--numpy-circular-references)
9. [Apple 统一内存与 MLX](#9-apple-unified-memory--mlx)
10. [对 Spektrafilm 的建议](#10-recommendations-for-spektrafilm)

---

## 1. 当前内存使用审计

### 1.1 管线架构

Spektrafilm 的仿真管线通过以下阶段处理图像：

```
Input RGB → [AutoExposure] → [Crop/Rescale] → [Filming: Expose] → [Filming: Develop]
→ [Printing: Expose] → [Printing: Develop] → [Scanning: Scan] → Output RGB
```

每个阶段都会创建一个完整的 `(H, W, 3)` 浮点数组。`pipeline.py:584-604` 中的管线对中间数组使用了显式 `del`：

```python
def _pipeline_print(self, rgb_image):
    log_raw_film = self._runtime_array(self._filming_stage.expose(rgb_image))
    del rgb_image
    cmy_film = self._runtime_array(self._filming_stage.develop(log_raw_film))
    del log_raw_film
    log_raw_print = self._runtime_array(self._printing_stage.expose(cmy_film))
    del cmy_film
    cmy_print = self._runtime_array(self._printing_stage.develop(log_raw_print))
    del log_raw_print
    rgb_scan = self._runtime_array(self._scanning_stage.scan(cmy_print, ...))
    del cmy_print
    return rgb_scan
```

### 1.2 峰值内存估算（按图像尺寸）

对于使用 float32（每值 4 字节）的典型管线处理：

| 图像尺寸 | 像素数 | 单个数组 | 管线峰值（5 个数组） | 含 LUT 中间数据 |
|------------|--------|-------------|-------------------------|----------------------|
| 2K (1920x1080) | 2.07M | 24 MB | ~120 MB | ~180 MB |
| 4K (3840x2160) | 8.29M | 96 MB | ~480 MB | ~720 MB |
| 6K (6000x4000) | 24M | 280 MB | ~1.4 GB | ~2.1 GB |
| 8K (7680x4320) | 33.2M | 388 MB | ~1.9 GB | ~2.9 GB |

**代码库中已识别的主要内存消耗来源：**

1. **管线数组** (`pipeline.py:584-604`)：处理期间同时存在 5-6 个 H x W x 3 float32 数组。每个约 `H x W x 12` 字节。峰值约为输入大小的 5 倍。

2. **FFT 高斯滤波** (`fft_gaussian_filter.py:33`)：创建 `np.empty_like(image)` 加填充副本加 FFT 数组。对于 3D 图像，使用 `ThreadPoolExecutor` 并行处理各通道，内存乘以线程数。

3. **LUT 计算** (`lut.py:20-30`)：形状为 `(steps, steps, steps, 3)` 的 3D LUT -- 当 steps=32 时为 32^3 x 3 x 8 = 3 MB（float64），当 steps=64 时为 24 MB。`fast_interp_lut.py:252-256` 创建与 LUT 大小匹配的斜率数组。

4. **HDR 照片处理** (`hdr_photo.py`)：创建多个 `(H, W, 3)` float32 数组 -- `hdr_rgb`、`unlifted_hdr_rgb`、`sdr_rgb`，以及 RGBA 载荷。在 `_prepare_generic_renditions` 期间峰值约为输入大小的 4 倍。

5. **扩散/光晕** (`diffusion.py:70-87`)：多次高斯滤波传递及中间数组。对于 N 次弹射，创建 N 个临时滤波副本。

6. **GPU 分块处理** (`pipeline.py:400-429`)：创建完整输出缓冲区加每块 GPU 数组。块重叠为每块增加约 10-20% 内存。

### 1.3 内存分配模式

**未找到内存池管理。** 代码库具有以下特点：
- 无 `gc.collect()` 调用
- 无 `tracemalloc` 使用
- 无 `weakref` 使用
- 无 `__del__` 方法
- 无 CuPy 内存池管理（`free_all_blocks`、`mempool`）
- 无 `numpy.memmap` 使用
- 无内存映射 I/O

**现有的 `del` 语句**（pipeline.py:586-603、hdr_photo.py:267、controller.py:355-359）表明对内存压力有所意识，但仅依赖引用计数。

---

## 2. 内存分析工具与集成

### 2.1 工具对比

| 工具 | 类型 | 开销 | 最适用场景 |
|------|------|------|----------|
| `tracemalloc` | 标准库 | 低-中 | 查找分配位置、泄漏检测 |
| `memory_profiler` | 第三方 | 高 | 逐行内存使用分析 |
| `memray` (Bloomberg) | 第三方 | 低 | 火焰图、原生调用栈、生产环境使用 |
| `objgraph` | 第三方 | 低 | 引用循环可视化 |
| `psutil` | 第三方 | 极小 | RSS/VMS 监控 |

### 2.2 tracemalloc 集成模式

```python
import tracemalloc

def profile_pipeline_run(pipeline, image, top_n=15):
    """Profile memory usage of a pipeline run."""
    tracemalloc.start(25)  # 25 frames deep for meaningful traces

    snapshot_before = tracemalloc.take_snapshot()
    result = pipeline.process(image)
    snapshot_after = tracemalloc.take_snapshot()

    # Top allocations during this run
    top_stats = snapshot_after.compare_to(snapshot_before, 'lineno')
    print(f"\n=== Memory Profile: top {top_n} allocations ===")
    for stat in top_stats[:top_n]:
        print(stat)

    current, peak = tracemalloc.get_traced_memory()
    print(f"\nCurrent: {current / 1024**2:.1f} MB, Peak: {peak / 1024**2:.1f} MB")
    tracemalloc.stop()
    return result
```

### 2.3 memray 集成模式

```bash
# Run with memray
memray run -o profile.bin your_script.py

# Generate flame graph
memray flamegraph profile.bin -o flamegraph.html

# Table view of top allocators
memray table profile.bin

# Compare two runs
memray compare run1.bin run2.bin
```

```python
# Programmatic memray usage
import memray

with memray.Tracker("output.bin", native_traces=True):
    result = pipeline.process(image)
```

### 2.4 轻量级 RSS 监控器

```python
import os
import psutil

def get_rss_mb():
    """Get current RSS in MB."""
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024**2

class MemoryTracker:
    """Context manager to track peak memory during a block."""
    def __enter__(self):
        self._start_rss = get_rss_mb()
        self._peak = self._start_rss
        return self

    def __exit__(self, *args):
        self._end_rss = get_rss_mb()

    @property
    def delta_mb(self):
        return self._end_rss - self._start_rss
```

### 2.5 对 Spektrafilm 的推荐集成方式

添加 `--profile-memory` CLI 标志或环境变量（`SPEKTRAFILM_PROFILE_MEMORY=1`），启用后对管线运行进行 tracemalloc 包装。禁用时零开销，启用时可提供可操作的数据。

---

## 3. NumPy 内存优化技术

### 3.1 零拷贝视图

NumPy 视图共享底层数据缓冲区而不进行复制。返回视图的关键操作：

```python
# Slicing — always a view
subarray = arr[100:200, :, :]  # view, no copy

# Transpose — just swaps strides
transposed = arr.T  # view

# Reshape — view if contiguous
reshaped = arr.reshape(-1, 3)  # view if C-contiguous

# dtype view (same-size dtypes)
reinterpreted = arr.view(np.float32)  # view
```

**验证：**
```python
assert np.shares_memory(arr, subarray)
assert subarray.base is arr
```

**与 Spektrafilm 的关联：** 管线的 `_preprocess_input_image`（`pipeline.py:556-559`）执行：
```python
image = np.ascontiguousarray(np.asarray(image, dtype=self._runtime_dtype)[:, :, 0:3])
```
`[:, :, 0:3]` 切片是视图，但 `np.ascontiguousarray` 强制复制。这对下游性能是正确的，但意味着原始 4 通道图像会短暂地与 3 通道副本并存。

### 3.2 原地操作

使用 `out=` 参数和增强赋值避免临时数组分配：

```python
# BAD: creates temporary
result = np.clip(arr, 0.0, 1.0)
result = result.astype(np.float32)

# GOOD: in-place
np.clip(arr, 0.0, 1.0, out=arr)
# Or with copy=False for astype (returns view if dtype matches)
result = arr.astype(np.float32, copy=False)

# GOOD: in-place arithmetic
arr *= 2.0        # instead of arr = arr * 2.0
arr += offset     # instead of arr = arr + offset
np.maximum(arr, 0.0, out=arr)  # instead of arr = np.maximum(arr, 0.0)
```

**Spektrafilm 已在多处使用 `copy=False`**（`hdr_photo.py:472-477`）：
```python
hdr_rgb = np.clip(hdr_rgb, 0.0, headroom).astype(np.float32, copy=False)
```
这是正确的 -- 当 dtype 已经匹配时避免了复制。

### 3.3 使用预分配缓冲区复用数组

```python
# Instead of allocating per call:
def process(image):
    output = np.empty_like(image)  # allocation every call
    # ... fill output
    return output

# Pre-allocate and reuse:
class Processor:
    def __init__(self, shape, dtype):
        self._buffer = np.empty(shape, dtype=dtype)

    def process(self, image):
        # Fill pre-allocated buffer
        np.multiply(image, 2.0, out=self._buffer)
        return self._buffer
```

**Spektrafilm 优化机会：** 管线各阶段可以共享预分配缓冲区池，因为它们都处理相同尺寸的图像。

### 3.4 内存布局优化

```python
# C-order (row-major): best for row-wise operations
arr_c = np.ascontiguousarray(arr, dtype=np.float32)

# F-order (column-major): best for column-wise operations
arr_f = np.asfortranarray(arr, dtype=np.float32)

# Check layout
assert arr_c.flags['C_CONTIGUOUS']
assert arr_f.flags['F_CONTIGUOUS']
```

**Spektrafilm 备注：** 所有图像数组均为 C 连续（H x W x 3，行优先）。这对整个代码中使用的像素处理访问模式是正确的。

### 3.5 `np.where` 与布尔索引

```python
# Boolean indexing — creates copies of selected elements
result = np.zeros_like(arr)
mask = arr > threshold
result[mask] = arr[mask] * scale  # two temporary arrays

# np.where — single allocation, no temporaries
result = np.where(arr > threshold, arr * scale, 0.0)
# Still creates arr * scale temporary, but fewer allocations overall

# Best: combine with out parameter where possible
np.multiply(arr, scale, out=temp)
np.where(arr > threshold, temp, 0.0, out=result)
```

---

## 4. GPU 内存管理模式

### 4.1 CuPy 内存池

CuPy 默认使用内存池来避免反复调用 `cudaMalloc`/`cudaFree` 的开销。内存池缓存已释放的块以供复用。

```python
import cupy as cp

# Access the default memory pool
mempool = cp.get_default_memory_pool()

# Monitor usage
print(f"Used: {mempool.used_bytes() / 1024**2:.1f} MB")
print(f"Total (cached): {mempool.total_bytes() / 1024**2:.1f} MB")

# Free unused cached blocks (does NOT free in-use arrays)
mempool.free_all_blocks()

# Pinned (page-locked) host memory pool for faster transfers
pinned_pool = cp.get_default_pinned_memory_pool()
pinned_pool.free_all_blocks()
```

### 4.2 CuPy 内存池配置

```python
# Set memory pool limits to prevent OOM
mempool = cp.get_default_memory_pool()
mempool.set_limit(size=4 * 1024**3)  # 4 GB limit

# Or use a custom allocator per-context
pool = cp.cuda.MemoryPool()
cp.cuda.set_allocator(pool.malloc)
# ... use GPU ...
pool.free_all_blocks()
```

### 4.3 GPU-CPU 传输模式

```python
import cupy as cp

# Host → Device (pinned memory is faster)
host_array = np.ascontiguousarray(host_array)  # ensure contiguous
device_array = cp.asarray(host_array)  # H2D transfer

# Device → Host
host_result = cp.asnumpy(device_array)  # D2H transfer
# or: host_result = device_array.get()

# Synchronize before accessing host memory
cp.cuda.Stream.null.synchronize()
```

### 4.4 Spektrafilm CuPy 后端分析

`CupyBackend` 类（`cupy_backend.py`）**没有内存池管理**：

```python
class CupyBackend:
    def __init__(self, *, precision: str = "float32"):
        import cupy as cp
        self.cp = cp
        # No pool configuration, no limits set

    def asarray(self, value, dtype=None):
        return self.cp.asarray(value, dtype=dtype or self.default_dtype)

    def to_numpy(self, value):
        self.synchronize()
        return self.cp.asnumpy(value)
```

**发现的问题：**
1. 管线完成后没有 `mempool.free_all_blocks()` -- GPU 内存保持缓存状态
2. 未设置内存限制 -- 大图像可能导致 OOM
3. 无锁页内存池用于加速 H2D/D2H 传输
4. 分块处理（`pipeline.py:414-419`）将每块结果单独传回 CPU，这是正确的，但可以使用锁页内存

### 4.5 推荐的 Spektrafilm CuPy 内存管理方案

```python
class CupyBackend:
    def __init__(self, *, precision="float32"):
        import cupy as cp
        self.cp = cp
        self._mempool = cp.get_default_memory_pool()
        self._pinned_pool = cp.get_default_pinned_memory_pool()
        # Set a reasonable limit (e.g., 80% of VRAM)
        free, total = cp.cuda.Device().mem_info
        self._mempool.set_limit(int(total * 0.8))

    def cleanup(self):
        """Call after pipeline run to free cached GPU memory."""
        self._mempool.free_all_blocks()
        self._pinned_pool.free_all_blocks()

    def __del__(self):
        try:
            self.cleanup()
        except Exception:
            pass
```

---

## 5. Float32 与 Float16 精度权衡

### 5.1 精度对比

| 属性 | float32 | float16 | bfloat16 |
|----------|---------|---------|----------|
| 位数 | 32 | 16 | 16 |
| 尾数位 | 23 | 10 | 7 |
| 指数位 | 8 | 5 | 8 |
| 十进制精度 | ~7 | ~3 | ~2-3 |
| 最大值 | 3.4x10^38 | 65,504 | 3.4x10^38 |
| 最小正规数 | 1.2x10^-38 | 6.1x10^-5 | 1.2x10^-38 |
| 每像素内存（RGB） | 12 字节 | 6 字节 | 6 字节 |

### 5.2 对图像处理的影响

**float16 在 Spektrafilm 管线中的风险：**

1. **HDR 值**：Spektrafilm 处理的值可达 `max_headroom`（通常 4-16 倍）。float16 可以表示这些值，但仅有约 3 位十进制精度。高光中的细微渐变会出现色带。

2. **对数密度**：密度曲线使用曝光值的 `log10()`。接近零的小 float16 值精度较差，会放大暗部区域的量化噪声。

3. **LUT 插值**：`fast_interp_lut.py` 中的三次插值涉及 64 个值（4^3）的加权求和。累积的 float16 舍入误差会产生可见的伪影。

4. **累积**：光晕弹射（`diffusion.py:79-83`）累积加权的高斯滤波值。float16 累积在每次加法时都会丢失精度。

5. **ICC 色彩变换**：色彩空间转换中的矩阵乘法会复合舍入误差。

### 5.3 Spektrafilm 当前的精度策略

代码库在运行时处理中全程使用 float32：
- `pipeline.py:47-52`：`_runtime_dtype()` 返回 float32 或 float64
- `hdr_photo.py`：在每个阶段显式转换为 float32
- `CupyBackend` 默认 float32，支持 float16 作为选项
- `MlxBackend` 默认 float32，支持 float16 作为选项

**CLAUDE.md 的约束是正确的**：float32 是正确的默认值。float16 应仅用于速度比质量更重要的预览/交互工作流。

### 5.4 混合精度策略（未来）

如果将来需要 float16 来提升性能：

```python
# Compute in float16, accumulate in float32
def halation_bounce_mixed(raw, sigma, weight, backend):
    # Filter in float16 for speed
    filtered_16 = gaussian_filter(raw.astype(np.float16), sigma)
    # Accumulate in float32 for precision
    return raw + weight * filtered_16.astype(np.float32)
```

这与 NVIDIA 的"混合精度"方法一致，但需要仔细验证每个操作的数值稳定性。

---

## 6. 无需完整分配的大图像处理

### 6.1 numpy.memmap

内存映射数组让操作系统按需将数据页面换入/换出 RAM，从而能够处理大于可用内存的图像：

```python
import numpy as np

# Create memory-mapped array
fp = np.memmap('large_image.dat', dtype='float32', mode='w+',
               shape=(40000, 60000, 3))  # 28.8 GB

# Process in chunks
chunk_rows = 1000
for i in range(0, fp.shape[0], chunk_rows):
    chunk = fp[i:i+chunk_rows, :, :]
    # Process chunk
    fp[i:i+chunk_rows, :, :] = processed_chunk

# Read existing file
fp = np.memmap('image.raw', dtype='float32', mode='r', shape=(H, W, 3))
```

**优点：** 操作系统管理分页、透明访问、兼容现有 NumPy 代码。
**缺点：** 无压缩、HDD 上随机访问速度慢、仅支持原始格式。

### 6.2 Zarr -- 分块压缩数组

```python
import zarr
import numpy as np

# Create chunked, compressed array
z = zarr.open('image.zarr', mode='w', shape=(40000, 60000, 3),
              chunks=(1000, 60000, 3), dtype='float32',
              compressor=zarr.Blosc(cname='zstd', clevel=3))

# Write chunks
for i in range(0, 40000, 1000):
    z[i:i+1000, :, :] = compute_chunk(i)

# Read chunks — only loads accessed chunks
chunk = z[5000:6000, :, :]
```

**优点：** 压缩（图像数据通常 2-5 倍）、云友好（S3/GCS）、块级并行。
**缺点：** 解压缩开销、不通过 `.np` 访问器无法直接作为 NumPy 数组使用。

### 6.3 使用 h5py 的 HDF5

```python
import h5py
import numpy as np

with h5py.File('image.h5', 'w') as f:
    ds = f.create_dataset('image', shape=(40000, 60000, 3),
                          chunks=(1000, 60000, 3), dtype='float32',
                          compression='gzip', compression_opts=4)
    for i in range(0, 40000, 1000):
        ds[i:i+1000, :, :] = compute_chunk(i)
```

### 6.4 Dask Array -- 惰性并行处理

```python
import dask.array as da

# Create lazy array from chunks
chunks = da.from_delayed(
    dask.delayed(load_chunk)(i),
    shape=(1000, 60000, 3), dtype='float32'
)
full_image = da.concatenate(chunk_list, axis=0)

# Process — only loads what's needed
result = da.map_blocks(process_func, full_image, dtype='float32')
result.compute()  # or result.to_zarr('output.zarr')
```

### 6.5 与 Spektrafilm 的关联

Spektrafilm 目前将完整图像加载到内存中。对于非常大的图像（8K 以上），管线峰值可能超过 2 GB。两种方案：

1. **保持当前架构** -- GPU 分块（`pipeline.py:396-429`）已将大图像拆分为可管理的块。这是主要的 OOM 缓解手段。内存映射 I/O 仅在 I/O 边界处有帮助。

2. **在 I/O 边界添加 memmap** -- 对最大图像使用 memmap 加载/保存，将块馈送到管线。这避免了加载期间的内存翻倍。

```python
# Example: memory-mapped input
def load_image_memmap(path):
    """Load image as memory-mapped array for large files."""
    # Use tifffile for TIFF memmap
    import tifffile
    return tifffile.memmap(path)

    # Or for raw formats:
    # return np.memmap(path, dtype='float32', shape=(H, W, 3))
```

---

## 7. GPU VRAM 管理与核外处理

### 7.1 分块策略（已实现）

Spektrafilm 已在 `pipeline.py:396-429` 中实现 GPU 分块：

```python
def _process_preprocessed_with_gpu_tiles(self, preprocessed):
    height, width = preprocessed.shape[:2]
    overlap = min(self._tile_overlap_pixels(), max(height - 1, 0))
    core_rows = self._tile_core_rows(width=width, overlap=overlap)
    output = np.empty((height, width, 3), dtype=self._runtime_dtype)

    for start_y in range(0, height, core_rows):
        end_y = min(start_y + core_rows, height)
        input_start = max(start_y - overlap, 0)
        input_end = min(end_y + overlap, height)
        tile = self._runtime_array(preprocessed[input_start:input_end, :, :])
        tile_output = self._process_runtime_array(tile)
        tile_output = np.asarray(self._array_backend.to_numpy(tile_output), ...)
        output[start_y:end_y, :, :] = tile_output[crop_start:crop_end, :, :]
```

**默认块预算：** 2,000,000 像素（`DEFAULT_GPU_TILE_PIXELS`），可通过 `SPEKTRAFILM_GPU_TILE_PIXELS` 环境变量配置。

**重叠计算**（`pipeline.py:441-478`）：基于镜头模糊、光晕散射和扩散大小 -- 确保块边界无缝衔接。

### 7.2 CUDA 流实现重叠

```python
import cupy as cp

# Use streams to overlap compute and transfer
stream1 = cp.cuda.Stream()
stream2 = cp.cuda.Stream()

with stream1:
    tile1_gpu = cp.asarray(tile1_cpu)
    result1_gpu = process(tile1_gpu)

with stream2:
    tile2_gpu = cp.asarray(tile2_cpu)
    result2_gpu = process(tile2_gpu)

# Synchronize and collect results
stream1.synchronize()
result1_cpu = cp.asnumpy(result1_gpu)
stream2.synchronize()
result2_cpu = cp.asnumpy(result2_gpu)
```

### 7.3 CuPy 内存池调优

```python
import cupy as cp

mempool = cp.get_default_memory_pool()

# Set limit to prevent OOM (e.g., 80% of VRAM)
free_mem, total_mem = cp.cuda.Device().mem_info
mempool.set_limit(size=int(total_mem * 0.8))

# Monitor fragmentation
print(f"Used: {mempool.used_bytes() / 1024**2:.0f} MB")
print(f"Total: {mempool.total_bytes() / 1024**2:.0f} MB")
print(f"Fragmentation: {1 - mempool.used_bytes() / max(mempool.total_bytes(), 1):.1%}")
```

### 7.4 使用 CuPy 的核外处理

对于即使分块也无法放入 VRAM 的图像：

```python
import cupy as cp
import numpy as np

def process_large_image(image, process_fn, tile_pixels=2_000_000):
    """Process a large image using GPU tiles with memory management."""
    mempool = cp.get_default_memory_pool()
    h, w = image.shape[:2]
    rows_per_tile = max(tile_pixels // w, 1)
    output = np.empty_like(image)

    for y in range(0, h, rows_per_tile):
        end = min(y + rows_per_tile, h)
        # Transfer tile to GPU
        tile_gpu = cp.asarray(image[y:end])
        # Process on GPU
        result_gpu = process_fn(tile_gpu)
        # Transfer back
        output[y:end] = cp.asnumpy(result_gpu)
        # Free GPU memory for this tile
        del tile_gpu, result_gpu
        mempool.free_all_blocks()

    return output
```

---

## 8. Python GC 与 NumPy 循环引用

### 8.1 Python GC 工作原理

Python 使用两种内存管理机制：

1. **引用计数**（主要）：每个对象都有一个引用计数。当计数降为 0 时，对象立即释放。这是确定性的且速度快。

2. **循环垃圾回收器**（辅助）：周期性扫描互相引用但除此之外不可达的对象组。基于代阈值运行（默认：700、10、10）。

### 8.2 NumPy 数组 GC 行为

NumPy 数组在 C 层管理其数据缓冲区。当 Python 数组对象被回收时，缓冲区通过 `__del__` 释放。自 Python 3.4（PEP 442）起，带 `__del__` 的对象可以参与循环解除。

```python
import gc
import numpy as np

# Reference counting works fine for simple cases
a = np.zeros(1000000)  # refcount = 1
b = a                   # refcount = 2
del b                   # refcount = 1
del a                   # refcount = 0, freed immediately

# Circular reference — needs cyclic GC
class Container:
    def __init__(self, data):
        self.data = data
        self.self_ref = self  # circular reference

c = Container(np.zeros(100000000))  # 800 MB
del c  # refcount never reaches 0 due to self_ref
gc.collect()  # cyclic GC breaks the cycle and frees
```

### 8.3 Spektrafilm GC 风险

代码库中**未发现循环引用模式**。用于 `HDRSceneEnergyMetadata` 和 `SimulationPipelineResult` 的 `dataclass(frozen=True, slots=True)` 模式防止了意外的循环引用。

但仍存在一些风险：

1. **`hdr_curve_profiles.py`**：使用闭包和函数引用，如果配置文件对象持有对管线的反向引用，可能创建循环。

2. **GUI 回调**：Qt 信号/槽连接可创建引用循环。`widget_editors.py` 和 `widget_sections.py` 中的 `del event` 模式表明对此有所意识。

3. **管线调试方法**（`pipeline.py:615-646`）：调试管线存储了正常管线会删除的中间数组的引用。

### 8.4 最佳实践

```python
import gc
import weakref

# 1. Use weakref for back-references
class Stage:
    def __init__(self, pipeline):
        self._pipeline = weakref.ref(pipeline)

    @property
    def pipeline(self):
        return self._pipeline()

# 2. Force GC after large operations
def process_large_batch(images):
    results = []
    for img in images:
        results.append(pipeline.process(img))
        if len(results) % 10 == 0:
            gc.collect()  # break any cycles
    return results

# 3. Use context managers for scoped resources
import contextlib

@contextlib.contextmanager
def gpu_processing(backend):
    try:
        yield backend
    finally:
        if hasattr(backend, 'cleanup'):
            backend.cleanup()
        gc.collect()
```

---

## 9. Apple 统一内存与 MLX

### 9.1 统一内存架构（UMA）

Apple Silicon（M1-M4）使用统一内存，CPU 和 GPU 共享同一物理 RAM。关键影响：

- **无 CPU-GPU 拷贝**：CPU 和 GPU 原地访问数据
- **共享带宽**：内存带宽在所有计算单元间共享
- **固定池**：在 16 GB 系统上，CPU + GPU + OS 共享这 16 GB

### 9.2 MLX 内存管理

MLX（Apple 的 ML 框架）利用 UMA：

```python
import mlx.core as mx

# Memory pool control
mx.metal.set_memory_limit(0.8)  # Use up to 80% of unified memory
mx.metal.set_cache_limit(0.5)   # Cache up to 50% for reuse

# Force evaluation (free intermediates)
a = mx.array([1.0, 2.0, 3.0])
b = mx.exp(a)
mx.eval(b)  # Forces computation, can free lazy graph

# Synchronize
mx.synchronize()

# Memory info
print(f"Active memory: {mx.metal.get_active_memory() / 1024**2:.1f} MB")
print(f"Peak memory: {mx.metal.get_peak_memory() / 1024**2:.1f} MB")
print(f"Cache memory: {mx.metal.get_cache_memory() / 1024**2:.1f} MB")
```

### 9.3 MLX 惰性求值

MLX 使用惰性求值 -- 计算被延迟到调用 `mx.eval()` 时执行。这允许：
- **图优化**：融合操作，消除中间结果
- **降低峰值内存**：中间张量在被消费后即可释放
- **自动分块**：MLX 可以拆分大操作以适应内存

```python
import mlx.core as mx

# Lazy computation — nothing executes yet
a = mx.random.normal((10000, 10000))
b = mx.exp(a)
c = mx.softmax(b)

# Now execute — MLX optimizes the graph
mx.eval(c)
# a and b can potentially be freed during execution
```

### 9.4 Spektrafilm MLX 后端分析

`MlxBackend`（`mlx_backend.py`）未使用任何内存管理：

```python
class MlxBackend:
    def __init__(self, *, precision="float32"):
        import mlx.core as mx
        self.mx = mx
        # No memory limits, no cache management

    def synchronize(self):
        self.mx.synchronize()
```

**建议：**
1. 根据系统 RAM 设置内存限制
2. 调用 `mx.metal.set_cache_limit()` 防止无限制缓存
3. 在每个管线阶段后策略性地使用 `mx.eval()` 释放中间结果
4. 无需显式 `del` -- MLX 的惰性求值比 NumPy 处理得更好

### 9.5 MLX 与 CuPy 内存特性对比

| 方面 | MLX (Apple UMA) | CuPy (NVIDIA) |
|--------|-----------------|---------------|
| 内存模型 | CPU+GPU 共享 | 独立 VRAM |
| 传输开销 | 零（原地访问） | 显式 H2D/D2H |
| 池管理 | `set_memory_limit()` | `MemoryPool.set_limit()` |
| 惰性求值 | 是（图融合） | 否（即时执行） |
| 缓存 | 内置 | 内存池缓存 |
| OOM 行为 | 溢出到磁盘（交换） | 硬性 OOM 崩溃 |

---

## 10. 对 Spektrafilm 的建议

### 10.1 优先级 1：GPU 内存池管理（高影响，低工作量）

**问题：** CuPy 后端没有内存池管理。GPU 内存跨管线运行泄漏。

**修复：** 为 `CupyBackend` 添加池管理：

```python
# In cupy_backend.py
class CupyBackend:
    def __init__(self, *, precision="float32"):
        import cupy as cp
        self.cp = cp
        self._mempool = cp.get_default_memory_pool()
        self._pinned_pool = cp.get_default_pinned_memory_pool()

        # Set VRAM limit
        free, total = cp.cuda.Device().mem_info
        self._mempool.set_limit(int(total * 0.8))
        self.precision = precision
        self.default_dtype = cp.float32 if precision == "float32" else cp.float16

    def cleanup(self):
        """Free cached GPU memory blocks."""
        self._mempool.free_all_blocks()
        self._pinned_pool.free_all_blocks()
```

**并在处理完成后为管线添加清理**：

```python
# In pipeline.py, after process() returns
if hasattr(self._array_backend, 'cleanup'):
    self._array_backend.cleanup()
```

### 10.2 优先级 2：MLX 内存限制（macOS 高影响，低工作量）

```python
# In mlx_backend.py
class MlxBackend:
    def __init__(self, *, precision="float32"):
        import mlx.core as mx
        self.mx = mx
        # Set memory limits
        mx.metal.set_memory_limit(0.75)
        mx.metal.set_cache_limit(0.4)
```

### 10.3 优先级 3：内存分析基础设施（中等影响，低工作量）

添加可选的 tracemalloc 分析：

```python
# In pipeline.py
import os
import tracemalloc

_PROFILE_MEMORY = os.environ.get("SPEKTRAFILM_PROFILE_MEMORY", "0") == "1"

class SimulationPipeline:
    def process(self, image):
        if _PROFILE_MEMORY:
            tracemalloc.start(25)
            snap_before = tracemalloc.take_snapshot()

        result = self._process_internal(image)

        if _PROFILE_MEMORY:
            snap_after = tracemalloc.take_snapshot()
            current, peak = tracemalloc.get_traced_memory()
            top = snap_after.compare_to(snap_before, 'lineno')[:10]
            for stat in top:
                print(f"  {stat}")
            print(f"  Peak: {peak / 1024**2:.1f} MB")
            tracemalloc.stop()

        return result
```

### 10.4 优先级 4：预分配缓冲区池（中等影响，中等工作量）

为处理相同图像尺寸的管线阶段创建缓冲区池：

```python
class BufferPool:
    """Pre-allocated buffer pool for pipeline stages."""

    def __init__(self):
        self._buffers = {}

    def get(self, shape, dtype):
        key = (shape, dtype)
        if key not in self._buffers:
            self._buffers[key] = np.empty(shape, dtype=dtype)
        return self._buffers[key]

    def clear(self):
        self._buffers.clear()
```

### 10.5 优先级 5：大图像的内存映射 I/O（低影响，中等工作量）

对于大于 4K 的图像，使用内存映射加载以避免在 I/O 边界处内存翻倍：

```python
def load_image_smart(path, max_in_memory_pixels=33_000_000):
    """Load image, using memmap for very large files."""
    # Check file size
    import os
    file_size = os.path.getsize(path)
    estimated_pixels = file_size / 12  # assume float32 RGB

    if estimated_pixels > max_in_memory_pixels:
        # Use memory-mapped loading
        import tifffile
        return tifffile.memmap(path)
    else:
        return load_image_normal(path)
```

### 10.6 优先级 6：降低管线峰值内存（高影响，较高工作量）

管线目前同时持有 5-6 个完整数组。通过融合阶段可降至 3 个：

```python
# Current: 5 arrays alive during _pipeline_print
# rgb_image, log_raw_film, cmy_film, log_raw_print, cmy_print

# Fused: 3 arrays alive
def _pipeline_print_fused(self, rgb_image):
    # Expose + Develop in one pass (requires in-place develop)
    cmy_film = self._filming_stage.expose_and_develop(rgb_image)
    del rgb_image
    # Print expose + develop in one pass
    cmy_print = self._printing_stage.expose_and_develop(cmy_film)
    del cmy_film
    rgb_scan = self._scanning_stage.scan(cmy_print, ...)
    del cmy_print
    return rgb_scan
```

这是较大的重构（在代码审查中标记为 H3 -- 根据 CLAUDE.md 跳过）。

### 10.7 总结：按影响/工作量比排序

| 优先级 | 建议 | 影响 | 工作量 | 节省的内存 |
|----------|---------------|--------|--------|-------------|
| 1 | CuPy 内存池管理 | 高 | 低 | 防止 GPU 内存泄漏 |
| 2 | MLX 内存限制 | 高（macOS） | 低 | 防止 Apple Silicon 上的 OOM |
| 3 | tracemalloc 分析标志 | 中 | 低 | 启用诊断 |
| 4 | 管线阶段缓冲区池 | 中 | 中 | 峰值降低约 20-30% |
| 5 | 内存映射 I/O | 低 | 中 | 帮助处理 >4K 图像 |
| 6 | 融合管线阶段 | 高 | 高 | 峰值降低约 40% |

---

## 附录 A：内存占用参考卡片

```
Image size guide (float32, 3 channels):
  1920x1080 (2K):    24 MB per array
  3840x2160 (4K):    96 MB per array
  6000x4000 (6K):   280 MB per array
  7680x4320 (8K):   388 MB per array
  12000x8000 (12K): 1.1 GB per array

Pipeline peak = ~5x single array size
With LUTs = ~7x single array size
GPU tile budget default = 2M pixels = 24 MB per tile
```

## 附录 B：关键文档来源

- Python tracemalloc: https://docs.python.org/3/library/tracemalloc.html
- memray (Bloomberg): https://bloomberg.github.io/memray/
- NumPy memmap: https://numpy.org/doc/stable/reference/generated/numpy.memmap.html
- CuPy Memory Management: https://docs.cupy.dev/en/stable/reference/memory.html
- MLX Unified Memory: https://ml-explore.github.io/mlx/
- Zarr: https://zarr.readthedocs.io/
- Python gc module: https://docs.python.org/3/library/gc.html
- PEP 442 (Safe finalization): https://peps.python.org/pep-0442/
