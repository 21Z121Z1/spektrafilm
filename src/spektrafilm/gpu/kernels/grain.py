"""Backend-portable stochastic distributions for grain simulation.

MLX implementations of the binomial, Poisson, and lognormal samplers needed
by ``spektrafilm.model.grain``.  Each function mirrors its CPU counterpart in
``spektrafilm.utils.fast_stats`` but operates on MLX arrays so the data stays
on-device when a GPU backend is active.

CPU fallback delegates to the existing Numba implementations so the same
caller API works regardless of backend availability.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from spektrafilm.utils.fast_stats import (
    fast_binomial as _cpu_fast_binomial,
    fast_lognormal_from_mean_std as _cpu_fast_lognormal_from_mean_std,
    fast_poisson as _cpu_fast_poisson,
)


# ---------------------------------------------------------------------------
# Backend capability helpers (same pattern as filters.py / density.py)
# ---------------------------------------------------------------------------

def _backend_supports_gpu(backend) -> bool:
    return backend is not None and bool(getattr(backend, "supports_gpu", False))


def _backend_supports_mlx_custom_kernels(backend) -> bool:
    return _backend_supports_gpu(backend) and hasattr(backend, "mx")


def _backend_supports_cupy(backend) -> bool:
    return _backend_supports_gpu(backend) and hasattr(backend, "cp")


# ---------------------------------------------------------------------------
# RNG key helpers for MLX
# ---------------------------------------------------------------------------

def _make_key(mx, seed: int | None):
    """Create an MLX RNG key, defaulting to 0 when *seed* is ``None``."""
    return mx.random.key(seed if seed is not None else 0)


def _split_key(key, n: int):
    """Split *key* into *n* + 1 sub-keys: the first *n* for consumption and
    the last one as the new parent (unused but keeps the API uniform)."""
    # mx.random.split returns exactly 2 children; for more, chain splits.
    keys = [key]
    for _ in range(n):
        k_left, k_right = mx.random.split(keys[-1])
        keys[-1] = k_left
        keys.append(k_right)
    return keys[:n], keys[n]  # consumed keys, remainder


# We hold module-level references so the split helper above works.
# These are resolved lazily on first GPU call.
mx = None  # type: ignore[assignment]


def _ensure_mx(backend):
    """Bind the module-level ``mx`` reference from *backend*."""
    global mx
    mx = backend.mx
    return mx


# ---------------------------------------------------------------------------
# fast_binomial_backend
# ---------------------------------------------------------------------------

def fast_binomial_backend(
    n: int,
    p: Any,
    backend=None,
    *,
    seed: int | None = None,
) -> Any:
    """Generate binomial(n, *p*) samples using the active backend.

    Parameters
    ----------
    n : int
        Number of Bernoulli trials (typically 5--20 in grain simulation).
    p : array-like
        Success probabilities, any broadcastable shape.
    backend : ArrayBackend or None
        GPU backend (MLX / CuPy).  ``None`` falls back to CPU/NumPy.
    seed : int or None
        Base RNG seed.

    Returns
    -------
    result : backend array of int32
        Binomial samples with the same shape as *p*.

    Notes
    -----
    For *n* <= 20 the simple sum-of-Bernoulli approach is efficient on GPU
    because each iteration is a single element-wise operation.
    """
    if not _backend_supports_gpu(backend):
        n_arr = np.full(np.shape(p), n, dtype=np.int64)
        p_arr = np.asarray(p, dtype=np.float64)
        return _cpu_fast_binomial(n_arr, p_arr)

    if _backend_supports_cupy(backend):
        return _fast_binomial_cupy(n, p, backend, seed=seed)

    # --- MLX path ---
    _mx = _ensure_mx(backend)
    p_mx = backend.asarray(p, dtype=_mx.float32)
    key = _make_key(_mx, seed)

    result = _mx.zeros(p_mx.shape, dtype=_mx.int32)
    consumed, key = _split_key(key, n)
    for i in range(n):
        bern = _mx.random.bernoulli(p=p_mx, key=consumed[i])
        result = result + bern.astype(_mx.int32)

    return result


def _fast_binomial_cupy(n: int, p: Any, backend, *, seed: int | None = None) -> Any:
    """CuPy fallback using NumPy-compatible random state."""
    cp = backend.cp
    rng = cp.random.RandomState(seed if seed is not None else 0)
    p_cp = backend.asarray(p, dtype=cp.float32)
    # CuPy does not have bernoulli; use binomial(n=1) element-wise.
    result = cp.zeros(p_cp.shape, dtype=cp.int32)
    for _ in range(n):
        result += rng.binomial(1, p_cp).astype(cp.int32)
    return result


# ---------------------------------------------------------------------------
# fast_poisson_backend
# ---------------------------------------------------------------------------

def fast_poisson_backend(
    lam: Any,
    backend=None,
    *,
    seed: int | None = None,
) -> Any:
    """Generate Poisson(*lam*) samples using the active backend.

    Parameters
    ----------
    lam : array-like
        Rate parameters (lambda values).
    backend : ArrayBackend or None
        GPU backend.  ``None`` falls back to CPU/NumPy.
    seed : int or None
        Base RNG seed.

    Returns
    -------
    result : backend array of int32
        Poisson samples with the same shape as *lam*.

    Notes
    -----
    * For lambda <= 10: Knuth's algorithm using sequential uniform draws
      compared against ``exp(-lam)``.
    * For lambda > 10: Normal approximation ``N(lam, sqrt(lam))`` clamped
      to non-negative integers, matching the CPU ``fast_poisson`` threshold.
    """
    if not _backend_supports_gpu(backend):
        return _cpu_fast_poisson(np.asarray(lam, dtype=np.float64))

    if _backend_supports_cupy(backend):
        return _fast_poisson_cupy(lam, backend, seed=seed)

    # --- MLX path ---
    _mx = _ensure_mx(backend)
    lam_mx = backend.asarray(lam, dtype=_mx.float32)
    key = _make_key(_mx, seed)

    # Normal approximation mask: lam > 10
    use_normal = lam_mx > 10.0

    # --- Normal approximation branch ---
    sqrt_lam = _mx.sqrt(lam_mx)
    key_norm, key = _mx.random.split(key)
    normal_samples = lam_mx + sqrt_lam * _mx.random.normal(lam_mx.shape, key=key_norm, dtype=_mx.float32)
    normal_int = _mx.round(normal_samples).astype(_mx.int32)
    normal_clamped = _mx.maximum(normal_int, _mx.zeros_like(normal_int))

    # --- Knuth algorithm branch (for small lambda) ---
    # Knuth: generate uniform U_1, U_2, ... until product < exp(-lam).
    # On GPU we use a fixed maximum iteration count (sufficient for lam<=10)
    # and mask-accumulate.
    max_iter = 60  # P(K > 60 | lam=10) is negligible

    knuth_count = _mx.zeros(lam_mx.shape, dtype=_mx.int32)
    knuth_product = _mx.ones(lam_mx.shape, dtype=_mx.float32)
    exp_neg_lam = _mx.exp(-lam_mx)

    key_knuth_start, key = _mx.random.split(key)
    current_key = key_knuth_start
    for _ in range(max_iter):
        u_key, current_key = _mx.random.split(current_key)
        u = _mx.random.uniform(low=0.0, high=1.0, shape=lam_mx.shape, key=u_key, dtype=_mx.float32)
        knuth_product = knuth_product * u
        still_active = knuth_product > exp_neg_lam
        knuth_count = knuth_count + still_active.astype(_mx.int32)

    # --- Merge branches ---
    result = _mx.where(use_normal, normal_clamped, knuth_count)
    return result


def _fast_poisson_cupy(lam: Any, backend, *, seed: int | None = None) -> Any:
    """CuPy Poisson using its built-in sampler."""
    cp = backend.cp
    rng = cp.random.RandomState(seed if seed is not None else 0)
    lam_cp = backend.asarray(lam, dtype=cp.float64)
    return rng.poisson(lam=lam_cp).astype(cp.int32)


# ---------------------------------------------------------------------------
# fast_lognormal_from_mean_std_backend
# ---------------------------------------------------------------------------

def fast_lognormal_from_mean_std_backend(
    mean: Any,
    std: Any,
    backend=None,
    *,
    seed: int | None = None,
) -> Any:
    """Generate lognormal samples parameterised by linear-space *mean*/*std*.

    Parameters
    ----------
    mean, std : array-like
        Linear-space mean and standard deviation of the desired lognormal
        distribution.  Same broadcastable shape.
    backend : ArrayBackend or None
        GPU backend.  ``None`` falls back to CPU/NumPy.
    seed : int or None
        Base RNG seed.

    Returns
    -------
    result : backend array of float32
        Lognormal samples with the same shape as *mean*.

    Notes
    -----
    The log-space parameters are recovered as::

        sigma_sq = ln(1 + std^2 / mean^2)
        mu       = ln(mean) - sigma_sq / 2

    Then ``result = exp(N(mu, sigma))``.
    """
    if not _backend_supports_gpu(backend):
        return _cpu_fast_lognormal_from_mean_std(
            np.asarray(mean, dtype=np.float64),
            np.asarray(std, dtype=np.float64),
        )

    if _backend_supports_cupy(backend):
        return _fast_lognormal_cupy(mean, std, backend, seed=seed)

    # --- MLX path ---
    _mx = _ensure_mx(backend)
    mean_mx = backend.asarray(mean, dtype=_mx.float32)
    std_mx = backend.asarray(std, dtype=_mx.float32)

    # Guard against zero / negative mean
    safe_mean = _mx.maximum(mean_mx, _mx.array(1e-30, dtype=_mx.float32))

    sigma_sq = _mx.log(1.0 + (std_mx * std_mx) / (safe_mean * safe_mean))
    sigma = _mx.sqrt(sigma_sq)
    mu = _mx.log(safe_mean) - sigma_sq * 0.5

    key = _make_key(_mx, seed)
    normal_key, _ = _mx.random.split(key)
    z = _mx.random.normal(mu.shape, key=normal_key, dtype=_mx.float32)
    return _mx.exp(mu + sigma * z)


def _fast_lognormal_cupy(mean: Any, std: Any, backend, *, seed: int | None = None) -> Any:
    """CuPy lognormal from linear-space mean/std."""
    cp = backend.cp
    rng = cp.random.RandomState(seed if seed is not None else 0)
    mean_cp = backend.asarray(mean, dtype=cp.float64)
    std_cp = backend.asarray(std, dtype=cp.float64)

    safe_mean = cp.maximum(mean_cp, 1e-30)
    sigma_sq = cp.log(1.0 + (std_cp ** 2) / (safe_mean ** 2))
    sigma = cp.sqrt(sigma_sq)
    mu = cp.log(safe_mean) - sigma_sq * 0.5
    return rng.lognormal(mean=mu, sigma=sigma).astype(cp.float32)
