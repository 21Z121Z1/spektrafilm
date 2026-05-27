# Memory Management Deep Research — Spektrafilm

Date: 2026-05-27

## Table of Contents

1. [Current Memory Usage Audit](#1-current-memory-usage-audit)
2. [Memory Profiling Tools & Integration](#2-memory-profiling-tools--integration)
3. [NumPy Memory Optimization Techniques](#3-numpy-memory-optimization-techniques)
4. [GPU Memory Management Patterns](#4-gpu-memory-management-patterns)
5. [Float32 vs Float16 Precision Tradeoffs](#5-float32-vs-float16-precision-tradeoffs)
6. [Large Image Processing Without Full Allocation](#6-large-image-processing-without-full-allocation)
7. [GPU VRAM Management & Out-of-Core Processing](#7-gpu-vram-management--out-of-core-processing)
8. [Python GC & NumPy Circular References](#8-python-gc--numpy-circular-references)
9. [Apple Unified Memory & MLX](#9-apple-unified-memory--mlx)
10. [Recommendations for Spektrafilm](#10-recommendations-for-spektrafilm)

---

## 1. Current Memory Usage Audit

### 1.1 Pipeline Architecture

Spektrafilm's simulation pipeline processes images through these stages:

```
Input RGB → [AutoExposure] → [Crop/Rescale] → [Filming: Expose] → [Filming: Develop]
→ [Printing: Expose] → [Printing: Develop] → [Scanning: Scan] → Output RGB
```

Each stage creates a full `(H, W, 3)` float array. The pipeline in `pipeline.py:584-604` shows explicit `del` of intermediate arrays:

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

### 1.2 Peak Memory Estimate (per image size)

For a typical pipeline pass with float32 (4 bytes/value):

| Image Size | Pixels | Single Array | Pipeline Peak (5 arrays) | With LUT Intermediates |
|------------|--------|-------------|-------------------------|----------------------|
| 2K (1920×1080) | 2.07M | 24 MB | ~120 MB | ~180 MB |
| 4K (3840×2160) | 8.29M | 96 MB | ~480 MB | ~720 MB |
| 6K (6000×4000) | 24M | 280 MB | ~1.4 GB | ~2.1 GB |
| 8K (7680×4320) | 33.2M | 388 MB | ~1.9 GB | ~2.9 GB |

**Key memory consumers identified in codebase:**

1. **Pipeline arrays** (`pipeline.py:584-604`): 5-6 simultaneous H×W×3 float32 arrays during processing. Each is ~`H×W×12` bytes. Peak at ~5× the input size.

2. **FFT Gaussian filter** (`fft_gaussian_filter.py:33`): Creates `np.empty_like(image)` plus padded copy plus FFT arrays. For 3D images, processes channels in parallel with `ThreadPoolExecutor`, multiplying memory by thread count.

3. **LUT computation** (`lut.py:20-30`): 3D LUTs of shape `(steps, steps, steps, 3)` — at steps=32 this is 32³×3×8 = 3 MB (float64), at steps=64 it's 24 MB. `fast_interp_lut.py:252-256` creates slope arrays matching LUT size.

4. **HDR photo processing** (`hdr_photo.py`): Creates multiple `(H, W, 3)` float32 arrays — `hdr_rgb`, `unlifted_hdr_rgb`, `sdr_rgb`, plus RGBA payloads. Peak at ~4× input size during `_prepare_generic_renditions`.

5. **Diffusion/halation** (`diffusion.py:70-87`): Multiple gaussian filter passes with intermediate arrays. For N bounces, creates N temporary filtered copies.

6. **GPU tile processing** (`pipeline.py:400-429`): Creates full output buffer plus per-tile GPU arrays. Tile overlap adds ~10-20% memory per tile.

### 1.3 Memory Allocation Patterns

**No memory pool management found.** The codebase has:
- No `gc.collect()` calls
- No `tracemalloc` usage
- No `weakref` usage
- No `__del__` methods
- No CuPy memory pool management (`free_all_blocks`, `mempool`)
- No `numpy.memmap` usage
- No memory-mapped I/O

**Existing `del` statements** (pipeline.py:586-603, hdr_photo.py:267, controller.py:355-359) show awareness of memory pressure but rely on reference counting alone.

---

## 2. Memory Profiling Tools & Integration

### 2.1 Tool Comparison

| Tool | Type | Overhead | Best For |
|------|------|----------|----------|
| `tracemalloc` | stdlib | Low-Medium | Finding allocation sites, leak detection |
| `memory_profiler` | 3rd party | High | Line-by-line memory usage |
| `memray` (Bloomberg) | 3rd party | Low | Flame graphs, native stacks, production use |
| `objgraph` | 3rd party | Low | Reference cycle visualization |
| `psutil` | 3rd party | Minimal | RSS/VMS monitoring |

### 2.2 tracemalloc Integration Pattern

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

### 2.3 memray Integration Pattern

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

### 2.4 Lightweight RSS Monitor

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

### 2.5 Recommended Integration for Spektrafilm

Add a `--profile-memory` CLI flag or environment variable (`SPEKTRAFILM_PROFILE_MEMORY=1`) that enables tracemalloc wrapping around pipeline runs. This is zero-cost when disabled and provides actionable data when enabled.

---

## 3. NumPy Memory Optimization Techniques

### 3.1 Zero-Copy Views

NumPy views share the underlying data buffer without copying. Key operations that return views:

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

**Verification:**
```python
assert np.shares_memory(arr, subarray)
assert subarray.base is arr
```

**Spektrafilm relevance:** The pipeline's `_preprocess_input_image` (`pipeline.py:556-559`) does:
```python
image = np.ascontiguousarray(np.asarray(image, dtype=self._runtime_dtype)[:, :, 0:3])
```
The `[:, :, 0:3]` slice is a view, but `np.ascontiguousarray` forces a copy. This is correct for downstream performance but means the original 4-channel image persists alongside the 3-channel copy briefly.

### 3.2 In-Place Operations

Avoid temporary array allocations with `out=` parameter and augmented assignment:

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

**Spektrafilm already uses `copy=False`** in many places (`hdr_photo.py:472-477`):
```python
hdr_rgb = np.clip(hdr_rgb, 0.0, headroom).astype(np.float32, copy=False)
```
This is good — it avoids a copy when the dtype already matches.

### 3.3 Array Reuse with Pre-allocated Buffers

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

**Spektrafilm opportunity:** The pipeline stages could share a pool of pre-allocated buffers since they all process the same image dimensions.

### 3.4 Memory Layout Optimization

```python
# C-order (row-major): best for row-wise operations
arr_c = np.ascontiguousarray(arr, dtype=np.float32)

# F-order (column-major): best for column-wise operations
arr_f = np.asfortranarray(arr, dtype=np.float32)

# Check layout
assert arr_c.flags['C_CONTIGUOUS']
assert arr_f.flags['F_CONTIGUOUS']
```

**Spektrafilm note:** All image arrays are C-contiguous (H×W×3, row-major). This is correct for the pixel-processing access patterns used throughout.

### 3.5 `np.where` vs Boolean Indexing

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

## 4. GPU Memory Management Patterns

### 4.1 CuPy Memory Pool

CuPy uses a memory pool by default to avoid the overhead of repeated `cudaMalloc`/`cudaFree` calls. The pool caches freed blocks for reuse.

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

### 4.2 CuPy Memory Pool Configuration

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

### 4.3 GPU-CPU Transfer Patterns

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

### 4.4 Spektrafilm CuPy Backend Analysis

The `CupyBackend` class (`cupy_backend.py`) has **no memory pool management**:

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

**Issues found:**
1. No `mempool.free_all_blocks()` after pipeline completion — GPU memory remains cached
2. No memory limit set — can OOM on large images
3. No pinned memory pool for faster H2D/D2H transfers
4. The tile processing (`pipeline.py:414-419`) transfers each tile result back to CPU individually, which is correct but could use pinned memory

### 4.5 Recommended CuPy Memory Management for Spektrafilm

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

## 5. Float32 vs Float16 Precision Tradeoffs

### 5.1 Precision Comparison

| Property | float32 | float16 | bfloat16 |
|----------|---------|---------|----------|
| Bits | 32 | 16 | 16 |
| Significand bits | 23 | 10 | 7 |
| Exponent bits | 8 | 5 | 8 |
| Decimal digits | ~7 | ~3 | ~2-3 |
| Max value | 3.4×10³⁸ | 65,504 | 3.4×10³⁸ |
| Smallest normal | 1.2×10⁻³⁸ | 6.1×10⁻⁵ | 1.2×10⁻³⁸ |
| Memory per pixel (RGB) | 12 bytes | 6 bytes | 6 bytes |

### 5.2 Impact on Image Processing

**float16 risks in Spektrafilm's pipeline:**

1. **HDR values**: Spektrafilm processes values up to `max_headroom` (typically 4-16×). float16 can represent these, but with only ~3 decimal digits of precision. Subtle gradations in highlights will band.

2. **Logarithmic density**: The density curves use `log10()` of exposure values. Small float16 values near zero have poor precision, amplifying quantization noise in shadow regions.

3. **LUT interpolation**: Cubic interpolation in `fast_interp_lut.py` involves weighted sums of 64 values (4³). Accumulated float16 rounding errors would produce visible artifacts.

4. **Accumulation**: Halation bounces (`diffusion.py:79-83`) accumulate weighted gaussian-filtered values. float16 accumulation loses precision with each addition.

5. **ICC color transforms**: Matrix multiplications in color space conversions compound rounding errors.

### 5.3 Spektrafilm's Current Precision Strategy

The codebase uses float32 throughout for runtime processing:
- `pipeline.py:47-52`: `_runtime_dtype()` returns float32 or float64
- `hdr_photo.py`: Explicitly casts to float32 at every stage
- `CupyBackend` defaults to float32, supports float16 as option
- `MlxBackend` defaults to float32, supports float16 as option

**The CLAUDE.md constraint is correct**: float32 is the right default. float16 should only be used for preview/interactive workflows where speed matters more than quality.

### 5.4 Mixed-Precision Strategy (Future)

If float16 is ever needed for performance:

```python
# Compute in float16, accumulate in float32
def halation_bounce_mixed(raw, sigma, weight, backend):
    # Filter in float16 for speed
    filtered_16 = gaussian_filter(raw.astype(np.float16), sigma)
    # Accumulate in float32 for precision
    return raw + weight * filtered_16.astype(np.float32)
```

This matches NVIDIA's "mixed precision" approach but requires careful validation of each operation's numerical stability.

---

## 6. Large Image Processing Without Full Allocation

### 6.1 numpy.memmap

Memory-mapped arrays let the OS page data in/out of RAM, enabling processing of images larger than available memory:

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

**Pros:** OS-managed paging, transparent access, works with existing NumPy code.
**Cons:** No compression, random access on HDD is slow, raw format only.

### 6.2 Zarr — Chunked Compressed Arrays

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

**Pros:** Compression (typically 2-5× for image data), cloud-friendly (S3/GCS), chunk-level parallelism.
**Cons:** Decompression overhead, not directly usable as NumPy array without `.np` accessor.

### 6.3 HDF5 with h5py

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

### 6.4 Dask Array — Lazy Parallel Processing

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

### 6.5 Relevance to Spektrafilm

Spektrafilm currently loads full images into memory. For very large images (8K+), this can exceed 2 GB for the pipeline peak. Two approaches:

1. **Keep current architecture** — the GPU tiling (`pipeline.py:396-429`) already splits large images into manageable tiles. This is the primary OOM mitigation. Memory-mapped I/O would only help at the I/O boundary.

2. **Add memmap at I/O boundary** — load/save via memmap for the largest images, feed tiles to the pipeline. This avoids doubling memory during load.

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

## 7. GPU VRAM Management & Out-of-Core Processing

### 7.1 Tiling Strategy (Already Implemented)

Spektrafilm already implements GPU tiling in `pipeline.py:396-429`:

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

**Default tile budget:** 2,000,000 pixels (`DEFAULT_GPU_TILE_PIXELS`), configurable via `SPEKTRAFILM_GPU_TILE_PIXELS` env var.

**Overlap computation** (`pipeline.py:441-478`): Based on lens blur, halation scatter, and diffusion sizes — ensures seamless tile boundaries.

### 7.2 CUDA Streams for Overlap

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

### 7.3 CuPy Memory Pool Tuning

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

### 7.4 Out-of-Core with CuPy

For images that don't fit in VRAM even as tiles:

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

## 8. Python GC & NumPy Circular References

### 8.1 How Python GC Works

Python uses two mechanisms for memory management:

1. **Reference counting** (primary): Every object has a refcount. When it drops to 0, the object is immediately freed. This is deterministic and fast.

2. **Cyclic garbage collector** (secondary): Periodically scans for groups of objects that reference each other but are otherwise unreachable. Runs on generation thresholds (default: 700, 10, 10).

### 8.2 NumPy Array GC Behavior

NumPy arrays manage their data buffer in C. When the Python array object is collected, the buffer is freed via `__del__`. Since Python 3.4 (PEP 442), objects with `__del__` can participate in cycle breaking.

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

### 8.3 Spektrafilm GC Risks

**No circular reference patterns found** in the codebase. The `dataclass(frozen=True, slots=True)` pattern used for `HDRSceneEnergyMetadata` and `SimulationPipelineResult` prevents accidental circular references.

However, some risks exist:

1. **`hdr_curve_profiles.py`**: Uses closures and function references that could create cycles if a profile object holds a reference back to the pipeline.

2. **GUI callbacks**: Qt signal/slot connections can create reference cycles. The `del event` patterns in `widget_editors.py` and `widget_sections.py` suggest awareness of this.

3. **Pipeline debug methods** (`pipeline.py:615-646`): The debug pipeline stores references to intermediate arrays that the normal pipeline deletes.

### 8.4 Best Practices

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

## 9. Apple Unified Memory & MLX

### 9.1 Unified Memory Architecture (UMA)

Apple Silicon (M1-M4) uses unified memory where CPU and GPU share the same physical RAM. Key implications:

- **No CPU↔GPU copies**: Data is accessed in-place by both CPU and GPU
- **Shared bandwidth**: Memory bandwidth is shared across all compute units
- **Fixed pool**: On a 16 GB system, CPU + GPU + OS share those 16 GB

### 9.2 MLX Memory Management

MLX (Apple's ML framework) leverages UMA:

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

### 9.3 MLX Lazy Evaluation

MLX uses lazy evaluation — computations are deferred until `mx.eval()` is called. This allows:
- **Graph optimization**: Fusing operations, eliminating intermediates
- **Reduced peak memory**: Intermediate tensors can be freed as soon as they're consumed
- **Automatic tiling**: MLX can split large operations to fit in memory

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

### 9.4 Spektrafilm MLX Backend Analysis

The `MlxBackend` (`mlx_backend.py`) does not use any memory management:

```python
class MlxBackend:
    def __init__(self, *, precision="float32"):
        import mlx.core as mx
        self.mx = mx
        # No memory limits, no cache management

    def synchronize(self):
        self.mx.synchronize()
```

**Recommendations:**
1. Set memory limits based on system RAM
2. Call `mx.metal.set_cache_limit()` to prevent unbounded caching
3. Use `mx.eval()` strategically after each pipeline stage to free intermediates
4. No explicit `del` needed — MLX's lazy evaluation handles this better than NumPy

### 9.5 MLX vs CuPy Memory Characteristics

| Aspect | MLX (Apple UMA) | CuPy (NVIDIA) |
|--------|-----------------|---------------|
| Memory model | Shared CPU+GPU | Separate VRAM |
| Transfer cost | Zero (in-place) | Explicit H2D/D2H |
| Pool management | `set_memory_limit()` | `MemoryPool.set_limit()` |
| Lazy evaluation | Yes (graph fusion) | No (eager execution) |
| Cache | Built-in | Memory pool cache |
| OOM behavior | Spills to disk (swap) | Hard OOM crash |

---

## 10. Recommendations for Spektrafilm

### 10.1 Priority 1: GPU Memory Pool Management (High Impact, Low Effort)

**Problem:** CuPy backend has no memory pool management. GPU memory leaks across pipeline runs.

**Fix:** Add pool management to `CupyBackend`:

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

**And add cleanup to pipeline** after processing completes:

```python
# In pipeline.py, after process() returns
if hasattr(self._array_backend, 'cleanup'):
    self._array_backend.cleanup()
```

### 10.2 Priority 2: MLX Memory Limits (High Impact on macOS, Low Effort)

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

### 10.3 Priority 3: Memory Profiling Infrastructure (Medium Impact, Low Effort)

Add optional tracemalloc profiling:

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

### 10.4 Priority 4: Pre-allocated Buffer Pool (Medium Impact, Medium Effort)

Create a buffer pool for pipeline stages that process the same image dimensions:

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

### 10.5 Priority 5: Memory-Mapped I/O for Large Images (Low Impact, Medium Effort)

For images >4K, use memory-mapped loading to avoid doubling memory at the I/O boundary:

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

### 10.6 Priority 6: Reduce Pipeline Peak Memory (High Impact, Higher Effort)

The pipeline currently holds 5-6 full arrays simultaneously. Could be reduced to 3 by fusing stages:

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

This is a larger refactor (noted as H3 in code review — skipped per CLAUDE.md).

### 10.7 Summary: Ranked by Impact-to-Effort Ratio

| Priority | Recommendation | Impact | Effort | Memory Saved |
|----------|---------------|--------|--------|-------------|
| 1 | CuPy memory pool management | High | Low | Prevents GPU memory leaks |
| 2 | MLX memory limits | High (macOS) | Low | Prevents OOM on Apple Silicon |
| 3 | tracemalloc profiling flag | Medium | Low | Enables diagnosis |
| 4 | Buffer pool for pipeline stages | Medium | Medium | ~20-30% peak reduction |
| 5 | Memory-mapped I/O | Low | Medium | Helps with >4K images |
| 6 | Fused pipeline stages | High | High | ~40% peak reduction |

---

## Appendix A: Memory Footprint Reference Card

```
Image size guide (float32, 3 channels):
  1920×1080 (2K):    24 MB per array
  3840×2160 (4K):    96 MB per array
  6000×4000 (6K):   280 MB per array
  7680×4320 (8K):   388 MB per array
  12000×8000 (12K): 1.1 GB per array

Pipeline peak = ~5× single array size
With LUTs = ~7× single array size
GPU tile budget default = 2M pixels = 24 MB per tile
```

## Appendix B: Key Documentation Sources

- Python tracemalloc: https://docs.python.org/3/library/tracemalloc.html
- memray (Bloomberg): https://bloomberg.github.io/memray/
- NumPy memmap: https://numpy.org/doc/stable/reference/generated/numpy.memmap.html
- CuPy Memory Management: https://docs.cupy.dev/en/stable/reference/memory.html
- MLX Unified Memory: https://ml-explore.github.io/mlx/
- Zarr: https://zarr.readthedocs.io/
- Python gc module: https://docs.python.org/3/library/gc.html
- PEP 442 (Safe finalization): https://peps.python.org/pep-0442/
