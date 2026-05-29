// Halide AOT generators for colour transfer functions and curves.
// Compiles to arm-64-android. Do NOT compile on this machine.

#include <Halide.h>

using Halide::Buffer;
using Halide::Expr;
using Halide::Func;
using Halide::Generator;
using Halide::Var;

// ---------------------------------------------------------------------------
// cctf_encode: piecewise sRGB-style encoding transfer function
//   linear      [C, H, W]
//   gamma       (float)        — gamma for the power-law segment
//   threshold   (float)        — boundary between linear and power segments
//   linear_slope (float)       — multiplier for the linear segment (typically 12.92)
//   offset_b    (float)        — additive offset in linear segment (typically 0.0)
//   alpha       (float)        — multiplier inside pow() (typically 1.055)
//   d_coeff     (float)        — subtracted constant in pow() segment (typically 0.055)
//   → encoded   [C, H, W]
//
//   f(x) = select(x <= threshold,
//                 linear_slope * x + offset_b,
//                 alpha * pow(x, 1/gamma) - d_coeff)
// ---------------------------------------------------------------------------
class CCTFEncodeGenerator : public Generator<CCTFEncodeGenerator> {
public:
    Input<Buffer<float, 3>> linear{"linear"};  // [C, H, W]
    Input<float> gamma{"gamma"};
    Input<float> threshold{"threshold"};
    Input<float> linear_slope{"linear_slope"};
    Input<float> offset_b{"offset_b"};
    Input<float> alpha{"alpha"};
    Input<float> d_coeff{"d_coeff"};

    Output<Buffer<float, 3>> output{"output"}; // [C, H, W]

    void generate() {
        Var c("c"), x("x"), y("y");
        Expr v = linear(c, x, y);

        // sRGB-style piecewise: linear segment below threshold, power-law above.
        // The power-law segment uses 1/gamma (encode = raise to inverse gamma).
        Expr inv_gamma = 1.0f / gamma;
        output(c, x, y) = select(v <= threshold,
                                  linear_slope * v + offset_b,
                                  alpha * fast_pow(v, inv_gamma) - d_coeff);
    }

    void schedule() {
        Var c("c"), x("x"), y("y");
        output.vectorize(x, 8)
              .unroll(c, 3)
              .parallel(y);
    }
};

HALIDE_REGISTER_GENERATOR(CCTFEncodeGenerator, cctf_encode)

// ---------------------------------------------------------------------------
// cctf_decode: inverse encoding transfer function (linearise)
//   encoded     [C, H, W]
//   gamma       (float)
//   threshold   (float)   — raw threshold (in linear space), NOT pre-encoded
//   linear_slope (float)  — 'a' coefficient
//   offset_b    (float)   — 'b' additive offset in linear segment
//   alpha       (float)   — 'c' coefficient in pow() segment
//   d_coeff     (float)   — 'd' subtracted constant in pow() segment
//   → linear    [C, H, W]
//
//   encoded_threshold = linear_slope * threshold + offset_b
//   f⁻¹(y) = select(y <= encoded_threshold,
//                    (y - offset_b) / linear_slope,
//                    pow((y + d_coeff) / alpha, gamma))
// ---------------------------------------------------------------------------
class CCTFDecodeGenerator : public Generator<CCTFDecodeGenerator> {
public:
    Input<Buffer<float, 3>> encoded{"encoded"}; // [C, H, W]
    Input<float> gamma{"gamma"};
    Input<float> threshold{"threshold"};
    Input<float> linear_slope{"linear_slope"};
    Input<float> offset_b{"offset_b"};
    Input<float> alpha{"alpha"};
    Input<float> d_coeff{"d_coeff"};

    Output<Buffer<float, 3>> output{"output"}; // [C, H, W]

    void generate() {
        Var c("c"), x("x"), y("y");
        Expr v = encoded(c, x, y);

        // Threshold in encoded space: encode(threshold) = linear_slope * threshold + offset_b
        Expr encoded_threshold = linear_slope * threshold + offset_b;

        output(c, x, y) = select(v <= encoded_threshold,
                                  (v - offset_b) / linear_slope,
                                  fast_pow((v + d_coeff) / alpha, gamma));
    }

    void schedule() {
        Var c("c"), x("x"), y("y");
        output.vectorize(x, 8)
              .unroll(c, 3)
              .parallel(y);
    }
};

HALIDE_REGISTER_GENERATOR(CCTFDecodeGenerator, cctf_decode)

// ---------------------------------------------------------------------------
// highlight_boost: piecewise highlight boost (pass-through below threshold,
//   linear gain + offset above)
//   image      [C, H, W]
//   threshold  (float) — boundary between pass-through and boosted regions
//   boost      (float) — gain multiplier for highlights
//   offset     (float) — additive offset before gain
//   → boosted  [C, H, W]
//
//   f(x) = select(x < threshold,
//                 x,
//                 (x + offset) * boost)
//
// Matches JIT semantics in halide_backend.py _build_highlight_boost_pipeline.
// ---------------------------------------------------------------------------
class HighlightBoostGenerator : public Generator<HighlightBoostGenerator> {
public:
    Input<Buffer<float, 3>> image{"image"}; // [C, H, W]
    Input<float> threshold{"threshold"};
    Input<float> boost{"boost"};
    Input<float> offset{"offset"};

    Output<Buffer<float, 3>> output{"output"}; // [C, H, W]

    void generate() {
        Var c("c"), x("x"), y("y");
        Expr v = image(c, x, y);

        // Below threshold: pass through unchanged
        // Above threshold: apply gain with offset
        output(c, x, y) = select(v < threshold,
                                  v,
                                  (v + offset) * boost);
    }

    void schedule() {
        Var c("c"), x("x"), y("y");
        output.vectorize(x, 8)
              .unroll(c, 3)
              .parallel(y);
    }
};

HALIDE_REGISTER_GENERATOR(HighlightBoostGenerator, highlight_boost)
