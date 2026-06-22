"""Test Metal precise::log2/exp2/pow against numpy float32."""
from __future__ import annotations

import numpy as np

from spektrafilm.gpu.backend import select_backend

backend = select_backend("mlx", precision="float32")
mx = backend.mx

N = np.float32(0.295164168)
inv_m2 = np.float32(1.0 / (1.7 * 2523.0 / 32.0))

source = r"""
    uint i = thread_position_in_grid.x;
    if (i >= 3) return;
    float N = input[0];
    float inv_m2 = input[1];
    if (i == 0) {
        log2_out[0] = precise::log2(N);
    } else if (i == 1) {
        exp2_out[0] = precise::exp2(inv_m2 * precise::log2(N));
    } else {
        pow_out[0] = precise::pow(N, inv_m2);
    }
"""

kernel = mx.fast.metal_kernel(
    name="test_pow",
    input_names=["input"],
    output_names=["log2_out", "exp2_out", "pow_out"],
    source=source,
)
outputs = kernel(
    inputs=[backend.asarray(np.array([N, inv_m2], dtype=np.float32))],
    grid=(3, 1, 1),
    threadgroup=(3, 1, 1),
    output_shapes=[(1,), (1,), (1,)],
    output_dtypes=[mx.float32, mx.float32, mx.float32],
)
log2_m = backend.to_numpy(outputs[0])[0]
exp2_m = backend.to_numpy(outputs[1])[0]
pow_m = backend.to_numpy(outputs[2])[0]

print("Metal precise::log2(N):", log2_m)
print("Python np.log2(N):     ", np.log2(N))
print("Metal exp2*log2:       ", exp2_m)
print("Python exp2*log2:      ", np.exp2(inv_m2 * np.log2(N)))
print("Metal precise::pow:    ", pow_m)
print("Python pow:            ", np.power(N, inv_m2))
