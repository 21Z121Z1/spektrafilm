// SPDX-License-Identifier: GPL-3.0-or-later
// HOST emulation of shared arithmetic. Never linked into the production dylib.
#include "spatial.h"
#include "spatial_math.h"
#include <vector>
extern "C" void sfm_host(const float* input, float* output,
                          unsigned height, unsigned width, unsigned channels,
                          const sfm_channel* plan, const float* constants) {
    std::vector<float> scratch(size_t(height) * width * channels);
    for (unsigned pass = 0; pass != 2; ++pass) {
        for (unsigned channel = 0; channel < channels; ++channel) {
            const auto& p = plan[channel];
            if (p.kind == 0) {
                if (pass == 0)
                    for (size_t i = channel; i < scratch.size(); i += channels) output[i] = input[i];
                continue;
            }
            unsigned axis = p.kind == 2 ? 1 - pass : pass;
            const float* source = pass == 0 ? input : scratch.data();
            float* destination = pass == 0 ? scratch.data() : output;
            if (p.kind == 1) {
                for (unsigned pixel = 0; pixel < height * width; ++pixel)
                    destination[pixel * channels + channel] = sfm::fir_value(
                        source, constants + p.offset, height, width, channels,
                        channel, axis, p.radius, pixel);
            } else {
                unsigned count = axis == 0 ? width : height;
                for (unsigned line = 0; line < count; ++line) {
                    unsigned start = axis == 0 ? line * channels + channel : line * width * channels + channel;
                    sfm::recursive_line(source, destination, constants + p.offset,
                        start, axis == 0 ? width * channels : channels, axis == 0 ? height : width);
                }
            }
        }
    }
}
extern "C" float sfm_host_probe(float a, float b) {
    return sfm::add({a, 0.0f}, {b, 0.0f}).low;
}
