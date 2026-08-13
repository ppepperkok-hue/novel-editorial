"""Guard against heavyweight dependencies creeping back into the CLI import chain."""

from __future__ import annotations

import subprocess
import sys


def test_heavy_dependencies_stay_lazy() -> None:
    cases = [
        ("novel_editorial.llm.client", "openai"),
        ("novel_editorial.store.db", "alembic"),
        ("novel_editorial.cli.app", "sqlalchemy"),
    ]
    for module_name, forbidden in cases:
        code = (
            "import importlib, sys; "
            f"importlib.import_module({module_name!r}); "
            f"assert {forbidden!r} not in sys.modules"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, (
            f"importing {module_name} pulled in {forbidden}\n{result.stderr}"
        )
