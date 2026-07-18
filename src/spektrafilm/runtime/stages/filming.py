from __future__ import annotations

import numpy as np

from spektrafilm.model.illuminants import standard_illuminant
from spektrafilm.model.color_filters import compute_band_pass_filter
from spektrafilm.model.diffusion import (
    apply_diffusion_filter_um,
    apply_fused_filming_filters,
    apply_gaussian_blur_um,
    apply_halation_um,
    boost_highlights,
    supports_fused_filming_filters,
)
from spektrafilm.model.develop import compute_density_spectral, develop, develop_simple
from spektrafilm.gpu.kernels.color import (
    boost_highlights_backend,
    rgb_to_raw_mallett2019_backend,
    rgb_to_tc_b_backend,
)
from spektrafilm.gpu.kernels.density import safe_log10_backend
from spektrafilm.gpu.precision_policy import (
    OP_LUT_2D_MITCHELL,
    OP_SPECTRAL_REDUCTION,
    should_fallback_to_cpu,
)
from spektrafilm.utils.autoexposure import measure_autoexposure_ev
from spektrafilm.utils.spectral_upsampling import (
    rgb_to_raw_hanatos2025,
    rgb_to_raw_mallett2019,
    _rgb_to_tc_b,
)
from spektrafilm.runtime.route_master import FilmingExposureResult
from spektrafilm.utils.timings import timeit


