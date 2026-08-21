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
from novel_editorial.store.models import Agent, Event, Workspace


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
