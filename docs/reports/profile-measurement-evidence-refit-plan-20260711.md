# Profile Measurement Evidence And Refit Plan

Date: 2026-07-11

## Goal

Find independent, stock-specific physical-film measurements that can improve bundled profiles, and use them only when the evidence supports a reproducible numerical refit. Where stock-specific evidence is insufficient, derive a measurement protocol from the applicable ISO 5 density standards and identify any standards that must be purchased.

## Evidence Tiers

### Tier A - Refit-Capable Measurement Evidence

All of the following are required:

- The physical material is identified as the same stock, with revision/emulsion/batch information where available.
- Exposure, processing chemistry, time, temperature, sample preparation, instrument, spectral range, sampling interval, and measurement geometry are documented.
- Machine-readable measurements or a graph with calibrated axes and adequate resolution is legally available.
- The observations are sufficient to constrain the claimed field. Neutral Min/Mid curves alone cannot identify separate CMY dye bases.
- The source can be archived by stable URL/DOI plus checksum and page/table/figure coordinates.

Tier A evidence may support a reproducible candidate refit and, after validation, replacement of a bundled field.

### Tier B - Stock-Specific But Incomplete Evidence

The source measures the named physical stock but lacks raw numeric data, complete process metadata, sufficient independent color/exposure samples, or a stable high-resolution graph. Tier B may support validation, bounds, or a candidate profile variant, but not silent replacement of a default field.

### Tier C - Method Or Non-Matching Material

The source explains dye-density separation, sensitometry, or instrument geometry but uses a different material or only republishes manufacturer curves. Tier C informs the measurement/refit method and provenance notes; it does not justify changing a stock profile.

## Production Replacement Gates

1. Preserve the current profile arrays as the numerical baseline.
2. Record source identity, access date, checksum, sample/process metadata, extraction procedure, and field-level provenance.
3. Keep source measurements separate from fitted runtime arrays.
4. Rebuild the candidate deterministically from retained extraction data and code.
5. Validate source-curve reconstruction error, held-out spectral-density error, colorimetric error, monotonicity, and exposure-ramp behavior.
6. Compare against the current profile and document the visible/runtime impact.
7. Do not replace the default when the new evidence is underdetermined or performs worse against available stock-specific observations.

## ISO Fallback

If no Tier A evidence is available, audit ISO 5-1, ISO 5-2, ISO 5-3, and ISO 5-4 for density terminology, transmission geometry, spectral conditions, and reflection geometry. Prefer current official editions or legally available identical national adoptions. Record which full texts are available and which must be purchased before a physical measurement campaign is specified as normative.

## Initial Stock Priority

1. Kodachrome 64: independent spectral analytical dye-density literature exists; determine whether usable numerical curves can be extracted and whether the measured emulsion matches the bundled source era.
2. Kodak Gold 200: published physical-film color-patch measurement claims exist; locate the actual paper, figures, and data rather than relying on abstract-only or secondary uploads.
3. Fujifilm Velvia 100: independent calibrated transmission targets exist; determine whether numerical spectra can be obtained and whether they constrain validation only or CMY/H-D fields.
4. Portra 400: flagship generic-CMY profile; search for independent multi-patch spectral transmission measurements before planning a new physical measurement set.

## Technical Summary

No reviewed source currently passes the Tier A replacement gate. The bundled
numeric arrays therefore remain unchanged.

Three results are nevertheless strong enough to narrow the work materially:

1. The F240222 Provia 100F and N230513 Velvia 100 batches are real, same-product
   transmission measurements. Five-fold held-out reconstruction shows that
   their measured density variation is stably three-dimensional and closely
   aligned with the bundled CMY shapes. This validates the broad channel shapes,
   but it does not identify unique analytical dyes.
