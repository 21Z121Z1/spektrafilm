"""ISO 21496-1 Gain Map computation engine.

Implements the core gain map algorithms from ISO 21496-1:2025:
- Formula A.1: compute_gain_map — log2 gain from baseline/alternate images
- Formula (2): apply_gain_map — reconstruct alternate from baseline + gain map
- Formula (3): compute_weight — HDR headroom-based weight factor
- Formula A.2: normalize_gain_map — min/max normalization
- Formula (1) inverse: denormalize_gain_map — restore log2 gain from normalized

All operations use float32 numpy arrays with offset constants for numerical stability.
"""

from __future__ import annotations

import numpy as np

_EPS32: np.float32 = np.float32(1e-8)
_DEFAULT_K: float = 1.0 / 1023.0


def compute_gain_map(
    baseline: np.ndarray,
    alternate: np.ndarray,
    *,
    k_baseline: float = _DEFAULT_K,
    k_alternate: float = _DEFAULT_K,
    h_baseline: float = 0.0,
    h_alternate: float = 3.0,
) -> np.ndarray:
    """Compute a log2 gain map from baseline and alternate images (ISO 21496-1 A.1).

    G = sign(H_alternate - H_baseline) * log2((alternate + k_alternate) / (baseline + k_baseline))

    Parameters
    ----------
    baseline : np.ndarray
        Linear baseline image (H, W, 3) or (H, W). Typically SDR.
    alternate : np.ndarray
        Linear alternate image, same shape. Typically HDR.
    k_baseline : float
        Offset constant for baseline to avoid log(0). Default 1/1023.
    k_alternate : float
        Offset constant for alternate. Default 1/1023.
    h_baseline : float
        HDR headroom of baseline (0.0 for SDR).
    h_alternate : float
        HDR headroom of alternate (e.g. 3.0 = 3 stops).

    Returns
    -------
    np.ndarray
        Log2 gain map, same shape as input, float32.
    """
    b = np.asarray(baseline, dtype=np.float32)
    a = np.asarray(alternate, dtype=np.float32)
    if b.shape != a.shape:
        raise ValueError(f"Shape mismatch: baseline {b.shape} vs alternate {a.shape}")

    sign = np.float32(1.0 if h_alternate >= h_baseline else -1.0)
    num = a + np.float32(k_alternate)
    den = b + np.float32(k_baseline)
    ratio = np.maximum(num / den, _EPS32)
    gain = sign * np.log2(ratio)
    return gain.astype(np.float32, copy=False)


def normalize_gain_map(
    gain: np.ndarray,
    *,
    gamma: float = 1.0,
) -> tuple[np.ndarray, float, float]:
    """Normalize a log2 gain map to [0, 1] with optional gamma encoding (ISO 21496-1 A.2 + A.3).

    G_normalized = (G - min(G)) / (max(G) - min(G))
    G_gamma = G_normalized ^ gamma

    Parameters
    ----------
    gain : np.ndarray
        Raw log2 gain map, shape (H, W, C) or (H, W).
    gamma : float
        Gamma exponent for encoding. 1.0 = linear.

    Returns
    -------
    tuple[np.ndarray, float, float]
        (normalized_gamma_encoded, g_min, g_max)
    """
    g = np.asarray(gain, dtype=np.float32)
    g_min = float(np.min(g))
    g_max = float(np.max(g))
    span = np.float32(g_max - g_min)
    if span < _EPS32:
        return np.zeros_like(g, dtype=np.float32), g_min, g_max
    normalized = (g - np.float32(g_min)) / span
    normalized = np.clip(normalized, 0.0, 1.0)
    if gamma != 1.0:
        normalized = np.power(normalized, np.float32(gamma))
    return normalized.astype(np.float32, copy=False), g_min, g_max


