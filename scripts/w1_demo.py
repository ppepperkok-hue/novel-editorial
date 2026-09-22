"""W1 HTTP end-to-end demo: the same main chain the frontend walks.

The script is idempotent: every run builds a fresh temporary data directory
and drives ``create_app()`` through ``fastapi.testclient.TestClient``, without
starting a port or depending on pre-seeded data. A failing step prints
``DEMO FAILED`` and exits non-zero immediately.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The demo is meant to run with `uv run python scripts/w1_demo.py`; the
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

    tmp = Path(tempfile.mkdtemp(prefix="w1-demo-"))
    _prepare_env(tmp)

    def require(label: str, ok: bool, detail: str = "") -> None:
        status = "OK" if ok else "FAIL"
        print(f"[{status}] {label}")
        if detail:
            print(f"  {detail}")
        if not ok:
            print("\nDEMO FAILED")
            raise SystemExit(1)

    print("=== W1 HTTP 端到端演示（mock LLM）===")
    print(f"临时数据目录: {tmp}")

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/works",
            json={
                "title": "W1 演示之书",
                "genre": "悬疑",
                "description": "界面同款主链路",
            },
        )
        created = response.json()
        require(
            "POST /works 建作品 (status 201)",
            response.status_code == 201 and bool(created.get("id")),
            f"status={response.status_code} body={response.text}",
        )
        workspace_id = created["id"]

        response = client.post(
            f"/works/{workspace_id}/talk",
            json={"message": "我们写一个雨夜故事"},
        )
        messages = response.json().get("messages", [])
        replied = any(
            item.get("role") == "agent" and bool(item.get("content")) for item in messages
        )
        require(
            "POST /works/{id}/talk 对话有回复 (status 201)",
            response.status_code == 201 and replied,
            f"status={response.status_code} messages={len(messages)} body={response.text}",
        )

        response = client.post(
            f"/works/{workspace_id}/drafts/new",
            json={"title": "第一章"},
        )
        draft_new = response.json()
        require(
            "POST /works/{id}/drafts/new 作者空稿 (status 201)",
            response.status_code == 201
            and draft_new.get("status") == "draft"
            and draft_new.get("current_version") == 0
            and draft_new.get("awaiting_decision") is True,
            f"status={response.status_code} body={response.text}",
        )
        draft_id = draft_new["id"]

        response = client.put(
            f"/works/{workspace_id}/drafts/{draft_id}/content",
            json={"content": "雨夜，她推开旧车站的门。", "reason": "初稿"},
        )
        saved = response.json()
        require(
            "PUT /works/{id}/drafts/{id}/content 手写正文 (status 200)",
            response.status_code == 200
            and saved.get("status") == "draft"
            and saved.get("current_version") == 1
            and saved.get("awaiting_decision") is True,
            f"status={response.status_code} body={response.text}",
        )

        response = client.get(f"/works/{workspace_id}/pending")
        pending = response.json()
        require(
            "GET /works/{id}/pending 有待拍板 (status 200)",
            response.status_code == 200 and any(item.get("id") == draft_id for item in pending),
            f"status={response.status_code} body={response.text}",
        )

        response = client.post(
            f"/works/{workspace_id}/decisions",
            json={"draft_id": draft_id, "action": "accept"},
        )
        decided = response.json()
        require(
            "POST /works/{id}/decisions accept 拍板 (status 201)",
            response.status_code == 201 and decided.get("status") == "accepted",
            f"status={response.status_code} body={response.text}",
        )

        response = client.get(f"/works/{workspace_id}/pending")
        pending_after = response.json()
        require(
            "GET /works/{id}/pending 拍板后为空 (status 200)",
            response.status_code == 200 and pending_after == [],
            f"status={response.status_code} body={response.text}",
        )

    print("\nDEMO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
