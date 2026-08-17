import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.chat import list_messages
from novel_editorial.core.config import load_settings
from novel_editorial.core.review import list_reviews
from novel_editorial.llm.client import MockLLMClient
from novel_editorial.store.db import DB
from novel_editorial.store.models import Decision, Draft, DraftVersion

runner = CliRunner()


class _CapturingLLMClient(MockLLMClient):
    def __init__(self, reply: str = "修订稿内容") -> None:
        super().__init__(reply)
        self.last_prompt = ""

    def complete(self, messages):
        self.last_prompt = messages[-1].content
        return super().complete(messages)


def _create_workspace(tmp_path: Path, monkeypatch) -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["works", "create", "评审之书", "--genre", "悬疑"])
    assert result.exit_code == 0, result.output
    return result.output.split()[2].rstrip(":")


def _generate_draft(workspace_id: str, monkeypatch) -> str:
    monkeypatch.setattr(
        "novel_editorial.cli.draft.build_client",
        lambda settings: MockLLMClient(reply="初稿内容"),
    )
    result = runner.invoke(app, ["draft", "generate", workspace_id, "--title", "第一章"])
    assert result.exit_code == 0, result.output
    return result.output.split()[1]


def _draft_status(workspace_id: str, draft_id: str) -> str:
    settings = load_settings()
    db = DB(settings)
    with db.workspace_session(workspace_id) as session:
        draft = session.query(Draft).filter_by(id=draft_id).first()
        assert draft is not None
        return draft.status


