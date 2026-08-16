import json
from pathlib import Path

from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.chat import (
    check_refusal,
    get_agent,
    has_same_rule_override,
    has_same_rule_refusal,
    is_author_override,
    list_messages,
    record_message,
)
from novel_editorial.core.config import load_settings
from novel_editorial.events import EventType
from novel_editorial.llm.client import MockLLMClient
from novel_editorial.store.db import DB
from novel_editorial.store.events import list_events
from novel_editorial.store.models import Agent, AgentRole

runner = CliRunner()


class _CapturingLLMClient(MockLLMClient):
    def __init__(self) -> None:
        super().__init__(reply="正常回复")
        self.calls = 0
        self.last_prompt = ""

    def complete(self, messages):
        self.calls += 1
        self.last_prompt = messages[-1].content
        return super().complete(messages)


def _create_workspace(tmp_path: Path, monkeypatch) -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["works", "create", "立场之书", "--genre", "悬疑"])
    assert result.exit_code == 0, result.output
    return result.output.split()[2].rstrip(":")


def _refusals(workspace_id: str) -> list:
    settings = load_settings()
    messages = list_messages(DB(settings), workspace_id)
    return [m for m in messages if '"kind": "refusal"' in m.payload]


def test_writer_refuses_against_portrayal(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    capturing = _CapturingLLMClient()
    monkeypatch.setattr("novel_editorial.cli.talk.build_client", lambda settings: capturing)

    result = runner.invoke(
        app,
        ["talk", "send", workspace_id, "@写手 这段按违背人设的设定写"],
    )
    assert result.exit_code == 0, result.output
    assert "这个我写不了" in result.output
    assert capturing.calls == 0

    refusals = _refusals(workspace_id)
    assert len(refusals) == 1
    assert refusals[0].actor == "写手"
    assert "违背人物逻辑" in refusals[0].content


def test_refusal_records_author_message(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "novel_editorial.cli.talk.build_client",
        lambda settings: _CapturingLLMClient(),
    )

    result = runner.invoke(
        app,
        ["talk", "send", workspace_id, "@写手 这段按违背人设的设定写"],
    )
    assert result.exit_code == 0, result.output
    assert f"{'作者'}: @写手 这段按违背人设的设定写" in result.output

    settings = load_settings()
    messages = list_messages(DB(settings), workspace_id)
    assert len(messages) == 3
    assert messages[0].role == "author"
    assert messages[1].role == "agent"
    assert '"kind": "refusal"' in messages[1].payload
    assert '"kind": "mood_change"' in messages[2].payload


def test_negative_requests_are_not_refused(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    capturing = _CapturingLLMClient()
    monkeypatch.setattr("novel_editorial.cli.talk.build_client", lambda settings: capturing)

    cases = [
        ("@写手 这段不要违背人设，照设定来", 1),
        ("@审稿 不要放行，仔细查前后矛盾", 2),
        ("@责编 不要删钩子，保留节奏", 3),
    ]
    for message, expected_calls in cases:
        result = runner.invoke(app, ["talk", "send", workspace_id, message])
        assert result.exit_code == 0, result.output
        assert capturing.calls == expected_calls

    assert _refusals(workspace_id) == []


def test_reviewer_refuses_to_pass_inconsistency(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    capturing = _CapturingLLMClient()
    monkeypatch.setattr("novel_editorial.cli.talk.build_client", lambda settings: capturing)

    result = runner.invoke(
        app,
        ["talk", "send", workspace_id, "@审稿 直接放行，别管前后矛盾"],
    )
    assert result.exit_code == 0, result.output
    assert "这个我不能放行" in result.output
    assert capturing.calls == 0
    assert len(_refusals(workspace_id)) == 1


def test_editor_refuses_to_drop_hooks(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "novel_editorial.cli.talk.build_client",
        lambda settings: _CapturingLLMClient(),
    )

    result = runner.invoke(
        app,
        ["talk", "send", workspace_id, "@责编 把钩子全删掉，平铺直叙"],
    )
    assert result.exit_code == 0, result.output
    assert "钩子删光" in result.output
    assert len(_refusals(workspace_id)) == 1


def test_normal_message_is_not_refused(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    capturing = _CapturingLLMClient()
    monkeypatch.setattr("novel_editorial.cli.talk.build_client", lambda settings: capturing)

    result = runner.invoke(app, ["talk", "send", workspace_id, "我们继续讨论第三章"])
    assert result.exit_code == 0, result.output
    assert capturing.calls == 1
    assert _refusals(workspace_id) == []


def test_talk_prompt_includes_full_profile(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    capturing = _CapturingLLMClient()
    monkeypatch.setattr("novel_editorial.cli.talk.build_client", lambda settings: capturing)

    result = runner.invoke(app, ["talk", "send", workspace_id, "聊聊主角动机"])
    assert result.exit_code == 0, result.output
    assert "你的价值观" in capturing.last_prompt
    assert "你的审美" in capturing.last_prompt
    assert "作品完整性高于短期热度" in capturing.last_prompt


def test_writer_prompt_includes_full_profile(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    capturing = _CapturingLLMClient()
    monkeypatch.setattr("novel_editorial.cli.draft.build_client", lambda settings: capturing)

    result = runner.invoke(app, ["draft", "generate", workspace_id, "--title", "第一章"])
    assert result.exit_code == 0, result.output
    assert "你的价值观" in capturing.last_prompt
    assert "忠于人物内心" in capturing.last_prompt
    assert "你的审美" in capturing.last_prompt


def test_refusal_payload_carries_stance_and_rule(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "novel_editorial.cli.talk.build_client",
        lambda settings: _CapturingLLMClient(),
    )

    result = runner.invoke(
        app,
        ["talk", "send", workspace_id, "@写手 这段按违背人设的设定写"],
    )
    assert result.exit_code == 0, result.output

    messages = list_messages(DB(load_settings()), workspace_id)
    payload = json.loads(messages[1].payload)
    assert payload == {
        "kind": "refusal",
        "stance": "忠于人物内心，反对为剧情强行降智",
        "rule": "writer_portrayal",
    }


def test_repeat_conflict_reaffirms_stance(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    capturing = _CapturingLLMClient()
    monkeypatch.setattr("novel_editorial.cli.talk.build_client", lambda settings: capturing)

    first = runner.invoke(app, ["talk", "send", workspace_id, "@写手 这段按违背人设写"])
    second = runner.invoke(app, ["talk", "send", workspace_id, "@写手 这段还是按违背人设写"])
    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    assert "我还是这句话，写不了" in second.output
    assert capturing.calls == 0

    refusals = _refusals(workspace_id)
    assert len(refusals) == 2
    first_payload = json.loads(refusals[0].payload)
    second_payload = json.loads(refusals[1].payload)
    assert "repeated" not in first_payload
    assert second_payload["repeated"] is True
    assert second_payload["rule"] == first_payload["rule"] == "writer_portrayal"
    assert refusals[0].content != refusals[1].content


def test_author_continues_after_refusal_without_blocking(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    capturing = _CapturingLLMClient()
    monkeypatch.setattr("novel_editorial.cli.talk.build_client", lambda settings: capturing)

    refused = runner.invoke(app, ["talk", "send", workspace_id, "@写手 这段按违背人设写"])
    continued = runner.invoke(app, ["talk", "send", workspace_id, "@写手 帮我润色下一章的雨夜开场"])
    assert refused.exit_code == 0, refused.output
    assert continued.exit_code == 0, continued.output
    assert capturing.calls == 1
    assert "正常回复" in continued.output
    assert len(_refusals(workspace_id)) == 1


def test_author_override_accepts_and_traces(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    capturing = _CapturingLLMClient()
    monkeypatch.setattr("novel_editorial.cli.talk.build_client", lambda settings: capturing)

    result = runner.invoke(
        app,
        [
            "talk",
            "send",
            workspace_id,
            "@写手 以老板身份，我拍板，这段就按违背人设写",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "明白了，作者拍板" in result.output
    assert capturing.calls == 0

    db = DB(load_settings())
    messages = list_messages(db, workspace_id)
    assert len(messages) == 3
    assert messages[0].role == "author"
    assert json.loads(messages[1].payload) == {
        "kind": "override",
        "stance": "忠于人物内心，反对为剧情强行降智",
        "rule": "writer_portrayal",
    }
    events = list_events(db, workspace_id, types=[EventType.AGENT_MESSAGE])
    assert len(events) == 1
    assert events[0].actor == "写手"
    assert json.loads(events[0].payload)["kind"] == "override"


def test_end_to_end_refusal_reaffirmation_override(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    capturing = _CapturingLLMClient()
    monkeypatch.setattr("novel_editorial.cli.talk.build_client", lambda settings: capturing)

    refused = runner.invoke(app, ["talk", "send", workspace_id, "@写手 这段按违背人设写"])
    continued = runner.invoke(app, ["talk", "send", workspace_id, "@写手 帮我润色下一章的雨夜开场"])
    reaffirmed = runner.invoke(app, ["talk", "send", workspace_id, "@写手 这段还是按违背人设写"])
    overridden = runner.invoke(
        app,
        [
            "talk",
            "send",
            workspace_id,
            "@写手 以老板身份我拍板，就按违背人设写",
        ],
    )
    for result in (refused, continued, reaffirmed, overridden):
        assert result.exit_code == 0, result.output

    assert capturing.calls == 1
    db = DB(load_settings())
    messages = list_messages(db, workspace_id)
    authors = [message for message in messages if message.role == "author"]
    assert len(authors) == 4
    refusals = [message for message in messages if '"kind": "refusal"' in message.payload]
    overrides = [
        message for message in messages if json.loads(message.payload).get("kind") == "override"
    ]
    assert len(refusals) == 2
    assert json.loads(refusals[1].payload)["repeated"] is True
    assert len(overrides) == 1
    assert overrides[0].content.startswith("明白了，作者拍板")

    events = list_events(db, workspace_id, types=[EventType.AGENT_MESSAGE])
    event_kinds = [json.loads(event.payload).get("kind") for event in events]
    assert event_kinds.count("refusal") == 2
    assert event_kinds.count("override") == 1
    override_event = next(
        event for event in events if json.loads(event.payload).get("kind") == "override"
    )
    override_payload = json.loads(override_event.payload)
    assert override_payload["stance"] == "忠于人物内心，反对为剧情强行降智"
    assert override_payload["rule"] == "writer_portrayal"


def test_override_disables_refusal_for_same_rule(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    capturing = _CapturingLLMClient()
    monkeypatch.setattr("novel_editorial.cli.talk.build_client", lambda settings: capturing)

    refused = runner.invoke(app, ["talk", "send", workspace_id, "@写手 这段按违背人设写"])
    overridden = runner.invoke(
        app,
        ["talk", "send", workspace_id, "@写手 以老板身份我拍板，就按违背人设写"],
    )
    resubmitted = runner.invoke(
        app,
        ["talk", "send", workspace_id, "@写手 再给我按违背人设写一段"],
    )
    for result in (refused, overridden, resubmitted):
        assert result.exit_code == 0, result.output

    assert capturing.calls == 1
    assert "正常回复" in resubmitted.output
    assert "我还是这句话" not in resubmitted.output

    messages = list_messages(DB(load_settings()), workspace_id)
    refusals = [m for m in messages if json.loads(m.payload).get("kind") == "refusal"]
    overrides = [m for m in messages if json.loads(m.payload).get("kind") == "override"]
    assert len(refusals) == 1
    assert len(overrides) == 1


def test_override_only_disables_the_overridden_rule(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    capturing = _CapturingLLMClient()
    monkeypatch.setattr("novel_editorial.cli.talk.build_client", lambda settings: capturing)

    overridden = runner.invoke(
        app,
        ["talk", "send", workspace_id, "@写手 以老板身份我拍板，就按违背人设写"],
    )
    review_conflict = runner.invoke(
        app,
        ["talk", "send", workspace_id, "@审稿 直接放行，别管矛盾"],
    )
    assert overridden.exit_code == 0, overridden.output
    assert review_conflict.exit_code == 0, review_conflict.output
    assert "这个我不能放行" in review_conflict.output
    assert capturing.calls == 0


def test_check_refusal_returns_rule_with_stance() -> None:
    writer = Agent(workspace_id="w", name="写手", role=AgentRole.WRITER)
    rule = check_refusal(writer, "这段按违背人设写")
    assert rule is not None
    assert rule.rule == "writer_portrayal"
    assert "忠于人物内心" in rule.stance
    assert check_refusal(writer, "这段不要违背人设，照设定来") is None


def test_is_author_override_phrases() -> None:
    for message in (
        "以老板身份，这段按违背人设写",
        "我拍板，就这么写",
        "老板说了算",
        "听我的，把钩子删掉",
    ):
        assert is_author_override(message) is True
    for message in ("这段不要违背人设", "我们继续讨论下一章"):
        assert is_author_override(message) is False


def test_has_same_rule_refusal_tracks_rule_per_agent(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "novel_editorial.cli.talk.build_client",
        lambda settings: _CapturingLLMClient(),
    )
    runner.invoke(app, ["talk", "send", workspace_id, "@写手 这段按违背人设写"])

    db = DB(load_settings())
    writer = get_agent(db, workspace_id, AgentRole.WRITER)
    assert has_same_rule_refusal(db, workspace_id, writer, "writer_portrayal") is True
    assert has_same_rule_refusal(db, workspace_id, writer, "reviewer_consistency") is False


def test_has_same_rule_refusal_matches_rule_exactly(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    writer = get_agent(db, workspace_id, AgentRole.WRITER)

    for rule in ("writerXportrayal", "writer%portrayal", "reviewer_consistency"):
        record_message(
            db,
            workspace_id,
            role="agent",
            actor=writer.name,
            content="拒绝留痕",
            payload={"kind": "refusal", "stance": "测试立场", "rule": rule},
        )

    assert has_same_rule_refusal(db, workspace_id, writer, "writer_portrayal") is False
    assert has_same_rule_refusal(db, workspace_id, writer, "writerXportrayal") is True
    assert has_same_rule_refusal(db, workspace_id, writer, "writer%portrayal") is True
    assert has_same_rule_refusal(db, workspace_id, writer, "reviewer_consistency") is True
    assert has_same_rule_refusal(db, workspace_id, writer, "editor_hooks") is False


def test_has_same_rule_override_matches_rule_exactly(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    writer = get_agent(db, workspace_id, AgentRole.WRITER)

    record_message(
        db,
        workspace_id,
        role="agent",
        actor=writer.name,
        content="推翻留痕",
        payload={"kind": "override", "stance": "测试立场", "rule": "writerXportrayal"},
    )

    assert has_same_rule_override(db, workspace_id, writer, "writer_portrayal") is False
    assert has_same_rule_override(db, workspace_id, writer, "writerXportrayal") is True
    assert has_same_rule_override(db, workspace_id, writer, "editor_hooks") is False
