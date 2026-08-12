"""Dependency-direction guard: lower layers must not import cli."""

from __future__ import annotations

from pathlib import Path


def test_lower_layers_do_not_import_cli() -> None:
    src = Path("src/novel_editorial")
    forbidden = ["from novel_editorial.cli", "import novel_editorial.cli"]
    for layer in ("core", "store", "llm", "quality"):
        for path in (src / layer).rglob("*.py"):
            content = path.read_text(encoding="utf-8")
            assert not any(token in content for token in forbidden), f"{path} imports cli"
