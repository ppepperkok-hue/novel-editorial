import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.config import load_settings
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.core.memory import add_memory_note
from novel_editorial.store.db import DB, workspace_db_path
from novel_editorial.store.models import Agent, AgentMemory

runner = CliRunner()


def _create_workspace(tmp_path: Path, monkeypatch, title: str = "记忆之书") -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["works", "create", title])
    assert result.exit_code == 0, result.output
    return result.output.split()[2].rstrip(":")


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
    assert lines[0] == f"{memory_id} [写手] 按 id 删"
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
    assert columns == {"id", "workspace_id", "agent_id", "content", "created_at"}


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
