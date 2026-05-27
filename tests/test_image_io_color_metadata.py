from __future__ import annotations

import numpy as np
import OpenImageIO as oiio
import exiv2
import pytest

from spektrafilm.color_management import ColorEncoding
from spektrafilm.utils import io as io_module
from spektrafilm.utils.io import (
    ImageMetadata,
    _known_color_space_from_chromaticities,
    colorspace_chromaticities,
    load_image_oiio,
    read_image_color_encoding,
    resolve_icc_profile_bytes,
    save_hdr_rendition_exr,
    save_image_oiio,
    write_image_metadata,
)


def _image_spec(path):
    image_input = oiio.ImageInput.open(str(path))
    assert image_input is not None
    try:
        return image_input.spec()
    finally:
        image_input.close()


def _icc_bytes_from_spec(spec) -> bytes | None:
    value = spec.getattribute("ICCProfile")
    if value is None:
        return None
    if isinstance(value, bytes):
        return value
    if isinstance(value, np.ndarray):
        return np.asarray(value, dtype=np.uint8).tobytes()
    return bytes(value)


def test_png_embeds_srgb_icc_and_reads_cctf_encoding(tmp_path) -> None:
    path = tmp_path / "srgb.png"
    image = np.full((2, 3, 3), 0.5, dtype=np.float32)

    save_image_oiio(
        str(path),
        image,
        encoding=ColorEncoding(color_space="sRGB", transfer="cctf", role="display"),
    )

    spec = _image_spec(path)
    assert _icc_bytes_from_spec(spec)
    encoding = read_image_color_encoding(str(path))
    assert encoding is not None
    assert encoding.color_space == "sRGB"
    assert encoding.transfer == "cctf"


def test_load_image_oiio_path_open_failure_raises_oserror(monkeypatch, tmp_path) -> None:
    path = tmp_path / "missing.exr"
    monkeypatch.setattr(io_module.oiio.ImageInput, "open", lambda filename: None)

    with pytest.raises(OSError, match=str(path)):
        load_image_oiio(path)


def test_png_default_export_uses_16_bit_rgb_and_embeds_icc(tmp_path) -> None:
    path = tmp_path / "srgb-16.png"
    image = np.array([[[0.0, 0.5, 1.0], [0.25, 0.75, 0.9]]], dtype=np.float32)

    save_image_oiio(
        str(path),
        image,
        encoding=ColorEncoding(color_space="sRGB", transfer="cctf", role="display"),
    )

    spec = _image_spec(path)
    assert spec.format == oiio.TypeDesc("uint16")
    assert spec.nchannels == 3
    assert _icc_bytes_from_spec(spec)

    image_input = oiio.ImageInput.open(str(path))
    assert image_input is not None
    try:
        pixels = np.asarray(image_input.read_image(oiio.TypeDesc("uint16"))).reshape(image.shape)
    finally:
        image_input.close()
    np.testing.assert_array_equal(pixels[0, 0], np.array([0, 32768, 65535], dtype=np.uint16))


def test_jpeg_embeds_display_p3_icc_and_reads_cctf_encoding(tmp_path) -> None:
    path = tmp_path / "display-p3.jpg"
    image = np.full((2, 3, 3), 0.5, dtype=np.float32)

    save_image_oiio(
        str(path),
        image,
        encoding=ColorEncoding(color_space="Display P3", transfer="cctf", role="display"),
    )

    spec = _image_spec(path)
    assert _icc_bytes_from_spec(spec)
    encoding = read_image_color_encoding(str(path))
    assert encoding is not None
    assert encoding.color_space == "Display P3"
    assert encoding.transfer == "cctf"


def test_exr_writes_chromaticities_colorspace_and_preserves_hdr_values(tmp_path) -> None:
    path = tmp_path / "hdr.exr"
    image = np.array([[[0.25, 1.5, 4.0], [0.1, 0.2, 0.3]]], dtype=np.float32)

    save_image_oiio(
        str(path),
        image,
        encoding=ColorEncoding(
            color_space="Display P3",
            transfer="linear",
            role="scene",
            clip_highlights=False,
        ),
    )

    spec = _image_spec(path)
    np.testing.assert_allclose(spec.getattribute("chromaticities"), colorspace_chromaticities("Display P3"))
    assert spec.get_string_attribute("oiio:ColorSpace") == "Display P3"
    assert spec.get_string_attribute("colorInteropID") == "Display P3"

    image_input = oiio.ImageInput.open(str(path))
    assert image_input is not None
    try:
        pixels = np.asarray(image_input.read_image(oiio.TypeDesc("float")), dtype=np.float32)
    finally:
        image_input.close()
    pixels = pixels.reshape(image.shape)
    np.testing.assert_allclose(pixels, image, rtol=1e-6, atol=1e-6)
    assert float(np.max(pixels)) > 1.0

    encoding = read_image_color_encoding(str(path))
    assert encoding is not None
    assert encoding.color_space == "Display P3"
    assert encoding.transfer == "linear"
    assert encoding.clip_highlights is False


