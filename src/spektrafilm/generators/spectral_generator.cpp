// Halide AOT generators for spectral simulation kernels.
// Compiles to arm-64-android. Do NOT compile on this machine.

#include <Halide.h>

using Halide::Generator;
using Halide::ImageParam;
using Halide::OutputImageParam;
using Halide::RDom;

// ---------------------------------------------------------------------------
// density_to_light: 10^(-density) * illuminant
//   density   [3, H, W]
//   illuminant [81, 3]
//   → light    [3, H, 81]
// ---------------------------------------------------------------------------
class DensityToLightGenerator : public Generator<DensityToLightGenerator> {
public:
    ImageParam density{Float(32), 3, "density"};      // [3, H, W]
    ImageParam illuminant{Float(32), 2, "illuminant"}; // [81, 3]

    Func output{"output"}; // [3, H, 81]

    void generate() {
        Var c("c"), y("y"), w("w");

        Expr d = density(c, y, 0); // density value for channel c at (y, 0)
        // 10^(-d) = exp(-d * ln(10))
        Expr transmittance = fast_exp(-d * 2.302585093f);

        // illuminant[w, c]: wavelength w, channel c
        output(c, y, w) = transmittance * illuminant(w, c);
    }

    void schedule() {
        if (auto_schedule) return;
        output.vectorize(c, 4)
              .parallel(y);
        output.dim(0).set_bounds(0, 3);
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
    ImageParam light{Float(32), 3, "light"};         // [3, H, 81]
    ImageParam sensitivity{Float(32), 2, "sensitivity"}; // [81, 3]

    Func output{"output"}; // [3, H, 3]

    void generate() {
        Var c("c"), y("y"), s("s");

        RDom k(0, 81, "k");
        Func acc{"light_to_raw_acc"};
        acc(c, y, s) = 0.0f;
        acc(c, y, s) += light(c, y, k) * sensitivity(k, s);

        output(c, y, s) = acc(c, y, s);
    }

    void schedule() {
        if (auto_schedule) return;
        Var c("c"), y("y"), s("s");
        output.vectorize(c, 4)
              .parallel(y);
        output.dim(0).set_bounds(0, 3);
        output.dim(2).set_bounds(0, 3);
    }
};

HALIDE_REGISTER_GENERATOR(LightToRawGenerator, light_to_raw)

// ---------------------------------------------------------------------------
// compute_density_spectral: einsum('ijk,lk->ijl', density_cmy, channel_density)
//   density_cmy    [3, H, W]
//   channel_density [3, 81]
//   → result       [3, H, 81]
// Reduction over last dim of channel_density (W=81 in the notation above).
// ---------------------------------------------------------------------------
class ComputeDensitySpectralGenerator : public Generator<ComputeDensitySpectralGenerator> {
public:
    ImageParam density_cmy{Float(32), 3, "density_cmy"};       // [3, H, W]
    ImageParam channel_density{Float(32), 2, "channel_density"}; // [3, 81]

    Func output{"output"}; // [3, H, 81]

    void generate() {
        Var c("c"), y("y"), w("w");

        // einsum('ijk,lk->ijl'): for each (c, y, w) sum over k
        //   density_cmy[c, y, k] * channel_density[c, w]  — wait, that's not right.
        // Actually: result[c, y, l] = sum_k density_cmy[c, y, k] * channel_density[l, k]
        // So: output(c, y, w) = sum_k density_cmy(c, y, k) * channel_density(w, k)
        // But density_cmy last dim is W (spatial width), and channel_density last dim is 81.
        // Let's re-read: einsum('ijk,lk->ijl') with shapes [3,H,W] and [3,81]
        //   i=3, j=H, k=W=81 for first tensor; l=3, k=81 for second.
        // Wait — the plan says density_cmy [3, H, W] but the reduction is over "last dim
        // of channel_density" which is 81. The first tensor's last dim W must equal 81.
        // So output[c, y, l] = sum_k density_cmy[c, y, k] * channel_density[l, k]

        RDom k(0, 81, "k");
        Func acc{"density_spectral_acc"};
        acc(c, y, w) = 0.0f;
        acc(c, y, w) += density_cmy(c, y, k) * channel_density(w, k);

        output(c, y, w) = acc(c, y, w);
    }

    void schedule() {
        if (auto_schedule) return;
        output.vectorize(c, 4)
              .parallel(y);
        output.dim(0).set_bounds(0, 3);
    }
};

HALIDE_REGISTER_GENERATOR(ComputeDensitySpectralGenerator, compute_density_spectral)
