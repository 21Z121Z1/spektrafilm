from __future__ import annotations

import struct
from pathlib import Path

from spektrafilm.utils.gain_map_metadata import GainMapChannel, GainMapMetadata
from spektrafilm.utils.heif_iso21496 import (
    repair_coreimage_tmap_min_max_order,
    validate_heif_iso21496,
)


def _box(box_type: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", len(payload) + 8, box_type) + payload


def _full_box(box_type: bytes, version: int, flags: int, payload: bytes) -> bytes:
    return _box(box_type, bytes([version]) + flags.to_bytes(3, "big") + payload)


def _infe(item_id: int, item_type: bytes, *, hidden: bool = False) -> bytes:
    flags = 1 if hidden else 0
    payload = (
        bytes([2]) + flags.to_bytes(3, "big")
        + struct.pack(">HH", item_id, 0)
        + item_type
        + b"\x00"
    )
    return _box(b"infe", payload)


def _iinf(*entries: bytes) -> bytes:
    return _full_box(b"iinf", 0, 0, struct.pack(">H", len(entries)) + b"".join(entries))


def _iref_dimg(targets: list[int]) -> bytes:
    child = _box(b"dimg", struct.pack(">HH", 4, len(targets)) + b"".join(struct.pack(">H", target) for target in targets))
    return _full_box(b"iref", 0, 0, child)


def _colr_prof() -> bytes:
    return _box(b"colr", b"prof" + b"test-profile")


def _colr_nclx(cp: int, tc: int, mc: int = 6) -> bytes:
    return _box(b"colr", b"nclx" + struct.pack(">HHHB", cp, tc, mc, 0x80))


def _pixi_rgb8() -> bytes:
    return _full_box(b"pixi", 0, 0, b"\x03\x08\x08\x08")


def _ipma_entry(item_id: int, property_indices: list[int]) -> bytes:
    return struct.pack(">HB", item_id, len(property_indices)) + bytes(property_indices)


def _iprp(
    *,
    include_base_colr: bool = True,
    gain_nclx_cp: int = 2,
    gain_nclx_tc: int = 2,
) -> bytes:
    props: list[bytes] = []
    base_colr_idx = None
    if include_base_colr:
        props.append(_colr_prof())
        base_colr_idx = len(props)
    props.append(_colr_nclx(gain_nclx_cp, gain_nclx_tc))
    gain_colr_idx = len(props)
    props.append(_colr_nclx(9, 16, 9))
    tmap_colr_idx = len(props)
    props.append(_pixi_rgb8())
    gain_pixi_idx = len(props)

    ipco = _box(b"ipco", b"".join(props))
    entries = []
    if base_colr_idx is not None:
        entries.append(_ipma_entry(1, [base_colr_idx]))
    entries.append(_ipma_entry(3, [gain_colr_idx, gain_pixi_idx]))
    entries.append(_ipma_entry(4, [tmap_colr_idx]))
    ipma = _full_box(b"ipma", 0, 0, struct.pack(">I", len(entries)) + b"".join(entries))
    return _box(b"iprp", ipco + ipma)


def _metadata_payload(
    *,
    bad_payload: bool = False,
    tmap_version: int = 0,
    swapped_min_max: bool = False,
) -> bytes:
    if bad_payload:
        return bytes([tmap_version]) + b"bad"
    ch = GainMapChannel(gain_map_min=0.0, gain_map_max=1.0, gamma=1.0, base_offset=1e-5, alternate_offset=1e-5)
    metadata = GainMapMetadata(
        is_multichannel=True,
        base_hdr_headroom=0.0,
        alternate_hdr_headroom=2.0,
        channels=(ch, ch, ch),
    )
    payload = bytearray(bytes([tmap_version]) + metadata.serialize())
    if swapped_min_max:
        for channel_index in range(3):
            offset = 1 + 21 + channel_index * 40
            min_bytes = bytes(payload[offset:offset + 8])
            max_bytes = bytes(payload[offset + 8:offset + 16])
            payload[offset:offset + 8] = max_bytes
            payload[offset + 8:offset + 16] = min_bytes
    return bytes(payload)


def _iloc(tmap_payload_len: int) -> bytes:
    entries = []
    for item_id, construction_method, offset, length in (
        (1, 0, 0, 0),
        (3, 0, 0, 0),
        (4, 1, 0, tmap_payload_len),
    ):
        entries.append(
            struct.pack(">HHHHII", item_id, construction_method, 0, 1, offset, length)
        )
    payload = b"\x44\x00" + struct.pack(">H", len(entries)) + b"".join(entries)
    return _full_box(b"iloc", 1, 0, payload)


def _heif_fixture(
    path: Path,
    *,
    brands: tuple[bytes, ...] = (b"mif1", b"tmap", b"heic"),
    dimg_targets: list[int] | None = None,
    gain_hidden: bool = True,
    base_hidden: bool = False,
    include_base_colr: bool = True,
    gain_nclx_cp: int = 2,
    gain_nclx_tc: int = 2,
    tmap_version: int = 0,
    bad_payload: bool = False,
    swapped_min_max: bool = False,
    tmap_item_type: bytes = b"tmap",
) -> Path:
    dimg_targets = [1, 3] if dimg_targets is None else dimg_targets
    tmap_payload = _metadata_payload(
        bad_payload=bad_payload,
        tmap_version=tmap_version,
        swapped_min_max=swapped_min_max,
    )
    ftyp = _box(b"ftyp", b"heic" + struct.pack(">I", 0) + b"".join(brands))
    meta = _full_box(
        b"meta",
        0,
        0,
        _full_box(b"pitm", 0, 0, struct.pack(">H", 1))
        + _iinf(
            _infe(1, b"hvc1", hidden=base_hidden),
            _infe(3, b"hvc1", hidden=gain_hidden),
            _infe(4, tmap_item_type),
        )
        + _iref_dimg(dimg_targets)
        + _iprp(include_base_colr=include_base_colr, gain_nclx_cp=gain_nclx_cp, gain_nclx_tc=gain_nclx_tc)
        + _box(b"idat", tmap_payload)
        + _iloc(len(tmap_payload)),
    )
    path.write_bytes(ftyp + meta)
    return path


def test_valid_heif_iso21496_graph(tmp_path) -> None:
    path = _heif_fixture(tmp_path / "valid.heic")

    result = validate_heif_iso21496(path)

    assert result.ok
    assert result.tmap_item_id == 4
    assert result.base_item_id == 1
    assert result.gain_map_item_id == 3
    assert result.metadata is not None
    assert result.metadata.alternate_hdr_headroom == 2.0


def test_missing_tmap_brand_is_error(tmp_path) -> None:
    path = _heif_fixture(tmp_path / "missing-brand.heic", brands=(b"mif1", b"heic"))

    result = validate_heif_iso21496(path)

    assert not result.ok
    assert any("compatible brands do not include tmap" in error for error in result.errors)


def test_tmap_brand_without_tmap_item_is_error(tmp_path) -> None:
    path = _heif_fixture(tmp_path / "brand-without-item.heic", tmap_item_type=b"hvc1")

    result = validate_heif_iso21496(path)

    assert not result.ok
    assert any("ftyp advertises tmap" in error for error in result.errors)
    assert any("No tmap derived image item" in error for error in result.errors)


def test_bad_tmap_dimg_is_error(tmp_path) -> None:
    path = _heif_fixture(tmp_path / "bad-dimg.heic", dimg_targets=[1])

    result = validate_heif_iso21496(path)

    assert not result.ok
    assert any("exactly two inputs" in error for error in result.errors)


def test_hidden_primary_item_is_error(tmp_path) -> None:
    path = _heif_fixture(tmp_path / "hidden-primary.heic", base_hidden=True)

    result = validate_heif_iso21496(path)

    assert not result.ok
    assert any("primary item 1 must not be hidden" in error for error in result.errors)


def test_missing_base_colr_is_error(tmp_path) -> None:
    path = _heif_fixture(tmp_path / "missing-base-colr.heic", include_base_colr=False)

    result = validate_heif_iso21496(path)

    assert not result.ok
    assert any("base input item 1 has no colr" in error for error in result.errors)


def test_non_hidden_gain_map_is_error(tmp_path) -> None:
    path = _heif_fixture(tmp_path / "visible-gain.heic", gain_hidden=False)

    result = validate_heif_iso21496(path)

    assert not result.ok
    assert any("is not hidden" in error for error in result.errors)


def test_invalid_gain_map_nclx_is_error(tmp_path) -> None:
    path = _heif_fixture(tmp_path / "bad-nclx.heic", gain_nclx_cp=1, gain_nclx_tc=1)

    result = validate_heif_iso21496(path)

    assert not result.ok
    assert any("colour_primaries must be 2" in error for error in result.errors)
    assert any("transfer_characteristics must be 2" in error for error in result.errors)


def test_bad_tmap_version_is_error(tmp_path) -> None:
    path = _heif_fixture(tmp_path / "bad-version.heic", tmap_version=1)

    result = validate_heif_iso21496(path)

    assert not result.ok
    assert any("ToneMapImage version must be 0" in error for error in result.errors)


def test_invalid_metadata_payload_is_error(tmp_path) -> None:
    path = _heif_fixture(tmp_path / "bad-payload.heic", bad_payload=True)

    result = validate_heif_iso21496(path)

    assert not result.ok
    assert any("GainMapMetadata payload is invalid" in error for error in result.errors)


def test_coreimage_min_max_order_repair(tmp_path) -> None:
    path = _heif_fixture(tmp_path / "swapped-range.heic", swapped_min_max=True)

    before = validate_heif_iso21496(path)
    assert not before.ok
    assert any("gain_map_max" in error for error in before.errors)

    assert repair_coreimage_tmap_min_max_order(path)
    after = validate_heif_iso21496(path)

    assert after.ok
    assert after.metadata is not None
    assert after.metadata.channels[0].gain_map_min == 0.0
    assert after.metadata.channels[0].gain_map_max == 1.0


def test_coreimage_min_max_order_repair_leaves_valid_file_unchanged(tmp_path) -> None:
    path = _heif_fixture(tmp_path / "already-valid.heic")
    original = path.read_bytes()

    assert not repair_coreimage_tmap_min_max_order(path)

    assert path.read_bytes() == original
