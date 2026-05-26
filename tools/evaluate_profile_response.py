import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

# Adjust sys.path to find spektrafilm package
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from spektrafilm.runtime.params_builder import init_params, digest_params
from spektrafilm.runtime.pipeline import SimulationPipeline
from spektrafilm.utils import hdr_photo

def _smoothstep(edge0: float, edge1: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)

def prototype_profile_aware_graft(
    look_rgb: np.ndarray,
    scene_y: np.ndarray,
    mapping: hdr_photo.HDRPhotoMapping,
    look_diffuse: float
):
    eps = np.float32(1e-8)
    look = np.maximum(np.asarray(look_rgb, dtype=np.float32), 0.0)
    look_y = np.max(look, axis=2)
    scene_y = np.maximum(np.asarray(scene_y, dtype=np.float32), eps)

    # Diffuse Lift
    log2_y = np.log2(scene_y)
    log2_d_start = np.log2(np.float32(mapping.hdr_diffuse_lift_start))
    log2_d_end = np.log2(np.float32(mapping.hdr_diffuse_lift_end))
    diffuse_w = _smoothstep(log2_d_start, log2_d_end, log2_y) * np.float32(mapping.hdr_diffuse_lift_strength)

    # Profile-derived target
    diffuse_gain = np.float32(mapping.hdr_diffuse_white_target) / np.float32(max(look_diffuse, 1e-8))
    diffuse_target_y = look_y * (1.0 + diffuse_w * (diffuse_gain - 1.0))

    # Specular Rolloff (Profile-aware)
    # The profile shoulder limits how much `scene_y` can be added without looking fake,
    # but for this prototype, we'll use the profile's paper rolloff shape.
    rolled_y = hdr_photo._apply_rolloff(scene_y, mapping=mapping)

    log2_graft_start = np.log2(np.float32(mapping.graft_start))
    log2_graft_end = np.log2(np.float32(mapping.graft_end))
    w_spec = _smoothstep(log2_graft_start, log2_graft_end, log2_y) * np.float32(mapping.graft_strength)

    # Target HDR Y
    specular_delta = np.maximum(rolled_y - diffuse_target_y, np.float32(0.0))
    target_y = diffuse_target_y + w_spec * specular_delta

    return target_y

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="debug/profile_evaluation", help="Output directory")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Initializing pipeline with Kodak Portra 400 + Endura...")
    params = init_params("kodak_portra_400", "kodak_portra_endura")
    # Deactivate stochastic and spatial effects for clean curve
    params.debug.deactivate_stochastic_effects = True
    params.debug.deactivate_spatial_effects = True
    params = digest_params(params)

    pipeline = SimulationPipeline(params)

    # Generate neutral ramp and characterize
    print("Characterizing profile...")
    from spektrafilm.runtime.pipeline import characterize_pipeline_profile
    scene_y_1d, look_y_1d = characterize_pipeline_profile(pipeline)
    w = len(scene_y_1d)

    # We still need the output image to pass into hdr_photo methods for comparison
    pipeline._resize_service.pixel_size_um = 10.0
    ramp_rgb = np.repeat(scene_y_1d.reshape(1, w, 1), 3, axis=2)
    ramp_rgb_backend = pipeline._runtime_array(ramp_rgb)
    if pipeline.io.scan_film:
        result_rgb = np.asarray(pipeline._array_backend.to_numpy(pipeline._pipeline_scan_film(ramp_rgb_backend)), dtype=np.float32)
    else:
        result_rgb = np.asarray(pipeline._array_backend.to_numpy(pipeline._pipeline_print(ramp_rgb_backend)), dtype=np.float32)
    look_rgb = np.maximum(result_rgb, 0.0)

    # Extract look_diffuse (F_profile(1.0))
    # Find index closest to 1.0
    idx_1 = np.argmin(np.abs(scene_y_1d - 1.0))
    look_diffuse = look_y_1d[idx_1]
    print(f"Profile look_y at scene_y=1.0: {look_diffuse:.4f}")

    # Calculate fixed HDR mapping
    mapping = hdr_photo.HDRPhotoMapping()

    # Fixed mapping calculation using internal hdr_photo functions
    renditions = hdr_photo.prepare_hdr_photo_renditions(look_rgb, mapping=mapping, scene_luminance=scene_y_1d.reshape(1, w))
    fixed_hdr_y = np.max(renditions.hdr_rgb[0], axis=1)

    # Profile-aware mapping
    profile_hdr_y = prototype_profile_aware_graft(
        look_rgb,
        scene_y_1d.reshape(1, w),
        mapping,
        look_diffuse
    )[0]

    # Plotting
    plt.figure(figsize=(10, 8))

    # Plot Identity
    plt.plot(scene_y_1d, scene_y_1d, '--', color='gray', label='Scene Linear (Identity)')

    # Plot Profile Response
    plt.plot(scene_y_1d, look_y_1d, '-', color='black', linewidth=2, label='Profile look_y (SDR limited)')

    # Plot Fixed HDR
    plt.plot(scene_y_1d, fixed_hdr_y, '-', color='red', label='Current Fixed HDR (Unaware)')

    # Plot Profile-Aware HDR
    plt.plot(scene_y_1d, profile_hdr_y, '--', color='green', linewidth=2, label='Profile-Aware HDR (Prototype)')

    plt.axhline(mapping.max_headroom, color='magenta', linestyle=':', label='Max Headroom')
    plt.axvline(1.0, color='blue', linestyle=':', label='Diffuse White (1.0)')

    # Mark the diffuse lift point
    plt.plot(1.0, look_diffuse, 'ko')
    plt.annotate(f' look_diffuse: {look_diffuse:.2f}', (1.0, look_diffuse), xytext=(10, -10), textcoords='offset points')

    plt.xscale('log', base=2)
    plt.yscale('log', base=2)
    plt.xlabel('Scene Y (EV relative to diffuse white)')
    plt.ylabel('Output Y')
    plt.title('Profile Response vs HDR Mapping')
    plt.legend()
    plt.grid(True, which="both", ls="--", alpha=0.5)

    out_path = out_dir / "profile_response_comparison.png"
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()
    print(f"Saved plot to {out_path}")

if __name__ == "__main__":
    main()
