from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_SOURCE = REPO_ROOT / "scripts" / "check-upstream-parity.sh"

CORE_FILES = (
    "src/spektrafilm/runtime/pipeline.py",
    "src/spektrafilm/runtime/process.py",
    "src/spektrafilm/runtime/params_builder.py",
    "src/spektrafilm/runtime/params_schema.py",
    "src/spektrafilm/runtime/stages/filming.py",
    "src/spektrafilm/runtime/stages/printing.py",
    "src/spektrafilm/runtime/stages/scanning.py",
    "src/spektrafilm/runtime/services/spectral_lut_compute.py",
    "src/spektrafilm/model/emulsion.py",
    "src/spektrafilm/model/density_curves.py",
    "src/spektrafilm/model/couplers.py",
    "src/spektrafilm/model/color_filters.py",
    "src/spektrafilm/profiles/io.py",
    "src/spektrafilm/profiles/__init__.py",
    "src/spektrafilm/config.py",
)


def _run(cmd: list[str], cwd: Path, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = _run(["git", *args], repo)
    assert result.returncode == 0, result.stdout
    return result


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _init_upstream_repo(path: Path, *, include_all_core_files: bool = True) -> None:
    path.mkdir(parents=True)
    init = _run(["git", "init"], path)
    assert init.returncode == 0, init.stdout
    _git(path, "checkout", "-B", "main")
    _git(path, "config", "user.email", "test@example.invalid")
    _git(path, "config", "user.name", "Parity Test")

    for core_file in CORE_FILES if include_all_core_files else CORE_FILES[1:]:
        _write(path / core_file, "# upstream core\n")

    _write(
        path / "src/spektrafilm/data/profiles/example.json",
        '{"stock": "upstream"}\n',
    )
    _git(path, "add", ".")
    _git(path, "commit", "-m", "initial upstream")


def _clone_with_script(tmp_path: Path, upstream: Path) -> Path:
    work = tmp_path / "work"
    clone = _run(["git", "clone", str(upstream), str(work)], tmp_path)
    assert clone.returncode == 0, clone.stdout
    scripts_dir = work / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SCRIPT_SOURCE, scripts_dir / "check-upstream-parity.sh")
    return work


def _script_env() -> dict[str, str]:
    env = os.environ.copy()
    env["UPSTREAM_REMOTE"] = "origin"
    env["UPSTREAM_BRANCH"] = "main"
    return env


def test_parity_script_checks_shared_data_under_src_spektrafilm_data(tmp_path: Path) -> None:
    upstream = tmp_path / "upstream"
    _init_upstream_repo(upstream)
    work = _clone_with_script(tmp_path, upstream)

    shared_data = work / "src/spektrafilm/data/profiles/example.json"
    shared_data.write_text('{"stock": "local-drift"}\n', encoding="utf-8")

    result = _run(["bash", "scripts/check-upstream-parity.sh"], work, env=_script_env())

    assert result.returncode != 0, result.stdout
    assert "src/spektrafilm/data/profiles/example.json" in result.stdout
    assert "local" in result.stdout and "upstream" in result.stdout


def test_parity_script_fails_missing_declared_core_path(tmp_path: Path) -> None:
    upstream = tmp_path / "upstream"
    _init_upstream_repo(upstream, include_all_core_files=False)
    work = _clone_with_script(tmp_path, upstream)

    result = _run(["bash", "scripts/check-upstream-parity.sh"], work, env=_script_env())

    assert result.returncode != 0, result.stdout
    assert CORE_FILES[0] in result.stdout
    assert "missing" in result.stdout.lower() or "not present" in result.stdout.lower()
