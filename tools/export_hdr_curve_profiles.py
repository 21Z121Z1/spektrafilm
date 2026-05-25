from __future__ import annotations

import argparse
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from spektrafilm.model.stocks import FilmStocks, PrintPapers
from spektrafilm.utils.hdr_curve_profiles import (
    DEFAULT_CURVE_PROFILE_DIR,
    sample_runtime_curve_profile,
    write_curve_profile_database,
)


def _split_csv(value: str | None, default: list[str]) -> list[str]:
    if value is None or not value.strip():
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Spektrafilm HDR curve-profile v2 data.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_CURVE_PROFILE_DIR)
    parser.add_argument("--films", help="Comma-separated film profile ids. Defaults to all FilmStocks.")
    parser.add_argument("--papers", help="Comma-separated paper profile ids. Defaults to all PrintPapers.")
    parser.add_argument("--ev-min", type=float, default=-10.0)
    parser.add_argument("--ev-max", type=float, default=6.0)
    parser.add_argument("--ev-step", type=float, default=0.5)
    args = parser.parse_args()

    films = _split_csv(args.films, [film.value for film in FilmStocks])
    papers = _split_csv(args.papers, [paper.value for paper in PrintPapers])

    samples = []
    failures: list[str] = []
    for film in films:
        for paper in papers:
            try:
                sample = sample_runtime_curve_profile(
                    film=film,
                    paper=paper,
                    ev_min=args.ev_min,
                    ev_max=args.ev_max,
                    ev_step=args.ev_step,
                )
                samples.append(sample)
                status = "safe" if sample["metrics"]["safe_for_profile_aware_hdr"] else "fallback"
                print(f"{film} on {paper}: {sample['metrics']['polarity']} ({status})")
            except Exception as exc:  # pragma: no cover - developer tool diagnostics
                message = f"{film} on {paper}: {exc}"
                failures.append(message)
                print(f"FAILED {message}", file=sys.stderr)

    summary_path = write_curve_profile_database(samples, args.output_dir)
    readme_path = args.output_dir / "README.md"
    readme_path.write_text(
        "# HDR Curve Profiles v2\n\n"
        "This directory contains machine-readable sampled Spektrafilm film/paper tone curves for "
        "profile-aware HDR photo export.\n\n"
        "The samples are generated from the deterministic Spektrafilm runtime with stochastic and "
        "spatial effects disabled. Each profile uses a neutral scene-linear RGB ramp where "
        "`scene_y=1.0` is diffuse white. Luminance is computed with Rec. 709/sRGB linear luma "
        "coefficients `(0.2126, 0.7152, 0.0722)` and max/min channel values are also recorded for "
        "headroom and tint diagnostics.\n\n"
        "Regenerate with:\n\n"
        "```bash\n"
        "uv run python tools/export_hdr_curve_profiles.py\n"
        "```\n\n"
        "Profiles whose sampled luminance curve is decreasing or nonmonotonic are marked unsafe "
        "for the increasing profile-aware HDR mapping path and must fall back to generic mapping.\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(samples)} profiles to {summary_path}")
    if failures:
        print(f"{len(failures)} profile combinations failed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
