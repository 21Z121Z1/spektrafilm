import numpy as np
import scipy
import scipy.ndimage
from spektrafilm.model.density_curves import interp_density_cmy_layers
from spektrafilm.runtime.params_schema import GrainParams
from spektrafilm.utils.fast_stats import fast_binomial, fast_poisson, fast_lognormal_from_mean_std
from spektrafilm.utils.fast_gaussian_filter import fast_gaussian_filter
from spektrafilm.gpu.kernels.tile_utils import (
    process_spatial_rows_tiled,
    resolve_spatial_tile_rows,
)
from spektrafilm.gpu.mlx_cache import maybe_clear_cache


_LARGE_GRAIN_STATE_PIXELS = 24_000_000


def _materialize_large_grain_state(value, backend) -> None:
    shape = getattr(value, "shape", ())
    if len(shape) < 2 or int(shape[0]) * int(shape[1]) < _LARGE_GRAIN_STATE_PIXELS:
        return
    backend.eval(value)
    maybe_clear_cache(backend)


def _backend_supports_gpu(backend) -> bool:
    return (
        backend is not None
        and bool(getattr(backend, "supports_gpu", False))
        and hasattr(backend, "mx")
    )


def _backend_is_unsupported_gpu(backend) -> bool:
    return (
        backend is not None
        and bool(getattr(backend, "supports_gpu", False))
        and not _backend_supports_gpu(backend)
    )


def _to_numpy_for_unsupported_gpu(value, backend):
    if _backend_is_unsupported_gpu(backend) and hasattr(backend, "to_numpy"):
        return backend.to_numpy(value)
    return value

################################################################################
# Grain (very simple model)
################################################################################

def layer_particle_model(density,
                         density_max=2.2,
                         n_particles_per_pixel=10,
                         grain_uniformity=0.98,
                         seed=None,
                         blur_particle=0.0,
                         method='poisson_binomial',
                         use_fast_stats=False,
                         backend=None,
                         ):
    if method not in {'gamma_beta', 'poisson_binomial'}:
        raise ValueError(f"Unsupported grain particle method: {method!r}")

    # --- GPU path ---
    if _backend_supports_gpu(backend):
        if method == 'poisson_binomial':
            return _layer_particle_model_gpu(
                density,
                density_max=density_max,
                n_particles_per_pixel=n_particles_per_pixel,
                grain_uniformity=grain_uniformity,
                seed=seed,
                blur_particle=blur_particle,
                method=method,
                use_fast_stats=use_fast_stats,
                backend=backend,
            )
        density = backend.to_numpy(density) if hasattr(backend, "to_numpy") else np.asarray(density)

    # --- CPU path ---
    uses_global_rng = seed is not None and method == 'poisson_binomial' and use_fast_stats
    rng = np.random.RandomState(seed) if seed is not None and not uses_global_rng else None
    if uses_global_rng:
        saved_state = np.random.get_state()
        np.random.seed(seed) # scipy uses np.random
    else:
        saved_state = None

    try:
        probability_of_development = density/density_max
        probability_of_development = np.clip(probability_of_development, 1e-6, 1-1e-6) # for safe calc
        od_particle = density_max/n_particles_per_pixel

        grain = np.zeros_like(density)
        if method=='gamma_beta':
            gamma_rvs = scipy.stats.gamma.rvs
            beta_rvs = scipy.stats.beta.rvs
            rvs_kwargs = {"random_state": rng} if rng is not None else {}
            seeds = gamma_rvs(
                n_particles_per_pixel/(1-grain_uniformity+1e-6),
                size=density.shape,
                **rvs_kwargs,
            ) * (1-grain_uniformity+1e-6)
            grain = beta_rvs(probability_of_development*n_particles_per_pixel,
                            (1-probability_of_development)*n_particles_per_pixel,
                            **rvs_kwargs)*seeds*od_particle
        elif method=='poisson_binomial':
            saturation = 1 - probability_of_development*grain_uniformity*(1-1e-6)
            if use_fast_stats:
                binom_rvs = fast_binomial
                poisson_rvs = fast_poisson
                seeds = poisson_rvs(n_particles_per_pixel/saturation)
                grain = binom_rvs(seeds, probability_of_development)
            else:
                binom_rvs = scipy.stats.binom.rvs
                poisson_rvs = scipy.stats.poisson.rvs
                rvs_kwargs = {"random_state": rng} if rng is not None else {}
                seeds = poisson_rvs(n_particles_per_pixel/saturation, **rvs_kwargs)
                grain = binom_rvs(seeds, probability_of_development, **rvs_kwargs)
            grain = np.double(grain)*od_particle*saturation

        if blur_particle>0:
            # grain = scipy.ndimage.gaussian_filter(grain, blur_particle*np.sqrt(od_particle))
            grain = fast_gaussian_filter(grain, blur_particle*np.sqrt(od_particle))
        return grain
    finally:
        if saved_state is not None:
            np.random.set_state(saved_state)


