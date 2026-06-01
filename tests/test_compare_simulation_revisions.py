from __future__ import annotations

import json

import pytest

from scripts import compare_simulation_revisions as csr


pytestmark = pytest.mark.unit


def test_evaluate_revision_ends_git_options_before_revision(monkeypatch) -> None:
    commands: list[list[str]] = []

    class Completed:
        stdout = ""

    def fake_run(command, **_kwargs):
        commands.append(command)
        return Completed()

    monkeypatch.setattr(csr.subprocess, "run", fake_run)
    monkeypatch.setattr(csr, "_run_subprocess", lambda *_args, **_kwargs: json.dumps({}))

    csr._evaluate_revision(
        "--upload-pack=malicious",
        film_profile="kodak_portra_400",
        print_profile="kodak_portra_endura",
        positive_film_profile="fujifilm_provia_100f",
    )

    add_command = commands[0]
    assert add_command[:4] == ["git", "worktree", "add", "--detach"]
    separator_index = add_command.index("--")
    assert separator_index < len(add_command) - 1
    assert add_command[separator_index + 1] == "--upload-pack=malicious"
