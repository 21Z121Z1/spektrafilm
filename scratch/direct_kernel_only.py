"""Call the fused kernel directly in isolation."""
from __future__ import annotations

import numpy as np

from spektrafilm.gpu.backend import select_backend
from spektrafilm.gpu.kernels.gamut_compress import _compress_rgb_jzazbz_chroma_mlx_kernel
from spektrafilm.utils.gamut_compression import OutputGamutCompressSpec, compress_rgb

backend = select_backend("mlx", precision="float32")
rng = np.random.default_rng(20260608)
rgb = rng.uniform(-0.2, 1.35, size=(6, 7, 3)).astype(np.float32)

spec = OutputGamutCompressSpec(algorithm="jzazbz")
expected = compress_rgb(rgb.astype(float), spec, output_color_space="sRGB")

result = _compress_rgb_jzazbz_chroma_mlx_kernel(
    backend.asarray(rgb),
    "sRGB",
    threshold=0.0,
    limit=1.0,
    power=6.0,
    lightness_compression=None,
    backend=backend,
)
result_np = backend.to_numpy(result)
print("Max abs error:", float(np.max(np.abs(result_np - expected))))
print("Worst pixel actual:", result_np[0, 6])
print("Worst pixel expected:", expected[0, 6])
print("Input worst pixel:", rgb[0, 6])
