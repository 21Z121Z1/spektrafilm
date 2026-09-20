// SPDX-License-Identifier: GPL-3.0-or-later
#include "philox.h"
extern "C" void sfm_philox_host(const uint32_t* in, uint32_t* out) {
    auto r=sfm_rng::philox({in[0],in[1],in[2],in[3]},in[4],in[5]);
    out[0]=r.x;out[1]=r.y;out[2]=r.z;out[3]=r.w;
}
