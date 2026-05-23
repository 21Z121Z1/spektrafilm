"""Unit tests for spektrafilm.utils.gamut_compression.

The algorithms themselves are A/B-validated against ACES RGC and
coloraide in spektrafilm-research/studies/a40_lut_system/
validate_compression_against_references.py. These tests cover the
public contract (spec validation, dispatcher, identity behavior,
LUT remap shape and end-effects).
"""
from __future__ import annotations

import numpy as np
import pytest

from spektrafilm.utils.gamut_compression import (
    GamutCompressSpec,
    OutputGamutCompressSpec,
    compress_rgb,
    compress_rgb_aces_rgc,
    compress_rgb_cam16ucs_chroma,
    compress_rgb_jzazbz_chroma,
    compress_rgb_oklch_chroma,
    compress_rgb_oklrab_chroma,
    compress_xy,
    reinhard_knee,
    remap_tc_lut_for_compression,
    spectral_locus_xy,
)


class TestGamutCompressSpec:
    def test_default_is_aces_cyan_with_limit_one(self):
        s = GamutCompressSpec()
        assert s.active is True
        assert s.algorithm == "xy"
        assert s.knee == (0.815, 1.0, 1.2)

    def test_inactive_constructs(self):
        s = GamutCompressSpec(active=False)
        assert s.active is False

    def test_oklch_algorithm_constructs(self):
        s = GamutCompressSpec(algorithm="oklch")
        assert s.algorithm == "oklch"

    def test_custom_knee_constructs(self):
        s = GamutCompressSpec(knee=(0.7, 1.5, 1.5))
        assert s.knee == (0.7, 1.5, 1.5)

    def test_invalid_algorithm_raises(self):
        with pytest.raises(ValueError, match="algorithm must be"):
            GamutCompressSpec(algorithm="cam16")

    def test_threshold_out_of_range_raises(self):
        with pytest.raises(ValueError, match="threshold"):
            GamutCompressSpec(knee=(1.0, 1.0, 1.2))
        with pytest.raises(ValueError, match="threshold"):
            GamutCompressSpec(knee=(-0.1, 1.0, 1.2))

    def test_non_positive_limit_raises(self):
        with pytest.raises(ValueError, match="limit"):
            GamutCompressSpec(knee=(0.8, 0.0, 1.2))

    def test_non_positive_power_raises(self):
        with pytest.raises(ValueError, match="power"):
            GamutCompressSpec(knee=(0.8, 1.0, 0.0))

    def test_frozen_dataclass(self):
        s = GamutCompressSpec()
        with pytest.raises(Exception):
            s.active = False  # type: ignore[misc]


class TestSpectralLocus:
    def test_closed_polygon(self):
        locus = spectral_locus_xy()
        assert locus.shape[1] == 2
        assert np.allclose(locus[0], locus[-1]), "polygon must close on itself"
        assert locus.shape[0] >= 50, "should have enough vertices for a smooth locus"

    def test_in_lower_triangle(self):
        """Every locus vertex must satisfy x >= 0, y >= 0, x + y <= 1
        (modulo floating-point at the rounding edge near 580nm)."""
        locus = spectral_locus_xy()
        assert np.all(locus[:, 0] >= -1e-6)
        assert np.all(locus[:, 1] >= -1e-6)
        assert np.all(locus.sum(axis=-1) <= 1.0 + 1e-6)

    def test_cached(self):
        a = spectral_locus_xy()
        b = spectral_locus_xy()
        assert a is b, "locus polygon should be a cached singleton"


class TestReinhardKnee:
    def test_below_threshold_identity(self):
        d = np.array([0.0, 0.2, 0.5, 0.8])
        out = reinhard_knee(d, threshold=0.815, limit=1.0, power=1.2)
        np.testing.assert_array_equal(out, d)

    def test_above_threshold_strictly_below_input(self):
        d = np.array([0.9, 1.5, 5.0, 100.0])
        out = reinhard_knee(d, threshold=0.815, limit=1.0, power=1.2)
        assert np.all(out < d), "knee must compress, not stretch"

    def test_asymptotes_at_limit(self):
        """As d -> infinity the knee approaches the limit."""
        out = reinhard_knee(
            np.array(1e9), threshold=0.815, limit=1.0, power=1.2
        )
        assert abs(float(out) - 1.0) < 1e-6

    def test_continuous_at_threshold(self):
        eps = 1e-9
        below = reinhard_knee(
            np.array(0.815 - eps), threshold=0.815, limit=1.0, power=1.2,
        )
        above = reinhard_knee(
            np.array(0.815 + eps), threshold=0.815, limit=1.0, power=1.2,
        )
        assert abs(float(above) - float(below)) < 1e-6


