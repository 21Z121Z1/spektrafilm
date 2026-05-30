import sys
import os
import numpy as np
import scipy.ndimage

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import mlx.core as mx

# 1. Test LUT Trilinear precision
from spektrafilm.gpu.kernels.lut import apply_lut_trilinear_3d_mlx, apply_lut_trilinear_3d_numpy

def test_lut_precision():
    print("--- Testing 3D LUT Precision ---")
    size = 17
    lut = np.random.rand(size, size, size, 3).astype(np.float32)
    image = np.random.rand(256, 256, 3).astype(np.float32)

    out_numpy = apply_lut_trilinear_3d_numpy(lut, image)
    
    out_mlx = apply_lut_trilinear_3d_mlx(lut, image, mx=mx)
    out_mlx_np = np.array(out_mlx.tolist()) if hasattr(out_mlx, 'tolist') else np.array(out_mlx)
    
    diff = np.abs(out_numpy - out_mlx_np)
    max_diff = np.max(diff)
    print(f"LUT Max absolute difference: {max_diff:.8f}")
    assert max_diff < 1e-4, f"LUT Precision failed: {max_diff}"
    print("LUT Precision OK.")


# 2. Test Highlight Boost precision
from spektrafilm.gpu.kernels.color import boost_highlights_backend
from spektrafilm.utils.numba_boost_hightlights import boost_highlights

def test_boost_precision():
    print("\n--- Testing Highlight Boost Precision ---")
    # Using scene linear values
    x = (np.random.rand(256, 256, 3).astype(np.float32) * 5.0)
    
    # Numba reference
    out_numba = boost_highlights(x.copy(), 2.0, 0.5, 0.5)
    
    # MLX new version
    import spektrafilm.gpu.mlx_backend as backend
    be = backend.MlxBackend()
    
    x_mx = be.asarray(x)
    out_mlx = boost_highlights_backend(x_mx, 2.0, 0.5, 0.5, be)
    out_mlx_np = be.to_numpy(out_mlx)
    
    diff = np.abs(out_numba - out_mlx_np)
    max_diff = np.max(diff)
    print(f"Boost Max absolute difference: {max_diff:.8f}")
    
    # The numba kernel and the new MLX kernel use exactly the same math, 
    # except the numba kernel syncs on max(x) and does exact branches.
    # The new MLX kernel uses soft conditions (denom > 0)
    assert max_diff < 1e-4, f"Boost Precision failed: {max_diff}"
    print("Highlight Boost Precision OK.")

if __name__ == '__main__':
    test_lut_precision()
    test_boost_precision()
    print("\nAll precision tests passed successfully!")
