"""Tests for edge cases identified in code quality review round 4."""

from __future__ import annotations

import numpy as np
import pytest

from spektrafilm.utils.crop_resize import crop_image
from spektrafilm.utils.hdr_photo import hdr_photo_color_space, SUPPORTED_HDR_PHOTO_COLOR_SPACES
from spektrafilm.model.diffusion import _strength_to_scatter


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# TC-C1: Pipeline.soft_update behavior
# ---------------------------------------------------------------------------


class TestPipelineSoftUpdate:
    """Tests for Pipeline.soft_update parameter mutation and state refresh."""

    def test_soft_update_changes_exposure_compensation(self, default_params) -> None:
        from spektrafilm.runtime.pipeline import SimulationPipeline
        from spektrafilm.runtime.params_builder import digest_params

        params = digest_params(default_params)
        pipeline = SimulationPipeline(params)

        original_ev = pipeline.camera.exposure_compensation_ev
        pipeline.soft_update(exposure_compensation_ev=original_ev + 1.5)
        assert pipeline.camera.exposure_compensation_ev == original_ev + 1.5

    def test_soft_update_changes_print_exposure(self, default_params) -> None:
        from spektrafilm.runtime.pipeline import SimulationPipeline
        from spektrafilm.runtime.params_builder import digest_params

        params = digest_params(default_params)
        pipeline = SimulationPipeline(params)

        original = pipeline.enlarger.print_exposure
        pipeline.soft_update(print_exposure=original * 2.0)
        assert pipeline.enlarger.print_exposure == original * 2.0

    def test_soft_update_changes_filter_neutrals(self, default_params) -> None:
        from spektrafilm.runtime.pipeline import SimulationPipeline
        from spektrafilm.runtime.params_builder import digest_params

        params = digest_params(default_params)
        pipeline = SimulationPipeline(params)

        pipeline.soft_update(c_filter_neutral=10.0, m_filter_neutral=20.0, y_filter_neutral=30.0)
        assert pipeline.enlarger.c_filter_neutral == 10.0
        assert pipeline.enlarger.m_filter_neutral == 20.0
        assert pipeline.enlarger.y_filter_neutral == 30.0

    def test_soft_update_none_leaves_unchanged(self, default_params) -> None:
        from spektrafilm.runtime.pipeline import SimulationPipeline
        from spektrafilm.runtime.params_builder import digest_params

        params = digest_params(default_params)
        pipeline = SimulationPipeline(params)

        original_ev = pipeline.camera.exposure_compensation_ev
        original_pe = pipeline.enlarger.print_exposure
        pipeline.soft_update()  # all None
        assert pipeline.camera.exposure_compensation_ev == original_ev
        assert pipeline.enlarger.print_exposure == original_pe

    def test_soft_update_with_density_curves(self, default_params) -> None:
        from spektrafilm.runtime.pipeline import SimulationPipeline
        from spektrafilm.runtime.params_builder import digest_params

        params = digest_params(default_params)
        pipeline = SimulationPipeline(params)

        new_curves = np.ones_like(pipeline.film.data.density_curves) * 0.5
        pipeline.soft_update(film_density_curves=new_curves)
        np.testing.assert_array_equal(pipeline.film.data.density_curves, new_curves)

    def test_soft_update_affects_subsequent_process(self, default_params) -> None:
        from spektrafilm.runtime.process import Simulator
        from spektrafilm.runtime.params_builder import digest_params

        params = digest_params(default_params)
        sim = Simulator(params)

        image = np.ones((4, 4, 3), dtype=np.float64) * 0.18
        result_before = sim.process(image)

        sim.soft_update(exposure_compensation_ev=2.0)
        result_after = sim.process(image)

        # Exposure change should produce different output
        assert not np.allclose(result_before, result_after, atol=1e-6)


# ---------------------------------------------------------------------------
# TC-H2: hdr_photo_color_space fallback behavior
# ---------------------------------------------------------------------------


class TestHdrPhotoColorSpace:
    def test_supported_space_returns_same(self) -> None:
        for space in SUPPORTED_HDR_PHOTO_COLOR_SPACES:
            assert hdr_photo_color_space(space) == space

    def test_unsupported_space_falls_back_to_display_p3(self) -> None:
        result = hdr_photo_color_space("Adobe RGB")
        assert result == "Display P3"

    def test_none_falls_back_to_display_p3(self) -> None:
        result = hdr_photo_color_space(None)
        assert result == "Display P3"

    def test_empty_string_falls_back(self) -> None:
        result = hdr_photo_color_space("")
        assert result == "Display P3"


