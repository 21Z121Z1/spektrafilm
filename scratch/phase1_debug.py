"""Phase 1 deep dive: compare Metal kernel intermediates to CPU and float32 DS sim."""
from __future__ import annotations

import math

import numpy as np
import colour
from colour.models import eotf_ST2084

from spektrafilm.gpu.backend import select_backend
from spektrafilm.gpu.kernels.gamut_compress import (
    _JZAZBZ_Y_W_CDM2,
    _debug_jzazbz_mlx,
)


def f32(x):
    return np.float32(x)


def two_sum(a, b):
    a, b = f32(a), f32(b)
    s = f32(a + b)
    bb = f32(s - a)
    e = f32(f32(a - f32(s - bb)) + f32(b - bb))
    return s, e


def quick_two_sum(a, b):
    a, b = f32(a), f32(b)
    s = f32(a + b)
    return s, f32(b - f32(s - a))


def ds_add(a, b):
    s, e = two_sum(a[0], b[0])
    return quick_two_sum(s, f32(f32(e + a[1]) + b[1]))


def ds_sub(a, b):
    s, e = two_sum(a[0], -b[0])
    return quick_two_sum(s, f32(f32(e + a[1]) - b[1]))


def ds_mul(a, b):
    p = f32(a[0] * b[0])
    e = f32(math.fma(f32(a[0]), f32(b[0]), f32(-p))
             + f32(a[0] * b[1]) + f32(a[1] * b[0]))
    return quick_two_sum(p, e)


def ds_mul_float(a, b):
    b = f32(b)
    p = f32(a[0] * b)
    e = f32(math.fma(f32(a[0]), b, f32(-p)) + f32(a[1] * b))
    return quick_two_sum(p, e)


def ds_div(a, b):
    q1 = f32(a[0] / b[0])
    qb = ds_mul_float(b, q1)
    r = ds_sub(a, qb)
    q2 = f32(f32(r[0] + r[1]) / b[0])
    return ds_add_float((q1, f32(0.0)), q2)


def ds_make(x):
    return (f32(x), f32(0.0))


def ds_add_float(a, b):
    return ds_add(a, ds_make(b))


def ds_signed_pow(x, exponent):
    exponent = f32(exponent)
    xh = f32(x[0])
    ax = abs(xh)
    if ax < 1e-30:
        return ds_make(0.0)
    mag = f32(np.exp2(f32(exponent * f32(np.log2(ax)))))
    y = f32(-mag) if xh < 0 else mag
    dy1 = f32(f32(f32(exponent * y) / xh) * x[1])
    dy2 = f32(f32(f32(f32(exponent * f32(exponent - 1.0)) * y)
                  / f32(2.0 * f32(xh * xh))) * f32(x[1] * x[1]))
    return ds_add_float(ds_make(y), f32(dy1 + dy2))


def ds_pq_inverse(C, m1, m2, C1, C2, C3):
    Yp = ds_signed_pow(ds_mul_float(C, f32(1e-4)), m1)
    numerator = ds_add_float(ds_mul_float(Yp, C2), C1)
    denominator = ds_add_float(ds_mul_float(Yp, C3), f32(1.0))
    return ds_signed_pow(ds_div(numerator, denominator), m2)


def ds_pq_forward(N, inv_m2, inv_m1, C1, C2, C3):
    Vp = ds_signed_pow(N, inv_m2)
    n = ds_sub(Vp, ds_make(C1))
    if f32(n[0] + n[1]) < 0.0:
        n = ds_make(0.0)
    denominator = ds_sub(ds_make(C2), ds_mul_float(Vp, C3))
    ratio = ds_div(n, denominator)
    return ds_mul_float(ds_signed_pow(ratio, inv_m1), f32(10000.0))


def split_hi_lo(values):
    hi = values.astype(np.float32)
    lo = (values.astype(np.float64) - hi.astype(np.float64)).astype(np.float32)
    return hi, lo


def ds_dot3(x, y, z, row):
    row_hi, row_lo = split_hi_lo(row)
    acc = ds_mul(x, ds_make(row_hi[0]))
    acc = ds_add(acc, ds_mul_float(x, row_lo[0]))
    acc = ds_add(acc, ds_mul(y, ds_make(row_hi[1])))
    acc = ds_add(acc, ds_mul_float(y, row_lo[1]))
    acc = ds_add(acc, ds_mul(z, ds_make(row_hi[2])))
    acc = ds_add(acc, ds_mul_float(z, row_lo[2]))
    return acc


