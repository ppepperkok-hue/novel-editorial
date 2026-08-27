"""HTTP API tests: health, works list/create/show, visibility routes, read-only guarantees."""

from __future__ import annotations

import json
import socket
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from typer.testing import CliRunner, Result

from novel_editorial.api import app as api_app
from novel_editorial.api.app import create_app
from novel_editorial.cli.app import app as cli_app
from novel_editorial.core.behavior import record_behavior_entry_safe
from novel_editorial.core.config import load_settings
from novel_editorial.core.structure import create_node
from novel_editorial.core.style import set_style_anchor
from novel_editorial.events import EventType
from novel_editorial.llm.client import MockLLMClient
from novel_editorial.store.db import DB
from novel_editorial.store.events import EventRecord, list_events_since, record_event
from novel_editorial.store.models import (
    Agent,
    AgentMotive,
    Draft,
    DraftVersion,
    Event,
    MotiveKind,
    Review,
    Workspace,
)

runner = CliRunner()


def _make_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[TestClient, DB]:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    monkeypatch.setenv("NOVEL_FRONTEND_DIST", str(tmp_path / "no-dist"))
    return TestClient(create_app()), DB(load_settings())


def _table_counts(db: DB, workspace_id: str) -> list[dict[str, int]]:
    """Count rows in every table of the global and workspace databases."""
    snapshots: list[dict[str, int]] = []
    for session in (db.global_session(), db.workspace_session(workspace_id)):
        with session:
            engine = session.get_bind()
            snapshots.append(
                {
                    table: session.execute(
                        text(f'SELECT COUNT(*) FROM "{table}"')
                    ).scalar_one()
                    for table in inspect(engine).get_table_names()
                }
            )
    return snapshots


def _detail_text(detail: object) -> str:
    """Flatten a FastAPI validation detail into one searchable string."""
    if isinstance(detail, str):
        return detail
    if not isinstance(detail, list):
        return str(detail)
    parts: list[str] = []
    for item in detail:
        if not isinstance(item, dict):
            parts.append(str(item))
            continue
        loc = ".".join(str(part) for part in item.get("loc", []))
        parts.append(f"{loc}: {item.get('msg', item)}")
    return " | ".join(parts)


def _seed_workspace(client: TestClient, db: DB, title: str = "可见性之书") -> str:
    """Create a workspace with style anchor, structure nodes, and one event."""
    workspace_id = client.post("/works", json={"title": title}).json()["id"]
    set_style_anchor(db, workspace_id, description="冷峻克制", forbidden_words="宛如、仿佛")
    volume = create_node(db, workspace_id, kind="volume", title="第一卷", sort_order=1)
    create_node(db, workspace_id, kind="chapter", title="第一章", parent_id=volume.id)
    record_event(
        db,
        workspace_id,
        type=EventType.SYSTEM,
        actor="system",
        payload={"kind": "manual_seed"},
    )
    return workspace_id


def _seed_draft(
    db: DB,
    workspace_id: str,
    *,
    title: str = "第一章",
    content: str = "雨夜开场，钩子埋下。",
    status: str = "draft",
    version: int = 1,
) -> str:
    """Insert one draft with its initial version directly (no LLM involved)."""
    with db.workspace_session(workspace_id) as session:
        draft = Draft(
            workspace_id=workspace_id,
            title=title,
            status=status,
            current_version=version,
        )
        session.add(draft)
        session.flush()
        session.add(
            DraftVersion(
                draft_id=draft.id,
                version=version,
                content=content,
                reason="initial" if version == 1 else "revision",
            )
        )
        session.commit()
        return draft.id


def _seed_draft_version(
    db: DB,
    workspace_id: str,
    draft_id: str,
    *,
    version: int,
    content: str,
    reason: str = "revision",
) -> None:
    """Append one version row to an existing draft (no LLM involved)."""
    with db.workspace_session(workspace_id) as session:
        session.add(
            DraftVersion(
                draft_id=draft_id,
                version=version,
                content=content,
                reason=reason,
            )
        )
        session.commit()


def _seed_review(
    db: DB,
    workspace_id: str,
    draft_id: str,
    *,
    actor: str = "责编",
    content: str = "钩子再亮一点",
) -> None:
    with db.workspace_session(workspace_id) as session:
        session.add(
            Review(
                workspace_id=workspace_id,
                draft_id=draft_id,
                role="agent",
                actor=actor,
                content=content,
            )
        )
        session.commit()


def _seed_motive(
    db: DB,
    workspace_id: str,
    *,
    agent_id: str,
    kind: str = MotiveKind.GOAL.value,
    content: str = "新章已交",
    source: str = "event:draft_generated",
    strength: int = 100,
) -> str:
    """Insert one motive row directly (no LLM involved)."""
    with db.workspace_session(workspace_id) as session:
        motive = AgentMotive(
            workspace_id=workspace_id,
            agent_id=agent_id,
            kind=kind,
            content=content,
            source=source,
            strength=strength,
        )
        session.add(motive)
        session.commit()
        return motive.id


def _seed_behavior(
    db: DB,
    workspace_id: str,
    *,
    agent_id: str,
    kind: str,
    target: str,
    summary: str = "",
    before_value: str | None = None,
    after_value: str | None = None,
    source: str = "",
) -> None:
    """Append one behavior timeline row (record_behavior_entry_safe)."""
    assert record_behavior_entry_safe(
        db,
        workspace_id,
        agent_id=agent_id,
        kind=kind,
        target=target,
        summary=summary,
        before_value=before_value,
        after_value=after_value,
        source=source,
    )


def _first_agent(db: DB, workspace_id: str) -> Agent:
    """Return the first partner of the band (creation order)."""
    with db.workspace_session(workspace_id) as session:
        agent = (
            session.query(Agent)
            .filter_by(workspace_id=workspace_id)
            .order_by(Agent.created_at, Agent.id)
            .first()
        )
        assert agent is not None, "workspace must have a band"
        return agent


def _patch_llm(monkeypatch: pytest.MonkeyPatch, reply: str) -> None:
    """Point both the CLI and the API at the same deterministic mock client."""
    monkeypatch.setattr(
        "novel_editorial.cli.talk.build_client",
        lambda settings: MockLLMClient(reply=reply),
    )
    monkeypatch.setattr(
        "novel_editorial.cli.draft.build_client",
        lambda settings: MockLLMClient(reply=reply),
    )
    monkeypatch.setattr(
        "novel_editorial.api.app.build_client",
        lambda settings: MockLLMClient(reply=reply),
    )


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _start_api_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[uvicorn.Server, threading.Thread, int]:
    """Start a real uvicorn server bound to a free local port."""
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    monkeypatch.setenv("NOVEL_FRONTEND_DIST", str(tmp_path / "no-dist"))
    port = _free_port()
    config = uvicorn.Config(
        create_app,
        factory=True,
        host="127.0.0.1",
        port=port,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.started, "API server failed to start"
    return server, thread, port


def _stop_api_server(server: uvicorn.Server, thread: threading.Thread) -> None:
    server.should_exit = True
    thread.join(timeout=10)


def test_health(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_config_default_poll_interval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    response = client.get("/config")
    assert response.status_code == 200
    data = response.json()
    assert data["panel_poll_interval"] == 3
    assert data["restart_required"] is False


def test_config_reflects_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NOVEL_PANEL_POLL_INTERVAL", "7")
    client, _ = _make_client(tmp_path, monkeypatch)
    response = client.get("/config")
    assert response.status_code == 200
    data = response.json()
    assert data["panel_poll_interval"] == 7
    assert data["restart_required"] is False


def test_works_list_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    response = client.get("/works")
    assert response.status_code == 200
    assert response.json() == []


def test_works_create_and_list_sorted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    first = client.post(
        "/works",
        json={"title": "甲书", "genre": "网文", "description": "第一本"},
    )
    assert first.status_code == 201
    first_body = first.json()
    assert first_body["title"] == "甲书"
    assert first_body["genre"] == "网文"
    assert first_body["description"] == "第一本"
    assert first_body["status"] == "writing"
    assert first_body["id"]
    assert first_body["created_at"]

    second = client.post("/works", json={"title": "乙书"})
    assert second.status_code == 201
    second_body = second.json()
    assert second_body["genre"] == ""
    assert second_body["description"] == ""

    listed = client.get("/works")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [
        first_body["id"],
        second_body["id"],
    ]


def test_works_create_requires_title(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    missing = client.post("/works", json={})
    assert missing.status_code == 422
    assert "detail" in missing.json()

    empty = client.post("/works", json={"title": ""})
    assert empty.status_code == 422
    assert "detail" in empty.json()


def test_works_show(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    created = client.post(
        "/works",
        json={"title": "展示之书", "genre": "短篇", "description": "一段简介"},
    ).json()

    response = client.get(f"/works/{created['id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "展示之书"
    assert body["genre"] == "短篇"
    assert body["description"] == "一段简介"
    assert body["status"] == "writing"

    band = body["band"]
    assert len(band) == 4
    roles = {agent["role"] for agent in band}
    assert roles == {"editor_in_chief", "editor", "writer", "reviewer"}
    for agent in band:
        assert agent["id"]
        assert agent["name"]
        assert agent["personality"]


def test_works_show_missing_returns_404(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    response = client.get("/works/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {"detail": "workspace not found: does-not-exist"}


def test_get_routes_do_not_write_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = _make_client(tmp_path, monkeypatch)
    created = client.post("/works", json={"title": "只读之书"}).json()
    workspace_id = created["id"]

    with db.workspace_session(workspace_id) as session:
        assert session.query(Event).count() == 0

    for url in ("/health", "/works", f"/works/{workspace_id}"):
        response = client.get(url)
        assert response.status_code == 200

    with db.workspace_session(workspace_id) as session:
        assert session.query(Event).count() == 0


def test_error_response_body_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)

    not_found = client.get("/works/missing")
    assert not_found.status_code == 404
    not_found_body = not_found.json()
    assert set(not_found_body) == {"detail"}
    assert isinstance(not_found_body["detail"], str)

    invalid = client.post("/works", json={})
    assert invalid.status_code == 422
    invalid_body = invalid.json()
    assert set(invalid_body) == {"detail"}


def test_unhandled_exception_maps_to_500(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from novel_editorial.core import workspace

    def boom(*args, **kwargs) -> None:
        raise RuntimeError("simulated failure")

    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    monkeypatch.setenv("NOVEL_FRONTEND_DIST", str(tmp_path / "no-dist"))
    client = TestClient(create_app(), raise_server_exceptions=False)
    monkeypatch.setattr(workspace, "create_workspace", boom)

    response = client.post("/works", json={"title": "会炸的书"})
    assert response.status_code == 500
    assert response.json() == {"detail": "simulated failure"}


def test_works_list_same_created_at_tiebreak_by_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = _make_client(tmp_path, monkeypatch)
    first = client.post("/works", json={"title": "甲书"}).json()
    second = client.post("/works", json={"title": "乙书"}).json()
    ids = [first["id"], second["id"]]

    fixed = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
    with db.global_session() as session:
        for workspace_id in ids:
            workspace = session.get(Workspace, workspace_id)
            assert workspace is not None
            workspace.created_at = fixed
        session.commit()

    listed = client.get("/works")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == sorted(ids)


def test_works_show_band_same_created_at_tiebreak_by_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "班底之书"}).json()["id"]

    fixed = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
    with db.workspace_session(workspace_id) as session:
        for agent in session.query(Agent).all():
            agent.created_at = fixed
        session.commit()

    response = client.get(f"/works/{workspace_id}")
    assert response.status_code == 200
    band = response.json()["band"]
    assert [agent["id"] for agent in band] == sorted(agent["id"] for agent in band)


def test_overview_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    response = client.get("/overview")
    assert response.status_code == 200
    assert response.json() == {"overviews": [], "total": 0, "skipped": 0}


def test_visibility_routes_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = _make_client(tmp_path, monkeypatch)
    workspace_id = _seed_workspace(client, db)

    overview_response = client.get("/overview")
    assert overview_response.status_code == 200
    overview_body = overview_response.json()
    assert set(overview_body) == {"overviews", "total", "skipped"}
    assert overview_body["total"] == 1
    assert overview_body["skipped"] == 0
    assert len(overview_body["overviews"]) == 1
    item = overview_body["overviews"][0]
    assert set(item) == {
        "workspace_id",
        "title",
        "genre",
        "status",
        "pending_count",
        "structure",
        "last_activity",
        "created_at",
    }
    assert item["workspace_id"] == workspace_id
    assert item["title"] == "可见性之书"
    assert item["status"] == "writing"
    assert item["pending_count"] == 0
    assert item["structure"] == "0/1 章"
    assert isinstance(item["last_activity"], str)
    assert isinstance(item["created_at"], str)

    events_response = client.get(f"/works/{workspace_id}/events")
    assert events_response.status_code == 200
    events = events_response.json()
    assert len(events) == 3
    assert events[0]["type"] == "system"
    assert events[0]["payload"] == {"kind": "manual_seed"}
    assert events[-1]["payload"]["kind"] == "structure_created"
    for event in events:
        assert set(event) == {"id", "workspace_id", "type", "time", "actor", "payload"}
        assert isinstance(event["payload"], dict)
        assert isinstance(event["time"], str)
        assert event["workspace_id"] == workspace_id

    style_response = client.get(f"/works/{workspace_id}/style")
    assert style_response.status_code == 200
    assert style_response.json() == {
        "description": "冷峻克制",
        "forbidden_words": "宛如、仿佛",
    }

    structure_response = client.get(f"/works/{workspace_id}/structure")
    assert structure_response.status_code == 200
    nodes = structure_response.json()
    assert len(nodes) == 2
    assert [node["kind"] for node in nodes] == ["volume", "chapter"]
    assert nodes[1]["parent_id"] == nodes[0]["id"]
    for node in nodes:
        assert set(node) == {
            "id",
            "kind",
            "title",
            "parent_id",
            "sort_order",
            "status",
            "draft_id",
            "created_at",
        }
        assert isinstance(node["created_at"], str)
    assert nodes[0]["title"] == "第一卷"
    assert nodes[0]["sort_order"] == 1
    assert nodes[0]["status"] == "writing"
    assert nodes[0]["draft_id"] is None
    assert nodes[1]["title"] == "第一章"
    assert nodes[1]["sort_order"] == 1


def test_style_route_missing_anchor_is_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A workspace without a style anchor gets empty values and no row is created."""
    client, db = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "无锚之书"}).json()["id"]

    before_counts = _table_counts(db, workspace_id)
    assert before_counts[1]["style_anchors"] == 0

    response = client.get(f"/works/{workspace_id}/style")
    assert response.status_code == 200
    assert response.json() == {"description": "", "forbidden_words": ""}

    assert _table_counts(db, workspace_id) == before_counts


@pytest.mark.parametrize(
    "path",
    [
        "/works/missing/events",
        "/works/missing/style",
        "/works/missing/structure",
        "/works/missing/outline",
        "/works/missing/settings",
        "/works/missing/settings/check",
        "/works/missing/inspirations",
    ],
)
def test_workspace_visibility_routes_missing_workspace_404(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    response = client.get(path)
    assert response.status_code == 404
    assert response.json() == {"detail": "workspace not found: missing"}


def test_visibility_routes_are_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = _make_client(tmp_path, monkeypatch)
    workspace_id = _seed_workspace(client, db)

    before_counts = _table_counts(db, workspace_id)
    events_before = client.get(f"/works/{workspace_id}/events").json()

    for url in (
        "/overview",
        f"/works/{workspace_id}/events",
        f"/works/{workspace_id}/style",
        f"/works/{workspace_id}/structure",
        f"/works/{workspace_id}/outline",
        f"/works/{workspace_id}/settings",
        f"/works/{workspace_id}/settings/check",
        f"/works/{workspace_id}/inspirations",
    ):
        response = client.get(url)
        assert response.status_code == 200

    assert _table_counts(db, workspace_id) == before_counts
    assert client.get(f"/works/{workspace_id}/events").json() == events_before


def test_frontend_dist_is_served_when_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text(
        "<html><body>Novel Editorial 面板</body></html>",
        encoding="utf-8",
    )
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    monkeypatch.setenv("NOVEL_FRONTEND_DIST", str(dist))

    client = TestClient(create_app())
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Novel Editorial 面板" in response.text


def test_frontend_dist_missing_keeps_api_behavior(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    monkeypatch.setenv("NOVEL_FRONTEND_DIST", str(tmp_path / "missing-dist"))

    client = TestClient(create_app())
    assert client.get("/").status_code == 404
    assert client.get("/health").status_code == 200


def test_global_events_merge_workspaces_newest_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = _make_client(tmp_path, monkeypatch)
    first = client.post("/works", json={"title": "甲书"}).json()["id"]
    second = client.post("/works", json={"title": "乙书"}).json()["id"]

    record_event(db, first, type=EventType.SYSTEM, actor="system", payload={"n": 1})
    record_event(db, second, type=EventType.SYSTEM, actor="system", payload={"n": 2})
    record_event(db, first, type=EventType.SYSTEM, actor="system", payload={"n": 3})

    response = client.get("/events")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"events", "skipped"}
    assert body["skipped"] == 0
    events = body["events"]
    assert [event["payload"]["n"] for event in events] == [3, 2, 1]
    assert {event["workspace_id"] for event in events} == {first, second}
    for event in events:
        assert set(event) == {"id", "workspace_id", "type", "time", "actor", "payload"}
        assert isinstance(event["payload"], dict)
        assert isinstance(event["time"], str)

    limited = client.get("/events", params={"limit": 2})
    assert limited.status_code == 200
    limited_body = limited.json()
    assert limited_body["skipped"] == 0
    assert [event["payload"]["n"] for event in limited_body["events"]] == [3, 2]

    invalid = client.get("/events", params={"limit": 0})
    assert invalid.status_code == 422
    assert "detail" in invalid.json()


def test_global_events_uses_registry_not_disk_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Events come from the global workspaces registry, not from scanning data/works."""
    client, db = _make_client(tmp_path, monkeypatch)
    registered = client.post("/works", json={"title": "注册之书"}).json()["id"]
    record_event(db, registered, type=EventType.SYSTEM, actor="system", payload={"n": 1})

    orphan = "orphan-workspace"
    db.create_workspace_db(orphan)
    record_event(db, orphan, type=EventType.SYSTEM, actor="system", payload={"n": 99})

    response = client.get("/events")
    assert response.status_code == 200
    body = response.json()
    assert body["skipped"] == 0
    events = body["events"]
    assert [event["payload"]["n"] for event in events] == [1]
    assert {event["workspace_id"] for event in events} == {registered}


def test_global_events_skips_failed_workspace_and_warns_on_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    client, db = _make_client(tmp_path, monkeypatch)
    first = client.post("/works", json={"title": "甲书"}).json()["id"]
    second = client.post("/works", json={"title": "乙书"}).json()["id"]
    record_event(db, first, type=EventType.SYSTEM, actor="system", payload={"n": 1})
    record_event(db, second, type=EventType.SYSTEM, actor="system", payload={"n": 2})

    original_list_events = api_app.list_events

    def flaky_list_events(
        db: DB, workspace_id: str, *, types=None, limit: int = 20
    ) -> list:
        if workspace_id == first:
            raise RuntimeError("simulated workspace failure")
        return original_list_events(db, workspace_id, types=types, limit=limit)

    monkeypatch.setattr(api_app, "list_events", flaky_list_events)

    response = client.get("/events")
    assert response.status_code == 200
    body = response.json()
    assert body["skipped"] == 1
    assert [event["payload"]["n"] for event in body["events"]] == [2]
    warning = capsys.readouterr().err
    assert f"warning: events skipped: {first}" in warning
    assert "simulated workspace failure" in warning


def test_pending_drafts_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "待拍板之书"}).json()["id"]
    pending_id = _seed_draft(db, workspace_id, title="第一章", status="draft")
    _seed_draft(db, workspace_id, title="已拒", status="rejected")
    _seed_draft(db, workspace_id, title="已过", status="accepted")

    response = client.get(f"/works/{workspace_id}/pending")
    assert response.status_code == 200
    pending = response.json()
    assert len(pending) == 1
    item = pending[0]
    assert set(item) == {"id", "title", "status", "current_version", "updated_at"}
    assert item["id"] == pending_id
    assert item["title"] == "第一章"
    assert item["status"] == "draft"
    assert item["current_version"] == 1
    assert isinstance(item["updated_at"], str)


def test_drafts_list_and_detail_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "草稿之书"}).json()["id"]
    draft_id = _seed_draft(db, workspace_id, title="第一章", content="初版正文")
    with db.workspace_session(workspace_id) as session:
        draft_row = session.get(Draft, draft_id)
        assert draft_row is not None
        draft_row.current_version = 2
        session.add(
            DraftVersion(
                draft_id=draft_id,
                version=2,
                content="修订版正文",
                reason="revision",
            )
        )
        session.commit()

    listed = client.get(f"/works/{workspace_id}/drafts")
    assert listed.status_code == 200
    items = listed.json()
    assert len(items) == 1
    assert set(items[0]) == {"id", "title", "status", "current_version", "updated_at"}
    assert items[0]["id"] == draft_id
    assert items[0]["title"] == "第一章"
    assert items[0]["current_version"] == 2

    detail = client.get(f"/works/{workspace_id}/drafts/{draft_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert set(body) == {
        "id",
        "title",
        "status",
        "current_version",
        "created_at",
        "updated_at",
        "versions",
    }
    assert body["title"] == "第一章"
    assert body["status"] == "draft"
    assert body["current_version"] == 2
    versions = body["versions"]
    assert [version["version"] for version in versions] == [1, 2]
    for version in versions:
        assert set(version) == {"version", "reason", "actor", "created_at", "content"}
    assert versions[0]["content"] == "初版正文"
    assert versions[0]["reason"] == "initial"
    assert versions[0]["actor"] == ""
    assert versions[1]["content"] == "修订版正文"
    assert versions[1]["reason"] == "revision"
    assert versions[1]["actor"] == ""

    missing = client.get(f"/works/{workspace_id}/drafts/does-not-exist")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "draft not found: does-not-exist"}