def _layer_particle_model_gpu(density,
                              density_max=2.2,
                              n_particles_per_pixel=10,
                              grain_uniformity=0.98,
                              seed=None,
                              blur_particle=0.0,
                              method='poisson_binomial',
                              use_fast_stats=False,
                              backend=None,
                              ):
    """GPU-accelerated particle model using backend-aware stochastic samplers."""
    from spektrafilm.gpu.kernels.grain import fast_poisson_backend
    from spektrafilm.gpu.kernels.filters import gaussian_filter_backend

    mx = backend.mx
    density_mx = backend.asarray(density, dtype=mx.float32)

    probability_of_development = density_mx / mx.array(density_max, dtype=mx.float32)
    probability_of_development = mx.clip(probability_of_development, 1e-6, 1 - 1e-6)
    od_particle = density_max / n_particles_per_pixel

    grain = mx.zeros_like(density_mx)
    if method == 'poisson_binomial':
        saturation = 1.0 - probability_of_development * grain_uniformity * (1 - 1e-6)
        # p is clipped to [1e-6, 1-1e-6], so for a physical uniformity in
        # [0, 1] the Poisson lambda has scalar bounds known before execution.
        # Passing them lets MLX omit an unreachable full-frame RNG branch
        # while preserving the exact random key used by the retained branch.
        minimum_lam = None
        maximum_lam = None
        particles = float(n_particles_per_pixel)
        uniformity = float(grain_uniformity)
        if particles >= 0.0 and 0.0 <= uniformity <= 1.0:
            minimum_lam = particles
            saturation_min = 1.0 - uniformity * (1.0 - 1e-6) ** 2
            if saturation_min > 0.0:
                maximum_lam = particles / saturation_min
        seeds = fast_poisson_backend(
            particles / saturation,
            backend,
            seed=seed,
            minimum_lam=minimum_lam,
            maximum_lam=maximum_lam,
        )

        # Binomial(seeds[i,j], p[i,j]) for variable n per pixel.
        # For large n: normal approximation  Binom(n,p) ~ N(n*p, n*p*(1-p)).
        # The approximation stays entirely on MLX; clamping by sampled seeds
        # keeps each pixel in the valid binomial range.
        binom_key = mx.random.key((seed + 10000) if seed is not None else 0)
        seeds_f = seeds.astype(mx.float32)
        binom_mean = seeds_f * probability_of_development
        binom_var = binom_mean * (1.0 - probability_of_development)
        binom_std = mx.sqrt(mx.maximum(binom_var, mx.array(1e-8, dtype=mx.float32)))

        _, norm_key = mx.random.split(binom_key)
        normal_samples = binom_mean + binom_std * mx.random.normal(
            density_mx.shape, key=norm_key, dtype=mx.float32,
        )
        binom_result = mx.round(normal_samples).astype(mx.int32)
        binom_result = mx.maximum(binom_result, mx.zeros_like(binom_result))
        binom_result = mx.minimum(binom_result, seeds.astype(mx.int32))

        grain = (
            binom_result.astype(mx.float32)
            * mx.array(od_particle, dtype=mx.float32)
            * saturation
        )

    if blur_particle > 0:
        sigma = blur_particle * float(np.sqrt(od_particle))
        grain = gaussian_filter_backend(grain, sigma, backend)

    return grain

