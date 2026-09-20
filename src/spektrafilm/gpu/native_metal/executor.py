"""Explicit native prepared execution; never selected by production defaults."""
from __future__ import annotations

import ctypes as ct
from dataclasses import dataclass
from pathlib import Path
import sys
from threading import RLock
from time import perf_counter
import weakref

import numpy as np

from . import _check_bundle, _validate_image
from .program import EXECUTION_VERSION, Program, integer

_PTR = ct.c_void_p
_F32 = ct.POINTER(ct.c_float)
_U32 = ct.POINTER(ct.c_uint32)
_ERROR = [ct.c_char_p, ct.c_size_t]


class _Stats(ct.Structure):
    _fields_ = [(x, ct.c_uint64) for x in (
        "allocated_bytes", "high_water_bytes", "dispatches", "submissions",
        "upload_bytes", "readback_bytes", "gpu_nanoseconds")]


@dataclass(frozen=True)
class ExecutionStats:
    allocated_bytes: int
    high_water_bytes: int
    dispatches: int
    submissions: int
    upload_bytes: int
    readback_bytes: int
    gpu_nanoseconds: int
    synchronized_seconds: float = 0.0

    @classmethod
    def from_native(cls, stats, elapsed=0.0):
        return cls(*(getattr(stats, name) for name, _ in _Stats._fields_), elapsed)


class _Owned:
    def __init__(self, engine, pointer, destructor):
        self.engine = engine
        self._pointer = pointer
        self._finalizer = weakref.finalize(self, destructor, pointer)

    def _live(self):
        if not self._finalizer.alive:
            raise RuntimeError("native handle is closed")
        return self._pointer

    def close(self):
        with self.engine._lock:
            self._finalizer()

    def __enter__(self):
        self._live()
        return self

    def __exit__(self, *_):
        self.close()


class ResidentImage(_Owned):
    def __init__(self, engine, pointer, shape):
        super().__init__(engine, pointer, engine._lib.sfm_image_destroy)
        self._shape = tuple(shape)

    @property
    def shape(self):
        return self._shape

    @property
    def nbytes(self):
        return int(np.prod(self._shape)) * 4

    def numpy(self):
        with self.engine._lock:
            self.engine._open()
            result = np.empty(self.shape, dtype=np.float32)
            self.engine._call(self.engine._lib.sfm_image_read, self.engine._pointer,
                              self._live(), result.ctypes.data_as(_F32), result.size)
            return result

    def texture(self):
        with self.engine._lock:
            self.engine._open()
            out = _PTR()
            self.engine._call(self.engine._lib.sfm_image_texture, self.engine._pointer,
                              self._live(), ct.byref(out))
            return TextureLease(self.engine, out, (*self.shape[:2], 4))


class TextureLease(_Owned):
    """RGBA32Float, alpha=1. Owner must finish external GPU reads before close.

    No color space is inferred or tagged; negative densities are not display RGB.
    Packing is a GPU operation, not a zero-work view of packed RGB. Accessing
    the borrowed pointer does not transfer ownership to an external consumer.
    """
    def __init__(self, engine, pointer, shape):
        super().__init__(engine, pointer, engine._lib.sfm_texture_destroy)
        self._shape = shape

    def numpy(self):
        """Explicit diagnostic readback; not part of the device handoff."""
        with self.engine._lock:
            result = np.empty(self._shape, dtype=np.float32)
            self.engine._call(self.engine._lib.sfm_texture_read, self._live(),
                              result.ctypes.data_as(_F32), result.size)
            return result

    @property
    def handle(self):
        with self.engine._lock:
            return self.engine._lib.sfm_texture_handle(self._live())


class PreparedProgram(_Owned):
    def __init__(self, engine, pointer, channels, fingerprint):
        super().__init__(engine, pointer, engine._lib.sfm_program_destroy)
        self._channels, self._fingerprint = channels, fingerprint

    @property
    def channels(self):
        return self._channels

    @property
    def fingerprint(self):
        return self._fingerprint