def test_archive_exr_does_not_call_hdr_rendition_mapping(monkeypatch, tmp_path) -> None:
    path = tmp_path / "archive.exr"
    image = np.array([[[0.25, 1.5, 4.0]]], dtype=np.float32)

    def fail_prepare(*args, **kwargs):
        raise AssertionError("scene-linear archive EXR must not call HDR rendition mapping")

    monkeypatch.setattr("spektrafilm.utils.hdr_photo.prepare_hdr_photo_renditions", fail_prepare)

    save_image_oiio(
        str(path),
        image,
        encoding=ColorEncoding(
            color_space="Display P3",
            transfer="linear",
            role="scene",
            clip_highlights=False,
        ),
        scene_luminance=np.array([[1.0]], dtype=np.float32),
        hdr_mapping_kwargs={"hdr_mapping_mode": "profile_aware"},
    )

    pixels = oiio.ImageInput.open(str(path))
    assert pixels is not None
    try:
        data = np.asarray(pixels.read_image(oiio.TypeDesc("float")), dtype=np.float32).reshape(image.shape)
    finally:
        pixels.close()
    np.testing.assert_allclose(data, image, rtol=1e-6, atol=1e-6)


def test_hdr_rendition_exr_uses_authored_hdr_mapping(tmp_path) -> None:
    path = tmp_path / "rendition.exr"
    image = np.full((1, 2, 3), 0.8, dtype=np.float32)
    scene_luminance = np.array([[0.8, 4.0]], dtype=np.float32)

    save_image_oiio(
        str(path),
        image,
        encoding=ColorEncoding(
            color_space="Display P3",
            transfer="linear",
            role="scene",
            clip_highlights=False,
        ),
        scene_luminance=scene_luminance,
        hdr_mapping_kwargs={
            "hdr_mapping_mode": "generic",
            "hdr_diffuse_lift_enabled": False,
            "max_headroom": 4.0,
        },
        exr_mode="hdr_rendition",
    )

    image_input = oiio.ImageInput.open(str(path))
    assert image_input is not None
    try:
        pixels = np.asarray(image_input.read_image(oiio.TypeDesc("float")), dtype=np.float32).reshape(image.shape)
        spec = image_input.spec()
    finally:
        image_input.close()

    assert float(pixels[0, 1].max()) > float(image[0, 1].max())
    assert not np.allclose(pixels, image)
    assert spec.getattribute("whiteLuminance") == pytest.approx(203.0)
    headroom = spec.getattribute("hdrHeadroom")
    assert headroom is not None
    assert 1.01 <= float(headroom) <= 4.0


def test_heic_export_passes_scene_luminance_to_hdr_photo_encoder(monkeypatch, tmp_path) -> None:
    path = tmp_path / "out.heic"
    image = np.full((1, 2, 3), 0.8, dtype=np.float32)
    scene_luminance = np.array([[0.8, 4.0]], dtype=np.float32)
    captured: dict[str, object] = {}

    def fake_save_hdr_photo_heic(filename, image_data, *, color_space, scene_luminance=None) -> None:
        captured["filename"] = filename
        captured["image_data"] = image_data.copy()
        captured["color_space"] = color_space
        captured["scene_luminance"] = None if scene_luminance is None else scene_luminance.copy()

    monkeypatch.setattr(io_module, "save_hdr_photo_heic", fake_save_hdr_photo_heic)

    io_module.save_image_oiio(
        str(path),
        image,
        encoding=ColorEncoding(
            color_space="Display P3",
            transfer="linear",
            role="scene",
            clip_highlights=False,
        ),
        scene_luminance=scene_luminance,
    )

    assert captured["filename"] == str(path)
    np.testing.assert_allclose(captured["image_data"], image)
    assert captured["color_space"] == "Display P3"
    np.testing.assert_allclose(captured["scene_luminance"], scene_luminance)


