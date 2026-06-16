"""Focused HEIF ISO 21496-1 / ISO/IEC 23008-12 tmap validation.

This module validates the item graph and metadata payload needed for gain-map
HDR HEIC output. It is intentionally not a HEVC decoder and does not inspect
pixel payloads beyond item locations and the tmap metadata item body.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from spektrafilm.utils.gain_map_metadata import GainMapMetadata


class HEIFISO21496Error(ValueError):
    """Raised when a HEIF file cannot be parsed for ISO 21496-1 validation."""


@dataclass(frozen=True, slots=True)
class HEIFISO21496ValidationResult:
    """Validation result for a HEIF tmap gain-map file."""

    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    tmap_item_id: int | None = None
    base_item_id: int | None = None
    gain_map_item_id: int | None = None
    metadata: GainMapMetadata | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_heif_iso21496(
    path: str | Path,
    *,
    require_tmap: bool = True,
) -> HEIFISO21496ValidationResult:
    """Validate a HEIF file against the ISO tmap gain-map structure.

    The hard checks map to ISO/IEC 23008-12 Amd.1 tone-map derivation and the
    ISO 21496-1 C.2 binary metadata payload. Advisory "should" requirements are
    returned as warnings so Mac-compatible files are not rejected for optional
    viewing hints.
    """

    path = Path(path)
    try:
        data = path.read_bytes()
        parsed = parse_heif(data, source=str(path))
    except Exception as exc:
        return HEIFISO21496ValidationResult(errors=(f"HEIF parse failed: {exc}",))
    return validate_parsed_heif_iso21496(parsed, require_tmap=require_tmap)


def repair_coreimage_tmap_min_max_order(path: str | Path) -> bool:
    """Repair CoreImage tmap payloads that store channel max/min in draft order.

    Some macOS CoreImage HEIC gain-map output has been observed to write the two
    per-channel gain-map range fields in the opposite order from ISO 21496-1 C.2:
    the first value is positive and the second is zero for ordinary HDR-up pairs.
    This function performs an in-place, same-size repair only when every channel
    exhibits that exact invalid ``min > max`` pattern. Arbitrary malformed files
    are left untouched so the normal validator can fail closed.
    """

    path = Path(path)
    try:
        data = bytearray(path.read_bytes())
        parsed = parse_heif(bytes(data), source=str(path))
    except Exception:
        return False

    repaired = False
    for item in parsed.get("items", {}).values():
        if item.get("item_type") != "tmap":
            continue
        extents = item.get("extents") or []
        if len(extents) != 1:
            continue
        start = int(extents[0].get("absolute_offset", extents[0].get("offset", 0)))
        length = int(extents[0].get("length", 0))
        end = start + length
        if start < 0 or end > len(data) or length < 22:
            continue
        if data[start] != 0:
            continue

        body_start = start + 1
        body = memoryview(data)[body_start:end]
        minimum_version = struct.unpack_from(">H", body, 0)[0]
        if minimum_version != 0:
            continue
        flags = body[4]
        channel_count = 3 if flags & 0x80 else 1
        required_body_len = 21 + channel_count * 40
        if len(body) < required_body_len:
            continue

        channel_offsets = [body_start + 21 + channel_index * 40 for channel_index in range(channel_count)]
        channel_ranges: list[tuple[float, float]] = []
        try:
            for channel_offset in channel_offsets:
                min_value = _read_signed_rational_value(data, channel_offset)
                max_value = _read_signed_rational_value(data, channel_offset + 8)
                channel_ranges.append((min_value, max_value))
        except ValueError:
            continue
        if not channel_ranges or not all(min_value > max_value for min_value, max_value in channel_ranges):
            continue

        for channel_offset in channel_offsets:
            min_bytes = bytes(data[channel_offset:channel_offset + 8])
            max_bytes = bytes(data[channel_offset + 8:channel_offset + 16])
            data[channel_offset:channel_offset + 8] = max_bytes
            data[channel_offset + 8:channel_offset + 16] = min_bytes
        repaired = True

    if repaired:
        path.write_bytes(data)
    return repaired


def validate_parsed_heif_iso21496(
    parsed: dict[str, Any],
    *,
    require_tmap: bool = True,
) -> HEIFISO21496ValidationResult:
    """Validate an already parsed HEIF structure."""

    errors: list[str] = []
    warnings: list[str] = []
    ftyp = parsed.get("ftyp") or {}
    brands = set(ftyp.get("compatible_brands") or [])
    items: dict[str, dict[str, Any]] = parsed.get("items") or {}
    primary_item_id = parsed.get("primary_item_id")
    tmap_items = [item for item in items.values() if item.get("item_type") == "tmap"]

    if primary_item_id is not None:
        primary_item = items.get(str(primary_item_id))
        if primary_item is None:
            errors.append(f"primary item {primary_item_id} is missing.")
        elif bool(primary_item.get("hidden")):
            errors.append(f"primary item {primary_item_id} must not be hidden.")

    if "tmap" in brands and not tmap_items:
        errors.append("ftyp advertises tmap but no tmap item is present.")
    if require_tmap and not tmap_items:
        errors.append("No tmap derived image item is present.")
    if tmap_items and "tmap" not in brands:
        errors.append("A tmap derived image item is present but ftyp compatible brands do not include tmap.")
    if len(tmap_items) > 1:
        warnings.append(f"Multiple tmap items present; validating the first of {len(tmap_items)}.")

    tmap_item = tmap_items[0] if tmap_items else None
    tmap_item_id = int(tmap_item["item_id"]) if tmap_item is not None else None
    base_item: dict[str, Any] | None = None
    gain_map_item: dict[str, Any] | None = None
    metadata: GainMapMetadata | None = None

    if tmap_item is not None:
        dimg_refs = [
            ref for ref in parsed.get("references", [])
            if ref.get("type") == "dimg" and ref.get("from_item_id") == tmap_item_id
        ]
        if len(dimg_refs) != 1:
            errors.append(f"tmap item {tmap_item_id} must have exactly one dimg reference.")
        child_ids = list(dimg_refs[0].get("to_item_ids", [])) if dimg_refs else []
        if len(child_ids) != 2:
            errors.append(f"tmap item {tmap_item_id} dimg must reference exactly two inputs.")
        else:
            base_item = items.get(str(child_ids[0]))
            gain_map_item = items.get(str(child_ids[1]))
            if base_item is None:
                errors.append(f"tmap base input item {child_ids[0]} is missing.")
            if gain_map_item is None:
                errors.append(f"tmap gain-map input item {child_ids[1]} is missing.")

        if base_item is not None and not base_item.get("colr"):
            errors.append(f"tmap base input item {base_item['item_id']} has no colr property.")

        if gain_map_item is not None:
            if not bool(gain_map_item.get("hidden")):
                errors.append(f"tmap gain-map input item {gain_map_item['item_id']} is not hidden.")
            gain_colr = gain_map_item.get("colr") or {}
            if gain_colr.get("color_type") != "nclx":
                errors.append(f"tmap gain-map input item {gain_map_item['item_id']} colr is not nclx.")
            else:
                if gain_colr.get("colour_primaries") != 2:
                    errors.append("tmap gain-map input nclx colour_primaries must be 2.")
                if gain_colr.get("transfer_characteristics") != 2:
                    errors.append("tmap gain-map input nclx transfer_characteristics must be 2.")
            pixi = gain_map_item.get("pixi") or {}
            channels = pixi.get("channels")
            if channels is not None and channels not in (1, 3):
                errors.append(f"tmap gain-map input pixi channel count must be 1 or 3, got {channels}.")
            bits = pixi.get("bits") or []
            if bits and any(int(bit) < 8 for bit in bits):
                warnings.append("tmap gain-map input bit depth is below the ISO 21496-1 recommended 8 bits.")

        tmap_colr = tmap_item.get("colr") or {}
        if not tmap_colr:
            errors.append(f"tmap item {tmap_item_id} has no alternate colr property.")

        _check_orientation_match(base_item, gain_map_item, tmap_item, errors, warnings)
        _check_clli(base_item, tmap_item, warnings)

        payload = _payload_from_item_extents(parsed.get("_data", b""), tmap_item)
        if not payload:
            errors.append(f"tmap item {tmap_item_id} has no ToneMapImage payload.")
        elif payload[0] != 0:
            errors.append(f"tmap ToneMapImage version must be 0, got {payload[0]}.")
        else:
            try:
                metadata = GainMapMetadata.deserialize(payload[1:])
            except Exception as exc:
                errors.append(f"tmap GainMapMetadata payload is invalid: {exc}")

    details = {
        "major_brand": ftyp.get("major_brand"),
        "compatible_brands": tuple(ftyp.get("compatible_brands") or ()),
        "item_count": len(items),
    }
    return HEIFISO21496ValidationResult(
        errors=tuple(errors),
        warnings=tuple(warnings),
        tmap_item_id=tmap_item_id,
        base_item_id=int(base_item["item_id"]) if base_item is not None else None,
        gain_map_item_id=int(gain_map_item["item_id"]) if gain_map_item is not None else None,
        metadata=metadata,
        details=details,
    )


def parse_heif(data: bytes, source: str | None = None) -> dict[str, Any]:
    """Parse the HEIF boxes needed by the ISO 21496-1 validator."""

    top_boxes = _iter_boxes(data)
    result: dict[str, Any] = {
        "_data": data,
        "source": source,
        "file_size": len(data),
        "boxes": _box_summary(top_boxes),
        "ftyp": {},
        "primary_item_id": None,
        "items": {},
        "properties": [],
        "references": [],
    }
    for top in top_boxes:
        if top["type"] == "ftyp":
            result["ftyp"] = _parse_ftyp(data, top)
            continue
        if top["type"] != "meta":
            continue
        _version, _flags, meta_child_start = _read_fullbox(data, top["payload_offset"])
        meta_end = top["payload_offset"] + top["payload_size"]
        meta_children = _iter_boxes(data, meta_child_start, meta_end)
        result["meta_boxes"] = _box_summary(meta_children)
        idat_payload_offset = next(
            (child["payload_offset"] for child in meta_children if child["type"] == "idat"),
            None,
        )
        property_list: list[dict[str, Any]] = []
        property_associations: dict[str, list[dict[str, Any]]] = {}
        for child in meta_children:
            if child["type"] == "pitm":
                result["primary_item_id"] = _parse_pitm(data, child)
            elif child["type"] == "iinf":
                for item_id, item_info in _parse_iinf(data, child).items():
                    item = result["items"].setdefault(item_id, {"item_id": int(item_id)})
                    item.update(item_info)
            elif child["type"] == "iloc":
                for item_id, location in _parse_iloc(data, child, idat_payload_offset).items():
                    item = result["items"].setdefault(item_id, {"item_id": int(item_id)})
                    item.update(location)
            elif child["type"] == "iref":
                result["references"].extend(_parse_iref(data, child))
            elif child["type"] == "iprp":
                property_list, property_associations = _parse_iprp(data, child)
                result["properties"] = property_list

        property_by_index = {prop["index"]: prop for prop in property_list}
        for item_id, associations in property_associations.items():
            item = result["items"].setdefault(item_id, {"item_id": int(item_id)})
            expanded_associations = []
            for association in associations:
                prop = property_by_index.get(association["property_index"])
                if prop is None:
                    expanded_associations.append(association)
                    continue
                expanded = dict(association)
                expanded.update({"type": prop["type"], "parsed": prop["parsed"]})
                expanded_associations.append(expanded)
                if prop["type"] == "colr":
                    item["colr"] = prop["parsed"]
                elif prop["type"] == "pixi":
                    item["pixi"] = prop["parsed"]
                elif prop["type"] == "ispe":
                    item["dimensions"] = prop["parsed"]
                elif prop["type"] == "auxC":
                    item["aux_type"] = prop["parsed"].get("aux_type")
                elif prop["type"] == "irot":
                    item["irot"] = prop["parsed"]
                elif prop["type"] == "clli":
                    item["clli"] = prop["parsed"]
            item["property_associations"] = expanded_associations
        _annotate_references(result["items"], result["references"])
    return result


def _check_orientation_match(
    base_item: dict[str, Any] | None,
    gain_map_item: dict[str, Any] | None,
    tmap_item: dict[str, Any],
    errors: list[str],
    warnings: list[str],
) -> None:
    values = []
    for role, item in (("base", base_item), ("gain-map", gain_map_item), ("tmap", tmap_item)):
        if item is None:
            continue
        irot = item.get("irot")
        if not irot:
            warnings.append(f"{role} item has no irot orientation property.")
            continue
        values.append((role, irot.get("angle_ccw_degrees")))
    known = [value for _role, value in values if value is not None]
    if known and any(value != known[0] for value in known):
        errors.append(f"tmap route item orientations do not match: {values}.")


def _check_clli(
    base_item: dict[str, Any] | None,
    tmap_item: dict[str, Any],
    warnings: list[str],
) -> None:
    if base_item is not None and not base_item.get("clli"):
        warnings.append("base input item has no clli viewing-condition hint.")
    if not tmap_item.get("clli"):
        warnings.append("tmap item has no clli viewing-condition hint.")


def _payload_from_item_extents(data: bytes, item: dict[str, Any]) -> bytes:
    payload = bytearray()
    for extent in item.get("extents", []):
        offset = int(extent.get("absolute_offset", extent.get("offset", 0)))
        length = int(extent.get("length", 0))
        payload.extend(data[offset:offset + length])
    return bytes(payload)


def _annotate_references(items: dict[str, dict[str, Any]], references: list[dict[str, Any]]) -> None:
    for ref in references:
        from_id = str(ref["from_item_id"])
        from_item = items.setdefault(from_id, {"item_id": ref["from_item_id"]})
        from_item.setdefault("references_from", []).append(
            {"type": ref["type"], "to_item_ids": ref["to_item_ids"]}
        )
        for to_item_id in ref["to_item_ids"]:
            to_item = items.setdefault(str(to_item_id), {"item_id": to_item_id})
            to_item.setdefault("references_to", []).append(
                {"type": ref["type"], "from_item_id": ref["from_item_id"]}
            )


def _parse_ftyp(data: bytes, box: dict[str, Any]) -> dict[str, Any]:
    pos = box["payload_offset"]
    end = pos + box["payload_size"]
    if end - pos < 8:
        return {}
    return {
        "major_brand": _fourcc(data[pos:pos + 4]),
        "minor_version": _u32(data, pos + 4),
        "compatible_brands": [
            _fourcc(data[index:index + 4])
            for index in range(pos + 8, end, 4)
            if index + 4 <= end
        ],
    }


def _parse_pitm(data: bytes, box: dict[str, Any]) -> int | None:
    version, _flags, pos = _read_fullbox(data, box["payload_offset"])
    end = box["payload_offset"] + box["payload_size"]
    if version == 0 and pos + 2 <= end:
        return _u16(data, pos)
    if pos + 4 <= end:
        return _u32(data, pos)
    return None


def _parse_iinf(data: bytes, box: dict[str, Any]) -> dict[str, dict[str, Any]]:
    version, _flags, pos = _read_fullbox(data, box["payload_offset"])
    end = box["payload_offset"] + box["payload_size"]
    if version in (0, 1):
        if pos + 2 > end:
            return {}
        entry_count = _u16(data, pos)
        pos += 2
    else:
        if pos + 4 > end:
            return {}
        entry_count = _u32(data, pos)
        pos += 4
    items: dict[str, dict[str, Any]] = {}
    for child in _iter_boxes(data, pos, end)[:entry_count]:
        if child["type"] != "infe":
            continue
        item = _parse_infe(data, child)
        item_id = item.get("item_id")
        if item_id is not None:
            items[str(item_id)] = item
    return items


def _parse_infe(data: bytes, box: dict[str, Any]) -> dict[str, Any]:
    version, flags, pos = _read_fullbox(data, box["payload_offset"])
    end = box["payload_offset"] + box["payload_size"]
    result: dict[str, Any] = {"infe_version": version, "flags": flags, "hidden": bool(flags & 1)}
    if version in (0, 1):
        if pos + 4 > end:
            return result
        item_id = _u16(data, pos)
        result["item_id"] = item_id
        result["item_protection_index"] = _u16(data, pos + 2)
        name, cursor = _read_cstr(data, pos + 4, end)
        content_type, cursor = _read_cstr(data, cursor, end)
        _content_encoding, _cursor = _read_cstr(data, cursor, end)
        result["name"] = name
        if len(content_type) == 4:
            result["item_type"] = content_type
        else:
            result["content_type"] = content_type
        return result
    if version in (2, 3):
        item_id_size = 4 if version == 3 else 2
        if pos + item_id_size + 6 > end:
            return result
        item_id, pos = _read_int(data, pos, item_id_size)
        result["item_id"] = item_id
        result["item_protection_index"] = _u16(data, pos)
        pos += 2
        result["item_type"] = _fourcc(data[pos:pos + 4])
        pos += 4
        name, _pos = _read_cstr(data, pos, end)
        result["name"] = name
    return result


def _parse_iloc(
    data: bytes,
    box: dict[str, Any],
    idat_payload_offset: int | None,
) -> dict[str, dict[str, Any]]:
    version, flags, pos = _read_fullbox(data, box["payload_offset"])
    end = box["payload_offset"] + box["payload_size"]
    if pos + 2 > end:
        return {}
    sizes_1 = _u8(data, pos)
    sizes_2 = _u8(data, pos + 1)
    pos += 2
    offset_size = sizes_1 >> 4
    length_size = sizes_1 & 0x0F
    base_offset_size = sizes_2 >> 4
    index_size = sizes_2 & 0x0F if version in (1, 2) else 0
    if version < 2:
        item_count = _u16(data, pos)
        pos += 2
    else:
        item_count = _u32(data, pos)
        pos += 4
    locations: dict[str, dict[str, Any]] = {}
    for _ in range(item_count):
        item_id_size = 2 if version < 2 else 4
        item_id, pos = _read_int(data, pos, item_id_size)
        construction_method = 0
        if version in (1, 2):
            construction_method = _u16(data, pos) & 0x000F
            pos += 2
        data_reference_index = _u16(data, pos)
        pos += 2
        base_offset, pos = _read_int(data, pos, base_offset_size)
        extent_count = _u16(data, pos)
        pos += 2
        extents = []
        for _extent in range(extent_count):
            if index_size:
                _extent_index, pos = _read_int(data, pos, index_size)
            extent_offset, pos = _read_int(data, pos, offset_size)
            extent_length, pos = _read_int(data, pos, length_size)
            if construction_method == 1 and idat_payload_offset is not None:
                absolute_offset = idat_payload_offset + base_offset + extent_offset
            else:
                absolute_offset = base_offset + extent_offset
            extents.append(
                {
                    "offset": extent_offset,
                    "length": extent_length,
                    "absolute_offset": absolute_offset,
                    "storage": "idat" if construction_method == 1 else "mdat",
                }
            )
        locations[str(item_id)] = {
            "iloc_version": version,
            "iloc_flags": flags,
            "construction_method": construction_method,
            "data_reference_index": data_reference_index,
            "base_offset": base_offset,
            "extents": extents,
        }
    return locations


def _parse_iref(data: bytes, box: dict[str, Any]) -> list[dict[str, Any]]:
    version, flags, pos = _read_fullbox(data, box["payload_offset"])
    end = box["payload_offset"] + box["payload_size"]
    references: list[dict[str, Any]] = []
    item_id_size = 2 if version == 0 else 4
    for child in _iter_boxes(data, pos, end):
        child_pos = child["payload_offset"]
        child_end = child_pos + child["payload_size"]
        if child_pos + item_id_size + 2 > child_end:
            continue
        from_item_id, child_pos = _read_int(data, child_pos, item_id_size)
        ref_count = _u16(data, child_pos)
        child_pos += 2
        to_item_ids = []
        for _ in range(ref_count):
            to_item_id, child_pos = _read_int(data, child_pos, item_id_size)
            to_item_ids.append(to_item_id)
        references.append(
            {
                "version": version,
                "flags": flags,
                "type": child["type"],
                "from_item_id": from_item_id,
                "to_item_ids": to_item_ids,
            }
        )
    return references


def _parse_iprp(data: bytes, box: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    pos = box["payload_offset"]
    end = pos + box["payload_size"]
    properties: list[dict[str, Any]] = []
    associations: dict[str, list[dict[str, Any]]] = {}
    for child in _iter_boxes(data, pos, end):
        if child["type"] == "ipco":
            for index, prop_box in enumerate(_iter_boxes(data, child["payload_offset"], child["payload_offset"] + child["payload_size"]), start=1):
                properties.append(_parse_property(data, prop_box, index))
        elif child["type"] == "ipma":
            associations.update(_parse_ipma(data, child))
    return properties, associations


def _parse_ipma(data: bytes, box: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    version, flags, pos = _read_fullbox(data, box["payload_offset"])
    end = box["payload_offset"] + box["payload_size"]
    if pos + 4 > end:
        return {}
    entry_count = _u32(data, pos)
    pos += 4
    associations: dict[str, list[dict[str, Any]]] = {}
    for _ in range(entry_count):
        item_id_size = 2 if version == 0 else 4
        item_id, pos = _read_int(data, pos, item_id_size)
        association_count = _u8(data, pos)
        pos += 1
        item_associations = []
        for _assoc in range(association_count):
            if flags & 1:
                raw = _u16(data, pos)
                pos += 2
                essential = bool(raw & 0x8000)
                property_index = raw & 0x7FFF
            else:
                raw = _u8(data, pos)
                pos += 1
                essential = bool(raw & 0x80)
                property_index = raw & 0x7F
            item_associations.append({"property_index": property_index, "essential": essential})
        associations[str(item_id)] = item_associations
    return associations


def _parse_property(data: bytes, box: dict[str, Any], index: int) -> dict[str, Any]:
    parsers = {
        "colr": _parse_colr,
        "pixi": _parse_pixi,
        "ispe": _parse_ispe,
        "auxC": _parse_auxc,
        "irot": _parse_irot,
        "clli": _parse_clli,
    }
    parsed = parsers.get(box["type"], lambda _data, _box: {})(data, box)
    return {"index": index, "type": box["type"], "parsed": parsed}


def _parse_colr(data: bytes, box: dict[str, Any]) -> dict[str, Any]:
    pos = box["payload_offset"]
    end = pos + box["payload_size"]
    if pos + 4 > end:
        return {}
    color_type = _fourcc(data[pos:pos + 4])
    result: dict[str, Any] = {"color_type": color_type}
    if color_type == "nclx" and pos + 11 <= end:
        result.update(
            {
                "colour_primaries": _u16(data, pos + 4),
                "transfer_characteristics": _u16(data, pos + 6),
                "matrix_coefficients": _u16(data, pos + 8),
                "full_range_flag": bool(_u8(data, pos + 10) & 0x80),
            }
        )
    elif color_type in ("prof", "rICC"):
        result["icc_profile_bytes"] = end - (pos + 4)
    return result


def _parse_pixi(data: bytes, box: dict[str, Any]) -> dict[str, Any]:
    _version, _flags, pos = _read_fullbox(data, box["payload_offset"])
    end = box["payload_offset"] + box["payload_size"]
    if pos >= end:
        return {}
    channels = _u8(data, pos)
    pos += 1
    return {"channels": channels, "bits": list(data[pos:min(end, pos + channels)])}


def _parse_ispe(data: bytes, box: dict[str, Any]) -> dict[str, Any]:
    _version, _flags, pos = _read_fullbox(data, box["payload_offset"])
    end = box["payload_offset"] + box["payload_size"]
    if pos + 8 > end:
        return {}
    return {"width": _u32(data, pos), "height": _u32(data, pos + 4)}


def _parse_auxc(data: bytes, box: dict[str, Any]) -> dict[str, Any]:
    version, flags, pos = _read_fullbox(data, box["payload_offset"])
    end = box["payload_offset"] + box["payload_size"]
    aux_type, pos = _read_cstr(data, pos, end)
    return {"version": version, "flags": flags, "aux_type": aux_type}


def _parse_irot(data: bytes, box: dict[str, Any]) -> dict[str, Any]:
    pos = box["payload_offset"]
    end = pos + box["payload_size"]
    if pos >= end:
        return {}
    return {"angle_ccw_degrees": (_u8(data, pos) & 0x03) * 90}


def _parse_clli(data: bytes, box: dict[str, Any]) -> dict[str, Any]:
    pos = box["payload_offset"]
    end = pos + box["payload_size"]
    if pos + 4 > end:
        return {}
    return {"max_content_light_level": _u16(data, pos), "max_pic_average_light_level": _u16(data, pos + 2)}


def _iter_boxes(data: bytes, start: int = 0, end: int | None = None) -> list[dict[str, Any]]:
    if end is None:
        end = len(data)
    boxes: list[dict[str, Any]] = []
    offset = start
    while offset + 8 <= end:
        size = _u32(data, offset)
        box_type = _fourcc(data[offset + 4:offset + 8])
        header_size = 8
        if size == 1:
            if offset + 16 > end:
                raise HEIFISO21496Error(f"Box {box_type} has truncated largesize.")
            size = _u64(data, offset + 8)
            header_size = 16
        elif size == 0:
            size = end - offset
        if size < header_size or offset + size > end:
            raise HEIFISO21496Error(f"Box {box_type} at {offset} has invalid size {size}.")
        boxes.append(
            {
                "type": box_type,
                "offset": offset,
                "size": size,
                "header_size": header_size,
                "payload_offset": offset + header_size,
                "payload_size": size - header_size,
            }
        )
        offset += size
    return boxes


def _box_summary(boxes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"type": box["type"], "offset": box["offset"], "size": box["size"]} for box in boxes]


def _read_fullbox(data: bytes, payload_offset: int) -> tuple[int, int, int]:
    return _u8(data, payload_offset), _u24(data, payload_offset + 1), payload_offset + 4


def _read_cstr(data: bytes, offset: int, end: int) -> tuple[str, int]:
    stop = data.find(b"\0", offset, end)
    if stop < 0:
        return data[offset:end].decode("utf-8", errors="replace"), end
    return data[offset:stop].decode("utf-8", errors="replace"), stop + 1


def _read_int(data: bytes, offset: int, size: int) -> tuple[int, int]:
    if size == 0:
        return 0, offset
    return int.from_bytes(data[offset:offset + size], "big"), offset + size


def _read_signed_rational_value(data: bytes | bytearray, offset: int) -> float:
    numerator, denominator = struct.unpack_from(">iI", data, offset)
    if denominator == 0:
        raise ValueError("rational denominator must not be zero")
    return numerator / denominator


def _fourcc(value: bytes) -> str:
    return value.decode("latin-1", errors="replace")


def _u8(data: bytes, offset: int) -> int:
    return data[offset]


def _u16(data: bytes, offset: int) -> int:
    return struct.unpack_from(">H", data, offset)[0]


def _u24(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset:offset + 3], "big")


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from(">I", data, offset)[0]


def _u64(data: bytes, offset: int) -> int:
    return struct.unpack_from(">Q", data, offset)[0]
