"""Fixed contracts for independent native prepared execution.

Host-only graph/RNG checks are not reported as GPU evidence. macOS must build
and execute the shipping Metal library; a missing device is never a pass/skip.
"""
from concurrent.futures import ThreadPoolExecutor
import ctypes as ct
from dataclasses import FrozenInstanceError
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
import pytest

from spektrafilm.gpu.native_metal import NativeMetalSpatial
from spektrafilm.gpu.native_metal.build import build
from spektrafilm.gpu.native_metal.executor import NativeExecutor, NativeSession
from spektrafilm.gpu.native_metal.program import (
    AFFINE, EXP10, GRAIN, LOG10, Builder, Node, Program, pairs, prepare_spatial,
    prepare_grain, prepare_development,
)

ATOL = RTOL = 1e-6
ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src/spektrafilm/gpu/native_metal"
# Published Philox4x32-10 known-answer vectors, not a self-generated oracle:
# DEShawResearch/random123 tests/kat_vectors (zero, all-one, digits-of-pi).
KATS = (
    ((0, 0, 0, 0), (0, 0), (0x6627e8d5, 0xe169c58d, 0xbc57ac4c, 0x9b00dbd8)),
    ((0xFFFFFFFF,) * 4, (0xFFFFFFFF,) * 2, (0x408f276d, 0x41c83b0e, 0xa20bc7c6, 0x6d5451fd)),
    ((0x243f6a88, 0x85a308d3, 0x13198a2e, 0x03707344), (0xa4093822, 0x299f31d0),
     (0xd16cfe09, 0x94fdcceb, 0x5001e420, 0x24126ea1)),
)


def test_host_philox_published_vectors(tmp_path):
    compiler = shutil.which("clang++") or shutil.which("g++")
    assert compiler, "host RNG validation requires a C++ compiler"
    library = tmp_path / ("philox.dylib" if sys.platform == "darwin" else "philox.so")
    subprocess.run([compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
                    "-I", str(SOURCE), str(Path(__file__).with_name("philox_probe.cpp")), "-o", str(library)], check=True)
    lib = ct.CDLL(str(library))
    lib.sfm_philox_host.argtypes = [ct.POINTER(ct.c_uint32), ct.POINTER(ct.c_uint32)]
    lib.sfm_philox_host.restype = None
    for counter, key, expected in KATS:
        out = (ct.c_uint32 * 4)()
        lib.sfm_philox_host((ct.c_uint32 * 6)(*counter, *key), out)
        assert tuple(out) == expected


def test_liveness_reuses_only_dead_slots_and_interns_constants():
    b = Builder()
    current = 0
    for _ in range(100):
        current = b.affine(current, 2, 0.25)
    compiled = b.finish().compile()
    assert compiled.slots == 3
    assert len(compiled.constants) == 12
    assert not compiled.operations.flags.writeable
    for row in compiled.operations:
        assert row[1] != row[3]
    live = b.finish()
    b.affine(0, 99)  # unreachable; must not change compilation or fingerprint
    assert b.finish(current).compile().fingerprint == live.compile().fingerprint


def test_branch_liveness_and_exact_constant_fingerprint():
    b = Builder()
    left = b.affine(0, 2)
    right = b.affine(0, 3)
    total = b.mix(left, right)
    compiled = b.finish(total).compile()
    assert compiled.slots == 4
    assert compiled.operations[-1, 1] != compiled.operations[-1, 2]
    other = Builder()
    other.affine(0, 2 + 1e-9)
    assert other.finish().compile().fingerprint != affine_program(2).compile().fingerprint


def affine_program(scale):
    b = Builder()
    b.affine(0, scale)
    return b.finish()


def test_program_copies_inputs_and_rejects_forward_edges():
    constants, inputs = list(pairs([1] * 3 + [0] * 3)), [0]
    node = Node(AFFINE, inputs, constants)
    before = Program(3, [node], 1).compile().fingerprint
    constants[0], inputs[0] = 77, 99
    assert Program(3, [node], 1).compile().fingerprint == before
    with pytest.raises(FrozenInstanceError):
        node.constants = ()
    with pytest.raises(ValueError):
        Program(3, [Node(AFFINE, (1,), ())], 1)
    for bad in (True, -1, 5, 3.5):
        with pytest.raises(ValueError):
            Builder(bad)


