# Memory Optimization Patterns for Spektrafilm

Research document covering memory-efficient patterns applicable to the spectral image simulation pipeline. All patterns are evaluated against the constraint of **zero precision/quality loss** — no approximations, float32 throughout, identical results across backends.

## Table of Contents

1. [Lazy Evaluation & Generator Pipelines](#1-lazy-evaluation--generator-pipelines)
2. [In-Place Operations & Zero-Copy Techniques](#2-in-place-operations--zero-copy-techniques)
3. [Memory-Efficient Data Structures](#3-memory-efficient-data-structures)
4. [Caching Strategies for Repeated Operations](#4-caching-strategies-for-repeated-operations)
5. [Streaming/Chunked Processing](#5-streamingchunked-processing)
6. [GPU Memory Pool Management (CuPy)](#6-gpu-memory-pool-management-cupy)
7. [Shared Memory & Multiprocessing](#7-shared-memory--multiprocessing)
8. [Spektrafilm-Specific Application Patterns](#8-spektrafilm-specific-application-patterns)

---

## 1. Lazy Evaluation & Generator Pipelines

### Core Concept

Generators produce values on-demand rather than materializing entire collections. For image processing pipelines where each stage transforms a full-resolution array, lazy evaluation avoids holding multiple full-size intermediates simultaneously.

### Pattern: Generator Chain for Pipeline Stages

```python
def pipeline_stages(image, stages):
    """Yield intermediate results lazily through pipeline stages."""
    current = image
    for stage in stages:
        current = stage.process(current)
        yield current  # caller can discard previous stage's output
```

### Pattern: `itertools.islice` for Batched Lazy Processing

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

### Pattern: `yield from` for Clean Delegation

```python
def process_tiles(image, tile_size):
    """Delegate tile processing without materializing all tiles."""
    tiles = split_into_tiles(image, tile_size)
    yield from (process_tile(t) for t in tiles)
```

### Application to Spektrafilm

The pipeline stages (filming → printing → scanning) each transform the full image. A generator approach doesn't help for single-image processing, but matters for **batch processing** multiple images or **tile-based GPU processing**:

```python
# Current pattern: all tiles materialized
tiles = [process_tile(t) for t in all_tiles]
result = reassemble(tiles)

# Memory-efficient: one tile at a time
def process_tiles_lazy(tiles):
    for tile in tiles:
        yield process_tile(tile)
result = reassemble(process_tiles_lazy(tiles))
```

### Caveats

- Generator chains are beneficial when intermediate results can be discarded
- For single full-image passes, the image itself is the bottleneck — generators don't reduce peak memory of the image array
- Most valuable for batch/iterative workflows and tile-based processing

---

## 2. In-Place Operations & Zero-Copy Techniques

### Core Concept

NumPy operations can either create new arrays (copy) or modify existing ones (in-place). For large float32 images (~96 MB for 4000×6000×4), avoiding copies is critical.

### Pattern: `out` Parameter in Ufuncs

```python
# BAD: creates temporary array
result = image * 2.0
result = np.clip(result, 0.0, 1.0)

# GOOD: in-place, no allocation
np.multiply(image, 2.0, out=image)
np.clip(image, 0.0, 1.0, out=image)
```

### Pattern: Compound In-Place Operations

```python
# BAD: two temporaries
temp = image * scale
result = temp + offset

# GOOD: single in-place chain
np.multiply(image, scale, out=image)
np.add(image, offset, out=image)
```

### Pattern: `np.copyto` for Controlled Copy

```python
# Reuse existing buffer instead of allocating new one
output_buffer = np.empty_like(image)
np.copyto(output_buffer, image)  # No new allocation
```

### Pattern: `astype` with `copy=False`

```python
# Avoid copy when dtype already matches
result = np.asarray(image, dtype=np.float32)  # view if already float32
result = image.astype(np.float32, copy=False)  # same — view if possible
```

### Pattern: View-Based Slicing

```python
# Slicing creates views (zero-copy)
roi = image[100:200, 100:200]  # No allocation, shares memory with image

# Fancy indexing creates copies
mask = image > 0.5
selected = image[mask]  # NEW array allocated
```

### Spektrafilm Relevance

The pipeline already uses `astype(np.float32, copy=False)` in several places (e.g., `pipeline.py:98`). Key opportunities:

```python
# In _scene_luminance_y (pipeline.py:85-99):
# Current: creates xyz intermediate, then extracts luminance
xyz = colour.RGB_to_XYZ(rgb, ...)  # full HxWx3 float32
luminance = xyz[..., 1]             # view, but xyz still allocated

# Optimization: if only Y is needed, compute Y directly
# (already has fallback path that does this via tensordot)
```

### Spektrafilm-Specific: Pre-Allocated Pipeline Buffers

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

### Anti-Patterns to Avoid

```python
# BAD: accumulator pattern creates N temporaries
result = image
for operation in operations:
    result = operation(result)  # new allocation each time

# GOOD: in-place chain
for operation in operations:
    operation.apply_in_place(image)
```

---

## 3. Memory-Efficient Data Structures

### `__slots__` on Dataclasses

Spektrafilm already uses `@dataclass(frozen=True, slots=True)` extensively (e.g., `HDRPhotoMapping`, `HDRSceneEnergyMetadata`, `SimulationPipelineResult`). This is the correct pattern.

**Memory savings**: `__slots__` eliminates per-instance `__dict__`, saving ~100+ bytes per instance. For dataclasses with many fields, this adds up.

```python
# Without slots: each instance has __dict__ (~104+ bytes overhead)
@dataclass
class HeavyConfig:
    a: float = 1.0
    b: float = 2.0

# With slots: compact tuple-like storage
@dataclass(slots=True)
class LightConfig:
    a: float = 1.0
    b: float = 2.0

# Typical savings: 40-60% per instance
```

### `frozen=True` for Hashability and Safety

Frozen dataclasses are immutable and hashable by default. This enables safe caching and prevents accidental mutation of shared state.

```python
@dataclass(frozen=True, slots=True)
class HDRPhotoMapping:
    # All fields immutable — safe to cache, safe to share
    hdr_mapping_mode: str = "generic"
    preserve_sdr_base: bool = True
    # ...
```

### NumPy Structured Arrays vs. Dicts

For large collections of parameter-like objects, structured arrays use 5-10× less memory than equivalent lists of dicts.

```python
# BAD: list of dicts (boxed Python objects, ~200+ bytes per record)
params = [{"exposure": 1.0, "contrast": 0.5} for _ in range(100000)]

# GOOD: structured array (contiguous, unboxed, ~16 bytes per record)
dt = np.dtype([("exposure", np.float32), ("contrast", np.float32)])
params = np.zeros(100000, dtype=dt)
params["exposure"] = 1.0
params["contrast"] = 0.5
```

### Application to Spektrafilm

The `HDRPhotoMapping` dataclass has ~50+ fields. As a frozen+slots dataclass, each instance is already compact. The issue is when **many instances** are created (e.g., in tests or batch processing). Since these are value objects, they can be reused:

```python
# Cache commonly-used mapping configurations
_DEFAULT_MAPPING = HDRPhotoMapping()  # singleton for default config

def get_mapping(**overrides):
    """Return cached default or create with overrides."""
    if not overrides:
        return _DEFAULT_MAPPING
    return HDRPhotoMapping(**overrides)
```

---

## 4. Caching Strategies for Repeated Operations

### Problem with `functools.lru_cache` for Large Arrays

`lru_cache` holds **strong references**, preventing garbage collection of cached numpy arrays. For a 4000×6000 float32 image (~96 MB), this means the cache can hold gigabytes of arrays that are no longer needed.

```python
# BAD: strong reference prevents GC
@functools.lru_cache(maxsize=16)
def compute_lut(film_name, resolution):
    return expensive_lut_computation(film_name, resolution)
```

### Pattern: Weak Reference LRU Cache

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

### Pattern: `weakref.WeakValueDictionary` for Simple Cases

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

### Pattern: Disk-Based Cache for Expensive Computations

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

### Spektrafilm Application: LUT Service Caching

The `SpectralLUTService` already caches LUTs. The key optimization is ensuring LUTs are shared across pipeline instances:

```python
# Current pattern in pipeline.py:228-237
# LUT service is reused when resolution and backend match
can_reuse_lut_service = (
    reused_lut_service is not None
    and reused_lut_service.lut_resolution == self.settings.lut_resolution
    and type(reused_backend) is type(self._array_backend)
)
```

This is already a good pattern. The additional optimization would be a module-level weak-reference cache for LUTs so they survive across pipeline instances even when the pipeline itself is GC'd:

```python
# Module-level LUT cache with weak references
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

### Spektrafilm Application: Profile Characterization Caching

`characterize_pipeline_profile` (pipeline.py:163) creates a temporary pipeline and runs a ramp through it. This is expensive. The result depends only on the pipeline parameters, so it can be cached:

```python
import functools

# Cache based on pipeline parameter hash
@functools.lru_cache(maxsize=8)
def _cached_characterize(params_hash: str, pipeline_cls_name: str):
    # ... expensive computation ...
    return scene_y, look_y
```

---

## 5. Streaming/Chunked Processing

### Pattern: NumPy `memmap` for Large Files

```python
import numpy as np

# Memory-map a large image file — only loads pages on access
mmap_arr = np.memmap(
    'large_image.dat',
    dtype='float32',
    mode='r',
    shape=(6000, 4000, 3)
)

# Process in chunks — only one chunk in memory at a time
chunk_height = 512
for y in range(0, mmap_arr.shape[0], chunk_height):
    chunk = np.array(mmap_arr[y:y+chunk_height])  # materialize just this chunk
    result = process(chunk)
    # write result to output...
```

### Pattern: Tile-Based Processing with Overlap

```python
def process_tiled(image, tile_size, overlap, process_fn):
    """Process image in overlapping tiles to avoid edge artifacts."""
    h, w = image.shape[:2]
    step = tile_size - overlap
    results = np.empty_like(image)

    for y in range(0, h, step):
        for x in range(0, w, step):
            # Extract tile with overlap
            y1 = max(0, y - overlap)
            y2 = min(h, y + tile_size + overlap)
            x1 = max(0, x - overlap)
            x2 = min(w, x + tile_size + overlap)

            tile = image[y1:y2, x1:x2]  # view, no copy
            processed_tile = process_fn(tile)

            # Write back only the non-overlap region
            ry1 = y - y1
            ry2 = ry1 + min(tile_size, h - y)
            rx1 = x - x1
            rx2 = rx1 + min(tile_size, w - x)
            results[y:y+ry2-ry1, x:x+rx2-rx1] = processed_tile[ry1:ry2, rx1:rx2]

    return results
```

### Pattern: `multiprocessing.shared_memory` for Parallel Processing

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
    chunk = arr[slice_def]  # view into shared memory
    result = process(chunk)
    existing_shm.close()
    return result

# Parent process
shm, shared_img = create_shared_array(image.shape)
shared_img[:] = image[:]  # one-time copy into shared memory
# ... dispatch workers with shm.name ...
shm.close()
shm.unlink()
```

### Spektrafilm Application: Tile-Based GPU Processing

The pipeline already has tile-based GPU processing infrastructure (`_gpu_tile_pixels`, `_image_pixel_count`). The GPU tiles are processed independently — this is the right pattern for memory-constrained GPU processing:

```python
# Current pattern (pipeline.py:56-66)
DEFAULT_GPU_TILE_PIXELS = 2_000_000  # ~24 MB for float32 RGB

def _gpu_tile_pixels() -> int:
    raw_limit = os.environ.get(GPU_TILE_PIXELS_ENV)
    if raw_limit is None:
        return DEFAULT_GPU_TILE_PIXELS
    return int(raw_limit)
```

### Spektrafilm Application: HDR Sidecar Streaming (H3 Fix)

The H3 finding shows that `scene_luminance` and `scene_rgb` sidecars are always computed, adding ~366 MiB for a 4000×6000 image. The fix is to make sidecar collection lazy/on-demand:

```python
@dataclass(frozen=True, slots=True)
class HDRSceneEnergyMetadata:
    scene_luminance: np.ndarray | None = None  # lazy — only computed when needed
    scene_rgb: np.ndarray | None = None         # lazy — only computed when needed
    # ... scalar fields are cheap ...

def process_with_metadata(image, *, collect_sidecars=False):
    """Process image, optionally collecting HDR sidecars."""
    result_image = process(image)

    if not collect_sidecars:
        return SimulationPipelineResult(image=result_image, hdr_scene_energy=None)

    # Only compute expensive sidecars when explicitly requested
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

## 6. GPU Memory Pool Management (CuPy)

### Core API

```python
import cupy as cp

# Get the default memory pool
pool = cp.get_default_memory_pool()

# Monitor usage
print(f"Used:      {pool.used_bytes() / 1e6:.1f} MB")
print(f"Total:     {pool.total_bytes() / 1e6:.1f} MB")
print(f"Free blocks: {pool.n_free_blocks()}")  # high count = fragmentation

# Release all cached blocks back to CUDA
pool.free_all_blocks()

# Set memory limit to prevent OOM
pool.set_limit(size=4 * 1024**3)  # 4 GB limit
```

### Pattern: Explicit Memory Management in Pipeline

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
        self.pool.free_all_blocks()  # Defragment on exit

    def stats(self):
        return {
            "used_bytes": self.pool.used_bytes(),
            "total_bytes": self.pool.total_bytes(),
            "n_free_blocks": self.pool.n_free_blocks(),
        }
```

### Pattern: Reuse GPU Buffers

```python
def process_gpu_tiled(image, tile_size, backend):
    """Process image on GPU with pre-allocated tile buffers."""
    pool = cp.get_default_memory_pool()

    # Pre-allocate GPU tile buffers
    gpu_tile_in = cp.empty((tile_size, tile_size, 3), dtype=cp.float32)
    gpu_tile_out = cp.empty((tile_size, tile_size, 3), dtype=cp.float32)

    results = []
    for tile_cpu in split_tiles(image, tile_size):
        gpu_tile_in.set(tile_cpu)  # Host → Device, reusing buffer
        gpu_result = process_on_gpu(gpu_tile_in)
        gpu_tile_out[:] = gpu_result  # Reuse output buffer
        results.append(gpu_tile_out.get())  # Device → Host

    # Cleanup
    del gpu_tile_in, gpu_tile_out
    pool.free_all_blocks()

    return reassemble_tiles(results)
```

### Pattern: Custom Allocator for Fine-Grained Control

```python
import cupy as cp

# Use a custom memory pool with specific allocation strategy
def create_managed_pool(size_limit):
    """Create a CuPy memory pool with a size limit."""
    pool = cp.cuda.MemoryPool()
    pool.set_limit(size=size_limit)
    cp.cuda.set_allocator(pool.malloc)
    return pool

# Usage
pool = create_managed_pool(8 * 1024**3)  # 8 GB
try:
    result = process_on_gpu(data)
finally:
    pool.free_all_blocks()
```

### Spektrafilm Application

The pipeline already selects GPU backends and tiles processing. The key addition would be explicit memory pool management:

```python
# In SimulationPipeline.process():
if self._array_backend.is_gpu:
    pool = self._array_backend.get_memory_pool()
    try:
        result = self._run_pipeline(image)
    finally:
        pool.free_all_blocks()  # Defragment after each image
```

---

## 7. Shared Memory & Multiprocessing

### Pattern: `multiprocessing.shared_memory` for Zero-Copy Sharing

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

### Pattern: Shared Memory Pipeline

```python
def parallel_pipeline(image, num_workers=4):
    """Process image in parallel using shared memory."""
    shm, shared_img = create_shared_numpy_array(image.shape, image.dtype)
    shared_img[:] = image

    # Each worker reads from shared memory, writes to its own result
    chunks = np.array_split(range(image.shape[0]), num_workers)
    results = []

    for chunk_slices in chunks:
        shm_name, shape, dtype = shm.name, shared_img.shape, shared_img.dtype
        # Workers attach to shared memory — no serialization
        result = worker(shm_name, shape, dtype, chunk_slices)
        results.append(result)

    shm.close()
    shm.unlink()
    return np.concatenate(results)
```

### Pattern: `mmap` for File-Based Processing

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

        # Process in chunks
        chunk_h = 512
        for y in range(0, shape[0], chunk_h):
            chunk = np.array(arr[y:y+chunk_h])  # materialize chunk
            result = process(chunk)
            yield y, result

        mm.close()
```

### Spektrafilm Application

Shared memory is most valuable for the GUI where preview and full-resolution processing might run in parallel, or for batch processing multiple images. The current architecture is single-threaded, so this is a future optimization.

---

## 8. Spektrafilm-Specific Application Patterns

### Priority 1: HDR Sidecar Memory Pressure (H3 Fix)

**Problem**: `process_with_metadata` always computes `scene_luminance` (H×W float32, ~96 MB for 4000×6000) and `scene_rgb` (H×W×3 float32, ~288 MB). Total sidecar overhead: ~384 MB per image.

**Solution A — Lazy Sidecar Collection** (no API change):

```python
@dataclass(frozen=True, slots=True)
class HDRSceneEnergyMetadata:
    # Keep scalar fields (cheap)
    diffuse_white_estimate: float = 0.0
    headroom_estimate: float = 1.0
    auto_exposure_ev: float = 0.0
    method: str = ""
    confidence: str = ""
    # Make arrays lazy — store computation closure instead
    _scene_luminance_factory: object = None  # callable that returns np.ndarray
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

**Solution B — Explicit Flag** (API change, cleaner):

```python
@dataclass(frozen=True, slots=True)
class SimulationRequest:
    image: np.ndarray
    collect_hdr_metadata: bool = False  # Default: no sidecars (saves ~384 MB)

def process_with_metadata(self, request: SimulationRequest):
    result_image = self.process(request.image)

    if not request.collect_hdr_metadata:
        return SimulationPipelineResult(image=result_image)

    # Sidecar computation only when explicitly requested
    sidecars = self._compute_hdr_sidecars(request.image)
    return SimulationPipelineResult(image=result_image, hdr_scene_energy=sidecars)
```

### Priority 2: Pipeline Buffer Reuse

**Problem**: Each pipeline stage allocates new arrays. For a 3-stage pipeline (filming, printing, scanning), this means 3× the image size in working memory plus the output.

**Solution**: Ping-pong buffer pattern:

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

### Priority 3: Weak-Reference LUT Cache

**Problem**: LUT arrays are large (~hundreds of MB for high resolution). When pipeline instances are GC'd, LUTs may be recomputed for the next instance.

**Solution**: Module-level weak-reference cache:

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

### Priority 4: In-Place HDR Mapping Operations

**Problem**: HDR mapping functions create multiple intermediate arrays (scene_luminance, normalized, tone-mapped, etc.).

**Solution**: Pre-allocate working buffers and use `out=` parameter:

```python
def apply_hdr_mapping_in_place(
    image: np.ndarray,
    scene_luminance: np.ndarray,
    mapping: HDRPhotoMapping,
    buffers: PipelineBuffers | None = None,
) -> np.ndarray:
    """Apply HDR mapping using in-place operations."""
    # Use pre-allocated buffers or create temporary ones
    if buffers is None:
        norm_lum = np.empty_like(scene_luminance)
    else:
        norm_lum = buffers.current

    # In-place normalization
    np.divide(scene_luminance, mapping.diffuse_white, out=norm_lum)
    np.clip(norm_lum, 0.0, None, out=norm_lum)

    # In-place tone mapping
    np.multiply(image, compute_gain(norm_lum, mapping), out=image)

    return image
```

### Priority 5: CuPy Memory Pool Integration

**Problem**: GPU memory fragmentation from repeated allocation/deallocation during tile processing.

**Solution**: Explicit pool management per pipeline run:

```python
class SimulationPipeline:
    def process(self, image):
        if self._array_backend.is_gpu:
            pool = self._array_backend.get_memory_pool()
            pool.free_all_blocks()  # Start clean
            try:
                return self._run_pipeline(image)
            finally:
                pool.free_all_blocks()  # Defragment after run
        return self._run_pipeline(image)
```

---

## Summary: Quick Wins (No API Changes)

| Pattern | Memory Saved | Effort | Risk |
|---------|-------------|--------|------|
| `astype(copy=False)` everywhere | Avoids redundant copies | Low | None |
| In-place `out=` in HDR mapping | ~96-288 MB per stage | Low | Low |
| `__slots__` on all dataclasses | Already done | None | None |
| Weak-reference LUT cache | Prevents LUT recomputation | Medium | Low |
| Lazy HDR sidecar collection | ~384 MB per image | Medium | Medium |
| Ping-pong pipeline buffers | ~96 MB per stage | Medium | Low |
| CuPy pool `free_all_blocks()` | Reduces fragmentation | Low | None |
| Pre-allocated GPU tile buffers | Reduces allocation churn | Medium | Low |

## Summary: Architectural Changes (API Changes Required)

| Pattern | Memory Saved | Effort | Risk |
|---------|-------------|--------|------|
| `SimulationRequest.collect_hdr_metadata` flag | ~384 MB per preview | Medium | Medium |
| Generator-based batch processing | O(1) instead of O(N) for batches | High | Medium |
| Shared memory for parallel processing | Enables true parallelism | High | High |
| `np.memmap` for disk-backed images | Enables images > RAM | High | High |

---

## References

- NumPy `out` parameter: https://numpy.org/doc/stable/reference/ufuncs.html#ufuncs
- NumPy `memmap`: https://numpy.org/doc/stable/reference/generated/numpy.memmap.html
- Python `weakref`: https://docs.python.org/3/library/weakref.html
- Python `multiprocessing.shared_memory`: https://docs.python.org/3/library/multiprocessing.shared_memory.html
- CuPy memory management: https://docs.cupy.dev/en/stable/reference/memory.html
- Python `__slots__`: https://docs.python.org/3/reference/datamodel.html#slots
- Dataclasses `slots=True`: https://docs.python.org/3/library/dataclasses.html
- Dask arrays: https://docs.dask.org/en/stable/array.html
