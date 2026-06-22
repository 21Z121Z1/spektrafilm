"""Micro-benchmark for JzAzBz MLX gamut compression kernel."""
from __future__ import annotations

import time
import numpy as np

from spektrafilm.gpu.backend import select_backend
from spektrafilm.gpu.kernels.gamut_compress import compress_rgb_backend
from spektrafilm.utils.gamut_compression import OutputGamutCompressSpec

backend = select_backend("mlx", precision="float32")
spec = OutputGamutCompressSpec(algorithm="jzazbz")

# Simulate a 2K frame
H, W = 1080, 1920
rng = np.random.default_rng(123)
rgb = backend.asarray((rng.random((H, W, 3), dtype=np.float32) * 1.4 - 0.2))

# Warmup
out = compress_rgb_backend(rgb, spec, output_color_space="sRGB", backend=backend)
backend.synchronize()

# Time
n_runs = 10
times = []
for _ in range(n_runs):
    start = time.perf_counter()
    out = compress_rgb_backend(rgb, spec, output_color_space="sRGB", backend=backend)
    backend.synchronize()
    times.append(time.perf_counter() - start)

print(f"JzAzBz MLX kernel: {H}x{W}x3, median = {np.median(times)*1000:.2f} ms, mean = {np.mean(times)*1000:.2f} ms")
