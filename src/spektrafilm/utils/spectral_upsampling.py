import importlib.resources
import struct
import warnings
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

import colour
import numpy as np
import scipy
from opt_einsum import contract
import scipy.interpolate
import scipy.special

from spektrafilm.utils.fast_interp_lut import apply_lut_cubic_2d
from spektrafilm.config import SPECTRAL_SHAPE, STANDARD_OBSERVER_CMFS
from spektrafilm.model.illuminants import standard_illuminant


NegativeRGBPolicy = Literal["clip", "warn", "error", "compress"]
XYOutOfBoundsPolicy = Literal["clip", "warn", "error"]


@dataclass(frozen=True, slots=True)
class SpectralInputPolicy:
    """Preflight policy for RGB values entering spectral upsampling."""

    negative_rgb: NegativeRGBPolicy = "clip"
    xy_out_of_bounds: XYOutOfBoundsPolicy = "clip"
    report_stats: bool = True

    def __post_init__(self) -> None:
        if self.negative_rgb not in ("clip", "warn", "error", "compress"):
            raise ValueError(f"Unsupported negative RGB policy: {self.negative_rgb!r}.")
        if self.xy_out_of_bounds not in ("clip", "warn", "error"):
            raise ValueError(f"Unsupported xy out-of-bounds policy: {self.xy_out_of_bounds!r}.")


DEFAULT_SPECTRAL_INPUT_POLICY = SpectralInputPolicy()
_SQRT2PI = float(np.sqrt(2.0 * np.pi))


def _resolve_input_policy(policy: SpectralInputPolicy | None) -> SpectralInputPolicy:
    if policy is None:
        return DEFAULT_SPECTRAL_INPUT_POLICY
    return policy


def _policy_message(
    values: np.ndarray,
    mask: np.ndarray,
    *,
    context: str,
    issue: str,
    report_stats: bool,
) -> str:
    if not report_stats:
        return f"{context}: {issue}."

    invalid_values = np.asarray(values)[mask]
    component_count = int(np.count_nonzero(mask))
    total_components = int(mask.size)
    if mask.ndim >= 1:
        pixel_mask = np.any(mask, axis=-1)
        pixel_count = int(np.count_nonzero(pixel_mask))
        total_pixels = int(pixel_mask.size)
    else:
        pixel_count = component_count
        total_pixels = total_components

    if invalid_values.size:
        min_value = float(np.nanmin(invalid_values))
        max_value = float(np.nanmax(invalid_values))
    else:
        min_value = float("nan")
        max_value = float("nan")

    return (
        f"{context}: {issue}; affected {pixel_count}/{total_pixels} pixels "
        f"({component_count}/{total_components} components), "
        f"invalid range [{min_value:.6g}, {max_value:.6g}]."
    )


def _handle_negative_rgb(
    values: np.ndarray,
    policy: SpectralInputPolicy,
    *,
    context: str,
) -> np.ndarray:
    rgb = np.asarray(values)
    negative_mask = rgb < 0.0
    if not np.any(negative_mask):
        return rgb

    message = _policy_message(
        rgb,
        negative_mask,
        context=context,
        issue="negative RGB values encountered",
        report_stats=policy.report_stats,
    )
    if policy.negative_rgb == "error":
        raise ValueError(message)
    if policy.negative_rgb == "warn":
        warnings.warn(message, RuntimeWarning, stacklevel=3)
    if policy.negative_rgb == "compress":
        min_channel = np.minimum(np.nanmin(rgb, axis=-1, keepdims=True), 0.0)
        return rgb - min_channel
    return np.maximum(rgb, 0.0)


def _handle_xy_out_of_bounds(
    xy: np.ndarray,
    policy: SpectralInputPolicy,
    *,
    context: str,
) -> np.ndarray:
    xy = np.asarray(xy)
    out_of_bounds_mask = (xy < 0.0) | (xy > 1.0)
    if not np.any(out_of_bounds_mask):
        return xy

    message = _policy_message(
        xy,
        out_of_bounds_mask,
        context=context,
        issue="xy chromaticities outside [0, 1] encountered",
        report_stats=policy.report_stats,
    )
    if policy.xy_out_of_bounds == "error":
        raise ValueError(message)
    if policy.xy_out_of_bounds == "warn":
        warnings.warn(message, RuntimeWarning, stacklevel=3)
    return np.clip(xy, 0.0, 1.0)

