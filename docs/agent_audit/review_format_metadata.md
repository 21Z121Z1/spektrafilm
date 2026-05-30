# Format, Metadata & I/O Safety Review

> Generated 2026-05-28 — Phase 1 Quality Audit  
> Updated 2026-05-28 — Deep review pass (review-only, no code changes)

---

## FMT-001: JPEG MPF entry size mismatch between writer and reader — gain map round-trip broken

**Severity**: P0 — Loss of core functionality  
**File:Function**: `src/spektrafilm/utils/gain_map_io.py:236-256` (writer), `:419-454` (reader)

**Description**: The MPF writer packs each MP Entry as **12 bytes** (flags 4B + size 4B + offset 4B), but CIPA DC-007 specifies **16 bytes** per entry (flags + size + offset + dependency/disparity). The reader at `:431` computes the second entry's position as `8 (header) + 16 (first entry) = 24`, but the writer only emitted 12 bytes for the first entry, placing the second entry at byte 20.

The parser reads bytes 24-35 for the second entry, which actually contains the trailing 4 bytes of the first entry plus 8 bytes of the second entry, producing garbage size and offset values.

**Reproduction**: Call `save_gain_map_jpeg(path, base, gain_map, metadata)` then `load_gain_map(path)`. The `gain_map` field will be `None`.

**Expected**: `load_gain_map` returns a dict with a valid `gain_map` PIL.Image.  
**Actual**: `load_gain_map` returns `gain_map=None` silently (the error is swallowed by bare `except Exception` at line 377).

**Minimal fix**: Either:
- (A) Add the missing 4 zero bytes per entry in `_build_mpf_payload` to match the 16-byte-per-entry spec.
- (B) Update the reader to match the 12-byte-per-entry layout.

Option (A) is preferred for spec compliance.

**Validation**: Round-trip test: `save_gain_map_jpeg` → `load_gain_map` → assert `gain_map is not None` and pixel data round-trips within tolerance.

---

## FMT-002: JPEG MPF Data Offset base is 8 bytes off from CIPA DC-007 spec

**Severity**: P1 — Incompatibility with conforming readers  
**File:Function**: `src/spektrafilm/utils/gain_map_io.py:216-217` (writer), `:440-444` (reader)

**Description**: The MPF Data Offset for image 2 (gain map) is stored as the distance from the MPF APP2 marker position (`ff e2`). Per CIPA DC-007 §6.2.3, the offset must be from the *MP Entry value* position, which is 8 bytes deeper (marker 2B + length 2B + "MPF\0" 4B = 8B). The writer and reader are self-consistent (both use the marker position), so the internal round-trip works, but an external conforming MPF reader would extract 8 bytes of garbage before the actual gain map.

**Minimal fix**: Update both writer and reader to use the MP Entry value position as the offset base.

**Validation**: Validate the output file with an external CIPA DC-007 compliant MPF parser.

---

## FMT-003: JPEG MPF gain map size is 2 bytes short (missing EOI)

**Severity**: P1 — Corrupt gain map for external readers  
**File:Function**: `src/spektrafilm/utils/gain_map_io.py:217,220-222`

**Description**: The gain map size stored in MPF is `len(gm_data)` where `gm_data` is the JPEG without SOI and without EOI. But the actual written gain map is `gm_data + _EOI` (2 bytes larger). The MPF `Individual Image Size` field is 2 bytes short. A conforming MPF reader would truncate the gain map JPEG, missing the final EOI marker.

**Minimal fix**: Change `len(gm_data)` to `len(gm_data) + 2` to account for the appended EOI.

**Validation**: Validate with an external MPF parser that reads the gain map by size.

---

## FMT-004: HEIF ISO 21496-1 tmap brand patching corrupts ISOBMFF box offsets

**Severity**: P1 — Corrupt output file  
**File:Function**: `src/spektrafilm/utils/gain_map_io.py:264-299`

