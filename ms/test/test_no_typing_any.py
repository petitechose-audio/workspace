from __future__ import annotations

import ast
from pathlib import Path


def test_no_typing_any_in_ms() -> None:
    """Enforce the type-safety contract: no explicit typing.Any in ms/.

    Rationale:
    - `Any` disables type checking, and it tends to spread.
    - We rely on boundary validation helpers (`ms.core.structured`) instead.
    """

    ms_root = Path(__file__).resolve().parents[1]
    offenders: list[str] = []

    for path in ms_root.rglob("*.py"):
        rel = path.relative_to(ms_root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        if any(part == "__pycache__" for part in rel.parts):
            continue

        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            continue

        try:
            tree = ast.parse(source, filename=str(rel))
        except SyntaxError:
            continue

        typing_aliases: set[str] = set()

        for node in ast.walk(tree):
            match node:
                case ast.Import(names=names):
                    for alias in names:
                        if alias.name == "typing":
                            typing_aliases.add(alias.asname or "typing")
                case ast.ImportFrom(module="typing", names=names):
                    for alias in names:
                        if alias.name == "Any":
                            line = getattr(node, "lineno", 1)
                            offenders.append(f"{rel}:{line}: from typing import Any")
                case _:
                    pass

        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            if node.attr != "Any":
                continue
            if not isinstance(node.value, ast.Name):
                continue
            if node.value.id not in typing_aliases:
                continue

            line = getattr(node, "lineno", 1)
            offenders.append(f"{rel}:{line}: {node.value.id}.Any")

    assert not offenders, "Explicit typing.Any is forbidden:\n" + "\n".join(sorted(offenders))
