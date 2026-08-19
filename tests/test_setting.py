import json
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import Table
from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.config import load_settings
from novel_editorial.core.draft import build_memory_pack
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.core.retrieval import LAYER_SETTING
from novel_editorial.core.setting import (
    KIND_LABELS,
    SETTING_KINDS,
    add_setting,
    check_settings,
    get_setting,
    list_setting_history,
    list_settings,
    revise_setting,
    settings_section,
)
from novel_editorial.core.views import build_editor_view
from novel_editorial.events import EventType
from novel_editorial.llm.embeddings import build_embedding_client
from novel_editorial.store.db import DB, workspace_db_path
from novel_editorial.store.events import list_events
from novel_editorial.store.models import MemoryEmbedding, SettingEntry, SettingVersion

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


@pytest.mark.parametrize("source", ["", "   "])
def test_add_setting_rejects_blank_source(
    tmp_path: Path, monkeypatch, source: str
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()

    with pytest.raises(NovelError) as exc_info:
        add_setting(
            db,
            workspace_id,
            kind="character",
            name="林墨",
            content="沉默寡言的侦探",
            source=source,
        )
    assert exc_info.value.code is ErrorCode.USAGE_ERROR
    assert "setting source must not be empty" in exc_info.value.message
    assert list_settings(db, workspace_id) == []


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


def test_revise_setting_records_system_event(tmp_path: Path, monkeypatch) -> None:
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

    revise_setting(
        db,
        workspace_id,
        entry.id,
        content="修订后的设定",
        reason="角色弧线调整",
        actor="责编",
    )

    events = list_events(db, workspace_id)
    revised_events = [
        event
        for event in events
        if json.loads(event.payload).get("kind") == "setting_revised"
    ]
    assert len(revised_events) == 1
    assert revised_events[0].type == EventType.SYSTEM
    assert revised_events[0].actor == "责编"
    assert json.loads(revised_events[0].payload) == {
        "kind": "setting_revised",
        "setting_id": entry.id,
        "name": "林墨",
        "version": 2,
        "actor": "责编",
        "reason": "角色弧线调整",
    }


def test_revise_setting_event_failure_keeps_revision_and_warns(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    entry = add_setting(
        db, workspace_id, kind="world", name="世界观", content="原设定"
    )

    def boom(*args, **kwargs):
        raise RuntimeError("event write failed")

    monkeypatch.setattr("novel_editorial.core.setting.record_event", boom)
    revised = revise_setting(
        db,
        workspace_id,
        entry.id,
        content="修订后的设定",
        reason="有理由",
        actor="作者",
    )

    assert revised.current_version == 2
    assert revised.content == "修订后的设定"
    captured = capsys.readouterr()
    assert "warning: setting revision event skipped" in captured.err
    assert "event write failed" in captured.err
    with db.workspace_session(workspace_id) as session:
        stored = session.get(SettingEntry, entry.id)
        assert stored is not None
        assert stored.current_version == 2
        assert stored.content == "修订后的设定"
    assert [version.version for version in list_setting_history(db, workspace_id, entry.id)] == [
        1,
        2,
    ]


def test_setting_revision_events_are_isolated_between_workspaces(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_a = _create_workspace(tmp_path, monkeypatch, "甲书")
    workspace_b = _create_workspace(tmp_path, monkeypatch, "乙书")
    db = _db()
    entry = add_setting(
        db, workspace_a, kind="character", name="林墨", content="甲书设定"
    )
    revise_setting(
        db,
        workspace_a,
        entry.id,
        content="甲书修订",
        reason="甲书理由",
        actor="作者",
    )

    assert list_events(db, workspace_a) != []
    assert list_events(db, workspace_b) == []


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


@pytest.mark.parametrize("actor", ["", "   "])
def test_revise_setting_rejects_blank_actor(
    tmp_path: Path, monkeypatch, actor: str
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
            content="修订后的设定",
            reason="有理由",
            actor=actor,
        )
    assert exc_info.value.code is ErrorCode.USAGE_ERROR
    assert "setting actor must not be empty" in exc_info.value.message

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


@pytest.mark.smoke
def test_setting_cli_end_to_end(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)

    added = runner.invoke(
        app,
        [
            "setting",
            "add",
            workspace_id,
            "--kind",
            "人物",
            "--name",
            "林墨",
            "--content",
            "沉默寡言的侦探",
            "--source",
            "第一章手稿",
        ],
    )
    assert added.exit_code == 0, added.output
    assert added.output.startswith("added ")
    setting_id = added.output.split()[1]
    assert "[人物] 林墨 v1" in added.output

    listed = runner.invoke(app, ["setting", "list", workspace_id])
    assert listed.exit_code == 0, listed.output
    assert f"{setting_id} [人物] 林墨 v1 沉默寡言的侦探" in listed.output

    shown = runner.invoke(app, ["setting", "show", workspace_id, setting_id])
    assert shown.exit_code == 0, shown.output
    assert "林墨 [人物] v1" in shown.output
    assert "source: 第一章手稿" in shown.output
    assert "沉默寡言的侦探" in shown.output

    revised = runner.invoke(
        app,
        [
            "setting",
            "revise",
            workspace_id,
            setting_id,
            "--content",
            "表面冷漠、暗地护短",
            "--reason",
            "角色弧线调整",
            "--actor",
            "责编",
        ],
    )
    assert revised.exit_code == 0, revised.output
    assert f"revised {setting_id} 林墨 v2" in revised.output

    shown_again = runner.invoke(app, ["setting", "show", workspace_id, setting_id])
    assert shown_again.exit_code == 0, shown_again.output
    assert "林墨 [人物] v2" in shown_again.output
    assert "表面冷漠、暗地护短" in shown_again.output

    history = runner.invoke(app, ["setting", "history", workspace_id, setting_id])
    assert history.exit_code == 0, history.output
    assert "v1 第一章手稿 initial 沉默寡言的侦探" in history.output
    assert "v2 责编 角色弧线调整 表面冷漠、暗地护短" in history.output


@pytest.mark.parametrize(
    ("label", "kind"),
    [
        ("人物", "character"),
        ("关系", "relation"),
        ("时间线", "timeline"),
        ("世界观", "world"),
    ],
)
def test_setting_add_accepts_chinese_kind_labels(
    tmp_path: Path, monkeypatch, label: str, kind: str
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(
        app,
        [
            "setting",
            "add",
            workspace_id,
            "--kind",
            label,
            "--name",
            "名称",
            "--content",
            "内容",
        ],
    )
    assert result.exit_code == 0, result.output
    setting_id = result.output.split()[1]
    assert get_setting(_db(), workspace_id, setting_id).kind == kind


@pytest.mark.parametrize("label", ["teaser", "作者", ""])
def test_setting_add_rejects_unknown_kind_label(
    tmp_path: Path, monkeypatch, label: str
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(
        app,
        [
            "setting",
            "add",
            workspace_id,
            "--kind",
            label,
            "--name",
            "x",
            "--content",
            "y",
        ],
    )
    assert result.exit_code == 2
    assert "invalid kind" in result.output
    assert (
        runner.invoke(app, ["setting", "list", workspace_id]).output.strip()
        == "no settings yet"
    )


def test_setting_list_empty_and_kind_filter(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    empty = runner.invoke(app, ["setting", "list", workspace_id])
    assert empty.exit_code == 0
    assert empty.output.strip() == "no settings yet"

    assert (
        runner.invoke(
            app,
            [
                "setting",
                "add",
                workspace_id,
                "--kind",
                "人物",
                "--name",
                "林墨",
                "--content",
                "侦探",
            ],
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(
            app,
            [
                "setting",
                "add",
                workspace_id,
                "--kind",
                "世界观",
                "--name",
                "灵气复苏",
                "--content",
                "三百年",
            ],
        ).exit_code
        == 0
    )

    filtered = runner.invoke(app, ["setting", "list", workspace_id, "--kind", "世界观"])
    assert filtered.exit_code == 0, filtered.output
    assert "灵气复苏" in filtered.output
    assert "林墨" not in filtered.output


def test_setting_cli_error_paths(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)

    blank_name = runner.invoke(
        app,
        [
            "setting",
            "add",
            workspace_id,
            "--kind",
            "人物",
            "--name",
            "   ",
            "--content",
            "x",
        ],
    )
    assert blank_name.exit_code == 2
    assert "setting name must not be empty" in blank_name.output

    blank_content = runner.invoke(
        app,
        [
            "setting",
            "add",
            workspace_id,
            "--kind",
            "人物",
            "--name",
            "x",
            "--content",
            "   ",
        ],
    )
    assert blank_content.exit_code == 2
    assert "setting content must not be empty" in blank_content.output

    blank_source = runner.invoke(
        app,
        [
            "setting",
            "add",
            workspace_id,
            "--kind",
            "人物",
            "--name",
            "x",
            "--content",
            "y",
            "--source",
            "   ",
        ],
    )
    assert blank_source.exit_code == 2
    assert "setting source must not be empty" in blank_source.output

    assert (
        runner.invoke(app, ["setting", "list", workspace_id]).output.strip()
        == "no settings yet"
    )

    missing_workspace = runner.invoke(app, ["setting", "list", "nope"])
    assert missing_workspace.exit_code == 1
    assert "workspace not found" in missing_workspace.output

    missing_id = "deadbeefdeadbeefdeadbeefdeadbeef"
    show_missing = runner.invoke(app, ["setting", "show", workspace_id, missing_id])
    assert show_missing.exit_code == 1
    assert "setting not found" in show_missing.output

    history_missing = runner.invoke(
        app, ["setting", "history", workspace_id, missing_id]
    )
    assert history_missing.exit_code == 1
    assert "setting not found" in history_missing.output

    revise_missing = runner.invoke(
        app,
        [
            "setting",
            "revise",
            workspace_id,
            missing_id,
            "--content",
            "x",
            "--reason",
            "y",
        ],
    )
    assert revise_missing.exit_code == 1
    assert "setting not found" in revise_missing.output


def test_setting_revise_cli_rejects_blank_content_or_reason(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    added = runner.invoke(
        app,
        [
            "setting",
            "add",
            workspace_id,
            "--kind",
            "人物",
            "--name",
            "林墨",
            "--content",
            "原设定",
        ],
    )
    assert added.exit_code == 0, added.output
    setting_id = added.output.split()[1]

    blank_content = runner.invoke(
        app,
        [
            "setting",
            "revise",
            workspace_id,
            setting_id,
            "--content",
            "   ",
            "--reason",
            "有理由",
        ],
    )
    assert blank_content.exit_code == 2
    assert "setting content must not be empty" in blank_content.output

    blank_reason = runner.invoke(
        app,
        [
            "setting",
            "revise",
            workspace_id,
            setting_id,
            "--content",
            "新设定",
            "--reason",
            "   ",
        ],
    )
    assert blank_reason.exit_code == 2
    assert "setting reason must not be empty" in blank_reason.output

    shown = runner.invoke(app, ["setting", "show", workspace_id, setting_id])
    assert shown.exit_code == 0, shown.output
    assert "林墨 [人物] v1" in shown.output
    assert "原设定" in shown.output


def test_setting_revise_default_actor_is_author(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    added = runner.invoke(
        app,
        [
            "setting",
            "add",
            workspace_id,
            "--kind",
            "人物",
            "--name",
            "林墨",
            "--content",
            "原设定",
        ],
    )
    assert added.exit_code == 0, added.output
    setting_id = added.output.split()[1]

    revised = runner.invoke(
        app,
        [
            "setting",
            "revise",
            workspace_id,
            setting_id,
            "--content",
            "新设定",
            "--reason",
            "作者修订",
        ],
    )
    assert revised.exit_code == 0, revised.output
    assert f"revised {setting_id} 林墨 v2" in revised.output

    history = runner.invoke(app, ["setting", "history", workspace_id, setting_id])
    assert history.exit_code == 0, history.output
    assert "v2 作者 作者修订 新设定" in history.output


@pytest.mark.parametrize(
    "content",
    [
        "第一段：雨夜侦探，习惯沉默\n第二段：只会对熟人露出破绽",
        "第一段：雨夜侦探，习惯沉默\r\n第二段：只会对熟人露出破绽",
    ],
)
def test_multiline_setting_content_renders_single_line_in_sections(
    tmp_path: Path, monkeypatch, content: str
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    entry = add_setting(
        db,
        workspace_id,
        kind="character",
        name="沈夜",
        content=content,
        source="作者",
    )
    assert entry.current_version == 1

    collapsed = " ".join(content.split())
    expected = f"- [人物] 沈夜 v1 {collapsed}（来源: 作者）"
    fragments = [fragment.strip() for fragment in content.splitlines() if fragment.strip()]

    for block in (
        settings_section(db, workspace_id),
        build_memory_pack(db, workspace_id),
        build_editor_view(db, workspace_id),
    ):
        stripped_lines = [line.strip() for line in block.splitlines()]
        assert expected in block.splitlines()
        for fragment in fragments:
            assert fragment not in stripped_lines


def test_check_settings_empty_state_is_a_single_line(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()

    report = check_settings(db, workspace_id)

    assert report == "settings: 0 entries (0 revised)；同名冲突：无"
    assert len(report.splitlines()) == 1


def test_check_settings_lists_revised_entries_in_kind_order(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    world = add_setting(
        db, workspace_id, kind="world", name="世界观", content="灵气复苏", source="大纲"
    )
    char = add_setting(
        db, workspace_id, kind="character", name="沈夜", content="侦探", source="手稿"
    )
    revise_setting(
        db, workspace_id, world.id, content="灵气复苏三百年", reason="调整", actor="作者"
    )
    revise_setting(
        db, workspace_id, char.id, content="表面冷漠", reason="调整", actor="作者"
    )

    report = check_settings(db, workspace_id)
    lines = report.splitlines()

    assert lines[0] == "settings: 2 entries (2 revised)"
    assert lines[1] == "陈旧（已修订）："
    assert lines[2] == "- 沈夜（人物）v2 表面冷漠（来源: 手稿）—— 已修订，旧版本见 history"
    world_line = (
        "- 世界观（世界观）v2 灵气复苏三百年（来源: 大纲）—— 已修订，旧版本见 history"
    )
    assert lines[3] == world_line
    assert len(lines) == 4
    assert "同名冲突：" not in report


def test_check_settings_revised_content_collapses_whitespace(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    entry = add_setting(
        db,
        workspace_id,
        kind="character",
        name="沈夜",
        content="初版设定",
        source="作者",
    )
    revise_setting(
        db,
        workspace_id,
        entry.id,
        content="第一段：雨夜侦探\n第二段：习惯沉默",
        reason="调整",
        actor="责编",
    )

    report = check_settings(db, workspace_id)

    assert (
        "- 沈夜（人物）v2 第一段：雨夜侦探 第二段：习惯沉默（来源: 作者）"
        "—— 已修订，旧版本见 history" in report
    )


def test_check_settings_same_name_conflict_across_kinds(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    add_setting(db, workspace_id, kind="character", name="沈夜", content="侦探", source="A")
    add_setting(db, workspace_id, kind="world", name="沈夜", content="古城", source="B")

    report = check_settings(db, workspace_id)
    lines = report.splitlines()

    assert lines[0] == "settings: 2 entries (0 revised)"
    assert lines[1] == "同名冲突："
    assert "- 「沈夜」：人物 v1 与 世界观 v1 —— 同名条目，请确认是否矛盾" in lines


def test_check_settings_same_name_conflict_joins_three_or_more(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    add_setting(db, workspace_id, kind="character", name="沈夜", content="侦探", source="A")
    add_setting(db, workspace_id, kind="timeline", name="沈夜", content="旧历", source="B")
    add_setting(db, workspace_id, kind="world", name="沈夜", content="古城", source="C")

    report = check_settings(db, workspace_id)

    assert (
        "- 「沈夜」：人物 v1 与 时间线 v1 与 世界观 v1"
        " —— 同名条目，请确认是否矛盾" in report
    )


def test_check_settings_distinct_names_have_no_conflict_section(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    add_setting(db, workspace_id, kind="character", name="沈夜", content="侦探", source="A")
    add_setting(db, workspace_id, kind="character", name="江晚", content="法医", source="B")

    report = check_settings(db, workspace_id)

    assert report == "settings: 2 entries (0 revised)；同名冲突：无"


def test_check_settings_isolated_between_workspaces(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_a = _create_workspace(tmp_path, monkeypatch, "甲书")
    workspace_b = _create_workspace(tmp_path, monkeypatch, "乙书")
    db = _db()
    entry = add_setting(
        db, workspace_a, kind="character", name="沈夜", content="甲书", source="A"
    )
    revise_setting(
        db, workspace_a, entry.id, content="甲书修订", reason="调整", actor="作者"
    )

    report_a = check_settings(db, workspace_a)
    assert report_a.startswith("settings: 1 entries (1 revised)")
    assert "沈夜（人物）v2 甲书修订" in report_a
    assert check_settings(db, workspace_b) == "settings: 0 entries (0 revised)；同名冲突：无"


def test_check_settings_unknown_workspace_is_not_found(
    tmp_path: Path, monkeypatch
) -> None:
    _create_workspace(tmp_path, monkeypatch)
    db = _db()

    with pytest.raises(NovelError) as exc_info:
        check_settings(db, "nope")
    assert exc_info.value.code is ErrorCode.NOT_FOUND
    assert "workspace not found" in exc_info.value.message


def test_setting_check_cli_end_to_end(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    added = runner.invoke(
        app,
        [
            "setting",
            "add",
            workspace_id,
            "--kind",
            "人物",
            "--name",
            "沈夜",
            "--content",
            "初版设定",
        ],
    )
    assert added.exit_code == 0, added.output
    setting_id = added.output.split()[1]
    revised = runner.invoke(
        app,
        [
            "setting",
            "revise",
            workspace_id,
            setting_id,
            "--content",
            "修订版",
            "--reason",
            "角色调整",
            "--actor",
            "责编",
        ],
    )
    assert revised.exit_code == 0, revised.output
    duplicated = runner.invoke(
        app,
        [
            "setting",
            "add",
            workspace_id,
            "--kind",
            "世界观",
            "--name",
            "沈夜",
            "--content",
            "古城设定",
        ],
    )
    assert duplicated.exit_code == 0, duplicated.output

    checked = runner.invoke(app, ["setting", "check", workspace_id])
    assert checked.exit_code == 0, checked.output
    assert "settings: 2 entries (1 revised)" in checked.output
    assert "陈旧（已修订）：" in checked.output
    assert "沈夜（人物）v2 修订版（来源: 作者）—— 已修订，旧版本见 history" in checked.output
    assert "同名冲突：" in checked.output
    assert "- 「沈夜」：人物 v2 与 世界观 v1 —— 同名条目，请确认是否矛盾" in checked.output

    missing = runner.invoke(app, ["setting", "check", "nope"])
    assert missing.exit_code == 1
    assert "workspace not found" in missing.output


def test_add_setting_syncs_embedding(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    db = _db()

    entry = add_setting(
        db,
        workspace_id,
        kind="character",
        name="林墨",
        content="沉默寡言的侦探",
        source="第一章手稿",
    )

    with db.workspace_session(workspace_id) as session:
        row = (
            session.query(MemoryEmbedding)
            .filter_by(layer=LAYER_SETTING, source_id=entry.id)
            .first()
        )
        assert row is not None
        assert json.loads(row.vector) == build_embedding_client(settings).embed(
            "沉默寡言的侦探"
        )
        assert row.dim == settings.embedding_dim
        assert row.workspace_id == workspace_id


def test_revise_setting_syncs_new_content(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    db = _db()
    entry = add_setting(
        db,
        workspace_id,
        kind="character",
        name="林墨",
        content="初版设定",
        source="第一章手稿",
    )

    revise_setting(
        db,
        workspace_id,
        entry.id,
        content="修订后的设定",
        reason="角色弧线调整",
        actor="责编",
    )

    with db.workspace_session(workspace_id) as session:
        rows = (
            session.query(MemoryEmbedding)
            .filter_by(layer=LAYER_SETTING, source_id=entry.id)
            .all()
        )
        assert len(rows) == 1
        assert json.loads(rows[0].vector) == build_embedding_client(settings).embed(
            "修订后的设定"
        )


def test_add_setting_embedding_failure_keeps_setting_and_warns(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()

    def boom(*args, **kwargs):
        raise RuntimeError("embedding backend down")

    monkeypatch.setattr("novel_editorial.core.retrieval.upsert_embedding", boom)
    entry = add_setting(
        db,
        workspace_id,
        kind="world",
        name="世界观",
        content="灵气复苏三百年",
    )

    assert entry.current_version == 1
    assert entry.content == "灵气复苏三百年"
    captured = capsys.readouterr()
    assert "warning: embedding index skipped" in captured.err
    assert "embedding backend down" in captured.err
    with db.workspace_session(workspace_id) as session:
        assert session.query(MemoryEmbedding).count() == 0
        assert session.get(SettingEntry, entry.id) is not None


def test_revise_setting_embedding_failure_keeps_revision_and_warns(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    entry = add_setting(
        db,
        workspace_id,
        kind="world",
        name="世界观",
        content="原设定",
    )

    def boom(*args, **kwargs):
        raise RuntimeError("embedding backend down")

    monkeypatch.setattr("novel_editorial.core.retrieval.upsert_embedding", boom)
    revised = revise_setting(
        db,
        workspace_id,
        entry.id,
        content="修订后的设定",
        reason="有理由",
        actor="作者",
    )

    assert revised.current_version == 2
    assert revised.content == "修订后的设定"
    captured = capsys.readouterr()
    assert "warning: embedding index skipped" in captured.err
    assert "embedding backend down" in captured.err
    with db.workspace_session(workspace_id) as session:
        stored = session.get(SettingEntry, entry.id)
        assert stored is not None
        assert stored.current_version == 2
        assert stored.content == "修订后的设定"
