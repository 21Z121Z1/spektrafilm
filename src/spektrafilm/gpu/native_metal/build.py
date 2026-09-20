"""Explicit developer build; never called on import or by a render."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from . import ABI_VERSION, SOURCE_FILES, _sha256


def build(output: Path) -> Path:
    if sys.platform != "darwin":
        raise RuntimeError("the native Metal build requires macOS and Xcode")
    source = Path(__file__).parent.resolve()
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sfm-build-", dir=output.parent) as temporary:
        root = Path(temporary)
        commands = [
            ["xcrun", "--sdk", "macosx", "metal", "-std=metal3.0",
             "-mmacosx-version-min=15.0", "-fmetal-math-mode=safe",
             "-fmetal-math-fp32-functions=precise", "-ffp-contract=off",
             "-I", str(source), "-c", str(source / "spatial.metal"), "-o", str(root / "spatial.air")],
            ["xcrun", "--sdk", "macosx", "metallib", str(root / "spatial.air"),
             "-o", str(root / "sfm_spatial.metallib")],
            ["xcrun", "--sdk", "macosx", "clang++", "-std=c++17", "-O2", "-fobjc-arc",
             "-fno-fast-math", "-ffp-contract=off", "-mmacosx-version-min=15.0",
             "-Wall", "-Wextra", "-Werror", "-dynamiclib", str(source / "spatial.mm"),
             "-framework", "Foundation", "-framework", "Metal", "-o", str(root / "libsfm_spatial.dylib")],
        ]
        for command in commands:
            subprocess.run(command, check=True)
        manifest = {
            "abi": ABI_VERSION,
            "sources": {name: _sha256(source / name) for name in SOURCE_FILES},
            "artifacts": {name: _sha256(root / name) for name in
                          ("sfm_spatial.metallib", "libsfm_spatial.dylib")},
            "commands": commands,
            "xcode": subprocess.check_output(["xcodebuild", "-version"], text=True).strip(),
        }
        (root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        # Manifest last: a partial replacement fails bundle verification.
        for name in ("sfm_spatial.metallib", "libsfm_spatial.dylib", "manifest.json"):
            os.replace(root / name, output / name)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(build(args.output))


if __name__ == "__main__":
    main()
