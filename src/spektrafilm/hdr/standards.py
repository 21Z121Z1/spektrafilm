from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import colour
import numpy as np

_PQ_MAX_NITS: float = 10_000.0
_DEFAULT_REFERENCE_WHITE_NITS: float = 203.0
_DEFAULT_MIN_MASTERING_LUMINANCE_NITS: float = 0.005
_DEFAULT_APPLICATION_ID = "spektrafilm"
_DEFAULT_APPLICATION_VERSION = "1"
_LUMA_COEFFS = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def _finite_float(value: Any, *, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return float(default)
    if not math.isfinite(result):
        return float(default)
    return result


def _finite_float_tuple(values: Any, *, expected: int, label: str) -> tuple[float, ...]:
    arr = np.asarray(values, dtype=np.float32).reshape(-1)
    if arr.size != expected or not np.all(np.isfinite(arr)):
        raise ValueError(f"{label} must contain {expected} finite float values.")
    return tuple(float(v) for v in arr.tolist())


def _chromaticities_from_color_space(color_space: str) -> tuple[tuple[tuple[float, float], tuple[float, float], tuple[float, float]], tuple[float, float]]:
    try:
        cs = colour.RGB_COLOURSPACES[color_space]
    except KeyError as exc:
        raise ValueError(f"Unknown color space {color_space!r}.") from exc
    primaries = tuple((float(x), float(y)) for x, y in np.asarray(cs.primaries, dtype=np.float32))
    white_point = (float(cs.whitepoint[0]), float(cs.whitepoint[1]))
    return primaries, white_point


def _scene_luminance_summary(values: np.ndarray | None) -> dict[str, float] | None:
    if values is None:
        return None
    arr = np.asarray(values, dtype=np.float32)
    if arr.size == 0:
        return None
    flat = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0).reshape(-1)
    if flat.size == 0:
        return None
    return {
        "min": float(np.min(flat)),
        "p50": float(np.percentile(flat, 50.0)),
        "p90": float(np.percentile(flat, 90.0)),
        "p99": float(np.percentile(flat, 99.0)),
        "p999": float(np.percentile(flat, 99.9)),
        "max": float(np.max(flat)),
    }


def _luminance_summary(rgb: np.ndarray | None) -> dict[str, float] | None:
    if rgb is None:
        return None
    arr = np.asarray(rgb, dtype=np.float32)
    if arr.ndim != 3 or arr.shape[-1] < 3 or arr.size == 0:
        return None
    values = np.tensordot(arr[..., :3], _LUMA_COEFFS, axes=([-1], [0]))
    return _scene_luminance_summary(values)


def pq_nits_to_code_values(nits: np.ndarray | float) -> np.ndarray:
    values = np.asarray(nits, dtype=np.float32)
    return np.asarray(
        colour.models.eotf_inverse_BT2100_PQ(np.clip(values, 0.0, _PQ_MAX_NITS)),
        dtype=np.float32,
    )


def pq_code_values_to_nits(code_values: np.ndarray | float) -> np.ndarray:
    values = np.asarray(code_values, dtype=np.float32)
    return np.asarray(
        colour.models.eotf_BT2100_PQ(np.clip(values, 0.0, 1.0)),
        dtype=np.float32,
    )


