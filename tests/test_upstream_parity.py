"""Upstream parity and golden-reference regression tests.

Verifies that the SDR simulation pipeline:
1. Is deterministic (same input produces identical output).
2. Is numerically stable across float32/float64 inputs.
3. Produces a spectral LUT with expected dtype, shape and value range.
4. Matches known-good golden reference values for a midgray input.
"""

from __future__ import annotations

import numpy as np
import pytest

from spektrafilm.profiles.io import load_profile
from spektrafilm.runtime.params_builder import digest_params, init_params
from spektrafilm.runtime.process import simulate
from spektrafilm.runtime.services import SpectralLUTService

pytestmark = pytest.mark.regression


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_deterministic_params():
    """Build RuntimePhotoParams with all stochastic/spatial effects disabled.

    Settings are chosen so that the pipeline is fully deterministic and
    suitable for bit-exact reproducibility checks.
    """
    params = init_params()
    params.debug.deactivate_spatial_effects = True
    params.debug.deactivate_stochastic_effects = True
    params.camera.auto_exposure = False
    params.settings.lut_resolution = 0
    params.settings.use_enlarger_lut = False
    params.settings.use_scanner_lut = False
    return digest_params(params)


def _make_test_images() -> dict[str, np.ndarray]:
    """Return a dict of small synthetic test images (all float64)."""
    gray_ramp = np.tile(
        np.linspace(0.0, 1.0, 32, dtype=np.float64)[None, :, None],
        (32, 1, 3),
    )
    return {
        "gray_ramp": gray_ramp,
        "midgray": np.full((16, 16, 3), 0.18, dtype=np.float64),
        "near_black": np.full((16, 16, 3), 0.001, dtype=np.float64),
        "near_white": np.full((16, 16, 3), 0.99, dtype=np.float64),
        "sat_red": np.dstack([
            np.full((16, 16), 0.9),
            np.full((16, 16), 0.0),
            np.full((16, 16), 0.0),
        ]).astype(np.float64),
    }


# ---------------------------------------------------------------------------
# TestSdrParityDeterminism
# ---------------------------------------------------------------------------

class TestSdrParityDeterminism:
    """Two runs with identical deterministic params must produce identical arrays."""

    @pytest.mark.parametrize("image_key", ["gray_ramp", "midgray", "near_black"])
    def test_deterministic_output(self, image_key: str) -> None:
        images = _make_test_images()
        img = images[image_key]

        params = _make_deterministic_params()
        result_a = simulate(img, params, digest_params_first=False)
        result_b = simulate(img, params, digest_params_first=False)

        assert np.array_equal(result_a, result_b), (
            f"Non-deterministic output for {image_key}: "
            f"max diff = {np.max(np.abs(result_a - result_b))}"
        )


# ---------------------------------------------------------------------------
# TestFloatPrecisionParity
# ---------------------------------------------------------------------------

class TestFloatPrecisionParity:
    """float64 and float32 inputs should produce close (not necessarily identical) results."""

    @pytest.mark.parametrize(
        "image_key",
        ["gray_ramp", "midgray", "near_black", "near_white", "sat_red"],
    )
    def test_float32_vs_float64(self, image_key: str) -> None:
        images = _make_test_images()
        img64 = images[image_key]
        img32 = img64.astype(np.float32)

        params = _make_deterministic_params()
        result64 = simulate(img64, params, digest_params_first=False)
        result32 = simulate(img32, params, digest_params_first=False)

        max_abs_diff = float(np.max(np.abs(result64 - result32)))
        mean_abs_diff = float(np.mean(np.abs(result64 - result32)))

        assert max_abs_diff < 1e-5, (
            f"max_abs_diff={max_abs_diff:.2e} exceeds 1e-5 for {image_key}"
        )
        assert mean_abs_diff < 1e-6, (
            f"mean_abs_diff={mean_abs_diff:.2e} exceeds 1e-6 for {image_key}"
        )


# ---------------------------------------------------------------------------
# TestSpectralLutProperties
# ---------------------------------------------------------------------------

class TestSpectralLutProperties:
    """Validate the spectral LUT produced by SpectralLUTService."""

    @pytest.fixture(autouse=True)
    def _build_lut(self):
        film = load_profile("kodak_portra_400")
        self._service = SpectralLUTService(lut_resolution=17)
        adapt = film.hanatos2025_adaptation()
        self._service.set_hanatos2025_adaptation(adapt)
        sensitivity = np.exp(film.data.log_sensitivity)
        self._lut = self._service.get_filming_tc_lut(sensitivity)

    def test_spectral_lut_dtype_is_float64(self) -> None:
        assert self._lut.dtype == np.float64, (
            f"Expected float64, got {self._lut.dtype}"
        )

    def test_spectral_lut_shape_is_valid(self) -> None:
        assert self._lut.ndim == 3, f"Expected 3-D array, got {self._lut.ndim}-D"
        assert self._lut.shape[2] == 3, (
            f"Expected 3 channels (last axis), got {self._lut.shape[2]}"
        )
        assert self._lut.shape[0] > 0 and self._lut.shape[1] > 0, (
            f"Spatial dimensions must be positive, got {self._lut.shape[:2]}"
        )

    def test_spectral_lut_values_in_valid_range(self) -> None:
        assert np.all(np.isfinite(self._lut)), "LUT contains non-finite values"
        assert np.all(self._lut >= 0), "LUT contains negative values"


# ---------------------------------------------------------------------------
# TestGoldenReference
# ---------------------------------------------------------------------------

class TestGoldenReference:
    """Regression suite against captured golden reference values."""

    # Golden reference captured with:
    #   params = init_params()
    #   params.debug.deactivate_spatial_effects = True
    #   params.debug.deactivate_stochastic_effects = True
    #   params.camera.auto_exposure = False
    #   params.settings.lut_resolution = 0
    #   img = np.full((16, 16, 3), 0.18, dtype=np.float64)
    #   result = simulate(img, digest_params(params))
    #   center = result[8, 8]
    GOLDEN_R = 4.587501955381701468e-01
    GOLDEN_G = 4.532247835250490797e-01
    GOLDEN_B = 4.577094035034299790e-01

    def test_midgray_output_golden_reference(self) -> None:
        params = _make_deterministic_params()
        img = np.full((16, 16, 3), 0.18, dtype=np.float64)
        result = simulate(img, params, digest_params_first=False)
        center = result[8, 8]

        assert center[0] == pytest.approx(self.GOLDEN_R, abs=1e-10), (
            f"R channel mismatch: {center[0]:.18e} != {self.GOLDEN_R:.18e}"
        )
        assert center[1] == pytest.approx(self.GOLDEN_G, abs=1e-10), (
            f"G channel mismatch: {center[1]:.18e} != {self.GOLDEN_G:.18e}"
        )
        assert center[2] == pytest.approx(self.GOLDEN_B, abs=1e-10), (
            f"B channel mismatch: {center[2]:.18e} != {self.GOLDEN_B:.18e}"
        )

    def test_output_dtype_is_float64(self) -> None:
        """Pipeline output must be float64 regardless of input dtype."""
        params = _make_deterministic_params()

        for dtype in [np.float64, np.float32]:
            img = np.full((16, 16, 3), 0.18, dtype=dtype)
            result = simulate(img, params, digest_params_first=False)
            assert result.dtype == np.float64, (
                f"Input dtype {dtype} produced output dtype {result.dtype}, expected float64"
            )
