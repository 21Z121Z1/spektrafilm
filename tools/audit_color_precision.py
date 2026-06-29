#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

OPERATIONS = ("cctf", "rgb-xyz", "lut2d", "jzazbz", "spectral")
DEFAULT_PRECISION_POLICY = "balanced"


def _load_runtime() -> None:
    """Import NumPy and Spektrafilm only when an audit actually runs.

    This keeps ``python tools/audit_color_precision.py --help`` usable with a
    bare system Python that has no project dependencies installed.
    """
    global np
    global BackendUnavailableError, select_backend
    global cctf_decoding_transfer_backend, cctf_encoding_backend
    global precompute_rgb_to_xyz_matrix, precompute_xyz_to_rgb_matrix
    global rgb_to_raw_mallett2019_backend, rgb_to_xyz, xyz_to_rgb
    global compress_rgb_backend
    global apply_lut_cubic_2d_backend, apply_lut_cubic_2d_numpy
    global OP_CCTF, OP_GAMUT_JZAZBZ, OP_LUT_2D_MITCHELL
    global OP_RGB_XYZ_MATRIX, OP_SPECTRAL_REDUCTION
    global precision_decision, precision_metrics
    global OutputGamutCompressSpec, compress_rgb, rgb_to_raw_mallett2019

    if "np" in globals():
        return

    import numpy as np  # noqa: F401

    from spektrafilm.gpu.backend import BackendUnavailableError, select_backend  # noqa: F401
    from spektrafilm.gpu.kernels.color import (  # noqa: F401
        cctf_decoding_transfer_backend,
        cctf_encoding_backend,
        precompute_rgb_to_xyz_matrix,
        precompute_xyz_to_rgb_matrix,
        rgb_to_raw_mallett2019_backend,
        rgb_to_xyz,
        xyz_to_rgb,
    )
    from spektrafilm.gpu.kernels.gamut_compress import compress_rgb_backend  # noqa: F401
    from spektrafilm.gpu.kernels.lut import (  # noqa: F401
        apply_lut_cubic_2d_backend,
        apply_lut_cubic_2d_numpy,
    )
    from spektrafilm.gpu.precision_policy import (  # noqa: F401
        OP_CCTF,
        OP_GAMUT_JZAZBZ,
        OP_LUT_2D_MITCHELL,
        OP_RGB_XYZ_MATRIX,
        OP_SPECTRAL_REDUCTION,
        precision_decision,
        precision_metrics,
    )
    from spektrafilm.utils.gamut_compression import OutputGamutCompressSpec, compress_rgb  # noqa: F401
    from spektrafilm.utils.spectral_upsampling import rgb_to_raw_mallett2019  # noqa: F401


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float):
        if np.isinf(value):
            return "inf"
        if np.isnan(value):
            return "nan"
    if hasattr(value, "__dict__"):
        return value.__dict__
    return value


def _make_backend(name: str):
    if name == "cpu":
        return select_backend("cpu")
    if name == "mlx":
        return select_backend("mlx", precision="float32")
    raise ValueError(f"Unsupported backend: {name}")


def _readback(backend, value: Any) -> np.ndarray:
    if backend is not None and getattr(backend, "supports_gpu", False):
        backend.synchronize()
        return np.asarray(backend.to_numpy(value), dtype=np.float64)
    return np.asarray(value, dtype=np.float64)


def audit_cctf(rng: np.random.Generator, backend) -> dict[str, Any]:
    rgb = rng.uniform(-0.05, 1.25, size=(32, 17, 3)).astype(np.float64)
    boundaries = np.array(
        [
            np.nextafter(np.float32(0.0031308), np.float32(0.0)),
            np.float32(0.0031308),
            np.nextafter(np.float32(0.0031308), np.float32(1.0)),
            np.nextafter(np.float32(0.04045), np.float32(0.0)),
            np.float32(0.04045),
            np.nextafter(np.float32(0.04045), np.float32(1.0)),
        ],
        dtype=np.float32,
    )
    rgb[:2, :3, 0] = boundaries.reshape(2, 3)

    from spektrafilm.gpu.numpy_backend import NumpyBackend

    ref_backend = NumpyBackend()
    encoded_ref = cctf_encoding_backend(rgb.astype(np.float32), "sRGB", ref_backend)
    decoded_ref = cctf_decoding_transfer_backend(encoded_ref, "sRGB", ref_backend)
    encoded = cctf_encoding_backend(rgb.astype(np.float32), "sRGB", backend)
    decoded = cctf_decoding_transfer_backend(encoded, "sRGB", backend)
    return {
        "operation": "cctf",
        "metrics": precision_metrics(decoded_ref, _readback(backend, decoded)),
        "notes": "sRGB float32 branch-threshold encode/decode roundtrip",
    }


