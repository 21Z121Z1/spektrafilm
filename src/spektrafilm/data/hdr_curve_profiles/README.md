# HDR Curve Profiles v2

This directory contains machine-readable sampled Spektrafilm film/paper tone curves for profile-aware HDR photo export.

The samples are generated from the deterministic Spektrafilm runtime with stochastic and spatial effects disabled. Each profile uses a neutral scene-linear RGB ramp where `scene_y=1.0` is diffuse white. Luminance is computed with Rec. 709/sRGB linear luma coefficients `(0.2126, 0.7152, 0.0722)` and max/min channel values are also recorded for headroom and tint diagnostics.

Regenerate with:

```bash
uv run python tools/export_hdr_curve_profiles.py
```

Profiles whose sampled luminance curve is decreasing or nonmonotonic are marked unsafe for the increasing profile-aware HDR mapping path and must fall back to generic mapping.
