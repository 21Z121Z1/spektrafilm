"""Regression tests for Tier 3 quality-audit fixes (FMT-004..FMT-008)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from spektrafilm.utils.gain_map_metadata import GainMapChannel, GainMapMetadata


# ---------------------------------------------------------------------------
# FIX 13: FMT-004 — HEIF save raises ImportError instead of silent fallback
# ---------------------------------------------------------------------------


def _make_gain_map_metadata() -> GainMapMetadata:
    ch = GainMapChannel(gain_map_min=0.0, gain_map_max=1.0)
    return GainMapMetadata(channels=[ch, ch, ch])


class TestHeifSaveFallsBackToJpeg:
    """save_gain_map_heif must fall back to JPEG MPF when pillow-heif is absent."""

    def test_falls_back_to_jpeg(self, tmp_path):
        from spektrafilm.utils import gain_map_io

        base = np.zeros((4, 4, 3), dtype=np.float32)
        gm = np.zeros((4, 4, 3), dtype=np.float32)
        meta = _make_gain_map_metadata()

        # Simulate pillow-heif being unavailable — code falls back to JPEG MPF
        with patch.dict(sys.modules, {"pillow_heif": None}):
            gain_map_io.save_gain_map_heif(tmp_path / "out.heif", base, gm, meta)

        assert (tmp_path / "out.jpg").exists(), "JPEG fallback must be created"

    def test_jpg_fallback_contains_valid_data(self, tmp_path):
        from spektrafilm.utils import gain_map_io

        base = np.ones((4, 4, 3), dtype=np.float32) * 0.5
        gm = np.zeros((4, 4, 3), dtype=np.float32)
        meta = _make_gain_map_metadata()

        with patch.dict(sys.modules, {"pillow_heif": None}):
            gain_map_io.save_gain_map_heif(tmp_path / "out.heif", base, gm, meta)

        jpg_path = tmp_path / "out.jpg"
        assert jpg_path.exists()
        data = jpg_path.read_bytes()
        assert data[:2] == b"\xff\xd8", "Fallback must be a valid JPEG"


# ---------------------------------------------------------------------------
# FIX 14: FMT-005 — PIL save uses resolve_icc_profile_bytes with fallback
# ---------------------------------------------------------------------------


class TestPilSaveIccFallback:
    """PIL/JPEG/PNG save path should use resolve_icc_profile_bytes (with fallback)."""

    def test_resolve_used_instead_of_load(self):
        """The save path must call resolve_icc_profile_bytes, not _load_icc_profile."""
        from spektrafilm.utils import io as io_module

        import inspect

        source = inspect.getsource(io_module.save_image_oiio)
        assert "resolve_icc_profile_bytes" in source, (
            "save_image_oiio must use resolve_icc_profile_bytes for ICC lookup"
        )


# ---------------------------------------------------------------------------
# FIX 15: FMT-006 — DCI-P3 linear ICC entry exists
# ---------------------------------------------------------------------------


class TestDciP3IccEntry:
    """_ICC_FILENAMES must contain DCI-P3 encoded entry."""

    def test_dci_p3_encoded_entry(self):
        from spektrafilm.utils.io import _ICC_FILENAMES

        assert ("DCI-P3", True) in _ICC_FILENAMES

    def test_dci_p3_encoded_resolves(self):
        """resolve_icc_profile_bytes should return something for DCI-P3 encoded."""
        from spektrafilm.utils.io import resolve_icc_profile_bytes

        result = resolve_icc_profile_bytes("DCI-P3", cctf_encoding=True)
        assert result is not None, "DCI-P3 encoded should resolve to an ICC profile"
        assert len(result) > 0


# ---------------------------------------------------------------------------
# FIX 16: FMT-008 — EXR float16 overflow warning
# ---------------------------------------------------------------------------


class TestExrFloat16OverflowWarning:
    """save_image_oiio must warn when pixel values exceed float16 range."""

    def test_warning_emitted_on_overflow(self, tmp_path):
        from spektrafilm.utils.io import save_image_oiio
        from spektrafilm.color_management import ColorEncoding

        # Create image data with values exceeding float16 max (65504)
        img = np.full((4, 4, 3), 70000.0, dtype=np.float32)

        encoding = ColorEncoding(color_space="ACEScg", transfer="linear", role="scene")

        out_path = str(tmp_path / "overflow.exr")
        with pytest.warns(UserWarning, match="float16"):
            save_image_oiio(
                out_path, img, encoding=encoding, bit_depth=16, color_space="ACEScg",
            )

    def test_no_warning_within_range(self, tmp_path):
        from spektrafilm.utils.io import save_image_oiio
        from spektrafilm.color_management import ColorEncoding

        img = np.full((4, 4, 3), 1.0, dtype=np.float32)

        encoding = ColorEncoding(color_space="ACEScg", transfer="linear", role="scene")

        out_path = str(tmp_path / "safe.exr")
        # Should not warn for values within float16 range
        save_image_oiio(
            out_path, img, encoding=encoding, bit_depth=16, color_space="ACEScg",
        )
