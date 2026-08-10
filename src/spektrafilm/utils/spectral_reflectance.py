from __future__ import annotations

from functools import lru_cache

import numpy as np
from opt_einsum import contract

from spektrafilm.model.illuminants import standard_illuminant
from spektrafilm.utils.fast_interp_lut import apply_lut_cubic_2d
from spektrafilm.utils.spectral_lut_registry import (
    spectral_lut_descriptor,
    spectral_lut_resource,
)
from spektrafilm.utils.spectral_upsampling import (
    HANATOS2025_NO_ADAPTATION,
    _illuminant_to_xy,
    _rgb_to_tc_b,
    _tri2quad,
    compute_hanatos2025_tc_lut,
    rgb_to_raw_hanatos2025,
)


@lru_cache(maxsize=None)
def get_spectral_lut_spectra(identifier: str) -> np.ndarray:
    """Lazy-load one spectral reconstruction LUT as float64.

    LUTs are intentionally not imported eagerly: each shipped 192x192x81
    reflectance table is about 6 MiB on disk, and only the selected method
    should consume resident memory.
    """
    descriptor = spectral_lut_descriptor(identifier)
    resource = spectral_lut_resource(identifier)
    with resource.open("rb") as file:
        spectra = np.double(np.load(file))

    array = descriptor.get("array", {})
    expected_shape = (
        int(array.get("lut_size", spectra.shape[0])),
        int(array.get("lut_size", spectra.shape[1])),
        int(array.get("bands", spectra.shape[2])),
    )
    if spectra.shape != expected_shape:
        raise ValueError(
            f"spectral LUT {identifier!r} has shape {spectra.shape}, "
            f"expected {expected_shape} from descriptor"
        )
    return spectra


def compute_reflectance_tc_lut(
    identifier: str,
    sensitivity,
    reference_illuminant: str,
    *,
    spectra_lut=None,
    gamut_compress=None,
):
    """Build a raw tc LUT from a reflectance-family spectral reconstruction.

    The reconstruction is defined under the descriptor's scene illuminant.
    At build time it is relit by the film reference illuminant, integrated
    against the film sensitivity, white-balanced on the method's own emitted
    neutral, and exposure-normalized so the descriptor's linear-RGB midgray
    maps to raw 1 in every channel. The per-pixel runtime remains the same tc
    lookup plus linear brightness scale used by the existing Hanatos path.
    """
    descriptor = spectral_lut_descriptor(identifier)
    if descriptor.get("kind") != "reflectance":
        raise ValueError(
            f"{identifier!r} is kind={descriptor.get('kind')!r}, not 'reflectance'"
        )

    if spectra_lut is None:
        spectra_lut = get_spectral_lut_spectra(identifier)

    reference_spd = standard_illuminant(reference_illuminant)[:]
    relit = spectra_lut * reference_spd[None, None, :]
    raw_lut = contract("ijl,lm->ijm", relit, sensitivity)

    reflectance = descriptor["reflectance"]
    scene_illuminant = reflectance["scene_illuminant"]
    midgray = float(reflectance["midgray"])
    if not np.isfinite(midgray) or midgray <= 0.0:
        raise ValueError(
            f"spectral LUT {identifier!r} has invalid reflectance midgray {midgray!r}"
        )

    scene_xy = _illuminant_to_xy(scene_illuminant)
    white_tc = _tri2quad(scene_xy)
    neutral_reflectance = apply_lut_cubic_2d(
        spectra_lut,
        np.asarray(white_tc).reshape(1, 1, 2),
    )[0, 0]
    raw_neutral = np.einsum(
        "l,lm->m",
        neutral_reflectance * reference_spd,
        sensitivity,
    )
    if np.any(np.abs(raw_neutral) < 1e-12):
        raise ValueError(f"spectral LUT {identifier!r} produced a zero neutral response")

    # First remove the reconstructed neutral's per-channel chroma.  This is
    # channel-generic (C=1 works for B&W) and keeps the scene-white tc cell
    # achromatic.  Then restore the exposure convention that was accidentally
    # dropped by upstream's 2026-07-02 B&W normalization refactor: for a linear
    # RGB neutral at value m, RGB->XYZ adapted to the scene white has Y=m and
    # brightness b=X+Y+Z=m/y_scene.  Therefore the neutral tc-LUT value must be
    # y_scene/m for runtime `lut(tc) * b` to produce raw=(1,...,1).
    raw_lut = raw_lut / raw_neutral
    exposure_anchor = float(scene_xy[1]) / midgray
    raw_lut = raw_lut * exposure_anchor

    if gamut_compress is not None and gamut_compress.active:
        from spektrafilm.utils.gamut_compression import remap_tc_lut_for_compression

        raw_lut = remap_tc_lut_for_compression(raw_lut, scene_xy, gamut_compress)

    return raw_lut


