import os
from pathlib import Path
import re

docs = [
    "docs/superpowers/plans/2026-05-23-hdr-diffuse-white-calibration.md",
    "docs/superpowers/plans/2026-05-24-hdr-scene-linear-exr.md",
    "docs/superpowers/plans/2026-05-24-raw-hdr-scene-energy-import.md",
    "docs/superpowers/plans/2026-05-24-gui-release-hardening.md",
    "docs/superpowers/plans/2026-05-23-aces-color-management.md",
    "docs/superpowers/plans/2026-05-24-auto-exposure-scene-linear.md",
    "docs/superpowers/plans/2026-05-24-film-simulation-lossless-speed.md",
    "docs/superpowers/plans/2026-05-24-scene-energy-hdr-gainmap-autoexposure.md",
    "docs/superpowers/plans/2026-05-23-hdr-photo-mapping.md",
    "docs/superpowers/plans/2026-05-23-hdr-photo-mapping-execution.md"
]

update_note = """

---
## [Resolved] 2026-05-24 / 2026-05-25 Session Update
- **Dual-Layer HDR Mapping (Diffuse Lift + Specular Rolloff)**: Successfully split HDR target into Diffuse Lift and Specular Rolloff layers. This completely fixes the problem where the simulation SDR aesthetic contrast broke midtones when scaling into HDR.
- **SDR Base Contrast Fix**: Refactored `_graft_scene_luminance` to strictly separate unlifted (SDR) and lifted (HDR) renditions.
- **RGB Gain Map Integration**: Enabled automatic RGB gain map generation via CoreImage by passing `hdrGainMapAsRGB=true` to the Swift encoder options.
- **GUI Controls Exposed**: Added a dedicated "HDR Export Settings" panel in the GUI to control `hdr_diffuse_lift_strength`, `graft_strength`, `paper_rolloff_exposure_scale`, `paper_rolloff_k`, and `max_headroom`. Setting `hdr_diffuse_lift_strength` to 0 completely disables the diffuse lift layer.
"""

for doc in docs:
    path = Path(doc)
    if not path.exists():
        continue
    content = path.read_text(encoding="utf-8")
    
    # Strip the appended note
    if update_note in content:
        content = content.replace(update_note, "")
        path.write_text(content, encoding="utf-8")
        print(f"Reverted {doc}")