def test_non_hdr_save_path_does_not_call_hdr_mapping(monkeypatch, tmp_path) -> None:
    path = tmp_path / "plain.tif"
    image = np.full((2, 2, 3), 0.5, dtype=np.float32)

    def fail_prepare(*args, **kwargs):
        raise AssertionError("generic TIFF export must not call HDR photo mapping")

    monkeypatch.setattr("spektrafilm.utils.hdr_photo.prepare_hdr_photo_renditions", fail_prepare)

    save_image_oiio(
        str(path),
        image,
        encoding=ColorEncoding(color_space="Display P3", transfer="cctf", role="display"),
    )

    assert path.exists()


def test_acescg_exr_roundtrips_scene_linear_metadata_and_hdr_values(tmp_path) -> None:
    path = tmp_path / "acescg.exr"
    image = np.array([[[0.25, 1.5, 4.0], [-0.02, 0.2, 0.3]]], dtype=np.float32)

    save_image_oiio(
        str(path),
        image,
        encoding=ColorEncoding(
            color_space="ACEScg",
            transfer="linear",
            role="scene",
            clip_negatives=False,
            clip_highlights=False,
        ),
    )

    spec = _image_spec(path)
    np.testing.assert_allclose(spec.getattribute("chromaticities"), colorspace_chromaticities("ACEScg"))
    assert spec.get_string_attribute("oiio:ColorSpace") == "ACEScg"
    assert spec.get_string_attribute("colorInteropID") == "ACEScg"

    image_input = oiio.ImageInput.open(str(path))
    assert image_input is not None
    try:
        pixels = np.asarray(image_input.read_image(oiio.TypeDesc("float")), dtype=np.float32)
    finally:
        image_input.close()
    pixels = pixels.reshape(image.shape)
    np.testing.assert_allclose(pixels, image, rtol=1e-6, atol=1e-6)
    assert float(np.max(pixels)) > 1.0
    assert float(np.min(pixels)) < 0.0

    encoding = read_image_color_encoding(str(path))
    assert encoding is not None
    assert encoding.color_space == "ACEScg"
    assert encoding.transfer == "linear"
    assert encoding.clip_negatives is False
    assert encoding.clip_highlights is False


def test_acescg_tiff_icc_roundtrips_as_linear_encoding(tmp_path) -> None:
    path = tmp_path / "acescg.tif"
    image = np.array([[[0.25, 0.5, 0.75]]], dtype=np.float32)

    save_image_oiio(
        str(path),
        image,
        bit_depth=32,
        encoding=ColorEncoding(
            color_space="ACEScg",
            transfer="linear",
            role="scene",
            clip_negatives=False,
            clip_highlights=False,
        ),
    )

    spec = _image_spec(path)
    assert _icc_bytes_from_spec(spec)

    encoding = read_image_color_encoding(str(path))
    assert encoding is not None
    assert encoding.color_space == "ACEScg"
    assert encoding.transfer == "linear"


def test_resolve_icc_profile_bytes_returns_none_for_linear_without_bundled_profile() -> None:
    """Linear requests for color spaces without bundled gamma=1.0 profiles must return None."""
    # ACES spaces have explicit linear profiles in _ICC_FILENAMES.
    assert resolve_icc_profile_bytes("ACEScg", cctf_encoding=False) is not None
    assert resolve_icc_profile_bytes("ACES2065-1", cctf_encoding=False) is not None
    # sRGB, Adobe RGB, ProPhoto, BT.2020 have Elle Stone g10 profiles.
    assert resolve_icc_profile_bytes("sRGB", cctf_encoding=False) is not None
    # Display P3 has a bundled linear profile (DisplayP3-linear.icc).
    assert resolve_icc_profile_bytes("Display P3", cctf_encoding=False) is not None
    # DCI-P3 has no bundled linear profile — must return None
    # rather than falling back to an encoded (non-linear) profile.
    assert resolve_icc_profile_bytes("DCI-P3", cctf_encoding=False) is None
    # Encoded requests still resolve correctly.
    assert resolve_icc_profile_bytes("Display P3", cctf_encoding=True) is not None
    assert resolve_icc_profile_bytes("DCI-P3", cctf_encoding=True) is not None


