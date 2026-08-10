from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "tools" / "spectral_conformance" / "probe_core.py"
UPSTREAM_URL = "https://github.com/andreavolpato/spektrafilm.git"
DEFAULT_UPSTREAM_REF = "28bf883e1672e884307edc75852549376e13644e"
STRICT_ATOL = 1e-12
STRICT_RTOL = 1e-12


def _run(cmd: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    subprocess.run(cmd, cwd=cwd, env=env, check=True)


def _probe(repo_root: Path, output: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    env["PYTHONNOUSERSITE"] = "1"
    _run(
        [sys.executable, str(PROBE), "--output", str(output)],
        cwd=repo_root,
        env=env,
    )


def _checkout_upstream(target: Path, ref: str) -> None:
    _run(["git", "init", "-q", str(target)], cwd=target.parent)
    _run(["git", "remote", "add", "origin", UPSTREAM_URL], cwd=target)
    _run(["git", "fetch", "--depth=1", "origin", ref], cwd=target)
    _run(["git", "checkout", "--detach", "FETCH_HEAD"], cwd=target)


def _metrics(reference: np.ndarray, candidate: np.ndarray) -> dict[str, float | int | bool]:
    if reference.shape != candidate.shape:
        return {
            "shape_match": False,
            "reference_size": int(reference.size),
            "candidate_size": int(candidate.size),
            "max_abs": float("inf"),
            "max_rel": float("inf"),
            "exact": False,
        }
    delta = np.abs(candidate - reference)
    denom = np.maximum(np.abs(reference), 1e-12)
    return {
        "shape_match": True,
        "reference_size": int(reference.size),
        "candidate_size": int(candidate.size),
        "max_abs": float(np.max(delta)) if delta.size else 0.0,
        "max_rel": float(np.max(delta / denom)) if delta.size else 0.0,
        "exact": bool(np.array_equal(reference, candidate)),
    }


def _strict_pass(metrics: dict[str, float | int | bool]) -> bool:
    return bool(
        metrics["shape_match"]
        and float(metrics["max_abs"]) <= STRICT_ATOL
        and float(metrics["max_rel"]) <= STRICT_RTOL
    )


def _jsonable(value):
    if isinstance(value, float) and not np.isfinite(value):
        return "inf" if value > 0 else "-inf"
    return value


def _mallett_report(local, upstream) -> dict[str, dict]:
    report: dict[str, dict] = {}
    rgb = local["fixture__rgb"].reshape(-1, 3)
    in_cube = np.all((rgb >= 0.0) & (rgb <= 1.0), axis=1)

    for key in sorted(upstream.files):
        if not key.startswith("mallett_lut__") or key.endswith("__tc_lut"):
            continue
        suffix = key.removeprefix("mallett_lut__")
        direct_key = "mallett_direct__" + suffix
        if direct_key not in local.files:
            continue
        lut_raw = upstream[key].reshape(-1, 3)
        direct_raw = local[direct_key].reshape(-1, 3)
        all_metrics = _metrics(direct_raw, lut_raw)
        cube_metrics = _metrics(direct_raw[in_cube], lut_raw[in_cube])
        report[suffix] = {
            "all_fixture": all_metrics,
            "input_rgb_cube_only": cube_metrics,
            "input_rgb_cube_samples": int(np.count_nonzero(in_cube)),
            "stress_samples": int(np.count_nonzero(~in_cube)),
        }
    return report


def run_diff(*, upstream_ref: str, output_dir: Path, keep_checkout: bool = False) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    local_path = output_dir / "local.npz"
    upstream_path = output_dir / "upstream.npz"

    temp_root = Path(tempfile.mkdtemp(prefix="spektrafilm-spectral-upstream-"))
    upstream_checkout = temp_root / "upstream"
    try:
        _checkout_upstream(upstream_checkout, upstream_ref)
        _probe(ROOT, local_path)
        _probe(upstream_checkout, upstream_path)

        local = np.load(local_path)
        upstream = np.load(upstream_path)
        common_keys = sorted(set(local.files) & set(upstream.files))
        comparisons: dict[str, dict] = {}
        failures: list[str] = []
        exact_count = 0
        for key in common_keys:
            metrics = _metrics(upstream[key], local[key])
            passed = _strict_pass(metrics)
            comparisons[key] = {"status": "ok" if passed else "failed", **metrics}
            if bool(metrics["exact"]):
                exact_count += 1
            if not passed:
                failures.append(key)

        report = {
            "schema": "spektrafilm.spectral_upstream_diff.v1",
            "status": "failed" if failures else "ok",
            "upstream_url": UPSTREAM_URL,
            "upstream_ref": upstream_ref,
            "strict_atol": STRICT_ATOL,
            "strict_rtol": STRICT_RTOL,
            "common_arrays": len(common_keys),
            "exact_arrays": exact_count,
            "failed_arrays": failures,
            "comparisons": comparisons,
            "mallett_direct_vs_upstream_lut": _mallett_report(local, upstream),
        }
        (output_dir / "report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True, default=_jsonable),
            encoding="utf-8",
        )
        (output_dir / "report.md").write_text(_format_markdown(report), encoding="utf-8")
        if failures:
            raise SystemExit(1)
        return report
    finally:
        if keep_checkout:
            kept = output_dir / "upstream-checkout"
            if kept.exists():
                shutil.rmtree(kept)
            shutil.move(str(upstream_checkout), kept)
        shutil.rmtree(temp_root, ignore_errors=True)


def _format_markdown(report: dict) -> str:
    lines = [
        "# Spectral upstream differential conformance",
        "",
        f"- status: **{report['status']}**",
        f"- upstream ref: `{report['upstream_ref']}`",
        f"- common arrays: {report['common_arrays']}",
        f"- exact arrays: {report['exact_arrays']}",
        f"- strict tolerance: atol={report['strict_atol']}, rtol={report['strict_rtol']}",
        "",
        "## Non-exact / failed common arrays",
        "",
    ]
    nonexact = [
        (key, value)
        for key, value in report["comparisons"].items()
        if not value["exact"]
    ]
    if not nonexact:
        lines.append("All common arrays are bit-identical.")
    else:
        lines.append("| key | status | max abs | max rel |")
        lines.append("|---|---:|---:|---:|")
        for key, value in nonexact:
            lines.append(
                f"| `{key}` | {value['status']} | {value['max_abs']:.6g} | {value['max_rel']:.6g} |"
            )

    lines += ["", "## Mallett: local direct path vs upstream reflectance LUT", ""]
    mallett = report["mallett_direct_vs_upstream_lut"]
    if not mallett:
        lines.append("Upstream probe did not expose a Mallett reflectance LUT.")
    else:
        lines.append("| case | cube max abs | cube max rel | all max abs | all max rel |")
        lines.append("|---|---:|---:|---:|---:|")
        for case, value in sorted(mallett.items()):
            cube = value["input_rgb_cube_only"]
            all_ = value["all_fixture"]
            lines.append(
                f"| `{case}` | {cube['max_abs']:.6g} | {cube['max_rel']:.6g} | "
                f"{all_['max_abs']:.6g} | {all_['max_rel']:.6g} |"
            )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream-ref", default=DEFAULT_UPSTREAM_REF)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts" / "spectral_upstream_diff",
    )
    parser.add_argument("--keep-checkout", action="store_true")
    args = parser.parse_args()
    run_diff(
        upstream_ref=args.upstream_ref,
        output_dir=args.output_dir,
        keep_checkout=args.keep_checkout,
    )


if __name__ == "__main__":
    main()