# ---------------------------------------------------------------------------
# TC-M3: crop_image boundary conditions
# ---------------------------------------------------------------------------


class TestCropImageBoundaryConditions:
    def test_very_small_crop(self) -> None:
        image = np.random.default_rng(42).random((100, 100, 3))
        cropped = crop_image(image, center=(0.5, 0.5), size=(0.01, 0.01))
        assert cropped.ndim == 3
        assert cropped.shape[0] > 0
        assert cropped.shape[1] > 0

    def test_crop_at_origin_corner(self) -> None:
        image = np.random.default_rng(42).random((100, 100, 3))
        cropped = crop_image(image, center=(0.0, 0.0), size=(0.1, 0.1))
        assert cropped.ndim == 3
        assert cropped.shape[0] > 0
        assert cropped.shape[1] > 0

    def test_crop_at_far_corner(self) -> None:
        image = np.random.default_rng(42).random((100, 100, 3))
        cropped = crop_image(image, center=(1.0, 1.0), size=(0.1, 0.1))
        assert cropped.ndim == 3
        assert cropped.shape[0] > 0
        assert cropped.shape[1] > 0

    def test_crop_size_equal_to_image(self) -> None:
        image = np.random.default_rng(42).random((50, 50, 3))
        cropped = crop_image(image, center=(0.5, 0.5), size=(1.0, 1.0))
        # Should not exceed original dimensions
        assert cropped.shape[0] <= 50
        assert cropped.shape[1] <= 50

    def test_crop_preserves_channel_count(self) -> None:
        image = np.random.default_rng(42).random((100, 100, 3))
        cropped = crop_image(image, center=(0.5, 0.5), size=(0.3, 0.3))
        assert cropped.shape[2] == 3


class TestFilterInterpolationSanitization:
    def test_load_filter_replaces_akima_out_of_range_nan_with_zero(self, monkeypatch) -> None:
        import spektrafilm.utils.io as io_utils

        class FakePackage:
            def __truediv__(self, _filename):
                return self

            def open(self, *_args, **_kwargs):
                class Handle:
                    def __enter__(self):
                        return object()

                    def __exit__(self, *_exc):
                        return False

                return Handle()

        class FakeAkima:
            def __init__(self, *_args, **_kwargs):
                pass

            def __call__(self, wavelengths):
                values = np.linspace(0.1, 0.3, np.size(wavelengths), dtype=float)
                values[0] = np.nan
                values[-1] = np.nan
                return values

        monkeypatch.setattr(io_utils.pkg_resources, "files", lambda _package: FakePackage())
        monkeypatch.setattr(io_utils.np, "loadtxt", lambda *_args, **_kwargs: np.array([[400.0, 10.0], [500.0, 20.0]]))
        monkeypatch.setattr(io_utils.scipy.interpolate, "Akima1DInterpolator", FakeAkima)

        transmittance = io_utils.load_filter(np.array([380.0, 450.0, 780.0]), name="KG3")

        np.testing.assert_allclose(transmittance, np.array([0.0, 0.2, 0.0]))

    def test_load_dichroic_filters_replaces_akima_out_of_range_nan_with_zero(self, monkeypatch) -> None:
        import spektrafilm.utils.io as io_utils

        class FakePackage:
            def __truediv__(self, _filename):
                return self

            def open(self, *_args, **_kwargs):
                class Handle:
                    def __enter__(self):
                        return object()

                    def __exit__(self, *_exc):
                        return False

                return Handle()

        class FakeAkima:
            def __init__(self, *_args, **_kwargs):
                pass

            def __call__(self, wavelengths):
                values = np.full(np.size(wavelengths), 0.5, dtype=float)
                values[0] = np.nan
                values[-1] = np.nan
                return values

        monkeypatch.setattr(io_utils.pkg_resources, "files", lambda _package: FakePackage())
        monkeypatch.setattr(io_utils.np, "loadtxt", lambda *_args, **_kwargs: np.array([[400.0, 10.0], [500.0, 20.0]]))
        monkeypatch.setattr(io_utils.scipy.interpolate, "Akima1DInterpolator", FakeAkima)

        filters = io_utils.load_dichroic_filters(np.array([380.0, 450.0, 780.0]))

        np.testing.assert_allclose(filters[0], np.zeros(3))
        np.testing.assert_allclose(filters[1], np.full(3, 0.5))
        np.testing.assert_allclose(filters[2], np.zeros(3))


