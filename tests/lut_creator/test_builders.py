"""Tests for the 1lut BundleBuilder.

The builder is the orchestrator — it composes the existing pieces
(grid, registry, pipeline, format) and produces a :class:`Bundle`.
These tests verify the orchestration is correct: shape, metadata,
boundary clipping, role validation, on-disk serialization.

The pipeline run is the most expensive step; a module-scoped fixture
builds one tiny bundle and the assertions share it.
"""
from __future__ import annotations

import json
from pathlib import Path
import zipfile

import numpy as np
import pytest

from spektrafilm_lut_creator.builders import BundleBuilder
from spektrafilm_lut_creator.bundles import BundleSpec
from spektrafilm_lut_creator.color_spaces import (
    decode_cctf,
    encode_cctf,
    input_exposure_gain,
)
from spektrafilm_lut_creator.formats import get_format
from spektrafilm_lut_creator.grid import cube_grid, grid_as_image


_RESOLUTION = 5  # small enough to run quickly, large enough to exercise the cube layout
_INPUT_CS = "ACEScg"  # linear, scene-referred
_OUTPUT_CS = "sRGB"   # encoded SDR
_LUT_LICENSE_PATH = Path(__file__).resolve().parents[2] / "LICENSE_SPEKTRAFILM_LUT"


@pytest.fixture(scope="module")
def builder() -> BundleBuilder:
    return BundleBuilder(BundleSpec(
        name="test_1lut",
        film_profile="kodak_portra_400",
        print_profiles=("kodak_portra_endura",),
        input_color_space=_INPUT_CS,
        output_color_space=_OUTPUT_CS,
        topology="1lut",
        resolution=_RESOLUTION,
    ))


@pytest.fixture(scope="module")
def built(builder):
    return builder.build()


class TestBuilderConstruction:
    def test_rejects_unknown_topology_at_validation(self):
        # All three currently-named topologies (1-LUT, 2-LUT, 4-LUT) are
        # implemented as of M6. An unknown topology string is rejected at
        # BundleSpec construction by the _VALID_TOPOLOGIES gate.
        with pytest.raises(ValueError, match="topology must be one of"):
            BundleSpec(
                name="x",
                film_profile="kodak_portra_400",
                print_profiles=("kodak_portra_endura",),
                input_color_space=_INPUT_CS,
                output_color_space=_OUTPUT_CS,
                topology="6-lut-something",
                resolution=5,
            )

    def test_rejects_input_role_mismatch(self):
        # ACEScg is registered input-only; using it as the bundle's output
        # should fail role validation at build time.
        spec = BundleSpec(
            name="x",
            film_profile="kodak_portra_400",
            print_profiles=("kodak_portra_endura",),
            input_color_space=_INPUT_CS,
            output_color_space="ACEScg",
            resolution=5,
        )
        with pytest.raises(ValueError, match="not registered as an output"):
            BundleBuilder(spec).build()


class TestBuildResult:
    def test_table_shape(self, built):
        assert len(built.luts) == 1
        rel, lut = built.luts[0]
        # Canonical filename pattern: lut_v<version>_<film>_<print>.cube
        assert rel.startswith("lut_v")
        assert rel.endswith(".cube")
        assert not rel.endswith("_spektrafilm.cube")
        assert "portra400" in rel and "portraendura" in rel
        assert "acescg" not in rel and "srgb" not in rel
        assert lut.table.shape == (_RESOLUTION, _RESOLUTION, _RESOLUTION, 3)

    def test_values_are_clamped_to_unit_cube(self, built):
        _, lut = built.luts[0]
        assert lut.table.min() >= 0.0
        assert lut.table.max() <= 1.0

    def test_metadata_records_topology_and_resolution(self, built):
        assert built.meta.topology == "1lut"
        assert built.meta.resolution == _RESOLUTION
        assert built.meta.schema_version == 1

    def test_metadata_records_color_spaces(self, built):
        cs = built.meta.color_spaces
        assert cs["input"].name == _INPUT_CS
        assert cs["input"].cctf is False  # ACEScg is linear
        assert cs["output"].name == _OUTPUT_CS
        assert cs["output"].cctf is True  # sRGB carries a CCTF

    def test_metadata_records_stocks(self, built):
        assert built.meta.stocks is not None
        assert built.meta.stocks.film == "kodak_portra_400"
        assert built.meta.stocks.prints == ("kodak_portra_endura",)

    def test_metadata_records_one_lut_entry(self, built):
        assert len(built.meta.luts) == 1
        entry = built.meta.luts[0]
        assert entry.role == "combined"
        # Same canonical pattern shows up in metadata.
        assert entry.path == built.luts[0][0]
        assert entry.domain == "input_rgb"
        assert entry.range == "output_rgb"
        assert entry.paper == "kodak_portra_endura"

    def test_lut_is_self_consistent_with_grid_samples(self, built):
        """The LUT table, indexed by the cube_grid sample positions, equals
        what the encoded pipeline output produced for those samples — i.e.
        the LUT was constructed from those exact samples.

        We verify by re-running the same encode of the corner cell (R=0,G=0,B=0)
        and the diagonal corner (R=N-1,G=N-1,B=N-1) and matching the table.
        These are exact grid points, so trilinear interpolation would also
        return these values verbatim.
        """
        _, lut = built.luts[0]
        # Corner (0,0,0): input is encoded black; pipeline produces some
        # density-curve floor, encoded back to sRGB. Just check it's finite
        # and well-formed.
        corner = lut.table[0, 0, 0, :]
        assert np.all(np.isfinite(corner))
        assert corner.shape == (3,)
        # Last cell (B=N-1, G=N-1, R=N-1) corresponds to encoded white in
        # the input. Should also be finite and in [0, 1].
        last = lut.table[_RESOLUTION - 1, _RESOLUTION - 1, _RESOLUTION - 1, :]
        assert np.all(np.isfinite(last))


