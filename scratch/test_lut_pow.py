"""Evaluate LUT-based pow for the 4 JzAzBz exponents."""
from __future__ import annotations

import numpy as np

m1 = 2610.0 / 4096.0 * 0.25
m2 = 1.7 * 2523.0 / 32.0
inv_m2 = 1.0 / m2
inv_m1 = 1.0 / m1

print(f"m1={m1}, m2={m2}, inv_m2={inv_m2}, inv_m1={inv_m1}")

def lut_error(p, x_min, x_max, n_bins=4096):
    # Exclude exact 0 if p <= 0 to avoid inf
    eps = 1e-30
    xs = np.linspace(max(x_min, eps), x_max, 100000, dtype=np.float64)
    # LUT nodes
    nodes = np.linspace(max(x_min, eps), x_max, n_bins, dtype=np.float64)
    vals = nodes ** p
    # Linear interpolation on log or linear scale
    # Try linear scale first
    y_interp = np.interp(xs, nodes, vals)
    y_true = xs ** p
    err = np.max(np.abs(y_interp - y_true))
    return err

# Estimate ranges from actual PQ behavior
print("\n=== Linear-scale LUT max interpolation error ===")
print(f"inv_m2 (p={inv_m2:.5f}, x in [1e-6, 1]): {lut_error(inv_m2, 1e-6, 1.0, 4096):.3e}")
print(f"inv_m1 (p={inv_m1:.3f}, x in [1e-6, 1]): {lut_error(inv_m1, 1e-6, 1.0, 4096):.3e}")
print(f"m1     (p={m1:.5f}, x in [0, 2]):       {lut_error(m1, 0.0, 2.0, 4096):.3e}")
print(f"m2     (p={m2:.3f}, x in [0, 1]):       {lut_error(m2, 0.0, 1.0, 4096):.3e}")

# Log-spaced nodes might be better for small x
print("\n=== Log-spaced LUT max interpolation error ===")
def lut_error_log(p, x_min, x_max, n_bins=4096):
    eps = 1e-30
    xs = np.linspace(max(x_min, eps), x_max, 100000, dtype=np.float64)
    log_nodes = np.linspace(np.log(max(x_min, eps)), np.log(x_max), n_bins)
    nodes = np.exp(log_nodes)
    vals = nodes ** p
    y_interp = np.interp(xs, nodes, vals)
    y_true = xs ** p
    return np.max(np.abs(y_interp - y_true))

print(f"inv_m2 (p={inv_m2:.5f}, x in [1e-6, 1]): {lut_error_log(inv_m2, 1e-6, 1.0, 4096):.3e}")
print(f"inv_m1 (p={inv_m1:.3f}, x in [1e-6, 1]): {lut_error_log(inv_m1, 1e-6, 1.0, 4096):.3e}")
print(f"m1     (p={m1:.5f}, x in [0, 2]):       {lut_error_log(m1, 0.0, 2.0, 4096):.3e}")
print(f"m2     (p={m2:.3f}, x in [0, 1]):       {lut_error_log(m2, 0.0, 1.0, 4096):.3e}")

# More realistic ranges for m2 and inv_m1
C1 = 3424.0 / 4096.0
C2 = 2413.0 / 4096.0 * 32.0
C3 = 2392.0 / 4096.0 * 32.0
print(f"\nC1={C1}, C2={C2}, C3={C3}, C2/C3={C2/C3}")
print(f"m2 realistic range [C1, C2/C3] = [{C1:.4f}, {C2/C3:.4f}]")
print(f"m2 log LUT over [C1, C2/C3]: {lut_error_log(m2, C1, C2/C3, 4096):.3e}")
print(f"m2 linear LUT over [C1, C2/C3]: {lut_error(m2, C1, C2/C3, 4096):.3e}")

# For inv_m1, ratio = (Vp - C1)/(C2 - C3*Vp); Vp in [0,1]
# Let's compute range
Vps = np.linspace(0.0, 1.0, 10000)
ratios = (Vps - C1) / (C2 - C3 * Vps)
ratios = ratios[ratios > 0]
print(f"\ninv_m1 ratio range: [{ratios.min():.4e}, {ratios.max():.4e}]")
print(f"inv_m1 log LUT over actual range: {lut_error_log(inv_m1, float(ratios.min()), float(ratios.max()), 4096):.3e}")
