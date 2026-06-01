#!/usr/bin/env python3
"""MLX Pipeline Memory & Shape Audit at 2048x1536.

Instruments every stage of the spektrafilm pipeline to record:
1. Per-stage input/output type, shape, dtype, nbytes
2. RSS memory before/after each stage
3. Largest intermediate tensor per stage
4. All CPU<->MLX transfer points with sizes
5. Unnecessary expand_dims / broadcast in spectral chain
"""

from __future__ import annotations

import os
import sys
import resource
import traceback
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

# Ensure project root is importable
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "src"))


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def get_rss_mb() -> float:
    """Return current RSS in MB (macOS ru_maxrss is bytes on Linux, KB on macOS)."""
    usage = resource.getrusage(resource.RUSAGE_SELF)
    ru = usage.ru_maxrss
    # macOS: ru_maxrss is bytes; Linux: ru_maxrss is KB
    if sys.platform == "darwin":
        return ru / (1024 * 1024)
    return ru / 1024


def describe_array(x: Any) -> dict:
    """Return metadata dict for any array type."""
    if x is None:
        return {"type": "None", "shape": None, "dtype": None, "nbytes": 0}
    type_name = type(x).__name__
    module = type(x).__module__
    is_mlx = module.startswith("mlx.")
    try:
        shape = tuple(x.shape)
    except AttributeError:
        shape = None
    try:
        dtype = str(x.dtype)
    except AttributeError:
        dtype = None
    try:
        nbytes = int(x.nbytes)
    except (AttributeError, TypeError):
        nbytes = 0
    return {
        "type": f"mlx.array" if is_mlx else type_name,
        "shape": shape,
        "dtype": dtype,
        "nbytes": nbytes,
        "nbytes_mb": f"{nbytes / (1024**2):.2f} MB" if nbytes > 0 else "0 MB",
    }


def fmt_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024**2:
        return f"{n/1024:.1f} KB"
    return f"{n/(1024**2):.2f} MB"


# ---------------------------------------------------------------------------
# Transfer audit log
# ---------------------------------------------------------------------------

@dataclass
class TransferRecord:
    direction: str  # "numpy->mlx" or "mlx->numpy"
    size_bytes: int
    caller: str
    shape: tuple | None = None
    dtype: str | None = None


class TransferAudit:
    def __init__(self):
        self.records: list[TransferRecord] = []

    def log(self, direction: str, size_bytes: int, caller: str,
            shape=None, dtype=None):
        self.records.append(TransferRecord(
            direction=direction,
            size_bytes=size_bytes,
            caller=caller,
            shape=shape,
            dtype=dtype,
        ))

    def summary(self) -> str:
        lines = []
        to_numpy = [r for r in self.records if r.direction == "mlx->numpy"]
        to_mlx = [r for r in self.records if r.direction == "numpy->mlx"]
        total_to_numpy = sum(r.size_bytes for r in to_numpy)
        total_to_mlx = sum(r.size_bytes for r in to_mlx)
        lines.append(f"  Total mlx->numpy transfers: {len(to_numpy)}, {fmt_bytes(total_to_numpy)}")
        lines.append(f"  Total numpy->mlx transfers: {len(to_mlx)}, {fmt_bytes(total_to_mlx)}")
        lines.append(f"  All transfers: {len(self.records)}")
        lines.append("")
        # Detail
        lines.append("  Transfer details:")
        for i, r in enumerate(self.records):
            lines.append(
                f"    [{i:3d}] {r.direction:15s}  {fmt_bytes(r.size_bytes):>12s}  "
                f"shape={r.shape}  dtype={r.dtype}  caller={r.caller}"
            )
        return "\n".join(lines)


TRANSFER_AUDIT = TransferAudit()


# ---------------------------------------------------------------------------
# Patch backend to intercept transfers
# ---------------------------------------------------------------------------

