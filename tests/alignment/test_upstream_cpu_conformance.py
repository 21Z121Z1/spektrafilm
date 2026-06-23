from __future__ import annotations

import pytest

from tools.sdr_alignment.run_alignment import run_alignment


pytestmark = pytest.mark.integration


def test_quick_upstream_compat_cpu_conformance(tmp_path) -> None:
    report = run_alignment(
        mode="upstream_compat",
        suite="quick",
        backend="cpu",
        output_dir=tmp_path / "alignment",
        report_only=True,
    )

    positive_case = next(
        case for case in report["cases"] if case["fixture"]["fixture_id"] == "positive_scan_film_8"
    )
    assert positive_case["skipped_taps"] == ["cmy_print", "log_e_print"]
    assert positive_case["taps"]["log_e_print"]["status"] == "skipped"
    assert positive_case["taps"]["cmy_print"]["status"] == "skipped"
    assert report["status"] == "ok"
