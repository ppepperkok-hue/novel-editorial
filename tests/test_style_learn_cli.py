"""CLI end-to-end tests for ``style learn`` (N20 S2)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.chat import list_messages
from novel_editorial.core.config import load_settings
from novel_editorial.store.db import DB

runner = CliRunner()

SHORT_CORPUS = {
    "a.txt": "他推门进来。她站着没动。月光洒落。",
    "b.md": "风停了。雨也停了。",
}


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))


def _create_workspace(tmp_path: Path) -> str:
    result = runner.invoke(app, ["works", "create", "风格学习之书", "--genre", "悬疑"])
    assert result.exit_code == 0, result.output
    match = re.search(r"created workspace (\w+):", result.output)
    assert match is not None, result.output
    return match.group(1)


def _write_corpus(tmp_path: Path, files: dict[str, str]) -> Path:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    for name, content in files.items():
        (corpus / name).write_text(content, encoding="utf-8")
    return corpus


def test_style_learn_reports_profile_without_writing(
    tmp_path: Path,
) -> None:
    workspace_id = _create_workspace(tmp_path)
    corpus = _write_corpus(tmp_path, SHORT_CORPUS)

    result = runner.invoke(app, ["style", "learn", workspace_id, str(corpus)])

    assert result.exit_code == 0, result.output
    assert "samples: 2" in result.output
    assert "avg sentence length: 4.2 字" in result.output
    assert "short sentence ratio: 100.0%" in result.output
    assert "modifier per 1000 chars: 0.0" in result.output
    assert "ai words in corpus:" not in result.output
    assert "suggested description: 短句，节奏快，修饰克制" in result.output
    assert "style anchor updated" not in result.output

    shown = runner.invoke(app, ["style", "show", workspace_id])
    assert shown.exit_code == 0, shown.output
    assert "description: (empty)" in shown.output
    assert "forbidden: (empty)" in shown.output


def test_style_learn_apply_writes_description_and_keeps_forbidden(
    tmp_path: Path,
) -> None:
    workspace_id = _create_workspace(tmp_path)
    corpus = _write_corpus(tmp_path, SHORT_CORPUS)
    preset = runner.invoke(
        app,
        ["style", "set", workspace_id, "--forbidden", "璀璨,宛如"],
    )
    assert preset.exit_code == 0, preset.output

    result = runner.invoke(
        app, ["style", "learn", workspace_id, str(corpus), "--apply"]
    )

    assert result.exit_code == 0, result.output
    assert "apply: description = 短句，节奏快，修饰克制" in result.output
    assert "style anchor updated: " in result.output

    shown = runner.invoke(app, ["style", "show", workspace_id])
    assert shown.exit_code == 0, shown.output
    assert "description: 短句，节奏快，修饰克制" in shown.output
    assert "forbidden: 璀璨,宛如" in shown.output

    db = DB(load_settings())
    assert list_messages(db, workspace_id) == []


def test_style_learn_apply_is_idempotent(tmp_path: Path) -> None:
    workspace_id = _create_workspace(tmp_path)
    corpus = _write_corpus(tmp_path, SHORT_CORPUS)

    first = runner.invoke(
        app, ["style", "learn", workspace_id, str(corpus), "--apply"]
    )
    assert first.exit_code == 0, first.output
    second = runner.invoke(
        app, ["style", "learn", workspace_id, str(corpus), "--apply"]
    )
    assert second.exit_code == 0, second.output
    assert second.output == first.output

    shown = runner.invoke(app, ["style", "show", workspace_id])
    assert shown.exit_code == 0, shown.output
    assert "description: 短句，节奏快，修饰克制" in shown.output


def test_style_learn_reports_ai_words_when_hit(tmp_path: Path) -> None:
    workspace_id = _create_workspace(tmp_path)
    corpus = _write_corpus(tmp_path, {"ai.txt": "她不禁莞尔，月光宛如薄纱。"})

    result = runner.invoke(app, ["style", "learn", workspace_id, str(corpus)])

    assert result.exit_code == 0, result.output
    assert "ai words in corpus: 不禁、宛如" in result.output


def test_style_learn_empty_corpus_is_usage_error(tmp_path: Path) -> None:
    workspace_id = _create_workspace(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()

    result = runner.invoke(app, ["style", "learn", workspace_id, str(empty)])

    assert result.exit_code == 2
    assert "corpus contains no readable samples" in result.output


def test_style_learn_missing_corpus_path_is_not_found(tmp_path: Path) -> None:
    workspace_id = _create_workspace(tmp_path)
    missing = tmp_path / "missing-corpus"

    result = runner.invoke(app, ["style", "learn", workspace_id, str(missing)])

    assert result.exit_code == 1
    assert "corpus path not found" in result.output


def test_style_learn_missing_workspace_is_not_found(tmp_path: Path) -> None:
    corpus = _write_corpus(tmp_path, SHORT_CORPUS)

    result = runner.invoke(app, ["style", "learn", "nope", str(corpus)])

    assert result.exit_code == 1
    assert "workspace not found" in result.output
