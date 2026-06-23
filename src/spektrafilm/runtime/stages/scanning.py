from __future__ import annotations

import colour
import numpy as np
from opt_einsum import contract

from spektrafilm.config import STANDARD_OBSERVER_CMFS
from spektrafilm.gpu.kernels.color import (
    cctf_encoding_backend,
    precompute_xyz_to_rgb_matrix,
    xyz_to_rgb as xyz_to_rgb_backend,
)
from spektrafilm.gpu.kernels.density import cmy_to_log_xyz_backend
from spektrafilm.gpu.kernels.tile_utils import (
    default_tile_rows,
    process_rows_tiled,
)
from spektrafilm.model.diffusion import apply_gaussian_blur, apply_unsharp_mask
from spektrafilm.model.develop import compute_density_spectral
from spektrafilm.model.glare import add_glare
from spektrafilm.model.illuminants import standard_illuminant
from spektrafilm.utils.conversions import density_to_light
from spektrafilm.utils.gamut_compression import compress_rgb
from spektrafilm.gpu.kernels.gamut_compress import compress_rgb_backend
from spektrafilm.runtime.route_master import ScanMasterResult
from spektrafilm.utils.timings import timeit


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

    @timeit("scan")
    def scan(self, density_channels: np.ndarray) -> np.ndarray:
        scan_master = self.scan_master(density_channels)
        return self.project_sdr_legacy(scan_master)

    def scan_master(self, density_channels: np.ndarray) -> ScanMasterResult:
        return self._density_to_master(density_channels, use_lut=self._settings.use_scanner_lut)

    def project_sdr_legacy(self, scan_master: ScanMasterResult) -> np.ndarray:
        rgb = self._apply_output_gamut_compression(scan_master.route_linear_rgb)
        rgb = self._apply_blur_and_unsharp(rgb)
        return self._apply_cctf_encoding_and_clip(rgb)

    # private methods

    def _density_to_master(self, density_channels: np.ndarray, *, use_lut: bool) -> ScanMasterResult:
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
        xyz = 10 ** log_xyz
        xyz = self._color_reference_service.black_white_xyz_correction(xyz)
        illuminant_xyz = contract("k,kl->l", scan_illuminant, STANDARD_OBSERVER_CMFS[:]) / normalization
        xyz = add_glare(xyz, illuminant_xyz, glare, backend=self._backend)
        route_luminance_y = xyz[:, :, 1]

        if self._backend is not None and self._backend.supports_gpu:
            rgb = xyz_to_rgb_backend(xyz, self._xyz_to_rgb_matrix, self._backend)
        else:
            illuminant_xy = colour.XYZ_to_xy(illuminant_xyz)
            rgb = colour.XYZ_to_RGB(
                xyz,
                colourspace=self._io.output_color_space,
                apply_cctf_encoding=False,
                illuminant=illuminant_xy,
            )

        if self._backend is not None and self._backend.supports_gpu:
            rgb = self._backend.asarray(rgb)
            xyz = self._backend.asarray(xyz)
            route_luminance_y = self._backend.asarray(route_luminance_y)
            density_channels = self._backend.asarray(density_channels)
        return ScanMasterResult(
            route_linear_rgb=rgb,
            route_linear_xyz=xyz,
            route_luminance_y=route_luminance_y,
            density_cmy=density_channels,
            diagnostics={
                "scan_film": bool(self._io.scan_film),
                "output_gamut_compression_in_projection": True,
            },
        )

    def _apply_output_gamut_compression(self, rgb: np.ndarray) -> np.ndarray:
        # Output gamut compression. Compresses chromaticities the
        # simulation reached that fall outside the output primaries
        # cube; for perceptual algorithms (oklch / oklrab / jzazbz /
        # cam16ucs) the spec's lightness_compression also pulls
        # super-bright pixels back into the cube via a one-sided soft
        # roll-off on the perceptual lightness axis (black stays at 0).
        # With both in place the output is in [0, 1] without a
        # downstream clip; see n100 / n110 for the design and b40 for
        # downstream clip; see n100 / n110 for the design and b40 for
        # the smoothness analysis.
        if self._backend is not None and self._backend.supports_gpu:
            rgb = compress_rgb_backend(
                rgb, self._io.output_gamut_compress,
                output_color_space=self._io.output_color_space,
                backend=self._backend,
            )
        else:
            rgb = compress_rgb(
                rgb, self._io.output_gamut_compress,
                output_color_space=self._io.output_color_space,
            )

        if self._backend is not None and self._backend.supports_gpu:
            rgb = self._backend.asarray(rgb)
        return rgb

    def _density_to_rgb(self, density_channels: np.ndarray, *, use_lut: bool) -> np.ndarray:
        return self._apply_output_gamut_compression(
            self._density_to_master(density_channels, use_lut=use_lut).route_linear_rgb
        )

    def _return_callable_cmy_to_log_xyz(self):
        if self._io.scan_film:
            channel_density = self._film.data.channel_density
            base_density = self._film.data.base_density
            scan_illuminant = standard_illuminant(self._film.info.viewing_illuminant)
        else:
            channel_density = self._print.data.channel_density
            base_density = self._print.data.base_density
            scan_illuminant = standard_illuminant(self._print.info.viewing_illuminant)

        cmfs = STANDARD_OBSERVER_CMFS[:]
        normalization = np.sum(scan_illuminant * cmfs[:, 1], axis=0)

        # Pre-compute the XYZ-to-RGB matrix with chromatic adaptation for GPU path
        _gpu = self._backend is not None and self._backend.supports_gpu
        if _gpu:
            illuminant_xyz = np.dot(scan_illuminant, cmfs) / normalization
            illuminant_xy = colour.XYZ_to_xy(illuminant_xyz)
            self._xyz_to_rgb_matrix = precompute_xyz_to_rgb_matrix(
                self._io.output_color_space, illuminant_xy=illuminant_xy
            )
            # Pre-convert static spectral tables to backend arrays once
            _backend_channel_density = self._backend.asarray(channel_density)
            _backend_base_density = self._backend.asarray(base_density)
            _backend_scan_illuminant = self._backend.asarray(scan_illuminant)
            _backend_cmfs = self._backend.asarray(cmfs)

        def cmy_to_log_xyz(density_cmy: np.ndarray) -> np.ndarray:
            if _gpu:
                tile_rows = self._resolve_tile_rows(density_cmy.shape[0])
                if tile_rows is not None:
                    def _tile_fn(tile):
                        return cmy_to_log_xyz_backend(
                            tile,
                            _backend_channel_density,
                            _backend_base_density,
                            _backend_scan_illuminant,
                            _backend_cmfs,
                            normalization,
                            self._backend,
                        )

                    return process_rows_tiled(
                        self._backend.asarray(density_cmy),
                        _tile_fn,
                        self._backend,
                        tile_rows=tile_rows,
                    )
                return cmy_to_log_xyz_backend(
                    density_cmy, _backend_channel_density, _backend_base_density,
                    _backend_scan_illuminant, _backend_cmfs, normalization,
                    self._backend,
                )
            density_spectral = compute_density_spectral(
                channel_density,
                density_cmy,
                base_density,
            )
            light = density_to_light(density_spectral, scan_illuminant)
            xyz = contract("ijk,kl->ijl", light, cmfs) / normalization
            return np.log10(np.fmax(xyz, 0.0) + 1e-10)
        return cmy_to_log_xyz

    def _apply_blur_and_unsharp(self, rgb: np.ndarray) -> np.ndarray:
        rgb = apply_gaussian_blur(
            rgb, self._scanner.lens_blur, backend=self._backend, settings=self._settings
        )
        sigma, amount = self._scanner.unsharp_mask
        if sigma > 0 and amount > 0:
            rgb = apply_unsharp_mask(
                rgb, sigma=sigma, amount=amount, backend=self._backend, settings=self._settings
            )
        return rgb

    def _apply_cctf_encoding_and_clip(self, rgb: np.ndarray, encoding=None) -> np.ndarray:
        if encoding is not None:
            apply_cctf = encoding.is_cctf_encoded
            color_space = encoding.color_space
            clip_negatives = encoding.clip_negatives
            clip_highlights = encoding.clip_highlights
        else:
            apply_cctf = self._io.output_cctf_encoding
            color_space = self._io.output_color_space
            clip_negatives = self._io.output_clip_min
            clip_highlights = self._io.output_clip_max

        if apply_cctf:
            if self._backend is not None and self._backend.supports_gpu:
                rgb = cctf_encoding_backend(rgb, color_space, self._backend)
            else:
                rgb = colour.RGB_to_RGB(
                    rgb,
                    color_space,
                    color_space,
                    apply_cctf_decoding=False,
                    apply_cctf_encoding=True,
                )
        a_min = 0.0 if clip_negatives else -np.inf
        a_max = 1.0 if clip_highlights else np.inf
        if self._backend is not None and self._backend.supports_gpu:
            return self._backend.clip(rgb, a_min, a_max)
        return np.clip(rgb, a_min=a_min, a_max=a_max)
