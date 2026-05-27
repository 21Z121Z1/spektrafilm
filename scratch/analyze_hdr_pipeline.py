import os
import sys
import numpy as np
import json
sys.path.insert(0, '/Users/retriedstormtrooper/Documents/spektrafilm-main/src')

from spektrafilm.runtime.params_builder import digest_params, init_params
from spektrafilm.runtime.process import Simulator
from spektrafilm.utils.raw_file_processor import load_and_process_raw_file
from spektrafilm.utils.hdr_photo import prepare_hdr_photo_renditions, HDRPhotoMapping, build_profile_preserving_hdr_curve, _resolve_curve_profile, _prepare_scene_luminance
from spektrafilm.utils.hdr_curve_profiles import profile_relative_hdr_gain_ev, profile_slope_loglog, evaluate_profile_sdr_curve, luminance_y

def main():
    print("Loading RAW file...")
    raw_path = "/Users/retriedstormtrooper/Documents/spektrafilm-main/scratch/IMG_9121_converted.DNG"
    if not os.path.exists(raw_path):
        print(f"Error: {raw_path} not found.")
        return

    # Load RAW in ACES scene linear
    res = load_and_process_raw_file(
        raw_path, 
        white_balance='as_shot', 
        output_colorspace="ACES2065-1", 
        return_diagnostics=True
    )
    rgb_aces = res.image
    diagnostics = res.diagnostics
    diffuse_white = diagnostics.diffuse_white_estimate
    print(f"RAW diffuse_white_estimate: {diffuse_white}")
    
    print("Setting up simulator...")
    params = init_params(film_profile="kodak_portra_400", print_profile="kodak_portra_endura") # Use some defaults or check GUI
    params.debug.deactivate_spatial_effects = True
    params.debug.deactivate_stochastic_effects = True
    params.io.full_image = True
    params = digest_params(params)
    
    sim = Simulator(params)
    
    print("Processing via Simulator...")
    res_meta = sim.process_with_metadata(rgb_aces)
    look_rgb = res_meta.image
    hdr_scene_energy = res_meta.hdr_scene_energy
    
    scene_luminance = hdr_scene_energy.scene_luminance if hdr_scene_energy else None
    scene_rgb = hdr_scene_energy.scene_rgb if hdr_scene_energy else None
    
    # 获取 diffuse white estimate
    diffuse_white = hdr_scene_energy.diffuse_white_estimate if hdr_scene_energy else diagnostics.diffuse_white_estimate
    scene_luminance = np.asarray(scene_luminance, dtype=np.float32)
    
    print(f"Look RGB shape: {look_rgb.shape}, Scene Luminance shape: {scene_luminance.shape}")
    
    # 1. Check Scene Luminance distribution
    flat_scene = scene_luminance.flatten()
    print("Scene Luminance p50:", np.percentile(flat_scene, 50.0))
    print("Scene Luminance p90:", np.percentile(flat_scene, 90.0))
    print("Scene Luminance p99:", np.percentile(flat_scene, 99.0))
    print("Scene Luminance p99.9:", np.percentile(flat_scene, 99.9))
    
    mapping = HDRPhotoMapping(
        hdr_mapping_mode="profile_aware",
        film="kodak_portra_400",
        paper="kodak_portra_endura",
        diffuse_white=diffuse_white,
        hdr_highlight_color_mode="bounded_look_chroma"
    )
    
    print("Preparing HDR Photo Renditions...")
    renditions = prepare_hdr_photo_renditions(
        look_rgb,
        mapping=mapping,
        scene_luminance=scene_luminance,
        scene_rgb=rgb_aces
    )
    
    print(f"HDR Renditions headroom: {renditions.headroom}")
    print(f"Diagnostics: {renditions.diagnostics}")
    
    hdr_rgb = renditions.hdr_rgb
    sdr_rgb = renditions.sdr_rgb
    
    # Analyze brightness distribution
    hdr_luma = luminance_y(hdr_rgb).flatten()
    sdr_luma = luminance_y(sdr_rgb).flatten()
    
    results = {
        "headroom": renditions.headroom,
        "diffuse_white": diffuse_white,
        "hdr_luma_percentiles": {
            "p50": float(np.percentile(hdr_luma, 50.0)),
            "p90": float(np.percentile(hdr_luma, 90.0)),
            "p95": float(np.percentile(hdr_luma, 95.0)),
            "p99": float(np.percentile(hdr_luma, 99.0)),
            "p99.9": float(np.percentile(hdr_luma, 99.9)),
            "max": float(np.max(hdr_luma))
        },
        "sdr_luma_percentiles": {
            "p50": float(np.percentile(sdr_luma, 50.0)),
            "p90": float(np.percentile(sdr_luma, 90.0)),
            "p95": float(np.percentile(sdr_luma, 95.0)),
            "p99": float(np.percentile(sdr_luma, 99.0)),
            "p99.9": float(np.percentile(sdr_luma, 99.9)),
            "max": float(np.max(sdr_luma))
        }
    }
    
    # Save to file
    with open('/Users/retriedstormtrooper/Documents/spektrafilm-main/scratch/hdr_analysis_data.json', 'w') as f:
        json.dump(results, f, indent=2)
    print("Done! Results saved.")

if __name__ == '__main__':
    main()
