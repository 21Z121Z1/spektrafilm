import argparse
import json
import math
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

# Adjust sys.path to find spektrafilm package
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from spektrafilm.runtime.api import init_params, digest_params, Simulator

def to_np(arr):
    if hasattr(arr, "get"):
        return arr.get()
    if hasattr(arr, "numpy"):
        return arr.numpy()
    return np.asarray(arr)

def get_y(arr):
    arr = to_np(arr)
    # Just take max across channels if 3 channels, else assume 1 channel or mean
    if len(arr.shape) == 3 and arr.shape[2] >= 3:
        # Simple luminance proxy: mean or max. Let's use max for headroom, or standard Y.
        # Here we'll just use mean for density, and standard luma for RGB if we want.
        # But simple mean is fine for general stat.
        return np.mean(arr, axis=2)
    return arr

def compute_stats(name, arr):
    arr = to_np(arr)
    flat = arr.flatten()
    if len(flat) == 0:
        return {}
    flat = flat[np.isfinite(flat)]
    if len(flat) == 0:
        return {}
    
    return {
        "p0": float(np.min(flat)),
        "p1": float(np.percentile(flat, 1)),
        "p5": float(np.percentile(flat, 5)),
        "p10": float(np.percentile(flat, 10)),
        "p25": float(np.percentile(flat, 25)),
        "p50": float(np.percentile(flat, 50)),
        "p75": float(np.percentile(flat, 75)),
        "p90": float(np.percentile(flat, 90)),
        "p95": float(np.percentile(flat, 95)),
        "p99": float(np.percentile(flat, 99)),
        "p99.9": float(np.percentile(flat, 99.9)),
        "max": float(np.max(flat)),
        "frac_gt_0_18": float(np.mean(flat > 0.18)),
        "frac_gt_1": float(np.mean(flat > 1.0)),
        "frac_gt_2": float(np.mean(flat > 2.0)),
        "frac_gt_4": float(np.mean(flat > 4.0)),
        "finite_fraction": float(np.mean(np.isfinite(arr.flatten()))),
        "negative_fraction": float(np.mean(flat < 0.0)),
        "zero_fraction": float(np.mean(flat == 0.0)),
    }

def run_pipeline_and_extract_stages(simulator, image):
    pipeline = simulator._pipeline
    
    # 1. Preprocess and metadata
    img_array = pipeline._runtime_array(image)
    preprocessed, metadata = pipeline._preprocess_input_image_with_metadata(img_array)
    scene_y = metadata.scene_luminance
    
    # 2. Film Expose
    log_raw_film = pipeline._runtime_array(pipeline._filming_stage.expose(preprocessed))
    
    # 3. Film Develop
    cmy_film = pipeline._runtime_array(pipeline._filming_stage.develop(log_raw_film))
    
    # 4. Print Expose
    log_raw_print = pipeline._runtime_array(pipeline._printing_stage.expose(cmy_film))
    
    # 5. Print Develop
    cmy_print = pipeline._runtime_array(pipeline._printing_stage.develop(log_raw_print))
    
    # 6. Scan
    rgb_scan = pipeline._runtime_array(pipeline._scanning_stage.scan(cmy_print, output_encoding=pipeline._output_encoding))
    
    return {
        "input_rgb": image,
        "preprocessed_rgb": to_np(preprocessed),
        "scene_y": to_np(scene_y),
        "log_raw_film": to_np(log_raw_film),
        "cmy_film": to_np(cmy_film),
        "log_raw_print": to_np(log_raw_print),
        "cmy_print": to_np(cmy_print),
        "rgb_scan": to_np(rgb_scan),
    }

def generate_ramp_image(w=1024):
    # Log-spaced ramp from 0.001 to 64.0
    ramp = np.logspace(math.log10(0.001), math.log10(64.0), w, dtype=np.float32)
    # Shape it into (H, W, 3)
    img = np.tile(ramp, (100, 1))
    return np.stack((img, img, img), axis=-1)

