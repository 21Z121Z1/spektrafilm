# Profile Provenance Label Implementation Plan

Date: 2026-07-11

## Goal

Add machine-readable, field-level provenance to every bundled Spektrafilm profile without changing any profile numeric data or runtime simulation behavior. The labels must distinguish the origin of an input shape from the status of the final bundled array, and must expose generic priors, related-profile donors, reconstructions, inheritance, and runtime optimization explicitly.

## Scope

- Add a backward-compatible provenance schema under `ProfileMetadata`.
- Label every field of all 28 bundled profiles, including the Hanatos 2025 runtime-fit fields.
- Record source identifiers, donor field paths, transformations, and the absence of retained raw instrument measurements.
- Add validation and regression tests for complete coverage and the historically verified donor relationships.
- Document the vocabulary and interpretation rules.
- Do not change profile numerical arrays, profile selection, SDR output, GPU behavior, or creator algorithms.

## Schema Decision

Each field receives both:

- `origin`: where the starting information came from, such as a manufacturer graph, manufacturer composite graph, generic reference, related profile, or an internally generated value.
- `status`: what the current bundled value is, such as source-derived, reconstructed, inherited, generated, or optimized.

Optional `sources`, `derived_from`, `transformations`, and `notes` retain the evidence and processing path. Profile-level `measurement_status` explicitly records whether raw instrument measurements are retained. A manufacturer graph is not treated as raw instrument data.

## Verified Historical Relationships To Encode

- The CMY basis for C200, Pro 400H, X-Tra 400, Ektar 100, Gold 200, Portra 160/400/800, and Ultramax 400 starts from generic `Film A` data and is reconstructed against stock-specific constraints.
- Portra 800 Push 1 and Push 2 inherit their spectral fields from base Portra 800; their sensitometric curves use push-specific source graphs.
- Verita 200D uses Vision3 50D as its CMY donor.
- Crystal Archive Type II uses its own sensitivity and dye-density source graphs but uses Supra Endura as the density-curve donor.
- Supra Endura uses Portra Endura as its sensitivity and CMY donor.
- Positive-film and printing profiles reconstruct base and metameric-neutral spectra internally.
- All final density-curve models/layers and Hanatos 2025 adaptation fields are reconstructed or optimized runtime data.

## Verification

1. Compare every bundled profile's `info` and `data` payload against `HEAD` after metadata insertion; require exact equality, including `NaN` placement.
2. Load and round-trip all profiles through `profile_from_dict` / `profile_to_dict`.
3. Require provenance coverage for every `ProfileData` field.
4. Assert the known generic, donor, push, positive/printing, and generated-field relationships.
5. Run `tests/test_profiles.py`, then the standard non-GUI test suite.

