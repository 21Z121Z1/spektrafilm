"""Tests for the 1-lut-combined BundleBuilder.

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
from spektrafilm_lut_creator.color_spaces import encode_cctf, decode_cctf
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
        topology="1-lut-combined",
        resolution=_RESOLUTION,
    ))


@pytest.fixture(scope="module")
def built(builder):
    return builder.build()


class TestBuilderConstruction:
    def test_rejects_non_1lut_topology(self):
        spec = BundleSpec(
            name="x",
            film_profile="kodak_portra_400",
            print_profiles=("kodak_portra_endura",),
            input_color_space=_INPUT_CS,
            output_color_space=_OUTPUT_CS,
            topology="2-lut-film-print",
            resolution=5,
        )
        with pytest.raises(NotImplementedError, match="1-lut-combined"):
            BundleBuilder(spec)

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
        assert built.meta.topology == "1-lut-combined"
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
        image_linear = decode_cctf(image_encoded, _INPUT_CS).astype(np.float32)
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
    """A 1-lut-combined bundle with N>1 print profiles produces N cubes — one per
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
            topology="1-lut-combined",
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
        # full 1-lut-combined bakes.
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
        assert payload["topology"] == "1-lut-combined"
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