def test_spectral_nan_policy_drops_band_not_individual_dye():
    b = Builder()
    dyes = np.ones((5, 3))
    dyes[2, 1] = np.nan
    b.spectral(0, dyes, np.ones(5), np.ones(5), np.ones((5, 3)))
    table = np.array(b.nodes[0].constants).reshape(5, 8, 2).sum(axis=2)
    np.testing.assert_array_equal(table[2], 0)
    np.testing.assert_array_equal(table[1], 1)


@pytest.fixture(scope="session")
def prepared_bundle(tmp_path_factory):
    if sys.platform != "darwin":
        pytest.skip("actual Metal requires macOS; graph/RNG host checks are separate")
    return build(tmp_path_factory.mktemp("prepared-executor"))


@pytest.fixture
def engine(prepared_bundle):
    with NativeExecutor(prepared_bundle) as value:
        yield value


def run_numpy(engine, program, image):
    with engine.prepare(program) as prepared, engine.upload(image) as source:
        output, stats = engine.run(prepared, source)
        with output:
            assert stats.submissions == 1 and stats.upload_bytes == 0 and stats.readback_bytes == 4
            return output.numpy(), stats


@pytest.mark.parametrize("counter,key,expected", KATS)
def test_actual_metal_philox(engine, counter, key, expected):
    assert engine.philox_words(counter, key) == expected


@pytest.mark.parametrize("shape", ((1, 1, 3), (1, 71, 3), (71, 1, 3), (131, 257, 3), (4, 8192, 3), (8192, 4, 3)))
@pytest.mark.parametrize("sigma", ((0, 0.75, 130), (2.9999, 3, 256)))
def test_actual_transpose_matches_existing_native_and_cpu(engine, prepared_bundle, shape, sigma):
    from spektrafilm.utils.fast_gaussian_filter import fast_gaussian_filter
    image = np.random.default_rng(171).uniform(-2, 16, shape).astype(np.float32)
    b = Builder()
    b.gaussian(0, sigma)
    actual, _ = run_numpy(engine, b.finish(), image)
    with NativeMetalSpatial(prepared_bundle) as previous:
        expected = previous.gaussian(image, sigma)
    np.testing.assert_array_equal(actual.view(np.uint32), expected.view(np.uint32))
    for dtype in (np.float32, np.float64):
        np.testing.assert_allclose(actual, fast_gaussian_filter(image.astype(dtype), sigma), atol=ATOL, rtol=RTOL)


def test_actual_device_branching_curves_and_spectral(engine):
    image = np.random.default_rng(17).uniform(0, 2, (89, 127, 3)).astype(np.float32)
    b = Builder()
    a, c = b.affine(0, (1, 2, 3), 0.1), b.affine(0, (3, 2, 1), -0.1)
    mixed = b.mix(a, c, 0.25, 0.75)
    x = np.array((0, 0.5, 0.5, 1, 4, 8))
    y = np.repeat((x * x)[:, None], 3, axis=1)
    curve = b.curve(mixed, x, y)
    actual, _ = run_numpy(engine, b.finish(curve), image)
    expected = image.astype(float) * (np.array((1, 2, 3))*0.25 + np.array((3, 2, 1))*0.75) - 0.05
    expected = np.stack([np.interp(expected[..., ch], x, y[:, ch]) for ch in range(3)], -1)
    np.testing.assert_allclose(actual, expected, atol=ATOL, rtol=RTOL)
    dyes = np.random.default_rng(18).uniform(0, 0.1, (81, 3));dyes[3, 1] = np.nan
    base = np.full(81, 0.1);illum = np.full(81, 0.02);sensitivity = np.ones((81, 3))
    s = Builder();s.spectral(0, dyes, base, illum, sensitivity)
    got, _ = run_numpy(engine, s.finish(), image)
    density = np.einsum("...c,kc->...k", image.astype(float), dyes) + base
    transmitted = np.nan_to_num(10**(-density) * illum, nan=0)
    expected = np.einsum("...k,kc->...c", transmitted, sensitivity)
    np.testing.assert_allclose(got, expected, atol=ATOL, rtol=RTOL)


