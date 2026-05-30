"""ISO 21496-1 Gain Map I/O — JPEG MPF and HEIF container support.

JPEG: CIPA DC-007 Multi-Picture Format (MPF) with APP2 ISO 21496-1 metadata.
HEIF: pillow-heif dual-image encode + ISOBMFF binary patch (when available).

Reference: XDRemux heif_io.py / isobmff_patch.py patterns.
"""

from __future__ import annotations

import io
import logging
import struct
from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image

from spektrafilm.utils.gain_map import (
    apply_gain_map,
    compute_gain_map,
    compute_weight,
    denormalize_gain_map,
    normalize_gain_map,
)
from spektrafilm.utils.gain_map_metadata import GainMapChannel, GainMapMetadata

_log = logging.getLogger(__name__)

# JPEG MPF APP2 URN for ISO 21496-1
_ISO21496_URN = b"urn:iso:std:iso:ts:21496:-1"
_APP2_MARKER = b"\xff\xe2"

# JPEG markers
_SOI = b"\xff\xd8"
_EOI = b"\xff\xd9"


def save_gain_map_jpeg(
    output_path: str | Path,
    base_image: np.ndarray,
    gain_map: np.ndarray,
    metadata: GainMapMetadata,
    *,
    base_quality: int = 95,
    gain_map_quality: int = 90,
) -> None:
    """Save SDR base + gain map as a JPEG file with MPF (ISO 21496-1 C.4).

    Parameters
    ----------
    output_path : str | Path
        Output JPEG file path.
    base_image : np.ndarray
        SDR base image, shape (H, W, 3), float32 in [0, 1] or uint8.
    gain_map : np.ndarray
        Normalized gain map in [0, 1], shape (H, W, 3) or (H, W), float32.
    metadata : GainMapMetadata
        ISO 21496-1 metadata.
    base_quality : int
        JPEG quality for base image (1-100).
    gain_map_quality : int
        JPEG quality for gain map (1-100).
    """
    output_path = Path(output_path)

    # Encode base image to JPEG bytes
    base_img = _to_pil_image(base_image)
    base_buf = io.BytesIO()
    base_img.save(base_buf, format="JPEG", quality=base_quality)
    base_jpeg = base_buf.getvalue()

    # Encode gain map to JPEG bytes
    gm_img = _to_pil_image(gain_map, is_gain_map=True)
    gm_buf = io.BytesIO()
    gm_img.save(gm_buf, format="JPEG", quality=gain_map_quality)
    gm_jpeg = gm_buf.getvalue()

    # Build MPF payload
    metadata_bytes = metadata.serialize()
    xmp_payload = metadata.to_xmp().encode("utf-8")

    mpf_data = _build_mpf_jpeg(base_jpeg, gm_jpeg, metadata_bytes, xmp_payload)

    with open(output_path, "wb") as f:
        f.write(mpf_data)


def save_gain_map_heif(
    output_path: str | Path,
    base_image: np.ndarray,
    gain_map: np.ndarray,
    metadata: GainMapMetadata,
    *,
    quality: int = 90,
) -> None:
    """Save SDR base + gain map as a HEIF file with ISO 21496-1 tmap.

    Requires pillow-heif. Use :func:`save_gain_map_jpeg` explicitly when a
    JPEG/MPF fallback is desired.

    Parameters
    ----------
    output_path : str | Path
        Output HEIF file path.
    base_image : np.ndarray
        SDR base image, shape (H, W, 3), float32 in [0, 1] or uint8.
    gain_map : np.ndarray
        Normalized gain map in [0, 1], shape (H, W, 3) or (H, W), float32.
    metadata : GainMapMetadata
        ISO 21496-1 metadata.
    quality : int
        HEIF encoding quality (1-100).
    """
    try:
        from pillow_heif import from_pillow
    except ImportError as exc:
        raise ImportError("pillow-heif is required for HEIF gain map output.") from exc

    output_path = Path(output_path)
    base_img = _to_pil_image(base_image)
    gm_img = _to_pil_image(gain_map, is_gain_map=True)

    # Ensure RGB mode for HEIF
    if base_img.mode != "RGB":
        base_img = base_img.convert("RGB")

    heif = from_pillow(base_img)
    heif.add_from_pillow(gm_img)
    heif.save(str(output_path), quality=quality, chroma="444")

    # Patch for ISO 21496-1 compliance
    try:
        iso_meta = _gainmap_metadata_to_iso_dict(metadata)
        _patch_heif_for_iso21496(str(output_path), iso_meta)
    except Exception as e:
        _log.warning("ISO 21496-1 HEIF patching failed: %s", e)


