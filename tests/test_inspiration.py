import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.config import load_settings
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.core.inspiration import (
    DEFAULT_INSPIRATION_KIND,
    add_inspiration,
    get_inspiration,
    list_inspirations,
    remove_inspiration,
)
from novel_editorial.store.db import DB, run_migrations, workspace_db_path
from novel_editorial.store.events import list_events
from novel_editorial.store.models import Inspiration

runner = CliRunner()


def _create_workspace(tmp_path: Path, monkeypatch, title: str = "灵感之书") -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["works", "create", title])
    assert result.exit_code == 0, result.output
    return result.output.split()[2].rstrip(":")


def _db() -> DB:
    return DB(load_settings())


def _alembic_config(url: str) -> Config:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def _table_names(path: Path) -> set[str]:
    connection = sqlite3.connect(path)
    try:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        return {row[0] for row in rows}
    finally:
        connection.close()


def _index_names(path: Path) -> set[str]:
    connection = sqlite3.connect(path)
    try:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
        return {row[0] for row in rows}
    finally:
        connection.close()


def test_inspiration_model_columns() -> None:
    columns = set(Inspiration.__table__.columns.keys())
    assert columns == {
        "id",
        "workspace_id",
        "kind",
        "content",
        "source",
        "created_at",
        "updated_at",
    }


