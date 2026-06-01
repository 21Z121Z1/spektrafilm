#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Sequence


PIPELINE = Path("src/spektrafilm/runtime/pipeline.py")
GRAIN = Path("src/spektrafilm/model/grain.py")
ANDROID_JNI = Path("android/app/src/main/cpp/spektrafilm_android_jni.cpp")


def _read(repo: Path, relative: Path) -> str:
    path = repo / relative
    try:
        return path.read_text()
    except FileNotFoundError:
        return ""


def _missing(text: str, needles: Iterable[str]) -> List[str]:
    return [needle for needle in needles if needle not in text]


def check_pipeline_backend_key(repo: Path) -> List[str]:
    text = _read(repo, PIPELINE)
    missing = _missing(
        text,
        (
            "def _backend_cache_key",
            "previous_lut_backend",
            "_backend_cache_key(previous_lut_backend) != _backend_cache_key(self._backend)",
        ),
    )
    if missing:
        return ["pipeline backend cache key guard missing: " + ", ".join(missing)]
    return []


def check_grain_local_rng(repo: Path) -> List[str]:
    text = _read(repo, GRAIN)
    failures: List[str] = []
    missing = _missing(
        text,
        (
            "uses_global_rng = seed is not None and method == 'poisson_binomial' and use_fast_stats",
            "np.random.RandomState(seed)",
            "random_state",
        ),
    )
    if missing:
        failures.append("grain local RNG guard missing: " + ", ".join(missing))

    seed_call = text.find("np.random.seed(seed)")
    if seed_call != -1 and text.rfind("if uses_global_rng:", 0, seed_call) == -1:
        failures.append("grain global seed call is not guarded by uses_global_rng")
    return failures


def check_android_jni_guards(repo: Path) -> List[str]:
    text = _read(repo, ANDROID_JNI)
    groups = (
        (
            "Android JNI short JSON guards missing",
            (
                "if (json == nullptr || key == nullptr) return def;",
                "if (klen == 0 || len < klen) return def;",
                "for (size_t i = 0; i + klen <= len; i++)",
                "char token[64];",
            ),
        ),
        (
            "Android JNI profile offset guard missing",
            (
                "offset < 16",
                "static_cast<size_t>(offset) > total_len",
            ),
        ),
        (
            "Android JNI params JSON guard missing",
            (
                "if (paramsJson == nullptr) return kInvalidCount;",
                "if (json_bytes == nullptr) return kNullBuffer;",
            ),
        ),
    )

    failures: List[str] = []
    for label, needles in groups:
        missing = _missing(text, needles)
        if missing:
            failures.append(label + ": " + ", ".join(missing))
    return failures


def _run(command: Sequence[str], cwd: Path, timeout_seconds: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        list(command),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )


def run_python_loader_probe(repo: Path, timeout_seconds: int) -> List[str]:
    python = repo / ".venv" / "bin" / "python"
    if not python.exists():
        print("PYTHON_LOADER_SKIPPED: .venv/bin/python not found")
        return []

    command = [str(python), "-S", "-c", "import _opcode; print('opcode import ok')"]
    try:
        result = _run(command, repo, timeout_seconds)
    except subprocess.TimeoutExpired:
        return [
            "PYTHON_LOADER_BLOCKED: command timed out after "
            + str(timeout_seconds)
            + "s: "
            + " ".join(command)
        ]

    if result.returncode != 0:
        return [
            "PYTHON_LOADER_FAILED: "
            + " ".join(command)
            + "\nstdout:\n"
            + result.stdout
            + "\nstderr:\n"
            + result.stderr
        ]
    print("PYTHON_LOADER_OK: " + result.stdout.strip())
    return []


def _candidate_ndk_clang() -> List[Path]:
    candidates: List[Path] = []
    for root in (
        os.environ.get("ANDROID_NDK_HOME"),
        os.environ.get("ANDROID_NDK_ROOT"),
        str(Path.home() / "Library/Android/sdk/ndk/28.2.13676358"),
    ):
        if not root:
            continue
        candidates.append(
            Path(root)
            / "toolchains"
            / "llvm"
            / "prebuilt"
            / "darwin-x86_64"
            / "bin"
            / "clang++"
        )
        candidates.append(
            Path(root)
            / "toolchains"
            / "llvm"
            / "prebuilt"
            / "darwin-arm64"
            / "bin"
            / "clang++"
        )
    return candidates


def _jdk_include_args() -> Optional[List[str]]:
    jdk_home = Path("/Library/Java/JavaVirtualMachines/jdk-21.jdk/Contents/Home")
    include = jdk_home / "include"
    darwin = include / "darwin"
    if include.exists() and darwin.exists():
        return ["-I" + str(include), "-I" + str(darwin)]
    return None


def run_android_syntax_check(repo: Path, timeout_seconds: int) -> List[str]:
    clang = next((path for path in _candidate_ndk_clang() if path.exists()), None)
    if clang is None:
        print("ANDROID_CLANG_SKIPPED: NDK clang++ not found")
        return []

    jdk_args = _jdk_include_args()
    if jdk_args is None:
        print("ANDROID_CLANG_SKIPPED: JDK 21 JNI headers not found")
        return []

    command = [
        str(clang),
        "--target=aarch64-linux-android35",
        "-std=c++17",
        "-fsyntax-only",
        "-DSPEKTRAFILM_HAS_HALIDE_AOT",
        "-Iandroid/app/src/main/cpp",
    ]
    command.extend(jdk_args)
    command.append(str(ANDROID_JNI))

    try:
        result = _run(command, repo, timeout_seconds)
    except subprocess.TimeoutExpired:
        return [
            "ANDROID_CLANG_BLOCKED: command timed out after "
            + str(timeout_seconds)
            + "s: "
            + " ".join(command)
        ]

    if result.returncode != 0:
        return [
            "ANDROID_CLANG_FAILED: "
            + " ".join(command)
            + "\nstdout:\n"
            + result.stdout
            + "\nstderr:\n"
            + result.stderr
        ]
    print("ANDROID_CLANG_OK: AOT JNI syntax check passed")
    return []


def run_source_checks(repo: Path) -> List[str]:
    failures: List[str] = []
    checks = (
        ("PIPELINE_SOURCE", check_pipeline_backend_key),
        ("GRAIN_SOURCE", check_grain_local_rng),
        ("ANDROID_JNI_SOURCE", check_android_jni_guards),
    )
    for label, check in checks:
        check_failures = check(repo)
        if check_failures:
            failures.extend(check_failures)
        else:
            print(label + "_OK")
    return failures


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify the 2026-05-31 Codex adversarial-review fixes with bounded stdlib checks.",
    )
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--skip-python-probe", action="store_true")
    parser.add_argument("--python-timeout", type=int, default=15)
    parser.add_argument("--skip-android-syntax", action="store_true")
    parser.add_argument("--android-timeout", type=int, default=30)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    repo = args.repo.resolve()

    failures = run_source_checks(repo)
    if not args.skip_python_probe:
        failures.extend(run_python_loader_probe(repo, args.python_timeout))
    if not args.skip_android_syntax:
        failures.extend(run_android_syntax_check(repo, args.android_timeout))

    if failures:
        print("VERIFY_FAILED")
        for failure in failures:
            print("- " + failure)
        return 1

    print("VERIFY_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
