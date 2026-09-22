"""W4 export/import round-trip demo: workspace archive + config read/write loop.

The script is idempotent: every run builds a fresh temporary data directory
and drives ``create_app()`` through ``fastapi.testclient.TestClient``, without
starting a port or depending on pre-seeded data. It exercises the export →
import round-trip (which must land under a brand-new workspace id, never
overwriting the source) and the config read/write round-trip (a whitelisted
key becomes effective and flags ``restart_required``). A failing step prints
``DEMO FAILED`` and exits non-zero immediately.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The demo is meant to run with `uv run python scripts/w4_demo.py`; the
# src-layout package stays importable under a plain interpreter as well.
sys.path.insert(0, str(ROOT / "src"))

for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if callable(_reconfigure):
        _reconfigure(encoding="utf-8", errors="replace", line_buffering=True)


def _ensure_project_env() -> None:
    """Re-run under the project environment when dependencies are missing."""
    try:
        import fastapi  # noqa: F401
        import sqlalchemy  # noqa: F401
    except ModuleNotFoundError:
        print("当前解释器缺少项目依赖，改用 uv run python 重跑 ...")
        result = subprocess.run(
            ["uv", "run", "python", str(Path(__file__).resolve())],
            cwd=str(ROOT),
        )
        raise SystemExit(result.returncode) from None


def _prepare_env(tmp: Path) -> None:
    """Point config at the temporary directory and force the mock LLM mode.

    Drop every caller-supplied ``NOVEL_*`` variable first so each run starts
    from a fresh, self-contained environment.
    """
    for key in list(os.environ):
        if key.startswith("NOVEL_"):
            os.environ.pop(key, None)
    os.environ["NOVEL_DATA_DIR"] = str(tmp / "data")
    os.environ["NOVEL_CONFIG"] = str(tmp / "config.toml")


def main() -> int:
    _ensure_project_env()

    from fastapi.testclient import TestClient

    from novel_editorial.api.app import create_app

    tmp = Path(tempfile.mkdtemp(prefix="w4-demo-"))
    _prepare_env(tmp)

    def require(label: str, ok: bool, detail: str = "") -> None:
        status = "OK" if ok else "FAIL"
        print(f"[{status}] {label}")
        if detail:
            print(f"  {detail}")
        if not ok:
            print("\nDEMO FAILED")
            raise SystemExit(1)

    print("=== W4 导出/导入回环演示（mock LLM）===")
    print(f"临时数据目录: {tmp}")

    app = create_app()
    with TestClient(app) as client:
        # 1. Create the source workspace.
        response = client.post(
            "/works",
            json={
                "title": "W4 演示之书",
                "genre": "悬疑",
                "description": "导出导入回环 + 配置读写回环",
            },
        )
        created = response.json()
        require(
            "POST /works 建作品 (status 201)",
            response.status_code == 201 and bool(created.get("id")),
            f"status={response.status_code} body={response.text}",
        )
        workspace_id = created["id"]

        # 2. Export the workspace as a ZIP byte stream.
        response = client.get(f"/works/{workspace_id}/export")
        content_type = response.headers.get("content-type", "")
        require(
            "GET /works/{id}/export 导出 ZIP (status 200)",
            response.status_code == 200
            and "application/zip" in content_type
            and bool(response.content)
            and response.content.startswith(b"PK"),
            f"status={response.status_code} content-type={content_type!r} "
            f"len={len(response.content)}",
        )
        zip_bytes = response.content

        # 3. Import the archive; it must land under a brand-new id.
        response = client.post(
            "/works/import",
            files={"file": ("export.zip", zip_bytes, "application/zip")},
        )
        imported = response.json()
        require(
            "POST /works/import 导入回环 (status 201, 全新 id)",
            response.status_code == 201
            and bool(imported.get("id"))
            and imported.get("id") != workspace_id,
            f"status={response.status_code} body={response.text}",
        )
        imported_id = imported["id"]
        print(f"  workspace_id={workspace_id} imported_id={imported_id}")

        # 4. Read the full config snapshot.
        response = client.get("/config")
        config_snapshot = response.json()
        require(
            "GET /config 快照 (status 200, restart_required=False)",
            response.status_code == 200
            and "quality_threshold" in config_snapshot
            and "panel_poll_interval" in config_snapshot
            and config_snapshot.get("restart_required") is False,
            f"status={response.status_code} body={response.text}",
        )

        # 5. Write a whitelisted key; the write requires a restart.
        response = client.put(
            "/config",
            json={"key": "quality_threshold", "value": 10},
        )
        updated = response.json()
        require(
            "PUT /config 写 quality_threshold=10 (status 200, restart_required=True)",
            response.status_code == 200
            and updated.get("restart_required") is True
            and bool(updated.get("message")),
            f"status={response.status_code} body={response.text}",
        )

        # 6. Re-read the snapshot; the write must already be effective.
        response = client.get("/config")
        reread = response.json()
        require(
            "GET /config 回读 quality_threshold==10 (status 200)",
            response.status_code == 200 and reread.get("quality_threshold") == 10,
            f"status={response.status_code} body={response.text}",
        )

    print("\nDEMO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
