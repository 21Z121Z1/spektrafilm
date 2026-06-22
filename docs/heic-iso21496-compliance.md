# HEIC ISO 21496-1 Compliance

Date: 2026-06-08

## References Checked

The local standards references for this pass are under:

`docs/reference/standards/`

The standards README says to search by clause or keyword rather than loading the
entire standards into context. The implementation was checked against:

- `ISO_21496-1_2025_2053497278426656768.md`
- `ISO_21496-1_2025_2053497278426656768_zh.md`
- `ISO_IEC_23008-12_2025_2053792792368005120.md`
- `ISO_IEC_23008-12_2025_Amd_1_2025_2053793830344998912.md`

Relevant clauses:

- ISO 21496-1 5.2.5.3: per-channel `max(G)` must be greater than or equal to
  `min(G)`.
- ISO 21496-1 5.2.5.6: per-channel gamma must be greater than zero.
- ISO 21496-1 5.2.7: alternate HDR headroom must differ from baseline HDR
  headroom.
- ISO 21496-1 C.2: `GainMapMetadata` is big-endian binary metadata, and parsers
  ignore unrecognized trailing optional data after recognized fields.
- ISO/IEC 23008-12 Amd.1 6.6.2.4: `tmap` uses a `dimg` reference with exactly
  two inputs, base first and gain-map second; base has `colr`; gain-map has
  `nclx` `colr` with colour primaries and transfer characteristics set to `2`;
  tmap has alternate `colr`; gain-map input should be hidden.
- ISO/IEC 23008-12 Amd.1 10.2.6: a file with a tone-map derived item includes
  the `tmap` compatible brand, and a file advertising `tmap` contains at least
  one tone-map derived image item.
- ISO/IEC 23008-12 6.4.2: a primary item must not be hidden.

## Encoder Strategy

Spektrafilm keeps the Swift/CoreImage writer as the default RouteMaster HEIC
writer because it is the Mac-compatible path. The encoder receives already
rendered SDR/HDR pairs and does not call the simulator, profile sampling, film
or paper profiles, or HDR recovery.

After CoreImage writes the file, Spektrafilm validates the actual HEIF structure.
Marker strings are not completion evidence.

## Validator

`src/spektrafilm/utils/heif_iso21496.py` parses the subset needed for ISO gain
map validation:

- `ftyp`
- `meta`
- `pitm`
- `iinf` / `infe`
- `iref`
- `iprp` / `ipco` / `ipma`
- `iloc`
- `idat`

Hard failures:

- `tmap` compatible brand and item presence disagree.
- The primary item is hidden.
- The `tmap` item lacks exactly one `dimg` reference with two inputs.
- The referenced base or gain-map input item is missing.
- The base input lacks `colr`.
- The gain-map input is not hidden.
- The gain-map input lacks `nclx` `colr` with colour primaries and transfer
  characteristics set to `2`.
- The `tmap` item lacks alternate-image `colr`.
- The `ToneMapImage` payload is missing, has a nonzero version, or does not parse
  as ISO 21496-1 C.2 `GainMapMetadata`.
- Metadata has non-finite values, invalid version ordering, equal headrooms,
  `minimum_version` other than `0`, negative headrooms,
  `gain_map_max < gain_map_min`, or non-positive gamma.

Warnings:

- Missing `clli` viewing-condition hints.
- Missing orientation hints, unless present orientation values disagree.
- Gain-map bit depth below the ISO recommendation.

## CoreImage Metadata Repair

Live CoreImage output on this machine produced a valid Mac-openable `tmap` item
graph but wrote the first two C.2 per-channel range fields in the opposite order
from the local ISO 21496-1 C.2 reference. The observed pattern was every channel
parsing as `min > max`, for example a positive first value and zero second value
for ordinary HDR-up pairs.

`repair_coreimage_tmap_min_max_order()` performs an in-place, same-size repair
only when all channels exhibit that exact invalid pattern. It swaps the two
eight-byte range fields for each channel and then the normal validator must pass.
Files with other malformed metadata are not repaired and still fail closed.

This keeps the Mac-compatible CoreImage writer while ensuring Spektrafilm does
not report success for a payload that violates ISO 21496-1 C.2.

## Fail-Closed Rules

`save_hdr_photo_heic_from_pair()`:

- writes through CoreImage;
- applies the narrow CoreImage range-order repair when needed;
- validates the resulting HEIF as ISO `tmap`;
- deletes partial output and raises `HDRPhotoExportError` on hard errors.

`save_hdr_photo_heic()` uses the same post-encode validation path but remains a
legacy compatibility API because it prepares HDR renditions internally.

`save_gain_map_heif()`:

- requires `pillow-heif`;
- requires the ISOBMFF patcher to produce `tmap`;
- validates the patched file;
- deletes partial output and raises if patching or validation fails.

## Mac Openability

The automated Darwin smoke test writes a small SDR/HDR pair and verifies:

- `validate_heif_iso21496()` accepts the real output;
- `sips` reports a readable HEIC with the expected dimensions;
- Swift ImageIO can create a `CGImage` from the result.

Apple Photos visual HDR activation and device gallery behavior remain manual
acceptance boundaries. They are not replaced by ISO structure validation or
local ImageIO openability.
