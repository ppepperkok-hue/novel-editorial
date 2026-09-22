"""W2 HTTP end-to-end demo: structure / outline / setting / inspiration chain.

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

# The demo is meant to run with `uv run python scripts/w2_demo.py`; the
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

    tmp = Path(tempfile.mkdtemp(prefix="w2-demo-"))
    _prepare_env(tmp)

    def require(label: str, ok: bool, detail: str = "") -> None:
        status = "OK" if ok else "FAIL"
        print(f"[{status}] {label}")
        if detail:
            print(f"  {detail}")
        if not ok:
            print("\nDEMO FAILED")
            raise SystemExit(1)

    print("=== W2 HTTP 端到端演示（mock LLM）===")
    print(f"临时数据目录: {tmp}")

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/works",
            json={
                "title": "W2 演示之书",
                "genre": "悬疑",
                "description": "界面同款结构 / 大纲 / 设定 / 灵感主链路",
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
            f"/works/{workspace_id}/structure",
            json={"kind": "volume", "title": "第一卷"},
        )
        volume = response.json()
        require(
            "POST /works/{id}/structure 建卷 (status 201)",
            response.status_code == 201
            and volume.get("kind") == "volume"
            and volume.get("parent_id") is None,
            f"status={response.status_code} body={response.text}",
        )
        volume_id = volume["id"]

        response = client.post(
            f"/works/{workspace_id}/structure",
            json={"kind": "chapter", "title": "第一章", "parent": volume_id},
        )
        chapter = response.json()
        require(
            "POST /works/{id}/structure 建章 parent=卷 (status 201)",
            response.status_code == 201
            and chapter.get("kind") == "chapter"
            and chapter.get("parent_id") == volume_id,
            f"status={response.status_code} body={response.text}",
        )
        chapter_id = chapter["id"]

        outline_content = "第一章：雨夜，她推开旧车站的门，广播声在空站台回响。"
        response = client.post(
            f"/works/{workspace_id}/outline",
            json={"content": outline_content, "actor": "作者"},
        )
        outline_created = response.json()
        require(
            "POST /works/{id}/outline 建大纲 (status 201)",
            response.status_code == 201
            and outline_created.get("version") == 1
            and outline_created.get("content") == outline_content,
            f"status={response.status_code} body={response.text}",
        )

        response = client.post(
            f"/works/{workspace_id}/settings",
            json={
                "kind": "人物",
                "name": "沈夜",
                "content": "雨夜归乡的侦探，旧车站长大的孩子。",
            },
        )
        setting_created = response.json()
        require(
            "POST /works/{id}/settings 加设定 kind=人物 (status 201)",
            response.status_code == 201
            and setting_created.get("kind") == "character"
            and setting_created.get("name") == "沈夜",
            f"status={response.status_code} body={response.text}",
        )
        setting_id = setting_created["id"]

        response = client.post(
            f"/works/{workspace_id}/inspirations",
            json={
                "content": "停运前最后一班列车的广播声",
                "kind": "灵感",
                "source": "W2 演示",
            },
        )
        inspiration_created = response.json()
        require(
            "POST /works/{id}/inspirations 加灵感 (status 201)",
            response.status_code == 201 and bool(inspiration_created.get("id")),
            f"status={response.status_code} body={response.text}",
        )
        inspiration_id = inspiration_created["id"]

        response = client.get(f"/works/{workspace_id}/structure")
        nodes = response.json()
        by_id = {node["id"]: node for node in nodes}
        ids = list(by_id)
        require(
            "GET /works/{id}/structure 树与父子关系 (status 200)",
            response.status_code == 200
            and by_id.get(volume_id) is not None
            and by_id.get(chapter_id) is not None
            and by_id[volume_id]["parent_id"] is None
            and by_id[chapter_id]["parent_id"] == volume_id
            and ids.index(volume_id) < ids.index(chapter_id),
            f"status={response.status_code} body={response.text}",
        )

        response = client.get(f"/works/{workspace_id}/outline")
        outline_shown = response.json()
        require(
            "GET /works/{id}/outline 内容断言 (status 200)",
            response.status_code == 200
            and outline_shown.get("content") == outline_content
            and outline_shown.get("version") == 1,
            f"status={response.status_code} body={response.text}",
        )

        response = client.get(f"/works/{workspace_id}/settings")
        settings = response.json()
        require(
            "GET /works/{id}/settings 条目断言 (status 200)",
            response.status_code == 200
            and any(
                entry.get("id") == setting_id
                and entry.get("kind") == "character"
                and entry.get("name") == "沈夜"
                for entry in settings
            ),
            f"status={response.status_code} body={response.text}",
        )

        response = client.get(f"/works/{workspace_id}/inspirations")
        inspirations = response.json()
        require(
            "GET /works/{id}/inspirations 灵感断言 (status 200)",
            response.status_code == 200
            and any(entry.get("id") == inspiration_id for entry in inspirations),
            f"status={response.status_code} body={response.text}",
        )

        response = client.get(f"/works/{workspace_id}/events")
        events = response.json()
        kinds = [event.get("payload", {}).get("kind") for event in events]
        require(
            "GET /works/{id}/events 留痕可见 (status 200)",
            response.status_code == 200
            and kinds.count("structure_created") >= 2
            and "outline_created" in kinds
            and "inspiration_created" in kinds,
            f"status={response.status_code} body={response.text}",
        )

        response = client.delete(f"/works/{workspace_id}/inspirations/{inspiration_id}")
        removed = response.json()
        require(
            "DELETE /works/{id}/inspirations/{id} 删除 (status 200)",
            response.status_code == 200 and removed.get("id") == inspiration_id,
            f"status={response.status_code} body={response.text}",
        )

        response = client.get(f"/works/{workspace_id}/inspirations")
        remaining = response.json()
        require(
            "GET /works/{id}/inspirations 移除后不可见 (status 200)",
            response.status_code == 200
            and all(entry.get("id") != inspiration_id for entry in remaining),
            f"status={response.status_code} body={response.text}",
        )

    print("\nDEMO OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
