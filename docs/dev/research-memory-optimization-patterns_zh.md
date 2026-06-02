# Spektrafilm 内存优化模式

> 这是英文原文的中文翻译。权威版本请参考英文原文。

研究文档，涵盖适用于光谱图像模拟流水线的内存高效模式。所有模式均在 **零精度/质量损失** 的约束下进行评估——不使用近似值，全程使用 float32，各后端结果完全一致。

## 目录

1. [惰性求值与生成器流水线](#1-惰性求值与生成器流水线)
2. [原地操作与零拷贝技术](#2-原地操作与零拷贝技术)
3. [内存高效数据结构](#3-内存高效数据结构)
4. [重复操作的缓存策略](#4-重复操作的缓存策略)
5. [流式/分块处理](#5-流式分块处理)
6. [GPU 内存池管理 (CuPy)](#6-gpu-内存池管理-cupy)
7. [共享内存与多进程](#7-共享内存与多进程)
8. [Spektrafilm 特定应用模式](#8-spektrafilm-特定应用模式)

---

## 1. 惰性求值与生成器流水线

### 核心概念

生成器按需产生值，而非实例化整个集合。对于图像处理流水线中每个阶段都变换全分辨率数组的情况，惰性求值可避免同时持有多个全尺寸中间结果。

### 模式：流水线阶段的生成器链

```python
def pipeline_stages(image, stages):
    """Yield intermediate results lazily through pipeline stages."""
    current = image
    for stage in stages:
        current = stage.process(current)
        yield current  # caller can discard previous stage's output
```

### 模式：`itertools.islice` 用于批处理惰性处理

```python
import itertools

def batched(iterable, n):
    """Yield successive n-sized chunks from iterable (Python 3.12+ has itertools.batched)."""
    it = iter(iterable)
    while True:
        batch = list(itertools.islice(it, n))
        if not batch:
            break
        yield batch
```

### 模式：`yield from` 用于简洁委托

```python
def process_tiles(image, tile_size):
    """Delegate tile processing without materializing all tiles."""
    tiles = split_into_tiles(image, tile_size)
    yield from (process_tile(t) for t in tiles)
```

### 在 Spektrafilm 中的应用

流水线阶段（拍摄 -> 印刷 -> 扫描）各自变换整幅图像。生成器方法对单幅图像处理没有帮助，但对 **批量处理** 多幅图像或 **基于分块的 GPU 处理** 很有价值：

```python
# 当前模式：所有分块被实例化
tiles = [process_tile(t) for t in all_tiles]
result = reassemble(tiles)

# 内存高效：一次处理一个分块
def process_tiles_lazy(tiles):
    for tile in tiles:
        yield process_tile(tile)
result = reassemble(process_tiles_lazy(tiles))
```

### 注意事项

- 当中间结果可以被丢弃时，生成器链是有益的
- 对于单次全图遍历，图像本身就是瓶颈——生成器不会降低图像数组的峰值内存
- 对批量/迭代工作流和基于分块的处理最有价值

---

## 2. 原地操作与零拷贝技术

### 核心概念

NumPy 操作可以创建新数组（拷贝）或修改现有数组（原地操作）。对于大型 float32 图像（4000x6000x4 约 96 MB），避免拷贝至关重要。

### 模式：通用函数中的 `out` 参数

```python
# 不好：创建临时数组
result = image * 2.0
result = np.clip(result, 0.0, 1.0)

# 好：原地操作，无分配
np.multiply(image, 2.0, out=image)
np.clip(image, 0.0, 1.0, out=image)
```

### 模式：复合原地操作

```python
# 不好：两个临时变量
temp = image * scale
result = temp + offset

# 好：单次原地链
np.multiply(image, scale, out=image)
np.add(image, offset, out=image)
```

### 模式：`np.copyto` 用于受控拷贝

```python
# 重用现有缓冲区，而非分配新缓冲区
output_buffer = np.empty_like(image)
np.copyto(output_buffer, image)  # 无新分配
```

### 模式：`astype` 配合 `copy=False`

```python
# 当 dtype 已匹配时避免拷贝
result = np.asarray(image, dtype=np.float32)  # 如果已是 float32 则为视图
result = image.astype(np.float32, copy=False)  # 相同——如果可能则为视图
```

### 模式：基于视图的切片

```python
# 切片创建视图（零拷贝）
roi = image[100:200, 100:200]  # 无分配，与 image 共享内存

# 花式索引创建拷贝
mask = image > 0.5
selected = image[mask]  # 分配了新数组
```

### Spektrafilm 相关性

流水线已在多处使用 `astype(np.float32, copy=False)`（例如 `pipeline.py:98`）。关键优化机会：

```python
# 在 _scene_luminance_y (pipeline.py:85-99) 中：
# 当前：创建 xyz 中间变量，然后提取亮度
xyz = colour.RGB_to_XYZ(rgb, ...)  # 全部 HxWx3 float32
luminance = xyz[..., 1]             # 视图，但 xyz 仍被分配

# 优化：如果只需要 Y，直接计算 Y
# （已有回退路径通过 tensordot 实现）
```

### Spektrafilm 特定：预分配流水线缓冲区

```python
class PipelineBuffers:
    """Pre-allocate working buffers for the pipeline to avoid per-stage allocation."""

    def __init__(self, shape, dtype=np.float32):
        self.staging_a = np.empty(shape, dtype=dtype)
        self.staging_b = np.empty(shape, dtype=dtype)
        self._active = self.staging_a

    def swap(self):
        """Swap active buffer (ping-pong pattern)."""
        self._active = self.staging_b if self._active is self.staging_a else self.staging_a
        return self._active
```

### 应避免的反模式

```python
# 不好：累加器模式创建 N 个临时变量
result = image
for operation in operations:
    result = operation(result)  # 每次都分配新空间

# 好：原地链
for operation in operations:
    operation.apply_in_place(image)
```

---

## 3. 内存高效数据结构

### 数据类上的 `__slots__`

Spektrafilm 已广泛使用 `@dataclass(frozen=True, slots=True)`（例如 `HDRPhotoMapping`、`HDRSceneEnergyMetadata`、`SimulationPipelineResult`）。这是正确的模式。

**内存节省**：`__slots__` 消除了每个实例的 `__dict__`，每个实例节省约 100+ 字节。对于字段很多的数据类，效果显著。

```python
# 不使用 slots：每个实例有 __dict__（约 104+ 字节开销）
@dataclass
class HeavyConfig:
    a: float = 1.0
    b: float = 2.0

# 使用 slots：紧凑的类元组存储
@dataclass(slots=True)
class LightConfig:
    a: float = 1.0
    b: float = 2.0

# 典型节省：每个实例 40-60%
```

### `frozen=True` 用于可哈希性和安全性

冻结数据类默认不可变且可哈希。这使得安全缓存成为可能，并防止对共享状态的意外修改。

```python
@dataclass(frozen=True, slots=True)
class HDRPhotoMapping:
    # 所有字段不可变——可安全缓存，可安全共享
    hdr_mapping_mode: str = "generic"
    preserve_sdr_base: bool = True
    # ...
```

### NumPy 结构化数组与字典对比

对于大型参数类对象集合，结构化数组比等效的字典列表少用 5-10 倍内存。

```python
# 不好：字典列表（装箱的 Python 对象，每条记录约 200+ 字节）
params = [{"exposure": 1.0, "contrast": 0.5} for _ in range(100000)]

# 好：结构化数组（连续、无装箱，每条记录约 16 字节）
dt = np.dtype([("exposure", np.float32), ("contrast", np.float32)])
params = np.zeros(100000, dtype=dt)
params["exposure"] = 1.0
params["contrast"] = 0.5
```

### 在 Spektrafilm 中的应用

`HDRPhotoMapping` 数据类有约 50+ 个字段。作为 frozen+slots 数据类，每个实例已经是紧凑的。问题在于创建 **大量实例** 时（例如在测试或批量处理中）。由于这些是值对象，可以重用：

```python
# 缓存常用的映射配置
_DEFAULT_MAPPING = HDRPhotoMapping()  # 默认配置的单例

def get_mapping(**overrides):
    """Return cached default or create with overrides."""
    if not overrides:
        return _DEFAULT_MAPPING
    return HDRPhotoMapping(**overrides)
```

---

## 4. 重复操作的缓存策略

### `functools.lru_cache` 对大型数组的问题

`lru_cache` 持有 **强引用**，阻止缓存的 numpy 数组被垃圾回收。对于 4000x6000 的 float32 图像（约 96 MB），这意味着缓存可能持有已不需要的数 GB 数组。

```python
# 不好：强引用阻止 GC
@functools.lru_cache(maxsize=16)
def compute_lut(film_name, resolution):
    return expensive_lut_computation(film_name, resolution)
```

### 模式：弱引用 LRU 缓存

```python
import weakref
from collections import OrderedDict

class WeakLRUCache:
    """LRU cache that holds weak references — cached objects can be GC'd."""

    def __init__(self, maxsize=128):
        self.maxsize = maxsize
        self._cache = OrderedDict()

    def get(self, key):
        if key in self._cache:
            ref = self._cache[key]
            obj = ref()
            if obj is not None:
                self._cache.move_to_end(key)
                return obj
            else:
                del self._cache[key]  # GC'd — remove stale entry
        return None

    def set(self, key, value):
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = weakref.ref(value)
        if len(self._cache) > self.maxsize:
            self._cache.popitem(last=False)

    def __contains__(self, key):
        return self.get(key) is not None
```

### 模式：`weakref.WeakValueDictionary` 用于简单场景

```python
import weakref

_lut_cache = weakref.WeakValueDictionary()

def get_lut(film_name, resolution):
    key = (film_name, resolution)
    lut = _lut_cache.get(key)
    if lut is None:
        lut = expensive_computation(film_name, resolution)
        _lut_cache[key] = lut
    return lut
```

### 模式：基于磁盘的缓存用于昂贵计算

```python
import hashlib
import pickle
from pathlib import Path

class DiskCache:
    """Cache expensive computations to disk — survives process restarts."""

    def __init__(self, cache_dir: Path, max_entries: int = 256):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_entries = max_entries

    def _key_path(self, key: str) -> Path:
        h = hashlib.sha256(key.encode()).hexdigest()[:16]
        return self.cache_dir / f"{h}.pkl"

    def get(self, key: str):
        path = self._key_path(key)
        if path.exists():
            with open(path, "rb") as f:
                return pickle.load(f)
        return None

    def set(self, key: str, value):
        path = self._key_path(key)
        with open(path, "wb") as f:
            pickle.dump(value, f, protocol=pickle.HIGHEST_PROTOCOL)
        self._evict_if_needed()

    def _evict_if_needed(self):
        files = sorted(self.cache_dir.glob("*.pkl"), key=lambda p: p.stat().st_atime)
        while len(files) > self.max_entries:
            files.pop(0).unlink()
```

### Spektrafilm 应用：LUT 服务缓存

`SpectralLUTService` 已经缓存 LUT。关键优化是确保 LUT 在流水线实例之间共享：

```python
# pipeline.py:228-237 中的当前模式
# 当分辨率和后端匹配时重用 LUT 服务
can_reuse_lut_service = (
    reused_lut_service is not None
    and reused_lut_service.lut_resolution == self.settings.lut_resolution
    and type(reused_backend) is type(self._array_backend)
)
```

这已经是好的模式。额外的优化是模块级弱引用缓存，使得 LUT 即使在流水线本身被 GC 回收后也能在流水线实例间存活：

```python
# 模块级 LUT 缓存，使用弱引用
_global_lut_cache = weakref.WeakValueDictionary()

class SpectralLUTService:
    def __init__(self, resolution, gpu_backend=None):
        cache_key = (resolution, type(gpu_backend).__name__)
        cached = _global_lut_cache.get(cache_key)
        if cached is not None:
            self._lut = cached
        else:
            self._lut = self._compute_lut(resolution, gpu_backend)
            _global_lut_cache[cache_key] = self._lut
```

### Spektrafilm 应用：配置文件特性化缓存

`characterize_pipeline_profile`（pipeline.py:163）创建临时流水线并通过它运行渐变。这很昂贵。结果仅依赖于流水线参数，因此可以缓存：

```python
import functools

# 基于流水线参数哈希的缓存
@functools.lru_cache(maxsize=8)
def _cached_characterize(params_hash: str, pipeline_cls_name: str):
    # ... expensive computation ...
    return scene_y, look_y
```

---

## 5. 流式/分块处理

### 模式：NumPy `memmap` 用于大型文件

```python
import numpy as np

# 内存映射大型图像文件——仅在访问时加载页面
mmap_arr = np.memmap(
    'large_image.dat',
    dtype='float32',
    mode='r',
    shape=(6000, 4000, 3)
)

# 分块处理——同时只有一个块在内存中
chunk_height = 512
for y in range(0, mmap_arr.shape[0], chunk_height):
    chunk = np.array(mmap_arr[y:y+chunk_height])  # 仅实例化此块
    result = process(chunk)
    # 将结果写入输出...
```

### 模式：带重叠的分块处理

```python
def process_tiled(image, tile_size, overlap, process_fn):
    """Process image in overlapping tiles to avoid edge artifacts."""
    h, w = image.shape[:2]
    step = tile_size - overlap
    results = np.empty_like(image)

    for y in range(0, h, step):
        for x in range(0, w, step):
            # 提取带重叠的分块
            y1 = max(0, y - overlap)
            y2 = min(h, y + tile_size + overlap)
            x1 = max(0, x - overlap)
            x2 = min(w, x + tile_size + overlap)

            tile = image[y1:y2, x1:x2]  # 视图，无拷贝
            processed_tile = process_fn(tile)

            # 仅回写非重叠区域
            ry1 = y - y1
            ry2 = ry1 + min(tile_size, h - y)
            rx1 = x - x1
            rx2 = rx1 + min(tile_size, w - x)
            results[y:y+ry2-ry1, x:x+rx2-rx1] = processed_tile[ry1:ry2, rx1:rx2]

    return results
```

### 模式：`multiprocessing.shared_memory` 用于并行处理

```python
from multiprocessing import shared_memory
import numpy as np

def create_shared_array(shape, dtype=np.float32):
    """Create a shared memory buffer backed by a numpy array."""
    nbytes = int(np.prod(shape)) * np.dtype(dtype).itemsize
    shm = shared_memory.SharedMemory(create=True, size=nbytes)
    arr = np.ndarray(shape, dtype=dtype, buffer=shm.buf)
    return shm, arr

def worker_process(shm_name, shape, dtype, slice_def):
    """Worker that reads from shared memory — no copy needed."""
    existing_shm = shared_memory.SharedMemory(name=shm_name)
    arr = np.ndarray(shape, dtype=dtype, buffer=existing_shm.buf)
    chunk = arr[slice_def]  # 视图，指向共享内存
    result = process(chunk)
    existing_shm.close()
    return result

# 父进程
shm, shared_img = create_shared_array(image.shape)
shared_img[:] = image[:]  # 一次性拷贝到共享内存
# ... 使用 shm.name 分发工作进程 ...
shm.close()
shm.unlink()
```

### Spektrafilm 应用：基于分块的 GPU 处理

流水线已有基于分块的 GPU 处理基础设施（`_gpu_tile_pixels`、`_image_pixel_count`）。GPU 分块独立处理——这是内存受限 GPU 处理的正确模式：

```python
# 当前模式 (pipeline.py:56-66)
DEFAULT_GPU_TILE_PIXELS = 2_000_000  # float32 RGB 约 24 MB

def _gpu_tile_pixels() -> int:
    raw_limit = os.environ.get(GPU_TILE_PIXELS_ENV)
    if raw_limit is None:
        return DEFAULT_GPU_TILE_PIXELS
    return int(raw_limit)
```

### Spektrafilm 应用：HDR Sidecar 流式处理（H3 修复）

H3 发现表明 `scene_luminance` 和 `scene_rgb` sidecar 始终被计算，对 4000x6000 图像增加约 366 MiB。修复方案是使 sidecar 收集变为惰性/按需的：

```python
@dataclass(frozen=True, slots=True)
class HDRSceneEnergyMetadata:
    scene_luminance: np.ndarray | None = None  # 惰性——仅在需要时计算
    scene_rgb: np.ndarray | None = None         # 惰性——仅在需要时计算
    # ... 标量字段开销很小 ...

def process_with_metadata(image, *, collect_sidecars=False):
    """Process image, optionally collecting HDR sidecars."""
    result_image = process(image)

    if not collect_sidecars:
        return SimulationPipelineResult(image=result_image, hdr_scene_energy=None)

    # 仅在明确请求时计算昂贵的 sidecar
    scene_luminance = _compute_scene_luminance(image)
    scene_rgb = _compute_scene_rgb(image)
    return SimulationPipelineResult(
        image=result_image,
        hdr_scene_energy=HDRSceneEnergyMetadata(
            scene_luminance=scene_luminance,
            scene_rgb=scene_rgb,
            # ...
        ),
    )
```

---

## 6. GPU 内存池管理 (CuPy)

### 核心 API

```python
import cupy as cp

# 获取默认内存池
pool = cp.get_default_memory_pool()

# 监控使用情况
print(f"Used:      {pool.used_bytes() / 1e6:.1f} MB")
print(f"Total:     {pool.total_bytes() / 1e6:.1f} MB")
print(f"Free blocks: {pool.n_free_blocks()}")  # 数量高意味着碎片化

# 将所有缓存块释放回 CUDA
pool.free_all_blocks()

# 设置内存限制以防止 OOM
pool.set_limit(size=4 * 1024**3)  # 4 GB 限制
```

### 模式：流水线中的显式内存管理

```python
class CuPyMemoryManager:
    """Context manager for CuPy memory lifecycle."""

    def __init__(self, limit_bytes=None):
        self.limit_bytes = limit_bytes
        self.pool = cp.get_default_memory_pool()

    def __enter__(self):
        if self.limit_bytes:
            self.pool.set_limit(size=self.limit_bytes)
        return self

    def __exit__(self, *exc):
        self.pool.free_all_blocks()  # 退出时整理碎片

    def stats(self):
        return {
            "used_bytes": self.pool.used_bytes(),
            "total_bytes": self.pool.total_bytes(),
            "n_free_blocks": self.pool.n_free_blocks(),
        }
```

### 模式：重用 GPU 缓冲区

```python
def process_gpu_tiled(image, tile_size, backend):
    """Process image on GPU with pre-allocated tile buffers."""
    pool = cp.get_default_memory_pool()

    # 预分配 GPU 分块缓冲区
    gpu_tile_in = cp.empty((tile_size, tile_size, 3), dtype=cp.float32)
    gpu_tile_out = cp.empty((tile_size, tile_size, 3), dtype=cp.float32)

    results = []
    for tile_cpu in split_tiles(image, tile_size):
        gpu_tile_in.set(tile_cpu)  # Host -> Device，重用缓冲区
        gpu_result = process_on_gpu(gpu_tile_in)
        gpu_tile_out[:] = gpu_result  # 重用输出缓冲区
        results.append(gpu_tile_out.get())  # Device -> Host

    # 清理
    del gpu_tile_in, gpu_tile_out
    pool.free_all_blocks()

    return reassemble_tiles(results)
```

### 模式：自定义分配器用于精细控制

```python
import cupy as cp

# 使用具有特定分配策略的自定义内存池
def create_managed_pool(size_limit):
    """Create a CuPy memory pool with a size limit."""
    pool = cp.cuda.MemoryPool()
    pool.set_limit(size=size_limit)
    cp.cuda.set_allocator(pool.malloc)
    return pool

# 用法
pool = create_managed_pool(8 * 1024**3)  # 8 GB
try:
    result = process_on_gpu(data)
finally:
    pool.free_all_blocks()
```

### Spektrafilm 应用

流水线已选择 GPU 后端并分块处理。关键新增功能是显式内存池管理：

```python
# 在 SimulationPipeline.process() 中：
if self._array_backend.is_gpu:
    pool = self._array_backend.get_memory_pool()
    try:
        result = self._run_pipeline(image)
    finally:
        pool.free_all_blocks()  # 每张图片后整理碎片
```

---

## 7. 共享内存与多进程

### 模式：`multiprocessing.shared_memory` 用于零拷贝共享

```python
from multiprocessing import shared_memory, Process
import numpy as np

def create_shared_numpy_array(shape, dtype=np.float32, name=None):
    """Create a numpy array backed by shared memory."""
    itemsize = np.dtype(dtype).itemsize
    nbytes = int(np.prod(shape)) * itemsize
    shm = shared_memory.SharedMemory(create=True, size=nbytes, name=name)
    arr = np.ndarray(shape, dtype=dtype, buffer=shm.buf)
    return shm, arr

def attach_shared_numpy_array(shape, dtype, name):
    """Attach to an existing shared memory array by name."""
    shm = shared_memory.SharedMemory(name=name)
    arr = np.ndarray(shape, dtype=dtype, buffer=shm.buf)
    return shm, arr
```

### 模式：共享内存流水线

```python
def parallel_pipeline(image, num_workers=4):
    """Process image in parallel using shared memory."""
    shm, shared_img = create_shared_numpy_array(image.shape, image.dtype)
    shared_img[:] = image

    # 每个工作进程从共享内存读取，写入自己的结果
    chunks = np.array_split(range(image.shape[0]), num_workers)
    results = []

    for chunk_slices in chunks:
        shm_name, shape, dtype = shm.name, shared_img.shape, shared_img.dtype
        # 工作进程连接共享内存——无需序列化
        result = worker(shm_name, shape, dtype, chunk_slices)
        results.append(result)

    shm.close()
    shm.unlink()
    return np.concatenate(results)
```

### 模式：`mmap` 用于基于文件的处理

```python
import mmap
import numpy as np

def process_large_image_mmap(filepath, shape, dtype=np.float32):
    """Process a large image file without loading it entirely into memory."""
    itemsize = np.dtype(dtype).itemsize
    total_bytes = int(np.prod(shape)) * itemsize

    with open(filepath, 'rb') as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        arr = np.ndarray(shape, dtype=dtype, buffer=mm)

        # 分块处理
        chunk_h = 512
        for y in range(0, shape[0], chunk_h):
            chunk = np.array(arr[y:y+chunk_h])  # 实例化块
            result = process(chunk)
            yield y, result

        mm.close()
```

### Spektrafilm 应用

共享内存对 GUI 最有价值，其中预览和全分辨率处理可能并行运行，或用于批量处理多幅图像。当前架构是单线程的，因此这是未来的优化方向。

---

## 8. Spektrafilm 特定应用模式

### 优先级 1：HDR Sidecar 内存压力（H3 修复）

**问题**：`process_with_metadata` 始终计算 `scene_luminance`（HxW float32，4000x6000 约 96 MB）和 `scene_rgb`（HxWx3 float32，约 288 MB）。每张图片的 sidecar 总开销约 384 MB。

**方案 A——惰性 Sidecar 收集**（不改变 API）：

```python
@dataclass(frozen=True, slots=True)
class HDRSceneEnergyMetadata:
    # 保留标量字段（开销小）
    diffuse_white_estimate: float = 0.0
    headroom_estimate: float = 1.0
    auto_exposure_ev: float = 0.0
    method: str = ""
    confidence: str = ""
    # 数组变为惰性——存储计算闭包而非数据
    _scene_luminance_factory: object = None  # 返回 np.ndarray 的可调用对象
    _scene_rgb_factory: object = None
    _profile_scene_y_factory: object = None
    _profile_look_y_factory: object = None

    @property
    def scene_luminance(self) -> np.ndarray:
        if self._scene_luminance_factory is not None:
            return self._scene_luminance_factory()
        raise AttributeError("scene_luminance not requested")

    @property
    def scene_rgb(self) -> np.ndarray:
        if self._scene_rgb_factory is not None:
            return self._scene_rgb_factory()
        raise AttributeError("scene_rgb not requested")
```

**方案 B——显式标志**（API 变更，更简洁）：

```python
@dataclass(frozen=True, slots=True)
class SimulationRequest:
    image: np.ndarray
    collect_hdr_metadata: bool = False  # 默认：不收集 sidecar（节省约 384 MB）

def process_with_metadata(self, request: SimulationRequest):
    result_image = self.process(request.image)

    if not request.collect_hdr_metadata:
        return SimulationPipelineResult(image=result_image)

    # 仅在明确请求时计算 sidecar
    sidecars = self._compute_hdr_sidecars(request.image)
    return SimulationPipelineResult(image=result_image, hdr_scene_energy=sidecars)
```

### 优先级 2：流水线缓冲区重用

**问题**：每个流水线阶段分配新数组。对于 3 阶段流水线（拍摄、印刷、扫描），这意味着工作内存中 3 倍图像大小加上输出。

**方案**：乒乓缓冲区模式：

```python
class PipelineBuffers:
    """Pre-allocated ping-pong buffers for pipeline stages."""

    def __init__(self, shape, dtype=np.float32):
        self._buf_a = np.empty(shape, dtype=dtype)
        self._buf_b = np.empty(shape, dtype=dtype)
        self._active = 0

    @property
    def current(self):
        return self._buf_a if self._active == 0 else self._buf_b

    @property
    def next(self):
        return self._buf_b if self._active == 0 else self._buf_a

    def swap(self):
        self._active = 1 - self._active
```

### 优先级 3：弱引用 LUT 缓存

**问题**：LUT 数组很大（高分辨率时数百 MB）。当流水线实例被 GC 回收时，下一个实例可能需要重新计算 LUT。

**方案**：模块级弱引用缓存：

```python
import weakref

_lut_cache = weakref.WeakValueDictionary()

class SpectralLUTService:
    def __init__(self, resolution, gpu_backend=None):
        cache_key = (resolution, type(gpu_backend).__name__)
        cached = _lut_cache.get(cache_key)
        if cached is not None:
            self._lut = cached
        else:
            self._lut = self._compute_lut(resolution, gpu_backend)
            _lut_cache[cache_key] = self._lut
```

### 优先级 4：原地 HDR 映射操作

**问题**：HDR 映射函数创建多个中间数组（scene_luminance、normalized、tone-mapped 等）。

**方案**：预分配工作缓冲区并使用 `out=` 参数：

```python
def apply_hdr_mapping_in_place(
    image: np.ndarray,
    scene_luminance: np.ndarray,
    mapping: HDRPhotoMapping,
    buffers: PipelineBuffers | None = None,
) -> np.ndarray:
    """Apply HDR mapping using in-place operations."""
    # 使用预分配的缓冲区或创建临时缓冲区
    if buffers is None:
        norm_lum = np.empty_like(scene_luminance)
    else:
        norm_lum = buffers.current

    # 原地归一化
    np.divide(scene_luminance, mapping.diffuse_white, out=norm_lum)
    np.clip(norm_lum, 0.0, None, out=norm_lum)

    # 原地色调映射
    np.multiply(image, compute_gain(norm_lum, mapping), out=image)

    return image
```

### 优先级 5：CuPy 内存池集成

**问题**：分块处理期间反复分配/释放导致 GPU 内存碎片化。

**方案**：每次流水线运行的显式池管理：

```python
class SimulationPipeline:
    def process(self, image):
        if self._array_backend.is_gpu:
            pool = self._array_backend.get_memory_pool()
            pool.free_all_blocks()  # 清空开始
            try:
                return self._run_pipeline(image)
            finally:
                pool.free_all_blocks()  # 运行后整理碎片
        return self._run_pipeline(image)
```

---

## 总结：快速收益（不改变 API）

| 模式 | 节省内存 | 工作量 | 风险 |
|------|---------|--------|------|
| 到处使用 `astype(copy=False)` | 避免冗余拷贝 | 低 | 无 |
| HDR 映射中的原地 `out=` | 每阶段约 96-288 MB | 低 | 低 |
| 所有数据类使用 `__slots__` | 已完成 | 无 | 无 |
| 弱引用 LUT 缓存 | 防止 LUT 重新计算 | 中 | 低 |
| 惰性 HDR sidecar 收集 | 每张图片约 384 MB | 中 | 中 |
| 乒乓流水线缓冲区 | 每阶段约 96 MB | 中 | 低 |
| CuPy 池 `free_all_blocks()` | 减少碎片化 | 低 | 无 |
| 预分配 GPU 分块缓冲区 | 减少分配波动 | 中 | 低 |

## 总结：架构变更（需要 API 变更）

| 模式 | 节省内存 | 工作量 | 风险 |
|------|---------|--------|------|
| `SimulationRequest.collect_hdr_metadata` 标志 | 每次预览约 384 MB | 中 | 中 |
| 基于生成器的批量处理 | 批量处理从 O(N) 变为 O(1) | 高 | 中 |
| 并行处理的共享内存 | 实现真正的并行 | 高 | 高 |
| `np.memmap` 用于磁盘支持的图像 | 支持超 RAM 的图像 | 高 | 高 |

---

## 参考资料

- NumPy `out` 参数：https://numpy.org/doc/stable/reference/ufuncs.html#ufuncs
- NumPy `memmap`：https://numpy.org/doc/stable/reference/generated/numpy.memmap.html
- Python `weakref`：https://docs.python.org/3/library/weakref.html
- Python `multiprocessing.shared_memory`：https://docs.python.org/3/library/multiprocessing.shared_memory.html
- CuPy 内存管理：https://docs.cupy.dev/en/stable/reference/memory.html
- Python `__slots__`：https://docs.python.org/3/reference/datamodel.html#slots
- Dataclasses `slots=True`：https://docs.python.org/3/library/dataclasses.html
- Dask arrays：https://docs.dask.org/en/stable/array.html
