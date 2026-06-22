from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class ArrayBackend(Protocol):
    name: str
    supports_gpu: bool
    fallback_reason: str | None
    requires_serial_runtime: bool

    def asarray(self, value: Any, dtype: Any | None = None) -> Any: ...
    def to_numpy(self, value: Any) -> Any: ...
    def eval(self, *values: Any) -> None: ...
    def synchronize(self) -> None: ...
    def cleanup(self) -> None: ...
    def zeros(self, shape: tuple[int, ...], dtype: Any | None = None) -> Any: ...

    def exp(self, x: Any) -> Any: ...
    def log10(self, x: Any) -> Any: ...
    def maximum(self, x: Any, y: Any) -> Any: ...
    def max_array(self, x: Any) -> Any: ...
    def max(self, x: Any) -> float: ...
    def clip(self, x: Any, lo: float, hi: float) -> Any: ...
    def matmul(self, a: Any, b: Any) -> Any: ...
    def einsum(self, pattern: str, *values: Any) -> Any: ...
    def power(self, base: float, x: Any) -> Any: ...
    def pow(self, x: Any, exponent: float) -> Any: ...
    def fmax(self, x: Any, y: float) -> Any: ...
    def nan_to_num(self, x: Any, nan: float = 0.0) -> Any: ...
    def where(self, condition: Any, x: Any, y: Any) -> Any: ...
    def abs(self, x: Any) -> Any: ...


class BackendUnavailableError(RuntimeError):
    """Raised when a requested compute backend cannot be initialized."""


@dataclass(slots=True)
class BackendInfo:
    requested: str
    selected: str
    supports_gpu: bool
    fallback_reason: str | None = None


def _normalize_backend_name(name: str | None) -> str:
    normalized = "auto" if name is None else str(name).strip().lower()
    if normalized not in {"auto", "cpu", "mlx", "cupy", "cuda", "halide"}:
        raise ValueError("compute_backend must be one of: 'auto', 'cpu', 'mlx', 'cupy', 'cuda', 'halide'")
    return normalized


def _select_mlx_backend(*, precision: str) -> ArrayBackend:
    from spektrafilm.gpu.mlx_backend import MlxBackend

    return MlxBackend(precision=precision)


def _select_cupy_backend(*, precision: str) -> ArrayBackend:
    from spektrafilm.gpu.cupy_backend import CupyBackend

    return CupyBackend(precision=precision)


def _select_halide_backend(*, precision: str) -> ArrayBackend:
    from spektrafilm.gpu.halide_backend import HalideBackend

    return HalideBackend(precision=precision)


def select_backend(name: str | None = "auto", *, precision: str = "float32") -> ArrayBackend:
    """Select an array backend for runtime computation.

    ``auto`` prefers MLX when it is importable and Metal is available, then
    CuPy when a CUDA/ROCm device is visible, otherwise it returns the NumPy
    backend with a fallback reason. Explicit GPU backend names are strict and
    raise when the requested backend cannot be used.
    """
    requested = _normalize_backend_name(name)
    if requested == "cpu":
        from spektrafilm.gpu.numpy_backend import NumpyBackend

        return NumpyBackend()

    if precision == "float64":
        if requested == "auto":
            from spektrafilm.gpu.numpy_backend import NumpyBackend

            return NumpyBackend(
                fallback_reason="GPU backends require float32 precision; using CPU for float64."
            )
        raise BackendUnavailableError(
            f"compute_backend='{requested}' does not support gpu_precision='float64'; "
            "use compute_backend='cpu' for float64."
        )

    if requested in {"cupy", "cuda"}:
        return _select_cupy_backend(precision=precision)

    if requested == "halide":
        return _select_halide_backend(precision=precision)

    mlx_error: BackendUnavailableError | None = None
    try:
        return _select_mlx_backend(precision=precision)
    except BackendUnavailableError as exc:
        if requested == "mlx":
            raise
        mlx_error = exc

    try:
        return _select_cupy_backend(precision=precision)
    except BackendUnavailableError as cupy_exc:
        from spektrafilm.gpu.numpy_backend import NumpyBackend

        return NumpyBackend(
            fallback_reason=(
                "GPU backends are unavailable "
                f"(MLX/Metal: {mlx_error}; CuPy/CUDA/ROCm: {cupy_exc})"
            )
        )