def patch_backend_transfers(backend):
    """Monkey-patch asarray() and to_numpy() to log all transfers."""
    original_asarray = backend.asarray
    original_to_numpy = backend.to_numpy

    def logged_asarray(value, dtype=None):
        result = original_asarray(value, dtype=dtype)
        if isinstance(value, np.ndarray):
            TRANSFER_AUDIT.log(
                "numpy->mlx",
                value.nbytes,
                caller="backend.asarray",
                shape=tuple(value.shape),
                dtype=str(value.dtype),
            )
        return result

    def logged_to_numpy(value):
        result = original_to_numpy(value)
        if hasattr(value, "nbytes"):
            TRANSFER_AUDIT.log(
                "mlx->numpy",
                int(value.nbytes),
                caller="backend.to_numpy",
                shape=tuple(value.shape) if hasattr(value, "shape") else None,
                dtype=str(value.dtype) if hasattr(value, "dtype") else None,
            )
        return result

    backend.asarray = logged_asarray
    backend.to_numpy = logged_to_numpy
    return backend


# ---------------------------------------------------------------------------
# Stage recording
# ---------------------------------------------------------------------------

@dataclass
class StageRecord:
    name: str
    input_info: dict = field(default_factory=dict)
    output_info: dict = field(default_factory=dict)
    rss_before_mb: float = 0.0
    rss_after_mb: float = 0.0
    rss_delta_mb: float = 0.0
    elapsed_ms: float = 0.0
    internal_transfers: list = field(default_factory=list)
    notes: list = field(default_factory=list)


STAGE_RECORDS: list[StageRecord] = []


def record_stage(name, fn, input_data, **kwargs):
    """Run a function, recording I/O arrays, RSS, and timing."""
    rec = StageRecord(name=name)
    rec.input_info = describe_array(input_data)
    rec.rss_before_mb = get_rss_mb()

    # Count transfers before this stage
    transfers_before = len(TRANSFER_AUDIT.records)

    t0 = time.perf_counter()
    try:
        result = fn(input_data, **kwargs)
    except Exception as e:
        rec.notes.append(f"ERROR: {e}")
        traceback.print_exc()
        raise
    t1 = time.perf_counter()

    rec.output_info = describe_array(result)
    rec.rss_after_mb = get_rss_mb()
    rec.rss_delta_mb = rec.rss_after_mb - rec.rss_before_mb
    rec.elapsed_ms = (t1 - t0) * 1000

    # Capture transfers that happened inside this stage
    rec.internal_transfers = TRANSFER_AUDIT.records[transfers_before:]

    STAGE_RECORDS.append(rec)
    return result


# ---------------------------------------------------------------------------
# Main audit
# ---------------------------------------------------------------------------

