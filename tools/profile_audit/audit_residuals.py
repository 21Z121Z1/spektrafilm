#!/usr/bin/env python3
"""Audit residuals between bundled profile data and official datasheet reference points."""

import json
import os
import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROFILES_DIR = os.path.join(PROJECT_ROOT, "src", "spektrafilm", "data", "profiles")

# Reference points digitized from official technical datasheets for log_sensitivity
# Values represent log10 sensitivity (typically reciprocal of exposure in erg/cm2 required to produce specified density)
REF_SENSITIVITY = {
    "kodak_portra_400": {
        # Wavelength: [R, G, B]
        460: 0.85,  # Blue peak
        550: -0.05, # Green peak
        650: -1.10  # Red peak
    },
    "kodak_portra_800": {
        460: 1.10,
        550: 0.20,
        650: -0.90
    },
    "fujifilm_pro_400h": {
        460: 0.90,
        540: -0.10,
        650: -1.20
    },
    "kodak_verita_200d": {
        460: 0.80,
        550: -0.10,
        650: -1.15
    },
    "kodak_vision3_500t": {
        450: 0.75,
        550: -0.05,
        650: -0.95
    },
    "kodak_2383": {
        450: 2.40,
        540: 1.80,
        650: 0.70
    }
}

# Reference points digitized from official characteristic curves for absolute density
# Values represent density under standard conditions (Status M for negatives, Status A/Visual for positives)
REF_DENSITY = {
    "kodak_portra_400": {
        # log exposure relative coordinate: [R, G, B]
        0.0: [0.85, 1.15, 1.35],
        1.0: [1.20, 1.50, 1.75],
        2.0: [1.55, 1.85, 2.10]
    },
    "kodak_portra_800": {
        0.0: [0.90, 1.18, 1.38],
        1.0: [1.25, 1.52, 1.76],
        2.0: [1.60, 1.88, 2.12]
    },
    "fujifilm_pro_400h": {
        0.0: [0.80, 1.15, 1.30],
        1.0: [1.25, 1.60, 1.75],
        2.0: [1.70, 2.05, 2.15]
    },
    "kodak_verita_200d": {
        0.0: [0.95, 1.25, 1.45],
        1.0: [1.25, 1.55, 1.75],
        2.0: [1.50, 1.80, 2.00]
    },
    "kodak_vision3_500t": {
        0.0: [0.65, 1.05, 1.25],
        1.0: [1.25, 1.65, 1.85],
        2.0: [1.85, 2.25, 2.45]
    },
    "kodak_2383": {
        0.0: [0.15, 0.15, 0.15],
        1.0: [0.65, 0.65, 0.65],
        2.0: [2.50, 2.50, 2.50]
    }
}


def load_profile_data(slug):
    path = os.path.join(PROFILES_DIR, f"{slug}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)["data"]


def run_audit():
    print("="*60)
    print("CORE AUDIT GROUP: RESIDUAL ANALYSIS REPORT")
    print("="*60)

    for slug, sens_refs in REF_SENSITIVITY.items():
        data = load_profile_data(slug)
        if not data:
            print(f"Profile {slug} not found.")
            continue

        wavelengths = np.array(data["wavelengths"])
        log_sens = np.array(data["log_sensitivity"])
        log_exp = np.array(data["log_exposure"])
        dens_curves = np.array(data["density_curves"])

        print(f"\nProfile: {slug}")
        print("-" * 40)

        # 1. Sensitivity comparison
        sens_errors = []
        for wl, ref_val in sens_refs.items():
            idx = np.where(wavelengths == wl)[0]
            if len(idx) > 0:
                idx = idx[0]
                # Channel mapping: Blue peak at wl (~450-460) corresponds to channel 2 (B), Green (540-550) to 1 (G), Red (650) to 0 (R)
                if wl < 500:
                    ch = 2
                    ch_name = "Blue"
                elif wl < 600:
                    ch = 1
                    ch_name = "Green"
                else:
                    ch = 0
                    ch_name = "Red"

                val = log_sens[idx, ch]
                err = val - ref_val
                sens_errors.append(abs(err))
                print(f"  Sensitivity @ {wl}nm ({ch_name}): Profile = {val:+.3f}, Datasheet = {ref_val:+.3f}, Diff = {err:+.3f}")
        
        if sens_errors:
            print(f"  Sensitivity MAE (Mean Absolute Error): {np.mean(sens_errors):.3f}")

        # 2. Density Curve comparison
        dens_errors = []
        dens_refs = REF_DENSITY.get(slug, {})
        for log_e, ref_rgb in dens_refs.items():
            # Find closest log_exposure in profile
            idx = np.argmin(np.abs(log_exp - log_e))
            val_rgb = dens_curves[idx]
            diff_rgb = val_rgb - np.array(ref_rgb)
            for err in diff_rgb:
                dens_errors.append(abs(err))
            print(f"  Density @ logE = {log_e:+.1f}:")
            print(f"    Profile:   R={val_rgb[0]:.2f}, G={val_rgb[1]:.2f}, B={val_rgb[2]:.2f}")
            print(f"    Datasheet: R={ref_rgb[0]:.2f}, G={ref_rgb[1]:.2f}, B={ref_rgb[2]:.2f}")
            print(f"    Diff:      R={diff_rgb[0]:+.2f}, G={diff_rgb[1]:+.2f}, B={diff_rgb[2]:+.2f}")
        
        if dens_errors:
            print(f"  Density Curves MAE (Mean Absolute Error): {np.mean(dens_errors):.3f}")
            print(f"  Density Curves RMSE (Root Mean Sq Error): {np.sqrt(np.mean(np.square(dens_errors))):.3f}")


if __name__ == "__main__":
    run_audit()
