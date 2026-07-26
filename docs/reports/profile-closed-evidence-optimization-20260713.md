# Profile Closed-Evidence Authenticity Optimization — 2026-07-13

## Decision first

This pass produced a reproducible, conservative improvement path without
contacting a manufacturer or author and without obtaining new film:

- The 28 bundled profile `data` arrays remain unchanged.  None of the results
  below authorizes replacing a bundled default.
- Five local candidate files pass the gates declared by their originating
  runs, across two authoritative manifests.  That is not a global promotion
  decision.  Four come only from the public patch
  corpus: Provia 100F effective output base, Velvia 100 effective output base,
  a Velvia 100 base-plus-effective-rank-3 basis, and Endura Premier effective
  reflection-output base.  A fifth combines the grouped Provia GS0 base with
  the exact-stock Fujifilm-published normalized Y/M/C graph.
- The Provia manufacturer-graph candidate is the most directly source-
  constrained Provia candidate: its base is reconstructed from 31 public
  archives in 14
  `PROD_DATE` proxy groups, while its 400--700 nm channel shapes are digitized
  from AF3-036E and restored to the bundled peak amplitudes.  It is
  **source-derived normalized shape plus an effective base**, not raw
  analytical dyes, absolute dye quantities, or exposure-response calibration.
- The separate patch-only Provia effective basis remains rejected because one
  full-data channel similarity was below its final-analysis gate.  The Ultra
  Endura output-base candidate remains rejected because one proxy group
  exceeded the maximum allowed p95 colour-difference regression.
- Direct replacement of Velvia 100 with the re-extracted manufacturer graph
  was rejected: the bundled curves already match the graph at approximately
  `0.99998--0.99999` cosine similarity and the small numerical replacement did
  not improve held-out results robustly.  A second-provider MicroCalT24 graph
  stress also favours the bundled basis and rejects the public effective-basis
  candidate in every one of 243 extraction variants.  Both Velvia public
  candidates are therefore demoted to corpus-specific exploratory artifacts.
- Kodachrome 64 Figure 5 independently supports the bundled normalized shape
  (`0.99982--0.99995` cosine similarity on the non-extrapolated 20 nm grid),
  but remains validation-only.
- A generalized Williams--Clapper diagnostic substantially improved Ultra and
  Premier reflection reconstruction, but `0.83%--1.01%` of held-out spectral
  elements exceeded the training-derived paper-white inverse domain.  No
  reflection-model candidate was emitted, no physical C/M/Y separation was
  claimed, and DP II remains distinct from Type II.
- Two Velvia archives, `N090322` and `N091125`, were excluded after
  duplicate-content QA found that their parsed 288×41 spectra are exactly
  identical despite different `PROD_DATE` values.  Excluding both removes
  cross-group leakage; the Velvia decisions still pass with 19 archives across
  8 proxy groups.
- The E240220 and R240103 downloads remain excluded from Ektachrome E100 and
  Crystal Archive Type II respectively because their material identities do
  not match exactly.
- Every bundled `ProfileData` field now has origin/status provenance, but no
  bundled profile currently claims retained raw instrument data.  Qualitative
  `ProfileInfo` settings such as `antihalation` are outside this numerical
  evidence fit and must not be inferred to have been measured by this work.

The machine-readable run is
`tmp/profile-public-batch-report-grouped.json`, SHA-256
`bb004d7be628f65417356e7951ee42d7034a04db3cbfc6eece80d1d895f246a2`.
The only authoritative list of
candidate files for that run is
`tmp/profile-public-batch-candidates/CURRENT_CANDIDATES.json`, SHA-256
`13977fbf74d9d8ddd9a89e7ca63fb14296a220803bfe3c9c6e98ab8511296ff3`.
Other files in that temporary directory may be stale exploratory outputs.
The combined analysis-code SHA-256 recorded by this run is
`4b8b81179b999ed8f8fa684b4863738566297eb148d31b830cd05fdcd201a63a`;
candidate identities also include a hash of the bundled numeric prior and the
analysis context, so a later code/prior change cannot silently reuse the same
candidate name.

The separate source-curve manifest is
`tmp/profile-source-curves/CURRENT_SOURCE_CURVE_CANDIDATES.json`, SHA-256
`be1272de92c6325232bfdc4828bd72ff353138a6c94cb19600d5c685adaf325e`.
It lists exactly one local Provia candidate and explicitly leaves default
replacement and redistribution unauthorized.

## Scope and evidence rules

The closed-evidence constraint for this work is:

1. do not contact manufacturers, laboratories, target vendors, or paper
   authors;
2. do not depend on acquiring or exposing a new film or paper sample;
3. use only already downloaded data, legally accessible public material,
   official historical/technical documents, and repeatable local computation;
4. require an exact stock/material identity before a numeric candidate can
   constrain that profile;
5. keep measurement, graph digitization, reconstruction, inheritance,
   generation, and runtime optimization separate;
6. treat an improvement in patch reconstruction as evidence for an effective
   spectral model only, never automatically as identification of analytical
   dyes or exposure-response curves;
7. keep candidate generation local until provenance, licence, held-out
   reconstruction, interpolation, runtime, and regression gates all pass.