def generate_diffuse_white_image(h=100, w=100):
    # Mean 1.0, some noise
    img = np.random.normal(1.0, 0.05, (h, w)).astype(np.float32)
    return np.stack((img, img, img), axis=-1)

def process_and_save(simulator, name, image, out_dir):
    prefix = out_dir / name
    stages = run_pipeline_and_extract_stages(simulator, image)
    
    # Save stats
    all_stats = {}
    for stage_name, data in stages.items():
        all_stats[stage_name] = compute_stats(stage_name, get_y(data))
        
    with open(f"{prefix}_stats.json", "w") as f:
        json.dump(all_stats, f, indent=2)
        
    # If it's a ramp, plot the transfer curves
    if "ramp" in name:
        # scene_y is calculated per pixel. We can just take the middle row.
        sy = stages["scene_y"][50, :]
        input_y = np.mean(stages["input_rgb"][50, :], axis=-1)
        look_y = np.mean(stages["rgb_scan"][50, :], axis=-1)
        
        cmy_film_y = np.mean(stages["cmy_film"][50, :], axis=-1)
        cmy_print_y = np.mean(stages["cmy_print"][50, :], axis=-1)
        
        plt.figure(figsize=(10, 6))
        plt.plot(sy, look_y, label='scene_y -> final look_y', color='blue')
        plt.plot(sy, sy, '--', color='gray', label='Linear')
        plt.xscale('log', base=2)
        plt.yscale('log', base=2)
        plt.xlabel('Scene Y (EV relative to 1.0)')
        plt.ylabel('Output Look Y')
        plt.title('End-to-End Transfer Curve')
        plt.legend()
        plt.grid(True, which="both", ls="--", alpha=0.5)
        plt.savefig(f"{prefix}_transfer_curve.png")
        plt.close()
        
        # Density curve
        plt.figure(figsize=(10, 6))
        plt.plot(sy, cmy_film_y, label='Film Density (CMY mean)', color='orange')
        plt.plot(sy, cmy_print_y, label='Print Density (CMY mean)', color='green')
        plt.xscale('log', base=2)
        plt.xlabel('Scene Y (EV)')
        plt.ylabel('Density')
        plt.title('Density Curves')
        plt.legend()
        plt.grid(True, which="both", ls="--", alpha=0.5)
        plt.savefig(f"{prefix}_density_curve.png")
        plt.close()
        
        # Output specific values for report
        vals = [0.184, 1.0, 2.0, 4.0, 8.0, 16.0]
        with open(out_dir / "key_measurements.txt", "w") as f:
            for v in vals:
                # find closest scene_y
                idx = np.abs(sy - v).argmin()
                f.write(f"scene_y={v} -> look_y = {look_y[idx]:.4f}\n")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="debug/pipeline_luminance", help="Output directory")
    args = parser.parse_args()
    
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize simulator with default profiles
    print("Initializing simulator...")
    # Use standard Kodak profiles
    params = init_params(film_profile="kodak_portra_400", print_profile="kodak_portra_endura")
    # Speed up by disabling grain and halation if they slow it down, or keep them to be accurate.
    # We will keep default for accuracy.
    params = digest_params(params)
    simulator = Simulator(params)
    
    # 1. Ramp
    print("Processing Ramp...")
    ramp_img = generate_ramp_image()
    process_and_save(simulator, "ramp", ramp_img, out_dir)
    
    # 2. Diffuse White
    print("Processing Diffuse White...")
    dw_img = generate_diffuse_white_image()
    process_and_save(simulator, "diffuse_white", dw_img, out_dir)
    
    # 3. Specular Patch
    print("Processing Specular Patch...")
    h, w = 100, 100
    spec_img = np.full((h, w, 3), 0.184, dtype=np.float32)
    spec_img[40:60, 40:60] = 8.0
    process_and_save(simulator, "specular", spec_img, out_dir)
    
    print(f"Diagnostics saved to {out_dir}")

if __name__ == "__main__":
    main()