**Description**: The inline fallback inserts 4 bytes (`b"tmap"`) into the ftyp box at byte offset `ftyp_size`, then updates the ftyp box size header. However, every ISOBMFF box after ftyp (meta, mdat, moov, etc.) has its absolute file offset shifted by +4 bytes. Box-relative pointers inside moov/trak/mdia (e.g., stco/chunk offset tables) now point 4 bytes too early, corrupting the file structure.

Additionally, the function tries to import `spektrafilm.utils._isobmff_patch`, which does not exist (confirmed by glob).

**Minimal fix**: Remove the inline fallback entirely (log a warning and return False), or implement proper ISOBMFF box traversal that patches stco/co64 tables after insertion.

**Validation**: Validate output HEIF with an ISOBMFF parser (e.g., mp4parse, isomp4).

---

## FMT-005: `_gainmap_metadata_to_iso_dict` discards multichannel metadata

**Severity**: P1 — Metadata loss  
**File:Function**: `src/spektrafilm/utils/gain_map_io.py:302-314`

**Description**: The function extracts metadata from `metadata.channels[0]` only and replicates it across all 3 channels. If a `GainMapMetadata` has per-channel variation (different gain_map_min/max/gamma per R/G/B), the per-channel differences are silently discarded.

**Minimal fix**: Iterate all channels: `"gainMapMin": [ch.gain_map_min for ch in metadata.channels]`

**Validation**: Unit test with per-channel metadata variation, verify ISO dict preserves all channels.

---

## FMT-006: `load_gain_map` HEIF path always returns metadata=None

**Severity**: P1 — Metadata loss  
**File:Function**: `src/spektrafilm/utils/gain_map_io.py:485-506`

**Description**: The `_load_gain_map_heif` function always returns `"metadata": None` (line 504). Even for properly tagged ISO 21496-1 HEIF files, no attempt is made to parse the ISOBMFF `tmap` item or read embedded XMP metadata.

**Minimal fix**: At minimum, attempt to read XMP metadata from the HEIF file using pillow-heif's metadata API, or log a clear warning.

**Validation**: Round-trip `save_gain_map_heif` → `load_gain_map` with metadata comparison.

---

## FMT-007: HEIF gain map fallback silently changes output format

**Severity**: P2 — User surprise  
**File:Function**: `src/spektrafilm/utils/gain_map_io.py:115-121`

**Description**: When `pillow-heif` is not installed, `save_gain_map_heif` falls back to `save_gain_map_jpeg` with a `.jpg` extension, and only logs a warning. The caller requested HEIF output and receives JPEG instead.

**Minimal fix**: Raise `ImportError("pillow-heif is required for HEIF gain map output.")` instead of silently changing format.

**Validation**: Test with pillow-heif unavailable; assert error is raised.

---

## FMT-008: 8-bit PNG/JPEG PIL path missing `resolve_icc_profile_bytes` fallback

**Severity**: P2 — Missing ICC profile  
**File:Function**: `src/spektrafilm/utils/io.py:688-704`

**Description**: The PIL-based save path for 8-bit PNG and JPEG only calls `_load_icc_profile(color_space, cctf_encoding)`, which checks `_ICC_FILENAMES`. If that lookup returns `None` (e.g., for a color space not in the table), the ICC profile is silently omitted. The OIIO path for TIFF/EXR has separate ICC embedding. The `_write_png_rgb16` 16-bit PNG path correctly receives and embeds the ICC profile.

**Minimal fix**: Replace `_load_icc_profile(color_space, cctf_encoding)` with `resolve_icc_profile_bytes(color_space, cctf_encoding)` in the PIL save block.

**Validation**: Save an 8-bit JPEG with a color space not in `_ICC_FILENAMES`; verify ICC is embedded via fallback.

---

## FMT-009: Missing `_ICC_FILENAMES` entries for linear DCI-P3 and Display P3

**Severity**: P2 — Incorrect ICC profile  
**File:Function**: `src/spektrafilm/utils/io.py:171-191`

