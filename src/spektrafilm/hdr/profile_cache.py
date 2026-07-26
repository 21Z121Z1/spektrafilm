from __future__ import annotations

from collections import OrderedDict
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from spektrafilm.runtime.route_master import HDRMode

if TYPE_CHECKING:
    from spektrafilm.utils.hdr_curve_profiles import HDRCurveProfile


@dataclass(frozen=True, slots=True)
class RouteProfileCacheKey:
    hdr_mode: HDRMode
    route_kind: str
    film: str
    camera_exposure_compensation_ev: float
    auto_exposure_ev: float | None
    film_density_curve_gamma: float
    scanner_black_correction: bool
    scanner_white_correction: bool
    scanner_black_level: float
    scanner_white_level: float
    viewing_illuminant: str
    output_color_space: str
    paper: str | None = None
    print_density_curves_morph: tuple[Any, ...] | None = None
    print_exposure: float | None = None
    enlarger_neutral_filters: tuple[float, float, float] | None = None
    preflash_exposure: float | None = None
    paper_white_anchor_policy: str | None = None


def _profile_id(profile) -> str:
    info = getattr(profile, "info", None)
    for attr in ("name", "stock", "label"):
        value = getattr(info, attr, None)
        if value:
            return str(value)
    return str(getattr(profile, "profile_id", type(profile).__name__))


def _morph_key(morph) -> tuple[Any, ...]:
    values: list[tuple[str, Any]] = []
    for name in sorted(vars(morph)):
        value = getattr(morph, name)
        if isinstance(value, (int, float, str, bool, type(None))):
            values.append((name, value))
        elif isinstance(value, tuple):
            values.append((name, value))
    return tuple(values)


def build_route_profile_cache_key(
    params,
    *,
    hdr_mode: HDRMode,
    auto_exposure_ev: float | None = None,
) -> RouteProfileCacheKey:
    if hdr_mode not in ("light_table", "paper"):
        raise ValueError("hdr_mode must be 'light_table' or 'paper'.")

    film_illuminant = str(getattr(getattr(params.film, "info", None), "viewing_illuminant", "unknown"))
    key = RouteProfileCacheKey(
        hdr_mode=hdr_mode,
        route_kind="film_scan" if hdr_mode == "light_table" else "print_scan",
        film=_profile_id(params.film),
        camera_exposure_compensation_ev=float(params.camera.exposure_compensation_ev),
        auto_exposure_ev=None if auto_exposure_ev is None else float(auto_exposure_ev),
        film_density_curve_gamma=float(params.film_render.density_curve_gamma),
        scanner_black_correction=bool(params.scanner.black_correction),
        scanner_white_correction=bool(params.scanner.white_correction),
        scanner_black_level=float(params.scanner.black_level),
        scanner_white_level=float(params.scanner.white_level),
        viewing_illuminant=film_illuminant,
        output_color_space=str(params.io.output_color_space),
    )
    if hdr_mode == "light_table":
        return key

    paper_illuminant = str(getattr(getattr(params.print, "info", None), "viewing_illuminant", film_illuminant))
    return RouteProfileCacheKey(
        **{
            **asdict(key),
            "viewing_illuminant": paper_illuminant,
            "paper": _profile_id(params.print),
            "print_density_curves_morph": _morph_key(params.print_render.density_curves_morph),
            "print_exposure": float(params.enlarger.print_exposure),
            "enlarger_neutral_filters": (
                float(params.enlarger.c_filter_neutral),
                float(params.enlarger.m_filter_neutral),
                float(params.enlarger.y_filter_neutral),
            ),
            "preflash_exposure": float(params.enlarger.preflash_exposure),
            "paper_white_anchor_policy": "legacy_sdr_print_white",
        }
    )


_DYNAMIC_PRINT_PROFILE_CACHE: "OrderedDict[RouteProfileCacheKey, tuple[HDRCurveProfile | None, str]]" = OrderedDict()
_DYNAMIC_PRINT_PROFILE_CACHE_MAX = 16


def clear_dynamic_print_profile_cache() -> None:
    _DYNAMIC_PRINT_PROFILE_CACHE.clear()


