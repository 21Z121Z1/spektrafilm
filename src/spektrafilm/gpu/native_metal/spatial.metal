// SPDX-License-Identifier: GPL-3.0-or-later
#include "spatial_math.h"
using namespace metal;

// meta: height, width, channels, channel, axis, FIR radius.
kernel void sfm_fir(device const float* source [[buffer(0)]],
                    device float* result [[buffer(1)]],
                    device const float* constants [[buffer(2)]],
                    constant uint* meta [[buffer(3)]], uint pixel [[thread_position_in_grid]]) {
    if (pixel >= meta[0] * meta[1]) return;
    result[pixel * meta[2] + meta[3]] = sfm::fir_value(
        source, constants, meta[0], meta[1], meta[2], meta[3], meta[4], meta[5], pixel);
}
kernel void sfm_recursive(device const float* source [[buffer(0)]],
                          device float* result [[buffer(1)]],
                          device const float* constants [[buffer(2)]],
                          constant uint* meta [[buffer(3)]], uint line [[thread_position_in_grid]]) {
    bool vertical = meta[4] == 0;
    uint lines = vertical ? meta[1] : meta[0];
    if (line >= lines) return;
    uint start = vertical ? line * meta[2] + meta[3] : line * meta[1] * meta[2] + meta[3];
    uint step = vertical ? meta[1] * meta[2] : meta[2];
    sfm::recursive_line(source, result, constants, start, step, vertical ? meta[0] : meta[1]);
}
kernel void sfm_copy(device const float* source [[buffer(0)]],
                     device float* result [[buffer(1)]],
                     constant uint* meta [[buffer(3)]], uint pixel [[thread_position_in_grid]]) {
    if (pixel < meta[0] * meta[1]) {
        uint at = pixel * meta[2] + meta[3];
        result[at] = source[at];
    }
}
kernel void sfm_probe(device const float* source [[buffer(0)]],
                      device float* result [[buffer(1)]], uint i [[thread_position_in_grid]]) {
    if (i != 0) return;
    sfm::Pair sum = sfm::add({source[0], 0.0f}, {source[1], 0.0f});
    // Inspect the error term, not a recombined cancellation. Under unsafe
    // reassociation the latter can simplify to source[1] and falsely pass.
    // For (2^24, 1), TwoSum must retain 1 in the low word; erasing it breaks
    // the same compensation used by FIR accumulation and the IIR state.
    result[0] = sum.low;
    result[1] = 1.0f; // shader ABI epoch
}
