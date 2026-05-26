from __future__ import annotations

import numpy as np
import colour

from spektrafilm.color_management import is_aces_scene_linear_space


MIDDLE_GRAY_LUMINANCE = 0.184
MIN_METER_LUMINANCE = 1e-8
MAX_AUTO_EXPOSURE_EV = 12.0
SCENE_LINEAR_HIGHLIGHT_PERCENTILE = 80.0
SCENE_LINEAR_FLOOR_PERCENTILE = 1.0


def _effective_apply_cctf_decoding(color_space, apply_cctf_decoding):
    if is_aces_scene_linear_space(str(color_space)):
        return False
    return bool(apply_cctf_decoding)


def _luminance_y(image, color_space, apply_cctf_decoding):
    image = np.asarray(image)
    if image.ndim != 3 or image.shape[2] < 3:
        raise ValueError("Auto exposure requires an RGB image with shape (height, width, 3).")
    if image.shape[0] <= 0 or image.shape[1] <= 0:
        raise ValueError("Auto exposure cannot meter an empty image.")

    image_XYZ = colour.RGB_to_XYZ(
        image[:, :, :3],
        color_space,
        apply_cctf_decoding=_effective_apply_cctf_decoding(color_space, apply_cctf_decoding),
    )
    return np.asarray(image_XYZ[:, :, 1], dtype=np.float64)


def _meterable_luminance(image_y):
    image_y = np.asarray(image_y, dtype=np.float64)
    finite = np.isfinite(image_y)
    metered = np.zeros_like(image_y, dtype=np.float64)
    metered[finite] = np.maximum(image_y[finite], 0.0)
    return metered, finite


def _normalized_coords_from_shape(shape):
    """Return x, y coordinate arrays normalized so the long edge spans [-0.5, 0.5]."""
    height, width = int(shape[0]), int(shape[1])
    long_edge = max(height, width, 1)
    x = (np.arange(width, dtype=np.float64) / max(width, 1) - 0.5) * (width / long_edge)
    y = (np.arange(height, dtype=np.float64) / max(height, 1) - 0.5) * (height / long_edge)
    return x, y


def _center_weights(shape, sigma=0.2):
    x, y = _normalized_coords_from_shape(shape)
    weights = np.exp(-(x ** 2 + y[:, None] ** 2) / (2 * float(sigma) ** 2))
    total = float(np.sum(weights))
    if total <= 0.0 or not np.isfinite(total):
        return np.ones(shape, dtype=np.float64) / float(np.prod(shape))
    return weights / total


def _weighted_average(values, weights, finite):
    usable_weights = np.where(finite, weights, 0.0)
    total = float(np.sum(usable_weights))
    if total <= 0.0 or not np.isfinite(total):
        return None
    return float(np.sum(values * usable_weights) / total)


def _weighted_percentile(values, weights, percentile):
    values = np.asarray(values, dtype=np.float64).reshape(-1)
    weights = np.asarray(weights, dtype=np.float64).reshape(-1)
    valid = np.isfinite(values) & np.isfinite(weights) & (weights > 0.0)
    if not np.any(valid):
        return None

    values = values[valid]
    weights = weights[valid]
    order = np.argsort(values)
    values = values[order]
    weights = weights[order]
    cumulative = np.cumsum(weights)
    total = float(cumulative[-1])
    if total <= 0.0 or not np.isfinite(total):
        return None

    threshold = np.clip(float(percentile), 0.0, 100.0) / 100.0 * total
    index = int(np.searchsorted(cumulative, threshold, side="left"))
    return float(values[min(index, values.size - 1)])


def _finite_mean(values, finite):
    if not np.any(finite):
        return None
    return float(np.mean(values[finite]))


def _finite_median(values, finite):
    if not np.any(finite):
        return None
    return float(np.median(values[finite]))


def _scene_linear_log_average_luminance(values, finite):
    weights = _center_weights(values.shape)
    positive = finite & (values > MIN_METER_LUMINANCE)
    if not np.any(positive):
        return None

    positive_values = values[positive]
    positive_weights = weights[positive]
    high_cap = _weighted_percentile(
        positive_values,
        positive_weights,
        SCENE_LINEAR_HIGHLIGHT_PERCENTILE,
    )
    low_floor = _weighted_percentile(
        positive_values,
        positive_weights,
        SCENE_LINEAR_FLOOR_PERCENTILE,
    )
    if high_cap is None or low_floor is None:
        return None

    low_floor = max(float(low_floor) * 0.25, MIN_METER_LUMINANCE)
    high_cap = max(float(high_cap), low_floor)
    clipped = np.clip(values, low_floor, high_cap)
    return float(np.exp(_weighted_average(np.log(clipped), weights, finite)))