################################################################################
# LUT generatation of irradiance spectra for any xy chromaticity
# Thanks to hanatos for providing luts and sample code to develop this. I am grateful.

def _load_coeffs_lut(filename='hanatos_irradiance_xy_coeffs_250304.lut'):
    # load lut of coefficients for efficient computations of irradiance spectra
    # formatting
    header_fmt = '=4i'
    header_len = struct.calcsize(header_fmt)
    pixel_fmt = '=4f'
    pixel_len = struct.calcsize(pixel_fmt)

    package = importlib.resources.files('spektrafilm.data.luts.spectral_upsampling')
    resource = package / filename
    with resource.open("rb") as file:
        header = file.read(header_len)
        _, _, width, height = struct.Struct(header_fmt).unpack_from(header)
        px = [[0] * height for _ in range(width)]
        for j in range(height):
            for i in range(width):
                data = file.read(pixel_len)
                px[i][j] = struct.Struct(pixel_fmt).unpack_from(data)
    return np.array(px)

def _tri2quad(tc):
    # converts triangular coordinates into square coordinates.
    # for better sampling of the visible locus of xy chromaticities.
    # the lut is represented in triangular coordinates
    tc = np.array(tc)
    tx = tc[...,0]
    ty = tc[...,1]
    y = ty / np.fmax(1.0 - tx, 1e-10)
    x = (1.0 - tx)*(1.0 - tx)
    x = np.clip(x, 0, 1)
    y = np.clip(y, 0, 1)
    return np.stack((x,y), axis=-1)

def _quad2tri(xy):
    # converts square coordinates into triangular coordinates
    x = xy[...,0]
    y = xy[...,1]
    tx = 1 - np.sqrt(x)
    ty = y * np.sqrt(x)
    return np.stack((tx,ty), axis=-1)

def _fetch_coeffs(tc, lut_coeffs):
    # find the coefficients for spectral upsampling of given rgb coordinates
    # if color_space!='ITU-R BT.2020' or apply_cctf_decoding:
    #     rgb = colour.RGB_to_RGB(rgb, input_colourspace=color_space, apply_cctf_decoding=apply_cctf_decoding,
    #                                     output_colourspace='ITU-R BT.2020', apply_cctf_encoding=False)
    #     rgb = np.clip(rgb,0,1)
    # xyz = colour.RGB_to_XYZ(rgb, colourspace='ITU-R BT.2020', apply_cctf_decoding=False)
    # b = np.sum(xyz, axis=-1)
    # xy = xyz[...,0:2] / b[...,None]
    # tc = _tri2quad(xy)
    coeffs = np.zeros(np.concatenate((tc.shape[:-1],[4])))
    x = np.linspace(0,1,lut_coeffs.shape[0])
    for i in np.arange(4):
        coeffs[...,i] = scipy.interpolate.RegularGridInterpolator((x,x), lut_coeffs[:,:,i], method='cubic')(tc)
    return coeffs

def _compute_spectra_from_coeffs(coeffs, smooth_steps=1):
    wl = SPECTRAL_SHAPE.wavelengths
    wl_up = np.linspace(360,800,441) # upsampled wl for finer initial calculation 0.5 nm
    x = (coeffs[...,0,None] * wl_up + coeffs[...,1,None])*  wl_up  + coeffs[...,2,None]
    y = 1.0 / np.sqrt(x * x + 1.0)
    spectra = 0.5 * x * y +  0.5
    spectra /= coeffs[...,3][...,None]
    
    # gaussian smooth with smooth_step*sigmas and downsample
    step = np.mean(np.diff(wl))
    spectra = scipy.ndimage.gaussian_filter(spectra, step*smooth_steps, axes=-1)
    def interp_slice(a, wl, wl_up):
        return np.interp(wl, wl_up, a)
    spectra = np.apply_along_axis(interp_slice, axis=-1, wl=wl, wl_up=wl_up, arr=spectra)
    return spectra

