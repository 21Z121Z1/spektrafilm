// Halide AOT generators for LUT interpolation.
// Compiles to arm-64-android. Do NOT compile on this machine.

#include <Halide.h>

using Halide::Buffer;
using Halide::Expr;
using Halide::Func;
using Halide::Generator;
using Halide::Var;

// ---------------------------------------------------------------------------
// interp_1d: linear interpolation in a 1-D LUT with clamp boundary
//   values    [N]             — LUT values at arbitrary positions
//   positions [N]             — corresponding input positions (monotonic ascending)
//   query     [H, W]          — input samples
//   → result  [H, W]
//
// For each query point, find the two bracketing LUT entries and linearly
// interpolate.  Positions are monotonically increasing but NOT necessarily
// evenly spaced.  An RDom scan finds the correct interval.
// Out-of-range queries are clamped to the nearest endpoint.
// Matches JIT semantics in halide_backend.py _build_interp_1d_pipeline.
// ---------------------------------------------------------------------------
class Interp1DGenerator : public Generator<Interp1DGenerator> {
public:
    Input<Buffer<float, 1>> values{"values"};       // [N]
    Input<Buffer<float, 1>> positions{"positions"};  // [N]
    Input<Buffer<float, 2>> query{"query"};          // [H, W]

    Output<Buffer<float, 2>> output{"output"}; // [H, W]

    void generate() {
        Var x("x"), y("y");
        Expr N = values.dim(0).extent();
        Expr q = query(x, y);

        // Clamp query to [positions[0], positions[N-1]]
        Expr q_clamped = clamp(q, positions(0), positions(N - 1));

        // Scan all intervals with RDom.  For each interval i, if
        // positions[i] <= q < positions[i+1], accumulate the interpolated value.
        // Strict < on upper bound prevents double-counting at shared boundary points.
        // Exactly one interval matches (monotonic positions), so the sum is correct.
        // Edge case: q == positions[N-1] matches no interval (handled below).
        RDom r(0, N - 1, "ri");
        Expr pos_lo = positions(r);
        Expr pos_hi = positions(r + 1);
        Expr in_interval = (pos_lo <= q_clamped) && (q_clamped < pos_hi);
        Expr t = clamp((q_clamped - pos_lo) / (pos_hi - pos_lo), 0.0f, 1.0f);
        Expr interp_val = values(r) + t * (values(r + 1) - values(r));

        Func scan{"interp_scan"};
        scan(x, y) = 0.0f;
        scan(x, y) += select(in_interval, interp_val, 0.0f);

        // Track whether any interval matched (flag, not a value comparison).
        Func matched{"interp_matched"};
        matched(x, y) = 0.0f;
        matched(x, y) += select(in_interval, 1.0f, 0.0f);

        // If no interval matched (q == positions[N-1] exactly), use last value.
        output(x, y) = select(matched(x, y) > 0.0f,
                              scan(x, y),
                              values(N - 1));
    }

    void schedule() {
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
    Input<Buffer<float, 3>> lut{"lut"};     // [size, size, C]
    Input<Buffer<float, 3>> image{"image"}; // [H, W, 2]

    Output<Buffer<float, 3>> output{"output"}; // [H, W, C]

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
        Var x("x"), y("y"), ch("ch");

        // Tile spatial dims; vectorize over the channel dimension.
        Var xo("xo"), yo("yo"), xi("xi"), yi("yi");
        output.tile(x, y, xo, yo, xi, yi, 32, 32)
              .vectorize(xi, 4)
              .parallel(yo);
    }
};

HALIDE_REGISTER_GENERATOR(Lut2DCubicGenerator, lut_2d_cubic)