**Description**: `_ICC_FILENAMES` is missing entries for `("DCI-P3", False)` (linear) and `("Display P3", False)` (linear). When `save_image_oiio` is called with `color_space="DCI-P3", cctf_encoding=False`, `_load_icc_profile` returns `None`. The fallback `_load_icc_profile_from_extra` returns `DCI-P3.icc`, which is a *different* file from the saucecontrol `DCI-P3-v4.icc` used when `cctf_encoding=True`. This means DCI-P3 linear and CCTF outputs get different ICC profiles from different vendors.

**Minimal fix**: Add `("DCI-P3", False)` and `("Display P3", False)` entries to `_ICC_FILENAMES`.

**Validation**: Verify ICC profile bytes match expected for both linear and CCTF variants.

---

## FMT-010: `GainMapMetadata.to_xmp()` only serializes first channel

**Severity**: P2 — Metadata loss  
**File:Function**: `src/spektrafilm/utils/gain_map_metadata.py:193-221`

**Description**: The `to_xmp()` method at line 201 uses `ch = self.channels[0]` and only emits a single set of values. For multichannel gain maps (`is_multichannel=True` with 3 channels), the per-channel variation is lost in the XMP representation.

**Minimal fix**: For multichannel metadata, emit per-channel values using `hdrgm:GainMapMinR`/`G`/`B` variants per Adobe HDR GM spec.

**Validation**: Parse generated XMP with an XMP reader and verify per-channel values.

---

## FMT-011: EXR half-float write silently truncates HDR values > 65504

**Severity**: P2 — Silent data loss  
**File:Function**: `src/spektrafilm/utils/io.py:711-715`

**Description**: When writing 16-bit EXR (`bit_depth=16`), the code casts `image_data` to `np.float16` without range checking. float16 max is ~65504. Scene-linear HDR data can easily exceed this, producing `inf` values in the output.

**Minimal fix**: Add a warning when values exceed float16 range, or clamp with a logged warning.

**Validation**: Test with extreme HDR values, verify warning is emitted.

---

## IO-001: `load_image_oiio` returns all channels including non-RGB extras

**Severity**: P1 — Potential data corruption  
**File:Function**: `src/spektrafilm/utils/io.py:480-524`

**Description**: The function reads all channels from the image spec (`spec.nchannels`) and reshapes to `(H, W, nchannels)`. For files with extra channels (alpha, depth, AOVs), this returns a 4+ channel array. The pipeline and `save_image_oiio` expect 3-channel `(H, W, 3)` data.

**Minimal fix**: Add a `channels` parameter to `load_image_oiio` (default 3) to control channel extraction, or document the behavior clearly.

**Validation**: Test with 4-channel input, verify output shape consistency.

---

## IO-002: `write_image_metadata` exiv2 handle not closed on error

**Severity**: P2 — Resource leak  
**File:Function**: `src/spektrafilm/utils/io.py:128-155`

**Description**: The `exiv2.ImageFactory.open(filename)` object at line 128 is not used as a context manager. If any exception occurs between `open` (line 128) and `writeMetadata` (line 155), the file handle leaks. The `oiio.ImageInput` at line 119 is properly closed in a try/finally, but the exiv2 image is not.

**Minimal fix**: Wrap in try/finally with explicit cleanup (assign `None` to the variable).

**Validation**: Trigger an exception during metadata write, verify no file handle leak.

---

## IO-003: `_read_exif_metadata` exiv2 handle not closed on error

**Severity**: P2 — Resource leak  
**File:Function**: `src/spektrafilm/utils/raw_file_processor.py:284-296`

**Description**: Same pattern as IO-002. The `exiv2.ImageFactory.open` result in `_read_exif_metadata` is not wrapped in try/finally. If `readMetadata()` succeeds but subsequent access raises, the handle leaks.

**Minimal fix**: Wrap in try/finally with explicit cleanup.

**Validation**: Same as IO-002.

---

## IO-004: `write_image_metadata` ICC verification TOCTOU window

**Severity**: P2 — Potential false failure  
**File:Function**: `src/spektrafilm/utils/io.py:152-160`

**Description**: After writing metadata, the function re-opens the file with OIIO to verify the ICC profile was preserved (line 158). Between the exiv2 `writeMetadata` call and the OIIO re-read, another process could modify the file. Additionally, exiv2 may rewrite the ICC profile in a different encoding (e.g., different chunking) while preserving semantic equivalence, causing a byte-level mismatch that raises a false `RuntimeError`.