def compute_lut_spectra(lut_size=128, smooth_steps=1, lut_coeffs_filename='hanatos_irradiance_xy_coeffs_250304.lut'):
    v = np.linspace(0,1,lut_size)
    tx,ty = np.meshgrid(v,v, indexing='ij')
    tc = np.stack((tx,ty), axis=-1)
    lut_coeffs = _load_coeffs_lut(lut_coeffs_filename)
    coeffs = _fetch_coeffs(tc, lut_coeffs)
    lut_spectra = _compute_spectra_from_coeffs(coeffs, smooth_steps=smooth_steps)
    lut_spectra = np.array(lut_spectra, dtype=np.half)
    return lut_spectra

def _load_hanatos2025_spectra_lut(filename='irradiance_xy_tc.npy'):
    data_path = importlib.resources.files('spektrafilm.data.luts.spectral_upsampling').joinpath(filename)
    with data_path.open('rb') as file:
        spectra_lut = np.double(np.load(file))
    return spectra_lut

def _illuminant_to_xy(illuminant_label):
    illu = standard_illuminant(illuminant_label)
    xyz = np.zeros((3))
    for i in np.arange(3):
        xyz[i] = np.sum(illu * STANDARD_OBSERVER_CMFS[:][:,i])
    xy = xyz[0:2] / np.sum(xyz)
    return xy

def _rgb_to_tc_b(
    rgb,
    color_space='ITU-R BT.2020',
    apply_cctf_decoding=False,
    reference_illuminant='D55',
    input_policy: SpectralInputPolicy | None = None,
):
    input_policy = _resolve_input_policy(input_policy)
    rgb = _handle_negative_rgb(
        np.asarray(rgb),
        input_policy,
        context="Hanatos spectral upsampling RGB input",
    )
    # source_cs = colour.RGB_COLOURSPACES[color_space]
    # target_cs = source_cs.copy()
    # target_cs.whitepoint = ILLUMINANTS['CIE 1931 2 Degree Standard Observer']['D65']
    # adapted_rgb = colour.RGB_to_RGB(rgb, input_colourspace=source_cs,
    #                                 output_colourspace=target_cs,
    #                                 adaptation_transform='Bradford')    
    # illu_xy = colour.CCS_ILLUMINANTS['CIE 1931 2 Degree Standard Observer'][reference_illuminant]
    illu_xy = _illuminant_to_xy(reference_illuminant)
    xyz = colour.RGB_to_XYZ(rgb, colourspace=color_space,
                            apply_cctf_decoding=apply_cctf_decoding,
                            illuminant=illu_xy,
                            chromatic_adaptation_transform='CAT02')
    b = np.sum(xyz, axis=-1)
    xy = xyz[...,0:2] / np.fmax(b[...,None], 1e-10)
    xy = _handle_xy_out_of_bounds(
        xy,
        input_policy,
        context="Hanatos spectral upsampling xy chromaticity",
    )
    tc = _tri2quad(xy)
    b = np.nan_to_num(b)
    return tc, b

################################################################################
# hanatos2025 sensitivity adaptation


def _radial_mobius_warp_xy(
    xy: np.ndarray,
    center: tuple[float, float],
    alpha: float,
) -> np.ndarray:
    cx, cy = center
    dx = xy[..., 0] - cx
    dy = xy[..., 1] - cy
    d = np.sqrt(dx * dx + dy * dy)
    scale = 1.0 / (1.0 + alpha * d)
    wxy = np.zeros_like(xy)
    wxy[..., 0] = cx + dx * scale
    wxy[..., 1] = cy + dy * scale
    return wxy


