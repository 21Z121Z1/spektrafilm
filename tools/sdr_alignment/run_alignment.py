from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from tools.sdr_alignment.candidate_runner import run_candidate_subprocess
from tools.sdr_alignment.fixtures import ALL_TAPS, iter_cases, skipped_taps
from tools.sdr_alignment.metrics import (
    compare_arrays,
    failed_metrics,
    thresholds_for_backend,
)
from tools.sdr_alignment.params_adapter import build_param_spec
from tools.sdr_alignment.reference_runner import run_reference_subprocess


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOCK = ROOT / "tests" / "alignment" / "upstream_lock.json"
DEFAULT_ALLOWLIST = ROOT / "tests" / "alignment" / "allowlist.yml"
DEFAULT_OUTPUT_ROOT = ROOT / "artifacts" / "sdr_alignment"


def run_alignment(
    *,
    mode: str,
    suite: str,
    backend: str,
    output_dir: Path | None = None,
    lock_path: Path = DEFAULT_LOCK,
    allowlist_path: Path = DEFAULT_ALLOWLIST,
    repo_root: Path = ROOT,
    report_only: bool = False,
) -> dict[str, Any]:
    if output_dir is None:
        stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
        output_dir = DEFAULT_OUTPUT_ROOT / f"{mode}-{suite}-{backend}-{stamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    allowlist = load_allowlist(allowlist_path)
    cases = list(iter_cases(suite))
    case_reports = []
    failed = False

    for case in cases:
        case_dir = output_dir / case.fixture_id
        case_dir.mkdir(parents=True, exist_ok=True)
        fixture_path = case_dir / "fixture.npz"
        np.savez_compressed(fixture_path, image=case.image)
        spec = build_param_spec(mode=mode, case=case.to_spec(), backend=backend)
        spec_path = case_dir / "spec.json"
        spec_path.write_text(json.dumps(spec, indent=2, sort_keys=True), encoding="utf-8")

        reference_path = case_dir / "reference.npz"
        candidate_path = case_dir / f"candidate-{backend}.npz"
        run_reference_subprocess(
            repo_root=repo_root,
            lock_path=lock_path,
            spec_path=spec_path,
            fixture_path=fixture_path,
            output_path=reference_path,
        )
        run_candidate_subprocess(
            repo_root=repo_root,
            spec_path=spec_path,
            fixture_path=fixture_path,
            output_path=candidate_path,
        )

        case_report = _compare_case(
            mode=mode,
            backend=backend,
            case=case.to_spec(),
            reference_path=reference_path,
            candidate_path=candidate_path,
            allowlist=allowlist,
        )
        case_reports.append(case_report)
        failed = failed or case_report["status"] == "failed"

    report = {
        "schema": "spektrafilm.sdr_upstream_conformance.report.v1",
        "status": "failed" if failed else "ok",
        "mode": mode,
        "suite": suite,
        "backend": backend,
        "lock": lock,
        "output_dir": str(output_dir),
        "cases": case_reports,
    }
    (output_dir / "report.json").write_text(
        json.dumps(_jsonable(report), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (output_dir / "report.md").write_text(_format_markdown(report), encoding="utf-8")

    if failed and not report_only:
        raise SystemExit(1)
    return report


def load_allowlist(path: Path) -> list[dict[str, Any]]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    differences = payload.get("differences", [])
    if differences is None:
        return []
    if not isinstance(differences, list):
        raise ValueError("allowlist.yml must contain a 'differences' list")
    return differences


def _compare_case(
    *,
    mode: str,
    backend: str,
    case: dict[str, Any],
    reference_path: Path,
    candidate_path: Path,
    allowlist: list[dict[str, Any]],
) -> dict[str, Any]:
    reference = np.load(reference_path)
    candidate = np.load(candidate_path)
    uses_lut = bool(
        case.get("mode") == "product_sdr"
    )  # Backward-compatible placeholder; spec below is authoritative.
    skipped = set(skipped_taps(case))
    taps: dict[str, Any] = {}
    failed = False

    spec = json.loads((reference_path.parent / "spec.json").read_text(encoding="utf-8"))
    settings = spec["common_overrides"].get("settings", {})
    uses_lut = bool(settings.get("use_enlarger_lut") or settings.get("use_scanner_lut"))
    thresholds = thresholds_for_backend(backend, mode=mode, uses_lut=uses_lut)

    for tap in ALL_TAPS:
        if tap in skipped:
            taps[tap] = {"status": "skipped", "reason": "scan_film_route"}
            continue
        metrics = compare_arrays(reference[tap], candidate[tap], final_sdr=(tap == "rgb_out"))
        failures = failed_metrics(metrics, thresholds, final_sdr=(tap == "rgb_out"))
        allowed, unallowed = _apply_allowlist(
            mode=mode,
            fixture=str(case["fixture_id"]),
            tap=tap,
            metrics=metrics,
            failures=failures,
            allowlist=allowlist,
        )
        status = "failed" if unallowed else "ok"
        failed = failed or bool(unallowed)
        taps[tap] = {
            "status": status,
            "metrics": metrics,
            "failed_metrics": unallowed,
            "allowed_differences": allowed,
        }

    return {
        "fixture": case,
        "status": "failed" if failed else "ok",
        "skipped_taps": sorted(skipped),
        "taps": taps,
    }


def _apply_allowlist(
    *,
    mode: str,
    fixture: str,
    tap: str,
    metrics: dict[str, Any],
    failures: dict[str, float],
    allowlist: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, float]]]:
    allowed: list[dict[str, Any]] = []
    unallowed: dict[str, dict[str, float]] = {}
    for metric, default_threshold in failures.items():
        actual = _metric_value(metrics, metric)
        entry = _matching_allowlist_entry(
            allowlist=allowlist,
            mode=mode,
            fixture=fixture,
            tap=tap,
            metric=metric,
        )
        if entry is not None and actual <= float(entry["threshold"]):
            allowed.append(
                {
                    "metric": metric,
                    "actual": actual,
                    "default_threshold": default_threshold,
                    "allowlist_threshold": float(entry["threshold"]),
                    "reason": str(entry["reason"]),
                    "owner": str(entry["owner"]),
                    "review_by": str(entry["review_by"]),
                }
            )
        else:
            unallowed[metric] = {
                "actual": actual,
                "threshold": default_threshold,
            }
    return allowed, unallowed