def test_actual_complete_serial_halation(engine):
    from spektrafilm.utils.fast_gaussian_filter import fast_gaussian_filter
    from spektrafilm.model.diffusion import apply_halation_um
    from spektrafilm.runtime.params_schema import HalationParams
    halation = HalationParams()
    halation.active = True
    image = np.random.default_rng(19).uniform(0, 4, (131, 257, 3)).astype(np.float32)
    program = prepare_spatial(halation, 10, lens_blur_um=8)
    actual, stats = run_numpy(engine, program, image)
    expected = apply_halation_um(fast_gaussian_filter(image.astype(np.float64), 0.8), halation, 10)
    np.testing.assert_allclose(actual, expected, atol=ATOL, rtol=RTOL)
    assert stats.dispatches > 6  # whole chain, not a single Gaussian
    assert program.compile().slots < len(program.nodes)


def grain_program(particles=100, uniformity=0.98, *, seed=17, origin=0):
    b = Builder()
    axis = np.repeat(np.array((0., 3.))[:, None], 3, axis=1)
    curves = np.repeat((axis/3)[:, None, :], 3, axis=1)
    params = np.tile((0., 1., particles, uniformity), (3, 3, 1))
    b.add(GRAIN, (0,), pairs(np.r_[axis.ravel(), curves.ravel(), params.ravel()]),
          (2, 0, seed & 0xFFFFFFFF, seed >> 32, 0, origin & 0xFFFFFFFF, origin >> 32, 0))
    return b.finish()


@pytest.mark.parametrize("p,particles,u", ((.02, 100, .98), (.3, 100, .98), (.8, 100, .98), (.3, 10, 0), (.5, 2000, 0)))
def test_actual_poisson_thinning_moments_and_correlations(engine, p, particles, u):
    # Predeclared seven-standard-error sampling bars; no observed-data retuning.
    size = 512
    image = np.full((size, size, 3), 3*p, np.float32)
    actual, _ = run_numpy(engine, grain_program(particles, u), image)
    saturation = 1 - p*u*(1-1e-6)
    rate = 3*particles*p/saturation
    scale = saturation/particles
    expected_mean, expected_var = rate*scale, rate*scale**2
    flat = actual.reshape(-1, 3).astype(float)
    n = len(flat)
    for ch in range(3):
        values = flat[:, ch];mean = values.mean();var = values.var()
        assert abs(mean-expected_mean) <= 7*np.sqrt(expected_var/n)
        assert abs(var/expected_var-1) <= 7*np.sqrt((2+1/rate)/n)
        skew = np.mean((values-mean)**3)/var**1.5
        assert abs(skew-1/np.sqrt(rate)) <= 7*np.sqrt((6+18/rate+1/rate**2)/n)
    correlation = np.corrcoef(flat.T)
    assert np.max(np.abs(correlation-np.eye(3))) < 0.015
    for offset in (1, 512):
        assert abs(np.corrcoef(flat[:-offset, 0], flat[offset:, 0])[0, 1]) < 0.015
    power = np.abs(np.fft.rfft2(actual[..., 0]-actual[..., 0].mean()))**2
    low = power[1:128, 1:128].mean();high = power[256:384, 128:256].mean()
    assert 0.9 < low/high < 1.1


def test_actual_grain_global_counter_tiling_and_repeatability(engine):
    image = np.full((64, 73, 3), .6, np.float32)
    origin = 2**32 - 4096;seed = 2**64 - 7
    whole, _ = run_numpy(engine, grain_program(seed=seed, origin=origin), image)
    first, _ = run_numpy(engine, grain_program(seed=seed, origin=origin), image[:32].copy())
    second, _ = run_numpy(engine, grain_program(seed=seed, origin=origin+32*73), image[32:].copy())
    np.testing.assert_array_equal(whole.view(np.uint32), np.concatenate((first, second)).view(np.uint32))
    again, _ = run_numpy(engine, grain_program(seed=seed, origin=origin), image)
    np.testing.assert_array_equal(whole, again)