class NativeExecutor:
    """One Metal queue, explicitly budgeted resident buffers, one wait per run.

    All large images stay on-device between runs unless numpy() is requested.
    The only run-time host readback is the four-byte error flag. Allocation
    accounting is retained Metal buffer bytes, not an RSS or VRAM estimate.
    """
    def __init__(self, bundle, *, max_resident_bytes=2 * 1024**3):
        if sys.platform != "darwin":
            raise RuntimeError("native prepared execution requires macOS")
        max_resident_bytes = integer(max_resident_bytes, maximum=2**63 - 1)
        if max_resident_bytes < 64:
            raise ValueError("resident budget is too small")
        self._lock = RLock()
        bundle = Path(bundle).resolve()
        _check_bundle(bundle)
        lib = self._lib = ct.CDLL(str(bundle / "libsfm_spatial.dylib"))
        signatures = {
            "sfm_execution_version": ([], ct.c_uint32),
            "sfm_executor_create": ([ct.c_char_p, ct.c_uint64, ct.POINTER(_PTR), *_ERROR], ct.c_int),
            "sfm_executor_destroy": ([_PTR], None),
            "sfm_executor_trim": ([_PTR, *_ERROR], ct.c_int),
            "sfm_executor_stats": ([_PTR, ct.POINTER(_Stats), *_ERROR], ct.c_int),
            "sfm_program_create": ([_PTR, _U32, ct.c_size_t, _F32, ct.c_size_t,
                                    ct.c_uint32, ct.c_uint32, ct.c_uint32, ct.POINTER(_PTR), *_ERROR], ct.c_int),
            "sfm_program_destroy": ([_PTR], None),
            "sfm_image_upload": ([_PTR, _F32, ct.c_size_t, ct.c_uint32, ct.c_uint32,
                                  ct.c_uint32, ct.POINTER(_PTR), *_ERROR], ct.c_int),
            "sfm_image_read": ([_PTR, _PTR, _F32, ct.c_size_t, *_ERROR], ct.c_int),
            "sfm_image_destroy": ([_PTR], None),
            "sfm_program_run": ([_PTR, _PTR, _PTR, ct.POINTER(_PTR), ct.POINTER(_Stats), *_ERROR], ct.c_int),
            "sfm_image_texture": ([_PTR, _PTR, ct.POINTER(_PTR), *_ERROR], ct.c_int),
            "sfm_texture_handle": ([_PTR], _PTR),
            "sfm_texture_destroy": ([_PTR], None),
            "sfm_texture_read": ([_PTR, _F32, ct.c_size_t, *_ERROR], ct.c_int),
            "sfm_executor_philox": ([_PTR, _U32, _U32, _U32, *_ERROR], ct.c_int),
        }
        for name, (args, restype) in signatures.items():
            function = getattr(lib, name)
            function.argtypes, function.restype = args, restype
        if lib.sfm_execution_version() != EXECUTION_VERSION:
            raise RuntimeError("prepared execution ABI mismatch")
        self._pointer = _PTR()
        self._call(lib.sfm_executor_create, str(bundle / "sfm_spatial.metallib").encode(),
                   max_resident_bytes, ct.byref(self._pointer))
        self._finalizer = weakref.finalize(self, lib.sfm_executor_destroy, self._pointer)

    @staticmethod
    def _call(function, *args):
        error = ct.create_string_buffer(2048)
        status = function(*args, error, len(error))
        if status:
            raise RuntimeError(error.value.decode("utf-8", errors="replace"))

    def _open(self):
        if not self._finalizer.alive:
            raise RuntimeError("executor is closed")

    def close(self):
        with self._lock:
            self._finalizer()

    def __enter__(self):
        self._open()
        return self

    def __exit__(self, *_):
        self.close()

    def trim(self):
        with self._lock:
            self._open()
            self._call(self._lib.sfm_executor_trim, self._pointer)

    @property
    def statistics(self):
        with self._lock:
            self._open()
            stats = _Stats()
            self._call(self._lib.sfm_executor_stats, self._pointer, ct.byref(stats))
            return ExecutionStats.from_native(stats)

    def prepare(self, program: Program):
        if not isinstance(program, Program):
            raise TypeError("expected an immutable Program")
        compiled = program.compile()
        with self._lock:
            self._open()
            pointer = _PTR()
            self._call(self._lib.sfm_program_create, self._pointer,
                       compiled.operations.ctypes.data_as(_U32), len(compiled.operations),
                       compiled.constants.ctypes.data_as(_F32), len(compiled.constants),
                       program.channels, compiled.slots, compiled.output, ct.byref(pointer))
            return PreparedProgram(self, pointer, program.channels, compiled.fingerprint)

    def upload(self, image):
        height, width, channels = _validate_image(image)
        with self._lock:
            self._open()
            pointer = _PTR()
            self._call(self._lib.sfm_image_upload, self._pointer, image.ctypes.data_as(_F32),
                       image.size, height, width, channels, ct.byref(pointer))
            return ResidentImage(self, pointer, image.shape)

    def run(self, program: PreparedProgram, image: ResidentImage):
        if not isinstance(program, PreparedProgram) or not isinstance(image, ResidentImage):
            raise TypeError("expected prepared program and resident image")
        if program.engine is not self or image.engine is not self:
            raise ValueError("program or image belongs to another executor")
        with self._lock:
            self._open()
            program._live()
            image._live()
            out, stats = _PTR(), _Stats()
            start = perf_counter()
            self._call(self._lib.sfm_program_run, self._pointer, program._pointer,
                       image._pointer, ct.byref(out), ct.byref(stats))
            elapsed = perf_counter() - start
            return ResidentImage(self, out, image.shape), ExecutionStats.from_native(stats, elapsed)

    def philox_words(self, counter, key):
        counter = tuple(integer(x) for x in counter)
        key = tuple(integer(x) for x in key)
        if len(counter) != 4 or len(key) != 2:
            raise ValueError("Philox4x32 requires four counter and two key words")
        with self._lock:
            self._open()
            result = (ct.c_uint32 * 4)()
            self._call(self._lib.sfm_executor_philox, self._pointer,
                       (ct.c_uint32 * 4)(*counter), (ct.c_uint32 * 2)(*key), result)
            return tuple(result)