def test_draft_diff_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "对比之书"}).json()["id"]
    draft_id = _seed_draft(db, workspace_id, title="第一章", content="第一版正文")
    _seed_draft_version(
        db, workspace_id, draft_id, version=2, content="第二版正文，更冷。"
    )

    response = client.get(
        f"/works/{workspace_id}/drafts/{draft_id}/diff",
        params={"version_a": 1, "version_b": 2},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    text = response.text
    assert "--- v1" in text
    assert "+++ v2" in text
    assert "第一版正文" in text
    assert "第二版正文，更冷。" in text


def test_draft_diff_no_differences_when_versions_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "无差之书"}).json()["id"]
    draft_id = _seed_draft(db, workspace_id, content="同一句话")
    _seed_draft_version(db, workspace_id, draft_id, version=2, content="同一句话")

    response = client.get(
        f"/works/{workspace_id}/drafts/{draft_id}/diff",
        params={"version_a": 1, "version_b": 2},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert response.text == "no differences"


def test_draft_diff_respects_version_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "顺序之书"}).json()["id"]
    draft_id = _seed_draft(db, workspace_id, content="第一版正文")
    _seed_draft_version(db, workspace_id, draft_id, version=2, content="第二版正文")

    response = client.get(
        f"/works/{workspace_id}/drafts/{draft_id}/diff",
        params={"version_a": 2, "version_b": 1},
    )
    assert response.status_code == 200
    text = response.text
    assert "--- v2" in text
    assert "+++ v1" in text


def test_draft_diff_missing_versions_are_404(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "缺版之书"}).json()["id"]
    draft_id = _seed_draft(db, workspace_id, content="第一版正文")

    missing_a = client.get(
        f"/works/{workspace_id}/drafts/{draft_id}/diff",
        params={"version_a": 99, "version_b": 1},
    )
    assert missing_a.status_code == 404
    assert missing_a.json() == {
        "detail": f"draft version not found: {draft_id} v99"
    }

    missing_b = client.get(
        f"/works/{workspace_id}/drafts/{draft_id}/diff",
        params={"version_a": 1, "version_b": 99},
    )
    assert missing_b.status_code == 404
    assert missing_b.json() == {
        "detail": f"draft version not found: {draft_id} v99"
    }


def test_draft_diff_invalid_or_missing_version_params_are_422(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "参数之书"}).json()["id"]
    draft_id = _seed_draft(db, workspace_id, content="正文")

    non_int = client.get(
        f"/works/{workspace_id}/drafts/{draft_id}/diff",
        params={"version_a": "abc", "version_b": 1},
    )
    assert non_int.status_code == 422
    assert "version_a" in _detail_text(non_int.json()["detail"])

    missing = client.get(
        f"/works/{workspace_id}/drafts/{draft_id}/diff",
        params={"version_a": 1},
    )
    assert missing.status_code == 422
    assert "version_b" in _detail_text(missing.json()["detail"])


def test_draft_diff_v0_draft_is_usage_error_422(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "空稿之书"}).json()["id"]
    draft_id = client.post(
        f"/works/{workspace_id}/drafts/new", json={"title": "第一章"}
    ).json()["id"]

    response = client.get(
        f"/works/{workspace_id}/drafts/{draft_id}/diff",
        params={"version_a": 1, "version_b": 1},
    )
    assert response.status_code == 422
    assert response.json() == {
        "detail": "cannot diff a draft with no versions; save a version first"
    }


def test_draft_diff_missing_workspace_or_draft_404(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "缺件之书"}).json()["id"]

    missing_workspace = client.get(
        "/works/nope/drafts/x/diff",
        params={"version_a": 1, "version_b": 1},
    )
    assert missing_workspace.status_code == 404
    assert missing_workspace.json() == {"detail": "workspace not found: nope"}

    missing_draft = client.get(
        f"/works/{workspace_id}/drafts/nope/diff",
        params={"version_a": 1, "version_b": 1},
    )
    assert missing_draft.status_code == 404
    assert missing_draft.json() == {"detail": "draft not found: nope"}


def test_openapi_draft_diff_200_is_text_plain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The diff endpoint must advertise text/plain, not application/json."""
    _make_client(tmp_path, monkeypatch)
    responses = create_app().openapi()["paths"][
        "/works/{workspace_id}/drafts/{draft_id}/diff"
    ]["get"]["responses"]["200"]
    assert "text/plain" in responses["content"]
    assert "application/json" not in responses["content"]


def test_openapi_export_200_is_application_zip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The export endpoint must advertise application/zip, not application/json."""
    _make_client(tmp_path, monkeypatch)
    content = create_app().openapi()["paths"][
        "/works/{workspace_id}/export"
    ]["get"]["responses"]["200"]["content"]
    assert "application/zip" in content
    assert content["application/zip"]["schema"]["format"] == "binary"


def test_openapi_outline_settings_post_declare_201(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Outline/settings create paths must advertise 201 (create) and keep 200 (revise)."""
    _make_client(tmp_path, monkeypatch)
    spec = create_app().openapi()["paths"]
    for path in (
        "/works/{workspace_id}/outline",
        "/works/{workspace_id}/settings",
    ):
        responses = spec[path]["post"]["responses"]
        assert "201" in responses
        assert "200" in responses


def test_reviews_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, db = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "意见之书"}).json()["id"]
    draft_id = _seed_draft(db, workspace_id)
    _seed_review(db, workspace_id, draft_id, actor="责编", content="钩子再亮一点")
    _seed_review(db, workspace_id, draft_id, actor="作者", content="方向没问题")

    response = client.get(f"/works/{workspace_id}/reviews", params={"draft_id": draft_id})
    assert response.status_code == 200
    reviews = response.json()
    assert len(reviews) == 2
    for item in reviews:
        assert set(item) == {"id", "role", "actor", "content", "created_at"}
        assert isinstance(item["created_at"], str)
    assert [item["actor"] for item in reviews] == ["责编", "作者"]
    assert [item["content"] for item in reviews] == ["钩子再亮一点", "方向没问题"]

    missing = client.get(f"/works/{workspace_id}/reviews")
    assert missing.status_code == 422
    assert missing.json() == {"detail": "draft_id is required"}

    unknown = client.get(
        f"/works/{workspace_id}/reviews", params={"draft_id": "does-not-exist"}
    )
    assert unknown.status_code == 404
    assert unknown.json() == {"detail": "draft not found: does-not-exist"}


def test_inspect_and_log_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = _make_client(tmp_path, monkeypatch)
    workspace_id = _seed_workspace(client, db)
    draft_id = _seed_draft(db, workspace_id, content="冷峻克制的雨夜开场")
    _seed_review(db, workspace_id, draft_id, content="冷峻的钩子再亮一点")

    inspected = client.get(f"/works/{workspace_id}/inspect", params={"keyword": "冷峻"})
    assert inspected.status_code == 200
    assert inspected.headers["content-type"].startswith("text/plain")
    assert "[风格]" in inspected.text
    assert "冷峻克制" in inspected.text
    assert "[版本]" in inspected.text
    assert "冷峻克制的雨夜开场" in inspected.text
    assert "[意见]" in inspected.text
    assert "冷峻的钩子再亮一点" in inspected.text

    logged = client.get(f"/works/{workspace_id}/log")
    assert logged.status_code == 200
    assert logged.headers["content-type"].startswith("text/plain")
    assert "作品：《可见性之书》" in logged.text
    assert "== 草稿 ==" in logged.text
    assert "第一章" in logged.text
    assert "冷峻克制的雨夜开场" in logged.text
    assert "== 意见 ==" in logged.text
    assert "冷峻的钩子再亮一点" in logged.text


def test_inspect_and_log_return_plain_text_not_json_escaped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PlainTextResponse keeps quotes and newlines verbatim, unlike JSON encoding."""
    client, db = _make_client(tmp_path, monkeypatch)
    workspace_id = _seed_workspace(client, db)
    _seed_draft(db, workspace_id, content='含"引号"与\n换行的正文')

    inspected = client.get(
        f"/works/{workspace_id}/inspect", params={"keyword": "引号"}
    )
    assert inspected.status_code == 200
    assert inspected.headers["content-type"].startswith("text/plain")
    assert '含"引号"' in inspected.text
    assert "\\\"" not in inspected.text

    logged = client.get(f"/works/{workspace_id}/log")
    assert logged.status_code == 200
    assert logged.headers["content-type"].startswith("text/plain")
    assert '含"引号"' in logged.text
    assert "\\\"" not in logged.text
    assert "\n" in logged.text


def test_inspect_missing_or_blank_keyword_is_422(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = _make_client(tmp_path, monkeypatch)
    workspace_id = _seed_workspace(client, db)

    missing = client.get(f"/works/{workspace_id}/inspect")
    assert missing.status_code == 422
    assert missing.json() == {"detail": "search keyword must not be empty"}

    blank = client.get(f"/works/{workspace_id}/inspect", params={"keyword": "   "})
    assert blank.status_code == 422
    assert blank.json() == {"detail": "search keyword must not be empty"}


def test_decisions_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "拍板之书"}).json()["id"]
    pending_id = _seed_draft(db, workspace_id, title="第一章")
    record_event(
        db,
        workspace_id,
        type=EventType.DECISION_REQUESTED,
        actor="system",
        payload={"draft_id": pending_id, "version": 1},
    )
    events_before = client.get(f"/works/{workspace_id}/events").json()
    assert any(event["type"] == "decision.requested" for event in events_before)

    accepted = client.post(
        f"/works/{workspace_id}/decisions",
        json={"draft_id": pending_id, "action": "accept"},
    )
    assert accepted.status_code == 201
    assert accepted.json() == {"id": pending_id, "status": "accepted"}
    assert client.get(f"/works/{workspace_id}/pending").json() == []
    drafts = client.get(f"/works/{workspace_id}/drafts").json()
    assert [item["status"] for item in drafts] == ["accepted"]

    already = client.post(
        f"/works/{workspace_id}/decisions",
        json={"draft_id": pending_id, "action": "accept"},
    )
    assert already.status_code == 422
    assert "already accepted" in already.json()["detail"]

    rejected_id = _seed_draft(db, workspace_id, title="第二章", status="draft")
    rejected = client.post(
        f"/works/{workspace_id}/decisions",
        json={"draft_id": rejected_id, "action": "reject"},
    )
    assert rejected.status_code == 201
    assert rejected.json() == {"id": rejected_id, "status": "rejected"}

    noted_id = _seed_draft(db, workspace_id, title="第三章", status="draft")
    noted = client.post(
        f"/works/{workspace_id}/decisions",
        json={"draft_id": noted_id, "action": "note", "content": "方向没问题"},
    )
    assert noted.status_code == 201
    assert noted.json() == {"id": noted_id, "status": "draft"}
    pending_now = client.get(f"/works/{workspace_id}/pending").json()
    assert [item["id"] for item in pending_now] == [noted_id]

    blank_note = client.post(
        f"/works/{workspace_id}/decisions",
        json={"draft_id": noted_id, "action": "note"},
    )
    assert blank_note.status_code == 422
    assert "note requires --content" in blank_note.json()["detail"]

    invalid = client.post(
        f"/works/{workspace_id}/decisions",
        json={"draft_id": noted_id, "action": "approve"},
    )
    assert invalid.status_code == 422
    assert invalid.json() == {"detail": "unknown decision action: approve"}

    unknown = client.post(
        f"/works/{workspace_id}/decisions",
        json={"draft_id": "does-not-exist", "action": "accept"},
    )
    assert unknown.status_code == 404
    assert unknown.json() == {"detail": "draft not found: does-not-exist"}

    missing_workspace = client.post(
        "/works/does-not-exist/decisions",
        json={"draft_id": pending_id, "action": "accept"},
    )
    assert missing_workspace.status_code == 404
    assert missing_workspace.json() == {"detail": "workspace not found: does-not-exist"}

    malformed = client.post(
        f"/works/{workspace_id}/decisions", json={"action": "accept"}
    )
    assert malformed.status_code == 422
    assert "detail" in malformed.json()

    assert client.get(f"/works/{workspace_id}/events").json() == events_before


