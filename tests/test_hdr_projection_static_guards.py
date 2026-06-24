from __future__ import annotations

import ast
from pathlib import Path


PROJECTION_PATH = Path(__file__).resolve().parents[1] / "src" / "spektrafilm" / "hdr" / "projection.py"
_BANNED_NUMPY_MATERIALIZERS = {"asarray", "ascontiguousarray"}


def _is_numpy_materializer_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in _BANNED_NUMPY_MATERIALIZERS
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "np"
    )


def test_backend_projection_helpers_do_not_directly_materialize_mlx_arrays() -> None:
    tree = ast.parse(PROJECTION_PATH.read_text(encoding="utf-8"))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or not node.name.endswith("_backend"):
            continue
        for child in ast.walk(node):
            if _is_numpy_materializer_call(child):
                offenders.append(f"{node.name}:{child.lineno}")

    assert offenders == []
