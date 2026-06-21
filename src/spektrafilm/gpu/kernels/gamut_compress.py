"""Backend-portable output gamut compression.

Accelerates the per-pixel compression loop from
``spektrafilm.utils.gamut_compression`` on GPU backends (MLX / CuPy).
The expensive ``C_max(L, h)`` boundary table is still computed on CPU
(it runs once per output-color-space change); only the per-pixel
RGB → OkLab → compress → OkLab → RGB chain is ported.

CPU fallback delegates to the existing NumPy implementation so callers
can use ``compress_rgb_backend`` unconditionally.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

import numpy as np


# ---------------------------------------------------------------------------
# OkLab matrices (exact values from colour-science / Björn Ottosson)
# ---------------------------------------------------------------------------

# XYZ → LMS (M1)
_OKLAB_M1 = np.array([
    [0.8189330101, 0.3618667424, -0.1288597137],
    [0.0329845436, 0.9293118715,  0.0361456387],
    [0.0482003018, 0.2643662691,  0.6338517070],
], dtype=np.float64)

# LMS^(1/3) → Lab (M2)
_OKLAB_M2 = np.array([
    [0.2104542553,  0.7936177850, -0.0040720468],
    [1.9779984951, -2.4285922050,  0.4505937099],
    [0.0259040371,  0.7827717662, -0.8086757660],
], dtype=np.float64)

# LMS → XYZ (M1 inverse)
_OKLAB_M1_INV = np.array([
    [ 1.2270138511035211,  -0.5577999806518222,  0.2812561489664678],
    [-0.0405801784232806,   1.1122568696168302, -0.0716766786656012],
    [-0.0763812845057069,  -0.4214819784180127,  1.5861632204407947],
], dtype=np.float64)

# Lab → LMS^(1/3) (M2 inverse)
_OKLAB_M2_INV = np.array([
    [1.0,  0.3963377774,  0.2158037573],
    [1.0, -0.1055613458, -0.0638541728],
    [1.0, -0.0894841775, -1.2914855480],
], dtype=np.float64)


# ---------------------------------------------------------------------------
# JzAzBz constants (colour-science Safdar 2017 path)
# ---------------------------------------------------------------------------

_JZAZBZ_Y_W_CDM2 = 100.0
_JZAZBZ_B = 1.15
_JZAZBZ_G = 0.66
_JZAZBZ_D = -0.56
_JZAZBZ_D0 = 1.6295499532821566e-11
_ST2084_M1 = 2610.0 / 4096.0 * 0.25
_ST2084_M2_JZ = 1.7 * 2523.0 / 32.0
_ST2084_C1 = 3424.0 / 4096.0
_ST2084_C2 = 2413.0 / 4096.0 * 32.0
_ST2084_C3 = 2392.0 / 4096.0 * 32.0

_JZAZBZ_XYZ_TO_LMS = np.array([
    [0.41478972, 0.57999900, 0.01464800],
    [-0.20151000, 1.12064900, 0.05310080],
    [-0.01660080, 0.26480000, 0.66847990],
], dtype=np.float64)
_JZAZBZ_LMS_TO_XYZ = np.linalg.inv(_JZAZBZ_XYZ_TO_LMS)
_JZAZBZ_LMSP_TO_IZAZBZ = np.array([
    [0.500000, 0.500000, 0.000000],
    [3.524000, -4.066708, 0.542708],
    [0.199076, 1.096799, -1.295875],
], dtype=np.float64)
_JZAZBZ_IZAZBZ_TO_LMSP = np.linalg.inv(_JZAZBZ_LMSP_TO_IZAZBZ)
_JZAZBZ_DS_CONSTANTS = np.array([
    _JZAZBZ_Y_W_CDM2,
    1.0 / _JZAZBZ_Y_W_CDM2,
    10000.0,
    1.0 / 10000.0,
    _JZAZBZ_B,
    _JZAZBZ_B - 1.0,
    _JZAZBZ_G,
    1.0 - _JZAZBZ_G,
    1.0 + _JZAZBZ_D,
    -_JZAZBZ_D,
    _JZAZBZ_D0,
    _ST2084_M1,
    _ST2084_M2_JZ,
    _ST2084_C1,
    _ST2084_C2,
    _ST2084_C3,
    1.0 / _ST2084_M2_JZ,
    1.0 / _ST2084_M1,
], dtype=np.float64)


# ---------------------------------------------------------------------------
# CAM16-UCS constants (fixed display-review viewing conditions)
# ---------------------------------------------------------------------------

_CAM16UCS_L_A = 64.0
_CAM16UCS_Y_B = 20.0
_CAM16UCS_SURROUND_F = 1.0
_CAM16UCS_SURROUND_C = 0.69
_CAM16UCS_SURROUND_N_C = 1.0
_CAM16UCS_C1 = 0.007
_CAM16UCS_C2 = 0.0228

_CAM16_MATRIX_16 = np.array([
    [0.401288, 0.650173, -0.051461],
    [-0.250268, 1.204414, 0.045854],
    [-0.002079, 0.048952, 0.953127],
], dtype=np.float64)
_CAM16_MATRIX_16_INV = np.linalg.inv(_CAM16_MATRIX_16)


# ---------------------------------------------------------------------------
# Backend detection helpers
# ---------------------------------------------------------------------------

def _backend_supports_gpu(backend) -> bool:
    return backend is not None and bool(getattr(backend, "supports_gpu", False))


_JZAZBZ_CHROMA_MLX_KERNEL = None


def _backend_supports_mlx_custom_kernels(backend) -> bool:
    return _backend_supports_gpu(backend) and hasattr(backend, "mx")


def _split_float32_hi_lo(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    hi = np.asarray(values, dtype=np.float32)
    lo = np.asarray(np.asarray(values, dtype=np.float64) - hi.astype(np.float64), dtype=np.float32)
    return hi, lo


def _get_jzazbz_chroma_mlx_kernel(mx):
    """Return the fused MLX/Metal JzAzBz chroma kernel.

    The kernel keeps the full-frame path resident and uses double-single
    float32 compensation for the JzAzBz/PQ forward-inverse chain. Metal does
    not expose ``double`` on Apple GPUs, so this is the only resident path that
    can materially reduce the gap to the CPU float64 colour-science reference.
    """
    global _JZAZBZ_CHROMA_MLX_KERNEL
    if _JZAZBZ_CHROMA_MLX_KERNEL is not None:
        return _JZAZBZ_CHROMA_MLX_KERNEL

    header = r"""
        #include <metal_stdlib>
        using namespace metal;

        struct DS {
            float hi;
            float lo;
        };

        inline DS ds_make(float x) {
            DS r = {x, 0.0f};
            return r;
        }

        inline DS ds_make_pair(float hi, float lo) {
            DS r = {hi, lo};
            return r;
        }

        inline DS ds_const(
            const device float* constants_hi,
            const device float* constants_lo,
            int index
        ) {
            return ds_make_pair(constants_hi[index], constants_lo[index]);
        }

        inline DS ds_const(
            const constant float* constants_hi,
            const constant float* constants_lo,
            int index
        ) {
            return ds_make_pair(constants_hi[index], constants_lo[index]);
        }

        inline float ds_value(DS a) {
            return a.hi + a.lo;
        }

        inline DS ds_quick_two_sum(float a, float b) {
            float s = a + b;
            float e = b - (s - a);
            DS r = {s, e};
            return r;
        }

        inline DS ds_two_sum(float a, float b) {
            float s = a + b;
            float bb = s - a;
            float e = (a - (s - bb)) + (b - bb);
            DS r = {s, e};
            return r;
        }

        inline DS ds_norm(DS a) {
            return ds_quick_two_sum(a.hi, a.lo);
        }

        inline DS ds_add(DS a, DS b) {
            DS s = ds_two_sum(a.hi, b.hi);
            float lo = s.lo + a.lo + b.lo;
            return ds_quick_two_sum(s.hi, lo);
        }

        inline DS ds_add_float(DS a, float b) {
            return ds_add(a, ds_make(b));
        }

        inline DS ds_sub(DS a, DS b) {
            DS s = ds_two_sum(a.hi, -b.hi);
            float lo = s.lo + a.lo - b.lo;
            return ds_quick_two_sum(s.hi, lo);
        }

        inline DS ds_sub_float(DS a, float b) {
            return ds_sub(a, ds_make(b));
        }

        inline DS ds_float_sub(float a, DS b) {
            return ds_sub(ds_make(a), b);
        }

        inline DS ds_mul(DS a, DS b) {
            float p = a.hi * b.hi;
            float e = fma(a.hi, b.hi, -p) + a.hi * b.lo + a.lo * b.hi;
            return ds_quick_two_sum(p, e);
        }

        inline DS ds_mul_float(DS a, float b) {
            float p = a.hi * b;
            float e = fma(a.hi, b, -p) + a.lo * b;
            return ds_quick_two_sum(p, e);
        }

        inline DS ds_mul_const(
            DS a,
            const device float* constants_hi,
            const device float* constants_lo,
            int index
        ) {
            return ds_mul(a, ds_const(constants_hi, constants_lo, index));
        }

        inline DS ds_div(DS a, DS b) {
            float q1 = a.hi / b.hi;
            DS qb = ds_mul_float(b, q1);
            DS r = ds_sub(a, qb);
            float q2 = ds_value(r) / b.hi;
            return ds_add_float(ds_make(q1), q2);
        }

        inline DS ds_div_float(DS a, float b) {
            return ds_div(a, ds_make(b));
        }

        inline DS ds_safe_div(DS a, DS b, float eps) {
            float bv = ds_value(b);
            if (fabs(bv) < eps) {
                b = ds_make(bv < 0.0f ? -eps : eps);
            }
            return ds_div(a, b);
        }

        inline DS ds_signed_pow(DS x, float exponent) {
            float xh = x.hi;
            float ax = fabs(xh);
            if (ax < 1.0e-30f) {
                return ds_make(0.0f);
            }
            float mag = precise::exp2(exponent * precise::log2(ax));
            float y = xh < 0.0f ? -mag : mag;
            float dy1 = (exponent * y / xh) * x.lo;
            float dy2 = (
                exponent * (exponent - 1.0f) * y / (2.0f * xh * xh)
            ) * (x.lo * x.lo);
            return ds_add_float(ds_make(y), dy1 + dy2);
        }

        inline DS ds_signed_pow_exp_log(DS x, float exponent) {
            float xh = x.hi;
            float ax = fabs(xh);
            if (ax < 1.0e-30f) {
                return ds_make(0.0f);
            }
            // For the small exponents used in the forward PQ EOTF, Metal's
            // exp(y * log(x)) happens to be closer to numpy/libm than either
            // precise::pow or exp2(y * log2(x)).
            float mag = precise::exp(exponent * precise::log(ax));
            float y = xh < 0.0f ? -mag : mag;
            float dy1 = (exponent * y / xh) * x.lo;
            float dy2 = (
                exponent * (exponent - 1.0f) * y / (2.0f * xh * xh)
            ) * (x.lo * x.lo);
            return ds_add_float(ds_make(y), dy1 + dy2);
        }

        inline DS ds_pq_inverse_jz_basic(
            DS C,
            const device float* constants_hi,
            const device float* constants_lo
        ) {
            float m1 = ds_value(ds_const(constants_hi, constants_lo, 11));
            float m2 = ds_value(ds_const(constants_hi, constants_lo, 12));
            DS Yp = ds_signed_pow(ds_mul_const(C, constants_hi, constants_lo, 3), m1);
            DS numerator = ds_add(
                ds_mul_const(Yp, constants_hi, constants_lo, 14),
                ds_const(constants_hi, constants_lo, 13)
            );
            DS denominator = ds_add_float(
                ds_mul_const(Yp, constants_hi, constants_lo, 15),
                1.0f
            );
            return ds_signed_pow(ds_div(numerator, denominator), m2);
        }

        inline DS ds_pq_jz_basic(
            DS N,
            const device float* constants_hi,
            const device float* constants_lo
        ) {
            float inv_m2 = ds_value(ds_const(constants_hi, constants_lo, 16));
            float inv_m1 = ds_value(ds_const(constants_hi, constants_lo, 17));
            DS Vp = ds_signed_pow_exp_log(N, inv_m2);
            DS n = ds_sub(Vp, ds_const(constants_hi, constants_lo, 13));
            if (ds_value(n) < 0.0f) {
                n = ds_make(0.0f);
            }
            DS denominator = ds_sub(
                ds_const(constants_hi, constants_lo, 14),
                ds_mul_const(Vp, constants_hi, constants_lo, 15)
            );
            DS ratio = ds_safe_div(n, denominator, 1.0e-20f);
            return ds_mul_const(
                ds_signed_pow(ratio, inv_m1),
                constants_hi,
                constants_lo,
                2
            );
        }

        inline DS ds_pq_inverse_jz(
            DS C,
            const device float* constants_hi,
            const device float* constants_lo
        ) {
            return ds_pq_inverse_jz_basic(C, constants_hi, constants_lo);
        }

        inline DS ds_pq_jz(
            DS N,
            const device float* constants_hi,
            const device float* constants_lo
        ) {
            return ds_pq_jz_basic(N, constants_hi, constants_lo);
        }

        inline DS ds_reinhard_knee(DS d, float threshold, float limit, float power) {
            float dv = ds_value(d);
            if (!(dv > threshold)) {
                return d;
            }
            float scale = limit - threshold;
            float x = max((dv - threshold) / scale, 0.0f);
            float y;
            if (x > 1.0f) {
                float inv_x = 1.0f / x;
                y = 1.0f / precise::pow(1.0f + precise::pow(inv_x, power), 1.0f / power);
            } else {
                y = x / precise::pow(1.0f + precise::pow(x, power), 1.0f / power);
            }
            return ds_make(threshold + scale * y);
        }

        inline DS ds_dot3_matrix(
            DS x,
            DS y,
            DS z,
            const device float* matrix_hi,
            const device float* matrix_lo,
            int row
        ) {
            int base = row * 3;
            DS acc = ds_mul(x, ds_make_pair(matrix_hi[base + 0], matrix_lo[base + 0]));
            acc = ds_add(acc, ds_mul(y, ds_make_pair(matrix_hi[base + 1], matrix_lo[base + 1])));
            acc = ds_add(acc, ds_mul(z, ds_make_pair(matrix_hi[base + 2], matrix_lo[base + 2])));
            return acc;
        }

        inline DS ds_dot3_const(
            DS x,
            DS y,
            DS z,
            float m00,
            float m01,
            float m02
        ) {
            DS acc = ds_mul_float(x, m00);
            acc = ds_add(acc, ds_mul_float(y, m01));
            acc = ds_add(acc, ds_mul_float(z, m02));
            return acc;
        }

        inline float finite_float(float v) {
            if (isnan(v)) {
                return 0.0f;
            }
            if (isinf(v)) {
                return v < 0.0f ? -3.4028234663852886e38f : 3.4028234663852886e38f;
            }
            return v;
        }
    """

    source = r"""
        uint pixel = thread_position_in_grid.x;
        uint total = rgb_shape[0];
        if (pixel >= total) {
            return;
        }

        uint base = pixel * 3;
        DS r = ds_make(float(rgb[base + 0]));
        DS g = ds_make(float(rgb[base + 1]));
        DS b = ds_make(float(rgb[base + 2]));
        DS Y_w = ds_const(jz_constants_hi, jz_constants_lo, 0);
        DS inv_Y_w = ds_const(jz_constants_hi, jz_constants_lo, 1);
        DS jz_B = ds_const(jz_constants_hi, jz_constants_lo, 4);
        DS jz_B_minus_one = ds_const(jz_constants_hi, jz_constants_lo, 5);
        DS jz_G = ds_const(jz_constants_hi, jz_constants_lo, 6);
        DS one_minus_jz_G = ds_const(jz_constants_hi, jz_constants_lo, 7);
        DS one_plus_jz_D = ds_const(jz_constants_hi, jz_constants_lo, 8);
        DS minus_jz_D = ds_const(jz_constants_hi, jz_constants_lo, 9);
        DS jz_D0 = ds_const(jz_constants_hi, jz_constants_lo, 10);

        DS X = ds_dot3_matrix(r, g, b, matrix_rgb_to_xyz_hi, matrix_rgb_to_xyz_lo, 0);
        DS Y = ds_dot3_matrix(r, g, b, matrix_rgb_to_xyz_hi, matrix_rgb_to_xyz_lo, 1);
        DS Z = ds_dot3_matrix(r, g, b, matrix_rgb_to_xyz_hi, matrix_rgb_to_xyz_lo, 2);
        X = ds_mul(X, Y_w);
        Y = ds_mul(Y, Y_w);
        Z = ds_mul(Z, Y_w);

        DS Xp = ds_sub(ds_mul(X, jz_B), ds_mul(Z, jz_B_minus_one));
        DS Yp = ds_add(ds_mul(Y, jz_G), ds_mul(X, one_minus_jz_G));

        DS L = ds_dot3_matrix(Xp, Yp, Z, jz_xyz_to_lms_hi, jz_xyz_to_lms_lo, 0);
        DS M = ds_dot3_matrix(Xp, Yp, Z, jz_xyz_to_lms_hi, jz_xyz_to_lms_lo, 1);
        DS S = ds_dot3_matrix(Xp, Yp, Z, jz_xyz_to_lms_hi, jz_xyz_to_lms_lo, 2);

        DS Lp = ds_pq_inverse_jz(L, jz_constants_hi, jz_constants_lo);
        DS Mp = ds_pq_inverse_jz(M, jz_constants_hi, jz_constants_lo);
        DS Sp = ds_pq_inverse_jz(S, jz_constants_hi, jz_constants_lo);

        DS Iz = ds_dot3_matrix(
            Lp, Mp, Sp, jz_lmsp_to_izazbz_hi, jz_lmsp_to_izazbz_lo, 0
        );
        DS az = ds_dot3_matrix(
            Lp, Mp, Sp, jz_lmsp_to_izazbz_hi, jz_lmsp_to_izazbz_lo, 1
        );
        DS bz = ds_dot3_matrix(
            Lp, Mp, Sp, jz_lmsp_to_izazbz_hi, jz_lmsp_to_izazbz_lo, 2
        );

        DS Jz = ds_sub(
            ds_div(ds_mul(Iz, one_plus_jz_D), ds_sub(ds_make(1.0f), ds_mul(Iz, minus_jz_D))),
            jz_D0
        );

        float use_lightness = params[6];
        if (use_lightness > 0.5f) {
            DS Jz_norm = ds_div_float(Jz, params[5]);
            Jz = ds_mul_float(
                ds_reinhard_knee(Jz_norm, params[2], params[3], params[4]),
                params[5]
            );
        }

        float az_v = ds_value(az);
        float bz_v = ds_value(bz);
        float chroma_radius_scale = max(fabs(az_v), fabs(bz_v));
        float Cz = 0.0f;
        if (chroma_radius_scale > 0.0f) {
            float az_r = az_v / chroma_radius_scale;
            float bz_r = bz_v / chroma_radius_scale;
            Cz = chroma_radius_scale * precise::sqrt(az_r * az_r + bz_r * bz_r);
        }
        float hz = precise::atan2(bz_v, az_v);

        int n_L = int(L_grid_shape[0]);
        int n_h = int(h_grid_shape[0]);
        DS L0_ds = ds_const(cmax_grid_hi, cmax_grid_lo, 0);
        DS L1_ds = ds_const(cmax_grid_hi, cmax_grid_lo, 1);
        DS h0_ds = ds_const(cmax_grid_hi, cmax_grid_lo, 2);
        DS h_step_ds = ds_const(cmax_grid_hi, cmax_grid_lo, 3);
        float L0 = ds_value(L0_ds);
        float L1 = ds_value(L1_ds);
        float Jz_lookup = clamp(ds_value(Jz), L0, L1);
        DS L_idx_ds = ds_mul_float(
            ds_div(ds_sub(ds_make(Jz_lookup), L0_ds), ds_sub(L1_ds, L0_ds)),
            float(n_L - 1)
        );
        float L_idx = ds_value(L_idx_ds);
        int L_lo = clamp(int(floor(L_idx)), 0, n_L - 2);
        int L_hi = L_lo + 1;
        float L_frac = L_idx - float(L_lo);

        DS h_idx_ds = ds_div(ds_sub(ds_make(hz), h0_ds), h_step_ds);
        float h_idx = ds_value(h_idx_ds);
        float h_floor = floor(h_idx);
        int h_lo = int(h_floor) % n_h;
        if (h_lo < 0) {
            h_lo += n_h;
        }
        int h_hi = (h_lo + 1) % n_h;
        float h_frac = h_idx - h_floor;

        int c00 = L_lo * n_h + h_lo;
        int c01 = L_lo * n_h + h_hi;
        int c10 = L_hi * n_h + h_lo;
        int c11 = L_hi * n_h + h_hi;
        DS v00 = ds_make_pair(C_max_table[c00], C_max_table_lo[c00]);
        DS v01 = ds_make_pair(C_max_table[c01], C_max_table_lo[c01]);
        DS v10 = ds_make_pair(C_max_table[c10], C_max_table_lo[c10]);
        DS v11 = ds_make_pair(C_max_table[c11], C_max_table_lo[c11]);
        float inv_L_frac = 1.0f - L_frac;
        float inv_h_frac = 1.0f - h_frac;
        DS Cz_max_ds = ds_add(
            ds_add(
                ds_mul_float(ds_mul_float(v00, inv_L_frac), inv_h_frac),
                ds_mul_float(ds_mul_float(v01, inv_L_frac), h_frac)
            ),
            ds_add(
                ds_mul_float(ds_mul_float(v10, L_frac), inv_h_frac),
                ds_mul_float(ds_mul_float(v11, L_frac), h_frac)
            )
        );
        float Cz_max = ds_value(Cz_max_ds);
        float safe_Cz_max = max(Cz_max, 1.0e-9f);
        float d_norm = Cz / safe_Cz_max;
        float threshold = params[0];
        float limit = params[1];
        float power = params[7];
        float scale = limit - threshold;
        float x = max((d_norm - threshold) / scale, 0.0f);
        float y;
        if (x > 1.0f) {
            float inv_x = 1.0f / x;
            y = 1.0f / precise::pow(1.0f + precise::pow(inv_x, power), 1.0f / power);
        } else {
            y = x / precise::pow(1.0f + precise::pow(x, power), 1.0f / power);
        }
        float d_compressed = d_norm > threshold ? threshold + scale * y : d_norm;
        float Cz_new = d_compressed * safe_Cz_max;
        float chroma_scale = Cz > 1.0e-20f ? Cz_new / Cz : 0.0f;
        DS az_new = ds_mul_float(az, chroma_scale);
        DS bz_new = ds_mul_float(bz, chroma_scale);

        DS Jz_plus_D0 = ds_add(Jz, jz_D0);
        DS Iz_new = ds_div(
            Jz_plus_D0,
            ds_add(one_plus_jz_D, ds_mul(Jz_plus_D0, minus_jz_D))
        );

        DS Lp_new = ds_dot3_matrix(
            Iz_new, az_new, bz_new, jz_izazbz_to_lmsp_hi, jz_izazbz_to_lmsp_lo, 0
        );
        DS Mp_new = ds_dot3_matrix(
            Iz_new, az_new, bz_new, jz_izazbz_to_lmsp_hi, jz_izazbz_to_lmsp_lo, 1
        );
        DS Sp_new = ds_dot3_matrix(
            Iz_new, az_new, bz_new, jz_izazbz_to_lmsp_hi, jz_izazbz_to_lmsp_lo, 2
        );

        DS L_new = ds_pq_jz(Lp_new, jz_constants_hi, jz_constants_lo);
        DS M_new = ds_pq_jz(Mp_new, jz_constants_hi, jz_constants_lo);
        DS S_new = ds_pq_jz(Sp_new, jz_constants_hi, jz_constants_lo);

        DS Xp_new = ds_dot3_matrix(L_new, M_new, S_new, jz_lms_to_xyz_hi, jz_lms_to_xyz_lo, 0);
        DS Yp_new = ds_dot3_matrix(L_new, M_new, S_new, jz_lms_to_xyz_hi, jz_lms_to_xyz_lo, 1);
        DS Z_new = ds_dot3_matrix(L_new, M_new, S_new, jz_lms_to_xyz_hi, jz_lms_to_xyz_lo, 2);

        DS X_new = ds_div(ds_add(Xp_new, ds_mul(Z_new, jz_B_minus_one)), jz_B);
        DS Y_new = ds_div(ds_sub(Yp_new, ds_mul(X_new, one_minus_jz_G)), jz_G);
        X_new = ds_mul(X_new, inv_Y_w);
        Y_new = ds_mul(Y_new, inv_Y_w);
        Z_new = ds_mul(Z_new, inv_Y_w);

        DS out_r = ds_dot3_matrix(X_new, Y_new, Z_new, matrix_xyz_to_rgb_hi, matrix_xyz_to_rgb_lo, 0);
        DS out_g = ds_dot3_matrix(X_new, Y_new, Z_new, matrix_xyz_to_rgb_hi, matrix_xyz_to_rgb_lo, 1);
        DS out_b = ds_dot3_matrix(X_new, Y_new, Z_new, matrix_xyz_to_rgb_hi, matrix_xyz_to_rgb_lo, 2);

        out[base + 0] = finite_float(ds_value(out_r));
        out[base + 1] = finite_float(ds_value(out_g));
        out[base + 2] = finite_float(ds_value(out_b));
    """

    _JZAZBZ_CHROMA_MLX_KERNEL = mx.fast.metal_kernel(
        name="spektrafilm_jzazbz_chroma_ds",
        input_names=[
            "rgb",
            "matrix_rgb_to_xyz_hi",
            "matrix_rgb_to_xyz_lo",
            "matrix_xyz_to_rgb_hi",
            "matrix_xyz_to_rgb_lo",
            "L_grid",
            "h_grid",
            "C_max_table",
            "C_max_table_lo",
            "cmax_grid_hi",
            "cmax_grid_lo",
            "params",
            "jz_constants_hi",
            "jz_constants_lo",
            "jz_xyz_to_lms_hi",
            "jz_xyz_to_lms_lo",
            "jz_lmsp_to_izazbz_hi",
            "jz_lmsp_to_izazbz_lo",
            "jz_izazbz_to_lmsp_hi",
            "jz_izazbz_to_lmsp_lo",
            "jz_lms_to_xyz_hi",
            "jz_lms_to_xyz_lo",
        ],
        output_names=["out"],
        source=source,
        header=header,
    )
    return _JZAZBZ_CHROMA_MLX_KERNEL


def _compress_rgb_jzazbz_chroma_mlx_kernel(
    rgb,
    output_color_space: str,
    *,
    threshold: float,
    limit: float,
    power: float,
    lightness_compression: tuple[float, float, float] | None,
    backend,
):
    mx = backend.mx
    from spektrafilm.gpu.kernels.color import (
        precompute_rgb_to_xyz_matrix,
        precompute_xyz_to_rgb_matrix,
    )
    from spektrafilm.utils.gamut_compression import (
        _get_output_c_max_table,
        _jzazbz_white_Jz,
    )

    rgb = backend.asarray(rgb)
    orig_shape = tuple(int(dim) for dim in rgb.shape)
    rgb_flat = mx.reshape(rgb, (-1, 3))

    matrix_rgb_to_xyz_hi, matrix_rgb_to_xyz_lo = _split_float32_hi_lo(
        precompute_rgb_to_xyz_matrix(output_color_space)
    )
    matrix_xyz_to_rgb_hi, matrix_xyz_to_rgb_lo = _split_float32_hi_lo(
        precompute_xyz_to_rgb_matrix(output_color_space)
    )
    jz_constants_hi, jz_constants_lo = _split_float32_hi_lo(_JZAZBZ_DS_CONSTANTS)
    jz_xyz_to_lms_hi, jz_xyz_to_lms_lo = _split_float32_hi_lo(_JZAZBZ_XYZ_TO_LMS)
    jz_lmsp_to_izazbz_hi, jz_lmsp_to_izazbz_lo = _split_float32_hi_lo(
        _JZAZBZ_LMSP_TO_IZAZBZ
    )
    jz_izazbz_to_lmsp_hi, jz_izazbz_to_lmsp_lo = _split_float32_hi_lo(
        _JZAZBZ_IZAZBZ_TO_LMSP
    )
    jz_lms_to_xyz_hi, jz_lms_to_xyz_lo = _split_float32_hi_lo(_JZAZBZ_LMS_TO_XYZ)
    L_grid, h_grid, C_max_table = _get_output_c_max_table("jzazbz", output_color_space)
    c_max_table_hi, c_max_table_lo = _split_float32_hi_lo(C_max_table)
    cmax_grid_constants = np.asarray(
        [L_grid[0], L_grid[-1], h_grid[0], h_grid[1] - h_grid[0]],
        dtype=np.float64,
    )
    cmax_grid_hi, cmax_grid_lo = _split_float32_hi_lo(cmax_grid_constants)

    if lightness_compression is None:
        lt, ll, lp = 0.0, 1.0, 1.0
        L_white = 1.0
        use_lightness = 0.0
    else:
        lt, ll, lp = lightness_compression
        L_white = _jzazbz_white_Jz(output_color_space)
        use_lightness = 1.0
    params = np.asarray(
        [threshold, limit, lt, ll, lp, L_white, use_lightness, power],
        dtype=np.float32,
    )

    kernel = _get_jzazbz_chroma_mlx_kernel(mx)
    outputs = kernel(
        inputs=[
            rgb_flat,
            backend.asarray(matrix_rgb_to_xyz_hi),
            backend.asarray(matrix_rgb_to_xyz_lo),
            backend.asarray(matrix_xyz_to_rgb_hi),
            backend.asarray(matrix_xyz_to_rgb_lo),
            backend.asarray(np.asarray(L_grid, dtype=np.float32)),
            backend.asarray(np.asarray(h_grid, dtype=np.float32)),
            backend.asarray(c_max_table_hi),
            backend.asarray(c_max_table_lo),
            backend.asarray(cmax_grid_hi),
            backend.asarray(cmax_grid_lo),
            backend.asarray(params),
            backend.asarray(jz_constants_hi),
            backend.asarray(jz_constants_lo),
            backend.asarray(jz_xyz_to_lms_hi),
            backend.asarray(jz_xyz_to_lms_lo),
            backend.asarray(jz_lmsp_to_izazbz_hi),
            backend.asarray(jz_lmsp_to_izazbz_lo),
            backend.asarray(jz_izazbz_to_lmsp_hi),
            backend.asarray(jz_izazbz_to_lmsp_lo),
            backend.asarray(jz_lms_to_xyz_hi),
            backend.asarray(jz_lms_to_xyz_lo),
        ],
        grid=(int(rgb_flat.shape[0]), 1, 1),
        threadgroup=(256, 1, 1),
        output_shapes=[rgb_flat.shape],
        output_dtypes=[mx.float32],
    )
    return mx.reshape(outputs[0], orig_shape)


# ---------------------------------------------------------------------------
# OkLab forward / inverse  (backend-portable)
# ---------------------------------------------------------------------------

def _xyz_to_oklab_backend(xyz, backend):
    """XYZ → OkLab via MLX/CuPy matrix ops.

    ``Lab = M2 @ cbrt(M1 @ XYZ)``  (per-pixel, batched via matmul).
    """
    mx = backend.mx
    M1 = backend.asarray(_OKLAB_M1)
    M2 = backend.asarray(_OKLAB_M2)

    # xyz shape: (..., 3).  matmul with (3, 3).T → (..., 3)
    lms = mx.matmul(xyz, mx.transpose(M1))
    # Signed cube root: preserve sign for negative XYZ edge cases
    lms_abs = mx.abs(lms)
    lms_cbrt = mx.where(
        lms >= 0,
        mx.power(lms_abs + 1e-30, 1.0 / 3.0),
        -mx.power(lms_abs + 1e-30, 1.0 / 3.0),
    )
    lab = mx.matmul(lms_cbrt, mx.transpose(M2))
    return lab


def _oklab_to_xyz_backend(lab, backend):
    """OkLab → XYZ via MLX/CuPy matrix ops.

    ``XYZ = M1_inv @ (M2_inv @ Lab)^3``
    """
    mx = backend.mx
    M1_inv = backend.asarray(_OKLAB_M1_INV)
    M2_inv = backend.asarray(_OKLAB_M2_INV)

    lms_cbrt = mx.matmul(lab, mx.transpose(M2_inv))
    lms = lms_cbrt * lms_cbrt * lms_cbrt   # cube
    xyz = mx.matmul(lms, mx.transpose(M1_inv))
    return xyz


def _safe_div_backend(numerator, denominator, backend, eps: float = 1e-12):
    mx = backend.mx
    eps_with_sign = mx.where(denominator < 0.0, -eps, eps)
    denom = mx.where(mx.abs(denominator) < eps, eps_with_sign, denominator)
    return numerator / denom


def _signed_power_backend(x, exponent: float, backend):
    mx = backend.mx
    magnitude = mx.power(mx.abs(x), exponent)
    return mx.where(x < 0, -magnitude, magnitude)


def _hypot_backend(a, b, backend):
    """Overflow-stable ``sqrt(a*a + b*b)`` on float32 backends."""
    mx = backend.mx
    scale = mx.maximum(mx.abs(a), mx.abs(b))
    safe_scale = mx.where(scale > 0.0, scale, 1.0)
    ar = a / safe_scale
    br = b / safe_scale
    return mx.where(
        scale > 0.0,
        scale * mx.sqrt(ar * ar + br * br),
        0.0,
    )


def _eotf_inverse_st2084_jz_backend(C, backend):
    Y_p = _signed_power_backend(C / 10000.0, _ST2084_M1, backend)
    ratio = (_ST2084_C1 + _ST2084_C2 * Y_p) / (_ST2084_C3 * Y_p + 1.0)
    return _signed_power_backend(ratio, _ST2084_M2_JZ, backend)


def _eotf_st2084_jz_backend(N, backend):
    mx = backend.mx
    V_p = _signed_power_backend(N, 1.0 / _ST2084_M2_JZ, backend)
    n = mx.maximum(0.0, V_p - _ST2084_C1)
    ratio = _safe_div_backend(n, _ST2084_C2 - _ST2084_C3 * V_p, backend)
    L = _signed_power_backend(ratio, 1.0 / _ST2084_M1, backend)
    return 10000.0 * L


def _xyz_to_jzazbz_backend(xyz_abs, backend):
    mx = backend.mx
    X = xyz_abs[..., 0]
    Y = xyz_abs[..., 1]
    Z = xyz_abs[..., 2]
    X_p = _JZAZBZ_B * X - (_JZAZBZ_B - 1.0) * Z
    Y_p = _JZAZBZ_G * Y - (_JZAZBZ_G - 1.0) * X
    xyz_p = mx.stack([X_p, Y_p, Z], axis=-1)
    lms = mx.matmul(xyz_p, mx.transpose(backend.asarray(_JZAZBZ_XYZ_TO_LMS)))
    lms_p = _eotf_inverse_st2084_jz_backend(lms, backend)
    izazbz = mx.matmul(lms_p, mx.transpose(backend.asarray(_JZAZBZ_LMSP_TO_IZAZBZ)))
    I_z = izazbz[..., 0]
    J_z = ((1.0 + _JZAZBZ_D) * I_z) / (1.0 + _JZAZBZ_D * I_z) - _JZAZBZ_D0
    return mx.stack([J_z, izazbz[..., 1], izazbz[..., 2]], axis=-1)


def _jzazbz_to_xyz_backend(jab, backend):
    mx = backend.mx
    J_z = jab[..., 0]
    I_z = (J_z + _JZAZBZ_D0) / (
        1.0 + _JZAZBZ_D - _JZAZBZ_D * (J_z + _JZAZBZ_D0)
    )
    izazbz = mx.stack([I_z, jab[..., 1], jab[..., 2]], axis=-1)
    lms_p = mx.matmul(izazbz, mx.transpose(backend.asarray(_JZAZBZ_IZAZBZ_TO_LMSP)))
    lms = _eotf_st2084_jz_backend(lms_p, backend)
    xyz_p = mx.matmul(lms, mx.transpose(backend.asarray(_JZAZBZ_LMS_TO_XYZ)))
    X_p = xyz_p[..., 0]
    Y_p = xyz_p[..., 1]
    Z = xyz_p[..., 2]
    X = (X_p + (_JZAZBZ_B - 1.0) * Z) / _JZAZBZ_B
    Y = (Y_p + (_JZAZBZ_G - 1.0) * X) / _JZAZBZ_G
    return mx.stack([X, Y, Z], axis=-1)


def _luminance_level_adaptation_factor(L_A: float) -> float:
    k = 1.0 / (5.0 * L_A + 1.0)
    k4 = k ** 4
    return float(0.2 * k4 * (5.0 * L_A) + 0.1 * (1.0 - k4) ** 2 * (5.0 * L_A) ** (1.0 / 3.0))


@lru_cache(maxsize=16)
def _cam16ucs_precomputed(output_color_space: str) -> dict[str, Any]:
    from spektrafilm.utils.gamut_compression import _output_cs_whitepoint_xyz

    xyz_w = np.asarray(_output_cs_whitepoint_xyz(output_color_space), dtype=np.float64)
    xyz_w_ref = xyz_w * 100.0
    rgb_w = _CAM16_MATRIX_16 @ xyz_w_ref
    Y_w = float(xyz_w_ref[1])
    D = _CAM16UCS_SURROUND_F * (1.0 - (1.0 / 3.6) * np.exp((-_CAM16UCS_L_A - 42.0) / 92.0))
    D = float(np.clip(D, 0.0, 1.0))
    n = _CAM16UCS_Y_B / Y_w
    F_L = _luminance_level_adaptation_factor(_CAM16UCS_L_A)
    N_bb = 0.725 * (1.0 / n) ** 0.2
    N_cb = N_bb
    z = 1.48 + np.sqrt(n)
    D_RGB = D * Y_w / rgb_w + 1.0 - D
    rgb_wc = D_RGB * rgb_w
    rgb_aw = _cam16_post_adaptation_forward_np(rgb_wc, F_L)
    A_w = (2.0 * rgb_aw[0] + rgb_aw[1] + 0.05 * rgb_aw[2] - 0.305) * N_bb
    return {
        "xyz_w": xyz_w,
        "rgb_w": rgb_w,
        "D_RGB": D_RGB.astype(np.float64),
        "n": float(n),
        "F_L": float(F_L),
        "N_bb": float(N_bb),
        "N_cb": float(N_cb),
        "z": float(z),
        "A_w": float(A_w),
    }


def _cam16_post_adaptation_forward_np(rgb: np.ndarray, F_L: float) -> np.ndarray:
    F_L_RGB = np.sign(rgb) * np.abs(F_L * rgb / 100.0) ** 0.42
    return (400.0 * F_L_RGB) / (27.13 + np.abs(F_L_RGB)) + 0.1


def _cam16_post_adaptation_forward_backend(rgb, F_L: float, backend):
    mx = backend.mx
    F_L_RGB = _signed_power_backend(F_L * rgb / 100.0, 0.42, backend)
    return (400.0 * F_L_RGB) / (27.13 + mx.abs(F_L_RGB)) + 0.1


def _cam16_post_adaptation_inverse_backend(rgb_a, F_L: float, backend):
    mx = backend.mx
    delta = rgb_a - 0.1
    ratio = (27.13 * mx.abs(delta)) / (400.0 - mx.abs(delta))
    sign = mx.where(delta < 0.0, -1.0, 1.0)
    sign = mx.where(delta == 0.0, 0.0, sign)
    return sign * 100.0 / F_L * _signed_power_backend(ratio, 1.0 / 0.42, backend)


def _xyz_to_cam16ucs_backend(xyz, output_color_space: str, backend):
    mx = backend.mx
    c = _cam16ucs_precomputed(output_color_space)
    xyz_ref = xyz * 100.0
    rgb = mx.matmul(xyz_ref, mx.transpose(backend.asarray(_CAM16_MATRIX_16)))
    rgb_c = rgb * backend.asarray(c["D_RGB"])
    rgb_a = _cam16_post_adaptation_forward_backend(rgb_c, c["F_L"], backend)

    R = rgb_a[..., 0]
    G = rgb_a[..., 1]
    B = rgb_a[..., 2]
    a = R - 12.0 * G / 11.0 + B / 11.0
    b = (R + G - 2.0 * B) / 9.0
    h = mx.arctan2(b, a)
    e_t = 0.25 * (mx.cos(2.0 + h) + 3.8)
    A = (2.0 * R + G + 0.05 * B - 0.305) * c["N_bb"]
    J = 100.0 * _signed_power_backend(
        _safe_div_backend(A, c["A_w"], backend),
        _CAM16UCS_SURROUND_C * c["z"],
        backend,
    )
    denom = R + G + 21.0 * B / 20.0
    t = ((50000.0 / 13.0) * _CAM16UCS_SURROUND_N_C * c["N_cb"]) * _safe_div_backend(
        e_t * mx.sqrt(a * a + b * b),
        denom,
        backend,
    )
    C = (
        _signed_power_backend(t, 0.9, backend)
        * mx.sqrt(mx.maximum(J, 0.0) / 100.0)
        * (1.64 - 0.29 ** c["n"]) ** 0.73
    )
    M = C * c["F_L"] ** 0.25

    J_p = ((1.0 + 100.0 * _CAM16UCS_C1) * J) / (1.0 + _CAM16UCS_C1 * J)
    M_p = (1.0 / _CAM16UCS_C2) * mx.log(1.0 + _CAM16UCS_C2 * M)
    a_p = M_p * mx.cos(h)
    b_p = M_p * mx.sin(h)
    return mx.stack([J_p, a_p, b_p], axis=-1)


def _cam16ucs_to_xyz_backend(jab, output_color_space: str, backend):
    mx = backend.mx
    c = _cam16ucs_precomputed(output_color_space)
    J_p = jab[..., 0]
    a_p = jab[..., 1]
    b_p = jab[..., 2]

    J = -J_p / (_CAM16UCS_C1 * J_p - 1.0 - 100.0 * _CAM16UCS_C1)
    M_p = mx.sqrt(a_p * a_p + b_p * b_p)
    h = mx.arctan2(b_p, a_p)
    M = (mx.exp(_CAM16UCS_C2 * M_p) - 1.0) / _CAM16UCS_C2
    C = M / c["F_L"] ** 0.25
    J_prime = mx.maximum(J, np.finfo(np.float64).eps)
    t = _signed_power_backend(
        C / (mx.sqrt(J_prime / 100.0) * (1.64 - 0.29 ** c["n"]) ** 0.73),
        1.0 / 0.9,
        backend,
    )
    e_t = 0.25 * (mx.cos(2.0 + h) + 3.8)
    A = c["A_w"] * _signed_power_backend(J / 100.0, 1.0 / (_CAM16UCS_SURROUND_C * c["z"]), backend)
    P_1 = _safe_div_backend((50000.0 / 13.0) * _CAM16UCS_SURROUND_N_C * c["N_cb"] * e_t, t, backend)
    P_2 = A / c["N_bb"] + 0.305
    P_3 = 21.0 / 20.0

    sin_h = mx.sin(h)
    cos_h = mx.cos(h)
    cos_over_sin = _safe_div_backend(cos_h, sin_h, backend)
    sin_over_cos = _safe_div_backend(sin_h, cos_h, backend)
    P_4 = _safe_div_backend(P_1, sin_h, backend)
    P_5 = _safe_div_backend(P_1, cos_h, backend)
    n = P_2 * (2.0 + P_3) * (460.0 / 1403.0)
    abs_sin_ge_cos = mx.abs(sin_h) >= mx.abs(cos_h)
    b_from_sin = n / (
        P_4
        + (2.0 + P_3) * (220.0 / 1403.0) * cos_over_sin
        - (27.0 / 1403.0)
        + P_3 * (6300.0 / 1403.0)
    )
    a_from_sin = b_from_sin * cos_over_sin
    a_from_cos = n / (
        P_5
        + (2.0 + P_3) * (220.0 / 1403.0)
        - ((27.0 / 1403.0) - P_3 * (6300.0 / 1403.0)) * sin_over_cos
    )
    b_from_cos = a_from_cos * sin_over_cos
    a = mx.where(abs_sin_ge_cos, a_from_sin, a_from_cos)
    b = mx.where(abs_sin_ge_cos, b_from_sin, b_from_cos)
    zero_t = t == 0
    a = mx.where(zero_t, 0.0, a)
    b = mx.where(zero_t, 0.0, b)

    rgb_a = (
        mx.matmul(
            mx.stack([P_2, a, b], axis=-1),
            mx.transpose(backend.asarray(np.array([
                [460.0, 451.0, 288.0],
                [460.0, -891.0, -261.0],
                [460.0, -220.0, -6300.0],
            ], dtype=np.float64))),
        )
        / 1403.0
    )
    rgb_c = _cam16_post_adaptation_inverse_backend(rgb_a, c["F_L"], backend)
    rgb = rgb_c / backend.asarray(c["D_RGB"])
    xyz_ref = mx.matmul(rgb, mx.transpose(backend.asarray(_CAM16_MATRIX_16_INV)))
    return xyz_ref / 100.0


# ---------------------------------------------------------------------------
# RGB ↔ XYZ  (using pre-computed matrices, no colour dependency)
# ---------------------------------------------------------------------------

def _rgb_to_xyz_backend(rgb, matrix_rgb_to_xyz, backend):
    """Linear RGB → XYZ:  ``XYZ = RGB @ M.T``."""
    return backend.mx.matmul(rgb, backend.mx.transpose(matrix_rgb_to_xyz))


def _xyz_to_rgb_backend(xyz, matrix_xyz_to_rgb, backend):
    """XYZ → Linear RGB:  ``RGB = XYZ @ M.T``."""
    return backend.mx.matmul(xyz, backend.mx.transpose(matrix_xyz_to_rgb))


# ---------------------------------------------------------------------------
# Bilinear C_max(L, h) lookup  (backend-portable)
# ---------------------------------------------------------------------------

def _c_max_lookup_backend(L, h, L_grid, h_grid, C_max_table, backend):
    """Bilinear interpolation of C_max(L, h) on the backend.

    Mirrors ``gamut_compression._c_max_lookup`` but with MLX tensors.
    The C_max_table, L_grid, h_grid are pre-computed numpy arrays from
    the CPU-side boundary builder and are transferred to backend once.
    """
    mx = backend.mx

    # Convert grid metadata to backend arrays (these are tiny, cached upstream)
    L_grid_b = backend.asarray(L_grid)
    h_grid_b = backend.asarray(h_grid)
    C_max_b = backend.asarray(C_max_table)

    n_L = L_grid.shape[0]
    n_h = h_grid.shape[0]

    # Clamp L to grid range
    L_clamped = mx.clip(L, float(L_grid[0]), float(L_grid[-1]))

    # Compute fractional indices for L dimension
    L_range = float(L_grid[-1] - L_grid[0])
    L_idx = (L_clamped - float(L_grid[0])) / L_range * (n_L - 1)
    L_lo = mx.clip(mx.floor(L_idx).astype(mx.int32), 0, n_L - 2)
    L_hi = L_lo + 1
    L_frac = L_idx - L_lo.astype(mx.float32)

    # Compute fractional indices for h dimension (periodic)
    h_step = float(h_grid[1] - h_grid[0])
    h_idx = (h - float(h_grid[0])) / h_step
    h_lo = mx.floor(h_idx).astype(mx.int32) % n_h
    h_hi = (h_lo + 1) % n_h
    h_frac = h_idx - mx.floor(h_idx)

    # Flatten indices for gather
    orig_shape = L.shape
    L_lo_f = mx.reshape(L_lo, (-1,))
    L_hi_f = mx.reshape(L_hi, (-1,))
    h_lo_f = mx.reshape(h_lo, (-1,))
    h_hi_f = mx.reshape(h_hi, (-1,))

    # Gather the four corner values
    # C_max_table shape is (n_L, n_h)
    v00 = C_max_b[L_lo_f, h_lo_f]
    v01 = C_max_b[L_lo_f, h_hi_f]
    v10 = C_max_b[L_hi_f, h_lo_f]
    v11 = C_max_b[L_hi_f, h_hi_f]

    v00 = mx.reshape(v00, orig_shape)
    v01 = mx.reshape(v01, orig_shape)
    v10 = mx.reshape(v10, orig_shape)
    v11 = mx.reshape(v11, orig_shape)

    # Bilinear interpolation
    result = (
        v00 * (1 - L_frac) * (1 - h_frac)
        + v01 * (1 - L_frac) * h_frac
        + v10 * L_frac * (1 - h_frac)
        + v11 * L_frac * h_frac
    )
    return result


# ---------------------------------------------------------------------------
# Reinhard knee  (backend-portable)
# ---------------------------------------------------------------------------

def _reinhard_knee_backend(d, *, threshold, limit, power, backend):
    """Reinhard knee on the backend, matching ``gamut_compression.reinhard_knee``."""
    mx = backend.mx
    scale = limit - threshold
    x = (d - threshold) / scale
    # Clamp x to non-negative for the power; identity below threshold.
    # For very large x, the direct x / (1 + x**p)**(1/p) form overflows
    # in float32 even though the mathematical limit is finite.  The
    # reciprocal form is algebraically identical for x > 1:
    #     x / (1 + x**p)**(1/p) == 1 / (1 + x**-p)**(1/p)
    x_safe = mx.maximum(x, 0.0)
    x_direct = mx.minimum(x_safe, 1.0)
    y_direct = x_direct / mx.power(1.0 + mx.power(x_direct, power), 1.0 / power)
    inv_x = 1.0 / mx.maximum(x_safe, 1.0)
    y_recip = 1.0 / mx.power(1.0 + mx.power(inv_x, power), 1.0 / power)
    y = mx.where(x_safe > 1.0, y_recip, y_direct)
    compressed = threshold + scale * y
    # Identity below threshold
    return mx.where(d > threshold, compressed, d)


def _compress_lightness_backend(L, *, params, L_white, backend):
    """One-sided soft compression on perceptual lightness, backend version."""
    threshold, limit, power = params
    L_norm = L / L_white
    L_norm = _reinhard_knee_backend(
        L_norm, threshold=threshold, limit=limit, power=power, backend=backend,
    )
    return L_norm * L_white


# ---------------------------------------------------------------------------
# Oklrab Lr remap  (backend-portable)
# ---------------------------------------------------------------------------

_OKLRAB_K1 = 0.206
_OKLRAB_K2 = 0.03
_OKLRAB_K3 = (1.0 + _OKLRAB_K1) / (1.0 + _OKLRAB_K2)


def _oklab_L_to_oklrab_Lr_backend(L, backend):
    """Forward Lr from OkLab L (Ottosson 2023), backend version."""
    mx = backend.mx
    k1, k2, k3 = _OKLRAB_K1, _OKLRAB_K2, _OKLRAB_K3
    t = k3 * L - k1
    return 0.5 * (t + mx.sqrt(t * t + 4.0 * k2 * k3 * L))


# ---------------------------------------------------------------------------
# compress_rgb_aces_rgc_backend
# ---------------------------------------------------------------------------

def compress_rgb_aces_rgc_backend(rgb, *, threshold, limit, power, backend):
    """ACES RGC v1.3 on the backend. Pure element-wise arithmetic."""
    mx = backend.mx
    rgb = backend.asarray(rgb)

    ach = mx.max(rgb, axis=-1, keepdims=True)
    safe_ach = mx.where(ach > 1e-12, ach, 1.0)

    d = (ach - rgb) / safe_ach
    d_compressed = _reinhard_knee_backend(
        d, threshold=threshold, limit=limit, power=power, backend=backend,
    )
    rgb_compressed = ach * (1.0 - d_compressed)
    return mx.where(ach > 1e-12, rgb_compressed, rgb)


# ---------------------------------------------------------------------------
# compress_rgb_oklch_chroma_backend
# ---------------------------------------------------------------------------

def compress_rgb_oklch_chroma_backend(
    rgb,
    output_color_space: str,
    *,
    threshold: float,
    limit: float,
    power: float,
    lightness_compression: tuple[float, float, float] | None = None,
    backend,
):
    """OkLch chroma reduction on the backend.

    Mirrors ``gamut_compression.compress_rgb_oklch_chroma`` but keeps all
    per-pixel computation on MLX.  The C_max table is built on CPU (cached)
    and transferred to the backend once.
    """
    mx = backend.mx
    rgb = backend.asarray(rgb)

    # Pre-computed matrices (CPU, cached by caller or here)
    from spektrafilm.gpu.kernels.color import (
        precompute_rgb_to_xyz_matrix,
        precompute_xyz_to_rgb_matrix,
    )
    M_rgb_to_xyz = backend.asarray(precompute_rgb_to_xyz_matrix(output_color_space))
    M_xyz_to_rgb = backend.asarray(precompute_xyz_to_rgb_matrix(output_color_space))

    # RGB → XYZ → OkLab
    xyz = _rgb_to_xyz_backend(rgb, M_rgb_to_xyz, backend)
    lab = _xyz_to_oklab_backend(xyz, backend)
    L = lab[..., 0]
    a = lab[..., 1]
    b = lab[..., 2]

    # Optional lightness compression (OkLab white = L=1.0)
    if lightness_compression is not None:
        L = _compress_lightness_backend(
            L, params=lightness_compression, L_white=1.0, backend=backend,
        )

    # Polar coordinates
    C = _hypot_backend(a, b, backend)
    h = mx.arctan2(b, a)

    # C_max lookup (table from CPU cache)
    from spektrafilm.utils.gamut_compression import _get_output_c_max_table
    c_max_data = _get_output_c_max_table("oklch", output_color_space)
    C_max = _c_max_lookup_backend(L, h, *c_max_data, backend)
    safe_C_max = mx.maximum(C_max, 1e-9)

    # Reinhard knee on normalized chroma
    d_norm = C / safe_C_max
    d_compressed = _reinhard_knee_backend(
        d_norm, threshold=threshold, limit=limit, power=power, backend=backend,
    )
    C_new = d_compressed * safe_C_max

    # Polar → OkLab → XYZ → RGB
    a_new = C_new * mx.cos(h)
    b_new = C_new * mx.sin(h)
    lab_new = mx.stack([L, a_new, b_new], axis=-1)
    xyz_new = _oklab_to_xyz_backend(lab_new, backend)
    rgb_new = _xyz_to_rgb_backend(xyz_new, M_xyz_to_rgb, backend)
    return rgb_new


# ---------------------------------------------------------------------------
# compress_rgb_oklrab_chroma_backend
# ---------------------------------------------------------------------------

def compress_rgb_oklrab_chroma_backend(
    rgb,
    output_color_space: str,
    *,
    threshold: float,
    limit: float,
    power: float,
    lightness_compression: tuple[float, float, float] | None = None,
    backend,
):
    """Oklrab chroma reduction on the backend.

    Same as oklch but C_max is indexed by rebased lightness Lr.
    """
    mx = backend.mx
    rgb = backend.asarray(rgb)

    from spektrafilm.gpu.kernels.color import (
        precompute_rgb_to_xyz_matrix,
        precompute_xyz_to_rgb_matrix,
    )
    M_rgb_to_xyz = backend.asarray(precompute_rgb_to_xyz_matrix(output_color_space))
    M_xyz_to_rgb = backend.asarray(precompute_xyz_to_rgb_matrix(output_color_space))

    xyz = _rgb_to_xyz_backend(rgb, M_rgb_to_xyz, backend)
    lab = _xyz_to_oklab_backend(xyz, backend)
    L = lab[..., 0]
    a = lab[..., 1]
    b = lab[..., 2]

    if lightness_compression is not None:
        L = _compress_lightness_backend(
            L, params=lightness_compression, L_white=1.0, backend=backend,
        )

    Lr = _oklab_L_to_oklrab_Lr_backend(L, backend)
    C = _hypot_backend(a, b, backend)
    h = mx.arctan2(b, a)

    from spektrafilm.utils.gamut_compression import _get_output_c_max_table
    c_max_data = _get_output_c_max_table("oklrab", output_color_space)
    C_max = _c_max_lookup_backend(Lr, h, *c_max_data, backend)
    safe_C_max = mx.maximum(C_max, 1e-9)

    d_norm = C / safe_C_max
    d_compressed = _reinhard_knee_backend(
        d_norm, threshold=threshold, limit=limit, power=power, backend=backend,
    )
    C_new = d_compressed * safe_C_max

    a_new = C_new * mx.cos(h)
    b_new = C_new * mx.sin(h)
    lab_new = mx.stack([L, a_new, b_new], axis=-1)
    xyz_new = _oklab_to_xyz_backend(lab_new, backend)
    rgb_new = _xyz_to_rgb_backend(xyz_new, M_xyz_to_rgb, backend)
    return rgb_new


# ---------------------------------------------------------------------------
# compress_rgb_jzazbz_chroma_backend
# ---------------------------------------------------------------------------

def compress_rgb_jzazbz_chroma_backend(
    rgb,
    output_color_space: str,
    *,
    threshold: float,
    limit: float,
    power: float,
    lightness_compression: tuple[float, float, float] | None = None,
    backend,
):
    """JzCzhz chroma reduction on the backend."""
    if _backend_supports_mlx_custom_kernels(backend):
        return _compress_rgb_jzazbz_chroma_mlx_kernel(
            rgb,
            output_color_space,
            threshold=threshold,
            limit=limit,
            power=power,
            lightness_compression=lightness_compression,
            backend=backend,
        )

    mx = backend.mx
    rgb = backend.asarray(rgb)

    from spektrafilm.gpu.kernels.color import (
        precompute_rgb_to_xyz_matrix,
        precompute_xyz_to_rgb_matrix,
    )
    M_rgb_to_xyz = backend.asarray(precompute_rgb_to_xyz_matrix(output_color_space))
    M_xyz_to_rgb = backend.asarray(precompute_xyz_to_rgb_matrix(output_color_space))

    xyz = _rgb_to_xyz_backend(rgb, M_rgb_to_xyz, backend)
    jab = _xyz_to_jzazbz_backend(xyz * _JZAZBZ_Y_W_CDM2, backend)
    Jz = jab[..., 0]
    az = jab[..., 1]
    bz = jab[..., 2]

    if lightness_compression is not None:
        from spektrafilm.utils.gamut_compression import _jzazbz_white_Jz

        Jz = _compress_lightness_backend(
            Jz,
            params=lightness_compression,
            L_white=_jzazbz_white_Jz(output_color_space),
            backend=backend,
        )

    Cz = _hypot_backend(az, bz, backend)
    hz = mx.arctan2(bz, az)

    from spektrafilm.utils.gamut_compression import _get_output_c_max_table

    c_max_data = _get_output_c_max_table("jzazbz", output_color_space)
    Cz_max = _c_max_lookup_backend(Jz, hz, *c_max_data, backend)
    safe_Cz_max = mx.maximum(Cz_max, 1e-9)
    d_norm = Cz / safe_Cz_max
    d_compressed = _reinhard_knee_backend(
        d_norm, threshold=threshold, limit=limit, power=power, backend=backend,
    )
    Cz_new = d_compressed * safe_Cz_max

    az_new = Cz_new * mx.cos(hz)
    bz_new = Cz_new * mx.sin(hz)
    jab_new = mx.stack([Jz, az_new, bz_new], axis=-1)
    xyz_new = _jzazbz_to_xyz_backend(jab_new, backend) / _JZAZBZ_Y_W_CDM2
    rgb_new = _xyz_to_rgb_backend(xyz_new, M_xyz_to_rgb, backend)
    return backend.nan_to_num(rgb_new)


# ---------------------------------------------------------------------------
# compress_rgb_cam16ucs_chroma_backend
# ---------------------------------------------------------------------------

def compress_rgb_cam16ucs_chroma_backend(
    rgb,
    output_color_space: str,
    *,
    threshold: float,
    limit: float,
    power: float,
    lightness_compression: tuple[float, float, float] | None = None,
    backend,
):
    """CAM16-UCS chroma reduction on the backend."""
    mx = backend.mx
    rgb = backend.asarray(rgb)

    from spektrafilm.gpu.kernels.color import (
        precompute_rgb_to_xyz_matrix,
        precompute_xyz_to_rgb_matrix,
    )
    M_rgb_to_xyz = backend.asarray(precompute_rgb_to_xyz_matrix(output_color_space))
    M_xyz_to_rgb = backend.asarray(precompute_xyz_to_rgb_matrix(output_color_space))

    xyz = _rgb_to_xyz_backend(rgb, M_rgb_to_xyz, backend)
    jab = _xyz_to_cam16ucs_backend(xyz, output_color_space, backend)
    Jp = jab[..., 0]
    ap = jab[..., 1]
    bp = jab[..., 2]

    if lightness_compression is not None:
        from spektrafilm.utils.gamut_compression import _cam16ucs_white_Jp

        Jp = _compress_lightness_backend(
            Jp,
            params=lightness_compression,
            L_white=_cam16ucs_white_Jp(output_color_space),
            backend=backend,
        )

    Cp = _hypot_backend(ap, bp, backend)
    hp = mx.arctan2(bp, ap)

    from spektrafilm.utils.gamut_compression import _get_output_c_max_table

    c_max_data = _get_output_c_max_table("cam16ucs", output_color_space)
    Cp_max = _c_max_lookup_backend(Jp, hp, *c_max_data, backend)
    safe_Cp_max = mx.maximum(Cp_max, 1e-9)
    d_norm = Cp / safe_Cp_max
    d_compressed = _reinhard_knee_backend(
        d_norm, threshold=threshold, limit=limit, power=power, backend=backend,
    )
    Cp_new = d_compressed * safe_Cp_max

    ap_new = Cp_new * mx.cos(hp)
    bp_new = Cp_new * mx.sin(hp)
    jab_new = mx.stack([Jp, ap_new, bp_new], axis=-1)
    xyz_new = _cam16ucs_to_xyz_backend(jab_new, output_color_space, backend)
    rgb_new = _xyz_to_rgb_backend(xyz_new, M_xyz_to_rgb, backend)
    return backend.nan_to_num(rgb_new)


# ---------------------------------------------------------------------------
# Top-level dispatcher
# ---------------------------------------------------------------------------

def compress_rgb_backend(
    rgb: Any,
    spec,
    *,
    output_color_space: str | None = None,
    backend=None,
) -> Any:
    """Backend-aware output gamut compression.

    When *backend* supports GPU, runs the compression entirely on the
    backend (MLX / CuPy).  Otherwise falls back to the CPU implementation
    in ``spektrafilm.utils.gamut_compression.compress_rgb``.

    Parameters
    ----------
    rgb : array
        Linear RGB in the output color space, shape ``(..., 3)``.
    spec : OutputGamutCompressSpec
        Compression configuration.
    output_color_space : str or None
        Required for perceptual algorithms (oklch, oklrab, etc.).
    backend : ArrayBackend or None
        GPU backend.  ``None`` falls back to CPU.
    """
    if not _backend_supports_gpu(backend):
        from spektrafilm.utils.gamut_compression import compress_rgb
        return compress_rgb(rgb, spec, output_color_space=output_color_space)

    if spec.algorithm == "off":
        return backend.asarray(rgb)

    threshold, limit, power = spec.knee

    if spec.algorithm == "aces_rgc":
        return compress_rgb_aces_rgc_backend(
            rgb, threshold=threshold, limit=limit, power=power, backend=backend,
        )

    if spec.algorithm == "oklch":
        if output_color_space is None:
            raise ValueError("output_color_space is required for oklch")
        return compress_rgb_oklch_chroma_backend(
            rgb, output_color_space,
            threshold=threshold, limit=limit, power=power,
            lightness_compression=spec.lightness_compression,
            backend=backend,
        )

    if spec.algorithm == "oklrab":
        if output_color_space is None:
            raise ValueError("output_color_space is required for oklrab")
        return compress_rgb_oklrab_chroma_backend(
            rgb, output_color_space,
            threshold=threshold, limit=limit, power=power,
            lightness_compression=spec.lightness_compression,
            backend=backend,
        )

    if spec.algorithm == "jzazbz":
        if output_color_space is None:
            raise ValueError("output_color_space is required for jzazbz")
        return compress_rgb_jzazbz_chroma_backend(
            rgb, output_color_space,
            threshold=threshold, limit=limit, power=power,
            lightness_compression=spec.lightness_compression,
            backend=backend,
        )

    if spec.algorithm == "cam16ucs":
        if output_color_space is None:
            raise ValueError("output_color_space is required for cam16ucs")
        return compress_rgb_cam16ucs_chroma_backend(
            rgb, output_color_space,
            threshold=threshold, limit=limit, power=power,
            lightness_compression=spec.lightness_compression,
            backend=backend,
        )

    raise ValueError(f"Unsupported output gamut compression algorithm: {spec.algorithm!r}")
