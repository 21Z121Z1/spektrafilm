// SPDX-License-Identifier: GPL-3.0-or-later
// Shared by Metal and the HOST-ONLY arithmetic test. Not a second film model.
#pragma once
#ifdef __METAL_VERSION__
#include <metal_stdlib>
#define SFM_DEVICE device
#define SFM_FMA metal::fma
#else
#include <cmath>
#define SFM_DEVICE
#define SFM_FMA std::fma
#endif

namespace sfm {
struct Pair { float high, low; };

// Error-free addition plus a renormalization. Requires no reassociation.
inline Pair add(Pair a, Pair b) {
    float s = a.high + b.high;
    float v = s - a.high;
    float e = ((a.high - (s - v)) + (b.high - v)) + (a.low + b.low);
    float h = s + e;
    return {h, e - (h - s)};
}
inline Pair multiply(Pair a, Pair b) {
    float p = a.high * b.high;
    float e = SFM_FMA(a.high, b.high, -p);
    e = e + a.high * b.low;
    e = e + a.low * b.high;
    e = e + a.low * b.low;
    float h = p + e;
    return {h, e - (h - p)};
}
inline Pair load_pair(SFM_DEVICE const float* p, unsigned i) {
    return {p[2u * i], p[2u * i + 1u]};
}
inline unsigned reflect_index(int index, unsigned length) {
    int period = 2 * int(length);
    int r = index % period;
    if (r < 0) r += period;
    return unsigned(r < int(length) ? r : period - 1 - r);
}

// One pixel/channel, vertical or horizontal. Weights are CPU-prepared pairs.
inline float fir_value(SFM_DEVICE const float* source,
                       SFM_DEVICE const float* weights,
                       unsigned height, unsigned width, unsigned channels,
                       unsigned channel, unsigned axis, unsigned radius,
                       unsigned pixel) {
    unsigned y = pixel / width, x = pixel % width;
    unsigned length = axis == 0 ? height : width;
    unsigned coord = axis == 0 ? y : x;
    Pair value{0.0f, 0.0f};
    for (int k = -int(radius); k <= int(radius); ++k) {
        unsigned r = reflect_index(int(coord) + k, length);
        unsigned at = axis == 0 ? (r * width + x) : (y * width + r);
        value = add(value, multiply({source[at * channels + channel], 0.0f},
                                   load_pair(weights, unsigned(k + int(radius)))));
    }
    return value.high + value.low;
}

// The CPU oracle stores float32 between sweeps, but carries float64 state.
// Two float32 words carry the recurrence here; no coefficients are derived here.
inline void recursive_line(SFM_DEVICE const float* source,
                           SFM_DEVICE float* destination,
                           SFM_DEVICE const float* coefficients,
                           unsigned start, unsigned step, unsigned length) {
    Pair b0 = load_pair(coefficients, 0), b1 = load_pair(coefficients, 1);
    Pair b2 = load_pair(coefficients, 2), b3 = load_pair(coefficients, 3);
    Pair s1{source[start], 0.0f}, s2 = s1, s3 = s1;
    for (unsigned i = 0; i < length; ++i) {
        unsigned at = start + i * step;
        Pair next = multiply(b0, {source[at], 0.0f});
        next = add(next, multiply(b1, s1));
        next = add(next, multiply(b2, s2));
        next = add(next, multiply(b3, s3));
        destination[at] = next.high + next.low;
        s3 = s2; s2 = s1; s1 = next;
    }
    s1 = {destination[start + (length - 1) * step], 0.0f};
    s2 = s1; s3 = s1;
    for (unsigned remaining = length; remaining != 0; --remaining) {
        unsigned at = start + (remaining - 1) * step;
        Pair next = multiply(b0, {destination[at], 0.0f});
        next = add(next, multiply(b1, s1));
        next = add(next, multiply(b2, s2));
        next = add(next, multiply(b3, s3));
        destination[at] = next.high + next.low;
        s3 = s2; s2 = s1; s1 = next;
    }
}
} // namespace sfm
#undef SFM_FMA
#undef SFM_DEVICE
