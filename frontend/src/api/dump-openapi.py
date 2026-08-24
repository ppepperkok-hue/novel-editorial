"""Dump the FastAPI OpenAPI snapshot consumed by ``npm run gen:types`` (FE-W1-S1).

The snapshot is the single source for the generated TypeScript types: the
backend app is built in a throwaway temp data directory (no repo pollution)
and ``app.openapi()`` is written to ``openapi.json`` next to this script.
``schema.ts`` is produced from that snapshot by openapi-typescript and is
never hand-edited.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from novel_editorial.api.app import create_app


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="novel-openapi-") as tmp:
        os.environ["NOVEL_DATA_DIR"] = os.path.join(tmp, "data")
        os.environ["NOVEL_CONFIG"] = os.path.join(tmp, "config.toml")
        os.environ["NOVEL_FRONTEND_DIST"] = os.path.join(tmp, "no-dist")
        schema = create_app().openapi()
    snapshot = Path(__file__).resolve().parent / "openapi.json"
    snapshot.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"openapi snapshot written: {snapshot}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
