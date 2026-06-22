"""Test PQ forward/inverse roundtrip accuracy in isolation."""
from __future__ import annotations

import numpy as np
import colour

from spektrafilm.gpu.backend import select_backend
from spektrafilm.gpu.kernels.gamut_compress import (
    _eotf_inverse_st2084_jz_backend,
    _eotf_st2084_jz_backend,
)

backend = select_backend("mlx", precision="float32")

# LMS absolute values in cd/m² (typical SDR range 0.01 to 100)
lms = np.logspace(-2, 2, 1000).astype(np.float32)
lms = np.stack([lms, lms * 0.5, lms * 2.0], axis=-1)

# CPU reference via colour (which uses the same PQ formula)
from colour.models import eotf_inverse_ST2084, eotf_ST2084
lms_p_cpu = eotf_inverse_ST2084(lms)
lms_back_cpu = eotf_ST2084(lms_p_cpu)

# MLX backend
lms_b = backend.asarray(lms)
lms_p_mlx = _eotf_inverse_st2084_jz_backend(lms_b, backend)
lms_back_mlx = _eotf_st2084_jz_backend(lms_p_mlx, backend)

err_forward = np.max(np.abs(backend.to_numpy(lms_p_mlx) - lms_p_cpu))
err_roundtrip = np.max(np.abs(backend.to_numpy(lms_back_mlx) - lms))
print("MLX PQ forward error vs CPU:", err_forward)
print("MLX PQ roundtrip error vs input:", err_roundtrip)

# Relative errors
rel_forward = np.max(np.abs(backend.to_numpy(lms_p_mlx) - lms_p_cpu) / (np.abs(lms_p_cpu) + 1e-12))
rel_roundtrip = np.max(np.abs(backend.to_numpy(lms_back_mlx) - lms) / (np.abs(lms) + 1e-12))
print("MLX PQ forward relative error:", rel_forward)
print("MLX PQ roundtrip relative error:", rel_roundtrip)

# Find worst case
worst = np.unravel_index(np.argmax(np.abs(backend.to_numpy(lms_back_mlx) - lms)), lms.shape)
print("Worst input:", lms[worst[0], worst[1]])
print("Worst output:", backend.to_numpy(lms_back_mlx)[worst[0], worst[1]])