def add_micro_structure(density_cmy_out, micro_structure, pixel_size_um, backend=None):
    grain_micro_structure_blur_pixel = micro_structure[0]/pixel_size_um
    grain_micro_structure_sigma = micro_structure[1]*0.001/pixel_size_um  # grain microstructure[1] is in nm
    if grain_micro_structure_sigma > 0.05:
        if _backend_supports_gpu(backend):
            from spektrafilm.gpu.kernels.grain import fast_lognormal_from_mean_std_backend
            from spektrafilm.gpu.kernels.filters import gaussian_filter_backend
            mx = backend.mx
            ones = mx.ones_like(backend.asarray(density_cmy_out))
            clumping = fast_lognormal_from_mean_std_backend(
                ones, ones * mx.array(grain_micro_structure_sigma, dtype=mx.float32), backend,
            )
            if grain_micro_structure_blur_pixel > 0.4:
                clumping = gaussian_filter_backend(clumping, grain_micro_structure_blur_pixel, backend)
            density_cmy_out = density_cmy_out * clumping
        else:
            clumping = fast_lognormal_from_mean_std(np.ones_like(density_cmy_out),
                                                    np.ones_like(density_cmy_out)*grain_micro_structure_sigma)
            if grain_micro_structure_blur_pixel>0.4:
                # clumping = scipy.ndimage.gaussian_filter(clumping, (grain_micro_structure_blur_pixel,
                #                                                     grain_micro_structure_blur_pixel, 0))
                clumping = fast_gaussian_filter(clumping, grain_micro_structure_blur_pixel)
            density_cmy_out *= clumping
    return density_cmy_out

def apply_grain_to_density(density_cmy,
                           pixel_size_um=10,
                           agx_particle_area_um2=0.2,
                           agx_particle_scale=(1,0.8,3),
                           density_min=(0.03,0.06,0.04),
                           density_max_curves=(2.2,2.2,2.2),
                           grain_uniformity=(0.98,0.98,0.98),
                           grain_blur=1.0,
                           n_sub_layers=1,
                           fixed_seed=None,
                           backend=None,
                           settings=None,
                           ):
    if n_sub_layers < 1:
        raise ValueError(f"n_sub_layers must be >= 1, got {n_sub_layers}")

    density_min = np.asarray(density_min, dtype=float)
    density_max = np.asarray(density_max_curves, dtype=float) + density_min
    pixel_area_um2 = pixel_size_um**2
    agx_particle_area_um2 = agx_particle_area_um2*np.asarray(agx_particle_scale, dtype=float)
    n_particles_per_pixel = pixel_area_um2/agx_particle_area_um2
    sigma_blur_pixel = grain_blur

    if fixed_seed is not None:
        seed = [int(fixed_seed), int(fixed_seed) + 1, int(fixed_seed) + 2]
    else:
        seed = [0, 1, 2]

    if n_sub_layers>1:
        n_particles_per_pixel /= n_sub_layers

    # --- GPU path ---
    if _backend_supports_gpu(backend):
        return _apply_grain_to_density_gpu(
            density_cmy,
            density_min=density_min,
            density_max=density_max,
            n_particles_per_pixel=n_particles_per_pixel,
            grain_uniformity=grain_uniformity,
            sigma_blur_pixel=sigma_blur_pixel,
            n_sub_layers=n_sub_layers,
            seed=seed,
            backend=backend,
            settings=settings,
        )

    # --- CPU path (unchanged) ---
    density_cmy = density_cmy.copy()
    density_cmy += density_min
    density_cmy_out = np.zeros_like(density_cmy)
    for ch in np.arange(3):
        for sl in np.arange(n_sub_layers):
            density_cmy_out[:,:,ch] += layer_particle_model(density_cmy[:,:,ch],
                                                            density_max=density_max[ch],
                                                            n_particles_per_pixel=n_particles_per_pixel[ch],
                                                            grain_uniformity=grain_uniformity[ch],
                                                            seed=seed[ch] + sl*10)
    density_cmy_out /= n_sub_layers
    density_cmy_out -= density_min

    if sigma_blur_pixel>0.4:
        # density_cmy_out = scipy.ndimage.gaussian_filter(density_cmy_out, (sigma_blur_pixel, sigma_blur_pixel, 0))
        density_cmy_out = fast_gaussian_filter(density_cmy_out, sigma_blur_pixel)

    return density_cmy_out


