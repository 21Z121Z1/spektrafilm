// Halide AOT generators for colour transfer functions and curves.
// Compiles to arm-64-android. Do NOT compile on this machine.

#include <Halide.h>

using Halide::Expr;
using Halide::Func;
using Halide::Generator;
using Halide::ImageParam;
using Halide::Var;

// ---------------------------------------------------------------------------
// cctf_encode: piecewise sRGB-style encoding transfer function
//   linear      [C, H, W]
//   gamma       (float)        — gamma for the power-law segment
//   coefficients (float[3])    — {threshold, linear_slope, alpha}
//     threshold:   boundary between linear and power segments
//     linear_slope: multiplier for the linear segment  (typically 12.92)
//     alpha:        multiplier inside pow()             (typically 1.055)
//   → encoded   [C, H, W]
//
//   f(x) = select(x <= threshold,
//                 linear_slope * x,
//                 alpha * pow(x, 1/gamma) - (alpha - 1))
// ---------------------------------------------------------------------------
class CCTFEncodeGenerator : public Generator<CCTFEncodeGenerator> {
public:
    ImageParam linear{Float(32), 3, "linear"};  // [C, H, W]
    Input<float> gamma{"gamma"};
    Input<float> threshold{"threshold"};
    Input<float> linear_slope{"linear_slope"};
    Input<float> alpha{"alpha"};

    Func output{"output"}; // [C, H, W]

    void generate() {
        Var c("c"), x("x"), y("y");
        Expr v = linear(c, x, y);

        // sRGB-style piecewise: linear segment below threshold, power-law above.
        // The power-law segment uses 1/gamma (encode = raise to inverse gamma).
        Expr inv_gamma = 1.0f / gamma;
        output(c, x, y) = select(v <= threshold,
                                  linear_slope * v,
                                  alpha * fast_pow(v, inv_gamma) - (alpha - 1.0f));
    }

    void schedule() {
        if (auto_schedule) return;
        Var c("c"), x("x"), y("y");
        output.vectorize(x, 8)
              .unroll(c)
              .parallel(y);
        output.dim(0).set_bounds(0, 3);
    }
};

HALIDE_REGISTER_GENERATOR(CCTFEncodeGenerator, cctf_encode)

// ---------------------------------------------------------------------------
// cctf_decode: inverse encoding transfer function (linearise)
//   encoded     [C, H, W]
//   gamma       (float)
//   threshold   (float)  — same threshold used during encoding
//   linear_slope (float)
//   alpha       (float)
//   → linear    [C, H, W]
//
//   f⁻¹(y) = select(y <= threshold,
//                    y / linear_slope,
//                    pow((y + (alpha - 1)) / alpha, gamma))
// ---------------------------------------------------------------------------
class CCTFDecodeGenerator : public Generator<CCTFDecodeGenerator> {
public:
    ImageParam encoded{Float(32), 3, "encoded"}; // [C, H, W]
    Input<float> gamma{"gamma"};
    Input<float> threshold{"threshold"};
    Input<float> linear_slope{"linear_slope"};
    Input<float> alpha{"alpha"};

    Func output{"output"}; // [C, H, W]

    void generate() {
        Var c("c"), x("x"), y("y");
        Expr v = encoded(c, x, y);

        // Threshold in encoded space: encode(threshold) = linear_slope * threshold
        // because the linear segment applies at/below that density.
        Expr encoded_threshold = linear_slope * threshold;

        output(c, x, y) = select(v <= encoded_threshold,
                                  v / linear_slope,
                                  fast_pow((v + (alpha - 1.0f)) / alpha, gamma));
    }

    void schedule() {
        if (auto_schedule) return;
        Var c("c"), x("x"), y("y");
        output.vectorize(x, 8)
              .unroll(c)
              .parallel(y);
        output.dim(0).set_bounds(0, 3);
    }
};

HALIDE_REGISTER_GENERATOR(CCTFDecodeGenerator, cctf_decode)

// ---------------------------------------------------------------------------
// highlight_boost: piecewise exponential highlight compression
//   image      [C, H, W]
//   threshold  (float) — pivot between linear and exponential regions
//   scale      (float) — linear-region gain multiplier
//   pivot      (float) — exponential curve anchor (density-space pivot)
//   → boosted  [C, H, W]
//
//   f(x) = select(x < threshold,
//                 x * scale,
//                 pivot + (x - pivot) * exp(-(x - pivot) * scale))
//
// This compresses highlights by blending toward the pivot value via an
// exponential decay, while leaving shadows linearly scaled.
// ---------------------------------------------------------------------------
class HighlightBoostGenerator : public Generator<HighlightBoostGenerator> {
public:
    ImageParam image{Float(32), 3, "image"}; // [C, H, W]
    Input<float> threshold{"threshold"};
    Input<float> scale{"scale"};
    Input<float> pivot{"pivot"};

    Func output{"output"}; // [C, H, W]

    void generate() {
        Var c("c"), x("x"), y("y");
        Expr v = image(c, x, y);

        // Linear region: simple gain
        Expr linear_part = v * scale;

        // Highlight region: exponential compression toward pivot
        Expr diff = v - pivot;
        Expr exp_part = pivot + diff * fast_exp(-diff * scale);

        output(c, x, y) = select(v < threshold, linear_part, exp_part);
    }

    void schedule() {
        if (auto_schedule) return;
        Var c("c"), x("x"), y("y");
        output.vectorize(x, 8)
              .unroll(c)
              .parallel(y);
        output.dim(0).set_bounds(0, 3);
    }
};

HALIDE_REGISTER_GENERATOR(HighlightBoostGenerator, highlight_boost)
