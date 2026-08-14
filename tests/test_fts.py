"""FTS5 trigram full-text search: migration, sync triggers, and dual-path parity."""

import importlib.util
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest import mock

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.chat import AUTHOR_ACTOR, record_message
from novel_editorial.core.config import load_settings
from novel_editorial.core.decision import decide
from novel_editorial.core.draft import generate_draft
from novel_editorial.core.memory import add_memory_note
from novel_editorial.core.plot import KIND_FORESHADOW, plant_thread
from novel_editorial.core.review import add_review
from novel_editorial.core.views import (
    FTS_TABLE_BY_LAYER,
    _fts5_available,
    _fts_tables_present,
    search_all_layers,
    search_memory,
)
from novel_editorial.llm.client import MockLLMClient
from novel_editorial.store.db import DB, workspace_db_path
from novel_editorial.store.models import Agent, AgentMemory, Message

runner = CliRunner()

FTS_TABLES = {
    "message_fts",
    "review_fts",
    "draft_version_fts",
    "agent_memory_fts",
    "plot_thread_fts",
}

PRE_FTS_HEAD = "1ecd3fdf59e1"

MIGRATION_MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "versions"
    / "9c3a71b5d2e4_add_fts5_trigram_indexes.py"
)


def _no_fts5_error(statement: str) -> OperationalError:
    """Build the wrapper error SQLAlchemy raises when the FTS5 module is missing."""
    return OperationalError(
        statement, {}, sqlite3.OperationalError("no such module: fts5")
    )


def _raise_no_fts5(statement) -> None:
    """Raise the wrapped "no such module: fts5" error for a fake connection.

    The pre-probe cleanup DROP TABLE IF EXISTS must succeed: on a build
    without FTS5 there is nothing to drop, and only the CREATE fails.
    """
    sql = str(statement)
    if "DROP TABLE IF EXISTS temp._novel_fts5_probe" in sql:
        return None
    raise _no_fts5_error(sql)


def _fts5_runtime_available() -> bool:
    """Run the real runtime probe so FTS5-dependent tests skip when unusable.

    The probe creates a temp FTS5 trigram table and drops it, mirroring what
    the search path does on every call, so a build whose FTS5 only exists in
    compile options still skips instead of crashing mid-test.
    """
    with Session(create_engine("sqlite://")) as session:
        return _fts5_available(session)


requires_fts5 = pytest.mark.skipif(
    not _fts5_runtime_available(),
    reason="SQLite in this process cannot create an FTS5 trigram table",
)


MEMORY_KEYWORDS = [
    "暗线七星",
    "hook",
    "HOOK",
    "100%达",
    'he said "h',
    "C:\\te",
    "a_b",
    "不存在的词",
]

LAYERS_KEYWORDS = [
    *MEMORY_KEYWORDS,
    "foreshadow",
    "第一卷",
    "note",
]

ADVERSARIAL_KEYWORDS = [
    '"""',
    '"delete"',
    'NEAR("a","b")',
    'a"b"c',
    '钩"子埋',
    "……省略",
    "—破折—",
    "delete",
]

NON_ASCII_KEYWORDS = ("café", "CAFÉ", "straße", "STRASSE", "résumé", "RESUMÉ")


def _create_workspace(tmp_path: Path, monkeypatch, title: str = "检索之书") -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(
        app,
        [
            "works",
            "create",
            title,
            "--genre",
            "悬疑",
            "--description",
            "雨夜的都市故事",
        ],
    )
    assert result.exit_code == 0, result.output
    # Parse stdout only: on builds without FTS5 the migration prints a warning
    # to stderr, and CliRunner mixes both streams into `output`.
    return result.stdout.split()[2].rstrip(":")


def _writer_id(db: DB, workspace_id: str) -> str:
    with db.workspace_session(workspace_id) as session:
        writer = session.query(Agent).filter_by(workspace_id=workspace_id, role="writer").first()
    assert writer is not None
    return writer.id


