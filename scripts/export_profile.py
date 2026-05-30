#!/usr/bin/env python3
"""Export film profiles as binary .prof files for the Android C++ pipeline.

Usage:
    python scripts/export_profile.py kodak_portra_400
    python scripts/export_profile.py --all
    python scripts/export_profile.py --hanatos-lut  # export LUT only
"""

import argparse
import struct
import sys
from pathlib import Path

import numpy as np

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from spektrafilm.profiles.io import load_profile
from spektrafilm.config import STANDARD_OBSERVER_CMFS
from spektrafilm.model.illuminants import standard_illuminant
from spektrafilm.utils.spectral_upsampling import MALLETT2019_BASIS as _MALLETT_BASIS_OBJ, HANATOS2025_SPECTRA_LUT

PROFILE_MAGIC = 0x53504631  # "SPF1"
PROFILE_VERSION = 1

# These match the C++ FilmProfileData struct layout exactly.
# Each entry: (name, shape_in_prof, numpy_shape, description)
# shape_in_prof is how it appears in the binary file (row-major)
PROFILE_FIELDS = [
    ("log_sensitivity",    (81, 3),  "log10 sensitivity [81,3]"),
    ("channel_density",    (81, 3),  "spectral channel density [81,3]"),
    ("base_density",       (81,),    "base density per wavelength [81]"),
    ("log_exposure",       (256,),   "log exposure axis [256]"),
    ("density_curves",     (256, 3), "density curves [256,3]"),
    ("cmfs",               (81, 3),  "CIE CMFS [81,3]"),
    ("illuminant",         (81,),    "scene illuminant [81]"),
    ("scan_illuminant",    (81,),    "scanner illuminant [81]"),
    ("enlarger_illuminant",(81,),    "enlarger illuminant [81]"),
    ("basis_functions",    (81, 3),  "Mallett2019 basis [81,3]"),
    ("basis_illuminant",   (81, 3),  "basis*illuminant [81,3]"),
    ("rgb_to_xyz",         (3, 3),   "RGB to XYZ matrix [3,3]"),
    ("xyz_to_rgb",         (3, 3),   "XYZ to RGB matrix [3,3]"),
    ("prophoto_to_xyz",    (3, 3),   "ProPhoto to XYZ [3,3]"),
    ("cctf_gamma",         None,     "CCTF gamma (scalar)"),
    ("cctf_threshold",     None,     "CCTF threshold (scalar)"),
    ("cctf_linear_slope",  None,     "CCTF linear slope (scalar)"),
    ("cctf_alpha",         None,     "CCTF alpha (scalar)"),
]


def get_srgb_cctf_params():
    """Get sRGB CCTF parameters matching the C++ implementation."""
    # sRGB piecewise: linear below threshold, power above
    # encode: y = 12.92*x if x<=0.0031308 else 1.055*x^(1/2.4)-0.055
    return {
        "cctf_gamma": 2.4,
        "cctf_threshold": 0.0031308,
        "cctf_linear_slope": 12.92,
        "cctf_alpha": 1.055,
    }


def get_illuminant(name):
    """Load an illuminant spectrum, return float32 array of shape (81,)."""
    sd = standard_illuminant(name)
    return np.array(sd[:], dtype=np.float32)


def get_color_matrix(name):
    """Get a 3x3 color matrix."""
    import colour
    try:
        cs = colour.RGB_COLOURSPACES[name]
        return cs.matrix_RGB_to_XYZ.astype(np.float32)
    except Exception:
        return np.eye(3, dtype=np.float32)


