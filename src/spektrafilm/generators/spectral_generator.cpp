// Halide AOT generators for spectral simulation kernels.
// Compiles to arm-64-android. Do NOT compile on this machine.

#include <Halide.h>

using Halide::Buffer;
using Halide::Generator;
using Halide::RDom;

// ---------------------------------------------------------------------------
// density_to_light: 10^(-density) * illuminant
//   density   [3, H, W]
//   illuminant [81, 3]
//   → light    [3, H, 81]
// ---------------------------------------------------------------------------
class DensityToLightGenerator : public Generator<DensityToLightGenerator> {
public:
    Input<Buffer<float, 3>> density{"density"};      // [3, H, W]
    Input<Buffer<float, 2>> illuminant{"illuminant"}; // [81, 3]

    Output<Buffer<float, 3>> output{"output"}; // [3, H, 81]

    void generate() {
        Var c("c"), y("y"), w("w");

        Expr d = density(c, y, w); // density value for channel c at row y, wavelength w
        // 10^(-d) = exp(-d * ln(10))
        Expr transmittance = fast_exp(-d * 2.302585093f);

        // illuminant[w, c]: wavelength w, channel c
        output(c, y, w) = transmittance * illuminant(w, c);
    }

    void schedule() {
        Var c("c"), y("y"), w("w");
        output.vectorize(c, 4)
              .parallel(y);
    }
};

HALIDE_REGISTER_GENERATOR(DensityToLightGenerator, density_to_light)

// ---------------------------------------------------------------------------
// light_to_raw: einsum('ijk,kl->ijl', light, sensitivity)
//   light      [3, H, 81]
//   sensitivity [81, 3]
//   → raw      [3, H, 3]
// Reduction over wavelength dimension K=81.
// ---------------------------------------------------------------------------
class LightToRawGenerator : public Generator<LightToRawGenerator> {
public:
    Input<Buffer<float, 3>> light{"light"};         // [3, H, 81]
    Input<Buffer<float, 2>> sensitivity{"sensitivity"}; // [81, 3]

    Output<Buffer<float, 3>> output{"output"}; // [3, H, 3]

    void generate() {
        Var c("c"), y("y"), s("s");

        RDom k(0, 81, "k");
        Func acc{"light_to_raw_acc"};
        acc(c, y, s) = 0.0f;
        acc(c, y, s) += light(c, y, k) * sensitivity(k, s);

        output(c, y, s) = acc(c, y, s);
    }

    void schedule() {
        Var c("c"), y("y"), s("s");
        output.vectorize(c, 4)
              .parallel(y);
    }
};

HALIDE_REGISTER_GENERATOR(LightToRawGenerator, light_to_raw)

// ---------------------------------------------------------------------------
// compute_density_spectral: result[c,y,wl] = sum_k density_cmy[k,y,wl] * channel_density[k,wl]
//   density_cmy     [3, H, 81]
//   channel_density  [3, 81]
//   → result        [3, H, 81]
// Reduction over channel index k (0..2).  Output channels are identical
// (c does not appear on the RHS) — matches JIT semantics.
// ---------------------------------------------------------------------------
class ComputeDensitySpectralGenerator : public Generator<ComputeDensitySpectralGenerator> {
public:
    Input<Buffer<float, 3>> density_cmy{"density_cmy"};       // [3, H, 81]
    Input<Buffer<float, 2>> channel_density{"channel_density"}; // [3, 81]

    Output<Buffer<float, 3>> output{"output"}; // [3, H, 81]

    void generate() {
        Var c("c"), y("y"), w("w");

        // result[c, y, wl] = sum_k density_cmy[k, y, wl] * channel_density[k, wl]
        // Note: c does not appear on the RHS — all output channels are identical.
        RDom k(0, 3, "k");
        Func acc{"density_spectral_acc"};
        acc(c, y, w) = 0.0f;
        acc(c, y, w) += density_cmy(k, y, w) * channel_density(k, w);

        output(c, y, w) = acc(c, y, w);
    }

    void schedule() {
        Var c("c"), y("y"), w("w");
        output.vectorize(c, 4)
              .parallel(y);
    }
};

HALIDE_REGISTER_GENERATOR(ComputeDensitySpectralGenerator, compute_density_spectral)