class TestFastGaussianFilterEmptyInputs:
    def test_large_sigma_empty_2d_height_returns_empty_copy(self) -> None:
        from spektrafilm.utils.fast_gaussian_filter import fast_gaussian_filter

        image = np.empty((0, 5), dtype=np.float64)
        result = fast_gaussian_filter(image, sigma=5.0)

        assert result.shape == image.shape
        assert result.dtype == image.dtype
        assert result is not image

    def test_large_sigma_empty_2d_width_returns_empty_copy(self) -> None:
        from spektrafilm.utils.fast_gaussian_filter import fast_gaussian_filter

        image = np.empty((5, 0), dtype=np.float64)
        result = fast_gaussian_filter(image, sigma=5.0)

        assert result.shape == image.shape
        assert result.dtype == image.dtype
        assert result is not image

    def test_large_sigma_empty_3d_returns_empty_copy(self) -> None:
        from spektrafilm.utils.fast_gaussian_filter import fast_gaussian_filter

        image = np.empty((0, 5, 3), dtype=np.float64)
        result = fast_gaussian_filter(image, sigma=5.0)

        assert result.shape == image.shape
        assert result.dtype == image.dtype
        assert result is not image


# ---------------------------------------------------------------------------
# TC-M4: _strength_to_scatter interpolation
# ---------------------------------------------------------------------------


class TestStrengthToScatter:
    def test_zero_strength_returns_zero(self) -> None:
        assert _strength_to_scatter(0.0, "black_pro_mist") == 0.0

    def test_negative_strength_returns_zero(self) -> None:
        assert _strength_to_scatter(-1.0, "black_pro_mist") == 0.0

    def test_monotonic_in_strength(self) -> None:
        strengths = [0.125, 0.25, 0.5, 1.0, 2.0]
        results = [_strength_to_scatter(s, "black_pro_mist") for s in strengths]
        for i in range(len(results) - 1):
            assert results[i] <= results[i + 1] + 1e-10

    def test_output_bounded_between_0_and_1(self) -> None:
        for strength in [0.001, 0.1, 0.5, 1.0, 2.0, 10.0]:
            result = _strength_to_scatter(strength, "black_pro_mist")
            assert 0.0 <= result <= 1.0

    def test_breakpoint_values_match_table_with_gain(self) -> None:
        from spektrafilm.model.diffusion import (
            _DIFFUSION_STRENGTH_BREAKPOINTS,
            _DIFFUSION_STRENGTH_TOTAL_FRACTION,
            _DIFFUSION_FAMILY_TOTAL_GAIN,
        )
        # At the exact breakpoints, the interpolated value should be base * gain
        gain = _DIFFUSION_FAMILY_TOTAL_GAIN.get("black_pro_mist", 1.0)
        for strength, base in zip(_DIFFUSION_STRENGTH_BREAKPOINTS, _DIFFUSION_STRENGTH_TOTAL_FRACTION):
            result = _strength_to_scatter(float(strength), "black_pro_mist")
            expected = float(np.clip(base * gain, 0.0, 0.99))
            np.testing.assert_allclose(result, expected, atol=0.02)

    def test_unknown_family_uses_gain_1(self) -> None:
        from spektrafilm.model.diffusion import (
            _DIFFUSION_STRENGTH_BREAKPOINTS,
            _DIFFUSION_STRENGTH_TOTAL_FRACTION,
        )

        result_unknown = _strength_to_scatter(1.0, "nonexistent_family")
        expected = np.interp(
            0.0,
            np.log2(_DIFFUSION_STRENGTH_BREAKPOINTS),
            _DIFFUSION_STRENGTH_TOTAL_FRACTION,
        )
        np.testing.assert_allclose(result_unknown, expected, atol=1e-12)


# ---------------------------------------------------------------------------
# EH-M5: least_squares convergence warning test
# ---------------------------------------------------------------------------


class TestMeasureDensityMinConvergence:
    def test_measure_density_min_handles_degenerate_data(self) -> None:
        """Verify that measure_density_min returns a valid result on degenerate (all-zero) data."""
        import warnings
        from spektrafilm.utils.measure import measure_density_min

        # Create data that's hard to fit (all zeros - degenerate case)
        log_exposure = np.linspace(-3, 3, 64)
        density_curves = np.zeros((64, 3))

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = measure_density_min(log_exposure, density_curves, info_type='negative')
            # The function handles degenerate data gracefully (no warning) and returns a valid shape
            assert result.shape == (3,)
            assert len(w) == 0, f"Unexpected warnings: {[str(x.message) for x in w]}"


