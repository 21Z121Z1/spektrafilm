"""Separate host-arithmetic evidence from actual native Metal evidence."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import ctypes as ct
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
import pytest

from spektrafilm.gpu.native_metal import (
    GaussianPlan, NativeMetalSpatial, _Channel, _check_bundle, _sha256, _validate_image,
    prepare_gaussian,
)
from spektrafilm.utils.fast_gaussian_filter import fast_gaussian_filter, _yvv_coeffs

ROOT = Path(__file__).resolve().parents[2]
SOURCES = ROOT / "src/spektrafilm/gpu/native_metal"
# Fixed before running either implementation. No per-case tolerance adjustment.
ATOL = RTOL = 1e-6
SIGMAS = (0.0, 0.2, 0.75, 2.9999, 3.0, 8.0, 20.0, 130.0, 256.0)
SHAPES = ((1, 1), (1, 29), (29, 1), (7, 11), (64, 65), (257, 263))


@pytest.fixture(scope="session")
def host(tmp_path_factory):
    compiler = shutil.which("clang++") or shutil.which("g++")
    assert compiler, "a C++ compiler is required for native arithmetic tests"
    root = tmp_path_factory.mktemp("native-host")
    library = root / ("probe.dylib" if sys.platform == "darwin" else "probe.so")
    subprocess.run([
        compiler, "-std=c++17", "-O2", "-fno-fast-math", "-ffp-contract=off",
        "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC", "-I", str(SOURCES),
        str(Path(__file__).with_name("host_probe.cpp")), "-o", str(library),
    ], check=True)
    lib = ct.CDLL(str(library))
    fp = ct.POINTER(ct.c_float)
    lib.sfm_host.argtypes = [fp, fp, ct.c_uint, ct.c_uint, ct.c_uint, ct.POINTER(_Channel), fp]
    lib.sfm_host.restype = None
    lib.sfm_host_probe.argtypes = []
    lib.sfm_host_probe.restype = ct.c_float
    assert lib.sfm_host_probe() == 1.0

    def run(image, sigma, truncate=3.0):
        h, w, c = _validate_image(image)
        plan = prepare_gaussian(sigma, c, truncate=truncate)
        entries = (_Channel * c)(*(_Channel(*entry) for entry in plan.entries))
        constants = np.asarray(plan.constants, dtype=np.float32)
        out = np.empty_like(image)
        lib.sfm_host(image.ctypes.data_as(fp), out.ctypes.data_as(fp), h, w, c,
                     entries, constants.ctypes.data_as(fp))
        return out
    return run


def check_reference(actual, image, sigma, truncate=3.0):
    # Two distinct references: CPU float32 storage and CPU float64 computation.
    for dtype in (np.float32, np.float64):
        expected = fast_gaussian_filter(image.astype(dtype), sigma, truncate=truncate)
        np.testing.assert_allclose(actual, expected, rtol=RTOL, atol=ATOL)
    assert actual.dtype == np.float32
    assert np.isfinite(actual).all()


@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("sigma", SIGMAS)
def test_host_arithmetic_against_cpu(host, shape, sigma):
    image = np.random.default_rng(19).uniform(-2, 16, (*shape, 3)).astype(np.float32)
    check_reference(host(image, sigma), image, sigma)


@pytest.mark.parametrize("sigma", (0.75, 3.0, 20.0, 130.0, 256.0))
@pytest.mark.parametrize("pattern", ("constant", "corner", "ramp", "checker"))
def test_host_spatial_patterns(host, sigma, pattern):
    h, w = 67, 131
    y, x = np.indices((h, w))
    if pattern == "constant": image = np.full((h, w), 0.184, np.float32)
    elif pattern == "corner":
        image = np.zeros((h, w), np.float32)
        image[0, 0] = 16
    elif pattern == "ramp": image = (x / w + y / h).astype(np.float32)
    else: image = ((x + y) % 2 * 2 - 1).astype(np.float32)
    check_reference(host(image, sigma), image, sigma)


@pytest.mark.parametrize("shape", ((4, 8192, 3), (8192, 4, 3)))
def test_host_long_recurrence_and_mixed_channels(host, shape):
    image = np.random.default_rng(21).uniform(-2, 16, shape).astype(np.float32)
    sigma = (0.0, 2.9, 130.0)
    out = host(image, sigma)
    check_reference(out, image, sigma)
    np.testing.assert_array_equal(out[..., 0].view(np.uint32), image[..., 0].view(np.uint32))


def test_plan_uses_cpu_coefficients_and_is_immutable():
    plan = prepare_gaussian([0, 0.75, 130], 3)
    assert [e[0] for e in plan.entries] == [0, 1, 2]
    offset = plan.entries[2][2]
    pairs = np.asarray(plan.constants[offset:]).reshape(-1, 2).sum(axis=1)
    np.testing.assert_allclose(pairs, _yvv_coeffs(130), rtol=1e-14, atol=1e-14)
    with pytest.raises(FrozenInstanceError):
        plan.constants = ()
    assert ct.sizeof(_Channel) == 12


def test_plan_copies_mutable_inputs():
    entries, constants = [[0, 0, 0]], [1.0, 0.0]
    plan = GaussianPlan(entries, constants)
    entries[0][0], constants[0] = 2, 99.0
    assert plan.entries == ((0, 0, 0),)
    assert plan.constants == (1.0, 0.0)


@pytest.mark.parametrize("damage", ("abi", "source", "artifact"))
def test_bundle_checks_reject_stale_or_damaged_files(tmp_path, damage):
    from spektrafilm.gpu.native_metal import ABI_VERSION, SOURCE_FILES
    artifacts = ("libsfm_spatial.dylib", "sfm_spatial.metallib")
    for name in artifacts:
        (tmp_path / name).write_bytes(b"test bundle, not executable")
    manifest = {
        "abi": ABI_VERSION,
        "sources": {name: _sha256(SOURCES / name) for name in SOURCE_FILES},
        "artifacts": {name: _sha256(tmp_path / name) for name in artifacts},
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    _check_bundle(tmp_path)
    if damage == "abi":
        manifest["abi"] += 1
    elif damage == "source":
        manifest["sources"][SOURCE_FILES[0]] = "stale"
    else:
        (tmp_path / artifacts[0]).write_bytes(b"corrupt")
    path.write_text(json.dumps(manifest))
    with pytest.raises(RuntimeError):
        _check_bundle(tmp_path)


@pytest.mark.parametrize("sigma,channels,truncate", [
    (float("nan"), 3, 3), (float("inf"), 3, 3), (257, 3, 3),
    ([1, 2], 3, 3), ([[1, 2, 3]], 3, 3), (1, 0, 3), (1, True, 3),
    (1, 3, -1), (1, 3, float("inf")), (2.9, 3, 100),
])
def test_invalid_plan_is_rejected(sigma, channels, truncate):
    with pytest.raises(ValueError): prepare_gaussian(sigma, channels, truncate=truncate)


@pytest.mark.parametrize("image", [
    np.zeros((3, 4), np.float64), np.zeros((0, 4), np.float32),
    np.zeros((4, 4), np.float32)[:, ::2], np.ones(4, np.float32),
    np.full((3, 4), np.nan, np.float32), np.zeros((3, 4, 5), np.float32),
])
def test_input_validation(image):
    with pytest.raises((ValueError, TypeError)): _validate_image(image)


def test_no_native_fallback_on_non_macos(tmp_path):
    if sys.platform != "darwin":
        with pytest.raises(RuntimeError, match="requires macOS"):
            NativeMetalSpatial(tmp_path)


@pytest.fixture(scope="session")
def metal_bundle(tmp_path_factory):
    if sys.platform != "darwin": pytest.skip("actual Metal requires macOS; host tests are separate")
    from spektrafilm.gpu.native_metal.build import build
    # A missing compiler/device or a parity failure on macOS is a FAILURE, never a skip.
    return build(tmp_path_factory.mktemp("native-metal-bundle"))


@pytest.mark.parametrize("sigma", SIGMAS)
def test_actual_metal_parity_and_determinism(metal_bundle, sigma):
    image = np.random.default_rng(23).uniform(-2, 16, (257, 263, 3)).astype(np.float32)
    with NativeMetalSpatial(metal_bundle) as engine:
        first, stats = engine.apply(image, prepare_gaussian(sigma, 3))
        second = engine.gaussian(image, sigma)
        check_reference(first, image, sigma)
        np.testing.assert_array_equal(first.view(np.uint32), second.view(np.uint32))
        assert stats.dispatches == (3 if sigma <= 0 else 6)
        assert stats.upload_bytes == stats.readback_bytes == image.nbytes
        assert stats.allocated_bytes < 3 * image.nbytes + 4096
        assert stats.synchronized_seconds > 0


@pytest.mark.parametrize("shape", ((1, 1, 3), (1, 29, 3), (29, 1, 3), (4, 8192, 3), (8192, 4, 3)))
def test_actual_metal_edges_and_mixed_channels(metal_bundle, shape):
    image = np.random.default_rng(24).uniform(-2, 16, shape).astype(np.float32)
    with NativeMetalSpatial(metal_bundle) as engine:
        check_reference(engine.gaussian(image, (0, 2.9, 130)), image, (0, 2.9, 130))


def test_actual_metal_budget_recovery_and_close(metal_bundle):
    engine = NativeMetalSpatial(metal_bundle, max_working_bytes=64)
    with pytest.raises(RuntimeError, match="budget"):
        engine.gaussian(np.ones((8, 8), np.float32), 0)
    image = np.array([[-0.0]], np.float32)
    out, stats = engine.apply(image, prepare_gaussian(0, 1))
    np.testing.assert_array_equal(out.view(np.uint32), image.view(np.uint32))
    assert stats.allocated_bytes <= 64
    engine.close()
    engine.close()
    with pytest.raises(RuntimeError, match="closed"): engine.gaussian(image, 0)


def test_actual_metal_reuse_resize_and_concurrency(metal_bundle):
    with NativeMetalSpatial(metal_bundle) as engine:
        image = np.random.default_rng(25).random((41, 53, 3), dtype=np.float32)
        out, first = engine.apply(image, prepare_gaussian((1, 3, 20), 3))
        saved = out.copy()
        for _ in range(8):
            _, stats = engine.apply(image, prepare_gaussian((1, 3, 20), 3))
            assert stats.allocated_bytes == first.allocated_bytes
            assert stats.high_water_bytes == first.high_water_bytes
        check_reference(engine.gaussian(image[:1].copy(), 0.75), image[:1].copy(), 0.75)
        engine.release_memory()
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(lambda s: engine.gaussian(image, s), (0.75, 3, 20)))
        for actual, sigma in zip(results, (0.75, 3, 20)):
            check_reference(actual, image, sigma)
        np.testing.assert_array_equal(out, saved)


def test_actual_metal_rejects_bad_plan_without_poisoning_context(metal_bundle):
    image = np.ones((7, 11), np.float32)
    with NativeMetalSpatial(metal_bundle) as engine:
        for plan in (GaussianPlan(((3, 0, 0),), ()), GaussianPlan(((2, 0, 100),), ()),
                     GaussianPlan(((1, 99, 0),), (1, 0))):
            with pytest.raises(RuntimeError): engine.apply(image, plan)
        np.testing.assert_array_equal(engine.gaussian(image, 0), image)


def test_actual_metal_fast_math_negative_control(metal_bundle, tmp_path):
    bad = tmp_path / "fast"
    shutil.copytree(metal_bundle, bad)
    subprocess.run(["xcrun", "--sdk", "macosx", "metal", "-std=metal3.0",
                    "-mmacosx-version-min=15.0", "-fmetal-math-mode=fast", "-I", str(SOURCES),
                    "-c", str(SOURCES / "spatial.metal"), "-o", str(tmp_path / "fast.air")], check=True)
    subprocess.run(["xcrun", "--sdk", "macosx", "metallib", str(tmp_path / "fast.air"),
                    "-o", str(bad / "sfm_spatial.metallib")], check=True)
    manifest = json.loads((bad / "manifest.json").read_text())
    manifest["artifacts"]["sfm_spatial.metallib"] = _sha256(bad / "sfm_spatial.metallib")
    (bad / "manifest.json").write_text(json.dumps(manifest))
    _check_bundle(bad)  # Correct hashes do not prove correct compiler semantics.
    with pytest.raises(RuntimeError, match="probe failed"): NativeMetalSpatial(bad)
