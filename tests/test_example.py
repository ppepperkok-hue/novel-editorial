"""Tests for M5-N11-R1: example editorial-office seeding service."""

from __future__ import annotations

import os
from pathlib import Path

from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.behavior import list_behavior_timeline
from novel_editorial.core.chat import list_messages
from novel_editorial.core.config import load_settings
from novel_editorial.core.draft import list_drafts
from novel_editorial.core.example import (
    DRAFT_CONTENT,
    DRAFT_TITLE,
    EXAMPLE_DESCRIPTION,
    EXAMPLE_GENRE,
    EXAMPLE_TITLE,
    STYLE_DESCRIPTION,
    STYLE_FORBIDDEN_WORDS,
    ExampleResult,
    seed_example_workspace,
)
from novel_editorial.core.memory import list_memory_notes
from novel_editorial.core.outline import list_outline_versions
from novel_editorial.core.overview import build_overview
from novel_editorial.core.plot import list_threads
from novel_editorial.core.setting import add_setting, list_settings
from novel_editorial.core.structure import list_structure
from novel_editorial.core.style import get_style_anchor
from novel_editorial.core.workspace import create_workspace
from novel_editorial.events import EventType
from novel_editorial.store.db import DB
from novel_editorial.store.events import list_events
from novel_editorial.store.models import (
    Draft,
    DraftVersion,
    StyleAnchor,
    Workspace,
)

runner = CliRunner()


def _db(tmp_path: Path, monkeypatch) -> DB:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    db = DB(load_settings())
    db.init_schema()
    return db


def test_seed_builds_every_editorial_layer(tmp_path: Path, monkeypatch) -> None:
    db = _db(tmp_path, monkeypatch)
    result = seed_example_workspace(db)

    assert isinstance(result, ExampleResult)
    assert result.title == EXAMPLE_TITLE
    assert result.genre == EXAMPLE_GENRE
    assert result.settings >= 2
    assert result.outline == 1
    assert result.structure_nodes == 4
    assert result.messages >= 2
    assert result.drafts == 1
    assert result.threads >= 1
    assert result.notes >= 1
    assert result.behavior_entries >= 1
    assert result.events >= 3

    with db.global_session() as session:
        workspace = session.get(Workspace, result.workspace_id)
    assert workspace is not None
    assert workspace.title == EXAMPLE_TITLE
    assert workspace.genre == "悬疑"
    assert EXAMPLE_DESCRIPTION in workspace.description
    assert workspace.status == "writing"

    anchor = get_style_anchor(db, result.workspace_id)
    assert anchor.description == STYLE_DESCRIPTION
    assert "璀璨" in anchor.forbidden_words
    assert "宛如" in anchor.forbidden_words
    assert STYLE_FORBIDDEN_WORDS == "璀璨、宛如"

    settings = list_settings(db, result.workspace_id)
    assert {entry.kind for entry in settings} >= {"character", "timeline", "world"}

    outlines = list_outline_versions(db, result.workspace_id)
    assert [row.version for row in outlines] == [1]

    nodes = list_structure(db, result.workspace_id)
    assert [node.kind for node in nodes] == ["volume", "chapter", "chapter", "chapter"]
    assert nodes[0].title == "第一卷 旧车站"
    assert nodes[1].title == "第一章 雨夜"
    assert nodes[1].status == "completed"
    assert all(node.status == "writing" for node in nodes[2:])

    messages = list_messages(db, result.workspace_id)
    assert messages[0].role == "author"
    assert sum(1 for message in messages if message.role == "agent") >= 1
    assert any('"initiator": "agent"' in message.payload for message in messages)

    drafts = list_drafts(db, result.workspace_id)
    assert len(drafts) == 1
    assert drafts[0].title == DRAFT_TITLE
    assert drafts[0].status == "draft"
    assert drafts[0].current_version == 1
    with db.workspace_session(result.workspace_id) as session:
        version = (
            session.query(DraftVersion)
            .filter_by(draft_id=drafts[0].id, version=1)
            .first()
        )
        raw = session.query(Draft).filter_by(id=drafts[0].id).first()
    assert version is not None
    assert version.content == DRAFT_CONTENT
    assert raw is not None and raw.status == "draft"

    threads = list_threads(db, result.workspace_id)
    assert len(threads) >= 1
    assert all(thread.kind == "foreshadow" for thread in threads)

    notes = list_memory_notes(db, result.workspace_id)
    assert len(notes) >= 1

    behavior = list_behavior_timeline(db, result.workspace_id, limit=1000)
    assert len(behavior) >= 1

    events = list_events(db, result.workspace_id, limit=1000)
    event_types = {event.type for event in events}
    assert EventType.DRAFT_CREATED.value in event_types
    assert EventType.QUALITY_GATE_PASSED.value in event_types
    assert EventType.DECISION_REQUESTED.value in event_types
    assert EventType.AGENT_MESSAGE.value in event_types