def export_profile(stock_name, output_dir):
    """Export a single film profile as a binary .prof file."""
    profile = load_profile(stock_name)
    data = profile.data
    info = profile.info

    print(f"Exporting profile: {stock_name}")
    print(f"  Type: {info.type}, Support: {info.support}")

    # Get spectral constants
    cmfs = np.array(STANDARD_OBSERVER_CMFS[:], dtype=np.float32)  # [81, 3]
    basis = np.array(_MALLETT_BASIS_OBJ[:], dtype=np.float32)      # [81, 3]

    # Get illuminants
    viewing_illuminant = info.viewing_illuminant or "D50"
    reference_illuminant = info.reference_illuminant or "D55"

    scene_illuminant = get_illuminant(reference_illuminant)
    scan_illuminant = get_illuminant(viewing_illuminant)
    enlarger_illuminant = get_illuminant("D50")  # default enlarger

    # Basis * illuminant (for Mallett2019 spectral upsampling)
    basis_illuminant = basis * scene_illuminant[:, np.newaxis]  # [81, 3]

    # Color matrices
    rgb_to_xyz = get_color_matrix("sRGB")
    xyz_to_rgb = np.linalg.inv(rgb_to_xyz).astype(np.float32)
    prophoto_to_xyz = get_color_matrix("ProPhoto RGB")

    # CCTF parameters
    cctf = get_srgb_cctf_params()

    # Build the binary data in struct order
    arrays = []

    def add(arr, expected_shape, name):
        arr = np.asarray(arr, dtype=np.float32)
        if arr.shape != expected_shape:
            # Try to reshape or pad
            if arr.size == np.prod(expected_shape):
                arr = arr.reshape(expected_shape)
            else:
                print(f"  WARNING: {name} shape {arr.shape} != expected {expected_shape}, zero-filling")
                arr = np.zeros(expected_shape, dtype=np.float32)
        arrays.append(arr.ravel())

    # Profile data arrays
    log_sens = np.asarray(data.log_sensitivity, dtype=np.float32)
    if log_sens.shape == (81, 3):
        add(log_sens, (81, 3), "log_sensitivity")
    else:
        add(log_sens.T if log_sens.shape == (3, 81) else log_sens, (81, 3), "log_sensitivity")

    add(data.channel_density, (81, 3), "channel_density")

    base_d = np.asarray(data.base_density, dtype=np.float32)
    if base_d.shape == (81,):
        add(base_d, (81,), "base_density")
    else:
        # If it's per-channel, broadcast to per-wavelength
        add(np.full(81, base_d.mean(), dtype=np.float32), (81,), "base_density")

    add(data.log_exposure, (256,), "log_exposure")
    add(data.density_curves, (256, 3), "density_curves")
    add(cmfs, (81, 3), "cmfs")
    add(scene_illuminant, (81,), "illuminant")
    add(scan_illuminant, (81,), "scan_illuminant")
    add(enlarger_illuminant, (81,), "enlarger_illuminant")
    add(basis, (81, 3), "basis_functions")
    add(basis_illuminant, (81, 3), "basis_illuminant")
    add(rgb_to_xyz, (3, 3), "rgb_to_xyz")
    add(xyz_to_rgb, (3, 3), "xyz_to_rgb")
    add(prophoto_to_xyz, (3, 3), "prophoto_to_xyz")

    # Scalar CCTF params
    for name in ["cctf_gamma", "cctf_threshold", "cctf_linear_slope", "cctf_alpha"]:
        arrays.append(np.array([cctf[name]], dtype=np.float32))

    # Concatenate all data
    data_bytes = np.concatenate(arrays).tobytes()

    # Write .prof file with header
    header = struct.pack("IIII", PROFILE_MAGIC, PROFILE_VERSION, 16, 0)
    output_path = Path(output_dir) / f"{stock_name}.prof"
    with open(output_path, "wb") as f:
        f.write(header)
        f.write(data_bytes)

    total_floats = sum(a.size for a in arrays)
    print(f"  Written: {output_path} ({len(data_bytes)} bytes, {total_floats} floats)")
    return output_path


def export_hanatos_lut(output_dir):
    """Export the Hanatos2025 spectral LUT as a separate binary file."""
    lut = np.array(HANATOS2025_SPECTRA_LUT, dtype=np.float32)
    assert lut.shape == (192, 192, 81), f"Unexpected LUT shape: {lut.shape}"

    output_path = Path(output_dir) / "hanatos2025_lut.bin"
    with open(output_path, "wb") as f:
        f.write(lut.tobytes())

    print(f"Hanatos2025 LUT: {output_path} ({lut.nbytes} bytes, {lut.size} floats)")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Export film profiles for Android")
    parser.add_argument("stock", nargs="?", help="Film stock name to export")
    parser.add_argument("--all", action="store_true", help="Export all default profiles")
    parser.add_argument("--hanatos-lut", action="store_true", help="Export Hanatos2025 LUT")
    parser.add_argument("--output-dir", default="android/app/src/main/assets/profiles",
                        help="Output directory")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.hanatos_lut:
        export_hanatos_lut(output_dir)
        return

    if args.all:
        stocks = ["kodak_portra_400", "kodak_portra_160", "kodak_gold_200",
                  "fuji_pro_400h", "kodak_trix_400", "ilford_hp5",
                  "kodak_portra_endura", "kodak_supra_endura"]
        for stock in stocks:
            try:
                export_profile(stock, output_dir)
            except Exception as e:
                print(f"  ERROR exporting {stock}: {e}")
        export_hanatos_lut(output_dir)
    elif args.stock:
        export_profile(args.stock, output_dir)
    else:
        # Default: export kodak_portra_400 + LUT
        export_profile("kodak_portra_400", output_dir)
        try:
            export_profile("kodak_portra_endura", output_dir)
        except Exception as e:
            print(f"  Note: kodak_portra_endura not available: {e}")
        export_hanatos_lut(output_dir)


if __name__ == "__main__":
    main()
