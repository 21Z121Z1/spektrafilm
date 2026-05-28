// Halide AOT generators for 2D image filters.
// Compiles to arm-64-android. Do NOT compile on this machine.

#include <Halide.h>

using Halide::BoundaryConditions::mirror_interior;
using Halide::Expr;
using Halide::Func;
using Halide::Generator;
using Halide::ImageParam;
using Halide::RDom;
using Halide::Var;

// ---------------------------------------------------------------------------
// gaussian_blur_fir: separable 2D FIR convolution
//   image     [C, H, W]
//   kernel_1d [K]           (K = radius*2 + 1)
//   → blurred [C, H, W]
// Two-pass: horizontal then vertical, mirror_interior boundary.
// ---------------------------------------------------------------------------
class GaussianBlurFIRGenerator : public Generator<GaussianBlurFIRGenerator> {
public:
    ImageParam image{Float(32), 3, "image"};        // [C, H, W]
    ImageParam kernel_1d{Float(32), 1, "kernel_1d"}; // [K]

    Func output{"output"}; // [C, H, W]
    Func blur_x{"blur_x"}; // intermediate horizontal pass

    void generate() {
        Var c("c"), x("x"), y("y");

        // Pad with mirror_interior boundary conditions.
        Func padded = mirror_interior(image);

        // kernel half-width
        Expr kw = kernel_1d.dim(0).extent();
        Expr half = kw / 2;

        // Horizontal pass
        RDom rx(0, kw, "rx");
        blur_x(c, x, y) += padded(c, x + rx - half, y) * kernel_1d(rx);

        // Vertical pass
        RDom ry(0, kw, "ry");
        output(c, x, y) += blur_x(c, x, y + ry - half) * kernel_1d(ry);
    }

    void schedule() {
        Var c("c"), x("x"), y("y");

        // Tile spatial dims, vectorize channel, parallelize outer tile loop.
        Var xo("xo"), yo("yo"), xi("xi"), yi("yi");
        output.tile(x, y, xo, yo, xi, yi, 64, 32)
              .vectorize(xi, 8)
              .unroll(c, 3)
              .parallel(yo);

        // Inline blur_x — fuses into output to avoid intermediate allocation.
        output.compute_root();
    }
};

HALIDE_REGISTER_GENERATOR(GaussianBlurFIRGenerator, gaussian_blur_fir)

// ---------------------------------------------------------------------------
// gaussian_blur_iir: Young-van Vliet 4-tap recursive filter
//   image  [C, H, W]
//   sigma  (float)
//   → blurred [C, H, W]
// Implements causal + anti-causal IIR per row, then per column.
// Coefficients derived from sigma via the YvV closed-form.
// ---------------------------------------------------------------------------
class GaussianBlurIIRGenerator : public Generator<GaussianBlurIIRGenerator> {
public:
    ImageParam image{Float(32), 3, "image"}; // [C, H, W]
    Input<float> sigma{"sigma"};

    Func output{"output"}; // [C, H, W]
    Func h_fwd{"h_fwd"}, h_out{"h_out"}, v_fwd{"v_fwd"}, v_out{"v_out"};

    void generate() {
        Var c("c"), x("x"), y("y");

        // --- Compute YvV coefficients from sigma ---
        Expr q = sigma * sigma;
        Expr m = 1.0f / (1.0f + 0.3186f * q + 0.01487f * q * q);
        Expr rho = select(q > 0.0f, 1.0f / (1.0f + 0.7038f * q), 0.0f);

        Expr b0 = m;
        Expr b1 = 4.0f * m * rho;
        Expr b2 = 6.0f * m * rho * rho;
        Expr b3 = 4.0f * m * rho * rho * rho;
        Expr a1 = -4.0f * rho;
        Expr a2 = 6.0f * rho * rho;
        Expr a3 = -4.0f * rho * rho * rho;
        Expr a4 = rho * rho * rho * rho;
        Expr gain = b0 + b1 + b2 + b3;
        Expr norm = select(gain > 1e-12f, 1.0f / gain, 1.0f);
        Expr nb0 = b0 * norm, nb1 = b1 * norm, nb2 = b2 * norm, nb3 = b3 * norm;

        Func padded = mirror_interior(image);
        Expr W = image.dim(2).extent();

        // --- Horizontal: forward causal scan ---
        h_fwd(c, x, y) = padded(c, x, y);  // boundary
        RDom xf(4, W - 4, "xf");
        h_fwd(c, xf, y) = nb0 * padded(c, xf, y)
                         + nb1 * padded(c, xf - 1, y)
                         + nb2 * padded(c, xf - 2, y)
                         + nb3 * padded(c, xf - 3, y)
                         - a1 * h_fwd(c, xf - 1, y)
                         - a2 * h_fwd(c, xf - 2, y)
                         - a3 * h_fwd(c, xf - 3, y)
                         - a4 * h_fwd(c, xf - 4, y);

        // --- Horizontal: backward anti-causal scan ---
        h_out(c, x, y) = h_fwd(c, x, y);  // boundary
        RDom xb(0, W - 4, "xb");  // reverse
        Expr xr = W - 1 - xb;
        h_out(c, xr, y) += nb0 * h_fwd(c, xr, y)
                          + nb1 * h_fwd(c, xr + 1, y)
                          + nb2 * h_fwd(c, xr + 2, y)
                          + nb3 * h_fwd(c, xr + 3, y)
                          - a1 * h_out(c, xr + 1, y)
                          - a2 * h_out(c, xr + 2, y)
                          - a3 * h_out(c, xr + 3, y)
                          - a4 * h_out(c, xr + 4, y);

        Expr H = image.dim(1).extent();

        // --- Vertical: forward causal scan ---
        v_fwd(c, x, y) = h_out(c, x, y);
        RDom yf(4, H - 4, "yf");
        v_fwd(c, x, yf) = nb0 * h_out(c, x, yf)
                         + nb1 * h_out(c, x, yf - 1)
                         + nb2 * h_out(c, x, yf - 2)
                         + nb3 * h_out(c, x, yf - 3)
                         - a1 * v_fwd(c, x, yf - 1)
                         - a2 * v_fwd(c, x, yf - 2)
                         - a3 * v_fwd(c, x, yf - 3)
                         - a4 * v_fwd(c, x, yf - 4);

        // --- Vertical: backward anti-causal scan ---
        v_out(c, x, y) = v_fwd(c, x, y);
        RDom yb(0, H - 4, "yb");
        Expr yr = H - 1 - yb;
        v_out(c, x, yr) += nb0 * v_fwd(c, x, yr)
                          + nb1 * v_fwd(c, x, yr + 1)
                          + nb2 * v_fwd(c, x, yr + 2)
                          + nb3 * v_fwd(c, x, yr + 3)
                          - a1 * v_out(c, x, yr + 1)
                          - a2 * v_out(c, x, yr + 2)
                          - a3 * v_out(c, x, yr + 3)
                          - a4 * v_out(c, x, yr + 4);

        output(c, x, y) = v_out(c, x, y);
    }

    void schedule() {
        Var c("c"), x("x"), y("y");

        // IIR is inherently sequential in scan direction — parallelize the
        // independent axis.  Horizontal scans are parallel over y; vertical
        // scans are parallel over x.
        // Store intermediate rows for vertical pass reuse.
        h_out.compute_root().parallel(y).vectorize(c, 4);
        v_out.compute_root().parallel(x).vectorize(c, 4);
        output.parallel(y).vectorize(c, 4);
    }
};

HALIDE_REGISTER_GENERATOR(GaussianBlurIIRGenerator, gaussian_blur_iir)
