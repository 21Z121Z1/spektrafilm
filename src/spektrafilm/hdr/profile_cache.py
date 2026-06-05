from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from spektrafilm.runtime.route_master import HDRMode


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


__all__ = ["RouteProfileCacheKey", "build_route_profile_cache_key"]
