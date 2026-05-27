# spektrafilm_lut_creator — LUT export layer

Builds 3D LUT bundles that capture the spektrafilm simulation for deployment in
external tools (DaVinci Resolve, Nuke, OBS, OCIO-aware DCCs, stills photo apps).

## Philosophy

This package owns the **complexity of LUTs** so the runtime doesn't have to. It
is a layer above `spektrafilm`, depending on it but never imported by it.

The split is deliberate:

- `spektrafilm` is the physical core. It speaks linear-light RGB in named
  primaries. It does not know about LUTs, .cube files, OCIO configs, transport
  encodings, registries, or sampling grids.
- `spektrafilm_lut_creator` knows about all of those things. It configures the
  runtime through the runtime's natural API (`RuntimePhotoParams`,
  `SimulationPipeline.process`) and translates between the runtime's
  linear-light contract and the encoded, bounded `[0, 1]` world that LUT formats
  demand.

## What lives here

- **Command-line interface** (`cli.py`) — `spektrafilm-lut build` and
  `spektrafilm-lut list KIND`. Accepts color spaces as canonical registry names
  (`"Panasonic V-Log"`) or short-tag slugs (`vlog`); the full `BundleSpec` is
  also loadable from TOML via `--from spec.toml`. CLI flags override TOML when
  both are present.
- **Color-space registry** (`color_spaces.py`) — gatekept list of curated
  `(name, primaries, CCTF, kind, role)` entries. Decouples primaries from CCTF
  (so Apple Log + BT.2020 and BMG5 + BMD Wide Gamut can be expressed); validates
  resolutions at import time.
- **Transport encodings** (`shapers.py`, plus the registry's `decode_cctf` /
  `encode_cctf`) — CCTF curves, log curves, HDR PQ / HLG. The runtime never
  touches these; the LUT creator applies them at its boundary with the runtime.
- **Wire contracts** (`wires.py`) — typed records for log-E and density wires
  that show up between LUTs in multi-LUT bundles.
- **Sampling grids** (`grid.py`) — Adobe-canonical `(N**3, 3)` grids plus
  image-shape reshaping for the pipeline.
- **Formats** (`formats/`) — pluggable readers/writers; v1 ships
  `cube` (Adobe), `lumix` (Lumix-strict `.cube` variant with
  `#LUMIXPHOTOSTYLE`), `3dl` (Autodesk 10-bit Lustre), and `hald_png`
  (Hald-CLUT 8-bit PNG for Photoshop / OBS / ImageMagick). OCIO config
  emission is its own sibling in `ocio_emit.py`.
- **Bundles** (`bundles.py`, `builders.py`) — `BundleSpec` / `BundleBuilder`
  orchestrating one or more LUT bakes; `BundleMeta` for `bundle.json` side-cars.
  Bundle READMEs lead with a "What this is / what this isn't" framing
  (n090 §5.1) and, when QA runs, surface a "## Quality" pass/fail badge
  block (n090 §6.1).

## The boundary with the runtime

The LUT creator always hands the runtime linear-light RGB and always gets
linear-light RGB back. Specifically:

1. Generate a sampling grid in the encoded input space (e.g., grid in sRGB code
   values, or Apple Log code values).
2. `decode_cctf(grid, input_name)` → linear-light RGB in the input space's
   primaries.
3. Configure `RuntimePhotoParams.io.input_color_space =
   registry.get(input_name).primaries`, `input_cctf_decoding = False`.
4. Run the pipeline; receive linear-light RGB in the output primaries.
5. `encode_cctf(output, output_name)` → encoded LUT values.
6. Pack into `Lut`, write `.cube` + `bundle.json`.

This works uniformly for every (primaries, CCTF) combination — SDR, camera log,
HDR. The runtime never sees the curves.

## Layering rule

`spektrafilm_lut_creator` imports from `spektrafilm`. **Never the reverse.** If
the runtime starts needing something defined here, it gets moved into the
runtime — not imported up the stack.

This means: the registry stays here. The runtime's color handling is "a
colour-science colourspace name + linear-or-encoded flag," and that is
intentionally less expressive than the registry. The expressive side lives here.

## What lives here and not in the runtime

- Curated lists of names. The runtime accepts any colour-science primaries name;
  the registry curates which names ship.
- Format-specific I/O. `.cube` and (future) `.3dl`, hald PNG, OCIO configs all
  live here.
- Knowledge that LUTs need shapers, normalization, `[0, 1]` domains, trilinear
  interpolation, peak-luminance assumptions. The runtime is blissfully unaware.

## Where to look

- `cli.py` — the `spektrafilm-lut` command-line entry point
- `color_spaces.py` — the gatekept registry (22 entries in v1, 27 in v2)
- `wires.py`, `shapers.py` — wire math
- `grid.py` — sampling-grid helpers
- `formats/cube.py` — Adobe .cube reader/writer
- `formats/lumix.py` — Lumix-strict .cube variant
- `formats/threedl.py` — Autodesk .3dl writer
- `formats/hald_png.py` — Hald-CLUT PNG writer
- `bundles.py` — `BundleSpec` (user-facing) + `Bundle` (built artifact)
- `builders.py` — `BundleBuilder` orchestrator
- `metadata.py` — `BundleMeta` (bundle.json schema)

## Open design notes

Recorded in
[`spektrafilm-research/studies/a40_lut_system/`](../../../spektrafilm-research/studies/a40_lut_system/):

- n010 initial plan, n020 dispatcher design (now in runtime)
- n030 LUT package design — the structural plan this package follows
- n040 color-space registry design
- n060 v2 research synthesis (color space additions and tier ordering)
- n070 runtime architecture split (the linear-in/linear-out contract)