def audit_rgb_xyz(rng: np.random.Generator, backend) -> dict[str, Any]:
    rgb = rng.uniform(-0.1, 1.2, size=(64, 3)).astype(np.float64)
    m_rgb_xyz = precompute_rgb_to_xyz_matrix("sRGB")
    m_xyz_rgb = precompute_xyz_to_rgb_matrix("sRGB")
    xyz_ref = rgb @ m_rgb_xyz.T
    roundtrip_ref = xyz_ref @ m_xyz_rgb.T
    xyz = rgb_to_xyz(rgb.astype(np.float32), backend.asarray(m_rgb_xyz), backend)
    roundtrip = xyz_to_rgb(xyz, backend.asarray(m_xyz_rgb), backend)
    return {
        "operation": "rgb-xyz",
        "metrics": precision_metrics(roundtrip_ref, _readback(backend, roundtrip)),
        "matrix_dtype": str(m_rgb_xyz.dtype),
        "matrix_shape": list(m_rgb_xyz.shape),
        "finite": bool(np.isfinite(m_rgb_xyz).all() and np.isfinite(m_xyz_rgb).all()),
    }


def audit_lut2d(rng: np.random.Generator, backend, policy: str) -> dict[str, Any]:
    size = 17
    x = np.linspace(0.0, 1.0, size)
    xx, yy = np.meshgrid(x, x, indexing="ij")
    lut = np.stack(
        [
            0.65 * xx + 0.35 * yy,
            np.sin(xx * np.pi) * 0.2 + yy,
            np.cos(yy * np.pi * 0.5) * 0.3 + xx * yy,
        ],
        axis=-1,
    ).astype(np.float64)
    coords = rng.uniform(-0.05, 1.05, size=(25, 19, 2)).astype(np.float64)
    ref = apply_lut_cubic_2d_numpy(lut, coords)
    decision = precision_decision(
        OP_LUT_2D_MITCHELL,
        policy=policy,
        backend_name=getattr(backend, "name", None),
        gpu_precision=getattr(backend, "precision", "float32"),
    )
    if decision.fallback_to_cpu:
        candidate = ref
        notes = f"Mitchell 2D LUT policy fallback to CPU reference under policy={policy}"
    else:
        candidate = apply_lut_cubic_2d_backend(lut, backend.asarray(coords), backend)
        notes = f"Mitchell 2D LUT resident backend path under policy={policy}"
    return {
        "operation": "lut2d",
        "metrics": precision_metrics(ref, _readback(backend, candidate)),
        "notes": notes,
    }


def audit_jzazbz(rng: np.random.Generator, backend, policy: str) -> dict[str, Any]:
    rgb = rng.uniform(-0.1, 1.5, size=(18, 13, 3)).astype(np.float32)
    spec = OutputGamutCompressSpec(algorithm="jzazbz", lightness_compression=(0.75, 1.0, 2.0))
    ref = compress_rgb(rgb.astype(float), spec, output_color_space="sRGB")
    candidate = compress_rgb_backend(
        backend.asarray(rgb),
        spec,
        output_color_space="sRGB",
        backend=backend,
        precision_policy=policy,
    )
    return {
        "operation": "jzazbz",
        "metrics": precision_metrics(ref, _readback(backend, candidate)),
        "notes": f"JzAzBz gamut compression under policy={policy}",
    }


def audit_spectral(rng: np.random.Generator, backend) -> dict[str, Any]:
    rgb = rng.uniform(0.0, 1.0, size=(20, 11, 3)).astype(np.float32)
    sensitivity = rng.uniform(0.0, 1.0, size=(81, 3)).astype(np.float64)
    ref = rgb_to_raw_mallett2019(
        rgb.astype(float),
        sensitivity,
        color_space="sRGB",
        apply_cctf_decoding=True,
        reference_illuminant="D65",
    )
    candidate = rgb_to_raw_mallett2019_backend(
        backend.asarray(rgb),
        sensitivity,
        color_space="sRGB",
        apply_cctf_decoding=True,
        reference_illuminant="D65",
        backend=backend,
    )
    return {
        "operation": "spectral",
        "metrics": precision_metrics(ref, _readback(backend, candidate)),
        "notes": "Mallett 2019 RGB-to-raw spectral reduction",
    }


