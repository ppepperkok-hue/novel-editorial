import json
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.cli.talk import (
    _collaboration_mark,
    _disagreement_mark,
    _proactive_kind,
)
from novel_editorial.core import proactive
from novel_editorial.core.behavior import list_behavior_timeline
from novel_editorial.core.chat import (
    get_agent,
    has_proactive_message,
    list_messages,
    record_message,
)
from novel_editorial.core.config import load_settings
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.core.motives import list_motives, upsert_motive_feedback
from novel_editorial.llm.client import LLMClient, LLMMessage, LLMResult, MockLLMClient
from novel_editorial.store.db import DB, workspace_db_path
from novel_editorial.store.models import AgentMotive, AgentRole

runner = CliRunner()


def _create_workspace(tmp_path: Path, monkeypatch) -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["works", "create", "对话之书", "--genre", "悬疑"])
    assert result.exit_code == 0, result.output
    return result.output.split()[2].rstrip(":")


@pytest.mark.smoke
def test_talk_send_records_author_reply_and_proactive(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(app, ["talk", "send", workspace_id, "我们写一个侦探故事"])
    assert result.exit_code == 0, result.output
    assert f"{'作者'}: 我们写一个侦探故事" in result.output
    assert "总编: （模拟回复）" in result.output
    assert "责编: 我想先确认一下" in result.output
    assert "总编: 这部作品的方向还没定" in result.output

    settings = load_settings()
    db = DB(settings)
    messages = list_messages(db, workspace_id)
    assert len(messages) == 5
    assert messages[0].role == "author"
    assert messages[1].role == "agent" and messages[1].actor == "总编"
    mood_payload = json.loads(messages[2].payload)
    assert mood_payload["kind"] == "mood_change"
    proactive_payload = json.loads(messages[3].payload)
    assert proactive_payload["initiator"] == "agent"
    direction_payload = json.loads(messages[4].payload)
    assert direction_payload == {
        "initiator": "agent",
        "kind": proactive.PROACTIVE_KIND_DIRECTION,
        "trigger": proactive.TRIGGER_TALK_FIRST_ROUND,
    }
    assert messages[4].actor == "总编"
    assert messages[4].content == (
        "这部作品的方向还没定：整体基调、核心冲突，咱们先把这些捋清楚再动笔。"
    )
    assert has_proactive_message(db, workspace_id)


@pytest.mark.smoke
def test_talk_send_routes_at_mention(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(app, ["talk", "send", workspace_id, "@写手 写一段开场"])
    assert result.exit_code == 0, result.output
    assert "写手: （模拟回复）" in result.output


def test_talk_send_routes_at_mention_with_cjk_punctuation(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(app, ["talk", "send", workspace_id, "@写手，写一段雨夜开场"])
    assert result.exit_code == 0, result.output
    assert "写手: （模拟回复）" in result.output


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (None, None),
        ("{}", None),
        ("not json", None),
        ("[]", None),
        ('{"initiator": "author", "kind": "proactive_report"}', None),
        ('{"initiator": "agent", "kind": "refusal"}', None),
        ('{"initiator": "agent", "kind": "rebuttal"}', None),
        ('{"initiator": "agent", "kind": "mood_change"}', None),
        ('{"initiator": "agent", "kind": ["proactive_question"]}', None),
        ('{"initiator": "agent", "kind": {"name": "proactive_question"}}', None),
        ('{"initiator": "agent", "kind": "proactive_question"}', "proactive_question"),
        (
            '{"initiator": "agent", "kind": "proactive_direction", "trigger": "talk_first_round"}',
            "proactive_direction",
        ),
    ],
)
def test_proactive_kind_classification(payload: str | None, expected: str | None) -> None:
    assert _proactive_kind(payload) == expected


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (None, None),
        ("{}", None),
        ("not json", None),
        ("[]", None),
        ('{"initiator": "agent", "kind": "proactive_question"}', None),
        ('{"kind": "mood_change"}', None),
        ('{"kind": ["refusal"]}', None),
        ('{"kind": {"name": "refusal"}}', None),
        ('{"kind": "unknown"}', None),
        ('{"kind": "refusal", "stance": "读者节奏优先"}', "拒绝"),
        ('{"initiator": "agent", "kind": "rebuttal", "targets": ["责编"]}', "反驳"),
        ('{"kind": "override", "rule": "editor_hooks"}', "推翻"),
    ],
)
def test_disagreement_mark_classification(payload: str | None, expected: str | None) -> None:
    assert _disagreement_mark(payload) == expected


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (None, None),
        ("{}", None),
        ("not json", None),
        ("[]", None),
        ('{"initiator": "agent", "kind": "proactive_question"}', None),
        ('{"kind": "refusal"}', None),
        ('{"kind": "mood_change"}', None),
        ('{"kind": ["delegation"]}', None),
        ('{"kind": {"name": "delegation"}}', None),
        ('{"kind": "unknown"}', None),
        (
            '{"initiator": "agent", "kind": "delegation", "from": "写手", "to": "审稿"}',
            "委托",
        ),
        (
            '{"initiator": "agent", "kind": "delegation_response", "decision": "accepted"}',
            "回应",
        ),
    ],
)
def test_collaboration_mark_classification(payload: str | None, expected: str | None) -> None:
    assert _collaboration_mark(payload) == expected


