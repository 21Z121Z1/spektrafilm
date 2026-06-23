from __future__ import annotations

import numpy as np
from opt_einsum import contract

from spektrafilm.model.diffusion import apply_diffusion_filter_um
from spektrafilm.model.develop import compute_density_spectral, develop_print_morph
from spektrafilm.model.illuminants import standard_illuminant
from spektrafilm.utils.conversions import density_to_light
from spektrafilm.utils.timings import timeit
from spektrafilm.gpu.kernels.density import (
    compute_density_spectral as compute_density_spectral_backend,
    density_to_light as density_to_light_backend,
    interpolate_exposure_to_density_backend,
    light_to_raw as light_to_raw_backend,
    safe_log10_backend,
)
from spektrafilm.gpu.kernels.tile_utils import (
    default_tile_rows,
    process_rows_tiled,
)
from spektrafilm.utils.morph_curves import apply_print_curves_morph


class PrintingStage:
    def __init__(
        self,
        film,
        film_render_params,
        print_profile,
        print_render_params,
        enlarger_params,
        settings_params,
        lut_service,
        enlarger_service,
        resize_service,
        color_reference_service,
        backend=None,
    ):
        self._film = film
        self._film_render = film_render_params
        self._print = print_profile
        self._print_render = print_render_params
        self._enlarger = enlarger_params
        self._settings = settings_params
        self._lut_service = lut_service
        self._enlarger_service = enlarger_service
        self._resize_service = resize_service
        self._color_reference_service = color_reference_service
        self._backend = backend

        # Pre-compute static spectral tables for GPU to avoid
        # repeated numpy→backend transfers on every _film_cmy_to_print_log_raw call.
        self._precompute_spectral_tables()

    def _precompute_spectral_tables(self) -> None:
        """Pre-convert static spectral arrays to backend arrays once."""
        _gpu = self._backend is not None and getattr(self._backend, "supports_gpu", False)
        if not _gpu:
            self._backend_channel_density = None
            self._backend_base_density = None
            self._backend_print_illuminant = None
            self._backend_sensitivity = None
            return

        sensitivity = 10 ** self._print.data.log_sensitivity
        sensitivity = np.nan_to_num(sensitivity)
        enlarger_light_source = standard_illuminant(self._enlarger.illuminant)
        print_illuminant = self._enlarger_service.enlarger_filtered_illuminant(enlarger_light_source)

        channel_density = self._film.data.channel_density
        base_density = self._film.data.base_density

        self._backend_channel_density = self._backend.asarray(channel_density)
        self._backend_base_density = self._backend.asarray(base_density)
        self._backend_print_illuminant = self._backend.asarray(print_illuminant)
        self._backend_sensitivity = self._backend.asarray(sensitivity)

    def _resolve_tile_rows(self, height: int) -> int | None:
        """Return the number of rows per spectral tile, or None to disable tiling."""
        if self._backend is None or not getattr(self._backend, "supports_gpu", False):
            return None
        if getattr(self._backend, "name", None) != "mlx":
            return None
        if getattr(self._backend, "precision", None) != "float32":
            return None
        if getattr(self._settings, "gpu_disable_spectral_tiling", False):
            return None
        explicit = getattr(self._settings, "gpu_tile_rows", None)
        if explicit is not None:
            return int(explicit)
        return default_tile_rows(height)

    # public methods

    def refresh_backend_spectral_tables(self) -> None:
        """Refresh backend-cached spectral tables after mutable inputs change."""
        self._precompute_spectral_tables()

    @timeit("expose")
    def expose(self, cmy_film_density: np.ndarray) -> np.ndarray:
        # Black/white reference points — tiny (1,1,3) arrays, direct computation is fine
        cmy_film_black = np.zeros((1,1,3)) - np.array(self._film_render.grain.density_min)
        cmy_film_white = np.nanmax(self._film.data.density_curves, axis=0)[None, None, :]
        self._color_reference_service.log_raw_print_black = self._film_cmy_to_print_log_raw(cmy_film_black)
        self._color_reference_service.log_raw_print_white = self._film_cmy_to_print_log_raw(cmy_film_white)

        _gpu = self._backend is not None and getattr(self._backend, "supports_gpu", False)
        if _gpu:
            # Main spectral computation — keep intermediates on backend
            log_raw_print = self._spectral_compute_enlarger_gpu(cmy_film_density)
            raw = self._backend.power(10.0, log_raw_print)
            raw = raw * self._backend.asarray(self._enlarger.print_exposure)
            raw = raw * self._backend.asarray(
                self._color_reference_service.black_white_printing_exposure_correction()
            )
        else:
            log_raw_print = self._lut_service.spectral_compute_enlarger(
                cmy_film_density,
                spectral_calculation=self._film_cmy_to_print_log_raw,
                data_min=-np.array(self._film_render.grain.density_min),
                data_max=np.nanmax(self._film.data.density_curves, axis=0),
                use_lut=self._settings.use_enlarger_lut,
            )
            raw = 10**log_raw_print
            raw *= self._enlarger.print_exposure
            raw *= self._color_reference_service.black_white_printing_exposure_correction()

        raw = apply_diffusion_filter_um(
            raw,
            self._enlarger.diffusion_filter,
            pixel_size_um=self._resize_service.pixel_size_um,
            backend=self._backend,
        )
        if _gpu:
            return safe_log10_backend(raw, self._backend)
        return np.log10(np.fmax(raw, 0.0) + 1e-10)

    def _spectral_compute_enlarger_gpu(self, cmy_film_density: np.ndarray):
        """GPU-optimized spectral computation that keeps intermediates on backend.

        Computes the same result as _film_cmy_to_print_log_raw but avoids
        the numpy round-trip by performing the full chain on the backend.
        """
        use_lut = self._settings.use_enlarger_lut

        if not use_lut:
            return self._film_cmy_to_print_log_raw(cmy_film_density, return_backend=True)

        return self._lut_service.spectral_compute_enlarger(
            cmy_film_density,
            spectral_calculation=self._film_cmy_to_print_log_raw,
            data_min=-np.array(self._film_render.grain.density_min),
            data_max=np.nanmax(self._film.data.density_curves, axis=0),
            use_lut=True,
        )

    @timeit("develop")
    def develop(self, log_raw: np.ndarray) -> np.ndarray:
        if self._backend is not None and getattr(self._backend, "supports_gpu", False):
            density_curves_morphed = apply_print_curves_morph(
                self._print.data.log_exposure,
                self._print.data.density_curves_model,
                self._print_render.density_curves_morph,
                profile_type=self._print.info.type,
            )
            return interpolate_exposure_to_density_backend(
                log_raw,
                self._print.data.log_exposure,
                density_curves_morphed,
                1.0,
                self._backend,
            )
        return develop_print_morph(
            log_raw,
            self._print.data.log_exposure,
            self._print.data.density_curves_model,
            density_curves_morph=self._print_render.density_curves_morph,
            profile_type=self._print.info.type,
        )

    # private methods

    def _film_cmy_to_print_log_raw(
        self,
        cmy_film_density: np.ndarray,
        *,
        return_backend: bool = False,
    ) -> np.ndarray:
        _gpu = self._backend is not None and getattr(self._backend, "supports_gpu", False)

        if _gpu:
            fused_log_raw = getattr(self._backend, "cmy_to_log_raw", None)
            if callable(fused_log_raw):
                sensitivity = 10 ** self._print.data.log_sensitivity
                sensitivity = np.nan_to_num(sensitivity)
                enlarger_light_source = standard_illuminant(self._enlarger.illuminant)
                print_illuminant = self._enlarger_service.enlarger_filtered_illuminant(enlarger_light_source)
                raw = fused_log_raw(
                    cmy_film_density,
                    self._backend_channel_density,
                    self._backend_base_density,
                    self._backend_print_illuminant,
                    self._backend_sensitivity,
                    self._compute_exposure_factor_midgray(sensitivity, print_illuminant),
                    self._compute_raw_preflash(enlarger_light_source, sensitivity),
                )
                if return_backend:
                    return raw
                return self._backend.to_numpy(raw)

            # Exposure factor and preflash use small arrays; compute on CPU once.
            sensitivity = 10 ** self._print.data.log_sensitivity
            sensitivity = np.nan_to_num(sensitivity)
            enlarger_light_source = standard_illuminant(self._enlarger.illuminant)
            print_illuminant = self._enlarger_service.enlarger_filtered_illuminant(enlarger_light_source)
            exp_factor = self._backend.asarray(
                self._compute_exposure_factor_midgray(sensitivity, print_illuminant)
            )
            preflash = self._backend.asarray(
                self._compute_raw_preflash(enlarger_light_source, sensitivity)
            )

            def _unfused_chain(tile):
                density_spectral = compute_density_spectral_backend(
                    self._backend_channel_density,
                    tile,
                    base_density=self._backend_base_density,
                    backend=self._backend,
                )
                light = density_to_light_backend(
                    density_spectral, self._backend_print_illuminant, self._backend,
                )
                raw = light_to_raw_backend(
                    light, self._backend_sensitivity, self._backend,
                )
                raw = raw * exp_factor
                raw = raw + preflash
                return safe_log10_backend(raw, self._backend)

            tile_rows = self._resolve_tile_rows(cmy_film_density.shape[0])
            log_raw = process_rows_tiled(
                self._backend.asarray(cmy_film_density),
                _unfused_chain,
                self._backend,
                tile_rows=tile_rows,
            )
            if return_backend:
                return log_raw
            return self._backend.to_numpy(log_raw)
        else:
            sensitivity = 10 ** self._print.data.log_sensitivity
            sensitivity = np.nan_to_num(sensitivity)
            enlarger_light_source = standard_illuminant(self._enlarger.illuminant)
            density_spectral = compute_density_spectral(
                self._film.data.channel_density,
                cmy_film_density,
                base_density=self._film.data.base_density,
            )
            print_illuminant = self._enlarger_service.enlarger_filtered_illuminant(enlarger_light_source)
            light = density_to_light(density_spectral, print_illuminant)
            raw = contract("ijk, kl->ijl", light, sensitivity)
            raw *= self._compute_exposure_factor_midgray(sensitivity, print_illuminant)
            raw += self._compute_raw_preflash(enlarger_light_source, sensitivity)
            return np.log10(np.fmax(raw, 0.0) + 1e-10)

    def _compute_raw_preflash(self, light_source, sensitivity):
        if self._enlarger.preflash_exposure > 0:
            preflash_illuminant = self._enlarger_service.preflash_filtered_illuminant(light_source)
            density_base = np.asarray(self._film.data.base_density)[None, None, :]
            light_preflash = density_to_light(density_base, preflash_illuminant)
            raw_preflash = contract("ijk, kl->ijl", light_preflash, sensitivity)
            return raw_preflash * self._enlarger.preflash_exposure
        return np.zeros((3,))

    def _compute_exposure_factor_midgray(self, sensitivity, print_illuminant):
        factor_midgray = _exposure_factor(sensitivity, print_illuminant, self._enlarger_service.density_spectral_midgray)
        if self._enlarger_service.density_spectral_midgray_comp is not None:
            factor_midgray_comp = _exposure_factor(sensitivity, print_illuminant,
                                                    self._enlarger_service.density_spectral_midgray_comp)
        else:
            factor_midgray_comp = 1.0
        if self._enlarger.print_exposure_compensation and not self._enlarger.normalize_print_exposure:
            return factor_midgray_comp / factor_midgray
        elif self._enlarger.normalize_print_exposure and self._enlarger.print_exposure_compensation:
            return factor_midgray_comp
        elif self._enlarger.normalize_print_exposure and not self._enlarger.print_exposure_compensation:
            return factor_midgray
        else:
            return 1.0

def _exposure_factor(sensitivity, print_illuminant, density_spectral_midgray):
    light_midgray = density_to_light(density_spectral_midgray, print_illuminant)
    raw_midgray = contract("ijk, kl->ijl", light_midgray, sensitivity)
    raw_midgray = np.fmax(raw_midgray, 1e-10)
    # use the geometric mean to normalize the exposure
    raw_midgray_geomean = np.exp(np.mean(np.log(raw_midgray), axis=2, keepdims=True))
    return 1 / raw_midgray_geomean
