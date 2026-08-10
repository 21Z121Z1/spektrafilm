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

from spektrafilm.utils.spectral_lut_registry import spectral_lut_descriptor
from spektrafilm.utils.spectral_upsampling import _illuminant_to_xy


ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "tools" / "spectral_conformance" / "probe_core.py"
UPSTREAM_URL = "https://github.com/andreavolpato/spektrafilm.git"
DEFAULT_UPSTREAM_REF = "28bf883e1672e884307edc75852549376e13644e"
STRICT_ATOL = 1e-12
STRICT_RTOL = 1e-12
REFLECTANCE_METHODS = {
    "arctic2026beta04",
    "jakob2019",
    "otsu2018",
    "gauss-lasers",
}


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


def _expected_upstream_scale(key: str) -> float:
    """Return the one deliberate delta from current upstream experimental.

    Upstream's 2026-07-02 B&W normalization refactor kept the per-channel
    neutral/chroma correction but dropped the descriptor midgray exposure
    anchor. For generic reflectance arrays our corrected implementation must
    therefore equal current upstream multiplied by y_scene / midgray. Fixture
    arrays and every non-reflectance array remain exact 1:1 comparisons.
    """
    method = key.split("__", 1)[0]
    if method not in REFLECTANCE_METHODS:
        return 1.0
    descriptor = spectral_lut_descriptor(method)
    reflectance = descriptor["reflectance"]
    scene_xy = _illuminant_to_xy(reflectance["scene_illuminant"])
    return float(scene_xy[1]) / float(reflectance["midgray"])


def _jsonable(value):
    if isinstance(value, float) and not np.isfinite(value):
        return "inf" if value > 0 else "-inf"
    return value


def _mallett_pair_report(reference, candidate, rgb: np.ndarray) -> dict[str, dict]:
    report: dict[str, dict] = {}
    in_cube = np.all((rgb >= 0.0) & (rgb <= 1.0), axis=1)
    for suffix in sorted(set(reference) & set(candidate)):
        ref_raw = reference[suffix].reshape(-1, 3)
        cand_raw = candidate[suffix].reshape(-1, 3)
        report[suffix] = {
            "all_fixture": _metrics(ref_raw, cand_raw),
            "input_rgb_cube_only": _metrics(ref_raw[in_cube], cand_raw[in_cube]),
            "input_rgb_cube_samples": int(np.count_nonzero(in_cube)),
            "stress_samples": int(np.count_nonzero(~in_cube)),
        }
    return report


def _mallett_reports(local, upstream) -> dict[str, dict]:
    rgb = local["fixture__rgb"].reshape(-1, 3)
    local_direct = {
        key.removeprefix("mallett_direct__"): local[key]
        for key in local.files
        if key.startswith("mallett_direct__")
    }
    upstream_direct = {
        key.removeprefix("mallett_direct__"): upstream[key]
        for key in upstream.files
        if key.startswith("mallett_direct__")
    }
    upstream_lut = {
        key.removeprefix("mallett_lut__"): upstream[key]
        for key in upstream.files
        if key.startswith("mallett_lut__") and not key.endswith("__tc_lut")
    }
    return {
        "local_direct_vs_upstream_direct": _mallett_pair_report(
            upstream_direct, local_direct, rgb
        ),
        "upstream_direct_vs_upstream_lut": _mallett_pair_report(
            upstream_direct, upstream_lut, rgb
        ),
        "local_direct_vs_upstream_lut": _mallett_pair_report(
            upstream_lut, local_direct, rgb
        ),
    }


def run_diff(*, upstream_ref: str, output_dir: Path, keep_checkout: bool = False) -> dict:
    output_dir = output_dir.resolve()
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
        # Mallett is intentionally reported separately because the user fork
        # retained its pre-registry direct/GPU path. The strict gate covers the
        # four generic reflectance methods that were actually ported, with only
        # the analytically defined midgray exposure-anchor correction allowed.
        core_keys = [key for key in common_keys if not key.startswith("mallett_direct__")]
        comparisons: dict[str, dict] = {}
        failures: list[str] = []
        exact_expected_count = 0
        for key in core_keys:
            expected_scale = _expected_upstream_scale(key)
            expected = upstream[key] * expected_scale
            metrics = _metrics(expected, local[key])
            passed = _strict_pass(metrics)
            comparisons[key] = {
                "status": "ok" if passed else "failed",
                "expected_upstream_scale": expected_scale,
                **metrics,
            }
            if bool(metrics["exact"]):
                exact_expected_count += 1
            if not passed:
                failures.append(key)

        report = {
            "schema": "spektrafilm.spectral_upstream_diff.v3",
            "status": "failed" if failures else "ok",
            "upstream_url": UPSTREAM_URL,
            "upstream_ref": upstream_ref,
            "strict_atol": STRICT_ATOL,
            "strict_rtol": STRICT_RTOL,
            "common_arrays": len(common_keys),
            "core_arrays": len(core_keys),
            "exact_expected_core_arrays": exact_expected_count,
            "failed_core_arrays": failures,
            "deliberate_delta": "reflectance arrays = upstream * (scene_y / descriptor_midgray)",
            "comparisons": comparisons,
            "mallett": _mallett_reports(local, upstream),
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


def _format_mallett_table(lines: list[str], title: str, values: dict[str, dict]) -> None:
    lines += ["", f"### {title}", ""]
    if not values:
        lines.append("No comparable arrays were produced.")
        return
    lines.append("| case | cube max abs | cube max rel | all max abs | all max rel |")
    lines.append("|---|---:|---:|---:|---:|")
    for case, value in sorted(values.items()):
        cube = value["input_rgb_cube_only"]
        all_ = value["all_fixture"]
        lines.append(
            f"| `{case}` | {cube['max_abs']:.6g} | {cube['max_rel']:.6g} | "
            f"{all_['max_abs']:.6g} | {all_['max_rel']:.6g} |"
        )


def _format_markdown(report: dict) -> str:
    lines = [
        "# Spectral upstream differential conformance",
        "",
        f"- status: **{report['status']}**",
        f"- upstream ref: `{report['upstream_ref']}`",
        f"- strict core arrays: {report['core_arrays']}",
        f"- bit-identical to corrected expectation: {report['exact_expected_core_arrays']}",
        f"- strict tolerance: atol={report['strict_atol']}, rtol={report['strict_rtol']}",
        f"- deliberate delta: {report['deliberate_delta']}",
        "",
        "## Generic reflectance core",
        "",
    ]
    nonexact = [
        (key, value)
        for key, value in report["comparisons"].items()
        if not value["exact"]
    ]
    if not nonexact:
        lines.append(
            "All generic reflectance core arrays exactly match current upstream after applying "
            "only the analytically defined midgray exposure-anchor correction."
        )
    else:
        lines.append("| key | status | expected scale | max abs | max rel |")
        lines.append("|---|---:|---:|---:|---:|")
        for key, value in nonexact:
            lines.append(
                f"| `{key}` | {value['status']} | {value['expected_upstream_scale']:.9g} | "
                f"{value['max_abs']:.6g} | {value['max_rel']:.6g} |"
            )

    lines += ["", "## Mallett compatibility analysis"]
    _format_mallett_table(
        lines,
        "Local direct vs upstream direct",
        report["mallett"]["local_direct_vs_upstream_direct"],
    )
    _format_mallett_table(
        lines,
        "Upstream direct vs upstream reflectance LUT",
        report["mallett"]["upstream_direct_vs_upstream_lut"],
    )
    _format_mallett_table(
        lines,
        "Local direct vs upstream reflectance LUT",
        report["mallett"]["local_direct_vs_upstream_lut"],
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