def _apply_grain_to_density_gpu(density_cmy,
                                density_min,
                                density_max,
                                n_particles_per_pixel,
                                grain_uniformity,
                                sigma_blur_pixel,
                                n_sub_layers,
                                seed,
                                backend,
                                settings=None):
    """GPU-accelerated grain application to density channels."""
    from spektrafilm.gpu.kernels.filters import gaussian_filter_backend

    mx = backend.mx
    density_cmy_mx = backend.asarray(density_cmy, dtype=mx.float32)
    density_min_mx = backend.asarray(density_min.astype(np.float32))
    density_cmy_mx = density_cmy_mx + density_min_mx
    _materialize_large_grain_state(density_cmy_mx, backend)

    out_channels = []
    for ch in range(3):
        ch_layer = mx.zeros(density_cmy_mx.shape[:2], dtype=mx.float32)
        for sl in range(n_sub_layers):
            ch_layer = ch_layer + layer_particle_model(
                density_cmy_mx[:, :, ch],
                density_max=density_max[ch],
                n_particles_per_pixel=n_particles_per_pixel[ch],
                grain_uniformity=grain_uniformity[ch],
                seed=seed[ch] + sl * 10,
                backend=backend,
            )
            _materialize_large_grain_state(ch_layer, backend)
        out_channels.append(ch_layer)

    density_cmy_out = mx.stack(out_channels, axis=-1)
    density_cmy_out = density_cmy_out / mx.array(n_sub_layers, dtype=mx.float32)
    density_cmy_out = density_cmy_out - density_min_mx

    if sigma_blur_pixel > 0.4:
        overlap = int(np.ceil(3.0 * sigma_blur_pixel))
        tile_rows = resolve_spatial_tile_rows(
            density_cmy_out.shape[0], overlap, backend=backend, settings=settings
        )
        if tile_rows is not None:
            def _blur_tile(tile_ext):
                return gaussian_filter_backend(tile_ext, sigma_blur_pixel, backend)

            density_cmy_out = process_spatial_rows_tiled(
                density_cmy_out,
                _blur_tile,
                backend,
                overlap=overlap,
                tile_rows=tile_rows,
            )
        else:
            density_cmy_out = gaussian_filter_backend(density_cmy_out, sigma_blur_pixel, backend)

    return density_cmy_out


# experimental
def apply_grain_to_density_layers(density_cmy_layers, # x,y,sublayers,rgb
                                  density_max_layers, # 3x3 [sublayers,rgb]
                                  pixel_size_um=10,
                                  agx_particle_area_um2=0.2,
                                  agx_particle_scale=(1,0.8,3), # rgb
                                  agx_particle_scale_layers=(3,1,0.3), # sublayers
                                  density_min=(0.03,0.06,0.04),
                                  grain_uniformity=(0.98,0.98,0.98),
                                  grain_blur=1.0,
                                  grain_blur_dye_clouds_um=1.0,
                                  grain_micro_structure=(0.1, 30),
                                  fixed_seed=None,
                                  use_fast_stats=False,
                                  backend=None,
                                  settings=None,
                                  ):
    density_max_total = np.sum(density_max_layers, axis=0) # [sublayers,rgb]
    density_max_fractions = density_max_layers/density_max_total[None,:]
    density_min_layers = density_max_fractions*np.array(density_min)[None,:]
    density_max_layers = density_max_layers + density_min_layers

    pixel_area_um2 = pixel_size_um**2
    agx_particle_area_um2_layers = (agx_particle_area_um2 *
                                    np.array(agx_particle_scale)[None,:] *
                                    np.array(agx_particle_scale_layers)[:,None]) # layers, rgb
    n_particles_per_pixel = pixel_area_um2*density_max_fractions/agx_particle_area_um2_layers


    if fixed_seed is not None:
        seed = [int(fixed_seed), int(fixed_seed) + 1, int(fixed_seed) + 2]
    else:
        seed = [0, 1, 2]

    # --- GPU path ---
    if _backend_supports_gpu(backend):
        return _apply_grain_to_density_layers_gpu(
            density_cmy_layers,
            density_min_layers=density_min_layers,
            density_max_layers=density_max_layers,
            n_particles_per_pixel=n_particles_per_pixel,
            grain_uniformity=grain_uniformity,
            grain_blur=grain_blur,
            grain_blur_dye_clouds_um=grain_blur_dye_clouds_um,
            grain_micro_structure=grain_micro_structure,
            density_min=density_min,
            pixel_size_um=pixel_size_um,
            seed=seed,
            backend=backend,
            settings=settings,
        )

    # --- CPU path (unchanged) ---
    density_cmy_layers = density_cmy_layers.copy()
    density_cmy_layers += density_min_layers
    density_cmy_out = np.zeros(density_cmy_layers.shape[0:3])
    for ch in np.arange(3): # rgb channels
        for sl in np.arange(3): # sublayers
            density_cmy_out[:,:,ch] += layer_particle_model(density_cmy_layers[:,:,sl,ch],
                                                            density_max=density_max_layers[sl,ch],
                                                            n_particles_per_pixel=n_particles_per_pixel[sl,ch],
                                                            grain_uniformity=grain_uniformity[ch],
                                                            seed=seed[ch] + sl*10,
                                                            blur_particle=grain_blur_dye_clouds_um,
                                                            use_fast_stats=use_fast_stats)

    # micro-structure
    density_cmy_out = add_micro_structure(density_cmy_out, grain_micro_structure, pixel_size_um)

    # final
    density_cmy_out -= density_min
    if grain_blur>0:
        # density_cmy_out = scipy.ndimage.gaussian_filter(density_cmy_out, (grain_blur, grain_blur, 0))
        density_cmy_out = fast_gaussian_filter(density_cmy_out, grain_blur)
    return density_cmy_out