class TestCompressXy:
    def setup_method(self):
        self.white = np.array([1 / 3, 1 / 3])
        self.spec = GamutCompressSpec()

    def test_inactive_is_identity(self):
        spec = GamutCompressSpec(active=False)
        xy = np.array([[0.7, 0.2], [0.1, 0.8]])
        out = compress_xy(xy, self.white, spec)
        np.testing.assert_array_equal(out, xy)

    def test_at_white_unchanged(self):
        out = compress_xy(self.white, self.white, self.spec)
        np.testing.assert_allclose(out, self.white, atol=1e-9)

    def test_in_locus_below_threshold_unchanged(self):
        # A point well inside the locus, below the threshold distance.
        # Pick xy ≈ (0.35, 0.36), very close to white.
        xy = np.array([0.35, 0.36])
        out = compress_xy(xy, self.white, self.spec)
        np.testing.assert_allclose(out, xy, atol=1e-9)

    def test_OOG_xy_pulled_inside_locus(self):
        # V-Gamut red corner direction, way outside the locus.
        xy = np.array([[0.73, 0.28]])
        out = compress_xy(xy, self.white, self.spec)
        # With limit=1.0 the asymptote is at the locus boundary; the
        # output should be at most ~1.0 × locus distance from white.
        d_in = np.linalg.norm(xy[0] - self.white)
        d_out = np.linalg.norm(out[0] - self.white)
        assert d_out < d_in, "OOG input should be pulled in"

    def test_oklch_algorithm_works(self):
        spec = GamutCompressSpec(algorithm="oklch")
        xy = np.array([[0.7, 0.2], [0.1, 0.8]])
        out = compress_xy(xy, self.white, spec)
        assert out.shape == xy.shape
        assert np.all(np.isfinite(out))


class TestRemapTcLutForCompression:
    def _dummy_lut(self, H=64, W=64):
        """A LUT whose value at each cell encodes the cell's tc index,
        so we can detect which cell got sampled by remap."""
        i, j = np.meshgrid(np.arange(H), np.arange(W), indexing="ij")
        return np.stack(
            [i / (H - 1), j / (W - 1), 0.5 * np.ones_like(i, dtype=float)],
            axis=-1,
        ).astype(float)

    def test_inactive_is_exact_identity(self):
        lut = self._dummy_lut()
        spec = GamutCompressSpec(active=False)
        out = remap_tc_lut_for_compression(
            lut, np.array([1 / 3, 1 / 3]), spec,
        )
        assert np.array_equal(out, lut)

    def test_active_preserves_shape_and_dtype(self):
        lut = self._dummy_lut()
        spec = GamutCompressSpec()
        out = remap_tc_lut_for_compression(
            lut, np.array([1 / 3, 1 / 3]), spec,
        )
        assert out.shape == lut.shape
        assert out.dtype == lut.dtype

    def test_active_changes_some_cells(self):
        """The compression should remap at least some cells (those near
        the OOG corners), proving the remap actually fires."""
        lut = self._dummy_lut()
        spec = GamutCompressSpec()
        out = remap_tc_lut_for_compression(
            lut, np.array([1 / 3, 1 / 3]), spec,
        )
        assert not np.array_equal(out, lut), "remap should change some cells"

    def test_oklch_algorithm_works(self):
        lut = self._dummy_lut()
        spec = GamutCompressSpec(algorithm="oklch")
        out = remap_tc_lut_for_compression(
            lut, np.array([1 / 3, 1 / 3]), spec,
        )
        assert out.shape == lut.shape
        assert np.all(np.isfinite(out))

    def test_remap_rejects_non_3_channels(self):
        lut = np.zeros((32, 32, 4))
        spec = GamutCompressSpec()
        with pytest.raises(AssertionError, match="3 channels"):
            remap_tc_lut_for_compression(
                lut, np.array([1 / 3, 1 / 3]), spec,
            )


