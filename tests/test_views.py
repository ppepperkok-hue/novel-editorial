from pathlib import Path

import pytest
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
    title: str = "视图之书",
    genre: str = "都市",
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


def test_writer_view_includes_own_notes_only(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    _add_note(workspace_id, "写手", "写手私藏")
    _add_note(workspace_id, "责编", "责编私藏")

    viewed = runner.invoke(app, ["memory", "view", workspace_id, "--as", "写手"])
    assert viewed.exit_code == 0, viewed.output
    assert "写手私藏" in viewed.output
    assert "责编私藏" not in viewed.output
    assert "视图之书" in viewed.output
    assert "章纲" in viewed.output

    packed = runner.invoke(app, ["memory", "pack", workspace_id])
    assert packed.exit_code == 0, packed.output
    assert packed.output == viewed.output


@pytest.mark.parametrize("role", ["总编", "主编", "责编"])
def test_editor_view_profile_and_conversation_without_private_memory(
    tmp_path: Path, monkeypatch, role: str
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    _add_note(workspace_id, "写手", "写手私藏")
    settings = load_settings()
    db = DB(settings)
    record_message(db, workspace_id, role="author", actor="作者", content="主角动机到底是什么")
    record_message(db, workspace_id, role="agent", actor="写手", content="他想要一场公平的雨")

    viewed = runner.invoke(app, ["memory", "view", workspace_id, "--as", role])
    assert viewed.exit_code == 0, viewed.output
    assert "作品档案" in viewed.output
    assert "视图之书" in viewed.output
    assert "雨夜的都市故事" in viewed.output
    assert "最近对话" in viewed.output
    assert "主角动机到底是什么" in viewed.output
    assert "他想要一场公平的雨" in viewed.output
    assert "写手私藏" not in viewed.output


def test_boss_view_band_drafts_reviews_decisions(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "novel_editorial.cli.draft.build_client",
        lambda settings: MockLLMClient(reply="雨夜的开场，钩子埋下。"),
    )
    generated = runner.invoke(app, ["draft", "generate", workspace_id, "--title", "雨夜"])
    assert generated.exit_code == 0, generated.output
    draft_id = generated.output.split()[1]
    assert (
        runner.invoke(
            app,
            ["review", "add", draft_id, "--from", "责编", "--content", "钩子再亮一点"],
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(
            app,
            ["decision", "note", draft_id, "--content", "方向没问题"],
        ).exit_code
        == 0
    )

    viewed = runner.invoke(app, ["memory", "view", workspace_id, "--as", "作者"])
    assert viewed.exit_code == 0, viewed.output
    assert "班子状态" in viewed.output
    for name in ("总编", "责编", "写手", "审稿"):
        assert name in viewed.output
    assert "草稿" in viewed.output
    assert "雨夜" in viewed.output
    assert "v1" in viewed.output
    assert "最近意见" in viewed.output
    assert "钩子再亮一点" in viewed.output
    assert "最近决策" in viewed.output
    assert "方向没问题" in viewed.output


def test_memory_view_invalid_role_exit_2(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(app, ["memory", "view", workspace_id, "--as", "路人"])
    assert result.exit_code == 2
    assert "invalid view role" in result.output


def test_memory_view_missing_workspace(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["memory", "view", "nope", "--as", "主编"])
    assert result.exit_code == 1
    assert "workspace not found" in result.output


def test_memory_search_hits_every_source_with_citation(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch, description="钩子驱动的悬疑故事")
    monkeypatch.setattr(
        "novel_editorial.cli.draft.build_client",
        lambda settings: MockLLMClient(reply="雨夜开场，钩子埋在最暗处。"),
    )
    generated = runner.invoke(app, ["draft", "generate", workspace_id, "--title", "第一章"])
    assert generated.exit_code == 0, generated.output
    draft_id = generated.output.split()[1]
    settings = load_settings()
    db = DB(settings)
    record_message(db, workspace_id, role="author", actor="作者", content="第三章的钩子别忘了")
    assert (
        runner.invoke(
            app,
            ["review", "add", draft_id, "--from", "责编", "--content", "这个钩子太弱了"],
        ).exit_code
        == 0
    )
    _add_note(workspace_id, "写手", "钩子埋在下雨天")

    result = runner.invoke(app, ["memory", "search", workspace_id, "钩子"])
    assert result.exit_code == 0, result.output
    assert "[档案]" in result.output
    assert "（来源: 作品《视图之书》）" in result.output
    assert "[对话]" in result.output
    assert "（来源: 作者）" in result.output
    assert "[意见]" in result.output
    assert "（来源: 责编）" in result.output
    assert "[版本]" in result.output
    assert "（来源: 第一章 v1）" in result.output
    assert "[笔记]" in result.output
    assert "（来源: 写手）" in result.output
    assert "钩子埋在最暗处" in result.output


def test_memory_search_is_case_insensitive(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    _add_note(workspace_id, "写手", "The Hook is here")

    result = runner.invoke(app, ["memory", "search", workspace_id, "hook"])
    assert result.exit_code == 0, result.output
    assert "[笔记]" in result.output
    assert "The Hook is here" in result.output


def test_memory_search_isolated_between_workspaces(tmp_path: Path, monkeypatch) -> None:
    workspace_a = _create_workspace(tmp_path, monkeypatch, title="甲书")
    workspace_b = _create_workspace(tmp_path, monkeypatch, title="乙书")
    _add_note(workspace_a, "写手", "甲书秘密钩子")

    leaked = runner.invoke(app, ["memory", "search", workspace_b, "甲书秘密钩子"])
    assert leaked.exit_code == 0, leaked.output
    assert leaked.output.strip() == "no matches"

    found = runner.invoke(app, ["memory", "search", workspace_a, "甲书秘密钩子"])
    assert found.exit_code == 0, found.output
    assert "[笔记]" in found.output


def test_memory_search_no_matches(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(app, ["memory", "search", workspace_id, "不存在的词"])
    assert result.exit_code == 0, result.output
    assert result.output.strip() == "no matches"


def test_memory_search_blank_keyword_usage_error(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(app, ["memory", "search", workspace_id, "   "])
    assert result.exit_code == 2
    assert "must not be empty" in result.output
