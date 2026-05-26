"""Shared runtime dtype validation utilities."""

from __future__ import annotations

import numpy as np


def runtime_float_dtype(precision: str) -> np.dtype:
    """Return ``np.float32`` or ``np.float64`` from a precision string.

    Parameters
    ----------
    precision : str
        Either ``"float32"`` or ``"float64"``.

    Returns
    -------
    np.dtype
        The corresponding NumPy dtype.

    Raises
    ------
    ValueError
        If *precision* is not ``"float32"`` or ``"float64"``.
    """
    if precision == "float32":
        return np.dtype(np.float32)
    if precision == "float64":
        return np.dtype(np.float64)
    raise ValueError("precision must be 'float32' or 'float64'")


def validate_float_dtype(dtype: type | np.dtype) -> np.dtype:
    """Validate and return a float32/float64 dtype.

    Parameters
    ----------
    dtype : type or np.dtype
        The dtype to validate.

    Returns
    -------
    np.dtype
        ``np.float32`` or ``np.float64``.

    Raises
    ------
    ValueError
        If *dtype* is not float32 or float64.
    """
    dtype = np.dtype(dtype)
    if dtype == np.dtype(np.float32) or dtype == np.dtype(np.float64):
        return dtype
    raise ValueError("dtype must be float32 or float64")
