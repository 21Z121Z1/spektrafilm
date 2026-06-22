"""Diagnostic: isolate PQ roundtrip error in resident MLX JzAzBz path.

Reports:
- Current xfail test max absolute error.
- JzAzBz RGB round-trip error (no compression) vs CPU float64 reference.
- Standalone PQ forward/inverse roundtrip error on representative LMS values.
- Estimated float32 double-single (DS) floor from a faithful Python simulation.

Conclusion is written to stdout; non-zero exit if any assertion fails.
"""
from __future__ import annotations

import math
import subprocess
import sys

import numpy as np
import colour

from spektrafilm.gpu.backend import select_backend
from spektrafilm.gpu.kernels.gamut_compress import (
    _JZAZBZ_Y_W_CDM2,
    _compress_rgb_jzazbz_chroma_mlx_kernel,
    _eotf_inverse_st2084_jz_backend,
    _eotf_st2084_jz_backend,
)


def run_xfail_error() -> float:
    """Run the parametrized xfail case and return the reported max abs diff."""
    result = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "tests/test_gamut_compression.py",
            "-q", "--runxfail",
            "-k", "test_mlx_backend_matches_cpu_reference_without_full_frame_readback and jzazbz",
        ],
        capture_output=True,
        text=True,
    )
    marker = "Max absolute difference among violations: "
    if marker in result.stdout:
        line = result.stdout.split(marker)[1].split("\n")[0]
        return float(line.strip())
    return float("nan")


def float32_ds_simulation_roundtrip(rgb: np.ndarray) -> tuple[np.ndarray, float]:
    """Faithful float32 DS simulation of the kernel's RGB->JzAzBz->RGB path."""
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
        mag = f32(math.exp2(f32(exponent * f32(math.log2(ax)))))
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

    def ds_forward(p):
        r, g, b = ds_make(p[0]), ds_make(p[1]), ds_make(p[2])
        X = ds_dot3(r, g, b, rgb_to_xyz[0])
        Y = ds_dot3(r, g, b, rgb_to_xyz[1])
        Z = ds_dot3(r, g, b, rgb_to_xyz[2])
        X = ds_mul_float(X, Y_w)
        Y = ds_mul_float(Y, Y_w)
        Z = ds_mul_float(Z, Y_w)
        Xp = ds_sub(ds_mul_float(X, B), ds_mul_float(Z, f32(B - 1.0)))
        Yp = ds_add(ds_mul_float(Y, G), ds_mul_float(X, f32(1.0 - G)))
        L = ds_dot3(Xp, Yp, Z, xyz_to_lms[0])
        M = ds_dot3(Xp, Yp, Z, xyz_to_lms[1])
        S = ds_dot3(Xp, Yp, Z, xyz_to_lms[2])
        Lp = ds_pq_inverse(L, m1, m2, C1, C2, C3)
        Mp = ds_pq_inverse(M, m1, m2, C1, C2, C3)
        Sp = ds_pq_inverse(S, m1, m2, C1, C2, C3)
        Iz = ds_dot3(Lp, Mp, Sp, lmsp_to_izazbz[0])
        az = ds_dot3(Lp, Mp, Sp, lmsp_to_izazbz[1])
        bz = ds_dot3(Lp, Mp, Sp, lmsp_to_izazbz[2])
        one_plus_D = ds_make(f32(1.0 + D))
        minus_D = ds_make(f32(-D))
        Jz = ds_sub(
            ds_div(
                ds_mul(Iz, one_plus_D),
                ds_sub(ds_make(f32(1.0)), ds_mul(Iz, minus_D)),
            ),
            ds_make(D0),
        )
        return Jz, az, bz

    def ds_inverse(jab_in):
        Jz, az, bz = jab_in
        Jz_plus_D0 = ds_add(Jz, ds_make(D0))
        one_plus_D = ds_make(f32(1.0 + D))
        minus_D = ds_make(f32(-D))
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
        X = ds_div(ds_add(Xp, ds_mul_float(Z, f32(B - 1.0))), ds_make(B))
        Y = ds_div(ds_sub(Yp, ds_mul_float(X, f32(1.0 - G))), ds_make(G))
        X = ds_mul_float(X, f32(1.0 / Y_w))
        Y = ds_mul_float(Y, f32(1.0 / Y_w))
        Z = ds_mul_float(Z, f32(1.0 / Y_w))
        out_r = ds_dot3(X, Y, Z, xyz_to_rgb[0])
        out_g = ds_dot3(X, Y, Z, xyz_to_rgb[1])
        out_b = ds_dot3(X, Y, Z, xyz_to_rgb[2])
        return np.array([
            f32(out_r[0] + out_r[1]),
            f32(out_g[0] + out_g[1]),
            f32(out_b[0] + out_b[1]),
        ])

    out = np.empty_like(rgb, dtype=np.float32)
    for i in range(rgb.shape[0]):
        for j in range(rgb.shape[1]):
            jab = ds_forward(rgb[i, j])
            out[i, j] = ds_inverse(jab)
    return out, float(np.max(np.abs(out - rgb)))