def test_display_p3_linear_icc_profile_has_linear_trc() -> None:
    """Verify the bundled Display P3 linear profile has a gamma=1.0 TRC (curv count=0)."""
    import struct

    profile_bytes = resolve_icc_profile_bytes("Display P3", cctf_encoding=False)
    assert profile_bytes is not None
    assert len(profile_bytes) >= 128  # Must have at least an ICC header

    # ICC header: size(4) + CMM(4) + version(4) + class(4) + space(4) + PCS(4)
    header_size = struct.unpack(">I", profile_bytes[0:4])[0]
    assert header_size == len(profile_bytes)
    assert profile_bytes[4:8] == b"none"
    device_class = profile_bytes[12:16]
    assert device_class == b"mntr"  # display
    color_space = profile_bytes[16:20]
    assert color_space == b"RGB "

    # Verify the TRC is linear by checking for the curv tag with count=0.
    # A curv tag with count=0 means gamma=1.0 (linear).
    # Search for the rTRC tag signature in the tag table.
    num_tags = struct.unpack(">I", profile_bytes[128:132])[0]
    trc_offset = None
    for i in range(num_tags):
        entry = profile_bytes[132 + i * 12 : 132 + (i + 1) * 12]
        sig = entry[0:4]
        if sig == b"rTRC":
            offset = struct.unpack(">I", entry[4:8])[0]
            trc_offset = offset
            break
    assert trc_offset is not None, "rTRC tag not found"
    # curv type signature + reserved(4) + count(2)
    trc_type = profile_bytes[trc_offset : trc_offset + 4]
    trc_count = struct.unpack(">H", profile_bytes[trc_offset + 8 : trc_offset + 10])[0]
    assert trc_type == b"curv", f"Expected curv tag, got {trc_type!r}"
    assert trc_count == 0, f"Expected linear TRC (count=0), got count={trc_count}"


def test_linear_png_without_linear_icc_is_rejected(tmp_path) -> None:
    with pytest.raises(ValueError, match="PNG export requires CCTF-encoded data"):
        save_image_oiio(
            str(tmp_path / "linear.png"),
            np.full((1, 1, 3), 0.5, dtype=np.float32),
            encoding=ColorEncoding(color_space="Display P3", transfer="linear", role="scene"),
        )


def test_cctf_exr_is_rejected(tmp_path) -> None:
    with pytest.raises(ValueError, match="EXR export requires linear data"):
        save_image_oiio(
            str(tmp_path / "encoded.exr"),
            np.full((1, 1, 3), 0.5, dtype=np.float32),
            encoding=ColorEncoding(color_space="sRGB", transfer="cctf", role="display"),
        )


def test_heic_hdr_photo_dispatches_to_gain_map_encoder(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}
    image = np.array([[[0.25, 1.5, 4.0]]], dtype=np.float32)
    path = tmp_path / "hdr.heic"

    def fake_save_hdr_photo_heic(filename, image_data, *, color_space) -> None:
        captured["filename"] = filename
        captured["image_data"] = image_data.copy()
        captured["color_space"] = color_space

    monkeypatch.setattr("spektrafilm.utils.io.save_hdr_photo_heic", fake_save_hdr_photo_heic)

    save_image_oiio(
        str(path),
        image,
        encoding=ColorEncoding(
            color_space="Display P3",
            transfer="linear",
            role="scene",
            clip_highlights=False,
        ),
    )

    assert captured["filename"] == str(path)
    assert captured["color_space"] == "Display P3"
    np.testing.assert_allclose(captured["image_data"], image)


def test_heic_hdr_photo_rejects_cctf_or_clipped_input(tmp_path) -> None:
    image = np.full((1, 1, 3), 0.5, dtype=np.float32)

    with pytest.raises(ValueError, match="requires linear data"):
        save_image_oiio(
            str(tmp_path / "encoded.heic"),
            image,
            encoding=ColorEncoding(color_space="Display P3", transfer="cctf", role="display"),
        )

    with pytest.raises(ValueError, match="requires unclipped highlight data"):
        save_image_oiio(
            str(tmp_path / "clipped.heic"),
            image,
            encoding=ColorEncoding(color_space="Display P3", transfer="linear", role="scene"),
        )


def test_metadata_copy_keeps_png_icc_profile(tmp_path) -> None:
    destination = tmp_path / "destination.png"
    image = np.full((2, 2, 3), 0.5, dtype=np.float32)
    encoding = ColorEncoding(color_space="Display P3", transfer="cctf", role="display")

    save_image_oiio(str(destination), image, encoding=encoding)
    metadata = ImageMetadata(exif=exiv2.ExifData(), iptc=exiv2.IptcData(), xmp=exiv2.XmpData())

    write_image_metadata(str(destination), metadata)

    spec = _image_spec(destination)
    assert _icc_bytes_from_spec(spec)
    roundtrip_encoding = read_image_color_encoding(str(destination))
    assert roundtrip_encoding is not None
    assert roundtrip_encoding.color_space == "Display P3"


