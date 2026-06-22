"""Python reference for DS JzAzBz transform to validate the Metal kernel."""
from __future__ import annotations

import numpy as np
import colour
import math

from spektrafilm.gpu.backend import select_backend
from spektrafilm.gpu.kernels.gamut_compress import (
    _JZAZBZ_Y_W_CDM2,
    _compress_rgb_jzazbz_chroma_mlx_kernel,
)

# DS helpers mimicking the Metal kernel
def two_sum(a, b):
    s = a + b
    bb = s - a
    e = (a - (s - bb)) + (b - bb)
    return s, e

def quick_two_sum(a, b):
    s = a + b
    e = b - (s - a)
    return s, e

def ds_add(a, b):
    s, e = two_sum(a[0], b[0])
    lo = e + a[1] + b[1]
    return quick_two_sum(s, lo)

def ds_sub(a, b):
    s, e = two_sum(a[0], -b[0])
    lo = e + a[1] - b[1]
    return quick_two_sum(s, lo)

def ds_mul(a, b):
    p = a[0] * b[0]
    e = math.fma(a[0], b[0], -p) + a[0] * b[1] + a[1] * b[0]
    return quick_two_sum(p, e)

def ds_mul_float(a, b):
    p = a[0] * b
    e = math.fma(a[0], b, -p) + a[1] * b
    return quick_two_sum(p, e)

def ds_div(a, b):
    q1 = a[0] / b[0]
    qb = ds_mul_float(b, q1)
    r = ds_sub(a, qb)
    q2 = (r[0] + r[1]) / b[0]
    return ds_add_float(ds_make(q1), q2)

def ds_make(x):
    return (float(x), 0.0)

def ds_add_float(a, b):
    return ds_add(a, ds_make(b))

def ds_sub_float(a, b):
    return ds_sub(a, ds_make(b))

def ds_div_float(a, b):
    return ds_div(a, ds_make(b))

def ds_signed_pow(x, exponent):
    xh = x[0]
    ax = abs(xh)
    if ax < 1e-30:
        return ds_make(0.0)
    log_ax = np.log2(ax)
    exp_arg = exponent * log_ax
    mag = np.exp2(exp_arg)
    y = -mag if xh < 0 else mag
    dy1 = (exponent * y / xh) * x[1]
    dy2 = (exponent * (exponent - 1.0) * y / (2.0 * xh * xh)) * (x[1] * x[1])
    return ds_add_float(ds_make(y), dy1 + dy2)

def ds_pq_inverse(C, m1, m2, C1, C2, C3):
    Yp = ds_signed_pow(ds_mul_float(C, 1e-4), m1)
    numerator = ds_add_float(ds_mul_float(Yp, C2), C1)
    denominator = ds_add_float(ds_mul_float(Yp, C3), 1.0)
    return ds_signed_pow(ds_div(numerator, denominator), m2)

def ds_pq_forward(N, inv_m2, inv_m1, C1, C2, C3):
    Vp = ds_signed_pow(N, inv_m2)
    n = ds_sub_float(Vp, C1)
    if n[0] + n[1] < 0.0:
        n = ds_make(0.0)
    denominator = ds_sub(ds_make(C2), ds_mul_float(Vp, C3))
    ratio = ds_div(n, denominator)
    return ds_mul_float(ds_signed_pow(ratio, inv_m1), 10000.0)

# Constants
m1 = 2610.0 / 4096.0 * 0.25
m2 = 1.7 * 2523.0 / 32.0
C1 = 3424.0 / 4096.0
C2 = 2413.0 / 4096.0 * 32.0
C3 = 2392.0 / 4096.0 * 32.0
inv_m2 = 1.0 / m2
inv_m1 = 1.0 / m1
B = 1.15
G = 0.66
D = -0.56
D0 = 1.6295499532821566e-11
Y_w = 100.0

# Matrices
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
izazbz_to_lmsp = np.linalg.inv(lmsp_to_izazbz)
lms_to_xyz = np.linalg.inv(xyz_to_lms)

