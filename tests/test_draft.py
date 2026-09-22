import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core import proactive
from novel_editorial.core.agents import create_agent, get_default_writer
from novel_editorial.core.chat import list_messages
from novel_editorial.core.config import load_settings
from novel_editorial.core.draft import (
    build_memory_pack,
    create_author_draft,
    generate_draft,
    get_draft_version,
    list_pending_drafts,
    revise_draft,
    save_author_version,
)
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.core.memory import archive_memory_notes
from novel_editorial.core.motives import list_motives
from novel_editorial.core.outline import create_outline, revise_outline
from novel_editorial.core.setting import add_setting, revise_setting
from novel_editorial.core.style import get_style_anchor
from novel_editorial.llm.client import LLMResult, MockLLMClient
from novel_editorial.store.db import DB, workspace_db_path
from novel_editorial.store.events import list_events
from novel_editorial.store.models import Agent, AgentMemory, AgentRole, Draft, DraftVersion

runner = CliRunner()


class _CaptureClient(MockLLMClient):
    def __init__(self, reply: str = "正文内容") -> None:
        super().__init__(reply)
        self.calls: list = []

    def complete(self, messages):
        self.calls.append(messages)
        return LLMResult(content=self.reply)


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


def test_memory_pack_includes_current_settings_in_kind_order(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    add_setting(
        db,
        workspace_id,
        kind="character",
        name="沈夜",
        content="雨夜归乡的侦探",
    )
    add_setting(
        db,
        workspace_id,
        kind="timeline",
        name="时间线",
        content="第一章发生在雨夜",
    )
    add_setting(
        db,
        workspace_id,
        kind="world",
        name="世界观",
        content="灵气复苏三百年",
    )
    add_setting(
        db,
        workspace_id,
        kind="relation",
        name="沈夜与林墨",
        content="旧识",
    )

    packed = build_memory_pack(db, workspace_id)
    assert "设定：" in packed
    assert "- [人物] 沈夜 v1 雨夜归乡的侦探（来源: 作者）" in packed
    assert "- [关系] 沈夜与林墨 v1 旧识（来源: 作者）" in packed
    assert "- [时间线] 时间线 v1 第一章发生在雨夜（来源: 作者）" in packed
    assert "- [世界观] 世界观 v1 灵气复苏三百年（来源: 作者）" in packed
    setting_lines = [
        line
        for line in packed.splitlines()
        if line.startswith("- [人物] ")
        or line.startswith("- [关系] ")
        or line.startswith("- [时间线] ")
        or line.startswith("- [世界观] ")
    ]
    assert [
        line.split()[1].strip("[]") for line in setting_lines
    ] == ["人物", "关系", "时间线", "世界观"]


def test_memory_pack_settings_follow_private_memory_before_hanging_threads(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    add_setting(db, workspace_id, kind="character", name="沈夜", content="侦探")
    writer_id = _writer_id(db, workspace_id)
    _add_raw_note(db, workspace_id, writer_id, "写手私记")

    packed = build_memory_pack(db, workspace_id)
    assert packed.index("私有记忆") < packed.index("设定：")
    assert "悬置线索" not in packed


def test_memory_pack_without_settings_has_no_setting_section(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    packed = build_memory_pack(DB(load_settings()), workspace_id)
    assert "设定：" not in packed
    assert "（来源:" not in packed


def test_memory_pack_keeps_outline_placeholder_without_outline(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    packed = build_memory_pack(DB(load_settings()), workspace_id)
    assert "章纲：暂无（占位）" in packed


def test_memory_pack_injects_current_outline_content(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    create_outline(db, workspace_id, content="楔子：雨夜车站", actor="作者")

    packed = build_memory_pack(db, workspace_id)
    assert "章纲：楔子：雨夜车站" in packed
    assert "章纲：暂无（占位）" not in packed

    revise_outline(
        db,
        workspace_id,
        content="楔子：雨夜车站，钟停十一点",
        reason="加悬念",
        actor="责编",
    )
    packed = build_memory_pack(db, workspace_id)
    assert "章纲：楔子：雨夜车站，钟停十一点" in packed


def test_memory_pack_collapses_and_truncates_outline(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    create_outline(db, workspace_id, content="第一行\n\n  第二行  内容", actor="作者")

    packed = build_memory_pack(db, workspace_id)
    assert "章纲：第一行 第二行 内容" in packed

    revise_outline(
        db,
        workspace_id,
        content="字" * 150,
        reason="超长",
        actor="作者",
    )
    packed = build_memory_pack(db, workspace_id)
    assert f"章纲：{'字' * 120}…" in packed
    assert "章纲：第一行" not in packed


def test_memory_pack_shows_revised_setting_version(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    entry = add_setting(
        db,
        workspace_id,
        kind="character",
        name="沈夜",
        content="初版设定",
    )

    assert "v1 初版设定" in build_memory_pack(db, workspace_id)
    revise_setting(
        db,
        workspace_id,
        entry.id,
        content="修订后的设定",
        reason="角色弧线调整",
        actor="责编",
    )
    assert "v2 修订后的设定" in build_memory_pack(db, workspace_id)
    assert "v1 初版设定" not in build_memory_pack(db, workspace_id)


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


def test_generate_draft_with_explicit_writer_isolates_memory(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    default_writer = get_default_writer(db, workspace_id)
    second_writer = create_agent(
        db, workspace_id, name="写手乙", role=AgentRole.WRITER
    )
    _add_raw_note(db, workspace_id, default_writer.id, "默认写手的私记")
    _add_raw_note(db, workspace_id, second_writer.id, "写手乙的私记")

    client = _CaptureClient()
    draft = generate_draft(
        db, workspace_id, title="第一章", client=client, writer=second_writer
    )
    assert draft.writer_id == second_writer.id
    prompt = client.calls[0][0].content
    assert "写手乙的私记" in prompt
    assert "默认写手的私记" not in prompt

    default_pack = build_memory_pack(db, workspace_id)
    assert "默认写手的私记" in default_pack
    assert "写手乙的私记" not in default_pack


def test_generate_draft_without_writer_uses_default_writer(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    default_writer = get_default_writer(db, workspace_id)
    second_writer = create_agent(
        db, workspace_id, name="写手乙", role=AgentRole.WRITER
    )
    _add_raw_note(db, workspace_id, default_writer.id, "默认写手的私记")
    _add_raw_note(db, workspace_id, second_writer.id, "写手乙的私记")

    client = _CaptureClient()
    draft = generate_draft(db, workspace_id, title="第一章", client=client)
    assert draft.writer_id == default_writer.id
    prompt = client.calls[0][0].content
    assert "默认写手的私记" in prompt
    assert "写手乙的私记" not in prompt


def test_revise_draft_defaults_to_original_writer(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    second_writer = create_agent(
        db, workspace_id, name="写手乙", role=AgentRole.WRITER
    )
    _add_raw_note(db, workspace_id, second_writer.id, "写手乙的私记")
    draft = generate_draft(
        db,
        workspace_id,
        title="第一章",
        client=_CaptureClient(),
        writer=second_writer,
    )
    assert draft.writer_id == second_writer.id

    revised_client = _CaptureClient(reply="修订稿内容")
    revised = revise_draft(
        db,
        workspace_id,
        draft.id,
        reason="收钩子",
        client=revised_client,
    )
    assert revised.writer_id == second_writer.id
    prompt = revised_client.calls[0][0].content
    assert "写手乙的私记" in prompt


def test_revise_draft_explicit_writer_switches(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    default_writer = get_default_writer(db, workspace_id)
    second_writer = create_agent(
        db, workspace_id, name="写手乙", role=AgentRole.WRITER
    )
    _add_raw_note(db, workspace_id, default_writer.id, "默认写手的私记")
    _add_raw_note(db, workspace_id, second_writer.id, "写手乙的私记")
    draft = generate_draft(
        db, workspace_id, title="第一章", client=_CaptureClient()
    )
    assert draft.writer_id == default_writer.id

    revised_client = _CaptureClient(reply="修订稿内容")
    revised = revise_draft(
        db,
        workspace_id,
        draft.id,
        reason="换人改",
        client=revised_client,
        writer=second_writer,
    )
    assert revised.writer_id == second_writer.id
    prompt = revised_client.calls[0][0].content
    assert "写手乙的私记" in prompt
    assert "默认写手的私记" not in prompt


def test_draft_migration_backfills_default_writer(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    db = DB(settings)
    default_writer = get_default_writer(db, workspace_id)
    create_agent(db, workspace_id, name="写手乙", role=AgentRole.WRITER)
    with db.workspace_session(workspace_id) as session:
        old_draft = Draft(workspace_id=workspace_id, title="旧章")
        session.add(old_draft)
        session.commit()
        old_draft_id = old_draft.id

    path = workspace_db_path(settings, workspace_id)
    for _ in range(2):
        connection = sqlite3.connect(path)
        connection.execute("ALTER TABLE drafts DROP COLUMN writer_id")
        connection.execute("DELETE FROM alembic_version")
        connection.execute(
            "INSERT INTO alembic_version (version_num) VALUES ('d3c2b1a09f8e')"
        )
        connection.commit()
        connection.close()

        upgraded = DB(settings)
        with upgraded.workspace_session(workspace_id) as session:
            draft = session.query(Draft).filter_by(id=old_draft_id).first()
            assert draft is not None
            assert draft.writer_id == default_writer.id


def test_draft_generate_cli_with_writer_and_list_visibility(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "novel_editorial.cli.draft.build_client",
        lambda settings: MockLLMClient(reply="正文内容"),
    )
    assert (
        runner.invoke(
            app, ["agents", "add", workspace_id, "写手", "写手乙"]
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(
            app, ["agents", "add", workspace_id, "writer", "写手丙"]
        ).exit_code
        == 0
    )

    first = runner.invoke(
        app,
        ["draft", "generate", workspace_id, "--title", "第一章", "--writer", "写手乙"],
    )
    assert first.exit_code == 0, first.output
    first_id = first.output.split()[1]

    second = runner.invoke(
        app,
        ["draft", "generate", workspace_id, "--title", "第二章", "--writer", "写手丙"],
    )
    assert second.exit_code == 0, second.output
    second_id = second.output.split()[1]

    listing = runner.invoke(app, ["draft", "list", workspace_id])
    assert listing.exit_code == 0, listing.output
    assert f"{first_id}  第一章" in listing.output
    assert f"{second_id}  第二章" in listing.output
    assert "（写手乙）" in listing.output
    assert "（写手丙）" in listing.output

    shown = runner.invoke(app, ["draft", "show", first_id])
    assert shown.exit_code == 0, shown.output
    assert "writer: 写手乙" in shown.output

    shown_second = runner.invoke(app, ["draft", "show", second_id])
    assert shown_second.exit_code == 0, shown_second.output
    assert "writer: 写手丙" in shown_second.output


def test_draft_generate_sediments_motive_to_actual_writer(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    default_writer = get_default_writer(db, workspace_id)
    second_writer = create_agent(
        db, workspace_id, name="写手乙", role=AgentRole.WRITER
    )
    monkeypatch.setattr(
        "novel_editorial.cli.draft.build_client",
        lambda settings: MockLLMClient(reply="正文内容"),
    )

    result = runner.invoke(
        app,
        ["draft", "generate", workspace_id, "--title", "第一章", "--writer", "写手乙"],
    )
    assert result.exit_code == 0, result.output

    motives = list_motives(db, workspace_id)
    assert len(motives) == 1
    assert motives[0].agent_id == second_writer.id
    assert motives[0].agent_id != default_writer.id


def test_draft_generate_cli_writer_memory_isolation(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    writer_id = _writer_id(db, workspace_id)
    second = create_agent(db, workspace_id, name="写手乙", role=AgentRole.WRITER)
    _add_raw_note(db, workspace_id, writer_id, "默认写手的私记")
    _add_raw_note(db, workspace_id, second.id, "写手乙的私记")

    client = _CaptureClient()
    monkeypatch.setattr(
        "novel_editorial.cli.draft.build_client", lambda settings: client
    )
    result = runner.invoke(
        app,
        ["draft", "generate", workspace_id, "--title", "第一章", "--writer", "写手乙"],
    )
    assert result.exit_code == 0, result.output
    prompt = client.calls[0][0].content
    assert "写手乙的私记" in prompt
    assert "默认写手的私记" not in prompt
    with db.workspace_session(workspace_id) as session:
        draft = session.query(Draft).filter_by(title="第一章").first()
    assert draft is not None
    assert draft.writer_id == second.id


def test_draft_generate_cli_rejects_non_writer_and_unknown(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "novel_editorial.cli.draft.build_client",
        lambda settings: MockLLMClient(reply="正文内容"),
    )
    non_writer = runner.invoke(
        app,
        ["draft", "generate", workspace_id, "--title", "第一章", "--writer", "责编"],
    )
    assert non_writer.exit_code == 2
    assert "not a writer" in non_writer.output

    unknown = runner.invoke(
        app,
        ["draft", "generate", workspace_id, "--title", "第一章", "--writer", "路人"],
    )
    assert unknown.exit_code == 1
    assert "agent not found" in unknown.output


def test_draft_revise_cli_default_keeps_original_writer(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    second = create_agent(db, workspace_id, name="写手乙", role=AgentRole.WRITER)
    _add_raw_note(db, workspace_id, second.id, "写手乙的私记")
    monkeypatch.setattr(
        "novel_editorial.cli.draft.build_client",
        lambda settings: MockLLMClient(reply="初稿内容"),
    )
    created = runner.invoke(
        app,
        ["draft", "generate", workspace_id, "--title", "第一章", "--writer", "写手乙"],
    )
    assert created.exit_code == 0, created.output
    draft_id = created.output.split()[1]

    revised = runner.invoke(app, ["draft", "revise", draft_id, "--reason", "收钩子"])
    assert revised.exit_code == 0, revised.output
    with db.workspace_session(workspace_id) as session:
        draft = session.query(Draft).filter_by(id=draft_id).first()
    assert draft is not None
    assert draft.writer_id == second.id

    shown = runner.invoke(app, ["draft", "show", draft_id])
    assert shown.exit_code == 0, shown.output
    assert "writer: 写手乙" in shown.output


def test_draft_revise_cli_explicit_writer_switch(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    default_writer = get_default_writer(db, workspace_id)
    second = create_agent(db, workspace_id, name="写手乙", role=AgentRole.WRITER)
    _add_raw_note(db, workspace_id, default_writer.id, "默认写手的私记")
    _add_raw_note(db, workspace_id, second.id, "写手乙的私记")
    monkeypatch.setattr(
        "novel_editorial.cli.draft.build_client",
        lambda settings: MockLLMClient(reply="初稿内容"),
    )
    created = runner.invoke(app, ["draft", "generate", workspace_id, "--title", "第一章"])
    assert created.exit_code == 0, created.output
    draft_id = created.output.split()[1]

    client = _CaptureClient(reply="修订稿内容")
    monkeypatch.setattr(
        "novel_editorial.cli.draft.build_client", lambda settings: client
    )
    revised = runner.invoke(
        app,
        [
            "draft",
            "revise",
            draft_id,
            "--reason",
            "换人改",
            "--writer",
            "写手乙",
        ],
    )
    assert revised.exit_code == 0, revised.output
    prompt = client.calls[0][0].content
    assert "写手乙的私记" in prompt
    assert "默认写手的私记" not in prompt
    with db.workspace_session(workspace_id) as session:
        draft = session.query(Draft).filter_by(id=draft_id).first()
    assert draft is not None
    assert draft.writer_id == second.id


def test_create_author_draft_is_empty_and_events(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    draft = create_author_draft(db, workspace_id, title="作者新章")
    assert draft.writer_id is None
    assert draft.status == "draft"
    assert draft.current_version == 0

    events = list_events(db, workspace_id)
    created = [event for event in events if event.type == "draft.created"]
    assert len(created) == 1
    assert created[0].actor == "作者"
    assert json.loads(created[0].payload) == {
        "draft_id": draft.id,
        "title": "作者新章",
    }

    with db.workspace_session(workspace_id) as session:
        versions = session.query(DraftVersion).filter_by(draft_id=draft.id).all()
    assert versions == []


def test_save_author_version_passes_gate_and_requests_decision(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    draft = create_author_draft(db, workspace_id, title="第一章")
    updated, version = save_author_version(
        db, workspace_id, draft.id, content="雨夜，她推开旧车站的门。"
    )
    assert updated.status == "draft"
    assert updated.current_version == 1
    assert version.version == 1
    assert version.content == "雨夜，她推开旧车站的门。"
    assert version.reason == "作者修改"
    assert version.actor == "作者"

    pending = list_pending_drafts(db, workspace_id)
    assert [item.id for item in pending] == [draft.id]

    events = list_events(db, workspace_id)
    passed = [event for event in events if event.type == "quality_gate.passed"]
    requested = [event for event in events if event.type == "decision.requested"]
    assert len(passed) == 1
    assert passed[0].actor == "system"
    assert json.loads(passed[0].payload)["draft_id"] == draft.id
    assert json.loads(passed[0].payload)["version"] == 1
    assert len(requested) == 1
    assert requested[0].actor == "system"
    assert json.loads(requested[0].payload) == {
        "draft_id": draft.id,
        "version": 1,
    }


def test_save_author_version_rejects_blank_content(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    draft = create_author_draft(db, workspace_id, title="空稿")
    with pytest.raises(NovelError) as excinfo:
        save_author_version(db, workspace_id, draft.id, content="   ")
    assert excinfo.value.code is ErrorCode.USAGE_ERROR
    assert "draft content must not be empty" in excinfo.value.message
    with db.workspace_session(workspace_id) as session:
        row = session.get(Draft, draft.id)
        assert row is not None
        assert row.current_version == 0


def test_save_author_version_quality_failure_is_rejected(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    draft = create_author_draft(db, workspace_id, title="第一章")
    updated, _ = save_author_version(
        db,
        workspace_id,
        draft.id,
        content="宛如璀璨的瞬间，她静静轻轻淡淡微微缓缓地叹息",
        quality_threshold=-1,
    )
    assert updated.status == "quality_failed"
    events = list_events(db, workspace_id)
    assert all(event.type != "quality_gate.passed" for event in events)
    assert all(event.type != "decision.requested" for event in events)


def test_save_author_version_rejects_accepted_draft(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    with db.workspace_session(workspace_id) as session:
        accepted = Draft(
            workspace_id=workspace_id,
            title="已过",
            status="accepted",
            current_version=1,
        )
        session.add(accepted)
        session.commit()
        accepted_id = accepted.id
    with pytest.raises(NovelError) as excinfo:
        save_author_version(db, workspace_id, accepted_id, content="正文")
    assert excinfo.value.code is ErrorCode.USAGE_ERROR
    assert "cannot revise an accepted draft" in excinfo.value.message


def test_draft_new_and_save_cli(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    created = runner.invoke(
        app, ["draft", "new", workspace_id, "--title", "作者章"]
    )
    assert created.exit_code == 0, created.output
    assert "now at v0" in created.output
    assert "awaiting decision" in created.output
    draft_id = created.output.split()[1]

    saved = runner.invoke(
        app,
        ["draft", "save", draft_id, "--content", "作者亲笔正文", "--reason", "初稿"],
    )
    assert saved.exit_code == 0, saved.output
    assert "now at v1" in saved.output
    assert "awaiting decision" in saved.output

    db = DB(load_settings())
    with db.workspace_session(workspace_id) as session:
        version = (
            session.query(DraftVersion).filter_by(draft_id=draft_id).first()
        )
        draft = session.get(Draft, draft_id)
    assert draft is not None
    assert draft.writer_id is None
    assert version is not None
    assert version.actor == "作者"
    assert version.reason == "初稿"


def test_draft_v0_empty_state_show_and_usage_errors(
    tmp_path: Path, monkeypatch
) -> None:
    """A freshly created author draft (v0, no version rows) must stay readable."""
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    created = runner.invoke(
        app, ["draft", "new", workspace_id, "--title", "作者章"]
    )
    assert created.exit_code == 0, created.output
    draft_id = created.output.split()[1]

    shown = runner.invoke(app, ["draft", "show", draft_id])
    assert shown.exit_code == 0, shown.output
    assert "作者章 (v0, draft)" in shown.output
    assert "暂无内容" in shown.output

    diff = runner.invoke(app, ["draft", "diff", draft_id, "1", "1"])
    assert diff.exit_code == 2
    assert "cannot diff a draft with no versions" in diff.output

    monkeypatch.setattr(
        "novel_editorial.cli.draft.build_client",
        lambda settings: MockLLMClient(reply="不该被调用"),
    )
    revised = runner.invoke(app, ["draft", "revise", draft_id, "--reason", "改"])
    assert revised.exit_code == 2
    assert "cannot revise a draft with no content" in revised.output

    saved = runner.invoke(
        app,
        ["draft", "save", draft_id, "--content", "作者亲笔正文"],
    )
    assert saved.exit_code == 0, saved.output
    assert "now at v1" in saved.output
    shown = runner.invoke(app, ["draft", "show", draft_id])
    assert shown.exit_code == 0, shown.output
    assert "作者章 (v1, draft)" in shown.output
    assert "作者亲笔正文" in shown.output


def test_draft_author_draft_shows_author_as_writer(
    tmp_path: Path, monkeypatch
) -> None:
    """Author drafts (writer_id=None) render as 作者, not the default writer."""
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    created = runner.invoke(
        app, ["draft", "new", workspace_id, "--title", "作者章"]
    )
    assert created.exit_code == 0, created.output
    draft_id = created.output.split()[1]

    listing = runner.invoke(app, ["draft", "list", workspace_id])
    assert listing.exit_code == 0, listing.output
    assert "（作者）" in listing.output
    assert "（写手）" not in listing.output

    shown = runner.invoke(app, ["draft", "show", draft_id])
    assert shown.exit_code == 0, shown.output
    assert "writer: 作者" in shown.output


def test_draft_save_cli_rejects_blank_content(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    created = runner.invoke(
        app, ["draft", "new", workspace_id, "--title", "空稿"]
    )
    assert created.exit_code == 0, created.output
    draft_id = created.output.split()[1]

    result = runner.invoke(
        app, ["draft", "save", draft_id, "--content", "   "]
    )
    assert result.exit_code == 2
    assert "draft content must not be empty" in result.output


def test_draft_version_migration_backfills_writer_name(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    db = DB(settings)
    default_writer = get_default_writer(db, workspace_id)
    with db.workspace_session(workspace_id) as session:
        owned = Draft(
            workspace_id=workspace_id,
            title="有主",
            writer_id=default_writer.id,
        )
        session.add(owned)
        session.flush()
        session.add(DraftVersion(draft_id=owned.id, version=1, content="旧正文"))
        orphan = Draft(workspace_id=workspace_id, title="无主")
        session.add(orphan)
        session.flush()
        session.add(DraftVersion(draft_id=orphan.id, version=1, content="孤儿正文"))
        session.commit()
        owned_id, orphan_id = owned.id, orphan.id

    path = workspace_db_path(settings, workspace_id)
    for _ in range(2):
        connection = sqlite3.connect(path)
        connection.execute("ALTER TABLE draft_versions DROP COLUMN actor")
        connection.execute("DELETE FROM alembic_version")
        connection.execute(
            "INSERT INTO alembic_version (version_num) VALUES ('0b7aeb265bb2')"
        )
        connection.commit()
        connection.close()

        upgraded = DB(settings)
        with upgraded.workspace_session(workspace_id) as session:
            owned_version = (
                session.query(DraftVersion).filter_by(draft_id=owned_id).first()
            )
            orphan_version = (
                session.query(DraftVersion).filter_by(draft_id=orphan_id).first()
            )
        assert owned_version is not None
        assert owned_version.actor == default_writer.name
        assert orphan_version is not None
        assert orphan_version.actor == ""

    # Re-running the migration with the column in place must not clobber
    # author-written versions (actor = "作者").
    with upgraded.workspace_session(workspace_id) as session:
        author_draft = Draft(workspace_id=workspace_id, title="作者稿")
        session.add(author_draft)
        session.flush()
        session.add(
            DraftVersion(
                draft_id=author_draft.id,
                version=1,
                content="作者正文",
                actor="作者",
            )
        )
        session.commit()
        author_draft_id = author_draft.id
    connection = sqlite3.connect(path)
    connection.execute("DELETE FROM alembic_version")
    connection.execute(
        "INSERT INTO alembic_version (version_num) VALUES ('0b7aeb265bb2')"
    )
    connection.commit()
    connection.close()
    replayed = DB(settings)
    with replayed.workspace_session(workspace_id) as session:
        author_version = (
            session.query(DraftVersion).filter_by(draft_id=author_draft_id).first()
        )
    assert author_version is not None
    assert author_version.actor == "作者"
