from pathlib import Path

from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.config import load_settings
from novel_editorial.core.draft import get_draft_version
from novel_editorial.core.style import get_style_anchor
from novel_editorial.llm.client import MockLLMClient
from novel_editorial.store.db import DB

runner = CliRunner()


def _create_workspace(tmp_path: Path, monkeypatch, title: str = "风格之书") -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["works", "create", title, "--genre", "武侠"])
    assert result.exit_code == 0, result.output
    return result.output.split()[2].rstrip(":")


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


def test_draft_generate_versions_and_diff(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    replies = iter(["雨夜的开场，第一版。", "雨夜的开场，第二版，更冷。"])
    monkeypatch.setattr(
        "novel_editorial.cli.app.build_client",
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
        "novel_editorial.cli.app.build_client",
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
