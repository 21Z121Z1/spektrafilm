import numpy as np

def _toe_or_shoulder_term(delta, size):
    if size == 0:
        return np.maximum(delta, 0.0)
    return size * np.logaddexp(0.0, np.log(10.0) * delta / size) / np.log(10.0)


def parametric_density_curves_model(log_exposure, gamma, log_exposure_0, density_max, toe_size, shoulder_size):
    log_exposure = np.asarray(log_exposure, dtype=float)
    density_curves = np.zeros((np.size(log_exposure), 3))
    for i, g, loge0, dmax, ts, ss in zip(np.arange(3),
                                            gamma, log_exposure_0, density_max, toe_size, shoulder_size):
        density_curves[:,i] = (
              g * _toe_or_shoulder_term(log_exposure - loge0, ts)
            - g * _toe_or_shoulder_term(log_exposure - loge0 - dmax/g, ss)
        )
    return density_curves
