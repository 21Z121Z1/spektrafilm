from __future__ import annotations

import colour
import numpy as np

from spektrafilm.color_management import ColorEncoding, output_encoding_from_io
from opt_einsum import contract

from spektrafilm.config import STANDARD_OBSERVER_CMFS
from spektrafilm.gpu.kernels.color import cctf_encoding_backend
from spektrafilm.gpu.kernels.color import precompute_xyz_to_rgb_matrix
from spektrafilm.gpu.kernels.color import xyz_to_rgb
from spektrafilm.gpu.kernels.density import cmy_to_log_xyz_backend
from spektrafilm.model.diffusion import apply_gaussian_blur, apply_unsharp_mask
from spektrafilm.model.emulsion import compute_density_spectral
from spektrafilm.model.glare import add_glare
from spektrafilm.model.illuminants import standard_illuminant
from spektrafilm.utils.timings import timeit
from spektrafilm.utils.conversions import density_to_light


class ScanningStage:
    def __init__(
        self,
        film,
        film_render_params,
        print_profile,
        print_render_params,
        scanner_params,
        io_params,
        settings_params,
        lut_service,
        color_reference_service,
        backend=None,
    ):
        self._film = film
        self._film_render = film_render_params
        self._print = print_profile
        self._print_render = print_render_params
        self._scanner = scanner_params
        self._io = io_params
        self._settings = settings_params
        self._lut_service = lut_service
        self._color_reference_service = color_reference_service
        self._backend = backend
        
        self.cmy_to_log_xyz = self._return_callable_cmy_to_log_xyz()
        
        # communicate to the color reference service the callable to convert cmy densities to log xyz
        self._color_reference_service.cmy_to_log_xyz = self.cmy_to_log_xyz

        # Precompute XYZ → RGB matrix so that ``_density_to_rgb`` avoids
        # calling ``colour.XYZ_to_RGB`` per frame.  The matrix includes
        # CAT from the scanner illuminant to the output colour-space
        # whitepoint.
        self._xyz_to_rgb_matrix = self._precompute_xyz_to_rgb_matrix()
        self._xyz_to_rgb_matrix_backend = (
            self._backend.asarray(self._xyz_to_rgb_matrix)
            if self._backend is not None and self._backend.supports_gpu
            else None
        )
        
    # public methods

    @timeit("scan")
    def scan(self, density_channels: np.ndarray, output_encoding: ColorEncoding | None = None) -> np.ndarray:
        if output_encoding is None:
            output_encoding = output_encoding_from_io(self._io)
        rgb = self._density_to_rgb(density_channels, use_lut=self._settings.use_scanner_lut)
        rgb = self._apply_blur_and_unsharp(rgb)
        return self._apply_cctf_encoding_and_clip(rgb, output_encoding)

    # private methods

    def _precompute_xyz_to_rgb_matrix(self) -> np.ndarray:
        """Build the 3×3 XYZ → output-RGB matrix once at init time."""
        if self._io.scan_film:
            scan_illuminant = standard_illuminant(self._film.info.viewing_illuminant)
        else:
            scan_illuminant = standard_illuminant(self._print.info.viewing_illuminant)

        normalization = np.sum(scan_illuminant * STANDARD_OBSERVER_CMFS[:, 1], axis=0)
        illuminant_xyz = contract("k,kl->l", scan_illuminant, STANDARD_OBSERVER_CMFS[:]) / normalization
        illuminant_xy = colour.XYZ_to_xy(illuminant_xyz)

        return precompute_xyz_to_rgb_matrix(
            self._io.output_color_space,
            illuminant_xy=illuminant_xy,
        )

    def _density_to_rgb(self, density_channels: np.ndarray, *, use_lut: bool) -> np.ndarray:
        if self._io.scan_film:
            glare = None
            density_min = -np.array(self._film_render.grain.density_min)
            density_max = np.nanmax(self._film.data.density_curves, axis=0)
            scan_illuminant = standard_illuminant(self._film.info.viewing_illuminant)
        else:
            glare = self._print_render.glare
            density_min = np.nanmin(self._print.data.density_curves, axis=0)
            density_max = np.nanmax(self._print.data.density_curves, axis=0)
            scan_illuminant = standard_illuminant(self._print.info.viewing_illuminant)
            
        normalization = np.sum(scan_illuminant * STANDARD_OBSERVER_CMFS[:, 1], axis=0)

        log_xyz = self._lut_service.spectral_compute_scanner(
            density_channels,
            spectral_calculation=self.cmy_to_log_xyz,
            data_min=density_min,
            data_max=density_max,
            use_lut=use_lut,
        )
        if self._backend is not None and self._backend.supports_gpu:
            xyz = self._backend.power(10.0, log_xyz)
        else:
            xyz = 10 ** log_xyz
        if (
            self._backend is not None
            and self._backend.supports_gpu
            and (self._scanner.black_correction or self._scanner.white_correction)
        ):
            xyz = self._backend.asarray(
                self._color_reference_service.black_white_xyz_correction(
                    self._backend.to_numpy(xyz)
                )
            )
        else:
            xyz = self._color_reference_service.black_white_xyz_correction(xyz)
        illuminant_xyz = contract("k,kl->l", scan_illuminant, STANDARD_OBSERVER_CMFS[:]) / normalization
        if self._backend is not None and self._backend.supports_gpu and glare is not None and glare.active:
            xyz = self._backend.asarray(add_glare(self._backend.to_numpy(xyz), illuminant_xyz, glare))
        else:
            xyz = add_glare(xyz, illuminant_xyz, glare)

        # Precomputed matrix multiplication: RGB = XYZ @ M.T
        if self._backend is not None and self._backend.supports_gpu:
            xyz = self._backend.asarray(xyz)
            return xyz_to_rgb(xyz, self._xyz_to_rgb_matrix_backend, self._backend)
        return np.asarray(xyz) @ self._xyz_to_rgb_matrix.T

    def _return_callable_cmy_to_log_xyz(self):
        if self._io.scan_film:
            channel_density = self._film.data.channel_density
            base_density = self._film.data.base_density
            scan_illuminant = standard_illuminant(self._film.info.viewing_illuminant)
        else:
            channel_density = self._print.data.channel_density
            base_density = self._print.data.base_density
            scan_illuminant = standard_illuminant(self._print.info.viewing_illuminant)
            
        normalization = np.sum(scan_illuminant * STANDARD_OBSERVER_CMFS[:, 1], axis=0)

        channel_density_backend = (
            self._backend.asarray(channel_density)
            if self._backend is not None and self._backend.supports_gpu
            else None
        )
        base_density_backend = (
            self._backend.asarray(base_density)
            if self._backend is not None and self._backend.supports_gpu
            else None
        )
        scan_illuminant_backend = (
            self._backend.asarray(scan_illuminant)
            if self._backend is not None and self._backend.supports_gpu
            else None
        )
        cmfs_backend = (
            self._backend.asarray(STANDARD_OBSERVER_CMFS[:])
            if self._backend is not None and self._backend.supports_gpu
            else None
        )

        def cmy_to_log_xyz(density_cmy: np.ndarray) -> np.ndarray:
            if self._backend is not None and self._backend.supports_gpu:
                return cmy_to_log_xyz_backend(
                    self._backend.asarray(density_cmy),
                    channel_density_backend,
                    base_density_backend,
                    scan_illuminant_backend,
                    cmfs_backend,
                    normalization,
                    self._backend,
                )
            density_spectral = compute_density_spectral(
                channel_density,
                density_cmy,
                base_density,
            )
            light = density_to_light(density_spectral, scan_illuminant)
            xyz = contract("ijk,kl->ijl", light, STANDARD_OBSERVER_CMFS[:]) / normalization
            return np.log10(np.fmax(xyz, 0.0) + 1e-10)
        return cmy_to_log_xyz

    def _apply_blur_and_unsharp(self, rgb: np.ndarray) -> np.ndarray:
        rgb = apply_gaussian_blur(rgb, self._scanner.lens_blur, backend=self._backend)
        sigma, amount = self._scanner.unsharp_mask
        if sigma > 0 and amount > 0:
            rgb = apply_unsharp_mask(rgb, sigma=sigma, amount=amount, backend=self._backend)
        return rgb

    def _apply_cctf_encoding_and_clip(self, rgb: np.ndarray, encoding: ColorEncoding) -> np.ndarray:
        backend = getattr(self, "_backend", None)
        if backend is not None and backend.supports_gpu:
            if encoding.is_cctf_encoded:
                rgb = cctf_encoding_backend(rgb, encoding.color_space, backend)
            if encoding.clip_negatives:
                rgb = backend.maximum(rgb, 0.0)
            if encoding.clip_highlights:
                rgb = backend.clip(rgb, -np.inf, 1.0)
            return rgb
        if encoding.is_cctf_encoded:
            rgb = cctf_encoding_backend(rgb, encoding.color_space, backend)
        if encoding.clip_negatives:
            rgb = np.maximum(rgb, 0.0)
        if encoding.clip_highlights:
            rgb = np.minimum(rgb, 1.0)
        return rgb