# ---------------------------------------------------------------------------
# TC-5: format_elapsed_time boundary values
# ---------------------------------------------------------------------------


class TestFormatElapsedTime:
    def test_zero_seconds(self) -> None:
        from spektrafilm.utils.timings import format_elapsed_time
        assert format_elapsed_time(0.0) == "0.00 us"

    def test_microseconds(self) -> None:
        from spektrafilm.utils.timings import format_elapsed_time
        result = format_elapsed_time(5e-6)
        assert "5.00" in result
        assert "us" in result

    def test_milliseconds(self) -> None:
        from spektrafilm.utils.timings import format_elapsed_time
        result = format_elapsed_time(0.005)
        assert "5.00" in result
        assert "ms" in result

    def test_seconds(self) -> None:
        from spektrafilm.utils.timings import format_elapsed_time
        result = format_elapsed_time(1.5)
        assert "1.50" in result
        assert "s" in result
        assert "ms" not in result

    def test_large_value_high_precision(self) -> None:
        from spektrafilm.utils.timings import format_elapsed_time
        result = format_elapsed_time(100.0)
        assert "s" in result
        # 100s should have 0 decimal places
        assert result == "100 s"

    def test_boundary_at_one_second(self) -> None:
        from spektrafilm.utils.timings import format_elapsed_time
        result = format_elapsed_time(1.0)
        assert "1.00" in result
        assert "s" in result

    def test_boundary_at_one_millisecond(self) -> None:
        from spektrafilm.utils.timings import format_elapsed_time
        result = format_elapsed_time(0.001)
        assert "1.00" in result
        assert "ms" in result


# ---------------------------------------------------------------------------
# TC-6: _validate_path_component security
# ---------------------------------------------------------------------------


class TestValidatePathComponent:
    def test_valid_simple_name(self) -> None:
        from spektrafilm.utils.io import _validate_path_component
        # Should not raise
        _validate_path_component("thorlabs", "brand")

    def test_valid_name_with_hyphen(self) -> None:
        from spektrafilm.utils.io import _validate_path_component
        _validate_path_component("black-pro-mist", "filter")

    def test_valid_name_with_underscore(self) -> None:
        from spektrafilm.utils.io import _validate_path_component
        _validate_path_component("my_filter_01", "filter")

    def test_valid_name_with_digits(self) -> None:
        from spektrafilm.utils.io import _validate_path_component
        _validate_path_component("filter123", "filter")

    def test_rejects_path_traversal(self) -> None:
        from spektrafilm.utils.io import _validate_path_component
        with pytest.raises(ValueError, match="Invalid"):
            _validate_path_component("../etc/passwd", "brand")

    def test_rejects_slash(self) -> None:
        from spektrafilm.utils.io import _validate_path_component
        with pytest.raises(ValueError, match="Invalid"):
            _validate_path_component("foo/bar", "brand")

    def test_rejects_backslash(self) -> None:
        from spektrafilm.utils.io import _validate_path_component
        with pytest.raises(ValueError, match="Invalid"):
            _validate_path_component("foo\\bar", "brand")

    def test_rejects_special_characters(self) -> None:
        from spektrafilm.utils.io import _validate_path_component
        with pytest.raises(ValueError, match="Invalid"):
            _validate_path_component("foo;rm -rf /", "brand")

    def test_rejects_spaces(self) -> None:
        from spektrafilm.utils.io import _validate_path_component
        with pytest.raises(ValueError, match="Invalid"):
            _validate_path_component("foo bar", "brand")

    def test_rejects_empty_string(self) -> None:
        from spektrafilm.utils.io import _validate_path_component
        with pytest.raises(ValueError, match="Invalid"):
            _validate_path_component("", "brand")

    def test_error_message_includes_label(self) -> None:
        from spektrafilm.utils.io import _validate_path_component
        with pytest.raises(ValueError, match="brand"):
            _validate_path_component("../bad", "brand")

    def test_error_message_includes_value(self) -> None:
        from spektrafilm.utils.io import _validate_path_component
        with pytest.raises(ValueError, match="../bad"):
            _validate_path_component("../bad", "brand")