def poly2d_deg3(
    tc: np.ndarray,
    params: np.ndarray,
    center_tc: tuple[float, float] = (0.0, 0.0),
) -> np.ndarray:
    """Evaluate a degree-3 polynomial
    """
    x = tc[..., 0] - center_tc[0]
    y = tc[..., 1] - center_tc[1]
    x2 = x * x
    y2 = y * y
    xy_term = x * y
    c0, c1, c2, c3, c4, c5, c6, c7, c8, c9 = params
    return (
        c0 + c1 * x + c2 * y + c3 * x2 + c4 * y2 + c5 * xy_term
        + c6 * (x2 * x) + c7 * (y2 * y) + c8 * (x2 * y) + c9 * (x * y2)
    )

def locked_logistic_rising(
    x: np.ndarray, mu: float, sigma: float, nu: float,
) -> np.ndarray:
    """Rising flex-and-sigma-locked logistic.

    Locked through (μ, ½) with maximum slope `S = 1/(σ·√(2π))`. ν > 0
    bends the tails (ν=1 ≈ erf in shape; ν<1 fattens the lower tail,
    ν>1 thins it). Inputs may broadcast freely.
    """
    nu = np.maximum(np.asarray(nu, dtype=float), 1e-5)
    S = 1.0 / (sigma * _SQRT2PI)
    k = (2.0 * nu * S) / (1.0 - 2.0 ** (-nu))
    exponent = np.clip(-k * (x - mu), -500.0, 500.0)
    nu_log2 = nu * np.log(2.0)
    log_q = np.where(
        nu_log2 > 50.0,
        nu_log2 + np.log1p(-np.exp(-nu_log2)),
        np.log(np.expm1(nu_log2)),
    )
    log_denom = np.logaddexp(0.0, log_q + exponent)
    return np.exp(-(1.0 / nu) * log_denom)


def eval_poly3_warp_log_exposure_surface(params, illuminant_xy) -> np.ndarray:
    """Evaluate a degree-3 polynomial surface after warping in xy, then mapping back to tc."""
    # Warp xy coordinate with the mobius warp, which is a radial compression towards the illuminant chromaticity.
    # This is to better sample the spectra of chromaticities close to the illuminant
    # and stabilize the surface for large chromaticity shifts.
    surface_size = HANATOS2025_SPECTRA_LUT.shape[0]
    tc_base = np.linspace(0,1,surface_size)
    tc = np.stack(np.meshgrid(tc_base, tc_base, indexing='ij'), axis=-1)
    xy = _quad2tri(tc)
    tc_center = _tri2quad(illuminant_xy)
    surface_log_exposure_correction = np.zeros((surface_size, surface_size,3))
    for i in range(3):
        xy_warped = _radial_mobius_warp_xy(xy, illuminant_xy, alpha=float(params[i,10]))
        tc_warped = _tri2quad(xy_warped)
        surface_log_exposure_correction[...,i] = poly2d_deg3(tc_warped, params[i,:10], center_tc=tc_center)
    return surface_log_exposure_correction

def eval_logiflex8_spectral_bandpass(params: np.ndarray) -> np.ndarray:
    """8-param logiflex window: erf6 skeleton + (nu_uv, nu_ir) shared across channels.

    params: (c_uv_base, sigma_uv, c_ir_base, sigma_ir, c_uv_b, c_ir_r, nu_uv, nu_ir).
    """
    wavelengths = SPECTRAL_SHAPE.wavelengths
    (c_uv_base, sigma_uv, c_ir_base, sigma_ir,
     c_uv_b, c_ir_r, nu_uv, nu_ir) = params
    cuv = np.array([c_uv_base, c_uv_base, c_uv_b], dtype=float)
    cir = np.array([c_ir_r, c_ir_base, c_ir_base], dtype=float)
    w = wavelengths[:, None]
    edge_uv = locked_logistic_rising(w, cuv[None, :], sigma_uv, nu_uv)
    edge_ir = 1.0 - locked_logistic_rising(w, cir[None, :], sigma_ir, nu_ir)
    return edge_uv * edge_ir

