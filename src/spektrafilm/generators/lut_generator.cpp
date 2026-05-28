// Halide AOT generators for LUT interpolation.
// Compiles to arm-64-android. Do NOT compile on this machine.

#include <Halide.h>

using Halide::Expr;
using Halide::Func;
using Halide::Generator;
using Halide::ImageParam;
using Halide::Var;

// ---------------------------------------------------------------------------
// interp_1d: linear interpolation in a 1-D LUT with clamp boundary
//   values    [N]             — evenly spaced LUT values
//   positions [N]             — corresponding input positions (monotonic)
//   query     [H, W]          — input samples
//   → result  [H, W]
//
// For each query point, find the two bracketing LUT entries and linearly
// interpolate.  Positions are assumed monotonically increasing.
// Out-of-range queries are clamped to the nearest endpoint.
// ---------------------------------------------------------------------------
class Interp1DGenerator : public Generator<Interp1DGenerator> {
public:
    ImageParam values{Float(32), 1, "values"};       // [N]
    ImageParam positions{Float(32), 1, "positions"};  // [N]
    ImageParam query{Float(32), 2, "query"};          // [H, W]

    Func output{"output"}; // [H, W]

    void generate() {
        Var x("x"), y("y");
        Expr N = values.dim(0).extent();
        Expr q = query(x, y);

        // Binary-search–free approach: scan positions to find bracket.
        // For an AOT generator we assume positions are evenly spaced or
        // use a simple linear scan (acceptable for small N).
        // A production version would bake in a binary search via select tree
        // or require evenly-spaced positions.  Here we use the evenly-spaced
        // shortcut: pos = (q - pos_min) / step, clamped.
        Expr pos_min = positions(0);
        Expr pos_max = positions(N - 1);
        Expr step = (pos_max - pos_min) / cast<float>(N - 1);

        // Normalised index in [0, N-1]
        Expr idx_f = clamp((q - pos_min) / step, 0.0f, cast<float>(N - 1));
        Expr idx_lo = clamp(cast<int>(floor(idx_f)), 0, N - 2);
        Expr idx_hi = idx_lo + 1;
        Expr frac = idx_f - cast<float>(idx_lo);

        Expr v_lo = values(idx_lo);
        Expr v_hi = values(idx_hi);

        // Linear blend
        output(x, y) = v_lo + frac * (v_hi - v_lo);
    }

    void schedule() {
        if (auto_schedule) return;
        Var x("x"), y("y");
        output.vectorize(x, 8)
              .parallel(y);
    }
};

HALIDE_REGISTER_GENERATOR(Interp1DGenerator, interp_1d)

// ---------------------------------------------------------------------------
// lut_2d_cubic: Mitchell-Netravali (B=1/3, C=1/3) 2-D LUT sampling
//   lut    [size, size, C]   — 2-D LUT with per-pixel channel values
//   image  [H, W, 2]         — normalised coordinates (u, v) in [0, 1]
//   → result [H, W, C]
//
// 4×4 bicubic kernel using the Mitchell-Netravali basis with B=C=1/3.
// Out-of-bounds samples are clamped to the LUT edge.
// ---------------------------------------------------------------------------
class Lut2DCubicGenerator : public Generator<Lut2DCubicGenerator> {
public:
    ImageParam lut{Float(32), 3, "lut"};     // [size, size, C]
    ImageParam image{Float(32), 3, "image"}; // [H, W, 2]

    Func output{"output"}; // [H, W, C]

    void generate() {
        Var x("x"), y("y"), ch("ch");

        Expr size = lut.dim(0).extent(); // assume square LUT
        Expr C = lut.dim(2).extent();

        // Normalised → grid coordinates
        Expr u = image(x, y, 0) * cast<float>(size - 1);
        Expr v = image(x, y, 1) * cast<float>(size - 1);

        // Integer base of the 4×4 footprint
        Expr ix = clamp(cast<int>(floor(u)) - 1, 0, size - 4);
        Expr iy = clamp(cast<int>(floor(v)) - 1, 0, size - 4);

        // Fractional part relative to the base (in [-1, 2])
        Expr fx = u - cast<float>(ix + 1);
        Expr fy = v - cast<float>(iy + 1);

        // Mitchell-Netravali kernel (B=1/3, C=1/3)
        auto mitchell = [](Expr t) -> Expr {
            Expr a = abs(t);
            // |t| in [0,1]:
            Expr w0 = (1.0f / 6.0f) * ((12.0f - 9.0f * 1.0f/3.0f - 6.0f * 1.0f/3.0f) * a * a * a
                                       + (-18.0f + 12.0f * 1.0f/3.0f + 6.0f * 1.0f/3.0f) * a * a
                                       + (6.0f - 2.0f * 1.0f/3.0f));
            // |t| in [1,2]:
            Expr w1 = (1.0f / 6.0f) * ((-1.0f * 1.0f/3.0f - 6.0f * 1.0f/3.0f) * a * a * a
                                       + (6.0f * 1.0f/3.0f + 30.0f * 1.0f/3.0f) * a * a
                                       + (-12.0f * 1.0f/3.0f - 48.0f * 1.0f/3.0f) * a
                                       + (8.0f * 1.0f/3.0f + 24.0f * 1.0f/3.0f));
            return select(a < 1.0f, w0, select(a < 2.0f, w1, 0.0f));
        };

        // Pre-compute 4 kernel weights per axis
        Expr wx0 = mitchell(fx + 1.0f);
        Expr wx1 = mitchell(fx);
        Expr wx2 = mitchell(fx - 1.0f);
        Expr wx3 = mitchell(fx - 2.0f);
        Expr wy0 = mitchell(fy + 1.0f);
        Expr wy1 = mitchell(fy);
        Expr wy2 = mitchell(fy - 1.0f);
        Expr wy3 = mitchell(fy - 2.0f);

        // Gather 4×4 neighbourhood, clamp to LUT bounds.
        // lut is [size, size, C] → lut(u, v, ch)
        auto sample = [&](int dx, int dy) -> Expr {
            Expr sx = clamp(ix + dx, 0, size - 1);
            Expr sy = clamp(iy + dy, 0, size - 1);
            return lut(sx, sy, ch);
        };

        // Weighted sum: rows first, then columns.
        Expr row0 = wx0 * sample(0, 0) + wx1 * sample(1, 0) + wx2 * sample(2, 0) + wx3 * sample(3, 0);
        Expr row1 = wx0 * sample(0, 1) + wx1 * sample(1, 1) + wx2 * sample(2, 1) + wx3 * sample(3, 1);
        Expr row2 = wx0 * sample(0, 2) + wx1 * sample(1, 2) + wx2 * sample(2, 2) + wx3 * sample(3, 2);
        Expr row3 = wx0 * sample(0, 3) + wx1 * sample(1, 3) + wx2 * sample(2, 3) + wx3 * sample(3, 3);

        output(x, y, ch) = wy0 * row0 + wy1 * row1 + wy2 * row2 + wy3 * row3;
    }

    void schedule() {
        if (auto_schedule) return;
        Var x("x"), y("y"), ch("ch");

        // Tile spatial dims; vectorize over the channel dimension.
        Var xo("xo"), yo("yo"), xi("xi"), yi("yi");
        output.tile(x, y, xo, yo, xi, yi, 32, 32)
              .vectorize(xi, 4)
              .unroll(ch)
              .parallel(yo);
        output.dim(2).set_bounds(0, 3);
    }
};

HALIDE_REGISTER_GENERATOR(Lut2DCubicGenerator, lut_2d_cubic)
