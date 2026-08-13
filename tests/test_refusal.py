from pathlib import Path

from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.chat import list_messages
from novel_editorial.core.config import load_settings
from novel_editorial.llm.client import MockLLMClient
from novel_editorial.store.db import DB

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
