import sys
from pathlib import Path
sys.path.insert(0, str(Path("src")))

import numpy as np
from spektrafilm.utils import hdr_photo

def evaluate_current():
    scene_y = np.array([0.5, 0.75, 1.0, 1.1, 1.25, 1.5, 2.0, 3.0, 4.0, 8.0, 16.0], dtype=np.float32)
    
    # 1. Print current rolloff output
    print("--- Current _paper_logistic_rolloff ---")
    rolled_y = hdr_photo._paper_logistic_rolloff(
        scene_y, 
        max_headroom=8.0, 
        start=1.0, 
        k=5.5, 
        x0=0.19, 
        exposure_scale=2.5
    )
    
    # 2. Print current graft blend
    print("--- Current Graft Blend (0.75 to 1.25) ---")
    blend = hdr_photo._smoothstep(0.75, 1.25, scene_y)
    
    print(f"{'scene_y':>10} | {'rolled_y':>10} | {'blend':>10} | {'is_boost':>10}")
    print("-" * 47)
    for s, r, b in zip(scene_y, rolled_y, blend):
        is_boost = "YES" if r > s else "no"
        print(f"{s:10.4f} | {r:10.4f} | {b:10.4f} | {is_boost:>10}")

if __name__ == "__main__":
    evaluate_current()
