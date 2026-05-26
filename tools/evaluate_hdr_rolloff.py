import argparse
import json
import os
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

# Adjust sys.path to find spektrafilm package
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from spektrafilm.utils import hdr_photo

def _smoothstep(edge0: float, edge1: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)

def plot_rolloff_curve(out_dir: Path, mapping: hdr_photo.HDRPhotoMapping):
    scene_y = np.array([
        0.01, 0.18, 0.5, 0.75, 1.0,
        1.1, 1.25, 1.5, 2.0,
        3.0, 4.0, 8.0, 16.0, 32.0, 64.0
    ], dtype=np.float32)

    # Generate fine-grained points for a smooth plot
    scene_y_fine = np.logspace(-2, 6, 500, base=2, dtype=np.float32)

    rolled_y_fine = hdr_photo._apply_rolloff(scene_y_fine, mapping=mapping)

    look_y_fine = np.minimum(scene_y_fine, 0.8) # simple SDR look mock

    log2_start = np.log2(np.float32(mapping.graft_start))
    log2_end = np.log2(np.float32(mapping.graft_end))
    log2_y = np.log2(np.maximum(scene_y_fine, 1e-8))
    diffuse_start = np.log2(np.float32(mapping.hdr_diffuse_lift_start))
    diffuse_end = np.log2(np.float32(mapping.hdr_diffuse_lift_end))
    diffuse_w = _smoothstep(diffuse_start, diffuse_end, log2_y) * mapping.hdr_diffuse_lift_strength

    # default look_white roughly 0.8387
    look_white = 0.8387
    paper_white_gain = mapping.hdr_diffuse_white_target / look_white
    diffuse_target_y_fine = look_y_fine * (1.0 + diffuse_w * (paper_white_gain - 1.0))

    w = _smoothstep(log2_start, log2_end, log2_y) * mapping.graft_strength
    target_y_fine = diffuse_target_y_fine + w * np.maximum(rolled_y_fine - diffuse_target_y_fine, 0.0)

    # Calculate slope
    slope_x = (scene_y_fine[1:] + scene_y_fine[:-1]) / 2
    slope_y = np.diff(rolled_y_fine) / np.diff(scene_y_fine)

    plt.figure(figsize=(10, 8))
    plt.subplot(2, 1, 1)
    plt.plot(scene_y_fine, scene_y_fine, '--', color='gray', label='Linear (Identity)')
    plt.plot(scene_y_fine, rolled_y_fine, '-', color='blue', label='Rolled Y')
    plt.plot(scene_y_fine, diffuse_target_y_fine, '--', color='orange', label='Diffuse Target Y')
    plt.plot(scene_y_fine, target_y_fine, '-', color='red', label='Final Target Y (Merge)')
    plt.axhline(mapping.max_headroom, color='r', linestyle=':', label='Max Headroom')
    plt.xscale('log', base=2)
    plt.yscale('log', base=2)
    plt.xlabel('Scene Y (EV relative to diffuse white)')
    plt.ylabel('Output Y')
    plt.title('HDR Paper Rolloff Transfer Function')
    plt.legend()
    plt.grid(True, which="both", ls="--", alpha=0.5)

    plt.subplot(2, 1, 2)
    plt.plot(slope_x, slope_y, '-', color='green', label='Slope (dRolled / dScene)')
    plt.xscale('log', base=2)
    plt.ylim(-0.1, 1.1)
    plt.xlabel('Scene Y (EV)')
    plt.ylabel('Local Slope')
    plt.title('Derivative of Rolloff')
    plt.legend()
    plt.grid(True, which="both", ls="--", alpha=0.5)

    plt.tight_layout()
    plt.savefig(out_dir / "rolloff_curve.png", dpi=150)
    plt.close()

    # Output CSV for specific sample points
    rolled_y = hdr_photo._apply_rolloff(scene_y, mapping=mapping)
    log2_y_sample = np.log2(np.maximum(scene_y, 1e-8))
    w_sample = _smoothstep(log2_start, log2_end, log2_y_sample) * mapping.graft_strength
    look_y = np.minimum(scene_y, 0.8)
    diffuse_w_sample = _smoothstep(diffuse_start, diffuse_end, log2_y_sample) * mapping.hdr_diffuse_lift_strength
    diffuse_target_y_sample = look_y * (1.0 + diffuse_w_sample * (paper_white_gain - 1.0))
    target_y = diffuse_target_y_sample + w_sample * np.maximum(rolled_y - diffuse_target_y_sample, 0.0)

    with open(out_dir / "rolloff_curve.csv", "w") as f:
        f.write("scene_y,rolled_y,blend_w,target_y,look_y\n")
        for s, r, w_val, t, l in zip(scene_y, rolled_y, w_sample, target_y, look_y):
            f.write(f"{s:.4f},{r:.4f},{w_val:.4f},{t:.4f},{l:.4f}\n")