def _parse_operations(value: str) -> list[str]:
    if value == "all":
        return list(OPERATIONS)
    requested = [item.strip() for item in value.split(",") if item.strip()]
    unknown = [item for item in requested if item not in OPERATIONS]
    if unknown:
        raise argparse.ArgumentTypeError(
            f"unknown operation(s): {', '.join(unknown)}; expected all or one of {', '.join(OPERATIONS)}"
        )
    return requested


def _format_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Spektrafilm Color Precision Audit",
        "",
        f"- backend: `{report['backend']}`",
        f"- selected_backend: `{report['selected_backend']}`",
        f"- policy: `{report['policy']}`",
        f"- seed: `{report['seed']}`",
        "",
        "| Operation | Policy status | max_abs | mean_abs | max_rel | rmse | PSNR dB | Notes |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in report["results"]:
        if item.get("skipped"):
            lines.append(
                f"| {item['operation']} | skipped |  |  |  |  |  | {item['reason']} |"
            )
            continue
        metrics = item["metrics"]
        decision = item["decision"]
        psnr = metrics.get("psnr_db", 0.0)
        psnr_text = "inf" if psnr == float("inf") else f"{psnr:.6g}"
        lines.append(
            "| {op} | {status} | {max_abs:.6g} | {mean_abs:.6g} | {max_rel:.6g} | "
            "{rmse:.6g} | {psnr} | {notes} |".format(
                op=item["operation"],
                status=decision["status"],
                max_abs=metrics.get("max_abs", 0.0),
                mean_abs=metrics.get("mean_abs", 0.0),
                max_rel=metrics.get("max_rel", 0.0),
                rmse=metrics.get("rmse", 0.0),
                psnr=psnr_text,
                notes=item.get("notes", ""),
            )
        )
    return "\n".join(lines) + "\n"


def run(args: argparse.Namespace) -> dict[str, Any]:
    _load_runtime()
    rng = np.random.default_rng(args.seed)
    try:
        backend = _make_backend(args.backend)
        selected_backend = getattr(backend, "name", args.backend)
        backend_error = None
    except (BackendUnavailableError, ValueError, ImportError, RuntimeError) as exc:
        backend = None
        selected_backend = "unavailable"
        backend_error = str(exc)

    report: dict[str, Any] = {
        "backend": args.backend,
        "selected_backend": selected_backend,
        "policy": args.policy,
        "seed": args.seed,
        "results": [],
    }

    auditors: dict[str, tuple[str, Callable[..., dict[str, Any]]]] = {
        "cctf": (OP_CCTF, audit_cctf),
        "rgb-xyz": (OP_RGB_XYZ_MATRIX, audit_rgb_xyz),
        "lut2d": (OP_LUT_2D_MITCHELL, audit_lut2d),
        "jzazbz": (OP_GAMUT_JZAZBZ, audit_jzazbz),
        "spectral": (OP_SPECTRAL_REDUCTION, audit_spectral),
    }

    for operation in args.operations:
        policy_op, auditor = auditors[operation]
        decision = precision_decision(
            policy_op,
            policy=args.policy,
            backend_name=selected_backend,
            gpu_precision=getattr(backend, "precision", "float32") if backend is not None else "float32",
        )
        if backend is None:
            report["results"].append(
                {
                    "operation": operation,
                    "skipped": True,
                    "reason": f"backend unavailable: {backend_error}",
                    "decision": asdict(decision),
                }
            )
            continue
        try:
            if operation in {"jzazbz", "lut2d"}:
                item = auditor(rng, backend, args.policy)
            else:
                item = auditor(rng, backend)
            item["decision"] = asdict(decision)
            report["results"].append(item)
        except Exception as exc:  # pragma: no cover - audit tool should report, not crash mid-report.
            report["results"].append(
                {
                    "operation": operation,
                    "skipped": True,
                    "reason": f"audit failed: {type(exc).__name__}: {exc}",
                    "decision": asdict(decision),
                }
            )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__ or "Audit Spektrafilm color precision.")
    parser.add_argument(
        "--operation",
        dest="operations",
        default=list(OPERATIONS),
        type=_parse_operations,
        help="Operation subset: all or comma-separated one of cctf,rgb-xyz,lut2d,jzazbz,spectral.",
    )
    parser.add_argument("--backend", choices=("cpu", "mlx"), default="cpu")
    parser.add_argument("--seed", type=int, default=20260629)
    parser.add_argument("--policy", choices=("fast", "balanced", "strict"), default=DEFAULT_PRECISION_POLICY)
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--output", type=Path, help="Optional report output path.")
    args = parser.parse_args(argv)

    report = run(args)
    if args.format == "json":
        text = json.dumps(report, indent=2, default=_jsonable, sort_keys=True) + "\n"
    else:
        text = _format_markdown(report)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
