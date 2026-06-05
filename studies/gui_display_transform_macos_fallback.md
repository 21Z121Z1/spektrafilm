# Spektrafilm GUI Display Transform macOS Fallback

## Problem

Spektrafilm's GUI Display Transform used Pillow `PIL.ImageCms.get_display_profile()` as the only display ICC profile source. On macOS, that call can return `None`; on this checkout it currently does. When it returns `None`, `GuiController.sync_display_transform_availability()` treats Display Transform as unavailable, unchecks the toggle during startup, and reports:

```text
Display transform unavailable: no display profile detected, disabled
```

That is a false negative on macOS systems where CoreGraphics can still provide the main display color space and ICC payload.

## Implementation

The fallback lives in `src/spektrafilm_gui/controller_runtime.py` and keeps the existing ImageCms transform path unchanged:

1. `display_profile_details()` and `display_profile_available()` now share `_resolve_display_profile()`.
2. `_resolve_display_profile()` tries Pillow `get_display_profile()` first.
3. If Pillow returns `None` or raises a safe ImageCms-related exception, `_display_profile_from_fallback()` may run.
4. `_display_profile_from_fallback()` is enabled only when:
   - `sys.platform == "darwin"`
   - the process is not running under the default pytest path
5. The fallback calls `_get_mac_display_profile_bytes()`, then constructs:

```python
imagecms_module.ImageCmsProfile(BytesIO(icc_bytes))
```

The transform itself still uses:

```python
imagecms_module.profileToProfile(source_image, source_profile, display_profile, outputMode="RGB")
```

## CoreGraphics And CoreFoundation

The fallback uses only Python standard library `ctypes`; it does not add PyObjC or any other third-party dependency.

It loads:

```text
/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation
/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics
```

It calls:

```text
CGMainDisplayID()
CGDisplayCopyColorSpace(display_id)
CGColorSpaceCopyICCData(color_space)
CFDataGetLength(icc_data)
CFDataGetBytePtr(icc_data)
ctypes.string_at(ptr, length)
```

The `ctypes` signatures use pointer-safe `ctypes.c_void_p` return types for CoreFoundation/CoreGraphics objects and `ctypes.c_uint32` for `CGDirectDisplayID`.

## Memory Management

Both copied objects follow CoreFoundation Copy ownership and must be released:

- `CGDisplayCopyColorSpace()` returns a color-space object that needs `CFRelease`.
- `CGColorSpaceCopyICCData()` returns a data object that needs `CFRelease`.

The implementation copies bytes with `ctypes.string_at(ptr, int(length))` before releasing `icc_data`, so it never returns a pointer into freed CoreFoundation memory. Release calls run from `finally`, and release failures are swallowed because this path must not crash GUI startup.

## Failure Behavior

Fallback failures return `None` and preserve the existing UI behavior:

```text
Display transform: no display profile, using raw preview
Display transform unavailable: no display profile detected, disabled
```

The fallback catches framework loading errors, missing symbols, invalid pointers, invalid lengths, and Pillow ICC parse failures. Non-macOS platforms return `None` before attempting to load macOS frameworks.

## Test Strategy

Default pytest behavior intentionally disables the real physical-display fallback with:

```python
def _running_under_pytest() -> bool:
    return "pytest" in sys.modules
```

This preserves existing tests where `get_display_profile()` returning `None` means "no display profile." The fallback remains testable because `_mac_display_profile_fallback_enabled()` and `_get_mac_display_profile_bytes()` are private but monkeypatchable.

Added coverage:

- existing active-profile tests still pass
- existing missing-profile tests still pass under pytest default path
- explicit monkeypatched fallback makes `display_profile_available()` return `True`
- explicit monkeypatched fallback makes `display_profile_details()` return a profile
- explicit monkeypatched fallback lets `prepare_output_display_image(... use_display_transform=True ...)` reach the active ImageCms path
- missing fallback bytes degrade to no display profile
- invalid ICC bytes degrade to no display profile
- framework loading failure in `_get_mac_display_profile_bytes()` returns `None`
- macOS-only smoke test parses real CoreGraphics ICC bytes when available and skips when unavailable

## Manual Validation

On a macOS machine:

1. Start Spektrafilm GUI.
2. Confirm Display Transform is not unchecked merely because Pillow `get_display_profile()` returns `None`.
3. Enable Display Transform.
4. Run Preview or Scan.
5. Confirm the status bar shows:

```text
Display transform: active (<profile name>)
```

The profile name is not stable and should not be asserted as a fixed string. It can be `Color LCD`, `Studio Display`, `Display P3`, `ImageCmsProfile`, or another ICC-derived name depending on the display and ColorSync data.

When Display Transform is disabled, the status should remain:

```text
Display transform: disabled
```

Current local evidence:

- Pillow probe returns `None`.
- The CoreGraphics smoke test returns ICC bytes that Pillow can parse.
- Targeted GUI/runtime tests pass after the fallback implementation.

## Limitations

This is a main-display fallback. It uses `CGMainDisplayID()` and does not identify the display that currently contains the Spektrafilm window. If the GUI is moved to an external secondary display, the fallback may use the main display ICC profile rather than the window's display profile. Window-aware multi-display matching should be a separate improvement.

This change does not modify the SDR rendering pipeline, HDR export, gain-map export, profile-aware HDR, film-scan-aware HDR, save-output behavior, or the core film simulation runtime.