def eval_erf4_spectral_bandpass(params: np.ndarray) -> np.ndarray:
    """4-param erf window: two independent erf edges per channel.

    params: (c_uv_r, sigma_uv_r, c_ir_r, sigma_ir_r).
    """
    _SQRT2 = float(np.sqrt(2.0))
    wavelengths = SPECTRAL_SHAPE.wavelengths
    c_uv_r, sigma_uv_r, c_ir_r, sigma_ir_r = params
    cuv = np.array([c_uv_r, c_uv_r, 0], dtype=float)
    cir = np.array([c_ir_r, c_ir_r, 0], dtype=float)
    w = wavelengths[:, None]
    edge_uv = 0.5 * (1.0 + scipy.special.erf((w - cuv[None, :]) / (sigma_uv_r * _SQRT2)))
    edge_ir = 0.5 * (1.0 - scipy.special.erf((w - cir[None, :]) / (sigma_ir_r * _SQRT2)))
    return edge_uv * edge_ir


def eval_spectral_bandpass(params: np.ndarray, model: str = 'logiflex8') -> np.ndarray:
    if model == 'logiflex8':
        return eval_logiflex8_spectral_bandpass(params)
    if model == 'erf4':
        return eval_erf4_spectral_bandpass(params)
    raise ValueError(f"Unknown spectral bandpass model: {model}")

################################################################################
# From [Mallett2019]

MALLETT2019_BASIS = colour.recovery.MSDS_BASIS_FUNCTIONS_sRGB_MALLETT2019.copy().align(SPECTRAL_SHAPE)
def rgb_to_raw_mallett2019(RGB, sensitivity,
                           color_space='sRGB', apply_cctf_decoding=True,
                           reference_illuminant='D65',
                           input_policy: SpectralInputPolicy | None = None):
    """
    Converts an RGB color to a raw sensor response using the method described in Mallett et al. (2019).

    Parameters
    ----------
    RGB : array_like
        RGB color values.
    illuminant : array_like
        Illuminant spectral distribution.
    sensitivity : array_like
        Camera sensor spectral sensitivities.
    color_space : str, optional
        The color space of the input RGB values. Default is 'sRGB'.
    apply_cctf_decoding : bool, optional
        Whether to apply the color component transfer function (CCTF) decoding. Default is True.

    Returns
    -------
    raw : ndarray
        Raw sensor response.
    """
    input_policy = _resolve_input_policy(input_policy)
    illuminant = standard_illuminant(reference_illuminant)[:]
    basis_set_with_illuminant = np.array(MALLETT2019_BASIS[:])*np.array(illuminant)[:, None]
    lrgb = colour.RGB_to_RGB(RGB, color_space, 'sRGB',
                    apply_cctf_decoding=apply_cctf_decoding,
                    apply_cctf_encoding=False)
    lrgb = _handle_negative_rgb(
        lrgb,
        input_policy,
        context="Mallett2019 linear sRGB",
    )
    raw  = contract('ijk,lk,lm->ijm', lrgb, basis_set_with_illuminant, sensitivity)
    raw = np.nan_to_num(raw)
    raw = np.ascontiguousarray(raw)

    raw_midgray  = np.einsum('k,km->m', illuminant*0.184, sensitivity) # use 0.184 as midgray reference
    return raw / raw_midgray[1] # normalize with green channel

################################################################################
# Using hanatos irradiance spectra generation

HANATOS2025_SPECTRA_LUT = _load_hanatos2025_spectra_lut()

def compute_hanatos2025_tc_lut(sensitivity, spectra_lut=HANATOS2025_SPECTRA_LUT):
    raw_lut = contract('ijl,lm->ijm', spectra_lut, sensitivity)
    return raw_lut

def compute_hanatos2025_adaptation_tc_lut(sensitivity,
                                          bandpass_params,
                                          surface_params,
                                          reference_illuminant,
                                          spectra_lut=HANATOS2025_SPECTRA_LUT):

    bandpass = eval_spectral_bandpass(bandpass_params)

    xy_illu = _illuminant_to_xy(reference_illuminant)
    surface = eval_poly3_warp_log_exposure_surface(surface_params,
                                                   illuminant_xy=xy_illu)

    raw_lut = contract('ijl,lm->ijm', spectra_lut, sensitivity*bandpass)
    raw_lut *= 2**surface
    return raw_lut

