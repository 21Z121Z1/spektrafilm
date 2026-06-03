import numpy as np
from spektrafilm.gpu.mlx_backend import MlxBackend
from spektrafilm.runtime.params_schema import OutputGamutCompressSpec
from spektrafilm.utils.gamut_compression import compress_rgb
from spektrafilm.gpu.kernels.gamut_compress import compress_rgb_backend

backend = MlxBackend(precision="float32")

# Create some random linear RGB values that are out of gamut
rng = np.random.default_rng(42)
rgb_cpu = rng.uniform(-0.5, 2.5, size=(100, 100, 3)).astype(np.float32)

spec = OutputGamutCompressSpec(
    algorithm="oklch",
    knee=(0.8, 1.2, 1.2),
    lightness_compression=(0.8, 1.2, 1.2)
)
output_color_space = "sRGB"

print("Running CPU version...")
res_cpu = compress_rgb(rgb_cpu, spec, output_color_space=output_color_space)

print("Running MLX version...")
# Warmup
rgb_mlx = backend.asarray(rgb_cpu)
_ = compress_rgb_backend(rgb_mlx, spec, output_color_space=output_color_space, backend=backend)
backend.eval(_)

# Actual
res_mlx_arr = compress_rgb_backend(rgb_mlx, spec, output_color_space=output_color_space, backend=backend)
res_mlx = backend.to_numpy(res_mlx_arr)

diff = np.abs(res_cpu - res_mlx)
max_diff = np.max(diff)
print(f"Max difference: {max_diff:.6e}")
print(f"Match (atol=1e-4): {np.allclose(res_cpu, res_mlx, atol=1e-4)}")

# Test oklrab
print("\nTesting oklrab...")
spec.algorithm = "oklrab"
res_cpu_oklrab = compress_rgb(rgb_cpu, spec, output_color_space=output_color_space)
res_mlx_oklrab_arr = compress_rgb_backend(rgb_mlx, spec, output_color_space=output_color_space, backend=backend)
res_mlx_oklrab = backend.to_numpy(res_mlx_oklrab_arr)
print(f"Max difference oklrab: {np.max(np.abs(res_cpu_oklrab - res_mlx_oklrab)):.6e}")
print(f"Match (atol=1e-4): {np.allclose(res_cpu_oklrab, res_mlx_oklrab, atol=1e-4)}")

# Test aces_rgc
print("\nTesting aces_rgc...")
spec.algorithm = "aces_rgc"
res_cpu_aces = compress_rgb(rgb_cpu, spec, output_color_space=output_color_space)
res_mlx_aces_arr = compress_rgb_backend(rgb_mlx, spec, output_color_space=output_color_space, backend=backend)
res_mlx_aces = backend.to_numpy(res_mlx_aces_arr)
print(f"Max difference aces_rgc: {np.max(np.abs(res_cpu_aces - res_mlx_aces)):.6e}")
print(f"Match (atol=1e-4): {np.allclose(res_cpu_aces, res_mlx_aces, atol=1e-4)}")