class TestOutputGamutCompressSpec:
    def test_default_is_oklch_with_gentle_knee(self):
        """Default is the perceptual-chroma OkLch algorithm with a
        gentle knee that only kicks in at 95% of the way to the cube
        edge — the output boundary is much closer to legitimate film
        chroma than the input boundary (spectral locus) was, so the
        output default is deliberately softer than the input default
        ``(0.815, 1.0, 1.2)``. aces_rgc / jzazbz remain available as
        opt-in."""
        s = OutputGamutCompressSpec()
        assert s.active is True
        assert s.algorithm == "oklch"
        assert s.knee == (0.95, 1.0, 2.0)

    def test_aces_rgc_constructs(self):
        s = OutputGamutCompressSpec(algorithm="aces_rgc")
        assert s.algorithm == "aces_rgc"

    def test_jzazbz_constructs(self):
        s = OutputGamutCompressSpec(algorithm="jzazbz")
        assert s.algorithm == "jzazbz"

    def test_cam16ucs_constructs(self):
        s = OutputGamutCompressSpec(algorithm="cam16ucs")
        assert s.algorithm == "cam16ucs"

    def test_oklrab_constructs(self):
        s = OutputGamutCompressSpec(algorithm="oklrab")
        assert s.algorithm == "oklrab"

    def test_inactive_constructs(self):
        OutputGamutCompressSpec(active=False)

    def test_invalid_algorithm_raises(self):
        with pytest.raises(ValueError, match="algorithm must be"):
            OutputGamutCompressSpec(algorithm="xy")

    def test_invalid_knee_raises(self):
        with pytest.raises(ValueError, match="threshold"):
            OutputGamutCompressSpec(knee=(1.0, 1.0, 1.2))
        with pytest.raises(ValueError, match="limit"):
            OutputGamutCompressSpec(knee=(0.5, -0.1, 1.2))
        with pytest.raises(ValueError, match="power"):
            OutputGamutCompressSpec(knee=(0.5, 1.0, 0.0))

    def test_frozen_dataclass(self):
        s = OutputGamutCompressSpec()
        with pytest.raises(Exception):
            s.active = False  # type: ignore[misc]


class TestCompressRgbAcesRgc:
    knee = dict(threshold=0.815, limit=1.0, power=1.2)

    def test_in_gamut_identity(self):
        rgb = np.array([0.5, 0.5, 0.5])
        out = compress_rgb_aces_rgc(rgb, **self.knee)
        np.testing.assert_allclose(out, rgb, atol=1e-12)

    def test_below_threshold_identity(self):
        # ach = 1.0; per-channel d = (1 - 0.3)/1 = 0.7 < threshold 0.815 -> identity.
        rgb = np.array([1.0, 0.3, 0.3])
        out = compress_rgb_aces_rgc(rgb, **self.knee)
        np.testing.assert_allclose(out, rgb, atol=1e-12)

    def test_negative_channels_pulled_back_inside(self):
        """With limit=1.0 the knee's asymptote is at d=1 (c'=0), but
        for finite OOG inputs the output is just shy of the boundary.
        What matters is that negatives become non-negative."""
        rgb = np.array([1.5, -0.1, -0.05])
        out = compress_rgb_aces_rgc(rgb, **self.knee)
        # Max channel unchanged; negatives pulled to >= 0.
        assert out[0] == pytest.approx(1.5, abs=1e-9)
        assert out[1] >= 0.0
        assert out[2] >= 0.0
        # And to *meaningfully* less than the original |c|, not just barely.
        assert out[1] < 0.2
        assert out[2] < 0.2

    def test_more_negative_channels_get_more_compressed(self):
        """Stronger negative inputs land closer to the c'=0 boundary
        because d is larger and the knee's asymptote is at limit=1.0."""
        a = compress_rgb_aces_rgc(
            np.array([1.0, -0.05, -0.05]), **self.knee,
        )
        b = compress_rgb_aces_rgc(
            np.array([1.0, -1.0, -1.0]), **self.knee,
        )
        # Stronger OOG -> smaller (closer to 0) output.
        assert b[1] < a[1]
        assert b[2] < a[2]

    def test_max_channel_never_changes(self):
        """ACES RGC's per-channel formula leaves the achromatic max
        untouched. It compresses the *other* channels relative to it.
        High-amplitude clipping is delegated to the downstream
        gamut_clip safety net."""
        rgb = np.array([2.0, -0.1, 0.3])
        out = compress_rgb_aces_rgc(rgb, **self.knee)
        assert out[0] == pytest.approx(2.0, abs=1e-9)

    def test_batch_input_preserves_shape(self):
        rgb = np.random.default_rng(0).uniform(-0.2, 1.5, size=(7, 11, 3))
        out = compress_rgb_aces_rgc(rgb, **self.knee)
        assert out.shape == rgb.shape

    def test_all_zero_pixel_falls_back_to_identity(self):
        """Pixels with ach <= 0 (black or below) keep their original
        values; no chromaticity is defined to compress around."""
        rgb = np.array([[0.0, 0.0, 0.0], [-1e-13, 0.0, 0.0]])
        out = compress_rgb_aces_rgc(rgb, **self.knee)
        np.testing.assert_allclose(out, rgb, atol=1e-12)