def rgb_to_raw_hanatos2025(rgb, sensitivity,
                           color_space,
                           apply_cctf_decoding,
                           reference_illuminant,
                           sensitivity_adaptation=False,
                           bandpass_params=None,
                           surface_params=None,
                           tc_lut=None,
                           input_policy: SpectralInputPolicy | None = None):
    tc_raw, b = _rgb_to_tc_b(
        rgb,
        color_space=color_space,
        apply_cctf_decoding=apply_cctf_decoding,
        reference_illuminant=reference_illuminant,
        input_policy=input_policy,
    )
    if tc_lut is None: # fallback to on-the-fly computation if tc_lut not provided
        if sensitivity_adaptation:
            tc_lut = compute_hanatos2025_adaptation_tc_lut(sensitivity,
                                                          bandpass_params=bandpass_params,
                                                          surface_params=surface_params,
                                                          reference_illuminant=reference_illuminant)
        else:
            tc_lut  = compute_hanatos2025_tc_lut(sensitivity)
    raw = apply_lut_cubic_2d(tc_lut, tc_raw)
    raw *= b[...,None] # scale the raw back with the scale factor
    # note that sensitivities are already normalized in balancing such that raw_midgray is 1, so no need to normalize here
    return raw


# ---------------------------------------------------------------------------
# Backend-aware variant: precompute CPU constants, execute per-pixel on GPU
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def precompute_hanatos2025_constants(color_space, apply_cctf_decoding, reference_illuminant):
    """CPU-only: return (M_rgb_to_xyz, cctf_decode_fn_or_None, illu_xy).

    ``M_rgb_to_xyz`` already includes the CAT02 adaptation to
    *reference_illuminant*.  If *apply_cctf_decoding* the caller must decode
    the CCTF first (on the backend) before multiplying; this helper records
    a callable for that purpose.
    """
    from spektrafilm.gpu.kernels.color import precompute_rgb_to_xyz_matrix as _pre_m
    illu_xy = _illuminant_to_xy(reference_illuminant)
    M = _pre_m(color_space, illuminant_xy=illu_xy, cat='CAT02')

    cctf_decode = None
    if apply_cctf_decoding:
        cs = colour.RGB_COLOURSPACES[color_space]
        cctf_decode = cs.cctf_decoding
    return M, cctf_decode, illu_xy


