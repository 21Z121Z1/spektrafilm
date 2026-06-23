from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path

import yaml

from tools.sdr_alignment.fixtures import ALL_TAPS


ROOT = Path(__file__).resolve().parents[2]
LOCK_PATH = ROOT / "tests" / "alignment" / "upstream_lock.json"
ALLOWLIST_PATH = ROOT / "tests" / "alignment" / "allowlist.yml"
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ALLOWLIST_KEYS = {"mode", "fixture", "tap", "metric", "threshold", "reason", "owner", "review_by"}


def test_upstream_lock_schema_and_local_hashes() -> None:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))

    assert lock["contract_version"] == 1
    assert lock["upstream"]["repo"] == "https://github.com/andreavolpato/spektrafilm"
    assert SHA_RE.match(lock["upstream"]["ref"])
    assert HASH_RE.match(lock["upstream"]["pyproject_sha256"])
    assert HASH_RE.match(lock["candidate"]["uv_lock_sha256"])
    assert lock["candidate"]["uv_lock_sha256"] == _sha256(ROOT / "uv.lock")
    assert lock["candidate"]["python"] == "~=3.13"
    assert lock["bootstrap"]["cache_dir"] == ".cache/sdr_alignment"


def test_allowlist_schema() -> None:
    payload = yaml.safe_load(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    assert set(payload) == {"differences"}
    assert isinstance(payload["differences"], list)

    today = dt.date.today()
    for item in payload["differences"]:
        assert set(item) == ALLOWLIST_KEYS
        assert item["mode"] in {"upstream_compat", "product_sdr"}
        assert item["tap"] in ALL_TAPS
        assert isinstance(item["threshold"], int | float)
        assert item["threshold"] >= 0.0
        assert str(item["reason"]).strip()
        assert str(item["owner"]).strip()
        review_by = dt.date.fromisoformat(str(item["review_by"]))
        assert review_by >= today


def test_tap_contract_contains_required_sdr_boundaries() -> None:
    assert ALL_TAPS == (
        "rgb_pre",
        "log_e_film",
        "cmy_film",
        "log_e_print",
        "cmy_print",
        "rgb_out",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