# Constants (float32, matching kernel)
m1 = f32(2610.0 / 4096.0 * 0.25)
m2 = f32(1.7 * 2523.0 / 32.0)
C1 = f32(3424.0 / 4096.0)
C2 = f32(2413.0 / 4096.0 * 32.0)
C3 = f32(2392.0 / 4096.0 * 32.0)
inv_m2 = f32(1.0 / m2)
inv_m1 = f32(1.0 / m1)
B = f32(1.15)
G = f32(0.66)
D = f32(-0.56)
D0 = f32(1.6295499532821566e-11)
Y_w = f32(_JZAZBZ_Y_W_CDM2)

xyz_to_lms = np.array([
    [0.41478972, 0.57999900, 0.01464800],
    [-0.20151000, 1.12064900, 0.05310080],
    [-0.01660080, 0.26480000, 0.66847990],
], dtype=np.float64)
lmsp_to_izazbz = np.array([
    [0.500000, 0.500000, 0.000000],
    [3.524000, -4.066708, 0.542708],
    [0.199076, 1.096799, -1.295875],
], dtype=np.float64)
izazbz_to_lmsp = np.linalg.inv(lmsp_to_izazbz).astype(np.float32)
lms_to_xyz = np.linalg.inv(xyz_to_lms).astype(np.float32)

cs = colour.RGB_COLOURSPACES["sRGB"]
rgb_to_xyz = cs.matrix_RGB_to_XYZ.astype(np.float32)
xyz_to_rgb = np.linalg.inv(cs.matrix_RGB_to_XYZ).astype(np.float32)
white = np.asarray(cs.whitepoint, dtype=np.float64)


def ds_forward(p):
    r, g, b = ds_make(p[0]), ds_make(p[1]), ds_make(p[2])
    X = ds_dot3(r, g, b, rgb_to_xyz[0])
    Y = ds_dot3(r, g, b, rgb_to_xyz[1])
    Z = ds_dot3(r, g, b, rgb_to_xyz[2])
    X = ds_mul_float(X, Y_w)
    Y = ds_mul_float(Y, Y_w)
    Z = ds_mul_float(Z, Y_w)
    Xp = ds_sub(ds_mul_float(X, B), ds_mul_float(Z, B - 1.0))
    Yp = ds_add(ds_mul_float(Y, G), ds_mul_float(X, 1.0 - G))
    L = ds_dot3(Xp, Yp, Z, xyz_to_lms[0])
    M = ds_dot3(Xp, Yp, Z, xyz_to_lms[1])
    S = ds_dot3(Xp, Yp, Z, xyz_to_lms[2])
    Lp = ds_pq_inverse(L, m1, m2, C1, C2, C3)
    Mp = ds_pq_inverse(M, m1, m2, C1, C2, C3)
    Sp = ds_pq_inverse(S, m1, m2, C1, C2, C3)
    Iz = ds_dot3(Lp, Mp, Sp, lmsp_to_izazbz[0])
    az = ds_dot3(Lp, Mp, Sp, lmsp_to_izazbz[1])
    bz = ds_dot3(Lp, Mp, Sp, lmsp_to_izazbz[2])
    one_plus_D = ds_make(1.0 + D)
    minus_D = ds_make(-D)
    Jz = ds_sub(
        ds_div(ds_mul(Iz, one_plus_D), ds_sub(ds_make(1.0), ds_mul(Iz, minus_D))),
        ds_make(D0),
    )
    return Jz, az, bz, Lp, Mp, Sp


def ds_inverse(jab, lmsp):
    Jz, az, bz = ds_make(jab[0]), ds_make(jab[1]), ds_make(jab[2])
    Jz_plus_D0 = ds_add(Jz, ds_make(D0))
    one_plus_D = ds_make(1.0 + D)
    minus_D = ds_make(-D)
    Iz = ds_div(
        Jz_plus_D0,
        ds_add(one_plus_D, ds_mul(Jz_plus_D0, minus_D)),
    )
    Lp = ds_dot3(Iz, az, bz, izazbz_to_lmsp[0])
    Mp = ds_dot3(Iz, az, bz, izazbz_to_lmsp[1])
    Sp = ds_dot3(Iz, az, bz, izazbz_to_lmsp[2])
    L = ds_pq_forward(Lp, inv_m2, inv_m1, C1, C2, C3)
    M = ds_pq_forward(Mp, inv_m2, inv_m1, C1, C2, C3)
    S = ds_pq_forward(Sp, inv_m2, inv_m1, C1, C2, C3)
    Xp = ds_dot3(L, M, S, lms_to_xyz[0])
    Yp = ds_dot3(L, M, S, lms_to_xyz[1])
    Z = ds_dot3(L, M, S, lms_to_xyz[2])
    X = ds_div(ds_add(Xp, ds_mul_float(Z, B - 1.0)), ds_make(B))
    Y = ds_div(ds_sub(Yp, ds_mul_float(X, 1.0 - G)), ds_make(G))
    X = ds_mul_float(X, 1.0 / Y_w)
    Y = ds_mul_float(Y, 1.0 / Y_w)
    Z = ds_mul_float(Z, 1.0 / Y_w)
    out_r = ds_dot3(X, Y, Z, xyz_to_rgb[0])
    out_g = ds_dot3(X, Y, Z, xyz_to_rgb[1])
    out_b = ds_dot3(X, Y, Z, xyz_to_rgb[2])
    return (
        np.array([L[0] + L[1], M[0] + M[1], S[0] + S[1]], dtype=np.float32),
        np.array([
            f32(out_r[0] + out_r[1]),
            f32(out_g[0] + out_g[1]),
            f32(out_b[0] + out_b[1]),
        ]),
    )


