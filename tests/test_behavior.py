"""Behavior timeline: model surface, migration, and service semantics."""

import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.behavior import (
    current_behavior_state,
    list_behavior_timeline,
    record_behavior_entry,
)
from novel_editorial.core.config import load_settings
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.store.db import DB, workspace_db_path
from novel_editorial.store.models import BehaviorTimeline

runner = CliRunner()

PRE_BEHAVIOR_HEAD = "9c3a71b5d2e4"


def _create_workspace(tmp_path: Path, monkeypatch) -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["works", "create", "留痕之书", "--genre", "悬疑"])
    assert result.exit_code == 0, result.output
    match = re.search(r"created workspace (\w+):", result.output)
    assert match is not None
    return match.group(1)


def test_behavior_timeline_model_columns_exact() -> None:
    assert set(BehaviorTimeline.__table__.columns.keys()) == {
        "id",
        "workspace_id",
        "agent_id",
        "kind",
        "target",
        "summary",
        "before_value",
        "after_value",
        "source",
        "created_at",
    }


def test_new_workspace_has_behavior_timeline_table(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    with sqlite3.connect(workspace_db_path(settings, workspace_id)) as connection:
        tables = [
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        ]
    assert "behavior_timeline" in tables
    assert list_behavior_timeline(DB(settings), workspace_id) == []


def test_legacy_workspace_upgrades_and_rebuilds_behavior_timeline(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    path = workspace_db_path(settings, workspace_id)

    connection = sqlite3.connect(path)
    try:
        connection.execute("DROP TABLE behavior_timeline")
        connection.execute("DELETE FROM alembic_version")
        connection.execute(
            "INSERT INTO alembic_version (version_num) VALUES (?)", (PRE_BEHAVIOR_HEAD,)
        )
        connection.commit()
    finally:
        connection.close()

    reopened = runner.invoke(app, ["agents", "show", workspace_id])
    assert reopened.exit_code == 0, reopened.output

    entry = record_behavior_entry(
        DB(load_settings()),
        workspace_id,
        agent_id="写手",
        kind="viewpoint",
        target="rule_a",
        summary="升级后仍可用",
    )
    entries = list_behavior_timeline(DB(load_settings()), workspace_id)
    assert [listed.id for listed in entries] == [entry.id]
    assert entries[0].summary == "升级后仍可用"


def test_migration_recreates_missing_behavior_timeline_indexes(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    path = workspace_db_path(settings, workspace_id)

    connection = sqlite3.connect(path)
    try:
        connection.execute("DROP INDEX ix_behavior_timeline_workspace_id")
        connection.execute("DROP INDEX ix_behavior_timeline_agent_id")
        connection.execute("DELETE FROM alembic_version")
        connection.execute(
            "INSERT INTO alembic_version (version_num) VALUES (?)", (PRE_BEHAVIOR_HEAD,)
        )
        connection.commit()
    finally:
        connection.close()

    reopened = runner.invoke(app, ["agents", "show", workspace_id])
    assert reopened.exit_code == 0, reopened.output

    with sqlite3.connect(path) as connection:
        indexes = [
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='index'")
        ]
    assert "ix_behavior_timeline_workspace_id" in indexes
    assert "ix_behavior_timeline_agent_id" in indexes


def test_record_and_list_roundtrip_oldest_first(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    first = record_behavior_entry(
        db,
        workspace_id,
        agent_id="写手",
        kind="viewpoint",
        target="rule_a",
        summary="坚持该立场",
        before_value="无",
        after_value="坚持",
        source="refusal:rule_a",
    )
    second = record_behavior_entry(
        db,
        workspace_id,
        agent_id="责编",
        kind="impression",
        target="写手",
        summary="盯逻辑",
    )

    entries = list_behavior_timeline(db, workspace_id)
    assert [entry.id for entry in entries] == [first.id, second.id]
    assert entries[0].workspace_id == workspace_id
    assert entries[0].agent_id == "写手"
    assert entries[0].kind == "viewpoint"
    assert entries[0].target == "rule_a"
    assert entries[0].summary == "坚持该立场"
    assert entries[0].before_value == "无"
    assert entries[0].after_value == "坚持"
    assert entries[0].source == "refusal:rule_a"
    assert entries[0].created_at is not None
    assert entries[1].before_value is None
    assert entries[1].after_value is None
    assert entries[1].source == ""
    assert entries[1].summary == "盯逻辑"


def test_record_rejects_unknown_kind_as_usage_error(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    with pytest.raises(NovelError) as excinfo:
        record_behavior_entry(db, workspace_id, agent_id="写手", kind="mood", target="rule_a")
    assert excinfo.value.code == ErrorCode.USAGE_ERROR
    assert list_behavior_timeline(db, workspace_id) == []


@pytest.mark.parametrize(
    ("agent_id", "target"),
    [("", "rule_a"), ("写手", "")],
)
def test_record_rejects_empty_agent_id_or_target_as_usage_error(
    tmp_path: Path, monkeypatch, agent_id: str, target: str
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    with pytest.raises(NovelError) as excinfo:
        record_behavior_entry(
            db, workspace_id, agent_id=agent_id, kind="viewpoint", target=target
        )
    assert excinfo.value.code == ErrorCode.USAGE_ERROR
    assert list_behavior_timeline(db, workspace_id) == []


def test_current_behavior_state_returns_latest_per_group(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    record_behavior_entry(
        db,
        workspace_id,
        agent_id="写手",
        kind="viewpoint",
        target="rule_a",
        summary="第一次拒绝",
        after_value="坚持该立场",
    )
    latest_viewpoint = record_behavior_entry(
        db,
        workspace_id,
        agent_id="写手",
        kind="viewpoint",
        target="rule_a",
        summary="作者推翻后调整",
        before_value="坚持该立场",
        after_value="按作者决定执行",
    )
    relationship = record_behavior_entry(
        db,
        workspace_id,
        agent_id="写手",
        kind="relationship",
        target="作者",
        summary="稿子被退回",
    )
    impression = record_behavior_entry(
        db,
        workspace_id,
        agent_id="责编",
        kind="impression",
        target="写手",
        summary="盯逻辑",
    )

    state = current_behavior_state(db, workspace_id)
    assert set(state) == {
        ("写手", "viewpoint", "rule_a"),
        ("写手", "relationship", "作者"),
        ("责编", "impression", "写手"),
    }
    assert state[("写手", "viewpoint", "rule_a")].id == latest_viewpoint.id
    assert state[("写手", "relationship", "作者")].id == relationship.id
    assert state[("责编", "impression", "写手")].id == impression.id

    writer_state = current_behavior_state(db, workspace_id, agent_id="写手")
    assert set(writer_state) == {
        ("写手", "viewpoint", "rule_a"),
        ("写手", "relationship", "作者"),
    }
    viewpoint_state = current_behavior_state(db, workspace_id, kind="viewpoint")
    assert set(viewpoint_state) == {("写手", "viewpoint", "rule_a")}


def test_list_behavior_timeline_limit_and_filters(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    for index in range(4):
        record_behavior_entry(
            db,
            workspace_id,
            agent_id="写手",
            kind="viewpoint",
            target="rule_a",
            summary=f"viewpoint-{index}",
        )
    record_behavior_entry(
        db,
        workspace_id,
        agent_id="责编",
        kind="impression",
        target="写手",
        summary="impression-0",
    )

    assert [
        entry.summary for entry in list_behavior_timeline(db, workspace_id, limit=2)
    ] == ["viewpoint-0", "viewpoint-1"]
    assert [
        entry.summary
        for entry in list_behavior_timeline(db, workspace_id, agent_id="写手")
    ] == ["viewpoint-0", "viewpoint-1", "viewpoint-2", "viewpoint-3"]
    assert [
        entry.summary
        for entry in list_behavior_timeline(db, workspace_id, kind="impression")
    ] == ["impression-0"]
    assert (
        list_behavior_timeline(db, workspace_id, agent_id="写手", kind="impression") == []
    )


def test_timeline_insertion_order_not_timestamp_based(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    fixed_time = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None) -> datetime:
            return fixed_time

    monkeypatch.setattr("novel_editorial.store.models.datetime", FrozenDateTime)
    db = DB(load_settings())
    first = record_behavior_entry(
        db, workspace_id, agent_id="写手", kind="impression", target="a", summary="first"
    )
    second = record_behavior_entry(
        db, workspace_id, agent_id="写手", kind="impression", target="b", summary="second"
    )

    entries = list_behavior_timeline(db, workspace_id)
    assert [entry.id for entry in entries] == [first.id, second.id]
    assert entries[0].created_at == entries[1].created_at == fixed_time.replace(tzinfo=None)


@pytest.mark.parametrize("empty_kind", [[], (), ""])
def test_list_behavior_timeline_empty_kind_means_no_filter(
    tmp_path: Path, monkeypatch, empty_kind
) -> None:
    """An empty kind sequence or empty string is equivalent to no kind filter."""
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    record_behavior_entry(
        db,
        workspace_id,
        agent_id="写手",
        kind="viewpoint",
        target="rule_a",
        summary="v0",
    )
    record_behavior_entry(
        db,
        workspace_id,
        agent_id="写手",
        kind="viewpoint",
        target="rule_a",
        summary="v1",
    )
    record_behavior_entry(
        db,
        workspace_id,
        agent_id="责编",
        kind="impression",
        target="写手",
        summary="i0",
    )

    expected = ["v0", "v1", "i0"]
    assert [
        entry.summary for entry in list_behavior_timeline(db, workspace_id, kind=empty_kind)
    ] == expected
    assert [
        entry.summary
        for entry in list_behavior_timeline(db, workspace_id, kind=empty_kind, limit=2)
    ] == ["v0", "v1"]


def test_list_behavior_timeline_multi_kind_ignores_kind_order_and_keeps_rowid(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    fixed_time = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None) -> datetime:
            return fixed_time

    monkeypatch.setattr("novel_editorial.store.models.datetime", FrozenDateTime)
    db = DB(load_settings())
    first = record_behavior_entry(
        db, workspace_id, agent_id="写手", kind="viewpoint", target="rule_a", summary="v0"
    )
    second = record_behavior_entry(
        db, workspace_id, agent_id="写手", kind="impression", target="责编", summary="i0"
    )
    third = record_behavior_entry(
        db, workspace_id, agent_id="写手", kind="relationship", target="作者", summary="r0"
    )

    entries = list_behavior_timeline(
        db, workspace_id, kind=["relationship", "impression", "viewpoint"]
    )
    assert [entry.id for entry in entries] == [first.id, second.id, third.id]


def test_list_behavior_timeline_multi_kind_applies_one_unified_limit(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    fixed_time = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None) -> datetime:
            return fixed_time

    monkeypatch.setattr("novel_editorial.store.models.datetime", FrozenDateTime)
    db = DB(load_settings())
    record_behavior_entry(
        db, workspace_id, agent_id="写手", kind="viewpoint", target="rule_a", summary="v0"
    )
    record_behavior_entry(
        db, workspace_id, agent_id="写手", kind="impression", target="责编", summary="i0"
    )
    record_behavior_entry(
        db, workspace_id, agent_id="写手", kind="relationship", target="作者", summary="r0"
    )

    entries = list_behavior_timeline(
        db, workspace_id, kind=("viewpoint", "impression", "relationship"), limit=2
    )
    assert [entry.summary for entry in entries] == ["v0", "i0"]