def denormalize_gain_map(
    normalized: np.ndarray,
    g_min: float,
    g_max: float,
    *,
    gamma: float = 1.0,
) -> np.ndarray:
    """Restore a log2 gain map from normalized form (ISO 21496-1 formula (1) inverse).

    G = (max(G) - min(G)) * normalized^(1/gamma) + min(G)

    Parameters
    ----------
    normalized : np.ndarray
        Normalized gain map in [0, 1], shape (H, W, C) or (H, W).
    g_min : float
        Minimum log2 gain value.
    g_max : float
        Maximum log2 gain value.
    gamma : float
        Gamma exponent used during encoding.

    Returns
    -------
    np.ndarray
        Restored log2 gain map, float32.
    """
    g = np.asarray(normalized, dtype=np.float32)
    g = np.clip(g, 0.0, 1.0)
    if gamma != 1.0:
        g = np.power(g, np.float32(1.0 / gamma))
    span = np.float32(g_max - g_min)
    return (span * g + np.float32(g_min)).astype(np.float32, copy=False)


def compute_weight(
    h_target: float,
    h_baseline: float,
    h_alternate: float,
) -> float:
    """Compute weight factor W for gain map application (ISO 21496-1 formula (3)).

    W = sign(H_alternate - H_baseline) * clamp((H_target - H_baseline) / (H_alternate - H_baseline), 0, 1)

    Parameters
    ----------
    h_target : float
        Target HDR headroom (display capability).
    h_baseline : float
        Baseline image headroom.
    h_alternate : float
        Alternate image headroom.

    Returns
    -------
    float
        Weight factor in [0, 1] (positive direction) or [-1, 0] (negative).
    """
    diff = h_alternate - h_baseline
    if abs(diff) < 1e-8:
        return 0.0
    sign = 1.0 if diff >= 0.0 else -1.0
    raw = (h_target - h_baseline) / diff
    clamped = max(0.0, min(1.0, raw))
    return sign * clamped


def apply_gain_map(
    baseline: np.ndarray,
    gain_map: np.ndarray,
    *,
    g_min: float,
    g_max: float,
    gamma: float = 1.0,
    k_baseline: float = _DEFAULT_K,
    k_alternate: float = _DEFAULT_K,
    h_baseline: float = 0.0,
    h_alternate: float = 3.0,
    h_target: float | None = None,
) -> np.ndarray:
    """Apply a gain map to a baseline image to reconstruct the alternate (ISO 21496-1 (2) + (3)).

    Alternate = (Baseline + k_baseline) * 2^(W * G) - k_alternate

    where G is the denormalized log2 gain and W is the headroom weight factor.

    Parameters
    ----------
    baseline : np.ndarray
        Linear baseline image (H, W, 3) or (H, W).
    gain_map : np.ndarray
        Normalized gain map in [0, 1], same spatial dims as baseline.
    g_min : float
        Minimum log2 gain from normalization metadata.
    g_max : float
        Maximum log2 gain from normalization metadata.
    gamma : float
        Gamma used during encoding.
    k_baseline : float
        Baseline offset constant.
    k_alternate : float
        Alternate offset constant.
    h_baseline : float
        Baseline HDR headroom.
    h_alternate : float
        Alternate HDR headroom.
    h_target : float, optional
        Target display headroom. Defaults to h_alternate (full gain).

    Returns
    -------
    np.ndarray
        Reconstructed alternate image, float32.
    """
    b = np.asarray(baseline, dtype=np.float32)
    gm = np.asarray(gain_map, dtype=np.float32)

    if h_target is None:
        h_target = h_alternate

    # Denormalize gain map to log2 domain
    g = denormalize_gain_map(gm, g_min, g_max, gamma=gamma)

    # Weight factor
    w = np.float32(compute_weight(h_target, h_baseline, h_alternate))

    # Apply: Alternate = (Baseline + k_baseline) * 2^(W * G) - k_alternate
    exponent = w * g
    alternate = (b + np.float32(k_baseline)) * np.power(np.float32(2.0), exponent) - np.float32(k_alternate)
    return np.maximum(alternate, 0.0).astype(np.float32, copy=False)