**Minimal fix**: Compare ICC profile descriptions or checksums rather than raw bytes, or skip verification for production builds.

**Validation**: Test with an ICC profile that exiv2 may rewrite differently.

---

## IO-005: `save_neutral_print_filters` writes to package resources

**Severity**: P2 — Deployment issue  
**File:Function**: `src/spektrafilm/utils/io.py:880-888`

**Description**: The function writes to `spektrafilm.data.filters/neutral_print_filters.json` via `importlib.resources`. In installed packages (wheel, zip), `importlib.resources.files()` may not be writable. This will raise `OSError` or `PermissionError` in production deployments.

**Minimal fix**: Write to a user-configurable output directory (e.g., `~/.config/spektrafilm/`) instead of package resources, or document that this function is development-only.

**Validation**: Test in a read-only installed environment.

---

## IO-006: `read_image_color_encoding` closes file handle before using spec

**Severity**: P3 — Potential race  
**File:Function**: `src/spektrafilm/utils/io.py:315-323`

**Description**: The function opens the file with OIIO, reads the spec, then closes the file (line 323). It then uses `spec` for metadata extraction after the file is closed. While OIIO's `ImageSpec` typically copies metadata into Python objects, some attribute values may reference internal buffers that become invalid after `close()`.

**Minimal fix**: Move `in_img.close()` to after all spec attribute accesses are complete.

**Validation**: Test with large ICC profiles on a slow filesystem.

---

## IO-007: `_to_pil_image` converts all float data to uint8 — precision loss for gain maps

**Severity**: P2 — Precision loss  
**File:Function**: `src/spektrafilm/utils/gain_map_io.py:514-540`

**Description**: Both SDR base and gain map images are converted to uint8 before JPEG/HEIF encoding. For the gain map, this means only 256 discrete levels of gain, which may introduce visible banding in smooth gradients. HEIF supports 10-bit encoding.

**Minimal fix**: For HEIF output, consider using 10-bit encoding. For JPEG, document the 8-bit limitation.

**Validation**: Compare gain map quality at 8-bit vs 10-bit encoding.

---

## IO-008: `_load_gain_map_jpeg` silently swallows parsing exceptions

**Severity**: P2 — Silent failure  
**File:Function**: `src/spektrafilm/utils/gain_map_io.py:376-385`

**Description**: Both gain map image opening (line 377) and metadata deserialization (line 383) catch bare `Exception` and silently set the result to `None`. The caller cannot distinguish between "no gain map present" and "gain map corrupted."

**Minimal fix**: Log a warning when exceptions are caught.

**Validation**: Feed a truncated gain map JPEG to `load_gain_map`, verify warning is logged.

---

## IO-009: `image_data.shape` unpack assumes 3D input in `save_image_oiio`

**Severity**: P3 — Defensive coding  
**File:Function**: `src/spektrafilm/utils/io.py:680`

**Description**: The unpack `height, width, nchannels = image_data.shape` will raise `ValueError` for 2D (grayscale) or 4D (batched) arrays. No explicit shape validation is performed.

**Minimal fix**: Add `if image_data.ndim != 3: raise ValueError(...)` before unpacking.

**Validation**: Pass a 2D array to `save_image_oiio`, verify a clear error message.

---

## IO-010: `_validate_hdr_photo_output_path` does not prevent symlink traversal

**Severity**: P3 — Security (low)  
**File:Function**: `src/spektrafilm/utils/hdr_photo.py:1023-1033`

**Description**: The path validation checks for control characters and parent directory existence, but does not resolve symlinks. A symlink could point to an unexpected location.

**Minimal fix**: Use `Path.resolve()` before validation.

**Validation**: Create a symlink to `/dev/null`, pass as output_path, verify behavior.

---

## IO-011: Extension parsing via `str.split('.')` is fragile

**Severity**: P3 — Edge case  
**File:Function**: `src/spektrafilm/utils/io.py:614`

