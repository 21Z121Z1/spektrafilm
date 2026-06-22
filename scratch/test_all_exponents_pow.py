"""Test Metal exp(p*log(x)) vs precise::pow for all 4 JzAzBz exponents."""
from __future__ import annotations

import numpy as np

from spektrafilm.gpu.backend import select_backend

backend = select_backend("mlx", precision="float32")
mx = backend.mx

m1 = np.float32(2610.0 / 4096.0 * 0.25)
m2 = np.float32(1.7 * 2523.0 / 32.0)
inv_m2 = np.float32(1.0 / m2)
inv_m1 = np.float32(1.0 / m1)

C1 = np.float32(3424.0 / 4096.0)
C2 = np.float32(2413.0 / 4096.0 * 32.0)
C3 = np.float32(2392.0 / 4096.0 * 32.0)

# Ranges
ranges = {
    "m1": (np.float32(0.0), np.float32(2.0)),      # C*1e-4
    "m2": (C1, C2/C3),                             # PQ inverse ratio
    "inv_m2": (np.float32(1e-6), np.float32(1.0)), # Lp
    "inv_m1": (np.float32(1e-5), np.float32(1.0)), # ratio
}
exponents = {"m1": m1, "m2": m2, "inv_m2": inv_m2, "inv_m1": inv_m1}

source = r"""
    uint i = thread_position_in_grid.x;
    if (i >= n) return;
    float x = input[i];
    float p = p_buf[0];
    pow_builtin[i] = precise::pow(x, p);
    pow_log_exp[i] = precise::exp(p * precise::log(x));
"""

kernel = mx.fast.metal_kernel(
    name="compare_pow_all_exponents",
    input_names=["input", "p_buf"],
    output_names=["pow_builtin", "pow_log_exp"],
    source=source,
)

print("Exponent | range            | precise::pow max err | exp(p*log(x)) max err | winner")
for name, p in exponents.items():
    x_min, x_max = ranges[name]
    xs = np.linspace(x_min, x_max, 2000, dtype=np.float32)
    if x_min == 0:
        xs[0] = np.float32(1e-30)

    outputs = kernel(
        inputs=[backend.asarray(xs), backend.asarray(np.array([p], dtype=np.float32))],
        grid=(len(xs), 1, 1),
        threadgroup=(256, 1, 1),
        output_shapes=[(len(xs),), (len(xs),)],
        output_dtypes=[mx.float32, mx.float32],
        template=[["n", len(xs)]],
    )
    pow_b = backend.to_numpy(outputs[0])
    pow_le = backend.to_numpy(outputs[1])
    np_pow = np.power(xs, p)

    err_pow = np.max(np.abs(pow_b - np_pow))
    err_le = np.max(np.abs(pow_le - np_pow))
    winner = "log/exp" if err_le < err_pow else "pow"
    print(f"{name:8s} | [{x_min:.4f}, {x_max:.4f}] | {err_pow:.3e}           | {err_le:.3e}            | {winner}")
