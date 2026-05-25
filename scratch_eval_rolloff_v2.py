import sys
import math
from pathlib import Path
sys.path.insert(0, str(Path("src")))

import numpy as np

def _paper_logistic_progress(scene_y, start, k, x0, contrast, exposure_scale):
    eps = np.float32(1e-8)
    y = np.maximum(np.asarray(scene_y, dtype=np.float32), 0.0)
    s = np.float32(max(start, eps))
    out = np.zeros_like(y)
    
    above = y > s
    if not np.any(above):
        return out

    x = np.log2(np.maximum(y[above], eps) / s) / np.float32(max(exposure_scale, eps))
    k_f = np.float32(k)
    x0_f = np.float32(x0)
    raw = np.float32(1.0) / (np.float32(1.0) + np.exp(-k_f * (x - x0_f)))
    raw0 = float(1.0 / (1.0 + math.exp(-k * (0.0 - x0))))
    progress = np.clip((raw - np.float32(raw0)) / np.float32(max(1.0 - raw0, 1e-8)), 0.0, 1.0)
    
    if contrast != 1.0:
        progress = np.power(progress, np.float32(contrast))
    
    out[above] = progress
    return out

def _compression_core(scene_y, progress, start, max_headroom):
    eps = np.float32(1e-8)
    y = np.maximum(np.asarray(scene_y, dtype=np.float32), 0.0)
    s = np.float32(max(start, eps))
    h = np.float32(max(max_headroom, 1.0))
    out = y.copy()

    above = y > s
    if not np.any(above):
        return np.minimum(out, h)

    excess = y[above] - s
    range_ = np.maximum(h - s, eps)
    compression = np.float32(1.0) + progress[above] * (excess / range_)
    
    rolled_y = s + excess / compression
    out[above] = rolled_y
    return np.minimum(out, h)

def _smoothstep(edge0, edge1, value):
    t = np.clip((value - np.float32(edge0)) / np.float32(edge1 - edge0), 0.0, 1.0)
    return t * t * (np.float32(3.0) - np.float32(2.0) * t)

def evaluate_current():
    scene_y = np.array([0.5, 0.75, 1.0, 1.1, 1.25, 1.5, 2.0, 3.0, 4.0, 8.0, 16.0], dtype=np.float32)
    
    start = 1.0
    max_headroom = 8.0
    k = 5.5
    x0 = 0.19
    exposure_scale = 2.5
    contrast = 1.0
    
    progress = _paper_logistic_progress(scene_y, start, k, x0, contrast, exposure_scale)
    rolled_y = _compression_core(scene_y, progress, start, max_headroom)
    
    graft_start = 1.0
    graft_end = 4.0
    graft_strength = 0.5
    
    log2_y = np.log2(np.maximum(scene_y, 1e-8))
    log2_start = np.log2(np.float32(graft_start))
    log2_end = np.log2(np.float32(graft_end))
    blend = _smoothstep(log2_start, log2_end, log2_y) * graft_strength

    print(f"{'scene_y':>10} | {'progress':>10} | {'rolled_y':>10} | {'blend':>10}")
    print("-" * 47)
    for s, p, r, b in zip(scene_y, progress, rolled_y, blend):
        print(f"{s:10.4f} | {p:10.4f} | {r:10.4f} | {b:10.4f}")

if __name__ == "__main__":
    evaluate_current()