2. The largest mismatch for both reversal profiles is the bundled, nearly
   constant `base_density`. The measured `GS0` Dmin patches differ from the
   bundled base by 0.225 D for Provia and 0.129 D for Velvia over the
   profile-supported bands. The [ColorAid target index](http://www.colorreference.de/targets/index.html)
   explicitly identifies `GS0/GS23` as `dmin/dmax`. This supports a Dmin-derived
   candidate, but ISO Dmin is not necessarily neutral and is not a bare-support
   or clear-base claim.
3. The 1978 Kodachrome 64 physical-film Figure 5 agrees with the bundled,
   peak-normalized Y/M/C shapes within the figure-digitization uncertainty.
   This is strong independent validation of shape, not a basis for changing the
   default profile or upgrading it to instrument-measured provenance.

The free rank-3 fits below are deliberately called **effective generators**.
They are not claimed to be physical C, M, and Y dye spectra. They remain
permutation-, scale-, and mixing-ambiguous without pure-dye or equivalent
identifying constraints.

## Reviewed Evidence Inventory

### Measured Target Data

| Evidence | Material identity | Measurement content | Profile use | Classification |
| --- | --- | --- | --- | --- |
| `F240222` | Fujichrome Provia 100F, RDP III | 288 batch-average transmission spectra, 380-780 nm at 10 nm | Same-product spectral validation and effective-basis fitting | Tier B, candidate-basis |
| `N230513` | Fujichrome Velvia 100, RVP 100 | 288 batch-average transmission spectra, 380-780 nm at 10 nm | Same-product spectral validation and effective-basis fitting | Tier B, candidate-basis |
| `E240220` | Kodak Ektachrome product family only | 288 batch-average transmission spectra, 380-780 nm at 10 nm | Family-level validation; not proven E100 | Tier B/C boundary, validation-only |
| `R110714` | Kodak Professional Ultra Endura | 288 batch-average reflection spectra, 400-700 nm at 10 nm | Same-product output validation | Tier B, validation-only |
| `R200204` | Kodak Professional Endura Premier | 288 batch-average reflection spectra, 400-700 nm at 10 nm | Same-product output validation | Tier B, validation-only |
| `R240103` | Fujicolor Crystal Archive DP II | 288 batch-average reflection spectra, 400-700 nm at 10 nm | Related family only; not Paper Type II | Tier C, validation-only |

The transmission packs identify the published spectra as batch averages derived
from 3 nm measurements and interpolated to 10 nm under ISO 13655:2009 Annex I.
They do not identify the instrument, exact transmission geometry, aperture,
bandpass, dynamic range, target count, exposure setup, processing laboratory,
chemistry, time, temperature, emulsion number, or raw 3 nm observations.

The reflection packs use final 45/0, black-backed reflection values and Status T
density. Their corresponding bundled profiles declare Status A. Reflection
density is not Beer-Lambert transmission density, and the black/white backing
differences reach about 2-3 CIE76 units on individual patches. These data cannot
be inserted directly into `channel_density` or `base_density`.

The external ColorAid files contain no open-data or redistribution license.
They may be audited locally, but neither the source spectra nor fitted numeric
derivatives should be committed until the applicable license or written
permission is confirmed.

### Source Traceability

All local files below were inspected on 2026-07-11. The hashes identify the
exact copies used for this audit; they are not a statement of redistribution
permission.

| Source file or batch member | SHA-256 |
| --- | --- |
| `F240222/EXTRAS/F240222.xls` | `56a38376f202639b468a4320db016aa043ab786828b78997b1d6f7c7fe1de3f8` |
| `N230513/EXTRAS/N230513.xls` | `125806d32cb39b0a40cad252dc2bacdba9389bdbc86879cd2d4586c71614d16b` |
| `E240220/EXTRAS/E240220.xls` | `b381cf1f30acaa375bb8c985658561fbd0f0a488922afa31c4e26016a232ee19` |
| `R110714/Extras/R110714.hist` | `79430cbd174fb13ce91bc23de284956e1a6f6236998f0e11f288dd7b060d33f4` |
| `R200204/Extras/R200204.hist` | `b5631c241f2bc9b1edfc41beda80ab3dcb25c8be9e72525bcba9de8b03368562` |
| `R240103/Extras/R240103.hist` | `0948c0664fc2bc29db9ec99091094d6340fdeb805cac3986a8f0aeafd5ad4a6d` |
| `1978_oct_1293-1301.pdf` | `2423a00887fc60f8ea45b052a058e7af7f3467436506be849e15c0038388a8ca` |
| `Cheng2013_Proc-SPIE_v8676-23.pdf` | `563b94e248531456636c7df5072b6f8771f25bb9417efad029f5c1dec030b820` |
| `Color photographic paper dye density estimate using wavelength-dependent optical properties.pdf` | `5d002f59f13702fe4c0bac43ed47bed17ea5038db4ecd78f0ef84b4950768e32` |
| `heritage-05-00203.pdf` | `1e1f933491f1fa45f03aa9c47499a0fe9f7457d0530cd42715f8c4bc1e0bc8ce` |
| `PhotoFilm_Publication_Plutino.pdf` | `31b3c89925f95833d168d81d43d33aff8d7fbe79573f6d39badaef4d3cc9c128` |
| `scgecolorwithtitle2014titleupdated3.pdf` | `c3a52dcdaf8029c03af8d290449e000533722931786dab7cf818f9a98cfa0bea` |

### Papers And Proceedings

| Source | Physical material | Reusable evidence | Decision |
| --- | --- | --- | --- |
| Scarpace and Friederichs, *A Method of Determining Spectral Analytical Dye Densities*, 1978 | 330 Kodachrome 64 patches; 425 Aerochrome patches | Digitizable normalized K64 Y/M/C Figure 5; PCA and reconstruction statistics | Strong Tier B validation; no default replacement |
| Cheng et al., Proc. SPIE 8676, 2013 | Velvia 100, 140 ColorChecker SG patches, standard E-6 at Dwayne's Photo | Instrument and process description, but no reusable numeric spectra | Same-stock validation-only |
| Glasgow, McElwain, and Pringle, *Color Photographic Paper Dye Density Estimate Using Wavelength Dependent Optical Properties*, 1996 | Unnamed 1995 film paper and Kodak Q-60 reflection standard | Reflection-to-transmission model and low-density polynomial | Method-only Tier C |
| Silva et al., *Contributions to the Characterization of Chromogenic Dyes in Color Slides*, 2022 | Provia 400X, RXP, emulsion 104, expired 2009 | Extracted solution-state peaks: C 651, M 546/551, Y 451 nm | Candidate shape only for a future RXP profile; not a Provia 100F donor |
| Plutino et al., *Limitations and Potentials of Hyperspectral Imaging Technique Applied to Cinematographic and Photographic Film Materials*, 2024 | Unknown-stock IT8, Kodak 2254, two Vision3 500T strips | Raster figures only; no cubes, point spectra, numeric table, or calibration data | Vision3 500T negative evidence for blind separation; no refit |
| Wang et al., *A geometry-based NMF & regression learning as a two-stage characterization model for photographic color film*, 2014 manuscript | Unknown film dataset A; under-documented Kodak Gold 200 dataset B | Method equations; no Gold spectra or Gold CMY basis | Gold 200 validation-only; no refit |

The Wang document is an internally inconsistent manuscript rather than a clean
final publication: its DOI is blank, page headers alternate 2012 and 2014, key
algorithm detail points to an "in preparation" reference, and the Gold 200 NMF
solution was selected to match a manufacturer neutral curve. Figure 6 does not
contain three Gold 200 analytical dye curves.

The Plutino Vision3 500T result is specifically cautionary. The authors report
that separation of individual dye spectra was difficult because of dye mixing.
PCA components and N-FINDR endmembers in that experiment are observed effective
directions or extreme pixels, not measured unit-concentration dyes.

## Operational Definition Of A CMY Basis

For a transmissive processed-film patch `p`, use base-10 spectral density:

```text
D_p(lambda) = -log10(T_p(lambda))
            = D_0(lambda)
            + a_p,C W_C(lambda)
            + a_p,M W_M(lambda)
            + a_p,Y W_Y(lambda)
            + error_p(lambda)
```

`D_0` is the independently measured support, mask, fog, and unavoidable minimum
density under the stated process. `W_C`, `W_M`, and `W_Y` are non-negative
analytical dye-density functions under an explicit normalization. The
coefficients `a_p,*` are non-negative dye amounts in that normalization.

A reproducible Spektrafilm CMY definition must therefore specify all of the
following:

- base-10 rather than unspecified logarithms;
- the sample stock, product code, emulsion/batch, storage, exposure, and process;
- spectral transmission geometry, instrument, calibration, aperture, bandpass,
  wavelength grid, dynamic range, and noise-floor handling;
- an independently measured `D_0`, not an unconstrained intercept silently
  absorbed by the three components;
- channel ordering and normalization, such as unit peak plus peak-region anchors;
- the identifying evidence: pure or highly selective separations, known dye
  amounts, manufacturer analytical curves, or another explicit prior;
- extraction uncertainty, repeated initializations, component stability, and
  held-out reconstruction error.

Rank-3 PCA or NMF by itself proves only a low-dimensional effective subspace.
For any invertible matrix `A`, related factorizations can describe the same data
subject to the applicable non-negativity constraints. A component becomes a
physical C, M, or Y curve only when additional evidence fixes that ambiguity.

For reflection papers, do not substitute `-log10(R)` into this equation. The
paper coating, support, scattering, Fresnel losses, and repeated internal
reflections require a validated reflection-to-transmission or radiative-transfer
model first. The Glasgow low-density polynomial is explicitly limited to about
1.5 reflection density, while more than 100 patches in each reviewed paper batch
exceed that limit in at least one band.

## Held-Out Same-Stock Reconstruction

The reproducible analysis is in
[`profile-measurement-basis-evaluation.py`](profile-measurement-basis-evaluation.py).
It reads the external TSV files, makes no writes, and prints a JSON result:

```bash
.venv/bin/python docs/reports/profile-measurement-basis-evaluation.py
```

The primary comparison uses five deterministic folds and excludes individual
measurements below `T = 0.001` (`D > 3`) from coefficient fitting and density
RMSE because the instrument noise floor is unknown. Each held-out patch still
gets its own non-negative coefficients. This tests whether a spectral basis can
reconstruct an unseen patch; it does not predict dye amounts from exposure.

Three models are compared:

- **Bundled basis and base**: the current `channel_density` and `base_density`.
- **Bundled basis plus training lower envelope**: the current channel shapes,
  with a per-band minimum estimated from training patches. This isolates channel
  shape from the current base but is not a physical-base claim.
- **Free effective NMF plus training lower envelope**: a non-negative rank-3
  benchmark, three initializations per fold, peak normalization, and a one-bin
  `[1, 2, 1] / 4` smoother.

### Primary Metrics At `T >= 0.001`

| Stock and model | Density RMSE (D) | Transmittance RMSE (percentage points) | Median Delta E 2000 | 95th percentile Delta E 2000 |
| --- | ---: | ---: | ---: | ---: |
| Provia 100F, bundled basis and base | 0.2126 | 6.936 | 2.948 | 9.666 |
| Provia 100F, bundled basis plus lower envelope | 0.0509 | 1.456 | 1.416 | 2.908 |
| Provia 100F, free effective NMF plus lower envelope | 0.0190 | 0.999 | 0.828 | 2.854 |
| Velvia 100, bundled basis and base | 0.1058 | 4.981 | 3.225 | 6.332 |
| Velvia 100, bundled basis plus lower envelope | 0.0296 | 0.617 | 0.695 | 2.712 |
| Velvia 100, free effective NMF plus lower envelope | 0.0200 | 0.943 | 0.469 | 1.531 |

The colorimetric comparison integrates both measured and reconstructed spectra
over 400-700 nm under D50 and the CIE 1931 2-degree observer. It is a truncated
common-band comparison, not a claim about a complete scanner transform. Delta E
uses the full reconstructed common-band spectrum, including points below the
density-fit transmittance floor; the floor applies only to NNLS fitting and the
reported density/transmittance RMSE masks.

The centered density PCA first-three variance fractions are 0.99962 for Provia
and 0.99924 for Velvia over their profile-supported bands. These descriptive PCA
figures use all published density values, including the uncharacterized
low-transmittance region, so they are dimensionality evidence rather than a
precision claim. At the primary noise floor, the free effective bases have mean
cosine similarity to the bundled `C/M/Y` shapes of:

| Stock | C | M | Y | Stable peak wavelengths across all five folds |
| --- | ---: | ---: | ---: | --- |
| Provia 100F | 0.9971 | 0.9975 | 0.9972 | 650 / 540 / 450 nm |
| Velvia 100 | 0.9980 | 0.9940 | 0.9995 | 660 / 550 / 440 nm |

Cross-fold cosine similarity to each candidate's fold mean is above 0.9997 for
all six channels. This strongly validates the existing broad CMY shapes. It does
not make the fitted components unique physical dyes.

### Robustness And Failure Modes

- Repeating at `T >= 0.01` and `T >= 0.0001` preserves the main ordering and
  component stability. Provia's fitted C peak moves from 660 nm at the strictest
  floor to 650 nm at the two lower floors; all other listed peaks remain fixed.
- On Velvia, free NMF improves density RMSE and Delta E but worsens absolute
  transmittance RMSE relative to the bundled shapes plus lower envelope. There
  is no metric-independent case for replacing the current basis.
- The lower envelope is almost the measured `GS0` spectrum: RMSE is 0.0019 D for
  Provia and 0.0027 D for Velvia. This makes `GS0` a useful minimum-density
  candidate. The target vendor explicitly calls it Dmin, while the ISO
  definition distinguishes product Dmin from minimum neutral density and from a
  bare clear-base claim.
- The data are batch averages, so the 288 rows are color patches, not 288
  independent film batches. Cross-validation measures patch reconstruction, not
  manufacturing variability.
- ColorAid does not provide per-patch spectral standard deviations. Very low
  transmittance is therefore thresholded, not statistically weighted by a known
  instrument uncertainty model.

## Measured GS0 Dmin Profile Candidates

The analysis script can now generate two local, non-default profile copies:

```bash
.venv/bin/python docs/reports/profile-measurement-basis-evaluation.py \
  --candidate-output-dir tmp/profile-dmin-candidates \
  --runtime-validation
```

Only the numeric `data.base_density` field changes. The bundled
`channel_density`, sensitivity, characteristic curves, layer model, and runtime
optimization fields are copied unchanged; the candidate name, provenance, data
source, date, and redistribution warning are updated deliberately. GS0 is
excluded from evaluation because it supplies the candidate base; the reported
metrics use the other 287 patches.

At `T >= 0.001`:

| Stock and base | Density RMSE (D) | Transmittance RMSE (percentage points) | Median Delta E 2000 | 95th percentile Delta E 2000 |
| --- | ---: | ---: | ---: | ---: |
| Provia 100F, bundled base | 0.2126 | 6.882 | 2.942 | 9.612 |
| Provia 100F, measured GS0 Dmin | 0.0508 | 1.448 | 1.418 | 2.917 |
| Velvia 100, bundled base | 0.1058 | 4.944 | 3.223 | 6.324 |
| Velvia 100, measured GS0 Dmin | 0.0296 | 0.619 | 0.702 | 2.711 |

Relative to the bundled base, the candidate reduces all-patch density RMSE by
76.1% for Provia and 72.1% for Velvia. It reduces transmittance RMSE by 79.0%
and 87.5%, respectively. On `GS1-GS23`, density RMSE falls by 72.6% for Provia
and 67.6% for Velvia; transmittance RMSE falls by 84.2% and 87.8%.

The external 10 nm Dmin spectrum is resampled to the 5 nm profile grid with
shape-preserving PCHIP only where all three bundled CMY curves are finite:

| Candidate | Replaced profile points | Measured-support range | PCHIP vs linear mean / maximum absolute difference |
| --- | ---: | --- | ---: |
| Provia 100F | 67 of 81 | 385-715 nm | 0.00154 / 0.03765 D |
| Velvia 100 | 62 of 81 | 400-705 nm | 0.00117 / 0.04040 D |

Outside the shared finite CMY support, the current base is retained and labeled
as inherited. The relatively large worst-case PCHIP/linear difference occurs in
the steep spectral edge, so the runtime check below carries both interpolation
choices through the full film-scan route. Candidate provenance is
`instrument-measurement` origin plus
`reconstructed` final status; it remains `no-raw-instrument-data` because the
vendor's raw 3 nm observations and full instrument chain are not retained.

The candidate filename has a `_gs0_dmin_candidate` suffix, while
`info.stock` deliberately remains the real source stock. This preserves the
same stock-specific coupler and rendering parameters as the bundled profile;
changing `info.stock` would make the runtime comparison invalid. The candidate
name and metadata identify it as experimental and non-default.

### Deterministic Runtime Check

The optional runtime validation runs the bundled profile, the PCHIP candidate,
and a linear-interpolation sensitivity candidate through the positive-film
light-table route. It uses 96 fixed linear ProPhoto RGB patches, including a
32-step neutral ramp, with auto exposure, spatial effects, stochastic effects,
LUT approximation, and output gamut compression disabled. Full RouteMaster
sidecars are retained for validation.

All three versions for both stocks produce finite route RGB, luminance, CMY,
and SDR arrays. Every neutral ramp is non-decreasing, the stock-specific
coupler signatures are identical, and repeating the PCHIP run is numerically
identical (`max absolute difference = 0`).

| Comparison | Mean / max route RGB absolute difference | Median / p95 clipped-linear-sRGB Delta E 2000 | Mean / max SDR absolute difference |
| --- | ---: | ---: | ---: |
| Provia: bundled vs PCHIP Dmin | 0.00872 / 0.05092 | 1.040 / 2.625 | 0.00645 / 0.02579 |
| Provia: PCHIP vs linear | 0.000119 / 0.000837 | 0.0186 / 0.0616 | 0.000095 / 0.000508 |
| Velvia: bundled vs PCHIP Dmin | 0.02088 / 0.09401 | 2.137 / 5.140 | 0.01483 / 0.05122 |
| Velvia: PCHIP vs linear | 0.000155 / 0.000857 | 0.0211 / 0.0591 | 0.000121 / 0.000709 |

The candidate therefore has a material runtime effect, especially for Velvia,
while the choice between PCHIP and linear interpolation is much smaller on this
test set. This closes the immediate runtime-safety and interpolation-sensitivity
gate. It is not an independent color-accuracy validation and does not resolve
the missing instrument chain, batch applicability, or derivative-data license.

## Kodachrome 64 Independent Shape Check

Scarpace and Friederichs measured 330 physical Kodachrome 64 patches at 20 nm
from 400-700 nm with a Gamma Scientific microdensitometer/monochromator and a
0.5 nm bandpass. Three characteristic vectors explain 99.94% of the variance;
the paper reports an average reconstruction standard deviation of about 0.089 D.

The paper then rotates the three-dimensional variation subspace toward Kodak
representative curves, so Figure 5 is physical-film-derived but not a unique
blind separation. Comparing the manually digitized Figure 5 with the bundled
profile only on the profile's finite common interval, 440-680 nm, gives:

| Channel | Correlation | Normalized RMSE | Figure peak | Profile peak |
| --- | ---: | ---: | ---: | ---: |
| Y | 0.99984 | 0.00797 | 440 nm | 440 nm |
| M | 0.99992 | 0.00584 | 540 nm | 540 nm |
| C | 0.99997 | 0.00582 | 640 nm | 640 nm |

Overall normalized RMSE is 0.00662, below the estimated typical figure-reading
uncertainty of about 0.015. This is strong validation of the bundled normalized
shape. It does not validate absolute scale, `base_density`, characteristic
curves, emulsion revision, or processing behavior, and therefore does not
justify a numeric profile change.

## Field-Level Decisions

| Profile or group | `channel_density` | `base_density` / minimum | `density_curves` / `log_sensitivity` | Current action |
| --- | --- | --- | --- | --- |
| Provia 100F | Broad shape independently supported; free fit is still an effective basis | Vendor identifies GS0 as Dmin; local candidate strongly improves held-out patches and passes deterministic runtime QA | No calibrated exposure axis | Keep default; seek metadata/license and independent validation |
| Velvia 100 | Broad shape independently supported; no metric-independent channel replacement gain | Vendor identifies GS0 as Dmin; local candidate strongly improves held-out patches and passes deterministic runtime QA | Cheng paper lacks reusable spectra/exposure table | Keep default; seek metadata/license and independent validation |
| Kodachrome 64 | Independent 1978 normalized curves agree within digitization uncertainty | Not independently validated | No matching raw H-D observations | Keep arrays; validation-only |
| Gold 200 | No reusable Gold CMY basis in reviewed manuscript | No reusable measurement | No documented experiment data | Keep arrays |
| Vision3 500T | HSI paper reports unsuccessful individual-dye separation | Not measured | No exposure series | Keep arrays; record negative evidence |
| Ultra Endura / Endura Premier | Reflection patches do not identify analytical CMY | Reflection model and density-status mismatch block use | No calibrated exposure series | Keep arrays; output validation only |
| Crystal Archive Type II | Downloaded batch is DP II, not Type II | Product mismatch | Product mismatch | Do not use as same-stock evidence |

No final bundled array should be relabeled `instrument-measured`. The current
field-level provenance labels remain correct: the newly reviewed sources either
validate an existing shape, constrain a reconstructed candidate, or describe a
method; none is the retained direct source of a final bundled field.

## ISO Standards Required For A New Measurement Campaign

No legal free full text was located for the current ISO 5 density documents.
The minimum useful purchase set is:

1. **ISO 5-2:2009**, geometric conditions for transmission density.
2. **ISO 5-3:2009**, spectral conditions.
3. **ISO 5-4:2009**, geometric conditions for reflection density, required for
   the paper profiles.

Add **ISO 5-1:2009** for the normative density definitions, notation, and common
terms if the measurement protocol will be published or used as a conformance
claim. ISO 13655:2009 Annex I explains the 3 nm to 10 nm interpolation reported
by the target vendor, but it does not fill the missing ISO 5 transmission and
reflection geometry requirements.

## Recommended Next Steps

> **Superseded for the active 2026-07-13 closed-evidence goal.** The current
> scope explicitly forbids contacting vendors/authors and does not depend on
> acquiring or measuring new film. Items 1–3 below are retained only as a
> historical record of what would be required to remove those external gaps;
> they are not active tasks. Continue with the public-source and repeatable
> local-computation path in
> [`profile-closed-evidence-optimization-20260713.md`](profile-closed-evidence-optimization-20260713.md).

1. Ask Wolf Faust/ColorAid for the instrument model, geometry, aperture,
   bandpass, dynamic range, target count, raw 3 nm spectra, batch construction,
   exposure/process metadata, and permission to redistribute spectra or fitted
   derivatives.
2. Run the candidates against independent same-stock targets or individually
   measured rolls that were not used to define GS0. Include repeated targets,
   multiple processing batches, and a documented scanner/illuminant chain.
3. Request Plutino's raw HSI cubes, dark/white calibration, precise wavelength
   vector, clear-base measurements, point spectra, and reuse permission. The
   PDF alone is insufficient.
4. If ISO 5-2 and 5-3 are purchased, convert their normative requirements into
   a same-roll transmission protocol with clear-base, selective dye, neutral
   ramp, repeated patch, and instrument-noise samples.
5. Promote a candidate only after the external-data license, instrument chain,
   and batch applicability are resolved. Keep defaults unchanged until held-out
   spectral, colorimetric, neutral-ramp, and runtime tests all improve without
   changing field meaning.

## Further Questions

- Does the target vendor retain individual-target spectra and per-band standard
  deviations behind the batch averages?
- Can the exact emulsion revisions represented by F240222 and N230513 be tied to
  the manufacturer graphs used by the historical profile creator?
- Is a three-effective-generator runtime sufficient for Provia 400X-like stocks
  where chemical separation finds two magenta dyes, or should future profiles
  represent more physical layers while retaining a three-channel interface?
- Can a stock-specific reflection model be validated for Endura before any
  analytical paper basis is reconstructed from the measured patches?
