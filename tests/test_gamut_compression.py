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
    compress_xy,
    reinhard_knee,
    remap_tc_lut_for_compression,
    spectral_locus_xy,
)


class TestGamutCompressSpec:
    def test_default_is_aces_cyan_with_limit_one(self):
        s = GamutCompressSpec()
        assert s.mode == "soft"
        assert s.algorithm == "xy"
        assert s.knee == (0.815, 1.0, 1.2)

    def test_off_mode_constructs(self):
        s = GamutCompressSpec(mode="off")
        assert s.mode == "off"

    def test_oklch_algorithm_constructs(self):
        s = GamutCompressSpec(algorithm="oklch")
        assert s.algorithm == "oklch"

    def test_custom_knee_constructs(self):
        s = GamutCompressSpec(knee=(0.7, 1.5, 1.5))
        assert s.knee == (0.7, 1.5, 1.5)

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="mode must be"):
            GamutCompressSpec(mode="hard")

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
            s.mode = "off"  # type: ignore[misc]


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

    def test_off_mode_is_identity(self):
        spec = GamutCompressSpec(mode="off")
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

    def test_off_mode_is_exact_identity(self):
        lut = self._dummy_lut()
        spec = GamutCompressSpec(mode="off")
        out = remap_tc_lut_for_compression(
            lut, np.array([1 / 3, 1 / 3]), spec,
        )
        assert np.array_equal(out, lut)

    def test_soft_mode_preserves_shape_and_dtype(self):
        lut = self._dummy_lut()
        spec = GamutCompressSpec()
        out = remap_tc_lut_for_compression(
            lut, np.array([1 / 3, 1 / 3]), spec,
        )
        assert out.shape == lut.shape
        assert out.dtype == lut.dtype

    def test_soft_mode_changes_some_cells(self):
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
