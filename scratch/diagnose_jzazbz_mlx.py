"""Diagnostic script: isolate PQ roundtrip error in JzAzBz MLX path.

Compare CPU reference vs MLX fused custom kernel vs MLX staged tensor ops
for the JzAzBz forward+inverse round-trip and full compression path.
"""
from __future__ import annotations

import numpy as np
import colour

from spektrafilm.gpu.backend import select_backend
from spektrafilm.gpu.kernels.gamut_compress import (
    _JZAZBZ_Y_W_CDM2,
    _compress_rgb_jzazbz_chroma_mlx_kernel,
    _xyz_to_jzazbz_backend,
    _jzazbz_to_xyz_backend,
    _rgb_to_xyz_backend,
    _xyz_to_rgb_backend,
)
from spektrafilm.gpu.kernels.color import (
    precompute_rgb_to_xyz_matrix,
    precompute_xyz_to_rgb_matrix,
)
from spektrafilm.utils.gamut_compression import (
    OutputGamutCompressSpec,
    compress_rgb,
)
from spektrafilm.gpu.kernels import gamut_compress
from spektrafilm.gpu.kernels.gamut_compress import compress_rgb_backend, compress_rgb_jzazbz_chroma_backend


def max_abs(a, b):
    return float(np.max(np.abs(a - b)))


