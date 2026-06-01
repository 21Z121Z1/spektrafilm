"""ISO 21496-1 Gain Map Metadata binary serialization.

Implements the GainMapMetadata binary payload (ISO 21496-1:2025 C.2.2):
- Big-endian rational number encoding (int32/uint32 numerator/denominator pairs)
- Per-channel gain map parameters (min, max, gamma, base_offset, alternate_offset)
- HDR headroom as rational pairs
- Flags: is_multichannel, use_base_colour_space
- XMP serialization for Adobe hdrgm namespace compatibility
"""

from __future__ import annotations

import struct
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Sequence


def _float_to_rational(value: float) -> tuple[int, int]:
    """Encode a float as an int32/uint32 rational pair with 1/10000 precision."""
    if value == 0.0:
        return 0, 1
    numerator = int(round(value * 10000))
    return numerator, 10000


def _float_to_unsigned_rational(value: float) -> tuple[int, int]:
    """Encode a non-negative float as a uint32/uint32 rational pair."""
    if value == 0.0:
        return 0, 1
    numerator = max(1, int(round(value * 10000)))
    return numerator, 10000


def _rational_to_float(num: int, den: int) -> float:
    """Decode a rational pair to float."""
    if den == 0:
        return 0.0
    return num / den


@dataclass(frozen=True, slots=True)
class GainMapChannel:
    """Per-channel gain map metadata (ISO 21496-1 C.2.2 GainMapChannel).

    Each field is stored as a rational (numerator, denominator) pair.
    """

    gain_map_min: float = 0.0
    gain_map_max: float = 1.0
    gamma: float = 1.0
    base_offset: float = 0.0
    alternate_offset: float = 0.0