def backend_summary(backend: ArrayBackend, *, runtime_gpu_enabled: bool = False) -> str:
    if backend.supports_gpu and not runtime_gpu_enabled:
        return f"cpu runtime path; {backend.name} validated for optional GPU kernels"
    summary = backend.name
    if backend.fallback_reason:
        summary = f"{summary} fallback: {backend.fallback_reason}"
    return summary


def _display_backend_name(name: str) -> str:
    return {
        "cpu": "CPU",
        "mlx": "MLX",
        "cupy": "CuPy",
        "halide": "Halide",
    }.get(str(name).lower(), str(name))


def runtime_backend_summary(backend: ArrayBackend) -> str:
    """Compact description of the active runtime backend for the status bar."""
    if not backend.supports_gpu:
        summary = backend_summary(backend)
        return summary

    display_name = _display_backend_name(backend.name)
    precision = getattr(backend, "precision", None)
    precision_tag = f" {precision}" if precision else ""
    return f"{display_name}{precision_tag}"


# ---------------------------------------------------------------------------
# GPU Tiling for Large Images
# ---------------------------------------------------------------------------


def tiled_processing(
    image: Any,
    tile_size: int,
    process_fn: Any,
    backend: ArrayBackend,
    *,
    overlap: int = 0,
) -> Any:
    """Process a large image in CPU tiles.

    Splits the image into overlapping NumPy tiles, processes each tile, and
    reassembles the result. The overlap region is discarded to avoid seam
    artifacts from filter kernels that extend beyond tile boundaries.

    This helper is intentionally a CPU fallback. GPU callers must not use it:
    the historical implementation silently copied the full image and every
    processed tile through CPU materialization, which was not GPU-resident
    tiling.

    Parameters
    ----------
    image : array-like
        Input image with shape ``(height, width, channels)``.
    tile_size : int
        Tile dimension in pixels.  Each tile is
        ``(tile_size, tile_size, channels)``.
    process_fn : callable
        Function that takes a backend array and returns a processed backend
        array with the same spatial dimensions.
    backend : ArrayBackend
        Array backend for GPU/CPU computation.
    overlap : int
        Number of pixels of overlap on each side to handle filter kernel
        bleed.  Element-wise operations (colour transforms) need ``0``;
        Gaussian blur needs ``3 * sigma``.

    Returns
    -------
    array-like
        Processed image with the same shape and dtype as ``image``.
    """

    import numpy as np

    if getattr(backend, "supports_gpu", False):
        raise RuntimeError(
            "tiled_processing is a CPU fallback; GPU backends must use whole-frame "
            "backend kernels or a dedicated backend_tiled_processing implementation."
        )

    np_image = np.asarray(image)
    h, w = np_image.shape[:2]
    stride = tile_size - 2 * overlap
    if stride <= 0:
        raise ValueError(f"tile_size ({tile_size}) must be greater than 2 * overlap ({2 * overlap}).")

    result = np.empty_like(np_image)
    has_coverage = np.zeros((h, w), dtype=bool)

    for y in range(0, h, stride):
        for x in range(0, w, stride):
            y1 = max(0, y - overlap)
            y2 = min(h, y1 + tile_size)
            x1 = max(0, x - overlap)
            x2 = min(w, x1 + tile_size)

            tile = backend.asarray(np_image[y1:y2, x1:x2])
            processed = np.asarray(process_fn(tile))

            # Compute the valid (non-overlap) region in output coordinates.
            oy1 = y
            oy2 = min(h, y + stride)
            ox1 = x
            ox2 = min(w, x + stride)

            # Map valid region back to tile-local coordinates.
            ty1 = oy1 - y1
            ty2 = ty1 + (oy2 - oy1)
            tx1 = ox1 - x1
            tx2 = tx1 + (ox2 - ox1)

            result[oy1:oy2, ox1:ox2] = processed[ty1:ty2, tx1:tx2]
            has_coverage[oy1:oy2, ox1:ox2] = True

    if not np.all(has_coverage):
        uncovered = int(np.sum(~has_coverage))
        raise RuntimeError(f"Tiling left {uncovered} pixels uncovered; increase tile_size or check stride logic.")

    return backend.asarray(result)
