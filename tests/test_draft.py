import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core import proactive
from novel_editorial.core.chat import list_messages
from novel_editorial.core.config import load_settings
from novel_editorial.core.draft import build_memory_pack, get_draft_version
from novel_editorial.core.memory import archive_memory_notes
from novel_editorial.core.style import get_style_anchor
from novel_editorial.llm.client import MockLLMClient
from novel_editorial.store.db import DB
from novel_editorial.store.events import list_events
from novel_editorial.store.models import Agent, AgentMemory, Draft

runner = CliRunner()


def _create_workspace(tmp_path: Path, monkeypatch, title: str = "风格之书") -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["works", "create", title, "--genre", "武侠"])
    assert result.exit_code == 0, result.output
    return result.output.split()[2].rstrip(":")


def _writer_id(db: DB, workspace_id: str) -> str:
    with db.workspace_session(workspace_id) as session:
        writer = session.query(Agent).filter_by(workspace_id=workspace_id, role="writer").first()
        assert writer is not None
        return writer.id


def _add_raw_note(
    db: DB,
    workspace_id: str,
    agent_id: str,
    content: str,
    *,
    strength: int = 100,
) -> AgentMemory:
    with db.workspace_session(workspace_id) as session:
        note = AgentMemory(
            workspace_id=workspace_id,
            agent_id=agent_id,
            content=content,
            strength=strength,
            last_accessed_at=datetime.now(UTC),
        )
        session.add(note)
        session.commit()
        return note


