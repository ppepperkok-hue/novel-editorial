import json
import sqlite3
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.config import load_settings
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.core.memory import (
    add_memory_note,
    apply_memory_decay,
    archive_memory_notes,
    delete_memory_note,
    effective_strength,
    list_archive_candidates,
    list_memory_notes,
    rehearse_memory_note,
    restore_memory_notes,
)
from novel_editorial.core.retrieval import LAYER_NOTE
from novel_editorial.core.setting import add_setting
from novel_editorial.llm.embeddings import build_embedding_client
from novel_editorial.store.db import DB, workspace_db_path
from novel_editorial.store.models import Agent, AgentMemory, MemoryEmbedding

runner = CliRunner()


def _create_workspace(tmp_path: Path, monkeypatch, title: str = "记忆之书") -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["works", "create", title])
    assert result.exit_code == 0, result.output
    return result.output.split()[2].rstrip(":")


def _memory_config(
    tmp_path: Path,
    monkeypatch,
    *,
    decay: int = 5,
    boost: int = 25,
    threshold: int = 20,
) -> None:
    (tmp_path / "config.toml").write_text(
        "[defaults]\n"
        f"memory_decay_per_day = {decay}\n"
        f"memory_rehearsal_boost = {boost}\n"
        f"memory_archive_threshold = {threshold}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))


def _writer_id(db: DB, workspace_id: str) -> str:
    with db.workspace_session(workspace_id) as session:
        writer = session.query(Agent).filter_by(workspace_id=workspace_id, role="writer").first()
        assert writer is not None
        return writer.id


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _add_raw_note(
    db: DB,
    workspace_id: str,
    agent_id: str,
    content: str,
    *,
    strength: int = 100,
    last_accessed_at: datetime | None = None,
    created_at: datetime | None = None,
) -> AgentMemory:
    with db.workspace_session(workspace_id) as session:
        note = AgentMemory(
            workspace_id=workspace_id,
            agent_id=agent_id,
            content=content,
            strength=strength,
            last_accessed_at=last_accessed_at or datetime.now(UTC),
            created_at=created_at or datetime.now(UTC),
        )
        session.add(note)
        session.commit()
        return note


@pytest.mark.smoke
def test_memory_note_persists_for_writer(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(
        app,
        [
            "memory",
            "note",
            workspace_id,
            "写手",
            "--content",
            "第三章钩子埋在下雨天",
            "--as",
            "写手",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "note added to 写手" in result.output

    settings = load_settings()
    db = DB(settings)
    with db.workspace_session(workspace_id) as session:
        writer = session.query(Agent).filter_by(workspace_id=workspace_id, role="writer").first()
        notes = session.query(AgentMemory).filter_by(workspace_id=workspace_id).all()
        assert writer is not None
        assert len(notes) == 1
        assert notes[0].agent_id == writer.id
        assert notes[0].content == "第三章钩子埋在下雨天"
        assert notes[0].created_at is not None


def test_memory_notes_partner_isolation_and_boss_view(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    assert (
        runner.invoke(
            app,
            ["memory", "note", workspace_id, "写手", "--content", "写手私藏", "--as", "写手"],
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(
            app,
            ["memory", "note", workspace_id, "责编", "--content", "责编私藏", "--as", "责编"],
        ).exit_code
        == 0
    )

    writer_notes = runner.invoke(app, ["memory", "notes", workspace_id, "写手"])
    assert writer_notes.exit_code == 0, writer_notes.output
    assert "写手私藏" in writer_notes.output
    assert "责编私藏" not in writer_notes.output

    editor_notes = runner.invoke(app, ["memory", "notes", workspace_id, "责编"])
    assert editor_notes.exit_code == 0, editor_notes.output
    assert "责编私藏" in editor_notes.output
    assert "写手私藏" not in editor_notes.output

    all_notes = runner.invoke(app, ["memory", "notes", workspace_id])
    assert all_notes.exit_code == 0, all_notes.output
    assert "写手私藏" in all_notes.output
    assert "责编私藏" in all_notes.output
    assert "[写手]" in all_notes.output
    assert "[责编]" in all_notes.output


def test_memory_note_and_notes_by_agent_id(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    db = DB(settings)
    with db.workspace_session(workspace_id) as session:
        writer = session.query(Agent).filter_by(workspace_id=workspace_id, role="writer").first()
        assert writer is not None
        writer_id = writer.id

    created = runner.invoke(
        app,
        ["memory", "note", workspace_id, writer_id, "--content", "按 id 记的", "--as", "写手"],
    )
    assert created.exit_code == 0, created.output
    listed = runner.invoke(app, ["memory", "notes", workspace_id, writer_id])
    assert listed.exit_code == 0, listed.output
    assert "按 id 记的" in listed.output


def test_memory_notes_empty(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(app, ["memory", "notes", workspace_id])
    assert result.exit_code == 0, result.output
    assert "no memory notes yet" in result.output
    single = runner.invoke(app, ["memory", "notes", workspace_id, "写手"])
    assert single.exit_code == 0, single.output
    assert "no notes for 写手" in single.output


def test_memory_note_unknown_agent_not_found(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(app, ["memory", "note", workspace_id, "nope", "--content", "x"])
    assert result.exit_code == 1
    assert "agent not found" in result.output


def test_memory_note_as_partner_writes_own_notes(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    created = runner.invoke(
        app,
        [
            "memory",
            "note",
            workspace_id,
            "写手",
            "--content",
            "写手自己的账本",
            "--as",
            "写手",
        ],
    )
    assert created.exit_code == 0, created.output
    assert "note added to 写手 by 写手" in created.output
    listed = runner.invoke(app, ["memory", "notes", workspace_id])
    assert listed.exit_code == 0, listed.output
    assert "写手自己的账本" in listed.output
    assert "[写手]" in listed.output


@pytest.mark.parametrize("alias", ["总编", "主编", "责编", "写手", "审稿"])
def test_memory_note_each_partner_alias_writes_own_note(
    tmp_path: Path, monkeypatch, alias: str
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    created = runner.invoke(
        app,
        ["memory", "note", workspace_id, alias, "--content", f"{alias}私有", "--as", alias],
    )
    assert created.exit_code == 0, created.output
    listed = runner.invoke(app, ["memory", "notes", workspace_id])
    assert listed.exit_code == 0, listed.output
    assert f"{alias}私有" in listed.output


@pytest.mark.parametrize("target", ["总编", "主编", "责编", "写手", "审稿"])
def test_memory_note_as_author_is_read_only(
    tmp_path: Path, monkeypatch, target: str
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    created = runner.invoke(
        app,
        ["memory", "note", workspace_id, target, "--content", "老板留言", "--as", "作者"],
    )
    assert created.exit_code == 2, created.output
    assert "作者只读" in created.output
    listed = runner.invoke(app, ["memory", "notes", workspace_id])
    assert listed.exit_code == 0, listed.output
    assert "老板留言" not in listed.output


def test_memory_note_invalid_actor_usage_error(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(
        app,
        ["memory", "note", workspace_id, "写手", "--content", "x", "--as", "路人"],
    )
    assert result.exit_code == 2
    assert "invalid actor" in result.output


@pytest.mark.parametrize("target", ["总编", "主编", "责编", "审稿"])
def test_memory_note_partner_cannot_write_other_partner(
    tmp_path: Path, monkeypatch, target: str
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(
        app,
        ["memory", "note", workspace_id, target, "--content", "x", "--as", "写手"],
    )
    assert result.exit_code == 2
    assert "may only write own notes" in result.output


def test_memory_note_missing_as_rejected_as_read_only_author(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    created = runner.invoke(
        app,
        ["memory", "note", workspace_id, "写手", "--content", "缺省即作者"],
    )
    assert created.exit_code == 2, created.output
    assert "作者只读" in created.output
    listed = runner.invoke(app, ["memory", "notes", workspace_id])
    assert listed.exit_code == 0, listed.output
    assert "缺省即作者" not in listed.output


def test_memory_note_valid_actor_unknown_target_not_found(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(
        app,
        ["memory", "note", workspace_id, "nope", "--content", "x", "--as", "写手"],
    )
    assert result.exit_code == 1
    assert "agent not found" in result.output


def test_memory_notes_prints_deletable_id(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    created = runner.invoke(
        app,
        ["memory", "note", workspace_id, "写手", "--content", "按 id 删", "--as", "写手"],
    )
    assert created.exit_code == 0, created.output
    listed = runner.invoke(app, ["memory", "notes", workspace_id])
    assert listed.exit_code == 0, listed.output
    lines = [line for line in listed.output.splitlines() if "按 id 删" in line]
    assert len(lines) == 1
    memory_id = lines[0].split()[0]
    assert len(memory_id) == 32
    assert lines[0] == f"{memory_id} [写手] strength=100 按 id 删"
    deleted = runner.invoke(app, ["memory", "delete", workspace_id, memory_id])
    assert deleted.exit_code == 0, deleted.output
    after = runner.invoke(app, ["memory", "notes", workspace_id])
    assert after.exit_code == 0, after.output
    assert "按 id 删" not in after.output
    assert "no memory notes yet" in after.output


def test_memory_note_unknown_workspace(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["memory", "note", "nope", "写手", "--content", "x"])
    assert result.exit_code == 1
    assert "workspace not found" in result.output


@pytest.mark.parametrize("content", ["", "   "])
def test_memory_note_rejects_blank_content(
    tmp_path: Path, monkeypatch, content: str
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(app, ["memory", "note", workspace_id, "写手", "--content", content])
    assert result.exit_code == 2
    assert "must not be empty" in result.output


@pytest.mark.parametrize(
    "content",
    [
        "first line\nsecond line",
        "first line\rsecond line",
        "first line\r\nsecond line",
        "first line\u2028second line",
        "first line\u2029second line",
        "first line\x0bsecond line",
        "first line\x0csecond line",
    ],
)
def test_memory_note_rejects_newline_content(
    tmp_path: Path, monkeypatch, content: str
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(
        app,
        ["memory", "note", workspace_id, "写手", "--content", content, "--as", "写手"],
    )
    assert result.exit_code == 2, result.output
    assert "must not contain newlines" in result.output
    settings = load_settings()
    db = DB(settings)
    with db.workspace_session(workspace_id) as session:
        notes = session.query(AgentMemory).filter_by(workspace_id=workspace_id).all()
        assert notes == []


def test_memory_delete_removes_note(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    assert (
        runner.invoke(
            app,
            ["memory", "note", workspace_id, "写手", "--content", "要删的笔记", "--as", "写手"],
        ).exit_code
        == 0
    )
    settings = load_settings()
    db = DB(settings)
    with db.workspace_session(workspace_id) as session:
        note = session.query(AgentMemory).filter_by(workspace_id=workspace_id).first()
        assert note is not None
        memory_id = note.id

    deleted = runner.invoke(app, ["memory", "delete", workspace_id, memory_id])
    assert deleted.exit_code == 0, deleted.output
    listed = runner.invoke(app, ["memory", "notes", workspace_id])
    assert listed.exit_code == 0, listed.output
    assert "要删的笔记" not in listed.output
    assert "no memory notes yet" in listed.output


def test_memory_delete_missing_note(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(app, ["memory", "delete", workspace_id, "nope"])
    assert result.exit_code == 1
    assert "memory note not found" in result.output


def test_memory_notes_isolated_between_workspaces(tmp_path: Path, monkeypatch) -> None:
    workspace_a = _create_workspace(tmp_path, monkeypatch, "甲书")
    workspace_b = _create_workspace(tmp_path, monkeypatch, "乙书")
    created = runner.invoke(
        app,
        ["memory", "note", workspace_a, "写手", "--content", "甲书秘密", "--as", "写手"],
    )
    assert created.exit_code == 0, created.output
    listed_b = runner.invoke(app, ["memory", "notes", workspace_b])
    assert listed_b.exit_code == 0, listed_b.output
    assert "甲书秘密" not in listed_b.output


def test_add_memory_note_rejects_foreign_agent(tmp_path: Path, monkeypatch) -> None:
    workspace_a = _create_workspace(tmp_path, monkeypatch, "甲书")
    workspace_b = _create_workspace(tmp_path, monkeypatch, "乙书")
    settings = load_settings()
    db = DB(settings)
    with db.workspace_session(workspace_a) as session:
        writer_a = session.query(Agent).filter_by(workspace_id=workspace_a, role="writer").first()
        assert writer_a is not None

    with pytest.raises(NovelError) as exc_info:
        add_memory_note(db, workspace_b, writer_a.id, actor="写手", content="串台笔记")
    assert exc_info.value.code is ErrorCode.NOT_FOUND


@pytest.mark.parametrize(
    "content",
    [
        "line one\nline two",
        "line one\rline two",
        "line one\r\nline two",
        "line one\u2028line two",
        "line one\u2029line two",
        "line one\x0bline two",
        "line one\x0cline two",
    ],
)
def test_add_memory_note_rejects_newline_content(
    tmp_path: Path, monkeypatch, content: str
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    db = DB(settings)
    with db.workspace_session(workspace_id) as session:
        writer = session.query(Agent).filter_by(workspace_id=workspace_id, role="writer").first()
        assert writer is not None

    with pytest.raises(NovelError) as exc_info:
        add_memory_note(db, workspace_id, writer.id, actor="写手", content=content)
    assert exc_info.value.code is ErrorCode.USAGE_ERROR
    assert "must not contain newlines" in exc_info.value.message


def test_agent_memory_model_columns() -> None:
    columns = set(AgentMemory.__table__.columns.keys())
    assert columns == {
        "id",
        "workspace_id",
        "agent_id",
        "content",
        "created_at",
        "strength",
        "last_accessed_at",
        "archived_at",
    }


def test_memory_upgrades_pre_migration_workspace(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    path = workspace_db_path(settings, workspace_id)
    connection = sqlite3.connect(path)
    connection.execute("DROP TABLE IF EXISTS agent_memories")
    connection.execute("DROP TABLE IF EXISTS plot_threads")
    connection.execute("DROP TABLE IF EXISTS events")
    connection.execute('ALTER TABLE agents DROP COLUMN "mood"')
    connection.execute("DELETE FROM alembic_version")
    connection.execute("INSERT INTO alembic_version (version_num) VALUES ('f1f5f128b371')")
    connection.commit()
    connection.close()

    created = runner.invoke(
        app,
        ["memory", "note", workspace_id, "写手", "--content", "升级后仍能记", "--as", "写手"],
    )
    assert created.exit_code == 0, created.output
    listed = runner.invoke(app, ["memory", "notes", workspace_id, "写手"])
    assert listed.exit_code == 0, listed.output
    assert "升级后仍能记" in listed.output


def test_memory_migration_backfills_existing_rows(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    db = DB(settings)
    writer_id = _writer_id(db, workspace_id)
    path = workspace_db_path(settings, workspace_id)
    connection = sqlite3.connect(path)
    connection.execute("ALTER TABLE agent_memories DROP COLUMN strength")
    connection.execute("ALTER TABLE agent_memories DROP COLUMN last_accessed_at")
    connection.execute("ALTER TABLE agent_memories DROP COLUMN archived_at")
    connection.execute("DELETE FROM alembic_version")
    connection.execute(
        "INSERT INTO alembic_version (version_num) VALUES ('f80e112950a2')"
    )
    connection.execute(
        "INSERT INTO agent_memories (id, workspace_id, agent_id, content, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            "legacy-note-1",
            workspace_id,
            writer_id,
            "迁移前的旧笔记",
            "2026-01-01 00:00:00",
        ),
    )
    connection.commit()
    connection.close()

    upgraded = DB(settings)
    with upgraded.workspace_session(workspace_id) as session:
        note = session.query(AgentMemory).filter_by(id="legacy-note-1").first()
        assert note is not None
        assert note.strength == 100
        assert note.last_accessed_at is not None
        assert note.archived_at is None


def test_effective_strength_same_day_is_unchanged(
    tmp_path: Path, monkeypatch
) -> None:
    _memory_config(tmp_path, monkeypatch, decay=5)
    now = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
    note = AgentMemory(
        id="n1",
        workspace_id="w",
        agent_id="a",
        content="x",
        strength=80,
        last_accessed_at=now,
    )
    assert effective_strength(note, now) == 80


def test_effective_strength_decays_whole_days(
    tmp_path: Path, monkeypatch
) -> None:
    _memory_config(tmp_path, monkeypatch, decay=5)
    now = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
    note = AgentMemory(
        id="n1",
        workspace_id="w",
        agent_id="a",
        content="x",
        strength=100,
        last_accessed_at=now - timedelta(days=3),
    )
    assert effective_strength(note, now) == 85


def test_effective_strength_floor_at_zero(tmp_path: Path, monkeypatch) -> None:
    _memory_config(tmp_path, monkeypatch, decay=5)
    now = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
    note = AgentMemory(
        id="n1",
        workspace_id="w",
        agent_id="a",
        content="x",
        strength=10,
        last_accessed_at=now - timedelta(days=100),
    )
    assert effective_strength(note, now) == 0


def test_effective_strength_caps_at_100(tmp_path: Path, monkeypatch) -> None:
    _memory_config(tmp_path, monkeypatch, decay=5)
    now = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
    note = AgentMemory(
        id="n1",
        workspace_id="w",
        agent_id="a",
        content="x",
        strength=120,
        last_accessed_at=now - timedelta(days=1),
    )
    assert effective_strength(note, now) == 100


def test_effective_strength_negative_days_count_as_zero(
    tmp_path: Path, monkeypatch
) -> None:
    _memory_config(tmp_path, monkeypatch, decay=5)
    now = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
    note = AgentMemory(
        id="n1",
        workspace_id="w",
        agent_id="a",
        content="x",
        strength=50,
        last_accessed_at=now + timedelta(days=2),
    )
    assert effective_strength(note, now) == 50


def test_effective_strength_treats_naive_utc_timestamp_as_utc(
    tmp_path: Path, monkeypatch
) -> None:
    _memory_config(tmp_path, monkeypatch, decay=5)
    note = AgentMemory(
        id="n1",
        workspace_id="w",
        agent_id="a",
        content="x",
        strength=100,
        last_accessed_at=datetime(2026, 8, 15, 12, 0),
    )
    now = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
    assert effective_strength(note, now) == 85


def test_effective_strength_aware_non_utc_now_uses_real_utc_days(
    tmp_path: Path, monkeypatch
) -> None:
    _memory_config(tmp_path, monkeypatch, decay=5)
    note = AgentMemory(
        id="n1",
        workspace_id="w",
        agent_id="a",
        content="x",
        strength=100,
        last_accessed_at=datetime(2026, 8, 18, 0, 0, tzinfo=UTC),
    )
    now = datetime(2026, 8, 19, 0, 30, tzinfo=timezone(timedelta(hours=8)))
    assert effective_strength(note, now) == 100


def test_apply_memory_decay_writes_changes_and_is_idempotent(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    _memory_config(tmp_path, monkeypatch, decay=5)
    db = DB(load_settings())
    writer_id = _writer_id(db, workspace_id)
    now = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
    note = _add_raw_note(
        db,
        workspace_id,
        writer_id,
        "旧账",
        last_accessed_at=now - timedelta(days=3),
    )
    changed = apply_memory_decay(db, workspace_id, now=now)
    assert [item.id for item in changed] == [note.id]
    assert changed[0].strength == 85
    assert apply_memory_decay(db, workspace_id, now=now) == []
    with db.workspace_session(workspace_id) as session:
        refreshed = session.query(AgentMemory).filter_by(id=note.id).first()
        assert refreshed is not None
        assert refreshed.strength == 85


def test_apply_memory_decay_floor_at_zero(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    _memory_config(tmp_path, monkeypatch, decay=5)
    db = DB(load_settings())
    writer_id = _writer_id(db, workspace_id)
    now = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
    note = _add_raw_note(
        db,
        workspace_id,
        writer_id,
        "快忘了",
        strength=30,
        last_accessed_at=now - timedelta(days=10),
    )
    changed = apply_memory_decay(db, workspace_id, now=now)
    assert changed[0].id == note.id
    assert changed[0].strength == 0


def test_apply_memory_decay_persists_normalized_utc_now(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    _memory_config(tmp_path, monkeypatch, decay=5)
    db = DB(load_settings())
    writer_id = _writer_id(db, workspace_id)
    note = _add_raw_note(
        db,
        workspace_id,
        writer_id,
        "日界附近的笔记",
        last_accessed_at=datetime(2026, 8, 17, 0, 0, tzinfo=UTC),
    )
    now = datetime(2026, 8, 19, 0, 30, tzinfo=timezone(timedelta(hours=8)))
    changed = apply_memory_decay(db, workspace_id, now=now)
    assert [item.id for item in changed] == [note.id]
    assert changed[0].strength == 95
    with db.workspace_session(workspace_id) as session:
        refreshed = session.query(AgentMemory).filter_by(id=note.id).first()
        assert refreshed is not None
        assert _as_utc(refreshed.last_accessed_at) == datetime(
            2026, 8, 18, 16, 30, tzinfo=UTC
        )


def test_apply_memory_decay_loads_settings_once(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    _memory_config(tmp_path, monkeypatch, decay=5)
    db = DB(load_settings())
    writer_id = _writer_id(db, workspace_id)
    now = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
    for index in range(3):
        _add_raw_note(
            db,
            workspace_id,
            writer_id,
            f"批量笔记-{index}",
            last_accessed_at=now - timedelta(days=3),
        )
    import novel_editorial.core.memory as memory_module

    calls = {"count": 0}
    real_load = memory_module.load_settings

    def counting_load_settings():
        calls["count"] += 1
        return real_load()

    monkeypatch.setattr(memory_module, "load_settings", counting_load_settings)
    apply_memory_decay(db, workspace_id, now=now)
    assert calls["count"] == 1


def test_list_archive_candidates_loads_settings_once(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    _memory_config(tmp_path, monkeypatch, decay=5, threshold=20)
    db = DB(load_settings())
    writer_id = _writer_id(db, workspace_id)
    now = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
    for index in range(3):
        _add_raw_note(
            db,
            workspace_id,
            writer_id,
            f"候选笔记-{index}",
            last_accessed_at=now - timedelta(days=3),
        )
    import novel_editorial.core.memory as memory_module

    calls = {"count": 0}
    real_load = memory_module.load_settings

    def counting_load_settings():
        calls["count"] += 1
        return real_load()

    monkeypatch.setattr(memory_module, "load_settings", counting_load_settings)
    list_archive_candidates(db, workspace_id, now=now)
    assert calls["count"] == 1


def test_archive_memory_notes_candidates_loads_settings_once(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    _memory_config(tmp_path, monkeypatch, decay=5, threshold=20)
    db = DB(load_settings())
    writer_id = _writer_id(db, workspace_id)
    now = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
    for index in range(3):
        _add_raw_note(
            db,
            workspace_id,
            writer_id,
            f"归档笔记-{index}",
            last_accessed_at=now - timedelta(days=3),
        )
    import novel_editorial.core.memory as memory_module

    calls = {"count": 0}
    real_load = memory_module.load_settings

    def counting_load_settings():
        calls["count"] += 1
        return real_load()

    monkeypatch.setattr(memory_module, "load_settings", counting_load_settings)
    archive_memory_notes(db, workspace_id, candidates=True, now=now)
    assert calls["count"] == 1


def test_apply_memory_decay_skips_archived_notes(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    _memory_config(tmp_path, monkeypatch, decay=5)
    db = DB(load_settings())
    writer_id = _writer_id(db, workspace_id)
    now = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
    note = _add_raw_note(
        db,
        workspace_id,
        writer_id,
        "已归档的旧账",
        strength=30,
        last_accessed_at=now - timedelta(days=10),
    )
    archive_memory_notes(db, workspace_id, [note.id], now=now)
    assert apply_memory_decay(db, workspace_id, now=now) == []
    with db.workspace_session(workspace_id) as session:
        refreshed = session.query(AgentMemory).filter_by(id=note.id).first()
        assert refreshed is not None
        assert refreshed.strength == 30


def test_list_archive_candidates_uses_effective_strength(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    _memory_config(tmp_path, monkeypatch, decay=5, threshold=20)
    db = DB(load_settings())
    writer_id = _writer_id(db, workspace_id)
    now = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
    strong = _add_raw_note(
        db, workspace_id, writer_id, "强记忆", last_accessed_at=now
    )
    weak = _add_raw_note(
        db,
        workspace_id,
        writer_id,
        "弱记忆",
        last_accessed_at=now - timedelta(days=20),
    )
    borderline = _add_raw_note(
        db,
        workspace_id,
        writer_id,
        "临界记忆",
        strength=35,
        last_accessed_at=now - timedelta(days=3),
    )
    archived = _add_raw_note(
        db,
        workspace_id,
        writer_id,
        "已归档弱记忆",
        last_accessed_at=now - timedelta(days=20),
    )
    archive_memory_notes(db, workspace_id, [archived.id], now=now)
    candidates = list_archive_candidates(db, workspace_id, now=now)
    candidate_ids = {note.id for note in candidates}
    assert candidate_ids == {weak.id, borderline.id}
    assert strong.id not in candidate_ids
    assert archived.id not in candidate_ids


def test_rehearse_memory_note_boosts_and_refreshes(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    _memory_config(tmp_path, monkeypatch, boost=25)
    db = DB(load_settings())
    writer_id = _writer_id(db, workspace_id)
    now = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
    note = _add_raw_note(
        db,
        workspace_id,
        writer_id,
        "要保鲜的",
        strength=60,
        last_accessed_at=now - timedelta(days=9),
    )
    rehearsed = rehearse_memory_note(db, workspace_id, note.id, now=now)
    assert rehearsed.id == note.id
    assert rehearsed.strength == 85
    assert _as_utc(rehearsed.last_accessed_at) == now
    with db.workspace_session(workspace_id) as session:
        refreshed = session.query(AgentMemory).filter_by(id=note.id).first()
        assert refreshed is not None
        assert refreshed.strength == 85
        assert _as_utc(refreshed.last_accessed_at) == now


def test_rehearse_memory_note_caps_at_100(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    _memory_config(tmp_path, monkeypatch, boost=25)
    db = DB(load_settings())
    writer_id = _writer_id(db, workspace_id)
    now = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
    note = _add_raw_note(db, workspace_id, writer_id, "接近上限", strength=90)
    rehearsed = rehearse_memory_note(db, workspace_id, note.id, now=now)
    assert rehearsed.strength == 100


def test_rehearse_archived_note_is_usage_error(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    _memory_config(tmp_path, monkeypatch, boost=25)
    db = DB(load_settings())
    writer_id = _writer_id(db, workspace_id)
    now = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
    note = _add_raw_note(db, workspace_id, writer_id, "已归档的", strength=60)
    archive_memory_notes(db, workspace_id, [note.id], now=now)
    with pytest.raises(NovelError) as exc_info:
        rehearse_memory_note(db, workspace_id, note.id, now=now)
    assert exc_info.value.code is ErrorCode.USAGE_ERROR


def test_rehearse_unknown_note_is_not_found(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    _memory_config(tmp_path, monkeypatch, boost=25)
    db = DB(load_settings())
    now = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
    with pytest.raises(NovelError) as exc_info:
        rehearse_memory_note(db, workspace_id, "nope", now=now)
    assert exc_info.value.code is ErrorCode.NOT_FOUND


def test_archive_memory_notes_explicit_ids_ignore_strength(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    writer_id = _writer_id(db, workspace_id)
    now = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
    strong = _add_raw_note(db, workspace_id, writer_id, "强记忆")
    weak = _add_raw_note(
        db,
        workspace_id,
        writer_id,
        "弱记忆",
        strength=1,
        last_accessed_at=now - timedelta(days=50),
    )
    archived = archive_memory_notes(db, workspace_id, [strong.id, weak.id], now=now)
    assert {note.id for note in archived} == {strong.id, weak.id}
    assert all(note.archived_at == now for note in archived)
    assert list_memory_notes(db, workspace_id) == []


def test_archive_memory_notes_missing_id_not_found_rolls_back(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    writer_id = _writer_id(db, workspace_id)
    now = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
    note = _add_raw_note(db, workspace_id, writer_id, "不应被归档")
    with pytest.raises(NovelError) as exc_info:
        archive_memory_notes(db, workspace_id, [note.id, "nope"], now=now)
    assert exc_info.value.code is ErrorCode.NOT_FOUND
    with db.workspace_session(workspace_id) as session:
        refreshed = session.query(AgentMemory).filter_by(id=note.id).first()
        assert refreshed is not None
        assert refreshed.archived_at is None


def test_archive_memory_notes_candidates(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    _memory_config(tmp_path, monkeypatch, decay=5, threshold=20)
    db = DB(load_settings())
    writer_id = _writer_id(db, workspace_id)
    now = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
    strong = _add_raw_note(
        db, workspace_id, writer_id, "强记忆", last_accessed_at=now
    )
    weak = _add_raw_note(
        db,
        workspace_id,
        writer_id,
        "弱记忆",
        last_accessed_at=now - timedelta(days=20),
    )
    archived = archive_memory_notes(db, workspace_id, candidates=True, now=now)
    assert [note.id for note in archived] == [weak.id]
    with db.workspace_session(workspace_id) as session:
        refreshed = session.query(AgentMemory).filter_by(id=strong.id).first()
        assert refreshed is not None
        assert refreshed.archived_at is None


def test_archive_memory_notes_candidates_with_ids_is_usage_error(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    writer_id = _writer_id(db, workspace_id)
    now = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
    note = _add_raw_note(db, workspace_id, writer_id, "哪条都不该归档")
    with pytest.raises(NovelError) as exc_info:
        archive_memory_notes(
            db, workspace_id, [note.id], candidates=True, now=now
        )
    assert exc_info.value.code is ErrorCode.USAGE_ERROR


def test_archive_memory_notes_empty_ids_returns_empty(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    now = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
    assert archive_memory_notes(db, workspace_id, [], now=now) == []


def test_restore_memory_notes_keeps_strength_and_access_time(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    writer_id = _writer_id(db, workspace_id)
    now = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
    note = _add_raw_note(
        db,
        workspace_id,
        writer_id,
        "可恢复的",
        strength=55,
        last_accessed_at=now - timedelta(days=7),
    )
    archive_memory_notes(db, workspace_id, [note.id], now=now)
    restored = restore_memory_notes(db, workspace_id, [note.id], now=now)
    assert [item.id for item in restored] == [note.id]
    assert restored[0].archived_at is None
    assert restored[0].strength == 55
    assert _as_utc(restored[0].last_accessed_at) == now - timedelta(days=7)
    assert {item.id for item in list_memory_notes(db, workspace_id)} == {note.id}


def test_restore_memory_notes_missing_id_not_found(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    now = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
    with pytest.raises(NovelError) as exc_info:
        restore_memory_notes(db, workspace_id, ["nope"], now=now)
    assert exc_info.value.code is ErrorCode.NOT_FOUND


def test_list_memory_notes_excludes_archived_and_sorts(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    writer_id = _writer_id(db, workspace_id)
    base = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
    first = _add_raw_note(
        db, workspace_id, writer_id, "早强", strength=100, created_at=base
    )
    second = _add_raw_note(
        db,
        workspace_id,
        writer_id,
        "晚强",
        strength=100,
        created_at=base + timedelta(minutes=1),
    )
    weak = _add_raw_note(
        db,
        workspace_id,
        writer_id,
        "弱",
        strength=50,
        created_at=base + timedelta(minutes=2),
    )
    archived = _add_raw_note(
        db,
        workspace_id,
        writer_id,
        "归档但最强",
        strength=200,
        created_at=base + timedelta(minutes=3),
    )
    archive_memory_notes(db, workspace_id, [archived.id], now=base)
    active = list_memory_notes(db, workspace_id)
    assert [note.id for note in active] == [first.id, second.id, weak.id]
    with_archived = list_memory_notes(db, workspace_id, include_archived=True)
    assert [note.id for note in with_archived] == [
        archived.id,
        first.id,
        second.id,
        weak.id,
    ]


def test_list_memory_notes_tiebreak_by_id(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    writer_id = _writer_id(db, workspace_id)
    base = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)
    first = _add_raw_note(
        db, workspace_id, writer_id, "甲", strength=90, created_at=base
    )
    second = _add_raw_note(
        db, workspace_id, writer_id, "乙", strength=90, created_at=base
    )
    listed = list_memory_notes(db, workspace_id)
    assert [note.id for note in listed] == sorted([first.id, second.id])


def test_memory_notes_include_archived_flag(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    writer_id = _writer_id(db, workspace_id)
    note = _add_raw_note(
        db, workspace_id, writer_id, "已归档的旧账", strength=50
    )
    archive_memory_notes(db, workspace_id, [note.id])

    hidden = runner.invoke(app, ["memory", "notes", workspace_id])
    assert hidden.exit_code == 0, hidden.output
    assert "已归档的旧账" not in hidden.output

    shown = runner.invoke(
        app, ["memory", "notes", workspace_id, "--include-archived"]
    )
    assert shown.exit_code == 0, shown.output
    assert "已归档的旧账" in shown.output
    assert "【归档】" in shown.output
    assert "strength=50" in shown.output


def test_memory_decay_cli_reports_changes_then_no_decay(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    _memory_config(tmp_path, monkeypatch, decay=5)
    db = DB(load_settings())
    writer_id = _writer_id(db, workspace_id)
    note = _add_raw_note(
        db,
        workspace_id,
        writer_id,
        "会衰减的旧账",
        last_accessed_at=datetime.now(UTC) - timedelta(days=3),
    )

    first = runner.invoke(app, ["memory", "decay", workspace_id])
    assert first.exit_code == 0, first.output
    assert f"{note.id}: 100 -> 85" in first.output

    again = runner.invoke(app, ["memory", "decay", workspace_id])
    assert again.exit_code == 0, again.output
    assert "no decay this time" in again.output


def test_memory_remember_cli_prints_new_strength(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    _memory_config(tmp_path, monkeypatch, boost=25)
    db = DB(load_settings())
    writer_id = _writer_id(db, workspace_id)
    note = _add_raw_note(db, workspace_id, writer_id, "要保鲜的", strength=60)

    result = runner.invoke(app, ["memory", "remember", workspace_id, note.id])
    assert result.exit_code == 0, result.output
    assert f"{note.id} strength=85" in result.output


def test_memory_archive_cli_requires_target_or_candidates(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(app, ["memory", "archive", workspace_id])
    assert result.exit_code == 2
    assert "provide at least one memory note id or --candidates" in result.output


def test_memory_archive_cli_candidates_no_candidates(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    _memory_config(tmp_path, monkeypatch, decay=5, threshold=20)
    db = DB(load_settings())
    writer_id = _writer_id(db, workspace_id)
    _add_raw_note(
        db, workspace_id, writer_id, "强记忆", last_accessed_at=datetime.now(UTC)
    )

    result = runner.invoke(app, ["memory", "archive", workspace_id, "--candidates"])
    assert result.exit_code == 0, result.output
    assert "no archive candidates" in result.output


def test_memory_archive_cli_explicit_ids(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    writer_id = _writer_id(db, workspace_id)
    strong = _add_raw_note(db, workspace_id, writer_id, "强记忆")
    weak = _add_raw_note(db, workspace_id, writer_id, "弱记忆")

    result = runner.invoke(
        app, ["memory", "archive", workspace_id, strong.id, weak.id]
    )
    assert result.exit_code == 0, result.output
    assert "archived 2 note(s)" in result.output
    assert list_memory_notes(db, workspace_id) == []


def test_memory_restore_cli(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    writer_id = _writer_id(db, workspace_id)
    note = _add_raw_note(db, workspace_id, writer_id, "可恢复的旧账")
    archive_memory_notes(db, workspace_id, [note.id])
    assert list_memory_notes(db, workspace_id) == []

    restored = runner.invoke(app, ["memory", "restore", workspace_id, note.id])
    assert restored.exit_code == 0, restored.output
    assert "restored 1 note(s)" in restored.output
    assert {item.id for item in list_memory_notes(db, workspace_id)} == {note.id}


def test_memory_cli_end_to_end_decay_archive_visibility_restore(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    _memory_config(tmp_path, monkeypatch, decay=5, boost=25, threshold=20)
    db = DB(load_settings())
    writer_id = _writer_id(db, workspace_id)
    fixed_now = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    _add_raw_note(
        db,
        workspace_id,
        writer_id,
        "强记忆-旧车站常驻",
        last_accessed_at=datetime.now(UTC),
    )
    weak = _add_raw_note(
        db,
        workspace_id,
        writer_id,
        "弱记忆-旧车站细节",
        last_accessed_at=fixed_now - timedelta(days=20),
    )
    changed = apply_memory_decay(db, workspace_id, now=fixed_now)
    assert [item.id for item in changed] == [weak.id]

    archived = runner.invoke(app, ["memory", "archive", workspace_id, "--candidates"])
    assert archived.exit_code == 0, archived.output
    assert "archived 1 note(s)" in archived.output

    searched = runner.invoke(app, ["memory", "search", workspace_id, "旧车站"])
    assert searched.exit_code == 0, searched.output
    assert "强记忆-旧车站常驻" in searched.output
    assert "弱记忆-旧车站细节" not in searched.output

    notes = runner.invoke(app, ["memory", "notes", workspace_id])
    assert notes.exit_code == 0, notes.output
    assert "强记忆-旧车站常驻" in notes.output
    assert "弱记忆-旧车站细节" not in notes.output

    packed = runner.invoke(app, ["memory", "pack", workspace_id])
    assert packed.exit_code == 0, packed.output
    assert "强记忆-旧车站常驻" in packed.output
    assert "弱记忆-旧车站细节" not in packed.output

    archived_visible = runner.invoke(
        app, ["memory", "notes", workspace_id, "--include-archived"]
    )
    assert archived_visible.exit_code == 0, archived_visible.output
    assert "弱记忆-旧车站细节" in archived_visible.output
    assert "【归档】" in archived_visible.output

    restored = runner.invoke(app, ["memory", "restore", workspace_id, weak.id])
    assert restored.exit_code == 0, restored.output
    assert "restored 1 note(s)" in restored.output

    notes_after = runner.invoke(app, ["memory", "notes", workspace_id])
    assert notes_after.exit_code == 0, notes_after.output
    assert "弱记忆-旧车站细节" in notes_after.output
    assert "【归档】" not in notes_after.output
    assert "强记忆-旧车站常驻" in notes_after.output


def test_add_memory_note_syncs_embedding(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    db = DB(settings)
    writer_id = _writer_id(db, workspace_id)

    note = add_memory_note(
        db, workspace_id, writer_id, actor="写手", content="雨夜归乡"
    )

    with db.workspace_session(workspace_id) as session:
        row = (
            session.query(MemoryEmbedding)
            .filter_by(layer=LAYER_NOTE, source_id=note.id)
            .first()
        )
        assert row is not None
        assert json.loads(row.vector) == build_embedding_client(settings).embed(
            "雨夜归乡"
        )
        assert row.dim == settings.embedding_dim
        assert row.workspace_id == workspace_id


def test_delete_memory_note_removes_embedding(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    db = DB(settings)
    writer_id = _writer_id(db, workspace_id)
    note = add_memory_note(
        db, workspace_id, writer_id, actor="写手", content="删掉就没了"
    )

    delete_memory_note(db, workspace_id, note.id)

    with db.workspace_session(workspace_id) as session:
        row = (
            session.query(MemoryEmbedding)
            .filter_by(layer=LAYER_NOTE, source_id=note.id)
            .first()
        )
        assert row is None


def test_add_memory_note_embedding_failure_keeps_note_and_warns(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    db = DB(settings)
    writer_id = _writer_id(db, workspace_id)

    def boom(*args, **kwargs):
        raise RuntimeError("embedding backend down")

    monkeypatch.setattr("novel_editorial.core.retrieval.upsert_embedding", boom)
    note = add_memory_note(
        db, workspace_id, writer_id, actor="写手", content="照常记"
    )

    assert note is not None
    assert note.content == "照常记"
    captured = capsys.readouterr()
    assert "warning: embedding index skipped" in captured.err
    assert "embedding backend down" in captured.err
    with db.workspace_session(workspace_id) as session:
        assert session.query(AgentMemory).filter_by(id=note.id).count() == 1
        assert session.query(MemoryEmbedding).count() == 0


def test_delete_memory_note_embedding_failure_keeps_delete_and_warns(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    db = DB(settings)
    writer_id = _writer_id(db, workspace_id)
    note = add_memory_note(
        db, workspace_id, writer_id, actor="写手", content="删除不回头"
    )

    def boom(*args, **kwargs):
        raise RuntimeError("index delete failed")

    monkeypatch.setattr("novel_editorial.core.retrieval.delete_embedding", boom)
    delete_memory_note(db, workspace_id, note.id)

    captured = capsys.readouterr()
    assert "warning: embedding index delete skipped" in captured.err
    assert "index delete failed" in captured.err
    with db.workspace_session(workspace_id) as session:
        assert session.query(AgentMemory).filter_by(id=note.id).count() == 0
        assert session.query(MemoryEmbedding).count() == 1


def test_delete_memory_note_retry_cleans_orphan_embedding(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    db = DB(settings)
    writer_id = _writer_id(db, workspace_id)
    note = add_memory_note(
        db, workspace_id, writer_id, actor="写手", content="索引删除失败留下孤儿"
    )

    def boom(*args, **kwargs):
        raise RuntimeError("index delete failed")

    monkeypatch.setattr("novel_editorial.core.retrieval.delete_embedding", boom)
    delete_memory_note(db, workspace_id, note.id)
    with db.workspace_session(workspace_id) as session:
        assert session.query(AgentMemory).filter_by(id=note.id).count() == 0
        assert session.query(MemoryEmbedding).count() == 1

    monkeypatch.undo()
    with pytest.raises(NovelError) as exc_info:
        delete_memory_note(db, workspace_id, note.id)
    assert exc_info.value.code is ErrorCode.NOT_FOUND
    with db.workspace_session(workspace_id) as session:
        assert session.query(MemoryEmbedding).count() == 0


def test_memory_search_semantic_off_by_default(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    db = DB(settings)
    writer_id = _writer_id(db, workspace_id)
    add_memory_note(
        db,
        workspace_id,
        writer_id,
        actor="写手",
        content="雨夜回乡 客船靠岸",
    )

    result = runner.invoke(
        app, ["memory", "search", workspace_id, "雨夜归乡 客船"]
    )

    assert result.exit_code == 0, result.output
    assert "[语义" not in result.output
    assert result.output.strip() == "no matches"


def test_memory_search_semantic_appends_and_dedupes_literal(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    db = DB(settings)
    with db.workspace_session(workspace_id) as session:
        editor = (
            session.query(Agent)
            .filter_by(workspace_id=workspace_id, role="editor")
            .first()
        )
        assert editor is not None
        editor_id = editor.id
    writer_id = _writer_id(db, workspace_id)
    add_memory_note(
        db,
        workspace_id,
        editor_id,
        actor="责编",
        content="雨夜归乡 客船",
    )
    add_memory_note(
        db,
        workspace_id,
        writer_id,
        actor="写手",
        content="雨夜回乡 客船靠岸",
    )

    result = runner.invoke(
        app,
        [
            "memory",
            "search",
            workspace_id,
            "雨夜归乡 客船",
            "--semantic",
        ],
    )

    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    keyword_lines = [line for line in lines if "[笔记] 雨夜归乡 客船" in line]
    semantic_lines = [line for line in lines if "[语义" in line]
    assert len(keyword_lines) == 1
    assert len(semantic_lines) == 1
    assert "雨夜回乡 客船靠岸" in semantic_lines[0]
    assert "（来源: 写手）" in semantic_lines[0]
    assert lines.index(keyword_lines[0]) < lines.index(semantic_lines[0])


def test_memory_search_semantic_keeps_related_hit_when_literal_fills_top_k(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    db = DB(settings)
    writer_id = _writer_id(db, workspace_id)
    literals = [
        "雨夜归乡 客船靠岸",
        "雨夜归乡 客船启航",
        "雨夜归乡 客船鸣笛",
        "雨夜归乡 客船灯火",
        "雨夜归乡 客船汽笛",
    ]
    for content in literals:
        add_memory_note(
            db,
            workspace_id,
            writer_id,
            actor="写手",
            content=content,
        )
    related = "雨夜回乡 客船靠岸"
    add_memory_note(
        db,
        workspace_id,
        writer_id,
        actor="写手",
        content=related,
    )

    result = runner.invoke(
        app,
        [
            "memory",
            "search",
            workspace_id,
            "雨夜归乡 客船",
            "--semantic",
        ],
    )

    assert result.exit_code == 0, result.output
    semantic_lines = [line for line in result.output.splitlines() if "[语义" in line]
    assert len(semantic_lines) == 1
    assert related in semantic_lines[0]
    assert all(literal not in semantic_lines[0] for literal in literals)


def test_memory_search_semantic_dedupes_setting_by_name(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    db = DB(settings)
    add_setting(
        db,
        workspace_id,
        kind="world",
        name="雨夜归乡 客船",
        content="客船靠岸",
        source="作者",
    )

    result = runner.invoke(
        app,
        [
            "memory",
            "search",
            workspace_id,
            "雨夜归乡 客船",
            "--semantic",
        ],
    )

    assert result.exit_code == 0, result.output
    setting_lines = [
        line for line in result.output.splitlines() if line.startswith("[设定]")
    ]
    assert len(setting_lines) == 1
    assert "[语义" not in result.output


def test_memory_search_semantic_no_hits_still_no_matches(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)

    result = runner.invoke(
        app,
        ["memory", "search", workspace_id, "任意词", "--semantic"],
    )

    assert result.exit_code == 0, result.output
    assert result.output.strip() == "no matches"


def test_memory_reindex_cli_reports_count(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    db = DB(settings)
    writer_id = _writer_id(db, workspace_id)
    add_memory_note(
        db,
        workspace_id,
        writer_id,
        actor="写手",
        content="雨夜回乡",
    )
    add_setting(
        db,
        workspace_id,
        kind="world",
        name="客船",
        content="客船靠岸",
        source="作者",
    )

    result = runner.invoke(app, ["memory", "reindex", workspace_id])

    assert result.exit_code == 0, result.output
    assert result.output.strip() == "reindexed 2 entries"


def test_memory_reindex_unknown_workspace(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))

    result = runner.invoke(app, ["memory", "reindex", "nope"])

    assert result.exit_code == 1
    assert "workspace not found" in result.output