def rgb_to_raw_hanatos2025_backend(
    rgb, sensitivity,
    color_space, apply_cctf_decoding, reference_illuminant,
    tc_lut=None,
    *,
    sensitivity_adaptation=False,
    bandpass_params=None,
    surface_params=None,
    backend=None,
    precomputed=None,
    input_policy: SpectralInputPolicy | None = None,
):
    """Backend-aware variant of ``rgb_to_raw_hanatos2025``.

    *precomputed* is the tuple returned by
    ``precompute_hanatos2025_constants`` — when provided, no ``colour``
    calls happen in the hot path.  When *backend* is ``None`` the
    function is functionally identical to the original.
    """
    if backend is None or not backend.supports_gpu:
        # Original CPU path — no change.
        return rgb_to_raw_hanatos2025(
            rgb, sensitivity, color_space, apply_cctf_decoding,
            reference_illuminant,
            sensitivity_adaptation=sensitivity_adaptation,
            bandpass_params=bandpass_params,
            surface_params=surface_params,
            tc_lut=tc_lut,
            input_policy=input_policy,
        )

    input_policy = _resolve_input_policy(input_policy)
    if input_policy != DEFAULT_SPECTRAL_INPUT_POLICY:
        return rgb_to_raw_hanatos2025(
            rgb, sensitivity, color_space, apply_cctf_decoding,
            reference_illuminant,
            sensitivity_adaptation=sensitivity_adaptation,
            bandpass_params=bandpass_params,
            surface_params=surface_params,
            tc_lut=tc_lut,
            input_policy=input_policy,
        )

    if precomputed is None:
        precomputed = precompute_hanatos2025_constants(
            color_space, apply_cctf_decoding, reference_illuminant,
        )
    M_rgb_to_xyz, _cctf_decode, _illu_xy = precomputed

    try:
        from spektrafilm.gpu.kernels.color import cctf_decoding_transfer_backend, rgb_to_xyz
        from spektrafilm.gpu.kernels.lut import apply_lut_cubic_2d_backend

        xp = getattr(backend, "mx", None) or getattr(backend, "cp", None)
        if xp is None:
            raise NotImplementedError
        rgb_b = backend.asarray(rgb)
        if apply_cctf_decoding:
            rgb_b = cctf_decoding_transfer_backend(rgb_b, color_space, backend)
        rgb_b = backend.fmax(rgb_b, 0.0)

        xyz = rgb_to_xyz(rgb_b, backend.asarray(M_rgb_to_xyz), backend)
        b = xyz[..., 0] + xyz[..., 1] + xyz[..., 2]
        b_safe = backend.nan_to_num(b)
        xy_denominator = backend.fmax(b, 1e-10)
        xy_x = backend.clip(xyz[..., 0] / xy_denominator, 0.0, 1.0)
        xy_y = backend.clip(xyz[..., 1] / xy_denominator, 0.0, 1.0)

        one_minus_x = 1.0 - xy_x
        tc_x = backend.clip(one_minus_x * one_minus_x, 0.0, 1.0)
        tc_y = backend.clip(xy_y / backend.fmax(one_minus_x, 1e-10), 0.0, 1.0)
        tc = xp.stack([tc_x, tc_y], axis=-1)

        if tc_lut is None:
            if sensitivity_adaptation:
                tc_lut = compute_hanatos2025_adaptation_tc_lut(
                    sensitivity,
                    bandpass_params=bandpass_params,
                    surface_params=surface_params,
                    reference_illuminant=reference_illuminant,
                )
            else:
                tc_lut = compute_hanatos2025_tc_lut(sensitivity)
        raw = apply_lut_cubic_2d_backend(tc_lut, tc, backend)
        return raw * b_safe[..., None]
    except NotImplementedError:
        pass

    if tc_lut is None:
        if sensitivity_adaptation:
            tc_lut = compute_hanatos2025_adaptation_tc_lut(
                sensitivity,
                bandpass_params=bandpass_params,
                surface_params=surface_params,
                reference_illuminant=reference_illuminant,
            )
        else:
            tc_lut = compute_hanatos2025_tc_lut(sensitivity)
    return rgb_to_raw_hanatos2025(
        rgb, sensitivity, color_space, apply_cctf_decoding,
        reference_illuminant,
        sensitivity_adaptation=sensitivity_adaptation,
        bandpass_params=bandpass_params,
        surface_params=surface_params,
        tc_lut=tc_lut,
        input_policy=input_policy,
    )

def rgb_to_smooth_spectrum(
    rgb,
    color_space,
    apply_cctf_decoding,
    reference_illuminant,
    input_policy: SpectralInputPolicy | None = None,
):
    # direct interpolation of the spectra lut, to be used only for smooth spectra close to white
    tc_w, b_w = _rgb_to_tc_b(
        rgb,
        color_space=color_space,
        apply_cctf_decoding=apply_cctf_decoding,
        reference_illuminant=reference_illuminant,
        input_policy=input_policy,
    )
    v = np.linspace(0, 1, HANATOS2025_SPECTRA_LUT.shape[0])
    spectrum_w = scipy.interpolate.RegularGridInterpolator((v,v), HANATOS2025_SPECTRA_LUT)(tc_w)
    spectrum_w *= b_w
    return spectrum_w.flatten()


if __name__=='__main__':
    lut_coeffs = _load_coeffs_lut()
    coeffs = _fetch_coeffs(np.array([[1,1]]) ,lut_coeffs)
    spectra = _compute_spectra_from_coeffs(coeffs)
    lut_spectra = compute_lut_spectra(lut_size=128)
