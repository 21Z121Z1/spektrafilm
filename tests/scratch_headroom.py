import numpy as np
from spektrafilm.utils.hdr_photo import HDRPhotoMapping, prepare_hdr_photo_renditions, _content_headroom

height, width = 100, 100
np.random.seed(42)
sdr_image = np.random.uniform(0.1, 0.9, size=(height, width, 3)).astype(np.float32)
scene_y = np.random.lognormal(mean=0.0, sigma=2.0, size=(height, width)).astype(np.float32)
scene_y = np.clip(scene_y, 0.0, 100.0)
scene_y[0:10, 0:10] = 64.0
scene_y[10:20, 10:20] = 16.0
scene_y[20:30, 20:30] = 8.0

print(f"Max scene_y: {np.max(scene_y):.2f}")
print("---")

test_cases = [
    {"label": "Default", "kwargs": {}},
    {"label": "Low graft_strength (0.2)", "kwargs": {"graft_strength": 0.2}},
    {"label": "High graft_strength (1.0)", "kwargs": {"graft_strength": 1.0}},
    {"label": "Gentle Rolloff (exposure_scale=5.0)", "kwargs": {"paper_rolloff_exposure_scale": 5.0}},
    {"label": "Steep Rolloff (exposure_scale=1.5)", "kwargs": {"paper_rolloff_exposure_scale": 1.5}},
    {"label": "Low Max Headroom (4.0)", "kwargs": {"max_headroom": 4.0}},
    {"label": "High Max Headroom (32.0)", "kwargs": {"max_headroom": 32.0}},
]

for case in test_cases:
    mapping = HDRPhotoMapping(**case["kwargs"])
    renditions = prepare_hdr_photo_renditions(sdr_image, scene_luminance=scene_y, mapping=mapping)
    max_hdr_rgb_val = np.max(renditions.hdr_rgb)
    
    print(f"[{case['label']}]")
    print(f"  Resulting Headroom (Metadata): {renditions.headroom:.4f}")
    print(f"  Max HDR pixel value: {max_hdr_rgb_val:.4f}")
    print(f"  mapping.max_headroom: {mapping.max_headroom:.4f}")
    print("---")