def test_actual_residency_cache_transactions_and_immutable_outputs(engine):
    image = np.full((71, 83, 3), .2, np.float32)
    good, bad = Builder(), Builder()
    good.affine(0, 2, 0.1)
    bad.add(EXP10, (bad.affine(0, 0, 100),))
    changed = Builder();changed.affine(0, 3, 0.1)
    with engine.prepare(good.finish()) as film, engine.prepare(good.finish()) as print_program, \
            engine.prepare(changed.finish()) as other, engine.prepare(bad.finish()) as invalid, NativeSession(engine, image) as session:
        first, _ = session.render(film, print_program)
        with first:
            saved = first.numpy()
            for _ in range(8):
                output, stats = session.render(film, print_program)
                with output:
                    np.testing.assert_array_equal(output.numpy(), saved)
                    assert stats.upload_bytes == 0
            assert session.film_runs == 1 and session.cache_hits == 8
            with pytest.raises(RuntimeError, match="rejected"):
                session.render(other, invalid)
            output, _ = session.render(film, print_program)
            with output:
                np.testing.assert_array_equal(output.numpy(), saved)
            assert session.film_runs == 2  # failed print did not replace old negative
            session.set_source(np.full_like(image, .4))
            output, _ = session.render(film, print_program)
            with output:
                assert not np.array_equal(output.numpy(), saved)
            engine.trim()
            np.testing.assert_array_equal(first.numpy(), saved)
    engine.trim()
    assert engine.statistics.allocated_bytes == 0


def test_actual_handle_close_cross_executor_budget_and_concurrency(engine, prepared_bundle):
    image = np.ones((31, 43, 3), np.float32)
    b = Builder();b.gaussian(0, (1, 3, 20))
    with engine.prepare(b.finish()) as p, engine.upload(image) as source:
        def render(_):
            out, _ = engine.run(p, source)
            with out:
                return out.numpy()
        with ThreadPoolExecutor(3) as pool:
            results = list(pool.map(render, range(6)))
        for result in results:
            np.testing.assert_array_equal(result, results[0])
        with NativeExecutor(prepared_bundle) as other:
            with pytest.raises(ValueError, match="another"):
                other.run(p, source)
        with NativeExecutor(prepared_bundle, max_resident_bytes=64) as small:
            with pytest.raises(RuntimeError, match="budget"):
                small.upload(image)
            with small.upload(np.ones((1, 1), np.float32)) as tiny:
                np.testing.assert_array_equal(tiny.numpy(), 1)
    with pytest.raises(RuntimeError, match="closed"):
        source.numpy()


def test_actual_texture_lease_is_not_recycled_with_image(engine):
    image = np.random.default_rng(401).uniform(-2, 16, (67, 73, 3)).astype(np.float32)
    resident = engine.upload(image)
    lease = resident.texture()
    assert lease.handle
    expected = np.concatenate((image, np.ones((*image.shape[:2], 1), np.float32)), -1)
    np.testing.assert_array_equal(lease.numpy().view(np.uint32), expected.view(np.uint32))
    occupied = engine.statistics.allocated_bytes
    resident.close();engine.trim()
    assert 0 < engine.statistics.allocated_bytes < occupied
    pointer = lease.handle
    for _ in range(4):
        with engine.upload(image*2):
            assert lease.handle == pointer
    np.testing.assert_array_equal(lease.numpy(), expected)
    lease.close();engine.trim()
    assert engine.statistics.allocated_bytes == 0
    with pytest.raises(RuntimeError, match="closed"):
        _ = lease.handle


def test_actual_malformed_prepared_data_fails_without_poisoning(engine):
    for program in (
        Program(3, (Node(AFFINE, (0,), ()),), 1),
        Program(3, (Node(4, (0,), tuple(pairs([1]*12)), (0,)),), 1),
        Program(3, (Node(1, (0,), (), (2, 0, 123)*3),), 1),
    ):
        with pytest.raises(RuntimeError):
            engine.prepare(program)
    image = np.ones((3, 5, 3), np.float32)
    got, _ = run_numpy(engine, Program(3, (), 0), image)
    np.testing.assert_array_equal(got, image)


def test_actual_poisson_domain_failure_is_not_a_normal_fallback(engine):
    image = np.full((11, 13, 3), 2.99, np.float32)
    with pytest.raises(RuntimeError, match="rejected"):
        run_numpy(engine, grain_program(1e8, .99999), image)
    got, _ = run_numpy(engine, grain_program(), image)
    assert np.isfinite(got).all()