@dataclass(frozen=True, slots=True)
class HDRStandardsMetadata:
    eotf: str
    mastering_primaries: tuple[tuple[float, float], tuple[float, float], tuple[float, float]]
    mastering_white_point: tuple[float, float]
    min_mastering_luminance_nits: float
    max_mastering_luminance_nits: float
    reference_white_nits: float
    mastering_scene_white: float | None = None
    mastering_look_white: float | None = None
    mastering_display_white_nits: float | None = None
    mastering_target_peak_ev: float | None = None
    mastering_curve_budget_ev: float | None = None
    application_id: str = _DEFAULT_APPLICATION_ID
    application_version: str = _DEFAULT_APPLICATION_VERSION
    time_interval: tuple[float, float] | None = None
    processing_window: tuple[int, int, int, int] | None = None
    target_display_primaries: tuple[tuple[float, float], tuple[float, float], tuple[float, float]] | None = None
    target_display_white_point: tuple[float, float] | None = None
    target_display_min_luminance_nits: float | None = None
    target_display_max_luminance_nits: float | None = None
    scene_statistics: dict[str, Any] = field(default_factory=dict)
    hdr_headroom: float | None = None
    encoded_color_space: str | None = None
    source_role: str | None = None
    schema: str = "spektrafilm.hdr.dynamic_metadata"
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.eotf, str) or not self.eotf:
            raise ValueError("eotf must be a non-empty string.")
        for label, primaries in (
            ("mastering_primaries", self.mastering_primaries),
            ("target_display_primaries", self.target_display_primaries),
        ):
            if primaries is None:
                continue
            if len(primaries) != 3:
                raise ValueError(f"{label} must contain exactly three primaries.")
            for pair in primaries:
                if len(pair) != 2 or not all(math.isfinite(float(v)) for v in pair):
                    raise ValueError(f"{label} must contain finite xy pairs.")
        for label, pair in (
            ("mastering_white_point", self.mastering_white_point),
            ("target_display_white_point", self.target_display_white_point),
        ):
            if pair is None:
                continue
            if len(pair) != 2 or not all(math.isfinite(float(v)) for v in pair):
                raise ValueError(f"{label} must be a finite xy pair.")
        for label, value in (
            ("min_mastering_luminance_nits", self.min_mastering_luminance_nits),
            ("max_mastering_luminance_nits", self.max_mastering_luminance_nits),
            ("reference_white_nits", self.reference_white_nits),
            ("mastering_scene_white", self.mastering_scene_white),
            ("mastering_look_white", self.mastering_look_white),
            ("mastering_display_white_nits", self.mastering_display_white_nits),
            ("mastering_target_peak_ev", self.mastering_target_peak_ev),
            ("mastering_curve_budget_ev", self.mastering_curve_budget_ev),
            ("target_display_min_luminance_nits", self.target_display_min_luminance_nits),
            ("target_display_max_luminance_nits", self.target_display_max_luminance_nits),
        ):
            if value is None:
                continue
            if not math.isfinite(float(value)):
                raise ValueError(f"{label} must be finite.")
        if self.min_mastering_luminance_nits < 0.0:
            raise ValueError("min_mastering_luminance_nits must be non-negative.")
        if self.max_mastering_luminance_nits <= self.min_mastering_luminance_nits:
            raise ValueError("max_mastering_luminance_nits must be greater than min_mastering_luminance_nits.")
        if self.reference_white_nits <= 0.0:
            raise ValueError("reference_white_nits must be positive.")
        if self.mastering_scene_white is not None and self.mastering_scene_white <= 0.0:
            raise ValueError("mastering_scene_white must be positive when provided.")
        if self.mastering_look_white is not None and self.mastering_look_white <= 0.0:
            raise ValueError("mastering_look_white must be positive when provided.")
        if self.mastering_display_white_nits is not None and self.mastering_display_white_nits <= 0.0:
            raise ValueError("mastering_display_white_nits must be positive when provided.")
        if self.mastering_target_peak_ev is not None and self.mastering_target_peak_ev <= 0.0:
            raise ValueError("mastering_target_peak_ev must be positive when provided.")
        if self.mastering_curve_budget_ev is not None and self.mastering_curve_budget_ev <= 0.0:
            raise ValueError("mastering_curve_budget_ev must be positive when provided.")
        if self.hdr_headroom is not None and self.hdr_headroom < 1.0:
            raise ValueError("hdr_headroom must be greater than or equal to 1.0 when provided.")
        if self.time_interval is not None:
            if len(self.time_interval) != 2 or not all(math.isfinite(float(v)) for v in self.time_interval):
                raise ValueError("time_interval must be a finite (start, end) pair.")
            if float(self.time_interval[0]) > float(self.time_interval[1]):
                raise ValueError("time_interval start must not exceed end.")
        if self.processing_window is not None:
            if len(self.processing_window) != 4:
                raise ValueError("processing_window must contain four integers.")
            if any(int(v) < 0 for v in self.processing_window):
                raise ValueError("processing_window values must be non-negative.")
        if self.schema_version < 1:
            raise ValueError("schema_version must be at least 1.")
        if self.encoded_color_space is not None and not self.encoded_color_space:
            raise ValueError("encoded_color_space must be non-empty when provided.")

    @property
    def mastering_display_max_luminance_nits(self) -> float:
        return float(self.max_mastering_luminance_nits)

    @classmethod
    def from_color_space(
        cls,
        color_space: str,
        *,
        eotf: str = "scene-linear",
        reference_white_nits: float = _DEFAULT_REFERENCE_WHITE_NITS,
        hdr_headroom: float | None = None,
        min_mastering_luminance_nits: float = _DEFAULT_MIN_MASTERING_LUMINANCE_NITS,
        mastering_scene_white: float | None = None,
        mastering_look_white: float | None = None,
        mastering_display_white_nits: float | None = None,
        mastering_target_peak_ev: float | None = None,
        mastering_curve_budget_ev: float | None = None,
        application_id: str = _DEFAULT_APPLICATION_ID,
        application_version: str = _DEFAULT_APPLICATION_VERSION,
        time_interval: tuple[float, float] | None = None,
        processing_window: tuple[int, int, int, int] | None = None,
        target_display_color_space: str | None = None,
        target_display_min_luminance_nits: float | None = None,
        target_display_max_luminance_nits: float | None = None,
        scene_luminance: np.ndarray | None = None,
        render_rgb: np.ndarray | None = None,
        source_role: str | None = None,
    ) -> HDRStandardsMetadata:
        mastering_primaries, mastering_white_point = _chromaticities_from_color_space(color_space)
        target_color_space = color_space if target_display_color_space is None else target_display_color_space
        target_primaries, target_white_point = _chromaticities_from_color_space(target_color_space)
        if hdr_headroom is not None:
            target_display_max = float(target_display_max_luminance_nits) if target_display_max_luminance_nits is not None else float(reference_white_nits) * float(hdr_headroom)
            mastering_max = target_display_max
        else:
            target_display_max = float(target_display_max_luminance_nits) if target_display_max_luminance_nits is not None else float(reference_white_nits)
            mastering_max = target_display_max
        scene_stats: dict[str, Any] = {
            "luminance_source": "scene_luminance" if scene_luminance is not None else ("render_luminance" if render_rgb is not None else None),
        }
        scene_summary = _scene_luminance_summary(scene_luminance)
        render_summary = _luminance_summary(render_rgb)
        if scene_summary is not None:
            scene_stats["scene_luminance"] = scene_summary
        if render_summary is not None:
            scene_stats["render_luminance"] = render_summary
        if scene_stats["luminance_source"] is None:
            scene_stats.pop("luminance_source")
        return cls(
            eotf=eotf,
            mastering_primaries=mastering_primaries,
            mastering_white_point=mastering_white_point,
            min_mastering_luminance_nits=float(min_mastering_luminance_nits),
            max_mastering_luminance_nits=float(mastering_max),
            reference_white_nits=float(reference_white_nits),
            mastering_scene_white=float(mastering_scene_white) if mastering_scene_white is not None else None,
            mastering_look_white=float(mastering_look_white) if mastering_look_white is not None else None,
            mastering_display_white_nits=(
                float(mastering_display_white_nits)
                if mastering_display_white_nits is not None
                else float(reference_white_nits)
            ),
            mastering_target_peak_ev=(
                float(mastering_target_peak_ev)
                if mastering_target_peak_ev is not None
                else None
            ),
            mastering_curve_budget_ev=(
                float(mastering_curve_budget_ev)
                if mastering_curve_budget_ev is not None
                else None
            ),
            application_id=application_id,
            application_version=application_version,
            time_interval=time_interval,
            processing_window=processing_window,
            target_display_primaries=target_primaries,
            target_display_white_point=target_white_point,
            target_display_min_luminance_nits=float(target_display_min_luminance_nits) if target_display_min_luminance_nits is not None else float(min_mastering_luminance_nits),
            target_display_max_luminance_nits=float(target_display_max),
            scene_statistics=scene_stats,
            hdr_headroom=float(hdr_headroom) if hdr_headroom is not None else None,
            encoded_color_space=color_space,
            source_role=source_role,
        )

    def to_exr_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "eotf": self.eotf,
            "masteringDisplayPrimaries": tuple(v for pair in self.mastering_primaries for v in pair),
            "masteringDisplayWhitePoint": self.mastering_white_point,
            "minMasteringLuminance": float(self.min_mastering_luminance_nits),
            "maxMasteringLuminance": float(self.max_mastering_luminance_nits),
            "referenceWhiteLuminance": float(self.reference_white_nits),
            "dynamicMetadataApplication": self.application_id,
            "dynamicMetadataVersion": self.application_version,
        }
        if self.target_display_primaries is not None:
            attrs["targetDisplayPrimaries"] = tuple(v for pair in self.target_display_primaries for v in pair)
        if self.target_display_white_point is not None:
            attrs["targetDisplayWhitePoint"] = self.target_display_white_point
        if self.target_display_min_luminance_nits is not None:
            attrs["targetDisplayMinLuminance"] = float(self.target_display_min_luminance_nits)
        if self.target_display_max_luminance_nits is not None:
            attrs["targetDisplayMaxLuminance"] = float(self.target_display_max_luminance_nits)
        if self.time_interval is not None:
            attrs["dynamicMetadataTimeInterval"] = tuple(float(v) for v in self.time_interval)
        if self.processing_window is not None:
            attrs["dynamicMetadataProcessingWindow"] = tuple(int(v) for v in self.processing_window)
        if self.hdr_headroom is not None:
            attrs["hdrHeadroom"] = float(self.hdr_headroom)
        if self.mastering_scene_white is not None:
            attrs["masteringSceneWhite"] = float(self.mastering_scene_white)
        if self.mastering_look_white is not None:
            attrs["masteringLookWhite"] = float(self.mastering_look_white)
        if self.mastering_display_white_nits is not None:
            attrs["masteringDisplayWhiteLuminance"] = float(self.mastering_display_white_nits)
        if self.mastering_target_peak_ev is not None:
            attrs["masteringTargetPeakEv"] = float(self.mastering_target_peak_ev)
        if self.mastering_curve_budget_ev is not None:
            attrs["masteringCurveBudgetEv"] = float(self.mastering_curve_budget_ev)
        if self.encoded_color_space is not None:
            attrs["hdrEncodedColorSpace"] = self.encoded_color_space
        if self.source_role is not None:
            attrs["hdrSourceRole"] = self.source_role
        return attrs

    def to_exr_attribute_items(self) -> tuple[tuple[str, Any], ...]:
        return tuple(self.to_exr_attributes().items())

    def to_json_dict(self) -> dict[str, Any]:
        def _pair_list(values: tuple[tuple[float, float], tuple[float, float], tuple[float, float]] | None) -> list[list[float]] | None:
            if values is None:
                return None
            return [[float(x), float(y)] for x, y in values]

        payload: dict[str, Any] = {
            "schema": self.schema,
            "schema_version": self.schema_version,
            "eotf": self.eotf,
            "mastering_display": {
                "primaries": _pair_list(self.mastering_primaries),
                "white_point": [float(v) for v in self.mastering_white_point],
                "min_luminance_nits": float(self.min_mastering_luminance_nits),
                "max_luminance_nits": float(self.max_mastering_luminance_nits),
            },
            "reference_white_nits": float(self.reference_white_nits),
            "mastering_summary": {
                "scene_white": None if self.mastering_scene_white is None else float(self.mastering_scene_white),
                "look_white": None if self.mastering_look_white is None else float(self.mastering_look_white),
                "display_white_nits": None if self.mastering_display_white_nits is None else float(self.mastering_display_white_nits),
                "target_peak_ev": None if self.mastering_target_peak_ev is None else float(self.mastering_target_peak_ev),
                "curve_budget_ev": None if self.mastering_curve_budget_ev is None else float(self.mastering_curve_budget_ev),
                "hdr_headroom": None if self.hdr_headroom is None else float(self.hdr_headroom),
            },
            "dynamic_metadata": {
                "application": {
                    "id": self.application_id,
                    "version": self.application_version,
                },
                "time_interval": None if self.time_interval is None else [float(v) for v in self.time_interval],
                "processing_window": None if self.processing_window is None else [int(v) for v in self.processing_window],
                "target_display": {
                    "primaries": _pair_list(self.target_display_primaries),
                    "white_point": None if self.target_display_white_point is None else [float(v) for v in self.target_display_white_point],
                    "min_luminance_nits": None if self.target_display_min_luminance_nits is None else float(self.target_display_min_luminance_nits),
                    "max_luminance_nits": None if self.target_display_max_luminance_nits is None else float(self.target_display_max_luminance_nits),
                },
                "scene_statistics": self.scene_statistics,
            },
        }
        if self.hdr_headroom is not None:
            payload["hdr_headroom"] = float(self.hdr_headroom)
        if self.encoded_color_space is not None:
            payload["encoded_color_space"] = self.encoded_color_space
        if self.source_role is not None:
            payload["source_role"] = self.source_role
        return payload


