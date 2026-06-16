"""Compatibility wrapper for the misspelled highlight boost module path."""

from __future__ import annotations

import numpy as np

from spektrafilm.utils.numba_boost_highlights import boost_highlights


def warmup_boost_highlights() -> None:
    """Trigger Numba compilation through the compatibility module."""
    sample = np.full((2, 2, 3), 1.0, dtype=np.float64)
    boost_highlights(sample, boost_ev=1.0, boost_range=0.5, protect_ev=0.0)


__all__ = ["boost_highlights", "warmup_boost_highlights"]
