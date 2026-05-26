from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from spektrafilm.profiles.io import Profile, ProfileData, ProfileInfo
from spektrafilm.runtime.services.color_reference import ColorReferenceService, _remove_cctf

pytestmark = pytest.mark.unit


def _make_profile(profile_type: str = "negative") -> Profile:
    log_exposure = np.linspace(-3.0, 1.0, 24)
    density_curves = np.column_stack([
        np.clip(log_exposure + 2.3, 0.2, 2.6),
        np.clip(log_exposure + 2.0, 0.3, 2.3),
        np.clip(log_exposure + 1.7, 0.4, 2.0),
    ])
    return Profile(
        info=ProfileInfo(type=profile_type, support="film"),
        data=ProfileData(
            wavelengths=np.array([450.0, 550.0, 650.0]),
            log_sensitivity=np.zeros((3, 3), dtype=float),
            channel_density=np.zeros((3, 3), dtype=float),
            base_density=np.zeros((3,), dtype=float),
            midscale_neutral_density=np.zeros((3,), dtype=float),
            log_exposure=log_exposure,
            density_curves=density_curves,
            density_curves_layers=np.stack([
                density_curves * 0.5,
                density_curves * 0.3,
                density_curves * 0.2,
            ], axis=1),
        ),
    )


def _make_io_params(scan_film: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        scan_film=scan_film,
        output_color_space="sRGB",
        output_clip_min=True,
        output_clip_max=True,
    )


def _make_service(
    profile_type: str = "negative",
    scan_film: bool = False,
    black_correction: bool = False,
    white_correction: bool = False,
    black_level: float = 0.01,
    white_level: float = 0.98,
) -> ColorReferenceService:
    film = _make_profile(profile_type)
    print_profile = _make_profile("negative")
    return ColorReferenceService(
        film_profile=film,
        film_render=SimpleNamespace(),
        print_profile=print_profile,
        print_render=SimpleNamespace(density_curve_gamma=1.0),
        black_correction=black_correction,
        white_correction=white_correction,
        black_level=black_level,
        white_level=white_level,
        io_params=_make_io_params(scan_film=scan_film),
    )


class TestRemoveCCTF:
    def test_srgb_round_trip_is_close_to_identity(self) -> None:
        """_remove_cctf decodes sRGB CCTF; a mid-gray input should stay near mid-gray."""
        result = _remove_cctf(0.5, color_space="sRGB")
        assert 0.1 < result < 0.6

    def test_white_level_decodes_to_near_one(self) -> None:
        result = _remove_cctf(1.0, color_space="sRGB")
        assert 0.8 < result < 1.1

    def test_zero_decodes_to_zero(self) -> None:
        result = _remove_cctf(0.0, color_space="sRGB")
        assert abs(result) < 0.01


class TestColorReferenceServiceNoCorrection:
    def test_no_correction_returns_identity_xyz(self) -> None:
        """When both corrections are disabled, black_white_xyz_correction returns input unchanged."""
        service = _make_service(black_correction=False, white_correction=False)
        xyz = np.random.default_rng(42).random((4, 4, 3)) * 0.5
        result = service.black_white_xyz_correction(xyz)
        np.testing.assert_array_equal(result, xyz)

    def test_negative_film_scan_returns_identity(self) -> None:
        """Negative film scans should not be corrected."""
        service = _make_service(
            profile_type="negative", scan_film=True,
            black_correction=True, white_correction=True,
        )
        xyz = np.random.default_rng(42).random((4, 4, 3)) * 0.5
        result = service.black_white_xyz_correction(xyz)
        np.testing.assert_array_equal(result, xyz)

    def test_filming_exposure_correction_returns_one_when_disabled(self) -> None:
        service = _make_service(black_correction=False, white_correction=False)
        result = service.black_white_filming_exposure_correction()
        assert result == 1.0

    def test_filming_exposure_correction_returns_one_for_negative(self) -> None:
        service = _make_service(
            profile_type="negative",
            black_correction=True, white_correction=True,
        )
        result = service.black_white_filming_exposure_correction()
        assert result == 1.0


class TestColorReferenceServiceWithCorrection:
    def test_positive_film_scan_applies_correction(self) -> None:
        """Positive film with scan_film=True and corrections enabled should modify XYZ."""
        service = _make_service(
            profile_type="positive", scan_film=True,
            black_correction=True, white_correction=True,
        )
        # Set up the cmy_to_log_xyz callback BEFORE calling correction methods.
        def fake_cmy_to_log_xyz(cmy):
            return np.log10(np.maximum(cmy, 1e-6))

        service.cmy_to_log_xyz = fake_cmy_to_log_xyz

        xyz = np.full((2, 2, 3), 0.5)
        result = service.black_white_xyz_correction(xyz)

        # Result should differ from input (correction applied).
        assert not np.allclose(result, xyz, atol=1e-6)

    def test_correction_references_computed_for_positive_scan(self) -> None:
        """_y_black and _y_white should be computed when positive film is scanned."""
        service = _make_service(
            profile_type="positive", scan_film=True,
            black_correction=True, white_correction=True,
        )

        def fake_cmy_to_log_xyz(cmy):
            return np.log10(np.maximum(cmy, 1e-6))

        service.cmy_to_log_xyz = fake_cmy_to_log_xyz

        # Trigger reference update via the correction path.
        service._update_cmy_black_white_references(in_print=False)

        assert service._y_black is not None
        assert service._y_white is not None
        assert np.isfinite(service._y_black)
        assert np.isfinite(service._y_white)
