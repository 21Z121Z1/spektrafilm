"""Row-wise tiling utilities for backend-resident spectral and spatial chains.

Spectral operations allocate high-dimensional transient arrays
(``H x W x K``); spatial filters allocate full-frame FFT buffers or
large kernels.  Splitting the image into horizontal strips keeps the
per-tile working set small while preserving per-pixel arithmetic.
"""

from __future__ import annotations

from typing import Any, Callable


def _is_backend_array(value: Any, backend: Any) -> bool:
    """Return True if ``value`` is already an array native to ``backend``."""
    return getattr(backend, "_is_mlx_array", lambda x: False)(value)


def default_tile_rows(height: int) -> int:
    """Return default row count per spectral tile.

    Uses ``max(256, height // 8)`` so small images still get enough rows for
    GPU occupancy while large images are split into at most eight tiles.
    """
    return max(256, height // 8)


def default_spatial_tile_rows(height: int) -> int:
    """Return default row count per spatial tile.

    Spatial filters need larger tiles than spectral chains because each tile
    carries an overlap halo.  ``max(512, height // 8)`` keeps the overlap
    ratio moderate for typical filter radii.
    """
    return max(512, height // 8)


def resolve_spatial_tile_rows(
    height: int,
    overlap: int,
    *,
    backend: Any,
    settings: Any | None = None,
) -> int | None:
    """Return the number of rows per spatial tile, or ``None`` to disable.

    Tiling is enabled only for MLX float32 backends.  The returned tile size
    is at least four times ``overlap`` so the halo overhead stays small, and
    it is capped so that at least two tiles fit with their halos.
    """
    if overlap <= 0:
        return None
    if backend is None or not getattr(backend, "supports_gpu", False):
        return None
    if getattr(backend, "name", None) != "mlx":
        return None
    if getattr(backend, "precision", None) != "float32":
        return None
    if settings is not None and getattr(settings, "gpu_disable_spatial_tiling", False):
        return None

    explicit = None
    if settings is not None:
        explicit = getattr(settings, "gpu_spatial_tile_rows", None)
    if explicit is not None:
        tile_rows = int(explicit)
    else:
        tile_rows = default_spatial_tile_rows(height)

    tile_rows = max(tile_rows, 4 * overlap)
    if height <= tile_rows + 2 * overlap:
        return None
    return tile_rows


def process_rows_tiled(
    image: Any,
    process_fn: Callable[[Any], Any],
    backend: Any,
    *,
    tile_rows: int | None = None,
    eval_per_tile: bool = True,
) -> Any:
    """Apply ``process_fn`` to horizontal strips of ``image``.

    Parameters
    ----------
    image:
        Backend array with shape ``(H, W, ...)``.
    process_fn:
        Function that accepts a backend array and returns a backend array of
        the same spatial shape (possibly different channels).
    backend:
        Backend instance (e.g. ``MlxBackend``).
    tile_rows:
        Number of rows per tile. If ``None`` or larger than ``H``, the whole
        image is processed at once (no tiling).
    eval_per_tile:
        If True, call ``backend.eval`` on each tile output before writing it
        back and deleting intermediates. Required for MLX lazy evaluation.

    Returns
    -------
    Output backend array with spatial shape ``(H, W, ...)``.
    """
    if tile_rows is None or tile_rows <= 0:
        return process_fn(image)

    height = int(image.shape[0])
    if height <= tile_rows:
        return process_fn(image)

    # Determine output shape/dtype by processing one tile first.
    first_tile = image[:tile_rows]
    first_out = process_fn(first_tile)
    if eval_per_tile:
        backend.eval(first_out)

    out_shape = (height, int(image.shape[1])) + tuple(first_out.shape[2:])
    output = backend.zeros(out_shape, dtype=first_out.dtype)

    # Write first tile.
    output = _write_tile(output, first_out, 0, tile_rows, backend)
    del first_tile, first_out

    for y0 in range(tile_rows, height, tile_rows):
        y1 = min(height, y0 + tile_rows)
        tile_in = image[y0:y1]
        tile_out = process_fn(tile_in)
        if eval_per_tile:
            backend.eval(tile_out)
        output = _write_tile(output, tile_out, y0, y1, backend)
        del tile_in, tile_out
        _maybe_clear_backend_cache(backend)

    return output


def process_spatial_rows_tiled(
    image: Any,
    process_fn: Callable[[Any], Any],
    backend: Any,
    overlap: int,
    *,
    tile_rows: int | None = None,
    eval_per_tile: bool = True,
) -> Any:
    """Apply a spatial ``process_fn`` to overlapping horizontal strips.

    ``process_fn`` receives an extended tile of shape
    ``(tile_rows + 2*overlap, W, C)`` and must return an array of the same
    shape.  The central ``tile_rows`` rows of the returned extended tile are
    written back; the overlap rows are discarded.  This gives the same result
    as running ``process_fn`` on the whole image and reflect-padding, as long
    as ``overlap`` is at least the spatial support radius of the filter.

    Parameters
    ----------
    image:
        Backend array with shape ``(H, W, ...)``.
    process_fn:
        Function that accepts an extended tile and returns an extended tile
        of the same spatial shape.
    backend:
        Backend instance (e.g. ``MlxBackend``).
    overlap:
        Number of overlap rows above and below each tile.  Must be at least
        the filter's spatial support radius.
    tile_rows:
        Number of center rows per tile. If ``None`` or the image is too small
        to fit two tiles with halos, the whole image is processed at once.
    eval_per_tile:
        If True, call ``backend.eval`` on each tile output before writing it
        back and deleting intermediates. Required for MLX lazy evaluation.

    Returns
    -------
    Output backend array with spatial shape ``(H, W, ...)``.
    """
    if tile_rows is None or tile_rows <= 0 or overlap <= 0:
        return process_fn(image)

    height = int(image.shape[0])
    if height <= tile_rows + 2 * overlap:
        return process_fn(image)

    def _extended_bounds(y0: int, y1: int) -> tuple[int, int]:
        return max(0, y0 - overlap), min(height, y1 + overlap)

    # Process first tile to determine output dtype/shape.
    y0, y1 = 0, min(tile_rows, height)
    ext_y0, ext_y1 = _extended_bounds(y0, y1)
    first_ext = image[ext_y0:ext_y1]
    first_out_ext = process_fn(first_ext)
    if eval_per_tile:
        backend.eval(first_out_ext)

    out_shape = (height, int(image.shape[1])) + tuple(first_out_ext.shape[2:])
    output = backend.zeros(out_shape, dtype=first_out_ext.dtype)

    in_offset = y0 - ext_y0
    out_len = y1 - y0
    output = _write_tile(
        output,
        first_out_ext[in_offset:in_offset + out_len],
        y0,
        y1,
        backend,
    )
    del first_ext, first_out_ext

    for y0 in range(tile_rows, height, tile_rows):
        y1 = min(height, y0 + tile_rows)
        ext_y0, ext_y1 = _extended_bounds(y0, y1)
        tile_ext = image[ext_y0:ext_y1]
        tile_out_ext = process_fn(tile_ext)
        if eval_per_tile:
            backend.eval(tile_out_ext)

        in_offset = y0 - ext_y0
        out_len = y1 - y0
        output = _write_tile(
            output,
            tile_out_ext[in_offset:in_offset + out_len],
            y0,
            y1,
            backend,
        )
        del tile_ext, tile_out_ext
        _maybe_clear_backend_cache(backend)

    return output


def _write_tile(output, tile_out, y0, y1, backend):
    """Write ``tile_out`` into rows ``[y0:y1]`` of ``output``.

    MLX arrays are immutable, so the update is expressed through an
    in-place addition on a zero-initialized output buffer.  Other backends
    fall back to direct slice assignment.
    """
    mx = getattr(backend, "mx", None)
    if mx is not None and _is_backend_array(output, backend):
        # output is zeros, so adding the tile materialises the tile values.
        return output.at[y0:y1].add(tile_out)
    output[y0:y1] = tile_out
    return output


def _maybe_clear_backend_cache(backend) -> None:
    """Clear non-essential backend cache between tiles to bound memory."""
    clear = getattr(backend, "clear_cache", None)
    if callable(clear):
        try:
            clear()
        except Exception:
            pass