def main():
    backend = select_backend("mlx", precision="float32")
    output_color_space = "sRGB"

    rng = np.random.default_rng(20260608)
    rgb = rng.uniform(0.0, 1.0, size=(6, 7, 3)).astype(np.float32)

    # CPU reference
    xyz_cpu = colour.RGB_to_XYZ(
        rgb, colourspace="sRGB", illuminant=white, apply_cctf_decoding=False,
    )
    jab_cpu = colour.XYZ_to_Jzazbz(xyz_cpu * _JZAZBZ_Y_W_CDM2)
    xyz_back_cpu = colour.Jzazbz_to_XYZ(jab_cpu) / _JZAZBZ_Y_W_CDM2
    rgb_back_cpu = colour.XYZ_to_RGB(
        xyz_back_cpu, colourspace="sRGB", illuminant=white, apply_cctf_encoding=False,
    )

    # CPU reference for inverse LMS (Lp->L via JzAzBz PQ forward)
    Jz_cpu = jab_cpu[..., 0]
    az_cpu = jab_cpu[..., 1]
    bz_cpu = jab_cpu[..., 2]
    Iz_cpu = (Jz_cpu + D0) / (1.0 + D - D * (Jz_cpu + D0))
    lmsp_p_cpu = np.stack([Iz_cpu, az_cpu, bz_cpu], axis=-1) @ np.linalg.inv(
        np.array([
            [0.500000, 0.500000, 0.000000],
            [3.524000, -4.066708, 0.542708],
            [0.199076, 1.096799, -1.295875],
        ], dtype=np.float64),
    ).T

    def pq_forward_jz(N):
        Vp = N ** (1.0 / m2)
        n = np.maximum(0.0, Vp - C1)
        den = C2 - C3 * Vp
        ratio = n / den
        return 10000.0 * (ratio ** (1.0 / m1))

    lmsp_inv_cpu = pq_forward_jz(lmsp_p_cpu)

    # Metal debug kernel
    (
        jab_mlx_b, lmsp_mlx_b, lmsp_inv_p_mlx_b, Vp_mlx_b, n_mlx_b, den_mlx_b,
        ratio_mlx_b, lmsp_inv_mlx_b, rgb_mlx_b,
    ) = _debug_jzazbz_mlx(rgb, output_color_space, backend)
    jab_mlx = backend.to_numpy(jab_mlx_b)
    lmsp_mlx = backend.to_numpy(lmsp_mlx_b)
    lmsp_inv_p_mlx = backend.to_numpy(lmsp_inv_p_mlx_b)
    Vp_mlx = backend.to_numpy(Vp_mlx_b)
    n_mlx = backend.to_numpy(n_mlx_b)
    den_mlx = backend.to_numpy(den_mlx_b)
    ratio_mlx = backend.to_numpy(ratio_mlx_b)
    lmsp_inv_mlx = backend.to_numpy(lmsp_inv_mlx_b)
    rgb_mlx = backend.to_numpy(rgb_mlx_b)

    # Python DS simulation per pixel
    ds_jab = np.empty_like(rgb, dtype=np.float32)
    ds_lmsp = np.empty_like(rgb, dtype=np.float32)
    ds_lmsp_inv = np.empty_like(rgb, dtype=np.float32)
    ds_rgb = np.empty_like(rgb, dtype=np.float32)
    for i in range(rgb.shape[0]):
        for j in range(rgb.shape[1]):
            Jz, az, bz, Lp, Mp, Sp = ds_forward(rgb[i, j])
            ds_jab[i, j] = [Jz[0] + Jz[1], az[0] + az[1], bz[0] + bz[1]]
            ds_lmsp[i, j] = [Lp[0] + Lp[1], Mp[0] + Mp[1], Sp[0] + Sp[1]]
            lmsp_inv, rgb_out = ds_inverse(ds_jab[i, j], ds_lmsp[i, j])
            ds_lmsp_inv[i, j] = lmsp_inv
            ds_rgb[i, j] = rgb_out

    def report(label, actual, expected):
        err = np.abs(actual - expected)
        max_err = float(np.max(err))
        worst = np.unravel_index(np.argmax(err), err.shape)
        print(f"\n{label}")
        print(f"  max abs err: {max_err:.3e}")
        print(f"  worst idx: {worst}")
        print(f"  actual:   {actual[worst[0], worst[1]]}")
        print(f"  expected: {expected[worst[0], worst[1]]}")
        return max_err

    print("=" * 70)
    print("Phase 1: intermediate comparison")
    print("=" * 70)

    report("JzAzBz forward: MLX vs CPU", jab_mlx, jab_cpu)
    report("JzAzBz forward: DS sim vs CPU", ds_jab, jab_cpu)
    report("JzAzBz forward: MLX vs DS sim", jab_mlx, ds_jab)

    report("LMS' forward: MLX vs DS sim", lmsp_mlx, ds_lmsp)
    report("LMSP inverse (before PQ): MLX vs forward", lmsp_inv_p_mlx, lmsp_mlx)

    # CPU Vp reference
    Vp_cpu = lmsp_p_cpu ** (1.0 / (1.7 * 2523.0 / 32.0))
    report("Vp inverse: MLX vs CPU", Vp_mlx, Vp_cpu)

    report("LMS inverse: MLX vs DS sim", lmsp_inv_mlx, ds_lmsp_inv)

    # Detailed dump for the worst inverse LMS pixel
    err_inv = np.abs(lmsp_inv_mlx - ds_lmsp_inv)
    worst_inv = np.unravel_index(np.argmax(err_inv), err_inv.shape)
    print(f"\n  Worst inverse LMS pixel: {worst_inv}")
    print(f"  input rgb: {rgb[worst_inv[0], worst_inv[1]]}")
    print(f"  forward jab: {jab_mlx[worst_inv[0], worst_inv[1]]}")
    print(f"  forward lmsp: {lmsp_mlx[worst_inv[0], worst_inv[1]]}")
    print(f"  inverse lmsp MLX: {lmsp_inv_mlx[worst_inv[0], worst_inv[1]]}")
    print(f"  inverse lmsp DS:  {ds_lmsp_inv[worst_inv[0], worst_inv[1]]}")
    print(f"  inverse lmsp CPU: {lmsp_inv_cpu[worst_inv[0], worst_inv[1]]}")

    # Detailed PQ forward intermediates for worst channel
    N_worst = lmsp_mlx[worst_inv[0], worst_inv[1], worst_inv[2]]
    print(f"\n  PQ forward for N={N_worst:.9f} (channel {worst_inv[2]}):")
    Vp_f64 = N_worst ** (1.0 / 134.034375)
    n_f64 = max(0.0, Vp_f64 - 3424.0 / 4096.0)
    den_f64 = (2413.0 / 4096.0 * 32.0) - (2392.0 / 4096.0 * 32.0) * Vp_f64
    ratio_f64 = n_f64 / den_f64
    L_f64 = 10000.0 * (ratio_f64 ** (1.0 / (2610.0 / 4096.0 * 0.25)))
    print(f"    float64 Vp={Vp_f64:.9f} n={n_f64:.9f} den={den_f64:.9f} ratio={ratio_f64:.9f} L={L_f64:.9f}")

    # Python f32 DS for this single value
    N_ds = ds_make(N_worst)
    Vp_ds = ds_signed_pow(N_ds, f32(1.0 / m2))
    n_ds = ds_sub(Vp_ds, ds_make(C1))
    if f32(n_ds[0] + n_ds[1]) < 0.0:
        n_ds = ds_make(0.0)
    den_ds = ds_sub(ds_make(C2), ds_mul_float(Vp_ds, C3))
    ratio_ds = ds_div(n_ds, den_ds)
    L_ds = ds_mul_float(ds_signed_pow(ratio_ds, inv_m1), f32(10000.0))
    print(f"    f32 DS  Vp={Vp_ds[0]+Vp_ds[1]:.9f} n={n_ds[0]+n_ds[1]:.9f} den={den_ds[0]+den_ds[1]:.9f} ratio={ratio_ds[0]+ratio_ds[1]:.9f} L={L_ds[0]+L_ds[1]:.9f}")

    i, j, c = worst_inv
    print(f"    MLX     Vp={Vp_mlx[i,j,c]:.9f} n={n_mlx[i,j,c]:.9f} den={den_mlx[i,j,c]:.9f} ratio={ratio_mlx[i,j,c]:.9f} L={lmsp_inv_mlx[i,j,c]:.9f}")

    report("RGB roundtrip: MLX vs CPU", rgb_mlx, rgb_back_cpu)
    report("RGB roundtrip: DS sim vs CPU", ds_rgb, rgb_back_cpu)
    report("RGB roundtrip: MLX vs DS sim", rgb_mlx, ds_rgb)

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