@dataclass(frozen=True, slots=True)
class GainMapMetadata:
    """ISO 21496-1 GainMapMetadata (C.2.2).

    Matches the binary payload structure for JPEG APP2 and HEIF tmap embedding.
    """

    minimum_version: int = 0
    writer_version: int = 0
    is_multichannel: bool = True
    use_base_colour_space: bool = True
    base_hdr_headroom: float = 0.0
    alternate_hdr_headroom: float = 3.0
    channels: tuple[GainMapChannel, ...] = field(default_factory=lambda: (GainMapChannel(),))

    def __post_init__(self) -> None:
        if self.minimum_version < 0 or self.minimum_version > 65535:
            raise ValueError("minimum_version must be in [0, 65535].")
        if self.writer_version < 0 or self.writer_version > 65535:
            raise ValueError("writer_version must be in [0, 65535].")
        expected = 3 if self.is_multichannel else 1
        if len(self.channels) != expected:
            raise ValueError(
                f"Expected {expected} channels for is_multichannel={self.is_multichannel}, "
                f"got {len(self.channels)}."
            )
        if self.base_hdr_headroom > self.alternate_hdr_headroom:
            raise ValueError(
                f"base_hdr_headroom ({self.base_hdr_headroom}) must be <= "
                f"alternate_hdr_headroom ({self.alternate_hdr_headroom})."
            )

    def serialize(self) -> bytes:
        """Serialize to big-endian binary payload per ISO 21496-1 C.2.2.

        Returns
        -------
        bytes
            Binary GainMapMetadata payload.
        """
        buf = bytearray()

        # GainMapVersion (4 bytes)
        buf += struct.pack(">HH", self.minimum_version, self.writer_version)

        # Flags byte: bit 7 = is_multichannel, bit 6 = use_base_colour_space
        flags = (int(self.is_multichannel) << 7) | (int(self.use_base_colour_space) << 6)
        buf += struct.pack(">B", flags)

        # HDR headroom as rational pairs
        buf += _pack_rational(self.base_hdr_headroom)
        buf += _pack_rational(self.alternate_hdr_headroom)

        # Per-channel metadata
        for ch in self.channels:
            buf += _pack_rational(ch.gain_map_min)
            buf += _pack_rational(ch.gain_map_max)
            buf += _pack_unsigned_rational(ch.gamma)
            buf += _pack_rational(ch.base_offset)
            buf += _pack_rational(ch.alternate_offset)

        return bytes(buf)

    @classmethod
    def deserialize(cls, data: bytes) -> GainMapMetadata:
        """Deserialize from a big-endian binary payload.

        Parameters
        ----------
        data : bytes
            Binary GainMapMetadata payload.

        Returns
        -------
        GainMapMetadata
            Parsed metadata.
        """
        if len(data) < 15:
            raise ValueError(f"GainMapMetadata payload too short: {len(data)} bytes (min 15).")

        offset = 0

        # GainMapVersion
        minimum_version, writer_version = struct.unpack_from(">HH", data, offset)
        offset += 4

        # Flags
        flags = struct.unpack_from(">B", data, offset)[0]
        offset += 1
        is_multichannel = bool(flags & 0x80)
        use_base_colour_space = bool(flags & 0x40)

        # HDR headroom
        base_hdr_headroom = _unpack_rational(data, offset)
        offset += 8
        alternate_hdr_headroom = _unpack_rational(data, offset)
        offset += 8

        # Per-channel metadata
        channel_count = 3 if is_multichannel else 1
        expected_len = 15 + channel_count * 40
        if len(data) < expected_len:
            raise ValueError(
                f"GainMapMetadata payload too short for {channel_count} channels: "
                f"{len(data)} bytes (need {expected_len})."
            )

        channels: list[GainMapChannel] = []
        for _ in range(channel_count):
            g_min = _unpack_rational(data, offset)
            offset += 8
            g_max = _unpack_rational(data, offset)
            offset += 8
            gamma = _unpack_unsigned_rational(data, offset)
            offset += 8
            b_off = _unpack_rational(data, offset)
            offset += 8
            a_off = _unpack_rational(data, offset)
            offset += 8
            channels.append(GainMapChannel(
                gain_map_min=g_min,
                gain_map_max=g_max,
                gamma=gamma,
                base_offset=b_off,
                alternate_offset=a_off,
            ))

        return cls(
            minimum_version=minimum_version,
            writer_version=writer_version,
            is_multichannel=is_multichannel,
            use_base_colour_space=use_base_colour_space,
            base_hdr_headroom=base_hdr_headroom,
            alternate_hdr_headroom=alternate_hdr_headroom,
            channels=tuple(channels),
        )

    def to_xmp(self, *, gain_map_length: int | None = None) -> str:
        """Serialize to XMP XML string using Adobe hdrgm namespace.

        Returns
        -------
        str
            UTF-8 XMP packet suitable for JPEG APP1 or HEIC metadata.
        """
        ch = self.channels[0]
        gain_map_length_attr = "" if gain_map_length is None else f'\n                  Item:Length="{int(gain_map_length)}"'
        return (
            '<?xpacket begin="\xef\xbb\xbf" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
            '<x:xmpmeta xmlns:x="adobe:ns:meta/">\n'
            '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
            '<rdf:Description rdf:about=""\n'
            '  xmlns:hdrgm="http://ns.adobe.com/hdr-gain-map/1.0/"\n'
            '  xmlns:Container="http://ns.google.com/photos/1.0/container/"\n'
            '  xmlns:Item="http://ns.google.com/photos/1.0/container/item/">\n'
            f'  <hdrgm:Version>1.0</hdrgm:Version>\n'
            f'  <hdrgm:GainMapMin>{ch.gain_map_min:.6g}</hdrgm:GainMapMin>\n'
            f'  <hdrgm:GainMapMax>{ch.gain_map_max:.6g}</hdrgm:GainMapMax>\n'
            f'  <hdrgm:Gamma>{ch.gamma:.6g}</hdrgm:Gamma>\n'
            f'  <hdrgm:OffsetSDR>{ch.base_offset:.6g}</hdrgm:OffsetSDR>\n'
            f'  <hdrgm:OffsetHDR>{ch.alternate_offset:.6g}</hdrgm:OffsetHDR>\n'
            f'  <hdrgm:HDRCapacityMin>{self.base_hdr_headroom:.6g}</hdrgm:HDRCapacityMin>\n'
            f'  <hdrgm:HDRCapacityMax>{self.alternate_hdr_headroom:.6g}</hdrgm:HDRCapacityMax>\n'
            f'  <hdrgm:BaseRenditionIsHDR>{"True" if self.base_hdr_headroom > 0 else "False"}</hdrgm:BaseRenditionIsHDR>\n'
            '  <Container:Directory>\n'
            '    <rdf:Seq>\n'
            '      <rdf:li rdf:parseType="Resource">\n'
            '        <Container:Item Item:Semantic="Primary" Item:Mime="image/jpeg"/>\n'
            '      </rdf:li>\n'
            '      <rdf:li rdf:parseType="Resource">\n'
            f'        <Container:Item Item:Semantic="GainMap" Item:Mime="image/jpeg"{gain_map_length_attr}/>\n'
            '      </rdf:li>\n'
            '    </rdf:Seq>\n'
            '  </Container:Directory>\n'
            '</rdf:Description>\n'
            '</rdf:RDF>\n'
            '</x:xmpmeta>\n'
            '<?xpacket end="w"?>'
        )


# --- Binary packing helpers ---


def _pack_rational(value: float) -> bytes:
    """Pack a float as a big-endian int32/uint32 rational pair."""
    num, den = _float_to_rational(value)
    return struct.pack(">iI", num, den)


def _pack_unsigned_rational(value: float) -> bytes:
    """Pack a non-negative float as a big-endian uint32/uint32 rational pair."""
    num, den = _float_to_unsigned_rational(value)
    return struct.pack(">II", num, den)


def _unpack_rational(data: bytes, offset: int) -> float:
    """Unpack a big-endian int32/uint32 rational pair to float."""
    num, den = struct.unpack_from(">iI", data, offset)
    return _rational_to_float(num, den)


def _unpack_unsigned_rational(data: bytes, offset: int) -> float:
    """Unpack a big-endian uint32/uint32 rational pair to float."""
    num, den = struct.unpack_from(">II", data, offset)
    return _rational_to_float(num, den)
