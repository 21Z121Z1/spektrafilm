// SPDX-License-Identifier: GPL-3.0-or-later
#include <metal_stdlib>
#include "spatial_math.h"
#include "philox.h"
using namespace metal;
namespace {
float value(sfm::Pair p) { return p.high + p.low; }
sfm::Pair subtract(sfm::Pair a, sfm::Pair b) { return sfm::add(a, {-b.high, -b.low}); }
sfm::Pair divide(sfm::Pair a, sfm::Pair b) {
    float q = a.high / b.high;
    sfm::Pair remainder = subtract(a, sfm::multiply(b, {q, 0}));
    return sfm::add({q, 0}, {(remainder.high + remainder.low) / b.high, 0});
}
float interpolate(device const float* axis, device const float* curves, uint n,
                  uint axis_stride, uint column, uint curve_stride, uint curve_column, float x) {
    auto first = sfm::load_pair(axis, column);
    auto last = sfm::load_pair(axis, (n - 1) * axis_stride + column);
    if (subtract({x, 0}, first).high <= 0) return value(sfm::load_pair(curves, curve_column));
    if (subtract({x, 0}, last).high >= 0) return value(sfm::load_pair(curves, (n - 1) * curve_stride + curve_column));
    uint lo = 0, hi = n;
    while (lo < hi) {
        uint mid = lo + (hi - lo) / 2;
        if (subtract({x, 0}, sfm::load_pair(axis, mid * axis_stride + column)).high >= 0) lo = mid + 1;
        else hi = mid;
    }
    uint j = lo - 1;
    auto x0 = sfm::load_pair(axis, j * axis_stride + column);
    auto dx = subtract(sfm::load_pair(axis, lo * axis_stride + column), x0);
    auto y0 = sfm::load_pair(curves, j * curve_stride + curve_column);
    auto dy = subtract(sfm::load_pair(curves, lo * curve_stride + curve_column), y0);
    return value(sfm::add(y0, sfm::multiply(divide(subtract({x, 0}, x0), dx), dy)));
}
// Stable log Poisson mass. Near the mean, a deviance series avoids subtracting
// O(lambda*log(lambda)) terms. No Gaussian approximation is used for sampling.
float poisson_log_mass(float k, float lambda) {
    if (k == 0) return -lambda;
    float correction;
    if (k < 16) {
        float factorial = 0;
        for (uint i = 2; i <= uint(k); ++i) factorial += log(float(i));
        return -lambda + k * log(lambda) - factorial;
    }
    float r = 1.0f / k, r2 = r * r;
    correction = r * (1.0f/12.0f - r2 * (1.0f/360.0f - r2/1260.0f));
    float delta = k - lambda, deviance;
    if (fabs(delta) < 0.1f * (k + lambda)) {
        float v = delta / (k + lambda), power = 2 * k * v;
        deviance = delta * v;
        float v2 = v * v;
        for (uint j = 1; j < 16; ++j) {
            power *= v2;
            deviance += power / float(2 * j + 1);
        }
    } else deviance = k * log(k / lambda) + lambda - k;
    return -correction - 0.5f * log(6.283185307179586f * k) - deviance;
}
float poisson(thread sfm_rng::Stream& rng, float lambda, device atomic_uint* failure) {
    if (!isfinite(lambda) || lambda < 0 || lambda > 1048576.0f) {
        atomic_fetch_or_explicit(failure, 2u, memory_order_relaxed); return 0;
    }
    if (lambda == 0) return 0;
    if (lambda < 10) {
        float product = 1, threshold = exp(-lambda);
        for (uint k = 0; k < 256; ++k) {
            product *= rng.uniform();
            if (product <= threshold) return float(k);
        }
    } else {
        float root = sqrt(lambda), b = 0.931f + 2.53f * root;
        float a = -0.059f + 0.02483f * b;
        float inverse_alpha = 1.1239f + 1.1328f / (b - 3.4f);
        float squeeze = 0.9277f - 3.6224f / (b - 2.0f);
        for (uint attempt = 0; attempt < 256; ++attempt) {
            float u = rng.uniform() - 0.5f, v = rng.uniform(), us = 0.5f - fabs(u);
            float k = floor((2 * a / us + b) * u + lambda + 0.43f);
            if (k < 0) continue;
            if (us >= 0.07f && v <= squeeze) return k;
            if (us < 0.013f && v > us) continue;
            if (log(v * inverse_alpha / (a / (us * us) + b)) <= poisson_log_mass(k, lambda)) return k;
        }
    }
    // A finite rejection cap is not a biased fallback. Fail the entire result.
    atomic_fetch_or_explicit(failure, 4u, memory_order_relaxed); return 0;
}
}
// A 32x32 tile with a padded row avoids strided device writes and shared
// memory bank conflicts. Every lane reaches the barrier, including edge tiles.
kernel void sfm_transpose(device const float* src [[buffer(0)]], device float* dst [[buffer(1)]],
                           constant uint* m [[buffer(3)]], uint lane [[thread_index_in_threadgroup]],
                           uint3 group [[threadgroup_position_in_grid]],
                           uint3 group_size [[threads_per_threadgroup]]) {
    threadgroup float tile[32][33];
    uint tiles_x=(m[1]+31)/32, tile_x=group.x%tiles_x, tile_y=group.x/tiles_x;
    for(uint j=lane;j<1024;j+=group_size.x) {
        uint x=j%32,y=j/32,gx=tile_x*32+x,gy=tile_y*32+y;
        tile[y][x]=(gx<m[1] && gy<m[0])?src[(gy*m[1]+gx)*m[2]+m[3]]:0;
    }
    threadgroup_barrier(mem_flags::mem_threadgroup);
    for(uint j=lane;j<1024;j+=group_size.x) {
        uint x=j%32,y=j/32,gx=tile_y*32+x,gy=tile_x*32+y;
        if(gx<m[0] && gy<m[1])dst[(gy*m[0]+gx)*m[2]+m[3]]=tile[x][y];
    }
}
// m = [H,W,C,opcode,args[0..11]]. Constants are bound at the operation offset.
kernel void sfm_pointwise(device const float* a [[buffer(0)]], device const float* b [[buffer(1)]],
                          device float* out [[buffer(2)]], device const float* d [[buffer(3)]],
                          device atomic_uint* failure [[buffer(4)]], constant uint* m [[buffer(5)]],
                          uint i [[thread_position_in_grid]]) {
    if (i >= m[0] * m[1]) return;
    uint c = m[2], op = m[3], n = m[4];
    for (uint ch = 0; ch < c; ++ch) {
        float x = a[i*c+ch], y = 0;
        if (op == 2) y = value(sfm::add(sfm::multiply({x,0}, sfm::load_pair(d,ch)), sfm::load_pair(d,c+ch)));
        else if (op == 3) y = value(sfm::add(sfm::multiply({x,0}, sfm::load_pair(d,ch)),
                                           sfm::multiply({b[i*c+ch],0}, sfm::load_pair(d,c+ch))));
        else if (op == 4) y = interpolate(d, d+2*n*c, n, c, ch, c, ch, x);
        else if (op == 5) {
            sfm::Pair total{0,0};
            for (uint k=0; k<n; ++k) {
                device const float* row = d+16*k;
                auto density = sfm::load_pair(row,3);
                for (uint j=0;j<3;++j) density=sfm::add(density,sfm::multiply({a[3*i+j],0},sfm::load_pair(row,j)));
                float transmission = pow(10.0f,-value(density));
                auto light = sfm::multiply({transmission,0},sfm::load_pair(row,4));
                total=sfm::add(total,sfm::multiply(light,sfm::load_pair(row,5+ch)));
            }
            y=value(total);
        } else if (op == 6) {
            // Layer layout is the CPU model's [sample, sublayer, channel].
            device const float* curves=d+6*n;
            device const float* parameters=curves+18*n;
            ulong pixel=(ulong(m[10])<<32)+ulong(m[9])+ulong(i);
            sfm::Pair sum{0,0};
            uint first=m[11] ? m[11]-1 : 0, end=m[11] ? m[11] : 3;
            for (uint sl=first;sl<end;++sl) {
                uint column=sl*3+ch;
                float density=interpolate(d,curves,n,3,ch,9,column,m[5] ? -x : x);
                auto minimum=sfm::load_pair(parameters,4*column);
                auto maximum=sfm::load_pair(parameters,4*column+1);
                auto particles=sfm::load_pair(parameters,4*column+2);
                auto uniformity=sfm::load_pair(parameters,4*column+3);
                float p=clamp(value(divide(sfm::add({density,0},minimum),maximum)),1e-6f,1.0f-1e-6f);
                auto saturation=subtract({1,0},sfm::multiply(sfm::multiply({p,0},uniformity),{0.999999f,1.3278961e-8f}));
                float rate=value(divide(sfm::multiply(particles,{p,0}),saturation));
                sfm_rng::Stream random(pixel,m[8]+column,m[6],m[7]);
                float count=poisson(random,rate,failure);
                sum=sfm::add(sum,sfm::multiply(sfm::multiply({count,0},divide(maximum,particles)),saturation));
            }
            y=value(sum);
        } else if (op == 7) {
            ulong pixel=(ulong(m[10])<<32)+ulong(m[9])+ulong(i);
            sfm_rng::Stream random(pixel,m[8]+ch,m[6],m[7]);
            float z=sqrt(-2*log(random.uniform()))*cos(6.283185307179586f*random.uniform());
            float sigma=value(sfm::load_pair(d,0));
            y=exp(sigma*z-0.5f*sigma*sigma);
        } else if (op == 8) y=x*b[i*c+ch];
        else if (op == 9) y=log10(max(x,0.0f)+1e-10f);
        else if (op == 10) y=pow(10.0f,x);
        else if (op == 12) {
            sfm::Pair total{0,0};
            for(uint j=0;j<3;++j) total=sfm::add(total,sfm::multiply({a[3*i+j],0},sfm::load_pair(d,3*ch+j)));
            y=value(total);
        }
        else atomic_fetch_or_explicit(failure,8u,memory_order_relaxed);
        out[i*c+ch]=y;
    }
}
kernel void sfm_validate(device const float* values [[buffer(0)]], device atomic_uint* failure [[buffer(1)]],
                         constant uint& n [[buffer(2)]], uint i [[thread_position_in_grid]]) {
    if (i<n && !isfinite(values[i])) atomic_fetch_or_explicit(failure,1u,memory_order_relaxed);
}
kernel void sfm_pack_rgba(device const float* src [[buffer(0)]], device float* dst [[buffer(1)]],
                           constant uint* m [[buffer(2)]], uint i [[thread_position_in_grid]]) {
    if(i>=m[0]*m[1]) return;
    uint p=(i/m[1])*m[3]+i%m[1];
    for(uint ch=0;ch<3;++ch) dst[4*p+ch]=src[i*m[2]+min(ch,m[2]-1)];
    dst[4*p+3]=1;
}
kernel void sfm_philox_probe(device const uint* in [[buffer(0)]], device uint* out [[buffer(1)]],
                              uint i [[thread_position_in_grid]]) {
    if(i) return;
    auto r=sfm_rng::philox({in[0],in[1],in[2],in[3]},in[4],in[5]);
    out[0]=r.x;out[1]=r.y;out[2]=r.z;out[3]=r.w;
}