class TestCompressRgbDispatcher:
    def test_inactive_identity(self):
        rgb = np.array([1.5, -0.1, -0.05])
        spec = OutputGamutCompressSpec(active=False)
        out = compress_rgb(rgb, spec)
        np.testing.assert_array_equal(out, rgb)

    def test_active_pulls_negatives_inside(self):
        # Default algorithm is "oklch" which needs output_color_space.
        rgb = np.array([1.5, -0.1, -0.05])
        spec = OutputGamutCompressSpec()
        out = compress_rgb(rgb, spec, output_color_space="sRGB")
        assert out[1] >= -1e-3
        assert out[2] >= -1e-3

    def test_oklch_requires_output_color_space(self):
        spec = OutputGamutCompressSpec(algorithm="oklch")
        with pytest.raises(ValueError, match="output_color_space is required"):
            compress_rgb(np.array([0.5, 0.5, 0.5]), spec)

    def test_oklch_dispatches_with_output_color_space(self):
        spec = OutputGamutCompressSpec(algorithm="oklch")
        rgb = np.array([1.2, -0.05, -0.05])
        out = compress_rgb(rgb, spec, output_color_space="sRGB")
        assert out.shape == rgb.shape

    def test_jzazbz_requires_output_color_space(self):
        spec = OutputGamutCompressSpec(algorithm="jzazbz")
        with pytest.raises(ValueError, match="output_color_space is required"):
            compress_rgb(np.array([0.5, 0.5, 0.5]), spec)

    def test_jzazbz_dispatches_with_output_color_space(self):
        spec = OutputGamutCompressSpec(algorithm="jzazbz")
        rgb = np.array([1.2, -0.05, -0.05])
        out = compress_rgb(rgb, spec, output_color_space="sRGB")
        assert out.shape == rgb.shape

    def test_cam16ucs_requires_output_color_space(self):
        spec = OutputGamutCompressSpec(algorithm="cam16ucs")
        with pytest.raises(ValueError, match="output_color_space is required"):
            compress_rgb(np.array([0.5, 0.5, 0.5]), spec)

    def test_cam16ucs_dispatches_with_output_color_space(self):
        spec = OutputGamutCompressSpec(algorithm="cam16ucs")
        rgb = np.array([1.2, -0.05, -0.05])
        out = compress_rgb(rgb, spec, output_color_space="sRGB")
        assert out.shape == rgb.shape

    def test_oklrab_requires_output_color_space(self):
        spec = OutputGamutCompressSpec(algorithm="oklrab")
        with pytest.raises(ValueError, match="output_color_space is required"):
            compress_rgb(np.array([0.5, 0.5, 0.5]), spec)

    def test_oklrab_dispatches_with_output_color_space(self):
        spec = OutputGamutCompressSpec(algorithm="oklrab")
        rgb = np.array([1.2, -0.05, -0.05])
        out = compress_rgb(rgb, spec, output_color_space="sRGB")
        assert out.shape == rgb.shape


