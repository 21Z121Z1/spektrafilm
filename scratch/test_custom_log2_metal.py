"""Prototype custom Metal log2/exp2 and compare to numpy float32."""
from __future__ import annotations

import numpy as np

from spektrafilm.gpu.backend import select_backend

backend = select_backend("mlx", precision="float32")
mx = backend.mx

# Test values including the worst-case N and a grid
N_worst = np.float32(0.295164168)
test_values = np.array([
    N_worst,
    np.float32(0.1),
    np.float32(0.25),
    np.float32(0.5),
    np.float32(0.75),
    np.float32(1.0),
    np.float32(1.25),
    np.float32(2.0),
    np.float32(5.0),
    np.float32(10.0),
    np.float32(100.0),
], dtype=np.float32)

inv_m2 = np.float32(1.0 / (1.7 * 2523.0 / 32.0))

header = r"""
    inline float my_log2(float v) {
        uint bits = as_type<uint>(v);
        int exponent = int((bits >> 23) & 0xFFu) - 127;
        uint mantissa_bits = (bits & 0x007FFFFFu) | 0x3F800000u;
        float m = as_type<float>(mantissa_bits);
        float f = m;
        int e_adj = exponent;
        if (m > 1.414213562f) {
            f = m * 0.5f;
            e_adj = exponent + 1;
        }
        float z = (f - 1.0f) / (f + 1.0f);
        float z2 = z * z;
        float poly = z * (2.0f / 0.6931471805599453f) *
            (1.0f + z2 * (0.3333333333f + z2 * (0.2f + z2 * (0.1428571429f + z2 * 0.1111111111f))));
        return float(e_adj) + poly;
    }

    inline float my_exp2(float v) {
        if (v < -126.0f) return 0.0f;
        if (v > 127.0f) return as_type<float>(0x7F800000u);
        float n = floor(v);
        float f = v - n;
        int e = int(n);
        float p = 1.0f + f * (0.6931471805599453f + f * (0.2402265069591007f +
            f * (0.0555041086648216f + f * (0.0096181291076285f +
            f * 0.0013333558146428f))));
        uint bits = as_type<uint>(p);
        bits += uint(e) << 23;
        return as_type<float>(bits);
    }
"""

source = r"""
    uint i = thread_position_in_grid.x;
    if (i >= n) return;
    float x = input[i];
    float inv_m2 = inv_m2_buf[0];

    log2_builtin[i] = precise::log2(x);
    log2_custom[i] = my_log2(x);
    exp2_builtin[i] = precise::exp2(x);
    exp2_custom[i] = my_exp2(x);
    pow_builtin[i] = precise::pow(x, inv_m2);
    pow_custom[i] = my_exp2(inv_m2 * my_log2(x));
    pow_custom2[i] = precise::exp2(inv_m2 * my_log2(x));
    pow_log_exp[i] = precise::exp(inv_m2 * precise::log(x));
"""

kernel = mx.fast.metal_kernel(
    name="test_custom_log2",
    input_names=["input", "inv_m2_buf"],
    output_names=["log2_builtin", "log2_custom", "exp2_builtin", "exp2_custom", "pow_builtin", "pow_custom", "pow_custom2", "pow_log_exp"],
    source=source,
    header=header,
)
outputs = kernel(
    inputs=[
        backend.asarray(test_values),
        backend.asarray(np.array([inv_m2], dtype=np.float32)),
    ],
    grid=(len(test_values), 1, 1),
    threadgroup=(len(test_values), 1, 1),
    output_shapes=[(len(test_values),)] * 8,
    output_dtypes=[mx.float32] * 8,
    template=[["n", len(test_values)]],
)
log2_b = backend.to_numpy(outputs[0])
log2_c = backend.to_numpy(outputs[1])
exp2_b = backend.to_numpy(outputs[2])
exp2_c = backend.to_numpy(outputs[3])
pow_b = backend.to_numpy(outputs[4])
pow_c = backend.to_numpy(outputs[5])
pow_c2 = backend.to_numpy(outputs[6])
pow_le = backend.to_numpy(outputs[7])

np_log2 = np.log2(test_values)
np_exp2 = np.exp2(test_values)
np_pow = np.power(test_values, inv_m2)

print("Value      | log2_builtin | log2_custom | pow_builtin | pow_custom | custom log2+Metal exp2 | Metal exp(log)")
for i, v in enumerate(test_values):
    print(f"{v:.8f} | {abs(log2_b[i] - np_log2[i]):.3e}     | {abs(log2_c[i] - np_log2[i]):.3e}    | "
          f"{abs(pow_b[i] - np_pow[i]):.3e}    | {abs(pow_c[i] - np_pow[i]):.3e}   | "
          f"{abs(pow_c2[i] - np_pow[i]):.3e}                    | {abs(pow_le[i] - np_pow[i]):.3e}")
