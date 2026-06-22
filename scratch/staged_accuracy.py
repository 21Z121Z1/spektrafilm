"""Compare fused vs fully-staged MLX JzAzBz compression accuracy."""
from __future__ import annotations

import numpy as np

from spektrafilm.gpu.backend import select_backend
from spektrafilm.gpu.kernels.gamut_compress import (
    _JZAZBZ_Y_W_CDM2,
    _compress_rgb_jzazbz_chroma_mlx_kernel,
    _xyz_to_jzazbz_backend,
    _jzazbz_to_xyz_backend,
    _rgb_to_xyz_backend,
    _xyz_to_rgb_backend,
    _c_max_lookup_backend,
    _reinhard_knee_backend,
)
from spektrafilm.gpu.kernels.color import (
    precompute_rgb_to_xyz_matrix,
    precompute_xyz_to_rgb_matrix,
)
from spektrafilm.utils.gamut_compression import (
    OutputGamutCompressSpec,
    compress_rgb,
    _get_output_c_max_table,
)

backend = select_backend("mlx", precision="float32")
mx = backend.mx
output_color_space = "sRGB"

# Use the same input as the pytest test
rng = np.random.default_rng(20260608)
rgb = rng.uniform(-0.2, 1.35, size=(6, 7, 3)).astype(np.float32)

spec = OutputGamutCompressSpec(algorithm="jzazbz")
expected = compress_rgb(rgb.astype(float), spec, output_color_space="sRGB")

# Fused kernel
fused = _compress_rgb_jzazbz_chroma_mlx_kernel(
    backend.asarray(rgb),
    output_color_space,
    threshold=0.0,
    limit=1.0,
    power=6.0,
    lightness_compression=(0.7, 1.0, 2.2),
    backend=backend,
)
fused_np = backend.to_numpy(fused)
print("FUSED error:", float(np.max(np.abs(fused_np - expected))))

# Fully staged using existing backend-portable functions
M_rgb_to_xyz = backend.asarray(precompute_rgb_to_xyz_matrix(output_color_space))
M_xyz_to_rgb = backend.asarray(precompute_xyz_to_rgb_matrix(output_color_space))
rgb_b = backend.asarray(rgb)
xyz = _rgb_to_xyz_backend(rgb_b, M_rgb_to_xyz, backend)
jab = _xyz_to_jzazbz_backend(xyz * _JZAZBZ_Y_W_CDM2, backend)
Jz = jab[..., 0]
az = jab[..., 1]
bz = jab[..., 2]

# Lightness compression
lt, ll, lp = (0.7, 1.0, 2.2)
L_white = 0.16728967487764359  # _jzazbz_white_Jz("sRGB")
Jz_norm = Jz / L_white
x = (Jz_norm - lt) / (ll - lt)
x_safe = mx.maximum(x, 0.0)
x_direct = mx.minimum(x_safe, 1.0)
y_direct = x_direct / mx.power(1.0 + mx.power(x_direct, lp), 1.0 / lp)
inv_x = 1.0 / mx.maximum(x_safe, 1.0)
y_recip = 1.0 / mx.power(1.0 + mx.power(inv_x, lp), 1.0 / lp)
y = mx.where(x_safe > 1.0, y_recip, y_direct)
Jz = mx.where(Jz_norm > lt, lt + (ll - lt) * y, Jz_norm) * L_white

Cz = mx.sqrt(az * az + bz * bz)
hz = mx.arctan2(bz, az)
L_grid, h_grid, C_max_table = _get_output_c_max_table("jzazbz", output_color_space)
Cz_max = _c_max_lookup_backend(Jz, hz, L_grid, h_grid, C_max_table, backend)
safe_Cz_max = mx.maximum(Cz_max, 1e-9)
d_norm = Cz / safe_Cz_max
d_compressed = _reinhard_knee_backend(
    d_norm, threshold=0.0, limit=1.0, power=6.0, backend=backend,
)
Cz_new = d_compressed * safe_Cz_max
az_new = Cz_new * mx.cos(hz)
bz_new = Cz_new * mx.sin(hz)
jab_new = mx.stack([Jz, az_new, bz_new], axis=-1)
xyz_new = _jzazbz_to_xyz_backend(jab_new, backend) / _JZAZBZ_Y_W_CDM2
rgb_new = _xyz_to_rgb_backend(xyz_new, M_xyz_to_rgb, backend)
staged_np = backend.to_numpy(backend.nan_to_num(rgb_new))
print("STAGED error:", float(np.max(np.abs(staged_np - expected))))