def test_panel_routes_404_for_missing_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    paths = (
        "/works/missing/pending",
        "/works/missing/drafts",
        "/works/missing/drafts/x",
        "/works/missing/drafts/x/decisions",
        "/works/missing/talk",
        "/works/missing/reviews?draft_id=x",
        "/works/missing/inspect?keyword=k",
        "/works/missing/log",
        "/works/missing/events/stream",
    )
    for path in paths:
        response = client.get(path)
        assert response.status_code == 404, path
        assert response.json() == {"detail": "workspace not found: missing"}


def test_panel_read_routes_do_not_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = _make_client(tmp_path, monkeypatch)
    workspace_id = _seed_workspace(client, db)
    draft_id = _seed_draft(db, workspace_id, content="冷峻克制的雨夜开场")
    _seed_review(db, workspace_id, draft_id, content="冷峻的钩子再亮一点")

    before_counts = _table_counts(db, workspace_id)
    events_before = client.get(f"/works/{workspace_id}/events").json()

    for url in (
        "/config",
        "/events",
        f"/works/{workspace_id}/pending",
        f"/works/{workspace_id}/drafts",
        f"/works/{workspace_id}/drafts/{draft_id}",
        f"/works/{workspace_id}/reviews?draft_id={draft_id}",
        f"/works/{workspace_id}/inspect?keyword=冷峻",
        f"/works/{workspace_id}/log",
    ):
        response = client.get(url)
        assert response.status_code == 200, url

    assert _table_counts(db, workspace_id) == before_counts
    assert client.get(f"/works/{workspace_id}/events").json() == events_before


def test_templates_endpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    response = client.get("/templates")
    assert response.status_code == 200
    body = response.json()
    assert [item["name"] for item in body] == ["网文", "同人", "正统"]
    for item in body:
        assert set(item) == {"name", "description"}
        assert item["description"]


def test_talk_send_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_llm(monkeypatch, reply="（模拟回复）")
    client, _ = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "对话之书"}).json()["id"]

    response = client.post(
        f"/works/{workspace_id}/talk", json={"message": "我们写一个侦探故事"}
    )
    assert response.status_code == 201
    assert set(response.json()) == {"messages"}
    messages = response.json()["messages"]
    assert [message["role"] for message in messages] == [
        "author",
        "agent",
        "system",
        "agent",
        "agent",
    ]
    assert messages[0]["actor"] == "作者"
    assert messages[0]["content"] == "我们写一个侦探故事"
    assert messages[0]["payload"] == {}
    assert messages[1]["actor"] == "总编"
    assert messages[1]["content"] == "（模拟回复）"
    assert messages[2]["payload"]["kind"] == "mood_change"
    assert messages[3]["actor"] == "责编"
    assert messages[3]["content"].startswith("我想先确认一下")
    assert messages[3]["payload"]["kind"] == "proactive_question"
    assert messages[4]["actor"] == "总编"
    assert messages[4]["payload"]["kind"] == "proactive_direction"
    for message in messages:
        assert set(message) == {
            "id",
            "role",
            "actor",
            "content",
            "payload",
            "created_at",
        }

    second = client.post(f"/works/{workspace_id}/talk", json={"message": "第二条"})
    assert second.status_code == 201
    second_messages = second.json()["messages"]
    assert [message["role"] for message in second_messages] == ["author", "agent"]
    assert second_messages[1]["content"] == "（模拟回复）"


def test_talk_send_refusal_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "立场之书"}).json()["id"]
    response = client.post(
        f"/works/{workspace_id}/talk", json={"message": "@责编 删掉钩子"}
    )
    assert response.status_code == 201
    messages = response.json()["messages"]
    assert messages[0]["content"] == "@责编 删掉钩子"
    refusal = messages[1]
    assert refusal["payload"]["kind"] == "refusal"
    assert refusal["payload"]["rule"] == "editor_hooks"
    assert "钩子" in refusal["content"]


def test_talk_send_unknown_alias_and_missing_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "别名之书"}).json()["id"]

    invalid = client.post(
        f"/works/{workspace_id}/talk", json={"message": "@主编大人 你好"}
    )
    assert invalid.status_code == 422
    assert "unknown partner alias" in invalid.json()["detail"]

    missing = client.post("/works/missing/talk", json={"message": "你好"})
    assert missing.status_code == 404
    assert missing.json() == {"detail": "workspace not found: missing"}


def test_talk_send_rejects_empty_or_blank_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P3-2: blank messages are a 422 usage error with no DB or LLM side effects."""

    def llm_must_not_run(*args, **kwargs) -> None:
        raise AssertionError("LLM must not be called for a blank message")

    monkeypatch.setattr(api_app, "build_client", llm_must_not_run)
    client, db = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "空消息之书"}).json()["id"]
    before_counts = _table_counts(db, workspace_id)

    for message in ("", "   ", "\t\n "):
        response = client.post(
            f"/works/{workspace_id}/talk", json={"message": message}
        )
        assert response.status_code == 422, repr(message)
        text = _detail_text(response.json()["detail"])
        assert "message" in text
        assert "whitespace-only" in text or "at least 1 character" in text

    assert _table_counts(db, workspace_id) == before_counts


def test_talk_list_renders_like_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_llm(monkeypatch, reply="（模拟回复）")
    client, _ = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "回放之书"}).json()["id"]
    client.post(f"/works/{workspace_id}/talk", json={"message": "我们写一个侦探故事"})

    response = client.get(f"/works/{workspace_id}/talk")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 5
    for item in items:
        assert set(item) == {
            "id",
            "role",
            "actor",
            "content",
            "payload",
            "created_at",
            "mark",
            "line",
        }
    assert items[0]["mark"] is None
    assert items[0]["line"] == "[author] 作者: 我们写一个侦探故事"
    assert items[1]["line"] == "[agent] 总编: （模拟回复）"
    assert items[2]["mark"] is None
    assert items[2]["line"].startswith("[system] 总编: 总编 的状态从")
    assert items[3]["mark"] == "agent·主动·proactive_question"
    assert items[4]["mark"] == "agent·主动·proactive_direction"


def test_draft_generate_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_llm(monkeypatch, reply="正文内容")
    client, _ = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "生成之书"}).json()["id"]

    response = client.post(f"/works/{workspace_id}/drafts", json={})
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {
        "id",
        "title",
        "status",
        "current_version",
        "updated_at",
        "awaiting_decision",
    }
    assert body["title"] == "未命名章节"
    assert body["status"] == "draft"
    assert body["current_version"] == 1
    assert body["awaiting_decision"] is True

    detail = client.get(f"/works/{workspace_id}/drafts/{body['id']}").json()
    assert detail["versions"][0]["content"] == "正文内容"
    assert detail["versions"][0]["reason"] == "initial"

    pending = client.get(f"/works/{workspace_id}/pending").json()
    assert [item["id"] for item in pending] == [body["id"]]


def test_draft_generate_writer_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_llm(monkeypatch, reply="正文内容")
    client, _ = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "写手校验"}).json()["id"]

    non_writer = client.post(
        f"/works/{workspace_id}/drafts", json={"writer": "责编"}
    )
    assert non_writer.status_code == 422
    assert "not a writer" in non_writer.json()["detail"]

    unknown = client.post(f"/works/{workspace_id}/drafts", json={"writer": "路人"})
    assert unknown.status_code == 404
    assert "agent not found" in unknown.json()["detail"]


def test_draft_revise_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    replies = ["初稿内容", "修订稿内容", "（未使用）"]
    monkeypatch.setattr(
        "novel_editorial.api.app.build_client",
        lambda settings: MockLLMClient(reply=replies.pop(0)),
    )
    client, _ = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "修订之书"}).json()["id"]
    draft_id = client.post(
        f"/works/{workspace_id}/drafts", json={"title": "第一章"}
    ).json()["id"]

    revised = client.post(
        f"/works/{workspace_id}/drafts/{draft_id}/revise",
        json={"reason": "收钩子"},
    )
    assert revised.status_code == 200
    body = revised.json()
    assert body["id"] == draft_id
    assert body["current_version"] == 2
    assert body["status"] == "draft"
    assert body["awaiting_decision"] is True

    detail = client.get(f"/works/{workspace_id}/drafts/{draft_id}").json()
    assert [version["content"] for version in detail["versions"]] == [
        "初稿内容",
        "修订稿内容",
    ]
    assert detail["versions"][1]["reason"] == "收钩子"

    missing = client.post(
        f"/works/{workspace_id}/drafts/does-not-exist/revise", json={}
    )
    assert missing.status_code == 404
    assert missing.json() == {"detail": "draft not found: does-not-exist"}


def test_author_draft_new_and_save_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "作者写作之书"}).json()["id"]

    created = client.post(
        f"/works/{workspace_id}/drafts/new", json={"title": "第一章"}
    )
    assert created.status_code == 201
    body = created.json()
    assert set(body) == {
        "id",
        "title",
        "status",
        "current_version",
        "updated_at",
        "awaiting_decision",
    }
    assert body["title"] == "第一章"
    assert body["status"] == "draft"
    assert body["current_version"] == 0
    assert body["awaiting_decision"] is True
    draft_id = body["id"]

    detail = client.get(f"/works/{workspace_id}/drafts/{draft_id}").json()
    assert detail["current_version"] == 0
    assert detail["versions"] == []

    saved = client.put(
        f"/works/{workspace_id}/drafts/{draft_id}/content",
        json={"content": "雨夜，她推开旧车站的门。", "reason": "初稿"},
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["id"] == draft_id
    assert body["current_version"] == 1
    assert body["status"] == "draft"
    assert body["awaiting_decision"] is True

    detail = client.get(f"/works/{workspace_id}/drafts/{draft_id}").json()
    assert len(detail["versions"]) == 1
    version = detail["versions"][0]
    assert version["version"] == 1
    assert version["content"] == "雨夜，她推开旧车站的门。"
    assert version["reason"] == "初稿"
    assert version["actor"] == "作者"

    pending = client.get(f"/works/{workspace_id}/pending").json()
    assert [item["id"] for item in pending] == [draft_id]


def test_author_draft_validation_and_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "校验之书"}).json()["id"]

    blank_title = client.post(
        f"/works/{workspace_id}/drafts/new", json={"title": "   "}
    )
    assert blank_title.status_code == 422
    assert "title" in _detail_text(blank_title.json()["detail"])

    draft_id = client.post(
        f"/works/{workspace_id}/drafts/new", json={"title": "第一章"}
    ).json()["id"]

    blank_content = client.put(
        f"/works/{workspace_id}/drafts/{draft_id}/content",
        json={"content": " \n "},
    )
    assert blank_content.status_code == 422
    assert "content" in _detail_text(blank_content.json()["detail"])

    missing = client.put(
        f"/works/{workspace_id}/drafts/does-not-exist/content",
        json={"content": "正文"},
    )
    assert missing.status_code == 404
    assert missing.json() == {"detail": "draft not found: does-not-exist"}

    with db.workspace_session(workspace_id) as session:
        accepted = Draft(
            workspace_id=workspace_id,
            title="已过",
            status="accepted",
            current_version=1,
        )
        session.add(accepted)
        session.commit()
        accepted_id = accepted.id
    blocked = client.put(
        f"/works/{workspace_id}/drafts/{accepted_id}/content",
        json={"content": "正文"},
    )
    assert blocked.status_code == 422
    assert "cannot revise an accepted draft" in blocked.json()["detail"]

    monkeypatch.setattr(
        "novel_editorial.api.app.build_client",
        lambda settings: MockLLMClient(reply="不该被调用"),
    )
    revised_v0 = client.post(
        f"/works/{workspace_id}/drafts/{draft_id}/revise",
        json={"reason": "改"},
    )
    assert revised_v0.status_code == 422
    assert "cannot revise a draft with no content" in revised_v0.json()["detail"]


def test_draft_decisions_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "拍板记录"}).json()["id"]
    first_id = _seed_draft(db, workspace_id, title="第一章")
    second_id = _seed_draft(db, workspace_id, title="第二章")
    _seed_draft(db, workspace_id, title="第三章")

    empty = client.get(f"/works/{workspace_id}/drafts/{first_id}/decisions")
    assert empty.status_code == 200
    assert empty.json() == []

    accepted = client.post(
        f"/works/{workspace_id}/decisions",
        json={"draft_id": first_id, "action": "accept"},
    )
    assert accepted.status_code == 201
    rejected = client.post(
        f"/works/{workspace_id}/decisions",
        json={"draft_id": second_id, "action": "reject"},
    )
    assert rejected.status_code == 201
    noted = client.post(
        f"/works/{workspace_id}/decisions",
        json={"draft_id": second_id, "action": "note", "content": "补充说明"},
    )
    assert noted.status_code == 201

    decisions = client.get(f"/works/{workspace_id}/drafts/{second_id}/decisions")
    assert decisions.status_code == 200
    body = decisions.json()
    assert [item["action"] for item in body] == ["reject", "note"]
    for item in body:
        assert set(item) == {
            "id",
            "draft_id",
            "action",
            "actor",
            "content",
            "created_at",
        }
        assert item["draft_id"] == second_id
        assert item["actor"] == "作者"
    assert body[1]["content"] == "补充说明"

    missing = client.get(f"/works/{workspace_id}/drafts/does-not-exist/decisions")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "draft not found: does-not-exist"}


def test_review_add_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "意见之书"}).json()["id"]
    draft_id = _seed_draft(db, workspace_id)

    response = client.post(
        f"/works/{workspace_id}/reviews",
        json={"draft_id": draft_id, "source": "责编", "content": "退稿：钩子不成立"},
    )
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "role", "actor", "content", "created_at"}
    assert body["role"] == "agent"
    assert body["actor"] == "责编"
    assert body["content"] == "退稿：钩子不成立"

    author = client.post(
        f"/works/{workspace_id}/reviews",
        json={"draft_id": draft_id, "source": "作者", "content": "方向没问题"},
    )
    assert author.status_code == 201
    assert author.json()["role"] == "author"
    assert author.json()["actor"] == "作者"

    listed = client.get(
        f"/works/{workspace_id}/reviews", params={"draft_id": draft_id}
    ).json()
    assert [item["actor"] for item in listed] == ["责编", "作者"]

    unknown = client.post(
        f"/works/{workspace_id}/reviews",
        json={"draft_id": draft_id, "source": "路人", "content": "x"},
    )
    assert unknown.status_code == 422
    assert "unknown reviewer alias" in unknown.json()["detail"]

    missing = client.post(
        f"/works/{workspace_id}/reviews",
        json={"draft_id": "does-not-exist", "source": "作者", "content": "x"},
    )
    assert missing.status_code == 404
    assert missing.json() == {"detail": "draft not found: does-not-exist"}


def test_review_add_rejects_empty_or_blank_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P3-2: blank review content is a 422 usage error and nothing is stored."""
    client, db = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "空意见之书"}).json()["id"]
    draft_id = _seed_draft(db, workspace_id)
    before_counts = _table_counts(db, workspace_id)

    for content in ("", "  ", "\n\t"):
        response = client.post(
            f"/works/{workspace_id}/reviews",
            json={"draft_id": draft_id, "source": "责编", "content": content},
        )
        assert response.status_code == 422, repr(content)
        text = _detail_text(response.json()["detail"])
        assert "content" in text
        assert "whitespace-only" in text or "at least 1 character" in text

    assert _table_counts(db, workspace_id) == before_counts