// Match Gaussian -> MIX arithmetic, but do not store and reread the final
// Gaussian plane. Rounding at the Gaussian result remains explicit.
namespace {
float mix_blurred(float blurred,float accumulated,device const float* coefficients,uint channel,uint channels) {
    return value(sfm::add(sfm::multiply({accumulated,0},sfm::load_pair(coefficients,channel)),
                          sfm::multiply({blurred,0},sfm::load_pair(coefficients,channels+channel))));
}
}
kernel void sfm_fir_mix(device const float* src [[buffer(0)]],device float* out [[buffer(1)]],
                        device const float* weights [[buffer(2)]],constant uint* m [[buffer(3)]],
                        device const float* acc [[buffer(4)]],device const float* scales [[buffer(5)]],
                        uint i [[thread_position_in_grid]]) {
    if(i>=m[0]*m[1])return;
    uint at=i*m[2]+m[3];
    float blurred=sfm::fir_value(src,weights,m[0],m[1],m[2],m[3],m[4],m[5],i);
    out[at]=mix_blurred(blurred,acc[at],scales,m[3],m[2]);
}
kernel void sfm_recursive_mix(device const float* src [[buffer(0)]],device float* out [[buffer(1)]],
                              device const float* coefficients [[buffer(2)]],constant uint* m [[buffer(3)]],
                              device const float* acc [[buffer(4)]],device const float* scales [[buffer(5)]],
                              uint line [[thread_position_in_grid]]) {
    uint length=m[4]==0?m[0]:m[1],lines=m[4]==0?m[1]:m[0];
    if(line>=lines)return;
    uint start=m[4]==0?line*m[2]+m[3]:line*m[1]*m[2]+m[3];
    uint step=m[4]==0?m[1]*m[2]:m[2];
    sfm::recursive_line(src,out,coefficients,start,step,length);
    for(uint j=0;j<length;++j){uint at=start+j*step;out[at]=mix_blurred(out[at],acc[at],scales,m[3],m[2]);}
}
kernel void sfm_copy_mix(device const float* src [[buffer(0)]],device float* out [[buffer(1)]],
                         constant uint* m [[buffer(3)]],device const float* acc [[buffer(4)]],
                         device const float* scales [[buffer(5)]],uint i [[thread_position_in_grid]]) {
    if(i<m[0]*m[1]){uint at=i*m[2]+m[3];out[at]=mix_blurred(src[at],acc[at],scales,m[3],m[2]);}
}