def test_metadata_copy_keeps_jpeg_icc_profile(tmp_path) -> None:
    destination = tmp_path / "destination.jpg"
    image = np.full((2, 2, 3), 0.5, dtype=np.float32)
    encoding = ColorEncoding(color_space="Display P3", transfer="cctf", role="display")

    save_image_oiio(str(destination), image, encoding=encoding)
    metadata = ImageMetadata(exif=exiv2.ExifData(), iptc=exiv2.IptcData(), xmp=exiv2.XmpData())

    write_image_metadata(str(destination), metadata)

    spec = _image_spec(destination)
    assert _icc_bytes_from_spec(spec)
    roundtrip_encoding = read_image_color_encoding(str(destination))
    assert roundtrip_encoding is not None
    assert roundtrip_encoding.color_space == "Display P3"


def test_chromaticities_matching_rejects_standard_primaries_with_wrong_whitepoint() -> None:
    chromaticities = np.asarray(colorspace_chromaticities("Display P3"), dtype=float)
    chromaticities[6:8] += np.array([0.001, -0.001], dtype=float)

    class FakeSpec:
        def getattribute(self, name):
            assert name == "chromaticities"
            return chromaticities

    assert _known_color_space_from_chromaticities(FakeSpec()) is None


def test_save_hdr_rendition_exr_produces_valid_output(tmp_path) -> None:
    """save_hdr_rendition_exr must produce an EXR with HDR metadata and distinct pixels."""
    path = tmp_path / "rendition.exr"
    image = np.full((1, 2, 3), 0.8, dtype=np.float32)
    scene_luminance = np.array([[0.8, 4.0]], dtype=np.float32)

    save_hdr_rendition_exr(
        str(path),
        image,
        color_space="Display P3",
        scene_luminance=scene_luminance,
        hdr_mapping_kwargs={
            "hdr_mapping_mode": "generic",
            "hdr_diffuse_lift_enabled": False,
            "max_headroom": 4.0,
        },
    )

    image_input = oiio.ImageInput.open(str(path))
    assert image_input is not None
    try:
        pixels = np.asarray(image_input.read_image(oiio.TypeDesc("float")), dtype=np.float32).reshape(image.shape)
        spec = image_input.spec()
    finally:
        image_input.close()

    assert float(pixels[0, 1].max()) > float(image[0, 1].max())
    assert not np.allclose(pixels, image)
    assert spec.getattribute("whiteLuminance") == pytest.approx(203.0)
    headroom = spec.getattribute("hdrHeadroom")
    assert headroom is not None
    assert float(headroom) > 1.0


def test_save_hdr_rendition_exr_returns_mapping_diagnostics(tmp_path) -> None:
    path = tmp_path / "rendition-diagnostics.exr"
    image = np.full((1, 2, 3), 0.8, dtype=np.float32)
    scene_luminance = np.array([[0.8, 4.0]], dtype=np.float32)
    scene_rgb = np.zeros((1, 2, 3), dtype=np.float32)

    diagnostics = save_hdr_rendition_exr(
        str(path),
        image,
        color_space="Display P3",
        scene_luminance=scene_luminance,
        scene_rgb=scene_rgb,
        hdr_mapping_kwargs={
            "hdr_mapping_mode": "profile_aware",
            "film": "kodak_portra_400",
            "paper": "kodak_ultra_endura",
            "hdr_highlight_color_mode": "source_chroma",
        },
    )

    assert any("degrading to off" in item for item in diagnostics)


def test_save_image_oiio_hdr_rendition_returns_mapping_diagnostics(tmp_path) -> None:
    path = tmp_path / "rendition-diagnostics-api.exr"
    image = np.full((1, 2, 3), 0.8, dtype=np.float32)
    scene_luminance = np.array([[0.8, 4.0]], dtype=np.float32)
    scene_rgb = np.zeros((1, 2, 3), dtype=np.float32)

    diagnostics = save_image_oiio(
        str(path),
        image,
        encoding=ColorEncoding(
            color_space="Display P3",
            transfer="linear",
            role="scene",
            clip_highlights=False,
        ),
        scene_luminance=scene_luminance,
        scene_rgb=scene_rgb,
        hdr_mapping_kwargs={
            "hdr_mapping_mode": "profile_aware",
            "film": "kodak_portra_400",
            "paper": "kodak_ultra_endura",
            "hdr_highlight_color_mode": "source_chroma",
        },
        exr_mode="hdr_rendition",
    )

    assert any("degrading to off" in item for item in diagnostics)


def test_save_hdr_rendition_exr_rejects_non_exr_extension(tmp_path) -> None:
    """save_hdr_rendition_exr must reject non-EXR file extensions."""
    with pytest.raises(ValueError, match="exr extension"):
        save_hdr_rendition_exr(
            str(tmp_path / "out.png"),
            np.full((1, 1, 3), 0.5, dtype=np.float32),
            color_space="sRGB",
        )
