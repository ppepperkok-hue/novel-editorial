from pathlib import Path

from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.chat import record_message
from novel_editorial.core.config import load_settings
from novel_editorial.llm.client import MockLLMClient
from novel_editorial.store.db import DB

runner = CliRunner()


def _create_workspace(
    tmp_path: Path,
    monkeypatch,
    *,
    title: str = "穿透之书",
    genre: str = "悬疑",
    description: str = "雨夜的都市故事",
) -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(
        app,
        [
            "works",
            "create",
            title,
            "--genre",
            genre,
            "--description",
            description,
        ],
    )
    assert result.exit_code == 0, result.output
    return result.output.split()[2].rstrip(":")


def _add_note(workspace_id: str, target: str, content: str) -> None:
    result = runner.invoke(
        app,
        ["memory", "note", workspace_id, target, "--content", content, "--as", target],
    )
    assert result.exit_code == 0, result.output


def test_inspect_hits_every_layer_with_citation(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(
        tmp_path,
        monkeypatch,
        title="钩子之书",
        genre="悬疑",
        description="钩子驱动的悬疑故事",
    )
    monkeypatch.setattr(
        "novel_editorial.cli.app.build_client",
        lambda settings: MockLLMClient(reply="雨夜开场，钩子埋在最暗处。"),
    )
    styled = runner.invoke(
        app,
        [
            "style",
            "set",
            workspace_id,
            "--description",
            "开篇必须下钩子",
            "--forbidden",
            "机器腔",
        ],
    )
    assert styled.exit_code == 0, styled.output
    talked = runner.invoke(app, ["talk", "send", workspace_id, "第一章的钩子怎么埋"])
    assert talked.exit_code == 0, talked.output
    generated = runner.invoke(app, ["draft", "generate", workspace_id, "--title", "第一章"])
    assert generated.exit_code == 0, generated.output
    draft_id = generated.output.split()[1]
    reviewed = runner.invoke(
        app,
        ["review", "add", draft_id, "--from", "责编", "--content", "这个钩子太弱了"],
    )
    assert reviewed.exit_code == 0, reviewed.output
    decided = runner.invoke(
        app,
        ["decision", "note", draft_id, "--content", "钩子方向没问题"],
    )
    assert decided.exit_code == 0, decided.output
    _add_note(workspace_id, "写手", "钩子要埋在下雨天")
    planted = runner.invoke(
        app,
        [
            "plot",
            "plant",
            workspace_id,
            "--kind",
            "foreshadow",
            "--content",
            "主角的钩子项链是伏笔",
        ],
    )
    assert planted.exit_code == 0, planted.output

    result = runner.invoke(app, ["inspect", workspace_id, "钩子"])
    assert result.exit_code == 0, result.output
    assert "[档案]" in result.output
    assert "（来源: 作品《钩子之书》）" in result.output
    assert "[风格]" in result.output
    assert "（来源: 风格锚点）" in result.output
    assert "[对话]" in result.output
    assert "（来源: 作者）" in result.output
    assert "[意见]" in result.output
    assert "（来源: 责编）" in result.output
    assert "[版本]" in result.output
    assert "（来源: 第一章 v1）" in result.output
    assert "[笔记]" in result.output
    assert "（来源: 写手）" in result.output
    assert "[决策]" in result.output
    assert "（来源: 决策 note（作者））" in result.output
    assert "[线索]" in result.output
    assert "（来源: 线索 伏笔（planted））" in result.output
    assert "钩子埋在最暗处" in result.output

    positions = [result.output.index(tag) for tag in ("[档案]", "[风格]", "[对话]", "[意见]")]
    positions.extend(
        result.output.index(tag) for tag in ("[版本]", "[笔记]", "[决策]", "[线索]")
    )
    assert positions == sorted(positions)


def test_inspect_searches_auxiliary_fields(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "novel_editorial.cli.app.build_client",
        lambda settings: MockLLMClient(reply="雨夜的开场白。"),
    )
    styled = runner.invoke(
        app, ["style", "set", workspace_id, "--forbidden", "机器腔,Ai味"]
    )
    assert styled.exit_code == 0, styled.output
    settings = load_settings()
    db = DB(settings)
    record_message(db, workspace_id, role="agent", actor="写手", content="正文草稿")
    _add_note(workspace_id, "责编", "节奏笔记")
    generated = runner.invoke(app, ["draft", "generate", workspace_id, "--title", "钩子章"])
    assert generated.exit_code == 0, generated.output
    draft_id = generated.output.split()[1]
    accepted = runner.invoke(app, ["decision", "accept", draft_id])
    assert accepted.exit_code == 0, accepted.output
    planted = runner.invoke(
        app,
        [
            "plot",
            "plant",
            workspace_id,
            "--kind",
            "foreshadow",
            "--content",
            "项链在第三章出现",
        ],
    )
    assert planted.exit_code == 0, planted.output

    style_result = runner.invoke(app, ["inspect", workspace_id, "ai味"])
    assert style_result.exit_code == 0, style_result.output
    assert "[风格]" in style_result.output
    assert "（来源: 风格锚点）" in style_result.output

    actor_result = runner.invoke(app, ["inspect", workspace_id, "写手"])
    assert actor_result.exit_code == 0, actor_result.output
    assert "[对话]" in actor_result.output
    assert "（来源: 写手）" in actor_result.output

    owner_result = runner.invoke(app, ["inspect", workspace_id, "责编"])
    assert owner_result.exit_code == 0, owner_result.output
    assert "[笔记]" in owner_result.output
    assert "（来源: 责编）" in owner_result.output

    title_result = runner.invoke(app, ["inspect", workspace_id, "钩子章"])
    assert title_result.exit_code == 0, title_result.output
    assert "[版本]" in title_result.output
    assert "（来源: 钩子章 v1）" in title_result.output

    action_result = runner.invoke(app, ["inspect", workspace_id, "accept"])
    assert action_result.exit_code == 0, action_result.output
    assert "[决策]" in action_result.output
    assert "（来源: 决策 accept（作者））" in action_result.output

    kind_result = runner.invoke(app, ["inspect", workspace_id, "foreshadow"])
    assert kind_result.exit_code == 0, kind_result.output
    assert "[线索]" in kind_result.output
    assert "（来源: 线索 伏笔（planted））" in kind_result.output

    status_result = runner.invoke(app, ["inspect", workspace_id, "planted"])
    assert status_result.exit_code == 0, status_result.output
    assert "[线索]" in status_result.output


def test_inspect_isolated_between_workspaces(tmp_path: Path, monkeypatch) -> None:
    workspace_a = _create_workspace(tmp_path, monkeypatch, title="甲书")
    workspace_b = _create_workspace(tmp_path, monkeypatch, title="乙书")
    planted = runner.invoke(
        app,
        ["plot", "plant", workspace_a, "--kind", "hook", "--content", "甲书秘密钩子"],
    )
    assert planted.exit_code == 0, planted.output
    _add_note(workspace_b, "写手", "乙书专属备忘")

    leaked = runner.invoke(app, ["inspect", workspace_b, "甲书秘密钩子"])
    assert leaked.exit_code == 0, leaked.output
    assert leaked.output.strip() == "no matches"

    leaked_other = runner.invoke(app, ["inspect", workspace_a, "乙书专属备忘"])
    assert leaked_other.exit_code == 0, leaked_other.output
    assert leaked_other.output.strip() == "no matches"

    found = runner.invoke(app, ["inspect", workspace_a, "甲书秘密钩子"])
    assert found.exit_code == 0, found.output
    assert "[线索]" in found.output
    assert "（来源: 线索 钩子（planted））" in found.output


def test_inspect_no_matches(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(app, ["inspect", workspace_id, "不存在的词"])
    assert result.exit_code == 0, result.output
    assert result.output.strip() == "no matches"


def test_inspect_blank_keyword_usage_error(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(app, ["inspect", workspace_id, "   "])
    assert result.exit_code == 2
    assert "must not be empty" in result.output


def test_inspect_missing_workspace(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["inspect", "nope", "关键词"])
    assert result.exit_code == 1
    assert "workspace not found" in result.output
