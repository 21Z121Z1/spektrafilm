import numpy as np
from scipy.ndimage import gaussian_filter

from spektrafilm.utils.fast_stats import fast_lognormal_from_mean_std
from spektrafilm.utils.fast_gaussian_filter import fast_gaussian_filter


def _backend_supports_gpu_array(backend) -> bool:
    return backend is not None and bool(getattr(backend, "supports_gpu", False))


def _backend_supports_gpu_stochastic(backend) -> bool:
    return (
        _backend_supports_gpu_array(backend)
        and (hasattr(backend, "mx") or hasattr(backend, "cp"))
    )


def add_glare(xyz: np.ndarray, illuminant_xyz: np.ndarray, glare, backend=None) -> np.ndarray:
    if glare is not None and glare.active and glare.percent > 0:
        glare_amount = compute_random_glare_amount(
            glare.percent,
            glare.roughness,
            glare.blur,
            xyz.shape[:2],
            backend=backend,
        )
        if _backend_supports_gpu_array(backend):
            illuminant_xyz = backend.asarray(illuminant_xyz)
        xyz = xyz + glare_amount[:, :, None] * illuminant_xyz[None, None, :]
    return xyz

def compute_random_glare_amount(amount, roughness, blur, shape, backend=None):
    if _backend_supports_gpu_stochastic(backend):
        from spektrafilm.gpu.kernels.filters import gaussian_filter_backend
        from spektrafilm.gpu.kernels.grain import fast_lognormal_from_mean_std_backend

        if hasattr(backend, "mx"):
            ones = backend.mx.ones(shape, dtype=backend.mx.float32)
        elif hasattr(backend, "cp"):
            ones = backend.cp.ones(shape, dtype=backend.cp.float32)
        else:
            ones = backend.asarray(np.ones(shape, dtype=np.float32))
        mean = ones * amount
        std = ones * (roughness * amount)
        random_glare = fast_lognormal_from_mean_std_backend(mean, std, backend)
        if blur > 0:
            random_glare = gaussian_filter_backend(random_glare, blur, backend)
        return random_glare / 100

    random_glare = fast_lognormal_from_mean_std(amount*np.ones(shape),
                                                roughness*amount*np.ones(shape))
    # random_glare = gaussian_filter(random_glare, blur)
    random_glare = fast_gaussian_filter(random_glare, blur)
    random_glare /= 100
    return random_glare
