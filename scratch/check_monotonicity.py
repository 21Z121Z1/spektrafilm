import numpy as np
import sys
sys.path.insert(0, 'src')
from spektrafilm.utils.hdr_curve_profiles import _smoothstep

def test_curve():
    scene = np.linspace(0.1, 16.0, 1000)
    # mock SDR curve: simple shoulder
    sdr = 1.0 - np.exp(-scene)
    look_white = 1.0 - np.exp(-1.0) # ~0.63
    target_white = 1.0
    lift_start = 0.35
    lift_end = 1.0
    lift_strength = 0.9
    max_headroom = 8.0
    exposure_scale = 2.5
    rolloff_k = 5.5
    graft_start = 1.0
    graft_end = 4.0
    graft_strength = 1.0

    log_scene = np.log2(scene)
    diffuse_w = _smoothstep(np.log2(lift_start), np.log2(lift_end), log_scene)
    diffuse_w = np.clip(diffuse_w * lift_strength, 0.0, 1.0)
    diffuse_branch = sdr * (target_white / look_white)
    diffuse_target = sdr + diffuse_w * (diffuse_branch - sdr)

    shoulder_input = np.maximum(scene - 1.0, 0.0)
    denom = max_headroom * exposure_scale / (rolloff_k / 5.5)
    highlight = 1.0 + (max_headroom - 1.0) * (1.0 - np.exp(-shoulder_input / denom))

    spec_w = _smoothstep(np.log2(graft_start), np.log2(graft_end), log_scene)
    spec_w = np.clip(spec_w * graft_strength, 0.0, 1.0)
    hdr = diffuse_target + spec_w * np.maximum(highlight - diffuse_target, 0.0)

    diffs = np.diff(hdr)
    non_monotonic = np.sum(diffs < -1e-5)
    print(f"Non-monotonic points: {non_monotonic}")
    if non_monotonic > 0:
        print("Dips:")
        for i in range(len(diffs)):
            if diffs[i] < -1e-5:
                print(f"scene={scene[i]:.2f}, hdr={hdr[i]:.4f}, next_hdr={hdr[i+1]:.4f}")

    flat_spots = np.sum(np.abs(diffs) < 1e-4)
    print(f"Flat spots (diff < 1e-4): {flat_spots}")

if __name__ == '__main__':
    test_curve()