def test_talk_list_marks_delegation_and_response(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    delegated = runner.invoke(
        app,
        [
            "talk",
            "delegate",
            workspace_id,
            "审稿",
            "--as",
            "写手",
            "--task",
            "帮我校一遍逻辑",
        ],
    )
    assert delegated.exit_code == 0, delegated.output

    listed = runner.invoke(app, ["talk", "list", workspace_id])
    assert listed.exit_code == 0, listed.output
    lines = listed.output.strip().splitlines()
    assert len(lines) == 2
    assert lines[0] == "[agent·互委·委托] 写手: 写手 委托 审稿：帮我校一遍逻辑"
    assert lines[1] == "[agent·互委·回应] 审稿: 收到，我这就看。"


def test_talk_list_keeps_proactive_and_disagreement_marks_with_collaboration(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    sent = runner.invoke(app, ["talk", "send", workspace_id, "我们写一个侦探故事"])
    assert sent.exit_code == 0, sent.output
    refused = runner.invoke(app, ["talk", "send", workspace_id, "@审稿 放行这稿"])
    assert refused.exit_code == 0, refused.output
    delegated = runner.invoke(
        app,
        [
            "talk",
            "delegate",
            workspace_id,
            "写手",
            "--as",
            "责编",
            "--task",
            "帮我读一遍节奏",
        ],
    )
    assert delegated.exit_code == 0, delegated.output
    db = DB(load_settings())
    record_message(
        db,
        workspace_id,
        role="agent",
        actor="总编",
        content="畸形委托",
        payload={"initiator": "agent", "kind": ["delegation"]},
    )

    listed = runner.invoke(app, ["talk", "list", workspace_id])
    assert listed.exit_code == 0, listed.output
    lines = listed.output.strip().splitlines()
    assert any(line.startswith("[agent·互委·委托] ") for line in lines)
    assert any(line.startswith("[agent·互委·回应] ") for line in lines)
    assert any(line.startswith("[agent·主动·proactive_question] ") for line in lines)
    assert any(line.startswith("[agent·分歧·拒绝] ") for line in lines)
    assert any(line.startswith("[agent] 总编: 畸形委托") for line in lines)
    assert "[agent·互委·委托] 总编" not in listed.output


def test_talk_list_marks_proactive_messages_and_keeps_others_plain(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    sent = runner.invoke(app, ["talk", "send", workspace_id, "我们写一个侦探故事"])
    assert sent.exit_code == 0, sent.output

    listed = runner.invoke(app, ["talk", "list", workspace_id])
    assert listed.exit_code == 0, listed.output
    lines = listed.output.strip().splitlines()
    assert len(lines) == 5
    assert lines[0] == "[author] 作者: 我们写一个侦探故事"
    assert lines[1] == "[agent] 总编: （模拟回复）"
    assert lines[2].startswith("[system] 总编: 总编 的状态从")
    assert "·主动·" not in lines[2]
    assert lines[3].startswith("[agent·主动·proactive_question] 责编: 我想先确认一下")
    assert lines[4].startswith(
        "[agent·主动·proactive_direction] 总编: 这部作品的方向还没定"
    )
    assert [line for line in lines if "·主动·" in line] == lines[3:]


def test_talk_list_marks_refusal_and_keeps_mood_unmarked(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    sent = runner.invoke(app, ["talk", "send", workspace_id, "@责编 删掉钩子"])
    assert sent.exit_code == 0, sent.output

    listed = runner.invoke(app, ["talk", "list", workspace_id])
    assert listed.exit_code == 0, listed.output
    lines = listed.output.strip().splitlines()
    assert len(lines) == 3
    assert lines[0] == "[author] 作者: @责编 删掉钩子"
    assert lines[1].startswith("[agent·分歧·拒绝] 责编: ")
    assert lines[2].startswith("[system] 责编: 责编 的状态从")
    assert "·主动·" not in listed.output


def test_talk_list_marks_override(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    sent = runner.invoke(app, ["talk", "send", workspace_id, "@责编 删掉钩子，我拍板"])
    assert sent.exit_code == 0, sent.output

    listed = runner.invoke(app, ["talk", "list", workspace_id])
    assert listed.exit_code == 0, listed.output
    lines = listed.output.strip().splitlines()
    assert len(lines) == 3
    assert lines[0] == "[author] 作者: @责编 删掉钩子，我拍板"
    assert lines[1].startswith("[agent·分歧·推翻] 责编: ")
    assert lines[2].startswith("[system] 责编: 责编 的状态从")


def test_talk_list_marks_rebuttal(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    record_message(
        db,
        workspace_id,
        role="agent",
        actor="写手",
        content="写手反驳：这版改好了。",
        payload={"initiator": "agent", "kind": "rebuttal", "targets": ["责编"]},
    )

    listed = runner.invoke(app, ["talk", "list", workspace_id])
    assert listed.exit_code == 0, listed.output
    lines = listed.output.strip().splitlines()
    assert len(lines) == 1
    assert lines[0] == "[agent·分歧·反驳] 写手: 写手反驳：这版改好了。"


def test_talk_list_survives_non_hashable_kind_payload(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    db = DB(settings)
    record_message(
        db,
        workspace_id,
        role="agent",
        actor="总编",
        content="畸形 payload",
        payload={"initiator": "agent", "kind": ["proactive_question"]},
    )

    listed = runner.invoke(app, ["talk", "list", workspace_id])
    assert listed.exit_code == 0, listed.output
    lines = listed.output.strip().splitlines()
    assert len(lines) == 1
    assert lines[0] == "[agent] 总编: 畸形 payload"
    assert "·主动·" not in listed.output


def test_talk_proactive_happens_only_once(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    runner.invoke(app, ["talk", "send", workspace_id, "第一句"])
    runner.invoke(app, ["talk", "send", workspace_id, "第二句"])

    settings = load_settings()
    db = DB(settings)
    messages = list_messages(db, workspace_id)
    proactive = [m for m in messages if json.loads(m.payload).get("initiator") == "agent"]
    assert len(proactive) == 2


def test_talk_send_unknown_alias(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(app, ["talk", "send", workspace_id, "@主编大人 你好"])
    assert result.exit_code == 2
    assert "unknown partner alias" in result.output


def test_talk_send_failure_leaves_no_messages(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    db = DB(settings)

    result = runner.invoke(app, ["talk", "send", workspace_id, "@主编大人 你好"])
    assert result.exit_code == 2
    assert list_messages(db, workspace_id) == []


class _RaisingLLMClient(LLMClient):
    def complete(self, messages: list[LLMMessage]) -> LLMResult:
        raise NovelError(ErrorCode.LLM_ERROR, "boom")


def test_talk_send_llm_failure_leaves_no_messages(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "novel_editorial.cli.talk.build_client",
        lambda settings: _RaisingLLMClient(),
    )
    settings = load_settings()
    db = DB(settings)

    result = runner.invoke(app, ["talk", "send", workspace_id, "正常消息"])
    assert result.exit_code == 1
    assert list_messages(db, workspace_id) == []


def test_talk_upgrades_pre_migration_workspace(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    db = DB(settings)
    path = workspace_db_path(settings, workspace_id)
    connection = sqlite3.connect(path)
    tables = [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT IN ('agents', 'workspaces', 'alembic_version')"
        )
    ]
    for table in tables:
        connection.execute(f"DROP TABLE IF EXISTS {table}")
    for column in (
        "values",
        "aesthetic",
        "emotion_baseline",
        "work_habits",
            "weaknesses",
            "relationship_presets",
            "private_motive",
            "mood",
        ):
        connection.execute(f'ALTER TABLE agents DROP COLUMN "{column}"')
    connection.execute("DELETE FROM alembic_version")
    connection.execute("INSERT INTO alembic_version (version_num) VALUES ('3b05b83f8953')")
    connection.commit()
    connection.close()

    result = runner.invoke(app, ["talk", "send", workspace_id, "升级后能聊"])
    assert result.exit_code == 0, result.output
    assert len(list_messages(db, workspace_id)) == 5

    with db.workspace_session(workspace_id) as session:
        from novel_editorial.store.models import Agent

        writer = session.query(Agent).filter_by(workspace_id=workspace_id, role="writer").first()
        assert writer is not None
        assert writer.values
        assert writer.private_motive
        assert writer.mood == "平静"


def test_proactive_question_survives_rebuttal(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "novel_editorial.cli.draft.build_client",
        lambda settings: MockLLMClient(reply="正文内容"),
    )
    monkeypatch.setattr(
        "novel_editorial.cli.talk.build_client",
        lambda settings: MockLLMClient(reply="正文内容"),
    )
    created = runner.invoke(app, ["draft", "generate", workspace_id, "--title", "第一章"])
    draft_id = created.output.split()[1]
    runner.invoke(
        app,
        ["review", "add", draft_id, "--from", "责编", "--content", "退稿：钩子不成立"],
    )
    runner.invoke(app, ["draft", "revise", draft_id, "--reason", "重写铺垫"])

    result = runner.invoke(app, ["talk", "send", workspace_id, "继续聊这个故事"])
    assert result.exit_code == 0, result.output
    assert "责编: 我想先确认一下" in result.output


def test_talk_proactive_question_fires_after_writer_revise_followup(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    replies = iter(["初稿内容", "修订稿内容"])
    monkeypatch.setattr(
        "novel_editorial.cli.draft.build_client",
        lambda settings: MockLLMClient(reply=next(replies)),
    )
    monkeypatch.setattr(
        "novel_editorial.cli.talk.build_client",
        lambda settings: MockLLMClient(reply="对话回复"),
    )
    created = runner.invoke(app, ["draft", "generate", workspace_id, "--title", "第一章"])
    assert created.exit_code == 0, created.output
    draft_id = created.output.split()[1]

    revised = runner.invoke(app, ["draft", "revise", draft_id, "--reason", "收钩子"])
    assert revised.exit_code == 0, revised.output
    assert "写手: 这章我留了个钩子，下章要不要收？" in revised.output

    sent = runner.invoke(app, ["talk", "send", workspace_id, "继续聊这个故事"])
    assert sent.exit_code == 0, sent.output
    assert "责编: 我想先确认一下" in sent.output


def test_talk_direction_suppressed_when_style_anchor_exists(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    styled = runner.invoke(
        app, ["style", "set", workspace_id, "--description", "平实克制短句"]
    )
    assert styled.exit_code == 0, styled.output

    result = runner.invoke(app, ["talk", "send", workspace_id, "我们写一个侦探故事"])
    assert result.exit_code == 0, result.output
    assert "责编: 我想先确认一下" in result.output
    assert "这部作品的方向还没定" not in result.output

    db = DB(load_settings())
    directions = [
        message
        for message in list_messages(db, workspace_id)
        if json.loads(message.payload).get("kind") == proactive.PROACTIVE_KIND_DIRECTION
    ]
    assert directions == []


def test_disabled_proactive_keeps_question_but_skips_direction(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("NOVEL_PROACTIVE_ENABLED", "false")
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(app, ["talk", "send", workspace_id, "我们写一个侦探故事"])
    assert result.exit_code == 0, result.output
    assert "责编: 我想先确认一下" in result.output
    assert "这部作品的方向还没定" not in result.output

    db = DB(load_settings())
    directions = [
        message
        for message in list_messages(db, workspace_id)
        if json.loads(message.payload).get("kind") == proactive.PROACTIVE_KIND_DIRECTION
    ]
    assert directions == []


def test_talk_praise_strengthens_named_partner_impression(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    writer = get_agent(db, workspace_id, AgentRole.WRITER)

    first = runner.invoke(app, ["talk", "send", workspace_id, "@写手 这段做得好"])
    assert first.exit_code == 0, first.output

    praise = [
        motive
        for motive in list_motives(db, workspace_id)
        if motive.source == "author_feedback:praise"
    ]
    assert len(praise) == 1
    assert praise[0].agent_id == writer.id
    assert praise[0].kind == "impression"
    assert praise[0].content == "被作者表扬了"
    assert praise[0].strength == 100

    with db.workspace_session(workspace_id) as session:
        stored = session.get(AgentMotive, praise[0].id)
        assert stored is not None
        stored.strength = 60
        session.commit()

    second = runner.invoke(app, ["talk", "send", workspace_id, "@写手 干得漂亮"])
    assert second.exit_code == 0, second.output

    remaining = [
        motive
        for motive in list_motives(db, workspace_id)
        if motive.source == "author_feedback:praise"
    ]
    assert len(remaining) == 1
    assert remaining[0].strength == 70


def test_talk_criticism_creates_named_partner_pending_issue(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    writer = get_agent(db, workspace_id, AgentRole.WRITER)

    result = runner.invoke(app, ["talk", "send", workspace_id, "@写手 别总这样写"])
    assert result.exit_code == 0, result.output

    criticism = [
        motive
        for motive in list_motives(db, workspace_id)
        if motive.source == "author_feedback:criticism"
    ]
    assert len(criticism) == 1
    assert criticism[0].agent_id == writer.id
    assert criticism[0].kind == "pending_issue"
    assert criticism[0].content == "被作者批评了"


def test_talk_negated_or_softened_phrases_are_not_criticism(
    tmp_path: Path, monkeypatch
) -> None:
    """「不太差」否定句与「不要老惦记」宽慰句不得写成批评动机 (P3 fix).

    The criticism phrases honor the shared negation guard, so
    「这段不太差了」 softens instead of criticizing. The ambiguous 「不要老」
    prefix is reclassified as let-go (作者劝放下), so 「不要老惦记那个伏笔」
    resolves author-related pending issues instead of adding a criticism motive.
    """
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    writer = get_agent(db, workspace_id, AgentRole.WRITER)
    upsert_motive_feedback(
        db,
        workspace_id,
        writer.id,
        kind="pending_issue",
        content="被退稿了，这事还惦记着",
        source="decision:reject",
    )

    softened = runner.invoke(
        app, ["talk", "send", workspace_id, "@写手 这段不太差了"]
    )
    assert softened.exit_code == 0, softened.output
    eased = runner.invoke(
        app, ["talk", "send", workspace_id, "@写手 不要老惦记那个伏笔"]
    )
    assert eased.exit_code == 0, eased.output

    assert [
        motive
        for motive in list_motives(db, workspace_id)
        if motive.source == "author_feedback:criticism"
    ] == []
    traces = [
        row
        for row in list_behavior_timeline(db, workspace_id)
        if row.source == "author_feedback:let_go"
    ]
    assert len(traces) == 1
    assert [motive.source for motive in list_motives(db, workspace_id)] == []


def test_talk_let_go_clears_author_related_pending_issues(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    writer = get_agent(db, workspace_id, AgentRole.WRITER)
    editor = get_agent(db, workspace_id, AgentRole.EDITOR)
    upsert_motive_feedback(
        db,
        workspace_id,
        writer.id,
        kind="pending_issue",
        content="被退稿了，这事还惦记着",
        source="decision:reject",
    )
    upsert_motive_feedback(
        db,
        workspace_id,
        writer.id,
        kind="pending_issue",
        content="被作者批评了",
        source="author_feedback:criticism",
    )
    upsert_motive_feedback(
        db,
        workspace_id,
        editor.id,
        kind="pending_issue",
        content="委托被拒，这事还惦记着",
        source="delegation:refused",
    )
    assert len(list_motives(db, workspace_id)) == 3

    result = runner.invoke(app, ["talk", "send", workspace_id, "那个先放下吧"])
    assert result.exit_code == 0, result.output

    remaining = list_motives(db, workspace_id)
    assert [motive.source for motive in remaining] == ["delegation:refused"]
    traces = [
        row
        for row in list_behavior_timeline(db, workspace_id)
        if row.source == "author_feedback:let_go"
    ]
    assert len(traces) == 2
    assert all(row.kind == "viewpoint" for row in traces)
    assert all(row.agent_id == writer.id for row in traces)


def test_talk_praise_without_mention_touches_no_motive(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)

    result = runner.invoke(app, ["talk", "send", workspace_id, "大家这章做得好"])
    assert result.exit_code == 0, result.output

    assert list_motives(DB(load_settings()), workspace_id) == []


def test_talk_feedback_failure_keeps_author_message(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("novel_editorial.core.motives.upsert_motive_feedback", boom)
    result = runner.invoke(app, ["talk", "send", workspace_id, "@写手 做得好"])
    assert result.exit_code == 0, result.output
    assert (
        "warning: motive feedback skipped (upsert author_feedback:praise): boom"
        in result.output
    )

    db = DB(load_settings())
    messages = list_messages(db, workspace_id)
    assert any(
        message.role == "author" and "做得好" in message.content
        for message in messages
    )
    assert list_motives(db, workspace_id) == []