class NativeSession:
    """One resident source and one negative, bounded by the executor's budget.

    Cache publication is transactional across BOTH film and print. A failed
    new render leaves the previous negative and its fingerprint intact.
    Programs include physical scale, profiles and seed in their constants.
    No resolution-based 4 MP cutoff and no input hashing on each reprint.
    """
    def __init__(self, engine: NativeExecutor, source):
        self.engine = engine
        self._source = engine.upload(source)
        self._negative = None
        self._film_key = None
        self.film_runs = self.print_runs = self.cache_hits = 0
        self._closed = False

    def set_source(self, source):
        with self.engine._lock:
            if self._closed:
                raise RuntimeError("session is closed")
            new_source = self.engine.upload(source)
            self.clear_negative()
            self._source.close()
            self._source = new_source

    def clear_negative(self):
        with self.engine._lock:
            if self._negative is not None:
                self._negative.close()
            self._negative = self._film_key = None

    def render(self, film: PreparedProgram, print_program: PreparedProgram):
        with self.engine._lock:
            if self._closed:
                raise RuntimeError("session is closed")
            if film.engine is not self.engine or print_program.engine is not self.engine:
                raise ValueError("session programs belong to another executor")
            film._live()
            print_program._live()
            reused = self._negative is not None and self._film_key == film.fingerprint
            candidate = self._negative
            if not reused:
                candidate, _ = self.engine.run(film, self._source)
                self.film_runs += 1
            try:
                result, stats = self.engine.run(print_program, candidate)
                self.print_runs += 1
            except BaseException:
                if not reused:
                    candidate.close()
                raise
            if not reused:
                self.clear_negative()
                self._negative, self._film_key = candidate, film.fingerprint
            else:
                self.cache_hits += 1
            return result, stats

    def close(self):
        with self.engine._lock:
            if not self._closed:
                self.clear_negative()
                self._source.close()
                self._closed = True

    def __enter__(self):
        if self._closed:
            raise RuntimeError("session is closed")
        return self

    def __exit__(self, *_):
        self.close()
