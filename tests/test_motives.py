"""N27 S1/S2 tests: motive table, services, CLI, and migration idempotency."""

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.config import load_settings
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.core.motives import (
    clear_motive,
    decay_motives,
    derive_motives,
    list_motives,
    strengthen_motive,
)
from novel_editorial.store.db import DB, run_migrations, workspace_db_path
from novel_editorial.store.models import (
    ROLE_PERSONALITY_PARAMS,
    Agent,
    AgentMotive,
    AgentRole,
    MotiveKind,
)

runner = CliRunner()
PRE_MOTIVE_HEAD = "9833bf1054ab"
PRE_MOTIVE_UNIQUE_HEAD = "c1557045673c"


def _create_workspace(
    tmp_path: Path, monkeypatch, title: str = "动机之书"
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


def _column_names(path: Path, table: str) -> set[str]:
    connection = sqlite3.connect(path)
    try:
        rows = connection.execute(f'PRAGMA table_info("{table}")').fetchall()
        return {row[1] for row in rows}
    finally:
        connection.close()


def _unique_source_index_names(path: Path) -> set[str]:
    """Unique indexes over (workspace_id, agent_id, kind, source) on agent_motives."""
    connection = sqlite3.connect(path)
    try:
        names: set[str] = set()
        for row in connection.execute('PRAGMA index_list("agent_motives")'):
            if not row[2]:
                continue
            columns = [
                column[2]
                for column in connection.execute(
                    f'PRAGMA index_info("{row[1]}")'
                )
            ]
            if columns[:4] == [
                "workspace_id",
                "agent_id",
                "kind",
                "source",
            ]:
                names.add(row[1])
        return names
    finally:
        connection.close()


def test_motive_model_columns_and_no_todo_semantics() -> None:
    columns = set(AgentMotive.__table__.columns.keys())
    assert columns == {
        "id",
        "workspace_id",
        "agent_id",
        "kind",
        "content",
        "strength",
        "source",
        "created_at",
        "last_touched_at",
    }
    todo_fields = {
        "due_at",
        "deadline",
        "assigned_to",
        "claimable",
        "claimed_by",
        "status",
        "resolved_at",
        "done",
    }
    assert columns.isdisjoint(todo_fields)


def test_motive_kind_enum_values() -> None:
    assert [kind.value for kind in MotiveKind] == [
        "foreshadow",
        "conflict",
        "goal",
        "impression",
        "pending_issue",
    ]


def test_derive_draft_generated_writer_goal(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _agent(db, workspace_id, AgentRole.WRITER)

    motives = derive_motives(
        db, workspace_id, "draft_generated", {"agent_id": writer.id}
    )

    assert len(motives) == 1
    motive = motives[0]
    assert motive.workspace_id == workspace_id
    assert motive.agent_id == writer.id
    assert motive.kind == MotiveKind.GOAL
    assert motive.content == "新章已交"
    assert motive.strength == 100
    assert motive.source == "event:draft_generated"
    assert motive.created_at == motive.last_touched_at


def test_derive_refusal_pending_issue_for_context_agent(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    editor = _agent(db, workspace_id, AgentRole.EDITOR)

    motives = derive_motives(
        db, workspace_id, "refusal", {"agent_id": editor.id}
    )

    assert motives[0].agent_id == editor.id
    assert motives[0].kind == MotiveKind.PENDING_ISSUE
    assert motives[0].content == "被拒了，这事还惦记着"
    assert motives[0].source == "event:refusal"


def test_derive_review_conflict_reviewer_foreshadow(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    reviewer = _agent(db, workspace_id, AgentRole.REVIEWER)

    motives = derive_motives(
        db, workspace_id, "review_conflict", {"agent_id": reviewer.id}
    )

    assert motives[0].agent_id == reviewer.id
    assert motives[0].kind == MotiveKind.FORESHADOW
    assert motives[0].content == "审稿时发现前后矛盾，先记一笔"


def test_derive_falls_back_to_role_agent_when_agent_missing(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()

    writer_goal = derive_motives(db, workspace_id, "draft_generated")
    assert writer_goal[0].agent_id == _agent(db, workspace_id, AgentRole.WRITER).id

    reviewer_foreshadow = derive_motives(db, workspace_id, "review_conflict")
    assert reviewer_foreshadow[0].agent_id == _agent(
        db, workspace_id, AgentRole.REVIEWER
    ).id


def test_derive_unknown_event_kind_is_usage_error(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()

    with pytest.raises(NovelError) as exc:
        derive_motives(db, workspace_id, "talk_send")
    assert exc.value.code == ErrorCode.USAGE_ERROR
    assert "unknown motive event kind" in exc.value.message


def test_derive_refusal_without_agent_is_usage_error(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()

    with pytest.raises(NovelError) as exc:
        derive_motives(db, workspace_id, "refusal")
    assert exc.value.code == ErrorCode.USAGE_ERROR
    assert "agent_id" in exc.value.message


def test_derive_unknown_agent_is_not_found(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()

    with pytest.raises(NovelError) as exc:
        derive_motives(
            db,
            workspace_id,
            "refusal",
            {"agent_id": "f" * 32},
        )
    assert exc.value.code == ErrorCode.NOT_FOUND


def test_derive_unknown_workspace_is_not_found(
    tmp_path: Path, monkeypatch
) -> None:
    _create_workspace(tmp_path, monkeypatch)
    db = _db()

    with pytest.raises(NovelError) as exc:
        derive_motives(db, "f" * 32, "draft_generated")
    assert exc.value.code == ErrorCode.NOT_FOUND


def test_derive_same_event_twice_merges_into_one_motive(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _agent(db, workspace_id, AgentRole.WRITER)

    first = derive_motives(
        db, workspace_id, "draft_generated", {"agent_id": writer.id}
    )[0]
    second = derive_motives(
        db, workspace_id, "draft_generated", {"agent_id": writer.id}
    )[0]

    assert second.id == first.id
    remaining = list_motives(db, workspace_id)
    assert len(remaining) == 1
    assert remaining[0].id == first.id
    assert remaining[0].content == "新章已交"
    assert remaining[0].source == "event:draft_generated"


def test_derive_repeat_with_fallback_role_merges(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()

    first = derive_motives(db, workspace_id, "draft_generated")[0]
    second = derive_motives(db, workspace_id, "draft_generated")[0]

    assert second.id == first.id
    assert [motive.id for motive in list_motives(db, workspace_id)] == [first.id]


def test_derive_repeat_strengthens_and_refreshes_existing(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    motive = derive_motives(
        db, workspace_id, "draft_generated", {"agent_id": writer.id}
    )[0]
    with db.workspace_session(workspace_id) as session:
        stored = session.get(AgentMotive, motive.id)
        assert stored is not None
        stored.strength = 60
        stored.last_touched_at = datetime.now(UTC) - timedelta(days=1)
        session.commit()

    repeated = derive_motives(
        db, workspace_id, "draft_generated", {"agent_id": writer.id}
    )[0]

    assert repeated.id == motive.id
    boost = load_settings().memory_rehearsal_boost
    assert repeated.strength == 60 + boost
    assert repeated.last_touched_at > datetime.now(UTC) - timedelta(seconds=5)
    assert len(list_motives(db, workspace_id)) == 1


def test_derive_repeat_strength_clamps_at_100(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    motive = derive_motives(
        db, workspace_id, "draft_generated", {"agent_id": writer.id}
    )[0]
    with db.workspace_session(workspace_id) as session:
        stored = session.get(AgentMotive, motive.id)
        assert stored is not None
        stored.strength = 95
        session.commit()

    repeated = derive_motives(
        db, workspace_id, "draft_generated", {"agent_id": writer.id}
    )[0]

    assert repeated.strength == 100
    assert [motive.id for motive in list_motives(db, workspace_id)] == [motive.id]


def test_derive_distinct_agent_kind_source_are_distinct_motives(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    editor = _agent(db, workspace_id, AgentRole.EDITOR)

    writer_goal = derive_motives(
        db, workspace_id, "draft_generated", {"agent_id": writer.id}
    )[0]
    editor_goal = derive_motives(
        db, workspace_id, "draft_generated", {"agent_id": editor.id}
    )[0]
    writer_issue = derive_motives(
        db, workspace_id, "refusal", {"agent_id": writer.id}
    )[0]
    reviewer_foreshadow = derive_motives(db, workspace_id, "review_conflict")[0]

    assert len({writer_goal.id, editor_goal.id, writer_issue.id, reviewer_foreshadow.id}) == 4
    assert len(list_motives(db, workspace_id)) == 4

    again = derive_motives(
        db, workspace_id, "draft_generated", {"agent_id": writer.id}
    )[0]
    assert again.id == writer_goal.id
    assert len(list_motives(db, workspace_id)) == 4


def test_derive_after_clear_creates_fresh_motive_not_resurrected(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    first = derive_motives(
        db, workspace_id, "draft_generated", {"agent_id": writer.id}
    )[0]

    assert clear_motive(db, workspace_id, first.id).id == first.id
    second = derive_motives(
        db, workspace_id, "draft_generated", {"agent_id": writer.id}
    )[0]

    assert second.id != first.id
    remaining = list_motives(db, workspace_id)
    assert len(remaining) == 1
    assert remaining[0].id == second.id


def test_strengthen_motive_clamps_to_0_100(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    motive = derive_motives(db, workspace_id, "draft_generated")[0]

    assert strengthen_motive(db, workspace_id, motive.id, 50).strength == 100

    with db.workspace_session(workspace_id) as session:
        stored = session.get(AgentMotive, motive.id)
        assert stored is not None
        stored.strength = 40
        session.commit()

    assert strengthen_motive(db, workspace_id, motive.id, 20).strength == 60
    assert strengthen_motive(db, workspace_id, motive.id, 1000).strength == 100
    assert strengthen_motive(db, workspace_id, motive.id, -1000).strength == 0
    assert list_motives(db, workspace_id)[0].strength == 0


def test_strengthen_motive_not_found(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()

    with pytest.raises(NovelError) as exc:
        strengthen_motive(db, workspace_id, "a" * 32, 10)
    assert exc.value.code == ErrorCode.NOT_FOUND


def test_decay_same_day_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    derive_motives(db, workspace_id, "draft_generated")

    assert decay_motives(db, workspace_id) == []
    assert decay_motives(db, workspace_id) == []


def test_decay_uses_n17_whole_day_semantics(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    motive = derive_motives(db, workspace_id, "draft_generated")[0]
    with db.workspace_session(workspace_id) as session:
        stored = session.get(AgentMotive, motive.id)
        assert stored is not None
        stored.last_touched_at = datetime.now(UTC) - timedelta(days=3)
        session.commit()

    changed = decay_motives(db, workspace_id)

    assert len(changed) == 1
    rate = load_settings().memory_decay_per_day
    assert changed[0].strength == 100 - 3 * rate
    assert decay_motives(db, workspace_id) == []


def test_decay_clamps_at_zero_and_never_deletes(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    motive = derive_motives(db, workspace_id, "draft_generated")[0]
    with db.workspace_session(workspace_id) as session:
        stored = session.get(AgentMotive, motive.id)
        assert stored is not None
        stored.last_touched_at = datetime.now(UTC) - timedelta(days=30)
        session.commit()

    changed = decay_motives(db, workspace_id)

    assert changed[0].strength == 0
    remaining = list_motives(db, workspace_id)
    assert len(remaining) == 1
    assert remaining[0].id == motive.id


def test_clear_motive_removes_only_target(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    first = derive_motives(db, workspace_id, "draft_generated")[0]
    second = derive_motives(db, workspace_id, "review_conflict")[0]

    cleared = clear_motive(db, workspace_id, first.id)

    assert cleared.id == first.id
    assert [motive.id for motive in list_motives(db, workspace_id)] == [second.id]


def test_clear_motive_unknown_is_not_found(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()

    with pytest.raises(NovelError) as exc:
        clear_motive(db, workspace_id, "b" * 32)
    assert exc.value.code == ErrorCode.NOT_FOUND


def test_list_motives_orders_strength_desc_then_created_at_asc(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    editor = _agent(db, workspace_id, AgentRole.EDITOR)
    writer_goal = derive_motives(db, workspace_id, "draft_generated")[0]
    refused = derive_motives(
        db, workspace_id, "refusal", {"agent_id": editor.id}
    )[0]
    foreshadow = derive_motives(db, workspace_id, "review_conflict")[0]

    base = datetime(2026, 8, 1, tzinfo=UTC)
    with db.workspace_session(workspace_id) as session:
        by_content = {
            row.content: row for row in session.query(AgentMotive).all()
        }
        writer_goal_row = by_content["新章已交"]
        refused_row = by_content["被拒了，这事还惦记着"]
        foreshadow_row = by_content["审稿时发现前后矛盾，先记一笔"]
        writer_goal_row.strength = 50
        refused_row.strength = 80
        foreshadow_row.strength = 80
        writer_goal_row.created_at = base
        refused_row.created_at = base + timedelta(hours=1)
        foreshadow_row.created_at = base + timedelta(hours=2)
        session.commit()

    ordered = list_motives(db, workspace_id)
    assert [row.content for row in ordered] == [
        "被拒了，这事还惦记着",
        "审稿时发现前后矛盾，先记一笔",
        "新章已交",
    ]
    assert [row.id for row in ordered] == [
        refused.id,
        foreshadow.id,
        writer_goal.id,
    ]

    editor_only = list_motives(db, workspace_id, agent_id=editor.id)
    assert [row.id for row in editor_only] == [refused.id]
    writer_only = list_motives(db, workspace_id, agent_id=writer_goal.agent_id)
    assert [row.id for row in writer_only] == [writer_goal.id]


def test_motive_lifecycle_end_to_end(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _agent(db, workspace_id, AgentRole.WRITER)

    motive = derive_motives(
        db, workspace_id, "draft_generated", {"agent_id": writer.id}
    )[0]
    assert strengthen_motive(db, workspace_id, motive.id, 5).strength == 100

    with db.workspace_session(workspace_id) as session:
        stored = session.get(AgentMotive, motive.id)
        assert stored is not None
        stored.strength = 60
        stored.last_touched_at = datetime.now(UTC) - timedelta(days=2)
        session.commit()

    changed = decay_motives(db, workspace_id)
    assert len(changed) == 1
    assert changed[0].strength == 50

    assert clear_motive(db, workspace_id, motive.id).id == motive.id
    assert list_motives(db, workspace_id) == []


def test_agent_motives_unique_constraint_blocks_duplicate_source_row(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    path = workspace_db_path(load_settings(), workspace_id)
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "INSERT INTO agent_motives "
            "(id, workspace_id, agent_id, kind, content, strength, source, "
            "created_at, last_touched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "a" * 32,
                workspace_id,
                writer.id,
                MotiveKind.GOAL.value,
                "新章已交",
                100,
                "event:draft_generated",
                "2026-08-23 00:00:00",
                "2026-08-23 00:00:00",
            ),
        )
        connection.commit()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO agent_motives "
                "(id, workspace_id, agent_id, kind, content, strength, source, "
                "created_at, last_touched_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "b" * 32,
                    workspace_id,
                    writer.id,
                    MotiveKind.GOAL.value,
                    "新章已交",
                    100,
                    "event:draft_generated",
                    "2026-08-23 00:01:00",
                    "2026-08-23 00:01:00",
                ),
            )
            connection.commit()
    finally:
        connection.close()


def test_motives_migration_dedupes_existing_duplicate_rows(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    path = workspace_db_path(settings, workspace_id)
    connection = sqlite3.connect(path)
    agent_id = connection.execute(
        "SELECT id FROM agents WHERE role=? ORDER BY created_at, id LIMIT 1",
        (AgentRole.WRITER,),
    ).fetchone()[0]
    connection.close()

    command.downgrade(
        _alembic_config(f"sqlite:///{path}"), PRE_MOTIVE_UNIQUE_HEAD
    )
    connection = sqlite3.connect(path)
    try:
        for row_id, created_at, strength in (
            ("1" * 32, "2026-08-01 00:00:00", 100),
            ("2" * 32, "2026-08-02 00:00:00", 40),
        ):
            connection.execute(
                "INSERT INTO agent_motives "
                "(id, workspace_id, agent_id, kind, content, strength, source, "
                "created_at, last_touched_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    row_id,
                    workspace_id,
                    agent_id,
                    MotiveKind.GOAL.value,
                    "新章已交",
                    strength,
                    "event:draft_generated",
                    created_at,
                    created_at,
                ),
            )
        connection.commit()
    finally:
        connection.close()

    run_migrations(f"sqlite:///{path}")

    connection = sqlite3.connect(path)
    try:
        rows = connection.execute(
            "SELECT id, workspace_id, agent_id, kind, content, strength, source "
            "FROM agent_motives"
        ).fetchall()
    finally:
        connection.close()
    assert len(rows) == 1
    assert rows[0][0] == "1" * 32
    assert rows[0][4] == "新章已交"
    assert rows[0][5] == 100
    assert rows[0][6] == "event:draft_generated"
    assert len(_unique_source_index_names(path)) == 1


def test_derive_motives_conflict_path_strengthens_existing_row(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    settings = load_settings()
    rival_id = "c" * 32
    real_commit = Session.commit
    armed = {"insert": True}

    def conflicting_commit(self) -> None:
        if not armed["insert"]:
            real_commit(self)
            return
        armed["insert"] = False
        path = workspace_db_path(settings, workspace_id)
        connection = sqlite3.connect(path)
        try:
            connection.execute(
                "INSERT INTO agent_motives "
                "(id, workspace_id, agent_id, kind, content, strength, source, "
                "created_at, last_touched_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    rival_id,
                    workspace_id,
                    writer.id,
                    MotiveKind.GOAL.value,
                    "新章已交",
                    50,
                    "event:draft_generated",
                    "2026-08-23 00:00:00",
                    "2026-08-23 00:00:00",
                ),
            )
            connection.commit()
        finally:
            connection.close()
        raise IntegrityError(
            "INSERT", {}, Exception("UNIQUE constraint failed")
        )

    monkeypatch.setattr(Session, "commit", conflicting_commit)
    result = derive_motives(
        db, workspace_id, "draft_generated", {"agent_id": writer.id}
    )

    assert len(result) == 1
    assert result[0].id == rival_id
    boost = load_settings().memory_rehearsal_boost
    assert result[0].strength == 50 + boost
    assert [motive.id for motive in list_motives(db, workspace_id)] == [rival_id]


def test_motives_cli_list_end_to_end(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()

    empty = runner.invoke(app, ["motives", "list", workspace_id])
    assert empty.exit_code == 0, empty.output
    assert empty.output.strip() == "no motives yet"

    writer = _agent(db, workspace_id, AgentRole.WRITER)
    derive_motives(db, workspace_id, "draft_generated", {"agent_id": writer.id})

    listed = runner.invoke(app, ["motives", "list", workspace_id])
    assert listed.exit_code == 0, listed.output
    assert "[写手] [goal] strength=100 source=event:draft_generated" in listed.output
    assert "新章已交" in listed.output
    assert "touched=" in listed.output

    filtered = runner.invoke(app, ["motives", "list", workspace_id, "--agent", "写手"])
    assert filtered.exit_code == 0, filtered.output
    assert "新章已交" in filtered.output

    other = runner.invoke(app, ["motives", "list", workspace_id, "--agent", "审稿"])
    assert other.exit_code == 0, other.output
    assert other.output.strip() == "no motives for 审稿"


def test_motives_cli_error_paths(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)

    missing_workspace = runner.invoke(
        app, ["motives", "list", "f" * 32]
    )
    assert missing_workspace.exit_code == 1
    assert "workspace not found" in missing_workspace.output

    missing_agent = runner.invoke(
        app, ["motives", "list", workspace_id, "--agent", "不存在的人"]
    )
    assert missing_agent.exit_code == 1
    assert "agent not found" in missing_agent.output


def test_motives_migration_roundtrip(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    path = workspace_db_path(settings, workspace_id)

    assert "agent_motives" in _table_names(path)
    motive_columns = _column_names(path, "agent_motives")
    assert {
        "id",
        "workspace_id",
        "agent_id",
        "kind",
        "content",
        "strength",
        "source",
        "created_at",
        "last_touched_at",
    } <= motive_columns
    assert {
        "proactivity",
        "stubbornness",
        "talkativeness",
        "patience",
    } <= _column_names(path, "agents")

    command.downgrade(_alembic_config(f"sqlite:///{path}"), PRE_MOTIVE_HEAD)
    assert "agent_motives" not in _table_names(path)
    assert {
        "proactivity",
        "stubbornness",
        "talkativeness",
        "patience",
    }.isdisjoint(_column_names(path, "agents"))

    run_migrations(f"sqlite:///{path}")
    assert "agent_motives" in _table_names(path)
    assert {
        "proactivity",
        "stubbornness",
        "talkativeness",
        "patience",
    } <= _column_names(path, "agents")

    db = DB(settings)
    for role, params in ROLE_PERSONALITY_PARAMS.items():
        agent = _agent(db, workspace_id, role)
        assert (
            agent.proactivity,
            agent.stubbornness,
            agent.talkativeness,
            agent.patience,
        ) == params


def test_motives_migration_legacy_replay_keeps_existing_data(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    db = DB(settings)
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    motive = derive_motives(
        db, workspace_id, "draft_generated", {"agent_id": writer.id}
    )[0]
    path = workspace_db_path(settings, workspace_id)
    connection = sqlite3.connect(path)
    connection.execute("DELETE FROM alembic_version")
    connection.execute(
        "INSERT INTO alembic_version (version_num) VALUES (?)",
        (PRE_MOTIVE_HEAD,),
    )
    connection.commit()
    connection.close()

    run_migrations(f"sqlite:///{path}")

    assert "agent_motives" in _table_names(path)
    with db.workspace_session(workspace_id) as session:
        stored = session.get(AgentMotive, motive.id)
        assert stored is not None
        assert stored.content == "新章已交"