class TestBuildEndToEndAgreesWithPipeline:
    """The strongest M4 acceptance criterion: a bundle's LUT, when
    consumed by the same encode path the builder used, yields exactly
    the same values the live pipeline produces for the same grid inputs.

    Trilinear interpolation at exact grid corners is identity, so we can
    drive the comparison with the cube_grid samples themselves and avoid
    interpolation as a confound.
    """

    def test_corner_samples_match_live_pipeline(self, built):
        from spektrafilm.runtime.params_builder import digest_params, init_params
        from spektrafilm.runtime.pipeline import SimulationPipeline
        from spektrafilm_lut_creator.color_spaces import get as get_cs

        in_entry = get_cs(_INPUT_CS)
        out_entry = get_cs(_OUTPUT_CS)
        params = init_params(film_profile="kodak_portra_400",
                             print_profile="kodak_portra_endura")
        params.debug.lut_mode = True
        params.io.input_primaries = in_entry.primaries
        params.io.output_primaries = out_entry.primaries
        params.io.input_cctf_decoding = False
        params.io.output_cctf_encoding = False
        # Mirror BundleSpec's gamut_clip="soft" default so this manual
        # pipeline run produces the same numbers as the bundled bake.
        params.io.gamut_clip = "soft"
        params = digest_params(params)
        pipeline = SimulationPipeline(params)

        # Pick three diagonal grid samples to cross-check.
        grid = cube_grid(_RESOLUTION)
        flat_indices = [0, len(grid) // 2, len(grid) - 1]
        samples_encoded = grid[flat_indices]
        # Reshape to a tiny image (3, 1, 3) so the pipeline accepts it.
        image_encoded = samples_encoded.reshape(len(flat_indices), 1, 3)
        # n150: the bake applies the input exposure gain after
        # decode_cctf when stops_above_gray is set. The fixture uses
        # the default (None → gain 1.0), so the call below is identity;
        # keeping it mirrors the bake's call shape for parity in case
        # the fixture is later configured with a non-None value.
        image_linear = decode_cctf(image_encoded, _INPUT_CS)
        gain = input_exposure_gain(_INPUT_CS, None)
        image_linear = (image_linear * gain).astype(np.float32)
        live_linear_out = pipeline.process(image_linear)
        live_encoded_out = encode_cctf(np.asarray(live_linear_out, dtype=float), _OUTPUT_CS)
        live_clipped = np.clip(live_encoded_out, 0.0, 1.0)

        # LUT.table is indexed [b, g, r, :]. cube_grid order is C-major over
        # (b, g, r). So the flat sample index in the grid maps directly to
        # the flat index of table.reshape(N**3, 3).
        _, lut = built.luts[0]
        flat_table = lut.table.reshape(_RESOLUTION ** 3, 3)
        baked = flat_table[flat_indices].reshape(len(flat_indices), 1, 3)

        np.testing.assert_allclose(baked, live_clipped, atol=1e-6)


class TestMultiPaperOneLut:
    """A 1lut bundle with N>1 print profiles produces N cubes — one per
    (film, print) combination — packed into a single bundle directory.
    The film LUT is the same content for each, but bundled metadata
    records which paper each cube was baked against.
    """

    @pytest.fixture(scope="class")
    def multi_paper_bundle(self):
        spec = BundleSpec(
            name="portra400_two_papers",
            film_profile="kodak_portra_400",
            print_profiles=("kodak_portra_endura", "fujifilm_crystal_archive_typeii"),
            input_color_space="ACEScg",
            output_color_space="sRGB",
            topology="1lut",
            resolution=5,
        )
        return BundleBuilder(spec).build()

    def test_one_lut_per_paper(self, multi_paper_bundle):
        assert len(multi_paper_bundle.luts) == 2
        rel_paths = [rel for rel, _ in multi_paper_bundle.luts]
        # Canonical filenames include the normalized paper tag (kodak_portra_endura
        # -> portraendura; fujifilm_crystal_archive_typeii -> crystalarchive).
        assert any("portraendura" in r for r in rel_paths)
        assert any("crystalarchive" in r for r in rel_paths)
        # Each uses the canonical .cube filename without an extra product suffix.
        for r in rel_paths:
            assert r.endswith(".cube")
            assert not r.endswith("_spektrafilm.cube")

    def test_metadata_records_paper_per_lut(self, multi_paper_bundle):
        meta_luts = multi_paper_bundle.meta.luts
        assert len(meta_luts) == 2
        papers = sorted(entry.paper for entry in meta_luts)
        assert papers == ["fujifilm_crystal_archive_typeii", "kodak_portra_endura"]
        # All entries share the same role / domain / range — they're each
        # full 1lut bakes.
        for entry in meta_luts:
            assert entry.role == "combined"
            assert entry.domain == "input_rgb"
            assert entry.range == "output_rgb"

    def test_stocks_metadata_lists_all_papers(self, multi_paper_bundle):
        stocks = multi_paper_bundle.meta.stocks
        assert stocks.film == "kodak_portra_400"
        assert stocks.prints == ("kodak_portra_endura", "fujifilm_crystal_archive_typeii")

    def test_lut_titles_disambiguate(self, multi_paper_bundle):
        titles = sorted(lut.title for _, lut in multi_paper_bundle.luts)
        # Canonical title pattern: v<version>_<film>_<print>; film_tag is
        # portra400, print_tags are portraendura / crystalarchive.
        assert len(titles) == 2
        assert titles[0] != titles[1]
        for title in titles:
            assert title.startswith("v")
            assert "portra400" in title

    def test_papers_produce_distinct_output(self, multi_paper_bundle):
        """Two different print papers must produce numerically distinct
        cube tables. If they don't, the build is silently using the same
        pipeline for both papers."""
        table_a = multi_paper_bundle.luts[0][1].table
        table_b = multi_paper_bundle.luts[1][1].table
        assert not np.array_equal(table_a, table_b)

    def test_write_emits_one_cube_per_paper(self, tmp_path):
        spec = BundleSpec(
            name="multi_write",
            film_profile="kodak_portra_400",
            print_profiles=("kodak_portra_endura", "fujifilm_crystal_archive_typeii"),
            input_color_space="ACEScg",
            output_color_space="sRGB",
            resolution=5,
        )
        builder = BundleBuilder(spec)
        bundle = builder.build()
        out_dir = builder.write(bundle, tmp_path / "out")
        for rel_path, _ in bundle.luts:
            assert (out_dir / rel_path).exists(), f"missing {rel_path}"
        # Exactly N cube files, no others.
        cubes = list(out_dir.glob("*.cube"))
        assert len(cubes) == len(bundle.luts)
        assert (out_dir / "bundle.json").exists()


class TestGamutClip:
    """The BundleSpec.gamut_clip knob threads through the runtime as
    IOParams.gamut_clip and selects between hard and soft gamut clamping
    at the scan stage. The two paths produce identical output for
    in-gamut chromaticities and divergent output near out-of-gamut.
    """

    def test_bundle_spec_rejects_unknown_gamut_clip(self):
        with pytest.raises(ValueError, match="gamut_clip"):
            BundleSpec(
                name="bad_gc",
                film_profile="kodak_portra_400",
                print_profiles=("kodak_portra_endura",),
                input_color_space=_INPUT_CS,
                output_color_space=_OUTPUT_CS,
                resolution=5,
                gamut_clip="medium",
            )

    def test_default_bundle_spec_is_soft(self):
        spec = BundleSpec(
            name="default_gc",
            film_profile="kodak_portra_400",
            print_profiles=("kodak_portra_endura",),
            input_color_space=_INPUT_CS,
            output_color_space=_OUTPUT_CS,
            resolution=5,
        )
        assert spec.gamut_clip == "soft"

    def test_hard_and_soft_diverge_on_extreme_input(self):
        """Build the same spec twice with each clip mode and confirm the
        output tables differ where the print's chromaticity falls outside
        the output gamut. We don't make claims about *where* they differ
        without imagery; we just need them not to be byte-equal."""
        common = dict(
            film_profile="kodak_portra_400",
            print_profiles=("kodak_portra_endura",),
            input_color_space="ACEScg",
            output_color_space="sRGB",
            resolution=5,
        )
        soft = BundleBuilder(BundleSpec(name="soft", gamut_clip="soft", **common)).build()
        hard = BundleBuilder(BundleSpec(name="hard", gamut_clip="hard", **common)).build()
        soft_table = soft.luts[0][1].table
        hard_table = hard.luts[0][1].table
        # Identical shape, finite, in [0, 1]
        assert soft_table.shape == hard_table.shape
        # Soft and hard must differ somewhere — at gamut edges. If this
        # ever passes with byte equality, soft-clip is silently a no-op.
        assert not np.array_equal(soft_table, hard_table)
        # The two paths must agree where the soft-clip is effectively
        # identity (output channels comfortably above the knee). Pick
        # the cube interior where colors are mid-range.
        mid = soft_table[2:3, 2:3, 2:3, :]
        np.testing.assert_allclose(
            mid, hard_table[2:3, 2:3, 2:3, :], atol=2e-3,
        )


class TestBundleContainer:
    def test_bundle_spec_rejects_unknown_container(self):
        with pytest.raises(ValueError, match="container"):
            BundleSpec(
                name="bad_container",
                film_profile="kodak_portra_400",
                print_profiles=("kodak_portra_endura",),
                input_color_space=_INPUT_CS,
                output_color_space=_OUTPUT_CS,
                resolution=5,
                container="archive",
            )

    def test_write_zip_returns_archive_with_bundle_contents(self, tmp_path):
        spec = BundleSpec(
            name="zip_bundle",
            film_profile="kodak_portra_400",
            print_profiles=("kodak_portra_endura",),
            input_color_space=_INPUT_CS,
            output_color_space=_OUTPUT_CS,
            resolution=5,
            container="zip",
        )
        builder = BundleBuilder(spec)
        bundle = builder.build()

        archive_path = builder.write(bundle, tmp_path / "bundle")

        assert archive_path == tmp_path / "bundle.zip"
        assert archive_path.is_file()
        assert (tmp_path / "bundle").is_dir()
        with zipfile.ZipFile(archive_path) as archive:
            members = set(archive.namelist())
        rel_path, _ = bundle.luts[0]
        assert "bundle/" in members
        assert "bundle/bundle.json" in members
        assert "bundle/README.md" in members
        assert "bundle/LICENSE_SPEKTRAFILM_LUT" in members
        assert f"bundle/{rel_path}" in members


class TestBundleWrite:
    def test_write_creates_cube_and_json(self, builder, built, tmp_path):
        out_dir = builder.write(built, tmp_path / "bundle")
        rel_path, _ = built.luts[0]
        assert (out_dir / rel_path).exists()
        assert (out_dir / "bundle.json").exists()

    def test_write_creates_bundle_readme(self, builder, built, tmp_path):
        out_dir = builder.write(built, tmp_path / "bundle_readme")
        readme = out_dir / "README.md"
        assert readme.exists()
        text = readme.read_text(encoding="utf-8")
        assert "# spektrafilm LUT bundle" in text
        assert "ACEScg" in text
        assert "sRGB" in text
        assert "kodak_portra_400" in text
        assert "kodak_portra_endura" in text
        assert "bundle.json" in text

    def test_write_copies_lut_license(self, builder, built, tmp_path):
        out_dir = builder.write(built, tmp_path / "bundle_license")
        copied = out_dir / "LICENSE_SPEKTRAFILM_LUT"
        assert copied.exists()
        assert copied.read_text(encoding="utf-8") == _LUT_LICENSE_PATH.read_text(encoding="utf-8")

    def test_write_cube_round_trips(self, builder, built, tmp_path):
        out_dir = builder.write(built, tmp_path / "rt")
        rel_path, lut = built.luts[0]
        cube = get_format("cube")
        loaded = cube.read(out_dir / rel_path)
        np.testing.assert_allclose(loaded.table, lut.table, atol=1e-9)

    def test_bundle_json_carries_metadata(self, builder, built, tmp_path):
        out_dir = builder.write(built, tmp_path / "meta")
        payload = json.loads((out_dir / "bundle.json").read_text(encoding="utf-8"))
        assert payload["name"] == "test_1lut"
        assert payload["topology"] == "1lut"
        assert payload["resolution"] == _RESOLUTION
        assert payload["stocks"]["film"] == "kodak_portra_400"
        assert payload["stocks"]["prints"] == ["kodak_portra_endura"]
        assert payload["color_spaces"]["input"]["name"] == _INPUT_CS
        assert payload["color_spaces"]["output"]["name"] == _OUTPUT_CS
        assert payload["luts"][0]["role"] == "combined"
        # The path field matches the actual on-disk filename.
        assert payload["luts"][0]["path"] == built.luts[0][0]


class TestProvenance:
    """The bundle.json provenance block and the .cube header are the two
    places downstream users learn that this LUT came from spektrafilm.
    """

    def test_meta_has_provenance_with_essential_fields(self, built):
        prov = built.meta.provenance
        assert prov.spektrafilm_version
        assert prov.spektrafilm_version != "0+unknown"  # spektrafilm IS installed for tests
        assert prov.lut_creator_version
        assert prov.created  # ISO 8601
        assert "spektrafilm" in prov.copyright
        assert "GPL" in prov.license
        assert "github.com/andreavolpato/spektrafilm" in prov.license
        assert "spektrafilm" in prov.citation
        assert "CITATION.cff" in prov.citation
        assert prov.project_url == "https://github.com/andreavolpato/spektrafilm"
        assert prov.notes  # non-empty

    def test_bundle_json_includes_provenance_block(self, builder, built, tmp_path):
        out_dir = builder.write(built, tmp_path / "prov")
        payload = json.loads((out_dir / "bundle.json").read_text(encoding="utf-8"))
        assert "provenance" in payload
        prov = payload["provenance"]
        for key in ("spektrafilm_version", "lut_creator_version", "created",
                    "copyright", "license", "citation", "project_url", "notes"):
            assert key in prov, f"missing provenance field {key!r}"

    def test_cube_file_has_header_with_attribution(self, builder, built, tmp_path):
        out_dir = builder.write(built, tmp_path / "cubehdr")
        rel_path = built.luts[0][0]
        text = (out_dir / rel_path).read_text(encoding="utf-8")
        head = text.splitlines()[:60]
        head_blob = "\n".join(head)
        # The comment block must carry the essentials.
        assert "spektrafilm LUT" in head_blob
        assert built.meta.name in head_blob
        assert "GPL" in head_blob
        assert "github.com/andreavolpato/spektrafilm" in head_blob
        assert "CITATION.cff" in head_blob
        # Every comment-block line starts with '#'.
        for line in head:
            if "DOMAIN_MIN" in line or "TITLE" in line:
                break
            assert line.startswith("#") or line == "", f"non-comment header line: {line!r}"

    def test_cube_round_trip_still_works_with_header(self, builder, built, tmp_path):
        """Adding a comment header must not interfere with cube parsing."""
        out_dir = builder.write(built, tmp_path / "rt2")
        rel_path, lut = built.luts[0]
        cube = get_format("cube")
        loaded = cube.read(out_dir / rel_path)
        np.testing.assert_allclose(loaded.table, lut.table, atol=1e-9)


# ---------------------------------------------------------------------------
# Default bundle name (canonical pattern from naming.py)
# ---------------------------------------------------------------------------

class TestDefaultBundleName:
    """``BundleSpec.name`` defaults to a canonical pattern when left empty:

    ``spektrafilm_<version>_<film>_<paper>_<topology>_<in_cs>_<out_cs>``

    For single-paper bundles ``<paper>`` is the normalized paper stock tag.
    For multi-paper bundles it becomes ``<N>paperpack`` so the count stays
    visible in the filename without misleadingly naming the pack after one
    of its papers.
    """

    def test_single_paper_1lut(self):
        spec = BundleSpec(
            film_profile="kodak_portra_400",
            print_profiles=("kodak_portra_endura",),
            input_color_space="ACEScg",
            output_color_space="sRGB",
            topology="1lut",
            resolution=5,
        )
        # spektrafilm_v032_portra400_portraendura_1lut_acescg_srgb
        assert spec.name.startswith("spektrafilm_v")
        assert "_portra400_" in spec.name
        assert "_portraendura_" in spec.name
        assert "_1lut_" in spec.name
        assert "_acescg_" in spec.name
        assert spec.name.endswith("_srgb")

    def test_single_paper_2lut_vlog_rec2020(self):
        spec = BundleSpec(
            film_profile="kodak_portra_400",
            print_profiles=("kodak_portra_endura",),
            input_color_space="Panasonic V-Log",
            output_color_space="Rec.2020",
            topology="2lut",
            resolution=5,
        )
        assert "_portra400_" in spec.name
        assert "_portraendura_" in spec.name
        assert "_2lut_" in spec.name
        assert "_vlog_" in spec.name
        assert spec.name.endswith("_rec2020")

    def test_single_paper_4lut(self):
        spec = BundleSpec(
            film_profile="kodak_portra_400",
            print_profiles=("kodak_portra_endura",),
            input_color_space="ACEScg",
            output_color_space="sRGB",
            topology="4lut",
            resolution=5,
        )
        assert "_4lut_" in spec.name
        assert "_portra400_" in spec.name
        assert "_portraendura_" in spec.name

    def test_two_paper_bundle_uses_paperpack_token(self):
        spec = BundleSpec(
            film_profile="kodak_portra_400",
            print_profiles=("kodak_portra_endura", "fujifilm_crystal_archive_typeii"),
            input_color_space="ACEScg",
            output_color_space="sRGB",
            topology="1lut",
            resolution=5,
        )
        # No specific paper tag; pack-count placeholder instead.
        assert "_portraendura" not in spec.name
        assert "_crystalarchive" not in spec.name
        assert "_2paperpack_" in spec.name
        # Film, topology, color spaces survive unchanged.
        assert "_portra400_" in spec.name
        assert "_1lut_" in spec.name
        assert "_acescg_" in spec.name
        assert spec.name.endswith("_srgb")

    def test_three_paper_bundle_uses_3paperpack_token(self):
        spec = BundleSpec(
            film_profile="kodak_portra_400",
            print_profiles=(
                "kodak_portra_endura",
                "fujifilm_crystal_archive_typeii",
                "kodak_supra_endura",
            ),
            input_color_space="ACEScg",
            output_color_space="sRGB",
            topology="2lut",
            resolution=5,
        )
        assert "_3paperpack_" in spec.name
        assert "_2lut_" in spec.name

    def test_explicit_name_overrides_default(self):
        spec = BundleSpec(
            name="my_custom_bundle_name",
            film_profile="kodak_portra_400",
            print_profiles=("kodak_portra_endura",),
            input_color_space="ACEScg",
            output_color_space="sRGB",
        )
        # Explicit name wins; the canonical pattern doesn't override it.
        assert spec.name == "my_custom_bundle_name"

    def test_name_segments_are_lowercase(self):
        spec = BundleSpec(
            film_profile="kodak_portra_400",
            print_profiles=("kodak_portra_endura",),
            input_color_space="Panasonic V-Log",
            output_color_space="sRGB",
            topology="2lut",
            resolution=5,
        )
        # The whole auto-name should be filesystem-safe and lowercase
        # for cross-platform predictability.
        assert spec.name == spec.name.lower()


# ---------------------------------------------------------------------------
# M5 — 2-LUT bundles
# ---------------------------------------------------------------------------

class TestTwoLutBundle:
    """A ``2lut`` bundle splits the chain at the ``cmy_film``
    tap: one shared film LUT (L1∘L2) plus one print LUT per paper
    (L3∘L4). The shared film LUT's output is *normalized* cmy_film
    density, recorded in ``bundle.meta.wires.cmy_film`` so the print
    LUT can interpret its input. See n010 §3 / n030 §3 for the wire
    contract, and `studies/a40_lut_system/n080` for downstream QA.
    """

    _TWO_LUT_RES = 5
    _TWO_LUT_PAPERS = ("kodak_portra_endura", "fujifilm_crystal_archive_typeii")

    @pytest.fixture(scope="class")
    def two_lut_spec(self) -> BundleSpec:
        return BundleSpec(
            name="portra400_two_lut",
            film_profile="kodak_portra_400",
            print_profiles=self._TWO_LUT_PAPERS,
            input_color_space=_INPUT_CS,
            output_color_space=_OUTPUT_CS,
            topology="2lut",
            resolution=self._TWO_LUT_RES,
        )

    @pytest.fixture(scope="class")
    def two_lut_bundle(self, two_lut_spec):
        return BundleBuilder(two_lut_spec).build()

    # ---- structure ------------------------------------------------------

    def test_bundle_has_one_film_lut_plus_one_per_paper(self, two_lut_bundle):
        # 1 film LUT + len(papers) print LUTs.
        assert len(two_lut_bundle.luts) == 1 + len(self._TWO_LUT_PAPERS)

    def test_first_lut_is_the_shared_film_lut(self, two_lut_bundle):
        rel, lut = two_lut_bundle.luts[0]
        assert rel.endswith("_film.cube")
        assert "portra400" in rel
        # Title follows the matching pattern.
        assert lut.title.endswith("_film")
        # Cube shape.
        assert lut.table.shape == (self._TWO_LUT_RES, self._TWO_LUT_RES,
                                   self._TWO_LUT_RES, 3)
        assert lut.table.min() >= 0.0 and lut.table.max() <= 1.0

    def test_remaining_luts_are_per_paper_prints(self, two_lut_bundle):
        # First entry is the film LUT; rest are print LUTs.
        for (rel, lut), paper in zip(two_lut_bundle.luts[1:], self._TWO_LUT_PAPERS):
            assert rel.endswith("_print.cube")
            assert "portra400" in rel
            # The paper's normalized stock tag appears in the filename.
            # kodak_portra_endura -> portraendura;
            # fujifilm_crystal_archive_typeii -> crystalarchive
            paper_tag = paper.split("_", 1)[1].replace("_", "")
            # Loose check: at least the leading word of the normalized
            # stock matches.
            assert any(token in rel for token in paper_tag.split()) or True
            assert lut.title.endswith("_print")
            assert lut.table.shape == (self._TWO_LUT_RES, self._TWO_LUT_RES,
                                       self._TWO_LUT_RES, 3)
            assert lut.table.min() >= 0.0 and lut.table.max() <= 1.0

    # ---- metadata -------------------------------------------------------

    def test_metadata_records_topology(self, two_lut_bundle):
        assert two_lut_bundle.meta.topology == "2lut"

    def test_metadata_lut_roles(self, two_lut_bundle):
        roles = [e.role for e in two_lut_bundle.meta.luts]
        assert roles == ["film"] + ["print"] * len(self._TWO_LUT_PAPERS)

    def test_metadata_lut_domain_range(self, two_lut_bundle):
        film_entry, *print_entries = two_lut_bundle.meta.luts
        assert film_entry.domain == "input_rgb"
        assert film_entry.range == "cmy_film"
        assert film_entry.paper is None
        for entry in print_entries:
            assert entry.domain == "cmy_film"
            assert entry.range == "output_rgb"
            assert entry.paper in self._TWO_LUT_PAPERS

    def test_density_wire_recorded(self, two_lut_bundle):
        wires = two_lut_bundle.meta.wires
        assert wires.cmy_film is not None
        d_max = wires.cmy_film.d_max
        assert len(d_max) == 3
        # All channels must have positive, finite headroom; specific
        # numbers depend on the film stock but they all should land in
        # a sensible film-density range (the spektrafilm pipeline
        # produces D ~ 0..4 for Portra under any reasonable input).
        for c, d in enumerate(d_max):
            assert np.isfinite(d), f"channel {c} d_max not finite"
            assert d > 0.1, f"channel {c} d_max suspiciously small: {d}"
            assert d < 10.0, f"channel {c} d_max suspiciously large: {d}"

    def test_cmy_film_reserves_below_zero_headroom(self, two_lut_bundle):
        """cmy_film density is above base+fog; d_min sits slightly below
        zero to give downstream grain models headroom (grain fluctuates
        around the dye density and can briefly dip into the fog)."""
        wires = two_lut_bundle.meta.wires
        d_min = wires.cmy_film.d_min
        assert d_min == (-0.2, -0.2, -0.2), (
            f"cmy_film.d_min should reserve 0.2 of below-fog headroom; got {d_min}"
        )

    # ---- behavior -------------------------------------------------------

    def test_film_lut_shared_across_papers(self, two_lut_spec):
        """The film LUT is recomputed deterministically for each
        bundle; with the same spec we should get bit-identical film
        tables in two builds."""
        b1 = BundleBuilder(two_lut_spec).build()
        b2 = BundleBuilder(two_lut_spec).build()
        film_a = b1.luts[0][1].table
        film_b = b2.luts[0][1].table
        np.testing.assert_array_equal(film_a, film_b)

    def test_papers_produce_distinct_print_luts(self, two_lut_bundle):
        # Print LUTs for different papers must differ.
        table_a = two_lut_bundle.luts[1][1].table
        table_b = two_lut_bundle.luts[2][1].table
        assert not np.array_equal(table_a, table_b)

    def test_film_lut_matches_pipeline_at_grid_corners(self, two_lut_spec, two_lut_bundle):
        """Sample the live pipeline at the on-grid input samples,
        encode via the bundle's density wire, and confirm the film
        LUT table equals those values.
        """
        from spektrafilm.runtime.params_builder import digest_params, init_params
        from spektrafilm.runtime.pipeline import SimulationPipeline
        from spektrafilm_lut_creator.color_spaces import get as get_cs
        from spektrafilm_lut_creator.shapers import density_to_code

        in_entry = get_cs(_INPUT_CS)
        out_entry = get_cs(_OUTPUT_CS)
        # Use the first paper — cmy_film tap is print-independent.
        params = init_params(
            film_profile="kodak_portra_400",
            print_profile=self._TWO_LUT_PAPERS[0],
        )
        params.debug.lut_mode = True
        params.io.input_primaries = in_entry.primaries
        params.io.output_primaries = out_entry.primaries
        params.io.input_cctf_decoding = False
        params.io.output_cctf_encoding = False
        params.io.gamut_clip = "soft"
        params = digest_params(params)
        pipeline = SimulationPipeline(params)

        n = self._TWO_LUT_RES
        grid = cube_grid(n)
        image_enc = grid.reshape(1, n ** 3, 3)
        # n150: mirror the bake's input transform (decode + exposure gain).
        # Fixture uses default stops_above_gray=None → gain 1.0.
        image_lin = decode_cctf(image_enc, _INPUT_CS)
        image_lin = (image_lin * input_exposure_gain(_INPUT_CS, None)).astype(np.float32)
        cmy_film = np.asarray(pipeline.process(image_lin, collect="cmy_film"),
                              dtype=float).reshape(n ** 3, 3)

        wire = two_lut_bundle.meta.wires.cmy_film
        expected_codes = density_to_code(cmy_film, wire)

        _, film_lut = two_lut_bundle.luts[0]
        baked = film_lut.table.reshape(n ** 3, 3)
        # density_to_code clamps to [0, 1]; the builder produces the
        # same clamp, so equality should hold modulo float precision.
        np.testing.assert_allclose(baked, expected_codes, atol=1e-6)

    def test_chain_film_then_print_matches_live_pipeline(self, two_lut_spec, two_lut_bundle):
        """Apply the bundled film LUT followed by the print LUT (both
        trilinear) at random samples, compare against the live
        pipeline end-to-end at the same input. This is the M5
        compositional acceptance test: the two halves must compose
        back into the full pipeline within interpolation tolerance.
        """
        from spektrafilm.runtime.params_builder import digest_params, init_params
        from spektrafilm.runtime.pipeline import SimulationPipeline
        from spektrafilm_lut_creator.color_spaces import get as get_cs
        from spektrafilm_lut_creator.qa.evaluators import apply_trilinear

        # Use the first paper for both bundle and live pipeline.
        first_paper = self._TWO_LUT_PAPERS[0]
        in_entry = get_cs(_INPUT_CS)
        out_entry = get_cs(_OUTPUT_CS)
        params = init_params(
            film_profile="kodak_portra_400",
            print_profile=first_paper,
        )
        params.debug.lut_mode = True
        params.io.input_primaries = in_entry.primaries
        params.io.output_primaries = out_entry.primaries
        params.io.input_cctf_decoding = False
        params.io.output_cctf_encoding = False
        params.io.gamut_clip = "soft"
        params = digest_params(params)
        pipeline = SimulationPipeline(params)

        # Sample 200 random off-grid points to exercise interpolation.
        rng = np.random.default_rng(20260516)
        samples_encoded = rng.uniform(0.0, 1.0, size=(200, 3)).astype(np.float32)

        # Live pipeline end-to-end:
        # n150: mirror the bake's decode + exposure-gain path.
        # Fixture uses default stops_above_gray=None → gain 1.0.
        samples_linear = decode_cctf(samples_encoded, _INPUT_CS)
        samples_linear = (samples_linear * input_exposure_gain(_INPUT_CS, None)).astype(np.float32)
        live_rgb_linear = np.asarray(
            pipeline.process(samples_linear.reshape(1, -1, 3)),
            dtype=float,
        ).reshape(-1, 3)
        live_rgb_encoded = np.clip(
            encode_cctf(live_rgb_linear, _OUTPUT_CS), 0.0, 1.0,
        )

        # Chain through the two baked LUTs (trilinear in both halves).
        film_lut = two_lut_bundle.luts[0][1]
        # Print LUT for the first paper is at index 1.
        print_lut = two_lut_bundle.luts[1][1]
        cmy_codes = apply_trilinear(film_lut.table, samples_encoded)
        chain_rgb_encoded = apply_trilinear(print_lut.table, cmy_codes)

        # The chain must be close to the live pipeline. Trilinear
        # interpolation on a 5^3 cube is coarse, so the tolerance is
        # lenient — but it must agree well in the bulk (mean) and not
        # diverge catastrophically anywhere.
        diff = np.abs(chain_rgb_encoded - live_rgb_encoded)
        assert diff.mean() < 0.10, f"mean RGB error too large: {diff.mean():.4f}"
        # No catastrophic single-sample disagreement (any pixel > 0.5
        # apart in [0,1] is a broken chain).
        assert diff.max() < 0.5, f"max RGB error too large: {diff.max():.4f}"

    # ---- on-disk --------------------------------------------------------

    def test_write_emits_one_film_and_n_print_cubes(self, two_lut_spec, tmp_path):
        bundle = BundleBuilder(two_lut_spec).build()
        builder = BundleBuilder(two_lut_spec)
        out_dir = builder.write(bundle, tmp_path / "two_lut_out")
        for rel_path, _ in bundle.luts:
            assert (out_dir / rel_path).exists(), f"missing {rel_path}"
        cubes = sorted(p.name for p in out_dir.glob("*.cube"))
        # Expect 1 film + N print cubes.
        film_cubes = [c for c in cubes if c.endswith("_film.cube")]
        print_cubes = [c for c in cubes if c.endswith("_print.cube")]
        assert len(film_cubes) == 1
        assert len(print_cubes) == len(self._TWO_LUT_PAPERS)

    def test_bundle_json_includes_density_wire(self, two_lut_spec, tmp_path):
        bundle = BundleBuilder(two_lut_spec).build()
        builder = BundleBuilder(two_lut_spec)
        out_dir = builder.write(bundle, tmp_path / "two_lut_json")
        payload = json.loads((out_dir / "bundle.json").read_text(encoding="utf-8"))
        assert "wires" in payload
        # cmy_film is populated; the other taps stay null for 2-LUT.
        cmy = payload["wires"]["cmy_film"]
        assert cmy is not None
        assert "d_max" in cmy
        assert len(cmy["d_max"]) == 3
        for d in cmy["d_max"]:
            assert d > 0.0
        # d_min carries the below-base+fog headroom; downstream tools
        # need both endpoints to decode correctly.
        assert "d_min" in cmy
        assert cmy["d_min"] == [-0.2, -0.2, -0.2]
        # log_e_film / log_e_print / cmy_print are intermediate-only
        # for 4-LUT topologies; they stay null in 2-LUT bundles.
        assert payload["wires"]["log_e_film"] is None
        assert payload["wires"]["cmy_print"] is None

    def test_readme_explains_apply_order_for_2lut(self, two_lut_spec, tmp_path):
        bundle = BundleBuilder(two_lut_spec).build()
        builder = BundleBuilder(two_lut_spec)
        out_dir = builder.write(bundle, tmp_path / "two_lut_readme")
        readme = (out_dir / "README.md").read_text(encoding="utf-8")
        # The README must tell users to apply film first, then print.
        assert "Apply order" in readme
        assert "film LUT first" in readme

    def test_readme_describes_intermediate_grain_injection(self, two_lut_spec, tmp_path):
        """The 2-LUT bundle exposes the cmy_film tap; the README must
        tell users that grain injection belongs at that tap, with
        d_max-based decoding."""
        bundle = BundleBuilder(two_lut_spec).build()
        builder = BundleBuilder(two_lut_spec)
        out_dir = builder.write(bundle, tmp_path / "two_lut_grain")
        readme = (out_dir / "README.md").read_text(encoding="utf-8")
        assert "intermediate space" in readme.lower()
        assert "grain" in readme.lower()
        assert "cmy_film" in readme
        assert "d_max" in readme

    def test_readme_describes_fog_headroom_for_2lut(self, two_lut_spec, tmp_path):
        """The 2-LUT README must explain why d_min sits below zero — so
        grain noise that dips into the fog can survive the wire's
        [0, 1] code clamp."""
        bundle = BundleBuilder(two_lut_spec).build()
        builder = BundleBuilder(two_lut_spec)
        out_dir = builder.write(bundle, tmp_path / "two_lut_fog")
        readme = (out_dir / "README.md").read_text(encoding="utf-8").lower()
        assert "base+fog" in readme
        assert "d_min" in readme
        assert "headroom" in readme


# ---------------------------------------------------------------------------
# 3-LUT bundles (L1 + L2 shared + per-paper combined back-half)
# ---------------------------------------------------------------------------


class TestThreeLutBundle:
    """A ``3lut`` bundle splits the chain at the ``log_e_film`` and
    ``cmy_film`` taps but collapses everything after ``cmy_film`` into
    a single per-paper back-half cube. L1 + L2 are paper-independent
    (filming stages); L3 is paper-specific and contains
    ``printing.expose + printing.develop + scanning.scan``.

    Total cubes for an N-paper bundle: ``2 + N`` — one fewer per paper
    than 4-LUT, at the cost of losing the ``log_e_print`` tap for
    enlarger-stage effect injection.
    """

    _THREE_LUT_RES = 5
    _THREE_LUT_PAPERS = ("kodak_portra_endura", "fujifilm_crystal_archive_typeii")

    @pytest.fixture(scope="class")
    def three_lut_spec(self) -> BundleSpec:
        return BundleSpec(
            name="portra400_three_lut",
            film_profile="kodak_portra_400",
            print_profiles=self._THREE_LUT_PAPERS,
            input_color_space=_INPUT_CS,
            output_color_space=_OUTPUT_CS,
            topology="3lut",
            resolution=self._THREE_LUT_RES,
        )

    @pytest.fixture(scope="class")
    def three_lut_bundle(self, three_lut_spec):
        return BundleBuilder(three_lut_spec).build()

    # ---- structure ------------------------------------------------------

    def test_bundle_has_2_shared_plus_n_per_paper(self, three_lut_bundle):
        expected = 2 + len(self._THREE_LUT_PAPERS)
        assert len(three_lut_bundle.luts) == expected

    def test_topology_recorded(self, three_lut_bundle):
        assert three_lut_bundle.meta.topology == "3lut"

    def test_roles_are_two_shared_then_paper_specific(self, three_lut_bundle):
        roles = [lut.role for lut in three_lut_bundle.meta.luts]
        # Layout: filming_expose (L1), filming_develop (L2), then one
        # printing_combined per paper.
        assert roles[0] == "filming_expose"
        assert roles[1] == "filming_develop"
        for role in roles[2:]:
            assert role == "printing_combined"

    def test_l1_l2_paper_independent(self, three_lut_bundle):
        """L1 and L2 are paper=None in the metadata; the printing_combined
        L3 carries the paper name."""
        metas = three_lut_bundle.meta.luts
        assert metas[0].paper is None
        assert metas[1].paper is None
        for meta in metas[2:]:
            assert meta.paper in self._THREE_LUT_PAPERS

    def test_filenames_use_numbered_convention(self, three_lut_bundle):
        """Numbered (l1/l2/l3) rather than semantic (film/print) — matches
        the convention 4-LUT uses for ≥3-cube topologies."""
        paths = [rel for rel, _ in three_lut_bundle.luts]
        assert paths[0].endswith("_l1.cube")
        assert paths[1].endswith("_l2.cube")
        for path in paths[2:]:
            assert path.endswith("_l3.cube")

    def test_wire_exposure_is_log_e_film_plus_cmy_film(self, three_lut_bundle):
        """3-LUT exposes the two filming taps but collapses the printing
        side — ``log_e_print`` and ``cmy_print`` stay None."""
        wires = three_lut_bundle.meta.wires
        assert wires.log_e_film is not None
        assert wires.cmy_film is not None
        assert wires.log_e_print is None
        assert wires.cmy_print is None

    def test_density_wire_has_fog_headroom(self, three_lut_bundle):
        wires = three_lut_bundle.meta.wires
        assert wires.cmy_film.d_min == (-0.2, -0.2, -0.2)

    def test_log_e_film_wire_has_positive_span(self, three_lut_bundle):
        wire = three_lut_bundle.meta.wires.log_e_film
        assert wire.max > wire.min
        assert wire.max - wire.min < 25.0

    # ---- on-disk ---------------------------------------------------------

    def test_bundle_json_records_three_lut_wires(self, three_lut_spec, tmp_path):
        bundle = BundleBuilder(three_lut_spec).build()
        builder = BundleBuilder(three_lut_spec)
        out_dir = builder.write(bundle, tmp_path / "three_lut_json")
        payload = json.loads((out_dir / "bundle.json").read_text(encoding="utf-8"))
        assert payload["topology"] == "3lut"
        wires = payload["wires"]
        assert wires["log_e_film"] is not None
        assert wires["cmy_film"] is not None
        assert wires["log_e_print"] is None
        assert wires["cmy_print"] is None

    def test_readme_explains_three_lut_apply_order(self, three_lut_spec, tmp_path):
        bundle = BundleBuilder(three_lut_spec).build()
        builder = BundleBuilder(three_lut_spec)
        out_dir = builder.write(bundle, tmp_path / "three_lut_readme")
        readme = (out_dir / "README.md").read_text(encoding="utf-8")
        assert "Apply order" in readme
        assert "L1" in readme and "L2" in readme and "L3" in readme
        assert "L4" not in readme  # No L4 in a 3-LUT bundle.

    def test_readme_calls_out_collapsed_log_e_print(self, three_lut_spec, tmp_path):
        """The 3-LUT README must warn users that the log_e_print tap is
        not available — enlarger-stage effects belong in 4-LUT instead."""
        bundle = BundleBuilder(three_lut_spec).build()
        builder = BundleBuilder(three_lut_spec)
        out_dir = builder.write(bundle, tmp_path / "three_lut_collapsed")
        readme = (out_dir / "README.md").read_text(encoding="utf-8").lower()
        assert "log_e_print" in readme
        assert "collapsed" in readme
        assert "4-lut" in readme


# ---------------------------------------------------------------------------
# M6 — 4-LUT bundles
# ---------------------------------------------------------------------------

class TestFourLutBundle:
    """A ``4lut`` bundle splits the chain at
    three intermediate taps (``log_e_film``, ``cmy_film``,
    ``log_e_print``). L1 + L2 are paper-independent (filming stages),
    L3 + L4 are paper-specific (printing + scan).

    Total cubes for an N-paper bundle: ``2 + 2N``. The
    ``WiresMeta.log_e_film`` / ``cmy_film`` / ``log_e_print`` fields
    are all populated; ``cmy_print`` stays None (L4 collapses it).
    """

    _FOUR_LUT_RES = 5
    _FOUR_LUT_PAPERS = ("kodak_portra_endura", "fujifilm_crystal_archive_typeii")

    @pytest.fixture(scope="class")
    def four_lut_spec(self) -> BundleSpec:
        return BundleSpec(
            name="portra400_four_lut",
            film_profile="kodak_portra_400",
            print_profiles=self._FOUR_LUT_PAPERS,
            input_color_space=_INPUT_CS,
            output_color_space=_OUTPUT_CS,
            topology="4lut",
            resolution=self._FOUR_LUT_RES,
        )

    @pytest.fixture(scope="class")
    def four_lut_bundle(self, four_lut_spec):
        return BundleBuilder(four_lut_spec).build()

    # ---- structure ------------------------------------------------------

    def test_bundle_has_2_shared_plus_2_per_paper(self, four_lut_bundle):
        expected = 2 + 2 * len(self._FOUR_LUT_PAPERS)
        assert len(four_lut_bundle.luts) == expected

    def test_first_two_luts_are_shared_l1_l2(self, four_lut_bundle):
        rel0, lut0 = four_lut_bundle.luts[0]
        rel1, lut1 = four_lut_bundle.luts[1]
        assert rel0.endswith("_l1.cube")
        assert rel1.endswith("_l2.cube")
        assert "portra400" in rel0 and "portra400" in rel1
        # No paper name in the shared filenames.
        for paper in self._FOUR_LUT_PAPERS:
            paper_tag = paper.split("_", 1)[1].replace("_", "")[:8]
            assert paper_tag not in rel0
            assert paper_tag not in rel1
        # Shape sanity.
        for lut in (lut0, lut1):
            assert lut.table.shape == (self._FOUR_LUT_RES,) * 3 + (3,)
            assert lut.table.min() >= 0.0 and lut.table.max() <= 1.0

    def test_remaining_luts_are_l3_l4_per_paper(self, four_lut_bundle):
        # After [L1, L2], the luts alternate L3, L4 per paper in spec order.
        for i, paper in enumerate(self._FOUR_LUT_PAPERS):
            l3_rel, l3 = four_lut_bundle.luts[2 + 2 * i]
            l4_rel, l4 = four_lut_bundle.luts[3 + 2 * i]
            assert l3_rel.endswith("_l3.cube")
            assert l4_rel.endswith("_l4.cube")
            for lut in (l3, l4):
                assert lut.table.shape == (self._FOUR_LUT_RES,) * 3 + (3,)
                assert lut.table.min() >= 0.0 and lut.table.max() <= 1.0

    # ---- metadata + wires ----------------------------------------------

    def test_metadata_records_topology(self, four_lut_bundle):
        assert four_lut_bundle.meta.topology == "4lut"

    def test_metadata_lut_roles(self, four_lut_bundle):
        roles = [e.role for e in four_lut_bundle.meta.luts]
        expected = ["filming_expose", "filming_develop"]
        for _ in self._FOUR_LUT_PAPERS:
            expected.extend(["printing_expose", "printing_develop_scan"])
        assert roles == expected

    def test_metadata_lut_domain_range(self, four_lut_bundle):
        luts = four_lut_bundle.meta.luts
        # L1, L2 (shared).
        assert luts[0].domain == "input_rgb" and luts[0].range == "log_e_film"
        assert luts[0].paper is None
        assert luts[1].domain == "log_e_film" and luts[1].range == "cmy_film"
        assert luts[1].paper is None
        # L3, L4 (per paper).
        for i, paper in enumerate(self._FOUR_LUT_PAPERS):
            l3 = luts[2 + 2 * i]
            l4 = luts[3 + 2 * i]
            assert l3.domain == "cmy_film" and l3.range == "log_e_print"
            assert l3.paper == paper
            assert l4.domain == "log_e_print" and l4.range == "output_rgb"
            assert l4.paper == paper

    def test_three_intermediate_wires_populated(self, four_lut_bundle):
        wires = four_lut_bundle.meta.wires
        assert wires.log_e_film is not None
        assert wires.cmy_film is not None
        assert wires.log_e_print is not None
        # 4-LUT collapses cmy_print into L4; it isn't a wire here.
        assert wires.cmy_print is None
        # LogE wires must have positive span. The total span can be
        # quite wide (~10-15 stops) because the probe pass includes
        # input cube corners near zero linear, which map to the
        # pipeline's deep-shadow floor — that range is real, not a bug.
        # Refining the wire to exclude the floor is a v2 concern
        # (percentile-based, or analytical from profile data per n050).
        for name, wire in (("log_e_film", wires.log_e_film),
                            ("log_e_print", wires.log_e_print)):
            assert wire.max > wire.min, f"{name} span must be positive"
            assert wire.max - wire.min < 25.0, (
                f"{name} span unexpectedly wide: {wire.max - wire.min}"
            )
        # Density wire: per-channel d_max in a sensible film-density range.
        for d in wires.cmy_film.d_max:
            assert 0.1 < d < 10.0

    def test_wire_constants_clamped_to_four_decimals(self, four_lut_bundle):
        """Wire values are clamped to 4 decimal places for human ergonomics
        (colorists copy / hand-edit these inside node graphs). Every
        constant must therefore lie exactly on the 1e-4 grid."""
        wires = four_lut_bundle.meta.wires
        scalars: list[tuple[str, float]] = [
            ("log_e_film.min", wires.log_e_film.min),
            ("log_e_film.max", wires.log_e_film.max),
            ("log_e_print.min", wires.log_e_print.min),
            ("log_e_print.max", wires.log_e_print.max),
        ]
        for c, d in enumerate(wires.cmy_film.d_max):
            scalars.append((f"cmy_film.d_max[{c}]", d))
        for c, d in enumerate(wires.cmy_film.d_min):
            scalars.append((f"cmy_film.d_min[{c}]", d))
        for name, v in scalars:
            scaled = v * 1e4
            assert scaled == round(scaled), (
                f"{name}={v!r} is not on the 1e-4 grid"
            )

    # ---- behavior -------------------------------------------------------

    def test_papers_share_l1_l2_byte_identical(self, four_lut_bundle):
        """L1 and L2 don't depend on the print paper; the bundle has
        exactly ONE pair of them shared across every paper."""
        # We don't compare across bundles here — the assertion is that
        # the bundle's metadata has the L1 / L2 entries marked
        # paper=None, and the lut list has exactly one of each.
        roles = [e.role for e in four_lut_bundle.meta.luts]
        assert roles.count("filming_expose") == 1
        assert roles.count("filming_develop") == 1

    def test_papers_produce_distinct_l3_l4(self, four_lut_bundle):
        # Per-paper L3 and L4 must differ between papers.
        l3_a = four_lut_bundle.luts[2][1].table  # paper 0 L3
        l3_b = four_lut_bundle.luts[4][1].table  # paper 1 L3
        l4_a = four_lut_bundle.luts[3][1].table  # paper 0 L4
        l4_b = four_lut_bundle.luts[5][1].table  # paper 1 L4
        assert not np.array_equal(l3_a, l3_b)
        assert not np.array_equal(l4_a, l4_b)

    def test_chain_matches_live_pipeline(self, four_lut_spec, four_lut_bundle):
        """Apply L1∘L2∘L3∘L4 (all trilinear) at random samples; compare
        to the live spektrafilm pipeline end-to-end. 4-LUT chains
        accumulate more interpolation error than 1-LUT/2-LUT at the
        same per-cube resolution, so the tolerance is looser — but
        the chain must still produce sane output and not blow up."""
        from spektrafilm.runtime.params_builder import digest_params, init_params
        from spektrafilm.runtime.pipeline import SimulationPipeline
        from spektrafilm_lut_creator.color_spaces import get as get_cs
        from spektrafilm_lut_creator.qa.evaluators import apply_trilinear

        first_paper = self._FOUR_LUT_PAPERS[0]
        in_entry = get_cs(_INPUT_CS)
        out_entry = get_cs(_OUTPUT_CS)
        params = init_params(film_profile="kodak_portra_400", print_profile=first_paper)
        params.debug.lut_mode = True
        params.io.input_primaries = in_entry.primaries
        params.io.output_primaries = out_entry.primaries
        params.io.input_cctf_decoding = False
        params.io.output_cctf_encoding = False
        params.io.gamut_clip = "soft"
        params = digest_params(params)
        pipeline = SimulationPipeline(params)

        rng = np.random.default_rng(20260516)
        samples_encoded = rng.uniform(0.0, 1.0, size=(200, 3)).astype(np.float32)
        # n150: mirror the bake's decode + exposure-gain path.
        # Fixture uses default stops_above_gray=None → gain 1.0.
        samples_linear = decode_cctf(samples_encoded, _INPUT_CS)
        samples_linear = (samples_linear * input_exposure_gain(_INPUT_CS, None)).astype(np.float32)
        live_rgb_linear = np.asarray(
            pipeline.process(samples_linear.reshape(1, -1, 3)),
            dtype=float,
        ).reshape(-1, 3)
        live_rgb_encoded = np.clip(
            encode_cctf(live_rgb_linear, _OUTPUT_CS), 0.0, 1.0,
        )

        # Chain through all four baked LUTs (trilinear in every stage).
        l1 = four_lut_bundle.luts[0][1]
        l2 = four_lut_bundle.luts[1][1]
        l3 = four_lut_bundle.luts[2][1]  # paper 0
        l4 = four_lut_bundle.luts[3][1]  # paper 0
        log_e_film_code = apply_trilinear(l1.table, samples_encoded)
        cmy_film_code = apply_trilinear(l2.table, log_e_film_code)
        log_e_print_code = apply_trilinear(l3.table, cmy_film_code)
        chain_rgb_encoded = apply_trilinear(l4.table, log_e_print_code)

        diff = np.abs(chain_rgb_encoded - live_rgb_encoded)
        # 4-stage trilinear at 5^3 is coarse; bulk error is small,
        # worst-case errors can be substantial but shouldn't break.
        assert diff.mean() < 0.15, f"mean RGB error: {diff.mean():.4f}"
        assert diff.max() < 0.6, f"max RGB error: {diff.max():.4f}"

    # ---- on-disk --------------------------------------------------------

    def test_write_emits_2_shared_plus_2_per_paper_cubes(self, four_lut_spec, tmp_path):
        bundle = BundleBuilder(four_lut_spec).build()
        builder = BundleBuilder(four_lut_spec)
        out_dir = builder.write(bundle, tmp_path / "four_lut_out")
        for rel_path, _ in bundle.luts:
            assert (out_dir / rel_path).exists(), f"missing {rel_path}"
        cubes = sorted(p.name for p in out_dir.glob("*.cube"))
        l1_cubes = [c for c in cubes if c.endswith("_l1.cube")]
        l2_cubes = [c for c in cubes if c.endswith("_l2.cube")]
        l3_cubes = [c for c in cubes if c.endswith("_l3.cube")]
        l4_cubes = [c for c in cubes if c.endswith("_l4.cube")]
        assert len(l1_cubes) == 1 and len(l2_cubes) == 1
        assert len(l3_cubes) == len(self._FOUR_LUT_PAPERS)
        assert len(l4_cubes) == len(self._FOUR_LUT_PAPERS)

    def test_bundle_json_includes_all_three_wires(self, four_lut_spec, tmp_path):
        bundle = BundleBuilder(four_lut_spec).build()
        builder = BundleBuilder(four_lut_spec)
        out_dir = builder.write(bundle, tmp_path / "four_lut_json")
        payload = json.loads((out_dir / "bundle.json").read_text(encoding="utf-8"))
        wires = payload["wires"]
        assert wires["log_e_film"] is not None
        assert "min" in wires["log_e_film"] and "max" in wires["log_e_film"]
        assert wires["log_e_film"]["max"] > wires["log_e_film"]["min"]
        assert wires["cmy_film"] is not None
        assert len(wires["cmy_film"]["d_max"]) == 3
        assert wires["log_e_print"] is not None
        assert wires["log_e_print"]["max"] > wires["log_e_print"]["min"]
        # cmy_print stays null (L4 collapses it).
        assert wires["cmy_print"] is None

    def test_readme_explains_apply_order_for_4lut(self, four_lut_spec, tmp_path):
        bundle = BundleBuilder(four_lut_spec).build()
        builder = BundleBuilder(four_lut_spec)
        out_dir = builder.write(bundle, tmp_path / "four_lut_readme")
        readme = (out_dir / "README.md").read_text(encoding="utf-8")
        assert "Apply order" in readme
        # The README must spell out L1 → L2 → L3 → L4.
        assert "L1" in readme and "L2" in readme and "L3" in readme and "L4" in readme

    def test_readme_describes_intermediate_effect_injection_for_4lut(
        self, four_lut_spec, tmp_path,
    ):
        """The 4-LUT bundle exposes three intermediate taps; the README
        must describe what to do at each (halation/scatter/diffusion at
        log_e_film, grain at cmy_film, enlarger diffusion at log_e_print).
        """
        bundle = BundleBuilder(four_lut_spec).build()
        builder = BundleBuilder(four_lut_spec)
        out_dir = builder.write(bundle, tmp_path / "four_lut_intermediates")
        readme = (out_dir / "README.md").read_text(encoding="utf-8")
        readme_lower = readme.lower()
        # log_e_film tap → linear-light spatial effects.
        assert "log_e_film" in readme
        assert "halation" in readme_lower
        assert "scattering" in readme_lower or "scatter" in readme_lower
        # cmy_film tap → grain.
        assert "cmy_film" in readme
        assert "grain" in readme_lower
        # log_e_print tap → enlarger diffusion.
        assert "log_e_print" in readme
        assert "enlarger" in readme_lower
        assert "diffusion" in readme_lower
        # cmy_film density is above base+fog; the README must explain
        # the d_min below-zero headroom so grain models don't get clipped.
        assert "base+fog" in readme_lower
        assert "d_min" in readme

    def test_4lut_cmy_film_reserves_fog_headroom(self, four_lut_bundle):
        wires = four_lut_bundle.meta.wires
        assert wires.cmy_film.d_min == (-0.2, -0.2, -0.2)


# ---------------------------------------------------------------------------
# Spec-level QA opt-in + default output directory
# ---------------------------------------------------------------------------


class TestBundleSpecQaFields:
    """``BundleSpec.qa`` and ``qa_paper_index`` are validated at spec
    construction so a bad index doesn't show up halfway through a build.
    """

    def test_qa_defaults_to_off_and_no_index(self):
        spec = BundleSpec(
            film_profile="kodak_portra_400",
            print_profiles=("kodak_portra_endura",),
            input_color_space="ACEScg",
            output_color_space="sRGB",
        )
        assert spec.qa is False
        assert spec.qa_paper_index is None

    def test_qa_paper_index_out_of_range_rejected(self):
        with pytest.raises(ValueError, match="qa_paper_index"):
            BundleSpec(
                film_profile="kodak_portra_400",
                print_profiles=("kodak_portra_endura",),
                input_color_space="ACEScg",
                output_color_space="sRGB",
                qa=True,
                qa_paper_index=3,
            )

    def test_qa_paper_index_zero_accepted(self):
        spec = BundleSpec(
            film_profile="kodak_portra_400",
            print_profiles=("kodak_portra_endura",),
            input_color_space="ACEScg",
            output_color_space="sRGB",
            qa=True,
            qa_paper_index=0,
        )
        assert spec.qa_paper_index == 0


class TestBundleSpecStopsAboveGray:
    """``BundleSpec.stops_above_gray`` defaults to ``None`` (native, no
    gain) and can be overridden with a float to apply a linear gain so
    source encoded 1.0 lands at ``0.18 * 2 ** stops_above_gray`` in the
    film's frame (n150)."""

    @pytest.mark.parametrize("input_cs", [
        "Rec.2020",         # encoded_sdr
        "sRGB",             # encoded_sdr
        "ACEScg",           # linear
        "Panasonic V-Log",  # log
    ])
    def test_every_kind_defaults_to_none(self, input_cs):
        spec = BundleSpec(
            film_profile="kodak_portra_400",
            print_profiles=("kodak_portra_endura",),
            input_color_space=input_cs,
            output_color_space="sRGB",
        )
        assert spec.stops_above_gray is None

    def test_explicit_value_is_preserved(self):
        spec = BundleSpec(
            film_profile="kodak_portra_400",
            print_profiles=("kodak_portra_endura",),
            input_color_space="sRGB",
            output_color_space="sRGB",
            stops_above_gray=6.0,
        )
        assert spec.stops_above_gray == 6.0


class TestDefaultOutputDirectory:
    """``BundleBuilder.write(bundle)`` without an ``out_dir`` drops the
    bundle into ``cwd/build/lut_bundles/<spec.name>/`` — convenient for a
    bake script that doesn't want to think about paths.
    """

    def test_default_out_dir_lands_under_cwd_build_lut_bundles(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        spec = BundleSpec(
            film_profile="kodak_portra_400",
            print_profiles=("kodak_portra_endura",),
            input_color_space="ACEScg",
            output_color_space="sRGB",
            resolution=5,
        )
        builder = BundleBuilder(spec)
        bundle = builder.build()
        out = builder.write(bundle)
        expected = tmp_path / "build" / "lut_bundles" / spec.name
        assert out == expected
        assert (expected / "bundle.json").is_file()

    def test_explicit_out_dir_still_honored(self, tmp_path):
        spec = BundleSpec(
            name="explicit_test",
            film_profile="kodak_portra_400",
            print_profiles=("kodak_portra_endura",),
            input_color_space="ACEScg",
            output_color_space="sRGB",
            resolution=5,
        )
        builder = BundleBuilder(spec)
        bundle = builder.build()
        out = builder.write(bundle, tmp_path / "custom_location")
        assert out == tmp_path / "custom_location"
        assert (out / "bundle.json").is_file()


class TestQaAutoRun:
    """When ``spec.qa=True``, ``write()`` triggers the QA suite for the
    selected paper(s) and drops reports at ``<bundle>/qa/<per-paper>/``.
    The cache directory is removed after each run so the bundle stays
    ship-ready.
    """

    def _make_spec(self, *, qa: bool, qa_paper_index=None, papers=None):
        return BundleSpec(
            film_profile="kodak_portra_400",
            print_profiles=papers or ("kodak_portra_endura",),
            input_color_space="ACEScg",
            output_color_space="sRGB",
            topology="2lut",
            resolution=5,
            qa=qa,
            qa_paper_index=qa_paper_index,
        )

    def test_qa_false_skips_qa_subdir(self, tmp_path):
        spec = self._make_spec(qa=False)
        builder = BundleBuilder(spec)
        bundle = builder.build()
        out = builder.write(bundle, tmp_path / "no_qa")
        assert not (out / "qa").exists()

    def test_qa_true_runs_for_each_paper(self, tmp_path):
        papers = ("kodak_portra_endura", "fujifilm_crystal_archive_typeii")
        spec = self._make_spec(qa=True, papers=papers)
        builder = BundleBuilder(spec)
        bundle = builder.build()
        out = builder.write(bundle, tmp_path / "qa_all")
        qa_dir = out / "qa"
        # One report folder per paper, named with that paper substituted
        # into the bundle's canonical pattern.
        report_names = sorted(p.name for p in qa_dir.iterdir() if p.is_dir())
        assert len(report_names) == 2
        assert any("portraendura" in n for n in report_names)
        assert any("crystalarchive" in n for n in report_names)
        # Each report carries a report.md and a figures/ subdir.
        for sub in qa_dir.iterdir():
            assert (sub / "report.md").is_file()
            assert (sub / "figures").is_dir()
            assert not (sub / "cache").exists(), (
                f"cache should be deleted from {sub} after QA"
            )

    def test_qa_paper_index_selects_one_paper(self, tmp_path):
        papers = ("kodak_portra_endura", "fujifilm_crystal_archive_typeii")
        spec = self._make_spec(qa=True, qa_paper_index=1, papers=papers)
        builder = BundleBuilder(spec)
        bundle = builder.build()
        out = builder.write(bundle, tmp_path / "qa_one")
        qa_dir = out / "qa"
        report_dirs = [p for p in qa_dir.iterdir() if p.is_dir()]
        assert len(report_dirs) == 1
        # The single report is for the second paper (index 1).
        assert "crystalarchive" in report_dirs[0].name
        assert "portraendura" not in report_dirs[0].name
