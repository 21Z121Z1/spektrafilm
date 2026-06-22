"""Isolate JzAzBz round-trip error (no compression) with in-gamut input."""
from __future__ import annotations

import numpy as np
import colour

from spektrafilm.gpu.backend import select_backend
from spektrafilm.gpu.kernels.gamut_compress import (
    _JZAZBZ_Y_W_CDM2,
    _compress_rgb_jzazbz_chroma_mlx_kernel,
    _xyz_to_jzazbz_backend,
    _jzazbz_to_xyz_backend,
    _rgb_to_xyz_backend,
    _xyz_to_rgb_backend,
)
from spektrafilm.gpu.kernels.color import (
    precompute_rgb_to_xyz_matrix,
    precompute_xyz_to_rgb_matrix,
)
from spektrafilm.utils.gamut_compression import OutputGamutCompressSpec, compress_rgb

backend = select_backend("mlx", precision="float32")
output_color_space = "sRGB"
cs = colour.RGB_COLOURSPACES["sRGB"]
white = np.asarray(cs.whitepoint, dtype=float)

# In-gamut input so Jz stays within table and no compression fires
rng = np.random.default_rng(20260608)
rgb = rng.uniform(0.0, 1.0, size=(6, 7, 3)).astype(np.float32)

# CPU reference round-trip
xyz_cpu = colour.RGB_to_XYZ(
    rgb, colourspace="sRGB", illuminant=white, apply_cctf_decoding=False,
)
jab_cpu = colour.XYZ_to_Jzazbz(xyz_cpu * _JZAZBZ_Y_W_CDM2)
xyz_back_cpu = colour.Jzazbz_to_XYZ(jab_cpu) / _JZAZBZ_Y_W_CDM2
rgb_back_cpu = colour.XYZ_to_RGB(
    xyz_back_cpu, colourspace="sRGB", illuminant=white, apply_cctf_encoding=False,
)

# Fused kernel with threshold high enough to be identity (d_norm <= 0.999)
# Use lightness compression OFF to isolate transform error
fused = _compress_rgb_jzazbz_chroma_mlx_kernel(
    backend.asarray(rgb),
    output_color_space,
    threshold=0.999,
    limit=1.0,
    power=6.0,
    lightness_compression=None,
    backend=backend,
)
fused_np = backend.to_numpy(fused)

print("CPU round-trip vs input:", float(np.max(np.abs(rgb_back_cpu - rgb))))
print("FUSED vs CPU round-trip:", float(np.max(np.abs(fused_np - rgb_back_cpu))))
print("FUSED vs input:", float(np.max(np.abs(fused_np - rgb))))

# Check if any compression fired in fused_rt (threshold=0.999)
spec_rt = OutputGamutCompressSpec(algorithm="jzazbz", knee=(0.999, 1.0, 6.0), lightness_compression=None)
expected_rt = compress_rgb(rgb.astype(float), spec_rt, output_color_space="sRGB")
print("FUSED rt vs CPU rt compression (should be 0 if identity):",
      float(np.max(np.abs(fused_np - expected_rt))))

# Compare intermediate JzAzBz values: CPU vs MLX staged tensor ops
M_rgb_to_xyz = backend.asarray(precompute_rgb_to_xyz_matrix(output_color_space))
M_xyz_to_rgb = backend.asarray(precompute_xyz_to_rgb_matrix(output_color_space))
rgb_b = backend.asarray(rgb)
xyz_b = _rgb_to_xyz_backend(rgb_b, M_rgb_to_xyz, backend)
jab_b = _xyz_to_jzazbz_backend(xyz_b * _JZAZBZ_Y_W_CDM2, backend)
jab_mlx = backend.to_numpy(jab_b)
print("MLX staged JzAzBz vs CPU JzAzBz:", float(np.max(np.abs(jab_mlx - jab_cpu))))

# Per-pixel errors
err = np.abs(fused_np - rgb_back_cpu).reshape(-1, 3)
print("Max per-channel error:", err.max(axis=0))
worst = np.unravel_index(np.argmax(np.abs(fused_np - rgb_back_cpu)), rgb.shape)
print("Worst pixel:", worst)
print("  input:", rgb[worst[0], worst[1]])
print("  CPU:  ", rgb_back_cpu[worst[0], worst[1]])
print("  FUSED:", fused_np[worst[0], worst[1]])
