"""Backward-compatible import path for the misspelled highlight boost module."""

import numpy as np

from spektrafilm.utils.numba_boost_highlights import boost_highlights as _boost_highlights_impl


def boost_highlights(*args, **kwargs):
    return _boost_highlights_impl(*args, **kwargs)


def warmup_boost_highlights() -> None:
    """Trigger Numba compilation through the compatibility module namespace."""
    sample = np.full((2, 2, 3), 1.0, dtype=np.float64)
    boost_highlights(sample, boost_ev=1.0, boost_range=0.5, protect_ev=0.0)