**Description**: `filename.split('.')[-1].lower()` fails for extensionless paths or paths ending with a dot. `Path(filename).suffix.lstrip('.').lower()` would be more robust, matching the pattern used elsewhere in the codebase.

**Minimal fix**: Replace with `Path(filename).suffix.lstrip('.').lower()`.

**Validation**: Test with extensionless path and trailing-dot path.

---

## IO-012: `save_neutral_print_filters` missing `allow_nan=False`

**Severity**: P3 — Data integrity  
**File:Function**: `src/spektrafilm/utils/io.py:880-888`

**Description**: `json.dump` at line 885 does not pass `allow_nan=False`. If the filter data contains `NaN` or `Inf` values, they will be serialized as `NaN`/`Infinity` (non-standard JSON), which `json.load` will fail to parse. `save_profile` at `profiles/io.py:302` correctly uses `allow_nan=False`.

**Minimal fix**: Add `allow_nan=False` to the `json.dump` call.

**Validation**: Pass filter data with NaN, verify `json.JSONDecodeError` on subsequent load.

---

## IO-013: MPF gain map MP Entry flags use wrong value

**Severity**: P3 — Interoperability  
**File:Function**: `src/spektrafilm/utils/gain_map_io.py:252`

**Description**: The MPF MP Entry flags for the gain map use `0x02000000`, which indicates "Dependent child image" per CIPA DC-007. For an ISO 21496-1 gain map, the correct flag is `0x00000000` (Undefined/Individual image). Using the wrong flag may cause some MPF readers to misclassify the gain map.

**Minimal fix**: Change to `struct.pack(">I", 0)` to match the base image entry flags.

**Validation**: Validate with an external MPF reader.

---

## Summary

| ID | Severity | Category | Brief |
|----|----------|----------|-------|
| FMT-001 | P0 | Gain Map JPEG | MPF entry size mismatch breaks round-trip |
| FMT-002 | P1 | Gain Map JPEG | MPF data offset base off by 8 bytes |
| FMT-003 | P1 | Gain Map JPEG | MPF gain map size off by 2 bytes (EOI) |
| FMT-004 | P1 | Gain Map HEIF | tmap brand patch corrupts ISOBMFF offsets |
| FMT-005 | P1 | Gain Map Metadata | Multichannel metadata discarded |
| FMT-006 | P1 | Gain Map HEIF | HEIF load always returns metadata=None |
| FMT-007 | P2 | Gain Map HEIF | Silent JPEG fallback |
| FMT-008 | P2 | ICC | PIL path missing resolve_icc_profile_bytes |
| FMT-009 | P2 | ICC | Missing linear DCI-P3/Display P3 entries |
| FMT-010 | P2 | XMP | Multichannel XMP incomplete |
| FMT-011 | P2 | EXR | Half-float truncation of HDR values |
| IO-001 | P1 | Image I/O | Extra channels returned without filtering |
| IO-002 | P2 | Metadata | exiv2 file handle leak in write_image_metadata |
| IO-003 | P2 | Metadata | exiv2 file handle leak in _read_exif_metadata |
| IO-004 | P2 | Metadata | ICC verification TOCTOU window |
| IO-005 | P2 | I/O | Writes to package resources |
| IO-006 | P3 | Image I/O | File closed before spec use |
| IO-007 | P2 | Gain Map | uint8 precision loss |
| IO-008 | P2 | Gain Map | Silent exception swallowing |
| IO-009 | P3 | Image I/O | Missing shape validation |
| IO-010 | P3 | Security | Symlink traversal |
| IO-011 | P3 | Image I/O | Fragile extension parsing |
| IO-012 | P3 | Data | allow_nan missing in save_neutral_print_filters |
| IO-013 | P3 | Gain Map JPEG | Wrong MPF entry flags |

**Critical path**: FMT-001 (JPEG MPF round-trip) is the highest priority — it breaks the core gain map I/O workflow. FMT-002 through FMT-004 affect interoperability with conforming external readers. IO-001 (extra channels) affects any EXR/RGBA pipeline input.