def _matrix_luminance(values, finite):
    h, w = values.shape
    n_rows = min(5, max(h, 1))
    n_cols = min(5, max(w, 1))
    row_edges = np.linspace(0, h, n_rows + 1, dtype=int)
    col_edges = np.linspace(0, w, n_cols + 1, dtype=int)
    zone_means = []
    zone_weights = []

    for r in range(n_rows):
        row_start, row_end = row_edges[r], row_edges[r + 1]
        for c in range(n_cols):
            col_start, col_end = col_edges[c], col_edges[c + 1]
            cell_values = values[row_start:row_end, col_start:col_end]
            cell_finite = finite[row_start:row_end, col_start:col_end]
            cell_mean = _finite_mean(cell_values, cell_finite)
            if cell_mean is None:
                continue
            zone_means.append(cell_mean)
            dy = 0.0 if n_rows == 1 else (r - (n_rows - 1) / 2) / ((n_rows - 1) / 2)
            dx = 0.0 if n_cols == 1 else (c - (n_cols - 1) / 2) / ((n_cols - 1) / 2)
            dist = np.sqrt(dx ** 2 + dy ** 2) / np.sqrt(2)
            zone_weights.append(max(0.0, 0.5 * (1.0 + np.cos(np.pi * dist))))

    if not zone_means:
        return None
    zone_weights = np.asarray(zone_weights, dtype=np.float64)
    total = float(np.sum(zone_weights))
    if total <= 0.0 or not np.isfinite(total):
        return float(np.mean(zone_means))
    return float(np.dot(zone_weights / total, np.asarray(zone_means, dtype=np.float64)))


def _partial_luminance(values, finite):
    x, y = _normalized_coords_from_shape(values.shape)
    radius = np.sqrt(x ** 2 + y[:, None] ** 2)
    mask = (radius < 0.15) & finite
    if not np.any(mask):
        mask = finite
    return _finite_mean(values, mask)


def _multi_zone_luminance(values, finite):
    x, y = _normalized_coords_from_shape(values.shape)
    radius = np.sqrt(x ** 2 + y[:, None] ** 2)
    ring_bounds = [(0.00, 0.05), (0.05, 0.25), (0.25, 0.50)]
    ring_weights = [0.50, 0.30, 0.20]
    weighted_sum = 0.0
    weight_total = 0.0
    for (r_min, r_max), weight in zip(ring_bounds, ring_weights):
        mask = (radius >= r_min) & (radius < r_max) & finite
        mean = _finite_mean(values, mask)
        if mean is None:
            continue
        weighted_sum += float(weight) * mean
        weight_total += float(weight)
    if weight_total <= 0.0:
        return _finite_mean(values, finite)
    return weighted_sum / weight_total


def _highlight_weighted_luminance(values, finite):
    weights = np.where(finite, values ** 2, 0.0)
    total = float(np.sum(weights))
    if total <= MIN_METER_LUMINANCE or not np.isfinite(total):
        weights = np.where(finite, 1.0, 0.0)
    return _weighted_average(values, weights, finite)


def _exposure_ev_from_luminance(luminance):
    if luminance is None:
        return 0.0
    luminance = float(luminance)
    if not np.isfinite(luminance) or luminance <= MIN_METER_LUMINANCE:
        return 0.0
    exposure_compensation_ev = np.log2(MIDDLE_GRAY_LUMINANCE / luminance)
    if not np.isfinite(exposure_compensation_ev):
        return 0.0
    return float(np.clip(exposure_compensation_ev, -MAX_AUTO_EXPOSURE_EV, MAX_AUTO_EXPOSURE_EV))


def measure_autoexposure_ev(image, color_space='sRGB', apply_cctf_decoding=True, method='center_weighted'):
    image_Y = _luminance_y(image, color_space, apply_cctf_decoding)
    values, finite = _meterable_luminance(image_Y)

    if method == 'scene_linear':
        luminance = _scene_linear_log_average_luminance(values, finite)
    elif method == 'average':
        luminance = _finite_mean(values, finite)
    elif method == 'median':
        luminance = _finite_median(values, finite)
    elif method == 'center_weighted':
        luminance = _weighted_average(values, _center_weights(values.shape), finite)
    elif method == 'partial':
        luminance = _partial_luminance(values, finite)
    elif method == 'matrix':
        luminance = _matrix_luminance(values, finite)
    elif method == 'multi_zone':
        luminance = _multi_zone_luminance(values, finite)
    elif method == 'highlight_weighted':
        luminance = _highlight_weighted_luminance(values, finite)
    else:
        raise ValueError(f"Unsupported auto exposure method: {method!r}")

    return _exposure_ev_from_luminance(luminance)


if __name__ == '__main__':
    import matplotlib.pyplot as plt
    image = np.random.uniform(0, 1, (3000, 2000, 3))
    exposure_ev = measure_autoexposure_ev(image)
    print(exposure_ev)
    plt.imshow(image)
    plt.show()
