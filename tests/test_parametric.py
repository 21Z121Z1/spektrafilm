import numpy as np
import pytest
from spektrafilm.model.parametric import parametric_density_curves_model


pytestmark = pytest.mark.unit


class TestParametricDensityCurvesModel:
    def test_monotonically_increasing(self):
        """Density curves for a negative film should be monotonically non-decreasing."""
        log_exposure = np.linspace(-3, 2, 200)
        gamma = [0.6, 0.6, 0.6]
        log_exposure_0 = [-1.5, -1.5, -1.5]
        density_max = [2.5, 2.5, 2.5]
        toe_size = [0.3, 0.3, 0.3]
        shoulder_size = [0.5, 0.5, 0.5]
        result = parametric_density_curves_model(
            log_exposure, gamma, log_exposure_0, density_max, toe_size, shoulder_size
        )
        for ch in range(3):
            diff = np.diff(result[:, ch])
            assert np.all(diff >= -1e-10), f"Channel {ch} is not monotonically increasing"

    def test_density_near_zero_at_low_exposure(self):
        """At very low exposures, density should be near zero."""
        log_exposure = np.linspace(-6, 2, 200)
        gamma = [0.6, 0.6, 0.6]
        log_exposure_0 = [-1.0, -1.0, -1.0]
        density_max = [2.5, 2.5, 2.5]
        toe_size = [0.3, 0.3, 0.3]
        shoulder_size = [0.5, 0.5, 0.5]
        result = parametric_density_curves_model(
            log_exposure, gamma, log_exposure_0, density_max, toe_size, shoulder_size
        )
        assert np.all(result[:5, :] < 0.01)

    def test_density_max_is_respected_as_upper_bound(self):
        """Density should not significantly exceed density_max."""
        log_exposure = np.linspace(-3, 5, 200)
        gamma = [0.6, 0.6, 0.6]
        log_exposure_0 = [-1.5, -1.5, -1.5]
        density_max = [2.0, 2.5, 3.0]
        toe_size = [0.3, 0.3, 0.3]
        shoulder_size = [0.5, 0.5, 0.5]
        result = parametric_density_curves_model(
            log_exposure, gamma, log_exposure_0, density_max, toe_size, shoulder_size
        )
        for ch in range(3):
            assert np.max(result[:, ch]) <= density_max[ch] + 0.05

    def test_extreme_gamma_low(self):
        """Very low gamma should produce compressed density range."""
        log_exposure = np.linspace(-3, 2, 100)
        gamma = [0.2, 0.2, 0.2]
        log_exposure_0 = [-1.5, -1.5, -1.5]
        density_max = [2.5, 2.5, 2.5]
        toe_size = [0.3, 0.3, 0.3]
        shoulder_size = [0.5, 0.5, 0.5]
        result = parametric_density_curves_model(
            log_exposure, gamma, log_exposure_0, density_max, toe_size, shoulder_size
        )
        # Low gamma = low contrast = smaller density range.
        assert np.max(result) < 1.0

    def test_extreme_gamma_high(self):
        """Very high gamma should produce expanded density range."""
        log_exposure = np.linspace(-3, 2, 100)
        gamma = [1.5, 1.5, 1.5]
        log_exposure_0 = [-1.5, -1.5, -1.5]
        density_max = [2.5, 2.5, 2.5]
        toe_size = [0.3, 0.3, 0.3]
        shoulder_size = [0.5, 0.5, 0.5]
        result = parametric_density_curves_model(
            log_exposure, gamma, log_exposure_0, density_max, toe_size, shoulder_size
        )
        # High gamma = high contrast = larger density range.
        assert np.max(result) > 2.0

    def test_small_toe_and_shoulder(self):
        """Very small toe/shoulder sizes should still produce valid output for moderate exposures."""
        log_exposure = np.linspace(-3, 1.5, 100)
        gamma = [0.6, 0.6, 0.6]
        log_exposure_0 = [-1.5, -1.5, -1.5]
        density_max = [2.5, 2.5, 2.5]
        toe_size = [0.1, 0.1, 0.1]
        shoulder_size = [0.1, 0.1, 0.1]
        result = parametric_density_curves_model(
            log_exposure, gamma, log_exposure_0, density_max, toe_size, shoulder_size
        )
        assert np.all(np.isfinite(result))
        assert np.all(result >= -0.1)

    def test_zero_toe_and_shoulder_use_clipped_linear_limit(self):
        """Zero-size toe/shoulder values should use the finite piecewise-linear limit."""
        log_exposure = np.linspace(-3, 3, 121)
        gamma = [0.6, 0.6, 0.6]
        log_exposure_0 = [-1.5, -1.0, -0.5]
        density_max = [2.0, 2.5, 3.0]
        toe_size = [0.0, 0.0, 0.0]
        shoulder_size = [0.0, 0.0, 0.0]

        with np.errstate(all="raise"):
            result = parametric_density_curves_model(
                log_exposure, gamma, log_exposure_0, density_max, toe_size, shoulder_size
            )

        expected = np.empty_like(result)
        for ch, (g, loge0, dmax) in enumerate(zip(gamma, log_exposure_0, density_max)):
            expected[:, ch] = g * (
                np.maximum(log_exposure - loge0, 0.0)
                - np.maximum(log_exposure - loge0 - dmax / g, 0.0)
            )

        assert np.all(np.isfinite(result))
        np.testing.assert_allclose(result, expected, atol=1e-12)

    def test_mixed_zero_and_nonzero_toe_shoulder_values_stay_finite(self):
        log_exposure = np.linspace(-3, 3, 121)
        result = parametric_density_curves_model(
            log_exposure,
            gamma=[0.45, 0.6, 0.75],
            log_exposure_0=[-1.5, -1.0, -0.5],
            density_max=[2.0, 2.5, 3.0],
            toe_size=[0.0, 0.2, 0.0],
            shoulder_size=[0.4, 0.0, 0.6],
        )

        assert np.all(np.isfinite(result))
        assert result.shape == (log_exposure.size, 3)

    def test_asymmetric_channel_parameters(self):
        """Different parameters per channel should produce different curves."""
        log_exposure = np.linspace(-3, 2, 100)
        gamma = [0.5, 0.6, 0.7]
        log_exposure_0 = [-1.5, -1.0, -0.5]
        density_max = [2.0, 2.5, 3.0]
        toe_size = [0.2, 0.3, 0.4]
        shoulder_size = [0.3, 0.5, 0.7]
        result = parametric_density_curves_model(
            log_exposure, gamma, log_exposure_0, density_max, toe_size, shoulder_size
        )
        # Channels should differ.
        assert not np.allclose(result[:, 0], result[:, 1])
        assert not np.allclose(result[:, 1], result[:, 2])
