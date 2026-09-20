"""Experimental native spatial executor. Never selected by the runtime factory."""
from __future__ import annotations

import ctypes as ct
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys
import threading
from time import perf_counter
import weakref

import numpy as np

ABI_VERSION = 1
SOURCE_FILES = ("spatial.h", "spatial_math.h", "spatial.metal", "spatial.mm", "build.py")


@dataclass(frozen=True)
class GaussianPlan:
    """Immutable execution data, derived only from the existing CPU model."""
    entries: tuple[tuple[int, int, int], ...]
    constants: tuple[float, ...]

    def __post_init__(self) -> None:
        # A caller may supply lists despite the type annotation.
        object.__setattr__(self, "entries", tuple(tuple(entry) for entry in self.entries))
        object.__setattr__(self, "constants", tuple(self.constants))


def prepare_gaussian(sigma, channels: int, *, truncate: float = 3.0) -> GaussianPlan:
    from spektrafilm.utils.fast_gaussian_filter import (
        SMALL_SIGMA_MAX, _gaussian_kernel_1d, _yvv_coeffs,
    )
    if isinstance(channels, bool) or not isinstance(channels, int) or not 1 <= channels <= 4:
        raise ValueError("channels must be an integer from 1 to 4")
    sigmas = np.asarray(sigma, dtype=np.float64)
    if sigmas.ndim == 0:
        sigmas = np.full(channels, float(sigmas))
    if sigmas.shape != (channels,) or not np.all(np.isfinite(sigmas)):
        raise ValueError("sigma must be finite and scalar or one value per channel")
    if np.any(sigmas > 256):
        raise ValueError("this experiment supports sigma <= 256 pixels")
    if not np.isfinite(truncate) or truncate < 0:
        raise ValueError("truncate must be finite and nonnegative")
    constants: list[float] = []
    entries: list[tuple[int, int, int]] = []
    for s in sigmas:
        offset = len(constants)
        if s <= 0:
            entries.append((0, 0, offset))
            continue
        if s < SMALL_SIGMA_MAX:
            if truncate * s + 0.5 >= 65:
                raise ValueError("this experiment supports FIR radius <= 64")
            values, radius = _gaussian_kernel_1d(float(s), float(truncate))
            entries.append((1, int(radius), offset))
        else:
            values = _yvv_coeffs(float(s))
            entries.append((2, 0, offset))
        for value in values:
            high = np.float32(value)
            low = np.float32(np.float64(value) - np.float64(high))
            constants.extend((float(high), float(low)))
    return GaussianPlan(tuple(entries), tuple(constants))


def _validate_image(image: np.ndarray) -> tuple[int, int, int]:
    if not isinstance(image, np.ndarray) or image.dtype != np.dtype("float32"):
        raise TypeError("input must be a native-endian float32 NumPy array")
    if image.ndim not in (2, 3) or not image.flags.c_contiguous:
        raise ValueError("input must be contiguous HxW or HxWxC")
    h, w = image.shape[:2]
    c = image.shape[2] if image.ndim == 3 else 1
    if not (0 < h <= 16384 and 0 < w <= 16384 and 1 <= c <= 4):
        raise ValueError("input dimensions exceed the experimental contract")
    if not np.all(np.isfinite(image)):
        raise ValueError("input must be finite")
    return h, w, c


class _Channel(ct.Structure):
    _fields_ = [(name, ct.c_uint32) for name in ("kind", "radius", "offset")]


class _Stats(ct.Structure):
    _fields_ = [(name, ct.c_uint64) for name in (
        "allocated_bytes", "high_water_bytes", "upload_bytes", "readback_bytes",
        "dispatches", "gpu_nanoseconds",
    )]


@dataclass(frozen=True)
class RunStats:
    synchronized_seconds: float
    allocated_bytes: int
    high_water_bytes: int
    upload_bytes: int
    readback_bytes: int
    dispatches: int
    gpu_nanoseconds: int | None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_bundle(bundle: Path) -> None:
    manifest = json.loads((bundle / "manifest.json").read_text())
    if manifest.get("abi") != ABI_VERSION:
        raise RuntimeError("native spatial bundle ABI mismatch")
    for name in SOURCE_FILES:
        if manifest["sources"].get(name) != _sha256(Path(__file__).parent / name):
            raise RuntimeError(f"stale native spatial source: {name}; rebuild explicitly")
    for name in ("libsfm_spatial.dylib", "sfm_spatial.metallib"):
        if manifest["artifacts"].get(name) != _sha256(bundle / name):
            raise RuntimeError(f"native spatial artifact hash mismatch: {name}")