def load_gain_map(path: str | Path) -> dict:
    """Load a gain map from a JPEG (MPF) or HEIF file.

    Parameters
    ----------
    path : str | Path
        Path to a JPEG or HEIF file with an embedded gain map.

    Returns
    -------
    dict
        Keys: 'base_image' (PIL.Image), 'gain_map' (PIL.Image),
        'metadata' (GainMapMetadata), 'format' ('jpeg' or 'heif').
    """
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix in (".jpg", ".jpeg"):
        return _load_gain_map_jpeg(path)
    elif suffix in (".heic", ".heif"):
        return _load_gain_map_heif(path)
    else:
        raise ValueError(f"Unsupported format for gain map loading: {suffix}")


# ---------------------------------------------------------------------------
# JPEG MPF implementation
# ---------------------------------------------------------------------------


def _build_mpf_jpeg(
    base_jpeg: bytes,
    gain_map_jpeg: bytes,
    metadata_bytes: bytes,
    xmp_payload: bytes,
) -> bytes:
    """Build a JPEG file with MPF containing a gain map.

    Structure:
    - SOI
    - APP2: GainMapVersion (base image)
    - APP2: XMP metadata
    - Base image JPEG data (without SOI/EOI)
    - MPF APP2 segment pointing to gain map
    - Gain map JPEG data (second image)
    - EOI
    """
    if not base_jpeg.startswith(_SOI):
        raise ValueError("base_jpeg is not a valid JPEG (missing SOI)")

    # Strip SOI/EOI from base JPEG
    base_data = base_jpeg[2:]
    if base_data.endswith(_EOI):
        base_data = base_data[:-2]

    # Strip SOI/EOI from gain map JPEG
    gm_data = gain_map_jpeg[2:] if gain_map_jpeg.startswith(_SOI) else gain_map_jpeg
    if gm_data.endswith(_EOI):
        gm_data = gm_data[:-2]

    out = bytearray()
    out += _SOI

    # APP2: ISO 21496-1 GainMapVersion for base image
    out += _build_app2_segment(b"urn:iso:std:iso:ts:21496:-1\x00" + metadata_bytes)

    # APP2: XMP metadata
    out += _build_app2_segment(b"http://ns.adobe.com/xap/1.0/\x00" + xmp_payload)

    # Base image data
    out += base_data

    # MPF APP2 segment
    base_offset = len(out)
    mpf_payload = _build_mpf_payload(base_offset, len(base_jpeg), len(gm_data) + len(_EOI))
    out += _build_app2_segment(b"MPF\x00" + mpf_payload)

    # Gain map data
    out += gm_data
    out += _EOI

    return bytes(out)


def _build_app2_segment(payload: bytes) -> bytes:
    """Build a JPEG APP2 segment."""
    # APP2 marker (2) + length (2) + payload
    segment_length = len(payload) + 2
    if segment_length > 0xFFFF:
        raise ValueError(f"APP2 segment too large: {segment_length} bytes")
    return _APP2_MARKER + struct.pack(">H", segment_length) + payload


def _build_mpf_payload(base_offset: int, base_length: int, gm_length: int) -> bytes:
    """Build MPF APP2 payload for two images (base + gain map).

    Follows CIPA DC-007 Multi-Picture Format.
    """
    # MPF header
    payload = bytearray()
    payload += b"0100"  # MP format version
    payload += struct.pack(">I", 2)  # number of images

    # MP Entry for image 1 (base)
    payload += struct.pack(">I", 0)  # MP Entry flags (individual image)
    payload += struct.pack(">I", base_length)  # individual image size
    payload += struct.pack(">I", 0)  # data offset (0 = first image)

    # MP Entry for image 2 (gain map)
    payload += struct.pack(">I", 0x02000000)  # MP Entry flags (gain map / thumbnail)
    payload += struct.pack(">I", gm_length)  # individual image size
    payload += struct.pack(">I", base_offset)  # data offset from MPF APP2

    return bytes(payload)