@pytest.mark.smoke
def test_review_add_from_author_and_editor(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    draft_id = _generate_draft(workspace_id, monkeypatch)

    author_review = runner.invoke(
        app,
        ["review", "add", draft_id, "--from", "作者", "--content", "节奏太慢"],
    )
    assert author_review.exit_code == 0, author_review.output

    editor_review = runner.invoke(
        app,
        ["review", "add", draft_id, "--from", "责编", "--content", "退稿：开头钩子不成立"],
    )
    assert editor_review.exit_code == 0, editor_review.output

    settings = load_settings()
    reviews = list_reviews(DB(settings), workspace_id, draft_id)
    assert len(reviews) == 2
    assert reviews[0].role == "author" and reviews[0].actor == "作者"
    assert reviews[1].role == "agent" and reviews[1].actor == "责编"
    assert "退稿" in reviews[1].content


def test_review_unknown_alias(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    draft_id = _generate_draft(workspace_id, monkeypatch)
    result = runner.invoke(
        app,
        ["review", "add", draft_id, "--from", "路人甲", "--content", "意见"],
    )
    assert result.exit_code == 2
    assert "unknown reviewer alias" in result.output


@pytest.mark.smoke
def test_revise_after_rejection_with_reason(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    draft_id = _generate_draft(workspace_id, monkeypatch)

    rejected = runner.invoke(app, ["decision", "reject", draft_id])
    assert rejected.exit_code == 0, rejected.output
    assert _draft_status(workspace_id, draft_id) == "rejected"

    monkeypatch.setattr(
        "novel_editorial.cli.draft.build_client",
        lambda settings: MockLLMClient(reply="修订稿内容"),
    )
    revised = runner.invoke(
        app,
        ["draft", "revise", draft_id, "--reason", "写手反驳：钩子成立，修改铺垫后重交"],
    )
    assert revised.exit_code == 0, revised.output
    assert "v2" in revised.output
    assert _draft_status(workspace_id, draft_id) == "draft"

    settings = load_settings()
    db = DB(settings)
    with db.workspace_session(workspace_id) as session:
        version = (
            session.query(DraftVersion)
            .filter_by(draft_id=draft_id, version=2)
            .first()
        )
        assert version is not None
        assert "写手反驳" in version.reason


def test_revise_feeds_feedback_and_previous_content_to_llm(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    draft_id = _generate_draft(workspace_id, monkeypatch)
    runner.invoke(
        app,
        ["review", "add", draft_id, "--from", "责编", "--content", "退稿：开头钩子不成立"],
    )

    capturing = _CapturingLLMClient()
    monkeypatch.setattr(
        "novel_editorial.cli.draft.build_client",
        lambda settings: capturing,
    )
    result = runner.invoke(app, ["draft", "revise", draft_id, "--reason", "针对钩子重写铺垫"])
    assert result.exit_code == 0, result.output

    assert "初稿内容" in capturing.last_prompt
    assert "退稿：开头钩子不成立" in capturing.last_prompt
    assert "针对钩子重写铺垫" in capturing.last_prompt
    assert "不要从头重写" in capturing.last_prompt


def test_revise_generates_writer_rebuttal_message(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    draft_id = _generate_draft(workspace_id, monkeypatch)
    runner.invoke(
        app,
        ["review", "add", draft_id, "--from", "责编", "--content", "退稿：节奏太慢"],
    )
    monkeypatch.setattr(
        "novel_editorial.cli.draft.build_client",
        lambda settings: MockLLMClient(reply="修订稿内容"),
    )
    result = runner.invoke(app, ["draft", "revise", draft_id, "--reason", "重写铺垫"])
    assert result.exit_code == 0, result.output

    settings = load_settings()
    messages = list_messages(DB(settings), workspace_id)
    rebuttals = [
        m for m in messages if json.loads(m.payload).get("kind") == "rebuttal"
    ]
    assert len(rebuttals) == 1
    assert rebuttals[0].actor == "写手"
    assert "写手反驳" in rebuttals[0].content
    assert json.loads(rebuttals[0].payload) == {
        "initiator": "agent",
        "kind": "rebuttal",
        "targets": ["责编"],
    }


def test_revise_rebuttal_targets_follow_agent_review_order_and_dedupe(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    draft_id = _generate_draft(workspace_id, monkeypatch)
    runner.invoke(
        app,
        ["review", "add", draft_id, "--from", "责编", "--content", "退稿：钩子不成立"],
    )
    runner.invoke(
        app,
        ["review", "add", draft_id, "--from", "作者", "--content", "我也觉得节奏慢"],
    )
    runner.invoke(
        app,
        ["review", "add", draft_id, "--from", "审稿", "--content", "伏笔没咬合"],
    )
    runner.invoke(
        app,
        ["review", "add", draft_id, "--from", "责编", "--content", "开头太长"],
    )
    monkeypatch.setattr(
        "novel_editorial.cli.draft.build_client",
        lambda settings: MockLLMClient(reply="修订稿内容"),
    )
    result = runner.invoke(app, ["draft", "revise", draft_id, "--reason", "重写铺垫"])
    assert result.exit_code == 0, result.output

    rebuttals = [
        message
        for message in list_messages(DB(load_settings()), workspace_id)
        if json.loads(message.payload).get("kind") == "rebuttal"
    ]
    assert len(rebuttals) == 1
    assert json.loads(rebuttals[0].payload) == {
        "initiator": "agent",
        "kind": "rebuttal",
        "targets": ["责编", "审稿"],
    }


def test_revise_without_agent_review_emits_no_rebuttal(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    draft_id = _generate_draft(workspace_id, monkeypatch)
    runner.invoke(
        app,
        ["review", "add", draft_id, "--from", "作者", "--content", "节奏太慢"],
    )
    monkeypatch.setattr(
        "novel_editorial.cli.draft.build_client",
        lambda settings: MockLLMClient(reply="修订稿内容"),
    )
    result = runner.invoke(app, ["draft", "revise", draft_id, "--reason", "重写铺垫"])
    assert result.exit_code == 0, result.output

    messages = list_messages(DB(load_settings()), workspace_id)
    assert not any(json.loads(m.payload).get("kind") == "rebuttal" for m in messages)


def test_review_list_and_decision_list(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    draft_id = _generate_draft(workspace_id, monkeypatch)
    runner.invoke(
        app,
        ["review", "add", draft_id, "--from", "作者", "--content", "节奏太慢"],
    )
    runner.invoke(app, ["decision", "accept", draft_id])

    review_list = runner.invoke(app, ["review", "list", draft_id])
    assert review_list.exit_code == 0, review_list.output
    assert "[author] 作者: 节奏太慢" in review_list.output

    decision_list = runner.invoke(app, ["decision", "list", draft_id])
    assert decision_list.exit_code == 0, decision_list.output
    assert "[accept] 作者" in decision_list.output


@pytest.mark.smoke
def test_draft_show_prints_reason(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    draft_id = _generate_draft(workspace_id, monkeypatch)

    shown = runner.invoke(app, ["draft", "show", draft_id])
    assert shown.exit_code == 0
    assert "reason: initial" in shown.output


def test_decision_accept_and_guard(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    draft_id = _generate_draft(workspace_id, monkeypatch)

    accepted = runner.invoke(app, ["decision", "accept", draft_id])
    assert accepted.exit_code == 0, accepted.output
    assert _draft_status(workspace_id, draft_id) == "accepted"

    again = runner.invoke(app, ["decision", "accept", draft_id])
    assert again.exit_code == 2
    assert "already accepted" in again.output

    revise = runner.invoke(app, ["draft", "revise", draft_id])
    assert revise.exit_code == 2
    assert "cannot revise an accepted draft" in revise.output


def test_decision_note_records(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    draft_id = _generate_draft(workspace_id, monkeypatch)

    noted = runner.invoke(
        app,
        ["decision", "note", draft_id, "--content", "先把第三章大纲补上"],
    )
    assert noted.exit_code == 0, noted.output
    assert _draft_status(workspace_id, draft_id) == "draft"

    settings = load_settings()
    db = DB(settings)
    with db.workspace_session(workspace_id) as session:
        decision = session.query(Decision).filter_by(draft_id=draft_id, action="note").first()
        assert decision is not None
        assert decision.content == "先把第三章大纲补上"
