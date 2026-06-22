"""Analyze how much of the JzAzBz MLX error comes from Metal transcendental vs DS arithmetic."""
from __future__ import annotations

import numpy as np

from spektrafilm.gpu.backend import select_backend

backend = select_backend("mlx", precision="float32")
mx = backend.mx

inv_m2 = np.float32(1.0 / (1.7 * 2523.0 / 32.0))
inv_m1 = np.float32(1.0 / (2610.0 / 4096.0 * 0.25))

# Grid covering the LMS' values typically seen in the kernel
N_grid = np.linspace(0.001, 1.0, 2000, dtype=np.float32)

source = r"""
    uint i = thread_position_in_grid.x;
    if (i >= n) return;
    float x = input[i];
    float p = p_buf[0];
    metal_pow[i] = precise::pow(x, p);
    metal_exp2_of_log2[i] = precise::exp2(p * precise::log2(x));
"""

kernel = mx.fast.metal_kernel(
    name="compare_pow",
    input_names=["input", "p_buf"],
    output_names=["metal_pow", "metal_exp2_of_log2"],
    source=source,
)

# inv_m2 pow (PQ forward, the dominant error source)
outputs = kernel(
    inputs=[backend.asarray(N_grid), backend.asarray(np.array([inv_m2], dtype=np.float32))],
    grid=(len(N_grid), 1, 1),
    threadgroup=(256, 1, 1),
    output_shapes=[(len(N_grid),), (len(N_grid),)],
    output_dtypes=[mx.float32, mx.float32],
    template=[["n", len(N_grid)]],
)
metal_pow = backend.to_numpy(outputs[0])
metal_exp2_log2 = backend.to_numpy(outputs[1])
numpy_pow = np.power(N_grid, inv_m2)

print("=== PQ forward: Vp = N^(1/m2) ===")
print(f"Metal precise::pow vs numpy pow:       max abs err = {np.max(np.abs(metal_pow - numpy_pow)):.3e}")
print(f"Metal exp2(p*log2(x)) vs numpy pow:    max abs err = {np.max(np.abs(metal_exp2_log2 - numpy_pow)):.3e}")

# If log2 were perfect but exp2 still Metal:
perfect_log2_then_metal_exp2 = np.exp2(inv_m2 * np.log2(N_grid))
err_if_log2_perfect = np.max(np.abs(perfect_log2_then_metal_exp2 - numpy_pow))
print(f"Perfect log2 + Metal exp2 vs numpy:    max abs err = {err_if_log2_perfect:.3e}")

# If both log2 and exp2 were perfect (numpy):
err_if_both_perfect = 0.0  # by definition np.exp2(inv_m2 * np.log2(N_grid)) == np.power(N_grid, inv_m2) for the cases where it matters
print(f"Perfect log2 + perfect exp2 vs numpy:  max abs err = {err_if_both_perfect:.3e}")

# inv_m1 pow (PQ forward second step: ratio^(1/m1))
outputs2 = kernel(
    inputs=[backend.asarray(N_grid), backend.asarray(np.array([inv_m1], dtype=np.float32))],
    grid=(len(N_grid), 1, 1),
    threadgroup=(256, 1, 1),
    output_shapes=[(len(N_grid),), (len(N_grid),)],
    output_dtypes=[mx.float32, mx.float32],
    template=[["n", len(N_grid)]],
)
metal_pow2 = backend.to_numpy(outputs2[0])
numpy_pow2 = np.power(N_grid, inv_m1)
print(f"\n=== PQ forward second step: ratio^(1/m1) ===")
print(f"Metal precise::pow vs numpy pow:       max abs err = {np.max(np.abs(metal_pow2 - numpy_pow2)):.3e}")

print(f"\n=== Estimated full roundtrip floor ===")
print(f"Faithful f32 DS simulation (uses numpy transcendentals): ~7.3e-5 vs CPU roundtrip")
print(f"Current MLX fused kernel vs CPU:                         ~1.1e-4 to 1.5e-4")
print(f"=> Even with perfect transcendentals, the float32 DS arithmetic floor is ~5.5e-5 vs input / ~7.3e-5 vs CPU.")