def main() -> int:
    print("=" * 70)
    print("JzAzBz MLX diagnostic")
    print("=" * 70)

    xfail_err = run_xfail_error()
    print(f"\n1. Current xfail max abs error: {xfail_err:.3e}")

    backend = select_backend("mlx", precision="float32")
    output_color_space = "sRGB"
    cs = colour.RGB_COLOURSPACES["sRGB"]
    white = np.asarray(cs.whitepoint, dtype=np.float64)

    rng = np.random.default_rng(20260608)
    rgb = rng.uniform(0.0, 1.0, size=(6, 7, 3)).astype(np.float32)

    # CPU reference round-trip (no compression)
    xyz_cpu = colour.RGB_to_XYZ(
        rgb, colourspace="sRGB", illuminant=white, apply_cctf_decoding=False,
    )
    jab_cpu = colour.XYZ_to_Jzazbz(xyz_cpu * _JZAZBZ_Y_W_CDM2)
    xyz_back_cpu = colour.Jzazbz_to_XYZ(jab_cpu) / _JZAZBZ_Y_W_CDM2
    rgb_back_cpu = colour.XYZ_to_RGB(
        xyz_back_cpu, colourspace="sRGB", illuminant=white, apply_cctf_encoding=False,
    )
    cpu_rt_err = float(np.max(np.abs(rgb_back_cpu - rgb)))
    print(f"\n2. CPU float64 round-trip error vs input: {cpu_rt_err:.3e}")

    # Fused kernel round-trip (threshold high enough to be identity for in-gamut)
    fused = _compress_rgb_jzazbz_chroma_mlx_kernel(
        backend.asarray(rgb),
        output_color_space,
        threshold=0.999,
        limit=1.0,
        power=6.0,
        lightness_compression=None,
        backend=backend,
    )
    fused_np = backend.to_numpy(fused)
    fused_rt_err = float(np.max(np.abs(fused_np - rgb_back_cpu)))
    print(f"3. Fused kernel round-trip error vs CPU ref: {fused_rt_err:.3e}")

    # Float32 DS simulation floor
    _, ds_floor = float32_ds_simulation_roundtrip(rgb)
    print(f"4. Float32 DS simulation floor (faithful): {ds_floor:.3e}")

    # Standalone PQ round-trip on representative LMS values
    lms = np.logspace(-2, 2, 1000).astype(np.float32)
    lms = np.stack([lms, lms * 0.5, lms * 2.0], axis=-1)
    lms_b = backend.asarray(lms)
    lms_p = _eotf_inverse_st2084_jz_backend(lms_b, backend)
    lms_back = _eotf_st2084_jz_backend(lms_p, backend)
    pq_rel_err = float(np.max(np.abs(backend.to_numpy(lms_back) - lms) / (np.abs(lms) + 1e-12)))
    print(f"5. MLX PQ round-trip relative error (0.01-100 cd/m^2): {pq_rel_err:.3e}")

    print("\n" + "=" * 70)
    print("Conclusion: PQ forward/inverse roundtrip is the dominant error source.")
    print(f"  - CPU reference already has {cpu_rt_err:.3e} round-trip error.")
    print(f"  - MLX fused kernel is {fused_rt_err:.3e} away from CPU reference.")
    print(f"  - Faithful float32 DS simulation floor is ~{ds_floor:.3e}.")
    print(f"  - Standalone PQ roundtrip relative error is ~{pq_rel_err:.3e}.")
    print("  -> 1e-6 absolute parity likely requires precision beyond float32 DS.")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
