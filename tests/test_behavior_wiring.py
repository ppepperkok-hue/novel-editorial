"""Behavior wiring: post-hoc traces for refusal/override, reviews, and decisions."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.behavior import list_behavior_timeline, record_behavior_entry_safe
from novel_editorial.core.chat import get_agent, list_messages
from novel_editorial.core.config import load_settings
from novel_editorial.core.review import add_review, list_reviews
from novel_editorial.llm.client import MockLLMClient
from novel_editorial.store.db import DB
from novel_editorial.store.models import AgentRole, BehaviorTimeline, Draft

runner = CliRunner()


def _create_workspace(tmp_path: Path, monkeypatch) -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["works", "create", "接线之书", "--genre", "悬疑"])
    assert result.exit_code == 0, result.output
    match = re.search(r"created workspace (\w+):", result.output)
    assert match is not None
    return match.group(1)


def _generate_draft(workspace_id: str, monkeypatch, title: str = "第一章") -> str:
    monkeypatch.setattr(
        "novel_editorial.cli.draft.build_client",
        lambda settings: MockLLMClient(reply="初稿内容"),
    )
    result = runner.invoke(app, ["draft", "generate", workspace_id, "--title", title])
    assert result.exit_code == 0, result.output
    return result.output.split()[1]


def _behavior_rows(workspace_id: str) -> list[BehaviorTimeline]:
    return list_behavior_timeline(DB(load_settings()), workspace_id)


def _writer_id(workspace_id: str) -> str:
    return get_agent(DB(load_settings()), workspace_id, AgentRole.WRITER).id


def test_talk_refusal_then_override_traces_viewpoints_and_relationship(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    refused = runner.invoke(app, ["talk", "send", workspace_id, "@写手 这段按违背人设写"])
    reaffirmed = runner.invoke(
        app, ["talk", "send", workspace_id, "@写手 这段还是按违背人设写"]
    )
    overridden = runner.invoke(
        app,
        ["talk", "send", workspace_id, "@写手 以老板身份我拍板，就按违背人设写"],
    )
    for result in (refused, reaffirmed, overridden):
        assert result.exit_code == 0, result.output

    writer_id = _writer_id(workspace_id)
    rows = _behavior_rows(workspace_id)
    assert len(rows) == 3

    refusal = rows[0]
    assert refusal.kind == "viewpoint"
    assert refusal.agent_id == writer_id
    assert refusal.target == "writer_portrayal"
    assert refusal.summary == "拒绝了违背立场的指令"
    assert refusal.before_value is None
    assert refusal.after_value == "坚持该立场"
    assert refusal.source == "refusal:writer_portrayal"

    override_viewpoint = rows[1]
    assert override_viewpoint.kind == "viewpoint"
    assert override_viewpoint.agent_id == writer_id
    assert override_viewpoint.target == "writer_portrayal"
    assert override_viewpoint.summary == "作者推翻后调整"
    assert override_viewpoint.before_value == "坚持该立场"
    assert override_viewpoint.after_value == "按作者决定执行"
    assert override_viewpoint.source == "override:writer_portrayal"

    override_relationship = rows[2]
    assert override_relationship.kind == "relationship"
    assert override_relationship.agent_id == writer_id
    assert override_relationship.target == "作者"
    assert override_relationship.summary == "作者拍板优先"
    assert override_relationship.source == "override:writer_portrayal"


@pytest.mark.parametrize(
    ("alias", "content", "impression", "relationship"),
    [
        ("责编", "退稿：开头钩子不成立", "盯节奏与钩子", "被退过稿"),
        ("审稿", "伏笔没有咬合，需要补一条回收", "盯逻辑与一致性", "被指出问题"),
        ("总编", "主线偏了，结构要收一收", "盯整体结构与基调", "被指出问题"),
    ],
)
def test_review_add_from_agent_traces_writer_impression_and_relationship(
    tmp_path: Path,
    monkeypatch,
    alias: str,
    content: str,
    impression: str,
    relationship: str,
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    draft_id = _generate_draft(workspace_id, monkeypatch)
    result = runner.invoke(
        app, ["review", "add", draft_id, "--from", alias, "--content", content]
    )
    assert result.exit_code == 0, result.output

    writer_id = _writer_id(workspace_id)
    rows = _behavior_rows(workspace_id)
    assert len(rows) == 2
    impression_row = next(row for row in rows if row.kind == "impression")
    relationship_row = next(row for row in rows if row.kind == "relationship")
    assert impression_row.agent_id == writer_id
    assert impression_row.target == alias
    assert impression_row.summary == impression
    assert impression_row.source == "review:add"
    assert relationship_row.agent_id == writer_id
    assert relationship_row.target == alias
    assert relationship_row.summary == relationship
    assert relationship_row.source == "review:add"


def test_review_add_from_author_or_writer_traces_nothing(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    draft_id = _generate_draft(workspace_id, monkeypatch)
    author = runner.invoke(
        app, ["review", "add", draft_id, "--from", "作者", "--content", "节奏太慢"]
    )
    self_review = runner.invoke(
        app, ["review", "add", draft_id, "--from", "写手", "--content", "我自评：再收一收"]
    )
    assert author.exit_code == 0, author.output
    assert self_review.exit_code == 0, self_review.output
    assert _behavior_rows(workspace_id) == []


def test_review_add_unknown_agent_actor_uses_generic_impression(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    draft_id = _generate_draft(workspace_id, monkeypatch)
    db = DB(load_settings())
    add_review(db, workspace_id, draft_id, role="agent", actor="特邀编辑", content="文风不对")

    writer_id = _writer_id(workspace_id)
    rows = _behavior_rows(workspace_id)
    assert len(rows) == 2
    impression = next(row for row in rows if row.kind == "impression")
    relationship = next(row for row in rows if row.kind == "relationship")
    assert impression.agent_id == writer_id
    assert impression.target == "特邀编辑"
    assert impression.summary == "给过修改意见"
    assert impression.source == "review:add"
    assert relationship.agent_id == writer_id
    assert relationship.target == "特邀编辑"
    assert relationship.summary == "被指出问题"
    assert relationship.source == "review:add"


def test_decision_accept_and_reject_trace_impression_and_relationship(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    accepted_draft = _generate_draft(workspace_id, monkeypatch)
    rejected_draft = _generate_draft(workspace_id, monkeypatch, title="第二章")
    accepted = runner.invoke(app, ["decision", "accept", accepted_draft])
    rejected = runner.invoke(app, ["decision", "reject", rejected_draft])
    assert accepted.exit_code == 0, accepted.output
    assert rejected.exit_code == 0, rejected.output

    writer_id = _writer_id(workspace_id)
    rows = _behavior_rows(workspace_id)
    assert len(rows) == 4
    by_key = {(row.kind, row.source): row for row in rows}
    assert set(by_key) == {
        ("impression", "decision:accept"),
        ("relationship", "decision:accept"),
        ("impression", "decision:reject"),
        ("relationship", "decision:reject"),
    }
    assert by_key[("impression", "decision:accept")].summary == "认可我的产出"
    assert by_key[("relationship", "decision:accept")].summary == "稿子被认可"
    assert by_key[("impression", "decision:reject")].summary == "对我的要求高"
    assert by_key[("relationship", "decision:reject")].summary == "稿子被退回"
    for row in rows:
        assert row.agent_id == writer_id
        assert row.target == "作者"


def test_decision_note_traces_nothing(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    draft_id = _generate_draft(workspace_id, monkeypatch)
    result = runner.invoke(
        app, ["decision", "note", draft_id, "--content", "先把第三章大纲补上"]
    )
    assert result.exit_code == 0, result.output
    assert _behavior_rows(workspace_id) == []


def test_record_behavior_entry_safe_returns_true_and_persists(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    result = record_behavior_entry_safe(
        db,
        workspace_id,
        agent_id="写手",
        kind="viewpoint",
        target="rule_a",
        summary="坚持该立场",
        after_value="坚持",
        source="refusal:rule_a",
    )
    assert result is True
    rows = list_behavior_timeline(db, workspace_id)
    assert len(rows) == 1
    assert rows[0].summary == "坚持该立场"


def test_record_behavior_entry_safe_warns_and_returns_false_on_failure(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("novel_editorial.core.behavior.record_behavior_entry", boom)
    result = record_behavior_entry_safe(
        DB(load_settings()),
        workspace_id,
        agent_id="写手",
        kind="viewpoint",
        target="rule_a",
    )
    assert result is False
    assert "warning: behavior trace skipped: boom" in capsys.readouterr().err
    assert _behavior_rows(workspace_id) == []


def test_talk_business_survives_behavior_trace_failure(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("novel_editorial.core.behavior.record_behavior_entry", boom)
    result = runner.invoke(app, ["talk", "send", workspace_id, "@写手 这段按违背人设写"])
    assert result.exit_code == 0, result.output
    assert "这个我写不了" in result.output
    assert "warning: behavior trace skipped: boom" in result.output

    messages = list_messages(DB(load_settings()), workspace_id)
    assert len(messages) == 3
    assert messages[0].role == "author"
    assert '"kind": "refusal"' in messages[1].payload
    assert _behavior_rows(workspace_id) == []


def test_review_business_survives_behavior_trace_failure(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    draft_id = _generate_draft(workspace_id, monkeypatch)

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("novel_editorial.core.behavior.record_behavior_entry", boom)
    result = runner.invoke(
        app, ["review", "add", draft_id, "--from", "责编", "--content", "退稿：钩子不成立"]
    )
    assert result.exit_code == 0, result.output
    assert "warning: behavior trace skipped: boom" in result.output
    reviews = list_reviews(DB(load_settings()), workspace_id, draft_id)
    assert len(reviews) == 1
    assert reviews[0].role == "agent"
    assert reviews[0].actor == "责编"
    assert _behavior_rows(workspace_id) == []


def test_decision_business_survives_behavior_trace_failure(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    draft_id = _generate_draft(workspace_id, monkeypatch)

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("novel_editorial.core.behavior.record_behavior_entry", boom)
    result = runner.invoke(app, ["decision", "accept", draft_id])
    assert result.exit_code == 0, result.output
    assert f"draft {draft_id} accepted" in result.output
    assert "warning: behavior trace skipped: boom" in result.output

    db = DB(load_settings())
    with db.workspace_session(workspace_id) as session:
        draft = session.query(Draft).filter_by(id=draft_id).first()
        assert draft is not None
        assert draft.status == "accepted"
    assert _behavior_rows(workspace_id) == []