def _seed_layers(db: DB, workspace_id: str) -> str:
    """Seed every searchable layer; returns the draft id."""
    record_message(
        db,
        workspace_id,
        role="author",
        actor=AUTHOR_ACTOR,
        content="雨夜开场，暗线七星埋在最暗处。",
    )
    record_message(
        db,
        workspace_id,
        role="author",
        actor=AUTHOR_ACTOR,
        content="The Hook is here, 100%达标。",
    )
    record_message(
        db,
        workspace_id,
        role="author",
        actor=AUTHOR_ACTOR,
        content='He said "hello" quietly',
    )
    record_message(
        db,
        workspace_id,
        role="author",
        actor=AUTHOR_ACTOR,
        content=r"路径 C:\temp 存档",
    )
    record_message(
        db,
        workspace_id,
        role="author",
        actor=AUTHOR_ACTOR,
        content="代号a_b 与 aXb",
    )
    record_message(
        db,
        workspace_id,
        role="author",
        actor=AUTHOR_ACTOR,
        content="前置 钩子 后置",
    )
    draft = generate_draft(
        db,
        workspace_id,
        title="第一卷",
        client=MockLLMClient(reply="版本正文：暗线七星顺着旧车站延伸。"),
    )
    add_review(
        db,
        workspace_id,
        draft.id,
        role="agent",
        actor="责编",
        content="暗线七星的回收节奏再快一点。",
    )
    add_memory_note(
        db,
        workspace_id,
        _writer_id(db, workspace_id),
        actor="写手",
        content="暗线七星在第 3 章回头。",
    )
    plant_thread(
        db,
        workspace_id,
        kind=KIND_FORESHADOW,
        content="暗线七星是贯穿线索。",
    )
    decide(db, workspace_id, draft.id, action="note", content="决策：暗线七星方案待定。")
    return draft.id


def _seed_non_ascii_layers(db: DB, workspace_id: str) -> None:
    """Seed uppercase/lowercase accented text across several searchable layers."""
    record_message(
        db,
        workspace_id,
        role="author",
        actor=AUTHOR_ACTOR,
        content="仓库里只有 CAFÉ 豆",
    )
    record_message(
        db,
        workspace_id,
        role="author",
        actor=AUTHOR_ACTOR,
        content="café 柜台在转角",
    )
    record_message(
        db,
        workspace_id,
        role="author",
        actor=AUTHOR_ACTOR,
        content="CAFÉ 与 café 混放",
    )
    record_message(
        db,
        workspace_id,
        role="author",
        actor=AUTHOR_ACTOR,
        content="Straße 与 STRASSE 并排写",
    )
    draft = generate_draft(
        db,
        workspace_id,
        title="拉丁字符卷",
        client=MockLLMClient(reply="正文：café 要开在 Straße 边。"),
    )
    add_review(
        db,
        workspace_id,
        draft.id,
        role="agent",
        actor="责编",
        content="CAFÉ 的招牌统一用 résumé 那种重音。",
    )
    add_memory_note(
        db,
        workspace_id,
        _writer_id(db, workspace_id),
        actor="写手",
        content="笔记：STRASSE 全部改成 Straße。",
    )


