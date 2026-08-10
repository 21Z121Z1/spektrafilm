from __future__ import annotations

from copy import deepcopy

import numpy as np
import pytest

from spektrafilm.gpu.backend import BackendUnavailableError, select_backend
from spektrafilm.runtime.process import simulate


pytestmark = pytest.mark.unit

_REFLECTANCE_METHODS = (
    "arctic2026beta04",
    "jakob2019",
    "otsu2018",
    "gauss-lasers",
)


def _deterministic_params(default_params, method: str, backend: str):
    params = deepcopy(default_params)
    params.settings.rgb_to_raw_method = method
    params.settings.compute_backend = backend
    params.settings.gpu_precision = "float32"
    params.settings.materialize_policy = "numpy_float64"
    params.debug.deactivate_spatial_effects = True
    params.debug.deactivate_stochastic_effects = True
    params.camera.auto_exposure = False
    return params


@pytest.mark.parametrize("method", _REFLECTANCE_METHODS)
def test_reflectance_method_mlx_fallback_matches_cpu(
    method,
    default_params,
    small_rgb_image,
) -> None:
    try:
        backend = select_backend("mlx", precision="float32")
    except (BackendUnavailableError, ValueError) as exc:
        pytest.skip(str(exc))
    if not backend.supports_gpu:
        pytest.skip("MLX GPU backend unavailable")

    cpu_params = _deterministic_params(default_params, method, "cpu")
    mlx_params = _deterministic_params(default_params, method, "mlx")

    cpu = simulate(small_rgb_image, cpu_params, digest_params_first=False)
    mlx = simulate(small_rgb_image, mlx_params, digest_params_first=False)

    assert cpu.shape == mlx.shape
    assert np.isfinite(cpu).all()
    assert np.isfinite(mlx).all()
    # The selected reflectance reconstruction itself is deliberately computed
    # on CPU for MLX today; the small tolerance covers the downstream float32
    # backend stages without masking method-specific spectral divergence.
    np.testing.assert_allclose(mlx, cpu, rtol=8e-5, atol=8e-5)
