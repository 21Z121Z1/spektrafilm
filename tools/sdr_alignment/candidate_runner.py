from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np

from tools.sdr_alignment.fixtures import expected_taps
from tools.sdr_alignment.params_adapter import build_runtime_params


def run_candidate_subprocess(
    *,
    repo_root: Path,
    spec_path: Path,
    fixture_path: Path,
    output_path: Path,
    python: Path | None = None,
) -> None:
    python = python or Path(sys.executable)
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(repo_root / "src"), str(repo_root), env.get("PYTHONPATH", "")]
    )
    subprocess.run(
        [
            str(python),
            "-m",
            "tools.sdr_alignment.candidate_runner",
            "worker",
            "--spec",
            str(spec_path),
            "--fixture",
            str(fixture_path),
            "--output",
            str(output_path),
        ],
        cwd=str(repo_root),
        env=env,
        check=True,
    )


def run_worker(*, spec_path: Path, fixture_path: Path, output_path: Path) -> None:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    image = np.load(fixture_path)["image"]

    params = build_runtime_params(spec, implementation="candidate")
    from spektrafilm.runtime.pipeline import SimulationPipeline

    arrays: dict[str, np.ndarray] = {}
    for tap in expected_taps(spec["fixture"]):
        pipeline = SimulationPipeline(params)
        value = pipeline.process(image, collect=tap)
        arrays[tap] = _to_numpy(pipeline, value)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output_path, **arrays)


def _to_numpy(pipeline: Any, value: Any) -> np.ndarray:
    backend = getattr(pipeline, "_array_backend", None) or getattr(pipeline, "_backend", None)
    if backend is not None and hasattr(backend, "to_numpy"):
        try:
            value = backend.to_numpy(value)
        except Exception:
            pass
    return np.asarray(value, dtype=np.float64)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run current checkout SDR alignment worker.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    worker = subparsers.add_parser("worker")
    worker.add_argument("--spec", type=Path, required=True)
    worker.add_argument("--fixture", type=Path, required=True)
    worker.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.command == "worker":
        run_worker(spec_path=args.spec, fixture_path=args.fixture, output_path=args.output)
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())