def _apply_grain_to_density_layers_gpu(density_cmy_layers,
                                       density_min_layers,
                                       density_max_layers,
                                       n_particles_per_pixel,
                                       grain_uniformity,
                                       grain_blur,
                                       grain_blur_dye_clouds_um,
                                       grain_micro_structure,
                                       density_min,
                                       pixel_size_um,
                                       seed,
                                       backend,
                                       settings=None):
    """GPU-accelerated layered grain application."""
    from spektrafilm.gpu.kernels.filters import gaussian_filter_backend

    mx = backend.mx
    density_cmy_layers_mx = backend.asarray(density_cmy_layers, dtype=mx.float32)
    density_min_layers_mx = backend.asarray(density_min_layers.astype(np.float32))
    density_cmy_layers_mx = density_cmy_layers_mx + density_min_layers_mx
    _materialize_large_grain_state(density_cmy_layers_mx, backend)

    out_channels = []
    for ch in range(3):
        ch_layer = mx.zeros(density_cmy_layers_mx.shape[:2], dtype=mx.float32)
        for sl in range(3):
            ch_layer = ch_layer + layer_particle_model(
                density_cmy_layers_mx[:, :, sl, ch],
                density_max=density_max_layers[sl, ch],
                n_particles_per_pixel=n_particles_per_pixel[sl, ch],
                grain_uniformity=grain_uniformity[ch],
                seed=seed[ch] + sl * 10,
                blur_particle=grain_blur_dye_clouds_um,
                backend=backend,
            )
            _materialize_large_grain_state(ch_layer, backend)
        out_channels.append(ch_layer)

    density_cmy_out = mx.stack(out_channels, axis=-1)

    # micro-structure
    density_cmy_out = add_micro_structure(density_cmy_out, grain_micro_structure, pixel_size_um, backend=backend)

    # final
    density_min_mx = backend.asarray(np.asarray(density_min, dtype=np.float32))
    density_cmy_out = density_cmy_out - density_min_mx
    if grain_blur > 0:
        overlap = int(np.ceil(3.0 * grain_blur))
        tile_rows = resolve_spatial_tile_rows(
            density_cmy_out.shape[0], overlap, backend=backend, settings=settings
        )
        if tile_rows is not None:
            def _blur_tile(tile_ext):
                return gaussian_filter_backend(tile_ext, grain_blur, backend)

            density_cmy_out = process_spatial_rows_tiled(
                density_cmy_out,
                _blur_tile,
                backend,
                overlap=overlap,
                tile_rows=tile_rows,
            )
        else:
            density_cmy_out = gaussian_filter_backend(density_cmy_out, grain_blur, backend)

    return density_cmy_out


