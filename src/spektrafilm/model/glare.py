import numpy as np

from spektrafilm.utils.fast_stats import fast_lognormal_from_mean_std
from spektrafilm.utils.fast_gaussian_filter import fast_gaussian_filter


def add_glare(xyz: np.ndarray, illuminant_xyz: np.ndarray, glare) -> np.ndarray:
    if glare is not None and glare.active and glare.percent > 0:
        glare_amount = compute_random_glare_amount(
            glare.percent,
            glare.roughness,
            glare.blur,
            xyz.shape[:2],
        )
        xyz = xyz + glare_amount[:, :, None] * illuminant_xyz[None, None, :]
    return xyz

def compute_random_glare_amount(amount: float, roughness: float, blur: float, shape: tuple[int, ...]) -> np.ndarray:
    random_glare = fast_lognormal_from_mean_std(amount*np.ones(shape),
                                                roughness*amount*np.ones(shape))
    # random_glare = gaussian_filter(random_glare, blur)
    random_glare = fast_gaussian_filter(random_glare, blur)
    random_glare /= 100
    return random_glare