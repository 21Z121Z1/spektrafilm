# Print exposure has no effect after selecting a print profile for positive film stocks

## Summary

When using a positive film stock such as `fujifilm_provia_100f`, selecting a print profile does not make `Print exposure` affect the preview. The GUI appears to keep the simulation on the direct film-scan route (`scan_film=True`), so the print stage is skipped even though a print profile has been selected.

## Reproduction

1. Open the GUI.
2. Import a RAW/image.
3. Select film profile: `fujifilm_provia_100f`.
4. Select print profile: `fujifilm_crystal_archive_typeii`.
5. Adjust `Print exposure`.
6. Run preview, or use auto preview.

## Expected behavior

After the user explicitly selects a print profile, the preview should run the print pipeline. `Print exposure` should change the output preview.

## Actual behavior

Adjusting `Print exposure` has no visible effect. The state remains on `scan_film=True` for positive film stocks, so the runtime takes the direct film-scan route and bypasses printing:

```python
if self.io.scan_film:
    rgb_scan = self._pipeline_scan_film(image)
else:
    rgb_scan = self._pipeline_print(image)
```

## Likely cause

Both profile selectors are connected to the same handler:

```python
widgets.simulation.film_stock.textActivated.connect(controller.apply_profile_defaults)
widgets.simulation.print_paper.textActivated.connect(controller.apply_profile_defaults)
```

That handler runs `digest_after_selection()`, which sets:

```python
params.io.scan_film = bool(params.film.is_positive)
```

For positive film stocks, this means selecting a print profile still leaves `scan_film=True`.

## Suggested fix

Use separate handlers for film and print profile selection:

- Film profile selection can keep the current default route: `scan_film=True` for positive film, `False` for negative film.
- Print profile selection should force `scan_film=False`, because choosing a print profile is an explicit request to preview/scan the print pipeline.

This preserves the useful default for slide film while making print controls behave as expected once a print profile is selected.

## Notes

This is separate from the existing closed issue about DIR coupler amount behavior. Current `main` uses absolute DIR coupler gamma presets for `fujifilm_provia_100f`/`fujifilm_velvia_100`, so this issue is specifically about GUI route selection and print-stage controls.