def main():
    backend = select_backend("mlx", precision="float32")
    mx = backend.mx
    output_color_space = "sRGB"
    cs = colour.RGB_COLOURSPACES["sRGB"]
    white = np.asarray(cs.whitepoint, dtype=float)

    rng = np.random.default_rng(20260608)
    rgb = rng.uniform(-0.2, 1.35, size=(6, 7, 3)).astype(np.float32)

    # --- CPU reference full compression ---
    spec = OutputGamutCompressSpec(algorithm="jzazbz")
    expected_full = compress_rgb(rgb.astype(float), spec, output_color_space="sRGB")

    # --- MLX fused custom kernel full compression ---
    fused = _compress_rgb_jzazbz_chroma_mlx_kernel(
        backend.asarray(rgb),
        output_color_space,
        threshold=0.0,
        limit=1.0,
        power=6.0,
        lightness_compression=None,
        backend=backend,
    )
    fused_np = backend.to_numpy(fused)
    print("FUSED full compression vs CPU:", max_abs(fused_np, expected_full))

    # --- MLX via compress_rgb_backend (default spec with lightness compression) ---
    spec2 = OutputGamutCompressSpec(algorithm="jzazbz")

    calls = []
    original = gamut_compress.compress_rgb_jzazbz_chroma_backend
    def logged(*args, **kwargs):
        calls.append((args, kwargs))
        return original(*args, **kwargs)
    gamut_compress.compress_rgb_jzazbz_chroma_backend = logged

    backend_full = compress_rgb_backend(
        backend.asarray(rgb), spec2, output_color_space="sRGB", backend=backend,
    )
    backend_full_np = backend.to_numpy(backend_full)
    print("BACKEND full compression vs CPU:", max_abs(backend_full_np, expected_full))
    print("Number of logged calls:", len(calls))
    if calls:
        print("Call kwargs:", calls[0][1])

    gamut_compress.compress_rgb_jzazbz_chroma_backend = original

    # --- MLX via compress_rgb_backend (no lightness compression) ---
    spec3 = OutputGamutCompressSpec(algorithm="jzazbz", lightness_compression=None)
    backend_none = compress_rgb_backend(
        backend.asarray(rgb), spec3, output_color_space="sRGB", backend=backend,
    )
    expected_none = compress_rgb(rgb.astype(float), spec3, output_color_space="sRGB")
    backend_none_np = backend.to_numpy(backend_none)
    print("BACKEND no-lightness vs CPU:", max_abs(backend_none_np, expected_none))

    # --- Direct call to compress_rgb_jzazbz_chroma_backend ---
    backend_direct = compress_rgb_jzazbz_chroma_backend(
        backend.asarray(rgb),
        output_color_space,
        threshold=0.0,
        limit=1.0,
        power=6.0,
        lightness_compression=None,
        backend=backend,
    )
    backend_direct_np = backend.to_numpy(backend_direct)
    print("DIRECT backend fn vs CPU:", max_abs(backend_direct_np, expected_full))

    # --- CPU reference: JzAzBz round-trip (no compression) ---
    xyz_cpu = colour.RGB_to_XYZ(
        rgb, colourspace="sRGB", illuminant=white, apply_cctf_decoding=False,
    )
    jab_cpu = colour.XYZ_to_Jzazbz(xyz_cpu * _JZAZBZ_Y_W_CDM2)
    xyz_back_cpu = colour.Jzazbz_to_XYZ(jab_cpu) / _JZAZBZ_Y_W_CDM2
    rgb_back_cpu = colour.XYZ_to_RGB(
        xyz_back_cpu, colourspace="sRGB", illuminant=white, apply_cctf_encoding=False,
    )
    print("CPU JzAzBz round-trip vs input:", max_abs(rgb_back_cpu, rgb))

    # --- MLX staged tensor ops: JzAzBz round-trip (no compression) ---
    M_rgb_to_xyz = backend.asarray(precompute_rgb_to_xyz_matrix(output_color_space))
    M_xyz_to_rgb = backend.asarray(precompute_xyz_to_rgb_matrix(output_color_space))
    rgb_b = backend.asarray(rgb)
    xyz_b = _rgb_to_xyz_backend(rgb_b, M_rgb_to_xyz, backend)
    jab_b = _xyz_to_jzazbz_backend(xyz_b * _JZAZBZ_Y_W_CDM2, backend)
    xyz_back_b = _jzazbz_to_xyz_backend(jab_b, backend) / _JZAZBZ_Y_W_CDM2
    rgb_back_b = _xyz_to_rgb_backend(xyz_back_b, M_xyz_to_rgb, backend)
    staged_rt_np = backend.to_numpy(backend.nan_to_num(rgb_back_b))
    print("STAGED JzAzBz round-trip vs CPU round-trip:",
          max_abs(staged_rt_np, rgb_back_cpu))
    print("STAGED JzAzBz round-trip vs input:", max_abs(staged_rt_np, rgb))

    # --- MLX fused kernel: JzAzBz round-trip (no compression) ---
    # Use threshold just below 1.0; in-gamut colors have d_norm <= 1.
    # For colors with d_norm <= threshold there is no chroma knee.
    fused_rt = _compress_rgb_jzazbz_chroma_mlx_kernel(
        rgb,
        output_color_space,
        threshold=0.999,
        limit=1.0,
        power=1.2,
        lightness_compression=None,
        backend=backend,
    )
    fused_rt_np = backend.to_numpy(fused_rt)
    print("FUSED JzAzBz round-trip vs CPU round-trip:",
          max_abs(fused_rt_np, rgb_back_cpu))
    print("FUSED JzAzBz round-trip vs input:", max_abs(fused_rt_np, rgb))

    # Which pixels actually got compressed in fused_rt?
    # Compare fused_rt to a CPU compression with threshold=0.999, limit=1.0
    spec_rt = OutputGamutCompressSpec(algorithm="jzazbz", knee=(0.999, 1.0, 6.0))
    expected_rt = compress_rgb(rgb.astype(float), spec_rt, output_color_space="sRGB")
    print("FUSED rt vs CPU rt compression:", max_abs(fused_rt_np, expected_rt))

    # --- Error per channel for full compression ---
    diff = np.abs(fused_np - expected_full)
    print("Full compression per-channel max abs error:", diff.reshape(-1, 3).max(axis=0))
    worst = np.unravel_index(np.argmax(diff), diff.shape)
    print("Worst pixel index:", worst, "error", diff[worst])
    print("FUSED worst pixel:", fused_np[worst[0], worst[1]])
    print("CPU  worst pixel:", expected_full[worst[0], worst[1]])
    print("Input worst pixel:", rgb[worst[0], worst[1]])

    # --- Print PQ constants ---
    print("ST2084_M1:", 2610.0 / 4096.0 * 0.25)
    print("ST2084_M2_JZ:", 1.7 * 2523.0 / 32.0)
    print("ST2084_C1:", 3424.0 / 4096.0)
    print("ST2084_C2:", 2413.0 / 4096.0 * 32.0)
    print("ST2084_C3:", 2392.0 / 4096.0 * 32.0)


if __name__ == "__main__":
    main()
