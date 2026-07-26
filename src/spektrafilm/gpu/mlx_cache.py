"""Optionally budget-gated MLX allocator-cache clearing for hot loops.

The 2026-07-19 M1 Pro bounding pass inserted ``mx.clear_cache()`` after every
chunk, tile, transfer component, and large grain state so the allocator cache
could never grow unboundedly.  ``maybe_clear_cache`` preserves exactly that
behavior by default (budget ``0`` = clear on every call).

Setting ``SPEKTRAFILM_MLX_CACHE_CLEAR_BUDGET_MB`` to a positive value gates
the clears: the cache is released only once ``mx.get_cache_memory()`` exceeds
the budget.  Measured on the 16 GiB M1 Pro reference machine
(``docs/reports/metal-mlx-exactness-preserving-optimization-20260726.md``):
a 256 MiB budget cut process CPU time ~14% on the 49.77 MP paper route but
*regressed* wall clock under system memory pressure, because the retained
cache competes with the OS pager — hence the conservative default.  Machines
with more unified memory can raise the budget; output values are bit-identical
either way (only *unused* pooled buffers are ever released, and all
``mx.eval`` boundaries are unchanged).
"""
from __future__ import annotations

import os
from typing import Any

_ENV_VAR = "SPEKTRAFILM_MLX_CACHE_CLEAR_BUDGET_MB"
_DEFAULT_BUDGET_BYTES = 0


def cache_clear_budget_bytes() -> int:
    """Return the cache budget in bytes (``0``, the default, clears every call)."""
    raw = os.environ.get(_ENV_VAR)
    if raw is None or not raw.strip():
        return _DEFAULT_BUDGET_BYTES
    try:
        return max(int(float(raw) * 1024 * 1024), 0)
    except ValueError:
        return _DEFAULT_BUDGET_BYTES


def _resolve_cache_api(backend_or_mx: Any):
    mx = getattr(backend_or_mx, "mx", None)
    if mx is None:
        mx = backend_or_mx
    for owner in (mx, getattr(mx, "metal", None)):
        clear = getattr(owner, "clear_cache", None)
        if callable(clear):
            return clear, getattr(owner, "get_cache_memory", None)
    return None, None


def maybe_clear_cache(backend_or_mx: Any) -> None:
    """Clear the MLX buffer cache only when it exceeds the configured budget."""
    clear, get_cache = _resolve_cache_api(backend_or_mx)
    if clear is None:
        return
    budget = cache_clear_budget_bytes()
    if budget <= 0 or not callable(get_cache):
        clear()
        return
    try:
        cache_bytes = int(get_cache())
    except (OSError, RuntimeError, TypeError, ValueError):
        clear()
        return
    if cache_bytes >= budget:
        clear()
