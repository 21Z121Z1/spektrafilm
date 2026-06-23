from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import site
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np

from tools.sdr_alignment.fixtures import expected_taps
from tools.sdr_alignment.params_adapter import build_runtime_params


def run_reference_subprocess(
    *,
    repo_root: Path,
    lock_path: Path,
    spec_path: Path,
    fixture_path: Path,
    output_path: Path,
) -> None:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    cache_dir = repo_root / str(lock["bootstrap"]["cache_dir"])
    checkout = ensure_reference_checkout(lock=lock, cache_dir=cache_dir)
    python = ensure_reference_venv(lock=lock, cache_dir=cache_dir)

    env = os.environ.copy()
    dependency_paths = _current_dependency_paths()
    env["PYTHONPATH"] = os.pathsep.join(
        [
            str(checkout / "src"),
            str(repo_root),
            *dependency_paths,
            env.get("PYTHONPATH", ""),
        ]
    )
    subprocess.run(
        [
            str(python),
            "-m",
            "tools.sdr_alignment.reference_runner",
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


def ensure_reference_checkout(*, lock: dict[str, Any], cache_dir: Path) -> Path:
    upstream = lock["upstream"]
    ref = str(upstream["ref"])
    checkout = cache_dir / "upstream" / ref
    if not (checkout / ".git").exists():
        checkout.parent.mkdir(parents=True, exist_ok=True)
        if checkout.exists():
            shutil.rmtree(checkout)
        subprocess.run(["git", "clone", str(upstream["repo"]), str(checkout)], check=True)
    subprocess.run(["git", "-C", str(checkout), "fetch", "origin", ref, "--depth", "1"], check=True)
    subprocess.run(["git", "-C", str(checkout), "checkout", "--detach", ref], check=True)

    current = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
    if current != ref:
        raise RuntimeError(f"upstream checkout is {current}, expected {ref}")
    pyproject_hash = _sha256(checkout / "pyproject.toml")
    expected_hash = str(upstream["pyproject_sha256"])
    if pyproject_hash != expected_hash:
        raise RuntimeError(
            f"upstream pyproject hash mismatch: {pyproject_hash} != {expected_hash}"
        )
    return checkout


def ensure_reference_venv(*, lock: dict[str, Any], cache_dir: Path) -> Path:
    ref = str(lock["upstream"]["ref"])
    venv = cache_dir / "venvs" / ref
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.exists():
        venv.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    return python


def run_worker(*, spec_path: Path, fixture_path: Path, output_path: Path) -> None:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    image = np.load(fixture_path)["image"]

    params = build_runtime_params(spec, implementation="reference")
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


def _current_dependency_paths() -> list[str]:
    paths: list[str] = []
    for path in site.getsitepackages():
        if path and path not in paths:
            paths.append(path)
    user_site = site.getusersitepackages()
    if user_site and user_site not in paths:
        paths.append(user_site)
    return paths


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run locked upstream SDR alignment worker.")
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

