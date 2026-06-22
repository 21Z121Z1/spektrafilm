"""Analyze PQ roundtrip error propagation."""
from __future__ import annotations

import numpy as np

m1 = 2610.0 / 4096.0 * 0.25
m2 = 1.7 * 2523.0 / 32.0
C1 = 3424.0 / 4096.0
C2 = 2413.0 / 4096.0 * 32.0
C3 = 2392.0 / 4096.0 * 32.0

def pq_inverse(C):
    Yp = C / 10000.0
    Yp_m1 = Yp ** m1
    ratio = (C1 + C2 * Yp_m1) / (C3 * Yp_m1 + 1.0)
    return ratio ** m2

def pq_forward(N):
    Vp = N ** (1.0 / m2)
    n = max(0.0, Vp - C1)
    ratio = n / (C2 - C3 * Vp)
    return 10000.0 * (ratio ** (1.0 / m1))

# Test at various C values
for C in [0.1, 1.0, 10.0, 100.0, 1000.0, 10000.0]:
    N = pq_inverse(C)
    C_back = pq_forward(N)
    # Add float32 epsilon perturbation to N
    N_pert = np.float32(N)  # cast to float32 and back
    C_back_pert = pq_forward(float(N_pert))
    print(f"C={C:8.2f} N={N:.6e} C_back={C_back:.6f} err_from_N_float32={abs(C_back_pert-C_back):.6e}")

# Direct float32 simulation
print("\nDirect float32 roundtrip:")
for C in [0.1, 1.0, 10.0, 100.0, 1000.0, 10000.0]:
    C_f = np.float32(C)
    Yp = C_f / np.float32(10000.0)
    Yp_m1 = np.float32(Yp) ** np.float32(m1)
    ratio = (np.float32(C1) + np.float32(C2) * Yp_m1) / (np.float32(C3) * Yp_m1 + np.float32(1.0))
    N = np.float32(ratio) ** np.float32(m2)
    Vp = N ** np.float32(1.0 / m2)
    n = max(np.float32(0.0), Vp - np.float32(C1))
    denom = np.float32(C2) - np.float32(C3) * Vp
    ratio2 = n / denom
    C_back = np.float32(10000.0) * (ratio2 ** np.float32(1.0 / m1))
    print(f"C={C:8.2f} C_back={C_back:.6f} rel_err={abs(C_back-C)/C:.6e}")