def get_dynamic_print_curve_profile(
    params,
    *,
    auto_exposure_ev: float | None = None,
) -> "tuple[HDRCurveProfile | None, str]":
    """Resample the print-route chemical profile for the current tone params.

    Returns ``(profile, origin)``. The sampled profile follows the caller's
    tone adjustments (density curve gamma, print exposure, enlarger filters,
    curve morph, preflash) so the HDR shoulder metrics stay in sync with the
    SDR look; results are cached on the tone-parameter cache key. On any
    sampling failure the function returns ``(None, reason)`` and callers fall
    back to the static bundled profile.
    """

    from spektrafilm.utils.hdr_curve_profiles import (
        curve_profile_from_sample,
        sample_runtime_print_curve_profile,
    )

    try:
        key = build_route_profile_cache_key(
            params,
            hdr_mode="paper",
            auto_exposure_ev=auto_exposure_ev,
        )
    except (AttributeError, TypeError, ValueError) as exc:
        return None, f"dynamic_cache_key_failed:{type(exc).__name__}"

    entry = _DYNAMIC_PRINT_PROFILE_CACHE.get(key)
    if entry is not None:
        _DYNAMIC_PRINT_PROFILE_CACHE.move_to_end(key)
        profile, origin = entry
        if profile is None:
            return None, origin
        return profile, "dynamic_resample_cached"

    try:
        sample = sample_runtime_print_curve_profile(params=params)
        profile = curve_profile_from_sample(sample)
        origin = "dynamic_resample"
    except Exception as exc:  # noqa: BLE001 - sampling must never break export; fall back to bundled
        profile = None
        origin = f"dynamic_sampling_failed:{type(exc).__name__}"

    _DYNAMIC_PRINT_PROFILE_CACHE[key] = (profile, origin)
    while len(_DYNAMIC_PRINT_PROFILE_CACHE) > _DYNAMIC_PRINT_PROFILE_CACHE_MAX:
        _DYNAMIC_PRINT_PROFILE_CACHE.popitem(last=False)
    return profile, origin


_DYNAMIC_NEGATIVE_SCAN_RENDER_CACHE: "OrderedDict[RouteProfileCacheKey, tuple[dict[str, Any] | None, str]]" = OrderedDict()
_DYNAMIC_NEGATIVE_SCAN_RENDER_CACHE_MAX = 16


def clear_dynamic_negative_scan_render_cache() -> None:
    _DYNAMIC_NEGATIVE_SCAN_RENDER_CACHE.clear()


def get_dynamic_negative_scan_render_metadata(
    params,
    *,
    auto_exposure_ev: float | None = None,
) -> "tuple[dict[str, Any] | None, str]":
    """Calibrate negative-scan render references for the current tone params.

    Returns ``(render_metadata, origin)``. The metadata is derived from a
    deterministic neutral ramp through the film-scan route (see
    ``sample_runtime_negative_scan_render_metadata``), so the light-table
    positive render is composition-independent and follows film-side tone
    adjustments; results are cached on the film-scan cache key. On any
    sampling failure the function returns ``(None, reason)`` and callers
    fall back to the legacy content-statistics estimate.
    """

    from spektrafilm.utils.hdr_curve_profiles import (
        sample_runtime_negative_scan_render_metadata,
    )

    try:
        key = build_route_profile_cache_key(
            params,
            hdr_mode="light_table",
            auto_exposure_ev=auto_exposure_ev,
        )
    except (AttributeError, TypeError, ValueError) as exc:
        return None, f"dynamic_cache_key_failed:{type(exc).__name__}"

    entry = _DYNAMIC_NEGATIVE_SCAN_RENDER_CACHE.get(key)
    if entry is not None:
        _DYNAMIC_NEGATIVE_SCAN_RENDER_CACHE.move_to_end(key)
        metadata, origin = entry
        if metadata is None:
            return None, origin
        return dict(metadata), "dynamic_resample_cached"

    try:
        metadata = sample_runtime_negative_scan_render_metadata(params=params)
        origin = "dynamic_resample"
    except Exception as exc:  # noqa: BLE001 - sampling must never break export; fall back to content stats
        metadata = None
        origin = f"dynamic_sampling_failed:{type(exc).__name__}"

    _DYNAMIC_NEGATIVE_SCAN_RENDER_CACHE[key] = (metadata, origin)
    while len(_DYNAMIC_NEGATIVE_SCAN_RENDER_CACHE) > _DYNAMIC_NEGATIVE_SCAN_RENDER_CACHE_MAX:
        _DYNAMIC_NEGATIVE_SCAN_RENDER_CACHE.popitem(last=False)
    if metadata is None:
        return None, origin
    return dict(metadata), origin


__all__ = [
    "RouteProfileCacheKey",
    "build_route_profile_cache_key",
    "clear_dynamic_negative_scan_render_cache",
    "clear_dynamic_print_profile_cache",
    "get_dynamic_negative_scan_render_metadata",
    "get_dynamic_print_curve_profile",
]