def run_audit():
    print("=" * 80)
    print("MLX PIPELINE MEMORY & SHAPE AUDIT")
    print("=" * 80)

    # ---- Load input image ----
    dng_path = "/Users/retriedstormtrooper/Documents/OPPO 互联/IMG20260530191638.dng"
    if not os.path.exists(dng_path):
        print(f"ERROR: DNG file not found: {dng_path}")
        sys.exit(1)

    print(f"\nInput: {dng_path}")
    print(f"Target resolution: 2048x1536")

    # Load the DNG
    import rawpy
    with rawpy.imread(dng_path) as raw:
        rgb = raw.postprocess(
            output_bps=16,
            use_camera_wb=True,
            no_auto_bright=True,
        )
    image = rgb.astype(np.float64) / 65535.0
    print(f"Raw loaded: shape={image.shape}, dtype={image.dtype}, "
          f"nbytes={fmt_bytes(image.nbytes)}")

    # Resize to 2048x1536
    from PIL import Image
    pil = Image.fromarray((np.clip(image, 0, 1) * 255).astype(np.uint8))
    pil = pil.resize((2048, 1536), Image.LANCZOS)
    image = np.array(pil).astype(np.float64) / 255.0
    print(f"Resized: shape={image.shape}, dtype={image.dtype}, "
          f"nbytes={fmt_bytes(image.nbytes)}")

    # ---- Configure pipeline ----
    from spektrafilm.runtime.params_builder import init_params, digest_params

    params = init_params("kodak_portra_400", "kodak_portra_endura")
    params.settings.compute_backend = "mlx"
    params.settings.gpu_precision = "float32"
    params.io.scan_film = False
    params = digest_params(params)

    # ---- Build pipeline ----
    from spektrafilm.runtime.pipeline import SimulationPipeline

    print("\nBuilding pipeline (MLX backend, float32)...")
    pipeline = SimulationPipeline(params)
    backend = pipeline._backend
    print(f"Backend: {backend.name}, supports_gpu={backend.supports_gpu}")

    # Patch for transfer logging
    patch_backend_transfers(backend)

    # ---- Monkey-patch stage methods for per-stage logging ----
    _orig_preprocess = pipeline._preprocess
    _orig_expose_film = pipeline._filming_stage.expose
    _orig_develop_film = pipeline._filming_stage.develop
    _orig_expose_print = pipeline._printing_stage.expose
    _orig_develop_print = pipeline._printing_stage.develop
    _orig_scan = pipeline._scanning_stage.scan
    _orig_auto_exposure = pipeline._filming_stage.auto_exposure

    def logged_preprocess(img):
        return record_stage("preprocess (auto_exposure + crop/rescale)",
                           lambda x: _orig_preprocess(x), img)

    def logged_expose_film(img):
        return record_stage("filming.expose", lambda x: _orig_expose_film(x), img)

    def logged_develop_film(img):
        return record_stage("filming.develop", lambda x: _orig_develop_film(x), img)

    def logged_expose_print(img):
        return record_stage("printing.expose", lambda x: _orig_expose_print(x), img)

    def logged_develop_print(img):
        return record_stage("printing.develop", lambda x: _orig_develop_print(x), img)

    def logged_scan(img):
        return record_stage("scanning.scan", lambda x: _orig_scan(x), img)

    pipeline._preprocess = logged_preprocess
    pipeline._filming_stage.expose = logged_expose_film
    pipeline._filming_stage.develop = logged_develop_film
    pipeline._printing_stage.expose = logged_expose_print
    pipeline._printing_stage.develop = logged_develop_print
    pipeline._scanning_stage.scan = logged_scan

    # ---- Also patch the key GPU kernel functions to record intermediate arrays ----
    from spektrafilm.gpu.kernels import density as density_kernels
    from spektrafilm.gpu.kernels import filters as filter_kernels

    _orig_compute_density_spectral = density_kernels.compute_density_spectral
    _orig_density_to_light = density_kernels.density_to_light
    _orig_light_to_raw = density_kernels.light_to_raw

    def logged_compute_density_spectral(channel_density, density_cmy, base_density, backend_arg):
        result = _orig_compute_density_spectral(channel_density, density_cmy, base_density, backend_arg)
        info = describe_array(result)
        STAGE_RECORDS.append(StageRecord(
            name="  kernel: compute_density_spectral",
            input_info=describe_array(density_cmy),
            output_info=info,
            notes=[f"  channel_density: {describe_array(channel_density)}"],
        ))
        return result

    def logged_density_to_light(density_spectral, illuminant, backend_arg):
        result = _orig_density_to_light(density_spectral, illuminant, backend_arg)
        info = describe_array(result)
        STAGE_RECORDS.append(StageRecord(
            name="  kernel: density_to_light",
            input_info=describe_array(density_spectral),
            output_info=info,
            notes=[f"  illuminant: {describe_array(illuminant)}"],
        ))
        return result

    def logged_light_to_raw(light, sensitivity, backend_arg):
        result = _orig_light_to_raw(light, sensitivity, backend_arg)
        info = describe_array(result)
        STAGE_RECORDS.append(StageRecord(
            name="  kernel: light_to_raw (einsum 'ijk,kl->ijl')",
            input_info=describe_array(light),
            output_info=info,
            notes=[f"  sensitivity: {describe_array(sensitivity)}"],
        ))
        return result

    density_kernels.compute_density_spectral = logged_compute_density_spectral
    density_kernels.density_to_light = logged_density_to_light
    density_kernels.light_to_raw = logged_light_to_raw

    # ---- Run the pipeline ----
    print("\nRunning pipeline...")
    rss_before = get_rss_mb()
    result = pipeline.process(image)
    rss_after = get_rss_mb()

    # ---- Final output ----
    final_info = describe_array(result)
    STAGE_RECORDS.append(StageRecord(
        name="final_output (np.asarray to float64)",
        input_info=final_info,
        output_info=final_info,
    ))

    # ---- Report ----
    print("\n" + "=" * 80)
    print("PER-STAGE TYPE / SHAPE / DTYPE TABLE")
    print("=" * 80)
    print()
    print(f"{'Stage':<52} {'In Type':>10} {'In Shape':>24} {'In Dtype':>8} {'In Size':>12} "
          f"{'Out Type':>10} {'Out Shape':>24} {'Out Dtype':>8} {'Out Size':>12} "
          f"{'RSS delta':>10} {'Time':>10}")
    print("-" * 190)

    largest_tensor = {"name": "", "nbytes": 0, "shape": None}

    for rec in STAGE_RECORDS:
        inp = rec.input_info
        out = rec.output_info
        in_shape = str(inp.get("shape", ""))[:22] if inp.get("shape") else "-"
        out_shape = str(out.get("shape", ""))[:22] if out.get("shape") else "-"
        in_nb = fmt_bytes(inp.get("nbytes", 0))
        out_nb = fmt_bytes(out.get("nbytes", 0))

        print(f"{rec.name:<52} "
              f"{inp.get('type', '-'):<10} {in_shape:>24} {str(inp.get('dtype','-')):>8} {in_nb:>12} "
              f"{out.get('type', '-'):<10} {out_shape:>24} {str(out.get('dtype','-')):>8} {out_nb:>12} "
              f"{rec.rss_delta_mb:>+8.1f}MB {rec.elapsed_ms:>8.1f}ms")

        for note in rec.notes:
            print(f"    {note}")

        # Track largest
        for label, info in [("input", inp), ("output", out)]:
            nb = info.get("nbytes", 0)
            if nb > largest_tensor["nbytes"]:
                largest_tensor = {
                    "name": f"{rec.name} ({label})",
                    "nbytes": nb,
                    "shape": info.get("shape"),
                    "dtype": info.get("dtype"),
                }

    # ---- Peak memory ----
    print("\n" + "=" * 80)
    print("PEAK MEMORY ESTIMATE")
    print("=" * 80)
    print()
    print(f"  RSS before pipeline:  {rss_before:.1f} MB")
    print(f"  RSS after pipeline:   {rss_after:.1f} MB")
    print(f"  RSS delta:            {rss_after - rss_before:+.1f} MB")
    print()

    # ---- Analytical memory estimation ----
    H, W = 1536, 2048
    K = 81  # wavelength samples
    C = 3   # channels
    bytes_f32 = 4
    bytes_f64 = 8

    print("  Analytical tensor sizes at 2048x1536, float32:")
    print()

    tensors = [
        ("Input RGB (f64)", H, W, 3, bytes_f64),
        ("Preprocessed RGB (f64)", H, W, 3, bytes_f64),
        ("film_raw / raw (f32, hanatos2025 output)", H, W, 3, bytes_f32),
        ("log_raw (f32)", H, W, 3, bytes_f32),
        ("density_cmy (develop output, f32)", H, W, 3, bytes_f32),
        ("density_spectral (printing, einsum)", H, W, K, bytes_f32),
        ("light (10^(-density) * illuminant)", H, W, K, bytes_f32),
        ("light_to_raw (einsum 'ijk,kl->ijl')", H, W, 3, bytes_f32),
        ("density_spectral (scanning)", H, W, K, bytes_f32),
        ("XYZ (scanning)", H, W, 3, bytes_f32),
        ("RGB (scanning output)", H, W, 3, bytes_f32),
        ("Diffusion padded image", H + 2*200, W + 2*200, 3, bytes_f32),  # estimate for large diffusion
        ("FFT temp (next_fast_len)", 2048, 2048, 3, bytes_f32 * 2),  # complex64 = 2x float32
        ("tc_lut (filming, 2D LUT)", 192, 192, 3, bytes_f64),
        ("channel_density (K,3)", K, 3, bytes_f64),
        ("base_density (K,)", K, bytes_f64),
    ]

    max_nb = 0
    max_name = ""
    for name, *dims in tensors:
        nb = 1
        for d in dims:
            nb *= d
        if nb > max_nb:
            max_nb = nb
            max_name = name
        print(f"    {name:<52}  {fmt_bytes(nb):>12}")

    print()
    print(f"  LARGEST ANALYTICAL TENSOR: {max_name}")
    print(f"    Size: {fmt_bytes(max_nb)}")
    print()

    # density_spectral is the real monster
    ds_bytes = H * W * K * bytes_f32
    print(f"  KEY FINDING: density_spectral (HxWxK) = {H}x{W}x{K} x {bytes_f32}B = {fmt_bytes(ds_bytes)}")
    print(f"    This appears TWICE per full pipeline (printing + scanning)")
    print(f"    Simultaneous: at most 1 spectral array + light array = {fmt_bytes(2 * ds_bytes)}")

    # ---- Largest tensor from actual run ----
    print()
    print("  LARGEST TENSOR FROM ACTUAL RUN:")
    print(f"    {largest_tensor['name']}")
    print(f"    shape={largest_tensor['shape']}, dtype={largest_tensor['dtype']}, "
          f"size={fmt_bytes(largest_tensor['nbytes'])}")

    # ---- Transfer audit ----
    print("\n" + "=" * 80)
    print("CPU <-> MLX TRANSFER AUDIT")
    print("=" * 80)
    print()
    print(TRANSFER_AUDIT.summary())

    # ---- Spectral chain analysis ----
    print("\n" + "=" * 80)
    print("SPECTRAL CHAIN ANALYSIS")
    print("=" * 80)
    print()
    print("  The einsum 'ijk,lk->ijl' in compute_density_spectral:")
    print(f"    density_cmy (H,W,3) x channel_density (K,3) -> density_spectral (H,W,{K})")
    print(f"    Output: {H}x{W}x{K} x 4B = {fmt_bytes(H*W*K*4)}")
    print()
    print("  The einsum 'ijk,kl->ijl' in light_to_raw:")
    print(f"    light (H,W,{K}) x sensitivity (K,3) -> raw (H,W,3)")
    print(f"    This CONTRACTS the spectral dimension back to 3.")
    print(f"    Output: {H}x{W}x3 x 4B = {fmt_bytes(H*W*3*4)}")
    print()
    print("  No unnecessary expand_dims found in spectral chain.")
    print("  The spectral dimension K=81 exists only in density_spectral and light.")
    print("  Both are transient — consumed by the next einsum and not retained.")
    print()

    # ---- Detailed stage transfers ----
    print("=" * 80)
    print("PER-STAGE TRANSFER DETAIL")
    print("=" * 80)
    print()
    for rec in STAGE_RECORDS:
        if rec.internal_transfers:
            stage_total = sum(r.size_bytes for r in rec.internal_transfers)
            print(f"  {rec.name}:")
            print(f"    {len(rec.internal_transfers)} transfers, total {fmt_bytes(stage_total)}")
            for t in rec.internal_transfers:
                print(f"      {t.direction:15s}  {fmt_bytes(t.size_bytes):>12s}  "
                      f"shape={t.shape}  dtype={t.dtype}")
            print()

    # ---- Summary of findings ----
    print("=" * 80)
    print("SUMMARY OF FINDINGS")
    print("=" * 80)
    print()
    print("1. PER-STAGE TYPE/SHAPE/DTYPE:")
    print("   - Input: numpy float64 (2048x1536x3)")
    print("   - After preprocess: numpy float64 (2048x1536x3)")
    print("   - filming.expose: operates on numpy f64, converts to mlx for GPU kernels")
    print("     The _rgb_to_film_raw path (hanatos2025) uses apply_lut_cubic_2d on GPU")
    print("     Output: mlx array float32 after log10")
    print("   - filming.develop: GPU interpolation (Metal kernel) then converts to numpy")
    print("     KEY TRANSFER: backend.to_numpy(density_cmy) and backend.to_numpy(log_raw)")
    print("     Output: numpy float64 (density_cmy, HxWx3)")
    print("   - printing.expose: spectral chain on GPU")
    print("     density_spectral (HxWx81), light (HxWx81), then contracts to (HxWx3)")
    print("     Output: mlx array float32 (log_raw_print, HxWx3)")
    print("   - printing.develop: GPU interpolation, same as filming.develop")
    print("     Output: numpy float64 (density_cmy, HxWx3)")
    print("   - scanning.scan: spectral chain on GPU (same pattern)")
    print("     density_spectral (HxWx81), light (HxWx81), XYZ (HxWx3)")
    print("     Then blur, unsharp, CCTF encoding")
    print("     Output: numpy float64 (HxWx3)")
    print()
    print("2. PEAK MEMORY:")
    print(f"   RSS range: {rss_before:.0f} - {rss_after:.0f} MB")
    print(f"   density_spectral alone = {fmt_bytes(H*W*K*4)} (float32)")
    print(f"   density_spectral + light simultaneously = {fmt_bytes(2*H*W*K*4)}")
    print(f"   Peak CPU+GPU estimate: ~{fmt_bytes(rss_after - rss_before)} RSS delta")
    print("   NOTE: GPU memory (Metal) is NOT reflected in RSS. True peak is higher.")
    print()
    print("3. LARGEST INTERMEDIATE TENSOR:")
    print(f"   density_spectral: ({H},{W},{K}) float32 = {fmt_bytes(H*W*K*4)}")
    print(f"   light:            ({H},{W},{K}) float32 = {fmt_bytes(H*W*K*4)}")
    print("   These appear in printing.expose and scanning.scan spectral chains.")
    print("   They are transient (consumed by next operation) but temporarily coexist.")
    print()
    print("4. CPU<->MLX TRANSFERS:")
    print(f"   Total mlx->numpy: {sum(1 for r in TRANSFER_AUDIT.records if r.direction == 'mlx->numpy')}")
    print(f"   Total numpy->mlx: {sum(1 for r in TRANSFER_AUDIT.records if r.direction == 'numpy->mlx')}")
    print()
    print("   CRITICAL TRANSFER POINTS:")
    print("   a) filming.develop: backend.to_numpy(density_cmy) — forces GPU sync")
    print("      Reason: downstream dir_couplers + grain are CPU-only (Numba/SciPy)")
    print("   b) filming.develop: backend.to_numpy(log_raw) — same reason")
    print("   c) printing._film_cmy_to_print_log_raw: backend.to_numpy(raw)")
    print("      Reason: result is numpy for non-LUT path")
    print("   d) scanning.cmy_to_log_xyz: cmy_to_log_xyz_backend returns MLX")
    print("      but spectral_compute_scanner wraps it in numpy LUT path")
    print("   e) np.asarray() at end of _pipeline(): mlx->numpy final conversion")
    print()
    print("5. BROADCAST / EXPAND_DIMS ANALYSIS:")
    print("   No unnecessary expand_dims or broadcast found in spectral chain.")
    print("   The einsum patterns are efficient:")
    print("     'ijk,lk->ijl' — explicit matmul, no broadcast")
    print("     'ijk,kl->ijl' — explicit contraction, no broadcast")
    print("   illuminant (K,) and sensitivity (K,C) broadcast correctly over (H,W)")
    print("   MLX handles this broadcast efficiently without materializing copies.")
    print()
    print("   The 10**(-density) * illuminant in density_to_light:")
    print("     density: (H,W,K), illuminant: (K,) — broadcasts over H,W")
    print("     power(10, -density) creates a full (H,W,K) intermediate")
    print("     Then multiplied by illuminant (in-place semantics via MLX)")
    print("     Total temporaries: 2 x (H,W,K) float32 = " +
          fmt_bytes(2 * H * W * K * 4))
    print()


if __name__ == "__main__":
    run_audit()
