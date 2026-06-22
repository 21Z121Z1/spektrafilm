import sys
import time
import json
import argparse
import resource
import numpy as np

# Add src to sys.path
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spektrafilm.runtime.params_builder import digest_params, init_params
from spektrafilm.runtime.pipeline import SimulationPipeline

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["cpu", "mlx"], required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--precision", choices=["float32", "float64"], default="float32")
    parser.add_argument("--diffusion", action="store_true", default=True)
    args = parser.parse_args()

    # Generate dummy input image in [0, 1]
    # Film scanning pipeline expects float32 or float64 input image
    image = np.linspace(0.0, 1.0, args.width, dtype=np.float32)[None, :]
    image = np.broadcast_to(image, (args.height, args.width))
    # 3 channels
    image = np.stack([image, image, image], axis=-1).copy()

    # Initialize params
    params = init_params(film_profile="kodak_portra_400", print_profile="kodak_portra_endura")
    params.settings.compute_backend = args.backend
    params.settings.gpu_precision = args.precision
    
    # Configure filters as requested
    params.film_render.grain.active = True
    # Ensure halation is active
    params.film_render.halation.active = True
    
    # Ensure diffusion filter is active
    if args.diffusion:
        params.camera.diffusion_filter.active = True
        params.camera.diffusion_filter.filter_family = "black_pro_mist"
        params.camera.diffusion_filter.strength = 0.5
    else:
        params.camera.diffusion_filter.active = False

    # Build pipeline
    digested = digest_params(params)
    pipeline = SimulationPipeline(digested)

    # We want to measure the peak RSS of the process.
    # To get a baseline, we measure RSS before running the process.
    # On macOS, ru_maxrss is in bytes.
    
    # Helper to sync backend
    def sync_backend():
        if args.backend == "mlx":
            import mlx.core as mx
            mx.eval()
            mx.synchronize()

    # Warmup / JIT Compile (First Run)
    t0 = time.perf_counter()
    out1 = pipeline.process(image.copy())
    sync_backend()
    t1 = time.perf_counter()
    warmup_time = t1 - t0

    # Active Run (Second Run)
    t2 = time.perf_counter()
    out2 = pipeline.process(image.copy())
    sync_backend()
    t3 = time.perf_counter()
    run_time = t3 - t2

    # Measure memory
    max_rss_bytes = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    max_rss_mb = max_rss_bytes / (1024 * 1024) if sys.platform == "darwin" else max_rss_bytes / 1024

    # MLX specific cache memory
    mlx_cache_mb = 0.0
    if args.backend == "mlx":
        import mlx.core as mx
        for owner in (mx, getattr(mx, "metal", None)):
            getter = getattr(owner, "get_cache_memory", None)
            if callable(getter):
                try:
                    mlx_cache_mb = float(getter()) / (1024 * 1024)
                    break
                except Exception:
                    pass

    # Print results as JSON
    result = {
        "backend": args.backend,
        "width": args.width,
        "height": args.height,
        "megapixels": (args.width * args.height) / 1e6,
        "warmup_time_sec": warmup_time,
        "run_time_sec": run_time,
        "peak_rss_mb": max_rss_mb,
        "mlx_cache_mb": mlx_cache_mb,
        "status": "success"
    }
    print(json.dumps(result))

if __name__ == "__main__":
    main()