def compute_stats(name, arr):
    if len(arr) == 0:
        return {}
    return {
        "p50": float(np.median(arr)),
        "p90": float(np.percentile(arr, 90)),
        "p95": float(np.percentile(arr, 95)),
        "p99": float(np.percentile(arr, 99)),
        "p99.9": float(np.percentile(arr, 99.9)),
        "max": float(np.max(arr))
    }

def process_synthetic_image(name: str, look_rgb: np.ndarray, scene_luminance: np.ndarray, mapping: hdr_photo.HDRPhotoMapping, out_dir: Path):
    prefix = out_dir / name

    eps = np.float32(1e-8)
    scene_y = np.maximum(scene_luminance, eps)
    look_y = np.maximum(np.max(look_rgb, axis=2), eps)

    renditions = hdr_photo.prepare_hdr_photo_renditions(look_rgb, mapping=mapping, scene_luminance=scene_luminance)

    hdr_rgb = renditions.hdr_rgb
    hdr_y = np.max(hdr_rgb, axis=2)
    sdr_y = np.maximum(np.max(renditions.sdr_rgb, axis=2), eps)

    gain = hdr_y / sdr_y
    headroom = renditions.headroom

    rolled_y = hdr_photo._apply_rolloff(scene_y, mapping=mapping)
    log2_start = np.log2(np.float32(mapping.graft_start))
    log2_end = np.log2(np.float32(mapping.graft_end))
    log2_y = np.log2(scene_y)
    blend = _smoothstep(log2_start, log2_end, log2_y) * mapping.graft_strength

    target_y = (1.0 - blend) * look_y + blend * rolled_y

    stats = {
        "scene_y": {**compute_stats("scene_y", scene_y), "frac_gt_1": float(np.mean(scene_y > 1.0)), "frac_gt_2": float(np.mean(scene_y > 2.0)), "frac_gt_4": float(np.mean(scene_y > 4.0))},
        "rolled_y": compute_stats("rolled_y", rolled_y),
        "blend": compute_stats("blend", blend),
        "gain": {**compute_stats("gain", gain), "max_gain": float(np.max(gain))},
        "headroom": float(headroom),
        "frac_near_headroom": float(np.mean(hdr_y >= 0.99 * headroom))
    }

    with open(f"{prefix}_stats.json", "w") as f:
        json.dump(stats, f, indent=2)

    plt.figure()
    plt.imshow(look_rgb)
    plt.title("SDR Preview")
    plt.savefig(f"{prefix}_sdr_preview.png")
    plt.close()

    plt.figure()
    plt.imshow(gain, cmap='inferno', vmin=1.0, vmax=float(mapping.max_headroom))
    plt.colorbar()
    plt.title("Gain Heatmap")
    plt.savefig(f"{prefix}_gain_heatmap.png")
    plt.close()

    mask = hdr_y >= 0.99 * headroom
    plt.figure()
    plt.imshow(mask, cmap='gray')
    plt.title("Near Headroom Mask")
    plt.savefig(f"{prefix}_near_headroom_mask.png")
    plt.close()

def run_synthetic_tests(out_dir: Path, mapping: hdr_photo.HDRPhotoMapping):
    # 1. Ramp
    w = 1000
    ramp_scene = np.linspace(0.01, 16.0, w).reshape(1, w).astype(np.float32)
    ramp_look = np.minimum(ramp_scene, 0.8)
    ramp_look_rgb = np.repeat(ramp_look[:, :, np.newaxis], 3, axis=2)
    process_synthetic_image("1_ramp", ramp_look_rgb, ramp_scene, mapping, out_dir)

    # 2. Diffuse White (1.0) with some noise
    h, w = 100, 100
    dw_scene = np.random.normal(1.0, 0.05, (h, w)).astype(np.float32)
    # Ensure it passes the SDR-only check by adding a small block of bright pixels (25 pixels > 0.1% of 10000)
    dw_scene[0:5, 0:5] = 2.0
    dw_look_rgb = np.full((h, w, 3), 0.8, dtype=np.float32)
    process_synthetic_image("2_diffuse_white", dw_look_rgb, dw_scene, mapping, out_dir)

    # 3. Small specular
    spec_scene = np.ones((h, w), dtype=np.float32)
    spec_scene[40:60, 40:60] = 8.0
    spec_look = np.ones((h, w, 3), dtype=np.float32) * 0.8
    process_synthetic_image("3_specular", spec_look, spec_scene, mapping, out_dir)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_exr", nargs="?", help="Input EXR file (optional)")
    parser.add_argument("--scene-luminance", help="Numpy array for scene luminance")
    parser.add_argument("--out", default="debug", help="Output directory")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    mapping = hdr_photo.HDRPhotoMapping(max_headroom=8.0, hdr_diffuse_white_target=1.5)

    plot_rolloff_curve(out_dir, mapping)
    print(f"Saved curve plots to {out_dir}/rolloff_curve.png and .csv")

    if args.input_exr and args.scene_luminance:
        print("Real image evaluation is not yet fully implemented with ImageIO.")
    else:
        print("Running synthetic tests...")
        run_synthetic_tests(out_dir, mapping)
        print(f"Synthetic test results saved to {out_dir}")

if __name__ == "__main__":
    main()