class NativeMetalSpatial:
    """Single-flight native context, with explicit build and memory ownership.

    No automatic build, dtype conversion, CPU fallback, or backend replacement.
    This first slice uses one host upload/readback, not texture interop.
    """
    def __init__(self, bundle: str | Path, *, max_working_bytes: int = 2 * 1024**3):
        if sys.platform != "darwin":
            raise RuntimeError("native Metal execution requires macOS")
        if (isinstance(max_working_bytes, bool) or not isinstance(max_working_bytes, int)
                or not 64 <= max_working_bytes < 2**64):
            raise ValueError("max_working_bytes must be an integer in [64, 2**64)")
        bundle = Path(bundle).resolve()
        _check_bundle(bundle)
        self._lock = threading.RLock()
        self._lib = ct.CDLL(str(bundle / "libsfm_spatial.dylib"))
        fp = ct.POINTER(ct.c_float)
        self._lib.sfm_abi_version.argtypes = []
        self._lib.sfm_abi_version.restype = ct.c_uint32
        self._lib.sfm_create.argtypes = [ct.c_char_p, ct.c_uint64, ct.POINTER(ct.c_void_p), ct.c_void_p, ct.c_size_t]
        self._lib.sfm_destroy.argtypes = [ct.c_void_p]
        self._lib.sfm_destroy.restype = None
        self._lib.sfm_release_memory.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_size_t]
        self._lib.sfm_gaussian.argtypes = [
            ct.c_void_p, fp, fp, ct.c_size_t, ct.c_uint32, ct.c_uint32, ct.c_uint32,
            ct.POINTER(_Channel), ct.c_size_t, fp, ct.c_size_t, ct.POINTER(_Stats),
            ct.c_void_p, ct.c_size_t,
        ]
        for name in ("sfm_create", "sfm_release_memory", "sfm_gaussian"):
            getattr(self._lib, name).restype = ct.c_int
        if self._lib.sfm_abi_version() != ABI_VERSION:
            raise RuntimeError("native spatial host ABI mismatch")
        self._context = ct.c_void_p()
        error = ct.create_string_buffer(2048)
        status = self._lib.sfm_create(
            str(bundle / "sfm_spatial.metallib").encode(), max_working_bytes,
            ct.byref(self._context), error, len(error),
        )
        if status:
            raise RuntimeError(error.value.decode(errors="replace"))
        self._finalizer = weakref.finalize(self, self._lib.sfm_destroy, self._context)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self) -> None:
        with self._lock:
            self._finalizer()

    def _require_open(self) -> None:
        if not self._finalizer.alive:
            raise RuntimeError("native spatial context is closed")

    def release_memory(self) -> None:
        with self._lock:
            self._require_open()
            error = ct.create_string_buffer(2048)
            if self._lib.sfm_release_memory(self._context, error, len(error)):
                raise RuntimeError(error.value.decode(errors="replace"))

    def apply(self, image: np.ndarray, plan: GaussianPlan) -> tuple[np.ndarray, RunStats]:
        h, w, channels = _validate_image(image)
        if not isinstance(plan, GaussianPlan) or len(plan.entries) != channels:
            raise ValueError("plan channel count does not match the input")
        # Public plans are immutable but still untrusted: ctypes integers wrap.
        for entry in plan.entries:
            if len(entry) != 3 or any(type(v) is not int or not 0 <= v < 2**32 for v in entry):
                raise ValueError("plan entries must contain three uint32 values")
        if len(plan.constants) > 4096 or not np.all(np.isfinite(plan.constants)):
            raise ValueError("invalid constant table")
        native_plan = (_Channel * channels)(*(_Channel(*e) for e in plan.entries))
        constants = np.asarray(plan.constants, dtype=np.float32)
        out = np.empty_like(image)
        stats, error = _Stats(), ct.create_string_buffer(2048)
        fp = ct.POINTER(ct.c_float)
        with self._lock:
            self._require_open()
            start = perf_counter()
            status = self._lib.sfm_gaussian(
                self._context, image.ctypes.data_as(fp), out.ctypes.data_as(fp), image.size,
                h, w, channels, native_plan, channels, constants.ctypes.data_as(fp),
                constants.size, ct.byref(stats), error, len(error),
            )
            elapsed = perf_counter() - start
            if status:
                raise RuntimeError(error.value.decode(errors="replace"))
        return out, RunStats(elapsed, stats.allocated_bytes, stats.high_water_bytes,
                             stats.upload_bytes, stats.readback_bytes, stats.dispatches,
                             stats.gpu_nanoseconds or None)

    def gaussian(self, image: np.ndarray, sigma, *, truncate: float = 3.0) -> np.ndarray:
        _, _, channels = _validate_image(image)
        return self.apply(image, prepare_gaussian(sigma, channels, truncate=truncate))[0]
