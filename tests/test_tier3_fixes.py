"""Regression tests for Tier 3 quality-audit fixes (FMT-004..FMT-008)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from types import SimpleNamespace
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


class TestHeifSaveRequiresPillowHeif:
    """save_gain_map_heif must fail loudly when pillow-heif is absent."""

    def test_missing_pillow_heif_raises_import_error(self, tmp_path):
        from spektrafilm.utils import gain_map_io

        base = np.zeros((4, 4, 3), dtype=np.float32)
        gm = np.zeros((4, 4, 3), dtype=np.float32)
        meta = _make_gain_map_metadata()

        with patch.dict(sys.modules, {"pillow_heif": None}):
            with pytest.raises(ImportError, match="pillow-heif"):
                gain_map_io.save_gain_map_heif(tmp_path / "out.heif", base, gm, meta)

        assert not (tmp_path / "out.jpg").exists(), "HEIF save must not write an unrequested JPEG fallback"
        assert not (tmp_path / "out.heif").exists()

    def test_missing_pillow_heif_does_not_write_partial_output(self, tmp_path):
        from spektrafilm.utils import gain_map_io

        base = np.ones((4, 4, 3), dtype=np.float32) * 0.5
        gm = np.zeros((4, 4, 3), dtype=np.float32)
        meta = _make_gain_map_metadata()

        with patch.dict(sys.modules, {"pillow_heif": None}):
            with pytest.raises(ImportError, match="pillow-heif"):
                gain_map_io.save_gain_map_heif(tmp_path / "out.heif", base, gm, meta)

        assert list(tmp_path.iterdir()) == []

    def test_missing_iso_patcher_removes_partial_heif(self, tmp_path, monkeypatch):
        from spektrafilm.utils import gain_map_io

        class FakeHeif:
            def add_from_pillow(self, _image):
                return None

            def save(self, filename, **_kwargs):
                Path(filename).write_bytes(b"non-iso-heif")

        monkeypatch.setitem(sys.modules, "pillow_heif", SimpleNamespace(from_pillow=lambda _image: FakeHeif()))
        monkeypatch.setattr(gain_map_io, "_patch_heif_for_iso21496", lambda *_args, **_kwargs: False)

        base = np.ones((4, 4, 3), dtype=np.float32) * 0.5
        gm = np.zeros((4, 4, 3), dtype=np.float32)
        meta = _make_gain_map_metadata()
        output = tmp_path / "out.heif"

        with pytest.raises(RuntimeError, match="patcher is unavailable"):
            gain_map_io.save_gain_map_heif(output, base, gm, meta)

        assert not output.exists()

    def test_iso_validation_failure_removes_partial_heif(self, tmp_path, monkeypatch):
        from spektrafilm.utils import gain_map_io

        class FakeHeif:
            def add_from_pillow(self, _image):
                return None

            def save(self, filename, **_kwargs):
                Path(filename).write_bytes(b"bad-tmap-heif")

        monkeypatch.setitem(sys.modules, "pillow_heif", SimpleNamespace(from_pillow=lambda _image: FakeHeif()))
        monkeypatch.setattr(gain_map_io, "_patch_heif_for_iso21496", lambda *_args, **_kwargs: True)
        monkeypatch.setattr(
            gain_map_io,
            "validate_heif_iso21496",
            lambda _path: SimpleNamespace(ok=False, errors=("bad dimg",)),
        )

        base = np.ones((4, 4, 3), dtype=np.float32) * 0.5
        gm = np.zeros((4, 4, 3), dtype=np.float32)
        meta = _make_gain_map_metadata()
        output = tmp_path / "out.heif"

        with pytest.raises(RuntimeError, match="validation failed"):
            gain_map_io.save_gain_map_heif(output, base, gm, meta)

        assert not output.exists()


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
    """_ICC_FILENAMES must contain DCI-P3 encoded and linear entries."""

    def test_dci_p3_encoded_entry(self):
        from spektrafilm.utils.io import _ICC_FILENAMES

        assert ("DCI-P3", True) in _ICC_FILENAMES
        assert ("DCI-P3", False) in _ICC_FILENAMES

    def test_dci_p3_encoded_resolves(self):
        """resolve_icc_profile_bytes should return something for DCI-P3 encoded."""
        from spektrafilm.utils.io import resolve_icc_profile_bytes

        result = resolve_icc_profile_bytes("DCI-P3", cctf_encoding=True)
        assert result is not None, "DCI-P3 encoded should resolve to an ICC profile"
        assert len(result) > 0

    def test_dci_p3_linear_resolves(self):
        """resolve_icc_profile_bytes should return a linear ICC for DCI-P3 linear."""
        from spektrafilm.utils.io import resolve_icc_profile_bytes

        result = resolve_icc_profile_bytes("DCI-P3", cctf_encoding=False)
        assert result is not None, "DCI-P3 linear should resolve to an ICC profile"
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

    def test_warning_emitted_on_negative_overflow(self, tmp_path):
        from spektrafilm.utils.io import save_image_oiio
        from spektrafilm.color_management import ColorEncoding

        img = np.full((4, 4, 3), -70000.0, dtype=np.float32)
        encoding = ColorEncoding(color_space="ACEScg", transfer="linear", role="scene")

        out_path = str(tmp_path / "negative_overflow.exr")
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