def build_hdr_standards_metadata(
    *,
    color_space: str,
    eotf: str = "scene-linear",
    reference_white_nits: float = _DEFAULT_REFERENCE_WHITE_NITS,
    hdr_headroom: float | None = None,
    min_mastering_luminance_nits: float = _DEFAULT_MIN_MASTERING_LUMINANCE_NITS,
    application_id: str = _DEFAULT_APPLICATION_ID,
    application_version: str = _DEFAULT_APPLICATION_VERSION,
    time_interval: tuple[float, float] | None = None,
    processing_window: tuple[int, int, int, int] | None = None,
    target_display_color_space: str | None = None,
    target_display_min_luminance_nits: float | None = None,
    target_display_max_luminance_nits: float | None = None,
    mastering_scene_white: float | None = None,
    mastering_look_white: float | None = None,
    mastering_display_white_nits: float | None = None,
    mastering_target_peak_ev: float | None = None,
    mastering_curve_budget_ev: float | None = None,
    scene_luminance: np.ndarray | None = None,
    render_rgb: np.ndarray | None = None,
    source_role: str | None = None,
) -> HDRStandardsMetadata:
    return HDRStandardsMetadata.from_color_space(
        color_space,
        eotf=eotf,
        reference_white_nits=reference_white_nits,
        hdr_headroom=hdr_headroom,
        min_mastering_luminance_nits=min_mastering_luminance_nits,
        application_id=application_id,
        application_version=application_version,
        time_interval=time_interval,
        processing_window=processing_window,
        target_display_color_space=target_display_color_space,
        target_display_min_luminance_nits=target_display_min_luminance_nits,
        target_display_max_luminance_nits=target_display_max_luminance_nits,
        mastering_scene_white=mastering_scene_white,
        mastering_look_white=mastering_look_white,
        mastering_display_white_nits=mastering_display_white_nits,
        mastering_target_peak_ev=mastering_target_peak_ev,
        mastering_curve_budget_ev=mastering_curve_budget_ev,
        scene_luminance=scene_luminance,
        render_rgb=render_rgb,
        source_role=source_role,
    )


def write_hdr_standards_sidecar(filename: str | Path, metadata: HDRStandardsMetadata) -> Path:
    output_path = Path(filename)
    sidecar_path = output_path.with_suffix(".hdr.json")
    sidecar_path.write_text(
        json.dumps(metadata.to_json_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return sidecar_path