class FilmingStage:
    def __init__(self, film, film_render_params, camera_params, io_params, settings_params,
                 lut_service, resize_service, enlarger_service, color_reference_service, backend=None):
        self._film = film
        self._film_render = film_render_params
        self._camera = camera_params
        self._io = io_params
        self._settings = settings_params
        self._lut_service = lut_service
        self._resize_service = resize_service
        self._enlarger_service = enlarger_service
        self._backend = backend

        # send info for hanatos2025 sensitivity adaptation to LUT service
        hanatos2025_adaptation = self._film.hanatos2025_adaptation()
        hanatos2025_adaptation.apply_window = self._settings.apply_hanatos2025_adaptation_window
        hanatos2025_adaptation.apply_surface = self._settings.apply_hanatos2025_adaptation_surface
        hanatos2025_adaptation.spectral_gaussian_blur = self._settings.spectral_gaussian_blur
        self._lut_service.set_hanatos2025_adaptation(hanatos2025_adaptation)
        # Input gamut compression is per-bundle config (lives on params.io
        # so the GUI and bundle bakes share the same code path). The
        # service caches the LUT and invalidates it when this spec changes.
        self._lut_service.set_input_gamut_compress(self._io.input_gamut_compress)
        self._enlarger_service.density_spectral_midgray, self._enlarger_service.density_spectral_midgray_comp = self._compute_density_spectral_midgray_to_balance_print()
        self._color_reference_service = color_reference_service

    # public methods

    def auto_exposure(self, image: np.ndarray) -> np.ndarray:
        exposed_image, _autoexposure_ev = self.auto_exposure_with_ev(image)
        return exposed_image

    @timeit("auto_exposure")
    def auto_exposure_with_ev(self, image: np.ndarray) -> tuple[np.ndarray, float | None]:
        if self._camera.auto_exposure:
            small_preview = self._resize_service.small_preview(image)
            autoexposure_ev = measure_autoexposure_ev(
                small_preview,
                self._io.input_color_space,
                self._io.input_cctf_decoding,
                method=self._camera.auto_exposure_method,
            )
            return image * 2 ** autoexposure_ev, float(autoexposure_ev)
        return image, None

    def expose(self, image: np.ndarray) -> np.ndarray:
        # The normal SDR/topology path only needs log exposure. Luminance
        # sidecars are full-size arrays and are only required by metadata and
        # RouteMaster callers, so do not build them for a plain exposure.
        return self._expose_core(image, include_metadata=False).log_raw

    def expose_with_metadata(self, image: np.ndarray) -> FilmingExposureResult:
        return self._expose_core(image, include_metadata=True)

    def _expose_core(
        self,
        image: np.ndarray,
        *,
        include_metadata: bool,
    ) -> FilmingExposureResult:
        raw = self._rgb_to_film_raw(
            image,
            color_space=self._io.input_color_space,
            apply_cctf_decoding=self._io.input_cctf_decoding,
        )
        raw *= 2 ** self._camera.exposure_compensation_ev
        scene_y_raw = self._raw_luminance_y(raw) if include_metadata else None
        if self._backend is not None and self._backend.supports_gpu:
            raw = boost_highlights_backend(
                raw, self._film_render.halation.boost_ev,
                self._film_render.halation.boost_range,
                self._film_render.halation.protect_ev, self._backend,
            )
        else:
            boost_highlights(raw, self._film_render.halation.boost_ev,
                             self._film_render.halation.boost_range,
                             self._film_render.halation.protect_ev, out=raw)
        if supports_fused_filming_filters(self._backend):
            raw = apply_fused_filming_filters(
                raw,
                diffusion_filter=self._camera.diffusion_filter,
                lens_blur_um=self._camera.lens_blur_um,
                halation=self._film_render.halation,
                pixel_size_um=self._resize_service.pixel_size_um,
                backend=self._backend,
            )
        else:
            raw = apply_diffusion_filter_um(
                raw,
                self._camera.diffusion_filter,
                pixel_size_um=self._resize_service.pixel_size_um,
                backend=self._backend,
                settings=self._settings,
            )
            raw = apply_gaussian_blur_um(raw, self._camera.lens_blur_um,
                                         self._resize_service.pixel_size_um,
                                         backend=self._backend,
                                         settings=self._settings)
            raw = apply_halation_um(raw, self._film_render.halation,
                                    self._resize_service.pixel_size_um,
                                    backend=self._backend,
                                    settings=self._settings)
        raw *= self._color_reference_service.black_white_filming_exposure_correction()
        post_halation_y = self._raw_luminance_y(raw) if include_metadata else None
        if self._backend is not None and self._backend.supports_gpu:
            log_raw = safe_log10_backend(raw, self._backend)
        else:
            log_raw = np.log10(np.fmax(raw, 0.0) + 1e-10)
        return FilmingExposureResult(
            log_raw=log_raw,
            scene_y_raw=scene_y_raw,
            post_halation_y=post_halation_y,
            diagnostics={"post_halation_y_source": "filming_raw_after_halation"},
        )

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
            settings=self._settings,
        )

    # private methods

    def _raw_luminance_y(self, raw: np.ndarray) -> np.ndarray:
        coeffs = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
        if self._backend is not None and self._backend.supports_gpu:
            values = self._backend.fmax(raw, 0.0)
            return self._backend.einsum("ijk,k->ij", values, self._backend.asarray(coeffs))
        return np.einsum("ijk,k->ij", np.fmax(raw, 0.0), coeffs)

    def _rgb_to_film_raw(
        self,
        rgb: np.ndarray,
        *,
        color_space: str = "sRGB",
        apply_cctf_decoding: bool = False,
        use_backend: bool = True,
    ) -> np.ndarray:
        sensitivity = 10 ** self._film.data.log_sensitivity
        sensitivity = np.nan_to_num(sensitivity)

        if getattr(self._settings, 'bandpass_hanatos2025', False):
            bandpass_data = getattr(self._film.data, 'bandpass_hanatos2025', None)
            if bandpass_data is not None:
                sensitivity = np.asarray(bandpass_data, dtype=float)

        if self._camera.filter_uv[0] > 0 or self._camera.filter_ir[0] > 0:
            illuminant = standard_illuminant(self._film.info.reference_illuminant)
            band_pass_filter = compute_band_pass_filter(self._camera.filter_uv, self._camera.filter_ir)
            band_pass_filter = np.tile(band_pass_filter[:, None], (1, 3))
            normalization = np.sum(sensitivity * band_pass_filter * illuminant[:, None], axis=0) / np.sum(sensitivity * illuminant[:, None], axis=0)
            sensitivity *= band_pass_filter / normalization

        if self._settings.rgb_to_raw_method == "hanatos2025":
            tc_lut = self._lut_service.get_filming_tc_lut(sensitivity)
            _backend = getattr(self, '_backend', None)
            _gpu = use_backend and _backend is not None and getattr(_backend, 'supports_gpu', False)
            if _gpu and not should_fallback_to_cpu(
                OP_LUT_2D_MITCHELL,
                policy=getattr(self._settings, "color_precision_policy", None),
                backend_name=getattr(_backend, "name", None),
                gpu_precision=getattr(_backend, "precision", None),
            ):
                # Use GPU-accelerated 2D LUT with cached backend tc_lut
                from spektrafilm.gpu.kernels.lut import apply_lut_cubic_2d_backend
                tc_raw_backend, b_backend = rgb_to_tc_b_backend(
                    rgb,
                    color_space=color_space,
                    apply_cctf_decoding=apply_cctf_decoding,
                    reference_illuminant=self._film.info.reference_illuminant,
                    backend=_backend,
                )
                backend_tc_lut = self._lut_service.get_filming_tc_lut_backend(sensitivity)
                raw_backend = apply_lut_cubic_2d_backend(
                    tc_lut, tc_raw_backend, _backend,
                    prepared_lut=backend_tc_lut,
                )
                raw = raw_backend * b_backend[..., None]
            else:
                if _gpu:
                    rgb = _backend.to_numpy(rgb)
                raw = rgb_to_raw_hanatos2025(
                    rgb,
                    sensitivity,
                    color_space=color_space,
                    apply_cctf_decoding=apply_cctf_decoding,
                    reference_illuminant=self._film.info.reference_illuminant,
                    tc_lut=tc_lut,
                )
        elif self._settings.rgb_to_raw_method == "mallett2019":
            _backend = getattr(self, '_backend', None)
            _gpu = use_backend and _backend is not None and getattr(_backend, 'supports_gpu', False)
            if _gpu and not should_fallback_to_cpu(
                OP_SPECTRAL_REDUCTION,
                policy=getattr(self._settings, "color_precision_policy", None),
                backend_name=getattr(_backend, "name", None),
                gpu_precision=getattr(_backend, "precision", None),
            ):
                raw = rgb_to_raw_mallett2019_backend(
                    rgb,
                    sensitivity,
                    color_space=color_space,
                    apply_cctf_decoding=apply_cctf_decoding,
                    reference_illuminant=self._film.info.reference_illuminant,
                    backend=_backend,
                )
            else:
                if _gpu:
                    rgb = _backend.to_numpy(rgb)
                raw = rgb_to_raw_mallett2019(rgb, sensitivity,
                                color_space=color_space,
                                apply_cctf_decoding=apply_cctf_decoding,
                                reference_illuminant=self._film.info.reference_illuminant)
        else:
            raise ValueError(f"Unsupported rgb_to_raw method: {self._settings.rgb_to_raw_method}")
        return raw

    def _compute_density_spectral_midgray_to_balance_print(self):
        rgb_midgray = np.array([[[0.184] * 3]])
        density_spectral_midgray = self._simple_rgb_to_density_spectral(
            rgb_midgray,
            apply_cctf_decoding=False,
        )
        if self._enlarger_service.print_exposure_compensation:
            neg_exp_comp_ev = self._camera.exposure_compensation_ev
            rgb_midgray_comp = np.array([[[0.184] * 3]]) * 2 ** neg_exp_comp_ev
            density_spectral_midgray_comp = self._simple_rgb_to_density_spectral(
                rgb_midgray_comp,
                apply_cctf_decoding=False,
            )
        else:
            density_spectral_midgray_comp = None
        return density_spectral_midgray, density_spectral_midgray_comp

    def _simple_rgb_to_density_spectral(
        self,
        rgb: np.ndarray,
        *,
        apply_cctf_decoding: bool | None = None,
    ) -> np.ndarray:
        # Always use CPU path: this processes tiny data (1x1 pixels) during
        # __init__ and channel_density may contain NaN that GPU einsum cannot
        # handle.
        if apply_cctf_decoding is None:
            apply_cctf_decoding = self._io.input_cctf_decoding
        raw = self._rgb_to_film_raw(
            rgb,
            color_space=self._io.input_color_space,
            apply_cctf_decoding=apply_cctf_decoding,
            use_backend=False,
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
