"""N28-C S1 tests: personality drift, effective params, and migration."""

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.behavior import list_behavior_timeline
from novel_editorial.core.config import load_settings
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.core.evolution import (
    DRIFT_FIELDS,
    apply_param_drift,
    effective_param,
    rebase_param_drift,
)
from novel_editorial.store.db import DB, run_migrations, workspace_db_path
from novel_editorial.store.models import (
    DRIFT_PARAM_FIELDS,
    PERSONALITY_PARAM_FIELDS,
    Agent,
    AgentRole,
)

runner = CliRunner()
PRE_DRIFT_HEAD = "6ebe40261d2545fe"


def _create_workspace(
    tmp_path: Path, monkeypatch, title: str = "演化之书"
) -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["works", "create", title])
    assert result.exit_code == 0, result.output
    return result.output.split()[2].rstrip(":")


def _db() -> DB:
    return DB(load_settings())


def _agent(db: DB, workspace_id: str, role: str) -> Agent:
    with db.workspace_session(workspace_id) as session:
        agent = (
            session.query(Agent)
            .filter_by(workspace_id=workspace_id, role=role)
            .first()
        )
        assert agent is not None
        return agent


def _drift(db: DB, workspace_id: str, agent_id: str, field: str) -> int:
    column = DRIFT_FIELDS[field]
    with db.workspace_session(workspace_id) as session:
        agent = session.query(Agent).filter_by(id=agent_id).first()
        assert agent is not None
        return int(getattr(agent, column))


def _alembic_config(url: str) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    return config


def _freeze_time(monkeypatch, value: datetime) -> None:
    """Freeze store.models.datetime so behavior traces get a controlled time."""

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None) -> datetime:
            return value

    monkeypatch.setattr("novel_editorial.store.models.datetime", FrozenDateTime)


def _column_names(path: Path, table: str) -> set[str]:
    connection = sqlite3.connect(path)
    try:
        rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    finally:
        connection.close()
    return {row[1] for row in rows}


def test_drift_fields_mirror_personality_fields() -> None:
    assert set(DRIFT_FIELDS) == set(PERSONALITY_PARAM_FIELDS)
    for field, column in DRIFT_FIELDS.items():
        assert column == f"drift_{field}"
        assert column in DRIFT_PARAM_FIELDS