def _matching_allowlist_entry(
    *,
    allowlist: list[dict[str, Any]],
    mode: str,
    fixture: str,
    tap: str,
    metric: str,
) -> dict[str, Any] | None:
    for entry in allowlist:
        if (
            entry.get("mode") == mode
            and entry.get("fixture") == fixture
            and entry.get("tap") == tap
            and entry.get("metric") == metric
        ):
            return entry
    return None


def _metric_value(metrics: dict[str, Any], metric: str) -> float:
    if metric == "shape_match":
        return 1.0 if metrics.get("shape_match") else 0.0
    if metric == "finite":
        return 1.0 if metrics.get("finite") else 0.0
    value = metrics.get(metric)
    if value is None:
        return float("inf")
    return float(value)


def _format_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# SDR Upstream Conformance Report",
        "",
        f"- Status: `{report['status']}`",
        f"- Mode: `{report['mode']}`",
        f"- Suite: `{report['suite']}`",
        f"- Backend: `{report['backend']}`",
        f"- Upstream: `{report['lock']['upstream']['repo']}@{report['lock']['upstream']['ref']}`",
        "",
        "| Fixture | Tap | Status | max_abs | p99_abs | rmse | Notes |",
        "| --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for case in report["cases"]:
        fixture_id = case["fixture"]["fixture_id"]
        for tap, tap_report in case["taps"].items():
            if tap_report["status"] == "skipped":
                lines.append(
                    f"| `{fixture_id}` | `{tap}` | skipped |  |  |  | {tap_report['reason']} |"
                )
                continue
            metrics = tap_report["metrics"]
            notes = []
            if tap_report["failed_metrics"]:
                notes.append(f"failed: {', '.join(tap_report['failed_metrics'])}")
            if tap_report["allowed_differences"]:
                notes.append(f"allowed: {len(tap_report['allowed_differences'])}")
            lines.append(
                "| "
                f"`{fixture_id}` | `{tap}` | `{tap_report['status']}` | "
                f"{_fmt(metrics.get('max_abs'))} | {_fmt(metrics.get('p99_abs'))} | "
                f"{_fmt(metrics.get('rmse'))} | {'; '.join(notes)} |"
            )
    lines.append("")
    return "\n".join(lines)


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    return f"{float(value):.3e}"


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run SDR upstream conformance alignment.")
    parser.add_argument("--mode", choices=("upstream_compat", "product_sdr"), default="upstream_compat")
    parser.add_argument("--suite", choices=("quick", "full"), default="quick")
    parser.add_argument("--backend", choices=("cpu", "mlx", "cupy", "cuda", "halide"), default="cpu")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST)
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args(argv)

    run_alignment(
        mode=args.mode,
        suite=args.suite,
        backend=args.backend,
        output_dir=args.output_dir,
        lock_path=args.lock,
        allowlist_path=args.allowlist,
        report_only=args.report_only,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