# sRGB matrices from colour
cs = colour.RGB_COLOURSPACES["sRGB"]
rgb_to_xyz = cs.matrix_RGB_to_XYZ.astype(np.float64)
xyz_to_rgb = np.linalg.inv(rgb_to_xyz)
white = np.asarray(cs.whitepoint, dtype=np.float64)

# Test on in-gamut input
rng = np.random.default_rng(20260608)
rgb = rng.uniform(0.0, 1.0, size=(6, 7, 3)).astype(np.float32)

# CPU reference
xyz_cpu = colour.RGB_to_XYZ(rgb, colourspace="sRGB", illuminant=white, apply_cctf_decoding=False)
jab_cpu = colour.XYZ_to_Jzazbz(xyz_cpu * Y_w)
xyz_back_cpu = colour.Jzazbz_to_XYZ(jab_cpu) / Y_w
rgb_back_cpu = colour.XYZ_to_RGB(xyz_back_cpu, colourspace="sRGB", illuminant=white, apply_cctf_encoding=False)

# DS Python reference (no compression, just roundtrip)
def ds_dot3(x, y, z, row):
    acc = ds_mul(x, ds_make(row[0]))
    acc = ds_add(acc, ds_mul(y, ds_make(row[1])))
    acc = ds_add(acc, ds_mul(z, ds_make(row[2])))
    return acc

def ds_forward(rgb_in):
    r, g, b = ds_make(rgb_in[0]), ds_make(rgb_in[1]), ds_make(rgb_in[2])
    X = ds_dot3(r, g, b, rgb_to_xyz[0])
    Y = ds_dot3(r, g, b, rgb_to_xyz[1])
    Z = ds_dot3(r, g, b, rgb_to_xyz[2])
    X = ds_mul_float(X, Y_w)
    Y = ds_mul_float(Y, Y_w)
    Z = ds_mul_float(Z, Y_w)
    Xp = ds_sub(X, ds_mul_float(Z, B - 1.0))
    Xp = ds_add(X, ds_mul_float(Z, B))  # wait, Xp = B*X - (B-1)*Z
    # redo
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
    Jz = ds_sub(ds_div(ds_mul(Iz, one_plus_D), ds_sub(ds_make(1.0), ds_mul(Iz, minus_D))), ds_make(D0))
    return Jz, az, bz

def ds_inverse(jab_in):
    Jz, az, bz = jab_in
    Jz_plus_D0 = ds_add(Jz, ds_make(D0))
    one_plus_D = ds_make(1.0 + D)
    minus_D = ds_make(-D)
    Iz = ds_div(Jz_plus_D0, ds_add(one_plus_D, ds_mul(Jz_plus_D0, minus_D)))
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
    return np.array([out_r[0]+out_r[1], out_g[0]+out_g[1], out_b[0]+out_b[1]])

ds_out = np.zeros_like(rgb, dtype=np.float64)
for i in range(rgb.shape[0]):
    for j in range(rgb.shape[1]):
        jab = ds_forward(rgb[i, j])
        ds_out[i, j] = ds_inverse(jab)

print("DS Python vs CPU roundtrip:", float(np.max(np.abs(ds_out - rgb_back_cpu))))
print("DS Python vs input:", float(np.max(np.abs(ds_out - rgb))))

# Fused kernel
backend = select_backend("mlx", precision="float32")
fused = _compress_rgb_jzazbz_chroma_mlx_kernel(
    backend.asarray(rgb),
    "sRGB",
    threshold=0.999,
    limit=1.0,
    power=6.0,
    lightness_compression=None,
    backend=backend,
)
fused_np = backend.to_numpy(fused)
print("FUSED vs CPU roundtrip:", float(np.max(np.abs(fused_np - rgb_back_cpu))))
print("FUSED vs DS Python:", float(np.max(np.abs(fused_np - ds_out))))
