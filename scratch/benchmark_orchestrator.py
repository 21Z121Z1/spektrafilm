import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def run_case(backend, width, height, diffusion=True):
    cmd = [
        str(ROOT / ".venv" / "bin" / "python"),
        str(ROOT / "scratch" / "run_case.py"),
        "--backend", backend,
        "--width", str(width),
        "--height", str(height),
    ]
    if diffusion:
        cmd.append("--diffusion")
    
    print(f"Running: {' '.join(cmd)} ... ", end="", flush=True)
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=300)
        # Find JSON line
        for line in res.stdout.splitlines():
            if line.startswith("{") and line.endswith("}"):
                data = json.loads(line)
                print(f"Success. peak_rss={data['peak_rss_mb']:.1f}MB, run_time={data['run_time_sec']:.3f}s")
                return data
    except subprocess.TimeoutExpired:
        print("Timeout (5 minutes)!")
        return {"status": "timeout", "backend": backend, "width": width, "height": height}
    except subprocess.CalledProcessError as e:
        print(f"Failed. Code: {e.returncode}")
        print("Stdout:", e.stdout)
        print("Stderr:", e.stderr)
        return {"status": "error", "backend": backend, "width": width, "height": height, "error": e.stderr}

def main():
    cases = [
        # (backend, width, height, name)
        ("mlx", 1280, 960, "1.2MP"),
        ("cpu", 1280, 960, "1.2MP"),
        ("mlx", 4000, 3000, "12MP"),
        ("cpu", 4000, 3000, "12MP (Only if safe)"),
        ("mlx", 8192, 6144, "50MP"),
    ]
    
    # We will skip CPU 12MP if it is too slow, but let's try running it.
    # We will skip CPU 50MP entirely because it is guaranteed to cause swap/OOM.
    
    results = []
    for backend, w, h, name in cases:
        if backend == "cpu" and w >= 4000:
            print(f"Skipping CPU {name} benchmark to prevent OOM/extreme lag...")
            results.append({
                "backend": "cpu",
                "width": w,
                "height": h,
                "megapixels": (w * h) / 1e6,
                "warmup_time_sec": None,
                "run_time_sec": None,
                "peak_rss_mb": None,
                "mlx_cache_mb": 0.0,
                "status": "skipped_protection"
            })
            continue
            
        res = run_case(backend, w, h)
        if res:
            results.append(res)
            
    # Output markdown report format
    print("\n\n=== BENCHMARK REPORT ===")
    print("| Backend | Resolution | Megapixels | Warmup Time (s) | Run Time (s) | Peak RSS (MB) | MLX Cache (MB) |")
    print("|---|---|---|---|---|---|---|")
    for r in results:
        res_str = f"{r['width']}x{r['height']}"
        mp_str = f"{r['megapixels']:.2f}"
        if r["status"] == "success":
            warmup = f"{r['warmup_time_sec']:.3f}"
            run_t = f"{r['run_time_sec']:.3f}"
            rss = f"{r['peak_rss_mb']:.1f}"
            cache = f"{r['mlx_cache_mb']:.1f}"
        elif r["status"] == "skipped_protection":
            warmup = "Skipped"
            run_t = "Skipped"
            rss = "N/A"
            cache = "0.0"
        else:
            warmup = "Error"
            run_t = "Error"
            rss = "N/A"
            cache = "0.0"
        print(f"| {r['backend'].upper()} | {res_str} | {mp_str} | {warmup} | {run_t} | {rss} | {cache} |")

if __name__ == "__main__":
    main()
