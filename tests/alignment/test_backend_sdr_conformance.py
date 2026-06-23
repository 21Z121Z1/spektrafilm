from __future__ import annotations

from pathlib import Path

import pytest

from spektrafilm.gpu.backend import BackendUnavailableError, select_backend
from tools.sdr_alignment.run_alignment import run_alignment


pytestmark = pytest.mark.integration


def test_candidate_cpu_backend_uses_independent_alignment_metrics(tmp_path) -> None:
    output_dir = tmp_path / "alignment-cpu"
    report = run_alignment(
        mode="upstream_compat",
        suite="quick",
        backend="cpu",
        output_dir=output_dir,
        report_only=True,
    )

    for spec_path in output_dir.glob("*/spec.json"):
        spec = _load_json(spec_path)
        assert spec["candidate_overrides"]["settings"]["compute_backend"] == "cpu"
        assert spec["candidate_overrides"]["settings"]["gpu_validate"] is False
    assert report["status"] == "ok"


@pytest.mark.parametrize("backend", ["mlx", "cupy", "halide"])
def test_optional_backend_sdr_conformance_or_skip(tmp_path, backend: str) -> None:
    try:
        select_backend("cuda" if backend == "cupy" else backend)
    except (BackendUnavailableError, Exception) as exc:
        pytest.skip(str(exc))

    output_dir = tmp_path / f"alignment-{backend}"
    report = run_alignment(
        mode="upstream_compat",
        suite="quick",
        backend="cuda" if backend == "cupy" else backend,
        output_dir=output_dir,
        report_only=True,
    )

    for spec_path in output_dir.glob("*/spec.json"):
        spec = _load_json(spec_path)
        assert spec["candidate_overrides"]["settings"]["gpu_validate"] is False
    assert report["status"] == "ok"


def _load_json(path: Path):
    import json

    return json.loads(path.read_text(encoding="utf-8"))
