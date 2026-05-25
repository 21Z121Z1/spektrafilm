import sys
import numpy as np
from scipy.optimize import curve_fit

sys.path.append("/Users/retriedstormtrooper/Documents/spektrafilm-main/src")
from spektrafilm.profiles.io import load_profile

papers = [
    "fujifilm_crystal_archive_typeii",
    "kodak_ektacolor_edge",
    "kodak_endura_premier",
    "kodak_portra_endura",
    "kodak_supra_endura",
    "kodak_ultra_endura"
]

# Logistic function
def logistic(x, L, U, k, x0):
    return L + (U - L) / (1 + np.exp(-k * (x - x0)))

for p in papers:
    try:
        prof = load_profile(p)
        le = prof.data.log_exposure
        dc = prof.data.density_curves[:, 1] # Green channel
        
        # Check if increasing or decreasing
        is_increasing = dc[-1] > dc[0]
        
        # initial guess
        L_guess = np.min(dc)
        U_guess = np.max(dc)
        x0_guess = le[np.argmin(np.abs(dc - (L_guess + U_guess) / 2))]
        k_guess = 2.0 if is_increasing else -2.0
        
        popt, _ = curve_fit(logistic, le, dc, p0=[L_guess, U_guess, k_guess, x0_guess], maxfev=10000)
        L, U, k, x0 = popt
        print(f"**{p}**")
        print(f"D(x) = {L:.3f} + ({U:.3f} - {L:.3f}) / (1 + exp(-{k:.3f} * (x - {x0:.3f})))")
        print(f"(D_min={L:.3f}, D_max={U:.3f}, k={k:.3f}, x0={x0:.3f})\n")
    except Exception as e:
        print(f"**{p}**: Could not fit ({e})\n")
