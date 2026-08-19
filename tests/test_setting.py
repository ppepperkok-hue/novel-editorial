import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import Table
from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.config import load_settings
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.core.setting import (
    KIND_LABELS,
    SETTING_KINDS,
    add_setting,
    get_setting,
    list_setting_history,
    list_settings,
    revise_setting,
)
from novel_editorial.store.db import DB, workspace_db_path
from novel_editorial.store.models import SettingEntry, SettingVersion

runner = CliRunner()


def _create_workspace(tmp_path: Path, monkeypatch, title: str = "设定之书") -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["works", "create", title])
    assert result.exit_code == 0, result.output
    return result.output.split()[2].rstrip(":")


def _db() -> DB:
    return DB(load_settings())


def test_setting_constants() -> None:
    assert SETTING_KINDS == ("character", "relation", "timeline", "world")
    assert KIND_LABELS == {
        "character": "人物",
        "relation": "关系",
        "timeline": "时间线",
        "world": "世界观",
    }


@pytest.mark.smoke
def test_add_setting_creates_entry_and_initial_version(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    entry = add_setting(
        db,
        workspace_id,
        kind="character",
        name="林墨",
        content="沉默寡言的侦探",
        source="第一章手稿",
    )

    assert len(entry.id) == 32
    assert entry.workspace_id == workspace_id
    assert entry.kind == "character"
    assert entry.name == "林墨"
    assert entry.content == "沉默寡言的侦探"
    assert entry.source == "第一章手稿"
    assert entry.current_version == 1
    assert entry.created_at is not None
    assert entry.updated_at is not None

    with db.workspace_session(workspace_id) as session:
        stored = session.get(SettingEntry, entry.id)
        assert stored is not None
        assert stored.current_version == 1
        versions = (
            session.query(SettingVersion)
            .filter_by(entry_id=entry.id)
            .order_by(SettingVersion.version)
            .all()
        )
    assert len(versions) == 1
    assert versions[0].version == 1
    assert versions[0].content == "沉默寡言的侦探"
    assert versions[0].reason == "initial"
    assert versions[0].actor == "第一章手稿"
    assert versions[0].created_at is not None


def test_add_setting_default_source_is_author(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    entry = add_setting(
        db,
        workspace_id,
        kind="world",
        name="世界观",
        content="灵气复苏三百年",
    )

    assert entry.source == "作者"
    history = list_setting_history(db, workspace_id, entry.id)
    assert [version.actor for version in history] == ["作者"]


@pytest.mark.parametrize("kind", ["teaser", "", "WORLD"])
def test_add_setting_rejects_invalid_kind(tmp_path: Path, monkeypatch, kind: str) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()

    with pytest.raises(NovelError) as exc_info:
        add_setting(db, workspace_id, kind=kind, name="x", content="y")
    assert exc_info.value.code is ErrorCode.USAGE_ERROR
    assert "invalid kind" in exc_info.value.message
    assert list_settings(db, workspace_id) == []


@pytest.mark.parametrize("name", ["", "   "])
def test_add_setting_rejects_blank_name(tmp_path: Path, monkeypatch, name: str) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()

    with pytest.raises(NovelError) as exc_info:
        add_setting(db, workspace_id, kind="character", name=name, content="y")
    assert exc_info.value.code is ErrorCode.USAGE_ERROR
    assert "setting name must not be empty" in exc_info.value.message
    assert list_settings(db, workspace_id) == []


@pytest.mark.parametrize(
    "name",
    [
        "first line\nsecond line",
        "first line\rsecond line",
        "first line\r\nsecond line",
        "first line\u2028second line",
        "first line\u2029second line",
        "first line\x0bsecond line",
        "first line\x0csecond line",
        "first line\n",
    ],
)
def test_add_setting_rejects_newline_name(tmp_path: Path, monkeypatch, name: str) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()

    with pytest.raises(NovelError) as exc_info:
        add_setting(db, workspace_id, kind="character", name=name, content="y")
    assert exc_info.value.code is ErrorCode.USAGE_ERROR
    assert "must not contain newlines" in exc_info.value.message
    assert list_settings(db, workspace_id) == []


@pytest.mark.parametrize("content", ["", "   "])
def test_add_setting_rejects_blank_content(
    tmp_path: Path, monkeypatch, content: str
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()

    with pytest.raises(NovelError) as exc_info:
        add_setting(db, workspace_id, kind="world", name="x", content=content)
    assert exc_info.value.code is ErrorCode.USAGE_ERROR
    assert "setting content must not be empty" in exc_info.value.message
    assert list_settings(db, workspace_id) == []


def test_add_setting_unknown_workspace_is_not_found(
    tmp_path: Path, monkeypatch
) -> None:
    _create_workspace(tmp_path, monkeypatch)
    db = _db()

    with pytest.raises(NovelError) as exc_info:
        add_setting(db, "nope", kind="character", name="x", content="y")
    assert exc_info.value.code is ErrorCode.NOT_FOUND
    assert "workspace not found" in exc_info.value.message


def test_list_settings_orders_and_filters(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    first = add_setting(
        db, workspace_id, kind="character", name="林墨", content="侦探"
    )
    second = add_setting(
        db, workspace_id, kind="relation", name="林墨与江晚", content="旧识"
    )
    third = add_setting(
        db, workspace_id, kind="character", name="江晚", content="法医"
    )

    all_entries = list_settings(db, workspace_id)
    assert all_entries == sorted(all_entries, key=lambda entry: (entry.created_at, entry.id))
    assert {entry.id for entry in all_entries} == {first.id, second.id, third.id}

    characters = list_settings(db, workspace_id, kind="character")
    expected_characters = [
        entry for entry in all_entries if entry.kind == "character"
    ]
    assert [entry.id for entry in characters] == [
        entry.id for entry in expected_characters
    ]
    assert all(entry.kind == "character" for entry in characters)

    relations = list_settings(db, workspace_id, kind="relation")
    assert [entry.id for entry in relations] == [second.id]

    assert list_settings(db, workspace_id, kind="timeline") == []


def test_list_settings_rejects_unknown_kind(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()

    with pytest.raises(NovelError) as exc_info:
        list_settings(db, workspace_id, kind="teaser")
    assert exc_info.value.code is ErrorCode.USAGE_ERROR
    assert "invalid kind" in exc_info.value.message


def test_get_setting_returns_entry_or_not_found(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    entry = add_setting(
        db, workspace_id, kind="timeline", name="时间线", content="开篇在雨夜"
    )

    fetched = get_setting(db, workspace_id, entry.id)
    assert fetched.id == entry.id
    assert fetched.name == "时间线"

    with pytest.raises(NovelError) as exc_info:
        get_setting(db, workspace_id, "deadbeefdeadbeefdeadbeefdeadbeef")
    assert exc_info.value.code is ErrorCode.NOT_FOUND
    assert "setting not found" in exc_info.value.message


def test_revise_setting_bumps_version_and_syncs_content(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    entry = add_setting(
        db,
        workspace_id,
        kind="character",
        name="林墨",
        content="初版设定",
        source="第一章手稿",
    )

    revised = revise_setting(
        db,
        workspace_id,
        entry.id,
        content="修订后的设定",
        reason="角色弧线调整",
        actor="责编",
    )
    assert revised.id == entry.id
    assert revised.content == "修订后的设定"
    assert revised.current_version == 2
    assert revised.updated_at is not None

    with db.workspace_session(workspace_id) as session:
        stored = session.get(SettingEntry, entry.id)
        assert stored is not None
        assert stored.content == "修订后的设定"
        assert stored.current_version == 2
        versions = (
            session.query(SettingVersion)
            .filter_by(entry_id=entry.id)
            .order_by(SettingVersion.version)
            .all()
        )
    assert [version.version for version in versions] == [1, 2]
    assert versions[1].content == "修订后的设定"
    assert versions[1].reason == "角色弧线调整"
    assert versions[1].actor == "责编"

    third = revise_setting(
        db,
        workspace_id,
        entry.id,
        content="第三版设定",
        reason="终稿确认",
        actor="总编",
    )
    assert third.current_version == 3
    assert [version.version for version in list_setting_history(db, workspace_id, entry.id)] == [
        1,
        2,
        3,
    ]


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        ("", "有理由"),
        ("   ", "有理由"),
        ("有内容", ""),
        ("有内容", "   "),
    ],
)
def test_revise_setting_rejects_blank_content_or_reason(
    tmp_path: Path, monkeypatch, content: str, reason: str
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    entry = add_setting(
        db, workspace_id, kind="world", name="世界观", content="原设定"
    )

    with pytest.raises(NovelError) as exc_info:
        revise_setting(
            db,
            workspace_id,
            entry.id,
            content=content,
            reason=reason,
            actor="作者",
        )
    assert exc_info.value.code is ErrorCode.USAGE_ERROR
    assert "must not be empty" in exc_info.value.message

    fetched = get_setting(db, workspace_id, entry.id)
    assert fetched.content == "原设定"
    assert fetched.current_version == 1
    assert len(list_setting_history(db, workspace_id, entry.id)) == 1


def test_revise_setting_unknown_setting_is_not_found(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()

    with pytest.raises(NovelError) as exc_info:
        revise_setting(
            db,
            workspace_id,
            "deadbeefdeadbeefdeadbeefdeadbeef",
            content="x",
            reason="y",
            actor="作者",
        )
    assert exc_info.value.code is ErrorCode.NOT_FOUND
    assert "setting not found" in exc_info.value.message


def test_list_setting_history_orders_versions(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    entry = add_setting(
        db, workspace_id, kind="relation", name="师徒", content="v1 师徒"
    )
    revise_setting(
        db,
        workspace_id,
        entry.id,
        content="v2 师徒",
        reason="第一次修订",
        actor="写手",
    )
    revise_setting(
        db,
        workspace_id,
        entry.id,
        content="v3 师徒",
        reason="第二次修订",
        actor="责编",
    )

    history = list_setting_history(db, workspace_id, entry.id)
    assert [version.version for version in history] == [1, 2, 3]
    assert [version.content for version in history] == ["v1 师徒", "v2 师徒", "v3 师徒"]
    assert [version.reason for version in history] == ["initial", "第一次修订", "第二次修订"]
    assert [version.actor for version in history] == ["作者", "写手", "责编"]


def test_list_setting_history_unknown_setting_is_not_found(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()

    with pytest.raises(NovelError) as exc_info:
        list_setting_history(db, workspace_id, "deadbeefdeadbeefdeadbeefdeadbeef")
    assert exc_info.value.code is ErrorCode.NOT_FOUND
    assert "setting not found" in exc_info.value.message


def test_settings_are_isolated_between_workspaces(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_a = _create_workspace(tmp_path, monkeypatch, "甲书")
    workspace_b = _create_workspace(tmp_path, monkeypatch, "乙书")
    db = _db()
    entry = add_setting(
        db, workspace_a, kind="character", name="林墨", content="甲书秘密"
    )

    assert list_settings(db, workspace_b) == []
    with pytest.raises(NovelError) as exc_info:
        get_setting(db, workspace_b, entry.id)
    assert exc_info.value.code is ErrorCode.NOT_FOUND
    with pytest.raises(NovelError) as exc_info:
        revise_setting(
            db,
            workspace_b,
            entry.id,
            content="x",
            reason="y",
            actor="作者",
        )
    assert exc_info.value.code is ErrorCode.NOT_FOUND
    with pytest.raises(NovelError) as exc_info:
        list_setting_history(db, workspace_b, entry.id)
    assert exc_info.value.code is ErrorCode.NOT_FOUND

    fetched = get_setting(db, workspace_a, entry.id)
    assert fetched.content == "甲书秘密"
    assert fetched.current_version == 1


def test_setting_entry_model_columns() -> None:
    columns = set(SettingEntry.__table__.columns.keys())
    assert columns == {
        "id",
        "workspace_id",
        "kind",
        "name",
        "content",
        "source",
        "current_version",
        "created_at",
        "updated_at",
    }


def test_setting_version_model_columns() -> None:
    columns = set(SettingVersion.__table__.columns.keys())
    assert columns == {
        "id",
        "entry_id",
        "version",
        "content",
        "reason",
        "actor",
        "created_at",
    }
    table = SettingVersion.__table__
    assert isinstance(table, Table)
    assert any(
        constraint.name == "uq_setting_versions_entry_version"
        for constraint in table.constraints
    )


def test_setting_upgrades_pre_migration_workspace(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    path = workspace_db_path(settings, workspace_id)
    connection = sqlite3.connect(path)
    connection.execute("DROP TABLE IF EXISTS setting_entries")
    connection.execute("DROP TABLE IF EXISTS setting_versions")
    connection.execute("DELETE FROM alembic_version")
    connection.execute("INSERT INTO alembic_version (version_num) VALUES ('5b5bdeb4ed9d')")
    connection.commit()
    connection.close()

    db = DB(settings)
    entry = add_setting(
        db,
        workspace_id,
        kind="timeline",
        name="旧库时间线",
        content="升级后仍可用",
    )
    assert entry.current_version == 1
    assert [version.version for version in list_setting_history(db, workspace_id, entry.id)] == [
        1
    ]
    with db.workspace_session(workspace_id) as session:
        assert session.get(SettingEntry, entry.id) is not None
        assert session.query(SettingVersion).filter_by(entry_id=entry.id).count() == 1