def _apply_grain_to_density_layers_streamed_gpu(
    density_cmy,
    density_curves,
    density_curves_layers,
    density_max_layers,
    *,
    pixel_size_um,
    agx_particle_area_um2,
    agx_particle_scale,
    agx_particle_scale_layers,
    density_min,
    grain_uniformity,
    grain_blur,
    grain_blur_dye_clouds_um,
    grain_micro_structure,
    positive_film,
    backend,
    settings=None,
):
    """Layered MLX grain without retaining the nine-plane interpolation cube."""

    from spektrafilm.gpu.kernels.density import interpolate_density_cmy_layer_backend
    from spektrafilm.gpu.kernels.filters import gaussian_filter_backend

    density_max_layers = np.asarray(density_max_layers)
    density_max_total = np.sum(density_max_layers, axis=0)
    density_max_fractions = density_max_layers / density_max_total[None, :]
    density_min_layers = density_max_fractions * np.asarray(density_min)[None, :]
    density_max_layers = density_max_layers + density_min_layers
    pixel_area_um2 = pixel_size_um**2
    particle_area_layers = (
        agx_particle_area_um2
        * np.asarray(agx_particle_scale)[None, :]
        * np.asarray(agx_particle_scale_layers)[:, None]
    )
    n_particles_per_pixel = pixel_area_um2 * density_max_fractions / particle_area_layers
    seed = [0, 1, 2]

    mx = backend.mx
    density_source = backend.asarray(density_cmy, dtype=mx.float32)
    _materialize_large_grain_state(density_source, backend)
    out_channels = []
    for ch in range(3):
        ch_layer = mx.zeros(density_source.shape[:2], dtype=mx.float32)
        for sl in range(3):
            density_layer = interpolate_density_cmy_layer_backend(
                density_source,
                density_curves,
                density_curves_layers,
                sl,
                ch,
                positive_film=positive_film,
                backend=backend,
            )
            density_layer = density_layer + mx.array(density_min_layers[sl, ch], dtype=mx.float32)
            ch_layer = ch_layer + layer_particle_model(
                density_layer,
                density_max=density_max_layers[sl, ch],
                n_particles_per_pixel=n_particles_per_pixel[sl, ch],
                grain_uniformity=grain_uniformity[ch],
                seed=seed[ch] + sl * 10,
                blur_particle=grain_blur_dye_clouds_um,
                backend=backend,
            )
            _materialize_large_grain_state(ch_layer, backend)
            del density_layer
        out_channels.append(ch_layer)

    density_cmy_out = mx.stack(out_channels, axis=-1)
    density_cmy_out = add_micro_structure(
        density_cmy_out,
        grain_micro_structure,
        pixel_size_um,
        backend=backend,
    )
    density_cmy_out = density_cmy_out - backend.asarray(np.asarray(density_min, dtype=np.float32))
    if grain_blur > 0:
        overlap = int(np.ceil(3.0 * grain_blur))
        tile_rows = resolve_spatial_tile_rows(
            density_cmy_out.shape[0], overlap, backend=backend, settings=settings
        )
        if tile_rows is not None:
            def _blur_tile(tile_ext):
                return gaussian_filter_backend(tile_ext, grain_blur, backend)

            density_cmy_out = process_spatial_rows_tiled(
                density_cmy_out,
                _blur_tile,
                backend,
                overlap=overlap,
                tile_rows=tile_rows,
            )
        else:
            density_cmy_out = gaussian_filter_backend(density_cmy_out, grain_blur, backend)
    return density_cmy_out