class TestCompressRgbOklchChroma:
    knee = dict(threshold=0.815, limit=1.0, power=1.2)

    def test_in_gamut_approximate_identity(self):
        """Below the threshold, OkLch chroma is near-identity. There's
        a small OkLab round-trip noise (~1e-5) but it's well below LUT
        precision."""
        rgb = np.array([0.5, 0.5, 0.5])
        out = compress_rgb_oklch_chroma(
            rgb, output_color_space="sRGB", **self.knee,
        )
        np.testing.assert_allclose(out, rgb, atol=1e-3)

    def test_pulls_negatives_inside(self):
        rgb = np.array([1.2, -0.1, -0.05])
        out = compress_rgb_oklch_chroma(
            rgb, output_color_space="sRGB", **self.knee,
        )
        # All channels should land at >= 0 (cube boundary).
        assert np.all(out >= -1e-3)

    def test_compresses_saturated_cyan(self):
        rgb = np.array([-0.2, 1.0, 1.0])
        out = compress_rgb_oklch_chroma(
            rgb, output_color_space="sRGB", **self.knee,
        )
        # R should land inside [0, 1]; G and B remain near 1.
        assert -1e-3 <= out[0] <= 1.0 + 1e-3
        assert out[1] > 0.7  # cyan-y still
        assert out[2] > 0.7

    def test_lightness_preserved_for_modest_OOG(self):
        """OkLch preserves perceptual lightness L by construction.
        For a sample whose chroma is OOG but L is well-defined, the
        compressed RGB should have approximately the same L."""
        import colour
        rgb = np.array([1.05, 0.1, 0.4])  # slightly OOG warm color
        out = compress_rgb_oklch_chroma(
            rgb, output_color_space="sRGB", **self.knee,
        )
        cs = colour.RGB_COLOURSPACES["sRGB"]
        white = cs.whitepoint
        xyz_in = colour.RGB_to_XYZ(
            rgb, colourspace="sRGB",
            illuminant=white, apply_cctf_decoding=False,
        )
        xyz_out = colour.RGB_to_XYZ(
            out, colourspace="sRGB",
            illuminant=white, apply_cctf_decoding=False,
        )
        L_in = float(colour.XYZ_to_Oklab(xyz_in)[0])
        L_out = float(colour.XYZ_to_Oklab(xyz_out)[0])
        # L should be unchanged (within OkLab round-trip noise).
        assert abs(L_in - L_out) < 1e-3

    def test_batch_input(self):
        rgb = np.random.default_rng(0).uniform(-0.2, 1.3, size=(20, 3))
        out = compress_rgb_oklch_chroma(
            rgb, output_color_space="sRGB", **self.knee,
        )
        assert out.shape == rgb.shape
        assert np.all(np.isfinite(out))

    def test_table_cached_per_color_space(self):
        """Calling the C_max accessor twice with the same (space,
        output) pair should hit the cache (no rebuild)."""
        from spektrafilm.utils.gamut_compression import _get_output_c_max_table
        first = _get_output_c_max_table("oklch", "sRGB")
        second = _get_output_c_max_table("oklch", "sRGB")
        assert first is second