def test_seed_shows_in_works_overview(tmp_path: Path, monkeypatch) -> None:
    db = _db(tmp_path, monkeypatch)
    result = seed_example_workspace(db)

    report = build_overview(db)
    rows = [item for item in report.overviews if item.workspace_id == result.workspace_id]
    assert len(rows) == 1
    assert rows[0].title == EXAMPLE_TITLE
    assert rows[0].genre == "悬疑"
    assert rows[0].pending_count == 1
    assert rows[0].structure == "1/3 章"

    cli = runner.invoke(app, ["works", "overview"])
    assert cli.exit_code == 0, cli.output
    assert "示例·雨夜车站" in cli.output
    assert "待拍板 1" in cli.output
    assert "进度 1/3 章" in cli.output


def test_seed_runs_without_llm_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("NOVEL_LLM_API_KEY", raising=False)
    monkeypatch.delenv("NOVEL_LLM_MODEL", raising=False)
    monkeypatch.delenv("NOVEL_LLM_BASE_URL", raising=False)
    assert os.environ.get("NOVEL_LLM_API_KEY") is None

    db = _db(tmp_path, monkeypatch)
    result = seed_example_workspace(db)

    assert result.workspace_id
    assert len(list_events(db, result.workspace_id, limit=1000)) >= 3


def test_repeated_seed_creates_new_workspace_and_keeps_old(
    tmp_path: Path, monkeypatch
) -> None:
    db = _db(tmp_path, monkeypatch)
    first = seed_example_workspace(db)
    second = seed_example_workspace(db)

    assert first.workspace_id != second.workspace_id

    assert len(list_settings(db, first.workspace_id)) == first.settings
    assert get_style_anchor(db, first.workspace_id).description == STYLE_DESCRIPTION
    assert len(list_drafts(db, first.workspace_id)) == first.drafts
    assert len(list_messages(db, first.workspace_id)) == first.messages
    assert len(list_threads(db, first.workspace_id)) == first.threads
    assert len(list_memory_notes(db, first.workspace_id)) == first.notes
    assert (
        len(list_behavior_timeline(db, first.workspace_id, limit=1000))
        == first.behavior_entries
    )
    assert len(list_events(db, first.workspace_id, limit=1000)) == first.events

    report = build_overview(db)
    assert {item.workspace_id for item in report.overviews} >= {
        first.workspace_id,
        second.workspace_id,
    }


def test_seed_does_not_touch_existing_workspace(
    tmp_path: Path, monkeypatch
) -> None:
    db = _db(tmp_path, monkeypatch)
    normal = create_workspace(
        db,
        title="普通作品",
        genre="都市",
        description="既有作品简介",
    )
    add_setting(
        db,
        normal.id,
        kind="character",
        name="路人甲",
        content="普通设定",
    )

    result = seed_example_workspace(db)

    assert result.workspace_id != normal.id
    with db.global_session() as session:
        row = session.get(Workspace, normal.id)
    assert row is not None
    assert row.title == "普通作品"
    assert row.genre == "都市"
    assert row.description == "既有作品简介"
    assert row.status == "writing"
    assert len(list_settings(db, normal.id)) == 1
    assert list_messages(db, normal.id) == []
    assert len(list_drafts(db, normal.id)) == 0
    with db.workspace_session(normal.id) as session:
        assert (
            session.query(StyleAnchor)
            .filter_by(workspace_id=normal.id)
            .first()
            is None
        )