def test_add_inspiration_defaults_and_fields(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    inspiration = add_inspiration(db, workspace_id, content="雨夜巷口的一只猫")

    assert len(inspiration.id) == 32
    assert inspiration.workspace_id == workspace_id
    assert inspiration.kind == DEFAULT_INSPIRATION_KIND
    assert inspiration.kind == "灵感"
    assert inspiration.content == "雨夜巷口的一只猫"
    assert inspiration.source == ""
    assert inspiration.created_at is not None
    assert inspiration.updated_at is not None

    with db.workspace_session(workspace_id) as session:
        stored = session.get(Inspiration, inspiration.id)
        assert stored is not None
        assert stored.kind == "灵感"
        assert stored.source == ""


def test_add_inspiration_custom_kind_and_source(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    inspiration = add_inspiration(
        db,
        workspace_id,
        content="破晓时分的码头",
        kind="场景",
        source="清晨散步笔记",
    )

    assert inspiration.kind == "场景"
    assert inspiration.source == "清晨散步笔记"


@pytest.mark.parametrize(
    ("content", "kind"),
    [
        ("   ", "灵感"),
        ("", "灵感"),
        ("有效内容", "   "),
        ("有效内容", ""),
    ],
)
def test_add_inspiration_empty_content_or_kind_is_usage_error(
    tmp_path: Path, monkeypatch, content: str, kind: str
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    with pytest.raises(NovelError) as exc:
        add_inspiration(db, workspace_id, content=content, kind=kind)
    assert exc.value.code == ErrorCode.USAGE_ERROR


def test_add_inspiration_unknown_workspace_not_found(
    tmp_path: Path, monkeypatch
) -> None:
    _create_workspace(tmp_path, monkeypatch)
    db = _db()
    with pytest.raises(NovelError) as exc:
        add_inspiration(
            db, "ffffffffffffffffffffffffffffffff", content="无主灵感"
        )
    assert exc.value.code == ErrorCode.NOT_FOUND


def test_list_inspirations_empty(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    assert list_inspirations(db, workspace_id) == []


def test_list_inspirations_kind_filter(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    image = add_inspiration(db, workspace_id, content="码头雾气", kind="意象")
    scene = add_inspiration(db, workspace_id, content="茶馆争吵", kind="场景")
    add_inspiration(db, workspace_id, content="女主名字候选", kind="素材")

    images = list_inspirations(db, workspace_id, kind="意象")
    assert [row.id for row in images] == [image.id]
    scenes = list_inspirations(db, workspace_id, kind="场景")
    assert [row.id for row in scenes] == [scene.id]
    assert list_inspirations(db, workspace_id, kind="不存在的分类") == []


def test_list_inspirations_keyword_case_insensitive_content_and_source(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    content_hit = add_inspiration(
        db, workspace_id, content="Dawn breaks over the pier", kind="意象"
    )
    source_hit = add_inspiration(
        db,
        workspace_id,
        content="码头雾散",
        kind="场景",
        source="from the DAWN notebook",
    )
    add_inspiration(db, workspace_id, content="茶馆争吵", kind="场景")

    assert [row.id for row in list_inspirations(db, workspace_id, keyword="dawn")] == [
        source_hit.id,
        content_hit.id,
    ]
    assert [row.id for row in list_inspirations(db, workspace_id, keyword="DAWN")] == [
        source_hit.id,
        content_hit.id,
    ]
    assert [row.id for row in list_inspirations(db, workspace_id, keyword="pier")] == [
        content_hit.id
    ]
    assert [row.id for row in list_inspirations(db, workspace_id, keyword="notebook")] == [
        source_hit.id
    ]
    assert list_inspirations(db, workspace_id, keyword="无关词") == []


def test_list_inspirations_sorted_updated_at_desc_then_id_asc(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    first = add_inspiration(db, workspace_id, content="第一条", kind="灵感")
    second = add_inspiration(db, workspace_id, content="第二条", kind="灵感")
    fixed = datetime(2026, 8, 1, tzinfo=UTC)
    with db.workspace_session(workspace_id) as session:
        for row in session.query(Inspiration).all():
            row.updated_at = fixed
        session.commit()

    rows = list_inspirations(db, workspace_id)
    assert [row.id for row in rows] == sorted([first.id, second.id])

    third = add_inspiration(db, workspace_id, content="第三条", kind="场景")
    rows = list_inspirations(db, workspace_id)
    assert [row.id for row in rows] == [third.id] + sorted([first.id, second.id])


def test_get_inspiration_returns_row(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    added = add_inspiration(
        db,
        workspace_id,
        content="北站的旧钟",
        kind="意象",
        source="第二章初稿",
    )

    shown = get_inspiration(db, workspace_id, added.id)
    assert shown.id == added.id
    assert shown.kind == "意象"
    assert shown.content == "北站的旧钟"
    assert shown.source == "第二章初稿"


def test_get_inspiration_not_found(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    add_inspiration(db, workspace_id, content="存在的灵感")

    with pytest.raises(NovelError) as exc:
        get_inspiration(db, workspace_id, "dddddddddddddddddddddddddddddddd")
    assert exc.value.code == ErrorCode.NOT_FOUND

    with pytest.raises(NovelError) as exc:
        get_inspiration(
            db, "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee", "dddddddddddddddddddddddddddddddd"
        )
    assert exc.value.code == ErrorCode.NOT_FOUND


def test_remove_inspiration_deletes_and_returns_row(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    added = add_inspiration(
        db, workspace_id, content="废弃车站的雨声", kind="意象", source="通勤路上"
    )

    removed = remove_inspiration(db, workspace_id, added.id)
    assert removed.id == added.id
    assert removed.kind == "意象"
    assert removed.content == "废弃车站的雨声"
    assert list_inspirations(db, workspace_id) == []

    with pytest.raises(NovelError) as exc:
        get_inspiration(db, workspace_id, added.id)
    assert exc.value.code == ErrorCode.NOT_FOUND


def test_remove_inspiration_not_found(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    with pytest.raises(NovelError) as exc:
        remove_inspiration(db, workspace_id, "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    assert exc.value.code == ErrorCode.NOT_FOUND


def test_inspiration_event_flow_created_removed_and_read_only(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    added = add_inspiration(db, workspace_id, content="雨夜巷口的猫", kind="意象")

    events = list_events(db, workspace_id)
    assert len(events) == 1
    assert events[0].type == "system"
    assert json.loads(events[0].payload) == {
        "kind": "inspiration_created",
        "inspiration_id": added.id,
        "inspiration_kind": "意象",
    }

    list_inspirations(db, workspace_id)
    get_inspiration(db, workspace_id, added.id)
    list_inspirations(db, workspace_id, kind="意象", keyword="猫")
    assert len(list_events(db, workspace_id)) == 1

    removed = remove_inspiration(db, workspace_id, added.id)
    assert removed.id == added.id
    events = list_events(db, workspace_id)
    assert len(events) == 2
    assert json.loads(events[0].payload) == {
        "kind": "inspiration_removed",
        "inspiration_id": added.id,
        "inspiration_kind": "意象",
    }
    assert json.loads(events[1].payload) == {
        "kind": "inspiration_created",
        "inspiration_id": added.id,
        "inspiration_kind": "意象",
    }


def test_inspiration_migration_roundtrip(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    path = workspace_db_path(settings, workspace_id)

    assert "inspirations" in _table_names(path)
    assert "ix_inspirations_workspace_id" in _index_names(path)

    command.downgrade(_alembic_config(f"sqlite:///{path}"), "cf095609171a")
    assert "inspirations" not in _table_names(path)

    run_migrations(f"sqlite:///{path}")
    assert "inspirations" in _table_names(path)
    assert "ix_inspirations_workspace_id" in _index_names(path)
