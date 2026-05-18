"""Tests for the OCIO 2 config emission (M8a).

Three layers of validation, in order of importance:

1. **PyOpenColorIO load** — the emitted ``config.ocio`` must parse and
   instantiate without errors. Catches syntax bugs immediately.
2. **Colorspace path resolution** — OCIO can build a processor from
   ACES2065-1 to the spektrafilm colorspace, and the processor produces
   finite output on a sampled grid.
3. **Cube-application consistency** — the named colorspace path
   (ACES2065-1 -> spektrafilm_<film>_<paper>) produces the same numbers
   as the equivalent explicit transform chain (AP0 -> input encoded ->
   apply .cube directly), confirming OCIO is composing the steps the
   way the emitter intends.

The bundle build itself is the most expensive step; a module-scoped
fixture builds one tiny ACEScg -> sRGB bundle and writes it to disk
under ``tmp_path_factory``, so every assertion in this file shares it.

See ``studies/a40_lut_system/n120_ocio_config_emission.md``.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from spektrafilm_lut_creator import ocio_emit
from spektrafilm_lut_creator.builders import BundleBuilder
from spektrafilm_lut_creator.bundles import BundleSpec


pytest.importorskip(
    "PyOpenColorIO",
    reason="PyOpenColorIO required for OCIO config validation tests; "
           "install with `pip install opencolorio`.",
)


_RESOLUTION = 5
_FILM = "kodak_portra_400"
_PAPER = "kodak_portra_endura"
_INPUT_CS = "ACEScg"
_OUTPUT_CS = "sRGB"


# ---------------------------------------------------------------------------
# Pure-function tests (no bundle build).
# ---------------------------------------------------------------------------

class TestSupportedPredicate:
    def _spec(self, **overrides) -> BundleSpec:
        defaults = dict(
            name="t",
            film_profile=_FILM,
            print_profiles=(_PAPER,),
            input_color_space=_INPUT_CS,
            output_color_space=_OUTPUT_CS,
            topology="1lut",
            resolution=5,
        )
        defaults.update(overrides)
        return BundleSpec(**defaults)

    def test_supported_for_1lut_acescg_to_srgb(self):
        assert ocio_emit.is_supported(self._spec())
        assert ocio_emit.unsupported_reason(self._spec()) == ""

    def test_unsupported_for_2lut(self):
        spec = self._spec(topology="2lut")
        assert not ocio_emit.is_supported(spec)
        assert "M8b" in ocio_emit.unsupported_reason(spec)

    def test_unsupported_for_unknown_output(self):
        spec = self._spec(output_color_space="Rec.2020")  # not in _OUTPUT_BUILTIN
        assert not ocio_emit.is_supported(spec)
        msg = ocio_emit.unsupported_reason(spec)
        assert "Rec.2020" in msg
        assert "supported outputs" in msg.lower()

    def test_emit_raises_for_unsupported(self):
        spec = self._spec(topology="2lut")
        # bundle arg is unused before the topology check; pass a placeholder.
        with pytest.raises(NotImplementedError, match="M8b"):
            ocio_emit.emit_ocio_config(bundle=None, spec=spec)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Bundle-based fixtures.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def written_bundle(tmp_path_factory) -> tuple[Path, BundleSpec, "Bundle"]:
    """Build and write one tiny 1-LUT bundle. Used by every test below."""
    from spektrafilm_lut_creator.bundles import Bundle  # noqa: F401 (typing)

    spec = BundleSpec(
        name="ocio_emit_fixture",
        film_profile=_FILM,
        print_profiles=(_PAPER,),
        input_color_space=_INPUT_CS,
        output_color_space=_OUTPUT_CS,
        topology="1lut",
        resolution=_RESOLUTION,
    )
    builder = BundleBuilder(spec)
    bundle = builder.build()
    out_dir = tmp_path_factory.mktemp("ocio_bundle")
    builder.write(bundle, out_dir / spec.name)
    return (out_dir / spec.name), spec, bundle


# ---------------------------------------------------------------------------
# Validation tests.
# ---------------------------------------------------------------------------

class TestConfigOnDisk:
    def test_config_ocio_written(self, written_bundle):
        bundle_dir, _spec, _bundle = written_bundle
        config_path = bundle_dir / "config.ocio"
        assert config_path.is_file()
        text = config_path.read_text(encoding="utf-8")
        assert "ocio_profile_version: 2.4" in text
        assert "spektrafilm_portra400_portraendura" in text
        assert "search_path: ." in text

    def test_emit_ocio_false_skips_emission(self, tmp_path):
        spec = BundleSpec(
            name="no_ocio",
            film_profile=_FILM,
            print_profiles=(_PAPER,),
            input_color_space=_INPUT_CS,
            output_color_space=_OUTPUT_CS,
            topology="1lut",
            resolution=_RESOLUTION,
            emit_ocio=False,
        )
        builder = BundleBuilder(spec)
        bundle = builder.build()
        out_dir = builder.write(bundle, tmp_path / spec.name)
        assert not (out_dir / "config.ocio").exists()


class TestConfigLoad:
    """The headline test: OCIO must accept the file."""

    def test_pyopencolorio_loads_config(self, written_bundle):
        import PyOpenColorIO as ocio

        bundle_dir, _spec, _bundle = written_bundle
        config = ocio.Config.CreateFromFile(str(bundle_dir / "config.ocio"))
        # Calling validate() raises if the config is malformed.
        config.validate()

    def test_config_declares_expected_colorspaces(self, written_bundle):
        import PyOpenColorIO as ocio

        bundle_dir, _spec, _bundle = written_bundle
        config = ocio.Config.CreateFromFile(str(bundle_dir / "config.ocio"))
        names = {cs.getName() for cs in config.getColorSpaces()}
        assert "ACES2065-1" in names
        assert _INPUT_CS in names
        assert _OUTPUT_CS in names
        assert "spektrafilm_portra400_portraendura" in names

    def test_aces_interchange_role_set(self, written_bundle):
        import PyOpenColorIO as ocio

        bundle_dir, _spec, _bundle = written_bundle
        config = ocio.Config.CreateFromFile(str(bundle_dir / "config.ocio"))
        assert config.getRoleColorSpace("aces_interchange") == "ACES2065-1"
        assert config.getRoleColorSpace("scene_linear") == "ACES2065-1"


class TestProcessorEvaluation:
    """The spektrafilm colorspace path resolves to a finite-output processor."""

    def test_processor_from_ap0_to_spektrafilm_produces_finite_output(self, written_bundle):
        import PyOpenColorIO as ocio

        bundle_dir, _spec, _bundle = written_bundle
        config = ocio.Config.CreateFromFile(str(bundle_dir / "config.ocio"))
        proc = config.getProcessor(
            "ACES2065-1", "spektrafilm_portra400_portraendura"
        )
        cpu = proc.getDefaultCPUProcessor()
        rng = np.random.default_rng(seed=0)
        samples = rng.uniform(0.0, 1.0, size=(64, 3)).astype(np.float32)
        out = samples.copy()
        cpu.applyRGB(out)
        assert np.all(np.isfinite(out)), "processor produced non-finite values"


class TestCubeApplicationConsistency:
    """Compositional check: the named colorspace path (AP0 -> spektrafilm)
    equals the explicit transform chain it represents (AP0 -> input -> .cube).

    This catches emitter bugs that would cause OCIO to silently chain the
    transforms in an unexpected order, or omit a stage."""

    def test_named_path_matches_explicit_chain(self, written_bundle):
        import PyOpenColorIO as ocio

        bundle_dir, _spec, bundle = written_bundle
        config = ocio.Config.CreateFromFile(str(bundle_dir / "config.ocio"))

        # Path A: the named colorspace path via the config.
        proc_named = config.getProcessor(
            "ACES2065-1", "spektrafilm_portra400_portraendura"
        ).getDefaultCPUProcessor()

        # Path B: the explicit GroupTransform that the spektrafilm
        # colorspace's from_scene_reference encodes inline.
        lut_relpath = bundle.luts[0][0]
        group = ocio.GroupTransform()
        group.appendTransform(ocio.ColorSpaceTransform(
            src="ACES2065-1", dst=_INPUT_CS,
        ))
        group.appendTransform(ocio.FileTransform(
            src=str(bundle_dir / lut_relpath),
            interpolation=ocio.INTERP_TETRAHEDRAL,
        ))
        proc_explicit = config.getProcessor(group).getDefaultCPUProcessor()

        # Apply both processors to a moderately-sized random grid in AP0.
        # AP0 values can extend outside [0, 1] in principle, but for this
        # consistency test any common input is fine — we're checking
        # numerical agreement between two paths through the same config.
        rng = np.random.default_rng(seed=42)
        samples = rng.uniform(0.0, 1.0, size=(256, 3)).astype(np.float32)

        out_named = samples.copy()
        proc_named.applyRGB(out_named)
        out_explicit = samples.copy()
        proc_explicit.applyRGB(out_explicit)

        # Both processors are evaluating the same underlying chain; the
        # only freedom OCIO has is in the order of internal precision
        # tricks, which should agree to float32 precision.
        np.testing.assert_allclose(out_named, out_explicit, atol=1e-6, rtol=1e-5)