def rgb_to_raw_reflectance(
    identifier: str,
    rgb,
    sensitivity,
    color_space: str,
    apply_cctf_decoding: bool,
    reference_illuminant: str,
    *,
    tc_lut=None,
    scene_illuminant=None,
):
    """Convert RGB through a reflectance-family spectral reconstruction."""
    descriptor = spectral_lut_descriptor(identifier)
    if descriptor.get("kind") != "reflectance":
        raise ValueError(
            f"{identifier!r} is kind={descriptor.get('kind')!r}, not 'reflectance'"
        )
    if scene_illuminant is None:
        scene_illuminant = descriptor["reflectance"]["scene_illuminant"]

    tc_raw, brightness = _rgb_to_tc_b(
        rgb,
        color_space=color_space,
        apply_cctf_decoding=apply_cctf_decoding,
        reference_illuminant=scene_illuminant,
    )
    if tc_lut is None:
        tc_lut = compute_reflectance_tc_lut(
            identifier,
            sensitivity,
            reference_illuminant,
        )
    raw = apply_lut_cubic_2d(tc_lut, tc_raw)
    raw *= brightness[..., None]
    return raw


def compute_spectral_tc_lut(
    method: str,
    sensitivity,
    reference_illuminant=None,
    *,
    spectra_lut=None,
    gamut_compress=None,
    hanatos2025_adaptation=None,
):
    """Generic tc-LUT builder while preserving the existing Hanatos implementation."""
    kind = spectral_lut_descriptor(method).get("kind")
    if kind == "reflectance":
        if reference_illuminant is None:
            raise ValueError("reference_illuminant is required for reflectance LUTs")
        return compute_reflectance_tc_lut(
            method,
            sensitivity,
            reference_illuminant,
            spectra_lut=spectra_lut,
            gamut_compress=gamut_compress,
        )
    if kind == "irradiance":
        adaptation = (
            hanatos2025_adaptation
            if hanatos2025_adaptation is not None
            else HANATOS2025_NO_ADAPTATION
        )
        return compute_hanatos2025_tc_lut(
            sensitivity,
            adaptation,
            gamut_compress=gamut_compress,
        )
    raise ValueError(f"method {method!r} has unsupported LUT kind {kind!r}")


def rgb_to_raw_spectral(
    method: str,
    rgb,
    sensitivity,
    color_space: str,
    apply_cctf_decoding: bool,
    reference_illuminant: str,
    *,
    tc_lut=None,
    scene_illuminant=None,
):
    """Generic runtime dispatch for shipped spectral reconstruction methods."""
    kind = spectral_lut_descriptor(method).get("kind")
    if kind == "reflectance":
        return rgb_to_raw_reflectance(
            method,
            rgb,
            sensitivity,
            color_space,
            apply_cctf_decoding,
            reference_illuminant,
            tc_lut=tc_lut,
            scene_illuminant=scene_illuminant,
        )
    if kind == "irradiance":
        return rgb_to_raw_hanatos2025(
            rgb,
            sensitivity,
            color_space=color_space,
            apply_cctf_decoding=apply_cctf_decoding,
            reference_illuminant=reference_illuminant,
            tc_lut=tc_lut,
        )
    raise ValueError(f"method {method!r} has unsupported LUT kind {kind!r}")