class TestCompressRgbJzazbzChroma:
    """JzAzBz chroma reduction. Same algorithm shape as OkLch (the two
    share the C_max bisection and Reinhard knee), so the contract
    mirrors :class:`TestCompressRgbOklchChroma`."""

    knee = dict(threshold=0.815, limit=1.0, power=1.2)

    def test_in_gamut_approximate_identity(self):
        rgb = np.array([0.5, 0.5, 0.5])
        out = compress_rgb_jzazbz_chroma(
            rgb, output_color_space="sRGB", **self.knee,
        )
        np.testing.assert_allclose(out, rgb, atol=1e-3)

    def test_pulls_negatives_inside(self):
        rgb = np.array([1.2, -0.1, -0.05])
        out = compress_rgb_jzazbz_chroma(
            rgb, output_color_space="sRGB", **self.knee,
        )
        assert np.all(out >= -1e-3)

    def test_compresses_saturated_cyan(self):
        rgb = np.array([-0.2, 1.0, 1.0])
        out = compress_rgb_jzazbz_chroma(
            rgb, output_color_space="sRGB", **self.knee,
        )
        assert -1e-3 <= out[0] <= 1.0 + 1e-3
        assert out[1] > 0.7
        assert out[2] > 0.7

    def test_lightness_preserved_for_modest_OOG(self):
        """JzAzBz preserves perceptual lightness Jz by construction."""
        import colour
        from spektrafilm.utils.gamut_compression import _JZAZBZ_Y_W_CDM2
        rgb = np.array([1.05, 0.1, 0.4])
        out = compress_rgb_jzazbz_chroma(
            rgb, output_color_space="sRGB", **self.knee,
        )
        cs = colour.RGB_COLOURSPACES["sRGB"]
        white = cs.whitepoint
        xyz_in = colour.RGB_to_XYZ(
            rgb, colourspace="sRGB",
            illuminant=white, apply_cctf_decoding=False,
        )
        xyz_out = colour.RGB_to_XYZ(
            out, colourspace="sRGB",
            illuminant=white, apply_cctf_decoding=False,
        )
        Jz_in = float(colour.XYZ_to_Jzazbz(xyz_in * _JZAZBZ_Y_W_CDM2)[0])
        Jz_out = float(colour.XYZ_to_Jzazbz(xyz_out * _JZAZBZ_Y_W_CDM2)[0])
        assert abs(Jz_in - Jz_out) < 1e-3

    def test_batch_input(self):
        rgb = np.random.default_rng(0).uniform(-0.2, 1.3, size=(20, 3))
        out = compress_rgb_jzazbz_chroma(
            rgb, output_color_space="sRGB", **self.knee,
        )
        assert out.shape == rgb.shape
        assert np.all(np.isfinite(out))


class TestCompressRgbOklrabChroma:
    """Oklrab chroma reduction — OkLab with Ottosson's Lr remap on the
    lightness axis. Same chromatic behavior as oklch, so the contract
    mirrors :class:`TestCompressRgbOklchChroma`."""

    knee = dict(threshold=0.95, limit=1.0, power=2.0)

    def test_lr_remap_roundtrip(self):
        from spektrafilm.utils.gamut_compression import (
            _oklab_L_to_oklrab_Lr,
            _oklrab_Lr_to_oklab_L,
        )
        L = np.linspace(0.0, 1.0, 21)
        Lr = _oklab_L_to_oklrab_Lr(L)
        L_back = _oklrab_Lr_to_oklab_L(Lr)
        np.testing.assert_allclose(L_back, L, atol=1e-12)
        # Endpoints fixed: Lr(0)=0, Lr(1)≈1.
        assert _oklab_L_to_oklrab_Lr(np.array(0.0)) == pytest.approx(0.0, abs=1e-12)
        assert _oklab_L_to_oklrab_Lr(np.array(1.0)) == pytest.approx(1.0, abs=1e-2)

    def test_in_gamut_approximate_identity(self):
        rgb = np.array([0.5, 0.5, 0.5])
        out = compress_rgb_oklrab_chroma(
            rgb, output_color_space="sRGB", **self.knee,
        )
        np.testing.assert_allclose(out, rgb, atol=1e-3)

    def test_pulls_negatives_inside(self):
        rgb = np.array([1.2, -0.1, -0.05])
        out = compress_rgb_oklrab_chroma(
            rgb, output_color_space="sRGB", **self.knee,
        )
        assert np.all(out >= -1e-3)

    def test_compresses_saturated_cyan(self):
        rgb = np.array([-0.2, 1.0, 1.0])
        out = compress_rgb_oklrab_chroma(
            rgb, output_color_space="sRGB", **self.knee,
        )
        assert -1e-3 <= out[0] <= 1.0 + 1e-3
        assert out[1] > 0.7
        assert out[2] > 0.7

    def test_lightness_preserved_for_modest_OOG(self):
        """Oklrab preserves OkLab L by construction (the knee touches
        only C). Equivalent to oklch's lightness-preservation contract."""
        import colour
        rgb = np.array([1.05, 0.1, 0.4])
        out = compress_rgb_oklrab_chroma(
            rgb, output_color_space="sRGB", **self.knee,
        )
        cs = colour.RGB_COLOURSPACES["sRGB"]
        white = cs.whitepoint
        xyz_in = colour.RGB_to_XYZ(
            rgb, colourspace="sRGB",
            illuminant=white, apply_cctf_decoding=False,
        )
        xyz_out = colour.RGB_to_XYZ(
            out, colourspace="sRGB",
            illuminant=white, apply_cctf_decoding=False,
        )
        L_in = float(colour.XYZ_to_Oklab(xyz_in)[0])
        L_out = float(colour.XYZ_to_Oklab(xyz_out)[0])
        assert abs(L_in - L_out) < 1e-3

    def test_batch_input(self):
        rgb = np.random.default_rng(0).uniform(-0.2, 1.3, size=(20, 3))
        out = compress_rgb_oklrab_chroma(
            rgb, output_color_space="sRGB", **self.knee,
        )
        assert out.shape == rgb.shape
        assert np.all(np.isfinite(out))


