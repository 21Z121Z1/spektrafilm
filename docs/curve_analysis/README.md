# Curve Analysis Corpus

This directory is mostly generated documentation for film+paper HDR curve behavior. The key conclusion is in the summary report: HDR mapping should depend on the joint film-stock plus print-paper response, not only on the film or paper in isolation.

## Entry Points

| Path | Use |
| --- | --- |
| [`film_print_hdr_analysis.md`](film_print_hdr_analysis.md) | Human summary and engineering interpretation. Start here. |
| [`curve_analysis.json`](curve_analysis.json) | Machine-readable analysis data. |
| [`analyze_curves.py`](analyze_curves.py) | Script that runs film/paper combinations through the simulator and fits curves. |
| [`generate_all_md.py`](generate_all_md.py) | Script that generates per-combination Markdown reports from `curve_analysis.json`. |

## Generated Reports

There are 160 per-combination Markdown reports named:

```text
<film>_on_<paper>.md
```

The corpus covers 20 film variants and 8 print-paper profiles. Use the per-combination files when investigating a specific profile pair; otherwise prefer the summary report.

## Maintenance Notes

- Do not hand-edit generated per-combination reports unless the generator output is intentionally being corrected.
- If `curve_analysis.json` changes, regenerate the per-combination Markdown with `generate_all_md.py` so the corpus stays coherent.
- Keep the summary report aligned with generated data when changing HDR curve-profile logic.
