#!/usr/bin/env python3
"""Verify the project constitution is present, non-empty, and loadable."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REQUIRED_FILES = [
    "AGENTS.md",
    "docs/architecture/rules.md",
    "docs/architecture/extension.md",
    "docs/project-checklist.md",
]

REQUIRED_MARKERS = [
    "验证纪律",
    "失败显式化",
    "权限边界",
    "冲突规则",
]


def main() -> int:
    errors: list[str] = []
    for rel in REQUIRED_FILES:
        path = ROOT / rel
        if not path.exists():
            errors.append(f"missing: {rel}")
        elif path.stat().st_size == 0:
            errors.append(f"empty: {rel}")

    agents = ROOT / "AGENTS.md"
    if agents.exists():
        content = agents.read_text(encoding="utf-8")
        for marker in REQUIRED_MARKERS:
            if marker not in content:
                errors.append(f"AGENTS.md missing marker: {marker}")

    if errors:
        for error in errors:
            print(f"[FAIL] {error}", file=sys.stderr)
        return 1
    print("[OK] constitution verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