def _load_fts_migration_module():
    spec = importlib.util.spec_from_file_location(
        "fts5_migration_under_test", MIGRATION_MODULE_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fts_hits(path: Path, table: str, keyword: str) -> list[str]:
    phrase = '"' + keyword.replace('"', '""') + '"'
    connection = sqlite3.connect(path)
    try:
        rows = connection.execute(f"SELECT id FROM {table} WHERE {table} MATCH ?", (phrase,))
        return [row[0] for row in rows]
    finally:
        connection.close()


@requires_fts5
def test_fts_migration_creates_shadow_tables_and_triggers(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    path = workspace_db_path(settings, workspace_id)

    connection = sqlite3.connect(path)
    try:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        triggers = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='trigger'")
        }
    finally:
        connection.close()

    assert FTS_TABLES <= tables
    expected_triggers = {
        f"{table}{suffix}" for table in FTS_TABLES for suffix in ("_ai", "_ad", "_au")
    }
    assert expected_triggers <= triggers


@requires_fts5
def test_fts_triggers_keep_shadow_tables_in_sync(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    db = DB(settings)
    message = record_message(
        db,
        workspace_id,
        role="author",
        actor=AUTHOR_ACTOR,
        content="雨夜开场钩子埋下",
    )
    path = workspace_db_path(settings, workspace_id)

    assert _fts_hits(path, "message_fts", "钩子埋") == [message.id]

    with db.workspace_session(workspace_id) as session:
        row = session.get(Message, message.id)
        assert row is not None
        row.content = "改成了另一段"
        session.commit()

    assert _fts_hits(path, "message_fts", "钩子埋") == []
    assert _fts_hits(path, "message_fts", "改成了") == [message.id]

    with db.workspace_session(workspace_id) as session:
        row = session.get(Message, message.id)
        assert row is not None
        session.delete(row)
        session.commit()

    assert _fts_hits(path, "message_fts", "改成了") == []


@requires_fts5
def test_fts_migration_upgrades_legacy_database_with_backfill(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    db = DB(settings)
    message = record_message(
        db,
        workspace_id,
        role="author",
        actor=AUTHOR_ACTOR,
        content="旧库里的钩子埋在这",
    )
    path = workspace_db_path(settings, workspace_id)

    connection = sqlite3.connect(path)
    try:
        for table in FTS_TABLES:
            for suffix in ("_ai", "_ad", "_au"):
                connection.execute(f"DROP TRIGGER IF EXISTS {table}{suffix}")
            connection.execute(f"DROP TABLE IF EXISTS {table}")
        connection.execute("DELETE FROM alembic_version")
        connection.execute("INSERT INTO alembic_version (version_num) VALUES (?)", (PRE_FTS_HEAD,))
        connection.commit()
    finally:
        connection.close()

    reopened = DB(load_settings())
    found = search_memory(reopened, workspace_id, "钩子埋")
    assert "[对话]" in found
    assert "旧库里的钩子埋在这" in found

    connection = sqlite3.connect(path)
    try:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        rows = connection.execute(
            "SELECT id FROM message_fts WHERE message_fts MATCH ?", ('"钩子埋"',)
        )
        ids = [row[0] for row in rows]
    finally:
        connection.close()

    assert FTS_TABLES <= tables
    assert ids == [message.id]


@requires_fts5
def test_dual_path_outputs_match_for_search_memory(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    db = DB(settings)
    _seed_layers(db, workspace_id)

    for keyword in MEMORY_KEYWORDS:
        liked = search_memory(db, workspace_id, keyword, _force_fts=False)
        ftsed = search_memory(db, workspace_id, keyword, _force_fts=True)
        assert ftsed.encode("utf-8") == liked.encode("utf-8"), f"keyword={keyword!r}"

    spaced = search_memory(db, workspace_id, " 钩子 ", _force_fts=False)
    spaced_fts = search_memory(db, workspace_id, " 钩子 ", _force_fts=True)
    assert spaced_fts.encode("utf-8") == spaced.encode("utf-8")

    cross_layer = search_memory(db, workspace_id, "暗线七星", _force_fts=True)
    for tag in ("[对话]", "[意见]", "[版本]", "[笔记]"):
        assert tag in cross_layer


@requires_fts5
def test_dual_path_outputs_match_for_search_all_layers(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    db = DB(settings)
    _seed_layers(db, workspace_id)

    for keyword in LAYERS_KEYWORDS:
        liked = search_all_layers(db, workspace_id, keyword, _force_fts=False)
        ftsed = search_all_layers(db, workspace_id, keyword, _force_fts=True)
        assert ftsed.encode("utf-8") == liked.encode("utf-8"), f"keyword={keyword!r}"

    cross_layer = search_all_layers(db, workspace_id, "暗线七星", _force_fts=True)
    for tag in ("[对话]", "[意见]", "[版本]", "[笔记]", "[决策]", "[线索]"):
        assert tag in cross_layer


@requires_fts5
def test_long_keywords_use_fts_and_short_keywords_use_like(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    db = DB(settings)
    record_message(
        db,
        workspace_id,
        role="author",
        actor=AUTHOR_ACTOR,
        content="钩子埋在这里",
    )

    statements: list[str] = []

    def capture(conn, cursor, statement, parameters, context, executemany) -> None:
        statements.append(statement)

    event.listen(Engine, "after_cursor_execute", capture)
    try:
        search_all_layers(db, workspace_id, "钩子埋")
        long_statements = list(statements)
        statements.clear()
        search_all_layers(db, workspace_id, "钩子")
        short_statements = list(statements)
    finally:
        event.remove(Engine, "after_cursor_execute", capture)

    assert any(
        "message_fts" in statement.lower() and "match" in statement.lower()
        for statement in long_statements
    )
    assert not any("message_fts" in statement.lower() for statement in short_statements)
    assert any("like" in statement.lower() for statement in short_statements)


@requires_fts5
def test_fts_query_escaping_never_errors(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    db = DB(settings)
    with db.workspace_session(workspace_id) as session:
        writer = session.query(Agent).filter_by(workspace_id=workspace_id, role="writer").first()
        assert writer is not None
        session.add(
            AgentMemory(
                workspace_id=workspace_id,
                agent_id=writer.id,
                content='这里有 """ 与 a"b"c 与 钩"子埋 与 ……省略 与 —破折— 与 delete',
            )
        )
        session.commit()

    for keyword in ADVERSARIAL_KEYWORDS:
        liked = search_memory(db, workspace_id, keyword, _force_fts=False)
        ftsed = search_memory(db, workspace_id, keyword, _force_fts=True)
        assert ftsed.encode("utf-8") == liked.encode("utf-8"), f"keyword={keyword!r}"


@requires_fts5
def test_non_ascii_case_folding_dual_path_parity(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    db = DB(settings)
    _seed_non_ascii_layers(db, workspace_id)

    for keyword in NON_ASCII_KEYWORDS:
        liked = search_memory(db, workspace_id, keyword, _force_fts=False)
        ftsed = search_memory(db, workspace_id, keyword, _force_fts=True)
        assert ftsed.encode("utf-8") == liked.encode("utf-8"), f"memory keyword={keyword!r}"

        liked_all = search_all_layers(db, workspace_id, keyword, _force_fts=False)
        ftsed_all = search_all_layers(db, workspace_id, keyword, _force_fts=True)
        assert ftsed_all.encode("utf-8") == liked_all.encode("utf-8"), (
            f"layers keyword={keyword!r}"
        )

    # P2-1 regression: the Unicode FTS hit on CAFÉ must be pruned by the LIKE refine.
    cafe = search_memory(db, workspace_id, "café", _force_fts=True)
    assert "仓库里只有 CAFÉ 豆" not in cafe
    assert "café 柜台在转角" in cafe


def test_search_falls_back_to_like_when_fts_tables_missing(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    db = DB(settings)
    _seed_layers(db, workspace_id)

    expected_memory = search_memory(db, workspace_id, "暗线七星", _force_fts=False)
    expected_layers = search_all_layers(db, workspace_id, "暗线七星", _force_fts=False)

    path = workspace_db_path(settings, workspace_id)
    connection = sqlite3.connect(path)
    try:
        for table in FTS_TABLES:
            for suffix in ("_ai", "_ad", "_au"):
                connection.execute(f"DROP TRIGGER IF EXISTS {table}{suffix}")
            connection.execute(f"DROP TABLE IF EXISTS {table}")
        connection.commit()
    finally:
        connection.close()

    memory_result = search_memory(db, workspace_id, "暗线七星")
    layers_result = search_all_layers(db, workspace_id, "暗线七星")
    assert memory_result.encode("utf-8") == expected_memory.encode("utf-8")
    assert layers_result.encode("utf-8") == expected_layers.encode("utf-8")
    assert "[对话]" in memory_result

    memory_cli = runner.invoke(app, ["memory", "search", workspace_id, "暗线七星"])
    assert memory_cli.exit_code == 0, memory_cli.output
    assert "暗线七星" in memory_cli.output

    inspect_cli = runner.invoke(app, ["inspect", workspace_id, "暗线七星"])
    assert inspect_cli.exit_code == 0, inspect_cli.output
    assert "[对话]" in inspect_cli.output


@requires_fts5
def test_fts_probe_true_when_fts5_enabled_and_all_shadow_tables_present() -> None:
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        for name in FTS_TABLE_BY_LAYER.values():
            connection.execute(text(f"CREATE TABLE {name} (id TEXT)"))

    with Session(engine) as session:
        assert _fts_tables_present(session) is True


@requires_fts5
def test_fts_probe_false_when_fts5_enabled_but_shadow_table_missing() -> None:
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        for name in list(FTS_TABLE_BY_LAYER.values())[:-1]:
            connection.execute(text(f"CREATE TABLE {name} (id TEXT)"))

    with Session(engine) as session:
        assert _fts_tables_present(session) is False


@requires_fts5
def test_fts_probe_self_heals_residual_probe_table() -> None:
    """A leftover probe table must not disable FTS5 or leak past the probe.

    pysqlite's legacy transaction control executes DDL outside the implicit
    transaction (driver-level autocommit), so a probe interrupted between
    CREATE and DROP leaves temp._novel_fts5_probe behind on the connection.
    The probe must clear the residue before CREATE and keep reporting True
    on every new session.
    """
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE VIRTUAL TABLE temp._novel_fts5_probe "
                "USING fts5(content, tokenize='trigram')"
            )
        )

    for _ in range(3):
        with Session(engine) as session:
            assert _fts5_available(session) is True
            residual = session.execute(
                text(
                    "SELECT name FROM sqlite_temp_master "
                    "WHERE name = '_novel_fts5_probe'"
                )
            ).scalars().all()
        assert residual == []


def test_fts_probe_true_even_when_tail_cleanup_drop_fails(capsys) -> None:
    """Tail cleanup failure must not crash the probe or flip True to False.

    The final DROP is best-effort housekeeping: the next probe clears any
    residue with the DROP TABLE IF EXISTS pre-step.
    """
    statements: list[str] = []

    def execute(statement):
        sql = str(statement)
        statements.append(sql)
        if "DROP TABLE IF EXISTS temp._novel_fts5_probe" in sql:
            return None
        if "CREATE VIRTUAL TABLE" in sql:
            return None
        if sql == "DROP TABLE temp._novel_fts5_probe":
            raise _no_fts5_error(sql)
        raise AssertionError(f"unexpected statement: {sql}")

    session = SimpleNamespace(execute=execute)

    assert _fts5_available(cast(Session, session)) is True
    assert any(
        statement == "DROP TABLE temp._novel_fts5_probe" for statement in statements
    )
    assert "warning: could not drop temp FTS5 probe table" in capsys.readouterr().err


def test_fts_probe_false_when_fts5_disabled_even_if_shadow_tables_exist() -> None:
    shadow_tables = list(FTS_TABLE_BY_LAYER.values())
    statements: list[str] = []

    def execute(statement):
        sql = str(statement)
        statements.append(sql)
        if "DROP TABLE IF EXISTS temp._novel_fts5_probe" in sql:
            return None
        if "CREATE VIRTUAL TABLE" in sql:
            raise _no_fts5_error(sql)
        if "sqlite_master" in sql:
            return SimpleNamespace(scalars=lambda: iter(shadow_tables))
        raise AssertionError(f"unexpected statement: {sql}")

    session = SimpleNamespace(execute=execute)

    assert _fts_tables_present(cast(Session, session)) is False
    # Fail closed before consulting sqlite_master: even a database that still
    # holds all five shadow tables falls back once the runtime probe fails.
    assert any(
        "DROP TABLE IF EXISTS temp._novel_fts5_probe" in statement
        for statement in statements
    )
    assert any("CREATE VIRTUAL TABLE" in statement for statement in statements)
    assert not any("sqlite_master" in statement for statement in statements)


@requires_fts5
def test_fts_path_uses_join_like_refine_not_in_list(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    db = DB(settings)
    _seed_layers(db, workspace_id)

    captured: list[tuple[str, tuple | dict]] = []

    def capture(conn, cursor, statement, parameters, context, executemany) -> None:
        captured.append((statement, parameters or ()))

    event.listen(Engine, "after_cursor_execute", capture)
    try:
        search_all_layers(db, workspace_id, "暗线七星")
    finally:
        event.remove(Engine, "after_cursor_execute", capture)

    fts_match = [
        statement
        for statement, _ in captured
        if "message_fts" in statement.lower() and "match" in statement.lower()
    ]
    assert fts_match, "no FTS MATCH statement reached the message layer"

    joined_like = [
        statement
        for statement, _ in captured
        if "join" in statement.lower()
        and "message_fts" in statement.lower()
        and "like" in statement.lower()
    ]
    assert joined_like, "FTS content filter was not a JOIN plus LIKE refine"

    assert not any(" in (" in statement.lower() for statement, _ in captured)
    max_params = max((len(parameters) for _, parameters in captured), default=0)
    assert max_params < 32, f"found a statement with {max_params} bound parameters"


@requires_fts5
def test_fts5_availability_detection() -> None:
    migration = _load_fts_migration_module()

    with create_engine("sqlite://").connect() as connection:
        assert migration._fts5_available(connection) is True

    without_fts5 = SimpleNamespace(execute=_raise_no_fts5)
    assert migration._fts5_available(without_fts5) is False


def test_fts_migration_skips_when_fts5_unavailable(capsys) -> None:
    migration = _load_fts_migration_module()
    executed: list[str] = []
    probed: list[str] = []

    def execute(statement):
        sql = str(statement)
        probed.append(sql)
        if "DROP TABLE IF EXISTS temp._novel_fts5_probe" in sql:
            return None
        raise _no_fts5_error(sql)

    without_fts5 = SimpleNamespace(
        execute=execute,
    )
    fake_op = SimpleNamespace(
        get_bind=lambda: without_fts5,
        execute=lambda statement: executed.append(str(statement)),
    )
    with mock.patch.object(migration, "op", fake_op):
        migration.upgrade()

    assert executed == []
    assert any("CREATE VIRTUAL TABLE" in statement for statement in probed)
    assert "FTS5" in capsys.readouterr().err
