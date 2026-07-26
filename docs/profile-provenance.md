# Profile Provenance

Bundled profile arrays are processed simulation inputs. They are not all direct measurements of a physical roll, and the existence of a manufacturer graph does not mean the final bundled array is an untouched copy of that graph.

Every bundled profile therefore carries machine-readable provenance under:

```text
metadata.provenance
```

The schema describes every `ProfileData` field, including runtime-only fields. It does not change the profile arrays or simulation behavior.

## Profile-Level Measurement Status

`measurement_status` describes retained measurement evidence for the profile as a whole. The current 28 bundled profiles use:

```text
no-raw-instrument-data
```

This means the repository does not retain an auditable chain from a documented physical sample and instrument output to the final bundled arrays. Manufacturer and publication graphs may still be valid source inputs, but they are representative published curves rather than exact-roll raw measurements.

Local experimental candidates may use `partial-instrument-data` when a
machine-readable spectrum derived from a physical target is retained but the
raw instrument observations, complete geometry/process record, or uncertainty
chain is not.  That profile-level label does not make a reconstructed field
`instrument-measured`; its field origin is `published-measurement` and its final
status remains `reconstructed`.

Published manufacturer spectral-dye graphs require an additional semantic
boundary.  Fujifilm's professional-film guide states that reversal-film dye
density is measured with a spectrophotometer or colour analyzer as three layer
curves and that the obtained density level is set to 1.0.  Such a graph can
therefore support a same-stock **normalized shape**, but it does not retain the
raw readings, identify absolute dye concentration, or establish a unique
analytical separation.  A digitized final field remains
`manufacturer-graph` / `source-derived`, never `instrument-measured`.

A runtime `channel_density` Y/M/C coordinate is an effective model channel,
not automatically one chemically pure dye.  It can aggregate multiple
same-colour dye species and layer, masking-coupler, or inter-image effects.
Silva et al. (2022), *Contributions to the Characterization of Chromogenic
Dyes in Color Slides*, resolved two magenta HPLC-DAD peaks in extracted Provia
400X material.  Because that is solution-state chemistry from a different
stock, it is only a methodological and chemical example; it neither derives
nor validates Provia 100F's numeric channels.

## Field Labels

Each field has two independent labels.

### `origin`

| Value | Meaning |
| --- | --- |
| `instrument-measurement` | The starting evidence is retained physical-sample instrument data. No current bundled profile uses this origin. |
| `published-measurement` | The starting evidence is a published machine-readable spectrum derived from a physical target, but raw instrument observations and a complete measurement chain are not retained. No current bundled default uses this origin; local candidates may. |
| `manufacturer-graph` | The starting shape came from a same-stock manufacturer graph. |
| `manufacturer-composite-graph` | The source supplied a composite curve such as Minimum Density or Midscale Neutral, not separated CMY components. |
| `generic-reference` | The starting basis was generic rather than stock-specific. |
| `related-profile` | Another bundled stock/profile supplied the field or starting basis. |
| `generated` | The field started as an internal grid, fit, or model object rather than a same-semantics source curve. |

### `status`

| Value | Meaning |
| --- | --- |
| `instrument-measured` | Retained raw instrument data directly supports the final field. No current bundled profile uses this status. |
| `source-derived` | A matching source graph exists, but the final array has been digitized, resampled, normalized, balanced, or otherwise processed. |
| `reconstructed` | The final field was solved from source constraints, priors, donor shapes, or other profile fields. |
| `inherited` | The field was copied from another profile rather than independently sourced for this stock/process variant. |
| `generated` | The field is an internal coordinate or generated representation. |
| `optimized` | The final field was tuned or refit for model/runtime behavior. |

`sources` refers to entries in the profile's `source_references`. `derived_from` records the donor field path when one is known. `transformations` records the material processing steps relevant to the label. `notes` captures semantic caveats such as peak normalization or a missing fourth source layer.

## Important Current Classifications

- C200, Pro 400H, X-Tra 400, Ektar 100, Gold 200, Portra 160/400/800, and Ultramax 400 use a generic `Film A` CMY prior followed by stock-constrained reconstruction.
- Portra 800 Push 1 and Push 2 inherit sensitivity, CMY, minimum density, and midscale-neutral spectra from base Portra 800. Their characteristic-curve inputs are push-specific.
- Verita 200D uses Vision3 50D as its CMY donor.
- Crystal Archive Type II uses its own manufacturer sensitivity and CMY graph shapes but uses Supra Endura as its characteristic-curve donor.
- Supra Endura uses Portra Endura as sensitivity and CMY donor.
- Positive-film and printing profiles reconstruct `base_density` and `midscale_neutral_density` internally from sensitometric/dye inputs.
- Provia 100F now cites AF3-036E exactly.  Its native separated Y/M/C masks
  support the bundled channel-shape origin; a separate local candidate combines
  that normalized shape with grouped public GS0 data, without changing the
  bundled default.
- Velvia 100 now cites AF3-202E exactly.  Independent vector extraction matches
  the bundled normalized channels closely enough that direct numeric
  replacement was rejected rather than treated as an improvement.  A separate
  Avian Rochester MicroCalT24 exact-stock graph stress also favours the bundled
  basis; the ColorReference-derived base/effective-basis files are therefore
  corpus-specific exploratory candidates, not promotion-ready defaults.
- Kodachrome 64 Figure 5 from Scarpace and Friederichs (1978) validates the
  bundled normalized channel shape only.  The paper's physical-patch-derived
  components were oriented toward manufacturer priors, so it is not a unique
  blind dye separation or an absolute-density source.
- All `density_curves_layers`, `density_curves_model`, and Hanatos 2025 adaptation parameters are internal reconstructed, generated, or optimized fields.

## Interpretation Rules

1. Never infer `instrument-measured` from a source citation alone.
2. Never describe `manufacturer-graph` plus `reconstructed` or `optimized` as a direct manufacturer array.
3. A field with `manufacturer-composite-graph` does not prove independently measured C/M/Y components.
4. A related-profile donor must keep `derived_from`; visual similarity or a shared datasheet is not enough to relabel it as same-stock source-derived.
5. Runtime aesthetic or neutral-print fitting must remain visible as a transformation/status and must not overwrite measurement provenance.
6. Independent evidence used only to validate a field belongs in
   `source_references` or notes; it must not be added to that field's `sources`
   as though it generated the bundled array.
7. Differences between manufacturer document revisions are a
   `source_revision_envelope`, not graph-extraction noise or a statistical
   confidence interval.
8. A candidate that passes its source-corpus gate can be demoted by later
   independent same-stock evidence.  Preserve both decisions and do not relabel
   the originating manifest as independent confirmation.

## Compatibility And Validation

Profiles without provenance remain loadable and receive an empty schema with `measurement_status = "unknown"`. All bundled profiles are required by tests to provide provenance for every `ProfileData` field. Tests also lock the known generic and donor relationships so later profile regeneration cannot silently upgrade reconstructed fields to direct-source claims.

Historical recipe evidence used for the first provenance pass is available in Git commit `91ce0f7a`. The historical creator contained digitized CSVs and recipes but did not retain raw instrument measurements or source PDFs, so these labels intentionally stop short of exact-roll measurement claims.