@pytest.mark.smoke
def test_style_set_and_show(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(
        app,
        [
            "style",
            "set",
            workspace_id,
            "--description",
            "平实克制的文风，短句为主",
            "--forbidden",
            "璀璨,瞬间,宛如",
        ],
    )
    assert result.exit_code == 0, result.output

    settings = load_settings()
    anchor = get_style_anchor(DB(settings), workspace_id)
    assert anchor.description == "平实克制的文风，短句为主"
    assert anchor.forbidden_words == "璀璨,瞬间,宛如"

    shown = runner.invoke(app, ["style", "show", workspace_id])
    assert shown.exit_code == 0
    assert "平实克制的文风" in shown.output


@pytest.mark.smoke
def test_memory_pack_is_isolated_per_workspace(tmp_path: Path, monkeypatch) -> None:
    first_id = _create_workspace(tmp_path, monkeypatch, title="第一本书")
    second_id = _create_workspace(tmp_path, monkeypatch, title="第二本书")
    runner.invoke(
        app,
        ["style", "set", first_id, "--description", "第一本的风格", "--forbidden", "甲词"],
    )

    first_pack = runner.invoke(app, ["memory", "pack", first_id])
    second_pack = runner.invoke(app, ["memory", "pack", second_id])
    assert first_pack.exit_code == 0 and second_pack.exit_code == 0
    assert "第一本书" in first_pack.output
    assert "第一本的风格" in first_pack.output
    assert "第二本书" not in first_pack.output
    assert "第一本书" not in second_pack.output


def test_memory_pack_excludes_archived_and_sorts_by_strength(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    db = DB(settings)
    writer_id = _writer_id(db, workspace_id)
    strong = _add_raw_note(db, workspace_id, writer_id, "强记忆", strength=100)
    weak = _add_raw_note(db, workspace_id, writer_id, "弱记忆", strength=30)
    archived = _add_raw_note(db, workspace_id, writer_id, "归档强记忆", strength=200)
    archive_memory_notes(db, workspace_id, [archived.id])

    packed = build_memory_pack(db, workspace_id)
    assert packed.index(strong.content) < packed.index(weak.content)
    assert archived.content not in packed


@pytest.mark.smoke
def test_draft_generate_versions_and_diff(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    replies = iter(["雨夜的开场，第一版。", "雨夜的开场，第二版，更冷。"])
    monkeypatch.setattr(
        "novel_editorial.cli.draft.build_client",
        lambda settings: MockLLMClient(reply=next(replies)),
    )

    first = runner.invoke(app, ["draft", "generate", workspace_id, "--title", "雨夜"])
    assert first.exit_code == 0, first.output
    draft_id = first.output.split()[1]

    second = runner.invoke(app, ["draft", "generate", workspace_id, "--title", "雨夜"])
    assert second.exit_code == 0, second.output
    assert "v2" in second.output

    listing = runner.invoke(app, ["draft", "list", workspace_id])
    assert listing.exit_code == 0
    assert "雨夜" in listing.output

    shown = runner.invoke(app, ["draft", "show", draft_id])
    assert shown.exit_code == 0
    assert "第二版，更冷" in shown.output

    diff = runner.invoke(app, ["draft", "diff", draft_id, "1", "2"])
    assert diff.exit_code == 0
    assert "第一版" in diff.output
    assert "第二版" in diff.output

    settings = load_settings()
    version = get_draft_version(DB(settings), workspace_id, draft_id, 1)
    assert version.reason == "initial"


def test_draft_show_missing_and_diff_missing(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "novel_editorial.cli.draft.build_client",
        lambda settings: MockLLMClient(reply="内容"),
    )
    created = runner.invoke(app, ["draft", "generate", workspace_id, "--title", "章一"])
    draft_id = created.output.split()[1]

    missing = runner.invoke(app, ["draft", "show", "nope"])
    assert missing.exit_code == 1
    assert "draft not found" in missing.output

    bad_diff = runner.invoke(app, ["draft", "diff", draft_id, "1", "99"])
    assert bad_diff.exit_code == 1
    assert "draft version not found" in bad_diff.output


def test_draft_generate_rejects_empty_content(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "novel_editorial.cli.draft.build_client",
        lambda settings: MockLLMClient(reply="   "),
    )

    result = runner.invoke(app, ["draft", "generate", workspace_id, "--title", "空章"])
    assert result.exit_code == 1
    assert "empty draft content" in result.output

    listing = runner.invoke(app, ["draft", "list", workspace_id])
    assert listing.exit_code == 0
    assert "空章" not in listing.output


def test_draft_generate_emits_writer_report_and_editor_review(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "novel_editorial.cli.draft.build_client",
        lambda settings: MockLLMClient(reply="正文内容"),
    )

    result = runner.invoke(app, ["draft", "generate", workspace_id, "--title", "第一章"])
    assert result.exit_code == 0, result.output
    assert "写手: 《第一章》初稿写完了" in result.output
    assert "责编: 《第一章》过了质量门，我试读了开头「正文内容」" in result.output

    db = DB(load_settings())
    messages = list_messages(db, workspace_id)
    writer_reports = [
        m
        for m in messages
        if m.actor == "写手"
        and json.loads(m.payload)["kind"] == proactive.PROACTIVE_KIND_REPORT
    ]
    editor_reviews = [
        m
        for m in messages
        if m.actor == "责编"
        and json.loads(m.payload)["kind"] == proactive.PROACTIVE_KIND_REVIEW
    ]
    assert len(writer_reports) == 1
    assert json.loads(writer_reports[0].payload) == {
        "initiator": "agent",
        "kind": "proactive_report",
        "trigger": "draft_generated",
    }
    assert len(editor_reviews) == 1
    assert json.loads(editor_reviews[0].payload)["trigger"] == "draft_gate_passed"

    events = list_events(db, workspace_id)
    agent_events = [event for event in events if event.type == "agent.message"]
    assert len(agent_events) == 2
    kinds = {json.loads(event.payload)["kind"] for event in agent_events}
    assert kinds == {"proactive_report", "proactive_review"}


def test_draft_revise_emits_writer_question(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    replies = iter(["初稿内容", "修订稿内容"])
    monkeypatch.setattr(
        "novel_editorial.cli.draft.build_client",
        lambda settings: MockLLMClient(reply=next(replies)),
    )
    created = runner.invoke(app, ["draft", "generate", workspace_id, "--title", "第一章"])
    assert created.exit_code == 0, created.output
    draft_id = created.output.split()[1]

    revised = runner.invoke(app, ["draft", "revise", draft_id, "--reason", "收钩子"])
    assert revised.exit_code == 0, revised.output
    assert "写手: 这章我留了个钩子，下章要不要收？" in revised.output

    db = DB(load_settings())
    questions = [
        m
        for m in list_messages(db, workspace_id)
        if json.loads(m.payload)["kind"] == proactive.PROACTIVE_KIND_QUESTION
    ]
    assert len(questions) == 1
    assert questions[0].actor == "写手"
    assert json.loads(questions[0].payload)["trigger"] == "draft_revised"


def test_draft_regenerate_reports_and_reviews_only_initial_version(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    replies = iter(["第一版正文", "第二版正文"])
    monkeypatch.setattr(
        "novel_editorial.cli.draft.build_client",
        lambda settings: MockLLMClient(reply=next(replies)),
    )

    first = runner.invoke(app, ["draft", "generate", workspace_id, "--title", "雨夜"])
    assert first.exit_code == 0, first.output
    assert "写手: 《雨夜》初稿写完了" in first.output
    assert "责编: 《雨夜》过了质量门" in first.output

    second = runner.invoke(app, ["draft", "generate", workspace_id, "--title", "雨夜"])
    assert second.exit_code == 0, second.output
    assert "v2" in second.output
    assert "写手: 《雨夜》初稿写完了" not in second.output
    assert "责编: 《雨夜》过了质量门" not in second.output

    db = DB(load_settings())
    messages = list_messages(db, workspace_id)
    writer_reports = [
        message
        for message in messages
        if message.actor == "写手"
        and json.loads(message.payload)["kind"] == proactive.PROACTIVE_KIND_REPORT
    ]
    editor_reviews = [
        message
        for message in messages
        if message.actor == "责编"
        and json.loads(message.payload)["kind"] == proactive.PROACTIVE_KIND_REVIEW
    ]
    assert len(writer_reports) == 1
    assert len(editor_reviews) == 1
    assert proactive.count_proactive_messages(db, workspace_id, "写手") == 1
    assert proactive.count_proactive_messages(db, workspace_id, "责编") == 1


def test_draft_revise_quality_failure_suppresses_writer_question(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "novel_editorial.cli.draft.build_client",
        lambda settings: MockLLMClient(reply="正文内容"),
    )
    created = runner.invoke(app, ["draft", "generate", workspace_id, "--title", "第一章"])
    assert created.exit_code == 0, created.output
    draft_id = created.output.split()[1]

    monkeypatch.setenv("NOVEL_QUALITY_THRESHOLD", "-1")
    revised = runner.invoke(app, ["draft", "revise", draft_id, "--reason", "收钩子"])
    assert revised.exit_code == 0, revised.output
    assert "写手: 这章我留了个钩子，下章要不要收？" not in revised.output
    assert "awaiting decision" not in revised.output

    db = DB(load_settings())
    questions = [
        message
        for message in list_messages(db, workspace_id)
        if json.loads(message.payload)["kind"] == proactive.PROACTIVE_KIND_QUESTION
    ]
    assert questions == []


def test_disabled_proactive_suppresses_draft_messages(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NOVEL_PROACTIVE_ENABLED", "false")
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    replies = iter(["初稿内容", "修订稿内容"])
    monkeypatch.setattr(
        "novel_editorial.cli.draft.build_client",
        lambda settings: MockLLMClient(reply=next(replies)),
    )
    created = runner.invoke(app, ["draft", "generate", workspace_id, "--title", "第一章"])
    assert created.exit_code == 0, created.output
    assert "写手:" not in created.output
    assert "责编:" not in created.output
    draft_id = created.output.split()[1]

    revised = runner.invoke(app, ["draft", "revise", draft_id, "--reason", "收钩子"])
    assert revised.exit_code == 0, revised.output
    assert "写手:" not in revised.output
    assert "责编:" not in revised.output

    db = DB(load_settings())
    proactive_messages = [
        m for m in list_messages(db, workspace_id) if '"initiator": "agent"' in m.payload
    ]
    assert proactive_messages == []


def test_writer_proactive_budget_stops_after_max(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NOVEL_PROACTIVE_MAX_PER_AGENT", "2")
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "novel_editorial.cli.draft.build_client",
        lambda settings: MockLLMClient(reply="正文内容"),
    )

    first = runner.invoke(app, ["draft", "generate", workspace_id, "--title", "第一章"])
    assert first.exit_code == 0, first.output
    assert "写手: 《第一章》初稿写完了" in first.output
    draft_id = first.output.split()[1]

    revised = runner.invoke(app, ["draft", "revise", draft_id, "--reason", "收钩子"])
    assert revised.exit_code == 0, revised.output
    assert "写手: 这章我留了个钩子，下章要不要收？" in revised.output

    third = runner.invoke(app, ["draft", "generate", workspace_id, "--title", "第二章"])
    assert third.exit_code == 0, third.output
    assert "写手:" not in third.output
    assert "责编: 《第二章》过了质量门" in third.output


def test_proactive_failure_does_not_roll_back_business(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "novel_editorial.cli.draft.build_client",
        lambda settings: MockLLMClient(reply="正文内容"),
    )

    def boom(db, workspace_id, trigger, context=None):
        raise RuntimeError("proactive write failed")

    monkeypatch.setattr(
        "novel_editorial.cli.draft.proactive.record_proactive_messages", boom
    )
    result = runner.invoke(app, ["draft", "generate", workspace_id, "--title", "第一章"])
    assert result.exit_code == 0, result.output
    assert "warning: proactive messages skipped" in result.output
    assert "proactive write failed" in result.output

    db = DB(load_settings())
    with db.workspace_session(workspace_id) as session:
        draft = session.query(Draft).filter_by(title="第一章").first()
    assert draft is not None
    assert draft.current_version == 1
