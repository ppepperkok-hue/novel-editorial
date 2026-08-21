"""HTTP API tests: health, works list/create/show, error mapping, read-only guarantees."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from novel_editorial.api.app import create_app
from novel_editorial.core.config import load_settings
from novel_editorial.store.db import DB
from novel_editorial.store.models import Event


def _make_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[TestClient, DB]:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    return TestClient(create_app()), DB(load_settings())


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