def test_effective_param_combines_baseline_and_drift(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    assert effective_param(writer, "proactivity") == 5

    apply_param_drift(db, workspace_id, writer.id, "proactivity", 3)
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    assert effective_param(writer, "proactivity") == 8


def test_effective_param_clamps_baseline_plus_drift_to_0_and_10(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    apply_param_drift(db, workspace_id, writer.id, "proactivity", -10)
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    assert effective_param(writer, "proactivity") == 0

    apply_param_drift(db, workspace_id, writer.id, "proactivity", 20)
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    assert effective_param(writer, "proactivity") == 10


def test_effective_param_unknown_field_usage_error(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    writer = _agent(_db(), workspace_id, AgentRole.WRITER)
    with pytest.raises(NovelError) as excinfo:
        effective_param(writer, "creativity")
    assert excinfo.value.code == ErrorCode.USAGE_ERROR
    assert "unknown personality field" in excinfo.value.message


def test_apply_param_drift_clamps_delta_to_drift_bounds(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _agent(db, workspace_id, AgentRole.WRITER)

    apply_param_drift(db, workspace_id, writer.id, "patience", 100)
    assert _drift(db, workspace_id, writer.id, "patience") == 10

    apply_param_drift(db, workspace_id, writer.id, "patience", -100)
    assert _drift(db, workspace_id, writer.id, "patience") == -10


def test_apply_param_drift_writes_viewpoint_trace_with_source(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _agent(db, workspace_id, AgentRole.WRITER)

    entry = apply_param_drift(
        db, workspace_id, writer.id, "stubbornness", 2, event="rejected"
    )

    assert entry.agent_id == writer.id
    assert entry.kind == "viewpoint"
    assert entry.target == "stubbornness"
    assert entry.source == "drift:rejected"
    assert entry.before_value == "0"
    assert entry.after_value == "2"
    assert "stubbornness drift +0 -> +2" in entry.summary
    assert "event=rejected" in entry.summary

    traces = list_behavior_timeline(db, workspace_id)
    assert [trace.id for trace in traces] == [entry.id]
    assert traces[0].source == "drift:rejected"


def test_apply_param_drift_unknown_field_usage_error(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    with pytest.raises(NovelError) as excinfo:
        apply_param_drift(db, workspace_id, writer.id, "creativity", 1)
    assert excinfo.value.code == ErrorCode.USAGE_ERROR


def test_apply_param_drift_unknown_agent_not_found(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    with pytest.raises(NovelError) as excinfo:
        apply_param_drift(db, workspace_id, "nope", "proactivity", 1)
    assert excinfo.value.code == ErrorCode.NOT_FOUND
    assert "agent not found" in excinfo.value.message


def test_apply_param_drift_rejects_non_integer_delta(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    with pytest.raises(NovelError) as excinfo:
        apply_param_drift(
            db, workspace_id, writer.id, "proactivity", "2"  # type: ignore[arg-type]
        )
    assert excinfo.value.code == ErrorCode.USAGE_ERROR
    assert "delta must be an integer" in excinfo.value.message


def test_rebase_settles_toward_zero_by_whole_days(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    base = datetime(2026, 8, 20, 12, 0, 0, tzinfo=UTC)
    _freeze_time(monkeypatch, base)
    apply_param_drift(db, workspace_id, writer.id, "proactivity", 5)
    apply_param_drift(db, workspace_id, writer.id, "patience", -5)

    _freeze_time(monkeypatch, base + timedelta(days=2, hours=1))
    settled = rebase_param_drift(
        db, workspace_id, writer.id, now=base + timedelta(days=2, hours=1)
    )
    assert settled["proactivity"] == 3
    assert settled["patience"] == -3

    # A fraction of a day after the last touch does not count as a whole day.
    _freeze_time(monkeypatch, base + timedelta(days=2, hours=23))
    settled = rebase_param_drift(
        db, workspace_id, writer.id, now=base + timedelta(days=2, hours=23)
    )
    assert settled["proactivity"] == 3
    assert settled["patience"] == -3


def test_rebase_is_idempotent_for_same_now(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    base = datetime(2026, 8, 20, 12, 0, 0, tzinfo=UTC)
    _freeze_time(monkeypatch, base)
    apply_param_drift(db, workspace_id, writer.id, "proactivity", 5)
    now = base + timedelta(days=3)

    _freeze_time(monkeypatch, now)
    first = rebase_param_drift(db, workspace_id, writer.id, now=now)
    second = rebase_param_drift(db, workspace_id, writer.id, now=now)
    assert first == second
    assert second["proactivity"] == 2

    traces = list_behavior_timeline(db, workspace_id)
    rebase_traces = [trace for trace in traces if trace.source == "drift:rebase"]
    assert len(rebase_traces) == 1


def test_rebase_is_monotonic_and_never_crosses_zero(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    base = datetime(2026, 8, 20, 12, 0, 0, tzinfo=UTC)
    _freeze_time(monkeypatch, base)
    apply_param_drift(db, workspace_id, writer.id, "proactivity", 5)
    apply_param_drift(db, workspace_id, writer.id, "patience", -9)

    _freeze_time(monkeypatch, base + timedelta(days=100))
    settled = rebase_param_drift(
        db, workspace_id, writer.id, now=base + timedelta(days=100)
    )
    assert settled["proactivity"] == 0
    assert settled["patience"] == 0
    assert all(0 <= value <= 10 for value in settled.values())

    # A later touch can only move toward 0, never away from it.
    _freeze_time(monkeypatch, base + timedelta(days=101))
    later = rebase_param_drift(
        db, workspace_id, writer.id, now=base + timedelta(days=101)
    )
    assert later == settled


def test_rebase_without_any_touch_is_a_noop(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    now = datetime(2026, 8, 20, 12, 0, 0, tzinfo=UTC)
    settled = rebase_param_drift(db, workspace_id, writer.id, now=now)
    assert settled == {field: 0 for field in DRIFT_FIELDS}
    assert list_behavior_timeline(db, workspace_id) == []


def test_rebase_unknown_agent_not_found(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    with pytest.raises(NovelError) as excinfo:
        rebase_param_drift(_db(), workspace_id, "nope")
    assert excinfo.value.code == ErrorCode.NOT_FOUND


def test_agent_drift_columns_default_zero(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    with db.workspace_session(workspace_id) as session:
        agents = session.query(Agent).all()
    assert len(agents) == 4
    for agent in agents:
        for field in DRIFT_PARAM_FIELDS:
            assert getattr(agent, field) == 0


def test_migration_adds_drift_columns_backfills_zero_and_is_idempotent(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    path = workspace_db_path(settings, workspace_id)

    command.downgrade(_alembic_config(f"sqlite:///{path}"), PRE_DRIFT_HEAD)
    assert set(DRIFT_PARAM_FIELDS).isdisjoint(_column_names(path, "agents"))
    connection = sqlite3.connect(path)
    try:
        existing = connection.execute(
            "SELECT id, name FROM agents ORDER BY created_at, id"
        ).fetchall()
    finally:
        connection.close()
    assert len(existing) == 4

    run_migrations(f"sqlite:///{path}")
    columns = _column_names(path, "agents")
    assert set(DRIFT_PARAM_FIELDS) <= columns
    connection = sqlite3.connect(path)
    try:
        rows = connection.execute(
            "SELECT id, name, drift_proactivity, drift_stubbornness, "
            "drift_talkativeness, drift_patience FROM agents "
            "ORDER BY created_at, id"
        ).fetchall()
    finally:
        connection.close()
    assert [(row[0], row[1]) for row in rows] == [
        (row[0], row[1]) for row in existing
    ]
    for row in rows:
        assert row[2:] == (0, 0, 0, 0)

    # Replaying the chain with the columns already in place must be a no-op.
    run_migrations(f"sqlite:///{path}")
    assert _column_names(path, "agents") == columns


def test_migration_legacy_replay_keeps_existing_data_and_drift(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    db = _db()
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    apply_param_drift(db, workspace_id, writer.id, "proactivity", 4)
    path = workspace_db_path(settings, workspace_id)

    connection = sqlite3.connect(path)
    try:
        connection.execute("DELETE FROM alembic_version")
        connection.execute(
            "INSERT INTO alembic_version (version_num) VALUES (?)",
            (PRE_DRIFT_HEAD,),
        )
        connection.commit()
    finally:
        connection.close()

    run_migrations(f"sqlite:///{path}")
    assert set(DRIFT_PARAM_FIELDS) <= _column_names(path, "agents")
    with db.workspace_session(workspace_id) as session:
        stored = session.query(Agent).filter_by(id=writer.id).first()
        assert stored is not None
        assert stored.name == "写手"
        assert stored.drift_proactivity == 4
        assert stored.drift_stubbornness == 0