def apply_grain(
    density_cmy,
    pixel_size_um,
    grain: GrainParams,
    density_curves,
    density_curves_layers,
    profile_type,
    bypass_grain=False,
    use_fast_stats=False,
    backend=None,
    settings=None,
):
    if not grain.active or bypass_grain:
        return density_cmy

    if not grain.sublayers_active:
        density_max = np.nanmax(density_curves, axis=0)
        grain_backend = backend
        density_input = density_cmy
        if _backend_is_unsupported_gpu(backend):
            density_input = _to_numpy_for_unsupported_gpu(density_cmy, backend)
            grain_backend = None
        return apply_grain_to_density(
            density_input,
            pixel_size_um=pixel_size_um,
            agx_particle_area_um2=grain.agx_particle_area_um2,
            agx_particle_scale=grain.agx_particle_scale,
            density_min=grain.density_min,
            density_max_curves=density_max,
            grain_uniformity=grain.uniformity,
            grain_blur=grain.blur,
            n_sub_layers=grain.n_sub_layers,
            backend=grain_backend,
            settings=settings,
        )

    density_max_layers = np.nanmax(density_curves_layers, axis=0)
    if _backend_supports_gpu(backend) and getattr(backend, "name", "") == "mlx":
        return _apply_grain_to_density_layers_streamed_gpu(
            density_cmy,
            density_curves,
            density_curves_layers,
            density_max_layers,
            pixel_size_um=pixel_size_um,
            agx_particle_area_um2=grain.agx_particle_area_um2,
            agx_particle_scale=grain.agx_particle_scale,
            agx_particle_scale_layers=grain.agx_particle_scale_layers,
            density_min=grain.density_min,
            grain_uniformity=grain.uniformity,
            grain_blur=grain.blur,
            grain_blur_dye_clouds_um=grain.blur_dye_clouds_um,
            grain_micro_structure=grain.micro_structure,
            positive_film=profile_type == "positive",
            backend=backend,
            settings=settings,
        )

    grain_backend = backend
    if _backend_supports_gpu(backend):
        from spektrafilm.gpu.kernels.density import interpolate_density_cmy_layers_backend

        density_cmy_layers = interpolate_density_cmy_layers_backend(
            density_cmy,
            density_curves,
            density_curves_layers,
            positive_film=profile_type == 'positive',
            backend=backend,
        )
    else:
        density_input = _to_numpy_for_unsupported_gpu(density_cmy, backend)
        density_cmy_layers = interp_density_cmy_layers(
            density_input,
            density_curves,
            density_curves_layers,
            positive_film=profile_type == 'positive',
        )
        if _backend_is_unsupported_gpu(backend):
            grain_backend = None
    return apply_grain_to_density_layers(
        density_cmy_layers,
        density_max_layers=density_max_layers,
        pixel_size_um=pixel_size_um,
        agx_particle_area_um2=grain.agx_particle_area_um2,
        agx_particle_scale=grain.agx_particle_scale,
        agx_particle_scale_layers=grain.agx_particle_scale_layers,
        density_min=grain.density_min,
        grain_uniformity=grain.uniformity,
        grain_blur=grain.blur,
        grain_blur_dye_clouds_um=grain.blur_dye_clouds_um,
        grain_micro_structure=grain.micro_structure,
        use_fast_stats=use_fast_stats,
        backend=grain_backend,
        settings=settings,
    )

# TODO: make grain parameter with RMS granularity

if __name__=='__main__':
    density = np.ones((128,128))*2
    g1 = layer_particle_model(density, density_max=2, n_particles_per_pixel=10, grain_uniformity=0.99, sigma_blur=0.)
    g2 = layer_particle_model(density, density_max=2, n_particles_per_pixel=10, grain_uniformity=0.96, sigma_blur=0.)
    print('g1 ------------------')
    print('Density Test')
    print('Mean', np.mean(g1))
    print('RMS', np.std(g1)*1000)
    print('Skewness', scipy.stats.skew(g1.flatten()))
    print('Kurtosis', scipy.stats.kurtosis(g1.flatten()))
    print('g2 ------------------')
    print('Mean', np.mean(g2))
    print('RMS', np.std(g2)*1000)
    print('Skewness', scipy.stats.skew(g2.flatten()))
    print('Kurtosis', scipy.stats.kurtosis(g2.flatten()))
    import matplotlib.pyplot as plt
    fig, axs = plt.subplots(1,2)
    axs[0].imshow(g1, vmin=0, vmax=2.2)
    axs[0].set_title('Uniformity=0.99')
    axs[1].imshow(g2, vmin=0, vmax=2.2)
    axs[1].set_title('Uniformity=0.96')
    fig.suptitle('Fully saturated density with different uniformity')
    plt.show()