# ---------------------------------------------------------------------------
# HEIF ISO 21496-1 patching (portable subset)
# ---------------------------------------------------------------------------


def _patch_heif_for_iso21496(path: str, iso_meta: dict) -> bool:
    """Patch a HEIF file for ISO 21496-1 compliance.

    Uses the same approach as XDRemux's isobmff_patch.py: add auxC property,
    create tmap item, link via iref/dimg.
    """
    try:
        from spektrafilm.utils import _isobmff_patch as patcher
        return patcher.patch_heic_for_iso21496(path, iso_meta=iso_meta)
    except ImportError:
        pass

    log.warning("_isobmff_patch module not available; skipping ISO 21496-1 HEIF brand patching")
    return False


def _gainmap_metadata_to_iso_dict(metadata: GainMapMetadata) -> dict:
    """Convert GainMapMetadata to the ISO dict format used by isobmff_patch."""
    ch = metadata.channels[0]
    return {
        "gainMapMin": [ch.gain_map_min] * 3,
        "gainMapMax": [ch.gain_map_max] * 3,
        "gamma": [ch.gamma] * 3,
        "offsetSdr": [ch.base_offset] * 3,
        "offsetHdr": [ch.alternate_offset] * 3,
        "hdrCapacityMin": metadata.base_hdr_headroom,
        "hdrCapacityMax": metadata.alternate_hdr_headroom,
        "baseRenditionIsHDR": metadata.base_hdr_headroom > 0,
    }


# ---------------------------------------------------------------------------
# Gain map loading
# ---------------------------------------------------------------------------


def _load_gain_map_jpeg(path: Path) -> dict:
    """Load gain map from a JPEG MPF file."""
    data = path.read_bytes()

    if not data.startswith(_SOI):
        raise ValueError("Not a valid JPEG file")

    # Parse APP2 segments
    metadata_bytes = None
    xmp_payload = None
    offset = 2  # Skip SOI

    while offset < len(data) - 4:
        if data[offset] != 0xFF:
            break
        marker = data[offset:offset + 2]
        if marker == _EOI:
            break

        if marker[1] == 0x00 or marker[1] == 0xFF:
            offset += 1
            continue

        if offset + 4 > len(data):
            break
        length = struct.unpack_from(">H", data, offset + 2)[0]
        segment_data = data[offset + 4 : offset + 2 + length]

        if marker == _APP2_MARKER:
            # Check for ISO 21496-1 URN
            urn_prefix = b"urn:iso:std:iso:ts:21496:-1"
            if segment_data.startswith(urn_prefix):
                metadata_bytes = segment_data[len(urn_prefix) + 1:]
            # Check for XMP
            xmp_prefix = b"http://ns.adobe.com/xap/1.0/"
            if segment_data.startswith(xmp_prefix):
                xmp_payload = segment_data[len(xmp_prefix) + 1:]

        offset += 2 + length

    # Parse MPF to find gain map offset
    gm_data = _extract_mpf_gain_map(data)

    # Build base image from full JPEG
    base_img = Image.open(io.BytesIO(data))

    result = {
        "base_image": base_img,
        "gain_map": None,
        "metadata": None,
        "format": "jpeg",
    }

    if gm_data is not None:
        try:
            result["gain_map"] = Image.open(io.BytesIO(gm_data))
        except Exception:
            pass

    if metadata_bytes is not None:
        try:
            result["metadata"] = GainMapMetadata.deserialize(metadata_bytes)
        except Exception:
            pass

    return result


def _extract_mpf_gain_map(jpeg_data: bytes) -> bytes | None:
    """Extract the gain map image from MPF APP2 data."""
    offset = 2  # Skip SOI

    while offset < len(jpeg_data) - 4:
        if jpeg_data[offset] != 0xFF:
            break
        marker = jpeg_data[offset:offset + 2]
        if marker == _EOI:
            break

        if marker[1] == 0x00 or marker[1] == 0xFF:
            offset += 1
            continue

        if offset + 4 > len(jpeg_data):
            break
        length = struct.unpack_from(">H", jpeg_data, offset + 2)[0]
        segment_data = jpeg_data[offset + 4 : offset + 2 + length]

        if marker == _APP2_MARKER and segment_data.startswith(b"MPF\x00"):
            mpf_data = segment_data[4:]
            return _parse_mpf_gain_map(jpeg_data, mpf_data)

        offset += 2 + length

    return None


