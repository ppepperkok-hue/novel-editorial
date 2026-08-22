"""HTTP API tests: health, works list/create/show, visibility routes, read-only guarantees."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from novel_editorial.api.app import create_app
from novel_editorial.core.config import load_settings
from novel_editorial.core.structure import create_node
from novel_editorial.core.style import set_style_anchor
from novel_editorial.events import EventType
from novel_editorial.store.db import DB
from novel_editorial.store.events import record_event
from novel_editorial.store.models import Agent, Draft, DraftVersion, Event, Review, Workspace


def _make_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[TestClient, DB]:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
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


def test_health(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = _make_client(tmp_path, monkeypatch)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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
    ):
        response = client.get(url)
        assert response.status_code == 200

    assert _table_counts(db, workspace_id) == before_counts
    assert client.get(f"/works/{workspace_id}/events").json() == events_before


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
    events = response.json()
    assert [event["payload"]["n"] for event in events] == [3, 2, 1]
    assert {event["workspace_id"] for event in events} == {first, second}
    for event in events:
        assert set(event) == {"id", "workspace_id", "type", "time", "actor", "payload"}
        assert isinstance(event["payload"], dict)
        assert isinstance(event["time"], str)

    limited = client.get("/events", params={"limit": 2})
    assert limited.status_code == 200
    assert [event["payload"]["n"] for event in limited.json()] == [3, 2]

    invalid = client.get("/events", params={"limit": 0})
    assert invalid.status_code == 422
    assert "detail" in invalid.json()


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
        assert set(version) == {"version", "reason", "created_at", "content"}
    assert versions[0]["content"] == "初版正文"
    assert versions[0]["reason"] == "initial"
    assert versions[1]["content"] == "修订版正文"
    assert versions[1]["reason"] == "revision"

    missing = client.get(f"/works/{workspace_id}/drafts/does-not-exist")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "draft not found: does-not-exist"}


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
    assert "[风格]" in inspected.text
    assert "冷峻克制" in inspected.text
    assert "[版本]" in inspected.text
    assert "冷峻克制的雨夜开场" in inspected.text
    assert "[意见]" in inspected.text
    assert "冷峻的钩子再亮一点" in inspected.text

    logged = client.get(f"/works/{workspace_id}/log")
    assert logged.status_code == 200
    assert "作品：《可见性之书》" in logged.text
    assert "== 草稿 ==" in logged.text
    assert "第一章" in logged.text
    assert "冷峻克制的雨夜开场" in logged.text
    assert "== 意见 ==" in logged.text
    assert "冷峻的钩子再亮一点" in logged.text


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
        "/works/missing/reviews?draft_id=x",
        "/works/missing/inspect?keyword=k",
        "/works/missing/log",
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
