"""Tests for ISO 21496-1 Gain Map computation and metadata.

Round-trip: compute → normalize → serialize → deserialize → denormalize → apply ≈ original.
Tests both 3-channel (RGB) and 1-channel (achromatic) modes.
"""

from __future__ import annotations

import math
import struct
import sys

import numpy as np
import pytest

from spektrafilm.utils.gain_map import (
    apply_gain_map,
    compute_gain_map,
    compute_weight,
    denormalize_gain_map,
    normalize_gain_map,
)
from spektrafilm.utils.gain_map_metadata import (
    GainMapChannel,
    GainMapMetadata,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _random_image(shape: tuple[int, ...], low: float = 0.0, high: float = 1.0) -> np.ndarray:
    rng = np.random.default_rng(42)
    return rng.uniform(low, high, size=shape).astype(np.float32)


def _sdr_hdr_pair_rgb(headroom: float = 3.0) -> tuple[np.ndarray, np.ndarray]:
    """Create a realistic SDR/HDR image pair (H=64, W=64, 3)."""
    sdr = _random_image((64, 64, 3), 0.01, 1.0)
    hdr = np.clip(sdr * headroom, 0.0, headroom).astype(np.float32)
    return sdr, hdr


def _sdr_hdr_pair_1ch(headroom: float = 3.0) -> tuple[np.ndarray, np.ndarray]:
    """Create a 1-channel (grayscale) SDR/HDR pair."""
    sdr = _random_image((64, 64), 0.01, 1.0)
    hdr = np.clip(sdr * headroom, 0.0, headroom).astype(np.float32)
    return sdr, hdr


# ---------------------------------------------------------------------------
# compute_gain_map
# ---------------------------------------------------------------------------


class TestComputeGainMap:
    def test_rgb_basic(self) -> None:
        sdr, hdr = _sdr_hdr_pair_rgb(3.0)
        gain = compute_gain_map(sdr, hdr, h_baseline=0.0, h_alternate=3.0)
        assert gain.shape == sdr.shape
        assert gain.dtype == np.float32
        assert np.all(np.isfinite(gain))

    def test_1ch_basic(self) -> None:
        sdr, hdr = _sdr_hdr_pair_1ch(3.0)
        gain = compute_gain_map(sdr, hdr, h_baseline=0.0, h_alternate=3.0)
        assert gain.shape == sdr.shape
        assert gain.dtype == np.float32

    def test_identical_inputs_yield_zero_gain(self) -> None:
        img = _random_image((32, 32, 3), 0.1, 1.0)
        gain = compute_gain_map(img, img, h_baseline=1.0, h_alternate=1.0)
        np.testing.assert_allclose(gain, 0.0, atol=1e-6)

    def test_shape_mismatch_raises(self) -> None:
        a = np.zeros((32, 32, 3), dtype=np.float32)
        b = np.zeros((32, 32), dtype=np.float32)
        with pytest.raises(ValueError, match="Shape mismatch"):
            compute_gain_map(a, b)

    def test_offset_constants_prevent_log_zero(self) -> None:
        """With k_baseline > 0, even zero baseline produces finite gain."""
        baseline = np.zeros((4, 4, 3), dtype=np.float32)
        alternate = np.ones((4, 4, 3), dtype=np.float32)
        gain = compute_gain_map(baseline, alternate, k_baseline=1 / 1023, k_alternate=1 / 1023)
        assert np.all(np.isfinite(gain))

    def test_sign_flips_when_h_alternate_less_than_h_baseline(self) -> None:
        """When h_alternate < h_baseline, sign = -1 flips the log2 direction."""
        sdr = np.full((4, 4, 3), 0.5, dtype=np.float32)
        hdr = np.full((4, 4, 3), 0.25, dtype=np.float32)
        # h_alt < h_base, so sign = -1
        # log2(0.25/0.5) = -1, so gain = -1 * (-1) = +1
        gain = compute_gain_map(sdr, hdr, h_baseline=3.0, h_alternate=0.0, k_baseline=0.0, k_alternate=0.0)
        # sign*log2(alt/base) = -1 * log2(0.5) = -1 * (-1) = +1
        np.testing.assert_allclose(gain, 1.0, atol=1e-5)

    def test_log2_gain_matches_expected(self) -> None:
        """For a known 2x ratio, log2 gain should be ~1.0."""
        sdr = np.full((4, 4, 3), 0.5, dtype=np.float32)
        hdr = np.full((4, 4, 3), 1.0, dtype=np.float32)
        gain = compute_gain_map(sdr, hdr, k_baseline=0.0, k_alternate=0.0, h_baseline=0.0, h_alternate=2.0)
        np.testing.assert_allclose(gain, 1.0, atol=1e-5)


# ---------------------------------------------------------------------------
# normalize_gain_map / denormalize_gain_map
# ---------------------------------------------------------------------------


class TestNormalizeDenormalize:
    def test_roundtrip_no_gamma(self) -> None:
        gain = _random_image((32, 32, 3), -0.5, 2.0)
        norm, g_min, g_max = normalize_gain_map(gain, gamma=1.0)
        assert norm.dtype == np.float32
        assert np.all(norm >= 0.0) and np.all(norm <= 1.0)
        restored = denormalize_gain_map(norm, g_min, g_max, gamma=1.0)
        np.testing.assert_allclose(restored, gain, atol=1e-5)

    def test_roundtrip_with_gamma(self) -> None:
        gain = _random_image((32, 32, 3), -0.5, 2.0)
        gamma = 2.2
        norm, g_min, g_max = normalize_gain_map(gain, gamma=gamma)
        restored = denormalize_gain_map(norm, g_min, g_max, gamma=gamma)
        np.testing.assert_allclose(restored, gain, atol=1e-4)

    def test_constant_gain_returns_zeros(self) -> None:
        gain = np.full((8, 8, 3), 1.5, dtype=np.float32)
        norm, g_min, g_max = normalize_gain_map(gain)
        np.testing.assert_allclose(norm, 0.0)
        assert g_min == pytest.approx(1.5)
        assert g_max == pytest.approx(1.5)

    def test_1ch_normalize(self) -> None:
        gain = _random_image((16, 16), -1.0, 3.0)
        norm, g_min, g_max = normalize_gain_map(gain)
        restored = denormalize_gain_map(norm, g_min, g_max)
        np.testing.assert_allclose(restored, gain, atol=1e-5)


# ---------------------------------------------------------------------------
# compute_weight
# ---------------------------------------------------------------------------


class TestComputeWeight:
    def test_full_alternate_weight(self) -> None:
        w = compute_weight(h_target=3.0, h_baseline=0.0, h_alternate=3.0)
        assert w == pytest.approx(1.0)

    def test_baseline_weight(self) -> None:
        w = compute_weight(h_target=0.0, h_baseline=0.0, h_alternate=3.0)
        assert w == pytest.approx(0.0)

    def test_mid_weight(self) -> None:
        w = compute_weight(h_target=1.5, h_baseline=0.0, h_alternate=3.0)
        assert w == pytest.approx(0.5)

    def test_clamp_above(self) -> None:
        w = compute_weight(h_target=5.0, h_baseline=0.0, h_alternate=3.0)
        assert w == pytest.approx(1.0)

    def test_clamp_below(self) -> None:
        w = compute_weight(h_target=-1.0, h_baseline=0.0, h_alternate=3.0)
        assert w == pytest.approx(0.0)

    def test_equal_headrooms_returns_zero(self) -> None:
        w = compute_weight(h_target=2.0, h_baseline=2.0, h_alternate=2.0)
        assert w == pytest.approx(0.0)

    def test_negative_direction(self) -> None:
        w = compute_weight(h_target=1.0, h_baseline=3.0, h_alternate=0.0)
        assert w < 0.0


# ---------------------------------------------------------------------------
# apply_gain_map
# ---------------------------------------------------------------------------


class TestApplyGainMap:
    def test_roundtrip_rgb(self) -> None:
        sdr, hdr = _sdr_hdr_pair_rgb(3.0)
        h_alt = 3.0
        gain = compute_gain_map(sdr, hdr, h_baseline=0.0, h_alternate=h_alt)
        norm, g_min, g_max = normalize_gain_map(gain)
        restored = apply_gain_map(sdr, norm, g_min=g_min, g_max=g_max, h_baseline=0.0, h_alternate=h_alt)
        np.testing.assert_allclose(restored, hdr, atol=1e-4)

    def test_roundtrip_1ch(self) -> None:
        sdr, hdr = _sdr_hdr_pair_1ch(3.0)
        h_alt = 3.0
        gain = compute_gain_map(sdr, hdr, h_baseline=0.0, h_alternate=h_alt)
        norm, g_min, g_max = normalize_gain_map(gain)
        restored = apply_gain_map(sdr, norm, g_min=g_min, g_max=g_max, h_baseline=0.0, h_alternate=h_alt)
        np.testing.assert_allclose(restored, hdr, atol=1e-4)

    def test_weight_half_reduces_gain(self) -> None:
        """Applying with h_target at midpoint should produce values between SDR and HDR."""
        sdr = np.full((8, 8, 3), 0.5, dtype=np.float32)
        hdr = np.full((8, 8, 3), 1.5, dtype=np.float32)
        h_alt = 3.0
        gain = compute_gain_map(sdr, hdr, h_baseline=0.0, h_alternate=h_alt)
        norm, g_min, g_max = normalize_gain_map(gain)

        full = apply_gain_map(sdr, norm, g_min=g_min, g_max=g_max, h_baseline=0.0, h_alternate=h_alt, h_target=h_alt)
        half = apply_gain_map(sdr, norm, g_min=g_min, g_max=g_max, h_baseline=0.0, h_alternate=h_alt, h_target=h_alt / 2)
        # Half-weight should produce less gain than full
        assert np.mean(half) < np.mean(full)

    def test_output_is_non_negative(self) -> None:
        sdr, hdr = _sdr_hdr_pair_rgb(4.0)
        gain = compute_gain_map(sdr, hdr, h_baseline=0.0, h_alternate=4.0)
        norm, g_min, g_max = normalize_gain_map(gain)
        restored = apply_gain_map(sdr, norm, g_min=g_min, g_max=g_max, h_baseline=0.0, h_alternate=4.0)
        assert np.all(restored >= 0.0)

    def test_with_gamma(self) -> None:
        sdr, hdr = _sdr_hdr_pair_rgb(3.0)
        gamma = 2.2
        gain = compute_gain_map(sdr, hdr, h_baseline=0.0, h_alternate=3.0)
        norm, g_min, g_max = normalize_gain_map(gain, gamma=gamma)
        restored = apply_gain_map(sdr, norm, g_min=g_min, g_max=g_max, gamma=gamma, h_baseline=0.0, h_alternate=3.0)
        np.testing.assert_allclose(restored, hdr, atol=1e-3)


# ---------------------------------------------------------------------------
# GainMapMetadata binary serialization
# ---------------------------------------------------------------------------


class TestGainMapMetadata:
    def test_serialize_deserialize_3ch(self) -> None:
        channels = (
            GainMapChannel(gain_map_min=0.0, gain_map_max=1.5, gamma=1.0, base_offset=0.001, alternate_offset=0.001),
            GainMapChannel(gain_map_min=0.0, gain_map_max=1.5, gamma=1.0, base_offset=0.001, alternate_offset=0.001),
            GainMapChannel(gain_map_min=0.0, gain_map_max=1.5, gamma=1.0, base_offset=0.001, alternate_offset=0.001),
        )
        meta = GainMapMetadata(
            is_multichannel=True,
            use_base_colour_space=True,
            base_hdr_headroom=0.0,
            alternate_hdr_headroom=3.0,
            channels=channels,
        )
        data = meta.serialize()
        assert isinstance(data, bytes)
        # 4(version) + 1(flags) + 8(base_h) + 8(alt_h) + 3*40(channels) = 141
        assert len(data) == 141

        restored = GainMapMetadata.deserialize(data)
        assert restored.is_multichannel is True
        assert restored.use_base_colour_space is True
        assert restored.base_hdr_headroom == pytest.approx(0.0, abs=1e-3)
        assert restored.alternate_hdr_headroom == pytest.approx(3.0, abs=1e-3)
        assert len(restored.channels) == 3
        for ch_r, ch_o in zip(restored.channels, channels):
            assert ch_r.gain_map_min == pytest.approx(ch_o.gain_map_min, abs=1e-3)
            assert ch_r.gain_map_max == pytest.approx(ch_o.gain_map_max, abs=1e-3)
            assert ch_r.gamma == pytest.approx(ch_o.gamma, abs=1e-3)

    def test_serialize_deserialize_1ch(self) -> None:
        channels = (GainMapChannel(gain_map_min=0.0, gain_map_max=2.0, gamma=1.0),)
        meta = GainMapMetadata(
            is_multichannel=False,
            use_base_colour_space=True,
            base_hdr_headroom=0.0,
            alternate_hdr_headroom=4.0,
            channels=channels,
        )
        data = meta.serialize()
        # 4(version) + 1(flags) + 8(base_h) + 8(alt_h) + 1*40(channel) = 61
        assert len(data) == 61

        restored = GainMapMetadata.deserialize(data)
        assert restored.is_multichannel is False
        assert len(restored.channels) == 1
        assert restored.channels[0].gain_map_max == pytest.approx(2.0, abs=1e-3)

    def test_channel_count_validation(self) -> None:
        with pytest.raises(ValueError, match="Expected 3 channels"):
            GainMapMetadata(is_multichannel=True, channels=(GainMapChannel(),))

    def test_to_xmp(self) -> None:
        meta = GainMapMetadata(
            is_multichannel=True,
            use_base_colour_space=True,
            base_hdr_headroom=0.0,
            alternate_hdr_headroom=3.0,
            channels=(
                GainMapChannel(gain_map_min=0.0, gain_map_max=1.585, gamma=1.0, base_offset=0.001, alternate_offset=0.001),
            ) * 3,
        )
        xmp = meta.to_xmp()
        assert "hdrgm:Version" in xmp
        assert "hdrgm:GainMapMax" in xmp
        assert "hdrgm:HDRCapacityMax" in xmp
        assert "Container:Directory" in xmp
        assert 'Item:Semantic="Primary"' in xmp
        assert 'Item:Semantic="GainMap"' in xmp
        assert 'Item:Mime="image/jpeg"' in xmp

    def test_to_xmp_includes_gain_map_length_when_known(self) -> None:
        meta = GainMapMetadata(
            is_multichannel=False,
            channels=(GainMapChannel(gain_map_min=0.0, gain_map_max=1.0),),
        )

        xmp = meta.to_xmp(gain_map_length=12345)

        assert 'Item:Length="12345"' in xmp

    def test_roundtrip_payload_size(self) -> None:
        """Verify binary payload sizes match ISO 21496-1 C.2.2 spec."""
        # 4(version) + 1(flags) + 8(base_h) + 8(alt_h) + N*40(channels)
        for multichannel, expected in [(True, 141), (False, 61)]:
            ch_count = 3 if multichannel else 1
            meta = GainMapMetadata(
                is_multichannel=multichannel,
                channels=tuple(GainMapChannel() for _ in range(ch_count)),
            )
            assert len(meta.serialize()) == expected


# ---------------------------------------------------------------------------
# Full round-trip: compute → normalize → serialize → deserialize → denormalize → apply
# ---------------------------------------------------------------------------


class TestFullRoundTrip:
    def test_roundtrip_rgb_3ch(self) -> None:
        sdr, hdr = _sdr_hdr_pair_rgb(3.0)
        h_baseline, h_alternate = 0.0, 3.0
        k = 1.0 / 1023.0

        # Compute gain map
        gain = compute_gain_map(sdr, hdr, k_baseline=k, k_alternate=k,
                                h_baseline=h_baseline, h_alternate=h_alternate)

        # Normalize
        norm, g_min, g_max = normalize_gain_map(gain)

        # Serialize metadata
        channels = tuple(
            GainMapChannel(gain_map_min=g_min, gain_map_max=g_max, gamma=1.0,
                           base_offset=k, alternate_offset=k)
            for _ in range(3)
        )
        meta = GainMapMetadata(
            is_multichannel=True,
            use_base_colour_space=True,
            base_hdr_headroom=h_baseline,
            alternate_hdr_headroom=h_alternate,
            channels=channels,
        )
        payload = meta.serialize()

        # Deserialize
        restored_meta = GainMapMetadata.deserialize(payload)

        # Denormalize and apply
        restored_gain = denormalize_gain_map(norm, g_min=g_min, g_max=g_max, gamma=1.0)
        np.testing.assert_allclose(restored_gain, gain, atol=1e-5)

        result = apply_gain_map(
            sdr, norm,
            g_min=restored_meta.channels[0].gain_map_min,
            g_max=restored_meta.channels[0].gain_map_max,
            gamma=1.0,
            k_baseline=restored_meta.channels[0].base_offset,
            k_alternate=restored_meta.channels[0].alternate_offset,
            h_baseline=restored_meta.base_hdr_headroom,
            h_alternate=restored_meta.alternate_hdr_headroom,
        )
        np.testing.assert_allclose(result, hdr, atol=1e-4)

    def test_roundtrip_achromatic_1ch(self) -> None:
        sdr, hdr = _sdr_hdr_pair_1ch(4.0)
        h_baseline, h_alternate = 0.0, 4.0
        k = 1.0 / 1023.0

        gain = compute_gain_map(sdr, hdr, k_baseline=k, k_alternate=k,
                                h_baseline=h_baseline, h_alternate=h_alternate)
        norm, g_min, g_max = normalize_gain_map(gain)

        meta = GainMapMetadata(
            is_multichannel=False,
            use_base_colour_space=True,
            base_hdr_headroom=h_baseline,
            alternate_hdr_headroom=h_alternate,
            channels=(GainMapChannel(gain_map_min=g_min, gain_map_max=g_max, gamma=1.0,
                                     base_offset=k, alternate_offset=k),),
        )
        payload = meta.serialize()
        restored_meta = GainMapMetadata.deserialize(payload)

        result = apply_gain_map(
            sdr, norm,
            g_min=restored_meta.channels[0].gain_map_min,
            g_max=restored_meta.channels[0].gain_map_max,
            k_baseline=restored_meta.channels[0].base_offset,
            k_alternate=restored_meta.channels[0].alternate_offset,
            h_baseline=restored_meta.base_hdr_headroom,
            h_alternate=restored_meta.alternate_hdr_headroom,
        )
        np.testing.assert_allclose(result, hdr, atol=1e-4)

    def test_roundtrip_with_gamma_encoding(self) -> None:
        sdr, hdr = _sdr_hdr_pair_rgb(3.0)
        gamma = 2.2
        k = 1.0 / 1023.0

        gain = compute_gain_map(sdr, hdr, k_baseline=k, k_alternate=k)
        norm, g_min, g_max = normalize_gain_map(gain, gamma=gamma)

        meta = GainMapMetadata(
            is_multichannel=True,
            use_base_colour_space=True,
            base_hdr_headroom=0.0,
            alternate_hdr_headroom=3.0,
            channels=tuple(
                GainMapChannel(gain_map_min=g_min, gain_map_max=g_max, gamma=gamma,
                               base_offset=k, alternate_offset=k)
                for _ in range(3)
            ),
        )
        payload = meta.serialize()
        restored_meta = GainMapMetadata.deserialize(payload)

        result = apply_gain_map(
            sdr, norm,
            g_min=restored_meta.channels[0].gain_map_min,
            g_max=restored_meta.channels[0].gain_map_max,
            gamma=restored_meta.channels[0].gamma,
            k_baseline=restored_meta.channels[0].base_offset,
            k_alternate=restored_meta.channels[0].alternate_offset,
            h_baseline=restored_meta.base_hdr_headroom,
            h_alternate=restored_meta.alternate_hdr_headroom,
        )
        np.testing.assert_allclose(result, hdr, atol=1e-3)

    def test_roundtrip_different_per_channel_values(self) -> None:
        """Test with different gain ranges per channel."""
        rng = np.random.default_rng(123)
        sdr = rng.uniform(0.01, 1.0, (32, 32, 3)).astype(np.float32)
        # Different scale per channel
        scales = np.array([2.0, 3.0, 4.0], dtype=np.float32)
        hdr = np.clip(sdr * scales, 0.0, 4.0).astype(np.float32)

        gain = compute_gain_map(sdr, hdr, k_baseline=0.0, k_alternate=0.0,
                                h_baseline=0.0, h_alternate=4.0)

        # Per-channel normalization
        norms = []
        g_mins = []
        g_maxs = []
        for c in range(3):
            n, lo, hi = normalize_gain_map(gain[:, :, c])
            norms.append(n)
            g_mins.append(lo)
            g_maxs.append(hi)

        meta = GainMapMetadata(
            is_multichannel=True,
            use_base_colour_space=True,
            base_hdr_headroom=0.0,
            alternate_hdr_headroom=4.0,
            channels=tuple(
                GainMapChannel(gain_map_min=g_mins[c], gain_map_max=g_maxs[c])
                for c in range(3)
            ),
        )
        payload = meta.serialize()
        restored = GainMapMetadata.deserialize(payload)

        # Verify per-channel values survive roundtrip
        for c in range(3):
            assert restored.channels[c].gain_map_min == pytest.approx(g_mins[c], abs=1e-3)
            assert restored.channels[c].gain_map_max == pytest.approx(g_maxs[c], abs=1e-3)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_very_small_headroom(self) -> None:
        """Headroom close to 1.0 (barely HDR)."""
        sdr = _random_image((16, 16, 3), 0.1, 0.95)
        hdr = np.clip(sdr * 1.02, 0.0, 1.02).astype(np.float32)
        gain = compute_gain_map(sdr, hdr, h_baseline=0.0, h_alternate=1.02)
        norm, g_min, g_max = normalize_gain_map(gain)
        restored = apply_gain_map(sdr, norm, g_min=g_min, g_max=g_max, h_baseline=0.0, h_alternate=1.02)
        np.testing.assert_allclose(restored, hdr, atol=1e-4)

    def test_large_headroom(self) -> None:
        """High dynamic range (8 stops)."""
        sdr = _random_image((16, 16, 3), 0.01, 1.0)
        hdr = np.clip(sdr * 8.0, 0.0, 8.0).astype(np.float32)
        gain = compute_gain_map(sdr, hdr, h_baseline=0.0, h_alternate=8.0)
        norm, g_min, g_max = normalize_gain_map(gain)
        restored = apply_gain_map(sdr, norm, g_min=g_min, g_max=g_max, h_baseline=0.0, h_alternate=8.0)
        np.testing.assert_allclose(restored, hdr, atol=1e-3)

    def test_near_zero_pixel_values(self) -> None:
        """Very dark pixels with offset constants."""
        sdr = np.full((8, 8, 3), 1e-6, dtype=np.float32)
        hdr = np.full((8, 8, 3), 1e-4, dtype=np.float32)
        gain = compute_gain_map(sdr, hdr, k_baseline=1 / 1023, k_alternate=1 / 1023)
        assert np.all(np.isfinite(gain))

    def test_dtype_float32_throughout(self) -> None:
        """Verify all outputs are float32."""
        sdr = _random_image((16, 16, 3))
        hdr = sdr * 2.0
        gain = compute_gain_map(sdr, hdr)
        assert gain.dtype == np.float32
        norm, _, _ = normalize_gain_map(gain)
        assert norm.dtype == np.float32
        restored = denormalize_gain_map(norm, 0.0, 1.0)
        assert restored.dtype == np.float32


# ---------------------------------------------------------------------------
# Gain Map I/O (JPEG MPF)
# ---------------------------------------------------------------------------


class TestGainMapIO:
    def test_save_and_load_jpeg_roundtrip(self, tmp_path) -> None:
        """Save a JPEG with gain map and load it back."""
        from spektrafilm.utils.gain_map_io import save_gain_map_jpeg, load_gain_map

        ramp = np.linspace(0.1, 1.0, 32, dtype=np.float32)
        sdr = np.dstack([
            np.tile(ramp[None, :], (32, 1)),
            np.tile(ramp[:, None], (1, 32)),
            np.full((32, 32), 0.5, dtype=np.float32),
        ]).astype(np.float32)
        gain = _random_image((32, 32, 3), 0.0, 1.0)

        meta = GainMapMetadata(
            is_multichannel=True,
            use_base_colour_space=True,
            base_hdr_headroom=0.0,
            alternate_hdr_headroom=3.0,
            channels=(
                GainMapChannel(gain_map_min=0.0, gain_map_max=1.5, gamma=1.0,
                               base_offset=0.001, alternate_offset=0.001),
            ) * 3,
        )

        out_path = tmp_path / "test_gain_map.jpg"
        save_gain_map_jpeg(out_path, sdr, gain, meta)

        assert out_path.exists()
        assert out_path.stat().st_size > 0

        loaded = load_gain_map(out_path)
        assert loaded["format"] == "jpeg"
        assert loaded["base_image"] is not None
        assert loaded["base_image"].size == (32, 32)
        loaded_base = np.asarray(loaded["base_image"], dtype=np.float32) / 255.0
        np.testing.assert_allclose(loaded_base, sdr, atol=8 / 255)

    def test_save_jpeg_metadata_roundtrip(self, tmp_path) -> None:
        """Verify metadata survives JPEG MPF roundtrip."""
        from spektrafilm.utils.gain_map_io import save_gain_map_jpeg, load_gain_map

        sdr = np.full((16, 16, 3), 0.5, dtype=np.float32)
        gain = np.full((16, 16, 3), 0.5, dtype=np.float32)

        meta = GainMapMetadata(
            is_multichannel=False,
            use_base_colour_space=True,
            base_hdr_headroom=0.0,
            alternate_hdr_headroom=4.0,
            channels=(GainMapChannel(gain_map_min=0.0, gain_map_max=2.0, gamma=1.0),),
        )

        out_path = tmp_path / "meta_test.jpg"
        save_gain_map_jpeg(out_path, sdr, gain, meta)

        loaded = load_gain_map(out_path)
        assert loaded["metadata"] is not None
        assert loaded["metadata"].alternate_hdr_headroom == pytest.approx(4.0, abs=1e-3)
        assert loaded["metadata"].is_multichannel is False

    def test_save_jpeg_uint8_input(self, tmp_path) -> None:
        """Verify uint8 images are handled correctly."""
        from spektrafilm.utils.gain_map_io import save_gain_map_jpeg

        sdr = np.random.randint(0, 256, (16, 16, 3), dtype=np.uint8)
        gain = np.random.randint(0, 256, (16, 16, 3), dtype=np.uint8)

        meta = GainMapMetadata(
            is_multichannel=True,
            channels=(GainMapChannel(),) * 3,
        )

        out_path = tmp_path / "uint8_test.jpg"
        save_gain_map_jpeg(out_path, sdr, gain, meta)
        assert out_path.exists()

    def test_save_jpeg_1ch_gain_map(self, tmp_path) -> None:
        """Verify single-channel (achromatic) gain map saves correctly."""
        from spektrafilm.utils.gain_map_io import save_gain_map_jpeg

        sdr = _random_image((16, 16, 3), 0.1, 1.0)
        gain = _random_image((16, 16), 0.0, 1.0)  # 1-channel

        meta = GainMapMetadata(
            is_multichannel=False,
            channels=(GainMapChannel(gain_map_min=0.0, gain_map_max=1.0),),
        )

        out_path = tmp_path / "achromatic_test.jpg"
        save_gain_map_jpeg(out_path, sdr, gain, meta)
        assert out_path.exists()

    def test_load_nonexistent_raises(self) -> None:
        """Loading a non-existent file should raise."""
        from spektrafilm.utils.gain_map_io import load_gain_map

        with pytest.raises((FileNotFoundError, OSError)):
            load_gain_map("/nonexistent/file.jpg")

    def test_load_unsupported_extension_raises(self) -> None:
        """Loading an unsupported format should raise."""
        from spektrafilm.utils.gain_map_io import load_gain_map

        with pytest.raises(ValueError, match="Unsupported format"):
            load_gain_map("test.bmp")


class TestGainMapIOHeif:
    def test_save_heif_requires_pillow_heif(self, tmp_path, monkeypatch) -> None:
        """When pillow-heif is unavailable, HEIF save must fail without changing formats."""
        from spektrafilm.utils import gain_map_io

        sdr = _random_image((16, 16, 3), 0.1, 1.0)
        gain = _random_image((16, 16, 3), 0.0, 1.0)

        meta = GainMapMetadata(
            is_multichannel=True,
            channels=(GainMapChannel(),) * 3,
        )

        out_path = tmp_path / "fallback_test.heic"
        monkeypatch.setitem(sys.modules, "pillow_heif", None)

        with pytest.raises(ImportError, match="pillow-heif"):
            gain_map_io.save_gain_map_heif(out_path, sdr, gain, meta)

        assert not out_path.exists()
        assert not (tmp_path / "fallback_test.jpg").exists()