def test_style_set_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "风格之书"}).json()["id"]

    response = client.post(
        f"/works/{workspace_id}/style",
        json={"description": "冷峻克制", "forbidden": "宛如、仿佛"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "description": "冷峻克制",
        "forbidden_words": "宛如、仿佛",
    }

    fetched = client.get(f"/works/{workspace_id}/style").json()
    assert fetched == {"description": "冷峻克制", "forbidden_words": "宛如、仿佛"}

    # Like ``style set``, the API route fires the reviewer consistency message.
    talk = client.get(f"/works/{workspace_id}/talk").json()
    assert any(
        item["payload"].get("kind") == "proactive_consistency" for item in talk
    )

    overwrite = client.post(f"/works/{workspace_id}/style", json={"description": "平实"})
    assert overwrite.status_code == 200
    assert overwrite.json() == {"description": "平实", "forbidden_words": ""}


def test_new_read_routes_are_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "只读新路由"}).json()["id"]
    draft_id = _seed_draft(db, workspace_id, title="第一章")
    noted = client.post(
        f"/works/{workspace_id}/decisions",
        json={"draft_id": draft_id, "action": "note", "content": "先记一笔"},
    )
    assert noted.status_code == 201

    before_counts = _table_counts(db, workspace_id)
    events_before = client.get(f"/works/{workspace_id}/events").json()

    for url in (
        "/templates",
        f"/works/{workspace_id}/talk",
        f"/works/{workspace_id}/drafts/{draft_id}/decisions",
        f"/works/{workspace_id}/drafts/{draft_id}/diff?version_a=1&version_b=1",
        f"/works/{workspace_id}/outline",
        f"/works/{workspace_id}/settings",
        f"/works/{workspace_id}/settings/check",
        f"/works/{workspace_id}/inspirations",
    ):
        response = client.get(url)
        assert response.status_code == 200, url

    assert _table_counts(db, workspace_id) == before_counts
    assert client.get(f"/works/{workspace_id}/events").json() == events_before


def test_sse_stream_replays_events_with_rowid_cursor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server, thread, port = _start_api_server(tmp_path, monkeypatch)
    db = DB(load_settings())
    with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10) as http:
        workspace_id = http.post("/works", json={"title": "事件流之书"}).json()["id"]
    try:
        record_event(
            db,
            workspace_id,
            type=EventType.SYSTEM,
            actor="system",
            payload={"n": 1},
        )
        record_event(
            db,
            workspace_id,
            type=EventType.SYSTEM,
            actor="system",
            payload={"n": 2},
        )
        records = list_events_since(db, workspace_id)
        rowids = [record.rowid for record in records]
        assert len(rowids) == 2

        url = f"http://127.0.0.1:{port}/works/{workspace_id}/events/stream"
        with httpx.Client(timeout=10) as http:
            with http.stream("GET", url) as response:
                assert response.status_code == 200
                assert response.headers["content-type"].startswith(
                    "text/event-stream"
                )
                ids: list[str] = []
                data_lines: list[str] = []
                for line in response.iter_lines():
                    if line.startswith("id:"):
                        ids.append(line[3:].strip())
                    elif line.startswith("data:"):
                        data_lines.append(line[5:].strip())
                        if len(data_lines) == 2:
                            break

        assert ids == [str(rowids[0]), str(rowids[1])]
        events = [json.loads(line) for line in data_lines]
        assert [event["payload"]["n"] for event in events] == [1, 2]
        for event in events:
            assert set(event) == {
                "id",
                "workspace_id",
                "type",
                "time",
                "actor",
                "payload",
            }
            assert event["workspace_id"] == workspace_id
    finally:
        _stop_api_server(server, thread)


def test_sse_resumes_strictly_after_last_event_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server, thread, port = _start_api_server(tmp_path, monkeypatch)
    db = DB(load_settings())
    with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10) as http:
        workspace_id = http.post("/works", json={"title": "续传之书"}).json()["id"]
    try:
        for n in (1, 2, 3):
            record_event(
                db,
                workspace_id,
                type=EventType.SYSTEM,
                actor="system",
                payload={"n": n},
            )
        records = list_events_since(db, workspace_id)
        assert [
            json.loads(record.event.payload)["n"] for record in records
        ] == [1, 2, 3]
        cursor = records[1].rowid

        url = f"http://127.0.0.1:{port}/works/{workspace_id}/events/stream"
        with httpx.Client(timeout=10) as http:
            with http.stream("GET", url, headers={"Last-Event-ID": str(cursor)}) as response:
                assert response.status_code == 200
                ids: list[str] = []
                data_lines: list[str] = []
                for line in response.iter_lines():
                    if line.startswith("id:"):
                        ids.append(line[3:].strip())
                    elif line.startswith("data:"):
                        data_lines.append(line[5:].strip())
                        if len(data_lines) == 1:
                            break

        assert ids == [str(records[2].rowid)]
        event = json.loads(data_lines[0])
        assert event["payload"] == {"n": 3}
        assert event["id"] == records[2].event.id
    finally:
        _stop_api_server(server, thread)


def test_sse_sends_heartbeat_comments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(api_app, "SSE_HEARTBEAT_SECONDS", 0.2)
    server, thread, port = _start_api_server(tmp_path, monkeypatch)
    with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10) as http:
        workspace_id = http.post("/works", json={"title": "心跳之书"}).json()["id"]
    try:
        url = f"http://127.0.0.1:{port}/works/{workspace_id}/events/stream"
        with httpx.Client(timeout=10) as http:
            with http.stream("GET", url) as response:
                pings: list[str] = []
                seen = 0
                for line in response.iter_lines():
                    seen += 1
                    if line.startswith(": ping"):
                        pings.append(line)
                        if len(pings) >= 2:
                            break
                    if seen > 200:
                        break

        assert len(pings) >= 2
    finally:
        _stop_api_server(server, thread)