class TestCompressRgbCam16UcsChroma:
    """CAM16-UCS chroma reduction. Same algorithm shape as OkLch and
    JzAzBz; contract mirrors :class:`TestCompressRgbJzazbzChroma`."""

    knee = dict(threshold=0.95, limit=1.0, power=2.0)

    def test_in_gamut_approximate_identity(self):
        rgb = np.array([0.5, 0.5, 0.5])
        out = compress_rgb_cam16ucs_chroma(
            rgb, output_color_space="sRGB", **self.knee,
        )
        np.testing.assert_allclose(out, rgb, atol=1e-3)

    def test_pulls_negatives_inside(self):
        rgb = np.array([1.2, -0.1, -0.05])
        out = compress_rgb_cam16ucs_chroma(
            rgb, output_color_space="sRGB", **self.knee,
        )
        assert np.all(out >= -1e-3)

    def test_compresses_saturated_cyan(self):
        rgb = np.array([-0.2, 1.0, 1.0])
        out = compress_rgb_cam16ucs_chroma(
            rgb, output_color_space="sRGB", **self.knee,
        )
        assert -1e-3 <= out[0] <= 1.0 + 1e-3
        assert out[1] > 0.7
        assert out[2] > 0.7

    def test_lightness_preserved_for_modest_OOG(self):
        """CAM16-UCS preserves perceptual lightness Jp by construction."""
        import colour
        from spektrafilm.utils.gamut_compression import (
            _CAM16UCS_L_A,
            _CAM16UCS_Y_B,
            _output_cs_whitepoint_xyz,
        )
        rgb = np.array([1.05, 0.1, 0.4])
        out = compress_rgb_cam16ucs_chroma(
            rgb, output_color_space="sRGB", **self.knee,
        )
        cs = colour.RGB_COLOURSPACES["sRGB"]
        white = cs.whitepoint
        xyz_w = _output_cs_whitepoint_xyz("sRGB")
        xyz_in = colour.RGB_to_XYZ(
            rgb, colourspace="sRGB",
            illuminant=white, apply_cctf_decoding=False,
        )
        xyz_out = colour.RGB_to_XYZ(
            out, colourspace="sRGB",
            illuminant=white, apply_cctf_decoding=False,
        )
        Jp_in = float(colour.XYZ_to_CAM16UCS(
            xyz_in, XYZ_w=xyz_w, L_A=_CAM16UCS_L_A, Y_b=_CAM16UCS_Y_B,
        )[0])
        Jp_out = float(colour.XYZ_to_CAM16UCS(
            xyz_out, XYZ_w=xyz_w, L_A=_CAM16UCS_L_A, Y_b=_CAM16UCS_Y_B,
        )[0])
        # CAM16 Jp ≈ 100 at white; 0.1 tolerance is well within
        # round-trip noise and easily distinguishes preserved-J from
        # an algorithm bug that lost it.
        assert abs(Jp_in - Jp_out) < 0.1

    def test_batch_input(self):
        rgb = np.random.default_rng(0).uniform(-0.2, 1.3, size=(20, 3))
        out = compress_rgb_cam16ucs_chroma(
            rgb, output_color_space="sRGB", **self.knee,
        )
        assert out.shape == rgb.shape
        assert np.all(np.isfinite(out))