The source search covered manufacturer technical/R&D pages, the public
[ColorReference target archive index](https://www.colorreference.de/targets/index.html),
publisher and institutional paper pages, ISO catalogue records, Zenodo,
Figshare, Mendeley Data, Dryad, GitHub, and institutional repositories.  This
systematic search found no second independent, openly reusable, same-stock raw
spectral matrix for Provia 100F or Velvia 100.  On 2026-07-16 it did find an
independent exact-stock Velvia 100 source: Avian Rochester's public MicroCalT24
nominal transmittance graphs.  Those graphs are useful validation evidence but
are not a downloadable numeric matrix and carry no open derivative licence.
These are time-bounded search results, not claims that stronger data cannot
exist elsewhere.

## What a defensible C/M/Y curve means

An analytical dye model would require

```text
D(lambda) = D0(lambda) + sum_i q_i * d_i(lambda)
```

For transmission, `D(lambda) = -log10(T(lambda))` under a specified measurement
geometry.  `D0` is a same-geometry, independently characterized non-image
base-plus-fog term; a finished-product GS0 Dmin patch is not automatically
`D0`.  The isolated spectra `d_i` and physical dye amounts `q_i` must be
supported by selective chemistry, known mixtures, or equivalent physical
evidence.  The current candidates do **not** meet that definition.  Their
operational runtime model is instead

```text
D_hat(lambda) = B_eff(lambda)
              + z_C * G_C(lambda)
              + z_M * G_M(lambda)
              + z_Y * G_Y(lambda)

z_i >= 0
G_i(lambda) >= 0
```

Here `B_eff` is a product/output-domain effective base, `G_i` are effective
generators, and `z_i` are patch-specific latent non-negative coordinates—not
known dye amounts.

Two meanings must remain distinct:

- **Analytical dye curve**: an isolated dye or dye-family density spectrum,
  supported by selective chemistry, controlled separations, known dye amounts,
  or equivalent physical evidence.
- **Effective generator**: a non-negative rank-3 basis that reconstructs
  observed stock spectra well and is aligned to C/M/Y semantics by explicit
  priors and constraints.

Patch spectra alone generally identify a low-dimensional subspace, not a
unique basis.  Permutation, scale, and mixing transformations can preserve the
same reconstruction.  NNLS can absorb channel scale changes into `z_i`, so a
lower residual does not validate a new absolute density amplitude.  The
candidate code therefore preserves the bundled per-channel peak scale and
interpolates only a published-measurement-grid shape delta.

The physical chemistry can also be richer than three molecules.  The
downloaded Provia 400X conservation study reported four visible HPLC-DAD
peaks—one cyan, one yellow, and two magenta components—after separation.  The
paper's HRMS/MS work was performed on Ektachrome 160T, not on this Provia 400X
sample.  Provia 400X is also a different stock, so it cannot refit Provia 100F;
the two magenta peaks only support the inference that a runtime C/M/Y channel
can aggregate multiple dye species.  See the open-access
[Heritage study](https://www.mdpi.com/2571-9408/5/4/203).

## Downloaded data: identity and permitted use

| Download | Declared material | Identity against bundled profile | Corpus eligibility / permitted use |
| --- | --- | --- | --- |
| `F240222` | Fujichrome Provia 100F (RDP III) | Exact | Eligible as one member of the 31-archive Provia corpus; it cannot alone establish the grouped candidate. |
| `N230513` | Fujichrome Velvia 100 (RVP 100) | Exact | Eligible as one member of the final 19-archive Velvia corpus; the corpus, not this file alone, supports the passing candidates. |
| `E240220` | Kodak Ektachrome Product Family | Not exact E100 | Family-level context only; no E100 field validation or numeric change. |
| `R110714` | Kodak Professional Ultra Endura | Exact | Eligible in the 18-archive black-backed 45/0 reflection corpus; that corpus's current base candidate failed. |
| `R200204` | Kodak Professional Endura Premier | Exact | Eligible in the 16-archive reflection corpus that supports the local effective-output-base candidate. |
| `R240103` | Fujicolor Crystal Archive Paper DP II | Not Type II | Never map to the bundled Crystal Archive Type II profile; consider only a separate DP II experiment. |

Fujifilm's professional-film guide independently maps `RDP III` to Provia 100F
and `RVP 100` to Velvia 100 and documents E-6/CR-56 processing:
[Professional Film Data Guide](https://asset.fujifilm.com/www/us/files/2020-03/85d928f44b0df3b2a95913e46608881d/ProfessionalFilmDataGuide.pdf).
The exact current manufacturer graph context is also available in the
[Provia 100F sheet](https://asset.fujifilm.com/www/us/files/2020-03/dc6e1c21c643f82b7fb393cef94d524a/Provia100FAF3-036E.pdf),
[Provia R&D report](https://asset.fujifilm.com/www/jp/files/2019-09/2a15e9d6cbc116f67a6ada2c2b239c61/rd_report_ff_rd046_001.pdf),
and [Velvia 100 R&D report](https://asset.fujifilm.com/www/jp/files/2019-10/d2a435c2e3c6481447ecdbc0c29d75f0/rd_report_ff_rd049_003.pdf).

Each selected transmission archive contains 288 unique patches.  The TSV
members contain 41 values from 380–780 nm in 10 nm steps; Velvia archive
`N110201` instead contributes a CxF member with 36 values from 380–730 nm.  The
evaluation uses the common profile-supported wavelength grid, so that shorter
CxF support does not create extrapolated evidence.  The files state that
underlying 3 nm measurements were interpolated under ISO 13655:2009 Annex I,
but they do not include the raw 3 nm observations, instrument model, detailed
geometry, exposure target count, processing record, uncertainty budget, or an
explicit open derivative licence in the reviewed materials.  The published
spectra therefore give reconstructed base fields the origin
`published-measurement`, with profile measurement status
`partial-instrument-data`; they are not labelled raw instrument measurements.
The Velvia effective channel remains a hybrid: its origin stays
`manufacturer-graph`, the public patch-spectra source is added, and its final
status is `reconstructed`.

The selected reflection archives contain 288 unique patches at 31 values from
400–700 nm in 10 nm steps and represent final black-backed 45/0 reflectance.
They cannot be interpreted as single-pass dye transmission.  Reflection-print
models must account for coating interfaces, backing, scattering, and repeated
light paths; the downloaded method paper makes this failure of simple Beer-law
interpretation explicit.  See the primary
[reflection dye-density paper](https://library.imaging.org/admin/apis/public/api/ist/website/downloadArticle/cic/3/1/art00039),
the original [Williams–Clapper model](https://opg.optica.org/josa/abstract.cfm?uri=josa-43-7-595),
and its [generalization](https://library.imaging.org/admin/apis/public/api/ist/website/downloadArticle/jist/45/5/art00010).

## Manufacturer graph extraction and validation

Fujifilm's professional-film guide gives the semantics that were previously
missing from the profile labels: the reversal-film spectral dye-density graph
is produced with a spectrophotometer or colour analyzer for the three colour
layers and is normalized so the obtained density level is 1.0.  Consequently,
the graph is stronger than an invented curve but weaker than retained raw
instrument readings or a concentration-calibrated analytical dye spectrum.

[`profile-source-curve-digitization.py`](profile-source-curve-digitization.py)
extracts the exact-stock product graphs with calibrated axes, repeat sampling,
alternate axis/centre methods, cross-edition envelopes, and fixed 5 nm output.
Its script SHA-256 is
`297ffa28180394e26aa6ba1de20df23f8f2dcb963e918c5edcf68a9d1c5f6d89`;
the JSON report SHA-256 is
`7d8803c422dab4fd3d852b9b7d064053cbed2ed8bd0f68b1d3ccb56650a6a052`.
That report now hashes its emitted Provia CSV (`a5200fe818559d7af7dfbbc86a14d975ef5123ac1530b3e37a01d4fdaca29a65`),
Velvia CSV (`ab2edffee41e7341336467ee77679a585db6411e495231dd8752ba5ff42698bf`),
and comparison plot (`d21db07bc7733371d5fce2f870ba67dd5d2b20a4e758c2bc220e68b1eeda921b`)
to prevent a report/output freshness mismatch.
The primary source files and hashes are:

| Stock / source | Source semantics | SHA-256 |
| --- | --- | --- |
| Provia 100F AF3-036E product sheet | Same-stock normalized Y/M/C graph; primary extraction | `e28d54e76e8fcdf44c8ffacc930b5b8f2ea54a7cdaeedfcc91790e68eb599de8` |
| Velvia 100 AF3-202E product sheet | Same-stock normalized Y/M/C graph; primary extraction | `4c57a27b978311ca2ef819f2bf2d74c757639d27f9f0bd94e5f49c4b1c3d5902` |
| Fujifilm Professional Film Data Guide | Measurement semantics and Provia cross-edition graph | `64c6455651b9f13f5cd190219e4928d1fdf13ecf33859c4691d830bced8d3d36` |

Normalized bundled-versus-primary-graph comparisons are:

| Stock | Y cosine / RMSE | M cosine / RMSE | C cosine / RMSE | Consequence |
| --- | ---: | ---: | ---: | --- |
| Provia 100F | 0.999345 / 0.01661 D | 0.998435 / 0.02888 D | 0.999182 / 0.02263 D | Bundled shape is source-consistent, but the independently extracted graph is different enough to test as a candidate. |
| Velvia 100 | 0.999989 / 0.00221 D | 0.999975 / 0.00355 D | 0.999991 / 0.00244 D | Bundled numbers already reproduce the source graph; retain them. |

[`profile-manufacturer-curve-validation.py`](profile-manufacturer-curve-validation.py)
then holds the manufacturer shape fixed, derives each training base only from
non-held-out groups, and fits held-out patch coefficients independently.  For
Provia, the fixed graph replacement improves all five metrics in all 14 proxy
groups; every one-sided descriptive sign test is `p = 0.00006103515625`, and
the decision survives all alternate extraction variants.  For Velvia, direct
graph replacement slightly improves density RMSE but regresses transmission
and colour metrics, including the chronological stress slice; it is rejected.

The final Provia joint two-field comparison uses the bundled default as the
baseline and a training-only group-equal GS0 base plus AF3-036E normalized
shapes as the candidate.  Group-macro improvements are 79.39% density RMSE,
79.56% transmission RMSE, 58.89% median DE00, 66.36% mean DE00, and 73.06%
p95 DE00.  All five metrics win in all 14 groups.  The newest three groups
also improve by 61.37%--81.45%, but they are a chronological stress slice of
the same corpus, not independent replication.

The emitted candidate replaces 67 `base_density` points on the shared
385--715 nm support and 61 `channel_density` points on the source-supported
400--700 nm range.  It preserves the three bundled channel peaks exactly,
leaves the channel values outside 400--700 nm unchanged, and leaves
`density_curves`, `log_sensitivity`, `midscale_neutral_density`, and the
exposure-to-density runtime mapping unchanged.  Linear 10-to-5 nm base
interpolation is selected as the non-overshooting lower-assumption method;
PCHIP is sensitivity-only.  Their p95 base difference is `0.00305 D`, runtime
p95 difference is `0.07043` DE00, and maximum SDR difference is `0.000611`.
The manufacturer-validation script SHA-256 is
`fa293e7e7738023097631915ecae1d111cf3e1bdd7bd06a64353dcc8559dc7e5`;
its JSON report SHA-256 is
`37a450a3855733a51b6f96e557b085bd8695ceeba4ee8fb7876f406926592a56`.

## Independent Velvia 100 MicroCalT24 stress

The current [Avian Rochester MicroCalT24 page](https://www.avianrochester.com/microcal24t/)
and its public brochure explicitly identify the target film as Fujifilm Velvia
100.  They publish nominal transmittance graphs for 18 chromatic and 6 neutral
patches from 400--700 nm.  Individually calibrated NIST-traceable values are a
commercial deliverable; no public numeric matrix, instrument/geometry record,
processing record, patch-to-curve legend, or open derivative licence is
provided.  This is therefore an independent graph-based validation source,
not refit-capable data.

[`profile-velvia-microcal-validation.py`](profile-velvia-microcal-validation.py)
extracts only visible exact-colour pixels from the 18 chromatic curves.  It
does not interpolate line segments hidden by overlaps.  The highest dotted
neutral curve supplies a same-target effective-white reference; it is not
called GS0, base-plus-fog, unexposed film, or analytical Dmin.  The primary
extraction contains 1005 visible chromatic points and 58 effective-white
points.  The source overlay was visually checked against both public PNGs and
the rendered two-page brochure.

With the same extracted effective white held fixed, the independent
basis-only reconstruction is:

| Fixed basis | Density RMSE | Transmittance RMSE, percentage points | Per-curve wins vs bundled, D / T |
| --- | ---: | ---: | ---: |
| Bundled Velvia basis | 0.024466 D | 1.10884 | baseline |
| Public ColorReference effective rank-3 basis | 0.024942 D | 1.22166 | 5 / 5 of 18 |
| AF3-202E manufacturer-normalized basis | 0.024504 D | 1.11677 | 6 / 5 of 18 |

The public effective basis regresses the micro density metric by 1.94% and
transmittance metric by 10.17%.  Across 243 combinations of graph-axis centres
and pixel windows, it improves both metrics zero times: density regression is
1.12%--3.00% and transmittance regression is 9.70%--11.47%.  The manufacturer
re-extraction is effectively tied in density but regresses transmittance by
0.24%--1.02% in every variant.  This independently supports retaining the
bundled Velvia channel numbers.

The effective-white base stress also favours the bundled base over the public
grouped GS0 candidate (`0.03572` vs `0.06099 D`; `5.84` vs `8.89` percentage
points).  Because the plotted white is not documented as GS0 or base-plus-fog,
this can reject cross-source generalization but cannot identify the physical
base field.  Absolute full-profile reconstruction is mixed--the bundled model
has lower density error while public-base models have lower transmittance
error--so no base promotion is authorized.

The script SHA-256 is
`9cc808b1ecec47ead3bcc126f0b78ad7af6b1936faeb5471fc1617982c479d88`;
the JSON report SHA-256 is
`3ad83f3dfe67daf4ba97593f64e0487875292dfcb2d038d379dcc4c0cba574a7`.
Pinned source SHA-256 values are `0df3908a...` for the brochure,
`74fde88b...` for the chromatic graph, and `17e55ce3...` for the neutral graph.
No source image or digitized array is added to package data.

## Reproducible evaluation design

The implementation is
[`profile-public-batch-validation.py`](profile-public-batch-validation.py).
It applies the following controls:

1. discover and cache all 153 archives listed by the public index;
2. select exact `MATERIAL` strings only;
3. prefer structured archive metadata over unrelated or incorrect diagnostic
   text (`R110714/Extras/Fault.txt` names another batch and is not identity
   evidence);
4. validate patch uniqueness, canonical patch ordering, wavelength grids,
   finite values, and raw-zero handling;
5. hash canonical parsed patch names, wavelength grids, and spectra; if exact
   spectral content occurs under different `PROD_DATE` values, exclude every
   ambiguous copy rather than leak the same matrix across train/test groups;
6. group every archive sharing `PROD_DATE` as one conservative **target
   production-date proxy**.  It is not claimed to be a film manufacturing lot
   or emulsion batch;
7. take an archive median within each proxy group, then a group-equal median
   across groups, preventing dates with many archived scans from receiving more
   weight;
8. hold out complete proxy groups.  No archive from a held-out group can appear
   in training;
9. fit latent patch coordinates from held-out patch spectra with NNLS.  This
   tests base/basis spectral reconstruction, not prediction of coefficients
   from scene exposure;
10. for transmission-only channel candidates, fit multiple non-negative
   initializations, align them to the bundled C/M/Y prior, choose the
   configured smallest positive blend (`alpha = 0.25`), preserve bundled peak
   scales, and hold out the newest target-date proxy groups separately;
11. run finite-value, neutral-ramp monotonicity, determinism, linear-versus-
    PCHIP interpolation, unchanged-support, and exact-zero-delta runtime checks.

Gate thresholds are conservative Spektrafilm engineering policy.  They are not
requirements supplied by an ISO standard or cited paper.  In particular, the
base gate requires at least eight target-date proxy groups, improvements in both
micro and group-macro metrics, sign-test support for primary metrics, no
single-group regression above 5%, and a runtime pass.  The effective-basis gate
also requires full/fold channel similarity, peak stability, all newest-group
primary-metric wins, amplitude preservation, and interpolation/runtime checks.
Because all groups come from one target-provider ecosystem and `PROD_DATE` is
only a proxy, the paired sign-test p-values are descriptive within this corpus;
they are not proof of independent film-lot replication.

## Grouped results

Values below are target-production-date-proxy group macro means at the primary
measurement floor: `1e-3` transmission for film and `1e-2` reflection for
paper.  Density is in optical-density units; transmission/reflection RMSE is in
percentage points.  DE00 values are differences in the evaluation conversion,
not an independent instrument colour-accuracy certification.

| Exact material | Archives / `PROD_DATE` groups | Density RMSE bundled → candidate | T/R RMSE bundled → candidate | Median DE00 bundled → candidate | p95 DE00 bundled → candidate | Base decision |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Provia 100F | 31 / 14 | 0.21225 → 0.05294 | 6.8150 → 1.5429 T | 2.9307 → 1.5054 | 9.7813 → 2.9096 | Pass; local base only |
| Velvia 100 | 19 / 8 | 0.10758 → 0.03184 | 5.3633 → 0.6127 T | 3.2465 → 0.6502 | 6.9998 → 2.2425 | Passes source-corpus gate; fails independent MicroCal promotion stress |
| Ultra Endura | 18 / 16 | 0.18074 → 0.16762 | 7.8870 → 5.4113 R | 4.6150 → 4.3624 | 10.2040 → 9.9026 | Reject |
| Endura Premier | 16 / 15 | 0.05228 → 0.03413 | 3.2230 → 1.4431 R | 1.6224 → 0.6008 | 3.2166 → 1.7092 | Pass; local effective reflection base |

`R041016` was excluded because its archive contains no machine-readable
reflection spectra.  Velvia `N090322` and `N091125` were both excluded because
their exact parsed spectral-content SHA-256 is
`8568bb0abe866d81cd7e76cebc1f4fc0a32cf9848e5580cfb28d981a6070d49f`
while their proxy groups are `2008:03` and `2009:05`.

For Velvia 100, with the same grouped GS0 effective base held common to both
channel alternatives, the selected effective basis improved the proxy-group
macro metrics over the bundled channel basis by 22.51% density RMSE, 8.32%
transmission RMSE, 19.40% median DE00, 19.50% mean DE00, and 19.84% p95 DE00.
All five metrics won in all 8 proxy groups (descriptive paired sign-test
`p = 0.00390625`).  The newest two proxy groups were disjoint from
training and improved on every metric.  Full-data channel cosine similarities
to the bundled C/M/Y prior were `0.99791`, `0.99597`, and `0.99921`; the
minimum fold values were `0.99791`, `0.99392`, and `0.99884`; peak ranges were
0 nm.  The candidate changes the supported 400–700 nm channel shapes by a mean
`0.00951 D` and maximum `0.02310 D`, preserves all three original peak
amplitudes exactly, leaves values outside the measured range unchanged, and
has a PCHIP-versus-linear maximum difference of `0.00154 D`.

## Candidates and rejections

The public-batch manifest lists exactly four local candidates:

| Candidate | Meaning | SHA-256 | Default status |
| --- | --- | --- | --- |
| `fujifilm_provia_100f_public_grouped_dmin_5e3c07c1_9c59ac4b_candidate` | Grouped same-stock GS0 effective transmission-output base; bundled channels unchanged | `f4c1ffcc8351ed1c56951714b83c043719deda43de939d652a4ba16fb2a9e7e8` | Experimental only |
| `fujifilm_velvia_100_public_grouped_dmin_fc36171d_1bf732d5_candidate` | Grouped same-stock GS0 effective transmission-output base; bundled channels unchanged | `f416ce168a47545409867cb506c15660d2b292c5c358e5c5857b469fc59978d3` | Corpus-specific exploratory; independent target-white stress fails promotion |
| `fujifilm_velvia_100_public_grouped_effective_basis_a025_fc36171d_7832b1c9_e34fe838_candidate` | Same grouped base plus gated effective rank-3 channel-shape delta | `5a1bb4ee8e23b37d5a1db815e6743c9353bdd50b4802807853bcd1b20d45de31` | Corpus-specific exploratory; independent basis gate fails |
| `kodak_endura_premier_public_grouped_effective_dmin_d9f2b144_810008af_candidate` | Black-backed 45/0 effective reflection-output base; channels unchanged | `e7d8c30341f6622cd91d42a982cf83648940d2f7224a3aeb6c7b32674d66fc94` | Experimental only |

The source-curve manifest lists one additional candidate:

| Candidate | Meaning | SHA-256 | Default status |
| --- | --- | --- | --- |
| `fujifilm_provia_100f_public_grouped_gs0_base_fuji_normalized_cmy_5e3c07c1_e28d54e7_bcbd0f5c_linear_candidate` | Training-group-only GS0 effective base plus AF3-036E manufacturer-published normalized Y/M/C shape with bundled peaks restored | `43ddafc7d5e18507e7ee68be4421c54443783241bb414373a08ac08a58a7bc4f` | Local evidence candidate only; no redistribution/default replacement |

Two apparently promising paths were deliberately rejected:

- **Provia 100F patch-only effective basis**: patch errors improved strongly,
  but the full-data magenta-channel cosine similarity was `0.989855`, below
  the configured `0.99` final-analysis gate.  This rejection does not apply to
  the separately sourced AF3-036E normalized-graph candidate above.
- **Ultra Endura base**: aggregate metrics improved, but one proxy group
  regressed by `7.0529%` on p95 DE00, beyond the 5% worst-group limit.  A stale
  exploratory file may exist locally, but it is not in the authoritative
  manifest and must not be used.
- **Velvia public base/effective basis promotion**: both files remain listed in
  the ColorReference run manifest because they pass that run's internal gate.
  The later independent MicroCalT24 stress rejects cross-source promotion, so
  they must not be treated as globally validated candidates.

Passing an originating manifest means “eligible for controlled local
comparison under that run's stated engineering policy.”  Later independent
evidence may demote it, as happened for Velvia.  It does not mean “true
chemical profile,” “manufacturer
approved,” “independently replicated,” “licensed for redistribution,” or
“authorized to replace the default.”

## Kodachrome 64 Figure 5 validation

Scarpace and Friederichs measured 330 physical Kodachrome 64 patches with a
Gamma Scientific microdensitometer/monochromator at 0.5 nm bandpass and 20 nm
sampling from 400--700 nm.  Their three characteristic vectors explained
99.94% of the measured variance, but the paper oriented the solution using
manufacturer curves and did not publish the raw 330-by-16 matrix.

[`profile-k64-figure5-digitization.py`](profile-k64-figure5-digitization.py)
digitizes the printed markers, records raster/axis uncertainty, and compares
only the jointly finite, non-extrapolated 440--680 nm range.  The source overlay
was visually inspected against the PDF.  Results are:

| Channel | Cosine similarity | Normalized-density RMSE | Peak, figure / bundled 20 nm sample |
| --- | ---: | ---: | ---: |
| Y | 0.9998219 | 0.010413 | 440 / 440 nm |
| M | 0.9998864 | 0.009700 | 540 / 540 nm |
| C | 0.9999516 | 0.007185 | 640 / 640 nm |

The combined normalized RMSE is `0.009204`.  This supports the current shape
but not its absolute amplitude, base-plus-fog, characteristic curves, emulsion
revision, or processing.  The result is validation-only and no K64 candidate
was emitted.  Script/report SHA-256 values are
`b7fc196c4b343c1b32e8904729876b66a093099dc7bdabad00b165dbe645f071`
and `c14d128a410d398ceebcdfc7ad6fff6aeec0433390b1ebe7ef2b0dd648be5cc1`.

## Reflection-model diagnostic

[`profile-reflection-williams-clapper-validation.py`](profile-reflection-williams-clapper-validation.py)
implements a black-backed 45/0 generalized Shore--Spoonhower/Williams--Clapper
forward model and an explicit no-clipping inverse:

```text
R = [T01(theta_i) T01(theta_o) / n^2]
    * rho_B * t^q / [1 - rho_B * I_n(t)]
```

The paper-white anchor is trained only from neutral, high-L* patches in the
non-held-out groups.  An inverse value outside the training-derived physical
domain becomes `NaN` and is counted; it is never clipped to make the fit look
valid.  At the primary `n = 1.53`, group-macro results are:

| Material | Current/additive D RMSE; R RMSE pp; median/p95 DE00 | Best WC effective result | Strict result |
| --- | --- | --- | --- |
| Ultra Endura, 18/16 groups | 0.18053; 7.9482; 4.6368/10.1845 | rank 4: 0.02202; 1.2544; 0.3922/1.5639 | Reject: 0.9525% held-out elements exceed the training white endpoint. |
| Endura Premier, 16/15 groups | 0.05227; 3.2472; 1.6285/3.2211 | rank 4: 0.01398; 0.9353; 0.4357/1.6571 | Reject: 0.8254% held-out elements exceed the training white endpoint. |
| Crystal Archive DP II, 29/26 groups | additive effective rank 3: 0.01902; 1.3701; 0.7220/1.9174 | WC rank 3/4 regress D, R, and p95 versus that baseline | Reject: 1.0119% out of domain and the material is not Type II. |

Rank 4 improves Ultra and Premier relative to WC rank 3, but this says only
that a three-dimensional effective subspace may be insufficient under this
model; it does not identify a fourth dye.  Varying refractive index from 1.45
to 1.60 changes some effective-rank reflection-RMSE results by as much as
16.8%, so `n` is not treated as an established stock parameter.  Including
the manufacturer-prior model raises the observed maximum to 17.9%.  The
transform itself passes
round-trip and quadrature checks, but every WC profile-emission flag remains
false.  Script/report SHA-256 values are
`049b8925921f4c6a914ce9fc3b6d904b3aa40f7c5b8b426581aea66959abe7f2`
and `c168b5b78f3586707c47e8ae4fd6bb207c9d10d5a2f0fdffa56902dd8cd33f62`.

## Paper and document audit

| Evidence | Physical/material support | What it can prove here | What it cannot prove |
| --- | --- | --- | --- |
| Avian Rochester MicroCalT24 | Commercial target explicitly built on Velvia 100; public nominal graphs for 18 chromatic and 6 neutral patches, 400--700 nm | Independent second-provider stress for bundled and candidate effective bases; rejects promotion of the ColorReference effective basis | No public numeric matrix, instrument/geometry/process record, patch legend, open derivative licence, analytical dyes, or documented GS0/base-plus-fog |
| Scarpace & Friederichs, 1978, Kodachrome 64 | 330 physical patches; 0.5 nm bandpass; samples every 20 nm, 400–700 nm; three characteristic vectors explain 99.94% | Physical-patch-constrained, manufacturer-prior-participating normalized-shape consistency check after graph digitization | A unique independent dye separation, current absolute amplitudes, exact emulsion revision, Dmin, H-D curves, or a raw 330×16 refit; [public PDF](https://www.asprs.org/wp-content/uploads/pers/1978journal/oct/1978_oct_1293-1301.pdf) |
| Cheng et al., Velvia 100 | 140 ColorChecker SG patches, standard E-6, PR730/FP730 microscope setup | Independent same-stock physical validation that microscopic Velvia transmission spectra are measurable | No reusable numeric spectra or declared wavelength grid; [DOI](https://doi.org/10.1117/12.2007215) |
| Wang et al., geometry-constrained NMF, 2014 | Dataset B is exact-stock Kodak Gold 200: 216 developed screen-exposed colours with measured transmission spectra; Dataset A is an unidentified 1000-patch negative | Exact-stock physical validation for Gold 200 and direct evidence that ordinary NMF produces initialization-dependent bases | No released matrices, instrument/geometry/processing record, or three reusable Gold 200 C/M/Y curves; validation-only |
| Earlier MIT calibration paper | Positive and negative film data, 1000 RGB laser exposures, 101 wavelengths | Supports rank-3/NNMF modelling and exposure-to-density stage separation | Stock names and raw matrices are absent; [public manuscript](https://math.mit.edu/~edelman/homepage/papers/writeupc.pdf) |
| Plutino et al., 2024 | Exact-stock physical Vision3 500T samples measured by HSI from 400--900 nm at 1.2 nm resolution | Independent physical-sample validation and a documented Specim/Hamamatsu/tungsten setup | Authors report difficult dye separation; no raw cube, reusable numeric curves, controlled C/M/Y ladder, or complete processing record; validation-only |
| Silva et al., 2022 | Physical Ektachrome 160T EPT and Provia 400X RXP dyes separated by TLC/HPLC-DAD; RXP shows two magenta peaks | Demonstrates chemical multiplicity within one runtime colour channel and gives method evidence for isolated-dye work | Neither stock is current E100/Provia 100F; solution spectra lack film-layer concentration/path-length scale and cannot refit current profiles; method-only |
| Endura Premier technology paper | Same product family and documents a new cyan emulsion/dye | Proves Premier cannot silently inherit Ultra Endura cyan semantics | Does not publish a patch matrix or isolated spectral dyes; [primary paper](https://library.imaging.org/admin/apis/public/api/ist/website/downloadArticle/tdpf/4/1/art00006) |

Local PDF identities used in this audit:

| File | SHA-256 |
| --- | --- |
| `1978_oct_1293-1301.pdf` | `2423a00887fc60f8ea45b052a058e7af7f3467436506be849e15c0038388a8ca` |
| `Cheng2013_Proc-SPIE_v8676-23.pdf` | `563b94e248531456636c7df5072b6f8771f25bb9417efad029f5c1dec030b820` |
| `Color photographic paper dye density estimate using wavelength-dependent optical properties.pdf` | `5d002f59f13702fe4c0bac43ed47bed17ea5038db4ecd78f0ef84b4950768e32` |
| `heritage-05-00203.pdf` | `1e1f933491f1fa45f03aa9c47499a0fe9f7457d0530cd42715f8c4bc1e0bc8ce` |
| `PhotoFilm_Publication_Plutino.pdf` | `31b3c89925f95833d168d81d43d33aff8d7fbe79573f6d39badaef4d3cc9c128` |
| `scgecolorwithtitle2014titleupdated3.pdf` | `c3a52dcdaf8029c03af8d290449e000533722931786dab7cf818f9a98cfa0bea` |
| `tmp/pdfs/writeupc.pdf` | `afa7ead4fc109f019bc64ad78fd44528dc215e774e8356dd574b8c164c705eaa` |

## Field-by-field consequence for bundled profiles

The provenance contract is documented in
[`../profile-provenance.md`](../profile-provenance.md).  This evidence pass
changes the confidence classification of candidates, not the bundled arrays.

| Field | Current evidence interpretation | Action now |
| --- | --- | --- |
| `wavelengths`, `log_exposure` | Generated coordinate grids | Keep labelled generated |
| `log_sensitivity` | Usually digitized/resampled manufacturer graph or inherited/generic donor; not raw observations | No numeric change from patch spectra; later compare against axis-calibrated official graph digitizations |
| `density_curves` | Manufacturer graph may be an input, but final arrays include normalization, unmixing, neutral refinement, or refit | Keep source-derived/optimized labels; public patches do not validate exposure response |
| `channel_density` | Manufacturer graph, generic donor, related profile, or reconstruction depending on stock | Retain bundled Velvia after the independent MicroCal gate; demote its effective basis to corpus-specific exploration; keep the separate Provia manufacturer-normalized-shape candidate local; K64 is validation-only; preserve exact source/effective/analytical distinctions |
| `base_density` | Often internally reconstructed rather than a measured spectrum | Provia appears in both base-only and combined-source candidates; demote the Velvia grouped base after the independent target-white stress; Premier remains an effective 45/0 output base, and no Williams--Clapper base is emitted |
| `midscale_neutral_density` | Metameric-neutral/runtime reconstruction | No evidence upgrade |
| `density_curves_layers` | Parametric decomposition generated from other curves | Keep reconstructed/generated |
| `density_curves_model` | Runtime parametric refit | Keep optimized/generated |
| Hanatos 2025 adaptation fields | Per-stock runtime fit, not a film measurement | Keep optimized/generated |
| `ProfileInfo` categories | Curated runtime/product semantics, not part of this numerical measurement model | Do not call measured; a future schema can give these non-array fields their own provenance class |

Important existing donor boundaries remain in force: the generic `Film A` CMY
prior used by several negative stocks, push-profile inheritance from Portra 800,
Vision3 50D donation to Verita 200D, Supra/Portra Endura donor relationships,
and Crystal Archive Type II's characteristic-curve donor must remain visible.

## ISO status and purchase priority

No legal free full text was found for the minimum density-measurement standards.
The official catalogue pages establish scope and current status but are not a
substitute for the normative clauses:

- [ISO 5-2:2009](https://www.iso.org/standard/52914.html): geometric conditions
  for transmission density; current and confirmed in 2025.
- [ISO 5-3:2009](https://www.iso.org/standard/52915.html): spectral conditions;
  current and confirmed in 2025.
- [ISO 5-4:2009](https://www.iso.org/standard/52916.html): geometric conditions
  for reflection density, including backing/polarization/accuracy concerns;
  current and confirmed in 2025.
- [ISO 13655:2009](https://www.iso.org/standard/39877.html): withdrawn, but the
  archive metadata explicitly cites its Annex I, so this edition is needed to
  audit that historical interpolation claim.
- [ISO 13655:2017](https://www.iso.org/standard/65430.html): current replacement
  and needed for present-day comparison.
- [ISO 12641-1:2025](https://www.iso.org/standard/84133.html) and
  [ISO 12641-2:2019](https://www.iso.org/standard/68575.html): scanner
  characterization targets; useful context, but a target patch does not reveal
  known individual dye amounts.
- [ISO 17972-2:2016](https://www.iso.org/standard/61501.html): CxF/X-4 exchange
  format context.

If standards are purchased, the minimum order is ISO 5-2 and 5-3 for film.  For
paper and for auditing these archives, add ISO 5-4 plus both ISO 13655:2009 and
ISO 13655:2017.

## Licence boundary

Public downloadability does not itself establish an open derivative licence.
No explicit open permission to redistribute raw spectra or derived tables was
found in the index, archive, and explanatory materials reviewed in this pass;
redistribution permission therefore remains unconfirmed.  Consequently:

- raw archives remain in `tmp/` and are not package data;
- candidate profiles remain untracked local artifacts;
- reports record hashes, method, counts, and aggregate metrics rather than
  embedding the source spectral matrices;
- resolving permission is necessary but not sufficient for any bundled
  promotion; the physical-evidence, held-out, and runtime gates must also pass,
  and default replacement remains separately unauthorized.

## Reproduction

From the repository root, after the public archive cache and cited PDFs have
been populated:

```bash
MPLCONFIGDIR=/tmp/spektrafilm-mpl \
  .venv/bin/python docs/reports/profile-source-curve-digitization.py \
  --pdf-dir tmp/pdfs/profile-curves \
  --output-dir tmp/profile-source-curves/fuji

MPLCONFIGDIR=/tmp/spektrafilm-mpl \
  .venv/bin/python docs/reports/profile-manufacturer-curve-validation.py \
  --cache-dir tmp/profile-public-batches \
  --pdf-dir tmp/pdfs/profile-curves \
  --output tmp/profile-source-curves/manufacturer_curve_batch_validation.json \
  --emit-candidate \
  --candidate-output-dir tmp/profile-source-curves/candidates \
  --candidate-manifest tmp/profile-source-curves/CURRENT_SOURCE_CURVE_CANDIDATES.json

MPLCONFIGDIR=/tmp/spektrafilm-mpl \
  .venv/bin/python docs/reports/profile-k64-figure5-digitization.py

MPLCONFIGDIR=/tmp/spektrafilm-mpl \
  .venv/bin/python docs/reports/profile-velvia-microcal-validation.py \
  --source-dir tmp/profile-velvia-microcal/sources \
  --output-dir tmp/profile-velvia-microcal/results \
  --download-missing

MPLCONFIGDIR=/tmp/spektrafilm-mpl \
  .venv/bin/python docs/reports/profile-public-batch-validation.py \
  --cache-dir tmp/profile-public-batches \
  --candidate-output-dir tmp/profile-public-batch-candidates \
  --runtime-validation \
  --effective-basis-validation \
  --emit-effective-basis-candidates \
  --report-output tmp/profile-public-batch-report-grouped.json

MPLCONFIGDIR=/tmp/spektrafilm-mpl \
  .venv/bin/python docs/reports/profile-reflection-williams-clapper-validation.py \
  --cache-dir tmp/profile-public-batches \
  --output-dir tmp/profile-reflection-wc/final \
  --refractive-indices 1.53 1.45 1.60
```

Add `--download-public-batches` only when the public cache is absent.  Use
`--refresh` only for an explicit source-refresh audit.

## Verification and immutable-default proof

- `pypdf~=6.13` is now a declared development dependency; the lock resolves
  6.14.2.  The candidate `uv.lock` SHA in the alignment contract was refreshed
  to `965ab21c56f5ea89107b4bdedb0135309b6c0607fb33f6692c7d10c67f110f3a`.
- All five analysis scripts pass `py_compile`; `git diff --check` passes.
- Targeted profile/provenance/candidate/reflection tests: `67 passed`.
- Full non-GUI suite with the declared Apple GPU extra restored:
  `1704 passed, 20 skipped, 4 xfailed`.
- Every current `data` object in all 28 bundled profile JSON files is byte-
  independently parsed and equal to its counterpart in `HEAD`; the difference
  list is empty.
- The authoritative Provia source candidate loads through `profile_from_dict`,
  its file hash matches the manifest, and its changed `data` keys are exactly
  `base_density` and `channel_density`.
- The candidate runtime report confirms the exposure-to-density mapping is
  exactly unchanged and the channel values outside 400--700 nm are exactly
  unchanged.  The base is separately disclosed as changing on 385--715 nm.
- The Gold 200 and Vision3 500T validation-only references occur in
  `source_references`/notes and in no field's `sources` array.

## Next closed-evidence steps

1. Digitize exact-stock characteristic and sensitivity graphs with the same
   calibrated-axis, repeat-extraction, edition-envelope, and held-out-runtime
   discipline before changing `log_sensitivity` or `density_curves`.  A graph
   of relative sensitivity cannot supply absolute exposure calibration by
   itself.
2. Keep the Provia combined candidate local and compare it against the bundled
   profile on representative scene spectra and controlled runtime routes.  Do
   not reinterpret the unchanged exposure-to-density mapping as validated by
   the patch reconstruction result.
3. Keep both Velvia public candidates demoted.  Re-open them only if a second
   licensed numeric matrix or a stronger independent graph extraction clears
   the external-source gate; do not tune them against MicroCal after seeing
   this result and then call the same graph an independent holdout.
4. For paper, improve the training-only paper-white uncertainty envelope and
   require zero held-out inverse-domain failures across refractive-index and
   anchor-policy sensitivity.  Even then, reflection-only fitting may emit at
   most an effective output model, not analytical dye curves.
5. Treat R240103 only as a new DP II experimental profile.  Never use it to
   relabel or refit Crystal Archive Type II.
6. Use the Gold 200 GNMF paper only as an exact-stock validation and
   method/non-uniqueness constraint unless
   a released numeric matrix or independently digitizable same-stock curve is
   found.
7. Keep searching official archives and research-data repositories for an
   independently licensed same-stock numeric matrix.  Re-run the entire gate
   if a new source appears; absence in this search is not proof of absence.
8. Resolve redistribution permission before packaging any source-derived
   table or candidate.  Technical validity does not imply a licence.
9. Extend provenance to non-array `ProfileInfo` categories separately, without
   conflating curated product metadata with instrument measurements.

Until those steps produce stronger evidence, the correct state is: **local
candidates exist, bundled defaults remain unchanged, and the provenance labels
remain conservative**.