def test_sse_poll_query_runs_off_event_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P3-1: a slow events query must not block heartbeats or other requests."""
    real_list_events_since = api_app.list_events_since

    def slow_list_events_since(
        db: DB, workspace_id: str, *, after_rowid: int | None = None
    ) -> list[EventRecord]:
        time.sleep(1.2)
        return real_list_events_since(db, workspace_id, after_rowid=after_rowid)

    monkeypatch.setattr(api_app, "list_events_since", slow_list_events_since)
    server, thread, port = _start_api_server(tmp_path, monkeypatch)
    db = DB(load_settings())
    with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10) as http:
        workspace_id = http.post("/works", json={"title": "不卡循环之书"}).json()["id"]
    try:
        record_event(
            db,
            workspace_id,
            type=EventType.SYSTEM,
            actor="system",
            payload={"n": 1},
        )
        record_event(
            db,
            workspace_id,
            type=EventType.SYSTEM,
            actor="system",
            payload={"n": 2},
        )
        url = f"http://127.0.0.1:{port}/works/{workspace_id}/events/stream"
        with httpx.Client(timeout=10) as http:
            with http.stream("GET", url) as response:
                assert response.status_code == 200
                for line in response.iter_lines():
                    if line.startswith("data:"):
                        break
                with httpx.Client(
                    base_url=f"http://127.0.0.1:{port}", timeout=3
                ) as health:
                    for _ in range(2):
                        started = time.monotonic()
                        health_response = health.get("/health")
                        elapsed = time.monotonic() - started
                        assert health_response.status_code == 200
                        assert elapsed < 1.0, (
                            f"health check blocked for {elapsed:.2f}s"
                        )
    finally:
        _stop_api_server(server, thread)


def test_sse_missing_workspace_returns_404(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    response = client.get("/works/missing/events/stream")
    assert response.status_code == 404
    assert response.json() == {"detail": "workspace not found: missing"}


def test_cli_api_contract_talk_send(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_llm(monkeypatch, reply="（模拟回复）")
    client, _ = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "同源对话"}).json()["id"]

    api_round = client.post(
        f"/works/{workspace_id}/talk", json={"message": "我们写一个侦探故事"}
    )
    assert api_round.status_code == 201
    api_messages = api_round.json()["messages"]
    assert [message["role"] for message in api_messages] == [
        "author",
        "agent",
        "system",
        "agent",
        "agent",
    ]
    assert api_messages[1]["content"] == "（模拟回复）"

    cli_round = runner.invoke(
        cli_app, ["talk", "send", workspace_id, "第二条消息"]
    )
    assert cli_round.exit_code == 0, cli_round.output
    assert "作者: 第二条消息" in cli_round.output
    assert "总编: （模拟回复）" in cli_round.output

    api_list = client.get(f"/works/{workspace_id}/talk").json()
    cli_list = runner.invoke(cli_app, ["talk", "list", workspace_id])
    assert cli_list.exit_code == 0, cli_list.output
    expected_lines = cli_list.output.strip().splitlines()
    assert [item["line"] for item in api_list] == expected_lines


def test_cli_api_contract_draft_generate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_llm(monkeypatch, reply="正文内容")
    client, _ = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "同源草稿"}).json()["id"]

    cli_created = runner.invoke(
        cli_app, ["draft", "generate", workspace_id, "--title", "第一章"]
    )
    assert cli_created.exit_code == 0, cli_created.output
    cli_draft_id = cli_created.output.split()[1]

    api_created = client.post(
        f"/works/{workspace_id}/drafts", json={"title": "第二章"}
    )
    assert api_created.status_code == 201
    api_draft = api_created.json()
    assert api_draft["title"] == "第二章"
    assert api_draft["status"] == "draft"
    assert api_draft["current_version"] == 1
    assert api_draft["awaiting_decision"] is True

    api_detail = client.get(
        f"/works/{workspace_id}/drafts/{api_draft['id']}"
    ).json()
    assert api_detail["versions"][0]["content"] == "正文内容"
    cli_show = runner.invoke(cli_app, ["draft", "show", cli_draft_id])
    assert cli_show.exit_code == 0, cli_show.output
    assert "正文内容" in cli_show.output

    api_drafts = client.get(f"/works/{workspace_id}/drafts").json()
    cli_list = runner.invoke(cli_app, ["draft", "list", workspace_id])
    assert cli_list.exit_code == 0, cli_list.output
    assert len(api_drafts) == 2
    for item in api_drafts:
        assert item["id"] in cli_list.output
        assert item["status"] in cli_list.output

    api_pending = client.get(f"/works/{workspace_id}/pending").json()
    assert {item["id"] for item in api_pending} == {
        cli_draft_id,
        api_draft["id"],
    }
    cli_pending = runner.invoke(cli_app, ["decision", "pending", workspace_id])
    assert cli_pending.exit_code == 0, cli_pending.output
    assert cli_draft_id in cli_pending.output
    assert api_draft["id"] in cli_pending.output


def test_cli_api_contract_author_draft(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "同源手写"}).json()["id"]

    cli_new = runner.invoke(
        cli_app, ["draft", "new", workspace_id, "--title", "第一章"]
    )
    assert cli_new.exit_code == 0, cli_new.output
    assert "now at v0" in cli_new.output
    assert "awaiting decision" in cli_new.output
    cli_draft_id = cli_new.output.split()[1]

    api_new = client.post(
        f"/works/{workspace_id}/drafts/new", json={"title": "第二章"}
    )
    assert api_new.status_code == 201
    api_draft = api_new.json()
    assert api_draft["current_version"] == 0

    cli_saved = runner.invoke(
        cli_app,
        ["draft", "save", cli_draft_id, "--content", "作者亲笔", "--reason", "初稿"],
    )
    assert cli_saved.exit_code == 0, cli_saved.output
    assert "now at v1" in cli_saved.output
    assert "awaiting decision" in cli_saved.output

    api_saved = client.put(
        f"/works/{workspace_id}/drafts/{api_draft['id']}/content",
        json={"content": "界面手稿"},
    )
    assert api_saved.status_code == 200
    assert api_saved.json()["current_version"] == 1

    api_drafts = client.get(f"/works/{workspace_id}/drafts").json()
    cli_list = runner.invoke(cli_app, ["draft", "list", workspace_id])
    assert cli_list.exit_code == 0, cli_list.output
    assert len(api_drafts) == 2
    for item in api_drafts:
        assert item["id"] in cli_list.output
        assert item["status"] in cli_list.output

    cli_detail = runner.invoke(cli_app, ["draft", "show", cli_draft_id])
    assert cli_detail.exit_code == 0, cli_detail.output
    assert "作者亲笔" in cli_detail.output
    api_detail = client.get(
        f"/works/{workspace_id}/drafts/{api_draft['id']}"
    ).json()
    assert api_detail["versions"][0]["actor"] == "作者"


def test_cli_api_contract_review_add(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_llm(monkeypatch, reply="正文内容")
    client, _ = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "同源意见"}).json()["id"]
    draft_id = client.post(
        f"/works/{workspace_id}/drafts", json={"title": "第一章"}
    ).json()["id"]

    cli_added = runner.invoke(
        cli_app,
        [
            "review",
            "add",
            draft_id,
            "--from",
            "责编",
            "--content",
            "退稿：钩子不成立",
        ],
    )
    assert cli_added.exit_code == 0, cli_added.output

    api_added = client.post(
        f"/works/{workspace_id}/reviews",
        json={"draft_id": draft_id, "source": "作者", "content": "方向没问题"},
    )
    assert api_added.status_code == 201
    body = api_added.json()
    assert body["role"] == "author"
    assert body["actor"] == "作者"
    assert body["content"] == "方向没问题"

    api_reviews = client.get(
        f"/works/{workspace_id}/reviews", params={"draft_id": draft_id}
    ).json()
    cli_reviews = runner.invoke(cli_app, ["review", "list", draft_id])
    assert cli_reviews.exit_code == 0, cli_reviews.output
    expected_lines = cli_reviews.output.strip().splitlines()
    assert [
        f"[{item['role']}] {item['actor']}: {item['content']}"
        for item in api_reviews
    ] == expected_lines


def test_cli_api_contract_decision_accept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_llm(monkeypatch, reply="正文内容")
    client, _ = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "同源拍板"}).json()["id"]
    draft_id = client.post(
        f"/works/{workspace_id}/drafts", json={"title": "第一章"}
    ).json()["id"]

    cli_accepted = runner.invoke(cli_app, ["decision", "accept", draft_id])
    assert cli_accepted.exit_code == 0, cli_accepted.output
    assert "accepted" in cli_accepted.output

    api_pending = client.get(f"/works/{workspace_id}/pending").json()
    assert api_pending == []
    cli_pending = runner.invoke(cli_app, ["decision", "pending", workspace_id])
    assert cli_pending.exit_code == 0, cli_pending.output
    assert "no pending decisions" in cli_pending.output

    api_decisions = client.get(
        f"/works/{workspace_id}/drafts/{draft_id}/decisions"
    ).json()
    assert len(api_decisions) == 1
    assert api_decisions[0]["action"] == "accept"
    assert api_decisions[0]["actor"] == "作者"
    assert api_decisions[0]["content"] == ""

    cli_decisions = runner.invoke(cli_app, ["decision", "list", draft_id])
    assert cli_decisions.exit_code == 0, cli_decisions.output
    assert "[accept] 作者" in cli_decisions.output

    api_drafts = client.get(f"/works/{workspace_id}/drafts").json()
    assert [item["status"] for item in api_drafts] == ["accepted"]
    cli_drafts = runner.invoke(cli_app, ["draft", "list", workspace_id])
    assert cli_drafts.exit_code == 0, cli_drafts.output
    assert "accepted" in cli_drafts.output


def test_cli_api_contract_style_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_llm(monkeypatch, reply="（模拟回复）")
    client, _ = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "同源风格"}).json()["id"]

    cli_styled = runner.invoke(
        cli_app,
        [
            "style",
            "set",
            workspace_id,
            "--description",
            "冷峻克制",
            "--forbidden",
            "宛如、仿佛",
        ],
    )
    assert cli_styled.exit_code == 0, cli_styled.output

    api_styled = client.post(
        f"/works/{workspace_id}/style",
        json={"description": "平实短句", "forbidden": "不禁"},
    )
    assert api_styled.status_code == 200
    assert api_styled.json() == {"description": "平实短句", "forbidden_words": "不禁"}

    api_style = client.get(f"/works/{workspace_id}/style").json()
    assert api_style == {"description": "平实短句", "forbidden_words": "不禁"}
    cli_show = runner.invoke(cli_app, ["style", "show", workspace_id])
    assert cli_show.exit_code == 0, cli_show.output
    assert "description: 平实短句" in cli_show.output
    assert "forbidden: 不禁" in cli_show.output


def test_cli_api_contract_draft_diff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "同源对比"}).json()["id"]
    draft_id = client.post(
        f"/works/{workspace_id}/drafts/new", json={"title": "第一章"}
    ).json()["id"]
    client.put(
        f"/works/{workspace_id}/drafts/{draft_id}/content",
        json={"content": "雨夜，她推开旧车站的门。", "reason": "初稿"},
    )
    client.put(
        f"/works/{workspace_id}/drafts/{draft_id}/content",
        json={"content": "雨夜，她推开旧车站的门，门轴锈住了。", "reason": "打磨"},
    )

    api_diff = client.get(
        f"/works/{workspace_id}/drafts/{draft_id}/diff",
        params={"version_a": 1, "version_b": 2},
    )
    assert api_diff.status_code == 200
    assert api_diff.headers["content-type"].startswith("text/plain")
    cli_diff = runner.invoke(cli_app, ["draft", "diff", draft_id, "1", "2"])
    assert cli_diff.exit_code == 0, cli_diff.output
    assert api_diff.text.splitlines() == cli_diff.output.strip().splitlines()

    api_same = client.get(
        f"/works/{workspace_id}/drafts/{draft_id}/diff",
        params={"version_a": 1, "version_b": 1},
    )
    assert api_same.status_code == 200
    assert api_same.text == "no differences"
    cli_same = runner.invoke(cli_app, ["draft", "diff", draft_id, "1", "1"])
    assert cli_same.exit_code == 0, cli_same.output
    assert cli_same.output.strip() == "no differences"

    missing = client.get(
        f"/works/{workspace_id}/drafts/{draft_id}/diff",
        params={"version_a": 1, "version_b": 99},
    )
    assert missing.status_code == 404
    cli_missing = runner.invoke(cli_app, ["draft", "diff", draft_id, "1", "99"])
    assert cli_missing.exit_code == 1
    assert "draft version not found" in cli_missing.output
    assert "draft version not found" in missing.json()["detail"]


def test_cli_api_contract_structure_add_rename_status_move_remove(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "同源结构"}).json()["id"]

    cli_volume = runner.invoke(
        cli_app, ["structure", "add", workspace_id, "卷", "第一卷"]
    )
    assert cli_volume.exit_code == 0, cli_volume.output
    volume_id = cli_volume.output.split()[1]
    assert cli_volume.output.strip() == f"created {volume_id} volume 第一卷"

    api_chapter = client.post(
        f"/works/{workspace_id}/structure",
        json={"kind": "chapter", "title": "第一章", "parent": volume_id},
    )
    assert api_chapter.status_code == 201
    chapter = api_chapter.json()
    assert set(chapter) == {
        "id",
        "kind",
        "title",
        "parent_id",
        "sort_order",
        "status",
        "draft_id",
        "created_at",
    }
    assert chapter["kind"] == "chapter"
    assert chapter["title"] == "第一章"
    assert chapter["parent_id"] == volume_id
    assert chapter["sort_order"] == 1

    cli_section = runner.invoke(
        cli_app,
        [
            "structure",
            "add",
            workspace_id,
            "篇目",
            "第一节",
            "--parent",
            chapter["id"],
        ],
    )
    assert cli_section.exit_code == 0, cli_section.output
    section_id = cli_section.output.split()[1]

    api_list = client.get(f"/works/{workspace_id}/structure").json()
    assert [node["id"] for node in api_list] == [volume_id, chapter["id"], section_id]
    cli_list = runner.invoke(cli_app, ["structure", "list", workspace_id])
    assert cli_list.exit_code == 0, cli_list.output
    assert cli_list.output.splitlines() == [
        f"[卷] 第一卷（{volume_id}）",
        f"  [章] 第一章（{chapter['id']}）",
        f"    [篇目] 第一节（{section_id}）",
    ]

    events = client.get(f"/works/{workspace_id}/events").json()
    created_kinds = {
        event["payload"].get("kind")
        for event in events
        if event["payload"].get("kind", "").startswith("structure_")
    }
    assert "structure_created" in created_kinds

    renamed = client.patch(
        f"/works/{workspace_id}/structure/{chapter['id']}",
        json={"title": "新第一章"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "新第一章"

    statused = client.patch(
        f"/works/{workspace_id}/structure/{chapter['id']}",
        json={"status": "completed"},
    )
    assert statused.status_code == 200
    assert statused.json()["status"] == "completed"

    cli_status = runner.invoke(
        cli_app, ["structure", "status", workspace_id, chapter["id"], "创作中"]
    )
    assert cli_status.exit_code == 0, cli_status.output
    api_after_status = client.get(f"/works/{workspace_id}/structure").json()
    chapter_status = next(
        node["status"]
        for node in api_after_status
        if node["id"] == chapter["id"]
    )
    assert chapter_status == "writing"

    moved = client.post(
        f"/works/{workspace_id}/structure/{chapter['id']}/move", json={"root": True}
    )
    assert moved.status_code == 200
    assert moved.json()["parent_id"] is None

    moved_back = client.post(
        f"/works/{workspace_id}/structure/{chapter['id']}/move",
        json={"parent": volume_id, "order": 1},
    )
    assert moved_back.status_code == 200
    assert moved_back.json()["parent_id"] == volume_id
    assert moved_back.json()["sort_order"] == 1

    removed = client.delete(f"/works/{workspace_id}/structure/{volume_id}")
    assert removed.status_code == 200
    assert removed.json() == {"removed": 3}
    assert client.get(f"/works/{workspace_id}/structure").json() == []
    cli_empty = runner.invoke(cli_app, ["structure", "list", workspace_id])
    assert cli_empty.exit_code == 0, cli_empty.output
    assert cli_empty.output.strip() == "no structure"


def test_structure_api_errors_match_cli_and_isolation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    workspace_a = client.post("/works", json={"title": "甲书"}).json()["id"]
    workspace_b = client.post("/works", json={"title": "乙书"}).json()["id"]

    invalid_kind = client.post(
        f"/works/{workspace_a}/structure", json={"kind": "book", "title": "书"}
    )
    assert invalid_kind.status_code == 422
    assert "invalid kind: book" in invalid_kind.json()["detail"]
    cli_invalid = runner.invoke(
        cli_app, ["structure", "add", workspace_a, "book", "书"]
    )
    assert cli_invalid.exit_code == 2
    assert "invalid kind: book" in cli_invalid.output

    blank_title = client.post(
        f"/works/{workspace_a}/structure", json={"kind": "chapter", "title": "   "}
    )
    assert blank_title.status_code == 422
    assert "node title must not be empty" in blank_title.json()["detail"]
    cli_blank = runner.invoke(
        cli_app, ["structure", "add", workspace_a, "chapter", "   "]
    )
    assert cli_blank.exit_code == 2
    assert "node title must not be empty" in cli_blank.output

    missing_parent = client.post(
        f"/works/{workspace_a}/structure",
        json={"kind": "chapter", "title": "孤儿", "parent": "missing"},
    )
    assert missing_parent.status_code == 404
    assert "structure node not found: missing" in missing_parent.json()["detail"]
    cli_missing_parent = runner.invoke(
        cli_app,
        ["structure", "add", workspace_a, "chapter", "孤儿", "--parent", "missing"],
    )
    assert cli_missing_parent.exit_code == 1

    volume = client.post(
        f"/works/{workspace_a}/structure", json={"kind": "volume", "title": "卷"}
    ).json()
    foreign = client.post(
        f"/works/{workspace_a}/structure",
        json={"kind": "chapter", "title": "章", "parent": volume["id"]},
    ).json()

    conflict = client.post(
        f"/works/{workspace_a}/structure/{foreign['id']}/move",
        json={"parent": volume["id"], "root": True},
    )
    assert conflict.status_code == 422
    assert "mutually exclusive" in conflict.json()["detail"]
    cli_conflict = runner.invoke(
        cli_app,
        [
            "structure",
            "move",
            workspace_a,
            foreign["id"],
            "--parent",
            volume["id"],
            "--root",
        ],
    )
    assert cli_conflict.exit_code == 2

    neither = client.patch(
        f"/works/{workspace_a}/structure/{foreign['id']}", json={}
    )
    assert neither.status_code == 422
    both = client.patch(
        f"/works/{workspace_a}/structure/{foreign['id']}",
        json={"title": "x", "status": "completed"},
    )
    assert both.status_code == 422

    missing_node = client.patch(
        f"/works/{workspace_a}/structure/missing", json={"title": "x"}
    )
    assert missing_node.status_code == 404
    assert "structure node not found: missing" in missing_node.json()["detail"]
    assert (
        client.delete(f"/works/{workspace_a}/structure/missing").status_code == 404
    )

    cross_patch = client.patch(
        f"/works/{workspace_b}/structure/{foreign['id']}", json={"title": "x"}
    )
    assert cross_patch.status_code == 404
    cross_move = client.post(
        f"/works/{workspace_b}/structure/{foreign['id']}/move", json={"root": True}
    )
    assert cross_move.status_code == 404
    cross_delete = client.delete(
        f"/works/{workspace_b}/structure/{foreign['id']}"
    )
    assert cross_delete.status_code == 404
    assert client.get(f"/works/{workspace_b}/structure").json() == []


def test_cli_api_contract_outline_create_revise_show(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "同源大纲"}).json()["id"]

    cli_created = runner.invoke(
        cli_app,
        ["outline", "create", workspace_id, "--content", "楔子：雨夜车站", "--actor", "作者"],
    )
    assert cli_created.exit_code == 0, cli_created.output
    assert cli_created.output.strip() == "outline v1 created"

    api_show = client.get(f"/works/{workspace_id}/outline")
    assert api_show.status_code == 200
    created = api_show.json()
    assert created["version"] == 1
    assert created["content"] == "楔子：雨夜车站"
    assert created["actor"] == "作者"
    assert created["reason"] == "initial"
    assert created["workspace_id"] == workspace_id

    api_revised = client.post(
        f"/works/{workspace_id}/outline",
        json={
            "content": "楔子：雨夜车站，钟停十一点",
            "reason": "加悬念",
            "actor": "责编",
        },
    )
    assert api_revised.status_code == 200
    revised = api_revised.json()
    assert revised["version"] == 2
    assert revised["actor"] == "责编"

    cli_show = runner.invoke(cli_app, ["outline", "show", workspace_id])
    assert cli_show.exit_code == 0, cli_show.output
    assert cli_show.output.startswith("outline v2：")
    assert "钟停十一点" in cli_show.output

    cli_revised = runner.invoke(
        cli_app,
        [
            "outline",
            "revise",
            workspace_id,
            "--content",
            "楔子：雨夜车站，钟停十一点，列车误点",
            "--reason",
            "再打磨",
        ],
    )
    assert cli_revised.exit_code == 0, cli_revised.output
    api_after = client.get(f"/works/{workspace_id}/outline").json()
    assert api_after["version"] == 3
    assert "列车误点" in api_after["content"]


def test_outline_api_create_path_empty_state_and_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "大纲空态"}).json()["id"]

    empty = client.get(f"/works/{workspace_id}/outline")
    assert empty.status_code == 200
    assert empty.json() is None
    cli_empty = runner.invoke(cli_app, ["outline", "show", workspace_id])
    assert cli_empty.exit_code == 0, cli_empty.output
    assert cli_empty.output.strip() == "no outline"

    api_created = client.post(
        f"/works/{workspace_id}/outline", json={"content": "初版"}
    )
    assert api_created.status_code == 201
    assert api_created.json()["version"] == 1
    assert api_created.json()["actor"] == "作者"

    duplicated = client.post(
        f"/works/{workspace_id}/outline", json={"content": "重复"}
    )
    assert duplicated.status_code == 422
    assert "already exists" in duplicated.json()["detail"]
    cli_duplicated = runner.invoke(
        cli_app, ["outline", "create", workspace_id, "--content", "重复"]
    )
    assert cli_duplicated.exit_code == 2
    assert "already exists" in cli_duplicated.output

    other = client.post("/works", json={"title": "无大纲"}).json()["id"]
    revise_missing = client.post(
        f"/works/{other}/outline", json={"content": "内容", "reason": "理由"}
    )
    assert revise_missing.status_code == 404
    assert "outline not found" in revise_missing.json()["detail"]
    cli_revise_missing = runner.invoke(
        cli_app,
        ["outline", "revise", other, "--content", "内容", "--reason", "理由"],
    )
    assert cli_revise_missing.exit_code == 1
    assert "outline not found" in cli_revise_missing.output

    blank = client.post(f"/works/{workspace_id}/outline", json={"content": "   "})
    assert blank.status_code == 422
    assert "outline content must not be empty" in blank.json()["detail"]
    cli_blank = runner.invoke(
        cli_app, ["outline", "create", workspace_id, "--content", "   "]
    )
    assert cli_blank.exit_code == 2

    missing_ws = client.get("/works/missing/outline")
    assert missing_ws.status_code == 404
    assert "workspace not found: missing" in missing_ws.json()["detail"]


def test_cli_api_contract_setting_add_list_show_revise_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "同源设定"}).json()["id"]

    cli_added = runner.invoke(
        cli_app,
        [
            "setting",
            "add",
            workspace_id,
            "--kind",
            "人物",
            "--name",
            "沈夜",
            "--content",
            "雨夜归乡的侦探",
        ],
    )
    assert cli_added.exit_code == 0, cli_added.output
    cli_setting_id = cli_added.output.split()[1]
    assert cli_added.output.strip() == f"added {cli_setting_id} [人物] 沈夜 v1"

    api_added = client.post(
        f"/works/{workspace_id}/settings",
        json={"kind": "世界观", "name": "旧城", "content": "雨夜常驻"},
    )
    assert api_added.status_code == 201
    api_setting = api_added.json()
    assert api_setting["kind"] == "world"
    assert api_setting["name"] == "旧城"
    assert api_setting["content"] == "雨夜常驻"
    assert api_setting["source"] == "作者"
    assert api_setting["current_version"] == 1

    api_list = client.get(f"/works/{workspace_id}/settings").json()
    assert [entry["id"] for entry in api_list] == [cli_setting_id, api_setting["id"]]
    cli_list = runner.invoke(cli_app, ["setting", "list", workspace_id])
    assert cli_list.exit_code == 0, cli_list.output
    assert cli_list.output.splitlines() == [
        f"{cli_setting_id} [人物] 沈夜 v1 雨夜归乡的侦探",
        f"{api_setting['id']} [世界观] 旧城 v1 雨夜常驻",
    ]

    api_filtered = client.get(
        f"/works/{workspace_id}/settings", params={"kind": "人物"}
    ).json()
    assert [entry["id"] for entry in api_filtered] == [cli_setting_id]
    cli_filtered = runner.invoke(
        cli_app, ["setting", "list", workspace_id, "--kind", "人物"]
    )
    assert cli_filtered.exit_code == 0, cli_filtered.output
    assert [line.split()[0] for line in cli_filtered.output.splitlines()] == [
        cli_setting_id
    ]

    api_show = client.get(f"/works/{workspace_id}/settings/{api_setting['id']}")
    assert api_show.status_code == 200
    assert api_show.json()["content"] == "雨夜常驻"
    cli_show = runner.invoke(
        cli_app, ["setting", "show", workspace_id, cli_setting_id]
    )
    assert cli_show.exit_code == 0, cli_show.output
    assert "沈夜 [人物] v1" in cli_show.output

    api_revised = client.post(
        f"/works/{workspace_id}/settings",
        json={
            "setting_id": api_setting["id"],
            "content": "雨夜常驻三百年",
            "reason": "世界观扩展",
            "actor": "责编",
        },
    )
    assert api_revised.status_code == 200
    assert api_revised.json()["current_version"] == 2

    api_check = client.get(f"/works/{workspace_id}/settings/check")
    assert api_check.status_code == 200
    assert api_check.headers["content-type"].startswith("text/plain")
    cli_check = runner.invoke(cli_app, ["setting", "check", workspace_id])
    assert cli_check.exit_code == 0, cli_check.output
    assert api_check.text.splitlines() == cli_check.output.strip().splitlines()
    assert "settings: 2 entries (1 revised)" in api_check.text


def test_setting_api_errors_match_cli_and_isolation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    workspace_a = client.post("/works", json={"title": "甲书"}).json()["id"]
    workspace_b = client.post("/works", json={"title": "乙书"}).json()["id"]

    invalid_kind = client.post(
        f"/works/{workspace_a}/settings",
        json={"kind": "character", "name": "x", "content": "y"},
    )
    assert invalid_kind.status_code == 422
    assert "invalid kind: character" in invalid_kind.json()["detail"]
    cli_invalid = runner.invoke(
        cli_app,
        [
            "setting",
            "add",
            workspace_a,
            "--kind",
            "character",
            "--name",
            "x",
            "--content",
            "y",
        ],
    )
    assert cli_invalid.exit_code == 2
    assert "invalid kind: character" in cli_invalid.output

    blank_name = client.post(
        f"/works/{workspace_a}/settings",
        json={"kind": "人物", "name": "   ", "content": "y"},
    )
    assert blank_name.status_code == 422
    assert "setting name must not be empty" in blank_name.json()["detail"]
    blank_content = client.post(
        f"/works/{workspace_a}/settings",
        json={"kind": "人物", "name": "x", "content": "   "},
    )
    assert blank_content.status_code == 422
    assert "setting content must not be empty" in blank_content.json()["detail"]
    cli_blank = runner.invoke(
        cli_app,
        ["setting", "add", workspace_a, "--kind", "人物", "--name", "x", "--content", ""],
    )
    assert cli_blank.exit_code == 2

    missing_kind = client.post(
        f"/works/{workspace_a}/settings", json={"name": "x", "content": "y"}
    )
    assert missing_kind.status_code == 422
    assert "setting kind is required" in missing_kind.json()["detail"]
    missing_name = client.post(
        f"/works/{workspace_a}/settings", json={"kind": "人物", "content": "y"}
    )
    assert missing_name.status_code == 422
    assert "setting name is required" in missing_name.json()["detail"]

    entry = client.post(
        f"/works/{workspace_a}/settings",
        json={"kind": "人物", "name": "沈夜", "content": "甲书"},
    ).json()

    revise_missing = client.post(
        f"/works/{workspace_a}/settings",
        json={"setting_id": "f" * 32, "content": "x", "reason": "y"},
    )
    assert revise_missing.status_code == 404
    assert "setting not found" in revise_missing.json()["detail"]
    cli_revise_missing = runner.invoke(
        cli_app,
        ["setting", "revise", workspace_a, "f" * 32, "--content", "x", "--reason", "y"],
    )
    assert cli_revise_missing.exit_code == 1

    missing_reason = client.post(
        f"/works/{workspace_a}/settings",
        json={"setting_id": entry["id"], "content": "y"},
    )
    assert missing_reason.status_code == 422
    assert "setting reason is required" in missing_reason.json()["detail"]

    cross_show = client.get(f"/works/{workspace_b}/settings/{entry['id']}")
    assert cross_show.status_code == 404
    cross_revise = client.post(
        f"/works/{workspace_b}/settings",
        json={"setting_id": entry["id"], "content": "x", "reason": "y"},
    )
    assert cross_revise.status_code == 404
    assert client.get(f"/works/{workspace_b}/settings").json() == []

    invalid_filter = client.get(
        f"/works/{workspace_a}/settings", params={"kind": "teaser"}
    )
    assert invalid_filter.status_code == 422
    assert "invalid kind: teaser" in invalid_filter.json()["detail"]
    missing_ws = client.get("/works/missing/settings")
    assert missing_ws.status_code == 404
    assert "workspace not found: missing" in missing_ws.json()["detail"]


def test_cli_api_contract_inspiration_add_list_show_remove(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "同源灵感"}).json()["id"]

    cli_added = runner.invoke(
        cli_app,
        [
            "inspiration",
            "add",
            workspace_id,
            "--content",
            "码头雾气与旧钟",
            "--kind",
            "意象",
        ],
    )
    assert cli_added.exit_code == 0, cli_added.output
    cli_id = cli_added.output.split()[1]

    api_added = client.post(
        f"/works/{workspace_id}/inspirations",
        json={"content": "茶馆争吵", "kind": "场景", "source": "from the DAWN notebook"},
    )
    assert api_added.status_code == 201
    api_row = api_added.json()
    assert api_row["kind"] == "场景"
    assert api_row["source"] == "from the DAWN notebook"

    api_second = client.post(
        f"/works/{workspace_id}/inspirations",
        json={"content": "雨夜巷口的猫", "kind": "意象"},
    )
    assert api_second.status_code == 201
    api2_id = api_second.json()["id"]

    api_list = client.get(f"/works/{workspace_id}/inspirations").json()
    assert [row["id"] for row in api_list] == [api2_id, api_row["id"], cli_id]
    cli_list = runner.invoke(cli_app, ["inspiration", "list", workspace_id])
    assert cli_list.exit_code == 0, cli_list.output
    assert cli_list.output.splitlines() == [
        f"{api2_id} [意象] 雨夜巷口的猫",
        f"{api_row['id']} [场景] 茶馆争吵",
        f"{cli_id} [意象] 码头雾气与旧钟",
    ]

    api_kind = client.get(
        f"/works/{workspace_id}/inspirations", params={"kind": "意象"}
    ).json()
    assert [row["id"] for row in api_kind] == [api2_id, cli_id]
    api_keyword = client.get(
        f"/works/{workspace_id}/inspirations", params={"keyword": "DAWN"}
    ).json()
    assert [row["id"] for row in api_keyword] == [api_row["id"]]
    cli_keyword = runner.invoke(
        cli_app, ["inspiration", "list", workspace_id, "--keyword", "DAWN"]
    )
    assert cli_keyword.exit_code == 0, cli_keyword.output
    assert [line.split()[0] for line in cli_keyword.output.splitlines()] == [
        api_row["id"]
    ]

    api_show = client.get(f"/works/{workspace_id}/inspirations/{cli_id}")
    assert api_show.status_code == 200
    assert api_show.json()["content"] == "码头雾气与旧钟"
    assert api_show.json()["source"] == ""
    cli_show = runner.invoke(
        cli_app, ["inspiration", "show", workspace_id, cli_id]
    )
    assert cli_show.exit_code == 0, cli_show.output
    assert cli_show.output.splitlines() == [
        "kind: 意象",
        "content: 码头雾气与旧钟",
        "source: (empty)",
    ]

    removed = client.delete(f"/works/{workspace_id}/inspirations/{api2_id}")
    assert removed.status_code == 200
    assert removed.json() == {"id": api2_id, "kind": "意象"}
    api_after = client.get(f"/works/{workspace_id}/inspirations").json()
    assert [row["id"] for row in api_after] == [api_row["id"], cli_id]
    cli_after = runner.invoke(cli_app, ["inspiration", "list", workspace_id])
    assert cli_after.exit_code == 0, cli_after.output
    assert api2_id not in cli_after.output


def test_inspiration_api_errors_match_cli_and_isolation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    workspace_a = client.post("/works", json={"title": "甲书"}).json()["id"]
    workspace_b = client.post("/works", json={"title": "乙书"}).json()["id"]

    blank = client.post(f"/works/{workspace_a}/inspirations", json={"content": "   "})
    assert blank.status_code == 422
    assert "inspiration content must not be empty" in blank.json()["detail"]
    cli_blank = runner.invoke(
        cli_app, ["inspiration", "add", workspace_a, "--content", "   "]
    )
    assert cli_blank.exit_code == 2
    assert "inspiration content must not be empty" in cli_blank.output

    blank_kind = client.post(
        f"/works/{workspace_a}/inspirations", json={"content": "x", "kind": "  "}
    )
    assert blank_kind.status_code == 422
    assert "inspiration kind must not be empty" in blank_kind.json()["detail"]

    missing_ws = client.post("/works/missing/inspirations", json={"content": "x"})
    assert missing_ws.status_code == 404
    assert "workspace not found: missing" in missing_ws.json()["detail"]
    cli_missing_ws = runner.invoke(
        cli_app, ["inspiration", "add", "f" * 32, "--content", "无主灵感"]
    )
    assert cli_missing_ws.exit_code == 1

    row = client.post(
        f"/works/{workspace_a}/inspirations", json={"content": "北站的旧钟"}
    ).json()
    missing_show = client.get(
        f"/works/{workspace_a}/inspirations/missing-id"
    )
    assert missing_show.status_code == 404
    assert "inspiration not found: missing-id" in missing_show.json()["detail"]
    cli_missing_show = runner.invoke(
        cli_app, ["inspiration", "show", workspace_a, "a" * 32]
    )
    assert cli_missing_show.exit_code == 1

    cross_show = client.get(f"/works/{workspace_b}/inspirations/{row['id']}")
    assert cross_show.status_code == 404
    cross_delete = client.delete(f"/works/{workspace_b}/inspirations/{row['id']}")
    assert cross_delete.status_code == 404
    assert client.get(f"/works/{workspace_b}/inspirations").json() == []


# ---------------------------------------------------------------------------
# FE-W3-S1: quality / style / consistency / free-will read-face API contract
# ---------------------------------------------------------------------------


def _cli_text(result: Result) -> str:
    """Strip the trailing newline the CLI always appends (mixed stdout+stderr)."""
    return result.output.removesuffix("\n")


def test_cli_api_contract_quality_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "质量之书"}).json()["id"]
    set_style_anchor(
        db, workspace_id, description="克制、留白", forbidden_words="宛如"
    )
    draft_id = _seed_draft(db, workspace_id, content="雨夜开场。宛如轻纱笼罩。")

    api = client.get(
        f"/works/{workspace_id}/drafts/{draft_id}/quality/check"
    )
    assert api.status_code == 200
    assert api.headers["content-type"].startswith("text/plain")
    assert "passed: True" in api.text
    assert "score: 6.5 (threshold 8)" in api.text
    assert "ai word hits: ['宛如']" in api.text
    assert "style hits: 0/2 (consistency 0.00)" in api.text

    cli = runner.invoke(cli_app, ["quality", "check", draft_id])
    assert cli.exit_code == 0, cli.output
    assert api.text == _cli_text(cli)


def test_cli_api_contract_quality_explain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "定位之书"}).json()["id"]
    set_style_anchor(
        db, workspace_id, description="克制、留白", forbidden_words="宛如"
    )
    content = "雨夜开场，宛如轻纱。他静静站着。夜风很冷。夜风很冷。"
    draft_id = _seed_draft(db, workspace_id, content=content)

    api = client.get(
        f"/works/{workspace_id}/drafts/{draft_id}/quality/explain"
    )
    assert api.status_code == 200
    assert api.headers["content-type"].startswith("text/plain")
    assert "第一章 (v1)" in api.text
    assert "[AI 词命中]「宛如」 → 用具体比喻或直接写物象" in api.text
    assert "style: 命中 0/2；缺失：克制、留白" in api.text
    assert "good sentences: 句 1" in api.text
    assert "（感官细节，建议保留）" in api.text

    cli = runner.invoke(cli_app, ["quality", "explain", draft_id])
    assert cli.exit_code == 0, cli.output
    assert api.text == _cli_text(cli)


def test_cli_api_contract_quality_explain_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "干净之书"}).json()["id"]
    draft_id = _seed_draft(db, workspace_id, content="雨夜开场。风从巷口吹来。")

    api = client.get(
        f"/works/{workspace_id}/drafts/{draft_id}/quality/explain"
    )
    assert api.status_code == 200
    assert "未发现明显 AI 味" in api.text
    assert "good sentences:" in api.text

    cli = runner.invoke(cli_app, ["quality", "explain", draft_id])
    assert cli.exit_code == 0, cli.output
    assert api.text == _cli_text(cli)


def test_cli_api_contract_consistency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from novel_editorial.core import setting

    client, db = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "一致之书"}).json()["id"]
    setting.add_setting(
        db,
        workspace_id,
        kind="character",
        name="沈夜",
        content="雨夜归乡的侦探",
    )
    draft_id = _seed_draft(db, workspace_id, content="雨夜开场，钩子埋下。")

    api = client.get(
        f"/works/{workspace_id}/drafts/{draft_id}/consistency"
    )
    assert api.status_code == 200
    assert api.headers["content-type"].startswith("text/plain")
    assert "settings checked: 1 / threads checked: 0" in api.text
    assert "[未提及] 沈夜：设定人物未在正文出现" in api.text

    cli = runner.invoke(cli_app, ["consistency", "check", draft_id])
    assert cli.exit_code == 0, cli.output
    assert api.text == _cli_text(cli)


def test_cli_api_contract_quality_calibrate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "sample.txt").write_text(
        "雨夜开场，风从巷口吹来。\n", encoding="utf-8"
    )
    (corpus / "bad.txt").write_bytes(b"\xff\xfe\x00\xc3\x28")

    api = client.post("/quality/calibrate", json={"path": str(corpus)})
    assert api.status_code == 200
    assert api.headers["content-type"].startswith("text/plain")
    assert "samples: 1" in api.text
    assert "suggested threshold: 1" in api.text
    assert "skipped: 1" in api.text
    assert "warning: corpus file is not valid UTF-8" in api.text

    cli = runner.invoke(cli_app, ["quality", "calibrate", str(corpus)])
    assert cli.exit_code == 0, cli.output
    assert api.text == _cli_text(cli)


def test_cli_api_contract_quality_calibrate_apply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "sample.txt").write_text("雨夜开场。", encoding="utf-8")

    api = client.post(
        "/quality/calibrate", json={"path": str(corpus), "apply": True}
    )
    assert api.status_code == 200
    assert "apply: quality_threshold = 1" in api.text
    assert "config updated:" in api.text
    config = (tmp_path / "config.toml").read_text(encoding="utf-8")
    assert "quality_threshold = 1" in config

    cli = runner.invoke(
        cli_app, ["quality", "calibrate", str(corpus), "--apply"]
    )
    assert cli.exit_code == 0, cli.output
    assert api.text == _cli_text(cli)


def test_quality_calibrate_error_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)

    missing = client.post(
        "/quality/calibrate", json={"path": str(tmp_path / "nope")}
    )
    assert missing.status_code == 404
    assert "corpus path not found" in missing.json()["detail"]

    (tmp_path / "notes.csv").write_text("x", encoding="utf-8")
    single = client.post(
        "/quality/calibrate", json={"path": str(tmp_path / "notes.csv")}
    )
    assert single.status_code == 422
    assert "single-file corpus must be a non-hidden .txt/.md file" in single.json()[
        "detail"
    ]

    empty_body = client.post("/quality/calibrate", json={})
    assert empty_body.status_code == 422
    blank_path = client.post("/quality/calibrate", json={"path": "  "})
    assert blank_path.status_code == 422

    cli_missing = runner.invoke(
        cli_app, ["quality", "calibrate", str(tmp_path / "nope")]
    )
    assert cli_missing.exit_code == 1
    assert "corpus path not found" in cli_missing.output
    cli_single = runner.invoke(
        cli_app, ["quality", "calibrate", str(tmp_path / "notes.csv")]
    )
    assert cli_single.exit_code == 2
    assert "single-file corpus" in cli_single.output


def test_cli_api_contract_quality_feedback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    feedback = tmp_path / "feedback.jsonl"
    feedback.write_text(
        '{"label": "bad", "text": "雨夜宛如轻纱笼罩。"}\n'
        '{"label": "good", "text": "雨夜开场。"}\n',
        encoding="utf-8",
    )

    api = client.post("/quality/feedback", json={"path": str(feedback)})
    assert api.status_code == 200
    assert api.headers["content-type"].startswith("text/plain")
    assert "samples: 2" in api.text
    assert "bad: 1 / good: 1" in api.text
    assert "bad scores: min 6 median 6 p90 6 max 6" in api.text
    assert "agreement at threshold 8: 50.0% (1/2)" in api.text

    cli = runner.invoke(cli_app, ["quality", "feedback", str(feedback)])
    assert cli.exit_code == 0, cli.output
    assert api.text == _cli_text(cli)


def test_cli_api_contract_quality_feedback_apply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("NOVEL_FRONTEND_DIST", str(tmp_path / "no-dist"))
    feedback = tmp_path / "feedback.jsonl"
    feedback.write_text(
        '{"label": "bad", "text": "雨夜宛如轻纱，仿佛梦呓。"}\n'
        '{"label": "bad", "text": "雨夜宛如轻纱笼罩。"}\n'
        '{"label": "good", "text": "雨夜开场。"}\n',
        encoding="utf-8",
    )

    # API and CLI each apply against their own config, both starting from the
    # default threshold 8, so the report lines stay comparable while the write
    # lands in separate files.
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "api-config.toml"))
    client = TestClient(create_app())
    api = client.post(
        "/quality/feedback", json={"path": str(feedback), "apply": True}
    )
    assert api.status_code == 200

    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "cli-config.toml"))
    cli = runner.invoke(
        cli_app, ["quality", "feedback", str(feedback), "--apply"]
    )
    assert cli.exit_code == 0, cli.output

    api_normalized = api.text.replace(
        str(tmp_path / "api-config.toml"), "<config>"
    )
    cli_normalized = _cli_text(cli).replace(
        str(tmp_path / "cli-config.toml"), "<config>"
    )
    assert api_normalized == cli_normalized
    suggested_line = next(
        line
        for line in cli.output.splitlines()
        if line.startswith("suggested threshold: ")
    )
    suggested = suggested_line.split(": ", 1)[1]
    assert f"apply: quality_threshold = {suggested}" in api.text
    assert f"quality_threshold = {suggested}" in (
        tmp_path / "api-config.toml"
    ).read_text(encoding="utf-8")
    assert f"quality_threshold = {suggested}" in (
        tmp_path / "cli-config.toml"
    ).read_text(encoding="utf-8")


def test_quality_feedback_error_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)

    missing = client.post(
        "/quality/feedback", json={"path": str(tmp_path / "nope.jsonl")}
    )
    assert missing.status_code == 404
    assert "feedback file not found" in missing.json()["detail"]

    bad_json = tmp_path / "bad.jsonl"
    bad_json.write_text("not json\n", encoding="utf-8")
    invalid = client.post("/quality/feedback", json={"path": str(bad_json)})
    assert invalid.status_code == 422
    assert "invalid JSON" in invalid.json()["detail"]

    good_only = tmp_path / "good-only.jsonl"
    good_only.write_text('{"label": "good", "text": "雨夜开场。"}\n', encoding="utf-8")
    no_suggestion = client.post(
        "/quality/feedback",
        json={"path": str(good_only), "apply": True},
    )
    assert no_suggestion.status_code == 422
    assert (
        "cannot apply a suggested threshold without bad samples"
        in no_suggestion.json()["detail"]
    )

    cli_bad = runner.invoke(cli_app, ["quality", "feedback", str(bad_json)])
    assert cli_bad.exit_code == 2
    assert "invalid JSON" in cli_bad.output
    cli_apply = runner.invoke(
        cli_app, ["quality", "feedback", str(good_only), "--apply"]
    )
    assert cli_apply.exit_code == 2
    assert "cannot apply a suggested threshold" in cli_apply.output


def test_cli_api_contract_style_learn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "学风格之书"}).json()["id"]
    set_style_anchor(
        db, workspace_id, description="旧描述", forbidden_words="宛如、仿佛"
    )
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "ref.txt").write_text(
        "雨停了。街灯一盏盏亮起来。风里带着潮气。", encoding="utf-8"
    )

    api = client.post(
        f"/works/{workspace_id}/style/learn", json={"path": str(corpus)}
    )
    assert api.status_code == 200
    assert api.headers["content-type"].startswith("text/plain")
    assert "samples: 1" in api.text
    assert "suggested description: " in api.text

    cli = runner.invoke(
        cli_app, ["style", "learn", workspace_id, str(corpus)]
    )
    assert cli.exit_code == 0, cli.output
    assert api.text == _cli_text(cli)


def test_cli_api_contract_style_learn_apply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "落锚之书"}).json()["id"]
    set_style_anchor(
        db, workspace_id, description="旧描述", forbidden_words="宛如、仿佛"
    )
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "ref.txt").write_text(
        "雨停了。街灯一盏盏亮起来。", encoding="utf-8"
    )

    api = client.post(
        f"/works/{workspace_id}/style/learn",
        json={"path": str(corpus), "apply": True},
    )
    assert api.status_code == 200
    assert "apply: description = " in api.text
    assert f"style anchor updated: {workspace_id}" in api.text
    shown = client.get(f"/works/{workspace_id}/style").json()
    assert shown["description"] != "旧描述"
    assert shown["forbidden_words"] == "宛如、仿佛"

    cli = runner.invoke(
        cli_app, ["style", "learn", workspace_id, str(corpus), "--apply"]
    )
    assert cli.exit_code == 0, cli.output
    assert api.text == _cli_text(cli)


def test_cli_api_contract_style_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "漂移之书"}).json()["id"]
    set_style_anchor(
        db, workspace_id, description="克制、留白", forbidden_words="宛如"
    )
    _seed_draft(db, workspace_id, title="第一章", content="雨夜开场。风很冷。")
    _seed_draft(db, workspace_id, title="第二章", content="阳光明媚。鸟语花香。")

    api = client.get(f"/works/{workspace_id}/style/drift")
    assert api.status_code == 200
    assert api.headers["content-type"].startswith("text/plain")
    assert "chapters: 2" in api.text
    assert "drift trend:" in api.text
    assert "verdict:" in api.text

    cli = runner.invoke(cli_app, ["style", "drift", workspace_id])
    assert cli.exit_code == 0, cli.output
    assert api.text == _cli_text(cli)


def test_cli_api_contract_style_drift_no_chapters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "空书"}).json()["id"]

    api = client.get(f"/works/{workspace_id}/style/drift")
    assert api.status_code == 200
    assert api.text == "no chapters"

    cli = runner.invoke(cli_app, ["style", "drift", workspace_id])
    assert cli.exit_code == 0, cli.output
    assert api.text == _cli_text(cli)


def test_style_learn_error_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "错路径之书"}).json()["id"]

    missing = client.post(
        f"/works/{workspace_id}/style/learn",
        json={"path": str(tmp_path / "nope")},
    )
    assert missing.status_code == 404
    assert "corpus path not found" in missing.json()["detail"]

    empty_corpus = tmp_path / "empty"
    empty_corpus.mkdir()
    no_samples = client.post(
        f"/works/{workspace_id}/style/learn",
        json={"path": str(empty_corpus)},
    )
    assert no_samples.status_code == 422
    assert "corpus contains no readable samples" in no_samples.json()["detail"]

    blank = client.post(
        f"/works/{workspace_id}/style/learn", json={"path": "  "}
    )
    assert blank.status_code == 422

    cli_missing = runner.invoke(
        cli_app, ["style", "learn", workspace_id, str(tmp_path / "nope")]
    )
    assert cli_missing.exit_code == 1
    assert "corpus path not found" in cli_missing.output


def test_cli_api_contract_motives_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "动机之书"}).json()["id"]
    agent = _first_agent(db, workspace_id)
    _seed_motive(db, workspace_id, agent_id=agent.id)

    api = client.get(f"/works/{workspace_id}/motives")
    assert api.status_code == 200
    assert api.headers["content-type"].startswith("text/plain")
    assert f"[{agent.name}] [goal] strength=100" in api.text
    assert "source=event:draft_generated" in api.text

    cli = runner.invoke(cli_app, ["motives", "list", workspace_id])
    assert cli.exit_code == 0, cli.output
    assert api.text == _cli_text(cli)

    filtered_api = client.get(
        f"/works/{workspace_id}/motives", params={"agent": agent.name}
    )
    assert filtered_api.status_code == 200
    cli_filtered = runner.invoke(
        cli_app, ["motives", "list", workspace_id, "--agent", agent.name]
    )
    assert cli_filtered.exit_code == 0, cli_filtered.output
    assert filtered_api.text == _cli_text(cli_filtered)


def test_cli_api_contract_motives_list_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "无动机之书"}).json()["id"]

    api = client.get(f"/works/{workspace_id}/motives")
    assert api.status_code == 200
    assert api.text == "no motives yet"

    cli = runner.invoke(cli_app, ["motives", "list", workspace_id])
    assert cli.exit_code == 0, cli.output
    assert api.text == _cli_text(cli)


def test_cli_api_contract_motives_drop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "放下之书"}).json()["id"]
    agent = _first_agent(db, workspace_id)
    cli_motive_id = _seed_motive(
        db, workspace_id, agent_id=agent.id, content="放下的旧事"
    )
    api_motive_id = _seed_motive(
        db,
        workspace_id,
        agent_id=agent.id,
        content="放下的旧事",
        source="event:review_conflict",
    )

    cli_drop = runner.invoke(
        cli_app, ["motives", "drop", workspace_id, cli_motive_id]
    )
    assert cli_drop.exit_code == 0, cli_drop.output
    api_drop = client.delete(
        f"/works/{workspace_id}/motives/{api_motive_id}"
    )
    assert api_drop.status_code == 200
    assert api_drop.headers["content-type"].startswith("text/plain")
    assert api_drop.text == _cli_text(cli_drop).replace(
        cli_motive_id, api_motive_id
    )

    remaining = client.get(f"/works/{workspace_id}/motives").text
    assert cli_motive_id not in remaining
    assert api_motive_id not in remaining

    timeline = client.get(f"/works/{workspace_id}/behavior/timeline").text
    assert "作者放下动机" in timeline
    assert "source=author_feedback:drop" in timeline


def test_motives_error_paths_and_isolation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = _make_client(tmp_path, monkeypatch)
    workspace_a = client.post("/works", json={"title": "甲书"}).json()["id"]
    workspace_b = client.post("/works", json={"title": "乙书"}).json()["id"]
    agent = _first_agent(db, workspace_a)
    motive_id = _seed_motive(db, workspace_a, agent_id=agent.id)

    missing_ws = client.get("/works/missing/motives")
    assert missing_ws.status_code == 404
    assert "workspace not found: missing" in missing_ws.json()["detail"]

    unknown_agent = client.get(
        f"/works/{workspace_a}/motives", params={"agent": "不存在的伙伴"}
    )
    assert unknown_agent.status_code == 404
    assert "agent not found" in unknown_agent.json()["detail"]

    missing_motive = client.delete(
        f"/works/{workspace_a}/motives/missing-id"
    )
    assert missing_motive.status_code == 404
    assert "motive not found: missing-id" in missing_motive.json()["detail"]

    cross_drop = client.delete(
        f"/works/{workspace_b}/motives/{motive_id}"
    )
    assert cross_drop.status_code == 404
    assert client.get(f"/works/{workspace_a}/motives").status_code == 200

    cli_missing = runner.invoke(cli_app, ["motives", "drop", workspace_a, "a" * 32])
    assert cli_missing.exit_code == 1
    assert "motive not found" in cli_missing.output


def test_cli_api_contract_patience_show(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "耐心之书"}).json()["id"]
    agent = _first_agent(db, workspace_id)
    _seed_behavior(
        db,
        workspace_id,
        agent_id=agent.id,
        kind="relationship",
        target="作者",
        summary="拍板拒绝",
        source="decision:reject",
    )
    _seed_behavior(
        db,
        workspace_id,
        agent_id=agent.id,
        kind="viewpoint",
        target="规则A",
        summary="作者推翻",
        source="override:规则A",
    )

    api = client.get(f"/works/{workspace_id}/patience")
    assert api.status_code == 200
    assert api.headers["content-type"].startswith("text/plain")
    assert f"[{agent.name}]" in api.text
    assert "rejected=1" in api.text
    assert "overridden=1" in api.text

    cli = runner.invoke(cli_app, ["patience", "show", workspace_id])
    assert cli.exit_code == 0, cli.output
    assert api.text == _cli_text(cli)


def test_cli_api_contract_patience_show_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "空耐心之书"}).json()["id"]

    api = client.get(f"/works/{workspace_id}/patience")
    assert api.status_code == 200
    assert "pool=" in api.text

    cli = runner.invoke(cli_app, ["patience", "show", workspace_id])
    assert cli.exit_code == 0, cli.output
    assert api.text == _cli_text(cli)


def test_cli_api_contract_behavior_timeline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "行为之书"}).json()["id"]
    agent = _first_agent(db, workspace_id)
    _seed_behavior(
        db,
        workspace_id,
        agent_id=agent.id,
        kind="impression",
        target="作者",
        summary="初见印象",
        before_value="",
        after_value="认真",
        source="first_meet",
    )
    _seed_behavior(
        db,
        workspace_id,
        agent_id=agent.id,
        kind="viewpoint",
        target="规则B",
        summary="坚持立场",
        after_value="坚持该立场",
        source="refusal:规则B",
    )

    api = client.get(f"/works/{workspace_id}/behavior/timeline")
    assert api.status_code == 200
    assert api.headers["content-type"].startswith("text/plain")
    assert "[impression]" in api.text
    assert "[viewpoint]" in api.text
    assert "source=refusal:规则B" in api.text

    cli = runner.invoke(cli_app, ["behavior", "timeline", workspace_id])
    assert cli.exit_code == 0, cli.output
    assert api.text == _cli_text(cli)

    kind_api = client.get(
        f"/works/{workspace_id}/behavior/timeline",
        params=[("kind", "viewpoint")],
    )
    kind_cli = runner.invoke(
        cli_app,
        ["behavior", "timeline", workspace_id, "--kind", "viewpoint"],
    )
    assert kind_cli.exit_code == 0, kind_cli.output
    assert kind_api.text == _cli_text(kind_cli)

    agent_api = client.get(
        f"/works/{workspace_id}/behavior/timeline",
        params={"agent": agent.name},
    )
    agent_cli = runner.invoke(
        cli_app,
        ["behavior", "timeline", workspace_id, "--agent", agent.name],
    )
    assert agent_cli.exit_code == 0, agent_cli.output
    assert agent_api.text == _cli_text(agent_cli)

    limit_api = client.get(
        f"/works/{workspace_id}/behavior/timeline", params={"limit": 1}
    )
    limit_cli = runner.invoke(
        cli_app, ["behavior", "timeline", workspace_id, "--limit", "1"]
    )
    assert limit_cli.exit_code == 0, limit_cli.output
    assert limit_api.text == _cli_text(limit_cli)


def test_cli_api_contract_behavior_timeline_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "空行为之书"}).json()["id"]

    api = client.get(f"/works/{workspace_id}/behavior/timeline")
    assert api.status_code == 200
    assert api.text == "no behavior traces yet"

    cli = runner.invoke(cli_app, ["behavior", "timeline", workspace_id])
    assert cli.exit_code == 0, cli.output
    assert api.text == _cli_text(cli)


def test_behavior_timeline_error_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "错行为之书"}).json()["id"]
    _first_agent(db, workspace_id)

    unknown_kind = client.get(
        f"/works/{workspace_id}/behavior/timeline",
        params=[("kind", "nonsense")],
    )
    assert unknown_kind.status_code == 422
    assert "unknown behavior kind: nonsense" in unknown_kind.json()["detail"]

    unknown_agent = client.get(
        f"/works/{workspace_id}/behavior/timeline",
        params={"agent": "不存在的人"},
    )
    assert unknown_agent.status_code == 422
    assert "unknown agent: 不存在的人" in unknown_agent.json()["detail"]

    bad_limit = client.get(
        f"/works/{workspace_id}/behavior/timeline", params={"limit": 0}
    )
    assert bad_limit.status_code == 422

    cli_kind = runner.invoke(
        cli_app,
        ["behavior", "timeline", workspace_id, "--kind", "nonsense"],
    )
    assert cli_kind.exit_code == 2
    assert "unknown behavior kind" in cli_kind.output
    cli_agent = runner.invoke(
        cli_app,
        ["behavior", "timeline", workspace_id, "--agent", "不存在的人"],
    )
    assert cli_agent.exit_code == 2
    assert "unknown agent" in cli_agent.output


def test_cli_api_contract_behavior_show(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "状态之书"}).json()["id"]
    agent = _first_agent(db, workspace_id)
    _seed_behavior(
        db,
        workspace_id,
        agent_id=agent.id,
        kind="viewpoint",
        target="规则C",
        summary="拒绝指令",
        after_value="坚持该立场",
        source="refusal:规则C",
    )
    _seed_behavior(
        db,
        workspace_id,
        agent_id=agent.id,
        kind="impression",
        target="作者",
        summary="认真的人",
        source="first_meet",
    )

    api = client.get(f"/works/{workspace_id}/behavior")
    assert api.status_code == 200
    assert api.headers["content-type"].startswith("text/plain")
    assert f"[{agent.name}]" in api.text
    assert "viewpoint -> 规则C" in api.text
    assert "impression -> 作者" in api.text

    cli = runner.invoke(cli_app, ["behavior", "show", workspace_id])
    assert cli.exit_code == 0, cli.output
    assert api.text == _cli_text(cli)


def test_cli_api_contract_behavior_show_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "空状态之书"}).json()["id"]

    api = client.get(f"/works/{workspace_id}/behavior")
    assert api.status_code == 200
    assert api.text == "no behavior traces yet"

    cli = runner.invoke(cli_app, ["behavior", "show", workspace_id])
    assert cli.exit_code == 0, cli.output
    assert api.text == _cli_text(cli)


def test_quality_consistency_draft_cross_workspace_isolation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = _make_client(tmp_path, monkeypatch)
    workspace_a = client.post("/works", json={"title": "甲书"}).json()["id"]
    workspace_b = client.post("/works", json={"title": "乙书"}).json()["id"]
    draft_id = _seed_draft(db, workspace_a, content="雨夜宛如轻纱。")

    for suffix in ("quality/check", "quality/explain", "consistency"):
        api = client.get(f"/works/{workspace_b}/drafts/{draft_id}/{suffix}")
        assert api.status_code == 404
        assert f"draft not found: {draft_id}" in api.json()["detail"]

    cli = runner.invoke(cli_app, ["quality", "check", draft_id])
    assert cli.exit_code == 0, cli.output
    assert "passed:" in cli.output


def test_quality_style_read_routes_are_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, db = _make_client(tmp_path, monkeypatch)
    workspace_id = _seed_workspace(client, db)
    draft_id = _seed_draft(db, workspace_id, content="雨夜开场。宛如轻纱笼罩。")

    before_counts = _table_counts(db, workspace_id)
    events_before = client.get(f"/works/{workspace_id}/events").json()

    urls = (
        f"/works/{workspace_id}/drafts/{draft_id}/quality/check",
        f"/works/{workspace_id}/drafts/{draft_id}/quality/explain",
        f"/works/{workspace_id}/drafts/{draft_id}/consistency",
        f"/works/{workspace_id}/style/drift",
        f"/works/{workspace_id}/motives",
        f"/works/{workspace_id}/patience",
        f"/works/{workspace_id}/behavior",
        f"/works/{workspace_id}/behavior/timeline",
    )
    for url in urls:
        response = client.get(url)
        assert response.status_code == 200

    assert _table_counts(db, workspace_id) == before_counts
    assert client.get(f"/works/{workspace_id}/events").json() == events_before


def test_config_snapshot_is_full_and_non_sensitive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NOVEL_LLM_API_KEY", "sk-secret")
    client, _ = _make_client(tmp_path, monkeypatch)

    response = client.get("/config")

    assert response.status_code == 200
    data = response.json()
    assert data["restart_required"] is False
    assert "llm_api_key" not in data
    for field in (
        "data_dir",
        "config_path",
        "llm_base_url",
        "llm_model",
        "log_level",
        "quality_threshold",
        "memory_decay_per_day",
        "memory_rehearsal_boost",
        "memory_archive_threshold",
        "proactive_enabled",
        "proactive_max_per_agent",
        "freedom_dial",
        "freedom_seed",
        "motive_llm_enabled",
        "embedding_backend",
        "embedding_model",
        "embedding_dim",
        "embedding_top_k",
        "api_host",
        "api_port",
        "panel_poll_interval",
    ):
        assert field in data, field
    assert data["data_dir"] == str(tmp_path)
    assert data["config_path"] == str(tmp_path / "config.toml")


@pytest.mark.parametrize(
    "key,value,expected",
    [
        ("quality_threshold", 10, 10),
        ("panel_poll_interval", 5, 5),
        ("freedom_dial", 0.5, 0.5),
        ("freedom_seed", 7, 7),
        ("proactive_enabled", False, False),
        ("proactive_max_per_agent", 4, 4),
        ("motive_llm_enabled", True, True),
    ],
)
def test_config_put_each_writable_key_reads_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    key: str,
    value: object,
    expected: object,
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)

    response = client.put("/config", json={"key": key, "value": value})

    assert response.status_code == 200
    data = response.json()
    assert data[key] == expected
    assert data["restart_required"] is True
    assert "重启后生效" in data["message"]
    snapshot = client.get("/config").json()
    assert snapshot[key] == expected
    assert snapshot["restart_required"] is False


@pytest.mark.parametrize(
    "key,value,expected",
    [
        ("quality_threshold", "9", 9),
        ("freedom_dial", "0.25", 0.25),
        ("proactive_enabled", "off", False),
        ("motive_llm_enabled", "yes", True),
    ],
)
def test_config_put_accepts_string_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    key: str,
    value: str,
    expected: object,
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)

    response = client.put("/config", json={"key": key, "value": value})

    assert response.status_code == 200
    assert response.json()[key] == expected


def test_config_put_idempotent_same_value_keeps_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    first = client.put("/config", json={"key": "quality_threshold", "value": 11})
    assert first.status_code == 200
    config_path = tmp_path / "config.toml"
    before = config_path.read_bytes()

    again = client.put("/config", json={"key": "quality_threshold", "value": 11})

    assert again.status_code == 200
    assert config_path.read_bytes() == before


@pytest.mark.parametrize(
    "payload",
    [
        {"key": "llm_api_key", "value": "sk-secret"},
        {"key": "embedding_model", "value": "x"},
        {"key": "quality_threshold", "value": -1},
        {"key": "quality_threshold", "value": 3.5},
        {"key": "freedom_dial", "value": 2},
        {"key": "proactive_enabled", "value": "maybe"},
        {"key": "panel_poll_interval", "value": 0},
    ],
)
def test_config_put_invalid_key_or_value_422(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: dict
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)

    response = client.put("/config", json=payload)

    assert response.status_code == 422
    assert not (tmp_path / "config.toml").exists()


def test_config_put_env_overridden_key_snapshot_still_shows_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NOVEL_QUALITY_THRESHOLD", "5")
    client, _ = _make_client(tmp_path, monkeypatch)

    response = client.put("/config", json={"key": "quality_threshold", "value": 10})

    assert response.status_code == 200
    assert response.json()["quality_threshold"] == 5
    assert client.get("/config").json()["quality_threshold"] == 5
    assert (tmp_path / "config.toml").read_text(
        encoding="utf-8"
    ) == "[defaults]\nquality_threshold = 10\n"


def test_export_download_and_cli_import_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "导出之书"}).json()["id"]

    response = client.get(f"/works/{workspace_id}/export")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")
    disposition = response.headers["content-disposition"]
    assert f"{workspace_id[:8]}-" in disposition
    assert disposition.endswith('.zip"')

    archive = tmp_path / "api-export.zip"
    archive.write_bytes(response.content)

    imported = runner.invoke(cli_app, ["works", "import", str(archive)])
    assert imported.exit_code == 0, imported.output
    assert "导出之书" in imported.output
    imported_id = imported.output.split()[2].rstrip(":")
    assert imported_id != workspace_id
    works = client.get("/works").json()
    assert any(item["id"] == imported_id for item in works)


def test_cli_export_and_api_import_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    workspace_id = client.post("/works", json={"title": "导入之书"}).json()["id"]
    export_dir = tmp_path / "cli-exports"
    export_dir.mkdir()

    exported = runner.invoke(
        cli_app, ["works", "export", workspace_id, str(export_dir)]
    )
    assert exported.exit_code == 0, exported.output
    archives = list(export_dir.glob("novel-export-*.zip"))
    assert len(archives) == 1

    response = client.post(
        "/works/import",
        files={"file": ("workspace.zip", archives[0].read_bytes(), "application/zip")},
    )

    assert response.status_code == 201
    imported = response.json()
    assert imported["id"] != workspace_id
    assert imported["title"] == "导入之书"
    events = client.get(f"/works/{imported['id']}/events").json()
    imported_events = [
        event
        for event in events
        if event["payload"].get("kind") == "workspace_imported"
    ]
    assert len(imported_events) == 1
    assert imported_events[0]["payload"]["source_id"] == workspace_id


@pytest.mark.parametrize("content", [b"not a zip", b""])
def test_import_invalid_archive_422(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    content: bytes,
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)

    response = client.post(
        "/works/import",
        files={"file": ("broken.zip", content, "application/zip")},
    )

    assert response.status_code == 422
    assert "invalid archive" in response.json()["detail"]


def test_export_missing_workspace_404(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)

    response = client.get("/works/missing/export")

    assert response.status_code == 404
    assert response.json() == {"detail": "workspace not found: missing"}