@pytest.mark.parametrize("sigma", ((0, 0.75, 130), (2.9, 3, 20)))
def test_actual_fused_gaussian_accumulation_preserves_values(engine, sigma):
    image = np.random.default_rng(713).uniform(-2, 16, (137, 259, 3)).astype(np.float32)
    unfused, fused = Builder(), Builder()
    acc = unfused.affine(0, .5, -.1)
    gauss = unfused.gaussian(0, sigma)
    unfused.mix(acc, gauss, (1, 2, 3), (.1, .3, .7))
    acc = fused.affine(0, .5, -.1)
    fused.gaussian_mix(0, acc, sigma, (1, 2, 3), (.1, .3, .7))
    expected, plain_stats = run_numpy(engine, unfused.finish(), image)
    actual, fused_stats = run_numpy(engine, fused.finish(), image)
    np.testing.assert_array_equal(actual.view(np.uint32), expected.view(np.uint32))
    assert fused_stats.dispatches == plain_stats.dispatches-1
    assert fused.finish().compile().slots < unfused.finish().compile().slots


@pytest.mark.parametrize("stock", ("kodak_portra_400", "fujifilm_provia_100f"))
@pytest.mark.parametrize("spatial", (False, True))
def test_actual_real_profile_development_against_cpu(engine, stock, spatial):
    from spektrafilm.profiles.io import load_profile
    from spektrafilm.model.develop import develop
    from spektrafilm.runtime.params_schema import GrainParams, DirCouplersParams
    profile = load_profile(stock)
    grain, couplers = GrainParams(active=False), DirCouplersParams()
    if not spatial:
        couplers.diffusion_size_um = 0
    image = np.random.default_rng(731).uniform(-2, 2, (71, 97, 3)).astype(np.float32)
    data = profile.data
    positive = profile.info.type == "positive"
    program = prepare_development(data.log_exposure, data.density_curves, data.density_curves_layers,
                                  couplers, grain, 10, positive=positive)
    actual, _ = run_numpy(engine, program, image)
    reference = develop(image.astype(np.float64), 10, data.log_exposure, data.density_curves,
                        data.density_curves_layers, couplers, grain, profile.info.type)
    np.testing.assert_allclose(actual, reference, atol=ATOL, rtol=RTOL)


@pytest.mark.parametrize("layered", (False, True))
def test_actual_real_profile_grain_variants_are_finite_and_repeatable(engine, layered):
    from spektrafilm.profiles.io import load_profile
    from spektrafilm.runtime.params_schema import GrainParams
    p = load_profile("kodak_portra_400")
    curves = p.data.density_curves-np.min(p.data.density_curves, axis=0)
    grain = GrainParams(sublayers_active=layered, n_sub_layers=4)
    # Exercise non-delta dye blur and per-channel microstructure, not only defaults.
    grain.blur_dye_clouds_um = 8
    grain.micro_structure = (8, 800)
    image = np.full((193, 257, 3), .8, np.float32)
    program = prepare_grain(curves, p.data.density_curves_layers, grain, 5, seed=987)
    first, _ = run_numpy(engine, program, image)
    second, _ = run_numpy(engine, program, image)
    np.testing.assert_array_equal(first.view(np.uint32), second.view(np.uint32))
    assert np.isfinite(first).all()
    np.testing.assert_allclose(first.mean(axis=(0, 1)), (.8, .8, .8), atol=.015, rtol=0)


def test_actual_microstructure_channels_are_independent(engine):
    from spektrafilm.gpu.native_metal.program import LOGNORMAL
    b = Builder()
    b.add(LOGNORMAL, (0,), pairs([.3]), (0, 0, 171, 0, 9, 0, 0))
    actual, _ = run_numpy(engine, b.finish(), np.zeros((512, 512, 3), np.float32))
    correlation = np.corrcoef(actual.reshape(-1, 3).T)
    assert np.max(np.abs(correlation-np.eye(3))) < .015
    np.testing.assert_allclose(actual.mean(axis=(0, 1)), 1, atol=.007, rtol=0)


def test_actual_scalar_chain_is_not_cpu_fallback(engine):
    image = np.random.default_rng(723).uniform(.01, 8, (193, 257, 3)).astype(np.float32)
    b = Builder();first = b.add(LOG10, (0,));b.add(EXP10, (first,))
    actual, stats = run_numpy(engine, b.finish(), image)
    np.testing.assert_allclose(actual, image, atol=ATOL, rtol=RTOL)
    assert stats.dispatches == 3 and stats.submissions == 1
