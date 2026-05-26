from __future__ import annotations

import numpy as np
import colour

from spektrafilm.gpu.kernels.color import boost_highlights_backend
from spektrafilm.model.color_filters import compute_band_pass_filter
from spektrafilm.model.diffusion import apply_diffusion_filter_um, apply_gaussian_blur_um, apply_halation_um
from spektrafilm.utils.numba_boost_hightlights import boost_highlights
from spektrafilm.model.emulsion import compute_density_spectral, develop, develop_simple
from spektrafilm.utils.autoexposure import measure_autoexposure_ev
from spektrafilm.utils.spectral_upsampling import (
    SpectralInputPolicy,
    precompute_hanatos2025_constants,
    rgb_to_raw_hanatos2025_backend,
    rgb_to_raw_mallett2019,
)
from spektrafilm.utils.timings import timeit


class FilmingStage:
    def __init__(self, film, film_render_params, camera_params, io_params, settings_params,
                 lut_service, resize_service, enlarger_service, color_reference_service,
                 backend=None):
        self._film = film
        self._film_render = film_render_params
        self._camera = camera_params
        self._io = io_params
        self._settings = settings_params
        self._lut_service = lut_service
        self._resize_service = resize_service
        self._enlarger_service = enlarger_service
        self._backend = backend
        self._enlarger_service.density_spectral_midgray, self._enlarger_service.density_spectral_midgray_comp = self._compute_density_spectral_midgray_to_balance_print()
        self._color_reference_service = color_reference_service

    # public methods

    @timeit("auto_exposure")
    def auto_exposure(self, image: np.ndarray) -> np.ndarray:
        autoexposed_image, _autoexposure_ev = self.auto_exposure_with_ev(image)
        return autoexposed_image

    def auto_exposure_with_ev(self, image: np.ndarray) -> tuple[np.ndarray, float]:
        if self._camera.auto_exposure:
            small_preview = self._resize_service.small_preview(image)
            autoexposure_ev = measure_autoexposure_ev(
                small_preview,
                self._io.input_color_space,
                self._io.input_cctf_decoding,
                method=self._camera.auto_exposure_method,
            )
            return image * 2 ** autoexposure_ev, float(autoexposure_ev)
        return image, 0.0

    @timeit("expose")
    def expose(self, image: np.ndarray) -> np.ndarray:
        raw = self._rgb_to_film_raw(
            image,
            color_space=self._io.input_color_space,
            apply_cctf_decoding=self._io.input_cctf_decoding,
        )
        raw = raw * (2 ** self._camera.exposure_compensation_ev)
        if self._backend is not None and self._backend.supports_gpu:
            raw = self._backend.asarray(raw)
        if self._backend is not None and self._backend.supports_gpu:
            raw = boost_highlights_backend(
                raw,
                self._film_render.halation.boost_ev,
                self._film_render.halation.boost_range,
                self._film_render.halation.protect_ev,
                self._backend,
            )
        else:
            boost_highlights(raw, self._film_render.halation.boost_ev,
                             self._film_render.halation.boost_range,
                             self._film_render.halation.protect_ev, out=raw)
        raw = apply_diffusion_filter_um(
            raw,
            self._camera.diffusion_filter,
            pixel_size_um=self._resize_service.pixel_size_um,
            backend=self._backend,
        )
        raw = apply_gaussian_blur_um(
            raw,
            self._camera.lens_blur_um,
            self._resize_service.pixel_size_um,
            backend=self._backend,
        )
        raw = apply_halation_um(
            raw,
            self._film_render.halation,
            self._resize_service.pixel_size_um,
            backend=self._backend,
        )
        raw = raw * self._color_reference_service.black_white_filming_exposure_correction()
        if self._backend is not None and self._backend.supports_gpu:
            log_raw = self._backend.log10(self._backend.fmax(raw, 0.0) + 1e-10)
        else:
            log_raw = np.log10(np.fmax(raw, 0.0) + 1e-10)
        return log_raw

    @timeit("develop")
    def develop(self, log_raw: np.ndarray) -> np.ndarray:
        return develop(
            log_raw,
            self._resize_service.pixel_size_um,
            self._film.data.log_exposure,
            self._film.data.density_curves,
            self._film.data.density_curves_layers,
            self._film_render.dir_couplers,
            self._film_render.grain,
            self._film.info.type,
            gamma_factor=self._film_render.density_curve_gamma,
            use_fast_stats=self._settings.use_fast_stats,
            backend=self._backend,
        )

    # private methods

    def _rgb_to_film_raw(
        self,
        rgb: np.ndarray,
        *,
        color_space: str = "sRGB",  # Legacy default — all runtime callers pass io.input_color_space explicitly.
        apply_cctf_decoding: bool = False,
    ) -> np.ndarray:
        sensitivity = 10 ** self._film.data.log_sensitivity
        sensitivity = np.nan_to_num(sensitivity)

        if self._camera.filter_uv[0] > 0 or self._camera.filter_ir[0] > 0:
            band_pass_filter = compute_band_pass_filter(self._camera.filter_uv, self._camera.filter_ir)
            sensitivity *= band_pass_filter[:, None]

        if self._settings.bandpass_hanatos2025 and self._settings.rgb_to_raw_method == "hanatos2025":
            bandpass_hanatos2025 = np.asarray(self._film.data.bandpass_hanatos2025, dtype=float)
            if bandpass_hanatos2025.size:
                if bandpass_hanatos2025.shape != sensitivity.shape:
                    raise ValueError(
                        "film.data.bandpass_hanatos2025 must match film.data.log_sensitivity shape "
                        f"{sensitivity.shape}, got {bandpass_hanatos2025.shape}."
                    )
                sensitivity *= bandpass_hanatos2025

        if self._settings.rgb_to_raw_method == "hanatos2025":
            sensitivity_adaptation = bool(
                getattr(self._settings, "hanatos2025_sensitivity_adaptation", False)
            )
            bandpass_params = (
                self._film.data.hanatos2025_adaptation_bandpass_params
                if sensitivity_adaptation
                else None
            )
            surface_params = (
                self._film.data.hanatos2025_adaptation_surface_params
                if sensitivity_adaptation
                else None
            )
            try:
                tc_lut = self._lut_service.get_filming_tc_lut(
                    sensitivity,
                    sensitivity_adaptation=sensitivity_adaptation,
                    bandpass_params=bandpass_params,
                    surface_params=surface_params,
                    reference_illuminant=self._film.info.reference_illuminant,
                )
            except TypeError:
                tc_lut = self._lut_service.get_filming_tc_lut(sensitivity)
            raw_kwargs = {
                "color_space": color_space,
                "apply_cctf_decoding": apply_cctf_decoding,
                "reference_illuminant": self._film.info.reference_illuminant,
                "tc_lut": tc_lut,
                "backend": self._backend,
                "precomputed": (
                    precompute_hanatos2025_constants(
                        color_space, apply_cctf_decoding,
                        self._film.info.reference_illuminant,
                    )
                    if self._backend is not None and self._backend.supports_gpu
                    else None
                ),
                "input_policy": self._spectral_input_policy(),
            }
            if sensitivity_adaptation:
                raw_kwargs.update(
                    sensitivity_adaptation=True,
                    bandpass_params=bandpass_params,
                    surface_params=surface_params,
                )
            raw = rgb_to_raw_hanatos2025_backend(rgb, sensitivity, **raw_kwargs)
        elif self._settings.rgb_to_raw_method == "mallett2019":
            raw = rgb_to_raw_mallett2019(rgb, sensitivity,
                            color_space=color_space,
                            apply_cctf_decoding=apply_cctf_decoding,
                            reference_illuminant=self._film.info.reference_illuminant,
                            input_policy=self._spectral_input_policy())
        else:
            raise ValueError(f"Unsupported rgb_to_raw method: {self._settings.rgb_to_raw_method}")
        return raw

    def _spectral_input_policy(self) -> SpectralInputPolicy:
        negative_rgb = getattr(self._settings, "spectral_negative_rgb", "clip")
        xy_out_of_bounds = getattr(self._settings, "spectral_xy_out_of_bounds", "clip")
        report_stats = bool(getattr(self._settings, "spectral_report_stats", True))
        return SpectralInputPolicy(
            negative_rgb=negative_rgb,
            xy_out_of_bounds=xy_out_of_bounds,
            report_stats=report_stats,
        )
    
    def _compute_density_spectral_midgray_to_balance_print(self):
        rgb_midgray = self._input_reference_rgb(0.184)
        density_spectral_midgray = self._simple_rgb_to_density_spectral(rgb_midgray)
        if self._enlarger_service.print_exposure_compensation:
            neg_exp_comp_ev = self._camera.exposure_compensation_ev
            rgb_midgray_comp = self._input_reference_rgb(0.184 * 2 ** neg_exp_comp_ev)
            density_spectral_midgray_comp = self._simple_rgb_to_density_spectral(rgb_midgray_comp)
        else:
            density_spectral_midgray_comp = None
        return density_spectral_midgray, density_spectral_midgray_comp

    def _input_reference_rgb(self, linear_value: float) -> np.ndarray:
        linear_rgb = np.full((1, 1, 3), float(linear_value), dtype=float)
        if not self._io.input_cctf_decoding:
            return linear_rgb

        color_space = colour.RGB_COLOURSPACES[self._io.input_color_space]
        return np.asarray(color_space.cctf_encoding(linear_rgb), dtype=float)

    def _simple_rgb_to_density_spectral(self, rgb: np.ndarray) -> np.ndarray:
        raw = self._rgb_to_film_raw(
            rgb,
            color_space=self._io.input_color_space,
            apply_cctf_decoding=self._io.input_cctf_decoding,
        )
        log_raw = np.log10(raw + 1e-10)
        density_cmy = develop_simple(
            log_raw,
            self._film.data.log_exposure,
            self._film.data.density_curves,
            gamma_factor=self._film_render.density_curve_gamma,
        )
        density_spectral = compute_density_spectral(
            self._film.data.channel_density,
            density_cmy,
            base_density=self._film.data.base_density,
        )
        return density_spectral
    
