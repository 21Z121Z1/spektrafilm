// SPDX-License-Identifier: GPL-3.0-or-later
// Independent implementation of the Philox4x32-10 permutation (Salmon et al.,
// SC11). Constants and known-answer vectors identify the published algorithm.
#pragma once
#ifdef __METAL_VERSION__
#include <metal_stdlib>
namespace sfm_rng { using Word = uint; using Wide = ulong;
#else
#include <cstdint>
namespace sfm_rng { using Word = uint32_t; using Wide = uint64_t;
#endif
struct Block { Word x, y, z, w; };
inline Block philox(Block counter, Word key0, Word key1) {
    for (unsigned round = 0; round < 10; ++round) {
        Wide left = Wide(counter.x) * Wide(0xD2511F53u);
        Wide right = Wide(counter.z) * Wide(0xCD9E8D57u);
        counter = {Word(right >> 32) ^ counter.y ^ key0, Word(right),
                   Word(left >> 32) ^ counter.w ^ key1, Word(left)};
        key0 += 0x9E3779B9u;
        key1 += 0xBB67AE85u;
    }
    return counter;
}
// Versioned stream map: (pixel low, pixel high, stream, block) and seed64.
// A renderer changing tiles or worker counts must not change these words.
struct Stream {
    Wide pixel;
    Word stream, key0, key1, block = 0, lane = 4;
    Block current{};
    Stream(Wide p, Word s, Word k0, Word k1) : pixel(p), stream(s), key0(k0), key1(k1) {}
    Word next() {
        if (lane == 4) {
            current = philox({Word(pixel), Word(pixel >> 32), stream, block++}, key0, key1);
            lane = 0;
        }
        Word value = lane == 0 ? current.x : (lane == 1 ? current.y : (lane == 2 ? current.z : current.w));
        ++lane;
        return value;
    }
    float uniform() {
        // 23 random bits at cell midpoints: strictly between zero and one,
        // including after float32 rounding. No log(0), no rounded-to-one bin.
        return (float(next() >> 9) + 0.5f) * 0x1p-23f;
    }
};
} // namespace sfm_rng
