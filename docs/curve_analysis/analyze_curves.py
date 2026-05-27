import numpy as np
from scipy.optimize import curve_fit
from spektrafilm.runtime.api import Simulator
from spektrafilm.runtime.params_builder import init_params, digest_params
from spektrafilm.model.stocks import FilmStocks, PrintPapers
import json

# Generate a high dynamic range ramp
# From 10^-3 to 10^2
evs = np.linspace(-10, 8, 256)
scene_luminance = np.power(2.0, evs).astype(np.float32)
# Create neutral grey image (N, 3)
input_rgb = np.stack([scene_luminance]*3, axis=-1).reshape(1, 256, 3)

results = []

films = [f.value for f in FilmStocks]
papers = [p.value for p in PrintPapers]

for film in films:
    for paper in papers:
        # Initialize simulator
        try:
            params = init_params(film_profile=film, print_profile=paper)
            params = digest_params(params)
            
            sim = Simulator(params)
            
            # Process
            out = sim.process(input_rgb)
            out_rgb = out[0] # Shape: (256, 3)
            out_y = np.max(out_rgb, axis=-1)
            
            # 0. Shadow Floor (scene_y = 0.001)
            idx_001 = np.argmin(np.abs(scene_luminance - 0.001))
            shadow_rgb = out_rgb[idx_001]
            shadow_y = out_y[idx_001]
            shadow_spread = float(np.max(shadow_rgb) - np.min(shadow_rgb))
            
            # Toe (shadow contrast between 0.001 and 0.05)
            idx_005 = np.argmin(np.abs(scene_luminance - 0.05))
            shadow_contrast = (out_y[idx_005] - shadow_y) / (0.05 - 0.001)

            # 1. Diffuse white (scene_y = 1.0)
            idx_1 = np.argmin(np.abs(scene_luminance - 1.0))
            look_white_rgb = out_rgb[idx_1]
            look_white_y = out_y[idx_1]
            
            # Midtone Contrast (between 0.05 and 1.0)
            midtone_contrast = (look_white_y - out_y[idx_005]) / (1.0 - 0.05)

            # 2. Max shoulder (scene_y = 16.0)
            idx_16 = np.argmin(np.abs(scene_luminance - 16.0))
            shoulder_rgb = out_rgb[idx_16]
            shoulder_y = out_y[idx_16]
            
            # Highlight Rolloff (between 1.0 and 16.0)
            highlight_contrast = (shoulder_y - look_white_y) / (16.0 - 1.0)
            
            # 3. Channel spread at shoulder (tinting)
            shoulder_spread = float(np.max(shoulder_rgb) - np.min(shoulder_rgb))
            
            # Fit 5-Parameter Logistic Curve (Richards curve)
            def logistic_5pl(x, dmin, dmax, k, x0, nu):
                # nu must be positive
                return dmin + (dmax - dmin) / np.power(1 + nu * np.exp(-k * (x - x0)), 1/nu)
            
            # Use log2 of scene luminance for fitting (EV)
            ev = np.log2(scene_luminance)
            p0 = [float(shadow_y), float(shoulder_y), 1.0, 0.0, 1.0]
            # bounds: nu > 0
            bounds = ([-np.inf, -np.inf, -np.inf, -np.inf, 0.001], 
                      [np.inf, np.inf, np.inf, np.inf, 100.0])
            try:
                popt, _ = curve_fit(logistic_5pl, ev, out_y, p0=p0, bounds=bounds, maxfev=20000)
                fit_dmin, fit_dmax, fit_k, fit_x0, fit_nu = popt
            except Exception as e:
                fit_dmin, fit_dmax, fit_k, fit_x0, fit_nu = (0.0, 1.0, 1.0, 0.0, 1.0)

            results.append({
                "film": film,
                "paper": paper,
                "shadow_floor_y": float(shadow_y),
                "shadow_spread": shadow_spread,
                "shadow_contrast": float(shadow_contrast),
                "look_white_y": float(look_white_y),
                "midtone_contrast": float(midtone_contrast),
                "shoulder_y": float(shoulder_y),
                "shoulder_spread": shoulder_spread,
                "highlight_contrast": float(highlight_contrast),
                "fit_dmin": float(fit_dmin),
                "fit_dmax": float(fit_dmax),
                "fit_k": float(fit_k),
                "fit_x0": float(fit_x0),
                "fit_nu": float(fit_nu)
            })
            
        except Exception as e:
            # Some combinations might not be supported or error out
            print(f"Failed {film} + {paper}: {e}")
            pass

# Output to JSON for further reading
with open("/Users/retriedstormtrooper/Documents/spektrafilm-main/curve_analysis.json", "w") as f:
    json.dump(results, f, indent=2)

print(f"Analyzed {len(results)} combinations.")