def _parse_mpf_gain_map(jpeg_data: bytes, mpf_data: bytes) -> bytes | None:
    """Parse MPF data to extract gain map image bytes."""
    if len(mpf_data) < 16:
        return None

    # Parse MP header
    num_images = struct.unpack_from(">I", mpf_data, 4)[0]
    if num_images < 2:
        return None

    # Parse MP Entry for image 2 (gain map)
    # Each entry: 4 (flags) + 4 (size) + 4 (offset) = 12 bytes
    entry_offset = 8 + 12  # Skip header + first entry
    if len(mpf_data) < entry_offset + 12:
        return None

    gm_size = struct.unpack_from(">I", mpf_data, entry_offset + 4)[0]
    gm_data_offset = struct.unpack_from(">I", mpf_data, entry_offset + 8)[0]

    # The offset is relative to the MPF APP2 segment start
    # Find the MPF APP2 position in the JPEG
    app2_pos = _find_mpf_app2_position(jpeg_data)
    if app2_pos is None:
        return None

    gm_start = app2_pos + gm_data_offset
    gm_end = gm_start + gm_size
    if gm_end > len(jpeg_data):
        return None

    # The gain map data should start with SOI
    gm_bytes = jpeg_data[gm_start:gm_end]
    if not gm_bytes.startswith(_SOI):
        gm_bytes = _SOI + gm_bytes

    return gm_bytes


def _find_mpf_app2_position(jpeg_data: bytes) -> int | None:
    """Find the file position of the MPF APP2 segment."""
    offset = 2  # Skip SOI

    while offset < len(jpeg_data) - 4:
        if jpeg_data[offset] != 0xFF:
            break
        marker = jpeg_data[offset:offset + 2]
        if marker == _EOI:
            break

        if marker[1] == 0x00 or marker[1] == 0xFF:
            offset += 1
            continue

        if offset + 4 > len(jpeg_data):
            break
        length = struct.unpack_from(">H", jpeg_data, offset + 2)[0]
        segment_data = jpeg_data[offset + 4 : offset + 2 + length]

        if marker == _APP2_MARKER and segment_data.startswith(b"MPF\x00"):
            return offset

        offset += 2 + length

    return None


def _load_gain_map_heif(path: Path) -> dict:
    """Load gain map from a HEIF file."""
    try:
        from pillow_heif import open_heif
    except ImportError:
        raise ImportError("pillow-heif is required to load HEIF gain maps.") from None

    heif_img = open_heif(str(path), convert_hdr_to_8bit=False)
    base = heif_img[0] if hasattr(heif_img, "__getitem__") else heif_img
    base_image = base.to_pillow()

    gain_map = None
    if len(heif_img) > 1:
        gm = heif_img[1]
        gain_map = gm.to_pillow()

    return {
        "base_image": base_image,
        "gain_map": gain_map,
        "metadata": None,  # Would need ISOBMFF parsing to extract
        "format": "heif",
    }


# ---------------------------------------------------------------------------
# Image conversion helpers
# ---------------------------------------------------------------------------


def _to_pil_image(
    array: np.ndarray,
    *,
    is_gain_map: bool = False,
) -> Image.Image:
    """Convert a numpy array to a PIL Image suitable for JPEG/HEIF encoding."""
    arr = np.asarray(array)

    if arr.dtype == np.float32 or arr.dtype == np.float64:
        if is_gain_map:
            # Gain map: normalize to [0, 255] uint8
            arr = np.clip(arr * 255.0, 0, 255).astype(np.uint8)
        else:
            # SDR base: assume [0, 1] range
            arr = np.clip(arr * 255.0, 0, 255).astype(np.uint8)
    elif arr.dtype != np.uint8:
        arr = arr.astype(np.uint8)

    if arr.ndim == 2:
        return Image.fromarray(arr, mode="L")
    if arr.ndim == 3:
        if arr.shape[2] == 1:
            return Image.fromarray(arr[:, :, 0], mode="L")
        if arr.shape[2] >= 3:
            return Image.fromarray(arr[:, :, :3], mode="RGB")

    raise ValueError(f"Unsupported array shape for image conversion: {arr.shape}")
